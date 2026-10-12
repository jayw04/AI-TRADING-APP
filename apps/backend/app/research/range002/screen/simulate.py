"""Long-only opening-range breakout simulation on one-minute bars (signal level, R units).

Every public entry point requires a results capability (Level-1 import lint). Private helpers
are pure arithmetic over already-validated sessions. No price is read before ``validate`` has
accepted the session, and no value after the decision minute is used to make a decision
(checked by ``causal.check_causal``).

Interpretations the kernel makes, all listed as UNRESOLVED in the amendment (none is a P0 value):
entry is a buy-stop at ``OR high + tick_offset * tick`` (fill ``max(trigger, bar open)``); the
stop sells at ``OR low`` (fill ``min(stop, bar open)`` on a gap); a fixed-R target is a limit at
``entry + k * R_fill`` filled AT the target (never better); when stop and target are both inside
one bar, or when the entry bar itself reaches the stop, the stop wins (worst case); the time exit
sells at the open of the first bar at or after the EOD time, falling back to the last close;
costs are all-in per-side basis points on each leg's notional.

Baseline (SKIP): a breakout bar that starts at or after the session's EOD flatten cutoff is not
entered (terminal state ENTRY_AT_OR_AFTER_EOD_CUTOFF); existing positions still exit at the first
bar at/after the cutoff. Changing this is a baseline change that needs a re-frozen spec hash.

Access limit, stated plainly: ``_simulate`` and the other private helpers are importable. Python
privacy and the import lint are developer safeguards, not an access boundary. The supported,
result-producing entry points require a LIVE capability (checked again after run closure); code
that bypasses them in-process is outside the protection of Level 1.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta

from app.research.range002.governance.results_guard import requires_capability
from app.research.range002.screen.errors import (
    DataDefectError,
    FunnelMismatchError,
    SpecBindingError,
)
from app.research.range002.screen.types import (
    FAMILY_FIXED_R,
    FAMILY_SCALE_OUT,
    FAMILY_TRAILING,
    STATE_ENTERED,
    STATE_ENTRY_AT_OR_AFTER_EOD,
    STATE_INVALID_RISK,
    STATE_NO_BREAKOUT,
    STATE_OR_INCOMPLETE,
    STATE_OR_TOO_NARROW,
    STATE_SKIPPED_CROSSED,
    TERMINAL_STATES,
    Bar,
    ExitSpec,
    Funnel,
    Outcome,
    ScreenParams,
    ScreenRun,
    SessionBars,
    Trade,
)

_FULL_DAY_CLOSE = time(16, 0)
_FULL_DAY_FLAT_MINUTES = 5.0  # 16:00 - 15:55; the spec fixes eod_flat at 15:55:00


def _minutes_before(close: time, minutes: float) -> time:
    base = datetime.combine(date(2000, 1, 3), close) - timedelta(minutes=minutes)
    return base.time().replace(microsecond=0)


def _eod_time(params: ScreenParams, session: SessionBars) -> time:
    if session.session_close >= _FULL_DAY_CLOSE:
        return params.eod_flat
    return _minutes_before(session.session_close, params.halfday_offset_min)


def _validate(params: ScreenParams, session: SessionBars) -> None:
    if not session.permaticker.strip():
        raise DataDefectError(
            f"{session.symbol} {session.day}: empty permaticker (issuer identity)"
        )
    if session.feed != params.feed:
        raise DataDefectError(f"{session.symbol} {session.day}: feed {session.feed!r} != sip")
    if session.ts_convention != params.bar_timestamp_convention:
        raise DataDefectError(
            f"{session.symbol} {session.day}: timestamp convention {session.ts_convention!r} "
            f"!= spec {params.bar_timestamp_convention!r}"
        )
    prev: time | None = None
    for bar in session.bars:
        if prev is not None and bar.start <= prev:
            raise DataDefectError(f"{session.symbol} {session.day}: bars unsorted or duplicate")
        prev = bar.start
        if bar.start < params.or_start or bar.start >= session.session_close:
            raise DataDefectError(
                f"{session.symbol} {session.day}: bar {bar.start} outside session"
            )
        if bar.start in session.gap_minutes or bar.start in session.halt_minutes:
            raise DataDefectError(
                f"{session.symbol} {session.day}: a bar exists at {bar.start}, a minute declared "
                "DATA_GAP/halt (contradictory availability evidence)"
            )
        vals = (bar.open, bar.high, bar.low, bar.close)
        if not all(math.isfinite(v) and v > 0 for v in vals):
            raise DataDefectError(f"{session.symbol} {session.day}: non-positive/NaN price")
        if not (bar.low <= min(bar.open, bar.close) and bar.high >= max(bar.open, bar.close)):
            raise DataDefectError(
                f"{session.symbol} {session.day}: inconsistent OHLC at {bar.start}"
            )


def _or_levels(params: ScreenParams, session: SessionBars) -> tuple[float, float] | None:
    in_or = [b for b in session.bars if params.or_start <= b.start <= params.or_end]
    gaps = [m for m in session.gap_minutes if params.or_start <= m <= params.or_end]
    if not in_or or len(gaps) > params.or_max_gap_minutes:
        return None
    return max(b.high for b in in_or), min(b.low for b in in_or)


def _cost_r(
    bps: float, entry: float, legs: tuple[tuple[float, float], ...], r_fill: float
) -> float:
    """All-in per-side cost in R: bps on the entry notional plus on every exit leg's notional."""
    exit_notional = sum(frac * px for frac, px in legs)
    return (bps / 10_000.0) * (entry + exit_notional) / r_fill


