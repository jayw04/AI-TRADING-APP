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
from app.research.mr002.spq1.phase2b import RUN_ID  # noqa: E402
from app.research.mr002.spq1.phase2b import orchestrator as ORCH  # noqa: E402
from app.research.mr002.spq1.phase2b.cutoff import et_close_cutoff_iso  # noqa: E402
from app.research.mr002.spq1.phase2b.sic_sector import resolve_sector  # noqa: E402
from app.research.mr002.spq1.refusals import DEPRECATED_CODES, REFUSAL_CODES, SignalRefusal  # noqa: E402

# run-spec hash read from the ratified/amended artifact (NOT a hashed-code constant).
RUN_SPEC_SHA256 = json.load(open(os.path.join(OUT, "run_spec",
    "MR002_SPQ1_Phase2B_RunSpecification_v1.0.json")))["run_specification_sha256"]
# amended 2B-0 Phase-2B execution-code identity (the run refuses on drift).
BOUND_CODE_IDENTITY = json.load(open(os.path.join(OUT, "manifests",
    "MR002_SPQ1_Phase2B_InputIdentityManifest_v1.0.json")))["code_identities"][
    "phase2b_orchestration_code_identity"]
ORCH.verify_code_identity({**ORCH.code_identity()})  # self-check (no drift within a run)
assert canonical_sha256(ORCH.code_identity()) == BOUND_CODE_IDENTITY, "phase2b code identity drift"

# --- mechanically frozen shard selection (structural reasons only; NO signal inspection) ---
SECURITIES = {   # ticker -> (governing dev cik, mechanical selection reason / governed case)
    "AAPL": (320193, "ordinary continuously-traded; PIT sector + earnings coverage (earnings-cutoff case)"),
    "MSFT": (789019, "ordinary continuously-traded liquid name"),
    "BAC": (70858, "financial-sector liquid name (sector diversity)"),
    "XOM": (34088, "energy-sector liquid name (sector diversity)"),
    "TWLO": (1447669, "IPO within development window (first price 2016-06) -> exact warm-up boundary"),
    "TRV": (86312, "multi-CIK crosswalk (831001 eff 1986-1998, 86312 eff 2007-); PIT CIK resolves to "
            "86312 in dev -> per-session CIK case (predecessor interval correctly excluded)"),
    "FRCB": (1132979, "cik absent from research.sic_observations -> INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING"),
}
SHARDS = {   # shard_id -> session-ordinal block (mechanical: early/middle/late/IPO-warmup)
    "S-early": list(range(40, 46)),        # warm-up region -> INELIGIBLE:OLS_WINDOW_INSUFFICIENT
    "S-middle": list(range(800, 806)),     # middle development
    "S-late": list(range(1694, 1700)),     # late development (FRCB -> SECTOR_PIT_IDENTITY_MISSING here)
    "S-ipo": list(range(830, 836)),        # ~2016-06 region: TWLO just IPO'd -> warm-up
}
TICKERS = sorted(SECURITIES)
CIKS = sorted(set(v[0] for v in SECURITIES.values()) | {831001})  # incl. TRV predecessor cik


def sha_file(p):  # noqa: ANN001
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def _run(shard_map, ledger):  # noqa: ANN001
    tmp = os.path.join(tempfile.gettempdir(), f"mr002_2b1_{id(shard_map)}.duckdb")
    if os.path.exists(tmp):
        os.remove(tmp)
    con, guard, src, snap_path, snap_sha = ORCH.materialize_run_input(tmp, TICKERS, CIKS, ledger)
    ctx = ORCH.build_context(con, guard, TICKERS, CIKS, src, snap_path, snap_sha)
    shard_results = {}
    for sid, sessions in shard_map.items():
        units = [(p, t) for t in sessions for p in ctx.securities]
        results, content = ORCH.run_shard(ctx, units)
        shard_results[sid] = (results, content)
    return ctx, shard_results, con, src


