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
import hashlib
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


#: Absolute ceiling on the refresh universe, tied to provider and host capacity.
#: Growth beyond this is a stop, never a raise-the-limit-in-place.
DEFAULT_MAX_UNIVERSE = 2000

#: Growth beyond this fraction of the prior sealed run is reported for review.
#: It does not fail on its own — a newly registered strategy or a new holding can
#: legitimately expand the set — but it must be explained by component attribution.
DEFAULT_GROWTH_REVIEW = 0.25


class RefreshError(RuntimeError):
    """Universe construction or staging verification failed."""


def digest(symbols: Iterable[str]) -> str:
    """Canonical SHA-256 over a symbol set.

    Sorted, uppercased, newline-joined. Always reported *with* its count: a digest
    alone cannot reveal whether a malformed serialisation dropped or duplicated
    entries, and two different sets must never be able to present as one.
    """
    canonical = "\n".join(sorted({str(s).strip().upper() for s in symbols if str(s).strip()}))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------- universe


def registered_symbols(app_db: str | Path) -> dict[str, list[str]]:
    """Every strategy's registered symbol list, keyed by ``"<id>:<status>"``.

    **No status filter.** The previous ``status='PAPER'`` filter is the IDLE
    chicken-and-egg described in the module docstring. A strategy pending
    activation must have fresh data *before* it is activated, not after. The cost
    of over-inclusion is a few hundred extra tickers on a pull already dominated
    by the ranking pool; the cost of under-inclusion is a silent allocation bug.

    Malformed metadata **fails the refresh**; it is never skipped. A silently
    omitted strategy drops out of the safety union, its names go stale, and the
    allocation bug is invisible — the exact failure class this module exists to
    prevent. Errors name the strategy but never echo the raw value, which may be
    large or hold data that does not belong in a log.
    """
    con = sqlite3.connect(f"file:{app_db}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT id, status, symbols_json FROM strategies").fetchall()
    finally:
        con.close()

    out: dict[str, list[str]] = {}
    for sid, status, raw in rows:
        identity = f"{sid}:{status}"

        if raw is None:
            raise RefreshError(f"strategy {identity}: symbols_json is NULL")
        if not isinstance(raw, str) or not raw.strip():
            raise RefreshError(f"strategy {identity}: symbols_json is empty or non-text")

        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise RefreshError(f"strategy {identity}: symbols_json is invalid JSON") from exc

        # A JSON object would iterate its KEYS and yield plausible-but-wrong
        # symbols with no error at all, which is worse than omission because
        # nothing signals it. A scalar would raise an unattributed TypeError.
        if not isinstance(parsed, list):
            raise RefreshError(
                f"strategy {identity}: symbols_json must be a JSON array, "
                f"got {type(parsed).__name__}"
            )
        if not parsed:
            raise RefreshError(f"strategy {identity}: symbols_json is an empty array")

        normalized: set[str] = set()
        for index, item in enumerate(parsed):
            if not isinstance(item, str):
                raise RefreshError(
                    f"strategy {identity}: symbols_json[{index}] must be a string, "
                    f"got {type(item).__name__}"
                )
            symbol = item.strip().upper()
            if not symbol:
                raise RefreshError(f"strategy {identity}: symbols_json[{index}] is blank")
            normalized.add(symbol)

        out[identity] = sorted(normalized)
    return out


