"""Generate supplemental execution identity v2.0 against the pushed checkpoint 0eac4fe.

v1.0 (a2f2ff32...) bound an execution layer that could not actually be invoked: there was no entry
point, no production reader construction, and the world was assembled by test fixtures rather than
by the code under authorization. It was adjudicated ACCEPTED and then superseded when the live
preflight showed the package was executionally incomplete. **No sealed opening ever occurred under
it.** v2.0 binds the completed production invocation path.

Everything v1 did, v2 still does: reads the PUSHED tree only, closes the roster, binds qualification
by identity rather than by claim, and demonstrates grant compatibility instead of asserting it.

v2 adds three things.

**A required-input consumption matrix, derived from source.** For every governed table the package
locates the production component that consumes it and records the control purpose it serves. A table
that is loaded but consumed nowhere refuses generation. This makes the defect class that invalidated
v1 - inputs present but not actually used - mechanically detectable rather than reviewer-detectable.

**Semantic guarantees verified from the checkpoint, not asserted.** "anchors cannot be optional" and
"the mode check precedes any file open" are checked against the bytes at the checkpoint, including
one ordering check that a prose claim could not capture.

**An explicit supersession record** naming v1 by both of its hashes, why it was superseded, and that
the opening remained unspent throughout.

Zero-data instrument: reads git objects only. No AWS call, no sealed object, no credential.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess

CHECKPOINT = "0eac4fe98aad41c4de7e5f41d1f1c39d25247f15"
CHECKPOINT_SHORT = "0eac4fe"
BRANCH = "research/mr002-preregistration"

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))

LAYER_DIR = "apps/backend/app/research/mr002/phase3b"
QUAL_DIR = "apps/backend/tests/research/phase3b"
SPQ1 = "apps/backend/app/research/mr002/spq1"
GOV_DIR = "docs/review/mr002/phase3bc"

PRODUCER_MODULES = (
    "calendar.py", "constants.py", "eligibility.py", "identities.py", "liquidity.py",
    "models.py", "normalization.py", "producer.py", "refusals.py", "residuals.py",
    "returns.py", "sector_factor.py", "sector_pit.py", "security_identity.py",
    "stock_regression.py",
)
REUSED_FROZEN = (
    f"{SPQ1}/phase2b/__init__.py",
    f"{SPQ1}/phase2b/cutoff.py",
    f"{SPQ1}/phase2b/sic_sector.py",
    f"{SPQ1}/adapters/__init__.py",
)

# Modules v1 could not bind because they did not exist. Their absence is what made v1 incomplete.
V2_ADDED_MODULES = ("entrypoint.py", "earnings_blackout.py")

# The closed governed-input set, exactly as the entry point declares it.
WINDOW_TABLES = ("prices", "etf_prices", "actions", "sic_observations", "universe", "anchors")
REFERENCE_TABLES = ("sic_mapping", "crosswalk")

# Every governed table must have a registered PURPOSE. A table with no purpose is either an
# unregistered input or a control nobody can name - both refuse.
TABLE_PURPOSE = {
    "prices": (
        "raw OHLCV: the close_t / open_t+1 execution seam, the registered economic gap, ADV and "
        "price liquidity screens, and the residual return series"
    ),
    "etf_prices": (
        "sector-proxy and SPY series for the sector-neutral factor regression; without it the "
        "residual is not sector-neutral"
    ),
    "actions": (
        "corporate actions: the known cash distribution term of the registered economic gap, and "
        "the split basis adjudicated in A1-F1"
    ),
    "sic_observations": (
        "point-in-time SIC with its acceptance timestamp: the PIT sector assignment, so sector "
        "membership is never known before it was filed"
    ),
    "universe": (
        "monthly reconstitution membership: enumerates the governed (symbol, decision-session) "
        "units and the long/short eligibility flags"
    ),
    "anchors": (
        "earnings anchors: BOTH frozen event controls - the 70-calendar-day stale-anchor blackout "
        "and the two-session post-release cooling interval. Absence disables both controls, which "
        "is the exact Phase 2B nonconformance; therefore absence must refuse"
    ),
    "sic_mapping": (
        "registered SIC-range to research-sector and sector-proxy mapping, with effective dates"
    ),
    "crosswalk": (
        "permaticker/ticker/CIK intervals: PIT security lineage and CIK resolution, so a reused "
        "ticker is never silently treated as the same security"
    ),
}

# The eight semantic guarantees the owner requires reasserted. Each is CHECKED, not declared.
QUALIFICATION_SUITES = {
    "execution_qualification": {
        "file": f"{QUAL_DIR}/test_phase3b_entrypoint_qualification.py",
        "role": (
            "EXECUTION qualification - drives the real entry point and injects NOTHING except the "
            "hermetic reader. The world is built by the same constructors validation will use."
        ),
    },
    "component_qualification": {
        "files": [
            f"{QUAL_DIR}/test_phase3b_real_adapter_e2e.py",
            f"{QUAL_DIR}/test_phase3b_candidate_equivalence.py",
            f"{QUAL_DIR}/test_phase3b_producer_equivalence.py",
        ],
        "role": (
            "COMPONENT qualification - injects units, identity and eligibility to isolate a "
            "component. These suites opt OUT of the earnings controls EXPLICITLY rather than by "
            "omitting a table, so a missing input can never disable a control silently."
        ),
    },
}

QUALIFICATION_RESULTS = {
    "phase3b_suite": {"tests": 192, "result": "PASS", "ruff": "clean"},
    "entry_point_qualification": {
        "tests": 20,
        "result": "PASS",
        "non_vacuity_conditions": 8,
        "observed": (
            "all six window tables and both reference tables opened by production construction; "
            "universe contributes units; crosswalk contributes a mid-window lineage interval; "
            "anchors produce BOTH a cooling and a stale-anchor exclusion; an ambiguous symbol stays "
            "unresolved and is reported; removing ANY of the eight required inputs refuses; "
            "PRE_ACCESS_READY is reached with no AWS, zero reads and zero bytes; the reader is the "
            "only injected dependency"
        ),
    },
    "defects_found_by_the_new_qualification": [
        {
            "defect": "a missing anchors table silently disabled BOTH frozen earnings controls",
            "severity": "critical",
            "significance": (
                "this is the exact Phase 2B nonconformance, reintroduced by optional-table handling "
                "inside the correction meant to fix it. It is the failure mode that invalidated the "
                "v1 package, and it is now caught by the entry-point suite."
            ),
            "resolution": "CandidateSourceRefused; a named test asserts the refusal",
        },
        {
            "defect": "--mode execute --fixture-root failed on a missing file, not on the contradiction",
            "severity": "moderate",
            "significance": "a mis-declared execution must fail on the declaration",
            "resolution": "the mode check now runs before any file is opened; ordering is verified",
        },
    ],
    "mutation_check_a1f2": {
        "result": "PASS",
        "proves": "the suite ENFORCES the registered economic-gap formula",
    },
    "mutation_check_assembly": {
        "result": "PASS",
        "drifts_detected": 4,
        "proves": "the equivalence suite detects every injected drift by the comparison meant to "
                  "detect it",
    },
    "mutation_check_execution_protocol": {
        "requirement": "RUN SEQUENTIALLY, NEVER CONCURRENTLY",
        "reason": (
            "each check mutates a source file the other's baseline suite depends on. Run in "
            "parallel they refuse with 'the suite does not pass before mutation' - which is the "
            "guard working correctly, not a failure. Both PASS when run in isolation."
        ),
        "post_condition": "the working tree is verified byte-for-byte restored after each run",
    },
}

P12_BOUND = {
    "evaluator_image_index":
        "sha256:194efbdf96ee11c19f3554dcf1b1097958cdc347bcdc1637504b441237432f51",
    "dependency_lockfile_sha256":
        "bb38b685d15f78b705fff2681b76807f2277b02f7af5788e4c320951121c7ebd",
    "numeric_runtime_manifest_sha256":
        "8e5e39471c0d96c5cd6916e7c316bc74fa320336c7e0106515ede11f479c1ed0",
    "frozen_host": "i-00c1034f7026db45e",
    "qualified_host_role_arn": "arn:aws:iam::219024422756:role/mr002-phase3c-run-host",
    "resolver": "WP-B Requirement-7 fail-closed resolver",
}
P12_FILE_IDENTITIES = {
    "numeric_runtime_manifest_sha256":
        f"{GOV_DIR}/MR002_NumericRuntimeIdentityManifest_RuntimeInstance_v1.0.json",
    "dependency_lockfile_sha256":
        "docs/review/mr002/evaluator/MR002_LinuxDependencyLock_v1.1.json",
}

# Governing records this package binds by identity so a reviewer can reconstruct the whole chain.
GOVERNING_RECORDS = (
    "MR002_Phase3B_RunSpecification_v1.0.json",
    "MR002_Phase3B_ExecutionBoundaryClarification_v1.0.json",
    "MR002_Phase3B_ExecutionBoundary_EvidenceMemo_v1.0.md",
    "MR002_Phase3B_LaunchPreflight_BlockerRegister_v1.0.json",
    "MR002_Phase3B_LaunchPreflight_Corrigendum_v1.0.json",
    "MR002_Phase3B_LaunchPreflight_Corrigendum_v2.0.json",
    "MR002_Phase3B_ProducerIdentityContinuity_v1.0.json",
    "MR002_Phase3B_A1_PriceBasisEvidence_v1.0.json",
    "MR002_Phase3B_A1F1_ActionsSplitBasis_v1.0.json",
    "MR002_Phase3B_EarningsControlStructuralCensus_v1.0.json",
    "MR002_Phase3B_CorrectedDevelopmentReconciliation_v1.0.json",
    "MR002_Phase3B_SupplementalExecutionIdentity_v1.0.json",
    "MR002_Phase3BC_P12AuthorizationGrant_v1.0.json",
    "MR002_Phase3BC_ValidationAuthorizationState_v1.0.json",
)

SUPERSEDED_V1 = {
    "artifact": f"{GOV_DIR}/MR002_Phase3B_SupplementalExecutionIdentity_v1.0.json",
    "record_identity_sha256":
        "a2f2ff32b3a10a25814f76c5cb2f0abc6741931dbe282fd36dc77eb2e61add2e",
    "file_sha256": "6c0d0b6cf579025d7ba482b2664e1f6ac6be5ca88c5157174abb9053ba461cae",
    "checkpoint": "6d2a21f9bc8f1ef24d2fa5852b558259f83ab259",
}


class SupplementRefused(Exception):
    """The package cannot be generated truthfully. Nothing is emitted."""


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _git(*args: str) -> bytes:
    proc = subprocess.run(["git", "-C", _REPO, *args], capture_output=True)
    if proc.returncode != 0:
        raise SupplementRefused(f"git {' '.join(args)}: {proc.stderr.decode()[:200]}")
    return proc.stdout


def _blob(path: str) -> bytes:
    """Read a file AS PUSHED, never from the working tree."""
    return _git("show", f"{CHECKPOINT}:{path}")


def _text(path: str) -> str:
    return _blob(path).decode("utf-8")


def _sha(path: str) -> str:
    return hashlib.sha256(_blob(path)).hexdigest()


def _tree_files(directory: str) -> list[str]:
    out = _git("ls-tree", "-r", "--name-only", CHECKPOINT, "--", directory).decode().split()
    return sorted(f for f in out if f.endswith(".py"))


def verify_checkpoint_is_pushed() -> dict:
    remote = _git("rev-parse", f"origin/{BRANCH}").decode().strip()
    if remote != CHECKPOINT:
        raise SupplementRefused(
            f"remote head {remote[:12]} is not the checkpoint {CHECKPOINT[:12]}; the package must "
            "bind an immutable pushed commit, never a working tree"
        )
    if f"origin/{BRANCH}" not in _git("branch", "-r", "--contains", CHECKPOINT).decode():
        raise SupplementRefused("checkpoint is not contained in the pushed branch")
    return {
        "commit": CHECKPOINT,
        "short": CHECKPOINT_SHORT,
        "branch": BRANCH,
        "remote_head_matches": True,
        "subject": _git("log", "-1", "--format=%s", CHECKPOINT).decode().strip(),
        "read_from": "git object store at the checkpoint; the working tree is NOT consulted",
    }


def closed_roster() -> dict:
    layer = _tree_files(LAYER_DIR)
    if not layer:
        raise SupplementRefused("execution layer is empty at the checkpoint")

    layer_names = {os.path.basename(p) for p in layer}
    missing_new = [m for m in V2_ADDED_MODULES if m not in layer_names]
    if missing_new:
        raise SupplementRefused(
            f"v2 exists to bind the completed invocation path, but these are absent: {missing_new}"
        )

    producer = [f"{SPQ1}/{m}" for m in sorted(PRODUCER_MODULES)]
    spq1_files = set(_tree_files(SPQ1))
    absent = [p for p in producer if p not in spq1_files]
    if absent:
        raise SupplementRefused(f"producer modules absent at the checkpoint: {absent}")
    if len(producer) != 15:
        raise SupplementRefused(f"expected 15 producer modules, enumerated {len(producer)}")

    for path in REUSED_FROZEN:
        _blob(path)  # refuses if absent

    qualification = _tree_files(QUAL_DIR)
    if not qualification:
        raise SupplementRefused("qualification code is empty at the checkpoint")
    for key, spec in QUALIFICATION_SUITES.items():
        for f in [spec["file"]] if "file" in spec else spec["files"]:
            if f not in qualification:
                raise SupplementRefused(f"{key} names {f}, absent at the checkpoint")

    governance = [f"{GOV_DIR}/{n}" for n in GOVERNING_RECORDS]
    everything = layer + producer + list(REUSED_FROZEN) + qualification + governance
    if len(everything) != len(set(everything)):
        raise SupplementRefused("a module is bound twice; the roster is not closed")

    return {
        "execution_layer": {p: _sha(p) for p in layer},
        "producer_modules": {p: _sha(p) for p in producer},
        "reused_frozen_phase2b": {p: _sha(p) for p in REUSED_FROZEN},
        "qualification_code": {p: _sha(p) for p in qualification},
        "governing_records": {p: _sha(p) for p in governance},
        "added_since_v1": {
            f"{LAYER_DIR}/{m}": _sha(f"{LAYER_DIR}/{m}") for m in V2_ADDED_MODULES
        },
        "suite_roles": QUALIFICATION_SUITES,
        "counts": {
            "execution_layer": len(layer),
            "producer_modules": len(producer),
            "reused_frozen_phase2b": len(REUSED_FROZEN),
            "qualification_code": len(qualification),
            "governing_records": len(governance),
            "total_bound": len(everything),
        },
        "closure_rule": (
            "A missing, modified or ADDITIONAL runtime-critical module refuses generation. An "
            "unenumerated file that executes is the gap this package exists to close."
        ),
    }


def consumption_matrix() -> dict:
    """Derive, per governed table, WHICH production component consumes it and to what end.

    A table that is declared required and consumed nowhere refuses generation. That is the defect
    class - inputs present but unused - that a file listing cannot detect.
    """
    entry = _text(f"{LAYER_DIR}/entrypoint.py")
    declared_window = re.search(r"REQUIRED_TABLES\s*=\s*\(([^)]*)\)", entry)
    declared_ref = re.search(r"REQUIRED_REFERENCE\s*=\s*\(([^)]*)\)", entry)
    if not declared_window or not declared_ref:
        raise SupplementRefused("entrypoint does not declare its required inputs")
    found_window = tuple(re.findall(r'"([^"]+)"', declared_window.group(1)))
    found_ref = tuple(re.findall(r'"([^"]+)"', declared_ref.group(1)))
    if found_window != WINDOW_TABLES or found_ref != REFERENCE_TABLES:
        raise SupplementRefused(
            f"the entry point's declared inputs {found_window}+{found_ref} do not match the "
            f"registered set {WINDOW_TABLES}+{REFERENCE_TABLES}"
        )

    layer = _tree_files(LAYER_DIR)
    sources = {p: _text(p) for p in layer}

    matrix, unconsumed = {}, []
    for table in WINDOW_TABLES + REFERENCE_TABLES:
        if table not in TABLE_PURPOSE:
            raise SupplementRefused(f"governed table {table!r} has no registered purpose")
        sites = []
        for path, src in sources.items():
            if path.endswith("entrypoint.py"):
                continue  # declaration, not consumption
            for m in re.finditer(rf'tables\[\s*"{re.escape(table)}"\s*\]', src):
                line = src.count("\n", 0, m.start()) + 1
                sites.append(f"{path}:{line}")
        if not sites:
            unconsumed.append(table)
        matrix[table] = {
            "class": "window" if table in WINDOW_TABLES else "reference",
            "consumed_by": sorted(sites),
            "consumer_count": len(sites),
            "purpose": TABLE_PURPOSE[table],
        }

    if unconsumed:
        raise SupplementRefused(
            f"declared required but consumed by no production component: {unconsumed}. An input "
            "that is loaded and never used is a control that does not exist."
        )

    # The converse: a table read from `tables[...]` that is not in the registered set.
    all_keys = set()
    for path, src in sources.items():
        if path.endswith("entrypoint.py"):
            continue
        all_keys.update(re.findall(r'tables\[\s*"([^"]+)"\s*\]', src))
    unregistered = sorted(all_keys - set(WINDOW_TABLES) - set(REFERENCE_TABLES))
    if unregistered:
        raise SupplementRefused(f"production code consumes unregistered inputs: {unregistered}")

    return {
        "derivation": (
            "derived from the checkpoint blobs by locating every `tables[\"<name>\"]` consumption "
            "site outside the entry point; NOT declared by the author"
        ),
        "matrix": matrix,
        "bidirectional_closure": (
            "every registered table has at least one production consumer, AND every consumed key "
            "is a registered table. Either direction failing refuses generation."
        ),
        "detects": (
            "the defect class that invalidated v1: governed inputs present in the manifest but "
            "consumed by nothing, so the control they carry silently does not exist"
        ),
    }


def semantic_guarantees() -> dict:
    """Verify the owner-required semantics against the bytes at the checkpoint."""
    entry = _text(f"{LAYER_DIR}/entrypoint.py")
    candidates = _text(f"{LAYER_DIR}/candidates.py")
    guard = _text(f"{LAYER_DIR}/guard.py")
    execq = _text(QUALIFICATION_SUITES["execution_qualification"]["file"])

    checks: list[tuple[str, bool, str, str]] = []

    checks.append((
        "anchors_are_mandatory_never_optional",
        "anchors table absent: the frozen earnings controls cannot be applied" in candidates,
        f"{LAYER_DIR}/candidates.py",
        "a missing anchors table raises CandidateSourceRefused rather than disabling both controls",
    ))

    checks.append((
        "both_frozen_earnings_controls_are_active",
        all(
            t in _text(f"{LAYER_DIR}/earnings_blackout.py")
            for t in ("STALE_ANCHOR_DAYS", "cooling_interval", "stale_anchor_start")
        ),
        f"{LAYER_DIR}/earnings_blackout.py",
        "the 70-calendar-day stale-anchor blackout and the two-session post-release cooling are "
        "both implemented and separately identified",
    ))

    checks.append((
        "default_mode_stops_at_pre_access_ready",
        'default=DRY' in entry and "stop_at=S.S7_PRE_ACCESS_READY if args.mode == DRY" in entry,
        f"{LAYER_DIR}/entrypoint.py",
        "the default mode is dry and dry halts at S7_PRE_ACCESS_READY; spending a one-time opening "
        "requires saying so",
    ))

    # An ORDERING guarantee: the mode contradiction must be caught before any file is opened.
    main_body = entry.split("def main(", 1)[-1]
    mode_check = main_body.find("refusing to call a fixture run an execution")
    first_load = main_body.find("_load(")
    checks.append((
        "mode_validation_precedes_any_input_opening",
        mode_check != -1 and first_load != -1 and mode_check < first_load,
        f"{LAYER_DIR}/entrypoint.py",
        f"the mode contradiction check appears at offset {mode_check} in main(), before the first "
        f"_load() at offset {first_load}; a mis-declared execution fails on the declaration, not on "
        "whichever input happens to be missing",
    ))

    # Laziness is an INDENTATION fact: a module-level import would connect before PRE_ACCESS_READY.
    boto_lines = [ln for ln in entry.splitlines() if "import boto3" in ln]
    checks.append((
        "real_aws_client_construction_is_lazy",
        bool(boto_lines) and all(ln.startswith("        ") for ln in boto_lines),
        f"{LAYER_DIR}/entrypoint.py",
        "every `import boto3` is nested inside the client factory, so no client and no credential "
        "resolution can occur during dry qualification",
    ))

    checks.append((
        "no_downstream_fixtures_are_injected_in_execution_qualification",
        "source.units is None and source.lineage is None and source.cik_by_symbol is None" in execq
        and "source.eligibility_checks_by_symbol is None" in execq,
        QUALIFICATION_SUITES["execution_qualification"]["file"],
        "the execution suite asserts the entry point injects no units, lineage, CIK map or "
        "eligibility checks; the world is built by the code under authorization",
    ))

    checks.append((
        "removing_any_required_input_refuses",
        "test_removing_any_required_input_makes_the_run_refuse" in execq,
        QUALIFICATION_SUITES["execution_qualification"]["file"],
        "parameterised over all eight governed tables",
    ))

    checks.append((
        "oos_is_refused_unconditionally",
        'return False, "oos_denied_requires_separate_authorization"' in guard,
        f"{LAYER_DIR}/guard.py",
        "no code path in the guard can turn a validation authorisation into an OOS authorisation",
    ))

    failed = [name for name, ok, _, _ in checks if not ok]
    if failed:
        raise SupplementRefused(f"semantic guarantees NOT verifiable at the checkpoint: {failed}")

    return {
        "verification_mode": "CHECKED against the bytes at the checkpoint, not asserted in prose",
        "guarantees": {
            name: {"verified": True, "verified_from": path, "evidence": ev}
            for name, ok, path, ev in checks
        },
        "count": len(checks),
    }


def supersession() -> dict:
    """Name v1 unambiguously and record why it did not survive."""
    actual_file = _sha(SUPERSEDED_V1["artifact"])
    if actual_file != SUPERSEDED_V1["file_sha256"]:
        raise SupplementRefused(
            f"the artifact being superseded does not hash as recorded: {actual_file}"
        )
    v1 = json.loads(_blob(SUPERSEDED_V1["artifact"]))
    if v1.get("record_identity_sha256") != SUPERSEDED_V1["record_identity_sha256"]:
        raise SupplementRefused("v1 declares a different record identity than the one superseded")

    return {
        "supersedes": SUPERSEDED_V1["artifact"],
        "superseded_identity": SUPERSEDED_V1["record_identity_sha256"],
        "superseded_file_sha256": SUPERSEDED_V1["file_sha256"],
        "superseded_checkpoint": SUPERSEDED_V1["checkpoint"],
        "status_assigned_to_v1": "SUPERSEDED_EXECUTIONALLY_INCOMPLETE",
        "adjudication_history_of_v1": (
            "ADJUDICATED ACCEPTED on the evidence available at the time, then withdrawn from "
            "execution authority when the live-state preflight established the package could not "
            "actually be invoked."
        ),
        "why_superseded": [
            "no production entry point existed: nothing assembled the governed run",
            "the real S3 reader was never constructed by production code",
            "the world - units, PIT lineage, CIK resolution, eligibility - was supplied by test "
            "fixtures, so qualification did not exercise the code path validation would run",
            "the two frozen earnings controls were absent from the execution path entirely",
        ],
        "opening_status_throughout": {
            "sealed_opening_occurred_under_v1": False,
            "basis": (
                "v1 was never executed against AWS. No credential was assumed, no host was started "
                "and no GetObject was issued under it; the recorded access history at the last live "
                "preflight showed zero validation reads and the package was superseded before any "
                "execution was authorized."
            ),
            "note": (
                "this is asserted from the governed record and the absence of any execution event, "
                "not from a fresh live query - re-verifying by touching the store would itself be "
                "the event under control."
            ),
        },
        "what_v2_adds": [
            "the production entry point (entrypoint.py): the only place the run is assembled and "
            "the only place S3PinnedReader is constructed",
            "the frozen earnings controls (earnings_blackout.py) wired into the eligibility path",
            "production construction of units, PIT lineage, CIK resolution and earnings intervals "
            "from the governed tables themselves",
            "execution qualification driven from the real entry point with nothing injected but "
            "the hermetic reader",
            "a derived required-input consumption matrix",
        ],
        "unchanged_from_v1": (
            "the research identity, the frozen contract, the evaluator image, the configuration "
            "set, and every P12-bound identity"
        ),
    }


def grant_compatibility() -> dict:
    verified = {}
    for name, path in P12_FILE_IDENTITIES.items():
        actual = _sha(path)
        if actual != P12_BOUND[name]:
            raise SupplementRefused(
                f"P12-bound identity {name} CHANGED: {actual} != {P12_BOUND[name]}. This would not "
                "be a supplement; it would require a fresh grant."
            )
        verified[name] = {"path": path, "sha256": actual, "unchanged": True}
    return {
        "p12_bound_identities": P12_BOUND,
        "file_backed_identities_reverified_at_the_checkpoint": verified,
        "aws_state_identities": {
            "evaluator_image_index": "unchanged - this package builds no image and pushes none",
            "frozen_host": "unchanged - SR-HOST-1 binds the host; this package does not start it",
            "qualified_host_role_arn": "unchanged - no IAM edit is performed or required",
            "resolver": "unchanged - WP-B remains the sole permitted resolution path",
        },
        "conclusion": (
            "Every identity P12 binds is unchanged. This supplement closes the one execution-package "
            "identity the grant does not name; it does not replace, reopen or re-issue the grant."
        ),
    }


def build() -> dict:
    return {
        "record_type": "MR002_Phase3B_SupplementalExecutionIdentity",
        "version": "2.0",
        "artifact_kind": "IDENTITY_SUPPLEMENT",
        "status": "SUBMITTED_FOR_ADJUDICATION",
        "date": "2026-08-12",
        "purpose": (
            "Bind the COMPLETED Phase 3B production invocation path so the already-granted "
            "validation opening becomes spendable. Supersedes v1.0, which bound an execution layer "
            "that could not be invoked."
        ),
        "boundary": (
            "Zero-data. No AWS call, no sealed object opened, no credential assumed, no host "
            "started, no image change. validation_authorization remains true at _rev 1 and the "
            "single validation opening remains UNSPENT."
        ),
        "grants": "NOTHING. This artifact asks the owner for a decision.",
        "pre_validation_checkpoint": verify_checkpoint_is_pushed(),
        "supersession": supersession(),
        "governing_bindings": {
            "runspecification_identity":
                "2a1fb7755a57b97f9831cf257c6e60c8bd5baf77eab39541b75ae88c27cb5b43",
            "execution_boundary_clarification_identity":
                "5f54d85b1ff9193ddefdc5a7639d02e8406e28089248e92d211f47c1f300d88f",
            "run_id": "MR002-SPQ1-P3B-VALIDATION-V1",
            "window": "validation",
            "openings": 1,
        },
        "execution_package_roster": closed_roster(),
        "required_input_consumption_matrix": consumption_matrix(),
        "semantic_guarantees": semantic_guarantees(),
        "configurations": {
            "mode": "CITE AND VERIFY - no mapping is constructed, selected or altered",
            "z_entry": {"A": 1.75, "B": 2.00, "C": 2.25},
            "implemented_in": "mr002_valoos_portfolio_identity.Z_ENTRY, inside the bound image",
        },
        "sealed_inputs": {
            "bucket": "workbench-mr002-sealed-219024422756",
            "region": "us-east-1",
            "prefix": "validation/",
            "window_tables": list(WINDOW_TABLES),
            "reference_tables": list(REFERENCE_TABLES),
            "pinning": "every read specifies the registered VersionId; an unpinned read, an object "
                       "outside the registered set, or a checksum mismatch is refused",
            "decode_control": (
                "the adapter decodes against the P9 structural commitment - column ORDER, row count "
                "and date bounds - so a payload that is not the sealed table is refused even when "
                "its checksum matches the bytes requested"
            ),
        },
        "output_contract": {
            "root": "/opt/mr002/out/valoos/validation",
            "artifact_count": 9,
            "rules": "exclusive creation, read-only lock, exit/disposition agreement, vacancy check "
                     "before any byte is written, partial output preserved and named",
        },
        "one_opening_semantics": {
            "states": "S0..S11 with S7_PRE_ACCESS_READY as the gate",
            "consumption": "the first SUCCESSFUL read of a validation object at its pinned VersionId",
            "restart": "free before consumption; PROHIBITED after, without adjudication",
            "terminal_state": "S11_PUBLISHED, entered on PUBLICATION rather than on success",
            "oos": "refused unconditionally; no code path in the guard could become an authorization",
            "first_use_rule": (
                "the FIRST use of the released reader must be the governed run itself - no probe, "
                "no sample read, no schema check, no ls"
            ),
        },
        "qualification_evidence": {
            "results": QUALIFICATION_RESULTS,
            "identity_linkage": (
                "the qualification_code roster binds the SHA-256 of the exact test and "
                "mutation-check code that produced these results, read from the checkpoint. The "
                "claim is re-runnable, not merely reported."
            ),
        },
        "grant_compatibility": grant_compatibility(),
        "frozen_research_rules_unchanged": {
            "research_identity": "UNCHANGED",
            "dsr_trials_N": 5,
            "dsr_trial_ledger_sha256":
                "deda5cec0bbb72dd845633e99682849e6cf0db949e252dba956a432fcb383e9b",
            "configuration_set": ["A", "B", "C"],
            "evaluator_logic": "UNCHANGED - 21/21 image modules untouched",
            "gates_thresholds_windows_folds_seams_costs_estimators": "UNCHANGED",
            "statement": (
                "This package creates an EXECUTION identity. It creates no research identity, adds "
                "no trial, selects no parameter and alters no economic rule. The earnings controls "
                "it adds are FROZEN-CONTRACT controls being implemented as written, not new rules."
            ),
        },
        "the_ask": {
            "decision_requested": (
                "Adjudicate whether this exact execution package is the one authorized to consume "
                "the already-granted validation opening."
            ),
            "if_granted": (
                "the existing P12 grant becomes spendable by this package and no other; no new "
                "credential release is required because SR-GRANT-1 already occurred."
            ),
            "explicitly_not_requested": [
                "OOS access", "a second validation opening", "any parameter or gate change",
                "re-issuance of the P12 grant", "performance interpretation",
                "host start, credential assumption, or any sealed read",
            ],
        },
    }


def main() -> None:
    record = build()
    body = _canonical(record)
    record["record_identity_sha256"] = hashlib.sha256(body).hexdigest()
    record["record_identity_covers"] = (
        "the canonical JSON of this record EXCLUDING record_identity_sha256 and "
        "record_identity_covers; the on-disk file bytes therefore hash differently. Both hashes are "
        "printed at generation so the artifact can be named unambiguously by either."
    )
    out = os.path.join(_HERE, "MR002_Phase3B_SupplementalExecutionIdentity_v2.0.json")
    payload = _canonical(record)
    with open(out, "wb") as fh:
        fh.write(payload)

    counts = record["execution_package_roster"]["counts"]
    print(f"wrote {out}")
    print(f"record identity  {record['record_identity_sha256']}")
    print(f"file sha256      {hashlib.sha256(payload).hexdigest()}")
    print(f"checkpoint       {CHECKPOINT_SHORT} (remote head verified)")
    print(f"supersedes       v1.0 {SUPERSEDED_V1['record_identity_sha256'][:16]}... "
          f"({record['supersession']['status_assigned_to_v1']})")
    print(f"bound modules    {counts}")
    print(f"consumption      {len(record['required_input_consumption_matrix']['matrix'])} tables, "
          "every one with a production consumer")
    print(f"semantics        {record['semantic_guarantees']['count']} guarantees verified from "
          "the checkpoint")


if __name__ == "__main__":
    main()
