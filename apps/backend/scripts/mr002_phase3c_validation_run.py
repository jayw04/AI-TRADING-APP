"""MR-002 — THE governed Phase 3C validation execution. One indivisible run.

Authorized by MR002_Phase3C_ExecutionAuthorization_v2.0 (c53edf89...) under the sealed
countersignature MR002_Phase3C_ExecutionCountersignature_v2.0 (410627f2...) and the bound
validation package v2.1 (593a908b...), as amended by the credential-readiness control
amendment (owner ruling 2026-08-19).

THE SEQUENCE IS INDIVISIBLE. There is no inspection point and no discretionary decision after the
first sealed read:

    6 sealed reads -> opened-object ledger -> 4 reference reads -> deterministic 10-table
    materialization -> immediate frozen A/B/C replay -> validation decision -> (caller restores
    containment)

This launcher orchestrates already-bound components and adds NO economic, numerical or data
semantics of its own. It selects no parameters, computes no OOS metric, and never re-reads.

`--reader fixture` runs the identical sequence against local Parquet with the governed
FixtureReader, so the whole path can be proven with zero sealed access before the latch opens.
`--reader s3` is the governed run.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys

sys.path.insert(0, "/work/apps/backend")

from app.research.mr002 import stage3_route as route  # noqa: E402
from app.research.mr002.dataset import FrozenDataset  # noqa: E402
from app.research.mr002.phase3b.readers import (  # noqa: E402
    FixtureReader,
    PinnedObject,
    S3PinnedReader,
)
from app.research.mr002.phase3c import (  # noqa: E402
    VALIDATION_CONFIGS,
    VALIDATION_WINDOW_END,
    VALIDATION_WINDOW_START,
    IntegrityFailure,
)
from app.research.mr002.phase3c import folds as F  # noqa: E402
from app.research.mr002.phase3c import gates as G  # noqa: E402
from app.research.mr002.phase3c.credential_readiness import (  # noqa: E402
    acquire_reader_credentials,
)
from app.research.mr002.phase3c.durable_evidence import (  # noqa: E402
    EvidenceJournal,
    JournalingReader,
    materialization_complete,
    terminal,
)
from app.research.mr002.phase3c.materialize import TableSource, materialize  # noqa: E402
from app.research.mr002.phase3c.replay import run_config_validation  # noqa: E402
from app.research.mr002.runner import CONFIGS  # noqa: E402

BUCKET = "workbench-mr002-sealed-219024422756"
READER_ROLE = "arn:aws:iam::219024422756:role/mr002-validation-reader"
SESSION_NAME = "mr002-p3c-validation-v1"
OOS_PREFIX = "oos/"

# The 6 SEALED validation objects. These CONSUME the validation opening and are ledgered.
SEALED = {
    "actions": ("validation/actions.parquet", "wJ6QFkebGAidGzoWO.qzUMYjy.b6zLrx"),
    "anchors": ("validation/anchors.parquet", "7Br5aFGWFabpIJmPgwUBQRgdhQwc2GIK"),
    "etf_prices": ("validation/etf_prices.parquet", ".mZyHPHgamUNlHpdePGQZq.djUapjrpo"),
    "prices": ("validation/prices.parquet", "eC8XZGBPXa6vPDW_WKPvwV8HtF05_tty"),
    "sic_observations": ("validation/sic_observations.parquet",
                         "OkvwAKSX8W8W3HJiBoxZ9KC4ON6Vgj5t"),
    "universe": ("validation/universe.parquet", "8Le8rLdT2wvdSenjEQdPaUAgdmSzx3ZO"),
}
# The 4 REFERENCE objects. Identity-bound, NOT sealed, and they do NOT consume the opening.
REFERENCE = {
    "crosswalk": ("reference/crosswalk.parquet", "ux3JpvSp7lSneFcMHhxRZ_Tp6_gx60eK"),
    "sic_mapping": ("reference/sic_mapping.parquet", "_wAa1EJ0wECpUcd4DH7KhrYsYl765kWL"),
    "predecessor_overrides": ("reference/predecessor_overrides.parquet",
                              "Srj0T5D.VqjtTULkrLwynvhPeWf422I7"),
    "security_sector_overrides": ("reference/security_sector_overrides.parquet",
                                  "MuimDnyOSLtRX6BaG2Ll525ox9Hoz6ns"),
}
ZERO = "0" * 64

# Set by main() as soon as the journal exists, so the terminal record can be written from
# EVERY exit path -- including the replay failure that destroyed the 2026-08-19 evidence.
_JOURNAL = None


def _object_hashes(manifest_path: str) -> dict:
    """The per-object SHA-256 the custodian recorded at upload; the reader fails closed on these."""
    with open(manifest_path, "rb") as fh:
        doc = json.loads(fh.read())
    out = {}

    def walk(node):
        if isinstance(node, dict):
            if "key" in node and "sha256" in node and "version_id" in node:
                out[node["key"]] = (node["version_id"], node["sha256"], node.get("bytes"))
                return
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(doc)
    return out


def _ledger(opened: list) -> dict:
    """Hash-chained opened-object ledger over the SEALED reads only."""
    rows, prev = [], ZERO
    for i, o in enumerate(opened, start=1):
        row = {"sequence": i, "object_id": o["key"], "version_id": o["version_id"],
               "partition": o["partition"], "permitted": True, "reason": "authorized",
               "prev_hash": prev}
        row["row_hash"] = hashlib.sha256(
            f"{row['sequence']}|{row['object_id']}|{row['version_id']}|{prev}".encode()
        ).hexdigest()
        prev = row["row_hash"]
        rows.append(row)
    return {"record_type": "ValidationOpenedObjectLedger", "chain_verifies": True,
            "counts": {"sealed_reads": len(rows), "oos_reads": 0, "attempts": len(rows),
                       "permitted": len(rows), "blocked": 0,
                       "unregistered_data_source_reads": 0},
            "ledger": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reader", choices=("fixture", "s3"), required=True)
    ap.add_argument("--window", choices=("validation", "development"), default="validation",
                    help="fixture-only rehearsal affordance")
    ap.add_argument("--fixture-root", default="/tmp/fx")
    ap.add_argument("--manifest", default="/opt/mr002/phase3c_src/docs_upload_manifest.json")
    ap.add_argument("--latch-release-epoch", type=float, default=None,
                    help="epoch seconds at which the latch Deny was removed; bounds the "
                         "readiness deadline. Absent => measured from process start.")
    ap.add_argument("--materialized", required=True)
    ap.add_argument("--journal", default=None,
                    help="durable evidence journal (JSONL). Default: <out>.journal.jsonl")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if args.window == "development" and args.reader != "fixture":
        raise IntegrityFailure("WINDOW_MISUSE",
                               "the development window is a fixture-only rehearsal affordance")

    hashes = _object_hashes(args.manifest)
    report = {"record_type": "MR002_Phase3C_ValidationExecution", "version": "1.0",
              "reader_kind": args.reader,
              "authorization": "MR002_Phase3C_ExecutionAuthorization_v2.0 / c53edf89",
              "countersignature": "MR002_Phase3C_ExecutionCountersignature_v2.0 / 410627f2",
              "package": "MR002_Phase3C_ValidationExecutionPackage_v2.2 / pending",
              "control_amendment": "credential readiness, owner ruling 2026-08-19"}

    # ---- build the pinned object set; refuse anything touching the OOS prefix ---------------
    sources, sealed_meta = [], []
    for table_map, is_sealed in ((SEALED, True), (REFERENCE, False)):
        for table, (key, vid) in table_map.items():
            if key.startswith(OOS_PREFIX):
                raise IntegrityFailure("OOS_ACCESS_ATTEMPT", key)
            rec = hashes.get(key)
            if rec is None:
                raise IntegrityFailure("UNPINNED_OBJECT", f"no recorded sha256 for {key}")
            if rec[0] != vid:
                raise IntegrityFailure("VERSION_ID_MISMATCH", f"{key}: {rec[0]} != {vid}")
            obj = PinnedObject(bucket=BUCKET, key=key, version_id=vid, sha256=rec[1])
            sources.append(TableSource(table, obj))
            if is_sealed:
                sealed_meta.append({"key": key, "version_id": vid, "partition": obj.partition})
    if len(sealed_meta) != 6 or len(sources) != 10:
        raise IntegrityFailure("INPUT_CONTRACT_MISMATCH",
                               f"{len(sealed_meta)} sealed / {len(sources)} total")

    # ---- durable evidence journal ---------------------------------------------------------
    # Opened BEFORE any read. Every sealed object is journalled and fsync'd as it is opened, so
    # a later failure -- including a replay failure on a CONSUMED opening -- cannot destroy the
    # custody record. The final report aggregates these rows; it is never their only copy.
    global _JOURNAL
    journal = EvidenceJournal(args.journal or (args.out + ".journal.jsonl"))
    _JOURNAL = journal
    journal.append("run_opened", {
        "reader_kind": args.reader, "window": args.window,
        "authorization": report["authorization"], "countersignature": report["countersignature"],
        "package": report["package"], "sealed_declared": len(SEALED),
        "reference_declared": len(REFERENCE), "materialized_path": args.materialized})

    # ---- reader ------------------------------------------------------------------------------
    if args.reader == "s3":
        import boto3
        sts = boto3.client("sts")
        # Bounded pre-sealed-read readiness: the latch release is not in force at STS for
        # minutes (measured +286.1s). Repeated AccessDenied here are propagation probes, not
        # validation retries -- no credentials are issued and no byte is read. The first
        # success is a one-way boundary straight into the indivisible sequence.
        creds, readiness = acquire_reader_credentials(
            sts, READER_ROLE, SESSION_NAME,
            latch_release_epoch=args.latch_release_epoch)
        report["credential_readiness"] = readiness
        reader = S3PinnedReader(lambda: boto3.client(
            "s3", aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"]))
    else:
        reader = FixtureReader(args.fixture_root)
    reader = JournalingReader(reader, journal)

    # ---- THE INDIVISIBLE SEQUENCE ------------------------------------------------------------
    ev = materialize(sources, reader, args.materialized)
    materialization_complete(journal, args.materialized, ev)
    report["materialization"] = {k: v for k, v in ev.items() if k != "objects_opened"}
    report["objects_opened"] = ev["objects_opened"]
    report["opened_object_ledger"] = _ledger(
        [o for o in ev["objects_opened"] if o["partition"] == "VALIDATION"])
    report["read_split"] = {
        "sealed_consuming_the_opening":
            sum(1 for o in ev["objects_opened"] if o["partition"] == "VALIDATION"),
        "reference_not_consuming_the_opening":
            sum(1 for o in ev["objects_opened"] if o["partition"] == "REFERENCE"),
        "oos_reads": 0,
    }

    ds = FrozenDataset(args.materialized)
    if args.window == "validation":
        first, last = VALIDATION_WINDOW_START, VALIDATION_WINDOW_END
    else:
        first, last = _dt.date(2013, 1, 2), _dt.date(2019, 10, 2)
    days = ds.day_inputs(first, last)
    report["window"] = {"first": str(days[0].session), "last": str(days[-1].session),
                        "sessions": len(days)}
    report["fold_assignment"] = (F.verify_assignment([d.session for d in days])
                                 if args.window == "validation"
                                 else {"skipped": "rehearsal window"})

    per_config, stage3 = {}, {}
    for name in VALIDATION_CONFIGS:
        census: list = []
        with route.routed(census, countersignature=route.EXECUTION_COUNTERSIGNATURE_ID):
            va = run_config_validation(days, CONFIGS[name], assert_oos_boundary=True)
        acc = va.acc
        per_config[name] = {"sessions": [d.session for d in days],
                            "nav_curve": acc.nav_curve, "daily_ret": acc.daily_ret}
        stage3[name] = route.census_summary(census)
        report.setdefault("replay", {})[name] = {
            "run_hash": hashlib.sha256("|".join(acc.session_hashes).encode()).hexdigest(),
            "reductions": acc.reductions, "exits": acc.exits,
            "new_orders": acc.entries_long + acc.entries_short,
            "exit_reasons": dict(acc.exit_reasons), "costs": acc.costs, "borrow": acc.borrow,
            "traded_notional": acc.traded_notional, "session_outcomes": dict(acc.outcomes),
            "band_observations": len(va.band_observations),
            "trades": len(acc.trades),
        }
    report["stage3"] = stage3

    integrity_ok = all(c["all_reconcile_to_a_registered_disposition"]
                       and c["unrecognized_outcomes"] == 0 and c["stop_dispositions"] == 0
                       for c in stage3.values())
    report["integrity_admissible"] = integrity_ok
    report["decision"] = (G.evaluate(per_config, integrity_ok=integrity_ok,
                                     integrity_detail="" if integrity_ok else "stage3 census")
                          if args.window == "validation"
                          else {"verdict": "REHEARSAL_NO_VERDICT", "gates_evaluated": False})

    # DSR trial-dispersion input: validation annualized net Sharpes of A/B/C. NOT a gate.
    report["dsr_trial_dispersion_input"] = {
        name: G.annualized_net_sharpe(per_config[name]["daily_ret"]) for name in VALIDATION_CONFIGS
    }
    report["dsr_note"] = ("frozen input to the later OOS DSR; explicitly NOT a validation "
                          "pass/fail")
    report["oos_metrics_computed"] = []

    body = json.dumps(report, indent=1, sort_keys=True, default=str)
    with open(args.out, "w") as fh:
        fh.write(body + "\n")
    d = report["decision"]
    print(json.dumps({
        "verdict": d["verdict"],
        "gate_folds": d.get("gate_validation_positive_folds_ge_3_of_5", {}).get("passed"),
        "positive_folds": d.get("gate_validation_positive_folds_ge_3_of_5", {})
                           .get("observed_positive_folds"),
        "gate_stability": d.get("gate_parameter_stability_A_and_C_net_profitable", {})
                           .get("passed"),
        "read_split": report["read_split"],
        "integrity_admissible": integrity_ok,
    }, indent=1))
    return 0


if __name__ == "__main__":
    try:
        _rc = main()
    except BaseException as _exc:                     # noqa: BLE001 - evidence, then re-raise
        if _JOURNAL is not None:
            try:
                terminal(_JOURNAL, "FAILED", f"{type(_exc).__name__}: {_exc}")
                _JOURNAL.close()
            except Exception:                         # noqa: BLE001 - never mask the real failure
                pass
        raise
    else:
        if _JOURNAL is not None:
            terminal(_JOURNAL, "COMPLETED", "")
            _JOURNAL.close()
        raise SystemExit(_rc)
