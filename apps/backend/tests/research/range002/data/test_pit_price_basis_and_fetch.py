"""PIT price-basis regression, spec-bound universe parameters, and the MOCK-backed fetch adapter.

SYNTHETIC. The vendor transport is a local function; nothing here touches a network or real data.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path

import duckdb
import pytest

from app.research.range002.data.bar_loader import load_session
from app.research.range002.data.fetch_adapter import (
    FetchAuthorization,
    FetchNotAuthorizedError,
    PageRequest,
    PageResponse,
    RawBar,
    fetch_and_store,
    fetch_symbol_window,
    store_fetched_bars,
    vendor_transport,
)
from app.research.range002.data.identity_map import IdentityRecord, build_identity_map
from app.research.range002.data.pit_universe import (
    BASIS_SPLIT_ADJUSTED,
    PRICE_NOT_ABOVE_MIN,
    DailyObs,
    Listing,
    UniverseParams,
    build_universe_month,
)
from app.research.range002.data.store_adapter import universe_params_from_draft
from app.research.range002.governance.errors import InvalidCapabilityError
from app.research.range002.screen.errors import DataDefectError, SpecBindingError
from app.research.range002.screen.params import extract_params
from app.research.range002.spec.loader import parse_draft
from tests.research.range002.governance.conftest import synthetic_manifest  # noqa: F401
from tests.research.range002.screen.conftest import make_capability, synth_payload

D = date
DECISION = D(2018, 2, 28)
PARAMS = UniverseParams(n=5, adv_window=3, min_price=10.0, basis=BASIS_SPLIT_ADJUSTED)


def _days(k: int = 3) -> list[date]:
    out, d = [], DECISION
    while len(out) < k:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def _obs(pid: str, close: float, close_unadj: float, vol: float) -> list[DailyObs]:
    return [DailyObs(pid, d, close, close_unadj, vol, BASIS_SPLIT_ADJUSTED) for d in _days()]


def _build(obs: list[DailyObs], pids: list[str]):  # type: ignore[no-untyped-def]
    idmap = build_identity_map([IdentityRecord(p, p, D(2005, 1, 1), None) for p in pids])
    return build_universe_month(
        D(2018, 3, 1), DECISION, [Listing(p, True, None) for p in pids], obs, idmap, PARAMS
    )


def test_a_later_split_does_not_distort_dollar_volume_or_the_price_floor() -> None:
    # traded at 100 with 1M shares; a LATER 10:1 split makes the vendor's close 10 and volume 10M.
    # close*volume = 100M either way (the factor cancels); the floor must see the traded 100.
    u = _build(_obs("SPLITTER", close=10.0, close_unadj=100.0, vol=10_000_000), ["SPLITTER"])
    m = u.members[0]
    assert m.adv == pytest.approx(100_000_000)  # not 1e9 (unadj * adjusted volume)
    assert m.prior_close == pytest.approx(100.0)  # the price seen that day


def test_the_floor_uses_the_price_seen_that_day_not_a_future_adjusted_price() -> None:
    # traded at 8 (below the floor); a later 1-for-10 reverse split makes the adjusted close 80
    u = _build(_obs("REVERSE", close=80.0, close_unadj=8.0, vol=100_000), ["REVERSE"])
    assert u.members == () and u.excluded[0].reason == PRICE_NOT_ABOVE_MIN


def test_universe_params_come_from_the_frozen_spec_and_fail_closed(tmp_path: Path) -> None:
    payload = synth_payload(**{"universe__n": 100})
    cap, _ = make_capability(tmp_path, payload)
    p = universe_params_from_draft(cap, parse_draft(payload), basis=BASIS_SPLIT_ADJUSTED)
    assert (p.n, p.adv_window, p.min_price) == (100, 20, 10.0)  # Plan v0.5 2.1, schema-pinned
    other = synth_payload(**{"universe__n": 50})  # a different spec than the capability's
    with pytest.raises(SpecBindingError):
        universe_params_from_draft(cap, parse_draft(other), basis=BASIS_SPLIT_ADJUSTED)
    with pytest.raises(InvalidCapabilityError):
        universe_params_from_draft(None, parse_draft(payload), basis=BASIS_SPLIT_ADJUSTED)


# --- mock-backed fetch adapter --------------------------------------------------------------

START = datetime(2026, 3, 2, 14, 30)
END = datetime(2026, 3, 2, 14, 40)
AUTH = FetchAuthorization("AUTH-1", "USE-REF", "ENT-REF", storage_permitted=True)


def _bar(i: int, **kw) -> RawBar:  # type: ignore[no-untyped-def]
    t = START + timedelta(minutes=i)
    return RawBar(
        t,
        kw.get("o", 10.0),
        kw.get("h", 10.1),
        kw.get("low", 9.9),
        kw.get("c", 10.0),
        100,
        None,
        None,
    )


def _paged(pages: list[list[RawBar]]):  # type: ignore[no-untyped-def]
    calls: list[PageRequest] = []

    def transport(req: PageRequest) -> PageResponse:
        calls.append(req)
        idx = 0 if req.page_token is None else int(req.page_token)
        nxt = str(idx + 1) if idx + 1 < len(pages) else None
        return PageResponse(tuple(pages[idx]), nxt)

    return transport, calls


KW = {"feed": "sip", "adjustment": "raw", "asof": "2026-03-02", "limit": 4, "max_pages": 5}


@pytest.fixture
def cap(tmp_path: Path) -> object:
    return make_capability(tmp_path, synth_payload())[0]


def test_pagination_validation_and_resume(cap: object) -> None:
    pages = [[_bar(0), _bar(1), _bar(2)], [_bar(3), _bar(4)]]
    transport, calls = _paged(pages)
    res = fetch_symbol_window(cap, transport, symbol="AAA", start_utc=START, end_utc=END, **KW)
    assert res.pages == 2 and len(res.bars) == 5 and [c.page_token for c in calls] == [None, "1"]
    assert all(c.adjustment == "raw" and c.feed == "sip" for c in calls)

    con = duckdb.connect(":memory:")
    journal: set[tuple[str, str]] = set()
    chunks = [("AAA", START, END)]
    n = fetch_and_store(cap, transport, con, chunks, authorization=AUTH, journal=journal, **KW)
    assert n == 5
    again = fetch_and_store(cap, transport, con, chunks, authorization=AUTH, journal=journal, **KW)
    assert again == 0 and con.execute("SELECT COUNT(*) FROM minute_bars").fetchone() == (5,)


@pytest.mark.parametrize(
    ("pages", "kw_over"),
    [
        ([[_bar(1), _bar(1)]], {}),  # duplicate timestamp
        ([[_bar(2), _bar(1)]], {}),  # out of order
        ([[_bar(0)] * 1 + [_bar(30)]], {}),  # outside the requested window
        ([[_bar(i) for i in range(5)]], {"limit": 4}),  # page exceeds the declared limit
        ([[_bar(0, h=9.0)]], {}),  # inconsistent OHLC
        ([[_bar(0)]], {"adjustment": "split"}),  # not raw
        ([[_bar(0)]], {"feed": "iex"}),  # not SIP
        ([[_bar(0)]], {"asof": " "}),  # asof is an explicit decision
    ],
)
def test_defective_vendor_responses_are_refused(cap: object, pages, kw_over) -> None:  # type: ignore[no-untyped-def]
    transport, _ = _paged(pages)
    with pytest.raises(DataDefectError):
        fetch_symbol_window(
            cap, transport, symbol="AAA", start_utc=START, end_utc=END, **{**KW, **kw_over}
        )


def test_a_repeating_page_token_is_a_loop_not_a_hang(cap: object) -> None:
    def loop(req: PageRequest) -> PageResponse:
        return PageResponse((_bar(0),) if req.page_token is None else (), "same")

    with pytest.raises(DataDefectError, match="repeated"):
        fetch_symbol_window(cap, loop, symbol="AAA", start_utc=START, end_utc=END, **KW)


def test_storage_and_real_transport_are_conditional_on_authorization(cap: object) -> None:
    transport, _ = _paged([[_bar(0)]])
    res = fetch_symbol_window(cap, transport, symbol="AAA", start_utc=START, end_utc=END, **KW)
    con = duckdb.connect(":memory:")
    for bad in (None, FetchAuthorization("A", "U", "E", storage_permitted=False)):
        with pytest.raises(FetchNotAuthorizedError):
            store_fetched_bars(cap, con, res, authorization=bad, journal=set(), chunk_key="k")
    with pytest.raises(FetchNotAuthorizedError):
        vendor_transport(cap, None)
    with pytest.raises(NotImplementedError):  # authorised, but no real transport exists in BUILD
        vendor_transport(cap, AUTH)
    with pytest.raises(InvalidCapabilityError):
        fetch_symbol_window(None, transport, symbol="AAA", start_utc=START, end_utc=END, **KW)


def test_mock_fetch_to_store_to_loader_round_trip(tmp_path: Path, cap: object) -> None:
    bars = [_bar(i) for i in range(10)]
    transport, _ = _paged([bars])
    con = duckdb.connect(":memory:")
    window = (datetime(2026, 3, 2, 14, 30), datetime(2026, 3, 2, 14, 40))
    fetch_and_store(
        cap,
        transport,
        con,
        [("AAA", *window)],
        authorization=AUTH,
        journal=set(),
        **{**KW, "limit": 100},
    )
    params = extract_params(cap, parse_draft(synth_payload()))
    s = load_session(
        cap, con, params, "AAA", D(2026, 3, 2), time(16, 0),
        source_feed=params.feed, source_ts_convention=params.bar_timestamp_convention,
        no_trade_evidence=frozenset(), halt_minutes=frozenset(),
    )  # fmt: skip
    assert s is not None and s.bars[0].start == time(9, 30) and len(s.bars) == 10
    assert time(9, 40) in s.gap_minutes  # unfetched minutes are unresolved gaps, never invented
