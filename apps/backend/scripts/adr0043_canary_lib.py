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
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db.models.risk_reservation import RESERVATION_HELD

# ---------------------------------------------------------------------------- config
USER = int(os.environ.get("ADR0043_USER", "3"))
ACCT = int(os.environ.get("ADR0043_ACCOUNT", "3"))

# The protected legs — the reduction targets the assertions need. Never churned or flattened.
# Re-frozen to MSFT-only (manifest v1.1): the frozen canary account (account 3, PA34USW0Q8UO) holds
# MSFT and no F, so the reduction target is MSFT. Legs are never bought/established by the harness —
# it REFUSES if a declared leg is absent — so the config must match what the account actually holds.
PROTECTED: tuple[str, ...] = tuple(
    s.strip().upper() for s in os.environ.get("ADR0043_PROTECTED", "MSFT").split(",") if s.strip()
)
LEGS: tuple[tuple[str, D], ...] = tuple(
    (sym, D(qty))
    for sym, qty in (
        pair.split(":") for pair in os.environ.get("ADR0043_LEGS", "MSFT:19").split(",")
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

# The single share the A2 reduction sells and the A3 new-risk BUY asks for. One constant so the
# submit, the identity check, and the expected post-settlement position can never disagree.
REDUCE_QTY = D(os.environ.get("ADR0043_REDUCE_QTY", "1"))

# How long the per-order settlement barrier may wait for the broker to reach terminal. Generous
# relative to a market order on a liquid name; a barrier that gives up early would produce a FALSE
# stop, and one that never gives up would hang the run past its budget.
SETTLEMENT_TIMEOUT_S = float(os.environ.get("ADR0043_SETTLEMENT_TIMEOUT_S", "45"))

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


# ---------------------------------------------------------------------------- redaction
# Evidence packages are archived, copied into review documents, and pasted into tickets. Anything
# that reaches them is effectively published, so the ONLY defence that survives careless handling is
# never writing the secret in the first place.
#
# Two rules, applied together:
#   * diagnostics record an exception's TYPE plus a bounded message — never the exception object,
#     never adapter configuration, never a request/response with headers attached;
#   * every serialized evidence blob passes through ``redact`` on the way out, so a future field
#     added without thinking about this cannot quietly leak.
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    # key=value / key: value forms for anything credential-shaped, quoted or bare.
    (re.compile(
        r"(?i)\b(api[-_ ]?key|secret[-_ ]?key|secret|token|password|passwd|pwd|authorization|"
        r"auth|bearer|credential|access[-_ ]?key)\b\s*[:=]\s*['\"]?[^\s'\",;}\)]+",
    ), r"\1=<redacted>"),
    # An Authorization header value on its own line.
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"), "Bearer <redacted>"),
    # Alpaca key ids are PK/AK-prefixed uppercase runs; the secret is a long mixed-case run that
    # follows the same shape as a key= value already handled above.
    (re.compile(r"\b(?:PK|AK)[A-Z0-9]{10,}\b"), "<redacted-key-id>"),
)


def redact(blob: str) -> str:
    """Strip credential-shaped material from text bound for the evidence package.

    Deliberately conservative: it does NOT touch hex digests (evidence integrity depends on them),
    ids, quantities, or status strings. It is the last line of defence, not the first — the first is
    not collecting the material at all."""
    for pattern, replacement in _REDACTIONS:
        blob = pattern.sub(replacement, blob)
    return blob


class BreachUnreachable(RuntimeError):
    """BREACH_SETUP_UNREACHABLE_UNDER_CURRENT_LIMITS — the account's own limits do not permit enough
    turnover to realise the loss. The answer is NOT to relax the limits (that is the bug this whole
    ADR exists to prevent)."""


class CanaryRefused(RuntimeError):
    """The harness refuses to run: a precondition for a VALID run is absent (wrong mode, no lock,
    missing legs). A refusal is a correct outcome — a run that assumes its preconditions is not."""


class CanaryStop(RuntimeError):
    """A HARD STOP mid-run, distinct from a refusal: the run began legitimately and then hit a
    condition that makes continuing unsafe rather than merely un-assertable. Carries a SPECIFIC
    ``stop_reason`` so the evidence names the failure instead of recording a generic canary FAIL.

    Nothing after a stop is attempted — the point of stopping is that the next step would act on a
    ledger the harness cannot vouch for."""

    def __init__(self, stop_reason: str, detail: str, diagnostics: dict[str, Any] | None = None):
        super().__init__(f"{stop_reason}: {detail}")
        self.stop_reason = stop_reason
        self.detail = detail
        self.diagnostics = diagnostics or {}


class SettlementBarrierFailed(CanaryStop):
    """``settle_order`` could not positively establish that an order is settled. The ledger for that
    order is UNRESOLVED, so no further order may be placed — this is the condition that, unnamed and
    unenforced, produced both Phase-0 SETUP failures."""

    def __init__(self, detail: str, diagnostics: dict[str, Any] | None = None):
        super().__init__("SETTLEMENT_BARRIER_FAILED", detail, diagnostics)


class LossMeasurementUnavailable(CanaryStop):
    """The authoritative session loss cannot be measured, so the run has no ruler.

    Every §5 terminal-range check and the §10 overshoot floor are expressed in this number. If it
    cannot be measured, those controls are not merely imprecise — they are absent, and the harness
    must stop rather than continue with a placeholder. See
    ``docs/incidents/ADR0043_Harness_AccountState_Missing_Defaults_To_Zero_20260724.md``.
    """


# ------------------------------------------------------------------- session loss measurement
# The ADR-0043 loss is `current equity − immutable current-session baseline equity`, which is the
# production mechanism this canary exists to prove. It is NOT `accounts_state.day_change`: that
# column is a cache of a broker field, refreshed by a sync sweep that may not run at all on the
# validation host, and reading it with a `or 0` default silently converted "no measurement" into
# "measured zero" — disarming both the breach observation and the overshoot floor.
LOSS_BASIS_SESSION_BASELINE = "SESSION_BASELINE"

# Named refusals. Each one names a specific way the measurement can be untrustworthy; none of them
# may be softened into a number.
STOP_ACCOUNT_STATE_ROW_MISSING = "ACCOUNT_STATE_ROW_MISSING"
STOP_CURRENT_EQUITY_UNAVAILABLE = "CURRENT_EQUITY_UNAVAILABLE"
STOP_SESSION_BASELINE_MISSING = "SESSION_BASELINE_MISSING"
STOP_SESSION_BASELINE_WRONG_SESSION = "SESSION_BASELINE_WRONG_SESSION"
STOP_SESSION_BASELINE_ACCOUNT_MISMATCH = "SESSION_BASELINE_ACCOUNT_MISMATCH"
STOP_SESSION_BASELINE_AFTER_FIRST_SUBMISSION = "SESSION_BASELINE_AFTER_FIRST_SUBMISSION"
STOP_SESSION_BASELINE_CONTRADICTORY = "SESSION_BASELINE_CONTRADICTORY"
STOP_NOT_A_TRADING_SESSION = "NOT_A_TRADING_SESSION"

_BASELINE_STATUS_ACTIVE = "ACTIVE"


def _utcnow() -> datetime:
    """The measurement clock, as a seam. The offline harness tests pin it to a fixed trading
    instant so their assertions do not depend on the day the suite happens to run."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class SessionLoss:
    """The measured session loss and the exact evidence it was derived from."""

    day_change: D
    equity: D
    baseline_equity: D
    baseline_id: int
    baseline_captured_at: str
    market_session_date: str
    basis: str = LOSS_BASIS_SESSION_BASELINE

    def as_dict(self) -> dict[str, Any]:
        return {
            "basis": self.basis,
            "day_change": str(self.day_change),
            "equity": str(self.equity),
            "baseline_equity": str(self.baseline_equity),
            "baseline_id": self.baseline_id,
            "baseline_captured_at": self.baseline_captured_at,
            "market_session_date": self.market_session_date,
        }


def broker_equity(adapter, *, attempts: int = 5, backoff_s: float = 0.5) -> D:
    """Live account equity from the broker, with bounded retries, or a named stop.

    Read from the broker on EVERY call rather than from `accounts_state`: the driver must see the
    account move as legs settle, and a cached row that no sweep is updating would hold the loss
    constant across the whole run — indistinguishable from "the churn is not working".

    5xx flaps against Alpaca are routine (§9 of the frozen plan), so a single failure is retried;
    exhausting the attempts is a stop, never a fallback value.
    """
    last_error: str | None = None
    for attempt in range(attempts):
        try:
            raw = adapter.get_account()
            value = (raw or {}).get("equity")
            if value is None or str(value) == "":
                last_error = "broker returned no equity field"
            else:
                return D(str(value))
        except Exception as exc:  # noqa: BLE001 — type + bounded message only (never the object)
            last_error = f"{type(exc).__name__}: {str(exc)[:200]}"
        if attempt < attempts - 1:
            time.sleep(backoff_s * (2**attempt))
    raise LossMeasurementUnavailable(
        STOP_CURRENT_EQUITY_UNAVAILABLE,
        f"could not read account equity from the broker in {attempts} attempts",
        {"last_error": last_error},
    )


def select_active_baseline(rows: list[dict[str, Any]], session_date: str) -> dict[str, Any]:
    """The one ACTIVE baseline for ``session_date``, or a named refusal.

    Pure, so the decision can be exercised directly. The unique constraint on
    ``(account_id, market_session_date)`` is the primary defence against two ACTIVE baselines; this
    is the second one, for a database that reaches the harness without it (a restore, a copy) — the
    ambiguity is refused rather than resolved by picking a row.
    """
    today = [r for r in rows if r["market_session_date"] == session_date]
    if not today:
        other = sorted({str(r["market_session_date"]) for r in rows})
        raise LossMeasurementUnavailable(
            STOP_SESSION_BASELINE_WRONG_SESSION if other else STOP_SESSION_BASELINE_MISSING,
            f"no baseline for session {session_date}"
            + (f"; the account holds baselines for {other} only" if other else ""),
            {"session_date": session_date, "baseline_session_dates": other},
        )
    active = [r for r in today if r["status"] == _BASELINE_STATUS_ACTIVE]
    if not active:
        raise LossMeasurementUnavailable(
            STOP_SESSION_BASELINE_MISSING,
            f"session {session_date} has baseline rows but none is ACTIVE",
            {"statuses": [r["status"] for r in today]},
        )
    if len(active) > 1:
        raise LossMeasurementUnavailable(
            STOP_SESSION_BASELINE_CONTRADICTORY,
            f"{len(active)} ACTIVE baselines for session {session_date}; the measurement is ambiguous",
            {"baseline_ids": [r["id"] for r in active]},
        )
    return active[0]


async def measure_session_loss(sf, adapter, *, now: datetime | None = None) -> SessionLoss:
    """`current equity − immutable current-session baseline equity`, or a named stop.

    Refuses — never returns a number — when the session is not a trading session, when the baseline
    is missing / belongs to another session / is contradictory / was captured after activity had
    already begun, or when current equity cannot be read.

    A baseline whose recorded equity is numerically ``0`` is PRESENT, not missing: the checks below
    test for absence with ``is None``, never for falsiness. That distinction is the whole defect.
    """
    from app.market.session import default_market_session
    from app.risk.loss_control.session_baseline import resolve_session_date

    now = now or _utcnow()
    session_date = resolve_session_date(now)
    if session_date is None:
        raise LossMeasurementUnavailable(
            STOP_NOT_A_TRADING_SESSION,
            "no ET trading session for the current instant; a session baseline cannot exist",
            {"now": now.isoformat()},
        )

    async with sf() as s:
        rows = [
            dict(r._mapping)
            for r in (
                await s.execute(
                    text(
                        "SELECT id, account_id, market_session_date, baseline_equity, captured_at, "
                        "status FROM risk_session_baselines WHERE account_id = :a"
                    ),
                    {"a": ACCT},
                )
            ).fetchall()
        ]
        account_user = (
            await s.execute(text("SELECT user_id FROM accounts WHERE id = :a"), {"a": ACCT})
        ).scalar()
        open_utc = default_market_session().classify(now).regular_open
        first_submission = (
            await s.execute(
                text(
                    "SELECT MIN(created_at) FROM orders "
                    "WHERE account_id = :a AND created_at >= :o"
                ),
                {"a": ACCT, "o": open_utc},
            )
        ).scalar()

    if account_user is None or int(account_user) != USER:
        raise LossMeasurementUnavailable(
            STOP_SESSION_BASELINE_ACCOUNT_MISMATCH,
            f"account {ACCT} does not belong to the configured canary user {USER}",
            {"account_user_id": account_user, "expected_user_id": USER},
        )

    row = select_active_baseline(rows, session_date)
    if int(row["account_id"]) != ACCT:
        raise LossMeasurementUnavailable(
            STOP_SESSION_BASELINE_ACCOUNT_MISMATCH,
            f"baseline {row['id']} belongs to account {row['account_id']}, not {ACCT}",
            {"baseline_account_id": row["account_id"], "expected_account_id": ACCT},
        )
    if row["baseline_equity"] is None:
        raise LossMeasurementUnavailable(
            STOP_SESSION_BASELINE_MISSING,
            f"baseline {row['id']} records no equity",
            {"baseline_id": row["id"]},
        )

    captured_at = str(row["captured_at"])
    if first_submission is not None and captured_at > str(first_submission):
        raise LossMeasurementUnavailable(
            STOP_SESSION_BASELINE_AFTER_FIRST_SUBMISSION,
            "the baseline was captured after this session's first order; it cannot describe the "
            "account as it stood before activity",
            {"captured_at": captured_at, "first_submission_at": str(first_submission)},
        )

    equity = broker_equity(adapter)
    baseline_equity = D(str(row["baseline_equity"]))
    return SessionLoss(
        day_change=equity - baseline_equity,
        equity=equity,
        baseline_equity=baseline_equity,
        baseline_id=int(row["id"]),
        baseline_captured_at=captured_at,
        market_session_date=session_date,
    )


# ---------------------------------------------------------------------------- state snapshot
@dataclass(frozen=True)
class StateSnapshot:
    """Recorded immediately before EVERY order, so no assertion has to ASSUME the lock was on. Unlike
    0042 this also captures the durable loss-control state — the property under test."""

    at: str
    #: `equity - baseline_equity`, measured through `measure_session_loss`. Never a default.
    day_change: D
    #: Live broker equity at the instant of this snapshot.
    equity: D
    #: From `accounts_state`, kept for evidence only — NOTHING derives the loss from it.
    last_equity: D | None
    #: The full provenance of `day_change`, carried into the evidence package.
    loss: SessionLoss
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
            "last_equity": str(self.last_equity) if self.last_equity is not None else None,
            "loss": self.loss.as_dict(),
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


async def snapshot_state(sf, adapter, *, now: datetime | None = None) -> StateSnapshot:
    """The pre-order record. Whether the loss-control lock is engaged is MEASURED, not inferred.

    The loss itself comes from ``measure_session_loss`` — live broker equity against the immutable
    session baseline — so it is re-read on every call and cannot sit constant while the book moves.
    ``accounts_state`` contributes only ``last_equity``, kept for evidence and used for nothing.

    Raises ``LossMeasurementUnavailable`` rather than returning a snapshot the run cannot trust: a
    missing ``accounts_state`` row, an absent or contradictory baseline, or an unreadable equity all
    stop the run with a named reason.
    """
    async with sf() as s:
        row = (
            await s.execute(
                text("SELECT last_equity FROM accounts_state WHERE account_id = :a"),
                {"a": ACCT},
            )
        ).mappings().first()
        if row is None:
            raise LossMeasurementUnavailable(
                STOP_ACCOUNT_STATE_ROW_MISSING,
                f"no accounts_state row for account {ACCT}; the account's live state is unknown",
                {"account_id": ACCT},
            )
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

    loss = await measure_session_loss(sf, adapter, now=now)
    cap_d = D(str(cap)) if cap is not None else None
    last_equity = row["last_equity"]
    return StateSnapshot(
        at=datetime.now(UTC).isoformat(),
        day_change=loss.day_change,
        equity=loss.equity,
        last_equity=D(str(last_equity)) if last_equity is not None else None,
        loss=loss,
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
# The ordered, side-effecting steps. Each is checkpointed BEFORE the next begins so a dropped SSH
# session resumes at the first incomplete step and NEVER re-runs a completed side effect (a second
# protected-leg SELL, a second rejected BUY, a second recovery request).
STEPS: tuple[str, ...] = ("A1", "A2", "A3", "A4", "A5")


@dataclass
class Checkpoint:
    """Durable, resumable, idempotent — a dropped SSH session must never leave the run indeterminate,
    re-run a completed side effect, or let a SECOND invocation race the first.

    ``steps`` records each completed step's durable outcome (order id, preflight id, …). On restart
    the run re-derives that step's assertion FROM the durable evidence rather than re-executing it."""

    phase: str = "INIT"
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    deadline_at: str = ""
    lock_reached: bool = False
    # A STABLE run id — the deterministic order/recovery identity that closes the
    # post-submit/pre-checkpoint crash window (a retry reuses the SAME broker client_order_id and the
    # SAME recovery key, so it can never create a second order or a second preflight).
    run_id: str = ""
    idempotency_key: str = ""
    completed_gate: str | None = None
    completed_digest: str | None = None
    steps: dict[str, Any] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls) -> Checkpoint:
        if CHECKPOINT.exists():
            return cls(**json.loads(CHECKPOINT.read_text(encoding="utf-8")))
        now = datetime.now(UTC)
        cp = cls()
        cp.deadline_at = (now + timedelta(minutes=BUDGET_MINUTES)).isoformat()
        cp.run_id = now.strftime("%Y%m%d%H%M%S")
        cp.idempotency_key = f"adr0043-canary-{cp.run_id}"
        cp.save()
        return cp

    def client_id(self, step: str) -> str:
        """The deterministic broker client_order_id for a side-effecting order step — stable across
        retries so the broker itself dedupes a re-submit."""
        return f"adr0043-{self.run_id}-{step.lower()}"

    def save(self) -> None:
        CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
        tmp = CHECKPOINT.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.__dict__, indent=2, default=str), encoding="utf-8")
        tmp.replace(CHECKPOINT)          # atomic — a torn checkpoint is worse than none

    def expired(self) -> bool:
        return datetime.now(UTC) >= datetime.fromisoformat(self.deadline_at)

    def step_done(self, name: str) -> bool:
        return bool(self.steps.get(name, {}).get("done"))

    def step_data(self, name: str) -> dict:
        return dict(self.steps.get(name, {}))

    def record_intent(self, name: str, **data: Any) -> None:
        """Record what a side-effecting step is ABOUT to do, durably, BEFORE it does it.

        The deterministic client id closes the "did I already submit?" window; this closes the
        "what was true before I submitted?" window. Without it a crash between submit and checkpoint
        leaves the resumed run unable to say what the position SHOULD settle to — and a resumed run
        that cannot verify its own arithmetic must refuse, not guess."""
        self.steps[f"{name}_intent"] = {**data, "at": datetime.now(UTC).isoformat()}
        self.save()

    def intent(self, name: str) -> dict:
        return dict(self.steps.get(f"{name}_intent", {}))

    def record_step(self, name: str, **data: Any) -> None:
        self.steps[name] = {**self.steps.get(name, {}), **data, "done": True,
                            "at": datetime.now(UTC).isoformat()}
        self.save()

    def all_done(self) -> bool:
        return all(self.step_done(s) for s in STEPS)

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
            "settlements": [],
            "assertions": [],
            "stop": None,
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

    def record_settlement(self, record: dict[str, Any]) -> None:
        """One settlement outcome — success or failure — bound into the evidence. A failed barrier
        is evidence too, and the more diagnostic the better: the whole reason Phase 0 burned two
        attempts is that "the order didn't settle" left no record of HOW it didn't settle."""
        self.doc["settlements"].append(record)

    def record_stop(self, stop_reason: str, detail: str, diagnostics: dict[str, Any]) -> None:
        self.doc["stop"] = {"stop_reason": stop_reason, "detail": detail,
                            "diagnostics": diagnostics,
                            "at": datetime.now(UTC).isoformat()}

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
        # Redact on the way OUT, so the digest covers exactly the bytes that were written and a
        # field added later without thinking about credentials still cannot leak one.
        blob = redact(json.dumps(self.doc, indent=2, default=str))
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


