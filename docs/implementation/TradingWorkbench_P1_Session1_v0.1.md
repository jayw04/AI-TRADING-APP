# P1 Session 1 — P0 Close-out & Alpaca Adapter Foundation

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-20 |
| Phase | **P1**, **Sections §0 + §1.1 + §1.2 + (error taxonomy from §1.5)** |
| Predecessor | *TradingWorkbench_P1_Checklist_v0.1.md* |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | (1) Close out all P0 follow-ups. (2) Lay the Alpaca adapter foundation: credentials, error taxonomy, adapter class with read-only methods, streaming module skeleton. **No order submission code in this session** — that comes after the Risk Engine and Order Router land. |
| Estimated wall time | 2.5–3.5 hours |
| Stopping point | `git tag p1-session1-complete` |
| Explicitly deferred to **P1 Session 2** | Daily asset sync scheduler, account/position polling loops, Trade Updates WS lifecycle, reconciliation drift detection |

---

## Session Goal

After this session:
- All five P0 follow-ups from todo.md are closed (CI green, branch protection live, validation PR merged, Alpaca creds in `.env`, Implementation Plan v0.2 in the repo).
- A working `AlpacaAdapter` can `connect()` to Alpaca paper, return `get_account()` with real numbers, return `get_positions()`, and `list_assets()` for US equities.
- A typed error taxonomy classifies Alpaca exceptions into transient vs permanent.
- A `TradeUpdatesStream` class exists as a skeleton (no running task yet).
- Backend tests for the adapter pass with mocked Alpaca client.
- One PR merged through the protected-branch workflow.

What does NOT happen this session:
- No `submit_order` / `cancel_order` / `replace_order` implementations — they land in P1 Session 4 (Order Router), because per ADR 0002 they must only be reachable through the router.
- No background tasks, no schedulers, no live polling loops.
- No order database schema yet (P1 Session 3).

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP  # or wherever your local clone is
git status                # must be clean on main
git pull origin main      # must be at p0-complete tag

# Confirm tag
git describe --tags --abbrev=0  # expect: p0-complete

# Confirm three services still healthy
./scripts/dev.sh &        # or `docker compose up -d`
sleep 15
curl -s http://127.0.0.1:8000/healthz | jq .   # expect {status:ok, db:ok}
docker compose down       # we'll bring it back up later
```

Also confirm you have:
- Alpaca paper API key + secret (from https://app.alpaca.markets/paper/dashboard/overview, "View" next to API Keys).
- `gh` CLI authenticated against the `jayw04` account.

---

## §0 — Close out P0 follow-ups

### 0.1 Confirm CI green

```bash
gh run list --branch main --limit 5
```

Look for the most recent `main`-targeted run on commit `6e66ad9`. Expect status `completed` and conclusion `success` across all 6 jobs.

If any job failed:
```bash
gh run view <run-id> --log-failed
```
Fix and push a small commit. Do not proceed until CI is green on `main`.

- [ ] CI green on `6e66ad9` or later.

### 0.2 Branch protection on `main`

GitHub Rulesets via the web UI (the CLI's `ruleset` support is too limited for this).

Open: `https://github.com/jayw04/AI-TRADING-APP/settings/rules`

Click **New ruleset → New branch ruleset**. Fill in:

| Setting | Value |
|---|---|
| Ruleset name | `protect-main` |
| Enforcement status | **Active** |
| Bypass list | (empty — even admin bypass off) |
| Target branches | Include default branch (`main`) |

**Branch rules** (check these boxes):
- ✅ Restrict deletions
- ✅ Require linear history
- ✅ Require a pull request before merging
  - Required approvals: **0** (solo for now)
  - ✅ Dismiss stale pull request approvals when new commits are pushed
  - ❌ Require review from Code Owners
  - ❌ Require approval of the most recent reviewable push
- ✅ Require status checks to pass
  - ✅ Require branches to be up to date before merging
  - Add status checks (search for each by name and select):
    - `Python (backend)`
    - `Python (mcp-server)`
    - `Frontend`
    - `Build image (backend)`
    - `Build image (mcp-server)`
    - `Build image (frontend)`
- ✅ Block force pushes
- ❌ Require deployments to succeed
- ❌ Require code scanning results

Click **Create**.

**Verify it bites:**

```bash
# Try a direct push to main — should fail
git commit --allow-empty -m "test: direct push should be blocked"
git push origin main
# Expected: rejected by GitHub with a ruleset violation message
git reset --hard HEAD~1
```

If the push succeeded, the ruleset isn't enforced — re-check the settings (most common mistake: enforcement status set to Evaluate instead of Active).

- [ ] Ruleset `protect-main` active.
- [ ] Direct push to `main` blocked in the verify step.

### 0.3 First validation PR

A trivial, low-risk change to validate the protected-branch flow end-to-end.

```bash
git checkout -b chore/validate-protected-main
```

Add a line to README.md acknowledging branch protection:

