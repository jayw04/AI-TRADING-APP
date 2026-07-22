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
# ── PROVENANCE MODEL (path-scoped reviewed baseline, 2026-07-22) ──────────────────────────────
# TWO distinct identities, never conflated:
#   • ADR-0043 IMPLEMENTATION baseline — the reviewed ADR-0043 executable advancement. The governed
#     ADR-0043 paths in the deployed tree must be BYTE-IDENTICAL to this commit, so the ENFORCE box
#     runs exactly the reviewed loss-control/settlement code. Default ea6db6e (#463 settlement
#     barrier), which SUPERSEDES the historical PR8 baseline c8b3ac24 (recorded, not used as the gate).
#   • DEPLOYED repository commit — the complete reviewed tree being packaged (an explicit SHA).
# The delta between the two is PERMITTED but must be enumerated and classified, and must fall
# entirely OUTSIDE the governed ADR-0043 path set (a governed-path change after the baseline is a
# hard refusal). Override the implementation baseline only via ADR0043_IMPLEMENTATION_SHA with review.
ADR0043_ORIGINAL_BASELINE="c8b3ac24b839d7b19c40979a9e4be859151dbab7"   # historical PR8, recorded only
IMPL_SHA="${ADR0043_IMPLEMENTATION_SHA:-ea6db6e6d5dc338196ffca9919a7a2e2643e1f6c}"

# The governed ADR-0043 executable / structural-checker / governing-doc paths (from #463's own
# change set, d03af06..ea6db6e, plus the pre-existing canary manifest+runbook the ENFORCE deploy is
# governed by). These MUST equal the implementation baseline in the deployed tree.
GOVERNED_PATHS="
apps/backend/app/orders/settlement.py
apps/backend/scripts/adr0043_canary_lib.py
apps/backend/scripts/adr0043_canary_run.py
apps/backend/scripts/adr0043_churn_driver.py
apps/backend/scripts/check_settlement_barrier.py
apps/backend/scripts/check_settlement_barrier.sh
scripts/reconcile_stuck_orders.py
docs/implementation/ADR0043_SettlementBarrier_BaselineDiscrepancy_v1.0.md
docs/implementation/ADR0043_Canary_Manifest_v1.0.md
docs/runbook/ADR0043_Live_Canary_Runbook.md
"

command -v git >/dev/null || { echo "FATAL: git is required — run on the build machine, not the box."; exit 1; }
git rev-parse --git-dir >/dev/null 2>&1 \
  || { echo "FATAL: not a git repository. Provenance MUST be produced where .git exists."; exit 1; }

# (1) The source ref MUST be an explicit immutable commit SHA, never a moving branch/tag/remote ref.
#     A raw object id has no symbolic full name; a branch resolves to refs/heads/… etc.
SYMBOLIC="$(git rev-parse --symbolic-full-name "$SOURCE_REF" 2>/dev/null || true)"
if [ -n "$SYMBOLIC" ]; then
  echo "FATAL: '$SOURCE_REF' is a moving ref ($SYMBOLIC), not an immutable commit SHA."
  echo "       Pass the explicit reviewed commit id so a later push cannot change what deploys."
  exit 1
fi
DEPLOYED_SHA="$(git rev-parse --verify --quiet "${SOURCE_REF}^{commit}" || true)"
if [ -z "$DEPLOYED_SHA" ]; then
  echo "FATAL: '$SOURCE_REF' does not resolve to a commit."
  exit 1
fi

# (2) Ancestry proof: the ADR-0043 implementation baseline must be an ancestor of the deployed tree,
#     else the archive would not contain the reviewed loss-control/settlement code.
if git merge-base --is-ancestor "$IMPL_SHA" "$DEPLOYED_SHA"; then
  ANCESTRY="verified"
else
  echo "FATAL: ADR-0043 implementation ${IMPL_SHA} is NOT an ancestor of ${DEPLOYED_SHA}."
  echo "       The archive would not contain the ADR-0043 code. Refusing to build."
  exit 2
fi

