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
from datetime import date, timedelta
from pathlib import Path

from app.validation.governed_corpus import (
    CorpusManifest,
    Dgs3moManifest,
    load_corpus_manifest,
    load_dgs3mo_manifest,
)

#: Where the preregistration's frozen artifacts live in the repository.
GOVERNED_ARTIFACTS = (Path(__file__).resolve().parents[4]
                      / "docs" / "review" / "momentum_daily" / "equal_weight_validation")

UNIVERSE_SHA = "a" * 64
BASE_CORPUS_SHA = "d" * 64
ACTIONS_MANIFEST_SHA = "e" * 64

#: The embedded TICKERS construction. `coverage_cutoff` is filled per-session by the installer, since
#: a security master that stops before the session cannot say which securities were tradeable during it.
TICKERS_BLOCK = {
    "schema_version": "TICKERS_V2_PERMATICKER",
    "columns": ["permaticker", "ticker", "name", "firstpricedate", "lastpricedate"],
    "rows": 2,
    "permanent_ids": 2,
    "row_identity_sha256": "b" * 64,
    "artifact_sha256": "c" * 64,
    "source_identity": "SHARADAR/TICKERS (table=SEP)",
    "countersignature": "TickersManifest_v1.0",
}


def install_governed_construction(tmp_path: Path, session: date) -> dict:
    """Write the frozen artifacts and both manifests. Returns the deployment manifest `corpus` block."""
    from app.validation.forward_window import DGS3MO_OBSERVATION_CUTOFF

    dgs3mo = tmp_path / "DGS3MO.csv"
    dgs3mo.write_bytes((GOVERNED_ARTIFACTS / "data" / "DGS3MO.csv").read_bytes())
    ledger = tmp_path / "TrialLedger.json"
    ledger.write_bytes((GOVERNED_ARTIFACTS / "TrialLedger_v1.0.json").read_bytes())

    from app.validation.security_lineage import SECURITY_IDENTITY_CONTRACT

    corpus_path = tmp_path / "corpus_manifest.json"
    corpus_path.write_text(json.dumps({
        "base_corpus_sha256": BASE_CORPUS_SHA,
        "base_coverage_through": session.isoformat(),
        "governed_universe_sha256": UNIVERSE_SHA,
        "governed_universe_size": 14_150,
        "actions_manifest_sha256": ACTIONS_MANIFEST_SHA,
        "actions_authoritative": True,
        # ADR 0048 as amended 2026-07-29: TICKERS is part of the bound construction, and the rule by
        # which its rows resolve to securities is bound with it.
        # TICKERS coverage naturally runs to "now", i.e. at or past the session. Held clear of the
        # session here so it never becomes the binding constraint in tests that are about something
        # else; the cutoff rule has its own dedicated cases in `test_governed_corpus`.
        "tickers": TICKERS_BLOCK | {
            "coverage_cutoff": (session + timedelta(days=30)).isoformat()},
        "tickers_authoritative": True,
        "security_identity_contract": SECURITY_IDENTITY_CONTRACT,
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
    return _base_block(corpus, dgs)


#: The in-repo Layer 2 construction artifacts. Installed REAL, for the same reason the frozen DGS3MO
#: snapshot is: a fixture that hand-rolls a plausible manifest proves the loader parses fixtures, not
#: that it accepts the construction actually deployed. Using the committed files means these tests also
#: re-prove that `corpus_manifest_v2.json` and its countersignature sidecar still hash to the values
#: every downstream binding names.
LAYER2_ARTIFACTS = Path(__file__).resolve().parents[4] / "manifests" / "layer2"

#: The session the committed Layer 2 reconstruction was built for. It is a property of that artifact,
#: not a choice the tests get to make.
LAYER2_SESSION = date(2026, 7, 27)

#: The pinned evidence artifacts the narrow-readiness wiring READS (as opposed to merely names): the
#: countersigned quarantine and the decision-relevance assessment the M&A disclosure derives from.
#: Committed alongside the manifest that pins them, so a run of these tests also re-proves that both
#: still hash to the values the countersignature transitively binds.
LAYER2_EVIDENCE_ARTIFACTS = ("shop_tln_quarantine.json", "residual_relevance.json")


def install_layer2_construction(tmp_path: Path, *, session: date = LAYER2_SESSION,
                                sidecar: bool = True) -> dict:
    """Install the real Layer 2 reconstruction and its countersignature sidecar.

    Returns the deployment manifest `corpus` block, built by the SAME producer the session path
    recomputes it with — so a test that composes successfully has also proved the generator and the
    session path agree on the block. Pass ``sidecar=False`` to install the construction WITHOUT its
    approval, which is the refusal case.

    ⚠ `session` sizes the DGS3MO extension ONLY. The corpus manifest is the real committed artifact
    and its coverage is a property of that artifact, not of the caller — which is exactly what lets a
    test compose a DIFFERENT covered session against the same corpus without the risk-free series
    becoming the binding constraint by accident.
    """
    from app.validation.forward_window import DGS3MO_OBSERVATION_CUTOFF, DGS3MO_SNAPSHOT_SHA256
    from app.validation.governed_corpus import (
        deployment_corpus_block,
        load_any_corpus_manifest,
        load_layer2_countersignature,
        normalize_corpus_manifest,
    )

    (tmp_path / "DGS3MO.csv").write_bytes((GOVERNED_ARTIFACTS / "data" / "DGS3MO.csv").read_bytes())
    (tmp_path / "TrialLedger.json").write_bytes(
        (GOVERNED_ARTIFACTS / "TrialLedger_v1.0.json").read_bytes())

    corpus_path = tmp_path / "corpus_manifest.json"
    corpus_path.write_bytes((LAYER2_ARTIFACTS / "corpus_manifest_v2.json").read_bytes())
    if sidecar:
        (tmp_path / "countersignature.json").write_bytes(
            (LAYER2_ARTIFACTS / "corpus_countersignature_v1.json").read_bytes())
    # The pinned evidence artifacts, installed under the names the manifest declares for them —
    # which is how the runtime locates them, and therefore how a test must. Real, for the same
    # reason the manifest itself is: a synthetic stand-in would prove the reader parses fixtures.
    for name in LAYER2_EVIDENCE_ARTIFACTS:
        (tmp_path / name).write_bytes((LAYER2_ARTIFACTS / name).read_bytes())

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

    corpus = load_any_corpus_manifest(corpus_path)
    dgs = load_dgs3mo_manifest(dgs3mo_manifest_path)
    countersignature = (load_layer2_countersignature(tmp_path / "countersignature.json")
                        if sidecar else None)
    return deployment_corpus_block(
        normalize_corpus_manifest(corpus),
        dgs3mo_manifest_sha256=dgs.dgs3mo_manifest_sha256,
        countersignature=countersignature) if sidecar else {}


def layer2_quarantine_policy():
    """The REAL governed quarantine, derived from the committed artifacts by the ONE derivation.

    ⚠ Tests use this rather than constructing a `GovernedQuarantinePolicy` by hand, and the difference
    is the whole point of the 2026-07-31 ruling: a hand-built policy in a test is the same defect as
    the hand-built `QUARANTINED_IDENTITIES` in the runner, and a parity test written against two
    hand-built policies would agree with itself.
    """
    from app.validation.governed_corpus import (
        load_any_corpus_manifest,
        load_layer2_countersignature,
        normalize_corpus_manifest,
    )
    from app.validation.governed_quarantine import governed_quarantine_policy

    corpus = load_any_corpus_manifest(LAYER2_ARTIFACTS / "corpus_manifest_v2.json")
    sidecar = load_layer2_countersignature(LAYER2_ARTIFACTS / "corpus_countersignature_v1.json")
    return governed_quarantine_policy(normalize_corpus_manifest(corpus), sidecar,
                                      governed_root=LAYER2_ARTIFACTS)


def governed_movement_examples(policy=None) -> list[dict]:
    """The measured `unexplained_examples` shape for exactly the movements the policy governs.

    Shaped like the verifier's own payload — ticker, permanent identity, session and factor — because
    clause (6) now checks all four, and a double that omitted any of them could not exercise it.
    """
    p = policy or layer2_quarantine_policy()
    return [{"ticker": m.ticker, "permaticker": m.permanent_identity,
             "session_date": m.session_date.isoformat(), "factor": str(m.factor)}
            for m in p.movements]


def _base_block(corpus: CorpusManifest, dgs: Dgs3moManifest) -> dict:
    return {
        "base_corpus_sha256": corpus.base_corpus_sha256,
        "base_coverage_through": corpus.base_coverage_through.isoformat(),
        "ordered_delta_manifest_sha256s": list(corpus.ordered_delta_manifest_sha256s),
        "governed_universe_sha256": corpus.governed_universe_sha256,
        "actions_manifest_sha256": corpus.actions_manifest_sha256,
        "tickers_manifest_sha256": corpus.tickers_manifest_sha256,
        "security_identity_contract": corpus.security_identity_contract,
        "corpus_manifest_sha256": corpus.corpus_manifest_sha256,
        "dgs3mo_manifest_sha256": dgs.dgs3mo_manifest_sha256,
    }
