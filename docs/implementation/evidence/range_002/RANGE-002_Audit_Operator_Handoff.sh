#!/usr/bin/env bash
# RANGE-002 2016-Q1 bounded AUDIT REPLAY of the completed run range002-run-000011 (one script, four modes).
#
#   bash RANGE-002_Audit_Operator_Handoff.sh preflight | run | status | collect
#
# Run on the AWS box (ec2-paper) as a user with sudo/docker. Nothing here fetches data (the
# container runs with --network none), deploys the application, restarts a service, places an
# order, changes a parameter, selects a candidate, reads another date range or touches the holdout.
# It consumes NO strategy attempt: it opens a distinct phase-AUDIT registry row under its own
# audit capability, bound to the completed parent's spec, code, data and report digests, and it
# refuses any altered input. It writes only to a NEW audit directory and one append-only audit
# log; the parent's report, store, journal and evidence are mounted read-only.
set -euo pipefail
umask 022
set +x

MODE="${1:-}"
IMAGE=trading-workbench-backend
NAME=range002-audit-2016q1-a4
PARENT_RUN_ID=range002-run-000011
AUDIT_ID=AUDIT-RANGE002-2016Q1-20261013-A4R
PARENT_CODE_SHA=567742649daedb56da17fb4ef5c2ae80458846d9
BUNDLE_TGZ=/tmp/s1/bundle9.tgz
BUNDLE_TGZ_SHA=50f3a452bab921dad024e60b6e56cba33b83552a1e01688a3502b7936d44e79e
BUNDLE_DIR=/tmp/s1/bundle9
REL=docs/implementation/evidence/range_002
SPEC_REL=$REL/RANGE-002_Screen_Spec_Frozen_2016Q1_v0.5.json
SPEC_FILE_SHA=f3d7a4dc03e7d676f107e87f6928c5c1b24ef5a09d89335290cb1317f6d28d5d
RECORD_REL=$REL/RANGE-002_Owner_Instruction_Record_2026-10-13_rev5.md
RECORD_FILE_SHA=9ced1413fd0eb618778ae864d6ac8133619ecc9548f4f11eca37dd92b7432bfd
MANIFEST_REL=$REL/RANGE-002_governance_manifest.json
MANIFEST_FILE_SHA=c9b7a4304f58890b73d75dcea3ddf660db749adab753acc07e22c37495c1cf89
AUDIT_TOOL_REL=apps/backend/scripts/research/range002/audit_replay_run.py
AUDIT_TOOL_FILE_SHA=673a17dc42f28f33003e4c6feb3c55345f5c03abc3d1c10d52226c77e3cd5019
MAPPING_HOST=/opt/workbench/data/research/range002_run/symbol_mapping_2016q1_v3.json
MAPPING_SHA=78a1f5756bef79c920b319f34ababb95438c00f63a7d4c3e11ce0d8edd94077d
UNIVERSE_HOST=/opt/workbench/data/research/range002_s1/universe-2016q1-20261013/universe_symbols.txt
UNIVERSE_SHA=d00c48a33d6a632a39742afb01782508367f1153b98c892576afd54b022bee5c
PARENT_REPORT_SHA=44e712290fff3b278e84d1d3f6e043344eab37ef23961b0bb9fa88cac4da39c0
EXPECTED_SPEC_SHA256=84dc328eb4b063a500dedb72766450c366e779ba2c225284a77be37d54018e08
RUN_DIR=/opt/workbench/data/research/range002_run
PARENT_OUT=$RUN_DIR/out_2016q1_a4
STORE_HOST=$RUN_DIR/minute_bars_2016q1_a4.duckdb
AUDIT_OUT=$RUN_DIR/out_2016q1_a4_audit
AUDIT_LOG=/opt/workbench/data/research/range002_registry/range002_audit_log.jsonl

die() { echo "PREFLIGHT FAILED: $*" >&2; exit 2; }
check_sha() { # file expected label
  local got
  got="$(sudo sha256sum "$1" | cut -d' ' -f1)"
  [ "$got" = "$2" ] || die "$3: sha256 $got != expected $2"
  echo "ok  $3"
}

