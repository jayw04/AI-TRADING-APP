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
import sys
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
#
# Defined in ``factor_adjudication`` and re-exported here, NOT duplicated. Until
# 2026-08-11 this module and ``deploy/aws/factor-freshness.sh`` each carried their own
# reading of the same evidence artifact and reached opposite verdicts from it: the
# watchdog published coverage 1.0000 / PASS while this gate aborted the swap at 0.9784,
# from the same store, universe and file. One implementation consumed by both is the
# only structural fix — see that module's docstring for the three asymmetries closed.
#
# The sibling import needs the script directory on ``sys.path``. It already is when this
# runs as ``python scripts/factor_refresh.py`` (the shell job's form), but not when a
# test loads this file through ``spec_from_file_location``, so make it explicit.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

# Redundant ``X as X`` aliases are the PEP 484 re-export form: these names are part of
# this module's public surface (its tests and the shell job both reach for them here),
# they are simply no longer DEFINED here.
from factor_adjudication import (  # noqa: E402  (needs the sys.path line above)
    ATTRIBUTED as ATTRIBUTED,
)
from factor_adjudication import (  # noqa: E402
    DEFAULT_SCHEDULE_TZ as _DEFAULT_SCHEDULE_TZ,
)

# The DIAGNOSTIC surface, re-exported on the same terms. It decides nothing — see
# ``diagnose_unexplained`` — but it is what lets this gate's abort line and the watchdog's
# alert describe one condition in one vocabulary.
from factor_adjudication import (  # noqa: E402
    EVIDENCE_DIAGNOSIS_DETAIL as EVIDENCE_DIAGNOSIS_DETAIL,
)
from factor_adjudication import (  # noqa: E402
    EVIDENCE_PRESENT_REFUSED as EVIDENCE_PRESENT_REFUSED,
)
from factor_adjudication import (  # noqa: E402
    FAILED_OR_UNEXPLAINED as FAILED_OR_UNEXPLAINED,
)
from factor_adjudication import (  # noqa: E402
    FRESH as FRESH,
)
from factor_adjudication import (  # noqa: E402
    MAX_EVIDENCE_AGE_DAYS as MAX_EVIDENCE_AGE_DAYS,
)
from factor_adjudication import (  # noqa: E402
    PROVIDER_EXHAUSTED as PROVIDER_EXHAUSTED,
)
from factor_adjudication import (  # noqa: E402
    PROVIDER_NOT_COVERED as PROVIDER_NOT_COVERED,
)
from factor_adjudication import (  # noqa: E402
    _as_date as _as_date,
)
from factor_adjudication import (  # noqa: E402
    adjudicate as adjudicate,
)
from factor_adjudication import (  # noqa: E402
    classify_stale_symbol as classify_stale_symbol,
)
from factor_adjudication import (  # noqa: E402
    diagnose_unexplained as diagnose_unexplained,
)
from factor_adjudication import (  # noqa: E402
    evidence_expiry as evidence_expiry,
)
from factor_adjudication import (  # noqa: E402
    exemption_ceiling as exemption_ceiling,
)
from factor_adjudication import (  # noqa: E402
    gating_coverage as gating_coverage,
)
from factor_adjudication import (  # noqa: E402
    load_evidence as load_evidence,
)
from factor_adjudication import (  # noqa: E402
    load_evidence_records as load_evidence_records,
)
from factor_adjudication import (  # noqa: E402
    operational_facts as operational_facts,
)
from factor_adjudication import (  # noqa: E402
    schedule_today as schedule_today,
)

#: How many days before the evidence artifact's expiry the verifier starts saying so. The
#: refresh runs on weekdays, so a 10-day notice is at least seven opportunities to act — and
#: the cliff it guards against (all attributions sharing one observation timestamp) turns a
#: missed notice into a multi-name failure rather than a single one.
EVIDENCE_EXPIRY_WARN_DAYS = 10

#: The timezone the refresh schedule is expressed in. Mirrors ``REFRESH_SCHEDULE_TZ`` in
#: ``deploy/aws/factor-freshness.sh``. DEFINED IN THE SHARED MODULE and re-exported here, not
#: restated: this verifier, the watchdog and the evidence generator must age one artifact
#: against ONE calendar, and three copies of a timezone constant is three chances to drift.
DEFAULT_SCHEDULE_TZ = _DEFAULT_SCHEDULE_TZ


