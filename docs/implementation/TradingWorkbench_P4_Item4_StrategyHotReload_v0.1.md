# P4 Item 4 — Strategy Hot-Reload from Filesystem

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-23 |
| Phase | **P4 — Polish & Extend**, Item §4 |
| Predecessor | *TradingWorkbench_P4_Item3_OpportunitiesPage_v0.1.md* (tag `p4-opportunities-page-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | (1) Watch `strategies_user/` for file modifications via `watchfiles`. (2) On modification: detect which registered strategies use the changed file, mark them as having a pending reload (new column on `strategies`), publish a bus event, and surface a banner in the strategy detail UI. (3) New endpoint `POST /api/v1/strategies/{id}/reload` that stops the strategy → re-imports the module → starts it again. (4) **Do not auto-reload.** Auto-reload during market hours while a strategy holds positions is unsafe. Single PR. |
| Estimated wall time | 3–4 hours |
| Stopping point | `git tag p4-strategy-hot-reload-complete` |
| Out of scope | Auto-reload (deliberately not built). Hot-reload of running Python *closures* (we always go through a clean re-import; Python's `importlib.reload` has too many edge cases). Cross-strategy reloads when shared utility modules under `strategies_user/` change — we mark every strategy whose `code_path` is the affected file, not strategies that *import* the affected file. Module-graph dependency tracking is overengineered for MVP. |

---

## Session Goal

After this session:
- The backend has a `StrategyFileWatcher` service. On startup it scans `strategies_user/` and registers a watch via `watchfiles.awatch`. It runs continuously as a background asyncio task.
- When a `.py` file under `strategies_user/` is modified, the watcher:
  1. Queries the DB for strategies whose `code_path` matches the affected file.
  2. Sets `strategies.has_pending_reload = TRUE` and `strategies.pending_reload_at = NOW()` on each match.
  3. Publishes `strategy.pending_reload` on the bus.
- The UI surfaces a yellow banner on the strategy detail page when `has_pending_reload` is true: "The strategy file has changed. Reload to apply." with a Reload button.
- `POST /api/v1/strategies/{id}/reload` (new endpoint):
  1. Stops the strategy (calls `engine.unregister(id, reason="reload")`).
  2. Clears `has_pending_reload`.
  3. Calls `engine.register(id)` again — which re-imports the module from disk.
  4. On import failure, the strategy transitions to ERROR with the import error in `error_text`.
- The banner clears when the reload endpoint succeeds.
- The pending-reload state is **per-strategy**, not per-file. Two strategies pointing at the same file each get their own pending flag.

What does NOT happen this session:
- No auto-reload. The user always clicks Reload.
- No cross-strategy module-graph awareness. Editing a helper file imported by `examples/rsi_meanreversion.py` does NOT mark RSI as pending — only editing the RSI file itself does. Gotcha #4 documents this.
- No hot-swap of in-process Python state. Reload = stop + re-import + start. The strategy's in-process state (`_entry_state` dict, etc.) is discarded; the new instance starts fresh. Gotcha #6 documents the implication.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                                       # clean
git pull origin main
git describe --tags --abbrev=0                   # expect: p4-opportunities-page-complete

# watchfiles in deps
grep -E "^\s*\"watchfiles" apps/backend/pyproject.toml || echo "MISSING: watchfiles"

./scripts/dev.sh &
sleep 30

# Engine boots; reference strategy exists
docker compose logs backend | grep -E "strategy_engine_started"
curl -fs "http://127.0.0.1:8000/api/v1/strategies?limit=1" | jq '.items[0] | {id, name, code_path}'

docker compose down
```

- [ ] On `main`, at `p4-opportunities-page-complete`.
- [ ] `watchfiles` is in `pyproject.toml`. If missing:
  ```bash
  cd apps/backend && uv add watchfiles && cd ../..
  ```

```bash
git checkout -b feat/p4-strategy-hot-reload
```

---

## §4.1 — Schema: `has_pending_reload` + `pending_reload_at` Columns

Two columns on `strategies`. `has_pending_reload` is a boolean for quick filtering; `pending_reload_at` is when the file was detected as changed (used by the UI for "changed 2 minutes ago").

Edit `apps/backend/app/db/models/strategy.py`. Inside the `Strategy` model, append two columns near the other status fields:

```python
has_pending_reload: Mapped[bool] = mapped_column(
    Boolean, nullable=False, default=False, server_default="0",
)
pending_reload_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True,
)
```

> `server_default="0"` is for SQLite compatibility (it stores booleans as 0/1). Without it, existing rows would NULL out on migration and Pydantic deserialization would complain.

Generate migration:

```bash
cd apps/backend
uv run alembic revision --autogenerate -m "P4: strategies.has_pending_reload + pending_reload_at"
```

Open the generated file. Verify:

- [ ] `op.add_column("strategies", sa.Column("has_pending_reload", sa.Boolean(), nullable=False, server_default="0"))`
- [ ] `op.add_column("strategies", sa.Column("pending_reload_at", sa.DateTime(timezone=True), nullable=True))`
- [ ] `downgrade()` drops both columns.

Apply and verify:

```bash
uv run alembic upgrade head
uv run sqlite3 data/workbench.sqlite ".schema strategies" | grep -E "pending"
# Expect: has_pending_reload, pending_reload_at

# Round-trip
uv run alembic downgrade -1
uv run alembic upgrade head
cd ../..
```

- [ ] Migration round-trips clean.

---

## §4.2 — `StrategyFileWatcher` Service

Create `apps/backend/app/services/strategy_file_watcher.py`:

```python
"""StrategyFileWatcher — watches strategies_user/ for file modifications and
marks affected strategies as needing reload.

Design choices:
  - Pure watch + mark. The watcher does NOT trigger an automatic reload.
    Auto-reload during market hours while a strategy holds positions is
    a class of bug we don't want to invent. The user clicks Reload.
  - Per-file granularity. We match `strategies.code_path` exactly against
    the changed file's relative path under strategies_user/. Editing
    examples/rsi_meanreversion.py marks strategies with code_path
    'examples/rsi_meanreversion.py' as pending. Editing a helper file
    imported by RSI does NOT mark RSI as pending — module-graph tracking
    is out of scope (see Gotcha #4 in the session doc).
  - Debouncing. A single 'save' from many editors (VS Code, Vim with
    backup files) produces multiple change events within ~100ms.
    watchfiles already coalesces; we additionally apply a per-file
    cooldown to avoid spamming the bus.

State:
  - _last_marked_at: dict[code_path -> epoch_seconds]. Used for debouncing.

The watcher runs as a long-lived asyncio task started in lifespan. Cancel
on shutdown to release the inotify (or equivalent) file descriptor.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from watchfiles import Change, awatch

from app.db.models.strategy import Strategy as StrategyRow


logger = structlog.get_logger(__name__)


# Per-file cooldown between mark operations. A user saving in a tight
# loop (e.g. autosave on every keystroke) shouldn't generate one bus
# event per stroke.
COOLDOWN_SECONDS = 2.0


class StrategyFileWatcher:
    def __init__(
        self,
        *,
        root: Path,
        session_factory: async_sessionmaker[AsyncSession],
        bus: Any,
    ) -> None:
        self._root = root.resolve()
        self._session_factory = session_factory
        self._bus = bus
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._last_marked_at: dict[str, float] = {}

    async def start(self) -> None:
        if not self._root.exists():
            logger.warning(
                "strategy_file_watcher_root_missing",
                root=str(self._root),
            )
            return
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="strategy_file_watcher")
        logger.info("strategy_file_watcher_started", root=str(self._root))

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except (asyncio.CancelledError, Exception):
                    pass
            self._task = None
            logger.info("strategy_file_watcher_stopped")

    async def _run(self) -> None:
        """Long-lived watch loop. Yields on each batch of changes."""
        try:
            async for changes in awatch(
                str(self._root),
                stop_event=self._stop_event,
                step=300,    # ms debounce window inside watchfiles
                recursive=True,
            ):
                await self._handle_changes(changes)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("strategy_file_watcher_loop_crashed")
            # Don't crash the whole backend — the watcher is non-critical.

    async def _handle_changes(self, changes: set[tuple[Change, str]]) -> None:
        """Process one batch of file-system events."""
        # Filter to `.py` files under strategies_user/, excluding
        # auto-generated artifacts (pycache, .pyc, etc.)
        relevant_paths: set[str] = set()
        for change, path in changes:
            if change not in (Change.modified, Change.added):
                continue
            p = Path(path)
            if p.suffix != ".py":
                continue
            if "__pycache__" in p.parts:
                continue
            if p.name.startswith("."):     # hidden files / editor swap files
                continue
            try:
                rel = p.resolve().relative_to(self._root)
            except ValueError:
                continue
            relevant_paths.add(str(rel))

        if not relevant_paths:
            return

        now = time.time()
        for rel_path in relevant_paths:
            last = self._last_marked_at.get(rel_path, 0.0)
            if now - last < COOLDOWN_SECONDS:
                logger.debug("strategy_file_watcher_cooldown_skip", path=rel_path)
                continue
            self._last_marked_at[rel_path] = now
            await self._mark_strategies_for_path(rel_path)

    async def _mark_strategies_for_path(self, rel_path: str) -> None:
        """Mark every strategy whose code_path == rel_path as pending reload."""
        async with self._session_factory() as session:
            stmt = select(StrategyRow).where(StrategyRow.code_path == rel_path)
            strategies = (await session.execute(stmt)).scalars().all()
            if not strategies:
                logger.debug("strategy_file_watcher_no_match", path=rel_path)
                return
            now = datetime.now(timezone.utc)
            ids: list[int] = []
            for s in strategies:
                s.has_pending_reload = True
                s.pending_reload_at = now
                ids.append(s.id)
            await session.commit()

        # Publish on the bus after commit
        if self._bus is not None:
            for sid in ids:
                try:
                    await self._bus.publish("strategy.pending_reload", {
                        "strategy_id": sid,
                        "code_path": rel_path,
                        "detected_at": now.isoformat(),
                    })
                except Exception:
                    logger.exception("strategy_file_watcher_publish_failed", strategy_id=sid)

        logger.info("strategy_file_watcher_marked",
                    path=rel_path, strategy_count=len(ids), ids=ids)
```

- [ ] `strategy_file_watcher.py` created.

Wire it into the lifespan. Edit `apps/backend/app/lifespan.py`:

```python
from pathlib import Path
from app.services.strategy_file_watcher import StrategyFileWatcher

# After event_bus + session_factory exist, and AFTER the StrategyEngine
# starts (the watcher is independent but ordering helps if you ever add
# inter-service dependencies):
app.state.strategy_file_watcher = StrategyFileWatcher(
    root=Path("strategies_user"),
    session_factory=app.state.session_factory,
    bus=app.state.event_bus,
)
await app.state.strategy_file_watcher.start()
```

And in the shutdown / `lifespan.cleanup()`:

```python
if hasattr(app.state, "strategy_file_watcher"):
    await app.state.strategy_file_watcher.stop()
```

- [ ] Watcher started in lifespan; stopped on shutdown.

---

## §4.3 — WS Topic Wiring

Edit `apps/backend/app/ws/gateway.py`. Add the new bus event to the `bus_to_ws_map`:

```python
bus_to_ws_map = {
    # ... existing entries ...

    # NEW for P4 §4:
    "strategy.pending_reload": "strategies",
}
```

No new topic — `strategies` already exists from P2 Session 4 with a 60-min replay window. The pending-reload event piggybacks. UI on the strategy detail page already subscribes to `strategies`; it just needs to handle the new `msg.type`.

- [ ] `strategy.pending_reload` routes to the `strategies` WS topic.

---

## §4.4 — REST: Reload Endpoint

Edit `apps/backend/app/api/v1/strategies.py`. Add the new endpoint alongside `/start` and `/stop`:

```python
@router.post("/{strategy_id}/reload", response_model=StrategyActionResponse)
async def reload_strategy(
    strategy_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Reload a strategy: stop → re-import → start.

    If the strategy is IDLE, this is the same as 'start with fresh code' (no
    stop step needed; engine.register re-imports anyway). If the strategy is
    PAPER, we stop it first.

    The has_pending_reload flag clears as part of this operation regardless
    of whether the import succeeds — if it fails, the strategy enters ERROR
    and the user fixes the file, which produces a new pending_reload event.
    """
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if row.type != StrategyType.PYTHON:
        raise HTTPException(
            status_code=400,
            detail="Only python strategies are reloadable",
        )

    engine = _get_engine(request)

    was_active = row.status in ACTIVE_STRATEGY_STATUSES
    if was_active:
        try:
            await engine.unregister(strategy_id, reason="reload")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Stop during reload failed: {exc}")

    # Clear the pending flag
    row = await session.get(StrategyRow, strategy_id)
    row.has_pending_reload = False
    row.pending_reload_at = None
    await session.commit()

    # Now re-register (which re-imports the module file)
    new_run_id: Optional[int] = None
    if was_active:
        try:
            running = await engine.register(strategy_id)
            new_run_id = running.run_id
        except Exception as exc:
            # The engine sets status=ERROR on register failure; the user sees it
            raise HTTPException(
                status_code=400,
                detail=f"Reload failed: {exc}",
            )

    # Audit
    await AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(current_user.id),
        action=AuditAction.STRATEGY_UPDATED,
        target_type="strategy",
        target_id=strategy_id,
        payload={"action": "reload", "was_active": was_active},
        user_id=current_user.id,
    )
    await session.commit()

    row = await session.get(StrategyRow, strategy_id)
    return StrategyActionResponse(
        strategy_id=strategy_id,
        action="reload" if "reload" in StrategyActionResponse.__annotations__.get("action", str).__args__ else "start",
        new_status=row.status,
        run_id=new_run_id,
    )
```

The `StrategyActionResponse.action` Literal currently allows `"start" | "stop"`. Extend it. Edit `apps/backend/app/api/v1/schemas/strategies.py`:

```python
class StrategyActionResponse(BaseModel):
    strategy_id: int
    action: Literal["start", "stop", "reload"]    # extended
    new_status: StrategyStatus
    run_id: Optional[int] = None
```

> If you'd rather not extend the Literal, return `"start"` for an active reload and `"stop"` if the strategy was IDLE (no-op). Either works. I prefer the explicit `"reload"` value because it's an audit-readable signal in the UI's action button feedback.

The audit-action enum already has `STRATEGY_UPDATED` from P2 Session 4. Reuse it — we're not introducing a new event type, just a different `payload.action` field.

- [ ] `POST /strategies/{id}/reload` works.
- [ ] `StrategyActionResponse.action` extended with `"reload"`.
- [ ] Pending flag clears as part of the call (idempotent — calling reload when there's nothing pending still works).

---

## §4.5 — Schema Updates

The `StrategyResponse` Pydantic model needs to expose the two new fields. Edit `apps/backend/app/api/v1/schemas/strategies.py`:

```python
class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    version: str
    type: StrategyType
    status: StrategyStatus
    code_path: Optional[str]
    params: dict[str, Any] = Field(alias="params_json")
    symbols: list[str] = Field(alias="symbols_json")
    schedule: str
    risk_limits_id: Optional[int]
    error_text: Optional[str]
    has_pending_reload: bool = False         # NEW
    pending_reload_at: Optional[datetime] = None    # NEW
    created_at: datetime
    updated_at: datetime
```

`from_attributes=True` picks the new columns directly off the ORM row. No other endpoint changes needed.

- [ ] `StrategyResponse` exposes the two new fields.

---

## §4.6 — Backend Tests

Three test files. First the watcher (unit), then the endpoint (integration), then the publish wiring.

### 4.6.1 — Watcher unit tests

Create `apps/backend/tests/services/test_strategy_file_watcher.py`:

```python
"""StrategyFileWatcher: file change → DB mark + bus publish."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.user import User
from app.services.strategy_file_watcher import StrategyFileWatcher


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(StrategyRow(
            id=1, user_id=1, name="rsi", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.PAPER,
            code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="*/1 * * * *",
            risk_limits_id=None, has_pending_reload=False,
            pending_reload_at=None,
            created_at=_now(), updated_at=_now(),
        ))
        session.add(StrategyRow(
            id=2, user_id=1, name="other", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
            code_path="my_other_strategy.py",
            params_json={}, symbols_json=["AAPL"], schedule="event",
            risk_limits_id=None, has_pending_reload=False,
            pending_reload_at=None,
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


@pytest.mark.asyncio
async def test_mark_marks_only_strategies_with_matching_code_path(
    watcher, seeded, session_factory,
):
    """Editing examples/rsi_meanreversion.py marks strategy 1, not strategy 2."""
    await watcher._mark_strategies_for_path("examples/rsi_meanreversion.py")

    async with session_factory() as session:
        s1 = await session.get(StrategyRow, 1)
        s2 = await session.get(StrategyRow, 2)
    assert s1.has_pending_reload is True
    assert s1.pending_reload_at is not None
    assert s2.has_pending_reload is False


@pytest.mark.asyncio
async def test_mark_publishes_pending_reload_event(watcher, seeded):
    await watcher._mark_strategies_for_path("examples/rsi_meanreversion.py")
    watcher._bus.publish.assert_called()
    args = watcher._bus.publish.call_args.args
    assert args[0] == "strategy.pending_reload"
    assert args[1]["strategy_id"] == 1
    assert args[1]["code_path"] == "examples/rsi_meanreversion.py"
    assert "detected_at" in args[1]


@pytest.mark.asyncio
async def test_mark_no_match_is_noop(watcher, seeded, session_factory):
    """Changing a file no strategy references doesn't publish anything."""
    await watcher._mark_strategies_for_path("examples/some_random_file.py")
    watcher._bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_mark_multiple_strategies_with_same_code_path(
    watcher, seeded, session_factory,
):
    """Two strategies pointing at the same file each get marked."""
    async with session_factory() as session:
        session.add(StrategyRow(
            id=3, user_id=1, name="rsi-v2", version="0.2.0",
            type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
            code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="event",
            risk_limits_id=None, has_pending_reload=False,
            pending_reload_at=None,
            created_at=_now(), updated_at=_now(),
        ))
        await session.commit()

    await watcher._mark_strategies_for_path("examples/rsi_meanreversion.py")

    async with session_factory() as session:
        s1 = await session.get(StrategyRow, 1)
        s3 = await session.get(StrategyRow, 3)
    assert s1.has_pending_reload is True
    assert s3.has_pending_reload is True
    # Bus published twice (once per strategy)
    assert watcher._bus.publish.call_count == 2


@pytest.mark.asyncio
async def test_cooldown_prevents_rapid_remarks(watcher, seeded):
    """Two rapid changes to the same file produce only one bus publish."""
    await watcher._handle_changes({(2, "examples/rsi_meanreversion.py")})  # 2 = Change.modified
    # Spy on the publish count
    first_call_count = watcher._bus.publish.call_count

    # Construct the absolute path watchfiles would deliver
    abs_path = str(watcher._root / "examples" / "rsi_meanreversion.py")

    from watchfiles import Change as _Change
    # First batch
    await watcher._handle_changes({(_Change.modified, abs_path)})
    after_first = watcher._bus.publish.call_count
    # Second batch immediately (within cooldown)
    await watcher._handle_changes({(_Change.modified, abs_path)})
    after_second = watcher._bus.publish.call_count

    assert after_second == after_first  # cooldown blocked the second


@pytest.mark.asyncio
async def test_ignores_non_python_files(watcher, seeded):
    from watchfiles import Change as _Change
    abs_path = str(watcher._root / "examples" / "README.md")
    await watcher._handle_changes({(_Change.modified, abs_path)})
    watcher._bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_ignores_pycache_directory(watcher, seeded):
    from watchfiles import Change as _Change
    abs_path = str(watcher._root / "examples" / "__pycache__" / "rsi.cpython-312.pyc")
    await watcher._handle_changes({(_Change.modified, abs_path)})
    watcher._bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_start_then_stop_is_clean(watcher, tmp_path):
    """Lifecycle smoke: watcher starts, can stop, doesn't hang."""
    await watcher.start()
    await watcher.stop()
    assert watcher._task is None
```

### 4.6.2 — Reload endpoint tests

Edit `apps/backend/tests/api/test_strategies_endpoint.py`. Append:

```python
@pytest.mark.asyncio
async def test_reload_endpoint_calls_unregister_then_register(client, session_factory):
    """Reload an active strategy: should call unregister then register."""
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1, name="reloadable", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.PAPER,
            code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="*/1 * * * *",
            risk_limits_id=None, has_pending_reload=True,
            pending_reload_at=_now(),
            created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    unregister_calls = []
    register_calls = []

    async def fake_unregister(strategy_id, reason=None):
        unregister_calls.append((strategy_id, reason))
        async with session_factory() as s:
            r = await s.get(StrategyRow, strategy_id)
            r.status = StrategyStatus.IDLE
            await s.commit()

    async def fake_register(strategy_id):
        register_calls.append(strategy_id)
        async with session_factory() as s:
            r = await s.get(StrategyRow, strategy_id)
            r.status = StrategyStatus.PAPER
            await s.commit()
        result = MagicMock()
        result.run_id = 99
        return result

    client._transport.app.state.strategy_engine.unregister = fake_unregister
    client._transport.app.state.strategy_engine.register = fake_register

    resp = await client.post(f"/api/v1/strategies/{sid}/reload")
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "reload"
    assert body["new_status"] == "paper"
    assert body["run_id"] == 99

    assert len(unregister_calls) == 1
    assert unregister_calls[0] == (sid, "reload")
    assert len(register_calls) == 1
    assert register_calls[0] == sid

    # Pending flag cleared
    async with session_factory() as session:
        row = await session.get(StrategyRow, sid)
    assert row.has_pending_reload is False
    assert row.pending_reload_at is None


@pytest.mark.asyncio
async def test_reload_idle_strategy_does_not_unregister(client, session_factory):
    """If the strategy is IDLE, reload doesn't call unregister."""
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1, name="idle-reloadable", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
            code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="*/1 * * * *",
            risk_limits_id=None, has_pending_reload=True,
            pending_reload_at=_now(),
            created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    unregister_count = 0
    register_count = 0

    async def fake_unregister(strategy_id, reason=None):
        nonlocal unregister_count
        unregister_count += 1

    async def fake_register(strategy_id):
        nonlocal register_count
        register_count += 1
        result = MagicMock()
        result.run_id = 1
        return result

    client._transport.app.state.strategy_engine.unregister = fake_unregister
    client._transport.app.state.strategy_engine.register = fake_register

    resp = await client.post(f"/api/v1/strategies/{sid}/reload")
    assert resp.status_code == 200

    # Neither was called (the strategy is IDLE)
    assert unregister_count == 0
    assert register_count == 0

    # Pending flag still cleared
    async with session_factory() as session:
        row = await session.get(StrategyRow, sid)
    assert row.has_pending_reload is False


@pytest.mark.asyncio
async def test_reload_returns_404_for_other_user(client, session_factory):
    async with session_factory() as session:
        session.add(User(id=2, email="other@test", display_name="Other"))
        row = StrategyRow(
            user_id=2, name="not-mine", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
            code_path="examples/rsi.py",
            params_json={}, symbols_json=["AAPL"], schedule="event",
            risk_limits_id=None, has_pending_reload=False,
            created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        other_sid = row.id

    resp = await client.post(f"/api/v1/strategies/{other_sid}/reload")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reload_rejects_non_python_strategy(client, session_factory):
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1, name="pine-not-allowed", version="0.1.0",
            type=StrategyType.PINE, status=StrategyStatus.IDLE,
            code_path=None,
            params_json={}, symbols_json=["AAPL"], schedule="event",
            risk_limits_id=None, has_pending_reload=False,
            created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    resp = await client.post(f"/api/v1/strategies/{sid}/reload")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_strategy_response_exposes_pending_reload_fields(client, session_factory):
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1, name="visible-flag", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.PAPER,
            code_path="examples/rsi.py",
            params_json={}, symbols_json=["AAPL"], schedule="event",
            risk_limits_id=None,
            has_pending_reload=True, pending_reload_at=_now(),
            created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    resp = await client.get(f"/api/v1/strategies/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_pending_reload"] is True
    assert body["pending_reload_at"] is not None
```

Run:

```bash
cd apps/backend
uv run pytest tests/services/test_strategy_file_watcher.py \
              tests/api/test_strategies_endpoint.py -v
uv run pytest -q
cd ../..
```

- [ ] All watcher tests pass (8 cases).
- [ ] All reload endpoint tests pass (5 cases).
- [ ] Full backend suite still green.

---

## §4.7 — Frontend: Types

Extend `apps/frontend/src/api/types.ts`. Find the `Strategy` interface and add:

```typescript
export interface Strategy {
  // ... existing fields ...
  has_pending_reload: boolean;
  pending_reload_at: string | null;
}
```

Also add the reload method to the API client. Edit `apps/frontend/src/api/strategies.ts`:

```typescript
reload: (id: number) =>
  apiFetch<StrategyActionResponse>(`/api/v1/strategies/${id}/reload`, {
    method: "POST",
    body: {},
  }),
```

Extend `StrategyActionResponse` type to allow `"reload"` action:

```typescript
export interface StrategyActionResponse {
  strategy_id: number;
  action: "start" | "stop" | "reload";
  new_status: StrategyStatus;
  run_id: number | null;
}
```

- [ ] Types extended.
- [ ] Reload API method added.

---

## §4.8 — Frontend: Pending Reload Banner

Edit `apps/frontend/src/pages/Strategies/Detail.tsx`. Add a banner just below the header.

First, the imports at the top:

```tsx
import { useCallback, useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { strategiesApi } from "@/api/strategies";
import { ApiError } from "@/api/client";
import type { Strategy } from "@/api/types";
// ... existing imports ...
```

Then inside the component, alongside the existing `handleStart` / `handleStop`:

```tsx
const [reloading, setReloading] = useState(false);

async function handleReload() {
  if (!strategy) return;
  if (!confirm(`Reload "${strategy.name}" from disk?`)) return;
  setReloading(true);
  try {
    await strategiesApi.reload(strategy.id);
    await load();
  } catch (e) {
    if (e instanceof ApiError) {
      alert(`Reload failed: ${e.detail}`);
    } else {
      alert(`Reload failed: ${e}`);
    }
  } finally {
    setReloading(false);
  }
}
```

Add the banner JSX just before the tab buttons (after the existing error banner):

```tsx
{strategy.has_pending_reload && (
  <div className="flex items-center justify-between rounded border border-amber-600 bg-amber-900/30 p-3 text-sm text-amber-100">
    <div>
      <span className="font-semibold">The strategy file has changed</span>
      {strategy.pending_reload_at && (
        <span className="ml-2 text-xs text-amber-300">
          (detected {new Date(strategy.pending_reload_at).toLocaleString()})
        </span>
      )}
      <div className="mt-0.5 text-xs text-amber-200">
        The running code is still the old version. Click Reload to apply the changes.
      </div>
    </div>
    <button
      onClick={handleReload}
      disabled={reloading}
      className="rounded bg-amber-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-amber-600 disabled:bg-gray-700"
    >
      {reloading ? "Reloading…" : "Reload"}
    </button>
  </div>
)}
```

The detail page already polls every 5s and subscribes to the `strategies` WS topic (P2 Session 5). When the watcher fires, the next refresh sees `has_pending_reload=true` and the banner appears — same goes for the WS event triggering an immediate re-fetch.

- [ ] Banner renders when `has_pending_reload=true`.
- [ ] Reload button calls the API, then refreshes the strategy.

---

## §4.9 — Frontend: List Page Indicator

The Strategies list page should also indicate "this strategy has a pending reload" so the user knows which one needs attention without navigating in.

Edit `apps/frontend/src/pages/Strategies/index.tsx`. In the table row's name cell, add a small badge:

```tsx
<td className="px-3 py-2 font-semibold">
  <Link to={`/strategies/${s.id}`} className="text-white hover:underline">
    {s.name}
  </Link>
  <span className="ml-2 text-xs text-gray-500">v{s.version}</span>
  {s.has_pending_reload && (
    <span className="ml-2 rounded bg-amber-700 px-1.5 py-0.5 text-[10px] font-semibold text-amber-100">
      RELOAD PENDING
    </span>
  )}
  {s.status === "error" && s.error_text && (
    <div className="mt-1 text-xs text-rose-400">
      {s.error_text.slice(0, 80)}{s.error_text.length > 80 ? "…" : ""}
    </div>
  )}
</td>
```

- [ ] List page shows a "RELOAD PENDING" badge per row.

---

## §4.10 — Frontend Tests

Append to `apps/frontend/src/pages/Strategies/__tests__/StrategyDetailPage.test.tsx`:

```tsx
describe("StrategyDetailPage — P4 §4 reload banner", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(strategiesApi.listRuns).mockResolvedValue({ items: [], count: 0 });
    vi.mocked(strategiesApi.listSignals).mockResolvedValue({ items: [], count: 0 });
    vi.mocked(strategiesApi.listBacktests).mockResolvedValue({ items: [], count: 0 });
    vi.mocked(signalsApi.list).mockResolvedValue({ items: [], count: 0 });
    vi.mocked(ordersApi.list).mockResolvedValue({ items: [], count: 0 });
  });

  it("shows the banner when has_pending_reload is true", async () => {
    vi.mocked(strategiesApi.get).mockResolvedValue({
      id: 1, name: "rsi", version: "0.1.0",
      type: "python", status: "paper",
      code_path: "examples/rsi.py",
      params: {}, symbols: ["AAPL"], schedule: "*/1 * * * *",
      risk_limits_id: null, error_text: null,
      has_pending_reload: true,
      pending_reload_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    } as any);

    render(
      <MemoryRouter initialEntries={["/strategies/1"]}>
        <Routes>
          <Route path="/strategies/:id" element={<StrategyDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText(/The strategy file has changed/i)).toBeInTheDocument();
    expect(await screen.findByText("Reload")).toBeInTheDocument();
  });

  it("does NOT show the banner when has_pending_reload is false", async () => {
    vi.mocked(strategiesApi.get).mockResolvedValue({
      id: 1, name: "rsi", version: "0.1.0",
      type: "python", status: "paper",
      code_path: "examples/rsi.py",
      params: {}, symbols: ["AAPL"], schedule: "*/1 * * * *",
      risk_limits_id: null, error_text: null,
      has_pending_reload: false,
      pending_reload_at: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    } as any);

    render(
      <MemoryRouter initialEntries={["/strategies/1"]}>
        <Routes>
          <Route path="/strategies/:id" element={<StrategyDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByText("rsi");
    expect(screen.queryByText(/The strategy file has changed/i)).not.toBeInTheDocument();
  });

  it("Reload button calls strategiesApi.reload", async () => {
    vi.mocked(strategiesApi.get).mockResolvedValue({
      id: 1, name: "rsi", version: "0.1.0",
      type: "python", status: "paper",
      code_path: "examples/rsi.py",
      params: {}, symbols: ["AAPL"], schedule: "*/1 * * * *",
      risk_limits_id: null, error_text: null,
      has_pending_reload: true,
      pending_reload_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    } as any);
    vi.mocked(strategiesApi.reload).mockResolvedValue({
      strategy_id: 1, action: "reload", new_status: "paper", run_id: 7,
    } as any);

    render(
      <MemoryRouter initialEntries={["/strategies/1"]}>
        <Routes>
          <Route path="/strategies/:id" element={<StrategyDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );
    const btn = await screen.findByText("Reload");
    fireEvent.click(btn);
    await waitFor(() => expect(strategiesApi.reload).toHaveBeenCalledWith(1));
  });
});
```

```bash
cd apps/frontend
pnpm test --run
cd ../..
```

- [ ] Three new frontend tests pass.
- [ ] Existing Vitest tests still green.

---

## §4.11 — Manual Smoke

```bash
./scripts/dev.sh &
sleep 30

# Verify the watcher started
docker compose logs backend | grep -E "strategy_file_watcher_started"
# Expect: one line with the resolved root path

# Register the reference RSI strategy (if not already registered)
curl -s -X POST http://127.0.0.1:8000/api/v1/strategies \
  -H "Content-Type: application/json" \
  -d '{
    "name": "rsi-hot-reload-test",
    "code_path": "examples/rsi_meanreversion.py",
    "type": "python",
    "symbols": ["AAPL"]
  }' | jq '{id, name, has_pending_reload}'

SID=$(curl -s "http://127.0.0.1:8000/api/v1/strategies" | jq -r '.items[0].id')
echo "Strategy: $SID"

# Start it (optional — for testing the active-reload path)
curl -s -X POST "http://127.0.0.1:8000/api/v1/strategies/${SID}/start" | jq '.new_status'

# Touch the file on disk to trigger the watcher
docker compose exec backend bash -c "touch -m strategies_user/examples/rsi_meanreversion.py"
sleep 2

# Watcher log line should appear
docker compose logs backend | grep -E "strategy_file_watcher_marked"
# Expect: a line with strategy_count=1, ids=[$SID]

# The strategy now has has_pending_reload=true
curl -s "http://127.0.0.1:8000/api/v1/strategies/${SID}" \
  | jq '{name, status, has_pending_reload, pending_reload_at}'
# Expect: has_pending_reload=true, pending_reload_at set

# Open http://localhost:5173/strategies/$SID — the yellow banner should be visible.
# Click Reload. Confirm. Status flickers (PAPER → IDLE → PAPER) and the banner disappears.

# Via API:
curl -s -X POST "http://127.0.0.1:8000/api/v1/strategies/${SID}/reload" \
  | jq '{action, new_status, run_id}'

# Verify cleared
curl -s "http://127.0.0.1:8000/api/v1/strategies/${SID}" \
  | jq '{has_pending_reload, pending_reload_at}'
# Expect: false, null

# Negative: introduce a syntax error and reload
docker compose exec backend bash -c "echo 'this is not python' >> strategies_user/examples/rsi_meanreversion.py"
sleep 2
curl -s -X POST "http://127.0.0.1:8000/api/v1/strategies/${SID}/reload" \
  | jq '.detail'
# Expect: 400 with a Python syntax error in the detail

# Strategy should be in ERROR
curl -s "http://127.0.0.1:8000/api/v1/strategies/${SID}" | jq '{status, error_text}'

# Fix the file
docker compose exec backend bash -c "sed -i '\$d' strategies_user/examples/rsi_meanreversion.py"
sleep 2

# Reload again should succeed
curl -s -X POST "http://127.0.0.1:8000/api/v1/strategies/${SID}/reload" \
  | jq '{action, new_status}'

docker compose down
```

- [ ] Watcher boots; logs `strategy_file_watcher_started`.
- [ ] File touch triggers `strategy_file_watcher_marked`.
- [ ] `has_pending_reload=true` appears in the strategy response.
- [ ] UI banner appears on the detail page.
- [ ] Reload clears the flag and returns the strategy to its previous status.
- [ ] Syntax error → reload returns 400, strategy enters ERROR.
- [ ] Fix + reload recovers cleanly.

---

## §4.12 — Commit and PR

```bash
git add apps/backend/app/db/models/strategy.py
git add apps/backend/alembic/versions/
git add apps/backend/app/services/strategy_file_watcher.py
git add apps/backend/app/lifespan.py
git add apps/backend/app/ws/gateway.py
git add apps/backend/app/api/v1/strategies.py
git add apps/backend/app/api/v1/schemas/strategies.py
git add apps/backend/tests/services/test_strategy_file_watcher.py
git add apps/backend/tests/api/test_strategies_endpoint.py
git add apps/frontend/src/api/types.ts
git add apps/frontend/src/api/strategies.ts
git add apps/frontend/src/pages/Strategies/Detail.tsx
git add apps/frontend/src/pages/Strategies/index.tsx
git add apps/frontend/src/pages/Strategies/__tests__/StrategyDetailPage.test.tsx

git commit -m "feat(strategies): hot-reload from filesystem with explicit user gate (P4 §4)

- strategies.has_pending_reload + pending_reload_at columns; migration
- StrategyFileWatcher service: watchfiles.awatch on strategies_user/.
  On .py modification: mark all strategies whose code_path matches as
  pending; publish strategy.pending_reload on the bus. Per-file 2s
  cooldown to debounce rapid saves.
- WS gateway routes strategy.pending_reload to 'strategies' topic
- POST /api/v1/strategies/{id}/reload: stop → re-import → start (idempotent
  for IDLE strategies). Clears has_pending_reload as part of the call.
  On import failure: strategy enters ERROR with the exception text.
- Frontend: yellow banner on strategy detail when pending; RELOAD PENDING
  badge on the list page. Both call POST /reload with confirm.
- Tests: 8 watcher unit cases + 5 endpoint cases + 3 frontend cases.

Deliberately NOT auto-reload — user clicks the button. Auto-reload during
market hours with open positions is a class of bug we don't want to invent.

Per-strategy granularity: editing a helper file imported BY a strategy
file does NOT mark the strategy. Only editing strategies.code_path itself
triggers a mark. Module-graph awareness is out of scope (P5+)."

git push -u origin feat/p4-strategy-hot-reload

gh pr create \
  --title "feat(strategies): hot-reload with explicit user gate (P4 §4)" \
  --body "P4 Item 4 — closes the deferral from P2 Session 6 prereqs section #2. Shorter edit-test loop for strategy authors."

gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
git tag -a p4-strategy-hot-reload-complete -m "P4 §4 complete"
git push origin p4-strategy-hot-reload-complete
```

- [ ] PR merged.
- [ ] Tag pushed.
- [ ] `todo.md` updated: P4 §4 ✅.

---

## Verification Checklist (full session)

- [ ] §4.1 Two new columns on `strategies`; migration round-trips.
- [ ] §4.2 `StrategyFileWatcher` watches `strategies_user/`, debounces, marks strategies, publishes on bus.
- [ ] §4.3 `strategy.pending_reload` routed to `strategies` WS topic.
- [ ] §4.4 `POST /strategies/{id}/reload` works (active path + IDLE path).
- [ ] §4.5 `StrategyResponse` exposes the two new fields.
- [ ] §4.6 16 backend tests pass; full suite green.
- [ ] §4.7 Frontend types + API client updated.
- [ ] §4.8 Banner renders on strategy detail when pending.
- [ ] §4.9 List page badge per row.
- [ ] §4.10 3 frontend tests pass.
- [ ] §4.11 Live smoke walks happy path + syntax-error recovery.
- [ ] §4.12 PR merged, tag pushed.

---

## Notes & Gotchas

1. **Auto-reload is deliberately NOT built.** Auto-reload during market hours while a strategy holds positions is a class of bug we don't want to invent. The user always clicks the button. If you ever feel tempted to add "auto-reload for strategies in IDLE only" — fine, that's a coherent narrower feature; design it explicitly rather than expanding this item's scope.

2. **Per-strategy debounce is by `code_path`, not by `strategy_id`.** Two strategies with the same `code_path` share the cooldown bucket. In practice this is fine — they all get marked together when the file changes, so per-file debounce is correct.

3. **`watchfiles.awatch` is async-native.** Earlier "file watcher" libraries (watchdog) need thread bridges; `watchfiles` plays cleanly with FastAPI's event loop. The `stop_event` is the clean shutdown signal.

4. **No module-graph dependency tracking.** Editing `strategies_user/helpers/risk_utils.py` does NOT mark a strategy that imports it. Only editing `strategies.code_path` itself does. Module-graph awareness would require AST parsing every strategy file + maintaining an import-graph cache + invalidating on any file in the graph — a lot of complexity for the rare "I edited a shared helper" workflow. If this comes up in practice, a manual "Reload" still works; you just don't get the banner. P5+ scope if it ever genuinely hurts.

5. **`importlib.reload` is NOT used.** `engine.register(id)` calls `StrategyLoader.load(code_path)` which uses `importlib.util.spec_from_file_location` + `module_from_spec` + `spec.loader.exec_module`. This gives us a fresh module object every time — no stale closures, no half-reloaded state. The trade-off is that the old module stays in memory until GC; for the size of typical strategy files this is invisible.

6. **In-process strategy state is discarded.** A strategy's `_entry_state` dict, indicator caches, or any other instance state lives only in the Python object. Reload creates a new object → state goes to zero. If a strategy holds positions that depend on knowing entry timestamps for stop-loss calculations, the new instance won't know. The user can either (a) keep that state in the DB (the `signals` table, `positions` table, etc.), or (b) not reload while holding open positions. Worth a note in `docs/runbook/strategy-authoring.md` — append a "Reloading a running strategy" subsection in a follow-up doc PR if not already there.

7. **The reload endpoint clears the flag BEFORE attempting register.** If register fails (syntax error), the flag is gone but the strategy is in ERROR with the error text visible. The user fixes the file → the watcher fires again → flag goes back to true → user clicks Reload again. Don't keep the flag set on failure; the watcher is the source of truth for "file changed," not the reload outcome.

8. **The watcher cooldown is per-file, not per-strategy.** If you have two strategies pointing at the same file and you save it twice in 1 second, both strategies get marked once (during the first save). The second save is in cooldown. The strategies still both end up marked — the cooldown only prevents re-publishing identical events, not the underlying marking.

9. **Editor swap files are filtered.** Vim creates `*.swp`, VS Code creates `*.tmp` and renames, JetBrains writes through. The `if p.name.startswith(".")` filter catches the common dotfile-prefixed ones; the `.py` suffix check catches the rest. If your editor has an exotic save pattern, you may need to extend the filter. Test by saving from your normal editor and checking the watcher logs.

10. **`StrategyFileWatcher` doesn't crash the backend on internal errors.** The `_run` method catches all exceptions inside its loop and logs them. The intent is: a flaky inotify watcher should never bring down the trading engine. If you're debugging a watcher problem, look for `strategy_file_watcher_loop_crashed` in the logs — if you see it, the watcher is dead but everything else still works.

11. **The action value `"reload"`** appears in audit_log via `payload.action` and in `StrategyActionResponse.action`. If anything else in the codebase pattern-matches on Literal `["start", "stop"]`, extend it. Search for `"start" \| "stop"` in TypeScript and `Literal\["start", "stop"\]` in Python — extension targets.

12. **Don't bundle other P4 items.** Tag and ship.

---

*End of P4 Item 4 v0.1.*
