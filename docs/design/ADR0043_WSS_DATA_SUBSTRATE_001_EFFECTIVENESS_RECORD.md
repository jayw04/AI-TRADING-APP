# ADR0043-WSS-DATA-SUBSTRATE-001 — EFFECTIVENESS RECORD

> ## DECISION: **EFFECTIVE** — data-substrate establishment only
>
> `ADR0043-WSS-DATA-SUBSTRATE-001` is approved and made effective **solely** for establishment and
> verification of the WSS data substrate on WS5.
>
> ⛔ This record does **not** authorize WSS trading activation, order submission, a trading
> scheduler, Start-A sealing, canary orders, or an activation manifest.

## 1. Effective authorization

```
document_id                ADR0043-WSS-DATA-SUBSTRATE-001
document_pr                #610
approved_pr_head           f5c0bb54bbcf1211cc44b8c2f1d1e6416aa8691c
approved_document_blob     6a8448ab4a9d54228ce9cd4951a9e08614d0244b
approved_canonical_sha256  cb7350e3232429eaf4cd7dfb853b58702bbed68b5dc23b36164d0ae14446e4f2

effective_at               2026-08-04T21:41:00Z
expiration_at              2026-08-18T21:41:00Z
duration                   336 hours = 1,209,600 seconds exactly (DERIVED, never chosen)

terminal_success           DATA_SUBSTRATE_READY
terminal_failure           DATA_SUBSTRATE_FAILED
```

Blob integrity was verified before sealing: `git cat-file blob 6a8448ab4a9d54228ce9cd4951a9e08614d0244b` recomputes to
`cb7350e3232429eaf4cd7dfb853b58702bbed68b5dc23b36164d0ae14446e4f2`, matching the approved canonical
hash exactly.

⚠ Any change to the approved document, PR head, canonical body, source commit, candidate image
digest, platform tuple, runtime identity, provider partition, seed artifacts, capacity limits or
credential bindings **invalidates this record** and requires a new review.

## 2. Runtime and strategy identity

```
runtime_instance           i-0fff7076ad461aa9a
data_volume                vol-0710769fb6981102d
platform                   linux/arm64 on aarch64
strategy                   WSS / strategy 9 / construction v1.3 / C40
workbench_logical_account  7
broker_account             PA3E97RWHKQZ
broker_account_uuid        0fa55b0d-74d6-4a61-a361-ab154857cfb5
```

Account 7 is an **internal Workbench mapping**. This record does not independently "activate
account 7." The legacy canary account `PA34USW0Q8UO` is outside scope and must not be used.

## 3. Candidate image binding

```
repository                 219024422756.dkr.ecr.us-east-1.amazonaws.com/adr0043-canary-ws5
OCI index                  sha256:fc390cf5cb5fbd43d9d4c6bc256b19db9c7607a3b011d51dc8e28f740e30f31f
linux/arm64 deployable     sha256:d771197fa4c94bfd85e417f584002e0d811e9bdefa85f863066392870f950f56
source commit              a91fe75c041be25f116c9590d1574481443d2a42
platform                   os=linux · architecture=arm64 · variant=none
```

The tag `candidate-a91fe75c041b` is **informational**. Selection and verification must use the
pinned digest — an index digest can remain constant while platform selection differs.

## 4. Bootstrap artifacts — all digests complete

```
measurement_sha256                    72506343a79677ba52a3ba850fc87ccad324118dca4e5b813247fbdea36de9ac
bootstrap_seed_sha256                 189f242e7329736a8c0fb9163e9760373dfdaef1f133ec330abe9a1b47bd04ef
governed_membership_sha256            8dd3589bf5b673ae4557a6239dc804b845eeb2dfec535b23636adcd94e252549
cross_asset_bar_symbols_sha256        c03605282965bf17b2a54c625f3f69748ffb8a642c52bf2f84744b2bac9e987b
factor_store_required_symbols_sha256  226a271cc62a67866511404f3cd8b48a2fcbd870389223e342996ed9ca3701d3
```

✅ **No abbreviated digest appears in this record.** The two partition digests were extracted from
the approved blob itself (lines 607/610 and 867/869 of blob `6a8448ab4a9d54228ce9cd4951a9e08614d0244b`), not transcribed from working
notes, and are self-consistent at both occurrences.

## 5. Provider-specific data contract

WSS has **two** governed market-data substrates. An equity-only substrate is rejected: it would
silently change the governed 0.40/0.60 construction.

### 5.1 Sharadar factor-store partition

```
provider                   Nasdaq Data Link / Sharadar
datasets                   SEP · TICKERS · ACTIONS          methods  GET only
bootstrap membership       1,254 symbols                    required registered  199
projected rows             627,000    ceiling 900,000 per authorized day
projected requests           2,509    ceiling 3,000
history target             500 trading sessions per available symbol
```

The nine cross-asset ETFs are **not** Sharadar missingness. They are an exact, governed provider
partition — the subscription is Core US Equities and excludes SFP.

### 5.2 Alpaca cross-asset bars partition

```
provider host              data.alpaca.markets        trading host  paper-api.alpaca.markets
allowed operation          read-only historical daily-bar GETs
symbols                    DBC EEM EFA GLD IEF KMLM SPY TLT UUP
required returned set      9 of 9
minimum requested bars     338 completed daily bars per symbol
calendar lookback          551 days
expected bounded rows      3,042
```

