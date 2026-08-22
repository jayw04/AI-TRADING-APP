# MDQ-001 — Program-Start Record (deployment / clock-freeze)

| Field | Value |
|---|---|
| Document version | **v0.1 DRAFT — NOT EFFECTIVE.** This record becomes effective only when the owner stamps the FILL-AT-FREEZE values in §4 and §6 and signs §11. Until then it freezes nothing. **As of drafting, no admissible partition exists and the 60-day clock has NOT started** (see §8.1). *Updated 2026-08-18 for the owner correction set of that date — registration §8.2 rulings 1–4 (the `expected_cycles` denominator, the ANY-K correction, the undefined-verdict disposition, and the holdout boundary/embargo) — and for the **§8.2 pre-commitment** excluding the 2026-08-18 partition. Only the placeholders those rulings resolve were filled; **every other FILL-AT-FREEZE value remains empty and the clock still has not started.*** |
| Date | 2026-08-18 (drafted; **not** a clock-start date) |
| Program | **MDQ-001** — Algo Trader Plus / SIP Market-Data Qualification, Phase A |
| Supersedes | Nothing. This is the first program-start record for MDQ-001. It does **not** supersede, amend, or reopen `MDQ-001_Registration_v1_0_DRAFT.md`; it records values that document deferred to "the day the first admissible partition freezes". |
| Basis | `docs/design/MDQ-001_Registration_v1_0_DRAFT.md` (signed §8 block, ratified §8.1) · `docs/Strategies/AlgoTraderPlus_v1_4_1_ImplementationPlan_v0_8.md` §1.3, §2, §4.9, §4.10, §4.11, §7, §8 · owner deployment-execution boundary, 2026-08-17 night (items 6 and 7) · ADR 0051 (research-plane isolation) · ADR 0050 / GITHUB-OPS-001 v1.2 (this is *governing* documentation, therefore Git) |
| Governance stance | **Recording instrument, not a decision instrument.** Every value here traces to an already-signed or already-ratified decision, or is an observation made at a freeze. If this record conflicts with the registration document, a signed §8 line, the ratified §8.1 block, or an owner ruling, **those control and this record is wrong**. Nothing here may be used to adjust a K-criterion, a threshold, a tolerance, a denominator, or an evaluability clause. |
| Decision owner | Platform owner (Jay Wang) |

---

## 1. What "program start" means — the definition this record exists to fix

> **"PROGRAM START" IS NOT DEPLOYMENT TIME AND NOT FIRST WRITE — IT IS THE FIRST ADMISSIBLE GOVERNED FROZEN PARTITION (FULL ADMISSIBILITY CHAIN).**
>
> — Owner, deployment-execution boundary item 6, 2026-08-17

Four distinct events exist and only the last one starts the clock:

| Event | Status | Does it start the 60-day clock? |
|---|---|---|
| **Deployment** — governed code and schedule installed on `ec2-paper` | Done 2026-08-17, ~19:25–19:40 ET | **No.** Deployment is capability, not evidence. |
| **First timer fire** — a `systemd` unit activates on schedule | First fire 2026-08-18 09:25:02 EDT | **No.** A timer firing proves the schedule works, not that data was acquired. On 2026-08-18 the wrapper's fail-closed guard correctly refused the run — see §8.1. |
| **First write** — the collector appends the first quote-sample record to a partition | **Not yet occurred.** *(Corrected 2026-08-18 ~22:50Z: an earlier draft of this row anticipated a bar-only `2026-08-18` partition from the 16:30/16:45 ET runs. **It was never created** — `mdq-eod` failed closed on the credential identity latch and `freeze` reported `no partitions for 2026-08-18; nothing to freeze`. **No 2026-08-18 bytes exist in the governed corpus.** See the §8.1 correction note.)* | **No.** Bytes on disk are not an admissible partition; the abort-after-30 rule and the completeness thresholds exist precisely because records can be present while sufficiency is absent. |
| **First admissible governed frozen partition** — freeze completed, `verify` passes, and **every** §7.1 condition in §5 below is satisfied | **Not yet occurred** | **Yes. This and only this.** |

Consequences that follow from the definition and are binding:

1. The **60-day review clock starts on the session date of the first admissible governed frozen partition**, not on 2026-08-15 (entitlement), not on 2026-08-17 (deployment), not on a timer fire, and not on the first sampler cycle.
2. The **review date, the holdout period dates, and the corpus window** are all derived from that one date and are stamped **once**, here, in §4.
3. If a candidate day produces no admissible partition, **the clock does not start** — see §8.
4. A partition that is written, frozen, and `verify`-clean but fails a completeness threshold **is not a program start**. `verify` proves the bytes are the frozen bytes; it does not prove the partition contains the observations it was supposed to contain (plan v0.8 §4.9).

---

## 2. Deployed identity — the code that produced (or will produce) the corpus

### 2.1 Commit identity

| Item | Value |
|---|---|
| **Deployed commit (box)** | `027301223d8e88ce616e90a2d6831d689f2964f0` |
| Short / `WORKBENCH_CODE_VERSION` | `0273012` |
| Deployed at | 2026-08-17, ~19:25–19:40 ET (post-close, Monday) |
| Deploy vehicle | S3 source tarball, sha256 prefix `fc7e2472386d8dab…` → `/opt/workbench/app`; `.deploy_src_sha` written; backend-only rebuild |
| Alembic head at deploy | `b2d8f4c6a901` (unchanged — zero new migrations in this deployment) |
| Pre-deploy DB backup | `/opt/workbench/data/workbench.predeploy-mdq-20260817.sqlite` |

### 2.2 Merge chain that produced the deployed commit

Linear, no merge commits; each entry is a squash merge onto `main`.

| PR | Full SHA | Committed (local) | Subject |
|---|---|---|---|
| **#634** | `63c0c52107ed4cba6ffb8aa1c53bed5db526b02b` | 2026-08-17T17:39:49-05:00 | MDQ-001 Phase A: explicit feed pinning, registration draft, account-7 collector |
| **#636** | `be4235dd2ae9623391946d46d2076197b12cc8e9` | 2026-08-17T18:07:35-05:00 | ci: wire market-data feed-pinning guard into the invariant checks |
| **#637** | `027301223d8e88ce616e90a2d6831d689f2964f0` | 2026-08-17T18:10:00-05:00 | docs(gapper): commit the v2.1.1 approval record into Git custody |

Parent of #634 is `3e28a75cddd56785610dde7e79f7c3ca5c70e4dc` (#635, EC2 fleet audit).

**#636 closes registration precondition P-4** — the feed-pinning guard `check_marketdata_feed_pinning.sh` is CI-enforced on `main` before the first governed capture. An unwired guard is convention, not mechanism.

