#!/usr/bin/env bash
# ADR-0043 VALIDATION-BOX provisioner — manifest-frozen identity, staged, migration-gated, fail-closed.
#
# WHY A SEPARATE, STRICTER PROVISIONER
# provision-from-s3.sh downloads by bucket/key only, does not verify the approved SHA before
# extraction, extracts directly over the running tree, and immediately rebuilds + restarts. The
# ADR-0043 validation-box deploy was approved as ONE EXACT object (bucket + key + S3 VersionId +
# sha256 + byte size + provenance commits). This provisioner deploys ONLY that object.
#
# IDENTITY IS FROZEN IN A COMMITTED MANIFEST (adr0043_validation_deploy.json), NOT operator-supplied.
# Every identity — bucket, key, version_id, sha256, bytes, deployed/impl commits — is read from the
# manifest sitting next to this script. Runtime environment values are accepted ONLY as ASSERTIONS:
# if set, they must equal the manifest value EXACTLY, else the script refuses BEFORE contacting S3.
# So an operator cannot declare a different object at runtime; they can at most re-assert the frozen
# one. Changing the approved object requires editing the committed manifest under review.
#
# FLOW
#   default (migration NOT authorized):
#       download the exact version -> verify size+sha BEFORE extraction -> extract to staging ->
#       verify the staged marker -> STOP. The running /opt/workbench/app is left UNCHANGED (no swap),
#       and staging is discarded. No half-deployed state.
#   ADR0043_MIGRATION_AUTHORIZED=1 (migration + deploy JOINTLY authorized):
#       ... same verification ... -> atomically swap the app dir (prior tree retained, data + .env
#       preserved) -> build/start (the backend CMD runs `alembic upgrade head`) -> health-gate. On
#       build/start OR health failure: stop the attempted new stack, restore the prior tree, restart
#       and health-check the PRIOR stack, and report ROLLBACK_OK or ROLLBACK_FAILED (distinct from
#       the original failure; recovery errors are never suppressed).
#
# It never trades, never captures a baseline, never runs Phase 0.
set -uo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin:/sbin:/usr/sbin:/snap/bin:$PATH
HERE="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$HERE/adr0043_validation_deploy.json"   # fixed sibling; not overridable at runtime
PYTHON="${PYTHON:-python3}"

fatal()          { echo "FATAL: $*" >&2; exit 1; }
rollback_failed(){ echo "ROLLBACK_FAILED: $*" >&2; exit 4; }

command -v "$PYTHON" >/dev/null || fatal "python3 is required for manifest + object verification."
[ -f "$MANIFEST" ] || fatal "frozen deploy manifest not found at $MANIFEST — no manifest, no deploy."

mf() { "$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$MANIFEST" "$1"; }
REGION="$(mf region)"
BUCKET="$(mf bucket)"
KEY="$(mf key)"
VERSION_ID="$(mf version_id)"
SHA="$(mf sha256)"
BYTES="$(mf bytes)"
DEPLOYED_COMMIT="$(mf deployed_repository_commit)"
IMPL_COMMIT="$(mf adr0043_implementation_commit)"

