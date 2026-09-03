# Opportunity Page — Candidate Watchlist Design

| Field | Value |
|---|---|
| Document version | **v1.0 — Phase 1.1 product/ops closeout** |
| Date | 2026-08-27 |
| Status | Phase 1.1 **product functionality COMPLETE**. Backup **inclusion** CONFIRMED. Scheduled SQLite backup repair **DEPLOYED and production-proven** via scoped overlay `5c5969e`; host pin remains `07a9233`. 90-day JSON prune **FUTURE NATURAL PROOF**. **Not a strategy pre-registration. Not an authorization to trade or influence LOW-001.** |
| Supersedes | `docs/design/Opportunity Page/TradingWorkbench_Opportunity_Page_Watchlist_Design_v0_11.md` for **current implementation/design state**. v0.11 remains the Slice-3 closeout pin; v0.9 remains the Slice-2 deployed-state pin; v0.8 remains the Slice-1 deployed-state pin; v0.7 remains the Slice-1 contract pin. |
| Parent freeze | `docs/Strategies/TradingWorkbench_Opportunity_Page_Watchlist_Design_v0_3.md` — still the product/display contract that produced the Phase-1 freeze. Later revisions add history, MDQ boundary, and implementation contract; they do **not** reopen families, thresholds, screen identity, or research authority. |
| Parent plan | `docs/design/ATP/AlgoTraderPlus_v1_4_1_ImplementationPlan_v0_14.md` (current; supersedes v0.13). On conflict, the parent/governed artifact controls. |
| Screen identity | `DISC-001-WATCHLIST` / `v0.3.0` — unchanged. A gate change is a version bump and a ledger event, not a silent edit. |

No new research authority and no strategy behavior change. Frozen admission conditions remain v0.7 §3. Opportunity History remains independent of MDQ and of LOW-001 execution. Checkpoints remain read-time enrichment, not a new durable table.

---

## Change summary — v1.0 Phase 1.1 closeout (2026-08-26; amended 2026-08-27)

Scheduled SQLite backup repair **DEPLOYED and production-proven** via scoped overlay `5c5969e`; host pin remains `07a9233`. The 2026-08-26 backend restart happened **during RTH** (owner said go), not after close: Alpaca websocket reconnected, **0** unexpected orders. That is an observed operational event, not a failure.

| Item | State |
|---|---|
| Phase 1.1 product functionality | **COMPLETE** |
| History filters | **CLOSED / live** |
| SQLite backup inclusion | **CONFIRMED** (WAL-safe one-shot 2026-08-26) |
| `#690` scheduled backup repair | **CLOSED** — merged `5c5969e`, overlay deployed 2026-08-26T20:21Z, scheduled 02:00 ET proof 2026-08-27 |
| v1.0 design | **IN GIT** (`#691` / `08e4cc0`; this amendment records the scheduled proof) |
| 90-day prune survival | **FUTURE NATURAL PROOF** (~2026-11-12) |
| Strategy 8 | **IDLE / 1.0.3 / untouched** |

