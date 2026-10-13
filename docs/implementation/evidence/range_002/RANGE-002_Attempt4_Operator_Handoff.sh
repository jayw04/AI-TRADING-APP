#!/usr/bin/env bash
# RANGE-002 2016-Q1 descriptive diagnostic: attempt 4 operator handoff (one script, four modes).
#
#   PRICE_TOLERANCE=0.05 PRICE_MAX_MISMATCH_FRACTION=0.10 bash RANGE-002_Attempt4_Operator_Handoff.sh run
#   bash RANGE-002_Attempt4_Operator_Handoff.sh preflight | status | collect
#
# Run on the AWS box (ec2-paper) as a user with sudo/docker. Nothing here deploys the
# application, restarts a service, places an order or touches the holdout. It is read-only
# against the Sharadar export and writes only under /opt/workbench/data/research/range002_run
# (store, journal, outputs) and range002_registry (the run row).
#
# The two price-consistency settings are PROPOSED data-quality settings (not part of the frozen
# baseline). They have NO defaults: Jay sets them before the run, and they are not tuned after
# candidate performance is seen. The check cannot prove issuer identity.
#
# Credentials: the Alpaca key/secret are read from the existing backend container environment
# (the platform's configuration) into this process's environment only, never printed, never
# written to a file, and passed to the one-off container by name.
set -euo pipefail
umask 022
set +x

MODE="${1:-}"
CODE_SHA=d0a166f12024dd96892ed544245d1a577553989f
IMAGE=trading-workbench-backend
NAME=range002-run-2016q1-a4
BUNDLE_TGZ=/tmp/s1/bundle7.tgz
BUNDLE_TGZ_SHA=c97d55d0615801d80c98fcc11b03d7d604cf7af53e2108dd33086c63d7d92d92
BUNDLE_DIR=/tmp/s1/bundle
REL=docs/implementation/evidence/range_002
SPEC_REL=$REL/RANGE-002_Screen_Spec_Frozen_2016Q1_v0.4.json
SPEC_FILE_SHA=e460d8afc284279087d213390051f2dc6111be13ce6b73793051600003993974
LEDGER_REL=$REL/RANGE-002_exposure_ledger_2026-10-13_rev4.json
LEDGER_FILE_SHA=0649c7120d40413bf68a959a822186f27b835597edcc1842d26b4a3555469f0c
RECORD_REL=$REL/RANGE-002_Owner_Instruction_Record_2026-10-13_rev4.md
RECORD_FILE_SHA=864fbeb97199d379701c10d8126d97c2f13fb0621b439159f4a17324a667132d
MANIFEST_REL=$REL/RANGE-002_governance_manifest.json
MANIFEST_FILE_SHA=c9b7a4304f58890b73d75dcea3ddf660db749adab753acc07e22c37495c1cf89
RUNNER_REL=apps/backend/scripts/research/range002/run_descriptive_screen.py
RUNNER_FILE_SHA=3e63927e1332f39e26230dc965d05512b559767bdd951c52b19f4dfdad334c21
MAPPING_HOST=/opt/workbench/data/research/range002_run/symbol_mapping_2016q1_v3.json
MAPPING_SHA=78a1f5756bef79c920b319f34ababb95438c00f63a7d4c3e11ce0d8edd94077d
UNIVERSE_HOST=/opt/workbench/data/research/range002_s1/universe-2016q1-20261013/universe_symbols.txt
UNIVERSE_SHA=d00c48a33d6a632a39742afb01782508367f1153b98c892576afd54b022bee5c
EXPECTED_SPEC_SHA256=d209c14263aabcd7806f60e8aa809dd1e3f17777f30a5bd0ab7d5838ff21071e
RUN_DIR=/opt/workbench/data/research/range002_run
STORE_HOST=$RUN_DIR/minute_bars_2016q1_a4.duckdb
JOURNAL_HOST=$RUN_DIR/sip_journal_2016q1_a4.jsonl
OUT_HOST=$RUN_DIR/out_2016q1_a4

die() { echo "PREFLIGHT FAILED: $*" >&2; exit 2; }
check_sha() { # file expected label
  local got
  got="$(sudo sha256sum "$1" | cut -d' ' -f1)"
  [ "$got" = "$2" ] || die "$3: sha256 $got != expected $2"
  echo "ok  $3"
}

