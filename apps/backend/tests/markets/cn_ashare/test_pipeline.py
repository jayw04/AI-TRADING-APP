"""Adapters (fake clients), store provenance, adjustment, provider cross-check and one research run."""

from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path

import pytest

from app.markets import cn_ashare
from app.markets.cn_ashare import adjust, crosscheck, ingest, research
from app.markets.cn_ashare.providers import synthetic as syn
from app.markets.cn_ashare.providers.baostock import BaostockProvider
from app.markets.cn_ashare.providers.base import ProviderError
from app.markets.cn_ashare.providers.tushare import TushareProvider
from app.markets.cn_ashare.store import CnAshareStore, StoreRefusal
from app.markets.context import US_EQUITY, MarketMismatchError, PriceBasis

START, END = date(2024, 1, 2), date(2024, 12, 31)
TS, BS = "cn_synthetic:tushare_shape", "cn_synthetic:baostock_shape"


@pytest.fixture(scope="module")
def truth() -> syn.Truth:
    return syn.build_truth(START, END)


def providers(
    truth: syn.Truth, *, inject: bool = False
) -> tuple[TushareProvider, BaostockProvider]:
    return (
        TushareProvider(syn.FakeTusharePro(truth), source_id=TS),
        BaostockProvider(syn.FakeBaostock(truth, inject_price_mismatch=inject), source_id=BS),
    )


@pytest.fixture
def store(tmp_path: Path) -> CnAshareStore:
    s = CnAshareStore(tmp_path / "cn_ashare_test.duckdb", tmp_path / "cache")
    yield s
    s.close()


# --- adapters ------------------------------------------------------------------------------------


def test_tushare_units_are_converted_to_shares_and_cny(truth: syn.Truth) -> None:
    ts, _ = providers(truth)
    f = ts.daily("000001.SZ", START, END)
    raw = {r["trade_date"]: r for r in f.raw_rows}
    row = f.rows[0]
    src = raw[row["trade_date"].strftime("%Y%m%d")]
    assert row["volume_shares"] == src["vol"] * 100 and row["amount_cny"] == pytest.approx(
        src["amount"] * 1000
    )
    assert row["is_st"] is None and row["trade_status"] == 1
    assert ts.units.volume_unit.startswith("lot")


def test_tushare_omits_suspended_days_and_baostock_lists_them(truth: syn.Truth) -> None:
    ts, bs = providers(truth)
    t_days = {r["trade_date"] for r in ts.daily(syn.SUSPENDED, START, END).rows}
    b_rows = bs.daily(syn.SUSPENDED, START, END).rows
    suspended = {r["trade_date"] for r in b_rows if r["trade_status"] == 0}
    assert len(suspended) == 5 and not suspended & t_days


def test_securities_include_delisted_and_drop_non_stocks(truth: syn.Truth) -> None:
    ts, bs = providers(truth)
    for p in (ts, bs):
        rows = {r["symbol"]: r for r in p.securities().rows}
        assert rows[syn.DELISTED]["status"] == "D" and rows[syn.DELISTED]["delist_date"] is not None
        assert "000001.SH" not in rows  # the Baostock index row
        assert rows[syn.OUT_OF_SCOPE]["board"] == "CHINEXT"


def test_baostock_error_code_raises() -> None:
    class Bad:
        def query_trade_dates(self, **_: str) -> syn._ResultSet:
            return syn._ResultSet([], [], error_code="10001")

    with pytest.raises(ProviderError):
        BaostockProvider(Bad()).trade_calendar(START, END)


def test_tushare_token_comes_from_a_file(tmp_path: Path) -> None:
    with pytest.raises(ProviderError):
        TushareProvider.from_token_file(tmp_path / "missing")
    (tmp_path / "empty").write_text("  ")
    with pytest.raises(ProviderError):
        TushareProvider.from_token_file(tmp_path / "empty")


# --- adjustment ----------------------------------------------------------------------------------


def test_hfq_returns_agree_across_factor_scales_and_qfq_pins_reference(truth: syn.Truth) -> None:
    ts, bs = providers(truth)
    sym = syn.EX_RIGHTS
    a = adjust.hfq(sym, ts.daily(sym, START, END).rows, ts.adj_factors(sym, START, END).rows)
    b = adjust.hfq(sym, bs.daily(sym, START, END).rows, bs.adj_factors(sym, START, END).rows)
    ex = truth.special_days["ex_rights"]
    assert adjust.total_return(a, START, END) == pytest.approx(
        adjust.total_return(b, START, END), rel=1e-5
    )
    raw_drop = (
        truth.bars[sym][ex].close
        / truth.bars[sym][truth.calendar[truth.calendar.index(ex) - 1]].close
    )
    adj_ret = adjust.total_return(b, truth.calendar[truth.calendar.index(ex) - 1], ex)
    assert adj_ret is not None and adj_ret > raw_drop - 1  # the dividend gap is adjusted away
    q = adjust.qfq(
        sym,
        bs.daily(sym, START, END).rows,
        bs.adj_factors(sym, START, END).rows,
        reference_date=END,
    )
    assert q.reference_date == END and q.close[-1] == pytest.approx(
        truth.bars[sym][q.dates[-1]].close
    )


