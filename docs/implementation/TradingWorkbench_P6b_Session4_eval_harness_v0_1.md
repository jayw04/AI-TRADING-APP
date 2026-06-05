# P6b Session 4 — Mode-B LLM Eval Harness

| Field | Value |
|---|---|
| Document version | **v0.1** (drafted against `TradingWorkbench_P6b_Session3b_promote_Results_v0.1.md` + the 11-question architecture analysis with picks Q1=(b) first-class harness, Q2=(a) §2/§4 mutually exclusive, Q8=$5/day eval cap with hard-stop) |
| Date | 2026-06-04 |
| Phase | **P6b — Direction v0.2 deferred capabilities**, **§4-eval-harness** (backend half of P6b §4 per Q6/Q11 carve; §4b adds the comparison dashboard UI; §5 adds the live opt-in flow + LLM_OPT_IN_ALLOWED bypass) |
| Predecessor | `TradingWorkbench_P6b_Session3b_promote_Results_v0.1.md` (tag `p6b-session3-promote-complete` at `5213c69`; P6b §3 closed with live BarCache → Alpaca path verified) |
| Successor | `TradingWorkbench_P6b_Session4b_dashboard_v0_1.md` (drafted only after §4 ships per Retrospective Rec #10) — then `TradingWorkbench_P6b_Session5_live_optin_v0_1.md` (the LLM-in-order-path session) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | **New first-class `eval_harness` model** (per Q1 (b)) — a row binding the live Strategy (Mode C) to two newly-spawned paper Strategy rows: Mode A (deterministic mirror) + Mode B (LLM-gated). Three Strategy rows total when eval is active; each routes orders through `OrderRouter.submit` (Mode A/B with paper creds, Mode C with live creds). **`eval_harness_decisions` per-signal table** (per Q4 lean) — one row per signal with A's call, B's call, the LLM rationale, and outcome attribution for the 3 decision-specific metrics. **`EvalHarnessComparison` dataclass** (per Q5 lean) — reuses §1a-drift's metric functions (`win_rate`, `sharpe_ratio`, `max_drawdown`) for the 3 overlap deltas + new computations for the 3 decision metrics (decision-agreement rate, disagreement asymmetry, worst single-decision divergence). Separate from §2b's `VariantComparison` to avoid muddying the param-variant-vs-live lifecycle context. **§4/§2 mutually exclusive enforcement** (per Q2 (a)) — extend §2a's one-in-flight guard so starting an eval blocks §2 spawn and vice versa; surfaces as 409 on the conflicting endpoint. **`app/services/eval_harness.py` with own `ALLOWED_DIRS` entry** in `check_no_llm_in_order_path.sh` (per Q3 (a) + ADR 0006 v2 §2) — the eval-harness module calls Anthropic on Mode-B paper trades; gets its own allowlist entry distinct from `app/llm/` to make the LLM-in-paper-path boundary visible in code review. **Binary act/skip LLM contract** (per Q7 + ADR §99) — `{"action": "act"|"skip", "rationale": str}` over a structured signal payload (no free text per §98 social-engineering mitigation); invoked at signal-evaluation, not bar-dispatch (latency mitigation per §99). **Per-signal cost envelope** (per Q8 settled $5/day) — new sub-key `agent_envelope_json.eval_harness_cost_envelope` (default `{"daily_cap_cents": 500}`); hard-stop on exhaustion → harness state transitions to `PAUSED_BUDGET`; signals skip the LLM call entirely (no decision recorded for skipped signals → cleaner metric computation than recording "budget_paused" pseudo-decisions); resumes next day on cost-window roll. **Double-floor eligibility computation** (per Q9 lean + ADR §64-68) — `(b_trade_count ≥ 50) AND (window_days ≥ 30) AND (no parent param modification since started_at)`; computed read-only by the harness service; exposed via the read endpoint + new MCP tool for §5's opt-in dialog to consume. **`GET /api/v1/eval-harness/{harness_id}` read endpoint** — returns harness state + comparison metrics + eligibility verdict. **`POST /api/v1/strategies/{id}/start-eval` action endpoint** — creates the harness + spawns Mode A and B Strategy rows; checks for no existing §2 paper-variant; transitions Strategy status. **`POST /api/v1/eval-harness/{id}/stop`** — manual stop; terminates Mode A + Mode B; writes audit. **D8-style invalidation hooks** — parent strategy leaves LIVE or params_json mutates → harness auto-terminates (clock resets per ADR §64). **New MCP tool `workbench_eval_harness_metrics`** (per Q9 + new tool not additive extension) — read-only passthrough; tool count 19 → 20. **New audit action `EVAL_HARNESS_STARTED`** (per Q10) — total P6+P6b audit actions 9 → 10; per-signal decisions go to the dedicated table (not the hash chain). Single PR. |
| Estimated wall time | 6-7h |
| Stopping point | `git tag p6b-session4-eval-harness-complete` |
| Tests added | ~32 backend (harness model + decision recording + 6 metrics + eligibility + endpoints + MCP + audit + budget + invariant) |
| Out of scope | Comparison dashboard UI (§4b — VariantCard analog for eval harness, equity-curve chart showing A vs B, decision-by-decision drill-down). Live opt-in dialog (§5 — typed risk acknowledgment). 7-day activation cooldown (§5). `LLM_OPT_IN_ALLOWED` per-user-strategy bypass mechanism (§5 — the actual ADR 0006 v2 invariant extension allowing LLM decisions to reach a LIVE broker). Full prompt/response audit logging per ADR §3.4 (§5 — currently each decision row stores the rationale; full prompt logging is a live-only requirement). User-raisable budget cap with extra confirmation gate (§5 — for the live $10/day cap). Strategy.status enum extension for `EVAL_HARNESS_MODE_A` / `_MODE_B` (Q-side decision: reuse `paper_variant` with a `harness_role` column on Strategy to distinguish; see §4.1). Cross-strategy LLM eval (one harness per strategy v1). Multi-account Mode B (one paper account per harness v1). Modify-size action in LLM contract (binary act/skip only per §99). |

---

## 🚦 THRESHOLD-VERIFY block — primary-source ADR 0006 v2 references

Per the §3 lesson (Closure-plan-shorthand misled the §3a duration gate and drawdown threshold by ~5× each). For §4, these are the load-bearing thresholds and contracts; each is pinned to ADR text. **Verify against the actual ADR section at code-paste time; flip any line that diverges.**

| THRESHOLD | Value baked into v0.1 | ADR text reference |
|---|---|---|
| **LLM decision contract** | Binary `{"action": "act"\|"skip", "rationale": str}` | ADR 0006 v2 §99 "invoked only at signal generation"; binary act/skip per §99 phrasing |
| **Structured-input constraint** | LLM receives structured signal payload only; NO free text fields | ADR 0006 v2 §98 "no read access to user-supplied free text… evaluates structured market data and pre-defined strategy logic" |
| **Eligibility double-floor** | `(B_trades ≥ 50) AND (window_days ≥ 30) AND (no parent modification since started_at)` | ADR 0006 v2 §64-68 — "50 Mode-B trades AND 30 calendar days AND wasn't deactivated/modified during the window" |
| **Reset-on-modify** | Any change to `parent.params_json` after `eval_harness.started_at` → harness auto-terminates (eligibility clock resets fully — no partial credit, no new harness can start until user re-initiates) | ADR 0006 v2 §64-68 "a param tweak resets the clock" |
| **Order routing** | Mode A/B orders route through `OrderRouter.submit(...)` with paper-broker credentials (engine routes orders normally, just with paper creds); Mode C unchanged | ADR 0006 v2 §108 |
| **Six metrics exact definitions** | Win-rate delta (B−A), Sharpe delta (B−A), max-DD delta (B−A), decision-agreement rate (count A_dec==B_dec / total), disagreement asymmetry (when A≠B, signed: + means B-right more often by realized PnL), worst single-decision divergence (max \|B_outcome − A_outcome\| among disagreements) | ADR 0006 v2 §49-56 |
| **Allowlist scope distinction** | §4 adds eval-harness directory to `ALLOWED_DIRS` (paper-path LLM calls); §5 adds `LLM_OPT_IN_ALLOWED` DB-flag bypass (live-path). §4 does NOT touch the live bypass; §5 does | ADR 0006 v2 §2 (eval-harness allowlist entry) + §3 (live opt-in bypass) — two distinct invariant changes |
| **Per-signal cost budget** | `$5/day` default eval-harness cap (half the live $10/day cap, since eval is preparatory not productive); hard-stop on exhaustion → harness state = PAUSED_BUDGET; resumes next day. **NOT specified by ADR — flagged for sanity check.** | (Genuinely unsettled by ADR — §3.6 specifies $10/day live cap only; §4 paper cap is implementation choice) |

**Two further checks** at code-paste time:
- §99's "invoked only at signal generation" — confirm LLM call site is the signal-evaluation pipeline, not bar-dispatch.
- §3.4's prompt+response audit logging — confirmed live-only (§5 scope); §4 stores `rationale` in `eval_harness_decisions.mode_b_rationale` column, not in hash-chain audit log.

---

## ⚠ Review corrections (2026-06-04) — verified against shipped code; engine mechanism settled

The doc's scaffolding (tables, metrics, eligibility, endpoints) is sound, but its **keystone was missing and it imported fabricated infrastructure**. These corrections (confirmed against the engine + LLM code) **supersede the sketches** and were applied at implementation time.

1. **`call_with_budget` / `BudgetExhausted` / `app/llm/budget.py` DO NOT EXIST** (fabricated). The LLM modules are only `anthropic_client` / `pricing` / `runtime` / `system_prompt`. §1a shipped a *GET `/agent/cost-envelope`* pre-call **check** (`_sum_cost_cents_24h` + `cost_envelope_cents`), not an execute-and-raise wrapper. → §4 builds a **real budget gate** in `app/services/eval_harness/gate.py` on top of `anthropic_client.create_message` + `pricing.estimate_cost` + a **per-harness daily cost sum** from a new **`eval_harness_decisions.llm_cost_cents` column** (avoids flooding the audit hash chain with per-signal rows). Over the `eval_harness_cost_envelope.daily_cap_cents` (default 500) → harness → `PAUSED_BUDGET`, signal skipped, no order.
2. **The engine integration (the keystone) was missing.** The doc relied on a nonexistent "engine signal-fork hook." Settled mechanism: every strategy submits via `ctx.submit_order(OrderRequest)` → `submit_order_fn` (engine.py:220 injects `=OrderRouter.submit`). **Mode A is a running `PAPER_VARIANT` clone whose `submit_order_fn` is WRAPPED** (the engine injects the wrapper for `harness_role=="mode_a"`); per order intent the wrapper: (i) submits A's order under its own id (A always acts), (ii) budget-gated **LLM act/skip** for B, (iii) if act, submits B's order via `dataclasses.replace(req, source_id=str(mode_b_id))`, (iv) writes ONE paired `EvalHarnessDecision`. **ADR 0002 intact** (orders still go through `OrderRouter.submit`); the Anthropic import lives only in the allowlisted `eval_harness` package (the engine imports a *factory*, no `anthropic` in engine.py); Mode A/B are paper-only.
3. **Mode B is an IDLE source_id "bucket", NOT a registered `PAPER_VARIANT`.** A `PAPER_VARIANT` Mode B would be picked up by the boot-resume (ENGINE_RUNNABLE_STATUSES) and run the deterministic code → polluting B's data with non-LLM-gated orders. → Mode B row is `status=IDLE`, `harness_role="mode_b"`, never engine-registered; it exists only to own `mode_b_id` for `source_id` attribution. B's orders are submitted by Mode A's wrapper under `mode_b_id`.
4. **Outcomes are DERIVED, not pushed** (kills Candid-Ack #109's cross-cutting hook). The metrics reconstruct Mode A vs Mode B equity from `source_id` via the §1a/§2b round-trip + equity-curve functions (the live-verified path); per-decision outcome (for asymmetry/divergence) comes from the round-trip the decision's order opened. **No OrderRouter fill hook**, no `mode_a_outcome_pnl`/`mode_b_outcome_pnl` columns on the decision row.
5. **`from app.db.base import Base`** (the model sketch's `app.db.models.base` is wrong).
6. **Migration `down_revision = "d7f4a9c2e1b8"`** (the §3a head — §3b was migration-free, reused `transitioned_at`). Use the modern `revision: str = …` template + `op.batch_alter_table` for the `strategies` column (the §2a/§3a precedent).
7. **`AuditAction.EVAL_HARNESS_STARTED`** in `app/audit/logger.py` (9 → 10). Stop/terminate is a state change on the harness row (no extra action, per Q10). Cost lives in `llm_cost_cents`, not the audit log.

---

## How this differs from §3b-promote Results

§3b's 8 corrections (A1-A4 + B1-B4 + minors) shape §4 directly:

- **§3b A1 (variant alive through PROMOTING for UI data)** — same lesson here: Mode A and Mode B Strategy rows must remain alive (`status=paper_variant` with `harness_role` tag) throughout the eval window. Terminating mid-eval breaks the read endpoint + dashboard data flow. They terminate only on eval-stop (manual or auto-invalidation).
- **§3b A4 (reuse existing columns)** — applied here: Strategy gets one new column (`harness_role`); `transitioned_at` reused where state-time computation needed; cost-envelope reuses §1a infrastructure rather than new schema.
- **§3b B1 (`terminate_for_parent` signature)** — verified before pasting in §4.7 (harness termination calls).
- **§3b B2 (`proposal_payload_json["changes"]` + `_apply_changes`)** — naming-from-imagination guard. §4's eval_harness service references existing infrastructure by exact names (verification-checklist items below).
- **§3b B3 (terminate-first ordering for audit hash chain)** — applied: harness stop terminates Mode A and Mode B before writing `EVAL_HARNESS_TERMINATED` audit + commit.
- **§3b B4 (in-scope `scheduler.scheduler`)** — applied: any §4 cron registration follows the lifespan.py pattern from §3b.

Plus all standing P6+P6b deviations:
- `func.json_extract(...)` Core for JSON queries (relevant: cost envelope reads).
- `AuditLogger.write` sync staticmethod, single-commit caller per §1a-drift.
- `AuditLog.target_id` STRING; `payload_json` STRING needing `json.loads`.
- One audit row per transaction.
- SQLite tz coercion via `_aware()` for datetime comparisons.
- `Strategy.status` lowercase StrEnum.
- `find_in_flight_variant` module-level helper (§2b — §4's mutual-exclusion check reuses this).
- MCP server pattern `_TOOLS: list[Callable]` + module-level `async def _get`.

---

## ⚠ Posture

**§4 is the policy + measurement layer of P6b's LLM track.** Four principles:

1. **The harness measures; §5 acts.** §4 collects per-signal A/B decisions, computes the 6 metrics, signals eligibility via the double-floor — but doesn't enable LLM-driven LIVE trading anywhere. The `ALLOWED_DIRS` allowlist gets the eval-harness directory entry (paper-path LLM calls); the LIVE-path bypass (`LLM_OPT_IN_ALLOWED`) is entirely §5's surface.

2. **Mode A and Mode B are paper Strategy rows; Mode C is the original live Strategy unchanged.** Three rows, one harness binding. Mode A's role is "deterministic baseline on paper, identical params to live" — it's a control group. Mode B's role is "LLM-gated variant on paper, identical params + decision-layer wrapper." Both route orders through OrderRouter with paper creds. Mode C continues unchanged; the harness doesn't touch it.

3. **§4 and §2 are mutually exclusive per strategy.** A strategy is either under §2 param-validation OR §4 LLM-eval, not both. v1 simplicity (Q2=(a) settled). The §2a one-in-flight concurrency guard extends to cover eval_harness rows.

4. **Hard budget stop, not soft degradation.** Budget exhaustion → harness PAUSED_BUDGET → signals skip the LLM call entirely → no decision recorded for skipped signals (cleaner than recording "budget_paused" pseudo-decisions that would skew agreement-rate computation). Resumes next day on cost-window roll. The user can either wait for the next day or stop the harness to start fresh.

Paper smoke from P1-P5 byte-identical. ADR-0002 `_router_token` discipline unaffected. `check_workbench_mcp_readonly.sh` adjusts (new MCP tool is read-only). `check_no_llm_in_order_path.sh` gets the eval-harness directory entry — extension, not removal.

---

## Verification checklist — grep before pasting any code below

Per Retrospective Rec #5. With the §3b corrections fresh in mind:

- [ ] **`PaperVariantService.terminate_for_parent` signature** at `app/services/paper_variant.py` per §3b — `(session, parent_strategy_id, reason: str, user_id: int) → None`. Harness stop calls this for Mode A and Mode B.
- [ ] **`find_in_flight_variant(session, parent_strategy_id) → Strategy | None`** module-level per §2b. §4's mutual-exclusion check uses this.
- [ ] **`Strategy.status` lowercase StrEnum** values: `live`, `paper`, `idle`, `paper_variant`. Mode A and Mode B Strategy rows take `paper_variant` status.
- [ ] **`StrategyStatus.PAPER_VARIANT` + `ACTIVE_STRATEGY_STATUSES` + `ENGINE_RUNNABLE_STATUSES`** frozensets — confirmed per §2a. The new `harness_role` column distinguishes harness-spawned rows from §2 paper-variants.
- [ ] **`ALLOWED_DIRS` in `apps/backend/scripts/check_no_llm_in_order_path.sh`** — confirm current entries (likely `app/llm/` alone). §4 adds `app/services/eval_harness.py` (or the eval_harness directory if structured as a package).
- [ ] **Cost-envelope endpoint at `/api/v1/agent/cost-envelope`** (NOT `budget` per the §1a-drift correction). The harness adds a sub-key but the endpoint stays unchanged structurally.
- [ ] **`cost_cents` is fractional cents** (USD×100, stringified Decimal) per §1a-drift. Eval-harness daily cap stored as `500` cents = $5.00.
- [ ] **`call_with_budget` signature** at `app/llm/budget.py` (or wherever §1a put it) — `(session, user_id, callable, system=None, ...) → result`. Harness uses with `system="eval_harness"` and tracks cost against the new sub-key.
- [ ] **`AuditLogger.write` sync staticmethod** signature per §1a-drift. Single-commit caller pattern.
- [ ] **`AuditAction` location** at `app/audit/logger.py`. Add `EVAL_HARNESS_STARTED = "EVAL_HARNESS_STARTED"`. Total 9 → 10. Per §2b-rv: additive enum is `audit_immutability`-safe.
- [ ] **`AuditActorType.USER` for user-initiated** + **`AuditActorType.SYSTEM`** for auto-termination per §3b.
- [ ] **`OrderRouter.submit(...)` signature** — used for both Mode A and Mode B orders. Confirm paper-account binding is via the Strategy's account_id, not a separate parameter. (Mode A's Strategy row binds to the user's paper account.)
- [ ] **`get_sessionmaker()` pattern** — `app.state.session_factory` doesn't exist per the conversation summary; harness service uses `get_sessionmaker()`.
- [ ] **MCP server `_TOOLS: list[Callable]` + module-level `async def _get(path, params=None)`** at `apps/mcp-workbench/src/mcp_workbench/server.py` per §1b-drift correction. Build-server count assertion currently 19 (per §2b-variant + §2c shipped); §4 updates to 20.
- [ ] **`apps/mcp-workbench/CLAUDE.md`** decision-tree row format per §1b-drift pattern. New tool gets a row.
- [ ] **§2a's one-in-flight variant guard** — find the exact location (likely in `PaperVariantService.spawn`). §4's start-eval check adds: ALSO reject if `EvalHarness` exists for the strategy.
- [ ] **`evaluation_results_json` sub-key conventions** — not used by §4 (harness has its own table). But confirm the §2/§3 sub-keys aren't disturbed.

---

## Candid acknowledgment — what this session plan cannot predict

- **Per-signal LLM cost magnitude.** $5/day cap is a lean. Real per-signal cost depends on the signal payload size + LLM model used. Anthropic API at Claude 3.5 Sonnet (or whatever the harness uses) is roughly $0.003 per 1k input tokens + $0.015 per 1k output tokens. A structured signal payload of ~500 tokens + 100-token rationale response ≈ $0.003 per signal. At 78 5-min bars/day = ~$0.23/day per strategy. $5/day cap allows ~21 strategies under simultaneous eval. Probably comfortable; if signal payloads balloon (multi-symbol, technical indicators) cost rises. **Worth profiling on real ADR-shape signals before committing.**
- **Strategy.harness_role column vs new status enum value.** v0.1 leans column (light migration; preserves status enum's existing semantic for `paper_variant`). Alternative: new `eval_harness_a` / `eval_harness_b` enum values. Trade-off: column is more reusable but adds a discriminator field everywhere code reads "is this a paper variant?"; enum is cleaner discriminator but bloats `ACTIVE_STRATEGY_STATUSES` membership decisions. Lean column for v1; document.
- **Mode A vs Mode C signal divergence.** ADR says A receives "identical signals from the same bar dispatch" as B. But Mode C (live) also receives signals from bar dispatch. v0.1 implementation: bar dispatch fires for Mode C (existing behavior) AND for the harness (which intercepts and produces A + B). The harness's signal forwarding ensures A/B/C all see the same signal at the same wall-clock time. If the harness's intercept introduces latency or out-of-order delivery, A/B metrics could diverge from C unexpectedly. v1 assumes synchronous intercept (no async drift); profile if it becomes an issue.
- **Two-account routing for Mode A and Mode B.** Both are paper. Same paper account? Separate paper accounts? v0.1 leans: same paper account, distinguished by Strategy.id and `harness_role`. Alternative: spawn a dedicated harness-A and harness-B paper account pair. v1 same-account; if order tracking gets confused (which "AAPL buy" is A's vs B's?), revisit. Per `OrderRouter.submit` semantics: orders carry `source_id` (strategy_id) per §1a-drift, so attribution by strategy is unambiguous.
- **Decision recording ordering vs order outcome.** Per-signal flow: signal → A decides act/skip + B decides act/skip + write decision row + submit A order (if act) + submit B order (if act). Outcome (PnL) lands later when fill arrives. The decision row's outcome columns (`mode_a_outcome_pnl`, `mode_b_outcome_pnl`) update on fill arrival via a hook. v1 implements the hook in `OrderRouter` (or wherever fills land); coupling to fill processing is a real cross-cutting concern. Document.
- **Cron sweep for invalidation checks.** Parent leaves LIVE → harness auto-terminates. Could be: (a) inline check in the strategy status-mutation endpoint (like §3b's D8 hook); (b) periodic sweep (cron); (c) both. v0.1 leans (a) only — same hook point as §3b's D8. If the inline hook misses cases (out-of-band status changes via SQL), add (b) as a follow-up.
- **Eligibility computation as derived state.** v0.1: eligibility is computed on-demand (read endpoint + MCP tool); not stored on `eval_harness.eligible_at`. Pro: always fresh, no risk of staleness. Con: every read recomputes. For typical harness counts (1-2 per user), compute cost is trivial. If scale grows, cache.
- **The 6 metrics' interpretation when B has very few trades.** If B skips most signals (LLM consistently says "skip"), B's trade count is low → low statistical power. The 6 metrics compute regardless; eligibility's `B_trades ≥ 50` floor is the protection. Below 50 trades, metrics are visible in the dashboard (§4b) for transparency but eligibility flag is false.
- **Worst single-decision divergence definition.** "Max |B_outcome - A_outcome| among disagreements" — but A_outcome and B_outcome are realized PnL per signal. What if A acted and made $100 while B skipped (avoiding a loss of $50)? Disagreement: A acted, B skipped. A_outcome = +$100. B_outcome = $0 (didn't trade). Divergence = $100. Or: B was right to skip a winner (lost potential)? Or wrong? Lean: A_outcome - B_outcome (signed); positive means A was right; negative means B was right. Worst divergence = max(|A_outcome - B_outcome|). Document.
- **Disagreement asymmetry calculation.** "When they differ, who's right more often." Method: of disagreement signals, count where (A_outcome > B_outcome) vs (B_outcome > A_outcome); asymmetry = (B_better - A_better) / total_disagreements, signed. Positive = B right more often. Interpretation: above 0 favors B (LLM-gated), below 0 favors A (deterministic). v0.1 implementation; verify against ADR §49-56 metric definitions.
- **Auto-termination on parent modification: what counts as "modification"?** v0.1: any change to `Strategy.params_json` (per §3a-style detection). Alternative: only "material" changes; minor formatting updates don't count. ADR §64-68 doesn't specify; lean strict (any params_json hash change). Document.

---

## Goal

After §4-eval-harness ships:

- A user can start an LLM eval on a LIVE strategy via `POST /api/v1/strategies/{id}/start-eval`. The harness:
  - Verifies no existing §2 paper-variant in flight (mutual exclusion per Q2).
  - Spawns Mode A (paper Strategy with `harness_role="mode_a"`, identical params) and Mode B (paper Strategy with `harness_role="mode_b"`, identical params + LLM-gating).
  - Creates `eval_harness` row binding Mode C (the live original) to Mode A and Mode B.
  - Writes `EVAL_HARNESS_STARTED` audit row.
- Bar dispatch generates signals for Mode C as before; the harness intercepts to also dispatch to Mode A and Mode B.
- Mode A: deterministic decision (always act on every signal per the strategy's normal logic) → paper order via `OrderRouter.submit`.
- Mode B: LLM call (`{action, rationale}`) over structured signal → if act, paper order via `OrderRouter.submit`; if skip, no order.
- Mode C: unchanged — live deterministic decisions (always act); live orders.
- Per signal, `eval_harness_decisions` row records: signal payload, A's decision, B's decision, B's rationale, A and B order IDs (nullable when "skip").
- Daily cost tracked against `agent_envelope_json.eval_harness_cost_envelope.daily_cap_cents` (default 500 = $5.00). On exhaustion: harness state = `PAUSED_BUDGET`; subsequent signals skip the LLM call (no decision row written).
- Hourly check (or on-demand): if cost window rolled (new day), resume from PAUSED_BUDGET → ACTIVE.
- Parent strategy params modified → harness auto-terminates (clock reset); Mode A and Mode B Strategy rows terminate via `PaperVariantService.terminate_for_parent` with reason `eval_harness_modify_reset`.
- Parent strategy leaves LIVE → harness auto-terminates with reason `eval_harness_parent_deactivated`.
- User can manually stop via `POST /api/v1/eval-harness/{id}/stop`.
- `GET /api/v1/eval-harness/{harness_id}` returns: state, 6 metrics (computed on-demand), eligibility verdict (50-AND-30-AND-no-modification), Mode A/B trade counts, window dates.
- `workbench_eval_harness_metrics(strategy_id)` MCP tool exposes the same view to the agent (read-only).
- All P6+P6b mechanics unchanged; §2/§3 surfaces untouched except for the mutual-exclusion guard.
- All 13 CI invariants + 3 coverage gates green; `check_no_llm_in_order_path.sh` extended with eval_harness directory; new invariant: `check_eval_harness_paper_only.sh` confirms eval-harness orders never route to live accounts.
- Paper smoke from P1-P5 byte-identical.
- Build-server tool count 19 → 20.
- Total P6+P6b audit actions 9 → 10.

---

## §4.1 — Migration

Create `apps/backend/alembic/versions/[YYYY_MM_DD]_p6b_4_eval_harness.py`:

```python
"""P6b §4: eval_harness + eval_harness_decisions tables + harness_role column.

Revision ID: [auto]
Revises: [§3b head]
"""
from alembic import op
import sqlalchemy as sa


revision = "[auto]"
down_revision = "[§3b head]"


def upgrade() -> None:
    # 1. harness_role column on strategies (distinguishes harness-spawned rows).
    with op.batch_alter_table("strategies") as batch_op:
        batch_op.add_column(
            sa.Column("harness_role", sa.String(16), nullable=True),
        )

    # 2. eval_harness table.
    op.create_table(
        "eval_harness",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("parent_strategy_id", sa.Integer, sa.ForeignKey("strategies.id"), nullable=False),
        sa.Column("mode_a_strategy_id", sa.Integer, sa.ForeignKey("strategies.id"), nullable=False),
        sa.Column("mode_b_strategy_id", sa.Integer, sa.ForeignKey("strategies.id"), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),  # active | paused_budget | terminated
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminated_reason", sa.String(64), nullable=True),
    )

    # 3. eval_harness_decisions table (per-signal record).
    op.create_table(
        "eval_harness_decisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("harness_id", sa.Integer, sa.ForeignKey("eval_harness.id"), nullable=False),
        sa.Column("signal_uuid", sa.String(36), nullable=False),
        sa.Column("signal_payload_json", sa.JSON, nullable=False),
        sa.Column("mode_a_decision", sa.String(8), nullable=False),  # 'act' | 'skip'
        sa.Column("mode_b_decision", sa.String(8), nullable=False),
        sa.Column("mode_b_rationale", sa.Text, nullable=True),
        sa.Column("mode_a_order_id", sa.Integer, sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("mode_b_order_id", sa.Integer, sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("mode_a_outcome_pnl", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("mode_b_outcome_pnl", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_eval_harness_decisions_harness_id_recorded_at",
        "eval_harness_decisions",
        ["harness_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_eval_harness_decisions_harness_id_recorded_at")
    op.drop_table("eval_harness_decisions")
    op.drop_table("eval_harness")
    with op.batch_alter_table("strategies") as batch_op:
        batch_op.drop_column("harness_role")
```

Update `app/db/models/eval_harness.py` (new file):

```python
"""P6b §4: EvalHarness + EvalHarnessDecision models."""
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Index, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base


class EvalHarness(Base):
    __tablename__ = "eval_harness"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    parent_strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"))
    mode_a_strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"))
    mode_b_strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"))
    state: Mapped[str] = mapped_column(String(20))   # active | paused_budget | terminated
    started_at: Mapped[datetime]
    terminated_at: Mapped[datetime | None] = mapped_column(default=None)
    terminated_reason: Mapped[str | None] = mapped_column(String(64), default=None)


class EvalHarnessDecision(Base):
    __tablename__ = "eval_harness_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    harness_id: Mapped[int] = mapped_column(ForeignKey("eval_harness.id"))
    signal_uuid: Mapped[str] = mapped_column(String(36))
    signal_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    mode_a_decision: Mapped[str] = mapped_column(String(8))
    mode_b_decision: Mapped[str] = mapped_column(String(8))
    mode_b_rationale: Mapped[str | None] = mapped_column(Text, default=None)
    mode_a_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), default=None)
    mode_b_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), default=None)
    mode_a_outcome_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), default=None)
    mode_b_outcome_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), default=None)
    recorded_at: Mapped[datetime]
```

**Verify before pasting:**
- `[§3b head]` revision ID.
- Mapped-style and existing column conventions for Strategy.

---

## §4.2 — Eval harness service

Create `apps/backend/app/services/eval_harness/__init__.py` (package; this is the new ALLOWED_DIRS entry):

```python
"""P6b §4 eval-harness package.

Allowlist note: this directory is added to ALLOWED_DIRS in
check_no_llm_in_order_path.sh per ADR 0006 v2 §2. The harness module calls
Anthropic on Mode-B paper signals; the directory's purpose is visible in
code review because it's distinct from app/llm/.
"""
from app.services.eval_harness.service import (
    EvalHarnessService,
    start_eval_harness,
    stop_eval_harness,
    record_decision,
)
from app.services.eval_harness.metrics import (
    EvalHarnessComparison,
    compute_eval_harness_comparison,
)
from app.services.eval_harness.eligibility import (
    check_eligibility,
    EligibilityVerdict,
)
```

Create `apps/backend/app/services/eval_harness/service.py`:

```python
"""Eval-harness lifecycle + per-signal LLM decision capture."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, UTC
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.enums import StrategyStatus
from app.db.models.eval_harness import EvalHarness, EvalHarnessDecision
from app.db.models.strategy import Strategy
from app.services.paper_variant import find_in_flight_variant
from app.llm.budget import call_with_budget   # existing P3 §4 / P6 §1a infrastructure


logger = structlog.get_logger(__name__)


DEFAULT_DAILY_CAP_CENTS = 500   # $5/day per Q8 settled
LLM_SYSTEM_TAG = "eval_harness"


# State constants.
STATE_ACTIVE = "active"
STATE_PAUSED_BUDGET = "paused_budget"
STATE_TERMINATED = "terminated"


# Termination reasons.
REASON_USER_STOPPED = "user_stopped"
REASON_PARENT_DEACTIVATED = "parent_deactivated"
REASON_PARENT_MODIFIED = "parent_modified"
REASON_BUDGET_HARD_STOP_EXTENDED = "budget_persistent_exhaustion"   # not used in v1


async def start_eval_harness(
    session: AsyncSession,
    parent_strategy_id: int,
    user_id: int,
) -> EvalHarness:
    """Start LLM eval for a LIVE strategy.

    Per Q2 (a): mutually exclusive with §2 paper-variant. Raises if an
    in-flight paper-variant exists OR if an eval harness already runs.
    """
    parent = await session.get(Strategy, parent_strategy_id)
    if parent is None or parent.user_id != user_id:
        raise ValueError(f"Strategy {parent_strategy_id} not found / not yours")
    if parent.status != StrategyStatus.LIVE:
        raise ValueError(f"Cannot start eval on non-LIVE strategy (current: {parent.status})")

    # Mutual exclusion guards.
    existing_pv = await find_in_flight_variant(session, parent_strategy_id)
    if existing_pv is not None:
        raise ValueError(
            f"Strategy {parent_strategy_id} has §2 paper-variant in flight; "
            "cannot start eval. Stop the validation first."
        )
    existing_harness = await _find_active_harness(session, parent_strategy_id)
    if existing_harness is not None:
        raise ValueError(
            f"Strategy {parent_strategy_id} already has active eval harness #{existing_harness.id}"
        )

    now = datetime.now(UTC)

    # Spawn Mode A and Mode B paper Strategy rows. Cloned from parent;
    # same params_json; paper account binding; harness_role set.
    mode_a = _clone_strategy_for_harness(
        parent, harness_role="mode_a", user_id=user_id,
    )
    mode_b = _clone_strategy_for_harness(
        parent, harness_role="mode_b", user_id=user_id,
    )
    session.add(mode_a)
    session.add(mode_b)
    await session.flush()   # need IDs for harness row

    harness = EvalHarness(
        user_id=user_id,
        parent_strategy_id=parent_strategy_id,
        mode_a_strategy_id=mode_a.id,
        mode_b_strategy_id=mode_b.id,
        state=STATE_ACTIVE,
        started_at=now,
    )
    session.add(harness)
    await session.flush()

    # Audit row (one row per transaction).
    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(user_id),
        action=AuditAction.EVAL_HARNESS_STARTED,
        target_type="eval_harness",
        target_id=str(harness.id),
        payload={
            "harness_id": harness.id,
            "parent_strategy_id": parent_strategy_id,
            "mode_a_strategy_id": mode_a.id,
            "mode_b_strategy_id": mode_b.id,
            "started_at": now.isoformat(),
        },
        user_id=user_id,
    )
    await session.commit()
    return harness


def _clone_strategy_for_harness(
    parent: Strategy, harness_role: str, user_id: int,
) -> Strategy:
    """Clone a Strategy row for harness Mode A or Mode B.

    Identical params_json; paper account binding; harness_role tag.
    """
    return Strategy(
        user_id=user_id,
        name=f"{parent.name} ({harness_role})",
        params_json=dict(parent.params_json or {}),
        status=StrategyStatus.PAPER_VARIANT,
        parent_strategy_id=parent.id,
        harness_role=harness_role,
        account_id=_get_user_paper_account_id(user_id, parent),
        # ... other Strategy fields per existing convention
    )


async def _find_active_harness(
    session: AsyncSession, parent_strategy_id: int,
) -> EvalHarness | None:
    return (await session.execute(
        select(EvalHarness)
        .where(EvalHarness.parent_strategy_id == parent_strategy_id)
        .where(EvalHarness.state != STATE_TERMINATED)
    )).scalar_one_or_none()


async def stop_eval_harness(
    session: AsyncSession,
    harness_id: int,
    user_id: int,
    reason: str = REASON_USER_STOPPED,
) -> None:
    """Stop an active eval harness. Terminates Mode A and Mode B."""
    harness = await session.get(EvalHarness, harness_id)
    if harness is None or harness.user_id != user_id:
        raise ValueError(f"Harness {harness_id} not found / not yours")
    if harness.state == STATE_TERMINATED:
        return   # idempotent

    # Terminate Mode A and Mode B (terminate-first per §3b B3).
    from app.services.paper_variant import PaperVariantService
    await PaperVariantService(session, engine=None).terminate_for_parent(
        harness.parent_strategy_id, reason=f"eval_harness_{reason}", user_id=user_id,
    )

    # Update harness row.
    now = datetime.now(UTC)
    harness.state = STATE_TERMINATED
    harness.terminated_at = now
    harness.terminated_reason = reason
    # No new audit action for stop (per Q10 — reuse EVAL_HARNESS_STARTED enum
    # only; stop is a state change reflected on the row).

    await session.commit()


async def record_decision(
    session: AsyncSession,
    harness_id: int,
    signal_payload: dict[str, Any],
    user_id: int,
) -> EvalHarnessDecision | None:
    """Process one signal through the A/B/(skip-or-act) pipeline.

    Returns the EvalHarnessDecision row, or None if harness is paused/terminated.
    Caller (engine signal-fork hook) submits orders separately per the
    A/B decisions in the returned row.
    """
    harness = await session.get(EvalHarness, harness_id)
    if harness is None or harness.state != STATE_ACTIVE:
        return None

    signal_uuid = str(uuid.uuid4())
    # Mode A: deterministic — always acts on signal per the strategy's logic.
    mode_a_decision = "act"

    # Mode B: LLM call.
    try:
        llm_result = await call_with_budget(
            session=session,
            user_id=user_id,
            callable_=lambda: _query_llm_decision(signal_payload),
            system=LLM_SYSTEM_TAG,
            budget_subkey="eval_harness_cost_envelope",
            default_daily_cap_cents=DEFAULT_DAILY_CAP_CENTS,
        )
        mode_b_decision = llm_result["action"]  # "act" | "skip"
        mode_b_rationale = llm_result.get("rationale", "")
    except BudgetExhausted:
        # Per Q8: hard-stop on exhaustion → PAUSED_BUDGET; skip signal entirely.
        harness.state = STATE_PAUSED_BUDGET
        await session.commit()
        logger.info(
            "eval_harness_paused_budget",
            harness_id=harness_id, signal_uuid=signal_uuid,
        )
        return None
    except Exception as exc:
        logger.warning(
            "eval_harness_llm_call_failed",
            harness_id=harness_id, signal_uuid=signal_uuid, error=str(exc),
        )
        # AGENT_LLM_CALL_FAILED already written by call_with_budget on error per §1a.
        return None

    # Record decision (orders submitted by caller based on returned row).
    decision = EvalHarnessDecision(
        harness_id=harness_id,
        signal_uuid=signal_uuid,
        signal_payload_json=signal_payload,
        mode_a_decision=mode_a_decision,
        mode_b_decision=mode_b_decision,
        mode_b_rationale=mode_b_rationale,
        recorded_at=datetime.now(UTC),
    )
    session.add(decision)
    await session.commit()
    return decision


async def _query_llm_decision(signal_payload: dict[str, Any]) -> dict[str, Any]:
    """Call Anthropic with the binary act/skip prompt.

    Per ADR 0006 v2 §99 (binary contract) + §98 (structured input only,
    no free-text fields).
    """
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()
    system_prompt = (
        "You are an evaluator deciding whether to act on a trading signal. "
        "Respond with JSON: {\"action\": \"act\" or \"skip\", \"rationale\": brief reason}. "
        "Evaluate ONLY the structured signal data provided. "
        "Do not interpret free-text fields."
    )
    user_message = (
        f"Signal payload (structured):\n{json.dumps(signal_payload, sort_keys=True)}\n\n"
        "Decision (act or skip):"
    )
    resp = await client.messages.create(
        model="claude-3-5-sonnet-20241022",  # or whatever model is configured
        max_tokens=200,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    # Parse JSON from response.
    text = resp.content[0].text if resp.content else ""
    # Defensive: tolerate minor JSON formatting issues.
    try:
        parsed = json.loads(text)
        action = parsed.get("action", "").strip().lower()
        rationale = parsed.get("rationale", "")
        if action not in ("act", "skip"):
            raise ValueError(f"Invalid action: {action}")
        return {"action": action, "rationale": rationale}
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"LLM returned malformed decision: {text[:200]}") from exc
```

**Verify before pasting:**
- `call_with_budget` exact signature per §1a; `budget_subkey` parameter naming.
- `BudgetExhausted` exception class location.
- `Strategy` model: `harness_role`, `account_id`, full field list.
- `_get_user_paper_account_id` helper — verify the existing convention for binding user paper account to strategies.
- `PaperVariantService.terminate_for_parent` exact signature per §3b B1.
- `_query_llm_decision` model identifier (Sonnet 3.5 latest, etc.) — verify against current Anthropic API conventions.

---

## §4.3 — Metrics service

Create `apps/backend/app/services/eval_harness/metrics.py`:

```python
"""Eval-harness 6 metrics + EvalHarnessComparison dataclass.

Per Q5 settled: separate dataclass from §2b's VariantComparison. Reuses
the §1a-drift metric functions for the overlap deltas.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.eval_harness import EvalHarness, EvalHarnessDecision
from app.services.drift_detection import reconstruct_round_trips  # §1a-drift
from app.services.equity_curve import reconstruct_equity_curve   # §2b
from app.strategies.metrics import (
    win_rate, sharpe_ratio, max_drawdown,
)


@dataclass(frozen=True)
class EvalHarnessSideMetrics:
    trade_count: int
    win_rate: float
    sharpe_ratio: float | None
    max_drawdown: float | None


@dataclass(frozen=True)
class DecisionMetrics:
    """The 3 LLM-specific metrics."""
    decision_agreement_rate: float        # 0.0 - 1.0
    disagreement_asymmetry: float          # -1.0 to 1.0 (positive = B right more often)
    worst_single_divergence: float         # max |A_outcome - B_outcome| among disagreements
    total_signals: int
    disagreement_count: int


@dataclass(frozen=True)
class EvalHarnessComparison:
    harness_id: int
    parent_strategy_id: int
    mode_a_strategy_id: int
    mode_b_strategy_id: int
    window_start: datetime
    window_end: datetime
    mode_a_metrics: EvalHarnessSideMetrics
    mode_b_metrics: EvalHarnessSideMetrics
    deltas: dict[str, float | None]        # sharpe_delta, max_dd_delta, win_rate_delta_pp
    decisions: DecisionMetrics


def _pct_delta(b: float | None, a: float | None) -> float | None:
    if a is None or b is None or a == 0:
        return None
    return ((b - a) / abs(a)) * 100


async def compute_eval_harness_comparison(
    session: AsyncSession,
    harness_id: int,
    bar_cache=None,
) -> EvalHarnessComparison | None:
    """Compute the 6 metrics for a harness."""
    harness = await session.get(EvalHarness, harness_id)
    if harness is None:
        return None

    start = harness.started_at
    end = harness.terminated_at or datetime.now(UTC)

    # Mode A round-trips + equity curve.
    a_trips = await reconstruct_round_trips(
        session, harness.mode_a_strategy_id, start,
    )
    a_curve = await reconstruct_equity_curve(
        session, harness.mode_a_strategy_id, start, end,
    )
    b_trips = await reconstruct_round_trips(
        session, harness.mode_b_strategy_id, start,
    )
    b_curve = await reconstruct_equity_curve(
        session, harness.mode_b_strategy_id, start, end,
    )

    a_metrics = EvalHarnessSideMetrics(
        trade_count=len(a_trips),
        win_rate=win_rate(a_trips),
        sharpe_ratio=sharpe_ratio([(t, float(eq)) for t, eq in a_curve]),
        max_drawdown=max_drawdown([(t, float(eq)) for t, eq in a_curve]),
    )
    b_metrics = EvalHarnessSideMetrics(
        trade_count=len(b_trips),
        win_rate=win_rate(b_trips),
        sharpe_ratio=sharpe_ratio([(t, float(eq)) for t, eq in b_curve]),
        max_drawdown=max_drawdown([(t, float(eq)) for t, eq in b_curve]),
    )

    deltas = {
        "sharpe_delta_pct": _pct_delta(b_metrics.sharpe_ratio, a_metrics.sharpe_ratio),
        "max_drawdown_delta_pct": _pct_delta(b_metrics.max_drawdown, a_metrics.max_drawdown),
        "win_rate_delta_pp": (b_metrics.win_rate - a_metrics.win_rate) * 100,
    }

    decisions = await _compute_decision_metrics(session, harness_id)

    return EvalHarnessComparison(
        harness_id=harness_id,
        parent_strategy_id=harness.parent_strategy_id,
        mode_a_strategy_id=harness.mode_a_strategy_id,
        mode_b_strategy_id=harness.mode_b_strategy_id,
        window_start=start,
        window_end=end,
        mode_a_metrics=a_metrics,
        mode_b_metrics=b_metrics,
        deltas=deltas,
        decisions=decisions,
    )


async def _compute_decision_metrics(
    session: AsyncSession, harness_id: int,
) -> DecisionMetrics:
    """The 3 LLM-specific decision metrics per ADR §49-56."""
    decisions = list((await session.execute(
        select(EvalHarnessDecision)
        .where(EvalHarnessDecision.harness_id == harness_id)
    )).scalars().all())

    total = len(decisions)
    if total == 0:
        return DecisionMetrics(
            decision_agreement_rate=0.0,
            disagreement_asymmetry=0.0,
            worst_single_divergence=0.0,
            total_signals=0,
            disagreement_count=0,
        )

    agreements = sum(1 for d in decisions if d.mode_a_decision == d.mode_b_decision)
    disagreements = [d for d in decisions if d.mode_a_decision != d.mode_b_decision]
    n_disagreements = len(disagreements)

    if n_disagreements == 0:
        return DecisionMetrics(
            decision_agreement_rate=1.0,
            disagreement_asymmetry=0.0,
            worst_single_divergence=0.0,
            total_signals=total,
            disagreement_count=0,
        )

    # Asymmetry: of disagreements with realized outcomes, who was right more.
    # B-right means B's outcome > A's outcome (B made more money or lost less).
    scored = [
        d for d in disagreements
        if d.mode_a_outcome_pnl is not None and d.mode_b_outcome_pnl is not None
    ]
    if scored:
        b_better = sum(
            1 for d in scored if d.mode_b_outcome_pnl > d.mode_a_outcome_pnl
        )
        a_better = sum(
            1 for d in scored if d.mode_a_outcome_pnl > d.mode_b_outcome_pnl
        )
        asymmetry = (b_better - a_better) / len(scored)
        worst_divergence = max(
            float(abs(d.mode_b_outcome_pnl - d.mode_a_outcome_pnl)) for d in scored
        )
    else:
        asymmetry = 0.0
        worst_divergence = 0.0

    return DecisionMetrics(
        decision_agreement_rate=agreements / total,
        disagreement_asymmetry=asymmetry,
        worst_single_divergence=worst_divergence,
        total_signals=total,
        disagreement_count=n_disagreements,
    )
```

---

## §4.4 — Eligibility computation

Create `apps/backend/app/services/eval_harness/eligibility.py`:

```python
"""Double-floor eligibility per ADR 0006 v2 §64-68.

(B_trades ≥ 50) AND (window_days ≥ 30) AND (no parent modification since started_at)

Reset-on-modify: any change to parent.params_json after started_at →
harness auto-terminates; this function only checks the current state.
"""
from dataclasses import dataclass
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.eval_harness import EvalHarness
from app.db.models.strategy import Strategy
from app.services.eval_harness.service import STATE_ACTIVE


# Eligibility floors (per ADR §64-68).
MIN_B_TRADES = 50
MIN_WINDOW_DAYS = 30


@dataclass(frozen=True)
class EligibilityVerdict:
    eligible: bool
    b_trade_count: int
    window_days: int
    parent_modified_since_start: bool
    details: dict


async def check_eligibility(
    session: AsyncSession,
    harness_id: int,
    b_trade_count: int,    # passed from comparison computation
) -> EligibilityVerdict:
    """Compute eligibility verdict (read-only)."""
    harness = await session.get(EvalHarness, harness_id)
    if harness is None or harness.state != STATE_ACTIVE:
        return EligibilityVerdict(
            eligible=False, b_trade_count=b_trade_count, window_days=0,
            parent_modified_since_start=False,
            details={"reason": "harness_not_active"},
        )

    now = datetime.now(UTC)
    window_days = (now - harness.started_at).days

    parent = await session.get(Strategy, harness.parent_strategy_id)
    # "Modified since start" — verify with the params-snapshot-on-start
    # approach. v0.1 simplification: compare parent.updated_at to started_at.
    # If parent.updated_at > started_at, treat as modified (parent's
    # params_json change updates the column via SA touch).
    parent_modified = (
        parent.updated_at > harness.started_at
        if parent and parent.updated_at else False
    )

    trades_passed = b_trade_count >= MIN_B_TRADES
    window_passed = window_days >= MIN_WINDOW_DAYS
    not_modified = not parent_modified

    eligible = trades_passed and window_passed and not_modified

    return EligibilityVerdict(
        eligible=eligible,
        b_trade_count=b_trade_count,
        window_days=window_days,
        parent_modified_since_start=parent_modified,
        details={
            "trades_passed": trades_passed,
            "window_passed": window_passed,
            "not_modified": not_modified,
            "min_b_trades": MIN_B_TRADES,
            "min_window_days": MIN_WINDOW_DAYS,
        },
    )
```

**Note on "modified since start" detection:** v0.1 uses `parent.updated_at > harness.started_at`. ADR §64-68's "param tweak resets the clock" implies auto-terminate on modification, not a soft eligibility flip. Per the verification checklist, an inline hook in the strategy-params-mutation endpoint should auto-terminate the harness on any params_json change. This eligibility check is a defensive belt-and-suspenders read; the primary enforcement is the auto-terminate hook (see §4.5).

---

## §4.5 — Parent-modification + parent-deactivation invalidation hooks

Two D8-style hooks mirroring §3b's pattern. Both call `stop_eval_harness` with the appropriate reason.

### Hook 1: parent params modified

In the strategy-params-mutation endpoint (likely the PATCH /strategies/{id} endpoint per §2c shipped):

```python
# After applying the params_json change, before commit:
existing_harness = await _find_active_harness(session, strategy.id)
if existing_harness is not None:
    await stop_eval_harness(
        session, harness_id=existing_harness.id, user_id=current_user.id,
        reason=REASON_PARENT_MODIFIED,
    )
    # stop_eval_harness commits internally per §3b B3 ordering.
```

### Hook 2: parent leaves LIVE

In the strategy status-mutation endpoint (PATCH /strategies/{id}/status):

```python
# When transitioning out of ACTIVE_STRATEGY_STATUSES:
if old_status in ACTIVE_STRATEGY_STATUSES and new_status not in ACTIVE_STRATEGY_STATUSES:
    existing_harness = await _find_active_harness(session, strategy.id)
    if existing_harness is not None:
        await stop_eval_harness(
            session, harness_id=existing_harness.id, user_id=current_user.id,
            reason=REASON_PARENT_DEACTIVATED,
        )
```

---

## §4.6 — Endpoints

Create `apps/backend/app/api/v1/eval_harness.py`:

```python
"""GET /api/v1/eval-harness/{harness_id}
POST /api/v1/strategies/{strategy_id}/start-eval
POST /api/v1/eval-harness/{harness_id}/stop
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_session
from app.db.models.eval_harness import EvalHarness
from app.services.eval_harness import (
    compute_eval_harness_comparison,
    check_eligibility,
    start_eval_harness,
    stop_eval_harness,
)


router = APIRouter()


@router.get("/eval-harness/{harness_id}")
async def get_eval_harness(
    harness_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    harness = await session.get(EvalHarness, harness_id)
    if harness is None or harness.user_id != current_user.id:
        raise HTTPException(404, "Eval harness not found")

    comparison = await compute_eval_harness_comparison(session, harness_id)
    if comparison is None:
        return {
            "harness_id": harness_id,
            "state": harness.state,
            "started_at": harness.started_at.isoformat(),
            "terminated_at": harness.terminated_at.isoformat() if harness.terminated_at else None,
        }

    eligibility = await check_eligibility(
        session, harness_id, b_trade_count=comparison.mode_b_metrics.trade_count,
    )

    return {
        "harness_id": harness_id,
        "state": harness.state,
        "started_at": harness.started_at.isoformat(),
        "terminated_at": harness.terminated_at.isoformat() if harness.terminated_at else None,
        "terminated_reason": harness.terminated_reason,
        "comparison": _comparison_to_dict(comparison),
        "eligibility": _eligibility_to_dict(eligibility),
    }


@router.post("/strategies/{strategy_id}/start-eval")
async def start_eval_endpoint(
    strategy_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        harness = await start_eval_harness(session, strategy_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"status": "started", "harness_id": harness.id}


@router.post("/eval-harness/{harness_id}/stop")
async def stop_eval_endpoint(
    harness_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        await stop_eval_harness(session, harness_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"status": "stopped"}


def _comparison_to_dict(comp) -> dict:
    return {
        "window_start": comp.window_start.isoformat(),
        "window_end": comp.window_end.isoformat(),
        "mode_a_metrics": {
            "trade_count": comp.mode_a_metrics.trade_count,
            "win_rate": comp.mode_a_metrics.win_rate,
            "sharpe_ratio": comp.mode_a_metrics.sharpe_ratio,
            "max_drawdown": comp.mode_a_metrics.max_drawdown,
        },
        "mode_b_metrics": {
            "trade_count": comp.mode_b_metrics.trade_count,
            "win_rate": comp.mode_b_metrics.win_rate,
            "sharpe_ratio": comp.mode_b_metrics.sharpe_ratio,
            "max_drawdown": comp.mode_b_metrics.max_drawdown,
        },
        "deltas": comp.deltas,
        "decisions": {
            "decision_agreement_rate": comp.decisions.decision_agreement_rate,
            "disagreement_asymmetry": comp.decisions.disagreement_asymmetry,
            "worst_single_divergence": comp.decisions.worst_single_divergence,
            "total_signals": comp.decisions.total_signals,
            "disagreement_count": comp.decisions.disagreement_count,
        },
    }


def _eligibility_to_dict(verdict) -> dict:
    return {
        "eligible": verdict.eligible,
        "b_trade_count": verdict.b_trade_count,
        "window_days": verdict.window_days,
        "parent_modified_since_start": verdict.parent_modified_since_start,
        "details": verdict.details,
    }
```

Register in `app/api/v1/__init__.py`.

---

## §4.7 — MCP tool `workbench_eval_harness_metrics`

Add to `apps/mcp-workbench/src/mcp_workbench/server.py`:

```python
async def workbench_eval_harness_metrics(*, strategy_id: int) -> dict:
    """Eval harness comparison for the active harness on `strategy_id`.

    Returns harness state + 6 metrics + eligibility, or
    {"status": "no_active_harness"} if none.
    """
    # Find the active harness for this strategy via the read endpoint.
    # Backend resolves strategy_id → harness_id internally.
    return await _get(f"/api/v1/strategies/{strategy_id}/eval-harness")


_TOOLS.append(workbench_eval_harness_metrics)
```

(Backend adds a small `GET /api/v1/strategies/{strategy_id}/eval-harness` endpoint that returns the active harness for the strategy or `no_active_harness`.)

Build-server test asserts tool count 19 → **20**.

---

## §4.8 — New audit action + ALLOWED_DIRS extension + new invariant

### Audit action

In `app/audit/logger.py`:

```python
class AuditAction(StrEnum):
    # ... existing 9 actions ...
    EVAL_HARNESS_STARTED = "EVAL_HARNESS_STARTED"
```

Total 9 → 10. `audit_immutability` invariant additive-safe per §2b-rv.

### ALLOWED_DIRS extension

In `apps/backend/scripts/check_no_llm_in_order_path.sh`:

```bash
# Existing:
ALLOWED_DIRS=("app/llm/")

# Extended for P6b §4:
ALLOWED_DIRS=("app/llm/" "app/services/eval_harness/")
```

### New CI invariant

Create `apps/backend/scripts/check_eval_harness_paper_only.sh`:

```bash
#!/usr/bin/env bash
# P6b §4: confirm eval-harness Mode A and Mode B Strategy rows only ever
# route orders through paper accounts. The invariant is structural: harness
# spawn binds to paper accounts; modifying that wiring requires explicit
# review. This script checks that the eval_harness module doesn't reference
# live account ids.

set -euo pipefail

if grep -rn "live_account\|account.live\|broker_mode.*live" \
   apps/backend/app/services/eval_harness/ 2>/dev/null; then
    echo "FAIL: eval_harness references live accounts"
    exit 1
fi
echo "OK: eval_harness paper-only"
```

Register in CI workflow (alongside the 13 existing invariants — now 14).

---

## §4.9 — Tests

### Migration (`tests/test_migration_p6b_4.py`)
- `test_migration_upgrades_and_round_trips`
- `test_harness_role_column_added`
- `test_eval_harness_table_created`
- `test_eval_harness_decisions_table_created`
- `test_index_on_decisions_harness_id_recorded_at`

### Service (`tests/services/test_eval_harness_service.py`)
- `test_start_eval_creates_mode_a_and_mode_b_and_harness_row`
- `test_start_eval_writes_audit`
- `test_start_eval_409_when_existing_paper_variant` (Q2 mutual exclusion)
- `test_start_eval_409_when_existing_harness`
- `test_start_eval_409_when_parent_not_live`
- `test_stop_eval_terminates_mode_a_and_mode_b`
- `test_stop_eval_idempotent`
- `test_record_decision_writes_row`
- `test_record_decision_returns_none_when_paused`
- `test_record_decision_transitions_to_paused_on_budget_exhaustion`

### Metrics (`tests/services/test_eval_harness_metrics.py`)
- `test_six_metrics_computed_correctly`
- `test_decision_agreement_rate_no_decisions`
- `test_decision_agreement_rate_all_match`
- `test_decision_agreement_rate_partial_match`
- `test_disagreement_asymmetry_signed`
- `test_worst_single_divergence_max_abs`
- `test_overlap_deltas_use_drift_metric_functions`

### Eligibility (`tests/services/test_eval_harness_eligibility.py`)
- `test_eligibility_requires_50_b_trades`
- `test_eligibility_requires_30_days_window`
- `test_eligibility_requires_no_parent_modification`
- `test_eligibility_AND_not_OR` (load-bearing per §3a lesson)

### Endpoints (`tests/api/test_eval_harness_endpoints.py`)
- `test_get_returns_state_and_comparison`
- `test_start_eval_returns_harness_id`
- `test_stop_eval_returns_status`
- `test_endpoints_404_for_other_user`
- `test_start_eval_409_when_mutual_exclusion`

### MCP (`tests/mcp/test_eval_harness_tool.py`)
- `test_workbench_eval_harness_metrics_passthrough`
- `test_build_server_tool_count_now_20`

### Invariant (`tests/test_eval_harness_invariant.py`)
- `test_check_eval_harness_paper_only_passes` (grep guard)
- `test_allowed_dirs_includes_eval_harness`

### Hook tests (`tests/api/test_eval_harness_hooks.py`)
- `test_parent_params_change_auto_terminates_harness`
- `test_parent_deactivation_auto_terminates_harness`

---

## §4.10 — Manual smoke

```bash
# 0. Prerequisites
git describe --tags --abbrev=0  # expect: p6b-session3-promote-complete

# 1. Migration round-trip
cd apps/backend && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && cd ../..

# 2. Bring up stack
docker compose up -d && sleep 30
./scripts/login_helper.sh

# 3. Need a LIVE strategy with no existing paper-variant
STRAT_ID=$(curl -s -b /tmp/cookies.txt "http://127.0.0.1:8000/api/v1/strategies" \
  | jq -r '.items[] | select(.status=="live") | .id' | head -1)

# 4. Start eval
curl -s -b /tmp/cookies.txt -X POST \
  "http://127.0.0.1:8000/api/v1/strategies/${STRAT_ID}/start-eval" | jq
# Expect: {status: "started", harness_id: N}

HARNESS_ID=$(curl -s -b /tmp/cookies.txt -X POST \
  "http://127.0.0.1:8000/api/v1/strategies/${STRAT_ID}/start-eval" | jq -r '.harness_id')
# Note: second call should 409 (existing harness)

# 5. Verify Mode A and Mode B rows created
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT id, name, harness_role, status, parent_strategy_id FROM strategies
WHERE harness_role IS NOT NULL ORDER BY id DESC LIMIT 2;"

# 6. Verify eval_harness row + audit
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT id, state, parent_strategy_id, mode_a_strategy_id, mode_b_strategy_id, started_at
FROM eval_harness ORDER BY id DESC LIMIT 1;"

docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT action FROM audit_log WHERE action='EVAL_HARNESS_STARTED' ORDER BY id DESC LIMIT 1;"

# 7. Verify mutual exclusion: try to spawn §2 paper-variant on the same strategy
PROP_ID=$(...)   # a proposal on STRAT_ID
curl -s -b /tmp/cookies.txt -X POST \
  "http://127.0.0.1:8000/api/v1/proposals/${PROP_ID}/validate" | jq
# Expect: 409 — already has eval harness

# 8. Get harness state + metrics (empty for fresh harness)
curl -s -b /tmp/cookies.txt "http://127.0.0.1:8000/api/v1/eval-harness/${HARNESS_ID}" | jq

# 9. MCP tool
docker compose exec mcp-workbench uv run python -c "
import asyncio
from mcp_workbench.server import workbench_eval_harness_metrics
print(asyncio.run(workbench_eval_harness_metrics(strategy_id=${STRAT_ID})))
"

# 10. Build-server tool count
docker compose exec mcp-workbench uv run python -c "
from mcp_workbench.server import _TOOLS
print(f'Tool count: {len(_TOOLS)}')"
# Expect: 20

# 11. Auto-terminate on parent params modification
curl -s -b /tmp/cookies.txt -X PATCH \
  "http://127.0.0.1:8000/api/v1/strategies/${STRAT_ID}" \
  -H "Content-Type: application/json" \
  -d '{"params_json": {"some": "change"}}'

docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT state, terminated_reason FROM eval_harness WHERE id=${HARNESS_ID};"
# Expect: state=terminated, reason=eval_harness_parent_modified

# 12. CI invariants
bash apps/backend/scripts/check_no_llm_in_order_path.sh
bash apps/backend/scripts/check_eval_harness_paper_only.sh
# Both: OK

# 13. LOAD-BEARING: paper smoke byte-identical
PAPER_ACC=$(curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/accounts \
  | jq -r '.items[] | select(.mode=="paper") | .id')
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{\"account_id\":${PAPER_ACC},\"symbol\":\"AAPL\",\"side\":\"buy\",\"type\":\"market\",\"qty\":\"1\",\"tif\":\"day\",\"source\":\"manual\"}" \
  | jq '{status}'
# Expect: status=accepted
```

---

## §4.11 — Notes & gotchas

1. **NO LIVE LLM TRADING** — load-bearing invariant. §4's eval-harness directory is allowlisted for paper-path LLM calls only. The `check_eval_harness_paper_only.sh` invariant guards against any accidental live-account reference in the eval_harness module. §5 is the only session that touches the LIVE order path.

2. **Mutual exclusion with §2 paper-variant** per Q2 settled. The start-eval endpoint AND the §2 spawn endpoint both check for the other's existence. v1: surface as 409 with explanatory message.

3. **Binary act/skip LLM contract** per ADR §99. The harness sends a structured signal payload (no free text per §98) and parses a JSON response `{"action": "act"|"skip", "rationale": str}`. Malformed responses raise; failed LLM calls log `AGENT_LLM_CALL_FAILED` (existing P6 audit action — no new action needed).

4. **Per-signal cost: $5/day default, hard-stop on exhaustion.** Per Q8 settled. Budget machinery from §1a reused; sub-key `eval_harness_cost_envelope.daily_cap_cents` (= 500 = $5.00 in fractional cents per §1a convention). On exhaustion: harness `state=paused_budget`; signals continue but harness skips the LLM call entirely (no decision recorded — keeps agreement-rate metric clean). Resumes next day on cost-window roll.

5. **Decision recording is one row per signal.** Per Q4 settled — dedicated table, not audit hash chain. Hash chain would be swamped by per-signal volume. Per-signal LLM rationale stored in `mode_b_rationale` column; full prompt/response audit (ADR §3.4) is §5/live concern.

6. **Mode A and Mode B Strategy rows remain alive throughout the eval window.** Per the §3b A1 lesson — terminating mid-eval breaks the read endpoint + dashboard data flow. Termination only on harness stop (manual or auto-invalidation).

7. **Parent params modification → reset clock per ADR §64-68.** Inline hook in PATCH /strategies/{id} fires `stop_eval_harness(reason=parent_modified)`. User must explicitly re-start eval. v1 detection: any params_json change triggers reset (no "material" filter).

8. **Parent leaves LIVE → auto-terminate** mirroring §3b's D8 invalidation pattern. Inline hook in status-mutation endpoint.

9. **Six metrics defined per ADR §49-56**: Win-rate / Sharpe / max-DD deltas (3 overlap with §2b) + decision-agreement / asymmetry / worst-divergence (3 new). The overlap deltas reuse §1a-drift's metric functions; the 3 new compute over the decisions table.

10. **`EvalHarnessComparison` is separate from `VariantComparison`** per Q5 settled. The lifecycle contexts are different — eval-harness has 3 modes + decisions; variant-comparison has parent + variant + lifecycle gates.

11. **Eligibility computed on-demand** (read-only). The 50-AND-30-AND-no-modification verdict feeds §5's opt-in dialog. §4 doesn't store eligibility flag on the row.

12. **Outcome attribution on fill arrival.** The `mode_a_outcome_pnl` and `mode_b_outcome_pnl` columns populate when fills land on Mode A and Mode B paper orders. Hook in `OrderRouter` (or wherever fills processing lives) finds matching decision row + updates outcome columns. v1 implementation; coupling to fill processing is a cross-cutting concern.

13. **Same paper account for Mode A and Mode B** in v0.1. Order attribution via `Order.source_id` (= Mode A's or Mode B's strategy_id) per §1a-drift's existing convention. Unambiguous.

14. **`harness_role` column on Strategy** as discriminator (vs new status enum value). v1 lighter; if status-based discrimination becomes painful, escalate.

15. **`ALLOWED_DIRS` extension is the §4 piece of ADR 0006 v2's invariant work.** §5 adds the `LLM_OPT_IN_ALLOWED` DB-flag-bypass mechanism — separate concern; §4 does not touch live-path enforcement.

16. **`check_eval_harness_paper_only.sh`** is a new CI invariant (14 → 15 total). Defends against future drift where someone might modify the harness module to reference live accounts.

17. **MCP tool count 19 → 20.** New tool `workbench_eval_harness_metrics`. Build-server count assertion updates.

18. **Total P6+P6b audit actions 9 → 10.** `EVAL_HARNESS_STARTED` only. Stop is reflected in row state (not a new action).

19. **`_router_token` discipline preserved.** §4 orders use OrderRouter.submit per ADR §108; no order-path code changes.

20. **`check_workbench_mcp_readonly.sh` green.** New MCP tool is read-only GET passthrough.

21. **`check_agent_no_db_access.sh` unaffected.** §4 adds nothing to `apps/agent/`.

22. **Walk-away ≥1h before merge.** Per Retrospective Rec #6. The metrics + decisions table + mutual-exclusion logic together are non-trivial.

23. **Standing cleanup-PR carry-forwards:** `check_p3_coverage.py --cov-report=xml` locally; explicit `git add` over `Docs/`.

24. **§4b dashboard UI will need the `EvalHarnessComparison` shape from this session.** Drafted §4b only after §4 ships (per Rec #10).

25. **Cost-profile sanity check before deploy.** Per Candid Acknowledgment: validate per-signal cost on realistic ADR-shape signals; the $5/day default assumes ~21 strategies under simultaneous eval based on $0.003/signal estimate. If actual cost is materially higher, revisit the default.

---

## §4.12 — Commit and PR

Branch: `feat/p6b-session4-eval-harness`. Single PR; walk-away ≥1 hour before merge.

Tag: `git tag -a p6b-session4-eval-harness-complete -m "P6b §4 eval-harness backend"`.

After §4 ships: draft `TradingWorkbench_P6b_Session4b_dashboard_v0_1.md` against this Results doc.

---

## §4.13 — Verification Checklist (full session)

- [ ] §4.1 Migration adds `eval_harness` + `eval_harness_decisions` tables + `harness_role` column; round-trips cleanly.
- [ ] §4.2 `eval_harness/service.py`: start/stop/record_decision with mutual-exclusion guards; budget exhaustion → PAUSED_BUDGET; LLM call uses structured payload + binary contract.
- [ ] §4.3 6 metrics computed correctly; overlap deltas reuse §1a-drift functions; 3 decision metrics defined.
- [ ] §4.4 Eligibility: 50-AND-30-AND-no-modification with correct AND logic.
- [ ] §4.5 Invalidation hooks fire on parent params modification and parent deactivation.
- [ ] §4.6 Endpoints: GET / start-eval / stop-eval; ownership validated; 409 on mutual exclusion.
- [ ] §4.7 New MCP tool; build-server count 19 → 20; CLAUDE.md row added.
- [ ] §4.8 `EVAL_HARNESS_STARTED` enum added (9 → 10); `ALLOWED_DIRS` extended; `check_eval_harness_paper_only.sh` registered and passing.
- [ ] §4.9 ~32 backend tests pass; full suite green; mypy/ruff clean.
- [ ] §4.10 Manual smoke: start → mutual-exclusion → audit → MCP → auto-terminate-on-modify; paper smoke byte-identical.
- [ ] §4.11 Notes & gotchas reviewed.
- [ ] `_router_token` discipline preserved; ADR-0002 invariant green.
- [ ] `audit_immutability` invariant green with new enum value.
- [ ] `check_no_llm_in_order_path.sh` green with extended ALLOWED_DIRS.
- [ ] `check_eval_harness_paper_only.sh` green (new invariant).
- [ ] All 14 CI invariants + 3 coverage gates green; P3 gate verified locally with `--cov-report=xml`.
- [ ] §4.12 PR merged; `p6b-session4-eval-harness-complete` tag pushed.

---

# Results template stub — fill at execution time

```markdown
# P6b Session 4-eval-harness — Results

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | [YYYY-MM-DD] |
| Phase | P6b §4-eval-harness — Mode-B LLM Eval Harness (backend) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Shipped as | PR **#[NN]** — branch `feat/p6b-session4-eval-harness`; tag **`p6b-session4-eval-harness-complete`** |
| Built against | `main` at `p6b-session3-promote-complete` (`5213c69`) |
| Verdict | **GO / NO-GO.** |
| Method | Executed: full backend suite; mypy; ruff; migration round-trip; all CI invariants (now 14). |

## Gates — PASS (executed)

| § | Gate | Result |
|---|---|---|
| 4.1 | Migration round-trip + tables + harness_role column | [✅ / details] |
| 4.2 | Service: start/stop/record + mutual-exclusion + budget | [✅ / details] |
| 4.3 | 6 metrics + EvalHarnessComparison | [✅ / details] |
| 4.4 | Eligibility AND logic | [✅ / details] |
| 4.5 | Auto-invalidation hooks | [✅ / details] |
| 4.6 | Endpoints; 409 on mutual exclusion | [✅ / details] |
| 4.7 | MCP tool; count 19 → 20 | [✅ / details] |
| 4.8 | Audit enum + ALLOWED_DIRS + new invariant | [✅ / details] |
| 4.9 | ~32 tests pass | [✅ / details] |
| 4.10 | Manual smoke; paper smoke byte-identical | [✅ / details] |

## Deliberate deviations (as-built vs the v0.1 plan)

Pre-named candidates (from v0.1's Candid Acknowledgment):

- **[Sharpe margin / metric formula edge cases]** — [confirmed / required different handling.]
- **[Strategy.harness_role column vs status enum]** — [column held / needed enum value.]
- **[Mode A vs Mode C signal sync]** — [synchronous intercept worked / required async coordination.]
- **[Two-account Mode A/B vs one]** — [single paper held / required separate accounts.]
- **[Per-signal cost magnitude]** — [$5/day cap held / required different default.]
- **[Cron sweep for invalidation]** — [inline hook only worked / required sweep too.]
- **[Eligibility derived vs stored]** — [on-demand held / required cache.]
- **[Worst-divergence definition]** — [max abs held / required different semantics.]
- **[Disagreement asymmetry signed direction]** — [B-positive held / required A-positive.]
- **[Parent modification detection]** — [updated_at compare worked / required hash-based detection.]

Other deviations: [Deviation N].

## Findings / punch list

- [ ] [Anything specific.]
- [ ] [Flaky test status.]

## Deferred gates — require a live stack

- [ ] **Real LIVE strategy → eval start → A/B signals → real LLM calls → 6 metrics populated** end-to-end.
- [ ] **Real budget exhaustion → PAUSED_BUDGET → resume next day** end-to-end.
- [ ] **Real parent params modification → auto-terminate** end-to-end.
- [ ] **Post-merge CI run green** — pending PR.

## To close §4 cleanly

1. Walk away ≥1 hour before opening PR.
2. Confirm post-merge CI green; tag `p6b-session4-eval-harness-complete`.
3. **Next: §4b** — comparison dashboard UI — draft against this Results doc.

---

*P6b Session 4-eval-harness results v0.1 — recorded [DATE].*
```

---

*End of P6b Session 4-eval-harness v0.1. Drafted against §3b-promote Results' 8 corrections + the 11-question architecture analysis turn's settled answers (Q1=(b) first-class eval_harness, Q2=(a) mutually exclusive with §2, Q3=(a) own ALLOWED_DIRS entry, Q4 dedicated decisions table, Q5 separate EvalHarnessComparison, Q6 split via §4/§4b, Q7 binary act/skip + structured payload, Q8 $5/day eval cap hard-stop, Q9 eligibility read-only in §4, Q10 single EVAL_HARNESS_STARTED audit action, Q11 single PR). THRESHOLD-VERIFY block at the top pins five thresholds to ADR 0006 v2 sections (§99 contract, §98 input constraint, §64-68 eligibility floors, §108 order routing, §49-56 metric definitions) per the §3 lesson — ADR-shipped reading is the source of truth, not analyst summary. Ships the migration (eval_harness + eval_harness_decisions tables + harness_role column), eval-harness service (start/stop/record + LLM call via call_with_budget with eval_harness_cost_envelope sub-key + paused-budget hard-stop), metrics service (EvalHarnessComparison with 6 metrics reusing §1a-drift functions for 3 overlap deltas + 3 new decision metrics), double-floor eligibility (50-AND-30-AND-no-modification, derived not stored), invalidation hooks (parent params modify + parent deactivation), 3 endpoints (GET / start-eval / stop-eval), new MCP tool (count 19 → 20), new audit action (9 → 10), ALLOWED_DIRS extension, new CI invariant (13 → 14). NO LIVE LLM trading anywhere — that's §5. Together §4 builds the policy + measurement substrate; §4b adds the dashboard UI; §5 adds the LIVE opt-in flow + the LLM_OPT_IN_ALLOWED bypass mechanism + the live invariant extension. The Closure plan's remaining P6b commitments after §5: extended-evaluation feature + strategy-version archiving (both deferred per ADR-faithful-but-pragmatic v1 choices).*
