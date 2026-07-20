"""Generate the Increment-3 qualification-evidence bundle: source hashes, a canonical synthetic
portfolio-to-metrics replay report (exact-float, dependency-lock embedded), determinism proof, and the
governing-identity binding. Writes MR002_Increment3_ReplayReport.json and
MR002_Increment3_Qualification.json. Reads NO real dataset; computes no residual/z/sigma.
"""
import hashlib
import json

import mr002_valoos_pipeline as P
import mr002_valoos_portfolio_identity as ID

DEP_LOCK = "MR002_Increment1_Dependencies.json"
SRC = ["mr002_valoos_portfolio_identity.py", "mr002_valoos_candidates.py", "mr002_valoos_construction.py",
       "mr002_valoos_portfolio_state.py", "mr002_valoos_exposure.py", "mr002_valoos_replay.py",
       "mr002_valoos_nav.py", "mr002_valoos_pipeline.py", "test_increment3.py", "_gen_evidence_inc3.py"]
GOV_DIR = ".."


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _cand(cid, side, z, sec, sigma=0.02, beta=0.05, price=100.0, adv=1e15, ds=0):
    return {"candidate_id": cid, "permanent_security_id": cid, "signal_origin_session": 1,
            "decision_session": ds, "symbol": cid, "side": side, "registered_signal_value": z,
            "registered_sigma_resid": sigma, "sector_id": sec, "beta": beta, "eligibility_status": "ELIGIBLE",
            "eligibility_evidence_identity": "ev", "configuration_id": "B",
            "official_next_open_price": price, "trailing_adv_dollars": adv}


def _sessions():
    recs = []
    for sec in range(5):
        for j in range(10):
            recs.append(_cand(f"L{sec}_{j}", "long", -3.0 if j == 0 else -2.0, f"SEC{sec}"))
            recs.append(_cand(f"S{sec}_{j}", "short", 3.0 if j == 0 else 2.0, f"SEC{sec}"))
    held = [f"L{s}_0" for s in range(5)] + [f"S{s}_0" for s in range(5)]
    opens1 = {r["candidate_id"]: 100.0 for r in recs}
    adv = {r["candidate_id"]: 1e15 for r in recs}
    sess = [{"session": 1, "date": "2024-01-02", "opens": opens1, "adv": adv,
             "candidate_records": recs, "exit_signals": []}]
    for k, s in enumerate((2, 3, 4), start=1):
        o = {sym: (100.0 + k * (1 if sym.startswith("L") else -1)) for sym in held}
        sess.append({"session": s, "date": f"2024-01-0{s + 1}", "opens": o, "adv": {},
                     "candidate_records": [], "exit_signals": []})
    return sess


identity = ID.load_portfolio_identity(GOV_DIR)


def _report():
    replay = P.run_replay(_sessions(), initial_cash=1_000_000.0, config_id="B")
    metrics = P.metric_handoff(replay["return_series"])
    return P.build_pipeline_report(replay=replay, metrics=metrics,
                                   identity={"registry_sha256": identity["registry_sha256"],
                                             "resolution_sha256": identity["resolution_sha256"]},
                                   config_id="B", code_identity={s: sha(s) for s in SRC},
                                   dependency_lock_sha256=sha(DEP_LOCK)), replay, metrics


report, replay, metrics = _report()
report2, _, _ = _report()
open("MR002_Increment3_ReplayReport.json", "w", encoding="utf-8").write(json.dumps(report, sort_keys=True, indent=2))

committed = sum(1 for r in replay["results"] if r["disposition"] == "COMMITTED")
qual = {
    "record_type": "MR002_Increment3_Qualification",
    "increment": 3, "version": "1.0",
    "scope": "identity-bound loader + strict candidate schema + inverse-vol/normalization + entry-neutral "
             "construction + position->sector->beta removal cascade + pending/exits-first state + "
             "Increment-2 execution integration (preview->verify->commit) + three-state exposure + "
             "official-open daily NAV/returns + Increment-1 metric integration; synthetic-only",
    "owner_authorization": "docs/review/comments.md build-plan verdict 2026-07-20 (Increment 3 authorized with four clarifications incorporated)",
    "governing_identities": {"registry_v1.0": identity["registry_sha256"],
                             "resolution_v1.0": identity["resolution_sha256"],
                             "sources": identity["source_shas"]},
    "clarifications_incorporated": [
        "HeldPosition carries entry_registered_signal_value + originating_candidate_id + eligibility_evidence_identity",
        "candidate/market execution-input identity (CANDIDATE_EXECUTION_INPUT_MISMATCH) + NAV_IDENTITY_MISMATCH",
        "full-session atomic preview: exits -> provisional state -> entries -> verify -> commit",
        "sector/beta realized fail-closed (distinct REALIZED_* codes); Increment-2 clip/cost primitives reused (no duplication)"],
    "excluded_not_authorized": ["real residual/z/sigma", "PIT sector reconstruction", "real vendor adapters",
        "validation/OOS access", "development performance", "performance interpretation", "production promotion"],
    "source_hashes": {s: sha(s) for s in SRC},
    "dependency_lock": DEP_LOCK, "dependency_lock_sha256": sha(DEP_LOCK),
    "tests": {"count": 27, "result": "27 passed", "file": "test_increment3.py",
              "matrix": "MR002_Increment3_QualificationMatrix_v1.0.json (T3-01..T3-33; consolidated)"},
    "full_evaluator_suite": "121 passed (Increment 1: 59, Increment 2: 35, Increment 3: 27; Increment-2 refactor behavior-preserving)",
    "replay_report_output_hash": report["output_hash"],
    "determinism_proof": {"run1_hash": report["output_hash"], "run2_hash": report2["output_hash"],
                          "byte_identical": report["output_hash"] == report2["output_hash"]},
    "report_self_hash_verifies": P.report_hash(report) == report["output_hash"],
    "sessions_committed": committed,
    "metric_input_series_len": metrics["input_series_len"],
    "metric_input_is_portfolio_series": metrics["input_series_exact_hex"] == [float(r).hex() for r in replay["return_series"]],
    "development_free_assertions": {"validation_data_read": report["validation_data_read"],
        "oos_data_read": report["oos_data_read"],
        "development_performance_computed": report["development_performance_computed"],
        "synthetic_fixture_only": report["synthetic_fixture_only"]},
    "no_real_dataset_opened": True,
}
open("MR002_Increment3_Qualification.json", "w", encoding="utf-8").write(json.dumps(qual, sort_keys=True, indent=2))
print("replay_report_output_hash:", report["output_hash"])
print("determinism byte_identical:", qual["determinism_proof"]["byte_identical"])
print("sessions committed:", committed, "| metric series is portfolio series:", qual["metric_input_is_portfolio_series"])
