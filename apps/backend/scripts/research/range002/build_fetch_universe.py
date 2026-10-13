#!/usr/bin/env python3
"""RANGE-002: monthly top-N fetch universe (and identity-conflict inspection) from a Sharadar export.

    python -I build_fetch_universe.py --daily-dir DIR --table-filter SEP \\
        --category-map "Domestic Common Stock" --category-map "Domestic Common Stock Primary Class" \\
        --n 100 --adv-window-days 20 --min-price 10.0 --lookback-calendar-days 45 \\
        --month-start 2016-01-01 --month-start 2016-02-01 --month-start 2016-03-01 \\
        --out-universe-file SYMBOLS.txt --out-report REPORT.json [--inspect-identity]

Purpose: decide WHICH SYMBOLS the intraday fetch must request, before any bar is fetched. It
builds each month's universe with the SAME pure builder the runner uses
(``app.research.range002.data.pit_universe.build_universe_month``) from the SAME inputs: the
identity map and listings come from ``store_adapter.load_identity_records`` / ``load_listings``
(pure, ungated), and observations come from ``observations_ungated`` below, which is the
store adapter's attribution logic reproduced for a read of the daily export only (the runner's
own ``load_observations`` is capability-gated and must not consume an attempt). A test asserts,
on a synthetic export, that the observations, listings and universe equal what the capability
path produces.

Every parameter is explicit; nothing is defaulted. The category map is a RESTRICTED category
definition taken from current-snapshot TICKERS metadata; it is not an independently verified
point-in-time category. Including a Secondary Class label is a second, explicit invocation; the
report records whether the map did.

Outputs carry symbols, ranks and counts only; no price or volume value is written or printed.
``--inspect-identity`` adds a read-only identity-conflict section (see ``inspect_identity``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import duckdb  # noqa: E402

from app.research.range002.data.identity_map import (  # noqa: E402
    RESOLVED,
    IdentityMap,
    audit_identity,
    build_identity_map,
    permaticker_on,
    ticker_on,
)
from app.research.range002.data.pit_universe import (  # noqa: E402
    AMBIGUOUS_IDENTITY,
    BASIS_SPLIT_ADJUSTED,
    INSUFFICIENT_HISTORY,
    NO_DECISION_DAY_PRINT,
    NO_IDENTITY_MAPPING,
    DailyObs,
    Listing,
    UniverseMonth,
    UniverseParams,
    build_universe_month,
)
from app.research.range002.data.store_adapter import (  # noqa: E402
    IdentityLoad,
    ObsLoad,
    SnapshotError,
    load_identity_records,
    load_listings,
    open_snapshot,
)
from app.research.range002.screen.types import SUPPORTED_INTRADAY_BASIS  # noqa: E402

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_SHORTFALL = 3  # report written; at least one month supplies fewer than N eligible names

REPORT_LABEL = "FETCH_UNIVERSE_PLANNING_NOT_A_RESULT"
SECONDARY_CLASS_LABEL = "Domestic Common Stock Secondary Class"
CATEGORY_NOTE = (
    "RESTRICTED category definition taken from current-snapshot TICKERS metadata; NOT "
    "independently verified point-in-time categories. Membership means 'category label is in "
    "this map', nothing more."
)
#: exclusion reasons that can hide an issuer that was otherwise eligible, because of identity
_IDENTITY_REASONS = (AMBIGUOUS_IDENTITY, NO_IDENTITY_MAPPING)
#: reasons a ticker-side overlap (one ticker string carrying two issuers) can induce, because the
#: ambiguous SEP rows are dropped before selection
_ATTRIBUTION_INDUCED = (NO_DECISION_DAY_PRINT, INSUFFICIENT_HISTORY)


class FetchUniverseError(Exception):
    """A precondition failed; nothing is written."""


@dataclass(frozen=True)
class MonthResult:
    month_start: date
    decision_day: date
    universe: UniverseMonth
    identity: IdentityLoad
    observations: ObsLoad
    listings: tuple[Listing, ...]
    idmap: IdentityMap


# --------------------------------------------------------------------------- the build


def prior_trading_day(con: Any, month_start: date) -> date:
    """Same rule as ``store_adapter._prior_trading_day``: latest SEP session before the month."""
    row = con.execute('SELECT MAX(date) FROM "sep" WHERE date < ?', [month_start]).fetchone()
    if row is None or row[0] is None:
        raise FetchUniverseError(f"no SEP session before {month_start}")
    return row[0]


def observations_ungated(
    con: Any, idmap: IdentityMap, *, window_start: date, decision_day: date, basis: str
) -> ObsLoad:
    """``store_adapter.load_observations`` without the capability gate (same logic, same order).

    Read-only; used only to plan the fetch. Kept line-for-line equivalent on purpose: the drift
    test compares the two on a synthetic export."""
    if basis != BASIS_SPLIT_ADJUSTED:
        raise FetchUniverseError(f"basis must be {BASIS_SPLIT_ADJUSTED!r}")
    rows = con.execute(
        'SELECT ticker, date, close, closeunadj, volume FROM "sep" WHERE date BETWEEN ? AND ?',
        [window_start, decision_day],
    ).fetchall()
    out: dict[tuple[str, date], DailyObs] = {}
    clash: set[tuple[str, date]] = set()
    unattributed = ambiguous = 0
    for ticker, day, close, close_unadj, volume in rows:
        res = permaticker_on(idmap, ticker, day)
        if res.status != RESOLVED or res.value is None:
            if res.status == "NO_MAPPING":
                unattributed += 1
            else:
                ambiguous += 1
            continue
        key = (res.value, day)
        if key in out:
            clash.add(key)
            continue
        out[key] = DailyObs(res.value, day, close, close_unadj, volume, basis)
    for key in clash:
        del out[key]
    ordered = tuple(out[k] for k in sorted(out))
    return ObsLoad(ordered, unattributed, ambiguous, len(clash))


def build_month(
    con: Any,
    month_start: date,
    params: UniverseParams,
    *,
    table_filter: str,
    lookback_calendar_days: int,
) -> MonthResult:
    if lookback_calendar_days < params.adv_window:
        raise FetchUniverseError("lookback_calendar_days is shorter than adv_window")
    has_table_col = any(
        r[0].lower() == "table"
        for r in con.execute('SELECT column_name FROM (DESCRIBE "tickers")').fetchall()
    )
    if not has_table_col:
        raise FetchUniverseError(
            "tickers has no vendor `table` column: ticker reuse is unobservable and this tool "
            "refuses to plan a universe from a collapsed table"
        )
    ident = load_identity_records(con, table_filter=table_filter)
    idmap = build_identity_map(ident.records)
    decision_day = prior_trading_day(con, month_start)
    obs = observations_ungated(
        con,
        idmap,
        window_start=decision_day - timedelta(days=lookback_calendar_days),
        decision_day=decision_day,
        basis=params.basis,
    )
    listings = load_listings(
        con, table_filter=table_filter, common_stock_categories=frozenset(params.category_map)
    )
    universe = build_universe_month(
        month_start, decision_day, listings, obs.observations, idmap, params
    )
    return MonthResult(month_start, decision_day, universe, ident, obs, listings, idmap)


def universe_symbols(months: list[MonthResult]) -> list[str]:
    return sorted({m.vendor_ticker for r in months for m in r.universe.members})


# --------------------------------------------------------------------------- report


def _ticker_label(idmap: IdentityMap, permaticker: str, day: date) -> str:
    res = ticker_on(idmap, permaticker, day)
    return res.value if res.status == RESOLVED and res.value else f"<perma:{permaticker}>"


def month_report(r: MonthResult, n: int) -> dict[str, Any]:
    u = r.universe
    by_reason = Counter(e.reason for e in u.excluded)
    # The category label as observed on each non-common-stock listing (the runner reports the
    # exclusion `detail` text; the label itself is clearer and the counts reconcile).
    cat_labels: Counter[str] = Counter()
    for li in r.listings:
        if not li.common_stock:
            cat_labels[li.category] += 1
    short = len(u.members) < n
    return {
        "month_start": r.month_start.isoformat(),
        "decision_day": r.decision_day.isoformat(),
        "population": u.population,
        "members": len(u.members),
        "below_cut": u.below_cut,
        "excluded": len(u.excluded),
        "excluded_by_reason": dict(sorted(by_reason.items())),
        "not_common_stock_by_category": dict(sorted(cat_labels.items())),
        "fewer_than_n_eligible": short,
        "shortfall": max(0, n - len(u.members)),
        "insufficient_history": sorted(
            {
                _ticker_label(r.idmap, e.permaticker, r.decision_day)
                for e in u.excluded
                if e.reason == INSUFFICIENT_HISTORY
            }
        ),
        "identity_one_row_per_ticker": r.identity.one_row_per_ticker,
        "identity_refused_rows": len(r.identity.refused),
        "unattributed_sep_rows": r.observations.unattributed_rows,
        "ambiguous_sep_rows": r.observations.ambiguous_rows,
        "duplicate_after_attribution": r.observations.duplicate_after_attribution,
        "members_ranked": [
            {"rank": m.rank, "ticker": m.vendor_ticker, "permaticker": m.permaticker}
            for m in u.members
        ],
    }


def build_report(
    months: list[MonthResult],
    params: UniverseParams,
    *,
    table_filter: str,
    lookback_calendar_days: int,
    daily_dir: Path,
    symbols: list[str],
) -> dict[str, Any]:
    files = {
        f"{t}.parquet": hashlib.sha256((daily_dir / f"{t}.parquet").read_bytes()).hexdigest()
        for t in ("tickers", "sep", "actions")
        if (daily_dir / f"{t}.parquet").is_file()
    }
    rows = [month_report(r, params.n) for r in months]
    return {
        "label": REPORT_LABEL,
        "note": "symbols, ranks and counts only; no price or volume value; not a strategy result",
        "category_definition": CATEGORY_NOTE,
        "parameters": {
            "n": params.n,
            "adv_window_days": params.adv_window,
            "min_price": params.min_price,
            "lookback_calendar_days": lookback_calendar_days,
            "table_filter": table_filter,
            "category_map": list(params.category_map),
            "basis": params.basis,
            "map_includes_secondary_class": SECONDARY_CLASS_LABEL in params.category_map,
        },
        "export_file_sha256": files,
        "months": rows,
        "months_with_fewer_than_n_eligible": sum(1 for x in rows if x["fewer_than_n_eligible"]),
        "any_month_short": any(x["fewer_than_n_eligible"] for x in rows),
        "union_size": len(symbols),
        "union_symbols": symbols,
    }


# --------------------------------------------------------------------------- identity inspection


def _month_status(r: MonthResult, permaticker: str) -> dict[str, Any]:
    u = r.universe
    for m in u.members:
        if m.permaticker == permaticker:
            return {"status": "MEMBER", "rank": m.rank, "ticker": m.vendor_ticker}
    for e in u.excluded:
        if e.permaticker == permaticker:
            return {"status": "EXCLUDED", "reason": e.reason}
    if any(li.permaticker == permaticker for li in r.listings):
        return {"status": "BELOW_CUT_OR_UNRANKED"}
    return {"status": "NOT_IN_POPULATION"}


def _affects(statuses: list[dict[str, Any]], *, ticker_side: bool) -> bool:
    sensitive = set(_IDENTITY_REASONS) | (set(_ATTRIBUTION_INDUCED) if ticker_side else set())
    for s in statuses:
        if s["status"] == "MEMBER":
            return True
        if s["status"] == "EXCLUDED" and s.get("reason") in sensitive:
            return True
    return False


def _gone(delisted: Any) -> bool:
    # same truthiness as store_adapter._is_delisted
    return delisted is not None and str(delisted).strip().upper() in ("Y", "TRUE", "T", "1")


_RULE_AFFECTED = (
    "EXPLICIT EXCLUSION REQUIRED, never silently resolved: the builder excludes the issuer in a "
    "month where more than one ticker interval contains the decision day (AMBIGUOUS_IDENTITY), "
    "and attribution drops the SEP rows of an ambiguous ticker-day. The run record must name "
    "this issuer and the months with the reason; choosing one ticker by hand is not permitted."
)
_RULE_UNAFFECTED = (
    "no eligible issuer involved in the three months; no resolution needed for this run (the "
    "overlap would still make any lookup that lands in it AMBIGUOUS_OVERLAP)"
)


def inspect_identity(con: Any, months: list[MonthResult], *, table_filter: str) -> dict[str, Any]:
    """Read-only identity-conflict inspection (counts and symbols only)."""
    ident = months[0].identity if months else load_identity_records(con, table_filter=table_filter)
    idmap = months[0].idmap if months else build_identity_map(ident.records)
    audit = audit_identity(idmap)

    detail_rows = con.execute(
        'SELECT "table", CAST(permaticker AS VARCHAR), ticker, category, firstpricedate, '
        'lastpricedate, isdelisted FROM "tickers"'
    ).fetchall()
    by_perma: dict[str, list[dict[str, Any]]] = {}
    for tbl, perma, tick, cat, first, last, delisted in detail_rows:
        by_perma.setdefault((perma or "").strip(), []).append(
            {
                "table": tbl,
                "ticker": tick,
                "category": cat,
                "first": None if first is None else first.isoformat(),
                "last": None if last is None else last.isoformat(),
                "delisted": delisted,
            }
        )

    def group(permaticker: str, kind: str, tickers: tuple[str, ...]) -> dict[str, Any]:
        side = kind.startswith("ticker")
        involved = [permaticker] if not side else list(tickers)
        # for a ticker-side conflict `permaticker` is the TICKER string and `tickers` the permas
        statuses = [
            {"month_start": r.month_start.isoformat(), "permaticker": p, **_month_status(r, p)}
            for r in months
            for p in involved
        ]
        affects = _affects(statuses, ticker_side=side)
        rows: list[dict[str, Any]] = []
        for p in involved:
            rows.extend({"permaticker": p, **x} for x in by_perma.get(p, ()))
        return {
            "kind": kind,
            "key": permaticker,
            "tickers_or_permatickers": list(tickers),
            "rows": rows,
            "month_status": statuses,
            "affects_eligible_issuer": affects,
            "resolution_rule": _RULE_AFFECTED if affects else _RULE_UNAFFECTED,
        }

    sep_conflicts = [
        group(p, "permaticker_overlap_in_" + table_filter, t) for p, t in audit.permaticker_overlaps
    ]
    ticker_conflicts = [
        group(t, "ticker_overlap_in_" + table_filter, p) for t, p in audit.ticker_overlaps
    ]

    # Across ALL vendor tables: one permaticker, different tickers, overlapping intervals.
    cross: list[dict[str, Any]] = []
    for perma, recs in sorted(by_perma.items()):
        seen_pairs: set[tuple[str, str]] = set()
        for i, a in enumerate(recs):
            for b in recs[i + 1 :]:
                if a["ticker"] == b["ticker"] or a["first"] is None or b["first"] is None:
                    continue
                a_end = a["last"] if _gone(a["delisted"]) else None
                b_end = b["last"] if _gone(b["delisted"]) else None
                if (b_end is None or a["first"] <= b_end) and (
                    a_end is None or b["first"] <= a_end
                ):
                    pair = tuple(sorted((str(a["ticker"]), str(b["ticker"]))))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)  # type: ignore[arg-type]
                    cross.append(
                        {
                            "permaticker": perma,
                            "a": a,
                            "b": b,
                            "affects_eligible_issuer": _affects(
                                [{"permaticker": perma, **_month_status(r, perma)} for r in months],
                                ticker_side=False,
                            ),
                        }
                    )
    multi_ticker_sep = sum(
        1
        for p, recs in by_perma.items()
        if len({x["ticker"] for x in recs if x["table"] == table_filter}) > 1
    )
    return {
        "table_filter": table_filter,
        "permatickers_with_more_than_one_ticker_in_table": multi_ticker_sep,
        "sequential_rename_candidates": len(audit.rename_candidates),
        "sequential_reuse_candidates": len(audit.reuse_candidates),
        "overlapping_permaticker_conflicts": sep_conflicts,
        "overlapping_ticker_conflicts": ticker_conflicts,
        "cross_table_overlapping_ticker_rows": cross,
        "any_conflict_affects_eligible_issuer": any(
            c["affects_eligible_issuer"] for c in sep_conflicts + ticker_conflicts + cross
        ),
        "note": (
            "temporal screen only: a sequential rename candidate has passed the interval check, "
            "not a verification that the vendor retro-mapped history; see identity_map.py"
        ),
    }


# --------------------------------------------------------------------------- CLI


def _iso(text: str, name: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise FetchUniverseError(f"{name} must be an ISO date: {text!r}") from exc


def run(a: argparse.Namespace) -> int:
    daily_dir: Path = a.daily_dir
    if not daily_dir.is_dir():
        raise FetchUniverseError(f"--daily-dir {daily_dir} is not a directory")
    for out in (a.out_report, a.out_universe_file):
        if out is not None and out.exists():
            raise FetchUniverseError(f"{out} already exists; never overwritten")
    if a.out_universe_file is None and not a.inspect_identity:
        raise FetchUniverseError("--out-universe-file is required unless --inspect-identity")
    if a.n <= 0 or a.adv_window_days <= 0 or a.min_price <= 0:
        raise FetchUniverseError("--n, --adv-window-days and --min-price must be positive")
    cats = tuple(dict.fromkeys(c.strip() for c in a.category_map))
    if not cats or any(not c for c in cats):
        raise FetchUniverseError("--category-map needs at least one non-empty label")
    starts = sorted({_iso(s, "--month-start") for s in a.month_start})
    if any(s.day != 1 for s in starts):
        raise FetchUniverseError("--month-start values must be first-of-month dates")
    params = UniverseParams(
        n=a.n,
        adv_window=a.adv_window_days,
        min_price=a.min_price,
        basis=BASIS_SPLIT_ADJUSTED,
        category_map=cats,
        intraday_basis=SUPPORTED_INTRADAY_BASIS,
    )
    try:
        con = open_snapshot(daily_dir)
    except SnapshotError as exc:
        raise FetchUniverseError(f"snapshot refused: {exc}") from exc
    try:
        months = [
            build_month(
                con,
                s,
                params,
                table_filter=a.table_filter,
                lookback_calendar_days=a.lookback_calendar_days,
            )
            for s in starts
        ]
        symbols = universe_symbols(months)
        report = build_report(
            months,
            params,
            table_filter=a.table_filter,
            lookback_calendar_days=a.lookback_calendar_days,
            daily_dir=daily_dir,
            symbols=symbols,
        )
        if a.inspect_identity:
            report["identity_inspection"] = inspect_identity(
                con, months, table_filter=a.table_filter
            )
    finally:
        con.close()
    a.out_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if a.out_universe_file is not None:
        a.out_universe_file.write_text("".join(f"{s}\n" for s in symbols), encoding="utf-8")
    for row in report["months"]:
        print(
            f"{row['month_start']} decision_day={row['decision_day']} population={row['population']} "
            f"members={row['members']} below_cut={row['below_cut']} excluded={row['excluded']}"
            + ("  FEWER_THAN_N" if row["fewer_than_n_eligible"] else "")
        )
    print(
        f"union_size={report['union_size']} months_short={report['months_with_fewer_than_n_eligible']}"
    )
    if a.inspect_identity:
        ins = report["identity_inspection"]
        print(
            "identity: overlapping_permaticker_conflicts="
            f"{len(ins['overlapping_permaticker_conflicts'])} ticker_conflicts="
            f"{len(ins['overlapping_ticker_conflicts'])} cross_table={len(ins['cross_table_overlapping_ticker_rows'])} "
            f"affects_eligible_issuer={ins['any_conflict_affects_eligible_issuer']}"
        )
    return EXIT_SHORTFALL if report["any_month_short"] else EXIT_OK


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    r = p.add_argument
    r("--daily-dir", required=True, type=Path)
    r("--table-filter", required=True)
    r("--category-map", required=True, action="append")
    r("--n", required=True, type=int)
    r("--adv-window-days", required=True, type=int)
    r("--min-price", required=True, type=float)
    r("--lookback-calendar-days", required=True, type=int)
    r("--month-start", required=True, action="append")
    r("--out-report", required=True, type=Path)
    r("--out-universe-file", type=Path, default=None)
    r("--inspect-identity", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    try:
        return run(a)
    except (FetchUniverseError, duckdb.Error, ValueError) as exc:
        print(f"REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