# ---------------------------------------------------------------------------- durable lookups (resume)
async def order_row(sf, order_id: int) -> dict | None:
    """The durable order a checkpointed step recorded — so a resumed step re-derives its assertion
    from the committed order rather than submitting again."""
    async with sf() as s:
        r = (
            await s.execute(
                text(
                    "SELECT id, account_id, symbol_id, side, status, rejection_reason "
                    "FROM orders WHERE id = :i"
                ),
                {"i": order_id},
            )
        ).mappings().first()
    return dict(r) if r else None


async def find_order_by_client_id(sf, adapter, client_id: str) -> dict | None:
    """Locate an order by its DETERMINISTIC client_order_id — the identity that closes the
    post-submit/pre-checkpoint crash window. Checks the durable LOCAL order first (the router
    persists it around submit), then the BROKER (in case the local write was the thing that was
    lost). Returns normalized {source, local_id, side, symbol, qty, status} or None."""
    async with sf() as s:
        r = (
            await s.execute(
                text(
                    "SELECT o.id, o.side, o.qty, o.status, sym.ticker AS symbol "
                    "FROM orders o JOIN symbols sym ON sym.id = o.symbol_id "
                    "WHERE o.account_id = :a AND o.client_order_id = :c ORDER BY o.id DESC"
                ),
                {"a": ACCT, "c": client_id},
            )
        ).mappings().first()
    if r:
        return {"source": "local", "local_id": r["id"], "side": str(r["side"]),
                "symbol": str(r["symbol"]), "qty": D(str(r["qty"])), "status": str(r["status"])}
    if adapter is not None:
        for o in (adapter.list_orders() or []):
            if str(o.get("client_order_id")) == client_id:
                return {"source": "broker", "local_id": None, "side": str(o.get("side")),
                        "symbol": str(o.get("symbol")), "qty": D(str(o.get("qty") or 0)),
                        "status": str(o.get("status"))}
    return None


