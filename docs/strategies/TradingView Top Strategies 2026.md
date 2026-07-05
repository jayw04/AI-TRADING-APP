# TradingView Top Community Strategies — 2026

**Compiled:** 2026-06-29
**Purpose:** Document the top-3 public TradingView community strategies (2026) as backtest
candidates, then run an apples-to-apples Strategy Tester pass on each.

> ## ⮕ Verdict (2026-06-29): chartered as **TV-001 — 🔴 Not Approved**
> This test is now a formal research program — **TV-001 (Community Strategy Import Test)** in the
> [Research Program Registry](../implementation/TradingWorkbench_Research_Program_Registry_v0.1.md).
> **Record:** [`TradingWorkbench_TV001_CommunityStrategyImport_v0.1.md`](../implementation/TradingWorkbench_TV001_CommunityStrategyImport_v0.1.md).
> - **HalfTrend (#1)** and **Universal RSI (#2)** → **Rejected** (no edge; sign-flip across windows).
> - **Supertrend (#3)** → **research candidate `TV-001-SUPERTREND`** only (needs walk-forward + realistic
>   sizing before any promotion — *not* a deployment decision).
> - **Lessons:** popularity ≠ edge · symbol selection > strategy choice · severe window sensitivity.
> - **Rule established:** no 100%-equity sizing in promotion-grade tests.

---

## ⚠️ Critical caveat — read first

TradingView has **no verified-performance ranking**. The public library is sorted by:
- **Boosts (likes)** — how many users saved a script. Real and unfakeable, but measures
  *popularity/usefulness*, NOT realized returns.
- **Editor's Picks** — hand-curated by the TV team for quality/innovation, not performance.

Any "best performing" return figures attached to community scripts are **self-reported backtests**,
which are routinely **curve-fit / overfit / single-asset / cherry-picked timeframe**. Of 100k+
published scripts, experts estimate only ~20–30 are consistently profitable. **The only trustworthy
number is one we generate ourselves** under controlled conditions (our symbol, our costs, our window).

This ranking is therefore by **community popularity (boosts)** — the most objective public signal —
not by claimed performance.

**Source:** TradingView Strategies library, `tradingview.com/scripts/?script_type=strategies`
(snapshot 2026-06-29).

---

## #1 — HalfTrend SNIPERMONKEY

| Field | Value |
|---|---|
| Author | YashikaSatya |
| Boosts | **398** (by far the most-saved strategy in the current library) |
| Type | Trend-following, intraday, long & short with auto-flip |
| Underlying | HalfTrend indicator (ATR-based trend filter) |
| Target market | Indian equities/index intraday (NSE session, IST) |

### What HalfTrend is (the engine)
HalfTrend is an overlay **trend-following** indicator, conceptually similar to SuperTrend but with
different flip logic. It plots:
- a **main HalfTrend line** that acts as dynamic support (uptrend) / resistance (downtrend), and
- an **ATR-based channel** (ATR High / ATR Low bands) around it.

Mechanics: it tracks **swing highs/lows over an `amplitude` lookback** and uses ATR to decide when
price has genuinely broken structure. When the trend flips down→up it prints a **Buy** and the line
turns to support; up→down prints a **Sell** and the line becomes resistance. Because it requires a
true structural flip (not a simple MA cross), it filters a lot of chop.

**Key parameters:**
- `Amplitude` (default **2**) — sensitivity / lookback for swing detection. Higher = smoother, more
  lag, fewer false signals.
- `Channel Deviation` (default **2**) — ATR multiple setting the channel width. The ATR High/Low
  bands are commonly used as TP / SL references.

### What SNIPERMONKEY adds on top
- **Session-gated entries:** new positions only inside the cash session (~09:20–15:20 IST); nothing
  opened outside the window.
- **Pre-session signal carry-forward:** a HalfTrend flip that fires pre-market/overnight is *latched*
  and executed at the session open — so a signal formed while closed isn't missed.
- **Automatic position flip:** on a mid-session reversal it closes the current position and opens the
  opposite side in one step (always-in-market during the session).
- **Pivot/volume filters:** "Require Absorption On Pivot Candle" (valid pivots must have the
  absorption candle exactly on the pivot) and a "Pivot Volume Multiplier" (minimum volume for the
  pivot).

### Backtest-ability: ✅ Good
Self-contained fixed-logic strategy with `strategy()` calls → Strategy Tester works directly.
**Caveats:** it's tuned for the **IST session** — backtesting on a US ticker (e.g. CRCL) needs the
session window adjusted to US RTH (09:30–16:00 ET) or session-gating disabled, else entries are
suppressed. Designed for intraday timeframes (1m–15m).

---

## #2 — Universal Strategy Feed

| Field | Value |
|---|---|
| Author | Options360 |
| Boosts | **75** |
| Type | **Meta-strategy / framework** (not a fixed strategy) |
| Underlying | User-selected signal + user-selected exit |

### What it is
A flexible "meta-strategy" backtesting harness in one script. Instead of hardcoding one indicator,
you pick the **signal source**, **signal mode**, and **exit method**, and it wires them into the
Strategy Tester. Think of it as a configurable strategy bench rather than a single edge.

**Signal modes:**
- **Pulse** — binary on/off signal.
- **Sign Cross** — enter when source crosses above/below a defined level.
- **Level Cross** — classic overbought/oversold logic.
- **Volume** — auto-detects volume spikes.

**Signal sources:** any series — `close`, `RSI`, `EMA`, or another indicator's output.

**Exit methods:**
- **Signal** — exit when the opposite signal fires.
- **Percent** — fixed % TP / SL.
- **ATR** — volatility-scaled dynamic TP / SL.

**Other:** contracts-per-trade sizing, date-range filter for windowing the backtest.

### Backtest-ability: ⚠️ Config-dependent
It *runs* in the Strategy Tester, but its "performance" is **whatever configuration you choose** — it
has no inherent edge to measure. To compare it fairly we must **pin one specific config** (e.g.
RSI Level-Cross 30/70 with ATR exits) and document that config as part of the test. Otherwise the
result says nothing about "the strategy."

---

## #3 — "Pass most prop-firm challenges with this Pine script"

| Field | Value |
|---|---|
| Author | finnick1111 |
| Boosts | **33** |
| Type | Risk-managed strategy aimed at funded-account / prop-firm evaluations |
| Status | **Public detail thin — needs verification** |

### What's known
Marketed as a strategy engineered to pass proprietary-firm trading challenges — i.e. the design
emphasis is **prop-firm rule compliance** (daily-loss limits, max drawdown caps, profit targets,
disciplined position sizing) more than a novel entry edge. This is a common 2026 niche: scripts that
shape risk/drawdown to evaluation rules rather than maximize raw return.

### ⚠️ Gaps
Public search surfaced **no authoritative description, source logic, or parameter list** for this
specific script. Possible reasons: protected/invite-only source, recent/low-indexed, or a generic
title. **Before backtesting we need either (a) the direct TradingView script URL, or (b) agreement to
substitute** a better-documented #3.

### Suggested substitutes (well-documented, openly loadable) if we drop #3
- **Supertrend** by KivancOzbilgic — perennial top-tier ATR trend flipper; clean fixed logic.
- **Ultimate Lorentzian Classification** by greymyst — popular ML-style classifier strategy (also on
  the current strategies page).

---

## Backtest plan (to run next, one by one)

Apples-to-apples settings so results are comparable:

| Parameter | Value |
|---|---|
| Symbol | TBD (default: **CRCL**, or a basket) |
| Timeframe | Per strategy's design (HalfTrend: intraday e.g. 15m; others: TBD) |
| Period | **2026 YTD** (and/or trailing 3 months) |
| Costs | Set realistic commission + slippage in Strategy Tester properties |
| Starting capital | Fixed (e.g. $10,000), same for all |
| Position sizing | Normalize (e.g. % of equity) so net-profit is comparable |

**Metrics to capture for each:** Net Profit %, Profit Factor, Max Drawdown %, Win Rate, **# of
Trades** (sample size — reject tiny samples), Sharpe/Sortino if shown, avg trade.

> Note: a strategy's published default settings + symbol are usually where it looks best (in-sample).
> Running it on *our* symbol/period is the honest out-of-sample-ish test — expect numbers to drop.

---

## Results log

**Full 3×3 matrix tested 2026-06-29.** All three strategies × {AMD, TSLA, MSFT}, run in one
consistent pass under identical settings so cells are comparable. Settings for every cell:
**15m timeframe**, period **Nov 3 2025 → Jun 29 2026** (~8 mo — all of TV's available 15m history),
**US-RTH session gating** (09:30–16:00 ET), long/short, **commission 0.02% + 2 ticks slippage**,
**100% equity sizing, $10k start**. Recon Pine sources saved under `Docs/Strategies/pine/`.

> Reproducibility note: the three originals are community scripts (SNIPERMONKEY's is closed; the
> others public/configurable). These are faithful **reconstructions** of the documented engines, not
> byte-for-byte copies. The AMD cells for #1/#2 reproduce the earlier standalone runs to within
> rounding (identical win rates and trade counts), which validates the reconstructions.

### Net Profit % matrix (15m, ~8 mo, US-RTH)

| Strategy | AMD | TSLA | MSFT | Read |
|---|---|---|---|---|
| **#1 HalfTrend** (trend-follow) | ❌ −25.60% | ❌ −32.79% | ✅ **+22.60%** | 1 win / 3 |
| **#2 Universal** (RSI 30/70 mean-rev) | ❌ −23.86% | ❌ −4.96% | ❌ −21.14% | 0 wins / 3 |
| **#3 Supertrend** (trend-follow) | ❌ −25.44% | ✅ **+23.22%** | ✅ **+59.28%** | **2 wins / 3** |

### Per-cell detail

| # / Symbol | Net PnL | Max DD | Win rate | Trades |
|---|---|---|---|---|
| #1 HalfTrend / AMD | −$2,560.39 (−25.60%) | $5,569.79 (46.19%) | 33.33% | 132 |
| #1 HalfTrend / TSLA | −$3,279.47 (−32.79%) | $4,963.39 (48.63%) | 37.16% | 148 |
| #1 HalfTrend / MSFT | **+$2,260.07 (+22.60%)** | $1,664.05 (12.46%) | 41.88% | 160 |
| #2 Universal / AMD | −$2,386.09 (−23.86%) | $4,611.79 (41.24%) | 33.95% | 162 |
| #2 Universal / TSLA | −$496.22 (−4.96%) | $2,874.27 (23.56%) | 39.57% | 187 |
| #2 Universal / MSFT | −$2,114.28 (−21.14%) | $2,215.71 (22.16%) | 30.99% | 171 |
| #3 Supertrend / AMD | −$2,544.11 (−25.44%) | $4,655.83 (40.03%) | 38.71% | 93 |
| #3 Supertrend / TSLA | **+$2,322.03 (+23.22%)** | $2,517.63 (17.13%) | 48.42% | 95 |
| #3 Supertrend / MSFT | **+$5,927.88 (+59.28%)** | $1,632.32 (15.84%) | 49.41% | 85 |

### What the matrix says

- **Symbol mattered more than strategy.** MSFT (clean, persistent 15m trends) was friendly to *both*
  trend-followers; AMD (choppy, gappy intraday) was hostile to *all three*. No strategy was robust
  across all symbols — every "edge" here is symbol-conditional, which is exactly the overfitting trap
  the popularity ranking warns about.
- **Popularity ≠ performance, confirmed again.** #1 HalfTrend — by far the most-boosted script
  (398) — was the *worst* of the two trend-followers (1/3, deep −33% on TSLA). The far-less-hyped
  **Supertrend recon was the standout (2/3, +59% on MSFT)**.
- **Overtrading is the tell.** The losers churn: HalfTrend (132–160 trades) and the RSI config
  (162–187 trades) flip constantly and bleed on commission + slippage. Supertrend trades least
  (85–95) — fewer whipsaws, lower drawdown (16–17% vs 40–49%), and it's the only consistent winner.
- **The mean-reversion config (#2) lost on every symbol.** Best case was TSLA at −5%. A naive
  "buy oversold / short overbought" RSI cross with fixed ATR exits has no edge on these names at 15m.
  (This was *our* pinned config; the framework itself has no inherent edge to measure.)
- **Bottom line:** of 9 cells, only 3 are green and they cluster in one place — trend-following on
  MSFT/TSLA. Nothing here is a deployable edge; it's a demonstration that community popularity tells
  you nothing about realized performance, and that a single friendly symbol can flatter a strategy.

### Caveats (don't over-read these numbers)

- ~8-month single window, one timeframe (15m) — not enough to trust; no walk-forward / multi-regime.
- 100% equity sizing compounds aggressively and is not how any of these would be sized live; it
  inflates both the winners and the losers vs realistic position sizing.
- Recon scripts ≈ the documented engines, not the exact originals (especially SNIPERMONKEY's closed
  source). Sample sizes (85–187 trades) are adequate but not large.
- TV's structured Strategy-Tester API returned empty this session; all figures were read from the
  Strategy Tester UI (screenshots archived under `~/tradingview-mcp/screenshots/`).

---

## Last-3-month window + data-driven symbol selection (2026-06-29)

Two follow-ups: (1) re-run on the **last 3 months** (Mar 29 → Jun 29 2026) instead of the full ~8 mo,
and (2) add symbols **selected to fit each strategy's nature** rather than picked arbitrarily.

### How symbols were selected (not just picked)

The two trend-followers (#1, #3) profit from **clean directional legs**; the mean-reversion config
(#2) profits from **range/chop**. So we screened a liquid candidate universe on 15m over the last
~3 months with a custom Pine study (`Trendiness Screener`, saved at
`Docs/Strategies/pine/trendiness_screener.pine`) measuring, per symbol:

- **segER** — Kaufman Efficiency Ratio over rolling 100-bar (~4-day) segments, averaged. Trend
  *quality* of the legs the strategy actually trades. (A whole-window ER is useless here — it just
  measures net displacement; TSLA scored 0.007 because it round-tripped, despite tradeable legs.)
- **avgADX** — directional strength. **avgCI** — Choppiness Index (high = range, low = trend).
- **avgTR%** — per-bar volatility (noise).
- **TrendScore = segER ÷ avgTR%** — trend quality *per unit of noise*. This single composite ranked
  the three anchors in exact order of their trend-follower results (MSFT 0.53 win > TSLA 0.32 mixed >
  AMD 0.19 loss), so it was used to pick.

Screen (15m, ~3 mo; * = calibration anchors with known outcomes):

| Symbol | segER | ADX | CI | TR% | TrendScore | Character |
|---|---|---|---|---|---|---|
| SPY | 0.115 | 26.5 | 46.6 | **0.14** | 0.82 | ultra-quiet range |
| QQQ | 0.135 | 27.9 | 45.0 | 0.23 | 0.59 | quiet, balanced trend |
| MSFT* | 0.168 | 28.0 | 42.6 | 0.32 | 0.53 | *anchor: big win* |
| AAPL | 0.116 | 26.2 | 46.6 | 0.27 | 0.43 | quiet/rangey |
| NFLX | 0.117 | 23.7 | 46.3 | 0.28 | 0.42 | quiet, weak ADX |
| META | 0.135 | 26.0 | 44.9 | 0.33 | 0.41 | clean mega-cap trend |
| GOOGL | 0.113 | 26.7 | 46.5 | 0.34 | 0.33 | mid |
| PLTR | **0.163** | 28.4 | **43.6** | 0.51 | 0.32 | best trend quality, noisy |
| TSLA* | 0.130 | 26.4 | 45.2 | 0.41 | 0.32 | *anchor: mixed* |
| NVDA | 0.119 | 25.9 | 46.4 | 0.38 | 0.31 | mid |
| AVGO | 0.130 | 27.1 | 44.4 | 0.56 | 0.23 | noisy |
| COIN | 0.125 | 27.0 | 44.4 | 0.63 | 0.20 | very noisy |
| AMD* | 0.132 | 29.5 | 44.2 | 0.70 | 0.19 | *anchor: loss* |

**Picks:** trend-followers → **QQQ** (top TrendScore among real movers) and **PLTR** (highest trend
*quality* / lowest CI, but noisy — a deliberate trend-vs-noise stress test). Mean-reversion → **SPY**
(highest CI + lowest noise = textbook range; its fairest possible test).

### 3-month results matrix — Net Profit % (15m, Mar 29 → Jun 29 2026, US-RTH)

Run via a `useDateFilter` gate (entries only after Mar 29 2026) added to each recon. `—` = not run
(symbol not matched to that strategy's nature).

| Strategy | AMD | TSLA | MSFT | QQQ | PLTR | SPY |
|---|---|---|---|---|---|---|
| **#1 HalfTrend** (trend) | ✅ +9.40% | −8.92% | −5.58% | −15.39% | ❌ −28.51% | — |
| **#2 RSI** (mean-rev) | −7.79% | −13.98% | −7.47% | — | — | ✅ **+0.51%** |
| **#3 Supertrend** (trend) | −10.74% | −16.41% | ✅ **+34.60%** | −12.61% | ✅ **+26.09%** | — |

Per-cell detail:

| # / Symbol | Net PnL | Max DD | Win rate | Trades |
|---|---|---|---|---|
| #1 HalfTrend / AMD | +$939.51 (+9.40%) | 33.87% | 36.84% | 57 |
| #1 HalfTrend / TSLA | −$891.96 (−8.92%) | 29.24% | 42.86% | 49 |
| #1 HalfTrend / MSFT | −$558.16 (−5.58%) | 12.51% | 39.06% | 64 |
| #1 HalfTrend / QQQ | −$1,538.71 (−15.39%) | 16.35% | 36.00% | 50 |
| #1 HalfTrend / PLTR | −$2,850.70 (−28.51%) | 33.29% | 44.23% | 52 |
| #2 RSI / AMD | −$779.18 (−7.79%) | 26.04% | 32.76% | 58 |
| #2 RSI / TSLA | −$1,397.68 (−13.98%) | 15.55% | 31.88% | 69 |
| #2 RSI / MSFT | −$746.51 (−7.47%) | 9.64% | 33.77% | 77 |
| #2 RSI / SPY | **+$51.11 (+0.51%)** | **4.21%** | 36.54% | 52 |
| #3 Supertrend / AMD | −$1,074.50 (−10.74%) | 39.45% | 45.71% | 35 |
| #3 Supertrend / TSLA | −$1,640.52 (−16.41%) | 17.39% | 44.74% | 38 |
| #3 Supertrend / MSFT | **+$3,460.45 (+34.60%)** | 11.49% | 42.86% | 28 |
| #3 Supertrend / QQQ | −$1,260.98 (−12.61%) | 16.39% | 45.95% | 37 |
| #3 Supertrend / PLTR | **+$2,608.76 (+26.09%)** | 12.53% | 46.43% | 28 |

### What changed vs the 8-month window — and what the selection bought us

- **Window sensitivity is severe (the headline finding).** Comparing the four cells we can match
  8 mo → 3 mo: **TSLA Supertrend +23.22% → −16.41%** (flipped), **MSFT HalfTrend +22.60% → −5.58%**
  (flipped), **AMD HalfTrend −25.60% → +9.40%** (flipped the other way), MSFT Supertrend +59% → +35%
  (held). When the sign of your "edge" depends on where you start the clock, it isn't an edge — it's
  window-dependent noise. This is the clearest possible illustration of the doc's opening warning.
- **Supertrend (#3) is still the only repeatable winner** — MSFT in *both* windows, plus PLTR. It
  trades least (28 trades) and its wide ATR trail rides legs through noise.
- **The selection partially worked — and worked exactly where the metric was decisive:**
  - **PLTR → Supertrend +26.1%.** Picked for best trend *quality* (highest segER, lowest CI); paid off
    for the patient trend-follower.
  - **SPY → #2's only non-loss (+0.5%, DD just 4.21%).** The mean-reversion strategy's best result
    landed on the symbol selected for it — highest CI, lowest noise. Selection validated for #2.
  - **But QQQ (top TrendScore) → both trend-followers lost.** Low noise alone wasn't enough; QQQ
    simply lacked a big directional leg in *this* window. Lesson: the screen improves the *odds* and
    the *drawdown profile*, but the realized 3-month PnL still needs an actual trend to show up.
- **Selection clearly improved risk even when PnL was negative.** Drawdowns on the low-noise selected
  symbols were far shallower: SPY 4.2%, MSFT/QQQ/PLTR-Supertrend 11–16%, vs AMD's 33–39%. Picking by
  noise bought materially smoother equity curves.
- **Same symbol, opposite outcomes (PLTR):** Supertrend +26.1% vs HalfTrend −28.5%. Identical
  underlying; the difference is purely trade frequency — HalfTrend's 52 flips get whipsawed by PLTR's
  noise where Supertrend's 28 patient trades do not. The *strategy × symbol-noise* interaction, not
  the symbol alone, determines the result.
- **Mean-reversion (#2) still has no positive edge** — breakeven on its ideal symbol was the ceiling;
  it lost on every real stock. Conclusion from the 8-month run stands.

**Net:** selecting symbols by character is worth doing — it found #3's two winners and gave #2 its only
non-loss, and it reliably reduced drawdown — but it does not manufacture an edge that isn't there. The
strategies remain window- and symbol-dependent; none is robust enough to deploy. (Same caveats as
above: recon ≈ originals, 100% equity sizing, one timeframe, modest samples, UI-read figures.)

---

**Sources:**
- TradingView Strategies library — https://www.tradingview.com/scripts/?script_type=strategies
- TradingView Editor's Picks — https://www.tradingview.com/scripts/editors-picks/
- HalfTrend (canonical indicator, everget) — https://www.tradingview.com/script/U1SJ8ubc-HalfTrend/
- HalfTrend mechanics — https://pineify.app/resources/blog/half-trend-indicator-tradingview-pine-script
- Options360 author page — https://www.tradingview.com/u/Options360/
- Supertrend (KivancOzbilgic) — https://www.tradingview.com/script/r6dAP7yi-Supertrend/
- Recon Pine sources (this repo) — `Docs/Strategies/pine/{halftrend_snipermonkey,universal_strategy_feed,supertrend_kivanc}_recon.pine`
- Symbol-selection screener (this repo) — `Docs/Strategies/pine/trendiness_screener.pine`
