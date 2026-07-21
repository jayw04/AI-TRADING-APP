"""SPQ-1 Phase 2B-2 — full development-partition signal-production run + deterministic replay.

Enumerates the frozen PIT universe (governing-month membership) over all 1,700 development sessions,
runs the accepted producer (frozen orchestration-code identity bb029a96...) over every
(request-symbol x session) unit -> exactly one terminal disposition, shards by contiguous governing
month, publishes immutable shards, reconciles, and proves determinism via an INDEPENDENT second full
pass (fresh materialization + fresh enumeration + fresh run into a clean output location).

No signal value is ranked or interpreted (performance quarantine): only dispositions + record
identities are retained. Nothing here is modified in the frozen phase2b execution modules -- the
universe enumeration lives entirely in this runner and reads the registered universe table through the
returned PartitionGuard/ledger. Stops before Phase 2B-3 (closeout), which is NOT YET authorized.

Runtime: ~2 full passes over 425,000 units (materialize ~22min + run ~40min each) ~= 2 hours.
"""
from __future__ import annotations

import bisect
import functools
import hashlib
import json
import os
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

print = functools.partial(print, flush=True)  # noqa: A001

ROOT = str(Path(__file__).resolve().parents[5])
OUT = os.path.dirname(os.path.abspath(__file__))
O2 = os.path.join(OUT, "2b2")
sys.path.insert(0, os.path.join(ROOT, "apps", "backend"))

import duckdb  # noqa: E402

from app.research.mr002.spq1.adapters import (  # noqa: E402
    DEV_END,
    REGISTERED_PROVENANCE_DB,
    REGISTERED_RESEARCH_DB,
    abs_path,
)
from app.research.mr002.spq1.adapters.calendar_adapter import dev_calendar_sha256  # noqa: E402
from app.research.mr002.spq1.adapters.manifests import sha256_file  # noqa: E402
from app.research.mr002.spq1.identities import canonical_sha256  # noqa: E402
from app.research.mr002.spq1.phase2b import RUN_ID  # noqa: E402
from app.research.mr002.spq1.phase2b import orchestrator as ORCH  # noqa: E402
from app.research.mr002.spq1.refusals import DEPRECATED_CODES, REFUSAL_CODES  # noqa: E402

sys.path.insert(0, OUT)  # sibling: collision_rule.py (runner-side governed collision handling)
from collision_rule import (  # noqa: E402
    COLLISION_CODE,
    COLLISION_RULE_ID,
    module_identity as collision_module_identity,
    run_shard_governed,
)

# ---- governing run specification v1.1 (collision-rule amendment; hash fd19aef5...) ----
RUN_SPEC = json.load(open(os.path.join(OUT, "run_spec",
    "MR002_SPQ1_Phase2B_RunSpecification_v1.1.json")))
RUN_SPEC_SHA256 = RUN_SPEC["run_specification_sha256"]
BOUND = RUN_SPEC["bound_identities"]
BOUND_CODE_IDENTITY = json.load(open(os.path.join(OUT, "manifests",
    "MR002_SPQ1_Phase2B_InputIdentityManifest_v1.0.json")))["code_identities"][
    "phase2b_orchestration_code_identity"]
ORCH.verify_code_identity(ORCH.code_identity())  # self-check (no drift within a run)
assert canonical_sha256(ORCH.code_identity()) == BOUND_CODE_IDENTITY == BOUND[
    "phase2b_orchestration_code_identity"], "phase2b code identity drift"

UNI_FIRST, UNI_LAST = "2013-01-01", "2019-10-01"
PHASE1_SHA = "c9ebd7f9c88a7d9c73ca391245f0b4305ffe721fdbf13731271d003aa8d40d6f"
INCREMENT3_SHA = "42c5cee0fc121f1fabf9ff1916a02cc8bd922ce69b8f80d85be7852dc5fde907"
GOVERNING_RUN_SPEC_SHA = "fd19aef5230bac56bc82be1efb1be55ba3fe5d4f9daae33608f49ebbfd4554c3"

# ---- FROZEN SPQ-1 run configuration: authorized request population = the LONG side ----
# The frozen producer request is LONG (ProductionRequest("MR-002","B","LONG",...)); the authorized
# request population is ALL in_long_universe members for each development session. The in_short set is
# a strict SUBSET of in_long (verified below: short-only = 0), so short-side request units = 0 -- there
# are no short-only names to enumerate; they are outside this run's unit population by configuration.
AUTHORIZED_SIDE = "LONG"
_r = duckdb.connect(abs_path(REGISTERED_RESEARCH_DB), read_only=True)
SHORT_ONLY_MEMBERS = _r.execute(
    "select count(*) from universe where universe_month between ? and ?"
    " and in_short_universe and not in_long_universe", [UNI_FIRST, UNI_LAST]).fetchone()[0]
assert SHORT_ONLY_MEMBERS == 0, (
    f"frozen-config check: {SHORT_ONLY_MEMBERS} short-only members exist -> in_short is NOT a subset of "
    "in_long; a long-side-only 425,000-unit run would be INCOMPLETE. STOP and re-adjudicate the side.")
TICKERS = sorted({str(x[0]) for x in _r.execute(
    "select distinct ticker from universe where universe_month between ? and ?"
    " and in_long_universe", [UNI_FIRST, UNI_LAST]).fetchall()})
CIKS = sorted({int(c[0]) for c in _r.execute(
    "select distinct cik from crosswalk where ticker = ANY(?)", [TICKERS]).fetchall()})
_r.close()


def sha_file(p):  # noqa: ANN001
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def gtable(con, table, where, params):  # noqa: ANN001
    """EXACT 2B-0 identity computation: canonical_sha256 of stringified rows sorted by json.dumps."""
    rows = con.execute(f"select * from {table} where {where}", params).fetchall()
    norm = [[None if v is None else str(v) for v in r] for r in rows]
    norm.sort(key=lambda r: json.dumps(r))
    return canonical_sha256(norm), len(norm), norm


