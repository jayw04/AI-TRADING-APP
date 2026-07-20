# MR-002 Workstream B — Increment 3 v1.1 submission (three blocking defects corrected)

**Status: resubmitted for review.** Narrow v1.1 correction of the three blocking defects the
adjudication identified, plus the supporting hardening. Scope, module separation, and accepted
components are otherwise unchanged. **Synthetic-only; reads no real dataset; no residual/z/sigma; no
performance; validation/OOS never opened.** Binds registry `edb7ff22` + resolution `860c8cde`.

## Defect 1 — held-book constraints & numeric grandfathering (was: key-only, construction ignored held)

- **Construction is now held-aware.** `build_intended_target(cands, nav, occupied, held_legs)` takes
  the provisional post-exit held book (marked at session opens) as the **baseline**; the
  position→sector→beta cascade constrains the **total held+new** book and removes the smallest-|z|
  **new** candidate (freed→cash, no upward renormalization) whenever a new entry would create or
  **worsen** a breach vs baseline.
- **Numeric grandfathering** replaces the key-only suppression: `worsened_or_new_violations(baseline,
  book)` compares **actual values** per subject — a breach fails closed if the subject was ≤ limit in
  the baseline (**NEW**) or the book value **strictly exceeds** the baseline value (**WORSENED**); an
  already-breached subject that is unchanged or **reduced** is grandfathered. Applied at both
  construction (INTENDED vs baseline) and execution (REALIZED vs baseline). So market appreciation of
  a fixed-share held position no longer false-trips, but no new order may worsen an existing breach.

## Defect 2 — complete Increment-2 17-field ledger integration (was: empty events, abbreviated exits)

- A single shared constructor `mr002_valoos_execution.ledger_event(...)` builds the qualified 17-field
  schema; `_event` (Increment-2 internal) now delegates to it — **no second abbreviated schema**.
- The replay emits full 17-field events for **ENTRY_FILL, ENTRY_CANCELLED, EXIT_FILL, EXIT_PENDING,
  ENTRY_REFUSED_SAME_OPEN** (with `gross_pnl`/`net_pnl` on exits). The canonical session-1 report now
  carries **10 ENTRY_FILL events** (was empty).
- **Reconciliation** on every committed session: `opening_cash + entry/short-sale flows + exit flows −
  commissions − borrow = closing_cash` (`reconciliation.reconciles = true`); every committed position
  maps to exactly one `ENTRY_FILL` (asserted).

## Defect 3 — non-null RAW_TARGET + derivation trail (was: `RAW_TARGET = None`)

- Construction persists a true **RAW_TARGET** snapshot (pre-cascade sized book: raw inverse-vol
  weights, within-side normalized weights, raw dollar targets, raw gross/per-name/sector/beta/cash).
  The report shows RAW_TARGET gross (100% NAV) > INTENDED_TARGET gross (post position-cap), and every
  position-cap clip + removal is a recorded **ConstraintDecision**, so INTENDED is demonstrably derived
  from RAW. Exposure states are now the full four: RAW_TARGET / HELD_BASELINE / INTENDED_TARGET /
  REALIZED_EXECUTED.

## Supporting hardening

- Replay report embeds `governing_source_identities` (all loader-validated source shas), plus
  top-level `research_gate_verdict = NOT_EVALUATED_SYNTHETIC` and
  `performance_interpretation_authorized = false`; the metric block is labelled
  `SYNTHETIC_INTERFACE_QUALIFICATION_ONLY` — no synthetic metric is presented as an MR-002 gate.
- A deferred exit whose symbol has no open now correctly emits the `EXIT_PENDING` evidence **and**
  fails the session closed with `HELD_POSITION_OPEN_MARK_MISSING` (both frozen rules hold; state
  unchanged).

## Qualification

- **Increment 3: 34 tests** (27 + 7 v1.1 correction tests); **full evaluator suite: 128 passed**
  (Inc 1: 59, Inc 2: 35 — refactor behavior-preserving, Inc 3: 34); **ruff clean**.
- New tests: numeric grandfathering (new/worsened/unchanged/reduced); held-appreciation grandfathered
  with no new orders; construction sees held exposure and blocks a worsening entry; 17-field
  entry/exit/pending events; committed positions reconcile to entry events + cash ledger reconciles;
  RAW_TARGET non-null + RAW→INTENDED clip/removal trail; synthetic report verdict `NOT_EVALUATED_SYNTHETIC`.
- **Determinism:** replay report byte-identical; `output_hash` =
  `a5cb8e3cc08fa1f817b545a8e029d81a9cb1ee62ca1f013688ba358c0ac2cc53` (file `58edd23b…`); qualification
  `f6d85343…`; `metric_input_is_portfolio_series = true`; 4/4 sessions committed;
  `synthetic_fixture_only = true`, `validation_data_read = false`.

## Boundary

Validation/OOS **SEALED AND UNREAD**. **NOT authorized / not implemented:** real residual/z/sigma, PIT
sector reconstruction, real vendor/sealed adapters, validation/OOS access, development performance,
performance interpretation, production promotion, Increment 4. Stops at the regenerated qualification
package.
