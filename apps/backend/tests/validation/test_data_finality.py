"""Forward-validation data-finality gate (R5a) — a session runs only on final, complete data.

Every verdict is exercised against a synthetic store on the REAL schema, driven through the REAL
registered universe construction (`universe_asof`), so coverage is measured the way the decision
measures it. Also pinned here: the value-level store identity (a single changed `closeadj` with every
count, date and coverage figure intact must be caught) and the rule that an unproven corporate-action
adjustment refuses the session rather than sitting beside a READY verdict.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from app.factor_data.store import FactorDataStore
from app.validation.adjustment_verifier import ActionSourceDeclaration, verify_adjustments
from app.validation.data_finality import (
    ConstructionSpec,
    DataFinalityError,
    DataReadiness,
    assess_data_finality,
    verify_store_unchanged,
    whole_file_digest,
)

SESSION = date(2026, 7, 24)                      # a real XNYS session (the frozen forward start)
PRIOR = date(2026, 7, 23)
NEXT = date(2026, 7, 27)

N_SESSIONS = 300
N_TICKERS = 260
# The gate measures against the frozen construction; the only values shrunk for the fixture are the
# universe sizes — a 260-name synthetic store cannot supply a 200/500-name universe.
SPEC = ConstructionSpec(scoring_universe_n=50, proxy_universe_n=80)
REAL_SOURCE = ActionSourceDeclaration(identity="sharadar/ACTIONS@test", authoritative=True,
                                      coverage_start=date(2020, 1, 1), coverage_end=date(2027, 1, 1))


def _sessions(end: date, n: int) -> list[date]:
    out: list[date] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


ALL_SESSIONS = _sessions(NEXT, N_SESSIONS)
TICKERS = [f"T{i:04d}" for i in range(N_TICKERS)]


def _sep_frame(sessions: list[date], tickers: list[str]) -> pd.DataFrame:
    """Dollar volume decreases with the ticker index, so top-N membership is stable: removing a single
    session's row must not silently reshuffle the universe out from under a test. `closeadj` tracks
    `close` exactly, so the fixture contains NO adjustment event — each test introduces the one it is
    about."""
    return pd.DataFrame([
        {"ticker": t, "date": d, "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0,
         "volume": 10_000_000 - 10_000 * int(t[1:]), "closeadj": 10.0,
         "closeunadj": 10.0, "lastupdated": d}
        for d in sessions for t in tickers])


def _tickers_frame(tickers: list[str], first: date, last: date) -> pd.DataFrame:
    return pd.DataFrame([
        {"ticker": t, "name": t, "exchange": "NYSE", "category": "Domestic Common Stock",
         "sector": "Technology", "industry": "Software", "isdelisted": False,
         "firstpricedate": first, "lastpricedate": last, "lastupdated": last} for t in tickers])


@pytest.fixture
def store(tmp_path):
    """A complete store: 300 sessions through the session AFTER the one under test, 260 listed names,
    clean sep + actions ingests, no corporate actions."""
    st = FactorDataStore(db_path=str(tmp_path / "factor.duckdb"))
    st.ingest_sep(_sep_frame(ALL_SESSIONS, TICKERS))
    st.ingest_tickers(_tickers_frame(TICKERS, ALL_SESSIONS[0], ALL_SESSIONS[-1]))
    st.record_ingest_run("sep", datetime(2026, 7, 27, 21, 0), datetime(2026, 7, 27, 21, 5),
                         len(ALL_SESSIONS) * N_TICKERS, "ok")
    st.record_ingest_run("actions", datetime(2026, 7, 27, 21, 5), datetime(2026, 7, 27, 21, 6),
                         0, "ok")
    yield st
    st.close()


class _StubAdjustment:
    """A stand-in for the R5b verifier's evidence object. The gate must DERIVE its verdict from this,
    never from a caller-supplied boolean."""

    def __init__(self, proven: bool, detail: str = "stub"):
        self.proven = proven
        self._detail = detail

    def to_open_provenance(self) -> dict:
        return {"verdict": "PROVEN" if self.proven else "NOT_PROVEN_INSUFFICIENT_DATA",
                "detail": self._detail, "proven": self.proven}


def _proven(window_start, session_date, tickers):
    return _StubAdjustment(True, "all relevant actions reflected (stub)")


def _not_proven(window_start, session_date, tickers):
    return _StubAdjustment(False, "reflection not proven (stub)")


def _assess(store, session=SESSION, **kw):
    kw.setdefault("construction", SPEC)
    kw.setdefault("adjustment_verifier", _proven)
    return assess_data_finality(store, session, **kw)


def _add_action(store, when: date, ticker: str = "T0000") -> None:
    store.con.execute("INSERT INTO actions VALUES (?, 'split', ?, ?, 2.0, NULL)",
                      [when, ticker, ticker])


# ---- READY -----------------------------------------------------------------------------------------

def test_a_complete_store_is_ready(store):
    ev = _assess(store)
    assert ev.verdict is DataReadiness.READY and ev.ready
    assert ev.session_eligible_universe == SPEC.scoring_universe_n
    assert ev.session_complete == ev.session_eligible_universe
    assert ev.session_missing == 0 and ev.session_excluded_by_rule == 0
    assert ev.momentum_candidates == ev.full_lookback_candidates == SPEC.scoring_universe_n
    assert ev.proxy_expected_constituents == ev.proxy_contributing_constituents == SPEC.proxy_universe_n
    assert ev.proxy_sessions_incomplete == 0 and ev.duplicate_row_count == 0
    assert "settled" in ev.finality_basis


def test_evidence_is_open_provenance_only(store):
    d = _assess(store).to_open_provenance()
    assert d["verdict"] == "READY"
    assert d["construction"]["momentum_lookback_sessions"] == 252     # what the construction required
    assert d["construction"]["regime_ma_sessions"] == 200
    forbidden = {"strategy_return", "sharpe", "equity", "pnl", "cumulative_return", "turnover",
                 "scores", "ranking", "weights"}
    assert not (forbidden & set(d))


# ---- staleness + the finality basis ------------------------------------------------------------------

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
    """A session that is merely the store's last row is not final: a clean sep ingest must be evidenced
    as having completed after that session's authoritative close."""
    store.con.execute("DELETE FROM sep WHERE date > ?", [SESSION])
    store.con.execute("DELETE FROM ingest_runs")
    assert _assess(store).verdict is DataReadiness.NOT_READY_DATA_STALE

    store.record_ingest_run("sep", datetime(2026, 7, 24, 12, 0), datetime(2026, 7, 24, 19, 0),
                            10, "ok")                            # BEFORE the 20:00Z close
    assert _assess(store).verdict is DataReadiness.NOT_READY_DATA_STALE

    store.con.execute("DELETE FROM ingest_runs")
    store.record_ingest_run("sep", datetime(2026, 7, 24, 21, 0), datetime(2026, 7, 24, 21, 30),
                            10, "ok")                            # AFTER the close
    ev = _assess(store)
    assert ev.verdict is DataReadiness.READY and "after the" in ev.finality_basis


