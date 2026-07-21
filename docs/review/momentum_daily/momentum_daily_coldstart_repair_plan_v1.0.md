# momentum-daily Cold-Start Repair — Implementation Plan v1.0
**Status:** APPROVED (design direction, owner 2026-07-20) — proceed in §12 order.
**Strategy:** momentum-daily (id=11, acct 4 / user 4), PAUSED (`AWAITING_COLD_START_FIX`).
**Decision:** Owner-approved Option A — explicit one-shot `initial_seed`.
**Classification (RATIFIED by owner 2026-07-20): Case C-structural → Case A-behavioral. Definitively NOT Case B.** Final-record wording: *`initial_seed` restores the validated inception timing, subject to proving the live implementation and validation selection cores are decision-equivalent* (the §8 drift audit). The Stage 2-4 harness never instantiated `MomentumDaily`; it reimplemented the selection core + its own simulator whose trade trigger includes `changed = set(target) != held`, which on a flat book is True on the first scorable day → **the validated book deployed at inception (day 1, 2005-01-03).** `changed` is NOT one of the six §5.1 triggers — it's a harness-only term the live template lacks. ⇒ the ~10-session live cold-start delay is a **divergence from validated behavior**, never a validated property; `initial_seed` (seed at first eligible review) **restores conformance to the validated inception**. Caveat: because validation ran a *reimplementation*, §8 must bound the drift surface (harness selection vs live `_select_targets`/`_eligible`), not just inception.

## 0. Scope & non-goals
- **In scope:** `initial_seed` trigger; persisted deployment lifecycle + separate seed-attempt status; fail-closed operational-hold enforcement at every activation boundary; governed clear-hold op; evidence-clock split; pre-declared inception-equivalence rerun; ADR 0044; validation.
- **Non-goals (unchanged):** `_backstop_due`; the six §5.1 triggers; regime model; `_select_targets`/sizing; the risk engine / OrderRouter (seed routes THROUGH them, ADR 0002); concentration risk (separate ADR).

---

## 1. Branch & provenance
- **Base:** a commit containing PR #435 / `f8f079c` (on `origin/main`) — home of `momentum_daily.py`, `strategy_state` model, `context.get_state/set_state/clear_state`, migration `d4e8f2a6c9b1`, tests.
- **Branch:** `fix/momentum-daily-cold-start-seed` off `origin/main`, in an **isolated worktree** (do not disturb `research/mr002-preregistration`).
- **Do NOT** implement on the MR-002 branch or transplant later.
- **Provenance proof (pre-code gate, 4 checks):** (a) `git merge-base --is-ancestor f8f079c HEAD`; (b) `momentum_daily.py` + strategy_state machinery present; (c) diff vs origin/main carries no MR-002 files; (d) worktree isolated, MR-002 working tree untouched.
- **Rebase policy:** if origin/main advances, rebase + re-run full acceptance suite; reactivation image digest must match the reviewed commit.

---

## 2. Deployment lifecycle + seed-attempt status (two separate concerns)
### 2a. Deployment lifecycle (strategy_state keys; no migration)
`deployment_state ∈ {NEVER_DEPLOYED, DEPLOYMENT_PENDING, DEPLOYED, INTENTIONALLY_FLAT}`, `first_deployed_at` (ISO|null), `has_ever_deployed` (bool, **derived-but-persisted**).

| From | Event | To | Guard |
|---|---|---|---|
| (none) | migration (§6) | `NEVER_DEPLOYED` | proven from authoritative records |
| `NEVER_DEPLOYED` | `initial_seed` fires (all §4 gates) | `DEPLOYMENT_PENDING` | seed_attempt written **before** submission (§3) |
| `DEPLOYMENT_PENDING` | **qualifying** fill → attributable exposure > 0 | `DEPLOYED` | set `first_deployed_at`; set `has_ever_deployed=true` |
| `DEPLOYMENT_PENDING` | seed_attempt terminal, **0** qualifying fills, reconciliation clean | `NEVER_DEPLOYED` | clear seed_attempt; retry-eligible next review |
| `DEPLOYMENT_PENDING` | reconciliation unresolved / open-order or delayed-fill risk | (hold in PENDING + operator alert) | never silently advance |
| `DEPLOYED` | regime-cash / full exit / governed flatten / liquidation | `INTENTIONALLY_FLAT` | record cause (§5) |
| `INTENTIONALLY_FLAT` | authorized re-entry trigger | `DEPLOYED`/`DEPLOYMENT_PENDING` | **NEVER via `initial_seed`** |

