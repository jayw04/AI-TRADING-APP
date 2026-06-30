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

_(run in progress; table appended on completion)_