# ---- session coverage, measured against the REGISTERED universe ---------------------------------------

def test_a_universe_name_without_a_session_mark_is_refused(store):
    store.con.execute("DELETE FROM sep WHERE date = ? AND ticker = 'T0005'", [SESSION])
    ev = _assess(store)
    assert ev.verdict is DataReadiness.NOT_READY_CURRENT_SESSION_MISSING
    assert ev.session_missing == 1 and "T0005" in ev.missing_examples
    assert ev.session_complete == ev.session_eligible_universe - 1


def test_an_unpriced_row_is_not_coverage(store):
    store.con.execute("UPDATE sep SET closeadj = NULL WHERE date = ? AND ticker = 'T0007'", [SESSION])
    ev = _assess(store)
    assert ev.verdict is DataReadiness.NOT_READY_CURRENT_SESSION_MISSING
    assert "T0007" in ev.missing_examples


def test_a_recently_listed_name_is_excluded_from_scoring_by_rule_not_flagged_missing(store):
    """A name listed after the window began cannot carry the consumed history. That is the frozen
    eligibility rule at work, so it leaves the scoring candidate set — it is never counted as a data
    hole, and its short history does not fail the lookback check."""
    late_list = ALL_SESSIONS[-30]
    store.con.execute("UPDATE tickers SET firstpricedate = ? WHERE ticker = 'T0003'", [late_list])
    store.con.execute("DELETE FROM sep WHERE ticker = 'T0003' AND date < ?", [late_list])
    # a large, very liquid recent listing — enough trailing dollar volume to stay in the top-N despite
    # its short history (the realistic case this rule exists for)
    store.con.execute("UPDATE sep SET volume = 100000000 WHERE ticker = 'T0003'")
    ev = _assess(store)
    assert ev.verdict is DataReadiness.READY
    assert ev.session_missing == 0
    assert ev.session_complete == SPEC.scoring_universe_n            # it IS priced today
    assert ev.momentum_candidates == ev.full_lookback_candidates == SPEC.scoring_universe_n - 1


