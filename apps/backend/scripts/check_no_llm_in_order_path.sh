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
# This invariant exists to keep Architecture 3 (Claude in the per-order
# decision) deliberately out of scope. See docs/adr/0006-llm-not-in-order-path.md
# for the full reasoning. Removing or weakening this invariant requires
# a successor ADR.

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
    echo "The order path must not call LLM APIs. See ADR 0006:"
    echo "  docs/adr/0006-llm-not-in-order-path.md"
    echo ""
    echo "If you genuinely need LLM access in a new module, you must:"
    echo "  1. Confirm the module is advisory (user-initiated or scheduled),"
    echo "     not in the order-submission path."
    echo "  2. Add the module path to ALLOWED_DIRS in this script."
    echo "  3. Note in your PR description why the addition is justified."
    echo ""
    echo "If the addition would put LLM calls in the order path, the answer"
    echo "is no — that's Architecture 3, which is paused per ADR 0006."
    exit 1
fi

echo "No-LLM-in-order-path invariant OK"
exit 0
