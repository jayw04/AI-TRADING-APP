# FI-001 — Multi-Factor Interaction & Portfolio Engineering (Plan v0.1, pre-registered)

| Field | Value |
|---|---|
| Program ID | **FI-001** (permanent — platform IP; citable in the whitepaper / patent / customer docs) |
| Title | Multi-Factor Interaction & Portfolio Engineering |
| Status | **Planning — charter frozen / pre-registered** (no interaction research has run yet) |
| Verdict | **Pending** |
| Owner | Jay Wang (GlobalComplyAI, LLC) |
| Date | 2026-07-02 |
| Family | Portfolio Engineering (bridges Discovery Lab → the Combined Book) |
| Related | MOM-001, LOW-001, SEC-001, TREND-001, MF-001 (the input books) · PORT-001 (the ERC engine this consumes) · ADR 0014 (evidence gate) · ADR 0019 (research engine) · ADR 0026 (programs-as-configuration) |

> **Charter (frozen).** *Determine how validated investment factors interact, complement, or interfere
> with one another, and develop evidence-based portfolio construction methods that maximize
> diversification, improve risk-adjusted returns, and reduce concentration without degrading individual
> factor integrity.*

This is a **pre-registration**. The hypotheses (§1), the evidence gate (§5), and the method (§3) are
frozen *before* any interaction study runs, exactly as LOW-001 / SEC-001 / MOM-002 were. What is written
here is what the data will be allowed to answer — no post-hoc reframing.

---

## §0 — Why FI-001 exists

The platform has spent its research phase *discovering and validating individual factors*: MOM-001
(Approved), and the diversifier books LOW-001, SEC-001, TREND-001 (each Verdict B — real but no decisive
standalone edge). Two recent results made the next question unavoidable:

- **MOM-002 (Rejected, 2026-07-02):** reshaping a *single* momentum book — broadening it or capping
  sectors — does **not** improve risk-adjusted performance, and a Top-5↔Top-20 monthly-return
  correlation of 0.90 proved that widening the *same factor* cannot manufacture independent evidence.
- **The 2026-07-02 daily-report review:** the three live momentum books correlate ~1.00 with 100%
  holdings overlap — the portfolio's risk is concentration, and the fix is **independent factors, not a
  reshaped momentum book.**

FI-001 is the program that answers "so how *do* we combine the validated factors well?" It is the
**bridge between Discovery Lab** (finding and validating individual factors) **and Portfolio
Engineering** (combining validated factors into robust investment capabilities). Today's Combined Book
(PORT-001) is one output of this program; correlation analysis, diversification measurement, allocation
methods, and adaptive construction are the rest — all under one durable program rather than a new ID each
time.

The discipline constraint is in the charter's last clause — *"without degrading individual factor
integrity."* FI-001 **does not re-optimize the underlying factors.** Each book's signal is frozen at its
program's definition; FI-001 studies only how the frozen books *interact and combine.*

---

## §1 — Frozen hypotheses

Pre-registered priors are drawn from each input program's already-published H2 correlation and the
MOM-002 result, so the study can be scored against an honest expectation rather than a moving target.

**H1 — Diversification spectrum (Measurement).** The validated books do **not** form a uniformly
diversified set: some pairs are genuinely independent, others are near-redundant. Pre-registered priors:
MOM↔LOW ≈ **−0.15** (true defensive diversifier, LOW-001 H2), MOM↔SEC ≈ **+0.38** (partial, SEC-001 H2),
MOM↔TREND ≈ **+0.87** (NOT a low-corr diversifier, TREND-001 H2). *Expectation: LOW is the strongest
diversifier of momentum; TREND is largely redundant with it; SEC sits between.* Holdings/sector overlap
corroborate the return correlations.

**H2 — Interaction / blend (does combining help?).** A multi-factor blend **reduces drawdown** versus
standalone momentum; the **standalone-Sharpe uplift is modest and may not clear zero.** Pre-registered:
every prior pairwise blend's ΔSharpe CI *spanned zero* (MF-001 +0.04, SEC-001 +0.09/+0.16, LOW-001) while
drawdown consistently fell — so the modal outcome is *"diversification benefit confirmed (DD ↓), decisive
Sharpe uplift not confirmed."* Momentum + Low-Vol is the most likely pair to clear the bar.

