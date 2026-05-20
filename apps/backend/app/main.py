import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1 import api_router
from app.config import get_settings
from app.db.session import get_sessionmaker
from app.utils.logging import configure_logging, get_logger


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Trading Workbench Backend",
        version=settings.version,
        docs_url="/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )
        log = get_logger("http")
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("request.error")
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        log.info("request.complete", status=response.status_code, ms=round(elapsed_ms, 2))
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/healthz")
    async def healthz() -> Response:
        db_status = "ok"
        try:
            async with get_sessionmaker()() as session:
                await session.execute(text("SELECT 1"))
        except Exception:
            db_status = "down"

        payload = {"status": "ok" if db_status == "ok" else "degraded",
                   "db": db_status, "version": settings.version}
        status_code = 200 if db_status == "ok" else 503
        return JSONResponse(payload, status_code=status_code)

    app.include_router(api_router)

    return app
