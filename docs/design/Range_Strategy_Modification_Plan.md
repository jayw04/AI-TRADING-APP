# Range Strategy — Modification Plan (APPROVED, rev. 2)

**Status:** APPROVED by owner (9.8/10) with modifications, now folded in (`review-comments.md`).
**Inputs:** owner review of the EOD report (`Range_BuySell_Formula_Study.md`, 2026-06-30) →
modification plan → owner review of the plan.
**Scope:** a *research* iteration. The live strategy (#1 "Range Trader NVDA", on the EC2 paper
box) is **not touched**; work happens in the existing **backtest harness** (no research clone).
Structural code lands default-off; anything that reaches production gets an ADR.

---

## 1. Principles
1. **One variable per phase** — isolated hypotheses, attributable results.
2. **Research-first** — evaluated in backtest over a **3-year window** (regime coverage) before any live decision.
3. **Preserve identity** — a *range-fade* strategy; modes are *added alongside* and compared, never silently swapped.
4. **Capital unchanged** — a bigger Opportunity Set raises *evidence*, not exposure.
5. **"No trade" is valid** — central to the trend-filter work.
6. **Promotion is evidence-gated** — by the §4 gate, never by P&L alone.

## 2. The engine already supports much of this (param sweeps, not builds)
| Recommendation | In code? | Knob |
|---|---|---|
| Support **zone** / modes B,C | ✅ | `entry_zone_pct`, `entry_zone_atr_mult` × `atr20_pct` |
| VWAP filter (mode D) | ✅ partial | `vwap_gate_pct` |
| Stop width | ⚙️ | `stop_buffer_pct` (fixed %) — ATR-scaling & time-stop are new |
| Opportunity Set size | ✅ | `auto_select_top_n` |
| Partial exits | ✅ | `scale_out_pct` / `scale_out_target_pct` |
| Bounce confirmation, entry-delay, ATR-stop, time-stop, trend filter, regime classifier, oscillation score, candidate-explainability, MAE/MFE, opportunity funnel, symmetric short | ❌ new | (built per phase, default-off) |

---

## 3. Research sequence (owner's preferred order: **Instrumentation → Entry → Trend → Stop → Candidate**)

> Cross-cutting from Phase 0 onward: a **Regime Classifier** runs *passively* on every backtest
> bar — labels each day **Trend / Range / Neutral** (from SPY trend + OR-width + VIX) and records
> stats. It does **not** gate trades yet; it's for *learning* ("after ~200 days you know exactly
> where Range Trader works"). It also lets every later phase be segmented by regime.

### Phase 0A — Trading metrics  *(do first)*
- **MAE** (max adverse excursion), **MFE** (max favorable excursion), **holding time**,
  **time-to-entry** — per trade + aggregate, added to the backtest result.
- *Gate:* META's stop-then-target story is reproduced numerically (high MAE, MFE>target after exit).

### Phase 0B — Opportunity Funnel  *(permanent platform KPI)*
- Per run: **Universe → Qualified → Selected → Touched-entry → Entered → Stopped → Exited**.
- Promoted to a **permanent dashboard KPI** (not just a research artifact) — it answers *why* only
  1 of 5 traded, every day, forever.

### Phase 1 — Entry-mode comparison  ⭐⭐⭐⭐⭐
- Modes **A** exact-low (baseline) · **B** zone +0.15% · **C** zone +0.25·ATR · **D** VWAP-pullback ·
  **E** bounce-confirmation (5-min close back above zone / VWAP reclaim / higher-low — *new code*).
- A–D are pure param sweeps; only E is new. 3-yr backtest, all modes, segmented by regime.
- **Carry the TOP 2** forward (not one) — 3 years isn't enough to know if regime flips the best mode.
- *Fixed:* stop 0.5%, universe 5, long-only.

### Phase 1.5 — Entry delay  *(cheap, between Entry and Trend)*
- **Wait N min (start 5) after first touch; enter only if support held.** New, tiny code.
- Run against each Phase-1 finalist; keep if it improves quality without killing participation.

### Phase 3 — Trend-day filter  ⭐⭐⭐⭐  *(moved BEFORE stop — today wasn't a range day)*
- Gate: if **strong trend** (SPY-trend + OR-width + VIX — **no ADX yet**, all three already
  available) → disable entries that day.
- Phase-1/1.5 config, with vs without the gate, segmented Trend vs Range days via the classifier.
- *Gate:* expectancy improves on trend days with acceptable lost opportunity on range days.

### Phase 2 — Stop study  ⭐⭐⭐⭐
- Compare **three**: fixed 0.5% · **ATR-scaled `max(0.5%, 0.8·ATR%)`** · **time-stop (exit after 90 min)**.
  (Some range trades simply *expire*.) Hold the Phase-1/1.5/3 winner fixed; vary only the stop.
- *Gate:* fewer premature stop-outs, no material DD increase; MAE distribution shifts.

### Phase 4 — Opportunity Set + Candidate Engine  ⭐⭐⭐
- **4a:** `auto_select_top_n` **5 → 8–10** for research (capital fixed via `per_position_budget`).
- **4b:** add **Intraday Oscillation Score** (avg support↔resistance crossings over prior 20 days =
  *range*, not *volatility*) — **with explainability labels** (e.g. `AMD: High ATR · High Oscillation
  · High RVOL → Score 87`) so selection is auditable/calibratable.

### Phase 5 — Symmetric short (research only)  ⭐⭐  *(left last — no rush)*
- Isolated research only; **production stays long-only**. Measure if the short side carries edge.

### Deferred — Adaptive (morning→afternoon) levels
- Most invasive; **not** hourly recalculation. Its own ADR, only if participation is still too low after 1–3.

---

## 4. Promotion gate (owner-set — a mode/variant is "better" only if ALL hold)
| Metric | Minimum |
|---|---|
| Trades | **> 100** |
| Profit factor | **> 1.2** |
| Win rate | **> 50%** |
| Max drawdown | **not worse than baseline** |
| Expectancy | **positive** |
| Bootstrap CI (mean return) | **above zero** |

Never P&L alone.

## 5. Resolved decisions (owner)
| Q | Decision |
|---|---|
| Backtest window | **3 years** (bull/bear/sideways/volatile/quiet) — not 12 months |
| Trend indicator | **SPY trend + OR-width + VIX** now; ADX only later if needed |
| Research vehicle | **existing backtest harness** — no clone (less code, more evidence) |
| Sequence | 0A → 0B → 1 → 1.5 → 3 → 2 → 4 → 5 (**trend before stop**) |
| Winner selection | **Top 2**, not one |

## 6. Deliverables per phase
- A dated section in `Range_BuySell_Formula_Study.md` with the comparison table + an
  evidence-backed, gate-checked recommendation (segmented by regime).
- The **Opportunity Funnel** becomes a permanent dashboard KPI (Phase 0B).
- New code default-off; structural changes (bounce, entry-delay, ATR/time stop, trend gate,
  short) each get an ADR before any live activation.
- Candidate for a Whitepaper **Evidence-Engineering case study**.

---

**Implementation starts now at Phase 0A** (trading metrics) — pure instrumentation, zero behavior
change — then Phase 0B (the funnel KPI). These unblock everything else.
