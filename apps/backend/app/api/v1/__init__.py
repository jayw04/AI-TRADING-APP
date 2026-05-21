from fastapi import APIRouter

from app.api.v1 import account, internal, orders

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(account.router)
api_router.include_router(internal.router)
api_router.include_router(orders.router)
