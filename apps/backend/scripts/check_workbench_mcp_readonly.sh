#!/bin/bash
# check_workbench_mcp_readonly.sh
#
# CI invariant #12 (P5.5 §3): the workbench-mcp server only makes read-only
# (GET) calls to the backend. The ONE allowed non-GET is the idempotent
# POST /api/v1/morning-brief/generate (upserts on (user_id, brief_date) —
# doesn't mutate trading state).
#
# Mutating tools are P6 territory (agent autonomy). Adding a non-GET call here
# must be a deliberate, design-reviewed change — add it to ALLOWED_POSTS below
# AND justify it in the PR, or the build fails.
#
# Mechanism: scan apps/mcp-workbench/src for non-GET tool CALL SITES — i.e.
# `_post("…")` / `_put("…")` / `_delete("…")` / `_patch("…")` with a literal
# path string. The `("` after the verb skips the helper *definitions*
# (`async def _post(path, …)`) and the underlying client methods (`c.post(`).
#
# Run from the repo root.

set -e

SEARCH_DIR="apps/mcp-workbench/src"

ALLOWED_POSTS=(
    "/api/v1/morning-brief/generate"
)

if [[ ! -d "$SEARCH_DIR" ]]; then
    echo "ERROR: $SEARCH_DIR not found (run from repo root)" >&2
    exit 2
fi

# Call sites: a non-GET wrapper immediately followed by a quoted literal path.
NON_GET=$(grep -rnE '_(post|put|delete|patch)\("' "$SEARCH_DIR" || true)

VIOLATIONS=""
if [[ -n "$NON_GET" ]]; then
    while IFS= read -r line; do
        allowed=false
        for path in "${ALLOWED_POSTS[@]}"; do
            if echo "$line" | grep -qF "\"$path\""; then
                allowed=true
                break
            fi
        done
        if [[ "$allowed" == false ]]; then
            VIOLATIONS+="$line"$'\n'
        fi
    done <<< "$NON_GET"
fi

if [[ -n "$VIOLATIONS" ]]; then
    echo "ERROR: workbench-mcp makes a non-GET call outside the allowlist:"
    echo ""
    echo "$VIOLATIONS"
    echo "Mutating tools are P6 territory. If this is a new idempotent read-only"
    echo "POST, add its path to ALLOWED_POSTS in this script and justify it in the PR."
    exit 1
fi

echo "workbench-mcp read-only invariant OK"
exit 0
