"""BREADTH-CN-001 Track A1: resumable Baostock pull for the SH/SZ breadth panel.

Pulls, one stock at a time, the RAW (unadjusted) daily close, tradestatus and isST plus the adjustment
factor events, and stores the vendor strings exactly as received in a new DuckDB file.  Nothing else is read
or written: the security master is opened read-only, and no existing store is touched.

Design points the pilot gates rely on
  * one DuckDB transaction per stock (bars + factors + log row): a hard kill leaves either the whole stock or
    nothing, so a restart can neither duplicate nor skip rows;
  * resume = skip stocks whose pull_log status is 'ok'; failed stocks are retried;
  * every stock logs n_bars, n_factors and a SHA-256 of its canonical rows; every batch of `--batch` stocks
    logs a SHA-256 over its stocks' hashes, written when the batch is complete;
  * throughput (calls/s, stocks/s, rows/s) is written to <store>.summary.json.

Usage
  python pull_baostock.py pull  --master-store <duckdb> --store <new.duckdb> --start 2024-01-02 --end 2024-12-31
  python pull_baostock.py gates --master-store <duckdb> --store <new.duckdb> --calendar-csv <csv> \\
         --start 2024-01-02 --end 2024-12-31 --out <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

A_SHARE_CODE = re.compile(r"^(600|601|603|605|688|000|001|002|003|300|301)\d{3}$")
BAR_FIELDS = "date,code,close,tradestatus,isST"
SEP = "\x1f"


class FetchError(RuntimeError):
    pass


# ---------------------------------------------------------------- fetchers
class BaostockFetcher:
    """Real vendor access.  Sleeps `throttle` seconds after every call; retries with re-login."""

    def __init__(self, throttle: float = 0.05, retries: int = 4):
        import baostock as bs

        self.bs, self.throttle, self.retries = bs, throttle, retries
        self.calls = 0
        self._login()

    def _login(self) -> None:
        lg = self.bs.login()
        if lg.error_code != "0":
            raise FetchError(f"login failed: {lg.error_code} {lg.error_msg}")

    def _collect(self, rs, what: str) -> list[list[str]]:
        if rs.error_code != "0":
            raise FetchError(f"{what}: {rs.error_code} {rs.error_msg}")
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        return rows

    def _call(self, fn, what: str) -> list[list[str]]:
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                rows = self._collect(fn(), what)
                self.calls += 1
                time.sleep(self.throttle)
                return rows
            except Exception as exc:  # network and vendor errors alike: back off, log in again
                last = exc
                time.sleep(min(30.0, 2.0 * 2**attempt))
                try:
                    self.bs.logout()
                    self._login()
                except Exception as exc2:
                    last = exc2
        raise FetchError(f"{what} failed after {self.retries} attempts: {last}")

    def bars(self, code: str, start: str, end: str) -> list[list[str]]:
        return self._call(
            lambda: self.bs.query_history_k_data_plus(
                code, BAR_FIELDS, start_date=start, end_date=end, frequency="d", adjustflag="3"
            ),
            f"bars {code}",
        )

    def factors(self, code: str, start: str, end: str) -> list[list[str]]:
        """Event rows as [dividOperateDate, foreAdjustFactor, backAdjustFactor, adjustFactor] (code dropped)."""
        rows = self._call(
            lambda: self.bs.query_adjust_factor(code, start_date=start, end_date=end),
            f"factors {code}",
        )
        return [r[1:] if len(r) == 5 else r for r in rows]

    def close(self) -> None:
        self.bs.logout()


class FakeFetcher:
    """Deterministic offline stand-in for tests: one bar per weekday, one factor event, optional delay."""

    def __init__(self, delay: float = 0.0):
        self.delay, self.calls = delay, 0

    def bars(self, code: str, start: str, end: str) -> list[list[str]]:
        time.sleep(self.delay)
        self.calls += 1
        seed = int(hashlib.sha256(code.encode()).hexdigest()[:6], 16)
        days = pd.bdate_range(start, end)
        return [
            [d.strftime("%Y-%m-%d"), code, f"{10 + ((seed + i) % 97) / 10:.2f}", "1", "0"]
            for i, d in enumerate(days)
        ]

    def factors(self, code: str, start: str, end: str) -> list[list[str]]:
        time.sleep(self.delay)
        self.calls += 1
        return [["2000-01-03", "1.000000", "1.000000", "1.000000"]]

    def close(self) -> None:
        pass


# ---------------------------------------------------------------- universe
def board_of(code6: str) -> str:
    if code6.startswith("688"):
        return "STAR"
    if code6.startswith(("300", "301")):
        return "CHINEXT"
    if code6.startswith("60"):
        return "SH_MAIN"
    return "SZ_MAIN"


def load_universe(master_store: str | None, universe_csv: str | None) -> pd.DataFrame:
    """SH/SZ A-shares incl. delisted.  Columns: symbol (SHSE.600000), bs_code (sh.600000), code6, name,
    list_date, delist_date (blank = still listed), board.  B-shares, indices and funds fall out of the code filter."""
    if universe_csv:
        u = pd.read_csv(universe_csv, dtype=str)
    else:
        con = duckdb.connect(master_store, read_only=True)
        u = con.execute(
            "select symbol, sec_name as name, listed_date as list_date, delisted_date as delist_date, exchange "
            "from ashare_symbol_master where exchange in ('SHSE','SZSE')"
        ).df()
        con.close()
    u["code6"] = u["symbol"].str.extract(r"(\d{6})")[0]
    u = u[u["code6"].str.match(A_SHARE_CODE)].copy()
    u["bs_code"] = (
        u["symbol"].str.split(".").str[0].map({"SHSE": "sh", "SZSE": "sz"}) + "." + u["code6"]
    )
    u["list_date"] = pd.to_datetime(u["list_date"], errors="coerce")
    d = pd.to_datetime(u["delist_date"], errors="coerce")
    u["delist_date"] = d.where(
        d.dt.year < 2037, pd.NaT
    )  # 2038-01-01 is the 'still listed' sentinel
    u["board"] = u["code6"].map(board_of)
    return u.sort_values("symbol").reset_index(drop=True)


def write_master_csv(u: pd.DataFrame, path: Path) -> None:
    m = u[["symbol", "list_date", "delist_date", "board"]].rename(columns={"symbol": "code"})
    m.to_csv(path, index=False, date_format="%Y-%m-%d")


# ---------------------------------------------------------------- store
SCHEMA = """
create table if not exists bars (date varchar, code varchar, close varchar, tradestatus varchar, isst varchar);
create table if not exists factors (code varchar, dividoperatedate varchar, foreadjustfactor varchar,
                                    backadjustfactor varchar, adjustfactor varchar);