def test_a_delisted_proxy_constituent_is_excluded_by_rule_not_counted_missing(store):
    """The proxy basket is a union over month-ends, so it legitimately contains names that were
    delisted before this session. They drop out of the expected constituents rather than making the
    proxy look incomplete."""
    last_day = ALL_SESSIONS[-10]
    store.con.execute("UPDATE tickers SET isdelisted = true, lastpricedate = ? WHERE ticker = 'T0075'",
                      [last_day])
    store.con.execute("DELETE FROM sep WHERE ticker = 'T0075' AND date > ?", [last_day])
    ev = _assess(store)
    # Without the rule classification this would be PROXY_INCOMPLETE: T0075 sits in the basket union
    # from earlier month-ends and has had no mark for the last ten sessions.
    assert ev.verdict is DataReadiness.READY
    assert ev.proxy_contributing_constituents == ev.proxy_expected_constituents
    assert ev.proxy_sessions_incomplete == 0


def test_an_empty_registered_universe_is_refused(store):
    ev = _assess(store, universe_fn=lambda as_of, n: [])
    assert ev.verdict is DataReadiness.NOT_READY_CURRENT_SESSION_MISSING
    assert "empty" in ev.detail


def test_a_universe_construction_failure_is_refused(store):
    def boom(as_of, n):
        raise RuntimeError("universe unavailable")

    ev = _assess(store, universe_fn=boom)
    assert ev.verdict is DataReadiness.NOT_READY_CURRENT_SESSION_MISSING
    assert "could not be constructed" in ev.detail


# ---- self-contradicting data ---------------------------------------------------------------------------

def test_duplicate_rows_are_an_integrity_stop(tmp_path):
    con = duckdb.connect(str(tmp_path / "dup.duckdb"))
    con.execute("CREATE TABLE sep (ticker VARCHAR, date DATE, open DOUBLE, high DOUBLE, low DOUBLE, "
                "close DOUBLE, volume BIGINT, closeadj DOUBLE, closeunadj DOUBLE, lastupdated DATE)")
    con.execute("CREATE TABLE tickers (ticker VARCHAR, sector VARCHAR, isdelisted BOOLEAN, "
                "firstpricedate DATE, lastpricedate DATE, lastupdated DATE)")
    con.execute("CREATE TABLE actions (date DATE, action VARCHAR, ticker VARCHAR, value DOUBLE, "
                "contraticker VARCHAR)")
    con.execute("CREATE TABLE ingest_runs (dataset VARCHAR, started_at TIMESTAMP, "
                "finished_at TIMESTAMP, rows BIGINT, status VARCHAR)")
    con.executemany("INSERT INTO sep VALUES (?, ?, 10, 10, 10, 10, 1000000, 10, 10, ?)",
                    [(t, d, d) for d in ALL_SESSIONS for t in TICKERS[:60]])
    con.executemany("INSERT INTO tickers VALUES (?, 'Tech', false, ?, ?, ?)",
                    [(t, ALL_SESSIONS[0], ALL_SESSIONS[-1], ALL_SESSIONS[-1]) for t in TICKERS[:60]])
    con.execute("INSERT INTO sep VALUES ('T0000', ?, 10, 10, 10, 10, 1000000, 11, 10, ?)",
                [SESSION, SESSION])                                   # the duplicate
    ev = assess_data_finality(con, SESSION, construction=SPEC,
                              universe_fn=lambda as_of, n: TICKERS[:min(n, 60)])
    assert ev.verdict is DataReadiness.INTEGRITY_STOP_DATA_CONFLICT
    assert ev.duplicate_row_count == 1
    con.close()


