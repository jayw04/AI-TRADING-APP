#!/usr/bin/env python3
"""Required-test verifier for the RANGE-002 Linux acceptance step (stdlib only).

A green `pytest` job cannot show WHETHER a particular test executed: a skipped test, a test that was
never collected (file absent, renamed, deselected) and a passing test all leave the job green. The
RANGE-002 Level 1 acceptance plan needs the opposite guarantee for a named set of tests (the
symlink/hardlink alias tests and the POSIX fcntl / multi-process locking tests): each must have been
collected AND PASSED on Linux. This script reads the JUnit XML pytest wrote and a manifest of required
pytest node ids and fails unless every required test in the enabled set passed.

Statuses per required test:
    PASSED   present in the XML, no failure / error / skipped child.
    FAILED   present, has a <failure>.
    ERROR    present, has an <error> (setup/teardown/collection error).
    SKIPPED  present, has a <skipped> child (this includes xfail: an xfail is not a pass).
    MISSING  not present in the XML (not collected, deselected, renamed, or its file is absent).
    DUPLICATE the id appears more than once in the XML (ambiguous evidence; fails closed).
    PENDING  manifest entry marked `"pending_pr": "<n>"` whose test file is absent from the checkout.
             PENDING is NEVER a pass. See --allow-pending.

Exit codes:
    0  every enabled required test PASSED (and, without --allow-pending, none is PENDING)
    0  with --allow-pending: every non-PENDING test PASSED; PENDING entries are reported, not failed
    1  at least one required test is FAILED / ERROR / SKIPPED / MISSING / DUPLICATE
    2  usage error, unreadable / malformed / empty JUnit XML, or invalid manifest
    3  no failures, but at least one PENDING entry and --allow-pending was NOT given
       (acceptance mode: non-zero, because the evidence is incomplete)

There is deliberately NO flag that ignores a required test whose file is absent. The only softening is
the explicit, per-entry `pending_pr` marker in the committed manifest plus the explicit CLI flag.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

PASSED = "PASSED"
FAILED = "FAILED"
ERROR = "ERROR"
SKIPPED = "SKIPPED"
MISSING = "MISSING"
DUPLICATE = "DUPLICATE"
PENDING = "PENDING"

# Worst-first ordering when several outcomes are recorded for one id.
_SEVERITY = (ERROR, FAILED, SKIPPED, PASSED)

VALID_PHASES = ("pr2", "pr3")

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_PENDING = 3


class VerifierError(Exception):
    """Unusable input (manifest or XML). Maps to exit code 2; never treated as 'nothing to check'."""


@dataclass(frozen=True)
class Required:
    node_id: str
    phase: str
    pending_pr: str | None


@dataclass(frozen=True)
class Result:
    node_id: str
    phase: str
    status: str
    detail: str = ""


def node_id_to_junit_key(node_id: str) -> tuple[str, str]:
    """Map a pytest node id to the (classname, name) pair pytest's xunit2 JUnit writer emits.

    `tests/a/b.py::Cls::test_x[p]` -> (`tests.a.b.Cls`, `test_x[p]`). The parametrize suffix (which
    may itself contain `/` or `::`) stays inside `name`.
    """
    bracket = node_id.find("[")
    head, params = (node_id, "") if bracket == -1 else (node_id[:bracket], node_id[bracket:])
    parts = head.split("::")
    if len(parts) < 2 or not parts[0].endswith(".py") or not all(parts):
        raise VerifierError(f"not a pytest node id (expected 'path.py::test'): {node_id!r}")
    module = parts[0][: -len(".py")].replace("\\", "/").strip("/").replace("/", ".")
    classname = ".".join([module, *parts[1:-1]])
    return classname, parts[-1] + params


def node_id_file(node_id: str) -> str:
    return node_id.split("::", 1)[0]


def load_manifest(path: Path) -> list[Required]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerifierError(f"cannot read manifest {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("tests"), list) or not data["tests"]:
        raise VerifierError("manifest must be an object with a non-empty 'tests' array")
    out: list[Required] = []
    seen: set[str] = set()
    for i, raw in enumerate(data["tests"]):
        if not isinstance(raw, dict):
            raise VerifierError(f"manifest tests[{i}] is not an object")
        nid, phase, pending = raw.get("id"), raw.get("phase"), raw.get("pending_pr")
        if not isinstance(nid, str) or not nid:
            raise VerifierError(f"manifest tests[{i}] has no 'id'")
        node_id_to_junit_key(nid)  # validates shape
        if phase not in VALID_PHASES:
            raise VerifierError(f"{nid}: phase must be one of {VALID_PHASES}, got {phase!r}")
        if pending is not None and (not isinstance(pending, str) or not pending):
            raise VerifierError(f"{nid}: 'pending_pr' must be a non-empty string when present")
        if nid in seen:
            raise VerifierError(f"duplicate id in manifest: {nid}")
        seen.add(nid)
        out.append(Required(nid, phase, pending))
    return out


def parse_junit(path: Path) -> dict[tuple[str, str], list[tuple[str, str]]]:
    """Return {(classname, name): [(status, detail), ...]} for every <testcase>.

    Raises VerifierError for unreadable, malformed, empty (no testcases) or non-JUnit XML: an empty
    report must never be mistaken for 'nothing required ran, so nothing failed'.
    """
    try:
        root = ET.parse(path).getroot()  # noqa: S314 - CI-produced file, stdlib parser
    except (OSError, ET.ParseError) as exc:
        raise VerifierError(f"cannot parse JUnit XML {path}: {exc}") from exc
    if root.tag not in ("testsuites", "testsuite"):
        raise VerifierError(f"{path}: root element <{root.tag}> is not JUnit")
    cases = list(root.iter("testcase"))
    if not cases:
        raise VerifierError(f"{path}: JUnit XML contains no <testcase> elements (empty run)")
    seen: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for tc in cases:
        key = (tc.get("classname", ""), tc.get("name", ""))
        status, detail = PASSED, ""
        for child in tc:
            if child.tag == "error":
                status, detail = ERROR, (child.get("message") or "")[:160]
                break
            if child.tag == "failure":
                status, detail = FAILED, (child.get("message") or "")[:160]
                break
            if child.tag == "skipped":
                status, detail = SKIPPED, (child.get("message") or "")[:160]
                # keep scanning: an <error> sibling would be worse
        seen.setdefault(key, []).append((status, detail))
    return seen


def evaluate(
    required: list[Required],
    observed: dict[tuple[str, str], list[tuple[str, str]]],
    root: Path,
    phases: tuple[str, ...],
) -> list[Result]:
    results: list[Result] = []
    for req in required:
        if req.phase not in phases:
            continue
        file_present = (root / node_id_file(req.node_id)).is_file()
        key = node_id_to_junit_key(req.node_id)
        outcomes = observed.get(key)
        if outcomes is None:
            if not file_present and req.pending_pr is not None:
                results.append(
                    Result(
                        req.node_id,
                        req.phase,
                        PENDING,
                        f"test file absent; marked pending_pr={req.pending_pr}",
                    )
                )
            elif not file_present:
                results.append(Result(req.node_id, req.phase, MISSING, "test file absent"))
            else:
                results.append(
                    Result(req.node_id, req.phase, MISSING, "not in JUnit XML (not collected?)")
                )
            continue
        if len(outcomes) > 1:
            statuses = ",".join(s for s, _ in outcomes)
            results.append(
                Result(req.node_id, req.phase, DUPLICATE, f"{len(outcomes)} records: {statuses}")
            )
            continue
        status, detail = outcomes[0]
        results.append(Result(req.node_id, req.phase, status, detail))
    return results


def render_table(results: list[Result]) -> str:
    counts = {s: 0 for s in (PASSED, FAILED, ERROR, SKIPPED, MISSING, DUPLICATE, PENDING)}
    for r in results:
        counts[r.status] += 1
    width = max((len(r.node_id) for r in results), default=10)
    lines = [f"{'STATUS':<9} {'PHASE':<5} {'TEST':<{width}}  DETAIL", "-" * (18 + width + 8)]
    for r in results:
        lines.append(f"{r.status:<9} {r.phase:<5} {r.node_id:<{width}}  {r.detail}".rstrip())
    lines.append("-" * (18 + width + 8))
    collected = sum(counts[s] for s in (PASSED, FAILED, ERROR, SKIPPED, DUPLICATE))
    lines.append(
        f"required={len(results)} collected={collected} passed={counts[PASSED]} "
        f"failed={counts[FAILED]} errored={counts[ERROR]} skipped={counts[SKIPPED]} "
        f"missing={counts[MISSING]} duplicate={counts[DUPLICATE]} pending={counts[PENDING]}"
    )
    return "\n".join(lines)


def decide_exit(results: list[Result], allow_pending: bool) -> int:
    if any(r.status not in (PASSED, PENDING) for r in results):
        return EXIT_FAIL
    if any(r.status == PENDING for r in results) and not allow_pending:
        return EXIT_PENDING
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--junit", required=True, type=Path, help="JUnit XML written by pytest")
    p.add_argument("--manifest", required=True, type=Path, help="required-tests manifest (JSON)")
    p.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="directory the manifest's node-id paths are relative to (pytest rootdir; default .)",
    )
    p.add_argument(
        "--phases",
        default=",".join(VALID_PHASES),
        help="comma-separated enabled phases (default: pr2,pr3)",
    )
    p.add_argument(
        "--allow-pending",
        action="store_true",
        help="PENDING entries (pending_pr set AND file absent) do not fail the run (gate mode). "
        "Without it a PENDING entry exits 3 (acceptance mode). PENDING is never reported as PASSED.",
    )
    p.add_argument("--table-out", type=Path, help="also write the table to this file")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        phases = tuple(x.strip() for x in args.phases.split(",") if x.strip())
        bad = [x for x in phases if x not in VALID_PHASES]
        if not phases or bad:
            raise VerifierError(f"--phases must be a subset of {VALID_PHASES}, got {args.phases!r}")
        required = load_manifest(args.manifest)
        observed = parse_junit(args.junit)
        results = evaluate(required, observed, args.root, phases)
        if not results:
            raise VerifierError("enabled phases select no required tests")
    except VerifierError as exc:
        print(f"ci_verify_required_tests: {exc}", file=sys.stderr)
        return EXIT_USAGE
    table = render_table(results)
    print(table)
    if args.table_out:
        args.table_out.write_text(table + "\n", encoding="utf-8", newline="\n")
    code = decide_exit(results, args.allow_pending)
    verdict = {
        EXIT_OK: "OK",
        EXIT_FAIL: "FAIL: a required test is not PASSED",
        EXIT_PENDING: "INCOMPLETE: PENDING entries present (acceptance mode)",
    }[code]
    print(f"verdict: {verdict} (exit {code})")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
