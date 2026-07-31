#!/usr/bin/env python3
"""EVGAP Stage 3 — no-bindable-corpus construction refusal (deterministic).

Does NOT emit CANDIDATE / QUALIFIED archives. Does NOT reconstruct missing surfaces.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

FREEZE_BODY = "af7693f4b97fd7d9d4ad642ab1af47e9e9a2a8cd680f6a26c4d01fee8d57967e"
CAPTURE_ID = "20260731T002055Z"
STAGE1_MERGE = "561e52409eda6c552029da20113caa211aba2256"
STAGE2_MERGE = "3f256bb2affae631c22eed72a0f54b2e10aabadd"
SQLITE_SHA = "9e40a9ad2f0176acf884140594ddfa9e946e42d2723794f464bbb0efdc2d9db6"
BAR_SHA = "b32e118732669c2880291cd0a7226589e4b0e2ef20839dc8172c26ce51e0adc7"
MP_SHA = "c0148389daa4139dd60a5921d6bec55a224a4156fb7cca080cc2b8fdfb7eb2c1"
O5_TREE_SHA = "1c209b068e89456dbdbb8f380fc8672d0b3d04d1460752e12d32dd8717832d26"
EXPECTED_STAGE2_REPORT_SHA = (
    "aac5b599f16324d12a91ca792dc406063d68c7628d1eec9a27b47fde66e3fb0c"
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, obj: object) -> str:
    data = (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage2-report", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--tooling-commit", required=True)
    args = ap.parse_args()

    if len(args.tooling_commit) != 40:
        raise SystemExit("tooling-commit must be 40 hex")

    stage2_sha = sha256_file(args.stage2_report)
    if stage2_sha != EXPECTED_STAGE2_REPORT_SHA:
        raise SystemExit(
            f"stage2 report sha mismatch expected={EXPECTED_STAGE2_REPORT_SHA} "
            f"got={stage2_sha}"
        )
    stage2 = json.loads(args.stage2_report.read_text(encoding="utf-8"))
    counts = stage2["count_reconciliation"]
    if counts["n_complete_o3"] != 0 or counts["n_complete_o4a"] != 0 or counts["n_complete_o4b"] != 0:
        raise SystemExit("refusing Stage 3: Stage 2 reports nonzero complete episodes")

    out: Path = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    constructed_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    common_bindings = {
        "freeze_body_sha256": FREEZE_BODY,
        "capture_id": CAPTURE_ID,
        "stage1_opening_merge": STAGE1_MERGE,
        "stage2_merge": STAGE2_MERGE,
        "stage2_report_sha256": stage2_sha,
        "source_pins": {
            "sqlite_snapshot_sha256": SQLITE_SHA,
            "bar_cache_manifest_sha256": BAR_SHA,
            "market_projection_manifest_sha256": MP_SHA,
            "o5_evidence_tree_manifest_sha256": O5_TREE_SHA,
        },
        "stage2_reason_code_counts": counts["reason_code_counts"],
        "stage2_count_reconciliation": {
            "n_source_count": counts["n_source_count"],
            "n_window_eligible": counts["n_window_eligible"],
            "n_deduplicated": counts["n_deduplicated"],
            "n_complete_o3": counts["n_complete_o3"],
            "n_complete_o4a": counts["n_complete_o4a"],
            "n_complete_o4b": counts["n_complete_o4b"],
        },
        "rows_emitted": 0,
        "missing_surfaces_reconstructed": False,
        "accounts_state_day_change_copied_into_episodes": False,
        "fabrication_performed": False,
        "mapping_relaxation": False,
        "o4a_o4b_mix": False,
        "gate_evidence": False,
        "tooling_commit": args.tooling_commit,
        "constructed_at_utc": constructed_at,
    }

    o3 = {
        "artifact_kind": "CONSTRUCTION_REFUSAL_CENSUS",
        "not_a_candidate_archive": True,
        "archive_status_labels_forbidden": [
            "CANDIDATE",
            "QUALIFIED_CANDIDATE",
            "O3_HISTORICAL_REPLAY",
        ],
        "package": "O3",
        "outcome": "REJECTED_AS_NON_BINDABLE",
        "reason": (
            "All 292 eligible episodes lack required O3 replay surfaces "
            "(quote_provenance, checkpoint_tuple, loss_accounting_inputs, "
            "recovery_inputs) under frozen mappings; no bindable row to emit"
        ),
        "n_eligible_episodes": 292,
        "n_bindable_episodes": 0,
        "candidate_archive_path": None,
        **common_bindings,
    }
    o4a = {
        "artifact_kind": "CONSTRUCTION_REFUSAL_CENSUS",
        "not_a_candidate_archive": True,
        "archive_status_labels_forbidden": [
            "CANDIDATE",
            "QUALIFIED_CANDIDATE",
            "O4A_DECISION_TIME",
        ],
        "package": "O4_A",
        "outcome": "REJECTED_AS_NON_BINDABLE",
        "reason": (
            "All 292 eligible episodes lack decision-time quote provenance and/or "
            "explicit model_available (MISSING_DECISION_TIME_QUOTE / "
            "MISSING_PROVENANCE); 5 also MISSING_CUTOFF; no bindable row to emit"
        ),
        "n_eligible_episodes": 292,
        "n_bindable_episodes": 0,
        "candidate_archive_path": None,
        **common_bindings,
    }
    o4b = {
        "artifact_kind": "CONSTRUCTION_REFUSAL_CENSUS",
        "not_a_candidate_archive": True,
        "archive_status_labels_forbidden": [
            "CANDIDATE",
            "QUALIFIED_CANDIDATE",
            "O4B_FORENSIC",
        ],
        "package": "O4_B",
        "outcome": "REJECTED_AS_NON_BINDABLE",
        "reason": (
            "No episode has a provenance-bound forensic baseline: "
            "MISSING_FORENSIC_BASELINE on all 292; snapshot-wide "
            "accounts_state.day_change must not be copied into episodes; "
            "6 also O4B_INCOMPLETE; no bindable row to emit"
        ),
        "n_eligible_episodes": 292,
        "n_bindable_episodes": 0,
        "candidate_archive_path": None,
        "day_change_policy": (
            "accounts_state.day_change=1032.27 (BROKER_LAST_EQUITY) is "
            "snapshot-as-of only; copying into 292 episodes is prohibited "
            "reconstruction"
        ),
        **common_bindings,
    }
    o5 = {
        "artifact_kind": "O5_LOCATE_MANIFEST",
        "not_a_candidate_archive": True,
        "not_gate_evidence": True,
        "package": "O5",
        "outcome": "INCONCLUSIVE",
        "o5_live_fill_anchors": {
            "policy": "PRE_EXISTING_SEALED_TIER_A_ONLY",
            "anchors": [],
            "predetermined_disposition": "INCONCLUSIVE",
            "disposition_note": (
                "Stage 2 locate-only found zero nonempty Tier-A manifests in "
                "the Stage 1 pinned evidence tree; anchors:[] is valid"
            ),
        },
        "n_qualifying_nonempty_tier_a_manifests": 0,
        **common_bindings,
    }

    package = {
        "document_id": "ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-STAGE3-001",
        "stage": 3,
        "mode": "NO_BINDABLE_CORPUS_CONSTRUCTION_REFUSAL",
        "substantive_candidate_construction": False,
        "gate_campaign_basis": False,
        "outcomes": {
            "O3": "REJECTED_AS_NON_BINDABLE",
            "O4_A": "REJECTED_AS_NON_BINDABLE",
            "O4_B": "REJECTED_AS_NON_BINDABLE",
            "O5": "INCONCLUSIVE",
        },
        "statement": (
            "No row was emitted and no missing surface was reconstructed. "
            "Ordinary candidate archives were not created because they cannot "
            "cure missing evidence and must not be presented as progress toward "
            "gate eligibility."
        ),
        **common_bindings,
        "artifacts": {
            "O3_REFUSAL": "O3_CONSTRUCTION_REFUSAL.json",
            "O4A_REFUSAL": "O4A_CONSTRUCTION_REFUSAL.json",
            "O4B_REFUSAL": "O4B_CONSTRUCTION_REFUSAL.json",
            "O5_MANIFEST": "O5_LOCATE_MANIFEST.json",
        },
    }

    hashes = {
        "O3_CONSTRUCTION_REFUSAL.json": write_json(out / "O3_CONSTRUCTION_REFUSAL.json", o3),
        "O4A_CONSTRUCTION_REFUSAL.json": write_json(out / "O4A_CONSTRUCTION_REFUSAL.json", o4a),
        "O4B_CONSTRUCTION_REFUSAL.json": write_json(out / "O4B_CONSTRUCTION_REFUSAL.json", o4b),
        "O5_LOCATE_MANIFEST.json": write_json(out / "O5_LOCATE_MANIFEST.json", o5),
    }
    package["artifact_sha256"] = hashes
    pkg_sha = write_json(out / "stage3_refusal_package.json", package)
    print("stage3_refusal_package_sha256", pkg_sha)
    for k, v in hashes.items():
        print(k, v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
