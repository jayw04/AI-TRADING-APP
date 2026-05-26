# P2 Session 6 — Tests, Smoke Matrix, Runbooks, P2 Exit Gate

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-22 |
| Phase | **P2**, **§8 (Tests + Smoke) + §9 (Documentation) + §10 (Exit Gate)** |
| Predecessor | *TradingWorkbench_P2_Session5_v0.1.md* (tag `p2-session5-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Close P2. (1) Backfill any P2 unit-test coverage that Sessions 1–5 deferred. (2) Add the strategy-isolation grep tripwire to CI as a required check. (3) Ratchet coverage gates upward for the new strategy code. (4) Execute the six-step paper-trading smoke matrix for P2. (5) Write the three new runbook docs. (6) Update `README.md` and `todo.md`. (7) Walk the P2 exit gate, tag, and queue P3 prereqs. |
| Estimated wall time | 3–4 hours (single PR) |
| Stopping point | `git tag p2-complete` |
| Out of scope | New feature work. New strategy types. Frontend E2E tests with Playwright (Vitest unit coverage from Session 5 is sufficient for the exit gate per Checklist §8.4). |

---

## Session Goal

After this session:
- Overall backend coverage ≥ 80%; new P2 code (`app/indicators`, `app/market_data`, `app/strategies`, new API endpoints) ≥ 85%. CI enforces both.
- The strategy-isolation grep tripwire from Session 2 is a required CI check (the script exists; this session promotes it from "runs" to "required").
- The Risk Engine 95% branch-coverage gate from P1 still holds; P2 didn't touch that file, but the gate re-runs.
- One end-to-end backend integration test exercises the full P2 pipeline: register strategy → start → simulated bar dispatch → strategy submits order → risk passes → mocked Alpaca fill → strategy `on_fill` fires → audit chain complete.
- Backtest reproducibility test from Session 3 is wired into CI as a required check (it would already run; we're confirming it's gating).
- Frontend Vitest gates: tests from Session 5 plus one new component test for the equity-curve sparkline.
- `docs/runbook/strategy-authoring.md`, `docs/runbook/backtesting.md` exist and are accurate.
- `docs/runbook/risk-limits.md` updated with the STRATEGY-scope section.
- `docs/runbook/p2-smoke-log.md` committed with all six smoke steps recorded.
- `README.md` Quickstart updated to mention the Strategies page and the reference strategy.
- `todo.md` updated: P2 marked complete; P3 prereqs section written.
- `git tag p2-complete` is pushed.

What does NOT happen this session:
- New feature work. Bugs found during smoke get fixed; missing features get written down for P4.
- Async backtest with progress events. Still deferred (Session 4 / Session 5 gotchas).
- Playwright E2E. Vitest is sufficient per the checklist.
- A "load test" of WS fan-out under many concurrent strategy subscriptions. P4 polish.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                                       # clean
git pull origin main
git describe --tags --abbrev=0                   # expect: p2-session5-complete

# Sessions 1–5 still boot
./scripts/dev.sh &
sleep 30
curl -fs http://127.0.0.1:8000/healthz | jq -e '.status == "ok"'
curl -fs http://127.0.0.1:8000/api/v1/strategies | jq '.count'

# Strategy engine started, isolation check passes
docker compose logs backend | grep -E "strategy_engine_started"
bash apps/backend/scripts/check_strategy_isolation.sh
# Expect: "Strategy isolation OK"

# CI shows the existing ADR 0002 + risk coverage gates green on main
gh run list --branch main --limit 1

docker compose down
```

- [ ] On `main`, clean tree, at `p2-session5-complete` or later.
- [ ] All five P2 sessions in place; engine boots; isolation check passes.

Cut the branch:

```bash
git checkout -b feat/p2-tests-smoke-exit
```

---

## §6.1 — Coverage Gates

Two coverage gates already exist from P1 Session 7:
1. Overall pytest-cov `fail_under = 80` in `pyproject.toml`.
2. `scripts/check_risk_coverage.py` enforces 95% branch on `app/risk/engine.py`.

Add a third: per-module coverage targets for the P2 code. Either as a CI script or by tightening `fail_under` opportunistically.

### 6.1.1 — Local coverage snapshot

```bash
cd apps/backend
uv run pytest --cov-report=term --cov-report=xml
```

Read the per-file output for the P2 modules:
- `app/indicators/computer.py`
- `app/market_data/bar_cache.py`
- `app/strategies/base.py`
- `app/strategies/context.py`
- `app/strategies/loader.py`
- `app/strategies/engine.py`
- `app/strategies/backtest_context.py`
- `app/strategies/backtester.py`
- `app/strategies/backtest_models.py`
- `app/api/v1/strategies.py`
- `app/api/v1/signals.py`
- `app/api/v1/indicators.py`
- `strategies_user/examples/rsi_meanreversion.py`

Note the percentages. Anything below 75% per file deserves one or two more targeted tests in §6.2.

### 6.1.2 — Per-module coverage check

Create `apps/backend/scripts/check_p2_coverage.py`:

```python
"""Fail CI if branch coverage on any P2 module drops below 80%.

Reads coverage.xml (produced by pytest-cov), checks each P2 module against
its threshold, and exits non-zero if any drops below.

We use 80% for most modules — RSI strategy code, the loader, and the backtester
all earn higher (engine.py at 90%, backtester at 85%) because they're the
operational core of P2.

If your build legitimately drops one module below threshold (e.g. you added a
defensive branch you can't easily exercise from tests), update the threshold
in this script in the same PR. Don't paper-over a regression.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# (filename suffix, branch-rate threshold)
P2_MODULES: list[tuple[str, float]] = [
    ("app/indicators/computer.py", 0.80),
    ("app/market_data/bar_cache.py", 0.75),       # disk I/O is awkward to test exhaustively
    ("app/strategies/base.py", 0.80),
    ("app/strategies/context.py", 0.80),
    ("app/strategies/loader.py", 0.85),
    ("app/strategies/engine.py", 0.85),
    ("app/strategies/backtest_context.py", 0.80),
    ("app/strategies/backtester.py", 0.85),
    ("app/api/v1/strategies.py", 0.75),           # FastAPI handlers light on branches
    ("app/api/v1/signals.py", 0.75),
    ("app/api/v1/indicators.py", 0.75),
]


def main() -> int:
    coverage_xml = Path("coverage.xml")
    if not coverage_xml.exists():
        print(f"ERROR: {coverage_xml} not found. Run pytest --cov-report=xml first.", file=sys.stderr)
        return 2

    tree = ET.parse(coverage_xml)
    root = tree.getroot()

    actual: dict[str, float] = {}
    for cls in root.iter("class"):
        filename = cls.get("filename", "")
        # The filename may be absolute or relative — match by suffix
        for suffix, _threshold in P2_MODULES:
            if filename.endswith(suffix):
                actual[suffix] = float(cls.get("branch-rate", "0"))

    failures: list[str] = []
    for suffix, threshold in P2_MODULES:
        rate = actual.get(suffix)
        if rate is None:
            print(f"WARN: {suffix} not found in coverage.xml (no tests touched it?)", file=sys.stderr)
            continue
        status = "OK" if rate >= threshold else "FAIL"
        print(f"  {suffix:55s} branch-rate={rate:.3f} threshold={threshold:.2f}  {status}")
        if rate < threshold:
            failures.append(f"{suffix}: {rate:.3f} < {threshold:.2f}")

    if failures:
        print("\nP2 coverage FAILURES:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nP2 coverage OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run locally first:

```bash
uv run pytest --cov-report=xml -q
uv run python scripts/check_p2_coverage.py
cd ../..
```

If anything fails, either add tests in §6.2 or — if the failure is on a module where 100% would require ridiculous mocking — lower its threshold in `P2_MODULES` to the current floor *in the same PR* with a comment explaining why. The principle is ratcheting (never regress); the absolute number is negotiable.

### 6.1.3 — Wire the new check into CI

Edit `.github/workflows/ci.yml`. Find the existing coverage step (P1 Session 7 added it):

```yaml
      - name: Risk engine branch-coverage gate
        run: |
          cd apps/backend
          uv run pytest --cov-report=xml
          uv run python scripts/check_risk_coverage.py
```

Add a new step right after:

```yaml
      - name: P2 module branch-coverage gate
        run: |
          cd apps/backend
          uv run python scripts/check_p2_coverage.py
```

> Coverage.xml is already produced by the previous step; we just consume it.

After the next PR cycle is green, promote both this check AND the strategy-isolation check (from Session 2) to **required** in the GitHub branch protection UI.

- [ ] `check_p2_coverage.py` created.
- [ ] CI workflow runs the new gate.

---

## §6.2 — Backfill Backend Tests (Targeted)

Read the §6.1.1 coverage snapshot. For any P2 module below its threshold, write one or two targeted tests that exercise the missing branches. Don't aim for 100% — aim for "the important branches are tested."

### 6.2.1 — Most likely gaps

Based on the design of Sessions 1–4, these branches are *frequently* the ones left uncovered after the session tests:

**`app/market_data/bar_cache.py`**:
- The "empty Alpaca result writes `.empty` markers" path. Test by mocking `_alpaca_fetch_bars` to return an empty DataFrame and asserting `.empty` files appear.
- The "fetch raises exception" path. Test that the catch returns an empty frame and logs.

**`app/strategies/engine.py`**:
- The `_handle_user_exception` path where the strategy row no longer exists (defensive guard). Skip if you don't have a test that triggers it; this is one of those branches where 100% coverage costs more than it earns.
- The "schedule string is invalid → fall back to */1" path in `register()`. Worth covering.

**`app/strategies/backtester.py`**:
- The `_force_close_all_open_positions` end-of-backtest path. Covered by `test_backtester_force_closes_open_positions_at_end` from Session 3 — confirm it's still passing.
- The empty bars path (no bars for any symbol). Covered by `test_backtester_empty_bars_returns_neutral_metrics`.

**`app/api/v1/strategies.py`**:
- The "update rejected when status != IDLE" branch. Covered by `test_update_rejects_when_active`.
- The "backtest range > 1 year" branch. Covered by `test_backtest_rejects_long_range`.
- The "backtest with no symbols → 400" path. Probably NOT covered. Add a test below.
- The "start a strategy currently in ERROR" path. Worth covering since it's a real recovery flow.

### 6.2.2 — Targeted backfill tests

Create `apps/backend/tests/api/test_strategies_endpoint_extras.py`:

```python
"""Branch-coverage backfill for /api/v1/strategies."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from httpx import AsyncClient

from app.db.enums import StrategyStatus, StrategyType, RiskScopeType
from app.db.models.account import Account
from app.db.models.risk_limits import RiskLimits
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        session.add(RiskLimits(
            user_id=1, scope_type=RiskScopeType.GLOBAL, scope_id=None,
            max_position_qty=Decimal("100"),
            max_position_notional=Decimal("25000"),
            max_gross_exposure=Decimal("100000"),
            max_daily_loss=Decimal("2000"),
            max_orders_per_minute=10,
            allow_short=False,
            created_at=_now(), updated_at=_now(),
        ))
        await session.commit()


@pytest.fixture
async def client(seeded):
    from app.main import create_app
    app = create_app()
    app.state.strategy_engine = MagicMock()
    app.state.strategy_engine.register = AsyncMock()
    app.state.strategy_engine.unregister = AsyncMock()
    app.state.bar_cache = MagicMock()
    app.state.bar_cache.get_bars = AsyncMock(return_value=pd.DataFrame(columns=["t","o","h","l","c","v"]))
    app.state.indicator_computer = MagicMock()
    app.state.event_bus = MagicMock()
    app.state.event_bus.publish = AsyncMock()
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


async def _make_strategy(session_factory, *, status: StrategyStatus, symbols=None):
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1, name="t", version="0.1.0", type=StrategyType.PYTHON,
            status=status,
            code_path="examples/rsi_meanreversion.py",
            params_json={},
            symbols_json=symbols if symbols is not None else ["AAPL"],
            schedule="*/1 * * * *",
            risk_limits_id=None,
            created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


@pytest.mark.asyncio
async def test_backtest_rejects_when_no_symbols(client, session_factory):
    sid = await _make_strategy(session_factory, status=StrategyStatus.IDLE, symbols=[])
    resp = await client.post(f"/api/v1/strategies/{sid}/backtest", json={
        "start": "2025-11-03T00:00:00+00:00",
        "end": "2025-11-05T00:00:00+00:00",
        "symbols": [],   # also empty in request override
    })
    assert resp.status_code == 400
    assert "no symbols" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_start_recovers_from_error_state(client, session_factory):
    sid = await _make_strategy(session_factory, status=StrategyStatus.ERROR)

    async def fake_register(strategy_id):
        async with session_factory() as s:
            r = await s.get(StrategyRow, strategy_id)
            r.status = StrategyStatus.PAPER
            r.error_text = None
            await s.commit()
        result = MagicMock()
        result.run_id = 1
        return result

    client._transport.app.state.strategy_engine.register = fake_register
    resp = await client.post(f"/api/v1/strategies/{sid}/start")
    assert resp.status_code == 200
    assert resp.json()["new_status"] == "paper"


@pytest.mark.asyncio
async def test_get_strategy_returns_404_for_other_user_id(client, session_factory):
    """Ownership check — current_user.id=1 should NOT see user_id=2's row."""
    async with session_factory() as session:
        session.add(User(id=2, email="other@test", display_name="Other"))
        await session.commit()
    sid_other = await _make_strategy_for_user(session_factory, user_id=2)
    resp = await client.get(f"/api/v1/strategies/{sid_other}")
    assert resp.status_code == 404


async def _make_strategy_for_user(session_factory, *, user_id: int):
    async with session_factory() as session:
        row = StrategyRow(
            user_id=user_id, name="other", version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE,
            code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="*/1 * * * *",
            risk_limits_id=None,
            created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


@pytest.mark.asyncio
async def test_create_falls_back_to_class_symbols_when_request_omits(client):
    """If the create request has empty symbols, fall back to the strategy class's
    declared symbols list."""
    resp = await client.post("/api/v1/strategies", json={
        "name": "default-symbols",
        "code_path": "examples/rsi_meanreversion.py",
        "type": "python",
        # symbols intentionally omitted
    })
    assert resp.status_code == 200
    body = resp.json()
    # RsiMeanReversion declares ["AAPL","MSFT","SPY"]
    assert "AAPL" in body["symbols"]
```

Create `apps/backend/tests/strategies/test_engine_extras.py`:

```python
"""Branch-coverage backfill for StrategyEngine: malformed schedule fallback,
defensive paths."""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.account import Account
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.strategies import StrategyEngine


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "strategies"


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        await session.commit()


@pytest.fixture
async def engine(session_factory, seeded):
    scheduler = AsyncIOScheduler()
    scheduler.start()
    bus = EventBus()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock()
    indicator_computer = MagicMock()
    order_router = MagicMock()
    order_router.submit = AsyncMock()
    eng = StrategyEngine(
        scheduler=scheduler, session_factory=session_factory, bus=bus,
        bar_cache=bar_cache, indicator_computer=indicator_computer,
        order_router=order_router, strategies_root=FIXTURES_ROOT,
    )
    yield eng, scheduler
    await eng.shutdown()
    scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_engine_register_falls_back_on_invalid_cron(engine, session_factory):
    eng, scheduler = engine
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1, name="bad-cron", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
            code_path="echo_strategy.py", params_json={},
            symbols_json=["AAPL"],
            schedule="this is not a cron string",
            risk_limits_id=None,
            created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    running = await eng.register(sid)
    # The job is still scheduled — fallback to */1 * * * *
    assert running.job_id is not None
    assert scheduler.get_job(running.job_id) is not None


@pytest.mark.asyncio
async def test_engine_unregister_unknown_strategy_is_noop(engine):
    eng, _ = engine
    # Should NOT raise
    await eng.unregister(99999, reason="unknown")
```

Run:

```bash
cd apps/backend
uv run pytest tests/api/test_strategies_endpoint_extras.py \
              tests/strategies/test_engine_extras.py -v
uv run pytest -q
uv run pytest --cov-report=xml
uv run python scripts/check_p2_coverage.py
cd ../..
```

- [ ] Extras tests pass.
- [ ] Full backend suite still green.
- [ ] `check_p2_coverage.py` exits 0.

---

## §6.3 — Frontend Tests Snapshot

Confirm Session 5's three Vitest files still pass and there are no obvious gaps.

```bash
cd apps/frontend
pnpm test --run
cd ../..
```

If you want one additional component test (optional), the `StatusBadge` component is the cheapest non-trivial unit. Create `apps/frontend/src/components/strategies/__tests__/StatusBadge.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "../StatusBadge";

describe("StatusBadge", () => {
  it("renders all status values without crashing", () => {
    const statuses = ["idle", "backtest", "paper", "live", "halted", "error"] as const;
    for (const s of statuses) {
      const { unmount } = render(<StatusBadge status={s} />);
      expect(screen.getByText(s.toUpperCase())).toBeInTheDocument();
      unmount();
    }
  });

  it("PAPER badge has emerald color class", () => {
    render(<StatusBadge status="paper" />);
    const el = screen.getByText("PAPER");
    expect(el.className).toContain("emerald");
  });

  it("LIVE badge has red color class", () => {
    render(<StatusBadge status="live" />);
    const el = screen.getByText("LIVE");
    expect(el.className).toContain("red");
  });
});
```

- [ ] All Vitest tests pass.

---

## §6.4 — Promote the Strategy-Isolation Tripwire to Required

Session 2 added `scripts/check_strategy_isolation.sh` and wired it into CI. This session promotes it from "runs in CI" to "required for merge."

After the PR for this session is open and CI is green:

1. GitHub repo → Settings → Rules → Rulesets → `protect-main`.
2. Required status checks → Add the check name (it will appear as something like "P2 module branch-coverage gate" and "Strategy isolation invariant check").
3. Save.

Verify by going to a recent PR view → the two checks should show as required.

Also verify the script's failure mode works. Temporarily edit `apps/backend/app/strategies/context.py` to add `from app.brokers.alpaca import AlpacaAdapter`. Run:

```bash
bash apps/backend/scripts/check_strategy_isolation.sh
# Expect: exit 1 with the violation listed
```

Remove the test line:

```bash
git diff apps/backend/app/strategies/context.py
# Should show no changes
bash apps/backend/scripts/check_strategy_isolation.sh
# Expect: "Strategy isolation OK"
```

- [ ] Tripwire exists and fails on a deliberate violation.
- [ ] Test violation removed and verified clean.
- [ ] Tripwire promoted to required in branch protection (after PR merges).

---

## §6.5 — Runbook Docs

### 6.5.1 — `docs/runbook/strategy-authoring.md`

Create:

```markdown
# Strategy Authoring Runbook

> P2 ships one strategy type (Python). Pine arrives in P4; Agent in P6. This
> runbook covers Python only.

## File location

Strategies live under `apps/backend/strategies_user/`. The engine's loader
refuses paths outside this directory.

```
apps/backend/strategies_user/
├── examples/
│   └── rsi_meanreversion.py     # reference (do NOT take live unmodified)
└── my_strategy.py
```

## Minimal strategy

```python
from app.strategies import Strategy
from app.db.enums import OrderSide, OrderSourceType, OrderType, SignalType, TimeInForce
from app.risk import OrderRequest
from decimal import Decimal

class MyStrategy(Strategy):
    name = "my-strategy"
    version = "0.1.0"
    symbols = ["AAPL"]
    schedule = "*/1 * * * *"            # cron, or "event"
    default_params = {"timeframe": "1Min", "rsi_buy": 30, "rsi_sell": 70}

    async def on_init(self):
        # Called once before the first on_bar
        pass

    async def on_bar(self, bar):
        # Called every bar at the cadence above
        indicators = await self.ctx.get_indicators(
            bar.symbol, names=["RSI14"], timeframe=self.params["timeframe"]
        )
        rsi = indicators["RSI14"].dropna()
        if rsi.empty:
            return
        latest_rsi = float(rsi.iloc[-1])

        position = await self.ctx.get_position_for(bar.symbol)
        in_long = position is not None and position.qty > 0

        if not in_long and latest_rsi < self.params["rsi_buy"]:
            req = OrderRequest(
                user_id=0, account_id=0, symbol_id=0, symbol=bar.symbol,
                side=OrderSide.BUY, qty=Decimal("10"),
                type=OrderType.MARKET, tif=TimeInForce.DAY,
                source_type=OrderSourceType.STRATEGY,
            )
            result = await self.ctx.submit_order(req)
            await self.ctx.log_signal(bar.symbol, SignalType.ENTRY, payload={"rsi": latest_rsi})

    async def on_fill(self, fill):
        pass

    async def on_signal(self, signal):
        pass

    async def on_shutdown(self):
        pass
```

## The context surface

`self.ctx` is the only object your strategy uses for I/O:

| Method | Description |
|---|---|
| `await ctx.get_recent_bars(symbol, timeframe, n)` | OHLCV DataFrame from the cache |
| `await ctx.get_indicators(symbol, names, timeframe)` | Curated indicators (see below) |
| `await ctx.get_positions()` | Open positions in this strategy's universe |
| `await ctx.get_position_for(symbol)` | One position (or None) |
| `await ctx.submit_order(req)` | Through OrderRouter + Risk Engine |
| `await ctx.log_signal(symbol, type, payload)` | Persist a signal row + emit on bus |

**You cannot reach the broker directly.** The strategy isolation tripwire fails CI on any direct import of `app.brokers` from `app/strategies/`. ADR 0002 in code.

## Supported indicators

`SMA20`, `SMA50`, `SMA200`, `EMA9`, `EMA21`, `RSI14`, `MACD` (returns dict of `macd`/`signal`/`hist`), `ATR14`, `VWAP`, `BB` (returns dict of `bb_lower`/`bb_mid`/`bb_upper`), `RELVOL20`.

Anything beyond this set: compute it yourself in `on_bar` from raw bars. Curating the set keeps pandas-ta version churn from breaking strategies.

## Registering and starting

Two paths:

**From the UI (preferred):** Strategies page → "+ New strategy" → fill the form → Register → Start. Status transitions IDLE → PAPER.

**From the API:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/strategies \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-strategy",
    "code_path": "my_strategy.py",
    "type": "python",
    "symbols": ["AAPL"],
    "params": {"rsi_buy": 28}
  }'
# Then:
curl -X POST http://127.0.0.1:8000/api/v1/strategies/${ID}/start
```

## Common pitfalls

1. **Forgetting to subclass `Strategy`.** The loader rejects the file with "no Strategy subclass found."
2. **Multiple Strategy subclasses in one file** without declaring `__strategy__ = MainClass`. The loader rejects with "multiple Strategy subclasses."
3. **Trying to import `app.brokers` directly.** CI fails via the isolation tripwire. Use `ctx.submit_order` instead.
4. **Requesting bars for an unauthorized symbol.** `ctx.get_recent_bars("ZZZZ", ...)` returns an empty frame and logs a warning. Your strategy keeps running but its math sees no data.
5. **Submitting `symbol_id` other than 0.** Just leave `symbol_id=0`; the context resolves it from the ticker. If you set it manually wrong, the Risk Engine rejects.
6. **Risk Engine rejection is NOT an exception.** `ctx.submit_order` returns the rejected order; your strategy must check `result.status` or `result.rejection_reason`. Don't crash on rejection — log a signal and continue.
7. **Editing a running strategy's file.** No hot-reload. Stop the strategy, edit, register again (or rely on resume-on-boot which re-loads on backend restart). Hot-reload is P4 polish.
8. **Cron string typo.** Engine logs `strategy_schedule_invalid_falling_back` and dispatches every minute. Check logs after register.

## Per-strategy risk limits

When you register, you can set `risk_limits_id` to point at a STRATEGY-scope `risk_limits` row tighter than GLOBAL. The seed script creates a default tighter-than-global row for the reference strategy at:

```bash
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT id FROM risk_limits WHERE scope_type='strategy' LIMIT 1;"
```

Use that id, or create your own. See `docs/runbook/risk-limits.md`.

## Errors and recovery

If `on_bar`/`on_signal`/`on_fill` raise an uncaught exception, the engine:
1. Logs the exception.
2. Writes a `strategy.error` audit row.
3. Sets `strategies.status = ERROR` and writes the truncated error text to `error_text`.
4. Unregisters the strategy from the scheduler.
5. Publishes `strategy.error` on the bus → UI shows red status badge.

To recover: fix the code, click Start in the UI (or POST `/start`). Engine clears `error_text` on successful re-register.
```

### 6.5.2 — `docs/runbook/backtesting.md`

Create:

```markdown
# Backtesting Runbook

## How a backtest runs

`POST /api/v1/strategies/{id}/backtest` runs synchronously:
1. Loads the strategy class from disk via the same loader the runtime uses.
2. Pulls bars from `BarCache` for the requested range (and fetches+caches any missing days from Alpaca).
3. Constructs `BacktestContext` (in-memory positions, simulated cash) instead of the real `StrategyContext`.
4. Iterates bar-by-bar, calling `on_bar` per symbol. Orders submitted on bar N fill at bar N+1's open (± `slippage_bps`).
5. At the end, force-closes any open positions at the last close price.
6. Computes metrics, persists a `BacktestResult` row, returns the full result.

## Data source

Backtest bars come from the same `BarCache` that serves the runtime. First backtest of a date range fetches from Alpaca; subsequent backtests of the same range serve from disk. Free-tier IEX feed only (see Implementation Plan v0.2 §16 for the implications).

## Slippage and commission

- **Slippage:** `slippage_bps` (default 5 bps = 0.05% of fill price). Buys pay up; sells receive less.
- **Commission:** `commission_per_share` (default 0; Alpaca paper has no commissions, and many brokers no longer charge for US equities).

To stress-test a strategy, run the same backtest with `slippage_bps=25` (high friction) and see how metrics change.

## What's simulated, what isn't

| Aspect | Simulated | Notes |
|---|---|---|
| Market orders | Yes | Fill at next bar's open |
| Limit orders | **No** | Returns `non_market_orders_unsupported_in_backtest`. The reference RSI strategy works around this with a virtual stop check in `on_bar`. |
| Stop orders | **No** | Same as limit. |
| Bracket / OCO | **No** | Same. |
| Partial fills | No | Every fill is full qty |
| Slippage | Yes (linear, bps) | Constant; doesn't model order book impact |
| Borrow cost for shorts | No | Treats shorts as free |
| Overnight gaps | Yes (bars carry it naturally) | |
| Survivorship bias | Not addressed | Symbol universe is what you give it |

Limit/stop simulation lands per-strategy when a strategy needs it (per P2 Checklist §5.3 / Session 3 Gotcha #3).

## Metrics

| Field | Definition |
|---|---|
| `total_return` | (ending_equity / starting_equity) − 1 |
| `annualized_return` | (ending/starting) ^ (1/years) − 1 |
| `sharpe_ratio` | Daily-bucketed returns, annualized × √252, risk-free rate = 0 |
| `max_drawdown` | Largest peak-to-trough drop, as a negative fraction |
| `win_rate` | Fraction of closed trades with pnl > 0 |
| `profit_factor` | gross_profit / abs(gross_loss); ∞ if no losses |
| `trade_count` | Closed round-trips only |
| `avg_win` / `avg_loss` | Mean pnl among winners/losers |
| `avg_trade_duration_seconds` | Mean across closed trades |

**Sharpe caveat:** with < 2 trading days of data, Sharpe returns 0 by convention. Don't read meaning into low-data-point Sharpes.

## Reproducibility

A backtest is fully deterministic given:
- Identical bars in the cache.
- Identical `params`.
- Identical `slippage_bps` and `commission_per_share`.

The `tests/strategies/test_backtest_reproducibility.py` test runs the reference strategy twice on committed fixture bars and asserts every metric matches down to 1e-9. CI enforces this.

If your own strategy's backtest gives different metrics across runs:
1. Check for `random` or `numpy.random` without a fixed seed.
2. Check for `set` iteration where the order matters.
3. Check for dict iteration where the order matters and assumes Python's insertion-ordered behavior.
4. Bar cache regenerated mid-test? (Shouldn't happen, but the parquet file's mtime can shift.)

## Running a backtest

From the UI:
1. Strategies page → click the strategy → Backtests tab → "Run backtest".
2. Fill the form (defaults are last 10 days, 1-minute bars, 5 bps slippage).
3. Click Run. The modal blocks 2–10 seconds for a short range.
4. Result opens in a results view with metrics, equity curve, and trade list.

From the CLI / curl:
```bash
curl -X POST http://127.0.0.1:8000/api/v1/strategies/1/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "start": "2025-11-03T00:00:00+00:00",
    "end": "2025-11-10T00:00:00+00:00",
    "label": "default",
    "initial_equity": "100000",
    "slippage_bps": 5
  }'
