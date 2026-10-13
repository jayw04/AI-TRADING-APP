"""SIP minute fetch: Alpaca transport + bounded CLI core. SYNTHETIC; a fake HTTP function only.

No network, no credentials: environment values are sentinels injected through a mapping.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import pytest

from app.research.range002.data.alpaca_transport import (
    AlpacaTransportConfig,
    HttpReply,
    RequestCapExceededError,
    TransportError,
    build_alpaca_transport,
)
from app.research.range002.data.bar_loader import load_session
from app.research.range002.data.fetch_adapter import (
    FetchAuthorization,
    FetchNotAuthorizedError,
    PageRequest,
    fetch_symbol_window,
    store_fetched_bars,
    vendor_transport,
)
from app.research.range002.governance.errors import InvalidCapabilityError
from app.research.range002.screen.errors import DataDefectError
from app.research.range002.screen.params import extract_params
from app.research.range002.spec.loader import parse_draft
from tests.research.range002.governance.conftest import synthetic_manifest  # noqa: F401
from tests.research.range002.screen.conftest import make_capability, synth_payload

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "research" / "range002"))
import fetch_sip_minutes as fsm  # noqa: E402

_ET = ZoneInfo("America/New_York")
_C: Any = None


def _T(cfg: AlpacaTransportConfig) -> Any:
    return build_alpaca_transport(_C, cfg)


SENTINEL_KEY = "PKSENTINEL0KEY0VALUE"
SENTINEL_SECRET = "SENTINEL0SECRET0VALUE0XYZ"
ENV = {"K_ENV": SENTINEL_KEY, "S_ENV": SENTINEL_SECRET}
AUTH = FetchAuthorization("AUTH-1", "PU-REF", "ENT-REF", storage_permitted=True)
START = datetime(2026, 3, 2, 5, 0)
END = datetime(2026, 3, 3, 5, 0)


@pytest.fixture
def cap(tmp_path: Path, synthetic_manifest: Any) -> object:  # noqa: F811
    global _C
    _C = make_capability(tmp_path, synth_payload())[0]
    return _C


@pytest.fixture(autouse=True)
def _bind_capability(cap: object) -> None:
    return None


def _session_bars(start: datetime, end: datetime, minutes: int = 5) -> list[dict[str, Any]]:
    """Weekday bars 09:30.. (``minutes`` of them) ET inside [start, end), as vendor JSON."""
    out: list[dict[str, Any]] = []
    d = start.replace(tzinfo=UTC).astimezone(_ET).date()
    last = (end - timedelta(seconds=1)).replace(tzinfo=UTC).astimezone(_ET).date()
    while d <= last:
        if d.weekday() < 5:
            for i in range(minutes):
                t = datetime.combine(d, time(9, 30), tzinfo=_ET) + timedelta(minutes=i)
                u = t.astimezone(UTC)
                if start <= u.replace(tzinfo=None) < end:
                    out.append(
                        {"t": u.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": 10.0, "h": 10.5, "l": 9.5,
                         "c": 10.2, "v": 100 + i, "n": 3, "vw": 10.1}
                    )  # fmt: skip
        d += timedelta(days=1)
    return out


class FakeVendor:
    """Callable HttpGet. Records every request; serves paged session bars."""

    def __init__(self, *, fail_on_call: int | None = None, statuses: list[int] | None = None):
        self.calls: list[dict[str, Any]] = []
        self.fail_on_call = fail_on_call
        self.statuses = list(statuses or [])

    def __call__(
        self, url: str, params: Mapping[str, str], headers: Mapping[str, str]
    ) -> HttpReply:
        self.calls.append({"url": url, "params": dict(params), "headers": dict(headers)})
        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call:
            raise TransportError("synthetic network failure")
        if self.statuses:
            st = self.statuses.pop(0)
            if st != 200:
                return HttpReply(st, {"retry-after": "1"}, None)
        s = datetime.strptime(params["start"], "%Y-%m-%dT%H:%M:%SZ")
        e = datetime.strptime(params["end"], "%Y-%m-%dT%H:%M:%SZ")
        bars = _session_bars(s, e)
        sym = url.rsplit("/", 2)[-2]
        lim = int(params["limit"])
        off = int(params.get("page_token", "0"))
        page = bars[off : off + lim]
        nxt = str(off + lim) if off + lim < len(bars) else None
        return HttpReply(200, {}, {"bars": page, "symbol": sym, "next_page_token": nxt})


def _cfg(vendor: FakeVendor, **kw: Any) -> AlpacaTransportConfig:
    clock = kw.pop("clock", None)
    sleep = kw.pop("sleep", None)
    base: dict[str, Any] = {
        "key_env": "K_ENV", "secret_env": "S_ENV", "requests_per_minute": 6000,
        "max_retries": 2, "max_requests": 1000, "environ": ENV, "http_get": vendor,
        "clock": clock or (lambda: 0.0), "sleep": sleep or (lambda _s: None),
    }  # fmt: skip
    base.update(kw)
    return AlpacaTransportConfig(**base)


def _req(**kw: Any) -> PageRequest:
    base: dict[str, Any] = {
        "symbol": "AAA", "start_utc": START, "end_utc": END, "feed": "sip",
        "adjustment": "raw", "asof": "-", "limit": 3, "page_token": None,
    }  # fmt: skip
    base.update(kw)
    return PageRequest(**base)


# ------------------------------------------------------------------ transport


def test_request_shape_and_pagination_through_the_adapter(cap: object) -> None:
    v = FakeVendor()
    t = _T(_cfg(v))
    res = fetch_symbol_window(
        cap, t, symbol="AAA", start_utc=START, end_utc=END, feed="sip", adjustment="raw",
        asof="-", limit=3, max_pages=10,
    )  # fmt: skip
    assert len(res.bars) == 5 and res.pages == 2
    p0, p1 = v.calls[0]["params"], v.calls[1]["params"]
    assert v.calls[0]["url"] == "https://data.alpaca.markets/v2/stocks/AAA/bars"
    assert p0["timeframe"] == "1Min" and p0["feed"] == "sip" and p0["adjustment"] == "raw"
    assert p0["asof"] == "-" and p0["sort"] == "asc" and p0["limit"] == "3"
    assert p0["start"] == "2026-03-02T05:00:00Z" and "page_token" not in p0
    assert p1["page_token"] == "3"
    assert v.calls[0]["headers"]["APCA-API-KEY-ID"] == SENTINEL_KEY


@pytest.mark.parametrize("over", [{"feed": "iex"}, {"adjustment": "split"}, {"asof": " "}])
def test_transport_refuses_non_sip_non_raw_and_missing_asof(over: dict[str, str]) -> None:
    v = FakeVendor()
    with pytest.raises(DataDefectError):
        _T(_cfg(v))(_req(**over))
    assert v.calls == []


def test_retry_on_429_then_success_and_bounded_failure() -> None:
    sleeps: list[float] = []
    v = FakeVendor(statuses=[429, 503, 200])
    t = _T(_cfg(v, sleep=sleeps.append))
    assert len(t(_req()).bars) == 3 and t.http_attempts() == 3
    assert 1.0 in sleeps  # Retry-After honoured

    v2 = FakeVendor(statuses=[500, 500, 500, 200])
    t2 = _T(_cfg(v2, max_retries=2))
    with pytest.raises(TransportError, match="bounded") as ei:
        t2(_req())
    assert t2.http_attempts() == 3
    assert SENTINEL_KEY not in str(ei.value) and SENTINEL_SECRET not in str(ei.value)


def test_non_retryable_status_is_not_retried() -> None:
    v = FakeVendor(statuses=[403])
    t = _T(_cfg(v))
    with pytest.raises(TransportError, match="403"):
        t(_req())
    assert len(v.calls) == 1


def test_rate_limit_argument_is_respected_with_a_fake_clock() -> None:
    now = [0.0]
    slept: list[float] = []

    def sleep(s: float) -> None:
        slept.append(s)
        now[0] += s

    t = _T(_cfg(FakeVendor(), requests_per_minute=30, clock=lambda: now[0], sleep=sleep))
    for _ in range(4):
        t(_req(limit=100))
    assert slept == pytest.approx([2.0, 2.0, 2.0])  # 60/30 s between every pair of requests


def test_max_requests_cap_fails_closed_without_sending() -> None:
    v = FakeVendor()
    t = _T(_cfg(v, max_requests=2))
    t(_req(limit=100))
    t(_req(limit=100))
    with pytest.raises(RequestCapExceededError):
        t(_req(limit=100))
    assert len(v.calls) == 2


def test_missing_credentials_name_the_variable_not_a_value() -> None:
    with pytest.raises(TransportError) as ei:
        _T(_cfg(FakeVendor(), environ={"K_ENV": SENTINEL_KEY}))
    assert "S_ENV" in str(ei.value) and SENTINEL_KEY not in str(ei.value)


def test_repr_and_network_exception_do_not_leak_the_key() -> None:
    v = FakeVendor(fail_on_call=1)
    t = _T(_cfg(v))
    assert SENTINEL_KEY not in repr(t) and SENTINEL_SECRET not in repr(t)
    with pytest.raises(TransportError) as ei:
        t(_req())
    assert SENTINEL_KEY not in str(ei.value)


@pytest.mark.parametrize(
    "body",
    [
        {
            "bars": [
                {"t": "2026-03-02T14:30:00Z", "o": float("nan"), "h": 1, "l": 1, "c": 1, "v": 1}
            ]
        },
        {"bars": [{"t": "2026-03-02T14:30:00", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]},
        {"bars": "x"},
        {"symbol": "ZZZ", "bars": []},
        {"bars": [], "next_page_token": ""},
    ],
)
def test_malformed_vendor_bodies_are_defects(body: dict[str, Any]) -> None:
    def get(_u: str, _p: Mapping[str, str], _h: Mapping[str, str]) -> HttpReply:
        return HttpReply(200, {}, body)

    with pytest.raises(DataDefectError):
        _T(_cfg(FakeVendor(), http_get=get))(_req())


def test_out_of_window_and_non_increasing_bars_are_refused_by_the_adapter(cap: object) -> None:
    def make(bars: list[dict[str, Any]]) -> Any:
        def get(_u: str, _p: Mapping[str, str], _h: Mapping[str, str]) -> HttpReply:
            return HttpReply(200, {}, {"bars": bars, "next_page_token": None})

        return _T(_cfg(FakeVendor(), http_get=get))

    b = _session_bars(START, END)
    kw: dict[str, Any] = {
        "symbol": "AAA", "start_utc": START, "end_utc": END, "feed": "sip",
        "adjustment": "raw", "asof": "-", "limit": 10, "max_pages": 3,
    }  # fmt: skip
    with pytest.raises(DataDefectError, match="out-of-order|duplicate"):
        fetch_symbol_window(cap, make([b[1], b[0]]), **kw)
    late = dict(b[0], t="2026-03-09T14:30:00Z")
    with pytest.raises(DataDefectError, match="outside"):
        fetch_symbol_window(cap, make([late]), **kw)


def test_vendor_transport_keeps_the_authorization_gates(cap: object) -> None:
    v = FakeVendor()
    with pytest.raises(FetchNotAuthorizedError):
        vendor_transport(cap, None, config=_cfg(v))
    with pytest.raises(FetchNotAuthorizedError):
        vendor_transport(cap, FetchAuthorization("A", " ", "E", True), config=_cfg(v))
    with pytest.raises(InvalidCapabilityError):
        vendor_transport(object(), AUTH, config=_cfg(v))
    with pytest.raises(NotImplementedError):
        vendor_transport(cap, AUTH)
    assert callable(vendor_transport(cap, AUTH, config=_cfg(v)))
    with pytest.raises(FetchNotAuthorizedError):
        store_fetched_bars(
            cap, duckdb.connect(":memory:"),
            fetch_symbol_window(
                cap, _T(_cfg(FakeVendor())), symbol="AAA", start_utc=START,
                end_utc=END, feed="sip", adjustment="raw", asof="-", limit=10, max_pages=3,
            ),
            authorization=FetchAuthorization("A", "U", "E", False), journal=set(), chunk_key="k",
        )  # fmt: skip


# ------------------------------------------------------------------ CLI core


def _cfg_run(tmp: Path, mode: str = "store", **kw: Any) -> fsm.RunConfig:
    base: dict[str, Any] = {
        "mode": mode, "symbols": ("AAA", "BBB"), "date_from": date(2026, 3, 2),
        "date_to": date(2026, 4, 3), "asof": "-", "limit": 40, "max_pages": 20,
        "universe_sha256": "0" * 64, "requests_per_minute": 6000, "max_requests": 1000,
        "authorization": AUTH, "permission_basis_claimed": "owner claim: personal use",
        "store_path": tmp / "min.duckdb", "journal_path": tmp / "journal.jsonl",
        "script_sha256": "1" * 64,
    }  # fmt: skip
    base.update(kw)
    return fsm.RunConfig(**base)


def _run(cap: object, cfg: fsm.RunConfig, v: FakeVendor, **tkw: Any) -> dict[str, Any]:
    t = _T(_cfg(v, **tkw))
    return fsm.run_fetch(cap, t, cfg, http_attempts=t.__dict__["http_attempts"])


def _rows(path: Path) -> int:
    con = duckdb.connect(str(path), read_only=True)
    try:
        return int(con.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0])
    finally:
        con.close()


def test_windows_are_month_aligned_et_midnight() -> None:
    ch = fsm.build_chunks(("AAA",), date(2026, 3, 2), date(2026, 4, 3))
    assert [(s.isoformat(), e.isoformat()) for _, s, e in ch] == [
        ("2026-03-02T05:00:00", "2026-04-01T04:00:00"),  # EST then EDT after Mar 8
        ("2026-04-01T04:00:00", "2026-04-04T04:00:00"),
    ]


def test_store_run_schema_basis_manifest_and_no_secret(cap: object, tmp_path: Path) -> None:
    v = FakeVendor()
    m = _run(cap, _cfg_run(tmp_path), v)
    assert m["status"] == "COMPLETE" and m["permission_verified"] is False
    assert m["license_status"] == "UNKNOWN" and m["license_sources"] == ["alpaca_market_data"]
    assert m["permission_basis_claimed"] == "owner claim: personal use"
    assert m["totals"]["bars"] == m["totals"]["store_rows"] == _rows(tmp_path / "min.duckdb")
    assert m["totals"]["http_requests"] == len(v.calls)
    assert m["store"]["sha256"] and m["scope"]["windows_done"] == 4
    con = duckdb.connect(str(tmp_path / "min.duckdb"), read_only=True)
    cols = [
        r[0] for r in con.execute('SELECT column_name FROM (DESCRIBE "minute_bars")').fetchall()
    ]
    assert cols == ["symbol", "ts", "open", "high", "low", "close", "volume", "basis"]
    assert con.execute("SELECT DISTINCT basis FROM minute_bars").fetchall() == [("raw",)]
    con.close()
    conv = m["convention_check"]
    assert conv["first_regular_minute_et_histogram"] == {"09:30": conv["symbol_days"]}
    assert set(conv["utc_hhmm_of_0930_et_bar_histogram"]) == {"14:30", "13:30"}
    for p in tmp_path.iterdir():  # every artefact: manifest, journal, days, sidecars, store
        assert SENTINEL_KEY.encode() not in p.read_bytes()
        assert SENTINEL_SECRET.encode() not in p.read_bytes()
    assert (tmp_path / "min.duckdb.license.json").exists()


def test_resume_does_not_rerequest_or_double_write(cap: object, tmp_path: Path) -> None:
    cfg = _cfg_run(tmp_path)
    v1 = FakeVendor()
    boom = _cfg(v1, max_requests=3)  # dies mid-run on the request cap
    t = _T(boom)
    with pytest.raises(RequestCapExceededError):
        fsm.run_fetch(cap, t, cfg, http_attempts=t.__dict__["http_attempts"])
    done_lines = [json.loads(x) for x in (tmp_path / "journal.jsonl").read_text().splitlines()]
    n_done = sum(1 for r in done_lines if r["type"] == "chunk")
    assert 0 < n_done < 4

    v2 = FakeVendor()
    m = _run(cap, cfg, v2)
    assert m["status"] == "COMPLETE"
    requested = {(c["url"], c["params"]["start"]) for c in v2.calls}
    assert len(requested) == 4 - n_done  # journaled windows are never requested again
    assert _rows(tmp_path / "min.duckdb") == m["totals"]["bars"]

    v3 = FakeVendor()
    _run(cap, cfg, v3)  # a third run: everything journaled, nothing requested or written
    assert v3.calls == [] and _rows(tmp_path / "min.duckdb") == m["totals"]["bars"]


def test_resume_refuses_a_different_invocation_or_a_lone_file(cap: object, tmp_path: Path) -> None:
    _run(cap, _cfg_run(tmp_path), FakeVendor())
    with pytest.raises(fsm.FetchRefusal, match="header"):
        _run(cap, _cfg_run(tmp_path, asof="2026-03-01"), FakeVendor())
    (tmp_path / "journal.jsonl").unlink()
    with pytest.raises(fsm.FetchRefusal, match="both exist"):
        _run(cap, _cfg_run(tmp_path), FakeVendor())


def test_counts_only_writes_nothing(cap: object, tmp_path: Path) -> None:
    before = sorted(p.name for p in tmp_path.iterdir())
    out = _run(cap, _cfg_run(tmp_path, "counts-only"), FakeVendor())
    assert out["store_writes"] is False and out["symbol_days"][0]["bars"] == 5
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_store_mode_requires_storage_permitted_flag(cap: object, tmp_path: Path) -> None:
    no_store = FetchAuthorization("A", "U", "E", storage_permitted=False)
    v = FakeVendor()
    before = sorted(p.name for p in tmp_path.iterdir())
    with pytest.raises(fsm.FetchRefusal, match="storage-permitted"):
        _run(cap, _cfg_run(tmp_path, authorization=no_store), v)
    assert v.calls == [] and sorted(p.name for p in tmp_path.iterdir()) == before


def test_max_requests_cap_through_the_cli_core_keeps_journal_consistent(
    cap: object, tmp_path: Path
) -> None:
    v = FakeVendor()
    t = _T(_cfg(v, max_requests=4))
    cfg = _cfg_run(tmp_path)
    with pytest.raises(RequestCapExceededError):
        fsm.run_fetch(cap, t, cfg, http_attempts=t.__dict__["http_attempts"])
    assert len(v.calls) == 4
    journal = [json.loads(x) for x in (tmp_path / "journal.jsonl").read_text().splitlines()]
    assert sum(r.get("bars", 0) for r in journal[1:]) == _rows(tmp_path / "min.duckdb") > 0


def test_dry_plan_and_arg_refusals_touch_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "d").mkdir()
    u = tmp_path / "d" / "u.txt"
    u.write_text("# comment\nAAA\nBBB\n", encoding="utf-8")
    rc = fsm.main(
        ["--mode", "dry-plan", "--universe-file", str(u), "--date-from", "2026-03-02",
         "--date-to", "2026-04-03", "--asof", "-", "--limit", "10000"]
    )  # fmt: skip
    plan = json.loads(capsys.readouterr().out)
    assert rc == 0 and plan["symbol_windows"] == 4 and plan["network"] is False
    assert plan["requests_worst_case"] >= plan["requests_lower_bound"]
    assert [p.name for p in u.parent.iterdir()] == ["u.txt"]
    rc = fsm.main(
        ["--mode", "store", "--universe-file", str(u), "--date-from", "2026-03-02",
         "--date-to", "2026-04-03", "--asof", "-"]
    )  # fmt: skip
    assert rc == 2 and "missing required" in capsys.readouterr().err


def test_universe_file_rejects_duplicates_and_junk(tmp_path: Path) -> None:
    u = tmp_path / "u.txt"
    u.write_text("AAA\nAAA\n", encoding="utf-8")
    with pytest.raises(fsm.FetchRefusal):
        fsm.read_universe(u)
    u.write_text("aaa\n", encoding="utf-8")
    with pytest.raises(fsm.FetchRefusal):
        fsm.read_universe(u)


def test_round_trip_store_is_what_the_runner_loader_reads(cap: object, tmp_path: Path) -> None:
    _run(cap, _cfg_run(tmp_path, symbols=("AAA",)), FakeVendor())
    payload = synth_payload()
    params = extract_params(cap, parse_draft(payload))
    con = duckdb.connect(str(tmp_path / "min.duckdb"), read_only=True)
    s = load_session(
        cap, con, params, "AAA", date(2026, 3, 2), time(16, 0), permaticker="P1",
        source_feed=params.feed, source_ts_convention=params.bar_timestamp_convention,
        no_trade_evidence=frozenset(), halt_minutes=frozenset(),
    )  # fmt: skip
    con.close()
    assert s is not None and len(s.bars) == 5 and s.bars[0].start == time(9, 30)
    assert params.intraday_price_basis == "raw"


def test_vendor_end_is_inclusive_so_the_transport_asks_for_the_last_instant_before_end(
    cap: object,
) -> None:
    """Observed 2026-10-13 on the first real request: a bar labelled exactly at `end` came back
    (the adapter flagged it outside [start, end) and aborted before any bulk fetch). The transport
    must therefore request `end - 1s`, and a vendor with an inclusive end must then yield no bar
    at `end`."""

    class InclusiveEndVendor(FakeVendor):
        def __call__(
            self, url: str, params: Mapping[str, str], headers: Mapping[str, str]
        ) -> HttpReply:
            self.calls.append({"url": url, "params": dict(params), "headers": dict(headers)})
            s = datetime.strptime(params["start"], "%Y-%m-%dT%H:%M:%SZ")
            e = datetime.strptime(params["end"], "%Y-%m-%dT%H:%M:%SZ")
            bars: list[dict[str, Any]] = []
            t = s
            while t <= e:  # INCLUSIVE end, on the minute grid
                if t.second == 0:
                    bars.append(
                        {
                            "t": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "o": 10.0, "h": 10.1, "l": 9.9, "c": 10.0, "v": 100,
                            "n": 1, "vw": 10.0,
                        }
                    )  # fmt: skip
                t += timedelta(minutes=1)
            sym = url.rsplit("/", 2)[-2]
            return HttpReply(200, {}, {"bars": bars, "symbol": sym, "next_page_token": None})

    v = InclusiveEndVendor()
    res = fetch_symbol_window(
        cap, _T(_cfg(v)), symbol="AAA", start_utc=START, end_utc=END, feed="sip",
        adjustment="raw", asof="-", limit=10_000, max_pages=2,
    )  # fmt: skip
    assert v.calls[0]["params"]["end"] == (END - timedelta(seconds=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    assert res.bars and all(START <= b.t < END for b in res.bars)
    assert res.bars[-1].t == END - timedelta(minutes=1)


def test_adjacent_windows_neither_drop_nor_duplicate_a_boundary_bar(cap: object) -> None:
    """Two adjacent [start, end) windows against a vendor whose `end` is inclusive: the bar labelled
    exactly at the shared boundary belongs to the second window only, and the union of the two
    results equals one continuous series, each bar once."""

    class Continuous(FakeVendor):
        def __call__(
            self, url: str, params: Mapping[str, str], headers: Mapping[str, str]
        ) -> HttpReply:
            self.calls.append({"url": url, "params": dict(params), "headers": dict(headers)})
            s = datetime.strptime(params["start"], "%Y-%m-%dT%H:%M:%SZ")
            e = datetime.strptime(params["end"], "%Y-%m-%dT%H:%M:%SZ")
            bars: list[dict[str, Any]] = []
            t = s
            while t <= e:  # inclusive end
                if t.second == 0:
                    bars.append(
                        {
                            "t": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "o": 10.0, "h": 10.1, "l": 9.9, "c": 10.0, "v": 100,
                            "n": 1, "vw": 10.0,
                        }
                    )  # fmt: skip
                t += timedelta(minutes=1)
            sym = url.rsplit("/", 2)[-2]
            return HttpReply(200, {}, {"bars": bars, "symbol": sym, "next_page_token": None})

    boundary = START + timedelta(minutes=20)
    stop = START + timedelta(minutes=40)
    t = _T(_cfg(Continuous()))
    first = fetch_symbol_window(
        cap, t, symbol="AAA", start_utc=START, end_utc=boundary, feed="sip", adjustment="raw",
        asof="-", limit=10_000, max_pages=2,
    )  # fmt: skip
    second = fetch_symbol_window(
        cap, t, symbol="AAA", start_utc=boundary, end_utc=stop, feed="sip", adjustment="raw",
        asof="-", limit=10_000, max_pages=2,
    )  # fmt: skip
    stamps = [b.t for b in first.bars] + [b.t for b in second.bars]
    assert len(stamps) == len(set(stamps)) == 40
    assert stamps == [START + timedelta(minutes=i) for i in range(40)]
    assert first.bars[-1].t == boundary - timedelta(minutes=1)
    assert second.bars[0].t == boundary


def test_mapped_symbol_is_requested_with_asof_and_stored_under_the_vendor_ticker(
    cap: object, tmp_path: Path
) -> None:
    """A vendor-disambiguated ticker ('APC1') is requested from Alpaca under its base symbol with
    the window's date as asof, and its bars are stored under the vendor ticker so the runner's
    expected symbol-days still match; unmapped symbols are untouched."""
    v = FakeVendor()
    cfg = _cfg_run(
        tmp_path,
        symbols=("AAA", "APC1"),
        date_from=date(2026, 3, 2),
        date_to=date(2026, 3, 6),
        symbol_map={"APC1": (("2026-03-02", "APC"),)},
    )
    _run(cap, cfg, v)
    requested = {(c["url"].rsplit("/", 2)[-2], c["params"]["asof"]) for c in v.calls}
    assert requested == {("AAA", "-"), ("APC", "2026-03-02")}
    con = duckdb.connect(str(tmp_path / "min.duckdb"), read_only=True)
    try:
        stored = {r[0] for r in con.execute("SELECT DISTINCT symbol FROM minute_bars").fetchall()}
    finally:
        con.close()
    assert stored == {"AAA", "APC1"}


def test_a_rename_inside_the_window_is_split_without_dropping_or_duplicating_bars(
    cap: object, tmp_path: Path
) -> None:
    """CB-style: the vendor ticker 'CB' traded as 'ACE' until a change date inside the window. The
    window is split at ET midnight of the change date; each part is requested under its own symbol
    and asof; bars are stored once, under the vendor ticker."""
    v = FakeVendor()
    cfg = _cfg_run(
        tmp_path,
        symbols=("CB",),
        date_from=date(2026, 3, 2),
        date_to=date(2026, 3, 6),
        symbol_map={"CB": (("2026-03-02", "ACE"), ("2026-03-04", "CB"))},
    )
    _run(cap, cfg, v)
    requested = [(c["url"].rsplit("/", 2)[-2], c["params"]["asof"]) for c in v.calls]
    assert ("ACE", "2026-03-02") in requested and ("CB", "2026-03-04") in requested
    assert all(sym in ("ACE", "CB") for sym, _ in requested)
    con = duckdb.connect(str(tmp_path / "min.duckdb"), read_only=True)
    try:
        syms = {r[0] for r in con.execute("SELECT DISTINCT symbol FROM minute_bars").fetchall()}
        n, nd = con.execute("SELECT COUNT(*), COUNT(DISTINCT ts) FROM minute_bars").fetchone()
    finally:
        con.close()
    assert syms == {"CB"} and n == nd and n > 0


def test_schedule_segments_cover_the_window_exactly_once() -> None:
    from datetime import datetime

    start, end = datetime(2016, 1, 1, 5), datetime(2016, 2, 1, 5)
    segs = fsm.schedule_segments((("2016-01-01", "ACE"), ("2016-01-15", "CB")), start, end)
    assert [s[0] for s in segs] == ["ACE", "CB"]
    assert segs[0][1] == start and segs[-1][2] == end and segs[0][2] == segs[1][1]
