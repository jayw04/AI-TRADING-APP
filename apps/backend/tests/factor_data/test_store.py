"""Schema, idempotent ingest, and survivorship-free price access (P9 §1 §4.6)."""

from __future__ import annotations

from datetime import date

import pytest

from app.factor_data.store import FactorDataStore


def test_schema_tables_and_columns(store: FactorDataStore) -> None:
    tables = {r[0] for r in store.con.execute("SHOW TABLES").fetchall()}
    assert {"sep", "tickers", "actions", "ingest_runs"}.issubset(tables)

    sep_cols = {r[1] for r in store.con.execute("PRAGMA table_info('sep')").fetchall()}
    assert {"ticker", "date", "close", "closeadj", "closeunadj", "volume"}.issubset(sep_cols)

    # sep primary key is (ticker, date)
    pk = {
        r[1]
        for r in store.con.execute("PRAGMA table_info('sep')").fetchall()
        if r[5]  # the `pk` flag column
    }
    assert pk == {"ticker", "date"}


def test_idempotent_ingest_converges(synthetic_frames, tmp_path) -> None:
    sep, tickers = synthetic_frames
    s = FactorDataStore(db_path=str(tmp_path / "idem.duckdb"))
    try:
        s.ingest_sep(sep)
        s.ingest_tickers(tickers)
        first_sep, first_tk = s.row_count("sep"), s.row_count("tickers")
        # re-ingest the identical slice — counts and state must not change
        s.ingest_sep(sep)
        s.ingest_tickers(tickers)
        assert s.row_count("sep") == first_sep
        assert s.row_count("tickers") == first_tk
    finally:
        s.close()


def test_actions_ingest_idempotent_per_ticker(tmp_path) -> None:
    import pandas as pd

    s = FactorDataStore(db_path=str(tmp_path / "act.duckdb"))
    try:
        df = pd.DataFrame(
            [
                dict(date="2020-08-31", action="split", ticker="BIGA", name="BIGA Inc",
                     value=4.0, contraticker=None),
                dict(date="2019-05-01", action="dividend", ticker="BIGA", name="BIGA Inc",
                     value=0.2, contraticker=None),
            ]
        )
        s.ingest_actions(df)
        s.ingest_actions(df)  # re-ingest same ticker slice → converges (not doubled)
        assert s.row_count("actions") == 2
    finally:
        s.close()


def test_survivorship_free_delisted_name_has_history(store: FactorDataStore) -> None:
    """★ The single most important test in P9: a delisted name is not 'unknown';
    it has a finite price history ending at its delisting."""
    px = store.get_prices("DEAD1", date(1999, 1, 1), date(2026, 1, 1))
    assert not px.empty
    assert px["date"].max().date() == date(2008, 9, 15)  # the delisting day
    assert px["date"].min().date() >= date(2000, 1, 3)


def test_get_prices_adjusted_vs_raw(store: FactorDataStore) -> None:
    adj = store.get_prices("BIGA", date(2005, 1, 1), date(2005, 12, 31), adjusted=True)
    raw = store.get_prices("BIGA", date(2005, 1, 1), date(2005, 12, 31), adjusted=False)
    assert not adj.empty and not raw.empty
    assert adj["close"].iloc[0] == pytest.approx(90.0)   # closeadj = 100 * 0.9
    assert raw["close"].iloc[0] == pytest.approx(100.0)  # closeunadj


def test_get_prices_unknown_ticker_is_empty_not_error(store: FactorDataStore) -> None:
    px = store.get_prices("NOPE", date(2005, 1, 1), date(2005, 12, 31))
    assert px.empty


def test_read_only_open_of_missing_store_raises(tmp_path) -> None:
    import duckdb

    with pytest.raises(duckdb.Error):
        FactorDataStore(db_path=str(tmp_path / "does_not_exist.duckdb"), read_only=True)


def test_row_count_rejects_unknown_table(store: FactorDataStore) -> None:
    with pytest.raises(ValueError):
        store.row_count("not_a_table")


def test_record_ingest_run_writes_bookkeeping(tmp_path) -> None:
    from datetime import datetime

    s = FactorDataStore(db_path=str(tmp_path / "runs.duckdb"))
    try:
        t0 = datetime(2026, 1, 1, 9, 0, 0)
        t1 = datetime(2026, 1, 1, 9, 5, 0)
        s.record_ingest_run("sep:BIGA", t0, t1, 7155, "ok")
        assert s.row_count("ingest_runs") == 1
        row = s.con.execute(
            "SELECT dataset, rows, status FROM ingest_runs"
        ).fetchone()
        assert row == ("sep:BIGA", 7155, "ok")
    finally:
        s.close()


def test_price_date_bounds_empty_store(tmp_path) -> None:
    s = FactorDataStore(db_path=str(tmp_path / "bounds.duckdb"))
    try:
        assert s.price_date_bounds() == (None, None)
    finally:
        s.close()
