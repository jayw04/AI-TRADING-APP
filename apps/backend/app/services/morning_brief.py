"""MorningBriefService — the scheduled per-user session brief (P5.5 §2).

Reads:
  - The user's trading_profile (watchlist + bias_thresholds) — §1.
  - Latest indicator values via the bar cache + IndicatorComputer (P2 §3) —
    the SAME path /api/v1/indicators uses, so the brief and the charts never
    disagree.
  - The user's Anthropic API key (if configured) — P5 §4 credential store.

Writes:
  - A morning_briefs row (UPSERT per (user, date)).
  - One MORNING_BRIEF_GENERATED audit row per save, carrying the LLM cost
    record when the optional narration ran.

Never submits orders. The brief is information.

This is the platform's first sustained LLM cost surface (P6 Orientation Gap #1);
the cost record in the audit payload gives P6's cost-envelope work real data.
``app/services/morning_brief.py`` is on the no-LLM-in-order-path allowlist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.models.morning_brief import MorningBrief
from app.llm.anthropic_client import create_message
from app.llm.pricing import estimate_cost
from app.security.credential_store import CredentialKind, CredentialStore
from app.services.trading_profile import TradingProfileService
from app.utils.time import today_eastern

logger = structlog.get_logger(__name__)

# Haiku 4.5 — fast + cheap; the brief synthesizes observations, it doesn't need
# Opus reasoning. In the pricing table (app/llm/pricing.py).
_BRIEF_MODEL = "claude-haiku-4-5-20251001"

# Daily bars for swing-bias labeling. 400 calendar days gives EMA50/SMA200
# headroom after weekends/holidays.
_BRIEF_TIMEFRAME = "1Day"
_BRIEF_LOOKBACK = timedelta(days=400)
_BRIEF_INDICATORS = ["RSI14", "EMA20", "EMA50", "VWAP"]


@dataclass
class SymbolObservation:
    symbol: str
    bias: str  # "bullish" | "bearish" | "neutral"
    key_level: float | None = None
    watch_for: str = ""
    indicators: dict[str, Any] = field(default_factory=dict)


@dataclass
class MorningBriefData:
    user_id: int
    brief_date: date
    symbols: list[SymbolObservation]
    overall_note: str
    agent_used: bool
    trigger: str
    generated_at: datetime
    # Not persisted on the row — carried to save() for the audit cost record.
    llm_meta: dict[str, Any] | None = None


class MorningBriefService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        bar_cache: Any = None,
        indicator_computer: Any = None,
    ) -> None:
        self._session = session
        self._bar_cache = bar_cache
        self._indicator_computer = indicator_computer

    # ------------------------ generate / save ------------------------

    async def generate(
        self, user_id: int, *, trigger: str = "manual"
    ) -> MorningBriefData:
        """Build the brief from the user's profile + current indicators. Does
        NOT persist — the caller decides whether to save()."""
        profile = await TradingProfileService(self._session).get(user_id)

        watchlist = profile.watchlist or {}
        do_not_trade = {s.upper() for s in watchlist.get("do_not_trade", [])}
        ordered: list[str] = []
        seen: set[str] = set()
        for tier in ("core", "swing_candidates"):
            for raw in watchlist.get(tier, []):
                sym = str(raw).upper()
                if sym in do_not_trade or sym in seen:
                    continue
                seen.add(sym)
                ordered.append(sym)

        thresholds = profile.bias_thresholds or {}
        observations = [await self._observe_symbol(s, thresholds) for s in ordered]

        overall_note, llm_meta = await self._generate_overall_note(
            user_id, observations, profile.bias_criteria or {}
        )

        return MorningBriefData(
            user_id=user_id,
            brief_date=today_eastern(),
            symbols=observations,
            overall_note=overall_note,
            agent_used=bool(overall_note),
            trigger=trigger,
            generated_at=datetime.now(UTC),
            llm_meta=llm_meta,
        )

    async def save(self, brief: MorningBriefData) -> int:
        """Persist the brief (UPSERT on (user_id, brief_date)) and write one
        MORNING_BRIEF_GENERATED audit row. Single commit."""
        symbols_data = [
            {
                "symbol": o.symbol,
                "bias": o.bias,
                "key_level": o.key_level,
                "watch_for": o.watch_for,
                "indicators": o.indicators,
            }
            for o in brief.symbols
        ]

        row = await self._select(brief.user_id, brief.brief_date)
        if row is None:
            row = MorningBrief(
                user_id=brief.user_id,
                brief_date=brief.brief_date,
                symbols_json=symbols_data,
                overall_note=brief.overall_note,
                agent_used=brief.agent_used,
                trigger=brief.trigger,
                generated_at=brief.generated_at,
            )
            self._session.add(row)
        else:
            row.symbols_json = symbols_data
            row.overall_note = brief.overall_note
            row.agent_used = brief.agent_used
            row.trigger = brief.trigger
            row.generated_at = brief.generated_at
        await self._session.flush()  # populate row.id for the audit target

        payload: dict[str, Any] = {
            "brief_date": brief.brief_date.isoformat(),
            "trigger": brief.trigger,
            "symbol_count": len(brief.symbols),
            "agent_used": brief.agent_used,
        }
        if brief.agent_used and brief.llm_meta:
            payload["llm"] = brief.llm_meta

        AuditLogger.write(
            self._session,
            actor_type=(
                AuditActorType.SYSTEM
                if brief.trigger == "scheduled"
                else AuditActorType.USER
            ),
            actor_id="morning_brief_service",
            action=AuditAction.MORNING_BRIEF_GENERATED,
            target_type="morning_brief",
            target_id=row.id,
            payload=payload,
            user_id=brief.user_id,
        )

        await self._session.commit()
        return row.id

    # ------------------------ reads ------------------------

    async def get(self, user_id: int, brief_date: date) -> MorningBriefData | None:
        row = await self._select(user_id, brief_date)
        return self._to_data(row) if row else None

    async def get_latest(self, user_id: int) -> MorningBriefData | None:
        row = (
            await self._session.execute(
                select(MorningBrief)
                .where(MorningBrief.user_id == user_id)
                .order_by(MorningBrief.brief_date.desc())
                .limit(1)
            )
        ).scalars().first()
        return self._to_data(row) if row else None

    async def get_recent(
        self, user_id: int, limit: int = 7
    ) -> list[MorningBriefData]:
        rows = (
            await self._session.execute(
                select(MorningBrief)
                .where(MorningBrief.user_id == user_id)
                .order_by(MorningBrief.brief_date.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [self._to_data(r) for r in rows]

    # ------------------------ internals ------------------------

    async def _select(self, user_id: int, brief_date: date) -> MorningBrief | None:
        return (
            await self._session.execute(
                select(MorningBrief)
                .where(MorningBrief.user_id == user_id)
                .where(MorningBrief.brief_date == brief_date)
            )
        ).scalars().first()

    async def _observe_symbol(
        self, symbol: str, thresholds: dict[str, Any]
    ) -> SymbolObservation:
        if self._bar_cache is None or self._indicator_computer is None:
            return SymbolObservation(
                symbol=symbol, bias="neutral", watch_for="indicator service unavailable"
            )
        try:
            indicators = await self._fetch_indicators(symbol)
        except Exception as exc:  # noqa: BLE001 - one bad symbol must not fail the brief
            logger.warning(
                "morning_brief_indicator_fetch_failed", symbol=symbol, error=str(exc)
            )
            return SymbolObservation(
                symbol=symbol, bias="neutral", watch_for="indicator fetch failed"
            )

        if not indicators:
            return SymbolObservation(
                symbol=symbol, bias="neutral", watch_for="insufficient data"
            )

        bias = _label_bias(indicators, thresholds)
        return SymbolObservation(
            symbol=symbol,
            bias=bias,
            key_level=_compute_key_level(indicators),
            watch_for=_compose_watch_for(indicators, bias),
            indicators=indicators,
        )

    async def _fetch_indicators(self, symbol: str) -> dict[str, Any]:
        """Latest RSI/EMA20/EMA50/VWAP via the shared bar-cache + computer path
        (mirrors /api/v1/indicators). Returns {} when no bars are cached."""
        end = datetime.now(UTC)
        start = end - _BRIEF_LOOKBACK
        bars = await self._bar_cache.get_bars(
            symbol, _BRIEF_TIMEFRAME, start, end
        )
        if bars is None or bars.empty:
            return {}

        import pandas as pd

        computed = self._indicator_computer.compute(
            bars, names=_BRIEF_INDICATORS, symbol=symbol, timeframe=_BRIEF_TIMEFRAME
        )

        def _last(name: str) -> float | None:
            series = computed.get(name)
            if series is None or getattr(series, "empty", True):
                return None
            val = series.iloc[-1]
            return None if pd.isna(val) else float(val)

        last_close = bars["c"].iloc[-1]
        as_of = bars["t"].iloc[-1]
        return {
            "price": None if pd.isna(last_close) else float(last_close),
            "rsi": _last("RSI14"),
            "ema_20": _last("EMA20"),
            "ema_50": _last("EMA50"),
            "vwap": _last("VWAP"),
            "as_of": pd.Timestamp(as_of).isoformat(),
        }

    async def _generate_overall_note(
        self,
        user_id: int,
        observations: list[SymbolObservation],
        bias_criteria: dict[str, Any],
    ) -> tuple[str, dict[str, Any] | None]:
        """1-2 sentence synthesis via Haiku, if a key is configured. Returns
        (note, llm_meta) — ("", None) when no key or the call fails."""
        if not observations:
            return "", None

        api_key = await CredentialStore(self._session).get(
            user_id, CredentialKind.ANTHROPIC_API_KEY
        )
        if not api_key:
            return "", None

        counts = {
            b: sum(1 for o in observations if o.bias == b)
            for b in ("bullish", "bearish", "neutral")
        }
        lines = "\n".join(
            f"- {o.symbol}: {o.bias} (key {o.key_level}; {o.watch_for})"
            for o in observations
        )
        system = (
            "You are reviewing a trader's watchlist before the session opens. "
            "Write 1-2 concrete, observational sentences about what's notable. "
            "Do NOT recommend trades. Do NOT predict prices. Describe only what "
            "the data shows."
        )
        prompt = (
            f"Bullish criteria: {bias_criteria.get('bullish', '(not specified)')}\n"
            f"Bearish criteria: {bias_criteria.get('bearish', '(not specified)')}\n\n"
            f"Observations:\n{lines}\n\n"
            f"Counts: {counts['bullish']} bullish, {counts['bearish']} bearish, "
            f"{counts['neutral']} neutral."
        )

        try:
            call = await create_message(
                api_key=api_key,
                model=_BRIEF_MODEL,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
        except Exception as exc:  # noqa: BLE001 - narration is best-effort
            logger.warning("morning_brief_agent_call_failed", error=str(exc))
            return "", None

        note = " ".join(
            block.get("text", "")
            for block in call.content_blocks
            if block.get("type") == "text"
        ).strip()
        if not note:
            return "", None

        cost_usd = estimate_cost(_BRIEF_MODEL, call.input_tokens, call.output_tokens)
        meta = {
            "model": _BRIEF_MODEL,
            "input_tokens": call.input_tokens,
            "output_tokens": call.output_tokens,
            "cost_cents": cost_usd * Decimal("100"),
        }
        return note, meta

    @staticmethod
    def _to_data(row: MorningBrief) -> MorningBriefData:
        symbols = [
            SymbolObservation(
                symbol=s["symbol"],
                bias=s["bias"],
                key_level=s.get("key_level"),
                watch_for=s.get("watch_for", ""),
                indicators=s.get("indicators", {}),
            )
            for s in (row.symbols_json or [])
        ]
        return MorningBriefData(
            user_id=row.user_id,
            brief_date=row.brief_date,
            symbols=symbols,
            overall_note=row.overall_note,
            agent_used=row.agent_used,
            trigger=row.trigger,
            generated_at=row.generated_at,
        )


# -------- pure helpers (bias labeling) --------


def _label_bias(indicators: dict[str, Any], thresholds: dict[str, Any]) -> str:
    """Apply the user's bias_thresholds to the indicator snapshot."""
    if not indicators or not thresholds:
        return "neutral"

    def matches(rule_name: str) -> bool:
        rule = thresholds.get(rule_name)
        if not rule:
            return False
        rsi = indicators.get("rsi")
        if "rsi_min" in rule and (rsi is None or rsi < rule["rsi_min"]):
            return False
        if "rsi_max" in rule and (rsi is None or rsi > rule["rsi_max"]):
            return False
        ema_rel = rule.get("ema_relationship")
        ema_20, ema_50 = indicators.get("ema_20"), indicators.get("ema_50")
        if ema_rel:
            if ema_20 is None or ema_50 is None:
                return False
            if ema_rel == "20>50" and not ema_20 > ema_50:
                return False
            if ema_rel == "20<50" and not ema_20 < ema_50:
                return False
        price_vwap = rule.get("price_vs_vwap")
        price, vwap = indicators.get("price"), indicators.get("vwap")
        if price_vwap in ("above", "below"):
            if price is None or vwap is None:
                return False
            if price_vwap == "above" and not price > vwap:
                return False
            if price_vwap == "below" and not price < vwap:
                return False
        return True

    if matches("bullish"):
        return "bullish"
    if matches("bearish"):
        return "bearish"
    return "neutral"


def _compute_key_level(indicators: dict[str, Any]) -> float | None:
    """Best single 'watch this level' number."""
    for name in ("vwap", "ema_20"):
        val = indicators.get(name)
        if val is not None:
            return round(float(val), 2)
    return None


def _compose_watch_for(indicators: dict[str, Any], bias: str) -> str:
    rsi = indicators.get("rsi")
    if rsi is None:
        return ""
    if 45 <= rsi <= 55:
        return f"RSI {rsi:.0f} — near midpoint; watch for a break either way"
    if bias == "bullish" and rsi > 70:
        return f"RSI {rsi:.0f} — overbought; watch for a pullback"
    if bias == "bearish" and rsi < 30:
        return f"RSI {rsi:.0f} — oversold; watch for a bounce"
    if bias == "bullish":
        return f"Holding above key levels; RSI {rsi:.0f}"
    if bias == "bearish":
        return f"Below key levels; RSI {rsi:.0f}"
    return f"Mixed signals; RSI {rsi:.0f}"
