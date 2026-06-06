# P7 Session 3 — Auto-backtest of generated code — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-06 |
| Phase | P7 — NL → Python strategy authoring (§3 of 8 — P7a) |
| Plan doc | `TradingWorkbench_P7_Session3_backtest_v0_1.md` |
| Predecessor | `p7-session2-generation-complete` |
| Tag | **`p7-session3-backtest-complete`** (`7a918a9` squash → moved to the §3 todo commit) |
| Shipped as | PR **#68** — branch `feat/p7-session3-backtest`; squash-merged `7a918a9` |
| Verdict | **GO.** Generated code is now safety-validated + backtested before it's presented. Full backend suite green; all 10 invariants + 3 coverage gates; no migration, no order path, no UI. |

## What shipped

- **`app/services/strategy_authoring/code_safety.py`** — `validate_generated_code(source)` / `validate_generated_code_tree(tree)` / `UnsafeCodeError`. An AST denylist that runs **before** any execution (the loader exec's module top-level code). Forbids imports of brokers/network/file-IO/subprocess/concurrency/native/LLM-SDKs, the builtin calls `eval`/`exec`/`compile`/`__import__`/`open`/`input`/`breakpoint`/`globals`/`locals`/`vars`, relative imports, and the sandbox-escape dunders (`__subclasses__`/`__globals__`/`__builtins__`/`__bases__`/`__mro__`/…). `getattr`/`setattr` deliberately allowed (strategies use `getattr(pos, "side", None)`).
- **`app/services/strategy_authoring/backtest.py`** — `backtest_generated_code(*, code, bar_cache, indicator_computer, now=None) → BacktestOutcome` (`ok` | `no_trades` | `syntax_error` | `unsafe_code` | `load_error` | `runtime_error` | `unavailable`). `ast.parse` (syntax) → AST gate (unsafe) → temp `.py` + `StrategyLoader` (load) → `Backtester(...).run` over the strategy's timeframe + `BACKTEST_WINDOW_DAYS = 183`. Never raises.
- **`POST /strategies/author`** now returns `{..., backtest: {status, metrics, trade_count, error}}`. A backtest failure is surfaced with the code, not raised; graceful `unavailable` when `app.state.bar_cache` isn't wired.

## Decisions settled (owner, 2026-06-06 — AskUserQuestion)

1. **Safety:** AST forbidden-import/call validator (pre-execution gate).
2. **Load:** temp `.py` + the existing `StrategyLoader` (the production load path).
3. **Window (Direction Q2):** the strategy's own timeframe over ~6 months.

## Notes

- **Order matters:** the AST gate runs before `StrategyLoader.load` (which exec's the module). A forbidden `import os; os.system(...)` at module scope would otherwise run on load.
- **Denylist, not allowlist** (owner pick) — favors not falsely rejecting valid strategies; the §1 prompt + the in-memory simulator are the other layers.
- One **static-scanner false positive** handled: the backtest test's generated-strategy *source strings* contain `self.ctx.submit_order(...)`, which the ADR 0002 grep flagged → added the test file to that invariant's allowlist (string literals, not call sites).

## Verification

- ~25 new §3 tests (validator rejects `os`/`socket`/`subprocess`/`app.brokers`/`requests`/`httpx`/`threading`/`importlib`/`eval`/`exec`/`open`/`__import__`/`globals`/`__subclasses__`/relative-import, accepts `getattr`; backtest `ok`/`no_trades`/`runtime_error`/`syntax_error`/`unsafe_code`/`unavailable`; endpoint carries the `backtest` key). Full backend suite **1015+ passed / 9 skipped / 0 failed**; ruff + mypy(186) clean.
- All 10 shell invariants (no-LLM confirms `strategy_authoring` un-allowlisted) + 3 coverage gates (risk 0.904 / P2 / P3). **No migration.**
- PR CI all green (Python-backend 5m18s). Merged on the owner's "merge on green."

## Next

**§4** — the "Author with AI" UI + the **save flow**: write the generated `.py` to `strategies_user/` → `POST /strategies` (the loader validates `code_path` before persisting) → set the new **`authoring_method`** field on `strategies` (enum `manual`/`nl_generation`/`nl_refinement`/`template`) — **the migration lands in §4.** That completes **P7a** (single-shot generation, independently shippable). The `DEBUG_SYSTEM` auto-retry-on-backtest-failure loop is deferred (§6/P7b). Then §5–8 = P7b refinement.
