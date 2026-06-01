#!/bin/bash
# check_audit_immutability.sh
#
# P5 §8 invariant (the ninth quality gate; sixth shell invariant): no production
# code path may mutate or delete audit_log rows, or drop its append-only
# triggers. The DB triggers (audit_log_no_update / audit_log_no_delete) enforce
# this at the storage layer; this grep catches the application-layer attempts
# between PRs.
#
# Allowed locations (outside $ROOT, so already excluded):
#   - alembic/versions/  — the migration that creates the columns + triggers.
#   - tests/             — fixtures may construct throwaway schemas.
#
# Mirrors check_no_env_credentials.sh + check_broker_isolation.sh in shape.

set -e

ROOT="apps/backend/app"

# Forbidden in production code: direct UPDATE/DELETE of audit_log, or dropping
# its triggers. (The model's before_insert SELECT and the CREATE TRIGGER DDL
# do not match these — "UPDATE ON" / "DELETE ON" / "... FROM audit_log" in a
# SELECT are distinct from "UPDATE audit_log" / "DELETE FROM audit_log".)
PATTERN="UPDATE[[:space:]]+audit_log|DELETE[[:space:]]+FROM[[:space:]]+audit_log|DROP[[:space:]]+TRIGGER[[:space:]].*audit_log"

VIOLATIONS=$(find "$ROOT" -name "*.py" \
  -exec grep -lEi "$PATTERN" {} \; 2>/dev/null || true)

if [ -n "$VIOLATIONS" ]; then
    echo "ERROR: production code mutates/deletes audit_log or drops its triggers."
    echo ""
    for f in $VIOLATIONS; do
        echo "  $f:"
        grep -nEi "$PATTERN" "$f" | sed 's/^/    /'
    done
    echo ""
    echo "audit_log is append-only. Add rows via AuditLogger.write(); never"
    echo "UPDATE/DELETE. A genuine one-off cleanup belongs in alembic/versions/"
    echo "with an ADR explaining why."
    exit 1
fi

echo "Audit immutability invariant OK"
exit 0
