"""MKT-PROJ-001 §4 scheduled jobs (ModelCard v1.0 owner decision; plan v0.1).

Three entry points, all env-gated in lifespan (`WORKBENCH_MARKET_PROJECTION_ENABLED`),
all fail-soft, none anywhere near the order path (NFR-001, CI-enforced):

- ``run_market_projection_preclose`` — 15:45 + 12:45 ET crons; each fire asks the
  authoritative calendar whether it IS close−15m today (half-day tick-and-check)
  and no-ops otherwise. Serves ONLY the primary horizon (guardrail 2). Every
  attempt writes a runs row (SUCCESS / UNAVAILABLE / FAILED / SKIPPED).
- ``run_market_projection_outcomes`` — 18:30 ET; grades matured SUCCESS runs
  (guardrail 4) and, for the first 30 served days, runs the train/serve drift
  ladder (guardrail 8, owner-amended thresholds).
- ``run_market_projection_regime_report`` — monthly (1st, 17:05 ET); served-
  projection Brier by regime slice → evidence file + log line (guardrail 6).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select

from app.db.models.market_projection_model import MarketProjectionModelRegistry
from app.db.models.market_projection_run import MarketProjectionRun
from app.db.session import get_sessionmaker
from app.services.market_projection import dataset as ds
from app.services.market_projection.infer import (
    build_live_features,
    next_cutoff_for,
    run_projection,
)
from app.services.market_projection.model_registry import load_artifact
from app.services.market_projection.outcomes import (
    apply_drift_ladder,
    compute_drift_row,
    grade_run_fields,
    sip_features_for,
)
from app.services.market_projection.schemas import MARKET_PROXY, ProjectionType
from app.utils.time import EASTERN

logger = structlog.get_logger(__name__)

FIRE_TOLERANCE_MIN = 5
DRIFT_WINDOW_SERVED_DAYS = 30


async def _production_model() -> tuple[Any, str] | None:
    sf = get_sessionmaker()
    async with sf() as s:
        row = (await s.execute(
            select(MarketProjectionModelRegistry).where(
                MarketProjectionModelRegistry.status == "production",
                MarketProjectionModelRegistry.projection_type
                == ProjectionType.PRE_CLOSE_TOMORROW.value,
            ).order_by(MarketProjectionModelRegistry.created_at.desc())
        )).scalars().first()
    if row is None:
        return None
    return load_artifact(row.artifact_path, row.artifact_hash), row.model_version


async def _write_run(fields: dict[str, Any]) -> None:
    sf = get_sessionmaker()
    async with sf() as s:
        prior = (await s.execute(
            select(func.max(MarketProjectionRun.attempt_number)).where(
                MarketProjectionRun.projection_type == fields["projection_type"],
                MarketProjectionRun.market_proxy == fields["market_proxy"],
                MarketProjectionRun.target_date == fields["target_date"],
            )
        )).scalar()
        s.add(MarketProjectionRun(**fields, attempt_number=(prior or 0) + 1))
        await s.commit()


async def run_market_projection_preclose(*, now: datetime | None = None) -> dict | None:
    now_utc = now or datetime.now(UTC)
    now_et = now_utc.astimezone(EASTERN)
    day = now_et.date()
    if now_et.weekday() >= 5:
        return None
    cutoff = next_cutoff_for(day)
    if cutoff is None or abs((now_et - cutoff).total_seconds()) > FIRE_TOLERANCE_MIN * 60:
        return None  # holiday, or this cron tick isn't today's close−15m (half-day check)

    base = {
        "projection_type": ProjectionType.PRE_CLOSE_TOMORROW.value,
        "market_proxy": MARKET_PROXY, "as_of": now_utc, "target_date": day,
        "run_status": "FAILED", "outcome_status": "pending",
    }
    try:
        resolved = await _production_model()
        if resolved is None:
            await _write_run({**base, "run_status": "UNAVAILABLE",
                              "unavailable_reason": "no_production_model"})
            logger.warning("mktproj_preclose_unavailable", reason="no_production_model")
            return None
        models, model_version = resolved
        client = ds._client()
        try:
            features, source = build_live_features(client, day, cutoff)
        except ValueError as exc:
            await _write_run({**base, "run_status": "UNAVAILABLE",
                              "unavailable_reason": str(exc)})
            logger.warning("mktproj_preclose_unavailable", reason=str(exc))
            return None
        fields = run_projection(models, features, source, day=day, cutoff_et=cutoff,
                                model_version=model_version)
        fields["outcome_status"] = "pending"
        await _write_run(fields)
        logger.info("mktproj_preclose_served", p_material=round(fields["prob_material"], 3),
                    elevated=fields["elevated"], confidence=fields["confidence"])
        return fields
    except Exception:  # noqa: BLE001 - never raises into the scheduler
        logger.exception("mktproj_preclose_failed")
        try:
            await _write_run({**base, "unavailable_reason": "exception"})
        except Exception:  # noqa: BLE001
            logger.exception("mktproj_preclose_run_row_write_failed")
        return None


async def run_market_projection_outcomes(*, now: datetime | None = None) -> int:
    """Grade matured SUCCESS runs; run the drift ladder inside the 30-served-day window."""
    now_et = (now or datetime.now(UTC)).astimezone(EASTERN)
    sf = get_sessionmaker()
    graded = 0
    try:
        async with sf() as s:
            pending = (await s.execute(
                select(MarketProjectionRun).where(
                    MarketProjectionRun.run_status == "SUCCESS",
                    MarketProjectionRun.outcome_status == "pending",
                    MarketProjectionRun.target_date < now_et.date(),
                )
            )).scalars().all()
            if not pending:
                return 0
            client = ds._client()
            start = min(r.target_date for r in pending) - timedelta(days=10)
            spy_daily = ds.fetch_daily(client, [MARKET_PROXY], start, now_et.date(),
                                       feed="sip").get(MARKET_PROXY)
            served_days = (await s.execute(
                select(func.count(func.distinct(MarketProjectionRun.target_date))).where(
                    MarketProjectionRun.run_status == "SUCCESS",
                )
            )).scalar() or 0
            for run in pending:
                fields = grade_run_fields(run, spy_daily) if spy_daily is not None else None
                if fields is None:
                    continue
                for k, v in fields.items():
                    setattr(run, k, v)
                graded += 1
                if (served_days <= DRIFT_WINDOW_SERVED_DAYS and run.features_json
                        and run.source_json and run.source_json.get("as_of")):
                    resolved = await _production_model()
                    if resolved is not None:
                        models, _ = resolved
                        stds = dict(zip(models.pipeline.columns, models.pipeline.stds,
                                        strict=False))
                        cutoff = datetime.fromisoformat(run.source_json["as_of"])
                        sip = sip_features_for(client, run.target_date, cutoff)
                        if sip:
                            drift = compute_drift_row(run.features_json, sip, stds)
                            apply_drift_ladder(run.target_date, drift)
            await s.commit()
        logger.info("mktproj_outcomes_graded", graded=graded)
        return graded
    except Exception:  # noqa: BLE001
        logger.exception("mktproj_outcomes_failed")
        return graded


async def run_market_projection_regime_report(*, now: datetime | None = None) -> None:
    """Monthly guardrail 6: served-projection Brier by regime slice → evidence file."""
    import json
    import os

    now_et = (now or datetime.now(UTC)).astimezone(EASTERN)
    try:
        sf = get_sessionmaker()
        async with sf() as s:
            runs = (await s.execute(
                select(MarketProjectionRun).where(
                    MarketProjectionRun.run_status == "SUCCESS",
                    MarketProjectionRun.outcome_status == "graded",
                )
            )).scalars().all()
        if not runs:
            logger.info("mktproj_regime_report_empty")
            return
        slices: dict[str, list[Any]] = {}
        vols = sorted(
            (r.features_json or {}).get("spy_realized_vol_20d") or 0.0 for r in runs
        )
        stress_floor = vols[int(len(vols) * 0.9)] if len(vols) >= 10 else float("inf")
        for r in runs:
            f = r.features_json or {}
            keys = ["uptrend" if (f.get("regime_trend") or 0) >= 0.5 else "downtrend"]
            med = vols[len(vols) // 2]
            keys.append("vol_high" if (f.get("spy_realized_vol_20d") or 0) >= med else "vol_low")
            if (f.get("spy_realized_vol_20d") or 0) >= stress_floor:
                keys.append("stress_like")
            for k in keys:
                slices.setdefault(k, []).append(r)
        slice_stats: dict[str, dict[str, float]] = {
            k: {
                "days": float(len(v)),
                "brier_material": sum(
                    ((r.prob_material or 0.0)
                     - (1.0 if r.realized_label in ("UP", "DOWN") else 0.0)) ** 2
                    for r in v
                ) / len(v),
            }
            for k, v in sorted(slices.items())
        }
        month = now_et.strftime("%Y-%m")
        report = {"month": month, "served_graded": len(runs), "slices": slice_stats}
        os.makedirs("data/market_projection", exist_ok=True)
        path = f"data/market_projection/regime_report_{month}.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        logger.info("mktproj_regime_report_written", path=path, **{
            k: round(v["brier_material"], 4) for k, v in slice_stats.items()
        })
    except Exception:  # noqa: BLE001
        logger.exception("mktproj_regime_report_failed")
