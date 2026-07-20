"""MR-002 Increment 3 — official-open NAV valuation + daily return series (synthetic only).

Daily NAV marking ruling: official-open-to-official-open on the registered session calendar. NAV_s =
cash + Sum_long shares*open_s - Sum_short shares*open_s (long assets marked at the official open, short
liabilities marked at the official open). A held position without an official open mark on session s
fails closed (HELD_POSITION_OPEN_MARK_MISSING) — no forward-fill / close / midpoint. r_s =
NAV_s / NAV_{s-1} - 1. Split-adjusted, non-dividend-adjusted official opens only.
"""

from __future__ import annotations


class NavIntegrityStop(Exception):
    """INTEGRITY_STOP — a NAV valuation input failed (e.g. missing held-position open mark)."""


def mark_positions(held, opens_s: dict) -> float:
    """Signed mark of held positions at session s official opens; missing mark -> fail closed."""
    mv = 0.0
    for h in held:
        p = opens_s.get(h.symbol)
        if p is None:
            raise NavIntegrityStop(f"HELD_POSITION_OPEN_MARK_MISSING:{h.symbol}")
        mv += (h.shares * p) if h.side == "long" else -(h.shares * p)
    return mv


def daily_nav_record(*, session: int, cash: float, held, opens_s: dict, nav_prev) -> dict:
    """Value the book at session-s official opens and compute the primary daily return. `nav_prev`
    is the immediately preceding NAV (warm-up state for the first scoring session — never a spurious
    zero-return first observation)."""
    mark = mark_positions(held, opens_s)
    nav = cash + mark
    daily_return = None if nav_prev is None else (nav / nav_prev - 1.0)
    return {"session": session, "nav_prev": nav_prev, "nav": nav, "daily_return": daily_return,
            "cash": cash, "gross_mark": mark, "positions_valued": len(held),
            "open_marks_used": len(held)}


def return_series(nav_records: list) -> list:
    """Ordered daily simple returns (skipping the first record's None), for the Increment-1 metrics."""
    return [r["daily_return"] for r in nav_records if r["daily_return"] is not None]
