"""§9A.3 market-session gate in the RiskEngine (defense in depth).

The engine consults a ``MarketSession`` before the per-order checks and fails
closed: it rejects with ``MARKET_SESSION_CLOSED`` when the order is not
permitted to trade in the current session. These tests inject an explicit
``MarketSession`` stub so the gate is exercised independently of the wall clock
(the suite-wide ``_market_open`` autouse fixture pins the *default* session to
REGULAR for every other test).
"""

from datetime import UTC, datetime
from decimal import Decimal

from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.market.session import MarketSessionType, SessionInfo
from app.risk.engine import RiskEngine
from app.risk.reason_codes import ReasonCode
from app.risk.types import OrderRequest

_AS_OF = datetime(2026, 6, 17, 15, 0, tzinfo=UTC)


def _info(session: MarketSessionType) -> SessionInfo:
    return SessionInfo(
        session=session,
        as_of=_AS_OF,
        is_trading_day=session is not MarketSessionType.CLOSED,
        is_half_day=False,
        regular_open=None,
        regular_close=None,
    )


class _FixedSession:
    """Classifies every instant as one fixed session."""

    def __init__(self, session: MarketSessionType) -> None:
        self._info = _info(session)

    def classify(self, instant: datetime | None = None) -> SessionInfo:
        return self._info


class _RaisingSession:
    """Calendar lookup blows up — the gate must fail closed."""

    def classify(self, instant: datetime | None = None) -> SessionInfo:
        raise RuntimeError("calendar unavailable")


def _req(**overrides) -> OrderRequest:
    base = dict(
        user_id=1,
        account_id=1,
        symbol_ticker="AAPL",
        side=OrderSide.BUY,
        qty=Decimal("10"),
        type=OrderType.MARKET,
        tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,
    )
    base.update(overrides)
    return OrderRequest(**base)


async def test_closed_session_rejects(session_factory) -> None:
    eng = RiskEngine(
        session_factory, market_session=_FixedSession(MarketSessionType.CLOSED)
    )
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert not out.passed
    assert out.reason_codes == [ReasonCode.MARKET_SESSION_CLOSED]


async def test_premarket_without_extended_rejects(session_factory) -> None:
    eng = RiskEngine(
        session_factory, market_session=_FixedSession(MarketSessionType.PRE_MARKET)
    )
    out = await eng.evaluate(_req(extended_hours=False), trading_mode="paper")
    assert not out.passed
    assert ReasonCode.MARKET_SESSION_CLOSED in out.reason_codes


async def test_afterhours_without_extended_rejects(session_factory) -> None:
    eng = RiskEngine(
        session_factory, market_session=_FixedSession(MarketSessionType.AFTER_HOURS)
    )
    out = await eng.evaluate(_req(extended_hours=False), trading_mode="paper")
    assert not out.passed
    assert ReasonCode.MARKET_SESSION_CLOSED in out.reason_codes


async def test_premarket_with_extended_passes_gate(session_factory) -> None:
    """Opting into extended hours clears the gate; the order then fails on the
    next check (no account seeded → MODE_MISMATCH), not on the session."""
    eng = RiskEngine(
        session_factory, market_session=_FixedSession(MarketSessionType.PRE_MARKET)
    )
    out = await eng.evaluate(_req(extended_hours=True), trading_mode="paper")
    assert ReasonCode.MARKET_SESSION_CLOSED not in out.reason_codes


async def test_regular_session_passes_gate(session_factory) -> None:
    eng = RiskEngine(
        session_factory, market_session=_FixedSession(MarketSessionType.REGULAR)
    )
    out = await eng.evaluate(_req(extended_hours=False), trading_mode="paper")
    assert ReasonCode.MARKET_SESSION_CLOSED not in out.reason_codes


async def test_classification_failure_fails_closed(session_factory) -> None:
    eng = RiskEngine(session_factory, market_session=_RaisingSession())
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert not out.passed
    assert out.reason_codes == [ReasonCode.MARKET_SESSION_CLOSED]


async def test_gate_precedes_input_validation(session_factory) -> None:
    """The session gate is a global trading-permission gate: a closed market is
    reported before per-order shape errors (a malformed order at 3am gets
    MARKET_SESSION_CLOSED, not INVALID_INPUT)."""
    eng = RiskEngine(
        session_factory, market_session=_FixedSession(MarketSessionType.CLOSED)
    )
    out = await eng.evaluate(_req(qty=Decimal("-1")), trading_mode="paper")
    assert out.reason_codes == [ReasonCode.MARKET_SESSION_CLOSED]
