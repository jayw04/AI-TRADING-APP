"""Phase-A REST capture primitives (registration §7).

Two capture modes, both REST — Phase A deliberately arms NO websocket, which
makes subordination to the account-7 transition executor trivial (a couple of
requests per minute) and leaves streaming to Phase B where K2 requires it:

  * ``sample_quotes_cycle`` — one multi-symbol latest-quote request per feed
    per cycle, producing time-aligned SIP/IEX quote pairs (K6 stub-quote
    analysis needs paired same-instant observations).
  * ``fetch_session_bars`` — end-of-session 1-minute bars 04:00–16:00 ET per
    feed (premarket + RTH — the registered census scope; postmarket is
    deliberately not collected without a qualification reason, and the 16:00
    cutoff is what makes the 16:30-capture/16:45-freeze schedule sound). Bars
    carry volume, trade_count and vwap, covering the K1/K3 census fields
    without raw-tape storage cost.

The sampler's *schedule* lives here too — ``SlotGrid`` and
``iter_scheduled_slots`` — because the completeness threshold is measured
against a slot grid, so the emitter and the checker must agree on what a slot
IS. Scheduling is FIXED-RATE against absolute deadlines, never fixed-delay
sleeping (owner ruling 2026-08-18): ``sleep(cadence)`` *after* a cycle makes the
true start-to-start interval ``cadence + per-cycle work``, which drifts a
perfectly healthy capture below the frozen 98% floor with no outage at all.

Every request names its feed explicitly (§3.1; check_marketdata_feed_pinning.sh).
The client is passed in untyped — construction and identity-latching live in
scripts/mdq_collector.py.
"""

from __future__ import annotations

import math
import time as time_mod
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Proposed Phase-A capture universe — FROZEN at registration sign-off (§8).
# SPY/QQQ/IWM + the 11 SPDR sector ETFs; the acct-7 transition set and the
# ≤50-symbol scanner sample are appended via the --universe-file override so
# the frozen list lives in one reviewed artifact, not in code drift.
PHASE_A_UNIVERSE: tuple[str, ...] = (
    "SPY",
    "QQQ",
    "IWM",
    "XLB",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLRE",
    "XLU",
    "XLV",
    "XLY",
)

CAPTURE_MODE_SAMPLER = "rest_quote_sampler_v1"
CAPTURE_MODE_EOD_BARS = "rest_eod_bars_v1"

# --- the frozen slot grid ----------------------------------------------------
#
# The quote sampler's schedule is a fixed grid of instants, not "whatever the
# sleep loop produced". Owner ruling 2026-08-18:
#
#     sampler_start   = 09:25 America/New_York
#     sampler_end     = the official NYSE close, EXCLUSIVE
#     cadence         = 60 s
#     expected_cycles = |{ t : t = sampler_start + k*cadence,
#                          sampler_start <= t < sampler_end, k >= 0 }|
#
# HALF-OPEN: a slot exactly at the close is NOT a slot. 395 on a normal 16:00
# close, 215 on a 13:00 half day, 0 on a non-session. Every emitted cycle
# carries its ``slot_index`` and ``scheduled_slot_ts`` so ``observed_cycles``
# is reproducible against this grid rather than inferred from wall-clock drift.

SAMPLER_START_ET = time(9, 25)
DEFAULT_CADENCE_SECONDS = 60


@dataclass(frozen=True)
class SlotStamp:
    """Identity of one scheduled cycle on the grid: which slot, and when that
    slot was *due* (not when the cycle happened to run)."""

    index: int
    ts: datetime

    def as_record_fields(self) -> dict[str, Any]:
        return {"slot_index": self.index, "scheduled_slot_ts": self.ts.isoformat()}