*Note for the record:* `main` has moved past the deployed commit since deployment — `835c4132fdc417e6debd528207a0156ebdc680c3` (#638) and `5441da1f0ab068df4d8d024bddf929b79219b554` (#639), both range-strategy history-capture fixes, unrelated to MDQ. **The box still runs `0273012`.** The corpus identity is the deployed commit, not `main`.

### 2.3 Collector code identity

**Normalization rule (stated exactly, applied uniformly):** every hash below is the **SHA-256 of the git blob content at `0273012`**, i.e. the LF-normalized bytes as stored in Git, obtained by

```bash
git show 0273012:<path> | sha256sum
```

This is **not** the hash of the working-tree file. This checkout applies CRLF on checkout, so working-tree bytes differ from blob bytes for every text file, and hashing the working tree produces values that reproduce nowhere else. The box's container copies come from `git archive` and are CRLF; the 2026-08-17 conformance check confirmed that **CRLF-normalized runtime sha == git blob sha** for the collector files, which is why the blob hash is the portable identity.

| File | git-blob SHA-256 @ `0273012` |
|---|---|
| `apps/backend/scripts/mdq_collector.py` (CLI) | `ddb088e8b344075f09ff3bb2051bcca703acef2286a2214c9455b046f64ef3f8` |
| `apps/backend/app/research/capture/store.py` | `22c3405e5acbba6c7a86ef71468898ec0515126399770b02dfb42373f211e222` |
| `apps/backend/app/research/capture/collector.py` | `9545b231006fcfd72c242efe9c46bfbee28bdc0f6374dc0553140f42c89bee68` |
| `apps/backend/app/research/capture/identity.py` | `211b3b189f73bc8c765552704cad591a197e3a59de5b7f023ea24afbe81242d7` |
| `apps/backend/app/research/capture/__init__.py` | `da6c00367e9a0ef479c9b87a52b9bf4e6b0f1e95de439e91befdb2dca526dcb8` — **APPROVED MEMBER of the code-identity set** (owner ruling 2026-08-18: the set is **five** files; §10 Q6 closed). The 2026-08-17 conformance check covered only **four** and omitted this file. |
| Declared collector version string | `mdq-collector/0.1.0` (`store.COLLECTOR_VERSION`; appears in every manifest) |
| Manifest schema | `mdq-capture-manifest/1` |

"Collector code identity is approved for the period" (§7.1) means: for every session in the corpus window, the runtime files hash to the values above. Any change to any of them is a **new** code identity and requires an explicit owner decision about whether the corpus continues across the boundary.

> ⚠ *Note added 2026-08-18 — consequence of registration §8.2 ruling 1.* The related runtime ruling replaces the sampler's **fixed-delay** loop with **fixed-rate scheduling against an absolute monotonic deadline** (no burst/catch-up, close checked before each cycle, `scheduled_slot_ts` / `slot_index` persisted per cycle). That change edits `apps/backend/app/research/capture/collector.py`, which is **a file in the table above** — so it produces a **new collector code identity**, and the row's blob hash (`9545b231…` at `0273012`) will no longer describe the runtime. Per §8 step 4 this must be **re-stamped here, against the new deployed commit, before the first admissible capture**; the corpus identity is whatever is recorded in this table at the time the corpus accrues. **No hash is guessed here** — the row is left as deployed and the re-stamp is an action, not a prediction. The patch itself is implementation work owned outside this document. The re-stamp is now also **wider**: the approved set is **five** files, not four (owner ruling 2026-08-18, below), and it must additionally pin the **running container image** (§2.5, §6) — git blobs alone do not prove the container was recreated.

#### Approved code-identity set — **FIVE files** *(owner ruling, 2026-08-18; closes §10 Q6)*

```text
apps/backend/app/research/capture/__init__.py
apps/backend/app/research/capture/collector.py
apps/backend/app/research/capture/identity.py
apps/backend/app/research/capture/store.py
apps/backend/scripts/mdq_collector.py
```

**Why five and not four.** `__init__.py` is **imported at runtime and re-exports the package API**, so excluding it left a **runtime-loaded file outside the identity** — a file that could change without changing the recorded identity, which is precisely what a code-identity stamp exists to prevent. The 2026-08-17 four-file conformance set was an **omission, not a scoping decision**. Correcting it **now, before any corpus exists**, is the free moment: no evidence has accrued against the narrower set, so widening it invalidates nothing. After the window opened it would have been a mid-window identity change.

**The hashes are deliberately empty — they stamp at the merge commit, which does not yet exist.**

| File | git-blob SHA-256 @ the **merge commit** | Expectation to VERIFY (never to copy forward) |
|---|---|---|
| `apps/backend/app/research/capture/__init__.py` | `«FILL-AT-FREEZE»` | **new to the approved set** |
| `apps/backend/app/research/capture/collector.py` | `«FILL-AT-FREEZE»` | **CHANGING** — carries the fixed-rate scheduler; will differ from `9545b231…` |
| `apps/backend/app/research/capture/identity.py` | `«FILL-AT-FREEZE»` | expected **unchanged** from `211b3b18…` |
| `apps/backend/app/research/capture/store.py` | `«FILL-AT-FREEZE»` | expected **unchanged** from `22c3405e…` |
| `apps/backend/scripts/mdq_collector.py` | `«FILL-AT-FREEZE»` | **CHANGING** — will differ from `ddb088e8…` |

**No value above is guessed, and “expected unchanged” is an expectation to check, not a value to carry over.** If `identity.py` or `store.py` differs at the merge commit, that is a **finding**, not a typo. The normalization rule is unchanged and applies to the new ref exactly as it applied to `0273012`:

```bash
git show <merge-commit>:<path> | sha256sum
```

— **LF-normalized git blob bytes, not worktree bytes.** This checkout applies CRLF on checkout, so hashing the working tree produces values that reproduce nowhere else. Once stamped, the table above is the corpus code identity; the `@ 0273012` table is retained as the record of what was deployed on 2026-08-17.

### 2.4 Acquisition identity (fail-closed latch)

| Item | Value |
|---|---|
| Credential fingerprint (`sha256(key_id)[:12]`) | `5b6f39e5198d` |
| Broker account number | `PA3BGKRLH2AP` (workbench **account 7**) |
| Env keys (resolved, then verified by fingerprint — **never trusted by name**) | `ALPACA_PAPER_6_API_KEY` / `ALPACA_PAPER_6_API_SECRET` |
| Trading base URL (identity latch only) | `https://paper-api.alpaca.markets` |
| Entitlement | Algo Trader Plus, on the account-7 login (switched, not added, 2026-08-15) |
| Real-time tier proof (P-2 / G1) | **CLOSED 2026-08-17 RTH** — v2 proof script sha `959c5399…`, sealed evidence sha `67c400d3…`, R1–R4 all PASS; v1 preserved as a mechanical FAIL, `c7b9371d…` |

Payload discipline: exactly one field (`account_number`) leaves the `GET /v2/account` boundary; equity, buying power and all other execution-plane state are discarded inside `_get_account_number` and never reach the research archive.

Per ADR 0051 the collector is the **single designated writer**; MDQ-001 and every other consumer is a reader. The collector is the only process authorized to authenticate for MDQ acquisition; MDQ analysis code holds no Alpaca credentials and makes no API calls.

---

### 2.5 Deployment mechanics — the collector runs **inside the backend container** *(recorded 2026-08-18, owner ruling)*

⚠ **The collector does not run from the host checkout.** The wrapper invokes it through the running backend container:

```bash
docker exec workbench-backend python scripts/mdq_collector.py …
```

and **the backend image bakes the source in**. The only bind mounts are `bars_cache`, `premarket_gappers`, `data` and `strategies_user` — **there is no source bind mount**. Three consequences, all load-bearing:

1. **Deploying a collector change is a rebuild, not a file copy.** The backend **image must be rebuilt and the container recreated**. That restarts the **live trading backend**, which makes it a **Tier-3 live-stack touch** under the walk-away discipline — not routine housekeeping, and not something to slip in between other work. Any wording in this record or the implementation plan suggesting the collector runs “from the deployed repo on the box” understates what a collector change costs.
2. **Code identity and running-image identity are two different things, and this record pins BOTH.** The git blobs in §2.3 say what the source **is**; the **image ID actually serving `docker exec`** (§6) says what is **running**. **A reader who checks only the git blobs would not detect a container that was never recreated** — the repo on the box can be perfectly up to date while the container serving every capture cycle still runs the previous image. Every partition would then carry a code identity describing source that no process executed. That is a silent divergence, invisible to a git-only check, and it is exactly the failure §7.1's code-identity condition exists to catch.
3. **Deployment window: after tonight's 16:45 ET freeze completes — never intraday** *(owner ruling, 2026-08-18)*. The 16:30 `eod` and 16:45 `freeze` runs `docker exec` into **that same container**, and recreating it mid-session restarts the live trading backend and can interrupt a run in flight. Deploy after the freeze completes, verify, and let the **next morning's 09:25 fire** be the first cycle of the fixed-rate sampler.

---

## 3. Frozen capture identity

### 3.1 Universe

| Artifact | git-blob SHA-256 @ `0273012` | Verified |
|---|---|---|
| `apps/backend/config/mdq_phase_a_universe.json` (composite: rule + base + sample + symbols) | `d6248e2b7055aec6ba77fc8ce4056840713830695a08ff61f4236cb780f77a45` | ✅ reproduces the value recorded in registration §8 |
| `apps/backend/config/mdq_phase_a_universe_symbols.json` (deployable `--universe-file` array) | `0c57bd71c0b73565328ec27036c6573f11b87594acb49ca461458a7d947f88d4` | ✅ reproduces registration §8 and the `universe_symbols_sha256` field inside the holdout artifact |
| `apps/backend/config/mdq_phase_a_holdout.json` | `6c6cf03a80598f54df89b599f2ffbbda09ea44af8f3596421d6c58104e2393bb` | ✅ reproduces registration §8.1 |

**Derived `universe_sha256` written into every partition manifest:**

```
a022e399e216f16328eaecd809126951f6658cb09351281fa02187a0a6faf563
```

Definition (from `scripts/mdq_collector.py::_universe_sha`): `sha256(json.dumps(sorted(universe)).encode()).hexdigest()`, where `universe` is the uppercased tuple loaded from `--universe-file`. Note this is a hash of the **canonical sorted symbol list**, not of the file — it is invariant to file formatting and is therefore the value that must appear in the manifest. ✅ Recomputed from the blob and reproduces `a022e399…`.

For contrast, so no future reader confuses them: the in-code 14-symbol `PHASE_A_UNIVERSE` default (used only when `--universe-file` is absent) has derived sha `f881e2c1366640c1e0d3db5fa192363189979ff13f477e3beb65df525758a91e`. **A manifest carrying that value is a partition captured without the frozen universe file and is inadmissible.**

**Composition (50 symbols):** BASE 22 = SPY/QQQ/IWM + 11 SPDR sector ETFs + the account-7 transition set (DBC, EEM, EFA, GLD, IEF, KMLM, TLT, UUP). SAMPLE 28 = top-28 by 60-session average dollar volume from Sharadar SEP as of `2026-06-12` (traded on max date, close ≥ $5, ≥ 55 of last 60 sessions), excluding BASE. Mechanical rule, no discretionary selection.

### 3.2 Session scope, cadence, and capture modes — frozen identity

| Parameter | Frozen value | Source |
|---|---|---|
| Bar census window | **04:00–16:00 ET** (premarket + RTH; **no postmarket**) | registration §7 Phase A; plan §4.1 |
| Quote sampler cadence | **60 s** | registration §8 (signed) |
| **Quote-sampler window — the `expected_cycles` denominator** | **09:25 America/New_York → official NYSE close for that session, EXCLUSIVE**; `expected_cycles` = the count of scheduled 60 s slots `t` with `sampler_start <= t < sampler_end` ⇒ **395** on a normal 16:00 close · **215** on a 13:00 early close · **0** on holidays and non-session days | registration **§8.2 ruling 1** (owner, 2026-08-18) |
| Retry policy | per-feed error isolation; continue on transient failure; **abort after 30 consecutive fully-failed cycles** | registration §8 (signed) |
| Capture mode — quotes | `rest_quote_sampler_v1` | `collector.CAPTURE_MODE_SAMPLER` |
| Capture mode — bars | `rest_eod_bars_v1` | `collector.CAPTURE_MODE_EOD_BARS` |
| Feeds | `iex` and `sip`, both **explicit on every request** | registration §3.1; `check_marketdata_feed_pinning.sh` |
| Websocket | **none.** Phase A arms no websocket; 2 REST calls per cycle | registration §7 |

**Cadence is frozen identity and may not be tightened after seeing results** — in particular not to improve K6's chance of observing a stub-quote event.

**The two windows are different denominators and must not be conflated.** The **04:00–16:00 ET** interval is the **EOD one-minute bar census** scope and is the denominator on the **bar** side. The **09:25 → close (exclusive)** interval is the **quote-sampler** scope and is the denominator for `expected_cycles` / completeness. Registration §8.2 ruling 1 binds this because §8 froze the completeness *threshold* while leaving `session_scope` unbound: had the census window been used as the sampler denominator, a fully healthy partition would have scored ≈ 55% and **nothing would ever have been admissible.** The 98% floor and the 10-minute maximum contiguous gap are **unchanged**.

### 3.3 Schedule and timezone identity

| Item | Value |
|---|---|
| Mechanism | **systemd timers, timezone-explicit** (not cron) |
| Units | `mdq-sample.service`/`.timer` · `mdq-eod.service`/`.timer` · `mdq-freeze.service`/`.timer` · `mdq-alert@.service` (OnFailure) |
| `OnCalendar` | `Mon..Fri 09:25:00` · `Mon..Fri 16:30:00` · `Mon..Fri 16:45:00`, all `America/New_York` |
| `AccuracySec` | `10s` |
| `Persistent` | `true` |
| Host timezone | `America/New_York` (verified via `timedatectl` at conformance) |
| Container timezone | `UTC` **by design** — every timestamp written into a partition is UTC |
| Wrapper | `/opt/workbench/mdq/mdq_run.sh` — fail-closed: universe-hash pin · free-space floor `max(10 GB, 20%)` · single-sampler check · freeze path = `freeze` → `verify` → `aws s3 sync` |
| First timer fire | 2026-08-18 09:25:02 EDT — **fired on schedule; the run was refused by the free-space guard.** See §8.1. |

Trading-day gating is not left to the timer: `_session_close_utc` consults the **NYSE calendar** (`pandas_market_calendars`) and the sampler exits immediately on a non-trading day and stops at the authoritative session close, half-days included.

**Guard ordering, observed:** the wrapper's free-space check **precedes** the subcommand dispatch, so a floor breach suppresses `sample`, `eod` and `freeze` alike for that day. This is correct fail-closed behavior; its consequence is that a breach costs the **whole session**, not one subcommand.

**Box state change, 2026-08-18 midday** *(reported by the operating session; not re-verified from this document, and no value here is a freeze stamp).* The free-space breach was cleared — Docker build-cache prune plus removal of two superseded image tags took the volume from **8.1 GB to 12 GB free** against the **10 GB** floor — and a **CloudWatch alarm is now wired** on the `Workbench/Paper / MdqCollectorFailure` metric (§10 Q4, Q5). **The sampler still cannot run today**: `systemd` has already satisfied today's `OnCalendar` occurrence and `Persistent=true` does not re-fire a satisfied occurrence. **`mdq-eod` (16:30 ET) and `mdq-freeze` (16:45 ET) are no longer blocked and will run**, which is why the exclusion in **§8.2** was recorded in advance of them.

### 3.4 Storage, durability, and the shared-host floor

| Item | Value |
|---|---|
| Capture root (host) | `/opt/workbench/data/mdq_capture` |
| Capture root (container) | `/app/data/mdq_capture` (`WORKBENCH_MDQ_CAPTURE_ROOT` in the box `.env`) |
| Permissions | root-owned `755` — designated-writer / read-only-consumer |
| Layout | `<root>/<feed>/<YYYY-MM-DD>/{quotes,bars}/…` + `manifest.json` (**manifest presence == FROZEN**) |
| **Backing volume** | ⚠ **`/dev/root` — a single ~30 GB root disk, NOT a dedicated persistent volume.** Shared with Docker, `/var/log`, a 4.1 GB swapfile, the SQLite trading book, and existing research artifacts. Plan §1.3 specified the governed host's **persistent volume**. See §10 Q10. |
| Durability choice (§6.4, signed) | **S3 byte-for-byte mirror after local `verify` passes** |
| Mirror location | `s3://workbench-backups-219024422756/mdq_capture/` |
| Mirror control | the instance role can **PUT but not DELETE** in that prefix — the box cannot destroy mirrored bytes (probe-verified at deployment; probe object removed) |
| Free-space floor (signed) | `max(10 GB, 20% of volume)`, checked before each write cycle and before EOD/freeze; **abort-and-alert** on breach |
| Free space at deployment | 14 GB (after reclaiming 5.5 GB of docker cache) vs a 10 GB floor |
| Free space at first timer fire | **9 GB — BELOW the floor. The guard fired and the capture was refused.** See §8.1. |
| Collector ceiling (signed) | ≤ 50% of one vCPU · ≤ 1 GB RSS · ≤ 20 GB partition store (alert at 15 GB) · ≤ 5 GB analysis scratch; abort on 2 consecutive minutes above ceiling or any live-stack health-check failure; **always subordinate to the account-7 transition executor** |
| Failure surface | `OnFailure` → `/opt/workbench/data/mdq_capture_alerts.log` + CloudWatch metric `Workbench/Paper: MdqCollectorFailure` — ⚠ **no alarm is attached.** On 2026-08-18 the failure published a datapoint that **notified nobody**. See §10 Q4. |

⚠ The systemd units and `mdq_run.sh` live **only on the box and are not in Git.** Committing them is an owner decision (§10 Q3). Until they are, their identity is carried only by the SHA-256 values stamped in §6.

---

## 4. THE CLOCK — first admissible governed frozen partition

> ⚠ **EVERY VALUE IN THIS SECTION IS AN UNFILLED PLACEHOLDER.**
> **No admissible partition exists as of drafting.** No value below may be inferred,
> estimated, or filled in "provisionally" by a session. The arithmetic in §4.3 is
> *illustration of the rule only* and is **not** a stamped value.

### 4.1 Stamped values

| Field | Value |
|---|---|
| First admissible governed capture — **session date (ET)** | `«FILL-AT-FREEZE — session date»` |
| First admissible governed capture — **freeze timestamp (UTC)** | `«FILL-AT-FREEZE — manifest frozen_at, UTC, ISO-8601, labelled UTC»` |
| First admissible governed capture — **freeze timestamp (ET)** | `«FILL-AT-FREEZE — the same instant expressed in America/New_York, labelled ET»` |
| Which feed partitions | `«FILL-AT-FREEZE — both sip and iex must be admissible; a session where only one feed qualifies is NOT a program start»` |
| **60-day clock start (day 0)** | `«FILL-AT-FREEZE — equals the session date above»` |
| **Computed review date (day +60)** | `«FILL-AT-FREEZE — apply the §4.2 rule to the stamped start»` |
| **Holdout period — first day** | `«FILL-AT-FREEZE — day 0 + 48 calendar days; arithmetic frozen at §4.2 / §4.4 by owner ruling 4»` |
| **Holdout period — last day** | `«FILL-AT-FREEZE — day 0 + 59 calendar days (the day before review_end_exclusive); §4.2 / §4.4»` |
| Adjudicated by / at | `«FILL-AT-FREEZE — owner name, date»` |

### 4.2 The review-date rule (frozen at registration §8, restated here — not re-decided)

> **The 60-day clock runs from the FIRST ADMISSIBLE GOVERNED CAPTURE, not the entitlement date.**
> `review_date = first_admissible_session_date + 60 calendar days`

The **rule** was frozen at G2 sign-off. The **date** could not be computed then, because the capture that anchors it had not occurred. Stamping it here is the mechanical completion of a signed decision, not a new decision.

A slip moves the review date; it never silently shortens the evidence window. **A slip is not a cost to be recovered by shortening the window.**

**Boundary arithmetic — frozen by owner ruling 4, 2026-08-18** (registration §8.2; recorded here, not decided here):

```text
review_start_date    = session_date of the first admissible governed capture
review_end_exclusive = review_start_date + 60 calendar days
period_holdout_start = review_start_date + 48 calendar days

period holdout       = session_date >= period_holdout_start
                       AND session_date <  review_end_exclusive
```

⇒ the **corpus window is offsets 0–59** and the **period holdout is offsets 48–59 — exactly 12 calendar dates**. The **review date is `review_end_exclusive` (day +60)**, i.e. the first day *outside* the window; it is the adjudication date, not a corpus date. **The boundary does not slide for weekends or holidays** — a non-session date inside the holdout simply contains no trading partition, and sliding would silently convert “the final 20% of the window” into “the final 12 **trading sessions**,” a different rule. This resolves §10 Q1.

### 4.3 The arithmetic, illustrated — **NOT STAMPED VALUES**

The table below exists so the rule is unambiguous, not to pre-commit a date. Every row is hypothetical; the operative value is whatever §4.1 eventually carries. ⚠ **Nothing in this table is predeclared — 2026-08-19 included.** The holdout and review dates stamp **only if and when** a partition actually qualifies under §5; running the sampler is not qualifying. The 2026-08-19 row is the owner-confirmed **conditional** arithmetic *should* that partition qualify: `review_start_date = 2026-08-19`, `period_holdout_start = 2026-10-06` (offset 48), `review_end_exclusive = 2026-10-18` ⇒ period holdout = **2026-10-06 through 2026-10-17 inclusive**.

| Hypothetical day 0 | Review date (day +60 = `review_end_exclusive`) | Weekday of review date | Corpus window (offsets 0–59) | Period holdout (offsets 48–59 — 12 calendar dates) |
|---|---|---|---|---|
| ~~2026-08-18~~ | ~~2026-10-17~~ | — | — | **Excluded — the 2026-08-18 partition is INADMISSIBLE on §7.1 completeness (0 of 395 expected sampler cycles); pre-committed in §8.2.** |
| 2026-08-19 (earliest still possible) | 2026-10-18 | **Sunday** | 2026-08-19 … 2026-10-17 | 2026-10-06 … 2026-10-17 |
| 2026-08-20 | 2026-10-19 | Monday | 2026-08-20 … 2026-10-18 | 2026-10-07 … 2026-10-18 |

*Holdout columns recomputed 2026-08-18 under owner ruling 4 (§4.2); the previous values were drawn from the looser reading the ruling settles.*

For contrast, the registration document's indicative target of **~2026-10-14** derives from a 2026-08-15 (entitlement-date) anchor, which the v0.5 re-anchoring explicitly replaced. **That target is stale and non-binding; it is not the review date.** Only the stamped §4.1 value governs.

Note that two of the three candidate review dates fall on a weekend. §10 Q2 asks how a non-business **adjudication date** resolves; under owner ruling 4 the answer does **not** move the holdout window with it — the holdout is fixed by calendar-day offset from day 0 and does not slide.

### 4.4 Holdout reserve — ratified §8.1, materialized before capture

**Symbol holdout — 10 of 50 (20%), zero discretion:**

```
AMZN  EFA  KMLM  MSTR  NBIS  NOW  TSLA  XLK  XLV  XOM
```

Draw rule: `random.Random(int(sha256(<universe_symbols_file, LF bytes>), 16)).sample(sorted(universe), 10)`.

✅ **Reproduced during the drafting of this record** from blob `0c57bd71…` — the draw returns exactly the ten symbols above. Anyone can re-derive it from committed artifacts alone.

**Period holdout — RULE (ratified):** the **final 12 calendar days** (= final 20%) of the 60-day review window. The **dates** stamp in §4.1 when the clock stamps.

*Edit note — 2026-08-18, owner ruling 4 (**CORRECTION**: makes the ratified rule arithmetically exact; the rule itself is unchanged and §8.1 is not reopened).* The offsets are now fixed: `period_holdout_start = day 0 + 48 calendar days`, holdout = `[day +48, day +60)` — **offsets 48–59, exactly 12 calendar dates** — inside a corpus window of offsets 0–59. **The boundary does not slide for weekends or holidays.** Full arithmetic at §4.2; controlling text at registration §8.2 ruling 4.

**Exploration embargo — the predicate that governs every value-extraction read** (ruling 4):

```text
exploratory_access_allowed = symbol NOT IN holdout_symbols
                             AND session_date < period_holdout_start
```

⇒ the **10 holdout symbols are quarantined for the entire window**, and **every** symbol is quarantined during the **final 12 calendar dates**. Both conditions must hold; failing either makes the read unauthorized.

⚠ **The holdout artifact cannot itself be updated with the dates.** `mdq_phase_a_holdout.json` carries `"period_holdout_dates": "STAMPED_AT_FIRST_ADMISSIBLE_CAPTURE"` and its sha `6c6cf03a…` is bound into the ratified §8.1 block. Writing the dates into that file would change its hash and break the ratified binding. **The stamped dates live in §4.1 of this record and nowhere else.**

**Quarantine (ratified, binding):** exploration and all value-extraction work touch the **explore set only** — never the holdout symbols and never the holdout period. A hypothesis graduating to pre-registration is evaluated on the holdout **once**. Exploratory access to the holdout before its hypothesis is pre-registered is explicitly unauthorized (plan §10).

---

## 5. §7.1 admissibility checklist — this record shows its work

The candidate partition is admissible **only if every row below passes.** Record the **observed result**, not a verdict. A row left blank is a fail.

| # | §7.1 condition | How it is checked | Observed result |
|---|---|---|---|
| A1 | Captured **after** registration/§8 sign-off | Session date > 2026-08-17 sign-off; manifest carries **no** `label` field (a `PRE_REGISTRATION_SMOKE` label is disqualifying) | `«FILL-AT-FREEZE»` |
| A2 | Credential/account latch passed | Manifest `credential_fingerprint == 5b6f39e5198d` and `account_number == PA3BGKRLH2AP`; the latch is fail-closed, so a run that produced records necessarily passed it — confirm from the manifest, not from memory | `«FILL-AT-FREEZE»` |
| A3 | Explicit feed identity present | Manifest `feed` is literally `sip` / `iex`; partition path matches | `«FILL-AT-FREEZE»` |
| A4 | Universe scope matches frozen identity | Manifest `universe_sha256 == a022e399e216f16328eaecd809126951f6658cb09351281fa02187a0a6faf563` and `universe` lists the 50 frozen symbols | `«FILL-AT-FREEZE»` |
| A5 | Cadence scope matches frozen identity | Sampler ran at 60 s; `capture_modes` include `rest_quote_sampler_v1` and `rest_eod_bars_v1` | `«FILL-AT-FREEZE»` |
| A6 | Session scope matches frozen identity | Bars cover 04:00–16:00 ET; sampler ran 09:25 → NYSE close | `«FILL-AT-FREEZE»` |
| A7 | Freeze completed | `manifest.json` present in **both** feed partitions; `frozen_at` recorded | `«FILL-AT-FREEZE»` |
| A8 | `verify` passes | `mdq_collector.py verify --date <session>` → `verified` for both feeds, exit 0 | `«FILL-AT-FREEZE»` |
| A9 | Manifest lists all expected files; **no unmanifested strays** | `verify` reports zero `unmanifested file:` and zero `missing file:` lines | `«FILL-AT-FREEZE»` |
| A10 | Collector code identity approved for the period | Runtime files (CRLF-normalized) hash to the §2.3 blob values | `«FILL-AT-FREEZE»` |
| A11 | No post-freeze mutation | Re-`verify` after the S3 sync; the store refuses writes once frozen (`FrozenPartitionError`) | `«FILL-AT-FREEZE»` |
| A12 | **Completeness ≥ 98%** per partition **per feed** | `completeness = observed_cycles / expected_cycles`; `feed_error` records count toward the **denominator only**. **`expected_cycles` is FROZEN (registration §8.2 ruling 1, 2026-08-18):** scheduled 60 s slots `t` with `09:25 ET <= t < official NYSE close (exclusive)` ⇒ **395** on a normal close, **215** on a 13:00 early close, **0** on non-session days — the **sampler** window, **not** the 04:00–16:00 ET bar-census window. — resolves §10 Q7 | `«FILL-AT-FREEZE — state expected_cycles, observed_cycles and the ratio, for sip AND iex separately»` |
| A13 | **Max contiguous gap ≤ 10 minutes**, independent of the aggregate rate | Longest run of consecutive missing/error cycles in the quotes JSONL | `«FILL-AT-FREEZE — per feed»` |
| A14 | Durability: S3 mirror present and byte-identical | Object listing under `s3://workbench-backups-219024422756/mdq_capture/<feed>/<session>/`; re-hash mirrored objects against the local manifest — **an unverified copy is not durability** | `«FILL-AT-FREEZE — object keys + version IDs + hash-comparison result»` |

**Additional observations to record at the same time** (not §7.1 conditions, but the evidence a future reader will want):

| Item | Observed |
|---|---|
| Manifest provenance block, verbatim (`provider`, `entitlement`, `alpaca_py_version`, `capture_modes`, `collector_version`, `frozen_at`) | `«FILL-AT-FREEZE — quote both manifests in full»` |
| Per-file SHA-256 and byte counts from both manifests | `«FILL-AT-FREEZE»` |
| Bar row counts, sip vs iex | `«FILL-AT-FREEZE — diagnostic only; NOT a K3 statement»` |
| systemd timer fire evidence | `«FILL-AT-FREEZE — journalctl for mdq-sample / mdq-eod / mdq-freeze»` |
| Free space on the capture volume at each guard check | `«FILL-AT-FREEZE — vs the max(10 GB, 20%) floor»` |
| Live-stack health during the capture session | `«FILL-AT-FREEZE — any capture-induced degradation is ADR 0051 Phase-2 trigger evidence, to be recorded, not engineered around»` |

**Verdict:** `«FILL-AT-FREEZE — ADMISSIBLE / NOT ADMISSIBLE»`

> **Inadmissible ≠ failed criterion.** A partition adjudicated NOT ADMISSIBLE contributes **nothing** to K1–K6 in **either** direction — it is not a FAIL on any criterion, and it **never** counts toward the keep/cancel denominator. It is simply not in the corpus, and criteria are computed only over the corpus. Completeness is a **prerequisite for entry, adjudicated on the partition as a whole**; it is not criterion-specific, and **no criterion-specific or “partially usable” corpus exists or may be created later.** See §8.2.

---

## 6. Runtime artifact identity — box-resident, not in Git

| Artifact | SHA-256 |
|---|---|
| `/opt/workbench/mdq/mdq_run.sh` (wrapper) | **expected to begin `109931ef063d3cf4…`** — `«FILL-AT-FREEZE — full 64-hex value, recomputed on the box at freeze; if it does not begin 109931ef063d3cf4 the wrapper changed after deployment, and that is a finding, not a typo»` |
| `/etc/systemd/system/mdq-sample.service` | `«FILL-AT-FREEZE»` |
| `/etc/systemd/system/mdq-sample.timer` | `«FILL-AT-FREEZE»` |
| `/etc/systemd/system/mdq-eod.service` | `«FILL-AT-FREEZE»` |
| `/etc/systemd/system/mdq-eod.timer` | `«FILL-AT-FREEZE»` |
| `/etc/systemd/system/mdq-freeze.service` | `«FILL-AT-FREEZE»` |
| `/etc/systemd/system/mdq-freeze.timer` | `«FILL-AT-FREEZE»` |
| `/etc/systemd/system/mdq-alert@.service` | `«FILL-AT-FREEZE»` |
| **Backend container image serving `docker exec`** | `«FILL-AT-FREEZE — image ID and repo:tag the workbench-backend container is ACTUALLY running at capture time. §2.5: the §2.3 git blobs do not prove the container was recreated after the image rebuild; this row is what proves it.»` |
| **Backend container identity** | `«FILL-AT-FREEZE — container ID and Created timestamp for workbench-backend. A Created timestamp older than the image build is the signature of a container that was never recreated.»` |
| Capture-root **volume identity** | `«FILL-AT-FREEZE — device, EBS volume id, filesystem UUID and total size backing /opt/workbench/data. Observed at first timer fire: /dev/root, ~30 GB, shared — see §10 Q10»` |
| Capture-root absolute path (host, confirmed at freeze) | `«FILL-AT-FREEZE — expected /opt/workbench/data/mdq_capture»` |

---

## 7. Qualification criteria as frozen — the October verdict is adjudicated against THIS table

Reproduced from the signed registration §4 and the ratified §8.1 **for reference under pressure**. If any line here differs from the registration document, **the registration document controls and this table is in error**. Nothing here restates a criterion in order to change it.

| # | Criterion | Threshold as frozen | Evaluability as frozen |
|---|---|---|---|
| **K1** | Scanner / decision materiality | SIP changes SCAN-001 eligibility, ranking, or GAPPER-relevant upstream classification on **≥ 10%** of evaluated session-days, **or** corrects ≥ 1 predeclared gate-material IEX observation defect. **ΔVolume is a required diagnostic, never a keep trigger.** | May have **no in-corpus instance** because §8 item 14 resolved to **MDQ corpus only** — the sealed account-7 records (`c7b9371d…`, `67c400d3…`, `a892edf4…`) are **citable context, never scored**. |
| **K2** | Streaming reliability | ≥ **99.5%** session uptime over **20 consecutive sessions** at ≥ **250** symbols, zero unrecovered gaps | **NOT EVALUABLE unless G10 opens.** G10 is **CLOSED by default**; Phase A is REST-only. NOT EVALUABLE ≠ FAIL, and it cannot itself satisfy GO. |
| **K3** | Data completeness | Union grid `U` = all `(symbol, session_date, minute_ts)` keys observed by **either** feed in 04:00–16:00 ET; `missing_rate_f = 1 − observed_keys_f / |U|`; **met when `(missing_rate_IEX − missing_rate_SIP) / missing_rate_IEX ≥ 0.50`**. Raw row-count ratios are **diagnostic only**. | Evaluable; **not evaluable if `missing_rate_IEX == 0`** — no division, no artificial pass. |
| **K4** | GAPPER Stage-0 enablement | SIP supplies required upstream fields the incumbent feed measurably cannot, per the Stage-0 field-sufficiency report | **NOT EVALUABLE if Stage 0 slips the window.** Stage 0 awaits the **G4** sequencing ruling (OPEN). A scheduling artifact unrelated to SIP must not count toward Cancel. |
| **K5** | Execution evidence | Spread/mid/shortfall metrics for **≥ 90%** of paper fills. Population: **all paper fills, Phase-A symbols only**; quote match **at-or-before**, **max age 5 s**; no-quote fills excluded from **numerator AND denominator**. | **NOT EVALUABLE below `N_min` = 50 fills.** With MR-002 on HOLD and GAPPER Stage 0 unstarted, this floor is **expected to bind — by design, not by failure.** |
| **K6** | Quote fidelity | **Zero** recurrence in SIP of the IEX stub-quote artifact class (single-venue quote implying a spread ≥ **100 bps** wider than consolidated NBBO), measured against ≥ 1 observed IEX occurrence | **Option (a) signed:** NOT EVALUABLE unless ≥ 1 IEX stub-quote occurrence is captured **in the admissible corpus**. Option (b) — admitting the executor spread-gate rejection log — was **not** taken. The 60 s cadence is frozen identity and **may not be tightened** to improve the odds. |
| **C1** | Cancel | No K criterion met, judged **net of cost** — subscription **plus** incremental storage/compute attributable to MDQ-001 / OPRA-CAP-001 | Criteria scored NOT EVALUABLE **leave the keep/cancel denominator entirely**: they can neither satisfy GO nor count toward Cancel. |

### 7.1 GO floor — ratified §8.1 (§4.11), verbatim

> **GO requires at least two of K1–K6 to be BOTH evaluable AND PASS.**
> **Fewer than two evaluable ⇒ HOLD with the required extension stated explicitly.**
> Never a default Cancel on unevaluability. Never a single-criterion GO.

Enumerated worst case, ratified: under the signed choices (item 14 = MDQ corpus only; K6 = option (a); G10 closed; Stage 0 awaiting G4; fills below `N_min` plausible while MR-002 holds), **K1, K2, K4, K5 and K6 can all be NOT EVALUABLE simultaneously, leaving GO reachable on K3 alone** — which the floor converts from a surprise into a policy: that case is a **HOLD with a stated extension**, not a GO.

Verdict format (registration §5): **GO** (retain; open the governed adoption path) · **HOLD** (extend **exactly one** additional period, for a named reason stated at the verdict) · **STOP** (cancel; unwind pinned-SIP paths back to `feed=iex`).

**Completed disposition table** *(registration §5, added by owner ruling 3, 2026-08-18)* — reproduced here for reference under pressure; the registration document controls.

| Review result | Disposition |
|---|---|
| ≥ 2 criteria evaluable and ≥ 2 PASS | **GO** |
| ≥ 2 criteria evaluable and 0 PASS | **STOP** |
| Fewer than 2 criteria evaluable | **HOLD**, one stated extension |
| ≥ 2 criteria evaluable and **exactly 1 PASS** | **HOLD**, one stated extension — ⚠ **NEW DISPOSITION, PENDING EXPLICIT OWNER SIGN-OFF** |

> ⚠ **The fourth row is the one item in the 2026-08-18 correction set that ADDS a disposition rather than fixing stale prose, and it is NOT ratified.**
>
> Rows 1–3 are restatements: rows 1 and 3 are the ratified §8.1 floor verbatim, row 2 is C1 read with that floor. **Row 4 fills a genuine gap.** `≥ 2 evaluable and exactly 1 PASS` was undefined — not GO (needs ≥ 2 passes), not STOP under the old “no K criterion met” wording (one criterion *was* met), and not covered by §8.1's HOLD clause (which addresses *fewer than two evaluable*). Assigning it HOLD-with-one-stated-extension is therefore an **addition**, recorded as **proposed and awaiting the owner's explicit sign-off** in registration §8.2 ruling 3. **It must be signed before value-extraction work starts:** once exploration touches the corpus, the §8.1 evidence firewall forbids revising a verdict or evaluability clause, so an unsigned gap stops being merely open and becomes unfixable. **Nothing in this record may be read as if row 4 were ratified**, and this record — a recording instrument — cannot ratify it.

### 7.2 The evidence firewall — both directions

Ratified §8.1 / plan §4.10.1, §7.2, §10:

1. **Value-extraction / Track-3A output is INADMISSIBLE to K1–K6.** `MOM-SIP-0`, CEE, `DISC-001`, `RANGE-SIP-OBS-001` and the SIP feature library are **strategy/execution evidence and never qualification evidence.** Where the same underlying measurement is wanted for both, the MDQ calculator computes it **independently** from the frozen corpus under the registered definition.
2. **No K-criterion definition, threshold, tolerance, denominator, or evaluability clause may be revised once value-extraction work begins.** They freeze at G2 regardless; exploratory findings create **no exception**, including via a "clarification."
3. If a value-extraction finding suggests a K definition was poorly chosen, the correct move is the one the **P-2 proof already demonstrated**: record the criterion as answered-or-invalid on its own terms, preserve the run, and version the criterion **prospectively for a future cycle**. Never retune a live criterion mid-window.
4. Any pre-registration drawn from exploratory work must cite its **discovery-ledger entry** and state **how many conditions were examined in that family** (append-only ledger, §4.10.2).
5. Sequencing, ordered by the owner: `MOM-SIP-0` → CEE → feature library (scoped to what those two consume) → `DISC-001` → `RANGE-SIP-OBS-001`; the last two gated on the first producing output or an explicit owner time-box.
6. Track-3A output has **no L1/L2 authority**: candidate is not signal. No `DISC-001` surface reaches the order path, a live scanner, or a sizing decision. Existing strategy behavior stays **L0** until the Track-4 ADR path completes.

---

## 8. If a candidate day produces no admissible partition

**The clock does not start.** This is the whole point of the definition in §1 and is not a discretionary judgement.

Two distinct failure shapes exist, and they are **not** handled the same way:

**(i) The collector never ran — a NON-EVENT.**
No cycles, no files, no partition, no manifest. There is nothing to quarantine, nothing to exclude from the corpus, and no evidence of any kind was produced. It is not a "failed partition" and it must never be described as one; the corpus is exactly as empty afterwards as before. What it *is* is an operational fault that consumed a trading session, and it belongs in the attempt log so the record shows the clock start was **earned on a specific day** rather than silently assumed.

**(ii) A partition was produced but fails a §5 row — PRESERVED EVIDENCE.**
Bytes exist. They are frozen and immutable. The partition is not deleted, not re-frozen, not "repaired"; it simply never enters the corpus — exactly as the P-2 v1 FAIL was preserved rather than unsealed.

The procedure, in order:

1. **Record the failure here** — which shape (i or ii), which §5 row if applicable, the observed value, the raw evidence (journal excerpt, guard output, `verify` output, completeness arithmetic), and the timestamp of the check. Do not summarize a failure into a sentence; a future reader must be able to re-derive it.
2. **Do not modify any produced partition.** See shape (ii) above.
3. **Do not relax a threshold to make it admissible.** Completeness minimum, maximum contiguous gap, universe hash, cadence and session scope are frozen identity. Adjusting any of them after seeing a result is the failure mode the freeze exists to prevent. If a threshold is genuinely wrong, it is versioned **prospectively for a future cycle**, and this cycle records the criterion as answered on its own terms.
4. **Diagnose and fix the cause** — timer, wrapper, disk floor, network, entitlement, calendar. A fix that changes any file in §2.3 creates a **new collector code identity** and must be recorded as such before the next attempt. A fix to the box-resident wrapper or units changes a §6 hash and must be re-stamped there.
5. **Repeat next session.** The next trading session produces the next candidate, and §5 runs again from the top.
6. **Repeat until a partition is admissible.** The 60-day window then starts from *that* session date and the review date moves accordingly. A slip moves the review date; it never shortens the evidence window.
7. **Item-15 value-extraction work does not open** until a program start exists. There is no frozen admissible corpus to read.

### 8.1 Attempt log — append-only

Every trading day on which a first admissible capture was attempted, with its outcome. Append; never rewrite a row.

| # | Session date (ET) | Outcome | Shape | Reason / evidence |
|---|---|---|---|---|
| 1 | **2026-08-18** (Tue) | **NOT ADMISSIBLE — clock NOT started** | **(i) non-event** | `mdq-sample.timer` fired on schedule at **09:25:02 EDT**; the wrapper's fail-closed free-space guard refused the run: `FREE-SPACE FLOOR BREACH: 9G available < 10G floor (max(10G, 20% of 29G))`. **Zero cycles captured.** No `sip/2026-08-18` and no `iex/2026-08-18` partition exists on either feed; capture root empty; S3 mirror empty. Because the guard precedes subcommand dispatch, the 16:30 `eod` and 16:45 `freeze` runs were expected to be refused on the same condition — **no partition existed to adjudicate.** The guard behaved **correctly**: this is fail-closed working as signed, and the fault is the disk, not the collector. Failure published the `Workbench/Paper / MdqCollectorFailure` datapoint, which — having **no alarm attached** — notified nobody (§10 Q4). Earliest possible next attempt: **Wed 2026-08-19**, contingent on clearing headroom above the floor (§10 Q5, Q10). |
| 2 | `«FILL-AT-FREEZE»` | `«FILL-AT-FREEZE»` | `«FILL-AT-FREEZE»` | `«FILL-AT-FREEZE»` |

> **Note appended 2026-08-18, 15:19:32Z / 11:19:32 EDT — row 1 is NOT rewritten (the log is append-only).** Row 1
> records the state as of the morning read: the **sampler** was a non-event. Later the same day the free-space
> breach was cleared, which unblocks `mdq-eod` (16:30 ET) and `mdq-freeze` (16:45 ET) — so the session is expected
> to end with a **bar-only `2026-08-18` partition** that is frozen, manifested and mirrored. That converts the
> day's overall shape from **(i) non-event** to **(ii) preserved evidence** for the partition, while leaving row 1
> accurate about the sampler. **The partition is INADMISSIBLE and the clock still does not start** — the exclusion
> is pre-committed in **§8.2 below, written before the freeze**.

> **⚠ CORRECTION appended 2026-08-18 ~22:50Z / 18:50 EDT — the note above ANTICIPATED a partition that was never
> created. Neither note is rewritten; this one supersedes the prediction in the note immediately above it.**
>
> The 16:45 ET `freeze` reported, verbatim: `no partitions for 2026-08-18; nothing to freeze`, and exited **0**.
> **No `2026-08-18` partition exists** — not bar-only, not partial, not at all. The capture root is empty and the
> S3 mirror holds no `2026-08-18` object. Verified post-hoc: `find /opt/workbench/data/mdq_capture` returns the
> root directory and nothing beneath it.
>
> The reason is a **second, independent fault**, unrelated to the disk. Clearing the free-space breach let
> `mdq-eod` run for the first time that day, and it reached the acquisition identity latch and **failed closed**:
>
> ```text
> IdentityError: credential fingerprint b56421a28128 != pinned 5b6f39e5198d
> — refusing to acquire. If the key was rotated, re-pin deliberately.
> ```
>
> The `ALPACA_PAPER_6` key had been rotated on the box at **2026-08-17 21:32 EDT**, roughly two hours after this
> collector was deployed and pinned. The morning's free-space guard had tripped *before* the identity check ever
> ran, so the disk fault masked the credential fault; fixing the first is what exposed the second. Both faults are
> fail-closed controls behaving exactly as designed, and **no bytes were written under either**.
>
> **Therefore 2026-08-18 remains shape (i) — a NON-EVENT — for the whole day, not shape (ii).** Row 1 was right as
> logged and needs no amendment. Nothing from 2026-08-18 exists in the governed corpus to preserve, quarantine or
> exclude; there is no bar-only annex and no partition to point at. The §8.2 pre-commitment below stands as
> written and remains correct — it simply turns out to have had no subject. **This distinction matters: the record
> must not imply that any 2026-08-18 bytes exist in the governed corpus.**
>
> The credential was re-pinned to `b56421a28128` under owner authorization on 2026-08-18 (same broker account
> `PA3BGKRLH2AP`, verified ACTIVE by a read-only `GET /v2/account`); see §2.3.

**Disposition for attempt 1 — owner-supplied text, transcribed VERBATIM (owner review, 2026-08-18).** The status label is a name, not prose; do not paraphrase it. Recorded here rather than inside the table cell so the wording survives intact, and appended rather than written into row 1, which stays as logged.

```text
2026-08-18 disposition:
INADMISSIBLE — PRESTART / NO GOVERNED QUOTE-SAMPLER CYCLES

Reason:
0 observed sampler cycles versus the frozen expected-cycle requirement.
The 04:00–16:00 IEX/SIP EOD bar capture may be preserved and verified,
but no measurement from this partition is admissible to K1–K6,
including K3.

This is an admissibility failure under §7.1 completeness, not a
finding about SIP/IEX bar quality and not a K3 FAIL.
```

### 8.2 Pre-commitment — the `2026-08-18` partition is EXCLUDED *(owner ruling, recorded before the freeze)*

> **⚠ Read this first — appended 2026-08-18 ~22:50Z, after the freeze.** The partition this subsection was written
> about **was never created.** `mdq-eod` failed closed on the credential identity latch and `mdq-freeze` reported
> `no partitions for 2026-08-18; nothing to freeze`. **No 2026-08-18 bytes exist in the governed corpus** — there
> is nothing to exclude, quarantine or preserve, and nothing anywhere to point at. See the correction note in §8.1.
>
> This subsection is **retained unchanged and remains correct.** Two reasons it is not deleted. First, its value
> was never conditional on the partition existing: it was written *before* the outcome was known, and a
> pre-commitment that is discarded once it turns out to be unnecessary is not a pre-commitment — the record of
> having bound the decision in advance is the artifact. Second, **the two numbered rules below are standing rules,
> not facts about 2026-08-18**: they govern every future partition, and the first day one of them binds is the
> first day a partial partition actually freezes. Read the paragraphs below in that light — where they say
> "this partition," the subject is hypothetical, not historical.

**Written at `2026-08-18T15:19:32Z` (UTC) = `2026-08-18 11:19:32 EDT` (ET).** Both labels are given because the
timestamp is the whole point of this subsection: it is **before** `mdq-eod` (16:30 ET), **before** `mdq-freeze`
(16:45 ET), **before** any `2026-08-18` partition exists, and **before anyone has examined its contents.**

**What is expected to happen tonight.** With the free-space breach cleared (§3.3), `eod` will fetch 04:00–16:00 ET
one-minute bars for **both** feeds into a `2026-08-18` partition, and `freeze` will seal, `verify` and mirror it.
The corpus will therefore contain a frozen, manifested, S3-mirrored `2026-08-18` partition with **valid bars and
zero quote cycles**.

**Owner-supplied disposition text — reviewed and confirmed by the owner, 2026-08-18. Transcribed VERBATIM.** The label `INADMISSIBLE — PRESTART / NO GOVERNED QUOTE-SAMPLER CYCLES` is a **status name, not prose**: it is not to be paraphrased, abbreviated, re-worded, or “tidied” in this or any later artifact. This is the wording that has to survive to the October adjudication.

```text
2026-08-18 disposition:
INADMISSIBLE — PRESTART / NO GOVERNED QUOTE-SAMPLER CYCLES

Reason:
0 observed sampler cycles versus the frozen expected-cycle requirement.
The 04:00–16:00 IEX/SIP EOD bar capture may be preserved and verified,
but no measurement from this partition is admissible to K1–K6,
including K3.

This is an admissibility failure under §7.1 completeness, not a
finding about SIP/IEX bar quality and not a K3 FAIL.
```

*(“§7.1 completeness” in the block above is the **admissible-corpus rule** — plan §7.1 / registration §4 — which §5 of this record implements row by row. It is not §7.1 of this document.)*

**The ruling, recorded in advance:**

1. **The `2026-08-18` partition is INADMISSIBLE.** Completeness is **0 of 395** expected sampler cycles per feed
   (denominator per registration §8.2 ruling 1) against a ratified **≥ 98%** floor — §5 row **A12** fails outright,
   on both feeds.
2. **It is excluded from K1–K6 in their entirety — K3 specifically included** — notwithstanding that its bars are
   structurally valid.
3. **The ground of exclusion is §7.1 completeness, not bar quality.** Stated explicitly so it cannot later be
   re-argued on bar quality: the bars may be perfectly good and the partition is *still* inadmissible, because
   admissibility is a property of the partition against the frozen identity, not a property of the rows a reader
   likes. No finding about bar quality — favourable or otherwise — reopens this.
4. **It does not start the clock.** §1 is unchanged: program start is the first **admissible** governed frozen
   partition. §4.1 stays empty.

⚠ **2026-08-19 is NOT predeclared as the start.** It is the **earliest date on which a start is not yet ruled out** — nothing more. Running the sampler is **not** qualifying: the 08-19 partition starts the clock only if and when it passes **every** §5 row and is adjudicated ADMISSIBLE. Until that adjudication, §4.1 stays empty, no review date exists, and no holdout dates exist. Every 08-19 figure anywhere in this document is a **clearly-labelled conditional worked example**, never a stamped value.

**The two load-bearing points, stated as general rules rather than as facts about this one partition.**

1. **Completeness is a prerequisite for entry into the K1–K6 corpus. It is not criterion-specific.** A partition either enters the corpus or it does not; admissibility is adjudicated **on the partition as a whole**, before any criterion is computed against it. A partition carrying valid 04:00–16:00 ET bars and zero quote-sampler cycles is therefore inadmissible **in its entirety** — not “inadmissible for the quote-derived criteria and usable for the bar-derived ones.” This is the standing rule and it governs every future partition, not just `2026-08-18`.
2. **No separate “K3-valid but sampler-incomplete” corpus exists, and carving one out later is foreclosed.** Creating a second corpus with a laxer entry rule would be **weakening the frozen rule after seeing the data** — precisely the move this pre-commitment exists to prevent. The admissible corpus is the one defined at registration §4 and adjudicated by §5 of this record. There is no second corpus, no “bars-only annex,” and no criterion-specific admissibility. **This forecloses the carve-out prospectively**, while nobody has yet looked at the bars.

**Inadmissible ≠ failed criterion — and the distinction runs in both directions.** A partition excluded on admissibility contributes **nothing** to K1–K6, in **either** direction. It is **not a K3 FAIL**, it is not evidence against SIP, it is not evidence for SIP, and it **must never be counted toward the keep/cancel denominator**. It simply is not in the corpus, and a criterion is computed only over the corpus. This is exactly the distinction §4.11's evaluability logic turns on — NOT EVALUABLE criteria leave the denominator entirely rather than counting as failures — and getting it wrong in **either** direction corrupts the verdict: reading this partition as a K3 FAIL manufactures evidence against SIP that nobody measured, while reading its bars as a K3 PASS manufactures evidence for SIP from a partition the frozen rule excluded.

**Why this had to be written now rather than in October.** K3's frozen metric is the **union `(symbol, session_date,
minute_ts)` grid over 04:00–16:00 ET on both feeds** — which is *exactly* what a bar-only partition contains. So
this partition is inadmissible on completeness while simultaneously holding K3-relevant data, and that is precisely
the shape of evidence someone can later argue into the corpus in good faith: *“the sampler failed, but the bars are
clean — use them for K3.”* Deciding this **after** seeing the bars would be a post-hoc admissibility judgement made
with knowledge of the data, which is the failure mode the freeze exists to prevent. Deciding it **before** the
partition exists costs nothing and is binding. This is a **pre-commitment under plan §4.10.1 / registration §8.1**
(the evidence firewall), **not** a post-hoc judgement.

**Why exclusion is the only available control.** The S3 mirror prefix
`s3://workbench-backups-219024422756/mdq_capture/` is **PUT-only for the instance role** — by design, so the box
cannot destroy its own mirrored evidence (§3.4). Once this partition is mirrored it **cannot be withdrawn**. It will
sit in the archive for the life of the program, structurally valid and permanently inadmissible. The exclusion
recorded here is therefore the *only* control available, which is exactly why it is made in advance rather than
relied upon later.

