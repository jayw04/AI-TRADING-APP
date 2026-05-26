# P4 Item 5 — Backend `source_id` Filter on Orders

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-23 |
| Phase | **P4 — Polish & Extend**, Item §5 |
| Predecessor | *TradingWorkbench_P4_Item3_OpportunitiesPage_v0.1.md* (tag `p4-opportunities-page-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Add `source_type` and `source_id` query parameters to `GET /api/v1/orders`. Update the Strategy detail Orders tab to use them directly instead of pulling 500 orders and filtering client-side. Update P3's `list_recent_orders` MCP tool to accept and pass through the new filters. Single PR. |
| Estimated wall time | 1–2 hours |
| Stopping point | `git tag p4-order-source-filter-complete` |
| Out of scope | Index on `(source_type, source_id)`. The orders table is small enough that the existing index on `(user_id, created_at)` plus a sequential scan is fast. Add the composite index in P5 when concurrent users hit it. Backfill or denormalize anything — the existing column is already there. |

---

## Session Goal

After this session:
- `GET /api/v1/orders?source_type=strategy&source_id=42` returns only orders attributed to that strategy.
- `GET /api/v1/orders?source_type=manual` returns only manually-placed orders (no source_id required).
- `GET /api/v1/orders?source_id=42` without `source_type` returns 400 (the combination is ambiguous — different source types could share an id namespace).
- The Strategy detail Orders tab (P2 Session 5 §5.5.3) no longer pulls 500 orders and filters client-side. It calls `/api/v1/orders?source_type=strategy&source_id={id}` directly with a small limit.
- The P3 MCP `list_recent_orders` tool accepts optional `source_type` and `source_id` parameters and passes them through.
- The Pydantic `BaseOrder` response continues to expose `source_type` and `source_id` (no schema change).
- All existing tests still green; new tests cover the filter combinations.

What does NOT happen this session:
- No new index. Verified by the smoke + the existing `(user_id, created_at)` index. If P5/multi-user runs into slowness, add `CREATE INDEX ix_orders_source ON orders(user_id, source_type, source_id)` in a follow-up.
- No new endpoint. This is parameter expansion on an existing endpoint.
- No change to the WS topic stream — orders broadcast unchanged.
- No new MCP tool. We're updating the existing `list_recent_orders` signature, not adding `list_orders_by_strategy`.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                                       # clean
git pull origin main
git describe --tags --abbrev=0                   # expect: p4-opportunities-page-complete

./scripts/dev.sh &
sleep 30

# Orders endpoint reachable; current behavior returns all orders
curl -fs "http://127.0.0.1:8000/api/v1/orders?limit=5" | jq '.count'

# Strategy Orders tab currently pulls 500 and filters
# (smoke: open http://localhost:5173/strategies/{id} → Orders tab → Network panel)

docker compose down
```

- [ ] On `main`, at `p4-opportunities-page-complete`.
- [ ] `/api/v1/orders` endpoint responds; the existing Orders tab works (client-side filtered).

```bash
git checkout -b feat/p4-order-source-filter
```

---

## §5.1 — Backend: Extend the Orders Endpoint

Find the existing handler. Per P1 Session 6 it lives at `apps/backend/app/api/v1/orders.py` in a `list_orders` function with FastAPI's `Query(...)` parameters.

Edit `apps/backend/app/api/v1/orders.py`. Update the signature:

```python
from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType


@router.get("", response_model=OrderListResponse)
async def list_orders(
    status: Optional[OrderStatus] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    source_type: Optional[OrderSourceType] = Query(
        default=None,
        description="Filter by order source type (manual / strategy / agent / pine).",
    ),
    source_id: Optional[str] = Query(
        default=None,
        max_length=64,
        description="Filter by source id. REQUIRES source_type also be set.",
    ),
    since: Optional[datetime] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # Validate: source_id without source_type is ambiguous.
    if source_id is not None and source_type is None:
        raise HTTPException(
            status_code=400,
            detail="source_id requires source_type to also be specified.",
        )

    stmt = select(Order).where(Order.user_id == current_user.id)
    if status is not None:
        stmt = stmt.where(Order.status == status)
    if symbol:
        # Resolve ticker -> symbol_id; unknown symbol => empty result
        sym = (await session.execute(
            select(Symbol).where(Symbol.ticker == symbol.upper())
        )).scalars().first()
        if sym is None:
            return OrderListResponse(items=[], count=0)
        stmt = stmt.where(Order.symbol_id == sym.id)
    if source_type is not None:
        stmt = stmt.where(Order.source_type == source_type)
    if source_id is not None:
        # source_id is a string column (legacy heterogeneous design — see §0.4
        # of the P4 checklist). Compare as string.
        stmt = stmt.where(Order.source_id == source_id)
    if since is not None:
        stmt = stmt.where(Order.created_at >= since)
    stmt = stmt.order_by(Order.created_at.desc()).limit(limit)

    rows = (await session.execute(stmt)).scalars().all()
    return OrderListResponse(
        items=[await _order_to_response(session, o) for o in rows],
        count=len(rows),
    )
```

> Two design choices recorded here:
>
> 1. **`source_id without source_type → 400`.** A strategy with `id=42` and an agent with `id=42` are different entities; querying by `source_id=42` alone is meaningless. The 400 surfaces this earlier than "you got the wrong results."
>
> 2. **No filter for `source_type=null`.** "Manually-placed orders with no source_id" is the same as `source_type=manual` (P1 sets `OrderSourceType.MANUAL` for ticket-submitted orders, with `source_id=None`). If you ever genuinely need "orders with NULL source_type," that's a data-quality issue worth investigating directly, not a filter the API exposes.

- [ ] Handler signature extended with two new query params.
- [ ] 400 when `source_id` is set without `source_type`.

---

## §5.2 — Backend Tests

Edit `apps/backend/tests/api/test_orders_endpoint.py` (the P1 Session 6 file). Append new test cases — don't modify existing ones.

```python
"""P4 §5: source_type / source_id filter on /api/v1/orders."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.enums import (
    OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce,
)
from app.db.models.order import Order


# Reuse the existing `client` and `seeded` fixtures from this file.


def _now():
    return datetime.now(timezone.utc)


async def _make_order(
    session_factory, *, user_id=1, symbol_id=1,
    source_type: OrderSourceType, source_id: str | None,
):
    async with session_factory() as session:
        order = Order(
            user_id=user_id, account_id=1, symbol_id=symbol_id,
            broker_order_id=f"b-{_now().timestamp()}-{source_type.value}-{source_id or 'na'}",
            side=OrderSide.BUY, qty=Decimal("10"),
            type=OrderType.MARKET, tif=TimeInForce.DAY,
            status=OrderStatus.SUBMITTED,
            source_type=source_type, source_id=source_id,
            created_at=_now(), updated_at=_now(),
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order.id


@pytest.mark.asyncio
async def test_filter_by_source_type_manual(client, session_factory):
    await _make_order(session_factory, source_type=OrderSourceType.MANUAL, source_id=None)
    await _make_order(session_factory, source_type=OrderSourceType.STRATEGY, source_id="7")

    resp = await client.get("/api/v1/orders?source_type=manual")
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["source_type"] == "manual"


@pytest.mark.asyncio
async def test_filter_by_source_type_and_id(client, session_factory):
    await _make_order(session_factory, source_type=OrderSourceType.STRATEGY, source_id="7")
    await _make_order(session_factory, source_type=OrderSourceType.STRATEGY, source_id="8")
    await _make_order(session_factory, source_type=OrderSourceType.MANUAL, source_id=None)

    resp = await client.get("/api/v1/orders?source_type=strategy&source_id=7")
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["source_id"] == "7"
    assert body["items"][0]["source_type"] == "strategy"


@pytest.mark.asyncio
async def test_source_id_without_source_type_returns_400(client):
    resp = await client.get("/api/v1/orders?source_id=42")
    assert resp.status_code == 400
    assert "requires source_type" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_source_filter_returns_empty_when_no_match(client, session_factory):
    await _make_order(session_factory, source_type=OrderSourceType.STRATEGY, source_id="7")
    resp = await client.get("/api/v1/orders?source_type=strategy&source_id=999")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_source_filter_combines_with_status(client, session_factory):
    """Two strategy orders, different statuses — filter both must match."""
    o1 = await _make_order(session_factory, source_type=OrderSourceType.STRATEGY, source_id="7")
    o2 = await _make_order(session_factory, source_type=OrderSourceType.STRATEGY, source_id="7")
    # Mark o2 as filled
    async with session_factory() as session:
        row = await session.get(Order, o2)
        row.status = OrderStatus.FILLED
        await session.commit()

    resp = await client.get("/api/v1/orders?source_type=strategy&source_id=7&status=submitted")
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["id"] == o1


@pytest.mark.asyncio
async def test_source_filter_combines_with_symbol(client, session_factory):
    """Strategy orders on AAPL vs MSFT; filter by symbol drops MSFT."""
    from app.db.models.symbol import Symbol
    async with session_factory() as session:
        session.add(Symbol(id=2, ticker="MSFT", exchange="NASDAQ",
                           asset_class="us_equity", name="Microsoft", active=True))
        await session.commit()
    await _make_order(session_factory, symbol_id=1, source_type=OrderSourceType.STRATEGY, source_id="7")
    await _make_order(session_factory, symbol_id=2, source_type=OrderSourceType.STRATEGY, source_id="7")

    resp = await client.get("/api/v1/orders?source_type=strategy&source_id=7&symbol=AAPL")
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_source_type_only_returns_all_orders_of_that_type(client, session_factory):
    """source_type without source_id returns every order of that type."""
    await _make_order(session_factory, source_type=OrderSourceType.STRATEGY, source_id="7")
    await _make_order(session_factory, source_type=OrderSourceType.STRATEGY, source_id="8")
    await _make_order(session_factory, source_type=OrderSourceType.MANUAL, source_id=None)

    resp = await client.get("/api/v1/orders?source_type=strategy")
    body = resp.json()
    assert body["count"] == 2
    assert all(item["source_type"] == "strategy" for item in body["items"])


@pytest.mark.asyncio
async def test_invalid_source_type_returns_422(client):
    resp = await client.get("/api/v1/orders?source_type=garbage")
    # FastAPI enum validation
    assert resp.status_code == 422
```

Run:

```bash
cd apps/backend
uv run pytest tests/api/test_orders_endpoint.py -v
uv run pytest -q
cd ../..
```

- [ ] All eight new tests pass.
- [ ] Full backend suite still green.

---

## §5.3 — MCP Tool: Update `list_recent_orders`

Edit `apps/mcp-server/tools/list_recent_orders.py`. Extend the tool's schema and pass-through:

```python
"""Tool: list_recent_orders.

Recent orders including terminal ones. Calls GET /api/v1/orders.
Optional source_type / source_id filters route through to the backend.
"""
from __future__ import annotations

from typing import Any

from ._common import cap_list, get_json


NAME = "list_recent_orders"

DESCRIPTION = (
    "List recent orders (including filled, cancelled, rejected). Most recent "
    "first. Optionally filter by source_type and source_id to scope to a "
    "specific strategy or to manual orders. Useful for 'what orders did "
    "strategy X submit today' / 'why was this manual order rejected'."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "limit": {
            "type": "integer",
            "description": "Max orders to return (default 25, max 100)",
            "minimum": 1, "maximum": 100, "default": 25,
        },
        "source_type": {
            "type": "string",
            "enum": ["manual", "strategy", "agent", "pine"],
            "description": "Filter to orders of this source type.",
        },
        "source_id": {
            "type": "string",
            "description": (
                "Filter to a specific source id. REQUIRES source_type also be "
                "set. Example: source_type='strategy' source_id='42' returns "
                "only strategy 42's orders."
            ),
        },
    },
    "required": [],
}


async def execute(input: dict[str, Any]) -> dict:
    limit = min(int(input.get("limit", 25)), 100)
    params: dict[str, Any] = {"limit": limit}

    source_type = input.get("source_type")
    source_id = input.get("source_id")

    # Mirror the backend's invariant: source_id without source_type is 400.
    # Catch it client-side so we surface a helpful error rather than a 400 to the agent.
    if source_id is not None and source_type is None:
        return {
            "error": (
                "source_id requires source_type also to be specified. "
                "Example: source_type='strategy' source_id='42'."
            ),
            "items": [],
            "count": 0,
        }

    if source_type:
        params["source_type"] = source_type
    if source_id is not None:
        params["source_id"] = str(source_id)

    data = await get_json("/api/v1/orders", params=params)
    items = data.get("items", []) if isinstance(data, dict) else data
    return {
        "count": len(items),
        "items": cap_list(items, limit=limit),
    }
```

Edit the MCP runbook to document the new params. Append to `docs/runbook/mcp-tools.md` under the `list_recent_orders` section:

```markdown
**Parameters (P4 §5):**
- `source_type` ∈ {manual, strategy, agent, pine} — optional.
- `source_id` — optional; **requires source_type**. Example: `source_type='strategy', source_id='42'` returns only strategy 42's orders.

These filters reduce token usage when the agent is asking "what did my RSI strategy do today" — without them the agent gets 25 mixed orders and has to filter mentally. With them it gets exactly the slice it needs.
```

- [ ] MCP tool schema extended.
- [ ] Pre-validation mirrors the backend's 400 rule.
- [ ] Runbook updated.

> Test for the tool: append to `apps/mcp-server/tests/test_tools.py`:

```python
@pytest.mark.asyncio
async def test_list_recent_orders_passes_source_filters():
    captured = {}

    async def fake_get(path, params=None):
        captured["params"] = params
        return {"items": [], "count": 0}

    with patch("tools._common.get_json", new=AsyncMock(side_effect=fake_get)):
        await list_recent_orders.execute({
            "source_type": "strategy",
            "source_id": "42",
        })
    assert captured["params"]["source_type"] == "strategy"
    assert captured["params"]["source_id"] == "42"


@pytest.mark.asyncio
async def test_list_recent_orders_rejects_source_id_without_type():
    """Client-side mirror of the backend's 400."""
    result = await list_recent_orders.execute({"source_id": "42"})
    assert "error" in result
    assert "requires source_type" in result["error"]
```

```bash
cd apps/mcp-server
uv run pytest tests/ -v
cd ../..
```

- [ ] Two new MCP tool tests pass.

---

## §5.4 — Frontend: Remove the Client-Side Filter

The Strategy detail Orders tab from P2 Session 5 currently pulls 500 orders and filters client-side. Replace with a direct query.

Edit `apps/frontend/src/api/orders.ts` (if `ordersApi.list` doesn't already accept these params). Extend the typed signature:

```typescript
import type {
  Order, OrderListResponse, OrderSide, OrderSourceType, OrderStatus,
} from "./types";

export const ordersApi = {
  list: (params: {
    status?: OrderStatus;
    symbol?: string;
    source_type?: OrderSourceType;
    source_id?: string;
    since?: string;
    limit?: number;
  } = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set("status", params.status);
    if (params.symbol) q.set("symbol", params.symbol);
    if (params.source_type) q.set("source_type", params.source_type);
    if (params.source_id !== undefined) q.set("source_id", params.source_id);
    if (params.since) q.set("since", params.since);
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q}` : "";
    return apiFetch<OrderListResponse>(`/api/v1/orders${suffix}`);
  },

  // ... other methods unchanged ...
};
```

Extend `apps/frontend/src/api/types.ts` if missing:

```typescript
export type OrderSourceType = "manual" | "strategy" | "agent" | "pine";