def order_identity_matches(existing: dict, *, side: str, symbol: str, qty: D) -> bool:
    """Whether a found order's risk-bearing identity matches the step's intent."""
    return (
        str(existing["side"]).lower().endswith(side.lower())
        and str(existing["symbol"]).upper() == symbol.upper()
        and existing["qty"] == qty
    )


async def preflight_row(sf, preflight_id: int) -> dict | None:
    async with sf() as s:
        r = (
            await s.execute(
                text(
                    "SELECT id, account_id, status, aggregate_verdict, origin_state, "
                    "transition_event_id FROM risk_recovery_preflights WHERE id = :i"
                ),
                {"i": preflight_id},
            )
        ).mappings().first()
    return dict(r) if r else None


async def preflight_pass_check_count(sf, preflight_id: int) -> int:
    async with sf() as s:
        return int(
            (
                await s.execute(
                    text(
                        "SELECT COUNT(*) FROM risk_recovery_preflight_checks "
                        "WHERE preflight_id = :i AND status = 'PASS'"
                    ),
                    {"i": preflight_id},
                )
            ).scalar()
            or 0
        )


async def event_row(sf, event_id: int) -> dict | None:
    async with sf() as s:
        r = (
            await s.execute(
                text(
                    "SELECT id, to_state, from_state, requested_transition "
                    "FROM risk_control_events WHERE id = :i"
                ),
                {"i": event_id},
            )
        ).mappings().first()
    return dict(r) if r else None


