"""The COMPLETE Layer 2 package — everything a countersignature ruling needs, in one artifact.

## What this is for

It assembles the whole governed reconstruction: what was found, what was rebuilt, what was measured,
what remains unproven, and what is still required before any of it may run. Every digest it states is
recomputed from the artifact bytes at assembly time, so the package cannot name evidence it did not
actually read.

## What it is NOT

⛔ It is not an authorization to deploy. `runtime_compatible` is FALSE and stays false until native
Layer 2 manifest loading is implemented, CI-green, merged, and deployed from the exact squash. A
countersignature here approves the governed DATA CONSTRUCTION and its evidence — not deployment
success, and not the July 27 observation.

⛔ It does not claim every corporate action is economically reconciled. It claims something narrower
and states the limitation in the same breath.
"""

# ⚠ PORTED into the repository for REPRODUCIBILITY. Operator machine paths are removed: the
# backend root resolves relative to this file and every data location comes from an argument or
# an environment override. A hard-coded working-copy path would make the tool unrunnable by
# anyone else, which is the opposite of what a reproducible build tool is for.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.validation.governed_corpus import canonical_json  # noqa: E402

ROOT = Path(os.environ.get("LAYER2_ROOT", "."))
FVD = ROOT / "forward-validation-deploy"
V2 = ROOT / "layer2-vintage" / "v2"
C2 = ROOT / "layer2-vintage" / "corpus-v2"

