"""SPQ-1 synthetic signal/data producer — orchestration (all closed Phase-0 rules).

Given synthetic, calendar-aligned market + security fixtures, produces a ``SignalDecisionRecord``
for one security at decision session ``t``, staging every governed refusal. SYNTHETIC-ONLY: no
vendor adapter, no real dataset, no performance metric. Independent of the Stage-3-frozen
``app.research.mr002.signal`` module.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .calendar import RegisteredCalendar
from .constants import (
    OLS_WINDOW,
    R5_HORIZON,
    WARMUP_PRICE_OBSERVATIONS,
    Z_NORM_OBS,
)
from .eligibility import ExclusionCheck, evaluate_eligibility
from .identities import InputIdentityRegistry, canonical_sha256
from .liquidity import trailing_adv_dollars
from .models import SignalDecisionRecord, build_signal_decision_record
from .normalization import normalize_signal, r5_value
from .refusals import refuse
from .residuals import stock_residual_and_beta
from .returns import CellStatus, classify_stock_window
from .sector_factor import sector_factor_at
from .sector_pit import SectorRecord, resolve_sector
from .security_identity import PitIdentityRegistry, build_candidate_id

__all__ = ["MarketData", "SecurityData", "ProductionRequest", "produce_decision"]


@dataclass(frozen=True)
class MarketData:
    calendar: RegisteredCalendar
    spy_ret: np.ndarray                       # calendar-aligned SPY total returns
    sector_ret: dict[str, np.ndarray]         # sector_id -> calendar-aligned sector-ETF returns
    observed_identities: dict[str, str]       # input identities to verify against the registry


@dataclass(frozen=True)
class SecurityData:
    symbol: str
    stock_ret: np.ndarray                     # calendar-aligned total returns
    stock_status: list[CellStatus]            # per-session status (PRESENT/YOUNG/HOLE/HALT)
    raw_close: np.ndarray                      # raw (unadjusted) close for ADV
    raw_volume: np.ndarray                     # raw share volume for ADV
    sector_records: list[SectorRecord]
    eligibility_checks: list[ExclusionCheck]


@dataclass(frozen=True)
class ProductionRequest:
    program_id: str
    configuration_id: str
    side: str
    t: int                                     # decision-session ordinal
    decision_cutoff: str                       # close-t timestamp (ISO 8601)


def produce_decision(
    market: MarketData,
    security: SecurityData,
    registry: InputIdentityRegistry,
    lineage: PitIdentityRegistry,
    req: ProductionRequest,
) -> SignalDecisionRecord:
    """Produce the close-t SignalDecisionRecord for one security (raises a governed refusal)."""
    t = req.t

    # 1. Frozen-input identity verification (fail closed before any computation).
    registry.verify("registered_exchange_calendar", market.calendar.identity)
    for key, observed in market.observed_identities.items():
        registry.verify(key, observed)

    # 2. Warm-up boundary (SIG-32 / OWNER-A): first scoreable t needs 126 price obs [t-125, t].
    if t < WARMUP_PRICE_OBSERVATIONS - 1:
        raise refuse(
            "INELIGIBLE:OLS_WINDOW_INSUFFICIENT",
            f"decision session {t} earlier than the first scoreable session "
            f"{WARMUP_PRICE_OBSERVATIONS - 1} (125 return / 126 price)",
        )

    # 3. Permanent security identity (lineage) + PIT sector.
    permanent_security_id = lineage.resolve_permanent_id(security.symbol, t)
    sector = resolve_sector(security.sector_records, req.decision_cutoff)
    if sector.sector_id not in market.sector_ret:
        raise refuse(
            "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
            f"no registered sector-ETF series for sector {sector.sector_id}",
        )
    sector_ret = market.sector_ret[sector.sector_id]

    # 4. Stock-return window statuses over [t-124, t] (125 returns): young/hole/halt dispositions.
    earliest_return = t - (WARMUP_PRICE_OBSERVATIONS - 2)   # t-124
    classify_stock_window(security.stock_status[earliest_return : t + 1])

    # 5. u_sector over [t-124, t] (PIT-recursive; factor identity refusals inside).
    u_sector = np.full(len(security.stock_ret), np.nan, dtype=np.float64)
    for s in range(earliest_return, t + 1):
        u_sector[s] = sector_factor_at(market.spy_ret, sector_ret, s)

    # 6. eps over [t-64, t] (earliest R5 residual is eps_{t-64}); capture beta at t.
    eps: dict[int, float] = {}
    beta_m_t = float("nan")
    earliest_resid = t - (Z_NORM_OBS + R5_HORIZON - 1)      # t-64
    for s in range(earliest_resid, t + 1):
        e, b = stock_residual_and_beta(security.stock_ret, market.spy_ret, u_sector, s)
        eps[s] = e
        if s == t:
            beta_m_t = b

    # 7. R5 over [t-60, t]; normalization window = R5_{t-60}..R5_{t-1}, current R5_t excluded.
    def r5_at(sess: int) -> float | None:
        return r5_value([eps[k] for k in range(sess - R5_HORIZON + 1, sess + 1)])

    r5_hist = [r5_at(sess) for sess in range(t - Z_NORM_OBS, t)]
    r5_t = r5_at(t)
    normalized = normalize_signal(r5_hist, r5_t, list(range(t - Z_NORM_OBS, t)))

    # 8. ADV (20-session median of raw close x raw volume, ending t-1).
    adv = trailing_adv_dollars(security.raw_close, security.raw_volume, t)

    # 9. Close-t eligibility (fixed precedence; no z/percentile/gap).
    elig = evaluate_eligibility(security.eligibility_checks, req.decision_cutoff)
    eligibility_evidence_identity = canonical_sha256(
        [
            {
                "rule_id": e.rule_id,
                "outcome": e.outcome,
                "observed_value": e.observed_value,
                "threshold": e.threshold,
                "source_identity": e.source_identity,
                "availability_timestamp": e.availability_timestamp,
                "decision_cutoff": e.decision_cutoff,
                "precedence_rank": e.precedence_rank,
            }
            for e in elig.evidence
        ]
    )

    # 10. candidate_id binds program|config|session|permanent-security|side|signal-record.
    candidate_id = build_candidate_id(
        req.program_id,
        req.configuration_id,
        t,
        permanent_security_id,
        req.side,
        normalized.computation_record_identity,
    )

    return build_signal_decision_record(
        {
            "candidate_id": candidate_id,
            "permanent_security_id": permanent_security_id,
            "symbol": security.symbol,
            "decision_session": t,
            "signal_origin_session": t,
            "side": req.side,
            "registered_signal_value": normalized.z,
            "registered_sigma_resid": normalized.sigma,
            "sector_id": sector.sector_id,
            "beta": beta_m_t,
            "decision_eligibility_status": elig.status,
            "eligibility_evidence_identity": eligibility_evidence_identity,
            "eligibility_precedence_rank": elig.precedence_rank,
            "configuration_id": req.configuration_id,
            "trailing_adv_dollars": adv,
            "normalization_window_identity": normalized.normalization_window_identity,
            "computation_record_identity": normalized.computation_record_identity,
            "warmup_return_sessions": WARMUP_PRICE_OBSERVATIONS - 1,
            "warmup_price_observations": WARMUP_PRICE_OBSERVATIONS,
        }
    )


_ = OLS_WINDOW  # referenced for parity with the frozen window constant set
