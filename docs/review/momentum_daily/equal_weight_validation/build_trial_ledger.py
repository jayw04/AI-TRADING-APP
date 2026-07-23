#!/usr/bin/env python3
"""Assemble the DSR trial ledger for the equal-weight production-sizing validation (PREREG v1.0 §7 D).

Conservative rule (owner 2026-07-22): include EVERY materially related experiment in the momentum
lineage whose result was seen before the next design choice; exclude ONLY pure mechanical
reproductions with no new performance interpretation, and document each exclusion. The effective
count may exceed the number of named strategies, never fall below it without a documented dependence
adjustment (none is claimed here — effective == included).

Deterministic: emits TrialLedger_v1.0.json + a content SHA-256, from a fixed row list.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

FULL = "2005-01-03..2026-06-12"

# Each row: trial_id, research_program, configuration, data_window, decision_role,
# result_seen_before_next_choice, included_in_trial_count, inclusion_or_exclusion_reason,
# artifact_or_commit.
ROWS: list[dict] = []


def add(tid, prog, cfg, window, role, seen, included, reason, artifact):
    ROWS.append({
        "trial_id": tid, "research_program": prog, "configuration": cfg, "data_window": window,
        "decision_role": role, "result_seen_before_next_choice": seen,
        "included_in_trial_count": included, "inclusion_or_exclusion_reason": reason,
        "artifact_or_commit": artifact,
    })


# ── Stage 2 — rebalance policy (4) ────────────────────────────────────────────────
S2 = "MR_MomentumDaily_Stage2_full.json"
for v, lbl in [("A", "Weekly (v0.9 baseline)"), ("B", "Trade-on-change"),
               ("C", "Daily conditional (§5.1)"), ("D", "Biweekly")]:
    add(f"S2-{v}", "momentum-daily Stage 2 (rebalance policy)", f"N5/ew/nocap · rebalance={lbl}",
        FULL, "rebalance-policy selection (chose C)", True, True,
        "distinct rebalance-cadence performance trial; result seen before choosing C", S2)

# ── Stage 3 — construction grid (12) ──────────────────────────────────────────────
S3 = "MR_MomentumDaily_Stage3_full.json"
for n in (5, 8, 10):
    for sizing in ("ew", "hyb"):
        for cap in ("nocap", "cap"):
            add(f"S3-N{n}-{sizing}-{cap}", "momentum-daily Stage 3 (construction)",
                f"N{n}/{sizing}/{cap}", FULL, "construction selection (chose N5/*/nocap)", True, True,
                "distinct construction (name-count × sizing × sector-cap) performance trial", S3)

# ── Stage 4 — regime variant (4) ──────────────────────────────────────────────────
S4 = "MR_MomentumDaily_Stage4_full.json"
for v, lbl in [("A", "Binary"), ("B", "Buffered binary"), ("C", "Graduated"), ("D", "None-control")]:
    add(f"S4-{v}", "momentum-daily Stage 4 (regime)", f"N5/ew/nocap · regime={lbl}", FULL,
        "regime selection (chose C graduated)", True, True,
        "distinct regime-overlay performance trial; result seen before choosing C", S4)

# ── Inception threshold — Policy M vs H, on proxy (5A) and actual book (5B) (4) ────
for step, data in [("5A", "market proxy"), ("5B", "actual 5-name book")]:
    for pol in ("M(>=0.60)", "H(=0.98)"):
        add(f"INC-{step}-{pol[0]}", "momentum-daily inception threshold (Step 5)",
            f"initial_seed policy {pol} · data={data}", FULL,
            "inception-threshold selection (locked 0.60)", True, True,
            "distinct inception-eligibility performance trial; both 5A and 5B results seen before "
            "the 0.60 lock. No dependence discount claimed (5A/5B evaluate the same 2 policies on "
            "different data → effective could be argued as 2, but conservatively counted as 4).",
            "threshold_policyM_vs_policyH_v1.0.md / threshold_actualbook_5B_v1.0.md")

# ── Weighting-defect impact study — equal-weight arms, variants C & D (6) ──────────
IMP = "weighting_defect_impact_v1.1.json"
for var in ("C", "D"):
    for arm, desc in [("B_pinned_equal", "equal, trade-date-pinned"),
                      ("B_free_equal", "equal, free-running"),
                      ("B_pinned_production", "production capped-equal, pinned")]:
        add(f"IMP-{var}-{arm}", "momentum-daily weighting-defect impact study",
            f"variant {var} · {desc}", FULL, "sizing correction-impact (verdict MATERIALLY_DIFFERENT)",
            True, True,
            "distinct equal-weight performance arm; pinned vs free are distinct trials, production "
            "arm distinct from preregistered arm; variant C (graduated) and D (regime-free) are "
            "distinct regime contexts", IMP)
# The A_defective_hybrid arms reproduce the Stage-3/4 hybrid winner — EXCLUDED (mechanical repro).
for var in ("C", "D"):
    add(f"IMP-{var}-A_defective_hybrid", "momentum-daily weighting-defect impact study",
        f"variant {var} · defective hybrid (reference)", FULL, "reproduction reference", True, False,
        "EXCLUDED: mechanical reproduction of the already-counted Stage-3/4 hybrid winner "
        f"(S3-N5-hyb-nocap / S4-{var}); no new configuration or performance interpretation", IMP)

# ── MOM-002 Broad Momentum — related program, name-count × sector-cap (12) ─────────
for tn in (5, 10, 15, 20):
    add(f"MOM002-v1-N{tn}", "MOM-002 Broad Momentum (related lineage)",
        f"top_n={tn}, no sector cap", FULL + " (n_reb 389)", "breadth selection (rejected)", True, True,
        "materially related momentum name-count trial (breadth). Related-but-distinct program; "
        "included conservatively — owner may rule it a separate lineage (would REDUCE the count, so "
        "requires an explicit scope adjustment, not a silent drop).",
        "research/mom002/mom002_results.json")
for tn in (5, 10, 15, 20):
    for scap in ("none", "0.3"):
        add(f"MOM002-v2-N{tn}-sc{scap}", "MOM-002 Broad Momentum (related lineage)",
            f"top_n={tn}, sector_cap={scap}", "OOS box (n_reb 80)", "breadth+cap selection (rejected)",
            True, True,
            "materially related momentum name-count × sector-cap trial; distinct window from v1",
            "research/mom002/v2_sectorcap_box/mom002_results.json")

# ── Factor-level screen — momentum vs low-vol vs reversal (upstream multiple-comparison, 3) ──
# The upstream screen compared 3 factors and selected momentum. "Missing or uncertain trials must be
# counted conservatively" (owner rule) ⟹ count the 3 named factors, not 1. Overcounting deflates the
# Sharpe more (harder gate) — the safe direction. The exact per-factor sub-config count is not in a
# located artifact; ⚠ FLAGGED — the owner may RAISE it (if each factor had sub-configs) but reducing
# below 3 requires a documented scope/dependence adjustment.
for fac, kept in [("momentum", "SELECTED"), ("low_volatility", "rejected"), ("reversal", "rejected")]:
    add(f"FACTOR-{fac}", "Factor research program (upstream screen)",
        f"factor={fac} ({kept})", FULL, "factor selection (chose momentum)", True, True,
        "upstream factor multiple-comparison; counted conservatively as 3 named factors. ⚠ FLAGGED: "
        "exact per-factor sub-config count not in a located artifact — may be RAISED; reducing below "
        "3 needs a documented scope/dependence adjustment.",
        "factor_research_program (memory) — artifact to be located")


def main() -> int:
    included = [r for r in ROWS if r["included_in_trial_count"]]
    excluded = [r for r in ROWS if not r["included_in_trial_count"]]
    payload = {
        "schema": "momentum_daily.equal_weight_validation.trial_ledger.v1",
        "prereg": "PREREG_EqualWeight_Production_Validation_v1.0.md (§7 D)",
        "conservative_rule": (
            "include every materially related experiment whose result was seen before the next "
            "design choice; exclude only pure mechanical reproductions (documented); effective "
            "count == included count (no dependence discount claimed)."
        ),
        "raw_row_count": len(ROWS),
        "included_trial_count": len(included),
        "excluded_row_count": len(excluded),
        "effective_dsr_trial_count": len(included),
        "flagged_for_owner": [r["trial_id"] for r in ROWS
                              if "FLAGGED" in r["inclusion_or_exclusion_reason"]
                              or "owner may rule" in r["inclusion_or_exclusion_reason"]],
        "rows": ROWS,
    }
    out = Path(__file__).resolve().parent / "TrialLedger_v1.0.json"
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    out.write_text(text, encoding="utf-8")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    print(f"raw_rows={len(ROWS)} included={len(included)} excluded={len(excluded)} "
          f"effective_dsr_trials={len(included)}")
    print(f"flagged_for_owner={payload['flagged_for_owner']}")
    print(f"TrialLedger_v1.0.json sha256={sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
