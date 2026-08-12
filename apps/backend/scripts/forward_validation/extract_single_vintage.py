"""Layer 2 — the single-vintage full-history extraction of SEP / TICKERS / ACTIONS.

The defect this exists to eliminate: the base corpus SPLICES two adjustment vintages. Rows before
2026-06-15 came from a one-shot bulk ingest and were never re-pulled; rows from 06-15 onward have been
incrementally refreshed. Any dividend paid after 2026-06-15 back-adjusts only the refreshed side, so
`closeadj` steps at the seam — 635 of 5,690 names, 18x the ordinary adjacent-pair rate. A corpus built
by appending fresh rows to frozen history can never be free of it. The only fix is to take the whole
history from ONE vendor export.

## What "one governed source vintage" can and cannot mean

Each datatable refreshes on its OWN schedule — measured 2026-07-29: TICKERS 05:09 UTC, ACTIONS 04:13,
SEP 12:13. So a vintage CANNOT be defined as three equal refresh timestamps; no such instant exists.

What IS provable, and what the owner's stop conditions describe, is a NO-CHANGE WINDOW. Every identity
the vendor exposes for all three tables is recorded BEFORE the pull and again AFTER it:

  * `datatable.last_refreshed_time`  — when the table's data last changed
  * `file.data_snapshot_time`        — when this export was cut
  * the export object name           — content-addressed, e.g. `SHARADAR_SEP_2_da2386a1….zip`

If all nine values are unchanged across the window, then there exists an instant during it at which all
three files were simultaneously the current export — which is exactly the property that rules out
combining independently refreshed exports. Any drift is `RESTART_FROM_ZERO`: the run refuses, and the
downloaded bytes are marked `VOID` rather than reused, because a set that shifted mid-pull cannot be
repaired by re-pulling only the file that moved.

Deliberately NOT done here: no restriction to the historical `table == 'SEP'` master slice. That
restriction is narrower than the vendor's own price coverage — HYPG and OCCI carry governed SEP price
rows while their master records are filed under SFP — so the FULL TICKERS export is retained and the
slice is recorded as evidence, never applied as a filter.
"""

# ⚠ PORTED into the repository for REPRODUCIBILITY. Operator machine paths are removed: the
# backend root resolves relative to this file and every data location comes from an argument or
# an environment override. A hard-coded working-copy path would make the tool unrunnable by
# anyone else, which is the opposite of what a reproducible build tool is for.

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit

import duckdb
import httpx

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

# Deterministic console encoding. A cp1252 console raised UnicodeEncodeError on a single arrow
# character AFTER all substantive validation had passed, discarding three otherwise-valid extractions.
# Logging must never decide whether a valid result survives.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


import truststore  # noqa: E402

truststore.inject_into_ssl()

from dotenv import load_dotenv  # noqa: E402

for _e in (Path(os.environ.get("WORKBENCH_ENV_FILE", ".env")),
           Path(os.environ.get("WORKBENCH_ENV_FILE_ALT", "apps/backend/.env"))):
    if _e.exists():
        load_dotenv(_e, override=False)

from app.config import get_settings  # noqa: E402
from app.utils.tls_trust import enable_os_trust_store  # noqa: E402
from app.validation.governed_corpus import canonical_json  # noqa: E402

NDL_BASE = "https://data.nasdaq.com/api/v3/datatables/SHARADAR"
TABLES = ("TICKERS", "ACTIONS", "SEP")

#: The governed session cutoff is an explicit per-run input — deliberately NOT a module default.
#: Rows dated after it are recorded as bounded-out evidence, never silently dropped: at T+2 the source
#: NECESSARILY carries later-dated rows, and future-dated rows are a point-in-time hazard precisely
#: BECAUSE they exist upstream.
#:
#: It WAS the constant `GOVERNED_CUTOFF = "2026-07-27"` through the first governed construction. A
#: default is the wrong shape for a governed boundary: forgetting the flag would silently rebuild the
#: PREVIOUS session's corpus, and every downstream identity would still verify, because all of them
#: would be internally consistent with the wrong cutoff. There is no digest that catches that — the
#: only defence is to make the boundary an explicit act of the operator. Hence: required, no default.


