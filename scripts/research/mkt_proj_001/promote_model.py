"""MKT-PROJ-001 §4 guardrail 1 — audited candidate→production promotion.

Owner conditions (2026-07-11 approval): promotion is allowed ONLY when the
registry row's FULL sha256 matches the decided §3 candidate recorded in the
merged evidence manifest (ml_walkforward_PRE_CLOSE_TOMORROW.json →
registered_model.artifact_hash). No retraining, no artifact substitution —
a mismatch aborts loudly. The promotion writes MKTPROJ_MODEL_PROMOTED to the
hash-chained audit log (see docs/runbook/on-call.md).

Run inside the backend container on the box:

    sudo docker exec workbench-backend python3 /app/data/mkt_proj_001/promote_model.py \
        --manifest /app/data/mkt_proj_001/ml_walkforward_PRE_CLOSE_TOMORROW.json
"""

from __future__ import annotations

import argparse
import asyncio
import json

from sqlalchemy import select

from app.audit.logger import AuditAction, AuditActorType, AuditLogger
from app.db.models.market_projection_model import MarketProjectionModelRegistry
from app.db.session import get_sessionmaker


async def promote(manifest_path: str) -> int:
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    decided = manifest["registered_model"]
    expected_hash = decided["artifact_hash"]
    expected_version = decided["model_version"]

    sf = get_sessionmaker()
    async with sf() as s:
        row = (await s.execute(
            select(MarketProjectionModelRegistry).where(
                MarketProjectionModelRegistry.model_version == expected_version,
            )
        )).scalars().first()
        if row is None:
            print(f"ABORT: registry row {expected_version} not found")
            return 1
        if row.artifact_hash != expected_hash:
            print("ABORT: registry artifact_hash does not match the decided §3 manifest "
                  f"(registry {row.artifact_hash[:16]}… vs manifest {expected_hash[:16]}…) — "
                  "no substitution is permitted")
            return 1
        # hash-verified load proves the on-disk artifact matches too
        from app.services.market_projection.model_registry import load_artifact

        load_artifact(row.artifact_path, expected_hash)

        if row.status == "production":
            print(f"no-op: {expected_version} is already production")
            return 0
        before = row.status
        row.status = "production"
        AuditLogger.write(
            s,
            actor_type=AuditActorType.SYSTEM,
            actor_id=None,
            action=AuditAction.MKTPROJ_MODEL_PROMOTED,
            target_type="market_projection_model",
            target_id=row.id,
            payload={
                "model_version": expected_version,
                "artifact_hash": expected_hash,
                "projection_type": row.projection_type,
                "before_status": before,
                "evidence_manifest": manifest_path,
                "authority": "ModelCard v1.0 owner decision 2026-07-10/11 (§4 Q4)",
            },
            user_id=None,
        )
        await s.commit()
    print(f"PROMOTED {expected_version} ({before} → production), audit-logged")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    args = ap.parse_args()
    return asyncio.run(promote(args.manifest))


if __name__ == "__main__":
    raise SystemExit(main())
