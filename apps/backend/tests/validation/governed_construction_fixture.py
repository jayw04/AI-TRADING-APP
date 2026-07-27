"""Install a governed construction into a temporary deployment (ADR 0048).

Tests that drive the composition root need the four governed inputs to be real, because
`resolve_governed_construction` verifies the frozen artifacts against the countersigned pins in
`forward_window` and refuses anything else. So this installs the ACTUAL committed DGS3MO snapshot and
trial ledger — the ones the preregistration froze — rather than stand-ins.

That has a second effect worth keeping: every run of these tests re-proves that the in-repo artifacts
still hash to their pinned values. If someone normalizes a line ending in `DGS3MO.csv`, this fails
here rather than on the deployed host the morning of an observation.

The shape installed is the one observation #1 actually has: base coverage through the forward start,
no corpus deltas yet, and a single DGS3MO extension carrying the risk-free series from its 2026-07-21
cutoff up to the session.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.validation.governed_corpus import (
    load_corpus_manifest,
    load_dgs3mo_manifest,
)

#: Where the preregistration's frozen artifacts live in the repository.
GOVERNED_ARTIFACTS = (Path(__file__).resolve().parents[4]
                      / "docs" / "review" / "momentum_daily" / "equal_weight_validation")

UNIVERSE_SHA = "a" * 64
BASE_CORPUS_SHA = "d" * 64
ACTIONS_MANIFEST_SHA = "e" * 64


def install_governed_construction(tmp_path: Path, session: date) -> dict:
    """Write the frozen artifacts and both manifests. Returns the deployment manifest `corpus` block."""
    from app.validation.forward_window import DGS3MO_OBSERVATION_CUTOFF

    dgs3mo = tmp_path / "DGS3MO.csv"
    dgs3mo.write_bytes((GOVERNED_ARTIFACTS / "data" / "DGS3MO.csv").read_bytes())
    ledger = tmp_path / "TrialLedger.json"
    ledger.write_bytes((GOVERNED_ARTIFACTS / "TrialLedger_v1.0.json").read_bytes())

    corpus_path = tmp_path / "corpus_manifest.json"
    corpus_path.write_text(json.dumps({
        "base_corpus_sha256": BASE_CORPUS_SHA,
        "base_coverage_through": session.isoformat(),
        "governed_universe_sha256": UNIVERSE_SHA,
        "governed_universe_size": 14_150,
        "actions_manifest_sha256": ACTIONS_MANIFEST_SHA,
        "actions_authoritative": True,
        "base_countersignature": "GoverningCorpus_Countersignature_v2.0",
        "deltas": [],
    }), encoding="utf-8")

    from app.validation.forward_window import DGS3MO_SNAPSHOT_SHA256

    dgs3mo_manifest_path = tmp_path / "dgs3mo_manifest.json"
    dgs3mo_manifest_path.write_text(json.dumps({
        "base_sha256": DGS3MO_SNAPSHOT_SHA256,
        "base_coverage_through": DGS3MO_OBSERVATION_CUTOFF,
        "extensions": [{
            "session_date": session.isoformat(),
            "coverage_through": session.isoformat(),
            "sha256": "1" * 64,
            "source_sha256": "2" * 64,
            "rows": 1,
            "retrieved_at": f"{session.isoformat()}T22:05:00Z",
            "countersignature": "fred-dgs3mo-ext-1",
        }],
    }), encoding="utf-8")

    corpus = load_corpus_manifest(corpus_path)
    dgs = load_dgs3mo_manifest(dgs3mo_manifest_path)
    return {
        "base_corpus_sha256": corpus.base_corpus_sha256,
        "base_coverage_through": corpus.base_coverage_through.isoformat(),
        "ordered_delta_manifest_sha256s": list(corpus.ordered_delta_manifest_sha256s),
        "governed_universe_sha256": corpus.governed_universe_sha256,
        "actions_manifest_sha256": corpus.actions_manifest_sha256,
        "corpus_manifest_sha256": corpus.corpus_manifest_sha256,
        "dgs3mo_manifest_sha256": dgs.dgs3mo_manifest_sha256,
    }
