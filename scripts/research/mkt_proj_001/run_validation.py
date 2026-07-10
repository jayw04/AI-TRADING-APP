"""MKT-PROJ-001 §2 — the baselines-only walk-forward evidence run (FR-005/007).

Run INSIDE the backend container on the box after the §1 dataset is persisted:

    sudo docker exec workbench-backend python3 /app/data/mkt_proj_001/run_validation.py \
        [--projection-type PRE_CLOSE_TOMORROW] [--out /app/data/mkt_proj_001/]

Baselines only — no ML exists yet by design: this run is the §2→§3 owner
checkpoint ("how hard is the target?"). Writes one evidence JSON per horizon
with the pooled walk-forward metrics for all pre-registered baselines, the
best-baseline identification, and reproducibility metadata (NFR-002).
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
from app.db.session import get_sessionmaker
from app.services.market_projection.baselines import baselines_for
from app.services.market_projection.schemas import (
    FEATURE_VERSION,
    LABEL_VERSION,
    ProjectionType,
)
from app.services.market_projection.validate import run_walk_forward

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
            {
                "date": r.date,
                "label": r.label,
                "realized_return": r.realized_return,
                "features_json": r.features_json,
            }
            for r in result.scalars()
        ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--projection-type", choices=[p.value for p in ProjectionType], default=None)
    ap.add_argument("--out", default=".")
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
        if not rows:
            continue
        predictors = baselines_for(ptype)
        directional = DIRECTIONAL_BASELINES + (
            ["premarket_gap_direction"] if ptype == ProjectionType.PRE_OPEN_TODAY else []
        )
        result = run_walk_forward(
            rows, predictors,
            magnitude_baselines=MAGNITUDE_BASELINES,
            directional_baselines=directional,
        )
        result["meta"] = {
            "program": "MKT-PROJ-001",
            "stage": "§2 baselines-only (owner checkpoint before §3 ML)",
            "projection_type": ptype.value,
            "feature_version": FEATURE_VERSION,
            "label_version": LABEL_VERSION,
            "pre_registration": "TradingWorkbench_MKT-PROJ-001_PreRegistration_v1.2.md",
            "git_commit": commit,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        out = Path(args.out) / f"baseline_walkforward_{ptype.value}.json"
        out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"wrote {out}")
        best = result["best_magnitude_baseline"]
        print(f"  best magnitude baseline: {best} "
              f"(brier={result['predictors'][best]['brier_material']:.4f})")
        print(f"  best directional baseline: {result['best_directional_baseline']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
