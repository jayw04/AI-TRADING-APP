#!/usr/bin/env bash
# Hermetic behaviour tests for provision-versioned-s3.sh. No AWS, no Docker, no box: `aws`,
# `docker compose` and `curl` are faked and a synthetic gzipped tarball stands in for the S3 object.
#
# Two harness shapes, mirroring the ADR-0043 harness:
#   * assertion-refusal cases run the REAL script + REAL manifest with ONE mismatching env value and
#     assert refusal BEFORE any S3 contact (AWS_MUST_NOT_RUN=1 makes a breach loud);
#   * verification / staging / swap / rollback cases run a COPY of the tooling beside a TEST control
#     record + TEST manifest whose sha/bytes match the fake object.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
AWSDIR="$(cd "$HERE/.." && pwd)"                 # deploy/aws — real tooling, real manifests
PROV_REAL="$AWSDIR/provision-versioned-s3.sh"
ADR_PROV="$AWSDIR/provision-adr0043-validation.sh"
ADR_MANIFEST="$AWSDIR/adr0043_validation_deploy.json"
PASS=0; FAIL=0
ok(){ echo "  PASS: $1"; PASS=$((PASS+1)); }
bad(){ echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
check(){ if eval "$2"; then ok "$1"; else bad "$1 [cond: $2]"; fi; }

REAL_NAME="factor_repair_b94838b6"
DEPLOYED="b94838b6aa611e02982b3d1ae5ca5333b5f1d80e"
IMPL="38f40b46906fc91497049924f7a62e7384d67653"

# ---- fakes ------------------------------------------------------------------------------------
BIN="$(mktemp -d)"
cat > "$BIN/aws" <<'EOF'
#!/usr/bin/env bash
if [ "${AWS_MUST_NOT_RUN:-0}" = "1" ]; then echo "GUARD-BREACH: aws reached" >&2; exit 91; fi
if [ "${FAKE_AWS_FAIL:-0}" = "1" ]; then echo "fake-aws: NoSuchVersion" >&2; exit 254; fi
out=""; for a in "$@"; do out="$a"; done
cp "$FAKE_OBJECT" "$out"; echo '{"VersionId":"vX"}'
EOF
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
cat > "$BIN/curl" <<'EOF'
#!/usr/bin/env bash
c=$(( $(cat "${CURL_COUNTER:-/dev/null}" 2>/dev/null || echo 0) + 1 ))
[ -n "${CURL_COUNTER:-}" ] && echo "$c" > "$CURL_COUNTER"
for k in ${FAIL_HEALTH_CALLS:-}; do [ "$c" = "$k" ] && exit 22; done
exit 0
EOF
chmod +x "$BIN"/aws "$BIN"/compose "$BIN"/curl
export PATH="$BIN:$PATH"
export AWS_BIN="$BIN/aws" COMPOSE="$BIN/compose" CURL="$BIN/curl"

# ---- a synthetic S3 object (gzipped tar) with a chosen marker ----------------------------------
mk_object() {  # <outfile> <governed:true|false> [deployed] [impl]
  local out="$1" governed="$2" dep="${3:-$DEPLOYED}" impl="${4:-$IMPL}" d
  d="$(mktemp -d)"; mkdir -p "$d/tree/apps/backend/app"
  echo "print('app')" > "$d/tree/apps/backend/app/main.py"
  cat > "$d/tree/DEPLOYED_BUILD_INFO.json" <<JSON
{ "deployed_repository_commit": "$dep",
  "adr0043_implementation_commit": "$impl",
  "adr0043_governed_paths_match": $governed }
JSON
  tar czf "$out" -C "$d/tree" .
}

# ---- a copy of the tooling beside TEST control + manifest matching a fake object ---------------
mk_kit() {  # <objfile> <key> [sha-override] [bytes-override] -> echoes kit dir
  local obj="$1" key="$2" sha_o="${3:-}" bytes_o="${4:-}" kit sha bytes
  kit="$(mktemp -d)"; mkdir -p "$kit/manifests"
  cp "$PROV_REAL" "$kit/provision-versioned-s3.sh"
  cp "$AWSDIR/verify_deploy_object.py" "$kit/verify_deploy_object.py"
  sha="${sha_o:-$(python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$obj")}"
  bytes="${bytes_o:-$(python3 -c 'import os,sys;print(os.path.getsize(sys.argv[1]))' "$obj")}"
  cat > "$kit/manifests/DEPLOY_CONTROL.json" <<JSON
{ "schema":"versioned-deploy-control/1",
  "allowed_manifests":["t_manifest"],
  "allowed_key_prefixes":["bootstrap/factor-repair/"],
  "forbidden_keys":["bootstrap/code.tgz"] }
