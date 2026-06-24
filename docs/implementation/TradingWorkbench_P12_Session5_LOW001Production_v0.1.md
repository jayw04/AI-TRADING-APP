# P12 §5 — LOW-001 Low-Volatility Capability Promotion

| Field | Value |
|---|---|
| Session | P12 §5: LOW-001 Capability Promotion / Methodology Transfer (#2) |
| Date | 2026-06-24 |
| Owner | Jay Wang |
| Objective | Promote **LOW-001 (Low Volatility)** from L2 (Validated) toward L4 (Paper) by operationalizing the validated research as a deterministic strategy template — the **second** Methodology-Transfer demonstration (after SEC-001), proving the Evidence Engineering lifecycle is repeatable across *multiple* capabilities, not just the first. |
| What this proves | MOM-001 → SEC-001 → **LOW-001** → TREND-001 all travel the *same* lifecycle: `Research → Evidence → Governance → Paper → Continuous Evidence → L4/L5`. The lifecycle is the product. |
| Acceptance | LOW-001 live on paper (standalone account) for 4+ weeks; operational health clean; correlation direction holds; governance gate signed → L4 recommendation. |

---

## 0. Strategic context: Phase 2 (Demonstrate Repeatability)

Per the SCAN-001 review's three-phase roadmap (`TradingWorkbench_SCAN001_StatusAndNextSteps_v0.1.md` §4a):

1. ✅ **Phase 1** — Freeze Discovery Lab v1.0
2. ⭐ **Phase 2** — Demonstrate repeatability: **SEC-001 → LOW-001 → TREND-001** through the *same* lifecycle
3. 📋 **Phase 3** — Commercialization (whitepaper, patent, UX, SaaS)

SEC-001 was the first transfer (PR #242, merged `8ed2975`). **LOW-001 is the second** — and it is a *different investment philosophy*: where Momentum/Sector are **offensive** (relative strength), Low Volatility is **defensive** (own the calmest names). That makes it the strongest diversifier candidate and the cleanest demonstration that the methodology, not the signal, is what transfers.

Like SEC-001, LOW-001 is uniquely ready to promote:
- **Research Complete, verdict frozen** (no new variants until repeatability is proven).
- **All inputs known** (−trailing 252-day realized vol, top-quintile equal-weight, 200-name universe).
- **No parameters to tune** — construction is the validated V1 (the no-overfit clause).

---

## 1. LOW-001 overview

| Property | Value |
|---|---|
| **Program** | LOW-001 — Low Volatility |
| **Research verdict** | 🟡 **Diversifier / Defensive (B)** — strong defensive sleeve, no standalone edge |
| **Key metrics** | Sharpe **0.59** (vs MOM 0.39, EW 0.35); maxDD **−39.0%** (vs MOM −76.4%, EW −69.2%); Corr **−0.153** with momentum |
| **H1 (standalone)** | ΔSharpe vs EW **+0.24, 95% CI [−0.029, 0.53]** → spans zero (no standalone edge) |
| **H2 (diversifier)** | corr(MOM, LowVol) **−0.153**; blend ΔSharpe +0.10, CI [−0.165, 0.359] |
| **H3 (downside protection)** | maxDD **+37.4%** shallower than momentum; shallower than EW in **5/5** walk-forward windows — the low-vol signature |
| **Signal** | −(trailing **252-day** realized daily-return volatility), point-in-time |
| **Construction** | top-quintile (lowest-vol **20%**), equal-weight; weekly Monday rebalance |
| **Universe** | same top-200 liquidity candidates + SPY (regime filter) |
| **Evidence** | `docs/implementation/evidence/low_001_low_volatility/` (EXP-20260622-013311-low001, full-cycle survivorship-free 2000–2026) |

**Why now:** All research is done, on the *proper* full-cycle survivorship-free window (2000–2026) — the test that **reverses** the narrow 2016–2026 mega-cap negative of PR #142. LOW-001 is promoted as a **standalone paper capability** for operational validation and to measure its diversification against the live momentum books independently first (the Evidence-Engineering way of handling a diversifier).

**Low Volatility ≠ Volatility Targeting** (a distinction customers will confuse): LOW-001 changes **stock selection** (which names); the shipped v1.1 vol-scaling overlay changes **position sizing** (how much). They are complementary; the overlay ships **OFF** here so the *selection* signal is proven in isolation.

---

## 2. Architecture: LOW-001 from research to continuous evidence

```
LOW Research (validated, full-cycle 2000–2026)
       ↓
Frozen Parameters (−trailing 252d realized vol, top-quintile 20%, 200-name universe)
       ↓
factors/low_vol.py::low_vol_scores  (reuses backtest._trailing_vol — same primitive the research used)
       ↓
FactorAccessor.low_vol_scores  (sandboxed, read-only, PIT-clamped)
       ↓
low_volatility.py  (pure code, no broker/DB/LLM)
       ↓
OrderRouter (ADR 0002) → Risk Engine (ADR 0005; pending-aware gates ADR 0025)
       ↓
Paper Deployment (standalone account)
       ↓
Continuous Evidence (live_evidence.py) → Governance Review (4-week) → L2→L4 recommendation
```

---

## 3. What was built (this session)

| File | Action | What |
|---|---|---|
| `apps/backend/app/factor_data/factors/low_vol.py` | **NEW** | `low_vol_scores(store, as_of, …)` — the factor analog of `momentum_scores`; score = −(trailing realized vol). **Reuses `backtest._trailing_vol`** (the exact primitive the research + factor-agnostic backtest used) so the promoted book cannot drift from its evidence. |
| `apps/backend/app/factor_data/accessor.py` | MODIFY | Adds `FactorAccessor.low_vol_scores(...)` (lazy import → keeps the backtest module out of the base sandbox import path). Read-only, PIT-clamped, mirrors `momentum_scores`. |
| `apps/backend/strategies_user/templates/low_volatility.py` | **NEW** | `LowVolatility` strategy (1.0.0). Top-quintile lowest-vol, equal-weight, weekly Monday rebalance. Self-contained (not subclassing MomentumPortfolio); reuses the SEC/MOM discipline: regime filter, once-per-week storm guard, sell-before-buy, turnover threshold, optional vol-scaling (OFF). Daily-overlay machinery deliberately omitted (no schema↔code drift). |
| `apps/backend/tests/strategies/test_low_volatility_template.py` | **NEW** | 11 tests: schema parity, frozen defaults, cadence + storm guard, top-quintile `ceil(N·q)` selection, equal-weight sizing, SPY exclusion, sells-on-exit, factor-unavailable HOLD, regime→cash, rejection-logged. |
| `apps/backend/tests/factor_data/test_low_vol.py` | **NEW** | 3 tests for the engine: calmest-first ranking, determinism, `FactorUnavailable` on a thin cross-section (purpose-built volatile store). |
| `apps/backend/tests/factor_data/test_accessor.py` | MODIFY | Adds `low_vol_scores` to the pinned read-only accessor surface. |
| `apps/backend/tests/test_adr_0002_invariant.py` | MODIFY | Allowlists the template (`ctx.submit_order` = the sanctioned OrderRouter path). |

**Faithfulness (no parameter tuning):** the held-count uses the same `max(1, ceil(N · top_quantile))` rule as `run_momentum_backtest`; the vol window (252d), quintile (0.20), equal-weight, and 200-name universe are all inherited from the validated V1. No per-name cap, no pruning — those would be construction changes the Methodology-Transfer discipline forbids.

---

## 4. Pre-registration (operational validation hypotheses)

Per ADR 0014, short-term P&L is not evidence. The live-window hypotheses are operational/structural (none reference Sharpe or P&L targets):

- **H1 (Execution Health):** all rebalances fire on schedule; zero failed orders within the risk envelope; zero spurious breaker trips attributable to LOW-001; zero reconciliation mismatches.
- **H2 (Structural Correctness):** each rebalance holds ≈ the lowest-vol quintile, equal-weight; weights sum to ≤100%; the market proxy (SPY) is never held.
- **H3 (Correlation Direction):** Pearson corr(LowVol daily returns, MOM daily returns) stays **low/negative** (research −0.153; flag if it drifts persistently positive).
- **H4 (Operational Repeatability):** 4 weeks of continuous evidence, daily snapshots captured, risk audits clean, OrderRouter handles MOM + SEC + LOW without crosstalk (ADR 0002).

---

## 5. Success criteria (Governance Gate)

Phase-2 transfer #2 is proven when: CI green + ruff/mypy clean (✅ this session); first rebalance fires with no crashes; operational health 100% clean over 4 weeks; positions match the lowest-vol quintile; correlation direction holds; governance gate signed → **L2 → L4** recommendation.

**NOT success criteria:** Sharpe/DD matching research exactly, or any P&L target (4 weeks is too short — ADR 0014).

---

## 6. Activation (owner-gated — NOT done in this session)

Activation touches the live paper system and is owner-gated. Prerequisites:
- A **new standalone Alpaca paper account** (distinct from MOM-001's three books and the Range sandbox) for clean attribution + independent risk caps — requires owner-supplied paper credentials.
- DB registration: `name=low-volatility`, `code_path=templates/low_volatility.py`, status `IDLE`, schedule `0 14 * * mon`, 201 symbols (top-200 + SPY).
- Backend rebuild + restart (the image drifts from `main`) → `/start` on the paper account.
- First rebalance would target **Monday 2026-06-30 14:00 UTC**.

Activation is registered as the next owner action; this session ships only the validated, tested template (CI-green) — the same boundary as SEC-001 #242.

---

## 7. Status / test results

- ✅ 11 template tests + 3 engine tests + accessor surface + ADR-0002 invariant — all pass locally.
- ✅ ruff clean; mypy clean (`low_vol.py`, `accessor.py`).
- ⏳ Full CI (`mypy app`, all invariants) on the PR.
- ⏳ Activation (owner-gated) → 4-week accrual → `..._LOW001Production_Results_v0.1.md` with the live evidence + L4 verdict.

**Then:** LOW-001 paper completes the second transfer → **TREND-001** is the third (closing the initial catalog), after which Phase 3 (commercialization) begins.
