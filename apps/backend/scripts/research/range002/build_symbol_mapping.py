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
* ``HISTORICAL_SYMBOL_ACTIONS_CHAIN``  the vendor's daily ``ticker`` is the CURRENT, retro-mapped
  symbol (``META`` for a company that traded as ``FB`` in 2016). The symbol as of a date is derived
  from the vendor's own ACTIONS ``tickerchangefrom`` rows (ticker = new symbol, contraticker = old
  symbol, date = change date) by walking backwards from the vendor ticker over every change dated
  AFTER the as-of date. A change dated INSIDE the requested window makes the symbol ambiguous for
  that window and the entry is ``UNVERIFIED`` (refused), never guessed.
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
PROV_SUFFIX = "SUFFIX_MAPPED_PROBE_VERIFIED"  # superseded by the chain (kept for old files)
PROV_CHAIN = "HISTORICAL_SYMBOL_ACTIONS_CHAIN"
PROV_UNVERIFIED = "UNVERIFIED"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def historical_symbol(
    ticker: str,
    asof: str,
    events: dict[str, list[tuple[str, str]]],
    window_end: str | None = None,
) -> tuple[str, list[str], bool]:
    """(symbol as of ``asof``, chain of symbols walked, change_inside_window).

    ``events[new_symbol]`` lists ``(YYYY-MM-DD, old_symbol)`` for every ``tickerchangefrom`` row
    (ticker = new symbol, contraticker = old symbol). Walk backwards over the nearest change dated
    after ``asof``; repeat from the old symbol using only changes dated before the one just
    undone. ``change_inside_window`` is True when any change used lies in (asof, window_end]."""
    sym = ticker
    chain = [ticker]
    bound = "9999-12-31"
    inside = False
    while True:
        cand = sorted(
            (d, old)
            for d, old in events.get(sym, [])
            if asof < d < bound and old and old != "N/A" and old != sym
        )
        if not cand:
            break
        d, old = cand[0]  # the nearest change AFTER asof
        if window_end is not None and d <= window_end:
            inside = True
        bound = d
        sym = old
        chain.append(sym)
        if len(chain) > 8:
            break
    return sym, chain, inside


def symbol_schedule(
    ticker: str,
    date_from: str,
    date_to: str,
    events: dict[str, list[tuple[str, str]]],
) -> list[tuple[str, str]]:
    """Dated request-symbol schedule for ``ticker`` over [date_from, date_to].

    First entry: the symbol as of ``date_from``. Each further entry is the symbol the company took
    on a change date INSIDE the window (ascending). Built only from the vendor's ACTIONS
    ``tickerchangefrom`` rows; nothing is inferred from the spelling of the ticker."""
    sym = ticker
    bound = "9999-12-31"
    transitions: list[tuple[str, str]] = []  # (change date, symbol FROM that date)
    for _ in range(8):
        cand = sorted(
            (d, old)
            for d, old in events.get(sym, [])
            if date_from < d < bound and old and old not in ("N/A", sym)
        )
        if not cand:
            break
        d, old = cand[0]
        if d <= date_to:
            transitions.append((d, sym))
        bound, sym = d, old
    return [(date_from, sym), *sorted(transitions)]


def probe_evidence(probe: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in probe.get("records", []):
        out.setdefault((str(r["vendor_ticker"]), str(r["request_symbol"])), []).append(r)
    return out


def _probe_ok(recs: list[dict[str, Any]], symbol: str) -> bool:
    return bool(recs) and all(
        r["http_status"] == 200 and (r["bars"] or 0) > 0 and r["symbol_echo"] == symbol
        for r in recs
    )


def build_entries(
    symbols: list[str],
    ticker_rows: dict[str, dict[str, Any]],
    probe: dict[str, Any],
    events: dict[str, list[tuple[str, str]]],
    date_from: str,
    date_to: str,
) -> list[dict[str, Any]]:
    ev = probe_evidence(probe)
    entries: list[dict[str, Any]] = []
    for s in symbols:
        row = ticker_rows.get(s, {})
        sched = symbol_schedule(s, date_from, date_to, events)
        schedule = [{"from": d, "request_symbol": sym} for d, sym in sched]
        base: dict[str, Any] = {
            "vendor_ticker": s,
            "request_symbol": sched[0][1],
            "schedule": schedule,
            "asof_policy": "-",
            "provenance": PROV_UNVERIFIED,
            "evidence": {
                "relatedtickers": str(row.get("relatedtickers") or ""),
                "sharadar_price_interval": [
                    str(row.get("firstpricedate")),
                    str(row.get("lastpricedate")),
                ],
            },
        }
        changed = len(sched) > 1 or sched[0][1] != s
        if changed:
            # the vendor's ticker is the CURRENT symbol; the company traded under another one in
            # the window. Every scheduled symbol needs its own successful return-blind probe.
            checks = {sym: _probe_ok(ev.get((s, sym), []), sym) for _, sym in sched}
            base["evidence"]["chain_note"] = (
                "vendor ACTIONS tickerchangefrom history; supporting evidence, not proof of "
                "historical issuer identity"
            )
            base["evidence"]["probe_ok_by_symbol"] = checks
            base["asof_policy"] = "SEGMENT_START_DATE"
            if all(checks.values()):
                base["provenance"] = PROV_CHAIN
        elif re.fullmatch(r"[A-Z]+", s):
            base["provenance"] = PROV_ALPHA
        elif re.fullmatch(r"[A-Z]+\.[A-Z]", s):
            base["provenance"] = PROV_CLASS
            probed = ev.get((s, s), [])
            if probed:
                base["evidence"]["probe"] = {
                    "days": sorted({p["day"] for p in probed}),
                    "all_ok": _probe_ok(probed, s),
                }
        entries.append(base)
    return entries


def load_events(daily_dir: Path) -> dict[str, list[tuple[str, str]]]:
    import duckdb

    con = duckdb.connect(":memory:")
    path = (daily_dir / "actions.parquet").as_posix()
    rows = con.execute(
        f"SELECT CAST(date AS VARCHAR), ticker, contraticker FROM read_parquet('{path}') "
        "WHERE action = 'tickerchangefrom'"
    ).fetchall()
    con.close()
    events: dict[str, list[tuple[str, str]]] = {}
    for d, t, old in rows:
        if t and old:
            events.setdefault(str(t), []).append((str(d), str(old)))
    return events


def run(
    universe_file: Path,
    daily_dir: Path,
    table_filter: str,
    probe_json: Path,
    out: Path,
    date_from: str,
    date_to: str,
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
    entries = build_entries(symbols, ticker_rows, probe, load_events(daily_dir), date_from, date_to)
    unverified = [e["vendor_ticker"] for e in entries if e["provenance"] == PROV_UNVERIFIED]
    doc = {
        "schema": SCHEMA,
        "universe_sha256": _sha(universe_file),
        "probe_sha256": _sha(probe_json),
        "table_filter": table_filter,
        "date_from": date_from,
        "date_to": date_to,
        "symbols": len(symbols),
        "by_provenance": {
            p: sum(1 for e in entries if e["provenance"] == p)
            for p in (PROV_ALPHA, PROV_CLASS, PROV_CHAIN, PROV_UNVERIFIED)
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
    p.add_argument("--date-from", required=True)
    p.add_argument("--date-to", required=True)
    a = p.parse_args(argv)
    try:
        return run(
            a.universe_file,
            a.daily_dir,
            a.table_filter,
            a.probe_json,
            a.out,
            a.date_from,
            a.date_to,
        )
    except (ValueError, OSError, KeyError) as exc:
        print(f"REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
