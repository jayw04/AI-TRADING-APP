"""ADR 0043 Phase-0 — the account-3 loss-control state bootstrap.

WHY THIS EXISTS AT ALL
----------------------
Phase-0 attempt 1 (2026-07-28) stopped at leg 0 with ``LOSS_CONTROL_STOP``: the order gate reads the
durable loss-control state via ``LossControlService.load_state_row`` — which deliberately NEVER
bootstraps — and an absent row is an ``INTEGRITY_STOP`` in ENFORCE mode. That is the control working.
The canary account was provisioned (user/account scaffold, credentials, limits row, ``accounts_state``
scoped sync) without the one row the enforcement gate requires: ``risk_loss_control_state``.

Explicit initialization is ``LossControlService.get_state_row`` — the race-safe
``INSERT ... ON CONFLICT DO NOTHING`` bootstrap the service itself provides — performed deliberately
BEFORE enforcement traffic, never inside an order decision. This tool is that deliberate act, for
exactly one account, under the same structural narrowness as the scoped sync:

  1. the target is user 3 / account 3, frozen as constants — never read from the environment;
  2. the broker identity is verified to be ``PA34USW0Q8UO`` (and ``PA3QRX9KSPXA`` refused by name)
     through the shared read-only adapter before any write;
  3. the ONLY row this tool creates is account 3's ``risk_loss_control_state`` row, through the
     service's own bootstrap — never ad-hoc SQL;
  4. a row that already exists — in ANY state — is a refusal, not an idempotent no-op: this tool's
     mandate is first provisioning, and finding prior state means the world changed since review;
  5. a bootstrap is NOT a state transition: no ``risk_control_events`` row is fabricated, no
     NORMAL -> NORMAL transition is requested. The governance record is a typed ``audit_log`` entry
     (``LOSS_CONTROL_STATE_BOOTSTRAPPED``) that says what it is;
  6. no ``BrokerRegistry`` / ``load_all`` — the adapter factory decrypts user 3's credentials and
     nothing else (attempt 1 showed ``load_all`` touches account 1's credential metadata);
  7. evidence is written atomically on success AND on refusal, with before/after row state and the
     side-effect counters (control events, orders, HELD reservations, baselines, account-1
     loss-control row) proven unchanged.

Writes require ``--commit``. The default is a dry run that performs every read and every check and
reports the exact row it would create.

⚠ RUNTIME IS AWS. This runs on the ADR-0043 validation host against the frozen acct-3 rig, once,
under an approved execution package. It is not a general-purpose bootstrap tool.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.audit.logger import AuditAction, AuditActorType, AuditLogger
from app.risk.loss_control import constants as lc_constants
from app.risk.loss_control.service import LossControlService

# The shared refusal family, read-only broker view and atomic writer — one allowlist to audit
# across the ADR-0043 tooling, and one ``code``/``detail``/``diagnostics`` shape.
from scripts.adr0043_scoped_sync import (
    ScopedSyncRefused,
    assess_broker_identity,
    build_scoped_adapter,
    verify_account_row,
)
from scripts.adr0043_session_open import (
    REFUSE_BROKER_IDENTITY,
    ReadOnlyBrokerView,
    SessionOpenRefused,
    write_package_atomically,
)

# ---------------------------------------------------------------------------- the frozen target
# Constants, never environment reads — the tests assert the module consults no environment at all.
BOOTSTRAP_USER_ID = 3
BOOTSTRAP_ACCOUNT_ID = 3

# The exact row the service bootstrap must produce. Anything else is a refusal.
EXPECTED_STATE = lc_constants.STATE_NORMAL
EXPECTED_STATE_VERSION = 0
EXPECTED_LAST_SEQUENCE_NO = 0
EXPECTED_CONTROL_VERSION = lc_constants.LOSS_CONTROL_STATE_VERSION

# The governance record. It describes a provisioning act — it must not impersonate a state-machine
# transition, which is why it is an audit action and not a ``risk_control_events`` row.
AUDIT_ACTION = AuditAction.LOSS_CONTROL_STATE_BOOTSTRAPPED
AUDIT_REASON = "ADR0043_CANARY_PROVISIONING"
AUDIT_AUTHORITY = "reviewed bootstrap tool + approved execution package"

REFUSE_ROW_EXISTS = "LOSS_CONTROL_STATE_ALREADY_PRESENT"
REFUSE_UNPROTECTED_ADAPTER = "BOOTSTRAP_ADAPTER_NOT_READ_ONLY"
REFUSE_BOOTSTRAP_RESULT = "BOOTSTRAP_RESULT_UNEXPECTED"
REFUSE_SIDE_EFFECT = "BOOTSTRAP_SIDE_EFFECT_DETECTED"


class BootstrapRefused(ScopedSyncRefused):
    """A precondition for a VALID bootstrap is absent, so nothing (more) was written.

    Subclasses the scoped-sync refusal (itself a ``SessionOpenRefused``) so the whole ADR-0043
    tool family shares one refusal shape while remaining separately catchable.
    """


# ---------------------------------------------------------------------------- reads


async def read_loss_control_row(sf, account_id: int) -> dict[str, Any] | None:
    """The durable state row as persisted — the exact thing the enforcement gate reads."""
    async with sf() as s:
        row = (
            await s.execute(
                text(
                    "SELECT account_id, state, state_version, last_sequence_no, control_version, "
                    "updated_at FROM risk_loss_control_state WHERE account_id = :a"
                ),
                {"a": account_id},
            )
        ).mappings().first()
    return {k: str(v) if k == "updated_at" else v for k, v in dict(row).items()} if row else None


async def side_effect_counters(sf) -> dict[str, Any]:
    """Everything the bootstrap must NOT change, counted before and after.

    The account-1 loss-control row is included verbatim: reading that single row (and nothing else
    of account 1's) is the sanctioned proof that the bootstrap left it untouched.
    """
    async with sf() as s:
        counters = {
            "risk_control_events_total": (
                await s.execute(text("SELECT COUNT(*) FROM risk_control_events"))
            ).scalar()
            or 0,
            "orders_total": (await s.execute(text("SELECT COUNT(*) FROM orders"))).scalar() or 0,
            "held_reservations_total": (
                await s.execute(
                    text("SELECT COUNT(*) FROM risk_reservations WHERE state = 'HELD'")
                )
            ).scalar()
            or 0,
            "session_baselines_total": (
                await s.execute(text("SELECT COUNT(*) FROM risk_session_baselines"))
            ).scalar()
            or 0,
            "audit_log_total": (await s.execute(text("SELECT COUNT(*) FROM audit_log"))).scalar()
            or 0,
        }
    counters["account1_loss_control_row"] = await read_loss_control_row(sf, 1)
    return counters


def assess_bootstrap_row(row: dict[str, Any] | None) -> tuple[bool, str]:
    """Does the persisted row match the exact frozen expectation? Pure, so every branch is a test."""
    if row is None:
        return False, "no risk_loss_control_state row exists after the service bootstrap"
    mismatches = [
        f"{field}={row.get(field)!r} (expected {expected!r})"
        for field, expected in (
            ("state", EXPECTED_STATE),
            ("state_version", EXPECTED_STATE_VERSION),
            ("last_sequence_no", EXPECTED_LAST_SEQUENCE_NO),
            ("control_version", EXPECTED_CONTROL_VERSION),
        )
        if row.get(field) != expected
    ]
    if mismatches:
        return False, "bootstrapped row does not match the frozen expectation: " + "; ".join(
            mismatches
        )
    return True, (
        f"state={row['state']} state_version={row['state_version']} "
        f"last_sequence_no={row['last_sequence_no']} control_version={row['control_version']}"
    )


def assess_side_effects(
    before: dict[str, Any], after: dict[str, Any], *, committed: bool
) -> tuple[bool, list[str]]:
    """Nothing but the bootstrap row (and, on commit, exactly one audit record) may change."""
    problems = []
    for key in (
        "risk_control_events_total",
        "orders_total",
        "held_reservations_total",
        "session_baselines_total",
    ):
        if before[key] != after[key]:
            problems.append(f"{key} changed {before[key]} -> {after[key]}")
    expected_audit_delta = 1 if committed else 0
    delta = after["audit_log_total"] - before["audit_log_total"]
    if delta != expected_audit_delta:
        problems.append(
            f"audit_log_total delta {delta} (expected exactly {expected_audit_delta})"
        )
    if before["account1_loss_control_row"] != after["account1_loss_control_row"]:
        problems.append("account 1 loss-control row changed")
    return (not problems), problems


# ---------------------------------------------------------------------------- the bootstrap


async def bootstrap_loss_control(
    *, sf, adapter_factory, commit: bool, out: Path | None = None
) -> dict[str, Any]:
    """Perform the bootstrap. A refusal still writes the evidence file — the checks that DID pass
    are part of the record."""
    evidence: dict[str, Any] = {}
    try:
        return await _bootstrap(
            sf=sf, adapter_factory=adapter_factory, commit=commit, out=out, evidence=evidence
        )
    except SessionOpenRefused as exc:
        evidence["outcome"] = "REFUSED"
        evidence["refusal"] = str(exc)
        evidence["refusal_code"] = exc.code
        evidence["refusal_diagnostics"] = exc.diagnostics
        evidence["finished_at"] = datetime.now(UTC).isoformat()
        _write_evidence(evidence, out)
        raise


def _write_evidence(evidence: dict[str, Any], out: Path | None) -> None:
    if out is None:
        return
    write_package_atomically(evidence, out)
    print(f"evidence -> {out}", flush=True)


async def _bootstrap(
    *, sf, adapter_factory, commit: bool, out: Path | None, evidence: dict[str, Any]
) -> dict[str, Any]:
    evidence.update(
        {
            "tool": "adr0043_bootstrap_loss_control",
            "started_at": datetime.now(UTC).isoformat(),
            "target": {
                "user_id": BOOTSTRAP_USER_ID,
                "account_id": BOOTSTRAP_ACCOUNT_ID,
                "expected_row": {
                    "state": EXPECTED_STATE,
                    "state_version": EXPECTED_STATE_VERSION,
                    "last_sequence_no": EXPECTED_LAST_SEQUENCE_NO,
                    "control_version": EXPECTED_CONTROL_VERSION,
                },
            },
            "mode": "COMMIT" if commit else "DRY_RUN",
            "checks": [],
            "outcome": None,
        }
    )

    def check(name: str, ok: bool, detail: str) -> bool:
        evidence["checks"].append(
            {"name": name, "result": "PASS" if ok else "FAIL", "detail": detail}
        )
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
        return ok

    print(
        f"ADR-0043 loss-control bootstrap — target user={BOOTSTRAP_USER_ID} "
        f"account={BOOTSTRAP_ACCOUNT_ID} mode={evidence['mode']}",
        flush=True,
    )

    row = await verify_account_row(sf)
    check(
        "account_row_binding",
        True,
        f"accounts id={row['id']} user_id={row['user_id']} mode={row['mode']}",
    )

    before_row = await read_loss_control_row(sf, BOOTSTRAP_ACCOUNT_ID)
    evidence["before_row"] = before_row
    if before_row is not None:
        detail = (
            f"a risk_loss_control_state row already exists for account {BOOTSTRAP_ACCOUNT_ID} "
            f"(state={before_row['state']!r}, state_version={before_row['state_version']}); "
            f"this tool performs FIRST provisioning only. Prior state is a finding to "
            f"investigate, never something to overwrite."
        )
        check("no_existing_row", False, detail)
        raise BootstrapRefused(REFUSE_ROW_EXISTS, detail, {"existing_row": before_row})
    check("no_existing_row", True, "account 3 has no risk_loss_control_state row")

    evidence["counters_before"] = before_counters = await side_effect_counters(sf)

    broker = await adapter_factory(sf)
    if not isinstance(broker, ReadOnlyBrokerView):
        raise BootstrapRefused(
            REFUSE_UNPROTECTED_ADAPTER,
            "the adapter factory must return a ReadOnlyBrokerView",
            {"observed_type": type(broker).__name__},
        )
    raw_account = await asyncio.to_thread(broker.get_account)
    ok, detail = assess_broker_identity(raw_account.get("account_number"))
    if not check("broker_identity", ok, detail):
        raise BootstrapRefused(
            REFUSE_BROKER_IDENTITY, detail, {"observed": raw_account.get("account_number")}
        )
    evidence["broker_calls"] = list(broker.calls)

    if not commit:
        evidence["would_bootstrap"] = dict(evidence["target"]["expected_row"])
        evidence["outcome"] = "DRY_RUN_NO_WRITE"
        evidence["finished_at"] = datetime.now(UTC).isoformat()
        _write_evidence(evidence, out)
        print(f"outcome: {evidence['outcome']}", flush=True)
        return evidence

    # THE write: the service's own race-safe bootstrap, never ad-hoc SQL. get_state_row commits.
    async with sf() as s:
        await LossControlService(s).get_state_row(BOOTSTRAP_ACCOUNT_ID)

    # Verified from a FRESH read of what was actually persisted, not from the returned object.
    after_row = await read_loss_control_row(sf, BOOTSTRAP_ACCOUNT_ID)
    evidence["after_row"] = after_row
    ok, detail = assess_bootstrap_row(after_row)
    if not check("bootstrapped_row", ok, detail):
        raise BootstrapRefused(REFUSE_BOOTSTRAP_RESULT, detail, {"after_row": after_row})

    # The governance record — an audit entry describing a provisioning act, NOT a fabricated
    # NORMAL -> NORMAL transition. The hash chain extends via the model's insert hook.
    async with sf() as s:
        AuditLogger.write(
            s,
            actor_type=AuditActorType.USER,
            actor_id="adr0043_bootstrap_loss_control",
            action=AUDIT_ACTION,
            target_type="risk_loss_control_state",
            target_id=BOOTSTRAP_ACCOUNT_ID,
            payload={
                "account_id": BOOTSTRAP_ACCOUNT_ID,
                "initial_state": EXPECTED_STATE,
                "state_version": EXPECTED_STATE_VERSION,
                "reason": AUDIT_REASON,
                "authority": AUDIT_AUTHORITY,
            },
        )
        await s.commit()
    check("audit_recorded", True, f"audit action {AUDIT_ACTION} written")

    evidence["counters_after"] = after_counters = await side_effect_counters(sf)
    ok, problems = assess_side_effects(before_counters, after_counters, committed=True)
    if not check("no_side_effects", ok, "; ".join(problems) or "all counters unchanged"):
        raise BootstrapRefused(
            REFUSE_SIDE_EFFECT,
            "the bootstrap changed something it must not have: " + "; ".join(problems),
            {"problems": problems},
        )

    evidence["outcome"] = "COMMITTED"
    evidence["finished_at"] = datetime.now(UTC).isoformat()
    _write_evidence(evidence, out)
    print(f"outcome: {evidence['outcome']}", flush=True)
    return evidence


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=f"ADR-0043 loss-control bootstrap for account {BOOTSTRAP_ACCOUNT_ID}"
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="actually bootstrap. Default is a dry run that performs every read and check.",
    )
    parser.add_argument("--evidence", type=Path, default=None, help="write the evidence JSON here")
    args = parser.parse_args(argv)

    from app.db.session import get_sessionmaker

    sf = get_sessionmaker()
    try:
        await bootstrap_loss_control(
            sf=sf, adapter_factory=build_scoped_adapter, commit=args.commit, out=args.evidence
        )
    except SessionOpenRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(asyncio.run(_main(sys.argv[1:])))