# (3) GOVERNED-PATH INVARIANT — the ADR-0043 executable/checker/governing files in the deployed tree
#     must be BYTE-IDENTICAL to the implementation baseline. This is the ENFORCE safety property:
#     "the ADR-0043 code that runs is exactly the reviewed code." A change to ANY governed path after
#     the baseline is a hard refusal (it would mean unreviewed ADR-0043 code rides into the box).
GOVERNED_LIST="$(printf '%s\n' $GOVERNED_PATHS | sed '/^$/d')"
GOVERNED_DELTA="$(git diff --name-only "$IMPL_SHA" "$DEPLOYED_SHA" -- $GOVERNED_LIST || true)"
if [ -n "$GOVERNED_DELTA" ]; then
  echo "FATAL: governed ADR-0043 path(s) changed after the implementation baseline ${IMPL_SHA}:"
  printf '  %s\n' $GOVERNED_DELTA
  echo "       The ADR-0043 code that runs ENFORCE must equal the reviewed baseline. Refusing to build."
  exit 3
fi
GOVERNED_MATCH=true

# (4) REVIEWED SUPERSET DELTA — every application change between the baseline and the deployed tree is
#     enumerated and classified. It is PERMITTED (it is reviewed, merged, non-ADR-0043 code), but it
#     must fall entirely OUTSIDE the governed set — which (3) already guarantees, re-asserted here so
#     the classification cannot silently include a governed path.
SUPERSET_DELTA="$(git diff --name-only "$IMPL_SHA" "$DEPLOYED_SHA" -- apps/ scripts/ | sed '/^$/d' || true)"
for f in $SUPERSET_DELTA; do
  for g in $GOVERNED_LIST; do
    if [ "$f" = "$g" ]; then
      echo "FATAL: superset delta ${f} is inside the governed ADR-0043 set — cannot classify as non-ADR-0043."
      exit 3
    fi
  done
done

BUILT_AT="$(date -u +%FT%TZ)"
BUILDER="$(git config user.email 2>/dev/null || echo unknown)@$(hostname 2>/dev/null || echo unknown-host)"

mkdir -p "$OUT_DIR"
MARKER="$OUT_DIR/DEPLOYED_BUILD_INFO.json"
# Enumerate the reviewed superset delta as a valid JSON array of file paths (comma-separated,
# one per line, no trailing comma). classification: non-ADR-0043.
DELTA_JSON="$(printf '%s\n' $SUPERSET_DELTA | sed '/^$/d' \
  | awk '{ printf "%s    \"%s\"", (NR>1 ? ",\n" : ""), $0 } END { if (NR) printf "\n" }')"
cat > "$MARKER" <<EOF
{
  "deployed_repository_commit": "$DEPLOYED_SHA",
  "adr0043_original_baseline_commit": "$ADR0043_ORIGINAL_BASELINE",
  "adr0043_implementation_commit": "$IMPL_SHA",
  "adr0043_governed_paths_match": $GOVERNED_MATCH,
  "implementation_ancestry_verified": true,
  "application_delta_after_adr0043_baseline": [
${DELTA_JSON}
  ],
  "reviewed_superset_delta_classification": "reviewed_non_adr0043_superset",
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
source_ref                    : $SOURCE_REF (explicit immutable commit SHA)
deployed_repository_commit    : $DEPLOYED_SHA
adr0043_implementation_commit : $IMPL_SHA (governed ADR-0043 paths pinned here)
adr0043_original_baseline     : $ADR0043_ORIGINAL_BASELINE (historical PR8, recorded only)
implementation_ancestry       : $ANCESTRY (git merge-base --is-ancestor, build machine)
adr0043_governed_paths_match  : $GOVERNED_MATCH (byte-identical to the implementation baseline)
reviewed_superset_delta       : $(printf '%s ' $SUPERSET_DELTA)(classification: reviewed_non_adr0043_superset)
built_at_utc                  : $BUILT_AT
builder                       : $BUILDER
archive                       : $ARCHIVE
archive_sha256                : $ARCHIVE_SHA
marker                        : $MARKER (embedded at archive root → /opt/workbench/app/DEPLOYED_BUILD_INFO.json)
============================================================
Next: upload the archive to the S3 bootstrap key the box pulls, e.g.
  aws s3 cp "$ARCHIVE" "s3://<bucket>/bootstrap/code.tgz"
then deploy with ambient ENFORCE on the ISOLATED validation box:
  LOSS_CONTROL_MODE=ENFORCE bash deploy/aws/provision-from-s3.sh
Record archive_sha256 above; the box-side gate re-computes it and compares.
EOF
