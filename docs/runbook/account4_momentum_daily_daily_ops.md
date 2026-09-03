# Account 4 / momentum-daily (id=11) — Daily Operations Checklist

**Visit this checklist every trading day.** Primary window: **16:05–16:40 ET**, after the
15:50 ET eval and before/alongside the 16:35 ET daily-report email. A 30-second pre-open
glance (item 0) catches overnight problems while there is still time to act.

- Book: user 4 (`momentum-growth@globalcomplyai.com`), Alpaca paper account 4 (`ALPACA_PAPER_3`), $100k inception 2026-07-17.
- Strategy: `momentum-daily` id=11, v0.2.0, `regime_mode=graduated`, entry_rank 5 / hold_rank 10, 252/21 momentum, equal-weight, evaluates **15:50 ET mon–fri** (`50 15 * * mon-fri`), trades only on a fired trigger or the scheduled backstop.
- Data: Sharadar via `/app/data/factor_data.duckdb` (`sep` prices, T-1 publication lag), refreshed by the ~06:04 ET factor-refresh restart; `ingest_runs` records each pull.
- Everything here is **read-only**; operate on the box via SSH (never the local stack).

## The one command

```bash
ssh -o ClearAllForwardings=yes workbench \
    'sudo docker exec -i workbench-backend python -' \
    < scripts/reports/acct4_daily_check.py
```

Prints ✅/🟡/🔴 per item plus today's strategy signals and the user-4 audit tail, ending in
`VERDICT: PASS|WARN|CRIT`. **A PASS verdict closes the daily visit.** Anything else →
work the playbook below. The script is the checklist items A–E automated; items 0 and F–H
are the judgment calls it cannot make.

**Scheduled:** the Windows task `TradingWorkbench Acct4 DailyCheck` runs this command
weekdays at 15:10 CT (16:10 ET), saves the result to `logs\acct4_daily\YYYY-MM-DD.txt`
(summary line in `logs\acct4-daily-check.log`), and pops the result in Notepad on any
non-PASS verdict. Re-register or change cadence:
`scripts/register_acct4_daily_check_task.ps1`. The laptop must be on for it — the
16:35 ET box-side daily-report email is the machine-independent backstop. Known false
alarm: market holidays fail `eval_ran_today` (holidays are not modeled).

## Checklist

### 0. Pre-open glance (~09:00–09:25 ET, 30 seconds)
- [ ] Backend container `Up` + `(healthy)` after the ~06:04 ET restart: `ssh workbench "sudo docker ps"`.
- [ ] Resume-on-boot re-registered id=11 (`resume ... attempted N, resumed N, failed 0` in backend logs, or run the one command and confirm `active_run` PASS with a fresh run id).
- [ ] `day_change` ≈ 0 (baseline rolled overnight — a stale `last_equity` is the spurious-breaker-trip bug class).

### A. Registration & pins (script)
- [ ] id=11 status `PAPER`, active run open, no `error_text`.
- [ ] Schedule still `50 15 * * mon-fri`; version `0.2.0`; `regime_mode=graduated` **present** in stored params (absence = silent class-default fallback).

### B. Data updated daily (script)
- [ ] `sep` max(date) ≥ previous trading day (T-1 lag anchored to the last weekday refresh). 1 day behind = 🟡 (holiday/publication delay — recheck tomorrow); more = 🔴 stale, the strategy will degrade gross or go flat blind.
- [ ] Factor ingest ran this morning (`ingest_runs` has ok rows today) with zero failed rows.
- [ ] No `factor_unavailable_hold` / `regime_stale_degraded_gross` / `regime_stale_blind_flat` signals today. These are the strategy telling you its inputs were bad — the fail-safe worked, but the data pipeline needs fixing before the next eval.

