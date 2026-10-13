"""GET /api/v1/markets and /api/v1/markets/{market}/* — market-scoped research views.

Contract (read-only, every response names its market, currency and timezone):

* ``GET /markets`` lists the supported markets.
* ``GET /markets/{market}/data-status``: providers, coverage, last update, trading calendar, issues.
* ``GET /markets/{market}/strategies``: research candidates and their status.
* ``GET /markets/{market}/results``: descriptive runs with costs, risk metrics and limitations.

An unknown market id is refused with 404 ``UNSUPPORTED_MARKET``; it is never served as US data. The
US subsystem keeps its existing /api/v1 endpoints, so ``us_equity`` here answers 404
``MARKET_NOT_SCOPED``. The China A-share views read only the separate A-share store, read-only, and
touch no US account, position, scheduler or order path.

Personal use (PU-1): these are the owner's own research views; nothing is published.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
from fastapi import APIRouter, Depends, HTTPException

from app.auth.stub import CurrentUser, get_current_user
from app.config import get_settings
from app.markets.cn_ashare import SCOPE
from app.markets.cn_ashare.research import CANDIDATES
from app.markets.cn_ashare.store import CnAshareStore, StoreRefusal, resolve
from app.markets.context import Market
from app.markets.registry import MARKETS, MarketInfo, UnsupportedMarket, api_ids
from app.markets.registry import resolve as resolve_market
from app.markets.source_classification import get_source

router = APIRouter(prefix="/markets", tags=["markets"])

_PROVIDERS = ("tushare_pro", "baostock")


def scoped_market(market: str) -> MarketInfo:
    try:
        info = resolve_market(market)
    except UnsupportedMarket:
        raise HTTPException(
            status_code=404,
            detail={"code": "UNSUPPORTED_MARKET", "market": market, "supported": api_ids()},
        ) from None
    if not info.scoped_api:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "MARKET_NOT_SCOPED",
                "market": market,
                "message": f"{info.label} views are served by the existing /api/v1 endpoints",
            },
        )
    return info


def _header(info: MarketInfo) -> dict[str, Any]:
    head: dict[str, Any] = info.as_dict()
    if info.market is Market.CN_ASHARE:
        head["scope"] = SCOPE
    return head


def _open_store() -> CnAshareStore | None:
    s = get_settings()
    if not resolve(s.cn_ashare_db_path).is_file():
        return None
    try:
        return CnAshareStore(s.cn_ashare_db_path, s.cn_ashare_cache_dir, read_only=True)
    except (StoreRefusal, duckdb.Error):
        return None


@router.get("")
async def list_markets(_: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return {"markets": [m.as_dict() for m in MARKETS.values()]}


@router.get("/{market}/data-status")
async def data_status(
    info: MarketInfo = Depends(scoped_market), _: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    s = get_settings()
    token = Path(s.cn_ashare_tushare_token_path).expanduser().is_file()
    store = _open_store()
    datasets: list[dict[str, Any]] = []
    stored_issues: list[dict[str, Any]] = []
    calendar: list[dict[str, Any]] = []
    crosscheck = None
    if store is not None:
        with store:
            datasets = store.availability()
            stored_issues = store.issues()
            calendar = store.calendar_summary()
            crosscheck = store.latest_crosscheck()

    seen = {d["provider"] for d in datasets}
    providers = []
    for pid in (*_PROVIDERS, *sorted(seen - set(_PROVIDERS))):
        src = get_source(pid)
        mine = [d for d in datasets if d["provider"] == pid]
        providers.append(
            {
                **asdict(src),
                "credential": ("PRESENT" if token else "ABSENT")
                if pid == "tushare_pro"
                else "NOT_REQUIRED",
                "datasets": mine,
                "last_update_utc": max((d["last_fetch_utc"] for d in mine), default=None),
            }
        )

    issues: list[dict[str, Any]] = []
    if store is None:
        issues.append(
            {
                "severity": "BLOCKER",
                "kind": "NO_STORE",
                "detail": "no A-share data has been ingested",
            }
        )
    if not token:
        issues.append(
            {"severity": "WARNING", "kind": "TUSHARE_TOKEN_ABSENT",
             "detail": "no Tushare token file; the primary provider cannot be queried"}
        )  # fmt: skip
    if datasets and all(d["provider"].startswith("cn_synthetic") for d in datasets):
        issues.append(
            {"severity": "WARNING", "kind": "SYNTHETIC_ONLY",
             "detail": "only synthetic fixtures are stored; no market data yet"}
        )  # fmt: skip
    issues.append(
        {"severity": "WARNING", "kind": "TUSHARE_NO_ST_FLAG",
         "detail": "Tushare daily bars carry no ST flag; limits before 2026-07-06 need an ST history source"}
    )  # fmt: skip
    issues.extend(stored_issues)
    return {
        **_header(info),
        "store": "PRESENT" if store is not None else "NO_STORE",
        "providers": providers,
        "calendar": [
            {k: (v.isoformat() if isinstance(v, date) else v) for k, v in c.items()}
            for c in calendar
        ],
        "crosscheck": crosscheck,
        "issues": issues,
    }


@router.get("/{market}/strategies")
async def strategies(
    info: MarketInfo = Depends(scoped_market), _: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    store = _open_store()
    runs: list[dict[str, Any]] = []
    if store is not None:
        with store:
            runs = store.runs(limit=500)
    out = []
    for c in CANDIDATES.values():
        mine = [r for r in runs if r["candidate_id"] == c.candidate_id]
        last = mine[0] if mine else None
        out.append(
            {
                **asdict(c),
                "run_count": len(mine),
                "last_run": None
                if last is None
                else {
                    "run_id": last["run_id"],
                    "created_at_utc": last["created_at_utc"],
                    "sample_label": last["sample_label"],
                },
            }  # fmt: skip
        )
    return {**_header(info), "candidates": out}


@router.get("/{market}/results")
async def results(
    info: MarketInfo = Depends(scoped_market), _: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    store = _open_store()
    if store is None:
        return {**_header(info), "store": "NO_STORE", "runs": []}
    with store:
        runs = store.runs()
    out = []
    for r in runs:
        rep = r["report"]
        out.append(
            {
                "run_id": r["run_id"],
                "created_at_utc": r["created_at_utc"],
                "candidate_id": r["candidate_id"],
                "sample_label": r["sample_label"],
                "labels": rep.get("labels", []),
                "market_context": r["market_context"],
                "period": rep.get("period"),
                "universe": rep.get("universe"),
                "capital_cny": rep.get("capital_cny"),
                "commission_assumption": rep.get("commission_assumption"),
                "result": rep.get("result", {}),
                "limitations": {
                    "not_modelled": rep.get("not_modelled", []),
                    "accounting": rep.get("accounting", []),
                    "rules": rep.get("rules", []),
                },
            }
        )
    return {**_header(info), "store": "PRESENT", "runs": out}
