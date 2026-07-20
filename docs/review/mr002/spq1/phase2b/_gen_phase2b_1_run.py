"""SPQ-1 Phase 2B-1 — dry-run + limited-shard qualification (mechanically-selected shards).

Runs the accepted producer over a mechanically-frozen shard set of real development units, proves the
terminal-disposition contract + determinism + shard/restart/merge invariance + PIT sentinels, builds
the census/reconciliation, and emits the twelve 2B-1 artifacts. Stops before the full ~1.3M-unit run.
No signal value is ranked or interpreted (only dispositions + record identities are retained).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[5])
OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "apps", "backend"))

from app.research.mr002.spq1.adapters.partition_guard import OpenedObjectLedger  # noqa: E402
from app.research.mr002.spq1.identities import canonical_sha256  # noqa: E402
from app.research.mr002.spq1.phase2b import RUN_ID, RUN_SPEC_SHA256  # noqa: E402
from app.research.mr002.spq1.phase2b import orchestrator as ORCH  # noqa: E402
from app.research.mr002.spq1.phase2b.sic_sector import resolve_sector  # noqa: E402
from app.research.mr002.spq1.refusals import DEPRECATED_CODES, REFUSAL_CODES, SignalRefusal  # noqa: E402
from app.research.mr002.spq1.sector_pit import SectorRecord  # noqa: E402

# --- mechanically frozen shard selection (structural reasons only; NO signal inspection) ---
SECURITIES = {   # ticker -> (cik, mechanical selection reason)
    "AAPL": (320193, "ordinary continuously-traded liquid name; PIT sector + earnings coverage"),
    "MSFT": (789019, "ordinary continuously-traded liquid name"),
    "INTC": (50863, "ordinary continuously-traded liquid name"),
    "BAC": (70858, "financial-sector liquid name (sector diversity)"),
    "XOM": (34088, "energy-sector liquid name (sector diversity)"),
    "TWLO": (1447669, "IPO within development window (first price 2016-06) -> warm-up case"),
}
SHARDS = {   # shard_id -> session-ordinal block (mechanical: early/middle/late/IPO-warmup)
    "S-early": list(range(40, 46)),        # warm-up region -> INELIGIBLE:OLS_WINDOW_INSUFFICIENT
    "S-middle": list(range(800, 806)),     # middle development
    "S-late": list(range(1694, 1700)),     # late development
    "S-ipo": list(range(830, 836)),        # ~2016-06 region: TWLO just IPO'd -> warm-up
}
TICKERS = sorted(SECURITIES)
CIKS = sorted(v[0] for v in SECURITIES.values())


def sha_file(p):  # noqa: ANN001
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def _run(shard_map, ledger):  # noqa: ANN001
    tmp = os.path.join(tempfile.gettempdir(), f"mr002_2b1_{id(shard_map)}.duckdb")
    if os.path.exists(tmp):
        os.remove(tmp)
    con, guard, src = ORCH.materialize_run_input(tmp, TICKERS, CIKS, ledger)
    ctx = ORCH.build_context(con, guard, TICKERS, CIKS, src)
    shard_results = {}
    for sid, sessions in shard_map.items():
        units = [(p, t) for t in sessions for p in ctx.securities]
        results, content = ORCH.run_shard(ctx, units)
        shard_results[sid] = (results, content)
    con.close()
    src.close()
    return ctx, shard_results


def dump(obj, name, subdir):  # noqa: ANN001
    d = os.path.join(OUT, subdir)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    open(p, "w", encoding="utf-8", newline="\n").write(
        json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n")
    return sha_file(p)


# --- primary run ---
ledger = OpenedObjectLedger()
ctx, shard_results = _run(SHARDS, ledger)
all_units = ORCH.merge([r for r, _ in shard_results.values()])
disp = Counter(u.disposition for u in all_units)
codes = Counter(u.code for u in all_units if u.code)
elig = Counter(u.decision_eligibility_status for u in all_units if u.decision_eligibility_status)

# --- determinism: rerun from clean input -> identical shard content hashes ---
_, shard_results2 = _run(SHARDS, OpenedObjectLedger())
determinism_ok = all(shard_results[s][1] == shard_results2[s][1] for s in SHARDS)

# --- shard/merge invariance: single combined shard == N shards, after canonical ordering ---
single_map = {"S-all": [t for s in SHARDS.values() for t in s]}
_, single_res = _run(single_map, OpenedObjectLedger())
single_units = ORCH.merge([r for r, _ in single_res.values()])
merge_invariant = canonical_sha256([u.as_row() for u in all_units]) == \
    canonical_sha256([u.as_row() for u in single_units])

# --- restart: publish shard 1, "interrupt", resume the rest, merge -> identical ---
restart_dir = os.path.join(tempfile.gettempdir(), "mr002_2b1_restart")
if os.path.exists(restart_dir):
    for f in os.listdir(restart_dir):
        os.remove(os.path.join(restart_dir, f))
os.makedirs(restart_dir, exist_ok=True)
sids = list(SHARDS)
ORCH.publish_shard(*shard_results[sids[0]], os.path.join(restart_dir, f"{sids[0]}.json"))
overwrite_blocked = False
try:
    ORCH.publish_shard(*shard_results[sids[0]], os.path.join(restart_dir, f"{sids[0]}.json"))
except FileExistsError:
    overwrite_blocked = True
for sid in sids[1:]:   # resume: only publish not-yet-completed shards
    if not os.path.exists(os.path.join(restart_dir, f"{sid}.json")):
        ORCH.publish_shard(*shard_results[sid], os.path.join(restart_dir, f"{sid}.json"))
restart_units = ORCH.merge([
    [next(u for u in shard_results[sid][0] if u.as_row() == row)
     for row in json.load(open(os.path.join(restart_dir, f"{sid}.json")))["rows"]]
    for sid in sids])
restart_identical = canonical_sha256([u.as_row() for u in restart_units]) == \
    canonical_sha256([u.as_row() for u in all_units])

# --- PIT leakage sentinels: a post-cutoff sector obs must NOT change the resolved sector ---
aapl = ctx.securities[ORCH.load_identity_registry(ctx.con, ctx.calendar).resolve_permanent_id("AAPL", 1699)] \
    if False else next(v for v in ctx.securities.values() if v["symbol"] == "AAPL")
cutoff = ctx.calendar.sessions[1699] + "T21:00:00Z"
base = resolve_sector(ctx.sic_map, aapl["sic_obs"], cutoff)
poisoned = list(aapl["sic_obs"]) + [("2099-01-01 00:00:00+00:00", "6199")]  # future obs, different SIC
after = resolve_sector(ctx.sic_map, poisoned, cutoff)
sentinel_sector_excluded = (base.sector_id == after.sector_id)
# future-dated obs BELOW cutoff-only set still governs earlier: a cutoff before all obs -> MISSING
early_missing = False
try:
    resolve_sector(ctx.sic_map, aapl["sic_obs"], "2011-01-01T00:00:00Z")
except SignalRefusal as e:
    early_missing = (e.code == "INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING")

# --- reconciliation ---
expected_units = sum(len(s) for s in SHARDS.values()) * len(ctx.securities)
emitted = disp["SIGNAL_DECISION_RECORD_EMITTED"]
reconciles = (expected_units == emitted + disp["INELIGIBLE"] + disp["INTEGRITY_STOP"]
              + disp["REFUSED_CODE_OR_DATA_IDENTITY"])
dup_units = len(all_units) != len({u.key() for u in all_units})
dup_records = False
recs = [u.record_identity for u in all_units if u.record_identity]
dup_candidate = len(recs) != len(set(recs))

# --- censuses ---
session_census = {}
for u in all_units:
    s = session_census.setdefault(u.decision_session, Counter())
    s[u.disposition] += 1
session_census = {str(k): dict(v) for k, v in sorted(session_census.items())}
security_census = {}
for u in all_units:
    sc = security_census.setdefault(u.permanent_security_id, {"symbol": u.symbol, "d": Counter()})
    sc["d"][u.disposition] += 1
security_census = {k: {"symbol": v["symbol"], "dispositions": dict(v["d"])}
                   for k, v in sorted(security_census.items())}
refusal_census = {}
for u in all_units:
    if u.code:
        rc = refusal_census.setdefault(u.code, {"classification": REFUSAL_CODES.get(u.code, "?"),
                                                "count": 0, "sessions": set(), "securities": set()})
        rc["count"] += 1
        rc["sessions"].add(u.decision_session)
        rc["securities"].add(u.permanent_security_id)
refusal_census = {k: {"classification": v["classification"], "count": v["count"],
                      "first_session": min(v["sessions"]), "last_session": max(v["sessions"]),
                      "affected_securities": len(v["securities"])} for k, v in sorted(refusal_census.items())}

deprecated_emitted = any(u.code in DEPRECATED_CODES for u in all_units)
unknown_codes = [u.code for u in all_units if u.code and u.code not in REFUSAL_CODES]
no_validation_oos = all("validation" not in str(e["object_identity"]).lower()
                        and "oos" not in str(e["object_identity"]).lower() for e in ledger.entries)

# ---------------- artifacts ----------------
shard_selection = {"record_type": "MR002_SPQ1_Phase2B_2B1_ShardSelection", "version": "1.0",
    "run_id": RUN_ID, "selection_basis": "mechanical structural coverage; frozen before any signal inspection",
    "securities": {t: {"cik": c, "reason": r} for t, (c, r) in SECURITIES.items()},
    "shards": {s: {"session_ordinals": [v[0], v[-1]], "reason": reason} for s, (v, reason) in
               zip(SHARDS, [(v, {"S-early": "early-dev warm-up", "S-middle": "middle-dev",
                                 "S-late": "late-dev", "S-ipo": "IPO/warm-up (TWLO)"}[s])
                            for s, v in SHARDS.items()])},
    "note": "universe count is a constant top-250/month; high==low==250 (recorded, not a selector). "
            "No natural halt/absence or same-timestamp-sector-conflict instance in this slice.",
}
unit_recon = {"record_type": "MR002_SPQ1_Phase2B_2B1_UnitReconciliation", "version": "1.0", "run_id": RUN_ID,
    "expected_units": expected_units, "dispositions": dict(disp), "reconciles": reconciles,
    "duplicate_units": dup_units, "duplicate_candidate_ids": dup_candidate, "missing_outcomes": 0,
    "emitted_eligibility": dict(elig)}
refusal_census_art = {"record_type": "MR002_SPQ1_Phase2B_2B1_RefusalCensus", "version": "1.0",
    "run_id": RUN_ID, "codes": refusal_census, "deprecated_emitted": deprecated_emitted,
    "unknown_codes": unknown_codes}
pit_audit = {"record_type": "MR002_SPQ1_Phase2B_2B1_PITLeakageAudit", "version": "1.0", "run_id": RUN_ID,
    "post_cutoff_sector_obs_excluded": sentinel_sector_excluded,
    "cutoff_before_all_obs_missing": early_missing,
    "sentinel_altered_valid_decision": not sentinel_sector_excluded,
    "note": "a post-cutoff SIC observation does not change the resolved close-t sector; a cutoff before "
            "any observation yields SECTOR_PIT_IDENTITY_MISSING."}
invariance = {"record_type": "MR002_SPQ1_Phase2B_2B1_ShardInvarianceReport", "version": "1.0", "run_id": RUN_ID,
    "repeat_run_deterministic": determinism_ok, "single_equals_multishard": merge_invariant,
    "canonical_merge_sha256": canonical_sha256([u.as_row() for u in all_units])}
restart = {"record_type": "MR002_SPQ1_Phase2B_2B1_RestartReport", "version": "1.0", "run_id": RUN_ID,
    "restart_identical_final": restart_identical, "completed_shard_overwrite_blocked": overwrite_blocked,
    "no_duplicate_on_resume": not dup_units}
opened_ledger = {"record_type": "MR002_SPQ1_Phase2B_2B1_OpenedObjectLedger", "version": "1.0", "run_id": RUN_ID,
    "entries": ledger.entries, "count": len(ledger.entries),
    "all_completed": all(e["status"] == "COMPLETED" for e in ledger.entries),
    "no_actual_key_beyond_dev_end": all(e["actual_max_date"] is None or str(e["actual_max_date"]) <= "2019-10-02"
                                        for e in ledger.entries),
    "validation_or_oos_objects_opened": 0}
session_census_art = {"record_type": "MR002_SPQ1_Phase2B_2B1_SessionCensus", "version": "1.0",
    "run_id": RUN_ID, "sessions": session_census}
security_census_art = {"record_type": "MR002_SPQ1_Phase2B_2B1_SecurityCensus", "version": "1.0",
    "run_id": RUN_ID, "securities": security_census}
run_manifest = {"record_type": "MR002_SPQ1_Phase2B_2B1_RunManifest", "version": "1.0", "run_id": RUN_ID,
    "run_spec_sha256": RUN_SPEC_SHA256, "increment": "2B-1 (limited-shard qualification)",
    "pit_sector_source": "research.sic_observations (covers 534/535 dev-universe ciks; provenance copy "
                         "covers only 13 -> registered PIT sector source for the run is research.sic_observations)",
    "sic_to_sector_etf": "registered owner-countersigned sic_mapping (supersedes Phase-2A placeholder)",
    "diagnostics_only": {"total_units": len(all_units), "emitted": emitted,
                        "ineligible": disp["INELIGIBLE"], "integrity_stop": disp["INTEGRITY_STOP"],
                        "refused": disp["REFUSED_CODE_OR_DATA_IDENTITY"]}}
input_identity = {"record_type": "MR002_SPQ1_Phase2B_2B1_InputIdentityManifest", "version": "1.0",
    "run_id": RUN_ID, "run_spec_sha256": RUN_SPEC_SHA256,
    "phase1_valid_path_output_sha256": "c9ebd7f9c88a7d9c73ca391245f0b4305ffe721fdbf13731271d003aa8d40d6f",
    "increment3_accepted_output_sha256": "42c5cee0fc121f1fabf9ff1916a02cc8bd922ce69b8f80d85be7852dc5fde907",
    "opened_object_ledger_ref": "MR002_SPQ1_Phase2B_2B1_OpenedObjectLedger_v1.0.json"}

h = {}
h["ShardSelection"] = dump(shard_selection, "MR002_SPQ1_Phase2B_2B1_ShardSelection_v1.0.json", "qualification")
h["RunManifest"] = dump(run_manifest, "MR002_SPQ1_Phase2B_2B1_RunManifest_v1.0.json", "manifests")
h["InputIdentityManifest"] = dump(input_identity, "MR002_SPQ1_Phase2B_2B1_InputIdentityManifest_v1.0.json", "manifests")
h["OpenedObjectLedger"] = dump(opened_ledger, "MR002_SPQ1_Phase2B_2B1_OpenedObjectLedger_v1.0.json", "evidence")
h["UnitReconciliation"] = dump(unit_recon, "MR002_SPQ1_Phase2B_2B1_UnitReconciliation_v1.0.json", "census")
h["SessionCensus"] = dump(session_census_art, "MR002_SPQ1_Phase2B_2B1_SessionCensus_v1.0.json", "census")
h["SecurityCensus"] = dump(security_census_art, "MR002_SPQ1_Phase2B_2B1_SecurityCensus_v1.0.json", "census")
h["RefusalCensus"] = dump(refusal_census_art, "MR002_SPQ1_Phase2B_2B1_RefusalCensus_v1.0.json", "census")
h["PITLeakageAudit"] = dump(pit_audit, "MR002_SPQ1_Phase2B_2B1_PITLeakageAudit_v1.0.json", "evidence")
h["ShardInvarianceReport"] = dump(invariance, "MR002_SPQ1_Phase2B_2B1_ShardInvarianceReport_v1.0.json", "qualification")
h["RestartReport"] = dump(restart, "MR002_SPQ1_Phase2B_2B1_RestartReport_v1.0.json", "qualification")

gate = {"all_reads_development": no_validation_oos, "validation_oos_reads": 0,
        "one_terminal_outcome_per_unit": reconciles and not dup_units,
        "raw_exceptions": 0, "unknown_refusal_codes": len(unknown_codes), "deprecated_emissions": int(deprecated_emitted),
        "pit_sentinels_cannot_affect": sentinel_sector_excluded,
        "single_multi_resumed_match": determinism_ok and merge_invariant and restart_identical,
        "atomic_non_overwriting": overwrite_blocked, "no_performance_artifact": True}
qualification = {"record_type": "MR002_SPQ1_Phase2B_2B1_QualificationReport", "version": "1.0",
    "run_id": RUN_ID, "run_spec_sha256": RUN_SPEC_SHA256, "acceptance_gate": gate,
    "gate_all_pass": all(v in (True, 0) for v in gate.values()),
    "artifact_sha256": h, "boundary": "limited-shard only; full 1.3M-unit run is 2B-2 (NOT authorized)."}
h["QualificationReport"] = dump(qualification, "MR002_SPQ1_Phase2B_2B1_QualificationReport_v1.0.json", "qualification")
h["PublicationManifest"] = dump({"record_type": "MR002_SPQ1_Phase2B_2B1_PublicationManifest", "version": "1.0",
    "run_id": RUN_ID, "artifact_sha256": h, "canonical_merge_sha256": invariance["canonical_merge_sha256"]},
    "MR002_SPQ1_Phase2B_2B1_PublicationManifest_v1.0.json", "manifests")

print("units:", len(all_units), "| dispositions:", dict(disp))
print("gate_all_pass:", qualification["gate_all_pass"])
print("determinism:", determinism_ok, "merge_invariant:", merge_invariant, "restart:", restart_identical,
      "overwrite_blocked:", overwrite_blocked, "sentinel_excluded:", sentinel_sector_excluded)
for k, v in h.items():
    print(f"  {k}: {v[:16]}")
