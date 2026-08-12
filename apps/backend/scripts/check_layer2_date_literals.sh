#!/usr/bin/env bash
# Layer 2 — no ungoverned date literal in the governed construction toolchain.
#
# Thin entrypoint over the AST-based checker (scripts/check_layer2_date_literals.py). AST, not grep,
# so a literal is caught whatever shape it takes — bare assignment, tuple, list, dict value,
# `date(...)` call, argument default, inline comparison — and a date named in a docstring is not a
# false positive. PR #589 generalized the session constants a scalar-assignment sweep could see; the
# tuple-bound `DECISION_WINDOW` survived it, which is why this checks the parsed tree instead.
#
# The failure it prevents: a construction that silently uses the previous session's date produces a
# corpus, manifest, attestation and readiness receipt that all agree with one another and are all
# wrong together. Every digest is computed over internally consistent inputs, so no hash catches it.
#
# A date that is a genuine historical contract fact — a property of an adjudicated ruling or an
# external dataset, which does not move when the corpus moves — is registered by exact value in
# REGISTERED_HISTORICAL_CONSTANTS in the checker, with a reason.
#
# Disabling this requires an ADR.
set -euo pipefail
cd "$(dirname "$0")/.."  # apps/backend
python3 scripts/check_layer2_date_literals.py
