# Trading Workbench — LOW-001 Dynamic PIT Execution
## Design & Implementation Specification v0.5

**Strategy:** LOW-001 (`low-volatility`) · **Strategy ID:** 8 · **Paper account:** Account 6 / user 6
**Merged runtime on `main`:** **v1.0.3** (`956e932`, PR #667) · **Reserved:** v1.0.4 — Dynamic PIT acquisition
**Deployed runtime on ec2-paper:** **v1.0.2** (`0344337`) — *last known 2026-08-23; unverified since*
**DB `strategies.version` (strategy 8):** **1.0.1** — behind both
**Status:** PR S **MERGED, NOT YET DEPLOYED-AND-PROVEN** — S8.6 failed once and must be rerun from check 1 on v1.0.3. **PR S is still NOT the safe rollback baseline. Dynamic BUY remains PROHIBITED.**
**Date:** 2026-08-25 · **Review revision:** 2 (2026-08-25)

> **VERSIONING NOTE.** This review remains **v0.5**. Because dotted v0.5 has not yet entered Git custody,
> assigning v0.6 now would create the same phantom-version failure §0 is intended to prevent. Review
> revision 2 adds four review findings (§1.2); it is the same pre-custody document, and A2 commits
> whichever revision is current.

> ⚠ **CUSTODY: this document is UNCOMMITTED.** It supersedes the Git-tracked v0.4 in full and must be
> committed from a branch cut off `origin/main` before it is cited as governing. Until then the
> governing copy in Git is v0.4 (`ec889bb`) and this file is a review draft.

---

## 0. Numbering ruling — read this before citing any "v0.5"

Two different documents have carried a v0.4/v0.5 number. Only one series is governed.

| File | Bytes | Custody | Standing |
|---|---:|---|---|
| `…_v0.3.md` | 59,333 | Git (`main`) | superseded |
| `…_v0.4.md` | 13,817 | Git (`main`, `ec889bb`) | **the predecessor this document supersedes** |
| `…_v0_5.md` *(underscore)* | 75,250 | **untracked, primary worktree only** | ⛔ **off-series draft — RETIRE** |
| `…_v0.5.md` *(this file)* | — | uncommitted, custody pending | governing once committed |

The underscore file `…_v0_5.md` was written 2026-08-22 20:22, **before PR S merged**, by a session
working in the primary worktree. It numbered itself v0.5 against a v0.4 that did not exist at that
time; the branch session then deliberately numbered its own state sync **v0.4** (`ec889bb`) on the
reasoning that *"a phantom version in a governed series is worse than a corrected number."*

Consequences, stated plainly because the underscore draft is still on disk and reads as current:

- its §1.1 status table (`S5.5 NEXT · S5.6 OPEN · S6/S7/S8 OPEN`) is **wrong** — all shipped in #666;
- its §10/§16/§18 status columns and its "version assignment OPEN" gate are **wrong** — ruled in S8.1;
- its §21.5 prediction that the cost-basis consumer audit "expects zero" is **falsified** (§4 below);
- its §§2–9, 11–14, 17, 19–22 architecture, invariants, gates, non-goals and STOP conditions are
  **not** superseded by being in the wrong file — they were carried into v0.4 and remain governing.

**Do not delete the underscore draft without the owner's instruction** — it is the only copy of the
§21 live-state measurements in narrative form. Retirement is a custody operation, not housekeeping:

1. record the underscore draft's SHA-256 and byte count;
2. commit this dotted v0.5 from a branch cut from `origin/main`;
3. move the underscore draft to an `archive/` prefix with an explicit **NON-GOVERNING / OFF-SERIES**
   banner and retain its recorded hash; and
4. commit that archival move (or a manifest referring to the archived object) so the retirement itself
   is attributable.

Do not delete it merely because the dotted successor exists. This is the "untracked stale copy shadows
the governed file" failure mode, recurring.

### 0.1 Custody addendum — recorded at commit time, 2026-08-25

Two facts established when this document entered Git supersede the retirement procedure above.

1. **The off-series underscore draft no longer exists in the working tree.** It was removed during
   consolidation before custody, together with the interim dotted v0.5. This file — carrying review
   revision 2 — is the surviving document, committed here under the dotted governed name. Its
   pre-custody working name was `…_v0_5_2.md`, SHA-256
   `8ec462d73fd3c7ef69c8e9d5b4782c093a80b47175bd82ddafa3978a85a482a2`, 38,570 bytes.
2. **Nothing was lost, and the "only copy" justification was wrong.** The §21 live-state measurements
   are carried in full by **v0.3 §§21.1–21.7, already in Git** — stale live parameters, live version
   and status, the schedule-default defect, the registered universe, HON, the 42 MANUAL SELLs, and the
   tooling observations. The underscore draft was a *duplicate* of that narrative, not its only home.

⇒ **Task A4 (archive the underscore draft) is MOOT** and is closed without action. The §0 table and
retirement steps are retained above as the record of the numbering ruling, which stands; only their
disposal instructions are obsolete.


---

## 1. What changed since v0.4

v0.4 closed with PR S as an *implementation-complete candidate* and named the S8.6 deployment proof as
the last step before "safe rollback baseline." Two things then happened: PR S merged, and **S8.6 ran
and failed on the deployed runtime.** That failure is the substance of this document.

| # | Change since v0.4 | Section |
|---:|---|---|
| 1 | PR S merged — **#666**, squash → `main` `0344337`, LOW-001 **v1.0.2** | §2 |
| 2 | **S8.6 executed 2026-08-23 and FAILED at check 8** on deployed v1.0.2 — production-shaped identity lag exposed two defects that existing local fixtures did not exercise | §3 |
| 3 | Repair PR **S-R (#667)** merged → `main` `956e932`, LOW-001 **v1.0.3**; identity resolves on the **data frontier**, readiness became real | §3.2 |
| 4 | **Version table shifts.** 1.0.3 is consumed by the repair; **Dynamic PIT is now v1.0.4** | §5 |
| 5 | Box state diverged from `main`: box runs **1.0.2**, DB says **1.0.1**, `main` is **1.0.3** — a three-way split | §6 |
| 6 | ⚠ **Last-known v1.0.2 deployment hazard:** PAPER liquidation failed closed for all 39 holdings; current box state is unverified | §6.2 |
| 7 | 🐛 **v0.4 §21.5 cost-basis consumer audit returns a HIT** — `app/risk/engine.py` consumes `avg_entry_price`. By the doc's own conditional this **gates Account-6 activation** | §4 |
| 8 | The **cutover + S8.6-rerun runbook** is written down here for the first time — it previously existed only in session memory | §7 |
| 9 | Seven deployment gotchas and three CI lessons recorded, each of which cost real time | §8 |

### 1.1 Review corrections applied in this revision

This review makes **no strategy-economic change** and does not create implementation authority. It
tightens evidence and sequencing in five places:

- §2 separates the historical **PR #666 / 1.0.2** snapshot from the later **current-main / 1.0.3**
  snapshot. A current-main file must not be presented as evidence of what #666 itself contained.
- §3 replaces the absolute claim that the two S8.6 defects were "reachable only on the live box" with
  the narrower supported finding: production-shaped identity lag exposed them and the existing local
  fixtures did not.
- §4 records a **review recommendation, not an owner ruling**: do not accept next-sync gross exposure
  as sufficient compensation for a permissive pre-trade notional gate; repair or isolate the consumer
  before Account-6 activation, and characterize `app/orders/positions.py`.
- §6 distinguishes **deployment identity** from **control-plane metadata**. The DB version row must
  reconcile at cutover, but it is not sufficient evidence of what code is running.
- §7/§10 add a read-only preflight, already-cut-over branch, post-deploy IDLE assertion, exact-one-row
  version reconciliation, and dependency tracks so custody, baseline proof, risk repair and Dynamic-PIT
  engineering cannot be accidentally conflated.

**No architecture, invariant, gate definition, economics or non-goal changes.** LOW-001 remains
**Diversifier (B)**. No live-money authorization. Dynamic BUY still does not exist in any merged code.

### 1.2 Review revision 2 — four findings (2026-08-25)

- **§4 scope sharpened — the larger hole is by design, not corruption.** When `pos` is `None` (every
  market-order BUY opening a **new** name), `ref_price` is `0` and the notional gate passes trivially,
  always, per the author's own comment. The corrupted-row case makes an existing-name check ~10×
  permissive; the `None` branch makes new-name checks 100% permissive by design — and weekly rebalances
  open new names routinely. Both branches are now named in-scope for the §4.1 repair so it cannot
  under-scope to "don't trust corrupted cost basis." The gate is also **platform-wide** (every armed
  strategy submitting market orders shares it) — Track B gains read-only step **B0**.
- **A1 gains a retroactive conformance check** — if the 08-24 rebalance completed, its orders ran
  through the defective gate; re-evaluate them against a corrected reference price and record whether
  any would have been rejected (§7.0 item I).
- **B1 is dated.** The "IDLE through the next rebalance?" decision is due **before the Monday
  2026-08-31 10:32 America/New_York fire**: either B1 is ruled and closed, or an IDLE-through decision
  is recorded. Undated decisions drift.
- **§7.1 consistency:** step 7 names its mechanism as a governed exception to the no-direct-DB-edit
  posture; step 11 is conditional on step 10 having started the strategy.

---

## 2. PR S — merged

**PR #666**, squash-merged **2026-08-23 12:42:00Z** → `main` **`0344337787a6ce27df64995f7a556b19a4bf297a`**.
Head `1fe98bc9`, base `7bd35f1c`, 15 commits (S1→S8 plus a strict-base sync).

Two snapshots must be kept distinct.

**Historical PR-S snapshot (`0344337`, #666).** PR S delivered the universe/disposal and control seams
listed below and identified LOW-001 as **v1.0.2**:

```
apps/backend/app/universe/         __init__ · diagnostics · liquidation
                                   owned_holdings · security_identity · strategy_ownership
apps/backend/app/services/         strategy_control.py · paper_strategy_liquidation.py
apps/backend/tests/universe/       7 modules
apps/backend/tests/strategies/     test_activation_liquidation_ownership · test_paper_strategy_liquidation
                                   test_strategy_control_liquidation
low_volatility.py                  version = "1.0.2" · schedule = "32 10 * * mon"
```

**Current `origin/main` snapshot (after #667).** The same strategy template now reports
`version = "1.0.3"` because PR S-R consumed the next runtime version. That current-main value is
evidence of **#667**, not evidence of what #666 itself contained.

`app/universe/dynamic_symbol_resolver.py` is **absent**, as designed — that is PR B.

⛔ **Merging PR S did not make it the safe rollback baseline.** v0.4 §10 fixed the terminology and it
holds: the designation is earned by the deployment proof, not by the merge.

---

## 3. S8.6 — executed, FAILED, repaired

### 3.1 The failure (2026-08-23, ec2-paper)

`0344337` was deployed to ec2-paper and **failed at check 8**. The factor store was healthy —
22,104 tickers, 21,988 carrying a permaticker, identity coverage through 2026-08-20 — and the
runtime resolved nothing:

```
resolve("AAPL", today = 2026-08-23)  ->  None
resolve("AAPL", 2026-08-20)          ->  199059
```

**All 39 Account-6 holdings classified `identity_unresolved` and failed closed.**

**Defect 1 — `as_of` defaulted to the wall clock.** Vendor identity data always lags. On a Sunday, or
any morning before ingest, every effective interval has already closed and the entire book becomes
unattributable.

> ⭐ **The identity frontier is a property of the DATA, never of the calendar.**

**Defect 2 — readiness was structurally true.** `ready` tested `store is not None`, so it returned
`True` throughout — exactly the *"provisioned but useless reads as healthy"* hazard that S5.5's own
docstring had named. The readiness gate could not have caught defect 1.

Both defects survived the full local suite and CI. They were **exposed by production-shaped identity
lag on the live box**, while the existing local store fixtures had no lag and therefore did not exercise
the failing state. This record does **not** claim the defects were logically unreachable off-box; it
claims the pre-deploy test data did not reproduce the production data frontier.

### 3.2 The repair — PR S-R (#667)

Merged **2026-08-23 17:19:22Z** → `main` **`956e932c8860602060b627b9c8f7966d31565337`**, LOW-001 **v1.0.3**.
Narrow by design: no dynamic BUY, no enrollment, no broker resolver, no selection or economics change,
no Account 5 change, no risk/order-path change.

- default `as_of` = `MAX(lastpricedate)` **over rows that carry a permaticker**, taken from the
  **TICKERS** identity slice — deliberately not SEP, not the clock. A row with no permaticker cannot
  resolve at any date, so counting it would push the frontier past where identity can be established;
- explicitly-passed `as_of` is honoured unchanged — historical questions stay answerable at the date asked;
- `ready` now resolves a **deterministic probe end-to-end**; the three failure modes (no store, all-null
  permatickers, unestablishable frontier) are distinguished. Cached — a startup gate, not a per-call check;
- `current_identity_date()` joined the `SecurityIdentityResolver` **Protocol**, so a fake that omits it
  breaks visibly instead of silently recreating the bug. Seven test fakes updated;
- 14 new tests pin the production shape exactly (coverage 2026-08-20, AAPL → 199059). Mutation-verified:
  restoring the wall-clock default fails the headline test.

⭐ **1.0.2 is deliberately not reused.** It names a specific runtime that was deployed to Account 6 and
failed its proof. Silently replacing it with different code would make that failure unattributable.

---

## 4. 🐛 v0.4 §21.5 cost-basis consumer audit — CLOSED with a HIT

v0.4 (carrying v0.3 §21.5) required one bounded task: *enumerate every consumer of
`positions.cost_basis` / `avg_entry_price` / unrealized P&L on the LOW-001 monitoring, risk or
reporting path.* Its stated expectation was **zero**, with the conditional:

> "Zero consumers → the OPS-only classification stands. **Any consumer → the defect intersects this
> workstream and gates Account-6 activation until the consumer is repaired or isolated.**"

**The audit was run 2026-08-25. The answer is not zero.**

`apps/backend/app/risk/engine.py:315-320`, inside the `max_position_notional` gate:

```python
# Use limit_price if supplied; else avg_entry_price of current
# position; else 0 (market orders pass notional check here and
# are picked up by gross exposure on the next position-sync).
ref_price = req.limit_price or (pos.avg_entry_price if pos else Decimal(0))
resulting_notional = resulting_qty * (ref_price or Decimal(0))
if resulting_notional > limits.max_position_notional:
    ... REJECT / POSITION_CAP_NOTIONAL
```

`pos` is the **DB `positions` row** (`select(Position).where(account_id, symbol_id)`, `:284-288`) — the
same row the recomputer corrupts. LOW-001 sizes with **market orders**, so `limit_price` is `None` and
this branch runs on **every LOW-001 BUY into a name it already holds**.

**Two failure modes, one gate *(review revision 2)*.** The fallback chain fails open twice:

1. **Corrupted existing position** (the audit's hit): a HON-shaped `avg_entry_price` understates
   projected notional ~10× and the gate under-rejects, silently.
2. **New position, by design:** when `pos` is `None` — every market-order BUY **opening** a name —
   `ref_price` is `0` and the check passes trivially, always, exactly as the `:317` comment concedes.
   Weekly rebalances open new names routinely, so the gate is decorative for the most common BUY shape
   even where no row is corrupted.

Any §4.1 repair scoped only to mode 1 leaves the pre-trade control decorative under mode 2. Both are
in scope: the gate uses a trusted bounded execution-price reference for market orders (opening or
adding), or fails closed.

**Concrete consequence on Account 6.** HON's stored `avg_entry_price` is `21.05` against a true ≈`224`
(the recomputer overwrote with the last fill's notional instead of accumulating; `qty = 11` and
`market_value` are correct). The gate therefore computes `resulting_notional` roughly **10× too small**
against a 25,000 cap, and **under-rejects — it fails open, permissively, and silently.**

Full consumer list found:

| Consumer | Path | Assessment |
|---|---|---|
| `app/risk/engine.py` | **risk / order path** | ⛔ **the hit** — notional-cap reference price |
| `app/services/position_sync.py` | writer | the recomputer itself |
| `app/orders/positions.py` | order path | to be characterised |
| `app/api/v1/positions.py` + schema | reporting | operator-visible wrong P&L |
| `app/strategies/backtest_context.py` | research plane | out of scope for activation |

**Standing.** This is a **platform position-accounting defect**, not a HON anomaly — any restoration path
that ran the recomputer may have corrupted other rows. Per the conditional above it now **gates
Account-6 activation** until the risk-engine consumer is repaired or isolated.

⚠ **This is an owner ruling, not an implementation decision, and it is NOT taken here.** The comment at
`:317` shows the author knew market orders lean on this fallback and accepted it, relying on gross
exposure to catch up on the next position-sync. Whether that compensating control is sufficient — and
whether the defect is repaired, isolated, or accepted for Account 6 with the reason recorded — is the
owner's call. What is no longer available is the v0.4 assumption that no consumer exists.

### 4.1 Review recommendation — pending owner acceptance

**Recommendation: REPAIR OR ISOLATE; do not accept the next-sync gross-exposure catch-up as sufficient
compensation for this gate.** The reason is structural: `max_position_notional` is a pre-trade deny
control. A control that can understate projected notional by ~10× and only be corrected after execution
has already allowed the condition it is intended to prevent.

Minimum closure evidence should include:

1. characterize `app/orders/positions.py` before declaring the consumer audit complete;
2. prove the notional gate uses a **trusted bounded execution-price reference** for market orders, or
   fails closed when such a reference is unavailable — it must not use corrupted historical cost basis
   as a permissive substitute;
3. add a regression with a HON-shaped corrupted `avg_entry_price` showing the old path under-rejects
   and the repaired/isolated path cannot;
4. enumerate and repair, quarantine, or explicitly disposition other affected `positions` rows before
   Account-6 activation; and
5. open or link a **platform-level position-accounting defect record** so this issue is not silently
   closed merely because LOW-001 is isolated.

This is a review recommendation only. Until the owner rules, the standing gate remains **OPEN FOR
ACTIVATION**.

⛔ Note it does **not** touch selection or sizing: LOW-001's equal-weight construction never reads cost
basis. The blast radius is the notional **gate**, not the target book.

---

## 5. Version table — corrected

```
1.0.0   original                          superseded
1.0.1   conformance repair (#661)         <- what the DB still says
1.0.2   PR S safety/conformance (#666)    <- what the BOX still runs · FAILED its deployment proof
1.0.3   identity/readiness repair (#667)  <- what MAIN holds · not yet deployed
1.0.4   Dynamic PIT acquisition           RESERVED — PR B
```

v0.4 §8 reserved 1.0.3 for Dynamic PIT. **That reservation is void**; #667 consumed 1.0.3 and Dynamic
PIT moves to **1.0.4**. The ruling that `version` tracks the *runtime implementation* for this strategy
(S8.1) is unchanged and is what forced the bump.

---

## 6. Deployed state — the three-way split

### 6.1 Where each number lives

| Surface | Value | Note |
|---|---|---|
| `origin/main` template `version` | **1.0.3** | verified 2026-08-25 |
| ec2-paper running image | **1.0.2** (`0344337`) | last known 2026-08-23 — **not re-verified**; SSH to `13.217.236.134:22` timed out 08-25 (IP rotation, not a dead box) |
| `strategies.version` row, strategy 8 | **1.0.1** | never updated at the 1.0.2 cutover |

The DB row and the last-known running image disagreed after the 08-23 deploy. That is itself a finding:
the deploy path does not automatically reconcile `strategies.version`.

For **deployment identity**, require agreement between the authoritative build marker
`DEPLOYED_BUILD_INFO.json` and the running process/source self-report. The DB row is **control-plane
metadata that must be reconciled at cutover**, but it is not sufficient by itself to prove what code is
running. A future disagreement among these surfaces is a deployment nonconformance, not a reason to
discard one of the surfaces.

### 6.2 ⚠ Last-known operational hazard — conditional until live state is re-established

**Last known on 2026-08-23:** while the box was running PR-S v1.0.2, PAPER liquidation could not
liquidate Account 6 through `/stop {liquidate:true}` because all 39 holdings classified
`identity_unresolved` and the liquidator failed closed.

Do **not** restate that condition as current fact until item §10/A1 establishes the live build.

- **If the box is still on v1.0.2:** treat explicit PAPER liquidation as unavailable for LOW-001; use
  the governed manual flatten or the previously governed rollback image if flattening is required.
- **If the box is already on v1.0.3:** do not redeploy reflexively; establish deployment identity,
  verify the corrected resolver/readiness path, and rerun S8.6 from check 1.
- Plain `/stop` (no liquidation) was unaffected by the observed defect.
- The Monday **2026-08-24 10:32 America/New_York** rebalance had been deliberately allowed to run on
  1.0.2, but its completion is **not established in this document**.

⚠ **Unverified as of 2026-08-25.** Whether the 08-24 rebalance completed, and whether the §7 cutover
has since been executed, could not be established from the laptop. **Establish it before any mutation.**

---

## 7. Cutover + S8.6 rerun — the runbook

This runbook may be used only after the reviewed dotted v0.5 is in custody. The first phase is
**read-only** and must determine which branch is actually applicable.

### 7.0 Read-only preflight — establish reality before choosing a mutation

Capture, with timestamps:

```
A. access path and host identity (prefer SSM if available; do not assume the old /32)
B. DEPLOYED_BUILD_INFO.json target/source SHA
C. runtime-reported LOW-001 version and source identity
D. strategy 8 DB row: version + active/idle state
E. rebalance_completed evidence for the 2026-08-24 slot
F. open orders for Account 6
G. scheduler armed state + next LOW-001 fire
H. current security-identity frontier and resolver readiness
I. IF the 08-24 rebalance completed: its order list, re-evaluated read-only against a corrected
   reference price (current/bounded market price at order time), recording whether any order the
   defective gate passed would have been rejected by a sound gate  (review revision 2)
```

Decision:

- **Already on v1.0.3 / `956e932`:** do not redeploy. Reconcile the DB version if needed while strategy
  8 is IDLE, then rerun S8.6 from check 1.
- **Still on v1.0.2 / `0344337`:** use the cutover sequence below.
- **Anything else / mixed identity / missing evidence:** STOP. Reconstruct deployment state before
  changing strategy state.

### 7.1 v1.0.2 → v1.0.3 cutover sequence

Preconditions: the 08-24 rebalance **completed** (verify `rebalance_completed`, not `_started`) and no
open orders. If Strategy 8 is running, the cost-basis finding in §4 remains an activation gate; the
cutover itself restores disposal/readiness capability but does not authorize a new activation.

```
1.  capture pre-cutover evidence bundle from §7.0
2.  capture the 1.0.1 DB slot/version claim and the completed 08-24 rebalance claim
3.  stop strategy 8 — liquidate = FALSE
4.  verify strategy 8 is IDLE and still has no open orders
5.  deploy 956e932 using the governed full-cutover path
6.  verify backend health, scheduler armed state, Alpaca startup setting, build marker,
    runtime SHA/version, and that strategy 8 remains IDLE after deploy
7.  update strategies.version 1.0.1 -> 1.0.3 WHILE IDLE
    · a governed exception to the no-direct-DB-edit posture: recorded manual update,
      exactly one strategy-8 row, old value, new value, timestamp and row count captured
8.  verify no 1.0.3 claim exists for the 08-24 slot (no retroactive claim / catch-up)
9.  establish the one-epoch reload condition required for activation
10. start strategy 8 only if the standing activation gates permit it; NO backend restart between
    the reload proof and start
    · with the §4 activation gate OPEN, the gates do NOT permit a start — the strategy
      remains IDLE after cutover and that is the expected outcome
11. if step 10 started the strategy: verify next fire = 2026-08-31 10:32 America/New_York
    (a future fire, not a catch-up); if it did not: verify NO scheduled LOW-001 fire exists
12. rerun S8.6 FROM CHECK 1
```

⚠ A deploy/restart can re-set `has_pending_reload`. The reload/start evidence is valid for exactly one
runtime epoch. Do not treat a pre-restart reload as authority for a post-restart activation.

### 7.2 S8.6 — the twelve checks (v0.4 §11, expanded)

```
 1  running version reports 1.0.3
 2  running source SHA == 956e932 and agrees with DEPLOYED_BUILD_INFO.json
 3  owned-holdings provider READY · security identity READY
 4  LOW-001 CANNOT START without a usable provider          (readiness is fatal at init)
 5  PAPER liquidation authorized for LOW-001 ONLY           (another paper strategy still DENIED)
 6  schedule resolves Monday 10:32 America/New_York
 7  G0 config cleanup: orphan use_market_regime_filter REMOVED · fractional_shares reconciled
 8  identity resolves on the data frontier for all 39 Account-6 holdings   <- FAILED on 1.0.2
 9  completed rebalance week cannot be duplicated across restart/reload semantics
10  owned-but-unregistered holdings discoverable AND exitable
11  explicit PAPER liquidation reachable via the control seam
12  Account 5 unchanged
```

Check 9 should be proven with production-safe synthetic/read-only evidence when possible. Do not induce
an unnecessary live restart merely to satisfy the test if doing so would invalidate the one-epoch
reload/start condition being proved.

Routing may be established by production-safe synthetic or read-only evidence. What must not recur is
the capability existing as an uncalled object — or as a callable object that answers `None`.

### 7.3 Proof result semantics

- **All 12 pass:** PR S/S-R earns **SAFE ROLLBACK BASELINE** status for the disposal/readiness layer.
- **Any check fails:** record the first failure, preserve the evidence bundle, keep Dynamic BUY
  prohibited, and do not partially credit later checks as a passed deployment proof.
- A passed S8.6 does **not** close the §4 cost-basis activation gate and does not authorize Dynamic PIT.


---

## 8. Operational lessons — recorded because each cost real time

### 8.1 Deployment gotchas (found during the 08-23 S8.6 attempt)

1. `.deploy_src_sha` lives at **`/opt/workbench/app/`**, not `/opt/workbench/`, and
   `provision-from-s3.sh` **does not maintain it** — a separate ad-hoc recipe does. It was stale at
   `02e77a76` after the cutover, and `disc_mdq/ledger.py` **reads it as deployment identity**.
   ⭐ The authoritative marker is **`DEPLOYED_BUILD_INFO.json`**.
2. The box was a **mixed tree**: base `02e77a76` plus a surgical 4-file v1.0.1 overlay
   (`.deploy_low001_1.0.1.json`), 13 commits behind `main`. Full cutover was owner-authorized.
3. `build-deploy-archive.sh` **fail-closes** on a stale ADR-0043 baseline. Owner re-baselined
   `ea6db6e` → **`38f40b4` (#535)** via `ADR0043_IMPLEMENTATION_SHA`. Proofs required: ancestry PASS +
   governed-path diff EMPTY across all 10 paths.
4. `present_in_deploy_delta` in the marker is the **baseline→target** delta (~300 files), **not** the
   deployment blast radius (30 files). Do not misread it as "the risk engine was redeployed."
5. ⛔ **Never pass `LOSS_CONTROL_MODE=ENFORCE` to the paper box** — the provisioner would classify it as
   the ADR-0043 validation box and REFUSE. Live default is OFF; pass it explicitly.
6. The provisioner **rebuilds `.env` from scratch** and defaults `WORKBENCH_SCHEDULER_ENABLED` and
   `WORKBENCH_ALPACA_STARTUP_ENABLED` to **false** — pass the live values (`true`) explicitly or the box
   comes back **disarmed**. ⚠ This is the same class of event that erased `ALPACA_PAPER_6_*` and cost
   MDQ-001 the 08-24 capture day.
7. `ps` does not exist in the backend container — `ps | grep | wc -l` returns 0 for the wrong reason.
   Use **`docker top`**.

### 8.2 CI lessons (each cost a full 27-minute FULL run)

1. 🐛 A structlog fixture that swaps processors by hand **captures nothing** once `app/utils/logging.py`
   has configured logging, and every assertion silently degrades to comparing empty lists — *"no events"
   reads exactly like "no problems."* ⭐ Use `structlog.testing.capture_logs()` **and** replace the target
   module's cached logger (`cache_logger_on_first_use=True` binds the module logger **once**; no later
   `configure()` rebinds it). Verify in **≥2 test orders**, never in isolation only.
2. ⛔ `ruff format app/services` (a **directory**) reformatted ~60 unrelated files. Always scope format
   commands to exact files. Pristine `main` fails repo-wide `ruff format --check` (689 files), so a
   repo-wide check is **not** a valid gate here — the differential rule applies.
3. ⭐ Reviewing a PR with interleaved format churn: `-w` does **not** absorb ruff's line-rewrapping. Use
   an **AST diff with docstrings stripped** (ruff re-indents docstrings, changing the AST constant).
   That collapsed 67 apparent changes → **24 real** ones and proved `_select_targets` was semantically
   untouched — the strongest single piece of "no BUY-side change" evidence produced by PR S.
4. Add a **production-shaped lag fixture** for identity data: wall clock later than the latest
   permaticker-bearing `lastpricedate`, including a weekend/morning-before-ingest case. The headline
   test must fail if the resolver defaults to wall clock again.
5. A readiness test must prove a **usable read**, not object construction. Pin at least: no store,
   all-null permatickers, unestablishable frontier, successful deterministic probe, and a lagged
   production-shaped success case.

### 8.3 Observability note

`ownership_unclaimed` is emitted at **info**. The box was deployed with `WORKBENCH_LOG_LEVEL=INFO` so it
is visible — **at a WARNING deployment level it would be invisible by design.** Any change to the
deployed log level silently removes one of the five S6 diagnostics.

---

## 9. Gate status

| Gate | Status | Change since v0.4 |
|---|---|---|
| G-A risk allow/deny envelope | **CLOSED** — measured, no allowlist exists | — |
| G-B ownership design | **RULED** — set provenance + broker quantity, no schema change | — |
| G-C startup readiness | **CLOSED (re-earned)** — the v1.0.2 `ready` was structurally true; v1.0.3 resolves a probe | ⚠ re-closed by #667 |
| G1 static-strategy regression | **CLOSED** — denial proven by policy, not by absence of calls | — |
| G4 exit safety (normal path) | **CLOSED** in code | — |
| G4b capability | **CLOSED** in code | — |
| G4b operational reachability | **CLOSED** in code · **FAILED on last-known v1.0.2 deployment**; current box state unverified (§6.2) | ⚠ deployment proof pending |
| **S8.6 deployment proof** | ⛔ **FAILED 2026-08-23 · rerun from check 1 pending** | **new — the blocking gate** |
| **G0 Account-6 boundary** | **OPEN** — not established; params cleanup outstanding | — |
| **§21.5 cost-basis consumer audit** | ⛔ **CLOSED WITH A HIT — gates activation, owner ruling pending** | **new** (§4) |
| G2 research-selection conformance | OPEN — PR B/C | — |
| G3 dynamic enrollment correctness | OPEN — PR B | — |
| G5 failure/restart safety | OPEN — PR C | — |
| G6 reconciliation | OPEN — PR C | — |
| G7 paper-only first activation | OPEN — PR D | — |

### Terminology, held until earned

```
today                            PR S + S-R = MERGED, v1.0.3 deployment-unproven
after the S8.6 rerun passes      v1.0.3 (PR S + S-R) = SAFE ROLLBACK BASELINE
```

**Dynamic BUY remains PROHIBITED at minimum until that second line is true.** Passing S8.6 is
necessary, not sufficient: G2/G3/G5/G6/G7 and the §4 activation gate remain independent blockers.

---

## 10. What actually remains — dependency tracks

The previous single numbered list implied more serialization than the gates require and incorrectly
placed document custody after executable work. Use these tracks instead.

### Track A — establish and prove the disposal/readiness baseline

| Step | Work | Owner action needed | Blocks |
|---|---|---|---|
| **A1** | **Establish live state read-only** — 08-24 `rebalance_completed`; current build SHA/version; DB row; strategy state; open orders; scheduler state; resolver frontier. Prefer SSM if available; do not assume the old SSH `/32`. | no | every mutation |
| **A2** | **Put this reviewed dotted v0.5 in custody** from a branch cut from `origin/main`; record the underscore draft hash before archival. | review/merge | use of this runbook as governing |
| **A3** | **Cut over/reconcile to v1.0.3 if needed and rerun S8.6 from check 1** (§7), including G0 cleanup and durable deployment/version/config evidence. | authorization for mutation | PR B/C/D; safe rollback baseline |
| **A4** | After A3 passes, archive the underscore `…_v0_5.md` as **NON-GOVERNING / OFF-SERIES** with retained hash/provenance. | no deletion without owner instruction | stale-copy hazard |

### Track B — close the platform risk/accounting activation gate

| Step | Work | Owner action needed | Blocks |
|---|---|---|---|
| **B0** | *(review revision 2)* **Platform blast-radius enumeration, read-only:** all `positions` rows with implausible `avg_entry_price` across **all accounts** (recomputer may have corrupted more than HON); all currently-armed strategies that submit **market orders** (every one shares the defective gate, both failure modes). Output: a table the B1 ruling is made against. | no | informed B1 |
| **B1** | **§21.5 ruling** — repair, isolate, or explicitly accept-with-reason the `risk/engine.py` `avg_entry_price` consumer, **covering both §4 failure modes** (corrupted-row AND `None`-branch). Review recommendation is **repair/isolate** (§4.1). ⏰ **Due before the Monday 2026-08-31 10:32 America/New_York fire** — either ruled and closed, or an explicit IDLE-through-rebalance decision recorded. | **YES — owner ruling, dated** | Account-6 activation |
| **B2** | Characterize `app/orders/positions.py`; open/link the platform-level position-accounting defect; enumerate affected rows (folds in B0's output). | no | audit closure |
| **B3** | Implement and prove the chosen repair/isolation; add HON-shaped regression **and a `pos is None` new-position regression** showing the old path under-rejects and the repaired path cannot; disposition affected Account-6 position data before activation. | depends on B1 | Account-6 activation |

**Safety posture until B1–B3 close:** do not treat the current static strategy's next scheduled BUY as
implicitly authorized merely because Dynamic BUY is prohibited. The identified consumer is on the
existing LOW-001 market-order path. After A1 establishes live state, the owner should explicitly decide
whether Strategy 8 remains IDLE through the next rebalance while Track B is closed.

### Track C — Dynamic PIT acquisition programme

Track C may begin only after **A3 passes**. Final activation additionally requires **Track B closure**
and the remaining gates.

| Step | Work | Owner action needed | Blocks |
|---|---|---|---|
| **C1** | **PR A / PR B** — dynamic eligibility: broker asset resolution, `dynamic_symbol_resolver.py`, dynamic enrollment, identity-first reconciliation. **This code does not exist.** | no | G2/G3 |
| **C2** | **PR C** — executable set, `ceil(selected × 0.70)` floor, evidence + membership hash, restart/fault tests | no | G5/G6 |
| **C3** | **PR D** — Dynamic-PIT activation record at **v1.0.4**, runbook, Account 6 PAPER only | **YES — activation** | G7 |

### Dependency statement

```
A1 -> A2 -> A3 -> C1 -> C2 -> C3
                     -> A4  (after A3 pass)

B0 -> B1 -> B2 -> B3 ---------------> C3 activation
```

A passed A3 establishes the disposal/readiness rollback baseline. It does **not** waive Track B.
Track-B engineering may proceed in parallel with A3 once A1 has established live reality, but no
Account-6 activation may rely on the defective pre-trade notional control while B remains open.

**Rough weight.** A1–A4 are custody/operations. B is a bounded platform-risk repair plus data
disposition. C1–C3 are the entire remaining Dynamic-PIT *engineering* programme — PR S was the disposal
half of the acquisition/disposal symmetry invariant (v0.3 §4.6); the acquisition half has not started.

Against v0.4's Definition of Done, the satisfied lines are disposal, the READ/BUY split and diagnostics.
Every line mentioning PIT-200 reconstruction, dynamic purchase without re-registration, the executable
floor, selected-to-executable reasons and final reconciliation is **unstarted**.


---

## 11. Unchanged from v0.4 and v0.3

Economics frozen — 252-session realized vol, lowest quintile, equal weight, weekly cadence. No Account 5
change. No live-money authorization. No `positions` schema migration; the six reopening triggers of
v0.3 §5.4.2 stand. No symbol-table writes at enrollment. No retrospective quantity reconstruction, ever.
The acquisition/disposal symmetry invariant (§4.6) and the READ/BUY authority split (§4.7) govern
unchanged. The v0.3 §14 non-goals — including the total prohibition on DISC-001 / Opportunity /
DISC-MDQ coupling — stand. The v0.3 §22 STOP conditions stand, all eleven.

LOW-001 remains **B (Diversifier)**. Post-repair paper P&L is **not** an economic-validation dataset.

### Residuals still carried deliberately (v0.4 §9)

1. `_legacy_registration_liquidation` remains reachable for a static LIVE strategy with no provider
   wired; the readiness assertion is what keeps LOW-001 off it in a healthy deployment.
2. Repo formatting baseline — differential rule only.
3. Pre-existing mypy error in `app/research/disc001/engine.py`, verified at base `7bd35f1c`.

### Review disposition

This revision accepts the **dotted v0.5 successor / underscore off-series** ruling. It does **not**
promote this file to governing standing by itself: until the reviewed dotted v0.5 is committed from a
clean branch based on `origin/main`, Git v0.4 remains the governing document.

It also does not convert the §4.1 recommendation into an owner ruling. That decision must be recorded
explicitly before Account-6 activation.

**Do not change the strategy economics. Do not weaken static registration for other strategies. Do not
treat post-change P&L as validation. Do not ship the ability to acquire before the ability to dispose —
and note that as of today, the ability to dispose is proven in `main` but NOT on the box.**
