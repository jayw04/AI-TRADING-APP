#!/usr/bin/env bash
# AWS-side daily paper-stack report -> SNS email (ADR 0032 ops).
# Runs on the EC2 paper box via a systemd timer (once after close). Feeds the tracked
# generator (scripts/reports/daily_report.py) into the backend container, captures the
# Markdown digest (per-account summary + an issues/alerts section), persists a dated copy
# under reports/, and publishes it to the paper-alarms SNS topic so the owner gets the
# full daily report + issue list WITHOUT depending on the laptop/session. No secrets: aws
# uses the instance role (granted sns:Publish on this topic).
set -uo pipefail

REGION="${AWS_REGION:-us-east-1}"
TOPIC="arn:aws:sns:us-east-1:219024422756:workbench-paper-alarms"
DOCKER="docker"; command -v docker >/dev/null 2>&1 || DOCKER="sudo docker"
SCRIPT="/opt/workbench/app/scripts/reports/daily_report.py"
OUTDIR="/opt/workbench/app/reports"
[ -f "$SCRIPT" ] || { echo "generator missing: $SCRIPT"; exit 1; }

# Feed the generator into the container over stdin; the container needs no on-disk copy.
# The container's structlog init writes to STDOUT (broker-adapter load, factor-store open),
# so it precedes the Markdown — strip everything before the report header.
# Keep stderr: discarding it made a failed run report a GUESSED cause ("transient hiccup")
# with the real traceback gone, so a repeat was undiagnosable (2026-07-13).
ERRLOG="$(mktemp)"
trap 'rm -f "$ERRLOG"' EXIT
BODY="$($DOCKER exec -i workbench-backend python - < "$SCRIPT" 2>"$ERRLOG" | sed -n '/^# Daily Report/,$p')"

DATE_ET="$(TZ=America/New_York date '+%Y-%m-%d')"
if [ -z "$BODY" ] || ! printf '%s' "$BODY" | grep -q '^# Daily Report'; then
  ERRTAIL="$(grep -v '^[0-9-]\{10\} [0-9:]\{8\} \[' "$ERRLOG" 2>/dev/null | tail -25)"
  BODY="Daily report ${DATE_ET} - GENERATION FAILED.

The report generator ran but produced no digest. Investigate if several in a row fail.

Error output:
${ERRTAIL:-(no stderr captured)}"
  SUBJECT="Daily report ${DATE_ET} - GENERATION FAILED"
else
  # Persist a dated copy on the box (reports/*.md is git-ignored; handy for history).
  mkdir -p "$OUTDIR"
  printf '%s\n' "$BODY" > "$OUTDIR/${DATE_ET}.md"
  # Surface the alert count in the ASCII subject so the owner can triage without opening.
  CRIT=$(printf '%s\n' "$BODY" | grep -c '🔴' || true)
  WARN=$(printf '%s\n' "$BODY" | grep -c '🟡' || true)
  if [ "$CRIT" -gt 0 ]; then FLAG="${CRIT} critical / ${WARN} warn";
  elif [ "$WARN" -gt 0 ]; then FLAG="${WARN} warn";
  else FLAG="clean"; fi
  SUBJECT="Daily report ${DATE_ET} - ${FLAG}"
fi

aws sns publish --region "$REGION" --topic-arn "$TOPIC" --subject "$SUBJECT" --message "$BODY" >/dev/null \
  && echo "published: $SUBJECT" || { echo "SNS publish FAILED"; exit 1; }