# ---------------------------------------------------------------------------- settlement evidence
async def order_fill_summary(sf, order_id: int) -> dict[str, Any]:
    """What the LOCAL ledger has actually booked for one order — the figure every settlement
    assertion compares against, read from the durable rows rather than from the router's response."""
    async with sf() as s:
        r = (
            await s.execute(
                text(
                    "SELECT o.status, o.broker_order_id, o.terminal_at, "
                    "(SELECT COUNT(*) FROM fills f WHERE f.order_id = o.id) AS fill_count, "
                    "(SELECT COALESCE(SUM(f.qty), 0) FROM fills f WHERE f.order_id = o.id) AS qty, "
                    "(SELECT COALESCE(SUM(f.qty * f.price), 0) FROM fills f "
                    " WHERE f.order_id = o.id) AS notional "
                    "FROM orders o WHERE o.id = :i"
                ),
                {"i": order_id},
            )
        ).mappings().first()
    if r is None:
        return {"status": None, "broker_order_id": None, "terminal_at": None,
                "fill_count": 0, "filled_qty": D(0), "avg_price": None}
    qty = D(str(r["qty"] or 0))
    notional = D(str(r["notional"] or 0))
    return {
        "status": str(r["status"]),
        "broker_order_id": r["broker_order_id"],
        "terminal_at": str(r["terminal_at"]) if r["terminal_at"] else None,
        "fill_count": int(r["fill_count"] or 0),
        "filled_qty": qty,
        "avg_price": (notional / qty) if qty > 0 else None,
    }


