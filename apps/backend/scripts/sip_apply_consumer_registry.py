"""Apply the SIP consumer registry artifact (SIP-CACHE-001 B3, Decision 1).

    python scripts/sip_apply_consumer_registry.py \
        --artifact config/sip_consumer_registry.v1.json \
        --expect-sha256 <sha256 of the reviewed artifact> \
        --applied-by <operator identity> [--apply]

Dry-run by default: prints what WOULD be issued / updated / revoked and exits 0 without touching the
database. ``--apply`` performs the change and audits every issuance and revocation under
``--applied-by``. Refuses (exit 3) if the artifact on disk does not hash to ``--expect-sha256`` —
the operator applies the artifact they reviewed, not whatever is on disk now.

This is the ONLY sanctioned way a SIP consumer registration comes into existence. Nothing is
discovered from strategies, scheduler jobs, credentials, SIP-capable accounts, or running processes.
No secret is read, printed, or logged here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


def _parse(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--artifact", required=True, help="path to the registry artifact (JSON)")
    ap.add_argument(
        "--expect-sha256", required=True, help="sha256 of the reviewed artifact; mismatch refuses"
    )
    ap.add_argument(
        "--applied-by", required=True, help="operator identity recorded in the audit log"
    )
    ap.add_argument("--apply", action="store_true", help="perform the change (default: dry run)")
    return ap.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    from app.config import get_settings
    from app.db.session import get_sessionmaker
    from app.market_data.sip.demand import (
        ConsumerRegistry,
        DemandPlaneConfig,
        NoFreshnessPolicy,
        RegistryArtifactError,
        artifact_sha256,
    )

    raw = Path(args.artifact).read_bytes()
    digest = artifact_sha256(raw)
    if digest != args.expect_sha256.lower():
        print(
            f"REFUSED: artifact sha256 {digest} != expected {args.expect_sha256.lower()}",
            file=sys.stderr,
        )
        return 3
    artifact = json.loads(raw.decode("utf-8"))
    settings = get_settings()
    registry = ConsumerRegistry(
        get_sessionmaker(),
        config=DemandPlaneConfig.from_settings(settings),
        policy=NoFreshnessPolicy(),
    )
    try:
        result = await registry.apply_artifact(
            artifact,
            artifact_sha256=digest,
            applied_by=args.applied_by,
            dry_run=not args.apply,
        )
    except RegistryArtifactError as exc:
        print(f"REFUSED: invalid artifact — {exc}", file=sys.stderr)
        return 4
    mode = "APPLIED" if args.apply else "DRY RUN"
    print(f"{mode}  artifact={digest}")
    print(f"  issued : {list(result.issued)}")
    print(f"  updated: {list(result.updated)}")
    print(f"  revoked: {list(result.revoked)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
