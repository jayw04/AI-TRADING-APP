#!/usr/bin/env bash
# Build a PROVENANCE-STAMPED deploy archive for the git-archive deployment path (ADR 0032 + ADR 0043).
#
# WHY THIS EXISTS
# The paper box has NO .git — code is a `git archive` tarball extracted into /opt/workbench/app
# (see provision-from-s3.sh). `git rev-parse HEAD` therefore cannot anchor deployment provenance on
# the box. So the deployed package must carry its OWN immutable source identity: this script embeds a
# committed-source manifest (DEPLOYED_BUILD_INFO.json) into the archive and records the archive digest.
# The git-lineage proof (approved source commit + implementation-baseline ancestry) is produced HERE,
# on the build machine where .git exists — never on the box.
#
# WHAT IT PRODUCES (into <out-dir>, default ./dist):
#   source.tar.gz            archive of an APPROVED commit + an embedded /DEPLOYED_BUILD_INFO.json
#   source.tar.gz.sha256     its checksum (the recorded archive digest)
#   DEPLOYED_BUILD_INFO.json the marker, also left beside the archive as recorded evidence
# and prints the deployment-evidence record (source SHA, implementation baseline + ancestry proof,
# archive SHA-256, build timestamp, builder identity). The container image ID/digest is recorded
# separately, on the box, after the image is built (runbook A3 / the box-side gate).
#
# USAGE:
#   deploy/aws/build-deploy-archive.sh <approved-commit-sha> [<out-dir>]
#   # <approved-commit-sha> is REQUIRED and must be the EXPLICIT revision approved for this attempt.
#   # Do NOT build from the moving origin/main tip: main can advance past the approved revision
#   # between approval and build (it has — a governed loss-control deploy must pin the exact SHA so an
#   # unrelated, separately-reviewed feature merged after approval cannot ride into the ENFORCE box).
#   # out-dir defaults to ./dist ; override the implementation baseline via ADR0043_IMPLEMENTATION_SHA.
#
# NOTE ON NO PREFIX: the archive is built WITHOUT a path prefix so it extracts straight into
# /opt/workbench/app (matching `tar xzf … -C "$APP/app"` in provision-from-s3.sh). The marker is
# appended at the archive root, so it lands at /opt/workbench/app/DEPLOYED_BUILD_INFO.json — the path
# the box-side provenance gate reads.
set -euo pipefail

SOURCE_REF="${1:-}"
OUT_DIR="${2:-dist}"
if [ -z "$SOURCE_REF" ]; then
  echo "FATAL: pass the EXPLICIT approved commit SHA as arg 1 — never the moving origin/main tip."
  echo "       A governed loss-control deploy pins the reviewed revision so a feature merged after"
  echo "       approval cannot ride into the ENFORCE validation box."
  exit 1
fi
# ADR-0043 implementation baseline — must be an ancestor of the deployed source, else the archive
# would not contain the loss-control code (PR8 merge). Fixed; override only with explicit review.
IMPL_SHA="${ADR0043_IMPLEMENTATION_SHA:-c8b3ac24b839d7b19c40979a9e4be859151dbab7}"

command -v git >/dev/null || { echo "FATAL: git is required — run on the build machine, not the box."; exit 1; }
git rev-parse --git-dir >/dev/null 2>&1 \
  || { echo "FATAL: not a git repository. Provenance MUST be produced where .git exists."; exit 1; }

DEPLOYED_SHA="$(git rev-parse "${SOURCE_REF}^{commit}")"

# Ancestry proof (the build-machine lineage check the box cannot perform):
if git merge-base --is-ancestor "$IMPL_SHA" "$DEPLOYED_SHA"; then
  ANCESTRY="verified"
else
  echo "FATAL: ADR-0043 implementation ${IMPL_SHA} is NOT an ancestor of ${DEPLOYED_SHA}."
  echo "       The archive would not contain the ADR-0043 loss-control code. Refusing to build."
  exit 2
fi

