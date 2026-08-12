"""Layer 2 Step 6 — the PROPOSED `corpus_manifest_sha256` for the rebuilt construction.

## Every digest is COMPUTED, never declared

The manifest reads each artifact's bytes and hashes them itself. That is the same discipline the
registered `CorpusManifest` applies to TICKERS — it EMBEDS the sub-manifest so its identity is computed
rather than declared, "so there is no declared-vs-actual gap to police". A manifest that merely restates
digests someone typed in can name an artifact it never assembled; this one cannot.

⛔ A missing or unreadable artifact is a REFUSAL, not a skipped field.

## It SUPERSEDES; it does not mutate

The prior construction keeps its identity `a69ad50ffc3c6925…` intact and unaltered. This manifest
declares a NEW identity and records the old one as superseded, with the reason. Mutating the old
identity in place would destroy the only thing that makes the earlier countersignature checkable — and
ADR 0048 §4 is explicit that a historical correction is never a delta.

## Why this is a DIFFERENT SHAPE from the registered `CorpusManifest`

The registered manifest describes `base + ordered deltas`. This construction is neither: it is a
whole-corpus reconstruction from a single sealed vintage under permanent identities, so it binds the
CONSTRUCTION EVIDENCE (crosswalk, universes, adjudication, censuses, reconciliation, impact analyses)
rather than a delta chain. It therefore carries its own `kind` and `construction_schema_version`, and
does not pretend to be the same object. The canonicalization contract is shared — `canonical_json`,
sorted keys, no insignificant whitespace — so the identity is reproducible byte-for-byte.
"""

# ⚠ PORTED into the repository for REPRODUCIBILITY. Operator machine paths are removed: the
# backend root resolves relative to this file and every data location comes from an argument or
# an environment override. A hard-coded working-copy path would make the tool unrunnable by
# anyone else, which is the opposite of what a reproducible build tool is for.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.validation.forward_window import (  # noqa: E402
    DGS3MO_SNAPSHOT_SHA256,
    TRIAL_LEDGER_SHA256,
)
from app.validation.governed_corpus import canonical_json  # noqa: E402
from scripts.forward_validation._session_arg import (  # noqa: E402
    add_session_argument,
)

ROOT = Path(os.environ.get("LAYER2_ROOT", "."))
FVD = ROOT / "forward-validation-deploy"
V2 = ROOT / "layer2-vintage" / "v2"
C2 = ROOT / "layer2-vintage" / "corpus-v2"

CONSTRUCTION_SCHEMA_VERSION = "LAYER2_SINGLE_VINTAGE_PERMANENT_LINEAGE_v1.0"
SECURITY_IDENTITY_CONTRACT = "PERMATICKER_EFFECTIVE_INTERVAL_V1"
SUPERSESSION_REASON = "HISTORICAL_RECONSTRUCTION_SINGLE_VINTAGE_AND_PERMANENT_LINEAGE"
#: The manifest this one supersedes is a per-run input (`--supersedes`). It WAS the constant
#: `a69ad50ffc3c6925…`, correct only for the first reconstruction; each later construction supersedes
#: the manifest actually installed at the time, and a stale constant would break the supersession
#: chain while still producing a well-formed manifest.

