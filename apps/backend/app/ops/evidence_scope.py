"""Per-account scoping helpers for the live-evidence tools.

Resolve a PAPER strategy to its owning user + that user's dedicated Alpaca paper account (per-user
isolation — one paper account per user, P5 §7), so the evidence reports (`live_evidence.py`,
`monthly_evidence.py`, `confidence_score.py`, `ops_kpis.py`) can each scope their queries to ONE book
instead of aggregating across every account. Raw-sqlite to match the report scripts' read-only
connections; pure (no clock, no writes).
"""

from __future__ import annotations

import sqlite3


def paper_strategy_ids(con: sqlite3.Connection) -> list[int]:
    """Every strategy currently on PAPER (ascending id). Drives `--all-paper` fan-out so the weekly
    evidence covers all live books (SEC-001, LOW-001, combined-book, …), not just the default one."""
    try:
        return [int(r[0]) for r in con.execute(
            "SELECT id FROM strategies WHERE status='PAPER' ORDER BY id")]
    except sqlite3.OperationalError:
        return []


def resolve_paper_account(
    con: sqlite3.Connection, strategy_id: int
) -> tuple[int | None, int | None]:
    """``(user_id, account_id)`` for a strategy's owner and its dedicated Alpaca paper account.

    Either element is ``None`` if the strategy row or the account is absent. Mirrors the resolution
    in ``live_evidence.build`` (strategy → ``user_id`` → ``accounts`` where
    ``broker='alpaca' AND mode='paper'``), so every consumer scopes identically.
    """
    srow = con.execute(
        "SELECT user_id FROM strategies WHERE id=?", (strategy_id,)).fetchone()
    user_id = int(srow[0]) if srow and srow[0] is not None else None
    account_id: int | None = None
    if user_id is not None:
        arow = con.execute(
            "SELECT id FROM accounts WHERE user_id=? AND broker='alpaca' AND mode='paper' "
            "ORDER BY id LIMIT 1", (user_id,)).fetchone()
        account_id = int(arow[0]) if arow else None
    return user_id, account_id
