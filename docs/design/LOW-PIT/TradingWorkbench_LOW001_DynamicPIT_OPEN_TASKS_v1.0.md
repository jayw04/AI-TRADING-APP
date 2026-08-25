# LOW-001 Dynamic PIT — Open Task List
## Companion to Design & Implementation Specification v0.5 (review revision 2)

**Scope:** the remaining work only. Rationale, architecture, invariants and gate definitions live in v0.5;
this document does not restate them and **does not override them**.
**Date:** 2026-08-25 · **Task list revision:** 1.1 (owner review of PR #682 applied)
**Live state established:** 2026-08-25 via SSM read-only (§A1)

> **Standing constraints, unchanged.** Economics frozen. LOW-001 remains Diversifier (B). No live-money
> authorization. No Account 5 change. **Dynamic BUY remains PROHIBITED.** Passing v1.0.3 S8.6 is a
> *necessary prerequisite, not sufficient authority* — G2/G3/G5/G6/G7, Track B closure and C1–C3 all
> remain required, and final activation is a separate owner decision.

---

## 0. Status

Five tasks closed by read-only measurement. **Two change the scope of Track B, and the owner has now
ruled B1.**

| Task | Was | Now |
|---|---|---|
| **A1** live-state preflight | OPEN — blocked, SSH timed out | ✅ **CLOSED** — SSM read-only; §7.0 items A–I captured, **including H** |
| **A4** archive off-series draft | OPEN | ✅ **MOOT** — draft already gone; v0.3 §21 in Git holds the narrative |
| **B0** blast-radius enumeration | OPEN | ✅ **CLOSED** — screen result, stated narrowly; 5 market-order templates |
| **B2** characterize `app/orders/positions.py` | OPEN | ✅ **CLOSED** — and it **retracts the attributed HON mechanism** |
| **A1 item I** retroactive gate conformance | OPEN | ✅ **CLOSED BENIGN** — no 08-24 order would have been rejected by a sound gate |
| **B1** §21.5 ruling | OPEN — owner decision | ⚖ **RULED: REPAIR** (owner, 2026-08-25) — §B1 |

**Track A.** A3 is **operationally ready but governance-blocked on A2.** Every *technical* precondition
in v0.5 §7.1 is satisfied and the build parameters are pre-verified (§A3-PRE), but it may not execute
until A2 earns custody: v0.5 §7 states the runbook "may be used only after the reviewed dotted v0.5 is
in custody," and this companion does not override v0.5.

**Track B.** The screen found no current severe anomaly and HON is gone, so immediate data exposure is
small. **That is not the basis of the ruling** — see §B1.

---

## A. Track A — establish and prove the disposal/readiness baseline

### ✅ A1 — Establish live state (read-only) — **CLOSED 2026-08-25**

Captured via SSM (`i-084f47fe4e69192e9`, agent Online). SSH port 22 still times out on the rotated
`/32`; **SSM is the working access path** — do not spend time on the security group.

| § | Item | Measured |
|---|---|---|
| A | access path / host | SSM `AWS-RunShellScript`, `i-084f47fe4e69192e9`, running, EIP `13.217.236.134` |
| B | `DEPLOYED_BUILD_INFO.json` | `deployed_repository_commit = 0344337787a6…` · `adr0043_governed_paths_match = true` · `implementation_ancestry_verified = true` |
| B′ | `.deploy_src_sha` | `0344337787a6…` — **agrees** with the build marker (the 08-23 manual repair held) |
| C | running LOW-001 template | `version: ClassVar[str] = "1.0.2"` — read inside `workbench-backend` |
| D | `strategies` row id=8 | `version=1.0.1` · `status=PAPER` · `has_pending_reload=1` · `schedule=32 10 * * mon` · `user_id=6` · `risk_limits_id=NULL` · `cooldown_until=2026-08-24 14:33:56` (expired) |
| E | 08-24 rebalance | ✅ **COMPLETED** — signal `2851`, `{"reason":"rebalance_completed","iso_week":[2026,35]}` at `2026-08-24 14:33:03` |
| F | open orders, account 6 | **0** non-terminal. 08-24: 28 BUY + 5 SELL, all `MARKET`, all `FILLED` |
| G | containers | backend up 14 h (healthy); frontend/agent/mcp up 42–46 h |
| **H** | **identity frontier / readiness** | ✅ **PROBED 2026-08-25 14:47 UTC** — below |
| I | retroactive gate conformance | ✅ **BENIGN** — below |

**H — identity frontier probe** (read-only, v1.0.3 query semantics against the live store). Run
directly against `/app/data/factor_data.duckdb` rather than through the runtime, because the box runs
the pre-repair v1.0.2 resolver and cannot answer the question itself.

```
FRONTIER  MAX(lastpricedate) WHERE permaticker IS NOT NULL  =  2026-08-21
tickers 22,105 · with permaticker 21,989
deterministic probe  AAPL @ frontier 2026-08-21    ->  199059    <- v1.0.3 behaviour, CORRECT
same probe           AAPL @ wall clock 2026-08-25  ->  None      <- v1.0.2 behaviour, THE DEFECT
```

Two conclusions:

1. **The v1.0.2 defect is live and reproducible today**, with a four-day lag across a weekend. A
   liquidation attempted on the box right now would still fail closed on every holding. This is the
   measured confirmation of v0.5 §6.2, which until now was only a *last-known* condition.
2. **`199059` is the expected post-cutover value**, matching the assertion #667 pinned. S8.6 checks 3
   and 8 now have a known-good target rather than a hope.

⚠ Readiness itself is **not** assertable pre-cutover: v1.0.2's `ready` is the structurally-true version,
so a healthy reading from it would be meaningless. Readiness is proven at S8.6 check 3, post-deploy.

**Item I — retroactive conformance of the 08-24 orders.** Max `estimated_notional` across the 28 BUYs
was **$1,089.24** (COST); min **$290.48**; every order an incremental top-up. Against
`max_position_notional = 25,000` (user-6 GLOBAL row; `risk_limits_id` still NULL). **No order the
defective gate passed would have been rejected by a sound gate.** No retroactive nonconformance.

⚠ This is evidence that the completed 08-24 rebalance was benign and that immediate LOW-001 economic
exposure is small. **It is not a reason to accept the platform defect** — see §B1.

**⭐ Incidental finding — see [T1].** Signal `2811`, 14:32:02 on 08-24:
`{"reason":"pit_name_not_registered","n":6,"sample":["CB","CSX","TRV","PLD","HLT","ORLY"]}`.
Account 6 now holds **34** positions, down from 39.

---

### ☐ A2 — Put v0.5 (review revision 2) in custody — **IN REVIEW**

**Actual state:** PR **#682**, branch `docs/lowpit-v0.5-custody`, base `origin/main` (`148c3dc`),
worktree `C:/LLM-RAG-APP/wt-lowpit-v05`. Docs-only, Tier 0. Source draft recorded at SHA-256
`8ec462d7…`, 38,570 bytes (v0.5 §0.1); committed under the dotted governed name.

- [x] branch cut from `origin/main`
- [x] source hash + byte count recorded before any move
- [x] v0.5 rev 2 and this task list committed
- [x] PR opened
- [x] **owner review corrections applied** — this revision (1.1)
- [ ] exact-head CI green on the corrected head · **walk-away restarts from the corrected head**
- [ ] merge
- **Owner action:** review / merge. **Blocks:** citing the §7 runbook as governing, therefore **A3**.

### ☐ A3 — Cut over to v1.0.3 and rerun S8.6 from check 1

**Technical preconditions: SATISFIED** (A1) — 08-24 rebalance completed · 0 open orders · box identity
unambiguous and self-consistent · cooldown expired · build parameters pre-verified.
**Governance precondition: NOT satisfied — A2 must merge first.**

- [ ] re-run the §7.0 preflight at execution time (do **not** reuse A1's capture as the bundle)
- [ ] capture the 1.0.1 DB version claim and the completed 08-24 rebalance claim
- [ ] stop strategy 8 — **`liquidate = FALSE`**
- [ ] verify IDLE and still no open orders
- [ ] deploy `956e932` via the governed full-cutover path (§A3-PRE parameters)
- [ ] verify health · scheduler armed · Alpaca startup · build marker · runtime SHA/version · strategy 8 **still IDLE**
- [ ] update `.deploy_src_sha` to `956e932` by hand (the provisioner does not maintain it)
- [ ] update `strategies.version` `1.0.1 → 1.0.3` **while IDLE** — governed exception: record old value, new value, timestamp, **exactly one row affected**
- [ ] verify no 1.0.3 claim exists for the 08-24 slot (no retroactive claim / catch-up)
- [ ] **do NOT start strategy 8** — B1 is ruled REPAIR and B3a is not yet proven; IDLE is the required outcome
- [ ] verify **no** scheduled LOW-001 fire exists
- [ ] **rerun S8.6 from check 1** — all twelve checks, v0.5 §7.2; the check 3/8 target is `AAPL → 199059`
- **Owner action:** authorization to mutate — **granted 2026-08-25**, conditional on A2 merging first and Strategy 8 remaining IDLE.

#### A3-PRE — build parameters, **pre-verified 2026-08-25 (read-only)**

Three of the v0.5 §8.1 gotchas were checked against the actual target rather than carried as warnings.
**One would have hard-refused the build after Strategy 8 was already stopped.**

**1. ⛔ `ADR0043_IMPLEMENTATION_SHA` MUST be overridden.** `build-deploy-archive.sh:53` defaults to
`ea6db6e…`. Evaluated against target `956e932`:

```
IMPL_SHA=38f40b4 (owner re-baseline, #535)   ancestry PASS   governed-path delta EMPTY     -> BUILD OK
IMPL_SHA=ea6db6e (script default)            ancestry PASS   governed-path delta NON-EMPTY -> exit 3
                                                  apps/backend/scripts/adr0043_canary_lib.py
                                                  apps/backend/scripts/adr0043_churn_driver.py
```

⇒ export `ADR0043_IMPLEMENTATION_SHA=38f40b46906fc91497049924f7a62e7384d67653`. This matches
`adr0043_implementation_commit` already in the box's `DEPLOYED_BUILD_INFO.json`, so the override
**preserves** governed provenance rather than changing it.

**2. Runtime flags — reproduce the live values.** Measured in the running container;
`provision-from-s3.sh:30-34` defaults the first two to `false`:

| Variable | Live value | Provisioner default |
|---|---|---|
| `WORKBENCH_SCHEDULER_ENABLED` | **`true`** | `false` — box returns **disarmed** |
| `WORKBENCH_ALPACA_STARTUP_ENABLED` | **`true`** | `false` |
| `WORKBENCH_LOSS_CONTROL_MODE` | **`OFF`** | `OFF` ✅ |
| `WORKBENCH_LOG_LEVEL` | **unset** — relies on `settings.log_level` INFO default | — |

⛔ Do **not** pass `LOSS_CONTROL_MODE=ENFORCE` — `provision-from-s3.sh:47` would classify the host as
the ADR-0043 validation box and refuse.

⚠ `WORKBENCH_LOG_LEVEL` unset is a latent version of v0.5 §8.3: `ownership_unclaimed` is emitted at
info and survives only on the framework default. Consider pinning it explicitly at cutover.

### ✅ A4 — Archive the off-series draft — **MOOT / CLOSED 2026-08-25**

Closed without action. The underscore draft no longer exists (removed during consolidation), and the
"only copy of the §21 measurements" justification was wrong: **v0.3 §§21.1–21.7 in Git carry that
narrative in full.** Nothing was lost. Recorded in v0.5 §0.1.

---

## B. Track B — close the platform risk/accounting activation gate

### B-FINDINGS

**1. ✅ B0 data half — no current severe anomaly detected, stated narrowly.**

The screen: over all **86** positions on **all accounts**, flag any row where
`|market_price / avg_entry_price| > 3`. **Result: 0 rows flagged.** Separately, **the HON position no
longer exists** — it was exited.

⚠ **What this does and does not establish.** A ratio screen detects *gross* implausibility. It **cannot
prove exact cost-basis correctness**, and it would not detect a moderate error, a compensating error,
or a row whose `market_value` and `avg_entry_price` are wrong consistently. The supported claim is
*"no grossly implausible current row was detected by this screen, and the one known bad row is gone"* —
**not** "zero corrupted rows platform-wide," and **not** "the blast radius is empty."

- [ ] **optional strengthening**, only if the stronger claim is ever needed: reconcile current rows
      against the broker as authoritative, or against recomputable *complete* fill histories. Not
      required for B1, which does not rest on this measurement.

**2. ✅ B0 code half — the exposure is total, and this is the load-bearing finding.**

Five templates submit `OrderType.MARKET`: `combined_book`, `low_volatility`, `momentum_portfolio`,
`range_trader`, `sector_rotation`. **No template passes `limit_price` at all** — confirmed empirically:
**0** of user 6's orders, ever, carry one. So `req.limit_price` is `None` for every strategy-originated
order, and `max_position_notional` runs on the `avg_entry_price`-or-zero fallback every time.

**3. 🐛 B2 — the attributed HON mechanism is RETRACTED.**

v0.3 §21.5, carried into v0.4 and v0.5, states the recomputer *"overwrote `cost_basis` with the last
fill instead of accumulating it."* **That is formally retracted.** `PositionRecomputer.recompute()`
(`app/orders/positions.py:37-118`) replays **all** fills for the `(account, symbol)` pair in
`filled_at` order and accumulates correctly. Simulated against HON's measured history:

```
FULL history (all 4 fills)          qty=11  cost_basis=2468.29  avg_entry=224.390000   <- TRUE values
ONLY the 08-17 fill                 qty= 1  cost_basis= 231.59  avg_entry=231.590000
08-17 + the 2nd BUY                 qty=11  cost_basis=2468.29  avg_entry=224.390000
BUYs only (SELL fill missing)       qty=21  cost_basis=4709.69  avg_entry=224.270952

LIVE ROW OBSERVED                   qty=11  cost_basis= 231.589996  avg_entry=21.053636
```

The correct arithmetic reproduces the **true** values exactly, and **no subset of the fill history
reaches the observed row.**

**Evidentiary standing — keep these three claims distinct:**

| Claim | Standing |
|---|---|
| The recomputer does not overwrite-instead-of-accumulate; the old mechanism is wrong | ✅ **PROVEN** — code inspection + simulation |
| Two authoritative writers to `qty`/`avg_entry_price`/`cost_basis` with contradictory documented ownership | ✅ **PROVEN** — `position_sync.py:155-171,251-255` writes all three from the broker payload, while `positions.py`'s module docstring assigns them to the recomputer |
| HON specifically was corrupted **by** `position_sync.py` or **by** a restoration script | ⚠ **HYPOTHESIS, not proven causation** — circumstantially supported (`231.589996` is a float round-trip artifact; the recomputer is `Decimal` throughout) but no causal evidence was captured, and the row is now gone |

⇒ The defect **class** is contradictory writer ownership. The HON **instance** is unexplained and, with
the row gone, may now be unexplainable. Do not upgrade the hypothesis to a finding.

### ⚖ B1 — §21.5 owner ruling — **RULED: REPAIR** (owner, 2026-08-25, in review of PR #682)

> **REPAIR. Do not accept the zero-reference behavior.** Repair `max_position_notional` so that a market
> order uses a trusted, bounded current execution-price estimate, or **fails closed** when one cannot be
> established. Cover **both** the `pos is None` case and the corrupted-existing-position case. Keep
> Strategy 8 **IDLE** until that repair is proven, if A3 completes first.

**Reasoning of record.** The decisive failure mode is not HON. For every market-order BUY **opening** a
position, `pos` is `None`, `ref_price` becomes `0`, and the notional check passes trivially — across all
five measured market-order templates. That is a **deterministic bypass of a stated pre-trade deny
control**, and it is hard to reconcile with the binding *"risk gates are non-bypassable"* invariant this
programme is governed by.

⛔ Explicitly **not** a basis for the ruling: that the 08-24 orders were small ($1,089 max against a
$25,000 cap). The invariant must not depend on Account-6 position sizing staying small.

**Deadline — corrected.** The earlier "due before the Monday 2026-08-31 10:32 ET fire" wording was wrong,
because A3 leaves Strategy 8 IDLE and verifies that **no** LOW-001 fire is scheduled. The correct
condition:

> **B1/B3a must close before any Strategy-8 reactivation.** If the owner intends LOW-001 to participate
> in the 2026-08-31 rebalance, they must close before that intended start. Otherwise Strategy 8 remains
> **IDLE through that rebalance** — the default, requiring no further decision.

### ☐ B2 — remaining sub-items *(parallel, not on the critical path)*

- [x] characterize `app/orders/positions.py` — done, B-FINDINGS 3
- [x] enumerate affected rows — done; stated narrowly per B-FINDINGS 1
- [ ] open or link a **platform-level position-accounting defect record** for the dual-writer ownership
      conflict, and **formally retract** the "overwrote instead of accumulated" wording wherever it
      appears (v0.3 §21.5, v0.4, v0.5 §4) rather than carrying it forward
- [ ] reconcile the `positions.py` docstring with what `position_sync.py` actually writes — whichever way
      ownership is ruled, the two must stop contradicting each other
- **Owner action:** none. **Blocks:** nothing on the critical path.

### ☐ B3a — Risk-engine repair *(critical path)*

The activation-critical half. Once the risk engine no longer consumes unreliable cost basis for the
pre-trade notional check, **the LOW-001 activation intersection is isolated even if the broader
accounting-ownership cleanup remains open.**

- [ ] `max_position_notional` uses a trusted bounded current execution-price estimate for market orders, or **fails closed**
- [ ] regression: `pos is None` new-position case — old path passes trivially, repaired path cannot
- [ ] regression: HON-shaped corrupted `avg_entry_price` — old path under-rejects, repaired path cannot
- [ ] ⚠ **`app/risk/` requires ≥95% coverage** (`check_risk_coverage.py`); **Tier 3** — risk/order path
- [ ] ⚠ the **`risk-engine` skill is binding**. Tightening a gate that currently fails open is a behaviour
      change for **every armed strategy** — the four other market-order books must be regression-proven,
      not assumed, and a newly-rejecting gate is itself a live-safety event
- [ ] no position-data disposition required (B-FINDINGS 1)
- **Owner action:** none beyond the B1 ruling. **Blocks:** Strategy-8 reactivation; C3 activation.

### ☐ B3b — Dual-writer ownership repair *(parallel track)*

- [ ] rule which component owns `qty` / `avg_entry_price` / `cost_basis`, and enforce it in one place
- [ ] make the losing writer stop writing those fields, or make the ownership explicit and tested
- **Owner action:** ruling on ownership. **Blocks:** nothing on the critical path — tracked, not serialized.

---

## C. Track C — Dynamic PIT acquisition programme

⛔ **May not begin before A3 passes.** Final activation additionally requires **B3a** closure and the
remaining gates. **None of this code exists.**

### ☐ C1 — PR A / PR B, dynamic eligibility
- [ ] `app/universe/dynamic_symbol_resolver.py` — broker asset resolution (reads broker metadata; **writes nothing** to the symbol or risk layer, per G-A)
- [ ] dynamic enrollment path; identity-first reconciliation
- [ ] ⛔ the resolver may **not** live under `app/strategies/` (`check_strategy_isolation.sh` forbids the `app.brokers` import) — inject via `StrategyContext` as `submit_order_fn` is
- [ ] static-strategy regressions; **G2 / G3**

### ☐ C2 — PR C, target and reconciliation
- [ ] executable set · `ceil(selected × 0.70)` floor · `executable_set_below_floor` → HOLD · **log the raw ratio every rebalance, pass or fail**
- [ ] durable evidence model + membership hash; end-state reconciliation
- [ ] restart / partial-fill / fault tests; **G5 / G6**

### ☐ C3 — PR D, activation record
- [ ] final runtime version **v1.0.4** · runbook · Account 6 PAPER only · **G7**
- **Owner action: YES — activation.** Requires B3a proven.

---

## T. Standalone tasks surfaced by A1

### ☐ T1 — Capture `pit_name_not_registered` as a weekly measurement

Signal 2811 (08-24) recorded **6** PIT-selected names the runtime could not buy: CB, CSX, TRV, PLD,
HLT, ORLY.

**What this establishes:** one measured live instance in which six PIT-selected names were unavailable
to the statically registered universe. **It does not establish a recurrence rate** — a single
observation is not a pattern, and the count will vary with universe turnover. The signal is *eligible
for weekly measurement*; recurrence becomes evidence only once captured repeatedly.

- [ ] record the 08-24 instance (n=6, the six tickers, ISO week 2026-35)
- [ ] capture the same signal **each Monday until C1 lands** — free, and the natural before/after
      measurement for the Dynamic PIT case
- [ ] ⛔ do **not** treat it as authorization to accelerate C1 past A3
- **Owner action:** none.

---

## Dependency graph

```
A1 ✅ ──> A2 (#682, in review) ──> A3 ──> C1 ──> C2 ──> C3 activation
A4 ✅ moot

B0 ✅ ──> B1 ⚖ RULED: REPAIR ──> B3a risk-engine repair ──> Strategy-8 reactivation
                                                        └──> C3 activation
              └──> B2 remaining · B3b dual-writer   (parallel, NOT on the critical path)

T1 independent, read-only
```

**Critical path:** `A2 merge → A3`, and independently **`B3a`**.
**Gate on reactivating Strategy 8:** B3a proven. Until then, **IDLE**.

---

## What is NOT in scope

Unchanged from v0.5 §11 and v0.3 §14. Specifically not authorized by anything in this list: changing
LOW-001 economics; weakening static registration for other strategies; treating post-repair paper P&L
as validation; any DISC-001 / Opportunity / DISC-MDQ coupling; any Account 5 change; any live-money
authorization; **starting strategy 8 before B3a is proven.**

The eleven STOP conditions of v0.3 §22 remain in force.
