# Runbook — EAD / GOVCONTRACT-001 deploy gate

The EAD code (Phases 0–2) is on `main`; **nothing has touched the live system yet.** This runbook
is the ordered, data-gated sequence to bring GOVCONTRACT-001 to a recorded verdict. Every command
below has been dry-run / import-validated offline (2026-07-05). Operate the live app on the box
(**never** start the laptop stack — CLAUDE.md RUNTIME note).

Conventions (from `aws-migration.md`): box = `ssh workbench`; app dir `/opt/workbench/app`; backend
service = `backend`; the container `.env` is rendered from SSM by `provision-from-s3.sh` (already
extended to include `QUIVER_API_KEY`). The event store is the DuckDB file at
`get_settings().event_store_path` (`data/event_store.duckdb`, backend-relative — inside the container's
`data` volume).

⚠ Before any `aws …` command on the laptop: clear Machine-scope env creds + point at the Norton CA
bundle (see the `aws_migration_phase1` memory). Prefer running `aws` on the box (its IAM role covers SSM).

---

## Step 1 — Create the Quiver token in SSM (secret; owner)

```bash
aws ssm put-parameter --region us-east-1 --type SecureString \
  --name /workbench/prod/QUIVER_API_KEY --value '<the Quiver token>'
```

Verify (no value printed):
```bash
aws ssm get-parameter --region us-east-1 --name /workbench/prod/QUIVER_API_KEY \
  --query 'Parameter.Name' --output text
```

## Step 2 — Deploy the merged code + re-render the box `.env`

Deploy `main` to the box per the standard recipe (`aws_migration_phase1` memory). The re-provision
re-renders `.env` from SSM, which now includes `QUIVER_API_KEY`. Confirm it landed (name only):

```bash
ssh workbench "grep -c '^QUIVER_API_KEY=.\+' /opt/workbench/app/.env"   # expect 1
```

## Step 3 — Migrate the Event Store (schema converges on open; backfill is the gated part)

The schema (11 EAD columns + the `corporate_events_pit` view) converges automatically the first time
the new backend opens the store, so the app is safe post-deploy. The **backfill** is the signed-off
step and takes its own timestamped backup first.

```bash
# dry-run first (reports columns-to-add + backfill preview; makes no changes)
ssh workbench "cd /opt/workbench/app && docker compose exec -T backend \
  python scripts/migrate_event_store_ead.py --dry-run"

# apply (auto-writes data/event_store.duckdb.pre-ead-<ts>.bak, then backfills Form-4 rows)
ssh workbench "cd /opt/workbench/app && docker compose exec -T backend \
  python scripts/migrate_event_store_ead.py"
```

## Step 4 — INSIDER-001 reproduction-diff (the invariance gate — do NOT skip)

Prove the Form-4 backfill moved nothing. Run the reproduction against the **backup** and the
**migrated** store; the outputs must be identical.

```bash
BAK=$(ssh workbench "ls -t /opt/workbench/app/data/event_store.duckdb.pre-ead-*.bak | head -1")
ssh workbench "cd /opt/workbench/app && docker compose exec -T backend \
  python scripts/run_insider_reproduction.py --events-db '$BAK'      > /tmp/insider_pre.txt"
ssh workbench "cd /opt/workbench/app && docker compose exec -T backend \
  python scripts/run_insider_reproduction.py                          > /tmp/insider_post.txt"
ssh workbench "diff /tmp/insider_pre.txt /tmp/insider_post.txt && echo 'INVARIANT OK'"
```
A non-empty diff **blocks** — restore from the `.bak` and investigate before proceeding.

## Step 5 — Ingest government contracts

Full per-ticker history over the factor universe (the study needs history), then a live pull for the
tail. `SEC_EDGAR_USER_AGENT` must be set (the Security Master builds its name map from EDGAR).

```bash
ssh workbench "cd /opt/workbench/app && docker compose exec -T backend \
  python scripts/ingest_govcontracts.py --factor-universe 500"
ssh workbench "cd /opt/workbench/app && docker compose exec -T backend \
  python scripts/ingest_govcontracts.py --live"
```

Data-quality check (license status, eligibility, unresolved-by-reason, mapping-failure rate):
```bash
ssh workbench "cd /opt/workbench/app && docker compose exec -T backend python - <<'PY'
from app.altdata.events.store import EventStore
from app.services.data_quality import build_govcontract_data_quality, render_report
with EventStore(read_only=True) as s:
    print(render_report(build_govcontract_data_quality(s)))
PY"
```

## Step 6 — USAspending cross-check → calibrate the disclosure lag (exit gate)

```bash
ssh workbench "cd /opt/workbench/app && docker compose exec -T backend \
  python scripts/quiver_usaspending_crosscheck.py --sample 100"
```
Read the **recipient / agency match rate** (a low rate = a §2.6a kill signal) and the **availability
lag** distribution. Set `DISCLOSURE_LAG_DAYS` in `app/altdata/quiver/govcontracts.py` to the suggested
p90, **re-ingest** (Step 5) so `available_time` reflects the calibrated lag, and commit that one-line
change through a PR.

## Step 7 — Lock the two pre-registration placeholders

In `TradingWorkbench_GOVCONTRACT001_Plan_v0.1.md`, replace the placeholders with locked values
(commit via PR, **before** the run — pre-registration discipline):
- **§2 materiality floor** (award-size threshold).
- **§6 cost model** (per-side commission + spread/slippage for the liquidity tier).

## Step 8 — Run GOVCONTRACT-001 once → record the verdict

```bash
ssh workbench "cd /opt/workbench/app && docker compose exec -T backend \
  python scripts/run_govcontract001.py --hold-days 20"
```
If it stamps **INTERIM** (< 100 benchmarked events), that is **not** the registered verdict — ingest
more history / revisit eligibility; do **not** weaken the gates to reach 100 (plan §5). Once the floor
is met, this is the one registered run: capture the Evidence JSON, write it to
`docs/implementation/evidence/govcontract_001/`, update `programs.py` (status → `validated` /
`inconclusive` / `rejected`) + the Research Program Registry doc, all via PR.

---

## Rollback

- **Backfill wrong:** restore `data/event_store.duckdb` from the `pre-ead-<ts>.bak` (Step 3).
- **Quiver disabled:** unset/rotate `QUIVER_API_KEY` in SSM + re-provision — empty key disables ingestion (no code change).
- The migration/ingest are **read-only w.r.t. the order path** (14th CI invariant); none of this can reach a broker.

## Offline validations already done (2026-07-05, laptop)
`--help`/import OK for all four scripts; `migrate_event_store_ead.py --dry-run` on a scratch legacy
store (reports the 11 columns + backfill preview); `run_govcontract001.py` against an empty store
prints the graceful "ingest first" message; `mypy app` (323 files) + ruff + `tests/altdata/` all green.