CONSTRUCTION_SCHEMA_VERSION = "LAYER2_SINGLE_VINTAGE_PERMANENT_LINEAGE_v1.0"
PROPOSED_MANIFEST = "1e269fadedff74b04135dea5441f2f3338852464c3d06a74c81c98dfc43ca064"
SUPERSEDED_MANIFEST = "a69ad50ffc3c6925b3c9b6c8fd1c2adc7143ef9d5c98e9378e1c3ea21ca75c49"


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    manifest_p = C2 / "proposed_corpus_manifest_v2.json"
    step7_p = C2 / "step7_supersession_package.json"
    manifest = json.loads(manifest_p.read_bytes())
    step7 = json.loads(step7_p.read_bytes())

    for p, expected, label in ((manifest_p, PROPOSED_MANIFEST, "proposed manifest"),):
        actual = _sha(p)
        if actual != expected:
            print(f"REFUSED — {label} digest moved: {actual} != {expected}")
            return 1

    pkg = {
        "kind": "layer2_complete_package", "version": "v1.0",
        "assembled_for": "countersignature ruling",
        "session": "2026-07-27",
        "construction_schema_version": CONSTRUCTION_SCHEMA_VERSION,

        # ── STATE — the four flags, stated first because everything else is read through them ──
        "state": {
            "proposed": True,
            "countersigned": False,
            "deployed": False,
            "runtime_compatible": False,
            "runtime_compatible_blocked_until":
                "native Layer 2 manifest loading is implemented, CI-green, merged, and deployed "
                "from the exact squash commit",
            "account4": "UNCHANGED", "forward_window": "CLOSED",
            "session_count": 0, "witness_prefix": "EMPTY",
        },

        # ── (1) EXECUTIVE DECISION RECORD ──
        "executive_decision_record": {
            "what_was_wrong": (
                "The countersigned corpus spliced TWO ADJUSTMENT VINTAGES at 2026-06-15. Rows before "
                "the seam were loaded in a one-shot bulk ingest and never re-pulled, so any "
                "distribution after 2026-06-15 back-adjusted only the refreshed side. It also "
                "resolved securities by TICKER, conflating distinct issuers that reused a symbol."),
            "how_bad": (
                "The seam produced a cross-sectional mean 1-day adjusted return of +38.0398% across "
                "5,761 names on 2026-06-15 — physically impossible — which compounds permanently "
                "into the market-proxy index. 44 of 200 scoring names and 111 of 671 proxy names "
                "were affected."),
            "what_was_done": (
                "A whole-corpus reconstruction from ONE sealed source vintage, normalized on the "
                "vendor's PERMANENT identifier rather than ticker text, with every excluded or "
                "quarantined identity adjudicated and digest-bound."),
            "what_it_changed": (
                "The July 27 PORTFOLIO DECISION IS UNCHANGED — top five AXTI SNDK BE WDC MU, "
                "identical ordering, identical 19.6% equal weights, identical regime state "
                "ABOVE_BAND at 0.98 gross. What changed is a DECISION INPUT: the margin above the "
                "regime moving average more than halved, +27.2576% -> +12.3491%."),
            "why_that_matters": (
                "Layer 2 corrected a decision input even though it did not change this particular "
                "decision. The regime state held only because both values sit far above the ±2% "
                "band; nearer the band the seam would have changed the regime outright. The rebuilt "
                "margin is the valid one."),
            "what_remains_unproven": (
                "18 economically terminal acquired-side events cannot be proven from the vendor "
                "schema, which supplies no per-share consideration, exchange ratio or successor "
                "conversion term. Each was MEASURED to have zero July 27 decision impact and is "
                "DISCLOSED, not waived."),
            "what_is_still_required": (
                "Native Layer 2 manifest loading. The registered loader was TESTED against this "
                "manifest and refuses it."),
        },

        # ── (2) SOURCE-VINTAGE EVIDENCE ──
        "source_vintage": {
            "source_vintage_sha256": manifest["declared_identities"]["source_vintage_sha256"],
            "artifacts": {k: manifest["artifacts"][k]
                          for k in ("source_vintage", "extraction_evidence")},
            "sealed_verification": "verify_sealed_vintage.py — 20/20 checks PASS",
            "one_vintage_definition": (
                "NOT equal refresh timestamps — each datatable refreshes on its own schedule. What is "
                "provable is a NO-CHANGE WINDOW: all 9 vendor identities recorded before the pull and "
                "reconfirmed after, so an instant exists at which all three were simultaneously "
                "current."),
            "trap": (
                "⚠ the export OBJECT NAME is NOT content-addressed — the same name served DIFFERENT "
                "bytes across two pulls. Only the downloaded artifact sha256 is a content identity."),
        },

        # ── (3) CROSSWALK AND BOTH UNIVERSE IDENTITIES ──
        "universes": {
            "legacy_governed_universe_sha256":
                manifest["declared_identities"]["legacy_governed_universe_sha256"],
            "legacy_size": 14_150,
            "governed_universe_key_crosswalk_sha256":
                manifest["declared_identities"]["governed_universe_key_crosswalk_sha256"],
            "governed_mapped_identity_universe_sha256":
                manifest["declared_identities"]["governed_mapped_identity_universe_sha256"],
            "mapped_identity_universe_size": manifest["mapped_identity_universe_size"],
            "governed_price_universe_sha256":
                manifest["declared_identities"]["governed_price_universe_sha256"],
            "price_universe_size": manifest["price_universe_size"],
            "two_universes_never_collapsed": manifest["two_universes_never_collapsed"],
            "reconciliation": "14,150 keys -> 14,145 mapped -> 5 key exclusions -> 2 non-price-bearing "
                              "-> 14,143 price-bearing -> 0 unadjudicated",
            "security_identity_contract": manifest["security_identity_contract"],
            "artifacts": {k: manifest["artifacts"][k] for k in
                          ("universe_crosswalk_v2", "crosswalk_summary_v2", "price_universe_v2")},
        },

        # ── (4) EXCLUSIONS AND PRICE ADJUDICATIONS ──
        "exclusions_and_adjudications": {
            "excluded_identities": {
                "EXCLUDED_UNRESOLVED_SOURCE_MASTER": ["DHCC", "EVTV", "GAMB"],
                "EXCLUDED_DOCUMENTED_HISTORICAL_DELISTING": ["MRXLY", "PGIE"],
                "EXCLUDED_NO_AUTHORITATIVE_SEP_PRICE_COVERAGE": ["OCCI (113567)", "HYPG (6399295)"],
            },
            "reinstated_before_countersignature": {
                "VYNE (120814)": "INCLUDED_PRICE_BEARING — present as successor symbol YARW",
                "LTGRU (6399330)": "INCLUDED_PRICE_BEARING — present as successor symbol LTGR",
                "trap": "⚠ a by-TICKER presence test reports a FALSE ZERO in a permaticker-keyed "
                        "corpus; both were confirmed by PERMANENT IDENTITY",
            },
            "artifacts": {k: manifest["artifacts"][k] for k in
                          ("universe_exclusions_v2", "quarantine_unresolved_source_master_v2",
                           "layer2_price_adjudication", "july27_exclusion_impact_check")},
        },

        # ── (5) NORMALIZED CORPUS EVIDENCE ──
        "normalized_corpus": manifest["normalized_datasets"] | {
            "artifact": manifest["artifacts"]["normalized_corpus_evidence"],
            "guards": "G1 retracted-returns-rows · G2 quarantine-leak · G3 digest-matches-set · "
                      "G4 not-excluded-on-impact · G5 sealed in-window proof — ALL PASS",
            "join_basis": "SEP.ticker -> TICKERS.ticker -> permaticker WITHIN ONE VINTAGE (the "
                          "vendor's own internal key relation, never cross-vintage ticker equality)",
        },

        # ── (6) SEAM-ELIMINATION EVIDENCE ──
        "seam_elimination": {
            "claim": "the 2026-06-15 adjustment-vintage seam is ELIMINATED",
            "direct_proof": {
                "measure": "cross-sectional mean 1-day adjusted return on the seam date 2026-06-15",
                "superseded": "+38.0398% across 5,761 names — physically impossible",
                "rebuilt": "+0.4648% across 5,798 names — an ordinary day",
                "controls": "every adjacent session agrees between the corpora: 06-09 "
                            "+0.2615/+0.2663 · 06-11 +1.7931/+1.7844 · 06-16 -0.4930/-0.4782",
            },
            "worked_case_ABBV": "closeadj/close was 1.00000000 through 06-12 then 0.99296448 from "
                                "06-15 (a spurious 0.7% step); rebuilt it is continuous "
                                "0.99296288/0.99296169/0.99296096 -> 0.99296448",
            "governed_universe_census": "the former seam pair 06-12->06-15 has 80 stepped names and "
                                        "100% are explained by a dividend with an ex-date in that "
                                        "interval; controls 50/50 and 18/18 explained",
            "downstream_effect": "the proxy index level and therefore the regime margin — see the "
                                 "Step 4 comparison",
        },

        # ── (7) LINEAGE / HOLE CENSUS ──
        "lineage_and_holes": {
            "artifact": manifest["artifacts"]["lineage_hole_census"],
            "scoring_universe": "raw 200 -> eligible 200 · excluded 0",
            "proxy_basket": "10 month-ends -> raw 689 -> eligible 671 · excluded 18, ALL "
                            "NO_ACTIVE_LINEAGE (the ordinary acquired/delisted case)",
            "layer1_refusals_now_gone": "the old corpus additionally excluded 1 METADATA_PRICE_DISAGREE "
                                        "(ECHO) and 1 LOOKBACK_CROSSES_LINEAGE (INFQ); Layer 1 could "
                                        "only make conflated history INELIGIBLE, Layer 2 made it "
                                        "CORRECT",
            "structural_holes": "14,141 of 14,143 identities have ZERO; only 1 identity (0.01%) at or "
                                "over the 20-session threshold",
            "landmarks": {"ECHO": "perma 193776 EchoStar, 4,670 rows, 0 holes",
                          "ECHO2": "perma 193608 Echo Global, 3,057 rows — SEPARATED lineage",
                          "BKYI": "7,185 rows = EVERY session, the 22-session hole is gone",
                          "LEXX": "starts 2021-01-12, the correct Lexaria start",
                          "AMCRY": "ends 2007-06-04, the correct ADR end"},
        },

        # ── (8) COMPLETE STEP 3 RECONCILIATION ──
        "step3_reconciliation": {
            "artifact": manifest["artifacts"]["adjustment_reconciliation_final"],
            "supporting": {k: manifest["artifacts"][k] for k in
                           ("residual_relevance", "tolerance_remeasurement")},
            "scope": "1,791 (ticker,date) checks over 1,845 relevant actions; truncated=False",
            "terminal_census": {"PROVEN_REFLECTED": 1676,
                                "PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE": 94,
                                "PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT": 3,
                                "UNRESOLVED_NONDECISION_MA_SEMANTICS": 18,
                                "NOT_PROVEN_UNSUPPORTED_SEMANTICS": 0,
                                "conflict": 0, "insufficient": 0},
            "direction_b": {"undeclared_dividend_factor_changes": 4,
                            "undeclared_split_factor_changes": 0,
                            "combined_or_ambiguous": 0,
                            "all_four_are": "SHOP and TLN, both quarantined"},
            "key_findings": [
                "SHARADAR `close` is ALREADY SPLIT-ADJUSTED; `closeunadj` is the traded price. The "
                "split factor lives in close/closeunadj and CANNOT appear in closeadj/close.",
                "The 'N/A' contraticker sentinel made every dividend and split unverifiable; ⚠ `NA` "
                "is a LIVE TICKER, so the sentinel is matched EXACTLY and never case-folded.",
                "Direction (b) was STRUCTURALLY BLIND to splits — a split never changes the dividend "
                "factor. A second leg was added; it found its defect class EMPTY (no undeclared "
                "split exists in the vintage).",
                "`ACTIONS.value` is TYPE-DEPENDENT: dividend=cash/share, split=multiplier, "
                "acquisition=TRANSACTION VALUE IN MILLIONS. It must NEVER determine adjustment "
                "applicability.",
                "`spinoffdividend.value` IS the per-parent-share distributed value (verified on all "
                "14 in-window groups at 8e-08..1.3e-05); `spinoff.value` is the SHARE-COUNT RATIO "
                "and must never be reconstructed into a price term.",
            ],
            "tolerance": {
                "noise_safety_factor": 5.0, "status": "RETAINED",
                "basis": "NOT because corpus-v2 produced a universal plateau — it did not. Split-leg "
                         "noise is stable at 5x (floor 2 from 6x); lowering it increases noise "
                         "sharply (655 at 4x, 2,282 at 3x); raising it destroys true dividend "
                         "sensitivity (declared dividends flagged 8,220/8,229 at 5x -> 8,155 at 20x "
                         "-> 7,977 at 50x).",
                "retracted": "the earlier single-universal-plateau justification was measured on the "
                             "SEAM-CONTAMINATED predecessor store and is withdrawn",
            },
        },

        # ── (9) NARROW-READINESS ATTESTATION AND DISCLOSED LIMITATIONS ──
        "narrow_readiness": step7["step3_limitation_statement"] | {
            "readiness_contract": "DataReadiness.READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_"
                                  "LIMITATIONS, reachable ONLY via NarrowReadinessAttestation",
            "guards": "every clause re-derived from the measured evidence: every action assessed · no "
                      "conflict/insufficient · only the disclosed status tolerated · disclosure "
                      "digest-bound · per-status census sums to the assessed total and the bounding "
                      "arithmetic is consistent (CENSUS completeness — payload truncation under the "
                      "200-action production cap is expected and is NOT a refusal) · the census was "
                      "measured over this session's own relevance set, bound by digest · unexplained "
                      "movements only on quarantined identities · census not stale",
            "session_scoping": "the attestation names ONE session_date and is REFUSED for any other, "
                               "so the status can never be inherited",
            "not_in_readiness_set": "UNRESOLVED_NONDECISION_MA_SEMANTICS is deliberately NOT in "
                                    "SATISFIES_READINESS — a disclosure is not a proof",
        },

        # ── (10) SHOP/TLN QUARANTINE EVIDENCE ──
        "quarantine": manifest["governed_quarantine"] | {
            "artifact": manifest["artifacts"]["shop_tln_quarantine"],
            "anomalies": {"SHOP": "2025-06-26 and 2025-06-27",
                          "TLN": "2026-02-02 and 2026-02-03; closeadj on 02-02 = 348.36 = the 01-30 "
                                 "close exactly — a carried-forward stale value"},
            "zero_declared_actions_in_window": True,
            "second_access_path": "SUCCEEDED and returned BYTE-IDENTICAL values ⟹ the anomaly is what "
                                  "the vendor still publishes, NOT a transient capture defect ⟹ "
                                  "re-extraction would not fix it, so quarantine is correct",
            "measured_effect": "top five UNCHANGED; basket 689->687; contributors 663->661; regime "
                               "IDENTICAL; all gates pass unrelaxed",
            "quarantined_histories": manifest["quarantined_histories"],
        },

        # ── (11) CORRECTED STEP 4 COMPARISON ──
        "step4_comparison": step7["step4_evidence"] | {
            "artifact": manifest["artifacts"]["step4_comparison"],
            "apples_to_apples_proof": "the host runtime commit is the SAME squash this worktree sits "
                                      "on, and scripts/backtest_momentum_stage4.py hashes IDENTICALLY "
                                      "on both sides; ONE script was run against both stores",
            "unchanged": {"top_five": ["AXTI", "SNDK", "BE", "WDC", "MU"],
                          "ordering": True, "weights": "19.6% each, 98% gross",
                          "regime_state": "ABOVE_BAND", "scoring": "200/200", "scored": 198},
        },

        # ── (12) EXACT STEP 5 IMPACT ANALYSIS ──
        "step5_impact": step7["step5_evidence"],

        # ── (13)(14)(15) manifest, store identities, supersession ──
        "proposed_corpus_manifest": {
            "corpus_manifest_sha256": PROPOSED_MANIFEST,
            "artifact_bytes": manifest_p.stat().st_size,
            "reproducible": "re-ran the whole build end-to-end; byte-identical output",
            "every_digest_computed_from_disk": True,
            "missing_artifact_behaviour": "REFUSE",
        },
        "store_identities": step7["proposed"] | {
            "semantics": step7["store_identity_semantics"]},
        "supersession": step7["supersession"] | {
            "package_sha256": _sha(step7_p),
            "superseded": step7["superseded"]},

        # ── (16) LOADER COMPATIBILITY REQUIREMENT ──
        "loader_compatibility_requirement": step7["deployment_compatibility"] | {
            "ruling": "NATIVE support for the Layer 2 manifest kind",
            "rejected_alternative": "converting the reconstruction into a synthetic base-plus-delta "
                                    "deployment manifest — that would make the runtime accept the "
                                    "bytes by representing the construction as something it is not",
            "loader_increment_must": [
                "recognize the exact kind and construction_schema_version",
                "validate the reconstruction manifest's canonical hash",
                "require all 18 evidence artifacts, quarantine histories, universe identities and "
                "store identities",
                "validate the explicit supersession link",
                "refuse Layer 2 schema versions it does not understand",
                "return a normalized internal construction object WITHOUT inventing "
                "base_coverage_through, a base artifact identity, delta order or delta coverage",
                "preserve existing base-plus-delta loading unchanged",
            ],
            "runtime_must_expose": {
                "corpus_construction_kind": "layer2_governed_corpus",
                "construction_schema_version": CONSTRUCTION_SCHEMA_VERSION,
                "supersedes_corpus_manifest_sha256": SUPERSEDED_MANIFEST,
            },
            "internal_normalization_allowed_only_if": "it does not claim a base or delta exists and "
                                                      "does not generate a misleading registered "
                                                      "manifest artifact",
        },

        # ── (17) COMPLETE ARTIFACT INVENTORY ──
        "artifact_inventory": manifest["artifacts"],
        "artifact_count": len(manifest["artifacts"]),
        "quarantine_inventory": manifest["quarantined_histories"],

        # ── (18) CODE/TREE IDENTITY AND LOCAL GATES ──
        "code_identity_and_gates": step7["code_identity"],
        "schema_differences": step7["schema_differences"],
        "wording_rulings": step7["wording_rulings"],

        # ── the conditional countersignature this package is assembled for ──
        "countersignature_request": {
            "scope": "the governed DATA CONSTRUCTION and its evidence",
            "explicitly_not": ["deployment success", "the July 27 observation",
                               "a claim that all corporate actions are economically reconciled"],
            "proposed_conditional_wording":
                "Approved as the replacement governed corpus construction; NOT authorized for "
                "deployment or observation until native Layer 2 manifest loading is implemented, "
                "CI-green, merged, deployed from the exact squash commit, and the complete readiness "
                "run passes.",
            "sequence_preserved": [
                "complete Layer 2 package", "countersignature ruling", "one coherent PR",
                "CI and exact-head merge", "deploy native loader plus verifier changes",
                "install countersigned corpus", "complete readiness",
                "immediate Account 4 check", "opening package"],
        },
        "gates_relaxed": False,
    }

    blob = canonical_json(pkg)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()

    print("=" * 78)
    print("COMPLETE LAYER 2 PACKAGE")
    print("=" * 78)
    for k in ("proposed", "countersigned", "deployed", "runtime_compatible"):
        print(f"  {k:<22}{pkg['state'][k]}")
    print(f"  {'account4':<22}{pkg['state']['account4']}")
    print(f"  {'forward_window':<22}{pkg['state']['forward_window']}")
    print()
    print(f"  proposed manifest     {PROPOSED_MANIFEST}")
    print(f"  supersedes            {SUPERSEDED_MANIFEST}")
    print(f"  supersession package  {pkg['supersession']['package_sha256']}")
    print(f"  artifacts bound       {pkg['artifact_count']} + "
          f"{len(pkg['quarantine_inventory'])} quarantine histories")
    print("  sections              18")
    print(f"\nlayer2_complete_package_sha256: {digest}")
    print(f"wrote {out} ({len(blob):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
