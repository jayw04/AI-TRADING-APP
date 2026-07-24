"""ADR 0043 Phase 0 churn driver — the ways it could establish the lock UNSAFELY.

The driver's job is narrow (get the account across its own daily-loss boundary) but its failure
modes are not: it trades, so every one of them costs real money on the paper rig and, worse, can
leave the canary asserting against a state nobody verified. These tests run offline with a fake
broker and prove the driver is single-order, synchronous, bounded, and fail-closed — and that it
never touches the protected leg the canary's assertions depend on.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce
from app.db.models.account import Account, AccountMode
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.symbol import Symbol
from app.db.models.user import User

PROTECTED_TICKER = "MSFT"
CHURN_TICKER = "IEUS"

#: The account's equity at the session open. The harness measures `equity - baseline`, so the rig
#: moves equity and the expected day-change follows from arithmetic, not from a settable field.
BASELINE_EQUITY = D("84000")

#: A fixed mid-session Friday. The loss measurement is only defined inside a trading session, so a
#: real-clock suite would fail every weekend and holiday; pinning it also fixes the session date the
#: seeded baseline must carry.
FROZEN_NOW = datetime(2026, 7, 17, 17, 0, tzinfo=UTC)  # 13:00 ET


@pytest.fixture(autouse=True)
def _frozen_measurement_clock(monkeypatch):
    import scripts.adr0043_canary_lib as lib

    monkeypatch.setattr(lib, "_utcnow", lambda: FROZEN_NOW)


@pytest.fixture
def drv(tmp_path, monkeypatch):
    monkeypatch.setenv("ADR0043_CHURN_CHECKPOINT", str(tmp_path / "churn.json"))
    monkeypatch.setenv("ADR0043_LOCKFILE", str(tmp_path / "churn.lock"))
    import scripts.adr0043_canary_lib as lib
    import scripts.adr0043_churn_driver as m

    importlib.reload(lib)
    monkeypatch.setattr(lib, "_utcnow", lambda: FROZEN_NOW)  # survives the reload above
    return importlib.reload(m)


@pytest.fixture
def lib(drv):
    import scripts.adr0043_canary_lib as m

    return m


# ---------------------------------------------------------------------------- fake broker


class FakeBroker:
    """A paper account that actually moves: positions change as orders fill, and each round trip
    loses a fixed amount, so the driver's loop terminates on a real day_change rather than a flag."""

    def __init__(self, *, loss_per_leg=D("0"), price=D("50"), protected=D("19"),
                 buying_power=D("100000"), equity=BASELINE_EQUITY):
        self.positions: dict[str, D] = {PROTECTED_TICKER: protected}
        self.price = price
        self.loss_per_leg = loss_per_leg
        # Equity is what the harness now measures against the immutable session baseline; the rig
        # moves the ACCOUNT, not a cached day_change column, because that is what a real churn does.
        self.equity = D(equity)
        self.buying_power = buying_power
        self.orders: list[dict] = []
        self.open_orders: list[dict] = []
        self.fail_symbol_move: str | None = None

    @property
    def day_change(self) -> D:
        """Derived, never set: `equity - baseline`, the same arithmetic the harness performs."""
        return self.equity - BASELINE_EQUITY

    # ---- reads ----
    def get_positions(self):
        return [
            {"symbol": s, "qty": str(q), "market_value": str(q * self.price)}
            for s, q in self.positions.items() if q != 0
        ]

    def get_account(self):
        return {"buying_power": str(self.buying_power), "equity": str(self.equity)}

    def list_orders(self, *a, **k):
        return list(self.open_orders)

    def get_order(self, broker_order_id):
        for o in self.orders:
            if o["id"] == broker_order_id:
                return o
        return None

    # ---- the fill the driver's settle spy will apply ----
    def fill(self, *, symbol, side, qty, client_order_id):
        signed = qty if side == "BUY" else -qty
        self.positions[symbol] = self.positions.get(symbol, D(0)) + signed
        self.equity -= self.loss_per_leg
        bo = {"id": f"b-{len(self.orders) + 1}", "status": "filled", "filled_qty": str(qty),
              "filled_avg_price": str(self.price), "client_order_id": client_order_id,
              "symbol": symbol, "side": side.lower(), "qty": str(qty)}
        self.orders.append(bo)
        return bo


