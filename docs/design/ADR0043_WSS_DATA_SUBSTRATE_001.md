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

### 1.1 Terminology — what "account 7" is, and is not

**"Account 7" is only the internal Workbench account mapping.** The object being prepared here, and
later activated under Authorization 2, is **WSS / strategy 9**. The broker account is
`PA3E97RWHKQZ`. The internal account row is **not independently activated** — there is no such thing
as "activating account 7," and describing the goal that way is what produced earlier confusion
between this account 7 and the legacy canary.

`barred_manifest_sha256` is **barred from this activation programme**. It is deliberately not
described as revoked, refused, superseded or invalid — no governing record assigned it any of those
states, and inventing lifecycle semantics here would misrepresent its history.

⚠ Do not repoint account 7 to `PA34USW0Q8UO`. That is the legacy canary's account; it appears zero
times in the governing successor authorization and survives only as provenance *tags* on the WS5
runtime.

## 2. Scope — preparation is not authorized execution

Repository work and CI do not invoke this authorization and do not touch WS5. They are therefore
**prerequisites to effectiveness**, not authorized actions against the runtime. Separating them
means the effectiveness record binds *concrete artifacts* rather than authorizing future unknown
ones.

### 2.1 Pre-effectiveness prerequisites — completed before this document may become effective

```
✅ #606 hardened and merged        squash a91fe75c041be25f116c9590d1574481443d2a42  2026-08-04T18:21:00Z
✅ exact merged source commit      a91fe75c041be25f116c9590d1574481443d2a42
✅ Tier 3 CI evidence              run 30933387628 on head eac0ecae53d4… → success
                                   Python CI Gate SUCCESS · Python FULL (backend) SUCCESS
                                   36 tests / 51 cases · ruff, format, mypy (454 files), bash -n clean
✅ merged tree verified            exactly 3 files: factor_refresh.py, its tests, factor-refresh.sh
✅ no automatic deployment         ci.yml performs no deploy step; no host unit pulls from git;
                                   /opt/workbench/app is not a git repository
✅ linux/arm64 candidate image built          native on WS5, 2026-08-04T18:48:19Z → 18:51:09Z, exit 0
✅ index/manifest digest + platform tuple     pinned in §2.1.1
✅ candidate image scan evidence              ECR BASIC, COMPLETE, zero findings
✅ nothing deployed, pulled, selected or executed on WS5
```

### 2.1.1 Candidate artifact bindings

```
source commit          a91fe75c041be25f116c9590d1574481443d2a42   (head_matches_pin = true)
git tree object        f216ec78c796185e98dc8c45c2b9173cc7ad08d0
source acquisition     shallow anonymous fetch of the pinned commit; detached checkout; tree clean
build context          apps/backend        (docker-compose.yml pins `context: ./apps/backend`)
context tree sha256    495600586143bcb8d291bab1d677e1ad4ee736b1df89b83186c734e66da73ab3
Dockerfile sha256      ff8406ac5743fbe8e0707cf16b15e32538bf0b792f3e5c5f219c998881e820e8

repository             219024422756.dkr.ecr.us-east-1.amazonaws.com/adr0043-canary-ws5
tag                    candidate-a91fe75c041b        (new tag; nothing overwritten)
OCI index digest       sha256:fc390cf5cb5fbd43d9d4c6bc256b19db9c7607a3b011d51dc8e28f740e30f31f
arm64 DEPLOYABLE       sha256:d771197fa4c94bfd85e417f584002e0d811e9bdefa85f863066392870f950f56
attestation manifest   sha256:583cb64635c34da8d0b1a1d5e29fc11e11c7a31bd4ec802c73d8ae0a984fa6aa
config digest          sha256:1d7f14392e27bc54aafff0d739e38f43bb98bba1309643add610a5177398f8f4
platform tuple         os=linux · architecture=arm64 · variant=none
size / pushed          322,792,101 bytes · 2026-08-04T18:51:08Z

host                   i-0fff7076ad461aa9a (aarch64, t4g.medium, 3825 MiB)
buildx / buildkit      v0.36.0 / v0.31.2
builder                wss-arm64-candidate-builder (docker-container), memory-capped 2560m,
                       BUILDKIT_MAX_PARALLELISM=1 — removed after evidence capture
provenance / SBOM      --provenance=true --sbom=true; syft v1.11.0 via buildkit-syft-scanner
vulnerability scan     ECR BASIC (scanOnPush=true) — status COMPLETE, findings: none
```