**H3 — Correlation stability (does diversification survive stress?).** Pairwise correlations are
**regime-dependent and rise in equity-market stress** — the "diversification disappears when you need it"
failure mode. FI-001 quantifies *by how much*: rolling 63-/126-day correlations, and the correlation
measured specifically inside each book's worst-drawdown window. *Expectation: LOW↔MOM stays low/negative
even in stress (that is what makes it defensive); the equity-beta pairs (MOM↔SEC, MOM↔TREND) converge
upward.* A blend whose diversification evaporates in the drawdown is worth less than its average
correlation suggests.

**H4 — Allocation (does a principled weighting beat naive?).** A **risk-based allocation** — ERC /
risk-parity / dynamic vol-target / correlation-aware — beats **both** naive equal-weight-of-books **and**
standalone momentum on a risk-adjusted basis (Sharpe and/or Calmar), net of cost. Pre-registered:
ERC/risk-parity reliably *reduce drawdown*; a decisive *Sharpe* win over standalone momentum is the
harder, less-likely half and is where the real evidence lies.

---

## §2 — Inputs (the books; frozen, not re-optimized)

Each input book is consumed at its program's **frozen** definition via the existing survivorship-free
scorers (no re-tuning — protects "individual factor integrity"):

| Book | Score fn (frozen) | Verdict in |
|---|---|---|
| Momentum (12-1) | `app.factor_data.factors.engine.momentum_scores` | MOM-001 ✅ Approved |
| Low Volatility | `app.factor_data.factors.low_vol.low_vol_scores` | LOW-001 🟡 Diversifier B |
| Sector Rotation | `app.factor_data.factors.sector.sector_scores` | SEC-001 🟡 Diversifier B |
| Trend Following | `app.factor_data.factors.trend.trend_scores` | TREND-001 🟡 Diversifier B |
| (Optional) Value/Quality | `app.factor_data.factors.composite.composite_scores` | MF-001 🟡 Inconclusive |

Each book's daily **equity/return series** is produced by `run_momentum_backtest(store, …, score_fn=…)`
— identical construction to the live books — and those return series are the unit of analysis for the
interaction, stability, and allocation work.

---

## §3 — Method (reuse map; nothing rebuilt)

FI-001 is *programs-as-configuration* (ADR 0026) over the existing engine. Concretely:

