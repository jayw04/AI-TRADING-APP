#!/usr/bin/env bash
# Daily incremental Sharadar SEP refresh for the LIVE factor store (ADR 0032 migration).
#
# WHY: the factor books (momentum / sector-rotation / low-volatility / combined-book) RANK on
# data/factor_data.duckdb via ctx.factors. The only existing ingest is a one-time back-fill with
# --skip-existing into a SEPARATE file, so recent bars are never pulled and the live store silently
# goes stale (found 2026-06-30: sep prices ~18 days old). Live Alpaca bars keep SIZING fresh, but
# the SELECTION drifts. This job keeps the live store current — the piece the laptop never had.
#
# HOW: ingest_sharadar.py upserts sep by (ticker,date) (INSERT OR REPLACE), so an incremental is just
# a recent-bars pull (no --skip-existing) bounded by --from-date. The backend holds the DuckDB file
# read-only, so we ingest into a STAGING copy (backend stays up), then take the shortest possible
# downtime for an atomic swap + restart (resume-on-boot re-registers strategies).
#
# SCHEDULE: pre-market on trading days (e.g. 06:00 ET) via systemd timer / cron — see
# Docs/runbook/aws-migration.md. PREREQS: NASDAQ_DATA_LINK_API_KEY in SSM /workbench/prod/* (+ the
# env-build fetches it), and survivorship_pool.txt present in the data dir.
set -euo pipefail

APP=/opt/workbench/app
DATADIR=/opt/workbench/data                 # mounted into the container at /app/data
LIVE="$DATADIR/factor_data.duckdb"
STAGE="$DATADIR/factor_data.staging.duckdb"
UNIVERSE_FILE="/app/data/_factor_refresh_universe.txt"
LOOKBACK_DAYS="${LOOKBACK_DAYS:-20}"
FROM="$(date -u -d "-${LOOKBACK_DAYS} days" +%Y-%m-%d)"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

log(){ echo "[factor-refresh $(date -u +%FT%TZ)] $*"; }
cd "$APP"

[ -f "$LIVE" ] || { log "FATAL: live store $LIVE missing (seed it at cutover)"; exit 1; }

# 1) snapshot live -> staging (backend keeps serving from LIVE; read-copy is safe)
cp -f "$LIVE" "$STAGE"
log "staged a copy of the live store"

# 1b) derive the refresh UNIVERSE from the LIVE books (union of active strategy symbols) — NOT the
#     14k survivorship pool, which is for one-time back-fill. Keeps the daily pull to a few hundred
#     tickers (the books only rank over their own universes), well under Sharadar's daily cap.
$COMPOSE run --rm --no-deps backend python - <<'PYEOF'
import sqlite3, json
c = sqlite3.connect("/app/data/workbench.sqlite"); u = set()
for (s,) in c.execute("SELECT symbols_json FROM strategies WHERE status='PAPER'"):
    u |= set(json.loads(s or "[]"))
with open("/app/data/_factor_refresh_universe.txt", "w") as f:
    f.write("\n".join(sorted(x for x in u if x)))
print("refresh universe tickers:", len(u))
c.close()
PYEOF
log "derived refresh universe from the live books"

# 2) incremental upsert of recent SEP (+ corporate actions) into STAGING, via a one-off container
#    that reuses the backend image (has ingest_sharadar.py, deps, and the .env / Nasdaq key).
$COMPOSE run --rm --no-deps \
  -e WORKBENCH_FACTOR_DATA_DB_PATH=/app/data/factor_data.staging.duckdb \
  backend python scripts/ingest_sharadar.py \
    --tickers-file "$UNIVERSE_FILE" \
    --datasets sep,actions --from-date "$FROM"
log "ingested SEP/actions since ${FROM} into staging"

# 3) shortest-downtime atomic swap
$COMPOSE stop backend
mv -f "$STAGE" "$LIVE"
$COMPOSE start backend
log "swapped staging -> live; backend restarting"

# 4) verify the data advanced + the backend is healthy
sleep 20
$COMPOSE exec -T backend python - <<'PY' || true
import duckdb
c = duckdb.connect('/app/data/factor_data.duckdb', read_only=True)
print("sep max date after refresh:", c.execute("SELECT max(date) FROM sep").fetchone()[0])
c.close()
PY
if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
  log "OK: backend healthy after factor refresh"
else
  log "WARN: backend not healthy yet after refresh — check logs"
fi