# ---- the exact history the scoring candidates consume ----------------------------------------------------

def test_short_history_is_refused(tmp_path):
    st = FactorDataStore(db_path=str(tmp_path / "short.duckdb"))
    sessions = _sessions(NEXT, 100)                                   # far short of 252 + 21
    st.ingest_sep(_sep_frame(sessions, TICKERS))
    st.ingest_tickers(_tickers_frame(TICKERS, sessions[0], sessions[-1]))
    ev = _assess(st)
    assert ev.verdict is DataReadiness.NOT_READY_LOOKBACK_INCOMPLETE
    assert ev.lookback_sessions_required == 273                       # 252 + 21 dominates the 200 MA
    assert ev.lookback_sessions_available < ev.lookback_sessions_required
    st.close()


def test_a_hole_in_a_candidates_lookback_is_refused(store):
    """The name is priced today and its listing dates give it no excuse — one missing mark inside the
    consumed window means the momentum computation cannot see the history it consumes."""
    mid = ALL_SESSIONS[-100]
    store.con.execute("DELETE FROM sep WHERE ticker = 'T0004' AND date = ?", [mid])
    ev = _assess(store)
    assert ev.verdict is DataReadiness.NOT_READY_LOOKBACK_INCOMPLETE
    assert ev.full_lookback_candidates == ev.momentum_candidates - 1
    assert "T0004" in ev.missing_examples


# ---- the market proxy's own constituent set ------------------------------------------------------------------

def test_a_proxy_constituent_missing_todays_mark_is_refused(store):
    """T0060 is in the proxy basket but not in the 50-name scoring universe, so this isolates the proxy
    check: `build_market_proxy` averages with skipna and would silently drop it."""
    store.con.execute("DELETE FROM sep WHERE ticker = 'T0060' AND date = ?", [SESSION])
    ev = _assess(store)
    assert ev.verdict is DataReadiness.NOT_READY_PROXY_INCOMPLETE
    assert ev.proxy_contributing_constituents == ev.proxy_expected_constituents - 1


def test_a_thin_session_inside_the_ma_window_is_refused(store):
    ma_day = ALL_SESSIONS[-30]
    store.con.execute("DELETE FROM sep WHERE ticker = 'T0070' AND date = ?", [ma_day])
    ev = _assess(store)
    assert ev.verdict is DataReadiness.NOT_READY_PROXY_INCOMPLETE
    assert ev.proxy_sessions_incomplete >= 1
    assert ev.proxy_sessions_checked == SPEC.regime_ma_sessions


# ---- ingest state ------------------------------------------------------------------------------------------------

def test_a_running_sep_ingest_blocks_the_session(store):
    store.record_ingest_run("sep", datetime(2026, 7, 27, 22, 0), datetime(2026, 7, 27, 22, 0),
                            0, "running")
    ev = _assess(store)
    assert ev.verdict is DataReadiness.NOT_READY_INGEST_IN_PROGRESS
    assert "sep:running" in ev.ingest_unclean_datasets


