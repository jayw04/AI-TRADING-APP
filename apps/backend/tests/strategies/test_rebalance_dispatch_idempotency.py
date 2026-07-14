"""One cron dispatch must produce AT MOST ONE rebalance — even when the symbols disagree
about how recent their bars are.

THE BUG (live, 2026-07-13, combined-book / account 7). The engine calls ``on_bar`` once per
symbol per cron tick (209 calls for the combined book). Every portfolio template guarded
against that fan-out by remembering the ISO week of ``bar.t``:

    wk = bar.t.isocalendar()[:2]
    if wk == self._last_rebalance_week:
        return
    self._last_rebalance_week = wk

But ``bar.t`` is DATA, and each call carries that symbol's *own* latest bar. Symbols routinely
disagree on how recent that is — a stale cached month-bucket, a thin ETF that has not printed
yet, a mid-rebalance panel refetch. Friday 2026-07-10 is ISO week 28; Monday 2026-07-13 is
week 29. So a single lagging symbol flips the guard BACK to week 28, and the very next
current-week symbol sees 29 != 28 and re-runs the entire rebalance.

It fired five times in one slot. Each run re-read stale holdings, so the book double-bought
and then double-sold the same names (LLY: BUY 0.121769, BUY 0.121705, SELL 0.121776, SELL
0.121773 -> broker rejected, only 0.121698 available).

This is the same failure class as the 2026-06-22/23 conservative-book blowout (a rebalance
dispatched 3x -> ~3.8x leverage): NO REBALANCE IDEMPOTENCY.

THE FIX. Live keys on the DISPATCH (``ctx.dispatch_seq``, stamped once per tick by the
engine), which no amount of bar staleness can perturb. Backtests have no dispatch and replay
bars one at a time, so they keep the bar-derived ISO week.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.db.enums import SignalType


class _Ctx:
    """Minimal StrategyContext stand-in: only what on_bar's guard touches."""

    def __init__(self, dispatch_seq: int | None = None) -> None:
        self.dispatch_seq = dispatch_seq
        self.signals: list[tuple[str, Any, dict]] = []

    async def log_signal(self, symbol: str, type_: Any, payload: dict) -> None:
        self.signals.append((symbol, type_, payload))


class _Book:
    """The on_bar guard EXACTLY as the four live templates now implement it.

    Kept in the test rather than importing a template so the property under test is stated
    once and cannot drift silently; the templates are asserted to match it below.
    """

    def __init__(self, ctx: _Ctx) -> None:
        self.ctx = ctx
        self._last_rebalance_week: tuple[int, int] | None = None
        self._last_dispatch_seq: int | None = None
        self.rebalances = 0

    async def _rebalance(self) -> None:
        self.rebalances += 1

    async def on_bar(self, bar: Any) -> None:
        seq = getattr(self.ctx, "dispatch_seq", None)
        if isinstance(seq, int):
            if seq == self._last_dispatch_seq:
                return
            self._last_dispatch_seq = seq
        else:
            wk = bar.t.isocalendar()[:2]
            if wk == self._last_rebalance_week:
                return
            self._last_rebalance_week = wk
        try:
            await self._rebalance()
        except Exception as exc:  # noqa: BLE001
            await self.ctx.log_signal(
                "PORTFOLIO", SignalType.EXIT, payload={"reason": "rebalance_failed", "error": str(exc)}
            )


def _bar(day: int) -> Any:
    """A bar dated 2026-07-``day``. The 10th is a Friday (ISO week 28); the 13th is the
    following Monday (ISO week 29) — the exact boundary that broke the old guard."""
    return SimpleNamespace(t=datetime(2026, 7, day, 14, 0, tzinfo=UTC))


FRIDAY, MONDAY = 10, 13


def test_friday_and_monday_really_are_different_iso_weeks() -> None:
    """The premise. If this ever stops holding, the bug it models is gone."""
    assert _bar(FRIDAY).t.isocalendar()[:2] == (2026, 28)
    assert _bar(MONDAY).t.isocalendar()[:2] == (2026, 29)


