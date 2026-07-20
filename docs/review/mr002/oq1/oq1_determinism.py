"""MR-002 OQ-1 — deterministic operational run + comparison projection (Component 6).

Runs the accepted synthetic replay and proves byte-determinism; defines the comparison projection that
isolates the economic/evaluator payload from operational provenance fields so host-vs-container and
image-vs-rebuild comparisons are explainable.
"""

from __future__ import annotations

import hashlib
import json

# operational-provenance fields excluded from the economic-payload projection
OPERATIONAL_FIELDS = {"code_identity", "dependency_lock_sha256", "governing_source_identities"}


def economic_payload_hash(report: dict) -> str:
    """Hash of the report with operational-provenance fields removed. The economic/evaluator payload
    (sessions, exposures, NAV, returns, metrics, verdict labels) must be byte-identical across
    environments even if operational provenance changes."""
    payload = {k: v for k, v in report.items() if k not in OPERATIONAL_FIELDS and k != "output_hash"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def run_replay_report():
    """Reproduce the accepted synthetic replay report IN MEMORY (writes nothing — read-only-code safe).
    Replicates the _gen_evidence_inc3 construction exactly so the bytes stay identical to the accepted
    output_hash: same synthetic fixture, same code_identity over the evaluator sources, same dep lock."""
    import hashlib as _h
    import os as _os

    import mr002_valoos_pipeline as P
    import mr002_valoos_portfolio_identity as ID

    ev = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "evaluator"))
    src = ["mr002_valoos_portfolio_identity.py", "mr002_valoos_candidates.py", "mr002_valoos_construction.py",
           "mr002_valoos_portfolio_state.py", "mr002_valoos_exposure.py", "mr002_valoos_replay.py",
           "mr002_valoos_nav.py", "mr002_valoos_pipeline.py", "test_increment3.py", "_gen_evidence_inc3.py"]
    dep_lock = "MR002_Increment1_Dependencies.json"

    def sha(name):
        return _h.sha256(open(_os.path.join(ev, name), "rb").read()).hexdigest()

    def cand(cid, side, z, sec):
        return {"candidate_id": cid, "permanent_security_id": cid, "signal_origin_session": 1,
                "decision_session": 0, "symbol": cid, "side": side, "registered_signal_value": z,
                "registered_sigma_resid": 0.02, "sector_id": sec, "beta": 0.05, "eligibility_status": "ELIGIBLE",
                "eligibility_evidence_identity": "ev", "configuration_id": "B",
                "official_next_open_price": 100.0, "trailing_adv_dollars": 1e15}

    recs = []
    for sec in range(5):
        for j in range(10):
            recs.append(cand(f"L{sec}_{j}", "long", -3.0 if j == 0 else -2.0, f"SEC{sec}"))
            recs.append(cand(f"S{sec}_{j}", "short", 3.0 if j == 0 else 2.0, f"SEC{sec}"))
    held = [f"L{s}_0" for s in range(5)] + [f"S{s}_0" for s in range(5)]
    sess = [{"session": 1, "date": "2024-01-02", "opens": {r["candidate_id"]: 100.0 for r in recs},
             "adv": {r["candidate_id"]: 1e15 for r in recs}, "candidate_records": recs, "exit_signals": []}]
    for k, s in enumerate((2, 3, 4), start=1):
        o = {sym: (100.0 + k * (1 if sym.startswith("L") else -1)) for sym in held}
        sess.append({"session": s, "date": f"2024-01-0{s + 1}", "opens": o, "adv": {},
                     "candidate_records": [], "exit_signals": []})

    identity = ID.load_portfolio_identity(_os.path.abspath(_os.path.join(ev, "..")))
    replay = P.run_replay(sess, initial_cash=1_000_000.0, config_id="B")
    return P.build_pipeline_report(
        replay=replay, metrics=P.metric_handoff(replay["return_series"]),
        identity={"registry_sha256": identity["registry_sha256"], "resolution_sha256": identity["resolution_sha256"],
                  "source_shas": identity["source_shas"]},
        config_id="B", code_identity={s: sha(s) for s in src}, dependency_lock_sha256=sha(dep_lock))


def compare(report_a: dict, report_b: dict, *, accepted_output_hash: str | None = None) -> dict:
    """Full byte comparison + economic-payload projection. Returns a determinism verdict."""
    out_match = report_a["output_hash"] == report_b["output_hash"]
    econ_match = economic_payload_hash(report_a) == economic_payload_hash(report_b)
    accepted_ok = accepted_output_hash is None or report_a["output_hash"] == accepted_output_hash
    return {"output_hash_match": out_match, "economic_payload_match": econ_match,
            "accepted_hash_reproduced": accepted_ok,
            "output_hash_a": report_a["output_hash"], "output_hash_b": report_b["output_hash"],
            "economic_payload_hash": economic_payload_hash(report_a),
            "verdict": "DETERMINISTIC" if (out_match and econ_match and accepted_ok) else "DETERMINISM_MISMATCH"}
