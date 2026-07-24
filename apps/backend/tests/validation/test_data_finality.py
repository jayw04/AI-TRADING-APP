"""Forward-validation data-finality gate (R5a) — a session is evaluated only on final, complete data.

Every verdict in the taxonomy is exercised against a synthetic store built on the REAL schema, plus the
two constructed properties the schema cannot supply directly: the store-identity check that stands in
for a missing ingest-version column, and the recorded limit on corporate-action reflection.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from app.factor_data.store import FactorDataStore
from app.validation.data_finality import (
    DataFinalityError,
    DataReadiness,
    FinalityThresholds,
    assess_data_finality,
    verify_store_unchanged,
    whole_file_digest,
)

SESSION = date(2026, 7, 24)                      # a real XNYS session (the frozen forward start)
PRIOR = date(2026, 7, 23)
NEXT = date(2026, 7, 27)

# Small but structurally complete: enough history for the registered lookbacks, enough names for the
# coverage minima, sized so a test store builds in well under a second.
N_SESSIONS = 300
N_TICKERS = 260
THRESHOLDS = FinalityThresholds(min_session_constituents=200, min_full_lookback_constituents=100,
                                min_proxy_constituents=100)
# For the proxy tests only: a hole anywhere in the window also truncates those names' momentum
# lookback, so the lookback minimum is relaxed to isolate the proxy checks.
PROXY_THRESHOLDS = FinalityThresholds(min_session_constituents=200, min_full_lookback_constituents=10,
                                      min_proxy_constituents=100)


def _sessions(end: date, n: int) -> list[date]:
    """`n` weekday sessions ending at `end` (a calendar stand-in — the gate reads the store's own
    session dates, not an exchange calendar)."""
    out: list[date] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def _sep_frame(sessions: list[date], tickers: list[str]) -> pd.DataFrame:
    rows = [{"ticker": t, "date": d, "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0,
             "volume": 1_000_000, "closeadj": 10.0 + i * 0.01, "closeunadj": 10.0,
             "lastupdated": d}
            for i, d in enumerate(sessions) for t in tickers]
    return pd.DataFrame(rows)


@pytest.fixture
def store(tmp_path):
    """A complete store: 300 sessions through the session AFTER the one under test, 260 names."""
    st = FactorDataStore(db_path=str(tmp_path / "factor.duckdb"))
    sessions = _sessions(NEXT, N_SESSIONS)
    tickers = [f"T{i:04d}" for i in range(N_TICKERS)]
    st.ingest_sep(_sep_frame(sessions, tickers))
    st.record_ingest_run("sep", datetime(2026, 7, 27, 21, 0), datetime(2026, 7, 27, 21, 5),
                         len(sessions) * len(tickers), "ok")
    yield st
    st.close()


def _assess(store, session=SESSION, **kw):
    return assess_data_finality(store, session, thresholds=kw.pop("thresholds", THRESHOLDS), **kw)


# ---- READY ---------------------------------------------------------------------------------------

def test_a_complete_store_is_ready(store):
    ev = _assess(store)
    assert ev.verdict is DataReadiness.READY and ev.ready
    assert ev.session_constituents == N_TICKERS
    assert ev.lookback_sessions_available >= ev.lookback_sessions_required
    assert ev.full_lookback_constituents == N_TICKERS
    assert ev.proxy_constituents == N_TICKERS
    assert ev.thin_proxy_sessions == 0 and ev.duplicate_row_count == 0
    assert "settled" in ev.finality_basis                      # a later session exists


def test_evidence_is_open_provenance_only(store):
    d = _assess(store).to_open_provenance()
    assert d["verdict"] == "READY"
    assert d["thresholds"]["min_proxy_constituents"] == 100     # what was required is recorded
    assert d["adjustment_reflection_proven"] is False           # the limit is stated, not implied
    # counts, dates, digests and verdicts only — nothing that could inform a performance judgement
    forbidden = {"strategy_return", "sharpe", "equity", "pnl", "cumulative_return", "turnover"}
    assert not (forbidden & set(d))


# ---- staleness + the finality basis ---------------------------------------------------------------

def test_a_store_whose_cutoff_precedes_the_session_is_stale(store):
    store.con.execute("DELETE FROM sep WHERE date >= ?", [SESSION])
    ev = _assess(store)
    assert ev.verdict is DataReadiness.NOT_READY_DATA_STALE
    assert ev.max_finalized_session == PRIOR.isoformat()


def test_an_empty_store_is_stale(tmp_path):
    st = FactorDataStore(db_path=str(tmp_path / "empty.duckdb"))
    ev = _assess(st)
    assert ev.verdict is DataReadiness.NOT_READY_DATA_STALE
    assert ev.max_finalized_session is None
    st.close()


def test_the_last_session_needs_an_ingest_that_finished_after_its_close(store):
    """When the session IS the store's cutoff, "a later session exists" cannot establish finality: a
    clean sep ingest must be evidenced as having completed after that session's close."""
    store.con.execute("DELETE FROM sep WHERE date > ?", [SESSION])
    store.con.execute("DELETE FROM ingest_runs")
    ev = _assess(store)
    assert ev.verdict is DataReadiness.NOT_READY_DATA_STALE
    assert "final" in ev.detail

    store.record_ingest_run("sep", datetime(2026, 7, 24, 12, 0), datetime(2026, 7, 24, 19, 0),
                            10, "ok")                            # finished BEFORE the 20:00Z close
    assert _assess(store).verdict is DataReadiness.NOT_READY_DATA_STALE

    store.con.execute("DELETE FROM ingest_runs")
    store.record_ingest_run("sep", datetime(2026, 7, 24, 21, 0), datetime(2026, 7, 24, 21, 30),
                            10, "ok")                            # finished AFTER the close
    ev = _assess(store)
    assert ev.verdict is DataReadiness.READY
    assert "after the" in ev.finality_basis


