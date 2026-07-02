#!/usr/bin/env bash
# Sync the day's pre-market gappers file from this laptop to the AWS paper box.
# The gappers scanner (claude-trading-view, driven by TradingView Desktop) is laptop-only;
# the Opportunities-page panel on the box reads /opt/workbench/claude-trading-view/. This
# ships today's file (or the newest available) over SSH after the scanner runs (~07:30 ET).
# Advisory data only. Runs from a Windows scheduled task ~09:00 ET on trading days.
set -uo pipefail

GAPPERS_DIR="/c/LLM-RAG-APP/claude-trading-view"
SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=20 -o ClearAllForwardings=yes"
LOG="/c/LLM-RAG-APP/claude-trading-view/sync-gappers.log"

today="$(date +%Y-%m-%d)"
f="$GAPPERS_DIR/premarket_gappers_${today}.json"
[ -f "$f" ] || f="$(ls -t "$GAPPERS_DIR"/premarket_gappers_*.json 2>/dev/null | head -1)"
if [ -z "${f:-}" ] || [ ! -f "$f" ]; then
  echo "$(date '+%F %T') NO gappers file found in $GAPPERS_DIR" | tee -a "$LOG"
  exit 1
fi
base="$(basename "$f")"

if scp $SSH_OPTS "$f" workbench:/tmp/ \
   && ssh $SSH_OPTS workbench "sudo cp /tmp/'$base' /opt/workbench/claude-trading-view/"; then
  echo "$(date '+%F %T') synced $base -> box" | tee -a "$LOG"
else
  echo "$(date '+%F %T') FAILED to sync $base" | tee -a "$LOG"
  exit 1
fi
