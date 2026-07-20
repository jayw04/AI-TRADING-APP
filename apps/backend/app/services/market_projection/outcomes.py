"""MKT-PROJ-001 §4 outcome grading + the train/serve drift ladder (FR-013; guardrails 4 & 8).

**Grading**: every SUCCESS run matures when close(t+1) exists — realized return,
realized label (same frozen threshold the projection carried), magnitude
correctness (elevated call vs realized-material), and the probability assigned
to the realized class. No served projection escapes grading.

**Drift (owner-amended rule, 2026-07-11 approval message)**: for each served
day, the live IEX feature vector is compared against a SIP re-computation of
the same features, standardized by the PRODUCTION pipeline's train-window stds.
Ladder:

- WARNING / investigate: any manifest feature ≥ 0.5σ standardized mean drift on
  a served day.
- AUTO-DOWNGRADE when any of: (a) the same feature ≥ 0.5σ on 3 CONSECUTIVE
  served days; (b) any feature ≥ 1.0σ on one served day; (c) > 20% of manifest
  features ≥ 0.5σ on the same served day.
- Restoration is OPERATOR-ONLY (runbook: edit/remove the state file after
  review) — automation never re-promotes the badge (ADR 0035 discipline).

State lives in ``data/market_projection/drift_state.json`` (read by the API to
pick the badge) and the per-day ledger in ``drift_ledger.jsonl``. Downgrade
emits a structlog ERROR — the 5-minute log watcher turns that into an SNS alert.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog

from app.services.market_projection import dataset as ds
from app.services.market_projection.features_preclose import preclose_features
from app.services.market_projection.labels import label_for
from app.services.market_projection.schemas import MARKET_PROXY, PRECLOSE_FEATURES

logger = structlog.get_logger(__name__)

DRIFT_DIR = "data/market_projection"
DRIFT_STATE = os.path.join(DRIFT_DIR, "drift_state.json")
DRIFT_LEDGER = os.path.join(DRIFT_DIR, "drift_ledger.jsonl")
WARN_SIGMA = 0.5
HARD_SIGMA = 1.0
CONSECUTIVE_DAYS = 3
BREADTH_SHARE = 0.20


def grade_run_fields(run: Any, spy_daily) -> dict[str, Any] | None:
    """Realized-outcome fields for one SUCCESS run, or None if not matured."""
    day = run.target_date
    later = spy_daily.index[spy_daily.index > day]
    if day not in spy_daily.index or len(later) == 0:
        return None
    close_t = float(spy_daily.loc[day, "close"])
    close_t1 = float(spy_daily.loc[later[0], "close"])
    realized = (close_t1 - close_t) / close_t * 100.0
    thr = run.material_threshold_pct
    if thr is None:
        return None
    label = label_for(realized, thr).value
    material = label in ("UP", "DOWN")
    probs = {"UP": run.prob_up or 0.0, "DOWN": run.prob_down or 0.0,
             "NEUTRAL": run.prob_neutral or 0.0}
    return {
        "outcome_status": "graded",
        "realized_return": realized,
        "realized_label": label,
        "correct_magnitude": bool(run.elevated) == material,
        "prob_assigned_to_realized_class": probs.get(label),
    }


# --- drift ladder -----------------------------------------------------------------

def compute_drift_row(
    live_features: dict[str, float | None],
    sip_features: dict[str, float | None],
    stds: dict[str, float],
) -> dict[str, float]:
    """Per-feature |live − sip| / train-σ for features observed on both sides."""
    out: dict[str, float] = {}
    for name in PRECLOSE_FEATURES:
        lv, sv, sd = live_features.get(name), sip_features.get(name), stds.get(name)
        if lv is None or sv is None or not sd:
            continue
        out[name] = abs(float(lv) - float(sv)) / float(sd)
    return out


def _read_jsonl(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]
    except OSError:
        return []


def apply_drift_ladder(day: date, drift: dict[str, float]) -> dict[str, Any]:
    """Append the day's ledger row, evaluate the amended ladder, persist state.

    Returns the (possibly updated) state dict. Once ``downgraded``, only an
    operator restores (this function never upgrades the state)."""
    os.makedirs(DRIFT_DIR, exist_ok=True)
    row = {"day": day.isoformat(), "drift": {k: round(v, 3) for k, v in drift.items()}}
    with open(DRIFT_LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")

    try:
        with open(DRIFT_STATE, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, json.JSONDecodeError):
        state = {"status": "ok"}
    if state.get("status") == "downgraded":
        return state  # operator-only restoration

    warn = {k for k, v in drift.items() if v >= WARN_SIGMA}
    hard = {k for k, v in drift.items() if v >= HARD_SIGMA}
    reasons: list[str] = []
    if hard:
        reasons.append(f"feature(s) ≥ {HARD_SIGMA}σ on one served day: {sorted(hard)}")
    if len(warn) / len(PRECLOSE_FEATURES) > BREADTH_SHARE:  # owner: share of MANIFEST features
        reasons.append(
            f">{int(BREADTH_SHARE * 100)}% of manifest features ≥ {WARN_SIGMA}σ: {sorted(warn)}"
        )
    ledger = _read_jsonl(DRIFT_LEDGER)[-CONSECUTIVE_DAYS:]
    if len(ledger) == CONSECUTIVE_DAYS:
        persistent = set.intersection(*[
            {k for k, v in entry["drift"].items() if v >= WARN_SIGMA} for entry in ledger
        ])
        if persistent:
            reasons.append(
                f"feature(s) ≥ {WARN_SIGMA}σ on {CONSECUTIVE_DAYS} consecutive served days: "
                f"{sorted(persistent)}"
            )

    if reasons:
        state = {"status": "downgraded", "reasons": reasons,
                 "since": datetime.now(UTC).isoformat(),
                 "restore": "operator-only — docs/runbook/market-projection.md"}
        logger.error("mktproj_drift_downgrade", reasons=reasons)  # log watcher → SNS
    elif warn:
        state = {"status": "warning", "features": sorted(warn),
                 "since": datetime.now(UTC).isoformat()}
        logger.warning("mktproj_drift_warning", features=sorted(warn))
    else:
        state = {"status": "ok", "since": datetime.now(UTC).isoformat()}

    tmp = DRIFT_STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1)
    os.replace(tmp, DRIFT_STATE)
    return state


def drift_state() -> dict[str, Any]:
    try:
        with open(DRIFT_STATE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {"status": "ok"}


def sip_features_for(client: Any, day: date, cutoff_et: datetime) -> dict[str, float | None]:
    """Re-compute the served day's feature vector from SIP data (the training
    provenance) — the comparison side of the 30-day diagnostic."""
    sessions = ds.nyse_sessions(day - timedelta(days=45), day)
    daily = ds.fetch_daily(client, [MARKET_PROXY], day - timedelta(days=420),
                           day - timedelta(days=1), feed="sip")
    minute = ds.fetch_minute_range(client, ds.ALL_SYMBOLS, sessions.index[0], day, feed="sip")
    spy_daily = daily.get(MARKET_PROXY)
    if spy_daily is None or MARKET_PROXY not in minute:
        return {}
    cum = ds.spy_cum_volume_table(minute[MARKET_PROXY], sessions)
    prior = [d for d in sessions.index if d < day][-ds.VOLUME_TOD_LOOKBACK:]
    vols = [cum.get((d, cutoff_et.time())) for d in prior]
    known = [v for v in vols if v]
    baseline = (sum(known) / len(known)) if len(known) == ds.VOLUME_TOD_LOOKBACK else None
    open_et, close_et = sessions.loc[day, "open_et"], sessions.loc[day, "close_et"]
    rth = {sym: ds.rth_slice(df, day, open_et, close_et) for sym, df in minute.items()}
    return preclose_features(rth, spy_daily, day=day, cutoff=cutoff_et,
                             spy_cum_vol_20d_tod_avg=baseline)
