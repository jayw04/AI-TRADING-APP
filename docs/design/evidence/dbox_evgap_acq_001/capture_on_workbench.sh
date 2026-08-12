#!/usr/bin/env bash
# EVIDENCE-GAP Stage 1 — immutable source snapshot capture.
# NO SQL SELECT, NO candidate-row queries, NO joins/filters,
# NO recoverability file-content inspection, NO O5 anchor search,
# NO broker calls, NO production modification.
set -euo pipefail

FREEZE_BODY_SHA256="af7693f4b97fd7d9d4ad642ab1af47e9e9a2a8cd680f6a26c4d01fee8d57967e"
AUTH_MERGE="29eece313b1b2e7541a20c0440101455b78b106d"
CONTENT_TIP="853f5f620d3089e66e2a54261b33ee189e79c7cb"
SEAL_MERGE="ec243c57bb2cdd9e59f903a65489ea6298b99c72"
START_MERGE="eb9b66043c4d70b407b69d131581de1eda5d3af5"
PROD_EXCLUDED="b0058bf335628f8dbde09a93915314f3a1f7743b"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
CAP="/opt/workbench/data/ops/adr0043_evgap_acq_snapshots/${TS}"
sudo mkdir -p "${CAP}"
sudo chown ubuntu:ubuntu "${CAP}"

HOST="$(hostname)"
OPERATOR="${USER:-unknown}"
echo "capture_id=${TS}"
echo "capture_dir=${CAP}"
echo "host=${HOST}"
echo "operator=${OPERATOR}"
echo "freeze_body_sha256=${FREEZE_BODY_SHA256}"
echo "start_merge=${START_MERGE}"

# --- production exclusion check (administrative; no app mutation) ---
PROD_STATUS="UNUSED_CONFIRMED"
if command -v git >/dev/null 2>&1 && [[ -d /opt/workbench/.git ]]; then
  BOX_HEAD="$(git -C /opt/workbench rev-parse HEAD 2>/dev/null || true)"
  echo "box_git_head=${BOX_HEAD:-UNAVAILABLE}"
  if [[ "${BOX_HEAD}" == "${PROD_EXCLUDED}"* ]] || [[ "${BOX_HEAD}" == "${PROD_EXCLUDED}" ]]; then
    # Exact match on full sha
    if [[ "${BOX_HEAD}" == "${PROD_EXCLUDED}" ]]; then
      echo "WARN: box HEAD equals excluded production commit — capture continues read-only; modification forbidden"
      PROD_STATUS="REFERENCE_ONLY_HEAD_MATCHES_EXCLUDED_NO_MODIFY"
    fi
  fi
else
  BOX_HEAD="UNAVAILABLE"
fi
# Docker compose reference-only: do not start/restart/modify stacks
echo "production_b0058bf_status=${PROD_STATUS}"
echo "docker_mutation=none"

# --- SRC-APP-AUDIT + ACCT3: hash-copy sqlite (no SQL) ---
SRC="/opt/workbench/data/workbench.sqlite"
SQLITE_OUTCOME="UNAVAILABLE"
PRE_SHA=""
POST_SHA=""
PRE_META=""
POST_META=""
SNAP_SHA=""
SNAP_SIZE="0"
MUT="n/a"

if [[ -f "${SRC}" ]]; then
  PRE_META="$(stat --printf='%s %Y %i\n' "${SRC}")"
  PRE_SHA="$(sha256sum "${SRC}" | awk '{print $1}')"
  echo "sqlite_live_pre_meta=${PRE_META}"
  echo "sqlite_live_pre_sha256=${PRE_SHA}"

  # Prefer filesystem copy of bytes — avoid sqlite3 .backup which may touch pages.
  # Use cp -a for immutable byte identity of the live file at capture instant.
  cp -a "${SRC}" "${CAP}/workbench.sqlite.snapshot"
  SNAP_SHA="$(sha256sum "${CAP}/workbench.sqlite.snapshot" | awk '{print $1}')"
  SNAP_SIZE="$(stat --printf='%s\n' "${CAP}/workbench.sqlite.snapshot")"
  echo "sqlite_snapshot_sha256=${SNAP_SHA}"
  echo "sqlite_snapshot_size=${SNAP_SIZE}"

  POST_META="$(stat --printf='%s %Y %i\n' "${SRC}")"
  POST_SHA="$(sha256sum "${SRC}" | awk '{print $1}')"
  echo "sqlite_live_post_meta=${POST_META}"
  echo "sqlite_live_post_sha256=${POST_SHA}"

  if [[ "${PRE_SHA}" != "${POST_SHA}" ]] || [[ "${PRE_SHA}" != "${SNAP_SHA}" ]]; then
    MUT="LIVE_CHANGED_OR_COPY_MISMATCH"
    SQLITE_OUTCOME="MUTATED_DURING_CAPTURE"
  else
    MUT="NONE"
    SQLITE_OUTCOME="CAPTURED"
  fi
  echo "sqlite_capture_source_mutation=${MUT}"
  echo "sqlite_outcome=${SQLITE_OUTCOME}"
