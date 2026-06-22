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
        "LOW-001", "Low Volatility", "Defensive / low-volatility anomaly", "research",
        "Pre-registered (v0.2, approved 9.7/10). The defensive complement to momentum (strength vs "
        "stability). Re-tests the low-vol anomaly on full-cycle survivorship-free 2000-2026 data "
        "(a prior study found it negative on the narrow 2016-26 mega-cap window). H1 standalone / "
        "H2 diversifier (expect neg corr) / H3 downside protection. Evidence run in progress.",
        "docs/implementation/evidence/low_001_low_volatility/low_volatility.md"),
    ResearchProgram(
        "TREND-001", "Trend Following", "Time-series trend", "planned",
        "Tier-B philosophy (different holding period / turnover). Charter after LOW-001; then the "
        "platform shifts to the Factor Lab (programs become configuration, not new scripts).", None),
)


def list_programs() -> list[dict[str, Any]]:
    """The catalog as dashboard-ready dicts (id, family, philosophy, status, color, headline, doc)."""
    return [{**asdict(p), "color": STATUS_COLOR[p.status]} for p in RESEARCH_PROGRAMS]


def status_counts() -> dict[str, int]:
    out: dict[str, int] = {}
    for p in RESEARCH_PROGRAMS:
        out[p.status] = out.get(p.status, 0) + 1
    return out
