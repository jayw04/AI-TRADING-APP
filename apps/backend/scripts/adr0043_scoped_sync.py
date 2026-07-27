"""ADR 0043 Phase-0 — the account-3 scoped account/position sync.

WHY THIS EXISTS AT ALL
----------------------
Phase 0 needs account 3's ``accounts_state`` and ``positions`` rows refreshed from the broker before
a baseline can be captured, on a validation host where the global scheduler is deliberately DISARMED
(``ADR0043_VALIDATION_SCHEDULER_DISARMED``). Enabling the scheduler is NOT the answer: one flag arms
sync for **every** local account, including account 1, whose ledger is incident evidence for the
2026-07-13 risk-gate event and must not be touched.

Neither existing mechanism is acceptable, and neither is fixable by passing an argument:

  * ``AccountSyncService.sync_once`` / ``PositionSyncService.sync_once`` bind the *primary* adapter
    and resolve "the first alpaca account in the requested mode" — which account that is depends on
    row order, not on intent;
  * ``sync_all`` iterates every ``accounts`` row and syncs each from the broker registry.

Both are *configured* to be narrow at best. This module is **structurally** narrow: the target is a
pair of module constants, there is no loop, no registry, no scheduler, and no code path that can
reach a second account even if every environment variable on the host is wrong. That last clause is
the whole point — ``ADR0043_RUNTIME_TARGET_BINDING_MISMATCH`` happened precisely because the deployed
environment silently overrode a correct default.

THE PROOF OBLIGATIONS
---------------------
Each is enforced here and pinned by ``tests/scripts/test_adr0043_scoped_sync.py``:

  1. the target is user 3 / account 3, frozen as constants — **never** read from the environment;
  2. the adapter is built from user 3's encrypted credentials and nothing else;
  3. the broker identity is verified to be ``PA34USW0Q8UO`` before any write, and
     ``PA3QRX9KSPXA`` (account 1's broker account) is refused by name;
  4. account 1 is never queried, never decrypted, never mutated;
  5. there is no account loop;
  6. no scheduler is constructed;
  7. no mutating broker method is reachable — the adapter is wrapped in a read-only proxy;
  8. the write transaction touches only account-3 rows;
  9. the run REFUSES unless the broker holds exactly MSFT 19 LONG, 0 open orders, and the account
     holds 0 HELD reservations. It **never silently normalizes** a mismatch — a broker that disagrees
     with the frozen manifest is a finding to investigate, not a state to overwrite.

Writes require ``--commit``. The default is a dry run that performs every read and every check and
then reports what it *would* write, because a conservative default is the one that survives being
run by an operator who has not read this docstring.

⚠ RUNTIME IS AWS. This runs on the ADR-0043 validation host against the frozen acct-3 rig. It is
never run against the laptop's local stack, and it is not a general-purpose sync tool: it is a
single-purpose governed instrument that refuses every situation it was not built for.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models.account_state import AccountState
from app.db.models.position import Position
from app.db.models.risk_reservation import RESERVATION_HELD

# The day-change PROVENANCE logic is shared with the sweep (#495). ``day_change_basis`` is a pure,
# loop-free module — importing it brings no account iteration with it, so property 5 survives — and
# sharing it means this tool writes the same row the sweep would rather than a second opinion.
# Re-deriving "is there a usable baseline?" here is exactly the drift #495 exists to prevent.
from app.services.day_change_basis import (
    UNAVAILABLE,
    UNMEASURED,
    from_broker_last_equity,
    prior_session_close_proxy,
)

# The read-only proxy, the flat check, the atomic write and the refusal family are SHARED with
# ``adr0043_session_open``. One read-only broker view across the ADR-0043 tooling means there is one
# allowlist to audit, and its ``calls`` log lets this run record exactly which broker methods it
# touched rather than merely asserting which ones it did not.
from scripts.adr0043_session_open import (
    REFUSE_BROKER_IDENTITY,
    REFUSE_POSITIONS,
    ReadOnlyBrokerView,
    SessionOpenRefused,
    check_flat,
    write_package_atomically,
)

# ---------------------------------------------------------------------------- the frozen target
# NOT ``os.environ.get(...)``. The whole defect this module answers is an environment that silently
# overrode a correct default, so these are constants and the tests assert that the module reads no
# environment variable to derive them. Changing the target is a code change and a review, which is
# exactly the friction that should stand between an operator and the wrong account.
SCOPED_USER_ID = 3
SCOPED_ACCOUNT_ID = 3

# The broker account the frozen manifest binds to account 3.
EXPECTED_BROKER_ACCOUNT = "PA34USW0Q8UO"

# Named, not merely "anything else". Account 1's broker account is the one a mis-bound run would
# actually have reached, and naming it means a mismatch report says so instead of leaving an
# operator to work out whose account they nearly synced.
FORBIDDEN_BROKER_ACCOUNTS: dict[str, str] = {
    "PA3QRX9KSPXA": "account 1 — 2026-07-13 incident evidence; must never be touched by Phase 0",
}

# The frozen position manifest (canary manifest v1.1). The broker must agree with this EXACTLY.
EXPECTED_POSITIONS: dict[str, tuple[D, str]] = {"MSFT": (D(19), "long")}

# Statuses that actually hold capacity at the broker. ``list_orders`` returns recent orders, most of
# which are terminal; only these mean something is in flight.
OPEN_ORDER_STATUSES = frozenset(
    {
        "new",
        "accepted",
        "pending_new",
        "partially_filled",
        "accepted_for_bidding",
        "pending_replace",
        "replaced",
    }
)

# Refusal codes specific to this tool. The shared ones (identity, positions, not-flat, mutating
# call) come from ``adr0043_session_open`` so both tools name the same condition the same way.
REFUSE_TARGET_BINDING = "SCOPED_TARGET_BINDING_MISMATCH"
REFUSE_UNRESOLVED_SYMBOL = "SCOPED_SYNC_UNRESOLVED_SYMBOL"
REFUSE_UNPROTECTED_ADAPTER = "SCOPED_SYNC_ADAPTER_NOT_READ_ONLY"


class ScopedSyncRefused(SessionOpenRefused):
    """A precondition for a VALID scoped sync is absent, so nothing was written.

    Subclasses the governed-tooling refusal so both tools share one refusal family (and one
    ``code`` / ``detail`` / ``diagnostics`` shape), while staying separately catchable: a sync
    refusal and a session-open refusal call for different operator actions.

    A refusal is a correct outcome. The failure mode this class exists to prevent is the other one:
    a tool that finds the world disagreeing with its manifest and quietly makes the world match.
    """


# ---------------------------------------------------------------------------- pure helpers
def _to_decimal(v: Any, default: str = "0") -> D:
    if v is None or v == "":
        return D(default)
    try:
        return D(str(v))
    except Exception:
        return D(default)


def normalize_account_snapshot(raw: dict[str, Any]) -> dict[str, Any]:
    """Map Alpaca's account payload onto ``accounts_state`` columns.

    The column mapping is a local copy rather than an import of the sweep service's private
    normalizer: importing ``app.services.account_sync`` would put the looping sweep one attribute
    access away, and property 5 is meant to be provable by reading this file. A test pins this
    function's output equal to the service's, so the copy cannot drift.

    The day-change PROVENANCE, however, is shared outright (#495). Alpaca omits or zeroes
    ``last_equity`` on fresh paper accounts, and ``equity - 0`` would report the entire book as
    today's change while a plain ``0`` would claim a measured flat day. Both are assertions about a
    quantity nobody measured — and this column feeds the legacy daily-loss basis, so it is a
    risk-path input, not a display nit. With no broker baseline the answer here is UNMEASURED;
    :func:`resolve_day_change` may still reach the prior-close proxy, which needs a DB session this
    pure mapping does not have.
    """
    equity = _to_decimal(raw.get("equity"))
    last_equity = _to_decimal(raw.get("last_equity"))
    measured = from_broker_last_equity(equity, last_equity) or UNMEASURED
    return {
        "cash": _to_decimal(raw.get("cash")),
        "equity": equity,
        "last_equity": last_equity,
        "buying_power": _to_decimal(raw.get("buying_power")),
        "portfolio_value": _to_decimal(raw.get("portfolio_value") or raw.get("equity")),
        "daytrade_count": int(raw.get("daytrade_count") or 0),
        "day_change": measured.day_change,
        "day_change_pct": measured.day_change_pct,
        "day_change_basis": measured.basis,
        "status": str(raw.get("status") or "UNKNOWN"),
        "pattern_day_trader": bool(raw.get("pattern_day_trader") or False),
        "trading_blocked": bool(raw.get("trading_blocked") or False),
        "account_blocked": bool(raw.get("account_blocked") or False),
    }


async def resolve_day_change(session, payload: dict[str, Any], now: datetime) -> None:
    """Fill in the day-change fields the pure mapping could not decide, exactly as the sweep does.

    Mutates ``payload`` in place so the persisted row and the reported row carry one answer. Scoped
    to account 3 by the constant, like every other read here.

    A failure to read the snapshot history leaves the basis ``UNAVAILABLE``: it never invents a
    number to fill the gap, because an unmeasured baseline reported as a measured one is the exact
    defect #495 landed to prevent.
    """
    if payload["day_change_basis"] != UNAVAILABLE:
        return
    try:
        fallback = await prior_session_close_proxy(
            session, SCOPED_ACCOUNT_ID, payload["equity"], now
        )
    except Exception:
        return
    if fallback is None:
        return
    payload["day_change"] = fallback.day_change
    payload["day_change_pct"] = fallback.day_change_pct
    payload["day_change_basis"] = fallback.basis


def count_open_orders(orders: list[dict[str, Any]] | None) -> int:
    return sum(1 for o in (orders or []) if str(o.get("status", "")).lower() in OPEN_ORDER_STATUSES)


def assess_broker_identity(account_number: str | None) -> tuple[bool, str]:
    """Whether the connected broker account is the one account 3 is bound to.

    Checked BEFORE the position manifest and BEFORE any write: if this is the wrong account, every
    subsequent read describes somebody else's book and no later check means anything.
    """
    if not account_number:
        return False, "broker returned no account_number; identity cannot be established"
    number = str(account_number).strip()
    if number in FORBIDDEN_BROKER_ACCOUNTS:
        return False, (
            f"connected broker account {number} is EXPLICITLY FORBIDDEN "
            f"({FORBIDDEN_BROKER_ACCOUNTS[number]})"
        )
    if number != EXPECTED_BROKER_ACCOUNT:
        return False, (
            f"connected broker account {number} != expected {EXPECTED_BROKER_ACCOUNT}; "
            f"the credentials do not belong to account {SCOPED_ACCOUNT_ID}"
        )
    return True, f"broker account {number} matches the frozen binding"


def assess_position_manifest(positions: list[dict[str, Any]]) -> tuple[bool, str]:
    """Whether the broker's book is EXACTLY the frozen Phase-0 manifest.

    Positions only — "nothing in flight" is :func:`check_flat`, shared with ``adr0043_session_open``
    so both tools refuse a non-flat account by the same name and the same code.

    An inequality here is never repaired by writing. The account is meant to be quiescent, and if it
    is not, then something moved it and the interesting question is *what*, which a sync would erase
    the evidence of.
    """
    observed: dict[str, tuple[D, str]] = {}
    for p in positions or []:
        symbol = str(p.get("symbol") or "").upper()
        if not symbol:
            return False, "broker reported a position with no symbol"
        observed[symbol] = (_to_decimal(p.get("qty")), str(p.get("side") or "").lower())

    manifest = ", ".join(f"{k} {v[0]} {v[1]}" for k, v in sorted(EXPECTED_POSITIONS.items()))
    if observed != EXPECTED_POSITIONS:
        observed_s = (
            ", ".join(f"{k} {v[0]} {v[1]}" for k, v in sorted(observed.items())) or "(none)"
        )
        return False, (
            f"the broker book does not match the frozen Phase-0 manifest — expected "
            f"[{manifest}], broker holds [{observed_s}]. Refusing: this tool does not normalize a "
            f"mismatch it did not cause."
        )
    return True, f"broker holds exactly the frozen manifest ({manifest})"


# ---------------------------------------------------------------------------- scoped DB reads
async def verify_account_row(sf) -> dict[str, Any]:
    """Confirm the account-3 row is the account we think it is, before any credential is decrypted.

    Scoped by primary key: this is the only ``accounts`` read in the module, and it can return at
    most one row, which is why property 4 holds trivially rather than by convention.
    """
    async with sf() as s:
        row = (
            await s.execute(
                text("SELECT id, user_id, broker, mode FROM accounts WHERE id = :a"),
                {"a": SCOPED_ACCOUNT_ID},
            )
        ).mappings().first()
    if row is None:
        raise ScopedSyncRefused(
            REFUSE_TARGET_BINDING,
            f"no accounts row with id={SCOPED_ACCOUNT_ID}",
            {"account_id": SCOPED_ACCOUNT_ID},
        )
    if int(row["user_id"]) != SCOPED_USER_ID:
        raise ScopedSyncRefused(
            REFUSE_TARGET_BINDING,
            f"account {SCOPED_ACCOUNT_ID} belongs to user {row['user_id']}, not the frozen "
            f"user {SCOPED_USER_ID}. The target binding is wrong; investigate before syncing.",
            {"observed_user_id": int(row["user_id"]), "expected_user_id": SCOPED_USER_ID},
        )
    if str(row["broker"]) != "alpaca":
        raise ScopedSyncRefused(
            REFUSE_TARGET_BINDING,
            f"account {SCOPED_ACCOUNT_ID} broker is {row['broker']!r}",
            {"broker": str(row["broker"])},
        )
    if str(row["mode"]).lower().endswith("live"):
        raise ScopedSyncRefused(
            REFUSE_TARGET_BINDING,
            f"account {SCOPED_ACCOUNT_ID} is mode {row['mode']!r}; Phase 0 is paper-only",
            {"mode": str(row["mode"])},
        )
    return dict(row)


async def held_reservation_count(sf) -> int:
    async with sf() as s:
        return int(
            (
                await s.execute(
                    text(
                        "SELECT COUNT(*) FROM risk_reservations "
                        "WHERE account_id = :a AND state = :st"
                    ),
                    {"a": SCOPED_ACCOUNT_ID, "st": RESERVATION_HELD},
                )
            ).scalar()
            or 0
        )


async def symbol_id_for(sf, ticker: str) -> int | None:
    async with sf() as s:
        return (
            await s.execute(text("SELECT id FROM symbols WHERE ticker = :t"), {"t": ticker})
        ).scalar()


async def read_local_state(sf) -> dict[str, Any]:
    """The account-3 rows as they stand — the "before" half of the evidence package."""
    async with sf() as s:
        state = (
            await s.execute(
                text(
                    "SELECT equity, last_equity, day_change, cash, updated_at "
                    "FROM accounts_state WHERE account_id = :a"
                ),
                {"a": SCOPED_ACCOUNT_ID},
            )
        ).mappings().first()
        positions = (
            await s.execute(
                text(
                    "SELECT sym.ticker, p.qty, p.side FROM positions p "
                    "JOIN symbols sym ON sym.id = p.symbol_id "
                    "WHERE p.account_id = :a ORDER BY sym.ticker"
                ),
                {"a": SCOPED_ACCOUNT_ID},
            )
        ).mappings().all()
    return {
        "accounts_state": {k: str(v) for k, v in dict(state).items()} if state else None,
        "positions": [
            {"ticker": str(r["ticker"]), "qty": str(r["qty"]), "side": str(r["side"])}
            for r in positions
        ],
    }


# ---------------------------------------------------------------------------- the scoped write
async def write_account_3(sf, *, raw_account: dict[str, Any], positions: list[dict[str, Any]]) -> dict[str, Any]:
    """Upsert account 3's snapshot and positions in ONE transaction, touching no other account.

    Every statement carries ``account_id = SCOPED_ACCOUNT_ID`` as a literal bind — including the
    stale-position delete, which is the one statement in a sync that can plausibly be written
    unscoped and is therefore the one worth reading twice.
    """
    payload = normalize_account_snapshot(raw_account)
    now = datetime.now(UTC)
    written: dict[str, Any] = {"accounts_state": None, "positions_upserted": [], "positions_deleted": []}

    async with sf() as s:
        # Before the upsert, against the SAME session — so the persisted row and the reported row
        # cannot disagree about which baseline the day-change rests on.
        await resolve_day_change(s, payload, now)
        stmt = sqlite_insert(AccountState).values(
            account_id=SCOPED_ACCOUNT_ID, **payload, updated_at=now, raw_payload=raw_account
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["account_id"],
            set_={
                c: getattr(stmt.excluded, c)
                for c in (
                    "cash",
                    "equity",
                    "last_equity",
                    "buying_power",
                    "portfolio_value",
                    "daytrade_count",
                    "day_change",
                    "day_change_pct",
                    "day_change_basis",
                    "status",
                    "pattern_day_trader",
                    "trading_blocked",
                    "account_blocked",
                    "raw_payload",
                    "updated_at",
                )
            },
        )
        await s.execute(stmt)
        written["accounts_state"] = {k: str(v) for k, v in payload.items()}

        seen_symbol_ids: list[int] = []
        for p in positions:
            ticker = str(p.get("symbol") or "").upper()
            sid = (
                await s.execute(text("SELECT id FROM symbols WHERE ticker = :t"), {"t": ticker})
            ).scalar()
            if sid is None:
                # Cannot happen under the manifest gate (MSFT is a resolved symbol), but a silent
                # skip here would produce a partial sync that reads as a complete one.
                raise ScopedSyncRefused(
                    REFUSE_UNRESOLVED_SYMBOL,
                    f"broker reports {ticker} but no symbols row resolves it; refusing a partial "
                    f"sync that would look complete",
                    {"ticker": ticker},
                )
            seen_symbol_ids.append(int(sid))
            pstmt = sqlite_insert(Position).values(
                user_id=SCOPED_USER_ID,
                account_id=SCOPED_ACCOUNT_ID,
                symbol_id=int(sid),
                qty=_to_decimal(p.get("qty")),
                avg_entry_price=_to_decimal(p.get("avg_entry_price")),
                side=p.get("side"),
                market_value=_to_decimal(p.get("market_value")),
                cost_basis=_to_decimal(p.get("cost_basis")),
                unrealized_pl=_to_decimal(p.get("unrealized_pl")),
                unrealized_plpc=_to_decimal(p.get("unrealized_plpc")),
                updated_at=now,
            )
            pstmt = pstmt.on_conflict_do_update(
                index_elements=["account_id", "symbol_id"],
                set_={
                    c: getattr(pstmt.excluded, c)
                    for c in (
                        "qty",
                        "avg_entry_price",
                        "side",
                        "market_value",
                        "cost_basis",
                        "unrealized_pl",
                        "unrealized_plpc",
                        "updated_at",
                    )
                },
            )
            await s.execute(pstmt)
            written["positions_upserted"].append({"ticker": ticker, "qty": str(p.get("qty"))})

        existing = (
            await s.execute(
                text("SELECT symbol_id FROM positions WHERE account_id = :a"),
                {"a": SCOPED_ACCOUNT_ID},
            )
        ).scalars().all()
        stale = [int(sid) for sid in existing if int(sid) not in seen_symbol_ids]
        for sid in stale:
            await s.execute(
                text("DELETE FROM positions WHERE account_id = :a AND symbol_id = :s"),
                {"a": SCOPED_ACCOUNT_ID, "s": sid},
            )
            written["positions_deleted"].append(sid)

        await s.commit()
    return written


# ---------------------------------------------------------------------------- the run
async def scoped_sync(
    *, sf, adapter_factory, commit: bool, out: Path | None = None
) -> dict[str, Any]:
    """Perform the scoped sync. ``adapter_factory`` is injected so the tests can drive every branch
    offline; the production factory is :func:`build_scoped_adapter` and it resolves user 3's
    credentials and nothing else.

    A REFUSAL still writes the evidence file. The refusal is the outcome most worth a durable
    record — "the broker held something other than the manifest" is a finding, and a finding that
    exists only as a line on a terminal that has since scrolled away is not evidence.
    """
    # Owned here rather than inside the run, so the refusal path below can persist whatever was
    # established before the refusal — the checks that DID pass are part of the record.
    evidence: dict[str, Any] = {}
    try:
        return await _scoped_sync(
            sf=sf, adapter_factory=adapter_factory, commit=commit, out=out, evidence=evidence
        )
    # The BASE class, not ScopedSyncRefused: the shared ReadOnlyBrokerView and check_flat raise
    # SessionOpenRefused, and an attempted mutating call is precisely the refusal that must not go
    # unrecorded.
    except SessionOpenRefused as exc:
        evidence["outcome"] = "REFUSED"
        evidence["refusal"] = str(exc)
        evidence["refusal_code"] = exc.code
        evidence["refusal_diagnostics"] = exc.diagnostics
        evidence["finished_at"] = datetime.now(UTC).isoformat()
        _write_evidence(evidence, out)
        raise


def _write_evidence(evidence: dict[str, Any], out: Path | None) -> None:
    """Atomically, via the shared writer — a reader that finds a truncated evidence file must never
    mistake it for a complete one."""
    if out is None:
        return
    write_package_atomically(evidence, out)
    print(f"evidence → {out}", flush=True)


async def _scoped_sync(
    *, sf, adapter_factory, commit: bool, out: Path | None, evidence: dict[str, Any]
) -> dict[str, Any]:
    evidence.update({
        "tool": "adr0043_scoped_sync",
        "started_at": datetime.now(UTC).isoformat(),
        "target": {
            "user_id": SCOPED_USER_ID,
            "account_id": SCOPED_ACCOUNT_ID,
            "expected_broker_account": EXPECTED_BROKER_ACCOUNT,
            "forbidden_broker_accounts": sorted(FORBIDDEN_BROKER_ACCOUNTS),
            "expected_positions": {k: [str(v[0]), v[1]] for k, v in EXPECTED_POSITIONS.items()},
        },
        "mode": "COMMIT" if commit else "DRY_RUN",
        "checks": [],
        "before": None,
        "written": None,
        "outcome": None,
    })

    def check(name: str, ok: bool, detail: str) -> bool:
        evidence["checks"].append({"name": name, "result": "PASS" if ok else "FAIL", "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
        return ok

    # Identity is printed and verified BEFORE any credential is decrypted. On the validation host the
    # binding itself was the defect, so an operator must be able to see the target before the tool
    # has touched a secret.
    print(
        f"ADR-0043 scoped sync — target user={SCOPED_USER_ID} account={SCOPED_ACCOUNT_ID} "
        f"broker={EXPECTED_BROKER_ACCOUNT} mode={evidence['mode']}",
        flush=True,
    )
    row = await verify_account_row(sf)
    check("account_row_binding", True, f"accounts id={row['id']} user_id={row['user_id']} mode={row['mode']}")

    evidence["before"] = await read_local_state(sf)

    broker = await adapter_factory(sf)
    if not isinstance(broker, ReadOnlyBrokerView):
        raise ScopedSyncRefused(
            REFUSE_UNPROTECTED_ADAPTER,
            "the adapter factory must return a ReadOnlyBrokerView; a raw adapter would put every "
            "mutating broker method one attribute access away from this run",
            {"observed_type": type(broker).__name__},
        )

    raw_account = await asyncio.to_thread(broker.get_account)
    ok, detail = assess_broker_identity(raw_account.get("account_number"))
    if not check("broker_identity", ok, detail):
        raise ScopedSyncRefused(
            REFUSE_BROKER_IDENTITY, detail, {"observed": raw_account.get("account_number")}
        )

    positions = await asyncio.to_thread(broker.get_positions)
    orders = await asyncio.to_thread(broker.list_orders)
    open_orders = count_open_orders(orders)
    held = await held_reservation_count(sf)

    ok, detail = assess_position_manifest(positions)
    if not check("frozen_manifest", ok, detail):
        raise ScopedSyncRefused(REFUSE_POSITIONS, detail, {"open_orders": open_orders})

    # Shared with the session-open tool, so "the account is not flat" is one condition with one
    # name across the ADR-0043 tooling. It raises rather than returning a verdict.
    check_flat(open_orders, held)
    check("account_flat", True, f"open_orders={open_orders} held_reservations={held}")

    # What this run actually touched at the broker — recorded from the proxy's own log, so the
    # evidence states the reached surface rather than asserting the unreached one.
    evidence["broker_calls"] = list(broker.calls)

    if commit:
        evidence["written"] = await write_account_3(sf, raw_account=raw_account, positions=positions)
        evidence["after"] = await read_local_state(sf)
        evidence["outcome"] = "COMMITTED"
    else:
        # The preview resolves the day-change basis exactly as the commit would. A dry run that
        # showed UNAVAILABLE where --commit would write PRIOR_SESSION_CLOSE_PROXY would be
        # describing a different write than the one an operator is about to authorize.
        preview = normalize_account_snapshot(raw_account)
        async with sf() as s:
            await resolve_day_change(s, preview, datetime.now(UTC))
        evidence["written"] = {
            "would_write_accounts_state": {k: str(v) for k, v in preview.items()},
            "would_upsert_positions": [
                {"ticker": str(p.get("symbol")), "qty": str(p.get("qty"))} for p in positions
            ],
        }
        evidence["outcome"] = "DRY_RUN_NO_WRITE"

    evidence["finished_at"] = datetime.now(UTC).isoformat()
    _write_evidence(evidence, out)
    print(f"outcome: {evidence['outcome']}", flush=True)
    return evidence


async def build_scoped_adapter(sf) -> ReadOnlyBrokerView:
    """Construct the adapter from user 3's encrypted credentials — and no one else's.

    ``credentials_for_mode`` is called with the frozen constant, not with a value read from a row or
    an environment variable, so there is no input to this function that could select another user's
    keys. The ``BrokerRegistry`` is deliberately not used: it exists to build one adapter per account
    and its ``load_all`` decrypts every user's credentials in a loop.
    """
    from app.brokers.alpaca import AlpacaAdapter
    from app.brokers.alpaca.credentials import credentials_for_mode

    creds = await credentials_for_mode("paper", SCOPED_USER_ID, sf)
    adapter = AlpacaAdapter(credentials=creds)
    await asyncio.to_thread(adapter.connect)
    return ReadOnlyBrokerView(adapter)


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=f"ADR-0043 scoped sync for account {SCOPED_ACCOUNT_ID}")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="actually write. Default is a dry run that performs every read and check.",
    )
    parser.add_argument("--evidence", type=Path, default=None, help="write the evidence JSON here")
    args = parser.parse_args(argv)

    from app.db.session import get_sessionmaker

    sf = get_sessionmaker()
    try:
        await scoped_sync(sf=sf, adapter_factory=build_scoped_adapter, commit=args.commit, out=args.evidence)
    # The base class: a refused mutating-call attempt from the shared read-only view must exit 2
    # like any other refusal, not fall through as an unhandled traceback.
    except SessionOpenRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(asyncio.run(_main(sys.argv[1:])))
