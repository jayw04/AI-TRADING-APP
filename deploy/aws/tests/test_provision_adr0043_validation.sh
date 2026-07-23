#!/usr/bin/env bash
# Hermetic behaviour tests for provision-adr0043-validation.sh. No AWS, no Docker, no box: `aws`,
# `docker compose`, and `curl` are faked, and a synthetic gzipped tarball stands in for the S3
# object. Identity is FROZEN in a committed manifest — the happy-path/rollback cases run a copy of
# the tooling beside a TEST manifest whose sha/bytes match the fake object (no runtime identity
# override exists), while the assertion-refusal cases run the REAL script + the REAL manifest with a
# single mismatching env value and assert it refuses BEFORE contacting S3.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
AWSDIR="$(cd "$HERE/.." && pwd)"                       # deploy/aws (the real tooling + real manifest)
PROV_REAL="$AWSDIR/provision-adr0043-validation.sh"
PROVFS="$AWSDIR/provision-from-s3.sh"
PASS=0; FAIL=0
ok(){ echo "  PASS: $1"; PASS=$((PASS+1)); }
bad(){ echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
check(){ if eval "$2"; then ok "$1"; else bad "$1 [cond: $2]"; fi; }

DEPLOYED="b0058bf335628f8dbde09a93915314f3a1f7743b"
IMPL="ea6db6e6d5dc338196ffca9919a7a2e2643e1f6c"

# ---- fakes ------------------------------------------------------------------------------------
BIN="$(mktemp -d)"
cat > "$BIN/aws" <<'EOF'
#!/usr/bin/env bash
# fake aws: supports only `s3api get-object ... <outfile>`. Fails the test loudly if it should not
# have been reached (assertion-refusal cases must exit before download).
if [ "${AWS_MUST_NOT_RUN:-0}" = "1" ]; then echo "GUARD-BREACH: aws reached" >&2; exit 91; fi
if [ "${FAKE_AWS_FAIL:-0}" = "1" ]; then echo "fake-aws: NoSuchVersion" >&2; exit 254; fi
out=""; for a in "$@"; do out="$a"; done
cp "$FAKE_OBJECT" "$out"; echo '{"VersionId":"vX"}'
EOF
# fake compose: branch on the argv so build / down / prior-restart can be failed independently.
cat > "$BIN/compose" <<'EOF'
#!/usr/bin/env bash
args="$*"
case "$args" in
  *--build*) [ "${FAIL_BUILD:-0}" = 1 ] && { echo "fake-compose: build failed" >&2; exit 1; } ;;
  *down*)    [ "${FAIL_DOWN:-0}"  = 1 ] && { echo "fake-compose: down failed"  >&2; exit 1; } ;;
  *up*)      [ "${FAIL_OLDUP:-0}" = 1 ] && { echo "fake-compose: old up failed" >&2; exit 1; } ;;
esac
exit 0
EOF
# fake curl: fail specific health-check CALL indices (1=new-stack, 2=rollback prior-stack).
cat > "$BIN/curl" <<'EOF'
#!/usr/bin/env bash
c=$(( $(cat "${CURL_COUNTER:-/dev/null}" 2>/dev/null || echo 0) + 1 ))
[ -n "${CURL_COUNTER:-}" ] && echo "$c" > "$CURL_COUNTER"
for k in ${FAIL_HEALTH_CALLS:-}; do [ "$c" = "$k" ] && exit 22; done
exit 0
EOF
chmod +x "$BIN"/aws "$BIN"/compose "$BIN"/curl
export PATH="$BIN:$PATH"
export AWS_BIN="$BIN/aws" COMPOSE="$BIN/compose"
export CURL="$BIN/curl"   # bind the health-check seam: the provisioner hardens PATH, so curl must be
                          # injected by env like aws/compose rather than relied on via PATH