preflight() {
  check_sha "$BUNDLE_TGZ" "$BUNDLE_TGZ_SHA" "bundle archive"
  sudo test -d "$BUNDLE_DIR" || die "$BUNDLE_DIR is not unpacked (tar xzf $BUNDLE_TGZ -C $BUNDLE_DIR)"
  check_sha "$BUNDLE_DIR/$SPEC_REL" "$SPEC_FILE_SHA" "frozen spec file"
  check_sha "$BUNDLE_DIR/$RECORD_REL" "$RECORD_FILE_SHA" "owner-instruction record"
  check_sha "$BUNDLE_DIR/$MANIFEST_REL" "$MANIFEST_FILE_SHA" "governance manifest"
  check_sha "$BUNDLE_DIR/$AUDIT_TOOL_REL" "$AUDIT_TOOL_FILE_SHA" "audit tool"
  check_sha "$PARENT_OUT/report.json" "$PARENT_REPORT_SHA" "parent report (attempt 4)"
  check_sha "$MAPPING_HOST" "$MAPPING_SHA" "symbol mapping"
  check_sha "$UNIVERSE_HOST" "$UNIVERSE_SHA" "fetch universe"
  grep -q "\"spec_sha256\": \"$EXPECTED_SPEC_SHA256\"" "$BUNDLE_DIR/$SPEC_REL" || \
    die "spec file does not carry spec_sha256 $EXPECTED_SPEC_SHA256"
  echo "ok  spec_sha256 $EXPECTED_SPEC_SHA256"

  # registry: parent COMPLETED, exactly four consumed attempts (audit consumes none), nothing open
  sudo docker run --rm -i --network none --entrypoint python \
    -v /opt/workbench/data/research/range002_registry:/app/data/research/range002_registry:ro \
    -v "$BUNDLE_DIR":/work:ro "$IMAGE" -I - <<'PY'
import sys
sys.path.insert(0, "/work/apps/backend")
from pathlib import Path
from app.research.range002.governance.run_registry import RunRegistry, RunStatus

runs = RunRegistry(Path("/app/data/research/range002_registry/range002_runs.jsonl")).runs()
issued = [r for r in runs if r.capability_issued_seq is not None]
active = [r for r in runs if r.status is RunStatus.OPEN]
parent = [r for r in runs if r.run_id == "range002-run-000011"]
print(f"registry: runs={len(runs)} capability_issued={len(issued)} open={len(active)}")
if len(issued) != 4 or active or len(parent) != 1 or parent[0].status is not RunStatus.COMPLETED:
    print("expected 4 consumed attempts, no active run, parent range002-run-000011 COMPLETED", file=sys.stderr)
    sys.exit(2)
PY
  echo "ok  registry: four consumed attempts, no active run, parent COMPLETED"

  sudo test ! -e "$AUDIT_OUT" || die "$AUDIT_OUT already exists (audit outputs are never overwritten)"
  [ -z "$(sudo docker ps -a --filter "name=^${NAME}$" --format '{{.Names}}')" ] || \
    die "container $NAME already exists"
  if sudo test -e "$AUDIT_LOG" && sudo grep -q "\"audit_id\": \"$AUDIT_ID\"" "$AUDIT_LOG"; then
    die "audit id $AUDIT_ID already used"
  fi
  sudo test -w /opt/workbench/data/research/range002_registry || die "registry directory is not writable"
  echo "ok  fresh audit output path, unused audit id"
}

launch() {
  sudo docker run -d --name "$NAME" --network none --entrypoint python \
    -v /opt/workbench/data/research/range002_s1:/app/data/research/range002_s1:ro \
    -v /opt/workbench/data/research/range002_registry:/app/data/research/range002_registry:rw \
    -v "$RUN_DIR":/app/data/research/range002_run:ro \
    -v "$AUDIT_OUT":/app/data/research/range002_audit_out:rw \
    -v "$BUNDLE_DIR":/work:ro \
    "$IMAGE" -I "/work/$AUDIT_TOOL_REL" \
    --parent-run-id "$PARENT_RUN_ID" --audit-id "$AUDIT_ID" \
    --spec "/work/$SPEC_REL" \
    --registry /app/data/research/range002_registry/range002_runs.jsonl \
    --parent-report /app/data/research/range002_run/out_2016q1_a4/report.json \
    --parent-evidence /app/data/research/range002_run/out_2016q1_a4/acquisition_evidence_range002-run-000011.json \
    --mapping /app/data/research/range002_run/symbol_mapping_2016q1_v3.json \
    --universe /app/data/research/range002_s1/universe-2016q1-20261013/universe_symbols.txt \
    --price-tolerance 0.05 --price-max-mismatch-fraction 0.10 \
    --daily-snapshot /app/data/research/range002_s1/sharadar-2016q1-20261013 \
    --snapshot-manifest /app/data/research/range002_run/snapshot_manifest_v2_accepted.json \
    --minute-bars /app/data/research/range002_run/minute_bars_2016q1_a4.duckdb \
    --minute-feed sip --minute-ts-convention start --table-filter SEP \
    --lookback-calendar-days 45 --coverage-threshold 0.98 --or-completeness-threshold 0.98 \
    --equity 100000 --tick 0.01 --code-sha "$PARENT_CODE_SHA" \
    --raw-vendor-rows-attested --delisting-action-value delisted \
    --audit-log /app/data/research/range002_registry/range002_audit_log.jsonl \
    --out-dir /app/data/research/range002_audit_out/audit
  echo "launched container $NAME (audit replay of $PARENT_RUN_ID, no strategy attempt); use: bash $0 status"
}

status() {
  sudo docker inspect -f 'running={{.State.Running}} exit={{.State.ExitCode}} started={{.State.StartedAt}} finished={{.State.FinishedAt}}' "$NAME"
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
  sudo docker inspect -f 'exit={{.State.ExitCode}} (0 = reproduced + arithmetic clean, 2 = refused, 3 = completed with a reproduction/arithmetic DEFECT)' "$NAME"
  sudo docker logs "$NAME" 2>&1 | cut -c1-400 | tail -20
  sudo ls -la "$AUDIT_OUT/audit" 2>/dev/null || echo "(no audit output directory)"
  sudo sha256sum "$AUDIT_OUT"/audit/* 2>/dev/null | cut -c1-100 || true
  echo "Audit outputs stay on the box under $AUDIT_OUT (private to Jay; PU-1 sidecars apply)."
}

case "$MODE" in
  preflight) preflight ;;
  run)       preflight; sudo mkdir -p "$AUDIT_OUT"; launch; wait_done || true; collect ;;
  status)    status ;;
  collect)   collect ;;
  *) echo "usage: bash $0 preflight|run|status|collect" >&2; exit 64 ;;
esac
