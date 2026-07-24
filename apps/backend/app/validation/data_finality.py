"""Forward-validation DATA-FINALITY gate — prove the session's data is final before it is evaluated.

A forward observation is a claim about what the frozen instrument decided on a specific market session.
That claim is only as good as the data the decision was computed from, so before an eligible session may
be evaluated the runner must PROVE — not assume — that every input the registered construction reads is
present, complete and final for that exact date.

The registered construction is the census one and is not negotiable here (owner ruling 2026-07-24):
scores from `FactorDataStore` → `_CachedPriceStore` → `backtest_momentum_stage2.compute_day` (which is
`universe_asof(n=200)` → `compute_momentum_batch(252/21)`); regime from `stage4.build_market_proxy` /
`gross_series` over the BROAD EQUAL-WEIGHT proxy — the month-end union of `universe_asof(n=500)`, not
SPY and not any convenience benchmark — with a 200-session MA; prices from the same store's `closeadj`.

This module computes no factor value, return, ranking or portfolio result. It calls the SAME universe
construction the decision will call, so coverage is measured against the exact set of names the frozen
computation consumes, and it records what it found next to what the construction required.

## Verdicts

  READY                             every registered input is present, complete and final
  NOT_READY_DATA_STALE              the store's finalized cutoff precedes the session
  NOT_READY_CURRENT_SESSION_MISSING a name the construction admits has no usable mark on the session
  NOT_READY_LOOKBACK_INCOMPLETE     a scoring candidate lacks the exact 252+21-session history
  NOT_READY_PROXY_INCOMPLETE        a proxy constituent cannot contribute its return, on this session
                                    or on any of the 200 MA sessions
  NOT_READY_INGEST_IN_PROGRESS      an ingest is running, or the last one did not finish clean
  NOT_READY_ADJUSTMENT_UNVERIFIED   corporate-action reflection over the consumed window is not proven
                                    (including: no verifier configured, or the declared set is
                                    incomplete)
  INTEGRITY_STOP_DATA_CONFLICT      the data contradicts itself (duplicates, or the store moved
                                    underneath a run)

A NOT_READY_* verdict is the system working. The known stale-SEP condition on the box is exactly what
this gate is for: surfaced accurately, never bypassed.

## Coverage is construction-derived, not threshold-derived

There are no coverage minima. A name is either supplied to the frozen computation or it is not, and if
it is not, the reason must be a frozen eligibility RULE (listed after the window began, delisted before
the session) rather than a hole in the data. Every count is reported as a numerator over the
construction's own denominator, so "how much data was missing" is never a matter of interpretation.

## Corporate actions gate the session until reflection is PROVEN

The schema cannot show that an action is already baked into `closeadj`, and — critically — an EMPTY
`actions` table is not evidence that no action occurred. The governed store holds zero action rows while
`closeadj` departs from `close` on ~48% of its 39M rows, so a row count would let a session pass
vacuously. Reflection must therefore be proven by an `adjustment_verifier` (R5b) whose evidence object
the gate reads; the gate derives `adjustment_reflection_proven` from that verdict and never accepts an
independently supplied boolean. No verifier configured means nothing is proven, which means the session
does not run (owner ruling 2026-07-24).

## The store identity is value-level

`ingest_runs` carries no batch id and `sep` rows carry no version, so "all reads resolve from one
immutable ingest version" is CONSTRUCTED: a streaming SHA-256 over the deterministically ordered ROWS
the decision will consume — every `sep` field, the `tickers` PIT-eligibility fields, the window's
actions, and the ingest history. Aggregate counts would let a single changed `closeadj` slip through
unnoticed; hashing the values themselves does not. `verify_store_unchanged` re-streams it after the
session's reads, and any difference is `INTEGRITY_STOP_DATA_CONFLICT`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from app.validation.forward_window import IntegrityStop

# The registered construction constants (§2 / stage2 / stage4 frozen controls).
MOMENTUM_LOOKBACK_SESSIONS = 252
MOMENTUM_SKIP_SESSIONS = 21
REGIME_MA_SESSIONS = 200
SCORING_UNIVERSE_N = 200                  # stage2 UNIVERSE_N
PROXY_UNIVERSE_N = 500                    # stage4 build_market_proxy basket

# Datasets a forward session reads. An unclean ingest in any of them blocks the session.
REQUIRED_DATASETS = ("sep", "actions")

_ROW_SEP = "\x1e"
_FIELD_SEP = "\x1f"


class DataReadiness(StrEnum):
    READY = "READY"
    NOT_READY_DATA_STALE = "NOT_READY_DATA_STALE"
    NOT_READY_CURRENT_SESSION_MISSING = "NOT_READY_CURRENT_SESSION_MISSING"
    NOT_READY_LOOKBACK_INCOMPLETE = "NOT_READY_LOOKBACK_INCOMPLETE"
    NOT_READY_PROXY_INCOMPLETE = "NOT_READY_PROXY_INCOMPLETE"
    NOT_READY_INGEST_IN_PROGRESS = "NOT_READY_INGEST_IN_PROGRESS"
    NOT_READY_ADJUSTMENT_UNVERIFIED = "NOT_READY_ADJUSTMENT_UNVERIFIED"
    INTEGRITY_STOP_DATA_CONFLICT = "INTEGRITY_STOP_DATA_CONFLICT"


class DataFinalityError(IntegrityStop):
    """The store could not be interrogated at all (unreadable / wrong shape), or it moved underneath a
    run. Fails closed: a session whose data cannot be examined is never evaluated."""


@dataclass(frozen=True)
class ConstructionSpec:
    """The frozen construction the gate measures against. These are the registered values the decision
    itself uses — not tunable admission thresholds."""
    momentum_lookback_sessions: int = MOMENTUM_LOOKBACK_SESSIONS
    momentum_skip_sessions: int = MOMENTUM_SKIP_SESSIONS
    regime_ma_sessions: int = REGIME_MA_SESSIONS
    scoring_universe_n: int = SCORING_UNIVERSE_N
    proxy_universe_n: int = PROXY_UNIVERSE_N

    @property
    def required_history_sessions(self) -> int:
        return max(self.momentum_lookback_sessions + self.momentum_skip_sessions,
                   self.regime_ma_sessions)


@dataclass(frozen=True)
class DataFinalityEvidence:
    """OPEN operational provenance for one readiness assessment. Counts, dates, digests and verdicts
    only — no factor values, no returns, no rankings, no portfolio results."""
    session_date: str
    verdict: DataReadiness
    detail: str
    # store + ingest identity
    store_path: str
    store_identity_sha256: str                 # STREAMING value-level digest of the consumed rows
    ingest_identity_sha256: str
    ingest_runs_observed: int
    ingest_unclean_datasets: tuple[str, ...]
    # finality
    max_finalized_session: str | None
    finality_basis: str
    # session coverage — numerator over the construction's own denominator
    session_eligible_universe: int
    session_complete: int
    session_excluded_by_rule: int
    session_missing: int
    session_row_count: int
    session_max_lastupdated: str | None
    # lookback coverage
    lookback_sessions_available: int
    lookback_sessions_required: int
    lookback_earliest: str | None
    lookback_latest: str | None
    momentum_candidates: int
    full_lookback_candidates: int
    # market-proxy coverage
    proxy_expected_constituents: int
    proxy_contributing_constituents: int
    proxy_sessions_checked: int
    proxy_sessions_incomplete: int
    # conflicts
    duplicate_row_count: int
    # corporate actions
    corporate_actions_in_window: int
    corporate_actions_max_date: str | None
    adjustment_reflection_proven: bool
    adjustment_evidence: dict[str, Any] | None
    # what the construction required
    construction: dict[str, int] = field(default_factory=dict)
    missing_examples: tuple[str, ...] = ()     # a few names, for operational diagnosis

    @property
    def ready(self) -> bool:
        return self.verdict is DataReadiness.READY

    def to_open_provenance(self) -> dict[str, Any]:
        d = asdict(self)
        d["verdict"] = str(self.verdict)
        d["ingest_unclean_datasets"] = list(self.ingest_unclean_datasets)
        d["missing_examples"] = list(self.missing_examples)
        return d


UniverseFn = Callable[[date, int], list[str]]


class AdjustmentEvidence(Protocol):
    """What an adjustment verifier returns. The gate DERIVES `adjustment_reflection_proven` from this
    evidence — it never accepts an independently supplied boolean."""
    proven: bool

    def to_open_provenance(self) -> dict[str, Any]: ...


# (window_start, session_date, relevant_tickers, store_identity_sha256) -> evidence.
#
# The relevance set is the union of the scoring candidates and the whole market-proxy basket, so a
# security that left the universe mid-window but priced into the consumed history is still covered.
# The STORE IDENTITY is passed IN rather than recomputed: the adjustment verdict must be bound to the
# same identified store this assessment describes, and a separately recomputed value could differ.
AdjustmentVerifier = Callable[[date, date, list[str], str], AdjustmentEvidence]


class _Store:
    """Thin read-only SQL surface over the factor store. Accepts a `FactorDataStore` (its `.con`) or a
    duckdb connection, so the gate can be exercised without importing the ingest path."""

    def __init__(self, store: Any) -> None:
        con = getattr(store, "con", store)
        if not hasattr(con, "execute"):
            raise DataFinalityError(f"not a queryable store: {type(store).__name__}")
        self.con = con
        self.raw = store
        self.path = str(getattr(store, "db_path", "") or getattr(con, "database", "") or "unknown")

    def one(self, sql: str, params: list | None = None) -> tuple:
        try:
            row = self.con.execute(sql, params or []).fetchone()
        except Exception as exc:
            raise DataFinalityError(f"store query failed: {exc}") from exc
        return tuple(row) if row is not None else ()

    def all(self, sql: str, params: list | None = None) -> list[tuple]:
        try:
            return [tuple(r) for r in self.con.execute(sql, params or []).fetchall()]
        except Exception as exc:
            raise DataFinalityError(f"store query failed: {exc}") from exc

    def stream_into(self, digest: Any, sql: str, params: list | None = None,
                    *, batch: int = 10_000) -> None:
        """Feed a query's deterministically ordered rows into `digest` without materializing them."""
        digest.update(sql.encode("utf-8"))
        try:
            cur = self.con.execute(sql, params or [])
            while True:
                rows = cur.fetchmany(batch)
                if not rows:
                    break
                for r in rows:
                    digest.update(
                        (_FIELD_SEP.join("" if v is None else str(v) for v in r) + _ROW_SEP)
                        .encode("utf-8"))
        except DataFinalityError:
            raise
        except Exception as exc:
            raise DataFinalityError(f"store query failed: {exc}") from exc


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _digest(parts: list[Any]) -> str:
    return hashlib.sha256("|".join("" if p is None else str(p) for p in parts).encode()).hexdigest()


