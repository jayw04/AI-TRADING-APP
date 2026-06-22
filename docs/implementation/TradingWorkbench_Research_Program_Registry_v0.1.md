# TradingWorkbench — Research Program Registry (v0.1)

> The single catalog of every research program the platform has chartered — from hypothesis through
> evidence, governance, and (where warranted) production. This is the human-readable mirror of the code
> catalog (`apps/backend/app/research/programs.py`) and the live **Evidence Dashboard** (`/evidence`).
> The code is the source of truth; this doc is the narrative companion the whitepaper and patent cite.

| Field | Value |
|---|---|
| Version | v0.1 (2026-06-21) |
| Source of truth | `apps/backend/app/research/programs.py` + the Evidence Dashboard |
| Convention | Permanent IDs (`MOM / RNG / MF / SEC / LOW / TREND-NNN`) are platform IP — citable in the whitepaper, patent, and customer docs. |

---

## The three-layer product model

The platform is best understood as three layers — a framing customers grasp immediately:

| Layer | What it is | Examples |
|---|---|---|
| **Layer 1 — Methodology** | **Evidence Engineering** — the discipline of producing, governing, and preserving the proof behind every decision | pre-registration, evidence packages, the promotion gate, the stopping rule |
| **Layer 2 — Platform** | **TradingWorkbench** — the operating system that makes the methodology usable | the research engine, registries, risk engine, OrderRouter, audit, dashboards |
| **Layer 3 — Research Programs** | The individual strategies run *through* the platform — each a validated, rejected, or deferred instance | the registry below (`MOM-001` … `TREND-001`) |

Momentum is **Layer 3**, not the product — the *reference implementation* that proves Layers 1–2 work, much as Linux is a reference implementation of an operating system rather than the operating system itself.

## The research lifecycle (standardized phase terminology)

Every program travels the same phases — the terminology used across the whitepaper, the patent, and the codebase:

`Hypothesis → Research → Evidence → Governance → Candidate → Paper → Production → Continuous Evidence`

A program can exit at any phase with a verdict (Approved / Rejected / Inconclusive / Diversifier) — and **every exit is a success**, because Evidence Engineering measures the quality of decisions, not the count of strategies shipped.

---

## The registry

| ID | Philosophy | Phase | Verdict | Headline |
|---|---|---|---|---|
| **MOM-001** | Momentum (cross-sectional relative strength) | Production (paper) | ✅ **Approved** | Sharpe 0.48, 95% CI [0.13, 0.85], p=0.003 (1997–2026, survivorship-free), cost-robust. Live as three vol-target Risk Profiles. |
| **RNG-001** | Range / mean-reversion | Complete | 🔴 **Rejected** | First formal rejection: PF 1.27 (< 1.3 bar); bootstrap mean-P&L 95% CI [−$19.74, +$57.53] spans zero; walk-forward PF decays to 0.89. |
| **MF-001** | Multi-Factor (value + quality) | Complete | 🟡 **Inconclusive** | On survivorship-free SF1: genuine diversifier (corr −0.09/−0.005), DD −51%→−40%, but ΔSharpe +0.04, CI [−0.35, +0.48] spans zero → keep Momentum v1.1. |
| **SEC-001** | Sector Rotation (sector relative strength) | Complete | 🟡 **Diversifier (B)** | Strongest non-momentum book (Sharpe 0.51), but no standalone edge (V1 H1 +0.16 CI [−0.03, 0.366]). V2 pure baskets confirmed B; H3 showed construction is not the limiter → **construction archived** per the stopping rule. |
| **LOW-001** | Low Volatility (defensive) | Research (running) | ⏳ **Pending** | The defensive complement to momentum (strength vs stability). Full-cycle 2000–2026 re-test (prior negative was on a narrow 2016–26 mega-cap window). H1 standalone / H2 diversifier / H3 downside protection. |
| **TREND-001** | Trend Following (time-series trend) | Planned | — **Planned** | Tier-B philosophy (different holding period / turnover). Charter after LOW-001 — then the platform shifts to the **Factor Lab** (new programs become *configuration*, not new scripts). |

**Verdict legend:** Approved (validated standalone) · Rejected (no edge) · Inconclusive (gate held the line) · Diversifier (B — overlay value, not standalone). Colors match the Evidence Dashboard (green / red / amber / amber-blue).

## Score so far

- **6 programs chartered;** 4 resolved, 1 running, 1 planned.
- **1 deployed** (Momentum, live on paper as three Risk Profiles).
- **3 evidence-based "not deployed" decisions** — Range (rejected), Multi-Factor (inconclusive), Sector Rotation (diversifier, not standalone) — each a citable artifact. *Most software can validate; very few can decline.*

## How this evolves

New programs are added to `programs.py` (which the Evidence Dashboard renders live) and reflected here. Per the owner's roadmap, after **TREND-001** the platform stops authoring bespoke research scripts and generalizes into the **Factor Lab**, where a new program is a configuration over the shared evidence pipeline rather than a new document — the natural endpoint of the high reuse % each successive program has demonstrated (SEC-001 ~90%, LOW-001 ~90%).