else
  echo "sqlite_outcome=UNAVAILABLE"
fi

# --- SRC-MKT: recursive file SHA manifests (names+hashes only; no quote content eval) ---
hash_tree() {
  local root="$1"
  local out="$2"
  (cd "${root}" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "${out}"
  sha256sum "${out}" | awk '{print $1}'
}

MKT_OUTCOME="UNAVAILABLE"
BAR_MAN_SHA=""
MP_MAN_SHA=""
BAR_COUNT="0"
MP_COUNT="0"
if [[ -d /opt/workbench/data/bar_cache ]] && [[ -d /opt/workbench/data/market_projection ]]; then
  BAR_MAN_SHA="$(hash_tree /opt/workbench/data/bar_cache "${CAP}/bar_cache.files.sha256")"
  MP_MAN_SHA="$(hash_tree /opt/workbench/data/market_projection "${CAP}/market_projection.files.sha256")"
  BAR_COUNT="$(wc -l < "${CAP}/bar_cache.files.sha256" | tr -d ' ')"
  MP_COUNT="$(wc -l < "${CAP}/market_projection.files.sha256" | tr -d ' ')"
  if [[ -n "${BAR_MAN_SHA}" && -n "${MP_MAN_SHA}" ]]; then
    MKT_OUTCOME="CAPTURED"
  else
    MKT_OUTCOME="UNPINNABLE"
  fi
elif [[ -d /opt/workbench/data/bar_cache ]] || [[ -d /opt/workbench/data/market_projection ]]; then
  MKT_OUTCOME="UNPINNABLE"
  [[ -d /opt/workbench/data/bar_cache ]] && BAR_MAN_SHA="$(hash_tree /opt/workbench/data/bar_cache "${CAP}/bar_cache.files.sha256")"
  [[ -d /opt/workbench/data/market_projection ]] && MP_MAN_SHA="$(hash_tree /opt/workbench/data/market_projection "${CAP}/market_projection.files.sha256")"
fi
echo "mkt_outcome=${MKT_OUTCOME}"
echo "bar_cache_manifest_sha256=${BAR_MAN_SHA}"
echo "market_projection_manifest_sha256=${MP_MAN_SHA}"

# --- SRC-O5: hash governing git evidence tree paths (tree identity only; no anchor search) ---
O5_OUTCOME="UNAVAILABLE"
O5_MAN_SHA=""
O5_ROOT=""
# Prefer repo on box if present; else note UNAVAILABLE for on-box tree (Git pins still bound via SRC-GOV)
for candidate in /opt/workbench/AI-TRADING-APP /opt/workbench/ai-trading-app /home/ubuntu/AI-TRADING-APP; do
  if [[ -d "${candidate}/docs/design/evidence" ]]; then
    O5_ROOT="${candidate}/docs/design/evidence"
    break
  fi
done
if [[ -n "${O5_ROOT}" ]]; then
  O5_MAN_SHA="$(hash_tree "${O5_ROOT}" "${CAP}/o5_git_evidence_tree.files.sha256")"
  if [[ -n "${O5_MAN_SHA}" ]]; then
    O5_OUTCOME="CAPTURED"
  else
    O5_OUTCOME="UNPINNABLE"
  fi
fi
echo "o5_outcome=${O5_OUTCOME}"
echo "o5_evidence_root=${O5_ROOT:-none}"
echo "o5_tree_manifest_sha256=${O5_MAN_SHA}"

# --- SRC-GOV-GIT: already bound via governing commit pins (no content search) ---
GOV_OUTCOME="CAPTURED"

export CAP TS FREEZE_BODY_SHA256 AUTH_MERGE CONTENT_TIP SEAL_MERGE START_MERGE
export PROD_EXCLUDED PROD_STATUS BOX_HEAD HOST OPERATOR
export SQLITE_OUTCOME PRE_SHA POST_SHA PRE_META POST_META SNAP_SHA SNAP_SIZE MUT SRC
export MKT_OUTCOME BAR_MAN_SHA MP_MAN_SHA BAR_COUNT MP_COUNT
export O5_OUTCOME O5_MAN_SHA O5_ROOT GOV_OUTCOME

python3 <<'PY'
import hashlib, json, os, time
from pathlib import Path

cap = Path(os.environ["CAP"])

def file_sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

bar_p = cap / "bar_cache.files.sha256"
mp_p = cap / "market_projection.files.sha256"
o5_p = cap / "o5_git_evidence_tree.files.sha256"

sqlite_outcome = os.environ["SQLITE_OUTCOME"]
mkt_outcome = os.environ["MKT_OUTCOME"]
o5_outcome = os.environ["O5_OUTCOME"]
gov_outcome = os.environ["GOV_OUTCOME"]

sources = {
    "SRC-APP-AUDIT-PLAN-CKPT-TERM-001": {
        "live_path": os.environ.get("SRC", ""),
        "live_pre_sha256": os.environ.get("PRE_SHA") or None,
        "live_post_sha256": os.environ.get("POST_SHA") or None,
        "live_pre_meta_size_mtime_inode": (os.environ.get("PRE_META") or "").strip() or None,
        "live_post_meta_size_mtime_inode": (os.environ.get("POST_META") or "").strip() or None,
        "immutable_snapshot_path": str(cap / "workbench.sqlite.snapshot") if sqlite_outcome != "UNAVAILABLE" else None,
        "snapshot_sha256": os.environ.get("SNAP_SHA") or None,
        "snapshot_size_bytes": int(os.environ.get("SNAP_SIZE") or "0"),
        "source_mutation_by_capture": os.environ.get("MUT"),
        "stage1_outcome": sqlite_outcome,
        "commands": [
            f"stat {os.environ.get('SRC','')}",
            f"sha256sum {os.environ.get('SRC','')}",
            f"cp -a {os.environ.get('SRC','')} {cap}/workbench.sqlite.snapshot",
        ],
    },
    "SRC-ACCT3-PAPER-PRIOR-AUTH-001": {
        "shares_snapshot_with": "SRC-APP-AUDIT-PLAN-CKPT-TERM-001",
        "snapshot_sha256": os.environ.get("SNAP_SHA") or None,
        "stage1_outcome": sqlite_outcome,
    },
    "SRC-MKT-QUOTE-LAWFUL-001": {
        "bar_cache_root": "/opt/workbench/data/bar_cache",
        "bar_cache_manifest_path": str(bar_p) if bar_p.exists() else None,
        "bar_cache_manifest_sha256": os.environ.get("BAR_MAN_SHA") or file_sha(bar_p),
        "bar_cache_file_count": int(os.environ.get("BAR_COUNT") or "0"),
        "market_projection_root": "/opt/workbench/data/market_projection",
        "market_projection_manifest_path": str(mp_p) if mp_p.exists() else None,
        "market_projection_manifest_sha256": os.environ.get("MP_MAN_SHA") or file_sha(mp_p),
        "market_projection_file_count": int(os.environ.get("MP_COUNT") or "0"),
        "s3_version_ids": [],
        "stage1_outcome": mkt_outcome,
        "note": (
            "Recursive file SHA-256 manifests only; no quote-content evaluation; "
            "no S3 Version IDs for these roots"
        ),
    },
    "SRC-O5-TIERA-LOCATE-CORPUS-001": {
        "evidence_tree_root": os.environ.get("O5_ROOT") or None,
        "tree_manifest_path": str(o5_p) if o5_p.exists() else None,
        "tree_manifest_sha256": os.environ.get("O5_MAN_SHA") or file_sha(o5_p),
        "stage1_outcome": o5_outcome,
        "note": (
            "Tree identity hash of docs/design/evidence only; O5 anchor content "
            "search NOT performed at Stage 1"
        ),
    },
    "SRC-GOV-GIT-IMMUTABLE-001": {
        "status": "BOUND_VIA_GOVERNING_REFS",
        "authorization_merge": os.environ["AUTH_MERGE"],
        "freeze_content_tip": os.environ["CONTENT_TIP"],
        "freeze_seal_merge": os.environ["SEAL_MERGE"],
        "start_merge": os.environ["START_MERGE"],
        "stage1_outcome": gov_outcome,
    },
}

mandatory = [
    "SRC-APP-AUDIT-PLAN-CKPT-TERM-001",
    "SRC-ACCT3-PAPER-PRIOR-AUTH-001",
    "SRC-MKT-QUOTE-LAWFUL-001",
    "SRC-O5-TIERA-LOCATE-CORPUS-001",
    "SRC-GOV-GIT-IMMUTABLE-001",
]
all_captured = all(sources[k]["stage1_outcome"] == "CAPTURED" for k in mandatory)

summary = {
    "document_id": "ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-OPENING-001",
    "stage": 1,
    "capture_id": os.environ["TS"],
    "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "host": os.environ["HOST"],
    "operator": os.environ["OPERATOR"],
    "freeze_document_id": "ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-FREEZE-001",
    "freeze_body_sha256": os.environ["FREEZE_BODY_SHA256"],
    "start_ruling_id": "ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-START-001",
    "start_merge": os.environ["START_MERGE"],
    "authorization_merge": os.environ["AUTH_MERGE"],
    "freeze_content_tip": os.environ["CONTENT_TIP"],
    "freeze_seal_merge": os.environ["SEAL_MERGE"],
    "production_excluded_commit": os.environ["PROD_EXCLUDED"],
    "production_b0058bf_status": os.environ["PROD_STATUS"],
    "box_git_head": os.environ.get("BOX_HEAD") or None,
    "on_box_capture_root": str(cap),
    "selection_performed": False,
    "sql_select_performed": False,
    "o5_anchor_search_performed": False,
    "recoverability_inspection_performed": False,
    "broker_calls": [],
    "sources": sources,
    "all_mandatory_sources_captured": all_captured,
    "stage2_permitted": all_captured,
    "gates": "CLOSED",
    "d_wire": "BLOCKED",
}

(cap / "capture_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print("SUMMARY_JSON_BEGIN")
print(json.dumps(summary, indent=2))
print("SUMMARY_JSON_END")
print(f"all_mandatory_sources_captured={all_captured}")
PY
