#!/bin/bash
# check_agent_no_db_access.sh
#
# CI invariant #13 (P6 §1a, Decision 2): the agent process (apps/agent/) does
# NOT access the database directly. It reads via workbench-mcp (SSE) and writes
# via the backend HTTP API — both of which carry audit / risk-gate / cost-
# envelope enforcement. Direct DB access from the agent would route around all
# of that, so it's forbidden by grep here and unit-tested in
# apps/agent/tests/test_no_db_access.py.
#
# Run from the repo root (same posture as check_workbench_mcp_readonly.sh).

set -e

AGENT_DIR="apps/agent/src"

if [[ ! -d "$AGENT_DIR" ]]; then
    echo "ERROR: $AGENT_DIR not found (run from repo root)" >&2
    exit 2
fi

FORBIDDEN_PATTERNS=(
    "from sqlalchemy"
    "import sqlalchemy"
    "from app.db"
    "import app.db"
    "from alembic"
    "import alembic"
)

VIOLATIONS=""
for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
    HITS=$(grep -rnE "^[[:space:]]*${pattern}" "$AGENT_DIR" || true)
    if [[ -n "$HITS" ]]; then
        VIOLATIONS+="${pattern}:"$'\n'"${HITS}"$'\n\n'
    fi
done

if [[ -n "$VIOLATIONS" ]]; then
    echo "ERROR: apps/agent/ imports a forbidden DB-access module:"
    echo ""
    echo "$VIOLATIONS"
    echo "Per Decision 2 of the P6 Decisions doc: the agent reads via"
    echo "workbench-mcp and writes via the backend HTTP API. Direct DB access"
    echo "is not permitted."
    exit 1
fi

echo "agent no-DB-access invariant OK"
exit 0