# ---- a synthetic S3 object (gzipped tar) with a chosen marker ---------------------------------
mk_object() {  # <outfile> <governed:true|false> [deployed] [impl]
  local out="$1" governed="$2" dep="${3:-$DEPLOYED}" impl="${4:-$IMPL}" d
  d="$(mktemp -d)"; mkdir -p "$d/tree/apps/backend/app/orders"
  echo "print('settlement')" > "$d/tree/apps/backend/app/orders/settlement.py"
  cat > "$d/tree/DEPLOYED_BUILD_INFO.json" <<JSON
{ "deployed_repository_commit": "$dep",
  "adr0043_implementation_commit": "$impl",
  "adr0043_governed_paths_match": $governed }
JSON
  tar czf "$out" -C "$d/tree" .
}

# ---- a copy of the tooling beside a TEST manifest matching a fake object ------------------------
# usage: tooldir <object-file> <governed> [dep] [impl] -> prints the copied provisioner path
tooldir() {
  local obj="$1" governed="$2" dep="${3:-$DEPLOYED}" impl="${4:-$IMPL}" t sha bytes
  mk_object "$obj" "$governed" "$dep" "$impl"
  sha=$(sha256sum "$obj" | cut -d' ' -f1); bytes=$(wc -c < "$obj")
  t="$(mktemp -d)/aws"; mkdir -p "$t"
  cp "$PROV_REAL" "$AWSDIR/verify_deploy_object.py" "$t/"
  cat > "$t/adr0043_validation_deploy.json" <<JSON
{ "schema":"adr0043-validation-deploy/1","region":"us-east-1","bucket":"testbucket",
  "key":"adr0043/$DEPLOYED/source-$sha.tar.gz","version_id":"vid-test",
  "sha256":"$sha","bytes":$bytes,
  "deployed_repository_commit":"$dep","adr0043_implementation_commit":"$impl" }
JSON
  echo "$t/provision-adr0043-validation.sh"
}

new_app() {  # a fresh $APP with a prior tree + data + .env
  local A; A="$(mktemp -d)/opt-workbench"; mkdir -p "$A/app" "$A/data"
  echo "PRIOR-CODE" > "$A/app/marker.txt"; echo "SECRET=keepme" > "$A/.env"
  echo "sqlite-bytes" > "$A/data/workbench.sqlite"; printf '%s' "$A"
}

echo "== ADR-0043 validation provisioner tests (manifest-frozen) =="

# ============================================================ (A) IDENTITY IS FROZEN
# Real script + real manifest + a single mismatching env value -> refuse BEFORE S3 (aws must not run).
refuse_before_s3() {  # $1 label ; rest = VAR=VAL ...
  local out rc; out=$(env AWS_MUST_NOT_RUN=1 WORKBENCH_APP_DIR="$(mktemp -d)" "${@:2}" \
                        bash "$PROV_REAL" 2>&1); rc=$?
  if [ $rc -ne 0 ] && ! echo "$out" | grep -q GUARD-BREACH; then ok "$1"; else bad "$1 [rc=$rc]"; echo "$out"|tail -3; fi
}
refuse_before_s3 "alternate bucket refused"            S3_BUCKET=evil-bucket
refuse_before_s3 "alternate key (under adr0043/) refused" CODE_KEY=adr0043/other/source-x.tar.gz
refuse_before_s3 "alternate VersionId refused"         CODE_VERSION_ID=some-other-version
refuse_before_s3 "alternate checksum refused"          EXPECTED_CODE_SHA256=0000000000000000000000000000000000000000000000000000000000000000
refuse_before_s3 "alternate byte size refused"         EXPECTED_CODE_BYTES=999999
refuse_before_s3 "alternate deployed-commit refused"   EXPECTED_DEPLOYED_COMMIT=deadbeefdeadbeefdeadbeefdeadbeefdeadbeef
refuse_before_s3 "alternate impl-commit refused"       EXPECTED_IMPL_COMMIT=deadbeefdeadbeefdeadbeefdeadbeefdeadbeef
# re-asserting the FROZEN values is allowed (equals manifest) — reaches S3, no refusal-before-download
A=$(new_app); OBJ=$(mktemp); P=$(tooldir "$OBJ" true); export FAKE_OBJECT="$OBJ"
out=$(env WORKBENCH_APP_DIR="$A" S3_BUCKET=testbucket CODE_VERSION_ID=vid-test bash "$P" 2>&1); rc=$?
check "re-asserting the frozen identity is accepted"   "[ $rc -eq 0 ] && echo '$out' | grep -q 'NO SWAP'"

