# P6b Session 4 — Mode-B LLM eval harness — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-05 |
| Phase | P6b — §4 (Mode-B LLM evaluation harness, ADR 0006 v2) |
| Plan doc | `TradingWorkbench_P6b_Session4_eval_harness_v0_1.md` (+ the 2026-06-04 review-corrections section) |
| Predecessor | `p6b-session3-promote-complete` (`5213c69`) |
| Tag | **`p6b-session4-eval-harness-complete`** (`c1cfde6`, the §4 squash merge / todo commit) |
| Shipped as | PR **#63** — branch `feat/p6b-session4-eval-harness`; squash-merged `c1cfde6` |
| Verdict | **GO.** Paper-only A/B LLM eval harness. Full backend (935/9 skip/0 fail) + mcp-workbench (27) suites + mypy + ruff + migration round-trip + 3 coverage gates + all 9 shell invariants (incl. the new paper-only invariant #12) green. No frontend. |

## Why this session existed

ADR 0006 v2 forbids LLM calls in the order path *by default* and only permits an LLM-driven live opt-in (§5) after a strategy has been **evaluated on paper** in a controlled A/B comparison. §4 builds that evaluation harness. It is the gate the §5 opt-in reads; without it, "the LLM is beating the deterministic strategy" is an unfounded claim.

## What shipped

- **Schema** — `eval_harness` + `eval_harness_decisions` tables; `strategies.harness_role` (`mode_a` / `mode_b` / NULL); `AuditAction.EVAL_HARNESS_STARTED` (9 → 10 actions). Alembic **`e9a3c7f1d2b4`** (down-rev `d7f4a9c2e1b8`; `batch_alter_table` adds `harness_role`, creates both tables + indexes) — up → down → up verified.
- **Gate** (`app/services/eval_harness/gate.py`, the allowlisted LLM module) — `make_harness_submit_fn(...)` wraps Mode A's `submit_order_fn`. Per intent: (1) submit A (always — the deterministic control), (2) budget-gate (`_harness_spend_today_cents` sums `llm_cost_cents` over 24h; ≥ `$5/day` → harness `paused_budget`, no B), (3) `query_llm_decision` (Haiku, structured-only signal payload, JSON act/skip, **defaults skip on garbage**), (4) if "act" submit B via `replace(order_request, source_id=str(mode_b_id))`, (5) record one paired `EvalHarnessDecision`. `GATE_MODEL = claude-haiku-4-5-20251001`, `DEFAULT_DAILY_CAP_CENTS = 500`.
- **Engine integration** (`app/strategies/engine.py`) — `register()` injects the wrapped submit fn when `row.harness_role == "mode_a"` (looks up the non-terminated `EvalHarness` for that clone). Mode B is **never registered** — it is an IDLE `source_id` bucket whose id tags B's orders so §1a/§2b reconstruction can rebuild B's equity separately.
- **Service** (`service.py`) — `start_eval_harness` (guards: parent_not_found / parent_not_live / paper_variant_in_flight / eval_harness_already_active; spawns Mode A `PAPER_VARIANT` + Mode B `IDLE`; audit; commit-then-register A), `stop_eval_harness`, `terminate_harness_for_parent` (auto-invalidation), `_terminate` (unregister A or set IDLE; mark terminated; idempotent).
- **Metrics** (`metrics.py`) — the **six** ADR-0006-v2 metrics. 3 equity deltas (win-rate / Sharpe / max-dd, B − A) reuse `reconstruct_round_trips` + `reconstruct_equity_curve`. 3 decision metrics from the paired rows: agreement rate (= B's act rate, since A always acts), disagreement asymmetry (among B's skips, b_right − b_wrong over scored, signed +favours B), worst single divergence (max |A outcome| among skips). Outcomes are **derived on demand** via a focused FIFO `_order_realized_pnl` that attributes each round-trip's realized PnL to the entry order — no real-time fill hook.
- **Eligibility** (`eligibility.py`) — the opt-in double-floor: **≥50 Mode-B trades AND ≥30 days AND harness still ACTIVE** (the no-modification floor is enforced upstream by the invalidation hooks). §5's opt-in dialog consumes the verdict.
- **API + MCP** — `POST /strategies/{id}/start-eval`, `POST /eval-harness/{id}/stop`, `GET /strategies/{id}/eval-harness` (state + 6 metrics + eligibility, or `no_active_harness`). MCP `workbench_eval_harness_metrics` (**19 → 20** tools).
- **Invalidation hooks** — `stop_strategy` (strategies.py) + `deactivate_strategy` (activation.py) call `terminate_harness_for_parent` after the §2 D8 variant terminate.
- **CI invariant #12** — `check_eval_harness_paper_only.sh` (wired into `ci.yml`; CLAUDE.md eleven → **twelve**). Enforces: Mode A spawns `PAPER_VARIANT` + Mode B spawns `IDLE`; no `LIVE`/`PENDING_LIVE` status assigned anywhere in `app/services/eval_harness/`; B inherits A's account (`replace(order_request, source_id=...)` rewrites only `source_id`, never `account_id`). `eval_harness` also added to the no-LLM-in-order-path `ALLOWED_DIRS`.

## The doc was broken — what was rebuilt

The v0.1 plan's core mechanism was **fabricated**: `call_with_budget` / `BudgetExhausted` / `app/llm/budget.py` do not exist, and the "engine signal-fork hook" the service relied on was never implemented. Surfaced as a stop-the-PR finding (Jay chose Option A: settle the engine mechanism, then implement). Rebuilt as:

1. The real interception point — wrapping Mode A's `submit_order_fn` at `engine.py` register (the ADR-0002-respecting seam).
2. A real budget gate — an `llm_cost_cents` column summed per harness over 24h (not the nonexistent budget module; not the audit log, which per-signal volume would swamp).
3. Derived-outcome metrics — on-demand FIFO attribution (no cross-cutting real-time fill hook).
4. Mode B as an **IDLE bucket**, not a running `PAPER_VARIANT` (else boot-resume would run it deterministically and pollute B's data).
5. `from app.db.base import Base` (the doc's `app.db.models.base` is wrong); down-rev `d7f4a9c2e1b8`; `EVAL_HARNESS_STARTED` added. (7 corrections logged in the plan doc's review-corrections section.)

## Real bug fixed (the tests surfaced it)

§2 paper-variant **in-flight detection** (`_in_flight_variant_for`, `find_in_flight_variant`) **and** the 90-day **expiry sweep** (`run_paper_variant_expiry`) all selected `status == PAPER_VARIANT` by parent — which **matched the harness's own Mode-A clone** (also `PAPER_VARIANT`). Consequences: a second `start-eval` wrongly reported `paper_variant_in_flight` (never reaching the harness guard), and the sweep would have terminated a live harness's Mode A after 90 days via the §2 `terminate` path (which expects a proposal). Fix: all three queries now filter **`harness_role IS NULL`** — a §2 paper variant has a null role; a harness clone is tagged. Caught only because the mutual-exclusion tests exercised the second-start and cross-direction cases.

## Verification

- **Backend**: `pytest` full suite **935 passed / 9 skipped / 0 failed** (incl. 38 new §4 tests: gate, service, metrics, eligibility, endpoints). ruff + mypy(172) clean. Migration round-trips.
- **Coverage gates**: risk 0.904 / P2 / P3 — all exit 0.
- **Shell invariants**: all 9 green — strategy-isolation, mcp-readonly, no-LLM-in-order-path (with the new allowlist entry), broker-isolation, no-env-credentials, audit-immutability, workbench-mcp-readonly, agent-no-DB, **eval-harness-paper-only (new)**.
- **mcp-workbench**: 27 passed; ruff + mypy clean (fresh `.venv`, `pip install -e ".[dev]"`).
- **No frontend** changes (the §5 opt-in UI is a later session) — vitest not implicated.
- **PR CI**: all jobs green (Python-backend 4m8s). Merged on Jay's "merge it once CI is green".

## Deferred (live, non-Norton + credentialed stack)

A real harness accumulating Mode-A and Mode-B fills with a real `ANTHROPIC_API_KEY` driving the Haiku gate end-to-end (the in-suite tests mock `create_message` and the credential store); the eligibility floor crossing 50 trades / 30 days against real paper fills; and the §5 opt-in dialog reading a real eligibility verdict.

## Next

**P6b §5** — the LLM-driven live opt-in. Its own decision turn: it touches the order-path LLM allowlist per ADR 0006 v2 §5 (the `LLM_OPT_IN_ALLOWED` flag + 7-day activation cooldown + typed acknowledgment + $10/day live cap) — the *only* sanctioned path for LLM calls in the order path. Still pending (live, non-Norton): **§1b.12 → `p6-session1-complete`** + the §2-variant live cross-session smoke.
