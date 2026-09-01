"""SIP-CACHE-READINESS — the five-state machine, evaluated per profile (SIP-CACHE-001 §9).

``PASS`` · ``STALE`` · ``INCOMPLETE`` · ``ENTITLEMENT_FAIL`` · ``ABSENT``

Two rules make this an evidence gate rather than a liveness indicator:

1. **Freshness is measured from ``source_timestamp``** — never ``received_at_utc``, never job
   completion. "The scheduled job ran" is not ``PASS``; a job that completes while returning stale
   or partial data is ``STALE`` or ``INCOMPLETE``.
2. **A single global verdict is prohibited.** ``SIP_EOD`` and ``SIP_LIVE`` are evaluated
   independently with different policies. A ``PASS`` on one says nothing about the other and must
   never be read as though it did.

``ENTITLEMENT_FAIL`` is plane-wide and is reached only via the designated producer. It is never
avoided by trying a different credential — see :mod:`app.market_data.sip.identity`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

import structlog

from app.market_data.sip.profiles import SipProfile

logger = structlog.get_logger(__name__)


class SipReadinessState(StrEnum):
    PASS = "PASS"
    STALE = "STALE"
    INCOMPLETE = "INCOMPLETE"
    ENTITLEMENT_FAIL = "ENTITLEMENT_FAIL"
    ABSENT = "ABSENT"


#: The states a declaring consumer must fail closed on. Only PASS permits use.
FAIL_CLOSED_STATES = frozenset(SipReadinessState) - {SipReadinessState.PASS}


@dataclass(frozen=True)
class SipReadiness:
    """One profile's readiness verdict, with the evidence that produced it."""

    profile: SipProfile
    state: SipReadinessState
    evaluated_at: datetime
    reason: str
    observed_symbols: int = 0
    expected_symbols: int = 0
    coverage: float = 0.0
    max_age_s: float | None = None
    newest_source_timestamp: datetime | None = None
    expected_trading_date: date | None = None

    @property
    def is_pass(self) -> bool:
        return self.state is SipReadinessState.PASS

    def raise_if_not_pass(self, consumer: str) -> None:
        """Fail closed for a ``requires_sip`` consumer (§10).

        ⛔ There is deliberately no ``fallback_feed`` parameter. A consumer that may legitimately
        proceed on IEX must have that fallback explicitly designed, registered and governed for that
        consumer; absent such a registration, readiness failure stops the consumer.
        """
        if not self.is_pass:
            raise SipNotReadyError(
                f"{consumer}: SIP {self.profile} readiness is {self.state} ({self.reason}). "
                "Failing closed. Falling back to IEX is not permitted without a registered, "
                "governed per-consumer fallback."
            )


class SipNotReadyError(RuntimeError):
    """A declaring consumer asked for SIP data the plane cannot vouch for."""


class SipReadinessEvaluator:
    """Evaluates readiness per profile from stored records only.

    Nothing is inherited across a restart: every evaluation recomputes from ``source_timestamp``.
    """

    def __init__(
        self,
        *,
        expected_symbols: int,
        live_max_age_s: float,
        eod_expected_trading_date: date | None = None,
        min_coverage: float = 1.0,
    ) -> None:
        self._expected = expected_symbols
        self._live_max_age_s = live_max_age_s
        self._eod_expected = eod_expected_trading_date
        self._min_coverage = min_coverage

    def evaluate(
        self,
        profile: SipProfile,
        records: list,
        *,
        entitlement_ok: bool = True,
        store_available: bool = True,
        now: datetime | None = None,
    ) -> SipReadiness:
        now = now or datetime.now(UTC)

        if not store_available:
            return SipReadiness(
                profile=profile,
                state=SipReadinessState.ABSENT,
                evaluated_at=now,
                reason="cache or data store unavailable",
                expected_symbols=self._expected,
            )

        # Entitlement is checked before freshness: a plane that cannot acquire is not merely stale,
        # and reporting STALE would understate it.
        if not entitlement_ok:
            return SipReadiness(
                profile=profile,
                state=SipReadinessState.ENTITLEMENT_FAIL,
                evaluated_at=now,
                reason=(
                    "designated SIP producer could not obtain SIP data; plane-wide fail-closed. "
                    "No alternative credential is attempted."
                ),
                expected_symbols=self._expected,
            )

        if not records:
            return SipReadiness(
                profile=profile,
                state=SipReadinessState.ABSENT,
                evaluated_at=now,
                reason="no cached records for this profile",
                expected_symbols=self._expected,
            )

        observed = len(records)
        coverage = observed / self._expected if self._expected else 0.0
        newest = max(r.source_timestamp for r in records)
        oldest = min(r.source_timestamp for r in records)

        if profile is SipProfile.LIVE:
            # Age is judged on the OLDEST record: a profile is only as fresh as its stalest symbol.
            age = (now - oldest).total_seconds()
            if age > self._live_max_age_s:
                return SipReadiness(
                    profile=profile,
                    state=SipReadinessState.STALE,
                    evaluated_at=now,
                    reason=(
                        f"oldest source_timestamp is {age:.1f}s old, exceeding the "
                        f"{self._live_max_age_s:.1f}s consumer bound"
                    ),
                    observed_symbols=observed,
                    expected_symbols=self._expected,
                    coverage=coverage,
                    max_age_s=age,
                    newest_source_timestamp=newest,
                )
            age_s: float | None = age
            expected_date = None
        else:
            # SIP_EOD freshness is expressed in trading days against the authoritative calendar,
            # never wall-clock arithmetic and never "yesterday".
            expected_date = self._eod_expected
            age_s = None
            if expected_date is not None:
                present = {r.trading_date for r in records}
                if expected_date not in present:
                    return SipReadiness(
                        profile=profile,
                        state=SipReadinessState.STALE,
                        evaluated_at=now,
                        reason=(
                            f"expected completed trading date {expected_date} absent; "
                            f"newest present is {max(present)}"
                        ),
                        observed_symbols=observed,
                        expected_symbols=self._expected,
                        coverage=coverage,
                        newest_source_timestamp=newest,
                        expected_trading_date=expected_date,
                    )

        if coverage < self._min_coverage:
            return SipReadiness(
                profile=profile,
                state=SipReadinessState.INCOMPLETE,
                evaluated_at=now,
                reason=(
                    f"coverage {coverage:.4f} below required {self._min_coverage:.4f} "
                    f"({observed}/{self._expected} symbols)"
                ),
                observed_symbols=observed,
                expected_symbols=self._expected,
                coverage=coverage,
                max_age_s=age_s,
                newest_source_timestamp=newest,
                expected_trading_date=expected_date,
            )

        return SipReadiness(
            profile=profile,
            state=SipReadinessState.PASS,
            evaluated_at=now,
            reason="expected date present, age within tolerance, coverage satisfied",
            observed_symbols=observed,
            expected_symbols=self._expected,
            coverage=coverage,
            max_age_s=age_s,
            newest_source_timestamp=newest,
            expected_trading_date=expected_date,
        )
