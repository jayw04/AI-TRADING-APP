"""Data-only types for the RANGE-002 preliminary screen kernel (BUILD scope: synthetic-tested).

No callables live here: dataclasses are plain records, so the Level-1 import lint has nothing to
gate. Times are wall-clock Eastern minutes; ``Bar.start`` is the START of the one-minute bar
(the loader normalises vendor timestamps and records the convention on the session).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

FAMILY_TIME = "time"
FAMILY_FIXED_R = "fixed_r"
FAMILY_TRAILING = "trailing"
FAMILY_SCALE_OUT = "scale_out"
SUPPORTED_FAMILIES = ("time", "fixed_r", "trailing", "scale_out")

#: the only intraday bar basis the loader accepts today (fetched with adjustment "raw")
SUPPORTED_INTRADAY_BASIS = "raw"

HALT_POLICY_UNEXECUTABLE = "UNEXECUTABLE_DURING_UNAVAILABLE"
#: The frozen valuation rule for an exit that has no executable bar through the close: the
#: position is valued at the WORSE of the last close and the initial stop, flagged
#: ``exit_unexecutable`` and reported separately; it is never an ordinary fill.
UNAVAILABLE_EXIT_VALUATION_RULE = "WORSE_OF_LAST_CLOSE_AND_INITIAL_STOP"

STATE_OR_INCOMPLETE = "OR_INCOMPLETE"
STATE_OR_TOO_NARROW = "OR_TOO_NARROW"
STATE_NO_BREAKOUT = "NO_BREAKOUT"
STATE_SKIPPED_CROSSED = "SKIPPED_CROSSED_BEFORE_ARM"
STATE_INVALID_RISK = "INVALID_RISK"
#: SKIP baseline: a breakout bar that starts at or after the session's EOD flatten cutoff is not
#: entered (an entry there could only be flattened at that same bar's open, an impossible order).
STATE_ENTRY_AT_OR_AFTER_EOD = "ENTRY_AT_OR_AFTER_EOD_CUTOFF"
STATE_ENTERED = "ENTERED"
TERMINAL_STATES = (
    "OR_INCOMPLETE",
    "OR_TOO_NARROW",
    "NO_BREAKOUT",
    "SKIPPED_CROSSED_BEFORE_ARM",
    "INVALID_RISK",
    "ENTRY_AT_OR_AFTER_EOD_CUTOFF",
    "ENTERED",
)


@dataclass(frozen=True)
class Bar:
    start: time
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class SessionBars:
    """One symbol-day. ``bars`` sorted by ``start``. Minutes absent from ``bars`` and not in
    ``gap_minutes`` are NO_TRADE_MINUTE (legitimately no print); ``gap_minutes`` are DATA_GAP."""

    symbol: str
    day: date
    feed: str
    ts_convention: str
    session_close: time
    bars: tuple[Bar, ...]
    gap_minutes: frozenset[time]
    halt_minutes: frozenset[time]
    #: stable issuer identity (never the vendor ticker string): the scheduler's tie-break key
    permaticker: str


@dataclass(frozen=True)
class ExitSpec:
    id: str
    family: str
    r_multiple: float | None
    trail_r: float | None = None
    scale_remainder: str | None = None


@dataclass(frozen=True)
class ScreenParams:
    """Every spec value the screen kernel reads, typed and non-null. Built only by
    ``params.extract_params``; nothing here has a default (R9)."""

    spec_sha256: str
    feed: str
    or_start: time
    or_end: time
    entry_start: time
    entry_end: time
    tick_offset: int
    max_entries_per_symbol_day: int
    min_or_width_ticks: float
    or_max_gap_minutes: int
    eod_flat: time
    halfday_offset_min: float
    same_bar_policy: str
    base_bps_per_side: float
    stress_bps_per_side: float
    accounting_mode: str
    per_trade_pct: float
    #: explicit unit of ``per_trade_pct``: "percent" or "fraction" (hazard D)
    per_trade_pct_unit: str
    #: the derived fraction of equity risked per trade, in the open interval (0, 1)
    per_trade_fraction: float
    #: the spec's data.intraday_price_basis; every stored bar must carry exactly this tag (hazard B)
    intraday_price_basis: str
    bar_timestamp_convention: str
    crossed_before_arm_policy: str
    halt_policy: str
    candidates: tuple[ExitSpec, ...]
    #: execution settings present in the spec that the bar-level kernel does NOT simulate; carried
    #: so every report states them as unmodelled instead of implying execution realism.
    unmodelled_execution: tuple[str, ...]


@dataclass(frozen=True)
class Trade:
    candidate_id: str
    symbol: str
    permaticker: str
    day: date
    or_high: float
    or_low: float
    trigger: float
    entry_time: time
    entry_price: float
    r_pre: float
    r_fill: float
    qty: int
    exit_time: time
    exit_price: float
    exit_reason: str
    gross_r: float
    net_r_base: float
    net_r_stress: float
    scaled_out: bool
    exit_unexecutable: bool
    exit_after_unavailable: bool
    gapped_entry: bool
    path_ambiguous: bool


@dataclass(frozen=True)
class Outcome:
    """Result of one symbol-day: terminal state, plus the per-candidate trades if entered."""

    symbol: str
    day: date
    state: str
    or_high: float | None
    or_low: float | None
    entry_time: time | None
    trades: tuple[Trade, ...]


@dataclass(frozen=True)
class Funnel:
    eligible: int
    states: dict[str, int]
    exits: dict[str, dict[str, int]]


@dataclass(frozen=True)
class ScreenRun:
    citable: bool
    spec_sha256: str
    trades: dict[str, tuple[Trade, ...]]
    funnel: Funnel
