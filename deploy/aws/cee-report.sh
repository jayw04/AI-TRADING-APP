#!/usr/bin/env bash
# AWS-side Continuous Evidence Engine report -> SNS email (the CEE's scheduled consumer).
# Runs on the EC2 paper box via a systemd timer (weekdays after close, after the daily
# report). Feeds the tracked generator (apps/backend/scripts/reports/cee_report.py) into
# the backend container over stdin, captures the per-book Research-Envelope + Evidence-
# Clock status, persists a dated copy under reports/cee/, and publishes to the
# paper-alarms SNS topic. The generator exits 2 when any live book has escalated to
# Investigate (probabilistic drift) — that state is surfaced loudly in the subject so the
# owner can triage without opening. Publishing every run (not only on Investigate) makes
# a silent failure visible: no email means the control itself is broken. No secrets: aws
# uses the instance role (granted sns:Publish on this topic).
set -uo pipefail

REGION="${AWS_REGION:-us-east-1}"
TOPIC="arn:aws:sns:us-east-1:219024422756:workbench-paper-alarms"
DOCKER="docker"; command -v docker >/dev/null 2>&1 || DOCKER="sudo docker"
SCRIPT="/opt/workbench/app/apps/backend/scripts/reports/cee_report.py"
OUTDIR="/opt/workbench/app/reports/cee"
[ -f "$SCRIPT" ] || { echo "generator missing: $SCRIPT"; exit 1; }

# Feed the generator into the container over stdin; the container needs no on-disk copy.
# Keep stderr: discarding it made a failed run report a GUESSED cause ("transient hiccup")
# with the real traceback gone, so a repeat was undiagnosable (2026-07-13).
ERRLOG="$(mktemp)"
trap 'rm -f "$ERRLOG"' EXIT
RAW="$($DOCKER exec -i workbench-backend python - < "$SCRIPT" 2>"$ERRLOG")"
RC=$?
# The container's structlog init writes to STDOUT before the report — strip the preamble.
BODY="$(printf '%s\n' "$RAW" | sed -n '/^=== Continuous Evidence Engine/,$p')"

DATE_ET="$(TZ=America/New_York date '+%Y-%m-%d')"
if [ -z "$BODY" ]; then
  ERRTAIL="$(grep -v '^[0-9-]\{10\} [0-9:]\{8\} \[' "$ERRLOG" 2>/dev/null | tail -25)"
  BODY="CEE report ${DATE_ET} - GENERATION FAILED.

The CEE generator ran but produced no report. This control is the drift alarm — a repeat
means the alarm itself is down. Investigate.

Error output:
${ERRTAIL:-(no stderr captured)}"
  SUBJECT="CEE report ${DATE_ET} - GENERATION FAILED"
else
  # Persist a dated copy on the box (reports/ is git-ignored; handy for drift history).
  mkdir -p "$OUTDIR"
  printf '%s\n' "$BODY" > "$OUTDIR/${DATE_ET}.md"
  INVESTIGATE=$(printf '%s\n' "$BODY" | grep -c '\[Investigate\]' || true)
  WATCH=$(printf '%s\n' "$BODY" | grep -c '\[Watch\]' || true)
  if [ "$RC" -eq 2 ] || [ "$INVESTIGATE" -gt 0 ]; then
    SUBJECT="CEE report ${DATE_ET} - INVESTIGATE: ${INVESTIGATE} book(s) drifted"
  elif [ "$WATCH" -gt 0 ]; then
    SUBJECT="CEE report ${DATE_ET} - ${WATCH} book(s) on Watch"
  else
    SUBJECT="CEE report ${DATE_ET} - clean"
  fi
fi

aws sns publish --region "$REGION" --topic-arn "$TOPIC" --subject "$SUBJECT" --message "$BODY" >/dev/null \
  && echo "published: $SUBJECT" || { echo "SNS publish FAILED"; exit 1; }
