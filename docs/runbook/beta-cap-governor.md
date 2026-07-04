# Runbook — Enforcing the equity-beta-cap governor (PORT-001 lever #2)

**Scope:** flipping `combined-book` (strategy id=9, live paper acct 7) from the governor's
**report-only dry-run** to **enforcement** (`enforce_beta_cap=True`), after reviewing a live
rebalance's dry-run output. Owner priority #2. All commands run **on the AWS box** (`ssh workbench`);
the laptop is warm standby and must stay stopped.

## What the governor is

`app/research/factor_lab/beta_cap.py::cap_equity_beta` — a **de-risk-only** governor. When the book's
look-through *equity-beta risk contribution* (single stocks + SPY/EFA/EEM) exceeds `beta_cap_max_rc`
(default **0.80**), it scales those equity-beta weights **down** (raising cash) until within budget;
bonds/gold/DBC/UUP/KMLM are never touched. Wired into `combined_book.py::_rebalance` via
`_maybe_beta_cap`. It only runs **inside the weekly rebalance** (`40 14 * * mon` = Mon 14:40 UTC).

Shipped state (PR #342, deployed 2026-07-03): `enforce_beta_cap=False`, `beta_cap_report_only=True`
→ the would-be haircut is **logged but not applied**. Each rebalance writes a `signals` row
(`symbol=PORTFOLIO`, `payload.reason="beta_cap"`, `enforced=false`) carrying the full report.

## Step 1 — Review the dry-run (after a Monday rebalance)

The dry-run doesn't exist until a rebalance runs. After Mon 14:40 UTC, read the logged report:

```bash
ssh workbench
cd /opt/workbench/app
# Interim path: the script was scp'd into the bind-mounted data dir on 2026-07-04 (survives
# restarts) so it's runnable before it's merged + deployed into the image's scripts/ dir.
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T backend python /app/data/review_beta_cap_dryrun.py
# After a proper deploy, the canonical path is instead:  python scripts/review_beta_cap_dryrun.py
```

- Exit **0** → a dry-run was found; the script prints the report + a flip recommendation.
- Exit **2** → nothing logged in the window. The rebalance may not have run — check the engine logs
  (`... logs backend | grep -i rebalance`), confirm the market was open, then re-run.
- `--since-days N` widens the window; `--all` prints every dry-run found.

Two outcomes the script interprets for you:

| Report | Meaning | Flip decision |
|---|---|---|
| `applied=false` (RC ≤ 0.80, "within budget") | Enforcing changes nothing right now | **Safe no-op flip** — the governor only ever acts if a future rebalance breaches the cap |
| `applied=true` (RC > 0.80) | Enforcing **would** trim equity ×`scale_equity_beta`, raise `cash_freed` | **Owner decision** — flip only if the haircut magnitude is acceptable |

> The offline preview (`scripts/preview_beta_cap_live.py`, uncommitted) indicated RC ≈ 0.98 →
> equity ×0.37 on partial data, so `applied=true` with a material haircut is the likely case.
> **Trust the logged dry-run over the preview** — the preview approximates equity momentum from
> Alpaca bars rather than the Sharadar factor store.

## Step 2 — Flip `enforce_beta_cap=True`

Do this **after** the Monday review, which leaves us maximally far from the *next* rebalance — honoring
the no-reload-near-rebalance rule ([[feedback_no_reload_near_rebalance]]). Enforcement takes effect on
the **next** rebalance (the following Monday), since the governor only runs during a rebalance.

### Path A — API PUT (preferred: audit-logged) — *needs a working box login for user 7*

The PUT endpoint requires the strategy be **IDLE** and writes an `AuditAction.STRATEGY_UPDATED` entry.
It **replaces** `params_json` wholesale, so send the full params with only `enforce_beta_cap` changed.

```
# authenticate as user 7 → POST /strategies/9/stop → PUT /strategies/9 {params: <full params, enforce_beta_cap:true>} → POST /strategies/9/start
```

⚠ Box login for user 7 currently **401s** (box password ≠ laptop's). If you fix that first, prefer
this path — a risk-relevant config change **should** be audit-logged (CLAUDE.md: risk-limit edits are
consequential).

### Path B — direct params edit + restart (proven fallback; **NOT audit-logged**)

Used for the v1.1/v1.2 re-registrations on the box. `restart backend` triggers resume-on-boot, which
re-registers id=9 from the `strategies` row (fresh `params_json`).

```bash
ssh workbench
cd /opt/workbench/app
# 1) back up the live DB first
sudo cp data/workbench.sqlite data/workbench.pre-betacap-flip.sqlite
# 2) set enforce_beta_cap=True in params_json (JSON-safe, in-container)
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T backend python - <<'PY'
import sqlite3, json
from datetime import UTC, datetime
db = "/app/data/workbench.sqlite"
c = sqlite3.connect(db); cur = c.cursor()
p = json.loads(cur.execute("select params_json from strategies where id=9").fetchone()[0])
assert p.get("enforce_beta_cap") is False, f"unexpected pre-state: {p.get('enforce_beta_cap')}"
p["enforce_beta_cap"] = True            # leave beta_cap_report_only=True so logging continues
cur.execute("update strategies set params_json=?, updated_at=? where id=9",
            (json.dumps(p), datetime.now(UTC).isoformat()))
c.commit()
print("enforce_beta_cap ->", json.loads(cur.execute("select params_json from strategies where id=9").fetchone()[0])["enforce_beta_cap"])
PY
# 3) re-register with the new params
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml restart backend
```

Because Path B bypasses the API, **no audit entry is written**. Record the change out-of-band: note it
in the resume-state memory and (optionally) write a manual `STRATEGY_UPDATED`-equivalent audit note.

## Step 3 — Verify

```bash
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T backend python -c "
import sqlite3, json
c=sqlite3.connect('file:/app/data/workbench.sqlite?mode=ro', uri=True)
p=json.loads(c.execute('select params_json from strategies where id=9').fetchone()[0])
print('enforce_beta_cap =', p['enforce_beta_cap'], '| report_only =', p['beta_cap_report_only'])
"
# expect: enforce_beta_cap = True | report_only = True
```

Also confirm the engine re-registered cleanly (`... logs backend | grep strategy_registered`) and
`healthz` is green. **First enforcement = the next Monday rebalance** — after which re-run
`review_beta_cap_dryrun.py`: the row will show `enforced=true` and, if it acted, `applied=true` with
the real applied scale.

## Rollback

Same as Path B with `p["enforce_beta_cap"] = False`, then `restart backend`; or restore
`data/workbench.pre-betacap-flip.sqlite` and restart. The book reverts to report-only on the next
rebalance (nothing to unwind intra-week — the governor only acts at rebalance time).

## Related

- Review script: `apps/backend/scripts/review_beta_cap_dryrun.py`
- Offline preview: `apps/backend/scripts/preview_beta_cap_live.py` (uncommitted)
- Governor + wiring: `app/research/factor_lab/beta_cap.py`, `strategies_user/templates/combined_book.py`
- PORT-001 lever #2: PR #342 (`f33805d`). See [[port001_capability_onboarding]].