**Handling.** Shape **(ii) preserved evidence** per §8: the partition is **not** deleted, **not** re-frozen, **not**
repaired, and **not** hand-edited. It is preserved exactly as frozen — the same treatment the P-2 v1 FAIL received —
and it simply never enters the corpus. When §5 is run against it for the record, row A12 is expected to read
`0 / 395 = 0%` on both feeds; that adjudication is bookkeeping confirming this pre-commitment, not a re-decision of
it.

```
Recorded by / at:   developer session — 2026-08-18T15:19:32Z / 11:19:32 EDT,
                    before mdq-eod (16:30 ET) and mdq-freeze (16:45 ET)
Owner ruling:       Jay Wang — 2026-08-18, issued in session ("let it run, and
                    pre-commit the exclusion now, before the freeze")
Status:             BINDING as a pre-commitment. The clock has NOT started.
Observed values:    «FILL-AT-FREEZE — the actual A12 arithmetic and manifest
                    identities for the 2026-08-18 partition, recorded after the
                    16:45 ET freeze. Recording them CONFIRMS this exclusion; it
                    cannot revise it.»
```

---

## 9. What this record does NOT do

- It does **not** reopen the signed registration §8 block or the ratified §8.1 block. Both are additive-closed.
- It does **not** authorize Phase B / K2 streaming (**G10 is closed**), any capture-scope widening (no auction prints, no tick trades), a second subscription, or MDQ direct use of the `_6` credential.
- It does **not** authorize GAPPER Stage-0 execution (**G4 open**), MR-002 work (**HOLD**), reserve-strategy code (**G9**), or any L1/L2 strategy behavioral migration.
- It does **not** authorize the live-consumer cutover (bar cache, quote service, risk-gate price reads, strategy bars) onto the local store. That changes the **order path's data dependency** and requires its **own ADR** (Track 4 / G7).
- It does **not** grant any MDQ component order or broker capability. ADR 0051 research-plane isolation and the no-broker-capability invariant hold unchanged.
- It does **not** make the box's systemd units or wrapper governed artifacts. They are box-resident; §6 records their hashes only.
- It does **not** authorize any change to the free-space floor, the capture root, or the backing volume. §8.1 shows the floor doing its job; remedying the disk is an owner decision (§10 Q5, Q10), not a threshold adjustment.

