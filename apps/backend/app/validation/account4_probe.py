"""Authoritative Account-4 probe (R5c-2b) — evidence that the live book is paused, held and untouched.

The forward validation must never draw capital, prices, positions, orders or ledger state from Account 4.
Account 4 appears in the record for one reason only: to EVIDENCE that it was safely paused and held
while the session ran, and that it did not move during it. Every field here is a live read of the
governed application database, opened READ-ONLY.

## There is no PAUSED status, so none is invented

`StrategyStatus` defines `idle | backtest | paper | pending_live | live | halted | error | paper_variant`.
"Paused and held" is not a status — it is the conjunction the platform actually encodes:

    raw status in GOVERNED_NON_RUNNING_STATUSES
    AND operational_hold exists, schema-valid, status ACTIVE
    AND the hold carries a recognized reason code and a revision

The raw status is recorded verbatim; the safety verdict is DERIVED beside it, never substituted for it.
A non-running status without an active hold fails. An active hold over a running or transitional status
fails. Only `idle` + ACTIVE hold passes.

`GOVERNED_NON_RUNNING_STATUSES` is deliberately narrow — the single status this schema defines as
incapable of executing and not transitional. `backtest` (working), `pending_live` (cooldown, transitional),
`halted` (degraded), `error`, and every running status fail closed, as does any status this module has
never seen. A future status is refused until it is adjudicated, never accepted by default.

## Pre-decision and pre-commit probes must be identical

A hold cleared, a strategy resumed, an order appearing or a position moving between the two probes means
the operational state changed under the run: the session stops even when each probe looks safe on its own.
`comparison_digest` covers exactly the compared fields, and a revision change alone is enough to stop.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.validation.forward_window import ACCOUNT_4_ID, IntegrityStop

# The ONLY statuses this schema defines as incapable of executing and not transitional.
#   idle          -> registered, not dispatched, not engine-runnable
# Everything else fails closed, and for reasons worth stating:
#   paper/live/paper_variant -> engine-runnable (ENGINE_RUNNABLE_STATUSES)
#   pending_live             -> transitional: the activation cooldown, one scheduler tick from LIVE
#   backtest                 -> actively working
#   halted / error           -> degraded; the reason is unadjudicated here
GOVERNED_NON_RUNNING_STATUSES = frozenset({"idle"})

# Non-terminal order states: an order in any of these can still reach the broker.
OPEN_ORDER_STATUSES = ("pending_risk", "pending_submit", "submitted", "partially_filled")

HOLD_STATE_KEY = "operational_hold"
HOLD_SCHEMA_VERSION = 1
RECOGNIZED_HOLD_REASON_CODES = frozenset({
    "AWAITING_PRODUCTION_SIZING_VALIDATION",
    "AWAITING_COLD_START_FIX",
    "OPERATOR_HOLD",
})

# The fields the pre-decision and pre-commit probes must agree on.
COMPARED_FIELDS = (
    "account_id", "broker", "broker_mode", "raw_strategy_status", "hold_status",
    "hold_reason_code", "hold_rev", "positions_digest", "open_order_count",
)


class Account4ProbeError(IntegrityStop):
    """The live Account-4 state could not be read, or contradicts the safety condition. Fails closed:
    a session never runs on an assumption about the live book."""


@dataclass(frozen=True)
class Account4Probe:
    """One authoritative live read. Raw facts first, derived verdicts beside them."""
    probed_at: str
    account_id: int
    broker: str
    broker_mode: str
    account_label: str | None
    strategy_id: int
    raw_strategy_status: str
    hold_present: bool
    hold_schema_version: int | None
    hold_status: str | None
    hold_reason_code: str | None
    hold_rev: int | None
    positions_count: int
    positions_digest: str
    open_order_count: int
    # derived — never a substitute for the raw values above
    strategy_non_running: bool
    account4_operational_hold_active: bool
    account4_is_safely_paused_and_held: bool
    comparison_digest: str

    def to_open_provenance(self) -> dict[str, Any]:
        return asdict(self)

    def to_commit_probe(self) -> Any:
        """The commit protocol's own before/after probe value, built from THIS authoritative read so the
        two bindings cannot disagree about what the live book was."""
        from app.validation.observation_store import Account4StateProbe

        return Account4StateProbe(
            hold_status=str(self.hold_status or "ABSENT"),
            hold_reason_code=str(self.hold_reason_code or "ABSENT"),
            hold_rev=int(self.hold_rev if self.hold_rev is not None else -1),
            strategy_status=self.raw_strategy_status,
            positions_sha256=self.positions_digest,
        )


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _normalized_qty(raw: Any) -> str:
    """Quantity rendered canonically so the digest is stable across storage forms (1, 1.0, 1.00)."""
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise Account4ProbeError(f"position quantity {raw!r} is not a number") from exc
    normalized = value.normalize()
    return format(normalized if normalized != 0 else Decimal(0), "f")


def positions_digest(rows: list[tuple[str, str | None, Any]]) -> str:
    """A digest over normalized (symbol, side, quantity) ONLY.

    Market value is deliberately absent: it moves with prices, so a digest including it would report
    the book as changed on every tick and could never evidence that Account 4 stood still.
    """
    normalized = sorted(
        (str(symbol).upper(), str(side or "long").lower(), _normalized_qty(qty))
        for symbol, side, qty in rows)
    return _digest(normalized)


def probe_account4(
    db_path: Path | str,
    *,
    strategy_id: int,
    expected_broker: str,
    expected_broker_mode: str,
    account_id: int = ACCOUNT_4_ID,
) -> Account4Probe:
    """Read the live Account-4 state and return the evidence, or fail closed.

    Read-only by construction (`file:…?mode=ro`): this function cannot write to the application database
    even if it were asked to. Any unavailable or contradictory field raises.
    """
    path = Path(db_path)
    if not path.is_file():
        raise Account4ProbeError(f"the application database {path} does not exist")
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise Account4ProbeError(f"the application database could not be opened read-only: {exc}") from exc

    try:
        account = _one(con, "SELECT id, broker, mode, label FROM accounts WHERE id = ?", [account_id],
                       what=f"account {account_id}")
        if int(account[0]) != ACCOUNT_4_ID:
            raise Account4ProbeError(
                f"the probe read account {account[0]}, not Account {ACCOUNT_4_ID}")
        broker, broker_mode, label = str(account[1]), str(account[2]), account[3]
        if broker.lower() != expected_broker.lower() or broker_mode.lower() != expected_broker_mode.lower():
            raise Account4ProbeError(
                f"Account {ACCOUNT_4_ID} is registered as {broker}/{broker_mode}, but this deployment "
                f"expects {expected_broker}/{expected_broker_mode}")

        strategy = _one(con, "SELECT id, status FROM strategies WHERE id = ?", [strategy_id],
                        what=f"strategy {strategy_id}")
        raw_status = str(strategy[1] or "").strip().lower()
        if not raw_status:
            raise Account4ProbeError(f"strategy {strategy_id} has no status recorded")
        non_running = raw_status in GOVERNED_NON_RUNNING_STATUSES

        hold_row = con.execute(
            "SELECT value FROM strategy_state WHERE strategy_id = ? AND key = ?",
            [strategy_id, HOLD_STATE_KEY]).fetchone()
        hold = _parse_hold(hold_row[0] if hold_row else None, strategy_id)

        position_rows = con.execute(
            "SELECT s.ticker, p.side, p.qty FROM positions p JOIN symbols s ON s.id = p.symbol_id "
            "WHERE p.account_id = ?", [account_id]).fetchall()
        digest = positions_digest([(r[0], r[1], r[2]) for r in position_rows])

        placeholders = ",".join("?" * len(OPEN_ORDER_STATUSES))
        open_orders = con.execute(
            f"SELECT COUNT(*) FROM orders WHERE account_id = ? AND status IN ({placeholders})",
            [account_id, *OPEN_ORDER_STATUSES]).fetchone()
        open_order_count = int(open_orders[0]) if open_orders else 0
    except sqlite3.Error as exc:
        raise Account4ProbeError(f"the live Account-4 read failed: {exc}") from exc
    finally:
        con.close()

    hold_active = bool(hold["present"] and hold["status"] == "ACTIVE")
    safely_held = bool(non_running and hold_active
                       and hold["reason_code"] in RECOGNIZED_HOLD_REASON_CODES
                       and hold["rev"] is not None)

    compared = {
        "account_id": account_id, "broker": broker, "broker_mode": broker_mode,
        "raw_strategy_status": raw_status, "hold_status": hold["status"],
        "hold_reason_code": hold["reason_code"], "hold_rev": hold["rev"],
        "positions_digest": digest, "open_order_count": open_order_count,
    }
    probe = Account4Probe(
        probed_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        account_id=account_id, broker=broker, broker_mode=broker_mode,
        account_label=str(label) if label is not None else None,
        strategy_id=strategy_id, raw_strategy_status=raw_status,
        hold_present=bool(hold["present"]), hold_schema_version=hold["schema_version"],
        hold_status=hold["status"], hold_reason_code=hold["reason_code"], hold_rev=hold["rev"],
        positions_count=len(position_rows), positions_digest=digest,
        open_order_count=open_order_count,
        strategy_non_running=non_running, account4_operational_hold_active=hold_active,
        account4_is_safely_paused_and_held=safely_held,
        comparison_digest=_digest(compared))

    _assert_safe(probe)
    return probe


def _assert_safe(probe: Account4Probe) -> None:
    """Refuse anything short of `idle` + a schema-valid ACTIVE hold with a recognized reason and a
    revision, and refuse any open order on the live book."""
    if not probe.strategy_non_running:
        raise Account4ProbeError(
            f"strategy {probe.strategy_id} status {probe.raw_strategy_status!r} is not in the governed "
            f"non-running set {sorted(GOVERNED_NON_RUNNING_STATUSES)} — the live book may execute")
    if not probe.hold_present:
        raise Account4ProbeError(
            f"strategy {probe.strategy_id} carries no operational hold; a non-running status alone does "
            f"not evidence a held book")
    if probe.hold_schema_version != HOLD_SCHEMA_VERSION:
        raise Account4ProbeError(
            f"the operational hold is schema version {probe.hold_schema_version!r}, not "
            f"{HOLD_SCHEMA_VERSION} — it cannot be read as a governed hold")
    if probe.hold_status != "ACTIVE":
        raise Account4ProbeError(
            f"the operational hold is {probe.hold_status!r}, not ACTIVE")
    if probe.hold_reason_code not in RECOGNIZED_HOLD_REASON_CODES:
        raise Account4ProbeError(
            f"the operational hold reason {probe.hold_reason_code!r} is not a recognized governed "
            f"reason code")
    if probe.hold_rev is None:
        raise Account4ProbeError("the operational hold carries no revision")
    if probe.open_order_count:
        raise Account4ProbeError(
            f"Account {probe.account_id} has {probe.open_order_count} open order(s); a held book must "
            f"have none in flight")
    if not probe.account4_is_safely_paused_and_held:      # pragma: no cover - defensive
        raise Account4ProbeError("the derived safety verdict is false")


def _parse_hold(raw: Any, strategy_id: int) -> dict[str, Any]:
    """Read the hold blob fail-closed: absent is absent, malformed is a refusal (never 'no hold')."""
    if raw is None:
        return {"present": False, "schema_version": None, "status": None, "reason_code": None,
                "rev": None}
    try:
        blob = json.loads(raw) if isinstance(raw, str | bytes) else dict(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise Account4ProbeError(
            f"strategy {strategy_id}'s operational hold is unreadable: {exc}") from exc
    if not isinstance(blob, dict):
        raise Account4ProbeError(f"strategy {strategy_id}'s operational hold is not an object")
    rev = blob.get("_rev")
    return {
        "present": True,
        "schema_version": blob.get("schema_version"),
        "status": str(blob["status"]).upper() if blob.get("status") is not None else None,
        "reason_code": blob.get("reason_code"),
        "rev": int(rev) if isinstance(rev, int) else None,
    }


def assert_account4_unchanged(before: Account4Probe, after: Account4Probe) -> None:
    """Require the pre-decision and pre-commit probes to describe the same live state.

    Both probes independently passing is not enough: a hold cleared and re-placed, a revision bump, an
    order appearing or a position moving between them all mean the operational state shifted under the
    run. A revision change alone stops the session.
    """
    if before.comparison_digest == after.comparison_digest:
        return
    changed = [f for f in COMPARED_FIELDS if getattr(before, f) != getattr(after, f)]
    detail = ", ".join(f"{f}: {getattr(before, f)!r} → {getattr(after, f)!r}" for f in changed)
    raise Account4ProbeError(
        f"Account {before.account_id}'s operational state changed during the session ({detail or 'a '
        'compared field moved'}) — the session stops even though each probe was individually safe")


def _one(con: sqlite3.Connection, sql: str, params: list, *, what: str) -> tuple:
    row = con.execute(sql, params).fetchone()
    if row is None:
        raise Account4ProbeError(f"{what} is not present in the application database")
    return tuple(row)
