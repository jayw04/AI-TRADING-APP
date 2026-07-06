#!/usr/bin/env bash
# Publish Workbench paper-stack health metrics to CloudWatch (ADR 0032 monitoring).
#
# Runs on the EC2 box via a systemd timer (every 5 min). Bridges the app's own state
# into CloudWatch so the dashboard + alarms (esp. the missed-job alarm) have data:
#   namespace "Workbench/Paper", dimension HostId=<WORKBENCH_HOST_ID>
#     SchedulerArmed       1 if an armed scheduler heartbeat exists, else 0
#     BackendHealthy       1 if /healthz is ok, else 0
#     MarketOpen           1 during REGULAR session (MarketSession, holiday-aware), else 0
#     DispatchAgeSeconds   age of the last on_bar dispatch (large when idle/closed)
#     HeartbeatAgeSeconds  age of the last scheduler heartbeat
#     MissedDispatch       1 ONLY when armed AND market-open AND no dispatch in >15 min
#                          -> the market-hours-aware missed-rebalance signal (never fires
#                             overnight/weekends/holidays, and never on a disarmed box)
#
# The instance role's CloudWatchAgentServerPolicy already grants cloudwatch:PutMetricData.
# Compute happens INSIDE the backend container (reuses MarketSession + the heartbeat row +
# a self /healthz probe); the PutMetricData call runs on the host (has the aws CLI + role).
set -uo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin:/sbin:/usr/sbin:/snap/bin:$PATH

R="${AWS_REGION:-us-east-1}"
NS="Workbench/Paper"
APP=/opt/workbench
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
cd "$APP/app" 2>/dev/null || exit 0

# Build the CloudWatch MetricData JSON inside the container (it has the app + .env HostId).
RAW="$($COMPOSE exec -T backend python - <<'PY' 2>/dev/null
import json, os, sqlite3, urllib.request
from datetime import datetime, timezone

def age(ts):
    if not ts:
        return 1e7
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - d).total_seconds())
    except Exception:
        return 1e7

armed = 0
dispatch_age = beat_age = 1e7
try:
    c = sqlite3.connect("/app/data/workbench.sqlite")
    row = c.execute(
        "SELECT armed,last_dispatch_at,last_beat_at FROM scheduler_heartbeat "
        "ORDER BY last_beat_at DESC LIMIT 1"
    ).fetchone()
    c.close()
    if row:
        armed = 1 if row[0] else 0
        dispatch_age = age(row[1])
        beat_age = age(row[2])
except Exception:
    pass

try:
    from app.market.session import MarketSession
    market_open = 1 if MarketSession().classify().is_regular else 0
except Exception:
    market_open = 0

try:
    urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=5)
    healthy = 1
except Exception:
    healthy = 0

missed = 1 if (armed and market_open and dispatch_age > 900) else 0
host = os.environ.get("WORKBENCH_HOST_ID", "ec2-paper")
dims = [{"Name": "HostId", "Value": host}]
def m(name, value, unit="None"):
    return {"MetricName": name, "Value": float(value), "Unit": unit, "Dimensions": dims}
print(json.dumps([
    m("SchedulerArmed", armed),
    m("BackendHealthy", healthy),
    m("MarketOpen", market_open),
    m("DispatchAgeSeconds", round(dispatch_age), "Seconds"),
    m("HeartbeatAgeSeconds", round(beat_age), "Seconds"),
    m("MissedDispatch", missed),
]))
PY
)"

# The container may print structlog warnings (e.g. market_session_calendar_fallback) on
# stdout ahead of the payload; keep only the JSON array line the snippet prints last.
JSON="$(printf '%s\n' "$RAW" | grep -E '^\[' | tail -n 1)"

# Container down / exec failed -> emit an explicit "backend unhealthy" sample so the
# BackendUnhealthy alarm still trips (silence would otherwise read as healthy).
if [ -z "$JSON" ]; then
  HOST_ID="$(grep -E '^WORKBENCH_HOST_ID=' "$APP/.env" 2>/dev/null | cut -d= -f2)"
  HOST_ID="${HOST_ID:-ec2-paper}"
  JSON="[{\"MetricName\":\"BackendHealthy\",\"Value\":0,\"Unit\":\"None\",\"Dimensions\":[{\"Name\":\"HostId\",\"Value\":\"$HOST_ID\"}]}]"
fi

echo "$JSON" > /tmp/cw-metrics.json
aws cloudwatch put-metric-data --region "$R" --namespace "$NS" --metric-data "file:///tmp/cw-metrics.json"