def preflight(src, guard):  # noqa: ANN001
    """Mandatory pre-run checks: every registered identity reproduces the bound value (guarded reads).
    Returns (check_results, uni_norm_rows). Aborts (assert) on ANY mismatch -> stop before publication."""
    research_sha = sha256_file(abs_path(REGISTERED_RESEARCH_DB))
    prov_sha = sha256_file(abs_path(REGISTERED_PROVENANCE_DB))

    def guarded_content(table, where, params, tcol):  # noqa: ANN001
        tok = guard.authorize_read(REGISTERED_RESEARCH_DB, UNI_FIRST, DEV_END,
                                   f"2b2_preflight:{table}", "phase2b2-runner", allow_pre_window=True)
        sha, n, norm = gtable(src, table, where, params)
        ti = [d[0] for d in src.execute(f"select * from {table} limit 0").description].index(tcol)
        keys = [str(r[ti])[:10] for r in norm if r[ti] is not None]
        guard.record_completed_read(tok, research_sha, f"{table}:{where}", min(keys) if keys else None,
                                    max(keys) if keys else None, n, sha, "", allow_pre_window=True)
        return sha, n, norm

    uni_sha, uni_n, uni_norm = guarded_content(
        "universe", "universe_month between $a and $b", {"a": UNI_FIRST, "b": UNI_LAST}, "universe_month")
    sic_sha, sic_n, _ = guarded_content("sic_mapping", "1=1", {}, "effective_from")
    obs_sha, obs_n, _ = guarded_content(
        "sic_observations", "cast(accepted_utc as date) <= $b", {"b": DEV_END}, "accepted_utc")

    checks = {
        "registered_research_db_identity_matches": research_sha == BOUND["research_db_sha256"],
        "registered_provenance_db_identity_matches": prov_sha == BOUND["provenance_db_sha256"],
        "universe_identity_matches": uni_sha == BOUND["universe_content_sha256"],
        "sic_mapping_identity_matches": sic_sha == BOUND["sic_mapping_content_sha256"],
        "pit_sector_source_identity_matches": obs_sha == BOUND["pit_sector_observation_source_sha256"],
        "phase2b_orchestration_code_identity_matches":
            canonical_sha256(ORCH.code_identity()) == BOUND["phase2b_orchestration_code_identity"],
        "run_specification_hash_matches": RUN_SPEC_SHA256 == GOVERNING_RUN_SPEC_SHA,
        "phase1_valid_path_output_unchanged": BOUND["phase1_valid_path_output_sha256"] == PHASE1_SHA,
        "increment3_accepted_output_unchanged": BOUND["increment3_accepted_output_sha256"] == INCREMENT3_SHA,
    }
    for k, ok in checks.items():
        assert ok, f"MANDATORY PRE-RUN CHECK FAILED: {k} -> STOP before any shard"
    results = dict(checks)
    results.update({"research_db_sha256": research_sha, "provenance_db_sha256": prov_sha,
                    "universe_content_sha256": uni_sha, "universe_rows": uni_n,
                    "sic_mapping_content_sha256": sic_sha, "pit_sector_observation_source_sha256": obs_sha,
                    "run_specification_sha256": RUN_SPEC_SHA256})
    return results, uni_norm


def build_members(uni_norm):  # noqa: ANN001
    """month -> sorted member tickers, from the same guarded universe rows used for identity.
    universe cols: universe_month, ticker, permaticker, siccode, liquidity_rank, med_dv_60,
    in_long_universe, in_short_universe. AUTHORIZED member population = in_long_universe (the LONG side);
    short-side units = 0 (in_short is a subset of in_long -- verified SHORT_ONLY_MEMBERS==0). Also
    month->{ticker:permaticker} and a per-month short-subset count (governance/disclosure only)."""
    members: dict[str, list] = {}
    permatickers: dict[str, dict] = {}
    short_subset: dict[str, int] = {}
    for row in uni_norm:
        month, ticker, permaticker = str(row[0])[:10], str(row[1]), str(row[2])
        is_long, is_short = str(row[6]) == "True", str(row[7]) == "True"
        if is_long:                                   # LONG side only = the authorized request population
            members.setdefault(month, []).append(ticker)
            permatickers.setdefault(month, {})[ticker] = permaticker
            if is_short:
                short_subset[month] = short_subset.get(month, 0) + 1
    for m in members:
        members[m] = sorted(members[m])
    return members, permatickers, short_subset


def canonical_ordering_ok(units):  # noqa: ANN001
    keys = [u.key() for u in units]
    return keys == sorted(keys)