def store_identity(st: _Store, earliest: Any, session_date: date) -> str:
    """A STREAMING value-level digest over exactly the rows a session's construction consumes.

    Aggregates (counts, dates, coverage) cannot serve here: changing one `closeadj` leaves every
    aggregate intact while changing what the strategy decides. The digest therefore covers each `sep`
    field in the window, the `tickers` rows that drive PIT eligibility, the window's corporate actions,
    and the ingest history — each streamed in a deterministic order.
    """
    h = hashlib.sha256()
    lo = earliest if earliest is not None else session_date
    st.stream_into(h,
                   "SELECT ticker, date, open, high, low, close, volume, closeadj, closeunadj, "
                   "lastupdated FROM sep WHERE date BETWEEN ? AND ? ORDER BY ticker, date",
                   [lo, session_date])
    st.stream_into(h,
                   "SELECT ticker, sector, isdelisted, firstpricedate, lastpricedate, lastupdated "
                   "FROM tickers ORDER BY ticker")
    st.stream_into(h,
                   "SELECT date, action, ticker, value, contraticker FROM actions "
                   "WHERE date BETWEEN ? AND ? ORDER BY date, ticker, action, value",
                   [lo, session_date])
    st.stream_into(h,
                   "SELECT dataset, started_at, finished_at, rows, status FROM ingest_runs "
                   "ORDER BY dataset, started_at, finished_at, status")
    return h.hexdigest()


