"""Tests for the amended pilot gates (amendment A, 2026-10-16).  Offline: fake fetcher, 300 fake stocks.
Run: python3 test_gates_amendment.py

Each defect is injected into an otherwise clean store and must be caught by exactly the intended gate, while the
original v1 checks keep their meaning."""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import pull_baostock as P  # noqa: E402

START, END = "2024-01-02", "2024-03-29"
N = 300


def make_universe(path: Path) -> list[str]:
    syms = []
    rows = []
    for i in range(N):
        ex, code = ("SHSE", f"60{i:04d}") if i % 2 == 0 else ("SZSE", f"00{i:04d}")
        syms.append(f"{ex}.{code}")
        rows.append(
            {
                "symbol": f"{ex}.{code}",
                "name": code,
                "list_date": "2015-01-05",
                "delist_date": "2038-01-01",
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)
    return syms


def clean_store(tmp: Path, with_ohlc: bool = True) -> tuple[Path, Path, Path]:
    uni, cal = tmp / "uni.csv", tmp / "cal.csv"
    make_universe(uni)
    pd.DataFrame({"date": pd.bdate_range(START, END).strftime("%Y-%m-%d")}).to_csv(cal, index=False)
    store = tmp / "s.duckdb"
    P.pull(argparse.Namespace(master_store=None, universe_csv=str(uni), store=str(store), start=START, end=END,
                              batch=100, limit=0, throttle=0.0, fetcher="fake", fake_delay=0.0, with_ohlc=with_ohlc))  # fmt: skip
    return store, uni, cal


def run_gates(store: Path, uni: Path, cal: Path, out: Path, expl: Path | None = None) -> dict:
    a = argparse.Namespace(master_store=None, universe_csv=str(uni), store=str(store), start=START, end=END, batch=100,
                           limit=0, calendar_csv=str(cal), out=str(out), explanations_csv=str(expl) if expl else None,
                           run_gate3=False)  # fmt: skip
    return P.gates(a)


def edited(src: Path, tmp: Path, name: str, sql: list[str]) -> Path:
    dst = tmp / name
    shutil.copy(src, dst)
    con = duckdb.connect(str(dst))
    for s in sql:
        con.execute(s)
    con.close()
    return dst


def test_clean_store_passes_everything_but_gate3_skipped() -> None:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        store, uni, cal = clean_store(tmp)
        r = run_gates(store, uni, cal, tmp / "o")
        for g in (
            "gate1_no_duplicate_date_code",
            "gate2_expected_symbol_sessions_retrieved",
            "gate4_log_and_hashes",
            "gate5_prices_and_ohlc",
        ):
            assert r[g]["pass"], (g, r[g])
        assert r["definition_version"].startswith("v1@36a07890")
        print("ok clean store: gates 1, 2, 4, 5 pass")


def test_gate1_covers_the_factors_table() -> None:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        store, uni, cal = clean_store(tmp)
        bad = edited(
            store,
            tmp,
            "f.duckdb",
            [
                "insert into factors select * from factors where code = (select min(code) from factors)"
            ],
        )
        r = run_gates(bad, uni, cal, tmp / "o")
        g = r["gate1_no_duplicate_date_code"]
        assert not g["pass"] and g["duplicates"] == 0 and g["duplicate_factor_rows"] == 1, g
        print("ok a duplicated factor event fails gate 1 (bars duplicates still 0)")


def test_gate2_per_session_floor() -> None:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        store, uni, cal = clean_store(tmp)
        day = "2024-02-14"
        bad = edited(
            store,
            tmp,
            "p.duckdb",
            [
                f"delete from bars where date='{day}' and code in (select distinct code from bars order by code limit 15)"
            ],
        )
        r = run_gates(bad, uni, cal, tmp / "o")["gate2_expected_symbol_sessions_retrieved"]
        assert r["retrieved_share"] >= P.OVERALL_MIN, r  # the v1 overall threshold alone would pass
        assert (
            r["sessions_below_threshold"] == 1 and day in r["worst_sessions"] and not r["pass"]
        ), r
        print(
            "ok one thin session (95% coverage) fails gate 2 although the overall share is still >= 0.995"
        )


def test_gate2_whole_symbol_needs_an_explanation() -> None:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        store, uni, cal = clean_store(tmp)
        bad = edited(
            store,
            tmp,
            "w.duckdb",
            ["delete from bars where code='sh.600010'", "delete from ohlc where code='sh.600010'"],
        )
        r = run_gates(bad, uni, cal, tmp / "o")["gate2_expected_symbol_sessions_retrieved"]
        assert (
            r["whole_symbol_misses"] == ["600010"]
            and r["whole_symbol_unexplained"] == ["600010"]
            and not r["pass"]
        ), r
        e = tmp / "e.csv"
        pd.DataFrame(
            {
                "key": ["600010"],
                "reason": ["suspended all of Q1 2024; vendor returns no rows (fixture)"],
                "source": ["test"],
            }
        ).to_csv(e, index=False)
        r2 = run_gates(bad, uni, cal, tmp / "o2", e)["gate2_expected_symbol_sessions_retrieved"]
        assert r2["whole_symbol_unexplained"] == [] and r2["retrieved_share"] >= P.OVERALL_MIN, r2
        pd.DataFrame({"key": ["600010"], "reason": [" "], "source": ["test"]}).to_csv(
            e, index=False
        )
        r3 = run_gates(bad, uni, cal, tmp / "o3", e)["gate2_expected_symbol_sessions_retrieved"]
        assert r3["whole_symbol_unexplained"] == ["600010"], (
            "a blank reason must not count as an explanation"
        )
        print("ok a whole-symbol miss fails gate 2 until it is listed with a non-empty reason")


def test_gate5_prices_and_ohlc() -> None:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        store, uni, cal = clean_store(tmp)
        cases = {
            "non-positive close": [
                "update bars set close='0.0000' where rowid = 5",
                "update ohlc set close='0.0000' where rowid = 5",
            ],
            "non-numeric close": ["update bars set close='' where rowid = 7"],
            "non-positive factor": ["update factors set adjustfactor='0' where rowid = 3"],
            "high below low": ["update ohlc set high='1.00' where rowid = 9"],
            "low above close": ["update ohlc set low='99.00' where rowid = 11"],
            "ohlc close differs from bars close": [
                "update ohlc set close='55.55' where rowid = 13"
            ],
        }
        for name, sql in cases.items():
            bad = edited(store, tmp, "g5.duckdb", sql)
            g = run_gates(bad, uni, cal, tmp / "o")["gate5_prices_and_ohlc"]
            assert not g["pass"], (name, g)
        nol = clean_store(tmp / "x", with_ohlc=False) if (tmp / "x").mkdir() is None else None
        g = run_gates(nol[0], nol[1], nol[2], tmp / "o5")["gate5_prices_and_ohlc"]
        assert not g["pass"] and not g["ohlc_evaluable"] and "not evaluable" in g["note"], g
        print(
            "ok gate 5 catches non-positive/non-numeric prices and factors, OHLC violations, a close mismatch; no OHLC => FAIL, not pass"
        )


def test_ohlc_supplement_makes_an_old_store_evaluable() -> None:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        (tmp / "y").mkdir()
        store, uni, cal = clean_store(tmp / "y", with_ohlc=False)
        before = run_gates(store, uni, cal, tmp / "o1")
        assert not before["gate5_prices_and_ohlc"]["pass"]
        res = P.ohlc_supplement(
            argparse.Namespace(
                store=str(store), start=START, end=END, fetcher="fake", fake_delay=0.0, throttle=0.0
            )
        )
        assert res["ohlc_pulled"] == N
        after = run_gates(store, uni, cal, tmp / "o2")
        assert after["gate5_prices_and_ohlc"]["pass"] and after["gate4_log_and_hashes"]["pass"], (
            after
        )
        again = P.ohlc_supplement(
            argparse.Namespace(
                store=str(store), start=START, end=END, fetcher="fake", fake_delay=0.0, throttle=0.0
            )
        )
        assert again["ohlc_pulled"] == 0  # resumable: nothing left to do
        print(
            "ok the supplement fills a v1 store (300 stocks), gate 5 then passes, the v1 hashes still verify, a rerun does nothing"
        )


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
    print("ALL TESTS PASSED")
