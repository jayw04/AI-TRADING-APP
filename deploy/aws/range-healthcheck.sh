#!/usr/bin/env bash
# Range price-setting operational self-healing (ADR 0035). Runs on the EC2 box via a
# systemd timer at pre-open / post-open / intraday. Feeds scripts/range_healthcheck.py
# into the backend container, reads the health STATE (GREEN/YELLOW/ORANGE/RED), performs
# the one Level-1 operational correction (pre-open re-arm) when flagged + an ops
# credential is present, and SNS-alerts on any non-GREEN state. It NEVER clears a halt,
# resets a breaker, or submits/cancels an order — those are Level-4, human-only (ADR 0035).
set -uo pipefail

REGION="${AWS_REGION:-us-east-1}"
TOPIC="arn:aws:sns:us-east-1:219024422756:workbench-paper-alarms"
DOCKER="docker"; command -v docker >/dev/null 2>&1 || DOCKER="sudo docker"
SCRIPT="/opt/workbench/app/apps/backend/scripts/range_healthcheck.py"
# root-only file holding the range user's login password; enables the pre-open re-arm.
SECRET_FILE="${OPS_RANGE_SECRET_FILE:-/opt/workbench/.ops-range-secret}"
API="http://127.0.0.1:8000"
[ -f "$SCRIPT" ] || { echo "healthcheck script missing: $SCRIPT"; exit 1; }

# Phase from ET clock: <09:30 pre_open, 09:30-10:10 (range forming) treated as pre_open,
# 10:10-16:00 intraday; the post-open levels check wants the range frozen (~10:05+).
HH=$(TZ=America/New_York date +%H); MM=$(TZ=America/New_York date +%M)
MIN=$((10#$HH*60 + 10#$MM))
if   [ "$MIN" -lt 610 ]; then PHASE="pre_open"      # before 10:10 ET
elif [ "$MIN" -lt 960 ]; then PHASE="post_or"       # 10:10-16:00 ET
else PHASE="intraday"; fi

run_check() {
  $DOCKER exec -i workbench-backend python - --phase "$PHASE" < "$SCRIPT" 2>/dev/null
}

REPORT="$(run_check)"
STATE=$(printf '%s\n' "$REPORT" | sed -n 's/^STATE=//p' | head -1)
ACTION=$(printf '%s\n' "$REPORT" | sed -n 's/^ACTION=//p' | head -1)
SID=$(printf '%s\n' "$REPORT" | sed -n 's/^STRATEGY_ID=//p' | head -1)
[ -z "$STATE" ] && STATE="ORANGE" && REPORT="range-healthcheck: could not gather (transient) — no STATE returned"

# Level-1 operational correction: pre-open re-arm. Safe only pre-open (the opening range
# has not started, so the strategy rebuilds it cleanly). Requires the ops credential.
CORRECTED=""
if [ "$ACTION" = "rearm" ] && [ -n "$SID" ]; then
  if [ -f "$SECRET_FILE" ]; then
    PW=$(cat "$SECRET_FILE")
    curl -s -c /tmp/ops-cj.txt -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
      -d "{\"email\":\"range@local.dev\",\"password\":\"$PW\"}" -o /dev/null -w '' || true
    RC=$(curl -s -b /tmp/ops-cj.txt --max-time 90 -X POST "$API/api/v1/strategies/$SID/reload" \
           -o /dev/null -w '%{http_code}' || echo "000")
    rm -f /tmp/ops-cj.txt
    CORRECTED="re-armed strategy #$SID (reload http=$RC)"
    sleep 3
    REPORT="$(run_check)"                              # re-check after the correction
    STATE=$(printf '%s\n' "$REPORT" | sed -n 's/^STATE=//p' | head -1)
    [ "$STATE" = "GREEN" ] && STATE="YELLOW"           # recovered automatically
  else
    CORRECTED="re-arm needed but no ops credential ($SECRET_FILE) — alerting instead"
    STATE="ORANGE"
  fi
fi

# GREEN = quiet. Anything else pages, with the health state + findings + recommendations.
if [ "$STATE" = "GREEN" ]; then
  echo "range-healthcheck: GREEN ($PHASE) — no alert"
  exit 0
fi
SUBJECT="Range health ${STATE} $(TZ=America/New_York date '+%Y-%m-%d %H:%M ET') (${PHASE})"
BODY="$REPORT"
[ -n "$CORRECTED" ] && BODY="$BODY

self-heal: $CORRECTED"
aws sns publish --region "$REGION" --topic-arn "$TOPIC" --subject "$SUBJECT" --message "$BODY" >/dev/null \
  && echo "published: $SUBJECT" || { echo "SNS publish FAILED"; exit 1; }
