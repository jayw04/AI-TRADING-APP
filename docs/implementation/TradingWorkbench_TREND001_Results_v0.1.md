# TREND-001 Trend Following — Results (v0.1)

| Field | Value |
|---|---|
| Program | **TREND-001 — Trend Following** (time-series absolute trend) |
| Plan | `TradingWorkbench_TREND001_TrendFollowing_Plan_v0.1.md` **v0.2 (frozen, owner-approved)** |
| Experiment | `EXP-20260624-153254-trend001` · seed 17 · SEP survivorship-free 2000-01-01..2026-06-12 · n=200 |
| Construction | V1: per-name **close > 200-day SMA** → hold in-trend names equal-weight (1/N each → gross = #in-trend/N), **cash the rest**; weekly Monday rebalance |
| Evidence package | `docs/implementation/evidence/trend_001_trend_following/trend_following.{json,md}` |
| **Verdict** | 🟡 **B — Diversifier / Defensive** (a defensive participation sleeve; no standalone edge) |

---

## 1. Headline

| Book | CAGR | Sharpe | maxDD | Calmar |
|---|---|---|---|---|
| Equal-weight (benchmark) | +5.63% | 0.35 | −69.2% | 0.08 |
| Momentum (v1.1) | +7.39% | 0.39 | −76.4% | 0.10 |
| **Trend Following** | +4.73% | **0.46** | **−46.2%** | 0.10 |
| Momentum+Trend blend (50/50) | +6.80% | 0.43 | −62.6% | 0.11 |
| Regime-filter eqw (control) | +4.90% | 0.39 | −61.1% | 0.08 |

**Participation works as designed:** trend gross exposure averages **0.62** and falls to a
**0.015 minimum** — i.e. the book stands almost entirely in cash at the worst of the
2008 / 2020 / 2022 downturns. That is the mechanism, not a bug: trend following gives up
upside (lowest CAGR) to buy drawdown protection.

## 2. Hypotheses (pre-registered, frozen plan v0.2 §4)

**H1 — standalone risk-adjusted edge (trend vs equal-weight): does NOT clear.**
- ΔSharpe **+0.11, paired 95% CI [−0.11, 0.33]** — straddles zero. No decisive standalone edge.
- Walk-forward: trend beats equal-weight on Sharpe in **4/5** windows (only the 2000–2005
  dot-com-unwind window is negative, −0.04).

**H2 — diversifier via low correlation / blend: does NOT clear.**
- corr(trend, momentum) = **0.871** — high. Trend shares momentum's "winners-keep-winning"
  DNA, so it is *not* a low-correlation diversifier (unlike LOW-001's −0.15).
- Blend vs momentum-alone ΔSharpe **+0.04, CI [−0.095, 0.165]** — straddles zero.

**H3 — downside protection / participation, _beyond the existing regime filter_: CLEARS (the signature).**
- Trend maxDD is **+30.2%** shallower than momentum (−46.2% vs −76.4%) and **+23.0%** shallower
  than equal-weight; shallower than equal-weight in **5/5** walk-forward windows.
- **The decisive test (plan §5.5):** the platform already de-risks the whole book when SPY is
  below its 200-day MA. Does *per-name* trend add anything beyond that portfolio-level filter?
  **Yes** — trend beats the regime-filter control on **both** Sharpe (+0.06) and maxDD
  (**+14.9%** shallower: −46.2% vs −61.1%). Per-name trend timing is materially better than the
  market-level switch the platform already ships.
- Cost-robust: trend Sharpe **0.47 / 0.46 / 0.43 / 0.35** at 5 / 10 / 20 / 50 bps.

## 3. Verdict: B — Diversifier / Defensive

Per the frozen verdict tree (B = *"H1 fails but H2 **or** H3 clears beyond the existing regime
filter"*): H1 fails, H2 fails, but **H3 clears decisively and beyond the regime filter** → **B**.
Trend Following is a **defensive participation sleeve** — not standalone alpha, not a
low-correlation diversifier, but a genuine, cost-robust drawdown-management overlay that
improves on the market-level regime filter already in production.

**The pre-registered prior was refuted — in trend's favour.** The modal outcome was
**C — Rejected (40%)**, on the thesis that the existing regime filter would *subsume* the
benefit. The data rejected that thesis: per-name trend beat the portfolio-level filter on both
axes. This is the calibration story Evidence Engineering exists to capture — a recorded
prediction, an honest comparison, an outcome that moved against the prior.

**Product impact:** a candidate **participation/defensive sleeve** in the risk dial (or a
momentum+trend blend), evidence-gated; *not* a standalone book. Next, pre-registered: a V2
(inverse-vol sizing of the in-trend sleeve, or multi-window trend consensus) only if a sharper
standalone edge or lower correlation is wanted — the V1 stopping rule is satisfied (a real
defensive value was found, so it is not archived).

## 4. Methodology note — a verdict-logic correction (transparency)

The first run of the harness printed **D — Inconclusive**. On review this was a *tooling* bug,
not a data result: the verdict code carried an extra `corr < 0.7` gate on the B branch that is
**not in the frozen plan's B-trigger** (the plan triggers B on "H2 **or** H3", and H3 cleared).
The gate was removed so the code faithfully implements the pre-registered tree, the verdict
logic was extracted into a pure, unit-tested function (`classify_outcome`, with the A/B/C/D cases
— including this exact scenario — locked by tests), and the study was re-run. **No statistic
changed** (same seed, same data, same simulator → byte-identical books/CIs); only the derived
verdict string was corrected, D → **B**. Recording the correction rather than silently shipping
either string is the same self-correction discipline as the SCAN-001 prototype catching its own
ATR tautology — the pre-registered plan, not the code that drifted from it, is the source of truth.

## 5. Caveats / honest boundaries

- Long-only equity adaptation of a strategy that classically uses **shorts + futures** — the
  "cash, don't short" construction captures the defensive half only.
- High correlation with momentum (0.871) means trend is **not** a portfolio diversifier the way
  Low Volatility is; its value is on the **timing/drawdown** axis.
- The regime-filter control uses **market breadth** (ADR 0022, vendor-free) as the market proxy
  because SPY is absent from the SEP store (the P12 §1 data gap); a SPY-based control is a
  follow-on.
- 200-day SMA window frozen (the platform's regime-filter window); no sweep — alternative
  windows / the 252-day return-sign signal are pre-declared **future variants**.

_Per ADR 0014 + the TREND-001 gate. No parameter introduced solely to improve historical
performance. The evidence package is the deliverable._
