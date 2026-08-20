"""MR-002 Stage-3 v2 — Gate N3 PROSPECTIVE REGISTRATION record.

Freezes, BEFORE any N3 result exists (memo SA-4): the question, the frozen method, the domain, the
exact comparison surface, the pass rule, the mechanically derived reconciliation bound, the stop
conditions, and the firewalls.

Authority: the owner's Gate N3 grant of 2026-08-20, standing on
  MR002_N1_FinalVerdict_v1.0  identity 629eee0ee1c257a23312b539fbac8542b40cbf6f2cef296ba2c829fb6b29bd81
  MR002_N2_Verdict_v1.0       identity 27f98548067b3017870937c22196212e5bb1b11fdbd6a961a329f85f82aae471

This record AUTHORIZES NOTHING. It produces no result, scores no candidate, selects no solver, and
reads nothing outside the development domain.

WHY THIS RECORD EXISTS AT ALL, given that N1 already measured preservation. The N1 preservation run
(finding `preservation_governed_v1_replay`) reported byte identity for PIQP_P2 on this same window.
The owner ruled that this is PRIOR EVIDENCE and does not soften N3. Registering the rule before the
result is what separates a gate from a re-quotation of a number we already like. N3 also widens the
surface: N1 compared aggregate economic hashes, N3 compares SESSION-BY-SESSION and TRADE-BY-TRADE.

IDENTITIES. Every source file is bound by its GIT BLOB sha, never the Windows working tree, which
carries CRLF and fail-closes against an LF deploy.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
REV = "HEAD"
E = "docs/implementation/evidence/mr_002/"
M = "apps/backend/app/research/mr002/"
S = "apps/backend/scripts/"
PENDING: list[str] = []


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob_sha(path: str) -> str:
    out = subprocess.run(["git", "-C", REPO, "show", f"{REV}:{path}"], capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"not committed, cannot bind by Git blob: {path}")
    return hashlib.sha256(out.stdout).hexdigest()


def bound(path: str) -> dict:
    return {"path": path, "file_blob_sha256": blob_sha(path), "enforced": True}


def worktree_lf_sha(path: str) -> str:
    with open(os.path.join(REPO, path), "rb") as fh:
        return hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest()


def bind_or_pending(path: str, why: str) -> dict:
    out = subprocess.run(["git", "-C", REPO, "show", f"{REV}:{path}"], capture_output=True)
    if out.returncode == 0:
        return {"path": path, "file_blob_sha256": hashlib.sha256(out.stdout).hexdigest(),
                "enforced": True}
    PENDING.append(path)
    rec = {"path": path, "enforced": False, "pending_reason": why}
    if os.path.exists(os.path.join(REPO, path)):
        rec["worktree_lf_sha256"] = worktree_lf_sha(path)
    else:
        # The correct state at registration time: the rule is frozen BEFORE the code exists.
        # Asserting any hash here would assert an identity for a file that has not been written.
        rec["status"] = "NOT YET WRITTEN AT REGISTRATION TIME"
    return rec


def head_is_pushed() -> tuple[bool, str, str]:
    def rev(ref: str) -> str:
        o = subprocess.run(["git", "-C", REPO, "rev-parse", ref], capture_output=True, text=True)
        return o.stdout.strip() if o.returncode == 0 else ""
    head = rev("HEAD")
    br = subprocess.run(["git", "-C", REPO, "rev-parse", "--abbrev-ref", "HEAD"],
                        capture_output=True, text=True).stdout.strip()
    return (bool(head) and head == rev(f"origin/{br}")), head, rev(f"origin/{br}")


_pushed, _head, _remote = head_is_pushed()

REG: dict = {
    "record_type": "MR002_N3_PROSPECTIVE_REGISTRATION",
    "record_status": "DRAFT",
    "version": "1.0",
    "program": "MR-002 Sector-Neutral Residual Reversion — Stage-3 numerical method v2",
    "gate": "N3 — FULL DEVELOPMENT BEHAVIOURAL / ECONOMIC EQUIVALENCE",
    "date": "2026-08-20",

    "authorizes": "nothing — this record freezes the N3 rule; it grants no execution beyond N3 "
                  "itself and no economic conclusion of any kind",

    "question": (
        "Does the N1/N2-qualified Stage-3 v2 method preserve the frozen MR-002 development "
        "economics end-to-end when substituted for Stage-3 v1? This is the ONLY question N3 "
        "answers. N3 does not look for a better strategy and does not re-select the solver."
    ),

    "authority_chain": {
        "owner_grant": {
            "date": "2026-08-20",
            "instrument": "owner message granting Gate N3 after accepting Gate N2",
            "quoted_purpose": "The purpose is not to find a better strategy and not to re-select "
                              "the solver.",
        },
        "N1": {"record": "MR002_N1_FinalVerdict_v1.0",
               "identity_sha256":
                   "629eee0ee1c257a23312b539fbac8542b40cbf6f2cef296ba2c829fb6b29bd81",
               "disposition": "N1_ADVANCE"},
        "N2": {"record": "MR002_N2_Verdict_v1.0",
               "identity_sha256":
                   "27f98548067b3017870937c22196212e5bb1b11fdbd6a961a329f85f82aae471",
               "disposition": "N2 CLOSED — PASS"},
    },

    # ── the method is FROZEN. N3 selects nothing. ───────────────────────────────────────────────
    "frozen_method": {
        "solver_A": "QUADPROG_SQRT",
        "solver_B": "PIQP_P2",
        "selection_occurs_in_N3": False,
        "candidate_set_evaluated_in_N3": [],
        "why_no_candidate_set": (
            "N1 selected Solver B under a sealed rule on the frozen bakeoff corpus and N2 "
            "confirmed the pair under stress. N3 receives that pair as an input. Evaluating "
            "PIQP_P1 here — as the N1 preservation run legitimately did while selection was still "
            "open — would re-open a closed selection on replay economics, which is selection on "
            "returns and is forbidden outright."
        ),
        "max_iter": 1000,
        "max_iter_status": "FROZEN — unchanged from N1/N2",
        "unchanged_from_N1_N2": [
            "profiles and limits", "certificate predicate", "Stage 1", "Stage 2",
            "constraints and R/Q retention bands", "A/B/C configurations", "exits", "costs",
            "borrow", "dividend / cash-distribution handling", "corporate-action handling",
            "fold rule", "execution semantics", "governed development dataset identity",
            "runtime image identity",
        ],
    },

    # ── domain ──────────────────────────────────────────────────────────────────────────────────
    "domain": {
        "plane": "development only",
        "window": ["2013-01-02", "2019-10-02"],
        "configs": ["A", "B", "C"],
        "dataset": {
            "path": "apps/backend/data/mr002_research.duckdb",
            "sha256": "24e5153cc0ebed77c7b422562e5a8ebfa147aad3019b27035b5314aaaacfad5a",
            "referent": "the data_manifest_identity bound in MR002_EvaluatorBinding.json and in "
                        "custody_review/sealed_partition_commitment.py",
        },
        "governed_stage3_census_expected": {
            "A": {"PRIMARY_QUALIFIED": 1426, "FALLBACK_QUALIFIED": 1, "invocations": 1427},
            "B": {"PRIMARY_QUALIFIED": 1532, "FALLBACK_QUALIFIED": 3, "invocations": 1535},
            "C": {"PRIMARY_QUALIFIED": 933, "FALLBACK_QUALIFIED": 0, "invocations": 933},
            "total_invocations": 3895,
        },
        "validation_store_opened": False,
        "sealed_or_reference_bytes_read": 0,
        "oos": "PROHIBITED",
        "validation_2": "PROHIBITED",
        "consumed_validation_opening": "unchanged",
    },

    # ── the comparison surface, fixed before any result exists ──────────────────────────────────
    # Every line of the owner's required end-to-end comparison, mapped to a CONCRETE observable of
    # the frozen replay. Granularity is session-by-session and config-by-config as required; the
    # trade ledger is additionally compared record-by-record.
    "comparison_surface": {
        "granularity": "per config (A/B/C) x per session, plus per Stage-3 invocation and per "
                       "closed trade",
        "required_by_owner": {
            "stage3_disposition": {
                "observable": "ordered per-invocation census row from the routing seam: "
                              "disposition, accepted_by generator, termination reason",
                "comparison": "exact equality of the ordered sequence",
            },
            "accepted_holdings_weights": {
                "observable": "(a) per-invocation accepted allocation vector z returned to "
                              "build_joint; (b) per-session res.y and res.x books "
                              "(permaticker -> float64)",
                "comparison": "byte identity of the float64 payload, in order",
            },
            "entry_exit_decisions": {
                "observable": "per session: orders, exits, reductions, entries_long, "
                              "entries_short, exit-reason multiset, hard_exits_due / _executed / "
                              "_pending_missing_open, adv_clipped, over_cap_days",
                "comparison": "exact equality per session",
            },
            "trades_orders_implied": {
                "observable": "the closed-trade ledger Acc.trades: permaticker, side, "
                              "entry_session, exit_session, reason, gross_pnl, costs, net_pnl",
                "comparison": "record-by-record, in order; float fields by byte identity",
            },
            "executed_notional": {"observable": "per-session delta and cumulative traded_notional",
                                  "comparison": "byte identity"},
            "costs": {"observable": "per-session delta and cumulative costs",
                      "comparison": "byte identity"},
            "borrow": {"observable": "per-session delta and cumulative borrow",
                       "comparison": "byte identity"},
            "dividends_cash_distributions": {
                "observable": "DISCLOSED PROPERTY OF THE FROZEN CONSTRUCTION — see "
                              "scope_disclosures.dividends_have_no_independent_ledger",
                "comparison": "reconciled through the two channels that carry them: the "
                              "gap-filter candidate set and the action-exit hard exits",
            },
            "nav": {"observable": "per-session NAV level (nav_curve) and final NAV",
                    "comparison": "byte identity of the full curve"},
            "daily_return": {"observable": "per-session daily_ret",
                             "comparison": "byte identity of the full series"},
            "fold_membership": {
                "observable": "phase3c.folds.fold_of(session) for every replayed session",
                "comparison": "exact equality — but MECHANICALLY VACUOUS on this domain, see "
                              "scope_disclosures.fold_membership_is_vacuous_on_development",
            },
            "cumulative_config_return": {
                "observable": "nav_curve[-1] / NAV0 - 1 per config",
                "comparison": "byte identity",
            },
            "run_config_hashes": {
                "observable": "the ordered per-session determinism-hash sequence and the run hash "
                              "derived from it",
                "comparison": "exact equality of every session hash, in order",
            },
        },
        "reconciliation_evidence_only": {
            "status": "REPORTED, NEVER DECISIONAL",
            "fields": ["cumulative return", "fold results", "Sharpe", "max drawdown",
                       "trade count", "turnover", "cost totals"],
            "source": "the metrics() block already present in the frozen replay output",
            "rule": "these are quoted to show the two arms reconcile. No N3 threshold is derived "
                    "from any of them, and no new economic statistic is introduced to judge N3.",
        },
    },

    # ── the mechanically derived reconciliation bound ───────────────────────────────────────────
    # Derived, not chosen. It is derived from the structure of the replay, before any result.
    "numerical_reconciliation_bound": {
        "derivation": {
            "step_1_channels": (
                "The v2 method can influence the replay through exactly two channels, both at the "
                "joint_portfolio._solve_qp seam that stage3_route and the v2 seam replace: "
                "(C1) the accepted allocation vector z returned to build_joint, which propagates "
                "to res.y / res.x and therefore to orders, notional, costs, borrow, "
                "mark-to-market, NAV, daily return and the trade ledger; and (C2) the solver info "
                "dict, which reaches res.outcome and diag['zero_entry_reason'] and therefore the "
                "session outcome classification. There is no third channel: every other input to "
                "the loop -- prices, candidates, eligibility, exits, sizing, the cost and borrow "
                "models -- is computed by code that is byte-identical between the two arms and "
                "consumes only frozen dataset values."
            ),
            "step_2_determinism": (
                "The replay is executed in a single frozen image under FROZEN_THREAD_ENV "
                "(OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1, OPENBLAS_CORETYPE=HASWELL) with "
                "--network=none. Under that environment the arithmetic is a fixed sequence of "
                "IEEE-754 double operations with no threading-order nondeterminism."
            ),
            "step_3_conclusion": (
                "Therefore, conditional on C1 and C2 identity, every downstream economic quantity "
                "is produced by the SAME operations on the SAME operands in the SAME order, so "
                "the difference is EXACTLY ZERO -- not 'small'. The mechanically derived "
                "reconciliation bound on the development replay is ZERO on every compared "
                "quantity. It is not a tolerance and was not selected to fit a result."
            ),
        },
        "bound_when_C1_C2_identity_holds": 0.0,
        "bound_when_C1_identity_fails": {
            "status": "DEFINED BUT NOT PRESUMED — engages only on instances where the accepted "
                      "allocation is not byte-identical",
            "allocation_layer": "the ALREADY-REGISTERED N1 equivalence rule "
                                "(EQUIVALENCE_TRIVIAL / EQUIVALENCE_PROVEN_BOUND). N3 does not "
                                "re-derive an allocation equivalence rule.",
            "propagation_per_session": {
                "notional": "|d notional_i| <= NAV_open * |d z_i|",
                "costs": "|d costs| <= COST_BPS*1e-4 * NAV_open * ||d z||_1",
                "nav": "|d NAV| <= NAV_open * ||d z||_1 * (1 + COST_BPS*1e-4)",
                "note": "these compound across sessions through NAV_open; the differential "
                        "reports the realized compounding rather than a closed-form envelope",
            },
            "handling": "every such instance is INDIVIDUALLY ENUMERATED in the differential and "
                        "surfaced in the verdict. It is never silently absorbed.",
        },
        "owner_instruction_honoured": (
            "'If the existing N1 preservation machinery can prove byte identity, use byte "
            "identity. Do not weaken exact equality to a tolerance just because N3 formally "
            "permits numerical equivalence.' The primary rule below is byte identity. The bound "
            "above is a fallback that must be reported, not a relaxation applied up front."
        ),
    },

    # ── the pass rule ───────────────────────────────────────────────────────────────────────────
    "pass_rule": {
        "scope": "every governed development replay observation, for every config A/B/C, where v1 "
                 "produced an accepted economic state",
        "tier_1_primary": {
            "name": "BYTE IDENTITY",
            "requirement": "every quantity in comparison_surface.required_by_owner is "
                           "byte-identical between the v1 arm and the v2 arm",
            "verdict_if_met": "N3_PASS",
        },
        "tier_2_fallback": {
            "name": "REGISTERED NUMERICAL EQUIVALENCE",
            "engages": "only on quantities where Tier 1 fails",
            "requirement": "the allocation layer satisfies the already-registered N1 equivalence "
                           "rule AND every economic difference lies within "
                           "numerical_reconciliation_bound.bound_when_C1_identity_fails",
            "verdict_if_met": "N3_PASS_WITH_DISCLOSED_NUMERICAL_DIFFERENCE",
            "why_a_distinct_verdict": (
                "v2 is supposed to repair numerical resolution, not alter economic behaviour. A "
                "within-bound but non-zero economic difference is still a behavioural change. "
                "Recording it under the same label as a clean pass would hide the one thing the "
                "owner asked to be told about, so it is a separate disposition the owner "
                "adjudicates."
            ),
        },
        "six_registered_checks": [
            "C1 Stage-3 accepted allocation equivalent under the already-registered equivalence "
            "rule",
            "C2 downstream behavioural outputs reconcile",
            "C3 economic outputs reconcile within the mechanically derived bound",
            "C4 no new unresolved numerical failure",
            "C5 no integrity defect",
            "C6 no unregistered termination reason",
        ],
        "primary_gate": "allocation and behavioural preservation. NOT return improvement.",
    },

    # -- firewalls ------------------------------------------------------------------------------
    "firewalls": {
        "better_is_not_a_win": {
            "rule": "improvement OR degradation beyond the registered numerical reconciliation "
                    "bound => N3_STOP / investigate. Never 'accept because better'.",
            "why": "Stage-3 v2 repairs numerical resolution. It is not licensed to alter economic "
                   "behaviour. A return improvement is evidence that something other than "
                   "numerical resolution changed, which is a defect signal, not a result.",
            "enforced_mechanically": "the differential compares MAGNITUDES and is SIGN-BLIND; the "
                                     "pass rule contains no directional term, so a favourable "
                                     "difference cannot pass a test an unfavourable one fails",
        },
        "N1_prior_evidence_does_not_soften_N3": {
            "prior": "MR002_N1_FinalVerdict_v1.0 finding preservation_governed_v1_replay reported "
                     "byte identity for PIQP_P2 on this same window and configs",
            "rule": "that is helpful prior evidence and nothing more. N3 registers its rule before "
                    "its result, executes independently, and is adjudicated on its own output. "
                    "The prior does not lower any requirement, shrink the comparison surface, or "
                    "excuse a failure.",
            "and_the_converse": "reproducing the N1 numbers is NOT itself the pass criterion. The "
                                "pass criterion is the rule registered above.",
        },
        "no_new_economic_statistics": {
            "rule": "N3 introduces no economic statistic that the frozen replay does not already "
                    "produce. Sharpe and drawdown are quoted only because metrics() already "
                    "computes them.",
        },
        "no_solver_selection": "N3 evaluates one frozen pair. It ranks nothing and recommends no "
                              "solver.",
        "no_rerun_of_N2": "the N2 stress population is not regenerated, re-scored or re-run. "
                          "N2 is closed.",
    },

    # -- honest scope disclosures, registered BEFORE execution -----------------------------------
    "scope_disclosures": {
        "fold_membership_is_vacuous_on_development": {
            "fact": "the five frozen folds span 2020-01-13 .. 2023-02-08 "
                    "(phase3c/folds.py FROZEN_FOLDS). The N3 domain is the development window "
                    "2013-01-02 .. 2019-10-02. The two are DISJOINT, so fold_of(session) returns "
                    "None for every session N3 replays.",
            "consequence": "the fold-membership comparison is satisfied VACUOUSLY (None == None "
                           "for all sessions) and carries no evidential weight. Fold RESULTS "
                           "cannot be computed on this domain at all.",
            "why_not_fixed": "the only domain with a non-vacuous fold structure is the validation "
                             "window, and Validation-2 / OOS are PROHIBITED and the original "
                             "opening is consumed. Partitioning the development window into "
                             "substitute folds would invent a new economic construct, which the "
                             "grant forbids.",
            "recorded_as": "a DISCLOSED LIMITATION of N3, not a satisfied check. It is reported "
                           "with this caveat attached in the verdict.",
        },
        "dividends_have_no_independent_ledger": {
            "fact": "FrozenDataset.day_inputs sets the cash-distribution term to 0.0 for every "
                    "name ('dividends handled via ACTIONS below'), so the distribution argument "
                    "to economic_gap is identically zero across the development window. Dividends "
                    "and corporate events reach the replay only as ACTIONS "
                    "(acquisitionby / delisted / bankruptcy) via DayInputs.action_exit.",
            "consequence": "there is no separate dividend cash ledger in the frozen replay to "
                           "reconcile line-for-line.",
            "how_N3_reconciles_it": "through the two channels that actually carry the effect: the "
                                    "gap-filter candidate set and the action-exit hard exits, "
                                    "both compared per session, plus the bound dataset identity. "
                                    "Neither channel is downstream of Stage-3, so neither can be "
                                    "perturbed by the method under test.",
            "why_not_fixed": "adding a dividend accumulator would change the frozen replay and "
                             "introduce an economic quantity the governing construction does not "
                             "have. Disclosed rather than invented.",
        },
        "instrumentation_must_be_proven_inert": {
            "risk": "capturing per-session rows requires observing the replay while it runs. "
                    "Observation that perturbs the replay would make the differential measure the "
                    "instrument rather than the method.",
            "control": "the v1 arm is executed BOTH instrumented and uninstrumented, and the two "
                       "must agree on the full per-session determinism-hash sequence and on every "
                       "aggregate economic field. A mismatch is an N3_STOP for INSTRUMENT DEFECT, "
                       "reported as such and never as a method result.",
            "additional_check": "the uninstrumented v1 arm must reproduce the governed Stage-3 "
                                "census exactly (A 1426/1, B 1532/3, C 933/0), as the N1 baseline "
                                "reconciliation established it does.",
        },
    },

    # -- execution and custody plan --------------------------------------------------------------
    "execution_plan": {
        "runtime_image": "mr002-research:v1.4",
        "network": "none",
        "frozen_thread_env": {
            "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1", "OPENBLAS_CORETYPE": "HASWELL",
        },
        "arms_per_config": ["v1 uninstrumented (inertness control)",
                            "v1 instrumented (baseline)",
                            "v2 instrumented (QUADPROG_SQRT + PIQP_P2)"],
        "determinism": "a deterministic rerun of the v2 arm must reproduce its own outputs "
                       "bit-for-bit, as N1 and N2 both required",
    },
    "custody_plan": {
        "model": "the pattern proven by N1 and N2: large row/session-level differential to "
                 "versioned S3 pinned by VersionId + SHA-256 with read-back confirmation; the "
                 "concise governing verdict and the manifest in Git.",
        "s3_bucket": "workbench-backups-219024422756",
        "object_key_prefix": "artifacts/governed/mr002-n3-execution-evidence/1.0/",
        "manifest_path": "manifests/s3/objects/mr002-n3-execution-evidence.v1.json",
        "binds": ["execution commit", "runtime image", "frozen thread environment",
                  "dataset identity", "v1 baseline identity", "N1 and N2 verdict identities",
                  "this registration identity"],
        "scratch": ".mr002out/ remains 'scratch, never evidence' and is not a governance store",
    },

    "boundary": {
        "development_domain_only": True,
        "validation_store_opened": False,
        "sealed_or_reference_bytes_read": 0,
        "validation_2": "PROHIBITED",
        "oos": "PROHIBITED",
        "consumed_validation_opening": "unchanged",
        "cycle_2C": "NOT AUTHORIZED - it follows an N3 PASS and requires its own grant",
    },
}



# -- disposition comparison: the registered SEMANTIC CLASS, not the raw label -------------------
REG["disposition_semantic_class"] = {
    "problem": "the v1 cascade and the v2 method reconcile to DISJOINT label vocabularies. v1 "
               "emits PRIMARY_QUALIFIED / FALLBACK_QUALIFIED / UNRESOLVED_NUMERICAL_FAILURE / "
               "INVALID_RUN; v2 emits PRIMARY_CERTIFIED / SECONDARY_CERTIFIED / "
               "UNRESOLVED_INSTANCE / INVALID_RUN. Comparing the raw strings would fail on EVERY "
               "invocation by construction. That is a broken check, not a strict one.",
    "authority": {
        "record": "MR002_N1_FinalVerdict_v1.0 — owner ruling of 2026-08-19, D3 clause 5",
        "ruling": "'Method disposition' means the TERMINAL SEMANTIC CLASS of the two-generator "
                  "method — resolved certified allocation vs unresolved / integrity stop — not "
                  "the accepted_by generator attribution.",
        "note": "N3 applies this ruling verbatim. It does not extend it and does not invent a "
                "vocabulary of its own.",
    },
    "mapping": {
        "RESOLVED_CERTIFIED_ALLOCATION": {
            "v1": ["PRIMARY_QUALIFIED", "FALLBACK_QUALIFIED"],
            "v2": ["PRIMARY_CERTIFIED", "SECONDARY_CERTIFIED"],
        },
        "UNRESOLVED": {"v1": ["UNRESOLVED_NUMERICAL_FAILURE"], "v2": ["UNRESOLVED_INSTANCE"]},
        "INVALID_RUN": {"v1": ["INVALID_RUN"], "v2": ["INVALID_RUN"]},
        "UNREGISTERED": {"v1": ["<any other label>"], "v2": ["<any other label>"],
                         "effect": "fails C6 — an unregistered termination reason"},
    },
    "compared_as": "the ordered PER-INVOCATION sequence of semantic classes must be exactly equal "
                   "between the arms",
    "generator_attribution_is_diagnostic": {
        "rule": "which generator produced the accepted point (primary vs fallback/secondary) is "
                "RECORDED AND REPORTED but is NOT a pass criterion, exactly as N1 retained Solver "
                "A's permutation instability as an explicit diagnostic rather than presuming it "
                "away.",
        "why": "the governed v1 census contains 4 FALLBACK_QUALIFIED invocations across A/B/C. If "
               "v2 certifies any of those on its primary generator, the terminal semantic class "
               "is unchanged and the accepted allocation must STILL be byte-identical.",
    },
    "allocation_requirement_unchanged": "STRICT. The N1 ruling is explicit that the semantic-class "
                                        "reading is 'not a relaxation of the allocation "
                                        "requirement, which stays strict'. C1 remains byte "
                                        "identity of the accepted allocation.",
    "amendment_note": {
        "added": "2026-08-20, BEFORE any governed N3 execution",
        "trigger": "a scratch smoke run on a non-governed 124-session window (explicitly not "
                   "evidence) surfaced the vocabulary disjunction as a CODING defect in the "
                   "differential.",
        "why_this_is_not_post_results_rule_invention": "no governed N3 result existed, none had "
                                                       "been computed, and no threshold was "
                                                       "moved. The clarification names the label "
                                                       "spaces the already-adjudicated N1 ruling "
                                                       "was about. It is recorded here rather "
                                                       "than applied silently in code.",
    },
}

# -- bindings: every source the N3 rule depends on, by PUSHED Git blob -------------------------
REG["identity_basis"] = {
    "head": _head,
    "remote_head": _remote,
    "head_is_pushed": _pushed,
    "rule": "a Git-blob identity is only a PUSHED identity once HEAD has reached the remote branch",
}

REG["bound_sources"] = {
    "frozen_method": [
        bound(M + "n1/method.py"),
        bound(M + "n1/seam.py"),
        bound(M + "n1/reference.py"),
    ],
    "v1_baseline_path": [
        bound(M + "stage3_route.py"),
        bound(M + "stage3_cascade.py"),
    ],
    "governing_construction": [
        bound(M + "joint_portfolio.py"),
        bound(M + "runner.py"),
        bound(M + "dataset.py"),
    ],
    "replay_and_certifier": [
        bound(S + "mr002_development_run.py"),
        bound(S + "mr002_coverage_signed_gap.py"),
    ],
    "fold_authority": [
        bound(M + "phase3c/folds.py"),
    ],
    "prior_gate_machinery_reused": [
        bound(S + "mr002_n1_preservation.py"),
    ],
}
# The N3 differential implementation is deliberately NOT bound here. It is written AFTER this
# record, exactly as N1's execution implementation followed its registration, and it is bound by
# the VERDICT under execution_identities.bound_source — which is where N1 bound its own. Freezing
# the RULE before the CODE is the point: the rule constrains the code, never the reverse. Binding
# an unwritten file here would also make this record's identity depend on code it is supposed to
# govern, which is the wrong direction of dependency.
REG["implementation_binding"] = {
    "path": S + "mr002_n3_equivalence.py",
    "bound_by": "MR002_N3_Verdict_v1.0 -> execution_identities.bound_source",
    "why_not_here": "it does not exist yet, and this record must not depend on the code it "
                    "governs",
}
REG["pending_bindings"] = sorted(PENDING)
# SEALED is DERIVED, never asserted: every binding enforced from Git AND HEAD present on the
# remote. Asserting a seal the basis does not support is the defect class this check exists for.
REG["record_status"] = "SEALED" if (not PENDING and _pushed) else "DRAFT"
REG["sealing_requirement"] = (
    "this record is DRAFT while any binding is non-enforced. Sealing re-derives every binding from "
    "PUSHED Git and re-emits the identity."
)


def main() -> int:
    body = {k: v for k, v in REG.items() if k != "record_identity_sha256"}
    ident = hashlib.sha256(_canonical(body)).hexdigest()
    body["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_N3_ProspectiveRegistration_v1.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(body))
    os.replace(tmp, out)

    print("MR-002 Gate N3 PROSPECTIVE REGISTRATION")
    print(f"  identity   {ident}")
    print(f"  status     {REG['record_status']}")
    print(f"  head       {_head}  pushed={_pushed}")
    print(f"  pending    {REG['pending_bindings'] or 'none'}")
    print(f"  wrote      {out}")
    if not _pushed:
        print("  WARNING: HEAD is not pushed; Git-blob bindings are not PUSHED identities yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