preflight() {
  [ -n "${PRICE_TOLERANCE:-}" ] && [ -n "${PRICE_MAX_MISMATCH_FRACTION:-}" ] || \
    die "set PRICE_TOLERANCE and PRICE_MAX_MISMATCH_FRACTION explicitly (proposed 0.05 and 0.10)"
  echo "price-consistency settings (proposed, not baseline): tolerance=$PRICE_TOLERANCE max_mismatch_fraction=$PRICE_MAX_MISMATCH_FRACTION"

  # 1. hashes: bundle archive, the files inside it, mapping, universe
  check_sha "$BUNDLE_TGZ" "$BUNDLE_TGZ_SHA" "bundle archive"
  check_sha "$BUNDLE_DIR/$SPEC_REL" "$SPEC_FILE_SHA" "frozen spec file"
  check_sha "$BUNDLE_DIR/$LEDGER_REL" "$LEDGER_FILE_SHA" "exposure ledger file"
  check_sha "$BUNDLE_DIR/$RECORD_REL" "$RECORD_FILE_SHA" "owner-instruction record"
  check_sha "$BUNDLE_DIR/$MANIFEST_REL" "$MANIFEST_FILE_SHA" "governance manifest"
  check_sha "$BUNDLE_DIR/$RUNNER_REL" "$RUNNER_FILE_SHA" "runner script"
  check_sha "$MAPPING_HOST" "$MAPPING_SHA" "symbol mapping"
  check_sha "$UNIVERSE_HOST" "$UNIVERSE_SHA" "fetch universe"
  grep -q "\"spec_sha256\": \"$EXPECTED_SPEC_SHA256\"" "$BUNDLE_DIR/$SPEC_REL" || \
    die "spec file does not carry spec_sha256 $EXPECTED_SPEC_SHA256"
  echo "ok  spec_sha256 $EXPECTED_SPEC_SHA256"

  # 2. registry: exactly three consumed attempts, no active run
  sudo docker run --rm -i --entrypoint python \
    -v /opt/workbench/data/research/range002_registry:/app/data/research/range002_registry:ro \
    -v "$BUNDLE_DIR":/work:ro "$IMAGE" -I - <<'PY'
import sys
sys.path.insert(0, "/work/apps/backend")
from pathlib import Path
from app.research.range002.governance.run_registry import RunRegistry, RunStatus

runs = RunRegistry(Path("/app/data/research/range002_registry/range002_runs.jsonl")).runs()
issued = [r for r in runs if r.capability_issued_seq is not None]
active = [r for r in runs if r.status is RunStatus.OPEN]
print(f"registry: runs={len(runs)} capability_issued={len(issued)} open={len(active)}")
if len(issued) != 3 or active:
    print("expected exactly 3 consumed attempts and no active run", file=sys.stderr)
    sys.exit(2)
PY
  echo "ok  registry shows three consumed attempts, no active run"

  # 3. fresh a4 paths, no leftover container, writable destination, disk space
  for p in "$STORE_HOST" "$JOURNAL_HOST" "$OUT_HOST"; do
    sudo test ! -e "$p" || die "$p already exists (attempt 4 paths must be fresh)"
  done
  [ -z "$(sudo docker ps -a --filter "name=^${NAME}$" --format '{{.Names}}')" ] || \
    die "container $NAME already exists"
  sudo touch "$RUN_DIR/.a4-write-probe" && sudo rm -f "$RUN_DIR/.a4-write-probe" || \
    die "$RUN_DIR is not writable"
  sudo test -w /opt/workbench/data/research/range002_registry || die "registry directory is not writable"
  local avail
  avail="$(df -B1 --output=avail /opt/workbench/data | tail -1 | tr -d ' ')"
  [ "$avail" -ge $((2 * 1024 * 1024 * 1024)) ] || die "less than 2 GiB free on /opt/workbench/data"
  echo "ok  fresh a4 paths, writable research destinations, free space $((avail / 1048576)) MiB"
}

