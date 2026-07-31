"""ADR-0043 CAMPAIGN v1.2 — O4-B gate evaluation against QUALIFIED archive.

Isolated harness only. Does not submit orders or import the order path.
Does not infer missing forensic inputs from O4-A or external mutable records.
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
    o4b_row_to_forensic,
    open_qualified_archive,
    parse_ord_plan_id,
    sha256_file,
)
from app.risk.loss_control.phase0_o4_replay import (  # noqa: E402
    O4GateVerdict,
    run_o4b,
)
from app.risk.loss_control.phase0_reachability import Caps  # noqa: E402

OUT = ROOT / "docs/design/evidence/dbox_campaign_v1_2_run_001"
O4B_REL = (
    "docs/design/evidence/dbox_o34_acq_001/constructed/"
    "20260730T022316Z/O4B_CANDIDATE.json"
)
O4A_REL = (
    "docs/design/evidence/dbox_o34_acq_001/constructed/"
    "20260730T022316Z/O4A_CANDIDATE.json"
)
O4B_PATH = ROOT / O4B_REL
O4A_PATH = ROOT / O4A_REL
O4B_SHA = "e349f49465aa2689e6c24e20d6ae32286f0a447bfbcdf3b2fbbc531c656bae95"
O4A_SHA = "3ba73e61f5e8955a184d820c0aba4ed387de453c30fc6a22d168d84074403c49"
O4B_SIZE = 260426
EXPECTED_SCHEMA = "ADR0043-PH0-D-BOX-O34-O4B-ARCHIVE-SCHEMA-001"
EXPECTED_KIND = "O4B_FORENSIC"
EXPECTED_ARCHIVE_ID = "O4B-CAND-20260730T022316Z"
EXPECTED_N = 286
EXPECTED_O4B_INCOMPLETE = {
    "ord:1244",
    "ord:1250",
    "ord:1252",
    "ord:1256",
    "ord:1259",
    "ord:1384",
}
FREEZE_BODY = "b2e6090dfe26bd26fbf18a3eb1be02d7e69a49423559194b93e8a95d5d663270"
FORBIDDEN_O4A_ONLY_KEYS = {
    "cutoff_at_utc",
    "cutoff_event",
    "model_available",
    "plan_inputs",
    "post_submit_quotes",
    "authority_inputs",
}

CAPS = Caps(
    loss_target=Decimal("3000"),
    max_round_trips=12,
    max_setup_notional=Decimal("25000"),
    max_position_qty=Decimal("1000"),
)


def _forensic_surfaces_complete(row: dict) -> tuple[bool, list[str]]:
    """Terminal/fill/loss surfaces required to attempt UNREACHABLE_WITHIN_CAPS."""
    missing: list[str] = []
    fills = row.get("fills") or []
    if not fills:
        missing.append("fills")
    if row.get("fill_loss_per_round_trip") is None:
        missing.append("fill_loss_per_round_trip")
    term = row.get("terminal_completeness")
    if not isinstance(term, dict) or term.get("complete") is not True:
        missing.append("terminal_completeness.complete")
    if row.get("terminal_broker_state") is None:
        missing.append("terminal_broker_state")
    if row.get("terminal_loss_accounting_inputs") is None:
        missing.append("terminal_loss_accounting_inputs")
    # Cap-distance baseline required by assess() for UNREACHABLE vs INDETERMINATE
    if row.get("day_change") is None:
        missing.append("day_change")
    symbols = row.get("symbols") or []
    if not symbols:
        missing.append("symbols")
    return (len(missing) == 0, missing)


def _plan_fill_reconcile(row: dict) -> tuple[bool, str]:
    pid = str(row.get("plan_id"))
    try:
        order_id = parse_ord_plan_id(pid)
    except ValueError as exc:
        return False, str(exc)
    fills = row.get("fills") or []
    if not fills:
        return False, "no fills"
    for f in fills:
        if int(f.get("order_id")) != order_id:
            return False, f"fill order_id {f.get('order_id')} != {order_id}"
    return True, "ok"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()

    data = subprocess.check_output(["git", "cat-file", "blob", f"HEAD:{O4B_REL}"])
    O4B_PATH.write_bytes(data)

    archive = open_qualified_archive(O4B_PATH, expected_sha256=O4B_SHA)
    observations = list(archive.get("observations") or [])

    structural = {
        "archive_sha256_match": sha256_file(O4B_PATH) == O4B_SHA,
        "archive_size_match": O4B_PATH.stat().st_size == O4B_SIZE,
        "schema_id_match": archive.get("schema_id") == EXPECTED_SCHEMA,
        "archive_kind_match": archive.get("archive_kind") == EXPECTED_KIND,
        "archive_id_match": archive.get("archive_id") == EXPECTED_ARCHIVE_ID,
        "n_observations_286": len(observations) == EXPECTED_N,
        "counts_n_fills_286": int((archive.get("counts") or {}).get("n_fills", -1))
        == EXPECTED_N,
    }

    plan_ids: list[str] = []
    parse_failures: list[str] = []
    mix_hits: list[str] = []
    reconcile_failures: list[str] = []
    incomplete: list[dict] = []
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

        for k in FORBIDDEN_O4A_ONLY_KEYS:
            if k in row and row.get(k) is not None:
                mix_hits.append(f"{pid}:{k}")

        ok_rec, rec_detail = _plan_fill_reconcile(row)
        if not ok_rec:
            reconcile_failures.append(f"{pid}: {rec_detail}")

        complete, missing = _forensic_surfaces_complete(row)
        if not complete:
            incomplete.append({"plan_id": pid, "missing": missing})

        try:
            ev = o4b_row_to_forensic(row)
            rr = run_o4b(ev, CAPS)
            entry = {
                "plan_id": pid,
                "forensic_surfaces_complete": complete,
                "missing_surfaces": missing,
                "reconcile_ok": ok_rec,
                "gate_verdict": str(rr.gate_verdict),
                "expected_verdict": rr.expected_verdict,
                "adjudicated_verdict": (
                    rr.adjudicated.verdict if rr.adjudicated else None
                ),
                "adjudicated_reason": (
                    rr.adjudicated.reason_code if rr.adjudicated else None
                ),
                "refuse_reason": str(rr.refuse_reason) if rr.refuse_reason else None,
                "detail": rr.detail,
                "fill_loss_per_round_trip": row.get("fill_loss_per_round_trip"),
                "n_fills": len(row.get("fills") or []),
            }
            if rr.gate_verdict == O4GateVerdict.PASS:
                protocol_pass.append(pid)
            elif complete:
                protocol_fail.append(entry)
            row_results.append(entry)
        except Exception as exc:  # noqa: BLE001
            entry = {
                "plan_id": pid,
                "forensic_surfaces_complete": complete,
                "missing_surfaces": missing,
                "gate_verdict": "ERROR",
                "detail": repr(exc),
            }
            row_results.append(entry)
            if complete:
                protocol_fail.append(entry)

    plan_set = set(plan_ids)
    incomplete_excluded = EXPECTED_O4B_INCOMPLETE.isdisjoint(plan_set)
    incomplete_present = sorted(EXPECTED_O4B_INCOMPLETE & plan_set)
    all_ord = len(parse_failures) == 0 and len(plan_ids) == EXPECTED_N

    # Distinct from O4-A archive; no substitution of O4-A bytes
    o4a_distinct = True
    if O4A_PATH.is_file():
        o4a_distinct = sha256_file(O4A_PATH) == O4A_SHA and O4A_SHA != O4B_SHA

    structural.update(
        {
            "all_286_ord_mappings": all_ord,
            "o4b_incomplete_six_excluded": incomplete_excluded,
            "plan_fill_reconcile_1to1": len(reconcile_failures) == 0,
            "no_o4a_decision_time_payload_mix": len(mix_hits) == 0,
            "o4a_archive_not_substituted": o4a_distinct,
            "terminal_fill_completeness_flags": all(
                (o.get("terminal_completeness") or {}).get("complete") is True
                for o in observations
            ),
        }
    )

    # Cap inputs recorded (frozen hermetic caps; july24 digest not mutated)
    cap_inputs = {
        "loss_target": str(CAPS.loss_target),
        "max_round_trips": CAPS.max_round_trips,
        "max_setup_notional": str(CAPS.max_setup_notional),
        "max_position_qty": str(CAPS.max_position_qty),
        "source": "hermetic WP7 / phase0_o4_replay test caps (isolated harness)",
        "july24_digest_mutated": False,
    }

    n_missing_day = sum(
        1 for e in incomplete if "day_change" in e.get("missing", [])
    )
    n_missing_other = sum(
        1
        for e in incomplete
        if set(e.get("missing", [])) - {"day_change"}
    )

    required_checks = {
        "verdict_UNREACHABLE_WITHIN_CAPS": (
            "PASS"
            if protocol_pass and not protocol_fail and not incomplete
            else (
                "INCONCLUSIVE - forensic_bundle_incomplete"
                if incomplete and not protocol_fail
                else "FAIL"
            )
        ),
        "uses_complete_terminal_fills": (
            "PASS"
            if structural["terminal_fill_completeness_flags"]
            and structural["plan_fill_reconcile_1to1"]
            and all((o.get("fills") or []) for o in observations)
            else "FAIL"
        ),
        "no_mix_with_O4A_only_evidence": (
            "PASS"
            if structural["no_o4a_decision_time_payload_mix"]
            and structural["o4a_archive_not_substituted"]
            else "FAIL"
        ),
        "both_O4A_and_O4B_required_for_gate_O4": (
            "INCONCLUSIVE - O4-A disposition is INCONCLUSIVE; combined Gate O4 "
            "cannot PASS under START-002 until both halves APPROVE"
        ),
    }

    if (
        not all(
            structural[k]
            for k in structural
            if k != "o4a_archive_not_substituted"
        )
        or required_checks["uses_complete_terminal_fills"] == "FAIL"
        or required_checks["no_mix_with_O4A_only_evidence"] == "FAIL"
    ):
        disposition = "REJECT"
        reason = "structural, reconcile, terminal-fill, or no-mix required check FAIL"
    elif incomplete and not protocol_fail:
        disposition = "INCONCLUSIVE"
        reason = (
            "forensic_bundle_incomplete - "
            f"{len(incomplete)}/{len(observations)} observations missing surfaces "
            f"required for UNREACHABLE_WITHIN_CAPS (day_change missing on "
            f"{n_missing_day}; other missing groups={n_missing_other}). "
            "run_o4b yields INDETERMINATE/INSUFFICIENT_EXECUTION_COST without "
            "day_change baseline. Reconstruction from O4-A/external records forbidden."
        )
    elif protocol_fail:
        disposition = "REJECT"
        reason = (
            f"{len(protocol_fail)} complete forensic rows failed expected "
            "UNREACHABLE_WITHIN_CAPS"
        )
    elif protocol_pass and len(protocol_pass) == len(observations):
        disposition = "APPROVE"
        reason = "all observations PASS O4-B expected UNREACHABLE_WITHIN_CAPS"
    else:
        disposition = "INCONCLUSIVE"
        reason = "unable to classify under frozen criteria"

    completed = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (OUT / "forensic_bundle_hash.txt").write_text(O4B_SHA + "\n", encoding="utf-8")

    report = {
        "package": "O4-B",
        "campaign": "ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.2",
        "start_ruling": "ADR0043-PH0-D-BOX-START-002",
        "freeze_body_sha256": FREEZE_BODY,
        "archive_id": archive.get("archive_id"),
        "archive_sha256": O4B_SHA,
        "archive_size_bytes": O4B_SIZE,
        "archive_path": O4B_REL,
        "schema_id": archive.get("schema_id"),
        "archive_kind": archive.get("archive_kind"),
        "started_at_utc": started,
        "completed_at_utc": completed,
        "git_commit": head,
        "evaluator_version": "phase0_o4_replay.run_o4b@d1c2fbf+adapter",
        "protocol_ids": ["phase0_o4_replay.O4B", "O4-B-v1"],
        "caps": cap_inputs,
        "structural_checks": structural,
        "required_checks": required_checks,
        "counts": {
            "n_observations": len(observations),
            "n_ord_parse_ok": len(observations) - len(parse_failures),
            "n_forensic_complete": len(observations) - len(incomplete),
            "n_incomplete": len(incomplete),
            "n_missing_day_change": n_missing_day,
            "n_protocol_pass": len(protocol_pass),
            "n_protocol_fail_on_complete": len(protocol_fail),
            "n_reconcile_failures": len(reconcile_failures),
            "n_mix_hits": len(mix_hits),
        },
        "o4b_incomplete_expected_excluded": sorted(EXPECTED_O4B_INCOMPLETE),
        "o4b_incomplete_present_in_archive": incomplete_present,
        "parse_failures": parse_failures,
        "reconcile_failures": reconcile_failures,
        "mix_hits": mix_hits,
        "incomplete_sample": incomplete[:15],
        "protocol_fail_sample": protocol_fail[:10],
        "row_results_sha256": hashlib.sha256(
            json.dumps(row_results, sort_keys=True).encode()
        ).hexdigest(),
        "artifacts": {
            "o4b_report.json": "this file",
            "forensic_bundle_hash.txt": O4B_SHA,
            "o4b_row_results.json": "sibling",
        },
        "disposition": disposition,
        "disposition_reason": reason,
        "d_wire_effect": "NONE - O5 deferred; D-WIRE remains BLOCKED",
        "prior_dispositions": {
            "O3": "INCONCLUSIVE",
            "O4-A": "INCONCLUSIVE",
        },
        "inherited_packages_not_rerun": ["CORR-06", "O1", "O2"],
    }

    (OUT / "o4b_row_results.json").write_text(
        json.dumps(row_results, indent=2) + "\n", encoding="utf-8"
    )
    report_path = OUT / "o4b_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

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
    (OUT / "o4b_pytest.txt").write_text(
        proc.stdout + "\n" + proc.stderr, encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "disposition": disposition,
                "reason": reason,
                "n": len(observations),
                "n_incomplete": len(incomplete),
                "n_protocol_pass": len(protocol_pass),
                "structural_all_pass": all(structural.values()),
                "report_sha256": hashlib.sha256(
                    report_path.read_bytes()
                ).hexdigest(),
                "pytest_exit": proc.returncode,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
