# Monthly Evidence Report — 2026-06 — momentum-portfolio v1.1 (momentum + vol-scaling)

_Generated 2026-06-21T12:13:10.299010+00:00 · git ab4aede · window 2026-06-01 -> 2026-06-30 · live paper book (read-only)_

> **Monthly production-validation report (P12.5).** The institutional complement to the weekly snapshot: one month of performance + the operational / safety / verifiability record + an incident log + lessons learned. Short-window live P&L is *indicative*, not alpha (ADR 0014).

## 1. Performance (live equity curve)

_Accruing - 1 daily snapshot(s) in the month; the curve needs >=2 days. Run with `--month` set to a completed month for a full picture._

## 2. Risk

- Risk gates: **6 passed / 0 rejected** by the risk engine (+1 by broker).
- Circuit breaker: **1 trip(s) / 1 reset(s)**.

## 3. Operations

- Orders submitted **5** · fills **7** · canceled **1** · scanner runs **7**.
- Reconciliation runs **40** · replay runs **0** · audit actions logged **64**.
- Strategy re-registrations (resume-on-boot, ~= backend restarts): **22**.

## 4. Incidents

| When | Severity | Kind | Action | Target |
|---|---|---|---|---|
| 2026-06-11 21:59:29.668675 | medium | broker_reject | ORDER_REJECTED_BY_BROKER | order:5 |
| 2026-06-15 14:50:16.347512 | high | breaker | CIRCUIT_BREAKER_TRIPPED | account:1 |

## 5. Recovery

- Breaker tripped **1** and reset **1** - recovered under the documented runbook.

## 6. Replay (decision verifiability)

- **0** runs, **0** decisions checked, **0** mismatched.

## 7. Reconciliation (position verifiability)

- **40** runs, **0** discrepancies, **0** non-pass runs.
- Verifiability this month: **CLEAN**.

## 8. Changes (configuration / lifecycle)

_Meaningful changes only — strategy updates, deactivations, proposal transitions. Boot-time re-registrations are summarized under Operations._

| When | Action | Target |
|---|---|---|
| 2026-06-09 21:11:03.056798 | STRATEGY_PROPOSAL_TRANSITIONED | strategy_proposal:1 |
| 2026-06-15 14:47:59.727024 | STRATEGY_UPDATED | strategy:2 |
| 2026-06-15 14:59:50.575288 | STRATEGY_DEACTIVATED | strategy:2 |
| 2026-06-15 14:59:50.738158 | STRATEGY_UPDATED | strategy:2 |
| 2026-06-15 16:16:48.955153 | STRATEGY_UPDATED | strategy:2 |
| 2026-06-15 16:34:34.348716 | STRATEGY_UPDATED | strategy:2 |
| 2026-06-21 01:12:34.258110 | STRATEGY_UPDATED | strategy:2 |

## 9. Lessons learned

- Incident (medium, broker_reject) at 2026-06-11 21:59:29.668675 [ORDER_REJECTED_BY_BROKER order:5] - see the incident log.
- Incident (high, breaker) at 2026-06-15 14:50:16.347512 [CIRCUIT_BREAKER_TRIPPED account:1] - see the incident log.
- The circuit breaker tripped and recovered under the documented runbook (deactivate != stop; reset confirmed) - the safety net worked.
- Equity curve + trade log + operational trail continue to accumulate into the live track record (P12.5).

_Run monthly; the monthly reports accumulate into the institutional track record._
