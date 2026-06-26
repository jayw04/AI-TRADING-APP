# Trading Workbench — Range Trader: Rejection Evidence Package (v0.1)

| Field | Value |
|---|---|
| Document | **Range Trader — formal Rejection Evidence Package.** Completes the §5c research program (adds walk-forward + bootstrap) and records the governance verdict. |
| Date | 2026-06-21 |
| Status | **REJECTED — archived as the platform's FIRST formally-rejected strategy.** Do NOT paper-trade. |
| Strategy | `RangeTraderVWAP` (intraday mean-reversion, VWAP±σ dynamic bands) — the best-performing variant from the prior research. |
| Hypothesis | *RangeTraderVWAP has a robust, statistically-significant intraday mean-reversion edge.* |
| Governing | **ADR 0014** (backtests = primary eval ground-truth) · the §5c pre-registered gate · the Strategy Roadmap evidence gate. |
| Artifacts | `scripts/range_evidence.py` + `docs/implementation/evidence/range_rejection/range_evidence.{json,md}`; prior `..._RangeTrader_5c_TestResults_v0.1.md`. |

---

## Why this document exists

The owner's strategic review (`comments.md`, post-P14/P13.5) elected to **formally complete and archive
the Range Trader rejection** — to demonstrate, with a citable artifact, that *the platform validated
**and** declined a strategy.* "Most software can validate; very few can reject." This is the second
platform-declined strategy after the SF1 multi-factor book (P14), and the **first** carried all the way
to a formal *Rejected* archive.

Range Trader was already researched and rejected on 2026-06-16 (§5c gate + IS/OOS). This package adds
the two pieces that prior work lacked — **walk-forward** and a **trade-level bootstrap CI** — and
records the governance verdict.

## 1. The decisive test — full-window edge + bootstrap

Best prior config (the *only* one that ever cleared IS): `RangeTraderVWAP` PLTR, partial-reversion
`entry_sigma=2.0 / exit_sigma=0.5 / stop_sigma=3.0`, 2026-01-02 → 2026-06-12, Alpaca IEX 5-min RTH.
(`EXP` reproducible: seed 17, 2000 resamples; `range_evidence.json`.)

| Metric | Value |
|---|---|
| Trades | 102 |
| Profit factor | **1.271** (below the 1.3 bar) |
| Mean per-trade P&L | $15.14 |
| Win rate | 54.9% |
| **Bootstrap 95% CI of mean per-trade P&L** | **[−$19.74, +$57.53]** |

> **The bootstrap CI spans zero ⇒ no statistically demonstrable edge.** Even ignoring the sub-1.3
> profit factor, the per-trade expectancy is indistinguishable from breakeven at 95% confidence. This
> is the load-bearing result.

## 2. Walk-forward consistency

| Window | Trades | Profit factor | Mean P&L |
|---|---|---|---|
| 2026-01-02 → 02-11 | 29 | 1.691 | $49.23 |
| 2026-02-11 → 03-23 | 25 | 1.141 | $7.10 |
| 2026-03-23 → 05-02 | 30 | 1.325 | $12.88 |
| 2026-05-02 → 06-12 | 22 | 0.886 | −$6.37 |

3 of 4 sub-windows were nominally profitable (PF>1), but the edge **decays monotonically** across the
window (1.69 → 1.14 → 1.33 → **0.89**) and the **most-recent window is a loss** — the opposite of a
durable edge. With a full-window PF below the gate *and* a bootstrap CI that spans zero, this
walk-forward profitability is noise, not signal. (Intraday history is ~6 months = **one regime**, an
honest depth limit on walk-forward — but the bootstrap on the full 102-trade set is the decisive test.)

## 3. Prior evidence (consolidated, 2026-06-16)

The §5c pre-registered gate (frozen criteria: ≥50 trades, PF≥1.3, OOS PF≥max(1.0, 0.8·IS), robustness)
was run across **two strategy variants** (fixed-level + VWAP±σ), **multiple universes** (daily-range
large-caps; intraday-oscillation ETFs XLF/QQQ/XLE/PLTR), and **σ-sweeps**:

- Fixed-level on daily-range large-caps → too few trades (13–23), all **INCONCLUSIVE**.
- VWAP±σ solved trade count (63–98) but **every IS-passing config collapsed OOS**: PLTR deep-entry IS
  PF 1.24 → OOS 0.85; **best** = partial-reversion exit IS PF 1.37 (cleared 1.3) → **OOS PF 0.92 = NO-GO**.

The §5c gate *correctly prevented activating a curve-fit edge* — the signature the OOS check exists to
catch. (Details: `..._RangeTrader_5c_TestResults_v0.1.md`.)

## 4. Governance verdict

| Gate | Result |
|---|---|
| §5c pre-registered gate (2026-06-16) | **NO-GO** (OOS collapse; PF<1.3 OOS) |
| Walk-forward (this package) | not robust (one-regime; profitability is noise) |
| **Bootstrap mean-P&L 95% CI** | **[−$19.74, +$57.53] — includes zero ⇒ no edge** |
| **Verdict** | **REJECTED** |

Per ADR 0014 and the Strategy Roadmap evidence gate, a strategy earns paper/live **only** with a
robust, statistically-significant edge. Range Trader does not clear that bar.

## 5. Archive

**Range Trader (intraday mean-reversion) is the platform's first formally-rejected strategy.** Do NOT
paper-trade. The `range@local`/`ALPACA_PAPER_1` account stays unused; the idle `Range Trader NVDA/AAPL`
strategies remain IDLE. **Infrastructure is kept** (the §5c gate, the bar-count metric, the
oscillation screener, the VWAP±σ variant, and now `range_evidence.py`) — it is reusable for the next
intraday strategy.

> **A future research cycle may revisit intraday mean-reversion as a *brand-new hypothesis* (e.g.
> "First-Hour Fade" — the prior diagnostic found 62% of the edge concentrated at 10:00 ET), with its
> own ADR, hypothesis, and evidence package — NOT as "Range Trader v2."** (Owner's Option 2, future.)

## What this proves (the point)

The platform took a real strategy, gave it every fair chance (two variants, multiple universes,
σ-sweeps, IS/OOS, walk-forward, bootstrap), and **declined it on the evidence** — cleanly, reproducibly,
and on a pre-registered bar that could not be moved after seeing results. That capability — to reject,
not just validate — is the Evidence Engineering moat.