# ---- the session itself ---------------------------------------------------------------------------

def test_a_missing_session_is_refused(store):
    store.con.execute("DELETE FROM sep WHERE date = ?", [SESSION])
    ev = _assess(store)
    assert ev.verdict is DataReadiness.NOT_READY_CURRENT_SESSION_MISSING
    assert ev.session_row_count == 0


def test_partial_session_coverage_is_refused(store):
    store.con.execute("DELETE FROM sep WHERE date = ? AND ticker > 'T0100'", [SESSION])
    ev = _assess(store)
    assert ev.verdict is DataReadiness.NOT_READY_CURRENT_SESSION_MISSING
    assert ev.session_constituents < THRESHOLDS.min_session_constituents


def test_unpriced_rows_do_not_count_as_coverage(store):
    store.con.execute("UPDATE sep SET closeadj = NULL WHERE date = ? AND ticker > 'T0050'", [SESSION])
    ev = _assess(store)
    assert ev.verdict is DataReadiness.NOT_READY_CURRENT_SESSION_MISSING


# ---- self-contradicting data ----------------------------------------------------------------------

def test_duplicate_session_rows_are_an_integrity_stop(tmp_path):
    """`sep` normally has a (ticker, date) primary key. A store that somehow holds duplicates is
    contradicting itself, and the gate must say so rather than average over it."""
    con = duckdb.connect(str(tmp_path / "dup.duckdb"))
    con.execute("CREATE TABLE sep (ticker VARCHAR, date DATE, closeadj DOUBLE, lastupdated DATE)")
    con.execute("CREATE TABLE actions (date DATE, action VARCHAR, ticker VARCHAR)")
    con.execute("CREATE TABLE ingest_runs (dataset VARCHAR, started_at TIMESTAMP, "
                "finished_at TIMESTAMP, rows BIGINT, status VARCHAR)")
    sessions = _sessions(NEXT, N_SESSIONS)
    rows = [(f"T{i:04d}", d, 10.0, d) for d in sessions for i in range(N_TICKERS)]
    con.executemany("INSERT INTO sep VALUES (?, ?, ?, ?)", rows)
    con.execute("INSERT INTO sep VALUES ('T0000', ?, 11.0, ?)", [SESSION, SESSION])   # the duplicate
    ev = _assess(con)
    assert ev.verdict is DataReadiness.INTEGRITY_STOP_DATA_CONFLICT
    assert ev.duplicate_row_count == 1
    con.close()


# ---- lookback completeness -------------------------------------------------------------------------

def test_short_history_is_refused(tmp_path):
    st = FactorDataStore(db_path=str(tmp_path / "short.duckdb"))
    sessions = _sessions(NEXT, 100)                              # far short of 252 + 21
    st.ingest_sep(_sep_frame(sessions, [f"T{i:04d}" for i in range(N_TICKERS)]))
    ev = _assess(st)
    assert ev.verdict is DataReadiness.NOT_READY_LOOKBACK_INCOMPLETE
    assert ev.lookback_sessions_required == 273                  # 252 + 21 dominates the 200 MA
    assert ev.lookback_sessions_available < ev.lookback_sessions_required
    st.close()


def test_names_without_a_complete_lookback_do_not_count(store):
    """Enough names priced today, but their history is truncated — the momentum window cannot be
    computed for them, so the session is refused."""
    cutoff = _sessions(NEXT, N_SESSIONS)[-40]
    store.con.execute("DELETE FROM sep WHERE date < ? AND ticker > 'T0010'", [cutoff])
    ev = _assess(store)
    assert ev.verdict is DataReadiness.NOT_READY_LOOKBACK_INCOMPLETE
    assert ev.full_lookback_constituents < THRESHOLDS.min_full_lookback_constituents