// Confirm Order has source_type / source_id (P1 should have this):
export interface Order {
  // ... existing fields ...
  source_type: OrderSourceType;
  source_id: string | null;
}
```

Now rewrite the Orders tab. Edit `apps/frontend/src/pages/Strategies/tabs/OrdersTab.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react";
import { ordersApi } from "@/api/orders";
import type { Order } from "@/api/types";

interface Props {
  strategyId: number;
}

export function OrdersTab({ strategyId }: Props) {
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // P4 §5: filter at the backend, no more pull-500-and-filter.
      const resp = await ordersApi.list({
        source_type: "strategy",
        source_id: String(strategyId),
        limit: 100,
      });
      setOrders(resp.items);
    } finally {
      setLoading(false);
    }
  }, [strategyId]);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-400">
          Orders attributed to this strategy
        </span>
        <button onClick={load} className="rounded bg-gray-700 px-2 py-1 text-xs text-gray-200">
          {loading ? "…" : "Refresh"}
        </button>
      </div>

      <div className="rounded border border-gray-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-800 text-gray-300">
            <tr>
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Side</th>
              <th className="px-3 py-2 text-right">Qty</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Reason</th>
            </tr>
          </thead>
          <tbody>
            {orders.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-4 text-center text-gray-500">
                No strategy orders
              </td></tr>
            )}
            {orders.map((o) => (
              <tr key={o.id} className="border-t border-gray-800">
                <td className="px-3 py-2 text-xs text-gray-400">
                  {new Date(o.created_at).toLocaleString()}
                </td>
                <td className="px-3 py-2 font-semibold">{o.symbol}</td>
                <td className={`px-3 py-2 ${o.side === "buy" ? "text-emerald-400" : "text-rose-400"}`}>
                  {o.side.toUpperCase()}
                </td>
                <td className="px-3 py-2 text-right">{o.qty}</td>
                <td className="px-3 py-2">{o.type}</td>
                <td className="px-3 py-2">{o.status}</td>
                <td className="px-3 py-2 text-xs text-gray-400">{o.rejection_reason ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

Compare against the P2 Session 5 version: we **removed** the `.filter()` call and **changed** the API call from `ordersApi.list({ limit: 500 })` to a scoped query. Two lines removed; one line changed.

- [ ] `ordersApi.list` typed to accept `source_type` / `source_id`.
- [ ] Orders tab uses backend filtering; no client-side filter.

---

## §5.5 — Frontend Test

Edit `apps/frontend/src/pages/Strategies/__tests__/StrategyDetailPage.test.tsx` (the P2 Session 5 file). Append a test that verifies the right API call:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import StrategyDetailPage from "../Detail";
import { strategiesApi } from "@/api/strategies";
import { ordersApi } from "@/api/orders";
import { signalsApi } from "@/api/signals";


// Existing mocks ...


describe("StrategyDetailPage Orders tab — P4 §5 backend filter", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(strategiesApi.get).mockResolvedValue({
      id: 42, name: "rsi", version: "0.1.0",
      type: "python", status: "paper",
      code_path: "examples/rsi.py",
      params: {}, symbols: ["AAPL"], schedule: "*/1 * * * *",
      risk_limits_id: null, error_text: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    } as any);
    vi.mocked(strategiesApi.listRuns).mockResolvedValue({ items: [], count: 0 });
    vi.mocked(strategiesApi.listSignals).mockResolvedValue({ items: [], count: 0 });
    vi.mocked(strategiesApi.listBacktests).mockResolvedValue({ items: [], count: 0 });
    vi.mocked(signalsApi.list).mockResolvedValue({ items: [], count: 0 });
    vi.mocked(ordersApi.list).mockResolvedValue({ items: [], count: 0 });
  });

  it("calls ordersApi.list with source_type='strategy' and the strategy id", async () => {
    render(
      <MemoryRouter initialEntries={["/strategies/42"]}>
        <Routes>
          <Route path="/strategies/:id" element={<StrategyDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByText("rsi");
    fireEvent.click(screen.getByText("Orders"));

    await waitFor(() => expect(ordersApi.list).toHaveBeenCalled());
    const callArgs = vi.mocked(ordersApi.list).mock.calls[0]?.[0];
    expect(callArgs?.source_type).toBe("strategy");
    expect(callArgs?.source_id).toBe("42");
    // And we're NOT pulling 500 anymore
    expect(callArgs?.limit ?? 100).toBeLessThanOrEqual(100);
  });
});
```

Run:

```bash
cd apps/frontend
pnpm test --run
cd ../..
```

- [ ] New test passes.
- [ ] Existing Vitest tests still green.

---

## §5.6 — Manual Smoke

```bash
./scripts/dev.sh &
sleep 30

# Get a strategy id with some orders attributed to it
SID=$(curl -s "http://127.0.0.1:8000/api/v1/strategies?limit=1" | jq -r '.items[0].id')
echo "Strategy: $SID"

# New filter works
curl -s "http://127.0.0.1:8000/api/v1/orders?source_type=strategy&source_id=${SID}&limit=10" \
  | jq '{count, source_types: [.items[] | .source_type] | unique, source_ids: [.items[] | .source_id] | unique}'
# Expect: source_types: ["strategy"], source_ids: ["${SID}"]

# Same query, manual orders
curl -s "http://127.0.0.1:8000/api/v1/orders?source_type=manual&limit=10" \
  | jq '{count, source_types: [.items[] | .source_type] | unique}'

# Negative: source_id without source_type → 400
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8000/api/v1/orders?source_id=${SID}"
# Expect: 400

# Negative: invalid source_type → 422
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8000/api/v1/orders?source_type=bogus"
# Expect: 422

# UI smoke: open the strategy detail Orders tab
# Network panel should show one /api/v1/orders call with source_type=strategy & source_id=${SID}
# NOT a /api/v1/orders?limit=500 call followed by client-side filtering.
echo "Open http://localhost:5173/strategies/${SID} → Orders tab → check Network panel"

# MCP tool smoke
docker compose exec backend uv run python << 'EOF'
import asyncio, sys
sys.path.insert(0, '/app')
from tools import list_recent_orders

async def main():
    # Note: this hits the live backend via the MCP tool's normal path
    result = await list_recent_orders.execute({
        "source_type": "strategy",
        "source_id": "1",
        "limit": 5,
    })
    print(f"got {result['count']} orders")

    # Negative
    result = await list_recent_orders.execute({"source_id": "42"})
    print(f"validation result: {result.get('error', 'no error')}")
asyncio.run(main())
EOF

docker compose down
```

- [ ] Filter works; only the right slice returns.
- [ ] 400 fires for `source_id` without `source_type`.
- [ ] 422 fires for invalid `source_type`.
- [ ] UI Network panel shows a single scoped call instead of a 500-item pull.
- [ ] MCP tool returns scoped results and rejects bad input.

---

## §5.7 — Commit and PR

```bash
git add apps/backend/app/api/v1/orders.py
git add apps/backend/tests/api/test_orders_endpoint.py
git add apps/mcp-server/tools/list_recent_orders.py
git add apps/mcp-server/tests/test_tools.py
git add apps/frontend/src/api/orders.ts
git add apps/frontend/src/api/types.ts
git add apps/frontend/src/pages/Strategies/tabs/OrdersTab.tsx
git add apps/frontend/src/pages/Strategies/__tests__/StrategyDetailPage.test.tsx
git add docs/runbook/mcp-tools.md

git commit -m "feat(api): source_type and source_id filter on GET /orders (P4 §5)

- Backend: new optional query params source_type (enum) and source_id
  (string). source_id without source_type returns 400.
- Removed the client-side pull-500-and-filter hack in the Strategy
  detail Orders tab (P2 Session 5 §5.5.3 deferral). Now scoped to
  source_type=strategy and source_id={strategy_id} with limit=100.
- MCP list_recent_orders tool: schema extended; mirrors the backend's
  invariant by validating client-side before HTTP call.
- 8 new backend tests; 2 new MCP tests; 1 new frontend test.
- Runbook docs/runbook/mcp-tools.md updated for the new params."

git push -u origin feat/p4-order-source-filter

gh pr create \
  --title "feat(api): source_type / source_id filter on orders (P4 §5)" \
  --body "P4 Item 5 — small but eliminates the client-side pull-500-and-filter hack from the Strategy detail Orders tab. MCP tool also gets the filter so the agent can ask 'what did strategy 42 do' without pulling unrelated orders."

gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
git tag -a p4-order-source-filter-complete -m "P4 §5 complete"
git push origin p4-order-source-filter-complete
```

- [ ] PR merged.
- [ ] Tag pushed.
- [ ] `todo.md` updated: P4 §5 ✅.

---

## Verification Checklist (full session)

- [ ] §5.1 Backend handler accepts `source_type` and `source_id` query params; 400 when `source_id` set without `source_type`.
- [ ] §5.2 8 new endpoint tests pass; full backend suite green.
- [ ] §5.3 MCP `list_recent_orders` accepts new params; pre-validates source_id-without-type; runbook updated; 2 MCP tests added.
- [ ] §5.4 Frontend `ordersApi.list` typed for new params; Strategy detail Orders tab queries directly with scope; no `.filter()` call remains.
- [ ] §5.5 Frontend test verifies the right API params are sent.
- [ ] §5.6 Manual smoke green (5 curl steps + UI Network panel + MCP REPL).
- [ ] §5.7 PR merged, tag pushed.

---

## Notes & Gotchas

1. **`source_id` is a string, not an int.** Legacy P1 choice — `Order.source_id` is `String(64)`. The Pydantic schema mirrors it. If a future P5 refactor types it discriminated-union-ish (`{kind: 'strategy', id: int} | {kind: 'manual'}`), the API contract would change. For now, callers pass `source_id="42"` not `source_id=42`.

2. **400 on `source_id` without `source_type`** is the *single* combination we reject. All other combinations are valid:
   - `source_type=strategy` alone → all strategy orders
   - `source_type=manual` alone → all manual orders
   - `source_id=42` alone → 400 (ambiguous)
   - Both → scoped to one strategy

3. **No composite index added.** Gotcha #1 in the scope: the orders table is small enough that the existing `(user_id, created_at)` index plus a filter scan is fast. If P5 (multi-user) hits slowness, `CREATE INDEX ix_orders_source ON orders(user_id, source_type, source_id) WHERE source_type IS NOT NULL` is the targeted fix. Don't add it pre-emptively — `EXPLAIN QUERY PLAN` on the current dataset shows the existing index covers it.

4. **The MCP tool's client-side pre-validation.** §5.3's `if source_id is not None and source_type is None: return error_dict` mirrors the backend's 400. Without it, the agent gets a generic "WorkbenchAPIError: Backend returned 400" — useless. With it, the agent gets a specific error message it can recover from in its next turn.

5. **Frontend test asserts the actual call, not the resulting render.** The whole point of this item is that we're *not* pulling 500 orders anymore. The test must verify the API parameters, not just that orders render — the old buggy version also rendered orders, it just did so wastefully.

6. **Orders tab still polls every 5s.** P2 Session 5 kept this; we don't touch the polling cadence. The optimization is per-poll request weight (now ~100 rows max vs 500 before), not poll frequency.

7. **`source_id=null` is not filterable.** If you wanted "all orders with no source_id," that's `source_type=manual` (P1's invariant: manual orders have `source_id=None`; strategy/agent orders always have a non-null source_id). Adding an explicit `source_id_null=true` filter would be over-engineering for the actual use case.

8. **MCP tool returns an error dict, not raises.** §5.3's pre-validation returns `{"error": "...", "items": [], "count": 0}`. The agent receives this as the tool result and can read the error. Raising would surface as `WorkbenchAPIError`, which still works but the message is less actionable.

9. **Strategy detail page still polls every 5s.** No change to the polling cadence; just the per-poll request weight (100 rows max vs 500 before). The Orders tab also still subscribes to the `orders` WS topic from P1 Session 6 for instant updates on new orders.

10. **No backfill needed.** Existing rows already have `source_type` and `source_id` populated — P1's OrderRouter has been writing them since day one. The new filter just exposes what was already there.

11. **The P3 `list_recent_orders` MCP tool gets the filter for free agent UX.** Now an agent answering "did my RSI strategy execute today" doesn't burn token budget on 25 unrelated rows. The agent can ask for exactly the slice it needs, reducing both latency and cost. The runbook update reflects this.

12. **Don't bundle other P4 items into this PR.** One tag per item.

---

*End of P4 Item 5 v0.1.*
