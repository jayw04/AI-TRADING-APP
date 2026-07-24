"""Production data bindings (R5c) — every data input tied to a real, recorded source.

The load-bearing rule: source authority is DERIVED from a completed ingest's own coverage record, never
asserted by a caller and never inferred from the rows that happen to be present. A store whose ACTIONS
dataset was never ingested — the governed store today — must come back non-authoritative.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

import duckdb
import pandas as pd
import pytest

from app.factor_data.store import FactorDataStore
from app.validation.forward_window import FROZEN_CONFIG, IntegrityStop
from app.validation.production_bindings import (
    BindingError,
    PriceUnavailable,
    build_forward_context,
    declare_action_source,
    pit_price_fn,
    strict_pit_price_fn,
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
    assert "unlinked" in src.identity        # no coverage row -> nothing to link to


def _finalize(store, artifact, *, dataset="actions", rows=3,
              coverage=(date(2005, 1, 1), date(2026, 7, 24)),
              started=datetime(2026, 7, 24, 21, 0), finished=datetime(2026, 7, 24, 22, 0),
              source="sharadar/ACTIONS") -> str:
    """The governed completion protocol: the ONLY path that can produce authoritative coverage."""
    return store.finalize_dataset_ingest(
        dataset, started_at=started, finished_at=finished, rows=rows,
        coverage_start=coverage[0], coverage_end=coverage[1], artifact_path=artifact,
        source_identity=source)


@pytest.fixture
def artifact(tmp_path):
    p = tmp_path / "ACTIONS.csv"
    p.write_bytes(b"date,action,ticker,value\n2026-07-24,dividend,AAA,1.0\n")
    return p


def test_a_finalized_ingest_yields_an_authoritative_declaration(store, artifact):
    run_id = _finalize(store, artifact)
    src = declare_action_source(store)
    assert src.authoritative is True
    assert src.coverage_start == date(2005, 1, 1) and src.coverage_end == date(2026, 7, 24)
    assert src.covers(date(2025, 1, 1), SESSION) is True
    # the identity binds the artifact digest COMPUTED here and the execution that loaded it
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert src.identity == f"sharadar/ACTIONS@{digest}#{run_id}"


def test_the_digest_is_computed_from_the_artifact_not_supplied(store, artifact):
    _finalize(store, artifact)
    recorded = store.con.execute("SELECT artifact_sha256 FROM dataset_coverage").fetchone()[0]
    assert recorded == hashlib.sha256(artifact.read_bytes()).hexdigest()
    artifact.write_bytes(b"different bytes entirely\n")
    assert recorded != hashlib.sha256(artifact.read_bytes()).hexdigest()   # not recomputed later


def test_the_latest_finalized_ingest_wins(store, artifact, tmp_path):
    _finalize(store, artifact, coverage=(date(2005, 1, 1), date(2026, 6, 30)),
              finished=datetime(2026, 6, 30, 22, 0))
    later = tmp_path / "ACTIONS-2.csv"
    later.write_bytes(b"newer artifact\n")
    _finalize(store, later, coverage=(date(2005, 1, 1), date(2026, 7, 24)),
              finished=datetime(2026, 7, 24, 22, 0))
    src = declare_action_source(store)
    assert src.coverage_end == date(2026, 7, 24)
    assert src.identity.split("@")[1].startswith(hashlib.sha256(later.read_bytes()).hexdigest())


def test_an_absent_artifact_cannot_be_finalized(store, tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        _finalize(store, tmp_path / "nope.csv")
    assert declare_action_source(store).authoritative is False


def test_an_inverted_window_cannot_be_finalized(store, artifact):
    with pytest.raises(ValueError, match="after coverage_end"):
        _finalize(store, artifact, coverage=(date(2026, 7, 24), date(2005, 1, 1)))
    assert declare_action_source(store).authoritative is False


def test_an_empty_source_identity_cannot_be_finalized(store, artifact):
    with pytest.raises(ValueError, match="source_identity"):
        _finalize(store, artifact, source="   ")
    assert declare_action_source(store).authoritative is False


# ---- the artifact itself is re-verified, not merely referenced -------------------------------------

def test_a_deleted_artifact_revokes_authority(store, artifact):
    _finalize(store, artifact)
    assert declare_action_source(store).authoritative is True
    artifact.unlink()
    src = declare_action_source(store)
    assert src.authoritative is False and "artifact-missing" in src.identity


def test_changed_artifact_bytes_revoke_authority(store, artifact):
    """Authority rests on an immutable artifact: same path, different bytes is a different artifact."""
    _finalize(store, artifact)
    artifact.write_bytes(b"date,action,ticker,value\n2026-07-24,dividend,AAA,2.0\n")
    src = declare_action_source(store)
    assert src.authoritative is False and "artifact-digest-mismatch" in src.identity


def test_an_artifact_path_pointing_at_a_different_file_revokes_authority(store, artifact, tmp_path):
    _finalize(store, artifact)
    other = tmp_path / "OTHER.csv"
    other.write_bytes(b"a completely different artifact\n")
    store.con.execute("UPDATE dataset_coverage SET artifact_path = ?", [str(other)])
    src = declare_action_source(store)
    assert src.authoritative is False and "artifact-digest-mismatch" in src.identity


def test_a_truncated_artifact_revokes_authority(store, artifact):
    _finalize(store, artifact)
    artifact.write_bytes(b"")
    assert declare_action_source(store).authoritative is False


def test_an_unchanged_artifact_remains_authoritative(store, artifact):
    _finalize(store, artifact)
    assert declare_action_source(store).authoritative is True
    assert declare_action_source(store).authoritative is True     # re-read, not cached by path
    artifact.touch()                                              # metadata changes, bytes do not
    assert declare_action_source(store).authoritative is True


# ---- hand-written coverage rows confer nothing ------------------------------------------------------

def _insert_raw_coverage(store, **over) -> None:
    row = dict(dataset="actions", ingest_run_id="no-such-run", coverage_start=date(2005, 1, 1),
               coverage_end=date(2026, 7, 24), artifact_sha256="a" * 64,
               artifact_path="/invented/ACTIONS.csv", source_identity="sharadar/ACTIONS",
               rows_loaded=3, recorded_at=datetime(2026, 7, 24, 22, 0), status="ok")
    row.update(over)
    store.con.execute(
        "INSERT INTO dataset_coverage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [row["dataset"], row["ingest_run_id"], row["coverage_start"], row["coverage_end"],
         row["artifact_sha256"], row["artifact_path"], row["source_identity"], row["rows_loaded"],
         row["recorded_at"], row["status"]])


def test_an_unlinked_coverage_row_confers_nothing(store):
    """A hand-inserted row with an invented digest and no real execution behind it."""
    _insert_raw_coverage(store)
    src = declare_action_source(store)
    assert src.authoritative is False and "unlinked" in src.identity


def test_coverage_tied_to_a_failed_or_running_ingest_confers_nothing(store):
    for status in ("failed", "running"):
        rid = store.record_ingest_run("actions", datetime(2026, 7, 24, 21, 0),
                                      datetime(2026, 7, 24, 22, 0), 3, status)
        _insert_raw_coverage(store, ingest_run_id=rid)
        assert declare_action_source(store).authoritative is False


def test_coverage_tied_to_an_unfinished_ingest_confers_nothing(store):
    rid = store.record_ingest_run("actions", datetime(2026, 7, 24, 21, 0), None, 3, "ok")
    _insert_raw_coverage(store, ingest_run_id=rid)
    assert declare_action_source(store).authoritative is False


def test_a_row_count_mismatch_confers_nothing(store):
    rid = store.record_ingest_run("actions", datetime(2026, 7, 24, 21, 0),
                                  datetime(2026, 7, 24, 22, 0), 3, "ok")
    _insert_raw_coverage(store, ingest_run_id=rid, rows_loaded=999)
    assert declare_action_source(store).authoritative is False


def test_coverage_tied_to_another_datasets_ingest_confers_nothing(store):
    rid = store.record_ingest_run("sep", datetime(2026, 7, 24, 21, 0),
                                  datetime(2026, 7, 24, 22, 0), 3, "ok")
    _insert_raw_coverage(store, ingest_run_id=rid)
    assert declare_action_source(store).authoritative is False


def test_an_invalid_artifact_digest_confers_nothing(store):
    rid = store.record_ingest_run("actions", datetime(2026, 7, 24, 21, 0),
                                  datetime(2026, 7, 24, 22, 0), 3, "ok")
    _insert_raw_coverage(store, ingest_run_id=rid, artifact_sha256="not-a-digest")
    src = declare_action_source(store)
    assert src.authoritative is False and "incomplete" in src.identity


def test_an_unclean_ingest_after_the_coverage_supersedes_it(store, artifact):
    """A running or failed ingest since the coverage was recorded may have mutated the dataset."""
    _finalize(store, artifact)
    assert declare_action_source(store).authoritative is True
    store.record_ingest_run("actions", datetime(2026, 7, 25, 3, 0), None, 0, "running")
    src = declare_action_source(store)
    assert src.authoritative is False and "superseded" in src.identity


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

def test_the_strict_price_function_refuses_a_missing_mark(store):
    """The production binding: a security the ledger must mark is never valued at an earlier price."""
    price = strict_pit_price_fn(store)
    assert price("AAA", SESSION) == pytest.approx(10.5)
    with pytest.raises(PriceUnavailable, match="no usable closeadj"):
        price("BBB", PRIOR)                                       # closeadj IS NULL
    with pytest.raises(PriceUnavailable, match="no usable closeadj"):
        price("BBB", SESSION)                                     # no row at all
    with pytest.raises(PriceUnavailable, match="no usable closeadj"):
        price("AAA", SESSION + timedelta(days=1))                 # a later session


def test_the_strict_price_function_refuses_a_nonpositive_mark(store):
    store.con.execute("UPDATE sep SET closeadj = 0 WHERE ticker = 'AAA' AND date = ?", [SESSION])
    with pytest.raises(PriceUnavailable, match="nonpositive"):
        strict_pit_price_fn(store)("AAA", SESSION)


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