def governed_cutoff(raw: str) -> str:
    """Validate and canonicalize the governed cutoff.

    Returned as a canonical ISO date so that only a fixed-shape literal ever reaches the SQL below.
    The cutoff is interpolated into queries, and an unvalidated operator string must never be.
    """
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--governed-cutoff must be an ISO date (YYYY-MM-DD), got {raw!r}") from exc

#: The date column whose min/max is the "relevant date range" for each table.
DATE_COLUMN = {"SEP": "date", "ACTIONS": "date", "TICKERS": "lastpricedate"}

_CHUNK = 1 << 20

#: A liquid name that must return rows. Without it, a zero for a candidate is indistinguishable from a
#: broken query, an expired key or a network fault — so the control makes the zero MEAN something.
CONTROL_TICKER = "AAPL"


class VintageDrift(RuntimeError):
    """The source vintage moved during the pull. Terminal: restart from zero."""


def _probe(client: httpx.Client, key: str, table: str) -> dict:
    """One export-endpoint probe. Returns the vendor's identity for that table's current export.

    The presigned query string is NEVER recorded — it carries a per-request signature that changes on
    every call and would make an unchanged export look like a drifted one. The object PATH is
    content-addressed and is the stable export identity.
    """
    resp = client.get(f"{NDL_BASE}/{table}.json",
                      params={"qopts.export": "true", "api_key": key})
    resp.raise_for_status()
    bulk = resp.json()["datatable_bulk_download"]
    link = bulk["file"]["link"]
    path = urlsplit(link).path
    return {
        "table": table,
        "status": bulk["file"]["status"],
        "data_snapshot_time": bulk["file"].get("data_snapshot_time"),
        "last_refreshed_time": bulk.get("datatable", {}).get("last_refreshed_time"),
        "export_object": path.rsplit("/", 1)[-1],
        "export_object_path": path,
        "_link": link,
    }


def _identity(p: dict) -> dict:
    """The subset that must not move across the extraction window."""
    return {k: p[k] for k in ("table", "data_snapshot_time", "last_refreshed_time", "export_object")}


def _download(client: httpx.Client, url: str, dest: Path) -> dict:
    started = datetime.now(UTC)
    h = hashlib.sha256()
    size = 0
    with client.stream("GET", url) as r:
        r.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in r.iter_bytes(_CHUNK):
                fh.write(chunk)
                h.update(chunk)
                size += len(chunk)
    ended = datetime.now(UTC)
    return {"artifact_path": str(dest), "artifact_sha256": h.hexdigest(), "artifact_bytes": size,
            "download_started_utc": started.isoformat(), "download_ended_utc": ended.isoformat(),
            "download_seconds": round((ended - started).total_seconds(), 3)}


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _unzip_single_csv(zip_path: Path, out_dir: Path) -> tuple[Path, dict]:
    """Extract the one CSV member. Refuses a multi-member archive rather than guessing which is data."""
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        if len(members) != 1:
            raise RuntimeError(
                f"{zip_path.name} holds {len(members)} members; a datatable export is expected to be "
                f"exactly one CSV: {[m.filename for m in members]}")
        m = members[0]
        dest = out_dir / m.filename
        with zf.open(m) as src, dest.open("wb") as dst:
            shutil.copyfileobj(src, dst, _CHUNK)
    return dest, {"member_name": m.filename, "member_uncompressed_bytes": m.file_size,
                  "member_crc32": f"{m.CRC:08x}"}


def _schema_fingerprint(csv_path: Path) -> dict:
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        header = fh.readline().rstrip("\r\n")
    cols = next(csv.reader(io.StringIO(header)))
    return {"columns": cols, "column_count": len(cols),
            "schema_fingerprint_sha256": hashlib.sha256(
                canonical_json(cols)).hexdigest(),
            "header_line_sha256": hashlib.sha256(header.encode("utf-8")).hexdigest()}


