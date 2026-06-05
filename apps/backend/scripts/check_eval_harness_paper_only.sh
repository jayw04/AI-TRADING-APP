#!/bin/bash
# check_eval_harness_paper_only.sh
#
# CI invariant #12: the P6b §4 LLM eval harness never routes orders to a
# LIVE account.
#
# ADR 0006 v2 (docs/adr/0006-llm-in-order-path-gated.md) gates LLM-driven
# decisions behind a PAPER-trading evaluation harness. The harness runs two
# clones of the parent strategy — Mode A (deterministic control) and Mode B
# (LLM-gated) — and compares them BEFORE any live opt-in is even offered. If
# either clone could touch a live account, the "evaluate on paper first"
# safety property the entire opt-in rests on would be hollow.
#
# The paper-only guarantee has three load-bearing facts, each checked below:
#
#   1. The harness clones are non-live strategies. start_eval_harness spawns
#      Mode A as PAPER_VARIANT and Mode B as IDLE — never LIVE / PENDING_LIVE.
#      A PAPER_VARIANT resolves to the user's paper account in the engine, so
#      Mode A's OrderRequest.account_id is a paper account.
#
#   2. No code in app/services/eval_harness/ assigns a LIVE or PENDING_LIVE
#      status to anything (which could promote a clone onto the live path).
#
#   3. Mode B inherits Mode A's account. The gate submits Mode B by
#      dataclasses.replace(order_request, source_id=...) — it rewrites ONLY
#      source_id, never account_id. So B trades on the same paper account A
#      does; it cannot construct a fresh order pointed at a live account.
#
# Removing or weakening this invariant requires a successor ADR.

set -e

PKG="apps/backend/app/services/eval_harness"
SERVICE="${PKG}/service.py"
GATE="${PKG}/gate.py"

fail() {
    echo "ERROR: eval-harness paper-only invariant violated."
    echo ""
    echo -e "$1"
    echo ""
    echo "The LLM eval harness must evaluate on PAPER only (ADR 0006 v2):"
    echo "  docs/adr/0006-llm-in-order-path-gated.md"
    exit 1
}

# --- Fact 1: Mode A spawns PAPER_VARIANT, Mode B spawns IDLE. ---------------
if ! grep -qE 'status=StrategyStatus\.PAPER_VARIANT' "$SERVICE"; then
    fail "$SERVICE no longer spawns Mode A as PAPER_VARIANT.\nThe running clone must be a paper strategy, never live."
fi
if ! grep -qE 'status=StrategyStatus\.IDLE' "$SERVICE"; then
    fail "$SERVICE no longer spawns Mode B as IDLE.\nMode B is an IDLE bucket (never registered), not a live/running strategy."
fi

# --- Fact 2: no LIVE / PENDING_LIVE status is ever ASSIGNED in the package.
# Matches `status=StrategyStatus.LIVE`, `.status = StrategyStatus.LIVE`, and the
# PENDING_LIVE variants. Does NOT match read-guards like
# `parent.status != StrategyStatus.LIVE` (that's `!=`, not an assignment).
LIVE_ASSIGN=$(grep -rnE \
    '(status[[:space:]]*=[[:space:]]*StrategyStatus\.(LIVE|PENDING_LIVE)|\.status[[:space:]]*=[[:space:]]*StrategyStatus\.(LIVE|PENDING_LIVE))' \
    "$PKG" 2>/dev/null || true)
if [ -n "$LIVE_ASSIGN" ]; then
    fail "A harness clone is being assigned a LIVE/PENDING_LIVE status:\n$LIVE_ASSIGN"
fi

# --- Fact 3: Mode B reuses Mode A's account (rewrites only source_id). ------
# The single replace() of the order request in the gate must not touch
# account_id (which would re-route the order off the paper account).
if ! grep -qE 'replace\(order_request, source_id=' "$GATE"; then
    fail "$GATE no longer submits Mode B via replace(order_request, source_id=...).\nMode B must inherit Mode A's OrderRequest (and thus its paper account_id)."
fi
ACCOUNT_REWRITE=$(grep -nE 'replace\(order_request[^)]*account_id' "$GATE" 2>/dev/null || true)
if [ -n "$ACCOUNT_REWRITE" ]; then
    fail "$GATE rewrites account_id when building Mode B's order:\n$ACCOUNT_REWRITE\nMode B must keep Mode A's account; only source_id may change."
fi

echo "Eval-harness paper-only invariant OK"
exit 0
