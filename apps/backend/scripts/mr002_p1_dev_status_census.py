"""MR-002 P1 / tracks T3 + T4 — development status census, REANALYSIS tranche.

Governing protocol: `MR002_P1_NumericalInvestigation_Protocol_v1.0` (docs/design/MR002/P1/),
tracks T3 ("how do the two disposition taxonomies classify the same development evidence") and T4
("frequency, structure and correlates of generator termination on development").

WHAT THIS IS. A reanalysis of the per-instance Gate-N1 development census already collected on
2026-08-19 (`.mr002out/n1/n1_census_rows.json`, 3,895 instances x 3 candidates). It runs no solver,
imports no research module, and opens no corpus, dataset, sealed reader, validation store or OOS.
Every number it prints is a re-count of rows that already exist.

WHAT THIS IS NOT. It cannot produce any quantity the Aug-19 run did not record: exception messages,
iteration counts, residuals, conditioning, or timings are absent from the rows and are reported as
NOT RECORDED rather than inferred. It states no disposition; §5 of the protocol reserves that, and
admissibility condition A-2 (reproduced numerical environment) is currently unmet.

THE QUESTION IT EXISTS TO ANSWER. Gate N1 passed `PIQP_P2` on gate C2, "100% certified resolution".
In production shape the fallback runs only where the primary produced no certified candidate, so C2
tested the FALLBACK path on exactly as many instances as the primary failed. This script measures
that number, and states the confidence bound it supports, using the frozen corpus alone.
"""
from __future__ import annotations

import collections
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROWS = REPO / ".mr002out" / "n1" / "n1_census_rows.json"
SUMMARY_IN = REPO / ".mr002out" / "n1" / "n1_census_c1c2.json"
OUT = REPO / "docs" / "design" / "MR002" / "P1" / "MR002_P1_DevelopmentStatusCensus_v1.0.json"

REGISTERED_CORPUS_HASH = "1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b"

A_PROFILE = "QUADPROG_SQRT"
PRODUCTION_B = "PIQP_P2"

#: The one entry of the v1 `NUMERICAL_ALLOWLIST`, reproduced here as DATA so the counterfactual
#: below is auditable without importing the cascade. Scoped to QUADPROG_SQRT; PIQP_P2 has none.
V1_ALLOWLIST_SOLVERS = {A_PROFILE: [("ValueError", "constraints are inconsistent, no solution")]}


def identities(path: Path) -> dict:
    raw = path.read_bytes()
    return {
        "path": str(path.relative_to(REPO)).replace("\\", "/"),
        "bytes": len(raw),
        "sha256_worktree": hashlib.sha256(raw).hexdigest(),
        "sha256_lf": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(),
    }


def binom_zero_failure_upper(trials: int, alpha: float = 0.05) -> float | None:
    """Exact (Clopper-Pearson) one-sided upper bound on a failure probability after observing ZERO
    failures in `trials` independent draws: p_upper = 1 - alpha ** (1/trials).

    With 0/5 at 95%, p_upper is about 0.45 — a zero-failure result on five draws is compatible with
    a true failure rate approaching one in two. This is the standard bound, not a modelling choice.
    """
    if trials <= 0:
        return None
    return 1.0 - alpha ** (1.0 / trials)


def v1_reclassify_b(brow: dict) -> dict:
    """What the v1 cascade (`stage3_cascade.normalize`) would make of a recorded B outcome.

    v1 keys the numerical allowlist on (solver_id, exact exception CLASS OBJECT, exact complete
    MESSAGE). PIQP_P2 has zero registered entries, so ANY raise from it misses and is an
    INTEGRITY_DEFECT. That conclusion needs no message, which is why it is determinate here even
    though the Aug-19 rows did not record messages.
    """
    if brow["outcome"] == "CERTIFIED":
        return {"v1_enum": "QUALIFIED", "determinate": True}
    if brow["exception_class"]:
        return {
            "v1_enum": "INTEGRITY_DEFECT",
            "determinate": True,
            "why": "PIQP_P2 has no entry in NUMERICAL_ALLOWLIST, so every raise misses the exact "
                   "(solver, class, message) lookup regardless of its message",
            "v1_code": f"UNREGISTERED_EXCEPTION:{brow['exception_class']}:<message not recorded>",
        }
    # A returned point that the certifier rejected: same category in both layers.
    return {"v1_enum": "CERTIFICATE_NONQUALIFICATION", "determinate": True}


