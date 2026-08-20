"""OpportunityInputAdapter — load governed inputs, run the engine, persist a snapshot.

Fail-closed: a missing/stale SEP store marks OVERSOLD / MOM-NEAR / MOM-CORE
unavailable. GAP is independent (premarket file). Never relaxes gates to fill
the screen. Does not import the order path.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import structlog

from app.factor_data.factors.engine import FactorUnavailable, momentum_scores
from app.factor_data.store import FactorDataStore
from app.factor_data.universe import UniverseUnavailable, universe_asof
from app.research.disc001.engine import (
    FamilyResult,
    WatchlistResult,
    assemble_all,
    screen_gap,
    screen_mom_core,
    screen_mom_near,
    screen_oversold,
)
from app.research.disc001.features import (
    GapRow,
    MomCoreRow,
    SymbolFeatures,
    features_from_series,
)
from app.research.disc001.snapshot import resolve_snapshot_dir, write_snapshot
from app.research.disc001.spec import (
    CANDIDATE_UNIVERSE_N,
    FAMILY_HORIZON,
    LOOKBACK_TRADING_DAYS,
    MOM_CORE_TOP_N,
    MOM_CORE_UNIVERSE_N,
    PRICE_SOURCE_GAP,
    PRICE_SOURCE_SEP,
    SCREEN_ID,
    SCREEN_VERSION,
    SEP_STALE_CALENDAR_DAYS,
    SPY_TICKER,
    UNIVERSE_ID,
    FamilyId,
)

logger = structlog.get_logger(__name__)
_ET = ZoneInfo("America/New_York")


def _unavailable(fid: FamilyId, reason: str) -> FamilyResult:
    if fid is FamilyId.OVERSOLD:
        return screen_oversold(
            (), available=False, unavailable_reason=reason, price_source=PRICE_SOURCE_SEP
        )
    if fid is FamilyId.MOM_NEAR:
        return screen_mom_near(
            (),
            frozenset(),
            available=False,
            unavailable_reason=reason,
            price_source=PRICE_SOURCE_SEP,
        )
    if fid is FamilyId.MOM_CORE:
        return screen_mom_core(
            (), available=False, unavailable_reason=reason, price_source=PRICE_SOURCE_SEP
        )
    return screen_gap((), available=False, unavailable_reason=reason, price_source=PRICE_SOURCE_GAP)


def _sep_stale(as_of: date, today: date) -> str | None:
    if (today - as_of).days > SEP_STALE_CALENDAR_DAYS:
        return f"SEP as-of {as_of.isoformat()}, expected on or after {(today - timedelta(days=SEP_STALE_CALENDAR_DAYS)).isoformat()}"
    return None


def _gap_rows_from_payload(payload: dict[str, Any] | None) -> tuple[GapRow, ...] | None:
    """None → caller should mark GAP unavailable. Empty tuple → valid empty family."""
    if payload is None:
        return None
    raw = payload.get("gappers") or []
    if not isinstance(raw, list):
        return None
    rows: list[GapRow] = []
    for g in raw:
        if not isinstance(g, dict):
            continue
        symbol = str(g.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        headlines = g.get("headlines") or []
        if not isinstance(headlines, list):
            headlines = []
        rows.append(
            GapRow(
                rank=int(g.get("rank") or 0),
                symbol=symbol,
                price=g.get("price"),
                gap_pct=g.get("gap_pct"),
                premarket_volume=g.get("premarket_volume"),
                catalyst=g.get("catalyst"),
                headlines=tuple(str(h) for h in headlines),
            )
        )
    return tuple(rows)


def _load_features(
    store: FactorDataStore, tickers: list[str], as_of: date
) -> tuple[tuple[SymbolFeatures, ...], str | None]:
    if not tickers:
        return (), "empty candidate universe"
    start = as_of - timedelta(days=int(LOOKBACK_TRADING_DAYS * 1.6))
    try:
        prices = store.get_prices_many(tickers, start, as_of, adjusted=True)
        spy = store.get_prices(SPY_TICKER, start, as_of, adjusted=True)
        meta = store.get_ticker_meta(tickers)
        sf1 = store.get_sf1_asof(tickers, as_of)
    except Exception as exc:  # fail closed; do not partial-screen
        logger.warning("disc001_feature_load_failed", error=str(exc))
        return (), f"feature load failed: {type(exc).__name__}"
    if prices.empty:
        return (), "no SEP rows in lookback window"
    spy_closes = (
        spy["close"].to_numpy(dtype=float)
        if spy is not None and not spy.empty
        else np.array([], dtype=float)
    )
    meta_idx = meta.set_index("ticker") if not meta.empty else pd.DataFrame()
    cap_series = sf1["marketcap"] if (not sf1.empty and "marketcap" in sf1.columns) else None
    grouped = prices.groupby("ticker", sort=False)
    out: list[SymbolFeatures] = []
    for ticker, frame in grouped:
        closes = frame["close"].to_numpy(dtype=float)
        volumes = frame["volume"].to_numpy(dtype=float)
        row = meta_idx.loc[ticker] if ticker in meta_idx.index else None
        cap = None
        if cap_series is not None and ticker in cap_series.index:
            val = cap_series.loc[ticker]
            cap = float(val) if pd.notna(val) else None
        out.append(
            features_from_series(
                symbol=str(ticker),
                closes=closes,
                volumes=volumes,
                spy_closes=spy_closes,
                name=None
                if row is None
                else (None if pd.isna(row.get("name")) else str(row.get("name"))),
                sector=None
                if row is None
                else (None if pd.isna(row.get("sector")) else str(row.get("sector"))),
                category=None
                if row is None
                else (None if pd.isna(row.get("category")) else str(row.get("category"))),
                market_cap=cap,
            )
        )
    return tuple(out), None


def _mom_core_rows(
    store: FactorDataStore, as_of: date
) -> tuple[tuple[MomCoreRow, ...], str | None]:
    try:
        scores = momentum_scores(store, as_of, n=MOM_CORE_UNIVERSE_N)
    except (FactorUnavailable, UniverseUnavailable) as exc:
        return (), str(exc)
    except Exception as exc:
        logger.warning("disc001_mom_core_failed", error=str(exc))
        return (), f"MOM-001 rank unavailable: {type(exc).__name__}"
    top = scores.head(MOM_CORE_TOP_N)
    tickers = [str(t) for t in top.index.tolist()]
    meta = store.get_ticker_meta(tickers)
    meta_idx = meta.set_index("ticker") if not meta.empty else pd.DataFrame()
    start = as_of - timedelta(days=40)
    prices = store.get_prices_many(tickers, start, as_of, adjusted=True)
    sf1 = store.get_sf1_asof(tickers, as_of)
    cap_series = sf1["marketcap"] if (not sf1.empty and "marketcap" in sf1.columns) else None
    last_close = {}
    last_adv: dict[str, float] = {}
    if not prices.empty:
        for ticker, frame in prices.groupby("ticker"):
            closes = frame["close"].to_numpy(dtype=float)
            volumes = frame["volume"].to_numpy(dtype=float)
            if len(closes):
                last_close[str(ticker)] = float(closes[-1])
            if len(closes) >= 20 and len(volumes) >= 20:
                last_adv[str(ticker)] = float(np.median(closes[-20:] * volumes[-20:]))
    rows: list[MomCoreRow] = []
    for i, ticker in enumerate(tickers, start=1):
        row = meta_idx.loc[ticker] if ticker in meta_idx.index else None
        cap = None
        if cap_series is not None and ticker in cap_series.index:
            val = cap_series.loc[ticker]
            cap = float(val) if pd.notna(val) else None
        score = top.loc[ticker, "score"] if "score" in top.columns else None
        rows.append(
            MomCoreRow(
                rank=i,
                symbol=ticker,
                name=None
                if row is None
                else (None if pd.isna(row.get("name")) else str(row.get("name"))),
                sector=None
                if row is None
                else (None if pd.isna(row.get("sector")) else str(row.get("sector"))),
                score=None if score is None or pd.isna(score) else float(score),
                market_cap=cap,
                adv20=last_adv.get(ticker),
                close=last_close.get(ticker),
            )
        )
    return tuple(rows), None


def build_watchlist(
    store: FactorDataStore | None,
    *,
    gappers_payload: dict[str, Any] | None,
    today: date | None = None,
    vix: float | None = None,
) -> WatchlistResult:
    """Run frozen family screens. ``store is None`` → SEP families unavailable."""
    today = today or datetime.now(_ET).date()
    families: dict[FamilyId, FamilyResult] = {}
    as_of_label = today.isoformat()

    gap_rows = _gap_rows_from_payload(gappers_payload)
    if gap_rows is None:
        families[FamilyId.GAP] = _unavailable(
            FamilyId.GAP, "pre-market gappers file missing or unreadable"
        )
    else:
        families[FamilyId.GAP] = screen_gap(
            gap_rows, available=True, unavailable_reason=None, price_source=PRICE_SOURCE_GAP
        )

    if store is None:
        reason = "factor store not provisioned"
        families[FamilyId.OVERSOLD] = _unavailable(FamilyId.OVERSOLD, reason)
        families[FamilyId.MOM_NEAR] = _unavailable(FamilyId.MOM_NEAR, reason)
        families[FamilyId.MOM_CORE] = _unavailable(FamilyId.MOM_CORE, reason)
        return WatchlistResult(
            families=families,
            all_items=assemble_all(families),
            as_of=as_of_label,
            universe_id=UNIVERSE_ID,
            screen_id=SCREEN_ID,
            screen_version=SCREEN_VERSION,
            vix=vix,
        )

    floor, latest = store.price_date_bounds()
    if latest is None or floor is None:
        reason = "factor store has no SEP price history"
        families[FamilyId.OVERSOLD] = _unavailable(FamilyId.OVERSOLD, reason)
        families[FamilyId.MOM_NEAR] = _unavailable(FamilyId.MOM_NEAR, reason)
        families[FamilyId.MOM_CORE] = _unavailable(FamilyId.MOM_CORE, reason)
        return WatchlistResult(
            families=families,
            all_items=assemble_all(families),
            as_of=as_of_label,
            universe_id=UNIVERSE_ID,
            screen_id=SCREEN_ID,
            screen_version=SCREEN_VERSION,
            vix=vix,
        )

    as_of = latest  # T-1 by design (§7.1 option 1)
    as_of_label = as_of.isoformat()
    stale = _sep_stale(as_of, today)
    if stale:
        families[FamilyId.OVERSOLD] = _unavailable(FamilyId.OVERSOLD, stale)
        families[FamilyId.MOM_NEAR] = _unavailable(FamilyId.MOM_NEAR, stale)
        families[FamilyId.MOM_CORE] = _unavailable(FamilyId.MOM_CORE, stale)
        return WatchlistResult(
            families=families,
            all_items=assemble_all(families),
            as_of=as_of_label,
            universe_id=UNIVERSE_ID,
            screen_id=SCREEN_ID,
            screen_version=SCREEN_VERSION,
            vix=vix,
        )

    mom_rows, mom_reason = _mom_core_rows(store, as_of)
    if mom_reason:
        families[FamilyId.MOM_CORE] = _unavailable(FamilyId.MOM_CORE, mom_reason)
        mom_core_symbols: frozenset[str] = frozenset()
    else:
        families[FamilyId.MOM_CORE] = screen_mom_core(
            mom_rows, available=True, unavailable_reason=None, price_source=PRICE_SOURCE_SEP
        )
        mom_core_symbols = frozenset(r.symbol for r in mom_rows)

    try:
        tickers = universe_asof(store, as_of, n=CANDIDATE_UNIVERSE_N)
    except UniverseUnavailable as exc:
        reason = str(exc)
        families[FamilyId.OVERSOLD] = _unavailable(FamilyId.OVERSOLD, reason)
        families[FamilyId.MOM_NEAR] = _unavailable(FamilyId.MOM_NEAR, reason)
        return WatchlistResult(
            families=families,
            all_items=assemble_all(families),
            as_of=as_of_label,
            universe_id=UNIVERSE_ID,
            screen_id=SCREEN_ID,
            screen_version=SCREEN_VERSION,
            vix=vix,
        )

    features, feat_reason = _load_features(store, tickers, as_of)
    if feat_reason:
        families[FamilyId.OVERSOLD] = _unavailable(FamilyId.OVERSOLD, feat_reason)
        families[FamilyId.MOM_NEAR] = _unavailable(FamilyId.MOM_NEAR, feat_reason)
    else:
        families[FamilyId.OVERSOLD] = screen_oversold(
            features, available=True, unavailable_reason=None, price_source=PRICE_SOURCE_SEP
        )
        families[FamilyId.MOM_NEAR] = screen_mom_near(
            features,
            mom_core_symbols,
            available=True,
            unavailable_reason=None,
            price_source=PRICE_SOURCE_SEP,
        )

    return WatchlistResult(
        families=families,
        all_items=assemble_all(families),
        as_of=as_of_label,
        universe_id=UNIVERSE_ID,
        screen_id=SCREEN_ID,
        screen_version=SCREEN_VERSION,
        vix=vix,
    )


def _card_to_dict(card: Any) -> dict[str, Any]:
    from app.research.disc001.engine import CandidateCard

    assert isinstance(card, CandidateCard)
    return {
        "symbol": card.symbol,
        "family_ids": [str(f) for f in card.family_ids],
        "horizon": card.horizon,
        "status": str(card.status),
        "name": card.name,
        "sector": card.sector,
        "chips": [{"key": c.key, "value": c.value} for c in card.chips],
        "why": card.why,
        "tradability": card.tradability,
        "price_source": card.price_source,
        "close": card.close,
        "market_cap": card.market_cap,
        "adv20": card.adv20,
    }


def watchlist_to_payload(result: WatchlistResult) -> dict[str, Any]:
    families_out: dict[str, Any] = {}
    for fid, fam in result.families.items():
        families_out[str(fid)] = {
            "available": fam.available,
            "unavailable_reason": fam.unavailable_reason,
            "count": len(fam.items),
            "horizon": FAMILY_HORIZON[fid],
            "items": [_card_to_dict(c) for c in fam.items],
        }
    return {
        "as_of": result.as_of,
        "universe_id": result.universe_id,
        "screen_id": result.screen_id,
        "screen_version": result.screen_version,
        "price_source": PRICE_SOURCE_SEP,
        "subtitle": result.subtitle,
        "vix": result.vix,
        "families": families_out,
        "all": {
            "count": len(result.all_items),
            "items": [_card_to_dict(c) for c in result.all_items],
        },
    }


def build_and_persist(
    store: FactorDataStore | None,
    *,
    gappers_payload: dict[str, Any] | None,
    snapshot_dir: str | None = None,
    today: date | None = None,
    vix: float | None = None,
) -> dict[str, Any]:
    result = build_watchlist(store, gappers_payload=gappers_payload, today=today, vix=vix)
    payload = watchlist_to_payload(result)
    directory = resolve_snapshot_dir(snapshot_dir)
    write_snapshot(directory, payload)
    logger.info(
        "disc001_snapshot_written",
        as_of=payload["as_of"],
        oversold=payload["families"].get("OVERSOLD", {}).get("count"),
        mom_near=payload["families"].get("MOM-NEAR", {}).get("count"),
        mom_core=payload["families"].get("MOM-CORE", {}).get("count"),
        gap=payload["families"].get("GAP", {}).get("count"),
    )
    return payload