create table if not exists pull_log (symbol varchar primary key, status varchar, n_bars bigint, n_factors bigint,
                                     sha256 varchar, batch_id integer, attempts integer, finished varchar, error varchar);
create table if not exists batch_log (batch_id integer primary key, n_symbols integer, n_bars bigint,
                                      sha256 varchar, finished varchar);
"""


def canonical_sha(bars: list[list[str]], factors: list[list[str]]) -> str:
    b = sorted(SEP.join(r) for r in bars)
    f = sorted(SEP.join(r) for r in factors)
    return hashlib.sha256("\n".join(["BARS", *b, "FACTORS", *f]).encode()).hexdigest()


def batch_sha(hashes: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(hashes)).encode()).hexdigest()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def pull(args: argparse.Namespace) -> dict:
    u = load_universe(args.master_store, args.universe_csv)
    if args.limit:
        u = u.head(args.limit)
    store = Path(args.store)
    store.parent.mkdir(parents=True, exist_ok=True)
    progress = store.with_suffix(".progress.jsonl")
    con = duckdb.connect(str(store))
    for stmt in filter(None, (s.strip() for s in SCHEMA.split(";"))):
        con.execute(stmt)
    done = {r[0] for r in con.execute("select symbol from pull_log where status='ok'").fetchall()}
    fetcher = (
        FakeFetcher(args.fake_delay) if args.fetcher == "fake" else BaostockFetcher(args.throttle)
    )

    def note(**kw) -> None:
        with progress.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": _now(), **kw}, ensure_ascii=False) + "\n")

    note(
        event="run_start",
        universe=len(u),
        already_ok=len(done & set(u["symbol"])),
        start=args.start,
        end=args.end,
    )
    t0, calls0, n_new, rows_new = time.time(), getattr(fetcher, "calls", 0), 0, 0
    bs_ = args.batch
    for i, r in u.iterrows():
        sym, batch = r["symbol"], int(i) // bs_
        if sym in done:
            continue
        prev = con.execute(
            "select coalesce(max(attempts),0) from pull_log where symbol=?", [sym]
        ).fetchone()[0]
        try:
            bars = fetcher.bars(r["bs_code"], args.start, args.end)
            facs = fetcher.factors(r["bs_code"], "1990-01-01", args.end)
            note(event="fetched", symbol=sym, n_bars=len(bars), n_factors=len(facs))
        except Exception as exc:
            con.execute(
                "insert or replace into pull_log values (?,?,?,?,?,?,?,?,?)",
                [sym, "error", 0, 0, "", batch, prev + 1, _now(), str(exc)[:300]],
            )
            note(event="error", symbol=sym, error=str(exc)[:200])
            continue
        sha = canonical_sha(bars, facs)
        con.execute("begin")
        try:
            con.execute("delete from bars where code=?", [r["bs_code"]])
            con.execute("delete from factors where code=?", [r["bs_code"]])
            if bars:
                con.executemany("insert into bars values (?,?,?,?,?)", bars)
            if facs:
                con.executemany(
                    "insert into factors values (?,?,?,?,?)", [[r["bs_code"], *f] for f in facs]
                )
            con.execute(
                "insert or replace into pull_log values (?,?,?,?,?,?,?,?,?)",
                [sym, "ok", len(bars), len(facs), sha, batch, prev + 1, _now(), ""],
            )
            con.execute("commit")
        except Exception:
            con.execute("rollback")
            raise
        n_new, rows_new = n_new + 1, rows_new + len(bars)
        note(event="committed", symbol=sym, batch=batch)
        # batch hash once every stock of the batch is ok
        members = u.iloc[batch * bs_ : (batch + 1) * bs_]["symbol"].tolist()
        q = ",".join("?" * len(members))
        ok = con.execute(
            f"select sha256, n_bars from pull_log where status='ok' and symbol in ({q})", members
        ).fetchall()
        if len(ok) == len(members):
            con.execute(
                "insert or replace into batch_log values (?,?,?,?,?)",
                [batch, len(members), sum(x[1] for x in ok), batch_sha([x[0] for x in ok]), _now()],
            )
            note(event="batch_done", batch=batch, symbols=len(members))
    wall = max(time.time() - t0, 1e-9)
    calls = getattr(fetcher, "calls", 0) - calls0
    n_ok = con.execute("select count(*) from pull_log where status='ok'").fetchone()[0]
    n_err = con.execute("select count(*) from pull_log where status='error'").fetchone()[0]
    summary = {
        "universe": len(u),
        "ok_total": n_ok,
        "error_total": n_err,
        "pulled_this_run": n_new,
        "skipped_as_already_ok": len(done & set(u["symbol"])),
        "rows_this_run": rows_new,
        "wall_seconds": round(wall, 1),
        "calls": calls,
        "calls_per_second": round(calls / wall, 2),
        "stocks_per_second": round(n_new / wall, 3),
        "rows_per_second": round(rows_new / wall, 1),
        "start": args.start,
        "end": args.end,
        "finished": _now(),
    }
    store.with_suffix(".summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    note(event="run_end", **summary)
    fetcher.close()
    con.close()
    return summary


# ---------------------------------------------------------------- verification and gates
def verify_store(store: str) -> dict:
    """Duplicate rows, log completeness and hash recomputation.  Pure read."""
    con = duckdb.connect(store, read_only=True)
    dups = con.execute(
        "select count(*) from (select date, code from bars group by 1,2 having count(*)>1)"
    ).fetchone()[0]
    log = con.execute(
        "select symbol, status, n_bars, n_factors, sha256, batch_id from pull_log"
    ).df()
    bad_hash, bad_count = [], []
    bars = con.execute("select date, code, close, tradestatus, isst from bars").df()
    facs = con.execute(
        "select code, dividoperatedate, foreadjustfactor, backadjustfactor, adjustfactor from factors"
    ).df()
    bg = {c: g.astype(str).values.tolist() for c, g in bars.groupby("code")}
    fg = {c: g.drop(columns="code").astype(str).values.tolist() for c, g in facs.groupby("code")}
    for r in log[log["status"] == "ok"].itertuples(index=False):
        code = ("sh." if r.symbol.startswith("SHSE") else "sz.") + r.symbol.split(".")[1]
        b, f = bg.get(code, []), fg.get(code, [])
        if len(b) != r.n_bars or len(f) != r.n_factors:
            bad_count.append(r.symbol)
        if canonical_sha(b, f) != r.sha256:
            bad_hash.append(r.symbol)
    bl = con.execute("select batch_id, n_symbols, sha256 from batch_log").df()
    ok_by_batch = log[log["status"] == "ok"].groupby("batch_id")
    batch_issues = []
    for b in bl.itertuples(index=False):
        g = ok_by_batch.get_group(b.batch_id) if b.batch_id in ok_by_batch.groups else None
        if g is None or len(g) != b.n_symbols or batch_sha(g["sha256"].tolist()) != b.sha256:
            batch_issues.append(int(b.batch_id))
    con.close()
    return {
        "duplicate_date_code_rows": int(dups),
        "symbols_logged_ok": int((log["status"] == "ok").sum()),
        "symbols_logged_error": int((log["status"] == "error").sum()),
        "symbol_hash_mismatch": bad_hash,
        "symbol_count_mismatch": bad_count,
        "batches_logged": int(len(bl)),
        "batch_hash_mismatch": batch_issues,
    }


def gates(args: argparse.Namespace) -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import build_indicator as bi

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    u = load_universe(args.master_store, args.universe_csv)
    if args.limit:
        u = u.head(args.limit)
    write_master_csv(u, out / "master_universe.csv")
    v = verify_store(args.store)
    con = duckdb.connect(args.store, read_only=True)
    panel = con.execute("select cast(date as date) as date, code from bars").df()
    con.close()
    cov = bi.coverage_by_date(
        panel, str(out / "master_universe.csv"), args.calendar_csv, out, args.start, args.end
    )
    expected, missing = int(cov["expected"].sum()), int(cov["missing"].sum())
    miss = pd.read_csv(out / "coverage_missing_symbols.csv", dtype={"key": str})
    unexp = pd.read_csv(out / "coverage_unexpected_symbols.csv", dtype={"key": str})
    share = 1 - missing / expected if expected else 0.0
    ok_symbols_complete = v["symbols_logged_ok"] == len(u) and v["symbols_logged_error"] == 0
    batches_expected = -(-len(u) // args.batch)
    res = {
        "gate1_no_duplicate_date_code": {
            "duplicates": v["duplicate_date_code_rows"],
            "pass": v["duplicate_date_code_rows"] == 0,
        },
        "gate2_expected_symbol_sessions_retrieved": {
            "expected": expected,
            "missing": missing,
            "retrieved_share": round(share, 6),
            "threshold": 0.995,
            "missing_by_kind": miss.groupby("kind").size().to_dict() if len(miss) else {},
            "unexpected_by_reason": unexp.groupby("reason").size().to_dict() if len(unexp) else {},
            "pass": bool(expected > 0 and share >= 0.995),
        },
        "gate4_log_and_hashes": {
            "symbols_in_universe": len(u),
            "symbols_logged_ok": v["symbols_logged_ok"],
            "symbols_logged_error": v["symbols_logged_error"],
            "batches_expected": batches_expected,
            "batches_logged": v["batches_logged"],
            "symbol_hash_mismatch": len(v["symbol_hash_mismatch"]),
            "symbol_count_mismatch": len(v["symbol_count_mismatch"]),
            "batch_hash_mismatch": len(v["batch_hash_mismatch"]),
            "pass": bool(
                ok_symbols_complete
                and v["batches_logged"] == batches_expected
                and not v["symbol_hash_mismatch"]
                and not v["symbol_count_mismatch"]
                and not v["batch_hash_mismatch"]
            ),
        },
    }
    t = Path(__file__).parent / "test_pull_resume.py"
    run = subprocess.run([sys.executable, str(t)], capture_output=True, text=True, check=False)
    res["gate3_kill_and_restart_resumes_cleanly"] = {
        "test": t.name,
        "returncode": run.returncode,
        "output_tail": run.stdout.strip().splitlines()[-3:],
        "pass": run.returncode == 0 and "ALL TESTS PASSED" in run.stdout,
    }
    res["all_pass"] = all(res[k]["pass"] for k in res if k.startswith("gate"))
    (out / "gates.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("pull", "gates"):
        p = sub.add_parser(name)
        p.add_argument("--master-store")
        p.add_argument(
            "--universe-csv",
            help="alternative to --master-store (symbol, name, list_date, delist_date)",
        )
        p.add_argument("--store", required=True)
        p.add_argument("--start", required=True)
        p.add_argument("--end", required=True)
        p.add_argument("--batch", type=int, default=100)
        p.add_argument("--limit", type=int, default=0, help="first N symbols only (tests / smoke)")
    sub.choices["pull"].add_argument("--throttle", type=float, default=0.05)
    sub.choices["pull"].add_argument("--fetcher", choices=["baostock", "fake"], default="baostock")
    sub.choices["pull"].add_argument("--fake-delay", type=float, default=0.0)
    sub.choices["gates"].add_argument("--calendar-csv", required=True)
    sub.choices["gates"].add_argument("--out", required=True)
    a = ap.parse_args()
    if not (a.master_store or a.universe_csv):
        ap.error("need --master-store or --universe-csv")
    print(json.dumps(pull(a) if a.cmd == "pull" else gates(a), indent=1, default=str))


if __name__ == "__main__":
    main()
