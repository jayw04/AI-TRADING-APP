# Algo Trader Plus / Strategy Proposals v1.4.1 — Implementation Plan

| Field | Value |
|---|---|
| Document version | **v0.14 (LOW-001 Dynamic-PIT cross-program integration boundary + state sync; still DRAFT)** |
| Initial version date | 2026-08-22 |
| **Last state sync** | **2026-08-26** — 08-26 governed partition **COMPLETE + SEALED** (395/395, custody verified independently); corpus = **5 governed trading days**; **verdict reachability narrowed to K1+K3** (K5 foreclosed by signed §8.4, K2 hard deadline **2026-09-21**); SEC-001 §J superseded (V3-RC STOP, token SPENT, V3.1 successor) |
| Supersedes | **`AlgoTraderPlus_v1_4_1_ImplementationPlan_v0_13.md` and all earlier drafts. v0.13 and earlier are historical only; v0.14 is the sole current implementation-plan version.** |
| Basis | `docs/Strategies/Strategy-proposals-v1_4_1-Algo-Trader-Plus-2026-08-15.md` + `docs/Strategies/AlgoTraderPlus_Data_Inventory_Report_v1_1_2026-08-17.md` + Strategy Author Data and Validation Brief v1.2 + owner rulings and sealed evidence through 2026-08-17 (P-2 v2 proof, collector validation disposition, account-7 P0 closure records) + `docs/design/MDQ-001_Registration_v1_0_DRAFT.md` **as merged to `main` with the signed §8 block and the ratified §8.1** (PR #634 = `63c0c52`) + the merge chain #634 → #636 (`be4235d`, feed-pinning guard CI-enforced) → #637 (`0273012`) + the governed deployment executed on `ec2-paper` on the night of 2026-08-17 **+ the governed state-sync and ruling records of 2026-08-18 → 2026-08-26**: the D0 admissibility adjudication and Program-Start Record v0.2 (+ Amendment A, `e488440`/#672) · the 2026-08-20 rulings · the discovery-ledger acceptance and CEE authorization/Observation Record 001 · the GAPPER G4 closure record · the SEC-001 V3 governing records under `docs/design/SEC-001/` (disposition ruling, store pre-ingestion freeze, universe-liquidity defect ruling, pre-crawl coverage freeze, canary-defect remediations A–E, execution-control addenda v1.4.1/v1.4.2) · the 2026-08-22 SEC-001 production conformance incident · the 2026-08-24 MDQ capture non-event record (`311863cb`/#679) and the 5-gate acquisition-readiness control (`363daa08`/#673) · the 2026-08-25 MDQ capture recovery record (`5a48ee88`/#684) and its provenance addendum (`379eca63`/#689) · the 2026-08-26 state sync below, including the K5/`N_min` and §8.4 verdict-reachability closures read from `docs/design/MDQ-001_Registration_v1_0_DRAFT.md` |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Sequence all v1.4.1 implementation work while preserving strategy/research gates **and convert Algo Trader Plus capabilities into measurable strategy, execution, and profitability improvements as quickly as governance permits.** Platform/data work may proceed where authorized; reserve-strategy code remains prohibited until its pre-registration gate opens. |
| Related parallel workstream | **LOW-001 Dynamic PIT** — governed separately under `TradingWorkbench_LOW001_Dynamic_PIT_Execution_Design_Implementation_v0.5.md` *(v0.5 at 2026-08-23; v0.4 superseded)*. Shared neutral infrastructure is allowed; **the signal boundary is bidirectional** — DISC/Opportunity/MDQ signal coupling into LOW-001 is prohibited, **and** LOW-001 decision records/holdings/intents/orders are not Opportunity/DISC inputs (§1.4). |
| Version-control rule | **ONE CURRENT PLAN ONLY.** Operational/state changes must update v0.14 (or its future direct successor). Do not maintain a newer state on an older-numbered draft. Prior versions remain evidence/history only. |
| Governance stance | Planning document only. Governed program artifacts, frozen designs, sealed verdicts, owner rulings, ADRs, and promotion gates control over this plan. **Research is instrumental, not the product: the platform objective is to produce robust, deployable, net-profitable strategies and measurable execution/risk improvements, not to maximize research volume.** |
| Subscription ruling | **No second Algo Trader Plus subscription.** Workbench account 7 (`ALPACA_PAPER_6`, broker `PA3BGKRLH2AP`) is the sole entitled SIP acquisition identity. The **Phase-A acquisition collector is the sole authenticating component**; MDQ-001 **analysis/calculators** are offline read-only consumers of frozen partitions and receive no Alpaca credential. *(Precision fix at v0.5 — v0.4's blanket "MDQ-001 does not authenticate" contradicted §1.1/§3.1, where `identity.py` performs a pinned read-only `/v2/account` check.)* |
| Out of scope | Reserve-strategy code before gates open · MR-002 work of any kind (**TERMINATED 2026-08-22 without an economic verdict**; the former HOLD no longer describes its state) · GAPPER Stage-0 **execution against a corpus that fails the §3.1 contract** (G4 CLOSED 2026-08-22; the remaining bar is data sufficiency, not sequencing) · Phase-B streaming implementation unless separately authorized · live-consumer cutover before the local-cache ADR · reopening rejected RNG/MOM variants without a **new economic mechanism** and new prospective registration · anything v1.4.1 §14 says not to start |

---

## State sync — 2026-08-26 *(applied in place per the ONE CURRENT PLAN rule; no new version)*

**Headline: the 2026-08-26 governed partition is COMPLETE and SEALED on both feeds. The corpus is now
five governed trading days.** Nothing in this sync changes research authority, K1–K6, D0, the review
window, the holdouts, the DISC-001 gates, the DISC-MDQ hold, or the value-extraction priority order.
⚠ Every state figure below is a **point-in-time reading**, stamped with when and how it was measured.

### A. 2026-08-26 — GOVERNED PARTITION COMPLETE

The three-proof readiness standard was met in full **before** the slot, and readiness is **not** capture
evidence — the 2026-08-24 lesson, unchanged. The day earned evidence status only from its own terminal
execution.

| Proof | Evidence |
|---|---|
| 1. Early preflight | **READY 5/5**, `2026-08-26T12:04:01Z`, 81 minutes of margin before the slot |
| 2. Near-slot preflight | **READY 5/5**, `2026-08-26T13:14:40Z`, 10 minutes before the slot |
| 3. Natural timer start | `TriggeredBy=mdq-sample.timer`, `09:25:02 EDT`, PID 4081042. **Nothing hand-started** |

Both preflights ran the governed control at its verified identity —
`apps/backend/scripts/mdq_preflight_readiness.sh`, sha256
`2ad345b83aa3c81d3ab5041614e8e6b0d8c647f83affe1d126207ba497b902ba`, matching the blob merged at
`363daa08` (#673).

**All three custody legs OBSERVED, not inferred:**

| Leg | Result |
|---|---|
| `mdq-sample.service` | `Result=success`, `ExecMainStatus=0`, 09:25:02 → 15:59:00 EDT. ⭐ **`sampled 395 cycle(s) x 50 symbols x 2 feeds (395/395 scheduled slots)`** — a completeness proof, not merely a zero exit. Identity re-verified in-run at 09:25:04 (`PA3BGKRLH2AP`, `b56421a28128`) |
| `mdq-eod.service` | `Result=success`, 16:30:00 → 16:30:04 EDT; wrote **16,149 iex** / **25,685 sip** 1-min bar rows; identity re-verified at 16:30:02 |
| `mdq-freeze.service` | `Result=success`, 16:45:02 → 16:45:05 EDT, full sequence **frozen → verified → mirrored** on both feeds |

`ALERTS_TODAY = 0` for the entire session. Line counts corroborate the log line independently:
**19,750 rows per feed = 395 × 50**, both feeds identical.

**Partition shape — 3 files per feed, byte-consistent with the reference days:**

```
iex/2026-08-26  bars/bars_1min.parquet 495,870 | quotes/samples.jsonl 5,733,616 | manifest.json 1,467
sip/2026-08-26  bars/bars_1min.parquet 894,017 | quotes/samples.jsonl 5,742,972 | manifest.json 1,467
```

⭐ **S3 custody verified INDEPENDENTLY** — my own `s3 ls` / `head-object`, **not** the box's mirror log
line. All **6** objects present under
`s3://workbench-backups-219024422756/mdq_capture/{iex,sip}/2026-08-26/`, every `ContentLength` equal to
the manifest byte count, and **every host MD5 equal to the returned ETag** (stated as *measured
equality*; `PartsCount` is null and `ChecksumSHA256` is null, so no S3-side SHA-256 verification exists
— SHA-256 was verified host-side against the manifests). Host sha256 for all four data files matches
the manifest entry exactly.

⭐ **The governance tuple is unchanged, so the corpus did not split:** `schema mdq-capture-manifest/1`,
`collector_version mdq-collector/0.1.0`, `provider alpaca`,
`entitlement algo_trader_plus (account-7 login)`, **`credential_fingerprint b56421a28128`**,
**`account_number PA3BGKRLH2AP`**, `alpaca_py_version 0.44.0`,
`capture_modes [rest_quote_sampler_v1, rest_eod_bars_v1]`, `universe_sha256
a022e399e216f16328eaecd809126951f6658cb09351281fa02187a0a6faf563` (50 symbols).

**Corpus: five governed trading days per feed — 2026-08-19, 08-20, 08-21, 08-25, 08-26.**
Seven trading days have elapsed since D0; six captured; **2026-08-24 remains the sole loss** and stays
closed as a non-event with zero evidence contribution. 08-22 and 08-23 were the weekend — there is no
unexplained gap in the chain.

### A.1 ⚠ PROVENANCE SEAM — the #690 backend rebuild landed BETWEEN the sampler and the EOD/freeze legs

⚖ **Owner-classified 2026-08-26: a runtime seam with MDQ code continuity, NOT a corpus split. The
partition is not reopened.** Recorded here as provenance because a later reader must not assume a
homogeneous backend runtime across all three capture legs.

**Measured timeline** (read from the box `2026-08-26T21:08:38Z`, not inferred):

```
19:59:00Z  sampler END      old container a743e000fdf7 / image 66d98489d70d
20:23:02Z  image BUILT      new image ada7a5be76ba   <- carries #690 (5c5969e)
20:23:48Z  container RECREATED  656428498ad0
20:30:00Z  EOD              NEW container
20:45:02Z  freeze           NEW container
```

**Why this does not split the corpus — proven, not asserted:**

1. **#690 changed no MDQ implementation.** `5c5969e` touches `app/jobs/sqlite_backup.py` (new),
   `app/lifespan.py`, `tests/jobs/test_sqlite_backup.py`, `docs/runbook/deployment.md`,
   `docs/runbook/on-call.md`, `scripts/backup_db.sh` — backup-job / lifespan / runbook / test code only.
2. ⭐ **MDQ code continuity proven by HASH, not by reading the PR diff.** All five governed blobs inside
   the **running** container are byte-identical to `origin/main`:
   `scripts/mdq_collector.py b5feb2a9…`, `capture/identity.py 588e258f…`, `capture/store.py 22c3405e…`,
   `capture/collector.py e5e030a9…`, `capture/admissibility.py 5eb3c0b5…`.
3. **The registered acquisition identity is unchanged** — both manifests carry
   `credential_fingerprint b56421a28128` / `account_number PA3BGKRLH2AP` / `collector_version
   mdq-collector/0.1.0` / `universe_sha256 a022e399…`, and the terminal custody chain succeeded.
4. ✅ **The acquisition environment SURVIVED this rebuild**, unlike 2026-08-23: `/opt/workbench/.env`
   is byte-stable at **1,160 B, md5 `3871d041a651336aad40bbf176e8f1c4`, mtime 08-25 16:40:21 EDT**.

#### 🚨 A.1.1 THE SEAM EXPOSED A LIVE SELF-REPORT DEFECT — state this precisely

⛔⛔ **`.deploy_src_sha` remaining `07a9233` is NOT continuity evidence here — it is the defect.**
The rebuild moved the runtime **without updating either identity file**:

| Source | Declares | Reality |
|---|---|---|
| `/opt/workbench/app/.deploy_src_sha` | `07a92330…`, mtime **2026-08-25 21:25:19 EDT** | untouched by the 08-26 rebuild |
| `DEPLOYED_BUILD_INFO.json` | `deployed_repository_commit 07a92330…`, `built_at_utc` **`2026-08-26T01:19:05Z`** | actual image built **`2026-08-26T20:23:02Z`**, image `ada7a5be76ba` |

⇒ **The box is running code that its own identity declaration does not describe.** Any statement of the
form "the pin still reads `07a9233`, therefore the runtime is unchanged" is **invalid** — that inference
is exactly what this seam falsifies.

⭐⭐ **This is the runtime-self-report repair track demonstrating its own necessity in production, on
the same day it was authorized.** The repair is not a hygiene improvement; the deployment self-report is
*currently inaccurate*, and it failed silently. Its three-source design (embedded build commit ·
independently derived runtime artifact digest · deploy-written manifest, all three agreeing, fail-closed
on missing source or mismatch) would have caught this at the moment of divergence.

⚠ Carry forward with [[gotcha-redeploy-starves-capture-disk]] and the 2026-08-25 lesson: **a deployment
SHA is a point-in-time reading, not a property of the box** — and now, additionally, **a stale pin can
read as “unchanged” while the runtime has already moved.** Always stamp *when and how* it was measured,
and never treat pin-stability as runtime-stability.

### B. Owner freeze — first condition DISCHARGED

The 2026-08-26 freeze (no backend restart, deployment, `.env` rewrite, image replacement, or LOW-001
proof execution) was scoped **until the 08-26 governed partition is SEALED**. Section A discharges that
condition. ⛔ It does **not** by itself authorize any mutation — see section C, and note that the
runtime-self-report repair track *reopens for authorization*, it does not self-authorize.

**Freeze predicates held throughout, verified at 12:04Z and 13:14:40Z:** `.deploy_src_sha` =
`07a92330108390f8d5299e36b411150c08b9160c` (unchanged; **trails** Git `main@379eca6` — `379eca63`/#689
is a child of `07a9233`) · `/opt/workbench/.env` 1,160 B, md5 `3871d041a651336aad40bbf176e8f1c4`,
mtime unmoved · backend container `a743e000fdf7` created `2026-08-26T01:23:08Z` and **not restarted** ·
image `66d98489d70d`.

**Builder-cache prune — CLOSED PASS** (`02:07:37Z → 02:08:31Z`). Authorized mutation was
`docker builder prune -f` **only**; reclaimed **18,383,093,760 B**, avail
`22,413,398,016 → 40,796,491,776 B`. Images 10→10, containers 5→5, backend not restarted,
`.deploy_src_sha` unchanged, `.env` byte-stable, capture root untouched. A **capacity-maintenance act**,
not a deployment.
⭐ The durable lesson is qualitative: measure reclaimable cache and free bytes **every time**; never
predict reclaimed capacity from a prior event — this run reclaimed roughly 6× the earlier precedent.
⛔ Remaining reclaimable **image** space stays NO ACTION under separate authority.

### C. LOW-001 Run 2 — HOLD, and the gate is CONJUNCTIVE

The 2026-08-26 Run-2 window (09:35–10:00 ET) **closed unused**. Nothing was run and nothing was staged.
Strategy 8 remains **IDLE**; Dynamic PIT is **CLOSED**; B3a is deployed with its production proof
**unclosed**; #687 remains **HOLD**.

⚖ **Owner ruling, 2026-08-26 — sealing the 08-26 partition does NOT release Run 2.** Two conditions are
controlling and **both** must hold: (1) the partition completes its terminal sampler count, EOD write,
freeze→verify→mirror and custody verification — **now satisfied**; and (2) the activation-proof
no-transition window opens only after the **runtime self-report repair is deployed and its three-source
identity is proven** — **not satisfied**.

⭐ **Why (2) cannot be satisfied by reading the box:** on 2026-08-25 the three-leg reconciliation
returned legs 1 and 2 (`.deploy_src_sha`, `DEPLOYED_BUILD_INFO.json`) but **leg 3 — the LOW-001
template — does not self-report a version at all.** It was *silent*, and silence is not confirmation.
Three-source identity therefore requires the repair to land first; it is not an observation waiting to
be made.

### D. SEC-001 — §J status correction *(bookkeeping only; the program is governed elsewhere)*

⚠ **§J below describes SEC-001 V3 as an ACTIVE full crawl with coverage freeze `5b26ffa2…` UNSPENT.
That state is superseded.** The corrected status, carried here so a later reader is not misled:

| Item | Corrected state |
|---|---|
| SEC-001 V3-RC | **STOP / REDESIGN — classification coverage gate FAILED** before economics were run |
| Coverage token `5b26ffa209a6a13a599a99fb28268b46be569cd2` | **SPENT / CONSUMED** — may never govern a successor run |
| Successor candidate | **SEC-001 V3.1** — governed separately; consult the SEC-001 track's governing records. ⛔ No document version is pinned here deliberately: a version-specific pointer goes stale the next time SEC-001 advances, which is the failure this correction exists to stop |
| Authority + execution state | **Governed in a separate session.** WP0A / WP0A-Q-COVER authority and execution state are controlled **there**. ⛔ **This ATP plan creates no SEC-001 authority** and does not reproduce, sequence or adjudicate its work packages. ⚠ Do not restate SEC-001 gate status from this document — read the SEC-001 track's own records |

⛔ **This plan does not reproduce, sequence, or adjudicate any V3.1 work package.** §J's V3 narrative is
retained below as historical evidence of what was true at the 2026-08-24 sync — editing it would
destroy the record of the transition. Read it only through this correction.

⭐ **The one finding worth carrying across the boundary**, because it is a general lesson about
sequencing research spend rather than a SEC-001 detail: **the largest defect class was not the binding
constraint.** Lineage gaps were 60.2% of unresolved cells, but repairing them perfectly still left the
terminal window short of the coverage threshold, because a different and smaller class was actually
binding. ⇒ Rank remediation work by *what forecloses the verdict*, not by *what produces the most error
cells*. This applies directly to §E below.

### E. ⭐⭐ VERDICT REACHABILITY — the GO floor now rests on K1 and K3

Two section-7 questions from the open task list were closed against the **governed registration**, and
the answers materially narrow the verdict path. This is the §4.11 verdict-reachability concern made
concrete, and it is the single most consequential item in this sync.

- **K5 `N_min` = 50 is frozen** — registration §8 sign-off (`K5 minimum fills N_min: [X] 50`), §157
  confirms signing freezes the floor, §8.4.3 re-affirms it unchanged. The residual word *proposed*
  inside the signed checkbox is drafting residue, not an open choice.
- **K5 discrimination signed 2026-08-20 at §8.4** — **K5 as frozen cannot return FAIL** (no-quote fills
  are excluded from *both* numerator and denominator, so the ratio approaches 100% by construction), and
  **§8.4.2 item 4: a non-discriminating K5 PASS does not count toward the GO floor.** The PASS is
  preserved on the record; only its contribution is qualified.

The ratified floor is **≥2 of K1–K6 both evaluable AND PASS**. What can actually earn it:

| Path | Current character | What can still change it |
|---|---|---|
| **K1** | **P0 load-bearing engineering** | Build the calculator/evaluator |
| **K3** | **P0 load-bearing engineering** | Build the calculator/evaluator |
| **K2 / G10** | **Owner-controlled expiring option** | Decide **and** implement Phase B early enough for 20 consecutive sessions |
| **K4 / Stage 0** | **Data-sufficiency-constrained expiring option** | Obtain a conforming dataset **and** reach a Stage-0 execution in-window |
| **K5** | **Reporting only** — cannot contribute | Nothing; foreclosed by signed §8.4 |
| **K6** | **Event-contingent option** | A qualifying occurrence must naturally enter the corpus |

⚖ **Owner ruling 2026-08-26 — K2 and K4 are NOT equivalent levers.** K2/G10 is opened by *decision*;
K4 is bound by a *data-sufficiency contract*. **The ≥250 trustworthy PIT event-day requirement may not
be waived to rescue MDQ evaluability.** The owner may prioritize work that could make Stage 0 feasible;
"open K4" is not an available instruction.

⭐ **Precise statement of the consequence** (owner-worded; the earlier absolute phrasing overstated it):

> Under the current state, if either K1 or K3 fails or is NOT EVALUABLE, GO becomes unreachable **unless
> at least one presently non-contributing path first becomes legitimately contributing in-window** — K2
> through a timely G10/Phase-B run, K4 through a conforming Stage-0 execution, or K6 through a naturally
> captured qualifying occurrence. **No such path may be created retroactively after its evidentiary
> window closes.**

#### E.1 The K2 calendar — a hard, computed deadline

K2 requires **20 consecutive sessions**. The frozen review date is Sunday **2026-10-18**, so the last
usable session is Friday **2026-10-16**. There are **exactly 20 NYSE sessions from Monday 2026-09-21
through Friday 2026-10-16**, with no NYSE holiday inside the interval (Labor Day 09-07 falls before it;
NYSE trades Columbus Day 10-12). Verified by computation, not assumed.

⇒ **2026-09-21 is the absolute latest K2 measurement-start date.** It carries **zero** implementation or
qualification slack, so it is **not** the decision date. A distinct **G10 owner-decision deadline
belongs in early-to-mid September**, separate from the hard 09-21 measurement deadline.

#### E.2 ⚠ Open question that must be ruled BEFORE G10 is decided

Any 20-session window ending 10-16 necessarily overlaps the period holdout: **9 of the 20 sessions fall
inside 2026-10-06 … 10-17.** The overlap is unavoidable, because the holdout is the tail of the review
window.

Reading the registration, this appears to be a **non-conflict**: Ruling 4 defines the predicate as
`exploratory_access_allowed`, and the §8.1 quarantine language is scoped to **discovery / exploration**.
Verdict computation of a frozen K criterion is not exploratory access.

⛔ **But the distinction is load-bearing and easy to invert.** If K2 measurement were treated as an
exploratory read, only 11 sessions would remain usable, **K2 would be structurally impossible**, the G10
lever would already be dead, and the 09-21 deadline would be moot. This deserves one explicit sentence
of ruling now, rather than being discovered in October by whoever runs the calculator.

#### E.3 Planning priority that follows

**P0: build the K1/K3 machinery.** In parallel: force the G10 owner decision onto the calendar well
before 2026-09-21, and measure whether K4's data gap has any realistic path to closure. Everything else
sits behind those, because those are the items capable of foreclosing the October verdict before October
arrives.

⚠ **The calculators do not exist.** Verified against `origin/main@379eca6`:
`app/research/capture/admissibility.py` is present — it is what adjudicated D0 — but **no K-value
calculator module exists anywhere under `apps/backend/app/`**. K1 and K3 are therefore not merely the
largest remaining item but the **load-bearing** one, and they should be built first within it.

⚠ Also confirmed absent from `origin/main`: the box wrapper `/opt/workbench/mdq/mdq_run.sh` and the
three systemd units (`mdq-sample`, `mdq-eod`, `mdq-freeze`). These enforce the universe hash pin, the
free-space floor and the slot grid, and **none of them is in Git.** Owner direction stands: fold them
into the next ops-governance change, not a standalone PR.

### F. Open task list published for owner review *(new)*

`docs/design/ATP/ATP_MDQ001_OpenTaskList_2026-08-26.md` — a **task list only**: subordinate and
non-governing. Not a plan, not a governing record, and conveying no authority. It enumerates what
remains in the ATP / MDQ-001 scope so the direction can be confirmed before work resumes, and it
explicitly excludes SEC-001 V3.1.

### G. ⭐ Custody trap hit and avoided during this sync — record it, do not repeat it

The working copy of this plan in the `research/mr002-validation2-lineage` checkout was **untracked and
stale**: 293,399 B against the governed `origin/main` blob's **297,683 B / sha256
`7b2f1fd82e558d2f86eebd6f453ba35eb3b53dc1b7942afb1010940b16ce6185`** — it was missing the entire
2026-08-25 state sync. Sections H, I and J were first read from that stale copy.

⇒ This sync was cut from a **fresh `origin/main` worktree**, and the file was byte-verified against the
governed blob before editing. ⛔ **Never edit, hash, or quote this plan from the MR-002 research
checkout.** The same branch also carries pre-D0 `mdq_collector.py` and a pre-review
`mdq_preflight_readiness.sh` as untracked shadows of governed files.

---

---

## State sync — 2026-08-25 *(applied in place per the ONE CURRENT PLAN rule; no new version)*

**Headline: governed MDQ capture is RECOVERED. 2026-08-25 produced a complete governed partition on
both feeds, and the producer identity is continuous across the recovery boundary.** Nothing in this
sync changes research authority, K1–K6, D0, the review window, the holdouts, the DISC-001 gates, the
DISC-MDQ hold, or the value-extraction priority order.

### A. 2026-08-25 — RECOVERY CAPTURE / GOVERNED PARTITION COMPLETE *(record MERGED)*

Record: `docs/design/MDQ-001_Capture_Recovery_2026-08-25.md`, **MERGED `5a48ee88` (#684)**, post-squash
byte custody verified on `main` — 12,669 B, LF-only, sha256
`e4c7e5d967dd3c4e1433f178166c585af5e619dc5e1244c1f72045e5b0b7f3d7`.

⚖ Owner-ruled a **separate governed record, not a Program-Start §6 Amendment B**: 2026-08-25 is
operational execution evidence and alters none of the §6 authorities. ⛔ It is **not** a replacement,
substitute, or repair for 2026-08-24.

| Stage | Result |
|---|---|
| Three-proof readiness chain | post-recreate preflight **READY 5/5** (`2026-08-24T23:50:03Z`) · near-slot preflight **READY 5/5** (`2026-08-25T13:15:00Z`) · **natural timer start**, `TriggeredBy=mdq-sample.timer` |
| `mdq-sample.service` | `Result=success`, **395/395 scheduled slots**, 50 symbols × 2 feeds, 09:25:02→15:59:00 ET |
| `mdq-eod.service` | `Result=success` — 16,338 IEX / 26,984 SIP 1-min bar rows |
| `mdq-freeze.service` | `Result=success` — **freeze → verify → mirror**, 3 files per feed |
| S3 custody | six objects verified: manifest sha256 recomputed host-side, then host MD5 == S3 ETag |
| MDQ failure alerts | **0** for the day |

### B. ⭐⭐ THE LOAD-BEARING FINDING — no credential-identity seam in the corpus

The 08-23 runtime-environment loss was repaired by **restoring the existing registered acquisition
credential, not by rotating it**: no new Alpaca key pair, no `identity.py` re-pin, no account reset.

⇒ Both 2026-08-25 manifests stamp **`credential_fingerprint b56421a28128`** and
**`account_number PA3BGKRLH2AP`**, identical in identity semantics to 08-19/20/21. A rotation would
have failed `verify_identity()` closed and forced a governed re-pin of `identity.py` — one of the five
approved collector blobs — **splitting the corpus mid-stream**. Any analysis spanning 08-19 → 08-25
reads a single continuous producer identity.

### C. 2026-08-24 disposition — UNCHANGED

**Permanent NON-EVENT. Zero evidence. No backfill**, no denominator or evidence-window change, no
retroactive evidence. Nothing in the 08-25 recovery reopens, softens, or repairs it.

### D. Corpus state

**4 governed trading days: 2026-08-19 (D0), 08-20, 08-21, 08-25** — both feeds, every partition frozen,
verified and S3-mirrored. 2026-08-18 and 2026-08-24 remain non-events contributing zero evidence.

### E. §H recovery sequence — DISCHARGED

The 2026-08-24 §H sequence executed in order and is closed: credential restoration + backend recreate
→ post-recreate preflight PASS → (no deployment of the preflight) → near-slot preflight PASS → natural
timer start. The sampler was **not** hand-started at any point.

### F. ⚠ Operational note — `activating` is not a hang, and not evidence either

`mdq-sample.service` is a `oneshot` unit that runs **until close** (~6 h 34 m; `TimeoutStartSec=8h`), so
`ActiveState=activating` is the **expected** state for most of a healthy session. Judge liveness by
**governed byte growth, failure alerts, explicit failure signatures, and the terminal timestamp** —
never by `ActiveState` alone. The converse holds equally: `activating` is not evidence of capture, and
`mdq-freeze.service` exiting 0 means nothing on its own (08-24: `no partitions … nothing to freeze`).

This is an **operational interpretation rule**. It weakens no failure gate and changes no admissibility
criterion.

### G. DISC-MDQ population hold — UNCHANGED

The broad DISC-MDQ feature library remains **HELD** on the three-day census recorded at §F of the
2026-08-24 sync. A fourth governed capture day adds corpus depth, not population breadth, and does not
authorize the narrow MOM-CORE × MDQ observation.

---

## State sync — 2026-08-24 *(applied in place per the ONE CURRENT PLAN rule; no new version)*

**Headline: the 2026-08-24 governed capture did not happen, and it is closed as a NON-EVENT.** Nothing
in this sync changes research authority, K1–K6, D0, the review window, the holdouts, the DISC-001 gates,
or the value-extraction priority order.

### A. 2026-08-24 — CAPTURE NON-EVENT / NO GOVERNED PARTITION *(owner-ruled; record MERGED)*

`mdq-sample.service` failed three seconds after the 09:25 ET start:
`acquisition creds absent (ALPACA_PAPER_6_API_KEY / _SECRET)`.

**Root cause: runtime acquisition-environment loss after redeploy.** The 2026-08-23 deploy rewrote
`/opt/workbench/.env` (mtime 11:54:36 EDT — six minutes *before* the `.deploy_src_sha` stamp at
12:00:51) and dropped the registered account-7 credentials; the backend container was recreated
2026-08-23T20:17:44Z, and 08-24 was the first trading day after. Explicitly **NOT** disk exhaustion,
**NOT** collector-code drift, **NOT** universe-pin failure, **NOT** a data-quality failure.

| Completion fact | Observed 16:47 ET |
|---|---|
| `mdq-eod.service` 16:30 | **FAILED**, `ExecMainStatus=1`, byte-for-byte the same credential line. Second alert **preserved, not suppressed** |
| `mdq-freeze.service` 16:45 | **Exit 0** via `no partitions for 2026-08-24; nothing to freeze` |
| Both 08-24 partition dirs | **Absent** after every unit ran |

⚠⚠ **That freeze exit 0 means NO PARTITION / NO EVIDENCE — never read it as a successful capture.**
A later reader scanning unit exit codes will see `success` for `mdq-freeze.service` on this date.

**Disposition (owner):** lost day, same evidence class as 2026-08-18. **Zero evidence contribution;
no K-value may use the date.** No salvage, no backfill, no reconstruction, no credential substitution,
and **no 08-24 directory was created — including to document the failure.** A restart would have missed
the frozen 0.98 completeness floor (~0.96) and breached the 10-minute contiguous-gap limit at the open.
Record: `docs/design/MDQ-001_Capture_NonEvent_2026-08-24.md`, **MERGED `311863cb` (#679)**, byte custody
verified on `main` (`f6436c35…e95f3`, 11,832 B).

**Corpus is unchanged at three governed days per feed: 2026-08-19, 08-20, 08-21.**

### B. ⭐⭐ THE STRUCTURAL LESSON — code-identity conformance ≠ operational readiness

The 08-23 deploy left **all five approved collector blobs byte-identical and conformant** while
destroying the runtime environment they depend on. A green blob check says nothing about whether the
registered acquisition environment still exists.

🪲 **The checker failed the same way the system did.** The morning preflight (08:34 ET, 50 minutes
before the slot) ran the **free-space** leg only, passed it with a 16 GiB margin, and reported clean.
It was clean — for the one leg checked. §3.4 already warns that these gates mask each other and that the
literal failure line must be read rather than inferred; the preflight nonetheless was scoped to the
*remembered* failure mode. One line reading the container environment would have caught this in time
to repair before 09:25.

⇒ **New operational rule, binding:** *a deployment that recreates the collector's container must prove
the COMPLETE REGISTERED ACQUISITION ENVIRONMENT before the next scheduled governed slot.* Free space is
one gate of five, not the readiness test.

### C. Corrective control — 5-gate acquisition-readiness preflight *(MERGED)*

**`apps/backend/scripts/mdq_preflight_readiness.sh` + 16 regression tests — MERGED `363daa08` (#673).**
Read-only; reproduces the collector's actual chain in order:

```text
universe pin → acquisition credential presence → account-identity latch → free space → single-instance
```

Behaviour pinned by test, not convention: any required gate failing ⇒ **NOT READY / exit 1**; gate 3
becomes **NOT EVALUABLE** (never "pass", never silently skipped) when gate 2 blocks identity resolution;
secrets never printed (credentials as `SET`/`ABSENT` + length; fingerprint only in the 12-hex form the
collector already treats as non-secret); **the governed universe pin is not overridable by environment**
— a pin an env var can relax is not a control; and the failure output states that substituting the
unnumbered `ALPACA_PAPER_*` pair is a governance change, not a repair.

⭐ **It requires no deployment.** `AWS-RunShellScript` takes the script **as the command body**, so it
runs transiently against the box with **no file placement, no `docker cp`, no image rebuild, no
container recreate.** Merging it is a source-custody act, not a deployment act. ⛔ Do not redeploy
merely to "install" it.

Validated against the live box 2026-08-24: gate 1 PASS · gate 2 **FAIL** · gate 3 NOT EVALUABLE ·
gates 4–5 PASS ⇒ NOT READY, exit 1 — correctly identifying the gate that actually failed that morning.
⭐ Exit 1 surfaces as SSM `STATUS=Failed`; that is the fail-closed signal, not a broken script.

### D. Program-Start Record §6 — Amendment A *(MERGED)*

**`docs/design/MDQ-001_ProgramStart_Record_v0_2_Amendment_A_2026-08-24.md` — MERGED `e488440` (#672)**,
discharging the post-start finding the owner ruled on 2026-08-20 should be entered and which had
remained unwritten. Append-only, **limited to §6**; the signed v0.2 body is untouched, §7 "Effective
state" is neither restated nor summarized, later signed acts are cited **by identity only**, the base
document identity is pinned, and it explicitly does **not** reopen K1–K6, D0, the holdouts, the PX
rulings, or the approved producer identity.

| Finding | Substance |
|---|---|
| 5 | Deployed producer commit has moved **three times** since D0 — now `0344337` (#666), deployed 2026-08-23 12:00:51 EDT. All five approved collector blobs byte-identical at `86d8cbd`, `9e5cf65`, `50efc2f`, `0344337`, `4c4a2b1` **and inside the running container**. Commit-label drift, verdict-neutral. **Recorded, not re-latched.** |
| 6 | `.deploy_src_sha` and the backend image were written **4h16m apart** on 08-23 ⇒ the label alone does not establish what is running. Provenance weakness, not a corpus defect; the blob-hash component of the approved tuple is the mitigation. |
| 7 | The box trails `origin/main`; none of the intervening commits touches the approved collector files. |

Also confirmed: **the D0 partition is byte-intact** — all six 2026-08-19 files re-hash exactly to
Program-Start Record §5.5, five days and two redeploys later.

### E. ⚖ Authority order for MDQ identity questions *(owner-set 2026-08-24)*

1. **running-container governed blob / hash** (`docker exec … sha256sum`, CRLF-normalised)
2. **approved Git blob / collector-identity artifact**
3. **current clean-`main` source**

⛔ **Never an untracked copy on an unrelated research branch.** Concretely: on the MR-002 branch,
`app/research/capture/identity.py` and `scripts/mdq_collector.py` are untracked **pre-D0** copies —
the former pins the *old* fingerprint `5b6f39e5198d`, whereas the governed blob pins **`b56421a28128`**,
which is what the manifests carry. Reading the worktree copy nearly produced a false "identity drift"
diagnosis; this ordering is why 08-24 stayed correctly classified as a *runtime-environment* failure.

### F. DISC-MDQ population census repeated — **HOLD STANDS**

Third independent snapshot day (`as_of` 2026-08-20) agrees with 08-14 and 08-19:

| Family | n | ∩ MDQ non-holdout |
|---|---|---|
| GAP | 10 | **0 on 3/3 days** — structurally disjoint, not a one-off |
| MOM-CORE | 15 | **the same 5 names every day**: AMD, INTC, MRVL, MU, SNDK |
| MOM-NEAR / OVERSOLD | **0** | the families emit **zero candidates at all** |

⭐ MOM-NEAR / OVERSOLD are emptier than "not evaluable" implied: there is **no population**, not merely
no intersection. ⭐⭐ **NBIS — a holdout symbol — appeared in MOM-CORE on 08-19 and was correctly
excluded.** That is the first observed instance of the quarantine having something real to bite on, and
it is the citation to use as evidence the embargo works — **not** `denials=0`, which only shows it was
armed. ⚠ The screen is fixed-size (v0.3.0: 25 candidates, GAP=10 / MOM-CORE=15), so the population is
capped by **screen design**, not market conditions; widening is a governed change, never a convenience.

⇒ **The broad DISC-MDQ feature library remains HELD.** Three snapshot days strengthen the hold rather
than weaken it. Not yet sufficient to authorize even the narrow MOM-CORE × MDQ observation; continue
passive accrual and repeat the census later this week.

### G. Storage — obligation discharged, but the trend is the item

The mandatory pre-09:25 free-space guard (lead item of the 08-22 sync) was run **08:34:39 EDT**,
reproducing the deployed wrapper's own arithmetic: `size_gb=58 avail_gb=27 floor=11` ⇒ **PASS**, margin
**16 GiB**; raw `avail = 28,766,879,744 B`; effective fail threshold `avail_bytes <= 10,737,418,240`.

⚠ **Available space fell 35 G → 27 G in two days** and Docker build cache grew **9.6 → 16.72 GB**
(15.26 GB reclaimable). Roughly two more rebuild cycles at that rate would put the guard back in play,
and the guard is **silent** when it trips. A bounded, build-cache-only cleanup (`docker builder prune -f`,
with before/after evidence and rollback images preserved) is owner-authorized **after** a successful
freeze — not before a capture, and never as part of another operation.

### H. Next MDQ operational act — the recovery sequence *(sequenced, not optional)*

```text
credential restoration + backend recreate   (behind the C5b / container-custody boundary)
  → transient SSM preflight PASS            (immediate post-recreate proof)
  → (no deployment of the preflight itself)
  → near-09:25 transient SSM preflight PASS (near-slot proof)
  → natural sampler start from the timer
```

⛔ Do not hand-start the sampler. ⛔ Two proofs, not one: **a deployment/recreate is no longer
operationally complete for MDQ merely because code hashes and health checks pass.**
⚠ The backend recreate is entangled with an unrelated account-5 containment artifact staged inside the
same mutable container (`/app/scripts` is not a bind mount), so restoration waits on that boundary
being safe.

### I. ⚖ Canonical-plan custody — OWNER RULING 2026-08-24: COMMIT THE SOLE CURRENT v0.14 PLAN TO GIT

**The finding.** The 2026-08-23 ruling moved this plan to `docs/design/ATP/` **because `docs/design/**`
is tracked and reviewable in a PR diff**, and deleted the gitignored duplicate. Verified 2026-08-24:
`/docs/**` is ignored at `.gitignore:100`, but `!/docs/design/**` at line 112 is the **last matching
rule**, so this file is **not ignored** — yet it was **untracked locally and absent from `origin/main`.**
Moving it to a tracked-class path made Git custody **possible**, not **actual**. The plan's older
reasoning that it "is gitignored and cannot hold a gate-closing owner ruling" is **obsolete** at this path.

⚖⚖ **OWNER RULING 2026-08-24 — COMMIT THE SOLE CURRENT v0.14 PLAN TO GIT.** This **closes the
canonical-plan custody gap; it does not create a new plan version.** v0.14 remains the sole current
implementation-plan version under the ONE CURRENT PLAN rule, and the 2026-08-24 state sync stays applied
in place. **No v0.15.**

**Binding scope of the custody act:** a docs-only / Tier-0 PR containing **exactly one file** —
`docs/design/ATP/AlgoTraderPlus_v1_4_1_ImplementationPlan_v0_14.md` — cut from a **fresh `origin/main`
worktree**, staged by explicit path (never `git add -A`), with the integrity checks re-run (LF-only, one
H1, no placeholders, prior state-sync markers preserved). ⛔ Do not merge if an unexpected second file
appears.

**Closure criterion:** **merge to `main` + byte-identity verification of the file read back from `main`.**
Until both hold, this item is open. *(Recorded prospectively, before the merge, so the criterion cannot
be adjusted to fit whatever happens.)*

⛔ **The 2026-08-23 expectation is NOT rewritten.** Its superseded annotation above stands **exactly** as
historical evidence of what was intended and what was actually true — the distinction between the two is
the substance of this finding, and editing the earlier text would destroy it.

⭐ **The ABT citation gap does not block custody and is not papered over.** §J keeps its wording: the
ABT controller `50541e29…` and the **37/37** figure are **owner-provided, citation pending**, distinct
from the figures confirmed against the SEC-001 governing records. When the ABT canary record enters
durable custody, add the citation **in place** to v0.14 if v0.14 is still current — that does not itself
justify a v0.15.

---

---

### J. SEC-001 V3 classification program — state sync 2026-08-24

The plan previously described this work as a prospective ~800-name acquisition. It has progressed
through a sealed 1,167-identity population, 100% CIK resolution, several preserved canary defects, a
passing live v1.4 canary, and an **active governed full crawl**. Detailed evidence stays in the
SEC-001 governing records under `docs/design/SEC-001/`; this plan carries **current state, authority
boundaries, and the exact next sequence** only.

| Milestone | State |
|---|---|
| Governed deep-history store | **SEALED** (`SEC001_V3_GovernedStore_PreIngestionFreeze_v1_0.md`) |
| Liquidity definition | **CORRECTED** — unadjusted close × raw volume (`SEC001_V3_UniverseLiquidity_DefectRuling_v1_0.md`) |
| Governed rebalance calendar | Monday **10:24 ET**, **1,247 slots** |
| PIT-200 | **249,400** slot-name positions |
| Frozen union | **1,167 permanent identities** |
| CIK resolution | **1,167 / 1,167** — 0 unresolved, 0 conflicts, 0 ambiguities; from the original governed Sharadar TICKERS acquisition, **no new vendor acquisition** |
| Classification path | **Effective-dated Phase-2B only.** ⛔ The Phase-2A default path is **prohibited** |
| ABT v1.4 canary | **PASS 37/37** after Defect E remediation |
| Transport discipline | Ranged requests force `Accept-Encoding: identity`; **exact parser-facing decision bytes retained**; no 1 MiB / 8-request ceiling hits in the repaired canary; rate proof from **actual monotonic send timestamps** |
| Full crawl | **ACTIVE**, completion pending |
| Classification coverage | ⛔ **NOT YET EVALUATED** — freeze `5b26ffa2…` **UNSPENT** |
| Economics | ⛔ **NOT YET EVALUATED** |

⭐ **Verification note, stated rather than glossed:** the population figures (1,247 / 1,167 / 249,400),
the coverage-freeze identity `5b26ffa209a6a13a599a99fb28268b46be569cd2`, and the Segment-2/3 controller
hashes were **confirmed against the records in `docs/design/SEC-001/`**. The ABT canary controller
`50541e29…` and the **37/37** figure are recorded **as owner-provided**; they do not appear in those
files and are pending citation to the ABT canary record.

#### J.1 Acquisition defects A–E — concise record, not the lab notebook

Multiple **pre-coverage** acquisition defects were found by canary/diagnostic controls and preserved as
**superseded evidence**. The one that matters structurally:

⭐⭐ **Defect E** — ranged **gzip fragments were reaching the frozen parser as encoded bytes**, which
would have manufactured **plausible false historical missingness**. Repaired in the **V3 transport
layer**, with the **frozen MR-002 SIC parser left unmodified** — the correct side of the boundary.
⭐ Two earlier hypotheses were **REFUTED by the retained source bytes**: that SIC lay beyond the first
4 KiB, and that historical full submissions lacked SEC-header SIC. Retaining exact decision bytes is
what made refutation possible rather than a judgement call.

Governing records: `SEC001_V3_CanaryDefect_AcquisitionRemediation_v1_0.md` ·
`SEC001_V3_CanaryDefect_E_EncodedRangeRepresentation_v1_0.md` ·
`SEC001_V3_forensic_client_258c570d_vs_6c1d7006.diff.txt`.

#### J.2 Execution provenance — four segments *(affects admissibility)*

| Segment | Identities | Controller | Authority |
|---|---|---|---|
| 0 | #1 (ABT) | `canary_run_v3.py` `50541e29…` | Manifest v1.4 |
| 1 | #2–#5 | `crawl_full.py` `9571c9eb…` | **Unbound — recorded nonconformance** |
| 2 | #6–#8 | `crawl_full.py` `9571c9eb…` | Addendum v1.4.1 |
| 3 | #9–#1167 | `crawl_full.py` `894e4744…` | **Addendum v1.4.2 — current controller authority** |

Full controller identities: `9571c9eb5331381fa659cd800f6b9117e10daee67453bfe99c85349209aa2a5e` (v1.4.1,
superseded) → `894e474472111c129ad2eec8471f4d614a15956ee9521850e610d627925d21bc` (v1.4.2, active).

⭐ **Segment 1 is RETAINED, not discarded.** The unbound runner altered **no source selection, no bytes,
no classification, no population, and no order** — it only enforced stopping conditions. The
nonconformance is recorded so the retention is a documented judgement rather than a silent one.

#### J.3 ⛔ The next-step boundary — FROZEN

**Completing the crawl does NOT authorize computing coverage.** The sequence is:

```text
complete 1,167 unique terminals in exact frozen order
  → acquisition-only crawl-integrity report
  → hash + remote custody + fresh-fetch verification
  → OWNER CHECKPOINT  (stop here)
  → separate owner authorization to spend 5b26ffa2…
  → classification-coverage adjudication
  → if coverage PASS: corrected V2 reference + V3-RC economics
  → GO / STOP
  → only on GO: build and deploy a new V3 runtime
```

⛔ Successful acquisition is **not** implicit authorization for the next stage. Spending the coverage
freeze is a **separate owner act**. Economics are downstream of a coverage PASS, never concurrent
with it.

#### J.4 Account 5 / strategy 7 — SEC-001 runtime disposition

**Account 5 is flat and RESERVED** while V3 research proceeds. Legacy **strategy 7 / `sector-rotation`
v1.0.0 is permanently retired and nonconforming — it must never be reactivated** (it never ran frozen
SEC-001; every rebalance it made was nonconforming, and containment is recorded in
`docs/incidents/2026-08-22-sec001-production-conformance-failure.md`).

- If V3 receives a research **GO** and passes its runtime gates ⇒ create a **new** SEC-001 V3 strategy
  record/version for Account 5. Not a revival of strategy 7, and not a version bump on it.
- If V3 **STOPs** ⇒ Account 5 is free for reassignment.

---

---

## State sync — 2026-08-23 *(applied in place per the ONE CURRENT PLAN rule; no new version)*

Two addenda applied in place today. Neither changes research authority, K1–K6, the DISC-001 gates, the
value-extraction priority order, or any frozen product gate.

**v0.14 Review Addendum (2026-08-22), items 1–3 — APPLIED, and all three are now DISCHARGED or DELIVERED:**

| Item | Where it landed | State |
|---|---|---|
| 1 — escalate #511 | GAPPER open-controls row + execution-order block | **SCHEDULED.** Local validation green 2026-08-23 (clean merge of `main`; `ruff check .`; 28 focused + 173 `altdata`/`jobs` + 633 `services` tests; 7 invariant scripts). **Held, not pushed** — "update once, immediately before merge" puts the push with the merge decision. ⚠ Addendum said "ahead of/alongside #662"; **#662 merged 2026-08-22T20:35Z**, so #511 now stands alone. |
| 2 — quarantine review | open-controls row → `docs/design/Gapper/GAPPER_PremarketGateProvenance_Quarantine_Review_v1.0.md` | **DELIVERED.** 🚨 It found the script had **already run** in production; see the row for the measured residue. **Awaiting owner disposition**; recommendation now recorded (S5). |
| 3 — dataset scoping | GAPPER re-entry block → `docs/design/Gapper/GAPPER_Stage0_DatasetOptions_v1.0.md` | **DELIVERED.** `source_vendor` remains `UNSET_OWNER_DECISION`; no vendor named, nothing ranked. |

**State Sync Addendum (2026-08-23), items S1–S5 — APPLIED:**

| Item | Where it landed |
|---|---|
| **S1** LOW-001 pointer v0.4 → **v0.5** + the three v0.5 additions (scaffold custody · G4b LIVE/PAPER parity · HON cost-basis defect as a **platform** defect) | header line 11 · LOW-001 current-state block |
| **S2** boundary brought to **bidirectional** form (Watchlist v0.11) | §1.4 · header line 11 |
| **S3** SEC-001 V3 Disposition Ruling v1.0 — three incoming shared-infrastructure changes | new state-sync subsection below · open-controls table (2nd quarantine row) |
| **S4** DISC-001 **sector-label provenance caveat** — the substantive item | §4.10 |
| **S5** recommendation on the provenance residue: **annotate + schema `/v2` at the writer** | open-controls quarantine row *(recommendation, not a ruling)* |

⚖⚖ **OWNER RULING 2026-08-23 — CANONICAL PLAN CUSTODY.** Recorded verbatim:

> **`docs/design/ATP/AlgoTraderPlus_v1_4_1_ImplementationPlan_v0_14.md` is the sole current v0.14 plan.**
> The duplicate at `docs/Strategies/AlgoTraderPlus_v1_4_1_ImplementationPlan_v0_14.md` is deleted. Before
> deleting, sweep the repository for that exact path and update any live reference. Do not leave another
> plan copy or a synchronized mirror.

**Why**, in the owner's terms: the plan itself recorded that `docs/Strategies/` is gitignored, unreviewable
in a PR diff, and unguarded by CI, while `docs/design/**` is tracked — and the plan separately requires
**ONE CURRENT PLAN ONLY**. A duplicate in a weaker custody class is the hazard, not the tie-breaker.

**Executed 2026-08-23:** duplicate deleted; the ⚠ two-copy condition described here is **closed**. The
reference sweep found and dispositioned three classes of pointer:

| Reference | Disposition |
|---|---|
| `docs/design/Opportunity Page/…Watchlist_Design_v0_11.md` "Parent plan" | ✅ **Repointed** to the canonical path — a live pointer in the current Watchlist design |
| `apps/backend/app/research/capture/admissibility.py:79` `PLAN_DOC = "docs/Strategies/…v0_8.md"` | ⛔ **Left unchanged, deliberately.** It cites **v0_8**, not v0_14, and only as provenance for a §4.9 proposal ("proposed in {PLAN_DOC} §4.9; ACCEPTED as proposed, signed 2026-08-17"). Repointing a *historical citation* at a *current* document would assert that today's text is what was signed. Same principle as not rewriting a changelog to match present state. |
| `manifests/s3/docs/strategies.inventory.json` (v0_8, v0_9) · Watchlist v0.4–v0.10 under `docs/Strategies/` | ⛔ **Left unchanged.** Historical S3 pins and superseded designs; their paths were correct when written. |

⚠ **This does not settle where a future v1.0 series belongs.** The older plan-location item notes the
hybrid-docs rule contemplates `docs/implementation/` for governing implementation plans. This ruling
settles **current v0.14 custody only**: `docs/design/ATP/` beats a gitignored duplicate.

⭐ **Consequence to carry:** the canonical plan is now **tracked**, so every future state sync is a
reviewable diff and a Tier-0 CI cycle — cheap, but no longer invisible. Two statements elsewhere in this
document that asserted the opposite have been corrected (§6 item 6 custody note; the G4 §9 note).

> ⚠ **SUPERSEDED 2026-08-24 — this "now tracked" clause was an expectation, not a measured fact.**
> Measured: the file is **not ignored** (`!/docs/design/**`, `.gitignore:112`, is the last matching
> rule) but is **untracked locally and absent from `origin/main`.** Moving it to a tracked-class path
> made custody *possible*, not *actual*. The authoritative current statement is the **2026-08-24 sync
> §I**; the paragraph above is retained as the record of what was intended on 08-23.

---

## State sync — 2026-08-22 late *(v0.14; LOW-001 Dynamic-PIT cross-program boundary)*

This revision adds one **parallel platform/conformance workstream** without changing ATP/MDQ research authority:
**LOW-001 Dynamic PIT**. LOW-001 remains `B (Diversifier)` and its economics remain frozen. The workstream
exists to make the frozen PIT top-200 / lowest-volatility-quintile construction executable when PIT membership
changes, while preserving static registration behavior for every strategy that is not explicitly authorized for
dynamic PIT.

**Current LOW-001 state used by this plan:**

- PR **#661** (`low-volatility` v1.0.1 conformance repair) is merged to `main` as **`7bd35f1c`**.
- Dynamic-PIT work is isolated on `lowpit/scaffold`, based from that merged SHA.
- Governing design: `TradingWorkbench_LOW001_Dynamic_PIT_Execution_Design_Implementation_v0.5.md`
  (**v0.5 supersedes v0.4** for current implementation state; state sync 2026-08-23).
- **v0.5 adds three things this plan depends on:**
  1. **`lowpit/scaffold` custody push required now** — GITHUB-OPS-001 posture, carrying the GAPPER-harness
     lesson forward (five days of validated work on one laptop with no remote copy is the failure mode,
     not the exception).
  2. **G4b closes only on LIVE/PAPER liquidation-path parity** — shared fixture, identical ownership and
     ambiguity semantics on both paths. A PAPER-only proof does not close it.
  3. 🚨 **The HON cost-basis recomputer defect (overwrite-with-last-fill) is a PLATFORM position-accounting
     defect, not a LOW-001 defect.** Its platform-wide disposition is tracked **here** (OPS); the
     LOW-001-path *consumer enumeration* gates Account-6 activation **only if a consumer is found**.
     ⭐ Note the asymmetry deliberately: the defect is platform-wide, the activation gate is conditional —
     do not let "no LOW-001 consumer" be read as "no platform defect."

- Pre-Dynamic-PIT safety work is in progress: test fidelity, strategy-ownership provenance, held-position
  READ visibility, normal rebalance exit, and LIVE activation/deactivation ownership logic are implemented;
  concrete permanent-identity/provider wiring and an explicit PAPER liquidation path remain prerequisites
  before the safety release is deployable.
- **Dynamic BUY remains prohibited** until the safety baseline is merged/deployed and the PAPER exit gate is
  proven. No LOW-001 Dynamic-PIT work is a DISC/MDQ feature experiment and none consumes K1–K6 authority.

### Cross-program ruling

LOW-001 Dynamic PIT may **reuse platform infrastructure** that is also useful to ATP/DISC work:

- `PERMATICKER_EFFECTIVE_INTERVAL_V1` permanent-security identity / ticker lineage;
- exchange-session calendar semantics (`MarketSession` / America/New_York);
- Sharadar PIT/as-of conventions and governed universe metadata;
- common evidence fields such as `as_of`, source/version identity, adjustment basis, hashes, and durable
  operator diagnostics.

It may **not** consume Opportunity / `DISC-001-WATCHLIST` candidates, family labels, D1/D5/D10/D20/CURRENT
checkpoints, “Why it left” explanations, MDQ enrichment, SIP/news features, or Opportunity historical returns
as LOW-001 universe, ranking, weighting, BUY/SELL, or sizing inputs. Any such proposal is a **new research
mechanism** (for example LOW-002 or a separate DISC-derived strategy) and requires its own prospective
registration/version decision.

This boundary is deliberate: infrastructure can converge; **economic signals cannot cross programs merely
because they share infrastructure**.

---

## State sync — 2026-08-22 *(applied in place per the ONE CURRENT PLAN rule; no new version)*

🛑 **LEAD ITEM — MANDATORY before Monday 2026-08-24 09:25 ET.** Run the **deployed** free-space
guard against the **live** host using the wrapper's own byte calculation and its measured threshold
(`floor = max(10 GiB, 20% of capacity)`, evaluated exactly as the wrapper evaluates it).
⛔ **Do NOT inherit Friday/Saturday capacity figures** — not the margin, not the build-cache size, not a
remembered `df`. The point of the check is to re-measure the exact state immediately *before* the
collector becomes dependent on it. Docker and the MDQ capture root remain the **same mount (`/`)**; the
60 GB resize mitigates the coupling but does not remove it, so post-redeploy and pre-capture checks both
remain mandatory.

**Repository baseline: `main` = `a8f1be2`.** Completed chain, 2026-08-21 → 08-22:

```text
#654  50efc2f  discovery ledger, binding at the read
#656  e794fc7  discovery-ledger PRODUCTION ACCEPTANCE - PASS on ec2-paper
#657  dcc2c97  CEE authorization - recorded PROSPECTIVELY, before the first read
#659  07f745b  CEE Observation Record 001 - NOT EVALUABLE (n=17)
#660  a8f1be2  deploy-archive EOL determinism - structural, CI-enforced
```

### Discovery ledger — ✅ CLOSED and OPERATIONAL *(was: prerequisite / pending)*

The §4.10.7 gate is not merely written; it is **discharged**. The requirement stated elsewhere in this
plan — that the ledger be OPERATIONAL before CEE opens its first governed partition — remains correct
and is now **satisfied**, not outstanding.

- ledger code in Git (`50efc2f`, #654); all twelve acceptance items implemented and tested;
- **operational acceptance PASS on `ec2-paper`**, 2026-08-21T21:32:05Z, recorded at `e794fc7` (#656);
- production path **`/opt/workbench/data/mdq_discovery/ledger.jsonl`** — owner-pinned;
- **genesis established** (`DISC-MDQ-001#1:a1aecc44b28611e8`) as a production-control initialization
  event, with 0 conditions examined and 0 partition reads at that point;
- **fail-closed positive/negative matrix proven on the box**: wrong holdout hash, missing artifact and
  holdout/universe inconsistency each fail and write no ledger file; the correct pair passes; and a
  forged attestation claiming `verified=True` with wrong pins is refused at `open()`.

### CEE — ✅ AUTHORIZED, and Session 001 CLOSED *(supersedes "Run CEE first" as a pending instruction)*

"Run CEE first" is now **historical**. Current state:

- **prospectively authorized** in `dcc2c97` (#657) — committed *before* the first read, so the ledger
  cites an authorization that predates the evidence;
- **Session 001 CLOSED — NOT EVALUABLE, n = 17.** Evidence in Git at `07f745b` (#659);
- **no promotion decision generated.** All four examined conditions are recorded
  `examined_not_evaluable_small_n`; none is promising, passed, or failed;
- **median SIP–IEX implementation-shortfall difference = 0.00 bps.** The observed mean difference
  (4.25 bps) is **tail / stub-quote driven** and is **NOT** a systematic execution-improvement finding;
- **R2 unchanged.** Coverage (21 qualifying fills → 17 decision matches → 11 execution matches) is
  coverage evidence only and is explicitly **not** grounds to revisit the frozen matching rule;
- **no K1–K6 contamination.** Outputs stay L0 and INADMISSIBLE; PX-2 untouched; K5 still mechanically
  reported, with its non-discriminating PASS outside the ≥2 GO floor;
- **no CEE scope expansion** until population accrues.

🔭 **FOLLOW-ON HYPOTHESIS — not a result, and not to be built yet.** The observed benefit may be
**IEX stub-quote / tail suppression** rather than a general feed advantage. If so, a *prospective*
**quote-validity filter** could be cheaper and more appropriate than wholesale feed migration. Recorded
so it is not lost; deliberately **not** promoted into a finding and **not** added to Session 001's
condition set — retro-fitting a condition after seeing the data is what the discovery ledger exists to
prevent.

### Deploy-EOL determinism — ✅ CLOSED, now a platform control *(supersedes the LF/CRLF caveats)*

`#660` / `a8f1be2`. The LF/CRLF concerns recorded elsewhere in this plan as historical caveats are
**resolved and enforced**, not merely understood:

- **0 nondeterministic** archived files; **0 mismatches** against the Git blobs;
- the deployment archive **reproduces the Git blob bytes exactly** (2,239 of 2,241 identical; the two
  waivers are Windows-only `.bat` launchers, pinned CRLF on purpose and never executed on the box);
- **CI enforces the invariant** (`scripts/check_deploy_archive_determinism.py`), building the archive
  under *both* `core.autocrlf` settings, so the property no longer depends on an operator remembering a
  flag;
- the deliberate **`-text` digest-pinned evidence trees remain protected** — 10 committed blobs carry
  intentional CRLF inside them, and `.gitattributes` ordering is now regression-tested.

Measured before the fix: **2,078 of 2,239 archived files (93%)** did not match their Git blob.

### DISC-MDQ population — ruling UNCHANGED

Broad DISC-MDQ stays **HELD**; GAP remains **observation-only**; MOM-CORE remains **viable-but-narrow**
(5 names). Do not build the full Phase-B feature library. ⏭ On Monday / later in the week, **update the
census with the additional snapshots** rather than treating the current two-day table as final.

### GAPPER — custody discharged · preparation census RUN · G4 dependency re-read *(new 2026-08-22)*

**Harness custody — CLOSED.** The Stage-0 preparation harness (`74d569d`, built 2026-08-17, 11 modules +
census CLI + 72 tests) had lived for five days on one laptop with no remote copy. Pushed unmodified and
unrebased to `origin/feat/gapper-stage0-prep-harness`; **PR #662** opened against `main` (Tier 2). The
exact validated commit is preserved as the reviewable baseline — deliberately **not** rebased onto `main`
(9 behind), per GITHUB-OPS-001 §2: update once, immediately before merge.

**Preparation census — RUN 2026-08-22T18:32:44Z.** Executed under preparation authority only.

```text
PREPARATION / FIELD-SUFFICIENCY OUTPUT ONLY - NOT A GAPPER STAGE-0 EXECUTION OR VERDICT.
harness commit   74d569daa6f46c61cd502d8faa119aa1edb2f6a3
design artifact  docs/design/Gapper/GAPPER_Research_Design_v2_1_1.docx
design sha-256   2706c4dc406ac19350781db180c315c7f9f38f4c1c8ba9fe8466e9658873d73d  (approved anchor)
contract sha-256 a71bfa120a4f674120244899f2dbdc31f5aead83d35f7f2fb541035d0f2304b8  (INCOMPLETE)
sources          apps/backend/bars_cache  +  apps/backend/data/factor_data.duckdb (sep max 2026-06-16)
run_id           0971749798f7471293079b0e6c51ecf0        write_class  reconstruction
schema           gapper_stage0/census_report/v1          exit 0, no verdict key emitted
```

| Measure | Value |
|---|---|
| Candidate symbol-dates censused | 1,820 |
| Distinct calendar days | **68** (2026-03-24 → 2026-06-30), 57 symbols |
| Sufficient event-days | **4** (target **250**; shortfall **246**; `meets_target=false`) |
| `premarket_bars` | available 5 · partial 631 · **absent 1,184** — median premarket bar count **0**, max 39 |
| `minute_bar_coverage` | available 750 · partial 1,069 · absent 1 |
| `quote_data` | **0 available / 1,820 absent** |
| `halt_data` | **0 available / 1,820 absent** |
| `locate_ssr_data` | **0 available / 1,820 absent** |
| `contract_complete` | **false** — `source_vendor = UNSET_OWNER_DECISION` |

⛔ **This is not a Stage-0 HOLD and may not be recorded as one.** The preparation census **identifies a
Stage-0 data-sufficiency blocker**. The governed Stage-0 disposition remains **unavailable** until G4
authorizes Stage-0 execution. The verdict interlock stayed mandatory throughout and emitted nothing.

**Enumerated missing fields blocking a future Stage 0:**

1. **Raw premarket prints** — the binding constraint. Absent on 1,184 of 1,820 candidate-dates; median 0.
2. **Quote / spread data** — categorically absent. Blocks 0A friction measurement and the §6.3 short cells;
   `gapper_shadow.py` already documents that entry-time spread is unobservable from OHLCV bars.
3. **Halt / LULD data** — categorically absent. Blocks the halt-frequency measure.
4. **Locate / borrow / SSR** — categorically absent. No source exists in the repository.
5. **Daily spine freshness** — `sep` ends 2026-06-16, ~2 months stale.

⭐ **The shortfall is structural, not a data-quality problem.** The cache spans **68 distinct days**, so
even a flawless cache cannot reach the ≥250 trustworthy PIT event-day contract term. Improving fidelity on
the existing cache cannot close a 246-day gap; only a **dataset improvement** can. Note also that all 5
sufficient candidate-dates are April-2026 mega-cap tech (AMD, INTC, NFLX, NOW, NVDA) — a concentrated
sample that would fail §3.1's "materially different environments" term independently of the count.

**G4 — the dependency text, re-read now that MR-002 has terminated.** The plan is subordinate to the
governed artifact, so the approved DOCX was read directly (read-only; hash re-verified before and unchanged).
The dependency lives in **§9, paragraph [172]**, quoted exactly:

> "MR-002 continues on its independent v1.3 path; GAPPER never delays it. The binding constraint across the
> platform right now is OWNER capacity, not developer capacity: MR-002 execution-order Steps 1–2 (physical
> recovery control; operational-custodian naming) are owner acts gating six prerequisites. Therefore Stage 0
> of GAPPER begins only after MR-002 Steps 1–2 are complete. After v2.1.1 owner approval, developer-side
> Stage-0 preparation (dataset-contract drafting, reconstruction scripts against the development store) may
> proceed in parallel; owner adjudications may not compete."

Two facts follow, and they change the *nature* of the G4 ruling:

- **The stated rationale is owner-attention scheduling, not evidence.** The "Therefore" chain is explicit:
  owner capacity is the binding constraint → Steps 1–2 are owner acts → Stage 0 waits so adjudications do
  not compete. GAPPER was never entitled to an MR-002 *result*: §4 ¶[15] calls them "independent peer alpha
  programs" that "never share performance evidence," and §10 ¶[176] states "No MR-002 evidence in any GAPPER
  package … concepts and machinery transfer, verdicts never do." **MR-002 terminating without an economic
  verdict therefore deprives GAPPER of nothing it was ever owed.**
- **The precondition is already satisfied on its own terms.** Steps 1–2 completed **2026-08-10**, twelve days
  before termination: Step 1 (WP-A physical recovery control) CLOSED — A1–A6 executed, verified *from the
  medium* after a disconnect/reconnect cycle, PASS, offline, `INDEPENDENT_OFFLINE_RECOVERY_COPY = CREATED`;
  Step 2 — operational custodian **named (Jay Wang)**, dual appointment recorded in both
  `MR002_ExternalRecoveryCopy_Submission_v1.0.md` §7 and `MR002_OperationalCustodian_Appointment_v1.0.json`.

⚖⚖ **OWNER RULING 2026-08-22 — G4 CLOSED.** Recorded verbatim:

> **G4 CLOSED — prerequisite satisfied before GAPPER Stage-0 authorization.** MR-002 Steps 1–2 were
> completed 2026-08-10; MR-002's later termination without an economic verdict does not reopen or
> invalidate that prerequisite. No evidence transfers between the programs.

This is a **confirmation of an already-satisfied dependency, not a decoupling waiver.** Governing record:
**`docs/design/Gapper/GAPPER_G4_Sequencing_Gate_Closure_Record_v1.0.md`** — in **Git**, because an owner
ruling that closes a gate is *governing* and this plan was then gitignored (no PR, no CI, no review) — ⚠ **no longer true as of the 2026-08-23 canonical-custody ruling; the reasoning for a separate closure record still stands, since a gate ruling is governing in its own right**. The plan
carries operational state; the closure record carries the ruling.

⛔ **The closure is narrow.** It removes **one sequencing gate** and nothing else. §252 authorization scope
is untouched (forward accrual · validation · confirmatory consumption · paper trading · RANK-001 candidacy
each still need their own later authorization); §8.1 operational readiness is untouched and still gates
forward accrual with its probation clock unstarted; §3 acceptance conditions are untouched; no evidence
transfers in either direction.

⭐⭐ **Governance is no longer the blocker; data is.** The resulting GAPPER state:

| Item | State |
|---|---|
| **G4 sequencing gate** | ✅ **CLOSED** |
| Stage-0 preparation harness | Built (`74d569d`); custody **PR #662** in flight |
| Preparation census | ✅ **COMPLETE — non-verdict** |
| Stage-0 data sufficiency | ⛔ **BLOCKED** — 4/250 sufficient event-days; contract incomplete |
| Stage-0 execution | Technically permitted after G4, but presently **NOT EVALUABLE** under the available dataset |
| **Re-entry condition** | Governed dataset improvement **+** prospective `source_vendor` decision **+** re-run of the preparation census |

⛔ **Do not spend a governed Stage-0 execution to rediscover 4/250.** The preparation harness already
established the prerequisite failure **without issuing a verdict** — exactly what the interlock exists to
make possible. The economically useful next GAPPER action is **dataset acquisition and qualification**, not
running the same insufficient corpus through a formally authorized Stage 0.

**GAPPER dataset-acquisition scoping — the work item behind the re-entry condition** *(v0.14 Review
Addendum, 2026-08-22)*. As written, the re-entry condition had no work item behind it, so the eventual
owner `source_vendor` decision would have arrived **uncharacterized**. A bounded scoping task enumerates
candidates against the five blocking field classes **without naming a vendor as the decision** — which
preserves the prospective-decision discipline while making the decision reachable.

```text
GAPPER dataset-acquisition scoping (bounded; preparation authority only; no census re-run,
no Stage-0 execution, no source_vendor population):

  Produce GAPPER_Stage0_DatasetOptions_v1.0 enumerating, for each candidate source,
  coverage against the five blocking field classes:
    1. raw premarket prints  (binding constraint; 1,184/1,820 absent today)
    2. quote/spread data     (categorically absent today)
    3. halt / LULD data      (categorically absent today)
    4. locate / borrow / SSR (categorically absent today; likely broker-side, not vendor-side)
    5. daily spine freshness (sep ends 2026-06-16)
  plus: historical depth vs the >=250-event-day / materially-different-environments contract terms,
  PIT semantics, cost, and acquisition effort class.

  The document characterizes options; it decides nothing. source_vendor remains UNSET until the
  owner binds it prospectively to one exact dataset identity, after which the preparation census
  re-runs per the 2026-08-22 ruling.
```

✅ **DELIVERED 2026-08-23** — `docs/design/Gapper/GAPPER_Stage0_DatasetOptions_v1.0.md` (Git).
`source_vendor` remains **`UNSET_OWNER_DECISION`**; the document names no vendor and ranks nothing.
Its two load-bearing findings:

- ⭐⭐ **The five classes do not partition by vendor — they partition by *why* they are missing, and
  only some are a purchase.** Class **5** is an operational **refresh of an entitlement already
  held** (Sharadar `sep`), not procurement. Class **3** is a **capture** gap, not an entitlement
  gap — `census.py` records that the SIP `s`/`l` (status/LULD) channels are simply *not subscribed*
  under an entitlement the platform already owns. Classes **1–2** are SIP-derivable too; what the
  platform lacks is **history, not access**. So the real question every candidate answers is
  **buy the past or wait for it** — and waiting is ≈**250 trading days ≈ 12 months** at ~1
  event-day per trading day, longer to satisfy "materially different environments."
- 🚨 **"Just pull the history from Alpaca" is a governance question, not a technical one.** The
  subscription ruling makes account 7 the sole entitled SIP identity and the **Phase-A collector
  the sole authenticating component** — a GAPPER historical pull would either repurpose that
  collector or introduce a second authenticating component, which the ruling forecloses. It is the
  cheapest-looking option on the page, which is exactly why it must not be assumed.

⛔ It also refuses to hide one possibility: **class 4 (locate/borrow/SSR) may be unobtainable at
any price** — a PIT locate history is not a retail-scale product. If so the resolution is a
**design** decision (narrow §6.3's short cells to SSR-only · declare the short side NOT EVALUABLE ·
name a proxy *in the contract*), not a purchase. Current-state `shortable`/`easy_to_borrow` is
**not** point-in-time locate, and treating it as such would be the same metadata fiction the
`source_vendor` ruling exists to prevent.

⭐ **One scoping constraint the document must carry explicitly:** field classes **1–2** (and plausibly **5**)
are coverable by sources the platform already has commercial context for; classes **3–4** almost certainly
are not — halt/LULD is exchange/regulatory-side and locate/borrow/SSR is **broker-side, not vendor-side**.
The options document must say so on its face rather than letting a single-vendor framing imply that one
purchase closes all five gaps. ⛔ It is also **not** a purchase recommendation: an options document that
ranks a winner has quietly made the prospective decision it exists to keep open.

**`source_vendor` — owner decision 2026-08-22: KEEP `UNSET_OWNER_DECISION`.** It must **not** be populated
merely to make `contract_complete=true`. The census ran against local cache/reconstruction inputs that
demonstrably fail the contract standard (4/250 event-days, zero quote/halt/locate coverage, `sep` spine
ending 2026-06-16); naming a vendor against this dataset would convert a genuine missing-contract condition
into a **metadata fiction**. When a replacement dataset is selected, `source_vendor` becomes a *prospective*
decision bound to that exact dataset identity, coverage period, field set, PIT semantics, and provenance —
and the preparation census is **re-run**. ⛔ **The 2026-08-22 census may not be reused as a Stage-0 result
after the source changes.**

📌 **Census published to S3** (exact inspected bytes, not regenerated): sha `d5a3d89f…`, VID
`oGhkxbbN1ugg7lcXs.V8XG0T8y0ks0wd`, 1,272,442 B, pinned in `manifests/s3/docs/implementation.inventory.json`,
label **PREPARATION CENSUS / NON-VERDICT**.

**Three GAPPER hazards carried as open controls** — deliberately **not** folded into PR #662:

| Control | State |
|---|---|
| **#407** box-native gapper screener | **DO-NOT-MERGE.** 4 owner decisions open; merging starts no probation clock (`WORKBENCH_NATIVE_GAPPER_SCREENER_ENABLED` defaults off) |
| **#511** `INVALID-EVIDENCE / NO_SELECTION_CONTRAST` guard | ✅ **MERGED 2026-08-23T22:46Z as `992e454`** — owner approval granted; the void v1 `DOES-NOT-TRANSFER` path is **closed**. *(History below retained.)* ~~**SCHEDULED — next GAPPER merge**~~ *(escalated by the v0.14 Review Addendum, 2026-08-22)*. Zero owner decisions required; it is a pure hazard closure whose only cost is one rebase + one CI cycle. Until merged, the void v1 `DOES-NOT-TRANSFER` path stays human-invokable. **Open since 2026-07-25 and labelled "important" across three document generations — the age is itself the finding.** ⛔ Do **not** batch it behind #407. Mechanics: branch `fix/scan001-evidence-integrity`, presently `BEHIND` ⇒ update once immediately before merge (GITHUB-OPS-001 §2); **Tier 3** — it touches `deploy/sync-gappers-to-box.sh` as well as `app/jobs/` + `app/services/`. ⚠ The addendum sequenced it "ahead of/alongside #662"; **#662 merged 2026-08-22T20:35Z**, so #511 now stands alone. |
| `repair_premarket_gate_provenance.py` | **QUARANTINE REVIEW SCHEDULED** — same working session as the #511 merge *(v0.14 Review Addendum, 2026-08-22)*. It contradicts the §5.5 non-retroactive-provenance principle, and every day it stays invocable is a day that principle has a documented exception sitting in the repo. Expected disposition: remove, **or** move under `tools/quarantine/` with an execution guard and a README stating the principle it violates. Not folded into #662. ⭐ **State correction, verified 2026-08-22:** the script is **untracked** — it lives at `apps/backend/scripts/repair_premarket_gate_provenance.py`, is *not* gitignored, and is **absent from `origin/main`**. So the hazard is laptop-local, "remove" would leave **no Git record that it ever existed**, and quarantine-under-`tools/` would be the *first* commit of it. Custody is therefore part of the review decision, not a detail of it. ✅ **REVIEW DELIVERED 2026-08-23** — `docs/design/Gapper/GAPPER_PremarketGateProvenance_Quarantine_Review_v1.0.md` (Git). 🚨 **It found more than a hazard: the script ALREADY RAN with `--apply` against the LIVE corpus between 2026-07-16 and 2026-07-17.** Measured read-only via SSM: of 51 records in `/opt/workbench/data/premarket_gate_evidence`, **26 carry a retroactively-minted `provenance` string (20 `replayed` + 6 `live`, 2026-06-08 → 2026-07-16) and 25 carry none (2026-07-17 → 2026-08-21)** — under one unchanged `scan_001_premarket_gate/v1` schema tag. ⭐ So **absence of `provenance` means "written after the repair", i.e. it marks the NEWEST records, not the least known** — the inverse of the obvious reading. Blast radius today is nil (nothing reads the field; **#511 does not gate on it**), which is why now is the moment to dispose of it. ⚖⚖ **OWNER DISPOSITION — OPTION B APPROVED 2026-08-23** (supersedes AWAITING; S5's recommendation adopted). Binding terms: **(1)** all 51 existing `/v1` records stay **byte-unchanged**; **(2)** ⛔ do **not** strip the manufactured fields from the 26; **(3)** ⛔ do **not** add provenance retroactively to the remaining 25; **(4)** record that `/v1` provenance presence/absence is **not** an authenticity, quality, freshness, admission, or trust indicator; **(5)** preserve the 26/25 population and its historical dates as governance annotation; **(6)** future records are written under **`scan_001_premarket_gate/v2`**; **(7)** `/v2` uses genuine §5.5 write-time provenance, **reusing the already-merged conformant implementation** (`app/research/gapper_stage0/provenance.py`); **(8)** `/v2` carries an explicit **`provenance_semantics`** field so no consumer can confuse the legacy `/v1` *string* with the conformant *structure*; **(9)** ⛔ **no retroactive repair or backfill of provenance**, ever. **Tool disposition: quarantine, not deletion** — preserve under `tools/quarantine/`, **hard-disable the write path** (a quarantined utility that can still run `--apply` is not quarantined), README pointing at the review and the §5.5 violation. 📋 **IMPLEMENTED — PR #670 open 2026-08-23T23:01:16Z** (`fix/scan001-provenance-v2`, `df9ee73`): writer → `/v2` with a genuine §5.5 stamp reusing #662's `gapper_stage0/provenance.py`; source-artifact identity captured **at the read**; `provenance_semantics` on every record; `/v1` left a known schema and untouched; the script preserved under `tools/quarantine/` with **its write path removed** (no write-mode `open`, no serializer; `--apply` refuses, exit 2). 9 new tests encode the *binding terms* — including that the 16:30 ET back-fill never stamps an unstamped `/v1` record (term 9) and never normalises the legacy string on a stamped one — plus a structural quarantine assertion **verified by negative control**. ⚖ **OWNER RULING 2026-08-23 — no blanket schema-admission gate in #670.** #670 stays scoped to provenance correctness and prospective writer semantics. A rule of the form *`schema != /v2` ⇒ reject* would retroactively alter the standing of legitimate historical `/v1` evidence and couple the provenance repair to #511's admission semantics. **If a schema control is added later it must be prospective and cutover-aware:** `/v1` records remain evaluable under the existing #511 rules · records produced **before** the `/v2` activation point are never rejected merely for being `/v1` · records produced **after** it must be `/v2` and carry conformant write-time provenance · a **post-cutover `/v1` record fails closed as a writer/conformance defect** · legacy `/v1` provenance strings remain **uninterpreted residue, never normalised**. ⭐ That is a real invariant that does not rewrite history. ⚠ The untracked original at `apps/backend/scripts/` is **not deleted until #670 merges**, so the only copy is never inside an unmerged branch. This row's **ruling** is CLOSED. |
| `pit_sector_adapter.py::sic_to_sector` *(added 2026-08-23)* | **QUARANTINE REVIEW SCHEDULED** — SEC-001 V3 Disposition Ruling v1.0 rider item 5. `app/research/mr002/spq1/adapters/pit_sector_adapter.py:22` returns `_SIC_DIVISION.get(str(sic).strip()[:1], "MATERIALS")` — a **silent default** for any unmapped/empty SIC, inside a module whose docstring promises fail-closed resolution. **Same never-default defect class** as `repair_premarket_gate_provenance.py`, which is why it lands in this table rather than in a SEC-001-local list. V3 uses the Phase-2B fail-closed path exclusively and **never imports 2A**; the review decides removal vs guard. ⭐ Unlike the provenance script, this one is **tracked and on `main`** — so its disposition is a normal PR, not a custody puzzle. |

🪲 Minor harness defect found while running the census: `--help` raises `UnicodeEncodeError` on a Windows
cp1252 console (a `⇒` in the argparse epilog). Cosmetic, does not affect the census path; was **left unfixed** at census time
so `74d569d` stayed the byte-identical validated baseline for review. ✅ **Discharged:** fixed inside #662
as `ee86281` (`⇒` → `=>`); the same commit claimed a docstring-path correction that **silently no-matched**
(Bash-heredoc backslash mangling, with a whole-file changed-assert that passed on the other replacement),
redone as the correction of record in **#664** (`4d82242`) with per-replacement asserts.

⚠ The **stale "MR-002 HOLD" wording has been corrected at every live site** in this document (§1 scope,
the §2 G4 row, §4.3, §7 worst-case, Track 5, §6 item 32, §8.3, §8.8, §10 prohibitions). Entries inside the
**v0.5 / v0.9 amendment changelogs were deliberately left unedited** — they record what was decided when,
and rewriting a changelog to match present state destroys the audit value it exists for.

### SEC-001 V3 Sector-Classification Disposition Ruling v1.0 — incoming shared-infrastructure changes *(new 2026-08-23)*

**Disposition 1 ADOPTED** (`docs/design/SEC-001/SEC001_V3_SectorClassification_Disposition_Ruling_v1_0.md`,
owner, 2026-08-23): SEC-001 V3 uses a genuine **effective-dated** sector spine built on the surviving MR-002
EDGAR SIC machinery. Disposition 2 (accept restated labels as a recorded limitation) was **declined** — the
§5.1b META demonstration plus Finding A's measured **~8.4% sector-boundary-crossing rate** make restated
classification a demonstrated, material, *directional* leak into the grouping variable of a momentum signal.

⚖ **No ATP gate moves.** This ruling transfers **machinery and reference data only**, never MR-002 evidence
(standing cross-program rule). K1–K6, the value-extraction order, and the DISC-001 gates are untouched. What
does reach this plan is **three registered changes to infrastructure ATP sits on**:

| # | Registered change | What ATP must do about it |
|---|---|---|
| 1 | **`permaticker` ingested into the store `tickers` projection** | ✅ **ALREADY LANDED — CLOSED 2026-08-23.** 🚨 **This row previously said the opposite, and the error is instructive:** the "10-column `_TICKERS_COLS` with no `permaticker`" was read from the **primary working tree**, which sits on `research/mr002-validation2-lineage` — a branch behind `main` by the entire permaticker workstream. Verified on `origin/main`: `_TICKERS_COLS` has **11** entries with **`permaticker` leading** (`store.py:46`, owner ruling **2026-07-29**), `tickers` declares the column, and the upsert names and casts it. Verified on the **live** box (SSM, read-only): `permaticker` present, **21,988 / 22,104 rows non-null (99.47%)**. Nothing to schedule, nothing to coordinate, no same-commit consumer updates. Full enumeration: **`docs/design/SEC-001/SEC001_Tickers_Projection_Consumer_Enumeration_v1.0.md`**. ⭐ The enumeration also **inverts the risk**: three modules (`validation/security_lineage.py`, `validation/adjustment_verifier.py`, `layer2_lineage_hole_census.py`) *already depend* on the column, so the live exposure is not "a consumer breaks when it appears" but "identity resolution changes behaviour as coverage rises" — a row that failed closed on NULL starts resolving. ⛔ Do not backfill the 116 NULLs by ticker equality (same error class as the quarantined provenance repair); ⛔ do not add `permaticker` to `drift_audit_provenance.sector_content_digest` (it would break comparability of every prior drift audit).. ⚖⚖ **OWNER RULING 2026-08-23 — SNAPSHOT-GOVERNED RESOLUTION.** Closed as **AUTHORITATIVE-REFRESH ALLOWED · HEURISTIC/RETROACTIVE BACKFILL PROHIBITED · FAIL-CLOSED RESOLVER RETAINED · GOVERNED RUNS SNAPSHOT-PINNED · EXISTING SECTOR DIGEST UNCHANGED.** The governing distinction is **source evolution vs. historical rewriting**: a row becoming resolvable in a *later authoritative snapshot* is new information arriving prospectively; a value reconstructed from ticker equality is a fabricated answer. Terms: the 116 NULLs stay untouched · a normal vendor refresh **may** populate them only from the authoritative source · `permaticker_asof()` keeps failing closed, no fallback · resolution is **snapshot-relative** (NULL→resolved *across* snapshots allowed; changing the answer *inside* a frozen snapshot is not) · **SEC-001 freezes the exact TICKERS/factor-store snapshot identity together with the resolver/code identity before V3-RC**, with a **resolution census at the freeze** (eligible · resolved · NULL/unresolved · out-of-interval) so the exclusion population is reproducible · coverage improving **before** the freeze ⇒ re-measure and freeze the improved snapshot; **after** ⇒ V3-RC does not consume it · a row unresolved at the frozen snapshot stays `sector_unclassified` **for that run**. ⭐⭐ **A rising resolution rate is NOT drift** — it is expected source evolution; the drift would be letting it alter a frozen run *without* changing the bound source identity. ✅ Resolver conformance **verified 2026-08-23**: `store.py:907` returns `None` "never a guess" on all five unresolved cases, and `security_identity.py:140` treats even a store exception as unresolved — term 3 needs no code change, only protection. Full terms: the enumeration doc §3. |
| 2 | **SEC-001 V3 classification acquisition — ACTIVE** *(row rewritten 2026-08-24; the prior "~85k header fetches over the ~800-name PIT-200 union / one unattended crawl" description was materially stale)*. Governed PIT-200 membership = **1,247 rebalance slots**; frozen union = **1,167 permanent identities**. CIK-resolution sidecar resolved **1,167/1,167** — zero unresolved, zero conflicts, zero ambiguities — from the **original governed Sharadar TICKERS acquisition**; **no new vendor acquisition was required.** Acquisition machinery passed the live **ABT v1.4 canary** after Defect E remediation; the full v1.4 crawl is running over the same frozen population and order. | **REGISTERED HERE as a platform data-acquisition program**, alongside the GAPPER `source_vendor` UNSET decision, so the data-programs registry stays complete. SEC request-ceiling only: **no purchase, no Alpaca quota interaction, no K1–K6 interaction.** ⛔ **No classification coverage has been computed**; coverage-freeze artifact `5b26ffa209a6a13a599a99fb28268b46be569cd2` remains **UNSPENT**. Live per-identity progress belongs in the crawl's own progress/state artifacts, **not here** — this row states ACTIVE / completion pending, deliberately. |
| 3 | **Phase-2A adapter quarantined** (`app/research/mr002/spq1/adapters/pit_sector_adapter.py::sic_to_sector`) | Joins the open-controls/quarantine table below as a **second row of the same defect class** as `repair_premarket_gate_provenance.py`. V3 uses the **Phase-2B** fail-closed path (`phase2b/sic_sector.py`) **exclusively** and never imports 2A. |

⭐⭐ **The pattern worth naming: this is the second "never-default" violation found in eight days, in an
unrelated subsystem.** Both silently substitute a plausible value where the design says fail closed —
`sic_to_sector` returns `"MATERIALS"` for any unmapped SIC (verified: `_SIC_DIVISION.get(sic[:1],
"MATERIALS")`), inside a module whose own docstring promises "a same-timestamp conflict fails closed."
Two instances in different subsystems is a **class**, not a coincidence, and the class deserves a sweep
rather than two one-off quarantines. Unresolved names must carry `SECTOR_PIT_IDENTITY_MISSING` /
`sector_unclassified` — excluded with a reason, **never defaulted**.

### ✅ GAPPER SYNC RESTORED 2026-08-24 — SG rotated, publisher commit-pinned, exercised end-to-end

⚖ **Owner authorization 2026-08-24: administrative access rotation, narrow replacement only** —
"authorization specifically to restore the already-existing SSH operator access pattern, not to
change the host's broader network posture." Executed **add → prove → revoke** so a typo or a stale
IP observation could not lock the operator out.

**ACCESS ROTATION RECORD**

| Field | Value |
|---|---|
| Security group | **`sg-00dcdde89fa30e99a`** (instance `i-084f47fe4e69192e9`, workbench-paper) |
| Old CIDR (revoked) | **`18.88.47.36/32`** — description *"SSH operator 2026-08-10"* |
| New CIDR (added) | **`18.88.35.70/32`** — rule `sgr-0931a2fc44b988952`, description *"SSH operator 2026-08-24 (rotation from 18.88.47.36/32)"* |
| Port / protocol | **tcp 22 → 22 only.** ⛔ No subnet widening, no `0.0.0.0/0`, no additional ports |
| Timestamp (UTC) | **2026-08-24T00:44–00:46Z** |
| Egress IP re-read before the change | `18.88.35.70`, confirmed by **two consecutive** reads |
| Final inbound rule set | **exactly one rule** — `tcp/22 18.88.35.70/32` |
| Proof between add and revoke | `ssh workbench` → `SSH_OK` · `scp` probe exit 0, file read back and removed |
| Proof after revoke | `ssh workbench` → `SSH_STILL_OK` |

⭐ **Owner's standing preference, recorded for later:** the operational deployment path should move
to **SSM** rather than repeatedly rotating residential/dynamic SSH `/32`s. ⛔ Explicitly **not**
in scope today — do not broaden a Monday-critical task into an access redesign.

**Deployment-source binding — CLOSED.** The publisher no longer runs from whatever a research
worktree has checked out:

| | Before | After |
|---|---|---|
| Scheduled task action | `bash /c/LLM-RAG-APP/ai-trading-app/deploy/sync-gappers-to-box.sh` (primary tree, branch `research/mr002-validation2-lineage`) | `bash /c/LLM-RAG-APP/wt-deploy-gappers/deploy/sync-gappers-to-box.sh` |
| Source identity | whatever is checked out | **detached worktree pinned at `4c4a2b1089bbffa9d71022ebb9def1bd7431d3a6`** (= `main` with #511 **and** #670) |
| Trigger | weekdays 08:00 CT | **unchanged** |

⚠ A pinned worktree does **not** self-update. Advancing it is now a deliberate act — which is the
point — so a future fix on `main` reaches production only when someone moves the pin.

**Pre-Monday exercise — done, so Monday is verification and not first contact.** Log redirected via
`GAPPER_SYNC_LOG` throughout, so the operational log carries no backdated exercise entry:

1. **Dry-run, today (Sunday)** → correctly **failed closed**: *"no scanner guard-log activity at all
   for 2026-08-23"*. The strict path works — nothing published, alert would fire.
2. **Dry-run, real artifact (`--date 2026-08-21`)** → *"would publish … names=10
   scanned_at=2026-08-21T12:30:03Z"*. Full validation chain passes.
3. **The scheduler's exact command line** (`bash.exe -lc "bash /c/LLM-RAG-APP/wt-deploy-gappers/…"`)
   → same result, so the binding works under the invocation the task actually uses.
4. **Live publish** of `premarket_gappers_2026-08-21.json` → *"synced … sha256 `da09e964ae74…`
   verified"*. Confirmed on the box: it is now the newest artifact, and its sha256 matches the local
   file **byte-for-byte**. The `scp` + remote-sha-verify leg is proven.

**Monday 2026-08-24 expectation.** The 08:00 CT task runs the pinned publisher; if the scanner
produced an 08-24 artifact, the gate at 09:25 ET should see `source_date == asof` and
**`stale: false`** — the first admissible forward day since ~08-10. ⛔ If the scanner did not run,
the publisher now **fails closed and alerts** rather than republishing a stale file.

---

### 🚨 The failure this replaced — retained as the record

### 🚨 GAPPER SYNC HAS BEEN FAILING SINCE 2026-08-10 — found 2026-08-23, BLOCKS Monday

Found while establishing a commit-pinned deployment source for #511. This is larger than the
task-binding defect it was found through, and it is **not** a code problem.

**Symptom.** `/c/LLM-RAG-APP/claude-trading-view/sync-gappers.log`: last clean sync **2026-08-05**;
one partial on **08-10**; then `FAILED` on **every trading day** 08-10 → 08-21. Newest gappers file
on the box is **`premarket_gappers_2026-08-10.json`** (37 total).

**Consequence, measured on the box.** The premarket gate still writes a record every day, but from
an 11-day-old artifact — `premarket_scan_2026-08-21.json` carries `source_date: 2026-08-10`,
`scanned_at: 2026-08-10T12:30:03Z`, **`stale: true`**. ⭐ Those are exactly the two conditions
**#511 excludes** (`EXCLUDE_STALE`, `EXCLUDE_SOURCE_DATE_MISMATCH`), so #511 is doing its job —
but it means **no admissible forward evidence has accrued since ~2026-08-10**, and Monday will be
the same.

**Root cause — confirmed, and it is the SSH allowlist, not the scanner:**

| | |
|---|---|
| Current laptop egress IP | **18.88.35.70** |
| SG `sg-00dcdde89fa30e99a` 22/tcp allowlist | **18.88.47.36/32**, described *"SSH operator 2026-08-10"* |

The ISP rotated the IP after the 08-10 entry was written. Every `FAILED` line lands at **:21–:22 s**
past the minute — the script's 20 s `ConnectTimeout` plus overhead. That is a connect timeout
signature, not a scanner or validation failure. ⭐ Note the **2026-07-21** line in the same log,
`synced premarket_gappers_2026-07-20.json` — the stale-republish incident #511 exists to prevent,
visible in the record.

⛔ **NOT ACTIONED — owner decision required.** Editing the SG is a security-boundary change and is
owner-ruled (`gotcha_ssh_blocked_by_ip_rotation`: do not edit the SG without confirmation). The fix
is to authorize `18.88.35.70/32` and revoke the stale `/32`. Until then the pre-Monday exercise of
the merged #511 publisher **cannot complete its `scp`/`ssh` leg**, and Monday's gate keeps
producing correctly-excluded stale records.

### Deployment-source binding defect *(the smaller finding, same investigation)*

The scheduled task **"Sync Premarket Gappers to AWS"** (weekdays 08:00 CT) executes:

```text
C:\Program Files\Gitinash.exe -lc
  "bash /c/LLM-RAG-APP/ai-trading-app/deploy/sync-gappers-to-box.sh"
```

— the **primary working tree**, currently on `research/mr002-validation2-lineage`. So a production
publisher runs whatever an active research branch happens to have checked out: `main` can hold the
safety fix while production behaviour depends on an unrelated local branch. ⚖ **Owner ruling
2026-08-23: bind the task to a dedicated deployment worktree or an exact committed revision.**
⭐ Feasibility confirmed — the script's inputs are absolute (`GAPPERS_DIR=/c/LLM-RAG-APP/claude-trading-view`),
so it is checkout-independent; it also has `--dry-run` and an overridable `GAPPER_SYNC_LOG`, which
is what the controlled pre-Monday exercise should use.

### 📋 MONDAY 2026-08-24 — GATE SEQUENCE *(owner-specified 2026-08-24; verification, not development)*

⭐ **Tonight's sequence is CLOSED: #511 · #670 · SG rotation · publisher binding + exercise.** No
owner decision is outstanding. Monday is the next executable checkpoint, and **the one fact that
cannot exist yet — an 2026-08-24 forward artifact — stays unclaimed until Monday.**

**0 — Clock identity first.** Record **UTC and ET explicitly**. ⛔ Do not infer UTC from the host
shell (the box host is EDT, containers are UTC — 4th recorded incident).

**1 — Read-only capacity preflight, using the wrapper's OWN calculation.** ⛔ Do not reuse 08-22's
margin, build-cache size, or `df` output as a proxy; the point is to re-measure immediately before
the collector depends on it.

Deployed guard verified 2026-08-24 at `/opt/workbench/mdq/mdq_run.sh` (deployed 2026-08-17,
main @ `0273012`). Its **actual** arithmetic — worth knowing exactly, because it is not a byte
comparison:

```sh
ROOT_HOST=/opt/workbench/data              # same filesystem as / (/dev/root) - verified
size_gb=$(df -B1G --output=size  "$ROOT_HOST" | tail -1)   # whole GiB, ROUNDED UP
avail_gb=$(df -B1G --output=avail "$ROOT_HOST" | tail -1)  # whole GiB, ROUNDED UP
floor=$(( size_gb / 5 )); [ "$floor" -lt 10 ] && floor=10  # INTEGER division
[ "$avail_gb" -lt "$floor" ] && BREACH                     # strict <, not <=
```

Reproduce read-only, and record **byte precision** alongside the wrapper's own units:

```sh
sudo df -B1  --output=size,avail /opt/workbench/data | tail -1   # bytes, for the record
sudo df -B1G --output=size,avail /opt/workbench/data | tail -1   # what the guard actually compares
```

⭐⭐ **The binding leg has FLIPPED since the 29 G era.** With the volume resized to ~60 GB, if
`df -B1G --output=size` reports **58**, then `floor = 58/5 = 11 G` — so the **20 % leg binds, not
the 10 G leg**, the opposite of the old gotcha where 20 % looked healthy while 10 G was the real
constraint. Because `--output=avail` also rounds **up**, `avail_gb < 11` ⟺ `avail_bytes ≤
10,737,418,240` — which is why the owner's byte threshold and the 11 G floor are the *same*
statement, not a contradiction. ⛔ Report the measured numbers, never the remembered "11/12 GB".

⚠ **Two other fail-closed gates share this wrapper, and ORDER MATTERS:** the **universe SHA pin**
(`0c57bd71…`) is checked **before** free space, and the sample-mode **single-instance** `pgrep`
check after. A trip in one masks the others — this has already happened once
(`app/research/capture/identity.py:58`). Read the actual failure line, do not assume which gate fired.

⛔⛔ **PRESERVE THE WRAPPER EXACTLY AS DEPLOYED — owner instruction 2026-08-24.** Do **not**
"clean up" the integer-GiB arithmetic, do **not** convert it to a byte comparison, and do not
touch it before Monday. Its semantics are now understood, recorded, and **already part of the
governed schedule identity**. Any later rewrite is a **separate reviewed operational change**,
never a tidy-up folded into another task. ⭐ The rounding is not a bug to fix; it is the deployed
contract that Monday's evidence must be reconcilable against.

**Evidence to record at the preflight — BOTH views, owner refinement 2026-08-24.** Recording only
one of these forces a future reader to reverse-engineer the rounding a second time:

| View | What to capture |
|---|---|
| **What the wrapper acts on** | `size_gb`, `avail_gb`, and the **computed `floor`** (`size_gb / 5`, raised to 10) — the integers the comparison actually uses |
| **Raw bytes, for audit/reconciliation** | `df -B1 --output=size,avail /opt/workbench/data` — exact byte values |

⭐ **And record the LITERAL wrapper output on any failure.** Because the gate order is
**universe SHA pin → free space → single-instance**, the first failure masks every later one.
⛔ Do not write "free-space failure" or "identity failure" from inference — capture the exact
failure line and exit status the wrapper emitted, and attribute the stop to **that** gate.

**2 — If the capacity gate fails, STOP.** ⛔ Do not delete rollback images, evidence, or anything
else ad hoc to make 09:25. Refusing capture **is** the correct behaviour; the prior failure
established that.

**3 — After the ~08:30 ET scanner and ~09:00 ET publisher** (task now pinned to
`wt-deploy-gappers` @ `4c4a2b1`): verify the box's **newest** gappers artifact is the **2026-08-24**
file · verify its **sha256 against the published local artifact** · then verify the evidence record
shows **`source_date == asof == 2026-08-24` and `stale == false`**.

**4 — At/after 09:25 ET:** verify `mdq-sample.service` **actually started successfully** — ⛔ do not
trust the timer schedule. Timers confirmed on the box: `mdq-sample` 09:25 · `mdq-eod` 16:30 ·
`mdq-freeze` 16:45 EDT, all next-firing Mon 2026-08-24, last run Fri 2026-08-21.

**5 — Do not infer a successful day from a successful start.** Let 16:30 / 16:45 ET EOD+freeze
complete, then **verify the partition and the S3 mirror** before calling 08-24 a conforming
governed day.

**Monday decision tree:**

| Observation | Action |
|---|---|
| fresh gappers **+** storage PASS **+** sampler starts | continue normally |
| publisher fails because the **scanner** is absent | ✅ correct fail-closed outcome. ⛔ **Do not republish 2026-08-21.** |
| gappers still stale **or** storage fails | ⛔ **No workaround exists to manufacture an admissible day.** Diagnose and **preserve the failure evidence**. |

### Execution order from here

```text
Monday pre-09:25 ET free-space preflight
  -> continue governed capture
  -> passive CEE population accrual
  -> repeat the DISC-MDQ census later in the week
  -> decide whether another bounded CEE observation OR a MOM-CORE x MDQ study
     has enough population

GAPPER track (independent, runs in parallel, no owner adjudication required):
  #511  DONE -- MERGED 2026-08-23T22:46Z as 992e454 (owner approval granted)
       main moved 5c3fa1d -> a992a9e mid-decision, so the update was performed ONCE more
       (not ceremonially): #667/#668 touched services/premarket_gappers.py, adjacent to
       #511's premarket_verdict.py. Re-validated on the new base: ruff clean, 781 tests
       green (services + altdata), 4 invariants. Required "Python CI Gate" green on the
       exact head 02774fe; main unmoved at merge; walk-away 29 days.
       !! MERGING IS NOT DEPLOYING: the laptop scheduled task runs deploy/sync-gappers-to-box.sh
          from the WORKING TREE (branch research/mr002-validation2-lineage), which still holds
          the OLD permissive script. The strict publisher is not live until that tree is updated.
  -> repair_premarket_gate_provenance.py   RULED 2026-08-23 (Option B) and IMPLEMENTED:
       PR #670 open -- /v2 writer + section 5.5 stamp + quarantine with the write path removed.
       Awaiting review + walk-away; on merge, delete the untracked original under
       apps/backend/scripts/ so exactly one copy survives.
  -> GAPPER_Stage0_DatasetOptions_v1.0                       DELIVERED 2026-08-23
  -> Stage 0 remains blocked on dataset sufficiency regardless of G4

  DISCHARGED 2026-08-22 (was the head of this block):
    PR #662 harness custody          MERGED 20:35Z  (5714ca1)
    owner G4 ruling / closure record MERGED 20:37Z  (#663, 7089ccf)
    census CLI docstring redo        MERGED 21:26Z  (#664, 4d82242) - the docstring half
                                                     of ee86281 silently no-matched; this is
                                                     the correction of record
    Stage-0 prep scoping memo        MERGED 21:30Z  (#665, 5c3fa1d) - the 2026-08-17 memo,
                                                     not the DatasetOptions document above
```

⛔ **No** broad DISC-MDQ development, **no** GAP feature implementation, and **no** strategy / L1 change
may start from CEE 001.

---

## State sync — 2026-08-20 PM *(applied in place per the ONE CURRENT PLAN rule; no new version)*

⚠⚠ **v0.13 branched from a PRE-SYNC copy of v0.11, so five factual corrections verified against `main`
on 2026-08-20 did not carry forward.** They are re-applied here. Verified against `main` @ `15da72c`.

1. 🚨 **PX-1 is NOT open — ruling 3 was SIGNED 2026-08-19.** Registration **§8.3**
   ("Undefined-verdict disposition — SIGNED, 2026-08-19"); §5 disposition-table row 4 reads
   "SIGNED, §8.3"; merged **`d43817b` (#647)**, residual stale markers cleared **`15da72c` (#648)**.
   v0.13 asserts it is unsigned in **five** places (§4.12 table row 3, §4.12 narrative, §4.12 sequencing
   block, §6 item 18, §4.13 PX-1) plus §8 item 19 and §11. **All corrected.**
   ⭐ This is exactly the failure §4.13 warns about, one level up: **a checklist inherited across document
   versions accumulates items that were discharged but never struck** — and a *phantom* blocker on the
   pre-exploration gate is as costly as a missed one, because it sends someone to obtain a signature that
   already exists.
2. **PX-4 and PX-5 were already answerable and are now answered** (see §3.5). The symbol holdout **exists**:
   `mdq_phase_a_holdout.json`, LF sha256 `6c6cf03a...`, 850 B, 10/50, committed **`63c0c52` (2026-08-17)**
   — **before capture began**. §4.12 step 4 is confirmed: Program Start Record v0.2 §6 stamps image
   `cb4e42cd1481...` with the container created **50 s after the build**.
3. **PX-6 is now in durable custody — the v0.13 custody caveat is discharged.** Committed **`9a666e1`**,
   binding test **`d51f232`**, pushed to `research/disc-mdq001-phase-a`, **PR #650** open. Test count is
   **47** (not 45); **247** across the surrounding suites.
4. **PX-3 in flight — PR #649** lands `docs/design/MDQ-001_Rulings_2026-08-20.md`; **CI green** (Tier 0
   confirmed by behaviour: Frontend / Python FULL / Build image all skipping).
5. 🚨 **THE POPULATION PRECHECK HAS BEEN RUN — and it inverts the research priority (new §6 item 23a
   result).** Counted over both existing snapshots. **GAP — v0.13's #1 priority and the natural redirect
   target — has ZERO intersection with the MDQ universe on BOTH days.** The only family with any overlap
   is **MOM-CORE**, at **5 authorized names**. Detail in §4.10.4.
6. **Custody note** *(SUPERSEDED 2026-08-23 — see the canonical-custody ruling in the 2026-08-23 state
   sync; retained because it records what was true when written)*: `docs/Strategies/` is **gitignored** (`.gitignore:126`) — this plan **was** a local/S3
   artifact, not reviewable in a PR diff, and **no CI guards it**. `docs/design/**` **is** tracked, which is
   why governance records land there. Live input to §8 item 7.
7. **Host storage:** EBS `vol-0457fe650ba7fd66a` modification **COMPLETED** 30 → 60 GB;
   `growpart`/`resize2fs` still deferred to after the 16:45 ET freeze.
9. 🏁 **GATE PX CLOSED OUT (PR #651).** PX-2 **signed** at registration §8.4, with the
   *determination* made prospectively rather than left conditional; PX-4b **stamped** with named
   bounds, pre-stamp identity `6c6cf03a...` retained and symbol-list hash `320a8c3b...` attesting the
   ten symbols are untouched. github-ops skill gains §7.1/§7.2 (merge readiness = the *required*
   context, not a test job; `strict` ⇒ merge main in locally and push once).
8. ⚖ **OWNER RULING on the revised research priority — the GAP fallback is WITHDRAWN.** See §4.10.6. Effective order: **MOM-CORE (viable but narrow) → GAP (population observation only) → MOM-NEAR / OVERSOLD (NOT EVALUABLE on the current population)**. **Do not build Phase-B feature code yet**; accumulate more DISC snapshots and repeat the intersection census first.

---

## Change summary — v0.14 (LOW-001 Dynamic-PIT cross-program integration boundary, 2026-08-22)

1. **LOW-001 Dynamic PIT is recognized as a parallel platform/conformance workstream, not an ATP/MDQ
   research branch.** It does not alter K1–K6, DISC-MDQ, CEE, GAPPER, reserve-strategy gates, or the ATP
   value-extraction priority order.
2. **Shared infrastructure is authorized; shared alpha is not.** LOW-001 and Opportunity/DISC may reuse
   permanent-security identity, session-calendar semantics, PIT/as-of conventions, and evidence metadata.
   Opportunity candidates/checkpoints/“Why it left”/MDQ enrichment may not influence LOW-001 execution.
3. **Current LOW-001 implementation state is recorded.** #661 is merged at `7bd35f1c`; the safety baseline
   is being built before any dynamic acquisition capability; explicit PAPER liquidation and concrete
   permaticker/provider wiring remain open.
4. **No accidental strategy promotion.** A future attempt to combine DISC/Opportunity information with
   LOW-001 is a separate research mechanism (LOW-002 or another prospectively registered program), not a
   Dynamic-PIT conformance change.
5. **The plan remains ONE CURRENT PLAN.** v0.14 supersedes v0.13 directly; v0.13 remains historical evidence.

---

## Change summary — v0.13 (holdout-scope ruling + DISC-MDQ population precheck, 2026-08-20)

**Scope note.** No settled substance reopened, no review budget consumed, no K-criterion or DISC gate touched. v0.13 records three things that only became visible once the Watchlist product and the DISC-MDQ reader existed side by side, plus the custody caveat on the uncommitted Phase-A work.

1. **The symbol holdout has two different scopes, and only one of them is enforceable (new §4.10.5).** The implemented `MdqFeatureReader` embargo protects **MDQ corpus bytes** — that is correct and now provably works. But §4.10.2's holdout was written for `DISC-001` exploration generally, and DISC's own inputs are Sharadar / Factor Store / GAP, which the deployed Watchlist **displays to the operator every session** (Watchlist v0.6 §10.3 keeps held-out symbols visible, correctly, since the embargo protects MDQ bytes and not candidate existence). So a symbol subset is a real holdout for an **MDQ-derived** hypothesis and is **structurally void** for a **Sharadar-derived** one — the operator has already seen it. This answers v0.11's §3.5 question more usefully than a hash would: record which hypotheses each holdout actually protects, and accept that for DISC-001 hypotheses the only clean test set is prospective post-freeze data.
2. **The DISC ∩ MDQ enrichment population is smaller than §4.10.4 states, and may be near zero (§4.10.4 revised; new precheck at §6).** Watchlist v0.6 §3.1 freezes **ETF exclusion** into `DISC-001-WATCHLIST / v0.3.0`, while the MDQ universe is 22 ETFs + 28 top-ADV names — so the OVERSOLD/MOM-NEAR intersection is at most **28 symbols**, not 50. And the first deployed snapshot (`as_of=2026-08-19`) reports **OVERSOLD 0, MOM-NEAR 0**. If those families stay empty, DISC-MDQ Phase B has no population for two of its four research priorities. v0.13 adds a **population precheck** — count the authorized intersection per family per session over the accrued corpus **before** building feature code. This is the `MOM-SIP-0` lesson arriving a second time: establish the population exists before investing in the study.
3. **Uncommitted work is not custody (§4.13, §6).** ✅ *DISCHARGED at the 2026-08-20 PM state sync — committed `9a666e1` + `d51f232`, pushed, PR #650, 47 tests. Retained as written because the principle stands.* The Phase-A reader, its 45 tests and its green type/lint runs exist only in `C:/LLM-RAG-APP/wt-disc-mdq001`. v0.12 states this honestly and correctly leaves PX open — but the PX block now reads `IMPLEMENTED + TESTED` in a way a scanning operator can mistake for discharged, and single-machine artifacts have exactly the durability profile the 2026-07-27 volume-destruction incident punished. Commit-and-push to a draft branch costs minutes and should precede the state-sync claim, not trail it.
4. **Holdout-artifact stamping added explicitly to PX-4.** Deriving `2026-10-06..2026-10-17` from the frozen rule is a sound bridge, but `mdq_phase_a_holdout.json` was supposed to be stamped at D0 and D0 has passed. Stamping it — with the derived value and its provenance — is the resolution; deriving indefinitely is not. Note also that the regression test deliberately pins the *unstamped* state, so the correct governance act will **fail CI by design**: stamp and test-update belong in one commit, and the failure must not be "fixed" by reverting the stamp.
5. **Fixture symbols vs governed holdout list (§3.5).** v0.12 change 3 names TSLA/XOM/AMZN as the forbidden rows proving exclusion. Record whether those are the **actual governed holdout symbols** or arbitrary fixtures. If arbitrary, the test proves the mechanism but not that the reader is wired to the real list — add a test binding the reader to the governed artifact.
6. **New §8 item 21** for the holdout-scope ruling.

## Change summary — v0.12 (DISC-MDQ Phase-A implementation state sync + Phase-B ledger gate, 2026-08-20)

**Scope note.** This is a state/sequencing sync, not a redesign of DISC-001, MDQ-001, K1–K6, or the frozen `DISC-001-WATCHLIST / v0.3.0` product gates. It records the implemented DISC-MDQ read-boundary mechanism, surfaces two governance artifacts that must be closed before exploration, and makes the already-ratified discovery-ledger obligation executable as a hard Phase-B prerequisite. **No live MDQ exploratory corpus read occurred in Phase A.**

1. **DISC-MDQ Phase A is BUILT + GREEN in an isolated worktree, not yet landed.** Working tree `C:/LLM-RAG-APP/wt-disc-mdq001`, branch `research/disc-mdq001-phase-a` from `main@15da72c`. New `app/research/disc_mdq/` package plus focused tests; 45 new tests, 245/245 across `disc_mdq`, `disc001`, `test_mdq_capture`, and `test_mdq_admissibility`; `ruff`, `ruff format`, and `mypy` all green. The work remains uncommitted at this state-sync point.
2. **PX-6 mechanism implemented before any exploratory read.** `MdqFeatureReader` requires an `AuthorizedScope`; there is no unrestricted mode and no widening flag. Held-out dates are refused before the partition is opened, and unauthorized rows are discarded inside the parse loop before becoming observations. Frozen-partition manifests are verified in full and mutated corpora fail closed.
3. **Holdout proof is stronger than a live-corpus spot check.** Synthetic fixtures deliberately contain forbidden TSLA/XOM/AMZN rows and prove they never emerge from the reader. The live corpus was intentionally not opened; that remains a Phase-B act and a discovery-ledger event.
4. **Read purpose is intentionally singular.** `ReadPurpose` has exactly one Phase-A exploration member, pinned by test. Governed holdout evaluation remains a separate explicit act, never a flag or widening mode on the exploration reader.
5. **Machine-readable holdout artifact gap recorded.** `mdq_phase_a_holdout.json` still carries `"period_holdout_dates": "STAMPED_AT_FIRST_ADMISSIBLE_CAPTURE"` even though D0 and the concrete period holdout are already governed. Phase-A therefore derives `2026-10-06..2026-10-17` from the frozen rule, records that provenance, and cross-checks any future concrete stamp; mismatch is fatal. The regression test deliberately pins the current unstamped state so a later governance stamp requires an explicit test update rather than a silent transition.
6. **Discovery ledger becomes a hard Phase-B prerequisite.** §4.10.2 already requires an append-only record of every condition examined. The ledger implementation does not yet exist. Phase B may not compute its first feature until ledger infrastructure is operational and able to record the authorized scope, corpus/partition identity, condition/feature examined, code identity, disposition, and relevant denials. `AuthorizedScope.denials` retains the required denial detail for this purpose.
7. **Universe hash normalization is clarified.** The governed universe pin is `sha256(universe_symbols_file_LF)`. A Windows CRLF working-tree copy hashes differently by raw bytes; LF-normalization reproduces the governed pin and Git blob. Do **not** re-pin governance to a platform-specific CRLF hash.
8. **PX status remains OPEN overall.** The code obligation represented by PX-6 is implemented/tested in the worktree, but Gate PX is not globally closed until the remaining PX governance items clear and the Phase-A code itself enters durable repository custody.
9. **Watchlist/Opportunity History unaffected in eligibility.** DISC-MDQ remains an additive research sidecar over already-admitted candidates. It does not alter `DISC-001-WATCHLIST / v0.3.0`, and absence of MDQ coverage never invalidates a DISC candidate.

---

## Change summary — v0.11 (pre-exploration verdict integrity + execution-order repair, 2026-08-20)

**Scope note.** No settled substance is reopened and no review budget is consumed. v0.11 does three things: it repairs a genuine execution-order defect in §6, it raises one verdict-integrity problem that must be settled **inside the narrow window before exploration begins**, and it clears stale state that v0.10 carried forward. D0, the review window, the holdout dates, every ratified K value, the L0/L1/L2 discipline, the gate chain and Track 6A are **unchanged**.

1. **K5 may be structurally unfalsifiable — new §4.11.1, and this is the item that matters.** v0.10 change 3 records that unmatched fills are *excluded from the K5 ratio* and flags this only as "a potential discriminating-power weakness." Follow it through: if fills without a matching governed quote leave the denominator, then coverage = produced / (fills that had a match) ≈ **100% by construction**, and K5 **cannot fail**. The observed ~54.7% / 65.8% / 66.7% match rates are exactly the population being removed. A criterion that always passes is worse than one that is never evaluable, because it **counts toward the ratified GO floor of ≥2 evaluable-AND-PASS** — quietly converting the two-criterion floor back into the single-criterion test §4.11 was built to prevent (K3 + a tautology). This is a **verdict-clause question**, in the same class as the unsigned ruling 3, and it must be recorded prospectively — not by retuning K5, which §4.10.1 forbids and which would be post-hoc regardless.
2. **§6 execution order repaired — duplicate item numbers removed.** v0.10's "Current execution order" ran 9–18 and the "After D0" block then restarted at 14, 15, 16 before jumping to 19, 20, 19, 20, 21, 22. Items **14, 15, 16, 19 and 20 each appeared twice with different content**. An operator citing "item 14" could mean either "implement the DISC-MDQ embargo" or "provision the capture root (done)". Renumbered end-to-end with no duplicates.
3. **Ordering defect inside that block (new §4.13).** §4.12 requires ruling 3 signed and §6 item 16 requires the rulings document in Git custody **before** exploratory reads — yet CEE (item 13) and DISC-MDQ-001 (item 14) were listed *ahead* of both. As written, the sequence instructs starting exploration before the custody and signature steps that must precede it. This is the same class of defect as the v1.3 feed-pinning ordering bug: the guard is correct and is scheduled after the thing it guards. §4.13 states the pre-exploration checklist as a single gate and §6 now runs in that order.
4. **Symbol holdout status made visible (§3.5).** The state table records the **period** holdout only. §4.10.2 and ratified item 17 also require a **symbol** subset selected and hashed *before capture began*. If it exists, its identity/hash belongs in the state table alongside the period dates; if it does not, that must be recorded now rather than discovered when a hypothesis needs untouched data. §4.10.4's embargo predicate already assumes both.
5. **DISC-MDQ-001 generalization limit stated up front (§4.10.4).** Enrichment operates on `DISC candidates ∩ 50-symbol MDQ universe` — 22 base ETFs plus 28 mechanically selected top-ADV names. That intersection is small and liquidity-biased by construction, and ETFs do not carry oversold-quality-pullback semantics the way single names do. Findings from it do not generalize to the DISC universe. Better stated as a known limit before the work than discovered in a result.
6. **Value-extraction priority order marked as overtaken (§4.10, §4.10.3).** v0.10 change 4 makes CEE first because `MOM-SIP-0` is structurally NOT EVALUABLE, but §4.10 and §4.10.3 still read `MOM-SIP-0` → CEE. Marked in place so a reader of §4.10.3 does not start a closed workstream. The ratified order in §8 item 18 is untouched; only its application to the current population changes.
7. **§4.12 sequencing confirmation requested.** §4.12 requires steps 1–4 (definitions frozen → scheduler patched → image rebuilt/container recreated → program-start record re-stamped on **both** identities) to complete *before* any capture starts the clock. D0's 395/395 completeness implies the fixed-rate scheduler was live, but the plan should state explicitly that step 4 — the §6 image/container stamp, not just the git blobs — was completed before D0. That statement is what makes D0 auditable later.
8. **§8 status paragraph gap.** The v0.10 status enumeration accounts for items 1–6 and 9–19 but silently omits **items 7 (plan location) and 8 (GAPPER/MR-002 coupling)**, both still open. Restored. New item **20** added for the K5 discrimination question.
9. **Stale-state fixes.** §2 gate-table header date (2026-08-18 → 2026-08-20); §3.1's "draft PR #634" framing and its "uncommitted modifications in the main working tree … the PR branch is the source of truth" sentence, both contradicted by the merge and by §3.1's own v0.9 paragraph; §3.1's `collector.py` description, which still shows no fixed-rate scheduling after the §4.12 correction created a new collector identity; Track 1 §1.4 ("first governed session runs 2026-08-18", "in flight"); Track 3 §3.1's MOM-SIP-0 row; and §11, which had no v0.10 entry.

## Change summary — v0.10 (single-current-version consolidation + D0 / 2026-08-20 state sync)

**Authority note.** v0.10 is the **only current implementation plan**. v0.8 and v0.9 remain historical snapshots and must not receive further state updates. This revision carries forward all v0.9 substance, incorporates the later 2026-08-19/20 governed state, and records the DISC-001 × MDQ integration direction without changing any frozen DISC-001 family gate or MDQ K-criterion.

1. **D0 established.** The first admissible governed frozen MDQ partition is **2026-08-19**. Adjudication returned **ADMISSIBLE / exit 0**, zero non-passing conditions, both feeds 395/395, completeness 1.000, max contiguous gap 1.0 minute. The review window is **[2026-08-19, 2026-10-18)** and the period holdout is **[2026-10-06, 2026-10-18)** (October 6–17 inclusive). The effective Program Start Record v0.2 is in Git; the pre-start v0.1 draft remains byte-preserved.
2. **2026-08-18 remains a non-event.** No governed partition exists for that date. It neither starts the clock nor contributes evidence.
3. **K5 timestamp interpretation frozen as R2 before coverage was computed.** Match = latest governed quote snapshot at-or-before the reference timestamp, with `0 <= ref_ts - cycle_ts <= 5s`. `cycle_ts - quote_ts` remains a quote-freshness diagnostic, not the K5 matching tolerance. Subsequent observations (~54.7% fill / 65.8% submit / 66.7% decision match rates) are measurements, not inputs to the ruling. The exclusion of unmatched fills from the K5 ratio is recorded as a potential discriminating-power weakness; no threshold or denominator is retuned.
4. **MOM-SIP-0 structurally NOT EVALUABLE in the current window.** MOM-001 is archived/IDLE with only nine historical orders and no viable current population. **CEE becomes the first value-extraction workstream**; its population is viable. This changes sequencing, not MDQ criteria or strategy behavior.
5. **DISC-001 × MDQ integration is authorized as a governed enrichment experiment, not a gate rewrite.** Build an MDQ sidecar/observation layer over existing DISC candidates. Preserve `DISC-001-WATCHLIST / v0.3.0` eligibility rules. Test incremental microstructure value first—GAP opening confirmation, MOM-NEAR liquidity/confirmation, OVERSOLD reversal confirmation, SIP/IEX quote-quality divergence, spread/depth/freshness and VWAP/participation features—before considering any future versioned ranking or admission change.
6. **Holdout enforcement moves to the read boundary.** Any MDQ-derived DISC exploration must apply the symbol/date embargo **before opening MDQ corpus data**, not read-then-filter. Current non-MDQ DISC inputs (Sharadar/Factor Store/GAP) remain unaffected. Phase-A enrichment is observational on `DISC candidates ∩ MDQ eligible universe`; candidates outside the 50-symbol MDQ universe remain valid and simply have MDQ enrichment unavailable.
7. **Producer identity re-recorded, not re-latched.** The approved five collector blobs remain byte-identical while the deployment commit label moved to `9e5cf65`; the approved identity tuple remains governed by the collector-identity artifact. No behavioral identity change is inferred from a commit label alone.
8. **Shared-disk coupling is now an explicit capture-availability risk.** The 2026-08-20 09:03 ET preflight found 9.21 GB free against the 10 GB floor after the prior redeploy added a 1.43 GB image plus ~3.19 GB build cache. `docker builder prune -f` reclaimed ~3.159 GB without deleting images/containers and restored 12.37 GB free; the 09:25 sampler then started cleanly. EBS volume `vol-0457fe650ba7fd66a` has been expanded **30 → 60 GB**; filesystem growth is the remaining completion step after the 16:45 ET freeze.
9. **D0+1 capture healthy at the morning checkpoint.** 33/33 scheduled cycles per feed at 09:57 ET, 1,650 rows per feed, no alerts, identity latch verified, 395-cycle grid intact.
10. **Governance custody.** `docs/design/MDQ-001_Rulings_2026-08-20.md` records the K5 R2 ruling, MOM-SIP-0 disposition and producer-identity treatment. It should enter Git as a Tier-0 documentation change before exploratory/value-extraction work begins. The unresolved `>=2 evaluable and exactly 1 PASS` verdict row remains separate unless/until explicitly signed.

---

## Change summary — v0.9 (deployment state sync, 2026-08-18)

**Scope note.** State sync only, in the v0.6 mould: no review pass is consumed, no settled substance is reopened, and no new scope is added. What moved is *state* — G0 and G2 both closed on 2026-08-17, and the Phase-A collector is deployed and governed-scheduled on `ec2-paper`. v0.8 described a plan in which "nothing is deployed"; that sentence is now false, and a stale gate table is the kind of thing an operator reads under pressure.

1. **G0 CLOSED.** The merge chain completed on the night of 2026-08-17: **#634 `63c0c52`** (collector + signed §8 / ratified §8.1 registration + frozen universe + holdout + feed-pinning guard script) → **#636 `be4235d`** (guard wired into `ci.yml`, verified present at `.github/workflows/ci.yml:368–370` on `main`) → **#637 `0273012`** (GAPPER v2.1.1 approval record into Git custody). Track 0 §0.2 and §0.4 are both discharged.
2. **G2 CLOSED.** The §8 sign-off was executed and recorded on the branch, and §8.1 was ratified in full: two-way evidence firewall; discovery ledger + holdout accepted as materialized; **GO floor = ≥2 of K1–K6 both evaluable AND PASS, else HOLD with a stated extension**; §4.10.3 sequencing approved. The CI-wiring precondition is satisfied by #636. The registration document, not this plan, is the canonical text of every ratified value.
3. **Governed deployment EXECUTED** (2026-08-17 ~19:25–19:40 ET, post-close). Capture root provisioned on the persistent volume; schedule is **systemd timers, ET-explicit** (`OnCalendar=Mon..Fri 09:25 | 16:30 | 16:45 America/New_York`) rather than cron, with `Persistent=true`; a fail-closed wrapper enforces the universe-hash pin, the free-space floor and a single-sampler check; the freeze path is freeze → verify → S3 byte-mirror to a prefix the instance role can **PUT but not DELETE**. Failure alerting is wired to a log plus a CloudWatch metric; **no alarm is wired on that metric yet — owner follow-up.** The units and the wrapper live only on the box, not in Git; committing them is an owner decision.
4. **⚠ The first scheduled governed capture (2026-08-18) DID NOT RUN** — the wrapper's free-space guard rejected it, correctly, at 09:25:02 EDT; 0 of ~59 cycles captured, no partition exists, the clock has not started. See **§3.4**. The operative blocker is now G3's start condition, not a sign-off. Nothing in this plan advances until the **first admissible governed frozen partition** exists. Program start is defined — and must be recorded — as *that event*: not the deployment time, and not the first write. First scheduled fire was Tue **2026-08-18 09:25 EDT**; the first freeze is due 16:45 EDT the same day.
5. **New §6 "Today — 2026-08-18" block** replacing the discharged 2026-08-17 block, and §5 Track 0 / Track 1 statuses updated to match. Track 1 §1.5 is restated: the first thing the calculators need is not a K-calculator at all but a mechanical **admissibility** check, because `verify` proves integrity and §7.1 requires sufficiency.
6. **Stale-fact fixes.** §3.1's "Nothing is deployed" and §2's "G2 … now the operative blocker" are corrected; §4.11's worst-case enumeration said "a 60-day 14-symbol capture" — **14 was the pre-registration smoke universe; the frozen Phase-A universe is 50 symbols** (22 base ETFs + 28 mechanical top-ADV). The correction does not change §4.11's conclusion, only its arithmetic premise.

7. **Governed-text correction set applied (new §4.12).** Reviewing the governed text on the day the capture did not run surfaced four defects, and the owner ruled on all four the same day: the `expected_cycles` denominator, the stale "ANY K" sentence, an undefined verdict case, and the holdout boundary/embargo arithmetic. Three are consistency corrections; **one adds a disposition and is not yet signed.** The controlling text is the registration document (§8.2); §4.12 records the rulings' existence, their consequence for this plan, and the corrected sequencing.

**Unchanged:** the economic priority ordering, Track 3A scope and its firewall, the L0/L1/L2 discipline, the reserve queue, G4–G10, the two-review-max budget (spent), and every prohibition in §10.

---

## Change summary — v0.8 (value-extraction guardrails + state sync, 2026-08-17)

**Scope note.** v0.7 opened a genuinely new surface (§4.10 / Track 3A / Track 6A — exploratory work against the same frozen corpus MDQ-001 will adjudicate on). v0.8 does not re-review v0.3–v0.7 substance and consumes no review budget; it adds the guardrails that the *new* v0.7 scope requires, plus stale-state fixes. The economic priority ordering, the strategy queue, the gate chain, and all L0/L1/L2 discipline are **unchanged**.

1. **Evidence firewall between value-extraction and MDQ adjudication (new §4.10.1).** v0.7 correctly states exploration cannot authorize *behavior*. It does not close the reverse direction: exploratory work on the SIP corpus must not inform the K-criteria, their thresholds, their match rules, or the verdict. v0.8 adds an explicit two-way firewall — value-extraction outputs are **inadmissible** to K1–K6 (§7.2), and no K definition may be revised once exploration begins.
2. **Discovery ledger + untouched holdout for DISC-001 and the feature library (new §4.10.2).** v0.7's ~11-feature library and multi-family candidate screens can generate hundreds of comparisons; "graduates via a prospectively frozen hypothesis" does not prevent a hypothesis that was actually *found* by search from being registered as though it were prior. v0.8 requires a **discovery ledger** (every condition examined, dated, with disposition) that pre-registrations must cite, and a **holdout reserve** — a period and symbol subset quarantined from exploration at G2 — so a graduating hypothesis has genuinely untouched data. This is the failure mode opposite to GAPPER v1's: not a frozen design that could not answer, but an unfrozen search that always finds something.
3. **Verdict-reachability check added to the §8 sign-off (new §4.11, §8 item 2).** Counting the current evaluability clauses: K2 is NOT EVALUABLE unless G10 opens; K4 may be NOT EVALUABLE if Stage 0 slips (§8.8); K5 is NOT EVALUABLE below `N_min`; K6 may be NOT EVALUABLE without a captured occurrence; and if item 14 resolves as "MDQ corpus only," **K1's predeclared-defect correction may have no in-corpus instance either**. The worst case leaves **GO resting on K3 alone**. That may be an acceptable decision — but it must be a decision made at sign-off, not discovered at G3. §4.11 requires enumerating the worst case and confirming GO is still reachable before evidence accrues.
4. **Value-extraction sequencing (§4.10.3).** §1.3 item 5 says stop low-value work, but §4.10's default authorization opens five workstreams at once for a single operator. v0.8 sequences them: `MOM-SIP-0` and CEE first (they feed K5 and the P1 MOM-001 L1 path directly), with DISC-001 / `RANGE-SIP-OBS-001` / the broader feature library gated on those producing an output or on an explicit owner time-box.
5. **Non-equivalence test made concrete (§3A.2, Track 6 D).** "Only a *new* economic mechanism may graduate" and "prove it is not RNG relabeled" are labels without a test. v0.8 specifies one: signal-level correlation against the rejected predecessor on overlapping history, a materially different reject condition, and a stated economic mechanism that does not reduce to the rejected one — all frozen in the pre-registration.
6. **Track 3A/6A placed under ADR 0051 (§3A.0).** All value-extraction programs are Research/Analytics plane, hold no execution authority, and emit governed artifacts carrying the standard envelope — including **feed identity**. A candidate list without provenance is exactly what the feed-pinning rule exists to prevent.
7. **PIT/survivorship discipline stated once for DISC-001 (§3A.3).** v0.7 names PIT universe eligibility for the oversold family only; the emerging-momentum family needs it equally, or the candidate history is survivorship-biased from day one.
8. **§10 extended** with the v0.7-era non-authorizations (value-extraction output entering MDQ adjudication; DISC-001 output reaching the order path; registering an exploration-derived hypothesis without ledger disclosure).
9. **Stale-state fixes:** §2 gate-table header date (2026-08-15 → 2026-08-17); PR #634 commit count (5 → 6) in §2 G0 and Track 0 §0.3, matching §3.1; §4 preamble status updated for commit `1c7e318`; §6 execution-order headings relabeled now that Monday 2026-08-17 is the current day.

## Change summary — v0.7 (owner-directed value-extraction revision, 2026-08-17)

This revision is owner-directed and **does not reopen governance substance settled at v0.3–v0.6**. Its purpose is to correct the plan's emphasis: Algo Trader Plus is not being qualified as an end in itself. The Workbench exists to create strategies that demonstrate platform value and, after appropriate validation/promotion, generate profit. Research, qualification, and evidence controls remain mandatory because they protect that outcome; they are not the outcome.

1. **Platform outcome made explicit (§1.3):** success is measured by conversion of data capability into better execution, stronger validated strategies, new independent strategy candidates, and ultimately net-of-cost paper/live performance — not by the number of research artifacts produced.
2. **ATP value-extraction program added (§4.10 / Track 3A):** after G2, frozen SIP/IEX observations may be used immediately for observation-only strategy enhancement work: MOM-SIP execution sensitivity, CEE implementation shortfall, range-level measurement, candidate discovery, and SIP feature generation. No behavior changes occur without L1/L2 approval.
3. **MOM-001 gets the first profitability enhancement path:** preserve its validated PIT alpha/ranking initially and test SIP as an L1 execution/eligibility overlay — spread, freshness, consolidated liquidity, timing, decision-price quality. A later SIP-native momentum hypothesis must be a **new mechanism** (`MOM-LIQ-001` / `MOM-CAND-001`), not a relabeled reopening of rejected MOM-002.
4. **Range work reframed:** the rejected RNG path is not reopened. `RANGE-SIP-OBS-001` measures whether SIP/auction/VWAP/opening-range observations materially improve daily level estimation and execution quality. Only a prospectively registered **new economic mechanism** may graduate from that evidence.
5. **Opportunity-discovery layer added (`DISC-001`):** daily candidate generation for oversold/reversal and emerging-momentum conditions (e.g. RSI<30, RVOL, relative-strength acceleration, distance to highs, SIP spread/freshness/participation). Candidate ≠ signal; any profitable-looking condition must become a frozen hypothesis before backtest/paper promotion.
6. **RANK use narrowed and improved:** closed RANK-001 is not resurrected. SIP-derived liquidity/capacity/implementation-shortfall measures may support downstream execution/portfolio construction and candidate ranking. They may enter a future strategy-utility rank only after a prospective hypothesis proves predictive utility.
7. **New profit-oriented strategy queue added (Track 6A):** prioritize `MOM-LIQ-001`, `GAPPER-SIP`, `MOM-CAND-001`, then independent short-horizon reversal (`RSI-REV-001`), SIP continuation/reversion, and later OPRA risk overlays. Each must have a mechanism, falsification condition, cost model, and path to paper trading.
8. **Value conversion discipline added:** observational/research work must state what decision it can improve and its conversion gate. No indefinite “interesting research” lane; work either advances a strategy/execution decision, establishes a platform capability required by one, or stops.
9. **§8 item 15 added:** owner sign-off may authorize the observation-only ATP Value-Extraction scope during the 60-day MDQ period so the subscription is being exploited for strategy value while qualification evidence accrues. This does not authorize behavioral migration or strategy code before existing gates.

## Change summary — v0.6 (state sync, 2026-08-17)

Owner-directed synchronization of this plan with `AlgoTraderPlus_Data_Inventory_Report_v1_1_2026-08-17.md` and the sealed 2026-08-17 evidence. Like v0.4, this is a **state sync, not a review pass** — the two-review-max budget recorded at v0.4 §11 remains spent, and no governance substance settled at v0.3–v0.5 changes. One new §8 decision is added because the 08-17 events created it (item 14).

1. **G1 / P-2 CLOSED — real-time SIP confirmed on account 7 during RTH (2026-08-17).** The original box proof (`v13_sip_entitlement_proof.py`) is **preserved as a mechanical FAIL** (evidence sealed 0444, sha `c7b9371d…`): its frozen worst-quote-age ≤5s rule across all symbols conflated UUP quote-update sparsity with feed delay. The owner adjudicated the run **criterion-invalid for sparse instruments, not feed-invalid**, and authorized a versioned re-run. `v13_sip_entitlement_proof_v2.py` (staged sha-exact `959c5399…`, 0444) froze the entitlement decision on actual latency discriminators — R1 liquid controls (SPY/GLD) sub-second on `sip` ∧ R2 simultaneous `delayed_sip` control showing the ~900s signature ∧ R3 current-window SIP bars ∧ R4 credential entitlement asymmetry (`5b6f39e5198d` succeeds; others denied) — and returned **REAL-TIME SIP CONFIRMED** (evidence sealed, sha `67c400d3…`). §2, §5 Track 1, §6, and §8 updated accordingly.
2. **Qualification lesson recorded (inventory report v1.1 §1.2): real-time feed ≠ continuously updating symbol.** Entitlement/latency proofs must use liquid controls plus a delayed-feed contrast; sparse-symbol quote age (UUP/KMLM) is an execution-quality diagnostic and never a latency discriminator. This is now the standing pattern for any future feed-tier proof and bears directly on §4.8 (K6).
3. **Collector VALIDATED (owner disposition 2026-08-17).** An end-to-end laptop smoke (throwaway scratchpad store, deleted after; REST-only, no websocket) exercised the identity latch live against `PA3BGKRLH2AP`, paired IEX/SIP capture under a single `cycle_ts`, freeze with full provenance manifest, refusal of writes to a frozen partition (`FrozenPartitionError`), and detection of a one-byte tamper by `verify`. Owner disposition: **utility VALIDATED / READY FOR GOVERNED DEPLOYMENT GATES**; production capture remains blocked on §8 sign-off + CI feed-pinning guard (G2 preconditions unchanged); **consumer cutover remains NOT AUTHORIZED** pending the Track-4 ADR (G7) — explicitly reaffirmed.
4. **PR #634 is now 6 commits, 16 tests green** — commit 6 (`1c7e318`, 2026-08-16) landed the v0.5 §4 items in the registration draft (review-clock re-anchor, K5 `N_min`, K6 evaluability choice, completeness/admissibility, free-space floor, `identity.py` payload discipline).
5. **The account-7 program closed its P0 chain on SIP** (P0-B2/C/D/F sealed 2026-08-17; executor v7 sole runnable; SIP quote plane bound via limits v5). Sealed evidence now exists that the subscription corrects a gate-material IEX observation defect: **GLD's stub-spread failure mode is absent on SIP** (sub-bp median half-spread, zero >25 bps observations in the qualifying runs), **KMLM sparsity materially improved**, and **UUP improved versus IEX but remains structurally sparse and time-of-day dependent** — an open execution risk carried by the live fail-closed Stage-B gate, with a fresh in-window (10:00–10:30 ET) CA diagnostic as the account-7 pre-manifest gate (earliest Tue 2026-08-18). That program governs itself; this plan's §4.6 subordination constraint is unchanged.
6. **New §8 item 14 — cross-program evidence admissibility.** The sealed account-7 diagnostics are precisely the "correction of a predeclared gate-material IEX observation defect" that K1 names (Strategy Proposals v1.4.1 §4), and a measured IEX-occurrence-plus-SIP-comparison instance relevant to K6 — but they precede MDQ registration and belong to a different governed program. §8 must decide whether they are admissible toward K1/K6 as referenced sealed evidence, or whether the MDQ verdict rests solely on MDQ's own governed corpus (this plan's default), with the account-7 records cited as context only.
7. **G2 is now the operative blocker.** Remaining sequence (inventory report v1.1 §3.1): §8 owner sign-off → CI-enforced feed-pinning guard → box deployment → first admissible governed capture (which starts the 60-day G3 clock, per the v0.5 re-anchor) → K1–K6 keep/cancel review. The subscription-economics distinction from inventory §3.5 applies: operational usefulness is already evidenced by the account-7 program; **permanent retention at $99/month remains the K1–K6 decision**.

## Change summary — v0.5 (substantive revision, 2026-08-15)

**Review-budget note.** v0.4 §11 records that the v0.4 pass was the second review of this plan series, so under the two-review-max discipline this is not filed as a third review pass. v0.5 is a **substantive revision**: every change below either adds a *new* evaluability/admissibility constraint or corrects a statement that is internally inconsistent — none re-litigates governance substance already settled at v0.3/v0.4. The L0/L1/L2 migration model, archive/live-cache separation, G10, durability policy, gate chain, queue order, and reserve sequencing are **unchanged**.

Substantive changes:

1. **K6 evaluability is now an explicit §8 item (new §4.8).** K6 (quote fidelity, added in Strategy Proposals v1.4) requires at least one observed IEX stub-quote occurrence to measure against. The built Phase-A collector samples *latest quotes* at a 60-second cadence; a transient stub quote can appear and clear between samples. K6 must therefore either carry a **NOT EVALUABLE unless observed** clause (mirroring K2's treatment) or draw its IEX-side occurrence evidence from the live executor's spread-gate rejection log — which is where the 2026-08-14 GLD incident was actually detected. v0.4 listed K6 among the buildable Phase-A calculators without noting this.
2. **K5 gains a minimum-population floor (§4.3).** With MR-002 on HOLD and GAPPER Stage 0 not executing, the paper-fill denominator over the review window may be very small. A "≥90% of paper fills" criterion computed over a handful of fills is noise, not evidence. §8 must freeze a minimum fill count below which K5 is **NOT EVALUABLE**.
3. **Partition completeness added to admissibility (new §4.9, §7.1).** `verify` re-hashes manifested files — it proves *integrity*, not *sufficiency*. At 60-second cadence, the abort-after-30-consecutive-failures rule permits a ~30-minute hole in a partition that still freezes and still passes `verify`. This is the GAPPER v1 failure mode in a new costume (records present, contrast absent). Admissibility now requires observed-cycle count within a frozen tolerance of expected.
4. **Shared-host resource protection (new §4.9).** The capture root sits on the same AWS persistent volume as the live execution backend and the SQLite trading book. §4.6's "resource ceiling" had no disk floor or abort. v0.5 requires a free-space floor, a pre-write check, and an abort-and-alert rule — and notes that capture-induced degradation of the execution backend is exactly ADR 0051's first Phase-2 trigger, i.e. evidence to record, not something to push through.
5. **Review-date anchor corrected (§2 G3, §8).** The ~2026-10-14 target counts from the entitlement date, but no *admissible* evidence exists before G2 sign-off and first governed capture. Any pre-deployment slip therefore silently shortens the evidence window while the verdict date stays fixed. The 60-day clock is re-anchored to the **first admissible governed capture**, frozen at G2.
6. **CI wiring reclassified (§0.2, §6).** v0.4 correctly unblocked PR #634 from the CI-wiring PR, but then called the guard "not a deployment blocker." That leaves the feed-pinning guard as a script nobody runs. v0.5 keeps the two PRs separate (owner's ruling intact) and makes the CI-wiring PR a **precondition of G2 deployment**, not of the #634 merge — mechanism over convention, per Strategy Proposals v1.4 §3.4.
7. **`identity.py` payload discipline (§3.1, §4.5).** The pinned `/v2/account` call returns execution-plane state (equity, buying power) alongside the broker ID. The check must assert the fingerprint/broker identity and **discard the rest** — no account balances persisted into the research archive. Also cites ADR 0051's two-state rule explicitly, so the in-process credential is read as conformant rather than as a boundary violation.
8. **Terminology precision (header, §1.1).** "MDQ-001 does not authenticate" → the *collector* authenticates; the *calculators* do not.
9. **G4 row reworded (§2).** v0.4's "OPEN — MR-002 remains HOLD" implies the MR-002 hold is the blocker; whether Stage 0 is coupled to that hold is itself the open ruling. Added as §8 item 8.

## Change summary — v0.4 (state sync, 2026-08-15 late day)

v0.3's governance substance is unchanged. This revision synchronizes the plan with the repository state it was written slightly behind, and records which v0.3 §4 corrections are now **implemented** rather than pending:

1. **G0 largely complete — draft PR #634 is OPEN** on `research/mdq001-phase-a` (built from `origin/main`, 5 logically separate commits). v0.3 described the working set as uncommitted; that was stale at writing time. Remaining G0 work: review/merge (0.4) and the separate CI-wiring PR (0.2).
2. **§4.1 bar-window mismatch RESOLVED IN CODE**: the collector captures **04:00–16:00 ET** (the recommended option) — committed in PR #634. It is no longer a blocking decision; §8 sign-off simply ratifies it.
3. **§4.2/§4.3/§4.4/§4.7 APPLIED to the registration draft** (PR #634 commit `85ef245`): K3 union-grid metric keyed `(symbol, session_date, minute_ts)` with the divide-by-zero guard; K5 population/matching freeze fields; K2 NOT-EVALUABLE-unless-G10 language including "cannot itself satisfy GO"; admissible/inadmissible corpus rules (§7 of this plan); §6.4 durability policy with the S3 byte-for-byte mirror recommendation. The registration draft is now the canonical location of these definitions; this plan's §4 is the record of why they exist.
4. **§4.5 invariant IMPLEMENTED structurally**: a pytest invariant in the PR forbids mutating HTTP verbs, any `/v2/` endpoint other than `/v2/account`, `alpaca.trading` imports, and any `app.*` import outside the capture package. (The extension to the untracked ADR-0051 check script remains in the local working tree — that script ships with the ADR-0051 workstream, not with #634.)
5. **Sampler resilience implemented** (the §4.6 retry-policy item): per-feed error isolation (a transient SIP failure no longer loses the IEX observation; failures persist as auditable `feed_error` records) and continue-on-transient with abort after 30 consecutive fully-failed cycles (proposed default; frozen at §8). Test count is now **15**, all green.
6. **Track 0 ordering corrected**: v0.3 made CI wiring (§0.2) a prerequisite of the PR (§0.3). That contradicted the owner's prior ruling ("don't mix an unrelated CI reconstruction into the collector implementation") and the PR is already open. CI wiring is now a **separate small PR**, not a blocker.
7. **Document-location decision added to §8**: this plan series lives in `docs/Strategies/` while the hybrid-docs rule places governing implementation plans in `docs/implementation/` (Git-reviewable). Decide at v1.0 freeze. The superseded v0.1 file in `docs/implementation/` has been deleted.

## Change summary — v0.3 (retained)

That revision carried forward the v0.2 implementation-state and architecture corrections and added an explicit six-step, per-strategy SIP behavioral-migration model. The governing strategy queue and gate discipline remain unchanged.

1. **Current state corrected:** the Phase-A collector, immutable store, identity latch, CLI, tests, A1 feed work, guard, and registration draft are a sizeable **uncommitted working set** on the current branch. v0.1 incorrectly treated PR #634 as already merged. *(v0.4 sync: stale — PR #634 was already open when v0.3 was written; see v0.4 change 1.)*
2. **Option 2A made explicit:** account 7 is acquisition-only; MDQ calculators read frozen local partitions and receive no Alpaca credential.
3. **Research archive and live cache separated:** the immutable `mdq_capture` archive is not the future real-time application bus. Any "all apps use local data" migration must introduce/define a separate live local observation cache/read contract. The three concepts remain distinct: PIT spine, immutable SIP/OPRA research archive, live/paper cache.
4. **Phase-A timing inconsistency surfaced:** the built bar capture is described as 04:00–20:00 ET, while the intended cron runs EOD at 16:30 and freezes at 16:45. That cannot freeze a complete 20:00 partition. Default recommendation: Phase A captures **04:00–16:00 ET** bars (premarket + RTH), matching the registered census need; otherwise move EOD/freeze after 20:00 before deployment. *(v0.4 sync: resolved — 04:00–16:00 is committed in PR #634.)*
5. **Pre-registration smoke quarantined:** the Friday 14-symbol smoke remains implementation evidence only. Its 4,818 IEX vs 7,057 SIP bar counts (~46.5% more SIP rows) must not enter K1–K6 adjudication.
6. **K3 made reproducible:** use a frozen union-grid missingness definition; raw row-count uplift is diagnostic, not itself K3.
7. **K2 evaluability made a sign-off item:** Phase A is REST-only, while K2 requires 20 consecutive sessions at ≥250 symbols. K2 must be marked **NOT EVALUABLE unless a separate Phase-B streaming authorization is opened within the MDQ window**; it must not silently become a failed criterion.
8. **K5 denominator/timestamp policy added to §8 freeze:** define which paper fills count and the maximum quote-to-submission matching tolerance before evidence starts.
9. **Research-plane broker-capability invariant strengthened:** `identity.py` may perform the pinned read-only `/v2/account` identity check, but research capture code must structurally reject order/trading endpoints and generic broker mutation helpers.
10. **P2 sequencing tightened:** the SF1 NO-START census remains next after GAPPER under the governing queue. Starting it earlier requires an explicit owner sequencing exception; it is not implicitly authorized merely because it writes no strategy code.
11. **Durability separated from immutability:** SHA-256/manifest freeze proves integrity, not survival of the local volume. A post-freeze backup/mirror policy must be recorded before relying on the archive as the sole 60-day evidence corpus.
12. **Per-strategy SIP adoption made explicit:** installing the common local SIP observation layer changes no strategy behavior by itself. Each paper/live program must first run a sensitivity/shadow comparison, receive an explicit L0/L1/L2 SIP-authority classification and owner/program approval, then migrate individually with rollback and feed identity preserved end-to-end.

---

## 1. Why this plan exists

v1.4.1 defines a parallel market-data qualification track, an existing strategy/research queue, observation upgrades, and five reserve proposals. The main implementation risk is **sequencing error**:

- allowing entitlement to alter governed behavior implicitly;
- letting MDQ contend with account 7 execution;
- using pre-registration observations as verdict evidence;
- turning the immutable research archive into an undocumented live data source;
- starting strategy code before its pre-registration/data gate;
- or delaying clearly authorized platform work because a separate research gate is closed.

This plan states what is buildable now, what is already built, what is blocked, and exactly what unlocks each next step.

### 1.1 Governing data flow

```text
                 Workbench account 7
        ALPACA_PAPER_6 / PA3BGKRLH2AP
                       |
             explicit SIP / IEX REST
                       |
              Phase-A collector
       (research plane; acquisition only)
                       |
          +------------+-------------+
          |                          |
          v                          v
  current-session writes       EOD bar capture
          |                          |
          +------------+-------------+
                       |
           immutable capture archive
   <root>/{sip,iex}/YYYY-MM-DD/{quotes,trades,bars}/
        + manifest.json + per-file SHA-256
                       |
                 freeze + verify
                       |
                 READ ONLY
                       |
            MDQ-001 calculators
             K1/K3/K5/K6
```

**Invariant:** MDQ **analysis/calculators** do not authenticate to Alpaca; the **Phase-A collector is the sole authenticating component**, and only for pinned read-only identity and explicit-feed market-data endpoints (§4.5). The capture package is the designated writer. Frozen partitions are read-only inputs bound by manifest/hash identity.

### 1.2 Archive ≠ live local cache

The platform must preserve three distinct data concepts:

1. **PIT research spine** — Sharadar/FMP/MR-governed stores.
2. **Immutable execution/microstructure archive** — frozen SIP/IEX/OPRA capture partitions used by MDQ/research.
3. **Live/paper observation cache** — current-session SIP streams/recent bars with explicit freshness/staleness semantics.

Track 4 may implement the owner's local-data direction, but **live consumers must not read the immutable archive as if it were the live cache**. The ADR must define the live local cache/service separately and preserve feed identity end-to-end.

### 1.3 Platform outcome objective — strategy value and profit, not research volume

The Workbench's business objective is to produce **robust strategies that can survive governed paper validation and, when promoted, generate net profit at acceptable risk**. No plan can guarantee profitability; the implementation objective is to maximize the rate at which defensible ideas are converted into measurable paper/live value while rejecting weak ideas early.

Accordingly, ATP work is evaluated in this order:

1. **Improve already-validated strategy economics first.** Better execution, lower implementation shortfall, fewer false spread/staleness rejects, and better timing can create value without changing the underlying alpha.
2. **Improve opportunity detection second.** Use consolidated market participation, quotes, trades, auctions, VWAP, RVOL and activity measures to find better candidates earlier.
3. **Create genuinely new alpha mechanisms third.** New proposals must be economically distinct from rejected/redundant programs and prospectively registered before strategy backtests that could influence design.
4. **Use portfolio/risk overlays after independent edges exist.** SIP liquidity/capacity and OPRA implied-risk features should first improve sizing, eligibility and event-risk control; they become standalone alpha only if evidence supports that stronger claim.
5. **Stop low-value work.** A research task with no plausible decision, strategy, execution, risk, or promotion consequence does not receive continuing priority merely because the data exists.

For planning purposes, a successful ATP workstream should identify a concrete conversion target such as:

```text
observation → measurable decision improvement → prospective strategy/overlay
            → governed backtest/validation → paper candidate → promotion decision
```

Examples of measurable value include lower implementation shortfall, fewer bad/stale executions, improved net Sharpe/Calmar or drawdown at comparable turnover, incremental alpha independent of existing MOM exposure, stronger candidate hit rate, or a deployable risk filter. **Raw data volume, more features, or more research reports are not success criteria by themselves.**

### 1.4 Cross-program platform boundary — LOW-001 Dynamic PIT *(new at v0.14)*

LOW-001 Dynamic PIT is a **construction/execution-conformance** program. It is not an ATP data-acquisition
program and is not a new alpha study. Its frozen economic path remains:

```text
PIT top-200 universe
    -> valid 252-session realized volatility
    -> lowest quintile
    -> equal weight
    -> weekly rebalance
```

The implementation may reuse common platform services, but those services must stay semantically neutral.
In particular, `app/universe/` may host permanent-identity, ownership, PIT-universe, and later broker-eligibility
components without making `DISC-001`, MDQ, SIP, news, or Opportunity History an input to LOW-001.

**Allowed shared infrastructure:** permanent security identity/lineage · NYSE session calendar · PIT/as-of
metadata · Sharadar security metadata · evidence/hash conventions · broker symbol metadata through the
governed execution layer.

**Forbidden signal coupling:** Candidate Watchlist membership · OVERSOLD/MOM-NEAR/MOM-CORE/GAP family
labels · D1/D5/D10/D20/CURRENT checkpoint outcomes · “Why it left” · DISC-MDQ enrichment · news/SIP
selection · any Opportunity sort/rank/badge.

The reason is governance, not implementation convenience: letting a product/observation surface become a
LOW-001 filter would change the strategy economics and invalidate the claim that Dynamic PIT is merely
restoring the frozen research construction.

**The boundary is bidirectional** *(brought to Watchlist v0.11 form, 2026-08-22; state sync 2026-08-23)*.
The v0.14 text above states only the inbound half. The outbound half is equally binding:

```text
LOW-001 decision records, holdings, rebalance intents, and orders are likewise not Opportunity/DISC
admission, ranking, badge, or sort inputs; and while any strategy operates under an
EVIDENCE_NOT_FEEDBACK observation window, its live decision records are not surfaced as Opportunity
product content -- a product page an operator reads mid-window is a feedback channel.
Factual broker state in the account's own UI is unaffected.
```

⭐ The second clause is the one that is easy to lose: the prohibition is not only about *machine* inputs.
An observation window is contaminated just as thoroughly by a **human** reading the strategy's live
decisions off a product page and acting on them. That is why the carve-out is drawn at *factual broker
state in the account's own UI* — what the operator already owns — and not at "read-only displays," which
would swallow the rule.


---

## 2. Master gate table

| Gate | State (2026-08-20) | Unlocks |
|---|---|---|
| **G0 — working-set stabilization / review** | ✅ **CLOSED 2026-08-17 night** — #634 `63c0c52` → #636 `be4235d` (feed-pinning guard CI-enforced on `main`) → #637 `0273012`. Nothing outstanding. | Merge-ready Phase-A package — *delivered* |
| **G1 — P-2 real-time SIP proof** | ✅ **CLOSED 2026-08-17** — v2 proof `REAL-TIME SIP CONFIRMED` during RTH (v1 preserved as mechanical FAIL; criterion adjudicated invalid for sparse instruments — see v0.6 change 1; sealed evidence `c7b9371d…` / `67c400d3…`) | Final MDQ §8 owner sign-off |
| **G2 — MDQ-001 registration sign-off** | ✅ **CLOSED 2026-08-17 eve** — §8 block signed and §8.1 ratified in full (firewall, ledger + holdout, **GO floor ≥ 2 of K1–K6 evaluable AND PASS**, §4.10.3 sequencing); CI-wiring precondition satisfied by #636. Canonical text = the registration document. | AWS collector deployment (**executed 2026-08-17 night**); governed Phase-A corpus; Tracks 3.1/3.2 observation work — *all unlocked, none started* |
| **G3 — MDQ-001 verdict (GO/HOLD/STOP)** | **ACTIVE — D0 = 2026-08-19.** First admissible governed frozen partition adjudicated ADMISSIBLE/exit 0. Review window **[2026-08-19, 2026-10-18)**; period holdout **2026-10-06 through 2026-10-17 inclusive**. Capture accrues; final K1–K6 verdict remains future. | Permanent SIP adoption path; SCAN-001 SIP migration decision |
| **G4 — GAPPER v2.1.1 §9 sequencing ruling** | ✅ **CLOSED 2026-08-22 — prerequisite satisfied**, not waived. MR-002 Steps 1–2 completed 2026-08-10; its later termination without an economic verdict neither reopens nor invalidates that. Record: `docs/design/Gapper/GAPPER_G4_Sequencing_Gate_Closure_Record_v1.0.md`. ⛔ Closure is narrow — §252, §8.1 and §3 all untouched; no evidence transfers | ~~GAPPER Stage-0 execution~~ — now gated by **data sufficiency** (§8.8) |
| **G5 — GAPPER Stage-0 disposition** | Future | P2 Profitability Acceleration queue step; Reserve C consideration; informs Reserve D |
| **G6 — post-GAPPER/P2 portfolio reassessment** | Future | Reserves A/D and next reserve-program selection |
| **G7 — local live-cache consumer-migration ADR accepted** | OPEN — ADR not yet accepted | Implementation of live consumer cutovers to the local observation layer |
| **G8 — OPRA-CAP-001 corpus maturity** | Future | Reserves B/E pre-registration with defensible option history |
| **G9 — owner pre-registration of a specific reserve strategy** | Per strategy | Code for that reserve strategy only |
| **G10 — Phase-B/K2 authorization** | CLOSED by default | 250/500-symbol streaming reliability implementation and K2 measurement |

**Important:** G10 is intentionally separate from G2. Phase A can proceed without a WebSocket implementation. If G10 never opens during this MDQ cycle, §8 must state K2 = **NOT EVALUABLE**, not FAIL.

---

## 3. Current implementation state

### 3.1 Built, verified, merged and deployed — PR #634 *(heading corrected at v0.11; "draft" has been stale since the 2026-08-17 merge)*

Commits (branch `research/mdq001-phase-a`, base `origin/main`): (1) A1 explicit-feed fixes + feed-pinning guard · (2) MDQ-001 registration draft · (3) `app/research/capture/` + CLI · (4) tests + `.gitignore` · (5) plan-v0.3 corrections (K3/K5/K2 freeze semantics, durability, sampler resilience — `85ef245`) · (6) plan-v0.5 items in the registration draft (`1c7e318`, 2026-08-16). CI wiring was deliberately excluded from #634 and landed in #636. *(v0.11: the sentence that used to follow — "copies of the same files also exist as uncommitted modifications in the main working tree; the PR branch is the source of truth" — was already contradicted by the v0.9 paragraph below and is removed. `main` is the source of truth.)*

**v0.6 status:** the collector is **owner-VALIDATED (2026-08-17 disposition)** following an end-to-end quarantined smoke — live identity latch, paired dual-feed capture under one `cycle_ts`, freeze/manifest provenance, frozen-partition write refusal, and one-byte tamper detection.

**v0.9 status: MERGED AND DEPLOYED.** PR #634 merged as `63c0c52`; the package is on `main` and deployed to `ec2-paper` — see §3.3. The working-tree copies in the laptop checkout are now byte-identical to the `main` blobs and are no longer a separate source of truth.

Package: `apps/backend/app/research/capture/`

- `store.py`
  - partition layout: `<root>/{sip,iex}/YYYY-MM-DD/{quotes,trades,bars}/`;
  - temp-file + atomic replacement before freeze;
  - freeze writes `manifest.json` with provenance and SHA-256 per file;
  - frozen partitions reject later writes;
  - verify re-hashes manifested files and rejects unmanifested stray files;
  - empty partition freeze is rejected.
- `collector.py`
  - REST-only Phase-A primitives;
  - paired SIP/IEX latest-quote sampling;
  - one multi-symbol request per feed per cycle;
  - shared `cycle_ts` for aligned K6 comparison;
  - **per-feed error isolation** — a transient failure on one feed is persisted as an auditable `feed_error` record and never loses the other feed's observation *(added at v0.4)*;
  - **fixed-rate quote sampling against an absolute monotonic deadline** — no burst, no catch-up, close checked before each cycle, `scheduled_slot_ts` / `slot_index` persisted per cycle so observed cycles reproduce against the frozen grid *(the §4.12 correction; the original fixed-delay scheduler drifted to ~383–389 of 395 slots on a healthy feed and would have failed the ratified 98% floor. Applied at v0.11 to the package description — v0.10 recorded the correction in §4.12 but left this bullet describing the defective behavior)*;
  - EOD 1-minute bars on both feeds, **04:00–16:00 ET** (premarket + RTH; §4.1 resolved);
  - explicit feed on every request;
  - bar fields include volume, trade count, and VWAP.
- `identity.py`
  - fail-closed credential fingerprint pin;
  - live read-only `/v2/account` identity check must resolve broker `PA3BGKRLH2AP`;
  - deliberately avoids `alpaca.trading` import;
  - **payload discipline *(added at v0.5)*:** assert the broker/fingerprint identity and discard the remainder of the response — account equity, buying power, and other execution-plane state are never logged or persisted into the research archive.

CLI: `apps/backend/scripts/mdq_collector.py`

- `sample --until-close` (continue on transient failure; abort after `--max-consecutive-failures` fully-failed cycles, default 30 *(added at v0.4)*)
- `eod`
- `freeze` (`--label PRE_REGISTRATION_SMOKE` quarantines pre-registration captures)
- `verify`
- `status`
- root from `WORKBENCH_MDQ_CAPTURE_ROOT`
- frozen universe supplied through `--universe-file`

Verification state *(as of v0.6; **stale at v0.11** — the §4.12 scheduler correction touched five files and created a new collector code identity, so the test count and the identity tuple below both post-date this list. The governing record is the collector-identity artifact and the Program Start Record, not this paragraph.)*:

- **16** unit tests green (incl. the structural HTTP-boundary/order-path-exclusion invariant, per-feed failure isolation, and the `identity.py` payload-discipline locking test added at commit 6);
- ruff/mypy/format clean;
- feed-pinning guard green;
- both research-plane invariant checks green locally;
- live scratchpad smoke: identity latch → dual-feed capture → freeze → hash verify (quarantined, §3.2).

### 3.2 Smoke evidence status

The smoke produced:

- universe: 14 identical symbols;
- IEX 1-minute rows: 4,818;
- SIP 1-minute rows: 7,057;
- raw SIP row uplift vs IEX: ~46.5%.

Disposition:

> **PRE_REGISTRATION_SMOKE — engineering evidence only; inadmissible to K1–K6.**

Do not delete it if it is useful for implementation traceability, but its path/manifest must be impossible to include in the governed MDQ corpus.

---

### 3.3 Deployed state — `ec2-paper`, 2026-08-17 night *(new at v0.9)*

Governed deployment executed post-close on 2026-08-17 (~19:25–19:40 ET), Tier-3 discipline, live stack untouched:

- **Code:** `main` at the merge chain head. ⚠ *Corrected 2026-08-18:* the collector does **not** run from the host checkout — the wrapper invokes `docker exec workbench-backend python scripts/mdq_collector.py`, and **the backend image bakes the source in** (bind mounts are only `bars_cache`, `premarket_gappers`, `data`, `strategies_user`). So a collector change requires an **image rebuild and container recreate** — a **Tier-3 live-stack touch**, not a file copy — and **code identity and running-image identity are two different things**. Both are pinned in the program-start record (§2.3 git blobs, §2.5 mechanics, §6 the image actually serving `docker exec`); checking only the git blobs would not detect a container that was never recreated.
- **Capture root:** provisioned on the persistent volume via `WORKBENCH_MDQ_CAPTURE_ROOT`.
- **Schedule — systemd timers, ET-explicit** (not cron): `mdq-sample` / `mdq-eod` / `mdq-freeze` `.service` + `.timer`, `OnCalendar=Mon..Fri 09:25:00 | 16:30:00 | 16:45:00 America/New_York`, `AccuracySec=10s`, `Persistent=true`, plus `mdq-alert@.service` as the `OnFailure` handler. Timezone is declared in the unit, not inherited — the box host shell is EDT and the container is UTC, and this project has burned four incidents on that difference.
- **Fail-closed wrapper** `/opt/workbench/mdq/mdq_run.sh`: universe-hash pin, free-space floor `max(10 GB, 20%)`, single-sampler check. Refuses rather than degrades.
- **Freeze path:** freeze → `verify` → `aws s3 sync` to the mirror prefix. The instance role can **PUT but not DELETE** there, so the box cannot destroy its own mirrored evidence — the 2026-07-27 volume-destruction incident is the reason that asymmetry exists.
- **Alerting:** `OnFailure` → alert log + a CloudWatch metric. ⚠ **No alarm is wired on that metric yet.** A metric nobody is subscribed to is a record, not an alert — owner follow-up.
- **Custody gap to note:** the unit files and the wrapper exist **only on the box**, not in Git. Whether they are committed is an owner decision; until then the schedule identity is pinned by SHA in the program-start record rather than by version control.

**Nothing has been adjudicated.** Deployment is not program start.

---

### 3.4 First governed capture day — **DID NOT RUN** (2026-08-18) *(new at v0.9)*

**The first scheduled governed capture did not happen. The 60-day clock has not started.**

`mdq-sample.timer` fired on schedule at **09:25:02 EDT (13:25:02Z)**. The wrapper's fail-closed free-space guard rejected the run and the unit exited 1:

```text
Aug 18 09:25:02 mdq_run.sh[3825933]: FREE-SPACE FLOOR BREACH: 9G available < 10G floor (max(10G,20% of 29G))
Aug 18 09:25:02 systemd[1]: mdq-sample.service: Failed with result 'exit-code'.
```

Observed state at 10:24 EDT: **0 cycles captured** against ≈59 expected; no `sip/2026-08-18` or `iex/2026-08-18` partition directory on either feed; capture root empty; S3 mirror empty; the live trading stack unaffected and healthy.

**This is a disk-capacity operational failure, not a collector defect.** Every fail-closed layer behaved correctly: the wrapper refused rather than degraded, `OnFailure` wrote the alert log line, the CloudWatch datapoint published, and `CaptureStore.freeze` would in any case refuse an empty partition. Nothing partial was written and nothing inadmissible can be sealed.

Five findings worth recording, because four of them are design-level rather than incidental:

1. **Shortfall ≈ 0.93 GiB.** 8.07 GiB free against a 10 GiB floor. Reclaimable on the host: ~3.16 GB Docker build cache, ~2.44 GB images including two orphaned backend tags (`rangefix638-20260818`, `rollback-prerangefix638`, 1.43 GB each, 0 containers). ⚠ One of those is a **rollback image**; deleting it is an owner decision, not housekeeping.
2. **§1.3 was not satisfied as written.** The session called for the capture root on *the AWS persistent volume*. In fact `/opt/workbench/data` sits on `/dev/root` — a single 30 GB disk shared with Docker, `/var/log`, a 4.1 GB swapfile and ~1.8 GB of existing research artifacts. **The collector competes for space with the execution backend.** ADR 0051 anticipated exactly this: capture-induced pressure on the shared host is the first Phase-2 trigger. Record it; do not push through it.
3. **The day cannot self-recover.** `Persistent=true` does not help here — systemd recorded `LAST Tue 2026-08-18 09:25:02 EDT` and has satisfied today's `OnCalendar` occurrence; `NEXT` is Wed 2026-08-19 09:25. Freeing disk now does not restart today's sampler.
4. **Today's 16:30 and 16:45 runs will also fail** unless space is freed: the floor check precedes the mode dispatch in the wrapper, so it gates `eod` and `freeze` too. Expect two further `MDQ FAILURE` lines.
5. **The alert had no subscriber.** `describe-alarms-for-metric` on `Workbench/Paper / MdqCollectorFailure` returns `[]`. The metric published correctly and nobody was told — which is why a 09:25 failure was still unnoticed an hour later, on the program's first governed day. §3.3 flagged the missing alarm as a follow-up; it cost a day on day one.

**Disposition: 2026-08-18 is not the first governed capture day.** The earliest possible start is **Wed 2026-08-19**, and only if free space is above the floor before 09:25 EDT. The correct reading of this event is that the guard did its job — a partition captured on a host about to run out of disk is exactly the kind of evidence that fails §7.1 later, expensively.

**Midday update — the day now ends with an inadmissible partition, and the exclusion is pre-committed.** The free-space breach was cleared (build-cache prune + two superseded image tags; 8.1 GB → 12 GB free against a 10 GB floor) and a CloudWatch alarm is now wired on `MdqCollectorFailure`. The **sampler still cannot run today** — systemd has satisfied today's `OnCalendar` occurrence — but `mdq-eod` (16:30 ET) and `mdq-freeze` (16:45 ET) are unblocked and will run, so the corpus will contain a frozen, mirrored `2026-08-18` partition with **valid bars and zero quote cycles**. It is **INADMISSIBLE on §7.1 completeness (0 of 395 expected sampler cycles), not on bar quality**, and is excluded from **K1–K6 in their entirety, K3 specifically included** — which matters because K3's union grid is exactly the 04:00–16:00 ET bar data such a partition contains. The exclusion was **recorded before the freeze and before anyone examined the partition's contents** (owner ruling, 2026-08-18; full text and timestamp in the program-start record §8.2), which makes it a pre-commitment under §4.10.1 rather than a post-hoc judgement — and the S3 mirror prefix is **PUT-only**, so once mirrored the partition cannot be withdrawn and exclusion is the only control that exists. **The clock still has not started.**

**Owner-confirmed disposition — VERBATIM.** Reviewed and confirmed by the owner on 2026-08-18 and transcribed exactly. `INADMISSIBLE — PRESTART / NO GOVERNED QUOTE-SAMPLER CYCLES` is a **status name, not prose**; do not paraphrase or abbreviate it. The controlling copy lives in the program-start record §8.2 and its attempt log:

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

Two general rules travel with it, and they are the load-bearing part:

1. **Completeness is a prerequisite for entry into the K1–K6 corpus; it is not criterion-specific.** Admissibility is adjudicated on the **partition as a whole**, before any criterion is computed. Valid bars plus zero quote cycles ⇒ inadmissible **in its entirety**. This is the standing rule for every partition, not a fact about this one.
2. **No “K3-valid but sampler-incomplete” corpus is being created, and carving one out later is foreclosed.** A second corpus with a laxer entry rule would be weakening the frozen rule **after seeing the data** — exactly the move the pre-commitment exists to prevent. There is one admissible corpus (§7.1), no bars-only annex, and no criterion-specific admissibility.

**Inadmissible ≠ failed criterion.** An excluded partition contributes **nothing** to K1–K6 in **either** direction: it is **not a K3 FAIL**, not evidence against SIP, not evidence for SIP, and it **never** counts toward the keep/cancel denominator. This is the same distinction §4.11's evaluability logic turns on — NOT EVALUABLE leaves the denominator rather than counting as a failure — and getting it wrong in either direction corrupts the verdict.

⚠ **2026-08-19 is not predeclared as the start.** It is the earliest date not yet ruled out. Running the sampler is **not** qualifying — the review and holdout dates stamp only if and when a partition is adjudicated ADMISSIBLE under §7.1. The owner-confirmed *conditional* arithmetic, should 08-19 qualify: `review_start_date = 2026-08-19`, `period_holdout_start = 2026-10-06` (offset 48), `review_end_exclusive = 2026-10-18` ⇒ period holdout **2026-10-06 through 2026-10-17 inclusive**. Worked example, not a value.

---

### 3.5 Program start and current governed state — 2026-08-19/20 *(new at v0.10)*

The first admissible governed frozen partition is **2026-08-19**. This is **D0** and is the only event that starts the 60-calendar-day MDQ review clock.

| Item | Current state |
|---|---|
| D0 | **2026-08-19** |
| Adjudication | **ADMISSIBLE — exit 0; zero non-passing conditions** |
| Quote completeness | iex 395/395; sip 395/395; 1.000 each |
| Max contiguous gap | 1.0 minute |
| Review end exclusive | **2026-10-18** |
| Period holdout | **2026-10-06..2026-10-17 inclusive** |
| Machine-readable period holdout | ⚠ `mdq_phase_a_holdout.json` still says `STAMPED_AT_FIRST_ADMISSIBLE_CAPTURE`. Phase-A derives the governed dates from the frozen rule and records derivation provenance; any future concrete stamp must match exactly or fail closed. |
| Symbol holdout | ✅ **IDENTIFIED** *(state sync 2026-08-20 PM)* — `apps/backend/config/mdq_phase_a_holdout.json`, LF-normalised sha256 **`6c6cf03a80598f54df89b599f2ffbbda09ea44af8f3596421d6c58104e2393bb`**, 850 B, **10 of 50**: AMZN EFA KMLM MSTR NBIS NOW TSLA XLK XLV XOM. Committed **`63c0c52` (2026-08-17, #634)** — **before capture began** (D0 = 2026-08-19), satisfying §8 item 17. **Scope per §4.10.5:** genuine for MDQ-derived hypotheses, structurally void for Sharadar-derived DISC hypotheses. ⚠ It is the artifact's **period** field that is unstamped, not the symbol subset. |
| Period holdout — machine-readable artifact | ⚠ **UNSTAMPED** *(state sync 2026-08-20 PM)* — still carries `"period_holdout_dates": "STAMPED_AT_FIRST_ADMISSIBLE_CAPTURE"`. Phase A derives 2026-10-06..10-17 from the frozen rule, records the provenance, and treats a stamped-but-disagreeing artifact as **fatal**. Stamping is PX-4 and its regression-test update lands in the SAME commit (the test pins the unstamped state and **fails by design** when the stamp is correct). |
| Holdout fixture symbols | ⚠ *(added at v0.13)* — record whether the TSLA/XOM/AMZN rows proving exclusion are the **governed holdout symbols** or arbitrary synthetic fixtures. If arbitrary, add a test binding the reader to the governed holdout artifact; the current proof covers the mechanism, not the wiring. |
| §4.12 sequencing before D0 | ✅ **CONFIRMED** *(state sync 2026-08-20 PM)* — Program Start Record v0.2 §6 stamps running image `sha256:cb4e42cd1481ee9193f0a87bb6793cab6cb29093b6c58fee19efd58995871594`, built `2026-08-18T18:35:36-04:00`, **container created `2026-08-18T22:36:26Z` — 50 s after the build**, evidencing recreation rather than a stale container. Both identities stamped. |
| Program-start record | `docs/design/MDQ-001_ProgramStart_Record_v0_2.md` — EFFECTIVE |
| Collector approval | distinct pre-freeze artifact; approved collector ≠ approved data |
| Current capture state (2026-08-20 morning) | 33/33 cycles per feed at 09:57 ET, no alerts |
| Shared volume | EBS expanded 30→60 GB; filesystem growth pending after the 16:45 ET freeze |

**Operational lesson:** a redeploy is a capture-availability event while Docker/build cache and MDQ capture share one filesystem. Capacity checks therefore belong both before deployment and before the 09:25 collector start.


---

## 4. Pre-deployment corrections and sign-off definitions

These were the changes required before G2 deployment. **Status at v0.8:** 4.1 is resolved in code; 4.2–4.5 and 4.7 were applied to the registration draft at commit `85ef245`; **4.3's `N_min`, 4.8, 4.9, the review-clock re-anchor and the `identity.py` payload discipline were applied at commit `1c7e318` (2026-08-16)**. The registration draft is now the canonical text of all of these definitions; §4 is the record of *why* they exist, and the remaining sign-off acts (4.6, and the **values** in 4.3/4.8/4.9/4.11) are ratified at §8. The subsections are retained as the rationale record.

### 4.1 Resolve the bar-window / freeze mismatch — ✅ RESOLVED (04:00–16:00 ET committed)

Current intended schedule:

```text
09:25 ET   sample --until-close
16:30 ET   eod
16:45 ET   freeze
```

A 16:45 freeze cannot produce a complete 04:00–20:00 ET archive.

**Recommended Phase-A ruling:**

```text
bar session_scope = 04:00–16:00 ET
```

This covers the registered premarket + RTH census while keeping the existing EOD/freeze schedule.

Alternative: if postmarket data is explicitly required, change the operational schedule so EOD/freeze occur after 20:00 ET. Do not deploy with an internally inconsistent scope.

### 4.2 Freeze K3's exact missingness metric — ✅ APPLIED to registration draft

Default proposed metric:

For the frozen qualification universe and period, define the pooled key grid

```text
U = union of (symbol, session_date, minute_ts) keys
    observed by either IEX or SIP
```

For feed `f`:

```text
missing_rate_f =
    1 - observed_keys_f / |U|
```

Then:

```text
K3_reduction =
    (missing_rate_IEX - missing_rate_SIP)
    / missing_rate_IEX
```

K3 passes only if `K3_reduction >= 50%`.

Rules:

- The grid/aggregation method freezes at registration.
- A raw SIP/IEX row-count difference is diagnostic only.
- If `missing_rate_IEX == 0`, K3 is not evaluable on that grid; do not divide by zero or create an artificial pass.
- Do not use the pre-registration smoke to choose or tune the definition.

### 4.3 Freeze K5's evidence population — ✅ APPLIED to registration draft (values freeze at §8)

K5 says spread/mid/shortfall metrics must be produced for ≥90% of paper fills. Before G2, §8 must define:

- which paper account(s)/strategy program(s) are in the denominator;
- whether only fills for symbols in the frozen Phase-A universe count;
- the submission/fill timestamp source of record;
- the permissible SIP quote-match rule (at-or-before/nearest);
- the maximum quote age/tolerance;
- what happens when no valid quote exists.

No matching tolerance may be chosen after seeing coverage.

**Minimum-population floor *(added at v0.5; premise restated 2026-08-22)*.** With MR-002 **terminated without an economic verdict** and GAPPER Stage 0 not executing, the fill denominator over the review window may be very small; "≥90% of paper fills" over a handful of fills measures nothing. §8 must freeze a **minimum admissible fill count `N_min`** (proposed default: **50 fills** across the qualifying programs within the review window). Below `N_min`, K5 is **NOT EVALUABLE** — which, as with K2, is neither FAIL nor a basis for GO. The floor is frozen before evidence accrues, never adjusted after seeing the count.

### 4.4 Resolve K2 evaluability under REST-only Phase A — ✅ APPLIED to registration draft

K2 requires:

```text
>=99.5% session uptime
20 consecutive sessions
>=250 symbols
zero unrecovered gaps
```

The built Phase-A collector has **no WebSocket**, by design.

Recommended registration language:

> **K2 is NOT EVALUABLE in Phase A unless the owner separately opens G10 and authorizes the bounded Phase-B streaming module during the MDQ review window. NOT EVALUABLE is not FAIL and cannot itself satisfy GO.**

If the owner wants K2 evaluated in this cycle, Phase B receives a separate session doc, account-7 non-contention proof, resource ceiling, abort rule, and authorization. It must not be smuggled into Phase A.

### 4.5 Strengthen the no-broker-capability invariant — ✅ IMPLEMENTED (structural pytest invariant in PR #634)

Add/retain an invariant that the research capture package may:

- call the pinned read-only identity endpoint (`GET /v2/account`);
- call explicit-feed market-data endpoints;

and may **not**:

- construct/import an order client;
- POST/PATCH/DELETE to trading/order endpoints;
- expose a generic authenticated broker mutation helper;
- submit/cancel/replace orders;
- import order-path modules.

This keeps the research-plane boundary structural rather than relying on code-review convention.

**ADR 0051 framing *(added at v0.5)*.** Phase A runs in-process on the shared host, so the applicable rule is ADR 0051's **first state**: research-plane *code* holds no execution authority (no order-path imports, no router token, no mutating verbs) — enforced here by the pytest invariant. The stronger *structural incapability* state (no broker credential at all) applies to an independently deployed research runtime, which Phase A is not. The pinned read-only `/v2/account` call is therefore conformant, not an exception — provided the payload discipline in §3.1 holds.

### 4.6 Freeze the Phase-A universe and sampler cadence — ✅ RATIFIED at G2 (2026-08-17); universe frozen by file SHA and deployed under a wrapper-enforced hash pin

At G2 record:

- exact universe file hash;
- quote-sampling cadence;
- session scope;
- REST endpoint/request shape;
- collector code identity;
- credential fingerprint;
- account identity;
- feed identities;
- retry/backoff policy;
- resource ceiling;
- clock/timezone policy.

These become evidence identity, not mutable runtime convenience settings.

### 4.7 Durability policy for frozen partitions — ✅ APPLIED to registration draft (§6.4; choice made at §8)

`manifest.json` + SHA-256 establishes integrity and immutability behavior, but not durability if the local volume fails.

Before the 60-day corpus becomes authoritative, record one of:

1. frozen partitions are mirrored byte-for-byte to an existing governed off-host/object store after local verification; or
2. the owner explicitly accepts local-volume loss risk for this qualification cycle.

A backup copy must preserve the original manifest/file bytes; copying must not rewrite data or provenance.

The mirror is itself verified: re-hash after copy against the original `manifest.json`, and record the mirror location/verification result in the partition's provenance. An unverified copy is not durability.

### 4.8 Resolve K6 evaluability under 60-second REST sampling — ✅ RATIFIED at G2 (2026-08-17): option **(a)**, the NOT-EVALUABLE-unless-observed clause *(new at v0.5)*

K6 (quote fidelity, Strategy Proposals v1.4 §4.3) requires demonstrating that the stub-quote artifact class observed on IEX does not recur in SIP — measured **against at least one observed IEX occurrence**.

The structural problem mirrors K2's:

```text
K6 needs      an observed IEX stub-quote event
Phase A has   latest-quote snapshots at 60s cadence
```

A stub quote is transient; it can appear and clear entirely between two samples. K6 is therefore **not guaranteed evaluable** from Phase-A capture alone, and v0.4 listed it among the buildable Phase-A calculators (§1.4, Track 1.5) without saying so.

Two viable resolutions — **choose one at §8, before evidence accrues**:

1. **Evaluability clause (recommended):** register K6 as **NOT EVALUABLE unless at least one IEX stub-quote occurrence is captured in the admissible corpus**, with the same "NOT EVALUABLE is not FAIL and cannot itself satisfy GO" language already frozen for K2.
2. **Second evidence source:** admit IEX-side occurrences from the **live executor's spread-gate rejection log** — which is where the 2026-08-14 GLD incident was actually detected — as the occurrence trigger, with the SIP-side comparison drawn from the Phase-A capture at the matching `cycle_ts`. This requires freezing the rejection-log schema, the match tolerance, and the admissibility of that log as governed evidence at §8.

Do not resolve this by tightening the sampling cadence after seeing results: cadence is frozen identity (§4.6).

**v0.6 note — a third candidate evidence source now exists.** The account-7 program's sealed 2026-08-17 diagnostics measured the GLD stub-quote class on both feeds simultaneously (IEX artifact present, SIP consolidated book clean at sub-bp half-spreads). That is exactly the occurrence-plus-comparison shape K6 needs — but it predates MDQ registration and belongs to a different governed program, so admitting it is a §8 decision (item 14, cross-program evidence admissibility), not a default. The lesson it encodes (feed latency vs instrument sparsity are separate questions — inventory report v1.1 §1.2) applies to K6's design regardless of the admissibility ruling.

### 4.9 Partition completeness and shared-host resource protection — ✅ RATIFIED at G2 (2026-08-17); the resource floor is additionally **enforced in the deployed wrapper**, not only documented *(new at v0.5)*

**Completeness is not integrity.** `verify` re-hashes manifested files and rejects strays; it proves the bytes are the frozen bytes. It does **not** prove the partition contains the observations it was supposed to contain. With a 60-second cadence and the abort-after-30-consecutive-failed-cycles rule (§4.6), a partition can contain a **~30-minute hole**, freeze normally, and pass `verify` — and a sequence of shorter transient outages leaves smaller holes with no abort at all.

This is the GAPPER v1 failure mode in a new costume: records present, sufficiency absent. Freeze at §8:

```text
expected_cycles   = f(session_scope, cadence, market calendar)
observed_cycles   = admissible non-error observations in the partition
completeness      = observed_cycles / expected_cycles
```

- a **minimum completeness threshold** (proposed default: **≥ 98%** per partition per feed) below which the partition is **inadmissible** (§7.1);
- a **maximum contiguous gap** (proposed default: **10 minutes**) independent of the aggregate rate — an aggregate pass can still hide one long outage;
- `feed_error` records count toward the denominator, never the numerator.

**Shared-host resource protection.** `WORKBENCH_MDQ_CAPTURE_ROOT` sits on the same AWS persistent volume as the live execution backend and the SQLite trading book. §4.6's "resource ceiling" names no disk floor and no abort. Freeze at §8:

- a **free-space floor** (proposed default: the greater of **10 GB** or **20%** of the volume) checked **before each write cycle and before EOD/freeze**;
- **abort-and-alert** on breach — the collector stops; it never writes into the floor;
- a **per-partition size ceiling** consistent with the OPRA-CAP-001 storage budget (Track 2);
- freeze failures alert rather than fail silently (the daily-report watchdog is the existing surface).

Note the governance framing: capture-induced degradation of the execution backend is precisely **ADR 0051's first Phase-2 trigger**. If it occurs, it is trigger evidence to record — not an obstacle to engineer around in place.

### 4.10 ATP value-extraction operating rule — ✅ RATIFIED at G2 (2026-08-17), priority order `MOM-SIP-0` → CEE → feature library → `DISC-001` → `RANGE-SIP-OBS-001`, Phase-A branches only (no auction / tick-trade capture expansion) *(new at v0.7)*

⚠ **Application note *(v0.11)*.** The ratified order stands, but `MOM-SIP-0` is **structurally NOT EVALUABLE** for the current population (MOM-001 archived/IDLE, nine historical orders) — v0.10 change 4. **CEE is therefore the first executable workstream.** This changes which item is actionable, not the ratified sequence: `MOM-SIP-0` reopens if and when a governed population exists. Do not manufacture a sample to satisfy the written order.

The 60-day MDQ qualification window must not become a 60-day period in which ATP data is collected but not tested for platform value. After G2 and the first admissible governed partition, the following **observation-only / offline** work may proceed in parallel against frozen data, subject to §8 item 15:

- `MOM-SIP-0`: quantify whether SIP changes spread/freshness/liquidity/timing/decision-price quality for MOM-001 candidates and paper fills.
- `CEE`: reconstruct SIP midpoint/spread and implementation shortfall for qualifying paper fills.
- `RANGE-SIP-OBS-001`: compare IEX/SIP/auction/VWAP/opening-range measurements for daily level quality; no RNG strategy resurrection or order change.
- `DISC-001`: produce candidate-only oversold and emerging-momentum screens from approved historical/PIT inputs plus frozen SIP microstructure features.
- SIP feature library: derive reusable spread, quote-age, IEX/SIP divergence, trade-count, dollar-volume, VWAP-distance, RVOL, opening-volume-fraction, spread-contraction/expansion, liquidity-shock and participation-persistence features.
- Candidate-ranking experiments: rank **stocks/candidates**, not strategies, using prospectively frozen feature definitions; this does not reopen RANK-001.

Every work item must name:

```text
decision it could improve
baseline
feature/input definition
transaction-cost treatment
falsification / stop condition
what would justify the next governed step
```

An observation can justify a later pre-registration proposal; it cannot silently authorize behavior. Existing strategy behavior remains L0 until the specific L1/L2 approval path in Track 4 is completed.

**Sector-label provenance — a caveat that binds every sector-consuming DISC feature** *(from SEC-001 V3
§5.1b, 2026-08-23; state sync)*:

```text
tickers.sector is a RESTATED, latest-value, Morningstar-taxonomy label with NO PIT semantics -- the
present classification applied backward across each name's entire history. Demonstrated: META reads
"Communication Services" for years in which it was classified Technology.

Every DISC feature consuming sector labels inherits this:
  - sector relative strength / breadth context
  - sector-ETF underlying selection
  - any sector-conditional screen

For exploratory/product use this is tolerable IF DECLARED: the discovery ledger records
sector-derived conditions as computed on RESTATED labels.

At GRADUATION, any sector-derived hypothesis must declare classification provenance and choose
explicitly:
  (a) recompute on the V3 EDGAR effective-dated spine -- permitted shared infrastructure under
      Sec 1.4 (identity/classification, NOT alpha); or
  (b) carry a permanent restated-label caveat in its pre-registration.

Silent inheritance of restated labels into a registered hypothesis is PROHIBITED.
```

⭐⭐ **Why this is the substantive item and not housekeeping.** The leak SEC-001 V3 refused at its front
door can walk in through the **discovery pipeline** instead. V3 declined Disposition 2 precisely because
restated classification is a *directional* leak into a momentum grouping variable (~8.4% measured
boundary-crossing) — but DISC-001 reads the **same** restated `tickers.sector` column, and a
sector-conditional screen that graduates without declaring it would re-import the exact defect V3 paid to
eliminate. ⛔ The prohibition is on **silence**, not on use: exploratory work may use restated labels, and
the discovery ledger's declaration is what keeps option (b) honestly available at graduation.

⚠ **Applies to the emerging-momentum family as well as OVERSOLD.** §6 item 7 already records that v0.7
named PIT universe eligibility for the oversold family only and that emerging momentum "needs it equally,
or the candidate history is survivorship-biased from day one." Sector-label provenance is the **same
omission in a second dimension** — declare it for both families, not just the one the earlier text named.

#### 4.10.1 Evidence firewall — the constraint runs both ways *(new at v0.8)*

v0.7 closes one direction: exploration cannot change strategy behavior. The other direction is open and matters more, because the value-extraction programs read **the same frozen partitions MDQ-001 will adjudicate K1–K6 on**. Without a firewall, someone can look at SIP microstructure in September and then "ratify" a K5 match tolerance or a K3 grid choice in a way the corpus has already told them will pass.

Two rules, frozen at G2:

1. **Value-extraction outputs are inadmissible to K1–K6** (recorded in §7.2). `MOM-SIP-0`, CEE, `DISC-001`, `RANGE-SIP-OBS-001` and feature-library artifacts are strategy/execution evidence, never qualification evidence. Where the same underlying measurement is wanted for both, the MDQ calculator computes it independently from the frozen corpus under the registered definition.
2. **No K-criterion definition, threshold, tolerance, denominator, or evaluability clause may be revised once value-extraction work begins.** They freeze at G2 regardless; this states that exploratory findings create **no exception** to that freeze, including via a "clarification."

If the two conflict — a value-extraction finding suggests a K definition was poorly chosen — the correct move is the one the P-2 proof already demonstrated: record the criterion as answered-or-invalid on its own terms, preserve the run, and version the criterion prospectively for a *future* cycle. Never retune the live criterion mid-window.

#### 4.10.2 Discovery ledger and holdout reserve *(new at v0.8)*

`DISC-001` plus the feature library can generate hundreds of condition/regime/threshold combinations from one corpus. "It graduates through a prospectively frozen hypothesis" does not prevent the ordinary failure: search first, find something, then register the found thing as if it had been the prior hypothesis. The registration is honest and the evidence is still contaminated.

Two mechanisms, both cheap:

- **Discovery ledger** — an append-only record of every condition, family, feature, regime split, and threshold examined against the corpus: what was tried, when, on which period, and its disposition (dropped / parked / promoted). Any pre-registration drawn from exploratory work must **cite its ledger entry and state how many conditions were examined in that family**. Cost-free to maintain, and it converts an unknowable multiple-comparisons burden into a stated one.
- **Holdout reserve** — at G2, quarantine a period and a symbol subset (proposed default: **the final 20% of the review window**, plus a **randomly chosen 20% of the frozen universe**, selected and hashed before capture starts) from *all* exploratory access. Value-extraction and DISC-001 touch the explore set only. A hypothesis graduating to pre-registration is then evaluated once on genuinely untouched data.

Neither mechanism blocks any v0.7 work; both make its output defensible. Note the asymmetry with the platform's prior failures: GAPPER v1 and MR-002's fourth opening were *frozen designs that could not answer*. Unconstrained search is the opposite failure — it always answers, and the answer is usually noise.

#### 4.10.3 Sequencing within the value-extraction scope *(new at v0.8)*

§1.3 item 5 says stop low-value work, but §4.10's default authorization opens five workstreams simultaneously for a single operator — a wide front, not a priority order. Recommended sequence, for §8 ratification:

1. **`MOM-SIP-0` and CEE first.** They serve two things at once: the P1 MOM-001 L1 execution path (§3A.1) and the K5 shortfall/spread evidence the qualification itself needs. Highest value per hour, and no new machinery. *(v0.11: `MOM-SIP-0` is NOT EVALUABLE in the current window — see the §4.10 application note. Read this item as **CEE first**.)*
2. **SIP feature library second**, scoped initially to the features `MOM-SIP-0`/CEE actually consume rather than the full eleven.
3. **`DISC-001` and `RANGE-SIP-OBS-001` third**, gated on (1) producing an output or on an explicit owner time-box.

The Strategy Proposals effort-discipline figure still applies: guardrail/plumbing work stays a minority of effort; the majority goes to strategy and execution value.

#### 4.10.4 DISC-MDQ-001 — governed MDQ enrichment for the Opportunity layer *(new at v0.10)*

**Objective:** determine whether governed SIP/IEX microstructure provides incremental predictive or execution value for candidates already admitted by DISC-001, while keeping the frozen DISC-001 family gates unchanged during exploration.

**Phase-A implementation state (v0.12).** The read-boundary architecture below is now implemented and green in `research/disc-mdq001-phase-a` (uncommitted at this state-sync point). The implementation requires `AuthorizedScope` at construction, denies held-out dates before partition open, discards non-authorized rows during parsing, verifies frozen manifests, has no unrestricted/widening mode, and deliberately did **not** read the live MDQ corpus. Synthetic fixtures with known forbidden rows provide the exclusion proof.

**Phase-B prerequisite added at v0.12:** the append-only discovery ledger required by §4.10.2 must be operational **before** the first feature/condition is computed from an authorized MDQ partition. A successful authorization check is necessary but not sufficient to begin exploration; the act must also be ledgered.


**Architecture:**

```text
DISC-001 frozen eligibility (Sharadar / Factor Store / GAP)
            |
            v
existing candidate set
            |
            v
MDQ exploration policy  -- embargo checked BEFORE read
            |
            +--> held-out symbol/date -> DENY, corpus unopened
            |
            v
allowed DISC ∩ MDQ symbols/dates
            |
            v
read-only MDQ feature reader
            |
            v
additive mdq_observation / research features
            |
            v
governed comparison vs baseline DISC
```

**Initial feature families:**

- liquidity quality — median/p95 spread bps, quote freshness, bid/ask size/depth proxies, stability;
- opening confirmation — 09:30→09:35/09:45/10:00 returns, VWAP relation, volume/trade-count acceleration;
- GAP persistence — premarket gap through opening/first-hour continuation or failure;
- momentum confirmation — intraday persistence, VWAP hold, spread stability;
- oversold reversal confirmation — low-to-close recovery, VWAP reclaim, improving liquidity/participation;
- paired SIP/IEX diagnostics — midpoint/spread/availability divergence, treated first as explanatory features rather than assumed alpha.

**Research priority (as designed — ⛔ SUPERSEDED, see §4.10.6):** `GAP + opening microstructure` → `MOM-NEAR + liquidity/confirmation` → `OVERSOLD + reversal confirmation` → `MOM-CORE + execution quality`. **The owner withdrew this order on 2026-08-20 PM after the precheck below; the effective order is MOM-CORE → GAP (observation only) → MOM-NEAR / OVERSOLD (NOT EVALUABLE).**

🚨 **POPULATION PRECHECK RESULT *(state sync 2026-08-20 PM)* — this priority order is not executable as written.**
Counted over every DISC-001 snapshot that exists (`as_of` 2026-08-14 and 2026-08-19,
`DISC-001-WATCHLIST / v0.3.0`), intersected with the 50-symbol MDQ universe and then with the
10-symbol holdout removed:

| Family | items | ∩ MDQ (08-14) | ∩ MDQ (08-19) | **authorized** (non-holdout) |
|---|---|---|---|---|
| **GAP** | 10 | **0** | **0** | **0** |
| **MOM-CORE** | 15 | 5 | 6 | **5** — AMD, INTC, MRVL, MU, SNDK |
| **MOM-NEAR** | 0 | 0 | 0 | **0** |
| **OVERSOLD** | 0 | 0 | 0 | **0** |
| ALL | 25 | 5 | 6 | **5** |

⭐ **GAP — the #1 priority and the obvious redirect target once OVERSOLD/MOM-NEAR came up empty — has ZERO MDQ overlap on both days.** That is not a small sample; it is a structural mismatch: GAP selects premarket gappers (high-volatility, often smaller names) while the 28 non-ETF MDQ names are mechanically chosen **top-ADV megacaps**. The two populations are close to disjoint by construction, so accruing more sessions is unlikely to fix it.
⚠ The only family with any population is **MOM-CORE at 5 authorized names** — the **lowest** priority in the list above. On 08-19 the intersection was 6 and the holdout filter removed **NBIS**, so the embargo is demonstrably load-bearing even at this size.
⛔ **Do not build the opening / momentum / reversal feature library against this.** Five names on two observed days cannot support the §4.10.4 comparison design. The honest options are: (a) run MOM-CORE as an execution-quality study and accept its narrowness; (b) re-scope the enrichment population, which is a governed change, not a research choice; or (c) record DISC-MDQ Phase B as **NOT EVALUABLE on the current populations** — the `MOM-SIP-0` disposition arriving a second time, exactly as v0.13 predicted.
⚠ **Caveat:** two snapshot days only. GAP membership is day-dependent, so 0/2 is suggestive rather than conclusive — but the structural argument above does not depend on the sample size. Re-run the precheck as snapshots accrue before treating this as final.

**Non-authorizations:**

- do **not** alter `DISC-001-WATCHLIST / v0.3.0` thresholds or family eligibility from exploratory results;
- do **not** demote candidates merely because they are outside the 50-symbol Phase-A MDQ universe;
- do **not** generalize enrichment findings from the intersection to the DISC universe — see the limitation note below;
- do **not** read symbol/date holdout bytes and filter them afterward;
- do **not** collapse features into an opaque composite score before individual feature/outcome behavior is understood;
- any product promotion requires prospective governance and a new versioned ranking/overlay or screen version as appropriate.

#### 4.10.5 Holdout scope — what each holdout actually protects *(new at v0.13)*

§4.10.2 quarantines "a period and a symbol subset … from *all* exploratory access." The implemented reader enforces that for MDQ corpus bytes. The Watchlist deployment makes clear it cannot enforce it everywhere, and that is not a defect in either component — it is a consequence of the two systems reading different inputs:

| Holdout | Protects | Enforced by | Status |
|---|---|---|---|
| **Period holdout** (2026-10-06..10-17) | any hypothesis evaluated on MDQ corpus data from those dates | `MdqFeatureReader` — dates denied before partition open | genuine; enforceable |
| **Symbol subset — MDQ-derived hypotheses** | hypotheses whose evidence is MDQ microstructure for those symbols | same reader; rows discarded during parse | genuine; enforceable |
| **Symbol subset — Sharadar-derived DISC hypotheses** | *nothing* | nothing can | ⚠ **structurally void** |

The third row is the finding. `RSI-REV-001` and `MOM-CAND-001` are built on RSI, SMA, relative return and RVOL — **Sharadar/Factor-Store inputs**, not MDQ bytes. Those same names appear on Band B every session with their proposal prices, and (once Phase 1.1 ships) with their subsequent price history. Watchlist v0.6 §10.3 keeps them visible deliberately and correctly: the MDQ embargo protects corpus bytes, not the existence of an ordinary DISC candidate. The consequence is simply that **a symbol subset cannot be an untouched test set for a hypothesis whose inputs the product displays daily.**

Record at §8 (item 21), and carry into any pre-registration:

1. **For MDQ-derived hypotheses:** both holdouts are real; the reader enforces them; cite them.
2. **For Sharadar-derived DISC hypotheses:** the symbol subset confers no protection. The clean test set is **prospective data post-dating the hypothesis freeze** — the conclusion already reached in Watchlist v0.3 §12.4(b), now load-bearing rather than theoretical.
3. **Do not repair this by hiding held-out symbols from the product.** That was offered as an owner's call in Watchlist v0.3 §12.4(b) and declined; re-deciding it now, after the operator has already watched those names for weeks, would buy nothing and cost the product.

The honest position is the cheap one: name what each holdout covers, and stop treating the symbol subset as protection it cannot provide.

**Cross-platform universe identity (v0.12).** Wherever DISC-MDQ validates the governed universe pin, hash the LF-normalized universe content exactly as the holdout rule specifies: `sha256(universe_symbols_file_LF)`. A CRLF working-tree copy may have a different raw-byte hash without representing a different governed universe; re-pinning to the CRLF hash is forbidden.

**Known generalization limit *(added at v0.11; arithmetic corrected at v0.13)*.** Enrichment operates on `DISC candidates ∩ MDQ eligible universe`, and that universe is **50 symbols: 22 base ETFs plus 28 mechanically selected top-ADV names**. Since `DISC-001-WATCHLIST / v0.3.0` **excludes ETFs** (Watchlist v0.6 §3.1, frozen in ledger entry #0), the effective intersection for OVERSOLD and MOM-NEAR is at most **28 large-cap, top-ADV names** — not 50. Three consequences worth stating before the work rather than after a result:

1. **The intersection is small.** DISC families screen hundreds-to-thousands of names; the overlap with 50 symbols on any given session will be a handful, and on some sessions zero. Feature/outcome relationships measured on that sample carry very little power.
2. **The sample is liquidity-biased by construction.** Top-ADV selection is precisely the population where spread/depth/freshness problems are *least* likely to appear — so a null result on microstructure value here is weak evidence of absence for the broader DISC universe, where the effect should be larger.
3. **ETF semantics differ.** An oversold-quality-pullback or emerging-momentum reading on a sector ETF is not the same object as on a single name; pooling them would blur the very distinction DISC-001's families exist to preserve.

None of this blocks the work — the enrichment is still the cheapest way to see whether microstructure adds anything at all. It does mean the honest output is *"observed on the liquid, top-ADV, non-ETF intersection"*, and any pre-registration drawn from it must state the sample it came from.

**Population precheck — required before Phase-B feature code *(added at v0.13)*.** The first deployed Watchlist snapshot (`as_of=2026-08-19`) reports **OVERSOLD 0 and MOM-NEAR 0** — valid empty results under the frozen gates, and correctly not a reason to relax anything. But it means two of DISC-MDQ's four stated research priorities may currently have **no population at all**, and the third (`MOM-CORE`) is a read-only MOM-001 rank whose program is archived/IDLE. Before writing feature code, run the cheap count:

```text
for each accrued session, for each family:
    | DISC candidates ∩ MDQ universe ∩ authorized (non-holdout) scope |
```

If OVERSOLD/MOM-NEAR come back at or near zero across the accrued window, say so **before** building the study — the honest disposition is that DISC-MDQ Phase B is a **GAP-family** experiment for now, with the other families reopening if and when their candidate counts become non-trivial. This is the `MOM-SIP-0` lesson arriving a second time: a workstream whose population does not exist is NOT EVALUABLE, and discovering that after the feature library is built is the expensive order.

#### 4.10.6 Revised research priority after the population precheck — OWNER RULING, 2026-08-20 PM *(new)*

The §4.10.4 precheck was run before any feature code was written, and its result withdraws the priority
order §4.10.4 was designed around. **This is the `MOM-SIP-0` lesson applied a second time, and it is the
point of having run the precheck at all: population viability is itself a gate.**

| Rank | Family | Disposition | Authorized population |
|---|---|---|---|
| **1** | **MOM-CORE × MDQ execution quality** | **VIABLE but NARROW** — proceed as a deliberately scoped observational study | **5** — AMD, INTC, MRVL, MU, SNDK |
| **2** | **GAP** | **POPULATION OBSERVATION ONLY — do NOT build the feature study** | **0** on both snapshot days |
| **3** | **MOM-NEAR** | **NOT EVALUABLE on the current population** | 0 |
| **4** | **OVERSOLD** | **NOT EVALUABLE on the current population** | 0 |

⛔ **The GAP fallback is explicitly WITHDRAWN.** GAP was the natural redirect once OVERSOLD and MOM-NEAR
came up empty, but it is empty too — and structurally so: GAP selects premarket gappers while the 28
non-ETF MDQ names are mechanically chosen top-ADV megacaps. The populations are near-disjoint **by
construction**, so it would be wasteful to build the GAP–MDQ feature path hoping the population appears.
Continue counting it; do not fund it.

**MOM-CORE scope — bounded deliberately, because five names cannot carry a general claim.**
Permitted questions: **spread stability · SIP/IEX quote-quality divergence · VWAP participation ·
intraday liquidity · whether those measures improve execution/ranking *diagnostics*.**
⛔ **Do NOT generalize any MOM-CORE finding to the broader DISC universe.** Five top-ADV semiconductor-
adjacent megacaps are not a sample of DISC's ~2,000-name universe; they are a corner of it. This is the
§4.10.4 generalization limit arriving with a concrete number attached.
⛔ It does not become a DISC predictive claim, does not touch `DISC-001-WATCHLIST / v0.3.0`, and does not
acquire L1/L2 authority.

**"NOT EVALUABLE" is a completely valid outcome here.** If the population stays this thin, recording
**"DISC-MDQ Phase B NOT EVALUABLE on the current Phase-A universe"** is the honest disposition — not a
failure of the program and not a reason to widen the universe opportunistically. Re-scoping the enrichment
population is a **governed change**, never a research convenience.

**Next technical decision — deliberately narrow:**

1. **Do not build full Phase-B feature code yet.**
2. Accumulate a few more DISC snapshots and **repeat the intersection census** (§6 item 23a).
3. If MOM-CORE remains the only populated family, open a **deliberately scoped MOM-CORE × MDQ
   execution-quality observation** rather than pretending DISC-MDQ is broadly evaluable.
4. If the other families stay empty or near-zero, **record that as a governed population finding and stop
   those branches.**

⚠ The precheck rests on **two snapshot days**. GAP membership is day-dependent, so 0/2 is suggestive
rather than conclusive — the structural argument stands on its own, but the census must be repeated as
snapshots accrue before any branch is closed permanently.

#### 4.10.7 Discovery ledger — ACCEPTANCE GATE before CEE *(owner ruling, 2026-08-20 PM)*

§4.10.2 ratified *that* a ledger is required. This subsection fixes *what counts as done*, so "the ledger
was built" and "the ledger is actually gating the first read" cannot drift apart.

🛑 **THE HARD STATEMENT.** **CEE may be the first exploratory consumer, but the discovery ledger must
be OPERATIONAL before CEE opens its first governed partition.** Not written, not merged — *operational and
in the read path*. A ledger that exists but is not gating is not a ledger; it is a file.

**Acceptance gate — all twelve, or the gate is not met:**

```text
STRUCTURE
  1. append-only
  2. NO overwrite and NO delete path exists

ONE RECORD PER CONDITION/FEATURE EXAMINED, carrying:
  3. timestamp
  4. authorized scope
  5. corpus / partition identity
  6. code / version identity
  7. condition / feature definition
  8. disposition / result
  9. denial information, from AuthorizedScope.denials

ENFORCEMENT (the half that is easy to skip)
 10. the first exploratory MDQ feature read is IMPOSSIBLE unless ledger
     initialisation SUCCEEDS
 11. the holdout artifact AND the universe pin both load and verify BEFORE
     the reader opens a partition
 12. ledger initialisation failure is FAIL-CLOSED, never a warning
```

⭐ Items 1–9 describe a record. **Items 10–12 are what make it a control.** The Phase-A reader already
proves the pattern: it cannot be constructed without an `AuthorizedScope`, so there is no path that reads
first and records later. The ledger must bind the same way — authorisation answers *may these bytes be
observed?*, the ledger answers *what was examined, on which governed corpus, under which code and scope,
and with what disposition?* **Both are required, and neither is optional at the first read.**

⭐ `AuthorizedScope.denials` was deliberately built to retain **full** denial detail (every symbol/date and
its reason, not just a count) precisely to satisfy item 9. A program that silently drops names cannot
afterwards show it honoured the quarantine.

**Deployment prerequisite — new, and easy to miss.** The holdout artifact
`mdq_phase_a_holdout.json` is **not on the box today** (verified 2026-08-20: `/opt/workbench/data/mdq_config/`
holds only `mdq_phase_a_universe_symbols.json`, sha `0c57bd71...`, matching the wrapper's pin). That is
correct while nothing deployed reads it. **The moment `from_config` enters the deployed ledger/CEE reader
path, the concrete stamped holdout artifact becomes a deployment prerequisite alongside the universe pin**
— both must be present and verified on the box, or item 11 cannot hold in production.

### 4.11 Verdict-reachability check — ✅ RATIFIED at G2 (2026-08-17): **GO floor = ≥2 of K1–K6 both evaluable AND PASS; otherwise HOLD with a stated extension** *(new at v0.8)*

Each evaluability clause added since v0.3 is individually correct. Their **conjunction** has not been checked, and it should be, before evidence starts accruing:

```text
K1  correction of a predeclared gate-material IEX defect
      → may have no in-corpus instance if §8 item 14 resolves "MDQ corpus only"
K2  streaming reliability
      → NOT EVALUABLE unless G10 opens                        (§4.4)
K3  missingness reduction
      → evaluable; not evaluable if missing_rate_IEX == 0     (§4.2)
K4  GAPPER Stage-0 enablement
      → NOT EVALUABLE if Stage 0 slips the window             (§8.8)
K5  execution evidence coverage
      → NOT EVALUABLE below N_min fills                       (§4.3)
K6  quote fidelity
      → NOT EVALUABLE without a captured IEX occurrence       (§4.8)
```

The worst case is not exotic: G10 stays closed (the current default), Stage 0 waits on G4, the fill count sits under `N_min` with MR-002 **terminated** (its fills permanently absent, not merely deferred), no stub-quote event lands inside a 60-day 50-symbol capture, and item 14 resolves to the plan's own default *(corrected at v0.9 — 14 was the pre-registration smoke universe; the frozen Phase-A universe is 50 symbols).* That leaves **GO reachable on K3 alone** — a single-criterion retention test, which is a materially different decision from the six-criterion test the owner believes is being run.

Freeze at §8:

- the **enumerated worst case** — which criteria can simultaneously be NOT EVALUABLE under current defaults;
- confirmation that **GO remains reachable** in that case, and on which criteria;
- a **minimum evaluable-criteria count** for a GO verdict (proposed default: **at least 2 of K1–K6 evaluated PASS**, since a one-criterion GO is not a qualification);
- what disposition applies if the floor is not met (proposed: **HOLD with a stated extension**, per §4.4's GO/HOLD/STOP format — never a default Cancel on unevaluability, and never a GO on a single criterion).

This costs one paragraph at sign-off. Not doing it costs a 60-day window.

#### 4.11.1 The other failure of the same kind — a criterion that cannot fail *(new at v0.11)*

§4.11 protects against criteria that can never be **evaluated**. There is a mirror-image hole it does not cover: a criterion that can never **fail**. Both defeat the GO floor, and the second is harder to see because it looks like a pass.

K5 reads: spread/mid/shortfall metrics produced for **≥90% of paper fills**. v0.10 change 3 records — correctly, and before coverage was computed — that the R2 match rule leaves some fills without a governed quote, and that **unmatched fills are excluded from the K5 ratio**. Follow that through:

```text
K5 ratio = metrics produced / fills that HAD a governed quote match

but metrics are produced exactly when a match exists

=> numerator == denominator
=> ratio ≈ 100%, on any corpus, regardless of feed quality
```

The observed ~54.7% fill / 65.8% submit / 66.7% decision match rates are the size of the population being removed from the denominator — between a third and a half of the fills. K5 then measures whether the calculator ran, not whether SIP improved execution evidence. **It cannot return FAIL.**

That matters specifically because of the ratified GO floor. §8.1 requires **≥2 of K1–K6 both evaluable AND PASS**. An auto-passing K5 supplies one of those two for free, so the floor is satisfied by K3 plus a tautology — which is the single-criterion retention test §4.11 exists to prevent, arriving through the front door with a PASS stamp on it.

**What v0.11 does and does not propose.** It does **not** propose retuning K5, changing its denominator, or reinterpreting R2. §4.10.1 forbids revising a K definition, and the R2 ruling was correctly frozen before coverage was seen — reopening it now would be exactly the post-hoc move the firewall exists to stop. What is proposed is a **verdict-clause decision**, the same class as unsigned ruling 3, recorded prospectively **before exploration begins**:

1. **Record K5's discriminating status explicitly.** State, in the registration §8.2 stanza, whether K5 as frozen can return FAIL on the current corpus. If it cannot, say so now, on the record, while nobody has looked.
2. **Decide whether a non-discriminating PASS counts toward the GO floor.** Recommended: **it does not** — the floor should require two criteria that were *capable of failing*. Otherwise the floor's arithmetic is satisfied by a criterion that carries no information.
3. **Record the match-rate context as a diagnostic, not a criterion.** The ~55–67% match rates are a genuine and useful finding about quote coverage under R2. They belong in the verdict artifact as context, and are a strong candidate for a **prospectively versioned K5′ in a future cycle** — the P-2 precedent exactly: preserve the run, mark the criterion on its own terms, version forward.

If the honest answer turns out to be that only K3 could both be evaluated and fail, then the GO floor is not met and the disposition is **HOLD with a stated extension** — which is a real outcome the ratified rules already provide for, not a failure of the process. Deciding that in August costs a paragraph. Discovering it in October, after exploration has closed the firewall, costs the cycle.

#### 4.11.2 PX-2 — K5 discriminating status: ✅ **SIGNED 2026-08-20** *(governing text: registration §8.4; PR #651)*

✅ **SIGNED 2026-08-20**, before any exploratory read of the corpus. The governing text is
**registration §8.4** (additive — §8, §8.1, §8.2 and §8.3 verified byte-unchanged); this plan is
not the signature artifact. Landing in **PR #651**.

⭐ **The signed determination is deliberately stronger than the first draft.** The draft was
conditional — *"if the frozen construction leaves K5 without a meaningful FAIL region..."* — which
would have migrated the determination itself to verdict time, where "does K5 really discriminate?"
becomes arguable in whichever direction happens to be convenient. The question is **structural, not
empirical**: §4.11.1 already proves numerator ≡ denominator by construction, which holds on any
corpus. So it is decided **now**, and the conditional is gone.

> **PX-2 determination (signed).** K5 as frozen **cannot return FAIL** for its intended coverage
> question. Under the frozen population rule, fills without a valid matched quote are excluded from
> **both** numerator and denominator; for the fills that remain, the coverage numerator and denominator
> are therefore structurally equivalent except for computation/integrity failures. The K5 coverage ratio
> consequently approaches **100% by construction on any admissible corpus**. This determination is made
> from the frozen definition **before any governed K5 coverage result is examined**.
>
> K5 must still be calculated and reported exactly as frozen. If `N_min` is not met, K5 is **NOT
> EVALUABLE**. If `N_min` is met and the frozen computation succeeds, K5 may mechanically report PASS,
> but that **non-discriminating PASS does not count toward the ≥2 independent evaluable-and-PASS
> criteria required for GO**.
>
> **No K5 threshold, denominator, matching rule, `N_min`, evaluability clause, or metric definition is
> changed.**

**Why this wording, and why it does not violate §4.10.1.** Nothing about K5 moves: not the 90% threshold,
not `N_min`, not the R2 matching rule, not the population definition, not the denominator, not the
evaluability semantics. What is being decided is a **verdict-clause** question — how a PASS is *counted*
toward the ratified GO floor — which is the same class as ruling 3 and is exactly what §4.13 requires be
settled before exploration.

⭐ **It preserves the historical result rather than rewriting K5 after learning it is weak.** The mechanical
K5 PASS stays on the record as a K5 PASS; only its contribution to the ≥2-independent-PASS floor is
qualified. That is the P-2 precedent: preserve the run, mark the criterion on its own terms, version
forward.

**Consequence, stated plainly (registration §8.4.4).** With K2 NOT EVALUABLE (no G10), K4 NOT
EVALUABLE (no in-window Stage-0 run), K6 NOT EVALUABLE absent a captured IEX stub occurrence, and
K5's PASS now non-contributing, **the GO floor rests on K1 and K3.** If only one of those is both
evaluable and PASS, the disposition is **HOLD with one stated extension** under §8.3's matrix — a
real outcome the ratified rules already provide for, not a failure of the process and not a reason to
relax a threshold.

```text
K5 discriminating status:  SIGNED - cannot return FAIL for the coverage question
Determination timing:      SIGNED - from the frozen definition, BEFORE any result
Reporting:                 SIGNED - computed/reported as frozen; a mechanical PASS
                           remains a K5 PASS in the evidence record
GO-floor contribution:     SIGNED - a non-discriminating PASS does NOT count
Definitions changed:       NONE
Signed by / date:          Jay Wang (owner) — 2026-08-20
```
signature artifact.

### 4.12 Governed-text correction set — owner rulings, 2026-08-18 *(new at v0.9)*

The morning the first governed capture failed to run was also the first morning anyone read the governed text with a
running program behind it. That reading surfaced four defects. The owner ruled on all four the same day. **Three are
consistency corrections; the fourth adds a disposition and is not yet signed.**

**The registration document controls.** §4 of this plan is the record of *why* definitions exist, not the definitions
themselves — the frozen text of all four rulings lives in `docs/design/MDQ-001_Registration_v1_0_DRAFT.md` **§8.2**,
with the holdout arithmetic and the pre-commitment restated in `docs/design/MDQ-001_ProgramStart_Record_v0_1_DRAFT.md`
§4.2 / §4.4 / §8.2. Values are deliberately not duplicated here; where this plan and the registration differ, the
registration wins.

| # | Defect | Ruling | Kind |
|---|---|---|---|
| 1 | §4.9's `expected_cycles = f(session_scope, cadence, market calendar)` froze the **threshold** and left `session_scope` **unbound** — and the only session interval the documents name is the **bar-census** window | The census window is the **bar** denominator. The **quote-sampler** denominator is `09:25 ET <= t < official NYSE close (exclusive)` at 60 s. Registration §8.2 has the numbers. The **98% floor and 10-minute maximum gap are unchanged** | **Correction** — binds a definition |
| 2 | Registration §4 still read "keep if **ANY** K criterion is met," contradicting the later, specifically ratified §8.1 GO floor | §8.1 controls; §4 corrected to match | **Correction** — stale prose |
| 3 | The combined rules left **≥ 2 evaluable and exactly 1 PASS** with **no disposition at all** | HOLD with one stated extension — ✅ **SIGNED 2026-08-19**, registration §8.3; merged `d43817b` (#647), markers cleared `15da72c` (#648) *(state sync 2026-08-20 PM)* | ✅ **Addition, discharged** |
| 4 | §4.10.2's holdout rule ("final 12 calendar days") never stated its offsets, and the two readings differ by a day at each end | Offsets frozen; **the boundary does not slide for weekends or holidays**; the embargo predicate is stated explicitly | **Correction** — arithmetic |

Three things follow that this plan has to carry.

**Do not weaken the threshold to accommodate a defective runtime.** The sampler scheduled **fixed-delay** — it slept
the cadence *after* doing the work — so its real period was `60s + overhead` and a perfectly healthy capture drifted
to roughly 383–389 cycles against a 395-slot grid. Read carelessly, that looks like evidence the 98% floor is too
strict. It is not: it is **systematic scheduler drift**, and the fix belongs in the runtime, not in the threshold.
The correction is fixed-rate scheduling against an absolute monotonic deadline, no burst or catch-up, the close
checked before each cycle, and a persisted `scheduled_slot_ts` / `slot_index` per cycle so observed cycles reproduce
against the frozen grid. This is the temptation §11 already named, arriving a day early and wearing a plausible
technical argument: the thresholds were ratified before anyone had seen a governed partition, which is the only
moment at which a threshold can be set honestly.

**The gate test — measured, not argued.** Phase error against the grid origin over a full **395-slot** session bounded by the real 16:00 close:

| Scheduler | Per-cycle work | Slots captured | Phase error |
|---|---|---|---|
| **Fixed-rate** (the correction) | 1.5 s | **395 / 395** | **0.000 s** at k=1, k=100, k=394 |
| **Fixed-rate** (the correction) | 2.0 s | **395 / 395** | **0.000 s** at k=1, k=100, k=394 |
| **Fixed-rate**, 3 ms per-sleep overshoot injected | — | **395 / 395** | constant **3 ms** at k=394 — **bounded by one sleep, never compounding** |
| **Fixed-delay** (the deployed defect) | 1.5 s | 386 / 395 = **97.72 %** | ⛔ **below the ratified 98 % floor** |
| **Fixed-delay** (the deployed defect) | 2.0 s | 383 / 395 = **96.96 %** | ⛔ **below the ratified 98 % floor** |

Both fixed-delay rows were measured on a **healthy feed with zero outages**. That is the entire argument in one line: **the deployed scheduler could fail the ratified completeness floor on a perfect day, with nothing in the logs to show for it.** The partition would simply come up short, and the obvious reading at adjudication — “98 % is too strict” — would have been wrong. The defect is in the runtime and the correction goes there. This is the concrete evidence behind *do not weaken the threshold to accommodate a defective runtime*, and it is why the fix lands **before** any corpus accrues rather than being discovered in October against 60 days of short partitions.

**Ruling 3 — ✅ RATIFIED 2026-08-19** *(state sync 2026-08-20 PM)* *(this paragraph read "is not ratified, and it has a deadline that is not a date" — true when written, discharged at registration §8.3 / `d43817b` #647).* The reasoning is retained because it explains **why** the signature had to precede exploration, and that logic still governs the remaining unsigned items (PX-2 / §8 item 20). As written: it is the one item that adds a disposition
rather than correcting prose, so it needs the owner's explicit sign-off — and that sign-off must happen **before
value-extraction work starts**. Once exploration touches the corpus, §4.10.1's firewall forbids revising a verdict or
evaluability clause, so an unsigned gap stops being open and becomes unfixable. It costs one signature now and a
litigated October otherwise.

**Corrected sequencing — the order is the point.**

```text
1. FREEZE THE DEFINITIONS          registration §8.2 (done 2026-08-18);
                                   ruling 3 SIGNED 2026-08-19 (§8.3)
2. PATCH THE SCHEDULER             fixed-rate against an absolute monotonic
                                   deadline. Creates a NEW collector code
                                   identity - FIVE files, __init__.py included
                                   (owner 2026-08-18)
3. REBUILD IMAGE + RECREATE        the collector runs via `docker exec` into
                                   workbench-backend and the image BAKES THE
                                   SOURCE IN, so this is an image rebuild and a
                                   container recreate - a TIER-3 LIVE-STACK
                                   TOUCH, not a file copy.
                                   WINDOW: after tonight's 16:45 ET freeze
                                   completes. Never intraday - 16:30/16:45
                                   docker exec into that same container.
4. UPDATE THE PROGRAM-START RECORD re-stamp §2.3 (five git blobs, hashed at the
                                   MERGE COMMIT) AND §6 (the image/container
                                   actually serving docker exec). Git blobs
                                   alone do not prove the container was
                                   recreated.
5. THEN, AND ONLY THEN             allow a first admissible capture to start
                                   the 60-day clock
```

Steps 1–4 are cheap and reversible; step 5 is neither. Running step 5 first — letting a capture start the clock
against an unbound denominator, a drifting sampler, a stale code-identity stamp, or a container that was
never recreated — buys one calendar day and spends the corpus. **The clock not starting is a normal outcome,
not a failure.**

Step 3 is the one that is easy to under-scope. It is not “ship the patch”; it restarts the live trading backend,
and step 4 is what makes the restart auditable afterwards. **Two identities, both stamped:** the git blobs say
what the source is, the image ID says what actually ran.

### 4.13 Pre-exploration gate — the checklist that must clear before the first value-extraction read *(new at v0.11)*

Several obligations scattered across §4.10.1, §4.12, §8 item 19 and §6 share one property: **once exploratory work touches the corpus, none of them can be discharged any more.** §4.10.1 forecloses revising a verdict clause or an evaluability clause after exploration begins, and that foreclosure is deliberate and correct. It also means every unfinished governance item silently converts from *open* to *permanently unresolved* at the moment CEE opens its first frozen partition.

v0.10's §6 listed CEE (item 13) and DISC-MDQ-001 (item 14) **ahead of** landing the rulings document (item 16) and keeping ruling 3 unsigned (item 18). Read literally, that instructs exploration first and custody after — the guard scheduled behind the thing it guards.

**Gate PX — all of the following complete before any value-extraction or DISC-MDQ read of the MDQ corpus:**

🏁 **HISTORICAL / DONE — Gate PX is FULLY CLOSED (all six items), and the first governed read has since occurred.** *(state sync 2026-08-22.)* The checklist below is retained as the record of what was required and how each item was discharged. ⛔ **Nothing in this block is outstanding work.** Any line that reads as an instruction (notably PX-2) describes the requirement *as it stood*, not a task remaining. See the status table immediately after the block, and the 2026-08-22 state sync at the top of this document.

```text
PX-1  Ruling 3 SIGNED  [DONE]       SIGNED 2026-08-19 at registration §8.3;
                                     merged d43817b (#647); markers cleared
                                     15da72c (#648)        [state sync 08-20 PM]
PX-2  K5 discrimination  [SIGNED]   SIGNED 2026-08-20 at registration s8.4
                                     (PR #651). The determination was made
                                     PROSPECTIVELY, not left conditional: K5
                                     cannot return FAIL for its coverage
                                     question, and a non-discriminating PASS
                                     does NOT count toward the >=2 GO floor.
                                                          [state sync 08-22]
PX-3  Rulings doc IN GIT  [CLOSED]  MERGED b523897 (#649); blob 06e2c674...
                                     re-verified post-squash, LF, 0 CR bytes
PX-4a Holdout GOVERNANCE  [DONE]    identity + scope answered: 10/50 subset,
                                     LF sha 6c6cf03a..., frozen 63c0c52 on
                                     2026-08-17 i.e. BEFORE D0; scope per §4.10.5
                                     (real for MDQ-derived, void for
                                     Sharadar-derived DISC hypotheses)
PX-4b Holdout ARTIFACT STAMP        ✅ STAMPED (PR #651). Explicit NAMED bounds:
        [DONE, PR #651]              start_inclusive 2026-10-06 / end_inclusive
                                     2026-10-17 / end_exclusive 2026-10-18 - not
                                     a bare A..B range, per s8.2 ruling 4.
                                     Pre-stamp identity 6c6cf03a... retained;
                                     symbol-list hash 320a8c3b... attests the ten
                                     symbols are UNTOUCHED. The regression test
                                     was INVERTED, not deleted, in the same commit.
PX-5  §4.12 sequencing [CLOSED]     Program Start Record v0.2 §6 stamps image
                                     cb4e42cd1481... + container created 50 s
                                     after the build — both identities stamped
PX-6  Embargo AT THE READ [CLOSED]  MERGED 2db44b5 (#650); 47 tests; 7 files
                                     all ADDED, LF, 0 CR; SCREEN_VERSION v0.3.0
                                     and disc001/ byte-untouched on main
```

**Gate PX status after the 2026-08-20 merges** *(owner refinement, 2026-08-20 PM)*:

| Item | State |
|---|---|
| PX-1 | ✅ **CLOSED** |
| **PX-2** | ✅ **SIGNED 2026-08-20** — registration §8.4 (PR #651) |
| PX-3 | ✅ **CLOSED** by `b523897` |
| PX-4 governance/identity | ✅ **ANSWERED** |
| **PX-4 artifact stamp** | ✅ **STAMPED** (PR #651) — pre-stamp identity + symbol-list hash retained |
| PX-5 | ✅ **CLOSED** |
| PX-6 | ✅ **CLOSED** by `2db44b5` |

🏁 **Gate PX clears on the merge of PR #651** — all six items discharged. *(This note read
"Gate PX is NOT clear — two items remain"; both landed 2026-08-20 PM.)* The reason PX-4 was tracked
in two layers is worth keeping: calling it finished because its *governance* question was answered
would have left the machine-readable artifact permanently unstamped, and §4.10.1 forecloses fixing
that once exploration begins.

⛔ **Gate PX clearing does NOT start exploration.** The discovery ledger (§4.10.2) must exist first,
and only **CEE** is then unblocked — the broad DISC-MDQ feature library stays held on the population
census (§4.10.6).

**Custody caveat (v0.13) — ✅ DISCHARGED *(state sync 2026-08-20 PM)*:** committed `9a666e1` + binding test `d51f232`, pushed to `research/disc-mdq001-phase-a`, **PR #650** open, **47 tests**. The caveat as written, and the reasoning behind it, are retained below because the principle stands. *Original text:* PX-6's mechanism is implemented and tested, but the code, its 45 tests and its green type/lint runs exist only in an uncommitted Windows worktree. That is the same durability profile as the pre-#634 working set v0.3 flagged, and the same class of exposure the 2026-07-27 volume-destruction incident punished. Commit and push to a draft branch before treating PX-6 as evidenced — minutes of work, and it converts a claim about one machine into something reviewable.

**Phase-B ledger gate (v0.12).** Even after PX clears, the first authorized MDQ feature read must not occur until the append-only discovery ledger required by §4.10.2 is operational. Authorization answers *may these bytes be observed?*; the ledger answers *what condition was examined, on which governed corpus, under which code/scope, and with what disposition?* Both are required before exploration.

The asymmetry is the whole argument: clearing PX costs an afternoon, and every item on it becomes unfixable the moment it is skipped.

---

## 5. Tracks and sessions

Each executable session receives its own session document before work begins.

### Track 0 — Stabilize and package the current working set *(G0 — ✅ CLOSED 2026-08-17)*

| § | Session | Status |
|---|---|---|
| 0.1 | Apply the v0.3 pre-deploy corrections (bar window, smoke quarantine, K3/K5/K2 definitions, HTTP-capability invariant, sampler resilience) | ✅ DONE — in PR #634 (commit `85ef245` + earlier) |
| 0.2 | Restore/rebase `ci.yml` from `origin/main` without importing the local-revert drift; wire `check_marketdata_feed_pinning.sh` | ✅ **DONE** — PR **#636** (`be4235d`), a 4-line addition to the invariant block; verified present on `main` at `.github/workflows/ci.yml:368–370`. The guard is now mechanism, not convention. |
| 0.3 | Batch the working set into a draft PR with logically separate commits | ✅ DONE — draft **PR #634**, **6 commits** through `1c7e318` |
| 0.4 | Review/merge after green CI and governance-doc consistency check; walk-away discipline applies | ✅ **DONE 2026-08-17 night** — merged in the intended order #634 → #636 → #637, after G1/G2, so the merged registration text **is** the signed text. |

Do **not** mix Phase-B streaming into this PR.

### Track 1 — MDQ-001 Phase A *(G1 ✅, G2 ✅, deployed; awaiting the first admissible partition)*

| § | Session | Gate | Est. |
|---|---|---|---|
| 1.1 | Monday P-2 proof: confirm account-7 credential is real-time SIP during RTH | ✅ **DONE 2026-08-17** (v2 proof; v1 FAIL preserved — v0.6 change 1) | — |
| 1.2 | MDQ §8 owner sign-off | ✅ **DONE 2026-08-17 eve** — §8 signed, §8.1 ratified in full; item 14 resolved **MDQ corpus only**; K6 = option **(a)** | — |
| 1.3 | Provision `WORKBENCH_MDQ_CAPTURE_ROOT` on the AWS persistent volume | ✅ **DONE 2026-08-17 night** (§3.3) | — |
| 1.4 | Deploy collector/schedule and run the first governed session: sample → EOD → freeze → verify | ✅ deployed on **systemd ET timers** (§3.3); ✅ **first admissible governed session = 2026-08-19 (D0)**, adjudicated ADMISSIBLE/exit 0 *(v0.11: was still showing "first governed session runs 2026-08-18 / in flight")* | — |
| 1.5 | Build offline analysis against **frozen partitions only**. **Order corrected at v0.9:** the *first* tool needed is not a K-calculator but a mechanical **§7.1 admissibility check** — `verify` proves integrity, §7.1 requires *sufficiency* (completeness ratio, max contiguous gap, universe/identity/label/scope match). Program start cannot be adjudicated by eye. K1/K3/K5/K6 calculators follow. | G2 ✅ | 2h + 4–6h |
| 1.6 | Accrue governed evidence → GO/HOLD/STOP verdict artifact under ADR 0051 envelope | calendar → G3 | ongoing |

Phase-A direct Alpaca access belongs only to the acquisition collector. MDQ calculators receive no credentials.

### Track 1B — Phase-B streaming / K2 *(closed unless G10 opens)*

Purpose: prove 250/500-symbol streaming reliability.

Preconditions:

- separate owner authorization;
- proof that account-7 transition/executor activity will not contend;
- explicit WebSocket feed identity;
- one-connection/dual-arming analysis;
- frozen universe/cadence/recovery policy;
- CPU/memory/storage ceiling and abort rule;
- separate session doc.

If not opened, K2 remains NOT EVALUABLE for this MDQ cycle.

### Track 2 — OPRA-CAP-001 bounded options capture *(actionable after G2)*

Extend the same acquisition/archive pattern:

- account 7 remains acquisition identity unless a later owner ruling changes it;
- explicit OPRA feed;
- pre-declared underlyings (initially broad-market/sector ETFs per v1.4.1);
- 15-minute IV-surface snapshots;
- pre-declared storage budget;
- no full-tick archive;
- no options trading;
- immutable frozen history for later Reserves B/E.

Before start, freeze:

- exact underlying set;
- option-selection/expiry/delta policy;
- snapshot cadence;
- storage ceiling;
- missingness rules;
- provenance identity.

### Track 3 — Observation upgrades *(no strategy behavior changes)*

| § | Session | Gate | Data path |
|---|---|---|---|
| 3.1 | **MOM-SIP-0 shadow:** compare SEP identity and IEX/SIP observations; record whether target/universe/size/timing would differ | ⛔ **NOT EVALUABLE in the current window** *(v0.11)* — MOM-001 archived/IDLE, no viable population; closed unless a future governed population changes that | Prefer offline join to frozen capture data; no MDQ credential use |
| 3.2 | **CEE execution-quality fields:** decision price, SIP mid/spread, implementation shortfall — ✅ **AUTHORIZED** (`dcc2c97`, #657); **Session 001 COMPLETE, NOT EVALUABLE (n=17)** (`07f745b`, #659); no promotion decision; **further work is POPULATION-GATED** *(state sync 2026-08-22)* | G2 ✅ met | Offline reconstruction from frozen captures under the K5 matching rule |
| 3.3 | **SCAN-001 SIP path:** RVOL/gap/ATR, stale rejection, feed identity, divergence metric; candidate-not-signal invariant preserved | G3 + G7 if local-cache consumer | Live local observation cache/service — **not the immutable MDQ archive** |
| 3.4 | **MKT-PROJ breadth extras:** display/reference only | G3 + G7 if local-cache consumer | Live local cache; lowest priority |

Any finding that SIP changes MOM signal, eligible universe, target, size, or risk state is a governed strategy/data change, not a transparent observation upgrade.

### Track 3A — ATP Strategy Performance & Alpha-Discovery Program *(new at v0.7; observation first)*

Purpose: turn the qualified ATP datasets into measurable platform value while preserving the existing strategy gates.

**Plane placement *(added at v0.8)*.** Every program in this track sits in the **Research/Analytics plane** under ADR 0051: no execution authority, no order-path imports, no broker capability. Their outputs — sensitivity reports, shortfall reconstructions, feature tables, candidate lists — are **governed artifacts carrying the standard provenance envelope**, including the **feed identity** of every input. A candidate list whose feed provenance is not recorded is exactly what the explicit-feed rule exists to prevent, and it cannot later be cited as evidence for anything.

| Program | Initial authority | Core question | Earliest useful output | Graduation condition |
|---|---|---|---|---|
| **MOM-SIP-0** | L0 | Where does SIP materially change MOM execution quality vs the governed baseline? | spread/freshness/shortfall/timing sensitivity report | evidence supports a bounded L1 overlay |
| **MOM-LIQ-001** | spec/pre-registration only until authorized | Does validated medium-term momentum improve net of costs when entries are conditioned on consolidated liquidity/freshness and/or execution timing? | prospective design with independence/cost test | owner pre-registration + governed backtest |
| **MOM-CAND-001** | candidate-only | Can participation/liquidity acceleration identify emerging momentum before conventional medium-term rank? | daily candidate list + frozen feature history | prospective signal hypothesis passes pre-registration |
| **RANGE-SIP-OBS-001** | L0 | Do SIP quotes/trades/auctions/VWAP materially improve daily reference levels versus IEX for symbols where range-style levels are useful? | level-error / execution-quality comparison | only a *new* economic mechanism may become a strategy |
| **DISC-001 / RSI-REV-001** | candidate-only → pre-registration | Is RSI<30 useful only in specific trend/liquidity/volume regimes, net of costs? | oversold candidate set; conditional forward-return evidence | independent reversal hypothesis with falsification |
| **GAPPER-SIP** | governed by G4/G5 | Do gap magnitude + consolidated RVOL/participation + controlled spread/VWAP behavior identify higher-quality continuation candidates? | Stage-0/observational feature sufficiency | GAPPER's own gate chain |
| **RANK-EXEC / PORT-SIP** | downstream utility only | Can SIP liquidity, spread and realized shortfall improve execution/capacity allocation among already-valid opportunities? | capacity/shortfall diagnostics | predictive utility must be prospectively proved before any strategy-ranking use |
| **SIP-CONT-001** | reserve proposal | Does intraday continuation persist when confirmed by consolidated participation and healthy spreads? | pre-registration | G5→G6→G9 |
| **SIP-LSR-001** | reserve proposal | Does short-horizon reversion improve specifically after measurable consolidated liquidity shocks? | pre-registration | G6→G9; must prove non-equivalence to RNG |
| **OPRA-RISK-001** | risk-overlay research | Do IV/skew/term features improve event-risk avoidance or sizing for an already registered equity strategy? | risk-filter design after OPRA corpus matures | G8 + strategy-specific pre-registration |

#### 3A.1 MOM-001 — fastest path to measurable value

MOM-001 already has validated alpha; therefore ATP should first try to improve **realized implementation** without changing the alpha definition. Measure, per rebalance candidate/order where admissible:

```text
governed momentum rank
SIP bid / ask / midpoint
spread_bps
quote_age
SIP trade count / dollar volume
VWAP and distance-to-VWAP
IEX↔SIP divergence
decision timestamp
submission timestamp
fill timestamp / fill price
implementation shortfall
```

The first prospective behavioral proposal, if supported, should be **L1**: stale-quote rejection, spread/liquidity eligibility, bounded deferment or execution-window rules. Do not alter the PIT momentum ranking at L1.

A later `MOM-LIQ-001` may be L2 only if a prospectively registered hypothesis shows that consolidated participation/liquidity adds predictive value rather than merely reducing trading cost. Do not call it MOM-002 or treat greater breadth as a new edge.

#### 3A.2 Range-level accuracy without resurrecting rejected RNG

`RANGE-SIP-OBS-001` is a measurement program, not authorization to restart RNG-001. Compare daily reference levels built from:

- previous-session/overnight context;
- SIP premarket high/low;
- official opening/closing auctions where available;
- first-5m / first-15m opening ranges;
- consolidated VWAP;
- SIP spread/freshness;
- ATR / realized volatility;
- IEX equivalents.

Measure whether SIP reduces reference-level error or poor-fill incidence. If it does, that can improve execution/reference pricing or support a **new** range/breakout mechanism. It does not invalidate the prior RNG rejection.

**Non-equivalence test *(new at v0.8)*.** "A genuinely new economic mechanism" is a label, not a test — and the same label carries the weight in Track 6 Reserve D ("prove it is not RNG-001 re-labeled"). Any candidate claiming to be new must settle three things **in its pre-registration, before backtest**:

1. **Signal-level distinctness** — the proposed entry/exit signal's correlation with the rejected predecessor's signal on overlapping history, with a pre-declared maximum;
2. **A materially different reject condition** — the new mechanism must be falsifiable in a way the old one was not, or the rejection evidence transfers directly;
3. **A stated economic mechanism that does not reduce to the rejected one** — better *measurement* of the same effect is an execution/L1 improvement, not a new edge.

Failing any of the three, the proposal is a reopening and requires the owner ruling that reopenings require — not a new program identifier.

#### 3A.3 DISC-001 — candidate discovery, not automatic trading

Create a daily candidate surface with two initial families:

**Oversold/reversal candidates**
- RSI(14) < 30 as a starting condition;
- PIT liquidity/universe eligibility;
- longer-term trend state;
- distance from 20/50-day averages;
- abnormal volume / trade-count participation;
- SIP spread/freshness;
- gap/VWAP context.

**Emerging momentum candidates**
- 20/60/126/252-day relative return;
- acceleration of relative strength;
- distance to 52-week high;
- RVOL and trade-count acceleration;
- VWAP persistence;
- sector relative strength/breadth context;
- SIP spread/freshness/liquidity.

**PIT and survivorship discipline applies to both families *(added at v0.8)*.** v0.7 names PIT liquidity/universe eligibility under the oversold family only; the emerging-momentum family draws on 20/60/126/252-day returns, 52-week-high distance and sector breadth, all of which are survivorship-biased unless computed on a PIT universe that includes names later delisted or removed. State it once for the whole program: **DISC-001 candidate history is generated on the PIT universe, or it is not evidence.**

`RSI < 30`, `most-active`, `mover`, or any single screener flag is a **condition**, not an alpha claim. DISC-001 outputs `CANDIDATE`, never `BUY`. A candidate family graduates only through a prospectively frozen signal hypothesis and cost-aware validation.

#### 3A.4 RANK — use new data where it belongs

Do not reopen the closed RANK-001 composite merely because ATP provides more variables. In the near term:

- use SIP spread/freshness/liquidity/shortfall for **candidate ranking**, execution capacity and portfolio construction;
- keep strategy-alpha ranking separate;
- permit a future RANK utility factor only if its predictive dimension, PIT availability, independence from relabelled maturity/operational quality, and reject condition are frozen prospectively.

The default use of ATP microstructure in RANK-like work is therefore **downstream execution/capacity utility**, not another weighted strategy score.

#### 3A.5 Profitability conversion discipline

Each new proposal must have a bounded conversion path:

```text
candidate/observation
    ↓
prospective hypothesis
    ↓
cost-aware backtest / walk-forward
    ↓
paper-trading candidate
    ↓
forward evidence
    ↓
promotion / reject
```

A workstream is stopped or deprioritized when it cannot identify a defensible next decision, fails its prospective gate, duplicates an existing exposure without incremental utility, or shows no plausible net-of-cost advantage.


### Cross-program Track X — LOW-001 Dynamic PIT conformance *(new at v0.14; parallel, not Plus-dependent)*

This track is **not sequenced behind MDQ capture, CEE population, DISC-MDQ, or GAPPER** and does not consume
their evidence. It may proceed in parallel under its own governed LOW-PIT specification.

Current order:

```text
#661 v1.0.1 conformance repair — MERGED
    -> pre-Dynamic-PIT safety/conformance compatibility
       (ownership provenance -> held READ visibility -> normal exit -> safety liquidation)
    -> concrete permaticker / owned-holdings provider wiring
    -> explicit LOW-001 PAPER liquidation path
    -> operator-visible ambiguity diagnostics + schedule/default repair + regression gates
    -> only then dynamic enrollment / broker eligibility / executable-set reconciliation
    -> Account 6 PAPER activation after LOW-PIT G0-G7
```

**No ATP gate is added for this track.** Its only integration obligation to ATP/DISC is to preserve the
cross-program boundary in §1.4 and avoid changing shared platform services in ways that alter DISC eligibility
or MDQ authority.

### Track 4 — Local SIP observation layer + per-strategy behavioral migration ADR *(drafting actionable now)*

The ADR must **not** say simply "all apps read `mdq_capture`." It must preserve the separation between:

#### A. Immutable research archive

- frozen SIP/IEX/OPRA partitions;
- single acquisition writer;
- read-only governed research consumers;
- manifest/hash identity;
- historical/research semantics.

#### B. Live local observation cache/service

- current-session mutable state;
- single designated writer;
- per-consumer freshness contract;
- explicit feed identity and provenance;
- staleness rejection;
- collector/stream-down behavior;
- restart recovery;
- bounded retention;
- no silent fallback that changes feed semantics.

**Platform-wide migration invariant:**

> **Install one high-quality local SIP data layer → measure each strategy's sensitivity → explicitly approve what that strategy may use SIP for → migrate individually.**

Common infrastructure does **not** imply common behavioral migration. Installing the local SIP layer, or making it available to all applications, authorizes **no** existing strategy to change its universe, ranking, selection, removal, sizing, entry timing, execution gate, or order behavior by itself.

#### Step 1 — Install the common local SIP observation layer

Account 7 remains the designated SIP acquisition identity. The live local cache/service exposes current observations with provider/feed identity, observation timestamp, local receipt timestamp, freshness/staleness state, and collector/code identity. The immutable archive remains separate.

At this step, existing governed strategies remain behaviorally unchanged. Infrastructure availability is not a feed-migration decision.

#### Step 2 — Measure each strategy's SIP sensitivity in shadow

Before a strategy consumes SIP as a governing input, compare its current governed behavior with the SIP-backed observation path without changing actual paper orders. At minimum measure whether SIP would alter:

- eligible universe;
- ranking;
- selected names;
- keep/remove decisions;
- target size;
- spread/liquidity/freshness gates;
- entry/exit timing;
- decision/reference price;
- order eligibility or execution diagnostics.

The shadow output is evidence only. A divergence is a finding, not an automatic behavior change.

#### Step 3 — Classify the permitted SIP impact

Each strategy/program receives one explicit SIP-authority level before migration:

| Level | SIP authority | Typical use |
|---|---|---|
| **L0 — Observation only** | SIP cannot change governed strategy behavior | MOM-SIP shadow, CEE, diagnostics, execution-quality evidence |
| **L1 — Eligibility / execution** | The underlying alpha/ranking remains unchanged; SIP may reject, defer, or constrain an action using approved spread/liquidity/freshness rules | Liquidity/spread gate, stale-quote rejection, execution eligibility |
| **L2 — Signal / selection** | SIP-derived inputs may change ranking, stock selection, removal, or sizing | SCAN candidate construction after approval; future SIP-native strategies |

A strategy defaults to **L0** until a higher level is explicitly authorized. L1 does not silently imply L2.

#### Step 4 — Require explicit owner/program approval

No strategy moves from its existing feed/input contract to L1 or L2 merely because the cache exists. The approving artifact must record, at minimum:

- strategy/program and version;
- approved SIP-authority level;
- exact local observation-service contract;
- provider/feed identity;
- sensitivity/shadow evidence reviewed;
- whether universe, signal, ranking, sizing, or only execution/reference behavior changes;
- conformance/regression evidence;
- governed identity/re-seal requirements;
- rollback target.

This is the per-strategy implementation of the v1.4.1 feed-migration rule.

#### Step 5 — Migrate strategies individually

Cutover is per strategy/program, never platform-wide by implication. Recommended order:

1. research/read-only consumers;
2. display/reference consumers;
3. scanner/candidate consumers;
4. existing paper strategies approved at L0;
5. individual L1 strategy migrations;
6. L2 signal/selection migrations only after their stronger evidence/requalification;
7. order-path/reference-price consumers **LAST**.

Examples:

- **MOM-001:** begin L0; its validated SEP/PIT ranking remains authoritative unless a later owner decision explicitly approves an L1 liquidity/execution overlay or stronger change.
- **SCAN-001:** SIP may eventually affect candidate eligibility/ranking, but only after G3/G7 evidence and explicit approval; candidate-not-signal remains unchanged.
- **GAPPER:** SIP may affect upstream fields only if the governed design and sequencing authorize it.
- **MR-002:** remains untouched while HOLD.

#### Step 6 — Preserve rollback and fail-closed semantics

Every migrated strategy must retain a documented prior contract and rollback path. A cache/collector outage, stale data, entitlement change, or feed mismatch must **not** silently select another feed or silently change strategy behavior.

The strategy-specific migration artifact must define:

- stale-data behavior;
- collector/cache-down behavior;
- whether the strategy fails closed, defers action, or uses an explicitly governed fallback;
- the exact prior feed/input contract restored by rollback;
- evidence fields needed to prove which feed/cache observation drove a decision.

Any order-path cutover remains Tier 3 and requires the accepted ADR plus the strategy/program-specific approval above, conformance evidence, identity update, and re-seal/re-qualification where required.

### Track 5 — Existing research queue *(not Plus-dependent)*

| § | Session | Gate | Est. |
|---|---|---|---|
| 5.1 | GAPPER Stage-0 **preparation only**: field-sufficiency harness against the approved hash-bound design; add SIP evidence only if that design permits it | ✅ **DONE 2026-08-22** — harness `74d569d` built + pushed, **PR #662**; census RUN (4 of 250 event-days). The design permits **neither** SIP nor IEX: it names no feed at all, so `source_vendor` stays `UNSET_OWNER_DECISION` pending a governed pre-execution decision | spent |
| 5.2 | Run GAPPER Stage 0 | G4 **and** a dataset improvement — the 2026-08-22 census puts sufficiency at **4 of 250** event-days, so G4 alone does not make Stage 0 executable | governed program |
| 5.3 | GAPPER disposition | after 5.2 | G5 |
| 5.4 | Profitability Acceleration **SF1 NO-START census**: min/max dates, eligible-security count, PIT fields, missingness, OOS/power; zero strategy code | **G5 by default**; earlier only by explicit owner sequencing exception | 4–6h |
| 5.5 | One PIT fundamental-change pre-registration/design | after NO-START gate + owner authorization | governed P2 |

This preserves the source queue: finish GAPPER, then one narrowly defined PIT fundamental-change hypothesis, then reassess.

### Track 6 — Reserve strategies *(specification/pre-registration only until G9)*

Uniform rule:

> Gate opens → pre-registration first → session doc → code.

No informal backtest or "warm-up" evidence before pre-registration.

| Reserve | Mechanism | Unlock chain | Pre-registration must settle |
|---|---|---|---|
| **A — Pairs / stat-arb** | Walk-forward pair regression; z-scored residual reversion; SIP execution-materiality gate | G6 → G9 | Economic pair families; independence from MR-002; costs; relationship-break/shortability rules |
| **B — OPRA Implied-Risk Overlay** | IV/skew/term stress → gross-exposure risk multiplier | G8 → G9 | Corpus sufficiency; fixed risk-score construction; exact risk mechanism modulated |
| **C — SIP Liquidity-Confirmed Continuation** | Intraday continuation confirmed by consolidated participation | G5 → G6 → G9 | Exact score; overlap/independence vs GAPPER |
| **D — SIP Liquidity-Shock Reversion** | Reversion conditioned on observable SIP liquidity stress | G6 → G9 | Strong proof it is not RNG-001 re-labeled; stress definition; falsification |
| **E — Options-Implied Earnings Risk Filter** | ATM-straddle implied move as ex-ante risk filter | G8 → G9 | Which separately registered strategy it filters; interaction design; no graft into MR-002/MOM-001 |

### Track 6A — Profit-oriented strategy queue *(new at v0.7; gates unchanged)*

The queue below expresses **economic priority**, not permission to bypass the existing gates. Observation/specification may occur where authorized; strategy code still requires its governing pre-registration gate.

| Priority | Program | Why it is ahead of alternatives | Required proof |
|---|---|---|---|
| **P1** | **MOM-001 L1 execution enhancement** | Fastest route to value because underlying alpha already exists | lower shortfall / fewer bad executions without degrading signal |
| **P1** | **GAPPER-SIP** | Direct use of premarket/opening SIP breadth, trades, RVOL, spreads and auctions | incremental predictive value net costs under GAPPER gates |
| **P1** | **MOM-CAND-001** | Uses participation acceleration to find potential leaders earlier | forward candidate hit-rate and independence from plain MOM |
| **P2** | **MOM-LIQ-001** | Tests whether consolidated liquidity adds alpha beyond cost reduction | incremental OOS/walk-forward utility vs MOM baseline |
| **P2** | **RSI-REV-001** | Independent short-horizon mechanism if conditioned correctly | net-of-cost reversal edge; reject if unrestricted RSI effect disappears |
| **P2** | **SIP-CONT-001** | SIP-native continuation conditioned on consolidated participation | prospective continuation edge and GAPPER overlap test |
| **P2** | **SIP-LSR-001** | Potential diversifier if liquidity stress creates temporary dislocation | prove not RNG relabel; robust cost/shortability model |
| **P3** | **RANK-EXEC / PORT-SIP** | Improves capital deployment after multiple valid edges exist | capacity/shortfall improvement, not arbitrary composite score |
| **Future** | **OPRA-RISK-001 / implied-risk overlays** | New risk dimension with IV/Greeks/term structure | sufficient OPRA corpus + specific strategy interaction |

Portfolio-level priority is **incremental net utility**, not the count of strategies. A new strategy that is highly correlated with MOM and adds no net-of-cost portfolio value should be rejected even if its standalone backtest is positive.

---

## 6. Recommended execution order

**Parallel LOW-001 note (v0.14).** LOW-001 Dynamic-PIT safety/conformance work may proceed independently of
the numbered ATP execution queue. Do not insert it between CEE/DISC/GAPPER items as if it consumed their
research gates; equally, do not allow ATP/Opportunity outputs to become LOW-001 execution inputs. Shared
infrastructure changes must pass both programs' regression/invariant suites.


### Completed before 2026-08-17 *(items 1–3 and 5 DONE at v0.4)*

1. ✅ Registration/plan corrected for Option 2A and the v0.3 definitions (PR #634).
2. ✅ Bar window resolved: 04:00–16:00 ET committed.
3. ✅ Smoke-corpus exclusion + research HTTP-capability invariant landed (pytest, structural).
4. ⏳ Restore clean CI wiring — separate small PR; **a precondition of G2 deployment** *(reclassified at v0.5)*. It need not block the #634 merge, but no governed capture starts until the feed-pinning guard is actually enforced in CI.
5. ✅ Draft PR open; nothing deployed.

### Completed 2026-08-17 *(items 6–8 DONE — block closed at v0.9)*

6. ✅ P-2 real-time SIP proof on the pinned account-7 identity — **REAL-TIME SIP CONFIRMED** (v2 proof; v1 mechanical FAIL preserved as the record of the criterion change).
7. ✅ MDQ §8 sign-off completed and §8.1 ratified in full — K thresholds, K2/K6 evaluability, K3 formula, K5 denominator/tolerance, universe/cadence, resource ceiling, session scope, review-date **rule**, cross-program admissibility (**MDQ corpus only**), value-extraction scope, ledger/holdout, and the **GO floor**.
8. ✅ Merged in order once the registration text and the code agreed: #634 `63c0c52` → #636 `be4235d` → #637 `0273012`.
8a. ✅ Governed deployment executed post-close (§3.3).

### Already discharged — state as of 2026-08-20 *(renumbered at v0.11; v0.10 used items 14, 15, 16, 19 and 20 twice each with different content)*

9. ✅ Provisioned the AWS capture root and deployed Phase A (§3.3).
10. ✅ D0 established from the 2026-08-19 admissible governed frozen partition; Program Start Record v0.2 effective.
11. ✅ First governed session verified end-to-end: sample → EOD → freeze → verify → S3 mirror.
12. ✅ MDQ capture continues on the approved collector identity; 2026-08-20 morning sampler healthy (33/33 per feed at 09:57 ET).
13. ✅ K5 timestamp ambiguity resolved **before coverage computation**: R2 (`0 <= ref_ts - cycle_ts <= 5s`).
14. ✅ `MOM-SIP-0` classified **NOT EVALUABLE** for the current population; do not manufacture a sample.

### Next — operational, independent of the exploration gate

15. ✅ **DONE — STORAGE REMEDIATION CLOSED 2026-08-20 16:5x ET.** All nine gate steps passed. *(Original item and its gate retained below.)* **Finish the 60 GB host resize after today's 16:45 ET freeze** — after the partition has frozen *and mirrored*, complete the filesystem expansion and **verify BOTH the block device and the filesystem report the new capacity**. ⛔ **Complete this before another image rebuild:** the shared Docker/capture storage coupling has already cost one lost day (08-18) and one near-miss (08-20). *(owner, 2026-08-20 PM)* Original item: grow the partition/filesystem and verify the OS sees the expanded capacity before the next rebuild.

    **Owner-specified gate, 2026-08-20 PM — run in this order, and stop at the first failure:**

    ```text
    1. 16:45 ET freeze SUCCEEDS
    2. verify the frozen partition
    3. confirm the S3 mirror SUCCEEDS
    4. growpart
    5. resize2fs
    6. lsblk
    7. df -h
    8. confirm the FILESYSTEM sees ~60 GB   <- not merely the EBS volume
    9. confirm the MDQ free-space guard has comfortable margin
    ```

    ⛔ **No image rebuild and no unrelated deployment may be mixed into this operation.**
    Once steps 1-9 pass, the storage remediation is **CLOSED** and the box is safe for a future
    image rebuild from a capacity standpoint. ⭐ Steps 1-3 gate the rest for a reason: growing a
    filesystem under an unfrozen or unmirrored partition risks the one copy of the day's evidence.
16. Continue K1/K3/K5/K6 evidence accrual strictly from the governed MDQ corpus; value-extraction outputs remain inadmissible to the MDQ verdict (§4.10.1, §7.2).
17. Build/run the offline §7.1 **admissibility check first**, then the K1/K3/K5/K6 calculators — a K-value computed over an inadmissible partition is not evidence, it is a number.

    **RESULT — measured, 2026-08-20 (steps 1-9 all PASS):**

    | Step | Evidence |
    |---|---|
    | 1 freeze | `Result=success`, `ExecMainStatus=0`, exit 16:45:06 EDT; sampler **395/395** |
    | 2 verify | independently re-run: `iex/2026-08-20: verified`, `sip/2026-08-20: verified`, **all 4 file hashes re-computed against the manifest match** |
    | 3 mirror | all **6** S3 objects present, **byte sizes identical to the local manifest** |
    | 4 growpart | partition `nvme1n1p1` 29G → **59G** |
    | 5 resize2fs | ext4 `/dev/root` 29G → **58G** |
    | 6 lsblk | disk `nvme1n1` **60G**; p1 59G mounted `/` |
    | 7 df | `/dev/root ext4 58G used 17G avail 41G 29%` |
    | 8 filesystem | **`size=61,285,326,848 B` (61 GB) — the FILESYSTEM, not just EBS** |
    | 9 guard | **PASS both legs**; `avail = 43,525,328,896 B` (43.5 GB) vs 12.37 GB before |

    ✅ **Evidence untouched:** today's partition still verifies on both feeds after the resize; all
    five containers up; alerts log unchanged (still only the two 08-18 entries).

    ⭐⭐ **NON-OBVIOUS CONSEQUENCE — the binding leg FLIPPED**, and the guard is now stricter in
    absolute terms. See the unit convention below before quoting any number.

    **GOVERNING STATEMENT — always quote the formula, never a remembered number:**

    ```text
    floor = max(10 GiB, 20% of filesystem capacity)
    ```

    **IMPLEMENTATION — and the gap between the formula and what actually fires** *(measured on the box
    2026-08-20; wrapper sha `109931ef063d3cf4...`)*. The wrapper computes in **rounded-up whole GiB**,
    so the realized threshold is NOT the formula value:

    ```sh
    size_gb=$(df -B1G --output=size  "$ROOT_HOST" | tail -1 | tr -d ' ')   # ROUNDS UP
    avail_gb=$(df -B1G --output=avail "$ROOT_HOST" | tail -1 | tr -d ' ')  # ROUNDS UP
    floor=$(( size_gb / 5 )); [ "$floor" -lt 10 ] && floor=10              # integer division
    [ "$avail_gb" -lt "$floor" ] && exit 1                                  # fail-closed
    ```

    Because **`avail_gb` is rounded UP**, `avail_gb >= floor` is satisfied by any
    `avail_bytes > (floor - 1) GiB`. The realized rule is therefore:

    ```text
    FAILS  iff  avail_bytes <= (floor_variable - 1) * 2^30
    ```

    | Quantity | Before (30 GB vol) | Now (60 GB vol) |
    |---|---|---|
    | exact capacity | 30,083,776,512 B (28.02 GiB) | **61,285,326,848 B (57.08 GiB)** |
    | `size_gb` (rounded up) | 29 | **58** |
    | nominal 20% | 5.6 GiB | **11.6 GiB** |
    | `floor` variable | `max(10, 5)` = **10** | `max(10, 11)` = **11** |
    | **EFFECTIVE BYTE THRESHOLD** | `<= 9,663,676,416` (9 GiB) | **`<= 10,737,418,240` (10 GiB = 10.74 GB)** |

    ⚠ **The realized threshold is ~1.6 GiB MORE PERMISSIVE than a true 20%** at the current size, because
    of the round-up on `avail`. Reconciles both real events: 08-20 morning `avail = 9,214,504,960 B`
    (8.58 GiB, `avail_gb` = 9) breached the then-threshold of 9 GiB; post-resize
    `avail = 43,522,101,248 B` (40.53 GiB, `avail_gb` = 41) passes with **30.53 GiB margin**.

    ⛔ **Operational evidence must report the exact byte threshold alongside any human-readable figure.**
    *(Earlier drafts of this plan said "12.26 GB" and then "11 GiB"; both were wrong — the first was a
    byte-level 20% the wrapper never computes, the second ignored the round-up. Corrected by measurement.)*

    ⭐ Confirmed by measurement: **Docker and the MDQ capture root are the same mount** (`/`) — the
    coupling behind the 08-18 loss and the 08-20 near-miss is **mitigated by capacity, not removed**.
    The post-redeploy free-space check therefore remains **mandatory**.

    ⚠⚠ **BROADENED 2026-08-24 — free space is NOT the post-redeploy check, it is one gate of five.**
    The 08-24 capture was lost to a redeploy that rewrote the environment file and dropped the
    registered acquisition credentials, while free space sat at a comfortable 16 GiB margin and every
    approved collector blob stayed byte-identical. A post-redeploy check scoped to disk passes and
    proves nothing. Run the full chain — **universe pin → acquisition credential presence →
    account-identity latch → free space → single-instance** — via
    `apps/backend/scripts/mdq_preflight_readiness.sh` (#673), transiently through SSM, before the next
    governed slot. See the 2026-08-24 state sync, sections B and C.

    ⭐ Confirmed by measurement: **Docker and the MDQ capture root are the same mount** (`/`) — the
    coupling that caused the 08-18 loss and the 08-20 near-miss is real, and is now merely well-provisioned
    rather than eliminated.

### Gate PX — clear before the first exploratory read *(§4.13; ordering corrected at v0.11)*

18. ✅ **DONE — signed 2026-08-19** at registration **§8.3** (merged `d43817b` #647; markers cleared `15da72c` #648). *(PX-1; corrected at state sync 2026-08-20 PM — carried as open from pre-sync v0.11.)*
19. **Record the K5 discrimination decision** (§4.11.1): whether K5 as frozen can return FAIL, and whether a non-discriminating PASS counts toward the ≥2 GO floor. *(PX-2)*
20. **Land `docs/design/MDQ-001_Rulings_2026-08-20.md` in Git** as Tier-0 documentation custody. *(PX-3)*
21. **Record the holdout identity** — period dates plus the symbol-subset hash, or an explicit record that only a period holdout exists (§3.5). *(PX-4)*
22. **Confirm the §4.12 pre-D0 sequencing** in the program-start record, including the image/container stamp and not only the git blobs. *(PX-5)*
22a. **Commit and push the Phase-A worktree to a draft branch** before the next state sync — uncommitted single-machine work is not custody (§4.13). *(added at v0.13)*
23. **Land the implemented Phase-A pre-read embargo** from `research/disc-mdq001-phase-a` after review/CI: `AuthorizedScope` mandatory; holdout denied before open; unauthorized rows dropped during parse; frozen-manifest verification; no unrestricted/widening mode; no live-corpus read in Phase A. *(PX-6 mechanism implemented/tested; repository custody pending)*

### After PX clears + discovery ledger is operational — value extraction during the active review window

⭐ **CEE and DISC-MDQ are NOT the same "Phase B" and must not be gated identically** *(owner refinement, 2026-08-20 PM)*. **CEE proceeds** once Gate PX is clear and the ledger exists — its population is viable. **The broad DISC-MDQ feature library stays HELD** pending the repeated population census, independently of PX and the ledger. Treating them as one blocked bucket would either stall CEE for no reason or start DISC-MDQ feature work on a population that does not exist.

**Owner-specified order** *(state sync 2026-08-22: items 1–4 are ✅ **DONE**; the list is retained as
the record of the sequence. ⛔ Only items 5–8 remain current — do not read 1–4 as outstanding work.)*:

1. ✅ **DONE** — **Issue and record the PX-2 owner ruling.** SIGNED 2026-08-20 at registration §8.4 (PR #651).
2. ✅ **DONE** — **Stamp the period holdout artifact + update its regression test in ONE commit** (PX-4b, PR #651). The deliberately failing test was INVERTED, not deleted, in the same commit.
3. ✅ **DONE** — **Build and land the append-only discovery ledger.** `50efc2f` (#654); proven OPERATIONAL on `ec2-paper` with acceptance PASS recorded at `e794fc7` (#656).
4. ✅ **DONE** — **CEE started and finished.** Authorized prospectively in `dcc2c97` (#657); **Session 001 CLOSED NOT EVALUABLE at n=17**, evidence at `07f745b` (#659); no promotion decision. Further CEE work is **population-gated**.
5. **Continue accumulating DISC snapshots and repeating the population census.** ⏭ *still current*
6. ⛔ **Do not build the broad DISC-MDQ feature library.**
7. If MOM-CORE remains the only usable population, open **only** the deliberately narrow **MOM-CORE × MDQ execution-quality observation**.
8. If the other families remain empty, **disposition them NOT EVALUABLE rather than widening the universe post hoc.**

23a. ✅ **DONE — precheck RUN 2026-08-20** (§4.10.4): **GAP 0, MOM-CORE 5 authorized, MOM-NEAR 0, OVERSOLD 0** across both existing snapshots. ⛔ **The GAP-family fallback this item anticipated is WITHDRAWN — GAP is empty too** (§4.10.6). **Repeat the census as snapshots accrue**; do not write feature code before it. *(added at v0.13; result + owner ruling recorded 2026-08-20 PM)*
24. **Build/land the append-only discovery ledger — and make it OPERATIONAL — before the first exploratory condition is computed.** ⛔ **Acceptance is the twelve-item gate at §4.10.7**, not "the code exists": items 10–12 require that the first exploratory read be *impossible* unless ledger initialisation succeeds, and that the holdout artifact and universe pin both load and verify **before** the reader opens a partition. *(owner ruling 2026-08-20 PM.)* Original item: **Build/land the append-only discovery ledger before the first exploratory condition is computed.** It must record condition/feature examined, timestamp, authorized scope, corpus/partition identity, code identity, disposition, and relevant denials. Pre-registrations must cite the resulting entries (§4.10.2).
25. 🛑 **CEE may be the first exploratory consumer, but the discovery ledger must be OPERATIONAL before CEE opens its first governed partition.** *(owner ruling 2026-08-20 PM — stated here to remove any ambiguity between "ledger built" and "ledger actually gating the first read".)* Then: **Run CEE first** on authorized non-holdout data: governed implementation-shortfall / SIP midpoint-spread reconstruction. `MOM-SIP-0` remains closed unless a future governed population changes that fact. ✅ **DISCHARGED — HISTORICAL** *(state sync 2026-08-22)*: the ledger was proven OPERATIONAL on `ec2-paper` (acceptance PASS, `e794fc7`), CEE was authorized prospectively (`dcc2c97`), and **Session 001 ran and closed NOT EVALUABLE at n=17** (`07f745b`). This item is no longer an instruction to start CEE; further CEE work is **population-gated**.
26. ⛔ **HELD pending the repeated census (§4.10.6):** do not start the general feature library. If MOM-CORE remains the only populated family, open a **deliberately scoped MOM-CORE × MDQ execution-quality observation** instead; if the others stay empty, record a governed population finding and stop those branches. *(owner ruling 2026-08-20 PM)* Original item: **Start the scoped feature library and the DISC-MDQ-001 enrichment sidecar** against authorized frozen partitions — read-only, additive research observations that do not alter `DISC-001-WATCHLIST / v0.3.0` eligibility, and that carry the §4.10.4 generalization limit in every output.
27. Run `RANGE-SIP-OBS-001` as a measurement study if its required symbols/fields are inside the frozen admissible corpus; do not reopen RNG behavior.
28. Draft/accept the local SIP observation + per-strategy migration ADR, including the six-step L0/L1/L2 adoption model.
29. Start bounded OPRA-CAP-001 capture after shared-host storage/durability behavior is demonstrated stable.
30. Convert only evidence-backed improvements into prospective L1/L2 or new-strategy registrations; fastest expected conversion target is MOM-001 L1 execution enhancement.

### Strategy queue

31. GAPPER developer preparation may continue.
32. ✅ **G4 obtained and CLOSED 2026-08-22** (confirmation of discharge; closure record in `docs/design/Gapper/`). **Superseded as an action.** The next GAPPER action is **not** "execute Stage 0" — it is **dataset acquisition and qualification**, then a prospective `source_vendor` decision, then a **re-run** of the preparation census. Executing Stage 0 against the present corpus would spend a governed execution to rediscover **4 of 250** event-days.
33. When evidence supports it, prepare the **MOM-001 L1 execution-enhancement** approval artifact before inventing a new momentum signal.
34. After GAPPER disposition, run the SF1 NO-START census and, if it passes, authorize one Profitability Acceleration design.
35. Reassess the portfolio using **incremental net utility**: alpha, drawdown, turnover/cost, capacity and correlation to existing sleeves.
36. Open new strategy pre-registrations in economic-priority order (`MOM-CAND-001` / `MOM-LIQ-001` / `RSI-REV-001` / SIP continuation-reversion) as their gates mature.
37. OPRA-derived strategies/overlays remain later-stage until the bounded options corpus is sufficiently mature.

---

## 7. MDQ evidence rules

### 7.1 Admissible corpus

A partition is admissible only if:

- captured after MDQ registration/sign-off;
- credential/account latch passed;
- explicit feed identity is present;
- universe/cadence/session scope match the frozen identity;
- freeze completed;
- `verify` passes;
- manifest contains all expected files and no stray unmanifested files;
- collector code identity is approved for the period;
- no post-freeze mutation occurred;
- **completeness meets the §4.9 thresholds** — observed/expected cycle ratio at or above the frozen minimum, and no contiguous gap exceeding the frozen maximum *(added at v0.5)*.

### 7.2 Inadmissible corpus

Exclude:

- Friday pre-registration smoke;
- scratchpad/manual exploratory captures;
- partitions produced by an unpinned credential;
- partitions with mismatched universe/cadence/session scope;
- unfrozen partitions;
- failed hash verification;
- recovered/reconstructed files whose bytes are not the originally frozen bytes;
- partitions failing the §4.9 completeness thresholds, even where `verify` passes *(added at v0.5)*;
- **any value-extraction / Track-3A output** — `MOM-SIP-0`, CEE, `DISC-001`, `RANGE-SIP-OBS-001`, feature-library artifacts — which are strategy/execution evidence and never qualification evidence (§4.10.1) *(added at v0.8)*.

### 7.3 Feed semantics

Every request remains explicit:

```text
feed=iex
feed=sip
feed=opra
```

Entitlement is never allowed to select governed semantics implicitly.

---

## 8. Open owner decisions blocking v1.0 freeze

**Status at v0.10.** G2 is closed and **D0 = 2026-08-19**; the review clock is active. Items **2, 9, 10, 11, 12, 13, 14, 15, 16, 17 and 18** were closed at G2; item 1 was already closed at v0.6. Items **3, 4, 5, 6, 7, 8, 19, 20 and 21** retain their prior numbering/status unless separately ruled *(v0.11: items 7 and 8 were omitted from v0.10's enumeration though both remain open; item 20 is new)*. Item 19 still gates exploratory/value-extraction access until explicitly signed; it no longer has any bearing on whether the review clock starts. The ratified text of every closed item lives in `docs/design/MDQ-001_Registration_v1_0_DRAFT.md`, not here; where this plan and the registration document differ, **the registration document controls**. Items keep their original numbering for stability.

1. **G1:** ✅ **RESOLVED 2026-08-17** — real-time SIP confirmed by the adjudicated v2 proof (v0.6 change 1). Retained for numbering stability.
2. **G2:** ✅ **CLOSED 2026-08-17** — all values ratified; the signed §8 block is the canonical text. *(original text retained)* MDQ §8 sign-off — ratify/adjust the now-drafted values: Phase-A universe; sampler cadence + retry policy (60s / continue-on-transient / abort after 30 proposed); the committed 04:00–16:00 session scope; resource ceiling; K3 union-grid definition (drafted); K5 fill population and quote-age tolerance (fields drafted, values open); K2 = NOT EVALUABLE unless G10 opens (drafted); durability choice (§6.4 — S3 byte-mirror recommended); final 60-day review date; **and the §4.11 verdict-reachability enumeration + minimum evaluable-criteria floor** *(added at v0.8)*.
3. **G4:** ✅ **CLOSED 2026-08-22.** GAPPER v2.1.1 §9 sequencing ruling — prerequisite **satisfied** (MR-002 Steps 1–2 complete 2026-08-10), not waived. Closure record in `docs/design/Gapper/`. GAPPER's remaining blocker is **data sufficiency**, not governance. See §8.8.
4. **Track 2:** ⏳ **STILL OPEN** — not blocking; Track 2 starts only after shared-host storage/durability behavior is demonstrated stable. OPRA-CAP-001 underlyings, option-selection rule, and storage budget.
5. **Track 4:** ⏳ **STILL OPEN** — drafting is actionable now; acceptance is G7. ADR number and exact architecture for the **live local observation cache**, distinct from the immutable archive, plus the per-strategy L0/L1/L2 approval and rollback record format.
6. **Early P2 work:** ⏳ **STILL OPEN** — the plan default remains **no**. whether the SF1 NO-START census may be pulled forward before G5. Default in this plan is **no**; an explicit owner exception is required.
7. **Plan location** *(added at v0.4)*: this series lives in `docs/Strategies/`; the hybrid-docs rule places governing implementation plans in `docs/implementation/` (Git-reviewable in a PR diff). Decide where v1.0 lands; the superseded v0.1 in `docs/implementation/` is deleted either way.
8. **GAPPER/MR-002 coupling** *(added at v0.5; premise superseded 2026-08-22)*: G4 is the ruling on whether GAPPER Stage 0 starts independently of MR-002. The original reasoning — that the MR-002 block was external (Sharadar escalation) and open-ended, so leaving Stage 0 behind it had no governance function — **still holds, and is now stronger**: MR-002 **terminated 2026-08-22 without an economic verdict**, so there is no longer a HOLD to be coupled to.

   ⚠ **Do not resolve G4 from this plan.** The plan is subordinate to the governing GAPPER artifact, which carries its own dependency. Read directly from the approved design (§9 ¶[172], quoted verbatim in the 2026-08-22 state sync): the dependency is *"Stage 0 of GAPPER begins only after MR-002 Steps 1–2 are complete"*, and its stated rationale is **owner-attention scheduling** ("owner adjudications may not compete"), not evidence. GAPPER was never entitled to an MR-002 result — §4 ¶[15] and §10 ¶[176] forbid evidence transfer in both directions.

   **Finding of fact:** MR-002 execution-order **Steps 1–2 completed 2026-08-10** — Step 1 (WP-A physical recovery control) closed and verified from the medium; Step 2 operational custodian named (Jay Wang, dual appointment recorded). The precondition was **satisfied on its own terms, before termination**.

   ⚖ **OWNER RULING 2026-08-22 — G4 CLOSED, prerequisite satisfied.** *"MR-002 Steps 1–2 were completed 2026-08-10; MR-002's later termination without an economic verdict does not reopen or invalidate that prerequisite. No evidence transfers between the programs."* A **confirmation of an already-satisfied dependency, not a decoupling waiver.** Governing record: `docs/design/Gapper/GAPPER_G4_Sequencing_Gate_Closure_Record_v1.0.md` (in Git — this plan is gitignored and cannot hold a ruling). ⛔ Narrow: §252, §8.1 (forward-accrual probation, clock unstarted) and §3 acceptance are all untouched.

   **K4 provision, unchanged and now operative:** if Stage 0 cannot run in the review window for reasons unrelated to SIP, record **K4 = NOT EVALUABLE** and drop it from the keep/cancel denominator; do not let a scheduling artifact count toward Cancel. ⭐ As of the 2026-08-22 census this is the **expected** outcome, and for a reason unrelated to both SIP and G4: measured data sufficiency is **4 of 250** event-days, and the 68-day cache span makes the target unreachable without a dataset improvement.
9. **K6 evaluability** ✅ **CLOSED 2026-08-17** — option **(a)**, the NOT-EVALUABLE-unless-observed clause. *(original text retained)* *(added at v0.5, §4.8)*: choose the NOT-EVALUABLE-unless-observed clause or admit the executor spread-gate rejection log as the IEX-side occurrence source (with schema, match tolerance, and admissibility frozen).
10. **K5 minimum fill count ✅ **CLOSED 2026-08-17** — accepted as proposed. *(original text retained)* `N_min`** *(added at v0.5, §4.3)*: 50 proposed; below it K5 is NOT EVALUABLE.
11. **Partition completeness thresholds** ✅ **CLOSED 2026-08-17** — accepted as proposed. *(original text retained)* *(added at v0.5, §4.9)*: minimum completeness ratio (98% proposed), maximum contiguous gap (10 minutes proposed), and their place in §7.1 admissibility.
12. **Shared-host resource floor** ✅ **CLOSED 2026-08-17** — accepted as proposed, and **enforced in the deployed wrapper**, not merely documented. *(original text retained)* *(added at v0.5, §4.9)*: free-space floor (max(10 GB, 20%) proposed), pre-write check point, abort-and-alert behavior, per-partition size ceiling.
13. **Review-date anchor** ✅ **CLOSED 2026-08-17** — confirmed: the clock runs from the first admissible governed capture. The **rule** froze at G2; the **date** stamps at the event. *(original text retained)* *(added at v0.5, §2 G3)*: confirm the 60-day clock runs from the first admissible governed capture rather than the entitlement date.
14. **Cross-program evidence admissibility** ✅ **CLOSED 2026-08-17** — resolved **MDQ corpus only**; the sealed account-7 records are context, never K-evidence. *(original text retained)* *(added at v0.6, §4.8 note)*: whether the sealed account-7 program evidence — the 2026-08-14 GLD IEX stub-spread occurrence and the 2026-08-17 SIP-side diagnostics showing the artifact class absent on SIP (plus the KMLM/UUP sparsity measurements) — may count toward **K1** (correction of a predeclared gate-material IEX observation defect) and/or **K6** (quote fidelity), or whether the MDQ verdict rests solely on MDQ's own governed corpus with the account-7 records cited as context only. **Default in this plan: MDQ corpus only.** If admitted, freeze the exact sealed-artifact identities (shas) and the comparison semantics at sign-off — no post-hoc selection.
15. **ATP Value-Extraction scope** ✅ **CLOSED 2026-08-17** — **APPROVED**, priority `MOM-SIP-0` → CEE → feature library → `DISC-001` → `RANGE-SIP-OBS-001`; Phase-A branches only (no auction / tick-trade capture expansion). *(original text retained)* *(added at v0.7, §4.10 / Track 3A)*: authorize or narrow the observation-only work that may run during the MDQ accrual window after G2. Proposed default authorization: `MOM-SIP-0`, CEE, SIP feature generation, DISC-001 candidate generation, and `RANGE-SIP-OBS-001` where the frozen corpus supports it. These outputs may motivate a later prospective strategy/overlay registration but **do not authorize strategy behavior changes, L1/L2 migration, reserve-strategy code, or reopening rejected RNG/MOM variants.**
16. **Verdict reachability** ✅ **CLOSED 2026-08-17** — **GO floor = ≥2 of K1–K6 both evaluable AND PASS; otherwise HOLD with a stated extension.** *(original text retained)* *(added at v0.8, §4.11)*: ratify the enumerated worst case, confirm GO remains reachable, and set the minimum evaluable-criteria floor for a GO verdict (≥2 of K1–K6 evaluated PASS proposed) and the disposition when the floor is not met (HOLD proposed).
17. **Discovery ledger and holdout reserve** ✅ **CLOSED 2026-08-17** — accepted as materialized; the holdout is quarantined until its governed release point. *(original text retained)* *(added at v0.8, §4.10.2)*: confirm the ledger requirement for any exploration-derived pre-registration, and fix the holdout period/symbol subset (final 20% of window + random 20% of universe proposed) — **selected and hashed before capture begins**, or the holdout is not a holdout.
18. **Value-extraction sequencing** ✅ **CLOSED 2026-08-17** — the proposed order is ratified. *(original text retained)* *(added at v0.8, §4.10.3)*: ratify or replace the proposed order (`MOM-SIP-0` + CEE → scoped feature library → `DISC-001` / `RANGE-SIP-OBS-001`), or set an explicit time-box for the parallel front.
21. **Holdout scope** ⏳ **OPEN — added 2026-08-20 (§4.10.5).** Rule on what each holdout protects: the period holdout and the MDQ-symbol embargo are enforceable and genuine for MDQ-derived hypotheses; a symbol subset confers **no** protection on a Sharadar-derived DISC hypothesis, because the deployed Watchlist displays those names (and, at Phase 1.1, their outcomes) to the operator every session. Record the ruling, record which class each holdout covers, and confirm that for DISC-001 hypotheses the clean test set is prospective post-freeze data. Also record whether the TSLA/XOM/AMZN fixture symbols are the governed holdout list or arbitrary test data.

20. **K5 discriminating status** ✅ **CLOSED — SIGNED 2026-08-20** at registration **§8.4** (PR #651): K5 as frozen cannot return FAIL for its coverage question; a non-discriminating PASS does not count toward the ≥2 GO floor; **no K5 definition is changed.** *(added 2026-08-20, §4.11.1.)*

19. **Undefined-verdict disposition** ✅ **CLOSED — SIGNED 2026-08-19** at registration **§8.3** (merged `d43817b` #647). *(state sync 2026-08-20 PM)* Original text retained: added 2026-08-18 (§4.12 ruling 3). `≥ 2 criteria evaluable and exactly 1 PASS` had no disposition under the signed §8 block or the ratified §8.1 block: not GO, not STOP under the old "no K criterion met" wording, and not covered by §8.1's HOLD clause. Proposed: **HOLD with one stated extension.** This is an **addition, not a correction**, so it needs an explicit signature — the sign-off stanza is in registration §8.2. **It must be signed before value-extraction work begins**, because §4.10.1 then forecloses revising a verdict clause. Does not block the first admissible capture.

---

## 9. Walk-away / operational discipline

### 9.1 Merge-readiness — which green is the merge signal *(new, 2026-08-20 PM)*

Learned merging #650. `main` branch protection requires exactly one context, **`Python CI Gate`**, and that job runs **last** — after the ~25-minute `Python FULL (backend)` suite. When `Python FULL` went green the PR was still `mergeStateStatus = BLOCKED`, because the Gate had not started.

```text
Python FULL PASS                                  != merge-ready
required Python CI Gate PASS + exact head
  + up-to-date base + walk-away elapsed           == merge-ready
```

⚠ Protection is **`strict: true`**, so merging any PR flips every other open PR to BEHIND. The cheap fix is to merge `origin/main` into the branch **locally** and push **once** — one CI cycle instead of push-then-update-branch's two.

📌 **This belongs in durable GitHub-operations guidance** (`.claude/skills/github-ops/SKILL.md` / GITHUB-OPS-001), not only in this plan — owner-noted 2026-08-20 PM, not yet done.

- Documentation/pre-registration sessions ≥1h.
- Collector deployment or cron changes on the live AWS box ≥2h.
- Any live-cache migration touching scanner/live observation ≥2h with rollback.
- Any order-path price-read cutover remains Tier 3, ≥2h, with explicit rollback and re-qualification requirements.
- Phase-B/K2, if authorized, is a separate controlled session with a hard abort rule.
- Laptop remains warm standby: no capture, streaming, or K2 reliability measurement.

---

## 10. What this plan does NOT authorize

- A second Algo Trader Plus subscription.
- MDQ direct use of `_6` credentials.
- Any MDQ order/broker capability.
- A WebSocket Phase-B implementation without G10.
- Direct live-consumer reads from the immutable MDQ archive.
- SCAN-001 becoming a trading signal.
- GAPPER Stage-0 execution against a corpus that fails the §3.1 contract. *(G4 CLOSED 2026-08-22 — sequencing is no longer the bar; **data sufficiency is**, measured at 4 of 250 event-days. Re-entry needs a dataset improvement + a prospective `source_vendor` decision + a re-run census.)*
- Populating `source_vendor` to make `contract_complete=true` without a qualified dataset behind it — that is a metadata fiction, not a satisfied contract.
- Reusing the 2026-08-22 preparation census as a Stage-0 result after the data source changes.
- MR-002 work of any kind. ⚠ It **terminated 2026-08-22 without an economic verdict** — a stronger bar than the former HOLD, not a weaker one. Any revival is a **new prospective program** (requirements R1–R5), never a continuation.
- Profitability Acceleration strategy code before the NO-START gate and pre-registration.
- Any reserve strategy code before G9.
- Reopening MOM variants, RNG fades, rejected event strategies, carry without data, optimizer-first work, or standalone options selling.
- **Value-extraction / Track-3A output entering MDQ K1–K6 adjudication** (§4.10.1, §7.2) *(added at v0.8)*.
- **Revising any K-criterion definition, threshold, tolerance, or evaluability clause after exploratory work on the corpus has begun** *(added at v0.8)*.
- **`DISC-001` or any candidate surface reaching the order path, a live scanner, or a sizing decision** — candidate is not signal, and no Track-3A output has L1/L2 authority *(added at v0.8)*.
- **Registering an exploration-derived hypothesis without its discovery-ledger citation and examined-condition count** (§4.10.2) *(added at v0.8)*.
- **Exploratory access to the holdout reserve** before its hypothesis is pre-registered *(added at v0.8)*.
- **Using `DISC-001-WATCHLIST`, Opportunity History/checkpoints, “Why it left”, DISC-MDQ enrichment,
  SIP/news features, or Opportunity ranks as LOW-001 Dynamic-PIT universe/ranking/weighting/order inputs.**
  That is a new economic mechanism and requires a separate prospectively governed strategy/research version.
- **Treating LOW-001 Dynamic PIT as authority to weaken static registration for other strategies.** Dynamic
  universe behavior remains explicit/opt-in; static remains the default.
- **Repairing an MDQ acquisition failure by pointing the collector at the unnumbered `ALPACA_PAPER_*`
  credentials.** Account 7's entitled acquisition identity and the Phase-A collector boundary are
  deliberate; changing credential identity to make a slot run is a **governance change, not an
  operational recovery** *(added at the 2026-08-24 state sync)*.
- **Salvaging, backfilling, reconstructing, or later manufacturing the cycles of a lost governed capture
  day**, or creating a partition directory in order to document a failure *(added 2026-08-24)*.
- **Treating a `mdq-freeze.service` exit 0 as evidence of a successful capture.** With no partition it
  short-circuits on `nothing to freeze`; the zero means NO PARTITION / no evidence *(added 2026-08-24)*.
- **Declaring a deploy/recreate operationally complete for MDQ on code-identity and health checks alone.**
  The complete registered acquisition environment must be proven ready before the next governed slot,
  via the full five-gate preflight — free space is one gate of five *(added 2026-08-24)*.
- **Relaxing the governed universe pin, the acquisition fingerprint, or any preflight gate semantics in
  order to make a readiness check pass** *(added 2026-08-24)*.

---

## 10A. Current-version custody rule *(updated at v0.13; state sync 2026-08-22)*

- **v0.14 is the sole active/current implementation plan**, and as of the **2026-08-23 owner ruling** its
  sole current copy lives at **`docs/design/ATP/AlgoTraderPlus_v1_4_1_ImplementationPlan_v0_14.md`**.
  ⛔ No second copy, no synchronized mirror, in any custody class.
- v0.13, v0.12, v0.11 and all earlier drafts are retained only as historical evidence of what was known at those dates.
- Do not apply operational/state updates to older versions.
- **Operational/state changes update v0.14 IN PLACE**, each tagged with its state-sync date. A new version number is for a substantive *design* revision, not for a state sync. The next substantive design revision would be v0.15 (or v1.0 if the owner deliberately freezes the plan), and must supersede v0.14 directly.
- *(v0.14: v0.13 remains the immediately prior current-plan record; this successor is a substantive cross-program design revision, not an in-place state sync.)*
- Governed program artifacts (registration, collector approval, Program Start Record, rulings, sealed reports) continue to control over this planning document where they conflict.

---

## 11. Review disposition

### v0.14 disposition — cross-program convergence without signal coupling

v0.14 adds LOW-001 Dynamic PIT because the implementation is now building reusable platform primitives
(permanent identity, owned-holdings visibility, PIT universe evidence, and execution eligibility) that sit
adjacent to ATP/DISC infrastructure. The safe integration is at that neutral infrastructure layer.

It explicitly does **not** authorize Opportunity/DISC/MDQ information to enter LOW-001's economic path.
Dynamic PIT remains a conformance repair to make the frozen PIT universe executable. If a future hypothesis
uses Candidate Watchlist membership, checkpoint outcomes, “Why it left”, SIP/news enrichment, or DISC-MDQ
features to improve low-vol selection, that is new research and must be registered separately.

### v0.13 disposition — holdout scope and population reality

v0.13 reopens nothing and consumes no review budget. It records what became visible only once the Watchlist product and the DISC-MDQ reader existed at the same time.

The reader's embargo is genuinely good work — mandatory `AuthorizedScope`, no widening flag, denial before partition open, exclusion proved on synthetic fixtures rather than by spot-checking live bytes. What it cannot do is protect a hypothesis built from inputs the product displays. `RSI-REV-001` and `MOM-CAND-001` run on Sharadar features, and those names are on Band B every session. So the symbol subset is a real holdout for MDQ-derived work and a **structurally void** one for Sharadar-derived DISC work. Naming that is cheaper than discovering it when a pre-registration needs untouched data — and it makes the prospective-data conclusion from Watchlist v0.3 §12.4(b) load-bearing rather than a precaution.

The second item is population. ETF exclusion in the frozen `v0.3.0` gates plus a 22-ETF MDQ universe leaves at most 28 names in the OVERSOLD/MOM-NEAR intersection, and the first deployed snapshot shows both families empty. `MOM-SIP-0` was closed for exactly this reason a day earlier. Counting the population before building the feature library costs an hour; building first and counting later costs the workstream.

### v0.12 disposition — state/sequencing sync

v0.12 does not reopen settled design. It records that DISC-MDQ Phase-A authorization/embargo infrastructure is implemented and green but uncommitted; makes the already-ratified discovery ledger an explicit executable prerequisite before Phase-B feature computation; records the unstamped machine-readable holdout artifact and LF-normalized universe-hash rule; and preserves the no-live-corpus-read boundary. Gate PX remains open until its remaining governance/custody items and repository landing complete.


**v0.11 disposition: PRE-EXPLORATION VERDICT INTEGRITY (2026-08-20).** No review budget consumed, no settled substance reopened. v0.11 exists because of a window that is about to close.

The program is in good shape: D0 landed clean at 395/395 on both feeds, the fail-closed guard did its job on 08-18, the scheduler defect was caught by measurement before it could produce sixty short partitions, and the K5 timestamp ruling was frozen before coverage was computed — which is the discipline working exactly as designed.

But §4.10.1's firewall has a property worth stating plainly: **it converts every unfinished governance item into a permanently unresolved one at the instant exploration begins.** *(State sync 2026-08-20 PM: this read "Ruling 3 is unsigned" — it was signed 2026-08-19 at registration §8.3; the argument stands for the items that remain.)* The K5 discrimination question (§4.11.1) is unrecorded. The symbol holdout's identity is not in the plan. And v0.10's §6 listed CEE and DISC-MDQ-001 *ahead* of the custody steps meant to precede them — the guard scheduled behind the thing it guards, the same shape as the feed-pinning ordering defect caught at v1.3. §4.13 turns those into one checklist that clears in an afternoon and gates only the first exploratory **read**, never the capture.

The substantive finding is §4.11.1, and it is the mirror image of §4.11. That section protected against criteria that can never be *evaluated*. K5, under the frozen R2 rule with unmatched fills excluded from the ratio, may be a criterion that can never *fail* — numerator and denominator are the same population, so it returns ~100% on any corpus. An auto-pass is worse than a NOT EVALUABLE, because it **counts toward the ≥2 GO floor**: the floor is then satisfied by K3 plus a tautology, which is precisely the single-criterion retention test §4.11 was built to prevent, arriving with a PASS stamp on it. The right response is not to retune K5 — that is forbidden and would be post-hoc — but to record its discriminating status now, while nobody has looked, and decide whether a non-discriminating PASS counts. If the honest answer is that only K3 could both be evaluated and fail, then the disposition is HOLD with a stated extension: a real outcome the ratified rules already provide for.

*(v0.10 carried no disposition entry of its own; its change summary above serves that role.)*

---

**v0.9 disposition: DEPLOYMENT STATE SYNC (2026-08-18).** No review pass consumed, no settled substance reopened, no new scope. The two-review-max budget on this series remains spent.

What changed is that the plan's own blockers cleared: G0 and G2 both closed on 2026-08-17, and the collector is deployed and scheduled. The document that described a package waiting for sign-off now describes a program waiting for one adjudicated partition — and, as of today, still waiting.

Three things are worth stating plainly rather than leaving implicit in a table.

**The interesting risk has moved from governance to operations.** Every remaining precondition is a fact about a running machine — did the timer fire, did both feeds sample, is there enough disk, did the mirror sync — and none of those are settled by a document. §3.4 is the proof: eleven §8 decisions were ratified, three PRs merged, a fail-closed wrapper deployed, and the program still lost its first day to 0.93 GiB of free space. Track 1 §1.5 is re-ordered for the same reason: the admissibility check comes before the K-calculators, because a K-value computed over an inadmissible partition is not evidence, it is a number.

**The guard working is the good outcome.** It would have been entirely possible to build a collector that started on a nearly-full disk, captured most of a session, ran out of space mid-afternoon, froze a clean-verifying partition with a two-hour hole in it, and passed `verify`. That partition would then have been adjudicated by someone who wanted the clock to start. §4.9 exists because that is the GAPPER-v1 failure mode, and today it was the difference between losing a day and contaminating a corpus. The one thing that did *not* work is that nobody was told: the failure metric has no alarm, so a 09:25 failure sat unnoticed for an hour on day one.

**The temptation the next few days create.** If the next partition falls short — a late start, a completeness ratio at 96% — the cheap move is to admit it anyway, since the thresholds were "only proposals" a day ago. They are not proposals any more; they were ratified before anyone had seen a governed partition, which is the only moment at which a threshold can be set honestly. Admitting a short partition to avoid losing another day converts a one-day delay into a corpus whose admissibility rule is whatever was convenient at the time. **The clock not starting is a normal outcome, not a failure.**

---

**v0.8 disposition: GUARDRAILS FOR THE v0.7 SCOPE (2026-08-17).** v0.8 consumes no review budget and reopens nothing settled at v0.3–v0.7. v0.7's redirection is right — a 60-day window in which data accrues but is never tested for value would be a poor use of both the subscription and the operator. But v0.7 pointed exploratory work at the same frozen corpus that adjudicates the qualification, and that creates two hazards the plan did not yet name.

The first is **contamination direction**: v0.7 blocks exploration→behavior, and v0.8 blocks exploration→criteria. Without the second, a K threshold could be "ratified" by someone who has already seen what the corpus will say.

The second is **the opposite of this platform's usual failure**. GAPPER v1 and MR-002's fourth opening were frozen designs that could not answer their question. An unconstrained search over eleven features and several candidate families has the inverse property: it always answers, and the answer is usually noise. The discovery ledger and the pre-committed holdout are the cheapest known correctives, and they cost nothing that v0.7 wanted to do.

v0.8 also adds the one check that spans everything added since v0.3 — **§4.11, whether a GO verdict is reachable at all** under the accumulated NOT-EVALUABLE clauses. Under current defaults it may rest on K3 alone. That may be acceptable; it must be chosen at sign-off rather than discovered in October.

**v0.7 disposition: OWNER-DIRECTED VALUE-EXTRACTION REVISION (2026-08-17).** This is not a new review pass and does not reopen the two-review-max budget. v0.3–v0.6 governance substance remains controlling. v0.7 adds one missing business layer: how the now-qualified ATP capabilities are converted into execution improvements, candidate discovery and prospective profitable-strategy development. The controlling priority is **measurable net strategy/platform value**, with research retained only where it protects or advances that objective.

The near-term conversion path is intentionally asymmetric: improve the validated MOM-001 implementation first; use GAPPER as the first SIP-rich open research program when its own gate permits; build candidate-only momentum/RSI discovery in parallel from frozen observations; and require a genuinely new mechanism before any rejected/redundant strategy family is reopened. RANK-001 remains closed; ATP microstructure enters ranking first as candidate/execution/capacity information, not as a new arbitrary strategy-utility composite.

**v0.6 disposition: STATE SYNC (owner-directed, 2026-08-17).** No review pass consumed and no settled substance changed. What moved: G1 closed with sealed evidence and an owner adjudication that itself demonstrated this plan's central theme — a frozen criterion (the v1 proof's all-symbol freshness rule) that could not answer its question on the instruments it was pointed at, caught and corrected by versioned re-issue with the failed run preserved. The remaining path to v1.0 is exactly the §8 sign-off (items 2, 4–14, with new item 14), the CI-wiring PR, and G2 deployment. The subscription's operational value is now evidenced by the account-7 program independently of this plan; the K1–K6 keep/cancel review remains the retention decision.

**v0.4 disposition: REVISE → v0.5 (substantive revision, not a third review pass).** v0.4 §11 records the review budget as spent; v0.5 accordingly adds only new evaluability/admissibility constraints and internal-consistency corrections. Everything v0.3/v0.4 settled — the L0/L1/L2 migration model, archive/live-cache separation, G10, durability, the gate chain, the strategy queue, and reserve sequencing — is **carried forward unchanged**.

What v0.5 adds is a single theme: **three of the six keep-criteria could have reached the verdict date unevaluable or unfalsifiable without anyone noticing until then.** K2 already carried that protection; K5 (population floor), K6 (observation dependency), and K4 (Stage-0 scheduling) now do too, and partition admissibility now tests sufficiency rather than integrity alone. Discovering at G3 that the corpus cannot answer the question is the expensive failure mode — it is the one MR-002's fourth opening and GAPPER v1 both hit, in different forms.

The proposed numeric defaults in §4.3, §4.8, and §4.9 (`N_min` = 50 fills, ≥98% completeness, ≤10-minute contiguous gap, max(10 GB, 20%) free-space floor) are **proposals for §8 ratification**, adjustable by the owner at sign-off and frozen thereafter — the same discipline as K1–K6.

After the §8 blockers are resolved (G1/G2 foremost), the plan promotes to **v1.0 implementation baseline** without changing the strategy economics or reserve-strategy queue.