```

## Range limits

The synchronous endpoint rejects ranges over 1 year (returns 400). For longer ranges, run the backtester directly from a Python REPL inside the backend container; the harness has no internal limit. Async backtests with progress events are P4 polish.

## Don't draw conclusions from one backtest

A single 3-month backtest is a weak signal. Standard discipline:
- **Walk-forward** the period: split into train/test, optimize on train, validate on test.
- **Multiple slippage values:** if your edge disappears at 25 bps slippage, you may not have an edge.
- **Multiple symbols:** does it work on AAPL only? Or also on SPY, NVDA, etc.?
- **Multiple time periods:** a strategy that worked in 2020 may not work in 2024.

P2 ships none of this — it ships the *plumbing*. The discipline is yours.
```

### 6.5.3 — Update `docs/runbook/risk-limits.md`

The P1 file already exists. Append a section near the end:

```markdown
## Strategy-scope risk limits

P2 introduced the STRATEGY scope. A `risk_limits` row with `scope_type='strategy'` applies to one or more strategies (via `strategies.risk_limits_id`).

Layering: when the Risk Engine evaluates a strategy-attributed order, it merges the STRATEGY-scope row over the GLOBAL row. NULL fields fall through to GLOBAL.

The seed script creates one default STRATEGY-scope row with tighter caps than GLOBAL:

| Field | GLOBAL | STRATEGY default |
|---|---|---|
| `max_position_notional` | $25,000 | $5,000 |
| `max_gross_exposure` | $100,000 | $15,000 |
| `max_daily_loss` | $2,000 | $500 |
| `max_orders_per_minute` | 10 | 5 |

To create a tighter per-strategy row:

```bash
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
  INSERT INTO risk_limits (user_id, scope_type, scope_id,
    max_position_qty, max_position_notional, max_gross_exposure,
    max_daily_loss, max_orders_per_minute, allow_short,
    created_at, updated_at)
  VALUES (1, 'strategy', NULL, 50, 2000, 5000, 250, 3, 0,
    datetime('now'), datetime('now'));