def _exit_path(
    params: ScreenParams,
    session: SessionBars,
    spec: ExitSpec,
    entry_idx: int,
    entry_px: float,
    stop0: float,
    r_fill: float,
) -> tuple[time, str, bool, tuple[tuple[float, float], ...], bool, bool]:
    """Walk bars from the entry bar. Returns (final time, reason, path_ambiguous, legs,
    unexecutable, after_unavailable) where ``legs`` are ``(fraction, price)`` fills summing to 1.

    Halt policy ``UNEXECUTABLE_DURING_UNAVAILABLE``: no exit is assumed fillable inside a
    DATA_GAP or known/suspected-halt interval. An exit decided on the first bar after such an
    interval fills on that bar (a gap through the stop fills at its open) and is flagged
    ``after_unavailable``. If the session ends with no bar at or after the EOD time, the exit is
    ``unexecutable``: it is valued at the worse of the last close and the initial stop and is
    reported separately, never silently as an ordinary fill.

    A stop that moves (breakeven / trail) is updated AFTER a bar completes and applies from the
    next bar. Within one bar the original path is unknown, so the stop wins over any target or
    partial (worst case)."""
    fam = spec.family
    target: float | None = None
    if fam == FAMILY_FIXED_R and spec.r_multiple is not None:
        target = entry_px + spec.r_multiple * r_fill
    scale_px = entry_px + r_fill if fam == FAMILY_SCALE_OUT else None
    trails = fam == FAMILY_TRAILING or (fam == FAMILY_SCALE_OUT and spec.scale_remainder == "trail")
    armed = False  # +1R reached: stop at breakeven, then trail on completed-bar closes
    best_close = entry_px
    stop = stop0
    frac_left = 1.0
    legs: list[tuple[float, float]] = []
    eod = _eod_time(params, session)
    unavailable = session.gap_minutes | session.halt_minutes
    last: Bar = session.bars[entry_idx]
    for i in range(entry_idx, len(session.bars)):
        bar = session.bars[i]
        prev_start = session.bars[i - 1].start if i > entry_idx else None
        after = prev_start is not None and any(prev_start < m < bar.start for m in unavailable)
        if bar.start >= eod:
            legs.append((frac_left, bar.open))
            late = bar.start > eod and any(eod <= m < bar.start for m in unavailable)
            return bar.start, "EOD", False, tuple(legs), False, after or late
        last = bar
        gap = i > entry_idx and bar.open <= stop
        if gap or bar.low <= stop:
            px = bar.open if gap else stop
            reason = "STOP_GAP" if gap else ("TRAIL_STOP" if stop > stop0 else "STOP")
            hit_t = (target is not None and bar.high >= target) or (
                scale_px is not None and frac_left == 1.0 and bar.high >= scale_px
            )
            legs.append((frac_left, px))
            return bar.start, reason, bool(hit_t) and not gap, tuple(legs), False, after
        if target is not None and bar.high >= target:
            legs.append((frac_left, target))
            return bar.start, "TARGET", False, tuple(legs), False, after
        if scale_px is not None and frac_left == 1.0 and bar.high >= scale_px:
            legs.append((0.5, scale_px))
            frac_left = 0.5
        if trails:
            if not armed and bar.high >= entry_px + r_fill:
                armed = True
            if armed:
                best_close = max(best_close, bar.close)
                stop = max(stop, entry_px, best_close - (spec.trail_r or 0.0) * r_fill)
    legs.append((frac_left, min(last.close, stop0)))
    return last.start, "EOD_LASTBAR_FALLBACK", False, tuple(legs), True, True


