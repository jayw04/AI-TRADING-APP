# ADR0043-WSS-DATA-SUBSTRATE-001 — WSS data-substrate establishment

> ## STATUS: **DRAFT — NOT EFFECTIVE, NOT INVOKED**
>
> This document authorizes nothing until it is owner-approved and an effectiveness record is
> issued. No step below may be performed on the strength of this draft.
>
> **Terminal disposition when complete: `DATA_SUBSTRATE_READY`.**

| Field | Value |
|---|---|
| Document ID | `ADR0043-WSS-DATA-SUBSTRATE-001` |
| Status | **DRAFT** |
| Predecessor | `ADR0043-LIVE-CANARY-WS5-SUCCESSOR-START-001` — terminal disposition `READY` (#609) |
| Successor | `ADR0043-WSS-TRADING-ACTIVATION-001` — **not drafted**, opens only at `DATA_SUBSTRATE_READY` |
| Runtime | `i-0fff7076ad461aa9a` (WS5), `aarch64` / `t4g.medium`, 2 vCPU / 4 GiB RAM |
| Owner | Jay Wang, GlobalComplyAI LLC |

## 0. Why this document exists separately

The predecessor authorization ended at `READY`: it proved broker identity and inert runtime
readiness. It did **not** prove that strategy 9 can produce a valid decision, because the runtime
has no data substrate at all.

Surveyed 2026-08-04 on the WS5 host:

```
/var/lib/adr0043-ws5   20 GiB, 19 GiB free — build logs, src checkouts, lost+found, evidence only
workbench.sqlite       ABSENT          DuckDB files on host      0
/opt/workbench         ABSENT          market-data credential    absent
```

Factor data is produced on the **paper box**, a different machine. Establishing a substrate on WS5
therefore involves database creation, migration, strategy seeding, factor-store provisioning,
market-data credential staging, and a refresh schedule. Combining that infrastructure work with
baseline sealing, canary orders and scheduler activation would produce an authorization that is
harder to verify, harder to stop safely, and more likely to conceal a partial failure.

These are separate readiness dimensions and must not be conflated:

```
WS5_BROKER_READINESS   = READY            (established by the predecessor; unaffected by this document)
WSS_DATA_SUBSTRATE     = ABSENT           (what this document addresses)
WSS_TRADING_ACTIVATION = NOT_AUTHORIZED   (Authorization 2 only)
```

`READY` is not weakened or reinterpreted because the substrate is missing.

## 1. Identity — bind these, and only these

```
runtime instance           i-0fff7076ad461aa9a
data volume                vol-0710769fb6981102d
workbench logical account  7
alpaca paper account       PA3E97RWHKQZ
alpaca account uuid        0fa55b0d-74d6-4a61-a361-ab154857cfb5
strategy                   WSS / strategy 9, construction v1.3 / C40 (ADR 0049)
credential key fp          ffab8796516a          secret fp   c2cab6509f1b
barred_manifest_sha256     1e9e0f94…2bf2bb36     disposition NOT_AUTHORIZED_FOR_WSS_ACTIVATION
```

`barred_manifest_sha256` is **barred from this activation programme**. It is deliberately not
described as revoked, refused, superseded or invalid — no governing record assigned it any of those
states, and inventing lifecycle semantics here would misrepresent its history.

⚠ Do not repoint account 7 to `PA34USW0Q8UO`. That is the legacy canary's account; it appears zero
times in the governing successor authorization and survives only as provenance *tags* on the WS5
runtime.

## 2. Authorized scope

Only the following, and only in the sequence of §9:

1. Merge PR #606 after hardening (§3) and exact-head Tier 3 CI.
2. Rebuild the image from the merged source, targeting `linux/arm64`.
3. Pin the new source commit, image index digest, deployable manifest digest, and platform tuple.
4. Install or select the new image on WS5 by digest.
5. Create the successor database through a dedicated one-shot checkpoint.
6. Run migrations through a separately logged migration command.
7. Verify migration head and schema digest.
8. Seed only the minimum required WSS strategy metadata and universe.
9. Provision the factor-store directory and volume layout.
10. Stage narrowly scoped market-data credentials (§7).
11. Measure capacity and select the bootstrap method (§6).
12. Execute the store bootstrap (native build or verified copy).
13. Run an initial bounded incremental factor refresh.
14. Verify per-symbol freshness and completeness (§8).
15. Install the factor-refresh schedule, initially **disabled**.
16. Execute one scheduled-equivalent refresh manually.
17. Enable **only** the factor-refresh schedule.
18. Prove no WSS order path, broker mutation path, or trading scheduler is enabled.

## 3. Prerequisite — PR #606, and the eligibility question is CLOSED

### 3.1 The governing contract

```
factor_refresh_membership != trading_authorization
```

Factor-refresh membership is a **data-integrity obligation over a shared ranking substrate**. It is
deliberately independent of strategy lifecycle status and confers no authority to execute, schedule
trading, bind broker mutation capability, or submit orders. **All registered strategies contribute
their symbols to the safety union regardless of status.**

An explicit `factor_refresh_eligible` predicate was considered and **rejected**. The reasoning is
recorded here because it will otherwise be relitigated:

A book calls `momentum_scores(n=len(ctx.symbols))` → `universe_asof` → `dollar_volume_universe`,
which returns the top-*n* **store-wide** by trailing dollar volume and applies the registered list
as a filter *afterwards*. Unregistered names therefore determine which registered names survive the
cut, and `dollar_volume_universe` drops any name whose `lastpricedate` lags — so a stale name
disappears from the pool rather than merely ranking on old data. The refresh universe must be
store-wide for that reason.

An eligibility flag would narrow nothing where the data volume actually is (the ranking-pool term is
unchanged), while creating a second readiness dependency that can silently strand a strategy with
stale data — reproducing the exact defect it was meant to police.

Isolation belongs at decision time, not data time:

```
shared factor store → store-wide ranking pool → WSS registered-symbol filter
                    → WSS exclusions and eligibility rules → WSS selected 40
```

**Required test:** a symbol registered only to another strategy may influence the store-wide top-*n*
cutoff, but must not appear in WSS's final eligible or selected set unless independently included in
WSS's registered universe.

### 3.2 Bounded refresh construction

The refresh universe must remain:

```
(ranking pool × governed headroom) ∪ all registered strategy symbols
                                   ∪ currently held symbols
                                   ∪ explicitly governed extras
```

Pin and record: `DEFAULT_UNIVERSE_SIZE`, headroom, largest registered universe size, requested pool
size, actual pool count, registered-union count, held count, extras count, total final count.

Measured values at drafting: `DEFAULT_UNIVERSE_SIZE=500`, `HEADROOM=1.5`, `LOOKBACK=63d`,
`MAX_LAG_DAYS=4`, `MIN_COVERAGE=0.98`. Strategy 9 registers **208** symbols, so on a WS5 database
seeded with only strategy 9:

```
required_pool_size = max(500, ceil(208 × 1.5)) = max(500, 312) = 500
refresh universe   = pool(500) ∪ registered(208) ∪ held(0, fresh DB) ∪ extras(SPY) ≈ 500–700
```

### 3.3 Attribution without eligibility

Retain the existing `<strategy_id>:<status>` provenance. Evidence must show which strategies
contributed symbols beyond the ranking pool. **Status is descriptive, never permissive** — this
gives auditability without allowing an omitted flag to make a strategy stale.

### 3.4 No authority coupling — the actual security boundary

Tests must prove refresh construction never: updates strategy status · enables strategy execution ·
enables either scheduler · binds broker credentials · submits a broker request · creates an
activation manifest.

### 3.5 `symbols_json` must fail closed

`registered_symbols()` currently has three distinct failure modes. Only the first is obvious; the
second and third exist because the normalising comprehension sits **outside** the `try` block:

1. malformed JSON is caught and `continue`d — the strategy is **silently omitted** from the safety
   union, which is the same class of silent-staleness failure #606 exists to prevent;
2. valid **non-array** JSON is not rejected — `{"AAPL": 1}` iterates dict *keys* and yields
   plausible but incorrect symbols with no error raised at all;
3. **scalar** JSON raises an unattributed `TypeError` and crashes the job rather than failing closed
   with the offending strategy identified.

Required contract:

```
NULL                     invalid unless explicitly permitted by schema/policy
empty string             invalid
JSON value not an array  RefreshError
array item not a string  RefreshError
blank string item        RefreshError
valid empty array        allowed ONLY for records explicitly designated non-symbol strategies;
                         INVALID for WSS/C40 and any ranked equity strategy
```

Errors must identify `strategy_id`, `strategy_status`, `failure_class` and `observed_json_type`, and
must **not** echo the raw value, which may be large or sensitive.

**Deployment safety verified.** All ten strategy rows on the live paper box currently satisfy the
strict contract — zero would raise — so this hardening cannot break the 06:00 ET production refresh:

```
1:PAPER[5]  2:HALTED[200]  3:IDLE[1]   4:IDLE[200]  5:IDLE[200]
7:PAPER[200] 8:PAPER[200]  9:IDLE[208] 10:IDLE[1]   11:IDLE[200]
```

The `[]` policy therefore has **no current instances**; it is specified prospectively.

Note that strategy 2 is `HALTED` and still contributes 200 symbols under the unfiltered union. That
is correct under §3.1, and is precisely what an eligibility flag would have silently dropped.

### 3.6 Universe digests

Add before #606 becomes the image baseline:

```
ranking_pool_digest   registered_union_digest   held_symbols_digest   final_refresh_universe_digest
```

Canonical representation: sorted uppercase symbols joined with a fixed separator, SHA-256. **Record
the count alongside every digest**, so a malformed serialisation cannot hide dropped or duplicated
entries.

The **selected-40 digest does not belong here** — the generic refresh job does not run C40
selection. It belongs to the WSS deterministic decision dry run (§8.3), preserving the separation
between data production and strategy decision evidence.

### 3.7 Run-over-run expansion control

A large increase must not fail automatically — newly registered strategies or held positions can
legitimately expand the set. Use a hard maximum tied to provider and host capacity, a review
threshold for unexpected growth, and attribution explaining added symbols. **Fail closed when growth
cannot be explained** by the pool, registered, held or extras components.

The comparison anchor is always the **last sealed successful run**, never the last attempted run. A
failed refresh must not replace the previous successful baseline.

First run has no prior and must not compute relative growth against zero or an absent baseline:

```
NO_PRIOR_REFRESH → BOOTSTRAP_BASELINE_RECORDED → COMPARATIVE_GROWTH_CONTROL_ACTIVE
```

Bootstrap run requires: total below the absolute capacity ceiling · component counts recorded ·
provenance attribution complete · final universe digest recorded · no unexplained symbols · no
duplicate normalised symbols · capacity preflight passed. From the second successful run:
`prior_count`, `current_count`, `absolute_delta`, `relative_delta`, `added_symbols_digest`,
`removed_symbols_digest`, `component_attribution`.

## 4. Image platform binding

Platform is a **first-class binding**, not an implied property of the digest. The host is `aarch64`;
an `amd64` image would pull, verify by digest, and only then fail at exec — after the digest had
been "verified."

```
os = linux · architecture = arm64 · variant = <applicable or none>
host_arch = aarch64 · instance_type = t4g.medium
```

Required sequence — fail **before** runtime execution on any mismatch:

```
resolve digest → inspect manifest platform → confirm linux/arm64 → confirm host architecture
              → pull by digest → inspect local image architecture → bounded preflight
```

Single-platform manifest: pin the manifest digest **and** the expected platform. If a multi-platform
index is ever used, pin the index digest, the selected arm64 **child manifest** digest, and the
platform tuple — an index digest can remain constant while platform selection differs.

The previously authorized deployable `sha256:c0c1b0c4…` remains valid **historical readiness
evidence** and is **not** the image eligible for substrate work once the new digest is pinned.

## 5. Database checkpoint structure

Creation and migration are mechanically separate:

```
DB_ABSENT → DB_CREATE_AUTHORIZED → DB_CREATED → MIGRATION_AUTHORIZED
          → MIGRATION_APPLIED → SCHEMA_VERIFIED
```

The image's default `Cmd` remains **barred**. It is
`sh -c "alembic upgrade head && python scripts/seed_dev_data.py && uvicorn app.main:create_app …"`,
which would migrate, seed and start the application as a side effect of container startup. Every
step uses a **complete command override**; the image declares no `ENTRYPOINT`, so an override
replaces `Cmd` entirely. No application server, seed-dev-data routine, or scheduler startup may run.

Migration evidence must capture: database path · owner and mode · pre-state absent · post-state
present · migration head · schema fingerprint · tables created · unexpected tables **zero** ·
container digest · source commit · exit code · **no broker dispatches**.

## 6. Capacity assessment and bootstrap method

The method is selected **after measurement**, not pre-committed:

```
CAPACITY_MEASURED → BOOTSTRAP_METHOD_SELECTED → NATIVE_BUILD | VERIFIED_COPY
```

Measure the paper-box store and workload first: DuckDB file size · row counts by major table ·
earliest and latest dates · ticker count · peak memory or observed working set · temporary disk
growth · build duration · provider request count · amd64-versus-arm64 dependencies.

Then set explicit WS5 limits: maximum RSS · maximum temporary disk · minimum free disk retained ·
maximum runtime · maximum provider requests · swap policy · container memory limit · failure
behaviour.

⚠ **With 4 GiB RAM, an unconstrained full-history build is prohibited.** Use bounded date
partitions, provider-side batches, DuckDB incremental inserts with checkpoints, reduced concurrency,
container memory limits, and an explicit temporary directory on the 20 GiB volume. A pre-authorized
instance-size increase is permitted only if measurement proves `t4g.medium` insufficient.
**The OS OOM killer must never be the capacity control.**

### 6.1 Verified copy from the live paper runtime

Permitted only when every condition holds. ⚠ The source is the **live production runtime** — the one
machine where a mistake reaches real positions.

A plain file copy is **not** sufficient evidence of a consistent snapshot. The existing
`cp -f "$LIVE" "$STAGE"` pattern in `factor-refresh.sh` is explicitly **not** an acceptable source
method, because another process may be writing the source. Require one of: a DuckDB-supported
consistent export/checkpoint · a quiesced application and refresh process · a filesystem or volume
snapshot with consistency controls · another explicitly validated method.

The source procedure must assert: trading books remain running safely or are deliberately quiesced ·
no live order or risk process disrupted · factor refresh not concurrently replacing the store ·
source database internally consistent · snapshot read-only with respect to strategy state. Run
outside regular trading hours unless the method is already demonstrated to impose no meaningful risk.

Also required: source digest recorded · schema/version compatibility verified · transfer encrypted ·
destination digest reproduces · no application DB, broker credential, account state or unrelated
runtime data included · incremental refresh runs afterwards · per-name freshness gates pass · WSS
dry-run output deterministic.

**Provenance inheritance must be disclosed.** A copied store is not a clean genesis store:

```
bootstrap_method          = VERIFIED_COPY
source_runtime            = <paper box identity>
source_store_generation   = <pinned generation/digest>
source_snapshot_time      = <UTC>
source_history_inherited  = true
known_staleness_episode   = 2026-07-06 through 2026-07-28
post_copy_incremental_run = completed
post_copy_per_name_gate   = passed
```

The copied history must not be represented as newly reconstructed or independently clean. The
incremental refresh and per-name verification are what establish current usability.

## 7. Market-data credentials — a separate secret class

Keep the classes separate, with separate permissions, fingerprints, receipts and verification
commands:

```
/etc/adr0043/wss-broker.env        the B4-staged Alpaca credential (already staged and verified)
/etc/adr0043/wss-market-data.env   the market-data provider credential (this document)
```

The authorization must specify: provider · allowed endpoints · read-only nature · secret names ·
fingerprint method · storage path · file ownership and permissions · **interactive owner staging
required** · prohibition on logging, CLI arguments and repository fixtures.

Staging reuses the B4 mechanism — an owner-typed interactive entry on `/dev/tty` with echo disabled,
fingerprint-verified locally, never an argument, environment variable or piped stdin. The lesson
from B4 applies unchanged: **`ssm send-command` retains command text** in SSM history and on disk.

**Do not grant new IAM permissions** unless explicitly authorized. §5 of the predecessor prohibits
broadening the instance role, and that prohibition is carried forward.

The market-data verifier must prove the file exposes only the authorized provider names, and that
the credential cannot be consumed by a WSS trading container unless that mount is explicitly
required.

## 8. `DATA_SUBSTRATE_READY` acceptance gate

"Refresh completed" is not sufficient. All must hold:

```
expected universe count recorded          all required WSS symbols represented
no unexpected universe expansion          price/factor as_of timestamp pinned
freshness threshold met PER NAME          missingness below authorized threshold
stale names below authorized threshold    duplicate symbol rows = 0
factor calculation version pinned         source data provenance recorded
factor artifact digest reproduced         refresh exit code = 0
refresh dispatch count within bound       no broker endpoint contacted
```

⚠ Freshness is assessed **per-day-per-name**, never by `max(date)`. The `max(date)` reading is what
allowed 301 of 500 names to sit frozen at 2026-07-06 while every readiness gate reported green.

### 8.3 WSS deterministic decision dry run

Plus, with order submission **disabled**:

```
WSS decision dry run can read the factor store
WSS decision dry run produces a deterministic ranked set
order submission remains disabled
```

Record, for a 40-name C40 selection from roughly 500 symbols:

```
factor_store_digest   WSS_input_universe_digest   WSS_eligible_universe_digest   WSS_selected_40_digest
```

Both the eligible-universe and selected-40 digests are required: without them a later universe drift
could produce different holdings while the code and factor files appear unchanged.

## 9. State machine

```
SUBSTRATE_AUTHORIZED
→ PR606_HARDENED_AND_MERGED
→ IMAGE_REBUILT_ARM64
→ IMAGE_PLATFORM_VERIFIED
→ DB_CREATE_AUTHORIZED → DB_CREATED
→ MIGRATION_AUTHORIZED → MIGRATION_APPLIED → SCHEMA_VERIFIED
→ STRATEGY_SEEDED
→ MARKET_DATA_CREDENTIAL_STAGED
→ CAPACITY_MEASURED → BOOTSTRAP_METHOD_SELECTED
→ NATIVE_BUILD | VERIFIED_COPY → BOOTSTRAP_VERIFIED
→ INCREMENTAL_REFRESH → INCREMENTAL_REFRESH_VERIFIED
→ FACTOR_SCHEDULE_INSTALLED_DISABLED
→ SCHEDULED_EQUIVALENT_RUN_VERIFIED
→ FACTOR_REFRESH_SCHEDULER_ENABLED
→ NON_TRADING_POSTURE_PROVEN
→ DATA_SUBSTRATE_READY
```

Any failed gate transitions to **`DATA_SUBSTRATE_FAILED`** and must immediately leave: WSS stopped ·
trading scheduler disabled · order submission blocked · no activation manifest present. A failure
does not invalidate the predecessor's `READY` disposition.

## 10. Strategy seeding

```
strategy_id             = 9
construction            = v1.3 / C40
governing_adr           = ADR 0049
account_uuid            = 0fa55b0d-74d6-4a61-a361-ab154857cfb5
broker_account          = PA3E97RWHKQZ
runtime_status          = non-trading substrate state
barred_manifest_sha256  = 1e9e0f94…2bf2bb36
```

⚠ **Do not set strategy 9 to ordinary `PAPER`** in order to make a status-filtered query include it.
Under §3.1 status does not gate refresh membership at all, so no status change is required or
permitted for data purposes.

```
factor_refresh_eligible = n/a — the concept is rejected; membership is unconditional
trading_enabled         = false
scheduler_enabled       = false
```

Account 7 must be exclusively owned by WSS — no other strategy may point at `PA3E97RWHKQZ`.

## 11. Factor-refresh scheduler

The refresh scheduler **may** be enabled under this authorization because it is a data-maintenance
scheduler. It must be named and controlled separately from the WSS trading scheduler:

```
factor_refresh_scheduler_enabled = true
wss_trading_scheduler_enabled    = false
wss_order_submission_enabled     = false
```

Pin: exact cron or systemd timer · timezone · market-calendar behaviour · retry policy ·
lock/concurrency policy · stale-data failure behaviour · maximum runtime · output path · alert or
stop condition.

⚠ Express any weekday schedule using **day names, not numerics** — APScheduler treats `0` as Monday,
so `0 14 * * 1` fires on Tuesday. ⚠ Take the timezone from the host; local shell timezone conversion
has silently returned UTC.

A failed or stale refresh must **block** later WSS execution. It must never fall back silently to
old factor data.

## 12. Explicitly prohibited

```
WSS trading scheduler activation        strategy execution with order submission
activation manifest issuance            Start-A baseline sealing
canary orders                           account mutations
enabling the default application Cmd    sharing the paper box's database or factor files directly
copying an unverified database snapshot using the old image digest after the new one is pinned
broadening the instance IAM role        creating workbench.sqlite outside §5's checkpoints
```

## 13. Mechanical stop conditions

Stop immediately on any of: account identity mismatch · credential fingerprint mismatch · image
digest **or platform** mismatch · execution of any image other than the pinned deployable · source
revision mismatch · any broker mutation attempt or unapproved endpoint · database or Alembic state
outside §5 · unexpected tables after migration · refresh universe empty · growth unexplained by
component attribution · per-name freshness gate failure · capacity limit breach · loss or overwrite
of prior authorization binding history.

## 14. Relationship to Authorization 2

`ADR0043-WSS-TRADING-ACTIVATION-001` opens **only** at `DATA_SUBSTRATE_READY`, and consumes as
inputs: merged #606 source commit · new immutable image digest and platform tuple · database schema
digest · strategy-row digest · factor-store artifact digest · universe digest · latest freshness
report · factor-refresh scheduler identity · account `PA3E97RWHKQZ` · strategy 9 / C40 identity ·
barred manifest `1e9e0f94…2bf2bb36`.

⛔ **§5.2 negative-path evidence is a hard precondition of Authorization 2**, not of this document.
Forced-expiry and partial-fill semantics were never exercised — both prior canary legs filled on
attempt 1, and "both legs filled" is not partial-fill evidence. It must be re-scoped to the required
failure semantics rather than to account 3, whose tripped breaker and inactive status are unrelated
operational hazards. It may not be silently waived at activation time.

## 15. Open items for owner ruling

1. **Bootstrap method** — deferred to measurement per §6; this draft does not pre-select.
2. **Market-data provider identity and endpoint allowlist** — §7 specifies the *shape*; the provider,
   secret names and endpoints are not yet filled in.
3. **Absolute capacity ceiling and growth review threshold** — §3.7 requires them; the numbers await
   the §6 measurement.
4. **Expiration window** for this authorization once effective.
