"""Acquisition-identity latch for the MDQ-001 collector.

Accounts are resolved by FINGERPRINT, never by env-var name (the .env numbering
is offset from workbench account numbers and has been corrupted before). The
collector refuses to run unless BOTH hold:

  1. the resolved API key's fingerprint equals the pinned value, and
  2. the live broker identity (GET /v2/account, read-only) equals the pinned
     account number.

The account check uses a plain HTTPS GET — deliberately not the alpaca.trading
SDK, which research-plane code must not import (ADR 0051 Decision 3,
check_research_plane_no_broker_capability.sh). Reading the account number is an
identity latch, not broker capability.

Payload discipline (implementation-plan v0.5 §3.1): the /v2/account response
carries execution-plane state (equity, buying power, ...) alongside the broker
id. Exactly one field — ``account_number`` — leaves the HTTP boundary; the
remainder is never logged, returned, or persisted into the research archive.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

FINGERPRINT_HEX_LEN = 12


def key_fingerprint(api_key_id: str) -> str:
    """sha256 of the API key id, truncated to 12 hex chars.

    Matches the fingerprint scheme used by the account-7 identity-latch records
    (e.g. the ``ALPACA_PAPER_6`` key pins to ``5b6f39e5198d``). Reveals nothing
    recoverable about the key; safe for manifests and logs.
    """
    return hashlib.sha256(api_key_id.encode()).hexdigest()[:FINGERPRINT_HEX_LEN]


@dataclass(frozen=True)
class AcquisitionPins:
    """Pinned identity of the sole SIP acquisition credential (account 7).

    Rotating the credential intentionally breaks the pin — re-pinning is a
    deliberate, reviewed change, never an automatic fallback.
    """

    key_fingerprint: str = "5b6f39e5198d"
    account_number: str = "PA3BGKRLH2AP"
    cred_env_key: str = "ALPACA_PAPER_6_API_KEY"
    cred_env_secret: str = "ALPACA_PAPER_6_API_SECRET"
    trading_base_url: str = "https://paper-api.alpaca.markets"


class IdentityError(RuntimeError):
    """The resolved credential is not the pinned acquisition identity."""


def verify_identity(
    api_key: str,
    api_secret: str,
    pins: AcquisitionPins,
    *,
    account_getter: Callable[[str, str, str], str] | None = None,
) -> str:
    """Fail-closed identity latch. Returns the verified account number.

    ``account_getter(base_url, api_key, api_secret) -> account_number`` is
    injectable for tests; the default performs the read-only HTTPS GET.
    """
    fp = key_fingerprint(api_key)
    if fp != pins.key_fingerprint:
        raise IdentityError(
            f"credential fingerprint {fp} != pinned {pins.key_fingerprint} — "
            f"refusing to acquire. If the key was rotated, re-pin deliberately."
        )
    getter = account_getter or _get_account_number
    account = getter(pins.trading_base_url, api_key, api_secret)
    if account != pins.account_number:
        raise IdentityError(
            f"broker account {account} != pinned {pins.account_number} — "
            f"the credential does not belong to the acquisition account."
        )
    return account


def _get_account_number(base_url: str, api_key: str, api_secret: str) -> str:
    """Return ONLY the account number from the read-only GET /v2/account.

    The rest of the payload (equity, buying power, and other execution-plane
    state) is discarded here, inside the HTTP boundary — it must never be
    logged or persisted into the research archive (plan v0.5 §3.1).
    """
    import httpx

    resp = httpx.get(
        f"{base_url.rstrip('/')}/v2/account",
        headers={"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret},
        timeout=15.0,
    )
    resp.raise_for_status()
    return str(resp.json()["account_number"])