def _simulate(params: ScreenParams, session: SessionBars, tick: float, equity: float) -> Outcome:
    levels = _or_levels(params, session)
    if levels is None:
        return Outcome(session.symbol, session.day, STATE_OR_INCOMPLETE, None, None, None, ())
    or_high, or_low = levels
    if (or_high - or_low) < params.min_or_width_ticks * tick:
        return Outcome(session.symbol, session.day, STATE_OR_TOO_NARROW, or_high, or_low, None, ())
    trigger = or_high + params.tick_offset * tick
    eod = _eod_time(params, session)
    first_armed = True
    for idx, bar in enumerate(session.bars):
        if bar.start < params.entry_start or bar.start > params.entry_end:
            continue
        is_first, first_armed = first_armed, False
        if bar.high < trigger:
            continue
        if bar.start >= eod:
            # SKIP baseline: no new entry at/after the EOD cutoff. Entering in this bar and
            # flattening at the same bar's open would order the exit before the entry.
            return Outcome(
                session.symbol,
                session.day,
                STATE_ENTRY_AT_OR_AFTER_EOD,
                or_high,
                or_low,
                None,
                (),
            )
        gapped = bar.open >= trigger
        if gapped and is_first and params.crossed_before_arm_policy == "SKIP":
            return Outcome(
                session.symbol, session.day, STATE_SKIPPED_CROSSED, or_high, or_low, None, ()
            )
        entry_px = max(trigger, bar.open)
        r_fill = entry_px - or_low
        if r_fill <= 0:
            return Outcome(
                session.symbol, session.day, STATE_INVALID_RISK, or_high, or_low, None, ()
            )
        r_pre = trigger - or_low
        qty = int(equity * params.per_trade_fraction // r_fill)
        trades: list[Trade] = []
        for spec in params.candidates:
            xt, reason, ambiguous, legs, unexec, after_unavail = _exit_path(
                params, session, spec, idx, entry_px, or_low, r_fill
            )
            xp = legs[-1][1]
            gross = sum(frac * (px - entry_px) for frac, px in legs) / r_fill
            trades.append(
                Trade(
                    candidate_id=spec.id,
                    symbol=session.symbol,
                    permaticker=session.permaticker,
                    day=session.day,
                    or_high=or_high,
                    or_low=or_low,
                    trigger=trigger,
                    entry_time=bar.start,
                    entry_price=entry_px,
                    r_pre=r_pre,
                    r_fill=r_fill,
                    qty=qty,
                    exit_time=xt,
                    exit_price=xp,
                    exit_reason=reason,
                    gross_r=gross,
                    net_r_base=gross - _cost_r(params.base_bps_per_side, entry_px, legs, r_fill),
                    net_r_stress=gross
                    - _cost_r(params.stress_bps_per_side, entry_px, legs, r_fill),
                    scaled_out=len(legs) > 1,
                    exit_unexecutable=unexec,
                    exit_after_unavailable=after_unavail,
                    gapped_entry=gapped,
                    path_ambiguous=ambiguous,
                )
            )
        return Outcome(
            session.symbol, session.day, STATE_ENTERED, or_high, or_low, bar.start, tuple(trades)
        )
    return Outcome(session.symbol, session.day, STATE_NO_BREAKOUT, or_high, or_low, None, ())


def _bound(capability: object, params: ScreenParams) -> None:
    if getattr(capability, "spec_sha256", None) != params.spec_sha256:
        raise SpecBindingError("params were extracted for a different spec than the capability")


def _in_range(capability: object, day: date) -> bool:
    rng = getattr(capability, "date_range", None)
    return rng is not None and rng.start <= day <= rng.end


@requires_capability
def simulate_session(
    capability: object, params: ScreenParams, session: SessionBars, tick: float, equity: float
) -> Outcome:
    _bound(capability, params)
    if not _in_range(capability, session.day):
        raise DataDefectError(f"{session.symbol} {session.day}: outside the authorized date range")
    if tick <= 0 or equity <= 0:
        raise DataDefectError("tick and equity must be positive")
    _validate(params, session)
    return _simulate(params, session, tick, equity)


@requires_capability
def run_screen(
    capability: object,
    params: ScreenParams,
    sessions: Iterable[SessionBars],
    tick: float,
    equity: float,
) -> ScreenRun:
    _bound(capability, params)
    ordered = sorted(sessions, key=lambda s: (s.day, s.symbol))
    keys = [(s.day, s.symbol) for s in ordered]
    if len(set(keys)) != len(keys):
        raise DataDefectError("duplicate symbol-day in the session set")
    states = dict.fromkeys(TERMINAL_STATES, 0)
    exits: dict[str, dict[str, int]] = {c.id: {} for c in params.candidates}
    trades: dict[str, list[Trade]] = {c.id: [] for c in params.candidates}
    for session in ordered:
        if not _in_range(capability, session.day):
            raise DataDefectError(f"{session.symbol} {session.day}: outside the authorized range")
        _validate(params, session)
        out = _simulate(params, session, tick, equity)
        states[out.state] += 1
        for t in out.trades:
            trades[t.candidate_id].append(t)
            bucket = exits[t.candidate_id]
            bucket[t.exit_reason] = bucket.get(t.exit_reason, 0) + 1
    funnel = Funnel(eligible=len(ordered), states=states, exits=exits)
    _reconcile(funnel)
    return ScreenRun(
        citable=bool(getattr(capability, "citable", False)),
        spec_sha256=params.spec_sha256,
        trades={k: tuple(v) for k, v in trades.items()},
        funnel=funnel,
    )


def _reconcile(funnel: Funnel) -> None:
    if sum(funnel.states.values()) != funnel.eligible:
        raise FunnelMismatchError(
            f"terminal states sum to {sum(funnel.states.values())}, eligible {funnel.eligible}"
        )
    entered = funnel.states[STATE_ENTERED]
    for cand, reasons in funnel.exits.items():
        if sum(reasons.values()) != entered:
            raise FunnelMismatchError(f"{cand}: exits {sum(reasons.values())} != entered {entered}")


@requires_capability
def reconcile_funnel(capability: object, funnel: Funnel) -> None:
    _reconcile(funnel)