def _ingest_identity(st: _Store) -> tuple[str, int, tuple[str, ...]]:
    rows = st.all("SELECT dataset, started_at, finished_at, rows, status FROM ingest_runs "
                  "ORDER BY dataset, started_at, finished_at")
    digest = _digest([f"{d}~{_iso(s)}~{_iso(f)}~{r}~{stat}" for d, s, f, r, stat in rows])
    unclean: list[str] = []
    for dataset in REQUIRED_DATASETS:
        runs = [r for r in rows if r[0] == dataset]
        if not runs:
            continue                 # no bookkeeping is not evidence of a partial ingest; finality and
            # the adjustment rule below still have to be established on their own evidence.
        if any(str(r[4]).lower() == "running" for r in runs):
            unclean.append(f"{dataset}:running")
            continue
        latest = max(runs, key=lambda r: (r[2] or r[1] or datetime.min))
        if str(latest[4]).lower() != "ok":
            unclean.append(f"{dataset}:{latest[4]}")
    return digest, len(rows), tuple(unclean)


def _session_close_utc(session_date: date) -> datetime | None:
    try:
        import pandas_market_calendars as mcal
        schedule = mcal.get_calendar("XNYS").schedule(start_date=session_date, end_date=session_date)
        if schedule.empty:
            return None
        return schedule.iloc[0]["market_close"].tz_convert("UTC").to_pydatetime()
    except Exception:                                      # pragma: no cover
        return None


