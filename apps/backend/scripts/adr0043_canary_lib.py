"""ADR 0043 canary — shared harness: config, loss-control snapshots, checkpoint, evidence.

This mirrors ``adr0042_canary_lib`` and inherits its hard-won discipline (the notes there explain
WHY each guard exists): protected legs that are never flattened, a RELATIVE budget (never a
hard-coded date), cap-aware sizing derived from the account's OWN limits (never relaxed to
manufacture a breach), and a checkpointed / single-instance / idempotent run (two concurrent
harnesses are exactly what produced the 2026-07-14 cross-process double reservation).

WHAT IS DIFFERENT FROM 0042
---------------------------
0042 verified ONE property: a verified risk-reducing order passes the daily-loss/breaker gates. This
0043 harness verifies the loss-control STATE MACHINE in ``ENFORCE``: after a lock the account sits in
a durable ``REDUCTION_ONLY_*`` state; a verified reduction is ``ALLOW_REDUCTION_ONLY`` while new /
neutral risk is ``REFUSE`` (``LOSS_CONTROL_STOP``) with a durable control event; unknown state fails
closed to ``INTEGRITY_STOP``; and the sanctioned recovery path (preflight → cooldown) is reachable.

It stops SHORT of a real timed re-arm: the §D6 dwell tiers (30 min, until-next-session, until manual
repair) cannot be driven to completion inside one live run, so the harness asserts the account
ENTERS ``RECOVERY_COOLDOWN`` and that the evaluator HOLDs — it never fakes elapsed time to force a
``NORMAL`` (that would be the same class of lie as moving ``max_daily_loss`` to meet the account).

⚠ RUNTIME IS AWS. This harness runs on the box against the live paper acct-3 rig; it is NEVER run
against the laptop's local stack. The CI harness-invariant tests (``test_adr0043_canary_harness``)
are the offline half — they verify the harness cannot lie, without touching a broker.
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
USER = int(os.environ.get("ADR0043_USER", "3"))
ACCT = int(os.environ.get("ADR0043_ACCOUNT", "3"))

# The protected legs — the reduction targets the assertions need. Never churned or flattened.
PROTECTED: tuple[str, ...] = tuple(
    s.strip().upper() for s in os.environ.get("ADR0043_PROTECTED", "F,MSFT").split(",") if s.strip()
)
LEGS: tuple[tuple[str, D], ...] = tuple(
    (sym, D(qty))
    for sym, qty in (
        pair.split(":") for pair in os.environ.get("ADR0043_LEGS", "F:500,MSFT:20").split(",")
    )
)

# Churn instruments used to drive the loss. Wide-spread names cost the most per round trip.
CHURN_SYMBOLS: tuple[str, ...] = tuple(
    s.strip().upper()
    for s in os.environ.get("ADR0043_CHURN", "IEUS,KOKU").split(",")
    if s.strip()
)

# RELATIVE, not a date. A canary that expires on a calendar is not a canary.
BUDGET_MINUTES = int(os.environ.get("ADR0043_BUDGET_MINUTES", "150"))

# The breach target. Deliberately BELOW the frozen loss cap so the lock is unambiguous.
TARGET_OVERSHOOT = D(os.environ.get("ADR0043_TARGET_OVERSHOOT", "250"))

CHECKPOINT = Path(os.environ.get("ADR0043_CHECKPOINT", "/app/data/adr0043_canary_state.json"))
LOCKFILE = Path(os.environ.get("ADR0043_LOCKFILE", "/app/data/adr0043_canary.lock"))

POLICY_VERSION = "0043.1"

# The loss-control mode the harness REQUIRES to make a meaningful assertion. A canary run under
# OFF/SHADOW would assert nothing about the authoritative path — it must refuse rather than pretend.
REQUIRED_LOSS_CONTROL_MODE = "ENFORCE"

# Durable loss-control states.
STATE_NORMAL = "NORMAL"
STATE_REDUCTION_ONLY_DAILY_LOSS = "REDUCTION_ONLY_DAILY_LOSS"
STATE_REDUCTION_ONLY_BREAKER = "REDUCTION_ONLY_BREAKER"
STATE_INTEGRITY_STOP = "INTEGRITY_STOP"
STATE_RECOVERY_PREFLIGHT = "RECOVERY_PREFLIGHT"
STATE_RECOVERY_COOLDOWN = "RECOVERY_COOLDOWN"
REDUCTION_ONLY_STATES = frozenset(
    {STATE_REDUCTION_ONLY_DAILY_LOSS, STATE_REDUCTION_ONLY_BREAKER}
)


class BreachUnreachable(RuntimeError):
    """BREACH_SETUP_UNREACHABLE_UNDER_CURRENT_LIMITS — the account's own limits do not permit enough
    turnover to realise the loss. The answer is NOT to relax the limits (that is the bug this whole
    ADR exists to prevent)."""


class CanaryRefused(RuntimeError):
    """The harness refuses to run: a precondition for a VALID run is absent (wrong mode, no lock,
    missing legs). A refusal is a correct outcome — a run that assumes its preconditions is not."""


# ---------------------------------------------------------------------------- state snapshot
@dataclass(frozen=True)
class StateSnapshot:
    """Recorded immediately before EVERY order, so no assertion has to ASSUME the lock was on. Unlike
    0042 this also captures the durable loss-control state — the property under test."""

    at: str
    day_change: D
    equity: D
    last_equity: D
    max_daily_loss: D | None
    breaker_tripped_at: str | None
    loss_control_state: str | None
    loss_control_state_version: int | None
    last_sequence_no: int | None
    positions: dict[str, D]
    open_orders: int

    @property
    def reduction_only(self) -> bool:
        return self.loss_control_state in REDUCTION_ONLY_STATES

    @property
    def locked(self) -> bool:
        """Any non-NORMAL loss-control state is a lock for the purpose of the canary."""
        return self.loss_control_state is not None and self.loss_control_state != STATE_NORMAL

    def as_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "day_change": str(self.day_change),
            "equity": str(self.equity),
            "last_equity": str(self.last_equity),
            "max_daily_loss": str(self.max_daily_loss) if self.max_daily_loss else None,
            "breaker_tripped_at": self.breaker_tripped_at,
            "loss_control_state": self.loss_control_state,
            "loss_control_state_version": self.loss_control_state_version,
            "last_sequence_no": self.last_sequence_no,
            "reduction_only": self.reduction_only,
            "positions": {k: str(v) for k, v in self.positions.items()},
            "open_orders": self.open_orders,
        }


# ``list_orders()`` returns RECENT orders; only these statuses actually hold capacity at the broker.
_OPEN_STATUSES = {"new", "accepted", "pending_new", "partially_filled",
                  "accepted_for_bidding", "pending_replace", "replaced"}


def _count_open(adapter) -> int:
    return sum(
        1
        for o in (adapter.list_orders() or [])
        if str(o.get("status", "")).lower() in _OPEN_STATUSES
    )


async def snapshot_state(sf, adapter) -> StateSnapshot:
    """The pre-order record. Whether the loss-control lock is engaged is MEASURED, not inferred."""
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
        lc = (
            await s.execute(
                text(
                    "SELECT state, state_version, last_sequence_no "
                    "FROM risk_loss_control_state WHERE account_id = :a"
                ),
                {"a": ACCT},
            )
        ).mappings().first()

    cap_d = D(str(cap)) if cap is not None else None
    return StateSnapshot(
        at=datetime.now(UTC).isoformat(),
        day_change=D(str(row.get("day_change") or 0)),
        equity=D(str(row.get("equity") or 0)),
        last_equity=D(str(row.get("last_equity") or 0)),
        max_daily_loss=cap_d,
        breaker_tripped_at=str(tripped) if tripped else None,
        loss_control_state=lc["state"] if lc else None,
        loss_control_state_version=lc["state_version"] if lc else None,
        last_sequence_no=lc["last_sequence_no"] if lc else None,
        positions={p["symbol"]: D(str(p["qty"])) for p in adapter.get_positions()},
        open_orders=_count_open(adapter),
    )


async def loss_control_mode(sf) -> str:
    """The effective loss-control mode — read from the deployed config, NOT assumed. A canary that
    silently runs under OFF/SHADOW proves nothing."""
    # The mode is process config, not DB; the run script passes it in via env and records it. This
    # helper centralises the spelling so the harness and its tests agree.
    return os.environ.get("WORKBENCH_LOSS_CONTROL_MODE", "OFF").upper()


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
    """The largest order the account's OWN limits admit — computed, not guessed (never discovered by
    being refused, and never enlarged by relaxing a limit)."""
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
    """Durable, resumable, idempotent — a dropped SSH session must never leave the run indeterminate
    or let a SECOND invocation race the first."""

    phase: str = "INIT"
    cycles: int = 0
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    deadline_at: str = ""
    legs_established: bool = False
    lock_reached: bool = False
    events: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls) -> Checkpoint:
        if CHECKPOINT.exists():
            return cls(**json.loads(CHECKPOINT.read_text(encoding="utf-8")))
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
    """Refuse to run twice — two concurrent harness processes are the 2026-07-14 double-reservation
    condition."""

    def __init__(self) -> None:
        self._fd: int | None = None

    def __enter__(self) -> SingleInstance:
        LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._fd = os.open(str(LOCKFILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            age = time.time() - LOCKFILE.stat().st_mtime
            raise CanaryRefused(
                f"another canary process holds {LOCKFILE} (age {age:.0f}s). Two concurrent harness "
                f"processes is precisely the condition that produced the cross-process double "
                f"reservation. Remove the lock only if you are certain no run is live."
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
            "loss_control_mode": os.environ.get("WORKBENCH_LOSS_CONTROL_MODE"),
            "commit_sha": os.environ.get("ADR0043_COMMIT_SHA"),
            "image_digest": os.environ.get("ADR0043_IMAGE_DIGEST"),
            "deployed_at": os.environ.get("ADR0043_DEPLOYED_AT"),
            "config": {
                "protected": list(PROTECTED),
                "legs": [[s, str(q)] for s, q in LEGS],
                "churn_symbols": list(CHURN_SYMBOLS),
                "budget_minutes": BUDGET_MINUTES,
                "target_overshoot": str(TARGET_OVERSHOOT),
                "required_mode": REQUIRED_LOSS_CONTROL_MODE,
            },
            "risk_limits": None,
            "control_events": [],
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
        return bool(self.doc["assertions"]) and all(
            a["result"] == "PASS" for a in self.doc["assertions"])

    def write(self, path: Path) -> str:
        import hashlib

        self.doc["finished_at"] = datetime.now(UTC).isoformat()
        self.doc["gate"] = "PASS" if self.passed() else "FAIL"
        blob = json.dumps(self.doc, indent=2, default=str)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(blob, encoding="utf-8")
        return hashlib.sha256(blob.encode()).hexdigest()


# ---------------------------------------------------------------------------- durable trails
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


async def control_events_for(sf, *, since_id: int = 0) -> list[dict]:
    """The append-only loss-control event log — every state transition the machine committed."""
    async with sf() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT id, sequence_no, control_type, from_state, to_state, "
                    "requested_transition, trip_type, trip_cause, trip_evidence_status, "
                    "initiator_type, created_at "
                    "FROM risk_control_events WHERE account_id = :a AND id > :i ORDER BY id"
                ),
                {"a": ACCT, "i": since_id},
            )
        ).mappings().all()
    return [dict(r) for r in rows]


async def max_control_event_id(sf) -> int:
    async with sf() as s:
        return int(
            (
                await s.execute(
                    text(
                        "SELECT COALESCE(MAX(id), 0) FROM risk_control_events WHERE account_id = :a"
                    ),
                    {"a": ACCT},
                )
            ).scalar()
            or 0
        )
