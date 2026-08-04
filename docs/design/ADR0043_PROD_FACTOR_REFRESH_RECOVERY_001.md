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
expiration             EARLIER OF effective_at + 168 h  OR  2026-08-10T13:00:00Z
                       (= 2026-08-10T09:00:00-04:00; 84-minute buffer before strategy 7
                        dispatches at 10:24 ET. The fixed deadline is NOT optional — do not
                        use effective_at + 168 h alone.)
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

### 3.0 Cause — owner disposition 2026-08-04

```
CONFIRMED CAUSE            deliberate interactive operator stop through sudo
HISTORICAL MOTIVE          unrecorded / NOT ESTABLISHED
WORKING HYPOTHESIS         containment pending correction of the refresh defects later
                           fixed by #606
CURRENT OWNER DISPOSITION  no standing hold remains; recovery may proceed only under #614
```

**Owner ruling:** *no standing operational hold prevents restoration of the paper production
factor-refresh producer under the final, effective #614 authorization.*

⚠ The **motive is not upgraded to a finding.** The mechanism is confirmed — `sudo systemctl stop`,
`mask`, `disable --now` by `ubuntu`, three commands in eight seconds — but no operator record
exists in `/opt/workbench/data/ops` for that window, so *why* it was stopped remains unrecorded.
The containment theory is consistent with the timing and with the state of #606 at the time; it is
not evidence. This closes the decision gate without inventing a historical explanation.

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
2026-07-31 | tickers.lastpricedate: 2026-07-31`).

```
MTIME_ANOMALY               EXPLAINED
SUBSTANTIVE_CONTENT_CHANGE  NOT OBSERVED
CAUSE                       operator inspection through a non-read-only DuckDB connection
PROMOTION BLOCK             CLEARED
```

⚠ **This is not a proof that no value changed.** Matching row counts and a matching frontier are
consistent with an unmodified store, but they do not establish that no individual cell was altered.
The claim is bounded deliberately: a substantive content change was *not observed*, not that a write
*could not* have occurred.

Two consequences follow, and they are requirements rather than commentary:

1. **Preserve the original store digest**
   (`13d74f51e52ea1cb15d83c6e22fef25f0566ed79a9180e95492f16c41a277580`) as pre-recovery evidence.
2. **Build the recovery output through a new staging file**, so the current store is never *trusted*
   merely because the anomaly is explained. The recovery's own verification gates — not this
   disposition — are what qualify the promoted store.

⚠ Practice note: opening the live store read-write while the backend holds it should use
`read_only=True`. Nothing was observed to be corrupted here.

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

### 4.2 Authorized deployment shape — single-file, refresh-only

⛔ The earlier proposal `./apps/backend/scripts:/app/scripts:ro` is **REJECTED**. A directory mount
would shadow every image-baked script the moment the long-running backend is next recreated — a
latent application-runtime change outside this recovery, surfacing long after the change that
caused it.

Deploy exactly three files to pinned host paths, digests recorded before and after, rollback copies
retained:

```
/opt/workbench/app/apps/backend/scripts/factor_refresh.py          (new file)
/opt/workbench/app/deploy/aws/docker-compose.factor-refresh.yml    (new file)
/opt/workbench/app/deploy/aws/factor-refresh.sh                    (replaces a199e855…)
```

The override maps **one file, read-only**, into the throwaway refresh container only:

```yaml
services:
  backend:
    volumes:
      - ./apps/backend/scripts/factor_refresh.py:/app/scripts/factor_refresh.py:ro
