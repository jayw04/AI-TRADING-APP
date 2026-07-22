#!/usr/bin/env bash
# ADR 0043 — the settlement-barrier structural invariant for governed harnesses.
#
# Thin entrypoint over the AST-based checker (scripts/check_settlement_barrier.py). AST, not grep,
# so a submit inside a multi-line call or behind an alias is still caught and a mention in a
# docstring is not a false positive.
#
# Proves an ADR-0043 harness cannot express "submit without settling": orders go through the one
# GovernedSubmitter seam, which pairs the submit with the shared per-order REST barrier. Phase 0
# lost two live attempts to exactly that gap. Disabling this requires an ADR.
set -euo pipefail
cd "$(dirname "$0")/.."  # apps/backend
python3 scripts/check_settlement_barrier.py
