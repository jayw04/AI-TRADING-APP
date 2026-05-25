from fastapi import APIRouter

from app.api.v1 import (
    account,
    alerts,
    indicators,
    internal,
    market_data,
    orders,
    positions,
    signals,
    strategies,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(account.router)
api_router.include_router(internal.router)
api_router.include_router(orders.router)
api_router.include_router(positions.router)
api_router.include_router(market_data.router)
api_router.include_router(indicators.router)
api_router.include_router(users.router)
api_router.include_router(alerts.router)
api_router.include_router(strategies.router)
api_router.include_router(signals.router)
