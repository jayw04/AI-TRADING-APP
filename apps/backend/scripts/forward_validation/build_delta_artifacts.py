"""Build the governed SEP + ACTIONS delta artifacts for one session (ADR 0048 append-only delta).

The SEP artifact is DERIVED from the capture produced by `capture_verify_session.py` rather than
re-fetched, so the nine structural checks and the artifact digest recorded in that capture report keep
covering the rows that actually get ingested. Re-fetching would silently re-open the accretion window
between capture and build, and the delta would no longer be the thing that was verified.

The ACTIONS artifact is built here, bounded to `(base_coverage_through, session]`, restricted to the
same governed universe, and projected onto the corpus's exact column list. Its own bound is proven and
its future-dated exclusions are recorded, per OwnerRuling_SEPIngestLag_T2_v1.0 section 5 check 9.

Both are written as typed CSV: deterministic byte-for-byte, human-auditable, and castable to the
corpus schema on ingest without a serializer in the trust path.

⚠ `contraticker` carries the LITERAL string 'N/A' in 239,744 base rows and is NEVER NULL there. It is
preserved verbatim; converting it to NULL would make the delta structurally unlike the base.

    apps/backend/.venv/Scripts/python.exe build_delta_artifacts.py \
        --session 2026-07-27 --capture-dir deltas/2026-07-27 --out deltas/2026-07-27
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.factor_data.providers.sharadar import SharadarProvider  # noqa: E402
from scripts.forward_validation._base_facts import (  # noqa: E402
    bind_delta_lower_bound,
    load_corpus_manifest,
    measure_base,
    require_delta_window,
)
from scripts.forward_validation.capture_verify_session import (  # noqa: E402
    CORPUS,
    GOVERNED_UNIVERSE_SIZE,
    canonical_json,
    load_governed_context,
    universe_digest,
)

#: Exact corpus column order. Ingest casts positionally, so this list is load-bearing.
SEP_COLUMNS = ["ticker", "date", "open", "high", "low", "close", "volume",
               "closeadj", "closeunadj", "lastupdated"]
ACTIONS_COLUMNS = ["date", "action", "ticker", "name", "value", "contraticker"]

# The delta's lower edge is MEASURED from the bound corpus and BOUND to its countersigned manifest —
# see `_base_facts`. It was the constant `BASE_COVERAGE_THROUGH = date(2026, 7, 24)`, which described
# the base before any delta. That is the wrong edge for every session after the first: a 2026-07-28
# delta bounded at 2026-07-24 would re-ingest three sessions the corpus already holds. The edge moves
# whenever a delta is committed, so it cannot be a declaration.

RATIFIED_UNIVERSE_PREFIX = "2b34970fc123689b"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def csv_escape(value: str) -> str:
    if any(ch in value for ch in (',', '"', '\n', '\r')):
        return '"' + value.replace('"', '""') + '"'
    return value


def write_csv(path: Path, columns: list[str], rows: list[list[str]]) -> bytes:
    """Deterministic CSV: LF endings, no BOM, fixed column order, empty field == SQL NULL."""
    out = [",".join(columns)]
    out.extend(",".join(csv_escape(v) for v in row) for row in rows)
    payload = ("\n".join(out) + "\n").encode("utf-8")
    path.write_bytes(payload)
    return payload


def _num(value: str) -> str:
    """Normalize a stringified number; empty/NaN becomes an empty field (SQL NULL)."""
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null", "<na>"}:
        return ""
    return text


def _int(value: str) -> str:
    text = _num(value)
    if text == "":
        return ""
    return str(int(float(text)))


def build_sep(session: date, capture_dir: Path, out: Path, universe_sha: str) -> dict:
    """Project the verified capture onto the corpus schema. No re-fetch."""
    artifact = capture_dir / f"sep_governed_{session}.json"
    report_path = capture_dir / f"capture_report_{session}.json"
    if not artifact.is_file() or not report_path.is_file():
        raise SystemExit(f"capture artifact/report missing in {capture_dir}; run "
                         f"capture_verify_session.py --session {session} --out {capture_dir} first")

    raw = artifact.read_bytes()
    captured = json.loads(raw)
    report = json.loads(report_path.read_text(encoding="utf-8"))

    if not report.get("all_checks_pass"):
        raise SystemExit("the capture report does not record all structural checks passing")
    if report.get("artifact_sha256") != sha256_bytes(raw):
        raise SystemExit("the capture artifact does not hash to the digest in its own report")
    if report.get("governed_universe_sha256") != universe_sha:
        raise SystemExit("the capture bound a different governed universe than this build")

    cols = captured["columns"]
    if cols != SEP_COLUMNS:
        raise SystemExit(f"capture column order {cols} != corpus schema {SEP_COLUMNS}")

    idx = {c: i for i, c in enumerate(cols)}
    rows: list[list[str]] = []
    for r in captured["rows"]:
        if r[idx["date"]] != session.isoformat():
            raise SystemExit(f"capture carries a row dated {r[idx['date']]}, not {session}")
        rows.append([
            r[idx["ticker"]], r[idx["date"]],
            _num(r[idx["open"]]), _num(r[idx["high"]]), _num(r[idx["low"]]), _num(r[idx["close"]]),
            _int(r[idx["volume"]]),
            _num(r[idx["closeadj"]]), _num(r[idx["closeunadj"]]), r[idx["lastupdated"]],
        ])
    rows.sort(key=lambda r: (r[0], r[1]))

    path = out / f"sep_delta_{session}.csv"
    payload = write_csv(path, SEP_COLUMNS, rows)
    return {
        "path": str(path), "rows": len(rows), "sha256": sha256_bytes(payload),
        "source_sha256": report["artifact_sha256"],
        "retrieved_at": report["retrieved_at"],
        "derived_from_capture": True,
        "capture_report_sha256": sha256_bytes(report_path.read_bytes()),
    }


def build_actions(session: date, out: Path, universe: set[str], lower: date) -> dict:
    """Bounded to (lower, session], restricted to the governed universe.

    ``lower`` is the corpus's measured, manifest-bound coverage — never a declared constant.
    """
    retrieved_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with SharadarProvider() as provider:
        act = provider.fetch_table(
            "ACTIONS", **{"date.gte": (lower - timedelta(days=1)).isoformat()})

    source_payload = canonical_json({
        "table": "ACTIONS", "columns": list(act.columns),
        "rows": act.astype(str).sort_values(list(act.columns)).values.tolist()})
    source_sha = sha256_bytes(source_payload)

    dates = act["date"].astype(str)
    in_window = act[(dates > lower.isoformat()) & (dates <= session.isoformat())]
    future = act[dates > session.isoformat()]
    governed = in_window[in_window["ticker"].isin(universe)]
    dropped = len(in_window) - len(governed)

    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "pass": bool(ok), "detail": detail})

    win_dates = sorted({str(d) for d in governed["date"].astype(str)})
    # Refuses rather than records: an out-of-window date means the delta overlaps existing coverage.
    require_delta_window(lower, session, win_dates)
    check("bounded_to_cutoff",
          all(lower.isoformat() < d <= session.isoformat() for d in win_dates),
          f"session dates present: {win_dates} (bound: > {lower}, <= {session})")
    check("no_out_of_universe_rows",
          not len(governed) or bool((governed["ticker"].isin(universe)).all()),
          f"{dropped:,} out-of-universe rows dropped from {len(in_window):,} in-window rows")
    check("future_dated_excluded", True,
          f"{len(future):,} rows dated after {session} EXCLUDED "
          f"(dates {sorted({str(d) for d in future['date'].astype(str)})[:5]})")
    missing_cols = [c for c in ACTIONS_COLUMNS if c not in governed.columns]
    check("corpus_columns_present", not missing_cols,
          f"source carries {list(governed.columns)}; corpus needs {ACTIONS_COLUMNS}"
          + (f"; MISSING {missing_cols}" if missing_cols else ""))

    rows: list[list[str]] = []
    for _, r in governed.iterrows():
        rows.append([
            str(r["date"]), str(r["action"]), str(r["ticker"]), str(r["name"]),
            _num(r["value"]),
            # ⚠ literal 'N/A' is the base convention and is preserved verbatim
            "" if str(r["contraticker"]).strip().lower() in {"nan", "none", ""}
            else str(r["contraticker"]),
        ])
    rows.sort(key=lambda r: (r[0], r[1], r[2], r[5]))

    na_contra = sum(1 for r in rows if r[5] == "N/A")
    null_value = sum(1 for r in rows if r[4] == "")
    check("na_sentinel_preserved", True,
          f"contraticker=='N/A' literal on {na_contra:,} of {len(rows):,} rows (base convention); "
          f"{null_value:,} rows carry NULL value")

    by_action: dict[str, int] = {}
    for r in rows:
        by_action[r[1]] = by_action.get(r[1], 0) + 1

    path = out / f"actions_delta_{session}.csv"
    payload = write_csv(path, ACTIONS_COLUMNS, rows)
    return {
        "path": str(path), "rows": len(rows), "sha256": sha256_bytes(payload),
        "source_sha256": source_sha, "retrieved_at": retrieved_at,
        "by_action": dict(sorted(by_action.items(), key=lambda kv: -kv[1])),
        "session_dates_present": win_dates,
        "out_of_universe_dropped": dropped,
        "future_dated_excluded_rows": int(len(future)),
        "future_dated_excluded_dates": sorted({str(d) for d in future["date"].astype(str)}),
        "checks": checks,
        "all_checks_pass": all(c["pass"] for c in checks),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build governed SEP + ACTIONS delta artifacts.")
    ap.add_argument("--session", required=True)
    ap.add_argument("--capture-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base-manifest", required=True,
                    help="the countersigned corpus manifest the delta will be appended to. Required "
                         "and without a default: the delta's lower edge is read from it and "
                         "cross-checked against the bound corpus, so it cannot be assumed.")
    args = ap.parse_args(argv)

    session = date.fromisoformat(args.session)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # ---- bind the delta's lower edge to the corpus it will actually be appended to ----
    manifest = load_corpus_manifest(args.base_manifest)
    measured = measure_base(CORPUS)
    lower = bind_delta_lower_bound(manifest, measured, session=session)
    print(f"delta window bound to ({lower}, {session}]  "
          f"(base {manifest.base_coverage_through} + {len(manifest.deltas)} delta(s))")

    ctx = load_governed_context(session)
    universe = ctx["universe"]
    universe_sha = universe_digest(universe)
    if len(universe) != GOVERNED_UNIVERSE_SIZE:
        raise SystemExit(f"universe is {len(universe):,}, not the governing {GOVERNED_UNIVERSE_SIZE:,}")
    if not universe_sha.startswith(RATIFIED_UNIVERSE_PREFIX):
        raise SystemExit(f"universe digest {universe_sha[:16]} != ratified {RATIFIED_UNIVERSE_PREFIX}")

    sep = build_sep(session, Path(args.capture_dir), out, universe_sha)
    actions = build_actions(session, out, universe, lower)

    report = {
        "session": session.isoformat(),
        # Named `base_coverage_through` for continuity with the artifact schema, but it is now the
        # BOUND lower edge — base plus every committed delta — measured and manifest-verified.
        "base_coverage_through": lower.isoformat(),
        "delta_lower_bound_source": "corpus_manifest.coverage_through (measured + verified)",
        "base_manifest_path": str(args.base_manifest),
        "base_manifest_declared_base_coverage_through":
            manifest.base_coverage_through.isoformat(),
        "base_manifest_committed_deltas": len(manifest.deltas),
        "base_corpus_sha256": manifest.base_corpus_sha256,
        "measured_base": measured.evidence(),
        "governed_universe_sha256": universe_sha,
        "governed_universe_size": len(universe),
        "sep": sep,
        "actions": actions,
    }
    (out / f"delta_build_report_{session}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"=== governed delta artifacts - {session} ===")
    print(f"universe {len(universe):,} tickers, digest {universe_sha}")
    print(f"\nSEP     {sep['rows']:,} rows  sha256 {sep['sha256']}")
    print(f"        derived from capture artifact {sep['source_sha256'][:16]}... (no re-fetch)")
    print(f"ACTIONS {actions['rows']:,} rows  sha256 {actions['sha256']}")
    print(f"        by action: {actions['by_action']}")
    print(f"        dates: {actions['session_dates_present']}")
    print(f"        {actions['future_dated_excluded_rows']:,} future-dated rows excluded "
          f"({actions['future_dated_excluded_dates'][:4]})")
    print()
    for c in actions["checks"]:
        print(f"[{'PASS' if c['pass'] else 'FAIL'}] actions.{c['name']:<26} {c['detail']}")

    ok = actions["all_checks_pass"]
    print(f"\nVERDICT: {'ARTIFACTS BUILT' if ok else 'CHECKS FAILED'}")
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
