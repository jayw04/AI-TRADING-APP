#!/usr/bin/env bash
# AWS-side daily/weekly pipeline-health checklist -> DB + SNS email (ADR 0032 ops).
#
# Runs on the EC2 paper box via two systemd timers:
#   DAILY   weekdays 16:50 ET (after close, after the daily + CEE reports)
#   WEEKLY  Monday   11:15 ET (after ALL four cron rebalances: 10:00 / 10:24 / 10:32 / 10:40)
#
# Feeds the tracked generator (apps/backend/scripts/reports/pipeline_health.py) into the
# backend container. The generator PERSISTS its findings (data_health_snapshots +
# ops_check_runs) and reads strategy_dispatch_runs, so the checklist is queryable history —
# not just an email that scrolls away. It exits 2 when any check FAILs.
#
# No secrets: aws uses the instance role (granted sns:Publish on this topic).
set -uo pipefail

KIND="${1:-DAILY}"
REGION="${AWS_REGION:-us-east-1}"
TOPIC="arn:aws:sns:us-east-1:219024422756:workbench-paper-alarms"
DOCKER="docker"; command -v docker >/dev/null 2>&1 || DOCKER="sudo docker"
SCRIPT="/opt/workbench/app/apps/backend/scripts/reports/pipeline_health.py"
OUTDIR="/opt/workbench/app/reports/pipeline-health"
[ -f "$SCRIPT" ] || { echo "generator missing: $SCRIPT"; exit 1; }

# Keep stderr. Discarding it is why an empty report could only ever be described as a
# guessed "transient hiccup" with the real traceback gone (2026-07-13).
ERRLOG="$(mktemp)"
trap 'rm -f "$ERRLOG"' EXIT

# NOTE: `docker exec` needs -i to attach stdin — without it the heredoc/stdin script is
# never delivered and the python block silently does not run (fixed once already, #408).
RAW="$($DOCKER exec -i workbench-backend python - --kind "$KIND" < "$SCRIPT" 2>"$ERRLOG")"
RC=$?
# structlog's init writes to STDOUT ahead of the report — strip the preamble.
BODY="$(printf '%s\n' "$RAW" | sed -n '/^# .* Pipeline Health/,$p')"

DATE_ET="$(TZ=America/New_York date '+%Y-%m-%d')"
LABEL="$(printf '%s' "$KIND" | tr '[:upper:]' '[:lower:]')"

if [ -z "$BODY" ]; then
  ERRTAIL="$(grep -v '^[0-9-]\{10\} [0-9:]\{8\} \[' "$ERRLOG" 2>/dev/null | tail -25)"
  BODY="Pipeline health ${DATE_ET} (${KIND}) - CHECK DID NOT RUN.

The checklist generator produced no report, so data freshness and rebalance status are
UNVERIFIED for this window. This is itself a finding: the monitor is down.

Error output:
${ERRTAIL:-(no stderr captured)}"
  SUBJECT="Pipeline health ${DATE_ET} ${KIND} - CHECK FAILED TO RUN"
else
  mkdir -p "$OUTDIR"
  printf '%s\n' "$BODY" > "$OUTDIR/${DATE_ET}-${LABEL}.md"
  FAIL=$(printf '%s\n' "$BODY" | grep -c '🔴' || true)
  WARN=$(printf '%s\n' "$BODY" | grep -c '🟡' || true)
  if [ "$RC" -eq 2 ] || [ "$FAIL" -gt 0 ]; then
    SUBJECT="Pipeline health ${DATE_ET} ${KIND} - ${FAIL} FAIL / ${WARN} warn"
  elif [ "$WARN" -gt 0 ]; then
    SUBJECT="Pipeline health ${DATE_ET} ${KIND} - ${WARN} warn"
  else
    SUBJECT="Pipeline health ${DATE_ET} ${KIND} - clean"
  fi
fi

aws sns publish --region "$REGION" --topic-arn "$TOPIC" --subject "$SUBJECT" --message "$BODY" >/dev/null \
  && echo "published: $SUBJECT" || { echo "SNS publish FAILED"; exit 1; }
