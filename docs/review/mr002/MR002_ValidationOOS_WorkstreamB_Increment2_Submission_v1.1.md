# MR-002 Workstream B — Increment 2 v1.1 submission (hardening; all six blocking defects fixed)

**Status: resubmitted for review.** Narrow hardening of Increment 2 per the 2026-07-20 review, which
HELD Increment 2 qualification on six blocking defects. Each is corrected below; scope, cost values,
and next-open mechanics are otherwise unchanged. **Synthetic-only; reads no real dataset; no
performance computed. Increment 3 (portfolio replay + exposure constraints) NOT authorized / not
implemented.**

## Blocking defects — corrected

1. **Exit decision provenance.** Every event now carries **`decision_type`** plus the CAUSAL
   `decision_session`. Entry → `ENTRY_SIGNAL` @ t; explicit exit → `EXIT_DECISION` @ e; time-stop →
   `TIME_STOP_SCHEDULED_AT_ENTRY` @ t+5. The entry decision session is never stamped on an exit
   event. Ledger schema bumped to `increment2-v1.1-synthetic`; event schema is now **17 fields**
   (16 originals + `decision_type`). Canonical ledger confirms the long exit as
   `decision_session 5 / EXIT_DECISION` and the short time-stop exit as
   `decision_session 5 / TIME_STOP_SCHEDULED_AT_ENTRY`.
2. **Calendar-day borrow accrual.** `Market` now carries explicit `session_dates` (ISO). Borrow
   accrues over `borrow_calendar_days = (exit_date − entry_date).days` under the 360-day convention,
   not a trading-session count. Verified: **Friday→Monday = 3 days**; **holiday gap** (Wed→Fri across
   Thanksgiving) = 2 calendar days over a 1-session gap. Missing/invalid dates → `EXEC_DATE_MISSING`
   / `EXEC_DATE_INVALID`.
3. **Six-session horizon identity-enforced.** `intent.horizon != 6` →
   `REFUSED_CODE_OR_DATA_IDENTITY:EXECUTION_HORIZON` (`ExecRefused`). The governing horizon is fixed
   at `GOVERNING_HORIZON = 6`; callers cannot silently run a 4/5/7-session strategy.
4. **Missing/invalid ADV & NAV are integrity stops.** `EXEC_ADV_MISSING` (key absent),
   `EXEC_ADV_NEGATIVE`, `EXEC_ADV_NONFINITE`; `EXEC_NAV_MISSING` (None), `EXEC_NAV_NONPOSITIVE`,
   `EXEC_NAV_NONFINITE`. ADV = 0 is honoured only as an explicitly-supplied observed zero (→ NO_FILL);
   a missing record no longer launders into a no-trade outcome.
5. **Cost-schedule identity.** `validate_schedule` fail-closes any schedule that is not EXACTLY one
   of the three governing specs (name, both rates, `day_count == 360`, classification) →
   `REFUSED_CODE_OR_DATA_IDENTITY:COST_SCHEDULE`. Enforced in `simulate_position`,
   `simulate_sequence`, and `recompute_position_under_schedule`. The low-level primitives remain
   arbitrary-schedule capable (clearly documented). A tampered `BASE` (5 bps) and a `day_count=365`
   both refuse.
6. **Strict typing + provenance guards.** `borrow_cost` requires an exact integer day count (rejects
   `5.9` and `True` → `BORROW_DAYS_NOT_INT`); sessions are strict non-negative ints
   (`EXEC_INVALID_SESSION`); `simulate_sequence` refuses duplicate `trade_id` / `position_id`; exit
   decision before entry (or exit target ≤ entry fill) → `EXEC_EXIT_BEFORE_ENTRY`.

**Minor source defect:** `_resolve_exit_session` now returns `(None, False)` when no future open
exists (was the dead `target != target`).

## Qualification result

- **Tests:** Increment 2 **35/35** (all previously-required cases + the 15 review-mandated new
  tests); full evaluator suite (Increment 1 + 2) **94/94**; **ruff clean**.
- Reads no real dataset; no signal/universe/sector/optimization; synthetic constants only.
- **Determinism:** ledger report byte-identical across runs; `output_hash` =
  `940ecec4a0d3da926cf705d1ccd44fd45151a3a15bb55ac810655959088bb230`; self-hash verifies; all
  positions reconcile `net = gross − total_costs`; signed-zero (`-0x0.0p+0`) preserved; non-finite
  refuses.
- Evidence shas: ledger report file `48eeb510…`; qualification `efc15cdb…`; dependency lock reused
  from Increment 1 (`17a73ede…`).

## Review-mandated new tests (all present)

explicit-exit records exit decision session; time-stop records the frozen causal decision;
Friday→Monday short borrow = 3 calendar days; holiday-gap borrow accrual; caller horizon 5 refuses;
caller horizon 7 refuses; missing ADV stops; negative ADV stops; nonpositive + missing NAV stop;
tampered BASE schedule refuses; day_count 365 refuses; float & bool holding days refuse; duplicate
trade_id refuses; duplicate position_id refuses; no-future-open pending deterministic; canonical
report has no EXIT event carrying the entry decision session.

## Boundary

Validation/OOS **SEALED AND UNREAD**; `validation_authorization = false`. **NOT authorized / not
implemented:** residual signal calculation, universe reconstruction, sector mapping, portfolio
optimization, beta/sector exposure constraints, real vendor data adapters, development performance,
validation/OOS access, performance interpretation, production promotion. Increment 3 remains a
separate future authorization, gated on acceptance of this hardened execution layer.