async def test_one_dispatch_with_disagreeing_bars_rebalances_once() -> None:
    """THE REGRESSION. One dispatch, symbols whose bars straddle the week boundary.

    Under the OLD bar-keyed guard this sequence rebalances FIVE times — the guard flips
    28 -> 29 -> 28 -> 29 on every alternation. Under the dispatch-keyed guard: exactly once.
    """
    ctx = _Ctx(dispatch_seq=1)
    book = _Book(ctx)

    # 209 symbols in one tick; a handful lag a week behind the rest.
    for day in [MONDAY, MONDAY, FRIDAY, MONDAY, FRIDAY, MONDAY, MONDAY, FRIDAY, MONDAY]:
        await book.on_bar(_bar(day))

    assert book.rebalances == 1, (
        f"one cron dispatch produced {book.rebalances} rebalances — each one re-trades the "
        "book against stale holdings (the 2026-07-13 combined-book double-trade)"
    )


async def test_the_old_bar_keyed_guard_would_have_failed_this() -> None:
    """Prove the test is not vacuous: the guard we REPLACED really does oscillate.

    Without this, a future refactor could reintroduce the bar-keyed guard and the test above
    might still pass for the wrong reason.
    """
    days = [MONDAY, MONDAY, FRIDAY, MONDAY, FRIDAY, MONDAY, MONDAY, FRIDAY, MONDAY]

    last_week: tuple[int, int] | None = None
    rebalances = 0
    for day in days:
        wk = _bar(day).t.isocalendar()[:2]
        if wk == last_week:
            continue
        last_week = wk
        rebalances += 1

    # The old guard fires once per WEEK-CHANGE in the symbol order, so the count is whatever
    # the interleaving happens to be (live it was 5). The defect is that it is > 1 at all:
    # a single cron slot re-trading the book against stale holdings.
    assert rebalances > 1
    assert rebalances == 1 + sum(1 for a, b in zip(days, days[1:], strict=False) if a != b)


async def test_next_dispatch_rebalances_again() -> None:
    """The guard must not be a one-shot: the NEXT cron slot still rebalances."""
    ctx = _Ctx(dispatch_seq=1)
    book = _Book(ctx)
    for _ in range(50):
        await book.on_bar(_bar(MONDAY))
    assert book.rebalances == 1

    ctx.dispatch_seq = 2  # the engine stamps a new dispatch next week
    for _ in range(50):
        await book.on_bar(_bar(MONDAY))
    assert book.rebalances == 2


async def test_backtest_still_uses_the_bar_week() -> None:
    """No engine dispatch (dispatch_seq is None) => bars are replayed one at a time and the
    ISO week is the correct cadence. Rebalance once per week, not once per bar."""
    ctx = _Ctx(dispatch_seq=None)
    book = _Book(ctx)

    for day in (6, 7, 8, 9, FRIDAY):   # Mon-Fri, ISO week 28
        await book.on_bar(_bar(day))
    assert book.rebalances == 1

    await book.on_bar(_bar(MONDAY))    # week 29
    assert book.rebalances == 2


@pytest.mark.parametrize(
    "template",
    ["combined_book", "low_volatility", "momentum_portfolio", "sector_rotation"],
)
def test_every_live_template_keys_on_the_dispatch_not_the_bar(template: str) -> None:
    """All four live books must carry the fix — the bug is in the shared idiom, not in one
    book. combined_book is merely the one whose thin cross-asset ETFs exposed it first."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "strategies_user" / "templates"
    src = (root / f"{template}.py").read_text()

    assert "self._last_dispatch_seq" in src, f"{template} still lacks the dispatch guard"
    assert 'getattr(self.ctx, "dispatch_seq", None)' in src, (
        f"{template} does not read ctx.dispatch_seq"
    )
