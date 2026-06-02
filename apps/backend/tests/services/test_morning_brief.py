"""MorningBriefService tests (P5.5 §2).

Pure bias helpers are tested directly; the indicator path is exercised with a
fake bar cache + the real IndicatorComputer; the LLM narration is tested with a
monkeypatched ``create_message`` (no network) plus a stored credential.
"""
import json
from datetime import UTC, datetime

import pandas as pd
import pytest
from sqlalchemy import func, select

from app.db.models.audit_log import AuditLog
from app.db.models.morning_brief import MorningBrief
from app.db.models.user import User
from app.indicators import IndicatorComputer
from app.security.credential_store import CredentialKind, CredentialStore
from app.services.morning_brief import (
    MorningBriefService,
    _compose_watch_for,
    _compute_key_level,
    _label_bias,
)
from app.services.trading_profile import TradingProfileService

# ---------------- fakes ----------------


class FakeBarCache:
    """get_bars returns a fixed ascending-close frame for any symbol."""

    def __init__(self, n: int = 60, empty: bool = False) -> None:
        self._n = n
        self._empty = empty

    async def get_bars(self, symbol, timeframe, start, end) -> pd.DataFrame:
        if self._empty:
            return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])
        t = pd.date_range("2025-01-01", periods=self._n, freq="D", tz="UTC")
        c = pd.Series(range(100, 100 + self._n), dtype="float64")
        return pd.DataFrame(
            {"t": t, "o": c, "h": c + 1, "l": c - 1, "c": c, "v": [1000.0] * self._n}
        )


class FakeCall:
    def __init__(self, text: str, in_tok: int, out_tok: int) -> None:
        self.content_blocks = [{"type": "text", "text": text}]
        self.input_tokens = in_tok
        self.output_tokens = out_tok


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="t@local"))
        session.add(User(id=2, email="u@local"))
        await session.commit()
    return session_factory


async def _set_watchlist(session_factory, user_id, watchlist) -> None:
    async with session_factory() as session:
        await TradingProfileService(session).update(
            user_id, changes={"watchlist_json": watchlist}, actor_user_id=user_id
        )


async def _audit_rows(session_factory) -> list[AuditLog]:
    async with session_factory() as session:
        return list(
            (await session.execute(select(AuditLog).order_by(AuditLog.id))).scalars()
        )


# ---------------- pure helpers ----------------


def test_label_bias_bullish_when_all_rules_met():
    ind = {"rsi": 60, "ema_20": 11, "ema_50": 10, "price": 5, "vwap": 4}
    th = {"bullish": {"rsi_min": 50, "ema_relationship": "20>50", "price_vs_vwap": "above"}}
    assert _label_bias(ind, th) == "bullish"


def test_label_bias_bearish():
    ind = {"rsi": 40, "ema_20": 9, "ema_50": 10, "price": 3, "vwap": 4}
    th = {"bearish": {"rsi_max": 50, "ema_relationship": "20<50", "price_vs_vwap": "below"}}
    assert _label_bias(ind, th) == "bearish"


def test_label_bias_neutral_when_no_rule_matches():
    ind = {"rsi": 50, "ema_20": 10, "ema_50": 10, "price": 5, "vwap": 5}
    th = {"bullish": {"rsi_min": 70}}
    assert _label_bias(ind, th) == "neutral"


def test_label_bias_missing_indicator_fails_rule():
    ind = {"rsi": None, "ema_20": 11, "ema_50": 10}
    th = {"bullish": {"rsi_min": 50}}
    assert _label_bias(ind, th) == "neutral"


def test_label_bias_no_thresholds_is_neutral():
    assert _label_bias({"rsi": 99}, {}) == "neutral"


def test_compute_key_level_prefers_vwap():
    assert _compute_key_level({"vwap": 1.234, "ema_20": 9}) == 1.23


def test_compute_key_level_falls_back_to_ema20():
    assert _compute_key_level({"vwap": None, "ema_20": 9.876}) == 9.88


def test_compute_key_level_none():
    assert _compute_key_level({}) is None


def test_compose_watch_for_midpoint():
    assert "midpoint" in _compose_watch_for({"rsi": 50}, "neutral")


# ---------------- generate / collection ----------------


async def test_generate_empty_watchlist_returns_no_symbols(seeded):
    async with seeded() as session:
        brief = await MorningBriefService(session=session).generate(1)
    assert brief.symbols == []
    assert brief.agent_used is False


async def test_generate_dedups_and_excludes_do_not_trade(seeded):
    await _set_watchlist(
        seeded,
        1,
        {"core": ["AAPL", "MSFT"], "swing_candidates": ["AAPL", "NVDA"], "do_not_trade": ["MSFT"]},
    )
    async with seeded() as session:
        brief = await MorningBriefService(session=session).generate(1)
    assert [o.symbol for o in brief.symbols] == ["AAPL", "NVDA"]


