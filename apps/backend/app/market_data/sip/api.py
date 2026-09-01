"""The governed consumer surface for the shared SIP plane (SIP-CACHE-001 §10).

    CONSUMER CANNOT EXPRESS ENTITLEMENT IDENTITY.

That invariant is enforced **structurally, not by policing**. Look at the signatures below: there is
no ``account_id``, no ``api_key``, no ``credential``, no ``credential_fingerprint``, no
``entitlement``, no ``feed``, and no ``producer`` parameter anywhere in the public surface. A
consumer cannot express the request *"use my credential"* — it is not a check that could be bypassed,
it is a sentence that cannot be spelled in this contract.

The designated producer (account 7) stays entirely behind the producer boundary. This module does
not import :mod:`app.market_data.sip.identity` for any purpose a consumer can reach, and does not
re-export it. A consumer never needs to know which identity acquired the data — only that the
provenance is attached to what it received.

⚠ **A genuinely SIP-entitled credential is still refused if it is not the designated producer.** The
2026-08-31 census measured accounts 5 and 6 returning recent-SIP 200. That capability confers no
producer authority: *entitlement capability does not create producer authority.*

⚠ **The clock is injected at construction, never per call.** Freshness is a trust decision, so the
valuation time is as much a trust input as the credential: a caller able to say *"evaluate this as
though the time were earlier"* could convert ``STALE`` into ``PASS`` and recover a usable price. That
was reproduced empirically (``SIP-CACHE-CONSUMER-CLOCK-INJECTION-001``) and is closed here — no
public method accepts a time. Tests inject a fake clock via the constructor.

⚠ **``SIP_LIVE`` requires an explicit ``max_age_s``.** There is deliberately no infrastructure
default for the execution-reference bound — it is a consumer-specific execution-policy value and
must not be chosen here because a number was convenient. Omitting it raises.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import structlog

from app.market_data.sip.cache import SipOperationalCache
from app.market_data.sip.profiles import SipProfile
from app.market_data.sip.readiness import (
    SipReadiness,
    SipReadinessEvaluator,
    SipReadinessState,
)
from app.market_data.sip.schema import CACHE_SCHEMA_VERSION, SipRecord
from app.market_data.sip.views import (
    SipDataView,
    SipPlaneStatus,
    SipProfileStatus,
)

logger = structlog.get_logger(__name__)


class SipLiveBoundRequired(ValueError):
    """``SIP_LIVE`` was requested without an explicit maximum age.

    The execution-reference bound belongs to the consuming strategy's execution policy. Infrastructure
    must not invent it, and must not let a consumer inherit one by omission.
    """


def _view_not_ready(
    symbol: str,
    profile: SipProfile,
    state: SipReadinessState,
    reason: str,
    rec: SipRecord | None = None,
    age_s: float | None = None,
) -> SipDataView:
    """Build a non-``PASS`` view. Price fields are always ``None`` here — by construction."""
    return SipDataView(
        symbol=symbol,
        profile=profile,
        state=state,
        reason=reason,
        price=None,
        bid=None,
        ask=None,
        feed=rec.feed if rec else None,
        source_feed_identity=rec.source_feed_identity if rec else None,
        source_timestamp=rec.source_timestamp if rec else None,
        received_at_utc=rec.received_at_utc if rec else None,
        entitlement_identity=rec.entitlement_identity if rec else None,
        credential_identity_fingerprint=(rec.credential_identity_fingerprint if rec else None),
        quality_classification=rec.quality_classification if rec else None,
        age_s=age_s,
    )


class SipConsumerService:
    """Read-only access to the shared SIP operational cache.

    Constructed by the platform with a cache handle. Consumers receive an instance; they never
    construct a producer, never resolve a credential, and never name a feed.
    """

    def __init__(
        self,
        cache: SipOperationalCache,
        *,
        expected_symbols: int = 0,
        min_coverage: float = 1.0,
        entitlement_ok: bool = True,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._cache = cache
        # The only place a clock enters this service. Production gets the real one; tests inject.
        self._clock: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))
        self._expected = expected_symbols
        self._min_coverage = min_coverage
        self._entitlement_ok = entitlement_ok
        self._acquisition_failures = 0
        self._retry_count = 0
        self._last_success: dict[str, datetime] = {}

    # ---------------------------------------------------------------- consumer reads

    async def get_reference(
        self,
        symbol: str,
        *,
        profile: SipProfile,
        max_age_s: float | None = None,
    ) -> SipDataView:
        """Current reference observation for ``symbol``.

        ``max_age_s`` is **required** for :attr:`SipProfile.LIVE` and is the consumer's declared
        execution bound. There is no default: see the module docstring.
        """
        now = self._clock()
        if profile is SipProfile.LIVE and max_age_s is None:
            raise SipLiveBoundRequired(
                "SIP_LIVE requires an explicit max_age_s. The execution-reference bound is a "
                "consumer execution-policy value; infrastructure does not supply a default."
            )

        if not self._entitlement_ok:
            return _view_not_ready(
                symbol,
                profile,
                SipReadinessState.ENTITLEMENT_FAIL,
                "designated producer cannot obtain SIP; plane-wide fail-closed",
            )

        rec = await self._cache.get(symbol, profile)
        if rec is None:
            return _view_not_ready(
                symbol, profile, SipReadinessState.ABSENT, "no cached observation"
            )

        if not rec.feed_is_authentic:
            return _view_not_ready(
                symbol,
                profile,
                SipReadinessState.ABSENT,
                "provider served a different feed than requested",
                rec,
            )

        age = (now - rec.source_timestamp).total_seconds()
        if max_age_s is not None and age > max_age_s:
            return _view_not_ready(
                symbol,
                profile,
                SipReadinessState.STALE,
                f"observation is {age:.1f}s old, exceeding the {max_age_s:.1f}s bound",
                rec,
                age,
            )

        return SipDataView(
            symbol=symbol,
            profile=profile,
            state=SipReadinessState.PASS,
            reason="within the declared bound; provenance complete",
            price=rec.price,
            bid=rec.bid,
            ask=rec.ask,
            feed=rec.feed,
            source_feed_identity=rec.source_feed_identity,
            source_timestamp=rec.source_timestamp,
            received_at_utc=rec.received_at_utc,
            entitlement_identity=rec.entitlement_identity,
            credential_identity_fingerprint=rec.credential_identity_fingerprint,
            quality_classification=rec.quality_classification,
            age_s=age,
        )

    async def get_eod(
        self,
        symbol: str,
        *,
        trading_date: date | None = None,
    ) -> SipDataView:
        """Last completed-session observation for ``symbol``.

        ⛔ Never a current execution quote. A consumer needing a current price must call
        :meth:`get_reference` with :attr:`SipProfile.LIVE` and satisfy its own bound.
        """
        now = self._clock()
        if not self._entitlement_ok:
            return _view_not_ready(
                symbol,
                SipProfile.EOD,
                SipReadinessState.ENTITLEMENT_FAIL,
                "designated producer cannot obtain SIP; plane-wide fail-closed",
            )

        rec = await self._cache.get(symbol, SipProfile.EOD, trading_date)
        if rec is None:
            return _view_not_ready(
                symbol,
                SipProfile.EOD,
                SipReadinessState.ABSENT,
                "no cached EOD observation" + (f" for {trading_date}" if trading_date else ""),
            )
        if not rec.feed_is_authentic:
            return _view_not_ready(
                symbol,
                SipProfile.EOD,
                SipReadinessState.ABSENT,
                "provider served a different feed than requested",
                rec,
            )
        if trading_date is not None and rec.trading_date != trading_date:
            return _view_not_ready(
                symbol,
                SipProfile.EOD,
                SipReadinessState.STALE,
                f"requested {trading_date}, newest available is {rec.trading_date}",
                rec,
            )

        return SipDataView(
            symbol=symbol,
            profile=SipProfile.EOD,
            state=SipReadinessState.PASS,
            reason="completed-session observation present; provenance complete",
            price=rec.price,
            bid=rec.bid,
            ask=rec.ask,
            feed=rec.feed,
            source_feed_identity=rec.source_feed_identity,
            source_timestamp=rec.source_timestamp,
            received_at_utc=rec.received_at_utc,
            entitlement_identity=rec.entitlement_identity,
            credential_identity_fingerprint=rec.credential_identity_fingerprint,
            quality_classification=rec.quality_classification,
            age_s=(now - rec.source_timestamp).total_seconds(),
        )

    # ---------------------------------------------------------------- readiness / status

    async def readiness(
        self,
        profile: SipProfile,
        *,
        live_max_age_s: float | None = None,
        eod_expected_trading_date: date | None = None,
    ) -> SipReadiness:
        """Profile readiness recomputed from cache contents. Never a stored verdict."""
        if profile is SipProfile.LIVE and live_max_age_s is None:
            raise SipLiveBoundRequired(
                "SIP_LIVE readiness requires an explicit live_max_age_s bound."
            )
        records = await self._cache.latest_for_profile(profile)
        evaluator = SipReadinessEvaluator(
            expected_symbols=self._expected,
            # EOD ignores this; LIVE has already been required above.
            live_max_age_s=live_max_age_s if live_max_age_s is not None else 0.0,
            eod_expected_trading_date=eod_expected_trading_date,
            min_coverage=self._min_coverage,
        )
        return evaluator.evaluate(
            profile,
            records,
            entitlement_ok=self._entitlement_ok,
            store_available=True,
            now=self._clock(),
        )

    async def status(
        self,
        *,
        live_max_age_s: float | None = None,
        eod_expected_trading_date: date | None = None,
    ) -> SipPlaneStatus:
        """Whole-plane operational status for an activation gate.

        Per-profile verdicts are reported separately and never collapsed. ``SIP_LIVE`` is reported
        only when a bound is supplied — otherwise there is no defensible freshness verdict to give.
        """
        now = self._clock()
        # Imported here rather than at module scope so the public consumer surface does not carry a
        # path to the producer identity module.
        from app.market_data.sip.identity import PRODUCER

        profiles: dict[str, SipProfileStatus] = {}
        wanted = [SipProfile.EOD] + ([SipProfile.LIVE] if live_max_age_s is not None else [])
        for profile in wanted:
            records = await self._cache.latest_for_profile(profile)
            r = await self.readiness(
                profile,
                live_max_age_s=live_max_age_s,
                eod_expected_trading_date=eod_expected_trading_date,
            )
            counts: dict[str, int] = {}
            for rec in records:
                key = rec.quality_classification or "attested"
                counts[key] = counts.get(key, 0) + 1
            newest = max((rec.source_timestamp for rec in records), default=None)
            profiles[str(profile)] = SipProfileStatus(
                profile=profile,
                readiness_state=r.state,
                last_transition_reason=r.reason,
                evaluated_at=r.evaluated_at,
                last_successful_acquisition=self._last_success.get(str(profile)),
                latest_observation=newest,
                observed_symbols=r.observed_symbols,
                expected_symbols=r.expected_symbols,
                coverage=r.coverage,
                age_s=(now - newest).total_seconds() if newest else None,
                entitlement_state="ok" if self._entitlement_ok else "ENTITLEMENT_FAIL",
                quality_counts=counts,
                acquisition_failures=self._acquisition_failures,
                retry_count=self._retry_count,
            )

        return SipPlaneStatus(
            # Non-secret reference: an operator can confirm WHICH identity is in force without this
            # package offering any way to change it.
            producer_fingerprint=PRODUCER.key_fingerprint,
            entitlement_identity=PRODUCER.entitlement_identity,
            cache_schema_version=CACHE_SCHEMA_VERSION,
            profiles=profiles,
        )

    # ---------------------------------------------------------------- producer-side telemetry

    def record_acquisition_result(self, profile: SipProfile, *, ok: bool, retried: int = 0) -> None:
        """Producer-side hook for observability counters. Not part of the consumer contract."""
        self._retry_count += retried
        if ok:
            self._last_success[str(profile)] = self._clock()
        else:
            self._acquisition_failures += 1


def build_consumer_service(session_factory: Any, **kw: Any) -> SipConsumerService:
    """Construct the consumer service. Takes a session factory — never a credential."""
    return SipConsumerService(SipOperationalCache(session_factory), **kw)