# --- the frozen key must be an immutable archival object, never the live bootstrap key ---
case "$KEY" in
  adr0043/*) : ;;
  *) fatal "manifest key '$KEY' is not under the required adr0043/ immutable prefix." ;;
esac
[ "$KEY" != "bootstrap/code.tgz" ] || fatal "manifest key is the LIVE bootstrap key — never for the validation box."

# --- runtime values, if supplied, are ASSERTIONS only: must equal the frozen manifest exactly ---
assert_env() {  # $1 env-var-name  $2 frozen-value  $3 label
  local name="$1" frozen="$2" label="$3" got="${!1:-}"
  if [ -n "$got" ] && [ "$got" != "$frozen" ]; then
    fatal "$label mismatch: supplied $name='$got' != approved '$frozen'. The approved object is frozen in the manifest; refusing before contacting S3."
  fi
}
assert_env S3_BUCKET                "$BUCKET"          "bucket"
assert_env CODE_KEY                 "$KEY"             "code key"
assert_env CODE_VERSION_ID          "$VERSION_ID"      "S3 object VersionId"
assert_env EXPECTED_CODE_SHA256     "$SHA"             "archive sha256"
assert_env EXPECTED_CODE_BYTES      "$BYTES"           "archive byte size"
assert_env EXPECTED_DEPLOYED_COMMIT "$DEPLOYED_COMMIT" "deployed_repository_commit"
assert_env EXPECTED_IMPL_COMMIT     "$IMPL_COMMIT"     "adr0043_implementation_commit"
assert_env AWS_REGION               "$REGION"          "region"

# test seams (do NOT affect identity): swap the external tools without touching the box.
AWS_BIN="${AWS_BIN:-aws}"
COMPOSE="${COMPOSE:-docker compose -f docker-compose.yml -f docker-compose.prod.yml}"
APP="${WORKBENCH_APP_DIR:-/opt/workbench}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/healthz}"
START_WAIT="${START_WAIT:-25}"

echo "=== ADR-0043 validation-box provision (manifest-frozen, staged) ==="
echo "  bucket=$BUCKET"
echo "  key=$KEY"
echo "  version_id=$VERSION_ID sha256=$SHA bytes=$BYTES"
echo "  deployed=$DEPLOYED_COMMIT impl=$IMPL_COMMIT"

# --------------------------------------------------------------------- 1) versioned download
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
TGZ="$WORK/code.tgz"
echo "--- downloading the exact frozen version ---"
$AWS_BIN s3api get-object --bucket "$BUCKET" --key "$KEY" \
  --version-id "$VERSION_ID" --region "$REGION" "$TGZ" >/dev/null \
  || fatal "download of the frozen object/version failed."

# --------------------------------------------------------------------- 2) verify BEFORE extraction
echo "--- verifying downloaded object (size + sha256) BEFORE extraction ---"
"$PYTHON" "$HERE/verify_deploy_object.py" download --path "$TGZ" --sha256 "$SHA" --bytes "$BYTES" \
  || fatal "downloaded object failed size/sha256 verification — refusing to extract."

# --------------------------------------------------------------------- 3) extract to staging (same fs as app/)
STAGE="$APP/.staging.$$"
rm -rf "$STAGE"; mkdir -p "$STAGE"
echo "--- extracting into staging: $STAGE ---"
tar xzf "$TGZ" -C "$STAGE" || { rm -rf "$STAGE"; fatal "extraction failed."; }

# --------------------------------------------------------------------- 4) verify staged marker
echo "--- verifying staged provenance marker ---"
"$PYTHON" "$HERE/verify_deploy_object.py" marker \
  --marker "$STAGE/DEPLOYED_BUILD_INFO.json" \
  --deployed-commit "$DEPLOYED_COMMIT" --impl-commit "$IMPL_COMMIT" \
  || { rm -rf "$STAGE"; fatal "staged marker failed provenance verification — refusing."; }

# --------------------------------------------------------------------- 5) MIGRATION GATE (default: no swap)
#   Starting the backend runs `alembic upgrade head` (Dockerfile CMD), so build/start EXECUTES the
#   reviewed-superset migration. Until migration + deploy are JOINTLY authorized, do NOT swap the
#   running application tree at all — verify and STOP, leaving the box exactly as it was.
if [ "${ADR0043_MIGRATION_AUTHORIZED:-0}" != "1" ]; then
  rm -rf "$STAGE"
  echo "=== VERIFIED — NO SWAP, NO START ==="
  echo "The approved artifact (deployed=$DEPLOYED_COMMIT) downloaded and passed size+sha+version+"
  echo "marker verification. The running application tree is UNCHANGED. Set"
  echo "ADR0043_MIGRATION_AUTHORIZED=1 to atomically swap + build/start (which runs"
  echo "'alembic upgrade head') ONLY after migration execution and deployment are jointly authorized."
  exit 0
fi

# --------------------------------------------------------------------- 6) atomic swap (data/.env preserved)
CUR="$APP/app"; PREV="$APP/app.prev.$$"
mkdir -p "$APP/data"
relink() { [ -e "$APP/.env" ] && ln -sf "$APP/.env" "$1/.env"; ln -sfn "$APP/data" "$1/data"; }
[ -e "$CUR" ] && mv "$CUR" "$PREV" || true
mv "$STAGE" "$CUR"
relink "$CUR"
echo "--- code atomically swapped into $CUR (prior tree: $PREV) ---"

rollback() {  # $1 = reason ; exits 4 (ROLLBACK_FAILED) or returns 0 (ROLLBACK_OK)
  echo "!! initiating rollback: $1" >&2
  # a) stop/remove the partially created NEW stack so it cannot linger in a mixed state
  if ! ( cd "$CUR" 2>/dev/null && $COMPOSE down --remove-orphans ); then
    echo "!! WARN: 'compose down' of the attempted new stack failed (continuing rollback)" >&2
  fi
  # b) restore the prior application tree
  rm -rf "$CUR"
  [ -e "$PREV" ] && mv "$PREV" "$CUR" || rollback_failed "no prior application tree to restore ($PREV)"
  relink "$CUR"
  # c) restart the PRIOR stack — a failure here is NOT suppressed
  ( cd "$CUR" && $COMPOSE up -d ) || rollback_failed "prior stack did not restart"
  # d) verify the PRIOR stack is healthy
  sleep "$START_WAIT"
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "ROLLBACK_OK: prior stack restored and healthy."
    return 0
  fi
  rollback_failed "prior stack unhealthy after restore"
}

# --------------------------------------------------------------------- 7) build + start (health-gated)
echo "--- migration authorized: building + starting (runs alembic upgrade head) ---"
if ! ( cd "$CUR" && $COMPOSE up -d --build ); then
  rollback "image build/start failed"
  fatal "build/start failed — rolled back to the prior stack (healthy)."
fi
sleep "$START_WAIT"
if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
  echo "HEALTHZ_OK — deployment healthy; prior tree $PREV retained for manual cleanup."
else
  rollback "health check failed after start"
  fatal "health check failed after start — rolled back to the prior stack (healthy)."
fi
