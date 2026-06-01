"""Prometheus ``/metrics`` endpoint (P5 §8.3).

Unauthenticated, like ``/healthz`` — Prometheus scrapes it. Bound to 127.0.0.1
via the P0 docker-compose binding; scrape from the same host or through a
reverse proxy with an allow-list. The exposition includes strategy/account
counts you don't want to advertise publicly.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.observability.metrics import render

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics() -> Response:
    body, content_type = render()
    return Response(content=body, media_type=content_type)
