"""Cycle 2C — VALIDATION-2 STRUCTURAL PREFLIGHT, custodian-only and value-blind.

Owner ruling 2026-08-20: authorized as a custodian-only, value-blind structural verification via
the P6/P9/snapshot chain. ⛔ ZERO GetObject against any of the six sealed Validation-2 objects.

WHY THIS PATH RATHER THAN READING THE SEALED PARQUET
    The registered consumption boundary is the first successful exposure of a withheld economic
    observation. Fetching a sealed parquet to inspect its date column still delivers the whole
    object, so "we ignored the price columns" would not survive that rule. This producer never
    contacts the sealed store at all. It reads the PRE-SEALING snapshot -- the pinned source the
    sealed objects were exported from -- through the same audited custodian code that produced P6
    and P9, whose specification permits these reads ONLY for the sealing/custodian process.

TWO CLAIMS, KEPT APART ON PURPOSE
    DIRECTLY VERIFIED from the pre-sealing source
        session count, session-list hash, first/last session, formation/realization arithmetic,
        fold geometry, per-table content commitments recomputed and compared against P6.
    BOUND TO THE SEALED OBJECTS WITHOUT READING THEM
        each VersionId corresponds to the object uploaded from that committed source content,
        because its checksum was validated server-side at write and is frozen in the upload
        manifest.
    The second is a WEAKER claim than the first and the record says so. Collapsing both into
    "verified" is exactly the blur this program exists to prevent.

FAIL-CLOSED
    Anything other than 850 -> 69 formation -> 6 realization -> 775 eligible -> 5 x 155 -> 0
    remainder, with session-list hash 54e8d1f1..., stops at STRUCTURAL_POPULATION_MISMATCH. No
    repair, no reinterpretation, and still no sealed-object read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from sealed_partition_commitment import (  # noqa: E402
    SNAPSHOT_SHA256,
    _governed_session_check,
    _session_list,
    commit_window,
    open_snapshot,
    schema_identity,
)

REFUSAL = "VALIDATION2_NOT_READY:STRUCTURAL_POPULATION_MISMATCH"
WINDOW = "oos"                      # the S3 prefix name; the ROLE is Validation-2
REGISTRATION = "93ee468801c92edd9dd1ba49944b381a6d9172c2e22f9bcc76a9dcbe8541af57"
PARTITION_IDENTITY = "3b3910d00395d90189b94fd0f9901811b1813905f17219010b336c567cfa1296"
EXPECTED = {
    "sessions": 850,
    "session_list_sha256": "54e8d1f11e8934a3482e5eeae651fb83aaf6974a75e63c52f7eee9d986c79003",
    "first_session": "2023-02-17",
    "last_session": "2026-07-10",
    "formation_exclude_sessions": 69,
    "realization_horizon": 6,
    "eligible_sessions": 775,
    "folds": 5,
    "sessions_per_fold": 155,
    "remainder": 0,
}
P6_OOS_CONTENT = "a0595fd8179ca22e47afd90a55ff449239fe87c29b88a6ec5a0ddcbbf020932f"


class PreflightRefused(RuntimeError):
    pass


def _canonical(o: dict) -> bytes:
    return (json.dumps(o, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def fold_ordinals(eligible_first: int, per_fold: int, folds: int) -> list:
    return [{"fold": i + 1,
             "first_ordinal": eligible_first + i * per_fold,
             "last_ordinal": eligible_first + i * per_fold + per_fold - 1,
             "sessions": per_fold} for i in range(folds)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cycle 2C Validation-2 structural preflight")
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--upload-manifest", required=True)
    ap.add_argument("--structural-manifest", required=True, help="P9")
    ap.add_argument("--content-commitment", required=True, help="P6")
    ap.add_argument("--produced-at", required=True)
    ap.add_argument("--custodian", required=True)
    ap.add_argument("--emit", required=True)
    args = ap.parse_args(argv)

    up = json.loads(Path(args.upload_manifest).read_text(encoding="utf-8"))
    p9 = json.loads(Path(args.structural_manifest).read_text(encoding="utf-8"))
    p6 = json.loads(Path(args.content_commitment).read_text(encoding="utf-8"))

    problems: list = []

    # ── DIRECTLY VERIFIED from the pre-sealing source ──────────────────────────────────────────
    with open_snapshot(args.snapshot, SNAPSHOT_SHA256) as con:
        sess = _session_list(con, WINDOW)          # fails closed on count mismatch itself
        gov = _governed_session_check(con)
        window_commit = commit_window(con, WINDOW)
        tables = sorted(window_commit["tables"])
        schema = schema_identity(con, tables)

    if sess["observed_sessions"] != EXPECTED["sessions"]:
        problems.append(f"sessions {sess['observed_sessions']} != {EXPECTED['sessions']}")
    if sess["session_list_sha256"] != EXPECTED["session_list_sha256"]:
        problems.append(f"session_list_sha256 {sess['session_list_sha256']} != registered")
    if sess["first_session"] != EXPECTED["first_session"]:
        problems.append(f"first_session {sess['first_session']} != {EXPECTED['first_session']}")
    if sess["last_session"] != EXPECTED["last_session"]:
        problems.append(f"last_session {sess['last_session']} != {EXPECTED['last_session']}")

    # fold geometry, DERIVED from the transferred rule and CHECKED, never assumed
    eligible = (sess["observed_sessions"] - EXPECTED["formation_exclude_sessions"]
                - EXPECTED["realization_horizon"])
    per_fold, remainder = divmod(eligible, EXPECTED["folds"])
    if eligible != EXPECTED["eligible_sessions"]:
        problems.append(f"eligible {eligible} != {EXPECTED['eligible_sessions']}")
    if per_fold != EXPECTED["sessions_per_fold"]:
        problems.append(f"sessions_per_fold {per_fold} != {EXPECTED['sessions_per_fold']}")
    if remainder != EXPECTED["remainder"]:
        problems.append(f"remainder {remainder} != {EXPECTED['remainder']}")

    eligible_first = EXPECTED["formation_exclude_sessions"] + 1
    eligible_last = sess["observed_sessions"] - EXPECTED["realization_horizon"]
    folds = fold_ordinals(eligible_first, per_fold, EXPECTED["folds"])

    # independent recomputation of the partition content commitment against P6
    recomputed = window_commit["partition_content_sha256"]
    committed = p6["oos_partition"]["partition_content_sha256"]
    content_stable = (recomputed == committed == P6_OOS_CONTENT)
    if not content_stable:
        problems.append(f"partition content drifted: recomputed={recomputed} p6={committed}")

    # P9 cross-check: the pre-sealing structural manifest already carried this window
    p9w = p9["all_window_sessions"]["oos"]
    p9_agrees = (p9w["observed_sessions"] == sess["observed_sessions"]
                 and p9w["session_list_sha256"] == sess["session_list_sha256"]
                 and p9w["first_session"] == sess["first_session"]
                 and p9w["last_session"] == sess["last_session"])
    if not p9_agrees:
        problems.append("P9 structural manifest disagrees with the recomputed window structure")

    # ── BOUND to the sealed objects WITHOUT reading them ───────────────────────────────────────
    v2 = {k: v for k, v in up["objects"].items() if k.startswith("oos/")}
    if len(v2) != 6:
        problems.append(f"upload manifest lists {len(v2)} oos objects, expected 6")
    binding = []
    for key in sorted(v2):
        o = v2[key]
        binding.append({"key": key, "table": key.split("/")[-1].replace(".parquet", ""),
                        "version_id": o["version_id"], "sha256": o["sha256"],
                        "bytes": o["bytes"], "server_validated_at_write": o["server_validated"]})
        if not o.get("server_validated"):
            problems.append(f"{key} was not server-validated at write")
    partition_identity = hashlib.sha256(_canonical({"objects": [
        {"table": b["table"], "key": b["key"], "version_id": b["version_id"],
         "bytes": b["bytes"], "sha256": b["sha256"]} for b in binding]})).hexdigest()
    if partition_identity != PARTITION_IDENTITY:
        problems.append(f"partition identity {partition_identity} != registered "
                        f"{PARTITION_IDENTITY}")

    status = "STRUCTURAL_PREFLIGHT_PASS" if not problems else REFUSAL
    rec = {
        "record_type": "MR002_Validation2_StructuralPreflight",
        "version": "1.0",
        "produced_at_utc": args.produced_at,
        "custodian": args.custodian,
        "authority": "owner ruling 2026-08-20 — custodian-only, value-blind structural "
                     "verification via the P6/P9/snapshot chain",
        "bound_registration_identity": REGISTRATION,
        "value_blind": True,
        "sealed_store_getobject_calls": 0,
        "validation_2_objects_read": 0,
        "method": "the audited custodian producer sealed_partition_commitment.py, run against the "
                  "PRE-SEALING snapshot. The sealed store is never contacted.",

        "evidence_chain": [
            "pre-sealing snapshot apps/backend/data/mr002_research.duckdb "
            f"sha256={SNAPSHOT_SHA256}",
            f"-> P6 ValidationPartitionContentCommitment {p6['commitment_identity_sha256']} "
            f"(oos_partition content {committed})",
            f"-> P9 ValidationStructuralManifest {p9['manifest_identity_sha256']}",
            f"-> SealedStoreUploadManifest {up['manifest_identity_sha256']} "
            "(server-validated SHA-256 at write)",
            "-> six sealed VersionIds",
            f"-> Validation-2 partition identity {partition_identity}",
        ],

        "DIRECTLY_VERIFIED_from_the_pre_sealing_source": {
            "claim_strength": "STRONG — recomputed now, from the pinned source, by the audited "
                              "custodian producer, with the snapshot digest proved on both sides "
                              "of the read",
            "window_sessions": sess,
            "governed_calendar": gov,
            "formation_exclude_sessions": EXPECTED["formation_exclude_sessions"],
            "realization_horizon": EXPECTED["realization_horizon"],
            "eligible_sessions": eligible,
            "eligible_ordinal_range": [eligible_first, eligible_last],
            "folds": folds,
            "sessions_per_fold": per_fold,
            "remainder": remainder,
            "partition_content_sha256_recomputed": recomputed,
            "partition_content_matches_P6": content_stable,
            "p9_cross_check_agrees": p9_agrees,
            "schema_identity_sha256": schema.get("schema_identity_sha256"),
            "tables": tables,
        },

        "BOUND_to_the_sealed_objects_WITHOUT_reading_them": {
            "claim_strength": "WEAKER — this is a BINDING, not a direct verification. Each "
                              "VersionId corresponds to the object uploaded from the committed "
                              "source content because its checksum was validated server-side at "
                              "write and is frozen in the upload manifest. The sealed parquet "
                              "bytes were NOT hashed by this preflight, because doing so would "
                              "require a GetObject and would consume the opening.",
            "objects": binding,
            "partition_identity_sha256": partition_identity,
            "matches_registered_partition_identity": partition_identity == PARTITION_IDENTITY,
            "what_would_close_this_gap": "only a read of the six objects, which is exactly what "
                                         "the consumption boundary forbids before the opening "
                                         "grant. The gap is therefore STRUCTURAL and permanent "
                                         "until the opening; it is disclosed rather than closed.",
        },

        "status": status,
        "problems": problems,
        "boundary": "EVIDENCE ONLY. This record grants nothing, opens nothing, and does not "
                    "authorize the Validation-2 opening.",
    }
    rec["record_identity_sha256"] = hashlib.sha256(
        _canonical({k: v for k, v in rec.items()})).hexdigest()

    out = Path(args.emit)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_bytes(_canonical(rec))
    tmp.replace(out)

    print(json.dumps({
        "status": status,
        "sessions": sess["observed_sessions"],
        "session_list_sha256_matches": sess["session_list_sha256"]
        == EXPECTED["session_list_sha256"],
        "eligible": eligible, "folds": EXPECTED["folds"], "per_fold": per_fold,
        "remainder": remainder,
        "partition_content_matches_P6": content_stable,
        "p9_cross_check_agrees": p9_agrees,
        "partition_identity_matches": partition_identity == PARTITION_IDENTITY,
        "sealed_getobject_calls": 0,
        "problems": problems,
        "record_identity_sha256": rec["record_identity_sha256"],
        "emitted": str(out),
    }, indent=1))
    return 0 if not problems else 2


if __name__ == "__main__":
    sys.exit(main())