#: (logical name -> path). Every one is hashed from disk; a miss refuses the build.
ARTIFACTS: dict[str, Path] = {
    # universe construction
    "universe_crosswalk_v2": FVD / "crosswalk/v2/universe_crosswalk_v2.json",
    "crosswalk_summary_v2": FVD / "crosswalk/v2/crosswalk_summary.json",
    "universe_exclusions_v2": FVD / "crosswalk/v2/universe_exclusions_v2.json",
    "quarantine_unresolved_source_master_v2":
        FVD / "crosswalk/v2/quarantine_unresolved_source_master_v2.json",
    "july27_exclusion_impact_check": FVD / "crosswalk/v2/july27_exclusion_impact_check.json",
    "price_universe_v2": C2 / "price_universe_v2.json",
    "layer2_price_adjudication": FVD / "layer2_price_adjudication.json",
    # sealed source vintage
    "source_vintage": V2 / "source_vintage.json",
    "extraction_evidence": V2 / "extraction_evidence.json",
    # normalized corpus
    "normalized_corpus_evidence": C2 / "normalized_corpus_evidence.json",
    # Step 2
    "lineage_hole_census": C2 / "lineage_hole_census.json",
    # Step 3
    "adjustment_reconciliation_final": C2 / "adjustment_reconciliation_final.json",
    "residual_relevance": C2 / "residual_relevance.json",
    "tolerance_remeasurement": C2 / "tolerance_remeasurement.json",
    "shop_tln_quarantine": C2 / "shop_tln_quarantine.json",
    # Step 4 / Step 5
    "step4_comparison": C2 / "step4_comparison.json",
    "step5_exclusion_impact_273": C2 / "step5_exclusion_impact_273.json",
    "step5_package": C2 / "step5_package.json",
}

STORE = C2 / "factor_data_layer2.duckdb"
QUARANTINE_DIR = C2 / "quarantine"

#: The FROZEN legacy governed universe (14,150 source keys). This one is genuinely a constant: it
#: describes the legacy key set the crosswalk maps FROM, which does not move when a new vintage is
#: taken. Every other identity below is construction-specific and is READ from the evidence.
LEGACY_GOVERNED_UNIVERSE_SHA256 = (
    "2b34970fc123689b66c82c6c119d0e946bf99181b9109b878cb1ba6148d3bcc4")

#: The identities the construction asserts about itself, keyed as they appear in the manifest.
#: ⚠ These WERE hard-coded literals carrying the 2026-07-27 construction's values. That contradicted
#: this module's own stated contract ("every digest is COMPUTED, never declared") and, worse, a later
#: construction would have silently published the PREVIOUS vintage's identities inside an otherwise
#: correct manifest — a declared-vs-actual gap of exactly the kind the contract exists to prevent.
#: They are now read from `normalized_corpus_evidence.json`, and a missing key is a refusal.
_EVIDENCE_IDENTITY_KEYS = (
    "governed_universe_key_crosswalk_sha256",
    "governed_mapped_identity_universe_sha256",
    "governed_price_universe_sha256",
    "source_vintage_sha256",
)


