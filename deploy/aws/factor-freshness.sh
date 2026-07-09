#!/usr/bin/env bash
# Factor-store freshness alert -> SNS (the scheduled watchdog over factor-refresh).
# Runs on the EC2 paper box via a systemd timer, weekdays 07:00 ET — after the 06:00 ET
# factor-refresh and BEFORE the open (factor books rank on this store; Monday rebalances
# fire ~10:30 ET, hours before the 16:35 daily report would surface a problem).
#
# Alerts (SNS publish) when any of:
#   - workbench-factor-refresh.service last run FAILED (staging verify-abort or ingest error)
#   - the refresh has not run in the last ~26h (timer disabled / stuck)
#   - live sep prices are stale (> FRESH_TOLERANCE_DAYS calendar days; default 4 rides out a
#     long weekend without false alarms while still catching real staleness a day later)
#   - tickers.lastpricedate is BEHIND sep max — the lockstep break that empties the PIT
#     universe and makes every factor book silently HOLD (incident 2026-07-06)
#
# Deliberately alert-only (no daily "clean" email): the CEE and daily reports already prove
# the SNS path daily, and the daily report's >7d sep-staleness warn remains the coarse
# backstop if this watchdog itself dies. No secrets: aws uses the instance role.
set -uo pipefail

REGION="${AWS_REGION:-us-east-1}"
TOPIC="arn:aws:sns:us-east-1:219024422756:workbench-paper-alarms"
DOCKER="docker"; command -v docker >/dev/null 2>&1 || DOCKER="sudo docker"
TOLERANCE="${FRESH_TOLERANCE_DAYS:-4}"
SUBJECT_PREFIX="${FRESHNESS_SUBJECT_PREFIX:-}"   # e.g. "[TEST] " for manual alert-path tests

PROBLEMS=()

# 1) did the last refresh run fail? (oneshot: 'failed' persists until the next success)
if [ "$(systemctl is-failed workbench-factor-refresh.service 2>/dev/null)" = "failed" ]; then
  PROBLEMS+=("workbench-factor-refresh.service last run FAILED - live store left on its previous day (staging verify-abort or ingest error); see: journalctl -u workbench-factor-refresh")
fi

# 2) did the refresh actually run recently? (catches a disabled/stuck timer)
LAST_RUN="$(systemctl show workbench-factor-refresh.service -p ExecMainExitTimestamp --value 2>/dev/null)"
if [ -n "$LAST_RUN" ] && [ "$LAST_RUN" != "n/a" ]; then
  LAST_EPOCH="$(date -d "$LAST_RUN" +%s 2>/dev/null || echo 0)"
  AGE_H=$(( ( $(date +%s) - LAST_EPOCH ) / 3600 ))
  if [ "$AGE_H" -gt 26 ]; then
    PROBLEMS+=("factor-refresh has not run for ${AGE_H}h - is workbench-factor-refresh.timer enabled?")
  fi
else
  PROBLEMS+=("factor-refresh has no recorded run (fresh boot before 06:00 ET, or the unit never ran) - verify workbench-factor-refresh.timer")
fi

# 3) ground truth: the live store itself (freshness + the tickers/sep lockstep invariant).
STORE_REPORT="$($DOCKER exec -i -e TOLERANCE="$TOLERANCE" workbench-backend python - <<'PY' 2>/dev/null
import datetime, os, zoneinfo
import duckdb
tol = int(os.environ["TOLERANCE"])
et_today = datetime.datetime.now(zoneinfo.ZoneInfo("America/New_York")).date()
c = duckdb.connect("/app/data/factor_data.duckdb", read_only=True)
sep = c.execute("SELECT max(date) FROM sep").fetchone()[0]
lpd = c.execute("SELECT max(lastpricedate) FROM tickers").fetchone()[0]
print(f"STATUS sep_max={sep} lastpricedate={lpd} et_today={et_today} tolerance={tol}d")
if sep is None:
    print("PROBLEM live sep table is EMPTY")
else:
    age = (et_today - sep).days
    if age > tol:
        print(f"PROBLEM factor prices STALE: sep max {sep} is {age}d old (>{tol}d) - factor books are ranking on old data")
    if lpd is not None and lpd < sep:
        print(f"PROBLEM tickers.lastpricedate {lpd} BEHIND sep {sep} - PIT universe will resolve EMPTY and every factor book will silently HOLD (2026-07-06 incident class)")
PY
)"
RC=$?
if [ "$RC" -ne 0 ] || [ -z "$STORE_REPORT" ]; then
  PROBLEMS+=("could not read the live factor store from the backend container (container down, or duckdb open failed)")
else
  while IFS= read -r line; do
    case "$line" in PROBLEM*) PROBLEMS+=("${line#PROBLEM }");; esac
  done <<< "$STORE_REPORT"
fi

DATE_ET="$(TZ=America/New_York date '+%Y-%m-%d')"
if [ "${#PROBLEMS[@]}" -eq 0 ]; then
  echo "clean: $STORE_REPORT"
  exit 0
fi

BODY="${SUBJECT_PREFIX}Factor-store freshness check ${DATE_ET} - ${#PROBLEMS[@]} issue(s):

$(printf -- '- %s\n' "${PROBLEMS[@]}")

Store state:
${STORE_REPORT:-unavailable}

Runbook: the factor books (momentum/sector/low-vol/combined) RANK on data/factor_data.duckdb.
A failed refresh leaves the previous day's store (safe for ~a few days); a lockstep break makes
books HOLD at the next rebalance. Rollback copy: factor_data.prev.duckdb. See
deploy/aws/factor-refresh.sh and Docs/runbook/aws-migration.md."

SUBJECT="${SUBJECT_PREFIX}FACTOR STORE ALERT ${DATE_ET} - ${#PROBLEMS[@]} issue(s)"
aws sns publish --region "$REGION" --topic-arn "$TOPIC" --subject "$SUBJECT" --message "$BODY" >/dev/null \
  && echo "published: $SUBJECT" || { echo "SNS publish FAILED"; exit 1; }
