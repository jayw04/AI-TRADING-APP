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

# Overridable so the equivalence tests can point the check at fixture trees.
ROOT="${BROKER_ISOLATION_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../" && pwd)}"
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

# ---------------------------------------------------------------------------
# Prefilter (performance only — the reported result is unchanged)
# ---------------------------------------------------------------------------
#
# This check used to run one `grep` per (file, pattern): 455 files x 10 patterns
# = 4,550 process spawns, measured at 145s. It is the slowest step in the LIGHT
# block, and LIGHT runs on every backend pull request.
#
# One `grep -REl` over the alternation of the same ten patterns collects the
# CANDIDATE files first. The authoritative walk below is unchanged — same
# `find`, same order, same per-pattern loop, same message — it just skips any
# file the prefilter proved cannot match. In the normal case (no violations)
# there are zero candidates and zero inner greps; when something does match, the
# original code path runs on those few files and the output is byte-identical,
# including line order.
#
# The prefilter can only ever ADD work relative to correctness: a candidate that
# turns out not to match simply loops the ten patterns and finds nothing. The
# risk to guard is the converse — a file `find` sees but `grep -r` does not —
# which is what tests/test_check_broker_isolation.py differentially tests
# against an independent reference implementation.
#
# Limitation, stated: a filename containing a newline would defeat the candidate
# membership test below. `find -print0` tolerates such names and this does not.
# No such file exists or could reasonably exist here, and the pre-existing
# `grep -Eq "$pat" "$file"` was already unsafe for other exotic names.
COMBINED="$(IFS='|'; printf '%s' "${PATTERNS[*]}")"
CANDIDATES="$(grep -REl --include='*.py' "$COMBINED" "$APP_DIR" || true)"

while IFS= read -r -d '' file; do
  # Files under app/brokers/ are allowed to import the trading SDK.
  case "$file" in
    "$ALLOWED_DIR"/*) continue ;;
  esac
  # Skip files the single prefilter pass proved cannot match any pattern.
  case $'\n'"$CANDIDATES"$'\n' in
    *$'\n'"$file"$'\n'*) ;;
    *) continue ;;
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
