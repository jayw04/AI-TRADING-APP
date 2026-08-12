"""Compose the ONE governed delta artifact for a session (owner-ratified 2026-07-29).

ADR 0048 (2) speaks of "a delta" as a single hashed thing, and `GovernedDelta` carries exactly one
`sha256`. So SEP and ACTIONS travel as one artifact whose digest is literally the file's bytes — no
composite-digest convention is invented, and the manifest binds the same object an operator can hash.

The per-dataset CSVs stay on disk as the audit trail: their digests are recorded inside this artifact's
report so the composition is checkable in both directions, but they are not what the manifest binds.

    apps/backend/.venv/Scripts/python.exe build_combined_delta.py --session 2026-07-27 --dir deltas/2026-07-27
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import date
from pathlib import Path

from scripts.forward_validation._base_facts import (
    BaseFactsError,
    bind_delta_lower_bound,
    load_corpus_manifest,
    measure_base,
)
from scripts.forward_validation.capture_verify_session import CORPUS, canonical_json

# The composed artifact's `base_coverage_through` is taken from the build report and INDEPENDENTLY
# re-derived from the manifest here — it was the constant `BASE_COVERAGE_THROUGH = date(2026, 7, 24)`.
# Composition is the last step that can catch a delta bounded against the wrong corpus, so it checks
# rather than trusts: a build report and a manifest that disagree stop the composition.


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[list[str]], str]:
    raw = path.read_bytes()
    rows = list(csv.reader(raw.decode("utf-8").splitlines()))
    return rows[0], rows[1:], sha256_bytes(raw)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compose the single governed delta artifact.")
    ap.add_argument("--session", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--base-manifest", required=True,
                    help="the countersigned corpus manifest the delta will be appended to. Required "
                         "and without a default: the composed artifact declares the lower edge, so "
                         "composition re-derives it instead of trusting the build report alone.")
    args = ap.parse_args(argv)

    session = date.fromisoformat(args.session)
    d = Path(args.dir)

    build_report = json.loads((d / f"delta_build_report_{session}.json").read_text(encoding="utf-8"))

    # ---- the lower edge, re-derived and reconciled with what the build recorded ----
    manifest = load_corpus_manifest(args.base_manifest)
    measured = measure_base(CORPUS)
    lower = bind_delta_lower_bound(manifest, measured, session=session)

    declared = build_report.get("base_coverage_through")
    if declared is None:
        raise BaseFactsError(
            "the delta build report carries no base_coverage_through; it was produced by a builder "
            "that declared the lower edge as a constant, and this composition cannot confirm which "
            "corpus the delta was actually bounded against.")
    if str(declared) != lower.isoformat():
        raise BaseFactsError(
            f"the delta was built against lower edge {declared} but the manifest and the bound corpus "
            f"agree on {lower.isoformat()}; the artifact would declare coverage it does not have.")

    sep_cols, sep_rows, sep_sha = read_csv(d / f"sep_delta_{session}.csv")
    act_cols, act_rows, act_sha = read_csv(d / f"actions_delta_{session}.csv")

    # the composed artifact must carry exactly what the verified CSVs carry
    if sep_sha != build_report["sep"]["sha256"] or act_sha != build_report["actions"]["sha256"]:
        raise SystemExit("a per-dataset CSV does not hash to the digest recorded in the build report")
    if len(sep_rows) != build_report["sep"]["rows"] or len(act_rows) != build_report["actions"]["rows"]:
        raise SystemExit("a per-dataset CSV row count disagrees with the build report")

    artifact = {
        "kind": "governed_delta",
        "session_date": session.isoformat(),
        "coverage_through": session.isoformat(),
        "base_coverage_through": lower.isoformat(),
        "governed_universe_sha256": build_report["governed_universe_sha256"],
        "governed_universe_size": build_report["governed_universe_size"],
        "sep": {"columns": sep_cols, "rows": sep_rows},
        "actions": {"columns": act_cols, "rows": act_rows},
    }
    payload = canonical_json(artifact)
    path = d / f"delta_{session}.json"
    path.write_bytes(payload)
    digest = sha256_bytes(payload)

    report = {
        "artifact_path": str(path),
        "sha256": digest,
        "bytes": len(payload),
        "session_date": session.isoformat(),
        "coverage_through": session.isoformat(),
        "rows_total": len(sep_rows) + len(act_rows),
        "components": {
            "sep": {"rows": len(sep_rows), "csv_sha256": sep_sha,
                    "source_sha256": build_report["sep"]["source_sha256"],
                    "retrieved_at": build_report["sep"]["retrieved_at"]},
            "actions": {"rows": len(act_rows), "csv_sha256": act_sha,
                        "source_sha256": build_report["actions"]["source_sha256"],
                        "retrieved_at": build_report["actions"]["retrieved_at"]},
        },
        "exclusions": [
            f"ACTIONS rows dated after {session} excluded: "
            f"{build_report['actions']['future_dated_excluded_rows']} rows "
            f"({', '.join(build_report['actions']['future_dated_excluded_dates'][:3])})",
            f"out-of-universe ACTIONS rows dropped: "
            f"{build_report['actions']['out_of_universe_dropped']}",
        ],
    }
    (d / f"delta_artifact_report_{session}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"=== combined governed delta - {session} ===")
    print(f"artifact  {path}")
    print(f"sha256    {digest}")
    print(f"bytes     {len(payload):,}")
    print(f"rows      SEP {len(sep_rows):,} + ACTIONS {len(act_rows):,} = "
          f"{len(sep_rows) + len(act_rows):,}")
    print(f"components verified against the build report (SEP {sep_sha[:16]}..., "
          f"ACTIONS {act_sha[:16]}...)")
    for x in report["exclusions"]:
        print(f"exclusion {x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