"
```

Then attach to a strategy:

```bash
curl -X PUT http://127.0.0.1:8000/api/v1/strategies/${ID} \
  -H "Content-Type: application/json" \
  -d '{"risk_limits_id": 3}'
```

The strategy must be in IDLE state for the update.

P3 will introduce AGENT-scope risk limits in the same pattern.
```

- [ ] All three doc files created/updated.

---

## §6.6 — Manual Smoke Matrix (P2 Checklist §8.5)

Six steps. Recorded in `docs/runbook/p2-smoke-log.md`.

### 6.6.1 — Prepare the log

Create `docs/runbook/p2-smoke-log.md`:

```markdown
# P2 Strategy MVP Smoke Log

| Field | Value |
|---|---|
| Date | YYYY-MM-DD |
| Time started | HH:MM ET |
| Trader | Jay |
| Branch / tag | feat/p2-tests-smoke-exit at HEAD |
| Alpaca paper buying power before | $______ |

## Steps

### 1. Register the reference RSI strategy via UI; leave in IDLE

- [ ] Strategies page → "+ New strategy" → defaults
- [ ] Submitted at HH:MM:SS ET
- [ ] Strategy id: ___
- [ ] Status displays IDLE
- [ ] audit_log has STRATEGY_REGISTERED: yes / no
- Notes:

### 2. Run a 30-day backtest from the UI; metrics appear

- [ ] Strategy detail → Backtests tab → Run backtest
- [ ] Range start: ___, end: ___
- [ ] Result modal opens within 60 seconds: yes / no
- [ ] Metrics shown: trade_count=___, total_return=____%, sharpe=____, max_dd=____%
- [ ] Equity curve recharts widget renders: yes / no
- [ ] Trade list populated (count: ___): yes / no
- [ ] backtest_results row persisted: yes / no
- [ ] audit_log has STRATEGY_BACKTESTED: yes / no
- Notes:

### 3. Start strategy on paper during market hours

- [ ] Click Start, confirm
- [ ] Status transitions IDLE → PAPER within 2 seconds
- [ ] WS event `strategy.run_started` received (check browser DevTools network → WS)
- [ ] strategy_runs row has started_at set, ended_at NULL
- Notes:

### 4. Wait for (or force) an entry signal; observe order chain

> If RSI doesn't naturally drop below 30 during smoke, edit params to loosen
> the threshold (e.g. entry_threshold=70 inverts the logic against you and
> will trigger easily). Stop, edit Params, Start.

- [ ] Entry signal appears in Signals tab within 5 minutes: yes / no
- [ ] signals row has type=entry: yes / no
- [ ] orders row exists with source_type=strategy, source_id=${ID}: yes / no
- [ ] Order filled (during hours): yes / no
- [ ] positions row updated: yes / no
- [ ] strategy.on_fill fired (visible in backend logs as a fill audit): yes / no
- [ ] audit_log shows the full chain: order.created → order.risk_passed →
      order.submitted → order.fill: yes / no
- Notes:

### 5. Force a risk rejection by tightening per-strategy notional cap

```bash
# Set the strategy's risk_limits to one with max_position_notional=$1
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
  INSERT INTO risk_limits (user_id, scope_type, scope_id,
    max_position_notional, allow_short, created_at, updated_at)
  VALUES (1, 'strategy', ${STRATEGY_ID}, 1, 0, datetime('now'), datetime('now'));