```bash
# Insert a one-line note near the bottom of README.md
cat >> README.md << 'EOF'

---

> Branch protection: `main` is protected. All changes land via PR with required CI checks.
EOF
```

```bash
git add README.md
git commit -m "chore: document branch protection on main"
git push -u origin chore/validate-protected-main

gh pr create \
  --title "chore: validate protected-main workflow" \
  --body "Trivial README addition. Validates that the protected-branch + required-checks flow works end-to-end before P1 substantive work lands."
```

Wait for CI to run on the PR (Actions tab on GitHub, or `gh pr checks`). All 6 jobs must go green.

```bash
gh pr checks       # poll until all pass
gh pr merge --merge --delete-branch
git checkout main && git pull
```

- [ ] PR opened, CI ran all 6 jobs, all green.
- [ ] PR merged via the GitHub UI / `gh pr merge`.
- [ ] Branch auto-deleted.
- [ ] `git pull` on `main` brings the change down clean.

### 0.4 Migrate Alpaca creds out of `alpaca info.txt`

```bash
# Locate the file
find . -name "alpaca info.txt" -not -path "./node_modules/*"
```

If it shows up under git:

```bash
git log --all --full-history -- "*alpaca info.txt*"
```

**If that command shows ANY commits**, the file was committed at some point — even if you `git rm` it now, the keys are in history and need to be **rotated in Alpaca's dashboard today**. Don't put this off; even a private repo can leak via cloned forks, log aggregators, or accidental visibility changes.

Steps either way:

