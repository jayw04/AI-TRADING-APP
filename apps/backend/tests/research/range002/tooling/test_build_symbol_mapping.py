"""build_symbol_mapping.py: the symbol each vendor ticker traded as, from the vendor's own ACTIONS."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import build_symbol_mapping as bsm  # noqa: E402

FROM, TO = "2016-01-01", "2016-03-31"
EVENTS = {
    "META": [("2022-06-09", "FB")],
    "BKNG": [("2000-05-10", "BKNG1"), ("2018-02-28", "PCLN")],
    "CB": [("2016-01-15", "ACE")],  # renamed INSIDE the window
    "DD": [("2019-04-02", "DOW")],  # Sharadar DD is the Dow Chemical lineage in 2016
    "DD1": [("2017-09-01", "DD")],  # the 2016 holder of the symbol DD (E. I. du Pont)
    "APC1": [("2019-08-08", "APC")],
    "C2": [("2018-01-01", "C1"), ("2017-01-01", "C0")],  # only changes AFTER the window count
}


def _probe(*recs: tuple[str, str, str, int, int]) -> dict[str, Any]:
    return {
        "records": [
            {
                "vendor_ticker": v,
                "request_symbol": r,
                "day": day,
                "asof": "-",
                "http_status": st,
                "bars": n,
                "first_bar_utc": None,
                "last_bar_utc": None,
                "symbol_echo": r if st == 200 else None,
                "error_kind": None,
            }  # fmt: skip
            for v, r, day, st, n in recs
        ]
    }


ROWS: dict[str, dict[str, Any]] = {
    s: {"relatedtickers": "", "firstpricedate": "1997-12-31", "lastpricedate": "2026-10-12"}
    for s in ("META", "BKNG", "CB", "DD", "DD1", "APC1", "AAPL", "BRK.B", "ZZZ9")
}


def _entries(symbols: list[str], probe: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        e["vendor_ticker"]: e for e in bsm.build_entries(symbols, ROWS, probe, EVENTS, FROM, TO)
    }


def test_symbol_as_of_the_window_comes_from_the_vendors_ticker_changes() -> None:
    assert bsm.symbol_schedule("META", FROM, TO, EVENTS) == [(FROM, "FB")]
    assert bsm.symbol_schedule("BKNG", FROM, TO, EVENTS) == [(FROM, "PCLN")]  # 2000 change ignored
    assert bsm.symbol_schedule("AAPL", FROM, TO, EVENTS) == [(FROM, "AAPL")]
    assert bsm.symbol_schedule("DD", FROM, TO, EVENTS) == [(FROM, "DOW")]
    assert bsm.symbol_schedule("DD1", FROM, TO, EVENTS) == [(FROM, "DD")]


def test_a_rename_inside_the_window_splits_the_schedule() -> None:
    assert bsm.symbol_schedule("CB", FROM, TO, EVENTS) == [(FROM, "ACE"), ("2016-01-15", "CB")]


def test_chain_symbols_need_a_successful_probe_each_else_unverified() -> None:
    ok = _probe(("META", "FB", "2016-01-04", 200, 60), ("CB", "ACE", "2016-01-04", 200, 60),
                ("CB", "CB", "2016-03-31", 200, 60))  # fmt: skip
    got = _entries(["META", "CB", "BKNG"], ok)
    assert got["META"]["provenance"] == bsm.PROV_CHAIN and got["META"]["request_symbol"] == "FB"
    assert got["CB"]["provenance"] == bsm.PROV_CHAIN and len(got["CB"]["schedule"]) == 2
    assert (
        got["BKNG"]["provenance"] == bsm.PROV_UNVERIFIED
    )  # PCLN never probed: refused, not guessed
    bad = _probe(("META", "FB", "2016-01-04", 200, 0))
    assert _entries(["META"], bad)["META"]["provenance"] == bsm.PROV_UNVERIFIED


def test_reused_symbol_cannot_collide_dd_and_dd1_get_distinct_companies() -> None:
    probe = _probe(("DD", "DOW", "2016-01-04", 200, 60), ("DD1", "DD", "2016-01-04", 200, 60))
    got = _entries(["DD", "DD1"], probe)
    assert got["DD"]["request_symbol"] == "DOW" and got["DD1"]["request_symbol"] == "DD"
    assert got["DD"]["provenance"] == got["DD1"]["provenance"] == bsm.PROV_CHAIN


def test_plain_and_class_share_symbols_are_preserved_and_digit_suffix_never_stripped() -> None:
    got = _entries(["AAPL", "BRK.B", "ZZZ9"], _probe())
    assert got["AAPL"]["provenance"] == bsm.PROV_ALPHA and got["AAPL"]["request_symbol"] == "AAPL"
    assert (
        got["BRK.B"]["provenance"] == bsm.PROV_CLASS and got["BRK.B"]["request_symbol"] == "BRK.B"
    )
    assert (
        got["ZZZ9"]["provenance"] == bsm.PROV_UNVERIFIED and got["ZZZ9"]["request_symbol"] == "ZZZ9"
    )


def test_cli_end_to_end_refuses_overwrite_and_reports_unverified(tmp_path: Path) -> None:
    d = tmp_path / "export"
    d.mkdir()
    con = duckdb.connect(":memory:")
    con.execute(
        'CREATE TABLE tickers("table" VARCHAR, ticker VARCHAR, relatedtickers VARCHAR,'
        " firstpricedate DATE, lastpricedate DATE)"
    )
    con.execute("INSERT INTO tickers VALUES ('SEP','AAL',NULL,'1997-12-31','2026-10-12'),"
                " ('SEP','META','FB','2012-05-18','2026-10-12')")  # fmt: skip
    con.execute(f"COPY tickers TO '{(d / 'tickers.parquet').as_posix()}' (FORMAT PARQUET)")
    con.execute(
        "CREATE TABLE actions(date DATE, action VARCHAR, ticker VARCHAR, contraticker VARCHAR)"
    )
    con.execute("INSERT INTO actions VALUES ('2022-06-09','tickerchangefrom','META','FB')")
    con.execute(f"COPY actions TO '{(d / 'actions.parquet').as_posix()}' (FORMAT PARQUET)")
    con.close()
    uni = tmp_path / "u.txt"
    uni.write_text("AAL\nMETA\n", encoding="utf-8")
    probe = tmp_path / "p.json"
    probe.write_text(json.dumps(_probe()), encoding="utf-8")  # no probe for FB yet
    out = tmp_path / "m.json"
    argv = ["--universe-file", str(uni), "--daily-dir", str(d), "--table-filter", "SEP",
            "--probe-json", str(probe), "--out", str(out), "--date-from", FROM, "--date-to", TO]  # fmt: skip
    assert bsm.main(argv) == bsm.EXIT_UNVERIFIED
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["unverified"] == ["META"]
    assert bsm.main(argv) == bsm.EXIT_REFUSED
