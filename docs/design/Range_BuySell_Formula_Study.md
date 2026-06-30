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

Data provenance: OR levels below are computed from Alpaca IEX 5-min bars (full 09:30–10:00 window).
META's *actual* live levels come from the strategy's own signal/fills (see the caveat in §Findings).

---

## 2026-06-30 (Tue) — entry #1 day

Universe (daily auto-select Top-5): **MU, INTC, AMD, TSLA, META**. Account: Alpaca Paper (Range).
⚠ **Engine started 09:48 ET (18 min after the open)** — the live in-memory opening range was built
from ~09:48–10:00 bars (partial), so META's live entry differed slightly from the full-window OR
(see Findings). EC2 (up before 09:30) will use the full window.

### Intraday snapshot (~11:00 ET — NOT final; session low/high extend until 16:00)

| Sym  | Open    | Entry (OR low) | Exit (OR high) | Stop    | Sess Low | Sess High | Last    | Touched          |
|------|---------|----------------|----------------|---------|----------|-----------|---------|------------------|
| MU   | 1144.80 | 1125.06        | 1162.62        | 1119.43 | 1136.29  | 1155.81   | 1142.48 | none             |
| INTC | 132.19  | 131.60         | 137.44         | 130.94  | 136.33   | 140.65    | 139.31  | resistance       |
| AMD  | 547.52  | 546.02         | 564.56         | 543.29  | 552.79   | 573.49    | 572.33  | resistance       |
| TSLA | 406.99  | 406.39         | 412.57         | 404.36  | 410.99   | 418.00    | 417.06  | resistance       |
| META | 560.52  | 554.92         | 560.54         | 552.15  | 551.57   | 557.15    | 556.93  | **support+STOP** |

"Touched" = the session reached that zone after 10:00 ET. (Resistance touches are moot for a
long-only strategy that needs a support entry *first*.)

### Trades executed

| Sym  | Side | Time (ET) | Price   | Reason       | Notes |
|------|------|-----------|---------|--------------|-------|
| META | BUY  | 10:15     | 555.49  | range_entry  | live entry level 555.42 (signal), filled 555.49 |
| META | SELL | 10:56     | 552.42  | **stop_loss**| support broke; stopped out |

**Realized P&L: −$21.49** (META round-trip, −0.55%). No other name entered.

### Findings (preliminary — revisit at close)

1. **Up-day, few setups.** 4/5 names rose (INTC/AMD/TSLA hit resistance, MU drifted mid-range). A
   long-only fade-support formula correctly took **no** longs in the rallying names — it did **not**
   chase. That restraint is a feature, not a miss.
2. **The only pullback failed.** META was the lone name to dip to support — and it broke *straight
   through* (sess low 551.57 < stop 552.15) → bought then immediately stopped. The formula caught a
   falling knife rather than a bounce.
3. **Late-start OR distortion (laptop-only).** Engine up 09:48 → META's live entry was **555.42** vs
   the full-window OR low **554.92** (~0.5% higher) → it entered higher/earlier than the formula
   intends. Fixed by always-on EC2. Quantify the distortion again post-cutover.
4. **Resistance was reached on 3 names** (INTC/AMD/TSLA) — a *symmetric* fade (also short resistance)
   would have had setups today; the long-only formula structurally can't use them.

---

## EOD checklist (finalize after 16:00 ET)

- [ ] Re-capture full-day OHLC + final session low/high for all 5 (this snapshot is ~11:00 ET only).
- [ ] Confirm no further entries/exits fired after 11:00 (check signals + orders for strat 1).
- [ ] Recompute the **full-window** OR for META and restate the late-start distortion precisely.

### Formula-adjustment questions to answer with the day's evidence

1. **Entry timing — exact OR-low touch vs confirmation.** META bought the exact low and broke through.
   Would requiring a *bounce* (e.g. close back above the OR low, or a VWAP filter — `vwap_gate_pct`)
   have avoided the falling-knife entry? (Trade-off: fewer entries.)
2. **Stop width — fixed 0.5% vs ATR-scaled.** A 0.5% stop on a high-vol name (META) is inside normal
   intraday noise → easy shake-out. Should the stop be ATR-scaled (`stop_buffer` ∝ ATR%)?
3. **Buy zone width.** Exact-low touch (`entry_zone_pct = 0`) is unforgiving. Would a small support
   *zone* improve fill quality without inviting bad entries?
4. **Opening-range window.** Is 30 min the right window? A longer/shorter OR changes how often price
   revisits the low.
5. **Long-only vs symmetric.** 3/5 names reached resistance today. Is adding short-the-resistance worth
   the added complexity/risk, or does long-only fit the account's mandate?

> One day is a single data point — **do not change the formula on this alone.** Accumulate a window of
> daily entries here first, then decide (structural changes → ADR).