1. Open the file, read both keys (paper and live if present).
2. Open `.env` (create from `.env.example` if it doesn't exist locally):
   ```bash
   cp -n .env.example .env
   ${EDITOR:-nano} .env
   ```
3. Fill in:
   ```
   ALPACA_PAPER_API_KEY=PK********
   ALPACA_PAPER_API_SECRET=********
   # Leave ALPACA_LIVE_* blank unless you actually have live keys.
   ```
4. Delete the file:
   ```bash
   rm "alpaca info.txt"
   # If it was tracked:
   git rm "alpaca info.txt" 2>/dev/null || true
   ```
5. Confirm `.env` is gitignored:
   ```bash
   git check-ignore -v .env
   # Expected: .gitignore:<lineno>:.env  .env
   ```
6. If the file was in history → **go to Alpaca dashboard now**, regenerate the paper keys, update `.env` with the new ones, and continue.

If a delete commit is needed:
```bash
git commit -m "chore(security): remove alpaca info.txt; creds now in .env (gitignored)"
git push origin main   # this will be rejected; open a PR instead per the protected-main rule
```

Actually — given branch protection now requires PRs, do this on a branch:

```bash
git checkout -b chore/remove-alpaca-creds-file
git add -A
git commit -m "chore(security): remove alpaca info.txt; creds now in .env (gitignored)"
git push -u origin chore/remove-alpaca-creds-file
gh pr create --title "chore(security): remove alpaca info.txt" --body "Creds migrated to .env (gitignored). If file was ever in history with real keys, those keys have been rotated."
gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
```

- [ ] `alpaca info.txt` no longer exists in the working tree.
- [ ] `.env` contains the paper keys and is gitignored.
- [ ] If keys were ever in git history → keys rotated in Alpaca dashboard.
- [ ] Cleanup PR merged.

### 0.5 Drop Implementation Plan v0.2 into the repo

You already have the file from our earlier session (`TradingWorkbench_ImplementationPlan_v0.2.md` and `TradingWorkbench_P1_Checklist_v0.1.md`). Copy them in:

```bash
git checkout -b docs/add-implementation-plan-v0.2

# Adjust source paths to wherever you saved them locally:
cp /path/to/TradingWorkbench_ImplementationPlan_v0.2.md docs/implementation/
cp /path/to/TradingWorkbench_P1_Checklist_v0.1.md       docs/implementation/
cp /path/to/TradingWorkbench_P1_Session1_v0.1.md        docs/implementation/

# Add the phase-numbering note to the v0.2 doc header
# (manually edit the file to add the note from the P1 Checklist §0.3 mapping)
${EDITOR:-nano} docs/implementation/TradingWorkbench_ImplementationPlan_v0.2.md
```

Insert this near the top of v0.2 (e.g., right under the Changelog section):

```markdown
> **Phase-numbering note (added 2026-05-20):** This document predates the convention adopted in `todo.md`, which follows Design Doc §13's simpler 7-phase scheme. See `TradingWorkbench_P1_Checklist_v0.1.md` §0.3 for the canonical mapping.
```

Then commit and PR:

```bash
git add docs/implementation/
git commit -m "docs: add implementation plan v0.2 and p1 checklist/session1 to repo"
git push -u origin docs/add-implementation-plan-v0.2
gh pr create --title "docs: implementation plan v0.2 + p1 checklist + p1 session 1" --body "Drops the planning docs referenced throughout the repo into docs/implementation/. Adds a phase-numbering note to v0.2 pointing at the P1 Checklist's canonical mapping."
gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
```

- [ ] `docs/implementation/TradingWorkbench_ImplementationPlan_v0.2.md` exists on `main`.
- [ ] Phase-numbering note added near the top.
- [ ] `docs/implementation/TradingWorkbench_P1_Checklist_v0.1.md` exists on `main`.
- [ ] `docs/implementation/TradingWorkbench_P1_Session1_v0.1.md` exists on `main`.
- [ ] PR merged.

### 0.6 P1 prereqs (one-time reads, no commits)

- [ ] Re-read `docs/adr/0002-single-order-entry-point.md`. The whole P1 design depends on this invariant.
- [ ] Re-read Design Doc §10 (Security, Risk, Compliance) — informs Session 2 (risk engine).
- [ ] Confirm Alpaca paper account is alive:
  ```bash
  # Quick sanity-check using curl + the keys you just put in .env
  set -a; source .env; set +a
  curl -s -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
       -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET" \
       https://paper-api.alpaca.markets/v2/account | jq '{status, buying_power, equity}'
  # Expected: {"status":"ACTIVE","buying_power":"...","equity":"..."}
  ```
  If this returns a 4xx, fix credentials before proceeding (the rest of the session is useless without a working API key).
- [ ] Create a GitHub milestone "P1 — Manual Trading MVP" linking back to the P1 Checklist:
  ```bash
  gh api repos/jayw04/AI-TRADING-APP/milestones \
    -f title="P1 - Manual Trading MVP" \
    -f description="See docs/implementation/TradingWorkbench_P1_Checklist_v0.1.md"
  ```

**Section §0 acceptance:** all five P0 follow-ups closed; ADR 0002 re-read; Alpaca paper API responds to curl with status ACTIVE; P1 milestone created.

---

## §1 — Alpaca Adapter Foundation

From here, all work happens on a feature branch. Cut it now:

```bash
git checkout -b feat/p1-alpaca-adapter
```

### 1.1 Add `alpaca-py` to backend dependencies

Edit `apps/backend/pyproject.toml`. In the `[project] dependencies` (or equivalent) list, add:

```toml
"alpaca-py>=0.30.0,<1.0.0",
"apscheduler>=3.10.4,<4.0.0",  # used in P1 Session 2 for scheduled syncs
```

Then sync the venv:

```bash
cd apps/backend
uv pip install -e ".[dev]"
cd ../..
```

Verify the import works:

```bash
cd apps/backend
uv run python -c "from alpaca.trading.client import TradingClient; print('ok')"
cd ../..
```

- [ ] `alpaca-py` and `apscheduler` listed as deps.
- [ ] `uv pip install` succeeded.
- [ ] Import sanity-check prints `ok`.

### 1.2 Extend backend config with trading-mode env vars

Edit `apps/backend/app/config.py`. Add these fields to the `Settings` class (next to the existing `workbench_*` fields):

```python
# --- Trading mode ---
trading_mode: str = Field(default="paper", alias="WORKBENCH_TRADING_MODE")
live_ack: str = Field(default="", alias="WORKBENCH_LIVE_ACK")

# --- Alpaca credentials ---
alpaca_paper_api_key: str = Field(default="", alias="ALPACA_PAPER_API_KEY")
alpaca_paper_api_secret: str = Field(default="", alias="ALPACA_PAPER_API_SECRET")
alpaca_live_api_key: str = Field(default="", alias="ALPACA_LIVE_API_KEY")
alpaca_live_api_secret: str = Field(default="", alias="ALPACA_LIVE_API_SECRET")
```

Update `apps/backend/app/config.py` model-config block if you need `extra="ignore"` to tolerate unrelated env vars (you should already have this from P0).

Verify the config loads:

```bash
cd apps/backend
uv run python -c "from app.config import get_settings; s = get_settings(); print(s.trading_mode, bool(s.alpaca_paper_api_key))"
cd ../..
# Expected: paper True
```

- [ ] Settings fields added.
- [ ] `get_settings()` reads them from `.env` correctly.

### 1.3 Create the `brokers/alpaca/` package

```bash
mkdir -p apps/backend/app/brokers/alpaca
touch apps/backend/app/brokers/__init__.py
touch apps/backend/app/brokers/alpaca/__init__.py
```

Edit `apps/backend/app/brokers/alpaca/__init__.py`:

```python
"""Alpaca broker adapter.

Per ADR 0002, this is the Workbench's ONLY outbound interface to Alpaca.
All order submissions must originate from OrderRouter; no other code path
may import AlpacaAdapter.submit_order directly.
"""
from .adapter import AlpacaAdapter
from .credentials import AlpacaCredentials, load_credentials
from .errors import AlpacaError, TransientAlpacaError, PermanentAlpacaError, classify

__all__ = [
    "AlpacaAdapter",
    "AlpacaCredentials",
    "load_credentials",
    "AlpacaError",
    "TransientAlpacaError",
    "PermanentAlpacaError",
    "classify",
]
```

### 1.4 `credentials.py` — mode-gated credential loading

Create `apps/backend/app/brokers/alpaca/credentials.py`:

```python
"""Alpaca credential loader with paper-default and live-ack gating."""
from dataclasses import dataclass

from app.config import get_settings


@dataclass(frozen=True)
class AlpacaCredentials:
    api_key: str
    api_secret: str
    paper: bool

    @property
    def base_url(self) -> str:
        return (
            "https://paper-api.alpaca.markets"
            if self.paper
            else "https://api.alpaca.markets"
        )


class CredentialsError(RuntimeError):
    """Raised when credentials cannot be loaded safely."""


def load_credentials() -> AlpacaCredentials:
    """Load Alpaca credentials based on configured trading mode.

    - Default mode is 'paper'. Returns paper creds from env.
    - 'live' mode requires WORKBENCH_LIVE_ACK == 'I_UNDERSTAND' AND non-empty live keys.
      Any other condition raises CredentialsError. Live mode does NOT silently fall
      back to paper — that would be worse than failing loudly.
    """
    s = get_settings()
    mode = (s.trading_mode or "paper").lower()

    if mode == "live":
        if s.live_ack != "I_UNDERSTAND":
            raise CredentialsError(
                "Live mode requested but WORKBENCH_LIVE_ACK != 'I_UNDERSTAND'. "
                "See docs/runbook/live-mode.md."
            )
        if not s.alpaca_live_api_key or not s.alpaca_live_api_secret:
            raise CredentialsError(
                "Live mode requested but ALPACA_LIVE_API_KEY / "
                "ALPACA_LIVE_API_SECRET are not set."
            )
        return AlpacaCredentials(
            api_key=s.alpaca_live_api_key,
            api_secret=s.alpaca_live_api_secret,
            paper=False,
        )

    if mode != "paper":
        raise CredentialsError(
            f"WORKBENCH_TRADING_MODE must be 'paper' or 'live', got '{mode}'."
        )

    if not s.alpaca_paper_api_key or not s.alpaca_paper_api_secret:
        raise CredentialsError(
            "ALPACA_PAPER_API_KEY / ALPACA_PAPER_API_SECRET are not set in .env."
        )

    return AlpacaCredentials(
        api_key=s.alpaca_paper_api_key,
        api_secret=s.alpaca_paper_api_secret,
        paper=True,
    )
```

- [ ] File created.
- [ ] Default loading returns paper creds.
- [ ] Setting `WORKBENCH_TRADING_MODE=live` without ack raises.

### 1.5 `errors.py` — Transient vs Permanent error taxonomy

Create `apps/backend/app/brokers/alpaca/errors.py`:

```python
"""Alpaca error taxonomy.

Distinguishes transient (retryable) from permanent (don't retry; surface to user).
Order router uses this to decide retry behavior; UI uses it to format messages.
"""
from __future__ import annotations


class AlpacaError(Exception):
    """Base class for all Alpaca-related errors raised by the adapter."""


class TransientAlpacaError(AlpacaError):
    """Retryable: 5xx, timeouts, rate limit (429)."""


class PermanentAlpacaError(AlpacaError):
    """Not retryable: 4xx (except 429), insufficient funds, asset not tradable."""


def classify(exc: BaseException) -> AlpacaError:
    """Map an underlying exception to our taxonomy.

    Imports alpaca-py exception classes lazily so this module has no import-time
    dependency on alpaca-py (useful for tests).
    """
    # Try to detect alpaca-py's APIError
    try:
        from alpaca.common.exceptions import APIError  # type: ignore[import-not-found]

        if isinstance(exc, APIError):
            status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            if status == 429:
                return TransientAlpacaError(str(exc))
            if isinstance(status, int):
                if 500 <= status < 600:
                    return TransientAlpacaError(str(exc))
                if 400 <= status < 500:
                    return PermanentAlpacaError(str(exc))
    except ImportError:
        pass

    # Connection/timeout errors → transient
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return TransientAlpacaError(str(exc))

    # Default: treat as permanent. Better to surface and let the user retry manually
    # than silently retry something we don't understand.
    return PermanentAlpacaError(str(exc))
```

- [ ] File created.

### 1.6 `adapter.py` — the adapter class (read-only methods)

Create `apps/backend/app/brokers/alpaca/adapter.py`:

```python
"""AlpacaAdapter — the single outbound interface to Alpaca.

Per ADR 0002, order submission must only be invoked via OrderRouter. The
submit_order / cancel_order / replace_order methods are intentionally NOT
implemented in this session — they land in P1 Session 4 alongside OrderRouter,
to avoid creating a callable bypass.
"""
from __future__ import annotations

from typing import Any

import structlog

from .credentials import AlpacaCredentials, load_credentials
from .errors import classify

logger = structlog.get_logger(__name__)


class AlpacaAdapter:
    """Thin wrapper over alpaca-py TradingClient.

    Lifecycle:
        adapter = AlpacaAdapter()       # loads credentials from env
        adapter.connect()                # creates the TradingClient, verifies auth
        adapter.get_account()            # ... usable read methods ...
        adapter.disconnect()             # drops the client

    Concurrency: instances are not shared across asyncio tasks; the underlying
    alpaca-py TradingClient is sync. For async contexts, wrap calls in
    run_in_executor at the call site (done in P1 Session 2 polling loops).
    """

    def __init__(self, credentials: AlpacaCredentials | None = None) -> None:
        self._creds = credentials or load_credentials()
        self._trading: Any = None  # alpaca.trading.client.TradingClient
        logger.info(
            "alpaca_adapter_init",
            paper=self._creds.paper,
            base_url=self._creds.base_url,
        )

    # ---- lifecycle ----

    @property
    def is_paper(self) -> bool:
        return self._creds.paper

    @property
    def is_connected(self) -> bool:
        return self._trading is not None

    def connect(self) -> None:
        """Create the underlying TradingClient and verify by reading the account."""
        if self._trading is not None:
            return
        from alpaca.trading.client import TradingClient  # lazy import

        self._trading = TradingClient(
            api_key=self._creds.api_key,
            secret_key=self._creds.api_secret,
            paper=self._creds.paper,
        )
        # Verify by hitting the account endpoint. Raises if creds are bad.
        try:
            self.get_account()
        except Exception:
            self._trading = None
            raise
        logger.info("alpaca_adapter_connected", paper=self._creds.paper)

    def disconnect(self) -> None:
        self._trading = None
        logger.info("alpaca_adapter_disconnected")

    def _client(self) -> Any:
        if self._trading is None:
            self.connect()
        return self._trading

    # ---- read methods (P1 Session 1 scope) ----

    def get_account(self) -> dict[str, Any]:
        """Return the live account snapshot."""
        try:
            account = self._client().get_account()
            return _to_dict(account)
        except Exception as exc:  # noqa: BLE001
            raise classify(exc) from exc

    def get_positions(self) -> list[dict[str, Any]]:
        """Return all open positions for the account."""
        try:
            positions = self._client().get_all_positions()
            return [_to_dict(p) for p in positions]
        except Exception as exc:  # noqa: BLE001
            raise classify(exc) from exc

    def list_assets(self, active_only: bool = True) -> list[dict[str, Any]]:
        """List US-equity tradable assets (used by the daily symbol sync in Session 2)."""
        try:
            from alpaca.trading.enums import AssetClass, AssetStatus  # lazy
            from alpaca.trading.requests import GetAssetsRequest

            req = GetAssetsRequest(
                status=AssetStatus.ACTIVE if active_only else None,
                asset_class=AssetClass.US_EQUITY,
            )
            assets = self._client().get_all_assets(req)
            return [_to_dict(a) for a in assets]
        except Exception as exc:  # noqa: BLE001
            raise classify(exc) from exc

    def get_order(self, broker_order_id: str) -> dict[str, Any]:
        try:
            order = self._client().get_order_by_id(broker_order_id)
            return _to_dict(order)
        except Exception as exc:  # noqa: BLE001
            raise classify(exc) from exc

    def list_orders(
        self,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        try:
            from alpaca.trading.enums import QueryOrderStatus  # lazy
            from alpaca.trading.requests import GetOrdersRequest

            req = GetOrdersRequest(
                status=QueryOrderStatus(status) if status else QueryOrderStatus.ALL,
                limit=limit,
            )
            orders = self._client().get_orders(filter=req)
            return [_to_dict(o) for o in orders]
        except Exception as exc:  # noqa: BLE001
            raise classify(exc) from exc

    # ---- mutating methods (DELIBERATELY UNIMPLEMENTED — see ADR 0002) ----

    def submit_order(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        """NOT IMPLEMENTED in this session. Lands in P1 Session 4 with OrderRouter.

        Per ADR 0002, this method must only be invoked from OrderRouter.submit().
        It is deliberately left as NotImplementedError here to prevent any code
        path from accidentally calling Alpaca's submit endpoint before the risk
        engine is in place.
        """
        raise NotImplementedError(
            "submit_order is implemented in P1 Session 4 alongside OrderRouter. "
            "Per ADR 0002, this method may only be called from OrderRouter.submit()."
        )

    def cancel_order(self, *_args: Any, **_kwargs: Any) -> None:
        raise NotImplementedError("cancel_order lands in P1 Session 4.")

    def replace_order(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("replace_order lands in P1 Session 4.")


def _to_dict(obj: Any) -> dict[str, Any]:
    """Normalize alpaca-py model objects (pydantic v2) to plain dicts."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "_raw"):  # older alpaca-py
        return dict(obj._raw)
    if isinstance(obj, dict):
        return obj
    # Last-resort: try __dict__
    return dict(getattr(obj, "__dict__", {}) or {})
```

- [ ] File created.
- [ ] `submit_order` / `cancel_order` / `replace_order` raise `NotImplementedError` with a clear message.

### 1.7 `streaming.py` — Trade Updates skeleton

Create `apps/backend/app/brokers/alpaca/streaming.py`:

```python
"""Alpaca Trade Updates streaming (skeleton).

This file establishes the shape; the actual long-running task + event-bus wiring
lands in P1 Session 2. Nothing here is started automatically yet.
"""
from __future__ import annotations

from typing import Any, Callable, Awaitable

import structlog

from .credentials import AlpacaCredentials

logger = structlog.get_logger(__name__)


# Type for the handler the adapter consumer registers
TradeUpdateHandler = Callable[[dict[str, Any]], Awaitable[None]]


class TradeUpdatesStream:
    """Wraps alpaca-py's TradingStream and forwards trade updates to a handler.

    Lifecycle in Session 2:
        stream = TradeUpdatesStream(creds, on_update=lifecycle.handle_trade_update)
        await stream.start()    # creates and runs the underlying stream as a task
        await stream.stop()     # cancels the task

    This skeleton exists so other modules (e.g., the future order lifecycle) can
    reference its type. It does NOT start any work on import.
    """

    def __init__(
        self,
        credentials: AlpacaCredentials,
        on_update: TradeUpdateHandler,
    ) -> None:
        self._creds = credentials
        self._on_update = on_update
        self._stream: Any = None
        self._started = False

    @property
    def is_started(self) -> bool:
        return self._started

    async def start(self) -> None:  # pragma: no cover — implemented in Session 2
        raise NotImplementedError(
            "TradeUpdatesStream.start() is implemented in P1 Session 2."
        )

    async def stop(self) -> None:  # pragma: no cover — implemented in Session 2
        raise NotImplementedError(
            "TradeUpdatesStream.stop() is implemented in P1 Session 2."
        )
```

- [ ] File created.

### 1.8 Tests

Create `apps/backend/tests/brokers/__init__.py` and `apps/backend/tests/brokers/alpaca/__init__.py` (empty).

Then `apps/backend/tests/brokers/alpaca/test_credentials.py`:

```python
import pytest

from app.brokers.alpaca.credentials import (
    AlpacaCredentials,
    CredentialsError,
    load_credentials,
)


def test_paper_credentials_loaded(monkeypatch):
    monkeypatch.setenv("WORKBENCH_TRADING_MODE", "paper")
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "PK_TEST")
    monkeypatch.setenv("ALPACA_PAPER_API_SECRET", "SECRET_TEST")
    # Bust the lru_cache on settings
    from app.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]

    creds = load_credentials()
    assert isinstance(creds, AlpacaCredentials)
    assert creds.paper is True
    assert creds.api_key == "PK_TEST"
    assert "paper-api" in creds.base_url


def test_live_mode_requires_ack(monkeypatch):
    monkeypatch.setenv("WORKBENCH_TRADING_MODE", "live")
    monkeypatch.setenv("WORKBENCH_LIVE_ACK", "")  # missing ack
    monkeypatch.setenv("ALPACA_LIVE_API_KEY", "PK_LIVE")
    monkeypatch.setenv("ALPACA_LIVE_API_SECRET", "SECRET_LIVE")
    from app.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]

    with pytest.raises(CredentialsError, match="WORKBENCH_LIVE_ACK"):
        load_credentials()


def test_live_mode_requires_keys(monkeypatch):
    monkeypatch.setenv("WORKBENCH_TRADING_MODE", "live")
    monkeypatch.setenv("WORKBENCH_LIVE_ACK", "I_UNDERSTAND")
    monkeypatch.setenv("ALPACA_LIVE_API_KEY", "")
    monkeypatch.setenv("ALPACA_LIVE_API_SECRET", "")
    from app.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]

    with pytest.raises(CredentialsError, match="ALPACA_LIVE_API_KEY"):
        load_credentials()


def test_unknown_mode_rejected(monkeypatch):
    monkeypatch.setenv("WORKBENCH_TRADING_MODE", "yolo")
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "PK_TEST")
    monkeypatch.setenv("ALPACA_PAPER_API_SECRET", "SECRET_TEST")
    from app.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]

    with pytest.raises(CredentialsError, match="paper.*live"):
        load_credentials()
```

Then `apps/backend/tests/brokers/alpaca/test_errors.py`:

```python
from app.brokers.alpaca.errors import (
    PermanentAlpacaError,
    TransientAlpacaError,
    classify,
)


def test_connection_error_is_transient():
    out = classify(ConnectionError("connection reset"))
    assert isinstance(out, TransientAlpacaError)


def test_timeout_error_is_transient():
    out = classify(TimeoutError("timed out"))
    assert isinstance(out, TransientAlpacaError)


def test_unknown_exception_defaults_permanent():
    out = classify(ValueError("nope"))
    assert isinstance(out, PermanentAlpacaError)


def test_apierror_5xx_transient():
    # Construct a fake APIError-like object if alpaca-py is installed.
    try:
        from alpaca.common.exceptions import APIError
    except ImportError:
        return
    e = APIError.__new__(APIError)
    e.args = ("server error",)
    e.status_code = 503
    out = classify(e)
    assert isinstance(out, TransientAlpacaError)


def test_apierror_4xx_permanent():
    try:
        from alpaca.common.exceptions import APIError
    except ImportError:
        return
    e = APIError.__new__(APIError)
    e.args = ("bad request",)
    e.status_code = 422
    out = classify(e)
    assert isinstance(out, PermanentAlpacaError)


def test_apierror_429_transient():
    try:
        from alpaca.common.exceptions import APIError
    except ImportError:
        return
    e = APIError.__new__(APIError)
    e.args = ("rate limited",)
    e.status_code = 429
    out = classify(e)
    assert isinstance(out, TransientAlpacaError)
```

Then `apps/backend/tests/brokers/alpaca/test_adapter.py`:

```python
"""Adapter tests with the underlying TradingClient mocked.

For Session 1 we only verify the wiring; live integration test against Alpaca
paper happens in the manual smoke step at the end of the session.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.brokers.alpaca.adapter import AlpacaAdapter
from app.brokers.alpaca.credentials import AlpacaCredentials


@pytest.fixture
def paper_creds():
    return AlpacaCredentials(api_key="PK_TEST", api_secret="SECRET_TEST", paper=True)


def test_init_logs_mode(paper_creds):
    a = AlpacaAdapter(credentials=paper_creds)
    assert a.is_paper is True
    assert a.is_connected is False


def test_connect_calls_get_account(paper_creds):
    with patch("alpaca.trading.client.TradingClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.get_account.return_value = MagicMock(
            model_dump=lambda mode=None: {"status": "ACTIVE", "buying_power": "100000"}
        )
        MockClient.return_value = mock_instance

        a = AlpacaAdapter(credentials=paper_creds)
        a.connect()

        assert a.is_connected is True
        mock_instance.get_account.assert_called()


def test_submit_order_not_implemented_per_adr0002(paper_creds):
    a = AlpacaAdapter(credentials=paper_creds)
    with pytest.raises(NotImplementedError, match="OrderRouter"):
        a.submit_order(symbol="AAPL", qty=1, side="buy")


def test_cancel_order_not_implemented(paper_creds):
    a = AlpacaAdapter(credentials=paper_creds)
    with pytest.raises(NotImplementedError, match="Session 4"):
        a.cancel_order("fake-order-id")
```

Run all backend tests:

```bash
cd apps/backend
uv run pytest -q
cd ../..
```

- [ ] Three new test files exist.
- [ ] All tests pass locally.

### 1.9 Manual smoke against Alpaca paper

This proves the wiring against the real (paper) Alpaca API. Done from a Python REPL, not committed.

```bash
cd apps/backend
uv run python << 'EOF'
from app.brokers.alpaca.adapter import AlpacaAdapter

a = AlpacaAdapter()           # loads paper creds from .env
a.connect()
print("connected (paper=", a.is_paper, ")")

acct = a.get_account()
print("status:", acct.get("status"))
print("buying_power:", acct.get("buying_power"))
print("equity:", acct.get("equity"))

positions = a.get_positions()
print(f"positions: {len(positions)}")

assets = a.list_assets()
print(f"active US equities: {len(assets)}")

orders = a.list_orders(limit=5)
print(f"recent orders: {len(orders)}")

a.disconnect()
print("disconnected")
EOF
cd ../..
```

Expected output (numbers will vary):
```
connected (paper= True )
status: ACTIVE
buying_power: 100000.00
equity: 100000.00
positions: 0
active US equities: 5000+ (varies)
recent orders: 0
disconnected
```

- [ ] All steps succeed without exceptions.
- [ ] `status: ACTIVE` printed.
- [ ] At least 1000 active US equities returned.

### 1.10 Commit and PR

```bash
git add apps/backend/pyproject.toml apps/backend/app/config.py
git add apps/backend/app/brokers
git add apps/backend/tests/brokers
git commit -m "feat(brokers): alpaca adapter foundation with paper-mode gating

- AlpacaCredentials with WORKBENCH_TRADING_MODE + live-ack gating
- AlpacaAdapter with read-only methods (account, positions, assets, orders)
- TransientAlpacaError / PermanentAlpacaError taxonomy + classify()
- TradeUpdatesStream skeleton (implementation in Session 2)
- submit_order / cancel_order / replace_order intentionally NotImplemented
  per ADR 0002 — they land in P1 Session 4 alongside OrderRouter
- Tests with mocked TradingClient + APIError classification"

git push -u origin feat/p1-alpaca-adapter

gh pr create \
  --title "feat(brokers): alpaca adapter foundation" \
  --body "P1 Session 1 §1 deliverable. Adds the Alpaca adapter foundation: credentials with paper/live gating, read-only adapter methods, error taxonomy, streaming skeleton.

**Not in scope (deferred to P1 Session 2):**
- Background polling loops
- Daily symbol sync scheduler
- TradeUpdatesStream lifecycle wiring

**Not in scope (deferred to P1 Session 4, per ADR 0002):**
- submit_order / cancel_order / replace_order implementations

Closes part of #<milestone-id>"

gh pr checks
```

Wait for all 6 CI jobs to pass.

```bash
gh pr merge --merge --delete-branch
git checkout main && git pull
```

- [ ] PR opened, CI green, merged, branch deleted.
- [ ] `git pull` on `main` brings the change down.

---

## Verification Checklist (full session)

Tick every box before tagging:

- [ ] §0.1 CI green on `6e66ad9` or later.
- [ ] §0.2 Branch protection ruleset `protect-main` active; direct push verified blocked.
- [ ] §0.3 Validation PR opened, CI green on all 6 jobs, merged, branch deleted.
- [ ] §0.4 `alpaca info.txt` gone; `.env` populated; if file was in history, keys rotated.
- [ ] §0.5 Implementation Plan v0.2 + P1 Checklist + P1 Session 1 doc all in `docs/implementation/` on `main`.
- [ ] §0.6 ADR 0002 re-read; Alpaca paper API responds ACTIVE; P1 milestone created.
- [ ] §1.1 `alpaca-py` and `apscheduler` in `pyproject.toml`; install succeeded.
- [ ] §1.2 Settings reads `WORKBENCH_TRADING_MODE` and Alpaca env vars.
- [ ] §1.3 `app/brokers/alpaca/__init__.py` exists and exports the right names.
- [ ] §1.4 `credentials.py` loads paper by default; rejects live without ack.
- [ ] §1.5 `errors.py` classifies 5xx/timeouts/connection-errors as transient.
- [ ] §1.6 `adapter.py` `submit_order` raises `NotImplementedError` referencing ADR 0002.
- [ ] §1.7 `streaming.py` skeleton in place with `NotImplementedError` placeholders.
- [ ] §1.8 All Alpaca tests pass locally (`pytest apps/backend/tests/brokers`).
- [ ] §1.9 Manual smoke against Alpaca paper succeeded.
- [ ] §1.10 PR merged on `main` via the protected workflow.

---

## Sign-off

```bash
git tag -a p1-session1-complete -m "P1 Session 1 complete: P0 follow-ups closed + Alpaca adapter foundation"
git push origin p1-session1-complete
```

Update `todo.md`:

- Mark all P0 follow-ups complete.
- Add a "P1 progress" section listing P1 Session 1 as done.
- Note the next session: **P1 Session 2** — daily asset sync, polling loops, Trade Updates lifecycle, reconciliation drift detection.

---

## Notes & Gotchas

1. **`get_settings.cache_clear()` in tests** — `get_settings` is `@lru_cache`d (set up in P0). Without `cache_clear` the second `monkeypatch.setenv` in a test file won't take effect. If you forget it, the symptom is "tests pass alone but fail in suite." If your P0 config didn't actually use `lru_cache`, drop those lines.

2. **`alpaca-py` version pinning.** The `>=0.30.0,<1.0.0` range is conservative. If you hit a breaking API change (the package is pre-1.0), pin tighter, e.g., `~=0.40.0`.

3. **`pydantic-settings` and aliases.** The `Field(alias=...)` pattern requires `model_config = SettingsConfigDict(populate_by_name=True, env_file=".env", extra="ignore")` (or similar) on your `Settings` class. P0 should already have this; double-check if env reads return empty strings.

4. **Live keys absence is not an error in paper mode.** Empty `ALPACA_LIVE_*` env values are fine while `WORKBENCH_TRADING_MODE=paper`. The tests verify this.

5. **`submit_order` raising is deliberate** — do NOT be tempted to scaffold even a passthrough implementation "for testing." Per ADR 0002 there is no order submission path before the Risk Engine. The `NotImplementedError` IS the contract.

6. **`alpaca info.txt` already in history?** Even with the file removed by PR, git history is forever. `git filter-repo` can rewrite history but it's destructive and breaks all open clones. The right move is: rotate keys, accept that history is dirty, document the incident in `docs/runbook/security-incidents.md`. Single-user private repo with rotated keys is fine.

7. **If the branch-protection PR ever fails CI on a docs-only change** — that means the CI is over-broad (running backend tests for doc PRs). Acceptable for now; refine path-based filters in a later polish pass.

8. **Don't start P1 Session 2 mid-session.** The temptation to "just wire up the polling loop while I'm here" creates a 6-hour session and an unreviewable PR. Stop after the §1 PR merges.

---

*End of P1 Session 1 v0.1.*