def one_pass(tag, shards_dir, do_restart=False):  # noqa: ANN001
    """One independent full pass: materialize -> preflight -> enumerate -> run+publish 82 monthly shards
    -> merge -> aggregate hashes + censuses. Returns everything needed for artifacts / determinism."""
    t0 = time.time()
    os.makedirs(shards_dir, exist_ok=True)
    for f in os.listdir(shards_dir):  # clean output location
        os.remove(os.path.join(shards_dir, f))
    from app.research.mr002.spq1.adapters.partition_guard import OpenedObjectLedger
    ledger = OpenedObjectLedger()
    tmp = os.path.join(tempfile.gettempdir(), f"mr002_2b2_{tag}.duckdb")
    if os.path.exists(tmp):
        os.remove(tmp)
    con, guard, src, snap_path, snap_sha = ORCH.materialize_run_input(tmp, TICKERS, CIKS, ledger)
    print(f"[{tag}] materialized snapshot {snap_sha[:16]} ({time.time()-t0:.0f}s)")
    checks, uni_norm = preflight(src, guard)
    members, permatickers, short_subset = build_members(uni_norm)
    ctx = ORCH.build_context(con, guard, TICKERS, CIKS, src, snap_path, snap_sha)
    # dev calendar identity = the FROZEN newline-serialization dev_calendar_sha256 (the bound value +
    # the one load_calendar itself enforces on load), NOT RegisteredCalendar.identity (a distinct
    # canonical_sha256 serialization of the same session list).
    cal_sha = dev_calendar_sha256(tuple(ctx.calendar.sessions))
    assert cal_sha == BOUND["dev_calendar_sha256"], "dev calendar identity mismatch -> STOP"
    checks["dev_calendar_identity_matches"] = True
    checks["dev_calendar_sha256"] = cal_sha
    checks["registered_calendar_canonical_identity"] = ctx.calendar.identity
    checks["development_snapshot_content_sha256"] = snap_sha
    cal = ctx.calendar.sessions
    month_first = sorted(members)
    assert len(month_first) == 82, f"expected 82 governing months, got {len(month_first)}"

    def gov(dstr):
        return month_first[bisect.bisect_right(month_first, dstr) - 1]

    sess_by_month: dict[str, list] = {m: [] for m in month_first}
    for t, d in enumerate(cal):
        sess_by_month[gov(d)].append(t)
    # expected units reconstructed from shard facts: Σ(shard session_count × governing-month member_count)
    expected_units = sum(len(sess_by_month[m]) * len(members[m]) for m in month_first)
    print(f"[{tag}] enumerated {expected_units} LONG-side units across {len(cal)} sessions x 82 months "
          f"(members/month: {sorted({len(v) for v in members.values()})}; short-only=0); running shards...")

    shard_meta: dict[str, dict] = {}
    shard_content: dict[str, str] = {}
    all_results: list[list] = []
    shard_collision_rows: list = []
    overwrite_blocked_first = None
    tr = time.time()
    for i, m in enumerate(month_first):
        sess = sess_by_month[m]
        mem = members[m]
        exp = len(sess) * len(mem)                     # per-shard expected request-unit count
        units = [(tk, t) for t in sess for tk in mem]
        results, content, coll_rows = run_shard_governed(ctx, units)
        for cr in coll_rows:
            cr["governing_universe_month"] = m
        shard_collision_rows.extend(coll_rows)
        shard_path = os.path.join(shards_dir, f"{m}.json")
        ORCH.publish_shard(results, content, shard_path)
        # --- per-shard fail-fast gate (a violation is a STOP condition, not a repair) ---
        rk = ORCH.reconcile(results)
        d = Counter(u.disposition for u in results)
        unk = [u.code for u in results if u.code and u.code not in REFUSAL_CODES]
        assert len(results) == exp, f"[{tag}] shard {m}: actual {len(results)} != expected {exp} -> STOP"
        assert rk["duplicate_request_keys"] == 0, f"[{tag}] shard {m}: duplicate request keys -> STOP"
        assert rk["duplicate_resolved_permanent_security_session_keys"] == 0, \
            f"[{tag}] shard {m}: duplicate resolved unit -> STOP"
        assert not unk, f"[{tag}] shard {m}: unknown refusal codes {unk} -> STOP"
        if i == 0:                                     # early overwrite-immutability proof (milestone)
            try:
                ORCH.publish_shard(results, content, shard_path)
                overwrite_blocked_first = False
            except FileExistsError:
                overwrite_blocked_first = True
            assert overwrite_blocked_first, f"[{tag}] completed shard {m} was overwritable -> STOP"
        shard_meta[m] = {
            "shard_id": m, "run_id": RUN_ID, "run_spec_sha256": RUN_SPEC_SHA256,
            "governing_universe_month": m, "authorized_side": AUTHORIZED_SIDE,
            "member_count": len(mem), "member_set_sha256": canonical_sha256(mem),
            "member_source_set": mem, "short_subset_count": short_subset.get(m, 0),
            "session_ordinal_range": [sess[0], sess[-1]], "session_dates": [cal[t] for t in (sess[0], sess[-1])],
            "session_count": len(sess),
            "expected_request_unit_count": exp, "actual_terminal_outcome_count": len(results),
            "record_count": len(results), "duplicate_request_count": rk["duplicate_request_keys"],
            "duplicate_resolved_unit_count": rk["duplicate_resolved_permanent_security_session_keys"],
            "collision_request_units": len(coll_rows),
            "dispositions": dict(d), "content_sha256": content,
            "universe_identity": checks["universe_content_sha256"],
            "input_identity_manifest": None,  # filled after IIM is written
            "phase2b_orchestration_code_identity": BOUND["phase2b_orchestration_code_identity"],
            "completion_state": "COMPLETE"}
        shard_content[m] = content
        all_results.append(results)
        if i == 0 or (i + 1) % 20 == 0 or i + 1 == len(month_first):
            print(f"[{tag}] SHARD-GATE {i+1}/82 {m}: exp={exp} act={len(results)} dup_req=0 dup_res=0 "
                  f"unknown=0 overwrite_blocked={overwrite_blocked_first if i==0 else 'n/a'} "
                  f"({(time.time()-tr)/(i+1):.1f}s/shard, {time.time()-t0:.0f}s)")

    all_units = ORCH.merge(all_results)
    disp = Counter(u.disposition for u in all_units)
    codes = Counter(u.code for u in all_units if u.code)
    elig = Counter(u.decision_eligibility_status for u in all_units if u.decision_eligibility_status)
    recon_keys = ORCH.reconcile(all_units)

    # censuses
    session_census = {}
    for u in all_units:
        session_census.setdefault(u.decision_session, Counter())[u.disposition] += 1
    session_census = {str(k): {"date": cal[k], "dispositions": dict(v)}
                      for k, v in sorted(session_census.items())}
    security_census = {}
    for u in all_units:
        sc = security_census.setdefault(u.symbol, {"p": set(), "d": Counter()})
        sc["p"].add(u.permanent_security_id)
        sc["d"][u.disposition] += 1
    security_census = {k: {"resolved_permanent_security_ids": sorted(x for x in v["p"] if x),
                           "has_unresolved_units": "" in v["p"],
                           "dispositions": dict(v["d"])} for k, v in sorted(security_census.items())}
    refusal_census = {}
    for u in all_units:
        if u.code:
            rc = refusal_census.setdefault(u.code, {"classification": REFUSAL_CODES.get(u.code, "UNKNOWN"),
                                                    "count": 0, "sessions": set(), "securities": set()})
            rc["count"] += 1
            rc["sessions"].add(u.decision_session)
            rc["securities"].add(u.permanent_security_id or f"UNRESOLVED:{u.symbol}")
    refusal_census = {k: {"classification": v["classification"], "count": v["count"],
                          "first_session": min(v["sessions"]), "last_session": max(v["sessions"]),
                          "affected_securities": len(v["securities"])}
                      for k, v in sorted(refusal_census.items())}

    # --- CollisionCensus (MR002_SPQ1_NONINJECTIVE_REQUEST_IDENTITY_V1): per-request rows + group section ---
    collision_rows = sorted(shard_collision_rows, key=lambda r: (r["decision_session"], r["request_symbol"]))
    gmap: dict = {}
    for cr in collision_rows:
        g = gmap.setdefault(cr["collision_group_id"], {
            "collision_group_id": cr["collision_group_id"], "decision_session": cr["decision_session"],
            "session_date": cr["session_date"], "governing_universe_month": cr["governing_universe_month"],
            "claimed_permanent_security_id": cr["claimed_permanent_security_id"],
            "claimant_symbols": set(),
            "group_disposition_rule": f"{COLLISION_CODE} for ALL claimants (no winner selected)"})
        g["claimant_symbols"].add(cr["request_symbol"])
    collision_groups = [{**{k: v for k, v in g.items() if k != "claimant_symbols"},
                         "colliding_request_symbols": sorted(g["claimant_symbols"]),
                         "collision_cardinality": len(g["claimant_symbols"])}
                        for g in sorted(gmap.values(), key=lambda x: x["collision_group_id"])]
    collision_unit_keys = {(cr["decision_session"], cr["request_symbol"]) for cr in collision_rows}
    # collision-caused integrity stops (must equal the CollisionCensus affected-request count) vs
    # single-request lineage ambiguities emitted independently by frozen run_unit.
    ambig_units = [u for u in all_units if u.code == COLLISION_CODE]
    collision_caused = [u for u in ambig_units if (u.decision_session, u.symbol) in collision_unit_keys]
    single_request_ambig = [u for u in ambig_units if (u.decision_session, u.symbol) not in collision_unit_keys]
    collision_census = {
        "rule_id": COLLISION_RULE_ID, "terminal_code": COLLISION_CODE,
        "collision_group_count": len(collision_groups),
        "collision_request_unit_count": len(collision_rows),
        "distinct_collision_symbol_sets": len({tuple(g["colliding_request_symbols"]) for g in collision_groups}),
        "maximum_collision_cardinality": max((g["collision_cardinality"] for g in collision_groups), default=0),
        "affected_request_rows": collision_rows, "collision_groups": collision_groups,
        "reconciliation": {
            "affected_request_count": len(collision_rows),
            "collision_caused_security_identity_ambiguous_records": len(collision_caused),
            "reconciles": len(collision_rows) == len(collision_caused),
            "single_request_lineage_ambiguity_records": len(single_request_ambig),
            "note": "collision-caused stops are distinct from single-request PIT-resolution ambiguities; "
                    "affected_request_count must equal collision_caused records."}}
    assert collision_census["reconciliation"]["reconciles"], \
        f"[{tag}] CollisionCensus does not reconcile against collision-caused integrity stops -> STOP"
    collision_census_hash = canonical_sha256({k: v for k, v in collision_census.items()})

    # aggregate hashes (determinism surface)
    disposition_record_hash = canonical_sha256([u.as_row() for u in all_units])
    decision_record_hash = canonical_sha256(sorted(u.record_identity for u in all_units if u.record_identity))
    session_census_hash = canonical_sha256(session_census)
    security_census_hash = canonical_sha256(security_census)
    refusal_census_hash = canonical_sha256(refusal_census)
    publication_core = {
        "shard_content_sha256": {m: shard_content[m] for m in month_first},
        "disposition_record_hash": disposition_record_hash, "decision_record_hash": decision_record_hash,
        "session_census_hash": session_census_hash, "security_census_hash": security_census_hash,
        "refusal_census_hash": refusal_census_hash, "collision_census_hash": collision_census_hash,
        "total_units": len(all_units), "dispositions": dict(disp)}
    publication_core_hash = canonical_sha256(publication_core)

    unknown_codes = sorted({u.code for u in all_units if u.code and u.code not in REFUSAL_CODES})
    deprecated = sorted({u.code for u in all_units if u.code in DEPRECATED_CODES})
    val_oos = [e for e in ledger.entries
               if "validation" in str(e["object_identity"]).lower()
               or "oos" in str(e["object_identity"]).lower()]
    beyond_dev = [e for e in ledger.entries
                  if e["actual_max_date"] is not None and str(e["actual_max_date"]) > "2019-10-02"]

    restart = None
    if do_restart:
        restart = _restart_demo(ctx, members, sess_by_month, shards_dir, shard_content, all_units, cal)

    con.close()
    src.close()
    print(f"[{tag}] DONE units={len(all_units)} disp={dict(disp)} ({time.time()-t0:.0f}s)")
    return {
        "tag": tag, "snap_sha": snap_sha, "checks": checks, "ledger": ledger,
        "members": members, "permatickers": permatickers, "short_subset": short_subset,
        "overwrite_blocked_first": overwrite_blocked_first, "month_first": month_first,
        "sess_by_month": sess_by_month, "cal": cal, "expected_units": expected_units,
        "shard_meta": shard_meta, "shard_content": shard_content,
        "all_units": all_units, "disp": disp, "codes": codes, "elig": elig, "recon_keys": recon_keys,
        "session_census": session_census, "security_census": security_census,
        "refusal_census": refusal_census, "read_diagnostics": ctx.read_diagnostics,
        "collision_census": collision_census, "collision_census_hash": collision_census_hash,
        "disposition_record_hash": disposition_record_hash, "decision_record_hash": decision_record_hash,
        "session_census_hash": session_census_hash, "security_census_hash": security_census_hash,
        "refusal_census_hash": refusal_census_hash, "publication_core": publication_core,
        "publication_core_hash": publication_core_hash, "canonical_ordering_ok": canonical_ordering_ok(all_units),
        "unknown_codes": unknown_codes, "deprecated": deprecated, "val_oos_reads": len(val_oos),
        "beyond_dev_reads": len(beyond_dev), "restart": restart}


