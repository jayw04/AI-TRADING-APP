"""Subsystem-aware ``/healthz`` (P5 §8.2).

Unauthenticated by design — load balancers, monitors, and orchestrators must
probe health without credentials, and the endpoint exposes only status
booleans and counts (no secrets, no data). The 127.0.0.1 binding from P0 keeps
external reachability at the reverse proxy's discretion.

Status levels:
  ``ok``       — every started subsystem is healthy.
  ``degraded`` — trading is impaired but the system can serve traffic
                 (a circuit breaker is tripped). Load balancers should keep
                 a degraded instance in rotation (200).
  ``fail``     — the system cannot serve safely (DB unreachable, master key
                 missing, or a started subsystem is down). 503.

A subsystem that is intentionally not started — i.e. ``alpaca_startup_enabled``
is false (tests, or a diagnostics boot) — reports ``disabled`` and does not
degrade the status. The legacy top-level ``db`` key is preserved for the P0
health probe contract.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text

from app.config import get_settings
from app.db.session import get_sessionmaker

router = APIRouter(tags=["health"])

_BOOT_MONOTONIC = time.monotonic()


@router.get("/healthz")
async def healthz(request: Request) -> JSONResponse:
    settings = get_settings()
    checks: dict[str, str] = {}
    overall = "ok"

    def _fail(key: str, detail: str) -> None:
        nonlocal overall
        checks[key] = detail
        overall = "fail"

    def _degrade(key: str, detail: str) -> None:
        nonlocal overall
        checks[key] = detail
        if overall == "ok":
            overall = "degraded"

    # 1. Database connectivity.
    db_ok = True
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - health check must not raise
        db_ok = False
        _fail("database", f"fail: {exc.__class__.__name__}")

    # 2. Master key loaded (Fernet store is unusable without it).
    try:
        from app.security import verify_master_key

        verify_master_key()
        checks["master_key"] = "ok"
    except Exception:  # noqa: BLE001
        _fail("master_key", "fail")

    # 3. Broker registry — only meaningful when the broker subsystem started.
    if not settings.alpaca_startup_enabled:
        checks["broker_registry"] = "disabled"
    else:
        registry = getattr(request.app.state, "broker_registry", None)
        if registry is None:
            _fail("broker_registry", "fail: not initialized")
        else:
            adapter_count = len(getattr(registry, "_adapters", {}))
            acc_count = 0
            if db_ok:
                try:
                    async with get_sessionmaker()() as session:
                        from app.db.models.account import Account

                        acc_count = (
                            await session.execute(select(func.count(Account.id)))
                        ).scalar() or 0
                except Exception:  # noqa: BLE001
                    acc_count = 0
            if acc_count == 0:
                checks["broker_registry"] = "no_accounts"
            elif adapter_count == 0:
                _fail("broker_registry", "fail: accounts exist but no adapters")
            else:
                checks["broker_registry"] = "ok"

    # 4. Background scheduler.
    if not settings.alpaca_startup_enabled:
        checks["scheduler"] = "disabled"
    else:
        scheduler = getattr(request.app.state, "scheduler", None)
        underlying = getattr(scheduler, "scheduler", None)
        if underlying is not None and getattr(underlying, "running", False):
            checks["scheduler"] = "ok"
        else:
            _fail("scheduler", "fail: not running")

    # 5. Circuit breakers — tripped ⇒ degraded (not fail). Never fails the probe.
    if db_ok:
        try:
            async with get_sessionmaker()() as session:
                from app.db.models.account import Account

                tripped = (
                    await session.execute(
                        select(func.count(Account.id)).where(
                            Account.circuit_breaker_tripped_at.isnot(None)
                        )
                    )
                ).scalar() or 0
            if tripped > 0:
                _degrade("circuit_breakers_clear", f"degraded: {tripped} tripped")
            else:
                checks["circuit_breakers_clear"] = "ok"
        except Exception:  # noqa: BLE001
            checks["circuit_breakers_clear"] = "unknown"
    else:
        checks["circuit_breakers_clear"] = "unknown"

    body = {
        "status": overall,
        # Legacy P0 key, preserved for the existing health probe contract.
        "db": "ok" if db_ok else "down",
        "checks": checks,
        "version": settings.version,
        "uptime_seconds": int(time.monotonic() - _BOOT_MONOTONIC),
    }
    return JSONResponse(body, status_code=503 if overall == "fail" else 200)