launch() {
  local key secret
  key="$(sudo docker inspect workbench-backend --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^ALPACA_PAPER_6_API_KEY=' | cut -d= -f2-)"
  secret="$(sudo docker inspect workbench-backend --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^ALPACA_PAPER_6_API_SECRET=' | cut -d= -f2-)"
  [ -n "$key" ] && [ -n "$secret" ] || die "SIP credentials are not present in the backend container environment"
  export ALPACA_PAPER_6_API_KEY="$key" ALPACA_PAPER_6_API_SECRET="$secret"
  unset key secret
  sudo --preserve-env=ALPACA_PAPER_6_API_KEY,ALPACA_PAPER_6_API_SECRET \
    docker run -d --name "$NAME" --entrypoint python \
    -e ALPACA_PAPER_6_API_KEY -e ALPACA_PAPER_6_API_SECRET \
    -v /opt/workbench/data/research/range002_s1:/app/data/research/range002_s1:ro \
    -v /opt/workbench/data/research/range002_registry:/app/data/research/range002_registry:rw \
    -v /opt/workbench/data/research/range002_run:/app/data/research/range002_run:rw \
    -v "$BUNDLE_DIR":/work:ro \
    "$IMAGE" -I /work/apps/backend/scripts/research/range002/run_descriptive_screen.py \
    --spec "/work/$SPEC_REL" \
    --registry /app/data/research/range002_registry/range002_runs.jsonl \
    --exposure-ledger "/work/$LEDGER_REL" \
    --daily-snapshot /app/data/research/range002_s1/sharadar-2016q1-20261013 \
    --snapshot-manifest /app/data/research/range002_run/snapshot_manifest_v2_accepted.json \
    --minute-bars /app/data/research/range002_run/minute_bars_2016q1_a4.duckdb \
    --minute-feed sip --minute-ts-convention start \
    --date-start 2016-01-01 --date-end 2016-03-31 \
    --partition DEVELOPMENT_SELECTION --table-filter SEP \
    --lookback-calendar-days 45 --coverage-threshold 0.98 \
    --equity 100000 --tick 0.01 --code-sha "$CODE_SHA" \
    --out-dir /app/data/research/range002_run/out_2016q1_a4 \
    --raw-vendor-rows-attested \
    --allow-sequential-pulls-ref "owner-instruction-2026-10-13:RANGE-002_Owner_Instruction_Record_2026-10-13_rev4.md" \
    --delisting-action-value delisted \
    --fetch-bars \
    --fetch-universe-sha256 "$UNIVERSE_SHA" \
    --fetch-symbol-map /app/data/research/range002_run/symbol_mapping_2016q1_v3.json \
    --fetch-symbol-map-sha256 "$MAPPING_SHA" \
    --fetch-journal /app/data/research/range002_run/sip_journal_2016q1_a4.jsonl \
    --fetch-key-env ALPACA_PAPER_6_API_KEY --fetch-secret-env ALPACA_PAPER_6_API_SECRET \
    --fetch-requests-per-minute 150 --fetch-max-requests 2500 --fetch-asof - \
    --fetch-authorization-id AUTH-RANGE002-2016Q1-20261013-A4 \
    --fetch-permitted-use-ref "owner statement 2026-10-13: personal research use (claimed, not verified)" \
    --fetch-entitlement-ref "ALPACA_PAPER_6 key: SIP-entitled per 2026-10-12 probe (claimed)" \
    --fetch-permission-basis-claimed "owner reading: storage permitted by absence of prohibition for personal use on the owner's personal AWS account (claimed, not verified)" \
    --fetch-storage-permitted \
    --fetch-price-tolerance "$PRICE_TOLERANCE" \
    --fetch-price-max-mismatch-fraction "$PRICE_MAX_MISMATCH_FRACTION"
  unset ALPACA_PAPER_6_API_KEY ALPACA_PAPER_6_API_SECRET
  echo "launched container $NAME (attempt 4); use: bash $0 status"
}

status() {
  sudo docker inspect -f 'running={{.State.Running}} exit={{.State.ExitCode}} started={{.State.StartedAt}} finished={{.State.FinishedAt}}' "$NAME"
  echo "--- last log lines (statuses only; credentials are never logged)"
  sudo docker logs --tail 20 "$NAME" 2>&1 | cut -c1-300
}

wait_done() {
  for _ in $(seq 1 240); do   # up to 60 minutes
    [ "$(sudo docker inspect -f '{{.State.Running}}' "$NAME")" = "false" ] && return 0
    sleep 15
  done
  echo "still running after 60 minutes; use 'status' later" >&2
  return 1
}

collect() {
  echo "--- exit status"
  sudo docker inspect -f 'exit={{.State.ExitCode}} (0 = report written, 2 = refused or aborted, 3 = report with a data-quality DEFECT)' "$NAME"
  echo "--- run log"
  sudo docker logs "$NAME" 2>&1 | cut -c1-400 | tail -30
  echo "--- evidence and report files (kept; nothing is deleted)"
  sudo ls -la "$OUT_HOST" 2>/dev/null || echo "(no output directory: the run was refused before writing)"
  sudo sha256sum "$OUT_HOST"/* 2>/dev/null | cut -c1-100 || true
  echo "--- journal and store"
  sudo ls -la "$JOURNAL_HOST" "$STORE_HOST" 2>/dev/null || true
  echo "Report and evidence stay on the box under $OUT_HOST (private to Jay; PU-1 sidecars apply)."
  echo "Do NOT start another run automatically: a failed attempt is closed and kept as evidence."
}

case "$MODE" in
  preflight) preflight ;;
  run)       preflight; launch; wait_done || true; collect ;;
  status)    status ;;
  collect)   collect ;;
  *) echo "usage: [PRICE_TOLERANCE=.. PRICE_MAX_MISMATCH_FRACTION=..] bash $0 preflight|run|status|collect" >&2; exit 64 ;;
esac