def count_open_orders(adapter) -> int:
    """Open orders AT THE BROKER — the driver's "nothing is in flight" check. Public because the
    churn driver's per-leg invariants need it, not just the snapshot."""
    return _count_open(adapter)


async def held_reservation_count(sf) -> int:
    """HELD reservations across the whole ACCOUNT, not just one order. A leak anywhere consumes
    reducible capacity, and the driver must not place the next leg while one exists."""
    async with sf() as s:
        return int(
            (
                await s.execute(
                    text(
                        "SELECT COUNT(*) FROM risk_reservations "
                        "WHERE account_id = :a AND state = :st"
                    ),
                    {"a": ACCT, "st": RESERVATION_HELD},
                )
            ).scalar()
            or 0
        )


def limits_fingerprint(limits: Limits) -> str:
    """A stable digest of the EFFECTIVE limits. The driver freezes this before the first order and
    re-checks it after every leg: a limit that moves mid-run invalidates every sizing decision the
    run has already made, and "relax the limit to reach the breach" is the exact bug ADR 0043
    exists to prevent."""
    import hashlib

    blob = json.dumps(limits.as_dict(), sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


async def reservation_states_for(sf, order_id: int) -> list[str]:
    async with sf() as s:
        rows = (
            await s.execute(
                text("SELECT state FROM risk_reservations WHERE order_id = :i ORDER BY id"),
                {"i": order_id},
            )
        ).scalars().all()
    return [str(r) for r in rows]


async def local_position_qty(sf, ticker: str) -> D:
    async with sf() as s:
        q = (
            await s.execute(
                text(
                    "SELECT p.qty FROM positions p JOIN symbols sym ON sym.id = p.symbol_id "
                    "WHERE p.account_id = :a AND sym.ticker = :t"
                ),
                {"a": ACCT, "t": ticker},
            )
        ).scalar()
    return D(str(q)) if q is not None else D(0)


def broker_position_qty(adapter, ticker: str) -> D:
    for p in adapter.get_positions() or []:
        if str(p.get("symbol")).upper() == ticker.upper():
            return D(str(p.get("qty") or 0))
    return D(0)


async def settlement_diagnostics(
    sf, adapter, *, step: str, order_id: int | None, ticker: str,
    polls: int | None = None, elapsed_s: float | None = None,
    exception_category: str | None = None, detail: str | None = None,
) -> dict[str, Any]:
    """Everything needed to diagnose a settlement failure WITHOUT re-running it, and without leaking
    a credential — ids, statuses and quantities only. Best-effort and never raises: a diagnostic
    collector that can itself fail would destroy the evidence for the failure it is describing.

    Broker reads are attempted but recorded as ``UNAVAILABLE:<ExcType>`` when the broker is the very
    thing that is unreachable (the most likely cause of the failure being diagnosed)."""
    diag: dict[str, Any] = {
        "step": step,
        "stop_reason": "SETTLEMENT_BARRIER_FAILED",
        "local_order_id": order_id,
        "ticker": ticker,
        "polls": polls,
        "elapsed_s": round(elapsed_s, 3) if elapsed_s is not None else None,
        "exception_category": exception_category,
        # Bounded AND redacted: a broker exception message can carry a request line.
        "detail": redact((detail or "")[:400]),
        "at": datetime.now(UTC).isoformat(),
    }
    try:
        booked = await order_fill_summary(sf, order_id) if order_id else {}
        diag["local_order_status"] = booked.get("status")
        diag["broker_order_id"] = booked.get("broker_order_id")
        diag["local_filled_qty"] = str(booked.get("filled_qty", D(0)))
        diag["local_fill_count"] = booked.get("fill_count")
    except Exception as exc:  # noqa: BLE001 — diagnostics must never mask the failure
        diag["local_order_status"] = f"UNAVAILABLE:{type(exc).__name__}"
    try:
        diag["reservation_states"] = await reservation_states_for(sf, order_id) if order_id else []
    except Exception as exc:  # noqa: BLE001
        diag["reservation_states"] = [f"UNAVAILABLE:{type(exc).__name__}"]
    try:
        diag["local_position"] = str(await local_position_qty(sf, ticker))
    except Exception as exc:  # noqa: BLE001
        diag["local_position"] = f"UNAVAILABLE:{type(exc).__name__}"
    try:
        diag["broker_position"] = str(broker_position_qty(adapter, ticker))
    except Exception as exc:  # noqa: BLE001
        diag["broker_position"] = f"UNAVAILABLE:{type(exc).__name__}"
    bid = diag.get("broker_order_id")
    if bid:
        try:
            bo = adapter.get_order(str(bid)) or {}
            diag["broker_status"] = str(bo.get("status"))
            diag["broker_filled_qty"] = str(bo.get("filled_qty"))
        except Exception as exc:  # noqa: BLE001
            diag["broker_status"] = f"UNAVAILABLE:{type(exc).__name__}"
            diag["broker_filled_qty"] = None
    else:
        diag["broker_status"] = None
        diag["broker_filled_qty"] = None
    try:
        diag["loss_control_state"] = await current_loss_control_state(sf)
    except Exception as exc:  # noqa: BLE001
        diag["loss_control_state"] = f"UNAVAILABLE:{type(exc).__name__}"
    return diag


# ---------------------------------------------------------------------------- PURE settlement gates
def assess_a2_settlement(
    *, broker_status: str | None, local_status: str | None, fill_count: int, booked_qty: D,
    local_position: D, broker_position: D, expected_position: D,
    reservation_states: list[str], reduce_qty: D = REDUCE_QTY,
) -> tuple[bool, str]:
    """A2 is GREEN only when the reduction is SETTLED, not merely admitted.

    "The router returned ALLOW" says nothing about whether the share actually left the account —
    that gap is precisely what attempt 2 mistook for success. Every clause here is a fact read back
    from the ledger and the broker AFTER the barrier returned."""
    ok = (
        str(broker_status).lower() == "filled"
        # EXACTLY "filled" — an ``endswith`` here would silently accept PARTIALLY_FILLED, which is
        # the one local status that most looks settled and least is.
        and str(local_status).lower() == "filled"
        and fill_count == 1
        and booked_qty == reduce_qty
        and local_position == expected_position
        and broker_position == expected_position
        and RESERVATION_HELD not in reservation_states
    )
    return ok, (
        f"broker={broker_status} local={local_status} fills={fill_count} booked={booked_qty} "
        f"(expected {reduce_qty}) local_pos={local_position} broker_pos={broker_position} "
        f"(expected {expected_position}) reservations={reservation_states or '[]'}"
    )


def assess_a3_no_submission(
    *, rejected: bool, reason: str, broker_order_id: str | None, local_status: str | None,
    local_position: D, broker_position: D, expected_position: D, reservation_count: int,
) -> tuple[bool, str]:
    """A3 is GREEN only if the refusal reached NO broker at all.

    A refusal that still produced a broker order is not a refusal — it is an unnoticed order, which
    is a worse outcome than a failed canary."""
    ok = (
        rejected
        and "LOSS_CONTROL_STOP" in reason
        and not broker_order_id
        and str(local_status).lower().endswith("rejected")
        and local_position == expected_position
        and broker_position == expected_position
        and reservation_count == 0
    )
    return ok, (
        f"rejected={rejected} reason={reason or '-'} broker_order_id={broker_order_id or 'none'} "
        f"local_status={local_status} local_pos={local_position} broker_pos={broker_position} "
        f"(expected unchanged {expected_position}) reservations={reservation_count}"
    )


# ---------------------------------------------------------------------------- gating assertions
# Assertion names are EVIDENCE-SCHEMA FIELDS, not cosmetic strings: downstream verification reads
# the package and looks for these exact names, so a rename is a silent loss of a required check and
# a quiet removal is worse. The inventory is frozen here and pinned by a test, so an addition has to
# be deliberate and a removal fails loudly.
GATING_ASSERTIONS: frozenset[str] = frozenset({
    # --- canary (adr0043_canary_run) ---
    "A1.state_authoritative",
    "A2.verified_reduction_allowed",
    "A2.reduction_settled",
    "A2.admitted_as_verified_reduction",
    "A2.state_remains_reduction_only",
    "A3.new_risk_refused",
    "A3.no_broker_submission",
    "A3.refusal_is_auditable",
    "A4.reached_recovery_cooldown",
    "A5.evaluator_holds",
    "already_complete",
    # --- emitted by the governed seam, per step label ---
    "A2.settled",
    "A3.settled",
    "CHURN.settled",
    "CHURN.no_broker_submission",
    # --- Phase 0 churn driver ---
    "PHASE0.lock_established",
})


# ---------------------------------------------------------------------------- the submit seam
def _label(step: str) -> str:
    """The STEP a seam assertion belongs to, independent of the sub-step that produced it.

    Steps are named ``A2.reduce`` / ``A3.new_risk`` / ``CHURN.L3`` so the order record is precise,
    but the assertion the gate reads must stay ``A3.no_broker_submission`` whatever sub-step raised
    it — otherwise a rename of the sub-step silently renames a gating assertion."""
    return step.split(".", 1)[0]


@dataclass(frozen=True)
class GovernedOrder:
    """The outcome of one governed submission. ``settlement`` is non-None whenever the order
    reached the broker — that is the invariant, expressed as a return value."""

    step: str
    order: Any
    order_id: int | None
    broker_order_id: str | None
    status: str
    admitted: bool
    settlement: Any | None = None
    elapsed_s: float | None = None


class GovernedSubmitter:
    """The ONLY way an ADR-0043 harness may place an order.

    Attempt 2 of Phase 0 failed because a submit and its settlement were two separate decisions a
    caller had to remember to pair. Here they are one decision, and there are exactly two of them:

      * ``submit_and_settle`` — the order is EXPECTED to reach the broker. It returns only after the
        shared barrier has confirmed settlement. If the order is refused BEFORE the broker, nothing
        needs settling and that is recorded rather than silently treated as success.
      * ``submit_expecting_refusal`` — the order is expected to be REFUSED before the broker. It
        proves no broker order exists; if one does, it reconciles that order through the barrier and
        then STOPS, because a refusal that reached the broker is an unplanned live order.

    There is no third way. ``check_settlement_barrier.py`` proves at CI time that no ADR-0043 script
    calls ``router.submit`` or ``settle_order`` directly, so "forgot to settle" is not a mistake the
    harness can express.
    """

    def __init__(self, *, sf, adapter, router, consumer, evidence: Evidence,
                 checkpoint: Any = None, settle=None, timeout_s: float = SETTLEMENT_TIMEOUT_S):
        self.sf = sf
        self.ad = adapter
        self.router = router
        self.consumer = consumer
        self.ev = evidence
        self.cp = checkpoint
        self.timeout_s = timeout_s
        if settle is None:
            from app.orders.settlement import settle_order

            settle = settle_order
        self._settle_impl = settle

    # ---- the barrier ------------------------------------------------------------------
    async def settle_existing(self, *, step: str, order_id: int, ticker: str):
        """Settle an order this run did not just submit — the re-entry / rebind path. Same barrier,
        same evidence, same failure mode; only the submit is absent."""
        from app.orders.settlement import SettlementError

        started = time.monotonic()
        try:
            result = await self._settle_impl(
                self.sf, self.ad, self.consumer,
                order_id=order_id, ticker=ticker, timeout_s=self.timeout_s)
        except SettlementError as exc:
            diag = await settlement_diagnostics(
                self.sf, self.ad, step=step, order_id=order_id, ticker=ticker,
                elapsed_s=time.monotonic() - started,
                exception_category=type(exc).__name__, detail=str(exc))
            self.ev.record_settlement(diag)
            self.ev.assert_(f"{_label(step)}.settled", False,
                            f"barrier failed: {diag['detail']}")
            if self.cp is not None:
                self.cp.note("settlement_barrier_failed", **diag)
            raise SettlementBarrierFailed(redact(str(exc))[:300], diag) from exc
        elapsed = round(time.monotonic() - started, 3)
        record = {
            "step": step, "outcome": "SETTLED", "local_order_id": order_id, "ticker": ticker,
            "broker_status": result.broker_status, "local_status": result.local_status,
            "filled_qty": str(result.filled_qty), "local_position": str(result.local_position),
            "broker_position": str(result.broker_position), "polls": result.polls,
            "elapsed_s": elapsed,
        }
        self.ev.record_settlement(record)
        if self.cp is not None:
            self.cp.note("settled", **record)
        return result, elapsed

    # ---- the two sanctioned submissions ------------------------------------------------
    async def submit_and_settle(self, *, step: str, request: dict, order_req, ticker: str,
                                pre: StateSnapshot | None = None) -> GovernedOrder:
        o, order_id, broker_oid, status, admitted = await self._submit(step, request, order_req, pre)
        if not admitted or order_id is None:
            # Refused before the broker: there is nothing to settle, and pretending otherwise would
            # be the same lie in the opposite direction.
            return GovernedOrder(step, o, order_id, broker_oid, status, admitted=False)
        result, elapsed = await self.settle_existing(step=step, order_id=order_id, ticker=ticker)
        return GovernedOrder(step, o, order_id, broker_oid, status, admitted=True,
                             settlement=result, elapsed_s=elapsed)

    async def submit_expecting_refusal(self, *, step: str, request: dict, order_req,
                                       ticker: str) -> GovernedOrder:
        o, order_id, broker_oid, status, admitted = await self._submit(step, request, order_req)
        if not broker_oid:
            return GovernedOrder(step, o, order_id, broker_oid, status, admitted=admitted)

        self.ev.assert_(
            f"{_label(step)}.no_broker_submission", False,
            f"a broker order {broker_oid} exists for a step that must never reach the broker")
        diag: dict[str, Any] = {"reconciled": None, "broker_order_id": broker_oid}
        if order_id is not None:
            try:
                await self.settle_existing(step=f"{step}.unexpected", order_id=int(order_id),
                                           ticker=ticker)
                diag["reconciled"] = "SETTLED"
            except SettlementBarrierFailed as stop:
                diag = {**stop.diagnostics, "reconciled": "UNRESOLVED"}
        raise CanaryStop(
            f"{_label(step)}_UNEXPECTED_BROKER_SUBMISSION",
            f"{step} produced broker order {broker_oid}; the account now carries an unplanned "
            f"order. The run stops here.", diag)

    async def _submit(self, step, request, order_req, pre: StateSnapshot | None = None):
        pre = pre or await snapshot_state(self.sf, self.ad)
        o = await self.router.submit(order_req)
        self.ev.record_order(step=step, snapshot=pre, request=request, response=o)
        status = str(getattr(o, "status", "") or "")
        return (
            o,
            getattr(o, "id", None),
            getattr(o, "broker_order_id", None),
            status,
            not status.lower().endswith("rejected"),
        )


async def current_loss_control_state(sf) -> str | None:
    async with sf() as s:
        return (
            await s.execute(
                text("SELECT state FROM risk_loss_control_state WHERE account_id = :a"),
                {"a": ACCT},
            )
        ).scalar()


async def saw_state_since(sf, state: str, since_id: int) -> bool:
    """Did any control event since ``since_id`` transition the account INTO ``state``? Used to prove
    the account never touched NORMAL, and no COOLDOWN_COMPLETE fired, during the run."""
    return any(e["to_state"] == state for e in await control_events_for(sf, since_id=since_id))


# ---------------------------------------------------------------------------- PURE gate assessment
# Extracted so the harness-honesty tests can prove every failure mode is RED, offline. A live GREEN
# is only legitimate when reaching RECOVERY_COOLDOWN is MANDATORY — a preflight FAIL/INCOMPLETE, or an
# evaluator that re-arms/regresses, is a RED canary, not a vacuous pass.

# The expected count of preflight checks — all must PASS to enter cooldown.
PREFLIGHT_CHECK_COUNT = 12


def assess_a4(
    *, accepted: bool, aggregate_verdict: str | None, resulting_state: str | None,
    has_preflight_pass_event: bool, parent_status: str | None, pass_check_count: int,
) -> tuple[bool, str]:
    """A4 is GREEN only if the recovery drove the account all the way into RECOVERY_COOLDOWN with a
    full PASS: accepted, aggregate PASS, resulting state cooldown, a committed PREFLIGHT_PASS event,
    the parent preflight PASSED, and exactly 12 persisted PASS checks."""
    ok = (
        accepted
        and aggregate_verdict == "PASS"
        and resulting_state == STATE_RECOVERY_COOLDOWN
        and has_preflight_pass_event
        and parent_status == "PASSED"
        and pass_check_count == PREFLIGHT_CHECK_COUNT
    )
    return ok, (
        f"accepted={accepted} verdict={aggregate_verdict} state={resulting_state} "
        f"pass_event={has_preflight_pass_event} parent={parent_status} "
        f"pass_checks={pass_check_count}/{PREFLIGHT_CHECK_COUNT}"
    )


def assess_a5(
    *, evaluator_called: bool, verdict: str | None, transitioned_to: str | None,
    current_state: str | None, saw_normal: bool, saw_cooldown_complete: bool,
) -> tuple[bool, str]:
    """A5 is GREEN only if the evaluator was actually invoked and HELD: verdict exactly HOLD, no
    transition, the account still in RECOVERY_COOLDOWN, and NORMAL / COOLDOWN_COMPLETE reached at NO
    point in the run. A NO_OP, a regress to INTEGRITY_STOP, or a re-arm to NORMAL is RED."""
    ok = (
        evaluator_called
        and verdict == "HOLD"
        and transitioned_to is None
        and current_state == STATE_RECOVERY_COOLDOWN
        and not saw_normal
        and not saw_cooldown_complete
    )
    return ok, (
        f"called={evaluator_called} verdict={verdict} transitioned_to={transitioned_to} "
        f"state={current_state} saw_normal={saw_normal} saw_cooldown_complete={saw_cooldown_complete}"
    )
