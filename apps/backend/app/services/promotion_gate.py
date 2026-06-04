"""4-criterion promotion gate evaluator (P6b §3a-gate, ADR 0007).

A pure evaluator over an existing ``VariantComparison`` (the §2b primitive),
plus the morning-brief pass that runs it. Produces an ``EvidenceBundle`` with
per-criterion verdicts + a composite all-passed, stored at the proposal's
``evaluation_results_json.evidence_bundle`` sub-key (Q7).

The four criteria (ADR 0007 §"The promotion criteria"):
- **Duration** — ≥30 calendar days **AND** ≥50 trades ("whichever is later";
  either floor alone is misleading). Both required.
- **Sharpe margin** — variant Sharpe ≥ live Sharpe × 1.05 (≥5% relative).
- **Absolute floor** — variant absolute return over the window > 0 (strict;
  NOT user-configurable per ADR).
- **No worst-case divergence** — the variant's worst drawdown in any rolling
  7-business-day sub-window has not exceeded the LIVE side's max drawdown by
  more than 20% (i.e. ≤ |live_max_dd| × 1.20).

§3a evaluates + transitions EVALUATING → EVIDENCE_READY (sticky). It does NOT
promote and does NOT write STRATEGY_PROMOTED — that's §3b.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.services.paper_variant import VariantComparison, compare_variant_to_parent

logger = structlog.get_logger(__name__)

# Threshold defaults (tunable via agent_envelope_json.promotion_thresholds —
# EXCEPT the absolute-return floor, which ADR 0007 fixes at "positive").
DEFAULT_MIN_DAYS = 30
DEFAULT_MIN_TRADES = 50
DEFAULT_SHARPE_MARGIN_REL_PCT = 5      # variant ≥ live × 1.05
DEFAULT_DD_DIVERGENCE_MAX_PCT = 20     # variant worst-7d ≤ live_max_dd × 1.20
DEFAULT_DD_WINDOW_DAYS = 7             # rolling sub-window for the variant drawdown


@dataclass(frozen=True)
class GateCriterionResult:
    name: str
    passed: bool
    details: dict[str, Any]


@dataclass(frozen=True)
class GateResults:
    duration: GateCriterionResult
    sharpe_margin: GateCriterionResult
    absolute_return: GateCriterionResult
    drawdown_divergence: GateCriterionResult

    @property
    def all_passed(self) -> bool:
        return (
            self.duration.passed
            and self.sharpe_margin.passed
            and self.absolute_return.passed
            and self.drawdown_divergence.passed
        )


@dataclass(frozen=True)
class EvidenceBundle:
    captured_at: datetime
    comparison: VariantComparison
    gate_results: GateResults

    @property
    def all_criteria_passed(self) -> bool:
        return self.gate_results.all_passed


def _read_thresholds(envelope: dict[str, Any] | None) -> dict[str, Any]:
    e = (envelope or {}).get("promotion_thresholds") or {}
    return {
        "min_days": e.get("min_days", DEFAULT_MIN_DAYS),
        "min_trades": e.get("min_trades", DEFAULT_MIN_TRADES),
        "sharpe_margin_relative_pct": e.get(
            "sharpe_margin_relative_pct", DEFAULT_SHARPE_MARGIN_REL_PCT
        ),
        "drawdown_divergence_max_pct": e.get(
            "drawdown_divergence_max_pct", DEFAULT_DD_DIVERGENCE_MAX_PCT
        ),
        "drawdown_window_days": e.get("drawdown_window_days", DEFAULT_DD_WINDOW_DAYS),
    }


def _check_duration(
    comparison: VariantComparison, thresholds: dict[str, Any]
) -> GateCriterionResult:
    """≥min_days AND ≥min_trades (ADR 0007: 'whichever is later' — both)."""
    days_elapsed = (comparison.window_end - comparison.window_start).days
    trades = comparison.variant_trade_count
    days_passed = days_elapsed >= thresholds["min_days"]
    trades_passed = trades >= thresholds["min_trades"]
    return GateCriterionResult(
        name="duration",
        passed=days_passed and trades_passed,
        details={
            "actual_days": days_elapsed,
            "actual_trades": trades,
            "min_days": thresholds["min_days"],
            "min_trades": thresholds["min_trades"],
            "days_passed": days_passed,
            "trades_passed": trades_passed,
        },
    )


def _check_sharpe_margin(
    comparison: VariantComparison, thresholds: dict[str, Any]
) -> GateCriterionResult:
    """variant.sharpe ≥ live.sharpe × (1 + margin_pct/100). Metrics are non-null
    floats (§2b returns 0.0, never None). Negative live Sharpe makes ×1.05
    lenient — acceptable per ADR's literal relative formula."""
    live_sharpe = comparison.live_metrics.sharpe_ratio
    variant_sharpe = comparison.variant_metrics.sharpe_ratio
    margin_pct = thresholds["sharpe_margin_relative_pct"]

    required = live_sharpe * (1 + margin_pct / 100)
    return GateCriterionResult(
        name="sharpe_margin",
        passed=variant_sharpe >= required,
        details={
            "live_sharpe": live_sharpe,
            "variant_sharpe": variant_sharpe,
            "required_variant_sharpe": required,
            "required_margin_pct": margin_pct,
        },
    )