1. **§6.3 History filters / listing polish is CLOSED.** PR **#669** squash `e7f56c3` (date-range, family, symbol, screen-version, `presence` ∈ `{all,current,historical}`; `on_watchlist` from the **latest ingested candidate date**, optionally scoped by `screen_version`; `view=summary` with a symbol stays summary; row click uses `view=timeline`). PR **#681** squash `e58ee77` lists Watchlist/History only when status starts with `Source: MOM-001` (`isPatternValidatedStatus`) — **display-only**; admission unchanged. Owner display constraint 2026-08-25.
2. **§6.4 Scheduled SQLite backup repair: DEPLOYED and production-proven via scoped overlay `5c5969e`; host pin remains `07a9233`.** Inclusion remains the 2026-08-26 one-shot. Overlay sidecar `.deploy_disc001_backup_repair.json`. Backend-only rebuild **during RTH** 2026-08-26T20:21–20:24Z (not after close; websocket reconnected; 0 unexpected orders). Scheduled proof 2026-08-27T06:00:00Z / 02:00 ET: `daily_backup_complete` (`skipped: false`); new `workbench-2026-08-27.sqlite`; integrity `ok`; `opportunity_occurrence` present; live = backup = **100** rows, `2026-08-14`–`2026-08-21`; `healthz=ok`; no restart at 02:00; Range Trader still PAPER / `*/5`; open orders 0. Repair is **CLOSED**. 90-day prune remains an observation obligation, not unfinished product work.
3. **90-day JSON prune remains FUTURE NATURAL PROOF.** `SNAPSHOT_RETENTION_DAYS = 90` in `apps/backend/app/research/disc001/spec.py`. Earliest snapshots are `2026-08-14`, so the first natural prune is ~**2026-11-12**. Do not invent a prune. Do not claim CLOSED. Durable `opportunity_occurrence` rows must survive JSON prune.
4. **Three identities must not be collapsed** (updated 2026-08-26; do not use the v0.11 Slice-3 table as live state):

   | Identity | Value | Do not infer |
   |---|---|---|
   | Host / application pin | `.deploy_src_sha` = `07a92330108390f8d5299e36b411150c08b9160c` (B3a / `#683`) | not `0344337`, not `956e932`, not `e7f56c3`, not strategy 8's version |
   | DISC-001 sidecars | Slice 3, listing-filters, and `.deploy_disc001_backup_repair.json` → squash `5c5969e` | not a box-level pin replacement |
   | Strategy 8 live registration | **IDLE** / **1.0.3** / `32 10 * * mon` | not from the host code pin. Do not start it from this document. |

5. **History book (2026-08-26 proof):** **100** durable rows, `2026-08-14` → `2026-08-21`; families MOM-CORE **60** + GAP **40**; listing shows 60 MOM-001 names; 40 GAP unlisted; `SCREEN_VERSION=v0.3.0`; Alembic **unchanged** `c8e2a4b1d7f0`. Frontend-only rebuild 2026-08-26T12:06Z; backend **not** restarted for Opportunity UI. Shared root 58G, ~38G free, 34%. Open orders (strict NEW/ACCEPTED/…) 0.
6. **Still out of this closeout:** MDQ on the Opportunity surface, checkpoint persistence, `SCREEN_VERSION` bump, gate retune, order-path / broker / risk expansion, `EVIDENCE_NOT_FEEDBACK` fills filter, firing `disc001_watchlist_snapshot` except by owner request, Docker-prune, LOW-001 activation.

## Change summary — v0.11 Slice 3 closeout (2026-08-23)

1. **Phase 1.1 Slice 3 is CLOSED.** PR **#658** squash-merged to `main` as
   `81d63b44d97b1aae0ea0aa77efa9cdbba803a5c2` (2026-08-23T18:42:16Z). New-head CI on `369b4d1` was green
   (LIGHT including ADR 0002, FULL, Frontend, Python CI Gate). `SCREEN_VERSION` remains **`v0.3.0`**.
2. **Three identities must not be collapsed.** A full `81d63b4` tree extract would also have shipped
   LOW-001 1.0.3 (`#667`), which this slice does not authorize. Live production after closeout is:

   | Identity | Value | Do not infer |
   |---|---|---|
   | Host / application pin | `.deploy_src_sha` = `0344337787a6ce27df64995f7a556b19a4bf297a` (LOW-001 **1.0.2** / `#666` baseline) | not the Slice 3 squash; not strategy 8's version |
   | DISC-001 Slice 3 overlay | sidecar `/opt/workbench/app/.deploy_disc001_slice3.json` → squash `81d63b4` | not a box-level pin replacement |
   | Strategy 8 live registration | `PAPER` / **1.0.1** | not from the host code pin |

3. **Still out of this slice:** History filters/summary polish, SQLite backup inclusion, checkpoint
   persistence, MDQ, gate retune, order-path / broker / risk expansion, and any `EVIDENCE_NOT_FEEDBACK`
   fills filter. No 16:20 wait: Slice 3 is read-time, like Slice 2.

## Change summary — v0.11

1. **The LOW-001 boundary is now bidirectional.** v0.10 prohibited DISC → LOW-001 signal flow in detail but
   stated nothing about the reverse. v0.11 §7.4 adds it: LOW-001 decision records, holdings, rebalance
   intents, and orders are not Opportunity admission, ranking, badge, or sort inputs — and if LOW-001 (or any
   strategy) runs under an observation window governed by EVIDENCE_NOT_FEEDBACK, its live decision records
   are not surfaced as product content during that window, because a product page is an operator-feedback
   channel.