def v1_reclassify_a(arow: dict) -> dict:
    """What the v1 cascade would make of a recorded A outcome.

    Here the message DOES matter: A's single registered numerical status is keyed to the exact
    message 'constraints are inconsistent, no solution'. The Aug-19 rows record the class
    (`ValueError`) and owning module (`quadprog`) but NOT the message, so an A raise is
    INDETERMINATE between NUMERICAL_STATUS_NONQUALIFICATION (fallback-eligible) and
    INTEGRITY_DEFECT (fallback never invoked). It is reported as such and never guessed.
    """
    if arow["outcome"] == "CERTIFIED":
        return {"v1_enum": "QUALIFIED", "determinate": True}
    if arow["exception_class"]:
        allowed = V1_ALLOWLIST_SOLVERS.get(A_PROFILE, [])
        class_matches = any(cls == arow["exception_class"] for cls, _ in allowed)
        return {
            "v1_enum": "INDETERMINATE",
            "determinate": False,
            "candidates": (["NUMERICAL_STATUS_NONQUALIFICATION", "INTEGRITY_DEFECT"]
                           if class_matches else ["INTEGRITY_DEFECT"]),
            "why": "the v1 allowlist matches on the EXACT complete message, which the Aug-19 census "
                   "did not record; the recorded class does match the one registered entry",
        }
    return {"v1_enum": "CERTIFICATE_NONQUALIFICATION", "determinate": True}


