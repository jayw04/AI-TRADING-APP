#!/usr/bin/env bash
# RANGE-002 return-blind SIP trades probe of 2016-Q1 missing-bar intervals (owner-authorised,
# <= 40 HTTP requests including pagination and retries; frozen sample list; no strategy performance).
#   bash RANGE-002_Trades_Probe_R2_Operator_Handoff.sh preflight | run | collect
# Reads only trade timestamps and condition codes. Consumes no strategy attempt. Credentials are
# read from the backend container environment into this process only, passed by name, never printed.
set -euo pipefail
umask 022
set +x
MODE="${1:-}"
IMAGE=trading-workbench-backend
NAME=range002-trades-probe-2016q1-r2
BUNDLE_TGZ=/tmp/s1/bundle11.tgz
BUNDLE_TGZ_SHA=96f4508818bdc536694810056f5de86860636b1c358f6c99cea056be4cfed089
BUNDLE_DIR=/tmp/s1/bundle11
TOOL_REL=apps/backend/scripts/research/range002/sip_trades_probe.py
TOOL_SHA=96af97a5d0fdda9ac1232c1dfe5d3be14190248235397e155d58951597c22265
MANIFEST=/tmp/s1/trades_probe_manifest2.json
MANIFEST_SHA=a3c60facf9b5394df796b30aad54bcce4a2da8420e3b9035b5ad82710aabdea6
MAX_REQUESTS=10   # 40-request authorisation minus the 30 used by the first run
OUT_DIR=/opt/workbench/data/research/range002_run/out_2016q1_trades_probe_r2
ACCESS_LOG=/opt/workbench/data/research/range002_run/trades_probe_access_log.jsonl

die() { echo "PREFLIGHT FAILED: $*" >&2; exit 2; }
check_sha() { local got; got="$(sudo sha256sum "$1" | cut -d' ' -f1)"; [ "$got" = "$2" ] || die "$3: $got != $2"; echo "ok  $3"; }

preflight() {
  check_sha "$BUNDLE_TGZ" "$BUNDLE_TGZ_SHA" "bundle archive"
  sudo test -d "$BUNDLE_DIR" || die "$BUNDLE_DIR not unpacked"
  check_sha "$BUNDLE_DIR/$TOOL_REL" "$TOOL_SHA" "probe tool"
  check_sha "$MANIFEST" "$MANIFEST_SHA" "frozen sample manifest"
  sudo test ! -e "$OUT_DIR" || die "$OUT_DIR exists (outputs are never overwritten)"
  [ -z "$(sudo docker ps -a --filter "name=^${NAME}$" --format '{{.Names}}')" ] || die "container $NAME exists"
  echo "ok  fresh output path; cap $MAX_REQUESTS requests"
}

launch() {
  local key secret
  key="$(sudo docker inspect workbench-backend --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^ALPACA_PAPER_6_API_KEY=' | cut -d= -f2-)"
  secret="$(sudo docker inspect workbench-backend --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^ALPACA_PAPER_6_API_SECRET=' | cut -d= -f2-)"
  [ -n "$key" ] && [ -n "$secret" ] || die "credentials not present in the backend container environment"
  export ALPACA_PAPER_6_API_KEY="$key" ALPACA_PAPER_6_API_SECRET="$secret"
  unset key secret
  sudo mkdir -p "$OUT_DIR"
  sudo touch "$ACCESS_LOG"
  sudo --preserve-env=ALPACA_PAPER_6_API_KEY,ALPACA_PAPER_6_API_SECRET \
    docker run -d --name "$NAME" --entrypoint python \
    -e ALPACA_PAPER_6_API_KEY -e ALPACA_PAPER_6_API_SECRET \
    -v "$BUNDLE_DIR":/work:ro -v "$MANIFEST":/manifest.json:ro \
    -v "$OUT_DIR":/out:rw -v "$ACCESS_LOG":/access_log.jsonl:rw \
    "$IMAGE" -I "/work/$TOOL_REL" --manifest /manifest.json --manifest-sha256 "$MANIFEST_SHA" \
    --max-requests "$MAX_REQUESTS" --key-env ALPACA_PAPER_6_API_KEY --secret-env ALPACA_PAPER_6_API_SECRET \
    --out /out/trades_probe_r2.json --access-log /access_log.jsonl
  unset ALPACA_PAPER_6_API_KEY ALPACA_PAPER_6_API_SECRET
  echo "launched $NAME"
}

wait_done() {
  for _ in $(seq 1 120); do
    [ "$(sudo docker inspect -f '{{.State.Running}}' "$NAME")" = "false" ] && return 0
    sleep 5
  done
  return 1
}

collect() {
  sudo docker inspect -f 'exit={{.State.ExitCode}} (0 = done, 2 = refused)' "$NAME"
  sudo docker logs "$NAME" 2>&1 | cut -c1-300 | tail -10
  sudo ls -la "$OUT_DIR" 2>/dev/null || true
  sudo sha256sum "$OUT_DIR"/trades_probe_r2.json 2>/dev/null | cut -c1-90 || true
  echo "Output stays on the box (private to Jay; PU-1 sidecar applies); access log: $ACCESS_LOG"
}

case "$MODE" in
  preflight) preflight ;;
  run) preflight; launch; wait_done || true; collect ;;
  collect) collect ;;
  *) echo "usage: bash $0 preflight|run|collect" >&2; exit 64 ;;
esac