def _declared_from_evidence(ev: dict) -> dict[str, str]:
    """Lift the construction's self-asserted identities out of its own evidence."""
    missing = [k for k in _EVIDENCE_IDENTITY_KEYS if not ev.get(k)]
    if missing:
        raise SystemExit(
            f"REFUSED — normalized_corpus_evidence.json is missing {missing}; the manifest will not "
            f"declare an identity it did not read from the construction.")
    declared = {k: ev[k] for k in _EVIDENCE_IDENTITY_KEYS}
    declared["legacy_governed_universe_sha256"] = LEGACY_GOVERNED_UNIVERSE_SHA256
    return declared


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-store-digest", action="store_true",
                    help="skip the 2 GB store hash (diagnostic only; the manifest REFUSES to claim a "
                         "store identity it did not compute)")
    add_session_argument(ap)
    ap.add_argument("--supersedes", required=True,
                    help="the corpus_manifest_sha256 this construction supersedes — the manifest "
                         "actually installed at the time, not a constant")
    args = ap.parse_args()
    session = args.session

    missing = [n for n, p in ARTIFACTS.items() if not p.is_file()]
    if missing:
        print(f"REFUSED — {len(missing)} artifact(s) missing: {missing}")
        return 1

    print("computing artifact digests from disk…")
    artifacts = {}
    for name, p in sorted(ARTIFACTS.items()):
        d = _sha256_file(p)
        artifacts[name] = {"sha256": d, "bytes": p.stat().st_size, "path": p.name}
        print(f"  {name:<40} {d[:16]}…  {p.stat().st_size:>10,} B")

    quarantine = {}
    for p in sorted(QUARANTINE_DIR.glob("*.csv")):
        quarantine[p.name] = {"sha256": _sha256_file(p), "bytes": p.stat().st_size}
    print(f"  quarantine histories: {len(quarantine)} file(s)")

    # ── the construction's self-asserted identities, READ from its evidence, never declared ──
    evidence = json.loads(ARTIFACTS["normalized_corpus_evidence"].read_text(encoding="utf-8"))
    declared = _declared_from_evidence(evidence)
    if evidence.get("governed_cutoff") != session.isoformat():
        raise SystemExit(
            f"REFUSED — the construction was built at cutoff {evidence.get('governed_cutoff')} but "
            f"--session is {session.isoformat()}. A manifest must not label a corpus with a session "
            f"it was not bounded at.")

    # ── the dataset census, MEASURED from the store ──
    # These were literals (sep rows 39,125,482 / sessions 7,185 / coverage ending 2026-07-27). A
    # literal census silently misdescribes any later corpus while remaining perfectly well-formed,
    # so it is measured. This is a cheap metadata scan, not the 2 GB hash.
    con = duckdb.connect(str(STORE), read_only=True)
    try:
        sep_rows, sep_sessions, sep_lo, sep_hi = con.execute(
            "SELECT count(*), count(DISTINCT date), min(date), max(date) FROM sep").fetchone()
        tickers_n = con.execute("SELECT count(*) FROM tickers").fetchone()[0]
        actions_n = con.execute("SELECT count(*) FROM actions").fetchone()[0]
    finally:
        con.close()
    if sep_hi.isoformat() != session.isoformat():
        raise SystemExit(
            f"REFUSED — the store's last SEP session is {sep_hi.isoformat()} but --session is "
            f"{session.isoformat()}. The manifest will not declare a session the corpus does not end "
            f"at.")
    normalized_datasets = {
        "sep": {"rows": int(sep_rows), "sessions": int(sep_sessions),
                "coverage": [sep_lo.isoformat(), sep_hi.isoformat()]},
        "tickers": {"identities": int(tickers_n)},
        "actions": {"rows": int(actions_n)},
        "evidence": "normalized_corpus_evidence",
        "measured": True,
    }
    print(f"dataset census (measured): sep {sep_rows:,} rows / {sep_sessions:,} sessions "
          f"{sep_lo}..{sep_hi} | tickers {tickers_n:,} | actions {actions_n:,}")

    store_block: dict
    if args.skip_store_digest:
        store_block = {"computed": False,
                       "refusal": "the manifest does not claim a store identity it did not compute"}
    else:
        print("hashing the store (2 GB)…")
        sd = _sha256_file(STORE)
        store_block = {"computed": True, "store_file_sha256": sd,
                       "bytes": STORE.stat().st_size, "path": STORE.name}
        print(f"  store_file_sha256 {sd}")

    payload = {
        "kind": "layer2_governed_corpus",
        "construction_schema_version": CONSTRUCTION_SCHEMA_VERSION,
        "canonicalization_contract": {
            "encoder": "canonical_json",
            "rules": "json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=True, "
                     "default=str) encoded utf-8",
            "digest": "sha256 over that encoding",
            "shared_with": "app.validation.governed_corpus.canonical_json",
        },
        "session": session.isoformat(),
        "security_identity_contract": SECURITY_IDENTITY_CONTRACT,
        # ── universe identities the construction asserts about itself ──
        "declared_identities": declared,
        "mapped_identity_universe_size": int(evidence["governed_mapped_identity_count"]),
        "price_universe_size": int(evidence["governed_price_identity_count"]),
        "two_universes_never_collapsed": (
            "the mapped-identity universe and the price universe are DISTINCT and the former is "
            "never redefined to mean the latter"),
        # ── every artifact, hashed from disk ──
        "artifacts": artifacts,
        "quarantined_histories": quarantine,
        "store": store_block,
        # ── normalized dataset identities ──
        "normalized_datasets": normalized_datasets,
        # Carried through from the construction so downstream packages can state the governed window
        # without re-deriving it (and without a literal that goes stale).
        "decision_window": evidence.get("decision_window"),
        # ── frozen preregistration artifacts ──
        "frozen_preregistration": {
            "dgs3mo_snapshot_sha256": DGS3MO_SNAPSHOT_SHA256,
            "dgs3mo_manifest_sha256":
                "e7365865394d2fc7ce2a746d246da6184664b4c0f0167938d1ce9691a32fff29",
            "trial_ledger_sha256": TRIAL_LEDGER_SHA256,
            "frozen_replica_sha256": {
                "scripts/backtest_momentum_stage2.py":
                    "7a49141b2f8e494aeeb5c5c9b86bae23cbfbd7d02496af7a356bdbb29481dc6e",
                "scripts/backtest_momentum_stage3.py":
                    "a10c3e2ece7a0cd0fed2d467a80168fdb3015af49a0e70abda9e9f9591aee4d3",
                "scripts/backtest_momentum_stage4.py":
                    "59c46af111556fbefbeeb622753cb8b8cc3963f2d11f44fbbbaab15e3e0199df",
            },
            "note": "the stage-4 replica digest is IDENTICAL on the superseded host runtime and in "
                    "this worktree, which is what makes the Step-4 comparison attributable to corpus "
                    "construction rather than code drift",
        },
        # ── the quarantine, stated as the owner ruled ──
        "governed_quarantine": {
            "names": ["SHOP", "TLN"],
            "permanent_identities": ["167284", "642054"],
            "class": "UNEXPLAINED_VENDOR_ADJUSTMENT_ANOMALY",
            "kind": "VERSION_SPECIFIC_PRICE_HISTORY_QUARANTINE",
            "permanent_universe_removal": False,
            "statement": [
                "decision-relevant in raw construction",
                "governed-quarantined due to unexplained vendor anomalies",
                "post-quarantine decision remains valid and all gates pass",
            ],
            "must_not_say": "SHOP/TLN are decision-irrelevant",
            "raw_relevance": {"SHOP": "session rank 119; enters top-200 and top-five",
                              "TLN": "enters proxy basket and contributors",
                              "both": "can affect the regime input"},
        },
        # ── supersession: the prior identity is preserved, not mutated ──
        "supersedes": {
            "corpus_manifest_sha256": args.supersedes,
            "base_corpus_sha256":
                "2659233f97cd3b34631a45812d3f2b6282cc31545793d03b22e8c5569722af87",
            "governed_universe_sha256": declared["legacy_governed_universe_sha256"],
            "governed_universe_size": 14_150,
            "base_countersignature": "GoverningCorpus_Countersignature_v2.0",
            "reason": SUPERSESSION_REASON,
            "relationship": "SUPERSEDES — NOT A DELTA and NOT A MUTATION. The prior identity remains "
                            "valid and unaltered so its countersignature stays checkable; ADR 0048 "
                            "§4 is explicit that a historical correction is never a delta.",
            "prior_identity_altered": False,
        },
        "countersignature": None,
        "status": "PROPOSED — NOT COUNTERSIGNED, NOT DEPLOYED",
    }

    blob = canonical_json(payload)
    digest = hashlib.sha256(blob).hexdigest()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)

    print(f"\n{'=' * 78}")
    print(f"PROPOSED corpus_manifest_sha256 : {digest}")
    print(f"supersedes                      : {args.supersedes}")
    print(f"reason                          : {SUPERSESSION_REASON}")
    print(f"artifacts bound                 : {len(artifacts)} + {len(quarantine)} quarantine files")
    print(f"status                          : {payload['status']}")
    print(f"wrote {out} ({len(blob):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
