"""Refresh-universe construction and per-name staleness verification.

Extracted from the inline heredocs in ``deploy/aws/factor-refresh.sh`` so the two
decisions that silently mis-allocate capital are testable.

Two defects motivated this, both found 2026-08-03:

**The refresh universe was the wrong set.** It was the union of ``symbols_json``
over ``status='PAPER'`` strategies. But a factor book does not rank over its own
registered list — ``combined_book_v13`` calls
``ctx.factors.momentum_scores(n=len(ctx.symbols))``, which resolves to
``universe_asof(store, as_of, n)`` → ``dollar_volume_universe``: the top-*n*
tickers **store-wide** by trailing dollar volume. The registered list is applied
afterwards as a filter. So names that are not registered by any strategy still
determine which registered names survive the cut, and those names were never
refreshed. Worse, ``dollar_volume_universe`` requires ``lastpricedate >= as_of``,
so a stale name is *silently dropped from the ranking pool* rather than ranked on
old data — which is how 301 of 500 names sat frozen at 2026-07-06 while every
readiness gate reported green.

**IDLE strategies contributed nothing.** The ``status='PAPER'`` filter meant a
strategy held pending activation supplied no symbols, so its universe went stale
exactly while it waited to be activated — and could never reach a green readiness
gate. That is a chicken-and-egg, not a tuning problem.

**And freshness was read as ``max(date)``.** A single fresh ticker keeps
``max(lastpricedate)`` current while most of the pool is frozen. Staleness is
per-day-per-name or it is not measured at all.

Nothing here imports the app package: this runs in a one-off container against the
raw stores, exactly as the shell job does.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

# Mirrors app.factor_data.universe. Duplicated deliberately: this module must not
# import the app package (it runs against raw stores in a minimal container), and
# a drift test pins the two together.
DEFAULT_UNIVERSE_SIZE = 500
DEFAULT_LOOKBACK_DAYS = 63

#: Ranking-pool headroom. Universe membership churns day to day, and today's pool
#: is computed from yesterday's store, so refresh a superset of what will be
#: ranked tomorrow.
DEFAULT_HEADROOM = 1.5

#: A liquid top-N name trades every session, so tolerate only a long weekend.
DEFAULT_MAX_LAG_DAYS = 4

#: Fraction of the ranking pool that must be current. Not 1.0: a name may halt or
#: delist legitimately between the pool being computed and the refresh landing.
DEFAULT_MIN_COVERAGE = 0.98


class RefreshError(RuntimeError):
    """Universe construction or staging verification failed."""


# --------------------------------------------------------------- universe


def registered_symbols(app_db: str | Path) -> dict[str, list[str]]:
    """Every strategy's registered symbol list, keyed by ``"<id>:<status>"``.

    **No status filter.** The previous ``status='PAPER'`` filter is the IDLE
    chicken-and-egg described in the module docstring. A strategy pending
    activation must have fresh data *before* it is activated, not after. The cost
    of over-inclusion is a few hundred extra tickers on a pull already dominated
    by the ranking pool; the cost of under-inclusion is a silent allocation bug.
    """
    con = sqlite3.connect(f"file:{app_db}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT id, status, symbols_json FROM strategies").fetchall()
    finally:
        con.close()

    out: dict[str, list[str]] = {}
    for sid, status, raw in rows:
        try:
            syms = json.loads(raw or "[]")
        except (TypeError, ValueError):
            continue
        out[f"{sid}:{status}"] = sorted({str(s).upper() for s in syms if s})
    return out


def held_symbols(app_db: str | Path) -> list[str]:
    """Symbols currently held in any account.

    A held name must stay priceable even after it rotates out of the ranking
    pool, or the book cannot mark it — or exit it. This is the same class of
    defect as the v1.3 parity run-1 failure, where a holding outside the PIT
    universe was invisible to ``_current_holdings`` and its exit was missed.
    """
    con = sqlite3.connect(f"file:{app_db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            """
            SELECT DISTINCT sym.symbol
            FROM positions p
            JOIN symbols sym ON sym.id = p.symbol_id
            WHERE p.qty <> 0
            """
        ).fetchall()
    except sqlite3.Error as exc:  # pragma: no cover - schema drift guard
        raise RefreshError(f"cannot read held positions: {exc}") from exc
    finally:
        con.close()
    return sorted({str(r[0]).upper() for r in rows if r[0]})


def required_pool_size(
    registered: dict[str, list[str]],
    *,
    headroom: float = DEFAULT_HEADROOM,
    floor: int = DEFAULT_UNIVERSE_SIZE,
) -> int:
    """How deep the dollar-volume ranking pool must be refreshed.

    A book passes ``n = len(ctx.symbols)`` to ``momentum_scores``, so the deepest
    pool any strategy will ask for is the largest registered list. Refresh that
    times ``headroom`` (membership churns), never below ``floor`` (the app's
    ``DEFAULT_UNIVERSE_SIZE``, used whenever a caller passes no ``n``).
    """
    if headroom < 1.0:
        raise ValueError("headroom must be >= 1.0")
    largest = max((len(v) for v in registered.values()), default=0)
    return max(floor, math.ceil(largest * headroom))


def ranking_pool(
    store_path: str | Path,
    as_of: date,
    *,
    n: int,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[str]:
    """Top-``n`` tickers by trailing dollar volume — the set books actually rank.

    Mirrors ``FactorDataStore.dollar_volume_universe``. Deliberately does **not**
    apply the ``lastpricedate >= as_of`` eligibility filter that the production
    query uses: this is the set we want to *make* fresh, and filtering on
    freshness here would exclude exactly the stale names we are trying to repair.
    """
    import duckdb

    con = duckdb.connect(str(store_path), read_only=True)
    try:
        window_start = as_of - timedelta(days=lookback_days)
        rows = con.execute(
            """
            SELECT ticker
            FROM (
                SELECT ticker, SUM(close * volume) AS dv
                FROM sep
                WHERE date BETWEEN ? AND ?
                GROUP BY ticker
            )
            WHERE dv > 0
            ORDER BY dv DESC, ticker ASC
            LIMIT ?
            """,
            [window_start, as_of, n],
        ).fetchall()
    finally:
        con.close()
    return [r[0] for r in rows]


def build_refresh_universe(
    app_db: str | Path,
    store_path: str | Path,
    as_of: date,
    *,
    headroom: float = DEFAULT_HEADROOM,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    extra: Iterable[str] = (),
) -> dict[str, Any]:
    """The set of tickers the daily refresh must ingest, with its provenance."""
    registered = registered_symbols(app_db)
    held = held_symbols(app_db)
    pool_n = required_pool_size(registered, headroom=headroom)
    pool = ranking_pool(store_path, as_of, n=pool_n, lookback_days=lookback_days)

    reg_union = sorted({s for v in registered.values() for s in v})
    extras = sorted({str(s).upper() for s in extra if s})
    universe = sorted(set(pool) | set(reg_union) | set(held) | set(extras))

    if not universe:
        raise RefreshError(
            "refresh universe is EMPTY — refusing to ingest nothing "
            "(an empty pull silently freezes every book)"
        )

    return {
        "as_of": as_of.isoformat(),
        "universe": universe,
        "counts": {
            "total": len(universe),
            "ranking_pool": len(pool),
            "ranking_pool_requested": pool_n,
            "registered_union": len(reg_union),
            "held": len(held),
            "extra": len(extras),
            "registered_not_in_pool": len(set(reg_union) - set(pool)),
            "held_not_in_pool": len(set(held) - set(pool)),
        },
        "strategies": {k: len(v) for k, v in sorted(registered.items())},
    }


# ----------------------------------------------------------- verification


def _duck(path: str | Path):
    import duckdb

    return duckdb.connect(str(path), read_only=True)


def _scalar(con, sql: str):
    try:
        row = con.execute(sql).fetchone()
    except Exception:  # noqa: BLE001 - table may be absent in a partial store
        return None
    return row[0] if row else None


def per_name_staleness(
    store_path: str | Path,
    universe: Sequence[str],
    *,
    max_lag_days: int = DEFAULT_MAX_LAG_DAYS,
) -> dict[str, Any]:
    """Per-day-per-name freshness of ``universe`` against the store's own max date.

    ``max(date)`` over the whole table is not a freshness measure — one current
    ticker masks an arbitrarily stale remainder. This reports, per name, the last
    SEP date and the ``tickers.lastpricedate``, and counts how many are behind the
    store's own frontier by more than ``max_lag_days``.

    ``lastpricedate`` is reported separately because ``dollar_volume_universe``
    filters on it: a name whose ``lastpricedate`` lags is *excluded from the
    ranking pool entirely*, which is strictly worse than being ranked on old data.
    """
    con = _duck(store_path)
    try:
        frontier = _scalar(con, "SELECT max(date) FROM sep")
        if frontier is None:
            raise RefreshError("store has no SEP rows; cannot assess staleness")
        if hasattr(frontier, "date"):
            frontier = frontier.date()
        cutoff = frontier - timedelta(days=max_lag_days)

        placeholders = ",".join("?" * len(universe))
        sep_rows = con.execute(
            f"SELECT ticker, max(date) FROM sep WHERE ticker IN ({placeholders}) "  # noqa: S608
            "GROUP BY ticker",
            list(universe),
        ).fetchall()
        try:
            lpd_rows = con.execute(
                f"SELECT ticker, lastpricedate FROM tickers WHERE ticker IN ({placeholders})",  # noqa: S608
                list(universe),
            ).fetchall()
        except Exception:  # noqa: BLE001 - tickers table absent
            lpd_rows = []
    finally:
        con.close()

    def _d(v):
        return v.date() if hasattr(v, "date") else v

    sep_max = {t: _d(d) for t, d in sep_rows if d is not None}
    lpd = {t: _d(d) for t, d in lpd_rows if d is not None}

    missing = sorted(set(universe) - set(sep_max))
    stale = sorted(t for t, d in sep_max.items() if d < cutoff)
    lpd_stale = sorted(t for t in universe if t in lpd and lpd[t] < cutoff)
    lpd_missing = sorted(t for t in universe if t not in lpd)

    covered = len(universe) - len(missing) - len(stale)
    return {
        "frontier": frontier.isoformat(),
        "cutoff": cutoff.isoformat(),
        "universe_size": len(universe),
        "covered": covered,
        "coverage": (covered / len(universe)) if universe else 0.0,
        "missing": missing,
        "stale": stale,
        "lastpricedate_stale": lpd_stale,
        "lastpricedate_missing": lpd_missing,
    }


def verify_staging(
    live_path: str | Path,
    stage_path: str | Path,
    universe: Sequence[str],
    *,
    max_lag_days: int = DEFAULT_MAX_LAG_DAYS,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> tuple[list[str], dict[str, Any]]:
    """Gate the staging store before the swap. Returns ``(failures, report)``.

    Keeps the original global regression checks — they catch a truncated or
    rolled-back pull — and adds the per-name coverage the ``max(date)`` checks
    could not see.
    """
    failures: list[str] = []
    live, stage = _duck(live_path), _duck(stage_path)
    try:
        l_sep = _scalar(live, "SELECT max(date) FROM sep")
        s_sep = _scalar(stage, "SELECT max(date) FROM sep")
        l_tk = _scalar(live, "SELECT count(DISTINCT ticker) FROM sep")
        s_tk = _scalar(stage, "SELECT count(DISTINCT ticker) FROM sep")
        s_lpd = _scalar(stage, "SELECT max(lastpricedate) FROM tickers")
    finally:
        live.close()
        stage.close()

    if s_sep is None:
        failures.append("staging sep is EMPTY")
    elif l_sep is not None and s_sep < l_sep:
        failures.append(f"sep_max REGRESSED {l_sep}->{s_sep}")
    if s_tk is not None and l_tk and s_tk < 0.9 * l_tk:
        failures.append(f"ticker count dropped {l_tk}->{s_tk} (>10%)")
    if s_lpd is not None and s_sep is not None and s_lpd < s_sep:
        failures.append(
            f"tickers.lastpricedate {s_lpd} BEHIND sep {s_sep} "
            "-> PIT universe would EMPTY (books HOLD)"
        )

    report: dict[str, Any] = {
        "global": {
            "live_sep_max": str(l_sep),
            "stage_sep_max": str(s_sep),
            "live_tickers": l_tk,
            "stage_tickers": s_tk,
            "stage_lastpricedate_max": str(s_lpd),
        }
    }

    if s_sep is not None and universe:
        st = per_name_staleness(stage_path, universe, max_lag_days=max_lag_days)
        report["per_name"] = st
        if st["coverage"] < min_coverage:
            failures.append(
                f"per-name coverage {st['coverage']:.4f} < {min_coverage} "
                f"({len(st['missing'])} missing, {len(st['stale'])} stale "
                f"beyond {max_lag_days}d; e.g. "
                f"{(st['missing'] + st['stale'])[:8]})"
            )
        if st["lastpricedate_stale"]:
            failures.append(
                f"{len(st['lastpricedate_stale'])} universe tickers have a stale "
                f"tickers.lastpricedate -> they are EXCLUDED from the ranking pool "
                f"(e.g. {st['lastpricedate_stale'][:8]})"
            )

    return failures, report


# ------------------------------------------------------------------- cli


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="mode", required=True)

    u = sub.add_parser("universe", help="write the refresh universe file")
    u.add_argument("--app-db", required=True)
    u.add_argument("--store", required=True)
    u.add_argument("--as-of", required=True)
    u.add_argument("--out", required=True)
    u.add_argument("--report")
    u.add_argument("--headroom", type=float, default=DEFAULT_HEADROOM)
    u.add_argument("--extra", default="", help="comma-separated always-include tickers")

    v = sub.add_parser("verify", help="gate the staging store before the swap")
    v.add_argument("--live", required=True)
    v.add_argument("--stage", required=True)
    v.add_argument("--universe", required=True, help="the universe file")
    v.add_argument("--report")
    v.add_argument("--max-lag-days", type=int, default=DEFAULT_MAX_LAG_DAYS)
    v.add_argument("--min-coverage", type=float, default=DEFAULT_MIN_COVERAGE)

    args = ap.parse_args(argv)

    try:
        if args.mode == "universe":
            res = build_refresh_universe(
                args.app_db,
                args.store,
                date.fromisoformat(args.as_of),
                headroom=args.headroom,
                extra=[s for s in args.extra.split(",") if s.strip()],
            )
            Path(args.out).write_text("\n".join(res["universe"]), encoding="utf-8")
            if args.report:
                Path(args.report).write_text(json.dumps(res, indent=2), encoding="utf-8")
            print(f"refresh universe: {res['counts']}")
            return 0

        universe = [
            ln.strip()
            for ln in Path(args.universe).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        failures, report = verify_staging(
            args.live,
            args.stage,
            universe,
            max_lag_days=args.max_lag_days,
            min_coverage=args.min_coverage,
        )
        if args.report:
            Path(args.report).write_text(
                json.dumps(report, indent=2, default=str), encoding="utf-8"
            )
        print(f"verify: {json.dumps(report['global'], default=str)}")
        if "per_name" in report:
            pn = report["per_name"]
            print(
                f"verify: per-name coverage {pn['coverage']:.4f} "
                f"({pn['covered']}/{pn['universe_size']}) frontier={pn['frontier']}"
            )
        if failures:
            print("VERIFY_FAILED: " + "; ".join(failures))
            return 1
        print("VERIFY_OK")
        return 0
    except RefreshError as exc:
        print(f"VERIFY_FAILED: {exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