# ============================================================ (B) DEFAULT PATH = STAGE-ONLY, NO SWAP
A=$(new_app); OBJ=$(mktemp); P=$(tooldir "$OBJ" true); export FAKE_OBJECT="$OBJ"
L=$(mktemp); env WORKBENCH_APP_DIR="$A" bash "$P" >"$L" 2>&1; rc=$?
check "default: verifies + STOPS (exit 0)"             "[ $rc -eq 0 ] && grep -q 'NO SWAP, NO START' '$L'"
check "  ... running app tree UNCHANGED (no swap)"     "grep -q PRIOR-CODE '$A/app/marker.txt'"
check "  ... no new code placed"                       "! test -f '$A/app/apps/backend/app/orders/settlement.py'"
check "  ... no staging left behind"                   "! ls -d $A/.staging.* >/dev/null 2>&1"
check "  ... data + .env untouched"                    "grep -q sqlite-bytes '$A/data/workbench.sqlite' && grep -q keepme '$A/.env'"

# ============================================================ (C) VERIFY-BEFORE-EXTRACT failures
# wrong version (download fails)
A=$(new_app); OBJ=$(mktemp); P=$(tooldir "$OBJ" true); export FAKE_OBJECT="$OBJ"
L=$(mktemp); env FAKE_AWS_FAIL=1 WORKBENCH_APP_DIR="$A" bash "$P" >"$L" 2>&1; rc=$?
check "download failure refuses"                       "[ $rc -ne 0 ] && grep -q 'download' '$L'"
# wrong checksum: mutate the object AFTER the manifest froze its sha -> sha mismatch pre-extract
A=$(new_app); OBJ=$(mktemp); P=$(tooldir "$OBJ" true); echo "TAMPER" >> "$OBJ"; export FAKE_OBJECT="$OBJ"
L=$(mktemp); env WORKBENCH_APP_DIR="$A" bash "$P" >"$L" 2>&1; rc=$?
check "checksum mismatch refuses before extraction"    "[ $rc -ne 0 ] && grep -qi 'sha256' '$L'"
check "  ... app tree unchanged after checksum fail"   "grep -q PRIOR-CODE '$A/app/marker.txt'"
# bad marker (governed_paths_match=false)
A=$(new_app); OBJ=$(mktemp); P=$(tooldir "$OBJ" false); export FAKE_OBJECT="$OBJ"
L=$(mktemp); env WORKBENCH_APP_DIR="$A" bash "$P" >"$L" 2>&1; rc=$?
check "bad marker (governed false) refuses"            "[ $rc -ne 0 ] && grep -q 'governed_paths_match' '$L'"
check "  ... app tree unchanged after marker fail"     "grep -q PRIOR-CODE '$A/app/marker.txt'"

# ============================================================ (D) MIGRATION-AUTHORIZED swap + start
# happy path: swap + build ok + health ok
A=$(new_app); OBJ=$(mktemp); P=$(tooldir "$OBJ" true); export FAKE_OBJECT="$OBJ"
CC=$(mktemp); L=$(mktemp)
env ADR0043_MIGRATION_AUTHORIZED=1 START_WAIT=0 CURL_COUNTER="$CC" WORKBENCH_APP_DIR="$A" bash "$P" >"$L" 2>&1; rc=$?
check "migration auth + healthy: succeeds"             "[ $rc -eq 0 ] && grep -q HEALTHZ_OK '$L'"
check "  ... new code is live"                         "test -f '$A/app/apps/backend/app/orders/settlement.py'"
check "  ... data + .env preserved through swap"       "grep -q sqlite-bytes '$A/data/workbench.sqlite' && grep -q keepme '$A/app/.env'"

