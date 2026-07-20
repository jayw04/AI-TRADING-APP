"""MKT-PROJ-001 §4 live inference (FR-009; ModelCard v1.0 owner decision).

Serves ONE claim: primary-horizon (PRE_CLOSE_TOMORROW) elevated move-risk.
Owner guardrails enforced structurally:

- **G1 frozen artifact**: only the registry row with ``status='production'`` is
  served; the artifact loads hash-verified (a tampered file refuses). No
  fallback model exists — any failure is a ``run_status`` outcome, never a
  substitute projection (NFR-003).
- **G2 primary only**: this module cannot produce a PRE_OPEN projection; there
  is no code path for it.
- **G3 capped claim**: the stored ``display_phrase`` is one of the two
  owner-approved templates; drivers are ``material_drivers`` (raises/lowers
  move-risk — no directional vocabulary exists in the served payload).
- Full three-class probabilities are persisted in the runs table for research
  and outcome grading, but the API layer never emits them (owner Q1).

Live data path is IEX (recorded in ``source_json``; reconciled by the 30-day
train/serve drift diagnostic in ``outcomes.py``).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog

from app.services.market_projection import dataset as ds
from app.services.market_projection.attribution import material_drivers
from app.services.market_projection.features_preclose import preclose_features
from app.services.market_projection.labels import threshold_pct_for
from app.services.market_projection.schemas import (
    FEATURE_VERSION,
    FORECAST_OFFSET_MIN,
    LABEL_VERSION,
    MARKET_PROXY,
    PHRASE_ELEVATED,
    PHRASE_NOT_ELEVATED,
    PRECLOSE_FEATURES,
    ProjectionType,
)
from app.services.market_projection.validate import ELEVATED_CALL_MIN_P

logger = structlog.get_logger(__name__)

DAILY_CONTEXT_DAYS = 420          # calendar days of daily bars (≥260 sessions for MA200)
VOLUME_BASELINE_CAL_DAYS = 45     # calendar days of SPY minute bars for the 20-session baseline
CONF_HIGH = (0.60, 0.15)          # frozen §18 mapping (max class prob, gap)
CONF_MED = (0.50, 0.08)


def confidence_for(probs: dict[str, float]) -> str:
    ordered = sorted(probs.values(), reverse=True)
    top, gap = ordered[0], ordered[0] - (ordered[1] if len(ordered) > 1 else 0.0)
    if top >= CONF_HIGH[0] and gap >= CONF_HIGH[1]:
        return "HIGH"
    if top >= CONF_MED[0] and gap >= CONF_MED[1]:
        return "MEDIUM"
    return "LOW"


def build_live_features(
    client: Any, day: date, cutoff_et: datetime
) -> tuple[dict[str, float | None], dict[str, Any]]:
    """The frozen pre-close feature vector from LIVE (IEX) data as of the cutoff.

    Returns (features, source_meta). Fail-soft: raises ValueError with a reason
    the job converts into an UNAVAILABLE run — never a fabricated vector."""
    sessions = ds.nyse_sessions(day - timedelta(days=VOLUME_BASELINE_CAL_DAYS), day)
    if day not in sessions.index:
        raise ValueError("not_a_trading_session")

    daily = ds.fetch_daily(
        client, [MARKET_PROXY], day - timedelta(days=DAILY_CONTEXT_DAYS),
        day - timedelta(days=1), feed="iex",
    )
    spy_daily = daily.get(MARKET_PROXY)
    if spy_daily is None or len(spy_daily) < 220:
        raise ValueError("insufficient_daily_history")

    minute = ds.fetch_minute_range(
        client, ds.ALL_SYMBOLS, sessions.index[0], day, feed="iex"
    )
    if MARKET_PROXY not in minute or minute[MARKET_PROXY].empty:
        raise ValueError("missing_intraday_bars")

    cum = ds.spy_cum_volume_table(minute[MARKET_PROXY], sessions)
    prior = [d for d in sessions.index if d < day][-ds.VOLUME_TOD_LOOKBACK:]
    vols = [cum.get((d, cutoff_et.time())) for d in prior]
    known = [v for v in vols if v]
    baseline = (sum(known) / len(known)) if len(known) == ds.VOLUME_TOD_LOOKBACK else None

    open_et = sessions.loc[day, "open_et"]
    close_et = sessions.loc[day, "close_et"]
    rth = {sym: ds.rth_slice(df, day, open_et, close_et) for sym, df in minute.items()}
    features = preclose_features(
        rth, spy_daily, day=day, cutoff=cutoff_et, spy_cum_vol_20d_tod_avg=baseline,
    )
    if not features:
        raise ValueError("feature_build_empty")
    threshold = threshold_pct_for(spy_daily, day)
    source = {
        "feed": "iex",
        "as_of": cutoff_et.isoformat(),
        "spy_minute_rows_today": int(len(rth.get(MARKET_PROXY, []))),
        "volume_baseline_sessions": len(known),
        "threshold_pct": threshold,
    }
    return features, source


def run_projection(models: Any, features: dict[str, float | None], source: dict[str, Any],
                   *, day: date, cutoff_et: datetime, model_version: str) -> dict[str, Any]:
    """Features + the production model bundle → the runs-row field dict."""
    row = {"features_json": features, "date": day, "label": None, "realized_return": None}
    # manifest assertion (G1): the live vector must carry exactly the frozen keys
    if tuple(features.keys()) != PRECLOSE_FEATURES:
        raise ValueError("feature_manifest_mismatch")
    probs = models.predict_logistic([row])[0]
    p_material = probs["UP"] + probs["DOWN"]
    elevated = p_material >= ELEVATED_CALL_MIN_P
    x_std = models.pipeline.transform([row])[0]
    drivers = material_drivers(models.logistic, x_std, models.pipeline.columns)
    threshold = source.get("threshold_pct")
    return {
        "projection_type": ProjectionType.PRE_CLOSE_TOMORROW.value,
        "market_proxy": MARKET_PROXY,
        "as_of": cutoff_et.astimezone(UTC),
        "target_date": day,  # graded vs close(t+1) when it matures
        "model_version": model_version,
        "feature_version": FEATURE_VERSION,
        "label_version": LABEL_VERSION,
        "prob_up": probs["UP"], "prob_down": probs["DOWN"],
        "prob_neutral": probs["NEUTRAL"], "prob_material": p_material,
        "elevated": elevated,
        "display_phrase": PHRASE_ELEVATED if elevated else PHRASE_NOT_ELEVATED,
        "confidence": confidence_for(probs),
        "material_threshold_pct": threshold,
        "drivers_json": drivers,
        "source_json": source,
        "run_status": "SUCCESS",
        "unavailable_reason": None,
    }


def next_cutoff_for(day: date) -> datetime | None:
    """Today's close−15m from the authoritative calendar, or None when closed."""
    sessions = ds.nyse_sessions(day, day)
    if day not in sessions.index:
        return None
    return (sessions.loc[day, "close_et"] - timedelta(minutes=FORECAST_OFFSET_MIN)).to_pydatetime()
