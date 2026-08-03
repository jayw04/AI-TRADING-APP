"""ADR 0043 successor WS5 Stage-C read-only account reconciliation.

The governed boundary (``policy`` / ``transport`` / ``readonly_client`` /
``factory``) gives the runtime the *capability* to read a broker account safely.
This module is the *procedure* that uses it — the only sanctioned Stage-C entry
point.

It obtains its client exclusively from :func:`app.brokers.factory.get_broker_client`
and imports no legacy broker surface: no ``AlpacaAdapter``, no ``BrokerRegistry``,
no ``TradeUpdatesStream``, no alpaca-py ``TradingClient``, no raw authenticated
HTTP client. Those absences are asserted by tests, because "we didn't call it" is
weaker evidence than "it isn't reachable from here".

Sequence, in order, with identity first:

    GET /v2/account   -> account_number must equal expected_account_id
    GET /v2/positions
    GET /v2/orders
    GET /v2/account/activities

A mismatch stops everything: the read-only client latches shut, so later reads
raise without dispatching. Financial values are recorded as reconciliation
evidence only and are explicitly *not* an authoritative Start A baseline.

Run:  python -m app.brokers.adr0043_reconcile --output <path>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.brokers.exceptions import (
    BrokerAccountMismatch,
    BrokerBoundaryError,
    BrokerConfigurationError,
    BrokerOperationDenied,
)
from app.brokers.factory import BrokerCredentialRef, get_broker_client

SCHEMA_VERSION = "adr0043-ws5-stage-c/1.0"

#: Terminal dispositions. Exit codes are distinct so a supervising process can
#: branch without parsing the artifact.
READY = "READY"
REFUSED = "REFUSED"
INCONCLUSIVE = "INCONCLUSIVE"

EXIT_CODES = {READY: 0, REFUSED: 2, INCONCLUSIVE: 3}

APPROVED_CALL_ORDER = [
    "GET /v2/account",
    "GET /v2/positions",
    "GET /v2/orders",
    "GET /v2/account/activities",
]

#: Dedicated successor credential names. Deliberately NOT ALPACA_PAPER_7_*, which
#: collides with Workbench account 7 / strategy 9 (combined-book, PA3344TNRFYD).
ENV_KEY = "ADR0043_SUCCESSOR_CANARY_ALPACA_API_KEY"
ENV_SECRET = "ADR0043_SUCCESSOR_CANARY_ALPACA_API_SECRET"
ENV_ACCOUNT = "ADR0043_SUCCESSOR_CANARY_ACCOUNT_ID"


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class _CountingSender:
    """Wraps the real HTTP sender purely to count dispatches.

    The count is evidence: a denied mutation must leave it unchanged, and the
    artifact records it so a reviewer can see that exactly four requests left the
    process.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.dispatches = 0

    def __call__(self, method: str, url: str, *, headers: dict[str, str], timeout: float):
        self.dispatches += 1
        return self._inner(method, url, headers=headers, timeout=timeout)


def _default_sender():  # pragma: no cover - exercised only in a real runtime
    """Minimal HTTPS sender. Deliberately not a session object held anywhere."""
    import urllib.request

    def send(method: str, url: str, *, headers: dict[str, str], timeout: float):
        req = urllib.request.Request(url, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()

    return send


def build_evidence(
    *,
    run_id: str,
    started: str,
    completed: str,
    source_commit: str,
    image_digest: str,
    expected_account: str,
    returned_account: str | None,
    key_fp: str,
    secret_fp: str,
    access_mode: str,
    calls: list[str],
    account: dict[str, Any] | None,
    positions: list | None,
    orders: list | None,
    activities: list | None,
    dispatches: int,
    mutation_attempts: int,
    disposition: str,
    failure_code: str | None,
) -> dict[str, Any]:
    """Assemble the reconciliation record. ``artifact_sha256`` is added by the writer."""
    acct = account or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "started_at_utc": started,
        "completed_at_utc": completed,
        "source_commit": source_commit,
        "image_manifest_digest": image_digest,
        "expected_account_id": expected_account,
        "returned_account_id": returned_account,
        "credential_key_fingerprint": key_fp,
        "credential_secret_fingerprint": secret_fp,
        "broker_access_mode": access_mode,
        "approved_calls_in_order": calls,
        "positions_count": None if positions is None else len(positions),
        "orders_count": None if orders is None else len(orders),
        "activities_count": None if activities is None else len(activities),
        "equity": acct.get("equity"),
        "last_equity": acct.get("last_equity"),
        "cash": acct.get("cash"),
        "portfolio_value": acct.get("portfolio_value"),
        "position_market_value": acct.get("position_market_value"),
        "authoritative_start_a_baseline": False,
        "transport_dispatch_count": dispatches,
        "mutation_attempt_count": mutation_attempts,
        "terminal_disposition": disposition,
        "failure_code": failure_code,
    }


def write_evidence(record: dict[str, Any], path: Path) -> str:
    """Write atomically: temp file, validate, hash, then rename.

    A partially written record must never appear at the destination path, so the
    rename is the publication step and happens only once the record is complete.
    """
    missing = [
        k for k, v in record.items() if v is None and k in ("run_id", "terminal_disposition")
    ]
    if missing:
        raise ValueError(f"refusing to publish incomplete evidence; missing {missing}")

    body = json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    full = json.dumps(
        {**record, "artifact_sha256": digest}, indent=2, sort_keys=True, ensure_ascii=False
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".partial")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(full + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)  # atomic publication
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return digest