def _profile(con: duckdb.DuckDBPyConnection, table: str, csv_path: Path, cols: list[str],
             cutoff: str) -> dict:
    """Parsed-row profile, computed in duckdb so a 39M-row CSV never enters python memory."""
    rel = f"read_csv_auto('{csv_path.as_posix()}', header=true, all_varchar=true)"
    out: dict = {"parsed_row_count": int(
        con.execute(f"SELECT count(*) FROM {rel}").fetchone()[0])}
    dcol = DATE_COLUMN[table]
    if dcol in cols:
        lo, hi = con.execute(
            f"SELECT min({dcol}), max({dcol}) FROM {rel} WHERE {dcol} IS NOT NULL "
            f"AND {dcol} <> ''").fetchone()
        out |= {"date_column": dcol, "date_min": lo, "date_max": hi}
    if "ticker" in cols:
        out["distinct_tickers"] = int(con.execute(
            f"SELECT count(DISTINCT ticker) FROM {rel}").fetchone()[0])
    if "permaticker" in cols:
        out["distinct_permatickers"] = int(con.execute(
            f"SELECT count(DISTINCT permaticker) FROM {rel}").fetchone()[0])
        # The mapping itself is a stop condition, so it gets its own digest.
        pairs = con.execute(
            f"SELECT DISTINCT ticker, permaticker FROM {rel} ORDER BY ticker, permaticker"
        ).fetchall()
        out["ticker_permaticker_pair_count"] = len(pairs)
        out["ticker_permaticker_mapping_sha256"] = hashlib.sha256(
            canonical_json([[str(a), str(b)] for a, b in pairs])).hexdigest()
    if "table" in cols:
        out["slice_census"] = {str(k): int(v) for k, v in con.execute(
            f"SELECT \"table\", count(*) FROM {rel} GROUP BY 1 ORDER BY 1").fetchall()}
    if dcol in cols and table in ("SEP", "ACTIONS"):
        within = int(con.execute(
            f"SELECT count(*) FROM {rel} WHERE {dcol} <= '{cutoff}'").fetchone()[0])
        beyond = out["parsed_row_count"] - within
        out |= {"governed_cutoff": cutoff,
                "rows_within_cutoff": within, "rows_beyond_cutoff": beyond}
        if table == "ACTIONS":
            # "ACTIONS cutoff contents" is a stop condition in its own right.
            rows = con.execute(
                f"SELECT * FROM {rel} WHERE date <= '{cutoff}' "
                f"ORDER BY ALL").fetchall()
            out["actions_cutoff_row_count"] = len(rows)
            out["actions_cutoff_contents_sha256"] = hashlib.sha256(
                canonical_json([[None if c is None else str(c) for c in r] for r in rows])
            ).hexdigest()
            out["actions_cutoff_max_date"] = con.execute(
                f"SELECT max(date) FROM {rel} WHERE date <= '{cutoff}'").fetchone()[0]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Single-vintage extraction of SEP/TICKERS/ACTIONS.")
    ap.add_argument("--out", required=True)
    ap.add_argument("--crosswalk", required=True,
                    help="crosswalk/v2 — supplies the mapped universe the zero-row candidates for the "
                         "sealed G5 verification are derived from")
    ap.add_argument("--restart", action="store_true",
                    help="required to overwrite a non-empty output directory (restart from zero)")
    ap.add_argument("--governed-cutoff", required=True, type=governed_cutoff,
                    help="the governed session cutoff (YYYY-MM-DD). Rows dated after it are recorded "
                         "as bounded-out evidence. Required — see the module note on why this has no "
                         "default.")
    args = ap.parse_args(argv)
    cutoff: str = args.governed_cutoff

    # Artifact-level transactional seal: temporary artifacts -> all guards -> final evidence ->
    # atomic promotion. Three otherwise-valid extractions were discarded because a console print
    # raised after every guard had passed; a valid extraction must survive a logging failure.
    final_out = Path(args.out)
    if final_out.exists() and any(final_out.iterdir()) and not args.restart:
        raise SystemExit(
            f"{final_out} is not empty. A vintage extraction is all-or-nothing — pass --restart to "
            f"discard the previous attempt and restart from zero.")
    out = final_out.with_name(final_out.name + "__staging")
    if out.exists():
        shutil.rmtree(out)
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / "csv").mkdir(parents=True, exist_ok=True)

    enable_os_trust_store()
    key = get_settings().nasdaq_data_link_api_key
    if not key:
        raise SystemExit("NASDAQ_DATA_LINK_API_KEY is not set")

    window_open = datetime.now(UTC)
    client = httpx.Client(follow_redirects=True, timeout=300.0)
    try:
        # ---------------- Phase A: open the vintage window ----------------
        print("=== phase A: open vintage window ===")
        probes_open = {t: _probe(client, key, t) for t in TABLES}
        for t, p in probes_open.items():
            print(f"  {t:<8} status={p['status']:<10} refreshed={p['last_refreshed_time']} "
                  f"snapshot={p['data_snapshot_time']}")
            print(f"           export={p['export_object']}")
        stale = {t: p["status"] for t, p in probes_open.items() if p["status"] != "fresh"}
        if stale:
            raise SystemExit(
                f"refusing to extract: export(s) not fresh {stale}. A 'creating'/'regenerating' "
                f"export is a moving target and cannot anchor a vintage.")

        # ---------------- Phase B: pull ----------------
        print("\n=== phase B: pull ===")
        pulled: dict[str, dict] = {}
        for t in TABLES:
            dest = out / "raw" / probes_open[t]["export_object"]
            print(f"  downloading {t} -> {dest.name}", flush=True)
            pulled[t] = _download(client, probes_open[t]["_link"], dest)
            print(f"    {pulled[t]['artifact_bytes']:,} bytes in "
                  f"{pulled[t]['download_seconds']}s  sha256={pulled[t]['artifact_sha256']}")

        # ---------------- Phase C: close the vintage window ----------------
        print("\n=== phase C: close vintage window ===")
        probes_close = {t: _probe(client, key, t) for t in TABLES}
        drift = {t: {"open": _identity(probes_open[t]), "close": _identity(probes_close[t])}
                 for t in TABLES if _identity(probes_open[t]) != _identity(probes_close[t])}
        window_close = datetime.now(UTC)
        if drift:
            (out / "VOID_vintage_drift.json").write_text(json.dumps({
                "verdict": "RESTART_FROM_ZERO", "drift": drift,
                "window_open_utc": window_open.isoformat(),
                "window_close_utc": window_close.isoformat()}, indent=2), encoding="utf-8")
            for t, d in drift.items():
                print(f"  DRIFT {t}: {d['open']} -> {d['close']}")
            raise VintageDrift(
                "the source vintage moved during the pull; these bytes are VOID and must not be "
                "combined. Restart from zero with --restart.")
        print(f"  no drift across {len(TABLES)} tables — the window holds a single vintage "
              f"({(window_close - window_open).total_seconds():.0f}s wide)")
    finally:
        client.close()

    # ---------------- Phase D: parse + profile ----------------
    print("\n=== phase D: parse + profile ===")
    con = duckdb.connect(":memory:")
    sources: dict[str, dict] = {}
    for t in TABLES:
        zpath = Path(pulled[t]["artifact_path"])
        csv_path, member = _unzip_single_csv(zpath, out / "csv")
        schema = _schema_fingerprint(csv_path)
        prof = _profile(con, t, csv_path, schema["columns"], cutoff)
        row_set_sha = _sha256_file(csv_path)
        sources[t] = {
            **{k: v for k, v in probes_open[t].items() if k != "_link"},
            "vintage_identity_reconfirmed": _identity(probes_close[t]),
            **pulled[t], **member, **schema, **prof,
            "csv_path": str(csv_path),
            "row_set_identity_sha256": row_set_sha,
            "retrieval_parameters": {"endpoint": f"{NDL_BASE}/{t}.json",
                                     "qopts.export": "true",
                                     "api_key": "[redacted]"},
        }
        print(f"  {t:<8} rows={prof['parsed_row_count']:>12,} "
              f"{prof.get('date_column','-')}: {prof.get('date_min')}..{prof.get('date_max')}")
        print(f"           row_set_identity={row_set_sha}")
        if "rows_beyond_cutoff" in prof:
            print(f"           within {cutoff}: {prof['rows_within_cutoff']:,} | "
                  f"beyond (bounded out): {prof['rows_beyond_cutoff']:,}")
        if "slice_census" in prof:
            print(f"           slices: {prof['slice_census']}")
        if "ticker_permaticker_mapping_sha256" in prof:
            print(f"           permatickers={prof['distinct_permatickers']:,} "
                  f"mapping={prof['ticker_permaticker_mapping_sha256']}")
    # ---------------- Phase D2: SEALED direct per-ticker verification (the G5 contract) ----------
    # Vintage-bounded by construction. The zero-row candidates are DERIVED from this vintage, then
    # confirmed by a structurally different access path, and both the responses and the moment they
    # were taken are bound into the evidence below. Validation after the seal compares against THESE
    # sealed responses — never against whatever the live API returns hours later, because a frozen
    # export cannot be required to match an unbounded live API forever: any later vendor refresh would
    # make them disagree and would refuse every subsequent build. A post-seal live comparison is
    # DIAGNOSTIC ONLY, and a later refresh is recorded as post-capture drift.
    print("\n=== phase D2: sealed direct per-ticker verification (G5) ===")
    mapped = sorted({r["permaticker"] for r in json.loads(
        (Path(args.crosswalk) / "universe_crosswalk_v2.json").read_text(encoding="utf-8"))["rows"]
        if r.get("permaticker")})
    con.execute("CREATE TABLE _mapped(p VARCHAR)")
    con.executemany("INSERT INTO _mapped VALUES (?)", [(p,) for p in mapped])
    sep_rel = (f"read_csv_auto('{Path(sources['SEP']['csv_path']).as_posix()}', header=true, "
               f"all_varchar=true)")
    tk_rel = (f"read_csv_auto('{Path(sources['TICKERS']['csv_path']).as_posix()}', header=true, "
              f"all_varchar=true)")
    candidates = [(r[0], r[1]) for r in con.execute(f"""
        WITH tmap AS (SELECT DISTINCT ticker, permaticker FROM {tk_rel}),
             present AS (SELECT DISTINCT m.permaticker AS p FROM {sep_rel} s
                         JOIN tmap m ON m.ticker = s.ticker WHERE s.date <= '{cutoff}')
        SELECT _mapped.p,
               (SELECT min(ticker) FROM tmap WHERE permaticker = _mapped.p) AS tkr
        FROM _mapped WHERE _mapped.p NOT IN (SELECT p FROM present) ORDER BY 1""").fetchall()]
    con.close()
    print(f"  zero-row candidates derived from THIS vintage: "
          f"{[(p, t) for p, t in candidates]}")

    from app.factor_data.providers.sharadar import SharadarProvider  # noqa: PLC0415

    verified_at = datetime.now(UTC)
    per_ticker: dict[str, dict] = {}
    with SharadarProvider() as prov:
        for perm, tkr in candidates:
            df = prov.fetch_table("SEP", ticker=tkr)
            n = 0 if df.empty else len(df)
            per_ticker[tkr] = {"permaticker": perm, "export_rows": 0, "api_rows": n,
                               "agree": n == 0}
            print(f"  {tkr:<8} permaticker={perm:<9} export_rows=0 api_rows={n:<5} agree={n == 0}")
        cdf = prov.fetch_table("SEP", ticker=CONTROL_TICKER)
        control_n = 0 if cdf.empty else len(cdf)
    print(f"  control {CONTROL_TICKER}: api_rows={control_n} (must be > 0)")
    if control_n <= 0:
        raise VintageDrift(
            f"the control query ({CONTROL_TICKER}) returned {control_n} rows, so a zero for a "
            f"candidate proves nothing about the source; refusing to seal")
    disagree = {k: v for k, v in per_ticker.items() if not v["agree"]}
    if disagree:
        (out / "VOID_vintage_drift.json").write_text(json.dumps({
            "verdict": "RESTART_FROM_ZERO", "phase": "D2_seal_verification",
            "disagreement": disagree}, indent=2), encoding="utf-8")
        raise VintageDrift(
            f"G5: the two access paths disagree about zero-row status within the extraction window "
            f"{disagree}; the vintage cannot be sealed. Restart once the source is stable.")
    print(f"  G5 PASS: {len(per_ticker)} candidate(s) agree at zero across both access paths")

    # ---------------- Phase D3: SEAL — identities must be unchanged from open through seal --------
    print("\n=== phase D3: seal ===")
    seal_client = httpx.Client(follow_redirects=True, timeout=300.0)
    try:
        probes_seal = {t: _probe(seal_client, key, t) for t in TABLES}
    finally:
        seal_client.close()
    seal_drift = {t: {"open": _identity(probes_open[t]), "seal": _identity(probes_seal[t])}
                  for t in TABLES if _identity(probes_open[t]) != _identity(probes_seal[t])}
    if seal_drift:
        (out / "VOID_vintage_drift.json").write_text(json.dumps({
            "verdict": "RESTART_FROM_ZERO", "phase": "D3_seal", "drift": seal_drift}, indent=2),
            encoding="utf-8")
        raise VintageDrift(
            f"the source moved before the vintage could be sealed: {seal_drift}. VOID; restart.")
    sealed_at = datetime.now(UTC)
    print(f"  SEALED {sealed_at.isoformat()} — identities unchanged open→seal "
          f"({(sealed_at - window_open).total_seconds():.0f}s)")

    sealed_verification = {
        "contract": ("G5 is proved INSIDE the extraction window and bound here; post-seal live-API "
                     "comparison is diagnostic only, and a later vendor refresh is post-capture "
                     "drift that does not invalidate a properly sealed T+2 vintage"),
        "verified_at_utc": verified_at.isoformat(),
        "sealed_at_utc": sealed_at.isoformat(),
        "zero_row_candidates": [{"permaticker": p, "ticker": t} for p, t in candidates],
        "per_ticker": per_ticker,
        "control": {"ticker": CONTROL_TICKER, "api_rows": control_n, "valid": control_n > 0},
        "all_methods_agree_on_zero": True,
        "identities_unchanged_open_through_seal": True,
    }

    # Recorded paths must describe where the artifacts WILL be published, not the transient staging
    # location: the evidence outlives the staging directory, and a consumer resolving a staging path
    # after promotion finds nothing. Rewritten BEFORE the evidence is serialized, so the digest covers
    # the published paths.
    _stage, _final = str(out), str(final_out)
    for _src in sources.values():
        for _k in ("artifact_path", "csv_path"):
            _src[_k] = _src[_k].replace(_stage, _final)

    # ---------------- Phase E: the source-vintage identity ----------------
    vintage_payload = {
        "kind": "layer2_source_vintage", "version": "v1.0",
        "vintage_definition": (
            "a proven no-change window: every vendor identity for all three exports "
            "(last_refreshed_time, data_snapshot_time, content-addressed export object) was recorded "
            "before the pull and reconfirmed unchanged after it, so an instant exists at which all "
            "three were simultaneously the current export"),
        "window_open_utc": window_open.isoformat(),
        "window_close_utc": window_close.isoformat(),
        "sealed": True,
        "sealed_at_utc": sealed_at.isoformat(),
        "sealed_verification": sealed_verification,
        "governed_cutoff": cutoff,
        "tables": list(TABLES),
        "vintage_identities": {t: _identity(probes_open[t]) for t in TABLES},
        "artifact_sha256": {t: sources[t]["artifact_sha256"] for t in TABLES},
        "row_set_identity_sha256": {t: sources[t]["row_set_identity_sha256"] for t in TABLES},
        "ticker_permaticker_mapping_sha256":
            sources["TICKERS"].get("ticker_permaticker_mapping_sha256"),
        "actions_cutoff_contents_sha256": sources["ACTIONS"].get("actions_cutoff_contents_sha256"),
        "sep_table_slice_restriction_applied": False,
        "sep_table_slice_restriction_note": (
            "the historical table=='SEP' master restriction is NOT applied — it is narrower than the "
            "vendor's own price coverage (HYPG, OCCI file under SFP), so the full TICKERS export is "
            "retained and the slice census is evidence, not a filter"),
    }
    vintage_blob = canonical_json(vintage_payload)
    source_vintage_sha = hashlib.sha256(vintage_blob).hexdigest()

    evidence = {"kind": "layer2_extraction_evidence", "version": "v1.0",
                "source_vintage_sha256": source_vintage_sha,
                "source_vintage": vintage_payload, "sources": sources}
    blob = canonical_json(evidence)
    (out / "extraction_evidence.json").write_bytes(blob)
    (out / "source_vintage.json").write_bytes(vintage_blob)

    # ATOMIC PROMOTION — every guard has passed and the final evidence is durable, so publish the
    # sealed vintage NOW, before any further console IO. Nothing after this point may decide whether
    # a valid extraction survives.
    if final_out.exists():
        shutil.rmtree(final_out)
    out.rename(final_out)
    out = final_out

    print("\n=== phase E: source-vintage identity ===")
    print(f"  source_vintage_sha256      : {source_vintage_sha}")
    print(f"  extraction_evidence_sha256 : {hashlib.sha256(blob).hexdigest()}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VintageDrift as exc:
        print(f"\nRESTART_FROM_ZERO: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
