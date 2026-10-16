"""Forced socket-timeout test for BaostockFetcher / pull (offline: a stub vendor module and a silent local server).
Run: python3 test_pull_timeout_retry.py

One call for a bars request and one for a factors request hang on a real socket that never answers.  With the
fetcher's socket timeout set to 0.3 s each raises, is retried after a fresh login, and the stock must then be
committed exactly once: the resulting store must be identical (per-stock hashes, row counts, no duplicates) to an
unforced pull of the same universe."""

import argparse
import socket
import sys
import tempfile
import threading
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import pull_baostock as P  # noqa: E402

CODES = [
    ("SHSE", "600000"),
    ("SZSE", "000001"),
    ("SHSE", "688001"),
    ("SZSE", "300001"),
    ("SHSE", "601166"),
]


class SilentServer:
    """Accepts connections and never replies, so a recv() on it can only end by timeout."""

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.conns: list[socket.socket] = []
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            self.conns.append(c)

    def close(self) -> None:
        for c in self.conns:
            c.close()
        self.sock.close()


class Result:
    def __init__(self, fields: list[str], rows: list[list[str]]):
        self.error_code, self.error_msg, self.fields = "0", "", fields
        self._rows, self._i = rows, -1

    def next(self) -> bool:
        self._i += 1
        return self._i < len(self._rows)

    def get_row_data(self) -> list[str]:
        return self._rows[self._i]


class StubBaostock:
    """Vendor stand-in.  `hang_on` = {(kind, code): n}: the first n calls of that kind for that code block on the
    silent socket (and so die by the fetcher's socket timeout)."""

    def __init__(self, hang_on: dict, port: int):
        self.hang_on, self.port = dict(hang_on), port
        self.logins = self.logouts = 0
        self.calls: list[tuple[str, str]] = []
        self.fake = P.FakeFetcher()

    def login(self) -> Result:
        self.logins += 1
        return Result([], [])

    def logout(self) -> None:
        self.logouts += 1

    def _maybe_hang(self, kind: str, code: str) -> None:
        self.calls.append((kind, code))
        if self.hang_on.get((kind, code), 0) > 0:
            self.hang_on[(kind, code)] -= 1
            c = socket.create_connection(("127.0.0.1", self.port))
            try:
                c.recv(
                    1
                )  # never answered -> raises socket.timeout once the default timeout expires
            finally:
                c.close()

    def query_history_k_data_plus(
        self, code, fields, start_date, end_date, frequency, adjustflag
    ) -> Result:
        self._maybe_hang("bars", code)
        return Result(fields.split(","), self.fake.bars(code, start_date, end_date))

    def query_adjust_factor(self, code, start_date, end_date) -> Result:
        self._maybe_hang("factors", code)
        rows = [[code, *r] for r in self.fake.factors(code, start_date, end_date)]
        return Result(
            ["code", "dividOperateDate", "foreAdjustFactor", "backAdjustFactor", "adjustFactor"],
            rows,
        )


def args_for(uni: Path, store: Path, fetcher: str) -> argparse.Namespace:
    return argparse.Namespace(
        master_store=None, universe_csv=str(uni), store=str(store), start="2024-01-02", end="2024-03-29",
        batch=2, limit=0, throttle=0.0, fetcher=fetcher, fake_delay=0.0,
    )  # fmt: skip


def per_stock(store: Path) -> pd.DataFrame:
    import duckdb

    con = duckdb.connect(str(store), read_only=True)
    out = con.execute(
        "select symbol, status, n_bars, n_factors, sha256, batch_id from pull_log order by symbol"
    ).df()
    con.close()
    return out


def test_forced_timeout_retries_and_commits_once() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        uni = t / "uni.csv"
        pd.DataFrame(
            [
                {
                    "symbol": f"{e}.{c}",
                    "name": c,
                    "list_date": "2010-01-04",
                    "delist_date": "2038-01-01",
                }
                for e, c in CODES
            ]
        ).to_csv(uni, index=False)
        ref = t / "ref.duckdb"
        P.pull(args_for(uni, ref, "fake"))

        srv = SilentServer()
        stub = StubBaostock({("bars", "sz.000001"): 1, ("factors", "sh.688001"): 1}, srv.port)
        orig = P.BaostockFetcher
        P.BaostockFetcher = lambda throttle: orig(
            throttle, retries=3, timeout=0.3, backoff=0.01, bs_module=stub
        )
        try:
            forced = t / "forced.duckdb"
            summary = P.pull(args_for(uni, forced, "baostock"))
        finally:
            P.BaostockFetcher = orig
            srv.close()
            socket.setdefaulttimeout(None)

        assert summary["ok_total"] == len(CODES) and summary["error_total"] == 0, summary
        assert stub.hang_on == {("bars", "sz.000001"): 0, ("factors", "sh.688001"): 0}, (
            "timeouts were not triggered"
        )
        assert stub.calls.count(("bars", "sz.000001")) == 2, (
            "bars call should have been retried once"
        )
        assert stub.calls.count(("factors", "sh.688001")) == 2, (
            "factors call should have been retried once"
        )
        assert stub.logins == 3 and stub.logouts >= 2, (
            stub.logins,
            stub.logouts,
        )  # initial + one re-login per timeout
        v = P.verify_store(str(forced))
        assert v["duplicate_date_code_rows"] == 0, v
        assert (
            not v["symbol_hash_mismatch"]
            and not v["symbol_count_mismatch"]
            and not v["batch_hash_mismatch"]
        ), v
        a, b = per_stock(ref), per_stock(forced)
        assert a.drop(columns="status").equals(b.drop(columns="status")), (
            "forced-timeout pull differs from unforced pull"
        )
        import duckdb

        con = duckdb.connect(str(forced), read_only=True)
        for sym in ("sz.000001", "sh.688001"):
            n = con.execute("select count(*) from bars where code=?", [sym]).fetchone()[0]
            ref_n = len(P.FakeFetcher().bars(sym, "2024-01-02", "2024-03-29"))
            assert n == ref_n, (sym, n, ref_n)  # committed exactly once
        con.close()
        print(
            "ok forced socket timeout on a bars call and a factors call: each retried once after re-login, each stock committed exactly once, store identical to an unforced pull"
        )


if __name__ == "__main__":
    test_forced_timeout_retries_and_commits_once()
    print("ALL TESTS PASSED")
