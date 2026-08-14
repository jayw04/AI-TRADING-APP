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
import hashlib
import json
import os
import sys
from typing import Any

from ..spq1.calendar import RegisteredCalendar
from ..spq1.identities import GOVERNING_IDENTITIES, InputIdentityRegistry
from . import FROZEN_CONFIG_MAPPING, FROZEN_CONTRACT_IDENTITIES, RUN_ID, WINDOW
from . import states as S
from .candidates import ProducerCandidateSource
from .guard import VALIDATION
from .readers import FixtureReader, PinnedObject, S3PinnedReader
from .roster import current_roster
from .runner import Phase3BRunner

REQUIRED_TABLES = ("prices", "etf_prices", "actions", "sic_observations", "universe", "anchors")
REQUIRED_REFERENCE = ("sic_mapping", "crosswalk")
REFERENCE_PREFIX = "reference"

# The reference manifest is hash-bound here, inside the mounted layer whose own identity Supplement
# v3 binds. Without this, "fetch whatever the manifest declares" would let a later manifest edit
# silently add an override object and the fetcher would obediently consume it.
REFERENCE_MANIFEST_SHA256 = "fc8e91e9bc78faa6936dc68b82414a6a0a500f0c41c4d303419a2157a7ce7d35"

# The governed privilege transition. Fixed here, never supplied at runtime: a caller-chosen ARN
# would let the caller decide which identity reads the sealed store.
VALIDATION_READER_ROLE_ARN = "arn:aws:iam::219024422756:role/mr002-validation-reader"
READER_SESSION_NAME = "mr002-p3b-validation-v1"

DRY, EXECUTE = "dry", "execute"


class EntrypointRefused(Exception):
    """The run cannot be assembled. Nothing is opened and nothing is spent."""


