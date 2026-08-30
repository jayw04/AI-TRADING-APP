#!/usr/bin/env bash
# GENERIC version-pinned provisioner — manifest-frozen identity, staged, fail-closed.
#
# WHY THIS EXISTS, SEPARATELY FROM THE OTHER TWO PROVISIONERS
#   provision-from-s3.sh downloads by bucket/key ONLY. It cannot consume an S3 VersionId, does not
#   verify an approved digest before extraction, extracts directly over the running tree, and
#   rebuilds/restarts immediately. It cannot honour a "the Version ID is the artifact authority"
#   ruling, because the bytes it extracts are whatever the key holds at fetch time.
#
#   provision-adr0043-validation.sh has the right mechanics but is, by its own declaration, the
#   ADR-0043 VALIDATION-BOX provisioner: its manifest path is fixed to adr0043_validation_deploy.json,
#   it requires an adr0043/ key prefix, and its swap gate is ADR0043_MIGRATION_AUTHORIZED. Teaching
#   it to accept an unrelated key would make a non-ADR-0043 deployment masquerade as an ADR-0043
#   validation deployment. ⛔ That script and its manifest are deliberately NOT modified by this one.
#
#   So this script carries the hardened MECHANICS forward under a deployment-neutral AUTHORITY.
#
# PROPERTIES CARRIED FORWARD (each is a named, tested behaviour)
#   * identity is read from a COMMITTED manifest, never operator-supplied;
#   * the manifest is selected BY NAME from a committed allowlist — there is no path-selectable
#     manifest, so manifest selection cannot become the new artifact-selection escape hatch;
#   * runtime env values are ASSERTIONS ONLY: if set they must equal the frozen value exactly, and
#     a mismatch refuses BEFORE contacting S3;
#   * download is of one EXACT S3 object VERSION, never by key alone;
#   * byte size and SHA-256 are verified BEFORE extraction;
#   * extraction goes to STAGING on the same filesystem, never over the running tree;
#   * the staged DEPLOYED_BUILD_INFO.json is verified against the frozen provenance commits;
#   * the DEFAULT flow is VERIFY → STAGE → STOP: no swap, no restart, running tree UNCHANGED;
#   * swapping and starting requires a separate explicit latch, VERSIONED_DEPLOY_AUTHORIZED=1;
#   * the swap is atomic, the prior tree is retained, and .env + data are preserved;
#   * start is health-gated, and failure restores the prior tree and reports ROLLBACK_OK or
#     ROLLBACK_FAILED — a recovery error is never collapsed into the original failure.
#
# USAGE
#   DEPLOY_MANIFEST=<name> bash deploy/aws/provision-versioned-s3.sh            # verify+stage+STOP
#   DEPLOY_MANIFEST=<name> VERSIONED_DEPLOY_AUTHORIZED=1 bash ...               # swap + start
#   <name> is a bare manifest name from DEPLOY_CONTROL.json's allowed_manifests — not a path.
#
# It never trades, never captures a baseline, never runs Phase 0.
set -uo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin:/sbin:/usr/sbin:/snap/bin:$PATH
HERE="$(cd "$(dirname "$0")" && pwd)"
MANIFEST_DIR="$HERE/manifests"
CONTROL="$MANIFEST_DIR/DEPLOY_CONTROL.json"
PYTHON="${PYTHON:-python3}"

fatal()          { echo "FATAL: $*" >&2; exit 1; }
rollback_failed(){ echo "ROLLBACK_FAILED: $*" >&2; exit 4; }

command -v "$PYTHON" >/dev/null || fatal "python3 is required for manifest + object verification."
[ -f "$CONTROL" ] || fatal "deployment-control record not found at $CONTROL — no control record, no deploy."

# --- the ADR-0043 latch must never authorize a deployment on this path -------------------------
if [ "${ADR0043_MIGRATION_AUTHORIZED:-0}" = "1" ] && [ "${VERSIONED_DEPLOY_AUTHORIZED:-0}" != "1" ]; then
  fatal "ADR0043_MIGRATION_AUTHORIZED has NO effect here. This provisioner's authorization latch is
       VERSIONED_DEPLOY_AUTHORIZED. An ADR-0043 control must not authorize an unrelated deployment."
fi

