"""The designated SIP producer identity (SIP-CACHE-001 §7.1).

SIP is a **shared Workbench data service backed by one paid subscription**, not a per-account
entitlement. Exactly one credential identity is designated as the authorized producer, and
acquisition for the operational plane uses that identity and no other.

``SIP-CACHE-001-PRODUCER-001 = DESIGNATED / WORKBENCH ACCOUNT 7 / BROKER PA3BGKRLH2AP /
CREDENTIAL FP b56421a28128 / SHARED MARKET-DATA PRODUCER ONLY / NO STRATEGY EXECUTION AUTHORITY /
NO AUTOMATIC FAILOVER`` — owner ruling 2026-08-31.

⚠ **PRODUCER IDENTITY IS NOT ORDER IDENTITY.** Account 7's credential is designated here for the
shared market-data producer role. That designation confers no Strategy-9 execution authority, and
this module must never be used to obtain a credential for order submission — orders resolve through
``OrderRouter`` and the broker registry, which is a different question with a different answer.

⚠ **NO FAILOVER BY DISCOVERY.** The 2026-08-31 entitlement census measured accounts 5
(``PA3DBWDGOING``) and 6 (``PA30T0I3JJV9``) *also* returning recent-SIP 200. That is an
access-topology observation and confers no producer role. If the designated identity cannot provide
SIP the plane fails closed as ``ENTITLEMENT_FAIL``; substituting a credential that happens to work
would silently rewrite the provenance every cached record claims.

⚠ **Deliberately does not import ``app.research.capture.identity``**, which pins the same credential
for the MDQ evidence collector. The two planes share an entitlement and a credential identity and
**nothing else** (§4). Importing across would also become a research-plane isolation violation the
moment ``app/risk`` consumes this cache in Implementation B: the ADR-0051 checker walks the bounded
transitive closure, and ``app.risk -> app.market_data.sip -> app.research.capture`` is exactly the
order-path-into-the-archive path ``FORBIDDEN_FOR_ORDER_PATH`` exists to stop.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

FINGERPRINT_HEX_LEN = 12

#: Stable identifier for the entitlement in force, recorded on every cached record.
ENTITLEMENT_IDENTITY = "algo_trader_plus/account-7"

#: The designated producer. Changing any of these is a governed change (§7.1), never an
#: implicit consequence of a credential rotation or an outage.
DESIGNATED_ACCOUNT_ID = 7
DESIGNATED_BROKER_ACCOUNT = "PA3BGKRLH2AP"
DESIGNATED_KEY_FINGERPRINT = "b56421a28128"


def key_fingerprint(api_key_id: str) -> str:
    """``sha256`` of the API key id, truncated to 12 hex chars.

    Reveals nothing recoverable about the key, so it is safe for records, logs and evidence.
    The key itself is never returned, stored, or logged anywhere in this package.
    """
    return hashlib.sha256(api_key_id.encode()).hexdigest()[:FINGERPRINT_HEX_LEN]


class ProducerIdentityError(RuntimeError):
    """The credential offered is not the designated SIP producer.

    Raised *before* any network call. A credential that would succeed at the provider is still
    refused: entitlement is not authority.
    """


@dataclass(frozen=True)
class ProducerPins:
    """Pinned identity of the designated SIP producer.

    Rotating the credential intentionally breaks the pin. Re-pinning is a deliberate, reviewed
    change with its own record — never an automatic fallback.

    Re-pin history:

    ``b56421a28128`` — designated 2026-08-31 (`SIP-CACHE-001-PRODUCER-001`). The basis is
    evidentiary rather than convenience: account 7 is already the identity bound to the entire MDQ
    SIP evidence history and to the measured ATP/SIP path, so designating it minimises provenance
    discontinuity.
    """

    account_id: int = DESIGNATED_ACCOUNT_ID
    broker_account: str = DESIGNATED_BROKER_ACCOUNT
    key_fingerprint: str = DESIGNATED_KEY_FINGERPRINT
    entitlement_identity: str = ENTITLEMENT_IDENTITY

    def verify(self, api_key_id: str) -> str:
        """Return the fingerprint of ``api_key_id`` iff it is the designated producer.

        Raises :class:`ProducerIdentityError` otherwise. This is the single gate through which
        acquisition credentials pass; there is no bypass and no "try the next one" branch.
        """
        fp = key_fingerprint(api_key_id)
        if fp != self.key_fingerprint:
            raise ProducerIdentityError(
                "credential fingerprint "
                f"{fp} is not the designated SIP producer ({self.key_fingerprint}); "
                "SIP acquisition is refused. This is not a failover point — the shared SIP "
                "plane fails closed rather than acquiring under an undesignated identity."
            )
        return fp


PRODUCER = ProducerPins()
