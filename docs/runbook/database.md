# Database operations

The Trading Workbench uses **SQLite** for MVP via SQLAlchemy 2.x + Alembic. Two DB files exist depending on how you run:

| Path | When it's used |
|---|---|
| `apps/backend/data/workbench.sqlite` | Standalone backend (uvicorn directly). Cwd is `apps/backend/`, env's relative `./data/...` resolves there. |
| `./data/workbench.sqlite` (repo root) | Docker Compose. The backend container's cwd is `/app/`, mounted from host's `./data/`. |

They're independent. Resetting one does not reset the other.

## Reset everything (nuke + reseed)

> Destroys all local data. Safe only because P0 has no real trading data.

**Standalone:**

```powershell
cd apps\backend
.venv\Scripts\Activate.ps1
rm data\workbench.sqlite                    # PowerShell: Remove-Item .\data\workbench.sqlite
alembic upgrade head
python scripts\seed_dev_data.py
```

**Docker:**

```bash
# Stop the stack
./scripts/dev.sh down

# Wipe the host-side data dir
rm -f data/workbench.sqlite

# Bring it back up — the backend container self-bootstraps alembic + seed
./scripts/dev.sh
```

## Inspect tables

```powershell
sqlite3 data\workbench.sqlite ".tables"
# expected: accounts  alembic_version  audit_log  symbols  system_config  users

sqlite3 data\workbench.sqlite ".schema users"
sqlite3 data\workbench.sqlite "SELECT id, email FROM users;"
sqlite3 data\workbench.sqlite "SELECT id, broker, mode, label FROM accounts;"
sqlite3 data\workbench.sqlite "SELECT COUNT(*) FROM symbols;"
```

If you don't have `sqlite3` installed, use the [`DB Browser for SQLite`](https://sqlitebrowser.org/) GUI or VS Code's SQLite extension.

## Generate a new migration

After editing a model in `apps/backend/app/db/models/`:

```powershell
cd apps\backend
.venv\Scripts\Activate.ps1
alembic revision --autogenerate -m "describe the change in past tense"
```

**Always read the generated file** before committing. Autogenerate misses things:
- Server-side defaults
- Check constraints
- Column comment changes
- Enum value changes (it'll often emit a DROP+CREATE that loses data)

Then `alembic upgrade head` to apply.

## Stamp an existing DB

If your DB was created out-of-band (rare) and Alembic says "Can't locate revision":

```powershell
alembic stamp head      # tells Alembic the DB matches head without running anything
```

Only safe if you genuinely know the schema is up to date.

## Downgrade / roll back a migration

```powershell
alembic downgrade -1
```

In production this would need backup-first; in P0 just nuke + reseed (see top).

## Seed data conventions

`scripts/seed_dev_data.py` is **idempotent** — running it multiple times produces no duplicates. Keep it that way as new models land: every insert should be guarded by an existence check.

Current seed:
- `users(id=1, email=$WORKBENCH_DEV_USER_EMAIL)`
- `accounts(id=1, user_id=1, broker='alpaca', mode='paper', label='Alpaca Paper')`
- 10 `symbols`: AAPL, MSFT, NVDA, SPY, QQQ, TSLA, AMD, GOOGL, AMZN, META
- `system_config(key='mode', value='paper')`

## Future: Postgres

We'll migrate when single-process SQLite stops being enough (concurrent writes from multiple strategy processes, or hosted deployment). The model code targets SQLAlchemy's generic types so the migration should be a config change + `alembic upgrade head` against the new DB. Don't bake SQLite-specific SQL into application code.
