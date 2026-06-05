#!/bin/bash
# check_llm_optin_bypass_gated.sh
#
# CI invariant #13: the P6b §5 live LLM bypass can only fire behind the DB flag.
#
# §5 adds the ONLY sanctioned LLM-in-order-path: an opted-in user's LIVE strategy
# routes its orders through an LLM act/skip gate (ADR 0006 v2 §5). The bypass of
# invariant #11 is NOT a code allowance — it is an `active` llm_opt_in row, a
# version match, and a per-user daily cap. ADR 0006 v2 line 107: "the bypass
# cannot be granted by code change; it requires a database write." This invariant
# makes that property CI-enforced — the live gate must consult the DB flag before
# it can call the LLM or suppress an order.
#
# Four load-bearing facts about app/services/llm_live_gate/gate.py:
#   1. it looks up the active opt-in (find_active_opt_in) — the LLM is never
#      called without it;
#   2. it pins the strategy version (strategy_version) — a param tweak invalidates
#      the opt-in;
#   3. it enforces the per-user daily cap (daily_cap_cents);
#   4. its fail-safe direction is the DETERMINISTIC baseline (it falls back to
#      real_submit when the opt-in is absent / over budget / no key / errors),
#      never a fresh live order the strategy didn't ask for.
#
# Removing or weakening this invariant requires a successor ADR.

set -e

GATE="apps/backend/app/services/llm_live_gate/gate.py"

fail() {
    echo "ERROR: LLM-opt-in bypass-gating invariant violated."
    echo ""
    echo -e "$1"
    echo ""
    echo "The live LLM gate must be gated by the llm_opt_in DB flag (ADR 0006 v2 §5):"
    echo "  docs/adr/0006-llm-in-order-path-gated.md"
    exit 1
}

if [ ! -f "$GATE" ]; then
    fail "$GATE is missing — the live gate must live in the allowlisted module."
fi

# 1. The active-opt-in lookup is the gate on the bypass.
if ! grep -qE 'find_active_opt_in' "$GATE"; then
    fail "$GATE no longer consults find_active_opt_in.\nThe LLM must never be called without an active opt-in."
fi

# 2. The version pin (a param tweak must invalidate the opt-in).
if ! grep -qE 'strategy_version' "$GATE"; then
    fail "$GATE no longer references strategy_version.\nThe opt-in must be pinned to the strategy version."
fi

# 3. The per-user daily cap.
if ! grep -qE 'daily_cap_cents' "$GATE"; then
    fail "$GATE no longer enforces daily_cap_cents.\nThe per-user budget cap is required (ADR line 100)."
fi

# 4. The fail-safe path submits the deterministic baseline (real_submit), so an
#    absent/over-budget/no-key/errored opt-in falls back to the strategy's own
#    order rather than firing or fabricating one.
if ! grep -qE 'return await real_submit\(order_request\)' "$GATE"; then
    fail "$GATE no longer falls back to real_submit (the deterministic baseline) on\nthe opt-in-absent / over-budget / no-key / error paths."
fi

echo "LLM-opt-in bypass-gating invariant OK"
exit 0
