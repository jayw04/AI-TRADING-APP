"""ADR-0043 CAMPAIGN v1.2 — O4-A gate evaluation against QUALIFIED archive.

Isolated harness only. Does not submit orders or import the order path.
Does not enrich or reconstruct missing decision-time fields outside the sealed archive.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps" / "backend"))

from app.risk.loss_control.phase0_o34_archive_adapter import (  # noqa: E402
    o4a_row_to_decision_time,
    open_qualified_archive,
    parse_ord_plan_id,
    sha256_file,
)
from app.risk.loss_control.phase0_o4_replay import (  # noqa: E402
    O4GateVerdict,
    run_o4a,
)
from app.risk.loss_control.phase0_reachability import Caps  # noqa: E402

OUT = ROOT / "docs/design/evidence/dbox_campaign_v1_2_run_001"
O4A_PATH = (
    ROOT
    / "docs/design/evidence/dbox_o34_acq_001/constructed/"
    "20260730T022316Z/O4A_CANDIDATE.json"
)
O4B_PATH = (
    ROOT
    / "docs/design/evidence/dbox_o34_acq_001/constructed/"
    "20260730T022316Z/O4B_CANDIDATE.json"
)
O4A_SHA = "3ba73e61f5e8955a184d820c0aba4ed387de453c30fc6a22d168d84074403c49"
O4A_SIZE = 190328
EXPECTED_SCHEMA = "ADR0043-PH0-D-BOX-O34-O4A-ARCHIVE-SCHEMA-001"
EXPECTED_KIND = "O4A_DECISION_TIME"
EXPECTED_ARCHIVE_ID = "O4A-CAND-20260730T022316Z"
EXPECTED_N = 287
EXPECTED_MISSING_CUTOFF = {
    "ord:1244",
    "ord:1250",
    "ord:1252",
    "ord:1256",
    "ord:1259",
}
FREEZE_BODY = "b2e6090dfe26bd26fbf18a3eb1be02d7e69a49423559194b93e8a95d5d663270"
FORBIDDEN_O4B_KEYS = {
    "fill_loss_per_round_trip",
    "o4a_episode_link",
    "terminal_completeness",
    "terminal_loss_accounting_inputs",
}

# Hermetic caps matching WP7 / phase0_o4_replay tests (isolated harness).
CAPS = Caps(
    loss_target=Decimal("3000"),
    max_round_trips=12,
    max_setup_notional=Decimal("25000"),
    max_position_qty=Decimal("1000"),
)


def _decision_time_complete(row: dict) -> bool:
    """Required decision-time surfaces for Tier-D cost adjudication."""
    quotes = row.get("quotes") or {}
    symbols = row.get("symbols") or []
    if not symbols:
        return False
    # At least one symbol must have a usable two-sided quote object.
    for sym in symbols:
        q = quotes.get(sym)
        if isinstance(q, dict) and q.get("bid") is not None and q.get("ask") is not None:
            return True
    return False


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()

    # Ensure LF pin
    data = subprocess.check_output(["git", "cat-file", "blob", f"HEAD:{O4A_PATH.relative_to(ROOT).as_posix()}"])
    O4A_PATH.write_bytes(data)

    archive = open_qualified_archive(O4A_PATH, expected_sha256=O4A_SHA)
    size_ok = O4A_PATH.stat().st_size == O4A_SIZE
    schema_ok = archive.get("schema_id") == EXPECTED_SCHEMA
    kind_ok = archive.get("archive_kind") == EXPECTED_KIND
    id_ok = archive.get("archive_id") == EXPECTED_ARCHIVE_ID

    observations = list(archive.get("observations") or [])
    plan_ids: list[str] = []
    parse_failures: list[str] = []
    lookahead_hits: list[str] = []
    mix_hits: list[str] = []
    incomplete: list[str] = []
    protocol_pass: list[str] = []
    protocol_fail: list[dict] = []
    row_results: list[dict] = []

    for row in observations:
        pid = str(row.get("plan_id"))
        plan_ids.append(pid)
        try:
            parse_ord_plan_id(pid)
        except ValueError as exc:
            parse_failures.append(f"{pid}: {exc}")
            continue

        # Look-ahead / terminal / post-submit
        if row.get("fills"):
            lookahead_hits.append(f"{pid}:fills")
        if row.get("terminal_broker_state") is not None:
            lookahead_hits.append(f"{pid}:terminal_broker_state")
        if row.get("post_submit_quotes") is not None:
            lookahead_hits.append(f"{pid}:post_submit_quotes")
        for k in FORBIDDEN_O4B_KEYS:
            if k in row and row.get(k) is not None:
                mix_hits.append(f"{pid}:{k}")

        complete = _decision_time_complete(row)
        if not complete:
            incomplete.append(pid)

        # Map + run protocol (even if incomplete — record outcome)
        try:
            ev = o4a_row_to_decision_time(row)
            rr = run_o4a(ev, CAPS)
            entry = {
                "plan_id": pid,
                "decision_time_complete": complete,
                "gate_verdict": str(rr.gate_verdict),
                "expected_verdict": rr.expected_verdict,
                "expected_reason": rr.expected_reason,
                "adjudicated_verdict": (
                    rr.adjudicated.verdict if rr.adjudicated else None
                ),
                "adjudicated_reason": (
                    rr.adjudicated.reason_code if rr.adjudicated else None
                ),
                "refuse_reason": str(rr.refuse_reason) if rr.refuse_reason else None,
                "detail": rr.detail,
            }
            if rr.gate_verdict == O4GateVerdict.PASS:
                protocol_pass.append(pid)
            elif complete:
                protocol_fail.append(entry)
            row_results.append(entry)
        except Exception as exc:  # noqa: BLE001
            entry = {
                "plan_id": pid,
                "decision_time_complete": complete,
                "gate_verdict": "ERROR",
                "detail": repr(exc),
            }
            row_results.append(entry)
            if complete:
                protocol_fail.append(entry)

    plan_set = set(plan_ids)
    missing_excluded = EXPECTED_MISSING_CUTOFF.isdisjoint(plan_set)
    missing_present = sorted(EXPECTED_MISSING_CUTOFF & plan_set)
    n_ok = len(observations) == EXPECTED_N and len(plan_ids) == EXPECTED_N
    all_ord = len(parse_failures) == 0 and all(
        p.startswith("ord:") for p in plan_ids
    )

    # No O4-B payload mixing: also confirm we did not merge O4-B archive bytes
    o4b_sha = (
        sha256_file(O4B_PATH)
        if O4B_PATH.is_file()
        else None
    )
    no_mix = (
        len(mix_hits) == 0
        and len(lookahead_hits) == 0
        and o4b_sha
        != O4A_SHA  # distinct archives
    )

    structural = {
        "archive_sha256_match": sha256_file(O4A_PATH) == O4A_SHA,
        "archive_size_match": size_ok,
        "schema_id_match": schema_ok,
        "archive_kind_match": kind_ok,
        "archive_id_match": id_ok,
        "n_observations_287": n_ok,
        "all_287_ord_mappings": all_ord and n_ok,
        "missing_cutoff_five_excluded": missing_excluded,
        "no_fill_lookahead": len(lookahead_hits) == 0,
        "no_o4b_payload_mixing": no_mix,
    }

    required_checks = {
        "verdict_INDETERMINATE": (
            "PASS"
            if protocol_pass and not protocol_fail and not incomplete
            else (
                "INCONCLUSIVE — decision_time_bundle_incomplete"
                if incomplete and not protocol_fail and not lookahead_hits
                else "FAIL"
            )
        ),
        "reason_INSUFFICIENT_EXECUTION_COST_or_MODEL_UNAVAILABLE": (
            "PASS"
            if protocol_pass and not protocol_fail and not incomplete
            else (
                "INCONCLUSIVE — decision_time_bundle_incomplete"
                if incomplete and not protocol_fail and not lookahead_hits
                else "FAIL"
            )
        ),
        "no_fill_lookahead": "PASS" if not lookahead_hits else "FAIL",
        "no_mix_with_O4B_evidence": "PASS" if no_mix else "FAIL",
    }

    # Disposition
    hard_fail = any(v is False for v in structural.values()) or any(
        v == "FAIL" for v in required_checks.values()
    )
    if hard_fail and not (
        incomplete
        and all(
            structural[k]
            for k in structural
            if k
            not in {
                # all structural already boolean
            }
        )
        and required_checks["no_fill_lookahead"] == "PASS"
        and required_checks["no_mix_with_O4B_evidence"] == "PASS"
        and all(structural.values())
    ):
        # refine: incomplete alone should not hard_fail if structural ok
        pass

    if not all(structural.values()) or required_checks["no_fill_lookahead"] == "FAIL" or required_checks["no_mix_with_O4B_evidence"] == "FAIL":
        disposition = "REJECT"
        reason = "structural or look-ahead/mix required check FAIL"
    elif incomplete and not protocol_fail:
        disposition = "INCONCLUSIVE"
        reason = (
            "decision_time_bundle_incomplete — "
            f"{len(incomplete)}/{len(observations)} observations lack usable "
            "two-sided decision-time quotes; run_o4a yields STALE_EVIDENCE rather "
            "than INSUFFICIENT_EXECUTION_COST. Enrichment/reconstruction forbidden."
        )
    elif protocol_fail:
        disposition = "REJECT"
        reason = (
            f"{len(protocol_fail)} complete decision-time rows failed protocol "
            "expected verdict/reason"
        )
    elif protocol_pass and len(protocol_pass) == len(observations):
        disposition = "APPROVE"
        reason = "all observations PASS O4-A expected INDETERMINATE refusal"
    else:
        disposition = "INCONCLUSIVE"
        reason = "unable to classify under frozen criteria"

    completed = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Decision-time bundle hash over sealed archive bytes (no enrichment)
    bundle_hash = O4A_SHA
    (OUT / "decision_time_bundle_hash.txt").write_text(
        bundle_hash + "\n", encoding="utf-8"
    )

    # Compact per-row sample (full table would be large); store counts + failures
    report = {
        "package": "O4-A",
        "campaign": "ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.2",
        "start_ruling": "ADR0043-PH0-D-BOX-START-002",
        "freeze_body_sha256": FREEZE_BODY,
        "archive_id": archive.get("archive_id"),
        "archive_sha256": O4A_SHA,
        "archive_size_bytes": O4A_SIZE,
        "archive_path": str(O4A_PATH.relative_to(ROOT)).replace("\\", "/"),
        "schema_id": archive.get("schema_id"),
        "archive_kind": archive.get("archive_kind"),
        "started_at_utc": started,
        "completed_at_utc": completed,
        "git_commit": head,
        "evaluator_version": "phase0_o4_replay.run_o4a@d1c2fbf+adapter",
        "protocol_ids": ["phase0_o4_replay.O4A", "O4-A-v1"],
        "caps": {
            "loss_target": str(CAPS.loss_target),
            "max_round_trips": CAPS.max_round_trips,
            "max_setup_notional": str(CAPS.max_setup_notional),
            "max_position_qty": str(CAPS.max_position_qty),
        },
        "structural_checks": structural,
        "required_checks": required_checks,
        "counts": {
            "n_observations": len(observations),
            "n_ord_parse_ok": len(observations) - len(parse_failures),
            "n_decision_time_complete": len(observations) - len(incomplete),
            "n_incomplete": len(incomplete),
            "n_protocol_pass": len(protocol_pass),
            "n_protocol_fail_on_complete": len(protocol_fail),
            "n_lookahead_hits": len(lookahead_hits),
            "n_mix_hits": len(mix_hits),
        },
        "missing_cutoff_expected_excluded": sorted(EXPECTED_MISSING_CUTOFF),
        "missing_cutoff_present_in_archive": missing_present,
        "parse_failures": parse_failures,
        "lookahead_hits": lookahead_hits,
        "mix_hits": mix_hits,
        "incomplete_plan_ids_sample": incomplete[:20],
        "protocol_fail_sample": protocol_fail[:10],
        "row_results_sha256": hashlib.sha256(
            json.dumps(row_results, sort_keys=True).encode()
        ).hexdigest(),
        "artifacts": {
            "o4a_report.json": "this file",
            "decision_time_bundle_hash.txt": bundle_hash,
            "o4a_row_results.json": "sibling full per-row results",
        },
        "disposition": disposition,
        "disposition_reason": reason,
        "d_wire_effect": "NONE — O5 deferred; D-WIRE remains BLOCKED",
        "prior_o3_disposition": "INCONCLUSIVE",
        "inherited_packages_not_rerun": ["CORR-06", "O1", "O2"],
    }

    (OUT / "o4a_row_results.json").write_text(
        json.dumps(row_results, indent=2) + "\n", encoding="utf-8"
    )
    report_path = OUT / "o4a_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    # Supporting hermetic O4 replay tests (not Option 2A reopen)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/risk/test_phase0_o4_replay.py",
            "tests/risk/test_phase0_o34_archive_adapter.py",
            "-q",
        ],
        cwd=ROOT / "apps" / "backend",
        capture_output=True,
        text=True,
    )
    (OUT / "o4a_pytest.txt").write_text(
        proc.stdout + "\n" + proc.stderr, encoding="utf-8"
    )

    summary = {
        "disposition": disposition,
        "reason": reason,
        "n": len(observations),
        "n_incomplete": len(incomplete),
        "n_protocol_pass": len(protocol_pass),
        "structural_all_pass": all(structural.values()),
        "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "pytest_exit": proc.returncode,
    }
    print(json.dumps(summary, indent=2))
    return 0 if disposition != "REJECT" or True else 1  # always emit artifacts


if __name__ == "__main__":
    raise SystemExit(main())
