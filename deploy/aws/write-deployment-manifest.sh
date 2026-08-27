#!/usr/bin/env bash
# Write the deploy-side runtime manifest, on the box, immediately after the container is created.
#
# This is leg B of the deployment tuple. It is the artifact that makes an UNRECORDED container
# recreation detectable: it pins the container id and creation timestamp that the deploy step actually
# produced, so a later `docker compose up -d` that silently replaces the container no longer matches
# the deployment record — which is precisely what nobody could see on 2026-08-26.
#
# ⛔ It is NOT a replacement for .deploy_src_sha, and .deploy_src_sha is NOT a substitute for it.
# The old file remains a legacy corroborating declaration; after the repaired system is deployed,
# disagreement fails Gate 6, but that file may never again be sufficient evidence by itself.
#
#   sudo deploy/aws/write-deployment-manifest.sh [container] [app-dir]
#
# Idempotent: re-running after a legitimate recreation refreshes the record. That is the point — the
# deploy step is supposed to record what it made, and a recreation that skips this script is exactly
# the condition Gate 6 exists to catch.
set -eu

CONTAINER="${1:-workbench-backend}"
APP_DIR="${2:-/opt/workbench/app}"
MARKER="$APP_DIR/DEPLOYED_BUILD_INFO.json"
OUT="$APP_DIR/DEPLOYMENT_RUNTIME_MANIFEST.json"

command -v docker >/dev/null 2>&1 || { echo "FATAL: docker not available" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 not available" >&2; exit 1; }

[ -f "$MARKER" ] || {
  echo "FATAL: no build marker at $MARKER" >&2
  echo "       the deployment cannot record what it deployed if the archive carried no evidence" >&2
  exit 1
}

# Fresh from the daemon, never from a cached or remembered value.
CONTAINER_ID="$(docker inspect --format '{{.Id}}' "$CONTAINER")" || {
  echo "FATAL: container $CONTAINER not found" >&2; exit 1; }
IMAGE_ID="$(docker inspect --format '{{.Image}}' "$CONTAINER")"
CREATED="$(docker inspect --format '{{.Created}}' "$CONTAINER")"
IMAGE_NAME="$(docker inspect --format '{{.Config.Image}}' "$CONTAINER")"

# Atomic: a half-written manifest read by Gate 6 must never look like a valid one.
TMP="$(mktemp "${OUT}.XXXXXX")"
trap 'rm -f "$TMP"' EXIT

python3 - "$MARKER" "$TMP" "$CONTAINER_ID" "$IMAGE_ID" "$CREATED" "$IMAGE_NAME" <<'PY'
import hashlib, json, sys
from datetime import datetime, timezone

marker_path, out_path, container_id, image_id, created, image_name = sys.argv[1:7]
raw = open(marker_path, "rb").read()
marker = json.loads(raw.decode("utf-8"))

commit = str(marker.get("commit") or marker.get("deployed_repository_commit") or "").strip().lower()
code_digest = str(marker.get("code_digest") or "").strip().lower()
if len(commit) != 40:
    raise SystemExit(f"the build marker records no usable commit ({commit!r})")
if not code_digest.startswith("sha256:"):
    raise SystemExit(
        f"the build marker records no code_digest ({code_digest!r}); this archive predates the "
        f"attested deployment model and cannot be recorded under it")

json.dump({
    "schema": "workbench-deployment-runtime-manifest/1",
    "commit": commit,
    "code_digest": code_digest,
    "image_digest": image_id,
    "image_name": image_name,
    "container_id": container_id,
    "container_created": created,
    "build_info_sha256": hashlib.sha256(raw).hexdigest(),
    "deployed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
}, open(out_path, "w", encoding="utf-8"), indent=2, sort_keys=True)
PY

chmod 0644 "$TMP"
mv -f "$TMP" "$OUT"
trap - EXIT

echo "wrote $OUT"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); [print(f'  {k:20} {v}') for k,v in sorted(d.items())]" "$OUT"
