# ruff: noqa: F811  (pytest fixtures imported from the rehearsal module are re-requested by name)
"""Audit replay of a COMPLETED governed run: reproduction, refusals, no attempt consumed.

Synthetic only (the rehearsal ``world``). The audit tool is the same code the CLI calls.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.governance import errors as gov_errors
from app.research.range002.governance.model import Phase
from app.research.range002.governance.results_guard import authorize
from app.research.range002.governance.run_registry import RunRegistry, RunStatus
from tests.research.range002.screen.test_descriptive_run_rehearsal import (  # noqa: F401
    CODE_SHA,
    minutes_root,
    rds,
    world,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import audit_replay_run as ar  # noqa: E402


def _args(world: dict[str, Any], parent: Any, audit_id: str, **over: Any) -> list[str]:
    k = world["kwargs"]
    tmp: Path = world["tmp"]
    vals: dict[str, Any] = {
        "parent-run-id": parent.run_id,
        "audit-id": audit_id,
        "spec": k["spec_path"],
        "registry": k["registry_path"],
        "parent-report": parent.report_json,
        "daily-snapshot": k["daily_snapshot"],
        "snapshot-manifest": k["snapshot_manifest"],
        "minute-bars": k["minute_bars"],
        "minute-feed": k["minute_feed"],
        "minute-ts-convention": k["minute_ts_convention"],
        "table-filter": k["table_filter"],
        "lookback-calendar-days": k["lookback_calendar_days"],
        "coverage-threshold": k["coverage_threshold"],
        "equity": k["equity"],
        "tick": k["tick"],
        "code-sha": k["code_sha"],
        "out-dir": tmp / f"audit_{audit_id}",
        "audit-log": tmp / "audit_log.jsonl",
    }
    vals.update({key.replace("_", "-"): v for key, v in over.items()})
    argv: list[str] = []
    for key, v in vals.items():
        argv += [f"--{key}", str(v)]
    return argv


@pytest.fixture
def parent(world: dict[str, Any]) -> Any:
    out = rds.run(**world["kwargs"])
    assert out.status == rds.STATUS_COMPLETE
    return out


def _log(world: dict[str, Any]) -> list[dict[str, Any]]:
    p: Path = world["tmp"] / "audit_log.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_audit_reproduces_parent_without_consuming_an_attempt(
    world: dict[str, Any], parent: Any
) -> None:
    reg = RunRegistry(world["registry_path"])
    before = [r for r in reg.runs() if r.phase is Phase.P3A]
    rc = ar.main(_args(world, parent, "AUDIT-TEST-0001"))
    assert rc == ar.EXIT_OK
    rep = json.loads((world["tmp"] / "audit_AUDIT-TEST-0001" / "audit_report.json").read_text())
    assert rep["reproduction"]["matches_parent"] is True
    assert rep["arithmetic"]["trades_with_discrepancy"] == 0
    assert rep["findings"]["per_candidate"]
    # the parent annotation is a separate block; the parent's own report is not changed
    ann = rep["parent_annotation"]
    assert ann["parent_status_original"] == parent.status
    assert ann["measures"]["returned_coverage"]["meets"] is True
    assert "advancement" in ann
    diag = rep["findings"]["or_incomplete_diagnostics"]
    assert "UNRESOLVED" in diag["classification"]
    reg2 = RunRegistry(world["registry_path"])
    assert len([r for r in reg2.runs() if r.phase is Phase.P3A]) == len(before)
    audit_rows = [r for r in reg2.runs() if r.phase is Phase.AUDIT]
    assert len(audit_rows) == 1 and audit_rows[0].status is RunStatus.COMPLETED
    # the parent stays closed; its original report is untouched
    assert reg2.get_run(parent.run_id).status is RunStatus.COMPLETED
    assert hashlib.sha256(parent.report_json.read_bytes()).hexdigest() == parent.report_sha256
    # per-candidate trade files exist and the audit is non-citable
    assert list((world["tmp"] / "audit_AUDIT-TEST-0001").glob("trades_*.jsonl"))


def test_every_invocation_is_logged_and_chained(world: dict[str, Any], parent: Any) -> None:
    assert ar.main(_args(world, parent, "AUDIT-TEST-0002")) == ar.EXIT_OK
    entries = _log(world)
    assert [e["event"] for e in entries] == [
        "audit_invocation",
        "audit_capability_issued",
        "audit_outcome",
    ]
    lines = (world["tmp"] / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()
    for prev, cur in zip(lines, lines[1:], strict=False):
        assert json.loads(cur)["prev_line_sha256"] == hashlib.sha256(prev.encode()).hexdigest()


def test_reused_audit_id_is_refused(world: dict[str, Any], parent: Any) -> None:
    assert ar.main(_args(world, parent, "AUDIT-TEST-0003")) == ar.EXIT_OK
    argv = _args(world, parent, "AUDIT-TEST-0003", out_dir=world["tmp"] / "second")
    assert ar.main(argv) == ar.EXIT_REFUSED
    assert _log(world)[-1]["outcome"] == "REFUSED"


@pytest.mark.parametrize(
    "override",
    [
        {"code_sha": "b" * 40},
        {"minute_feed": "iex"},
        {"table_filter": "SFP"},
        {"parent_run_id": "range002-run-999999"},
    ],
)
def test_altered_binding_is_refused(world: dict[str, Any], parent: Any, override: dict) -> None:
    rc = ar.main(_args(world, parent, "AUDIT-TEST-0004", **override))
    assert rc == ar.EXIT_REFUSED
    reg = RunRegistry(world["registry_path"])
    assert not [r for r in reg.runs() if r.phase is Phase.AUDIT]


def test_altered_report_or_store_is_refused(
    world: dict[str, Any], parent: Any, tmp_path: Path
) -> None:
    tampered = tmp_path / "report_tampered.json"
    tampered.write_bytes(parent.report_json.read_bytes().replace(b'"tick"', b'"tick "', 1))
    rep = json.loads(parent.report_json.read_text())
    rep["data"]["minute_bars"]["sha256"] = "0" * 64
    tampered.write_text(json.dumps(rep), encoding="utf-8")
    argv = _args(world, parent, "AUDIT-TEST-0005", parent_report=tampered)
    assert ar.main(argv) == ar.EXIT_REFUSED
    store: Path = world["kwargs"]["minute_bars"]
    store.write_bytes(store.read_bytes() + b"\0")
    assert ar.main(_args(world, parent, "AUDIT-TEST-0006")) == ar.EXIT_REFUSED


def test_authorize_cannot_issue_an_audit_capability(world: dict[str, Any], parent: Any) -> None:
    view, _ = rds._load_spec(world["kwargs"]["spec_path"])
    with pytest.raises(gov_errors.GovernanceError):
        authorize(
            spec=view,
            phase=Phase.AUDIT,
            partition=parent.capability.partition,
            run_id=parent.run_id,
            registry=RunRegistry(world["registry_path"]),
            exposure_ledger=None,  # type: ignore[arg-type]
            requested_range=parent.capability.date_range,
        )


def test_closed_audit_capability_is_revoked(world: dict[str, Any], parent: Any) -> None:
    # reproduce through the guard directly to keep the capability object
    from app.research.range002.governance.results_guard import (
        AuditParentBinding,
        authorize_audit_replay,
        require_capability,
    )

    view, _ = rds._load_spec(world["kwargs"]["spec_path"])
    reg = RunRegistry(world["registry_path"])
    cap = authorize_audit_replay(
        spec=view,
        registry=reg,
        parent_run_id=parent.run_id,
        audit_id="AUDIT-TEST-0007",
        binding=AuditParentBinding(
            parent_report_sha256=parent.report_sha256,
            code_sha=CODE_SHA,
            data_manifest_sha256=parent.report["data"]["snapshot_manifest_sha256"],
            authorized_range=parent.capability.date_range,
        ),
        audit_log_path=world["tmp"] / "direct_audit_log.jsonl",
    )
    assert cap.citable is False and cap.phase is Phase.AUDIT
    reg.close_run(cap.run_id, RunStatus.COMPLETED, "c" * 64)

    with pytest.raises(gov_errors.GovernanceError):
        require_capability(cap)
    with pytest.raises(gov_errors.GovernanceError):
        require_capability(parent.capability)


def _trade(**over: Any) -> Any:
    from types import SimpleNamespace

    base = 10.0 * 1e-4
    entry, r, exit_px = 100.0, 2.0, 103.0
    gross = (exit_px - entry) / r
    cost = base * (entry + exit_px) / r
    t = {
        "entry_price": entry,
        "r_fill": r,
        "exit_price": exit_px,
        "scaled_out": False,
        "gross_r": gross,
        "net_r_base": gross - cost,
        "net_r_stress": gross - 3 * cost,
    }
    t.update(over)
    return SimpleNamespace(**t)


def test_arithmetic_check_accepts_consistent_and_flags_corrupt_trades() -> None:
    assert ar._arith(_trade(), 10.0, 30.0)["problems"] == []
    bad = ar._arith(_trade(net_r_base=1.0), 10.0, 30.0)["problems"]
    assert bad and any("base cost" in p for p in bad)
    bad = ar._arith(_trade(gross_r=9.0), 10.0, 30.0)["problems"]
    assert any("gross_r" in p for p in bad)


def test_scale_out_partial_is_part_of_the_recomputation() -> None:
    entry, r, exit_px = 100.0, 2.0, 99.0
    weighted = 0.5 * (entry + r) + 0.5 * exit_px
    gross = (weighted - entry) / r
    cost = 10.0e-4 * (entry + weighted) / r
    t = _trade(
        entry_price=entry,
        r_fill=r,
        exit_price=exit_px,
        scaled_out=True,
        gross_r=gross,
        net_r_base=gross - cost,
        net_r_stress=gross - 3 * cost,
    )
    assert ar._arith(t, 10.0, 30.0)["problems"] == []