# ============================================================ (E) ROLLBACK completeness
# build fails -> rollback: down + restore prior + prior up + prior health ok -> ROLLBACK_OK
A=$(new_app); OBJ=$(mktemp); P=$(tooldir "$OBJ" true); export FAKE_OBJECT="$OBJ"; CC=$(mktemp); L=$(mktemp)
env ADR0043_MIGRATION_AUTHORIZED=1 START_WAIT=0 CURL_COUNTER="$CC" FAIL_BUILD=1 WORKBENCH_APP_DIR="$A" bash "$P" >"$L" 2>&1; rc=$?
check "build fail -> ROLLBACK_OK"                      "[ $rc -eq 1 ] && grep -q ROLLBACK_OK '$L'"
check "  ... prior code restored"                      "grep -q PRIOR-CODE '$A/app/marker.txt'"
check "  ... rollback initiated (down attempted stack)" "grep -q 'initiating rollback' '$L'"
check "  ... data preserved through rollback"          "grep -q sqlite-bytes '$A/data/workbench.sqlite'"
# new-stack health fails -> rollback with prior health ok -> ROLLBACK_OK
A=$(new_app); OBJ=$(mktemp); P=$(tooldir "$OBJ" true); export FAKE_OBJECT="$OBJ"; CC=$(mktemp); L=$(mktemp)
env ADR0043_MIGRATION_AUTHORIZED=1 START_WAIT=0 CURL_COUNTER="$CC" FAIL_HEALTH_CALLS="1" WORKBENCH_APP_DIR="$A" bash "$P" >"$L" 2>&1; rc=$?
check "new health fail -> ROLLBACK_OK"                 "[ $rc -eq 1 ] && grep -q ROLLBACK_OK '$L'"
check "  ... prior code restored after health fail"    "grep -q PRIOR-CODE '$A/app/marker.txt'"
# prior stack fails to RESTART -> ROLLBACK_FAILED (exit 4)
A=$(new_app); OBJ=$(mktemp); P=$(tooldir "$OBJ" true); export FAKE_OBJECT="$OBJ"; CC=$(mktemp); L=$(mktemp)
env ADR0043_MIGRATION_AUTHORIZED=1 START_WAIT=0 CURL_COUNTER="$CC" FAIL_BUILD=1 FAIL_OLDUP=1 WORKBENCH_APP_DIR="$A" bash "$P" >"$L" 2>&1; rc=$?
check "prior restart fail -> ROLLBACK_FAILED (exit 4)" "[ $rc -eq 4 ] && grep -q 'ROLLBACK_FAILED' '$L'"
# prior stack unhealthy after restore -> ROLLBACK_FAILED (fail the 2nd = prior health call)
A=$(new_app); OBJ=$(mktemp); P=$(tooldir "$OBJ" true); export FAKE_OBJECT="$OBJ"; CC=$(mktemp); L=$(mktemp)
env ADR0043_MIGRATION_AUTHORIZED=1 START_WAIT=0 CURL_COUNTER="$CC" FAIL_HEALTH_CALLS="1 2" WORKBENCH_APP_DIR="$A" bash "$P" >"$L" 2>&1; rc=$?
check "prior health fail -> ROLLBACK_FAILED (exit 4)"  "[ $rc -eq 4 ] && grep -q 'ROLLBACK_FAILED' '$L'"

# ============================================================ (F) provision-from-s3.sh guard
cat > "$BIN/aws" <<'EOF'
#!/usr/bin/env bash
echo "GUARD-BREACH: aws reached in provision-from-s3.sh" >&2; exit 99
EOF
chmod +x "$BIN/aws"
guard_refuses() { local out rc; out=$("${@:2}" bash "$PROVFS" 2>&1); rc=$?
  { [ $rc -eq 2 ] && echo "$out" | grep -q "validation box" && ! echo "$out" | grep -q GUARD-BREACH; } && ok "$1" || { bad "$1 [rc=$rc]"; }; }
guard_refuses "provision-from-s3 refuses validation host_id" env WORKBENCH_HOST_ID=adr0043-canary
guard_refuses "provision-from-s3 refuses ENFORCE mode"       env WORKBENCH_HOST_ID=box LOSS_CONTROL_MODE=ENFORCE
guard_refuses "provision-from-s3 refuses adr0043/ code key"  env WORKBENCH_HOST_ID=box CODE_KEY=adr0043/x/s.tar.gz

echo "== provisioner tests: $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ]
