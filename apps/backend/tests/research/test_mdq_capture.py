"""MDQ-001 collector unit tests — store immutability, provenance, identity
latch, and paired sampling. No network; the Alpaca client and the account
getter are faked."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from datetime import time as clock_time
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from app.research.capture.collector import (
    ET,
    PHASE_A_UNIVERSE,
    SAMPLER_START_ET,
    SlotGrid,
    SlotStamp,
    fetch_session_bars,
    iter_scheduled_slots,
    sample_quotes_cycle,
)
from app.research.capture.identity import (
    AcquisitionPins,
    IdentityError,
    key_fingerprint,
    verify_identity,
)
from app.research.capture.store import (
    CaptureStore,
    FrozenPartitionError,
    PartitionRef,
)

SESSION = date(2026, 8, 17)


# --- identity -----------------------------------------------------------------


def test_key_fingerprint_is_stable_12_hex() -> None:
    fp = key_fingerprint("PKTESTKEY123")
    assert len(fp) == 12
    assert fp == key_fingerprint("PKTESTKEY123")
    int(fp, 16)  # valid hex


def test_verify_identity_rejects_wrong_fingerprint() -> None:
    pins = AcquisitionPins(key_fingerprint=key_fingerprint("EXPECTED"))
    with pytest.raises(IdentityError, match="fingerprint"):
        verify_identity("OTHER", "s", pins, account_getter=lambda *_: "PA3BGKRLH2AP")


def test_verify_identity_rejects_wrong_account() -> None:
    pins = AcquisitionPins(key_fingerprint=key_fingerprint("K"))
    with pytest.raises(IdentityError, match="account"):
        verify_identity("K", "s", pins, account_getter=lambda *_: "PAWRONGACCT")


def test_verify_identity_passes_and_returns_account() -> None:
    pins = AcquisitionPins(key_fingerprint=key_fingerprint("K"))
    assert (
        verify_identity("K", "s", pins, account_getter=lambda *_: pins.account_number)
        == pins.account_number
    )


def test_default_pins_are_the_account7_latch() -> None:
    pins = AcquisitionPins()
    assert pins.account_number == "PA3BGKRLH2AP"
    assert pins.key_fingerprint == "5b6f39e5198d"


def test_account_getter_surfaces_only_the_account_number(monkeypatch) -> None:
    """Payload discipline (plan v0.5 §3.1): /v2/account returns execution-plane
    state alongside the broker id; only account_number may leave the HTTP
    boundary — equity, buying power, etc. are discarded, never propagated."""
    import httpx

    from app.research.capture.identity import _get_account_number

    payload = {
        "account_number": "PA3BGKRLH2AP",
        "equity": "123456.78",
        "buying_power": "246913.56",
        "cash": "1.00",
        "status": "ACTIVE",
    }

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return payload

    captured: dict = {}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        return _FakeResponse()

    monkeypatch.setattr(httpx, "get", fake_get)
    result = _get_account_number("https://paper-api.alpaca.markets", "K", "S")
    assert result == "PA3BGKRLH2AP"
    assert isinstance(result, str)  # a scalar, not the payload
    assert captured["url"].endswith("/v2/account")


# --- store --------------------------------------------------------------------


def test_partition_ref_rejects_unknown_feed() -> None:
    with pytest.raises(ValueError):
        PartitionRef(feed="best_available", session=SESSION)


def test_append_write_freeze_verify_roundtrip(tmp_path) -> None:
    store = CaptureStore(tmp_path)
    ref = PartitionRef(feed="sip", session=SESSION)
    store.append_jsonl(ref, "quotes", [{"symbol": "SPY", "bid": 1.0}])
    store.write_parquet(ref, "bars", "bars_1min", pd.DataFrame({"symbol": ["SPY"], "close": [1.0]}))

    mpath = store.freeze(ref, provenance={"credential_fingerprint": "abc"})
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    assert manifest["feed"] == "sip"
    assert manifest["credential_fingerprint"] == "abc"
    assert {f["path"] for f in manifest["files"]} == {
        "quotes/samples.jsonl",
        "bars/bars_1min.parquet",
    }
    assert store.verify(ref) == []


def test_frozen_partition_refuses_all_writes(tmp_path) -> None:
    store = CaptureStore(tmp_path)
    ref = PartitionRef(feed="iex", session=SESSION)
    store.append_jsonl(ref, "quotes", [{"symbol": "SPY"}])
    store.freeze(ref, provenance={})
    with pytest.raises(FrozenPartitionError):
        store.append_jsonl(ref, "quotes", [{"symbol": "QQQ"}])
    with pytest.raises(FrozenPartitionError):
        store.write_parquet(ref, "bars", "x", pd.DataFrame({"a": [1]}))
    with pytest.raises(FrozenPartitionError):
        store.freeze(ref, provenance={})


def test_verify_detects_tamper_and_unmanifested_files(tmp_path) -> None:
    store = CaptureStore(tmp_path)
    ref = PartitionRef(feed="sip", session=SESSION)
    path = store.append_jsonl(ref, "quotes", [{"symbol": "SPY"}])
    store.freeze(ref, provenance={})

    path.write_text("tampered\n", encoding="utf-8")
    problems = store.verify(ref)
    assert any("hash mismatch" in p for p in problems)

    (store.partition_dir(ref) / "rogue.txt").write_text("x", encoding="utf-8")
    assert any("unmanifested" in p for p in store.verify(ref))


def test_freeze_refuses_empty_partition(tmp_path) -> None:
    store = CaptureStore(tmp_path)
    ref = PartitionRef(feed="sip", session=SESSION)
    store.partition_dir(ref).mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        store.freeze(ref, provenance={})


# --- collector primitives -----------------------------------------------------


class _FakeQuote(SimpleNamespace):
    pass


class _FakeClient:
    """Records every request so tests can assert explicit feed binding."""

    def __init__(self) -> None:
        self.requests: list = []

    def get_stock_latest_quote(self, req):
        self.requests.append(req)
        ts = datetime(2026, 8, 17, 14, 30, tzinfo=UTC)
        return {
            sym: _FakeQuote(
                timestamp=ts,
                bid_price=99.0,
                ask_price=101.0,
                bid_size=1.0,
                ask_size=2.0,
                bid_exchange="V",
                ask_exchange="V",
                conditions=["R"],
            )
            for sym in req.symbol_or_symbols
            if sym != "MISSING"
        }

    def get_stock_bars(self, req):
        self.requests.append(req)
        bar = SimpleNamespace(
            timestamp=datetime(2026, 8, 17, 13, 30, tzinfo=UTC),
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
            volume=100.0,
            trade_count=7,
            vwap=1.4,
        )
        return SimpleNamespace(data={s: [bar] for s in req.symbol_or_symbols})


def test_sample_cycle_pairs_feeds_and_binds_explicit_feed() -> None:
    client = _FakeClient()
    out = sample_quotes_cycle(client, ("SPY", "MISSING"))
    assert set(out) == {"iex", "sip"}
    assert [str(r.feed.value) for r in client.requests] == ["iex", "sip"]
    iex = {r["symbol"]: r for r in out["iex"]}
    assert iex["SPY"]["bid"] == 99.0 and iex["SPY"]["ask"] == 101.0
    assert iex["MISSING"]["missing"] is True
    # paired: both feeds share one cycle_ts
    assert out["iex"][0]["cycle_ts"] == out["sip"][0]["cycle_ts"]


def test_fetch_session_bars_tidy_frame_with_explicit_feed() -> None:
    client = _FakeClient()
    df = fetch_session_bars(client, ("SPY", "QQQ"), SESSION, "sip")
    assert str(client.requests[0].feed.value) == "sip"
    assert sorted(df["symbol"]) == ["QQQ", "SPY"]
    assert set(df.columns) >= {"symbol", "ts", "open", "close", "volume", "trade_count", "vwap"}


def test_phase_a_universe_is_the_proposed_default() -> None:
    assert "SPY" in PHASE_A_UNIVERSE and "XLK" in PHASE_A_UNIVERSE
    assert len(PHASE_A_UNIVERSE) == 14


# --- the frozen slot grid -----------------------------------------------------


def _grid(close_et: clock_time, *, session: date = SESSION, cadence: int = 60) -> SlotGrid:
    """Grid for ``session`` with an explicitly supplied close — the tests never
    reach for a market calendar, so they stay offline and deterministic."""
    return SlotGrid.for_session(
        session, datetime.combine(session, close_et, tzinfo=ET), cadence_seconds=cadence
    )


def _et(grid_ts: datetime) -> str:
    return grid_ts.astimezone(ET).strftime("%H:%M:%S")


def test_slot_grid_is_395_slots_on_a_normal_1600_close() -> None:
    """09:25 ET inclusive -> 16:00 ET exclusive at 60s = 395 slots (09:25..15:59)."""
    g = _grid(clock_time(16, 0))
    assert g.expected_cycles == 395
    assert _et(g.slot_ts(0)) == "09:25:00"
    assert _et(g.slot_ts(394)) == "15:59:00"
    assert _et(g.slot_ts(395)) == "16:00:00"  # the close itself is NOT a slot
    assert g.contains(0) and g.contains(394)
    assert not g.contains(395) and not g.contains(-1)


def test_slot_grid_is_215_slots_on_a_1300_early_close() -> None:
    g = _grid(clock_time(13, 0))
    assert g.expected_cycles == 215
    assert _et(g.slot_ts(214)) == "12:59:00"
    assert not g.contains(215)


def test_slot_grid_has_no_slots_when_the_window_is_empty_or_inverted() -> None:
    assert _grid(SAMPLER_START_ET).expected_cycles == 0  # close == start
    assert _grid(clock_time(9, 0)).expected_cycles == 0  # close before start


def test_slot_grid_index_floors_into_the_slot_minute() -> None:
    g = _grid(clock_time(16, 0))

    def at(h: int, m: int, s: int = 0) -> datetime:
        return datetime.combine(SESSION, clock_time(h, m, s), tzinfo=ET)

    assert g.slot_index_at(at(9, 25)) == 0
    assert g.slot_index_at(at(9, 25, 59)) == 0
    assert g.slot_index_at(at(9, 26)) == 1
    assert g.slot_index_at(at(15, 59, 59)) == 394
    assert g.slot_index_at(at(9, 24, 59)) == -1  # before the grid, never clamped here
    with pytest.raises(ValueError):
        g.slot_index_at(datetime(2026, 8, 17, 9, 30))  # naive


def test_slot_grid_rejects_naive_bounds_and_bad_cadence() -> None:
    start = datetime.combine(SESSION, SAMPLER_START_ET, tzinfo=ET)
    with pytest.raises(ValueError):
        SlotGrid(start=start.replace(tzinfo=None), end=start + timedelta(hours=6))
    with pytest.raises(ValueError):
        SlotGrid(start=start, end=start + timedelta(hours=6), cadence_seconds=0)


# --- fixed-rate scheduling ----------------------------------------------------


class _FakeClock:
    """Paired monotonic + wall clock. ``sleep`` advances both; nothing sleeps for
    real, and no test result depends on how fast the fixture happens to run."""

    def __init__(
        self, wall: datetime, mono: float = 10_000.0, *, sleep_overshoot: float = 0.0
    ) -> None:
        self.wall = wall
        self.mono = mono
        # Real sleeps always overshoot a little. That is the jitter source that
        # a naive scheduler turns into ACCUMULATING phase error.
        self.sleep_overshoot = sleep_overshoot
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.mono

    def now(self) -> datetime:
        return self.wall

    def advance(self, seconds: float) -> None:
        self.mono += seconds
        self.wall += timedelta(seconds=seconds)

    def advance_wall_only(self, seconds: float) -> None:
        """A wall-clock step (NTP correction) with no monotonic time elapsed."""
        self.wall += timedelta(seconds=seconds)

    def sleep(self, seconds: float) -> None:
        assert seconds > 0, f"the scheduler must never sleep {seconds}"
        self.sleeps.append(seconds)
        self.advance(seconds + self.sleep_overshoot)


def _drive(grid, clock, *, work, max_cycles=0, on_slots_missed=None):
    """Run the scheduler to completion, spending ``work`` seconds per cycle.

    ``work`` may be a float or ``callable(nth_cycle) -> float``.
    """
    seen: list[tuple[SlotStamp, datetime]] = []
    for slot in iter_scheduled_slots(
        grid,
        max_cycles=max_cycles,
        monotonic=clock.monotonic,
        now=clock.now,
        sleep=clock.sleep,
        on_slots_missed=on_slots_missed,
    ):
        seen.append((slot, clock.now()))
        clock.advance(work(len(seen) - 1) if callable(work) else work)
    return seen


def test_fixed_delay_sleeping_is_the_defect_it_under_runs_the_grid() -> None:
    """The defect, reproduced against the same clock: ``sleep(cadence)`` AFTER
    the work makes the true start-to-start interval ``cadence + work``, so a
    capture with ZERO outages still under-runs the 395-slot grid and fails the
    98% floor. The floor is ratified — the scheduler was wrong."""
    grid = _grid(clock_time(16, 0))
    clock = _FakeClock(grid.start)
    cycles = 0
    while clock.now() < grid.end:
        clock.advance(5.0)  # the cycle: 2 REST calls + 2 JSONL appends
        cycles += 1
        clock.sleep(grid.cadence_seconds)
    assert cycles == 365
    assert cycles / grid.expected_cycles < 0.98


def test_fixed_rate_schedule_fills_every_slot_despite_per_cycle_work() -> None:
    """The fix: the same 5s cycle, scheduled against absolute deadlines, hits
    all 395 slots — the work is absorbed by the wait instead of accumulating."""
    grid = _grid(clock_time(16, 0))
    clock = _FakeClock(grid.start)
    seen = _drive(grid, clock, work=5.0)

    assert [s.index for s, _ in seen] == list(range(395))
    assert len(seen) / grid.expected_cycles == 1.0
    # every cycle starts exactly on its slot: no drift, ever
    assert all(ran == s.ts for s, ran in seen)
    starts = [ran for _, ran in seen]
    assert {(b - a).total_seconds() for a, b in zip(starts, starts[1:], strict=False)} == {60.0}


def test_fixed_rate_absorbs_work_far_beyond_the_breakeven_overhead() -> None:
    """Breakeven for the old loop was ~1.24s of per-cycle work; at 30s the old
    loop lost a third of the session. Fixed-rate loses nothing until the work
    exceeds the cadence itself."""
    grid = _grid(clock_time(16, 0))
    clock = _FakeClock(grid.start)
    assert len(_drive(grid, clock, work=30.0)) == grid.expected_cycles


def test_an_overrunning_cycle_loses_its_slots_and_never_bursts() -> None:
    """A cycle that overruns its slot does NOT get made up: the slots it
    consumed stay missed and count against completeness. No rapid-fire cycles
    follow — that would fabricate completeness the capture did not earn."""
    grid = _grid(clock_time(9, 35))  # 10 slots: 09:25..09:34
    clock = _FakeClock(grid.start)
    missed: list[tuple[int, int]] = []
    # cycle #3 stalls for 150s (2.5 slots); everything else is quick
    seen = _drive(
        grid,
        clock,
        work=lambda n: 150.0 if n == 3 else 1.0,
        on_slots_missed=lambda first, resumed: missed.append((first, resumed)),
    )

    indices = [s.index for s, _ in seen]
    assert indices == [0, 1, 2, 3, 6, 7, 8, 9]
    assert 4 not in indices and 5 not in indices  # missed, and never revisited
    assert missed == [(4, 6)]
    # no burst: consecutive cycles are never closer together than the cadence
    starts = [ran for _, ran in seen]
    assert all(
        (b - a).total_seconds() >= grid.cadence_seconds
        for a, b in zip(starts, starts[1:], strict=False)
    )
    # and the schedule re-locks onto the grid instead of drifting by 150s
    assert seen[-1][1] == grid.slot_ts(9)


def test_a_cycle_overrunning_the_close_stops_rather_than_bursting_at_the_end() -> None:
    grid = _grid(clock_time(9, 30))  # 5 slots: 09:25..09:29
    clock = _FakeClock(grid.start)
    seen = _drive(grid, clock, work=lambda n: 400.0 if n == 1 else 1.0)
    assert [s.index for s, _ in seen] == [0, 1]
    assert all(ran < grid.end for _, ran in seen)


def test_no_cycle_begins_at_or_after_the_close() -> None:
    grid = _grid(clock_time(9, 30))
    clock = _FakeClock(grid.start)
    seen = _drive(grid, clock, work=5.0)
    assert [s.index for s, _ in seen] == [0, 1, 2, 3, 4]
    assert _et(seen[-1][0].ts) == "09:29:00"  # 09:30 is the close: not a slot
    assert all(ran < grid.end and s.ts < grid.end for s, ran in seen)


def test_close_is_tested_on_the_wall_clock_before_the_cycle_not_after() -> None:
    """A wall-clock step past the close must stop the sampler BEFORE the next
    cycle, not after it has already written a post-close observation."""
    grid = _grid(clock_time(9, 35))
    clock = _FakeClock(grid.start)
    seen: list[SlotStamp] = []
    for slot in iter_scheduled_slots(
        grid, monotonic=clock.monotonic, now=clock.now, sleep=clock.sleep
    ):
        seen.append(slot)
        clock.advance(1.0)
        if len(seen) == 2:
            clock.advance_wall_only(3600)  # NTP step to well past the close
    assert [s.index for s in seen] == [0, 1]


def test_starting_late_begins_on_the_current_slot_without_back_filling() -> None:
    grid = _grid(clock_time(16, 0))
    clock = _FakeClock(grid.start + timedelta(minutes=35, seconds=30))  # 10:00:30 ET
    seen = _drive(grid, clock, work=1.0, max_cycles=3)
    assert [s.index for s, _ in seen] == [35, 36, 37]
    assert _et(seen[0][0].ts) == "10:00:00"
    assert seen[0][1] == grid.start + timedelta(minutes=35, seconds=30)  # fired at once
    assert seen[1][1] == grid.slot_ts(36)  # then re-locked onto the grid


def test_starting_early_waits_for_slot_zero_and_never_goes_negative() -> None:
    grid = _grid(clock_time(16, 0))
    clock = _FakeClock(grid.start - timedelta(seconds=30))
    seen = _drive(grid, clock, work=1.0, max_cycles=2)
    assert [s.index for s, _ in seen] == [0, 1]
    assert seen[0][1] == grid.start
    assert clock.sleeps[0] == 30.0


def test_max_cycles_stops_the_schedule() -> None:
    grid = _grid(clock_time(16, 0))
    clock = _FakeClock(grid.start)
    assert len(_drive(grid, clock, work=1.0, max_cycles=7)) == 7


def test_a_session_with_no_slots_schedules_nothing() -> None:
    grid = _grid(clock_time(9, 25))
    clock = _FakeClock(grid.start)
    assert _drive(grid, clock, work=1.0) == []


# --- phase lock: the deployment gate ------------------------------------------
#
# Owner ruling 2026-08-18, added as a deployment gate. The count assertions
# above and the no-burst assertion below both pass on a schedule that is quietly
# drifting: the defect class is SUB-CADENCE per-cycle overhead (measured
# breakeven ~1.24s), where nothing crashes, no cycle looks wrong in isolation,
# and the only symptom is phase error accumulating against the grid origin over
# hundreds of cycles. So assert the start INSTANTS against the absolute grid,
# and assert that the error does not GROW with k.


def _phase_errors(starts: list[datetime], grid: SlotGrid) -> list[float]:
    """|actual start of the k-th cycle - (T0 + k*cadence)| in seconds.

    Measured against the grid ORIGIN, never against the previous start: a
    per-step spacing check passes on a slowly drifting schedule, cumulative
    phase against T0 does not.
    """
    return [abs((ran - grid.slot_ts(k)).total_seconds()) for k, ran in enumerate(starts)]


def _assert_phase_locked(
    starts: list[datetime], grid: SlotGrid, *, tolerance: float = 1e-6
) -> None:
    """The property under test: every cycle starts at T0 + k*cadence, and the
    error at the end of the session is no worse than at the beginning."""
    errors = _phase_errors(starts, grid)
    assert max(errors) <= tolerance, f"phase error up to {max(errors):.3f}s against the grid"
    assert errors[-1] <= errors[0] + tolerance, (
        f"phase error accumulated: {errors[0]:.6f}s at k=0 -> {errors[-1]:.6f}s at k={len(errors) - 1}"
    )


def _fixed_delay_starts(
    grid: SlotGrid, work, cycles: int, *, sleep_overshoot: float = 0.0
) -> list[datetime]:
    """Start instants of the OLD, defective loop: sleep(cadence) AFTER the work,
    so the true start-to-start interval is cadence + work."""
    clock = _FakeClock(grid.start, sleep_overshoot=sleep_overshoot)
    starts: list[datetime] = []
    for n in range(cycles):
        starts.append(clock.now())
        clock.advance(work(n) if callable(work) else work)
        clock.sleep(grid.cadence_seconds)
    return starts


@pytest.mark.parametrize(
    ("work", "label"),
    [
        (1.5, "constant 1.5s"),
        (2.0, "constant 2.0s"),
        (lambda n: 1.5 + (n % 7) * 0.1, "jittery 1.5-2.1s"),
    ],
)
def test_sub_cadence_work_never_accumulates_phase_error(work, label) -> None:
    """DEPLOYMENT GATE. 1.5-2.0s of per-cycle work — above the ~1.24s measured
    breakeven, far below the 60s cadence — across a full 395-slot session. The
    scheduled starts must stay T0, T0+60, T0+120 ... and NOT T0, T0+61.5,
    T0+123 ... The jittery case proves the lock is not an artifact of a constant
    work time.
    """
    grid = _grid(clock_time(16, 0))
    clock = _FakeClock(grid.start)
    seen = _drive(grid, clock, work=work)

    # contiguous: 1.5-2.1s of overhead is nowhere near a slot, so nothing is missed
    assert [s.index for s, _ in seen] == list(range(395)), label
    assert len(seen) == grid.expected_cycles

    starts = [ran for _, ran in seen]
    _assert_phase_locked(starts, grid)

    # the three checkpoints the owner asked to see, stated explicitly
    errors = _phase_errors(starts, grid)
    assert errors[1] == 0.0, f"{label}: k=1 phase error {errors[1]:.6f}s"
    assert errors[100] == 0.0, f"{label}: k=100 phase error {errors[100]:.6f}s"
    assert errors[394] == 0.0, f"{label}: k=394 phase error {errors[394]:.6f}s"

    # the emitted stamp is the grid instant itself, exactly — this is what makes
    # observed_cycles reproducible against the frozen grid
    for slot, ran in seen:
        assert slot.ts == grid.slot_ts(slot.index)
        assert ran == slot.ts


@pytest.mark.parametrize("work", [1.5, 2.0])
def test_the_phase_lock_gate_actually_catches_fixed_delay_drift(work) -> None:
    """The paired negative case: the SAME assertion, applied to fixed-delay
    semantics, must FAIL. Without this the gate above could be passing
    vacuously."""
    grid = _grid(clock_time(16, 0))
    starts = _fixed_delay_starts(grid, work, cycles=395)
    errors = _phase_errors(starts, grid)

    # drift is exactly k*work: the per-cycle overhead lands in the interval
    assert errors[1] == pytest.approx(work)
    assert errors[100] == pytest.approx(100 * work)
    assert errors[394] == pytest.approx(394 * work)
    assert errors[394] > 9 * 60  # ~10 minutes of phase error by the close

    with pytest.raises(AssertionError, match="phase error"):
        _assert_phase_locked(starts, grid)


@pytest.mark.parametrize("work", [1.5, 2.0])
def test_sub_cadence_work_is_where_fixed_delay_silently_failed_the_floor(work) -> None:
    """Why the gate matters: at 1.5-2.0s the old loop never crashes, never
    bursts and never logs anything — it just runs out of session early and lands
    under the ratified 98% floor with a perfectly healthy feed."""
    grid = _grid(clock_time(16, 0))
    clock = _FakeClock(grid.start)
    fixed_delay_cycles = 0
    while clock.now() < grid.end:
        clock.advance(work)
        fixed_delay_cycles += 1
        clock.sleep(grid.cadence_seconds)

    assert fixed_delay_cycles < grid.expected_cycles
    assert fixed_delay_cycles / grid.expected_cycles < 0.98
    # and the fix, same work, same clock:
    assert len(_drive(grid, _FakeClock(grid.start), work=work)) == grid.expected_cycles


OVERSHOOT = 0.003  # every real sleep(x) returns a little after x


@pytest.mark.parametrize("work", [1.5, 2.0])
def test_phase_lock_holds_when_every_sleep_overshoots(work) -> None:
    """The gate, hardened: an EXACT fake clock would let a drifting scheduler
    look perfect, so make every sleep overshoot by 3ms — the realistic jitter
    source. Fixed-rate absorbs it (bounded, constant error, because the next
    deadline is absolute); fixed-delay compounds it into the interval.
    """
    grid = _grid(clock_time(16, 0))
    clock = _FakeClock(grid.start, sleep_overshoot=OVERSHOOT)
    seen = _drive(grid, clock, work=work)

    assert [s.index for s, _ in seen] == list(range(395))
    errors = _phase_errors([r for _, r in seen], grid)

    # bounded by ONE overshoot, no matter how many cycles have gone by
    assert max(errors) <= OVERSHOOT + 1e-6, (
        f"phase error grew past one sleep overshoot: {max(errors):.6f}s"
    )
    assert errors[394] == pytest.approx(errors[1], abs=1e-9), (
        f"phase error accumulated with k: {errors[1]:.6f}s at k=1 -> {errors[394]:.6f}s at k=394"
    )
    _assert_phase_locked([r for _, r in seen], grid, tolerance=OVERSHOOT + 1e-6)

    # the same jitter under fixed-delay compounds into (work + overshoot) per cycle
    drifted = _phase_errors(_fixed_delay_starts(grid, work, 395, sleep_overshoot=OVERSHOOT), grid)
    assert drifted[394] == pytest.approx(394 * (work + OVERSHOOT))
    assert drifted[394] > 500.0  # 8+ minutes of phase error by the close


# --- slot stamping on the record ---------------------------------------------


def test_every_record_of_a_cycle_carries_its_scheduled_slot() -> None:
    """observed_cycles must be reproducible against the frozen grid rather than
    inferred from wall-clock timestamps — so the scheduled slot is persisted,
    additively, alongside the existing shared cycle_ts."""
    grid = _grid(clock_time(16, 0))
    slot = grid.stamp(7)
    out = sample_quotes_cycle(_FakeClient(), ("SPY", "MISSING"), slot=slot)

    for records in out.values():
        for rec in records:
            assert rec["slot_index"] == 7
            assert rec["scheduled_slot_ts"] == grid.slot_ts(7).isoformat()
            assert _et(datetime.fromisoformat(rec["scheduled_slot_ts"])) == "09:32:00"
    # paired-feed semantics preserved: one cycle identity across both feeds
    assert out["iex"][0]["cycle_ts"] == out["sip"][0]["cycle_ts"]
    assert {r["slot_index"] for r in out["iex"]} == {r["slot_index"] for r in out["sip"]}


def test_a_failed_feed_record_still_carries_the_slot() -> None:
    """The error record keeps the slot auditable: a failed feed is a slot that
    was scheduled and attempted, not a slot that never existed."""

    class _FlakyClient(_FakeClient):
        def get_stock_latest_quote(self, req):
            if str(req.feed.value) == "sip":
                raise ConnectionError("transient")
            return super().get_stock_latest_quote(req)

    slot = SlotStamp(index=12, ts=datetime(2026, 8, 17, 13, 37, tzinfo=UTC))
    out = sample_quotes_cycle(_FlakyClient(), ("SPY",), slot=slot)
    err = out["sip"][0]
    assert "feed_error" in err
    assert err["slot_index"] == 12
    assert err["scheduled_slot_ts"] == "2026-08-17T13:37:00+00:00"


def test_records_without_a_slot_keep_the_legacy_shape() -> None:
    """Schema compatibility: the slot stamp is additive. Nothing was renamed or
    removed, and a partition captured before the stamp existed still parses —
    cycle_ts remains the cycle identity."""
    out = sample_quotes_cycle(_FakeClient(), ("SPY",))
    rec = out["iex"][0]
    assert "cycle_ts" in rec
    assert "slot_index" not in rec and "scheduled_slot_ts" not in rec


# --- structural invariants (ADR 0051 / registration §7 control 1) --------------


def test_capture_package_http_boundary_is_structural() -> None:
    """app/research/capture performs raw HTTP for exactly one purpose — the
    read-only GET /v2/account identity latch. Raw HTTP must never grow into
    trading capability: no mutating verbs, no other /v2/ endpoints, no
    alpaca.trading import (MDQ-001 registration §7 control 1)."""
    import re

    import app.research.capture as pkg

    pkg_dir = Path(pkg.__file__).parent
    forbidden_verbs = re.compile(
        r"(httpx|requests)\.(post|put|delete|patch)\(|\.request\(\s*[\"'](POST|PUT|DELETE|PATCH)"
    )
    v2_endpoint = re.compile(r"/v2/[a-zA-Z_/]+")
    for path in sorted(pkg_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert not forbidden_verbs.search(text), f"mutating HTTP verb in {path.name}"
        for hit in v2_endpoint.findall(text):
            assert hit.startswith("/v2/account"), f"non-identity /v2/ endpoint {hit} in {path.name}"
        trading_import = re.compile(r"^\s*(from|import)\s+alpaca\.trading", re.MULTILINE)
        assert not trading_import.search(text), f"trading SDK import in {path.name}"
        # No order-path or broker-module imports: the package imports nothing
        # from app.* outside itself (plan v0.3 §4.5 — structural, not reviewed).
        app_import = re.compile(r"^\s*(?:from|import)\s+(app\.[\w.]+)", re.MULTILINE)
        for mod in app_import.findall(text):
            assert mod.startswith("app.research.capture"), (
                f"foreign app import {mod} in {path.name}"
            )


def test_sample_cycle_isolates_per_feed_failures() -> None:
    """A transient failure on one feed must not lose the other feed's cycle;
    the failed feed gets a single auditable error record (frozen retry policy)."""

    class _FlakyClient(_FakeClient):
        def get_stock_latest_quote(self, req):
            if str(req.feed.value) == "sip":
                raise ConnectionError("transient")
            return super().get_stock_latest_quote(req)

    out = sample_quotes_cycle(_FlakyClient(), ("SPY",))
    assert out["iex"][0]["bid"] == 99.0
    assert len(out["sip"]) == 1 and "feed_error" in out["sip"][0]
    assert "ConnectionError" in out["sip"][0]["feed_error"]