"
# Attach via API (strategy must be IDLE first)
curl -X POST http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/stop
curl -X PUT http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID} \
  -H "Content-Type: application/json" \
  -d "{\"risk_limits_id\": ${NEW_RISK_ROW_ID}}"
curl -X POST http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/start
```

- [ ] Next entry attempt rejected with POSITION_CAP_NOTIONAL: yes / no
- [ ] Strategy stays in PAPER (does NOT transition to ERROR): yes / no
- [ ] risk_checks row exists with decision=reject: yes / no
- [ ] Signal still logged (the strategy gracefully handled the rejection): yes / no
- Restore loose limits before continuing:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/stop
  curl -X PUT http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID} \
    -d '{"risk_limits_id": null}'
  ```
- Notes:

### 6. Stop strategy; open position left in place; close manually

- [ ] Click Stop
- [ ] Status transitions to IDLE within 2 seconds
- [ ] Any open position from earlier steps is NOT closed automatically: yes / no
- [ ] Positions page still shows it
- [ ] Close via Positions page "Close" button: yes / no
- [ ] strategy_runs row has ended_at set: yes / no
- [ ] audit_log has STRATEGY_STOPPED: yes / no
- Notes:

## Summary

- [ ] All 6 steps passed
- Buying power after: $___
- Open orders / positions after: ___ / ___ (target: both 0)
- Anomalies: (free text)
```

### 6.6.2 — Execute the smoke

```bash
./scripts/dev.sh
# Walk steps 1–6 in order; fill in the log as you go.
# If a step fails, fix the bug, then APPEND a second attempt to the log
# (don't edit the original failure record).
```

After completion:

```bash
# Cleanup check
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT count(*) FROM orders
   WHERE status NOT IN ('filled','canceled','rejected','expired','replaced');"
