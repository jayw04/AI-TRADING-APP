"""MR-002 OQ-1 — operational qualification entrypoint (Components 3-8 orchestration).

preflight -> (if PASS) run the accepted synthetic replay + determinism -> build the OQ-1 qualification
report -> publish an immutable local bundle -> exit code. A failed preflight executes NO portfolio
session. All nonzero exits emit a canonical refusal record. No real data; network-disabled run.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "evaluator")))

import oq1_determinism as DET      # noqa: E402
import oq1_exit_codes as EC        # noqa: E402
import oq1_preflight as PF         # noqa: E402

ACCEPTED_OUTPUT_HASH = "42c5cee0fc121f1fabf9ff1916a02cc8bd922ce69b8f80d85be7852dc5fde907"
ACCEPTED_SCHEMA = "increment3-v1.1-synthetic"
FIXED_TS = "OQ1-SYNTHETIC-RUN"                                 # deterministic: no wall-clock in evidence


def qualify(*, output_dir: str, container_digest: str = "n/a", code_commit: str = "n/a",
            require_network_disabled: bool = True) -> dict:
    dep_lock_hash = hashlib.sha256(open(os.path.join(HERE, "wheelhouse-manifest.json"), "rb").read()).hexdigest()

    def refusal(reason, stage, expected, observed):
        return EC.refusal_record(reason_code=reason, stage=stage, expected=expected, observed=observed,
                                 code_commit=code_commit, container_digest=container_digest,
                                 dependency_lock_hash=dep_lock_hash, timestamp=FIXED_TS)

    pre = PF.run_preflight(container_digest=container_digest,
                           require_network_disabled=require_network_disabled, output_dir=output_dir)
    if not pre["all_pass"]:                                    # a failed preflight runs NO portfolio session
        reason = (pre["stops"] or pre["refusals"] or ["INTEGRITY_STOP:PREFLIGHT"])[0]
        rec = refusal(reason.split(":", 2)[0] + (":" + reason.split(":", 2)[1] if ":" in reason else ""),
                      "preflight", "PREFLIGHT_PASS", pre["disposition"])
        rec["preflight"] = pre
        return {"exit_code": EC.exit_code_for(reason), "disposition": "REFUSED", "refusal": rec,
                "portfolio_session_executed": False}

    # preflight passed -> now (and only now) run the pipeline (in-memory; no writes to read-only code)
    report_a = DET.run_replay_report()
    report_b = DET.run_replay_report()
    det = DET.compare(report_a, report_b, accepted_output_hash=ACCEPTED_OUTPUT_HASH)
    if det["verdict"] != "DETERMINISTIC":
        rec = refusal("DETERMINISM_MISMATCH", "determinism", ACCEPTED_OUTPUT_HASH, det["output_hash_a"])
        rec["determinism"] = det
        return {"exit_code": EC.EXIT["DETERMINISM_MISMATCH"], "disposition": "REFUSED", "refusal": rec,
                "portfolio_session_executed": True}

    qual = {
        "record_type": "MR002_OQ1_Qualification", "version": "1.0",
        "disposition": "OQ1_PASS",
        "accepted_schema": ACCEPTED_SCHEMA, "accepted_output_hash": ACCEPTED_OUTPUT_HASH,
        "reproduced_output_hash": report_a["output_hash"],
        "economic_payload_hash": det["economic_payload_hash"],
        "determinism": det, "preflight": pre,
        "container_digest": container_digest, "code_commit": code_commit,
        "dependency_lock_hash": dep_lock_hash,
        "assertions": {"validation_authorization": False, "validation_data_read": False,
                       "oos_data_read": False, "development_performance_computed": False,
                       "real_data_accessed": False, "synthetic_fixture_only": True,
                       "performance_interpretation_authorized": False,
                       "production_promotion_authorized": False},
    }
    return {"exit_code": EC.EXIT["PASS"], "disposition": "OQ1_PASS", "qualification": qual, "report": report_a,
            "portfolio_session_executed": True}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    out = os.environ.get("OQ1_OUTPUT_DIR", os.path.join(HERE, "evidence"))
    os.makedirs(out, exist_ok=True)
    res = qualify(output_dir=out, container_digest=os.environ.get("OQ1_CONTAINER_DIGEST", "n/a"),
                  code_commit=os.environ.get("OQ1_CODE_COMMIT", "n/a"),
                  require_network_disabled=os.environ.get("OQ1_REQUIRE_NETWORK_DISABLED", "1") == "1")
    which = res.get("qualification") or res.get("refusal")
    open(os.path.join(out, "MR002_OQ1_Qualification.json"), "w", encoding="utf-8", newline="\n").write(
        json.dumps(which, sort_keys=True, indent=1) + "\n")
    print(f"OQ1 disposition={res['disposition']} exit={res['exit_code']} "
          f"portfolio_session_executed={res['portfolio_session_executed']}")
    return res["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
