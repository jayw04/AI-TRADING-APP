"""Operational-state resolver (P11 §1, ADR 0021).

Derives the four operational states — **Implemented → Enabled → Healthy → Verified**
(Direction v1.0 §2) — for each registered feature, from existing sources only:
- *Implemented*: it is in the registry (code on `main`).
- *Enabled*: a strategy currently **running on a book** has the feature's flag on (flag
  features), or the infra job is registered (monitor features).
- *Healthy (BASIC, §1)*: coarse — the enabling actor is actually running / its job is
  registered. Full KPI/freshness-based health is **§2**.
- *Verified*: the curated promotion-backtest verdict from the registry.

Read-only: no DB writes, no order path, no new schema. Derives from the
``StrategyEngine`` snapshot (`running_strategies()` + `scheduler_has_job()`); degrades
gracefully when the engine is absent (tests / alpaca-disabled) — everything reads as
not-enabled rather than raising.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ops.feature_registry import FEATURES, INFRA_JOB_IDS, OperationalFeature


@dataclass(frozen=True)
class FeatureState:
    key: str
    title: str
    governing_adr: str
    flag: str | None
    implemented: bool  # always True — in the registry
    enabled: bool
    healthy: str       # "ok" | "degraded" | "n_a"  (BASIC in §1; full KPIs are §2)
    verified: str
    note: str = ""


def _flag_on(value: Any) -> bool:
    """A feature flag is 'on' for True, or a set numeric (e.g. max_sector_pct,
    overlay_gross_smooth_span). None / "" / 0 / False all read as off."""
    if value is None or value is False or value == "":
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value > 0
    return bool(value)


def _resolve_one(feat: OperationalFeature, engine: Any) -> FeatureState:
    running = engine.running_strategies() if engine is not None else []

    if feat.enable_flag is None:
        # Infra actor: enabled iff its scheduler job is registered.
        job_id = INFRA_JOB_IDS.get(feat.key)
        enabled = bool(engine is not None and job_id and engine.scheduler_has_job(job_id))
        healthy = "ok" if enabled else "n_a"
    else:
        enabling = [r for r in running if _flag_on(r.instance.params.get(feat.enable_flag))]
        enabled = bool(enabling)
        # BASIC health (§1): the enabling strategy is actually being dispatched (has a
        # registered job). Precise per-tick health + last-run freshness is §2.
        if not enabled:
            healthy = "n_a"
        elif any(r.job_id for r in enabling):
            healthy = "ok"
        else:
            healthy = "degraded"

    return FeatureState(
        key=feat.key, title=feat.title, governing_adr=feat.governing_adr,
        flag=feat.enable_flag, implemented=True, enabled=enabled,
        healthy=healthy, verified=feat.verified, note=feat.note,
    )


def resolve_operational_state(engine: Any) -> list[FeatureState]:
    """Resolve the operational state of every registered feature (P11 §1).

    ``engine`` is the live ``StrategyEngine`` (or ``None`` when unavailable — then flag
    features read as not-enabled and infra as n_a). Pure derivation; no side effects."""
    return [_resolve_one(f, engine) for f in FEATURES]