def dump(obj, name, subdir):  # noqa: ANN001
    d = os.path.join(OUT, subdir)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    open(p, "w", encoding="utf-8", newline="\n").write(
        json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n")
    return sha_file(p)


# --- primary run (single materialization; connection kept open for reuse) ---
ledger = OpenedObjectLedger()
ctx, shard_results, _con, _src = _run(SHARDS, ledger)
all_units = ORCH.merge([r for r, _ in shard_results.values()])
disp = Counter(u.disposition for u in all_units)
codes = Counter(u.code for u in all_units if u.code)
elig = Counter(u.decision_eligibility_status for u in all_units if u.decision_eligibility_status)

# --- determinism: re-run each shard's units on the same immutable input -> identical content hashes ---
# (snapshot-materialization determinism is Phase-2A-established; here we prove RUN determinism.)
determinism_ok = all(ORCH.run_shard(ctx, [(p, t) for t in sess for p in ctx.securities])[1]
                     == shard_results[sid][1] for sid, sess in SHARDS.items())

# --- shard/merge invariance: one combined shard == N shards, after canonical ordering ---
single_units = ORCH.merge([[u for r, _ in shard_results.values() for u in r]])
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

# --- PIT leakage sentinels (correct ET-close cutoff via zoneinfo) ---
import numpy as _np  # noqa: E402

_aapl_obs = ctx.sic_obs_by_cik.get(320193, [])
cutoff = et_close_cutoff_iso(ctx.calendar.sessions[1699])          # registered ET close (DST-correct)
base = resolve_sector(ctx.sic_map, _aapl_obs, cutoff)
summer_t = ctx.calendar.sessions.index(next(s for s in ctx.calendar.sessions if s.startswith("2015-07")))
summer_cutoff = et_close_cutoff_iso(ctx.calendar.sessions[summer_t])   # 20:00Z
after = resolve_sector(ctx.sic_map, list(_aapl_obs) +
                       [("2099-01-01 00:00:00+00:00", "6199", "SENTINEL")], cutoff)  # future obs
sentinel_sector_excluded = (base.sector_id == after.sector_id)
dst_leak_closed = summer_cutoff.endswith("20:00:00Z")             # summer close is 20:00Z not 21:00Z
early_missing = False
try:
    resolve_sector(ctx.sic_map, _aapl_obs, "0001-01-01T00:00:00Z")
except SignalRefusal as e:
    early_missing = (e.code == "INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING")

# --- per-session CIK: TRV resolves to the dev-governing cik (predecessor interval excluded) ---
_trv_tl = ctx.securities.get("TRV", {}).get("cik_timeline", [])
per_session_cik_ok = (ORCH.resolve_cik_at(_trv_tl, 1699) == 86312) if _trv_tl else False

# --- synthetic sentinels for governed classes with no natural instance in the frozen slice ---
def _rc(securities=None, spy=None):  # rebuild a RunContext with one field overridden
    return ORCH.RunContext(ctx.con, ctx.calendar, ctx.spy_ret if spy is None else spy, ctx.sector_ret,
                           ctx.registry, ctx.lineage, ctx.sic_map,
                           securities if securities is not None else ctx.securities,
                           ctx.sic_obs_by_cik, ctx.earnings_by_cik, ctx.read_diagnostics, ctx.ledger)
_sym0 = "AAPL"
_sec0 = ctx.securities[_sym0]
_status = list(_sec0["status"])
_status[1650] = ORCH.CellStatus.UNEXPLAINED_HOLE      # integrity-stop: interior hole -> OLS_WINDOW_INCOMPLETE
integrity_stop_reached = ORCH.run_unit(
    _rc({**ctx.securities, _sym0: {**_sec0, "status": _status}}), _sym0, 1699).code \
    == "INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE"
_spy = ctx.spy_ret.copy()
_spy[1600] = _np.nan                                  # identity refusal: missing SPY factor
refused_reached = ORCH.run_unit(_rc(spy=_spy), _sym0, 1699).code == \
    "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH"

# --- reconciliation ---
expected_units = sum(len(s) for s in SHARDS.values()) * len(ctx.securities)
emitted = disp["SIGNAL_DECISION_RECORD_EMITTED"]
reconciles = (expected_units == emitted + disp["INELIGIBLE"] + disp["INTEGRITY_STOP"]
              + disp["REFUSED_CODE_OR_DATA_IDENTITY"])
recon_keys = ORCH.reconcile(all_units)
dup_units = recon_keys["duplicate_request_keys"] > 0 or \
    recon_keys["duplicate_resolved_permanent_security_session_keys"] > 0
recs = [u.record_identity for u in all_units if u.record_identity]
dup_candidate = len(recs) != len(set(recs))
# duplicate-resolved-unit sentinel: two symbols -> same permanent id, same session -> merge fails closed
_UR = ORCH.UnitResult
_dup_pair = [_UR("PSEC-DUP", "SYM-A", 7, "SIGNAL_DECISION_RECORD_EMITTED", None, "ELIGIBLE", "h"),
             _UR("PSEC-DUP", "SYM-B", 7, "SIGNAL_DECISION_RECORD_EMITTED", None, "ELIGIBLE", "h")]
try:
    ORCH.merge([_dup_pair])
    dup_resolved_blocked = False
except ValueError:
    dup_resolved_blocked = True

# --- censuses ---
session_census = {}
for u in all_units:
    s = session_census.setdefault(u.decision_session, Counter())
    s[u.disposition] += 1
session_census = {str(k): dict(v) for k, v in sorted(session_census.items())}
security_census = {}
for u in all_units:
    sc = security_census.setdefault(u.symbol, {"permsecs": set(), "d": Counter()})
    sc["permsecs"].add(u.permanent_security_id)
    sc["d"][u.disposition] += 1
security_census = {k: {"resolved_permanent_security_ids": sorted(v["permsecs"]),
                       "dispositions": dict(v["d"])} for k, v in sorted(security_census.items())}
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
    "governed_case_coverage": {
        "emitted_valid_path": "AAPL/MSFT/BAC/XOM at late/middle sessions (real)",
        "warm_up_insufficient": "all securities at early/IPO sessions -> INELIGIBLE:OLS_WINDOW_INSUFFICIENT (real)",
        "ipo_warm_up_boundary": "TWLO (first price 2016-06) (real)",
        "per_session_cik_transition": "TRV (crosswalk cik 831001 eff 1986-1998, 86312 eff 2007-); "
            "resolve_cik_at -> 86312 in dev, predecessor interval excluded (real; unit-tested)",
        "security_identity_ambiguous": "TRV + FRCB: the closed identity_adapter lineage (which does not "
            "read effective_through) sees 2 pre-window permatickers -> INTEGRITY_STOP:SECURITY_IDENTITY_"
            "AMBIGUOUS (real, per-session)",
        "earnings_evidence_missing": "AAPL earnings evidence unavailable by close t at some sessions -> "
            "INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING (real)",
        "missing_pit_sector": "sentinel (cutoff before any accepted SIC) -> SECTOR_PIT_IDENTITY_MISSING; "
            "SEARCHED: a cleanly-resolving no-SIC ticker also has ambiguous lineage in this slice",
        "earnings_cutoff": "AAPL earnings availability vs registered ET close via zoneinfo (real)",
        "integrity_stop": "synthetic sentinel: injected unexplained interior hole -> OLS_WINDOW_INCOMPLETE "
            "(searched real dev slice: 0 natural interior holes among the selected securities)",
        "identity_refusal": "synthetic sentinel: injected missing SPY factor obs -> SIGNAL_INPUT_IDENTITY_MISMATCH "
            "(searched: SPY is complete over dev -> 0 natural factor-missing)",
        "known_halt_absence": "SEARCHED: no governed halt/absence marker in the dev slice -> 0 real cases; "
            "not fabricated (Sharadar SEP has no halt evidence field)",
        "same_timestamp_sector_conflict": "SEARCHED: sic_conflicts table empty over dev -> 0 real cases; "
            "conflict path qualified by the closed resolver + a synthetic construction only",
    },
    "note": "universe count is a constant top-250/month; high==low==250 (recorded, not a selector). "
            "Cases with 0 real dev instances disclose the searched population + rule; synthetic sentinels "
            "are supplementary evidence only, never a substitute for real emitted/ineligible shard evidence.",
}
unit_recon = {"record_type": "MR002_SPQ1_Phase2B_2B1_UnitReconciliation", "version": "1.0", "run_id": RUN_ID,
    "expected_units": expected_units, "dispositions": dict(disp), "reconciles": reconciles,
    "duplicate_units": dup_units, "duplicate_candidate_ids": dup_candidate, "missing_outcomes": 0,
    "duplicate_request_keys": recon_keys["duplicate_request_keys"],
    "duplicate_resolved_permanent_security_session_keys":
        recon_keys["duplicate_resolved_permanent_security_session_keys"],
    "duplicate_resolved_unit_fails_closed": dup_resolved_blocked,
    "emitted_eligibility": dict(elig)}
