#!/usr/bin/env bash
# ADR 0043 PR5 — structural invariants for the loss-control architecture.
#
# Thin entrypoint over the AST-based checker (scripts/check_loss_control_invariants.py) — AST, not
# grep, because the two most important properties (single-persister and gate-only-via-engine) must
# survive aliased imports and multi-line calls and must NOT trip on docstring/comment mentions.
#
# Enforces five properties PR1–PR4 established (see the Python module's docstring). Disabling any of
# them requires an ADR.
set -euo pipefail
cd "$(dirname "$0")/.."  # apps/backend
python3 scripts/check_loss_control_invariants.py
