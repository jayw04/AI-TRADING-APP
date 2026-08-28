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

# One-off refresh container only. The corrected scripts/factor_refresh.py is baked into the image
# (Dockerfile: COPY scripts ./scripts) and is not bind-mounted, so a deployed image built before
# the file existed cannot run it. The override maps that ONE file, read-only, into the throwaway
# container — it must never reach the stop/start/exec calls below, which operate on the
# long-running backend and must see the image exactly as built.
COMPOSE_REFRESH="$COMPOSE -f deploy/aws/docker-compose.factor-refresh.yml"

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
$COMPOSE_REFRESH run --rm --no-deps backend python scripts/factor_refresh.py universe \
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

# 2a) REGENERATE the exhaustion evidence artifact from what this run actually observed.
#
#     ⚠ THIS STEP DECIDES NOTHING. It writes observations — was the symbol in the list handed
#     to the ingest, how did that ingest exit, how many rows did the provider deliver past the
#     live frontier, and what does an INDEPENDENT source say about the symbol and about a
#     control symbol probed on the same call. `factor_refresh.py verify` re-derives every
#     verdict from those observations using the shared adjudicator; the artifact cannot talk
#     the gate into anything.
#
#     WHY IT IS HERE. Until 2026-08-27 nothing in the repository wrote this artifact. The
#     production copy was hand-built once, on 2026-08-11, holding eleven records. A name that
#     went attributable-stale afterwards therefore had NO record and adjudicated
#     FAILED_OR_UNEXPLAINED, aborting the swap: EA needed a human on 08-17, and WBS halted the
#     refresh on 08-25, 08-26 and 08-27, freezing the live store at SEP 2026-08-21. Worse, all
#     eleven records shared one observation timestamp, so with MAX_EVIDENCE_AGE_DAYS=30 they
#     were due to expire TOGETHER on 2026-09-10 and the refresh would then have failed on
#     eleven names instead of one. A control refreshed by remembering to refresh it is a
#     control with a human in the hot path of every market day.
#
#     ⚠ A FAILURE HERE IS NOT AN ABORT. The verifier is the gate and is fail-closed on a
#     missing, unreadable or expired artifact, so a failed regeneration surfaces as a verify
#     failure with a diagnosis rather than as a second, earlier exit whose meaning an operator
#     would have to learn separately. The `|| log ...` tail is therefore deliberate rather
#     than defensive — it absorbs the non-zero exit that `set -e` would otherwise turn into an
#     abort, so the step is allowed to fail and the NEXT step is what refuses to promote.
#
#     ⚠ NO SYMBOL IS NAMED ANYWHERE IN THIS FILE. Every name — EA, WBS, and whatever the next
#     one is — reaches a verdict through evidence and adjudication. A ticker literal in this
#     path would be an exemption nobody could audit; check_no_factor_symbol_special_cases.sh
#     fails the build on one.
#
#     `--ingest-status` is left at its default `ok` and NOT computed from the ingest's exit
#     code, because `set -e` is in force above: a non-zero ingest has already exited the
#     script, so this line is only ever reached after a successful one. Capturing `$?` here
#     would suggest a failure path that cannot occur and would read as handling something it
#     does not. The parameter exists for reruns driven by hand, where the operator knows.
$COMPOSE_REFRESH run --rm --no-deps backend python scripts/factor_evidence.py generate \
    --live     /app/data/factor_data.duckdb \
    --stage    /app/data/factor_data.staging.duckdb \
    --universe "$UNIVERSE_FILE" \
    --app-db   /app/data/workbench.sqlite \
    --out      /app/data/_factor_exhaustion_evidence.json \
  || log "WARN: evidence regeneration FAILED — verification will fail closed on the stale artifact and report why"

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
if ! $COMPOSE_REFRESH run --rm --no-deps backend python scripts/factor_refresh.py verify \
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
