#!/usr/bin/env bash
# Auto-reconcile stuck-SUBMITTED orders on the always-on paper box (ADR 0032 ops).
# When a trade-updates stream gap drops a fill/cancel event, the local order stays
# SUBMITTED though the broker finished it (position stays correct via REST sync). This
# feeds the canonical reconcile script into the backend container to re-apply the missed
# outcome through TradeUpdateConsumer._handle. Idempotent; read-only against the broker
# (get_order only — never submits/cancels). Runs on a timer so the ledger self-heals
# without an operator present.
set -uo pipefail

DOCKER="docker"; command -v docker >/dev/null 2>&1 || DOCKER="sudo docker"
SCRIPT="/opt/workbench/app/scripts/reconcile_stuck_orders.py"
[ -f "$SCRIPT" ] || { echo "reconcile script missing: $SCRIPT"; exit 1; }

# --apply writes the reconciliations; a no-op (0 stuck orders) exits cleanly and cheaply.
$DOCKER exec -i workbench-backend python - --apply < "$SCRIPT"