def _check_absolute_return(comparison: VariantComparison) -> GateCriterionResult:
    """Strict variant absolute return > 0 over the window: final equity above the
    shared capital_base. NOT user-configurable (ADR 0007)."""
    curve = comparison.variant_equity_curve
    if not curve:
        return GateCriterionResult(
            name="absolute_return",
            passed=False,
            details={"skip_reason": "no_equity_curve"},
        )
    final_equity = Decimal(str(curve[-1][1]))
    capital_base = Decimal(str(comparison.capital_base))
    total_return = final_equity - capital_base
    return GateCriterionResult(
        name="absolute_return",
        passed=total_return > Decimal("0"),
        details={
            "variant_total_return": float(total_return),
            "capital_base": float(capital_base),
            "final_equity": float(final_equity),
        },
    )


def _worst_rolling_drawdown(
    curve: list[tuple[datetime, Decimal]], window_days: int
) -> float:
    """Worst drawdown (positive fraction) over any rolling ``window_days``-day
    sub-window. Within each window, drawdown is a running-peak walk:
    max over points of (peak - v) / peak. Returns 0.0 if no drawdown."""
    worst = 0.0
    n = len(curve)
    for i in range(n):
        window_end_ts = curve[i][0] + timedelta(days=window_days)
        peak = float(curve[i][1])
        for j in range(i, n):
            ts, eq = curve[j]
            if ts > window_end_ts:
                break
            v = float(eq)
            if v > peak:
                peak = v
            if peak > 0:
                dd = (peak - v) / peak
                if dd > worst:
                    worst = dd
    return worst


def _check_drawdown_divergence(
    comparison: VariantComparison, thresholds: dict[str, Any]
) -> GateCriterionResult:
    """Variant's worst rolling-N-day drawdown ≤ |live_max_dd| × (1 + max_pct/100).

    ADR 0007: the variant must not exceed the LIVE side's maximum drawdown by
    more than 20% in any rolling 7-day sub-window. Trivially passes when the
    live side never drew down (no reference) or the variant has <2 points.
    """
    live_dd = comparison.live_metrics.max_drawdown  # negative fraction or 0.0
    max_pct = thresholds["drawdown_divergence_max_pct"]
    window_days = thresholds["drawdown_window_days"]
    abs_live_dd = abs(float(live_dd))

    if abs_live_dd == 0:
        return GateCriterionResult(
            name="drawdown_divergence",
            passed=True,
            details={
                "live_max_drawdown": float(live_dd),
                "skip_reason": "live_drawdown_zero_no_reference",
            },
        )

    curve = comparison.variant_equity_curve
    if len(curve) < 2:
        return GateCriterionResult(
            name="drawdown_divergence",
            passed=True,
            details={"skip_reason": "insufficient_variant_equity_data"},
        )

    worst = _worst_rolling_drawdown(curve, window_days)
    allowed = abs_live_dd * (1 + max_pct / 100)
    ratio_pct = (worst / abs_live_dd) * 100
    return GateCriterionResult(
        name="drawdown_divergence",
        passed=worst <= allowed,
        details={
            "live_max_drawdown": float(live_dd),
            "variant_worst_window_drawdown": worst,
            "allowed_max_drawdown": allowed,
            "ratio_pct": ratio_pct,
            "max_excess_pct": max_pct,
            "window_days": window_days,
        },
    )


