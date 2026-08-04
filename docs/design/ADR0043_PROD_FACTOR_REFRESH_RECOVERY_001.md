# ADR0043-PROD-FACTOR-REFRESH-RECOVERY-001 — production factor-refresh recovery

> ## STATUS: **DRAFT — NOT EFFECTIVE, NOT INVOKED**
>
> Authorizes nothing until owner-approved with an effectiveness record.
>
> **Deadline: Monday 2026-08-10.** Strategy 7 dispatches 10:24 ET, strategy 8 at 10:32 ET.
> Recovery must complete before then.
>
> This governs the **paper production runtime only**. It must not modify the WS5 substrate
> runtime, and it is not part of `ADR0043-WSS-DATA-SUBSTRATE-001` (#610).

| Field | Value |
|---|---|
| Document ID | `ADR0043-PROD-FACTOR-REFRESH-RECOVERY-001` |
| Status | **DRAFT** |
| Terminal success | `PRODUCTION_REFRESH_RECOVERED` |
| Terminal failure | `PRODUCTION_REFRESH_RECOVERY_FAILED` |
| Owner | Jay Wang, GlobalComplyAI LLC |

## 1. Bindings

```
production host        i-084f47fe4e69192e9   ip-172-31-7-230   aarch64
application path       /opt/workbench/app     (NOT a git repository; git-archive deploys)
deployed commit        b0058bf335628f8dbde09a93915314f3a1f7743b   built 2026-07-22T23:57:55Z
store path             /opt/workbench/data/factor_data.duckdb
store pre-recovery     sha256 13d74f51e52ea1cb15d83c6e22fef25f0566ed79a9180e95492f16c41a277580
                       44,576,768 bytes · mtime 2026-08-03 09:08:39 EDT
corrected source       a91fe75c041be25f116c9590d1574481443d2a42   (PR #606, merged 2026-08-04)
  factor_refresh.py    sha256 b8b7f0395e7f6d6bbf71fff3ecab5fa483355e422441a97e3f856c9a33ed55a3
  factor-refresh.sh    sha256 bc32ab6c1d8e3150933f702b7d42657b8d8ace2e02b3a71233bf5f76d8dc6b72
deployed script now    sha256 a199e855f0db74cf700209c127a96553c41c3e9f37f202252d633f2297233881
provider               Nasdaq Data Link (Sharadar)
  base                 https://data.nasdaq.com/api/v3/datatables/SHARADAR
  datasets / methods   SEP · TICKERS · ACTIONS — GET only
  credential           NASDAQ_DATA_LINK_API_KEY   fingerprint 753417c970e0
units                  workbench-factor-refresh.timer / .service   OnCalendar=Mon-Fri 06:00
                       workbench-factor-freshness.timer / .service OnCalendar=Mon-Fri 07:00
host timezone          America/New_York        Persistent=false on both timers
affected strategies    7 (sector-rotation, `24 10 * * mon`) · 8 (low-volatility, `32 10 * * mon`)
expiration             effective_at + 168 hours (must complete before 2026-08-10 10:24 ET)
```

## 2. Incident summary

The producer was **deliberately stopped**, 3h43m after that morning's successful run:

```
2026-08-03 06:03 ET  scheduled refresh RAN OK → store advanced 07-30 → 07-31, 1254 tickers
2026-08-03 07:00 ET  freshness watchdog: clean
2026-08-03 09:08 ET  store file mtime — 65 min after the run finished (⚠ unexplained, see §3)
2026-08-03 09:46 ET  ubuntu → sudo systemctl stop / mask / disable --now  (three cmds, 8 seconds)
2026-08-04 06:00 ET  NO RUN — Monday 08-03's bars never ingested
2026-08-04 07:00 ET  watchdog: "FACTOR STORE ALERT 2026-08-04 - 1 issue(s)" (SNS fired)
```

Current state is `disabled` + `inactive`, **not masked** — the unit file is intact and
`LoadState=loaded`, so the `mask` did not persist. Re-verify before relying on that.

⚠ **Do not treat the store's apparent health as evidence the producer works.** Per-name
distribution is good (1249/1254 at 07-31; the laggards look delisted), which is precisely why the
watchdog stayed green for a day. The defect is a dead producer, not stale data — yet.

## 3. Stage A — preserve evidence and determine cause

Read-only. Capture host identity, timer/service unit contents and state, last successful and last
failed execution, journal around 2026-08-03 09:46 EDT, deployed script digest, deployed commit,
store digest, SEP max date, TICKERS `lastpricedate` frontier, per-name frontier distribution,
strategies 7/8 next-run times, and the watchdog's last verdict.

**Cause must be established, not inferred from the disabled state.** Distinguish: explicit operator
command · deployment process · incident response · unit replacement · package or host update ·
failed enablement · other automation.

Evidence already gathered points to an **explicit operator command** (`sudo systemctl stop`, `mask`,
`disable --now` by `ubuntu`). No operator record exists in `/opt/workbench/data/ops` for that
window. **Working hypothesis, unconfirmed:** the producer was stopped deliberately because its
deployed implementation carries the universe and freshness defects that #606 fixes — i.e. the
owner's preferred-recovery reasoning applied by hand. Confirm with the owner before proceeding;
if that is the reason, this recovery is the sanctioned way to restart it.

### 3.1 ✅ RESOLVED — the 09:08:39 store mtime was operator inspection, not an out-of-band write

The store's mtime is `2026-08-03 09:08:39`, 65 minutes after the refresh finished at 06:03:41 and
38 minutes before the timer was disabled. Investigated in `auth.log`:

```
09:08:57  ubuntu → sudo bash -s
09:10:04  ubuntu → sudo docker exec workbench-backend python -c
                   'from app.factor_data.accessor import FactorAccessor
                    from app.factor_data.store import FactorD…'
```

An operator was **inspecting the factor store** through `FactorAccessor` / `FactorDataStore` in
exactly that window. A DuckDB connection opened without `read_only=True` touches the file and bumps
its mtime without altering data.

Corroborated by content: the store still holds `sep max = 2026-07-31` with 685,585 rows over 1,254
tickers — consistent with what the 06:03 run logged post-swap (`live sep max after swap:
2026-07-31 | tickers.lastpricedate: 2026-07-31`). Had anything written *data* after the swap, the
frontier or row counts would differ.

**Disposition:** benign operator inspection. This no longer blocks promotion.

⚠ Practice note, not a finding: opening the live store read-write while the backend holds it is
mildly risky and should use `read_only=True`. Nothing was corrupted here.

## 4. Stage B — deploy the corrected implementation

### 4.1 ⛔ Rebuilding the production image is NOT authorized

The corrected `factor-refresh.sh` invokes
`$COMPOSE run --rm --no-deps backend python scripts/factor_refresh.py`. That script runs **inside
the backend container**, and `apps/backend/Dockerfile` line 48 does `COPY scripts ./scripts` — so
`scripts/` is baked into the image and is **not** bind-mounted (`docker-compose.yml` mounts only
`data`, `strategies_user`, `bars_cache`, and a read-only gappers directory).

Verified on the host: the running backend image contains `factor_research.py` but **no
`factor_refresh.py`**. So copying the file to the host alone would leave the corrected shell script
failing immediately, and copying it into the running container would not survive a restart.

The obvious repair — rebuild the image from `a91fe75c` — is **prohibited** here:

```
deployed b0058bf (2026-07-22)  →  a91fe75c
182 commits · 502 files · 135,420 insertions
touching app/risk/engine.py · app/risk/circuit_breaker.py · app/audit/logger.py
         the entire app/brokers/** layer · THREE Alembic migrations
```

That is a major production deployment carrying risk-engine, broker, audit and **migration** change
into the live trading runtime in order to fix a data job. It also directly violates §5's
prohibition on database migrations unrelated to refresh. A narrow recovery must not become an
unreviewed 182-commit release.

### 4.2 Authorized deployment shape

Deploy to host paths, pinned, with digests recorded before and after and rollback copies retained:

```
/opt/workbench/app/deploy/aws/factor-refresh.sh              ← bc32ab6c…  (host-executed)
/opt/workbench/app/apps/backend/scripts/factor_refresh.py    ← b8b7f039…  (new file)
```

The host already carries backend sources at `/opt/workbench/app/apps/backend/`, including
`scripts/`, so the second path exists and is the natural home for it.

Then make the **one-off refresh container** see the host copy, without touching the running
backend. Recommended: add a read-only mount for the backend `scripts` directory to the backend
service in `docker-compose.prod.yml`:

```yaml
- ./apps/backend/scripts:/app/scripts:ro
```

`docker compose run --rm --no-deps backend …` re-reads the compose files per invocation, so the
one-off refresh container picks this up **while the long-running backend container keeps its
existing configuration until it is next recreated**. No restart, no image rebuild, no migration.

⚠ Consequence to accept explicitly: when the backend container *is* next recreated, host `scripts/`
will shadow the image's. The host tree is the same `b0058bf` git-archive the image was built from,
so the contents are near-identical plus the new file — but this is a persistent behavioural change
and belongs in the authorization, not in someone's memory.

**Alternative** if that shadowing is unwanted: a follow-up PR that has `factor-refresh.sh` mount the
scripts directory explicitly into its own one-off container, pinned to that newer commit. Cleaner
provenance, costs one review cycle. Both fit before 2026-08-10; the owner should pick.

No service or timer starts as part of Stage B. After deployment, run syntax and import validation
only — no provider contact, no store change.

## 5. Scope

**Authorized:** read-only evidence collection · cause determination · deployment of the corrected
implementation per §4.2 · exactly one bounded manual refresh · verification · timer enablement ·
observation of one execution · confirmation that strategies 7 and 8 read the new generation.

**Prohibited:** broker order activity · strategy execution or status changes · account mapping
changes · any WSS or WS5 change · database migrations · IAM expansion · instance replacement or
resize · activation manifests · trading-scheduler changes · production image rebuild (§4.1).

## 6. Stage C — one bounded manual refresh

Timer remains **disabled** throughout. Exactly one run, using the corrected implementation.

```
provider rows          ≤ 900,000 for the authorized day (provider cap ~1,000,000)
runtime                explicitly bounded and measured
concurrency            one refresh only
free disk retained     explicitly pinned before start
strategy dispatch      blocked during store promotion
```

The universe must be built by the #606 rule — ranking pool ∪ **all registered strategy symbols
regardless of status** ∪ held ∪ governed extras — and the run must emit: component counts and
symbol sets · the four universe digests with counts · growth-control result · per-name coverage ·
stale-name list · provider request and row counts · staging-store digest · verification result.

⚠ SEP and ACTIONS are **per-ticker** pulls; TICKERS is a single full-table pull. The per-ticker
shape is what can exhaust the daily cap, which is why an explicit ticker list is mandatory and no
full-market pull exists.

## 7. Stage D — promotion

Promote only when **all** hold:

```
refresh exit code 0            universe artifact integrity PASS      growth control PASS
per-name coverage PASS         lastpricedate gate PASS               duplicate symbol rows 0
provider ceiling respected     no unexplained universe member        no registered/held member omitted
```

Promotion is atomic via the corrected script's sealed-anchor behaviour. The sealed artifact
advances **only after** verification passes, the swap succeeds, and the promoted store is reopened
and verified. A failed attempt must never replace the previous sealed anchor.

## 8. Stage E — post-refresh verification

Capture: new store digest · new sealed-universe artifact digest · SEP max date · TICKERS
`lastpricedate` frontier · per-name frontier distribution · missing and stale names · a factor-read
dry run for strategy 7 and for strategy 8 · **broker dispatch count = 0** · **order mutation count
= 0**.

Delisted or structurally inactive symbols may legitimately remain old, but each must be attributed
explicitly. They must not cause silent inclusion or exclusion in ranking.

## 9. Stage F — enable the producer

Only after §7 and §8 pass. Verify unit contents, then the schedule and timezone before enabling.

```
OnCalendar=Mon-Fri 06:00   ✅ day NAMES, not numerics
Timezone=America/New_York  ✅ host-confirmed
Persistent=false           ⚠ a missed trigger is NOT replayed on boot — intended here
```

⚠ Day names matter: numeric weekday fields are ambiguous across cron and APScheduler semantics —
`0 14 * * 1` fires **Tuesday** under APScheduler, which treats 0 as Monday. The existing units
already use names; keep it that way.

Enable, then confirm: timer enabled · timer active · next trigger present · next trigger timestamp
correct · service inactive between runs. Enabling must not immediately fire an unintended duplicate
refresh.

## 10. Stage G — observe recovery

Before closing, verify **either** one actual scheduled refresh completes successfully, **or** one
scheduled-equivalent invocation using the exact service command completes, followed by timer
enablement and next-trigger verification.

Then confirm: sealed artifact advanced · store frontier advanced · freshness monitor PASS ·
producer-liveness check PASS · strategies 7 and 8 reference the current generation.

## 11. Stop conditions

Stop immediately on: source or script digest mismatch · production-host identity mismatch ·
provider credential mismatch · unexpected endpoint or HTTP method · provider row/request limit
breach · staging-store verification failure · unexplained universe growth · per-name freshness
failure · failed atomic promotion · missing rollback artifact · timer schedule ambiguity · any
broker request or mutation attempt · any unexpected strategy or account-state change.

```
PRODUCTION_REFRESH_RECOVERY_FAILED
  timer disabled · previous sealed store retained · dispatch interlock closed · evidence preserved
```

## 12. Success state

```
PRODUCTION_REFRESH_RECOVERED
  corrected implementation deployed      manual refresh verified
  sealed store advanced                  timer enabled and active
  producer liveness confirmed            freshness confirmed
  strategies 7 and 8 safe for the next scheduled dispatch
```

## 13. Mandatory follow-up — watchdog hardening

A separate, isolated PR. **Not** bundled with this recovery, with #610, or with candidate-image
work. Required invariant:

```
factor-refresh producer disabled, inactive, missing, or overdue
→ freshness/readiness FAIL
→ factor-consuming strategy dispatch blocked
```

Independently verify: timer enabled · timer active · next trigger exists · expected prior trigger
occurred · last execution succeeded · sealed refresh artifact advanced · store frontier within
tolerance · per-day-per-name freshness passes.

Producer liveness and data freshness are **separate mandatory conditions**. This incident is the
proof: the watchdog reported clean while the producer was already dead, and only escalated a day
later when the data drifted. A fresh store must never conceal a dead producer.

## 14. Open items for owner ruling

1. **Cause confirmation** — was the 2026-08-03 09:46 stop deliberate containment pending #606?
2. **§4.2 deployment shape** — compose read-only mount (recommended) versus a follow-up PR that
   mounts scripts from within `factor-refresh.sh`.
3. ~~The 09:08:39 store mtime~~ — **RESOLVED** (§3.1): operator inspection via
   `FactorAccessor`/`FactorDataStore`, which bumps mtime without altering data. Corroborated by
   unchanged frontier and row counts. No longer blocks promotion.
4. **Effective date**, which sets the 168-hour expiration against the 2026-08-10 deadline.
