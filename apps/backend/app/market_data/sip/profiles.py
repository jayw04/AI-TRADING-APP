"""SIP_EOD and SIP_LIVE — two profiles, deliberately not interchangeable (SIP-CACHE-001 §5, §6).

``SIP_EOD`` is a snapshot of the last *completed* trading day, refreshed after the close. Its
freshness is expressed in **trading days** against the authoritative market calendar.

``SIP_LIVE`` is current-session reference data with a bounded maximum age, expressed in **seconds**
and measured from the provider's ``source_timestamp``.

⚠ ``SIP_EOD`` is never a current execution quote. A consumer needing a current price must declare
``SIP_LIVE`` and satisfy its readiness independently — a ``PASS`` on one profile says nothing about
the other, and the readiness evaluator refuses to emit a single global verdict.

⚠ **The ``SIP_LIVE`` maximum age is deliberately not defined here — or anywhere platform-side.**
It is consumer-specific and is supplied only by the governed execution policy of the consumer that
declares it (B3 Decision 3/5, ``app.market_data.sip.demand.FreshnessPolicyProvider``). The parameter
exists from the first commit so the mechanism is never retrofitted; the value has no default, no
inheritance, and no best-effort fallback. A LIVE consumer without a governed bound is refused
``FRESHNESS_UNBOUND``.
"""

from __future__ import annotations

from enum import StrEnum


class SipProfile(StrEnum):
    """The two SIP data products. Values are persisted, so they are part of the schema."""

    EOD = "SIP_EOD"
    LIVE = "SIP_LIVE"


#: ``SIP_EOD`` tolerance, in completed trading days. 1 = "the last completed session".
DEFAULT_EOD_MAX_AGE_TRADING_DAYS = 1

#: Fraction of the declared symbol set that must be present for a profile to be complete.
DEFAULT_MIN_COVERAGE = 1.0
