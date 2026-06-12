import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.healthz import router as healthz_router
from app.api.metrics import router as metrics_router
from app.api.v1 import api_router
from app.config import get_settings
from app.lifespan import lifespan
from app.utils.logging import configure_logging, get_logger
from app.utils.tls_trust import enable_os_trust_store
from app.ws.gateway import router as ws_router


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    # ADR 0017: verify outbound TLS against the OS trust store before any HTTPS
    # (broker connect, market data, Anthropic) so a TLS-inspecting proxy doesn't
    # break Alpaca/Anthropic. Earliest safe point — no connections made at import.
    enable_os_trust_store()

    app = FastAPI(
        title="Trading Workbench Backend",
        version=settings.version,
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
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

    # P5 §8: subsystem-aware /healthz + Prometheus /metrics, both unauthenticated
    # and outside /api/v1 (orchestrators + scrapers expect stable root paths).
    app.include_router(healthz_router)
    app.include_router(metrics_router)
    app.include_router(api_router)
    app.include_router(ws_router)

    return app
