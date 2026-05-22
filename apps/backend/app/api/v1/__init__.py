from fastapi import APIRouter

from app.api.v1 import account, indicators, internal, market_data, orders, positions

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(account.router)
api_router.include_router(internal.router)
api_router.include_router(orders.router)
api_router.include_router(positions.router)
api_router.include_router(market_data.router)
api_router.include_router(indicators.router)