def _default_universe_fn(store: Any) -> UniverseFn:
    """Bind to the REAL registered universe construction — the same call the decision makes."""
    from app.factor_data.universe import universe_asof

    def fn(as_of: date, n: int) -> list[str]:
        return list(universe_asof(store, as_of, n=n))

    return fn


@dataclass(frozen=True)
class _TickerFacts:
    first_price: date | None
    last_price: date | None
    delisted: bool


def _ticker_facts(st: _Store, tickers: list[str]) -> dict[str, _TickerFacts]:
    if not tickers:
        return {}
    ph = ",".join("?" * len(tickers))
    rows = st.all(f"SELECT ticker, firstpricedate, lastpricedate, isdelisted FROM tickers "
                  f"WHERE ticker IN ({ph})", list(tickers))
    return {r[0]: _TickerFacts(first_price=r[1], last_price=r[2], delisted=bool(r[3])) for r in rows}


def _excluded_by_rule(facts: _TickerFacts | None, window_start: date, session_date: date) -> bool:
    """True when a frozen eligibility RULE — not a data hole — explains an absent mark: the name was
    listed after the window began (it cannot carry the history the computation consumes), or it was
    delisted before the session."""
    if facts is None:
        return False                                  # unknown name: not excused by any rule
    if facts.first_price is not None and facts.first_price > window_start:
        return True
    return bool(facts.delisted and facts.last_price is not None and facts.last_price < session_date)


