#!/usr/bin/env bash
# RANGE-002 2017-H1 ACQUISITION + VALIDATION (phase ACQ: consumes NO P3A attempt, no strategy capability).
#   bash RANGE-002_2017H1_Acquisition_Handoff.sh preflight | run | status | collect
# Hard SIP request cap: 2,500 TOTAL including the 17 mapping probes already used (journal cap 2,483).
# Credentials come from the backend container environment into this process only (never printed).
set -euo pipefail
umask 022
set +x
MODE="${1:-}"
CODE_SHA=79d928fd0f593d6beb30ccfac0d3397d3cd5f42a
IMAGE=trading-workbench-backend
NAME=range002-acq-2017h1
BUNDLE_TGZ=/tmp/s1/bundle17.tgz
BUNDLE_TGZ_SHA=f6275d82afd72d06eb2e170bd7c032c78d06bf728a318b6bf5d987f4651e577d
BUNDLE_DIR=/tmp/s1/bundle17
REL=docs/implementation/evidence/range_002
SPEC_REL=$REL/RANGE-002_Screen_Spec_Frozen_CostAware_v0.6.json
SPEC_FILE_SHA=b06846ece79d976860db4d1e0f5e9a4774caccbb1a900107c4943b88a0a48c07
EXPECTED_SPEC_SHA256=5e88071d37fb77e1b9b25bd5081339eecf6bceaf0fff9eebf661c7ed122bcf71
LEDGER_REL=$REL/RANGE-002_exposure_ledger_2026-10-13_rev7_planned.json
LEDGER_FILE_SHA=a10abd3d0fcb2c546b7d017200028c13e29cab7115125db70a722b10e680d0d2
RECORD_REL=$REL/RANGE-002_Owner_Instruction_Record_2026-10-13_rev7.md
RECORD_FILE_SHA=dbbb0471031df701d683c7a4a3a029ec6510b5f5b067012ff5fe5b935e5ccb3e
RUNNER_REL=apps/backend/scripts/research/range002/run_descriptive_screen.py
RUNNER_FILE_SHA=7ddd9a5301bd4dab4c05fe83f381f89890f73995163c1d760869c550b3e8950c
RUN_DIR=/opt/workbench/data/research/range002_run
S1=/opt/workbench/data/research/range002_s1
MAPPING_HOST=$RUN_DIR/symbol_mapping_2017h1.json
MAPPING_SHA=a1ae363686a73aba6afab193c91ba10a6b50479072fd18b97b58a21ae6adfe78
UNIVERSE_HOST=$S1/universe-2017h1-20261013/universe_symbols.txt
UNIVERSE_SHA=5c1b4835e5e1b6e4918d6be2bc35be88f7636192ef6725babe2c93dc2f12e351
SNAP_MANIFEST_HOST=$RUN_DIR/snapshot_manifest_2017h1_accepted.json
SNAP_MANIFEST_SHA=97bf0501a60447d313e8ba0d469097747a26681cea0cece29bc83c62a3039501
STORE_HOST=$RUN_DIR/minute_bars_2017h1.duckdb
JOURNAL_HOST=$RUN_DIR/sip_journal_2017h1.jsonl
OUT_HOST=$RUN_DIR/out_2017h1_acq
MAX_REQUESTS=2483   # 2,500 hard cap minus 17 mapping probes already made
PRICE_TOLERANCE=0.05
PRICE_MAX_MISMATCH_FRACTION=0.10

die() { echo "PREFLIGHT FAILED: $*" >&2; exit 2; }
check_sha() { local got; got="$(sudo sha256sum "$1" | cut -d' ' -f1)"; [ "$got" = "$2" ] || die "$3: $got != $2"; echo "ok  $3"; }

preflight() {
  check_sha "$BUNDLE_TGZ" "$BUNDLE_TGZ_SHA" "bundle archive"
  check_sha "$BUNDLE_DIR/$SPEC_REL" "$SPEC_FILE_SHA" "frozen spec file"
  check_sha "$BUNDLE_DIR/$LEDGER_REL" "$LEDGER_FILE_SHA" "exposure ledger rev7"
  check_sha "$BUNDLE_DIR/$RECORD_REL" "$RECORD_FILE_SHA" "owner-instruction record rev7"
  check_sha "$BUNDLE_DIR/$RUNNER_REL" "$RUNNER_FILE_SHA" "runner"
  check_sha "$MAPPING_HOST" "$MAPPING_SHA" "symbol mapping"
  check_sha "$UNIVERSE_HOST" "$UNIVERSE_SHA" "fetch universe"
  check_sha "$SNAP_MANIFEST_HOST" "$SNAP_MANIFEST_SHA" "snapshot manifest"
  grep -q "\"spec_sha256\": \"$EXPECTED_SPEC_SHA256\"" "$BUNDLE_DIR/$SPEC_REL" || die "spec hash"
  sudo docker run --rm -i --network none --entrypoint python \
    -v /opt/workbench/data/research/range002_registry:/app/data/research/range002_registry:ro \
    -v "$BUNDLE_DIR":/work:ro "$IMAGE" -I - <<'PY'
import sys
sys.path.insert(0, "/work/apps/backend")
from pathlib import Path
from app.research.range002.governance.run_registry import RunRegistry, RunStatus
runs = RunRegistry(Path("/app/data/research/range002_registry/range002_runs.jsonl")).runs()
att = [r for r in runs if r.phase.value in ("P3A", "P3B") and r.capability_issued_seq is not None]
active = [r for r in runs if r.status is RunStatus.OPEN]
print(f"registry: runs={len(runs)} attempts_consumed={len(att)} open={len(active)}")
if len(att) != 4 or active:
    print("expected exactly 4 consumed attempts and no active run", file=sys.stderr)
    sys.exit(2)
PY
  for p in "$STORE_HOST" "$JOURNAL_HOST" "$OUT_HOST"; do sudo test ! -e "$p" || die "$p exists (fresh paths required)"; done
  [ -z "$(sudo docker ps -a --filter "name=^${NAME}$" --format '{{.Names}}')" ] || die "container exists"
  local avail
  avail="$(df -B1 --output=avail /opt/workbench/data | tail -1 | tr -d ' ')"
  [ "$avail" -ge $((3 * 1024 * 1024 * 1024)) ] || die "less than 3 GiB free"
  echo "ok  four consumed attempts, no active run, fresh paths, free space $((avail / 1048576)) MiB"
}

