#!/usr/bin/env bash
# Research-plane → order-path isolation (ADR 0051 Decision 3 / Phase 1A).
#
# Generalizes check_altdata_order_path_isolation.sh to the whole research plane:
# app/research/**, app/factor_data/**, app/altdata/** (and future rank/pcs/env under
# research/) MUST NOT import OrderRouter, the risk engine, or broker adapters, and
# MUST NOT reference ROUTER_TOKEN.
#
# Same shape as check_strategy_isolation.sh / check_altdata_order_path_isolation.sh.
# Disabling this requires an ADR. Prefer running against a clean checkout
# (CI always does; locally stash or commit first — ADR 0051 Decision 7).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

IMPORT_PATTERN='(from|import)[[:space:]]+app\.(orders|services\.order_router|risk|brokers)([.[:space:]]|$)'
TOKEN_PATTERN='ROUTER_TOKEN'

SEARCH_PATHS=(
  "apps/backend/app/research"
  "apps/backend/app/factor_data"
  "apps/backend/app/altdata"
)

OFFENDERS=""
for p in "${SEARCH_PATHS[@]}"; do
  [[ -e "$p" ]] || continue
  HIT=$(grep -rEn "$IMPORT_PATTERN" "$p" --include='*.py' || true)
  [[ -n "$HIT" ]] && OFFENDERS+="$HIT"$'\n'
  HIT=$(grep -rEn "$TOKEN_PATTERN" "$p" --include='*.py' || true)
  [[ -n "$HIT" ]] && OFFENDERS+="$HIT"$'\n'
done

if [[ -n "${OFFENDERS//[$'\n']/}" ]]; then
  echo "RESEARCH-PLANE ORDER-PATH ISOLATION VIOLATION — research-plane code imports" >&2
  echo "the order path or holds ROUTER_TOKEN (ADR 0051):" >&2
  echo "$OFFENDERS" >&2
  echo "" >&2
  echo "Research-plane packages produce governed artifacts only. They hold no execution" >&2
  echo "authority. Order path = app.orders / app.services.order_router / app.risk /" >&2
  echo "app.brokers. Crossing into execution requires a pinned human promotion (ADR 0051)." >&2
  exit 1
fi
echo "Research-plane order-path isolation OK"