def test_factor_gap_raises() -> None:
    rows = [{"trade_date": date(2024, 6, 3), "factor": 1.0}]
    with pytest.raises(adjust.FactorGap):
        adjust.factor_on(rows, [date(2024, 6, 1)])


# --- store -----------------------------------------------------------------------------------------


def test_store_refuses_us_name_and_us_context(tmp_path: Path, truth: syn.Truth) -> None:
    with pytest.raises(StoreRefusal):
        CnAshareStore(tmp_path / "research.duckdb", tmp_path / "cache")
    s = CnAshareStore(tmp_path / "cn_ashare_x.duckdb", tmp_path / "cache")
    ts, _ = providers(truth)
    with pytest.raises(MarketMismatchError):
        s.record(ts.securities(), US_EQUITY, sample_label="x")
    wrong = cn_ashare.context(exchange="SSE", provider="baostock", price_basis=PriceBasis.RAW)
    with pytest.raises(StoreRefusal):
        s.record(ts.securities(), wrong, sample_label="x")
    s.close()


def test_ingest_records_provenance_and_raw_payload(store: CnAshareStore, truth: syn.Truth) -> None:
    ts, _ = providers(truth)
    res = ingest.ingest_sample(
        store, ts, ["000001.SZ", "999999.SH"], START, END, sample_label=ingest.SYNTHETIC_SAMPLE
    )
    assert res.missing_symbols == ["999999.SH"]
    assert all(store.verify_payload(i) for i in res.ingest_ids)
    row = store.con.execute(
        "SELECT market, currency, timezone, price_basis, units_json, source_class_json, payload_path "
        "FROM ingest_runs WHERE dataset = 'daily'"
    ).fetchone()
    assert row is not None and row[:4] == ("CN_ASHARE", "CNY", "Asia/Shanghai", "RAW_WITH_FACTORS")
    assert json.loads(row[4])["volume_to_shares"] == 100.0
    assert json.loads(row[5])["presentation"] == "SYNTHETIC_OK"
    with gzip.open(row[6], "rb") as fh:
        assert json.loads(fh.read())["rows"][0]["ts_code"] == "000001.SZ"  # raw provider shape kept
    bars = store.daily(TS)
    assert bars and all(b["symbol"] == "000001.SZ" for b in bars)
    assert store.availability()[0]["sample_label"] == ingest.SYNTHETIC_SAMPLE


# --- cross-check -------------------------------------------------------------------------------------


def _both(store: CnAshareStore, truth: syn.Truth, *, inject: bool = False) -> dict:
    for p in providers(truth, inject=inject):
        ingest.ingest_sample(
            store, p, sorted(truth.names), START, END, sample_label=ingest.SYNTHETIC_SAMPLE
        )
    return crosscheck.compare(
        TS, store.daily(TS), store.factors(TS), BS, store.daily(BS), store.factors(BS)
    )


def test_provider_differences_are_all_explained(store: CnAshareStore, truth: syn.Truth) -> None:
    rep = _both(store, truth)
    assert rep["all_explained"], rep["unexplained"]
    assert rep["counts"]["SUSPENDED_ROW_ONLY_IN_ONE"] == 5
    assert {"VOLUME_LOT_ROUNDING", "AMOUNT_UNIT_ROUNDING", "FACTOR_SCALE_ONLY"} <= set(
        rep["explained"]
    )


def test_an_injected_price_difference_is_unexplained(
    store: CnAshareStore, truth: syn.Truth
) -> None:
    rep = _both(store, truth, inject=True)
    assert not rep["all_explained"]
    assert rep["unexplained"]["PRICE_MISMATCH"] == len(truth.names)
    assert rep["examples"]["PRICE_MISMATCH"][0]["field"] == "close"


# --- end-to-end research run --------------------------------------------------------------------------