def assess_data_finality(
    store: Any,
    session_date: date,
    *,
    construction: ConstructionSpec | None = None,
    universe_fn: UniverseFn | None = None,
    adjustment_verifier: AdjustmentVerifier | None = None,
) -> DataFinalityEvidence:
    """Assess whether `session_date` may be evaluated, and return the evidence either way.

    Checks run root-condition first: unclean ingest → staleness and the finality basis → the session's
    own coverage against the registered universe → self-contradiction → the exact lookback the scoring
    candidates consume → the market proxy's own constituent set across the session and the MA window →
    corporate-action reflection.
    """
    spec = construction or ConstructionSpec()
    st = _Store(store)
    uni = universe_fn or _default_universe_fn(store)
    iso = session_date.isoformat()

    ingest_digest, ingest_count, unclean = _ingest_identity(st)

    window = st.all("SELECT DISTINCT date FROM sep WHERE date <= ? ORDER BY date DESC LIMIT ?",
                    [session_date, spec.required_history_sessions])
    window_dates = [r[0] for r in window]
    earliest = window_dates[-1] if window_dates else None
    latest = window_dates[0] if window_dates else None

    max_row = st.one("SELECT MAX(date) FROM sep")
    max_finalized = max_row[0] if max_row else None

    sess = st.one("SELECT COUNT(*), MAX(lastupdated) FROM sep WHERE date = ? AND closeadj IS NOT NULL",
                  [session_date])
    session_rows, session_lastupdated = (sess or (0, None))

    dup_row = st.one(
        "SELECT COUNT(*) FROM (SELECT ticker, date FROM sep WHERE date BETWEEN ? AND ? "
        "GROUP BY ticker, date HAVING COUNT(*) > 1)", [earliest or session_date, session_date])
    duplicates = int(dup_row[0]) if dup_row else 0

    act_row = st.one("SELECT COUNT(*), MAX(date) FROM actions WHERE date BETWEEN ? AND ?",
                     [earliest or session_date, session_date])
    actions_count, actions_max = (act_row or (0, None))

    identity = store_identity(st, earliest, session_date)

    state: dict[str, Any] = {
        "session_eligible_universe": 0, "session_complete": 0, "session_excluded_by_rule": 0,
        "session_missing": 0, "momentum_candidates": 0, "full_lookback_candidates": 0,
        "proxy_expected": 0, "proxy_contributing": 0, "proxy_sessions_checked": 0,
        "proxy_sessions_incomplete": 0, "missing_examples": (), "relevance_tickers": (),
    }

    def evidence(verdict: DataReadiness, detail: str, basis: str = "", proven: bool = False,
                 adjustment: dict[str, Any] | None = None) -> DataFinalityEvidence:
        return DataFinalityEvidence(
            session_date=iso, verdict=verdict, detail=detail, store_path=st.path,
            store_identity_sha256=identity, ingest_identity_sha256=ingest_digest,
            ingest_runs_observed=ingest_count, ingest_unclean_datasets=unclean,
            max_finalized_session=_iso(max_finalized), finality_basis=basis,
            session_eligible_universe=state["session_eligible_universe"],
            session_complete=state["session_complete"],
            session_excluded_by_rule=state["session_excluded_by_rule"],
            session_missing=state["session_missing"],
            session_row_count=int(session_rows or 0),
            session_max_lastupdated=_iso(session_lastupdated),
            lookback_sessions_available=len(window_dates),
            lookback_sessions_required=spec.required_history_sessions,
            lookback_earliest=_iso(earliest), lookback_latest=_iso(latest),
            momentum_candidates=state["momentum_candidates"],
            full_lookback_candidates=state["full_lookback_candidates"],
            proxy_expected_constituents=state["proxy_expected"],
            proxy_contributing_constituents=state["proxy_contributing"],
            proxy_sessions_checked=state["proxy_sessions_checked"],
            proxy_sessions_incomplete=state["proxy_sessions_incomplete"],
            duplicate_row_count=duplicates,
            corporate_actions_in_window=int(actions_count or 0),
            corporate_actions_max_date=_iso(actions_max),
            adjustment_reflection_proven=proven, adjustment_evidence=adjustment,
            construction=asdict(spec), missing_examples=state["missing_examples"])

    # (1) mid-flight or unclean ingest
    if unclean:
        return evidence(DataReadiness.NOT_READY_INGEST_IN_PROGRESS,
                        f"ingest not clean for {list(unclean)} — the session's data may be partial")

    # (2) staleness / finality basis
    if max_finalized is None:
        return evidence(DataReadiness.NOT_READY_DATA_STALE, "the store holds no price data at all")
    if max_finalized < session_date:
        return evidence(DataReadiness.NOT_READY_DATA_STALE,
                        f"the store's finalized cutoff {_iso(max_finalized)} precedes session {iso}")
    if max_finalized > session_date:
        basis = f"a later session ({_iso(max_finalized)}) is present, so {iso} is settled"
    else:
        close = _session_close_utc(session_date)
        fin_row = st.one("SELECT MAX(finished_at) FROM ingest_runs WHERE dataset = 'sep' "
                         "AND LOWER(status) = 'ok'")
        finished_at = fin_row[0] if fin_row else None
        if close is None or finished_at is None:
            return evidence(DataReadiness.NOT_READY_DATA_STALE,
                            f"{iso} is the store's last session and no clean sep ingest completing "
                            f"after its close can be evidenced — it cannot be shown to be final")
        stamp = finished_at.replace(tzinfo=None) if isinstance(finished_at, datetime) else None
        if stamp is None or stamp < close.replace(tzinfo=None):
            return evidence(DataReadiness.NOT_READY_DATA_STALE,
                            f"the last clean sep ingest finished {_iso(finished_at)}, before the {iso} "
                            f"close {_iso(close)} — the session's data is not established as final")
        basis = (f"{iso} is the store's last session; a clean sep ingest finished {_iso(finished_at)}, "
                 f"after the {_iso(close)} close")

    # (3) the session's coverage, measured against the REGISTERED universe construction
    try:
        universe = uni(session_date, spec.scoring_universe_n)
    except Exception as exc:
        return evidence(DataReadiness.NOT_READY_CURRENT_SESSION_MISSING,
                        f"the registered universe could not be constructed for {iso}: {exc}", basis)
    state["session_eligible_universe"] = len(universe)
    if not universe:
        return evidence(DataReadiness.NOT_READY_CURRENT_SESSION_MISSING,
                        f"the registered universe for {iso} is empty", basis)

    window_start = earliest or session_date
    facts = _ticker_facts(st, universe)
    priced_today = {r[0] for r in st.all(
        "SELECT DISTINCT ticker FROM sep WHERE date = ? AND closeadj IS NOT NULL", [session_date])}

    complete, excluded, missing = [], [], []
    for t in universe:
        if t in priced_today:
            complete.append(t)
        elif _excluded_by_rule(facts.get(t), window_start, session_date):
            excluded.append(t)
        else:
            missing.append(t)
    state.update(session_complete=len(complete), session_excluded_by_rule=len(excluded),
                 session_missing=len(missing), missing_examples=tuple(sorted(missing)[:10]))
    if missing:
        return evidence(
            DataReadiness.NOT_READY_CURRENT_SESSION_MISSING,
            f"{len(missing)} of {len(universe)} registered universe name(s) have no usable mark on "
            f"{iso} and no frozen rule explains the absence (e.g. {sorted(missing)[:5]})", basis)

    # (4) self-contradiction
    if duplicates:
        return evidence(DataReadiness.INTEGRITY_STOP_DATA_CONFLICT,
                        f"{duplicates} duplicate (ticker, date) row(s) in the consumed window", basis)

    # (5) the exact history the scoring candidates consume
    if len(window_dates) < spec.required_history_sessions:
        return evidence(
            DataReadiness.NOT_READY_LOOKBACK_INCOMPLETE,
            f"{len(window_dates)} session(s) of history available, {spec.required_history_sessions} "
            f"required ({spec.momentum_lookback_sessions}+{spec.momentum_skip_sessions} momentum / "
            f"{spec.regime_ma_sessions} regime MA)", basis)

    candidates = [t for t in universe if not _excluded_by_rule(facts.get(t), window_start, session_date)]
    state["momentum_candidates"] = len(candidates)
    state["relevance_tickers"] = tuple(sorted(set(state["relevance_tickers"]) | set(candidates)))
    full = _names_with_full_history(st, candidates, window_start, session_date,
                                    len(window_dates))
    state["full_lookback_candidates"] = len(full)
    short = sorted(set(candidates) - full)
    if short:
        state["missing_examples"] = tuple(short[:10])
        return evidence(
            DataReadiness.NOT_READY_LOOKBACK_INCOMPLETE,
            f"{len(short)} of {len(candidates)} scoring candidate(s) lack the exact "
            f"{spec.required_history_sessions}-session history the computation consumes "
            f"(e.g. {short[:5]})", basis)

    # (6) the market proxy's OWN constituent set
    proxy_verdict = _assess_proxy(st, uni, spec, window_dates, session_date, state)
    if proxy_verdict is not None:
        return evidence(DataReadiness.NOT_READY_PROXY_INCOMPLETE, proxy_verdict, basis)

    # (7) corporate-action reflection — PROVEN by a verifier, or the session does not run.
    #
    # An empty `actions` table is NOT evidence that no action occurred: the governed store holds zero
    # action rows while `closeadj` departs from `close` on ~48% of its 39M rows. Counting rows would let
    # a session pass vacuously, so reflection must be proven by a verifier that also detects adjustment
    # events the declared set does not explain. With no verifier configured, nothing is proven.
    if adjustment_verifier is None:
        return evidence(
            DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED,
            f"no adjustment verifier is configured, so corporate-action reflection over the consumed "
            f"window cannot be proven ({actions_count} declared action row(s), latest "
            f"{_iso(actions_max)}); an absent action table is not evidence that none occurred", basis)
    result = adjustment_verifier(window_start, session_date, list(state["relevance_tickers"]), identity)
    adjustment = result.to_open_provenance()
    bound = str(adjustment.get("store_identity_sha256", ""))
    if bound != identity:
        return evidence(
            DataReadiness.INTEGRITY_STOP_DATA_CONFLICT,
            f"the adjustment verification is bound to store identity {bound[:16] or '<empty>'}… but "
            f"this assessment describes {identity[:16]}… — the two do not describe the same data",
            basis, False, adjustment)
    if not result.proven:
        return evidence(
            DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED,
            "corporate-action reflection over the consumed window is not proven: "
            f"{adjustment.get('detail', '')}",
            basis, False, adjustment)

    return evidence(DataReadiness.READY, "all registered inputs are present, complete and final",
                    basis, True, adjustment)


