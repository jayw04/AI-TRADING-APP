# MR-002 Workstream B — Increment 2 submission (cost model + trade ledger + next-open execution)

**Status: submitted for review.** Implements the Increment 2 scope authorized in the 2026-07-20
adjudication (`docs/review/comments.md`), built immediately after the Increment 1 closeout commit
`f9d9f223`. **Synthetic-only; reads no real dataset; no development/validation/OOS performance
computed. NO signal generation, universe reconstruction, sector mapping, portfolio optimization, or
exposure constraints (those are Increment 3 and are NOT implemented).**

## What was built (`docs/review/mr002/evaluator/`)

1. **`mr002_valoos_costmodel.py`** — frozen cost schedules + two primitives.
   - **BASE** 10 bps/side + 50 bps/yr borrow (360-day); **STRESS** 20/300 (mandatory gate);
     **SEVERE** 30/1000 (diagnostic, `classification="DIAGNOSTIC"`, never gated).
   - `commission_slippage_cost` is keyed to **executed** notional per filled leg; `borrow_cost`
     accrues only for a **short** leg, principal = executed short-entry notional, over the holding
     period with the frozen 360-day convention. Fail-closed: `COST_NONFINITE`,
     `COST_NEGATIVE_NOTIONAL`, `BORROW_NEGATIVE_DAYS`, `BORROW_LONG_SIDE`.
2. **`mr002_valoos_execution.py`** — next-open semantics + synthetic trade ledger + mechanical clips.
   - Entry at official open **t+1**; explicit exit at **e+1**; time-stop at **t+6** (last of t+1..t+6);
     missing entry open → **ENTRY_CANCELLED**; missing exit open → **deferred** to the next valid
     open (or **EXIT_PENDING** if none); **no same-open re-entry** (`ENTRY_REFUSED_SAME_OPEN`).
   - Mechanical controls only: **2% trailing-ADV** participation clip + **1.5% NAV** new-entry cap,
     **clip-never-delay** (clipped quantity dropped to cash; no residual order).
   - Every ledger event carries the **16 frozen fields** (`trade_id, symbol, side, decision_session,
     scheduled_execution_session, actual_execution_session, event_type, shares, official_open_price,
     executed_notional, commission_slippage_cost, borrow_cost, gross_pnl, net_pnl, position_id,
     reason`). Position summary reconciles **net = gross − total_costs** exactly.
   - Canonical exact-float ledger report (`ledger_report`, schema `increment2-v1.0-synthetic`) reuses
     the Increment-1 canonicalizer: signed zero preserved, non-finite refuses, deterministic
     `output_hash`, dependency-lock sha embedded. Fail-closed: `EXEC_PRICE_NONFINITE`,
     `EXEC_PRICE_NONPOSITIVE`, `EXEC_NAV_NONFINITE`, `EXEC_ADV_NONFINITE`, `EXEC_INVALID_SIDE`,
     `EXEC_INVALID_SHARES`.
3. **Evidence** — `test_increment2.py` (22 tests), `_gen_evidence_inc2.py`,
   `MR002_Increment2_LedgerReport.json`, `MR002_Increment2_Qualification.json`,
   `MR002_Increment2_TestLog.txt`.

## Required qualification cases (all present, hand-derived)

long round trip @ exact base costs (`979.0`); short round trip with daily borrow; mandatory
cost-stress recompute (gross unchanged, costs scale); severe-cost diagnostic isolated
(`classification=DIAGNOSTIC`); entry at t+1; time-stop exit at open of session 6; missing-entry
cancellation; missing-exit deferral (+ no-future-open PENDING); 2% ADV clip (250→100); 1.5% NAV clip
(250→150); clip-never-delay (no residual order); no same-open re-entry; deterministic ledger + report
hashes; signed-zero (`-0x0.0p+0`) preserved + non-finite refusal; gross−costs=net reconciliation
(long, short, stress, severe). Plus: costs-from-executed-not-intended-notional; invalid side/shares
refusal; 16-field event shape.

## Qualification result

- **Tests:** Increment 2 22/22; full evaluator suite (Increment 1 + 2) **81/81**; **ruff clean**.
- Reads no real dataset; no signal/universe/sector/optimization; synthetic constants only.
- **Determinism:** ledger report byte-identical across runs; `output_hash` =
  `b4bafae4c18b63607c10f7769b2cfeae9e2b5fd3a3ce125cc647ab92ed979808`; self-hash verifies; all
  positions reconcile `net = gross − total_costs`.
- Evidence shas: ledger report file `db96157e…`; qualification `4187689a…`; dependency lock reused
  from Increment 1 (`17a73ede…`).

## Boundary

Validation/OOS **SEALED AND UNREAD**; `validation_authorization = false`. **NOT authorized / not
implemented:** residual signal calculation, universe reconstruction, sector mapping, portfolio
optimization, beta/sector exposure constraints, real vendor data adapters, development performance,
validation/OOS access, performance interpretation, production promotion. Increment 3 (portfolio
replay + exposure constraints) remains a separate future authorization.