2. Nothing else changes. All v0.10 closures, freezes, and prohibitions stand exactly.

---

## Change summary — v0.10

1. **LOW-001 Dynamic PIT integration boundary is now explicit.** Opportunity / DISC-001 remains a product
   and observation surface; it is not an execution input to LOW-001.
2. **Shared platform infrastructure is allowed.** Both programs may reuse the governed permanent-security
   identity (`PERMATICKER_EFFECTIVE_INTERVAL_V1`), exchange-session/calendar semantics, Sharadar security
   metadata, PIT/as-of conventions, and evidence/version metadata.
3. **Signal coupling is prohibited.** Candidate membership, family labels, D1/D5/D10/D20/CURRENT
   checkpoints, current return, “Why it left”, and any future DISC-MDQ enrichment may not affect LOW-001
   universe membership, factor ranking, weights, rebalance timing, BUY/SELL authorization, or sizing.
4. **No Slice-2 code/design is reopened.** Checkpoints stay read-time; `opportunity_price_checkpoint`
   remains unbuilt; the 75-row durable-history proof and deployed identity remain exactly as v0.9 recorded.
5. **Future combination requires new governance.** Any hypothesis using Opportunity/DISC information to
   improve a low-volatility strategy is a separate research mechanism (for example LOW-002), requiring a
   prospective registration and strategy-version decision.

---

## Change summary — v0.9

