"""SPQ-1 Phase 2B-0 — Run Specification generator (spec only; NO signal production).

Corrections applied (2B-0 adjudication): (1) all bound identities are full 64-char SHA-256 / 40-char
commits, validated before any write; (2) the universe + sic_mapping identity reads go through the
Phase-2A PartitionGuard and are recorded in a dedicated 2B-0 opened-object ledger with completed-read
evidence; (3) the universe identity hashes the EXACT authorized governing-month row set and the
manifest freezes the monthly PIT membership-selection rule; (4) the repository root is derived from
this file's location (no workstation path). The SIC-mapping effective-time selection rule is frozen.
Produces no signal, no performance, no candidate records.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import duckdb

ROOT = str(Path(__file__).resolve().parents[5])   # .../ai-trading-app (portable; no hardcoded path)
OUT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "apps", "backend"))

from app.research.mr002.spq1.adapters import (  # noqa: E402
    ADAPTER_CODE_VERSION,
    DEV_CALENDAR_SHA256,
    DEV_END,
    GOVERNED_SESSION_LIST_SHA256,
    REGISTERED_PROVENANCE_DB,
    REGISTERED_RESEARCH_DB,
    abs_path,
)
from app.research.mr002.spq1.adapters.manifests import sha256_file  # noqa: E402
from app.research.mr002.spq1.adapters.partition_guard import (  # noqa: E402
    OpenedObjectLedger,
    PartitionGuard,
)
from app.research.mr002.spq1.identities import canonical_sha256  # noqa: E402

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
RUN_ID = "MR002-SPQ1-P2B-DEV-V1"
REVIEW_DATE = "2026-07-20"

# Exact authorized universe governing-month window (monthly PIT reconstitution covering dev sessions).
UNI_MONTH_FIRST = "2013-01-01"   # governs the first dev session 2013-01-02 (no pre-window seed needed)
UNI_MONTH_LAST = "2019-10-01"    # max universe_month <= DEV_END 2019-10-02


def _assert_identities(sha_fields: dict, commit_fields: dict) -> None:
    for k, v in sha_fields.items():
        if not (isinstance(v, str) and _SHA256.match(v)):
            raise ValueError(f"SHA-256 field {k!r} is not 64 lowercase hex (got {v!r})")
    for k, v in commit_fields.items():
        if not (isinstance(v, str) and _COMMIT.match(v)):
            raise ValueError(f"commit field {k!r} is not a full 40-char id (got {v!r})")


def _guarded_table(guard, con, research_sha, table, where, params, temporal_col):  # noqa: ANN001
    """Authorize -> read -> record a completed read; return (content_sha256, row_count)."""
    token = guard.authorize_read(REGISTERED_RESEARCH_DB, UNI_MONTH_FIRST, DEV_END,
                                 f"2b0_identity:{table}", "phase2b0-runspec", allow_pre_window=True)
    cols = [d[0] for d in con.execute(f"select * from {table} limit 0").description]
    rows = con.execute(f"select * from {table} where {where}", params).fetchall()
    norm = [[None if v is None else str(v) for v in r] for r in rows]
    norm.sort(key=lambda r: json.dumps(r))
    content = canonical_sha256(norm)
    ti = cols.index(temporal_col)
    keys = [str(r[ti])[:10] for r in norm if r[ti] is not None]
    guard.record_completed_read(
        token, research_sha, f"{table}:{where}", min(keys) if keys else None,
        max(keys) if keys else None, len(norm), content, "", allow_pre_window=True)
    return content, len(norm)


def run() -> dict:
    research_sha = sha256_file(abs_path(REGISTERED_RESEARCH_DB))
    prov_sha = sha256_file(abs_path(REGISTERED_PROVENANCE_DB))

    ledger = OpenedObjectLedger()
    guard = PartitionGuard(
        frozenset([REGISTERED_RESEARCH_DB, REGISTERED_PROVENANCE_DB]), ledger)
    con = duckdb.connect(abs_path(REGISTERED_RESEARCH_DB), read_only=True)
    uni_sha, uni_n = _guarded_table(
        guard, con, research_sha, "universe",
        "universe_month between $a and $b", {"a": UNI_MONTH_FIRST, "b": UNI_MONTH_LAST},
        "universe_month")
    sic_sha, sic_n = _guarded_table(
        guard, con, research_sha, "sic_mapping", "1=1", {}, "effective_from")
    # Amendment: research.sic_observations is the registered PIT-sector observation source (covers
    # 534/535 dev-universe ciks; the Phase-2A provenance copy covers only 13). Guarded + ledgered.
    sic_obs_sha, sic_obs_n = _guarded_table(
        guard, con, research_sha, "sic_observations",
        "cast(accepted_utc as date) <= $b", {"b": DEV_END}, "accepted_utc")
    con.close()

    core = os.path.join(ROOT, "apps", "backend", "app", "research", "mr002", "spq1")
    adp = os.path.join(core, "adapters")
    p2b = os.path.join(core, "phase2b")
    producer_hashes = {f: sha256_file(os.path.join(core, f))
                       for f in sorted(x for x in os.listdir(core) if x.endswith(".py"))}
    adapter_hashes = {f: sha256_file(os.path.join(adp, f))
                      for f in sorted(x for x in os.listdir(adp) if x.endswith(".py"))}
    phase2b_hashes = {f: sha256_file(os.path.join(p2b, f))
                      for f in sorted(x for x in os.listdir(p2b) if x.endswith(".py"))}
    phase2b_orchestration_code_identity = canonical_sha256(phase2b_hashes)

    sha_ids = {
        "phase0_census_sha256": "87602e7c5e5c719a44d83d6a556690116958c58e1e0d97b687531da824f9008e",
        "owner_rulings_sha256": "d8a9071d53bdb036ad9e6d46cd0d899f6846d3f2af946f932ce963e10f0e206a",
        "phase0_schema_sha256": "49c0e550f78127e04fcf92a649645aef23560173ccf89ef630dab30d4892497f",
        "phase1_valid_path_output_sha256": "c9ebd7f9c88a7d9c73ca391245f0b4305ffe721fdbf13731271d003aa8d40d6f",
        "increment3_accepted_output_sha256": "42c5cee0fc121f1fabf9ff1916a02cc8bd922ce69b8f80d85be7852dc5fde907",
        "phase2a_dev_snapshot_content_sha256": "211eacc0ff55904e7494b9688e74b76e57128a4e59cd809f78d66bf1621d3ae2",
        "dev_calendar_sha256": DEV_CALENDAR_SHA256,
        "governed_session_list_reference_sha256": GOVERNED_SESSION_LIST_SHA256,
        "research_db_sha256": research_sha, "provenance_db_sha256": prov_sha,
        "sic_mapping_content_sha256": sic_sha, "universe_content_sha256": uni_sha,
        "pit_sector_observation_source_sha256": sic_obs_sha,
        "phase2b_orchestration_code_identity": phase2b_orchestration_code_identity,
    }
    commit_ids = {
        "phase0_closeout": "023b75e837a6ca5992da4bf483dd122d35759e59",
        "phase1_closeout": "18561c3a8c56ff54b9fdfd1da8e7d9db6e2cfd60",
        "phase2a_closeout": "673f10bdc84e276d5fc1d5bce39f459c8bc869af",
    }
    for h in list(producer_hashes.values()) + list(adapter_hashes.values()):
        sha_ids[f"_code_{h[:8]}"] = h
    _assert_identities(sha_ids, commit_ids)
    for k in [k for k in sha_ids if k.startswith("_code_")]:
        del sha_ids[k]

    opened_object_ledger = {
        "record_type": "MR002_SPQ1_Phase2B_2B0_OpenedObjectLedger", "version": "1.0", "run_id": RUN_ID,
        "entries": ledger.entries, "count": len(ledger.entries),
        "all_completed": all(e["status"] == "COMPLETED" for e in ledger.entries),
        "no_actual_key_beyond_dev_end": all(
            e["actual_max_date"] is None or str(e["actual_max_date"]) <= DEV_END for e in ledger.entries),
        "validation_or_oos_objects_opened": 0,
        "note": "2B-0 reads are limited to the universe + sic_mapping identity binding; guarded, "
                "authorized, and recorded as completed reads (distinct from the Phase-2A ledger).",
    }

    universe_rule = {
        "source": "universe table (monthly PIT reconstitution)",
        "governing_universe_month": "max registered universe_month whose availability (= the "
            "universe_month date) is <= close(session t)",
        "membership_from": "ONLY the rows of that single governing month",
        "authorized_row_set": f"universe_month between {UNI_MONTH_FIRST} and {UNI_MONTH_LAST} "
            "(82 governing months covering dev sessions 2013-01-02..2019-10-02)",
        "pre_window_seed": "none required (the 2013-01 reconstitution governs the first dev session)",
        "availability_convention": "universe_month date is the reconstitution availability timestamp",
        "uniqueness_key": "(universe_month, permanent_security_id)",
        "missing_governing_month": "INELIGIBLE:OLS_WINDOW_INSUFFICIENT is NOT used; a missing governing "
            "month is a universe-integrity failure -> INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS (frozen)",
        "duplicate_membership_row": "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS",
        "future_universe_month": "excluded; can never influence session t",
        "membership_flags": "top-250 in_long_universe / top-150 in_short_universe per §4",
        "survivorship": "PIT, survivorship-free; never a present-day constituent list",
    }
    sic_rule = {
        "table": "registered owner-countersigned sic_mapping (content-hash bound)",
        "sector_lookup": "the row whose [sic_start, sic_end] inclusive range contains the security's "
            "PIT SIC (from sic_observations.accepted_utc <= close t)",
        "effective_time_selection": "among rows covering the SIC, the latest effective_from <= close t "
            "governs (NULL effective_from = always-effective); range boundaries inclusive",
        "same_effective_time_conflict": "INTEGRITY_STOP:SECTOR_EFFECTIVE_DATE_CONFLICT",
        "revision_supersession_order": "effective_from then review_status (approved supersedes draft)",
        "missing_sic_range": "INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING (never defaulted)",
        "sector_to_etf": "the sector_etf column (11 SPDR select-sector ETFs); one ETF per sector",
    }
    pit_sector_obs_rule = {
        "source": "research.sic_observations (the registered PIT-sector observation source)",
        "registered_database_sha256": research_sha,
        "content_sha256": sic_obs_sha, "rows": sic_obs_n,
        "authorized_columns": ["cik", "accepted_utc", "sic", "accession (provenance/source identity)"],
        "development_upper_bound": "accepted_utc <= DEV_END close (cast to date <= 2019-10-02)",
        "pre_window_policy": "earlier accepted observations allowed as PIT state seeds (allow_pre_window)",
        "uniqueness_key": "(cik, accepted_utc, accession); PIT selection = latest accepted_utc <= close t",
        "same_acceptance_time_conflict": "INTEGRITY_STOP:SECTOR_EFFECTIVE_DATE_CONFLICT",
        "coverage": "534 of 535 development-universe ciks",
        "missing_covered_cik": "INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING",
        "amends": "the 2B-0 ratified contract's provenance sic_observations source (only 13 ciks); "
                  "guarded + ledgered identically to every other real-data input.",
    }

    input_identity_manifest = {
        "record_type": "MR002_SPQ1_Phase2B_InputIdentityManifest", "version": "1.0", "run_id": RUN_ID,
        "registered_sources": {
            "mr002_research.duckdb": {"sha256": research_sha, "role": "prices/etf_prices/actions/crosswalk/universe/sic_mapping"},
            "mr002_provenance.duckdb": {"sha256": prov_sha, "role": "sic_observations/earnings_anchors"},
            "sic_mapping_table": {"content_sha256": sic_sha, "rows": sic_n, "role": "SIC-range -> sector -> ETF"},
            "development_universe": {"content_sha256": uni_sha, "rows": uni_n, "months": 82,
                                    "authorized_row_set": universe_rule["authorized_row_set"]},
            "pit_sector_observation_source": {"table": "research.sic_observations",
                                             "content_sha256": sic_obs_sha, "rows": sic_obs_n,
                                             "rule": pit_sector_obs_rule},
        },
        "code_identities": {"producer_modules": producer_hashes, "adapter_modules": adapter_hashes,
                            "phase2b_execution_modules": phase2b_hashes,
                            "phase2b_orchestration_code_identity": phase2b_orchestration_code_identity,
                            "adapter_code_version": ADAPTER_CODE_VERSION},
        "bound_prior_identities": {**sha_ids, **commit_ids},
        "opened_object_ledger_ref": "MR002_SPQ1_Phase2B_2B0_OpenedObjectLedger_v1.0.json",
    }

    development_run_manifest = {
        "record_type": "MR002_SPQ1_Phase2B_DevelopmentRunManifest", "version": "1.0", "run_id": RUN_ID,
        "development_window": {"start": "2013-01-02", "end": DEV_END, "sessions": 1700,
                              "dev_calendar_sha256": DEV_CALENDAR_SHA256,
                              "governed_session_list_reference_sha256": GOVERNED_SESSION_LIST_SHA256},
        "universe": {"identity": uni_sha, "rows": uni_n, "months": 82, "selection_rule": universe_rule},
        "security_types": {"included": "US-listed operating-company common equity + governed share classes (Ruling 10)",
                          "excluded": "ETF/ETN/CEF/preferred/rights/warrants/units/SPAC-units/OTC/foreign-ordinary/duplicate"},
        "factor_identities": {"market": "SPY total-return (etf_prices)", "sectors": "11 SPDR select-sector ETFs",
                             "sic_to_sector_etf_mapping": sic_sha, "sic_mapping_selection_rule": sic_rule},
        "pit_source_identities": {"sector": "research.sic_observations.accepted_utc + sic_mapping",
                                 "sector_observation_rule": pit_sector_obs_rule,
                                 "earnings": "earnings_anchors.acceptance_utc (BMO/AMC, amendments)",
                                 "corporate_actions": "actions.date", "adv": "closeunadj x volume"},
        "decision_cutoff": "registered ET regular-session close: 16:00 America/New_York -> UTC via "
                          "zoneinfo (21:00Z standard / 20:00Z daylight); no fabricated fixed UTC",
        "phase2b_orchestration_code_identity": phase2b_orchestration_code_identity,
        "phase2b_execution_modules": phase2b_hashes,
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
            "batch_policy": "single-process == multi-shard == restart, byte-identical after canonical ordering",
            "checkpoint_policy": "atomic per-shard completion; completed-shard SHA-256 recorded; non-overwriting",
            "restart_policy": "resume from last completed shard; never overwrite/duplicate/skip; identical final manifest",
            "failure_policy": "raw exception / unregistered refusal / reconciliation mismatch / post-dev row / "
                              "validation-OOS reference -> STOP, no repair/tune/reinterpret",
            "eligibility_boundary": "close-t only; any post-close-t fact -> INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED",
            "execution_enrichment": "NOT a full run; only a preregistered mechanical sample proving the seam",
            "performance_quarantine": "signal values emitted but never ranked/interpreted; only implementation "
                                      "diagnostics permitted",
            "resource_limits": "single-process default; a second shard configuration + a restart run for invariance",
        },
    }

    run_specification = {
        "record_type": "MR002_SPQ1_Phase2B_RunSpecification", "version": "1.0",
        "run_id": RUN_ID, "stage": "SPQ-1 Phase 2B (development-period signal-production qualification)",
        "review_date": REVIEW_DATE, "increment": "2B-0 (run specification; NO computation)",
        "authorization": "LIMITED DEVELOPMENT-PARTITION COMPUTATION; performance NOT authorized; validation/OOS sealed",
        "frozen_mechanics": {
            "solver": "numpy.linalg.lstsq", "lapack": "gelsd/SVD", "dtype": "float64", "rcond": 1e-10,
            "ols_window": "60 registered sessions ending t-1", "r5": "5 consecutive residuals ending t",
            "normalization": "60 complete R5 observations ending t-1", "sigma": "sample std ddof=1",
            "warmup_return_sessions": 125, "warmup_price_observations": 126,
            "adv": "median(raw close x raw volume)", "adv_windows": "60 and 20 sessions ending t-1",
            "note": "FROZEN; no Phase-2B work may alter these mechanics."},
        "universe_selection_rule": universe_rule,
        "sic_mapping_selection_rule": sic_rule,
        "pit_sector_observation_source_rule": pit_sector_obs_rule,
        "decision_cutoff_rule": "registered ET regular-session close 16:00 America/New_York -> UTC via "
            "zoneinfo (21:00Z standard / 20:00Z daylight per historical session date); NOT a fabricated "
            "fixed 21:00Z (which would leak 4-5pm ET evidence in summer).",
        "phase2b_orchestration_code_identity": phase2b_orchestration_code_identity,
        "amendment": "2B-0 amendment (post-2B-1 adjudication): PIT-sector source = research.sic_observations; "
            "decision cutoff = ET-close via zoneinfo; Phase-2B execution-code identity bound. Run ID unchanged.",
        "bound_identities": {**sha_ids, **commit_ids,
                            "development_run_manifest": None, "input_identity_manifest": None,
                            "opened_object_ledger": None},
        "increments": {"2B-0": "run specification (this)", "2B-1": "dry-run + limited-shard qualification (gate)",
                      "2B-2": "full development signal-production run", "2B-3": "reconciliation/determinism/closeout"},
        "not_authorized": ["ranking/interpretation", "portfolio", "execution replay", "P&L/returns/Sharpe/DSR",
                          "A/B/C comparison", "parameter tuning", "validation", "OOS", "order-path", "production"],
        "supersedes_phase2a_placeholder": "the full run binds the registered sic_mapping for SIC->sector->ETF; "
            "the Phase-2A pit_sector_adapter division placeholder is a one-sample stand-in, replaced for the run.",
    }

    def dump(obj, name, subdir):
        d = os.path.join(OUT, subdir)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        open(p, "w", encoding="utf-8", newline="\n").write(
            json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n")
        return hashlib.sha256(open(p, "rb").read()).hexdigest()

    ool = dump(opened_object_ledger, "MR002_SPQ1_Phase2B_2B0_OpenedObjectLedger_v1.0.json", "evidence")
    irm = dump(input_identity_manifest, "MR002_SPQ1_Phase2B_InputIdentityManifest_v1.0.json", "manifests")
    drm = dump(development_run_manifest, "MR002_SPQ1_Phase2B_DevelopmentRunManifest_v1.0.json", "manifests")
    run_specification["bound_identities"]["development_run_manifest"] = drm
    run_specification["bound_identities"]["input_identity_manifest"] = irm
    run_specification["bound_identities"]["opened_object_ledger"] = ool
    run_specification["run_specification_sha256"] = None
    body_hash = canonical_sha256(run_specification)
    run_specification["run_specification_sha256"] = body_hash
    _assert_identities({"run_specification_sha256": body_hash, "development_run_manifest": drm,
                        "input_identity_manifest": irm, "opened_object_ledger": ool,
                        "universe_content_sha256": uni_sha, "sic_mapping_content_sha256": sic_sha}, {})
    rs = dump(run_specification, "MR002_SPQ1_Phase2B_RunSpecification_v1.0.json", "run_spec")
    return {"RunSpecification": rs, "run_spec_body": body_hash, "DevelopmentRunManifest": drm,
            "InputIdentityManifest": irm, "OpenedObjectLedger": ool, "universe": uni_sha,
            "sic_mapping": sic_sha, "research_db": research_sha, "prov_db": prov_sha,
            "ledger_entries": len(ledger.entries)}


if __name__ == "__main__":
    out = run()
    for k, v in out.items():
        print(f"{k}: {v[:16] if isinstance(v, str) else v}")
    print("RUN_ID:", RUN_ID)