- **`has_ever_deployed` is monotonic `false → true` only** — never true→false. Once true, `initial_seed` is permanently disabled for this strategy.
- **"Qualifying" fill (successful deployment):** a `fills` row that (i) belongs to this strategy+account, (ii) belongs to the current `seed_attempt`, (iii) has positive executed qty, (iv) is not reversed/invalidated, (v) yields attributable nonzero exposure. `first_deployed_at` = ts of the first qualifying fill. Order acceptance / broker ack / open order is insufficient.

### 2b. seed_attempt (separate status — do not overload deployment_state)
`seed_attempt = { attempt_id, created_at, intended_orders:[{symbol,side,target_weight}], submitted_order_ids:[...], seed_attempt_status }`
`seed_attempt_status ∈ {PREPARED, SUBMITTING, ORDERS_OPEN, PARTIALLY_FILLED, FILLED, TERMINALLY_UNFILLED, RECONCILIATION_REQUIRED}`.
- A seed attempt ending all-rejected/canceled with 0 qualifying fills → `deployment_state=NEVER_DEPLOYED`, `has_ever_deployed=false` — **only after terminal reconciliation proves no open orders and no delayed-fill risk** (`TERMINALLY_UNFILLED`). Until then → `RECONCILIATION_REQUIRED` + operator alert (fail-closed; no auto-progression).

---

## 3. Idempotency & crash recovery
**Write-ahead:** (1) persist `seed_attempt` (attempt_id + intended orders, status `PREPARED`) and set `deployment_state=DEPLOYMENT_PENDING` in one transaction **before** any submission; (2) status→`SUBMITTING`, submit via `ctx.submit_order` (OrderRouter+risk), tag each order with `attempt_id` (client_order_id namespace); (3) append order_ids as returns arrive; status→`ORDERS_OPEN`.
**Recovery (restart / duplicate on_bar / delayed fills):**
- Existing durable `last_eval_date` latch → ≤1 eval/day, restart-safe (first guard vs duplicate on_bar).
- If `deployment_state==DEPLOYMENT_PENDING`: **reconcile, never re-seed** — match `attempt_id`-tagged orders against broker/local state; no new seed_attempt.
- Crash after PENDING before submission (empty `submitted_order_ids`, no broker orders under attempt_id) → roll back to `NEVER_DEPLOYED` + re-decide next review (deterministic).
- Submitted-some-then-crashed → reconcile by `attempt_id` (broker = source of truth), backfill ids.
- Delayed fill after pause → ingests to `fills`; reconciliation folds it in → operator alert (a paused strategy showing a fill is never silent).
- Concurrency: serial dispatch + `strategy_state` UNIQUE(strategy_id,key) atomic upsert; seed critical section keyed on `(strategy_id, attempt_id)`; only one seed_attempt may exist.

---