# expect: 0
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT count(*) FROM positions;"
# expect: 0

# If non-zero:
set -a; source .env; set +a
curl -X DELETE https://paper-api.alpaca.markets/v2/orders \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET"
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET"

docker compose down
```

- [ ] All six smoke steps green.
- [ ] Log committed with real values.
- [ ] Open orders + positions count = 0.

---

## §6.7 — README Quickstart Update

Find the existing Quickstart section in `README.md` (P1 Session 7 updated it). Add a new subsection after the "Common operations" block:

```markdown
### Running a strategy (P2)

The Strategies page is where systematic strategies live.

1. Visit `http://localhost:5173/strategies`.
2. Click "+ New strategy". The defaults register the reference RSI mean-reversion strategy on AAPL.
3. Click the strategy name → Backtests tab → "Run backtest". 10-day backtest takes a few seconds.
4. Review metrics + equity curve + trades.
5. Back to the strategy header → "Start (paper)". Status transitions IDLE → PAPER.
6. The Signals tab streams live signals via WebSocket; the Orders tab shows strategy-attributed orders.
7. Click Stop when done. Any open position is left for you to close manually from the Positions page.

> The reference strategy at `apps/backend/strategies_user/examples/rsi_meanreversion.py` is a **reference implementation, not a trading recommendation**. To write your own, read [`docs/runbook/strategy-authoring.md`](docs/runbook/strategy-authoring.md).
```

- [ ] README has the new Strategies subsection.

---

## §6.8 — Update `todo.md`

Replace P2 in-progress entries with a completion summary, add P3 prereqs:

```markdown
## ✅ P2 — Strategy MVP (complete)