⚠ **Pin the arm64 child manifest, not only the index.** An index digest can remain constant while
platform selection differs, so §4's verification resolves `d771197f…` explicitly. The tag is a
convenience label; the digests are the binding.

### 2.1.2 Non-invocation proofs

Construction and publication only — the candidate never entered the runtime image store:

```
candidate tag in local image store        0
candidate index digest in local store     0
arm64 child digest in local store         0
container created from the candidate      none
unit / compose / config referencing it    none
local image store after build             c0c1b0c4… (authorized deployable, untagged)
                                          37e52bc9… (retired PRIOR_STAGE1_ARTIFACT)
                                          moby/buildkit:buildx-stable-1
posture vs pre-build baseline             images 3 = 3 · containers 1 = 1 · builder removed
WS5 inert                                 workbench.sqlite ABSENT · 0 workbench services running
                                          B4 credential + receipt intact · 1 Stage-C evidence file
```

`--push` was used **without `--load`**, so the published artifact bypassed the ordinary local image
store entirely rather than relying on "presence ≠ execution". The single container on the host is
the retained Stage-C evidence container, `Exited (0)`, unchanged.

⚠ The candidate remains **barred from pulling, selection or execution on WS5** until this document
becomes effective. Building it conferred no operational authority.

These may proceed at any time. Merging #606 must not automatically deploy to the paper box or WS5,
must not select or execute any image on WS5, and must not change any database, credential, factor
store, scheduler or host state. The arm64 image is built and pushed as a **non-deployed candidate
artifact** so its exact digests and platform can be inserted into this document.

### 2.2 Authorized scope once effective

Only the following, and only in the sequence of §9:

1. Verify the pinned source commit, image digests and platform tuple.
2. Pull/select the pinned image on WS5 by digest.
3. Run the bounded image preflight (§4).
4. Create the successor database through a dedicated one-shot checkpoint.
5. Run migrations through a separately logged migration command.
6. Verify migration head and schema digest.
7. Seed only the minimum required WSS strategy metadata and universe.
8. Provision the factor-store directory and volume layout.
9. Stage narrowly scoped market-data credentials (§7).
10. Measure capacity and select the bootstrap method (§6).
11. Execute the store bootstrap (native build or verified copy).
12. Run an initial bounded incremental factor refresh.
13. Verify per-symbol freshness and completeness (§8).
14. Install the factor-refresh schedule, initially **disabled**.
15. Execute one scheduled-equivalent refresh manually.
16. Enable **only** the factor-refresh schedule.
17. Prove no WSS order path, broker mutation path, or trading scheduler is enabled.

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
valid empty array        RefreshError — invalid for EVERY strategy row under the current schema
```

The empty array is rejected outright rather than excepted. The draft previously allowed it for
"records explicitly designated non-symbol strategies," but the current data model has **no such
field and no authoritative designation**, so that exception could not be mechanically enforced —
it would be an informal carve-out that the schema cannot check. All ten current rows are non-empty,
so nothing is lost. A future non-symbol strategy introduces an explicit schema/policy amendment at
the point it actually exists.

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
container memory limits, and an explicit temporary directory on the 20 GiB volume.
**The OS OOM killer must never be the capacity control.**

**If `t4g.medium` proves insufficient, stop at `CAPACITY_INSUFFICIENT`.** Instance resizing is
**not** authorized by this document. It requires a controlled replacement or an amendment before
continuing — resizing introduces downtime and changes a bound runtime property, and this document
names no allowed instance types, memory ceiling, cost ceiling or replacement procedure. Stop and
return for a ruling rather than improvising a ladder.

⚠ Resizing implies a stack operation on an adopted resource. The 2026-07-27 incident, in which a
CloudFormation update **replaced a live EC2 instance and destroyed its root volume**, is the
governing precedent: any such change is create-change-set first, check for `Replacement: True`, and
never during regular trading hours.

### 6.1 Provisional ceilings governing the measurement itself

The measurement stage must not consume resources without limit, so two levels apply *before* the
final numbers are known:

```
measurement safety ceiling   RSS ≤ 2.0 GiB · temp disk ≤ 4 GiB · runtime ≤ 30 min
                             provider requests ≤ 2,000 rows-equivalent sampling only
                             read-only against the source; no writes to the paper box