## 4. initial_seed gating & decision trace
Fires **only when all six hold** (each surfaced individually — never a bare `initial_seed_not_fired`):
```
no_holdings            held == {}
no_pending_entries     no open/partial STRATEGY entry orders (query orders)
never_deployed         has_ever_deployed == false AND deployment_state == NEVER_DEPLOYED
regime_investable      regime_target_gross >= initial_seed_investable_gross
scores_available       momentum_scores computed (no _HOLD_ON)
eligible_candidates    len(_eligible(scores)) >= 1
```
- **`initial_seed_investable_gross` — candidate default 0.60** (NOT yet the immutable production default; locked only via §12 step 6). A **named, registered strategy parameter** (schema entry + description). **Inception-eligibility only** — must NOT be reused to govern warm-book regime adjustments unless separately validated. Because `regime_target_gross` is **discrete** (0.15 / 0.50-degraded / 0.60 / 0.98), the real choice is a distinct regime state, not a numeric cutoff: **Policy M (seed when gross ≥ 0.60)** vs **Policy H (seed only when gross = 0.98)**.
- **Threshold adjudication (empirical, two-sided; predeclared rule):** for inception observations starting at 0.60, measure transition to 0.15 within 5 & 10 sessions; transition to 0.98; dwell at 0.60; initial-seed turnover followed by rapid de-gross; return/drawdown before the next regime transition; and frequency of missed upside while waiting for 0.98. Weigh **both** costs — *seeding at 0.60:* whipsaw / turnover / transaction cost / early drawdown; *waiting for 0.98:* cash drag / delayed participation / missed momentum. **Predeclared decision rule:** retain 0.60 unless mid-state inception produces materially higher early reversal, turnover, or drawdown **without** compensating return; move to 0.98 only through an explicitly adjudicated validation result. Threshold adjudication precedes final code *configuration* but does not block implementing the parameterized *mechanism*.
- **Decision trace:** `reason="initial_seed_eval"` (INFO) logs all six booleans + `regime_target_gross` + candidate count. On fire: `reason="initial_seed"` with attempt_id + names/weights.
- **Routing:** `initial_seed → _select_targets(scores, held={}) → weights scaled to regime_target_gross (via existing _investable_equity) → ordinary risk → ordinary submission`. Fires inside `_evaluate` (only sanctioned order origin; ADR 0002).

---

## 5. Intentional-flat semantics
`DEPLOYED → INTENTIONALLY_FLAT` set + cause recorded for: regime-directed cash; risk/engine liquidation; complete trigger-driven exit; governed manual flatten; account-level intervention. **Invariant:** `initial_seed` may NEVER do `INTENTIONALLY_FLAT → DEPLOYED`; re-entry only via existing maintenance triggers.

---

## 6. Existing-state migration (proven, not inferred)
Determine `deployment_state` from authoritative records — historical `fills`, STRATEGY `orders`, current `positions`, pending orders, `prev_regime`, governed-flatten/activation history (`audit_log`), `strategy_runs`:
- ever a qualifying STRATEGY fill → `DEPLOYED` (if holds now) / `INTENTIONALLY_FLAT` (flat now, has fill history); `first_deployed_at` = earliest qualifying fill; `has_ever_deployed=true`.
- never any STRATEGY order/fill AND flat → `NEVER_DEPLOYED`; `first_deployed_at=null`; `has_ever_deployed=false`.
- **id=11 (proven from evidence snapshot, canonical sha256 `8fa766f39e289c9925e7295f434b7887abd4d91ce1d802eb21b30d626fd8c054`):** 0 STRATEGY orders, 0 fills, 0 holdings → `NEVER_DEPLOYED` / null / false; preserve `operational_hold`.
- **Reconciliation integrity check:** if a qualifying historical fill exists but `has_ever_deployed==false` → **fail loudly (operator alert); do NOT auto-reset** (auto-reset would conceal state corruption). Migration is idempotent + logs the evidence used per strategy.

---

## 7. Evidence-clock definitions (exact rules; versioned)
- `calendar_days_enabled` — calendar dates the strategy was registered (PAPER/LIVE) for any part of the day.
- `trading_days_reviewed` — sessions with a completed governed evaluation (`last_eval_date` advance).
- `trading_days_deployed` — sessions with confirmed nonzero attributable exposure.
- `exposure_days` — **count of completed sessions with nonzero attributable exposure at the official end-of-session evidence snapshot** (deterministic, auditable). Kept **separate** from `trading_days_deployed` (may initially equal it; not assumed permanently identical).
- `first_deployed_at` — first qualifying-fill ts (single source, = §2).
- Weighted duration deferred under a distinct name: `gross_exposure_day_equivalents`.
- **Maturity** (`continuous_evidence.py`) switches to `trading_days_deployed` (not `len(curve)`); reliability may use enabled/reviewed. **Version the metric definition** (`metric_def_version`), mark the recalc boundary in reports; historical rows keep their old basis with a visible cutover note (no silent rewrite).
- Touch-points: `services/continuous_evidence.py::BookEvidence`, `scripts/confidence_score.py::_track_record_days`, `scripts/reports/daily_report.py`.

