# PORT-001 — Crash-Protected Multi-Asset Portfolio Capability _(Combined Book · PAPER2)_

_Last updated: 2026-06-26 (lever 1 researched — §6.1 + §11 #1; capability framing + 2nd-round review
(9.95/10) folded from `comments.md` — current/target tables, lifecycle status, ProgramSpec mapping,
Part A/B split).
The flagship paper strategy: two independently-built sleeves (crash-protected equity momentum +
cross-asset trend) blended at equal-risk-contribution and governed by a correlation-regime overlay
and a live risk stack. This doc mirrors `Docs/Insider Strategy.md`: architecture, validation, live
state, honest assessment, and an improvement roadmap for review._

> **Product framing.** This is a **risk-managed, multi-sleeve beta product** — a crash-protected,
> diversified trend book — **not an alpha engine**. Its demonstrated value is **drawdown reduction
> and risk-adjusted return**, achieved by construction (diversification + de-risk-only exposure
> scaling), not by statistically significant stock-selection skill. Read §6 and §10 before treating
> any Sharpe number as "edge."
>
> **The real product is the construction framework.** Reviewer's framing (adopted): the value isn't
> momentum, cross-asset, or ERC individually — it's **"a disciplined framework for constructing and
> managing diversified portfolios with explicit drawdown control."** The sleeves are interchangeable
> inputs; the discipline is the asset. _Naming under consideration (decision pending — affects title/
> filename): Adaptive Diversified Portfolio · Crash-Protected Multi-Asset Portfolio · Risk-Balanced
> Multi-Asset Portfolio. Current working title kept until you choose._

---

## Capability framing — TradingWorkbench (PORT-001)

> _Folded from the 2026-06-26 owner review (`comments.md`): present this not as a standalone strategy
> but as a platform **capability** with a full research → validation → governance → execution →
> continuous-evidence lifecycle._
>
> **⚠ Current-vs-target honesty.** This book is **today implemented in the sibling `claude-trading-view`
> system** (its own scripts + risk stack + Windows-Task orchestration), **not** yet as a TradingWorkbench
> Factor-Lab ProgramSpec routed through the OrderRouter / risk engine / Evidence Engine. The framing
> below is the **target**; rows/items marked _(target)_ describe the post-migration state, not current
> reality. Asserting integration that doesn't exist would violate the same evidence discipline this book
> models in §6.4.

**Capability metadata**

| Field | Value |
|---|---|
| Capability ID | **PORT-001** (proposed; not yet in the Research Program Registry) |
| Program type | Portfolio Construction (multi-sleeve ERC + crash/correlation overlay) |
| Capability class | **Portfolio Construction** (registry classes: Factor · Portfolio Construction · Event-Driven · Discovery · Execution · Risk) |
| Investment style | Diversified trend / crash-protected beta |
| Expected role | Core portfolio (risk-managed beta + diversification) |
| Return driver | Diversification + risk management — **not** primary alpha (§6.3) |
| Risk profile | Medium |
| Data dependencies | Sharadar DAILY (equity momentum) · Yahoo + `^VIX` (cross-asset) · Alpaca (execution) |
| Current status | **Paper capability — sibling system** (PAPER2, execution ON) |
| Capability level | Production candidate _(pending platform migration)_ |
| Governance | Approved for paper (sibling); not yet under Workbench governance / Evidence Engine _(target)_ |
| Continuous evidence | Active via sibling monitors (§9); Workbench Continuous Evidence _(target)_ |

