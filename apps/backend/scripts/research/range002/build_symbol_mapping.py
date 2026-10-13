"""RANGE-002: explicit request-symbol mapping for every symbol of the fetch universe.

    python -I build_symbol_mapping.py --universe-file SYMBOLS.txt --daily-dir EXPORT_DIR \\
        --table-filter SEP --probe-json PROBE.json --out MAPPING.json

Every vendor ticker in the universe gets a request symbol, an ``asof`` policy and a PROVENANCE:

* ``ALPHA_TICKER_AS_IS``      letters only: the request symbol is the vendor ticker.
* ``CLASS_SHARE_PRESERVED``   a dotted class share (``BRK.B``): preserved verbatim, never stripped.
* ``SUFFIX_MAPPED_PROBE_VERIFIED``  a vendor-disambiguated reused ticker (``APC1``): the base symbol
  is used ONLY when (a) the vendor's own ``relatedtickers`` for that row lists the base AND (b) the
  return-blind probe returned bars (HTTP 200, bars > 0) for the base on every probed day. Both are
  supporting evidence, not proof of historical issuer identity; the Sharadar price-date interval is
  recorded beside them.
* ``UNVERIFIED``              anything else. The runner refuses a mapping that contains one; nothing is
  silently dropped and ``n`` is never reduced.

No generic suffix stripping is applied: a ticker that merely ends in digits is mapped only through
the two conditions above.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

EXIT_OK, EXIT_UNVERIFIED, EXIT_REFUSED = 0, 3, 2
SCHEMA = "range002.symbol_mapping.v1"

PROV_ALPHA = "ALPHA_TICKER_AS_IS"
PROV_CLASS = "CLASS_SHARE_PRESERVED"
PROV_SUFFIX = "SUFFIX_MAPPED_PROBE_VERIFIED"
PROV_UNVERIFIED = "UNVERIFIED"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe_evidence(probe: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in probe.get("records", []):
        out.setdefault((str(r["vendor_ticker"]), str(r["request_symbol"])), []).append(r)
    return out


def build_entries(
    symbols: list[str],
    ticker_rows: dict[str, dict[str, Any]],
    probe: dict[str, Any],
) -> list[dict[str, Any]]:
    ev = probe_evidence(probe)
    entries: list[dict[str, Any]] = []
    for s in symbols:
        row = ticker_rows.get(s, {})
        base: dict[str, Any] = {
            "vendor_ticker": s,
            "request_symbol": s,
            "asof_policy": "-",
            "provenance": PROV_UNVERIFIED,
            "evidence": {},
        }
        if re.fullmatch(r"[A-Z]+", s):
            base["provenance"] = PROV_ALPHA
        elif re.fullmatch(r"[A-Z]+\.[A-Z]", s):
            base["provenance"] = PROV_CLASS
            probed = ev.get((s, s), [])
            if probed:
                base["evidence"]["probe"] = {
                    "days": sorted({p["day"] for p in probed}),
                    "all_ok": all(p["http_status"] == 200 and (p["bars"] or 0) > 0 for p in probed),
                }
        else:
            m = re.fullmatch(r"([A-Z]+(?:\.[A-Z])?)(\d+)", s)
            if m:
                cand = m.group(1)
                related = str(row.get("relatedtickers") or "").split()
                probed = ev.get((s, cand), [])
                ok = bool(probed) and all(
                    p["http_status"] == 200 and (p["bars"] or 0) > 0 and p["symbol_echo"] == cand
                    for p in probed
                )
                base["evidence"] = {
                    "base_symbol": cand,
                    "relatedtickers_lists_base": cand in related,
                    "sharadar_price_interval": [
                        str(row.get("firstpricedate")),
                        str(row.get("lastpricedate")),
                    ],
                    "probe_days": sorted({p["day"] for p in probed}),
                    "probe_all_ok": ok,
                    "note": "supporting evidence, not proof of historical issuer identity",
                }
                if cand in related and ok:
                    base["request_symbol"] = cand
                    base["asof_policy"] = "WINDOW_START_DATE"
                    base["provenance"] = PROV_SUFFIX
        entries.append(base)
    return entries


def run(
    universe_file: Path,
    daily_dir: Path,
    table_filter: str,
    probe_json: Path,
    out: Path,
) -> int:
    import duckdb

    if out.exists():
        raise ValueError(f"{out} already exists; never overwritten")
    symbols = [
        ln.strip() for ln in universe_file.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    if len(set(symbols)) != len(symbols):
        raise ValueError("universe file lists a symbol twice")
    probe = json.loads(probe_json.read_text(encoding="utf-8"))
    con = duckdb.connect(":memory:")
    tpath = (daily_dir / "tickers.parquet").as_posix()
    rows = con.execute(
        f"SELECT ticker, relatedtickers, firstpricedate, lastpricedate "
        f"FROM read_parquet('{tpath}') WHERE \"table\" = ?",
        [table_filter],
    ).fetchall()
    con.close()
    ticker_rows = {
        r[0]: {"relatedtickers": r[1], "firstpricedate": r[2], "lastpricedate": r[3]} for r in rows
    }
    entries = build_entries(symbols, ticker_rows, probe)
    unverified = [e["vendor_ticker"] for e in entries if e["provenance"] == PROV_UNVERIFIED]
    doc = {
        "schema": SCHEMA,
        "universe_sha256": _sha(universe_file),
        "probe_sha256": _sha(probe_json),
        "table_filter": table_filter,
        "symbols": len(symbols),
        "by_provenance": {
            p: sum(1 for e in entries if e["provenance"] == p)
            for p in (PROV_ALPHA, PROV_CLASS, PROV_SUFFIX, PROV_UNVERIFIED)
        },
        "unverified": unverified,
        "entries": entries,
    }
    out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out} sha256={_sha(out)}")
    print(f"by_provenance={doc['by_provenance']}")
    if unverified:
        print(f"UNVERIFIED: {unverified}; the runner will refuse this mapping")
        return EXIT_UNVERIFIED
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--universe-file", required=True, type=Path)
    p.add_argument("--daily-dir", required=True, type=Path)
    p.add_argument("--table-filter", required=True)
    p.add_argument("--probe-json", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args(argv)
    try:
        return run(a.universe_file, a.daily_dir, a.table_filter, a.probe_json, a.out)
    except (ValueError, OSError, KeyError) as exc:
        print(f"REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