```

`factor-refresh.sh` invokes the one-off container through it:

```
docker compose -f docker-compose.yml -f docker-compose.prod.yml                -f deploy/aws/docker-compose.factor-refresh.yml                run --rm --no-deps backend python scripts/factor_refresh.py
```

Required behaviour, each covered by a test in the implementation PR:

```
one-off refresh container     sees the corrected file
running backend               unchanged
future backend recreation     unchanged
production image              unchanged
migration execution           none
other scripts shadowed        none
```

`ingest_sharadar.py` keeps using the plain compose invocation — it already ships in the image, and
substituting it would be an unreviewed change. Every `stop`/`start`/`exec` against the long-running
backend likewise uses plain compose.

No service or timer starts during Stage B. After deployment run syntax and import validation only —
no provider contact, no store change.

⚠ **Implementation is PR #617 and must be merged before this authorization becomes effective.**
Its merge commit and the three deployed-file digests are pinned in §14 as an effectiveness
prerequisite. Merging #617 deploys nothing.

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

## 14. Effectiveness prerequisites

This authorization may not become effective until every item below is complete:

```
1. ✅ §4.2 replaced with the single-file refresh-only override (directory mount REJECTED)
2. ⬜ isolated implementation PR #617 merged
3. ⬜ its merge commit + the three deployed-file digests pinned here
4. ⬜ #614 rebased onto current main
5. ⬜ exact recovery and rollback commands frozen
6. ⬜ numeric runtime, disk, request and ticker limits set
7. ⬜ final document blob and canonical SHA-256 recomputed
8. ⬜ effectiveness record submitted
```

Pins to be filled at step 3:

```
implementation merge commit    <pinned at merge of #617>
factor_refresh.py              b8b7f0395e7f6d6bbf71fff3ecab5fa483355e422441a97e3f856c9a33ed55a3
docker-compose.factor-refresh.yml  <pinned at merge>
factor-refresh.sh              <pinned at merge — supersedes a199e855…>
```

## 15. ⛔ REQUIRED — dispatch protection before Monday

**Until the producer is recovered and its refreshed generation is verified, strategies 7 and 8 must
not perform their Monday factor-consuming rebalance.**

#615 detection alone is **insufficient**. It signals; it does not stop anything. The chain today is:

```
FAIL → non-zero exit + SNS alert → [MISSING] → dispatch proceeds anyway
```

At least one explicit interlock must exist before 2026-08-10 10:24 ET:

```
producer liveness FAIL  OR  sealed generation FAIL  OR  data freshness FAIL
   → strategy 7/8 factor-consuming dispatch PREVENTED
```

### 15.1 Preferred — permanent consuming interlock

```
scheduler preflight invokes the readiness check
nonzero readiness result exits BEFORE strategy execution
no strategy-status mutation          no broker interaction
evidence records that the strategy function was never entered
```

⚠ It must be evaluated **at dispatch**, synchronously. Not strategy code reading the last watchdog
log; not assuming an alarm was acted on. It must fail closed when readiness is FAIL, missing,
unreadable, stale relative to the current dispatch, or bound to a different sealed generation or
factor-store identity.

### 15.2 Fallback — narrowly governed temporary disablement

If the permanent interlock cannot be completed in time, **temporarily disabling only the strategy 7
and 8 scheduled dispatches is safer than allowing stale-factor execution.** Any such disablement
and its restoration must be recorded separately, with the same rigour as the producer stop that
caused this incident — the absence of that record is precisely why §3.0's motive is unrecoverable.

## 16. Open items for owner ruling

1. ~~Cause confirmation~~ — **RULED** (§3.0). Mechanism confirmed; motive not established and
   deliberately not upgraded to a finding. No standing hold remains.
2. ~~Deployment shape~~ — **RULED** (§4.2). Single-file refresh-only override; directory mount
   rejected. Implemented in PR #617.
3. ~~The 09:08:39 store mtime~~ — **CLEARED** (§3.1), bounded as *not observed* rather than
   *impossible*, with the original digest preserved and recovery built through new staging.
4. **Effective date** — still open. Expiration is the **earlier of** `effective_at + 168 h` or
   `2026-08-10T13:00:00Z`, per §1.
5. **Dispatch protection** (§15) — permanent consuming interlock, or the governed temporary
   disablement fallback. **Required before 2026-08-10 10:24 ET regardless of recovery progress.**
