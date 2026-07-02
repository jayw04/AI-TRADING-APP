#!/usr/bin/env bash
# Phase-3 CUTOVER — flip the active host to EC2 (ADR 0032). Run ON the EC2 box.
#
# PRECONDITION (the operator MUST do this first): the laptop stack is DOWN and its
# autostart/scheduled tasks disabled  ==> ZERO armed schedulers. Then the operator takes a
# FRESH online snapshot of the live DB and uploads it:
#     python -c "import sqlite3;s=sqlite3.connect('data/workbench.sqlite');d=sqlite3.connect('snap.sqlite');s.backup(d)"
#     aws s3 cp snap.sqlite s3://<bucket>/cutover/workbench_final.sqlite
#
# This script then: restores that DB, migrates it, catches up factor data, ARMS this host
# (Alpaca + scheduler ON), and verifies EXACTLY ONE armed host. Reversible: `docker compose
# down` here + bring the laptop back up from the pre-cutover snapshot.
set -uxo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin:/sbin:/usr/sbin:/snap/bin:$PATH

R="${AWS_REGION:-us-east-1}"
BUCKET="${S3_BUCKET:-workbench-backups-219024422756}"
SNAPSHOT_KEY="${SNAPSHOT_KEY:-cutover/workbench_final.sqlite}"
APP=/opt/workbench
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
cd "$APP/app"

# 1) restore the REAL DB snapshot (overwrites any rehearsal/scratch DB)
$COMPOSE stop backend
aws s3 cp "s3://$BUCKET/$SNAPSHOT_KEY" "$APP/data/workbench.sqlite" --region "$R"

# 2) migrate — the laptop DB predates scheduler_heartbeat (and any newer ops/aws-migration heads)
$COMPOSE run --rm --no-deps backend alembic upgrade head

# 3) factor catch-up so the first EC2 rebalance ranks on fresh prices (then the daily timer keeps it)
bash "$APP/app/deploy/aws/factor-refresh.sh" || echo "WARN: factor-refresh failed — fix before the next rebalance"

# 4) ARM — and only this host: rebuild the stack with Alpaca + scheduler ON (provisioner reuses SSM)
WORKBENCH_ALPACA_STARTUP_ENABLED=true WORKBENCH_SCHEDULER_ENABLED=true \
  bash "$APP/app/deploy/aws/provision-from-s3.sh"

# 5) VERIFY exactly one armed host + sane state
sleep 25
echo "=== healthz ==="; curl -fsS http://127.0.0.1:8000/healthz; echo
echo "=== single-armed-host check (expect exit 0) ==="
python3 "$APP/app/scripts/scheduler_health_check.py" --db "$APP/data/workbench.sqlite"; echo "exit=$?"
echo "=== DB identity ==="
$COMPOSE exec -T backend python - <<'PY'
import sqlite3
c=sqlite3.connect("/app/data/workbench.sqlite")
print("strategies:", c.execute("SELECT count(*) FROM strategies").fetchone()[0],
      "| accounts:", c.execute("SELECT count(*) FROM accounts").fetchone()[0])
for r in c.execute("SELECT id,name,status,schedule FROM strategies ORDER BY id"): print("  ", r)
c.close()
PY
echo "### cutover ARM complete — watch one cycle, then the laptop is the warm standby ###"
