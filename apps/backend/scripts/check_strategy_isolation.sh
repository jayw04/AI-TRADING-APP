#!/usr/bin/env bash
# Strategy isolation tripwire: code under apps/backend/app/strategies/
# must NOT import from app.brokers directly. The only path to the broker
# is through OrderRouter, which the engine injects into StrategyContext.
#
# Catches future PRs that try to shortcut around StrategyContext (which
# would be a quiet ADR 0002 violation — strategies bypassing the risk
# engine without anyone noticing).
set -euo pipefail

PATTERN='from[[:space:]]+app\.brokers|import[[:space:]]+app\.brokers'
SEARCH_DIR="apps/backend/app/strategies"

OFFENDERS=$(grep -rEn "$PATTERN" "$SEARCH_DIR" --include='*.py' || true)

if [[ -n "$OFFENDERS" ]]; then
  echo "STRATEGY ISOLATION VIOLATION — code under app/strategies/ imports app.brokers:" >&2
  echo "$OFFENDERS" >&2
  echo "" >&2
  echo "Strategies reach the broker only via StrategyContext.submit_order, which the" >&2
  echo "engine binds to OrderRouter.submit. Don't bypass." >&2
  exit 1
fi
echo "Strategy isolation OK"
