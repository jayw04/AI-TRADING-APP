#!/usr/bin/env bash
# Build a PROVENANCE-STAMPED deploy archive for the git-archive deployment path (ADR 0032 + ADR 0043).
#
# WHY THIS EXISTS
# The paper box has NO .git — code is a `git archive` tarball extracted into /opt/workbench/app
# (see provision-from-s3.sh). `git rev-parse HEAD` therefore cannot anchor deployment provenance on
# the box. So the deployed package must carry its OWN immutable source identity: this script embeds a
# committed-source manifest (DEPLOYED_BUILD_INFO.json) into the archive and records the archive digest.
# The git-lineage proof (curated source commit + baseline ancestry + blob-exact delta) is produced
# HERE, on the build machine where .git exists — never on the box.
#
# WHAT CHANGED (settlement-barrier baseline amendment)
# The first canary artifact enforced "apps/** must equal the implementation baseline (c8b3ac24)
# exactly". That is now too strict: the separately reviewed settlement-barrier extension (#463)
# legitimately ADDS apps/** code. But the squash-merge governance commit (ea6db6e) is the full
# origin/main tip and carries UNRELATED main-line changes (ADR-0044, a new migration, momentum-daily,
# drift-audit, risk-path deltas). So this builder no longer trusts a caller-supplied ref or a single
# "no apps delta" test. It delegates verification to the provenance guard, which requires the source
# to be EXACTLY the curated validation-executable baseline (07d3b82) and its delta from the prior
# deploy to match the frozen manifest path-for-path AND blob-for-blob. Two immutable identities are
# recorded: the original implementation baseline and the validation executable baseline.
#
# WHAT IT PRODUCES (into <out-dir>, default ./dist):
#   source.tar.gz            archive of the curated commit + an embedded /DEPLOYED_BUILD_INFO.json
#   source.tar.gz.sha256     its checksum (the recorded archive digest)
#   DEPLOYED_BUILD_INFO.json the marker, also left beside the archive as recorded evidence
#
# USAGE:
#   deploy/aws/build-deploy-archive.sh <curated-commit-sha> [<out-dir>]
#   # <curated-commit-sha> is REQUIRED and must resolve to the manifest's validation_executable_baseline.
#   # Building from origin/main or HEAD is refused by the guard. The manifest is the single source of
#   # truth for the two baselines and the approved inventory; override it only via committed review.
#
# NOTE ON NO PREFIX: the archive is built WITHOUT a path prefix so it extracts straight into
# /opt/workbench/app (matching `tar xzf … -C "$APP/app"` in provision-from-s3.sh). The marker is
# appended at the archive root, so it lands at /opt/workbench/app/DEPLOYED_BUILD_INFO.json — the path
# the box-side provenance gate reads.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="${ADR0043_DEPLOY_MANIFEST:-$HERE/adr0043_deploy_manifest.json}"

SOURCE_REF="${1:-}"
OUT_DIR="${2:-dist}"
if [ -z "$SOURCE_REF" ]; then
  echo "FATAL: pass the curated commit SHA as arg 1 — it must be the manifest's"
  echo "       validation_executable_baseline. Building from origin/main or HEAD is refused."
  exit 1
fi

command -v git >/dev/null || { echo "FATAL: git is required — run on the build machine, not the box."; exit 1; }
command -v python3 >/dev/null || { echo "FATAL: python3 is required for the provenance guard."; exit 1; }
git rev-parse --git-dir >/dev/null 2>&1 \
  || { echo "FATAL: not a git repository. Provenance MUST be produced where .git exists."; exit 1; }
[ -f "$MANIFEST" ] || { echo "FATAL: deploy manifest not found at $MANIFEST — no manifest, no build."; exit 1; }

# --- read the two immutable identities from the manifest (single source of truth) ---
read_field() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$MANIFEST" "$1"; }
IMPL_SHA="$(read_field implementation_baseline)"
VALIDATION_SHA="$(read_field validation_executable_baseline)"
PRIOR_SHA="$(read_field prior_deploy_baseline)"

# --- the guard is the gate: exact curated source, lineage, no migration, blob-exact approved delta ---
if ! python3 "$HERE/verify_deploy_provenance.py" "$SOURCE_REF" --manifest "$MANIFEST"; then
  echo "FATAL: deploy-provenance guard refused the source (see above). Refusing to build."
  exit 3
fi

# The guard proved SOURCE_REF resolves to the curated validation executable baseline; archive THAT
# commit explicitly (never the caller's ref shape), so the built tree cannot drift from the reviewed one.
DEPLOYED_SHA="$(git rev-parse "${VALIDATION_SHA}^{commit}")"

BUILT_AT="$(date -u +%FT%TZ)"
BUILDER="$(git config user.email 2>/dev/null || echo unknown)@$(hostname 2>/dev/null || echo unknown-host)"

mkdir -p "$OUT_DIR"
MARKER="$OUT_DIR/DEPLOYED_BUILD_INFO.json"
# The reviewed delta (application + operational) is recorded in the marker straight from the manifest,
# so the embedded evidence and the gate cannot disagree.
python3 - "$MANIFEST" "$DEPLOYED_SHA" "$IMPL_SHA" "$VALIDATION_SHA" "$PRIOR_SHA" "$BUILT_AT" "$BUILDER" > "$MARKER" <<'PY'
import json, sys
manifest_path, deployed, impl, validation, prior, built_at, builder = sys.argv[1:8]
m = json.load(open(manifest_path))
json.dump({
    "deployed_repository_commit": deployed,
    "implementation_baseline": impl,
    "validation_executable_baseline": validation,
    "prior_deploy_baseline": prior,
    "governance_merge_commit": m.get("governance_merge_commit"),
    "application_delta_governed_by_manifest": True,
    "migration_delta_allowed": bool(m["migration_delta_allowed"]),
    "approved_application_paths": sorted(m["approved_application_paths"]),
    "approved_operational_paths": sorted(m["approved_operational_paths"]),
    "built_at_utc": built_at,
    "builder": builder,
    "artifact_type": "git-archive",
}, sys.stdout, indent=2, sort_keys=True)
sys.stdout.write("\n")
PY

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
source_ref                    : $SOURCE_REF
deployed_repository_commit    : $DEPLOYED_SHA
implementation_baseline       : $IMPL_SHA
validation_executable_baseline: $VALIDATION_SHA
prior_deploy_baseline         : $PRIOR_SHA
provenance_guard              : PASS (curated source, lineage, no migration, blob-exact approved delta)
built_at_utc                  : $BUILT_AT
builder                       : $BUILDER
archive                       : $ARCHIVE
archive_sha256                : $ARCHIVE_SHA
marker                        : $MARKER (embedded at archive root → /opt/workbench/app/DEPLOYED_BUILD_INFO.json)
============================================================
Next (SEPARATELY AUTHORIZED — not performed here): upload the archive to the S3 bootstrap key the box
pulls, then deploy with ambient ENFORCE on the ISOLATED validation box. Record archive_sha256 above;
the box-side gate re-computes it and compares.
EOF
