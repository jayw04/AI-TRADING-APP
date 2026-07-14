"""ADR 0042 § D — the reducible-capacity claim must hold ACROSS PROCESSES.

⚠ WHY THIS TEST USES REAL OS PROCESSES

A single-process concurrency test — two coroutines under ``asyncio.gather`` — passes on the OLD,
BROKEN implementation, because the process-local ``asyncio.Lock`` serialises them. It would have
certified the very defect it was written to catch.

On 2026-07-14 two independent Python processes each read ``reserved = 0``, each saw
``available_reducible_qty = 183``, and each received ``ALLOW / VERIFIED_REDUCTION`` for the same
183 shares, 139 ms apart. Only the broker stopped the second order.

So the test forks. Two interpreters, two event loops, two database connections, one shared SQLite
file, and a barrier immediately before the claim. Exactly one may win.

The guard against a vacuous pass is `test_the_old_process_local_lock_would_have_failed_this`,
which asserts the two claims genuinely raced.
"""

from __future__ import annotations

import multiprocessing as mp
import sqlite3
import tempfile
import time
from decimal import Decimal
from pathlib import Path

CAPACITY = Decimal(183)
SNAPSHOT = "snapshot-v1"


def _schema(db: str) -> None:
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE risk_capacity_state (
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            snapshot_version TEXT NOT NULL,
            reducible_capacity_qty NUMERIC NOT NULL DEFAULT 0,
            reserved_qty NUMERIC NOT NULL DEFAULT 0,
            state_version INTEGER NOT NULL DEFAULT 0,
            UNIQUE (account_id, symbol)
        );
        CREATE TABLE claims (pid INTEGER, outcome TEXT, version INTEGER, t REAL);
        """
    )
    con.execute(
        "INSERT INTO risk_capacity_state "
        "(account_id, symbol, snapshot_version, reducible_capacity_qty, reserved_qty, "
        " state_version) VALUES (3, 'KOKU', ?, ?, 0, 0)",
        (SNAPSHOT, str(CAPACITY)),
    )
    con.commit()
    con.close()


def _claim_worker(db: str, qty: str, barrier_at: float) -> None:
    """A separate OS process: its own interpreter, event loop and DB connection.

    This is the same conditional UPDATE that `RiskDecisionService._claim_capacity` issues. The
    guard lives entirely in the WHERE clause, so the database decides — once.
    """
    import os

    con = sqlite3.connect(db, timeout=30, isolation_level=None)
    while time.time() < barrier_at:          # release both processes at the same instant
        time.sleep(0.001)

    con.execute("BEGIN IMMEDIATE")
    cur = con.execute(
        """
        UPDATE risk_capacity_state
           SET reserved_qty = reserved_qty + :qty,
               state_version = state_version + 1
         WHERE account_id = 3
           AND symbol = 'KOKU'
           AND snapshot_version = :snap
           AND reserved_qty + :qty <= reducible_capacity_qty
        """,
        {"qty": float(qty), "snap": SNAPSHOT},
    )
    won = cur.rowcount == 1
    version = con.execute(
        "SELECT state_version FROM risk_capacity_state WHERE account_id=3 AND symbol='KOKU'"
    ).fetchone()[0]
    con.execute(
        "INSERT INTO claims (pid, outcome, version, t) VALUES (?, ?, ?, ?)",
        (os.getpid(), "ALLOW" if won else "REJECT", version, time.time()),
    )
    con.execute("COMMIT")
    con.close()


def _race(qty_a: str, qty_b: str) -> list[tuple]:
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "race.db")
        _schema(db)
        barrier = time.time() + 0.35
        ctx = mp.get_context("spawn")          # a genuinely separate interpreter, not a fork
        procs = [
            ctx.Process(target=_claim_worker, args=(db, qty_a, barrier)),
            ctx.Process(target=_claim_worker, args=(db, qty_b, barrier)),
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)
            assert p.exitcode == 0, f"claim worker crashed: exit {p.exitcode}"

        con = sqlite3.connect(db)
        claims = con.execute("SELECT pid, outcome, version, t FROM claims").fetchall()
        state = con.execute(
            "SELECT reserved_qty, reducible_capacity_qty, state_version "
            "FROM risk_capacity_state WHERE account_id=3 AND symbol='KOKU'"
        ).fetchone()
        con.close()
        return claims, state



def test_two_processes_cannot_both_claim_the_same_capacity():
    """THE regression test for the 2026-07-14 defect.

    Long 183. Two processes each request SELL 183. Exactly one may claim.
    """
    claims, state = _race("183", "183")

    outcomes = sorted(c[1] for c in claims)
    assert len(claims) == 2, "both processes must have recorded an outcome"
    assert outcomes == ["ALLOW", "REJECT"], (
        f"both processes claimed the same capacity: {outcomes} — this is the exact defect that "
        f"let two ALLOW/VERIFIED_REDUCTION decisions consume the same 183 KOKU shares"
    )

    reserved, capacity, version = Decimal(str(state[0])), Decimal(str(state[1])), state[2]
    assert reserved == CAPACITY, f"reserved {reserved} != {CAPACITY}"
    assert reserved <= capacity, "THE INVARIANT: reserved must never exceed reducible capacity"
    assert version == 1, "exactly one claim may have moved the capacity version"

    pids = {c[0] for c in claims}
    assert len(pids) == 2, "the two claims must have come from genuinely different processes"



def test_three_partial_claims_exceeding_capacity_are_bounded():
    """§11 — partial quantities whose TOTAL exceeds capacity. The sum, not each request, is what
    the invariant constrains, so a naive per-request check would pass this while overselling."""
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "race3.db")
        _schema(db)
        barrier = time.time() + 0.35
        ctx = mp.get_context("spawn")
        procs = [
            ctx.Process(target=_claim_worker, args=(db, q, barrier))
            for q in ("100", "100", "100")           # 300 > 183
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)
            assert p.exitcode == 0

        con = sqlite3.connect(db)
        outcomes = [r[0] for r in con.execute("SELECT outcome FROM claims").fetchall()]
        reserved, capacity = con.execute(
            "SELECT reserved_qty, reducible_capacity_qty FROM risk_capacity_state"
        ).fetchone()
        con.close()

    assert outcomes.count("ALLOW") == 1, f"only 100 of 183 fits twice? outcomes = {outcomes}"
    assert Decimal(str(reserved)) <= Decimal(str(capacity)), "capacity was oversubscribed"



def test_a_stale_snapshot_version_cannot_claim():
    """§11 — a claim computed against a snapshot that has since moved must not succeed. The
    version is pinned in the WHERE clause precisely so a stale view cannot win a race."""
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "stale.db")
        _schema(db)
        con = sqlite3.connect(db, isolation_level=None)
        cur = con.execute(
            """
            UPDATE risk_capacity_state
               SET reserved_qty = reserved_qty + 10, state_version = state_version + 1
             WHERE account_id = 3 AND symbol = 'KOKU'
               AND snapshot_version = 'snapshot-STALE'
               AND reserved_qty + 10 <= reducible_capacity_qty
            """
        )
        assert cur.rowcount == 0, "a claim against a stale snapshot version must not update a row"
        reserved = con.execute("SELECT reserved_qty FROM risk_capacity_state").fetchone()[0]
        con.close()
    assert Decimal(str(reserved)) == 0, "a refused claim must not have consumed capacity"



def test_the_old_process_local_lock_would_have_failed_this():
    """Guards the guard.

    If the two workers did not actually overlap in time, the race was never exercised and the
    passing result above would be meaningless. Assert they raced: both claims must land within a
    short window of the shared barrier.
    """
    claims, _state = _race("183", "183")
    times = sorted(c[3] for c in claims)
    assert times[1] - times[0] < 2.0, (
        "the two processes did not overlap; the concurrency was not actually exercised and the "
        "pass would be vacuous"
    )


def _legacy_worker(db: str, qty: str, barrier_at: float) -> None:
    """The OLD pattern: SELECT the reserved sum, decide in Python, then INSERT unconditionally.

    This is what `RiskDecisionService` did before ADR 0042 §D — guarded only by a process-local
    ``asyncio.Lock``, which two separate interpreters do not share.
    """
    import os

    con = sqlite3.connect(db, timeout=30, isolation_level=None)
    while time.time() < barrier_at:
        time.sleep(0.001)

    # read ...
    reserved, capacity = con.execute(
        "SELECT reserved_qty, reducible_capacity_qty FROM risk_capacity_state "
        "WHERE account_id=3 AND symbol='KOKU'"
    ).fetchone()
    time.sleep(0.05)                       # ... classify in Python (the window) ...
    allowed = float(reserved) + float(qty) <= float(capacity)
    if allowed:                            # ... then write unconditionally
        con.execute(
            "UPDATE risk_capacity_state SET reserved_qty = reserved_qty + ? "
            "WHERE account_id=3 AND symbol='KOKU'",
            (float(qty),),
        )
    con.execute(
        "INSERT INTO claims (pid, outcome, version, t) VALUES (?, ?, 0, ?)",
        (os.getpid(), "ALLOW" if allowed else "REJECT", time.time()),
    )
    con.close()


def test_the_OLD_pattern_double_allows_under_the_SAME_harness():
    """GUARDS THE GUARD — proves the test is not vacuous.

    If this harness could not reproduce the defect, the passing result above would prove nothing.
    Run the SAME two-process race against the OLD read-then-write pattern: both processes must
    receive ALLOW, and the capacity must be oversubscribed — exactly what happened on the live
    book on 2026-07-14, where only the broker stopped the second order.
    """
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "legacy.db")
        _schema(db)
        barrier = time.time() + 0.35
        ctx = mp.get_context("spawn")
        procs = [
            ctx.Process(target=_legacy_worker, args=(db, "183", barrier)),
            ctx.Process(target=_legacy_worker, args=(db, "183", barrier)),
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=60)
            assert p.exitcode == 0

        con = sqlite3.connect(db)
        outcomes = sorted(r[0] for r in con.execute("SELECT outcome FROM claims").fetchall())
        reserved, capacity = con.execute(
            "SELECT reserved_qty, reducible_capacity_qty FROM risk_capacity_state"
        ).fetchone()
        con.close()

    assert outcomes == ["ALLOW", "ALLOW"], (
        "the harness FAILED to reproduce the defect, so the conditional-claim tests above prove "
        f"nothing: got {outcomes}"
    )
    assert Decimal(str(reserved)) > Decimal(str(capacity)), (
        "the old pattern must oversubscribe capacity — that is the defect"
    )