def reconcile(
    *,
    settings: Any,
    credential: BrokerCredentialRef,
    expected_account_id: str,
    base_url: str,
    sender: Any,
    source_commit: str = "",
    image_digest: str = "",
    run_id: str | None = None,
    now: Any = _now,
) -> tuple[dict[str, Any], str]:
    """Run Stage-C reconciliation. Returns ``(evidence, disposition)``.

    Never raises for a broker-side outcome — every failure is classified into a
    terminal disposition so the caller always has an artifact to publish.
    """
    run_id = run_id or uuid.uuid4().hex
    started = now()
    counting = _CountingSender(sender)
    calls: list[str] = []
    account = positions = orders = activities = None
    returned = None
    failure: str | None = None
    disposition = INCONCLUSIVE

    def finish(disp: str, code: str | None) -> tuple[dict[str, Any], str]:
        return (
            build_evidence(
                run_id=run_id,
                started=started,
                completed=now(),
                source_commit=source_commit,
                image_digest=image_digest,
                expected_account=expected_account_id,
                returned_account=returned,
                key_fp=credential.fingerprint,
                secret_fp=getattr(credential, "secret_fingerprint", ""),
                access_mode=str(getattr(settings, "broker_access_mode", "") or ""),
                calls=calls,
                account=account,
                positions=positions,
                orders=orders,
                activities=activities,
                dispatches=counting.dispatches,
                mutation_attempts=0,
                disposition=disp,
                failure_code=code,
            ),
            disp,
        )

    try:
        client = get_broker_client(
            access_mode=getattr(settings, "broker_access_mode", ""),
            credential=credential,
            expected_account_id=expected_account_id,
            base_url=base_url,
            sender=counting,
            strategy_execution_enabled=getattr(settings, "strategy_execution_enabled", False),
            scheduler_enabled=getattr(settings, "scheduler_enabled", False),
        )
    except BrokerConfigurationError as exc:
        return finish(REFUSED, f"configuration_error: {exc}")
    except BrokerOperationDenied as exc:
        return finish(REFUSED, f"client_denied: {exc}")

    # ---- identity first; nothing else runs until it passes ----
    try:
        account = client.get_account()
        calls.append(APPROVED_CALL_ORDER[0])
        returned = str(account.get("account_number") or "")
    except BrokerAccountMismatch as exc:
        returned = exc.actual
        calls.append(APPROVED_CALL_ORDER[0])
        return finish(
            REFUSED, f"account_identity_mismatch: expected {exc.expected}, got {exc.actual}"
        )
    except BrokerOperationDenied as exc:
        return finish(REFUSED, f"policy_denied: {exc}")
    except Exception as exc:  # transport/connectivity — no integrity breach proven
        return finish(INCONCLUSIVE, f"account_read_failed: {type(exc).__name__}: {exc}")

    # ---- remaining approved reads ----
    try:
        positions = client.get_positions()
        calls.append(APPROVED_CALL_ORDER[1])
        orders = client.get_orders()
        calls.append(APPROVED_CALL_ORDER[2])
        activities = client.get_account_activities()
        calls.append(APPROVED_CALL_ORDER[3])
    except BrokerBoundaryError as exc:
        return finish(REFUSED, f"policy_denied: {exc}")
    except Exception as exc:
        return finish(INCONCLUSIVE, f"read_failed: {type(exc).__name__}: {exc}")

    if calls != APPROVED_CALL_ORDER:
        return finish(REFUSED, f"call_sequence_violation: {calls}")

    disposition = READY
    return finish(disposition, failure)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ADR 0043 WS5 Stage-C reconciliation")
    parser.add_argument("--output", required=True, help="path for the reconciliation artifact")
    parser.add_argument("--source-commit", default=os.environ.get("ADR0043_SOURCE_COMMIT", ""))
    parser.add_argument("--image-digest", default=os.environ.get("ADR0043_IMAGE_DIGEST", ""))
    args = parser.parse_args(argv)

    from app.config import get_settings

    settings = get_settings()
    key = os.environ.get(ENV_KEY, "")
    secret = os.environ.get(ENV_SECRET, "")
    expected = os.environ.get(ENV_ACCOUNT, "") or getattr(
        settings, "broker_expected_account_id", ""
    )
    if not key or not secret or not expected:
        print(
            f"REFUSED: {ENV_KEY}, {ENV_SECRET} and {ENV_ACCOUNT} are all required",
            file=sys.stderr,
        )
        return EXIT_CODES[REFUSED]

    cred = BrokerCredentialRef(
        source="env:ADR0043_SUCCESSOR_CANARY_*",
        fingerprint=_fingerprint(key),
        resolve=lambda: (key, secret),
        secret_fingerprint=_fingerprint(secret),
    )

    evidence, disposition = reconcile(
        settings=settings,
        credential=cred,
        expected_account_id=expected,
        base_url="https://paper-api.alpaca.markets",
        sender=_default_sender(),
        source_commit=args.source_commit,
        image_digest=args.image_digest,
    )
    try:
        write_evidence(evidence, Path(args.output))
    except Exception as exc:
        print(f"INCONCLUSIVE: evidence write failed: {exc}", file=sys.stderr)
        return EXIT_CODES[INCONCLUSIVE]

    print(f"{disposition}: {evidence.get('failure_code') or 'all approved reads completed'}")
    return EXIT_CODES[disposition]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
