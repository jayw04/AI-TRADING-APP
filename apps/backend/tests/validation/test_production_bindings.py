"""Production data bindings (R5c) — every data input tied to a real, recorded source.

The load-bearing rule: source authority is DERIVED from a completed ingest's own coverage record, never
asserted by a caller and never inferred from the rows that happen to be present. A store whose ACTIONS
dataset was never ingested — the governed store today — must come back non-authoritative.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import duckdb
import pandas as pd
import pytest

from app.factor_data.store import FactorDataStore
from app.validation.forward_window import FROZEN_CONFIG, IntegrityStop
from app.validation.production_bindings import (
    BindingError,
    build_forward_context,
    declare_action_source,
    pit_price_fn,
)

SESSION = date(2026, 7, 24)
PRIOR = date(2026, 7, 23)
SESSIONS = [PRIOR, SESSION]

REPO_DATA = "docs/review/momentum_daily/equal_weight_validation"


@pytest.fixture
def store(tmp_path):
    st = FactorDataStore(db_path=str(tmp_path / "bind.duckdb"))
    st.ingest_sep(pd.DataFrame([
        {"ticker": "AAA", "date": PRIOR, "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0,
         "volume": 1000, "closeadj": 9.5, "closeunadj": 10.0, "lastupdated": PRIOR},
        {"ticker": "AAA", "date": SESSION, "open": 11.0, "high": 11.0, "low": 11.0, "close": 11.0,
         "volume": 1000, "closeadj": 10.5, "closeunadj": 11.0, "lastupdated": SESSION},
        {"ticker": "BBB", "date": PRIOR, "open": 5.0, "high": 5.0, "low": 5.0, "close": 5.0,
         "volume": 1000, "closeadj": None, "closeunadj": 5.0, "lastupdated": PRIOR},
    ]))
    yield st
    st.close()


# ---- the action-source declaration is derived, never asserted -----------------------------------------

def test_a_store_without_a_coverage_record_is_never_authoritative(store):
    """The governed store's position today: an ACTIONS dataset that was never ingested. 'No rows' is
    not 'no actions', so the declaration must say coverage is unknown."""
    src = declare_action_source(store)
    assert src.authoritative is False
    assert src.coverage_start is None and src.coverage_end is None
    assert "coverage-unrecorded" in src.identity


def test_a_completed_ingest_coverage_record_yields_an_authoritative_declaration(store):
    store.record_dataset_coverage(
        "actions", date(2005, 1, 1), date(2026, 7, 24),
        artifact_sha256="a" * 64, source_identity="sharadar/ACTIONS",
        rows_loaded=1_234_567, recorded_at=datetime(2026, 7, 24, 22, 0))
    src = declare_action_source(store)
    assert src.authoritative is True
    assert src.coverage_start == date(2005, 1, 1) and src.coverage_end == date(2026, 7, 24)
    assert src.identity == "sharadar/ACTIONS@" + "a" * 64        # artifact identity is bound
    assert src.covers(date(2025, 1, 1), SESSION) is True


def test_the_latest_completed_coverage_record_wins(store):
    store.record_dataset_coverage("actions", date(2005, 1, 1), date(2026, 6, 30),
                                  artifact_sha256="a" * 64, source_identity="sharadar/ACTIONS",
                                  rows_loaded=1, recorded_at=datetime(2026, 6, 30, 22, 0))
    store.record_dataset_coverage("actions", date(2005, 1, 1), date(2026, 7, 24),
                                  artifact_sha256="b" * 64, source_identity="sharadar/ACTIONS",
                                  rows_loaded=2, recorded_at=datetime(2026, 7, 24, 22, 0))
    src = declare_action_source(store)
    assert src.coverage_end == date(2026, 7, 24) and src.identity.endswith("b" * 64)


def test_an_unfinished_ingest_does_not_confer_authority(store):
    store.record_dataset_coverage("actions", date(2005, 1, 1), date(2026, 7, 24),
                                  artifact_sha256="a" * 64, source_identity="sharadar/ACTIONS",
                                  rows_loaded=0, recorded_at=datetime(2026, 7, 24, 22, 0),
                                  status="running")
    assert declare_action_source(store).authoritative is False


def test_a_coverage_record_without_an_artifact_identity_is_not_authoritative(store):
    store.record_dataset_coverage("actions", date(2005, 1, 1), date(2026, 7, 24),
                                  artifact_sha256="", source_identity="sharadar/ACTIONS",
                                  rows_loaded=1, recorded_at=datetime(2026, 7, 24, 22, 0))
    src = declare_action_source(store)
    assert src.authoritative is False and "coverage-incomplete" in src.identity


def test_a_store_predating_the_coverage_table_is_not_authoritative(tmp_path):
    con = duckdb.connect(str(tmp_path / "old.duckdb"))
    con.execute("CREATE TABLE sep (ticker VARCHAR, date DATE, closeadj DOUBLE)")
    src = declare_action_source(con)                              # no dataset_coverage table at all
    assert src.authoritative is False
    con.close()


def test_actions_rows_alone_never_confer_coverage(store):
    """Rows present without a coverage record prove what was loaded, not what was requested — the
    invented-coverage move the governance forbids."""
    store.con.execute("INSERT INTO actions VALUES (?, 'dividend', 'AAA', 'AAA', 1.0, NULL)", [PRIOR])
    assert declare_action_source(store).authoritative is False


def test_a_non_queryable_store_fails_closed():
    with pytest.raises(BindingError, match="not a queryable store"):
        declare_action_source(object())


# ---- point-in-time prices ------------------------------------------------------------------------------

def test_the_price_function_reads_the_session_only(store):
    price = pit_price_fn(store)
    assert price("AAA", SESSION) == pytest.approx(10.5)          # closeadj, not close
    assert price("AAA", PRIOR) == pytest.approx(9.5)


def test_a_missing_or_unpriced_mark_returns_none_rather_than_a_substitute(store):
    price = pit_price_fn(store)
    assert price("BBB", PRIOR) is None                            # closeadj IS NULL
    assert price("BBB", SESSION) is None                          # no row at all
    assert price("ZZZ", SESSION) is None                          # unknown ticker


def test_the_price_function_cannot_see_a_later_session(store):
    """There is no fallback, no forward fill and no 'last known price': a future session's price is
    unreachable because it is never queried."""
    price = pit_price_fn(store)
    assert price("AAA", SESSION - timedelta(days=30)) is None     # before any data
    assert price("AAA", SESSION + timedelta(days=1)) is None      # after the last session


# ---- the per-session context is built on the FROZEN bindings ---------------------------------------------

def test_the_context_carries_the_frozen_bindings(tmp_path):
    ctx = build_forward_context(SESSION, dgs3mo_path=tmp_path / "DGS3MO.csv",
                                trial_ledger_path=tmp_path / "ledger.json", ledger_account_id=901)
    assert ctx.session_date == SESSION
    assert ctx.config == FROZEN_CONFIG                            # not a caller-supplied dict
    assert ctx.effective_dsr_trial_count == 45
    assert ctx.ledger_is_shadow_or_separate_paper is True
    assert ctx.references_account4_capital is False
    assert ctx.references_retired_baseline is False


def test_the_context_refuses_account_4_as_the_ledger(tmp_path):
    with pytest.raises(IntegrityStop, match="never be Account 4"):
        build_forward_context(SESSION, dgs3mo_path=tmp_path / "d.csv",
                              trial_ledger_path=tmp_path / "l.json", ledger_account_id=4)