class FakeRouter:
    """Persists a local order like the real router does, and asks the broker to fill it."""

    def __init__(self, sf, broker: FakeBroker, *, reject=False, reject_sides=()):
        self.sf = sf
        self.broker = broker
        self.submits = 0
        self.reject = reject
        self.reject_sides = tuple(reject_sides)

    async def submit(self, req):
        self.submits += 1
        side = "BUY" if req.side == OrderSide.BUY else "SELL"
        rejected = self.reject or side in self.reject_sides
        async with self.sf() as s:
            o = Order(user_id=3, account_id=3, symbol_id=_symbol_id(req.symbol_ticker),
                      client_order_id=req.client_order_id, side=req.side, qty=req.qty,
                      type=OrderType.MARKET, tif=TimeInForce.DAY,
                      status=OrderStatus.REJECTED if rejected else OrderStatus.SUBMITTED,
                      source_type=OrderSourceType.STRATEGY,
                      rejection_reason="LOSS_CONTROL_STOP" if rejected else None,
                      created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
            s.add(o)
            await s.commit()
            oid = o.id
        if rejected:
            return SimpleNamespace(id=oid, status="rejected", rejection_reason="LOSS_CONTROL_STOP")
        bo = self.broker.fill(symbol=req.symbol_ticker, side=side, qty=req.qty,
                              client_order_id=req.client_order_id)
        async with self.sf() as s:
            from sqlalchemy import update
            await s.execute(update(Order).where(Order.id == oid).values(
                status=OrderStatus.FILLED, broker_order_id=bo["id"],
                terminal_at=datetime.now(UTC)))
            await s.commit()
        await _book_fill(self.sf, oid, req.qty, self.broker.price)
        await _sync_position(self.sf, req.symbol_ticker, self.broker.positions.get(
            req.symbol_ticker, D(0)))
        return SimpleNamespace(id=oid, status="submitted", broker_order_id=bo["id"],
                               rejection_reason=None)


def _symbol_id(ticker: str) -> int:
    return {PROTECTED_TICKER: 1, CHURN_TICKER: 2, "KOKU": 3}[ticker.upper()]


async def _book_fill(sf, order_id, qty, price):
    from app.db.models.fill import Fill
    async with sf() as s:
        s.add(Fill(order_id=order_id, broker_fill_id=f"f-{order_id}", qty=qty, price=price,
                   commission=D("0"), filled_at=datetime.now(UTC)))
        await s.commit()


async def _sync_position(sf, ticker, qty):
    from sqlalchemy import delete, select
    async with sf() as s:
        sid = _symbol_id(ticker)
        row = await s.scalar(select(Position).where(Position.account_id == 3,
                                                    Position.symbol_id == sid))
        if qty == 0:
            await s.execute(delete(Position).where(Position.account_id == 3,
                                                   Position.symbol_id == sid))
        elif row is None:
            s.add(Position(user_id=3, account_id=3, symbol_id=sid, qty=qty,
                           avg_entry_price=D("50"), side="long", market_value=D("0"),
                           cost_basis=D("0"), unrealized_pl=D("0"), unrealized_plpc=D("0"),
                           updated_at=datetime.now(UTC)))
        else:
            row.qty = qty
        await s.commit()


class SettleSpy:
    """Stands in for the shared barrier. Records call order; can be told to fail."""

    def __init__(self, sf, broker: FakeBroker, *, fail_on=None):
        self.sf = sf
        self.broker = broker
        self.calls: list[int] = []
        self.fail_on = fail_on          # leg order-id index at which to fail, or None

    async def __call__(self, sf, adapter, consumer, *, order_id, ticker, timeout_s=None):
        self.calls.append(order_id)
        if self.fail_on is not None and len(self.calls) == self.fail_on:
            from app.orders.settlement import SettlementError
            raise SettlementError(f"order {order_id}: still non-terminal at broker (new) after 45s")
        qty = self.broker.positions.get(ticker, D(0))
        return SimpleNamespace(broker_status="filled", local_status="filled",
                               filled_qty=D("0"), local_position=qty, broker_position=qty, polls=1)


# ---------------------------------------------------------------------------- seeding


async def _seed(session_factory, *, max_daily_loss="2000", baseline: str | None = "84000"):
    """Seed the rig, including the immutable session baseline the harness measures against.

    ``baseline=None`` omits the baseline row entirely — the state the validation host was actually
    in, and the one the harness must refuse rather than read as a zero loss."""
    from app.db.enums import RiskScopeType
    from app.db.models.account_state import AccountState
    from app.db.models.risk_limits import RiskLimits
    from app.db.models.risk_session_baseline import RiskSessionBaseline
    async with session_factory() as s:
        s.add(User(id=3, email="c@t"))
        s.add(Account(id=3, user_id=3, broker="alpaca", mode=AccountMode.paper, label="C"))
        s.add(Symbol(id=1, ticker=PROTECTED_TICKER, exchange="X", asset_class="us_equity",
                     name="Microsoft", active=True))
        s.add(Symbol(id=2, ticker=CHURN_TICKER, exchange="X", asset_class="us_equity",
                     name="Churn", active=True))
        s.add(Symbol(id=3, ticker="KOKU", exchange="X", asset_class="us_equity", name="Churn2",
                     active=True))
        s.add(RiskLimits(
            user_id=3, scope_type=RiskScopeType.GLOBAL, broker_mode="paper",
            max_position_qty=D("1000"), max_position_notional=D("50000"),
            max_gross_exposure=D("200000"), max_daily_loss=D(max_daily_loss),
            max_orders_per_day=500, allow_short=False,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
        # day_change is deliberately left at its column default: nothing reads it any more, and a
        # stale value here must not be able to influence a single assertion.
        s.add(AccountState(
            account_id=3, equity=BASELINE_EQUITY, last_equity=BASELINE_EQUITY,
            updated_at=datetime.now(UTC)))
        if baseline is not None:
            s.add(RiskSessionBaseline(
                account_id=3,
                market_session_date=_session_date(),
                baseline_equity=D(baseline),
                baseline_source="RECONCILED_OPEN",
                captured_at=FROZEN_NOW - timedelta(hours=3),  # before any order the rig creates
                status="ACTIVE",
                created_by="TEST"))
        await s.commit()
    await _sync_position(session_factory, PROTECTED_TICKER, D("19"))


def _session_date() -> str:
    """The frozen instant's ET session date, from the calendar authority the harness itself uses."""
    from app.risk.loss_control.session_baseline import resolve_session_date
    date = resolve_session_date(FROZEN_NOW)
    assert date is not None, "FROZEN_NOW must be inside a real trading session"
    return date


_NOW = 1_000_000.0


def _quote_at(price, *, now=_NOW, age_s=0.0, source=None):
    """A governed-quote dict shaped like app.market_data.quotes.get_last_quote's output."""
    import scripts.adr0043_churn_driver as m

    ts = datetime.fromtimestamp(now - age_s, UTC).isoformat()
    ask = price
    bid = None if price is None else price - D("0.02")
    return {"symbol": "IEUS",
            "bid": None if bid is None else str(bid),
            "ask": None if ask is None else str(ask),
            "last": None if ask is None else str(ask),
            "ts": ts,
            "source": m.APPROVED_QUOTE_SOURCE if source is None else source}


def _driver(drv, session_factory, broker, *, router=None, settle=None, bounds=None,
            symbols=("IEUS",), price=D("50"), quote_fn=None, now=_NOW, max_quote_age_s=None):
    import scripts.adr0043_canary_lib as lib

    router = router or FakeRouter(session_factory, broker)
    settle = settle or SettleSpy(session_factory, broker)

    if quote_fn is None:
        async def quote_fn(_sym):
            return None if price is None else _quote_at(price, now=now)

    extra = {} if max_quote_age_s is None else {"max_quote_age_s": max_quote_age_s}
    return drv.ChurnDriver(
        sf=session_factory, adapter=broker, router=router, evidence=lib.Evidence(phase="TEST"),
        checkpoint=drv.ChurnCheckpoint.load(), consumer=MagicMock(), settle=settle,
        quote_fn=quote_fn, now_fn=lambda: now, bounds=bounds, symbols=symbols, **extra)


# ============================================================ protected-position isolation


def test_churn_symbol_equal_to_protected_is_refused_in_code(drv, lib):
    for bad in ("MSFT", "msft"):
        with pytest.raises(lib.CanaryRefused, match="overlap"):
            drv.validate_symbols((bad,))


def test_churn_symbol_overlapping_a_configured_leg_is_refused(drv, lib):
    leg_symbol = sorted(drv.NEVER_CHURN)[0]
    with pytest.raises(lib.CanaryRefused, match="overlap"):
        drv.validate_symbols((leg_symbol, "IEUS"))


def test_empty_and_duplicate_symbol_sets_are_refused(drv, lib):
    with pytest.raises(lib.CanaryRefused):
        drv.validate_symbols(())
    with pytest.raises(lib.CanaryRefused, match="duplicate"):
        drv.validate_symbols(("IEUS", "ieus"))


async def test_overlapping_symbol_refuses_before_any_submission(drv, session_factory):
    await _seed(session_factory)
    broker = FakeBroker()
    router = FakeRouter(session_factory, broker)
    driver = _driver(drv, session_factory, broker, router=router, symbols=("MSFT",))
    import scripts.adr0043_canary_lib as canary_lib
    with pytest.raises(canary_lib.CanaryRefused):
        await driver.preflight()
    assert router.submits == 0, "not one order may be sent before the disjointness proof"


# ============================================================ the per-leg invariants


def test_assess_churn_leg_green_on_a_clean_leg(drv):
    ok, v = drv.assess_churn_leg(
        local_status="filled", fill_count=1, booked_qty=D("10"), ordered_qty=D("10"),
        local_position=D("10"), broker_position=D("10"), held_reservations=0,
        open_broker_orders=0, loss_control_state="NORMAL", allowed_states=("NORMAL", None),
        breaker_tripped=False, breaker_trip_allowed=False, limits_fp="abc", frozen_limits_fp="abc",
        protected_now={"MSFT": D("19")}, protected_frozen={"MSFT": D("19")})
    assert ok is True and v == []


@pytest.mark.parametrize(("over", "expect"), [
    ({"local_status": "submitted"}, "not terminally FILLED"),
    ({"local_status": "partially_filled"}, "not terminally FILLED"),
    ({"booked_qty": D("4")}, "not fully filled"),          # partial never advances the driver
    ({"fill_count": 0}, "not fully filled"),
    ({"local_position": D("9")}, "!= broker"),
    ({"held_reservations": 1}, "HELD reservation"),
    ({"open_broker_orders": 1}, "unexpected open broker order"),
    ({"loss_control_state": "INTEGRITY_STOP"}, "loss-control state"),
    ({"breaker_tripped": True}, "circuit breaker"),
    ({"limits_fp": "zzz"}, "limits changed mid-run"),
    ({"protected_now": {"MSFT": D("18")}}, "protected MSFT moved"),
])
def test_assess_churn_leg_stops_on_each_violation(drv, over, expect):
    base = dict(local_status="filled", fill_count=1, booked_qty=D("10"), ordered_qty=D("10"),
                local_position=D("10"), broker_position=D("10"), held_reservations=0,
                open_broker_orders=0, loss_control_state="NORMAL", allowed_states=("NORMAL", None),
                breaker_tripped=False, breaker_trip_allowed=False, limits_fp="abc",
                frozen_limits_fp="abc", protected_now={"MSFT": D("19")},
                protected_frozen={"MSFT": D("19")})
    base.update(over)
    ok, violations = drv.assess_churn_leg(**base)
    assert ok is False and any(expect in x for x in violations), violations


# ============================================================ Phase 0 readiness


def test_phase0_ready_only_on_the_whole_end_state(drv):
    ok, _ = drv.assess_phase0_ready(
        day_change=D("-2100"), max_daily_loss=D("2000"),
        loss_control_state="REDUCTION_ONLY_DAILY_LOSS", trip_cause="DAILY_LOSS_BREACH",
        protected_ok=True, setup_positions={"IEUS": D("0")}, open_orders=0, held_reservations=0)
    assert ok is True


@pytest.mark.parametrize("over", [
    {"day_change": D("-1900")},                              # never crossed the boundary
    {"loss_control_state": "NORMAL"},                        # loss taken but no durable lock
    {"loss_control_state": "REDUCTION_ONLY_BREAKER"},        # locked for the wrong reason
    {"trip_cause": "MANUAL"},
    {"trip_cause": None},
    {"protected_ok": False},                                 # the protected leg moved
    {"setup_positions": {"IEUS": D("40")}},                  # temporary exposure left open
    {"open_orders": 1},
    {"held_reservations": 1},
])
def test_phase0_not_ready_on_any_missing_condition(drv, over):
    base = dict(day_change=D("-2100"), max_daily_loss=D("2000"),
                loss_control_state="REDUCTION_ONLY_DAILY_LOSS", trip_cause="DAILY_LOSS_BREACH",
                protected_ok=True, setup_positions={"IEUS": D("0")}, open_orders=0,
                held_reservations=0)
    base.update(over)
    ok, _ = drv.assess_phase0_ready(**base)
    assert ok is False, f"Phase 0 must be NOT READY for {over}"


def test_submitted_churn_is_not_the_success_condition(drv):
    """Loss realised, nothing else true: submitting plenty of churn proves nothing on its own."""
    ok, _ = drv.assess_phase0_ready(
        day_change=D("-5000"), max_daily_loss=D("2000"), loss_control_state="NORMAL",
        trip_cause=None, protected_ok=True, setup_positions={"IEUS": D("0")}, open_orders=0,
        held_reservations=0)
    assert ok is False


# ============================================================ sequencing


async def test_buy_settles_sell_settles_round_trip_closes(drv, session_factory):
    await _seed(session_factory)
    broker = FakeBroker(loss_per_leg=D("1200"))
    settle = SettleSpy(session_factory, broker)
    router = FakeRouter(session_factory, broker)
    driver = _driver(drv, session_factory, broker, router=router, settle=settle)

    plan = await driver.preflight()
    limits = await _limits(session_factory)
    buy = drv.Leg(0, "BUY", CHURN_TICKER, D("10"))
    await driver.run_leg(buy, limits)
    assert broker.positions[CHURN_TICKER] == D("10")

    sell = drv.Leg(1, "SELL", CHURN_TICKER, D("10"))
    await driver.run_leg(sell, limits)

    assert broker.positions[CHURN_TICKER] == D("0")
    assert len(settle.calls) == 2, "the barrier ran once per leg"
    assert router.submits == 2
    assert broker.positions[PROTECTED_TICKER] == D("19")     # untouched throughout
    assert plan.protected_qty[PROTECTED_TICKER] == "19"


async def test_first_leg_settlement_failure_prevents_a_second_order(drv, session_factory, lib):
    """The contract in one test: no second order while the first is unsettled."""
    await _seed(session_factory)
    broker = FakeBroker(loss_per_leg=D("100"))
    router = FakeRouter(session_factory, broker)
    driver = _driver(drv, session_factory, broker, router=router,
                     settle=SettleSpy(session_factory, broker, fail_on=1))

    await driver.preflight()
    with pytest.raises(lib.CanaryStop) as exc:
        await driver.run()

    assert exc.value.stop_reason == "SETTLEMENT_BARRIER_FAILED"
    assert router.submits == 1, "the driver must not submit a second leg on an unsettled first"


async def test_partial_fill_never_advances_the_driver(drv, session_factory, lib):
    """Broker terminal but only part of the quantity booked: the position is not what the driver
    asked for, so the run stops rather than reasoning about it."""
    await _seed(session_factory)
    broker = FakeBroker()
    router = FakeRouter(session_factory, broker)
    driver = _driver(drv, session_factory, broker, router=router)
    await driver.preflight()

    original = _book_fill

    async def _half(sf, order_id, qty, price):        # book only half the ordered quantity
        await original(sf, order_id, qty / 2, price)

    import tests.risk.test_adr0043_churn_driver as self_mod
    self_mod._book_fill = _half
    try:
        with pytest.raises(lib.CanaryStop) as exc:
            await driver.run_leg(drv.Leg(0, "BUY", CHURN_TICKER, D("10")),
                                 await _limits(session_factory))
    finally:
        self_mod._book_fill = original

    assert exc.value.stop_reason == "CHURN_INVARIANT_VIOLATED"
    assert "not fully filled" in exc.value.detail


async def test_a_rejected_setup_order_stops_the_run(drv, session_factory, lib):
    await _seed(session_factory)
    broker = FakeBroker()
    driver = _driver(drv, session_factory, broker,
                     router=FakeRouter(session_factory, broker, reject=True))
    await driver.preflight()
    with pytest.raises(lib.CanaryStop) as exc:
        await driver.run_leg(drv.Leg(0, "BUY", CHURN_TICKER, D("10")),
                             await _limits(session_factory))
    assert exc.value.stop_reason == "CHURN_LEG_REJECTED"


async def test_flattening_sell_refused_is_a_hard_stop_with_residual_evidence(drv, session_factory,
                                                                            lib):
    """The engine refuses to let the driver close a position it opened. That is reportable state,
    not something to route around."""
    await _seed(session_factory)
    broker = FakeBroker(loss_per_leg=D("3000"))
    router = FakeRouter(session_factory, broker, reject_sides=("SELL",))
    driver = _driver(drv, session_factory, broker, router=router)
    plan = await driver.preflight()
    # Pretend a BUY already settled and left 10 shares open.
    broker.positions[CHURN_TICKER] = D("10")
    await _sync_position(session_factory, CHURN_TICKER, D("10"))

    with pytest.raises(lib.CanaryStop) as exc:
        await driver.finish(plan, CHURN_TICKER, D("10"), round_trips=1)

    assert exc.value.stop_reason == "CHURN_RESIDUAL_POSITION"
    assert "10" in exc.value.detail and "remain open" in exc.value.detail
    assert D(exc.value.diagnostics["residual_local"]) == D("10")
    assert exc.value.diagnostics["underlying"] == "CHURN_LEG_REJECTED"


async def test_mid_loop_flatten_refusal_reports_residual_not_a_generic_reject(drv, session_factory,
                                                                              lib):
    """The closing leg inside the loop is subject to the same handling as the final flatten — a
    refused close must surface as residual exposure, not as an anonymous rejected order."""
    await _seed(session_factory)
    broker = FakeBroker(loss_per_leg=D("100"))
    driver = _driver(drv, session_factory, broker,
                     router=FakeRouter(session_factory, broker, reject_sides=("SELL",)))
    await driver.preflight()
    broker.positions[CHURN_TICKER] = D("10")
    await _sync_position(session_factory, CHURN_TICKER, D("10"))

    with pytest.raises(lib.CanaryStop) as exc:
        await driver.flatten(CHURN_TICKER, D("10"), await _limits(session_factory))
    assert exc.value.stop_reason == "CHURN_RESIDUAL_POSITION"
    assert exc.value.diagnostics["underlying"] == "CHURN_LEG_REJECTED"


async def test_limits_changing_mid_run_stops_the_driver(drv, session_factory, lib):
    await _seed(session_factory)
    broker = FakeBroker()
    driver = _driver(drv, session_factory, broker)
    await driver.preflight()

    from sqlalchemy import text
    async with session_factory() as s:                      # someone edits the cap mid-run
        await s.execute(text("UPDATE risk_limits SET max_daily_loss = 9999 WHERE user_id = 3"))
        await s.commit()

    with pytest.raises(lib.CanaryStop) as exc:
        await driver.run_leg(drv.Leg(0, "BUY", CHURN_TICKER, D("10")),
                             await _limits(session_factory))
    assert "limits changed mid-run" in exc.value.detail


async def test_breaker_tripping_for_a_non_daily_loss_cause_stops_the_driver(drv, session_factory,
                                                                           lib):
    await _seed(session_factory)
    broker = FakeBroker()                                    # no loss: breach not reached
    driver = _driver(drv, session_factory, broker)
    await driver.preflight()

    from sqlalchemy import text
    async with session_factory() as s:
        await s.execute(text(
            "UPDATE accounts SET circuit_breaker_tripped_at = :t WHERE id = 3"),
            {"t": datetime.now(UTC)})
        await s.commit()

    with pytest.raises(lib.CanaryStop) as exc:
        await driver.run_leg(drv.Leg(0, "BUY", CHURN_TICKER, D("10")),
                             await _limits(session_factory))
    assert "circuit breaker" in exc.value.detail


async def test_protected_position_moving_stops_the_driver(drv, session_factory, lib):
    await _seed(session_factory)
    broker = FakeBroker()
    driver = _driver(drv, session_factory, broker)
    await driver.preflight()
    broker.positions[PROTECTED_TICKER] = D("18")             # something touched the protected leg

    with pytest.raises(lib.CanaryStop) as exc:
        await driver.run_leg(drv.Leg(0, "BUY", CHURN_TICKER, D("10")),
                             await _limits(session_factory))
    assert "protected MSFT moved" in exc.value.detail


# ============================================================ bounds


async def test_max_round_trips_without_breach_is_breach_unreachable(drv, session_factory, lib):
    await _seed(session_factory)
    broker = FakeBroker(loss_per_leg=D("0"))                 # churn that never loses anything
    driver = _driver(drv, session_factory, broker,
                     bounds=drv.ChurnBounds(target_loss=D("2000"), max_round_trips=2))
    with pytest.raises(lib.BreachUnreachable, match="BREACH_UNREACHABLE"):
        await driver.run()


async def test_wall_clock_budget_ends_the_run(drv, session_factory, lib):
    await _seed(session_factory)
    broker = FakeBroker(loss_per_leg=D("0"))
    driver = _driver(drv, session_factory, broker,
                     bounds=drv.ChurnBounds(target_loss=D("2000"), max_wall_clock_s=0.0))
    with pytest.raises(lib.BreachUnreachable, match="wall-clock"):
        await driver.run()


async def test_zero_admissible_size_is_breach_unreachable_not_a_bigger_order(drv, session_factory,
                                                                            lib):
    """The account's own limits admit nothing. Sizing up is the forbidden move."""
    await _seed(session_factory)
    broker = FakeBroker(loss_per_leg=D("0"), buying_power=D("0"))
    driver = _driver(drv, session_factory, broker,
                     bounds=drv.ChurnBounds(target_loss=D("2000"), max_setup_notional=D("0")))
    with pytest.raises(lib.BreachUnreachable, match="admit 0 shares"):
        await driver.run()


# ============================================================ governed flat-symbol pricing


def test_evaluate_quote_prices_a_flat_symbol_off_the_ask(drv):
    """A flat setup symbol is priced from a governed quote's ASK (conservative), not from a held
    position — the whole point of Finding 1."""
    q = _quote_at(D("50"))                                    # bid 49.98 / ask 50.00
    pr = drv.evaluate_quote(symbol="IEUS", quote=q, now_ts=_NOW, max_age_s=10,
                            approved_sources=frozenset({drv.APPROVED_QUOTE_SOURCE}))
    assert pr.reference_price == D("50") and pr.ask == D("50") and pr.bid == D("49.98")
    assert pr.source == drv.APPROVED_QUOTE_SOURCE and pr.quote_age_s == 0.0


@pytest.mark.parametrize(("mut", "match"), [
    (lambda q: None, "no governed quote"),                    # unavailable
    (lambda q: {**q, "source": "sketchy-feed"}, "unapproved source"),
    (lambda q: {**q, "bid": "0", "ask": "0"}, "non-positive"),
    (lambda q: {**q, "bid": "50.10", "ask": "50.00"}, "crossed"),
    (lambda q: {**q, "ts": None}, "no timestamp"),
])
def test_evaluate_quote_fails_closed(drv, lib, mut, match):
    base = _quote_at(D("50"))
    with pytest.raises(lib.CanaryRefused, match=match):
        drv.evaluate_quote(symbol="IEUS", quote=mut(base), now_ts=_NOW, max_age_s=10,
                           approved_sources=frozenset({drv.APPROVED_QUOTE_SOURCE}))


def test_evaluate_quote_refuses_a_stale_quote(drv, lib):
    q = _quote_at(D("50"), age_s=30.0)                        # 30s old, allowance 10s
    with pytest.raises(lib.CanaryRefused, match="stale"):
        drv.evaluate_quote(symbol="IEUS", quote=q, now_ts=_NOW, max_age_s=10,
                           approved_sources=frozenset({drv.APPROVED_QUOTE_SOURCE}))


async def test_run_refuses_before_submission_when_quote_missing(drv, session_factory, lib):
    await _seed(session_factory)                             # day_change 0 — not breached
    broker = FakeBroker(loss_per_leg=D("0"))
    router = FakeRouter(session_factory, broker)

    async def _no_quote(_sym):
        return None

    driver = _driver(drv, session_factory, broker, router=router, quote_fn=_no_quote)
    with pytest.raises(lib.CanaryRefused, match="no governed quote"):
        await driver.run()
    assert router.submits == 0, "a missing price must refuse BEFORE any order"


async def test_run_refuses_before_submission_when_quote_stale(drv, session_factory, lib):
    await _seed(session_factory)
    broker = FakeBroker(loss_per_leg=D("0"))
    router = FakeRouter(session_factory, broker)

    async def _stale(_sym):
        return _quote_at(D("50"), age_s=45.0)

    driver = _driver(drv, session_factory, broker, router=router, quote_fn=_stale)
    with pytest.raises(lib.CanaryRefused, match="stale"):
        await driver.run()
    assert router.submits == 0


async def test_run_sizes_and_evidences_quantity_from_the_captured_quote(drv, session_factory,
                                                                        monkeypatch):
    """The BUY quantity and notional are computed from the captured governed price, and the quote is
    recorded in evidence (symbol, source, bid, ask, ts, age, reference, qty, notional)."""
    await _seed(session_factory)
    broker = FakeBroker(loss_per_leg=D("1100"))              # one round trip (2x1100) breaches 2000
    router = FakeRouter(session_factory, broker)
    settle = SettleSpy(session_factory, broker)
    driver = _driver(drv, session_factory, broker, router=router, settle=settle,
                     bounds=drv.ChurnBounds(target_loss=D("2000"), max_round_trips=6))

    real_snapshot = drv.snapshot_state

    async def _snapshot(sf, adapter):
        if broker.day_change <= D("-2000"):
            await _trip_lock(sf)
        return await real_snapshot(sf, adapter)

    monkeypatch.setattr(drv, "snapshot_state", _snapshot)

    outcome = await driver.run()
    assert outcome["ready"] is True, outcome["detail"]

    priced = driver.ev.doc["pricing"]
    assert len(priced) == 1
    p = priced[0]
    # admissible size at ask 50 with the seeded limits (25000 notional ceiling / 50) = 500 shares.
    assert p["reference_price"] == "50" and p["ask"] == "50" and p["bid"] == "49.98"
    assert p["source"] == drv.APPROVED_QUOTE_SOURCE
    assert p["calculated_qty"] == "500" and p["notional"] == "25000.00"
    # the freshness bound that governed the order is frozen in the plan and stamped on the evidence
    assert p["max_quote_age_s"] == 10.0
    assert driver.plan.max_quote_age_s == 10.0 and driver.cp.plan["max_quote_age_s"] == 10.0
    assert broker.positions[PROTECTED_TICKER] == D("19")     # protected untouched by the priced run


# ============================================================ loss measurement is a precondition


async def test_no_order_is_submitted_before_the_baseline_is_proven(drv, session_factory, lib):
    """The validation-host state: no session baseline for the account. The driver's guards are all
    expressed in a measured loss, so with no baseline it has no ruler — and a run with no ruler must
    submit nothing rather than churn to its cap and report a breach it never observed."""
    await _seed(session_factory, baseline=None)
    broker = FakeBroker(loss_per_leg=D("1200"))
    router = FakeRouter(session_factory, broker)
    driver = _driver(drv, session_factory, broker, router=router,
                     bounds=drv.ChurnBounds(target_loss=D("2000")))

    with pytest.raises(lib.LossMeasurementUnavailable) as exc:
        await driver.run()
    assert exc.value.stop_reason == lib.STOP_SESSION_BASELINE_MISSING
    assert router.submits == 0


async def test_a_missing_account_state_row_stops_before_any_order(drv, session_factory, lib):
    from sqlalchemy import text

    await _seed(session_factory)
    async with session_factory() as s:
        await s.execute(text("DELETE FROM accounts_state WHERE account_id = 3"))
        await s.commit()
    broker = FakeBroker(loss_per_leg=D("1200"))
    router = FakeRouter(session_factory, broker)
    driver = _driver(drv, session_factory, broker, router=router,
                     bounds=drv.ChurnBounds(target_loss=D("2000")))

    with pytest.raises(lib.LossMeasurementUnavailable) as exc:
        await driver.run()
    assert exc.value.stop_reason == lib.STOP_ACCOUNT_STATE_ROW_MISSING
    assert router.submits == 0


# ============================================================ overshoot / loop control


async def test_run_raises_overshoot_beyond_the_floor(drv, session_factory, lib):
    """Finding 2: a value beyond target+overshoot must raise CHURN_OVERSHOT — reachable now that the
    check precedes the boundary break — and stop before any order."""
    await _seed(session_factory)                             # floor is -(2000+750) = -2750
    broker = FakeBroker(loss_per_leg=D("0"), equity=BASELINE_EQUITY - D("3000"))
    router = FakeRouter(session_factory, broker)
    driver = _driver(drv, session_factory, broker, router=router,
                     bounds=drv.ChurnBounds(target_loss=D("2000")))
    with pytest.raises(lib.CanaryStop) as exc:
        await driver.run()
    assert exc.value.stop_reason == "CHURN_OVERSHOT"
    assert router.submits == 0


@pytest.mark.parametrize("dc", ["-2000", "-2500", "-2750"])  # at target / between / exactly at floor
async def test_run_stops_successfully_within_the_overshoot_band(drv, session_factory, dc):
    """At the target, between target and floor, and exactly at the floor: a normal terminal break,
    not an overshoot. (Frozen rule: == floor is permitted; only < floor overshoots.)"""
    await _seed(session_factory)
    broker = FakeBroker(loss_per_leg=D("0"), equity=BASELINE_EQUITY + D(dc))
    router = FakeRouter(session_factory, broker)
    driver = _driver(drv, session_factory, broker, router=router,
                     bounds=drv.ChurnBounds(target_loss=D("2000")))
    outcome = await driver.run()                             # returns (does not raise)
    assert router.submits == 0, "broke at the boundary before ordering"
    assert "day_change" in outcome


async def test_run_continues_just_above_target(drv, session_factory, lib):
    """Just short of the boundary the loop must CONTINUE (place an order), not break."""
    await _seed(session_factory)
    broker = FakeBroker(loss_per_leg=D("0"), equity=BASELINE_EQUITY - D("1999"))
    router = FakeRouter(session_factory, broker)
    driver = _driver(drv, session_factory, broker, router=router,
                     bounds=drv.ChurnBounds(target_loss=D("2000"), max_round_trips=1))
    with pytest.raises(lib.BreachUnreachable):               # ordered once, then out of round trips
        await driver.run()
    assert router.submits == 2, "continued past target -> exactly one BUY + one SELL"


# ============================================================ quote-freshness bound (hard-capped)


def test_validated_quote_age_accepts_within_the_ceiling(drv):
    assert drv.validated_quote_age(5.0) == 5.0
    assert drv.validated_quote_age(drv.MAX_PERMITTED_QUOTE_AGE_S) == drv.MAX_PERMITTED_QUOTE_AGE_S


@pytest.mark.parametrize("bad", [
    0.0,                                    # zero
    -1.0,                                   # negative
    float("nan"),                           # NaN
    float("inf"),                           # infinity
    10.0001,                                # just above the hard ceiling
    86400.0,                                # a full day — the operator-loosening case
])
def test_validated_quote_age_refuses_out_of_range_or_non_finite(drv, lib, bad):
    with pytest.raises(lib.CanaryRefused):
        drv.validated_quote_age(bad)


def test_construction_refuses_a_loosened_quote_age(drv, session_factory, lib):
    """An operator cannot widen the freshness bound at construction (e.g. via the env default)."""
    with pytest.raises(lib.CanaryRefused, match="within"):
        _driver(drv, session_factory, FakeBroker(), max_quote_age_s=86400.0)


async def test_a_tighter_quote_age_is_accepted_and_frozen(drv, session_factory):
    await _seed(session_factory)
    driver = _driver(drv, session_factory, FakeBroker(), max_quote_age_s=5.0)
    plan = await driver.preflight()
    assert plan.max_quote_age_s == 5.0
    assert driver.cp.plan["max_quote_age_s"] == 5.0


async def test_a_resumed_run_may_not_change_the_frozen_quote_age(drv, session_factory, lib):
    """The freshness bound is part of the plan: a restart whose config would use a different (even
    valid) bound is refused rather than silently adopting it."""
    await _seed(session_factory)
    first = _driver(drv, session_factory, FakeBroker())          # default bound 10.0, freezes + saves
    await first.preflight()
    assert first.cp.plan["max_quote_age_s"] == 10.0

    # A second invocation resumes the SAME checkpoint file but is configured with a tighter bound.
    resumed = _driver(drv, session_factory, FakeBroker(), max_quote_age_s=5.0)
    assert resumed.cp.plan is not None and resumed.cp.plan["max_quote_age_s"] == 10.0
    with pytest.raises(lib.CanaryStop, match="freshness bound") as exc:
        await resumed.preflight()
    assert exc.value.stop_reason == "CHURN_FRESHNESS_BOUND_CHANGED"


# ============================================================ preflight + re-entry


async def test_preflight_refuses_when_setup_symbols_are_not_flat(drv, session_factory, lib):
    await _seed(session_factory)
    broker = FakeBroker()
    broker.positions[CHURN_TICKER] = D("25")                 # left over from a crashed run
    driver = _driver(drv, session_factory, broker)
    with pytest.raises(lib.CanaryRefused, match="not flat"):
        await driver.preflight()


async def test_preflight_refuses_inside_an_existing_lock(drv, session_factory, lib):
    await _seed(session_factory)
    from sqlalchemy import text
    async with session_factory() as s:
        await s.execute(text(
            "INSERT INTO risk_loss_control_state (account_id, state, state_version, "
            "last_sequence_no, control_version, updated_at) "
            "VALUES (3, 'REDUCTION_ONLY_DAILY_LOSS', 1, 1, 1, :now)"),
            {"now": datetime.now(UTC)})
        await s.commit()
    driver = _driver(drv, session_factory, FakeBroker())
    with pytest.raises(lib.CanaryRefused, match="already in loss-control state"):
        await driver.preflight()


async def test_reentry_rebinds_a_completed_leg_instead_of_repeating_it(drv, session_factory):
    await _seed(session_factory)
    broker = FakeBroker(loss_per_leg=D("100"))
    router = FakeRouter(session_factory, broker)
    driver = _driver(drv, session_factory, broker, router=router)
    await driver.preflight()
    leg = drv.Leg(0, "BUY", CHURN_TICKER, D("10"))
    await driver.run_leg(leg, await _limits(session_factory))
    assert router.submits == 1

    # Re-entry with the same run id: the leg's durable order already exists.
    driver2 = _driver(drv, session_factory, broker, router=router)
    driver2.cp.run_id = driver.cp.run_id
    driver2.plan = driver.plan
    await driver2.run_leg(leg, await _limits(session_factory))
    assert router.submits == 1, "a completed leg must never be re-issued"


async def test_checkpoint_claiming_a_leg_with_no_order_is_not_trusted(drv, session_factory, lib):
    """A checkpoint is a claim; the order is the proof. A claim without proof stops the run."""
    await _seed(session_factory)
    broker = FakeBroker()
    router = FakeRouter(session_factory, broker)
    driver = _driver(drv, session_factory, broker, router=router)
    await driver.preflight()
    driver.cp.record_leg(0, index=0, side="BUY", symbol=CHURN_TICKER, qty="10")  # no order exists

    with pytest.raises(lib.CanaryStop) as exc:
        await driver.run_leg(drv.Leg(0, "BUY", CHURN_TICKER, D("10")),
                             await _limits(session_factory))
    assert exc.value.stop_reason == "CHURN_LEG_UNPROVEN"
    assert router.submits == 0


# ============================================================ end to end


async def test_full_run_establishes_the_lock_and_leaves_setup_flat(drv, session_factory,
                                                                   monkeypatch):
    """The whole loop: churn until the boundary trips, flatten, then prove the end state."""
    await _seed(session_factory)
    broker = FakeBroker(loss_per_leg=D("600"))
    router = FakeRouter(session_factory, broker)
    settle = SettleSpy(session_factory, broker)
    driver = _driver(drv, session_factory, broker, router=router, settle=settle,
                     bounds=drv.ChurnBounds(target_loss=D("2000"), max_round_trips=6))

    # The rig's day_change follows the broker, and the lock trips once the boundary is crossed.
    real_snapshot = drv.snapshot_state

    async def _snapshot(sf, adapter):
        if broker.day_change <= D("-2000"):
            await _trip_lock(sf)
        return await real_snapshot(sf, adapter)

    monkeypatch.setattr(drv, "snapshot_state", _snapshot)

    outcome = await driver.run()

    assert outcome["ready"] is True, outcome["detail"]
    assert broker.positions.get(CHURN_TICKER, D(0)) == D("0")    # setup fully closed
    assert broker.positions[PROTECTED_TICKER] == D("19")         # protected untouched
    assert len(settle.calls) == router.submits, "one barrier call per submitted order"
    assert outcome["loss_control_state"] == "REDUCTION_ONLY_DAILY_LOSS"


async def _trip_lock(sf):
    from sqlalchemy import text
    async with sf() as s:
        existing = (await s.execute(text(
            "SELECT COUNT(*) FROM risk_loss_control_state WHERE account_id = 3"))).scalar()
        if not existing:
            await s.execute(text(
                "INSERT INTO risk_loss_control_state (account_id, state, state_version, "
                "last_sequence_no, control_version, updated_at) "
                "VALUES (3, 'REDUCTION_ONLY_DAILY_LOSS', 1, 1, 1, :now)"),
                {"now": datetime.now(UTC)})
            await s.execute(text(
                "INSERT INTO risk_control_events (account_id, sequence_no, control_type, "
                "from_state, to_state, requested_transition, trip_type, initiator_type, "
                "control_version, created_at) VALUES (3, 1, 'LOSS_CONTROL', 'NORMAL', "
                "'REDUCTION_ONLY_DAILY_LOSS', 'TRIP', 'DAILY_LOSS_BREACH', 'SYSTEM', 1, :now)"),
                {"now": datetime.now(UTC)})
            await s.commit()


async def _limits(session_factory):
    import scripts.adr0043_canary_lib as lib
    return await lib.load_limits(session_factory)
