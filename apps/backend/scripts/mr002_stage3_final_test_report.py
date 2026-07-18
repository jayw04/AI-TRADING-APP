"""MR-002 Stage-3 — FINAL in-image test-report generator.

Produces the MR002_STAGE3_TEST_REPORT artifact consumed by `load_final_test_report`
(population runner, cycle-9 blockers 3-4): a per-test result map captured from the ACTUAL
pytest run (never hand-assembled counts), plus the runtime identities the report must
STATE so the loader can require equality with Phase B.

Run INSIDE the pinned image at the qualification commit, e.g.:

    MR002_IMAGE_DIGEST=sha256:... MR002_OCI_CONFIG_DIGEST=sha256:... \
    MR002_SOURCE_MANIFEST=... MR002_EXPECTED_PINS=... MR002_EXECUTION_PACKAGE=... \
    python scripts/mr002_stage3_final_test_report.py --out /out/final_test_report.json \
        -- --noconftest tests/research/test_mr002_stage3_cascade_dispA.py ...

Identity sources: commit/tree/dirty are OBSERVED from git in the container; the image +
OCI digests come from the launcher's environment (a container cannot observe its own
digest); the manifest/pins/package hashes are computed from the referenced file bytes.
`admissible_as_final` is DERIVED (exit 0, zero skips, clean tree, all passed, complete
identities) — never asserted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class ResultCollector:
    """Pytest plugin: one durable (test_id, outcome) record per test, from the real hooks."""

    def __init__(self) -> None:
        self.outcomes: dict[str, str] = {}

    def pytest_runtest_logreport(self, report) -> None:  # noqa: ANN001 - pytest hook
        if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
            # setup failures/skips are the test's outcome; a passed setup defers to call
            self.outcomes[report.nodeid] = report.outcome


def _git(args: list[str]) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True,  # noqa: S607
                          check=True).stdout.strip()


def build_report(*, outcomes: dict[str, str], exit_code: int, identities: dict) -> dict:
    """Pure assembly: every count DERIVED from the per-test map; admissibility derived."""
    test_results = [{"test_id": tid, "outcome": out}
                    for tid, out in sorted(outcomes.items())]
    collected_test_ids = [r["test_id"] for r in test_results]
    collected_passed = sum(1 for r in test_results if r["outcome"] == "passed")
    collected_skipped = sum(1 for r in test_results if r["outcome"] == "skipped")
    from scripts.mr002_stage3_population_runner import PRODUCTION_BINDING_TEST_ID
    pb = outcomes.get(PRODUCTION_BINDING_TEST_ID, "not_collected")
    identity_keys = ("bound_commit", "bound_tree", "image_digest", "oci_config_digest",
                     "source_manifest_sha256", "expected_pins_sha256",
                     "execution_package_sha256")
    admissible = (exit_code == 0 and collected_skipped == 0
                  and identities.get("working_tree_dirty") is False
                  and collected_passed == len(test_results)
                  and pb == "passed"
                  and all(identities.get(k) for k in identity_keys))
    doc = {
        "record_type": "MR002_STAGE3_TEST_REPORT",
        "version": "1.0",
        "record_status": "IMMUTABLE",
        "exit_code": exit_code,
        "collected_test_ids": collected_test_ids,
        "test_results": test_results,
        "collected_passed": collected_passed,
        "collected_skipped": collected_skipped,
        "production_binding_outcome": pb,
        "admissible_as_final": admissible,
    }
    doc.update({k: identities.get(k) for k in (*identity_keys, "working_tree_dirty")})
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("pytest_args", nargs=argparse.REMAINDER,
                    help="arguments after '--' are passed to pytest verbatim")
    args = ap.parse_args()
    pytest_args = [a for a in args.pytest_args if a != "--"]

    import pytest
    collector = ResultCollector()
    exit_code = int(pytest.main(pytest_args, plugins=[collector]))

    identities = {
        "bound_commit": _git(["rev-parse", "HEAD"]),
        "bound_tree": _git(["rev-parse", "HEAD^{tree}"]),
        "working_tree_dirty": bool(_git(["status", "--porcelain"])),
        "image_digest": os.environ.get("MR002_IMAGE_DIGEST", ""),
        "oci_config_digest": os.environ.get("MR002_OCI_CONFIG_DIGEST", ""),
        "source_manifest_sha256": _sha256_file(os.environ["MR002_SOURCE_MANIFEST"]),
        "expected_pins_sha256": _sha256_file(os.environ["MR002_EXPECTED_PINS"]),
        "execution_package_sha256": _sha256_file(os.environ["MR002_EXECUTION_PACKAGE"]),
    }
    doc = build_report(outcomes=collector.outcomes, exit_code=exit_code, identities=identities)
    data = (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode("utf-8")
    tmp = args.out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, args.out)
    print(json.dumps({"report_path": args.out,
                      "report_sha256": hashlib.sha256(data).hexdigest(),
                      "exit_code": exit_code,
                      "admissible_as_final": doc["admissible_as_final"],
                      "collected_passed": doc["collected_passed"],
                      "collected_skipped": doc["collected_skipped"],
                      "production_binding_outcome": doc["production_binding_outcome"]},
                     indent=1))
    # the generator's exit reflects the SUITE result so CI/launchers fail closed
    return exit_code if exit_code != 0 else (0 if doc["admissible_as_final"] else 8)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