### C. Daily eval & rebalance correct (script)
- [ ] `last_eval_date` == today (after 16:05 ET). Missing = the 15:50 dispatch never reached the strategy — engine/session-gate problem, not a data problem.
- [ ] `rebalance_lifecycle`: if `attempted_at` is set for today's `signal_date`, `completed_at` must be set too. Attempted-but-not-completed = a partial rebalance (some legs unsent).
- [ ] Today's signals make sense: `reviewed_no_trigger` on a quiet day is healthy; on a trade day the reason names which trigger fired (`entry_change`, `weight_drift`, `regime_change`, `scheduled_backstop`, …).
- [ ] Book shape after a trade day: ≤5 names, near equal-weight (script flags >35% relative skew — skew means partial fills; cross-check stuck/rejected orders), gross consistent with the regime multiplier (`prev_regime` state; graduated can hold <100% gross deliberately).

### D. Orders & positions (script)
- [ ] No non-terminal orders >15 min old (stuck `SUBMITTED` = the trade-updates stream-flap class; reconcile before assuming fills).
- [ ] No rejections today (a rejection means the risk engine refused a strategy order — read `rejection_reason` + the risk_checks row; the strategy does not retry).
- [ ] No shorts (`allow_short=0`), per-position ≤ $25k, gross ≤ $100k.

### E. Account & risk rails (script)
- [ ] Circuit breaker clear (`circuit_breaker_tripped_at IS NULL`).
- [ ] `day_change` headroom vs the **$2,000** daily-loss cap (🟡 at 50% consumed).
- [ ] `accounts_state` syncing (<30 min old during RTH).
- [ ] Risk limits row unchanged ($2k loss / $25k position / $100k gross / no shorts). Any drift = someone edited limits — find the audit entry.

### F. Daily-report email (16:35 ET)
- [ ] Read the SNS daily report; account 4 section present, subject `clean` (or explained). The email is the automated backstop for days nobody runs the script — a missing email is itself a 🔴 (timer broke).

### G. Broker reconcile (weekly, or same-day whenever C/D flagged anything)
- [ ] Ledger positions == Alpaca positions (qty per symbol), via the app UI or adapter — never trust either side alone. Ghost divergence is the paper-reset trap: **never reset an account that holds positions.**

### H. Log the visit
- [ ] Anything non-PASS: note it (and what you did) in the ops log / memory. A 🟡 that repeats two days running is a 🔴.

## Failure playbook

| Symptom | Meaning | Action |
|---|---|---|
| `eval_ran_today` 🔴 | Dispatch never reached on_bar | Backend logs around 15:50 ET (`strategy_dispatch_skipped_out_of_session`? engine restart? APScheduler error). Check the engine loaded the **new** schedule — the registration signal payload is known to echo the old `10 21` cron; the strategies row + actual dispatch are authoritative. |
| `factor_data_fresh` 🔴 | Price data stale (factor_data_staleness_gap class) | Check `ingest_runs` errors + the 06:04 ET refresh logs. Fix ingest; do NOT trade around it manually. The strategy already protected itself (degraded gross / flat). |
| `rebalance_lifecycle` 🔴 | Partial rebalance | Reconcile fills vs broker first (G), then check rejections/stuck orders for the missing legs. The next eval's `weight_drift` trigger will normally self-heal the book — verify it does. |
| Rejections | Risk engine refused a strategy order | Read `rejection_reason` + risk_checks. If the gate is correct, the strategy sizing is off — investigate before the next eval; never loosen limits to make an order pass. |
| Breaker tripped | Daily-loss cap hit (or a bug in the baseline) | Do **not** reset reflexively. Verify the loss is real (vs the stale-baseline spurious-trip bug). De-risking sells are allowed under lock (ADR 0042). Reset only with the audited confirmation flow, after understanding the loss. |
| Stuck orders | Trade-updates stream flap | Reconcile against Alpaca REST before acting; cancel/repair broker-side only after confirming ledger divergence. |
| No daily-report email | Report timer broke | `systemctl status workbench-daily-report.timer` on the box. |

## Standing cautions
- Account 4 is a **paper** research book — the value at risk is evidence integrity, not money. Preserve state when something breaks; investigate before "fixing".
- No strategy reload within 30–60 min of the 15:50 ET eval.
- All fixes flow through the normal path: risk gates are never bypassed, the audit log is never edited, limits are never loosened to unblock an order.
