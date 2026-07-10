"""MKT-PROJ-001 §3 — the ONE frozen ML evidence run (FR-006/007/008; pre-reg v1.2).

Run INSIDE the backend container on the box after §3 code is deployed:

    sudo docker exec workbench-backend python3 /app/data/mkt_proj_001/train_and_evaluate.py \
        [--projection-type PRE_CLOSE_TOMORROW] [--out /app/data/mkt_proj_001/]

Per horizon: walk-forward the three model predictors (calibrated logistic =
THE gate model; boosted + ensemble secondaries) against all pre-registered
baselines with identical fold/metric machinery to §2; compute the frozen
Move-Risk and Direction gates; batch permutation importance (attribution
diagnostic); fit + register the final candidate artifact (hash, NFR-002 row,
status=candidate); write the evidence JSON. One run — nothing is tuned after
seeing this output (pre-reg §10.3).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.db.models.market_projection import MarketProjectionTrainingRow
from app.db.models.market_projection_model import MarketProjectionModelRegistry
from app.db.session import get_sessionmaker
from app.services.market_projection.attribution import permutation_importance_material
from app.services.market_projection.baselines import baselines_for
from app.services.market_projection.model_registry import save_artifact
from app.services.market_projection.schemas import (
    FEATURE_VERSION,
    LABEL_VERSION,
    ProjectionType,
)
from app.services.market_projection.train import fit_models, manifest_for, model_predictors
from app.services.market_projection.validate import run_walk_forward, walk_forward_folds

MAGNITUDE_BASELINES = ["always_neutral", "unconditional", "vol_clustering_move_risk"]
DIRECTIONAL_BASELINES = ["prior_day_direction", "momentum_5d_direction"]


async def load_rows(ptype: ProjectionType) -> list[dict]:
    sf = get_sessionmaker()
    async with sf() as s:
        result = await s.execute(
            select(MarketProjectionTrainingRow).where(
                MarketProjectionTrainingRow.projection_type == ptype.value,
                MarketProjectionTrainingRow.feature_version == FEATURE_VERSION,
                MarketProjectionTrainingRow.valid_for_training.is_(True),
            ).order_by(MarketProjectionTrainingRow.date)
        )
        return [
            {"date": r.date, "label": r.label, "realized_return": r.realized_return,
             "features_json": r.features_json}
            for r in result.scalars()
        ]


async def persist_registry_row(fields: dict) -> None:
    sf = get_sessionmaker()
    async with sf() as s:
        s.add(MarketProjectionModelRegistry(**fields))
        await s.commit()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--projection-type", choices=[p.value for p in ProjectionType], default=None)
    ap.add_argument("--out", default=".")
    ap.add_argument("--artifact-dir", default="data/market_projection/models")
    args = ap.parse_args()
    ptypes = (
        [ProjectionType(args.projection_type)] if args.projection_type else list(ProjectionType)
    )
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10
        ).stdout.strip() or None
    except Exception:  # noqa: BLE001
        commit = None

    for ptype in ptypes:
        rows = asyncio.run(load_rows(ptype))
        print(f"{ptype.value}: {len(rows)} valid rows")
        if len(rows) < 800:
            print("  insufficient rows — skipping")
            continue

        predictors = dict(baselines_for(ptype))
        predictors.update(model_predictors(ptype))
        directional = DIRECTIONAL_BASELINES + (
            ["premarket_gap_direction"] if ptype == ProjectionType.PRE_OPEN_TODAY else []
        )
        result = run_walk_forward(
            rows, predictors,
            magnitude_baselines=MAGNITUDE_BASELINES,
            directional_baselines=directional,
            model_name="model_logistic",   # THE gate model (pre-reg §6)
        )

        # attribution diagnostic: permutation importance on the LAST fold's OOS days
        folds = walk_forward_folds([r["date"] for r in rows])
        train_idx, test_idx = folds[-1]
        final_models = fit_models([rows[i] for i in train_idx], ptype)
        result["permutation_importance_last_fold"] = permutation_importance_material(
            final_models.predict_logistic, [rows[i] for i in test_idx], manifest_for(ptype)
        )

        # final candidate artifact: fit on ALL valid rows (registered with the
        # walk-forward evidence; becomes production ONLY via the §4 review)
        all_models = fit_models(rows, ptype)
        reg = save_artifact(
            all_models,
            projection_type=ptype.value,
            model_type="calibrated_logistic_primary",
            training_window=f"{rows[0]['date']}..{rows[-1]['date']}",
            validation_window=f"{result['oos_start']}..{result['oos_end']}",
            git_commit=commit,
            artifact_dir=args.artifact_dir,
        )
        asyncio.run(persist_registry_row(dict(reg)))
        result["registered_model"] = reg

        result["meta"] = {
            "program": "MKT-PROJ-001",
            "stage": "§3 ML evidence (owner model-card review gates §4)",
            "projection_type": ptype.value,
            "feature_version": FEATURE_VERSION,
            "label_version": LABEL_VERSION,
            "pre_registration": "TradingWorkbench_MKT-PROJ-001_PreRegistration_v1.2.md",
            "git_commit": commit,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        out = Path(args.out) / f"ml_walkforward_{ptype.value}.json"
        out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"wrote {out}")
        m = result["predictors"]["model_logistic"]
        gate = result["move_risk_gate"]
        print(f"  model_logistic brier={m['brier_material']:.4f} ece={m['ece_material']:.4f} "
              f"cov={m['elevated_coverage']:.2f}")
        print(f"  move_risk_gate vs {gate['vs']}: delta={gate['brier_delta_ci']['delta']:.4f} "
              f"CI=[{gate['brier_delta_ci']['ci_low']:.4f},{gate['brier_delta_ci']['ci_high']:.4f}] "
              f"ece_ok={gate['ece_guardrail_ok']} cov_ok={gate['coverage_in_band']} "
              f"PASSES={gate['passes']}")
        print(f"  direction_gate: {json.dumps(result['direction_gate'], default=str)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
