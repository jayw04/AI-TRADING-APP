#!/usr/bin/env bash
# MKT-PROJ-001 order-path isolation tripwire (NFR-001; ModelCard v1.0 owner decision).
#
# Market Projection is DISPLAY-ONLY decision support. Two structural assertions:
#   A. Nothing in app/services/market_projection (or its jobs/API) imports the
#      OrderRouter, risk engine, broker adapters, or strategy machinery.
#   B. No order-path / ranking / sizing / strategy module imports market_projection —
#      the projection can never feed ranking, sizing, portfolio construction, or
#      orders until a separate MKT-PROJ-STRAT-001 program exists.
#
# Same shape as check_altdata_order_path_isolation.sh. Disabling this requires an ADR.
set -euo pipefail

# --- A: projection modules must not reach the order path -------------------------
A_PATTERN='(from|import)[[:space:]]+app\.(services\.order_router|risk|brokers\.alpaca\.adapter|strategies)([.[:space:]]|$)'
A_PATHS=(
  "apps/backend/app/services/market_projection"
  "apps/backend/app/jobs/market_projection_jobs.py"
  "apps/backend/app/api/v1/market_projection.py"
)
OFFENDERS=""
for p in "${A_PATHS[@]}"; do
  [[ -e "$p" ]] || continue
  HIT=$(grep -rEn "$A_PATTERN" "$p" --include='*.py' || true)
  [[ -n "$HIT" ]] && OFFENDERS+="$HIT"$'\n'
done

# --- B: the order path must not consume the projection ----------------------------
B_PATTERN='(from|import)[[:space:]]+app\.services\.market_projection'
B_PATHS=(
  "apps/backend/app/services/order_router.py"
  "apps/backend/app/risk"
  "apps/backend/app/brokers"
  "apps/backend/app/strategies"
  "apps/backend/app/orders"
  "apps/backend/app/factor_data"
)
for p in "${B_PATHS[@]}"; do
  [[ -e "$p" ]] || continue
  HIT=$(grep -rEn "$B_PATTERN" "$p" --include='*.py' || true)
  [[ -n "$HIT" ]] && OFFENDERS+="$HIT"$'\n'
done

if [[ -n "${OFFENDERS//[$'\n']/}" ]]; then
  echo "MARKET-PROJECTION ISOLATION VIOLATION (NFR-001):"
  echo "$OFFENDERS"
  exit 1
fi
echo "market-projection isolation invariant: OK"
