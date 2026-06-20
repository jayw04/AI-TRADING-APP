"""Operational-state resolver (P11 §1 + §2, ADR 0021).

Derives the four operational states — **Implemented → Enabled → Healthy → Verified**
(Direction v1.0 §2) — for each registered feature, from existing sources only.

- *Implemented*: it is in the registry (code on `main`).
- *Enabled*: a strategy currently running on a book has the feature's flag on (flag
  features), or the infra job is registered (monitor features).
- *Healthy* (§2, measured): ``ok`` / ``degraded`` / ``stale`` / ``unknown`` / ``n_a`` —
  derived from the scheduler last-success/last-error metric gauges per the feature's
  backing job(s). ``unknown`` (no data yet / within the startup grace window) is distinct
  from ``degraded``, so a fresh process / metrics reset does not false-alarm.
- *Verified*: the curated promotion-backtest verdict from the registry.

Read-only: no DB writes, no order path, no new schema. Reads the in-process Prometheus
registry (no new dependency). Degrades gracefully when the engine/metrics are absent
(tests / alpaca-disabled) — features read as not-enabled / ``unknown`` rather than raising.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from prometheus_client import REGISTRY

from app.ops.feature_registry import FEATURES, INFRA_JOB_IDS, OperationalFeature

# Health-calc version (P11 §2 review) — bump when thresholds change so a status is
# traceable to the algorithm that produced it. Exposed in the /ops/state envelope.
HEALTH_ALGORITHM_VERSION = "1.0"

# Startup grace: within this window from process start, health is `unknown` (not
# `degraded`) — avoids false alarms on a fresh process / after a metrics reset.
OPS_HEALTH_GRACE_S = 60.0
_PROC_START = time.monotonic()

# Features that act on the daily-overlay tick (backed by the strategy's overlay job);
# the rest of the flag features act on the weekly on_bar tick (backed by the bar job).
_OVERLAY_TICK_FEATURES = frozenset(
    {"daily_overlay", "breadth_overlay", "vix_overlay", "exposure_smoothing"}
)
# Staleness windows (~2x the nominal cadence) by backing kind.
_STALE_OVERLAY_S = 2 * 86_400.0    # daily overlay
_STALE_BAR_S = 2 * 604_800.0       # weekly rebalance
_STALE_INFRA_S = 120.0             # 60s breaker monitor

_SUCCESS_METRIC = "workbench_scheduler_job_last_success_timestamp"
_ERROR_METRIC = "workbench_scheduler_job_last_error_timestamp"


@dataclass(frozen=True)
class FeatureState:
    key: str
    title: str
    governing_adr: str
    category: str
    flag: str | None
    implemented: bool   # always True — in the registry
    enabled: bool
    healthy: str        # ok | degraded | stale | unknown | n_a
    verified: str
    last_success_age_s: float | None  # seconds since the backing job last succeeded
    note: str = ""


def _flag_on(value: Any) -> bool:
    """A feature flag is 'on' for True, or a set numeric (e.g. max_sector_pct,
    overlay_gross_smooth_span). None / "" / 0 / False all read as off."""
    if value is None or value is False or value == "":
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value > 0
    return bool(value)


def _job_ts(job_id: str, metric: str) -> float | None:
    return REGISTRY.get_sample_value(metric, {"job_id": job_id})


def _backing_job_ids(feat: OperationalFeature, enabling: list[Any]) -> list[str]:
    if feat.enable_flag is None:
        jid = INFRA_JOB_IDS.get(feat.key)
        return [jid] if jid else []
    if feat.key in _OVERLAY_TICK_FEATURES:
        return [r.overlay_job_id for r in enabling if r.overlay_job_id]
    return [r.job_id for r in enabling if r.job_id]


def _stale_after(feat: OperationalFeature) -> float:
    if feat.enable_flag is None:
        return _STALE_INFRA_S
    if feat.key in _OVERLAY_TICK_FEATURES:
        return _STALE_OVERLAY_S
    return _STALE_BAR_S


def _health(enabled: bool, job_ids: list[str], stale_after: float) -> tuple[str, float | None]:
    """Measured health (§2) → (state, last_success_age_s). See module docstring."""
    if not enabled:
        return "n_a", None
    if (time.monotonic() - _PROC_START) < OPS_HEALTH_GRACE_S:
        return "unknown", None  # startup grace — not yet evaluable
    succ = [t for t in (_job_ts(j, _SUCCESS_METRIC) for j in job_ids) if t is not None]
    errs = [t for t in (_job_ts(j, _ERROR_METRIC) for j in job_ids) if t is not None]
    last_success = max(succ) if succ else None
    last_error = max(errs) if errs else None
    if last_success is None and last_error is None:
        return "unknown", None  # no data yet (not degraded)
    age = (time.time() - last_success) if last_success is not None else None
    if last_error is not None and (last_success is None or last_error >= last_success):
        return "degraded", age  # the most recent run errored/was missed
    if last_success is not None and (time.time() - last_success) > stale_after:
        return "stale", age
    return "ok", age


def _resolve_one(feat: OperationalFeature, engine: Any) -> FeatureState:
    running = engine.running_strategies() if engine is not None else []

    if feat.enable_flag is None:
        jid = INFRA_JOB_IDS.get(feat.key)
        enabled = bool(engine is not None and jid and engine.scheduler_has_job(jid))
        enabling: list[Any] = []
    else:
        enabling = [r for r in running if _flag_on(r.instance.params.get(feat.enable_flag))]
        enabled = bool(enabling)

    healthy, age = _health(enabled, _backing_job_ids(feat, enabling), _stale_after(feat))
    return FeatureState(
        key=feat.key, title=feat.title, governing_adr=feat.governing_adr,
        category=feat.category, flag=feat.enable_flag, implemented=True,
        enabled=enabled, healthy=healthy, verified=feat.verified,
        last_success_age_s=age, note=feat.note,
    )


def resolve_operational_state(engine: Any) -> list[FeatureState]:
    """Resolve the operational state of every registered feature (P11 §1/§2).

    ``engine`` is the live ``StrategyEngine`` (or ``None`` when unavailable). Pure
    derivation from the engine snapshot + the Prometheus registry; no side effects."""
    return [_resolve_one(f, engine) for f in FEATURES]
