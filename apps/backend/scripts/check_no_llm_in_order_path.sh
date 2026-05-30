#!/bin/bash
# check_no_llm_in_order_path.sh
#
# CI invariant #11: no LLM calls in the order path.
#
# The order path — defined as OrderRouter, the risk engine, broker
# adapters, and strategy execution code — must not import or call the
# Anthropic SDK. LLM-driven decisions belong upstream (user-initiated
# B1/B2 chat) or downstream (scheduled advisory reports), never in the
# path from "order proposed" to "order sent to broker."
#
# Architecture: this is an ALLOWLIST, not a denylist. Modules are
# presumed to be in the order path unless they appear in ALLOWED_DIRS
# (where LLM calls are explicitly OK). New modules that need LLM access
# must add themselves to the allowlist, which surfaces the decision in
# code review.
#
# This invariant keeps Architecture 3 (Claude in the per-order decision) out
# of the DEFAULT product configuration. Per ADR 0006 v2
# (docs/adr/0006-llm-in-order-path-gated.md, supersedes the v1
# docs/adr/0006-llm-not-in-order-path.md), a gated opt-in — paper-trading
# evaluation harness + 7-day cooldown + typed acknowledgment — may permit
# LLM-driven decisions for a specific user and strategy; when that path ships
# (P6) it gets its own ALLOWED_DIRS entry. The default order path stays clean.
# Removing or weakening this invariant requires a successor ADR.

set -e

ROOT="apps/backend/app"

# Patterns that indicate LLM library use. Catches direct SDK imports
# and the common alias.
PATTERNS=(
    "from anthropic"
    "import anthropic"
    "AsyncAnthropic"
    "Anthropic\("
)

# Allowlist of directories permitted to use LLM libraries.
# IMPORTANT: keep this list MINIMAL. Adding to it requires an ADR
# or at minimum a comment explaining why this directory needs LLM access.
ALLOWED_DIRS=(
    "${ROOT}/agent"                          # B1/B2 user-initiated chat (P3)
    "${ROOT}/services/morning_brief.py"      # Scheduled advisory narration (P5.5 §2)
    "${ROOT}/services/strategy_review.py"    # Periodic advisory reports (P6, future)
    "${ROOT}/services/drift_detection.py"    # Periodic advisory reports (P6, future)
    # (P6) ADR 0006 v2 evaluation harness + opt-in path add their entries here
    #      when that gated capability ships.
)

# Build the find-prune expression dynamically. For each allowed path,
# add a `-not -path` clause.
FIND_PRUNE_ARGS=()
for allowed in "${ALLOWED_DIRS[@]}"; do
    FIND_PRUNE_ARGS+=(-not -path "${allowed}*")
done

# Search for any forbidden pattern in any non-allowlisted .py file.
VIOLATIONS=""
for pattern in "${PATTERNS[@]}"; do
    found=$(find "$ROOT" -name "*.py" \
        "${FIND_PRUNE_ARGS[@]}" \
        -exec grep -lE "$pattern" {} \; 2>/dev/null || true)
    if [ -n "$found" ]; then
        for file in $found; do
            # Get the line numbers for the violation
            matches=$(grep -nE "$pattern" "$file" 2>/dev/null || true)
            if [ -n "$matches" ]; then
                VIOLATIONS+="$file:\n$matches\n\n"
            fi
        done
    fi
done

if [ -n "$VIOLATIONS" ]; then
    echo "ERROR: LLM library use detected in the order path."
    echo ""
    echo -e "$VIOLATIONS"
    echo "The order path must not call LLM APIs by default. See ADR 0006 v2:"
    echo "  docs/adr/0006-llm-in-order-path-gated.md"
    echo ""
    echo "If you genuinely need LLM access in a new module, you must:"
    echo "  1. Confirm the module is advisory (user-initiated or scheduled),"
    echo "     not in the order-submission path."
    echo "  2. Add the module path to ALLOWED_DIRS in this script."
    echo "  3. Note in your PR description why the addition is justified."
    echo ""
    echo "If the addition would put LLM calls in the default order path, the"
    echo "answer is no — Architecture 3 is gated behind ADR 0006 v2's opt-in."
    exit 1
fi

echo "No-LLM-in-order-path invariant OK"
exit 0
