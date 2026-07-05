#!/usr/bin/env bash
# EAD order-path isolation tripwire (ADR 0037 Decision 11 — the fourteenth CI invariant).
#
# The alternative-data ingestion (Quiver), the Point-in-Time Security Master (CAP-024), and the
# Daily Opportunity Report are RESEARCH-ONLY and must never reach the order path. This asserts
# they import nothing from the OrderRouter / risk engine / broker adapters — structurally, so the
# property holds against the one PR nobody looks closely at (not just reviewer diligence).
#
# Same shape as check_strategy_isolation.sh. Disabling this requires an ADR.
set -euo pipefail

PATTERN='(from|import)[[:space:]]+app\.(services\.order_router|risk|brokers)([.[:space:]]|$)'

SEARCH_PATHS=(
  "apps/backend/app/altdata/quiver"
  "apps/backend/app/altdata/security_master.py"
  "apps/backend/app/services/opportunity_report"   # created in Phase 3; absent paths are skipped
)

OFFENDERS=""
for p in "${SEARCH_PATHS[@]}"; do
  [[ -e "$p" ]] || continue
  HIT=$(grep -rEn "$PATTERN" "$p" --include='*.py' || true)
  [[ -n "$HIT" ]] && OFFENDERS+="$HIT"$'\n'
done

if [[ -n "${OFFENDERS//[$'\n']/}" ]]; then
  echo "EAD ORDER-PATH ISOLATION VIOLATION — research-only alt-data code imports the order path:" >&2
  echo "$OFFENDERS" >&2
  echo "" >&2
  echo "Quiver / Security Master / Opportunity Report are advisory research inputs. They flow" >&2
  echo "Event Store -> evidence -> governance, never directly to OrderRouter/risk/brokers (ADR 0037)." >&2
  exit 1
fi
echo "EAD order-path isolation OK"
