# Trading Workbench — P12 §3: Advance the alpha (multi-factor book)

| Field | Value |
|---|---|
| Document version | **v0.2 — draft + review fold** (2026-06-20). Data path owner-confirmed (build infra → FMP exploratory → SF1 verdict). v0.2 folds the doc review (`comments.md`): the session split into **three distinct deliverables** (A engineering / B exploratory study / C recommendation), explicit **research states** (Validated/Rejected/Inconclusive/Deferred), a formal **research-debt table**, a **success matrix**, the **research-lifecycle diagram**, the crisp **scientific question**, "re-test"→**exploratory validation**, a **no-optimizer** guardrail, and a required **factor-correlation matrix** output. |
| Date | 2026-06-20 |
| Phase | **P12** — Validation & Results |
| Session | §3 of 4 (Advance the alpha — multi-factor book) |
| Predecessor | P12 §2 (tag `p12-session2-complete`); momentum v1.1 |
| Successor | P12 §4 — Operational-proof window (background) / phase close (Strategy Evidence Book) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Build the **missing multi-factor machinery** (a composite-factor scoring engine + a factor-agnostic backtest), **re-test value/quality on the broadest universe the data supports** (the prior rejection's named gate), and decide — on OOS evidence — whether a momentum + value/quality **multi-factor book** beats momentum alone. Read-only research; **does not change the live strategy** (owner-gated). |
| Estimated wall time | 8–12 hours (composite engine + backtest generalization + fundamentals breadth ingest + the multi-factor study + tests + results doc) — **plus** any FMP ingest wall-time |
| Tag on completion | `p12-session3-complete` |
| Out of scope | See "What this session does NOT do" |

---

## Why this session exists

§1 validated momentum; §2 fixed its drawdown (→ v1.1). §3 asks the **diversification** question:
*is there a second, lowly-correlated source of edge* — value/quality — that improves the book, or
does momentum stand alone? The honest prior answer (Factor Data Acquisition Guide §3) is **"not on
the mega-cap universe"**: on the top-200 liquid names, OOS 2023–26, every value/quality factor was
negative or flat (LS-Sharpe −1.9 to +0.9) while momentum was +1.33 — and they were *negatively*
correlated with momentum (momentum's opposite, not a diversifier). That was explicitly flagged as a
**universe + regime** result, with the named re-test gate: *do value/quality earn their keep **off
the mega-cap universe**?*

§3 answers that — but first it must build the machinery that doesn't exist yet (a composite
multi-factor score + a factor-agnostic backtest), and it must confront a **real data constraint**
(below) that bounds how decisive the answer can be.

### Why this matters (no feature creep)

> **The objective is not to maximize factor count.** It is to determine whether an *independent
> return premium* exists that **improves the existing momentum strategy**. A factor that is real but
> redundant with momentum (or that only works pre-cost) does not make the cut. The session's primary
> asset is the **reusable research infrastructure** — it pays off on every future factor study even
> if value/quality stay inconclusive.

### The scientific question (the hypothesis)

> *Do value and/or quality provide a **statistically significant, out-of-sample, low-correlation**
> return **independent of momentum**, after realistic transaction costs?*

The honest expected answer on the data we have is *probably not decisively, yet* — which is why §3
separates engineering success from research success.

### Research lifecycle (P12's spine — where §3 sits)

```
Idea → Infrastructure → Exploration → Validation → Evidence → Decision → Production → Monitoring
                ▲             ▲                          ▲
             §3 (A)        §3 (B, FMP)            §3 (C) / SF1 (later)
```

### Engineering success ≠ research success (do not conflate)

| Engineering success (this session delivers) | Research success (data-gated) |
|---|---|
| ✅ Composite multi-factor engine | ❓ Value — independent premium? |
| ✅ Factor-agnostic backtest | ❓ Quality — independent premium? |
| ✅ Tests + Research Registry rows | ❓ Composite — beats momentum-only OOS? |
| **Always completable** | **May be Inconclusive on FMP data — that's a valid outcome** |

## ⚠ The load-bearing constraint (read before everything else)

**Fundamentals depth/breadth is the binding limit, not the code.**

- Value/quality need **fundamentals**. The only ingested source is **FMP `/stable`**: ~**5 years**
  of statements, and currently ingested for ~**197 of the top-200** names. Prices (momentum) are
  28.5 yr / 14,150 names survivorship-free; **fundamentals are not.**
- **Sharadar SF1** (deep, broad, survivorship-free fundamentals) is **sample-only** on the current
  key — *not subscribed*.
- Therefore a *broad + long* value/quality re-test (the ideal gate) is **not fully achievable on
  today's data**. The realistically-testable re-test is **broader-universe but still ~5-yr / one-
  regime** (extend FMP ingest to the top-500/1000), which only *partially* satisfies the
  "different regime" intent.

This constraint is the subject of the **single open question** below; it changes §3's scope and may
need owner action (a data subscription), so it is confirmed **before** execution.

## What this session ships — three distinct deliverables

The review's key reframe: §3 is **three different products**, not one — kept separate so software
completion is never mistaken for research completion.

### Deliverable A — Research infrastructure (always completable; owner-mandatory)

1. **Composite multi-factor engine** (`composite.py`) — winsorize+`zscore` each factor, blend
   (**equal-weight**; missing-factor impute/drop), rank. ✅ **built** (`composite_scores`).
2. **Factor-agnostic backtest** — `run_momentum_backtest` gains a pluggable `score_fn` (default =
   momentum, byte-identical to §1/§2) so the §1 harness backtests *any* factor/composite. ✅ **built**.
3. **Tests + Research Registry rows** for the machinery. ✅ **8 tests, ruff/mypy clean**.

### Deliverable B — Exploratory validation (FMP — *current evidence, NOT a verdict*)

4. **Exploratory validation of value/quality on the broader universe** — extend FMP fundamentals,
   re-run the IS/OOS study (IC, LS-Sharpe, decay) **+ a factor-correlation matrix** (momentum ×
   value × quality × composite — *the reason §3 exists*) + a composite-vs-momentum backtest through
   the §1 harness. **Labelled exploratory** (~5-yr FMP, one regime, fundamentals not survivorship-
   free) → *current evidence*, not a verdict.
   - **No-optimizer guardrail:** only **equal-weight** + an **IC-weighted sensitivity** variant — no
     optimizer / parameter search (that is where research bias begins).

### Deliverable C — Research recommendation (governed by the success matrix)

5. **The §3 results doc** — Evidence Package Template + the engineering/research scorecard + the
   factor-correlation matrix + the **success-matrix decision** (below) with an explicit **research
   state** (Validated / Rejected / **Inconclusive** / Deferred) + **confidence**, Research/Decision
   Register rows, a v2.0 evolution row *only if* it decisively clears, and the formal **research-debt
   table**.

## Prerequisites

- **§1/§2 complete**; the evidence harness (`edge_evidence.py` + `evidence.py`) and momentum baseline.
- The factor infra: `factors/fundamental.py` (7 value/quality factors, PIT via `accepted_date`),
  `factors/cross_section.py` (winsorize/zscore/rank), `factors/engine.py` (`momentum_scores`),
  `store.get_fundamentals` (PIT), `scripts/ingest_fmp.py`.
- The FMP key (for any broader ingest); the survivorship-free price store.
- The prior result: Factor Data Acquisition Guide §3 (the mega-cap rejection table).

## Detailed work

### §A — Composite multi-factor engine (`factors/composite.py`)

```python
def composite_scores(store, as_of, *, factors: list[str], weights: dict[str, float] | None = None,
                     n: int = 500, min_names: int = 20) -> pd.DataFrame:
    """Per factor: build the cross-section, winsorize+zscore (existing cross_section). Blend the
    z-scores (equal-weight default; `weights` to override) into a composite `score`; rank. Names
    missing a factor are handled explicitly (mean-impute z=0 or drop — decided + tested). Pure +
    deterministic; raises FactorUnavailable below min_names."""
```

### §B — Factor-agnostic backtest (generalize selection)

Extract the hard-wired momentum selection (`backtest.py` ~line 514) behind a pluggable
`select_fn: Callable[[date], dict[str, float]] | None = None` (default = momentum, so every existing
caller and the §1/§2 runs are unchanged). The §1 harness gains a `--factors mom,value,quality` path
that backtests the composite.

### §C — Exploratory validation (broader universe, FMP)

Extend FMP fundamentals ingest to the broader universe, then re-run the IS/OOS study (the existing
`scripts/factor_research.py` already computes per-factor IC/LS/decay + inter-factor correlation) on
that universe. **Required output: the factor-correlation matrix** (momentum × value × quality ×
composite) — does value/quality *diversify* momentum (low/negative correlation that helps) or is it
just momentum's *opposite* (negative + no help)? **Honest framing:** current evidence, not a verdict.

### §D — Composite backtest + the success matrix

Backtest the composite through the §1 harness vs the momentum-only v1.1 baseline. Map the outcome to
a governance action (not a single pass/fail):

| Outcome (OOS, beyond bootstrap noise, post-cost) | Research state | Action |
|---|---|---|
| Strong, significant improvement | **Validated** | Candidate **v2.0** (owner-gated live decision) |
| Small / marginal improvement | **Inconclusive** | Further research; keep v1.1 |
| No improvement / redundant with momentum | **Rejected** (on this data) | **Momentum stands alone** — keep v1.1 |
| Promising but data-limited (the likely FMP outcome) | **Deferred** | **Acquire SF1** for a decisive verdict |

The honest prior (mega-cap) predicts **Rejected/Inconclusive on FMP**, with **Deferred → SF1** as the
real path to a verdict. A negative finding here is a *result*, recorded — not a failure.

### §E — Results doc + registries + tests

The §3 results doc (scorecard, the exploratory-validation table, the correlation matrix, the composite
backtest, the success-matrix decision + research state + confidence, Research/Decision Registers,
evolution row → **v2.0 only if it decisively clears**), and tests for the composite engine + generalized
selection.

**Research-debt table (formalized, not scattered bullets):**

| Item | Blocking the verdict? | Priority |
|---|---|---|
| **SF1 (deep, broad, survivorship-free fundamentals)** | **Yes** — the decisive value/quality verdict | **High** |
| Capacity / market-impact study | No | Medium |
| Liquidity model | No | Medium |
| Dividend-adjustment validation | No | Low |
| Full-history SPY series | No | Low |

## Manual smoke

1. `composite_scores(store, as_of, factors=["momentum","earnings_yield"])` on a fixture → a ranked
   composite with the expected blend; missing-factor handling deterministic.
2. `run_momentum_backtest(..., select_fn=<composite>)` over a short window → a report; the default
   (no `select_fn`) reproduces the §1 momentum numbers byte-for-byte.

## Walk-away discipline

**≥ 1 hour** for the research (read-only). ⚠ Acting on a "build the multi-factor book" recommendation
by changing the live strategy is a **separate, owner-gated** strategy change (it would be v2.0), not
part of §3's read-only research.

## What this session does NOT do

- **Does not change the live strategy.** §3 produces evidence + a recommendation; a multi-factor v2.0
  going live is a separate gated decision.
- **Does not subscribe to / assume SF1 or any new data vendor** — that is the open-question /
  owner-action item, and a new vendor is an ADR.
- **Does not claim a decisive long-history broad value/quality verdict** the FMP data can't support —
  the honest scope is bounded by ~5-yr fundamentals (the gate's "different regime" is only partly met).
- **Does not touch the order path / risk engine.**

## Open questions — RESOLVED (2026-06-20)

1. **★ The data path → owner-confirmed sequence: (c) → (a) → (b).**
   - **Step 1 (mandatory, now): build the reusable infrastructure** — the composite-factor engine +
     factor-agnostic backtest — and validate on the existing top-200 fundamentals. This is the durable
     deliverable, independent of any data verdict.
   - **Step 2 (worthwhile, exploratory): an FMP-based broader re-test** — extend FMP fundamentals to a
     broader universe and re-run value/quality + the multi-factor book over the ~5-yr FMP window,
     **clearly labelled exploratory / non-decisive** (one regime, fundamentals not survivorship-free).
   - **Step 3 (deferred): the final value/quality verdict** waits for **SF1 (or an equivalent deep,
     broad, survivorship-free fundamentals source)** — a paid subscription + new-vendor ADR (owner
     action), recorded as **research debt**. *"Maximize engineering progress without overclaiming
     research conclusions."*
2. **Composite weighting → equal-weight z-scores** (no in-sample optimization); an IC-weighted variant
   reported as sensitivity only.
3. **Missing-factor handling → drop** for the pure value/quality study; **mean-impute (z=0)** for the
   composite so momentum-only names aren't excluded — report both.

## Notes & gotchas

1. **The machinery is the durable asset.** The composite engine + factor-agnostic backtest outlive
   any single factor verdict and are reused by every future factor study — build them well (mirrors
   the §1 "harness is the asset" note).
2. **The honest prior is a universe+regime result, not "value is dead"** — §3 must hold that nuance:
   the test is whether value/quality diversify momentum *off mega-caps*, and the answer may still be
   no (a legitimate negative finding to record, not a failure).
3. **Fundamentals are not survivorship-free at depth** (FMP ~5-yr) — any value/quality backtest over
   a long window would silently bias; keep the value/quality study within the fundamentals' real
   coverage window and say so.
4. **Reproducible + governed** — same seed → same CIs; §3 runs carry experiment ids + repro metadata
   + a Research Registry row, like §1/§2.
