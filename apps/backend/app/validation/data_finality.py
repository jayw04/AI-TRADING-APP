"""Forward-validation DATA-FINALITY gate — prove the session's data is final before it is evaluated.

A forward observation is a claim about what the frozen instrument decided on a specific market session.
That claim is only as good as the data the decision was computed from, so before an eligible session may
be evaluated the runner must PROVE — not assume — that every input the registered construction reads is
present, complete and final for that exact date.

The registered construction is the census one and is not negotiable here (owner ruling 2026-07-24):
scores from `FactorDataStore` → `_CachedPriceStore` → `backtest_momentum_stage2.compute_day`; regime
from `stage4.build_market_proxy` / `gross_series` over the BROAD EQUAL-WEIGHT market proxy (not SPY, not
any convenience benchmark) with a 200-session MA warm-up; prices from the same store's `closeadj`. This
module does not compute any of those values — it proves the data they will read is final, and records
the evidence. Nothing here reveals a factor value, a return, a ranking or a portfolio result.

## Verdicts

  READY                             every check passed for this session
  NOT_READY_DATA_STALE              the store's finalized cutoff precedes the session
  NOT_READY_CURRENT_SESSION_MISSING the session itself has no (or unusable) rows
  NOT_READY_LOOKBACK_INCOMPLETE     252 / 21 / 200-session history is not complete
  NOT_READY_PROXY_INCOMPLETE        market-proxy constituents are missing or too thin
  NOT_READY_INGEST_IN_PROGRESS      an ingest is running, or the last one did not finish clean
  INTEGRITY_STOP_DATA_CONFLICT      the data contradicts itself (duplicates, or the store changed
                                    underneath a run)

A NOT_READY_* verdict is the system working. The known stale-SEP condition on the box is exactly what
this gate is for: it is surfaced accurately, never bypassed.

## Two honest limits, recorded rather than papered over

1. **There is no ingest-version column.** `ingest_runs` records `(dataset, started_at, finished_at,
   rows, status)` and `sep` rows carry no batch id, so "all reads resolve from one immutable ingest
   version" cannot be read off the data. It is CONSTRUCTED here: a content identity digest over the
   session's own lookback window plus the ingest-run history, captured before the reads and re-verified
   after them (`verify_store_unchanged`). A change mid-session is `INTEGRITY_STOP_DATA_CONFLICT`.

2. **Corporate-action *reflection* cannot be proven from this schema.** We can prove the actions ingest
   is clean and record the actions touching the window; we cannot prove every action is already baked
   into `closeadj`. The evidence therefore carries `adjustment_reflection_proven = False` rather than a
   status field that would imply a proof the data cannot support.

## Coverage thresholds are OPERATIONAL, not research parameters

The minimum constituent counts below decide only whether a session RUNS. They cannot change a decision,
a weight, a benchmark or a gate — a session either has enough data to be evaluated faithfully or it is
refused. They are injectable, conservative by default, and recorded in the evidence so that what was
required is always visible next to what was found.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.validation.forward_window import IntegrityStop

# The registered lookbacks (§2): 252-session momentum window, 21-session skip, 200-session regime MA.
MOMENTUM_LOOKBACK_SESSIONS = 252
MOMENTUM_SKIP_SESSIONS = 21
REGIME_MA_SESSIONS = 200

# Datasets a forward session reads. An unclean ingest in any of them blocks the session.
REQUIRED_DATASETS = ("sep",)


class DataReadiness(StrEnum):
    READY = "READY"
    NOT_READY_DATA_STALE = "NOT_READY_DATA_STALE"
    NOT_READY_CURRENT_SESSION_MISSING = "NOT_READY_CURRENT_SESSION_MISSING"
    NOT_READY_LOOKBACK_INCOMPLETE = "NOT_READY_LOOKBACK_INCOMPLETE"
    NOT_READY_PROXY_INCOMPLETE = "NOT_READY_PROXY_INCOMPLETE"
    NOT_READY_INGEST_IN_PROGRESS = "NOT_READY_INGEST_IN_PROGRESS"
    INTEGRITY_STOP_DATA_CONFLICT = "INTEGRITY_STOP_DATA_CONFLICT"


class DataFinalityError(IntegrityStop):
    """The store could not be interrogated at all (unreadable / wrong shape). Fails closed: a session
    whose data cannot be examined is never evaluated."""


@dataclass(frozen=True)
class FinalityThresholds:
    """Operational data-quality minima — they gate whether a session runs, never what it decides."""
    momentum_lookback_sessions: int = MOMENTUM_LOOKBACK_SESSIONS
    momentum_skip_sessions: int = MOMENTUM_SKIP_SESSIONS
    regime_ma_sessions: int = REGIME_MA_SESSIONS
    min_session_constituents: int = 200        # names priced on the session itself
    min_full_lookback_constituents: int = 100  # names with a COMPLETE momentum lookback
    min_proxy_constituents: int = 100          # names contributing a return to the market proxy

    @property
    def required_history_sessions(self) -> int:
        """The longest history any registered input needs, ending at the session."""
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
    store_identity_sha256: str                 # content digest over the window + ingest history
    ingest_identity_sha256: str                # digest over the ingest-run history alone
    ingest_runs_observed: int
    ingest_unclean_datasets: tuple[str, ...]
    # finality
    max_finalized_session: str | None          # the store's finalized SEP cutoff
    finality_basis: str                        # how finality was established for this session
    # session coverage
    session_row_count: int
    session_constituents: int
    session_max_lastupdated: str | None
    # lookback coverage
    lookback_sessions_available: int
    lookback_sessions_required: int
    lookback_earliest: str | None
    lookback_latest: str | None
    full_lookback_constituents: int
    # market-proxy coverage
    proxy_constituents: int
    thin_proxy_sessions: int                   # sessions in the MA window below the proxy minimum
    # conflicts
    duplicate_row_count: int
    # corporate actions — recorded, with the limit of what can be proven stated in the field itself
    corporate_actions_in_window: int
    corporate_actions_max_date: str | None
    adjustment_reflection_proven: bool
    # what was required
    thresholds: dict[str, int] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.verdict is DataReadiness.READY

    def to_open_provenance(self) -> dict[str, Any]:
        """The dict recorded next to an observation (or a readiness report). Verdict is a string so the
        payload is stable JSON."""
        d = asdict(self)
        d["verdict"] = str(self.verdict)
        d["ingest_unclean_datasets"] = list(self.ingest_unclean_datasets)
        return d


class _Store:
    """Thin read-only SQL surface over the factor store. Accepts either a `FactorDataStore` (its
    `.con`) or a duckdb connection, so the gate can be exercised against a synthetic fixture without
    importing the ingest path."""

    def __init__(self, store: Any) -> None:
        con = getattr(store, "con", store)
        if not hasattr(con, "execute"):
            raise DataFinalityError(f"not a queryable store: {type(store).__name__}")
        self.con = con
        self.path = str(getattr(store, "db_path", "") or getattr(con, "database", "") or "unknown")

    def one(self, sql: str, params: list | None = None) -> tuple:
        try:
            row = self.con.execute(sql, params or []).fetchone()
        except Exception as exc:                          # duckdb raises many concrete types
            raise DataFinalityError(f"store query failed: {exc}") from exc
        return tuple(row) if row is not None else ()

    def all(self, sql: str, params: list | None = None) -> list[tuple]:
        try:
            return [tuple(r) for r in self.con.execute(sql, params or []).fetchall()]
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


def _ingest_identity(st: _Store) -> tuple[str, int, tuple[str, ...]]:
    """A digest over the ingest-run history, the number of runs, and the datasets whose ingest is not
    clean (still running, failed, or never run at all)."""
    rows = st.all("SELECT dataset, started_at, finished_at, rows, status FROM ingest_runs "
                  "ORDER BY dataset, started_at, finished_at")
    digest = _digest([f"{d}~{_iso(s)}~{_iso(f)}~{r}~{stat}" for d, s, f, r, stat in rows])

    unclean: list[str] = []
    for dataset in REQUIRED_DATASETS:
        runs = [r for r in rows if r[0] == dataset]
        if not runs:
            continue                                       # no bookkeeping at all: not evidence of a
            # partial ingest, and the finality basis below still has to be established independently.
        if any(str(r[4]).lower() == "running" for r in runs):
            unclean.append(f"{dataset}:running")
            continue
        latest = max(runs, key=lambda r: (r[2] or r[1] or datetime.min))
        if str(latest[4]).lower() != "ok":
            unclean.append(f"{dataset}:{latest[4]}")
    return digest, len(rows), tuple(unclean)


def _session_close_utc(session_date: date) -> datetime | None:
    """The session's authoritative close in UTC (XNYS), used to decide whether an ingest that finished
    could have contained the complete session. None if the calendar cannot answer."""
    try:
        import pandas_market_calendars as mcal
        schedule = mcal.get_calendar("XNYS").schedule(start_date=session_date, end_date=session_date)
        if schedule.empty:
            return None
        return schedule.iloc[0]["market_close"].tz_convert("UTC").to_pydatetime()
    except Exception:                                      # pragma: no cover - calendar absence is
        return None                                        # handled by eval_calendar's own gate


def assess_data_finality(
    store: Any,
    session_date: date,
    *,
    thresholds: FinalityThresholds | None = None,
) -> DataFinalityEvidence:
    """Assess whether `session_date` may be evaluated, and return the evidence either way.

    Checks run in a deliberate order — the most fundamental contradiction first, so the verdict names
    the root condition rather than a downstream symptom:

      1. an ingest that is running or did not finish clean (the data may be mid-flight);
      2. the store's finalized cutoff versus the session (staleness);
      3. the session's own rows (present, priced, enough constituents);
      4. duplicate (ticker, date) rows anywhere in the window (self-contradicting data);
      5. the 252 / 21 / 200-session history behind the session (lookback completeness);
      6. market-proxy constituent coverage on the session and across the MA window.
    """
    th = thresholds or FinalityThresholds()
    st = _Store(store)
    iso = session_date.isoformat()

    ingest_digest, ingest_count, unclean = _ingest_identity(st)

    window = st.all(
        "SELECT DISTINCT date FROM sep WHERE date <= ? ORDER BY date DESC LIMIT ?",
        [session_date, th.required_history_sessions])
    window_dates = [r[0] for r in window]
    earliest = window_dates[-1] if window_dates else None
    latest = window_dates[0] if window_dates else None

    max_session = st.one("SELECT MAX(date) FROM sep")
    max_finalized = max_session[0] if max_session else None

    sess = st.one("SELECT COUNT(*), COUNT(DISTINCT ticker), MAX(lastupdated) FROM sep "
                  "WHERE date = ? AND closeadj IS NOT NULL", [session_date])
    session_rows, session_names, session_lastupdated = (sess or (0, 0, None))

    dup = st.one("SELECT COUNT(*) FROM (SELECT ticker, date FROM sep WHERE date <= ? AND date >= ? "
                 "GROUP BY ticker, date HAVING COUNT(*) > 1)",
                 [session_date, earliest or session_date])
    duplicates = int(dup[0]) if dup else 0

    full_lookback = 0
    thin_proxy = 0
    proxy_names = 0
    if earliest is not None:
        need = min(th.momentum_lookback_sessions + th.momentum_skip_sessions, len(window_dates))
        row = st.one(
            "SELECT COUNT(*) FROM (SELECT ticker FROM sep WHERE date BETWEEN ? AND ? "
            "AND closeadj IS NOT NULL GROUP BY ticker HAVING COUNT(DISTINCT date) >= ?)",
            [earliest, session_date, need])
        full_lookback = int(row[0]) if row else 0

        ma_dates = window_dates[:th.regime_ma_sessions]
        ma_earliest = ma_dates[-1] if ma_dates else session_date
        row = st.one(
            "SELECT COUNT(*) FROM (SELECT date FROM sep WHERE date BETWEEN ? AND ? "
            "AND closeadj IS NOT NULL GROUP BY date HAVING COUNT(DISTINCT ticker) < ?)",
            [ma_earliest, session_date, th.min_proxy_constituents])
        thin_proxy = int(row[0]) if row else 0

        # proxy constituents = names priced on BOTH this session and the previous one (a proxy
        # constituent must contribute a RETURN, which needs two consecutive marks)
        if len(window_dates) >= 2:
            prev = window_dates[1]
            row = st.one(
                "SELECT COUNT(*) FROM (SELECT ticker FROM sep WHERE date IN (?, ?) "
                "AND closeadj IS NOT NULL GROUP BY ticker HAVING COUNT(DISTINCT date) = 2)",
                [prev, session_date])
            proxy_names = int(row[0]) if row else 0

    actions = st.one("SELECT COUNT(*), MAX(date) FROM actions WHERE date BETWEEN ? AND ?",
                     [earliest or session_date, session_date])
    actions_count, actions_max = (actions or (0, None))

    store_identity = _digest([
        ingest_digest, _iso(max_finalized), _iso(earliest), _iso(latest), len(window_dates),
        session_rows, session_names, duplicates, full_lookback, proxy_names,
        _window_content_hash(st, earliest, session_date),
    ])

    def evidence(verdict: DataReadiness, detail: str, basis: str = "") -> DataFinalityEvidence:
        return DataFinalityEvidence(
            session_date=iso, verdict=verdict, detail=detail, store_path=st.path,
            store_identity_sha256=store_identity, ingest_identity_sha256=ingest_digest,
            ingest_runs_observed=ingest_count, ingest_unclean_datasets=unclean,
            max_finalized_session=_iso(max_finalized), finality_basis=basis,
            session_row_count=int(session_rows or 0), session_constituents=int(session_names or 0),
            session_max_lastupdated=_iso(session_lastupdated),
            lookback_sessions_available=len(window_dates),
            lookback_sessions_required=th.required_history_sessions,
            lookback_earliest=_iso(earliest), lookback_latest=_iso(latest),
            full_lookback_constituents=full_lookback, proxy_constituents=proxy_names,
            thin_proxy_sessions=thin_proxy, duplicate_row_count=duplicates,
            corporate_actions_in_window=int(actions_count or 0),
            corporate_actions_max_date=_iso(actions_max),
            adjustment_reflection_proven=False,
            thresholds=asdict(th))

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
        finished = st.one("SELECT MAX(finished_at) FROM ingest_runs "
                          "WHERE dataset = 'sep' AND LOWER(status) = 'ok'")
        finished_at = finished[0] if finished else None
        if close is None or finished_at is None:
            return evidence(
                DataReadiness.NOT_READY_DATA_STALE,
                f"{iso} is the store's last session and no clean sep ingest completing after its "
                f"close can be evidenced — the session cannot be shown to be final")
        naive_close = close.replace(tzinfo=None)
        stamp = finished_at.replace(tzinfo=None) if isinstance(finished_at, datetime) else None
        if stamp is None or stamp < naive_close:
            return evidence(
                DataReadiness.NOT_READY_DATA_STALE,
                f"the last clean sep ingest finished {_iso(finished_at)}, before the {iso} close "
                f"{_iso(close)} — the session's data is not established as final")
        basis = (f"{iso} is the store's last session; a clean sep ingest finished {_iso(finished_at)}, "
                 f"after the {_iso(close)} close")

    # (3) the session itself
    if session_rows == 0:
        return evidence(DataReadiness.NOT_READY_CURRENT_SESSION_MISSING,
                        f"no usable (closeadj) rows for session {iso}", basis)
    if session_names < th.min_session_constituents:
        return evidence(
            DataReadiness.NOT_READY_CURRENT_SESSION_MISSING,
            f"session {iso} prices {session_names} name(s), below the required "
            f"{th.min_session_constituents} — coverage is partial", basis)

    # (4) self-contradiction
    if duplicates:
        return evidence(DataReadiness.INTEGRITY_STOP_DATA_CONFLICT,
                        f"{duplicates} duplicate (ticker, date) row(s) in the lookback window", basis)

    # (5) history behind the session
    if len(window_dates) < th.required_history_sessions:
        return evidence(
            DataReadiness.NOT_READY_LOOKBACK_INCOMPLETE,
            f"{len(window_dates)} session(s) of history available, {th.required_history_sessions} "
            f"required (252+21 momentum / 200 regime MA)", basis)
    if full_lookback < th.min_full_lookback_constituents:
        return evidence(
            DataReadiness.NOT_READY_LOOKBACK_INCOMPLETE,
            f"{full_lookback} name(s) carry a complete momentum lookback, below the required "
            f"{th.min_full_lookback_constituents}", basis)

    # (6) the market proxy
    if proxy_names < th.min_proxy_constituents:
        return evidence(
            DataReadiness.NOT_READY_PROXY_INCOMPLETE,
            f"{proxy_names} market-proxy constituent(s) priced on {iso} and the prior session, below "
            f"the required {th.min_proxy_constituents}", basis)
    if thin_proxy:
        return evidence(
            DataReadiness.NOT_READY_PROXY_INCOMPLETE,
            f"{thin_proxy} session(s) in the 200-session MA window are below the proxy minimum — the "
            f"regime MA would be computed over incomplete constituents", basis)

    return evidence(DataReadiness.READY, "all registered inputs are present, complete and final", basis)


def _window_content_hash(st: _Store, earliest: Any, session_date: date) -> str:
    """A deterministic content hash over the exact rows the session's construction will read. Bounded
    work (the lookback window, not the whole table) and stable across processes."""
    if earliest is None:
        return "empty"
    row = st.one(
        "SELECT COUNT(*), SUM(hash(ticker || '|' || CAST(date AS VARCHAR) || '|' || "
        "COALESCE(CAST(closeadj AS VARCHAR), ''))::HUGEINT) FROM sep WHERE date BETWEEN ? AND ?",
        [earliest, session_date])
    return f"{row[0]}:{row[1]}" if row else "unavailable"


def verify_store_unchanged(store: Any, session_date: date, expected: DataFinalityEvidence, *,
                           thresholds: FinalityThresholds | None = None) -> None:
    """Re-assess after the session's reads and require the store identity to be unchanged.

    This is how "all data reads resolve from the same immutable ingest version" is established in a
    schema that carries no ingest-version column: not by trusting a field, but by proving the content
    the reads resolved against did not move underneath them.
    """
    now = assess_data_finality(store, session_date, thresholds=thresholds)
    if now.store_identity_sha256 != expected.store_identity_sha256:
        raise DataFinalityError(
            f"the factor store changed during session {session_date.isoformat()}: identity "
            f"{expected.store_identity_sha256[:16]}… → {now.store_identity_sha256[:16]}… — the "
            f"session's reads did not resolve against one immutable state")


def whole_file_digest(path: Path, *, chunk: int = 1 << 20) -> str:
    """SHA-256 of the store file itself — the census-style pin. Optional (it is minutes of I/O on a
    multi-gigabyte store); the content identity above is what every session records."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()