# --- manifest selection: BY NAME, from the committed allowlist, fail-closed --------------------
NAME="${DEPLOY_MANIFEST:-}"
[ -n "$NAME" ] || fatal "DEPLOY_MANIFEST is required (a bare name from $CONTROL allowed_manifests)."
case "$NAME" in
  */*|*\\*|*..*|"") fatal "DEPLOY_MANIFEST='$NAME' must be a bare manifest NAME, not a path." ;;
esac
"$PYTHON" - "$CONTROL" "$NAME" <<'PY' || fatal "DEPLOY_MANIFEST is not permitted by the committed deployment-control record."
import json, sys
ctl = json.load(open(sys.argv[1], encoding="utf-8"))
if ctl.get("schema") != "versioned-deploy-control/1":
    sys.exit(1)
sys.exit(0 if sys.argv[2] in (ctl.get("allowed_manifests") or []) else 1)
PY
MANIFEST="$MANIFEST_DIR/$NAME.json"
[ -f "$MANIFEST" ] || fatal "allowlisted manifest '$NAME' has no file at $MANIFEST."

mf() { "$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1],encoding="utf-8"))[sys.argv[2]])' "$MANIFEST" "$1"; }
[ "$(mf schema)" = "versioned-deploy/1" ] || fatal "manifest '$NAME' declares an unrecognised schema; refusing to interpret it."

REGION="$(mf region)"
BUCKET="$(mf bucket)"
KEY="$(mf key)"
VERSION_ID="$(mf version_id)"
SHA="$(mf sha256)"
BYTES="$(mf bytes)"
DEPLOYED_COMMIT="$(mf deployed_repository_commit)"
IMPL_COMMIT="$(mf adr0043_implementation_commit)"

# --- the frozen key must be an allowlisted immutable prefix, never a forbidden mutable key -----
"$PYTHON" - "$CONTROL" "$KEY" <<'PY' || fatal "manifest key is not permitted by the deployment-control record."
import json, sys
ctl = json.load(open(sys.argv[1], encoding="utf-8")); key = sys.argv[2]
if key in (ctl.get("forbidden_keys") or []):
    print(f"key '{key}' is explicitly FORBIDDEN (legacy mutable artifact, authority NONE).", file=sys.stderr)
    sys.exit(1)
if not any(key.startswith(p) for p in (ctl.get("allowed_key_prefixes") or [])):
    print(f"key '{key}' is under no allowed prefix.", file=sys.stderr)
    sys.exit(1)
PY

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
CURL="${CURL:-curl}"
APP="${WORKBENCH_APP_DIR:-/opt/workbench}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/healthz}"
START_WAIT="${START_WAIT:-25}"

echo "=== versioned provision (manifest-frozen, staged) ==="
echo "  manifest=$NAME"
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

# --------------------------------------------------------------------- 3) extract to staging
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

# --------------------------------------------------------------------- 5) AUTHORIZATION GATE
#   Starting the backend runs `alembic upgrade head` (Dockerfile CMD), so build/start EXECUTES
#   whatever migration state the artifact carries — even when the expected delta is none. Until the
#   deployment is separately authorized, do NOT touch the running tree: verify and STOP.
if [ "${VERSIONED_DEPLOY_AUTHORIZED:-0}" != "1" ]; then
  rm -rf "$STAGE"
  echo "=== VERIFIED — NO SWAP, NO START ==="
  echo "The approved artifact (deployed=$DEPLOYED_COMMIT) downloaded and passed version+size+sha+"
  echo "marker verification. The running application tree is UNCHANGED. Set"
  echo "VERSIONED_DEPLOY_AUTHORIZED=1 to atomically swap + build/start (which runs"
  echo "'alembic upgrade head') ONLY after the deployment is separately authorized."
  exit 0
fi

# --------------------------------------------------------------------- 6) atomic swap
CUR="$APP/app"; PREV="$APP/app.prev.$$"
mkdir -p "$APP/data"
relink() { [ -e "$APP/.env" ] && ln -sf "$APP/.env" "$1/.env"; ln -sfn "$APP/data" "$1/data"; }
[ -e "$CUR" ] && mv "$CUR" "$PREV" || true
mv "$STAGE" "$CUR"
relink "$CUR"
echo "--- code atomically swapped into $CUR (prior tree: $PREV) ---"

rollback() {  # $1 = reason ; exits 4 (ROLLBACK_FAILED) or returns 0 (ROLLBACK_OK)
  echo "!! initiating rollback: $1" >&2
  if ! ( cd "$CUR" 2>/dev/null && $COMPOSE down --remove-orphans ); then
    echo "!! WARN: 'compose down' of the attempted new stack failed (continuing rollback)" >&2
  fi
  rm -rf "$CUR"
  [ -e "$PREV" ] && mv "$PREV" "$CUR" || rollback_failed "no prior application tree to restore ($PREV)"
  relink "$CUR"
  ( cd "$CUR" && $COMPOSE up -d ) || rollback_failed "prior stack did not restart"
  sleep "$START_WAIT"
  if "$CURL" -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "ROLLBACK_OK: prior stack restored and healthy."
    return 0
  fi
  rollback_failed "prior stack unhealthy after restore"
}

# --------------------------------------------------------------------- 7) build + start (health-gated)
echo "--- deployment authorized: building + starting (runs alembic upgrade head) ---"
if ! ( cd "$CUR" && $COMPOSE up -d --build ); then
  rollback "image build/start failed"
  fatal "build/start failed — rolled back to the prior stack (healthy)."
fi
sleep "$START_WAIT"
if "$CURL" -fsS "$HEALTH_URL" >/dev/null 2>&1; then
  echo "HEALTHZ_OK — deployment healthy; prior tree $PREV retained for manual cleanup."
else
  rollback "health check failed after start"
  fatal "health check failed after start — rolled back to the prior stack (healthy)."
fi
