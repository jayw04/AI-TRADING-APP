"""Research Program registry (P13 — the owner's MOM-001/RNG-001/... convention).

A static catalog of the platform's research programs, each with a permanent ID, investment
philosophy, current status, headline result, and a link to its evidence package. This is what the
Evidence Dashboard surfaces as the "research dashboard" (Momentum 🟢 / Range 🔴 / Multi-Factor 🟡 /
Sector Rotation 🔵), and it is platform IP (citable in the whitepaper / patent).

Pure data + helpers — no DB. New programs are added here as they're chartered.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

Status = Literal["validated", "rejected", "inconclusive", "research", "planned"]

# status -> the dashboard colour the owner specified (Suggestion 10)
STATUS_COLOR: dict[Status, str] = {
    "validated": "green", "rejected": "red", "inconclusive": "amber",
    "research": "blue", "planned": "gray",
}


@dataclass(frozen=True)
class ResearchProgram:
    id: str
    family: str
    philosophy: str
    status: Status
    headline: str
    evidence_doc: str | None = None


RESEARCH_PROGRAMS: tuple[ResearchProgram, ...] = (
    ResearchProgram(
        "MOM-001", "Momentum", "Cross-sectional relative strength", "validated",
        "Sharpe 0.48, 95% CI [0.13, 0.85], p=0.003 (1997-2026, survivorship-free); cost-robust. "
        "Production book (v1.1, vol-scaled).",
        "docs/implementation/TradingWorkbench_P12_Session1_EdgeEvidence_Results_v0.1.md"),
    ResearchProgram(
        "RNG-001", "Range / Mean-Reversion", "Intraday mean reversion", "rejected",
        "First formally-rejected strategy: best config PF 1.271, bootstrap mean-P&L 95% CI "
        "[-$19.74, +$57.53] spans zero; walk-forward PF decays to 0.89. No edge.",
        "docs/implementation/TradingWorkbench_RangeTrader_RejectionEvidence_v0.1.md"),
    ResearchProgram(
        "MF-001", "Multi-Factor", "Value + Quality blend", "inconclusive",
        "Re-tested on survivorship-free SF1 (P14): genuine diversifier (corr -0.09/-0.005), DD "
        "-51%->-40%, but Delta-Sharpe +0.04 CI [-0.35,+0.48] spans zero -> keep Momentum v1.1.",
        "docs/implementation/TradingWorkbench_P14_Session1_MultiFactorRetest_Results_v0.1.md"),
    ResearchProgram(
        "SEC-001", "Sector Rotation", "Sector relative strength", "inconclusive",
        "Verdict B (Diversifier), 2000-2026, n=200. Strongest non-momentum book yet (V1 Sharpe 0.51 vs "
        "momentum 0.39, DD -64.8% vs -76.4%, corr 0.38), but no standalone edge: V1 H1 +0.16 CI "
        "[-0.03, 0.366]. V2 pure baskets confirmed B (H1 +0.04 CI [-0.17, 0.24]; H3 V2~=V1 -0.04 CI "
        "[-0.18, 0.09] -> construction NOT the limiter). Per the pre-registered stopping rule: "
        "construction ARCHIVED; a standalone edge needs a fundamentally different hypothesis.",
        "docs/implementation/evidence/sec_001_v2_pure_baskets/sector_rotation_v2.md"),
    ResearchProgram(
        "LOW-001", "Low Volatility", "Defensive / low-volatility anomaly", "inconclusive",
        "Verdict B (Diversifier/Defensive), full-cycle 2000-2026. Best risk-adjusted book on the platform: "
        "Sharpe 0.59 (vs momentum 0.39, eqw 0.35), maxDD -39.0% = HALF of momentum's -76.4%, Calmar 0.20. "
        "H1 standalone +0.24 CI [-0.029, 0.53] just spans zero (no decisive standalone edge). H2 corr "
        "-0.15 (negative = true defensive diversifier). H3 emphatic: shallower DD than eqw in 5/5 windows; "
        "cost-robust to 50bps. Reverses the #142 negative (that was a narrow-universe artifact). Next: "
        "defensive-sleeve / blend product, or a broader-universe V2 to chase the near-miss standalone edge.",
        "docs/implementation/evidence/low_001_low_volatility/low_volatility.md"),
    ResearchProgram(
        "TREND-001", "Trend Following", "Time-series trend (per-name 200d SMA participation)",
        "inconclusive",
        "Verdict B (Diversifier/Defensive), full-cycle 2000-2026. A defensive participation sleeve: "
        "Sharpe 0.46 (vs momentum 0.39, eqw 0.35), maxDD -46.2% (vs momentum -76.4%) by de-risking to "
        "cash in downtrends (gross falls to 1.5%). H1 standalone +0.11 CI [-0.11, 0.33] spans zero (no "
        "standalone edge); H2 corr 0.871 with momentum (NOT a low-corr diversifier). H3 is the signature "
        "+ key result: per-name trend BEATS the platform's existing portfolio-level regime filter "
        "(maxDD -46.2% vs -61.1%, +14.9pp; Sharpe +0.06), refuting the pre-registered modal "
        "'subsumed -> Rejected' prior. Cost-robust to 50bps. Next: V2 inverse-vol / multi-window "
        "only if a sharper edge or lower correlation is wanted.",
        "docs/implementation/evidence/trend_001_trend_following/trend_following.md"),
    ResearchProgram(
        "PORT-001", "Portfolio Construction",
        "Multi-sleeve ERC: crash-protected equity momentum + cross-asset TSMOM", "validated",
        "'Risk-Balanced Multi-Asset Portfolio' (Combined Book), ONBOARDED from the sibling "
        "claude-trading-view system (reproduce-first). ONBOARDING GATE PASSED 2026-06-27 via "
        "construction-verification (Lifecycle Fidelity 98.8%, 6/6 criteria): the platform's PCE/ERC "
        "reproduces the sibling combined book from its own sleeve return series -- daily-return corr "
        "0.99994, Sharpe 0.9001 vs 0.9015, maxDD 11.66% vs 11.57%, and the ERC blend independently "
        "lands at 0.41/0.59 ~= the pinned 40/60. HONEST VERDICT: crash-protected BETA + "
        "diversification, NOT alpha -- combined alpha t=0.82 insignificant, stock-selection alpha "
        "REFUTED under point-in-time data. SCOPE: this validates the construction engine; the "
        "self-stack (Alpaca total-return + platform momentum) end-to-end data-fidelity port is a "
        "separate tracked study (the harness's --db real mode). Capability Certificate v1.0 "
        "Gate-Passed (L1+L2).",
        "docs/implementation/evidence/port_001/EvidencePackage_PORT-001_v1.0.md"),
    ResearchProgram(
        "MOM-002", "Momentum", "Reshaping a concentrated momentum book (breadth / sector cap)", "rejected",
        "REJECTED (closed 2026-07-02). Q: can RESHAPING a concentrated momentum book improve "
        "risk-adjusted performance? NO on both arms. Breadth (Top-5->Top-20): Sharpe 1.37->1.12, Calmar "
        "1.40->0.96, CAGR +77%->+38% (OOS-confirmed 1.67->1.33) -- breadth buys only a shallower maxDD "
        "(-55%->-40%). Sector cap (30%): costs Sharpe (Top-10/15/20 -0.17..-0.29) WITHOUT recovering "
        "drawdown. Load-bearing finding: Top-5<->Top-20 monthly returns still correlate 0.90 -- widening "
        "the SAME factor does NOT create independent evidence (cf. the three-book redundancy, PR #322: "
        "corr ~1.00, 100% overlap). Conclusion: diversify by combining INDEPENDENT FACTORS, not by "
        "weakening the momentum signal. Caveat: within the available 2025-2026 sector-store universe; a "
        "full-history confirmation is Future Research (Medium), not on the critical path. 2nd preserved "
        "negative alongside RNG-001 -- the platform declines a plausible ENHANCEMENT, not just a strategy.",
        "docs/implementation/evidence/mom_002_broad_momentum/broad_momentum.md"),
    ResearchProgram(
        "FI-001", "Portfolio Engineering",
        "Multi-Factor Interaction & Portfolio Engineering — how validated factors interact & combine",
        "inconclusive",
        "Verdict B (Diversifier, portfolio-level): combining the validated books is a RISK-MANAGEMENT "
        "tool (drawdown reduction), NOT an alpha source. Phases 1-4 + the 4-book sector arm all agree "
        "(no interaction study cleared the paired-Sharpe gate). Phase 1 (Measurement): H1 ordering "
        "confirmed -- MOM<->LOW ~0.22-0.52 (independent, decouples in momentum's drawdown), MOM<->SEC "
        "~0.69 (moderate), MOM<->TREND ~0.90 (redundant); correlation is regime-dependent (rolling-63d "
        "swings -0.16..0.95). Phase 2 (Interaction): every blend cuts drawdown 6-8pp with a POSITIVE but "
        "non-significant Sharpe uplift (CIs span zero) = 'Diversification Confirmed (DD-only)'. Phase 3 "
        "(Allocation): sophistication does NOT pay -- inverse-vol/ERC/min-variance all fail to beat naive "
        "equal-weight (confirmed with 4 books; min-variance decisively worse); the vol-target OVERLAY is "
        "the real lever, halving maxDD but at a large CAGR give-up. Phase 4 (Adaptive): a market-regime "
        "gross overlay (de-risk below the 200d trend) is the best drawdown-managed book (Sharpe 1.17, "
        "maxDD -24% vs mom -38%, keeps more CAGR than vol-target) -- still no Sharpe-CI edge; regime-tilt "
        "and correlation-triggers do not help. RECIPE: equal-weight the books + a market-regime gross "
        "overlay; skip the optimizer. Regime overlay catalogued CAP-020 (drawdown-effective, Sharpe-"
        "neutral, verdict Promising, next: live validation -- NOT 'validated'; validation attempted "
        "2026-07-04 -> Inconclusive (data-gated): the box store's 4-book overlap is only 1.5y bull-only "
        "-- harness ready, blocked on >=4y overlapping history incl. bears). Consumes PORT-001's ERC "
        "engine; live counterpart = Portfolio Analytics Engine (#322). Follow-on: FI-002 (Correlation "
        "Stability, reserved) + a full-history+sector store (the sector arm is recent-window on the box).",
        "docs/implementation/TradingWorkbench_FI001_MultiFactorInteraction_Plan_v0.1.md"),
    ResearchProgram(
        "FI-002", "Portfolio Engineering",
        "Correlation Stability — is factor correlation stable enough to allocate on?", "planned",
        "RESERVED 2026-07-02 (do NOT start yet). FI-001's most interesting finding earns its own research "
        "identity: pairwise factor correlation is regime-dependent (Momentum<->Low-Vol rolling-63d swings "
        "-0.16..0.95), so a static combined book understates tail correlation and a 'diversification "
        "score' is falsely precise without a stability band. Q: can correlation stability / 'correlation "
        "confidence' be measured and used to gate allocation? Start only after enough live paper data "
        "accrues (per the FI-001 review) -- Continuous Evidence Engine is the higher priority first.",
        None),
    ResearchProgram(
        "TV-001", "External Strategy Import",
        "Import test of popular TradingView community strategies", "rejected",
        "REJECTED (program closed 2026-07-04). The platform's first external/community-strategy import "
        "test. Top-3 TradingView strategies by popularity (HalfTrend 398 boosts / Universal-RSI 75 / "
        "Supertrend 33) reconstructed + Strategy-Tested (15m, US-RTH, 0.02%+2tick, $10k; 28 backtests). "
        "HalfTrend + Universal-RSI REJECTED at import (no edge; sign-flip across windows; RSI best case "
        "breakeven +0.5% on SPY). Supertrend kept as candidate TV-001-SUPERTREND -> FULL PRE-REGISTERED "
        "VALIDATION 2026-07-04 (15 symbols, 2023-2026 walk-forward, 10bps, vs buy-and-hold): REJECTED "
        "(Evidenced) -- beats buy-and-hold on 1/15 (both fit-winners MSFT/PLTR fail, PLTR -13.8x vs "
        "holding), best-of-9 ATRxmult settings 13% (no parameter rescues it), ~98 trades/yr cost-bleed, "
        "walk-forward not robust; faint +per-trade signal (CI excludes 0) but loses to holding = "
        "research-yes / deployment-no. Lessons: popularity != edge; symbol selection > strategy choice; "
        "window sensitivity severe; no 100%-equity in promotion tests. Lasting assets = the import->recon"
        "->validation pipeline + the Strategy x Symbol Fit screener (CAP-023). Evidence: "
        "evidence/tv_001_supertrend/TV001_Supertrend_Result_v1.0.md.",
        "docs/implementation/TradingWorkbench_TV001_CommunityStrategyImport_v0.1.md"),
    ResearchProgram(
        "GOVCONTRACT-001", "Event-Driven",
        "Do new federal government-contract awards predict drift in small/mid-cap contractors?", "planned",
        "EAD's first event-driven research program (Quiver Government Contracts, DCAP-007; ADR 0037). "
        "Pre-registered (plan v0.1): a MATCHED-CONTROL benchmark (~20 controls, same sector + mktcap/ADV/"
        "6m-momentum decile +/-1, clean of same-event-type) so the test is residual alpha, not the "
        "sector/size beta that got INSIDER-001 rejected; 20d primary hold + 5/10/60 robustness; bootstrap "
        "excess-return 95% CI must exclude zero; >=100-event floor. Matched-control engine + verdict tree "
        "BUILT + unit-tested (app/altdata/matched_control.py). Verdict DATA-GATED on the deploy gate "
        "(migration + ingest) and the USAspending cross-check calibrating the disclosure lag. No book "
        "until Approved.",
        "docs/implementation/TradingWorkbench_GOVCONTRACT001_Plan_v0.1.md"),
)


def list_programs() -> list[dict[str, Any]]:
    """The catalog as dashboard-ready dicts (id, family, philosophy, status, color, headline, doc)."""
    return [{**asdict(p), "color": STATUS_COLOR[p.status]} for p in RESEARCH_PROGRAMS]


def status_counts() -> dict[str, int]:
    out: dict[str, int] = {}
    for p in RESEARCH_PROGRAMS:
        out[p.status] = out.get(p.status, 0) + 1
    return out