bootstrap operational ceiling RSS ≤ 3.0 GiB · temp disk ≤ 12 GiB · min free disk retained ≥ 4 GiB
                             runtime ≤ 6 h · provider rows ≤ 900,000/day (below the ~1M cap)
                             container memory limit set explicitly; swap disabled
```

These are provisional and bound the work that determines the final numbers. Exceeding either is
`CAPACITY_INSUFFICIENT`, not an occasion to raise the ceiling in place.

### 6.1.2 FROZEN operational limits — derived from §6.1.1, binding from here

The measurement is complete, so these supersede the provisional bootstrap ceiling above. Every
value carries the measured basis it was set from, and headroom is deliberate rather than arbitrary.

```
                              FROZEN        projected/measured        basis
maximum RSS                   3.0 GiB       « 3.0 GiB                 batched DuckDB inserts
maximum temporary disk        12 GiB        < 1 GiB                   store is 43 MiB at 685k rows
minimum free disk retained    4 GiB         19 GiB available          destination headroom
maximum staging-store size    500 MiB       ~27 MiB projected         ~18x headroom
maximum runtime               6 h           ~25–60 min                ~2,500 sequential requests
maximum provider rows/day     900,000       ~627,000 projected        provider cap ~1,000,000
maximum provider requests     3,000         ~2,500 projected          SEP+ACTIONS per-ticker, TICKERS bulk
concurrency                   1             —                         one refresh only, ever
stale-lock policy             12 h          2 × max runtime           break with alert, never silently
```

Universe-growth controls, matching the constants #606 already ships:

```
hard maximum universe count   2,000         DEFAULT_MAX_UNIVERSE      vs ~500–700 expected
review threshold              0.25          DEFAULT_GROWTH_REVIEW     report, do not fail
expected normal range         500 – 900     pool 500 ∪ registered 208 ∪ held ∪ extras
```

The hard maximum is a genuine stop, not a target: at ~700 expected it sits nearly 3× above normal,
so reaching it means the universe is being driven by something outside the authorized formula.
Breach ⇒ `CAPACITY_INSUFFICIENT`. **Never resize the instance or raise a limit in place.**

### 6.1.1 CAPACITY_MEASURED — the measurement, and what it changed

Measured 2026-08-04, read-only sampling against the paper production store. **The store is far
smaller than the "years of market history" framing assumed**, which makes both bootstrap methods
cheap and moves the decision from cost to governance.

```
measurement_sha256 = 72506343a79677ba52a3ba850fc87ccad324118dca4e5b813247fbdea36de9ac

store_bytes                44,576,768  (43 MiB)      tickers_table_rows      22,038
sep_rows                      685,585                 actions_rows               830
sep_tickers                     1,254                 distinct_trading_days     7,188
sep_date_range      1997-12-31 → 2026-07-31           survivorship_pool_lines  14,150
rows/ticker  min 53 · median 531 · max 7,188
median ticker's earliest date            2024-06-03   (≈2.2 years, not 28)
rows in the last 600 calendar days        498,723     (73% of the table)
WS5 destination: 19 GiB free · 3,825 MiB RAM · aarch64
```

The 1997–2026 span is carried by a handful of deep tickers; the **median** ticker holds ~531 rows
from mid-2024. This is an incrementally-grown store, not a full-history archive.

**Projected native build** for a WS5 universe of ≈500–700 tickers (pool 500 ∪ registered 208 ∪
held 0 ∪ SPY), bounded to ~500 trading days — comfortably beyond C40's needs (252-day momentum
lookback + 63-day dollar-volume window):

```
rows          ≈ 627,000        vs provider cap 900,000/day        → fits in one day
store size    ≈ 27 MiB         vs 19 GiB free                     → 0.14% of capacity
peak RSS      « 3.0 GiB        batched DuckDB inserts             → far inside the ceiling
requests      ≈ 2,500          SEP + ACTIONS per-ticker, TICKERS one bulk pull
runtime       ≈ 25–60 min      vs 6 h ceiling
```

⚠ **Empty-store degeneracy — the reason a seed list is mandatory.** On an empty store
`ranking_pool()` returns nothing, so `build_refresh_universe` degenerates to
registered ∪ extras ≈ 209 tickers, and the store-wide top-500 pool could never form. The bootstrap
must therefore be seeded from an **explicit governed ticker list**, exactly as the production store
originally was (`survivorship_pool.txt`, 14,150 names, used for the one-time back-fill). The full
pool is far too large — 14,150 × 500 ≈ 7.1M rows would breach the daily cap eightfold — so the seed
must be a bounded subset, pinned in the checkpoint.

### 6.2 Verified copy from the live paper runtime

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

The destination must be assigned a **new WS5 generation identifier**; it may not retain only the
source generation identity. The source generation is recorded as provenance, not as the WS5 store's
own identity — otherwise two distinct stores on two hosts would claim the same generation and later
divergence would be untraceable.

```
ws5_store_generation      = <new, WS5-owned identifier>
inherited_from_generation = <source generation, provenance only>
```

**Isolation is permanent after the copy.** Direct mounting, live sharing, network export, or any
continued synchronisation with the paper-box store is prohibited. What §6.2 permits is a **one-time,
independently verified snapshot copy** — after which the WS5 store evolves solely through its own
authorized refresh.

## 7. Market-data credentials — a separate secret class

Keep the classes separate, with separate permissions, fingerprints, receipts and verification
commands:

```
/etc/adr0043/wss-broker.env        the B4-staged Alpaca credential (already staged and verified)
/etc/adr0043/wss-market-data.env   the market-data provider credential (this document)
```

### 7.1 Provider binding — resolved

```
provider              Nasdaq Data Link (Sharadar)
base                  https://data.nasdaq.com/api/v3/datatables/SHARADAR
datasets              SHARADAR/SEP · SHARADAR/TICKERS · SHARADAR/ACTIONS
methods               GET only — no POST/PUT/PATCH/DELETE, no redirects to other hosts
read-only assertion   the provider is a market-data source; it holds no account, order or
                      position state and cannot mutate anything the platform owns
