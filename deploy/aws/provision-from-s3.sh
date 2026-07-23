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
#   LOSS_CONTROL_MODE                ADR 0043 loss-control mode: OFF | SHADOW | ENFORCE
#                                    (default OFF = pre-ADR-0043 behaviour; unchanged for live-box
#                                    redeploys). Set ENFORCE ONLY on the isolated ADR-0043 validation
#                                    box, never on the live paper stack before the canary is GREEN.
#   AWS_REGION / S3_BUCKET           default us-east-1 / workbench-backups-219024422756
#   CODE_KEY                         S3 key of the code tarball to deploy
#                                    (default bootstrap/code.tgz = the LIVE artifact; the isolated
#                                    validation box MUST override this so it neither reads nor clobbers
#                                    the live key, e.g. CODE_KEY=bootstrap/adr0043-canary/code.tgz)
#   NO_BUILD=1                       skip the image build (config/.env-only refresh)
set -uxo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin:/sbin:/usr/sbin:/snap/bin:$PATH

R="${AWS_REGION:-us-east-1}"
BUCKET="${S3_BUCKET:-workbench-backups-219024422756}"
CODE_KEY="${CODE_KEY:-bootstrap/code.tgz}"
APP=/opt/workbench
SCHED="${WORKBENCH_SCHEDULER_ENABLED:-false}"
ALPACA="${WORKBENCH_ALPACA_STARTUP_ENABLED:-false}"
HOST_ID="${WORKBENCH_HOST_ID:-ec2-paper}"
# ADR 0043: uppercase to match the LossControlMode enum values (OFF/SHADOW/ENFORCE).
LOSS_CONTROL_MODE="$(printf '%s' "${LOSS_CONTROL_MODE:-OFF}" | tr '[:lower:]' '[:upper:]')"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

# --- ADR-0043 VALIDATION-BOX GUARD -------------------------------------------------------------
# This provisioner is fine for the live box's own reviewed key, but it downloads by key only (no
# object version), does not verify the approved SHA before extraction, extracts directly over the
# running tree, and immediately rebuilds + restarts. The ADR-0043 validation-box deploy was approved
# as an EXACT object VERSION + checksum with a staged, migration-gated, rollback-capable swap. So
# this path REFUSES the validation box and directs the operator to the hardened provisioner. The
# validation box is identified by its host id, by ENFORCE loss-control mode (validation-box only),
# or by an adr0043/ code key — never fall back to bootstrap/code.tgz for it.
_validation_box=0
case "${HOST_ID}" in *adr0043*|*validation*|*canary*) _validation_box=1 ;; esac
[ "$LOSS_CONTROL_MODE" = "ENFORCE" ] && _validation_box=1
case "${CODE_KEY}" in adr0043/*) _validation_box=1 ;; esac
if [ "$_validation_box" = "1" ]; then
  echo "FATAL: this looks like the ADR-0043 validation box (host_id='${HOST_ID}',"      >&2
  echo "       loss_control_mode='${LOSS_CONTROL_MODE}', code_key='${CODE_KEY}')."       >&2
  echo "       Use the hardened, version+checksum-pinned, staged provisioner instead:"   >&2
  echo "         CODE_KEY=... CODE_VERSION_ID=... EXPECTED_CODE_SHA256=... \\"            >&2
  echo "         EXPECTED_CODE_BYTES=... bash deploy/aws/provision-adr0043-validation.sh" >&2
  echo "       This unversioned path must never deploy to the validation box."           >&2
  exit 2
fi
# --- end guard ---------------------------------------------------------------------------------

mkdir -p "$APP/app" "$APP/data"

# 1) code from S3 (CODE_KEY override keeps the validation box off the live bootstrap/code.tgz key)
aws s3 cp "s3://$BUCKET/$CODE_KEY" /tmp/code.tgz --region "$R"
tar xzf /tmp/code.tgz -C "$APP/app"

# 1b) provenance marker (git-archive deployments carry their own source identity — the box has no .git).
#     Non-fatal echo here; the authoritative read-only gate is in the runbook (marker + archive digest).
if [ -f "$APP/app/DEPLOYED_BUILD_INFO.json" ]; then
  echo "DEPLOYED_BUILD_INFO.json:"; cat "$APP/app/DEPLOYED_BUILD_INFO.json"
else
  echo "WARN: no DEPLOYED_BUILD_INFO.json in the archive — source provenance is unverifiable on this box."
fi

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
  # ADR 0043 ambient loss-control mode into the backend's REAL runtime env (loaded via env_file:.env).
  # OFF by default (identical to pre-ADR-0043); ENFORCE only on the isolated validation box.
  echo "WORKBENCH_LOSS_CONTROL_MODE=${LOSS_CONTROL_MODE}"
  echo "AGENT_DAILY_BUDGET_USD=2.0"
  # SEC EDGAR fair-access User-Agent (org + contact) — public, non-secret config, NOT in SSM.
  # Required by the Security Master (CAP-024) ticker->CIK map for EAD / GOVCONTRACT-001 ingestion.
  echo "SEC_EDGAR_USER_AGENT=TradingWorkbench (GlobalComplyAI, LLC) jay.w0416@gmail.com"
  for KEY in WORKBENCH_MASTER_KEY MCP_BACKEND_TOKEN WORKBENCH_MCP_KEY ANTHROPIC_API_KEY \
             AGENT_API_KEY ALPACA_PAPER_API_KEY ALPACA_PAPER_API_SECRET \
             NASDAQ_DATA_LINK_API_KEY FMP_API_KEY QUIVER_API_KEY; do
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
# ADR 0043: confirm the EFFECTIVE ambient mode from inside the container (not inferred from .env).
$COMPOSE exec -T backend sh -lc \
  'printf "effective WORKBENCH_LOSS_CONTROL_MODE=%s\n" "${WORKBENCH_LOSS_CONTROL_MODE:-<unset>}"' \
  2>/dev/null || echo "WARN: could not read effective loss-control mode from the container"

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
