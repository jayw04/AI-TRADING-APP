"""Producer-equivalence: the parquet assembly must hand `produce_decision` the same inputs
the Phase 2B DuckDB path would.

The risk this suite exists for is semantic reconstruction drift, so it does not test adapter
branches independently. It drives ONE set of synthetic source facts into BOTH a DuckDB table and a
parquet payload, assembles through each path, and requires the assembled `MarketData` /
`SecurityData` to be canonically equal and `produce_decision` to emit identical
`SignalDecisionRecord`s.

Per-branch tests can all pass while the assembled whole diverges. This one cannot.
"""

from __future__ import annotations

import io

import numpy as np
import pytest

pa = pytest.importorskip("pyarrow")
duckdb = pytest.importorskip("duckdb")
import pyarrow.parquet as pq  # noqa: E402

from app.research.mr002.phase3b import assembly as ASM  # noqa: E402
from app.research.mr002.spq1.adapters.price_adapter import load_price_series  # noqa: E402
from app.research.mr002.spq1.calendar import RegisteredCalendar  # noqa: E402
from app.research.mr002.spq1.returns import CellStatus, arithmetic_total_returns  # noqa: E402

SESSIONS = [
    "2019-10-03",
    "2019-10-04",
    "2019-10-07",
    "2019-10-08",
    "2019-10-09",
    "2019-10-10",
    "2019-10-11",
    "2019-10-14",
    "2019-10-15",
    "2019-10-16",
]

# One set of source facts, deliberately containing every shape the classifier must distinguish:
#   AAA present throughout; BBB starts late (YOUNG prefix); CCC has an interior hole.
PRICE_ROWS: list[tuple[str, str, float | None, float | None, float | None]] = []
for i, s in enumerate(SESSIONS):
    PRICE_ROWS.append(("AAA", s, 100.0 + i, 90.0 + i, 1_000_000.0 + i))
for i, s in enumerate(SESSIONS):
    if i < 3:
        continue  # BBB not yet listed
    PRICE_ROWS.append(("BBB", s, 50.0 + i, 45.0 + i, 500_000.0 + i))
for i, s in enumerate(SESSIONS):
    if i == 5:
        continue  # CCC interior hole
    PRICE_ROWS.append(("CCC", s, 20.0 + i, 18.0 + i, 250_000.0 + i))

ETF_ROWS = [("SPY", s, 300.0 + i) for i, s in enumerate(SESSIONS)]
ETF_ROWS += [("XLK", s, 80.0 + i * 0.5) for i, s in enumerate(SESSIONS)]
ETF_BY_SECTOR = {"technology": "XLK"}


def _parquet_prices() -> object:
    """The sealed prices table shape, in the committed column order."""
    cols = {
        "ticker": [r[0] for r in PRICE_ROWS],
        "date": [r[1] for r in PRICE_ROWS],
        "open": [(r[2] or 0.0) - 0.5 for r in PRICE_ROWS],
        "high": [(r[2] or 0.0) + 1.0 for r in PRICE_ROWS],
        "low": [(r[2] or 0.0) - 1.0 for r in PRICE_ROWS],
        # close is SPLIT-adjusted only; closeadj is TOTAL-RETURN adjusted. They must differ in the
        # fixture, or a substitution between them is invisible to every comparison below.
        "close": [None if r[2] is None else r[2] * 0.97 for r in PRICE_ROWS],
        "closeadj": [r[2] for r in PRICE_ROWS],
        "closeunadj": [r[3] for r in PRICE_ROWS],
        "volume": [r[4] for r in PRICE_ROWS],
    }
    return _roundtrip(pa.table(cols))


def _parquet_etfs() -> object:
    return _roundtrip(
        pa.table(
            {
                "ticker": [r[0] for r in ETF_ROWS],
                "date": [r[1] for r in ETF_ROWS],
                "adjclose": [r[2] for r in ETF_ROWS],
            }
        )
    )


def _roundtrip(table):
    """Through real parquet bytes, so the test exercises the encoding the run will meet."""
    buf = io.BytesIO()
    pq.write_table(table, buf)
    return pq.read_table(io.BytesIO(buf.getvalue()))


def _duckdb_connection():
    """The same source facts in the Phase 2B DuckDB shape."""
    con = duckdb.connect(":memory:")
    con.execute(
        'create table prices (ticker varchar, "date" varchar, closeadj double, '
        "closeunadj double, close double, open double, volume double)"
    )
    con.executemany(
        "insert into prices values (?, ?, ?, ?, ?, ?, ?)",
        [
            (t, d, ca, cu, None if ca is None else ca * 0.97, (ca or 0.0) - 0.5, v)
            for (t, d, ca, cu, v) in PRICE_ROWS
        ],
    )
    con.execute('create table etf_prices (ticker varchar, "date" varchar, adjclose double)')
    con.executemany("insert into etf_prices values (?, ?, ?)", ETF_ROWS)
    return con