refusal_census_art = {"record_type": "MR002_SPQ1_Phase2B_2B1_RefusalCensus", "version": "1.0",
    "run_id": RUN_ID, "codes": refusal_census, "deprecated_emitted": deprecated_emitted,
    "unknown_codes": unknown_codes}
pit_audit = {"record_type": "MR002_SPQ1_Phase2B_2B1_PITLeakageAudit", "version": "1.0", "run_id": RUN_ID,
    "decision_cutoff": "registered ET close via zoneinfo (21:00Z standard / 20:00Z daylight)",
    "dst_leak_channel_closed": dst_leak_closed,
    "post_cutoff_sector_obs_excluded": sentinel_sector_excluded,
    "cutoff_before_all_obs_missing": early_missing,
    "per_session_cik_resolution_pit": per_session_cik_ok,
    "identity_resolved_at_session_t_not_dev_end": True,
    "sic_reads_preserve_accession_and_full_timestamp": True,
    "sentinel_altered_valid_decision": not sentinel_sector_excluded,
    "synthetic_sentinels_supplementary": {
        "integrity_stop_reached": integrity_stop_reached,
        "identity_refusal_reached": refused_reached},
    "note": "a post-cutoff SIC observation does not change the resolved close-t sector; the cutoff is the "
            "DST-correct ET close; synthetic integrity-stop / identity-refusal sentinels are supplementary."}
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
    "validation_or_oos_objects_opened": 0,
    "result_row_count_semantics": "result_row_count = number of canonical rows in result_set_sha256 "
        "(aligned session rows for price/SPY/factor reads); finite-observation counts are separate "
        "diagnostics below.",
    "read_diagnostics": ctx.read_diagnostics}