def held_symbols(app_db: str | Path) -> list[str]:
    """Symbols currently held in any account.

    ⚠ The column is ``symbols.ticker`` — see ``app/db/models/symbol.py``. An earlier
    ``sym.symbol`` aborted the 2026-08-04 production recovery with
    "no such column: sym.symbol"; the unit test had invented a fixture schema that
    matched the query instead of the database.

    A held name must stay priceable even after it rotates out of the ranking
    pool, or the book cannot mark it — or exit it. This is the same class of
    defect as the v1.3 parity run-1 failure, where a holding outside the PIT
    universe was invisible to ``_current_holdings`` and its exit was missed.
    """
    con = sqlite3.connect(f"file:{app_db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            """
            SELECT DISTINCT sym.ticker
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
        # Every digest is paired with its count. A digest alone cannot show that a
        # malformed serialisation dropped or duplicated entries.
        "digests": {
            "ranking_pool": {"sha256": digest(pool), "count": len(pool)},
            "registered_union": {"sha256": digest(reg_union), "count": len(reg_union)},
            "held_symbols": {"sha256": digest(held), "count": len(held)},
            "final_refresh_universe": {"sha256": digest(universe), "count": len(universe)},
        },
        # The component sets themselves, so a later reader can re-derive the union
        # and attribute every member. Without these, "unexplained growth" is not
        # checkable — the union is trivially explained by its own definition.
        "components": {
            "ranking_pool": pool,
            "registered_union": reg_union,
            "held": held,
            "extra": extras,
        },
        "strategies": {k: len(v) for k, v in sorted(registered.items())},
    }


def attribute(universe_doc: dict[str, Any]) -> dict[str, list[str]]:
    """Map each universe member to the components that contributed it.

    This is the integrity check behind "unexplained growth": the universe must be
    exactly the union of its recorded components. A member belonging to none of
    them means the artifact was produced by something other than the authorized
    formula, or was altered after the fact.
    """
    comps = universe_doc["components"]
    sets = {name: set(values) for name, values in comps.items()}
    union = set().union(*sets.values()) if sets else set()
    universe = set(universe_doc["universe"])

    orphans = sorted(universe - union)
    if orphans:
        raise RefreshError(
            f"{len(orphans)} universe members belong to no recorded component "
            f"(first: {orphans[0]}) — the universe is not the union of its components"
        )
    missing = sorted(union - universe)
    if missing:
        raise RefreshError(
            f"{len(missing)} component members are absent from the universe "
            f"(first: {missing[0]}) — the union was not applied faithfully"
        )

    return {sym: sorted(n for n, s in sets.items() if sym in s) for sym in sorted(universe)}


