# Trading Workbench — P7 §3: Auto-Backtest of Generated Code

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-06 |
| Phase | P7 — NL → Python strategy authoring (§3 of 8 — completes P7a's core) |
| Predecessor | `p7-session2-generation-complete` (§2 generation service) |
| Successor | `TradingWorkbench_P7_Session4_*` (the "Author with AI" UI + save flow) |
| Direction | `TradingWorkbench_P7_Direction_v0.1.md` (Decision 2) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Compile + **AST-safety-validate** + backtest the generated code, and return the metrics (or the failure) alongside it. Never present code without a backtest. |
| Estimated wall time | 3–5 hours |
| Tag on completion | `p7-session3-backtest-complete` |
| Out of scope | See §"What this session does NOT do" |

---

## Why this session exists

Direction Decision 2: the platform never says "here is your strategy" and leaves the trader to judge unproven code — every generation is backtested before it's presented. §3 adds that step to the `POST /strategies/author` flow: after §2 generates the code, §3 **safety-validates it (AST gate), loads it through the production loader, runs a backtest on cached bars, and returns the metrics** — or, on syntax/safety/runtime/zero-trade failure, surfaces the failure with the code.

This is the platform's first execution of **freshly-LLM-authored, unreviewed** Python. The shell isolation check only greps for `app.brokers`; it's insufficient. §3's AST validator is the real pre-execution gate.

## Decisions settled for §3 (owner, 2026-06-06)

- **Safety:** an **AST forbidden-import/call validator** runs **before** the code is compiled/executed — reject (don't run) anything importing or calling outside the strategy sandbox (brokers, network, file I/O, subprocess, LLM SDKs, `eval`/`exec`/`compile`/`__import__`/`open`, sandbox-escape dunders).
- **Load:** **temp `.py` file + the existing `StrategyLoader`** — write the source to a temp dir, load through the production path (identical to how a saved strategy loads in §4), run, delete.
- **Window (Direction Q2):** the strategy's **own declared timeframe** over a fixed **~6-month** window — responsive for the interactive loop; configurability is a later refinement.

## What this session ships

1. `app/services/strategy_authoring/code_safety.py` — `validate_generated_code(source)` / `UnsafeCodeError`.
2. `app/services/strategy_authoring/backtest.py` — `BacktestOutcome` + `backtest_generated_code(...)`.
3. `POST /strategies/author` now also runs the backtest and returns `{... , "backtest": <outcome>}`.
4. Tests.

## Detailed work

### §3.1 — The AST safety validator (`code_safety.py`)

Runs on the parsed AST **before** any execution:

```python
class UnsafeCodeError(Exception): ...

# Forbidden import module prefixes (m == p or m.startswith(p + ".")):
_FORBIDDEN_MODULES = ("app.brokers", "socket", "ssl", "requests", "httpx",
  "urllib", "aiohttp", "http", "ftplib", "smtplib", "subprocess", "os", "sys",
  "shutil", "pathlib", "glob", "pickle", "marshal", "importlib", "ctypes",
  "multiprocessing", "threading", "asyncio", "tempfile", "webbrowser",
  "anthropic", "openai", "builtins")
# Forbidden builtin calls: eval, exec, compile, __import__, open, input, breakpoint, globals, locals, vars
# Forbidden attribute access (sandbox-escape chain): __subclasses__, __globals__,
#   __builtins__, __bases__, __mro__, __import__

def validate_generated_code(source: str) -> None:
    """Raise SyntaxError (unparseable) or UnsafeCodeError (forbidden import/call/attr)."""
```

Allowed by omission: stdlib `datetime`/`decimal`/`typing`/`math`/`statistics`/`enum`/`dataclasses`/`collections`/`zoneinfo`/`__future__`, `pandas`/`numpy` (indicator series), and the strategy-facing `app.strategies` / `app.risk` / `app.db.enums` (the interface the prompt mandates). The validator is a **denylist of dangerous categories**, matching the owner's pick; the prompt is the first line of defense, this is the enforced gate.

### §3.2 — `backtest_generated_code`

`app/services/strategy_authoring/backtest.py`:

```python
@dataclass(frozen=True)
class BacktestOutcome:
    status: str   # ok | no_trades | syntax_error | unsafe_code | load_error | runtime_error | unavailable
    metrics: dict | None
    trade_count: int
    error: str | None

BACKTEST_WINDOW_DAYS = 183  # ~6 months

async def backtest_generated_code(*, code, bar_cache, indicator_computer, now=None) -> BacktestOutcome:
    # 0. bar_cache/indicator_computer missing (e.g. alpaca-startup disabled) → "unavailable".
    # 1. ast.parse → SyntaxError → "syntax_error".
    # 2. validate AST → UnsafeCodeError → "unsafe_code" (BEFORE any exec).
    # 3. write temp .py → StrategyLoader(tmp).load(...) → StrategyLoadError → "load_error".
    #    (loader.exec_module runs the code — only reached after the AST gate passes.)
    # 4. config: timeframe = cls.default_params["timeframe"] (default 1Min); window = now-183d..now;
    #    symbols = cls.symbols (no symbols → "load_error"); params = cls.default_params.
    # 5. Backtester(bar_cache, indicator_computer).run(cls, symbols, config) → Exception → "runtime_error".
    # 6. metrics.trade_count == 0 → "no_trades", else "ok"; metrics → dict (return/sharpe/max_dd/
    #    win_rate/profit_factor/trade_count/starting_equity/ending_equity).
```

The temp file lives only inside a `tempfile.TemporaryDirectory()`; the loaded class is in memory, so the file is gone after load. ADR 0002 / isolation stays intact — the backtest uses the in-memory `BacktestContext` simulator, never a broker.

### §3.3 — Endpoint wiring

`POST /strategies/author` (add `request: Request`): after `generate_strategy(...)`, run `backtest_generated_code(code=result.code, bar_cache=request.app.state.bar_cache, indicator_computer=request.app.state.indicator_computer)` (getattr-guarded → `unavailable` when not wired) and add `"backtest": {status, metrics, trade_count, error}` to the response. Generation already succeeded + was audited; a backtest failure does **not** fail the request — it's returned for the trader to see (Decision 2).

### §3.4 — Tests

- **`code_safety`**: rejects `import os` / `import socket` / `from app.brokers import x` / `subprocess` / `eval(...)` / `open(...)` / `().__class__.__subclasses__()`; accepts the reference-style strategy (datetime/decimal/typing/app.strategies/app.risk/app.db.enums).
- **`backtest_generated_code`**: a valid no-indicator strategy (buy bar 2 / sell bar 5) over canned bars (mocked `bar_cache.get_bars`, MagicMock `indicator_computer`) → `ok` + metrics with `trade_count > 0`; a syntax-error string → `syntax_error`; an unsafe string → `unsafe_code` (and the loader is never reached); a strategy that raises in `on_bar` → `runtime_error`; a do-nothing strategy → `no_trades`; `bar_cache=None` → `unavailable`.
- **endpoint**: `POST /strategies/author` response includes a `backtest` object (monkeypatch `backtest_generated_code` to a fixed outcome so the endpoint test asserts the wiring, not the harness).

## What this session does NOT do

- **No persistence / save** — still generate-and-return (with a backtest now). The save flow + `authoring_method` field + migration are §4.
- **No auto-debug-retry** — on a backtest failure §3 surfaces it with the code; the `DEBUG_SYSTEM` regenerate-on-failure loop is a later refinement (§6/P7b territory), noted not built.
- **No UI** — §4.
- **No new audit action** — the generation is already audited (§2); the backtest is derived + re-runnable, not separately audited.
- **No order-path / risk-engine / new CI invariant.**

## Notes & gotchas

1. **The AST gate runs before `exec_module`.** `StrategyLoader.load` executes the module's top-level code; the validator must pass first, or a forbidden `import os; os.system(...)` at module scope would run. Order is load-bearing.
2. **Denylist, not allowlist** (owner pick) — favors not falsely rejecting valid strategies; the prompt + the in-memory simulator are the other layers.
3. **Norton:** a real 6-month backtest needs cached/fetched bars (`BarCache → Alpaca`), blocked locally. Unit tests mock `bar_cache.get_bars` with a canned frame (the existing backtester-test pattern); the live backtest is verified on a non-Norton stack.
4. **`unavailable` is graceful** — when `app.state.bar_cache` isn't wired (alpaca startup disabled), the endpoint still returns the generated code with `backtest.status = "unavailable"` rather than erroring.
5. **Temp file under a `TemporaryDirectory`**, not `strategies_user/` — so the strategy file watcher / engine never sees a half-baked generated file.