JSON
  cat > "$kit/manifests/t_manifest.json" <<JSON
{ "schema":"versioned-deploy/1","region":"us-east-1","bucket":"b","key":"$key",
  "version_id":"V1","sha256":"$sha","bytes":$bytes,
  "deployed_repository_commit":"$DEPLOYED","adr0043_implementation_commit":"$IMPL" }
JSON
  echo "$kit"
}

run_kit(){ local kit="$1"; shift; ( export DEPLOY_MANIFEST=t_manifest; "$@" bash "$kit/provision-versioned-s3.sh" ) >"$OUT" 2>&1; echo $?; }

OUT="$(mktemp)"

echo "== A. manifest selection is fail-closed =="
AWS_MUST_NOT_RUN=1 DEPLOY_MANIFEST="" bash "$PROV_REAL" >"$OUT" 2>&1; rc=$?
check "unset DEPLOY_MANIFEST refuses" "[ $rc -ne 0 ] && grep -q 'DEPLOY_MANIFEST is required' '$OUT'"
AWS_MUST_NOT_RUN=1 DEPLOY_MANIFEST="../../etc/passwd" bash "$PROV_REAL" >"$OUT" 2>&1; rc=$?
check "path-shaped DEPLOY_MANIFEST refuses" "[ $rc -ne 0 ] && grep -q 'bare manifest NAME' '$OUT'"
AWS_MUST_NOT_RUN=1 DEPLOY_MANIFEST="not_allowlisted" bash "$PROV_REAL" >"$OUT" 2>&1; rc=$?
check "non-allowlisted manifest name refuses" "[ $rc -ne 0 ] && grep -q 'not permitted by the committed' '$OUT'"

echo "== B. operator cannot substitute identity (assertions, before S3) =="
for pair in "CODE_VERSION_ID=WRONGVERSION:S3 object VersionId" \
            "EXPECTED_CODE_SHA256=deadbeef:archive sha256" \
            "EXPECTED_CODE_BYTES=1:archive byte size" \
            "EXPECTED_DEPLOYED_COMMIT=0000:deployed_repository_commit" \
            "EXPECTED_IMPL_COMMIT=0000:adr0043_implementation_commit" \
            "CODE_KEY=bootstrap/code.tgz:code key" \
            "S3_BUCKET=other:bucket"; do
  kv="${pair%%:*}"; label="${pair#*:}"
  AWS_MUST_NOT_RUN=1 DEPLOY_MANIFEST="$REAL_NAME" env "$kv" bash "$PROV_REAL" >"$OUT" 2>&1; rc=$?
  check "env override '${kv%%=*}' refuses before S3" "[ $rc -ne 0 ] && grep -q '$label mismatch' '$OUT'"
done

echo "== C. the ADR-0043 latch cannot authorize this path =="
AWS_MUST_NOT_RUN=1 DEPLOY_MANIFEST="$REAL_NAME" ADR0043_MIGRATION_AUTHORIZED=1 bash "$PROV_REAL" >"$OUT" 2>&1; rc=$?
check "ADR0043_MIGRATION_AUTHORIZED alone refuses" "[ $rc -ne 0 ] && grep -q 'NO effect here' '$OUT'"

echo "== D. object verification happens BEFORE extraction =="
OBJ="$(mktemp)"; mk_object "$OBJ" true
export FAKE_OBJECT="$OBJ"
kit="$(mk_kit "$OBJ" "bootstrap/factor-repair/x.tgz" "$(printf '%064d' 0)")"
export WORKBENCH_APP_DIR="$(mktemp -d)"
rc=$(run_kit "$kit"); check "wrong sha256 refuses before extraction" \
  "[ $rc -ne 0 ] && grep -q 'refusing to extract' '$OUT' && [ ! -d '$WORKBENCH_APP_DIR/app' ]"
