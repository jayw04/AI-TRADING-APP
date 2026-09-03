"""SIP-CACHE-001 Implementation B3 — governed market-data demand: registry, leases, union.

The distinction this module keeps structural (owner rulings 2026-09-01 / 2026-09-02):

    SELECTION UNIVERSE  ≠  MARKET-DATA DEMAND  ≠  HOLDINGS

Demand is *current execution/decision need*. A lease says which symbols a registered consumer needs
data for, why (a closed :class:`DemandReason`), on which profile, and until when. It never carries
a credential, feed selector, account id, or clock (the B1 invariant: consumers cannot express trust
inputs), and for ``SIP_LIVE`` it never carries a freshness bound of its own — the bound is resolved
from the consumer's *governed execution policy* at publish time and stamped onto the lease
(B3 Decision 3). A LIVE consumer with no governed bound is refused ``FRESHNESS_UNBOUND``; there is no
default, no inheritance, no best effort (B3 Decision 5).

Authority model:

* A consumer exists only because the versioned registry artifact named it and an operator applied
  it (:meth:`ConsumerRegistry.apply_artifact`). Nothing is discovered (B3 Decision 1).
* A consumer publishes through a :class:`ConsumerGrant` — a capability minted by the registry for a
  live registration. There is no string-typed ``consumer_id`` parameter on the publish surface, so
  identity cannot be self-nominated.
* Every capacity number (per-consumer cap, plane cap, lease maximum, producer floor) is *required
  configuration*. Absence fails closed (B3 Decision 2). This module contains no numeric defaults.

Audit (B3 Decision 4): ``REQUESTED`` ≠ ``ADMITTED`` ≠ ``SERVED``. A request proves a consumer asked;
admission proves the plane accepted the obligation; only a ``SERVED`` row proves data was acquired.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

import structlog
from sqlalchemy import select

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.enums import ENGINE_RUNNABLE_STATUSES
from app.db.models.sip_demand import SipConsumerRegistration, SipDemandLease
from app.db.models.strategy import Strategy as StrategyRow
from app.market_data.sip.profiles import SipProfile

logger = structlog.get_logger(__name__)

_ACTOR = "sip_demand"
_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,15}$")
_CONSUMER_ID_RE = re.compile(r"^(strategy|service):[a-z0-9][a-z0-9\-]{0,61}$")


# ----------------------------------------------------------------------------- closed enums


class DemandReason(StrEnum):
    """Why a consumer needs data for a symbol. Closed; the LIVE subset is the B3 correction."""

    HELD = "HELD"
    PENDING_ENTRY = "PENDING_ENTRY"
    PENDING_EXIT = "PENDING_EXIT"
    DECISION_WINDOW = "DECISION_WINDOW"
    EOD_FEATURE = "EOD_FEATURE"
    SELECTION_UNIVERSE = "SELECTION_UNIVERSE"


#: A SIP_LIVE lease may express economic need in exactly these four ways. It cannot express a
#: universe at all — SELECTION_UNIVERSE and EOD_FEATURE are unrepresentable on LIVE.
LIVE_REASONS: frozenset[DemandReason] = frozenset(
    {
        DemandReason.HELD,
        DemandReason.PENDING_ENTRY,
        DemandReason.PENDING_EXIT,
        DemandReason.DECISION_WINDOW,
    }
)
EOD_REASONS: frozenset[DemandReason] = frozenset(DemandReason)

REASONS_FOR_PROFILE: Mapping[SipProfile, frozenset[DemandReason]] = {
    SipProfile.LIVE: LIVE_REASONS,
    SipProfile.EOD: EOD_REASONS,
}


class LeaseStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    WITHDRAWN = "WITHDRAWN"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class LeaseRejection(StrEnum):
    """Every way a lease can be refused. Each value is audited as SIP_DEMAND_REJECTED."""

    GRANT_INVALID = "GRANT_INVALID"
    UNREGISTERED_CONSUMER = "UNREGISTERED_CONSUMER"
    CONSUMER_REVOKED = "CONSUMER_REVOKED"
    PROFILE_NOT_PERMITTED = "PROFILE_NOT_PERMITTED"
    REASON_NOT_PERMITTED = "REASON_NOT_PERMITTED"
    EMPTY_SYMBOL_SET = "EMPTY_SYMBOL_SET"
    MALFORMED_SYMBOL = "MALFORMED_SYMBOL"
    REASON_MISSING = "REASON_MISSING"
    REASON_NOT_ALLOWED_FOR_PROFILE = "REASON_NOT_ALLOWED_FOR_PROFILE"
    FRESHNESS_UNBOUND = "FRESHNESS_UNBOUND"
    EXPIRY_IN_PAST = "EXPIRY_IN_PAST"
    EXPIRY_EXCEEDS_MAX = "EXPIRY_EXCEEDS_MAX"
    LEASE_MAX_UNCONFIGURED = "LEASE_MAX_UNCONFIGURED"
    CONSUMER_CAP_EXCEEDED = "CONSUMER_CAP_EXCEEDED"
    PLANE_CAP_EXCEEDED = "PLANE_CAP_EXCEEDED"
    PLANE_CAP_UNCONFIGURED = "PLANE_CAP_UNCONFIGURED"
    PRODUCER_FLOOR_UNCONFIGURED = "PRODUCER_FLOOR_UNCONFIGURED"
    BOUND_BELOW_PRODUCER_FLOOR = "BOUND_BELOW_PRODUCER_FLOOR"
    EOD_TOLERANCE_INVALID = "EOD_TOLERANCE_INVALID"


# ----------------------------------------------------------------------------- configuration


@dataclass(frozen=True)
class DemandPlaneConfig:
    """Capacity policy, all Optional, all required. ``None`` fails closed everywhere it is read."""

    live_plane_symbol_cap: int | None
    eod_plane_symbol_cap: int | None
    live_max_lease_s: float | None
    eod_max_lease_days: int | None
    live_min_interval_s: float | None
    live_max_interval_s: float | None

    @classmethod
    def from_settings(cls, settings: Any) -> DemandPlaneConfig:
        return cls(
            live_plane_symbol_cap=settings.sip_live_plane_symbol_cap,
            eod_plane_symbol_cap=settings.sip_eod_plane_symbol_cap,
            live_max_lease_s=settings.sip_live_max_lease_s,
            eod_max_lease_days=settings.sip_eod_max_lease_days,
            live_min_interval_s=settings.sip_live_min_interval_s,
            live_max_interval_s=settings.sip_live_max_interval_s,
        )

    def plane_cap(self, profile: SipProfile) -> int | None:
        return (
            self.live_plane_symbol_cap if profile is SipProfile.LIVE else self.eod_plane_symbol_cap
        )

    def max_lease(self, profile: SipProfile) -> timedelta | None:
        if profile is SipProfile.LIVE:
            return (
                None if self.live_max_lease_s is None else timedelta(seconds=self.live_max_lease_s)
            )
        return None if self.eod_max_lease_days is None else timedelta(days=self.eod_max_lease_days)


class FreshnessPolicyProvider(Protocol):
    """The seam through which a consumer's *governed execution policy* supplies its LIVE bound."""

    async def live_max_age_s(self, consumer_id: str, policy_ref: str | None) -> float | None: ...