def test_an_unclean_actions_ingest_blocks_the_session(store):
    """`actions` is a required dataset: the window's corporate actions are part of the evidence."""
    store.record_ingest_run("actions", datetime(2026, 7, 27, 22, 0), datetime(2026, 7, 27, 22, 5),
                            0, "failed")
    ev = _assess(store)
    assert ev.verdict is DataReadiness.NOT_READY_INGEST_IN_PROGRESS
    assert "actions:failed" in ev.ingest_unclean_datasets


def test_an_earlier_failure_followed_by_a_clean_run_does_not_block(store):
    store.record_ingest_run("sep", datetime(2026, 7, 27, 20, 0), datetime(2026, 7, 27, 20, 5),
                            0, "failed")
    store.record_ingest_run("sep", datetime(2026, 7, 27, 22, 0), datetime(2026, 7, 27, 22, 5),
                            10, "ok")
    assert _assess(store).verdict is DataReadiness.READY


# ---- corporate-action reflection is PROVEN by the verifier, or the session does not run --------------

def test_no_verifier_configured_refuses_the_session(store):
    """An absent action table is not evidence that no action occurred, so nothing can be proven
    without a verifier — even on a store whose `actions` table is empty."""
    ev = assess_data_finality(store, SESSION, construction=SPEC)          # no verifier supplied
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert ev.adjustment_reflection_proven is False
    assert ev.corporate_actions_in_window == 0                            # and it still refuses
    assert "not evidence that none occurred" in ev.detail


def test_the_gate_derives_its_verdict_from_the_verifier_evidence(store):
    ev = _assess(store, adjustment_verifier=_not_proven)
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert ev.adjustment_reflection_proven is False
    assert ev.adjustment_evidence is not None
    assert ev.adjustment_evidence["proven"] is False                      # the evidence is embedded


def test_a_proven_verifier_lets_the_session_proceed(store):
    ev = _assess(store, adjustment_verifier=_proven)
    assert ev.verdict is DataReadiness.READY
    assert ev.adjustment_reflection_proven is True
    assert ev.adjustment_evidence["verdict"] == "PROVEN"


def test_the_relevance_set_passed_to_the_verifier_covers_candidates_and_the_proxy_basket(store):
    """The verifier is asked about the union of the scoring candidates and the whole proxy basket —
    including names that left the universe mid-window but priced into the consumed history."""
    seen: dict = {}

    def capture(window_start, session_date, tickers):
        seen["window_start"] = window_start
        seen["tickers"] = tickers
        return _StubAdjustment(True)

    _assess(store, adjustment_verifier=capture)
    assert seen["window_start"] < SESSION
    assert len(seen["tickers"]) >= SPEC.proxy_universe_n                  # basket ∪ candidates
    assert "T0000" in seen["tickers"] and "T0079" in seen["tickers"]


def test_the_real_verifier_wires_through_the_gate(store):
    """End-to-end with R5b: an authoritative source, a clean window, no undeclared adjustment."""
    def verifier(window_start, session_date, tickers):
        return verify_adjustments(store, window_start=window_start, session_date=session_date,
                                  relevant_tickers=tickers, source=REAL_SOURCE,
                                  store_identity_sha256="test")

    ev = _assess(store, adjustment_verifier=verifier)
    assert ev.verdict is DataReadiness.READY
    assert ev.adjustment_evidence["verdict"] == "NO_RELEVANT_ACTIONS"


def test_the_real_verifier_refuses_an_undeclared_adjustment(store):
    """The vacuous-pass hole, closed end to end: the `actions` table is empty (as the governed store's
    is today) while the adjusted series visibly steps against the raw series."""
    ex_date = ALL_SESSIONS[-40]
    store.con.execute("UPDATE sep SET close = close * 0.5 WHERE ticker = 'T0000' AND date >= ?",
                      [ex_date])

    def verifier(window_start, session_date, tickers):
        return verify_adjustments(store, window_start=window_start, session_date=session_date,
                                  relevant_tickers=tickers, source=REAL_SOURCE,
                                  store_identity_sha256="test")

    ev = _assess(store, adjustment_verifier=verifier)
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert ev.adjustment_evidence["unexplained_adjustment_count"] >= 1