def _names_with_full_history(st: _Store, names: list[str], window_start: Any, session_date: date,
                             required_sessions: int) -> set[str]:
    """The subset of `names` carrying a usable mark on EVERY session of the consumed window."""
    if not names:
        return set()
    ph = ",".join("?" * len(names))
    rows = st.all(
        f"SELECT ticker FROM sep WHERE ticker IN ({ph}) AND date BETWEEN ? AND ? "
        f"AND closeadj IS NOT NULL GROUP BY ticker HAVING COUNT(DISTINCT date) >= ?",
        [*names, window_start, session_date, required_sessions])
    return {r[0] for r in rows}


def _assess_proxy(st: _Store, uni: UniverseFn, spec: ConstructionSpec, window_dates: list[date],
                  session_date: date, state: dict[str, Any]) -> str | None:
    """Measure the market proxy against ITS OWN construction: the month-end union of
    `universe_asof(n=500)` over the MA window, each constituent needing consecutive marks to contribute
    a return. Returns a failure detail, or None when the proxy is complete.

    `build_market_proxy` averages returns with `skipna=True`, so a missing constituent is silently
    dropped by the construction — which is exactly why completeness has to be proven here.
    """
    ma_dates = sorted(window_dates[:spec.regime_ma_sessions])
    if len(ma_dates) < 2:
        return f"only {len(ma_dates)} proxy session(s) available; the 200-session MA cannot be formed"

    month_ends = [d for i, d in enumerate(ma_dates)
                  if i + 1 == len(ma_dates) or (ma_dates[i + 1].year, ma_dates[i + 1].month)
                  != (d.year, d.month)]
    basket: set[str] = set()
    for d in month_ends:
        try:
            basket |= set(uni(d, spec.proxy_universe_n))
        except Exception:                     # the construction itself suppresses these (stage4 §)
            continue
    if not basket:
        return "the market-proxy basket is empty — no month-end universe could be constructed"

    names = sorted(basket)
    facts = _ticker_facts(st, names)
    window_start = ma_dates[0]
    expected = [t for t in names
                if not _excluded_by_rule(facts.get(t), window_start, session_date)]
    state["proxy_expected"] = len(expected)
    state["proxy_sessions_checked"] = len(ma_dates)
    # Relevance for adjustment verification is the WHOLE basket, not just today's expected set: a name
    # that left the universe mid-window still priced into the consumed history.
    state["relevance_tickers"] = tuple(sorted(set(state["relevance_tickers"]) | basket))

    ph = ",".join("?" * len(expected)) if expected else "''"
    rows = st.all(
        f"SELECT date, COUNT(DISTINCT ticker) FROM sep WHERE ticker IN ({ph}) "
        f"AND date BETWEEN ? AND ? AND closeadj IS NOT NULL GROUP BY date",
        [*expected, window_start, session_date])
    per_session = {r[0]: int(r[1]) for r in rows}
    state["proxy_contributing"] = per_session.get(session_date, 0)

    incomplete = [d for d in ma_dates if per_session.get(d, 0) != len(expected)]
    state["proxy_sessions_incomplete"] = len(incomplete)
    if state["proxy_contributing"] != len(expected):
        return (f"{state['proxy_contributing']} of {len(expected)} proxy constituent(s) are priced on "
                f"{session_date.isoformat()} — the equal-weight return would silently drop the rest")
    if incomplete:
        return (f"{len(incomplete)} of {len(ma_dates)} proxy session(s) in the MA window are missing a "
                f"constituent mark (e.g. {[d.isoformat() for d in incomplete[:3]]}) — the 200-session "
                f"MA would be computed over an incomplete basket")
    return None


def verify_store_unchanged(store: Any, session_date: date, expected: DataFinalityEvidence, *,
                           construction: ConstructionSpec | None = None) -> None:
    """Re-stream the value-level identity after the session's reads and require it to be unchanged.

    This is how "all data reads resolve from the same immutable ingest version" is established in a
    schema with no ingest-version column: not by trusting a field, but by proving the VALUES the reads
    resolved against did not move underneath them.
    """
    spec = construction or ConstructionSpec()
    st = _Store(store)
    window = st.all("SELECT DISTINCT date FROM sep WHERE date <= ? ORDER BY date DESC LIMIT ?",
                    [session_date, spec.required_history_sessions])
    earliest = window[-1][0] if window else None
    now = store_identity(st, earliest, session_date)
    if now != expected.store_identity_sha256:
        raise DataFinalityError(
            f"the factor store changed during session {session_date.isoformat()}: identity "
            f"{expected.store_identity_sha256[:16]}… → {now[:16]}… — the session's reads did not "
            f"resolve against one immutable state")


def whole_file_digest(path: Path, *, chunk: int = 1 << 20) -> str:
    """SHA-256 of the store file itself — the census-style pin. Optional additional evidence; the
    streaming value-level identity above is what every session records."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()