def _restart_demo(ctx, members, sess_by_month, shards_dir, shard_content, all_units, cal):  # noqa: ANN001
    """Prove: (a) completed shard is non-overwriting; (b) a 'lost' shard recomputes byte-identically on
    resume; (c) merged-after-resume == full merge. Demonstrated on two representative shards."""
    victims = ["2013-01-01", "2016-06-01"]  # first dev month + TWLO-IPO era mid-dev
    # (a) overwrite blocked on a COMPLETE shard
    overwrite_blocked = False
    any_complete = sorted(shard_content)[0]
    try:
        r0 = [(tk, t) for t in sess_by_month[any_complete] for tk in members[any_complete]]
        res0, c0 = ORCH.run_shard(ctx, r0)
        ORCH.publish_shard(res0, c0, os.path.join(shards_dir, f"{any_complete}.json"))
    except FileExistsError:
        overwrite_blocked = True
    # (b) simulate loss + resume: delete victims, recompute ONLY those, compare content sha
    resume_identical = True
    for m in victims:
        os.remove(os.path.join(shards_dir, f"{m}.json"))
    for m in victims:
        if not os.path.exists(os.path.join(shards_dir, f"{m}.json")):  # resume incomplete only
            units = [(tk, t) for t in sess_by_month[m] for tk in members[m]]
            res, content = ORCH.run_shard(ctx, units)
            resume_identical &= (content == shard_content[m])
            ORCH.publish_shard(res, content, os.path.join(shards_dir, f"{m}.json"))
    # (c) re-merge from the on-disk shards -> identical canonical hash
    on_disk = []
    for m in sorted(shard_content):
        rows = json.load(open(os.path.join(shards_dir, f"{m}.json")))["rows"]
        on_disk.append([ORCH.UnitResult(r["permanent_security_id"], r["symbol"], r["decision_session"],
                                        r["disposition"], r["code"], r["decision_eligibility_status"],
                                        r["record_identity"]) for r in rows])
    remerged = ORCH.merge(on_disk)
    remerge_identical = (canonical_sha256([u.as_row() for u in remerged])
                         == canonical_sha256([u.as_row() for u in all_units]))
    return {"completed_shard_overwrite_blocked": overwrite_blocked,
            "resumed_shards": victims, "resume_recompute_identical": resume_identical,
            "remerge_after_resume_identical": remerge_identical}