credential name       NASDAQ_DATA_LINK_API_KEY
storage               /etc/adr0043/wss-market-data.env   0600 root:root, dir 0700 root:root
fingerprint method    sha256(value) truncated to 12, matching the B4 scheme
rate ceiling          ~1,000,000 rows/day provider cap; operational bound 900,000/day (§6.1)
```

**Bootstrap and daily-refresh endpoint patterns differ and must be bounded separately.** SEP and
ACTIONS are pulled **per ticker**, so a broad historical universe spans multiple days — that is the
bootstrap shape, and it is the one that can silently exhaust the daily cap. TICKERS is a single
full-table pull (~22k rows). There is deliberately **no full-market SEP pull**: an explicit ticker
list or file must always be supplied, so a run cannot silently blow the daily limit. Bootstrap runs
must use `--skip-existing` to resume cheaply rather than re-fetching.

Key hygiene follows ADR 0018 §5 — the key is read from the environment, printed as a **length
only**, never as a value, and never written to logs or the audit chain. HTTPS uses the OS trust
store per ADR 0017; a standalone script must inject `truststore` itself.

The authorization must also specify: file ownership and permissions · **interactive owner staging
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

### 8.1 Store acceptance conditions

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

### 8.2 WSS deterministic decision dry run

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

### 11.1 Rollback on refresh or freshness failure

A single provider outage should not necessarily disable the schedule, but **readiness is withdrawn
immediately**:

```
refresh failure OR freshness-gate failure
→ factor scheduler continues ONLY per the pinned retry policy
→ substrate_ready = false            (withdrawn at once, not after N failures)
→ WSS execution interlock remains CLOSED
→ no stale store promoted as current
→ last sealed successful run remains the comparison anchor
```

Restoring `substrate_ready = true` requires a successful refresh that passes the full §8.1 gate —
never a manual override, and never the passage of time.

## 12. Explicitly prohibited

```
WSS trading scheduler activation        strategy execution with order submission
activation manifest issuance            Start-A baseline sealing
canary orders                           account mutations
enabling the default application Cmd    direct mounting, live sharing, network export of, or
                                        continued synchronisation with the paper-box store
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

## 15. Expiration

```
expiration_at = authorization_effective_at + 336 hours
```

Consistent with the predecessor's bounded window. The effectiveness record must carry the resolved
UTC timestamp and **verify a difference of exactly 1,209,600 seconds** — derived, never chosen. If
the measured bootstrap is expected to need longer, that is an amendment before effectiveness, not an
extension afterwards.

## 16. BOOTSTRAP_METHOD_SELECTED — sealed checkpoint