---

## 8. Backtest/live inception alignment — classification GATE (do first, §12 step 2)
**Read the Stage 2-4 harness/prereg** (`docs/implementation/evidence/momentum_daily_stage2_4/`, `scripts/backtest_momentum_stage{2,3,4}.py`, `MR_MomentumDaily_Stage*_full.json`) to reconstruct the historical inception convention. ⚠ **A ~10-session delayed start is immaterial over a 2005–2026 backtest, so long-run performance CANNOT reveal whether the harness seeded immediately, entered via the same cold-start backstop, or used a separate init path.** Three cases (classification stays TBD until resolved):
- **Case A — harness seeds at first eligible review** → `initial_seed` is a live/backtest **conformance repair**.
- **Case B — harness waits for the backstop** → `initial_seed` changes validated inception timing (day-1 vs ~day-10) → **strategy change**. ⚠ *Nuance:* a delayed entry in validation proves only that the behavior was PRESENT, not that the delay was an intentional strategy property. Owner then decides: **preserve validated delayed inception**, OR **deliberately adopt day-one inception + broader re-validation**.
- **Case C — harness uses a third initialization path** → resolve the semantic mismatch BEFORE coding; neither classification is yet justified.

**Reconstruction result (step 3, 2026-07-20 — see `harness_inception_reconstruction_findings_v1.0.md`):** the harness never instantiates `MomentumDaily`; `conditional_select`/`select_n` + an inline `simulate()` reimplement the selection core, and the trade trigger `changed = set(target) != held` seeds a flat book on the first scorable day (first trade = window start 2005-01-03; `usable_score_days == trading_days == 5395`, so the 273-day 12-1 lookback is served by pre-window history and adds no delay). `changed` is a harness-only term absent from the six live triggers. **⇒ validated inception = day-1 deployment; the live ~10-session gap is a divergence, not a validated property; `initial_seed` restores conformance.** ⚠ **Drift-audit requirement:** validation ran a *reimplementation* the template itself says "must not drift" (`momentum_daily.py:12-16`) — the cold-start gap is a proven drift. §8 must therefore also bound the drift surface: prove the live `_eligible`/`_select_targets` are decision-equivalent to the harness `compute_day`/`conditional_select`/`select_n`, ideally by driving the ACTUAL live `MomentumDaily` (with `initial_seed`) through the historical window and comparing to the harness results — not merely re-running the harness.

**Drift-audit design (upgraded, required — owner-mandated):** preferably **drive the actual live `MomentumDaily` class through historical data**, replacing only external execution deps (context, broker, clock, state, order) with deterministic test adapters; run the existing Stage 2-4 replica on the SAME input; compare **session-by-session at each decision seam** — scores · eligible candidate set · ranking order · selected target set · target weights · regime-scaled gross · trade/no-trade decision · trigger/reason. **Extend the comparison through `_evaluate`** (not only `_eligible`/`_select_targets`) — this defect lived in the trigger GATE around selection, not selection itself. **Required outputs:** first-mismatch date · total decision-mismatch count · mismatch category · representative input state · live output · harness output · economically-material? · cumulative exposure/performance effect. **Tolerances: ZERO for semantic decisions** (candidate membership, selected names, trade-initiated); numeric tolerances only for weights/returns/floating-point (per the bands above).
**Two-variant rerun:** (A) historical harness inception convention vs (B) new `initial_seed`. Compare first-trade-date, first names, initial weights/ranking, gross-exposure path, turnover, returns, DD, Sharpe, order-timing, eligibility, costs/slippage.

**Structural requirements (mandatory, not tolerances):** first eligible review date identical · first trade date identical (absent documented execution-calendar effects) · initial selected names identical · initial target-ranking order identical · initial target gross identical within rounding · initial target weights identical within implementation rounding · cold-start trigger count exactly 1 · duplicate seed attempts 0. *Any diff in first names / first eligible date / first intended portfolio normally fails conformance.*

