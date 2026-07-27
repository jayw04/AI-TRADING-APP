"""ADR 0043 — the harness must MEASURE the session loss, or refuse.

The defect these tests exist for: `snapshot_state` read `accounts_state.day_change` with a
`.get(...) or 0` default. On the validation host there is no `accounts_state` row for account 3, so
every safety-critical reading in a Phase-0 run would have been a constant zero — the §5 breach
observation never becoming true, and the §10 overshoot floor never firing. The run would have spent
the session and recorded nothing.

The property under test throughout: **missing data stays missing and produces a NAMED refusal.** A
measurement that cannot be made is never a number, and never a zero.

See docs/incidents/ADR0043_Harness_AccountState_Missing_Defaults_To_Zero_20260724.md.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from unittest.mock import MagicMock

import pytest

from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.risk_session_baseline import RiskSessionBaseline
from app.db.models.user import User

BASELINE_EQUITY = D("84000")
FROZEN_NOW = datetime(2026, 7, 17, 17, 0, tzinfo=UTC)  # Friday, 13:00 ET — mid-session
OTHER_SESSION = "2026-07-16"


@pytest.fixture
def lib(monkeypatch):
    import scripts.adr0043_canary_lib as m

    m = importlib.reload(m)
    monkeypatch.setattr(m, "_utcnow", lambda: FROZEN_NOW)
    return m


def _session_date() -> str:
    from app.risk.loss_control.session_baseline import resolve_session_date

    date = resolve_session_date(FROZEN_NOW)
    assert date is not None, "FROZEN_NOW must be inside a real trading session"
    return date


def _adapter(equity: D | str | None = BASELINE_EQUITY, *, raises: Exception | None = None):
    a = MagicMock()
    if raises is not None:
        a.get_account.side_effect = raises
    else:
        a.get_account.return_value = {} if equity is None else {"equity": str(equity)}
    a.get_positions.return_value = []
    a.list_orders.return_value = []
    return a


async def _seed(
    session_factory,
    *,
    account_state: bool = True,
    baselines: list[dict] | None = None,
    user_id: int = 3,
):
    async with session_factory() as s:
        s.add(User(id=user_id, email="c@t"))
        s.add(
            Account(id=3, user_id=user_id, broker="alpaca", mode=AccountMode.paper, label="C")
        )
        if account_state:
            s.add(
                AccountState(
                    account_id=3,
                    equity=BASELINE_EQUITY,
                    last_equity=BASELINE_EQUITY,
                    updated_at=datetime.now(UTC),
                )
            )
        for spec in baselines or []:
            s.add(
                RiskSessionBaseline(
                    account_id=spec.get("account_id", 3),
                    market_session_date=spec.get("session_date", _session_date()),
                    baseline_equity=D(spec.get("equity", BASELINE_EQUITY)),
                    baseline_source="RECONCILED_OPEN",
                    captured_at=spec.get("captured_at", FROZEN_NOW - timedelta(hours=3)),
                    status=spec.get("status", "ACTIVE"),
                    created_by="TEST",
                )
            )
        await s.commit()


def _live_baseline(**over) -> dict:
    return {**{"equity": BASELINE_EQUITY}, **over}


async def _seed_second_baseline(session_factory):
    async with session_factory() as s:
        s.add(
            RiskSessionBaseline(
                account_id=3,
                market_session_date=_session_date(),
                baseline_equity=D("90000"),
                baseline_source="RECONCILED_OPEN",
                captured_at=FROZEN_NOW - timedelta(hours=2),
                status="ACTIVE",
                created_by="TEST",
            )
        )
        await s.commit()


# --------------------------------------------------------------------- the measurement itself


async def test_loss_is_live_equity_against_the_immutable_baseline(lib, session_factory):
    await _seed(session_factory, baselines=[_live_baseline()])
    loss = await lib.measure_session_loss(
        session_factory, _adapter(BASELINE_EQUITY - D("3000"))
    )
    assert loss.day_change == D("-3000")
    assert loss.equity == BASELINE_EQUITY - D("3000")
    assert loss.baseline_equity == BASELINE_EQUITY
    assert loss.basis == lib.LOSS_BASIS_SESSION_BASELINE
    assert loss.market_session_date == _session_date()


async def test_equity_is_re_read_so_the_loss_cannot_sit_still(lib, session_factory):
    """The disarmed harness returned the same cached number on every leg, which is
    indistinguishable from 'the churn is not working'. Each call must see the account move."""
    await _seed(session_factory, baselines=[_live_baseline()])
    adapter = _adapter()
    adapter.get_account.side_effect = [
        {"equity": str(BASELINE_EQUITY - D("500"))},
        {"equity": str(BASELINE_EQUITY - D("1800"))},
        {"equity": str(BASELINE_EQUITY - D("3100"))},
    ]
    seen = [
        (await lib.measure_session_loss(session_factory, adapter)).day_change for _ in range(3)
    ]
    assert seen == [D("-500"), D("-1800"), D("-3100")]


async def test_a_numerically_zero_baseline_is_present_not_missing(lib, session_factory):
    """`0` is a value. Treating it as absent is the same falsiness bug in a different place."""
    await _seed(session_factory, baselines=[_live_baseline(equity=D("0"))])
    loss = await lib.measure_session_loss(session_factory, _adapter(D("500")))
    assert loss.baseline_equity == D("0")
    assert loss.day_change == D("500")


# ------------------------------------------------------------------------- named refusals


async def test_missing_account_state_row_refuses(lib, session_factory):
    """The exact validation-host condition: account 3 has no accounts_state row."""
    await _seed(session_factory, account_state=False, baselines=[_live_baseline()])
    with pytest.raises(lib.LossMeasurementUnavailable) as exc:
        await lib.snapshot_state(session_factory, _adapter())
    assert exc.value.stop_reason == lib.STOP_ACCOUNT_STATE_ROW_MISSING


async def test_missing_current_session_baseline_refuses(lib, session_factory):
    await _seed(session_factory, baselines=[])
    with pytest.raises(lib.LossMeasurementUnavailable) as exc:
        await lib.measure_session_loss(session_factory, _adapter())
    assert exc.value.stop_reason == lib.STOP_SESSION_BASELINE_MISSING


async def test_a_previous_sessions_baseline_refuses(lib, session_factory):
    """A stale baseline is worse than none: it would silently measure today against yesterday."""
    await _seed(session_factory, baselines=[_live_baseline(session_date=OTHER_SESSION)])
    with pytest.raises(lib.LossMeasurementUnavailable) as exc:
        await lib.measure_session_loss(session_factory, _adapter())
    assert exc.value.stop_reason == lib.STOP_SESSION_BASELINE_WRONG_SESSION
    assert OTHER_SESSION in exc.value.diagnostics["baseline_session_dates"]


async def test_a_superseded_only_baseline_refuses(lib, session_factory):
    await _seed(session_factory, baselines=[_live_baseline(status="SUPERSEDED")])
    with pytest.raises(lib.LossMeasurementUnavailable) as exc:
        await lib.measure_session_loss(session_factory, _adapter())
    assert exc.value.stop_reason == lib.STOP_SESSION_BASELINE_MISSING


async def test_the_schema_refuses_a_second_baseline_for_the_session(session_factory):
    """The primary defence: `(account_id, market_session_date)` is unique, so a restart cannot mint
    a second, more favourable baseline mid-session."""
    from sqlalchemy.exc import IntegrityError

    await _seed(session_factory, baselines=[_live_baseline()])
    with pytest.raises(IntegrityError):
        await _seed_second_baseline(session_factory)


def test_contradictory_baselines_refuse(lib):
    """The second defence, for a database that arrives without that constraint (a restore, a copy):
    two ACTIVE rows mean two different answers, and picking one would be a guess."""
    rows = [
        {"id": 1, "account_id": 3, "market_session_date": "2026-07-17", "status": "ACTIVE"},
        {"id": 2, "account_id": 3, "market_session_date": "2026-07-17", "status": "ACTIVE"},
    ]
    with pytest.raises(lib.LossMeasurementUnavailable) as exc:
        lib.select_active_baseline(rows, "2026-07-17")
    assert exc.value.stop_reason == lib.STOP_SESSION_BASELINE_CONTRADICTORY
    assert exc.value.diagnostics["baseline_ids"] == [1, 2]


def test_a_superseded_row_never_shadows_the_active_one(lib):
    rows = [
        {"id": 1, "account_id": 3, "market_session_date": "2026-07-17", "status": "SUPERSEDED"},
        {"id": 2, "account_id": 3, "market_session_date": "2026-07-17", "status": "ACTIVE"},
    ]
    assert lib.select_active_baseline(rows, "2026-07-17")["id"] == 2


async def test_a_baseline_captured_after_the_first_order_refuses(lib, session_factory):
    """A baseline minted after activity describes the account mid-move, so any loss measured from
    it understates what the session actually did."""
    from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce
    from app.db.models.order import Order
    from app.db.models.symbol import Symbol

    await _seed(
        session_factory,
        baselines=[_live_baseline(captured_at=FROZEN_NOW + timedelta(hours=1))],
    )
    async with session_factory() as s:
        s.add(
            Symbol(id=1, ticker="IEUS", exchange="X", asset_class="us_equity", name="C", active=True)
        )
        s.add(
            Order(
                user_id=3,
                account_id=3,
                symbol_id=1,
                client_order_id="c-1",
                side=OrderSide.BUY,
                qty=D("1"),
                type=OrderType.MARKET,
                tif=TimeInForce.DAY,
                status=OrderStatus.FILLED,
                source_type=OrderSourceType.STRATEGY,
                created_at=FROZEN_NOW,
                updated_at=FROZEN_NOW,
            )
        )
        await s.commit()

    with pytest.raises(lib.LossMeasurementUnavailable) as exc:
        await lib.measure_session_loss(session_factory, _adapter())
    assert exc.value.stop_reason == lib.STOP_SESSION_BASELINE_AFTER_FIRST_SUBMISSION


async def test_another_accounts_baseline_cannot_satisfy_the_lookup(lib, session_factory):
    """Account 1 is the only row the validation host actually had. It must not stand in for 3."""
    async with session_factory() as s:
        s.add(User(id=1, email="a@t"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="A"))
        await s.commit()
    await _seed(session_factory, baselines=[])
    async with session_factory() as s:
        s.add(
            RiskSessionBaseline(
                account_id=1,
                market_session_date=_session_date(),
                baseline_equity=BASELINE_EQUITY,
                baseline_source="RECONCILED_OPEN",
                captured_at=FROZEN_NOW - timedelta(hours=3),
                status="ACTIVE",
                created_by="TEST",
            )
        )
        await s.commit()

    with pytest.raises(lib.LossMeasurementUnavailable) as exc:
        await lib.measure_session_loss(session_factory, _adapter())
    assert exc.value.stop_reason == lib.STOP_SESSION_BASELINE_MISSING


async def test_an_account_owned_by_another_user_refuses(lib, session_factory):
    await _seed(session_factory, user_id=9, baselines=[_live_baseline()])
    with pytest.raises(lib.LossMeasurementUnavailable) as exc:
        await lib.measure_session_loss(session_factory, _adapter())
    assert exc.value.stop_reason == lib.STOP_SESSION_BASELINE_ACCOUNT_MISMATCH


async def test_unreadable_equity_refuses_rather_than_defaulting(lib, session_factory, monkeypatch):
    monkeypatch.setattr(lib.time, "sleep", lambda _s: None)
    await _seed(session_factory, baselines=[_live_baseline()])
    with pytest.raises(lib.LossMeasurementUnavailable) as exc:
        await lib.measure_session_loss(session_factory, _adapter(equity=None))
    assert exc.value.stop_reason == lib.STOP_CURRENT_EQUITY_UNAVAILABLE


async def test_a_broker_flap_is_retried_before_it_becomes_a_stop(lib, session_factory, monkeypatch):
    """§9 of the frozen plan: 5xx flaps are routine, so one failure must not lose the session —
    but exhausting the bounded attempts is a stop, never a fallback number."""
    monkeypatch.setattr(lib.time, "sleep", lambda _s: None)
    await _seed(session_factory, baselines=[_live_baseline()])
    adapter = _adapter()
    adapter.get_account.side_effect = [
        ConnectionError("50010000"),
        ConnectionError("50010000"),
        {"equity": str(BASELINE_EQUITY - D("250"))},
    ]
    loss = await lib.measure_session_loss(session_factory, adapter)
    assert loss.day_change == D("-250")
    assert adapter.get_account.call_count == 3


async def test_outside_a_trading_session_there_is_no_measurement(lib, session_factory, monkeypatch):
    monkeypatch.setattr(lib, "_utcnow", lambda: datetime(2026, 7, 18, 17, 0, tzinfo=UTC))  # Saturday
    await _seed(session_factory, baselines=[_live_baseline()])
    with pytest.raises(lib.LossMeasurementUnavailable) as exc:
        await lib.measure_session_loss(session_factory, _adapter())
    assert exc.value.stop_reason == lib.STOP_NOT_A_TRADING_SESSION


# ------------------------------------------------------------------------ restart behaviour


async def test_a_restart_reuses_the_frozen_baseline_and_mints_nothing(lib, session_factory):
    """The measurement only ever READS the baseline. A restart mid-session must measure against the
    same row — a fresh, more favourable baseline is precisely the failure ADR 0043 exists to stop."""
    await _seed(session_factory, baselines=[_live_baseline()])
    first = await lib.measure_session_loss(
        session_factory, _adapter(BASELINE_EQUITY - D("1000"))
    )
    importlib.reload(lib)  # a new process, as far as the module is concerned

    import scripts.adr0043_canary_lib as reloaded

    reloaded._utcnow = lambda: FROZEN_NOW
    second = await reloaded.measure_session_loss(
        session_factory, _adapter(BASELINE_EQUITY - D("2500"))
    )

    assert second.baseline_id == first.baseline_id
    assert second.baseline_equity == first.baseline_equity
    assert second.day_change == D("-2500")  # only the equity moved
    async with session_factory() as s:
        from sqlalchemy import func, select

        assert (
            await s.scalar(select(func.count()).select_from(RiskSessionBaseline))
        ) == 1, "the measurement must never create a baseline"


async def test_the_snapshot_carries_the_measurement_provenance(lib, session_factory):
    """Evidence has to name the baseline the number came from, or a reviewer cannot check it."""
    await _seed(session_factory, baselines=[_live_baseline()])
    snap = await lib.snapshot_state(session_factory, _adapter(BASELINE_EQUITY - D("3000")))
    assert snap.day_change == D("-3000")
    evidence = snap.as_dict()["loss"]
    assert evidence["basis"] == lib.LOSS_BASIS_SESSION_BASELINE
    assert evidence["baseline_equity"] == str(BASELINE_EQUITY)
    assert evidence["market_session_date"] == _session_date()
    assert evidence["baseline_id"] == snap.loss.baseline_id