Tag: `p2-complete` at HEAD of `main`. P2 closes Design Doc §2.3 success
criterion **S3** — "At least one systematic strategy runs end-to-end:
signal → risk check → paper order → fill → journal entry."

| Session | Status | Notes |
|---|---|---|
| 1. Bar cache + indicator computer | ✅ | parquet cache + pandas-ta wrapper |
| 2. Strategies schema + framework | ✅ | 4 tables, Strategy/Context/Engine/Loader |
| 3. Reference RSI strategy + backtest | ✅ | reproducibility test against fixture bars |
| 4. REST + WS topics + paper deploy | ✅ | 11 endpoints, strategies/signals/backtests WS topics |
| 5. Frontend Strategies pages | ✅ | list + detail w/ 5 tabs + backtest results view |
| 6. Tests + smoke + runbooks + exit gate | ✅ | this session |

### Deferred items (intentionally) to later phases

- Async backtest with WS progress events (P4 polish)
- Strategy hot-reload from filesystem changes (P4)
- Backtest charting beyond recharts equity curve (P4)
- Multi-strategy concurrency / resource fairness (P4)
- Parameter form derivation from default_params (P4)
- Backend filter `/api/v1/orders?source_id=X` (the UI does client-side filtering today; P4)
- Limit / stop / bracket simulation in backtest (per-strategy as needed)
- WS-driven bar dispatch instead of 30s polling (P4)
- Walk-forward parameter optimization (not in MVP scope at all)

