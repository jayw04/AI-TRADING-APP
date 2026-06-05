# P6b Session 5 — LLM-driven live trading opt-in — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-05 |
| Phase | P6b — §5 (LLM-driven live trading opt-in, ADR 0006 v2 §5) — **completes P6b** |
| Plan doc | `TradingWorkbench_P6b_Session5_optin_v0_1.md` (revised 2026-06-05: budget $5, §5.4 nest-in-§4.5, unblocked) |
| Predecessor | `p6b-session4-5-autodispatch-complete` (ADR 0015) |
| Tag | **`p6b-session5-llm-optin-complete`** (`67d9934` squash → moved to the §5 todo commit) |
| Shipped as | PR **#65** — branch `feat/p6b-session5-llm-optin`; squash-merged `67d9934` |
| Verdict | **GO. P6b COMPLETE.** The only sanctioned LLM-in-order-path, fully gated. Full backend (976/9 skip/0 fail) + frontend (vitest 128) + mypy + ruff + tsc + eslint + 3 coverage gates + all 10 shell invariants (incl. the new #13) green. |

## What shipped

- **Schema** — version-pinned `llm_opt_in` table (`pending` → `active` → `opted_out`); an `active` row **is** the `LLM_OPT_IN_ALLOWED` runtime bypass. Alembic `f1b8d3e6a2c7` (down-rev `e9a3c7f1d2b4`; round-trips). No new `StrategyStatus`. The version pin gives the ADR's modification-floor for free (a param tweak bumps `strategies.version` → `find_active_opt_in` no longer matches).
- **Live gate** (`app/services/llm_live_gate/`, a new allowlisted module, separate from §4's paper `eval_harness` so invariant #12 is untouched): `make_live_llm_submit_fn` per live intent — active-opt-in lookup → per-user budget → Anthropic key → `query_live_llm_decision` (Haiku, structured-only, returns full prompt+response for the audit) → `act` submits / `skip` suppresses (`ReasonCode.LLM_SKIPPED`). **Fail-safe = deterministic baseline** (opt-in absent / over budget / no key / error → `real_submit`). Per-USER **$5/day** cap (`DEFAULT_LIVE_DAILY_CAP_CENTS = 500`).
- **Engine composition** — for a LIVE strategy: `OrderRouter.submit` → [§5 LLM gate, if opted in] → [§4.5 master-switch suppressor, **outermost**]. An off master switch returns before the LLM is consulted (no call, no cost).
- **Audit** — `LLM_LIVE_DECISION` writes the full prompt + response + baseline (`act`) + outcome to the hash chain (ADR line 79); the per-user budget sums `cost_cents` from those rows via `json_extract` (low volume — one live strategy). `LLM_OPT_IN_INITIATED` / `_ACTIVATED` / `LLM_OPT_OUT` for the lifecycle. On-call runbook scenario added.
- **Lifecycle** (`LLMOptInService`): `initiate_opt_in` (typed-ack phrase + TOTP, eligibility-gated on §4's `check_eligibility`) → `pending` → 7-day cron (`llm_opt_in_completion`) → `active` (re-register so the gate applies); `opt_out` frictionless (re-register drops the gate); a version drift / left-LIVE during the window → invalidated.
- **Invariants** — `llm_live_gate` added to #11's `ALLOWED_DIRS` (the live bypass); **new #13** `check_llm_optin_bypass_gated.sh` asserts the gate honors `find_active_opt_in` + `strategy_version` + `daily_cap_cents` + the deterministic `real_submit` fail-safe. CLAUDE.md twelve → **thirteen**.
- **Surfaces** — `POST /strategies/{id}/llm-opt-in` / `llm-opt-out`, `GET /strategies/{id}/llm-opt-in`; MCP `workbench_llm_opt_in_status` (20 → 21); zero-dep `LLMOptInCard` (ineligible progress / eligible typed-ack+TOTP modal / pending countdown / active `$spent / $cap` + opt-out).

## Recorded deviations

1. **Budget $5/day, not $10** (owner instruction 2026-06-05). ADR 0006 v2 line 100 still states `$10/day`; $5 is more conservative and user-configurable upward. Documented in the §5 doc banner + the gate constant; the **ADR text was left unchanged** (pending owner's call on amending it).
2. **`raise-cap` endpoint deferred to §5b** — the cap *field* + enforcement ship; the upward-config endpoint (a 5th audit action) is deferred to keep §5 at four audit actions.

## Verification

- **Backend**: `pytest` full suite **976 passed / 9 skipped / 0 failed** (27 new §5 tests: gate [9], service [13], endpoint [7]... net +27). ruff + mypy(180) clean. Migration round-trips up/down/up.
- **Coverage gates**: risk 0.904 / P2 / P3 — pass.
- **Shell invariants**: all 10 green, including the new `check_llm_optin_bypass_gated.sh` (#13).
- **mcp-workbench**: 28 passed; ruff + mypy clean. **Frontend**: vitest **128 passed** (+3), tsc + eslint clean.
- **PR CI**: all 10 jobs green (Python-backend 4m15s). Merged on the owner's "merge on green."

## Deferred (live, non-Norton + creds)

A real opt-in reaching `active` and a real `ANTHROPIC_API_KEY` driving the live Haiku gate end-to-end on a live Alpaca account (the gate is unit-tested with mocked `create_message` + a fake credential store; the master switch + §4.5 dispatch are the upstream live legs verified separately).

## P6b is complete

§1a/§1b (drift) → §2 (paper variant + comparison + UI) → §3 (promotion gate + promote/cooldown/lockout) → §4 (Mode-B paper eval harness) → §4.5 (live auto-dispatch, ADR 0015) → §5 (LLM-driven live opt-in). The four Direction-v0.2 capabilities ADR 0006 v2 + ADR 0007 committed are shipped. **Next:** the cross-session live verification still pending (§1b.12 → `p6-session1-complete`, the §2-variant live smoke, and now an end-to-end live opt-in run) on a non-Norton + credentialed stack; then **P7 (NL → Python authoring)**.