CAL = RegisteredCalendar(tuple(SESSIONS))


# --- the reference assembly: the Phase 2B DuckDB path, mirrored -------------------------------
def _reference_security_series(con, calendar):
    out = {}
    for symbol in sorted({r[0] for r in PRICE_ROWS}):
        series = load_price_series(con, symbol, calendar)
        close = series["closeadj"]
        present = np.isfinite(close)
        if not present.any():
            continue
        first = int(np.argmax(present))
        status = [
            CellStatus.PRESENT
            if present[i]
            else (CellStatus.YOUNG if i < first else CellStatus.UNEXPLAINED_HOLE)
            for i in range(len(calendar))
        ]
        out[symbol] = ASM.SecuritySeries(
            symbol=symbol,
            stock_ret=arithmetic_total_returns(close),
            status=status,
            raw_close=series["closeunadj"],
            raw_volume=series["volume"],
        )
    return out


def _reference_factor_returns(con, calendar, etf_by_sector, spy_ticker="SPY"):
    rows = con.execute('select ticker, "date", adjclose from etf_prices').fetchall()
    series: dict[str, dict[str, float]] = {}
    for tk, d, v in rows:
        series.setdefault(str(tk), {})[str(d)] = float(v)

    def aligned(ticker):
        by = series.get(ticker, {})
        return np.array([by.get(s, np.nan) for s in calendar.sessions], dtype=np.float64)

    spy = arithmetic_total_returns(aligned(spy_ticker))
    sector = {s: arithmetic_total_returns(aligned(etf)) for s, etf in sorted(etf_by_sector.items())}
    return spy, sector


def _canon(arr) -> list[str]:
    """Exact float comparison via hex, so a 1-ulp divergence is visible rather than tolerated."""
    return [float(x).hex() for x in np.asarray(arr, dtype=np.float64)]


# --- equivalence ------------------------------------------------------------------------------
def test_security_series_are_canonically_identical_across_both_paths():
    con = _duckdb_connection()
    reference = _reference_security_series(con, CAL)
    produced = ASM.security_series(_parquet_prices(), CAL)

    assert sorted(produced) == sorted(reference) == ["AAA", "BBB", "CCC"]
    for symbol in reference:
        r, p = reference[symbol], produced[symbol]
        assert _canon(p.stock_ret) == _canon(r.stock_ret), f"{symbol} stock_ret"
        assert _canon(p.raw_close) == _canon(r.raw_close), f"{symbol} raw_close"
        assert _canon(p.raw_volume) == _canon(r.raw_volume), f"{symbol} raw_volume"
        assert p.status == r.status, f"{symbol} CellStatus"


def test_cellstatus_distinguishes_young_from_interior_hole_identically():
    """The classification the whole window machinery keys off must not drift."""
    con = _duckdb_connection()
    reference = _reference_security_series(con, CAL)
    produced = ASM.security_series(_parquet_prices(), CAL)

    assert produced["BBB"].status[:3] == [CellStatus.YOUNG] * 3
    assert produced["CCC"].status[5] == CellStatus.UNEXPLAINED_HOLE
    assert produced["AAA"].status == [CellStatus.PRESENT] * len(SESSIONS)
    for symbol in ("AAA", "BBB", "CCC"):
        assert produced[symbol].status == reference[symbol].status


def test_factor_series_are_canonically_identical_across_both_paths():
    con = _duckdb_connection()
    ref_spy, ref_sector = _reference_factor_returns(con, CAL, ETF_BY_SECTOR)
    spy, sector = ASM.factor_returns(_parquet_etfs(), CAL, ETF_BY_SECTOR, "SPY")
    assert _canon(spy) == _canon(ref_spy)
    assert sorted(sector) == sorted(ref_sector)
    for name in ref_sector:
        assert _canon(sector[name]) == _canon(ref_sector[name]), name


def test_market_data_is_canonically_identical_across_both_paths():
    con = _duckdb_connection()
    ref_spy, ref_sector = _reference_factor_returns(con, CAL, ETF_BY_SECTOR)
    spy, sector = ASM.factor_returns(_parquet_etfs(), CAL, ETF_BY_SECTOR, "SPY")
    observed = {"spy_total_return_series": "id-spy", "sector_etf_source_series": "id-etf"}
    a = ASM.market_data(CAL, ref_spy, ref_sector, observed)
    b = ASM.market_data(CAL, spy, sector, observed)
    assert a.calendar.identity == b.calendar.identity
    assert _canon(a.spy_ret) == _canon(b.spy_ret)
    assert sorted(a.sector_ret) == sorted(b.sector_ret)
    for k in a.sector_ret:
        assert _canon(a.sector_ret[k]) == _canon(b.sector_ret[k])
    assert a.observed_identities == b.observed_identities


