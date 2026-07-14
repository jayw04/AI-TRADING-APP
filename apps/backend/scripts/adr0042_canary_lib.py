"""ADR 0042 canary — shared harness: config, cap-aware sizing, snapshots, checkpoint, evidence.

WHAT WENT WRONG WITH THE OLD HARNESS, and why each piece below exists
---------------------------------------------------------------------
1. It **flattened every position**, including the F/MSFT legs the assertions depend on. That
   produced a RED for a reason with nothing to do with the risk engine. -> `PROTECTED`, honoured
   everywhere, and a hard refusal to sell a protected symbol.

2. Its deadline was **hard-coded to a date** (`2026-07-13 19:50 UTC`). A test that silently expires
   is worse than no test. -> a RELATIVE, configurable budget.

3. Its breach sizing used a **fixed notional** and simply absorbed rejections. When user 3's
   position caps refused the orders it churned uselessly and stalled. -> sizing derived from the
   ACCOUNT'S OWN LIMITS, and an explicit `BREACH_SETUP_UNREACHABLE_UNDER_CURRENT_LIMITS` when the
   breach cannot be reached without touching them.

4. It depended on a **long-lived SSH session**. When the session dropped mid-cycle the run died in
   an indeterminate state — and, worse, a second invocation raced the first, which is how two
   processes came to hold ALLOW for the same 183 shares. -> checkpointed, resumable, idempotent,
   and single-instance by lock file.

THE LIMITS ARE NEVER MOVED TO MEET THE ACCOUNT. If the breach is unreachable under the configured
risk limits, the harness stops and says so. Lowering `max_daily_loss` to manufacture a breach is a
bypass, not a test.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from sqlalchemy import text

# ---------------------------------------------------------------------------- config
USER = int(os.environ.get("ADR0042_USER", "3"))
ACCT = int(os.environ.get("ADR0042_ACCOUNT", "3"))

# The protected legs. Never churned, never flattened, never sold except by an assertion that
# deliberately does so. Configurable, but with a safe default.
PROTECTED: tuple[str, ...] = tuple(
    s.strip().upper() for s in os.environ.get("ADR0042_PROTECTED", "F,MSFT").split(",") if s.strip()
)
LEGS: tuple[tuple[str, D], ...] = tuple(
    (sym, D(qty))
    for sym, qty in (
        pair.split(":") for pair in os.environ.get("ADR0042_LEGS", "F:500,MSFT:20").split(",")
    )
)

# Churn instruments. Wide-spread names cost the most per round trip.
CHURN_SYMBOLS: tuple[str, ...] = tuple(
    s.strip().upper()
    for s in os.environ.get("ADR0042_CHURN", "IEUS,KOKU").split(",")
    if s.strip()
)

# RELATIVE, not a date. A canary that expires on a calendar is not a canary.
BUDGET_MINUTES = int(os.environ.get("ADR0042_BUDGET_MINUTES", "150"))

# The breach target. Deliberately BELOW the frozen loss cap so the lock is unambiguous.
TARGET_OVERSHOOT = D(os.environ.get("ADR0042_TARGET_OVERSHOOT", "250"))

CHECKPOINT = Path(os.environ.get("ADR0042_CHECKPOINT", "/app/data/adr0042_canary_state.json"))
LOCKFILE = Path(os.environ.get("ADR0042_LOCKFILE", "/app/data/adr0042_canary.lock"))

POLICY_VERSION = "0042.1"


class BreachUnreachable(RuntimeError):
    """BREACH_SETUP_UNREACHABLE_UNDER_CURRENT_LIMITS.

    The account's own risk limits do not permit enough turnover to realise the configured loss.
    This is a SETUP failure, and the answer is NOT to relax the limits — that would be the same
    error as moving `max_daily_loss` to meet the account.
    """


class CanaryRefused(RuntimeError):
    """The harness refuses to run: a precondition for a VALID run is absent."""


# ---------------------------------------------------------------------------- state snapshot
@dataclass(frozen=True)
class StateSnapshot:
    """Recorded immediately before EVERY order, so no assertion has to assume the lock was on."""

    at: str
    day_change: D
    equity: D
    last_equity: D
    max_daily_loss: D | None
    lock_active: bool
    breaker_tripped_at: str | None
    positions: dict[str, D]
    open_orders: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "day_change": str(self.day_change),
            "equity": str(self.equity),
            "last_equity": str(self.last_equity),
            "max_daily_loss": str(self.max_daily_loss) if self.max_daily_loss else None,
            "lock_active": self.lock_active,
            "breaker_tripped_at": self.breaker_tripped_at,
            "positions": {k: str(v) for k, v in self.positions.items()},
            "open_orders": self.open_orders,
        }


async def snapshot_state(sf, adapter) -> StateSnapshot:
    """The pre-order record. Ambiguity about whether the lock was engaged is not acceptable
    evidence, so it is measured rather than inferred."""
    async with sf() as s:
        row = (
            await s.execute(
                text(
                    "SELECT day_change, equity, last_equity FROM accounts_state "
                    "WHERE account_id = :a"
                ),
                {"a": ACCT},
            )
        ).mappings().first() or {}
        tripped = (
            await s.execute(
                text("SELECT circuit_breaker_tripped_at FROM accounts WHERE id = :a"),
                {"a": ACCT},
            )
        ).scalar()
        cap = (
            await s.execute(
                text(
                    "SELECT max_daily_loss FROM risk_limits "
                    "WHERE user_id = :u AND scope_type = 'GLOBAL' AND broker_mode = 'paper'"
                ),
                {"u": USER},
            )
        ).scalar()

    dc = D(str(row.get("day_change") or 0))
    cap_d = D(str(cap)) if cap is not None else None
    return StateSnapshot(
        at=datetime.now(UTC).isoformat(),
        day_change=dc,
        equity=D(str(row.get("equity") or 0)),
        last_equity=D(str(row.get("last_equity") or 0)),
        max_daily_loss=cap_d,
        lock_active=bool(cap_d is not None and dc <= -cap_d),
        breaker_tripped_at=str(tripped) if tripped else None,
        positions={p["symbol"]: D(str(p["qty"])) for p in adapter.get_positions()},
        open_orders=len(adapter.list_orders() or []),
    )


# ---------------------------------------------------------------------------- cap-aware sizing
@dataclass(frozen=True)
class Limits:
    max_position_qty: D | None
    max_position_notional: D | None
    max_gross_exposure: D | None
    max_daily_loss: D | None
    max_orders_per_day: int | None

    def as_dict(self) -> dict[str, Any]:
        return {k: (str(v) if v is not None else None) for k, v in self.__dict__.items()}


async def load_limits(sf) -> Limits:
    async with sf() as s:
        row = (
            await s.execute(
                text(
                    "SELECT max_position_qty, max_position_notional, max_gross_exposure, "
                    "max_daily_loss, max_orders_per_day FROM risk_limits "
                    "WHERE user_id = :u AND scope_type = 'GLOBAL' AND broker_mode = 'paper'"
                ),
                {"u": USER},
            )
        ).mappings().first()
    if row is None:
        raise CanaryRefused(f"no paper GLOBAL risk_limits row for user {USER}")

    def dec(v):
        return D(str(v)) if v is not None else None

    return Limits(
        max_position_qty=dec(row["max_position_qty"]),
        max_position_notional=dec(row["max_position_notional"]),
        max_gross_exposure=dec(row["max_gross_exposure"]),
        max_daily_loss=dec(row["max_daily_loss"]),
        max_orders_per_day=int(row["max_orders_per_day"])
        if row["max_orders_per_day"] is not None
        else None,
    )


def admissible_shares(
    *, price: D, limits: Limits, gross_used: D, buying_power: D, ceiling: D
) -> D:
    """The largest order the account's OWN limits admit — computed, not guessed.

    The old harness picked a fixed $24k notional and then absorbed the resulting
    POSITION_CAP_QTY rejections, churning uselessly. Sizing must be derived from the limits, not
    discovered by being refused.
    """
    if price <= 0:
        return D(0)

    caps = [ceiling / price]
    if limits.max_position_qty is not None:
        caps.append(limits.max_position_qty)
    if limits.max_position_notional is not None:
        caps.append(limits.max_position_notional / price)
    if limits.max_gross_exposure is not None:
        caps.append(max(D(0), limits.max_gross_exposure - gross_used) / price)
    caps.append(max(D(0), buying_power) / price)

    return max(D(0), min(caps).quantize(D("1")))


# ---------------------------------------------------------------------------- checkpoint
@dataclass
class Checkpoint:
    """Durable, resumable, idempotent. A dropped connection must never leave the run in an
    indeterminate state — and must never let a SECOND invocation race the first, which is how two
    processes came to hold ALLOW for the same 183 shares."""

    phase: str = "INIT"
    cycles: int = 0
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    deadline_at: str = ""
    legs_established: bool = False
    breach_reached: bool = False
    events: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls) -> Checkpoint:
        if CHECKPOINT.exists():
            data = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
            return cls(**data)
        cp = cls()
        cp.deadline_at = (datetime.now(UTC) + timedelta(minutes=BUDGET_MINUTES)).isoformat()
        cp.save()
        return cp

    def save(self) -> None:
        CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
        tmp = CHECKPOINT.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.__dict__, indent=2, default=str), encoding="utf-8")
        tmp.replace(CHECKPOINT)          # atomic — a torn checkpoint is worse than none

    def expired(self) -> bool:
        return datetime.now(UTC) >= datetime.fromisoformat(self.deadline_at)

    def note(self, kind: str, **fields: Any) -> None:
        self.events.append({"at": datetime.now(UTC).isoformat(), "kind": kind, **fields})
        self.save()


class SingleInstance:
    """Refuse to run twice. Two concurrent harness processes are exactly what produced the
    cross-process double-reservation on 2026-07-14."""

    def __init__(self) -> None:
        self._fd: int | None = None

    def __enter__(self) -> SingleInstance:
        LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._fd = os.open(str(LOCKFILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            age = time.time() - LOCKFILE.stat().st_mtime
            raise CanaryRefused(
                f"another canary process holds {LOCKFILE} (age {age:.0f}s). Two concurrent "
                f"harness processes is precisely the condition that produced the cross-process "
                f"double reservation. Remove the lock only if you are certain no run is live."
            ) from exc
        os.write(self._fd, str(os.getpid()).encode())
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
        LOCKFILE.unlink(missing_ok=True)


# ---------------------------------------------------------------------------- evidence
class Evidence:
    """Every field the evidence package must bind, collected as the run proceeds."""

    def __init__(self, phase: str) -> None:
        self.doc: dict[str, Any] = {
            "phase": phase,
            "policy_version": POLICY_VERSION,
            "account_id": ACCT,
            "user_id": USER,
            "started_at": datetime.now(UTC).isoformat(),
            # Provenance: asserted "ran from committed code" is worthless unless it is
            # cryptographically tied to the deployed container.
            "commit_sha": os.environ.get("ADR0042_COMMIT_SHA"),
            "image_digest": os.environ.get("ADR0042_IMAGE_DIGEST"),
            "deployed_at": os.environ.get("ADR0042_DEPLOYED_AT"),
            "config": {
                "protected": list(PROTECTED),
                "legs": [[s, str(q)] for s, q in LEGS],
                "churn_symbols": list(CHURN_SYMBOLS),
                "budget_minutes": BUDGET_MINUTES,
                "target_overshoot": str(TARGET_OVERSHOOT),
            },
            "risk_limits": None,
            "breaker_transitions": [],
            "operator_actions": [],
            "orders": [],
            "assertions": [],
            "final": None,
        }

    def record_order(
        self, *, step: str, snapshot: StateSnapshot, request: dict, response: Any
    ) -> None:
        self.doc["orders"].append(
            {
                "step": step,
                "pre_order_state": snapshot.as_dict(),
                "request": request,
                "order_id": getattr(response, "id", None),
                "broker_order_id": getattr(response, "broker_order_id", None),
                "status": str(getattr(response, "status", response)),
                "rejection_reason": getattr(response, "rejection_reason", None),
            }
        )

    def assert_(self, name: str, ok: bool, detail: str) -> bool:
        self.doc["assertions"].append({"name": name, "result": "PASS" if ok else "FAIL",
                                       "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
        return ok

    def passed(self) -> bool:
        return all(a["result"] == "PASS" for a in self.doc["assertions"])

    def write(self, path: Path) -> str:
        import hashlib

        self.doc["finished_at"] = datetime.now(UTC).isoformat()
        self.doc["gate"] = "PASS" if self.passed() else "FAIL"
        blob = json.dumps(self.doc, indent=2, default=str)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(blob, encoding="utf-8")
        return hashlib.sha256(blob.encode()).hexdigest()


async def ledger_rows_for(sf, *, since_id: int = 0) -> list[dict]:
    """The append-only decision ledger — the audit trail every rejection must leave behind."""
    async with sf() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT id, action_type, symbol, side, qty, lock_state, lock_reason, "
                    "daily_pnl, risk_effect, decision, reason_codes, risk_policy_version, "
                    "capacity_state_version, correlation_id, decided_at "
                    "FROM risk_decisions WHERE account_id = :a AND id > :i ORDER BY id"
                ),
                {"a": ACCT, "i": since_id},
            )
        ).mappings().all()
    return [dict(r) for r in rows]


async def max_ledger_id(sf) -> int:
    async with sf() as s:
        return int(
            (
                await s.execute(
                    text("SELECT COALESCE(MAX(id), 0) FROM risk_decisions WHERE account_id = :a"),
                    {"a": ACCT},
                )
            ).scalar()
            or 0
        )
