from fastapi import APIRouter

from app.api.v1 import (
    account,
    accounts,
    agent,
    alerts,
    auth,
    backtest_jobs,
    credentials,
    indicators,
    internal,
    market_data,
    opportunities,
    orders,
    positions,
    risk,
    signals,
    strategies,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(credentials.router)
api_router.include_router(account.router)
api_router.include_router(accounts.router)
api_router.include_router(internal.router)
api_router.include_router(orders.router)
api_router.include_router(positions.router)
api_router.include_router(market_data.router)
api_router.include_router(indicators.router)
api_router.include_router(users.router)
api_router.include_router(alerts.router)
api_router.include_router(strategies.router)
api_router.include_router(signals.router)
api_router.include_router(backtest_jobs.router)
api_router.include_router(opportunities.router)
api_router.include_router(agent.router)
# P5 §5: risk router routes are already absolute (/risk-limits, /accounts/{id}/
# risk-state, ...); api_router already carries the /api/v1 prefix, so include
# with no extra prefix (the v0.2 doc's prefix="/api/v1" would double it).
api_router.include_router(risk.router)