```
BOOTSTRAP_METHOD_SELECTED
  method                   = NATIVE_BUILD
  measurement_artifact_sha = 72506343a79677ba52a3ba850fc87ccad324118dca4e5b813247fbdea36de9ac
  seed_universe            = explicit governed ticker list, bounded subset (see below)
  depth_bound              = ~500 trading days
  projected_rows           = ~627,000        (cap 900,000/day)
  projected_store          = ~27 MiB         (19 GiB free)
  projected_runtime        = ~25–60 min      (6 h ceiling)
  authority_basis          = owner ruling — method deferred to measurement, selected on evidence
```

### 16.1 Why NATIVE_BUILD, on governance rather than cost

Both methods fit the limits easily; a 43 MiB store makes the cost argument nearly moot. The
decision therefore rests on provenance and workstream separation:

1. **VERIFIED_COPY requires touching the live production runtime mid-incident.** §6.2 demands
   quiescence or a validated consistent snapshot. The paper box currently has a **deliberately
   stopped refresh producer**, a store frozen at 2026-07-31, and an **unexplained write** at
   2026-08-03 09:08:39 — 65 minutes after the run that produced the file and 38 minutes before the
   timer was disabled. That anomaly is unresolved and is a blocking item in the separate recovery
   authorization. Snapshotting a store whose recent history is under investigation would import an
   open incident into this authorization.
2. **It would entangle two workstreams that are deliberately separate.** Production refresh
   recovery and WSS substrate establishment are governed by different documents precisely so a
   failure in one cannot stall or contaminate the other.
3. **The inherited provenance is worse than the build cost.** A copy carries the 2026-07-06 →
   2026-07-28 staleness episode and the frozen frontier as history that must be disclosed and
   reasoned about forever. A native build yields clean genesis for ~40 minutes of work.
4. **Nothing about the native build strains the host.** 0.14% of free disk, well inside the RSS
   ceiling, ~70% of one day's provider budget, and roughly a tenth of the runtime ceiling.

The one thing a native build does *not* get for free is the ranking pool, which is why the seed
list is a pinned input rather than a derived one (§6.1.1).

### 16.2 Seed universe — open for owner ruling

The seed determines which names WS5 can ever rank over, so it is a governed binding, not an
operator convenience. Recommended: **the production store's current 1,254-ticker membership,
exported read-only as metadata**. That reproduces the production ranking pool's *membership*
without copying its *data* or inheriting its provenance, and it is proven to support a 500-name
pool. At ~500 trading days it projects to ≈627,000 rows — inside the daily cap with headroom for
retries.

⚠ Exporting the ticker list is a **read-only metadata** operation against production. It does not
require quiescence, does not touch the store contents, and does not interact with the recovery
incident. It is nonetheless production contact and is called out here rather than assumed.

## 17. Remaining open items for owner ruling

1. ~~Final capacity ceilings and growth review threshold~~ — **RESOLVED**, frozen in §6.1.2.
2. ~~Bootstrap method~~ — **RESOLVED**, `NATIVE_BUILD` sealed in §16.
3. ~~Pinned artifact values~~ — **RESOLVED**, see §2.1.1.

**All three original open items are resolved.** One new item arose from the measurement:

4. **Seed universe for the native build** (§16.2) — recommended: the production store's current
   1,254-ticker membership exported read-only as metadata. This is a governed binding because it
   determines which names WSS can ever rank over, and it involves read-only production contact.

This document is now **complete except for item 4 and the effectiveness record**. It may not become
effective until item 4 is ruled on, the final text is reviewed, the document hash is pinned, owner
approval is recorded, and an effectiveness record is issued carrying `effective_at` and
`expiration_at = effective_at + 336 hours`.

### 17.1 Build-host permission finding (informational)

The WS5 role is genuinely ECR-only. Confirmed during the candidate build:

```
s3:ListBucket · s3:GetObject · s3:PutObject     DENIED
ecr:DescribeRepositories · DescribeImageScanFindings   DENIED
ecr:GetAuthorizationToken · BatchGetImage · push       ALLOWED
```

This is the same shape as the Stage-B blocker that made B4 an owner-typed checkpoint, and it
constrained how the pinned source reached the host. It was resolved **without an IAM change**: the
repository is anonymously readable, so the source arrived by shallow unauthenticated fetch of the
pinned commit — no credential entered SSM history or host disk, and no policy was broadened.

Consequence for §8: **the substrate's scan and registry-introspection evidence cannot be produced
from WS5 itself** and must be gathered from an identity that holds those ECR permissions. The scan
result in §2.1.1 was obtained that way.
