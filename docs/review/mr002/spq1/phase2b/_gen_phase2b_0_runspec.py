"""SPQ-1 Phase 2B-0 — Run Specification generator (spec only; NO computation, NO signal production).

Freezes the development-run identity and binds every source + code identity, the universe and
registered SIC->sector->ETF mapping, PIT sources, and the sharding / ordering / checkpoint / restart /
failure policies. Reads source tables only to bind their content identities (dev-bounded); produces
no signal, no performance, no candidate records.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import duckdb

ROOT = r"C:\LLM-RAG-APP\ai-trading-app"
OUT = os.path.dirname(os.path.abspath(__file__))
BE = os.path.join(ROOT, "apps", "backend")
sys.path.insert(0, BE)

from app.research.mr002.spq1.adapters import (  # noqa: E402
    ADAPTER_CODE_VERSION,
    DEV_CALENDAR_SHA256,
    DEV_END,
    DEV_START,
    GOVERNED_SESSION_LIST_SHA256,
    REGISTERED_PROVENANCE_DB,
    REGISTERED_RESEARCH_DB,
    abs_path,
)
from app.research.mr002.spq1.adapters.manifests import sha256_file  # noqa: E402
from app.research.mr002.spq1.identities import canonical_sha256  # noqa: E402


def dump(obj, name, subdir=""):
    d = os.path.join(OUT, subdir) if subdir else OUT
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    open(p, "w", encoding="utf-8", newline="\n").write(
        json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n")
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def table_content_sha(con, sql):  # noqa: ANN001
    rows = con.execute(sql).fetchall()
    norm = [[None if v is None else str(v) for v in r] for r in rows]
    norm.sort(key=lambda r: json.dumps(r))
    return canonical_sha256(norm), len(rows)


RUN_ID = "MR002-SPQ1-P2B-DEV-V1"
REVIEW_DATE = "2026-07-20"

# --- source + code identities ---
research_sha = sha256_file(abs_path(REGISTERED_RESEARCH_DB))
prov_sha = sha256_file(abs_path(REGISTERED_PROVENANCE_DB))
R = duckdb.connect(abs_path(REGISTERED_RESEARCH_DB), read_only=True)
sic_map_sha, sic_map_n = table_content_sha(R, "select * from sic_mapping")
uni_sha, uni_n = table_content_sha(
    R, f"select * from universe where universe_month <= '{DEV_END}'")
R.close()

CORE = os.path.join(BE, "app", "research", "mr002", "spq1")
ADP = os.path.join(CORE, "adapters")
producer_hashes = {f: sha256_file(os.path.join(CORE, f))
                   for f in sorted(x for x in os.listdir(CORE) if x.endswith(".py"))}
adapter_hashes = {f: sha256_file(os.path.join(ADP, f))
                  for f in sorted(x for x in os.listdir(ADP) if x.endswith(".py"))}

BOUND = {
    "phase0_census_sha256": "87602e7c5e5c719a44d83d6a556690116958c58e1e0d97b687531da824f9008e",
    "owner_rulings_sha256": "d8a9071d53bdb036ad9e6d46cd0d899f6846d3f2af946f932ce963e10f0e206a",
    "phase0_schema_sha256": "49c0e550f78127e04fcf92a649645aef23560173ccf89ef630dab30d4892497f",
    "phase1_valid_path_output_sha256": "c9ebd7f9c88a7d9c73ca391245f0b4305ffe721fdbf13731271d003aa8d40d6f",
    "increment3_accepted_output_sha256": "42c5cee0fc121f1fabf9ff1916a02cc8bd922ce69b8f80d85be7852dc5fde907",
    "phase2a_dev_snapshot_content_sha256": "211eacc0ff55904e...",
    "phase0_closeout": "023b75e837a6ca5992da4bf483dd122d35759e59",
    "phase1_closeout": "18561c3a8c56ff54b9fdfd1da8e7d9db6e2cfd60",
    "phase2a_closeout": "673f10bdc84e276d5fc1d5bce39f459c8bc869af",
}

FROZEN_MECHANICS = {
    "solver": "numpy.linalg.lstsq", "lapack": "gelsd/SVD", "dtype": "float64", "rcond": 1e-10,
    "ols_window": "60 registered sessions ending t-1", "r5": "5 consecutive residuals ending t",
    "normalization": "60 complete R5 observations ending t-1", "sigma": "sample std ddof=1",
    "warmup_return_sessions": 125, "warmup_price_observations": 126,
    "adv": "median(raw close x raw volume)", "adv_windows": "60 and 20 sessions ending t-1",
    "note": "FROZEN; no Phase-2B work may alter these mechanics.",
}

input_identity_manifest = {
    "record_type": "MR002_SPQ1_Phase2B_InputIdentityManifest", "version": "1.0", "run_id": RUN_ID,
    "registered_sources": {
        "mr002_research.duckdb": {"sha256": research_sha, "role": "prices/etf_prices/actions/crosswalk/universe/sic_mapping"},
        "mr002_provenance.duckdb": {"sha256": prov_sha, "role": "sic_observations/earnings_anchors"},
        "sic_mapping_table": {"content_sha256": sic_map_sha, "rows": sic_map_n,
                              "role": "registered owner-countersigned SIC-range -> sector -> ETF mapping"},
        "development_universe": {"content_sha256": uni_sha, "rows": uni_n, "months": 82,
                                "role": "monthly PIT membership (top-250 long / top-150 short)"},
    },
    "code_identities": {"producer_modules": producer_hashes, "adapter_modules": adapter_hashes,
                        "adapter_code_version": ADAPTER_CODE_VERSION},
    "bound_prior_identities": BOUND,
}

development_run_manifest = {
    "record_type": "MR002_SPQ1_Phase2B_DevelopmentRunManifest", "version": "1.0", "run_id": RUN_ID,
    "development_window": {"start": DEV_START, "end": DEV_END, "sessions": 1700,
                          "dev_calendar_sha256": DEV_CALENDAR_SHA256,
                          "governed_session_list_reference_sha256": GOVERNED_SESSION_LIST_SHA256},
    "universe": {"identity": uni_sha, "source": "universe table (monthly PIT)", "months": 82,
                "distinct_permatickers": 540, "membership_rule": "universe_month <= session month; "
                "top-250 long / top-150 shorts per §4; PIT, survivorship-free; never a present-day list"},
    "security_types": {"included": "US-listed operating-company common equity + governed share classes (Ruling 10)",
                      "excluded": "ETF/ETN/CEF/preferred/rights/warrants/units/SPAC-units/OTC/foreign-ordinary/duplicate"},
    "factor_identities": {"market": "SPY total-return (etf_prices)", "sectors": "11 SPDR select-sector ETFs",
                         "sic_to_sector_etf_mapping": sic_map_sha},
    "pit_source_identities": {"sector": "sic_observations.accepted_utc + sic_mapping",
                             "earnings": "earnings_anchors.acceptance_utc (BMO/AMC, amendments)",
                             "corporate_actions": "actions.date", "adv": "closeunadj x volume"},
    "partition_guard_identity": adapter_hashes["partition_guard.py"],
    "output": {"root": "docs/review/mr002/spq1/phase2b/",
              "subdirs": ["run_spec", "manifests", "evidence", "census", "qualification"],
              "large_records": "decision/disposition shards may stay out of git; identities+manifests committed"},
    "policies": {
        "unit_of_computation": "permanent_security_id x decision_session -> exactly one terminal disposition",
        "terminal_dispositions": ["SIGNAL_DECISION_RECORD_EMITTED", "INELIGIBLE", "INTEGRITY_STOP",
                                 "REFUSED_CODE_OR_DATA_IDENTITY"],
        "canonical_ordering": "(decision_session_ordinal asc, permanent_security_id asc)",
        "sharding": "contiguous session-ordinal blocks (independent units -> shard-invariant after canonical merge)",
        "batch_policy": "per-shard; single-process and multi-shard runs must be byte-identical after canonical ordering",
        "checkpoint_policy": "atomic per-shard completion; completed-shard SHA-256 recorded; non-overwriting",
        "restart_policy": "resume from last completed shard; never overwrite/duplicate/skip; identical final manifest",
        "failure_policy": "raw exception / unregistered refusal / reconciliation mismatch / post-dev row / "
                          "validation-OOS reference -> STOP, no repair/tune/reinterpret",
        "eligibility_boundary": "close-t only; any post-close-t fact -> INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED",
        "execution_enrichment": "NOT a full run; only a preregistered mechanical sample proving the seam",
        "performance_quarantine": "signal values emitted but never ranked/interpreted; only implementation "
                                  "diagnostics (finite counts, refusal/coverage distributions) permitted",
        "resource_limits": "single-process default; a second shard configuration + a restart run for invariance",
    },
}

run_specification = {
    "record_type": "MR002_SPQ1_Phase2B_RunSpecification", "version": "1.0",
    "run_id": RUN_ID, "stage": "SPQ-1 Phase 2B (development-period signal-production qualification)",
    "review_date": REVIEW_DATE,
    "authorization": "LIMITED DEVELOPMENT-PARTITION COMPUTATION; performance NOT authorized; validation/OOS sealed",
    "increment": "2B-0 (run specification; NO computation)",
    "frozen_mechanics": FROZEN_MECHANICS,
    "bound_identities": {
        "development_run_manifest": None,  # filled after hashing
        "input_identity_manifest": None,
        **BOUND,
        "sic_mapping_sha256": sic_map_sha, "universe_sha256": uni_sha,
        "research_db_sha256": research_sha, "provenance_db_sha256": prov_sha,
    },
    "increments": {"2B-0": "run specification (this)", "2B-1": "dry-run + limited-shard qualification (gate)",
                  "2B-2": "full development signal-production run", "2B-3": "reconciliation/determinism/closeout"},
    "acceptance_gates": ["all 1700 sessions processed", "one terminal disposition per eligible unit",
                        "exact reconciliation", "development-only reads", "zero validation/OOS objects",
                        "PIT-valid records", "repeat-run byte-identical", "shard-invariant", "restart-identical",
                        "no deprecated/unknown code", "Phase-1 fixture + Increment-3 hash unchanged",
                        "no performance artifact"],
    "not_authorized": ["ranking/interpretation", "portfolio", "execution replay", "P&L/returns/Sharpe/DSR",
                      "A/B/C comparison", "parameter tuning", "validation", "OOS", "order-path", "production"],
    "supersedes_phase2a_placeholder": "the full run binds the registered sic_mapping (owner-countersigned) "
        "for SIC->sector->ETF; the Phase-2A pit_sector_adapter division placeholder is a one-sample stand-in "
        "and is replaced for the full-universe run.",
}

irm = dump(input_identity_manifest, "MR002_SPQ1_Phase2B_InputIdentityManifest_v1.0.json", "manifests")
drm_obj = development_run_manifest
run_specification["bound_identities"]["input_identity_manifest"] = irm
drm = dump(drm_obj, "MR002_SPQ1_Phase2B_DevelopmentRunManifest_v1.0.json", "manifests")
run_specification["bound_identities"]["development_run_manifest"] = drm
# run-spec hash = canonical hash of the spec with a null self-hash field
run_specification["run_specification_sha256"] = None
rs_body_hash = canonical_sha256(run_specification)
run_specification["run_specification_sha256"] = rs_body_hash
rs = dump(run_specification, "MR002_SPQ1_Phase2B_RunSpecification_v1.0.json", "run_spec")

print("research_db:", research_sha[:16], "prov_db:", prov_sha[:16])
print("sic_mapping:", sic_map_sha[:16], "rows", sic_map_n, "| universe:", uni_sha[:16], "rows", uni_n)
print("InputIdentityManifest:", irm[:16])
print("DevelopmentRunManifest:", drm[:16])
print("RunSpecification:", rs[:16], "| run_spec_body_hash:", rs_body_hash[:16])
print("RUN_ID:", RUN_ID)
