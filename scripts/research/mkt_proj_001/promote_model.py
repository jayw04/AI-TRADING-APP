"""MKT-PROJ-001 §4 guardrail 1 — audited candidate→production promotion.

Owner conditions (2026-07-11 approval): promotion is allowed ONLY when the
registry row's FULL sha256 matches the decided §3 candidate recorded in the
merged evidence manifest (ml_walkforward_PRE_CLOSE_TOMORROW.json →
registered_model.artifact_hash). No retraining, no artifact substitution —
a mismatch aborts loudly. The promotion writes MKTPROJ_MODEL_PROMOTED to the
hash-chained audit log (see docs/runbook/on-call.md).

Owner evidence review (2026-07-11) additionally requires a FULL provenance
record at promotion (git_commit:null is acceptable for draft evidence only):
training-code commit, evidence-JSON commit + path, ModelCard commit + path,
promotion operator, and timestamp all ride the audit payload, and the registry
row's git_commit is backfilled with the training-code commit. Do not retrain
or rebuild — this records provenance, nothing else.

Run inside the backend container on the box:

    sudo docker exec workbench-backend python3 /app/data/mkt_proj_001/promote_model.py \
        --manifest /app/data/mkt_proj_001/ml_walkforward_PRE_CLOSE_TOMORROW.json \
        --training-code-commit <sha> --evidence-commit <sha> --card-commit <sha> \
        --operator "Jay Wang"
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.audit.logger import AuditAction, AuditActorType, AuditLogger
from app.db.models.market_projection_model import MarketProjectionModelRegistry
from app.db.session import get_sessionmaker

EVIDENCE_PATH = "docs/implementation/evidence/mkt_proj_001/ml_walkforward_PRE_CLOSE_TOMORROW.json"
CARD_PATH = "docs/implementation/evidence/mkt_proj_001/ModelCard_v1.0.md"


async def promote(manifest_path: str, provenance: dict[str, str]) -> int:
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
        # owner evidence review 2026-07-11: git_commit:null is draft-only —
        # backfill the registry row with the training-code commit at promotion.
        row.git_commit = provenance["training_code_commit"]
        AuditLogger.write(
            s,
            actor_type=AuditActorType.SYSTEM,
            actor_id=None,
            action=AuditAction.MKTPROJ_MODEL_PROMOTED,
            target_type="market_projection_model",
            target_id=row.id,
            payload={
                "model_version": expected_version,
                "artifact_hash": expected_hash,   # full sha256, never truncated
                "projection_type": row.projection_type,
                "before_status": before,
                "evidence_manifest": manifest_path,
                "training_code_commit": provenance["training_code_commit"],
                "evidence_commit": provenance["evidence_commit"],
                "evidence_path": EVIDENCE_PATH,
                "model_card_commit": provenance["card_commit"],
                "model_card_path": CARD_PATH,
                "promotion_operator": provenance["operator"],
                "promotion_timestamp": datetime.now(UTC).isoformat(),
                "authority": "ModelCard v1.0 owner decision 2026-07-10/11 (§4 Q4) + "
                             "owner evidence review 2026-07-11 (provenance requirement)",
            },
            user_id=None,
        )
        await s.commit()
    print(f"PROMOTED {expected_version} ({before} → production), audit-logged with full provenance")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--training-code-commit", required=True,
                    help="git sha of the training code the §3 run executed")
    ap.add_argument("--evidence-commit", required=True,
                    help="git sha at which the evidence JSONs are merged on main")
    ap.add_argument("--card-commit", required=True,
                    help="git sha at which the corrected ModelCard is merged on main")
    ap.add_argument("--operator", required=True, help="human operator authorizing promotion")
    args = ap.parse_args()
    return asyncio.run(promote(args.manifest, {
        "training_code_commit": args.training_code_commit,
        "evidence_commit": args.evidence_commit,
        "card_commit": args.card_commit,
        "operator": args.operator,
    }))


if __name__ == "__main__":
    raise SystemExit(main())