- **Return series:** `run_momentum_backtest(score_fn=…)` per book → daily equity curves.
- **Correlation & overlap:** `app.research.factor_lab.runner._monthly_corr` / `_returns_corr`;
  holdings/sector overlap via the Jaccard already used in `app.services.portfolio_analytics`
  (the live operational counterpart, PR #322). Rolling correlation = a small new helper over the return
  series (the one genuinely new primitive).
- **Blends:** `_rank_blend_fn` (signal-level) and `_returns_blend` (return-level) from `factor_lab.runner`.
- **Allocation:** `app.research.factor_lab.portfolio.construct_portfolio` + `erc.erc_weights` (the
  PORT-001 ERC engine), plus `weighting=` (`equal_weight` / `inverse_vol` / `risk_parity_diagonal`) and
  the `vol_target_annual` overlay already in `run_momentum_backtest`. Correlation-aware and dynamic
  allocation are new configs over these.
- **Significance:** `app.factor_data.evidence.paired_sharpe_diff_ci` (paired circular-block bootstrap) vs
  standalone momentum; `stability_label` for walk-forward; a cost sweep to 50 bps.

Each phase ships a script under `apps/backend/scripts/` + an evidence package under
`docs/implementation/evidence/fi_001_*/`, seeded and reproducible.

---

## §4 — Research roadmap (owner-specified phases)

**Phase 1 — Measurement.** Rolling correlation, holdings overlap, sector overlap, diversification score
across all validated books. Deliverable: the correlation/overlap/diversification matrix + its stability
profile (answers H1 and seeds H3).

**Phase 2 — Interaction.** Pairwise combinations — Momentum + Low-Vol, Momentum + Sector, Momentum +
Trend, Low-Vol + Trend — each blend vs its standalone components (ΔSharpe CI, drawdown, correlation).
Answers H2.

**Phase 3 — Allocation.** Equal weight · risk parity · equal-risk-contribution (ERC) · dynamic
volatility targeting · correlation-aware allocation. Each vs naive equal-weight and standalone momentum.
Answers H4.

**Phase 4 — Adaptive Portfolio.** The eventual pipeline **Evidence → Factor Interaction → Portfolio
Allocation → Execution** — a regime/correlation-adaptive combined book, gated by the Phase 1–3 evidence.
This is the long-horizon deliverable, not a v0.1 commitment.

---

## §5 — Pre-registered evidence gate & verdict tree

Every comparison is judged on **risk-adjusted** metrics, never headline return, against standalone
Momentum v1.1 and an equal-weight benchmark. A claim of improvement requires a **paired Sharpe-diff
bootstrap CI that excludes zero** (the platform's H1 test), corroborated by drawdown and walk-forward
stability, and robustness to costs up to **50 bps**.

| Outcome | Criterion | Meaning |
|---|---|---|
| ✅ **Combined Book — Approved** | A construction beats standalone momentum on ΔSharpe with a CI excluding zero, DD no worse, cost-robust | A genuine multi-factor edge — promote to a paper Combined Book |
| 🟡 **Diversification Confirmed (B)** | DD materially lower than momentum and correlation-stability holds, but ΔSharpe CI spans zero | The modal, expected result — combine for risk reduction, not alpha; still a live-worthy overlay |
| 🔴 **No Improvement** | No construction reduces DD or improves Sharpe beyond equal-weight | Preserved negative — combining these books adds nothing beyond naive diversification |

As with every program, **whatever the verdict, the evidence package is the deliverable.** A "Diversification
Confirmed" or even "No Improvement" outcome is a success of the method, not a failure.

## §6 — Benchmarks

Standalone Momentum v1.1 (the incumbent) · equal-weight universe (passive) · **naive equal-weight of the
books** (the allocation control — every principled method must beat this to justify its complexity) · the
live Combined Book (PORT-001) as an external reference point.

## §7 — Data caveat (scope honesty)

The **Sector Rotation** arm needs a sector-populated factor store (`tickers.sector`); the local store has
none (0 tickers), so Sector interaction runs on the AWS box store (as MOM-002 v2 did), while
Momentum / Low-Vol / Trend interaction runs anywhere. Where a result depends on the box's recent-window
data limitation (full universe only from 2025), it is labelled as such — no over-generalization.

## §8 — Relationship to PORT-001 (no duplication)

PORT-001 validated the **ERC construction engine** by reproducing an *externally onboarded* combined book
(equity momentum + cross-asset TSMOM) — it proved the *engine*, honestly scoped to "beta + diversification,
not alpha." **FI-001 applies and extends that same engine to the platform's OWN validated factor books**,
and adds the interaction, correlation-stability, and dynamic-allocation research PORT-001 did not cover.
FI-001 is the umbrella research program; the Combined Book is one of its outputs. The live Portfolio
Analytics Engine (PR #322) is FI-001's **operational counterpart** — it already reports correlation /
overlap / diversification on the *live* accounts; FI-001 does the *backtested* research that tells the
allocator what those live numbers should be.

## §9 — Commercial value / reusable capability

FI-001 productizes **Portfolio Engineering** as a platform capability: an evidence-based answer to "given
a set of validated factors, how should a disciplined trader combine them?" — with correlation stability
and diversification as first-class, audited metrics rather than marketing claims. It is positioned to
become a core long-term research program alongside MOM-001, LOW-001, and SEC-001.

## §10 — Research cost / calibration (expected outcomes)

| Phase | Most-likely outcome (pre-registered) | Learning even if "negative" |
|---|---|---|
| 1 Measurement | LOW is the real diversifier; TREND ≈ redundant with MOM | Confirms *which* books are independent — kills wasted blends early |
| 2 Interaction | DD ↓ confirmed; decisive Sharpe uplift NOT confirmed | Same discipline as MF/SEC/LOW — the gate holds the line |
| 3 Allocation | ERC/risk-parity reduce DD; Sharpe win over momentum uncertain | Establishes the best *achievable* combined book on current evidence |
| 4 Adaptive | Long-horizon; gated by 1–3 | The pipeline design, even before a live adaptive book |

*Pre-registered 2026-07-02. Charter frozen. No interaction study has run yet — this document is the
freeze, not the result.*
