# Trading Workbench — Strategy Evidence Book (v0.1)

| Field | Value |
|---|---|
| Document | **Strategy Evidence Book** — the flagship P12 deliverable answering *"should we trade this?"* |
| Version | v0.1 (2026-06-20) — investment proof (P12 §1–§3) + operational proof (P11), every claim cited |
| Audience | the owner / a future investor or partner doing diligence |
| Companion | the **Platform Capability Report** (*"why adopt TradingWorkbench?"*) |
| Provenance | each result traces to a tagged experiment id + a committed artifact; results are *reproducible* and, for the live book, *replayable + reconciled* |

> **The thesis in one line.** Trading Workbench has a **real, statistically-significant, cost-robust
> momentum edge**, a **vol-scaling overlay that halves its drawdown at no risk-adjusted cost**, and
> the whole thing runs on an **operationally trustworthy, audit-verifiable** platform — so the
> evidence isn't just *reported*, it's *provable*.

---

## 1. Executive summary

| Claim | Evidence | Verdict |
|---|---|---|
| Momentum carries a real OOS edge | Sharpe **0.48**, 95% CI **[0.13, 0.85]**, **p=0.003** (1997–2026, survivorship-free) | ✅ Validated |
| …robust to transaction cost | Sharpe 0.50 / 0.48 / 0.45 / 0.35 at 5 / 10 / 20 / 50 bps | ✅ Robust |
| …but with a severe drawdown | **−76.4%** max-drawdown (GFC regime negative) | ⚠ The risk |
| Vol-scaling fixes the drawdown | maxDD **−76.4% → −47.2% (+38%)** at Sharpe **0.48 → 0.51** | ✅ → **v1.1** |
| …and holds in the crashes | GFC −65.6%→−31.9% (+51%), COVID −48.6%→−24.0% (+51%) | ✅ Robust |
| Value/quality add a second edge | multi-factor Sharpe +0.23 / DD halved, **but CI overlaps** | 🟡 Inconclusive → SF1 |
| The platform is operationally trustworthy | ADR 0021's 6 properties enforced + tested; 13 CI invariants | ✅ (P11) |

**Recommendation:** trade **Momentum v1.1 (momentum + vol-scaling)**; momentum is the production
edge, vol-scaling is the risk control. Treat the multi-factor question as *open, promising,
data-gated* (acquire SF1 to settle it). The live deployment is operationally proven — pending the
sustained-window attestation.

## 2. Research results (the edge)

**Momentum v1.0 — `EXP-20260620-193645` (`p12-session1-complete`).** Weekly long-only top-quintile
6-1 momentum, equal-weight, top-200 liquidity universe, **1997–2026, survivorship-free (38.99M price
rows, 14,150 tickers incl. delisted)**:

- CAGR **+10.73%** vs equal-weight **+7.74%** (+3.0pp); Sharpe **0.48** vs 0.43.
- **Statistical confidence:** 95% CI [0.13, 0.85], **p=0.003** (circular-block bootstrap, seeded,
  reproducible) — *the edge is not luck.*
- Positive in **6 of 7 regimes** (2010-13 0.89, 2016-19 0.88, 2022-24 1.04, 2024-26 AI 1.01); the
  exception is the **GFC** (−0.25) — momentum's known crash vulnerability.

## 3. Backtests & cost (robustness)

| bps | CAGR | Sharpe | maxDD |
|---|---|---|---|
| 5 | +11.43% | 0.50 | −76.1% |
| 10 | +10.85% | 0.48 | −76.4% |
| 20 | +9.70% | 0.45 | −77.1% |
| 50 | +6.31% | 0.35 | −81.8% |

The edge **survives realistic cost** (Sharpe 0.45 even at 20 bps), degrading only at a punitive 50 bps.

## 4. Walk-forward (stability across regimes)

7 contiguous regime windows, moderately stable; the edge is *not* a single-period artifact (§2/§3
above). The honest weak point is the GFC crash — which §5 (Risk) addresses.

## 5. Risk — and the vol-scaling fix (`EXP-20260620-212614`, `p12-session2-complete`)

The −76% drawdown was the headline risk. The **vol-scaling overlay (v1.1)** addresses it:

