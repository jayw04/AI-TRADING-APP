#!/usr/bin/env bash
# Provision / redeploy the workbench box from S3 code delivery + SSM secrets (ADR 0032).
#
# Used instead of the git-clone bootstrap when the repo is private and no deploy token is set:
# the laptop builds the code tarball (`git archive <branch> | gzip`) and uploads it to
# s3://<bucket>/bootstrap/code.tgz; this script pulls it, builds the `.env` ENTIRELY from
# SSM /workbench/prod/* (nothing hand-written), and builds + starts the stack.
#
# Env knobs (all default to the SAFE/inert values):
#   WORKBENCH_SCHEDULER_ENABLED      arm the scheduler (default false = DISARMED)
#   WORKBENCH_ALPACA_STARTUP_ENABLED connect to Alpaca at boot (default false)
#   WORKBENCH_HOST_ID                heartbeat host id (default ec2-paper)
#   AWS_REGION / S3_BUCKET           default us-east-1 / workbench-backups-219024422756
#   NO_BUILD=1                       skip the image build (config/.env-only refresh)
set -uxo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin:/sbin:/usr/sbin:/snap/bin:$PATH

R="${AWS_REGION:-us-east-1}"
BUCKET="${S3_BUCKET:-workbench-backups-219024422756}"
APP=/opt/workbench
SCHED="${WORKBENCH_SCHEDULER_ENABLED:-false}"
ALPACA="${WORKBENCH_ALPACA_STARTUP_ENABLED:-false}"
HOST_ID="${WORKBENCH_HOST_ID:-ec2-paper}"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

mkdir -p "$APP/app" "$APP/data"

# 1) code from S3
aws s3 cp "s3://$BUCKET/bootstrap/code.tgz" /tmp/code.tgz --region "$R"
tar xzf /tmp/code.tgz -C "$APP/app"

# 2) .env ENTIRELY from SSM — config lines + a per-key secret loop (no hand-written secrets).
#    TZ=UTC matches the laptop so per-strategy on_bar crons don't shift (ADR 0032 determinism).
{
  echo "WORKBENCH_ENV=paper-cloud"
  echo "TZ=UTC"
  echo "WORKBENCH_HOST=0.0.0.0"
  echo "WORKBENCH_DB_URL=sqlite+aiosqlite:////app/data/workbench.sqlite"
  echo "WORKBENCH_ALPACA_STARTUP_ENABLED=${ALPACA}"
  echo "WORKBENCH_SCHEDULER_ENABLED=${SCHED}"
  echo "WORKBENCH_LIVE_TRADING_ALLOWED=false"
  echo "WORKBENCH_HOST_ID=${HOST_ID}"
  echo "AGENT_DAILY_BUDGET_USD=2.0"
  for KEY in WORKBENCH_MASTER_KEY MCP_BACKEND_TOKEN WORKBENCH_MCP_KEY ANTHROPIC_API_KEY \
             AGENT_API_KEY ALPACA_PAPER_API_KEY ALPACA_PAPER_API_SECRET \
             NASDAQ_DATA_LINK_API_KEY FMP_API_KEY; do
    V=$(aws ssm get-parameter --region "$R" --name "/workbench/prod/$KEY" --with-decryption \
          --query Parameter.Value --output text 2>/dev/null)
    [ -n "$V" ] && [ "$V" != "None" ] && echo "$KEY=$V"
  done
} > "$APP/.env"
chmod 600 "$APP/.env"
ln -sf "$APP/.env" "$APP/app/.env"
ln -sfn "$APP/data" "$APP/app/data"
echo "env keys: $(cut -d= -f1 "$APP/.env" | tr '\n' ' ')"

# 3) build + start
cd "$APP/app"
if [ "${NO_BUILD:-0}" = "1" ]; then $COMPOSE up -d; else $COMPOSE up -d --build; fi
sleep 25
$COMPOSE ps --format "{{.Service}} {{.Status}}"
curl -fsS http://127.0.0.1:8000/healthz && echo " HEALTHZ_OK" || echo " HEALTHZ_FAIL"

# 4) CloudWatch metric publisher (ADR 0032 monitoring): install/refresh the systemd
#    timer that runs cw-publish-metrics.sh every 5 min (no-op-safe if already enabled).
if [ -d /run/systemd/system ]; then
  chmod +x "$APP/app/deploy/aws/cw-publish-metrics.sh"
  install -m 644 "$APP/app/deploy/aws/systemd/workbench-cw-metrics.service" /etc/systemd/system/
  install -m 644 "$APP/app/deploy/aws/systemd/workbench-cw-metrics.timer" /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now workbench-cw-metrics.timer
  echo "cw-metrics timer: $(systemctl is-active workbench-cw-metrics.timer 2>/dev/null)"
fi
