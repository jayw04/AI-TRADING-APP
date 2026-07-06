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


def test_get_sectors_maps_known_and_unknown(tmp_path) -> None:
    """P10 §3: get_sectors maps each requested ticker to its sector; unknown
    tickers → None; empty input → {}."""
    import pandas as pd

    s = FactorDataStore(db_path=str(tmp_path / "sec.duckdb"))
    try:
        tk = pd.DataFrame([
            dict(ticker="AAA", name="A Inc", exchange="NYSE", category="Domestic Common Stock",
                 sector="Technology", industry="Semiconductors", isdelisted="N",
                 firstpricedate="2020-01-01", lastpricedate="2026-01-01", lastupdated="2026-01-01"),
            dict(ticker="BBB", name="B Inc", exchange="NYSE", category="Domestic Common Stock",
                 sector="Energy", industry="Oil & Gas", isdelisted="N",
                 firstpricedate="2020-01-01", lastpricedate="2026-01-01", lastupdated="2026-01-01"),
        ])
        s.ingest_tickers(tk)
        assert s.get_sectors(["AAA", "BBB", "ZZZ"]) == {
            "AAA": "Technology", "BBB": "Energy", "ZZZ": None,
        }
        assert s.get_sectors([]) == {}
    finally:
        s.close()


# ---- SF1 fundamentals (ADR 0023) -----------------------------------------------

def _sf1_frame(extra_cols: bool = False):
    """A synthetic Sharadar SF1 slice (two quarters of AAPL ART)."""
    import pandas as pd

    rows = [
        dict(ticker="AAPL", dimension="ART", calendardate="2025-12-31", datekey="2026-01-30",
             reportperiod="2025-12-31", lastupdated="2026-02-01", marketcap=3.8e12, pe=32.3,
             pb=43.2, ps=9.0, roe=1.6, roic=0.55, grossmargin=0.47, de=1.4, fcf=1.0e11,
             revenue=4.0e11, netinc=1.0e11),
        dict(ticker="AAPL", dimension="ART", calendardate="2026-03-31", datekey="2026-05-01",
             reportperiod="2026-03-31", lastupdated="2026-05-02", marketcap=4.1e12, pe=33.6,
             pb=38.6, ps=9.2, roe=1.47, roic=0.52, grossmargin=0.48, de=1.3, fcf=1.1e11,
             revenue=4.1e11, netinc=1.05e11),
    ]
    df = pd.DataFrame(rows)
    if extra_cols:
        df["unstored_vendor_col"] = 123  # extra columns must be ignored, not crash
        df = df.drop(columns=["ps"])  # a missing curated column must become NULL, not crash
    return df


def test_sf1_schema_and_pk(store: FactorDataStore) -> None:
    tables = {r[0] for r in store.con.execute("SHOW TABLES").fetchall()}
    assert "sf1_fundamentals" in tables
    pk = {r[1] for r in store.con.execute("PRAGMA table_info('sf1_fundamentals')").fetchall() if r[5]}
    assert pk == {"ticker", "dimension", "calendardate", "datekey"}


def test_ingest_sf1_populates_and_casts(tmp_path) -> None:
    s = FactorDataStore(db_path=str(tmp_path / "sf1.duckdb"))
    try:
        assert s.ingest_sf1(_sf1_frame()) == 2
        assert s.row_count("sf1_fundamentals") == 2
        # latest-known row, columns cast to real numbers (no all-NULL trap)
        row = s.con.execute(
            "SELECT pe, pb, roe, marketcap, grossmargin FROM sf1_fundamentals "
            "WHERE ticker='AAPL' AND dimension='ART' ORDER BY datekey DESC LIMIT 1"
        ).fetchone()
        assert row == (33.6, 38.6, 1.47, 4.1e12, 0.48)
        # datekey is a real DATE (PIT), distinct from calendardate
        dk, cd = s.con.execute(
            "SELECT datekey, calendardate FROM sf1_fundamentals ORDER BY datekey DESC LIMIT 1"
        ).fetchone()
        assert str(dk) == "2026-05-01" and str(cd) == "2026-03-31"
    finally:
        s.close()


def test_ingest_sf1_idempotent_and_reindex_robust(tmp_path) -> None:
    s = FactorDataStore(db_path=str(tmp_path / "sf1idem.duckdb"))
    try:
        s.ingest_sf1(_sf1_frame())
        s.ingest_sf1(_sf1_frame(extra_cols=True))  # re-ingest: extra col ignored, missing col → NULL
        assert s.row_count("sf1_fundamentals") == 2  # converged, not doubled
        # the dropped 'ps' column is NULL after the second (reindexed) ingest
        ps = s.con.execute("SELECT ps FROM sf1_fundamentals ORDER BY datekey DESC LIMIT 1").fetchone()
        assert ps[0] is None
    finally:
        s.close()


def test_get_sf1_asof_is_point_in_time(tmp_path) -> None:
    s = FactorDataStore(db_path=str(tmp_path / "sf1asof.duckdb"))
    try:
        s.ingest_sf1(_sf1_frame())  # AAPL ART, datekeys 2026-01-30 (pe 32.3) and 2026-05-01 (pe 33.6)
        # as of 2026-03-01 only the Jan filing is knowable (the May one is in the future)
        early = s.get_sf1_asof(["AAPL"], date(2026, 3, 1))
        assert list(early.index) == ["AAPL"]
        assert early.loc["AAPL", "pe"] == 32.3
        # as of 2026-06-01 the latest-known is the May filing
        assert s.get_sf1_asof(["AAPL"], date(2026, 6, 1)).loc["AAPL", "pe"] == 33.6
        # before any filing → empty; unknown ticker → absent (not error); empty input → empty
        assert s.get_sf1_asof(["AAPL"], date(2026, 1, 1)).empty
        assert "ZZZ" not in s.get_sf1_asof(["AAPL", "ZZZ"], date(2026, 6, 1)).index
        assert s.get_sf1_asof([], date(2026, 6, 1)).empty
    finally:
        s.close()