⚠ `data.alpaca.markets` and `paper-api.alpaca.markets` are **separate boundaries**, resolved from
`alpaca.common.enums.BaseURL` and confirmed not interchangeable. Market-data authorization does not
broaden broker or order authority.

⚠ An empty bar frame, partial returned symbol set, unauthorized symbol, or unavailable data path is
a **hard readiness failure**. It must not silently produce a reduced cross-asset sleeve —
`ctx.get_recent_bars` returns an empty frame and logs a warning rather than raising, so this failure
mode is silent by construction.

⚠ **KMLM's inception is 2020-12.** Its legitimately shorter history must be explicitly attributed
and must not be mislabeled as a failed fetch.

## 6. Frozen capacity limits

```
maximum RSS                3.0 GiB      maximum temporary disk       12 GiB
minimum free disk retained 4 GiB        maximum staging-store size   500 MiB
maximum runtime            6 hours      concurrency                  1
provider rows/day          900,000      provider requests            3,000
stale-lock threshold       12 hours     universe hard maximum        2,000
growth review threshold    0.25         expected normal universe     500–900
```

A breach yields `CAPACITY_INSUFFICIENT`. It does **not** authorize instance resizing, broader IAM,
higher ceilings, or continuation in place.

## 7. Authorized execution sequence

```
SUBSTRATE_AUTHORIZED
→ verify document, runtime and artifact identities
→ verify OCI index, arm64 child manifest and platform
→ pull the pinned image by digest
→ bounded image preflight
→ DB_CREATE_AUTHORIZED → DB_CREATED
→ MIGRATION_AUTHORIZED → MIGRATION_APPLIED → SCHEMA_VERIFIED
→ STRATEGY_SEEDED
→ MARKET_DATA_CREDENTIAL_STAGED
→ BOOTSTRAP_METHOD_SELECTED: NATIVE_BUILD
→ NATIVE_BUILD → BOOTSTRAP_VERIFIED
→ SHARADAR_INCREMENTAL_REFRESH_VERIFIED
→ ALPACA_NINE_SYMBOL_BAR_GATE_VERIFIED
→ FULL_WSS_DETERMINISTIC_DRY_RUN_VERIFIED
→ FACTOR_SCHEDULE_INSTALLED_DISABLED
→ SCHEDULED_EQUIVALENT_RUN_VERIFIED
→ FACTOR_REFRESH_SCHEDULER_ENABLED
→ NON_TRADING_POSTURE_PROVEN
→ DATA_SUBSTRATE_READY
```

⚠ **Each transition must have its own recorded evidence. A later state must never be inferred from
the completion of an earlier command.**

## 8. Full WSS dry-run requirement

```
equity sleeve weight 0.40                cross-asset sleeve weight 0.60

EQUITY        factor-store digest · input-universe · eligible-universe
              · selected-40 · weights
CROSS-ASSET   nine-symbol-set · daily-bars panel · signal
              · raw weights · correlation-tilted weights
GOVERNORS     market-regime result · beta-cap input · beta-cap result
COMBINED      pre-trade target weights · final target weights · cash weight
              · deterministic reproduction result
```

Acceptance requires: nine requested ETF symbols returned **9/9** · broker mutation attempts **0** ·
order submissions **0** · deterministic reproduction **MATCH**.

⛔ **An equity-only result is not an acceptable WSS dry run.**

## 9. Scheduler boundary

Only the WSS **factor-refresh / data-maintenance** scheduler may be enabled, and only after its
scheduled-equivalent execution passes. Must **not** be enabled: WSS trading scheduler · order
submission · canary execution · Start-A baseline · activation manifest.

## 10. Hard prohibitions

```
WSS trading activation                    order create/replace/cancel/submit
broker or account mutation                strategy status changes to obtain data membership
barred manifest 1e9e0f94…2bf2bb36         repointing account 7
reactivation of account 3                 instance resizing
IAM expansion                             the image's default command
seed_dev_data.py                          application-server startup
any production paper-box change governed by #614
```

## 11. Failure disposition

Any failed identity, artifact, platform, schema, credential, capacity, provider, freshness,
completeness, deterministic-output, scheduler or non-trading gate results in:

```
DATA_SUBSTRATE_FAILED
  WSS stopped · trading scheduler disabled · order submission blocked
  activation manifest absent · evidence preserved
```

A substrate failure does **not** invalidate the predecessor's broker-readiness disposition `READY`.

## 12. Related workstreams — explicitly out of scope

- **#614** — production factor-refresh recovery on the paper box. Calendar-critical: strategies 7
  and 8 dispatch Monday 2026-08-10 at 10:24 / 10:32 ET. Governed separately; no action under this
  record may touch the paper production runtime.
- **#615** — factor-watchdog producer liveness. ⚠ It closes **detection only**. Producer-liveness
  detection without a dispatch veto is **not** a complete production interlock. #615 must not be
  described as closing the dispatch-safety gap until a separate consuming interlock proves
  `watchdog FAIL → readiness FAIL → factor-consuming dispatch prevented`. This does not block the
  present record, because WSS trading dispatch remains disabled throughout this authorization — but
  it matters directly for strategies 7 and 8 under the #614 deadline.

## 13. Owner approval

The owner approves the exact document and bindings identified above for the limited purpose of
establishing and proving the WSS data substrate on WS5.

**No WSS trading authority is granted.**

```
approved_by     Jay Wang (GlobalComplyAI LLC), owner
approved_head   f5c0bb54bbcf1211cc44b8c2f1d1e6416aa8691c
issued_at       2026-08-04T21:41:00Z
```
