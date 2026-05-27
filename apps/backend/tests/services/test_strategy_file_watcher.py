"""StrategyFileWatcher: file change → DB mark + bus publish (P4 §4).

The watcher exposes a low-level ``_handle_changes`` + ``_mark_strategies_for_path``
that we drive directly here — bypassing the real ``awatch`` loop. Those
methods are the meaningful logic; the awatch wrapper is just a transport.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from watchfiles import Change

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.account import Account, AccountMode
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.services.strategy_file_watcher import StrategyFileWatcher


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    """Two strategies: one on examples/rsi_meanreversion.py (id=1), one on
    my_other_strategy.py (id=2). Both IDLE so we exercise the
    'mark only matching code_path' branch."""
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(
            Account(
                id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper"
            )
        )
        session.add(
            Symbol(
                id=1, ticker="AAPL", exchange="NASDAQ",
                asset_class="us_equity", name="Apple", active=True,
            )
        )
        session.add(StrategyRow(
            id=1, user_id=1, name="rsi", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.PAPER,
            code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="*/1 * * * *",
            risk_limits_id=None,
            has_pending_reload=False, pending_reload_at=None,
            created_at=_now(), updated_at=_now(),
        ))
        session.add(StrategyRow(
            id=2, user_id=1, name="other", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
            code_path="my_other_strategy.py",
            params_json={}, symbols_json=["AAPL"], schedule="event",
            risk_limits_id=None,
            has_pending_reload=False, pending_reload_at=None,
            created_at=_now(), updated_at=_now(),
        ))
        await session.commit()


@pytest.fixture
def watcher(session_factory, tmp_path):
    bus = MagicMock()
    bus.publish = AsyncMock()
    return StrategyFileWatcher(
        root=tmp_path,
        session_factory=session_factory,
        bus=bus,
    )


# ---------- _mark_strategies_for_path: DB writes + bus events ----------


async def test_mark_only_matches_exact_code_path(watcher, seeded, session_factory):
    """Marking 'examples/rsi_meanreversion.py' flips strategy 1, leaves 2 alone."""
    await watcher._mark_strategies_for_path("examples/rsi_meanreversion.py")

    async with session_factory() as session:
        s1 = await session.get(StrategyRow, 1)
        s2 = await session.get(StrategyRow, 2)
    assert s1.has_pending_reload is True
    assert s1.pending_reload_at is not None
    assert s2.has_pending_reload is False
    assert s2.pending_reload_at is None


async def test_mark_publishes_pending_reload_event(watcher, seeded):
    await watcher._mark_strategies_for_path("examples/rsi_meanreversion.py")
    watcher._bus.publish.assert_called_once()
    topic, payload = watcher._bus.publish.call_args.args
    assert topic == "strategy.pending_reload"
    assert payload["strategy_id"] == 1
    assert payload["code_path"] == "examples/rsi_meanreversion.py"
    assert "detected_at" in payload


async def test_mark_no_match_is_noop(watcher, seeded):
    """Changing a file no strategy references doesn't publish anything."""
    await watcher._mark_strategies_for_path("examples/no_one_imports_me.py")
    watcher._bus.publish.assert_not_called()


async def test_mark_multiple_strategies_with_same_code_path(
    watcher, seeded, session_factory,
):
    """Two strategies pointing at the same file each get their own
    pending flag + bus event."""
    async with session_factory() as session:
        session.add(StrategyRow(
            id=3, user_id=1, name="rsi-v2", version="0.2.0",
            type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
            code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="event",
            risk_limits_id=None,
            has_pending_reload=False, pending_reload_at=None,
            created_at=_now(), updated_at=_now(),
        ))
        await session.commit()

    await watcher._mark_strategies_for_path("examples/rsi_meanreversion.py")

    async with session_factory() as session:
        s1 = await session.get(StrategyRow, 1)
        s3 = await session.get(StrategyRow, 3)
    assert s1.has_pending_reload is True
    assert s3.has_pending_reload is True
    assert watcher._bus.publish.call_count == 2


# ---------- _handle_changes: filter logic ----------


def _abs(root: Path, rel: str) -> str:
    return str((root / rel).resolve())


async def test_handle_changes_marks_modified_py(watcher, seeded):
    # Touch the file so the resolve() path inside the watcher succeeds
    (watcher._root / "examples").mkdir(parents=True, exist_ok=True)
    (watcher._root / "examples" / "rsi_meanreversion.py").write_text("# x\n")

    await watcher._handle_changes(
        {(Change.modified, _abs(watcher._root, "examples/rsi_meanreversion.py"))}
    )
    watcher._bus.publish.assert_called_once()


async def test_handle_changes_ignores_non_python_files(watcher, seeded):
    (watcher._root / "examples").mkdir(parents=True, exist_ok=True)
    (watcher._root / "examples" / "README.md").write_text("md\n")
    await watcher._handle_changes(
        {(Change.modified, _abs(watcher._root, "examples/README.md"))}
    )
    watcher._bus.publish.assert_not_called()


async def test_handle_changes_ignores_pycache(watcher, seeded):
    cache_dir = watcher._root / "examples" / "__pycache__"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "rsi.cpython-312.pyc").write_text("")
    await watcher._handle_changes(
        {(Change.modified, _abs(watcher._root, "examples/__pycache__/rsi.cpython-312.pyc"))}
    )
    watcher._bus.publish.assert_not_called()


async def test_handle_changes_ignores_deleted_events(watcher, seeded):
    """Deletes don't trigger pending-reload — only modifications + adds do."""
    (watcher._root / "examples").mkdir(parents=True, exist_ok=True)
    file_path = watcher._root / "examples" / "rsi_meanreversion.py"
    file_path.write_text("# x\n")
    await watcher._handle_changes(
        {(Change.deleted, _abs(watcher._root, "examples/rsi_meanreversion.py"))}
    )
    watcher._bus.publish.assert_not_called()


async def test_handle_changes_cooldown_blocks_rapid_remarks(watcher, seeded):
    """A burst of save events within COOLDOWN_SECONDS produces one publish."""
    (watcher._root / "examples").mkdir(parents=True, exist_ok=True)
    (watcher._root / "examples" / "rsi_meanreversion.py").write_text("# x\n")
    abs_path = _abs(watcher._root, "examples/rsi_meanreversion.py")

    await watcher._handle_changes({(Change.modified, abs_path)})
    first = watcher._bus.publish.call_count
    # Same path, immediately again — should be cooldown-skipped.
    await watcher._handle_changes({(Change.modified, abs_path)})
    second = watcher._bus.publish.call_count

    assert first == 1
    assert second == 1
