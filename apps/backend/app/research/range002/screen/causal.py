"""Look-ahead (causality) check by adversarial future replacement.

For each cut minute ``t`` the session is re-run with the future (every bar STARTING AFTER ``t``)
perturbed in six ways: prices far above, prices far below, volume zeroed, the future bars removed
with no availability evidence, removed and declared DATA_GAP, removed and declared halted.
Whatever the simulation reports as already decided at ``t`` -- the opening-range levels once
``or_end <= t``, an entry at or before ``t``, an exit at or before ``t`` -- must be identical to
the unmodified run. A decision that moves when only the future changed used future information.

Strength is bounded by the cuts the caller supplies: pass every bar-start minute of the session to test every
decision point. The inputs before ``or_end`` are not varied.

A harness that passes a causal function proves little unless it also fails a look-ahead one; the
tests drive both. ``simulate_fn`` lets a test substitute a deliberately look-ahead simulation.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import time
from typing import Any

from app.research.range002.governance.results_guard import requires_capability
from app.research.range002.screen import simulate as _sim
from app.research.range002.screen.types import Bar, Outcome, ScreenParams, SessionBars, Trade


def _is_end_of_data_valuation(t: Trade, session: SessionBars, params: ScreenParams) -> bool:
    """True only for the kernel's fallback valuation when the DATA genuinely ended.

    Verified against the session itself, not against the trade's own labels: the session must
    hold no bar at or after the EOD time, and the valuation must sit on the last bar. A real
    pre-cut decision (stop, target, EOD fill) can never satisfy this, so it is always compared.
    """
    if not (t.exit_unexecutable and t.exit_reason == "EOD_LASTBAR_FALLBACK"):
        return False
    if not session.bars or t.exit_time != session.bars[-1].start:
        return False
    if t.exit_price != min(session.bars[-1].close, t.or_low):  # the kernel's fallback valuation
        return False
    eod = _sim._eod_time(params, session)
    return not any(b.start >= eod for b in session.bars)


def _visible(
    out: Outcome, params: ScreenParams, cut: time, session: SessionBars
) -> tuple[Any, ...]:
    or_known = cut >= params.or_end
    levels = (out.or_high, out.or_low) if or_known else None
    entry = out.entry_time if (out.entry_time is not None and out.entry_time <= cut) else None
    exits = tuple(
        sorted(
            (t.candidate_id, t.exit_time, t.exit_price, t.exit_reason)
            for t in out.trades
            # only a VERIFIED end-of-data valuation is excluded (see _is_end_of_data_valuation)
            if t.exit_time <= cut and not _is_end_of_data_valuation(t, session, params)
        )
    )
    entry_px = tuple(
        sorted((t.candidate_id, t.entry_price) for t in out.trades if entry is not None)
    )
    return (levels, entry, entry_px, exits)


_VARIANTS = ("price_up", "price_down", "volume_zero", "drop", "drop_gap", "drop_halt")


def _replace_future(session: SessionBars, cut: time, variant: str) -> SessionBars:
    day_hi = max(b.high for b in session.bars)
    kept = [b for b in session.bars if b.start <= cut]
    future = [b for b in session.bars if b.start > cut]
    if variant in ("price_up", "price_down"):
        px = day_hi * (10.0 if variant == "price_up" else 0.01)
        moved = [Bar(b.start, px, px, px, px, b.volume) for b in future]
        return replace(session, bars=tuple(kept + moved))
    if variant == "volume_zero":
        zeroed = [Bar(b.start, b.open, b.high, b.low, b.close, 0) for b in future]
        return replace(session, bars=tuple(kept + zeroed))
    starts = frozenset(b.start for b in future)
    if variant == "drop":
        return replace(session, bars=tuple(kept))
    if variant == "drop_gap":
        return replace(session, bars=tuple(kept), gap_minutes=session.gap_minutes | starts)
    if variant == "drop_halt":
        return replace(session, bars=tuple(kept), halt_minutes=session.halt_minutes | starts)
    raise ValueError(f"unknown perturbation {variant!r}")


@requires_capability
def check_causal(
    capability: object,
    params: ScreenParams,
    session: SessionBars,
    tick: float,
    equity: float,
    cuts: Sequence[time],
    simulate_fn: Callable[[ScreenParams, SessionBars, float, float], Outcome] | None = None,
) -> list[str]:
    """Return violations (empty list = no look-ahead detected at the given cuts)."""
    fn = simulate_fn or _sim._simulate
    base = fn(params, session, tick, equity)
    problems: list[str] = []
    for cut in cuts:
        want = _visible(base, params, cut, session)
        for variant in _VARIANTS:
            alt_session = _replace_future(session, cut, variant)
            alt = fn(params, alt_session, tick, equity)
            got = _visible(alt, params, cut, alt_session)
            if got != want:
                problems.append(
                    f"{session.symbol} {session.day}: decision visible at {cut} changed when only "
                    f"the future after {cut} was perturbed ({variant})"
                )
    return problems
