#!/usr/bin/env bash
# O34 construction-start snapshot capture — NO row selection, NO broker calls.
set -euo pipefail

FREEZE_BODY_SHA256="80dfd8ec6d90182cdeabaab2d1457720ca417bcd5cb1511b4dd9d77989951bb0"
START_MERGE="811a808b7122c12e5948b92947879d327ca8cc29"
FREEZE_MERGE="a1f1fd3ccbd5f8209047d6e3f8663920abb0d04a"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
CAP="/opt/workbench/data/ops/adr0043_o34_acq_snapshots/${TS}"
sudo mkdir -p "${CAP}"
sudo chown ubuntu:ubuntu "${CAP}"

echo "capture_id=${TS}"
echo "capture_dir=${CAP}"
echo "freeze_body_sha256=${FREEZE_BODY_SHA256}"

SRC="/opt/workbench/data/workbench.sqlite"
PRE_META="$(stat --printf='%s %Y %i\n' "${SRC}")"
PRE_SHA="$(sha256sum "${SRC}" | awk '{print $1}')"
echo "sqlite_live_pre_meta=${PRE_META}"
echo "sqlite_live_pre_sha256=${PRE_SHA}"

if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "${SRC}" ".backup '${CAP}/workbench.sqlite.snapshot'"
else
  echo "sqlite3_missing=true"
  cp -a "${SRC}" "${CAP}/workbench.sqlite.snapshot"
fi

SNAP_SHA="$(sha256sum "${CAP}/workbench.sqlite.snapshot" | awk '{print $1}')"
SNAP_SIZE="$(stat --printf='%s\n' "${CAP}/workbench.sqlite.snapshot")"
echo "sqlite_snapshot_sha256=${SNAP_SHA}"
echo "sqlite_snapshot_size=${SNAP_SIZE}"

POST_META="$(stat --printf='%s %Y %i\n' "${SRC}")"
POST_SHA="$(sha256sum "${SRC}" | awk '{print $1}')"
echo "sqlite_live_post_meta=${POST_META}"
echo "sqlite_live_post_sha256=${POST_SHA}"

if [[ "${PRE_SHA}" == "${POST_SHA}" ]]; then
  MUT="NONE"
else
  MUT="LIVE_CHANGED_DURING_CAPTURE_EXTERNAL"
fi
echo "sqlite_capture_source_mutation=${MUT}"

hash_tree() {
  local root="$1"
  local out="$2"
  (cd "${root}" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "${out}"
  sha256sum "${out}" | awk '{print $1}'
}

if [[ -d /opt/workbench/data/bar_cache ]]; then
  BAR_MAN_SHA="$(hash_tree /opt/workbench/data/bar_cache "${CAP}/bar_cache.files.sha256")"
  echo "bar_cache_manifest_sha256=${BAR_MAN_SHA}"
  echo "bar_cache_file_count=$(wc -l < "${CAP}/bar_cache.files.sha256")"
fi

if [[ -d /opt/workbench/data/market_projection ]]; then
  MP_MAN_SHA="$(hash_tree /opt/workbench/data/market_projection "${CAP}/market_projection.files.sha256")"
  echo "market_projection_manifest_sha256=${MP_MAN_SHA}"
  echo "market_projection_file_count=$(wc -l < "${CAP}/market_projection.files.sha256")"
fi

export CAP TS FREEZE_BODY_SHA256 START_MERGE FREEZE_MERGE
export PRE_SHA POST_SHA PRE_META POST_META SNAP_SHA SNAP_SIZE MUT SRC
python3 <<'PY'
import hashlib, json, os, time
from pathlib import Path

cap = Path(os.environ["CAP"])

def file_sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

bar_p = cap / "bar_cache.files.sha256"
mp_p = cap / "market_projection.files.sha256"
bar_h = file_sha(bar_p)
mp_h = file_sha(mp_p)
mkt_status = "BOUND" if bar_h and mp_h else "INCOMPLETE"

summary = {
    "capture_id": os.environ["TS"],
    "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "host": os.uname().nodename,
    "freeze_document_id": "ADR0043-PH0-D-BOX-O34-ACQ-FREEZE-001",
    "freeze_body_sha256": os.environ["FREEZE_BODY_SHA256"],
    "start_ruling_id": "ADR0043-PH0-D-BOX-O34-ACQ-START-001",
    "start_merge": os.environ["START_MERGE"],
    "selection_performed": False,
    "broker_calls": [],
    "sources": {
        "SRC-APP-AUDIT-PLAN-CKPT-TERM-001": {
            "live_path": os.environ["SRC"],
            "live_pre_sha256": os.environ["PRE_SHA"],
            "live_post_sha256": os.environ["POST_SHA"],
            "live_pre_meta_size_mtime_inode": os.environ["PRE_META"].strip(),
            "live_post_meta_size_mtime_inode": os.environ["POST_META"].strip(),
            "immutable_snapshot_path": str(cap / "workbench.sqlite.snapshot"),
            "snapshot_sha256": os.environ["SNAP_SHA"],
            "snapshot_size_bytes": int(os.environ["SNAP_SIZE"]),
            "source_mutation_by_capture": os.environ["MUT"],
            "binding_status": "BOUND",
        },
        "SRC-ACCT3-PAPER-PRIOR-AUTH-001": {
            "shares_snapshot_with": "SRC-APP-AUDIT-PLAN-CKPT-TERM-001",
            "snapshot_sha256": os.environ["SNAP_SHA"],
            "binding_status": "BOUND",
        },
        "SRC-MKT-QUOTE-LAWFUL-001": {
            "bar_cache_root": "/opt/workbench/data/bar_cache",
            "bar_cache_manifest_path": str(bar_p),
            "bar_cache_manifest_sha256": bar_h,
            "market_projection_root": "/opt/workbench/data/market_projection",
            "market_projection_manifest_path": str(mp_p),
            "market_projection_manifest_sha256": mp_h,
            "binding_status": mkt_status,
            "s3_version_ids": [],
            "note": (
                "Local lawful stores pinned by recursive file SHA-256 manifests; "
                "no S3 Version IDs declared for these roots"
            ),
        },
        "SRC-GOV-GIT-IMMUTABLE-001": {
            "status": "BOUND_VIA_GOVERNING_REFS",
            "freeze_publish_merge": os.environ["FREEZE_MERGE"],
            "start_merge": os.environ["START_MERGE"],
            "binding_status": "BOUND",
        },
    },
}

required = [
    "SRC-APP-AUDIT-PLAN-CKPT-TERM-001",
    "SRC-ACCT3-PAPER-PRIOR-AUTH-001",
    "SRC-MKT-QUOTE-LAWFUL-001",
    "SRC-GOV-GIT-IMMUTABLE-001",
]
all_bound = all(
    summary["sources"][k].get("binding_status") == "BOUND" for k in required
)
summary["all_mandatory_snapshots_bound"] = all_bound
summary["record_selection_permitted"] = all_bound

(cap / "capture_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print("SUMMARY_JSON_BEGIN")
print(json.dumps(summary, indent=2))
print("SUMMARY_JSON_END")
print(f"all_mandatory_snapshots_bound={all_bound}")
PY