kit="$(mk_kit "$OBJ" "bootstrap/factor-repair/x.tgz" "" 123)"
rc=$(run_kit "$kit"); check "wrong byte count refuses before extraction" \
  "[ $rc -ne 0 ] && grep -q 'refusing to extract' '$OUT'"
kit="$(mk_kit "$OBJ" "bootstrap/factor-repair/x.tgz")"
rc=$(FAKE_AWS_FAIL=1 run_kit "$kit"); check "unresolvable object/version refuses" \
  "[ $rc -ne 0 ] && grep -q 'download of the frozen object/version failed' '$OUT'"

echo "== E. key guards =="
kit="$(mk_kit "$OBJ" "bootstrap/code.tgz")"
rc=$(run_kit "$kit"); check "legacy bootstrap/code.tgz key refuses" \
  "[ $rc -ne 0 ] && grep -q 'FORBIDDEN' '$OUT'"
kit="$(mk_kit "$OBJ" "adr0043/whatever.tgz")"
rc=$(run_kit "$kit"); check "key outside allowed prefixes refuses" \
  "[ $rc -ne 0 ] && grep -q 'under no allowed prefix' '$OUT'"

echo "== F. staged marker provenance =="
OBJ_BADDEP="$(mktemp)"; mk_object "$OBJ_BADDEP" true "0000000000000000000000000000000000000000" "$IMPL"
FAKE_OBJECT="$OBJ_BADDEP" ; export FAKE_OBJECT
kit="$(mk_kit "$OBJ_BADDEP" "bootstrap/factor-repair/x.tgz")"
rc=$(run_kit "$kit"); check "wrong deployed commit in staged marker refuses" \
  "[ $rc -ne 0 ] && grep -q 'staged marker failed provenance' '$OUT'"
OBJ_BADIMPL="$(mktemp)"; mk_object "$OBJ_BADIMPL" true "$DEPLOYED" "1111111111111111111111111111111111111111"
FAKE_OBJECT="$OBJ_BADIMPL" ; export FAKE_OBJECT
kit="$(mk_kit "$OBJ_BADIMPL" "bootstrap/factor-repair/x.tgz")"
rc=$(run_kit "$kit"); check "wrong ADR-0043 baseline in staged marker refuses" \
  "[ $rc -ne 0 ] && grep -q 'staged marker failed provenance' '$OUT'"
OBJ_NOGOV="$(mktemp)"; mk_object "$OBJ_NOGOV" false
FAKE_OBJECT="$OBJ_NOGOV" ; export FAKE_OBJECT
kit="$(mk_kit "$OBJ_NOGOV" "bootstrap/factor-repair/x.tgz")"
rc=$(run_kit "$kit"); check "governed_paths_match=false refuses" \
  "[ $rc -ne 0 ] && grep -q 'staged marker failed provenance' '$OUT'"

echo "== G. default flow: verify, stage, STOP — no swap, no restart =="
FAKE_OBJECT="$OBJ" ; export FAKE_OBJECT
export WORKBENCH_APP_DIR="$(mktemp -d)"; mkdir -p "$WORKBENCH_APP_DIR/app"; echo OLD > "$WORKBENCH_APP_DIR/app/marker"
kit="$(mk_kit "$OBJ" "bootstrap/factor-repair/x.tgz")"
rc=$(run_kit "$kit")
check "default invocation exits 0 with NO SWAP" "[ $rc -eq 0 ] && grep -q 'VERIFIED — NO SWAP, NO START' '$OUT'"
check "running tree is untouched" "[ \"\$(cat '$WORKBENCH_APP_DIR/app/marker')\" = OLD ]"
check "no staging residue is left behind" "[ -z \"\$(ls -d '$WORKBENCH_APP_DIR'/.staging.* 2>/dev/null)\" ]"

