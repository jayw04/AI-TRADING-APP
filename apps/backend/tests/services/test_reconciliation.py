"""Reconciliation service tests (P11 §3, ADR 0021).

Covers the pure position diff, the persisted-run + alert path (audit + metric +
reconciliation_runs row), the unavailable/error grading, and the scheduler pass
(per-account broker resolution, skip-on-no-adapter, best-effort isolation).

The service is ALERT-ONLY: these tests also assert it never imports or calls the
order path — see ``test_reconciliation_never_touches_order_path``.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.audit import AuditAction
from app.db.models.account import Account, AccountMode
from app.db.models.audit_log import AuditLog
from app.db.models.position import Position
from app.db.models.reconciliation_run import ReconciliationRun
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.services import reconciliation as recon
from app.services.reconciliation import (
    ALGORITHM_VERSION,
    Discrepancy,
    diff_positions,
    reconcile_intent,
    run_reconciliation,
    run_reconciliation_pass,
)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(
            Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper")
        )
        for sid, tk in ((1, "AAPL"), (2, "MSFT")):
            session.add(
                Symbol(id=sid, ticker=tk, exchange="NASDAQ", asset_class="us_equity",
                       name=tk, active=True)
            )
        await session.commit()
    yield


async def _add_position(session_factory, symbol_id: int, qty: str) -> None:
    async with session_factory() as session:
        session.add(
            Position(
                user_id=1, account_id=1, symbol_id=symbol_id, qty=Decimal(qty),
                avg_entry_price=Decimal("100"), side="long", market_value=Decimal("100"),
                cost_basis=Decimal("100"), unrealized_pl=Decimal("0"),
                unrealized_plpc=Decimal("0"), updated_at=datetime.now(UTC),
            )
        )
        await session.commit()


def _broker(positions: list[dict]) -> MagicMock:
    a = MagicMock()
    a.get_positions.return_value = positions
    return a


# ---- pure diff -----------------------------------------------------------------

def test_diff_clean() -> None:
    assert diff_positions({"AAPL": Decimal("10")}, {"AAPL": Decimal("10")}) == []


def test_diff_within_eps_is_clean() -> None:
    out = diff_positions({"AAPL": Decimal("10")}, {"AAPL": Decimal("10.0000001")})
    assert out == []


def test_diff_missing_broker() -> None:
    out = diff_positions({"AAPL": Decimal("10")}, {})
    assert len(out) == 1
    assert out[0].kind == "missing_broker"
    assert out[0].severity == "high"
    assert out[0].local == "10" and out[0].broker is None


def test_diff_missing_local() -> None:
    out = diff_positions({}, {"AAPL": Decimal("10")})
    assert out[0].kind == "missing_local"
    assert out[0].broker == "10" and out[0].local is None


def test_diff_qty_mismatch() -> None:
    out = diff_positions({"AAPL": Decimal("10")}, {"AAPL": Decimal("7")})
    assert out[0].kind == "qty_mismatch"
    assert out[0].local == "10" and out[0].broker == "7"


# ---- run_reconciliation --------------------------------------------------------

async def test_run_clean_pass(session_factory, seeded) -> None:
    await _add_position(session_factory, 1, "10")
    broker = _broker([{"symbol": "AAPL", "qty": "10"}])
    async with session_factory() as s:
        run = await run_reconciliation(s, broker, 1)
    assert run.result == "pass"
    assert run.n_checked == 1
    assert run.n_discrepancies == 0
    assert run.algorithm_version == ALGORITHM_VERSION
    assert run.detail_json is None
    # No discrepancy → no audit row.
    async with session_factory() as s:
        audits = (await s.execute(select(AuditLog))).scalars().all()
        assert audits == []


async def test_run_discrepancy_fails_and_alerts(session_factory, seeded) -> None:
    await _add_position(session_factory, 1, "10")  # local AAPL 10
    broker = _broker([{"symbol": "AAPL", "qty": "7"}])  # broker says 7
    async with session_factory() as s:
        run = await run_reconciliation(s, broker, 1)
    assert run.result == "fail"
    assert run.n_discrepancies == 1
    assert run.detail_json is not None
    # Persisted run + an audit row recording the discrepancy.
    async with session_factory() as s:
        runs = (await s.execute(select(ReconciliationRun))).scalars().all()
        assert len(runs) == 1
        audits = (await s.execute(select(AuditLog))).scalars().all()
        assert len(audits) == 1
        assert audits[0].action == AuditAction.RECONCILIATION_DISCREPANCY.value
        assert audits[0].target_type == "account"
        assert audits[0].target_id == "1"


async def test_run_broker_unavailable(session_factory, seeded) -> None:
    await _add_position(session_factory, 1, "10")
    broker = MagicMock()
    broker.get_positions.side_effect = RuntimeError("broker down")
    async with session_factory() as s:
        run = await run_reconciliation(s, broker, 1)
    assert run.result == "unavailable"
    assert run.n_discrepancies == 0
    # No conclusion drawn → no discrepancy audit.
    async with session_factory() as s:
        assert (await s.execute(select(AuditLog))).scalars().all() == []


async def test_run_internal_error_graded(session_factory, seeded, monkeypatch) -> None:
    monkeypatch.setattr(
        recon, "_local_qty_by_ticker",
        MagicMock(side_effect=ValueError("boom")),
    )
    broker = _broker([])
    async with session_factory() as s:
        run = await run_reconciliation(s, broker, 1)
    assert run.result == "error"


async def test_broker_qty_parsing_skips_blank_and_handles_quantity_key() -> None:
    # 'quantity' fallback key + blank-symbol row skipped + malformed qty → 0.
    out = recon._broker_qty_by_ticker(
        [{"ticker": "AAPL", "quantity": "5"}, {"symbol": ""}, {"symbol": "MSFT", "qty": "x"}]
    )
    assert out == {"AAPL": Decimal("5"), "MSFT": Decimal("0")}


# ---- intent (deferred) ---------------------------------------------------------

async def test_reconcile_intent_returns_empty(session_factory, seeded) -> None:
    async with session_factory() as s:
        assert await reconcile_intent(s, 1) == []


# ---- scheduler pass ------------------------------------------------------------

async def test_pass_reconciles_accounts_with_positions(session_factory, seeded) -> None:
    await _add_position(session_factory, 1, "10")
    broker = _broker([{"symbol": "AAPL", "qty": "10"}])
    await run_reconciliation_pass(session_factory, lambda _aid: broker)
    async with session_factory() as s:
        runs = (await s.execute(select(ReconciliationRun))).scalars().all()
        assert len(runs) == 1
        assert runs[0].account_id == 1


async def test_pass_skips_when_no_adapter(session_factory, seeded) -> None:
    await _add_position(session_factory, 1, "10")
    await run_reconciliation_pass(session_factory, lambda _aid: None)
    async with session_factory() as s:
        assert (await s.execute(select(ReconciliationRun))).scalars().all() == []


async def test_pass_is_best_effort_per_account(
    session_factory, seeded, monkeypatch
) -> None:
    """A reconciliation that raises for one account must not abort the pass."""
    await _add_position(session_factory, 1, "10")

    async def _boom(*_a, **_k):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(recon, "run_reconciliation", _boom)
    # Should swallow and return without raising.
    await run_reconciliation_pass(session_factory, lambda _aid: _broker([]))


async def test_pass_no_positions_is_noop(session_factory, seeded) -> None:
    await run_reconciliation_pass(session_factory, lambda _aid: _broker([]))
    async with session_factory() as s:
        assert (await s.execute(select(ReconciliationRun))).scalars().all() == []


async def test_pass_swallows_session_factory_failure() -> None:
    """The outer guard: if opening the listing session blows up, the pass logs
    and returns rather than letting the exception escape into the scheduler."""
    def _bad_factory():
        raise RuntimeError("db gone")

    await run_reconciliation_pass(_bad_factory, lambda _aid: _broker([]))


def test_reconciliation_never_touches_order_path() -> None:
    """ADR 0021 property 4: reconciliation alerts, never corrects. The module must
    not import the OrderRouter or a broker submit path."""
    import inspect

    src = inspect.getsource(recon)
    assert "OrderRouter" not in src
    assert "order_router" not in src
    assert ".submit(" not in src


def test_discrepancy_is_frozen() -> None:
    d = Discrepancy("position", "qty_mismatch", "high", "AAPL", "10", "7")
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.severity = "low"  # type: ignore[misc]
