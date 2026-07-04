# CAP-022 — Crash-Insurance / Tail-Hedge Overlay — Charter v0.1

| Field | Value |
|---|---|
| Status | **Planned · Promising** (spun out of CAP-020, 2026-07-04) |
| Origin | FI-001 Phase 4 `regime_gross` mechanism — the SAME 200d-trend gross de-risk that CAP-020 tested |
| Why | CAP-020 was **Rejected as a Calmar/return improver** (confirmed survivorship-free), but the mechanism **reproducibly cut crash drawdowns ~13-15pp** (COVID 2020, 2022 bear). That is a tail-hedge result, wrongly judged by a return-improver bar. |
| Reuses | The deepened **survivorship-free** factor store + `scripts/cap020_regime_validation.py` primitives (regime gate, cost model, block bootstrap, per-environment split) |

## The question (deliberately different from CAP-020)

Not *"does it improve Calmar overall?"* (answered: no) but:

> **Does it reduce crash/tail loss enough to justify its cost-of-carry in normal markets?**

A tail hedge is *supposed* to lose a little in calm regimes and pay in crashes; judging it on pooled
risk-adjusted return (as CAP-020 did) structurally rejects any hedge. CAP-022 judges it as insurance.

## Acceptance criteria (owner-specified)

| Category | Metric |
|---|---|
| **Crisis protection** | MaxDD reduction during stress regimes (2020/2022-like) |
| **Tail protection** | CVaR(5%) / worst-month improvement |
| **Cost of carry** | CAGR drag in calm/bull regimes (must be *bounded*) |
| **Timing quality** | Regime-signal false positives / false negatives |
| **Deployability** | Reduces live risk without excessive return sacrifice |

**Validated as crash insurance if:**
- materially reduces drawdown in 2020/2022-like stress regimes,
- improves worst-month or CVaR,
- has **bounded** cost-of-carry in calm regimes,
- works across parameter sweeps (SMA × gross),
- does **not** require curve-fit timing (robust regime signal, no look-ahead).

## What a CAP-022 study would build (not this session)

- Split returns into **stress vs calm regimes** (not just chronological IS/OOS) and measure the overlay
  separately in each — the crisis-protection and cost-of-carry numbers are the headline, not pooled Sharpe.
- **Tail metrics** (CVaR, worst-month, ulcer/Calmar *within* stress windows) as the primary lens.
- **Cost-of-carry budget**: define an acceptable calm-regime CAGR drag (e.g. ≤ X bps/yr) as the price of
  the hedge, and test whether crash protection clears it.
- **Timing-quality** analysis: how often the 200d gate de-risks into a false alarm vs a real crash, and
  the P&L of each.
- Consider a **partial/scaled** overlay (e.g. gross 0.7 not 0.5, or vol-scaled) to cut carry while keeping
  crash protection — the environment data already hints the milder de-risk (g=0.7) has better Calmar.
- Evaluate on the **survivorship-free** store (already deepened).

## Out of scope for the charter
- No live/paper deployment. A Validated-as-insurance result makes it *eligible* (then Continuous Evidence).
- Distinct from the live ADR-0020/0022 vol-target overlay (a different, continuous mechanism).

## Prior evidence (from CAP-020, both runs)

| Environment | ΔMaxDD | ΔCalmar |
|---|---|---|
| covid_2020 | +14.7 pp | +0.25 |
| bear_2022 | +12.2 pp | −0.02 |
| bull_2023_24 | +1.1 pp | −0.06 |

This is the promising signal CAP-022 exists to evaluate rigorously. See `CAP020_Validation_v1.2.md`.

_v0.1 — 2026-07-04. Charter only; the study is Planned, not started._