def test_descriptive_run_end_to_end(store: CnAshareStore, truth: syn.Truth) -> None:
    _, bs = providers(truth)
    res = ingest.ingest_sample(
        store, bs, sorted(truth.names), START, END, sample_label=ingest.SYNTHETIC_SAMPLE
    )
    rep = research.run_descriptive(
        "CN-MOM-20D", provider=BS, open_days=store.open_days(BS), daily=store.daily(BS),
        factors=store.factors(BS), securities=store.securities(BS), sample_label=ingest.SYNTHETIC_SAMPLE,
    )  # fmt: skip
    assert rep["labels"] == [research.DESCRIPTIVE, ingest.SYNTHETIC_SAMPLE]
    assert (
        rep["market_context"]["market"] == "CN_ASHARE"
        and rep["market_context"]["currency"] == "CNY"
    )
    assert syn.OUT_OF_SCOPE in rep["universe"]["excluded"]
    r = rep["result"]
    assert r["fills"] > 0 and r["fees_cny"] > 0
    assert r["gross_return_before_fees"] > r["net_return"]
    assert rep["rules"] and rep["not_modelled"]
    run_id = store.record_run(
        candidate_id="CN-MOM-20D",
        ctx=cn_ashare.context(exchange="SSE+SZSE", provider=BS, price_basis=PriceBasis.HFQ),
        sample_label=ingest.SYNTHETIC_SAMPLE, ingest_ids=res.ingest_ids, report=rep,
    )  # fmt: skip
    assert store.runs()[0]["run_id"] == run_id
    again = research.run_descriptive(
        "CN-MOM-20D", provider=BS, open_days=store.open_days(BS), daily=store.daily(BS),
        factors=store.factors(BS), securities=store.securities(BS), sample_label=ingest.SYNTHETIC_SAMPLE,
    )  # fmt: skip
    assert again["result"] == rep["result"]  # deterministic


def test_a_cash_dividend_on_a_held_stock_is_credited() -> None:
    days = [date(2024, 1, d) for d in (2, 3, 4, 5, 8, 9, 10, 31)] + [
        date(2024, 2, d) for d in (1, 2, 5, 6)
    ]
    sym, ex = "600100.SH", date(2024, 2, 5)
    daily, prev = [], 10.0
    for d in days:
        pre = prev - 0.5 if d == ex else prev
        daily.append({"symbol": sym, "trade_date": d, "open": pre, "high": pre + 0.05, "low": pre - 0.05,
                      "close": pre, "pre_close": pre, "volume_shares": 1e6, "amount_cny": 1e7,
                      "trade_status": 1, "is_st": False})  # fmt: skip
        prev = pre
    factors = [
        {"symbol": sym, "trade_date": days[0], "factor": 1.0, "factor_kind": "hfq_step"},
        {"symbol": sym, "trade_date": ex, "factor": 10.0 / 9.5, "factor_kind": "hfq_step"},
    ]
    secs = [{"symbol": sym, "name": "X", "exchange": "SSE", "board": "MAIN", "list_date": date(2010, 1, 4),
             "delist_date": None, "status": "L"}]  # fmt: skip
    rep = research.run_descriptive(
        "CN-REV-5D", provider=BS, open_days=days, daily=daily, factors=factors, securities=secs,
        sample_label=ingest.SYNTHETIC_SAMPLE,
    )  # fmt: skip
    held = rep["result"]["open_positions_at_end"][sym]
    assert rep["result"]["corporate_action_cash_cny"] == pytest.approx(0.5 * held)


def test_a_held_delisted_stock_is_stranded_and_valued_at_zero() -> None:
    days = [date(2024, 1, d) for d in (2, 3, 4, 5, 8, 9, 10, 11, 12, 15)]
    days += [date(2024, 1, 31), date(2024, 2, 1), date(2024, 2, 2), date(2024, 2, 5)]
    daily, factors = [], []
    sym = "600100.SH"
    for i, d in enumerate(days[:12]):  # trades until 2024-02-01, then gone
        px = 10.0 + 0.1 * i
        daily.append({"symbol": sym, "trade_date": d, "open": px, "high": px + 0.05, "low": px - 0.05,
                      "close": px, "pre_close": px - 0.1, "volume_shares": 1e6, "amount_cny": 1e7,
                      "trade_status": 1, "is_st": False})  # fmt: skip
    factors.append({"symbol": sym, "trade_date": days[0], "factor": 1.0, "factor_kind": "hfq_step"})
    secs = [{"symbol": sym, "name": "X", "exchange": "SSE", "board": "MAIN", "list_date": date(2010, 1, 4),
             "delist_date": date(2024, 2, 2), "status": "D"}]  # fmt: skip
    cand = research.CANDIDATES["CN-REV-5D"]
    rep = research.run_descriptive(
        cand.candidate_id, provider=BS, open_days=days, daily=daily, factors=factors, securities=secs,
        sample_label=ingest.SYNTHETIC_SAMPLE,
    )  # fmt: skip
    stranded = rep["result"]["unexecutable_delisting_exits"]
    assert sym in stranded and stranded[sym]["last_close_value_cny"] > 0
    assert rep["result"]["end_equity_cny"] < rep["capital_cny"]