**Numeric tolerances:** initial per-name weight ≤1 bp abs · daily gross-exposure path ≤5 bps/day abs (**and** max daily diff ≤5 bps **and** mean abs daily diff ≤1 bp) · annualized turnover ≤10 bps abs · total return/CAGR ≤5 bps abs · annualized vol ≤5 bps abs · Sharpe ≤0.01 abs · maxDD ≤5 bps abs · transaction costs ≤1 bp of cumulative traded notional · trade count exact (unless documented rounding yields only zero-economic-value orders).

**Classification rule:** conformance repair **iff** all structural pass AND all numeric pass AND all diffs explained by deterministic rounding/serialization/equivalent execution representation AND no change to candidate eligibility, first-entry timing, or economic exposure. Otherwise → strategy-behavior change → broader validation. Bands fixed here **before** the rerun; owner adjudicates.

---

## 9. Deployment, hold enforcement & reactivation
**Fail-closed operational hold — enforced, not displayed, at EVERY activation boundary** via a shared `assert_no_active_hold(strategy_id)`:
`engine.register`; `/start` (`start_strategy` → 409 w/ reason); engine **boot/resume**; `ActivationService` (LIVE); `provision_momentum_daily.py`; any admin / reconciliation / manual-rebalance utility. **Proposed CI invariant** (16th) — "no activation path registers a strategy with an active `operational_hold`."

**ADR 0044 — "Deployment Lifecycle and Fail-Closed Operational Holds"** (invariants only, not implementation detail): persisted deployment lifecycle is authoritative; holdings alone cannot determine inception state; `has_ever_deployed` monotonic; `initial_seed` one-shot & inception-only; operational holds enforced at every activation boundary; clearing a hold and activating are separate audited operations; activation paths protected by a CI-enforced invariant. States the lifecycle model applies to **future governed strategies unless a strategy-specific ADR overrides**. **+ Validation-production equivalence invariant** (owner-mandated, folded into ADR 0044): a governed strategy must be validated using its production implementation; when a replica is unavoidable, CI must prove decision-equivalence between replica and production across all governed decision seams. Tiers — **Preferred:** validation invokes the production strategy class. **Permitted exception:** a replicated harness with an automated, fail-closed equivalence contract. **Not permitted:** an independently maintained replica whose equivalence is asserted only by documentation. **Second CI invariant** (alongside the operational-hold one): governed strategy replicas must have a registered production-equivalence test, or validation must invoke the production strategy class directly. (Detailed fixtures / replay / adapters / comparison reports live in THIS plan + validation docs, not the ADR.)

**Audit actions (new):** `STRATEGY_HOLD_PLACED`, `STRATEGY_HOLD_CLEARED` (retain STRATEGY_REGISTERED/UNREGISTERED). Each captures: strategy_id, account_id, reason_code, reason, actor, timestamp, evidence refs, approval ref, prior hold state, new hold state. `STRATEGY_HOLD_CLEARED` **does not imply activation** — it only removes the prohibition. ⚠ The *current* hold predates these actions — **emit a RETROSPECTIVE `STRATEGY_HOLD_PLACED` on implementation**, transparently, NOT falsely back-timestamped: `event_time` = actual audit-row creation time; `effective_at` = original hold-marker ts (2026-07-20T22:48:22Z); `reason_code=AWAITING_COLD_START_FIX`; `source=RETROSPECTIVE_FORMALIZATION`; `evidence_refs=[operational_hold marker, STRATEGY_UNREGISTERED id=5733, run 605, pre-pause snapshot canonical sha256 8fa766f3…, approved repair plan]`. Description must state it **formalizes an already-effective hold — does not newly place or extend it** (protects audit chronology; no manufactured historical evidence).

