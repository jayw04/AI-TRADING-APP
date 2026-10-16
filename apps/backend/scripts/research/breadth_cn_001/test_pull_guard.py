"""A pull store is readable by breadth computation only after a passing, still-valid gate-5 acceptance.
Run: python3 test_pull_guard.py   (offline: fake fetcher)"""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import build_indicator as bi  # noqa: E402
import pull_baostock as P  # noqa: E402

START, END = "2024-01-02", "2024-02-29"


def make_store(tmp: Path, with_ohlc: bool, n: int = 12) -> Path:
    uni = tmp / "u.csv"
    rows = [{"symbol": f"{'SHSE' if i % 2 == 0 else 'SZSE'}.{'60' if i % 2 == 0 else '00'}{i:04d}", "name": "x", "list_date": "2015-01-05", "delist_date": "2038-01-01"} for i in range(n)]  # fmt: skip
    pd.DataFrame(rows).to_csv(uni, index=False)
    store = tmp / "s.duckdb"
    P.pull(argparse.Namespace(master_store=None, universe_csv=str(uni), store=str(store), start=START, end=END, batch=4, limit=0, throttle=0.0, fetcher="fake", fake_delay=0.0, with_ohlc=with_ohlc))  # fmt: skip
    return store


def load_args(store: Path) -> argparse.Namespace:
    return argparse.Namespace(
        duckdb=str(store), csv=None, sql="select cast(date as date) as date, code, close from bars"
    )


def refused(fn) -> bool:
    try:
        fn()
    except SystemExit as e:
        return "REFUSED" in str(e)
    return False


def test_unaccepted_store_is_refused_and_accepted_store_is_readable() -> None:
    with tempfile.TemporaryDirectory() as t:
        store = make_store(Path(t), with_ohlc=True)
        assert refused(lambda: bi.load(load_args(store))), (
            "an unpromoted pull store must be refused"
        )
        res = P.promote(argparse.Namespace(store=str(store)))
        assert res["accepted"], res
        df, _ = bi.load(load_args(store))
        assert len(df) > 0
        print("ok unpromoted store refused by build_indicator.load; after promote it loads")


def test_tampering_after_acceptance_is_refused() -> None:
    with tempfile.TemporaryDirectory() as t:
        store = make_store(Path(t), with_ohlc=True)
        assert P.promote(argparse.Namespace(store=str(store)))["accepted"]
        con = duckdb.connect(str(store))
        con.execute("update bars set close='9.99' where rowid = 3")
        con.close()
        assert refused(lambda: bi.load(load_args(store)))
        print("ok a single changed value invalidates the acceptance")


def test_store_without_ohlc_cannot_be_promoted() -> None:
    with tempfile.TemporaryDirectory() as t:
        store = make_store(Path(t), with_ohlc=False)
        res = P.promote(argparse.Namespace(store=str(store)))
        assert not res["accepted"] and any("OHLC not evaluable" in p for p in res["problems"]), res
        assert refused(lambda: bi.load(load_args(store)))
        # the pilot waiver exists only on `gates`; it cannot make a store readable
        args = argparse.Namespace(master_store=None, universe_csv=str(Path(t) / "u.csv"), store=str(store), start=START, end=END, batch=4, limit=0, calendar_csv=str(Path(t) / "c.csv"), out=str(Path(t) / "o"), explanations_csv=None, run_gate3=False, waive_gate5_ohlc=True)  # fmt: skip
        pd.DataFrame({"date": pd.bdate_range(START, END).strftime("%Y-%m-%d")}).to_csv(
            Path(t) / "c.csv", index=False
        )
        g = P.gates(args)["gate5_prices_and_ohlc"]
        assert g["pass"] and "PILOT ONLY" in g["waiver"], g
        assert refused(lambda: bi.load(load_args(store))), (
            "a waived pilot gate must not unlock the store"
        )
        print(
            "ok no OHLC => promote fails; the pilot waiver passes gate 5 on `gates` but never unlocks the store"
        )


def test_repair_then_promote_unlocks() -> None:
    with tempfile.TemporaryDirectory() as t:
        store = make_store(Path(t), with_ohlc=False)
        assert not P.promote(argparse.Namespace(store=str(store)))["accepted"]
        P.ohlc_supplement(
            argparse.Namespace(
                store=str(store), start=START, end=END, fetcher="fake", fake_delay=0.0, throttle=0.0
            )
        )
        assert P.promote(argparse.Namespace(store=str(store)))["accepted"]
        bi.load(load_args(store))
        print("ok after the OHLC supplement the store promotes and loads")


def test_non_pull_inputs_are_unaffected() -> None:
    with tempfile.TemporaryDirectory() as t:
        db = Path(t) / "other.duckdb"
        con = duckdb.connect(str(db))
        con.execute(
            "create table bars as select DATE '2024-01-02' as date, 'x' as code, 1.0 as close"
        )
        con.close()
        df, _ = bi.load(load_args(db))
        assert len(df) == 1
        shutil.copy(db, Path(t) / "copy.duckdb")
        print("ok a duckdb without pull_log is not a pull store and is not guarded")


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
    print("ALL TESTS PASSED")