echo "== H. authorized swap, health gate, rollback =="
export WORKBENCH_APP_DIR="$(mktemp -d)"; mkdir -p "$WORKBENCH_APP_DIR/app"; echo OLD > "$WORKBENCH_APP_DIR/app/marker"
rc=$(run_kit "$kit" env VERSIONED_DEPLOY_AUTHORIZED=1)
check "authorized deploy swaps and health-gates" "[ $rc -eq 0 ] && grep -q 'HEALTHZ_OK' '$OUT'"
check "new tree is in place after swap" "[ -f '$WORKBENCH_APP_DIR/app/DEPLOYED_BUILD_INFO.json' ]"

export WORKBENCH_APP_DIR="$(mktemp -d)"; mkdir -p "$WORKBENCH_APP_DIR/app"; echo OLD > "$WORKBENCH_APP_DIR/app/marker"
rc=$(run_kit "$kit" env VERSIONED_DEPLOY_AUTHORIZED=1 FAIL_BUILD=1)
check "build failure rolls back and reports ROLLBACK_OK" "[ $rc -ne 0 ] && grep -q 'ROLLBACK_OK' '$OUT'"
check "prior tree restored after build failure" "[ \"\$(cat '$WORKBENCH_APP_DIR/app/marker' 2>/dev/null)\" = OLD ]"

export WORKBENCH_APP_DIR="$(mktemp -d)"; mkdir -p "$WORKBENCH_APP_DIR/app"; echo OLD > "$WORKBENCH_APP_DIR/app/marker"
CNT="$(mktemp)"; echo 0 > "$CNT"
rc=$(run_kit "$kit" env VERSIONED_DEPLOY_AUTHORIZED=1 START_WAIT=0 CURL_COUNTER="$CNT" FAIL_HEALTH_CALLS=1)
check "new-stack health failure rolls back and reports ROLLBACK_OK" "[ $rc -ne 0 ] && grep -q 'ROLLBACK_OK' '$OUT'"

export WORKBENCH_APP_DIR="$(mktemp -d)"; mkdir -p "$WORKBENCH_APP_DIR/app"; echo OLD > "$WORKBENCH_APP_DIR/app/marker"
echo 0 > "$CNT"
rc=$(run_kit "$kit" env VERSIONED_DEPLOY_AUTHORIZED=1 START_WAIT=0 CURL_COUNTER="$CNT" FAIL_HEALTH_CALLS="1 2")
check "prior-stack unhealthy reports ROLLBACK_FAILED (exit 4), not the original failure" \
  "[ $rc -eq 4 ] && grep -q 'ROLLBACK_FAILED' '$OUT'"

export WORKBENCH_APP_DIR="$(mktemp -d)"; mkdir -p "$WORKBENCH_APP_DIR/app"; echo OLD > "$WORKBENCH_APP_DIR/app/marker"
rc=$(run_kit "$kit" env VERSIONED_DEPLOY_AUTHORIZED=1 FAIL_BUILD=1 FAIL_OLDUP=1)
check "prior stack failing to restart reports ROLLBACK_FAILED" \
  "[ $rc -eq 4 ] && grep -q 'ROLLBACK_FAILED' '$OUT'"

echo "== I. the ADR-0043 provisioner is untouched =="
check "provision-adr0043-validation.sh still requires the adr0043/ prefix" \
  "grep -q 'adr0043/\\*) : ;;' '$ADR_PROV'"
check "provision-adr0043-validation.sh still uses ADR0043_MIGRATION_AUTHORIZED" \
  "grep -q 'ADR0043_MIGRATION_AUTHORIZED' '$ADR_PROV'"
check "its manifest path is still the fixed sibling" \
  "grep -q 'adr0043_validation_deploy.json' '$ADR_PROV'"
# the path is PIPED, not passed as an argv path: a Windows-native python3 cannot open an MSYS
# /c/... path, so passing one makes this check fail locally while passing in CI.
check "its frozen manifest still names the adr0043/ object" \
  "cat '$ADR_MANIFEST' | python3 -c \"import json,sys;sys.exit(0 if json.load(sys.stdin)['key'].startswith('adr0043/') else 1)\""
# comments are stripped first: the generic provisioner's header names the ADR-0043 manifest
# precisely to document that it does NOT use it, and that explanation must not trip the check.
check "the generic provisioner never READS the ADR-0043 manifest (non-comment lines)" \
  "! grep -v '^[[:space:]]*#' '$PROV_REAL' | grep -q 'adr0043_validation_deploy'"

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
