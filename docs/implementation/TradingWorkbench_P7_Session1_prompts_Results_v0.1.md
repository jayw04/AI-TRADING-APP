# P7 Session 1 — System prompts for strategy generation — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-05 |
| Phase | P7 — NL → Python strategy authoring (§1 of 8 — P7a foundation) |
| Plan doc | `TradingWorkbench_P7_Session1_prompts_v0_1.md` |
| Direction | `TradingWorkbench_P7_Direction_v0.1.md` |
| Predecessor | `p6b-session5-llm-optin-complete` (P6b complete) |
| Tag | **`p7-session1-prompts-complete`** (`5406d40` squash → moved to the §1 todo commit) |
| Shipped as | PR **#66** — branch `feat/p7-session1-prompts`; squash-merged `5406d40` |
| Verdict | **GO.** The version-controlled generation prompts + output schema. Pure prompt content + render/schema; no Anthropic call, no order path, no migration, no UI. Full backend suite green; all 10 invariants + 3 coverage gates. |

## What shipped

- **`app/services/strategy_authoring/prompts.py`** — three prompt variants (`GENERATION_SYSTEM`, `REVISION_SYSTEM`, `DEBUG_SYSTEM`), frozen under `GENERATION_PROMPT_VERSION = "v1"` (§2 records it in the generation audit). `GENERATION_MODEL = "claude-sonnet-4-6"` (Direction Decision 6). `STRATEGY_OUTPUT_TOOL` = the tool-use schema `{code, assumptions[], explanation}`. Render helpers (`build_generation_user_message` / `_revision_` / `_debug_`).
- **Drift-proof vocabulary** — `INDICATOR_VOCABULARY` built from `app.indicators.computer.CORE_INDICATORS`; a test asserts `CORE_INDICATORS ⊆ the prompt`. `INTERFACE_REFERENCE` states the `Strategy` contract + isolation rules so generated code passes `check_strategy_isolation` by construction.
- **`app/services/strategy_authoring/__init__.py`** — package.

## Decisions settled (owner, 2026-06-05 — AskUserQuestion)

1. **Unsupported indicators (Direction Q1):** use only the supported library, compose freely, never implement a new indicator inline — explain + substitute the closest supported one.
2. **Prompt storage:** versioned string constants in `prompts.py` (the `eval_harness` / `morning_brief` pattern); version audit-logged by §2.
3. **Output contract:** Anthropic tool-use structured output (`emit_strategy`).

## Two static-scanner false positives (handled)

1. **no-LLM invariant** flagged the literal `import anthropic` in the isolation-constraint text → reworded to "no LLM or Anthropic-SDK usage" (avoids the grep patterns; §1 makes no SDK call).
2. **ADR 0002 invariant test** flagged `self.ctx.submit_order(...)` in the embedded interface example → added `prompts.py` to that test's allowlist (prompt content, not a call site — same rationale as the already-allowlisted `rsi_meanreversion.py`).

## Verification

- Backend full suite green (8 new prompt tests incl. the indicator drift guard); ruff + mypy(182) clean.
- All 10 shell invariants + 3 coverage gates (risk 0.904 / P2 / P3) green. No migration, no order-path, no UI.
- PR CI all green (Python-backend 4m47s). Merged on the owner's "merge on green."

## Next

**P7 §2** — the `strategy_authoring` generation service: the Sonnet tool-use call (forcing `STRATEGY_OUTPUT_TOOL`), parsing `{code, assumptions, explanation}`, recording `GENERATION_PROMPT_VERSION` in the generation audit, and the `authoring_method` field on `strategies` (`manual` / `nl_generation` / `nl_refinement` / `template`). Then §3 (auto-backtest after generation) and §4 (the "Author with AI" UI) complete P7a. Open questions for those sessions: backtest window (Q2), cost surfacing (Q7), logic-bug mitigation (Q5).
