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
# read-only, so we ingest into a STAGING copy (backend stays up). Before the swap the staging store
# is VERIFIED against the current live (no sep_max regression, <10% ticker loss, lastpricedate>=sep);
# on failure the job ABORTS with the live store untouched. On success we retain a one-deep rollback
# (factor_data.prev.duckdb), then take the shortest possible downtime for the swap + restart
# (resume-on-boot re-registers strategies). A stale factor store is a silent allocation bug — so a
# bad refresh must never reach the live book, and a good store is always recoverable.
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

# 1b) derive the refresh UNIVERSE — NOT the 14k survivorship pool, which is for one-time back-fill.
#     ⚠ This used to be the union of `symbols_json` over status='PAPER' strategies, on the premise
#     (stated in the old comment) that "the books only rank over their own universes". That premise
#     is false and it silently froze 301 of 500 ranking names at 2026-07-06 while every readiness
#     gate reported green. A book calls momentum_scores(n=len(ctx.symbols)) -> universe_asof ->
#     dollar_volume_universe: the top-n **store-wide** by trailing dollar volume, with the registered
#     list applied afterwards as a filter. Unregistered names therefore decide which registered names
#     survive the cut, and dollar_volume_universe drops any name whose lastpricedate lags — so a
#     stale name vanishes from the pool rather than merely ranking on old data.
#     The universe is now (ranking pool x headroom) U (registered, ANY status) U (held) U (extras).
#     Status is deliberately unfiltered: a book pending activation needs fresh data BEFORE it is
#     activated, or its readiness gate can never go green. See apps/backend/scripts/factor_refresh.py.
$COMPOSE run --rm --no-deps backend python scripts/factor_refresh.py universe \
    --app-db /app/data/workbench.sqlite \
    --store  /app/data/factor_data.duckdb \
    --as-of  "$(date -u +%Y-%m-%d)" \
    --out    "$UNIVERSE_FILE" \
    --report /app/data/_factor_refresh_universe_report.json \
    --prior  /app/data/_factor_refresh_universe_sealed.json \
    --extra  SPY
log "derived refresh universe (ranking pool + registered + held)"

# 2) incremental upsert of recent SEP (+ corporate actions) into STAGING, via a one-off container
#    that reuses the backend image (has ingest_sharadar.py, deps, and the .env / Nasdaq key).
# Refresh sep + actions (prices) AND tickers (reference metadata). The tickers table's
# `lastpricedate` gates the point-in-time universe (dollar_volume_universe filters
# lastpricedate >= as_of), so if SEP prices advance PAST a stale lastpricedate the universe
# resolves EMPTY and every factor book HOLDS instead of rebalancing (incident 2026-07-06:
# refresh advanced SEP to 07-02 but tickers.lastpricedate stayed 06-12 -> all books held).
# Keep prices and tickers metadata in lockstep. (tickers is a full ref-table pull; it ignores
# --tickers-file/--from.)
$COMPOSE run --rm --no-deps \
  -e WORKBENCH_FACTOR_DATA_DB_PATH=/app/data/factor_data.staging.duckdb \
  backend python scripts/ingest_sharadar.py \
    --tickers-file "$UNIVERSE_FILE" \
    --datasets sep,actions,tickers --from "$FROM"
log "ingested SEP/actions/tickers since ${FROM} into staging"

# 2b) VERIFY the staging store BEFORE the swap — a bad refresh must NOT reach the live book.
#     A stale factor store is a silent allocation bug, so the swap is GATED: staging must not
#     regress vs the current live (sep_max backward, >10% tickers lost) and must be self-consistent
#     (tickers.lastpricedate >= sep, else the PIT universe empties and every book HOLDS — the
#     2026-07-06 incident). On any failure we ABORT: the live store is left untouched and the job
#     exits non-zero (systemd marks it failed; the daily report's >7d staleness check is the backstop).
#     ⚠ The global checks below are necessary but NOT sufficient: `max(date)` over the whole table
#     is not a freshness measure, because ONE current ticker keeps it green while the rest of the
#     pool is frozen — which is exactly what happened on 2026-07-06. The gate is therefore also
#     PER-DAY-PER-NAME over the refresh universe, and fails if coverage drops below the threshold or
#     if any universe name's tickers.lastpricedate lags (such a name is EXCLUDED from the ranking
#     pool outright, which is strictly worse than being ranked on stale data).
if ! $COMPOSE run --rm --no-deps backend python scripts/factor_refresh.py verify \
    --live     /app/data/factor_data.duckdb \
    --stage    /app/data/factor_data.staging.duckdb \
    --universe "$UNIVERSE_FILE" \
    --report   /app/data/_factor_refresh_verify_report.json
then
  log "ABORTED: staging verification FAILED — LIVE store left unchanged, refresh NOT applied. Investigate."
  rm -f "$STAGE"
  exit 1
fi
log "staging verified OK"

# 3) safe atomic swap: retain a one-deep rollback copy of the CURRENT live, then swap.
$COMPOSE stop backend
cp -f "$LIVE" "$DATADIR/factor_data.prev.duckdb"   # rollback point (last known-good store)
mv -f "$STAGE" "$LIVE"
$COMPOSE start backend
log "swapped staging -> live (rollback at factor_data.prev.duckdb); backend restarting"

# 3b) SEAL the universe report only now. The growth control compares against the last
#     SEALED SUCCESSFUL run, never the last attempt — if a failed refresh could advance
#     this file, one bad run would silently re-baseline the comparison and the next
#     expansion would measure against a set nobody accepted.
cp -f "$DATADIR/_factor_refresh_universe_report.json" \
      "$DATADIR/_factor_refresh_universe_sealed.json"
log "sealed the universe report as the new growth-comparison anchor"

# 4) post-swap health: backend up + the live store now reads what staging verified.
sleep 20
$COMPOSE exec -T backend python - <<'PY' || true
import duckdb
c = duckdb.connect('/app/data/factor_data.duckdb', read_only=True)
print("live sep max after swap:", c.execute("SELECT max(date) FROM sep").fetchone()[0],
      "| tickers.lastpricedate:", c.execute("SELECT max(lastpricedate) FROM tickers").fetchone()[0])
c.close()
PY
if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
  log "OK: backend healthy after factor refresh"
else
  log "WARN: backend not healthy yet after refresh — check logs"
fi