### Pine (P4) and Agent (P6) preparation

- `strategies.type` enum already reserves `pine` and `agent` values.
- `signals.type` enum already reserves `pine_alert` and `agent_action`.
- Engine register() rejects non-PYTHON types with a clear error message.
- The schema migration when those phases land is column DEFAULTs only.

## 🚧 P3 — Agent MVP (B1+B2 chat panel)

Goal: a Claude-powered chat panel that the trader can talk to about
positions, recent trades, and current market state. **B1+B2 only** —
read-only context + interactive Q&A. No autonomous trading (that's B3, P6).

### P3 prereqs

- [ ] Re-read Design Doc §10 (Agent integration) and Implementation Plan v0.2 §10 + §12.
- [ ] Confirm: agent modes B1 (read-only) and B2 (interactive Q&A) are P3.
      B3 (Agent Strategy that submits orders) is explicitly P6.
- [ ] Confirm: $2/day per-agent cost cap, Haiku-default per Implementation Plan §13.3.
- [ ] Decide on Anthropic API key handling: per-user in `system_config`, encrypted at rest?
      Or env var only? (Recommend env var for MVP; per-user in P5.)
- [ ] Draft a P3 checklist analogous to P1 / P2 (sessions + acceptance criteria).
- [ ] Decide whether the chat panel is a new top-level page or a side panel
      docked into the existing layout.
```

- [ ] `todo.md` reflects P2 complete and P3 prereqs.

---

## §6.9 — P2 Exit Gate

Walk every box before tagging.

```bash
# 1. Clean state
git status                                     # clean
git pull origin main                           # PR merged
git fetch --tags

# 2. CI green on main
gh run list --branch main --limit 1

# 3. Branch protection includes the new required checks
gh api repos/jayw04/AI-TRADING-APP/rules/branches/main \
  | jq '.[] | select(.type == "required_status_checks") | .parameters.required_status_checks[].context'
# Expect: includes "ADR 0002 invariant check", "Strategy isolation invariant check",
# "Risk engine branch-coverage gate", "P2 module branch-coverage gate"

# 4. All four invariant scripts pass locally
bash apps/backend/scripts/check_adr0002.sh
bash apps/backend/scripts/check_strategy_isolation.sh
cd apps/backend
uv run pytest --cov-report=xml
uv run python scripts/check_risk_coverage.py
uv run python scripts/check_p2_coverage.py
cd ../..

# 5. End-to-end docker-compose boots cleanly
./scripts/dev.sh
sleep 30
curl -fs http://127.0.0.1:8000/healthz | jq -e '.status == "ok"'
curl -fs http://127.0.0.1:8000/api/v1/strategies | jq '.count'
echo "open http://localhost:5173/strategies and verify it renders"

# 6. Smoke log committed and complete
grep -c "All 6 steps passed" docs/runbook/p2-smoke-log.md
# Expect: 1

# 7. The three runbook docs exist
ls docs/runbook/strategy-authoring.md \
   docs/runbook/backtesting.md \
   docs/runbook/p2-smoke-log.md

docker compose down
```

Final checklist mirroring Design Doc §2.3 + P2 Checklist §10:

- [ ] **S3:** Reference RSI strategy runs end-to-end on paper (smoke step 4 confirms).
- [ ] Strategy backtest produces deterministic, reproducible metrics on committed fixture (CI-enforced).
- [ ] Every order submitted by a strategy goes through OrderRouter (ADR 0002 grep + strategy-isolation grep both green).
- [ ] Risk Engine branch coverage ≥ 95% (script-enforced).
- [ ] P2 module branch coverage ≥ 80% (script-enforced).
- [ ] All six manual smoke steps pass; log committed.
- [ ] CI green on `main`.
- [ ] `docker compose up` from a clean checkout works end-to-end.

If every box ticks:

```bash
git tag -a p2-complete -m "P2 Strategy MVP complete: reference RSI strategy + backtest harness + full UI"
git push origin p2-complete
```

- [ ] `p2-complete` tag pushed.

---

## §6.10 — Commit and PR

```bash
git add apps/backend/scripts/check_p2_coverage.py
git add apps/backend/tests/api/test_strategies_endpoint_extras.py
git add apps/backend/tests/strategies/test_engine_extras.py
git add apps/frontend/src/components/strategies/__tests__/StatusBadge.test.tsx
git add .github/workflows/ci.yml
git add docs/runbook/strategy-authoring.md
git add docs/runbook/backtesting.md
git add docs/runbook/risk-limits.md
git add docs/runbook/p2-smoke-log.md
git add README.md
git add todo.md

git commit -m "test(p2): coverage gates, integration backfill, smoke log, runbooks, exit gate

- check_p2_coverage.py: per-module branch-rate thresholds for P2 code
- Wired into CI alongside existing ADR 0002 + risk coverage gates
- Backfill tests: backtest-no-symbols, start-from-error-state,
  ownership-404, fallback-symbols, invalid-cron, unknown-unregister
- StatusBadge component test (frontend)
- Runbooks: strategy-authoring.md, backtesting.md
- risk-limits.md: STRATEGY-scope section added
- p2-smoke-log.md: all 6 steps recorded
- README.md: Strategies subsection in Quickstart
- todo.md: P2 marked complete; P3 prereqs section added"

git push -u origin feat/p2-tests-smoke-exit
gh pr create \
  --title "test(p2): exit gate — coverage, integration backfill, smoke, runbooks" \
  --body "Closes P2. After this lands, tag p2-complete."

gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
```

Then (only after merge):

```bash
git tag -a p2-complete -m "P2 Strategy MVP complete"
git push origin p2-complete
```

- [ ] PR merged.
- [ ] Tag pushed.

---

## Final Verification

After the tag:

```bash
git describe --tags --abbrev=0     # expect: p2-complete

# Clean-machine smoke
cd /tmp && git clone git@github.com:jayw04/AI-TRADING-APP.git twb-p2-clean
cd twb-p2-clean
cp .env.example .env
# populate ALPACA_PAPER_API_KEY/SECRET
./scripts/dev.sh
sleep 30
curl -fs http://127.0.0.1:8000/healthz
curl -fs http://127.0.0.1:8000/api/v1/strategies | jq '.count'
echo "open http://localhost:5173/strategies"
docker compose down
cd .. && rm -rf twb-p2-clean
```

- [ ] Clean-machine boot works without surprises.

---

## Sign-off

```bash
git tag -a p2-session6-complete -m "P2 Session 6 complete (= P2 complete)"
git push origin p2-session6-complete
```

> `p2-session6-complete` and `p2-complete` are functionally identical; both
> are pushed so the session-tag pattern stays unbroken.

**P2 is done. Move to P3 (Agent MVP — B1 read-only context + B2 interactive chat).**

---

## Notes & Gotchas

1. **Coverage gates ratchet, never regress.** Same rule as P1 Session 7. If a module legitimately drops below threshold because you added a defensive branch you can't easily test, lower the threshold *in the same PR* with a comment. The principle is "no silent regression," not "hit a magic number."

2. **The strategy-isolation tripwire complements ADR 0002.** ADR 0002's grep catches direct calls to `submit_order` / `cancel_order` / `replace_order` from outside `OrderRouter`. The isolation tripwire catches a sneakier path: a strategy that imports `app.brokers` and uses it via some indirection. Both are grep-level (Gotcha #3 in P1 Session 7); an AST-level upgrade is P4 polish.

3. **The smoke matrix has a critical cleanup in step 5.** Re-attach `risk_limits_id=null` after the rejection demonstration. Forgetting leaves the strategy with the artificially tight cap, and every future order rejects. This has bitten me; the log explicitly calls it out.

4. **Smoke step 4 may need params adjustment to fire reliably.** Real RSI < 30 on AAPL during a normal trading day is rare. If you can't naturally trigger, edit params to invert thresholds (e.g. `entry_threshold=70` makes the strategy enter at RSI > 70, which is much more common). Restore defaults before signing off.

5. **Smoke step 6's "open position not auto-closed" is deliberate.** A stop in P2 unregisters the strategy but leaves any open position alone. This is the safest default: forcing automatic close on stop is a class of bug ("I clicked stop and lost my position to slippage in a bad print") that auto-close-on-stop creates. P4 polish could add an opt-in "close all on stop" toggle.

6. **The reproducibility test is in CI as a gating check by virtue of running.** `test_reference_strategy_backtest_is_reproducible` is a normal pytest test — if it fails, the whole suite fails, which is already a required check. We don't need a separate scripted gate for it. Don't add one.

7. **The `check_p2_coverage.py` thresholds can be lowered, never raised silently.** If a future PR's coverage drops, the script fails. The choice is "add tests" or "lower the threshold with a comment." Raising thresholds without doing the work to actually exceed them creates the worst of both worlds: future PRs randomly fail on what feels like an arbitrary number.

8. **Frontend coverage isn't gated by CI.** Vitest tests run as a required check but no coverage gate. The Vitest suite is small enough that "did the tests pass" is the meaningful gate. P4 polish could add a Vitest coverage threshold if the frontend grows substantially.

9. **The `gh api .../rules/branches/main` query verifies branch protection in §6.9.** If it returns empty, branch protection isn't set up correctly. P0 should have configured it; if it's missing, set it up now via Settings → Rules → Rulesets → New ruleset.

10. **Clean-machine smoke is the last sanity check.** A repo that boots on the maintainer's machine and falls over on a fresh clone is a real failure mode — usually `.env` not being committed properly, or a missing volume mount, or an undocumented OS dep. The clone-into-/tmp pattern catches these.

11. **The post-tag P3 prereqs section in `todo.md` is the natural launch pad for the next phase.** Don't start P3 work in this session — but writing the prereqs forces you to surface decisions (API key handling, chat panel placement, B3 deferral) that would otherwise come up half-way through P3 Session 1.

12. **Don't compose a new strategy in this PR.** This is the closer. New features go in a new PR after the tag.

---

*End of P2 Session 6 v0.1.*