def test_a_single_altered_source_fact_breaks_equivalence():
    """The comparison must be capable of failing, or it proves nothing."""
    con = _duckdb_connection()
    reference = _reference_security_series(con, CAL)

    cols = _parquet_prices().to_pydict()
    idx = cols["ticker"].index("AAA")
    cols["closeadj"][idx] = cols["closeadj"][idx] + 1e-9  # one perturbed bar
    perturbed = ASM.security_series(_roundtrip(pa.table(cols)), CAL)

    assert _canon(perturbed["AAA"].stock_ret) != _canon(reference["AAA"].stock_ret)


# --- the closed table-to-domain mapping --------------------------------------------------------
def test_the_fixture_keeps_the_three_close_series_distinct():
    """A fixture where closeadj == close cannot detect a substitution between them."""
    cols = _parquet_prices().to_pydict()
    assert cols["close"] != cols["closeadj"]
    assert cols["closeunadj"] != cols["closeadj"]
    assert cols["close"] != cols["closeunadj"]


def test_every_consumed_column_has_exactly_one_registered_purpose():
    purposes = [v for (t, _c), v in ASM.COLUMN_PURPOSE.items() if t == "prices"]
    consumed = [p for p in purposes if p != "UNCONSUMED"]
    assert len(consumed) == len(set(consumed)), "a purpose is registered twice"
    assert ("prices", "closeadj") in ASM.COLUMN_PURPOSE
    assert ASM.COLUMN_PURPOSE[("prices", "closeadj")] == "total-return signal series"
    assert ASM.COLUMN_PURPOSE[("prices", "closeunadj")] == "raw close for ADV"


def test_an_unregistered_column_is_refused():
    with pytest.raises(ASM.AssemblyRefused, match="no registered purpose"):
        ASM.verify_column_purposes("prices", (*_parquet_prices().column_names, "sentiment_score"))


def test_a_missing_registered_column_is_refused():
    with pytest.raises(ASM.AssemblyRefused, match="registered columns absent"):
        ASM.verify_column_purposes("prices", ("ticker", "date", "closeadj"))


def test_an_unknown_table_consumes_nothing():
    with pytest.raises(ASM.AssemblyRefused, match="no registered column purposes"):
        ASM.verify_column_purposes("sentiment", ("ticker",))


# --- fail-closed behaviour ---------------------------------------------------------------------
def test_duplicate_price_rows_are_refused_not_last_wins():
    cols = _parquet_prices().to_pydict()
    for key in cols:
        cols[key].append(cols[key][0])  # exact duplicate (ticker, date)
    with pytest.raises(ASM.AssemblyRefused, match="duplicate price row"):
        ASM.security_series(_roundtrip(pa.table(cols)), CAL)


def test_calendar_is_registered_not_derived_and_identity_is_checked():
    cal = ASM.registered_calendar(SESSIONS, expected_identity=CAL.identity)
    assert cal.sessions == CAL.sessions
    with pytest.raises(ASM.AssemblyRefused, match="calendar identity"):
        ASM.registered_calendar(SESSIONS, expected_identity="0" * 64)
    with pytest.raises(ASM.AssemblyRefused, match="empty registered session list"):
        ASM.registered_calendar([])


def test_a_security_with_no_present_session_is_skipped_not_defaulted():
    cols = _parquet_prices().to_pydict()
    n = len(SESSIONS)
    for key, value in (
        ("ticker", "DDD"),
        ("date", None),
        ("closeadj", None),
        ("closeunadj", None),
        ("volume", None),
        ("open", None),
        ("high", None),
        ("low", None),
        ("close", None),
    ):
        for i in range(n):
            cols[key].append(SESSIONS[i] if key == "date" else value)
    produced = ASM.security_series(_roundtrip(pa.table(cols)), CAL)
    assert "DDD" not in produced


def test_missing_spy_in_the_window_is_refused():
    cols = _parquet_etfs().to_pydict()
    keep = [i for i, t in enumerate(cols["ticker"]) if t != "SPY"]
    trimmed = {k: [v[i] for i in keep] for k, v in cols.items()}
    with pytest.raises(ASM.AssemblyRefused, match="no SPY observation"):
        ASM.factor_returns(_roundtrip(pa.table(trimmed)), CAL, ETF_BY_SECTOR, "SPY")


def test_identity_registry_refuses_a_missing_required_slot():
    with pytest.raises(ASM.AssemblyRefused, match="required input identities absent"):
        ASM.identity_registry(CAL, {"spy_total_return_series": "id"})