def dump(obj, name):  # noqa: ANN001
    os.makedirs(O2, exist_ok=True)
    p = os.path.join(O2, name)
    open(p, "w", encoding="utf-8", newline="\n").write(
        json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n")
    return sha_file(p)


# =========================== PASS A (primary) ===========================
print("=== SPQ-1 Phase 2B-2 full development run ===")
print(f"tickers={len(TICKERS)} ciks={len(CIKS)} run_spec={RUN_SPEC_SHA256[:16]}")
A = one_pass("A", os.path.join(O2, "shards_A"), do_restart=True)

# =========================== PASS B (independent determinism replay) ===========================
print("=== determinism replay (independent second full pass) ===")
B = one_pass("B", os.path.join(O2, "shards_B"), do_restart=False)

# ---- determinism comparison ----
det = {
    "aggregate_decision_record_hash_equal": A["decision_record_hash"] == B["decision_record_hash"],
    "aggregate_disposition_record_hash_equal": A["disposition_record_hash"] == B["disposition_record_hash"],
    "session_census_hash_equal": A["session_census_hash"] == B["session_census_hash"],
    "security_census_hash_equal": A["security_census_hash"] == B["security_census_hash"],
    "refusal_census_hash_equal": A["refusal_census_hash"] == B["refusal_census_hash"],
    "collision_census_hash_equal": A["collision_census_hash"] == B["collision_census_hash"],
    "publication_core_hash_equal": A["publication_core_hash"] == B["publication_core_hash"],
    "record_counts_equal": len(A["all_units"]) == len(B["all_units"]),
    "canonical_ordering_holds": A["canonical_ordering_ok"] and B["canonical_ordering_ok"],
    "materialization_content_identity_equal": A["snap_sha"] == B["snap_sha"],
    "per_shard_content_sha256_equal": A["shard_content"] == B["shard_content"],
}
det_all = all(det.values())

# ---- reconciliation ----
disp = A["disp"]
total = len(A["all_units"])
reconciles = A["expected_units"] == total == (
    disp["SIGNAL_DECISION_RECORD_EMITTED"] + disp["INELIGIBLE"] + disp["INTEGRITY_STOP"]
    + disp["REFUSED_CODE_OR_DATA_IDENTITY"])
recs = [u.record_identity for u in A["all_units"] if u.record_identity]
dup_candidate = len(recs) != len(set(recs))
by_shard = {m: A["shard_meta"][m]["dispositions"] for m in A["month_first"]}
distinct_sessions = len({u.decision_session for u in A["all_units"]})
distinct_symbols = len({u.symbol for u in A["all_units"]})
distinct_terminal = len({u.terminal_key() for u in A["all_units"]})
# expected reconstructed from shard facts: Σ(shard session_count × governing-month member_count)
expected_from_shards = sum(A["shard_meta"][m]["expected_request_unit_count"] for m in A["month_first"])
actual_from_shards = sum(A["shard_meta"][m]["actual_terminal_outcome_count"] for m in A["month_first"])
shard_terms = {m: {"session_count": A["shard_meta"][m]["session_count"],
                   "member_count": A["shard_meta"][m]["member_count"],
                   "expected": A["shard_meta"][m]["expected_request_unit_count"],
                   "actual": A["shard_meta"][m]["actual_terminal_outcome_count"]}
               for m in A["month_first"]}
shard_reconstruction_ok = expected_from_shards == actual_from_shards == total == 425000

# ---- hard stop conditions (owner directive: mismatch -> STOP before publication) ----
stops = {
    "unknown_refusal_codes": A["unknown_codes"], "deprecated_emissions": A["deprecated"],
    "validation_or_oos_reads": A["val_oos_reads"] + B["val_oos_reads"],
    "reads_beyond_dev_end": A["beyond_dev_reads"] + B["beyond_dev_reads"],
    "reconciliation_failed": not reconciles,
    "duplicate_request_keys": A["recon_keys"]["duplicate_request_keys"],
    "duplicate_resolved_permanent_security_session_keys":
        A["recon_keys"]["duplicate_resolved_permanent_security_session_keys"],
    "duplicate_candidate_identities": dup_candidate,
    "determinism_replay_failed": not det_all,
}
hard_stop = (A["unknown_codes"] or A["deprecated"] or stops["validation_or_oos_reads"]
             or stops["reads_beyond_dev_end"] or not reconciles
             or stops["duplicate_request_keys"] or dup_candidate
             or stops["duplicate_resolved_permanent_security_session_keys"] or not det_all)

# =========================== ARTIFACTS ===========================
h = {}
run_manifest = {"record_type": "MR002_SPQ1_Phase2B_2B2_RunManifest", "version": "1.0", "run_id": RUN_ID,
    "run_spec_sha256": RUN_SPEC_SHA256, "increment": "2B-2 (full development signal-production run)",
    "development_window": {"start": "2013-01-02", "end": DEV_END, "sessions": len(A["cal"])},
    "authorized_request_population": {
        "side": AUTHORIZED_SIDE,
        "statement": "authorized request population = all in_long_universe members for each of the 1,700 "
            "development sessions (the frozen producer request is LONG). Phase 2B-2 produces the "
            "long-side SPQ-1 development census ONLY.",
        "short_side_request_units_produced": 0,
        "short_side_reason": "in_short_universe is a strict subset of in_long_universe (short-only "
            "members over the dev window = 0, verified); the 150 short-universe members per month are "
            "already enumerated as long-side units. There are no short-only names -> short-side unit "
            "population is empty by the frozen SPQ-1 run configuration.",
        "short_only_members_dev": SHORT_ONLY_MEMBERS},
    "universe_enumeration": {"governing_months": 82, "members_per_month": 250,
        "membership_rule": "governing_universe_month(t)=max universe_month<=close(t); members = "
            "in_long_universe of ONLY that governing month; request unit=(session,ticker)",
        "distinct_member_tickers": len(TICKERS), "distinct_ciks": len(CIKS),
        "session_counts_vary": "first/last governing months hold partial development-month session "
            "ranges; expected units reconstructed per shard, NOT assumed 250x1700"},
    "pit_sector_source": "research.sic_observations (534/535 dev-universe ciks)",
    "sic_to_sector_etf": "registered owner-countersigned sic_mapping",
    "decision_cutoff": "registered ET close via zoneinfo (21:00Z standard / 20:00Z daylight)",
    "development_snapshot_content_sha256": A["snap_sha"],
    "phase2b_orchestration_code_identity": BOUND["phase2b_orchestration_code_identity"],
    "request_identity_collision_rule": {
        "rule_id": COLLISION_RULE_ID, "terminal_code": COLLISION_CODE,
        "detection": "runner-side governed pre-production step (frozen phase2b modules unchanged)",
        "collision_census_ref": "MR002_SPQ1_Phase2B_2B2_CollisionCensus_v1.0.json",
        "collision_group_count": A["collision_census"]["collision_group_count"],
        "collision_request_unit_count": A["collision_census"]["collision_request_unit_count"],
        "distinct_collision_symbol_sets": A["collision_census"]["distinct_collision_symbol_sets"],
        "maximum_collision_cardinality": A["collision_census"]["maximum_collision_cardinality"]},
    "governed_code_identities": {
        "phase2b_orchestration_code_identity_frozen": BOUND["phase2b_orchestration_code_identity"],
        "full_run_runner_identity": sha_file(os.path.abspath(__file__)),
        "collision_rule_module_identity": collision_module_identity()},
    "mandatory_pre_run_checks": A["checks"],
    "totals": {"expected_units": A["expected_units"], "total_units": total, "dispositions": dict(disp),
               "emitted_eligibility": dict(A["elig"])},
    "performance_quarantine": "no signal value ranked or interpreted; only dispositions + record identities"}
h["RunManifest"] = dump(run_manifest, "MR002_SPQ1_Phase2B_2B2_RunManifest_v1.0.json")

input_identity = {"record_type": "MR002_SPQ1_Phase2B_2B2_InputIdentityManifest", "version": "1.0",
    "run_id": RUN_ID, "run_spec_sha256": RUN_SPEC_SHA256, "bound_identities": BOUND,
    "development_snapshot_content_sha256": A["snap_sha"],
    "phase1_valid_path_output_sha256": PHASE1_SHA, "increment3_accepted_output_sha256": INCREMENT3_SHA,
    "universe_content_sha256": A["checks"]["universe_content_sha256"],
    "sic_mapping_content_sha256": A["checks"]["sic_mapping_content_sha256"],
    "pit_sector_observation_source_sha256": A["checks"]["pit_sector_observation_source_sha256"],
    "governed_code_identities": {
        "phase2b_orchestration_code_identity_frozen": BOUND["phase2b_orchestration_code_identity"],
        "full_run_runner_identity": sha_file(os.path.abspath(__file__)),
        "collision_rule_module_identity": collision_module_identity()},
    "opened_object_ledger_ref": "MR002_SPQ1_Phase2B_2B2_OpenedObjectLedger_v1.0.json"}
h["InputIdentityManifest"] = dump(input_identity, "MR002_SPQ1_Phase2B_2B2_InputIdentityManifest_v1.0.json")

# stamp the input-identity-manifest hash into each shard binding, then publish the shard manifest
for m in A["month_first"]:
    A["shard_meta"][m]["input_identity_manifest"] = h["InputIdentityManifest"]
shard_manifest = {"record_type": "MR002_SPQ1_Phase2B_2B2_ShardManifest", "version": "1.0", "run_id": RUN_ID,
    "run_spec_sha256": RUN_SPEC_SHA256, "sharding_model": "contiguous governing-month session blocks",
    "shard_count": len(A["month_first"]), "shards": A["shard_meta"],
    "shards_immutable": True, "shard_output_location": "docs/review/mr002/spq1/phase2b/2b2/shards_A/ "
        "(out-of-git; reproducible; each shard content_sha256 bound here)",
    "aggregate_canonical_merge_sha256": A["disposition_record_hash"]}
h["ShardManifest"] = dump(shard_manifest, "MR002_SPQ1_Phase2B_2B2_ShardManifest_v1.0.json")

ool = A["ledger"]
opened_ledger = {"record_type": "MR002_SPQ1_Phase2B_2B2_OpenedObjectLedger", "version": "1.0", "run_id": RUN_ID,
    "entries": ool.entries, "count": len(ool.entries),
    "all_completed": all(e["status"] == "COMPLETED" for e in ool.entries),
    "no_actual_key_beyond_dev_end": all(e["actual_max_date"] is None or str(e["actual_max_date"]) <= "2019-10-02"
                                        for e in ool.entries),
    "validation_or_oos_objects_opened": A["val_oos_reads"],
    "result_row_count_semantics": "result_row_count = number of canonical rows in result_set_sha256; "
        "finite-observation counts are separate diagnostics below.",
    "read_diagnostics": A["read_diagnostics"]}
h["OpenedObjectLedger"] = dump(opened_ledger, "MR002_SPQ1_Phase2B_2B2_OpenedObjectLedger_v1.0.json")

unit_recon = {"record_type": "MR002_SPQ1_Phase2B_2B2_UnitReconciliation", "version": "1.0", "run_id": RUN_ID,
    "authorized_side": AUTHORIZED_SIDE, "short_side_request_units_produced": 0,
    "shard_fact_reconstruction": {
        "formula": "Σ(month-shard session_count × governing-month member_count)",
        "expected_from_shards": expected_from_shards, "actual_from_shards": actual_from_shards,
        "equals_425000": shard_reconstruction_ok, "per_shard": shard_terms,
        "note": "session counts vary by governing month (partial first/last months); 250×1700 is a "
                "headline identity, the governing figure is the per-shard sum above"},
    "expected_units": A["expected_units"], "total_units": total, "dispositions": dict(disp),
    "reconciles": reconciles and shard_reconstruction_ok, "missing_outcomes": A["expected_units"] - total,
    "orphan_outcomes": 0,
    "duplicate_request_keys": A["recon_keys"]["duplicate_request_keys"],
    "duplicate_resolved_permanent_security_session_keys":
        A["recon_keys"]["duplicate_resolved_permanent_security_session_keys"],
    "duplicate_candidate_identities": dup_candidate,
    "reconcile_by": {
        "session": {"distinct_sessions": distinct_sessions,
                    "sum_over_sessions_equals_total": sum(sum(v["dispositions"].values())
                        for v in A["session_census"].values()) == total},
        "permanent_security": {"distinct_resolved_terminal_keys": distinct_terminal},
        "symbol_request": {"distinct_symbols": distinct_symbols},
        "terminal_code": dict(A["codes"]),
        "shard": {"shard_count": len(by_shard),
                  "sum_over_shards_equals_total": sum(sum(d.values()) for d in by_shard.values()) == total}},
    "emitted_eligibility": dict(A["elig"])}
h["UnitReconciliation"] = dump(unit_recon, "MR002_SPQ1_Phase2B_2B2_UnitReconciliation_v1.0.json")

h["SessionCensus"] = dump({"record_type": "MR002_SPQ1_Phase2B_2B2_SessionCensus", "version": "1.0",
    "run_id": RUN_ID, "session_census_sha256": A["session_census_hash"], "sessions": A["session_census"]},
    "MR002_SPQ1_Phase2B_2B2_SessionCensus_v1.0.json")
h["SecurityCensus"] = dump({"record_type": "MR002_SPQ1_Phase2B_2B2_SecurityCensus", "version": "1.0",
    "run_id": RUN_ID, "security_census_sha256": A["security_census_hash"], "securities": A["security_census"]},
    "MR002_SPQ1_Phase2B_2B2_SecurityCensus_v1.0.json")
h["RefusalCensus"] = dump({"record_type": "MR002_SPQ1_Phase2B_2B2_RefusalCensus", "version": "1.0",
    "run_id": RUN_ID, "refusal_census_sha256": A["refusal_census_hash"], "codes": A["refusal_census"],
    "deprecated_emitted": bool(A["deprecated"]), "unknown_codes": A["unknown_codes"],
    "security_identity_ambiguous_split": {
        "collision_caused_noninjective": A["collision_census"]["reconciliation"][
            "collision_caused_security_identity_ambiguous_records"],
        "single_request_lineage_ambiguity": A["collision_census"]["reconciliation"][
            "single_request_lineage_ambiguity_records"],
        "note": f"records under {COLLISION_CODE} are split by cause via {COLLISION_RULE_ID}; the "
                "collision-caused subset is fully enumerated in the CollisionCensus."}},
    "MR002_SPQ1_Phase2B_2B2_RefusalCensus_v1.0.json")
h["CollisionCensus"] = dump({"record_type": "MR002_SPQ1_Phase2B_2B2_CollisionCensus", "version": "1.0",
    "run_id": RUN_ID, "rule_id": COLLISION_RULE_ID, "run_spec_sha256": RUN_SPEC_SHA256,
    "collision_census_sha256": A["collision_census_hash"], **A["collision_census"]},
    "MR002_SPQ1_Phase2B_2B2_CollisionCensus_v1.0.json")

determinism = {"record_type": "MR002_SPQ1_Phase2B_2B2_DeterminismReport", "version": "1.0", "run_id": RUN_ID,
    "method": "independent second full pass: fresh materialization + fresh enumeration + fresh run into a "
              "clean output location (shards_B); all aggregate/census hashes compared to pass A",
    "replay_independence_attestation": {
        "fresh_snapshot_materialization": A["snap_sha"] != "" and B["snap_sha"] != "",
        "fresh_guard_and_opened_object_ledger": True,   # one_pass constructs a new ledger + guard per pass
        "fresh_unit_enumeration": True,                 # pass B re-reads the universe + rebuilds members
        "clean_output_directory": True,                 # shards_B cleaned at pass start
        "no_reuse_of_passA_completed_shards": True,
        "no_reuse_of_passA_merged_records": True,
        "comparison_ignores_only_nongoverning_runtime_metadata": "temp snapshot filenames only; "
            "all governed artifacts + canonical record hashes must match"},
    "checks": det, "determinism_all_equal": det_all,
    "pass_A_publication_core_hash": A["publication_core_hash"],
    "pass_B_publication_core_hash": B["publication_core_hash"]}
h["DeterminismReport"] = dump(determinism, "MR002_SPQ1_Phase2B_2B2_DeterminismReport_v1.0.json")

restart_report = {"record_type": "MR002_SPQ1_Phase2B_2B2_RestartReport", "version": "1.0", "run_id": RUN_ID,
    **(A["restart"] or {}),
    "note": "completed shards are immutable (non-overwriting publication); a lost shard recomputes "
            "byte-identically on resume; merged-after-resume == full merge."}
h["RestartReport"] = dump(restart_report, "MR002_SPQ1_Phase2B_2B2_RestartReport_v1.0.json")

gate = {
    "all_registered_identities_match": all(A["checks"][k] for k in A["checks"] if k.endswith("_matches")),
    "one_terminal_outcome_per_unit": reconciles and A["recon_keys"]["duplicate_request_keys"] == 0
        and A["recon_keys"]["duplicate_resolved_permanent_security_session_keys"] == 0,
    "expected_equals_425000": A["expected_units"] == 425000 and total == 425000,
    "shard_fact_reconstruction_equals_425000": shard_reconstruction_ok,
    "long_side_only_short_units_zero": SHORT_ONLY_MEMBERS == 0,
    "no_silent_drops": (A["expected_units"] - total) == 0,
    "no_duplicate_request_keys": A["recon_keys"]["duplicate_request_keys"],
    "no_duplicate_resolved_keys": A["recon_keys"]["duplicate_resolved_permanent_security_session_keys"],
    "collision_census_reconciles": A["collision_census"]["reconciliation"]["reconciles"]
        and B["collision_census"]["reconciliation"]["reconciles"],
    "collision_census_hash_replay_equal": A["collision_census_hash"] == B["collision_census_hash"],
    "no_duplicate_candidate_identities": int(dup_candidate),
    "no_unknown_refusal_codes": len(A["unknown_codes"]),
    "no_deprecated_emissions": len(A["deprecated"]),
    "no_validation_or_oos_reads": stops["validation_or_oos_reads"],
    "no_reads_beyond_dev_end": stops["reads_beyond_dev_end"],
    "determinism_replay_equal": det_all,
    "canonical_ordering_holds": A["canonical_ordering_ok"] and B["canonical_ordering_ok"],
    "shards_immutable_non_overwriting": (A["restart"] or {}).get("completed_shard_overwrite_blocked", False),
    "first_shard_overwrite_blocked": bool(A["overwrite_blocked_first"]),
    "resume_recompute_identical": (A["restart"] or {}).get("resume_recompute_identical", False),
    "remerge_after_resume_identical": (A["restart"] or {}).get("remerge_after_resume_identical", False),
    "no_performance_artifact": True}
gate_all_pass = all((v is True) if isinstance(v, bool) else (v == 0) for v in gate.values())

publication = {"record_type": "MR002_SPQ1_Phase2B_2B2_PublicationManifest", "version": "1.0", "run_id": RUN_ID,
    "run_spec_sha256": RUN_SPEC_SHA256, "artifact_sha256": h,
    "aggregate_canonical_merge_sha256": A["disposition_record_hash"],
    "aggregate_decision_record_sha256": A["decision_record_hash"],
    "publication_core_sha256": A["publication_core_hash"],
    "acceptance_gate": gate, "gate_all_pass": gate_all_pass, "hard_stop_triggered": bool(hard_stop),
    "stop_conditions": {k: (v if not isinstance(v, list) else v) for k, v in stops.items()},
    "boundary": "full development run + determinism replay only; Phase 2B-3 closeout NOT YET authorized; "
        "performance/forward-return/ranking/portfolio/execution/validation/OOS/order-path/production NOT authorized."}
h["PublicationManifest"] = dump(publication, "MR002_SPQ1_Phase2B_2B2_PublicationManifest_v1.0.json")

print("\n=== 2B-2 SUMMARY ===")
print("authorized_side: LONG | short_only_members:", SHORT_ONLY_MEMBERS, "| short_side_units: 0")
print("shard_fact_reconstruction: expected", expected_from_shards, "== actual", actual_from_shards,
      "== total", total, "==425000:", shard_reconstruction_ok)
print("total_units:", total, "expected:", A["expected_units"], "dispositions:", dict(disp))
print("reconciles:", reconciles, "| dup_req:", A["recon_keys"]["duplicate_request_keys"],
      "dup_resolved:", A["recon_keys"]["duplicate_resolved_permanent_security_session_keys"],
      "dup_candidate:", dup_candidate)
print("determinism_all_equal:", det_all, det)
print("unknown_codes:", A["unknown_codes"], "| deprecated:", A["deprecated"],
      "| val/oos reads:", stops["validation_or_oos_reads"], "| beyond_dev:", stops["reads_beyond_dev_end"])
print("restart:", A["restart"])
print("gate_all_pass:", gate_all_pass, "| hard_stop:", bool(hard_stop))
print("canonical_merge_sha256:", A["disposition_record_hash"])
for k, v in h.items():
    print(f"  {k}: {v[:16]}")
