"""The Phase 3B production entry point.

This is the only place the governed run is assembled, and the only place the real reader is
constructed. Everything below it builds its own world from the six committed tables: nothing is
injected except the reader, so the code path qualification exercises is the code path validation
runs.

Two modes:

  ``dry``      halts at S7_PRE_ACCESS_READY. Nothing is spent, the run is repeatable, and every
               identity, configuration, runtime and output check has already passed.
  ``execute``  continues through the seam. The first successful validation GetObject consumes the
               single opening, and restart is prohibited thereafter.

`dry` is the default. Spending a one-time opening should require saying so.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from ..spq1.calendar import RegisteredCalendar
from ..spq1.identities import GOVERNING_IDENTITIES, InputIdentityRegistry
from . import RUN_ID, WINDOW
from . import states as S
from .candidates import ProducerCandidateSource
from .guard import VALIDATION
from .readers import FixtureReader, PinnedObject, S3PinnedReader
from .roster import current_roster
from .runner import Phase3BRunner

REQUIRED_TABLES = ("prices", "etf_prices", "actions", "sic_observations", "universe", "anchors")
REQUIRED_REFERENCE = ("sic_mapping", "crosswalk")

DRY, EXECUTE = "dry", "execute"


class EntrypointRefused(Exception):
    """The run cannot be assembled. Nothing is opened and nothing is spent."""


def _load(path: str) -> dict:
    if not os.path.exists(path):
        raise EntrypointRefused(f"required input absent: {path}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def s3_reader(region: str = "us-east-1") -> S3PinnedReader:
    """Construct the real reader. Deliberately builds no client until the first read.

    A reader that connects eagerly invites a probe before PRE_ACCESS_READY, which is exactly the
    event the whole sequence exists to prevent.
    """

    def factory():  # pragma: no cover - exercised only by the governed run
        import boto3

        return boto3.client("s3", region_name=region)

    return S3PinnedReader(factory)


def pinned_inputs(upload_manifest: dict, prefixes: tuple[str, ...]) -> list[PinnedObject]:
    """Every governed object, addressed by bucket, key, VersionId and SHA-256."""
    objects = upload_manifest.get("objects") or {}
    bucket = upload_manifest.get("bucket")
    if not bucket:
        raise EntrypointRefused("upload manifest names no bucket")
    out = [
        PinnedObject(bucket, key, meta["version_id"], meta["sha256"])
        for key, meta in sorted(objects.items())
        if key.split("/", 1)[0] in prefixes
    ]
    if not out:
        raise EntrypointRefused(f"no pinned objects under {prefixes}")
    return out


def build_runner(
    *,
    reader: Any,
    output_root: str,
    sessions: list[str],
    upload_manifest: dict,
    structural_manifest: dict,
    reference_manifest: dict,
    observed_identities: dict[str, str],
    runtime_facts: dict[str, str],
    expected_runtime_facts: dict[str, str],
    contract_identities: dict[str, str],
    published_at: str,
    identities: dict[str, str],
    config_mapping: dict[str, float],
) -> Phase3BRunner:
    """Assemble the governed run. The reader is the ONLY injected dependency."""
    calendar = RegisteredCalendar(tuple(sessions))
    registry_ids = dict(observed_identities)
    registry_ids["registered_exchange_calendar"] = calendar.identity
    registry_ids.update(GOVERNING_IDENTITIES)

    source = ProducerCandidateSource(
        calendar=calendar,
        registry=InputIdentityRegistry(registry_ids),
        observed_identities=dict(observed_identities),
        structural_manifest=structural_manifest,
        reference_manifest=reference_manifest,
        window_prefix=WINDOW,
    )
    inputs = pinned_inputs(upload_manifest, (WINDOW, "reference"))
    return Phase3BRunner(
        reader=reader,
        candidate_source=source,
        output_root=output_root,
        registered_objects={VALIDATION: {o.key for o in inputs}},
        inputs=inputs,
        bound_roster=current_roster(),
        contract_identities=dict(contract_identities),
        expected_contract_identities=dict(contract_identities),
        config_mapping=dict(config_mapping),
        expected_config_mapping=dict(config_mapping),
        runtime_facts=dict(runtime_facts),
        expected_runtime_facts=dict(expected_runtime_facts),
        published_at=published_at,
        identities=dict(identities),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=f"mr002-{RUN_ID}", description="MR-002 Phase 3B run")
    parser.add_argument("--mode", choices=(DRY, EXECUTE), default=DRY)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--sessions", required=True, help="registered session list JSON")
    parser.add_argument("--upload-manifest", required=True)
    parser.add_argument("--structural-manifest", required=True)
    parser.add_argument("--reference-manifest", required=True)
    parser.add_argument("--config", required=True, help="run configuration JSON")
    parser.add_argument(
        "--fixture-root", default=None, help="qualification only; forces the hermetic reader"
    )
    args = parser.parse_args(argv)

    # Checked BEFORE any file is opened: a mis-declared execution must fail on the declaration,
    # not on whichever input happens to be missing.
    if args.mode == EXECUTE and args.fixture_root:
        raise EntrypointRefused("refusing to call a fixture run an execution")

    config = _load(args.config)
    reader = FixtureReader(args.fixture_root) if args.fixture_root else s3_reader()

    runner = build_runner(
        reader=reader,
        output_root=args.output_root,
        sessions=_load(args.sessions),
        upload_manifest=_load(args.upload_manifest),
        structural_manifest=_load(args.structural_manifest),
        reference_manifest=_load(args.reference_manifest),
        observed_identities=config["observed_identities"],
        runtime_facts=config["runtime_facts"],
        expected_runtime_facts=config["expected_runtime_facts"],
        contract_identities=config["contract_identities"],
        published_at=config["published_at"],
        identities=config["identities"],
        config_mapping=config["config_mapping"],
    )
    outcome = runner.run(stop_at=S.S7_PRE_ACCESS_READY if args.mode == DRY else None)
    print(
        json.dumps(
            {
                "run_id": RUN_ID,
                "mode": args.mode,
                "disposition": outcome.disposition,
                "exit_code": outcome.exit_code,
                "state": outcome.state,
                "opening_consumed": outcome.opening_consumed,
                "error": outcome.error,
            },
            indent=1,
        )
    )
    return outcome.exit_code


if __name__ == "__main__":
    sys.exit(main())