def _load(path: str) -> dict:
    if not os.path.exists(path):
        raise EntrypointRefused(f"required input absent: {path}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_bound(path: str, expected_sha256: str) -> dict:
    """Load a file whose exact bytes are bound, so an edited manifest cannot be substituted."""
    if not os.path.exists(path):
        raise EntrypointRefused(f"required input absent: {path}")
    with open(path, "rb") as fh:
        raw = fh.read()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise EntrypointRefused(
            f"{os.path.basename(path)} is not the bound artifact: {actual} != {expected_sha256}"
        )
    return json.loads(raw.decode("utf-8"))


class ReaderAssumptionRefused(Exception):
    """The governed reader identity could not be assumed. No S3 client is built, nothing is read."""


def s3_reader(region: str = "us-east-1", *, boto3_module: Any = None) -> S3PinnedReader:
    """Construct the real reader: lazy, and via the governed privilege transition.

    The host role holds an explicit Deny on the sealed bucket and must keep it. The only sanctioned
    path to a validation object is to assume ``mr002-validation-reader``, so the S3 client is built
    ONLY from the temporary credentials that assumption returns. There is deliberately no ambient
    fallback: if the assumption fails, the run refuses before any S3 call rather than quietly
    retrying as the host role, which would either be denied or - far worse - succeed for the wrong
    identity and make the privilege crossing unauditable.

    Still lazy. Nothing here calls STS until the first read, so a dry run reaches PRE_ACCESS_READY
    with no STS call, no reader credentials and no S3 client.

    The role ARN is a module constant, not a parameter: a runtime-supplied ARN would let the caller
    choose which identity reads the sealed store.
    """

    def factory():
        b3 = boto3_module
        if b3 is None:  # pragma: no cover - the real path, exercised only by the governed run
            import boto3 as b3
        sts = b3.client("sts", region_name=region)
        try:
            assumed = sts.assume_role(
                RoleArn=VALIDATION_READER_ROLE_ARN, RoleSessionName=READER_SESSION_NAME
            )
        except Exception as exc:
            raise ReaderAssumptionRefused(
                f"could not assume {VALIDATION_READER_ROLE_ARN}: {exc}. Refusing before any S3 "
                "call; there is no ambient-credential fallback."
            ) from exc
        creds = (assumed or {}).get("Credentials") or {}
        missing = [
            k for k in ("AccessKeyId", "SecretAccessKey", "SessionToken") if not creds.get(k)
        ]
        if missing:
            raise ReaderAssumptionRefused(
                f"assumption returned no usable credentials (missing {missing}); refusing rather "
                "than falling back to the host role"
            )
        return b3.client(
            "s3",
            region_name=region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )

    reader = S3PinnedReader(factory)
    reader.assumed_role_arn = VALIDATION_READER_ROLE_ARN
    reader.reader_session_name = READER_SESSION_NAME
    return reader


def _reference_keys(reference_manifest: dict) -> set[str]:
    """Exactly the reference objects the manifest declares - never everything sharing the prefix.

    The reference layer registers four objects; Phase 3B consumes two. Sharing a prefix is not a
    reason to fetch: pulling the two override tables in would ADD an execution dependency the
    development window never had, because Phase 2B reads `sic_mapping` and `crosswalk` raw.
    """
    declared = reference_manifest.get("objects") or {}
    if not declared:
        raise EntrypointRefused("reference manifest declares no objects")
    keys = set(declared)
    stray = sorted(k for k in keys if k.split("/", 1)[0] != REFERENCE_PREFIX)
    if stray:
        raise EntrypointRefused(f"reference manifest names non-reference objects: {stray}")
    committed = set(reference_manifest.get("structure") or {})
    named = {k.split("/", 1)[-1].removesuffix(".parquet") for k in keys}
    if named != committed:
        raise EntrypointRefused(
            f"reference manifest is internally inconsistent: objects {sorted(named)} != committed "
            f"structure {sorted(committed)}"
        )
    return keys


def pinned_inputs(
    upload_manifest: dict, *, window: str, reference_manifest: dict
) -> list[PinnedObject]:
    """Every governed object, addressed by bucket, key, VersionId and SHA-256.

    Window objects come from the window prefix. Reference objects come from the reference
    MANIFEST, not the reference prefix, so the fetched set equals the decoded set equals the
    consumed set.
    """
    objects = upload_manifest.get("objects") or {}
    bucket = upload_manifest.get("bucket")
    if not bucket:
        raise EntrypointRefused("upload manifest names no bucket")

    wanted = {k for k in objects if k.split("/", 1)[0] == window} | _reference_keys(
        reference_manifest
    )
    missing = sorted(wanted - set(objects))
    if missing:
        raise EntrypointRefused(f"declared inputs absent from the upload manifest: {missing}")

    out = [
        PinnedObject(bucket, key, objects[key]["version_id"], objects[key]["sha256"])
        for key in sorted(wanted)
    ]
    if not out:
        raise EntrypointRefused(f"no pinned objects for window {window!r}")
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
    inputs = pinned_inputs(upload_manifest, window=WINDOW, reference_manifest=reference_manifest)
    return Phase3BRunner(
        reader=reader,
        candidate_source=source,
        output_root=output_root,
        registered_objects={VALIDATION: {o.key for o in inputs}},
        inputs=inputs,
        bound_roster=current_roster(),
        # INDEPENDENT PROVENANCE on both of these. The left side is what the staged CONFIGURATION
        # asserts; the right side comes from the frozen authorities inside the hash-bound closure.
        # Supplying the configuration to both -- as this did until v3.4 -- made each check a
        # self-comparison that could not fail.
        contract_identities=dict(contract_identities),
        expected_contract_identities=dict(FROZEN_CONTRACT_IDENTITIES),
        config_mapping=dict(config_mapping),
        expected_config_mapping=dict(FROZEN_CONFIG_MAPPING),
        runtime_facts=dict(runtime_facts),
        expected_runtime_facts=dict(expected_runtime_facts),
        identities=dict(identities),
        # Not derived from the live mount: this is the CONFIGURATION's recording, and it is the
        # only side of the comparison that can disagree with the executing bytes.
        observed_identities=dict(observed_identities),
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
        reference_manifest=_load_bound(args.reference_manifest, REFERENCE_MANIFEST_SHA256),
        observed_identities=config["observed_identities"],
        runtime_facts=config["runtime_facts"],
        expected_runtime_facts=config["expected_runtime_facts"],
        contract_identities=config["contract_identities"],
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
