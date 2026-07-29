"""Generate the ADR 0048 governed-construction manifests for one observation session.

Two manifests, both consumed fail-closed by `resolve_governed_construction`:

    corpus_manifest.json   immutable SEP/ACTIONS base + ordered deltas + the governed TICKERS
                           construction + the security-identity contract
    dgs3mo_manifest.json   the risk-free construction — frozen base + ordered coverage extensions

Every identity here is MEASURED, never typed: digests come from the artifacts on disk, row counts and
permanent-id counts from the artifacts themselves, and the manifest objects are built with the same
`app.validation.governed_corpus` classes the session validates with. Serialization goes through
`to_manifest_json()` for the same reason — a generator that wrote the JSON by hand would be a second,
unreviewed definition of what a governed construction is, free to drift from the one that verifies it.

Both manifests are validated with the real loaders before anything is written, so a manifest the host
would refuse fails on the build machine instead of on the morning of an observation.

    python scripts/forward_validation/generate_construction_manifests.py \\
        --session 2026-07-27 --spec build/session-2026-07-27.json --out build/manifests
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.validation.forward_window import (  # noqa: E402
    DGS3MO_OBSERVATION_CUTOFF,
    DGS3MO_SNAPSHOT_SHA256,
)
from app.validation.governed_corpus import (  # noqa: E402
    TICKERS_SCHEMA_VERSION,
    CorpusManifest,
    Dgs3moManifest,
    GovernedDelta,
    TickersManifest,
    file_sha256,
    load_corpus_manifest,
    load_dgs3mo_manifest,
    tickers_row_identity,
)
from app.validation.security_lineage import SECURITY_IDENTITY_CONTRACT  # noqa: E402


class GenerationError(RuntimeError):
    """The construction could not be described truthfully. Nothing is written."""


def _read_tickers_artifact(path: Path) -> tuple[list[list[str]], list[str]]:
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise GenerationError(f"the TICKERS artifact at {path} is empty")
    return rows[1:], rows[0]


def build_tickers_manifest(artifact: Path, *, cutoff: date, source_identity: str,
                           countersignature: str) -> TickersManifest:
    """Derive the TICKERS construction FROM the artifact, so the manifest cannot describe a file that
    is not there."""
    body, columns = _read_tickers_artifact(artifact)
    missing = [c for c in ("permaticker", "ticker", "firstpricedate", "lastpricedate")
               if c not in columns]
    if missing:
        raise GenerationError(
            f"the TICKERS artifact omits identity-bearing column(s) {missing}; "
            f"{SECURITY_IDENTITY_CONTRACT} cannot resolve securities without them")

    index = {c: i for i, c in enumerate(columns)}
    identity_rows = [[r[index["permaticker"]], r[index["ticker"]],
                      r[index["firstpricedate"]], r[index["lastpricedate"]]] for r in body]
    blank = sum(1 for r in identity_rows if not r[0].strip())
    if blank:
        raise GenerationError(
            f"{blank} TICKERS row(s) carry no permanent identifier; the column is mandatory and is "
            f"never backfilled from ticker equality")

    return TickersManifest(
        schema_version=TICKERS_SCHEMA_VERSION,
        columns=tuple(columns),
        rows=len(body),
        permanent_ids=len({r[0] for r in identity_rows}),
        row_identity_sha256=tickers_row_identity(identity_rows),
        coverage_cutoff=cutoff,
        artifact_sha256=file_sha256(artifact),
        source_identity=source_identity,
        countersignature=countersignature,
    )


def _delta(spec: dict[str, Any], artifact_root: Path) -> GovernedDelta:
    artifact = artifact_root / spec["artifact"]
    sources = artifact_root / spec["sources_artifact"]
    for p in (artifact, sources):
        if not p.is_file():
            raise GenerationError(f"the delta names {p}, which is not present")
    return GovernedDelta(
        session_date=date.fromisoformat(spec["session_date"]),
        coverage_through=date.fromisoformat(spec["coverage_through"]),
        sha256=file_sha256(artifact),
        source_sha256=file_sha256(sources),
        universe_sha256=spec["universe_sha256"],
        rows=int(spec["rows"]),
        retrieved_at=spec["retrieved_at"],
        countersignature=spec["countersignature"],
        exclusions=tuple(spec.get("exclusions", ())),
    )


def _extension(spec: dict[str, Any], artifact_root: Path) -> GovernedDelta:
    artifact = artifact_root / spec["artifact"]
    if not artifact.is_file():
        raise GenerationError(f"the DGS3MO extension names {artifact}, which is not present")
    return GovernedDelta(
        session_date=date.fromisoformat(spec["session_date"]),
        coverage_through=date.fromisoformat(spec["coverage_through"]),
        sha256=file_sha256(artifact),
        source_sha256=spec["source_sha256"],
        universe_sha256=None,                    # a rate series is not universe-bound
        rows=int(spec["rows"]),
        retrieved_at=spec["retrieved_at"],
        countersignature=spec["countersignature"],
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", required=True)
    ap.add_argument("--spec", required=True, type=Path,
                    help="JSON describing the base, deltas, TICKERS artifact and DGS3MO extensions")
    ap.add_argument("--artifact-root", type=Path, default=None,
                    help="directory the spec's artifact paths are relative to (default: spec's dir)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--expected-sessions", nargs="*", default=None,
                    help="governed sessions strictly after the base cutoff, through the session")
    args = ap.parse_args(argv)

    session = date.fromisoformat(args.session)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    root = args.artifact_root or args.spec.parent
    args.out.mkdir(parents=True, exist_ok=True)

    tickers = build_tickers_manifest(
        root / spec["tickers"]["artifact"],
        cutoff=date.fromisoformat(spec["tickers"]["coverage_cutoff"]),
        source_identity=spec["tickers"]["source_identity"],
        countersignature=spec["tickers"]["countersignature"])

    corpus = CorpusManifest(
        base_corpus_sha256=spec["base"]["sha256"],
        base_coverage_through=date.fromisoformat(spec["base"]["coverage_through"]),
        governed_universe_sha256=spec["base"]["governed_universe_sha256"],
        governed_universe_size=int(spec["base"]["governed_universe_size"]),
        actions_manifest_sha256=spec["actions"]["manifest_sha256"],
        actions_authoritative=bool(spec["actions"]["authoritative"]),
        tickers=tickers,
        tickers_authoritative=bool(spec["tickers"]["authoritative"]),
        security_identity_contract=SECURITY_IDENTITY_CONTRACT,
        deltas=tuple(_delta(d, root) for d in spec.get("deltas", [])),
        base_countersignature=spec["base"]["countersignature"])

    dgs3mo = Dgs3moManifest(
        base_sha256=DGS3MO_SNAPSHOT_SHA256,
        base_coverage_through=date.fromisoformat(DGS3MO_OBSERVATION_CUTOFF),
        extensions=tuple(_extension(e, root) for e in spec.get("dgs3mo_extensions", [])))

    corpus_path = args.out / "corpus_manifest.json"
    dgs3mo_path = args.out / "dgs3mo_manifest.json"
    corpus_path.write_text(json.dumps(corpus.to_manifest_json(), indent=2, sort_keys=True),
                           encoding="utf-8")
    dgs3mo_path.write_text(json.dumps(
        {"base_sha256": dgs3mo.base_sha256,
         "base_coverage_through": dgs3mo.base_coverage_through.isoformat(),
         "extensions": [{"session_date": e.session_date.isoformat(),
                         "coverage_through": e.coverage_through.isoformat(),
                         "sha256": e.sha256, "source_sha256": e.source_sha256, "rows": e.rows,
                         "retrieved_at": e.retrieved_at,
                         "countersignature": e.countersignature} for e in dgs3mo.extensions]},
        indent=2, sort_keys=True), encoding="utf-8")

    # ── validated with the REAL loaders, from disk, before anything downstream trusts them ──
    expected = tuple(date.fromisoformat(d) for d in (args.expected_sessions or []))
    reloaded = load_corpus_manifest(corpus_path)
    reloaded.validate(observation_session=session, expected_sessions=expected)
    reloaded_dgs = load_dgs3mo_manifest(dgs3mo_path)
    reloaded_dgs.validate(observation_session=session, frozen_base_sha256=DGS3MO_SNAPSHOT_SHA256)

    if reloaded.corpus_manifest_sha256 != corpus.corpus_manifest_sha256:
        raise GenerationError("the written corpus manifest does not reload to the identity it was "
                              "generated with")

    print(json.dumps({
        "status": "GENERATED",
        "session": session.isoformat(),
        "corpus_manifest": {"path": str(corpus_path),
                            "sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest()},
        "dgs3mo_manifest": {"path": str(dgs3mo_path),
                            "sha256": hashlib.sha256(dgs3mo_path.read_bytes()).hexdigest()},
        "identities": {
            "corpus_manifest_sha256": reloaded.corpus_manifest_sha256,
            "tickers_manifest_sha256": reloaded.tickers_manifest_sha256,
            "actions_manifest_sha256": reloaded.actions_manifest_sha256,
            "governed_universe_sha256": reloaded.governed_universe_sha256,
            "security_identity_contract": reloaded.security_identity_contract,
            "dgs3mo_manifest_sha256": reloaded_dgs.dgs3mo_manifest_sha256,
        },
        "coverage": {"corpus_through": reloaded.coverage_through.isoformat(),
                     "dgs3mo_through": reloaded_dgs.coverage_through.isoformat(),
                     "tickers_cutoff": reloaded.tickers.coverage_cutoff.isoformat()},
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GenerationError as exc:
        print(json.dumps({"status": "REFUSED", "detail": str(exc)}, indent=2))
        raise SystemExit(2) from exc