def _schedule_today(tz_name: str = DEFAULT_SCHEDULE_TZ) -> date:
    """Today's date in the refresh schedule's timezone. Delegates to the shared module.

    Kept as a name because this module's call sites and tests use it; the implementation
    lives in ``factor_adjudication`` so the generator can reach the same clock without
    importing the verifier. See :func:`factor_adjudication.schedule_today`.
    """
    return schedule_today(tz_name)


def verify_staging(
    live_path: str | Path,
    stage_path: str | Path,
    universe: Sequence[str],
    *,
    max_lag_days: int = DEFAULT_MAX_LAG_DAYS,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    evidence: dict[str, dict[str, Any]] | None = None,
    evidence_all: dict[str, dict[str, Any]] | None = None,
    evidence_status: str = "ok",
    operational: dict[str, dict[str, Any]] | None = None,
    as_of: date | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Gate the staging store before the swap. Returns ``(failures, report)``.

    Keeps the original global regression checks — they catch a truncated or
    rolled-back pull — and adds the per-name coverage the ``max(date)`` checks
    could not see.

    ``evidence`` is the CLAIMABLE mapping adjudication consumes. ``evidence_all`` additionally
    carries records that claim nothing adjudicable, and is used ONLY to diagnose the abort
    message: it is never passed to :func:`adjudicate`, so a dropped record cannot become an
    exemption by being reported. ``evidence_status`` is the artifact's own health, surfaced
    because a broken control is a finding even on a run where nothing happens to be stale.

    ``as_of`` is the run date the corroboration observations are aged against. It is a
    PARAMETER rather than ``date.today()`` because the watchdog computes it in the schedule
    timezone: with the two components on different clocks, a run in the UTC evening would age
    evidence one day further than the watchdog did over the same artifact, and the two would
    disagree at the tolerance boundary while both believed they were applying one rule.
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

    # ⛔ THE UNIVERSE DEFINES THE POPULATION BEING VERIFIED. Without it there is nothing to
    # verify, and "nothing to verify" is not "nothing failed". Until 2026-08-28 the entire
    # per-name block below — staleness, adjudication, the coverage gate AND the evidence-health
    # check — sat behind ``if s_sep is not None and universe:`` with no ``else``, so an empty
    # universe file produced ZERO failures and a passing verify, and the swap proceeded on a
    # vacuously-green gate. ``derive_refresh_universe`` refuses to WRITE an empty universe,
    # which lowers reachability but does not make this gate correct: a truncated, missing or
    # unreadable file reaches here, and the evidence writer is deliberately non-fatal precisely
    # because "the verifier is the gate". A gate that passes when its input is absent is not a
    # gate. Fail closed, first-class, before anything else reads it.
    if not universe:
        failures.append(
            "refresh universe is EMPTY - refusing verification and promotion. The universe "
            "defines the population being verified; with none, no per-name freshness, "
            "adjudication, coverage or evidence check can be performed, and an unperformed "
            "check is not a passed one"
        )

    if s_sep is not None and universe:
        st = per_name_staleness(stage_path, universe, max_lag_days=max_lag_days)
        report["per_name"] = st

        # Adjudicate FIRST, then gate. The previous order — gate on the raw figure, then
        # classify — is why the live store froze on 2026-08-11: nine cross-asset ETFs that
        # this provider does not carry at all were counted as uncovered against a threshold
        # they can never satisfy, and the classification that said so was computed
        # afterwards and only reported. Adjudication that does not reach the gate it exists
        # to inform is decoration.
        cutoff = _as_date(st.get("cutoff"))
        if cutoff is None:
            # per_name_staleness always derives this from the store's own frontier, so an
            # unresolvable cutoff means the report is malformed. Fail the gate rather than
            # adjudicate against an assumed date — every verdict below depends on it.
            raise RefreshError("staleness report has no resolvable cutoff date")
        non_fresh = sorted(set(st["missing"]) | set(st["stale"]) | set(st["lastpricedate_stale"]))
        # The live store's own per-symbol frontier, so "the frontier did not move" is
        # verified against the store rather than taken from the evidence file.
        live_eff = (
            per_name_staleness(live_path, non_fresh, max_lag_days=max_lag_days)[
                "effective_last_by_symbol"
            ]
            if non_fresh
            else {}
        )
        result = adjudicate(
            universe,
            stage_effective=st["effective_last_by_symbol"],
            live_effective=live_eff,
            non_fresh=non_fresh,
            cutoff=cutoff,
            # The corroboration block is a past observation; it is judged against the
            # cutoff of its own moment, not this run's. See classify_stale_symbol.
            tolerance_days=max_lag_days,
            as_of=as_of or date.today(),
            evidence=evidence or {},
            operational=operational or {},
        )
        coverage = gating_coverage(result)

        st["classification"] = {
            # Four populations. Attributed names are NEVER counted as fresh, so the raw
            # figure stays honest even when attribution reaches 100%.
            "fresh_count": result["fresh_count"],
            "provider_exhausted_count": len(result["provider_exhausted_symbols"]),
            "provider_exhausted_symbols": result["provider_exhausted_symbols"],
            "provider_exhausted_symbols_digest": digest(result["provider_exhausted_symbols"]),
            "provider_not_covered_count": len(result["provider_not_covered_symbols"]),
            "provider_not_covered_symbols": result["provider_not_covered_symbols"],
            "provider_not_covered_symbols_digest": digest(result["provider_not_covered_symbols"]),
            "failed_or_unexplained_count": result["failed_or_unexplained_count"],
            "failed_or_unexplained_symbols": result["failed_or_unexplained_symbols"],
            "failed_or_unexplained_symbols_digest": digest(result["failed_or_unexplained_symbols"]),
            "attributed_count": result["attributed_count"],
            "assessable_count": result["assessable_count"],
            "exemption_ceiling": result["exemption_ceiling"],
            "raw_freshness_coverage": result["raw_coverage"],
            # THE figure this gate compares against the threshold. Named explicitly so a
            # reader of the report can tell which number decided the run.
            "gating_coverage": coverage,
            "gating_coverage_definition": "covered / assessable, assessable = universe - attributed",
            # The per-symbol request outcome is LOG-DERIVED: ingest_runs is per-dataset, so
            # no per-symbol receipt exists. Disclosed rather than presented as a
            # machine-enforced fact.
            "request_evidence_quality": "LOG_DERIVED",
            "per_symbol_ingest_receipt": "NOT_AVAILABLE",
            "limitation": "accepted for this bounded recovery; frontiers and operational "
            "facts are independently recomputed and unproven cases fail closed",
            "records": result["records"],
            "notes": result["notes"],
        }

        if coverage < min_coverage:
            failures.append(
                f"per-name coverage {coverage:.4f} < {min_coverage} "
                f"({len(st['missing'])} missing, {len(st['stale'])} stale "
                f"beyond {max_lag_days}d; e.g. "
                f"{(st['missing'] + st['stale'])[:8]})"
            )
        # An exemption list large enough to hollow out the denominator, or one that covers
        # the whole pool, is a suppressed check rather than a healthy store.
        failures.extend(result["problems"])

        # --- evidence-artifact health, reported whether or not anything is stale ----
        #
        # The artifact is a CONTROL. On a run where nothing happens to be stale, a broken or
        # expiring artifact would otherwise pass silently and then fail on a morning when it
        # also has names to explain — which is the shape of the 2026-09-10 cliff.
        run_date = as_of or date.today()
        expiry = evidence_expiry(
            evidence or {}, as_of=run_date, max_evidence_age_days=MAX_EVIDENCE_AGE_DAYS
        )
        st["evidence"] = {"status": evidence_status, "expiry": expiry}
        if evidence_status in ("unreadable", "malformed"):
            failures.append(
                f"DATA_EXHAUSTION_EVIDENCE_{evidence_status.upper()}: the evidence artifact "
                "could not be used, so NO symbol could be attributed and an adjudicated "
                "delisting reads as a freshness failure - repair or regenerate the artifact "
                "(scripts/factor_evidence.py); do NOT relax the freshness threshold"
            )

        if result["failed_or_unexplained_symbols"]:
            bad = result["failed_or_unexplained_symbols"]
            # WHY each name is unexplained, not merely THAT it is. `UNEXPLAINED: ['WBS']` —
            # the line that aborted three consecutive production refreshes on 2026-08-25/26/27
            # — is the same string whether nobody ever wrote a record for the name or the rule
            # read a current record and refused it. Those need opposite operator responses:
            # regenerate the artifact, or investigate the symbol. Diagnosis is computed by the
            # shared module so this message and the watchdog's alert cannot drift apart.
            diagnosis = diagnose_unexplained(
                bad,
                all_records=evidence_all if evidence_all is not None else (evidence or {}),
                claimable_records=evidence or {},
                as_of=run_date,
                max_evidence_age_days=MAX_EVIDENCE_AGE_DAYS,
            )
            st["classification"]["unexplained_diagnosis"] = diagnosis
            grouped: dict[str, list[str]] = {}
            for symbol, label in sorted(diagnosis.items()):
                grouped.setdefault(label, []).append(symbol)
            detail = "; ".join(
                f"{label} {syms[:8]} - {EVIDENCE_DIAGNOSIS_DETAIL.get(label, '')}"
                for label, syms in sorted(grouped.items())
            )
            msg = (
                f"{len(bad)} stale universe tickers are UNEXPLAINED "
                f"(no accepted evidence): {bad[:8]}. Diagnosis: {detail}"
            )
            # Keep the consequence in the message: a lagging lastpricedate does not merely
            # rank a name on old data, it removes the name from the pool.
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
    v.add_argument(
        "--schedule-tz",
        default=DEFAULT_SCHEDULE_TZ,
        help="timezone the refresh schedule is expressed in. Evidence ages in DAYS, "
        "so this must match REFRESH_SCHEDULE_TZ in deploy/aws/factor-freshness.sh or "
        "the two components age one artifact against two calendars.",
    )

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
        # ONE reader, shared with the watchdog. This used to be a bespoke `json.loads` here
        # that kept EVERY record regardless of what it claimed, while the watchdog used
        # `load_evidence`, which drops records claiming nothing adjudicable. Same file, two
        # readers, two different evidence sets — precisely the class of divergence ADR 0051
        # closed for the classification rules but which survived, unnoticed, in the parsing.
        evidence_all, evidence, ev_note, evidence_status = load_evidence_records(args.evidence)
        print(f"verify: evidence status={evidence_status} ({ev_note})")

        # The run date, in the SCHEDULE timezone. `date.today()` in this container is UTC, and
        # the watchdog ages the same artifact against America/New_York — so between 20:00 and
        # 00:00 ET the two would differ by a day and could disagree at the expiry boundary
        # while both believed they were applying one rule.
        run_date = _schedule_today(args.schedule_tz)

        expiry = evidence_expiry(
            evidence, as_of=run_date, max_evidence_age_days=MAX_EVIDENCE_AGE_DAYS
        )
        if expiry["earliest_expiry_on"]:
            print(
                f"verify: evidence expires {expiry['earliest_expiry_on']} "
                f"({expiry['days_remaining']}d remaining, {expiry['record_count']} record(s))"
            )
        if (
            expiry["days_remaining"] is not None
            and expiry["days_remaining"] <= EVIDENCE_EXPIRY_WARN_DAYS
        ):
            # A WARNING here, not a failure: the artifact is still valid today. The failure
            # arrives on its own when the records actually expire — this is the notice that
            # there is still time to regenerate. Every record carries the same observation
            # timestamp, so they expire together and this is a cliff, not a slope.
            print(
                f"verify: EVIDENCE_EXPIRY_WARNING: attribution for {expiry['record_count']} "
                f"symbol(s) expires on {expiry['earliest_expiry_on']} "
                f"({expiry['days_remaining']}d) - regenerate with scripts/factor_evidence.py "
                "before then, or the refresh will begin failing on all of them at once"
            )

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
            evidence_all=evidence_all,
            evidence_status=evidence_status,
            operational=operational,
            as_of=run_date,
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