launch() {
  local key secret
  key="$(sudo docker inspect workbench-backend --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^ALPACA_PAPER_6_API_KEY=' | cut -d= -f2-)"
  secret="$(sudo docker inspect workbench-backend --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^ALPACA_PAPER_6_API_SECRET=' | cut -d= -f2-)"
  [ -n "$key" ] && [ -n "$secret" ] || die "SIP credentials not present"
  export ALPACA_PAPER_6_API_KEY="$key" ALPACA_PAPER_6_API_SECRET="$secret"
  unset key secret
  sudo --preserve-env=ALPACA_PAPER_6_API_KEY,ALPACA_PAPER_6_API_SECRET \
    docker run -d --name "$NAME" --entrypoint python \
    -e ALPACA_PAPER_6_API_KEY -e ALPACA_PAPER_6_API_SECRET \
    -v $S1:/app/data/research/range002_s1:ro \
    -v /opt/workbench/data/research/range002_registry:/app/data/research/range002_registry:rw \
    -v $RUN_DIR:/app/data/research/range002_run:rw -v "$BUNDLE_DIR":/work:ro \
    "$IMAGE" -I /work/$RUNNER_REL \
    --spec "/work/$SPEC_REL" --registry /app/data/research/range002_registry/range002_runs.jsonl \
    --exposure-ledger "/work/$LEDGER_REL" \
    --daily-snapshot /app/data/research/range002_s1/sharadar-2017h1-20261013 \
    --snapshot-manifest /app/data/research/range002_run/snapshot_manifest_2017h1_accepted.json \
    --minute-bars /app/data/research/range002_run/minute_bars_2017h1.duckdb \
    --minute-feed sip --minute-ts-convention start \
    --date-start 2017-01-01 --date-end 2017-06-30 \
    --partition ACQUISITION --table-filter SEP \
    --lookback-calendar-days 45 --coverage-threshold 0.98 --or-completeness-threshold 0.98 \
    --equity 100000 --tick 0.01 --code-sha "$CODE_SHA" \
    --out-dir /app/data/research/range002_run/out_2017h1_acq \
    --raw-vendor-rows-attested \
    --allow-sequential-pulls-ref "owner-instruction-2026-10-13:RANGE-002_Owner_Instruction_Record_2026-10-13_rev7.md" \
    --delisting-action-value delisted \
    --fetch-bars --fetch-universe-sha256 "$UNIVERSE_SHA" \
    --fetch-symbol-map /app/data/research/range002_run/symbol_mapping_2017h1.json \
    --fetch-symbol-map-sha256 "$MAPPING_SHA" \
    --fetch-journal /app/data/research/range002_run/sip_journal_2017h1.jsonl \
    --fetch-key-env ALPACA_PAPER_6_API_KEY --fetch-secret-env ALPACA_PAPER_6_API_SECRET \
    --fetch-requests-per-minute 150 --fetch-max-requests "$MAX_REQUESTS" --fetch-asof - \
    --fetch-authorization-id AUTH-RANGE002-2017H1-20261013-ACQ \
    --fetch-permitted-use-ref "owner statement 2026-10-13: personal research use (claimed, not verified)" \
    --fetch-entitlement-ref "ALPACA_PAPER_6 key: SIP-entitled per 2026-10-12 probe (claimed)" \
    --fetch-permission-basis-claimed "owner reading: storage permitted by absence of prohibition for personal use on the owner's personal AWS account (claimed, not verified)" \
    --fetch-storage-permitted \
    --fetch-price-tolerance "$PRICE_TOLERANCE" --fetch-price-max-mismatch-fraction "$PRICE_MAX_MISMATCH_FRACTION"
  unset ALPACA_PAPER_6_API_KEY ALPACA_PAPER_6_API_SECRET
  echo "launched $NAME (phase ACQ; no attempt)"
}

status() {
  sudo docker inspect -f 'running={{.State.Running}} exit={{.State.ExitCode}}' "$NAME"
  sudo docker logs --tail 20 "$NAME" 2>&1 | cut -c1-300
}

wait_done() {
  for _ in $(seq 1 240); do
    [ "$(sudo docker inspect -f '{{.State.Running}}' "$NAME")" = "false" ] && return 0
    sleep 15
  done
  return 1
}

collect() {
  sudo docker inspect -f 'exit={{.State.ExitCode}} (0 = validated, 3 = prerequisite defect, 2 = refused or aborted)' "$NAME"
  sudo docker logs "$NAME" 2>&1 | cut -c1-400 | tail -20
  sudo ls -la "$OUT_HOST" 2>/dev/null || echo "(no output directory)"
  sudo sha256sum "$OUT_HOST"/* 2>/dev/null | cut -c1-100 || true
}

case "$MODE" in
  preflight) preflight ;;
  run) preflight; launch; wait_done || true; collect ;;
  status) status ;;
  collect) collect ;;
  *) echo "usage: bash $0 preflight|run|status|collect" >&2; exit 64 ;;
esac
