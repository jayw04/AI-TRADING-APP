# Trading Workbench — Strategy Development Roadmap (v0.1)

| Field | Value |
|---|---|
| Document | **Strategy Development Roadmap** — what strategies we build, in what order, and the evidence gate every one must clear before paper/live. |
| Version | v0.1 (2026-06-21) — from the owner's strategic review (`comments.md`, post-P14/P13.5). |
| Source | P13 Direction v0.3 §9; the P14 multi-factor verdict; the P13.5 Risk Profiles activation. |
| Governing | **ADR 0014** (backtests = primary eval ground-truth) · **ADR 0019** (Research Engine, read-only/advisory) · activation cooldowns (ADR 0005). |

---

## 0. Principle

**Strategies prove the platform; they are not the product.** The platform is an *Evidence Engineering
Platform* whose moat is that it can **discover, validate, *reject*, and operate** strategies under one
governance framework (P14 proved the "reject"). So we add strategies that demonstrate **different
investment *philosophies*** — not more variants of one — and **every** strategy earns paper/live only
by clearing the same evidence gate.

> Build for *philosophy diversity*, not factor proliferation. Momentum chooses **what**; sector
> rotation chooses **where**; mean-reversion / trend are **different alpha classes**.

## 1. The evidence gate (every Tier-B strategy clears this before paper)

The discipline P14 applied to multi-factor — applied to every candidate:

1. **OOS backtest** on the survivorship-free, point-in-time store (no look-ahead).
2. **Walk-forward** across multiple regimes (consistency, not one lucky window).
3. **Bootstrap confidence intervals** on the edge (the decisive test: does the advantage exclude zero?).
4. **Evidence package** — a cited results doc (`script → JSON → Markdown`), reproducible (seed + repro metadata).
5. **Governance review** — the promotion gate (`app/research/promotion`) emits a verdict; owner decides.
6. **Only then** → paper account (its own user+account, P5 §7) → the 90–180-day evidence window → live.

A **negative** result is a *success* (it's recorded and the strategy is declined) — that is the moat.

## 2. Tiers

| Tier | Meaning | Strategies | State |
|---|---|---|---|
| **A** | Validated → the **first commercial offering** | Momentum **Balanced 15%** · **Conservative 10%** · **Growth 20%** | ✅ **LIVE on PAPER** (2026-06-21); accruing the evidence record |
| **B** | Research candidates — build, gate, then paper | **Sector Rotation** · **Low Volatility** · **Trend Following** · **Range / Mean Reversion** | research-track (see §3) |
| **C** | **Wait — P14 already answered** | Value · Quality · Dividend · Growth · AI-generated factors · alternative data | deprioritized |

**Explicitly NOT building now:** another momentum variant, another value/quality variant — they add
little confidence and don't broaden the philosophy story.

## 3. Research track — build order

Momentum ✅ → Risk Profiles ✅ → **Range (in progress)** → **Sector Rotation (next)** → **Low Vol
(next)** → **Trend Following (next)** → **Factor Lab (continuous)**.

### 3.1 Range Trader / Mean Reversion — **Strategy #2** (in progress)
- **Why:** demonstrates the platform supports **multiple alpha classes** (momentum/trend ↔
  range/mean-reversion). Strong marketing, not an outperformance bet.
- **Status:** strategy code exists (idle, `Range Trader NVDA/AAPL`); **NOT paper-traded** — must clear
  the §1 gate first (OOS / walk-forward / bootstrap / evidence package / governance). This is the
  owner's Priority 2.

### 3.2 Sector Rotation — **next new philosophy** (owner's favorite)
- **Why:** momentum picks *what*, sector rotation picks *where* — genuinely complementary; customers
  and institutions understand it immediately; broadens the platform beyond single-name stock selection.
- **Build:** sector-level momentum/relative-strength signal over sector ETFs (or the SEP `sector`
  classification already in the store), through the factor-agnostic backtest (`score_fn`) + the §1 gate.

### 3.3 Low Volatility — **institutional, infra-light**
- **Why:** an institutionally recognized factor, a *different* risk philosophy, and **the platform
  already has volatility infrastructure** (vol-scaling overlay, realized-vol estimation) — much code
  exists. Likely easier to validate than value.

### 3.4 Trend Following — **different holding period / turnover**
- **Why:** institutional pedigree; a different time-scale and turnover profile than weekly momentum —
  widens the philosophy spread.

### 3.5 Factor Lab — **continuous**
- The SF1-backed composite engine (P14) stays the substrate for factor studies. **SF1 = supporting
  infrastructure now, not a primary driver** (don't buy more SF1 history unless a specific study needs
  it — P13 Direction v0.3 §9.4).

## 4. The two-track relationship

| Platform Track (never stops) | Research Track (this doc) |
|---|---|
| Evidence Engine · Governance · Operations · AI · Reporting · Patent · Product · Commercialization | Momentum → Risk Profiles → Range → Sector Rotation → Low Vol → Trend Following → Factor Lab |

The Platform Track makes every Research-Track outcome *legible, reproducible, and sellable*. New
strategies feed the platform's "look what it can validate (and reject)" story.

## 5. What this roadmap deliberately does NOT do

- Chase a bigger backtested number on momentum (P14 settled the production book at v1.1).
- Paper-trade Range / Sector / Low-Vol / Trend before they clear the §1 gate.
- Treat strategy *count* as the goal — *philosophy diversity under governance* is the goal.
- Buy more SF1 history speculatively (it has achieved its purpose).

## 6. Open items for the owner

- Confirm the Tier-B **order** (this doc: Range → Sector Rotation → Low Vol → Trend Following).
- Which gets the **first** dedicated research session after the live evidence record is underway —
  recommend **Range Trader** (Priority 2; code already exists, just needs the evidence package).
- Universe + benchmark for Sector Rotation (sector ETFs vs the SEP sector classification).