**Two capabilities in one book (review #8 — the key distinction).** Separate them:
- **Investment capability** — *Crash-Protected Multi-Asset Portfolio* (this specific book).
- **Platform capability** — a reusable **Portfolio Construction Engine** (multi-sleeve ERC + de-risk-only
  overlay + look-through risk model) that **MOM / LOW / SEC / INSIDER could all reuse**. The engine is the
  durable, more valuable asset; the sleeves are interchangeable inputs — the doc's own "the real product
  is the construction framework."

**Research provenance** (honest — validation is *mixed*, per §6):

| Stage | Status |
|---|---|
| Research complete | ✓ |
| Independent reproduction | ✓ sibling backtests — **not** yet an independent *Workbench* reproduction |
| Statistical validation | ◑ **Mixed** — crash-protection + diversification validated; **stock-selection alpha REFUTED under PIT (§6.4)**; combined α insignificant (t = 0.82) |
| Governance review | ✓ sibling · _(target: Workbench governance gate)_ |
| Paper promotion | ✓ PAPER2 live |
| Continuous monitoring | Running (§9) |

**Lifecycle & platform migration (target).** The path that would make the framing above literally true:
`Research → ProgramSpec (Factor Lab, ADR 0026) → Evidence Package → Capability Registry (PORT-001) →
Promotion gate → Paper capability → Production capability → Continuous Evidence.` Concretely: **port the
sibling two-sleeve ERC construction into Factor Lab as a `PORT-001` ProgramSpec**, so it reuses
`run_program`, the bootstrap/evidence engine, the Registry, and (for any Workbench-side execution) the
single OrderRouter + risk engine. Until then the book is sibling-native and this doc is its capability
*spec*, not its implementation. _(Platform-integration roadmap item — distinct from the §11 research
levers; see §12.)_

**Current vs target at a glance** (migration status, review-2 #2):

| Dimension | Current | Target |
|---|---|---|
| System | Sibling `claude-trading-view` | TradingWorkbench |
| Construction | Native scripts | Factor-Lab **ProgramSpec** (ADR 0026) |
| Validation | Sibling backtests | **Evidence Engine** (bootstrap + Evidence Package) |
| Execution | Standalone executor | **OrderRouter** + risk engine (ADR 0002) |
| Monitoring | Local monitors (§9) | **Continuous Evidence** (Evidence Dashboard) |
| Registry | This doc | **Capability Registry** (PORT-001 entry) |

**Capability lifecycle status** (where it *actually* is today, review-2 #3):

| Phase | Status |
|---|---|
| Research | ✓ |
| Reproduction | ✓ (sibling) |
| ProgramSpec (Factor Lab) | Planned |
| Evidence Package | Planned |
| Registry entry | Planned |
| Paper capability | ✓ Running (sibling) |
| Platform migration | Not started |

**Platform dependencies _(target — PORT-001 is built on platform services, not standalone)_** (review-2 #1):

| Depends on | Purpose | Status |
|---|---|---|
| Factor Lab | ProgramSpec execution (`run_program`) | _(target)_ |
| Evidence Engine | Statistical validation + Evidence Package | _(target)_ |
| Risk Engine | Portfolio/position limits (ADR 0002) | _(target)_ |
| OrderRouter | Single-dispatch execution | _(target)_ |
| Continuous Evidence | Monitoring → Evidence Dashboard | _(target)_ |

**ProgramSpec mapping _(target, ADR 0026)_** (review-2 #5) — how the book becomes Factor-Lab configuration:
`PORT-001 ProgramSpec → Sleeve A (crash-protected momentum) + Sleeve B (cross-asset TSMOM) → ERC portfolio
construction + de-risk overlays → Evidence Package`. Today these are sibling scripts (§2); the migration
(§12 Part B) expresses them as a ProgramSpec.

**Platform dependency map (current).** Sharadar DAILY → equity-momentum sleeve · Yahoo + `^VIX` →
cross-asset sleeve · ERC optimizer + crash/correlation overlays → unified book · Alpaca → execution ·
sibling risk stack (§9) → monitoring. _(Target: Factor Lab → ProgramSpec → Risk Engine → Execution →
Continuous Evidence, all platform-native.)_

---

## 0. At a glance (one-page dashboard)

| Metric | Value |
|---|---|
| **Status** | Live paper trading (PAPER2, execution ON) — flagship |
| **Account** | Alpaca PAPER2 = `PA3344TNRFYD` ($100k, restarted 2026-06-24) |
| **Construction** | 2 sleeves @ ERC ≈ **40% equity-momentum / 60% cross-asset** |
| **Book size** | ~28 positions (20 stocks + 8 asset-class ETFs); gross ~70% / cash ~30% |
| **Combined Sharpe** | **0.84** (vs SPY ~0.6, 60/40 ~0.7) |
| **Combined MaxDD** | **−11.9%** (vs equity-only ~−23.5%) · Calmar ~0.52 |
| **Factor alpha** | **+1%/yr, t = 0.82 — not significant** (β: mkt 0.28, mom 0.22, size 0.18; R² 0.67) |
| **What's actually validated** | Crash protection + diversification; **NOT** standalone stock-selection alpha (refuted under PIT — §6.4) |
| **Diversification regime** | **AMBER** — sleeve corr 1y +0.68, 60d +0.77 and rising (the core thesis is **weakening**) |
| **Hidden risk** | Equity sleeve = 13% of capital but **~60–89% of risk** (look-through, §8) |
| **Role** | Crash-protected beta + diversification, sized and disclosed honestly |

---

## 1. Thesis

Two independently-validated return streams, blended so neither dominates risk:

- **Sleeve A — crash-protected equity momentum.** 12-1 cross-sectional momentum on a survivorship-
  clean US stock universe, tilted long-only with position/sector caps, then scaled by a **de-risk-
  only** crash engine (daily vol-target + a VIX/breadth regime cut). The engine roughly **halves the
  2008 drawdown** while holding Sharpe.
- **Sleeve B — cross-asset time-series momentum.** Long/flat 12-1 trend across 8 asset-class ETFs,
  risk-parity weighted and portfolio vol-targeted. Historically a **genuine crash diversifier**
  (positive in 2008 & 2020), low correlation to the equity sleeve.

Blended at **equal-risk-contribution (~40/60)**, the combined book beats SPY and 60/40 on risk-
adjusted return *and* recovery, with materially lower drawdown than equity alone.

**Bottom line:** the win is **risk management** (diversification + crash de-risking), not alpha.
Factor regression on the combined book shows **insignificant** residual alpha, and the equity sleeve's
earlier alpha headline **did not survive point-in-time data** (§6.4). Treat it as crash-protected
beta. The one structural worry is that the diversification engine — the entire reason the book works
— is **weakening** as the two sleeves become more correlated (§6.1).

---

## 2. Where it runs (infrastructure)

| Component | Detail |
|---|---|
| **Broker account** | Alpaca **PAPER2** = `PA3344TNRFYD` (dedicated; restarted on a fresh $100k acct 2026-06-24). Hard PAPER-only guard. |
| **Book builder** | `scripts/portfolio_live.py` — combines both sleeves → `portfolio_live_book_<date>.json`. DRY by itself. |
| **Equity sleeve** | `scripts/momentum_live.py` + `scripts/momentum_crash.py` (reuses `factor_backtest.py` so live can't drift from research). |
| **Cross-asset sleeve** | `scripts/cross_asset_momentum.py` (8 ETFs, Yahoo total-return bars + `^VIX`). |
| **Executor** | `scripts/portfolio_execute.py` — target book → Alpaca orders (bands, no-leverage cap, dedicated sweep). |
| **Risk/monitor stack** | `correlation_monitor.py`, `portfolio_risk.py`, `portfolio_riskmodel.py`, `portfolio_reconcile.py`. |
| **Orchestration** | `scripts/portfolio_guard.ps1`, Windows Task **"Portfolio Rebalance"**, weekdays **~07:00 ET** (early — the SEP fetch + book build takes tens of minutes), queues market DAY orders to the 09:30 open. |
| **Universe pin** | `equity_universe_pin.json` (2835 mid+large+mega symbols, pinned 2026-06-16) via `pin_universe.py`; `UNIVERSE_PIN=0` bypasses. |
| **Alerts** | ntfy.sh `strategy-notify` (book-build failure, correlation regime, risk breach). |
| **Config** | `portfolio.config.json`. |
| **Logs** | `logs/portfolio_guard.log`. |

---

## 3. How it works, end to end

### 3.1 Sleeve A — crash-protected equity momentum (`momentum_live.py` + `momentum_crash.py`)
1. **Signal:** 12-1 cross-sectional momentum (lookback 252d, skip 21d) over the pinned mid/large/mega
   universe, via `factor_backtest.build_cross_section()` (research parity).
2. **Tilt:** `factor_compute.tilt_weights()` — long the top ~40% of the momentum universe, **per-name
   cap 4%, sector cap 25%**.
3. **Top-N + replacement buffer:** cap to `book_names` (20) for a small account; keep a held name until
   it drops past rank `book_names + book_buffer` (= 25). Validated 2026-06-18: buffer 5 cuts turnover
   ~21% and lifts top-20 Sharpe 0.796 → 0.805.
4. **Crash engine (de-risk only, never > 1.0)** — `momentum_crash.py`:
   - **L1 vol-target:** EWMA(halflife 21) of the held book's daily vol → `g_vol = min(1, 0.12/σ̂)`.
   - **L3 regime cut:** `pressure = mean(VIX %ile over 252d, 1 − breadth %ile)`; breadth = % of universe
     above its 200d SMA; `g_reg = max(0.2, 1 − 0.7·pressure)`.
   - **Combine:** `g = min(g_vol, g_reg)` (most conservative layer wins), then a **±0.07 hysteresis
     band** vs prior gross to cut churn while snapping fast on big de-risks.

### 3.2 Sleeve B — cross-asset TSMOM (`cross_asset_momentum.py`)
- **Universe (the validated 8):** `SPY, EFA, EEM, TLT, IEF, GLD, DBC, UUP` (US/intl/EM equity, long &
  intermediate Treasuries, gold, commodities, USD).
- **Trend:** 12-1 (lookback 252, skip 21), **long/flat** (+1 if positive, 0 if negative — no shorting).
- **Sizing:** risk-parity (1/vol over 60d), then portfolio **vol-target 10%** → de-risk-only gross.
- Goes to cash as fewer assets trend — the defensive mechanism.

### 3.3 Combination & overlay (`portfolio_live.py`)
- **Sleeve weights:** equal-risk-contribution (~40% equity / 60% cross-asset) from
  `portfolio_optimizer.py` (`portfolio_optimizer_latest.json`), overridable via `SLEEVE_W_EQUITY`.
- **Position weight** = sleeve-policy weight × sleeve-internal weight (each sleeve's internal weights
  already carry its own de-risk gross). Cross-sleeve names are netted into one book.
- **Correlation-regime overlay (de-risk only):** reads `correlation_monitor_latest.json`; scales whole-
  book gross — GREEN/AMBER ×1.0, **RED ×0.6, BLACK ×0.3** (crisis floor). Never raises gross; ignored
  if the reading is > 4 days stale.
- **Output:** `portfolio_live_book_<date>.json` (sleeve weights, gross/cash, exposure by asset class,
  positions, regime inputs).

### 3.4 Execution (`portfolio_execute.py`)
- Diff target vs held per name; **skip trades inside the 0.75%-of-equity band** and orders < $5.
- **No-leverage cap:** scale all buys to available cash + sell proceeds (×0.999).
- Buys as **notional** (fractional), sells as qty/close; full exits tagged `PORT-…`. Idempotent via
  `client_order_id = PORT-<SYM>-<asof>-<B|S>`. Market DAY orders queue to the open.
- **Dedicated sweep:** since the account is dedicated, non-target ("foreign") positions are sold to 0.
- **Stale-book guard:** refuses to execute a book older than `max_stale_days` (3).

### 3.5 Orchestration order (`portfolio_guard.ps1`, ~07:00 ET)
**monitor → build → execute → risk snapshot:**
1. `correlation_monitor.py` (writes the regime the overlay will read).
2. `portfolio_live.py` (`BOOK_NAMES=20`) rebuilds the unified book; build failure alerts and aborts.
3. `portfolio_execute.py --live` (if `execution.enabled`) queues orders to the open.
4. `portfolio_risk.py --reconcile-soft` snapshot (pre-open held-vs-book mismatch → WARN, not fail).

---

## 4. Config reference (`portfolio.config.json`)

```jsonc
"book_names": 20,            // top-N equity stocks (small-account cap)
"book_buffer": 5,           // keep a held name until rank > 25 (turnover/Sharpe win)
"risk_overlay": {           // correlation-regime de-risk (never raises gross)
  "enabled": true, "amber_mult": 1.0, "red_mult": 0.6, "black_mult": 0.3, "max_stale_days": 4 },
"risk_limits": {            // live broker hard limits (portfolio_risk.py)
  "max_gross": 1.0, "max_position_pct": 0.25, "max_assetclass_pct": 0.45,
  "max_positions": 40, "max_drawdown_pct": 15.0, "max_daily_loss_pct": 5.0, "auto_repair": false },
"riskmodel": {              // look-through risk budgets (portfolio_riskmodel.py)
  "cov_lookback": 504, "max_name_rc": 0.20, "max_class_rc": 0.55, "max_equity_beta_rc": 0.80 },
"execution": {
  "enabled": true, "profile": "PAPER2", "dedicated": true,
  "deploy_fraction": 0.98, "band_pct": 0.75, "min_order": 5.0, "max_stale_days": 3 }
```

**Sleeve internals** (not in this config — in the sleeve modules / `factor_backtest.cfg()`):
equity momentum lookback 252 / skip 21, tilt top 40%, pos-cap 4%, sector-cap 25%; crash vol-target
0.12, EWMA halflife 21, regime k 0.7, gross floor 0.2, VIX lookback 252, breadth 24 months, band 0.07.
Cross-asset: 8 ETFs, lookback 252 / skip 21, vol lookback 60, vol-target 0.10, long/flat, 10 bps cost.

---

## 5. Validation evidence

### 5.1 Combined book — headline (the PURSUE result)
| Metric | Combined | Equity-only | Benchmarks |
|---|---|---|---|
| Sharpe | **0.84** | 0.73 | SPY ~0.6, 60/40 ~0.7 |
| MaxDD | **−11.9%** | −23.5% | beats both on recovery |
| Calmar | ~0.52 | — | — |
| CAGR | ~6.2% | — | — |

Robust across subperiods; rolling-3y Sharpe median ~0.80. Beats SPY and 60/40 on risk-adjusted return
and drawdown recovery.

### 5.2 Factor regression (combined book) — `flagship-benchmark-factor`
Alpha **+1%/yr, t = 0.82 (insignificant)**; betas: market 0.28, momentum 0.22, size 0.18; R² 0.67.
→ Quantifies "risk-managed **beta**, not alpha." The book's returns are explained by modest factor
exposures, not residual skill.

### 5.3 Crash-protection engine (equity sleeve)
The de-risk engine roughly **halves the 2008 drawdown** (~53.6% → low-to-mid 20s%) while holding
Sharpe. _Note: figures differ across runs — Phase-A build recorded 53.6→29.5% @ Sharpe 0.64 (DEFENSIVE,
below the 0.75 gate); the deployed/Paper-doc framing records 53.6→22.3% @ ~0.75. **Reconcile these to a
single current number** (improvement lever §11)._ The Sharpe give-up vs naive const-vol is concentrated
in 2020.

### 5.4 Cross-asset sleeve
MaxDD ~−11.8%; historically **positive in 2008 & 2020**; correlation to equity momentum ~0.34–0.48 at
validation — the diversification that makes the blend work. Universe expansion was researched and
**rejected** (`cross-asset-universe-expansion`): every crash-validatable add lowered Sharpe vs the 8;
managed futures deferred (ETFs too young). **Keep the 8.**

### 5.5 Construction research (what did / didn't help) — `portfolio-construction-research`

| Experiment | Result | Detail |
|---|---|---|
| Inverse-vol sizing | ❌ worse | Sharpe 0.85 < 0.88 baseline |
| Ensemble | ❌ worse | 0.854 < 0.876 |
| Dynamic allocation | ❌ worse | ≤ 0.84 |
| **Selection buffer** | ✅ **better — deployed** | top-20 Sharpe 0.796 → 0.805 **and** turnover −21% |

The **one real win** was the selection/replacement buffer (deployed). Everything else failed to beat
plain tilt. Lifting Sharpe past ~0.95–1.10 needs **new premia, not re-sizing** — re-sizing is exhausted.

---

## 6. Honest assessment (ordered by practical importance)

> _Scan map (review-2 #8) — two kinds of finding:_
> - **Operational concerns** (live risks to manage): §6.1 diversification weakening · §6.2 hidden
>   equity-beta concentration. _(See also §10: Treasury regime, monitoring, account-reset fragility.)_
> - **Research conclusions** (what the evidence settled): §6.3 risk-managed beta, not alpha · §6.4
>   selection alpha refuted under PIT · §6.5 selection layer adds little · §6.6 Sharpe ceiling from re-sizing.

### 6.1 ⚠️ The diversification thesis — the whole point — is weakening (the #1 risk)
`correlation-monitor-fix`: sleeve correlation is **+0.68 over 1y (persistent 12 months) and +0.77 over
60d and rising**. Historically the sleeves were a real hedge (**2008 corr −0.45**, it worked) but
**2020 corr +0.78 (it failed)**. Cross-asset is becoming increasingly equity-beta (regression R²
0.23 → 0.52). The diversification edge is **real but thinning** — if the correlation climbs toward 1.0,
the book degrades toward a single equity-beta sleeve and the drawdown advantage erodes. This directly
attacks the core thesis and is the first thing to fix (see §11 #1, the correlation decomposition).

**Decomposition (2026-06-25, `correlation_decompose.py`) — the driver is Treasuries going equity-like.**
Per-ETF correlation to the equity sleeve, 250d → 60d (current forward sleeve corr ~0.70):
**IEF 0.13 → 0.53 (Δ +0.40)** and **TLT 0.12 → 0.47 (Δ +0.35)** — intermediate/long Treasuries (~42%
of the cross-asset sleeve) flipped from diversifiers to equity-like in the post-2022 rate regime: the
single largest cause. The equity ETFs (SPY/EFA/EEM, ~20% of the sleeve) sit at 0.82–0.87 by
construction and are the biggest positive contributors. The **only surviving diversifiers are USD and
commodities** — **UUP −0.23 → −0.61** and **DBC −0.10 → −0.53**, both *deepening* (more negative =
better hedge). So the fix is mechanical: re-weight away from Treasuries + equity-ETFs, toward
USD/commodities — prototyped and quantified in §11 #1.

### 6.2 ⚠️ Hidden equity-beta concentration
`security-level-riskmodel`: the book is **~87% cross-asset by capital but ~89% equity-beta by risk**;
the equity sleeve is **13% of capital but ~60% of risk**. The sleeve-level ERC optimizer doesn't see
this look-through concentration — the look-through risk model (read-only) was built to surface it. The
"diversified" label is undercut until this is acted on (§11 #2).

### 6.3 It's risk-managed beta, not alpha
Combined-book residual alpha is **statistically insignificant (t = 0.82)**; the return is factor
exposure. The product's value is drawdown reduction + diversification, not skill.

### 6.4 ⚠️ The equity sleeve's stock-selection alpha was REFUTED under point-in-time data
`factor-engine-status`: when the universe was re-sized by **point-in-time market cap** (DAILY), the
clean PIT re-runs **killed the momentum-sleeve headline** — every window (5y mid+lg 0.67, 10y lg+mega
0.82, 10y mid+lg 0.76) **trailed SPY (0.99) and MTUM (0.94) net of cost**. The earlier "Sharpe 0.98
beats MTUM" was **look-ahead** (current-tier market-cap sizing leaked ~33% future information). The
mid-cap thesis was refuted. So the equity sleeve is a **risk-managed momentum tilt**, not a source of
selection alpha — its job is crash-protected beta + diversification. (28-yr PIT is impossible: DAILY
starts 2016.)

### 6.5 The selection layer adds little
Construction sweeps showed almost every sizing/ensemble idea failed to beat plain tilt; only the
turnover buffer helped, and modestly (§5.5).

### 6.6 Sharpe ceiling
Re-sizing is exhausted as a lever; pushing Sharpe higher requires a genuinely new return source (§11 #6).

---

## 7. Continuous Evidence (live state, 2026-06-25)

**Evidence outputs this capability generates** (review-2 #6 — what "Continuous Evidence" produces, today
via the sibling stack; _target_ destination = the Workbench Evidence Dashboard): daily **portfolio
snapshots** (`portfolio_live_book_<date>.json`) · **rebalance history** · **correlation-regime history**
(`correlation_monitor_latest.json`) · **drawdown-vs-HWM history** · **risk-limit violations**
(`portfolio_risk.py`) · **execution reconciliation** (`portfolio_reconcile.py`).

- **PAPER2** `PA3344TNRFYD` ACTIVE — equity ≈ $99,827, cash ≈ $32,308.
- **28 positions filled** at today's open (book asof 2026-06-24): cross-asset core IEF 15.8% / UUP
  15.3% / TLT 9.1% / SPY 5.6% / EFA 4.1% / DBC 3.8% / GLD 3.2% / EEM 2.4% + 20 momentum stocks ~0.4%
  each. Gross **67.6%**, cash 32.4%, day P&L ≈ −0.17%.
- **Regime: AMBER** → overlay ×1.00 (no de-risk; only RED/BLACK cut gross).
- **2026-06-24 reset:** the prior ~$99.7k/27-position PAPER2 was lost when the account was accidentally
  repointed; re-established on a **new $100k account** (PA3344TNRFYD) with equity/HWM restarting 6/24.
  Full re-deployment from cash ran at the 6/25 open. (See memory `paper-account-reset-20260624`.)
- A standing **−15% drawdown watchdog** monitors the book intraday and ntfy-alerts on breach.

---

## 8. Risk & exposure metrics

| Metric | Value / status |
|---|---|
| Gross / cash | ~68% / ~32% (regime + vol-target driven; max_gross limit 1.0) |
| Largest name / class | UUP ~15% (cap 25%); USD / Int-bond largest classes (cap 45%) |
| Position count | 28 (cap 40) |
| Portfolio market beta | **0.28** (from the combined-book factor regression, §5.2) |
| Effective equity beta (look-through) | **~89% of total risk** is equity-beta despite only ~13% equity-sleeve capital |
| Rate / duration exposure | material — IEF (~15.8%, ~7y dur) + TLT (~9.1%, ~17y dur) ≈ 25% of book; exact DV01 contribution *(to compute — §11)* |
| FX exposure | **net long USD** (UUP ~15.3%) partly offset by unhedged intl equity (EFA/EEM ~6.5%); net figure *(to compute)* |
| Commodity / gold | DBC ~3.8% + GLD ~3.2% ≈ **7%** |
| Drawdown vs HWM | monitored hard (limit −15%); HWM restarted $100k on 6/24 |
| Daily-loss limit | −5% (hard) |
| Live MaxDD (validated, full history) | −11.9% (combined book) |
| Hidden concentration | surfaced by `portfolio_riskmodel.py` — read-only audit, no auto-rebalance |

**Capital → risk → return contribution** (the equity sleeve punches far above its capital):

| Sleeve | Capital | Risk | Return |
|---|---|---|---|
| Equity momentum | **~13%** | ~50% sleeve-level / **~60–89% equity-beta** | **~51%** |
| Cross-asset | ~87% | ~50% sleeve-level | ~49% |

_Sources: `contribution_analysis.py` (return 51/49, sleeve-risk ~50/50, security-level 60/40) +
`portfolio_riskmodel.py` (~89% equity-beta-by-risk)._ → **~13% of capital drives ~half the return and
the majority of the risk** — high capital efficiency, but the equity sleeve is the dominant risk
source and the reason §6.1/§6.2 matter. Per-name marginal-return attribution is still to compute.

---

## 9. Monitoring stack & operational KPIs

| Module | Role |
|---|---|
| `correlation_monitor.py` | **Primary risk signal** — sleeve-pair correlation + cross-asset cohesion (top-eigenvalue "market-mode" share) → GREEN/AMBER/RED/BLACK; drives the de-risk overlay. |
| `portfolio_risk.py` | Live broker state vs hard limits (leverage/concentration/DD/daily-loss) + reconciliation vs book; ntfy on breach. |
| `portfolio_riskmodel.py` | Security-level look-through covariance; surfaces hidden equity-beta concentration (§6.2). |
| `portfolio_reconcile.py` | Post-open fill audit (filled/partial/rejected) + corrective orders (`--repair`, idempotent `RECON-…`). |

**Operational KPIs to track** (some continuous once logged): book-build success rate, SEP/Yahoo data
freshness (a stale Yahoo cache once nearly auto-halted the book — `yahoo-cache-freeze`), order fill
rate, correlation-regime state over time, days since last successful rebalance, drawdown vs HWM.

---

## 10. Limitations (summary)

1. **Diversification weakening** (§6.1) — sleeve corr 0.68→0.77; the core mechanism is thinning. **#1 risk.** _Decomposed + fix prototyped + λ-swept 2026-06-26 (Treasuries went equity-like; a λ≈0.5 corr-aware tilt cuts sleeve corr 0.57→0.42 ~free, with better drawdown) — §11 #1; deploy decision pending._
2. **Hidden equity-beta concentration** (§6.2) — 13% capital / ~60% risk in the equity sleeve.
3. **Not alpha** (§6.3) — combined alpha insignificant (t = 0.82); it's factor beta.
4. **Equity-sleeve selection alpha refuted under PIT** (§6.4) — the sleeve is risk-managed beta, not skill.
5. **Sharpe ceiling from re-sizing** (§6.6) — needs new premia.
6. **PIT history limited** — DAILY (point-in-time market cap) starts 2016; no clean 28-yr test.
7. **Small-account quantization** — top-20 cap + fractional sizing; not the full-universe construction.
8. **Operational fragility** — data-freshness and account-rotation incidents have nearly halted/lost the book.

---

## 11. Improvement levers — Part A · Investment Research (prioritized)

> _**Part A** (this §11) = research that improves the *investment* capability. **Part B** (§12) =
> *platform* integration. Separating them clarifies ownership (review-2 #4)._

**Governing principle (per review): fully optimize the risk management of the existing two sleeves
before adding a third.** Order below reflects that.

**Lever → work category** (review-2 #9 — what kind of change each needs):

| Lever | Category |
|---|---|
| 1 · Correlation-aware allocation | **ProgramSpec** (sleeve weighting) |
| 2 · Look-through risk model into construction | **Platform** (risk-engine integration) |
| 3 · Operational hardening (KPI tripwires) | **Operational** |
| 4 · Reconcile crash-engine numbers | Research |
| 5 · Full-universe vs top-20 | Research |
| 6 · Add a third return stream | Research _(last)_ |

**1. Correlation-aware allocation — ✅ RESEARCHED 2026-06-25/26 _(was lever B)_; deploy decision pending.**

- **Diagnosis** (`correlation_decompose.py`, §6.1): the rising sleeve correlation is driven by
  **Treasuries going equity-like** (IEF Δ +0.40, TLT Δ +0.35 over 250d→60d) plus the ~20% equity ETFs;
  the only surviving diversifiers are **USD (UUP −0.61) and commodities (DBC −0.53)**.
- **Fix prototype** (`cross_asset_corr_aware.py`, read-only): tilt the cross-asset risk-parity step by a
  diversification multiplier `d_a = clip(1 − λ·corr(asset_a, SPY), floor, cap)` that down-weights
  equity-correlated assets (stronger at higher tilt strength `λ`), then applies the usual trend filter +
  vol-target (both unchanged).
- **λ sweep — efficient frontier (combined book, 2026-06-26).** The original λ=1.0 over-tilted; at a
  moderate tilt the "cost" disappears:

  | λ | Sharpe (full) | MaxDD | **Sleeve corr** | Sharpe (recent) | Read |
  |---|---|---|---|---|---|
  | 0 (baseline) | 0.897 | 11.6% | 0.571 | 0.855 | the problem |
  | **0.25** | **0.901** | 11.0% | 0.506 | **0.863** | Pareto win — Sharpe + DD + corr all improve |
  | **0.50** | 0.894 | 10.7% | 0.418 | 0.858 | ~free: Sharpe flat, corr −27%, better DD |
  | 0.75 | 0.870 | **10.4%** | 0.300 | 0.844 | corr halved, best DD, −0.03 Sharpe |
  | 1.00 (orig) | 0.809 | 10.7% | 0.143 | 0.819 | over-tilt: −0.09 Sharpe |
  | 1.50 | 0.721 | 10.6% | 0.015 | 0.754 | kills the sleeve |

  → **Not a trade-off at a moderate tilt.** At **λ ≈ 0.25–0.50 it's a Pareto improvement / free
  correlation relief** (Sharpe held-or-up, drawdown better, corr down); even **λ = 0.75 halves sleeve
  correlation (0.57→0.30) for ~0.03 Sharpe with the best drawdown**. The λ=1.0 −0.09-Sharpe figure was
  simply too aggressive a tilt.
- **Recommendation: adopt at λ ≈ 0.50** — sleeve corr **0.57 → 0.42**, combined Sharpe **flat**
  (0.897 → 0.894), drawdown **better** (11.6 → 10.7%): real, near-free insurance against the #1 risk
  (correlation rising). Choose **λ = 0.75** instead if you want more correlation insurance and prize
  drawdown over the last bit of Sharpe (corr 0.30, best DD, −0.03 Sharpe). This answers the §11 open
  question ("crash-protected beta → stop chasing Sharpe") — and at λ≈0.5 we barely even pay.
- ⚠ **Deploying changes the LIVE PAPER2 book** — gate on owner sign-off + a careful productionization
  (fold the **λ ≈ 0.5** tilt into `cross_asset_momentum.py`'s weighting; keep it
  de-risk-direction-consistent; paper-validate before relying on it). Until then the prototype stays
  research-only and the RED/BLACK gross overlay remains the only live de-risk.

**2. Integrate the look-through risk model into construction _(was lever D)_.** Today it's read-only.
Decide whether to **cap equity-beta risk contribution** (config `max_equity_beta_rc` already exists)
and have the builder respect it, or keep it as disclosure only. Acts on §6.2.

**3. Operational hardening _(was lever F)_.** Promote the KPI list (§9) to logged metrics + tripwires
(data-freshness alarm, days-since-rebalance, account-identity check) after the 6/24 reset and the
Yahoo-cache near-miss.

**4. Reconcile the crash-engine numbers _(was lever A)_.** Phase-A (53.6→29.5 @ 0.64) vs deployed
(53.6→22.3 @ 0.75) disagree (§5.3). Re-run once, record a single current figure.

**5. Full-universe vs top-20 _(was lever E)_.** Quantify how much the small-account 20-name cap costs
vs the validated full-universe construction, so live behavior is calibrated.

**6. Add a third return stream — LAST _(was lever C)_.** Only after 1–5. Re-sizing is exhausted
(§6.6); new premia are the only Sharpe lever. Candidates: managed futures (revisit ETF maturity),
carry/quality, a low-correlation macro signal. Gate on crash-validatable, PIT-clean evidence, and
**only add a sleeve that demonstrably improves diversification** — not to grow the strategy count.

**Also recommended (richer analytics, feeds the above):** multi-horizon rolling correlation
(30/60/120/250d — shape beats one number); recovery metrics (recovery time, underwater duration, ulcer
index) alongside MaxDD; a SPY-vs-combined drawdown chart; look-through concentration persistence
(avg / peak / 95th pct); scenario/stress analysis across inflation / rate / recession regimes.

**Open questions for you:**
- Is the book's purpose **crash-protected beta** (then size it as such and stop chasing Sharpe), or are
  we still trying to find alpha (then #6 is the only path)?
- How much diversification decay (§6.1) is tolerable before we re-architect the sleeve mix?

---

## 12. Related context & Part B · Platform Integration

Flagship of the program. The retired ETF-momentum book (PAPER1-era) was superseded by this book's
cross-asset sleeve. The insider overlay (PAPER1) is a separate, smaller factor-tilt book — see
`Docs/Insider Strategy.md`. Full program map: `Docs/Paper Trading Strategies.md` and the memory index.

### Platform-integration roadmap — migrate to Factor Lab as PORT-001 _(target)_

The 2026-06-26 review (`comments.md`) is right that, *inside TradingWorkbench*, this should be a
first-class **capability**, not a standalone strategy. The honest gap today: the book lives in the
sibling `claude-trading-view` system and is **not** wired into Factor Lab / OrderRouter / Evidence
Engine / the Capability Registry. The work that closes that gap (and makes the "Capability framing"
section literally true rather than aspirational):

1. **Register `PORT-001`** in the Research Program Registry (Portfolio Construction; Investment + Platform
   capability split, review #8) with an honest verdict line (crash-protected beta + diversification;
   alpha refuted under PIT, §6.4).
2. **Express the two-sleeve ERC construction as a Factor-Lab `ProgramSpec`** (ADR 0026) so it runs through
   `run_program` + the bootstrap/evidence engine and emits a real Evidence Package — the *Portfolio
   Construction Engine* becomes the reusable platform capability MOM/LOW/SEC/INSIDER can consume.
3. **Route any Workbench-side execution through the single OrderRouter + risk engine** (ADR 0002); keep
   the sibling book running in parallel until the migrated capability is paper-validated (co-exist, then
   retire the sibling — the SEC-001/INSIDER-001 pattern).
4. Wire **Continuous Evidence** (§7/§9 monitors → the platform Evidence Dashboard).

This is an engineering/platform track, **distinct from the §11 research levers** (which optimize the
strategy itself). Sequence is the owner's call; until then this doc is PORT-001's capability *spec*.

**Migration complete when** (review-2 #10 — the done-definition that closes the loop):

1. **ProgramSpec implemented** — the two-sleeve ERC construction runs through Factor-Lab `run_program`.
2. **Evidence reproduced** — a Workbench Evidence Package reproduces the sibling's headline numbers
   (independent reproduction, the SEC-001/INSIDER-001 bar).
3. **Registry entry created** — `PORT-001` is in the Research Program Registry with its verdict.
4. **Paper capability running** — executes via the OrderRouter + risk engine on a Workbench paper account.
5. **Continuous Evidence operational** — monitors feed the platform Evidence Dashboard.
6. **Sibling retired** — only after sustained agreement between the two (co-exist, then retire).

Until all six hold, the "Capability framing" tables above keep their _(target)_ markers.