# ---- market-proxy coverage -------------------------------------------------------------------------

def test_thin_proxy_constituents_on_the_session_are_refused(store):
    """A proxy constituent must contribute a RETURN, so it needs a mark on this session AND the prior
    one. Losing the prior session's coverage makes the proxy incomplete even though today looks fine.

    The lookback minimum is relaxed here so the PROXY check is what the verdict reports: a hole on any
    window session also truncates those names' momentum lookback, which would otherwise fire first."""
    store.con.execute("DELETE FROM sep WHERE date = ? AND ticker > 'T0050'", [PRIOR])
    ev = _assess(store, thresholds=PROXY_THRESHOLDS)
    assert ev.verdict is DataReadiness.NOT_READY_PROXY_INCOMPLETE
    assert ev.proxy_constituents <= 51


def test_a_thin_session_inside_the_ma_window_is_refused(store):
    thin_day = _sessions(NEXT, N_SESSIONS)[-30]                  # inside the 200-session MA window
    store.con.execute("DELETE FROM sep WHERE date = ? AND ticker > 'T0020'", [thin_day])
    ev = _assess(store, thresholds=PROXY_THRESHOLDS)
    assert ev.verdict is DataReadiness.NOT_READY_PROXY_INCOMPLETE
    assert ev.thin_proxy_sessions >= 1


# ---- ingest state -----------------------------------------------------------------------------------

def test_a_running_ingest_blocks_the_session(store):
    store.record_ingest_run("sep", datetime(2026, 7, 27, 22, 0), datetime(2026, 7, 27, 22, 0),
                            0, "running")
    ev = _assess(store)
    assert ev.verdict is DataReadiness.NOT_READY_INGEST_IN_PROGRESS
    assert "sep:running" in ev.ingest_unclean_datasets


def test_a_failed_latest_ingest_blocks_the_session(store):
    store.record_ingest_run("sep", datetime(2026, 7, 27, 22, 0), datetime(2026, 7, 27, 22, 5),
                            0, "failed")
    ev = _assess(store)
    assert ev.verdict is DataReadiness.NOT_READY_INGEST_IN_PROGRESS
    assert "sep:failed" in ev.ingest_unclean_datasets


def test_an_earlier_failure_followed_by_a_clean_run_does_not_block(store):
    store.record_ingest_run("sep", datetime(2026, 7, 27, 20, 0), datetime(2026, 7, 27, 20, 5),
                            0, "failed")
    store.record_ingest_run("sep", datetime(2026, 7, 27, 22, 0), datetime(2026, 7, 27, 22, 5),
                            10, "ok")
    assert _assess(store).verdict is DataReadiness.READY


# ---- the constructed "one immutable version" property ------------------------------------------------

def test_store_identity_is_stable_across_repeated_assessments(store):
    assert _assess(store).store_identity_sha256 == _assess(store).store_identity_sha256


def test_a_store_that_changes_during_the_session_is_an_integrity_stop(store):
    before = _assess(store)
    verify_store_unchanged(store, SESSION, before, thresholds=THRESHOLDS)      # unchanged: silent
    store.con.execute("UPDATE sep SET closeadj = closeadj + 1 WHERE date = ? AND ticker = 'T0000'",
                      [SESSION])
    with pytest.raises(DataFinalityError, match="changed during session"):
        verify_store_unchanged(store, SESSION, before, thresholds=THRESHOLDS)


def test_identity_moves_when_a_row_is_added_outside_the_session(store):
    before = _assess(store).store_identity_sha256
    store.con.execute("INSERT INTO sep (ticker, date, closeadj) VALUES ('ZZZZ', ?, 5.0)", [PRIOR])
    assert _assess(store).store_identity_sha256 != before


# ---- misuse fails closed ------------------------------------------------------------------------------

def test_a_non_queryable_store_fails_closed():
    with pytest.raises(DataFinalityError, match="not a queryable store"):
        assess_data_finality(object(), SESSION)


def test_a_store_without_the_expected_tables_fails_closed(tmp_path):
    con = duckdb.connect(str(tmp_path / "bare.duckdb"))
    with pytest.raises(DataFinalityError, match="store query failed"):
        assess_data_finality(con, SESSION)
    con.close()


# ---- the optional census-style whole-file pin ----------------------------------------------------------

def test_whole_file_digest_is_deterministic(tmp_path: Path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"forward-validation" * 1000)
    assert whole_file_digest(p) == whole_file_digest(p)
    assert len(whole_file_digest(p)) == 64
