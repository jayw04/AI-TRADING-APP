"""A SYNCED ``accounts_state`` row for tests whose account is expected to trade normally.

Most fixtures used to seed a user, an account, limits and a symbol — but no ``accounts_state``
row — because nothing consulted one. The daily-loss gate now does: a configured ``max_daily_loss``
with no state row means no baseline, and no baseline means the limit cannot be evaluated, so
risk-increasing orders are refused (``DAILY_LOSS_BASIS_UNAVAILABLE``).

That refusal is the correct production behaviour for an account that has never synced. It is not
what those fixtures meant to describe: in production ``AccountSyncService`` writes this row on its
first poll, and startup now waits for it (``services/account_state_readiness.py``). So a fixture
that models a working account has to say so.

    session.add(synced_account_state(account_id=1))

The default is a measured FLAT day, which keeps every pre-existing assertion about non-daily-loss
gates unchanged. Pass ``day_change`` for a measured breach; to model the unavailable case
deliberately, construct ``AccountState`` directly and leave ``day_change_basis`` at its default.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.db.models.account_state import AccountState
from app.services.day_change_basis import BROKER_LAST_EQUITY

D = Decimal

# Module-level singletons: Decimal() in a default argument trips ruff B008.
_DEFAULT_EQUITY = D("100000")
_DEFAULT_DAY_CHANGE = D("0")
_DEFAULT_CASH = D("100000")
_DEFAULT_BUYING_POWER = D("400000")


def synced_account_state(
    *,
    account_id: int = 1,
    equity: Decimal = _DEFAULT_EQUITY,
    day_change: Decimal = _DEFAULT_DAY_CHANGE,
    cash: Decimal = _DEFAULT_CASH,
    buying_power: Decimal = _DEFAULT_BUYING_POWER,
    basis: str = BROKER_LAST_EQUITY,
    **overrides: object,
) -> AccountState:
    """An ``AccountState`` as ``AccountSyncService`` would write it after a successful poll."""
    fields: dict[str, object] = dict(
        account_id=account_id,
        cash=cash,
        equity=equity,
        last_equity=equity - day_change,
        buying_power=buying_power,
        portfolio_value=equity,
        daytrade_count=0,
        day_change=day_change,
        day_change_pct=D("0"),
        day_change_basis=basis,
        status="ACTIVE",
        raw_payload={},
        updated_at=datetime.now(UTC),
    )
    fields.update(overrides)
    return AccountState(**fields)