class NoFreshnessPolicy:
    """The only production provider in B3: no consumer has a frozen freshness policy yet.

    Returns ``None`` for everyone, so every LIVE lease is refused ``FRESHNESS_UNBOUND``. That is the
    intended fail-closed state until Strategy 9's execution policy exists — not a placeholder to be
    replaced by a number here.
    """

    async def live_max_age_s(self, consumer_id: str, policy_ref: str | None) -> float | None:
        return None


# ----------------------------------------------------------------------------- value objects


@dataclass(frozen=True)
class ConsumerGrant:
    """Capability to publish demand as one registered consumer.

    Minted only by :meth:`ConsumerRegistry.grant`. The nonce is per registry instance, so a grant
    assembled from a known ``consumer_id`` string outside the registry is refused ``GRANT_INVALID``.
    """

    registration_id: str
    _nonce: bytes = field(repr=False, compare=True)


@dataclass(frozen=True)
class DemandLease:
    """What a consumer asks for. No credential, feed, account, clock, or LIVE bound field exists."""

    profile: SipProfile
    symbols: frozenset[str]
    reasons: Mapping[str, DemandReason]
    expires_at: datetime
    max_age_trading_days: int | None = None


@dataclass(frozen=True)
class LeaseReceipt:
    accepted: bool
    lease_id: int | None = None
    rejection: LeaseRejection | None = None
    effective_from: datetime | None = None
    expires_at: datetime | None = None
    max_age_s: float | None = None
    superseded_lease_id: int | None = None


@dataclass(frozen=True)
class ProfileDemand:
    profile: SipProfile
    symbols: frozenset[str]
    per_symbol_bound_s: Mapping[str, float]
    strictest_bound_s: float | None
    lease_count: int
    consumer_ids: frozenset[str]
    lease_ids: frozenset[int]
    materialized_at: datetime


@dataclass(frozen=True)
class ProfileDemandStatus:
    profile: SipProfile
    active_leases: int
    union_size: int
    strictest_bound_s: float | None
    plane_cap: int | None
    cap_headroom: int | None


@dataclass(frozen=True)
class DemandPlaneStatus:
    registry_verified: bool
    artifact_sha256: str | None
    registered_consumers: int
    rejected_count: int
    last_rejection: str | None
    profiles: dict[str, ProfileDemandStatus] = field(default_factory=dict)


@dataclass(frozen=True)
class ApplyResult:
    artifact_sha256: str
    issued: tuple[str, ...]
    updated: tuple[str, ...]
    revoked: tuple[str, ...]
    dry_run: bool


