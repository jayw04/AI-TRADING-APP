"""EXPECTED behaviour for the RANGE-002 synthetic engineering benchmark (NON-INFERENTIAL).

Pure data plus plain arithmetic. This module imports NOTHING from ``app`` and nothing from the
kernel: every number below is derived from the frozen rules and the fixture prices by hand
(entry/stop/target/trail/scale/cost rules), not by running the code under test.

Rules used (from the kernel's documented semantics and the synthetic spec values 5/15 bps,
tick 0.01, tick_offset 1, OR 09:30-09:59, entry window 10:00-14:59, EOD flat 15:55, half-day
offset 4 min):

* trigger = OR high + 1 tick; entry fill = max(trigger, bar open); R_fill = entry - OR low;
  r_pre = trigger - OR low; stop = OR low.
* fixed-R target = entry + k*R_fill, filled AT the target; stop wins inside one bar.
* trailing: armed once a bar's high reaches entry + 1R; stop = max(stop, entry,
  best_close - trail*R_fill) applied from the NEXT bar; stop fills at the stop (open if gapped).
* scale-out: 50% at entry + 1R, the remainder at EOD or on the trailing rule (after +1R).
* time exit: open of the first bar at/after the flat time.
* cost (all-in) in R = bps/1e4 * (entry + sum(frac*exit px)) / R_fill, per candidate leg set.
* unavailable-exit valuation: worse of last close and initial stop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

CANDS = ("TIME", "R2", "R3", "TRAIL1", "TRAIL15", "SCALE_EOD", "SCALE_TRAIL")
BASE_BPS = 5.0
STRESS_BPS = 15.0
EQUITY_MAIN = 100_000.0
EQUITY_S6 = 20_000.0
PCT_MAIN = 0.1  # percent per trade (the fixtures' synthetic spec value)
PCT_S6 = 0.25  # percent per trade, overridden in the S6 synthetic payload only

Legs = tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class XT:
    """One expected trade for one candidate."""

    entry_time: str
    entry: float
    r_fill: float
    r_pre: float
    legs: Legs
    exit_time: str
    reason: str
    qty: int
    gapped: bool = False
    unexec: bool = False
    after_unavail: bool = False
    ambiguous: bool = False

    @property
    def gross(self) -> float:
        return sum(f * (px - self.entry) for f, px in self.legs) / self.r_fill

    def cost(self, bps: float) -> float:
        return bps / 10_000.0 * (self.entry + sum(f * px for f, px in self.legs)) / self.r_fill

    @property
    def net_base(self) -> float:
        return self.gross - self.cost(BASE_BPS)

    @property
    def net_stress(self) -> float:
        return self.gross - self.cost(STRESS_BPS)

    @property
    def scaled(self) -> bool:
        return len(self.legs) > 1


@dataclass(frozen=True)
class XS:
    """One expected symbol-day."""

    scenario: str
    symbol: str
    day: date
    state: str
    note: str
    trades: dict[str, XT] = field(default_factory=dict)


def _one(px: float) -> Legs:
    return ((1.0, px),)


def _split(scale_px: float, rest_px: float) -> Legs:
    return ((0.5, scale_px), (0.5, rest_px))


def _all(xt: XT) -> dict[str, XT]:
    return dict.fromkeys(CANDS, xt)


def _std(entry_time: str, entry: float, r: float, qty: int, legs: Legs, t: str, why: str) -> XT:
    return XT(entry_time, entry, r, r, legs, t, why, qty)


E, R, Q = 10.11, 0.11, 909  # standard breakout: OR 10.00-10.10, trigger 10.11, qty int(100/0.11)

# ---- S1 trending breakout --------------------------------------------------------------------
_S1A = {
    "TIME": _std("10:05", E, R, Q, _one(10.32), "15:55", "EOD"),
    "R2": _std("10:05", E, R, Q, _one(10.33), "12:00", "TARGET"),
    "R3": _std("10:05", E, R, Q, _one(10.44), "13:00", "TARGET"),
    "TRAIL1": _std("10:05", E, R, Q, _one(10.39), "14:30", "TRAIL_STOP"),
    "TRAIL15": _std("10:05", E, R, Q, _one(10.335), "14:30", "TRAIL_STOP"),
    "SCALE_EOD": _std("10:05", E, R, Q, _split(10.22, 10.32), "15:55", "EOD"),
    "SCALE_TRAIL": _std("10:05", E, R, Q, _split(10.22, 10.39), "14:30", "TRAIL_STOP"),
}
_S1C = {
    "TIME": _std("10:05", E, R, Q, _one(10.48), "15:55", "EOD"),
    "R2": _std("10:05", E, R, Q, _one(10.33), "10:06", "TARGET"),
    "R3": _std("10:05", E, R, Q, _one(10.44), "10:06", "TARGET"),
    "TRAIL1": _std("10:05", E, R, Q, _one(10.48), "15:55", "EOD"),
    "TRAIL15": _std("10:05", E, R, Q, _one(10.48), "15:55", "EOD"),
    "SCALE_EOD": _std("10:05", E, R, Q, _split(10.22, 10.48), "15:55", "EOD"),
    "SCALE_TRAIL": _std("10:05", E, R, Q, _split(10.22, 10.48), "15:55", "EOD"),
}
# ---- S2 false breakout / reversal ------------------------------------------------------------
_S2A = _all(_std("10:05", E, R, Q, _one(10.00), "10:06", "STOP"))
_S2B = {
    "TIME": _std("10:05", E, R, Q, _one(10.00), "12:00", "STOP"),
    "R2": _std("10:05", E, R, Q, _one(10.00), "12:00", "STOP"),
    "R3": _std("10:05", E, R, Q, _one(10.00), "12:00", "STOP"),
    "TRAIL1": _std("10:05", E, R, Q, _one(10.13), "12:00", "TRAIL_STOP"),
    "TRAIL15": _std("10:05", E, R, Q, _one(10.11), "12:00", "TRAIL_STOP"),
    "SCALE_EOD": _std("10:05", E, R, Q, _split(10.22, 10.00), "12:00", "STOP"),
    "SCALE_TRAIL": _std("10:05", E, R, Q, _split(10.22, 10.13), "12:00", "TRAIL_STOP"),
}
# ---- S3 gap entry, gap through stop, crossed-before-arm ---------------------------------------
_S3A = _all(
    XT("10:30", 10.20, 0.20, 0.11, _one(10.28), "15:55", "EOD", 500, gapped=True),
)
_S3B = _all(_std("10:05", E, R, Q, _one(9.80), "11:00", "STOP_GAP"))
# ---- S4 missing data / unavailable exits -------------------------------------------------------
_S4J = {
    **dict.fromkeys(
        ("TIME", "R2", "R3", "TRAIL1", "TRAIL15"),
        _std("10:05", E, R, Q, _one(10.30), "15:55", "EOD"),
    ),
    **dict.fromkeys(
        ("SCALE_EOD", "SCALE_TRAIL"),
        _std("10:05", E, R, Q, _split(10.22, 10.30), "15:55", "EOD"),
    ),
}
_UNEX = {"unexec": True, "after_unavail": True}
_S4K = {
    **dict.fromkeys(
        ("TIME", "R2", "R3", "TRAIL1", "TRAIL15"),
        XT("10:05", E, R, R, _one(10.00), "14:00", "EOD_LASTBAR_FALLBACK", Q, **_UNEX),
    ),
    **dict.fromkeys(
        ("SCALE_EOD", "SCALE_TRAIL"),
        XT("10:05", E, R, R, _split(10.22, 10.00), "14:00", "EOD_LASTBAR_FALLBACK", Q, **_UNEX),
    ),
}
_S4M = _all(
    XT("10:05", E, R, R, _one(9.70), "11:30", "STOP_GAP", Q, after_unavail=True),
)
# ---- S5 half day (close 13:00, flat 12:56) -----------------------------------------------------
_S5N = {
    **dict.fromkeys(
        ("TIME", "R2", "R3", "TRAIL1", "TRAIL15"),
        _std("10:05", E, R, Q, _one(10.30), "12:56", "EOD"),
    ),
    **dict.fromkeys(
        ("SCALE_EOD", "SCALE_TRAIL"),
        _std("10:05", E, R, Q, _split(10.22, 10.30), "12:56", "EOD"),
    ),
}
_S5O = _all(_std("12:55", E, R, Q, _one(10.18), "12:56", "EOD"))
# ---- S6 competing signals, constrained capital (equity 20,000; 0.25% => $50 risk) -----------------
R6, E6, Q6 = 0.16, 10.16, 312
_S6W = _all(_std("10:05", E6, R6, Q6, _one(10.20), "15:55", "EOD"))
_S6W10 = _all(_std("10:10", E6, R6, Q6, _one(10.20), "15:55", "EOD"))
_S6W20 = _all(_std("10:20", E6, R6, Q6, _one(10.20), "15:55", "EOD"))
_S6L15 = _all(_std("10:05", E6, R6, Q6, _one(10.00), "10:15", "STOP"))
_S6L20 = _all(_std("10:05", E6, R6, Q6, _one(10.00), "10:20", "STOP"))

D = date
EXPECTED: dict[str, list[XS]] = {
    "S1": [
        XS("S1", "AAA", D(2026, 3, 2), "ENTERED", "long breakout, staged continuation", _S1A),
        XS("S1", "BBB", D(2026, 3, 3), "NO_BREAKOUT", "downside break only; kernel is long-only"),
        XS("S1", "CCC", D(2026, 3, 4), "ENTERED", "long breakout, 3R in one bar then hold", _S1C),
    ],
    "S2": [
        XS("S2", "DDD", D(2026, 3, 5), "ENTERED", "break then reverse through stop", _S2A),
        XS("S2", "EEE", D(2026, 3, 6), "ENTERED", "break, +1R, then reverse", _S2B),
    ],
    "S3": [
        XS("S3", "FFF", D(2026, 3, 9), "ENTERED", "gap entry at 10:30 open 10.20", _S3A),
        XS("S3", "GGG", D(2026, 3, 10), "ENTERED", "gap through the stop at 11:00", _S3B),
        XS("S3", "HHH", D(2026, 3, 11), "SKIPPED_CROSSED_BEFORE_ARM", "gap open on first bar"),
    ],
    "S4": [
        XS("S4", "III", D(2026, 3, 12), "OR_INCOMPLETE", "1 DATA_GAP minute in OR"),
        XS("S4", "JJJ", D(2026, 3, 13), "ENTERED", "DATA_GAP 10:20 outside OR", _S4J),
        XS("S4", "KKK", D(2026, 3, 16), "ENTERED", "halted 14:01 to close: unexecutable", _S4K),
        XS("S4", "LLL", D(2026, 3, 17), "OR_INCOMPLETE", "2 DATA_GAP minutes in OR"),
        XS("S4", "MMM", D(2026, 3, 18), "ENTERED", "halt 11:00-11:29, reopen below stop", _S4M),
    ],
    "S5": [
        XS("S5", "NNN", D(2026, 3, 19), "ENTERED", "half day, break 10:05, flat 12:56", _S5N),
        XS("S5", "OOO", D(2026, 3, 20), "ENTERED", "half day, break 12:55, flat 12:56", _S5O),
        XS(
            "S5",
            "QQQ",
            D(2026, 3, 23),
            "ENTRY_AT_OR_AFTER_EOD_CUTOFF",
            "half day, break 12:56 = cutoff",
        ),
    ],
    "S6": [
        XS("S6", "SYM1", D(2026, 3, 30), "ENTERED", "perm PM-E, 10:05 winner", _S6W),
        XS("S6", "SYM2", D(2026, 3, 30), "ENTERED", "perm PM-D, 10:05 winner", _S6W),
        XS("S6", "SYM3", D(2026, 3, 30), "ENTERED", "perm PM-C, 10:05 winner", _S6W),
        XS("S6", "SYM4", D(2026, 3, 30), "ENTERED", "perm PM-B, 10:05 winner", _S6W),
        XS("S6", "SYM5", D(2026, 3, 30), "ENTERED", "perm PM-A, 10:05 winner", _S6W),
        XS("S6", "LOS1", D(2026, 3, 31), "ENTERED", "perm PM-L, 10:05 loser exits 10:15", _S6L15),
        XS("S6", "WIN1", D(2026, 3, 31), "ENTERED", "perm PM-A, 10:10 winner", _S6W10),
        XS("S6", "WIN2", D(2026, 3, 31), "ENTERED", "perm PM-B, 10:20 winner", _S6W20),
        XS("S6", "LOS2", D(2026, 4, 1), "ENTERED", "perm PM-A, 10:05 loser exits 10:20", _S6L20),
        XS("S6", "WIN3", D(2026, 4, 1), "ENTERED", "perm PM-B, 10:20 winner", _S6W20),
    ],
}

#: permaticker per S6 symbol (symbol order is the REVERSE of permaticker order on day one).
S6_PERMA = {
    "SYM1": "PM-E",
    "SYM2": "PM-D",
    "SYM3": "PM-C",
    "SYM4": "PM-B",
    "SYM5": "PM-A",
    "LOS1": "PM-L",
    "WIN1": "PM-A",
    "WIN2": "PM-B",
    "LOS2": "PM-A",
    "WIN3": "PM-B",
}

#: S6 portfolio expectations, hand-derived from the scheduler rules (limits: max_concurrent 2,
#: gross cap 0.3, per-name 0.2, daily loss 0.4 R, equity 20,000; notional 312 * 10.16 = 3169.92).
S6_DEFAULT_ACCEPTED = [("SYM5", "2026-03-30"), ("LOS1", "2026-03-31"), ("LOS2", "2026-04-01")]
S6_DEFAULT_REJECTED = {"DAILY_LOSS_LIMIT": 1, "GROSS_CAP": 6}
#: variant: gross cap relaxed to 1.0 by the harness (NOT a spec value) so concurrency binds.
S6_RELAXED_ACCEPTED = [
    ("SYM5", "2026-03-30"),
    ("SYM4", "2026-03-30"),
    ("LOS1", "2026-03-31"),
    ("WIN1", "2026-03-31"),
    ("LOS2", "2026-04-01"),
    ("WIN3", "2026-04-01"),
]
S6_RELAXED_REJECTED = {"DAILY_LOSS_LIMIT": 1, "MAX_CONCURRENT": 3}


def expected_funnel(scenario: str) -> tuple[int, dict[str, int], dict[str, dict[str, int]]]:
    """(eligible, non-zero state counts, exits per candidate) from the expected sessions."""
    sess = EXPECTED[scenario]
    states: dict[str, int] = {}
    exits: dict[str, dict[str, int]] = {c: {} for c in CANDS}
    for s in sess:
        states[s.state] = states.get(s.state, 0) + 1
        for c, xt in s.trades.items():
            exits[c][xt.reason] = exits[c].get(xt.reason, 0) + 1
    return len(sess), states, exits


def expected_trades(scenario: str, cand: str) -> list[tuple[XS, XT]]:
    return [(s, s.trades[cand]) for s in EXPECTED[scenario] if cand in s.trades]


def total_net(scenario: str, cand: str, *, stress: bool = False) -> float:
    return sum((x.net_stress if stress else x.net_base) for _, x in expected_trades(scenario, cand))


def pooled(cand: str) -> list[float]:
    """Pooled expected base net R for one candidate across S1-S6 (for the bootstrap/selection
    stage, which is run over the pooled synthetic trades)."""
    return [x.net_base for sc in EXPECTED for _, x in expected_trades(sc, cand)]