---

## 10. Open questions for the owner *(raised at drafting; none resolved here)*

| # | Question |
|---|---|
| **Q1** | ✅ **RESOLVED — owner ruling 4, 2026-08-18** (registration §8.2; arithmetic at §4.2, §4.4). Corpus window = **offsets 0–59**; `review_end_exclusive = day 0 + 60`; `period_holdout_start = day 0 + 48`; holdout = **offsets 48–59, exactly 12 calendar dates**; **the boundary does not slide for weekends or holidays**. *(Original question retained:)* The rule is "the final 12 calendar days of the 60-day window" — is the window `[day 0, day +60]` or `[day 0, day +59]`, and is the holdout `[day +49, day +60]` or `[day +48, day +59]`? |
| **Q2** | ⚠ **PARTIALLY RESOLVED — still open on the adjudication date itself.** Owner ruling 4 (2026-08-18) answers the second half: the **holdout does NOT shift** — it is fixed by calendar-day offset from day 0 and never slides for weekends or holidays. **Still open:** two of the three near-term candidate day-0 dates put day +60 on a weekend (a 2026-08-19 start ⇒ **Sunday 2026-10-18**). Does the **verdict / adjudication date** roll forward to the next business day, back to the prior, or stay on the calendar day? Note the window boundary itself is unaffected either way — only the day the owner sits down to adjudicate. |
| **Q3** | **Governance of the box-resident schedule.** The systemd units and `/opt/workbench/mdq/mdq_run.sh` enforce frozen identity (universe-hash pin, free-space floor, single-sampler check) but exist only on the box. They are arguably *governing* under ADR 0050. Commit them to Git, or leave them hash-recorded here only? §8.1 is the argument for committing: the wrapper's behavior is now load-bearing evidence in this record. |
| **Q4** | ✅ **RESOLVED 2026-08-18** — a CloudWatch alarm is now wired on `Workbench/Paper / MdqCollectorFailure` (§3.3, reported by the operating session; alarm identity is not stamped in this record). *(Original question retained:)* **Unwired failure alarm — now demonstrated, not hypothetical.** `OnFailure` writes `/opt/workbench/data/mdq_capture_alerts.log` and emits CloudWatch `Workbench/Paper: MdqCollectorFailure`, but **no alarm is attached**. On 2026-08-18 the collector failed all day and the datapoint notified nobody; the failure was found by a manual health read. Over a 60-day window this is the GAPPER-v1 "records present, sufficiency absent" pattern in its purest form — silent, and discovered late. Wire an alarm before the window accrues? |
| **Q5** | ⚠ **PART (a) ADDRESSED 2026-08-18** — build-cache prune plus removal of two superseded image tags took the volume from **8.1 GB to 12 GB free** against the 10 GB floor, which unblocks `eod`/`freeze` today and the sampler from Wed 2026-08-19 (§3.3). **Part (b) remains OPEN** — the recurring growth that consumed ~5 GB overnight is not diagnosed, and a one-off reclaim on a shared 30 GB root buys sessions, not a window; see Q10. *(Original question retained:)* **Disk headroom — the floor has already bound.** Free space fell from 14 GB at deployment (2026-08-17 evening) to **9 GB by 09:25 the next morning**, costing a full session before a single cycle was captured. That is roughly 5 GB consumed overnight on a volume the collector does not control. Two decisions: **(a)** what is reclaimed or expanded to get above the floor, and **(b)** what recurring growth caused it — because a one-off cleanup that leaves the same growth rate buys one or two sessions, not sixty. |
| **Q6** | ✅ **RESOLVED — owner ruling, 2026-08-18: FIVE files**, `__init__.py` included (§2.3). It is imported at runtime and re-exports the package API, so excluding it left a runtime-loaded file outside the identity; the 2026-08-17 four-file set was an **omission**, and re-stamping before any corpus exists is the free moment to correct it. Hashes stamp at the **merge commit** and are left empty until it exists. *(Original question retained:)* **Collector code-identity set: 4 files or 5?** The 2026-08-17 conformance check hashed `mdq_collector.py`, `store.py`, `collector.py`, `identity.py`. `app/research/capture/__init__.py` (blob `da6c0036…`) was not included, yet it is imported at runtime and re-exports the API. Should it be added to the approved set? |
| **Q7** | ✅ **RESOLVED — owner ruling 1, 2026-08-18** (registration §8.2; restated at §3.2 and §5 A12). **(a)** The denominator is the **sampler** window — `09:25 ET <= t < official NYSE close (exclusive)`, 60 s slots ⇒ **395** / **215** on a 13:00 early close / **0** on non-session days — **not** the 04:00–16:00 ET bar-census window. **(b)** The fixed-delay `sleep(cadence)`-after-work loop is a **runtime defect**, not evidence that the floor is too strict: it is being replaced by **fixed-rate scheduling against an absolute monotonic deadline** (no burst/catch-up, close checked before each cycle, `scheduled_slot_ts` / `slot_index` persisted per cycle so observed cycles reproduce against the frozen grid). **The 98% floor and the 10-minute gap are NOT weakened to accommodate a defective runtime.** The scheduler patch creates a **new collector code identity** — see §2.3. *(Original question retained:)* ⚠ **`expected_cycles` is a formula, never a number — and the arithmetic may not clear its own floor.** Plan §4.9 defines `expected_cycles = f(session_scope, cadence, market calendar)` and freezes completeness at **≥ 98%**, but no session ever resolved `f` to a value. Two sub-questions, both material: **(a) Which window is the denominator?** The registered *census* scope is 04:00–16:00 ET, but the deployed *sampler* runs 09:25 → NYSE close (≈ 395 minutes ⇒ ≈ 396 cycles/feed on a full day). The bars cover 04:00–16:00; the quotes do not. Confirm the quote denominator is the sampler window, not the census window — under the census window every partition is ~55% complete and **nothing is ever admissible.** **(b) Cadence drift may breach the floor with a perfectly healthy network.** `cmd_sample` does work, then `sleep(cadence)`, so the true period is `60 s + request time`, not 60 s. Over 395 minutes: ~1.0 s per-cycle overhead ⇒ ≈ 389 cycles ⇒ **98.2%** (just clears); ~1.5 s ⇒ ≈ 386 ⇒ **97.5%** (**fails**); ~2.0 s ⇒ ≈ 383 ⇒ **96.7%** (**fails**). Two REST calls per cycle plausibly cost more than 1.5 s. Either the denominator must be defined as *elapsed-time-derived achievable cycles* rather than `duration / cadence`, or the floor is measuring scheduler drift rather than data availability. **Settle this before the first admissibility adjudication, not after a partition is rejected** — and note that settling it is a *denominator definition*, which §7.2 rule 2 forbids revising once value-extraction begins. |
| **Q8** | ✅ **RESOLVED — owner rulings 2 and 3, 2026-08-18.** Ruling 2: **§8.1 controls**; registration §4 has been corrected to "GO — retain only if at least two of K1–K6 are both EVALUABLE and PASS," a consistency correction that reopens no threshold. Ruling 3 additionally completes the disposition table (§7.1 above) — and note that its fourth row, `≥ 2 evaluable and exactly 1 PASS`, is an **addition still awaiting explicit owner sign-off**. *(Original question retained:)* **"ANY K" vs the ≥ 2 GO floor.** Registration §4 (signed) reads "**Keep the subscription if ANY K criterion is met**"; ratified §8.1 sets "**GO requires ≥ 2 of K1–K6 both evaluable AND PASS**". §8.1 is later, more specific, and explicitly additive — so the ≥ 2 floor governs — but the §4 sentence was never edited and still reads the other way. Confirm the reading for the record, so the October adjudication is not litigating which sentence wins. |
| **Q9** | **Stale "14-symbol" language in plan v0.8 §4.11.** The verdict-reachability worst case reasons about "a 60-day **14-symbol** capture" (the in-code `PHASE_A_UNIVERSE` default). The frozen universe is **50** symbols. This does not change the ratified floor, but it does make K6's odds of observing a stub-quote occurrence better than the ratified worst case assumed. Note as a correction, or leave the ratified enumeration untouched as the conservative bound? |
| **Q10** | ⚠ **The capture root is not on a dedicated persistent volume.** Plan §1.3 and registration §6.1 place the collector and its store on the governed host's **persistent volume**. As deployed, `/opt/workbench/data` sits on **`/dev/root`** — a single ~30 GB root disk shared with Docker images and layers, `/var/log`, a 4.1 GB swapfile, the SQLite trading book, and existing research artifacts. The collector therefore **competes for space with the execution backend**, which is the coupling the ceiling and floor were written to prevent, and it is the direct cause of the §8.1 non-event. This is an **ADR 0051 Phase-2 trigger candidate** (capture activity affecting the shared host) and should be **recorded as trigger evidence, not engineered around in place**. Decision needed: attach a dedicated EBS volume and re-point `WORKBENCH_MDQ_CAPTURE_ROOT` before the window starts, or accept the shared root for this cycle with the recurring-growth risk in Q5 explicitly owned? Note that moving the capture root before day 0 is free; moving it mid-window changes capture-root identity and must be stamped in §6 and reconciled against the corpus. |

