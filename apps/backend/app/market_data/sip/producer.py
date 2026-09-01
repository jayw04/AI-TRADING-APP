"""SipProducer — the only path by which SIP data enters the Workbench (SIP-CACHE-001 §3, §8).

Every SIP request in the operational plane originates here, under the designated producer identity
and with ``feed=`` stated explicitly. Two controls make that structural rather than aspirational:

* ``check_marketdata_feed_pinning.sh`` (already wired at ``ci.yml``) AST-checks that every Alpaca
  data constructor receives an explicit, non-``None`` feed, and forbids env-driven feed defaults.
  Its stated hazard is exactly ours: *a subscription entitlement can silently switch an implicit IEX
  path to SIP with no code change.*
* :meth:`ProducerPins.verify` refuses any credential that is not the designated producer **before
  any network call is made** — a credential that would succeed at the provider is still refused.

⛔ **There is no failover branch in this module.** If the designated identity cannot provide SIP the
caller records ``ENTITLEMENT_FAIL`` for the whole plane. The 2026-08-31 census measured accounts 5
and 6 also returning recent-SIP 200; discovering and using one of them would silently rewrite the
provenance every cached record claims, and is prohibited (§11, §18).

⛔ **No order capability.** This module obtains a *market-data* credential for account 7. It does not
import the broker registry, does not construct a trading client, and confers no execution authority.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import structlog

from app.market_data.sip.identity import PRODUCER, ProducerIdentityError
from app.market_data.sip.profiles import SipProfile
from app.market_data.sip.schema import (
    CACHE_SCHEMA_VERSION,
    PROVIDER_ALPACA,
    SIP_FEED,
    SipRecord,
)

logger = structlog.get_logger(__name__)


class SipEntitlementError(RuntimeError):
    """The designated producer could not obtain SIP data.

    Carries the plane straight to ``ENTITLEMENT_FAIL``. It is never a prompt to try another
    credential.
    """


@dataclass(frozen=True)
class _Acquired:
    record: SipRecord
    fingerprint: str


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None


class SipProducer:
    """Acquires SIP observations under the designated producer identity."""

    def __init__(self, session_factory: Any) -> None:
        self._sf = session_factory

    async def _credentials(self) -> tuple[str, str, str]:
        """Resolve the designated producer's credential and verify the pin.

        Returns ``(api_key, api_secret, fingerprint)``. The key and secret are held only for the
        duration of the request and are never logged, stored, or returned to a caller outside this
        module.
        """
        from app.brokers.alpaca.credentials import credentials_for_mode

        creds = await credentials_for_mode("paper", PRODUCER.account_id, self._sf)
        # Verify BEFORE any network call. Entitlement is not authority.
        fingerprint = PRODUCER.verify(creds.api_key)
        return creds.api_key, creds.api_secret, fingerprint

    async def fetch_latest_quotes(
        self,
        symbols: list[str],
        *,
        profile: SipProfile,
        trading_date: date,
        session: str,
    ) -> list[SipRecord]:
        """Fetch current SIP quotes for ``symbols`` as the designated producer.

        Raises :class:`SipEntitlementError` if the provider refuses SIP for the designated
        identity, and :class:`ProducerIdentityError` if the resolved credential is not the pin.
        """
        if not symbols:
            return []

        api_key, api_secret, fingerprint = await self._credentials()
        loop = asyncio.get_running_loop()

        try:
            from alpaca.data.enums import DataFeed
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestQuoteRequest

            client = StockHistoricalDataClient(api_key=api_key, secret_key=api_secret)
            # feed is stated explicitly and is never defaulted or inferred (§9.2).
            req = StockLatestQuoteRequest(symbol_or_symbols=symbols, feed=DataFeed.SIP)
            result = await loop.run_in_executor(None, lambda: client.get_stock_latest_quote(req))
        except ProducerIdentityError:
            raise
        except Exception as exc:  # provider refusal, transport, SDK
            detail = str(exc)
            logger.warning(
                "sip_acquisition_failed",
                producer_fp=fingerprint,
                symbol_count=len(symbols),
                # The provider's message is safe (it names the subscription, not the key), but we
                # classify rather than echo it wholesale.
                classification=(
                    "subscription_not_permitted"
                    if "subscription does not permit" in detail.lower()
                    else "provider_error"
                ),
            )
            raise SipEntitlementError(
                "designated SIP producer could not acquire recent SIP data; the shared SIP plane "
                "fails closed. No alternative credential will be attempted."
            ) from exc
        finally:
            # Do not let the material outlive the request.
            api_key = api_secret = ""  # noqa: F841

        now = datetime.now(UTC)
        records: list[SipRecord] = []
        for symbol in symbols:
            q = result.get(symbol) if isinstance(result, dict) else result
            if q is None:
                continue
            ts = getattr(q, "timestamp", None)
            if ts is None:
                # No provider clock means no freshness basis. Refuse the row rather than
                # substitute our own receive time — that would silently make stale data look new.
                logger.warning("sip_record_dropped_no_source_timestamp", symbol=symbol)
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)

            # The SDK does not attest the served feed on every build. Where it does, record it;
            # where it does not, record the requested feed and mark the row so the limitation is
            # visible in the data rather than assumed away.
            served = getattr(q, "feed", None)
            quality = None if served else "feed_unattested"

            records.append(
                SipRecord(
                    symbol=symbol,
                    profile=profile,
                    trading_date=trading_date,
                    session=session,
                    source_timestamp=ts,
                    received_at_utc=now,
                    bid=_dec(getattr(q, "bid_price", None)),
                    ask=_dec(getattr(q, "ask_price", None)),
                    bid_size=_dec(getattr(q, "bid_size", None)),
                    ask_size=_dec(getattr(q, "ask_size", None)),
                    price=_dec(getattr(q, "ask_price", None))
                    or _dec(getattr(q, "bid_price", None)),
                    feed=SIP_FEED,
                    source_feed_identity=str(served) if served else SIP_FEED,
                    provider=PROVIDER_ALPACA,
                    entitlement_identity=PRODUCER.entitlement_identity,
                    credential_identity_fingerprint=fingerprint,
                    cache_schema_version=CACHE_SCHEMA_VERSION,
                    quality_classification=quality,
                )
            )

        logger.info(
            "sip_acquisition_completed",
            producer_fp=fingerprint,
            profile=str(profile),
            requested=len(symbols),
            acquired=len(records),
        )
        return records