**Clear-hold vs activate — two distinct audited ops.** clear-hold: actor = owner/designated; requires approved-plan + acceptance-suite + inception-rerun-adjudication refs; emits `STRATEGY_HOLD_CLEARED`. activate: normal `/start` (now unblocked); emits STRATEGY_REGISTERED.
**Reactivation checklist (in order):** approved plan ref · approved code review · migration dry-run · migration verification · acceptance-suite green · inception-rerun adjudication · deployed artifact digest recorded · service reload verified · `STRATEGY_HOLD_CLEARED` · 24h cooldown · `STRATEGY_REGISTERED` · first-review observation · `initial_seed` decision trace captured · order+fill reconciliation. **Controlled first activation:** operator observes first review, verifies exactly one seed_attempt, reconciles fills.

---

## 10. Validation matrix
Core (9): 1 new flat + risk-on → seeds first eligible review · 2 new flat + risk-off → cash · 3 no candidates/scores unavailable → hold w/ explicit per-condition reason · 4 pending initial orders → no duplicate seed · 5 partial initial fill → reconcile w/o reseed · 6 intentionally-flat warm book → no masquerade seed · 7 restart after deploy → no initial_seed · 8 target gross honors 0.98 + constraints · 9 live & backtest share inception semantics.
Failure-oriented (4): 10 crash after PENDING before submission → safe recovery, no deadlock/dupes · 11 partial fill then cancel → deterministic reconciliation · 12 activation while hold present → **fails closed + audit event** · 13 duplicate/concurrent review → exactly one seed_attempt.
Each has an explicit pass assertion; suite green before clear-hold.

---

## 11. Decisions (RESOLVED — owner 2026-07-20)
1. `initial_seed_investable_gross` = **0.60 candidate default** (registered param, inception-only; two-sided Policy M vs H adjudication per §4; not the immutable production default until §12 step 6).
2. successful deployment = **qualifying confirmed nonzero filled exposure** (5-point fill validity).
3. `exposure_days` = **end-of-session nonzero-exposure session count**; separate from `trading_days_deployed`; weighted → `gross_exposure_day_equivalents` (deferred).
4. equivalence gates = **structural (mandatory) + numeric bands** per §8.
5. **ADR 0044 required** (scope per §9).
6. audit actions = **`STRATEGY_HOLD_PLACED` / `STRATEGY_HOLD_CLEARED`**.
Adopted additions: `has_ever_deployed` monotonic + loud reconciliation (no auto-reset); `seed_attempt_status` separate from `deployment_state`.
**RATIFIED 2026-07-20** — owner ratified: classification **Case C-structural → A-behavioral**, treated as a **conformance-directional repair** (adopt day-1 inception; **do NOT preserve the live delay** — no affirmative validation supports it); §8 **drift-audit upgrade** (drive the live class through history; extend through `_evaluate`; zero-tolerance for semantic decisions); **validation-production equivalence invariant** folded into ADR 0044 + a second CI invariant; **commit the review package now** (docs-only) as a pre-code baseline.
Open (non-blocking): §8 numeric-band final numbers are set above; owner adjudicates the rerun result; `initial_seed_investable_gross` locked at §12 step 6.

## 12. Work breakdown (owner-revised order)
1. ✅ Finalize plan v1.0, classification = TBD.
2. ✅ Establish branch provenance (worktree `fix/momentum-daily-cold-start-seed` off origin/main; 4-point proof passed).
3. ✅ **[GATE] Read & reconstruct the historical harness inception path** (§8) — DONE: Case C-structural / A-behavioral (see findings doc).
4. ✅ **Classification decided + ratified 2026-07-20** — conformance-directional repair; adopt day-1 inception; do not preserve delay.
   **← NEXT: step 5.**
5. Run the 0.60-vs-0.98 (Policy M vs H) inception-threshold analysis (§4).
6. Lock production threshold + required validation scope.
7. Implement lifecycle + seed_attempt_status + hold enforcement + audit actions + ADR 0044 + evidence clocks (§2/§3/§4/§7/§9). *(Parameterized mechanism may be built before step 6 locks the value.)*
8. Emit the retrospective `STRATEGY_HOLD_PLACED` (§9).
9. Execute the applicable validation package (§10) — scope set by step 4/6.
10. Clear hold + reactivate only after all gates pass (§9).