def evaluate_gate(
    comparison: VariantComparison, envelope: dict[str, Any] | None = None
) -> EvidenceBundle:
    """Pure: compute the 4-criterion gate + evidence bundle from a comparison."""
    thresholds = _read_thresholds(envelope)
    return EvidenceBundle(
        captured_at=datetime.now(UTC),
        comparison=comparison,
        gate_results=GateResults(
            duration=_check_duration(comparison, thresholds),
            sharpe_margin=_check_sharpe_margin(comparison, thresholds),
            absolute_return=_check_absolute_return(comparison),
            drawdown_divergence=_check_drawdown_divergence(comparison, thresholds),
        ),
    )


async def evaluate_promotion_gate(
    session: AsyncSession,
    variant_strategy_id: int,
    envelope: dict[str, Any] | None = None,
    bar_cache: Any = None,
) -> EvidenceBundle | None:
    """Compute the gate for a variant by id. None if no comparison data (no
    parent / no in-flight variant — same conditions as compare_variant_to_parent)."""
    comparison = await compare_variant_to_parent(
        session, variant_strategy_id, bar_cache=bar_cache
    )
    if comparison is None:
        return None
    return evaluate_gate(comparison, envelope)


# ----- serialization -----


def _metrics_dict(m: Any) -> dict[str, Any]:
    return {
        "trade_count": m.trade_count,
        "win_rate": m.win_rate,
        "avg_return_per_trade": m.avg_return_per_trade,
        "sharpe_ratio": m.sharpe_ratio,
        "max_drawdown": m.max_drawdown,
    }


def _criterion_dict(c: GateCriterionResult) -> dict[str, Any]:
    return {"name": c.name, "passed": c.passed, "details": c.details}


def bundle_to_json(bundle: EvidenceBundle) -> dict[str, Any]:
    """Serialize an EvidenceBundle for ``evaluation_results_json.evidence_bundle``
    storage. Consumed by §3b's UI + MCP additions."""
    comp = bundle.comparison
    return {
        "captured_at": bundle.captured_at.isoformat(),
        "all_criteria_passed": bundle.all_criteria_passed,
        "comparison": {
            "window_start": comp.window_start.isoformat(),
            "window_end": comp.window_end.isoformat(),
            "capital_base": float(comp.capital_base),
            "live_metrics": _metrics_dict(comp.live_metrics),
            "variant_metrics": _metrics_dict(comp.variant_metrics),
            "deltas": comp.deltas,
            "live_trade_count": comp.live_trade_count,
            "variant_trade_count": comp.variant_trade_count,
            "live_equity_curve": [
                {"ts": ts.isoformat(), "equity": float(eq)}
                for ts, eq in comp.live_equity_curve
            ],
            "variant_equity_curve": [
                {"ts": ts.isoformat(), "equity": float(eq)}
                for ts, eq in comp.variant_equity_curve
            ],
        },
        "gate_results": {
            "duration": _criterion_dict(bundle.gate_results.duration),
            "sharpe_margin": _criterion_dict(bundle.gate_results.sharpe_margin),
            "absolute_return": _criterion_dict(bundle.gate_results.absolute_return),
            "drawdown_divergence": _criterion_dict(
                bundle.gate_results.drawdown_divergence
            ),
        },
    }