@dataclass(frozen=True)
class SlotGrid:
    """The half-open scheduled-sampling grid ``[start, end)`` at ``cadence``.

    ``start`` and ``end`` are timezone-aware; ``end`` is the official NYSE close
    and is EXCLUSIVE. The market calendar is the only source of ``end`` — this
    class never guesses a close, a half day or a holiday.
    """

    start: datetime
    end: datetime
    cadence_seconds: int = DEFAULT_CADENCE_SECONDS

    def __post_init__(self) -> None:
        if self.cadence_seconds <= 0:
            raise ValueError(f"cadence must be positive, got {self.cadence_seconds}")
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("slot-grid bounds must be timezone-aware")

    @classmethod
    def for_session(
        cls,
        session: date,
        session_close: datetime,
        *,
        start_et: time = SAMPLER_START_ET,
        cadence_seconds: int = DEFAULT_CADENCE_SECONDS,
    ) -> SlotGrid:
        """Grid for one session. ``session_close`` comes from the market
        calendar (it carries half days and holidays); it is exclusive."""
        return cls(
            start=datetime.combine(session, start_et, tzinfo=ET).astimezone(UTC),
            end=session_close.astimezone(UTC),
            cadence_seconds=cadence_seconds,
        )

    @property
    def expected_cycles(self) -> int:
        """Count of slots ``t`` with ``start <= t < end`` — the completeness
        denominator. ``ceil`` (not ``floor``+1) is what makes the grid
        half-open: on an exact multiple of the cadence the instant at ``end``
        is excluded."""
        span = (self.end - self.start).total_seconds()
        if span <= 0:
            return 0
        return math.ceil(span / self.cadence_seconds)

    def slot_ts(self, index: int) -> datetime:
        return self.start + timedelta(seconds=index * self.cadence_seconds)

    def slot_index_at(self, when: datetime) -> int:
        """Index of the slot whose minute contains ``when`` (negative before
        the grid starts)."""
        if when.tzinfo is None:
            raise ValueError("slot_index_at requires a timezone-aware datetime")
        return math.floor((when - self.start).total_seconds() / self.cadence_seconds)

    def contains(self, index: int) -> bool:
        return 0 <= index < self.expected_cycles

    def stamp(self, index: int) -> SlotStamp:
        return SlotStamp(index=index, ts=self.slot_ts(index))


def _now_utc() -> datetime:
    return datetime.now(UTC)


def iter_scheduled_slots(
    grid: SlotGrid,
    *,
    max_cycles: int = 0,
    monotonic: Callable[[], float] = time_mod.monotonic,
    now: Callable[[], datetime] = _now_utc,
    sleep: Callable[[float], None] = time_mod.sleep,
    on_slots_missed: Callable[[int, int], None] | None = None,
) -> Iterator[SlotStamp]:
    """Yield each due slot of ``grid`` at a true fixed rate.

    FIXED-RATE, not fixed-delay: the consumer's per-cycle work happens between
    a yield and the next resumption, and the wait is computed from the slot's
    ABSOLUTE deadline (``anchor + k*cadence``) measured on the monotonic clock —
    so per-cycle work is absorbed by the wait instead of accumulating into the
    interval. A 5-second cycle still produces 395 cycles against a 395-slot
    session; the old ``sleep(cadence)``-after-work form produced ~365.

    NO BURST, NO CATCH-UP. If a cycle overruns its slot the slots it consumed
    stay missed and count against completeness (``on_slots_missed(first, next)``
    reports them); the iterator resumes on the next FUTURE slot rather than
    firing rapid cycles to make the count up. Deadline exactly reached counts as
    on time — only a deadline already in the past is a miss.

    The wall clock is re-read and tested against ``grid.end`` immediately BEFORE
    each yield, so a cycle never begins at or after the close; and the grid is
    half-open, so slot ``expected_cycles`` (the instant of the close) is never
    scheduled. ``monotonic``/``now``/``sleep`` are injectable for tests.
    """
    anchor_wall = now()
    anchor_mono = monotonic()
    # Offset from the monotonic anchor to slot 0. Deadlines are absolute points
    # on the monotonic clock, so a wall-clock step (NTP) cannot compress or
    # stretch the cadence; the wall clock is used only for the close test.
    offset0 = (grid.start - anchor_wall).total_seconds()

    def deadline(index: int) -> float:
        return anchor_mono + offset0 + index * grid.cadence_seconds

    # Starting late is normal (the timer fires at 09:25, the process takes a
    # moment): begin at the slot whose minute we are in, never before slot 0,
    # and never by back-filling the slots that elapsed before the process ran.
    index = max(grid.slot_index_at(anchor_wall), 0)
    emitted = 0

    while grid.contains(index):
        delay = deadline(index) - monotonic()
        if delay > 0:
            sleep(delay)
        if now() >= grid.end:
            # The close test runs BEFORE the cycle, never after it.
            return
        yield grid.stamp(index)
        emitted += 1
        if max_cycles and emitted >= max_cycles:
            return
        following = index + 1
        if deadline(following) - monotonic() < 0:
            # Overran. Jump to the first slot still in the future; the skipped
            # slots are simply absent from the partition.
            elapsed = monotonic() - anchor_mono
            catch_up = max(
                following,
                math.ceil((elapsed - offset0) / grid.cadence_seconds),
            )
            if on_slots_missed is not None:
                on_slots_missed(following, catch_up)
            following = catch_up
        index = following


