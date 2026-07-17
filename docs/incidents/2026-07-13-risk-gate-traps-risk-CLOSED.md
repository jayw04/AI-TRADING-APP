# Incident closure — 2026-07-13 risk gate traps its own de-risking

**Status: CLOSED (2026-07-17).** Account/book: user 1 / `momentum-portfolio` (id=2), Alpaca paper account 1.

## One-line finding

A risk control that stops trading must not prevent verified reduction of the risk it exists to control.

## What happened (2026-07-13)

At 09:30:25 ET the daily-loss breaker tripped on account 1 (day −$5,504 vs a $5,000 cap). At 10:00
the strategy proposed trimming its two largest positions (SNDK, LITE) — reducing exposure. **Both
were rejected**, because the loss/breaker gates rejected *every* order regardless of risk effect.
The book stayed ~98% invested through a −7% day; the loss deepened to −$7,501, and **~$2,000 (≈36%)
of it accrued AFTER the control fired.** The strategy did not malfunction — the control locked in the
exposure it exists to cap.

Contributing causes: (1) the daily-loss and breaker gates did not consult `is_reducing_sell` (the
exemption existed for the gross-exposure gate per ADR 0038 and the cooldown per ADR 0039, but the
loss gates were missed); (2) `HALTED` was never enforced at dispatch (ADR 0004 semantics were
documented but unimplemented); (3) the dispatch slot fired 6× (bar-keyed guard oscillation);
(4) rejected orders were not persisted, so the investigation reached the wrong conclusion twice.

## Remediation (what closes this)

1. **ADR 0042 — verified risk-reducing orders + the durable decision ledger.** A locked account may
   submit an order the engine can *verify* reduces risk, classified by projected risk effect (never
   by BUY/SELL verb). Risk-increasing orders remain refused.
2. **Confirmatory canary — GREEN 2026-07-17 (non-vacuous).** On a genuinely lock-tripped account 3,
   a `SELL 50 F` was ALLOW / RISK_REDUCING / `VERIFIED_REDUCTION` while the breaker stayed tripped
   and `max_daily_loss` was unmoved; a risk-*increasing* BUY was still rejected. The cross-process
   capacity race (untested in two prior attempts) executed and passed all seven sub-checks —
   `settled_before_race` after 513 s (validating the #437 reservation-settle budget), the loser
   refused by the CLAIM not the broker, position never crossed zero. Evidence:
   `adr0042_orchestration.log` (`=== canary_run exit=0 ===`), and the ledger rows it cites.
3. **Strategy-code fixes deployed** — momentum-portfolio v0.9.0 Workstream-A (PR #439, deployed
   2026-07-17, commit `7abf404`): A1 dual momentum filter, A2 absolute-rank hysteresis, A3 pinned
   12-1 + effective-params assertion, A5 bounded regime fallback (no more fail-open). Deployed
   alongside #438 (the short gate now trusts the broker's position, not the ledger).

## Explicitly still OPEN (NOT closed by this)

- **ADR 0043 — loss-control architecture** (separated controls, persisted session baseline, trip
  classification, recovery preflight, hysteresis): **not started.** ADR 0042 was the fast-track fix;
  0043 is the durable design and remains owed.
- **Correlated-exposure / concentration risk** (the incident book was 59% memory-storage in one
  sub-industry = 78% of the day's loss): belongs in a separate portfolio-risk ADR. A per-name cap
  does not constrain a book whose names are the same trade. **Not started.** Do NOT recalibrate
  breaker thresholds to accommodate concentration.

## Durable lessons

- The `orders` table records only orders *accepted for submission* and is purged; it is not a history
  of what the system did. Use `strategy_dispatch_runs` (did it run), `risk_decisions` (what was
  proposed and why refused), and `audit_log` (what was done).
- A control that is written down but not enforced is worse than none — everyone plans around the
  documented version. ADR 0004's halt semantics were correct, specific, and absent from the code for
  months.

## Closure basis

The exact failure mode — a locked account unable to de-risk through the product path — is proven
fixed on live paper (canary GREEN, non-vacuous) and the strategy-code half is deployed. Account 1 is
released from its "retain unchanged as incident evidence" hold; momentum-portfolio may resume on the
fixed code. This closure does not discharge ADR 0043 or the concentration-risk ADR.