1. **Phase 1.1 Slice 2 is CLOSED and DEPLOYED.** D1/D5/D10/D20/CURRENT checkpoints, adjustment-basis-safe returns, and GAP mixed-basis protection shipped as PR **#655**, squash-merged to `main` as `02e77a764d74cf43e965b0b228fbbdbfc9867b85` (2026-08-21T22:50:32Z) and overlaid on `ec2-paper`. No 16:20 wait: Slice 2 is read-time, not scheduled ingest.
2. **Overlay predecessor corrected to `50efc2f`.** Live `.deploy_src_sha` before Slice 2 was `50efc2fb8f8eb8d3b3a3fcdc000e5d181121e807` (PR **#654**), not `a2659be`. `.env` still said `WORKBENCH_CODE_VERSION=a2659be` because rsync excludes `.env`. Overlay was **`50efc2f` → `02e77a7`**.
3. **Q19 and Q20 moved to implemented and deployed.** Checkpoints are **deliberately read-time**. The optional `opportunity_price_checkpoint` table from v0.7 §7.2 was **not** created and is **not** the shipped design. Q20 returns compute only when proposal and later-print `adjustment_basis` match; GAP later SEP prints are facts with return withheld.
4. **Q17 current-return tightening is deployed.** Slice 1’s simple `change_pct` is now the CURRENT checkpoint return on a compatible basis (null when mixed).
5. **Durable history state unchanged by Slice 2.** Production remains **75** rows, `candidate_date` **2026-08-14 → 2026-08-20**, families GAP 30 + MOM-CORE 45. Alembic remains `c8e2a4b1d7f0`. Slice 2 must not and did not mutate `opportunity_occurrence`.
6. **Remaining Phase 1.1 sequence recorded.** Next functional slice is “Why it left,” then only the frozen indicators that slice needs, then remaining History UI/filter polish, then SQLite backup inclusion, then the natural 90-day JSON-prune proof. No MDQ, no `SCREEN_VERSION` bump, no checkpoint persistence, no gate retune, no order-path work.
7. **Owner closeout 2026-08-21.** Slice 2 acceptance evidence is sufficient: checkpoint structures present; session-based D1/D5/D10/D20; pending prints stay null; GAP mixed-basis withholds return; history stayed at 75 rows; no Alembic; no MDQ/order-path expansion; `SCREEN_VERSION=v0.3.0` preserved. Stale `.env` `WORKBENCH_CODE_VERSION=a2659be` was rsync-exclusion lag; **both env files were corrected** so deployed identity is consistent with `.deploy_src_sha` / `02e77a7`. Shared-root free space **~37 GiB → 35 GiB** is not a capacity incident; **keep the post-overlay capacity check** because Docker and MDQ still share `/`. **Do not reopen checkpoint logic** unless production usage exposes a defect.

---

## Change summary — v0.8

1. **Phase 1.1 Slice 1 is CLOSED.** PR **#653** / `a2659be`, Alembic `c8e2a4b1d7f0`, natural 16:20 auto-ingest, durable history **50 → 75**.
2. **Q15–Q18 implemented and deployed** *(Q17 current-return tightening completed at v0.9 / Slice 2).*
3. **ADR 0051 split shipped:** mapping in `app.research.disc001.history`; persist in `app.services.opportunity_history`.
4. **Slice 2 start contract** *(closed at v0.9).*
5. **v0.7 remains the contract pin.**

---

## Status — Phase 1.1

| Area | Status |
|---|---|
| Durable occurrence history | **CLOSED** |
| Idempotent ingest/backfill | **CLOSED** |
| History API/UI core | **CLOSED** |
| D1/D5/D10/D20/CURRENT | **CLOSED** |
| Adjustment-basis-safe returns | **CLOSED** |
| GAP mixed-basis protection | **CLOSED** |
| “Why it left” | **CLOSED** (PR **#658** / `81d63b4`, overlaid) |
| Numeric frozen-rule recomputation | **CLOSED** (only what “Why it left” requires; same PR) |
| Remaining filters/UI polish | **NEXT** (History filters / summary fields) |
| SQLite backup inclusion | **OUTSTANDING** (separate from filters) |
| v1.0 state sync | **AFTER** filters + backup |
| 90-day prune survival | **FUTURE NATURAL PROOF** |
| v0.9 state sync | **CLOSED** (owner-accepted Slice 2 closeout) |

Remaining Phase 1.1 work is History filters/summary fields, ordinary SQLite backup inclusion, a v1.0 state sync, and the later natural 90-day prune proof.

---

## 1. Product scope — unchanged

Phase 1 (Current Candidate Watchlist) and Phase 1.1 (Opportunity History) keep the v0.7 meanings. Phase 1.1 does not create a new alpha mechanism.

Slice 1 answers the durable-record half. Slice 2 answers labelled checkpoints and a consistent current return. Remaining Phase 1.1 work answers “why it later stopped satisfying the frozen rule,” with no sell/exit meaning.

---

## 2. Owner questions — implemented vs still open

This is a **product freeze**, not a research finding.

| Q | Recommended (v0.3 / v0.5) | State |
|---|---|---|
| Q1 Phase-1 SEP product surface | Yes | Implemented and deployed (`9e5cf65`, PR #646) |
| Q2 Band A + Band B; gappers move | Yes | Implemented and deployed |
| Q3 OVERSOLD `close > SMA(200)` | Yes | Implemented |
| Q4 Include `MOM-CORE` | Yes | Implemented, read-only MOM-001 |
| Q5 MOM-NEAR continuation within 15% of 52w high | Yes | Implemented, not breakout |
| Q6 Price ≥ $10, ADV ≥ $20M, cap ≥ $1B | Yes | Implemented |
| Q7 News headlines | Phase 1b | Deferred |
| Q8 Apply / assign on Band B | No | No control shipped |
| Q9 Title "Candidate Watchlist" | Yes | Implemented |
| Q10 DISC-001 product surface, no new program ID | Yes | `SCREEN_ID=DISC-001-WATCHLIST` |
| Q11 Ledger entry #0 | Yes | Recorded in `spec.LEDGER_ENTRY_0`; parent-plan markdown cross-reference still outstanding |
| Q12 Holdout = prospective post-freeze data | Yes (display exclusion owner's call) | Recorded; not implemented as a symbol filter |
| Q13 Empty / fail-closed / snapshot retention | Yes | Implemented; retention numbers frozen in v0.7 |
| Q14 Newest bar T−1 SEP | Yes | Implemented and labelled |
| Q15 Preserve every historical candidate occurrence | Yes | **Implemented and deployed** (`a2659be`, PR #653). Production: **75** rows through `2026-08-20`. |
| Q16 Add `/opportunities/history` user-facing history UI | Yes | **Implemented and deployed.** Slice 2 added checkpoint columns and family horizon. Remaining filters/summary polish is a later slice. |
| Q17 Preserve immutable proposal price/date/reason + current-price enrichment | Yes | **Implemented and deployed.** First-write proposal facts are immutable. CURRENT price and return are read-time. Return is null when bases differ. |
| Q18 Durable history survives 90-day local snapshot pruning | Yes | **Implemented** as a separate SQLite table. Production 90-day prune has not yet fired. Ordinary SQLite backup inclusion is still an operational check. |
| Q19 Show factual D1/D5/D10/D20/current checkpoints without treating them as strategy evidence | Yes | **Implemented and deployed** (`02e77a7`, PR #655). Read-time from split-adjusted SEP. Offsets are the symbol’s own later sessions, not calendar days. Pending D10/D20 stay null. Family horizon is shown so D20 on GAP (`hours–1d`) is a fact, not a hold. **Not persisted** in `opportunity_price_checkpoint`. |
| Q20 Corporate-action-adjusted comparison basis for long-lived price history | Yes | **Implemented and deployed.** SEP-family returns use matching `adjustment_basis=sharadar.sep`. GAP proposal is `scan.premarket`; later SEP prints may display as facts with return withheld. Do not invent a raw unadjusted proposal series. |

---

## 3. Frozen admission conditions

Unchanged from v0.7 §3. `SCREEN_VERSION=v0.3.0`. Empty OVERSOLD / MOM-NEAR remain valid. Do not retune after seeing history or checkpoints.

---

## 4. Slice 2 — what shipped

### 4.1 Code (research plane vs persistence)

ADR 0051 unchanged. Mapping/calendar math is pure; factor-store I/O stays in services.

| Piece | Location |
|---|---|
| Checkpoint math | `apps/backend/app/research/disc001/checkpoints.py` — `nth_session_after`, `adjusted_return`, `build_checkpoints`; no DB, no factor store, no MDQ |
| SEP series | `apps/backend/app/services/opportunity_history.py` — `history_price_series(..., adjusted=True)` |
| API | `GET /api/v1/opportunities/history` attaches `checkpoints[]`; `change_pct` is CURRENT return when comparable |
| UI | `/opportunities/history` — Return column, D1/D5/D10/D20, family horizon |

No Alembic. No `opportunity_price_checkpoint` table. JSON prune still must not delete durable history.

### 4.2 Read-time rule

```text
D1/D5/D10/D20 = nth later SEP session for that symbol after candidate_date
CURRENT       = latest SEP print on or after candidate_date
return_pct    = (later / proposal) - 1  iff adjustment_basis matches
              = None                    if pending or mixed basis
```

The v0.7 optional store shape remains historical design, not the shipped implementation:

```text
opportunity_price_checkpoint   -- NOT BUILT; do not add unless a later ADR says so
```

### 4.3 Merge / deploy identity

| Field | Value |
|---|---|
| PR | **#655** |
| Squash on `main` | `02e77a764d74cf43e965b0b228fbbdbfc9867b85` |
| Merged | 2026-08-21T22:50:32Z |
| Host | `ec2-paper` (`i-084f47fe4e69192e9`) |
| Overlay predecessor | **`50efc2f`** (PR #654). Not `a2659be`. |
| Overlay | `git archive` tarball; exclude `.env` and `data` |
| Rebuilt | backend + frontend only |
| Scheduler | remained `WORKBENCH_SCHEDULER_ENABLED=true` |
| Alembic | **unchanged** `c8e2a4b1d7f0` |
| `.deploy_src_sha` | `02e77a764d74cf43e965b0b228fbbdbfc9867b85` |
| `WORKBENCH_CODE_VERSION` | `02e77a7` |

Walk-away ≥1h and CI green (LIGHT + FULL + Frontend + Python CI Gate) before merge. First overlay attempt aborted on a stale `a2659be` pin check; retry accepted `50efc2f`.

---

## 5. Production proof — Slice 2 closeout

Verified on `ec2-paper` after overlay. No login values were placed on the SSM command line; history proof used the same enrich path as `GET /api/v1/opportunities/history` inside the backend container.

| Check | Result |
|---|---|
| `.deploy_src_sha` / `WORKBENCH_CODE_VERSION` | `02e77a7` |
| `healthz` | `ok`, including `"scheduler":"ok"` |
| Checkpoint names | PROPOSAL, D1, D5, D10, D20, CURRENT on every summary row |
| Durable rows | **75**, `2026-08-14` → `2026-08-20`; GAP 30 + MOM-CORE 45; **not mutated** |
| Alembic | `c8e2a4b1d7f0` |
| SEP pending D10/D20 | 19/19 summaries null — not synthesized |
| SEP later prints with return | 23; 0 later prints missing return |
| GAP leaked return | **0**; later SEP prices shown as facts |
| UI | `History.tsx` has `D1 D5 D10 D20` and `Family / horizon` |
| Screen | `DISC-001-WATCHLIST` / `v0.3.0` |
| MDQ / order path | none in checkpoints module imports |
| Shared root | 58G size, 23G used, **35G free**, 41% (pre-overlay ~37G free). Not concerning by itself. Keep the post-overlay capacity check: Docker and MDQ still share `/`. |
| Env identity | `.deploy_src_sha` and `WORKBENCH_CODE_VERSION` both `02e77a7` after correcting the stale `.env` value left by rsync exclusion |

**Phase 1.1 Slice 2 is CLOSED.** Do not reopen checkpoint logic unless production usage exposes a defect.

---

## 5.1 Slice 3 — what shipped and production proof

### Merge / deploy identity

| Field | Value |
|---|---|
| PR | **#658** |
| Squash on `main` | `81d63b44d97b1aae0ea0aa77efa9cdbba803a5c2` |
| Merged | 2026-08-23T18:42:16Z |
| Host | `ec2-paper` (`i-084f47fe4e69192e9`) |
| Overlay predecessor | **`0344337`** (LOW-001 1.0.2 / `#666`). Not `02e77a7`. |
| Overlay | Slice-3 runtime files from `81d63b4` (`git cat-file` LF tarball). Exclude `.env` and `data`. Did **not** extract full `main`. |
| S3 | `s3://workbench-backups-219024422756/bootstrap/disc001-slice3-81d63b4.tgz` Version ID `ncyHePuDA90rFEyI4cRQf7KYCHqD_iXe` |
| Rebuilt | backend + frontend only (`--no-deps`) |
| Scheduler | remained `WORKBENCH_SCHEDULER_ENABLED=true` |
| Alembic | **unchanged** `c8e2a4b1d7f0` |
| Host / application pin | **unchanged** `.deploy_src_sha` = `0344337787a6ce27df64995f7a556b19a4bf297a` (LOW-001 1.0.2 baseline) |
| Slice-3 sidecar | `/opt/workbench/app/.deploy_disc001_slice3.json` → squash `81d63b4` (not a pin replacement) |
| Strategy 8 registration | `PAPER` / **1.0.1** — do not infer from the host pin |
| `WORKBENCH_CODE_VERSION` | **absent** from both env files (not invented) |

### Production proof (2026-08-23T20:31Z)

Verified on `ec2-paper` after overlay. No login values were placed on the SSM command line; Why-it-left used the same enrich path as `GET /api/v1/opportunities/history` inside the backend container.

| Check | Result |
|---|---|
| `healthz` | `ok`, including `"scheduler":"ok"` |
| Durable rows | **75**, `2026-08-14` → `2026-08-20`; GAP 30 + MOM-CORE 45; **not mutated** |
| Alembic | `c8e2a4b1d7f0` |
| Screen | `DISC-001-WATCHLIST` / `v0.3.0` |
| UI | `History.tsx` has column **Why it left** and copy **frozen-rule display, not a sell or exit signal** |
| API disclaimer | `not_a_signal` = `Frozen-rule display, not a sell or exit signal.` on every computed row |
| Summary rows | 29 symbol/family last-occurrences |
| MOM-CORE later membership | 4 `no_longer_meets` as of `2026-08-20`: DDOG / HIMS (`2026-08-14`), HUM / NBIS (`2026-08-19`) — `No longer MOM-CORE: not in the frozen MOM-001 readout.` |
| Insufficient later data | 25 `unavailable` (15 MOM-CORE with no later SEP after last candidate date; 10 GAP with no later governed gappers file). **Not** labeled “left”. |
| OVERSOLD / MOM-NEAR | No live durable rows in those families; later-SEP frozen-gate path is shipped and test-pinned, not exercised by the current 75-row book |
| MDQ / order / risk / broker | none in `why_left.py` source; LOW-001 strategy 8 left `PAPER` / version `1.0.1` |
| Open orders | 0 |
| Shared root | 58G size, 31G used, **27G free**, 53% (pre-overlay 29G free). Not a capacity incident. Keep the post-overlay check: Docker and MDQ still share `/`. |

**Phase 1.1 Slice 3 is CLOSED.** Do not mix History filter polish, backup/prune, MDQ, checkpoint persistence, or order-path work into a follow-up of this slice.

---

## 6. Remaining Phase 1.1 work

Phase 1.1 product/ops work is **CLOSED**. The only leftover is the 90-day JSON prune, which is an **observation obligation**, not unfinished product work. Do not alter `SCREEN_VERSION=v0.3.0` or frozen family gates. Do not import MDQ. Do not persist checkpoints. Do not expand the order path.

### 6.1 “Why it left” — CLOSED

A **second labelled compute path**: re-evaluate the **frozen** family gates on a later Sharadar SEP bar (GAP: later governed gappers file). Not a sell or exit signal. Examples are factual, e.g. `No longer OVERSOLD: RSI14 = 34.2.` / `No longer MOM-CORE: not in the frozen MOM-001 readout.` Read-time. Sharadar/GAP only. No MDQ. Must not retune thresholds. Shipped as PR **#658** / `81d63b4`.

### 6.2 Numeric frozen-rule recomputation — CLOSED

Only the frozen indicators required to explain family-state changes (RSI/RS/RVOL as the “Why it left” slice needs them). Not a general research feature engine. Not chip-string parsing. Shipped with Slice 3.

### 6.3 Remaining History UI / filter polish — CLOSED

Shipped as PR **#669** / `e7f56c3` (filters) and PR **#681** / `e58ee77` (MOM-001 listing only). On live pin `07a9233` after the 2026-08-26 frontend-only rebuild. Do not mix into “Why it left.”

### 6.4 Operational watches

- **SQLite backup *inclusion* — CONFIRMED 2026-08-26.** One-shot WAL snapshot `/app/data/backups/workbench-2026-08-26.sqlite` has 100 rows, `2026-08-14` → `2026-08-21`, matching live.
- **Scheduled-backup *repair* — CLOSED 2026-08-27.** **DEPLOYED and production-proven** via scoped overlay `5c5969e`; host pin remains `07a9233`. Scheduled proof: `daily_backup_complete` at 2026-08-27T06:00:00Z / 02:00 ET (`skipped: false`); new `workbench-2026-08-27.sqlite`; integrity `ok`; `opportunity_occurrence` present; live = backup = **100** rows, `2026-08-14`–`2026-08-21`; `healthz=ok`; no restart at 02:00; Range Trader still PAPER / `*/5`; open orders 0. The overlay backend rebuild itself happened **during RTH** 2026-08-26, not after close.
- **First real 90-day JSON prune — FUTURE NATURAL PROOF.** `SNAPSHOT_RETENTION_DAYS = 90`. Earliest snapshot date `2026-08-14` → first natural fire ~**2026-11-12**. Must not delete durable history. Not a code slice today. Do not invent a prune. Do not claim CLOSED.
- Keep the post-overlay shared-root capacity check (Docker + MDQ share `/`). 2026-08-26: 58G size, ~38G free, 34%.
- Do not manually fire `disc001_watchlist_snapshot` unless the owner wants a non-natural run.
- Do not Docker-prune or delete old SQLite copies as a capacity act.

---

## 7. LOW-001 Dynamic PIT integration boundary *(new v0.10)*

### 7.1 Program independence

`DISC-001-WATCHLIST` / Opportunity History and LOW-001 Dynamic PIT are **independent programs**:

```text
Opportunity / DISC-001                     LOW-001 Dynamic PIT
product + observation                      trading-strategy conformance
-----------------------                    ----------------------------
candidate families                         PIT top-200 universe
history/checkpoints                        252-session realized vol
"Why it left"                              lowest quintile
UI/filtering                               equal-weight target construction
NO order authority                         governed order authority
```

Opportunity output SHALL NOT be used to admit, exclude, rank, weight, size, buy, sell, or time LOW-001.
The fact that the two programs run on the same platform does not create research authority between them.

### 7.2 Shared infrastructure that MAY converge

The programs may reuse neutral platform services where their semantics genuinely match:

- **Permanent security identity / ticker lineage:** `PERMATICKER_EFFECTIVE_INTERVAL_V1`.
- **Exchange-session calendar semantics:** common NYSE/America_New_York session handling where applicable.
- **Sharadar security metadata and PIT/as-of conventions.**
- **Evidence metadata:** source/version identity, `as_of`, adjustment basis, content hashes, and explicit
  refusal/exclusion reasons.
- **Read-only factual price/history services**, provided Opportunity's existing adjustment-basis rules and
  ADR 0051 research/persistence separation remain intact.

This is infrastructure reuse only. It does not create a common selector, target builder, ranker, or order path.

### 7.3 No schema or checkpoint rewrite for Dynamic PIT

v0.10 does **not** authorize an Opportunity-history migration merely to mirror LOW-001's new identity
evidence. The shipped occurrence/checkpoint behavior remains frozen. If a later Opportunity feature needs
ticker-change-stable identity, it should reuse the same permanent identity contract rather than invent a
second one, but that is a separately scoped product change.

Likewise, do not replace the shipped `nth_session_after` / adjustment-basis-safe checkpoint implementation
inside this boundary revision. Shared calendar infrastructure may be adopted only through a separate,
regression-proven product change that preserves the exact D1/D5/D10/D20 semantics.

### 7.4 Explicit forbidden data path — both directions *(bidirectional at v0.11)*

The following path is prohibited:

```text
DISC candidate / checkpoint / "Why it left" / MDQ enrichment
        -> LOW-001 PIT universe or low-vol ranking
        -> LOW-001 target / order
```

And the reverse is equally prohibited:

```text
LOW-001 decision records / holdings / rebalance intents / orders
        -> Opportunity admission, ranking, family labels, badges, or sort keys
```

Additionally, while LOW-001 (or any strategy) operates under an observation window governed by
EVIDENCE_NOT_FEEDBACK, its live decision records are not surfaced as Opportunity product content during
that window: a product page an operator reads mid-window is a feedback channel, whatever the intent.
Factual, already-public broker state (e.g., account positions in their own account UI) is unaffected —
this clause governs the Opportunity surface only.

Any future proposal for either path is **new research**, not Dynamic-PIT conformance and not product
polish. It requires prospective registration, a new strategy/economic version, and independent validation
before any order-path or admission use.

---

## 8. Still prohibited on this product path

- MDQ in history, admission, ranking, badges, or sort keys
- `SCREEN_VERSION` bump or family-gate retune
- Persisting `opportunity_price_checkpoint`
- Reopening Slice-2 checkpoint logic unless production usage exposes a defect
- Order-path / broker / risk expansion
- Treating checkpoints or “Why it left” as strategy evidence or an exit recommendation
- Feeding Opportunity/DISC candidates, checkpoints, family labels, “Why it left”, returns, or MDQ enrichment into LOW-001 Dynamic PIT selection, ranking, weighting, sizing, or orders
- Feeding LOW-001 decision records, holdings, rebalance intents, or orders into Opportunity admission, ranking, badges, or sort keys; surfacing live strategy decision records as product content during any EVIDENCE_NOT_FEEDBACK observation window

---

## 9. Authority reminder

If this document conflicts with the parent ATP plan, a signed owner ruling, an ADR, a pre-registration, or another governed program artifact, the higher-authority artifact controls. Shipping Opportunity History does not start `DISC-001` or DISC-MDQ research and does not promote any family into a strategy. Historical outcome display is product behavior; threshold retuning, MDQ-derived predictive claims, or promotion of exploratory MDQ features into product admission/ranking remain governed research.
