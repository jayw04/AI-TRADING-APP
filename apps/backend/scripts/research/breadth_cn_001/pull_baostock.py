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

# prefix FAMILIES, not an enumeration: 60x SH main, 68x STAR (incl. 689 CDR), 00x SZ main, 30x ChiNext (incl. 302, e.g. 302132).
# B-shares (900/200), indices and funds do not match.
A_SHARE_CODE = re.compile(r"^(60|68|00|30)\d{4}$")
BAR_FIELDS = "date,code,close,tradestatus,isST"
SEP = "\x1f"


class FetchError(RuntimeError):
    pass


# ---------------------------------------------------------------- fetchers
class BaostockFetcher:
    """Real vendor access.  Sleeps `throttle` seconds after every call; retries with re-login."""

    def __init__(
        self,
        throttle: float = 0.05,
        retries: int = 4,
        timeout: float = 120.0,
        backoff: float = 2.0,
        bs_module=None,
    ):
        import socket

        if bs_module is None:
            import baostock as bs_module

        # a stalled connection must raise (and be retried after a fresh login), not hang for the rest of the pull
        socket.setdefaulttimeout(timeout)
        self.bs, self.throttle, self.retries, self.backoff = bs_module, throttle, retries, backoff
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
                time.sleep(min(30.0, self.backoff * 2**attempt))
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

    def bars_v2(self, code: str, start: str, end: str) -> list[list[str]]:
        """Bars with OHLC in ONE call: [date, code, open, high, low, close, tradestatus, isST]."""
        return self._call(
            lambda: self.bs.query_history_k_data_plus(
                code,
                "date,code,open,high,low,close,tradestatus,isST",
                start_date=start,
                end_date=end,
                frequency="d",
                adjustflag="3",
            ),
            f"bars_v2 {code}",
        )

    def bars_ohlc(self, code: str, start: str, end: str) -> list[list[str]]:
        """[date, code, open, high, low, close] (supplement for stores pulled without OHLC)."""
        return self._call(
            lambda: self.bs.query_history_k_data_plus(
                code,
                "date,code,open,high,low,close",
                start_date=start,
                end_date=end,
                frequency="d",
                adjustflag="3",
            ),
            f"ohlc {code}",
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

    def bars_ohlc(self, code: str, start: str, end: str) -> list[list[str]]:
        out = []
        for d, c, close, _ts, _st in self.bars(code, start, end):
            x = float(close)
            out.append([d, c, f"{x:.2f}", f"{x + 0.05:.2f}", f"{x - 0.05:.2f}", close])
        return out

    def bars_v2(self, code: str, start: str, end: str) -> list[list[str]]:
        base, ohlc = self.bars(code, start, end), self.bars_ohlc(code, start, end)
        return [
            [o[0], o[1], o[2], o[3], o[4], o[5], b[3], b[4]]
            for b, o in zip(base, ohlc, strict=True)
        ]

    def factors(self, code: str, start: str, end: str) -> list[list[str]]:
        time.sleep(self.delay)
        self.calls += 1
        return [["2000-01-03", "1.000000", "1.000000", "1.000000"]]

    def close(self) -> None:
        pass


# ---------------------------------------------------------------- universe
def board_of(code6: str) -> str:
    if code6.startswith("68"):
        return "STAR"
    if code6.startswith("30"):
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
create table if not exists ohlc (date varchar, code varchar, open varchar, high varchar, low varchar, close varchar);
create table if not exists batch_log (batch_id integer primary key, n_symbols integer, n_bars bigint,
                                      sha256 varchar, finished varchar);
"""


def open_store(path: str):
    """Open (creating if needed) a pull store; brings an older store up to the current schema (ohlc table,
    pull_log.ohlc_sha256).  The original columns and rows are untouched."""
    con = duckdb.connect(path)
    for stmt in filter(None, (s.strip() for s in SCHEMA.split(";"))):
        con.execute(stmt)
    con.execute("alter table pull_log add column if not exists ohlc_sha256 varchar")
    return con


def ohlc_sha(rows: list[list[str]]) -> str:
    return hashlib.sha256(
        "\n".join(["OHLC", *sorted(SEP.join(r) for r in rows)]).encode()
    ).hexdigest()


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
    con = open_store(str(store))
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
        ohlc: list[list[str]] = []
        try:
            if getattr(args, "with_ohlc", False):  # one call carries the OHLC fields too
                v2 = fetcher.bars_v2(r["bs_code"], args.start, args.end)
                bars = [
                    [x[0], x[1], x[5], x[6], x[7]] for x in v2
                ]  # identical strings to the v1 call
                ohlc = [x[:6] for x in v2]
            else:
                bars = fetcher.bars(r["bs_code"], args.start, args.end)
            facs = fetcher.factors(r["bs_code"], "1990-01-01", args.end)
            note(event="fetched", symbol=sym, n_bars=len(bars), n_factors=len(facs))
        except Exception as exc:
            con.execute(
                "insert or replace into pull_log (symbol, status, n_bars, n_factors, sha256, batch_id, attempts, finished, error, ohlc_sha256) values (?,?,?,?,?,?,?,?,?,?)",
                [sym, "error", 0, 0, "", batch, prev + 1, _now(), str(exc)[:300], None],
            )
            note(event="error", symbol=sym, error=str(exc)[:200])
            continue
        sha = canonical_sha(bars, facs)
        con.execute("begin")
        try:
            con.execute("delete from bars where code=?", [r["bs_code"]])
            con.execute("delete from factors where code=?", [r["bs_code"]])
            con.execute("delete from ohlc where code=?", [r["bs_code"]])
            if ohlc:
                con.executemany("insert into ohlc values (?,?,?,?,?,?)", ohlc)
            if bars:
                con.executemany("insert into bars values (?,?,?,?,?)", bars)
            if facs:
                con.executemany(
                    "insert into factors values (?,?,?,?,?)", [[r["bs_code"], *f] for f in facs]
                )
            con.execute(
                "insert or replace into pull_log (symbol, status, n_bars, n_factors, sha256, batch_id, attempts, finished, error, ohlc_sha256) values (?,?,?,?,?,?,?,?,?,?)",
                [
                    sym,
                    "ok",
                    len(bars),
                    len(facs),
                    sha,
                    batch,
                    prev + 1,
                    _now(),
                    "",
                    ohlc_sha(ohlc) if ohlc else None,
                ],
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


def ohlc_supplement(args: argparse.Namespace) -> dict:
    """Add open/high/low/close to a store that was pulled without them: one call per stock already logged ok.
    One transaction per stock; resumable (stocks with an ohlc_sha256 are skipped); bars/factors/hashes untouched."""
    store = Path(args.store)
    progress = store.with_suffix(".ohlc_progress.jsonl")
    con = open_store(str(store))
    todo = con.execute(
        "select symbol from pull_log where status='ok' and ohlc_sha256 is null order by symbol"
    ).fetchall()
    fetcher = (
        FakeFetcher(args.fake_delay) if args.fetcher == "fake" else BaostockFetcher(args.throttle)
    )
    t0, n = time.time(), 0
    for (sym,) in todo:
        code = ("sh." if sym.startswith("SHSE") else "sz.") + sym.split(".")[1]
        rows = fetcher.bars_ohlc(code, args.start, args.end)
        con.execute("begin")
        try:
            con.execute("delete from ohlc where code=?", [code])
            if rows:
                con.executemany("insert into ohlc values (?,?,?,?,?,?)", rows)
            con.execute("update pull_log set ohlc_sha256=? where symbol=?", [ohlc_sha(rows), sym])
            con.execute("commit")
        except Exception:
            con.execute("rollback")
            raise
        n += 1
        with progress.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps({"ts": _now(), "event": "ohlc_committed", "symbol": sym, "n": len(rows)})
                + "\n"
            )
    out = {"ohlc_pulled": n, "already_had_ohlc": int(con.execute("select count(*) from pull_log where status='ok'").fetchone()[0]) - n,
           "wall_seconds": round(time.time() - t0, 1)}  # fmt: skip
    fetcher.close()
    con.close()
    return out


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
    fdups = con.execute(
        "select count(*) from (select code, dividoperatedate from factors group by 1,2 having count(*)>1)"
    ).fetchone()[0]
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
    ohlc_bad: list[str] = []
    if con.execute("select count(*) from ohlc").fetchone()[0]:
        og = {
            c: g.drop(columns="code").astype(str).values.tolist()
            for c, g in con.execute("select code, date, open, high, low, close from ohlc")
            .df()
            .groupby("code")
        }
        for sym, h in con.execute(
            "select symbol, ohlc_sha256 from pull_log where ohlc_sha256 is not null"
        ).fetchall():
            code = ("sh." if sym.startswith("SHSE") else "sz.") + sym.split(".")[1]
            rows = [[d, code, *rest] for d, *rest in og.get(code, [])]
            if ohlc_sha(rows) != h:
                ohlc_bad.append(sym)
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
        "duplicate_factor_rows": int(fdups),
        "symbols_logged_ok": int((log["status"] == "ok").sum()),
        "symbols_logged_error": int((log["status"] == "error").sum()),
        "symbol_hash_mismatch": bad_hash,
        "symbol_count_mismatch": bad_count,
        "batches_logged": int(len(bl)),
        "batch_hash_mismatch": batch_issues,
        "ohlc_hash_mismatch": ohlc_bad,
    }


def verify_prices(store: str) -> dict:
    """Gate 5 inputs.  Non-positive / non-numeric prices and factors in every price-like column that exists, OHLC
    consistency when the ohlc table is complete.  Pure read."""
    con = duckdb.connect(store, read_only=True)
    q = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    bar_rows = q("select count(*) from bars")
    out = {
        "bar_rows": int(bar_rows),
        "nonpositive_or_nonnumeric_close": int(q("select count(*) from bars where try_cast(close as double) is null or try_cast(close as double) <= 0")),
        "nonpositive_or_nonnumeric_factor": int(q("select count(*) from factors where try_cast(adjustfactor as double) is null or try_cast(adjustfactor as double) <= 0 or try_cast(foreadjustfactor as double) is null or try_cast(foreadjustfactor as double) <= 0 or try_cast(backadjustfactor as double) is null or try_cast(backadjustfactor as double) <= 0")),
    }  # fmt: skip
    n_ohlc = q("select count(*) from ohlc")
    out["ohlc_rows"] = int(n_ohlc)
    out["ohlc_evaluable"] = bool(n_ohlc > 0 and n_ohlc == bar_rows)
    if out["ohlc_evaluable"]:
        v = "try_cast(open as double) o, try_cast(high as double) h, try_cast(low as double) l, try_cast(close as double) c"
        out["nonpositive_or_nonnumeric_ohlc"] = int(q(f"select count(*) from (select {v} from ohlc) where o is null or h is null or l is null or c is null or o<=0 or h<=0 or l<=0 or c<=0"))  # fmt: skip
        out["ohlc_violations"] = int(q(f"select count(*) from (select {v} from ohlc) where h < greatest(o,c,l) or l > least(o,c,h)"))  # fmt: skip
        out["ohlc_close_differs_from_bars_close"] = int(q("select count(*) from ohlc x join bars b on b.code=x.code and b.date=x.date where abs(try_cast(x.close as double) - try_cast(b.close as double)) > 1e-9"))  # fmt: skip
        out["bars_rows_without_ohlc_row"] = int(q("select count(*) from bars b left join ohlc x on b.code=x.code and b.date=x.date where x.code is null"))  # fmt: skip
    con.close()
    return out


def promote(args: argparse.Namespace) -> dict:
    """Acceptance of a pull store for breadth computation.  STRICT: gate 5 including the OHLC clause (no waiver exists
    here), plus store integrity (no duplicates, every stock logged ok, all hashes recompute).  Writes the acceptance row
    that pull_guard.require_accepted() checks - a failing row when anything is wrong."""
    import pull_guard

    v = verify_store(args.store)
    px = verify_prices(args.store)
    problems = []
    if v["duplicate_date_code_rows"] or v["duplicate_factor_rows"]:
        problems.append("duplicate rows")
    if v["symbols_logged_error"] or not v["symbols_logged_ok"]:
        problems.append("stocks not logged ok")
    if (
        v["symbol_hash_mismatch"]
        or v["symbol_count_mismatch"]
        or v["batch_hash_mismatch"]
        or v["ohlc_hash_mismatch"]
    ):
        problems.append("hash or count mismatch")
    if px["nonpositive_or_nonnumeric_close"] or px["nonpositive_or_nonnumeric_factor"]:
        problems.append("non-positive prices or factors")
    if not px["ohlc_evaluable"]:
        problems.append("OHLC not evaluable (ohlc table absent or incomplete)")
    else:
        for k in (
            "nonpositive_or_nonnumeric_ohlc",
            "ohlc_violations",
            "ohlc_close_differs_from_bars_close",
            "bars_rows_without_ohlc_row",
        ):
            if px[k]:
                problems.append(f"{k}={px[k]}")
    con = duckdb.connect(args.store)
    con.execute(
        "create table if not exists acceptance (gate varchar, passed boolean, detail varchar, fingerprint varchar, ts varchar)"
    )
    con.execute(
        "insert into acceptance values ('gate5', ?, ?, ?, ?)",
        [
            not problems,
            json.dumps({"problems": problems, "prices": px}, default=str),
            pull_guard.fingerprint(con),
            _now(),
        ],
    )
    con.close()
    return {"accepted": not problems, "problems": problems, "prices": px}


GATES_VERSION = "v1@36a07890 + amendment A (2026-10-16)"
PER_SESSION_MIN = 0.99
OVERALL_MIN = 0.995


def gates(args: argparse.Namespace) -> dict:
    """Pilot gates.  Definition history:
    v1 (commit 36a07890): gate1 no duplicate (date, code) rows; gate2 overall expected symbol-sessions retrieved
      >= 0.995; gate3 kill-and-restart test passes; gate4 every stock logged ok, one log + hash per batch, all hashes
      recompute.
    amendment A (2026-10-16, requested by the owner before the pilot finished; v1 checks are unchanged and kept):
      gate1 also covers the factors table (no duplicate (code, event date) rows);
      gate2 adds (i) per-session coverage >= 0.99 on EVERY session and (ii) zero whole-symbol misses unless each one
        is listed in --explanations-csv (key, reason, source) with a non-empty reason;
      gate5 (new) zero non-positive / non-numeric prices and factors, and zero OHLC violations (high < max(open, close,
        low) or low > min(open, close, high)); the OHLC clause needs a COMPLETE ohlc table (pull --with-ohlc, or the
        `ohlc` supplement) - if it is absent the gate FAILS as 'not evaluable', it never passes by default."""
    sys.path.insert(0, str(Path(__file__).parent))
    import build_indicator as bi

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    u = load_universe(args.master_store, args.universe_csv)
    if args.limit:
        u = u.head(args.limit)
    write_master_csv(u, out / "master_universe.csv")
    v = verify_store(args.store)
    px = verify_prices(args.store)
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
    # per-session coverage (all boards together)
    ps = cov.groupby("date")[["expected", "missing"]].sum()
    ps = ps[ps["expected"] > 0]
    ps["coverage"] = 1 - ps["missing"] / ps["expected"]
    below = ps[ps["coverage"] < PER_SESSION_MIN]
    # whole-symbol misses must each be listed and explained
    whole = sorted(set(miss.loc[miss["kind"] == "whole_symbol", "key"])) if len(miss) else []
    expl: dict[str, str] = {}
    if getattr(args, "explanations_csv", None) and Path(args.explanations_csv).exists():
        e = pd.read_csv(args.explanations_csv, dtype={"key": str}).fillna("")
        expl = {r.key: str(r.reason).strip() for r in e.itertuples() if str(r.reason).strip()}
    unexplained = [k for k in whole if k not in expl]
    ok_symbols_complete = v["symbols_logged_ok"] == len(u) and v["symbols_logged_error"] == 0
    batches_expected = -(-len(u) // args.batch)
    waive = bool(getattr(args, "waive_gate5_ohlc", False))
    ohlc_clean = px["ohlc_evaluable"] and not (
        px["nonpositive_or_nonnumeric_ohlc"]
        or px["ohlc_violations"]
        or px["ohlc_close_differs_from_bars_close"]
        or px["bars_rows_without_ohlc_row"]
        or v["ohlc_hash_mismatch"]
    )
    res = {
        "definition_version": GATES_VERSION,
        "gate1_no_duplicate_date_code": {
            "duplicates": v["duplicate_date_code_rows"],
            "duplicate_factor_rows": v["duplicate_factor_rows"],
            "pass": v["duplicate_date_code_rows"] == 0 and v["duplicate_factor_rows"] == 0,
        },
        "gate2_expected_symbol_sessions_retrieved": {
            "expected": expected,
            "missing": missing,
            "retrieved_share": round(share, 6),
            "threshold": OVERALL_MIN,
            "per_session_threshold": PER_SESSION_MIN,
            "sessions": int(len(ps)),
            "sessions_below_threshold": int(len(below)),
            "worst_sessions": {
                str(d.date()): round(float(c), 4) for d, c in ps["coverage"].nsmallest(5).items()
            },
            "whole_symbol_misses": whole,
            "whole_symbol_unexplained": unexplained,
            "missing_by_kind": miss.groupby("kind").size().to_dict() if len(miss) else {},
            "unexpected_by_reason": unexp.groupby("reason").size().to_dict() if len(unexp) else {},
            "pass": bool(
                expected > 0 and share >= OVERALL_MIN and len(below) == 0 and not unexplained
            ),
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
            "ohlc_hash_mismatch": len(v["ohlc_hash_mismatch"]),
            "pass": bool(
                ok_symbols_complete
                and v["batches_logged"] == batches_expected
                and not v["symbol_hash_mismatch"]
                and not v["symbol_count_mismatch"]
                and not v["batch_hash_mismatch"]
                and not v["ohlc_hash_mismatch"]
            ),
        },
        "gate5_prices_and_ohlc": {
            **px,
            "ohlc_hash_mismatch": len(v["ohlc_hash_mismatch"]),
            "waiver": (
                "OHLC clause waived for the PILOT ONLY (owner, 2026-10-16); price and factor positivity still "
                "enforced; the OHLC clause is a blocking acceptance gate on the full-pull output (promote)"
                if waive
                else ""
            ),
            "pass": bool(
                px["nonpositive_or_nonnumeric_close"] == 0
                and px["nonpositive_or_nonnumeric_factor"] == 0
                and (ohlc_clean or waive)
            ),
            "note": ""
            if px["ohlc_evaluable"]
            else "OHLC not evaluable: ohlc table absent or incomplete -> gate fails",
        },
    }
    if getattr(args, "run_gate3", True):
        t = Path(__file__).parent / "test_pull_resume.py"
        run = subprocess.run([sys.executable, str(t)], capture_output=True, text=True, check=False)
        res["gate3_kill_and_restart_resumes_cleanly"] = {
            "test": t.name,
            "returncode": run.returncode,
            "output_tail": run.stdout.strip().splitlines()[-3:],
            "pass": run.returncode == 0 and "ALL TESTS PASSED" in run.stdout,
        }
    res["all_pass"] = (
        all(res[k]["pass"] for k in res if k.startswith("gate"))
        and "gate3_kill_and_restart_resumes_cleanly" in res
    )
    (out / "gates.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("pull", "gates", "ohlc"):
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
    for name in ("pull", "ohlc"):
        sub.choices[name].add_argument("--throttle", type=float, default=0.05)
        sub.choices[name].add_argument(
            "--fetcher", choices=["baostock", "fake"], default="baostock"
        )
        sub.choices[name].add_argument("--fake-delay", type=float, default=0.0)
    sub.choices["pull"].add_argument(
        "--with-ohlc", action="store_true", help="fetch open/high/low in the same call"
    )
    sub.choices["gates"].add_argument("--calendar-csv", required=True)
    sub.choices["gates"].add_argument("--out", required=True)
    sub.choices["gates"].add_argument(
        "--explanations-csv", help="key, reason, source for each whole-symbol miss"
    )
    sub.choices["gates"].add_argument(
        "--waive-gate5-ohlc",
        action="store_true",
        help="PILOT ONLY: skip the OHLC clause of gate 5 (promote has no such option)",
    )
    pr = sub.add_parser("promote", help="strict acceptance of a pull store for breadth computation")
    pr.add_argument("--store", required=True)
    a = ap.parse_args()
    if a.cmd != "promote" and not (a.master_store or a.universe_csv):
        ap.error("need --master-store or --universe-csv")
    fn = {"pull": pull, "gates": gates, "ohlc": ohlc_supplement, "promote": promote}[a.cmd]
    print(json.dumps(fn(a), indent=1, default=str))


if __name__ == "__main__":
    main()