async def test_generate_uptrend_labels_bullish(seeded):
    await _set_watchlist(seeded, 1, {"core": ["AAPL"]})
    async with seeded() as session:
        await TradingProfileService(session).update(
            1,
            changes={"bias_thresholds_json": {"bullish": {"rsi_min": 50, "ema_relationship": "20>50"}}},
            actor_user_id=1,
        )
    async with seeded() as session:
        svc = MorningBriefService(
            session=session, bar_cache=FakeBarCache(), indicator_computer=IndicatorComputer()
        )
        brief = await svc.generate(1)
    assert len(brief.symbols) == 1
    obs = brief.symbols[0]
    assert obs.bias == "bullish"
    assert obs.indicators.get("ema_20") is not None


async def test_generate_no_bar_cache_marks_unavailable(seeded):
    await _set_watchlist(seeded, 1, {"core": ["AAPL"]})
    async with seeded() as session:
        brief = await MorningBriefService(session=session).generate(1)
    assert brief.symbols[0].bias == "neutral"
    assert "unavailable" in brief.symbols[0].watch_for


# ---------------- save / read ----------------


async def test_save_creates_row_and_audits(seeded):
    async with seeded() as session:
        svc = MorningBriefService(session=session)
        brief = await svc.generate(1, trigger="scheduled")
        await svc.save(brief)
    async with seeded() as session:
        count = (
            await session.execute(select(func.count()).select_from(MorningBrief))
        ).scalar_one()
    assert count == 1
    rows = await _audit_rows(seeded)
    assert len(rows) == 1
    assert rows[0].action == "MORNING_BRIEF_GENERATED"
    assert rows[0].actor_type == "system"  # scheduled trigger
    payload = json.loads(rows[0].payload_json)
    assert payload["trigger"] == "scheduled"
    assert payload["agent_used"] is False


async def test_save_replaces_same_date(seeded):
    await _set_watchlist(seeded, 1, {"core": ["AAPL"]})
    for _ in range(2):
        async with seeded() as session:
            svc = MorningBriefService(session=session)
            brief = await svc.generate(1, trigger="manual")
            await svc.save(brief)
    async with seeded() as session:
        count = (
            await session.execute(select(func.count()).select_from(MorningBrief))
        ).scalar_one()
    assert count == 1  # UPSERT on (user, date)
    brief_rows = [
        r for r in await _audit_rows(seeded) if r.action == "MORNING_BRIEF_GENERATED"
    ]
    assert len(brief_rows) == 2  # but two generations audited


async def test_get_returns_none_for_missing(seeded):
    from app.utils.time import today_eastern

    async with seeded() as session:
        assert await MorningBriefService(session=session).get(1, today_eastern()) is None


async def test_get_recent_orders_desc(seeded):
    from datetime import date

    async with seeded() as session:
        svc = MorningBriefService(session=session)
        for d in (date(2026, 6, 1), date(2026, 6, 3), date(2026, 6, 2)):
            from app.services.morning_brief import MorningBriefData

            await svc.save(
                MorningBriefData(
                    user_id=1, brief_date=d, symbols=[], overall_note="",
                    agent_used=False, trigger="manual", generated_at=datetime.now(UTC),
                )
            )
    async with seeded() as session:
        recent = await MorningBriefService(session=session).get_recent(1, limit=2)
    assert [b.brief_date.isoformat() for b in recent] == ["2026-06-03", "2026-06-02"]


# ---------------- narration ----------------


async def test_note_empty_without_key(seeded):
    await _set_watchlist(seeded, 1, {"core": ["AAPL"]})
    async with seeded() as session:
        brief = await MorningBriefService(session=session).generate(1)
    assert brief.overall_note == ""
    assert brief.agent_used is False
    assert brief.llm_meta is None


async def test_note_with_key_sets_agent_used_and_audits_cost(seeded, monkeypatch):
    await _set_watchlist(seeded, 1, {"core": ["AAPL"]})
    async with seeded() as session:
        await CredentialStore(session).set(1, CredentialKind.ANTHROPIC_API_KEY, "sk-test")

    async def _fake_create_message(**kwargs):
        return FakeCall("Two bullish names lead the watchlist.", 120, 18)

    monkeypatch.setattr(
        "app.services.morning_brief.create_message", _fake_create_message
    )

    async with seeded() as session:
        svc = MorningBriefService(session=session)
        brief = await svc.generate(1)
        assert brief.agent_used is True
        assert "bullish" in brief.overall_note
        assert brief.llm_meta["input_tokens"] == 120
        await svc.save(brief)

    rows = await _audit_rows(seeded)
    # CredentialStore.set wrote a CREDENTIAL audit row; the brief added one more.
    brief_rows = [r for r in rows if r.action == "MORNING_BRIEF_GENERATED"]
    assert len(brief_rows) == 1
    payload = json.loads(brief_rows[0].payload_json)
    assert payload["agent_used"] is True
    assert payload["llm"]["model"].startswith("claude-haiku")
    assert payload["llm"]["output_tokens"] == 18
    assert "cost_cents" in payload["llm"]