# ---- the value-level store identity ----------------------------------------------------------------------------------------

def test_one_changed_price_is_caught_although_every_aggregate_is_unchanged(store):
    """The load-bearing property: an aggregate-only digest (counts, dates, coverage) would report the
    store unchanged while the decision reads a different price."""
    before = _assess(store)
    store.con.execute("UPDATE sep SET closeadj = closeadj + 0.5 WHERE date = ? AND ticker = 'T0000'",
                      [SESSION])
    after = _assess(store)
    # every aggregate the old digest was built from is identical …
    assert (after.session_row_count, after.session_complete, after.session_missing,
            after.session_eligible_universe, after.lookback_sessions_available,
            after.full_lookback_candidates, after.proxy_contributing_constituents,
            after.duplicate_row_count, after.max_finalized_session,
            after.ingest_identity_sha256) == (
        before.session_row_count, before.session_complete, before.session_missing,
        before.session_eligible_universe, before.lookback_sessions_available,
        before.full_lookback_candidates, before.proxy_contributing_constituents,
        before.duplicate_row_count, before.max_finalized_session, before.ingest_identity_sha256)
    # … and the identity still moves
    assert after.store_identity_sha256 != before.store_identity_sha256
    with pytest.raises(DataFinalityError, match="changed during session"):
        verify_store_unchanged(store, SESSION, before, construction=SPEC)


def test_store_identity_is_stable_across_repeated_assessments(store):
    before = _assess(store)
    verify_store_unchanged(store, SESSION, before, construction=SPEC)      # unchanged: silent
    assert _assess(store).store_identity_sha256 == before.store_identity_sha256


@pytest.mark.parametrize("mutate", [
    pytest.param(lambda st: st.con.execute(
        "UPDATE tickers SET lastpricedate = ? WHERE ticker = 'T0001'", [NEXT + timedelta(days=5)]),
        id="pit-eligibility-row"),
    pytest.param(lambda st: st.con.execute(
        "INSERT INTO actions VALUES (?, 'dividend', 'T0002', 'T0002', 0.5, NULL)", [PRIOR]),
        id="corporate-action"),
    pytest.param(lambda st: st.record_ingest_run(
        "sep", datetime(2026, 7, 28, 1, 0), datetime(2026, 7, 28, 1, 5), 1, "ok"),
        id="ingest-history"),
    pytest.param(lambda st: st.con.execute(
        "UPDATE sep SET volume = volume + 1 WHERE date = ? AND ticker = 'T0000'", [PRIOR]),
        id="consumed-volume-field"),
])
def test_identity_binds_every_consumed_input(store, mutate):
    before = _assess(store).store_identity_sha256
    mutate(store)
    assert _assess(store).store_identity_sha256 != before


# ---- misuse fails closed -------------------------------------------------------------------------------------------------------

def test_a_non_queryable_store_fails_closed():
    with pytest.raises(DataFinalityError, match="not a queryable store"):
        assess_data_finality(object(), SESSION)


def test_a_store_without_the_expected_tables_fails_closed(tmp_path):
    con = duckdb.connect(str(tmp_path / "bare.duckdb"))
    with pytest.raises(DataFinalityError, match="store query failed"):
        assess_data_finality(con, SESSION, construction=SPEC, universe_fn=lambda as_of, n: [])
    con.close()


# ---- the optional census-style whole-file pin ------------------------------------------------------------------------------------

def test_whole_file_digest_is_deterministic(tmp_path: Path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"forward-validation" * 1000)
    assert whole_file_digest(p) == whole_file_digest(p)
    assert len(whole_file_digest(p)) == 64