# The DEPLOYED application/risk/migration code must be byte-identical to the reviewed implementation
# baseline: NO delta under apps/** (the risk engine, order path, and Alembic migrations all live there).
# This is the real safety property — "the risk-path code that runs is the reviewed code". Documentation
# (docs/**) and deployment-provenance tooling (deploy/**) are reviewed separately and never run in the
# risk path, so they are PERMITTED and RECORDED as evidence, not silently allowed.
APP_DELTA="$(git diff --name-only "$IMPL_SHA" "$DEPLOYED_SHA" -- apps/ || true)"
if [ -n "$APP_DELTA" ]; then
  echo "FATAL: application/risk/migration code differs from the implementation baseline ${IMPL_SHA}:"
  printf '  %s\n' $APP_DELTA
  echo "       The deployed risk-path code must equal the reviewed baseline. Refusing to build."
  exit 3
fi
# Non-application delta (reviewed docs + deploy-provenance tooling) — recorded, not hidden.
NONAPP_DELTA="$(git diff --name-only "$IMPL_SHA" "$DEPLOYED_SHA" -- . ':(exclude)apps/' || true)"

BUILT_AT="$(date -u +%FT%TZ)"
BUILDER="$(git config user.email 2>/dev/null || echo unknown)@$(hostname 2>/dev/null || echo unknown-host)"

mkdir -p "$OUT_DIR"
MARKER="$OUT_DIR/DEPLOYED_BUILD_INFO.json"
# Render the reviewed non-application delta as a JSON array for the evidence record.
NONAPP_JSON="$(printf '%s\n' $NONAPP_DELTA | sed '/^$/d' | sed 's/.*/"&"/' | paste -sd, - 2>/dev/null || true)"
cat > "$MARKER" <<EOF
{
  "deployed_repository_commit": "$DEPLOYED_SHA",
  "adr0043_implementation_commit": "$IMPL_SHA",
  "implementation_ancestry": "$ANCESTRY",
  "application_code_unchanged": true,
  "non_application_delta": [${NONAPP_JSON}],
  "built_at_utc": "$BUILT_AT",
  "builder": "$BUILDER",
  "artifact_type": "git-archive"
}
EOF

TAR="$OUT_DIR/source.tar"
git archive --format=tar "$DEPLOYED_SHA" > "$TAR"
# Append the marker at the archive ROOT (extracts to /opt/workbench/app/DEPLOYED_BUILD_INFO.json).
tar --append --file="$TAR" -C "$OUT_DIR" DEPLOYED_BUILD_INFO.json
gzip -nf "$TAR"                       # -n: reproducible (no mtime/name in the gzip header)
ARCHIVE="$TAR.gz"
sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
ARCHIVE_SHA="$(cut -d' ' -f1 "$ARCHIVE.sha256")"

cat <<EOF

=== ADR-0043 DEPLOY ARCHIVE — provenance evidence record ===
source_ref                 : $SOURCE_REF
deployed_repository_commit : $DEPLOYED_SHA
adr0043_implementation_sha : $IMPL_SHA
implementation_ancestry    : $ANCESTRY (git merge-base --is-ancestor, build machine)
application_code_unchanged : true (no apps/** delta from the implementation baseline)
non_application_delta      : $(printf '%s ' $NONAPP_DELTA)(reviewed docs + deploy provenance)
built_at_utc               : $BUILT_AT
builder                    : $BUILDER
archive                    : $ARCHIVE
archive_sha256             : $ARCHIVE_SHA
marker                     : $MARKER (embedded at archive root → /opt/workbench/app/DEPLOYED_BUILD_INFO.json)
============================================================
Next: upload the archive to the S3 bootstrap key the box pulls, e.g.
  aws s3 cp "$ARCHIVE" "s3://<bucket>/bootstrap/code.tgz"
then deploy with ambient ENFORCE on the ISOLATED validation box:
  LOSS_CONTROL_MODE=ENFORCE bash deploy/aws/provision-from-s3.sh
Record archive_sha256 above; the box-side gate re-computes it and compares.
EOF
