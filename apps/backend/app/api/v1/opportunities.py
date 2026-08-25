"""``GET /api/v1/opportunities`` — aggregator for the Opportunities page.

Returns six pre-shaped widget feeds in one round-trip. Each widget has its
own time window (30 min for signals, 60 min for risk rejects, etc.). The
UI does no transforming beyond layout — items are already denormalized
projections with joined names where the page needs them.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.opportunities import (
    OppCandidateWatchlistWidget,
    OppDiscoveryMatchesWidget,
    OppDiscoveryMatchItem,
    OppFillItem,
    OppHistoryCheckpoint,
    OppHistoryOccurrence,
    OppHistoryResponse,
    OppHistoryWhyLeft,
    OppLiveSignalsWidget,
    OppOpenOrderItem,
    OppOpenOrdersExpiringWidget,
    OpportunitiesResponse,
    OppPineAlertsWidget,
    OppPremarketGapperItem,
    OppPremarketGappersWidget,
    OppRecentFillsWidget,
    OppRiskRejectionsWidget,
    OppRiskRejectItem,
    OppSignalItem,
    OppStrategyErrorItem,
    OppStrategyErrorsWidget,
    OppWatchlistFamily,
    OppWatchlistItem,
)
from app.audit import AuditAction
from app.auth.stub import CurrentUser, get_current_user
from app.db.enums import (
    OrderSourceType,
    OrderStatus,
    RiskDecision,
    SignalType,
    StrategyStatus,
    TimeInForce,
)
from app.db.models.audit_log import AuditLog
from app.db.models.fill import Fill
from app.db.models.opportunity_occurrence import OpportunityOccurrence
from app.db.models.order import Order
from app.db.models.risk_check import RiskCheck
from app.db.models.scanner_definition import ScannerDefinition
from app.db.models.scanner_run import TRIGGER_SCHEDULED, ScannerRun
from app.db.models.signal import Signal
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.session import get_session
from app.research.disc001.checkpoints import build_checkpoints, parse_iso_date
from app.research.disc001.spec import PRICE_SOURCE_SEP
from app.research.disc001.why_left import WhyLeft
from app.services.opportunity_history import (
    explain_history_why_left,
    history_price_series,
    parse_reason_json,
)
from app.services.premarket_gappers import read_latest_gappers
from app.utils.time import EASTERN

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


SIGNALS_WINDOW = timedelta(minutes=30)
PINE_ALERTS_WINDOW = timedelta(minutes=30)
RISK_REJECTS_WINDOW = timedelta(minutes=60)
FILLS_WINDOW = timedelta(minutes=15)
DISCOVERY_MATCHES_MAX = 50

SIGNALS_MAX = 25
PINE_ALERTS_MAX = 25
STRATEGY_ERRORS_MAX = 20
OPEN_ORDERS_MAX = 25
RISK_REJECTS_MAX = 25
FILLS_MAX = 25
GAPPERS_MAX = 15

DAY_EXPIRY_MINUTES_BEFORE_CLOSE = 30
GTC_AGE_DAYS_THRESHOLD = 7

OPEN_ORDER_STATUSES = (
    OrderStatus.PENDING_RISK,
    OrderStatus.PENDING_SUBMIT,
    OrderStatus.SUBMITTED,
    OrderStatus.PARTIALLY_FILLED,
)


@router.get("", response_model=OpportunitiesResponse)
async def get_opportunities(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> OpportunitiesResponse:
    now = datetime.now(UTC)

    live_signals = await _fetch_live_signals(session, user_id=current_user.id, now=now)
    pine_alerts = await _fetch_pine_alerts(session, user_id=current_user.id, now=now)
    strategy_errors = await _fetch_strategy_errors(session, user_id=current_user.id)
    open_orders_expiring = await _fetch_open_orders_expiring(
        session, user_id=current_user.id, now=now
    )
    risk_rejections = await _fetch_risk_rejections(session, user_id=current_user.id, now=now)
    recent_fills = await _fetch_recent_fills(session, user_id=current_user.id, now=now)
    discovery_matches = await _fetch_discovery_matches(session, user_id=current_user.id, now=now)
    premarket_gappers = _fetch_premarket_gappers(now=now)
    candidate_watchlist = _fetch_candidate_watchlist(now=now)

    return OpportunitiesResponse(
        live_signals=OppLiveSignalsWidget(items=live_signals, count=len(live_signals), as_of=now),
        pine_alerts=OppPineAlertsWidget(items=pine_alerts, count=len(pine_alerts), as_of=now),
        discovery_matches=OppDiscoveryMatchesWidget(
            items=discovery_matches, count=len(discovery_matches), as_of=now
        ),
        strategy_errors=OppStrategyErrorsWidget(
            items=strategy_errors, count=len(strategy_errors), as_of=now
        ),
        open_orders_expiring=OppOpenOrdersExpiringWidget(
            items=open_orders_expiring,
            count=len(open_orders_expiring),
            as_of=now,
        ),
        risk_rejections=OppRiskRejectionsWidget(
            items=risk_rejections, count=len(risk_rejections), as_of=now
        ),
        recent_fills=OppRecentFillsWidget(items=recent_fills, count=len(recent_fills), as_of=now),
        premarket_gappers=premarket_gappers,
        candidate_watchlist=candidate_watchlist,
        as_of=now,
    )


@router.get("/history", response_model=OppHistoryResponse)
async def get_opportunity_history(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    symbol: str | None = Query(default=None),
    family: str | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    screen_version: str | None = Query(default=None),
    presence: str = Query(default="all", pattern="^(all|current|historical)$"),
    view: str | None = Query(default=None, pattern="^(summary|timeline)$"),
    limit: int = Query(default=200, ge=1, le=500),
) -> OppHistoryResponse:
    """Durable CandidateSnapshot occurrences. Prices, checkpoints, and why-left are read-time only."""
    _ = current_user
    now = datetime.now(UTC)
    stmt = select(OpportunityOccurrence).order_by(
        OpportunityOccurrence.candidate_date.asc(),
        OpportunityOccurrence.family.asc(),
        OpportunityOccurrence.symbol.asc(),
    )
    all_rows = list((await session.execute(stmt)).scalars().all())
    scoped = all_rows
    if screen_version:
        scoped = [row for row in scoped if row.screen_version == screen_version.strip()]
    latest = max((row.candidate_date for row in scoped), default=None)
    last_by_key: dict[tuple[str, str], str] = {}
    for row in scoped:
        key = (row.symbol, row.family)
        prev = last_by_key.get(key)
        if prev is None or row.candidate_date > prev:
            last_by_key[key] = row.candidate_date

    filtered = scoped
    if symbol:
        filtered = [row for row in filtered if row.symbol == symbol.strip().upper()]
    if family:
        filtered = [row for row in filtered if row.family == family.strip()]
    if from_date:
        filtered = [row for row in filtered if row.candidate_date >= from_date.strip()]
    if to_date:
        filtered = [row for row in filtered if row.candidate_date <= to_date.strip()]

    if view == "timeline" or (view is None and symbol):
        items = _history_timeline(filtered, limit=limit)
        view = "timeline"
    else:
        items = _history_summaries(filtered, limit=limit)
        view = "summary"
    marked: list[OppHistoryOccurrence] = []
    for item in items:
        on_watchlist = last_by_key.get((item.symbol, item.family)) == latest
        marked.append(item.model_copy(update={"on_watchlist": on_watchlist}))
    current_count = sum(1 for item in marked if item.on_watchlist)
    historical_count = sum(1 for item in marked if not item.on_watchlist)
    if presence == "current":
        marked = [item for item in marked if item.on_watchlist]
    elif presence == "historical":
        marked = [item for item in marked if not item.on_watchlist]

    series: dict[str, tuple[tuple[date, float], ...]] = {}
    if marked:
        start = min(parse_iso_date(item.candidate_date) for item in marked)
        series = history_price_series([item.symbol for item in marked], start=start)
    why_map = explain_history_why_left(
        [(item.symbol, item.family, item.candidate_date) for item in marked],
        sessions_by_symbol=series,
    )
    enriched = [
        _enrich_history_item(
            item,
            series.get(item.symbol, ()),
            why_map.get((item.symbol, item.family, item.candidate_date)),
        )
        for item in marked
    ]
    return OppHistoryResponse(
        view=view,
        count=len(enriched),
        items=enriched,
        as_of=now,
        latest_candidate_date=latest,
        current_count=current_count,
        historical_count=historical_count,
    )


def _history_summaries(
    rows: list[OpportunityOccurrence], *, limit: int
) -> list[OppHistoryOccurrence]:
    grouped: dict[tuple[str, str], list[OpportunityOccurrence]] = {}
    for row in rows:
        grouped.setdefault((row.symbol, row.family), []).append(row)
    summaries: list[OppHistoryOccurrence] = []
    for _key, group in grouped.items():
        ordered = sorted(group, key=lambda r: r.candidate_date)
        last = ordered[-1]
        first_seen = ordered[0].candidate_date
        last_seen = last.candidate_date
        summaries.append(
            _occurrence_item(last, first_seen=first_seen, last_seen=last_seen, count=len(ordered))
        )
    summaries.sort(key=lambda item: (item.symbol, item.family))
    summaries.sort(key=lambda item: item.last_seen, reverse=True)
    return summaries[:limit]


def _history_timeline(
    rows: list[OpportunityOccurrence], *, limit: int
) -> list[OppHistoryOccurrence]:
    if not rows:
        return []
    dates = [row.candidate_date for row in rows]
    first_seen = min(dates)
    last_seen = max(dates)
    count = len(rows)
    items = [
        _occurrence_item(row, first_seen=first_seen, last_seen=last_seen, count=count)
        for row in rows
    ]
    return items[:limit]


def _occurrence_item(
    row: OpportunityOccurrence,
    *,
    first_seen: str,
    last_seen: str,
    count: int,
) -> OppHistoryOccurrence:
    return OppHistoryOccurrence(
        symbol=row.symbol,
        family=row.family,
        candidate_date=row.candidate_date,
        horizon=row.horizon,
        status_at_proposal=row.status_at_proposal,
        proposal_price=row.proposal_price,
        proposal_price_source=row.proposal_price_source,
        adjustment_basis=row.adjustment_basis,
        reason=parse_reason_json(row.reason_json),
        screen_id=row.screen_id,
        screen_version=row.screen_version,
        snapshot_sha256=row.snapshot_sha256,
        snapshot_generated_at=row.snapshot_generated_at,
        first_seen=first_seen,
        last_seen=last_seen,
        occurrence_count=count,
    )


def _enrich_history_item(
    item: OppHistoryOccurrence,
    sessions: tuple[tuple[date, float], ...],
    why_left: WhyLeft | None = None,
) -> OppHistoryOccurrence:
    facts = build_checkpoints(
        proposal_price=item.proposal_price,
        proposal_basis=item.adjustment_basis,
        proposal_source=item.proposal_price_source,
        candidate_date=parse_iso_date(item.candidate_date),
        sessions=sessions,
        later_source=PRICE_SOURCE_SEP,
        later_basis=PRICE_SOURCE_SEP,
    )
    current = next((fact for fact in facts if fact.checkpoint == "CURRENT"), None)
    checkpoints = [
        OppHistoryCheckpoint(
            checkpoint=fact.checkpoint,
            price=fact.price,
            price_as_of=fact.price_as_of,
            price_source=fact.price_source,
            adjustment_basis=fact.adjustment_basis,
            return_pct=fact.return_pct,
        )
        for fact in facts
    ]
    why_model = None
    if why_left is not None:
        why_model = OppHistoryWhyLeft(
            state=why_left.state,
            as_of=why_left.as_of,
            summary=why_left.summary,
            details=list(why_left.details),
            not_a_signal=why_left.not_a_signal,
        )
    return item.model_copy(
        update={
            "current_price": current.price if current is not None else None,
            "current_price_as_of": current.price_as_of if current is not None else None,
            "current_price_source": current.price_source if current is not None else None,
            "change_pct": current.return_pct if current is not None else None,
            "checkpoints": checkpoints,
            "why_left": why_model,
        }
    )


def _fetch_premarket_gappers(*, now: datetime) -> OppPremarketGappersWidget:
    """Today's pre-market gappers from the external scanner file (read-only).

    Fully fail-soft: any read/parse problem yields an empty, ``stale`` widget so
    a missing or malformed source file can never break the Opportunities page.
    The data is advisory only — it never reaches the order path.
    """
    try:
        payload = read_latest_gappers()
    except Exception:  # defensive: the page must never 500 on this widget
        payload = {"date": None, "scanned_at": None, "gappers": [], "stale": True}

    items: list[OppPremarketGapperItem] = []
    for g in (payload.get("gappers") or [])[:GAPPERS_MAX]:
        if not isinstance(g, dict):
            continue
        try:
            items.append(
                OppPremarketGapperItem(
                    rank=int(g.get("rank") or 0),
                    symbol=str(g.get("symbol") or ""),
                    price=g.get("price"),
                    gap_pct=g.get("gap_pct"),
                    premarket_volume=g.get("premarket_volume"),
                    catalyst=g.get("catalyst"),
                    headlines=list(g.get("headlines") or []),
                )
            )
        except (ValueError, TypeError):
            continue

    return OppPremarketGappersWidget(
        items=items,
        count=len(items),
        as_of=now,
        scanned_at=payload.get("scanned_at"),
        date=payload.get("date"),
        stale=bool(payload.get("stale", True)),
    )


def _fetch_candidate_watchlist(*, now: datetime) -> OppCandidateWatchlistWidget:
    """DISC-001 Band B. Read-only snapshot + live GAP; never the order path."""
    from app.research.disc001.presentation import load_watchlist_widget

    try:
        payload = read_latest_gappers()
    except Exception:
        payload = None
    try:
        widget = load_watchlist_widget(gappers_payload=payload, now=now)
    except Exception:
        widget = {
            "as_of": now,
            "as_of_session": None,
            "universe_id": "SEP-liquid-v0",
            "screen_id": "DISC-001-WATCHLIST",
            "screen_version": "v0.3.0",
            "subtitle": "Watch, not a signal",
            "vix": None,
            "families": {},
            "all_items": [],
            "all_count": 0,
            "stale": True,
        }
    families = {
        fid: OppWatchlistFamily.model_validate(blob)
        for fid, blob in (widget.get("families") or {}).items()
    }
    return OppCandidateWatchlistWidget(
        as_of=widget.get("as_of") or now,
        as_of_session=widget.get("as_of_session"),
        universe_id=str(widget.get("universe_id") or "SEP-liquid-v0"),
        screen_id=str(widget.get("screen_id") or "DISC-001-WATCHLIST"),
        screen_version=str(widget.get("screen_version") or "v0.3.0"),
        subtitle=str(widget.get("subtitle") or "Watch, not a signal"),
        vix=widget.get("vix"),
        families=families,
        all_items=[OppWatchlistItem.model_validate(i) for i in (widget.get("all_items") or [])],
        all_count=int(widget.get("all_count") or 0),
        stale=bool(widget.get("stale", True)),
    )


async def _fetch_discovery_matches(
    session: AsyncSession, *, user_id: int, now: datetime
) -> list[OppDiscoveryMatchItem]:
    """Matches from the user's most recent SCHEDULED scan run today (P8 §4).
    On-demand runs (from the Discovery page) do not surface here."""
    today_start = (
        now.astimezone(EASTERN).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    )
    row = (
        await session.execute(
            select(ScannerRun, ScannerDefinition.name)
            .join(
                ScannerDefinition,
                ScannerRun.scanner_definition_id == ScannerDefinition.id,
            )
            .where(
                ScannerRun.user_id == user_id,
                ScannerRun.trigger == TRIGGER_SCHEDULED,
                ScannerRun.run_at >= today_start,
            )
            .order_by(ScannerRun.run_at.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return []
    run, scan_name = row
    return [
        OppDiscoveryMatchItem(
            symbol=m.get("symbol", ""),
            scan_name=scan_name,
            definition_id=run.scanner_definition_id,
            run_id=run.id,
            values={k: float(v) for k, v in (m.get("values") or {}).items()},
            run_at=run.run_at,
        )
        for m in (run.matched_json or [])[:DISCOVERY_MATCHES_MAX]
    ]


async def _fetch_live_signals(
    session: AsyncSession, *, user_id: int, now: datetime
) -> list[OppSignalItem]:
    cutoff = now - SIGNALS_WINDOW
    stmt = (
        select(Signal, Symbol, StrategyRow)
        .join(Symbol, Signal.symbol_id == Symbol.id)
        .outerjoin(StrategyRow, Signal.strategy_id == StrategyRow.id)
        .where(
            Signal.user_id == user_id,
            Signal.received_at >= cutoff,
            Signal.type != SignalType.PINE_ALERT,
        )
        .order_by(Signal.received_at.desc())
        .limit(SIGNALS_MAX)
    )
    rows = (await session.execute(stmt)).all()
    return [
        OppSignalItem(
            id=sig.id,
            strategy_id=sig.strategy_id,
            strategy_name=strat.name if strat is not None else None,
            symbol=sym.ticker,
            type=sig.type,
            received_at=sig.received_at,
            reason=(sig.payload_json or {}).get("reason"),
            side=(sig.payload_json or {}).get("side"),
        )
        for sig, sym, strat in rows
    ]


async def _fetch_pine_alerts(
    session: AsyncSession, *, user_id: int, now: datetime
) -> list[OppSignalItem]:
    cutoff = now - PINE_ALERTS_WINDOW
    stmt = (
        select(Signal, Symbol, StrategyRow)
        .join(Symbol, Signal.symbol_id == Symbol.id)
        .outerjoin(StrategyRow, Signal.strategy_id == StrategyRow.id)
        .where(
            Signal.user_id == user_id,
            Signal.received_at >= cutoff,
            Signal.type == SignalType.PINE_ALERT,
        )
        .order_by(Signal.received_at.desc())
        .limit(PINE_ALERTS_MAX)
    )
    rows = (await session.execute(stmt)).all()
    return [
        OppSignalItem(
            id=sig.id,
            strategy_id=sig.strategy_id,
            strategy_name=strat.name if strat is not None else None,
            symbol=sym.ticker,
            type=sig.type,
            received_at=sig.received_at,
            reason=(sig.payload_json or {}).get("comment")
            or (sig.payload_json or {}).get("reason"),
            side=(sig.payload_json or {}).get("side"),
        )
        for sig, sym, strat in rows
    ]


async def _fetch_strategy_errors(
    session: AsyncSession, *, user_id: int
) -> list[OppStrategyErrorItem]:
    """Strategies currently in error state. Augment with the timestamp of
    the most recent ``STRATEGY_ERROR`` audit row (its "first noticed").
    """
    stmt = (
        select(StrategyRow)
        .where(
            StrategyRow.user_id == user_id,
            StrategyRow.status == StrategyStatus.ERROR,
        )
        .order_by(StrategyRow.updated_at.desc())
        .limit(STRATEGY_ERRORS_MAX)
    )
    strategies = (await session.execute(stmt)).scalars().all()
    out: list[OppStrategyErrorItem] = []
    for s in strategies:
        latest_audit = (
            (
                await session.execute(
                    select(AuditLog)
                    .where(
                        AuditLog.action == AuditAction.STRATEGY_ERROR.value,
                        AuditLog.target_type == "strategy",
                        AuditLog.target_id == str(s.id),
                    )
                    .order_by(AuditLog.ts.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        first_seen = latest_audit.ts if latest_audit else None

        error_text = (s.error_text or "")[:280]
        out.append(
            OppStrategyErrorItem(
                id=s.id,
                name=s.name,
                version=s.version,
                error_text=error_text,
                error_first_seen=first_seen,
            )
        )
    return out


async def _fetch_open_orders_expiring(
    session: AsyncSession, *, user_id: int, now: datetime
) -> list[OppOpenOrderItem]:
    """Working orders that are close to their TIF deadline.

    Over-fetches up to 200 working orders then filters in Python; the
    "near expiry" check requires a current-time comparison that's awkward
    to express in SQL across SQLite/Postgres.
    """
    stmt = (
        select(Order, Symbol)
        .join(Symbol, Order.symbol_id == Symbol.id)
        .where(
            Order.user_id == user_id,
            Order.status.in_(OPEN_ORDER_STATUSES),
            Order.tif.in_([TimeInForce.DAY, TimeInForce.GTC]),
        )
        .order_by(Order.created_at.desc())
        .limit(200)
    )
    rows = (await session.execute(stmt)).all()

    market_close_today = _market_close_utc_today(now)
    minutes_to_close = (market_close_today - now).total_seconds() / 60.0

    out: list[OppOpenOrderItem] = []
    for order, sym in rows:
        flagged = False
        reason = ""
        if order.tif == TimeInForce.DAY:
            if 0 < minutes_to_close <= DAY_EXPIRY_MINUTES_BEFORE_CLOSE:
                flagged = True
                reason = f"DAY expires in {int(minutes_to_close)} min"
        elif order.tif == TimeInForce.GTC:
            created_at = order.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            age_days = (now - created_at).days
            if age_days >= GTC_AGE_DAYS_THRESHOLD:
                flagged = True
                reason = f"GTC age {age_days} days"

        if flagged:
            out.append(
                OppOpenOrderItem(
                    id=order.id,
                    symbol=sym.ticker,
                    side=order.side,
                    type=order.type,
                    tif=order.tif,
                    qty=order.qty,
                    limit_price=order.limit_price,
                    status=order.status,
                    created_at=order.created_at,
                    expiry_reason=reason,
                )
            )
        if len(out) >= OPEN_ORDERS_MAX:
            break

    return out


async def _fetch_risk_rejections(
    session: AsyncSession, *, user_id: int, now: datetime
) -> list[OppRiskRejectItem]:
    """Recent ``RiskCheck`` rejections.

    ``RiskCheck`` has no ``user_id`` column — scope through the linked
    ``Order`` for rows that have one. Rejects without an order (defensive
    pre-checks) are surfaced for the dev user (id=1) only; in production
    every reject should have an order_id, so this filter is a safety net.
    """
    cutoff = now - RISK_REJECTS_WINDOW
    stmt = (
        select(RiskCheck, Order, Symbol)
        .outerjoin(Order, RiskCheck.order_id == Order.id)
        .outerjoin(Symbol, Order.symbol_id == Symbol.id)
        .where(
            RiskCheck.decision == RiskDecision.REJECT,
            RiskCheck.evaluated_at >= cutoff,
            (Order.user_id == user_id) | (Order.id.is_(None)),
        )
        .order_by(RiskCheck.evaluated_at.desc())
        .limit(RISK_REJECTS_MAX)
    )
    rows = (await session.execute(stmt)).all()
    return [
        OppRiskRejectItem(
            id=check.id,
            order_id=check.order_id,
            symbol=sym.ticker if sym is not None else None,
            decision=check.decision,
            reason_codes=list(check.reason_codes or []),
            evaluated_at=check.evaluated_at,
        )
        for check, _order, sym in rows
    ]


async def _fetch_recent_fills(
    session: AsyncSession, *, user_id: int, now: datetime
) -> list[OppFillItem]:
    """Recent ``Fill`` rows, scoped via ``Order.user_id``.

    A two-pass strategy-name resolution: fetch fills+orders, then batch-
    resolve strategy names for orders whose ``source_type=='strategy'``.
    Cleaner than casting ``Order.source_id`` to int in the join.
    """
    cutoff = now - FILLS_WINDOW
    stmt = (
        select(Fill, Order, Symbol)
        .join(Order, Fill.order_id == Order.id)
        .join(Symbol, Order.symbol_id == Symbol.id)
        .where(
            Order.user_id == user_id,
            Fill.filled_at >= cutoff,
        )
        .order_by(Fill.filled_at.desc())
        .limit(FILLS_MAX)
    )
    rows = (await session.execute(stmt)).all()

    strategy_ids: set[int] = set()
    for _fill, order, _sym in rows:
        if order.source_type == OrderSourceType.STRATEGY and order.source_id:
            try:
                strategy_ids.add(int(order.source_id))
            except ValueError:
                continue
    names_by_id: dict[int, str] = {}
    if strategy_ids:
        strat_rows = (
            (await session.execute(select(StrategyRow).where(StrategyRow.id.in_(strategy_ids))))
            .scalars()
            .all()
        )
        names_by_id = {s.id: s.name for s in strat_rows}

    out: list[OppFillItem] = []
    for fill, order, sym in rows:
        strat_id: int | None = None
        strat_name: str | None = None
        if order.source_type == OrderSourceType.STRATEGY and order.source_id:
            try:
                sid = int(order.source_id)
                if sid in names_by_id:
                    strat_id = sid
                    strat_name = names_by_id[sid]
            except ValueError:
                pass
        out.append(
            OppFillItem(
                id=fill.id,
                order_id=fill.order_id,
                symbol=sym.ticker,
                side=order.side,
                qty=fill.qty,
                price=fill.price,
                filled_at=fill.filled_at,
                strategy_id=strat_id,
                strategy_name=strat_name,
            )
        )
    return out


def _market_close_utc_today(now: datetime) -> datetime:
    """Today's market close (16:00 ET) in UTC.

    Approximate — does NOT account for half-days, holidays, or DST
    transitions mid-session. Used only to decide if an order is "near
    expiry"; an approximate threshold is fine.
    """
    et = ZoneInfo("America/New_York")
    now_et = now.astimezone(et)
    close_et = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return close_et.astimezone(UTC)
