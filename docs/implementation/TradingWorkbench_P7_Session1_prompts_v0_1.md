# Trading Workbench — P7 §1: System Prompts for Strategy Generation

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-05 |
| Phase | P7 — NL → Python strategy authoring |
| Session | §1 of 8 (P7a foundation; serves both P7a generation and P7b refinement) |
| Predecessor | `p6b-session5-llm-optin-complete` (P6b complete) |
| Successor | `TradingWorkbench_P7_Session2_*` (the `strategy_authoring` generation service — the Anthropic call) |
| Direction | `TradingWorkbench_P7_Direction_v0.1.md` (2026-05-31) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | The version-controlled system prompts + the structured output schema + render helpers that drive NL→Python strategy generation. No Anthropic call (that's §2). |
| Estimated wall time | 3–4 hours |
| Tag on completion | `p7-session1-prompts-complete` |
| Out of scope | See §"What this session does NOT do" |

---

## Why this session exists

P7 turns a plain-English description into a complete Python strategy file. The quality, safety, and human-readability of that generated code is determined almost entirely by the **system prompts** — they tell the model the platform's `Strategy` interface, the exact indicator vocabulary, the human-readable-code requirement (Decision 1), and the structured output contract. §1 builds those prompt assets and freezes them under a version identifier so a future audit can reconstruct *which prompt produced which code*. Nothing in §1 calls the LLM or touches the order path; it is pure, reviewable prompt content + a small render/schema layer that §2 consumes.

Getting the prompts right up front (all three variants — generation, revision, debug-after-failure) means §2–§8 wire plumbing around a stable contract rather than re-litigating prompt design mid-phase.

## Decisions settled for §1 (owner, 2026-06-05)

- **Unsupported indicators (Direction Q1):** the prompt instructs the model to use **only** the supported indicator library (it may *compose* them — crossovers, thresholds, bands), and when a description needs an unsupported indicator it **does not implement it inline** — it explains the limitation and substitutes the closest supported indicator, recording that in the assumptions. Generated code only ever uses reviewed, tested indicators.
- **Prompt storage:** versioned **string constants in `app/services/strategy_authoring/prompts.py`** (matching the `morning_brief` / `eval_harness` `_GATE_SYSTEM` pattern), each carrying an explicit version tag (`GENERATION_PROMPT_VERSION = "v1"`) that §2 records in the generation audit. Git-reviewed in PRs; not runtime-mutable.
- **Output contract:** **structured output via Anthropic tool-use** — the model is forced to emit `StrategyOutput = {code: str, assumptions: list[str], explanation: str}`. §1 defines the tool/schema; §2 invokes it. (Code-in-JSON fragility for long files is mitigated by the human-readable ≤~150-line requirement and is handled at parse time in §2.)
- **Model (Decision 6):** **Sonnet** (`claude-sonnet-4-6`) is the generation/refinement default — not Haiku (code-gen is too high-stakes to optimize for cost). Opus is a future explicit-user-request path, out of §1.

## What this session ships

1. `app/services/strategy_authoring/__init__.py` — package.
2. `app/services/strategy_authoring/prompts.py`:
   - `GENERATION_PROMPT_VERSION = "v1"` and `GENERATION_MODEL = "claude-sonnet-4-6"`.
   - `STRATEGY_OUTPUT_TOOL` — the tool-use schema for `{code, assumptions[], explanation}`.
   - Shared building blocks: `INTERFACE_REFERENCE` (the `Strategy` contract the generated class must satisfy) and `INDICATOR_VOCABULARY` (the exact supported keys + the unsupported-indicator policy), assembled from the live source so they can't drift.
   - `GENERATION_SYSTEM`, `REVISION_SYSTEM`, `DEBUG_SYSTEM` — the three prompt variants.
   - Render helpers: `build_generation_user_message(description)`, `build_revision_user_message(prior_code, request)`, `build_debug_user_message(prior_code, error)`.
3. Tests asserting the prompts are well-formed and self-consistent (see §Tests).

## Detailed work

### §1.1 — The output schema (`STRATEGY_OUTPUT_TOOL`)

```python
STRATEGY_OUTPUT_TOOL = {
    "name": "emit_strategy",
    "description": "Return the generated trading strategy.",
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "The complete Python strategy file."},
            "assumptions": {
                "type": "array", "items": {"type": "string"},
                "description": "Each default/choice the AI made that the trader didn't specify.",
            },
            "explanation": {
                "type": "string",
                "description": "A plain-English summary of what the strategy does.",
            },
        },
        "required": ["code", "assumptions", "explanation"],
    },
}
```

### §1.2 — The shared contract blocks (drift-proof)

- `INDICATOR_VOCABULARY` is built from `app.indicators.computer`'s `INDICATOR_NAMES` (single source of truth) so the prompt's indicator list can never drift from what the engine actually computes. It names the single-series keys (`SMA20/50/200`, `EMA9/20/21/50`, `RSI14`, `ATR14`, `VWAP`, `RELVOL20`) and the multi-output ones (`MACD` → `macd`/`signal`/`hist`; `BB` → `bb_lower`/`bb_mid`/`bb_upper`), plus the **unsupported-indicator policy**.
- `INTERFACE_REFERENCE` states the `Strategy` contract verbatim from the platform: subclass `Strategy` from `app.strategies`; set `name`, `version`, `symbols`, `schedule`, `default_params`, and a typed `params_schema` (kept in sync with `default_params` — the documented "schema/code drift" hazard); override `on_bar` (and `on_fill`/`on_init` as needed); read indicators via `self.ctx.get_indicators(symbol, names=[...], timeframe=...)`, positions via `self.ctx.get_position_for(symbol)`, and submit via `self.ctx.submit_order(OrderRequest(... user_id=0, account_id=0, source_id=None ...))` (the context stamps ids). **Strategy-isolation rules are stated as hard constraints in the prompt** (no broker imports, no network/file I/O, no `anthropic`) so generated code passes `check_strategy_isolation.sh` by construction.

### §1.3 — `GENERATION_SYSTEM`

Encodes: the role (emit one complete, **deterministic** strategy file via `emit_strategy`); `INTERFACE_REFERENCE`; `INDICATOR_VOCABULARY`; **Decision 1 human-readability** (descriptive names, top docstring, inline comments for non-obvious logic, ≤~150 lines, verbose over clever); **no clarifying questions** (P7a single-shot — document assumptions instead, Direction §59); and the isolation constraints. Every default the model picks (indicator periods, thresholds, sizing, exits) goes in `assumptions`.

### §1.4 — `REVISION_SYSTEM` + `DEBUG_SYSTEM`

- `REVISION_SYSTEM` (P7b): given the prior code + a change request, return the **complete revised file** (not a diff) via `emit_strategy`, preserving everything not asked to change; may ask a clarifying question *in the explanation* if the request is ambiguous (Direction §59).
- `DEBUG_SYSTEM`: given the prior code + the failure (syntax error / runtime exception / zero-trades backtest), return a corrected complete file, with the fix described in `explanation`.

### §1.5 — Render helpers

Thin functions that wrap the user-supplied text into the `messages` user-turn content for §2 (e.g. `build_generation_user_message(description) -> str`). They do **not** call Anthropic; they just assemble the user message so §2's call site stays declarative.

## Tests (`tests/services/test_strategy_authoring_prompts.py`)

- `GENERATION_PROMPT_VERSION` is set; `GENERATION_MODEL` is the Sonnet id (not Haiku/Opus).
- `STRATEGY_OUTPUT_TOOL` is a structurally valid tool schema with the three required properties.
- `INDICATOR_VOCABULARY` contains **every** key in `app.indicators.computer.INDICATOR_NAMES` (drift guard — a new indicator added to the engine without updating the prompt fails this test).
- `GENERATION_SYSTEM` references the `Strategy` interface essentials (`on_bar`, `get_indicators`, `submit_order`) and states the isolation constraints + the unsupported-indicator policy + the human-readability requirement.
- The render helpers inject the supplied description / request / error verbatim.
- All three prompt constants are non-empty and mention `emit_strategy`.

## What this session does NOT do

- **No Anthropic call / no generation flow** — that's §2 (`strategy_authoring` service).
- **No backtest, no parsing of model output, no `strategies_user/` file writes** — §2/§3.
- **No DB schema, no migration, no `strategies` fields, no `strategy_revisions` table** — those land in §2 (authoring fields) / §5 (revisions).
- **No UI** — §4.
- **No order-path / risk-engine / new CI invariant** — P7-generated code is deterministic at runtime; existing invariants (esp. `check_strategy_isolation.sh`) cover it, and the prompt is written to satisfy them by construction.

## Notes & gotchas

1. **Drift guard is the load-bearing test.** The whole point of §1 is a stable, accurate contract. The `INDICATOR_NAMES` ⊆ prompt assertion ensures the prompt and the engine never silently diverge (the same class of bug as the CLAUDE.md "schema/code drift").
2. **The prompt must forbid inventing indicators** (Q1 decision) — composing existing ones is fine; implementing new indicator math inline is not. The test checks the policy text is present.
3. **Version the prompt, log the version.** §2 must record `GENERATION_PROMPT_VERSION` in the generation audit; §1 only defines the constant.
4. **Sonnet, not Haiku** — Decision 6. The model constant lives here so §2 imports it rather than hardcoding.
5. **Isolation by construction** — the generated code will live under `strategies_user/` and be loaded by `StrategyLoader`; the prompt states the isolation rules so the output passes `check_strategy_isolation.sh` without a post-hoc filter (a real validation pass is §2/§3, but the prompt is the first line of defense).