def sample_quotes_cycle(
    client: Any,
    universe: tuple[str, ...],
    *,
    feeds: tuple[str, ...] = ("iex", "sip"),
    slot: SlotStamp | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """One paired sampling cycle: for each feed, a single multi-symbol
    latest-quote request. Returns feed -> JSONL-ready records sharing one
    ``cycle_ts`` so SIP/IEX pairs align.

    ``slot`` stamps every record of the cycle with the grid slot it was
    scheduled for (``slot_index`` + ``scheduled_slot_ts``), so completeness is
    reproducible against the frozen grid instead of being inferred from
    wall-clock timestamps. It is additive: ``cycle_ts`` remains the shared
    cycle identity, and records written before the stamp existed still parse.
    """
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockLatestQuoteRequest

    cycle_ts = datetime.now(UTC).isoformat()
    stamp: dict[str, Any] = {"cycle_ts": cycle_ts}
    if slot is not None:
        stamp.update(slot.as_record_fields())
    out: dict[str, list[dict[str, Any]]] = {}
    for feed in feeds:
        # Per-feed error isolation: a transient failure on one feed must not
        # lose the other feed's observation for this cycle. The error record
        # keeps the cycle's slot in the partition auditable (frozen §8 retry
        # policy: continue on transient failure; the CLI aborts only on
        # sustained failure).
        try:
            quotes = client.get_stock_latest_quote(
                StockLatestQuoteRequest(symbol_or_symbols=list(universe), feed=DataFeed(feed))
            )
        except Exception as exc:  # noqa: BLE001 - recorded, never silently dropped
            out[feed] = [{**stamp, "feed_error": f"{type(exc).__name__}: {exc}"}]
            continue
        records: list[dict[str, Any]] = []
        for symbol in universe:
            q = quotes.get(symbol)
            if q is None:
                records.append({**stamp, "symbol": symbol, "missing": True})
                continue
            records.append(
                {
                    **stamp,
                    "symbol": symbol,
                    "quote_ts": q.timestamp.isoformat(),
                    "bid": float(q.bid_price),
                    "ask": float(q.ask_price),
                    "bid_size": float(q.bid_size),
                    "ask_size": float(q.ask_size),
                    "bid_exchange": getattr(q, "bid_exchange", None),
                    "ask_exchange": getattr(q, "ask_exchange", None),
                    "conditions": getattr(q, "conditions", None),
                }
            )
        out[feed] = records
    return out


def fetch_session_bars(client: Any, universe: tuple[str, ...], session: date, feed: str) -> Any:
    """Phase-A session 1-minute bars (04:00–16:00 ET: premarket + RTH, no
    postmarket) for one explicit feed. Returns a tidy DataFrame ready for
    ``write_parquet``."""
    import pandas as pd
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    start = datetime.combine(session, time(4, 0), tzinfo=ET)
    end = datetime.combine(session, time(16, 0), tzinfo=ET)
    data = client.get_stock_bars(
        StockBarsRequest(
            symbol_or_symbols=list(universe),
            timeframe=TimeFrame(1, TimeFrameUnit.Minute),
            start=start,
            end=end,
            feed=DataFeed(feed),
        )
    ).data
    rows: list[dict[str, Any]] = []
    for symbol, bars in data.items():
        for b in bars:
            rows.append(
                {
                    "symbol": symbol,
                    "ts": b.timestamp.isoformat(),
                    "open": float(b.open),
                    "high": float(b.high),
                    "low": float(b.low),
                    "close": float(b.close),
                    "volume": float(b.volume),
                    "trade_count": float(b.trade_count) if b.trade_count is not None else None,
                    "vwap": float(b.vwap) if b.vwap is not None else None,
                }
            )
    return pd.DataFrame(rows)