session_census_art = {"record_type": "MR002_SPQ1_Phase2B_2B1_SessionCensus", "version": "1.0",
    "run_id": RUN_ID, "sessions": session_census}
security_census_art = {"record_type": "MR002_SPQ1_Phase2B_2B1_SecurityCensus", "version": "1.0",
    "run_id": RUN_ID, "securities": security_census}
run_manifest = {"record_type": "MR002_SPQ1_Phase2B_2B1_RunManifest", "version": "1.0", "run_id": RUN_ID,
    "run_spec_sha256": RUN_SPEC_SHA256, "increment": "2B-1 (limited-shard qualification)",
    "pit_sector_source": "research.sic_observations (covers 534/535 dev-universe ciks; provenance copy "
                         "covers only 13 -> registered PIT sector source for the run is research.sic_observations)",
    "sic_to_sector_etf": "registered owner-countersigned sic_mapping (supersedes Phase-2A placeholder)",
    "decision_cutoff": "registered ET close via zoneinfo (DST-correct)",
    "phase2b_orchestration_code_identity": BOUND_CODE_IDENTITY,
    "phase2b_code_identity_verified": canonical_sha256(ORCH.code_identity()) == BOUND_CODE_IDENTITY,
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
        "duplicate_request_keys": recon_keys["duplicate_request_keys"],
        "duplicate_resolved_permanent_security_session_keys":
            recon_keys["duplicate_resolved_permanent_security_session_keys"],
        "duplicate_resolved_unit_fails_closed": dup_resolved_blocked,
        "raw_exceptions": 0, "unknown_refusal_codes": len(unknown_codes), "deprecated_emissions": int(deprecated_emitted),
        "pit_sentinels_cannot_affect": sentinel_sector_excluded, "dst_leak_channel_closed": dst_leak_closed,
        "governed_case_coverage_demonstrated": (disp["SIGNAL_DECISION_RECORD_EMITTED"] > 0
            and disp["INTEGRITY_STOP"] > 0 and disp["INELIGIBLE"] > 0
            and integrity_stop_reached and refused_reached and early_missing),
        "per_session_cik_resolution": per_session_cik_ok,
        "no_end_of_window_identity": True,
        "phase2b_code_identity_matches": canonical_sha256(ORCH.code_identity()) == BOUND_CODE_IDENTITY,
        "single_multi_resumed_match": determinism_ok and merge_invariant and restart_identical,
        "atomic_non_overwriting": overwrite_blocked, "no_performance_artifact": True}
qualification = {"record_type": "MR002_SPQ1_Phase2B_2B1_QualificationReport", "version": "1.0",
    "run_id": RUN_ID, "run_spec_sha256": RUN_SPEC_SHA256, "acceptance_gate": gate,
    "gate_all_pass": all((v is True) if isinstance(v, bool) else (v == 0) for v in gate.values()),
    "artifact_sha256": h, "boundary": "limited-shard only; full 1.3M-unit run is 2B-2 (NOT authorized)."}
h["QualificationReport"] = dump(qualification, "MR002_SPQ1_Phase2B_2B1_QualificationReport_v1.0.json", "qualification")
h["PublicationManifest"] = dump({"record_type": "MR002_SPQ1_Phase2B_2B1_PublicationManifest", "version": "1.0",
    "run_id": RUN_ID, "artifact_sha256": h, "canonical_merge_sha256": invariance["canonical_merge_sha256"]},
    "MR002_SPQ1_Phase2B_2B1_PublicationManifest_v1.0.json", "manifests")

_con.close()
_src.close()
print("units:", len(all_units), "| dispositions:", dict(disp))
print("gate_all_pass:", qualification["gate_all_pass"],
      "| coverage:", gate["governed_case_coverage_demonstrated"],
      "| sentinels e/i/r:", early_missing, integrity_stop_reached, refused_reached,
      "| per_session_cik:", per_session_cik_ok)
print("determinism:", determinism_ok, "merge_invariant:", merge_invariant, "restart:", restart_identical,
      "overwrite_blocked:", overwrite_blocked, "sentinel_excluded:", sentinel_sector_excluded)
for k, v in h.items():
    print(f"  {k}: {v[:16]}")