class RegistryArtifactError(ValueError):
    """The artifact is malformed or an entry is invalid. Nothing is applied."""


# ----------------------------------------------------------------------------- helpers


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def artifact_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _loads_list(text: str) -> list[str]:
    value = json.loads(text)
    return [str(v) for v in value]


# ----------------------------------------------------------------------------- registry


class ConsumerRegistry:
    """Governed registrations + demand leases. All writes audited; no discovery; no defaults."""

    def __init__(
        self,
        session_factory: Any,
        *,
        config: DemandPlaneConfig,
        policy: FreshnessPolicyProvider,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._sf = session_factory
        self._config = config
        self._policy = policy
        self._clock: Callable[[], datetime] = clock or _now_utc
        self._grants: dict[str, bytes] = {}
        self._rejected_count = 0
        self._last_rejection: str | None = None
        self._verified_sha: str | None = None
        self._registry_verified = False

    # ------------------------------------------------------------------ artifact (Decision 1)

    @staticmethod
    def validate_artifact(artifact: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Validate every entry before anything is applied. Raises on the first defect."""
        if artifact.get("schema_version") != 1:
            raise RegistryArtifactError("schema_version must be 1")
        consumers = artifact.get("consumers")
        if not isinstance(consumers, list):
            raise RegistryArtifactError("consumers must be a list")
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for raw in consumers:
            if not isinstance(raw, Mapping):
                raise RegistryArtifactError("consumer entry must be an object")
            cid = str(raw.get("consumer_id", ""))
            if not _CONSUMER_ID_RE.match(cid):
                raise RegistryArtifactError(f"invalid consumer_id {cid!r}")
            if cid in seen:
                raise RegistryArtifactError(f"duplicate consumer_id {cid!r}")
            seen.add(cid)
            kind = cid.split(":", 1)[0]
            if raw.get("kind") != kind:
                raise RegistryArtifactError(f"{cid}: kind must be {kind!r}")
            strategy_id = raw.get("strategy_id")
            if kind == "strategy" and not isinstance(strategy_id, int):
                raise RegistryArtifactError(f"{cid}: strategy consumers require strategy_id")
            if kind == "service" and strategy_id is not None:
                raise RegistryArtifactError(f"{cid}: service consumers carry no strategy_id")
            user_id = raw.get("user_id")
            if not isinstance(user_id, int):
                raise RegistryArtifactError(f"{cid}: user_id required")
            profiles_raw = raw.get("allowed_profiles")
            if not isinstance(profiles_raw, list) or not profiles_raw:
                raise RegistryArtifactError(f"{cid}: allowed_profiles must be a non-empty list")
            try:
                profiles = [SipProfile(p) for p in profiles_raw]
            except ValueError as exc:
                raise RegistryArtifactError(f"{cid}: unknown profile") from exc
            reasons_raw = raw.get("allowed_reasons")
            if not isinstance(reasons_raw, list) or not reasons_raw:
                raise RegistryArtifactError(f"{cid}: allowed_reasons must be a non-empty list")
            try:
                reasons = [DemandReason(r) for r in reasons_raw]
            except ValueError as exc:
                raise RegistryArtifactError(f"{cid}: unknown reason") from exc
            # Caps: required for every allowed profile; a cap without an allowed profile is 0.
            caps: dict[SipProfile, int] = {}
            for profile, key in (
                (SipProfile.EOD, "symbol_cap_eod"),
                (SipProfile.LIVE, "symbol_cap_live"),
            ):
                cap = raw.get(key)
                if profile in profiles:
                    if not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0:
                        raise RegistryArtifactError(
                            f"{cid}: {key} is required (positive int) for an allowed profile"
                        )
                    caps[profile] = cap
                else:
                    if cap not in (None, 0):
                        raise RegistryArtifactError(f"{cid}: {key} set for a non-allowed profile")
                    caps[profile] = 0
            policy_ref = raw.get("freshness_policy_ref")
            if policy_ref is not None and not isinstance(policy_ref, str):
                raise RegistryArtifactError(f"{cid}: freshness_policy_ref must be a string")
            out.append(
                {
                    "consumer_id": cid,
                    "kind": kind,
                    "strategy_id": strategy_id,
                    "user_id": user_id,
                    "allowed_profiles": [str(p) for p in profiles],
                    "allowed_reasons": [str(r) for r in reasons],
                    "symbol_cap_eod": caps[SipProfile.EOD],
                    "symbol_cap_live": caps[SipProfile.LIVE],
                    "freshness_policy_ref": policy_ref,
                }
            )
        return out

    async def apply_artifact(
        self,
        artifact: Mapping[str, Any],
        *,
        artifact_sha256: str,
        applied_by: str,
        dry_run: bool = True,
    ) -> ApplyResult:
        """Apply the artifact: upsert every listed consumer, revoke every unlisted live one.

        Validation is all-or-nothing. Every issuance/revocation is audited under ``applied_by``.
        """
        entries = self.validate_artifact(artifact)
        now = self._clock()
        issued: list[str] = []
        updated: list[str] = []
        revoked: list[str] = []
        async with self._sf() as s:
            rows = (await s.execute(select(SipConsumerRegistration))).scalars().all()
            by_id = {r.consumer_id: r for r in rows}
            listed = {e["consumer_id"] for e in entries}
            for e in entries:
                row = by_id.get(e["consumer_id"])
                payload = {**e, "artifact_sha256": artifact_sha256}
                if row is None:
                    issued.append(e["consumer_id"])
                    if not dry_run:
                        s.add(
                            SipConsumerRegistration(
                                consumer_id=e["consumer_id"],
                                kind=e["kind"],
                                strategy_id=e["strategy_id"],
                                user_id=e["user_id"],
                                allowed_profiles=json.dumps(e["allowed_profiles"]),
                                allowed_reasons=json.dumps(e["allowed_reasons"]),
                                symbol_cap_eod=e["symbol_cap_eod"],
                                symbol_cap_live=e["symbol_cap_live"],
                                freshness_policy_ref=e["freshness_policy_ref"],
                                artifact_sha256=artifact_sha256,
                                applied_at=now,
                                applied_by=applied_by,
                            )
                        )
                else:
                    updated.append(e["consumer_id"])
                    if not dry_run:
                        row.kind = e["kind"]
                        row.strategy_id = e["strategy_id"]
                        row.user_id = e["user_id"]
                        row.allowed_profiles = json.dumps(e["allowed_profiles"])
                        row.allowed_reasons = json.dumps(e["allowed_reasons"])
                        row.symbol_cap_eod = e["symbol_cap_eod"]
                        row.symbol_cap_live = e["symbol_cap_live"]
                        row.freshness_policy_ref = e["freshness_policy_ref"]
                        row.artifact_sha256 = artifact_sha256
                        row.applied_at = now
                        row.applied_by = applied_by
                        row.revoked_at = None
                        row.revoked_by = None
                        row.revocation_reason = None
                if not dry_run:
                    AuditLogger.write(
                        s,
                        actor_type=AuditActorType.USER,
                        actor_id=applied_by,
                        action=AuditAction.SIP_CONSUMER_GRANT_ISSUED,
                        target_type="sip_consumer",
                        target_id=e["consumer_id"],
                        payload=payload,
                        user_id=e["user_id"],
                    )
            for cid, row in by_id.items():
                if cid in listed or row.revoked_at is not None:
                    continue
                revoked.append(cid)
                if not dry_run:
                    row.revoked_at = now
                    row.revoked_by = applied_by
                    row.revocation_reason = "absent_from_artifact"
                    AuditLogger.write(
                        s,
                        actor_type=AuditActorType.USER,
                        actor_id=applied_by,
                        action=AuditAction.SIP_CONSUMER_GRANT_REVOKED,
                        target_type="sip_consumer",
                        target_id=cid,
                        payload={
                            "reason": "absent_from_artifact",
                            "artifact_sha256": artifact_sha256,
                        },
                        user_id=row.user_id,
                    )
                    self._grants.pop(cid, None)
            if not dry_run:
                await s.commit()
        if not dry_run:
            # Revoking a consumer revokes its demand (Decision 1: lifecycle/revocation authority).
            for cid in revoked:
                await self._revoke_leases(cid, reason="consumer_revoked", actor=applied_by)
        logger.info(
            "sip_registry_applied",
            dry_run=dry_run,
            issued=issued,
            updated=updated,
            revoked=revoked,
            artifact_sha256=artifact_sha256,
        )
        return ApplyResult(
            artifact_sha256=artifact_sha256,
            issued=tuple(issued),
            updated=tuple(updated),
            revoked=tuple(revoked),
            dry_run=dry_run,
        )

    async def verify_artifact(self, artifact_sha256: str) -> bool:
        """Startup verification: every live registration was applied from THIS artifact."""
        async with self._sf() as s:
            rows = (
                (
                    await s.execute(
                        select(SipConsumerRegistration).where(
                            SipConsumerRegistration.revoked_at.is_(None)
                        )
                    )
                )
                .scalars()
                .all()
            )
        ok = all(r.artifact_sha256 == artifact_sha256 for r in rows)
        self._registry_verified = ok
        self._verified_sha = artifact_sha256 if ok else None
        if not ok:
            logger.error(
                "sip_registry_artifact_mismatch",
                expected=artifact_sha256,
                found=sorted({r.artifact_sha256 for r in rows}),
            )
        return ok

    # ------------------------------------------------------------------ grants

    async def grant(self, consumer_id: str) -> ConsumerGrant:
        """Mint the publish capability for a live registration. Platform-side only."""
        reg = await self._registration(consumer_id)
        if reg is None or reg.revoked_at is not None:
            raise PermissionError(f"no live registration for {consumer_id!r}")
        nonce = self._grants.get(consumer_id)
        if nonce is None:
            nonce = secrets.token_bytes(16)
            self._grants[consumer_id] = nonce
        return ConsumerGrant(consumer_id, nonce)

    def _grant_valid(self, grant: ConsumerGrant) -> bool:
        nonce = self._grants.get(grant.registration_id)
        return nonce is not None and secrets.compare_digest(nonce, grant._nonce)

    async def _registration(self, consumer_id: str) -> SipConsumerRegistration | None:
        async with self._sf() as s:
            return await s.get(SipConsumerRegistration, consumer_id)

    # ------------------------------------------------------------------ publish

    async def publish(self, grant: ConsumerGrant, lease: DemandLease) -> LeaseReceipt:
        """Validate and admit a lease. REQUESTED is audited before validation; the outcome after."""
        now = self._clock()
        cid = grant.registration_id
        symbols = sorted(lease.symbols)
        request_payload = {
            "consumer_id": cid,
            "profile": str(lease.profile),
            "symbol_count": len(symbols),
            "symbols": symbols,
            "reasons": {k: str(v) for k, v in lease.reasons.items()},
            "expires_at": lease.expires_at.isoformat() if lease.expires_at else None,
        }
        async with self._sf() as s:
            reg = await s.get(SipConsumerRegistration, cid)
            req_row = AuditLogger.write(
                s,
                actor_type=AuditActorType.SYSTEM,
                actor_id=_ACTOR,
                action=AuditAction.SIP_DEMAND_REQUESTED,
                target_type="sip_consumer",
                target_id=cid,
                payload=request_payload,
                user_id=reg.user_id if reg is not None else None,
            )
            await s.flush()
            request_audit_id = req_row.id

            rejection, bound = await self._validate(s, grant, reg, lease, now)
            if rejection is not None:
                self._rejected_count += 1
                self._last_rejection = str(rejection)
                AuditLogger.write(
                    s,
                    actor_type=AuditActorType.SYSTEM,
                    actor_id=_ACTOR,
                    action=AuditAction.SIP_DEMAND_REJECTED,
                    target_type="sip_consumer",
                    target_id=cid,
                    payload={
                        **request_payload,
                        "rejection": str(rejection),
                        "request_audit_id": request_audit_id,
                    },
                    user_id=reg.user_id if reg is not None else None,
                )
                await s.commit()
                logger.warning("sip_demand_rejected", consumer_id=cid, rejection=str(rejection))
                return LeaseReceipt(accepted=False, rejection=rejection)

            assert reg is not None  # validated above
            max_lease = self._config.max_lease(lease.profile)
            assert max_lease is not None  # validated above
            # Supersede this consumer's current ACTIVE lease for the profile (renewal chain).
            prior = (
                (
                    await s.execute(
                        select(SipDemandLease).where(
                            SipDemandLease.consumer_id == cid,
                            SipDemandLease.profile == str(lease.profile),
                            SipDemandLease.status == str(LeaseStatus.ACTIVE),
                        )
                    )
                )
                .scalars()
                .all()
            )
            row = SipDemandLease(
                consumer_id=cid,
                profile=str(lease.profile),
                symbols=json.dumps(symbols),
                reasons=json.dumps({k: str(v) for k, v in lease.reasons.items()}),
                max_age_s=(Decimal(str(bound)) if bound is not None else None),
                max_age_trading_days=(
                    (lease.max_age_trading_days or 1) if lease.profile is SipProfile.EOD else None
                ),
                effective_from=now,
                expires_at=_aware(lease.expires_at),
                status=str(LeaseStatus.ACTIVE),
                request_audit_id=request_audit_id,
            )
            s.add(row)
            await s.flush()
            superseded_id: int | None = None
            for p in prior:
                p.status = str(LeaseStatus.SUPERSEDED)
                p.status_reason = "renewed"
                p.status_changed_at = now
                p.superseded_by = row.id
                superseded_id = p.id
            admitted_payload = {
                **request_payload,
                "lease_id": row.id,
                "request_audit_id": request_audit_id,
                "effective_from": now.isoformat(),
                "max_age_s": bound,
                "max_age_trading_days": row.max_age_trading_days,
                "superseded_lease_id": superseded_id,
            }
            AuditLogger.write(
                s,
                actor_type=AuditActorType.SYSTEM,
                actor_id=_ACTOR,
                action=(
                    AuditAction.SIP_DEMAND_RENEWED
                    if superseded_id is not None
                    else AuditAction.SIP_DEMAND_ADMITTED
                ),
                target_type="sip_lease",
                target_id=row.id,
                payload=admitted_payload,
                user_id=reg.user_id,
            )
            await s.commit()
            lease_id = row.id
        logger.info(
            "sip_demand_admitted",
            consumer_id=cid,
            lease_id=lease_id,
            profile=str(lease.profile),
            symbol_count=len(symbols),
            max_age_s=bound,
        )
        return LeaseReceipt(
            accepted=True,
            lease_id=lease_id,
            effective_from=now,
            expires_at=_aware(lease.expires_at),
            max_age_s=bound,
            superseded_lease_id=superseded_id,
        )

    async def _validate(
        self,
        s: Any,
        grant: ConsumerGrant,
        reg: SipConsumerRegistration | None,
        lease: DemandLease,
        now: datetime,
    ) -> tuple[LeaseRejection | None, float | None]:
        if not self._grant_valid(grant):
            return LeaseRejection.GRANT_INVALID, None
        if reg is None:
            return LeaseRejection.UNREGISTERED_CONSUMER, None
        if reg.revoked_at is not None:
            return LeaseRejection.CONSUMER_REVOKED, None
        allowed_profiles = _loads_list(reg.allowed_profiles)
        if str(lease.profile) not in allowed_profiles:
            return LeaseRejection.PROFILE_NOT_PERMITTED, None
        if not lease.symbols:
            return LeaseRejection.EMPTY_SYMBOL_SET, None
        for sym in lease.symbols:
            if not isinstance(sym, str) or not _SYMBOL_RE.match(sym):
                return LeaseRejection.MALFORMED_SYMBOL, None
        allowed_reasons = {DemandReason(r) for r in _loads_list(reg.allowed_reasons)}
        profile_reasons = REASONS_FOR_PROFILE[lease.profile]
        for sym in lease.symbols:
            reason = lease.reasons.get(sym)
            if reason is None:
                return LeaseRejection.REASON_MISSING, None
            if reason not in profile_reasons:
                return LeaseRejection.REASON_NOT_ALLOWED_FOR_PROFILE, None
            if reason not in allowed_reasons:
                return LeaseRejection.REASON_NOT_PERMITTED, None
        # Expiry: required (type-enforced), in the future, within the configured maximum.
        max_lease = self._config.max_lease(lease.profile)
        if max_lease is None:
            return LeaseRejection.LEASE_MAX_UNCONFIGURED, None
        expires = _aware(lease.expires_at)
        if expires <= now:
            return LeaseRejection.EXPIRY_IN_PAST, None
        if expires > now + max_lease:
            return LeaseRejection.EXPIRY_EXCEEDS_MAX, None
        bound: float | None = None
        if lease.profile is SipProfile.LIVE:
            # Decision 3/5: the bound comes from the governed policy, or the lease is refused.
            bound = await self._policy.live_max_age_s(reg.consumer_id, reg.freshness_policy_ref)
            if bound is None or bound <= 0:
                return LeaseRejection.FRESHNESS_UNBOUND, None
            floor = self._config.live_min_interval_s
            if floor is None:
                return LeaseRejection.PRODUCER_FLOOR_UNCONFIGURED, None
            if bound < 2 * floor:
                return LeaseRejection.BOUND_BELOW_PRODUCER_FLOOR, None
        else:
            tol = lease.max_age_trading_days if lease.max_age_trading_days is not None else 1
            if tol < 1:
                return LeaseRejection.EOD_TOLERANCE_INVALID, None
        # Caps: consumer, then plane. Overflow rejects THIS submission; nothing is truncated.
        cap = reg.symbol_cap_live if lease.profile is SipProfile.LIVE else reg.symbol_cap_eod
        if len(lease.symbols) > cap:
            return LeaseRejection.CONSUMER_CAP_EXCEEDED, None
        plane_cap = self._config.plane_cap(lease.profile)
        if plane_cap is None:
            return LeaseRejection.PLANE_CAP_UNCONFIGURED, None
        others = await self._active_symbols_excluding(s, lease.profile, reg.consumer_id, now)
        if len(others | set(lease.symbols)) > plane_cap:
            return LeaseRejection.PLANE_CAP_EXCEEDED, None
        return None, bound

    async def _active_symbols_excluding(
        self, s: Any, profile: SipProfile, consumer_id: str, now: datetime
    ) -> set[str]:
        rows = (
            (
                await s.execute(
                    select(SipDemandLease).where(
                        SipDemandLease.profile == str(profile),
                        SipDemandLease.status == str(LeaseStatus.ACTIVE),
                        SipDemandLease.consumer_id != consumer_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        out: set[str] = set()
        for r in rows:
            if _aware(r.expires_at) > now:
                out.update(_loads_list(r.symbols))
        return out

    # ------------------------------------------------------------------ withdraw / revoke / expire

    async def withdraw(self, grant: ConsumerGrant, lease_id: int) -> bool:
        if not self._grant_valid(grant):
            return False
        now = self._clock()
        async with self._sf() as s:
            row = await s.get(SipDemandLease, lease_id)
            if row is None or row.consumer_id != grant.registration_id:
                return False
            if row.status != str(LeaseStatus.ACTIVE):
                return False
            row.status = str(LeaseStatus.WITHDRAWN)
            row.status_reason = "consumer_withdrawal"
            row.status_changed_at = now
            reg = await s.get(SipConsumerRegistration, row.consumer_id)
            AuditLogger.write(
                s,
                actor_type=AuditActorType.SYSTEM,
                actor_id=_ACTOR,
                action=AuditAction.SIP_DEMAND_WITHDRAWN,
                target_type="sip_lease",
                target_id=lease_id,
                payload={"consumer_id": row.consumer_id, "profile": row.profile},
                user_id=reg.user_id if reg is not None else None,
            )
            await s.commit()
        return True

    async def revoke(self, grant: ConsumerGrant, *, reason: str) -> int:
        if not self._grant_valid(grant):
            return 0
        return await self._revoke_leases(grant.registration_id, reason=reason, actor=_ACTOR)

    async def revoke_for_strategy(self, strategy_id: int, *, reason: str) -> int:
        """Platform-side: the strategy runtime stops a strategy ⇒ its demand is removed NOW."""
        async with self._sf() as s:
            regs = (
                (
                    await s.execute(
                        select(SipConsumerRegistration).where(
                            SipConsumerRegistration.strategy_id == strategy_id
                        )
                    )
                )
                .scalars()
                .all()
            )
        total = 0
        for reg in regs:
            total += await self._revoke_leases(reg.consumer_id, reason=reason, actor=_ACTOR)
        return total

    async def _revoke_leases(self, consumer_id: str, *, reason: str, actor: str) -> int:
        now = self._clock()
        async with self._sf() as s:
            rows = (
                (
                    await s.execute(
                        select(SipDemandLease).where(
                            SipDemandLease.consumer_id == consumer_id,
                            SipDemandLease.status == str(LeaseStatus.ACTIVE),
                        )
                    )
                )
                .scalars()
                .all()
            )
            reg = await s.get(SipConsumerRegistration, consumer_id)
            for r in rows:
                r.status = str(LeaseStatus.REVOKED)
                r.status_reason = reason[:256]
                r.status_changed_at = now
                AuditLogger.write(
                    s,
                    actor_type=AuditActorType.SYSTEM,
                    actor_id=actor,
                    action=AuditAction.SIP_DEMAND_REVOKED,
                    target_type="sip_lease",
                    target_id=r.id,
                    payload={"consumer_id": consumer_id, "profile": r.profile, "reason": reason},
                    user_id=reg.user_id if reg is not None else None,
                )
            await s.commit()
        if rows:
            logger.info(
                "sip_demand_revoked", consumer_id=consumer_id, count=len(rows), reason=reason
            )
        return len(rows)

    async def expire_due(self) -> int:
        """Scheduler tick: expire lapsed leases, and reconcile leases whose strategy is no longer
        runnable (the backstop for a runtime that died before calling ``revoke``)."""
        now = self._clock()
        expired = 0
        reconciled: list[tuple[str, str]] = []
        async with self._sf() as s:
            rows = (
                (
                    await s.execute(
                        select(SipDemandLease).where(
                            SipDemandLease.status == str(LeaseStatus.ACTIVE)
                        )
                    )
                )
                .scalars()
                .all()
            )
            for r in rows:
                if _aware(r.expires_at) <= now:
                    r.status = str(LeaseStatus.EXPIRED)
                    r.status_reason = "expired"
                    r.status_changed_at = now
                    reg = await s.get(SipConsumerRegistration, r.consumer_id)
                    AuditLogger.write(
                        s,
                        actor_type=AuditActorType.SYSTEM,
                        actor_id=_ACTOR,
                        action=AuditAction.SIP_DEMAND_EXPIRED,
                        target_type="sip_lease",
                        target_id=r.id,
                        payload={
                            "consumer_id": r.consumer_id,
                            "profile": r.profile,
                            "expires_at": _aware(r.expires_at).isoformat(),
                        },
                        user_id=reg.user_id if reg is not None else None,
                    )
                    expired += 1
                    continue
                reg = await s.get(SipConsumerRegistration, r.consumer_id)
                if reg is not None and reg.strategy_id is not None:
                    strat = await s.get(StrategyRow, reg.strategy_id)
                    if strat is None or strat.status not in ENGINE_RUNNABLE_STATUSES:
                        reconciled.append((r.consumer_id, "strategy_not_runnable"))
            await s.commit()
        for cid, reason in {c: r for c, r in reconciled}.items():
            expired += await self._revoke_leases(cid, reason=reason, actor=_ACTOR)
        return expired

    # ------------------------------------------------------------------ served (scheduler-side)

    async def mark_served(
        self, profile: SipProfile, symbols: Iterable[str], *, trading_date: date
    ) -> int:
        """Audit SERVED for every ACTIVE lease whose symbols were just written. Scheduler-side."""
        served = set(symbols)
        if not served:
            return 0
        now = self._clock()
        count = 0
        async with self._sf() as s:
            rows = (
                (
                    await s.execute(
                        select(SipDemandLease).where(
                            SipDemandLease.profile == str(profile),
                            SipDemandLease.status == str(LeaseStatus.ACTIVE),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for r in rows:
                if _aware(r.expires_at) <= now:
                    continue
                wanted = set(_loads_list(r.symbols))
                hit = sorted(wanted & served)
                if not hit:
                    continue
                reg = await s.get(SipConsumerRegistration, r.consumer_id)
                AuditLogger.write(
                    s,
                    actor_type=AuditActorType.SYSTEM,
                    actor_id=_ACTOR,
                    action=AuditAction.SIP_DEMAND_SERVED,
                    target_type="sip_lease",
                    target_id=r.id,
                    payload={
                        "consumer_id": r.consumer_id,
                        "profile": r.profile,
                        "trading_date": trading_date.isoformat(),
                        "served": hit,
                        "missing": sorted(wanted - served),
                    },
                    user_id=reg.user_id if reg is not None else None,
                )
                count += 1
            await s.commit()
        return count

    # ------------------------------------------------------------------ status

    @property
    def rejected_count(self) -> int:
        return self._rejected_count

    @property
    def last_rejection(self) -> str | None:
        return self._last_rejection

    @property
    def registry_verified(self) -> bool:
        return self._registry_verified

    @property
    def verified_sha256(self) -> str | None:
        return self._verified_sha

    @property
    def config(self) -> DemandPlaneConfig:
        return self._config


# ----------------------------------------------------------------------------- union


class DemandUnion:
    """The scheduler's only source of "what to fetch": the union of ACTIVE, unexpired leases."""

    def __init__(
        self,
        session_factory: Any,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._sf = session_factory
        self._clock: Callable[[], datetime] = clock or _now_utc

    async def for_profile(self, profile: SipProfile, *, audit: bool = True) -> ProfileDemand:
        now = self._clock()
        symbols: set[str] = set()
        bounds: dict[str, float] = {}
        consumers: set[str] = set()
        lease_ids: set[int] = set()
        async with self._sf() as s:
            rows = (
                (
                    await s.execute(
                        select(SipDemandLease).where(
                            SipDemandLease.profile == str(profile),
                            SipDemandLease.status == str(LeaseStatus.ACTIVE),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for r in rows:
                if _aware(r.expires_at) <= now:
                    continue
                syms = _loads_list(r.symbols)
                symbols.update(syms)
                consumers.add(r.consumer_id)
                lease_ids.add(r.id)
                if profile is SipProfile.LIVE and r.max_age_s is not None:
                    b = float(r.max_age_s)
                    for sym in syms:
                        # Strictest wins. There is no other path.
                        bounds[sym] = min(b, bounds.get(sym, b))
            strictest = min(bounds.values()) if bounds else None
            if audit:
                AuditLogger.write(
                    s,
                    actor_type=AuditActorType.SYSTEM,
                    actor_id=_ACTOR,
                    action=AuditAction.SIP_DEMAND_UNION_MATERIALIZED,
                    target_type="sip_profile",
                    target_id=str(profile),
                    payload={
                        "symbol_count": len(symbols),
                        "strictest_bound_s": strictest,
                        "lease_ids": sorted(lease_ids),
                        "consumer_ids": sorted(consumers),
                    },
                )
                await s.commit()
        return ProfileDemand(
            profile=profile,
            symbols=frozenset(symbols),
            per_symbol_bound_s=bounds,
            strictest_bound_s=strictest,
            lease_count=len(lease_ids),
            consumer_ids=frozenset(consumers),
            lease_ids=frozenset(lease_ids),
            materialized_at=now,
        )

    async def status(self, registry: ConsumerRegistry) -> DemandPlaneStatus:
        profiles: dict[str, ProfileDemandStatus] = {}
        for profile in (SipProfile.EOD, SipProfile.LIVE):
            d = await self.for_profile(profile, audit=False)
            cap = registry.config.plane_cap(profile)
            profiles[str(profile)] = ProfileDemandStatus(
                profile=profile,
                active_leases=d.lease_count,
                union_size=len(d.symbols),
                strictest_bound_s=d.strictest_bound_s,
                plane_cap=cap,
                cap_headroom=(cap - len(d.symbols)) if cap is not None else None,
            )
        async with self._sf() as s:
            regs = (
                (
                    await s.execute(
                        select(SipConsumerRegistration).where(
                            SipConsumerRegistration.revoked_at.is_(None)
                        )
                    )
                )
                .scalars()
                .all()
            )
        return DemandPlaneStatus(
            registry_verified=registry.registry_verified,
            artifact_sha256=registry.verified_sha256,
            registered_consumers=len(regs),
            rejected_count=registry.rejected_count,
            last_rejection=registry.last_rejection,
            profiles=profiles,
        )
