"""Kill-and-restart test for pull_baostock.py (offline: uses the deterministic fake fetcher).
Run: python3 test_pull_resume.py

A pull is killed partway (hard kill, no cleanup), restarted, and compared with an uninterrupted pull of the same
universe: no duplicate rows, no gaps (every stock ok), identical per-stock hashes, identical batch hashes, and no
stock committed before the kill was fetched again."""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import pull_baostock as P  # noqa: E402

CODES = [
    ("SHSE", "600000"),
    ("SHSE", "600519"),
    ("SHSE", "688001"),
    ("SZSE", "000001"),
    ("SZSE", "000004"),
    ("SZSE", "300001"),
    ("SHSE", "601166"),
    ("SZSE", "002001"),
    ("SHSE", "603000"),
    ("SZSE", "300750"),
    ("SHSE", "600001"),
    ("SZSE", "000002"),
]


def universe_csv(path: Path) -> None:
    rows = [
        {"symbol": f"{ex}.{c}", "name": c, "list_date": "2010-01-04", "delist_date": "2038-01-01"}
        for ex, c in CODES
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def cmd(uni: Path, store: Path, delay: float) -> list[str]:
    return [
        sys.executable,
        str(HERE / "pull_baostock.py"),
        "pull",
        "--universe-csv",
        str(uni),
        "--store",
        str(store),
        "--start",
        "2024-01-02",
        "--end",
        "2024-03-29",
        "--batch",
        "4",
        "--fetcher",
        "fake",
        "--fake-delay",
        str(delay),
    ]


def events(store: Path) -> list[dict]:
    p = store.with_suffix(".progress.jsonl")
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def per_stock(store: Path) -> pd.DataFrame:
    import duckdb

    con = duckdb.connect(str(store), read_only=True)
    out = con.execute(
        "select symbol, status, n_bars, n_factors, sha256, batch_id from pull_log order by symbol"
    ).df()
    con.close()
    return out


def test_kill_and_resume() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        uni = t / "uni.csv"
        universe_csv(uni)
        ref, killed = t / "ref.duckdb", t / "killed.duckdb"
        r = subprocess.run(cmd(uni, ref, 0.0), capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stderr[-500:]

        proc = subprocess.Popen(
            cmd(uni, killed, 0.25), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        deadline = time.time() + 60
        while (
            time.time() < deadline
            and sum(e.get("event") == "committed" for e in events(killed)) < 4
        ):
            time.sleep(0.05)
        proc.kill()
        proc.wait()
        committed_before = [e["symbol"] for e in events(killed) if e.get("event") == "committed"]
        assert 4 <= len(committed_before) < len(CODES), "kill did not land partway"

        r2 = subprocess.run(cmd(uni, killed, 0.0), capture_output=True, text=True, check=False)
        assert r2.returncode == 0, r2.stderr[-500:]

        v = P.verify_store(str(killed))
        assert v["duplicate_date_code_rows"] == 0, v
        assert v["symbols_logged_ok"] == len(CODES) and v["symbols_logged_error"] == 0, v
        assert (
            not v["symbol_hash_mismatch"]
            and not v["symbol_count_mismatch"]
            and not v["batch_hash_mismatch"]
        ), v
        assert v["batches_logged"] == -(-len(CODES) // 4), v

        a, b = per_stock(ref), per_stock(killed)
        assert a.drop(columns="status").equals(b.drop(columns="status")), (
            "resumed pull differs from uninterrupted pull"
        )
        fetched = [e["symbol"] for e in events(killed) if e.get("event") == "fetched"]
        for s in committed_before:
            assert fetched.count(s) == 1, f"{s} was fetched again after it had been committed"
        starts = [e for e in events(killed) if e.get("event") == "run_start"]
        assert starts[1]["already_ok"] >= 4, starts
        print(
            f"ok kill/resume: killed after {len(committed_before)} of {len(CODES)} stocks; resume skipped them;"
            f" 0 duplicates, 0 gaps, hashes identical to an uninterrupted pull"
        )


if __name__ == "__main__":
    test_kill_and_resume()
    print("ALL TESTS PASSED")
