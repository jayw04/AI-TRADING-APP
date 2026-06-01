"""P5 §8.3 — /metrics endpoint + the order-submission counter.

The endpoint is tested via the API. The counter is tested at the OrderRouter
level (the order_router is not on app.state when alpaca-startup is disabled in
tests — same constraint as the §6/§7 router-level tests)."""

from decimal import Decimal

from prometheus_client import REGISTRY

from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.db.models.account import Account, AccountMode
from app.db.models.user import User
from app.orders.router import OrderRouter
from app.risk.engine import RiskEngine
from app.risk.types import OrderRequest


async def test_metrics_endpoint_returns_prometheus_format(client):
    r = await client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "# HELP workbench_orders_submitted_total" in body
    assert "# TYPE workbench_orders_submitted_total counter" in body
    assert "workbench_strategies_active" in body
    assert "workbench_audit_log_rows_total" in body


class _PaperStub:
    is_paper = True

    def submit_order(self, **kwargs):
        return {"id": "broker-1", "status": "accepted"}


class _Bus:
    async def publish(self, topic, payload):
        return None


async def test_order_counter_increments_on_submission(session_factory):
    from datetime import UTC, datetime

    async with session_factory() as s:
        s.add(User(id=1, email="t@local"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper,
                      label="P", created_at=datetime.now(UTC)))
        await s.commit()

    def _count() -> float:
        # outcome is "rejected" (no risk limits seeded) — what matters is that
        # the paper+manual counter advances.
        val = REGISTRY.get_sample_value(
            "workbench_orders_submitted_total",
            {"outcome": "rejected", "account_mode": "paper", "source": "manual"},
        )
        return val or 0.0

    before = _count()
    router = OrderRouter(_PaperStub(), RiskEngine(session_factory), session_factory, _Bus())
    req = OrderRequest(
        user_id=1, account_id=1, symbol_ticker="AAPL", side=OrderSide.BUY,
        qty=Decimal("1"), type=OrderType.MARKET, tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,
    )
    await router.submit(req)
    assert _count() >= before + 1
