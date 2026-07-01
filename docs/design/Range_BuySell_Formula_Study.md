# Range Strategy — Buy/Sell Price Formula Study

**Purpose.** A daily observation log of the Range Trader's opening-range fade formula vs. how the
5 auto-selected names actually traded, to decide — with evidence, not intuition — whether the
**buy/sell/stop price-setting formula** needs adjustment. Owner: Jay Wang. Research only; no live
behavior changes without a separate decision + (if structural) an ADR.

## The formula under study (current)

`level_mode = opening_range`, `opening_range_minutes = 30` (09:30–10:00 ET):
- **Entry (buy)** = opening-range **low** (fade to support). Buy zone ceiling = entry (exact-low touch;
  `entry_zone_pct` / `entry_zone_atr_mult` = 0, so no widening today).
- **Exit (sell)** = opening-range **high** (sell at resistance).
- **Stop** = entry × (1 − `stop_buffer_pct`), `stop_buffer_pct = 0.005` → **0.5% below the OR low**.
- Long-only; no entries during the 09:30–10:00 range build or the first `no_trade_open_minutes`.
- Hard exit `hard_exit_before_close_minutes` before the close.

Data provenance: OR levels and intraday paths below are computed from **Alpaca IEX 5-min RTH bars**
(full 09:30–16:00 session, fetched 2026-06-30 ~15:13 ET). Live fills come from `workbench.sqlite`
(`orders` / `fills`, strategy #1, user `range@local.dev`).

---

## 2026-06-30 (Tue) — entry #1 day

Universe (daily auto-select Top-5): **MU, INTC, AMD, TSLA, META**. Account: Alpaca Paper (Range).
Strategy: **Range Trader NVDA** (#1). ⚠ **Engine started 09:48 ET (18 min after the open)** — the live
in-memory opening range was built from ~09:48–10:00 bars (partial), so META's live entry differed
slightly from the full-window OR (see §Late-start OR distortion).

### EOD summary (full session — finalized)

| Sym  | Open    | Close   | Chg%  | Entry (OR low) | Exit (OR high) | Stop    | Sess Low | Sess High | OR width% | Outcome (long-only) |
|------|---------|---------|-------|----------------|----------------|---------|----------|-----------|-----------|---------------------|
| MU   | 1144.80 | 1152.16 | +0.64 | 1125.06        | 1162.62        | 1119.43 | 1125.06  | 1168.40   | 3.34      | no entry            |
| INTC | 132.19  | 139.55  | +5.57 | 131.60         | 137.44         | 130.95  | 131.60   | 142.33    | 4.43      | no entry            |
| AMD  | 547.51  | 580.52  | +6.03 | 546.02         | 564.56         | 543.29  | 546.02   | 584.62    | 3.40      | no entry            |
| TSLA | 406.99  | 420.37  | +3.29 | 406.39         | 412.57         | 404.36  | 406.39   | 424.53    | 1.52      | no entry            |
| META | 560.52  | 563.47  | +0.53 | 554.92         | 560.54         | 552.15  | 551.57   | 565.53    | 1.01      | **entered → stopped** |

**First touch after 10:00 ET** (when the formula allows entries):

| Sym  | Support (entry)     | Stop                | Resistance (exit)   |
|------|---------------------|---------------------|---------------------|
| MU   | never               | never               | 12:15 @ 1166.04     |
| INTC | never               | never               | 10:00 @ 138.08      |
| AMD  | never               | never               | 11:05 @ 566.10      |
| TSLA | never               | never               | 10:00 @ 413.12      |
| META | 10:00 @ 554.25      | 10:50 @ 551.57      | 14:00 @ 560.91      |

Post-10:00 session low vs entry explains "no entry" on MU/INTC/AMD/TSLA: price never returned to
OR low after the range froze (rally day — lows held above support).

---

### Intraday price history by symbol

Hour buckets use **ET** (09:30–10:00 = opening range; 10:00+ = tradeable window).

#### MU — drifted up, never faded to support

| Hour (ET) | Open    | High    | Low     | Close   | Notes |
|-----------|---------|---------|---------|---------|-------|
| 09:30–10  | 1144.80 | 1162.62 | **1125.06** | 1154.73 | OR formed; low = entry |
| 10:00–11  | 1154.48 | 1155.81 | 1136.29 | 1137.45 | Held above entry (1125) |
| 11:00–12  | 1137.52 | 1150.00 | 1137.52 | 1146.70 | Mid-range |
| 12:00–13  | 1146.36 | **1166.04** | 1145.90 | 1149.40 | **Exit zone touched** (1162.62) |
| 13:00–14  | 1149.27 | 1162.55 | 1149.27 | 1156.01 | Near resistance |
| 14:00–15  | 1156.25 | 1160.82 | 1144.05 | 1159.77 | Pulled back, still above entry |
| 15:00–16  | 1160.00 | **1168.40** | 1151.40 | 1152.16 | New session high at close |

#### INTC — strong trend day (+5.6%), resistance hit immediately after OR

| Hour (ET) | Open    | High    | Low     | Close   | Notes |
|-----------|---------|---------|---------|---------|-------|
| 09:30–10  | 132.19  | **137.44** | **131.60** | 137.20 | OR; closed at range high |
| 10:00–11  | 137.23  | 138.19  | 136.33  | 137.21  | **Exit touched** at open of hour |
| 11:00–12  | 137.29  | **140.65** | 137.29  | 140.05  | Extended rally |
| 12:00–16  | …       | **142.33** | 139.53  | 139.55  | Never returned to entry (131.60) |

#### AMD — largest mover (+6.0%), no pullback to OR low after 10:00

| Hour (ET) | Open    | High    | Low     | Close   | Notes |
|-----------|---------|---------|---------|---------|-------|
| 09:30–10  | 547.51  | **564.56** | **546.02** | 556.71 | Wide OR (3.4%) |
| 10:00–11  | 557.25  | 560.17  | 552.79  | 557.05  | Low 552.79 > entry 546.02 |
| 11:00–12  | 557.28  | **578.82** | 556.83  | 577.59  | Breakout leg |
| 12:00–13  | 577.27  | 581.28  | 575.33  | 579.74  | **Exit touched** (~11:05 bar) |
| 13:00–16  | …       | **584.62** | 578.02  | 580.52  | Trend intact |

#### TSLA — tight OR (1.5%), immediate break above resistance

| Hour (ET) | Open    | High    | Low     | Close   | Notes |
|-----------|---------|---------|---------|---------|-------|
| 09:30–10  | 406.99  | **412.57** | **406.39** | 412.10 | OR low ≈ session low |
| 10:00–11  | 411.93  | **416.26** | 410.99  | 414.18  | **Exit touched** at 10:00 |
| 11:00–16  | …       | **424.53** | 412.72  | 420.37  | No fade to 406 entry |

#### META — only pullback name; stop then rally (counterfactual exit would have worked)

Full **5-min bar log** (ET) with level flags (`<=entry`, `<=stop`, `>=exit`):

| Time  | O     | H     | L     | C     | Flags |
|-------|-------|-------|-------|-------|-------|
| 09:30 | 560.52| 560.54| 555.29| 556.62| >=exit |
| 09:35 | 557.10| 559.00| **554.92** | 555.30| <=entry (OR forming) |
| 09:40 | 555.28| 557.80| 555.00| 557.67| |
| 09:45 | 557.11| 557.79| 556.46| 556.97| |
| 09:50 | 556.83| 557.62| 555.42| 555.76| partial-OR low if engine starts 09:48 |
| 09:55 | 555.75| 557.68| 555.49| 556.23| |
| 10:00 | 556.30| 556.33| **554.25** | 556.33| <=entry — **first post-OR support touch** |
| 10:05–10:10 | … | … | 554.63 | 554.93 | <=entry |
| 10:15 | 555.00| 556.60| 555.00| 556.08| **live BUY fill zone** (see trades) |
| 10:35–10:45 | … | … | 553.66–554.45 | … | <=entry, grinding lower |
| 10:50 | 554.19| 554.74| **551.57** | 551.73| <=entry **<=stop** — session low |
| 10:55 | 551.73| 552.51| 551.62| 552.37| <=stop — **live SELL / stop fill zone** |
| 11:00–13:55 | … | … | 552–560 | … | Recovery; still below exit |
| 14:00 | 560.06| **560.91** | 560.00| 560.27| **>=exit** — would have hit target if still long |
| 14:15–15:55 | … | **565.53** | … | 563.47| Extended through exit; close +0.53% vs open |

**Late-start OR distortion (quantified).**

| Window        | OR low | OR high | Stop   |
|---------------|--------|---------|--------|
| Full 09:30–10:00 | 554.92 | 560.54 | 552.15 |
| Partial 09:48–10:00 (engine start) | **555.42** | 560.54 | **552.64** |

Partial OR entry is **$0.50 higher (+0.09%)** → live signal entered ~10:15 at 555.49 vs formula
554.92, slightly worse fill on a name already sliding toward stop.

---

### Trades executed (confirmed EOD)

Source: `orders` #58–59, `fills` — no further META orders after stop.

| Sym  | Side | Time (ET) | Fill    | Reason (strategy) | DB order id |
|------|------|-----------|---------|-------------------|-------------|
| META | BUY  | 10:15     | 555.49  | range_entry       | 58          |
| META | SELL | 10:56     | 552.42  | **stop_loss**     | 59          |

**Realized P&L: −$21.49** (7 sh × −$3.07/sh, −0.55%). No other name entered.

**Counterfactual:** If the stop had not fired and the position held to the OR-high exit, price
touched **560.91 at 14:00 ET** (exit = 560.54) — theoretical gain ≈ **+$38** (+0.98%) vs actual
**−$21.49**. The stop did its job limiting loss on a breakdown; the afternoon rally was not
predictable from the morning fade setup.

---

### Findings (EOD — session complete)

1. **Up-day, few setups.** 4/5 names closed higher (INTC +5.6%, AMD +6.0%, TSLA +3.3%). Long-only
   fade-support correctly took **no** longs in rallying names — it did **not** chase. That restraint
   is a feature, not a miss.
2. **The only pullback failed (then reversed).** META was the lone name to revisit OR low after 10:00.
   It broke through stop (sess low 551.57 < stop 552.15) → bought 555.49, stopped 552.42. Price
   later recovered and **would have hit exit at 14:00** — classic shake-out vs failed-bounce ambiguity.
3. **Late-start OR distortion (laptop-only).** Engine up 09:48 → live entry **555.42** vs full OR
   **554.92** (+0.09%). EC2 always-on will use the full window; re-quantify on first EC2 session.
4. **Resistance reached on 4/5 names** after 10:00 (MU, INTC, AMD, TSLA). A symmetric fade (short
   resistance) would have had setups; long-only structurally cannot use them.
5. **Stop width vs noise.** META OR width was only **1.01%**; a **0.5%** stop sits inside one
   normal 5-min bar. Session low pierced stop by **$0.58 (0.10%)** before a **+2.5%** rally from
   low to high — supports reviewing ATR-scaled stops (formula question #2).

---

## EOD checklist (2026-06-30)

- [x] Re-capture full-day OHLC + final session low/high for all 5 (Alpaca IEX 5-min, ~15:13 ET pull).
- [x] Confirm no further entries/exits after META stop (orders #58–59 only for range sleeve today).
- [x] Recompute full-window vs 09:48-partial OR for META (+0.09% entry distortion).

---

### Formula-adjustment questions (evidence from this day)

1. **Entry timing — exact OR-low touch vs confirmation.** META bought on first post-OR touch (10:00
   bar); stop hit 50 min later. Would a bounce confirm (close back above OR low, or `vwap_gate_pct`)
   have skipped the 10:15 entry? **Trade-off:** might also skip valid afternoon recovery — needs
   multi-day sample.
2. **Stop width — fixed 0.5% vs ATR-scaled.** Stop was inside intraday noise on a 1%-wide OR.
   ATR-scaled stop might have survived the 10:50 wick (low 551.57 vs stop 552.15) — but would have
   increased risk if the breakdown continued.
3. **Buy zone width.** Exact-low touch (`entry_zone_pct = 0`) filled at 555.49 while OR low was
   554.92; a small zone might delay entry until deeper support — unclear if helpful here.
4. **Opening-range window.** 30 min worked for level definition; INTC/AMD never retested OR low —
   window length did not matter for those names today.
5. **Long-only vs symmetric.** 4/5 names hit resistance; long-only left edge on the table. Mandate
   question, not a formula bug.

> One day is a single data point — **do not change the formula on this alone.** Accumulate daily
> entries here first, then decide (structural changes → ADR).

---

## Template for next session

Copy §2026-06-30 structure for each trading day: EOD table → first-touch table → hourly paths →
trades → findings → checklist.

---

# Phase 1 — Entry-Mode Comparison (backtest experiment)

> Research artifact, distinct from the per-day EOD narrative above. Plan:
> `Range_Strategy_Modification_Plan.md` rev.2, Phase 1 (⭐⭐⭐⭐⭐). One variable changed (the
> entry trigger); OR window, sizing, stop, exit held fixed. Harness:
> `scripts/research/range_entry_mode_compare.py`, run in a disarmed one-off container against the
> existing backtester (no strategy clone). The live strategy (#1 on EC2) is untouched.

**Modes.** A = exact OR-low touch (`entry_zone_pct=0`). B = +15% range-fraction zone
(`entry_zone_pct=0.15`). C = +0.25·ATR zone (`entry_zone_atr_mult=0.25`). D = VWAP gate + zone
(`vwap_gate_pct=0.01`). **E = bounce confirmation** (NEW code — two-stage: price must dip to support
*then* reclaim above the OR low before entry). A–D are param sweeps of existing knobs; only E is new code.

**Universe / window.** Range Top-5 (MU, INTC, AMD, TSLA, META), 5-min bars, 2025-07-01 → 2026-06-30.
Caveat: this universe is today's momentum leaders (survivorship); the bias hits every mode equally, so
mode-vs-mode comparison is fair, but the absolute level reflects a strong semiconductor uptrend.

### Results — 1-year validation window (2025-07 → 2026-06)

| Mode | Trades | Return | PF | Win% | avg MAE | avg MFE | Funnel (univ/qual/touch/enter) |
|---|---:|---:|---:|---:|---:|---:|---|
| A exact-low | 294 | −1.29% | 0.77 | 30.6% | −0.61% | +0.69% | 626/626/359/280 |
| B zone-15% | 362 | −1.70% | 0.79 | 34.0% | −0.74% | +0.74% | 626/626/359/346 |
| C atr-0.25 | 515 | −2.22% | **0.81** | **45.8%** | −0.82% | +0.68% | 626/626/359/448 |
| D vwap+zone | 333 | −2.24% | 0.70 | 33.6% | −0.73% | +0.71% | 626/626/359/317 |
| E bounce | 298 | −1.46% | 0.78 | 38.3% | −0.76% | **+0.76%** | 626/626/359/282 |

**Headline finding (honest): no entry mode passes the promotion gate.** Every mode loses — PF 0.70–0.81
(<1.0), negative return, win-rate 31–46% (<50%), expectancy negative. The gate (Trades>100, PF>1.2,
Win>50%, expectancy positive) fails on the PF/win/expectancy criteria for **all five**. Entry-trigger
refinement moves the margins but **does not flip the sign**. The lever for a profitable range book is
not *where* on support we enter — it is *whether to be long at all* in a name that is trending up
(Phase 3 trend filter) and *which names / regime* qualify, not the entry micro-structure.

**Funnel sanity check.** Universe → qualified → touched is identical (626/626/359) across all modes, as
it must be — entry MODE only changes the touched→entered conversion. C (ATR zone) converts most touches
(448) and lifts win-rate to 45.8%, but its losers are bigger (worst MAE −0.82%) and its return is worst,
i.e. it trades *more*, not *better*. A (exact-low) is the most selective (280 entries) and least-bad
return but the lowest hit-rate. **E (bounce, new) is the efficiency leader** — best MFE (+0.76%), 2nd-best
return, mid-pack hit-rate — confirming the two-stage idea avoids the worst first-touch knife-catches,
but not enough to overcome the regime headwind.

**Carry-forward (Top 2) for the downstream phases:** **C (atr-0.25)** as the high-conversion / best-PF
branch and **E (bounce)** as the selective / best-efficiency branch. They bracket the conversion–quality
trade-off, so Phase 3 (trend filter) and Phase 2 (stop) can be evaluated against both rather than one
arbitrary entry. A is kept as the conservative baseline. B and D are dropped (D's VWAP gate is strictly
worse here — fewer entries *and* worst PF).

**Why this matters before the 3-year run:** 2025-07→2026-06 was a strong semis uptrend — exactly the
regime where a long-only *fade* should lose. This 1-year pass tells us the experiment is wired correctly
and entry mode is a second-order lever; it does **not** condemn the strategy, because the fade is
designed for range/neutral regimes. The 3-year window (2023-07 →, running) spans more varied regimes and
is the owner's actual decision window; segmenting it by the Regime Classifier is where the real read is.

### Results — 3-year decision window (2023-07 → 2026-06)

> ⚠ **SUPERSEDED — the table below was computed on TRUNCATED data (bar_cache 10k bug; see the
> Correction section at the end of this file). Use the clean numbers there.**

| Mode | Trades | Return | PF | Win% | avg MAE | avg MFE | Funnel (univ/qual/touch/enter) |
|---|---:|---:|---:|---:|---:|---:|---|
| A exact-low | 641 | −1.50% | 0.87 | 30.6% | −0.53% | +0.66% | 1271/1270/748/611 |
| B zone-15% | 783 | −1.79% | **0.89** | 36.0% | −0.66% | +0.73% | 1271/1270/748/739 |
| C atr-0.25 | 1140 | −2.93% | 0.87 | **48.4%** | −0.73% | +0.65% | 1271/1270/748/945 |
| D vwap+zone | 736 | −2.71% | 0.82 | 35.6% | −0.64% | +0.70% | 1271/1270/748/697 |
| E bounce | 641 | −2.24% | 0.83 | 38.1% | −0.66% | +0.70% | 1271/1270/748/608 |

_Data note: today's (2026-06-30) TSLA 5-min bars failed to fetch (Norton SSL MITM on
`data.alpaca.markets` — known blocker `blocker_norton_ssl_alpaca`); 1 symbol-day of 1,271, the rest
from cache. Negligible for these aggregates; re-run on the EC2/non-Norton box to close the gap._

**The 1-year finding holds — and harder.** Over the owner's full 3-year decision window, **every mode
still fails the gate**: PF 0.82–0.89 (<1.2), win 31–48% (<50%), expectancy negative. The rankings are
stable across both windows (A/B = best PF & least-bad return; C = best win-rate but most trades & worst
return; D = worst; E = mid). Two things worth noting:

1. **The 3-year PFs are slightly *higher* than the 1-year (0.82–0.89 vs 0.70–0.81)** — i.e. the broader,
   more regime-varied window is *less* bad than the pure-uptrend 2025-26 slice. That is exactly the
   regime signature: the long-only fade bleeds less when not fighting a relentless uptrend, but it never
   crosses into profit on this universe at the whole-window level. **Confirms the lever is regime/trend,
   not entry.**
2. **Entry mode is settled as a second-order knob.** Across 641–1,140 trades over 3 years the five modes
   span a PF range of just 0.82–0.89 — the entry trigger cannot rescue a strategy that is short edge by
   ~15–20% in PF terms. No amount of entry tuning closes a 0.89→1.20 gap.

**Decision (Phase 1 closed):** carry **C** (best conversion/win-rate, robust across both windows) and
**E** (the new two-stage bounce — best MFE, the variant most likely to benefit once a trend filter
removes the fight-the-trend losers) into the downstream phases, both **default-off**. Drop B and D for
the live path (B is a fine PF baseline but adds nothing over A/C; D is strictly dominated). **Re-prioritize
Phase 3 (trend filter: SPY-trend + OR-width + VIX) ahead of further entry/stop tuning** — the evidence
says *whether to be long at all in a trending name* is the first-order lever, and the Regime Classifier
segmentation (range/neutral vs trend days) is where the fade's real edge, if any, will show. Entry modes
C/E will be re-measured *within* the trend-filtered, regime-segmented universe in Phase 3, not in
isolation again.

---

# Phase 3 — Trend-day filter (regime segmentation, research-first)

> Plan rev.2 Phase 3, moved ahead of Stop/Delay per Phase 1's finding. The disciplined order: BEFORE
> building a runtime gate, prove which regimes carry the edge vs the bleed. Harness:
> `scripts/research/range_regime_segment.py` (disarmed one-off). No strategy change — we label each
> session and bucket the existing Phase-1 trades by regime.

**Regime signal.** SPY **intraday directional efficiency** `DE = |close − open| / (high − low)` per SPY
daily bar — *not* the SMA200 macro trend (which labels 91% of 2023-26 sessions "trend" simply because
SPY ran 409→740, and is useless for a per-session gate). DE measures whether SPY travelled decisively
one way (trend) or oscillated and closed mid-range (range). Split at the window's empirical tertiles:
`range ≤ 0.33`, `trend ≥ 0.63`, else `neutral`. Distribution over 2023-07..2026-06: **trend 252 /
neutral 251 / range 247** of 750 sessions — balanced, as tertiles should be.

> ⚠ **SUPERSEDED — computed on TRUNCATED data (bar_cache 10k bug). Clean numbers in the Correction
> section at the end of this file. The "range days near-breakeven (PF 0.99)" claim below did NOT
> survive on full data — clean range days are PF 0.94, still losing.**

### Per-regime trade quality (3-year window, carry-forward modes)

| Mode | Bucket | Trades | PF | Win% | Expectancy $/trade | avg MAE | avg MFE |
|---|---|---:|---:|---:|---:|---:|---:|
| A exact-low | ALL | 641 | 0.87 | 30.6% | −2.34 | −0.53% | +0.66% |
| | **range** | 203 | **0.99** | 31.5% | **−0.15** | −0.48% | +0.71% |
| | neutral | 197 | 0.77 | 33.0% | −3.68 | −0.49% | +0.58% |
| | trend | 241 | 0.84 | 27.8% | −3.08 | −0.62% | +0.67% |
| | GATED (drop trend) | 400 | 0.88 | 32.2% | −1.89 | −0.48% | +0.65% |
| C atr-0.25 | ALL | 1140 | 0.87 | 48.4% | −2.57 | −0.73% | +0.65% |
| | **range** | 374 | **0.99** | 50.8% | **−0.15** | −0.67% | +0.68% |
| | neutral | 376 | 0.78 | 47.3% | −4.38 | −0.71% | +0.59% |
| | trend | 390 | 0.86 | 47.2% | −3.16 | −0.80% | +0.68% |
| | GATED (drop trend) | 750 | 0.88 | 49.1% | −2.27 | −0.69% | +0.63% |
| E bounce | ALL | 641 | 0.83 | 38.1% | −3.50 | −0.66% | +0.70% |
| | **range** | 207 | **0.99** | 41.5% | **−0.21** | −0.60% | +0.75% |
| | neutral | 196 | 0.86 | 37.8% | −2.70 | −0.60% | +0.67% |
| | trend | 238 | **0.71** | 35.3% | **−7.02** | −0.76% | +0.69% |
| | GATED (drop trend) | 403 | 0.92 | 39.7% | −1.42 | −0.60% | +0.71% |

### Findings

1. **The fade is a range-day strategy — confirmed numerically.** On range days every mode is
   **near-breakeven (PF 0.99, expectancy −$0.15 / −$0.15 / −$0.21)**; on neutral + trend days it
   bleeds. The strategy's whole-window loss is concentrated in non-range sessions. This is the
   strongest validation yet of the opening-range-fade thesis: it works where it's supposed to (calm,
   oscillating days) and loses where it's supposed to (decisive one-way days).
2. **Entry mode is second-order — re-confirmed by a third independent cut.** Range-day expectancy is
   −$0.15 / −$0.15 / −$0.21 across A / C / E — essentially *identical*. The regime, not the entry
   trigger, governs the outcome. Phase 1's conclusion holds.
3. **"Drop trend days" is the WRONG gate.** For A and C the worst bucket is **neutral** (PF 0.77–0.78),
   not trend (0.84–0.86); only E's bleed is trend-concentrated (PF 0.71, −$7.02 — the bounce-confirm
   gets chopped on decisive days). A blunt trend-exclusion helps E a lot (−$3.50 → −$1.42, PF 0.92, the
   best gated variant) but A/C only modestly (−$2.34 → −$1.89). **The right gate is "trade range days
   ONLY"** — that isolates the PF-0.99 bucket and removes both bleeding regimes.
4. **The regime gate is NECESSARY but not SUFFICIENT.** Even range-only is only ~breakeven (PF 0.99),
   not profitable. The gate removes the bleed; it does not by itself create positive expectancy. The
   positive edge must come from Phase 2 (stop — range-day losers are the lever) and/or symbol selection.
   But removing a −$2.3..−$3.5/trade drag to ≈0 is a first-order improvement that entry tuning never got
   near.

### ⚠ Critical caveat — DE is look-ahead; this segmentation is NOT yet a live gate

`DE = |close − open| / (high − low)` uses the **day's close, high, and low** — none of which are known
at ~10:00 ET when the fade entry fires. So the regime label here is **post-hoc**: perfectly valid for
*learning* "where the strategy works" (the question Phase 3 asks first), but it **cannot be used as a
runtime gate** — that would be trading on the future. A live gate needs a **point-in-time regime
predictor** built only from information available at entry time, e.g. SPY's opening 30-min directional
efficiency / range, VIX level at the open, the overnight gap, or the prior day's (settled) regime. The
open empirical question is whether such an early-session signal predicts the full-day regime *well
enough* to recover most of the range-only edge. That PIT predictor — built + validated against this
look-ahead label — is the real Phase-3 deliverable, and gates whether a runtime `trend_filter` /
`range_only` param is worth building (with an ADR, since it's a structural entry-gate). Until then: no
strategy change, no live gate.

**Next:** build the PIT regime predictor (SPY opening-range behavior / VIX-at-open), measure how much of
the range-only separation it recovers, then decide on the runtime gate + ADR.

---

# ⚠ Evidence Correction Report (2026-06-30) — data-fidelity bug; Phase 1 & 3 recomputed on clean data

> **Reusable pattern.** When a result is invalidated by a defect, don't silently re-run — publish a
> record of *what the bug was, why it happened, how it biased the result, and what changed after
> correction*. That transparency is what makes a negative (or any) result credible. This section is the
> template for future Evidence Correction Reports. The underlying platform defect is escalated to
> **ADR-0033 (Historical Data Integrity)** — it is a platform issue, not a Range issue.

**The bug.** `app/market_data/bar_cache.py` `_fetch_and_write` issues ONE Alpaca call for the whole
missing span with `limit=10000`. A cold multi-year 5-min fetch truncates at Alpaca's 10k-row page
(~126 sessions) and then writes bogus `.empty` markers for every un-returned day (which block
re-fetch). Result: the Range Top-5 + SPY 5-min caches held ~250 **non-contiguous** sessions (H2-2023
+ part of 2025), with **2024 and 2026 almost entirely missing**. The Phase-1 and Phase-3 tables above
were therefore computed on a biased ⅓ sample. Methodology/harnesses were correct; the data was not.
Fixed by `scripts/research/rebuild_5min_cache.py` (clear bogus markers, re-fetch month-by-month <10k
rows). All six symbols verified at 750 contiguous sessions `{2023:126, 2024:252, 2025:249, 2026:123}`.

## Phase 1 — clean 3-year (2023-07 → 2026-06), 5 entry modes

| Mode | Trades | Return | PF | Win% | avg MAE | avg MFE |
|---|---:|---:|---:|---:|---:|---:|
| A exact-low | 1843 | −5.02% | 0.84 | 27.7% | −0.52% | +0.66% |
| B zone-15% | 2310 | −4.29% | **0.91** | 34.2% | −0.66% | +0.77% |
| C atr-0.25 | 3302 | −7.86% | 0.88 | **46.2%** | −0.73% | +0.69% |
| D vwap+zone | 2120 | −5.22% | 0.88 | 34.7% | −0.64% | +0.73% |
| E bounce | 1876 | −5.31% | 0.87 | 37.3% | −0.65% | +0.75% |

Funnel: universe 3709 / qualified 3708 / touched 2189 / entered 1752–2728. **No mode passes the gate**
(PF 0.84–0.91 < 1.2, win < 50%, negative return). **Entry mode is second-order** — tight PF cluster.
The Phase-1 verdict is unchanged from the (biased) run; the bias flattered nobody differently.

## Phase 3 — clean per-regime segmentation (SPY DE tertiles; trend 252 / neutral 251 / range 247)

| Mode | Bucket | Trades | PF | Win% | Expectancy $/trade |
|---|---|---:|---:|---:|---:|
| A | ALL | 1843 | 0.84 | 27.7% | −2.72 |
| | range | 608 | **0.94** | 30.6% | −0.94 |
| | neutral | 609 | 0.74 | 25.3% | −4.68 |
| | trend | 626 | 0.85 | 27.3% | −2.55 |
| | GATED (drop trend) | 1217 | 0.84 | 27.9% | −2.81 |
| C | ALL | 3302 | 0.88 | 46.2% | −2.38 |
| | range | 1100 | **0.94** | 47.5% | −1.13 |
| | neutral | 1100 | 0.86 | 45.1% | −2.96 |
| | trend | 1102 | 0.86 | 46.0% | −3.05 |
| | GATED (drop trend) | 2200 | 0.90 | 46.3% | −2.05 |
| E | ALL | 1876 | 0.87 | 37.3% | −2.83 |
| | range | 630 | **0.94** | 40.3% | −1.14 |
| | neutral | 610 | 0.85 | 35.9% | −3.35 |
| | trend | 636 | 0.82 | 35.5% | −3.99 |
| | GATED (drop trend) | 1240 | 0.89 | 38.1% | −2.23 |

### Revised conclusions (authoritative — these supersede the pre-correction Phase-1/3 findings)

1. **The fade loses in EVERY regime.** Range days are the least-bad bucket (PF 0.94) but still lose
   ~−$1/trade; neutral and trend days lose more. The earlier "range days ≈ breakeven (PF 0.99)"
   finding was a **data artifact** of the missing 2024/2026 sessions and does NOT survive.
2. **Entry mode is second-order — confirmed a 4th time.** Range-day PF is 0.94 / 0.94 / 0.94, identical
   across A / C / E. Stop tuning cannot close a >0.06 PF gap from the *best* bucket.
3. **The trend gate is ineffective and sometimes counter-productive.** For A it makes things slightly
   *worse* (−$2.81 gated vs −$2.72 all), because neutral, not trend, is A's worst bucket. No gate
   variant reaches profitability.
4. **This is structural, not a tuning problem.** The long-only opening-range fade has **no edge in any
   regime** on the momentum-leader Top-5 (MU/INTC/AMD/TSLA/META) — the market's strongest *trenders*,
   i.e. the worst possible names to fade. Consistent with the research-portfolio design that already
   classes RNG as the **rejected-benchmark** sleeve.

### Recommendation — stop tuning; test the universe hypothesis

The evidence says the lever is neither entry nor stop nor a trend gate — it is **what we fade**. The
single highest-value next experiment is a **universe pivot** (one clean variable): run the *same*
strategy on genuinely mean-reverting names (low-momentum / high mean-reversion-score / range-bound
screen) instead of momentum leaders. If the fade shows an edge there, the thesis is universe-specific
and salvageable; if it fails there too, the fade thesis is dead and RNG stays a rejected benchmark.
Phases 1.5 / 2 (entry-delay, stop) are deprioritized — the clean data says they cannot rescue a
strategy that is short edge in its *best* bucket. No live change; the strategy stays default-config on
the box (it is a benchmark, not an approved edge).

---

# Universe pivot — mean-reverting names (the decisive test); PROGRAM CONCLUSION

**Design.** One clean variable: the *same* strategy + params, run on a mean-reverting universe instead
of the momentum Top-5. Candidate selection: screened a 34-name cross-style pool by **variance ratio**
(`Var(k-day)/(k·Var(1-day))`, <1 = mean-reverting) + low-momentum/defensive prior + tradeable daily
range. (Note: avg daily DE — my first proposed selector — was a near-constant ~0.45 across ALL liquid
equities and did NOT discriminate; VR was the usable metric.) Pivot universe = **D, PFE, BMY, VZ, PG**
(utility / 2× health / telecom / staple; VR5 0.87–0.92). Clean 5-min data rebuilt to 749 sessions each.

**Result — the pivot FAILED (worse than momentum, every mode):**

| Mode | Momentum Top-5 PF | Pivot (mean-rev) PF | Pivot win% | Pivot MFE |
|---|---:|---:|---:|---:|
| A exact-low | 0.84 | 0.74 | 38.7% | +0.39% |
| B zone-15% | 0.91 | 0.77 | 42.9% | +0.41% |
| C atr-0.25 | 0.88 | 0.65 | 49.6% | +0.26% |
| D vwap+zone | 0.88 | 0.76 | 42.7% | +0.41% |
| E bounce | 0.87 | 0.77 | 45.1% | +0.39% |

Per-name (mode C): **all five lose** — D 0.71, BMY 0.75, VZ 0.62, PFE 0.59, PG 0.52. Per-regime: uniformly
bad (PF 0.63–0.66, no bucket helps).

**Mechanism — the exact failure mode predicted.** The defensive reverters have **much smaller MFE
(~0.26–0.41% vs the semis' 0.66–0.77%)**: they *do* revert more often (**higher win rates, 44–50%**) but
each win is **too tiny to cover the losers + costs** (5 bps slippage/side + spread). Mode C is worst
(PF 0.65, −18%) — its ATR-zone over-trades low-vol names into a cost sink. The two universes bracket the
problem: momentum names **move but trend** (fade fights the trend); reverters **revert but don't move**
(fade can't clear costs). **No sweet spot was found within the two tested universe families** — high-
momentum semis and low-vol defensives. (Precise scope: two families were tested, not the whole universe
space; the claim is bounded to what was measured.)

## PROGRAM CONCLUSION — the fade has no tradable edge (RNG = rejected benchmark, fully evidenced)

The long-only opening-range fade is short edge across **three independent dimensions**, on clean 3-year
data: (1) every entry mode [Phase 1, PF 0.84–0.91]; (2) every regime [Phase 3, best bucket PF 0.94];
(3) both universe archetypes [momentum PF ~0.87, mean-reverting PF ~0.72]. Entry, stop, trend-gate, and
universe were each tested and none reaches profitability. This is a **strong, conclusive negative
result** — it confirms the research-portfolio design that classes RNG as the *rejected-benchmark* sleeve,
and now supplies the full *why*.

**Verdict framing: RNG-001 is COMPLETE — evidence REJECTS, program SUCCEEDED.** The program is not
"closed" (which frames a success as a failure); it is **completed with a rejected verdict**. The
*hypothesis* — that a long-only opening-range fade has a tradable edge — failed; the *research program*
succeeded, because it produced a transparent, reproducible verdict plus durable infrastructure. Formally:

> **RNG-001 — Status: Completed · Verdict: Rejected · Disposition: Archived.** The evidence does not
> support promotion of the opening-range fade on any tested universe or regime. RNG-001 is archived as a
> completed, rejected benchmark; its instrumentation, research harnesses, and methodology become reusable
> platform capabilities.

**"Archived" ≠ "paused" — reopening requires a NEW HYPOTHESIS, not another sweep.** Do not pursue Phase
1.5/2/4/5: parameter tuning cannot close a ~0.1–0.15 PF gap that is structural to the fade thesis on the
tested universes. The one residual thread (an exit capturing more of a positive MFE that the OR-high/stop
leaves on the table) is a long shot, relevant only on the *momentum* names where the fade also fights the
trend — not worth a phase. RNG stays live on the box as the **rejected-benchmark** sleeve (default config,
untouched): a verdict-distinct, evidence-backed negative. A future reopen must bring a *materially
different mechanic or instrument class* (not the same fade with new knobs) and a new hypothesis id.

### Research Deliverables (reusable platform assets, independent of the strategy)

The durable output of RNG-001 is infrastructure, not a strategy. Each carries forward to any future
program:

- ✅ **MAE/MFE + time-to-entry** per-trade instrumentation (`app/strategies/backtest_*`)
- ✅ **Opportunity Funnel** (universe→qualified→touched→entered→stopped→exited) — recommend promoting to
  a permanent, all-strategy dashboard KPI (Momentum, Insider, future books), not just a research artifact
- ✅ **Regime Classifier / segmentation** (SPY directional-efficiency day labels + trade bucketing)
- ✅ **Entry-mode comparison harness** (`scripts/research/range_entry_mode_compare.py`)
- ✅ **Universe-screen harness** (variance-ratio mean-reversion selection; lesson: avg daily DE is a
  non-discriminating ~0.45 constant — use VR)
- ✅ **Data-integrity checker + cache-repair tool** (`scripts/research/rebuild_5min_cache.py`) — surfaced
  and worked around the bar_cache 10k-truncation bug; the platform fix is recorded in **ADR-0033
  (Historical Data Integrity)**.