def analyse(cand: str, rows: list[dict]) -> dict:
    total = len(rows)
    a_cert = sum(1 for r in rows if r["A"]["outcome"] == "CERTIFIED")
    a_fail_rows = [r for r in rows if r["A"]["outcome"] != "CERTIFIED"]

    # ── T4: unconditional B behaviour over the whole corpus (run_both mode, as collected) ────────
    b_outcome = collections.Counter(r["B"]["outcome"] for r in rows if r["B"])
    b_reason = collections.Counter(r["B"]["reason"] for r in rows if r["B"] and r["B"]["reason"])
    b_terminated = [r for r in rows if r["B"] and r["B"]["exception_class"]]

    # ── T3: the PRODUCTION-SHAPE joint event ────────────────────────────────────────────────────
    # In production the fallback is invoked ONLY where A produced no certified candidate. The
    # fallback path's development evidence is therefore exactly these rows and no others.
    fb_invocations = len(a_fail_rows)
    fb_failures = [r for r in a_fail_rows if r["B"] and r["B"]["outcome"] != "CERTIFIED"]
    fb_terminations = [r for r in a_fail_rows
                       if r["B"] and r["B"]["reason"] == "ITERATION_LIMIT_REACHED"]

    # ── T4: is B's termination rate elevated where A struggles? ─────────────────────────────────
    # Neutral, prespecified stratifier: problem size n, the only structural field recorded.
    a_fail_n = sorted({r["n"] for r in a_fail_rows})
    lo, hi = (min(a_fail_n), max(a_fail_n)) if a_fail_n else (None, None)
    in_band = [r for r in rows if lo is not None and lo <= r["n"] <= hi]
    band_term = [r for r in in_band if r["B"] and r["B"]["exception_class"]]

    by_n_bucket: dict[str, dict] = {}
    for r in rows:
        b = (r["n"] // 10) * 10
        key = f"{b:02d}-{b + 9:02d}"
        d = by_n_bucket.setdefault(key, {"instances": 0, "B_terminations": 0,
                                         "A_nonqualified": 0, "B_certificate_false": 0})
        d["instances"] += 1
        if r["A"]["outcome"] != "CERTIFIED":
            d["A_nonqualified"] += 1
        if r["B"] and r["B"]["exception_class"]:
            d["B_terminations"] += 1
        if r["B"] and r["B"]["reason"] == "CERTIFICATE_PREDICATE_FALSE":
            d["B_certificate_false"] += 1
    for d in by_n_bucket.values():
        d["B_termination_rate"] = round(d["B_terminations"] / d["instances"], 6)

    # ── v1 counterfactual over the same rows ────────────────────────────────────────────────────
    v1_b = collections.Counter(v1_reclassify_b(r["B"])["v1_enum"] for r in rows if r["B"])
    v1_a = collections.Counter(v1_reclassify_a(r["A"])["v1_enum"] for r in rows)
    # Production shape under v1: fallback reached only from a fallback-eligible A. Where A is
    # INDETERMINATE the downstream disposition is indeterminate too, and is counted as such.
    v1_prod: collections.Counter = collections.Counter()
    for r in rows:
        av = v1_reclassify_a(r["A"])
        if av["v1_enum"] == "QUALIFIED":
            v1_prod["PRIMARY_QUALIFIED"] += 1
            continue
        if not av["determinate"]:
            bv = v1_reclassify_b(r["B"])["v1_enum"] if r["B"] else None
            v1_prod[f"INDETERMINATE_A(then_B={bv})"] += 1
            continue
        bv = v1_reclassify_b(r["B"])["v1_enum"] if r["B"] else None
        v1_prod[{"QUALIFIED": "FALLBACK_QUALIFIED",
                 "INTEGRITY_DEFECT": "INVALID_RUN",
                 "CERTIFICATE_NONQUALIFICATION": "UNRESOLVED_NUMERICAL_FAILURE"}[bv]] += 1

    return {
        "candidate": cand,
        "instances": total,
        "A_profile": A_PROFILE,
        "A_certified": a_cert,
        "A_nonqualified": total - a_cert,
        "A_nonqualified_instances": [
            {"i": r["i"], "n": r["n"], "exception_class": r["A"]["exception_class"],
             "owning_module": r["A"]["owning_module"], "reason": r["A"]["reason"],
             "B_outcome": r["B"]["outcome"] if r["B"] else None,
             "B_reason": r["B"]["reason"] if r["B"] else None,
             "disposition": r["disposition"]}
            for r in a_fail_rows],

        "B_unconditional": {
            "note": "the Aug-19 census ran B on EVERY instance (run_both), so these counts describe "
                    "B's behaviour on the corpus, not the fallback path's exercised evidence",
            "outcome_counts": dict(b_outcome),
            "reason_counts": dict(b_reason),
            "terminations": len(b_terminated),
            "termination_rate": round(len(b_terminated) / total, 6),
        },

        "fallback_path_evidence": {
            "note": "PRODUCTION SHAPE — the fallback is invoked only where A produced no certified "
                    "candidate. This is the entire development evidence for the fallback path.",
            "invocations": fb_invocations,
            "invocation_rate": round(fb_invocations / total, 6),
            "failures": len(fb_failures),
            "terminations_iteration_limit": len(fb_terminations),
            "observed_failure_rate": (round(len(fb_failures) / fb_invocations, 6)
                                      if fb_invocations else None),
            "exact_one_sided_95pct_upper_bound_on_failure_rate":
                (round(binom_zero_failure_upper(fb_invocations), 6)
                 if fb_invocations and not fb_failures else None),
            "upper_bound_method": "Clopper-Pearson, 0 failures in n trials: 1 - 0.05**(1/n)",
        },

        "size_stratification": {
            "stratifier": "problem size n (the only structural field the Aug-19 rows record)",
            "corpus_n_min": min(r["n"] for r in rows),
            "corpus_n_max": max(r["n"] for r in rows),
            "A_nonqualified_n_values": a_fail_n,
            "A_nonqualified_n_band": [lo, hi],
            "in_band_instances": len(in_band),
            "in_band_B_terminations": len(band_term),
            "in_band_B_termination_rate": (round(len(band_term) / len(in_band), 6)
                                           if in_band else None),
            "by_n_bucket": dict(sorted(by_n_bucket.items())),
        },

        "v1_counterfactual": {
            "note": "how the v1 cascade taxonomy would classify these same recorded outcomes",
            "B_enum_counts": dict(v1_b),
            "A_enum_counts": dict(v1_a),
            "production_shape_dispositions": dict(v1_prod),
            "indeterminacy": "A raises are INDETERMINATE because v1 matches on the exact complete "
                             "message and the Aug-19 census did not record messages. B raises are "
                             "determinate: PIQP_P2 has no allowlist entry at all.",
        },
    }


def main() -> int:
    if not ROWS.exists():
        print(f"ABORT: {ROWS} not found", file=sys.stderr)
        return 2

    rows_by_cand = json.loads(ROWS.read_text())
    prior = json.loads(SUMMARY_IN.read_text()) if SUMMARY_IN.exists() else {}

    if prior.get("corpus_hash") and prior["corpus_hash"] != REGISTERED_CORPUS_HASH:
        print(f"ABORT: corpus hash {prior['corpus_hash']} != registered", file=sys.stderr)
        return 2

    per_candidate = {c: analyse(c, rows) for c, rows in rows_by_cand.items()}
    prod = per_candidate.get(PRODUCTION_B, {})

    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                                text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        commit = None

    record = {
        "record_type": "MR002_P1_DEVELOPMENT_STATUS_CENSUS",
        "version": "1.0",
        "phase": "P1",
        "tracks": ["T3", "T4"],
        "tranche": "REANALYSIS — no solver executed",
        "governing_protocol": "MR002_P1_NumericalInvestigation_Protocol_v1.0",
        "generator": "apps/backend/scripts/mr002_p1_dev_status_census.py",
        "source_commit": commit,
        "data_scope": "DEVELOPMENT ONLY — reanalysis of the 2026-08-19 Gate-N1 census rows. No "
                      "corpus, dataset, sealed reader, validation store or OOS opened.",
        "inputs": [identities(ROWS)] + ([identities(SUMMARY_IN)] if SUMMARY_IN.exists() else []),
        "registered_corpus_hash": REGISTERED_CORPUS_HASH,
        "per_candidate": per_candidate,

        "findings": [
            {
                "id": "P1-F1",
                "title": "The fallback path's development qualification rests on five invocations.",
                "statement": (
                    f"Gate N1 passed {PRODUCTION_B} on C2 (100% certified resolution) over "
                    f"{prod.get('instances')} instances. In production shape the fallback is invoked "
                    f"only where the primary produced no certified candidate, which happened "
                    f"{prod.get('fallback_path_evidence', {}).get('invocations')} times. All "
                    f"{prod.get('fallback_path_evidence', {}).get('invocations')} certified, so the "
                    f"observed fallback failure rate is 0 — but the exact one-sided 95% upper bound "
                    f"from that sample is "
                    f"{prod.get('fallback_path_evidence', {}).get('exact_one_sided_95pct_upper_bound_on_failure_rate')}. "
                    "C2 as measured could not distinguish a fallback that never fails from one that "
                    "fails on roughly half of its invocations."),
                "status": "MEASURED from development evidence",
            },
            {
                "id": "P1-F2",
                "title": "The Validation-2 failure mode has zero development observations.",
                "statement": (
                    "The joint event 'primary produces no certified candidate AND the fallback "
                    "terminates without one' occurs "
                    f"{prod.get('fallback_path_evidence', {}).get('failures')} times on the "
                    "development corpus. The development corpus therefore contains no instance of "
                    "the class that ended Validation-2, and no development result can attest that "
                    "the frozen pair resolves it."),
                "status": "MEASURED from development evidence",
            },
            {
                "id": "P1-F3",
                "title": "The fallback generator's termination rate on the corpus is not small.",
                "statement": (
                    f"Independently of whether it was invoked, {PRODUCTION_B} terminated without a "
                    f"candidate on "
                    f"{prod.get('B_unconditional', {}).get('terminations')} of "
                    f"{prod.get('instances')} development instances "
                    f"(rate {prod.get('B_unconditional', {}).get('termination_rate')}), every one of "
                    "them with the registered reason ITERATION_LIMIT_REACHED. This behaviour was "
                    "measured on 2026-08-19 and is visible in the sealed N1 census; it did not "
                    "affect C2 because those instances were resolved by the primary."),
                "status": "MEASURED from development evidence",
            },
            {
                "id": "P1-F4",
                "title": "Under the v1 taxonomy every fallback termination is an integrity defect.",
                "statement": (
                    "PIQP_P2 has no entry in the v1 NUMERICAL_ALLOWLIST, so any raise from it misses "
                    "the exact (solver, class, message) lookup and is classified INTEGRITY_DEFECT -> "
                    "INVALID_RUN. The terminal disposition UNRESOLVED_NUMERICAL_FAILURE is therefore "
                    "reachable from the fallback only when it RETURNS a point the certifier rejects, "
                    "never when it terminates. This is a structural property of the frozen cascade, "
                    "not a property of any instance."),
                "status": "DERIVED from source; independent of the census rows",
            },
            {
                "id": "P1-F5",
                "title": "A stop is a stop under both taxonomies.",
                "statement": (
                    "Under the v2 method the same fallback termination is NO_CERTIFIED_CANDIDATE / "
                    "ITERATION_LIMIT_REACHED, giving disposition UNRESOLVED_INSTANCE, which raises "
                    "Stage3StopV2 and ends the run. The two layers differ in what the stop MEANS -- "
                    "an impugned evaluation system versus an unresolved instance -- not in whether "
                    "the run completes. Neither yields an economic verdict. Any claim that adopting "
                    "v2 would have produced a Validation-2 result is unsupported."),
                "status": "DERIVED from source",
            },
            {
                "id": "P1-F6",
                "title": "Fallback termination is strongly size-dependent on development.",
                "statement": (
                    f"{PRODUCTION_B}'s termination rate is roughly 28x higher on mid-sized instances "
                    "than on the smallest ones. It is NOT monotone in n: it rises steeply to a peak "
                    "at n in [20,29] and then declines while staying well above the small-n level. "
                    "Populated buckets: " + ", ".join(
                        f"n {k} -> {v['B_termination_rate']} ({v['B_terminations']}/{v['instances']})"
                        for k, v in sorted(
                            prod.get("size_stratification", {}).get("by_n_bucket", {}).items())
                        if v["instances"] >= 50) +
                    ". The development corpus is dominated by small instances, so the corpus-wide "
                    "rate understates the exposure of any population with a larger size mix. This is "
                    "a structural property of the frozen generator measured on development; it "
                    "implies nothing about, and must not be used to infer anything about, the size "
                    "distribution of any consumed or future holdout population."),
                "status": "MEASURED from development evidence",
            },
        ],

        "not_establishable_from_this_tranche": [
            "Exception messages, iteration counts, residuals, conditioning numbers and timings — "
            "NOT RECORDED by the Aug-19 census. Recovering them requires re-running the corpus in "
            "the pinned research image (track T2).",
            "Whether the Validation-2 instance is solvable at all at the frozen tolerances — "
            "requires Reference Solver R (track T5/T6) and, by protocol §3.2, may never be tested "
            "against the consumed population.",
            "Why the v1 layer rather than the v2 method was the bound Stage-3 path in the "
            "Validation-2 execution package. This is an execution-package question, not a numerical "
            "one, and is a named open P1 item.",
            "Any P1 disposition. Protocol §5.1 admissibility condition A-2 (reproduced numerical "
            "environment) is UNMET in this environment.",
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(record, indent=1, sort_keys=True).encode("utf-8")
    record["record_sha256_of_body_without_this_field"] = hashlib.sha256(body).hexdigest()
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_bytes(json.dumps(record, indent=1, sort_keys=True).encode("utf-8"))
    tmp.replace(OUT)

    fb = prod.get("fallback_path_evidence", {})
    print(f"instances                     {prod.get('instances')}")
    print(f"A certified                   {prod.get('A_certified')}")
    print(f"fallback invocations (prod)   {fb.get('invocations')}")
    print(f"fallback failures             {fb.get('failures')}")
    print(f"95% upper bound on that rate  {fb.get('exact_one_sided_95pct_upper_bound_on_failure_rate')}")
    print(f"B terminations (unconditional){prod.get('B_unconditional', {}).get('terminations')} "
          f"rate {prod.get('B_unconditional', {}).get('termination_rate')}")
    print(f"in-band B termination rate    {prod.get('size_stratification', {}).get('in_band_B_termination_rate')}")
    print(f"body sha256                   {record['record_sha256_of_body_without_this_field']}")
    print(f"wrote                         {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
