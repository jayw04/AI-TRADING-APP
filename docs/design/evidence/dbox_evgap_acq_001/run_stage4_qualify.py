#!/usr/bin/env python3
"""EVGAP Stage 4 — independent qualification of Stage 3 refusal package.

Separate operator role from constructor: verifies hashes/counts/no fabrication.
Does not execute gates or authorize D-WIRE.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

EXPECTED_STAGE2_REPORT_SHA = (
    "aac5b599f16324d12a91ca792dc406063d68c7628d1eec9a27b47fde66e3fb0c"
)
FREEZE_BODY = "af7693f4b97fd7d9d4ad642ab1af47e9e9a2a8cd680f6a26c4d01fee8d57967e"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage2-report", type=Path, required=True)
    ap.add_argument("--stage3-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--qualifier-commit", required=True)
    args = ap.parse_args()

    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "pass": ok, "detail": detail})
        if not ok:
            print(f"FAIL {name}: {detail}")

    stage2_sha = sha256_file(args.stage2_report)
    check(
        "stage2_report_hash",
        stage2_sha == EXPECTED_STAGE2_REPORT_SHA,
        f"got={stage2_sha}",
    )
    stage2 = json.loads(args.stage2_report.read_text(encoding="utf-8"))
    counts = stage2["count_reconciliation"]

    pkg_path = args.stage3_dir / "stage3_refusal_package.json"
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    check("freeze_body_bound", pkg.get("freeze_body_sha256") == FREEZE_BODY, str(pkg.get("freeze_body_sha256")))
    check("stage2_sha_bound", pkg.get("stage2_report_sha256") == stage2_sha, str(pkg.get("stage2_report_sha256")))
    check("no_substantive_construction", pkg.get("substantive_candidate_construction") is False, "")
    check("not_gate_basis", pkg.get("gate_campaign_basis") is False, "")
    check("rows_emitted_zero", pkg.get("rows_emitted") == 0, str(pkg.get("rows_emitted")))
    check("no_reconstruction", pkg.get("missing_surfaces_reconstructed") is False, "")
    check("no_day_change_copy", pkg.get("accounts_state_day_change_copied_into_episodes") is False, "")
    check("no_fabrication", pkg.get("fabrication_performed") is False, "")
    check("no_mapping_relax", pkg.get("mapping_relaxation") is False, "")
    check("no_o4_mix", pkg.get("o4a_o4b_mix") is False, "")

    # Count binding
    sc = pkg.get("stage2_count_reconciliation", {})
    check("counts_source_292", sc.get("n_source_count") == 292 == counts["n_source_count"], str(sc))
    check("counts_complete_zero", sc.get("n_complete_o3") == 0 and sc.get("n_complete_o4a") == 0 and sc.get("n_complete_o4b") == 0, str(sc))
    check(
        "reason_codes_match_stage2",
        pkg.get("stage2_reason_code_counts") == counts["reason_code_counts"],
        "mismatch",
    )

    outcomes = pkg.get("outcomes", {})
    check("o3_outcome", outcomes.get("O3") == "REJECTED_AS_NON_BINDABLE", str(outcomes.get("O3")))
    check("o4a_outcome", outcomes.get("O4_A") == "REJECTED_AS_NON_BINDABLE", str(outcomes.get("O4_A")))
    check("o4b_outcome", outcomes.get("O4_B") == "REJECTED_AS_NON_BINDABLE", str(outcomes.get("O4_B")))
    check("o5_outcome", outcomes.get("O5") == "INCONCLUSIVE", str(outcomes.get("O5")))

    # Per-artifact verification
    for fname, expected_outcome, package in [
        ("O3_CONSTRUCTION_REFUSAL.json", "REJECTED_AS_NON_BINDABLE", "O3"),
        ("O4A_CONSTRUCTION_REFUSAL.json", "REJECTED_AS_NON_BINDABLE", "O4_A"),
        ("O4B_CONSTRUCTION_REFUSAL.json", "REJECTED_AS_NON_BINDABLE", "O4_B"),
        ("O5_LOCATE_MANIFEST.json", "INCONCLUSIVE", "O5"),
    ]:
        path = args.stage3_dir / fname
        blob = path.read_bytes()
        got = hashlib.sha256(blob).hexdigest()
        expected = pkg["artifact_sha256"][fname]
        check(f"hash_{fname}", got == expected, f"got={got} expected={expected}")
        obj = json.loads(blob.decode("utf-8"))
        check(f"kind_{fname}", obj.get("not_a_candidate_archive") is True, str(obj.get("artifact_kind")))
        check(f"outcome_{fname}", obj.get("outcome") == expected_outcome, str(obj.get("outcome")))
        check(f"emitted_{fname}", obj.get("rows_emitted") == 0, str(obj.get("rows_emitted")))
        if package == "O5":
            anchors = obj.get("o5_live_fill_anchors", {}).get("anchors")
            check("o5_anchors_empty", anchors == [], str(anchors))
        else:
            check(
                f"no_candidate_path_{fname}",
                obj.get("candidate_archive_path") is None,
                str(obj.get("candidate_archive_path")),
            )
            # Ensure no misleading candidate labels in file content
            text = blob.decode("utf-8")
            check(
                f"no_qualified_candidate_label_{fname}",
                "QUALIFIED_CANDIDATE" not in text or "archive_status_labels_forbidden" in text,
                "label scan",
            )

    all_pass = all(c["pass"] for c in checks)
    report = {
        "document_id": "ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-STAGE4-001",
        "stage": 4,
        "role": "INDEPENDENT_QUALIFIER",
        "constructor_may_not_self_qualify": True,
        "qualified_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "qualifier_commit": args.qualifier_commit,
        "freeze_body_sha256": FREEZE_BODY,
        "stage2_report_sha256": stage2_sha,
        "stage3_package_sha256": sha256_file(pkg_path),
        "checks": checks,
        "all_checks_pass": all_pass,
        "qualification_outcomes": {
            "O3": "REJECTED_AS_NON_BINDABLE",
            "O4_A": "REJECTED_AS_NON_BINDABLE",
            "O4_B": "REJECTED_AS_NON_BINDABLE",
            "O5": "INCONCLUSIVE",
        },
        "acq_start_001_complete": all_pass,
        "gate_campaign_basis": False,
        "new_gate_freeze_authorized": False,
        "new_gate_start_authorized": False,
        "d_wire": "BLOCKED",
        "gates": "CLOSED",
        "disposition_note": (
            "ACQ-START-001 completed honestly via Stage 3 refusal + Stage 4 "
            "qualification. No basis for a new gate campaign."
            if all_pass
            else "Qualification FAILED — do not close ACQ-START-001"
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    args.out.write_bytes(data)
    print("all_checks_pass", all_pass)
    print("stage4_report_sha256", hashlib.sha256(data).hexdigest())
    print("WROTE", args.out.as_posix())
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
