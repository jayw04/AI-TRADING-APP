#!/usr/bin/env bash
# EAD reference-only invariant (the fifteenth CI invariant).
#
# Four EAD event-driven programs (INSIDER-001 / GOVCONTRACT-001 / CONGRESS-001 / LOBBY-001) cleared
# the >=100-benchmarked gate and were still Rejected after matched controls — one finding: public
# corporate-disclosure events carry no residual alpha. Their event labels are reference/context
# ONLY: they may be DISPLAYED (Opportunity Report, negative-evidence memory, whitepaper) but must
# never enter ranking, sizing, or the order path. This asserts the order-path + ranking/selection
# modules never name a reference-only event-type string — structurally, so "buy because X spiked"
# can't creep in via the one PR nobody looks closely at.
#
# Governance: docs/implementation/TradingWorkbench_EAD_DatasetTriage_v0.2.md (reference-use).
# Route EAD events through app.altdata.reference_only (partition_reference_only / assert_usable_for_ranking).
# Same shape as check_altdata_order_path_isolation.sh. Disabling this requires an ADR.
set -euo pipefail
cd "$(dirname "$0")/.."   # apps/backend

# Single source of truth: the rejected-EAD event types, straight from the guard module.
PATTERN="$(python3 -c 'from app.altdata.reference_only import REFERENCE_ONLY_EVENT_TYPES as s; print("|".join(sorted(s)))')"
[[ -n "$PATTERN" ]] || { echo "reference-only invariant: empty event-type set (import failed?)" >&2; exit 1; }

# Order-path + ranking / selection / sizing modules — these must be clear of reference-only labels.
SEARCH_PATHS=(
  "app/services/order_router.py"
  "app/orders"
  "app/risk"
  "app/brokers"
  "app/strategies"
  "app/services/scanner"
)

OFFENDERS=""
for p in "${SEARCH_PATHS[@]}"; do
  [[ -e "$p" ]] || continue
  HIT=$(grep -rEn "\"($PATTERN)\"|'($PATTERN)'" "$p" --include='*.py' || true)
  [[ -n "$HIT" ]] && OFFENDERS+="$HIT"$'\n'
done

if [[ -n "${OFFENDERS//[$'\n']/}" ]]; then
  echo "EAD REFERENCE-ONLY VIOLATION — order-path/ranking code names a rejected EAD event label:" >&2
  echo "$OFFENDERS" >&2
  echo "" >&2
  echo "Rejected EAD patterns ($PATTERN) are reference/context ONLY. They may be displayed, but" >&2
  echo "must not enter ranking, sizing, or the order path. Route EAD events through" >&2
  echo "app.altdata.reference_only (partition_reference_only / assert_usable_for_ranking)." >&2
  exit 1
fi
echo "EAD reference-only invariant OK"