| Metric | v1.0 | **v1.1 (vol-scaled 15%)** |
|---|---|---|
| Max drawdown | −76.4% | **−47.2% (+38% reduction)** |
| Sharpe | 0.48 | **0.51 (+0.03)** |
| Calmar | 0.14 | 0.15 |

It **cuts drawdown hardest exactly in the crashes** (GFC +51%, COVID +51%, 2024-26 +59%) and barely
touches calm regimes. A sensitivity grid shows it **enables at *every* target 10–20%** (a risk
*dial*: 10% = −34% DD / +4.8% CAGR; 20% = −57% DD / +8.5% CAGR / Sharpe 0.52). Sector caps were
tested and **rejected** (marginal); the combined book was **redundant** (vol-scaling does the work).

## 6. Multi-factor — open & promising (`EXP-20260621-002659`, `p12-session3-complete`)

Exploratory (FMP, 2021–2026, mega-cap — *not a verdict*): value/quality are **near-uncorrelated with
momentum** (genuine diversifiers), and a momentum+value+quality book showed **Sharpe 1.23 vs 1.00 and
drawdown halved (−21.4% vs −38.8%)** — **but the CI [0.46, 2.00] overlaps**, so it is **Inconclusive**
on the available data. *Decision: keep v1.1; the promising signal justifies acquiring SF1 (deep,
broad, survivorship-free fundamentals) for a decisive verdict.*

## 7. Live paper

Momentum is live on the BFY6 **paper** account (strategy id=2), weekly Mon rebalance, through the
single OrderRouter + full risk engine. Paper proves the **plumbing** (orders route, fills reconcile)
— it is deliberately **not** offered as a performance track record (short window = noise; ADR 0014:
backtests are the edge ground-truth).

## 8. Operational proof (why the evidence is trustworthy) — P11

The platform satisfies **ADR 0021's six-property operational contract**, enforced + tested
(`p11-session1..5-complete`): idempotent · fail-safe · **restart-recoverable** · **reconciled** ·
**replayable** · **self-healing**. Concretely:

- **Replayable** (§4): any automated decision is reconstructed from its audit fingerprint and
  re-verified — *"the audit log is executable evidence."*
- **Reconciled** (§3): broker truth is independently checked against local state, alert-only.
- **Recoverable** (§5): restart-resume is idempotent (no double-act); partial fills self-heal.
- **13 CI invariants** (single OrderRouter, non-bypassable risk gates, immutable hash-chained audit,
  no-LLM-in-order-path, …) make these load-bearing, not aspirational.

The **Operational Readiness Report** is the phase-exit attestation; `p11-complete` is gated on a
**≥30-day all-PASS paper window** (the only piece still accruing).

## 9. Final conclusion

> **Trade Momentum v1.1.** It is a real, cost-robust, OOS-validated edge whose one serious risk —
> catastrophic drawdown — is cut roughly in half by a vol-scaling overlay that costs nothing
> risk-adjusted and protects hardest in crashes. The multi-factor extension is promising but
> data-gated (→ SF1). And uniquely, **every number here is reproducible from a tagged run, and the
> live book's decisions are replayable and reconciled** — the evidence is provable, not asserted.

**Open owner decisions:** (1) set the vol-scaling risk dial (10–20%) and enable v1.1 live;
(2) acquire SF1 to settle the multi-factor question; (3) sign `p11-complete` after the sustained
paper window.

## Appendix — provenance

| Result | Tag / experiment | Artifact |
|---|---|---|
| Momentum edge | `p12-session1-complete` / `EXP-20260620-193645` | `docs/implementation/evidence/p12_s1/` |
| Vol-scaling (v1.1) | `p12-session2-complete` / `EXP-20260620-212614` | `docs/implementation/evidence/p12_s2_*/` |
| Multi-factor (exploratory) | `p12-session3-complete` / `EXP-20260621-002659-mf` | `docs/implementation/evidence/p12_s3_explore/` |
| Operational contract | `p11-session1..5-complete` (ADR 0021) | `docs/runbook/`, `TradingWorkbench_P11_OperationalReadinessReport_v0.1.md` |
