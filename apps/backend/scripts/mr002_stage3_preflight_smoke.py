"""MR-002 Stage-3 — preflight-only SMOKE tool (qualification tooling, Option 1).

Authorized by the v1.6 review verdict as an ADDITIVE test-only script, comparable to the
final-test-report tooling: it proves the FULL registered preflight passes inside the
pinned container against the real numerical checkout WITHOUT touching the population
path. It composes ONLY frozen registered functions:

  1. `load_authorization` (frozen loader) — the countersigned execution authorization,
     from MR002_EXECUTION_COUNTERSIGN(+_SHA256);
  2. `load_expected_pins` (frozen loader) — the REAL countersigned pins, hash-bound via
     the authorization (no operator-supplied expected values exist anywhere here);
  3. the registered source manifest (MR002_SOURCE_MANIFEST), parsed as the runner does;
  4. the registered `run_preflight(pins, manifest)` — verify_source + gather_env +
     evaluate, the exact composition `run_clean_successor` executes;
  5. prints the COMPLETE preflight summary; exits 0 only when EVERY check passes.

It must not and does not: invoke population resolution, open or iterate the corpus DB,
call the cascade, create any output, change any registered module, or become a production
command — the launcher's registered-command grammar continues to permit ONLY
`python scripts/mr002_stage3_population_runner.py` (enforced by test). Composition is
pinned by `test_smoke_tool_composition_static`.
"""
from __future__ import annotations

import json
import os
import sys


def main() -> int:
    from scripts.mr002_stage3_population_runner import load_authorization, load_expected_pins
    from scripts.mr002_stage3_preflight import run_preflight
    auth = load_authorization(os.environ["MR002_EXECUTION_COUNTERSIGN"],
                              os.environ["MR002_EXECUTION_COUNTERSIGN_SHA256"])
    pins = load_expected_pins(os.environ["MR002_EXPECTED_PINS"], auth["expected_pins_sha256"])
    with open(os.environ["MR002_SOURCE_MANIFEST"], encoding="utf-8") as fh:
        manifest = json.load(fh)
    rep = run_preflight(pins, manifest)
    print(json.dumps(rep.summary(), indent=2))
    return 0 if rep.passed else 1


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