def growth_control(
    current: dict[str, Any],
    prior: dict[str, Any] | None,
    *,
    max_universe: int = DEFAULT_MAX_UNIVERSE,
    review_threshold: float = DEFAULT_GROWTH_REVIEW,
) -> dict[str, Any]:
    """Compare a universe against the last **sealed successful** run.

    ``prior`` is the last sealed success, never the last attempt: a failed refresh
    must not become the anchor, or one bad run silently re-baselines the control.

    The first run has no prior. It records a baseline rather than computing growth
    against zero — a relative delta against an absent or zero prior is undefined,
    and dividing by it would fail the bootstrap for no reason.
    """
    total = current["counts"]["total"]
    if total > max_universe:
        raise RefreshError(
            f"refresh universe {total} exceeds the absolute ceiling {max_universe}; "
            "this is a stop, not an occasion to raise the ceiling"
        )

    if prior is None:
        return {
            "state": "BOOTSTRAP_BASELINE_RECORDED",
            "prior_count": None,
            "current_count": total,
            "absolute_delta": None,
            "relative_delta": None,
            "requires_review": False,
        }

    prior_count = prior["counts"]["total"]
    prior_syms = set(prior["universe"])
    current_syms = set(current["universe"])
    added = sorted(current_syms - prior_syms)
    removed = sorted(prior_syms - current_syms)

    # Fail closed when growth cannot be explained. `attribute` raises if any
    # member belongs to no recorded component; here we additionally record which
    # component each ADDED name came from, so an operator reviewing an expansion
    # sees its cause rather than just its size.
    by_component = attribute(current)
    added_by_component: dict[str, int] = {}
    for sym in added:
        for comp in by_component[sym]:
            added_by_component[comp] = added_by_component.get(comp, 0) + 1

    absolute = total - prior_count
    relative = (absolute / prior_count) if prior_count else None

    return {
        "state": "COMPARATIVE_GROWTH_CONTROL_ACTIVE",
        "prior_count": prior_count,
        "current_count": total,
        "absolute_delta": absolute,
        "relative_delta": relative,
        "added_symbols": {"sha256": digest(added), "count": len(added)},
        "removed_symbols": {"sha256": digest(removed), "count": len(removed)},
        "component_attribution": added_by_component,
        "requires_review": bool(relative is not None and relative > review_threshold),
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

    # The ranking pool filters on `lastpricedate`, so a name with fresh SEP but a
    # lagging lastpricedate is still excluded from it. The EFFECTIVE freshness of a
    # name is therefore the earlier of the two — otherwise a stale lastpricedate
    # would be invisible to any check that only looks at SEP.
    effective: dict[str, Any] = {}
    for tkr in universe:
        parts = [d for d in (sep_max.get(tkr), lpd.get(tkr)) if d is not None]
        effective[tkr] = min(parts) if parts else None

    return {
        "sep_max_by_symbol": {k: str(v) for k, v in sep_max.items()},
        "lastpricedate_by_symbol": {k: str(v) for k, v in lpd.items()},
        "effective_last_by_symbol": {k: (str(v) if v else None) for k, v in effective.items()},
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


# ------------------------------------------------- stale-symbol classification

#: A universe symbol's freshness verdict at verification time.
FRESH = "FRESH"
PROVIDER_EXHAUSTED = "PROVIDER_EXHAUSTED"
PROVIDER_NOT_COVERED = "PROVIDER_NOT_COVERED"
FAILED_OR_UNEXPLAINED = "FAILED_OR_UNEXPLAINED"

#: Verdicts that are attributable — a refresh can never make them fresh HERE, and
#: each carries per-symbol evidence saying why. They are never counted as fresh.
ATTRIBUTED = (PROVIDER_EXHAUSTED, PROVIDER_NOT_COVERED)


def classify_stale_symbol(
    symbol: str,
    *,
    live_last: date | None,
    stage_last: date | None,
    cutoff: date,
    evidence: dict[str, Any] | None,
    held_qty: float,
    open_orders: int,
    registered_in: Sequence[str],
) -> tuple[str, str]:
    """Classify one non-fresh universe symbol. Pure: no I/O, provider or store.

    Two distinct reasons a symbol can never be made fresh by this provider, and
    the alternate source is what tells them apart:

    ``PROVIDER_EXHAUSTED``    the instrument stopped trading — the alternate
                              source stops too (a delisting, merger or rename).
    ``PROVIDER_NOT_COVERED``  the instrument trades normally but is outside this
                              provider's subscription — the alternate source is
                              current (e.g. ETFs under a Core US Equities plan
                              that excludes the fund price dataset).

    Everything else is ``FAILED_OR_UNEXPLAINED``.

    ⚠ "the provider returned nothing newer" is NOT sufficient on its own — it
    equally describes a transient outage, a malformed response, an omitted
    request, an entitlement problem or a symbol-specific ingestion bug. Every
    condition must hold in the same governed run; anything unproven fails closed.

    ``evidence`` supplies only what verification cannot observe for itself: the
    per-symbol request outcome and an independent lifecycle signal. Frontiers,
    holdings and registration are recomputed by the caller and cross-checked
    here, never taken on trust.
    """
    if stage_last is not None and stage_last >= cutoff:
        return FRESH, "stage frontier is within tolerance"

    # --- the request itself must be proven to have happened and succeeded ---
    if not evidence:
        return FAILED_OR_UNEXPLAINED, "no exhaustion evidence supplied"
    if evidence.get("symbol") != symbol:
        return FAILED_OR_UNEXPLAINED, "evidence symbol mismatch"
    if evidence.get("requested") is not True:
        return FAILED_OR_UNEXPLAINED, "symbol was not requested from the provider"
    if evidence.get("request_status") != "ok":
        return FAILED_OR_UNEXPLAINED, f"provider request status {evidence.get('request_status')!r}"
    rows = evidence.get("provider_rows_after_live_frontier")
    if rows is None:
        return FAILED_OR_UNEXPLAINED, "provider row count after frontier not reported"
    if rows != 0:
        return (
            FAILED_OR_UNEXPLAINED,
            f"provider returned {rows} newer row(s); ingestion missed them",
        )
    if stage_last != live_last:
        return FAILED_OR_UNEXPLAINED, f"staging frontier {stage_last} != live {live_last}"

    # --- an independent source must be reachable and current ---------------
    corr = evidence.get("corroboration") or {}
    for field in ("source", "control_symbol", "control_last_date"):
        if not corr.get(field):
            return FAILED_OR_UNEXPLAINED, f"corroboration missing {field}"
    c_ctl = _as_date(corr["control_last_date"])
    if c_ctl is None or c_ctl < cutoff:
        # A stale control proves the alternate path is broken, not that the
        # subject symbol is dead. Without it every symbol would look attributable
        # during an outage of the corroborating source.
        return (
            FAILED_OR_UNEXPLAINED,
            "corroboration control is not current; alternate source unproven",
        )
    c_last = _as_date(corr.get("last_date"))

    alive_elsewhere = c_last is not None and c_last >= cutoff

    # --- operational requirements -----------------------------------------
    # A held name needs a continuing valuation and exit path. That is satisfied
    # only when the alternate source is currently pricing it.
    if (held_qty or open_orders) and not alive_elsewhere:
        need = f"held qty {held_qty}" if held_qty else f"{open_orders} open order(s)"
        return FAILED_OR_UNEXPLAINED, f"{need} with no proven alternate price source"
    if registered_in and not alive_elsewhere:
        return (
            FAILED_OR_UNEXPLAINED,
            f"registered by {sorted(registered_in)} with no alternate source",
        )

    if alive_elsewhere:
        if live_last is not None:
            # It once had provider history and the provider stopped while the
            # instrument kept trading — that is a coverage change, not a dead name,
            # and it deserves a look rather than a silent pass.
            return FAILED_OR_UNEXPLAINED, (
                f"provider stopped at {live_last} but {corr['source']} is current to {c_last}: "
                "coverage regression, not exhaustion"
            )
        return PROVIDER_NOT_COVERED, (
            f"outside provider coverage; trades normally — {corr['source']} current to {c_last}"
        )

    if live_last is None:
        return FAILED_OR_UNEXPLAINED, "no history in either source; symbol unverifiable"
    if live_last >= cutoff:
        return FAILED_OR_UNEXPLAINED, "live frontier is not actually stale"
    return PROVIDER_EXHAUSTED, (
        f"ceased trading: provider last {live_last}, {corr['source']} last {c_last}, "
        f"control {corr['control_symbol']} current to {c_ctl}"
    )


def _as_date(v: Any) -> date | None:
    if v is None:
        return None
    if hasattr(v, "date") and not isinstance(v, date):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        return None


def operational_facts(app_db: str | Path, universe: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Held quantity, open orders and registration per symbol, read from the app DB.

    Recomputed rather than accepted from the evidence artifact: a stale or crafted
    file must not be able to declare a held name unheld and so write it off.
    """
    out: dict[str, dict[str, Any]] = {
        s: {"held_qty": 0.0, "open_orders": 0, "registered_in": []} for s in universe
    }
    con = sqlite3.connect(f"file:{app_db}?mode=ro", uri=True)
    try:
        for tkr, qty in con.execute(
            "SELECT sym.ticker, SUM(p.qty) FROM positions p "
            "JOIN symbols sym ON sym.id = p.symbol_id WHERE p.qty <> 0 GROUP BY sym.ticker"
        ):
            if tkr in out:
                out[tkr]["held_qty"] = float(qty or 0)
        try:
            for tkr, n in con.execute(
                "SELECT sym.ticker, COUNT(*) FROM orders o JOIN symbols sym ON sym.id = o.symbol_id "
                "WHERE o.status NOT IN ('FILLED','CANCELED','EXPIRED','REJECTED') GROUP BY sym.ticker"
            ):
                if tkr in out:
                    out[tkr]["open_orders"] = int(n or 0)
        except sqlite3.Error:  # pragma: no cover - orders schema drift
            pass
        for sid, status, raw in con.execute("SELECT id, status, symbols_json FROM strategies"):
            try:
                syms = json.loads(raw or "[]")
            except (TypeError, ValueError):
                continue
            if not isinstance(syms, list):
                continue
            for s in syms:
                key = str(s).strip().upper()
                if key in out:
                    out[key]["registered_in"].append(f"{sid}:{status}")
    finally:
        con.close()
    return out


def verify_staging(
    live_path: str | Path,
    stage_path: str | Path,
    universe: Sequence[str],
    *,
    max_lag_days: int = DEFAULT_MAX_LAG_DAYS,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    evidence: dict[str, dict[str, Any]] | None = None,
    operational: dict[str, dict[str, Any]] | None = None,
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
        # Classify every non-fresh name. A dead or uncovered instrument must not
        # block the store forever, but nothing is written off without per-symbol
        # evidence — unproven is FAILED, never a silent pass.
        cutoff = _as_date(st.get("cutoff"))
        non_fresh = sorted(set(st["missing"]) | set(st["stale"]) | set(st["lastpricedate_stale"]))
        # The live store's own per-symbol frontier, so "the frontier did not move"
        # is verified against the store rather than taken from the evidence file.
        live_eff = (
            per_name_staleness(live_path, non_fresh, max_lag_days=max_lag_days)[
                "effective_last_by_symbol"
            ]
            if non_fresh
            else {}
        )
        ev, op = evidence or {}, operational or {}
        buckets: dict[str, list[str]] = {
            PROVIDER_EXHAUSTED: [],
            PROVIDER_NOT_COVERED: [],
            FAILED_OR_UNEXPLAINED: [],
        }
        records: list[dict[str, Any]] = []
        for sym in non_fresh:
            o = op.get(sym, {})
            verdict, reason = classify_stale_symbol(
                sym,
                live_last=_as_date(live_eff.get(sym)),
                stage_last=_as_date(st["effective_last_by_symbol"].get(sym)),
                cutoff=cutoff,
                evidence=ev.get(sym),
                held_qty=float(o.get("held_qty") or 0),
                open_orders=int(o.get("open_orders") or 0),
                registered_in=o.get("registered_in") or [],
            )
            buckets[verdict].append(sym)
            records.append(
                {
                    "symbol": sym,
                    "classification": verdict,
                    "reason": reason,
                    "live_effective_last": str(live_eff.get(sym)),
                    "stage_effective_last": str(st["effective_last_by_symbol"].get(sym)),
                    "stage_sep_last": st["sep_max_by_symbol"].get(sym),
                    "stage_lastpricedate": st["lastpricedate_by_symbol"].get(sym),
                    "held_qty": o.get("held_qty", 0),
                    "open_orders": o.get("open_orders", 0),
                    "registered_in": o.get("registered_in") or [],
                    "evidence": ev.get(sym),
                }
            )

        total = st["universe_size"]
        fresh_n = total - len(non_fresh)
        attributed = buckets[PROVIDER_EXHAUSTED] + buckets[PROVIDER_NOT_COVERED]
        st["classification"] = {
            "fresh_count": fresh_n,
            "provider_exhausted_count": len(buckets[PROVIDER_EXHAUSTED]),
            "provider_exhausted_symbols": buckets[PROVIDER_EXHAUSTED],
            "provider_exhausted_symbols_digest": digest(buckets[PROVIDER_EXHAUSTED]),
            "provider_not_covered_count": len(buckets[PROVIDER_NOT_COVERED]),
            "provider_not_covered_symbols": buckets[PROVIDER_NOT_COVERED],
            "provider_not_covered_symbols_digest": digest(buckets[PROVIDER_NOT_COVERED]),
            "unexplained_stale_count": len(buckets[FAILED_OR_UNEXPLAINED]),
            "unexplained_stale_symbols": buckets[FAILED_OR_UNEXPLAINED],
            "unexplained_stale_symbols_digest": digest(buckets[FAILED_OR_UNEXPLAINED]),
            # raw freshness NEVER counts an attributed name as fresh
            "raw_freshness_coverage": (fresh_n / total) if total else 0.0,
            "operationally_attributable_coverage": (
                ((fresh_n + len(attributed)) / total) if total else 0.0
            ),
            "records": records,
        }

        if buckets[FAILED_OR_UNEXPLAINED]:
            bad = buckets[FAILED_OR_UNEXPLAINED]
            msg = (
                f"{len(bad)} stale universe tickers are UNEXPLAINED "
                f"(no accepted evidence): {bad[:8]}"
            )
            # Keep the consequence in the message: a lagging lastpricedate does not
            # merely rank a name on old data, it removes the name from the pool.
            if any(s in set(st["lastpricedate_stale"]) for s in bad):
                msg += " -> names with a stale tickers.lastpricedate are EXCLUDED from the ranking pool"
            failures.append(msg)

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
    u.add_argument(
        "--prior",
        help="the last SEALED SUCCESSFUL universe report. Never a failed attempt: "
        "a failed run must not re-baseline the growth comparison. Absent on the "
        "first run, which records a baseline instead of computing growth.",
    )
    u.add_argument("--max-universe", type=int, default=DEFAULT_MAX_UNIVERSE)

    v = sub.add_parser("verify", help="gate the staging store before the swap")
    v.add_argument("--live", required=True)
    v.add_argument("--stage", required=True)
    v.add_argument("--universe", required=True, help="the universe file")
    v.add_argument("--report")
    v.add_argument("--max-lag-days", type=int, default=DEFAULT_MAX_LAG_DAYS)
    v.add_argument(
        "--evidence",
        default="/app/data/_factor_exhaustion_evidence.json",
        help="per-symbol exhaustion evidence. Supplies ONLY what verification cannot "
        "observe: the request outcome and an independent lifecycle signal. Absent or "
        "unreadable means no symbol can be attributed, so stale names fail closed.",
    )
    v.add_argument(
        "--app-db",
        default="/app/data/workbench.sqlite",
        help="read-only source for held qty, open orders and registration. These are "
        "RECOMPUTED here, never taken from the evidence file.",
    )
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
            # Integrity first: the universe must be exactly the union of its
            # recorded components. Run on EVERY refresh, including the first —
            # this is what makes "unexplained growth" a checkable claim rather
            # than a tautology about a union.
            attribute(res)

            prior = None
            if args.prior and Path(args.prior).exists():
                prior = json.loads(Path(args.prior).read_text(encoding="utf-8"))
            res["growth"] = growth_control(res, prior, max_universe=args.max_universe)

            Path(args.out).write_text("\n".join(res["universe"]), encoding="utf-8")
            if args.report:
                Path(args.report).write_text(json.dumps(res, indent=2), encoding="utf-8")
            print(f"refresh universe: {res['counts']}")
            print(f"growth: {json.dumps(res['growth'])}")
            if res["growth"].get("requires_review"):
                print("growth: REVIEW — expansion exceeds the review threshold", flush=True)
            return 0

        universe = [
            ln.strip()
            for ln in Path(args.universe).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        evidence: dict[str, dict[str, Any]] = {}
        if args.evidence and Path(args.evidence).exists():
            raw = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
            evidence = {e["symbol"]: e for e in raw.get("symbols", []) if e.get("symbol")}

        # Operational facts are recomputed from the app DB, never trusted from the
        # evidence file — an attacker or a stale artifact must not be able to
        # declare a held name unheld.
        operational: dict[str, dict[str, Any]] = {}
        if args.app_db and Path(args.app_db).exists():
            operational = operational_facts(args.app_db, universe)

        failures, report = verify_staging(
            args.live,
            args.stage,
            universe,
            max_lag_days=args.max_lag_days,
            min_coverage=args.min_coverage,
            evidence=evidence,
            operational=operational,
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