# ----- morning-brief pass -----


async def run_promotion_gate_for_user(
    session: AsyncSession, user_id: int, bar_cache: Any = None
) -> dict[str, int]:
    """Per-user gate-evaluation pass (morning-brief cadence).

    Selects the user's EVALUATING + EVIDENCE_READY proposals (the latter so the
    sticky bundle keeps refreshing). For each: evaluate the gate and MERGE-WRITE
    the evidence bundle into ``evaluation_results_json`` (preserving the §2a
    paper_variant / §2b-bt status / §2b-rv human_review sub-keys). An EVALUATING
    proposal whose gate passes transitions EVALUATING → EVIDENCE_READY with one
    STRATEGY_PROPOSAL_TRANSITIONED audit row (one row per transaction). Already-
    EVIDENCE_READY proposals only refresh the bundle (no transition, no audit).

    Per-proposal failures are isolated (a terminated-mid-eval variant, etc.)."""
    proposals = list(
        (
            await session.execute(
                select(StrategyProposal)
                .where(StrategyProposal.user_id == user_id)
                .where(
                    StrategyProposal.state.in_(
                        [ProposalState.EVALUATING, ProposalState.EVIDENCE_READY]
                    )
                )
            )
        ).scalars().all()
    )

    transitions_fired = bundles_updated = skips = 0

    for proposal in proposals:
        try:
            paper_variant = (proposal.evaluation_results_json or {}).get(
                "paper_variant"
            ) or {}
            variant_strategy_id = paper_variant.get("variant_strategy_id")
            if variant_strategy_id is None:
                skips += 1
                continue

            envelope = await _user_envelope(session, user_id)
            bundle = await evaluate_promotion_gate(
                session, variant_strategy_id, envelope=envelope, bar_cache=bar_cache
            )
            if bundle is None:
                skips += 1
                continue

            # MERGE-WRITE (reassign — preserve every sibling sub-key).
            existing = dict(proposal.evaluation_results_json or {})
            existing["evidence_bundle"] = bundle_to_json(bundle)
            proposal.evaluation_results_json = existing
            now = datetime.now(UTC)
            proposal.updated_at = now
            bundles_updated += 1

            if (
                proposal.state == ProposalState.EVALUATING
                and bundle.all_criteria_passed
            ):
                proposal.state = ProposalState.EVIDENCE_READY
                proposal.transitioned_at = now
                AuditLogger.write(
                    session,
                    actor_type=AuditActorType.AGENT,
                    actor_id="promotion_gate",
                    action=AuditAction.STRATEGY_PROPOSAL_TRANSITIONED,
                    target_type="strategy_proposal",
                    target_id=proposal.id,
                    payload={
                        "proposal_id": proposal.id,
                        "from": "EVALUATING",
                        "to": "EVIDENCE_READY",
                        "trigger": "gate_passed",
                        "captured_at": bundle.captured_at.isoformat(),
                    },
                    user_id=user_id,
                )
                await session.commit()  # one row per transaction
                transitions_fired += 1
            else:
                # Bundle-only update: its own commit, no audit row.
                await session.commit()

        except Exception:
            logger.exception(
                "promotion_gate_eval_failed", user_id=user_id, proposal_id=proposal.id
            )
            await session.rollback()

    logger.info(
        "promotion_gate_user_pass",
        user_id=user_id,
        transitions_fired=transitions_fired,
        bundles_updated=bundles_updated,
        skips=skips,
    )
    return {
        "transitions_fired": transitions_fired,
        "bundles_updated": bundles_updated,
        "skips": skips,
    }


async def _user_envelope(session: AsyncSession, user_id: int) -> dict[str, Any]:
    from app.services.trading_profile import TradingProfileService

    profile = await TradingProfileService(session).get(user_id)
    return profile.agent_envelope or {}
