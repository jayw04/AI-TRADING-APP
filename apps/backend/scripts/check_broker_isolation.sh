#!/usr/bin/env bash
# check_broker_isolation.sh
#
# P5 §2 CI invariant: only files under app/brokers/ may import a broker's
# TRADING / ORDER SDK. Everything above the OrderRouter interacts with brokers
# exclusively through the BrokerAdapter Protocol, resolved per-account by
# BrokerRegistry.
#
# Scope (verified against the codebase): this covers the order-routing SDK
# surface only — alpaca.trading / alpaca.broker / alpaca.common, plus other
# brokers' order SDKs (ib_insync, schwab_api). It deliberately EXCLUDES
# alpaca.data.* (historical bars, quotes, live bar stream), which is a separate
# read-only market-data concern that legitimately lives in app/market_data/,
# app/api/v1/market_data.py, and app/services/. A blanket `from alpaca` rule
# would false-flag all of that legitimate market-data code.
#
# Mirrors check_strategy_isolation.sh: the boundary between the trading-system
# core and broker-specific order code is enforced from CI, not just review.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../" && pwd)"
APP_DIR="$ROOT/app"
ALLOWED_DIR="$APP_DIR/brokers"

if [ ! -d "$APP_DIR" ]; then
  echo "No app/ directory; nothing to check."
  exit 0
fi

# Trading/order SDK imports. NOT alpaca.data.*
PATTERNS=(
  'from[[:space:]]+alpaca\.trading'
  'import[[:space:]]+alpaca\.trading'
  'from[[:space:]]+alpaca\.broker'
  'import[[:space:]]+alpaca\.broker'
  'from[[:space:]]+alpaca\.common'
  'import[[:space:]]+alpaca\.common'
  'from[[:space:]]+ib_insync'
  'import[[:space:]]+ib_insync'
  'from[[:space:]]+schwab_api'
  'import[[:space:]]+schwab_api'
)

FAIL=0

while IFS= read -r -d '' file; do
  # Files under app/brokers/ are allowed to import the trading SDK.
  case "$file" in
    "$ALLOWED_DIR"/*) continue ;;
  esac
  for pat in "${PATTERNS[@]}"; do
    if grep -Eq "$pat" "$file"; then
      echo "BROKER ISOLATION VIOLATION: $file matches forbidden pattern: $pat"
      FAIL=1
    fi
  done
done < <(find "$APP_DIR" -name '*.py' -type f -print0)

if [ "$FAIL" -ne 0 ]; then
  echo "Broker isolation check FAILED."
  echo "Order-routing broker code must live under app/brokers/. (Market-data"
  echo "alpaca.data.* imports are exempt by design.) If a broker SDK is"
  echo "genuinely needed elsewhere, write an ADR first."
  exit 1
fi

echo "Broker isolation check passed."
exit 0