---

## 11. Owner stamp

This record is **not effective** until this block is completed. **As of drafting it is unsigned and the clock has not started.**

```
Program start ADMISSIBLE:   [ ] yes — §5 all rows pass; §4.1 stamped
                            [ ] no  — §8.1 attempt log appended; the clock does NOT start

First admissible session:   ____________________  (ET session date)
Freeze timestamp:           ____________________  UTC
                            ____________________  ET
60-day clock start (day 0): ____________________
Computed review date:       ____________________  (= day 0 + 60 calendar days)
Holdout period:             ____________________  ..  ____________________

Deployed commit:            0273012 / 027301223d8e88ce616e90a2d6831d689f2964f0
Universe (derived):         a022e399e216f16328eaecd809126951f6658cb09351281fa02187a0a6faf563
Acquisition identity:       fp 5b6f39e5198d / PA3BGKRLH2AP

Open questions §10:         [ ] answered below / separately   [ ] deferred, with the
                                consequence that ____________________
                            (Q7 is a denominator definition and should be settled BEFORE
                             the first admissibility adjudication; Q5/Q10 are blocking
                             the first capture outright)
                            UPDATE 2026-08-18: Q1, Q4, Q6, Q7, Q8 RESOLVED; Q2 and
                            Q5 partially resolved; Q3, Q9, Q10 still open.

Carried, NOT signed here:   registration §8.2 ruling 3 — the `>= 2 evaluable and
                            exactly 1 PASS` disposition is an ADDITION and is
                            UNSIGNED. It is signed in the REGISTRATION document,
                            not here; this record cannot ratify it. It must be
                            signed BEFORE value-extraction work begins.
                            The scheduler patch (ruling 1) creates a NEW collector
                            code identity; §2.3 must be re-stamped before the first
                            admissible capture — FIVE files (owner 2026-08-18,
                            __init__.py included), hashed at the MERGE COMMIT — and
                            §6 must pin the container image actually serving
                            docker exec (§2.5). Git blobs alone do not prove the
                            container was recreated.

Stamped by / date:          ____________________
```

---

## 12. Authority

Recording instrument for a governed program clock. Subordinate to: the MDQ-001 registration document (signed §8, ratified §8.1), the Algo Trader Plus implementation plan, every owner ruling, ADR 0051, ADR 0050 / GITHUB-OPS-001 v1.2, and the platform's architectural invariants. It creates no authority and relaxes no gate. Where it conflicts with any of those, they control.
