# LOW-001 Dynamic PIT — Open Task List
## Companion to Design & Implementation Specification v0.5 (review revision 2)

**Scope:** the remaining work only. Rationale, architecture, invariants and gate definitions live in v0.5;
this document does not restate them and does not override them.
**Date:** 2026-08-25 · **Task list revision:** 1.0
**Live state established:** 2026-08-25 09:1x UTC via SSM read-only (§A1 evidence below)

> **Standing constraints, unchanged.** Economics frozen. LOW-001 remains Diversifier (B). No live-money
> authorization. Dynamic BUY prohibited until v1.0.3 passes S8.6. No Account 5 change.

---

## 0. Status change since v0.5 rev 2

Four tasks closed this session, all read-only. **Two of them change the scope of Track B.**

| Task | Was | Now |
|---|---|---|
| **A1** live-state preflight | OPEN — blocked, SSH timed out | ✅ **CLOSED** — SSM read-only; §7.0 items A–I captured |
| **A4** archive off-series draft | OPEN | ✅ **MOOT** — draft already gone; v0.3 §21 in Git holds the narrative |
| **B0** blast-radius enumeration | OPEN | ✅ **CLOSED** — 0 corrupted rows platform-wide; 5 market-order templates |
| **B2** characterize `app/orders/positions.py` | OPEN | ✅ **CLOSED** — and it **disproves the attributed mechanism** |
| **A1 item I** retroactive gate conformance | OPEN | ✅ **CLOSED BENIGN** — no 08-24 order would have been rejected by a sound gate |

**Net effect on Track B:** the *data* half is empty (no corrupted rows survive; the HON position no
longer exists). The *code* half is worse than documented — see §B-FINDINGS. B1's ruling is now a
narrower and better-posed question than v0.5 rev 2 assumed.

**Net effect on Track A:** all cutover preconditions are satisfied. A3 is unblocked pending
authorization.

---

## A. Track A — establish and prove the disposal/readiness baseline

### ✅ A1 — Establish live state (read-only) — **CLOSED 2026-08-25**

Evidence captured via SSM (`i-084f47fe4e69192e9`, SSM agent Online; SSH port 22 still timing out on the
rotated `/32`, so **SSM is the working access path** — do not spend time on the SG).

| § | Item | Measured |
|---|---|---|
| A | access path / host | SSM `AWS-RunShellScript`, instance `i-084f47fe4e69192e9`, running, EIP `13.217.236.134` |
| B | `DEPLOYED_BUILD_INFO.json` | `deployed_repository_commit = 0344337787a6ce27df64995f7a556b19a4bf297a` · `adr0043_governed_paths_match = true` · `implementation_ancestry_verified = true` |
| B′ | `.deploy_src_sha` | `0344337787a6…` — **agrees** with the build marker (the 08-23 manual repair held) |
| C | running LOW-001 template | `version: ClassVar[str] = "1.0.2"` — read inside `workbench-backend` |
| D | `strategies` row id=8 | `version=1.0.1` · `status=PAPER` · `has_pending_reload=1` · `schedule=32 10 * * mon` · `user_id=6` · `risk_limits_id=NULL` · `cooldown_until=2026-08-24 14:33:56` (expired) |
| E | 08-24 rebalance | ✅ **COMPLETED** — signal `2851`, `{"reason":"rebalance_completed","iso_week":[2026,35]}` at `2026-08-24 14:33:03` |
| F | open orders, account 6 | **0** non-terminal. 08-24 activity: 28 BUY + 5 SELL, all `MARKET`, all `FILLED` |
| G | containers | backend up 14h (healthy); frontend/agent/mcp up 42–46h |
| H | identity frontier | *not separately probed — superseded, the box runs the pre-repair 1.0.2 resolver* |
| I | retroactive gate conformance | ✅ **BENIGN** — see below |

**Decision per §7.0: the box is still on v1.0.2 / `0344337`. Use the §7.1 cutover sequence.**

**Item I — retroactive conformance of the 08-24 orders.** Max `estimated_notional` across the 28 BUYs
was **$1,089.24** (COST); min **$290.48**; every order an incremental top-up to an existing position.
Against `max_position_notional = 25,000` (measured 08-22, user-6 GLOBAL row, unchanged: `risk_limits_id`
is still NULL). **No order the defective gate passed would have been rejected by a sound gate.** No
retroactive nonconformance. Record and close.

**⭐ Incidental finding worth its own task — see [T1].** Signal `2811`, emitted 14:32:02 on 08-24:

```json
{"reason": "pit_name_not_registered", "n": 6, "sample": ["CB","CSX","TRV","PLD","HLT","ORLY"]}
```

That is the execution drift Dynamic PIT exists to remove, **measured live, weekly, right now** — six
PIT-selected names the runtime could not buy. Account 6 now holds **34** positions, down from 39.

---

### ☐ A2 — Put v0.5 (review revision 2) in custody — **IN FLIGHT**

- [x] cut a branch from `origin/main` — `docs/lowpit-v0.5-custody`, worktree `C:/LLM-RAG-APP/wt-lowpit-v05`, base `148c3dc`
- [x] record the source draft's SHA-256 + byte count — `8ec462d7…`, 38,570 bytes (v0.5 §0.1)
- [x] commit v0.5 rev 2 (dotted governed name) **and this task list** — docs-only, Tier 0
- [ ] open the PR; **honor the walk-away discipline** (≥1 h ready-for-review → merge)
- [ ] merge
- **Owner action:** review / merge. **Blocks:** citing the §7 runbook as governing, therefore A3.

### ☐ A3 — Cut over to v1.0.3 and rerun S8.6 from check 1

**Preconditions — ALL NOW SATISFIED** (A1): 08-24 rebalance completed · 0 open orders · box identity
unambiguous and self-consistent · cooldown expired.

- [ ] capture the pre-cutover evidence bundle (§7.0 re-run at execution time, not reused from A1)
- [ ] capture the 1.0.1 DB version claim + the completed 08-24 rebalance claim
- [ ] stop strategy 8 — **`liquidate = FALSE`**
- [ ] verify IDLE and still no open orders
- [ ] deploy `956e932` via the governed full-cutover path
- [ ] verify health · scheduler armed · Alpaca startup setting · build marker · runtime SHA/version · strategy 8 **still IDLE**
- [ ] update `strategies.version` `1.0.1 → 1.0.3` **while IDLE** — governed exception: record old value, new value, timestamp, **exactly one row affected**
- [ ] verify no 1.0.3 claim exists for the 08-24 slot (no retroactive claim / catch-up)
- [ ] establish the one-epoch reload condition
- [ ] **do NOT start strategy 8** — with the §4 activation gate OPEN the gates do not permit a start; IDLE is the expected outcome (see [B1] for the dated decision)
- [ ] verify **no** scheduled LOW-001 fire exists (since step 10 did not start it)
- [ ] **rerun S8.6 from check 1** — all twelve checks, v0.5 §7.2
- **Owner action:** authorization to mutate. **Blocks:** safe-rollback-baseline status; all of Track C.

⚠ Carry into execution: the seven deployment gotchas (v0.5 §8.1). The two that have already cost a day
each — `.env` rebuilt from scratch defaulting the scheduler and Alpaca startup to **false**, and
`.deploy_src_sha` not being maintained by the provisioner.

#### A3-PRE — build parameters, **pre-verified 2026-08-25 (read-only)**

Three of the §8.1 gotchas were checked against the actual target rather than carried as warnings.
**One of them would have hard-refused the build mid-cutover.**

**1. ⛔ `ADR0043_IMPLEMENTATION_SHA` MUST be overridden.** `build-deploy-archive.sh:53` defaults
`IMPL_SHA=ea6db6e…`. Evaluated against target `956e932`:

```
IMPL_SHA=38f40b4 (owner re-baseline, #535)   ancestry PASS   governed-path delta EMPTY   -> BUILD OK
IMPL_SHA=ea6db6e (script default)            ancestry PASS   governed-path delta NON-EMPTY -> exit 3
                                                  apps/backend/scripts/adr0043_canary_lib.py
                                                  apps/backend/scripts/adr0043_churn_driver.py
```

⇒ export `ADR0043_IMPLEMENTATION_SHA=38f40b46906fc91497049924f7a62e7384d67653`. This matches
`adr0043_implementation_commit` already recorded in the box's `DEPLOYED_BUILD_INFO.json`, so the
cutover preserves the governed provenance rather than changing it.

**2. Runtime flags — reproduce the live values, do not accept the provisioner defaults.** Measured in
the running container; `provision-from-s3.sh:30-34` defaults the first two to `false`:

| Variable | Live value | Provisioner default |
|---|---|---|
| `WORKBENCH_SCHEDULER_ENABLED` | **`true`** | `false` — box returns **disarmed** |
| `WORKBENCH_ALPACA_STARTUP_ENABLED` | **`true`** | `false` |
| `WORKBENCH_LOSS_CONTROL_MODE` | **`OFF`** | `OFF` ✅ |
| `WORKBENCH_LOG_LEVEL` | **unset** — relies on `settings.log_level` default of INFO | — |

⛔ Do **not** pass `LOSS_CONTROL_MODE=ENFORCE` — `provision-from-s3.sh:47` would classify the host as
the ADR-0043 validation box and refuse.

⚠ `WORKBENCH_LOG_LEVEL` being unset is a latent version of v0.5 §8.3: `ownership_unclaimed` is emitted
at info and survives only on the framework default. Setting the deployed level to WARNING at any future
point silently removes one of the five S6 diagnostics. Consider pinning it explicitly at cutover.

**3. `.deploy_src_sha` currently agrees with the build marker** (both `0344337`) — the 08-23 manual
repair held. The provisioner does not maintain it, so it must be updated again by hand to `956e932`
after deploy, or `disc_mdq/ledger.py` will report a stale deployment identity.

### ✅ A4 — Archive the off-series draft — **MOOT / CLOSED 2026-08-25**

Closed without action at custody time. The off-series underscore draft no longer exists in the working
tree (removed during consolidation), and the "only copy of the §21 measurements" justification was
wrong: **v0.3 §§21.1–21.7 in Git carry that narrative in full.** Nothing was lost. Recorded in
v0.5 §0.1. **Owner action:** none.

---

## B. Track B — close the platform risk/accounting activation gate

### B-FINDINGS — what B0 and B2 established (read this before ruling B1)

**1. ✅ B0 data half — the blast radius is EMPTY.**
Scanned all **86** positions across **all accounts** for an implausible reference price
(`|market_price / avg_entry_price| > 3`): **0 rows.** **The HON position no longer exists** — it was
exited, and with it the only known corrupted row. No position data disposition is required.

**2. ✅ B0 code half — the exposure is total.**
Five templates submit `OrderType.MARKET`: `combined_book`, `low_volatility`, `momentum_portfolio`,
`range_trader`, `sector_rotation`. **No template passes `limit_price` at all** — confirmed empirically:
**0** of user 6's orders, ever, carry a `limit_price`. So `req.limit_price` is `None` for every
strategy-originated order on the platform, and the `max_position_notional` gate runs on the
`avg_entry_price`-or-zero fallback **every time, for every armed strategy, on every account.**

**3. 🐛 B2 — the attributed mechanism is DISPROVEN. The repair must be re-scoped.**

v0.3 §21.5 (carried into v0.4 and v0.5) states the recomputer *"overwrote `cost_basis` with the last
fill instead of accumulating it."* **That is not what the code does.** `PositionRecomputer.recompute()`
(`app/orders/positions.py:37-118`) replays **all** fills for the `(account, symbol)` pair in
`filled_at` order and accumulates correctly. Simulated against HON's measured fill history:

```
FULL history (all 4 fills)          qty=11  cost_basis=2468.29  avg_entry=224.390000   <- TRUE values
ONLY the 08-17 fill                 qty= 1  cost_basis= 231.59  avg_entry=231.590000
08-17 + the 2nd BUY                 qty=11  cost_basis=2468.29  avg_entry=224.390000
BUYs only (SELL fill missing)       qty=21  cost_basis=4709.69  avg_entry=224.270952

LIVE ROW OBSERVED                   qty=11  cost_basis= 231.589996  avg_entry=21.053636
```

The correct arithmetic reproduces the **true** values exactly, and **no subset of the fill history
reaches the observed row.** `qty=11` with `cost_basis=231.59` is unreachable from this code path.
Two further tells:

- `231.589996` is a **float** round-trip artifact. The recomputer works in `Decimal` throughout and
  would have produced exactly `231.59`. A float arrives via a JSON payload.
- `app/services/position_sync.py:155-171` writes `qty`, `avg_entry_price` **and** `cost_basis` straight
  from the broker payload (`_to_decimal(raw.get(...))`, `:251-255`) — while `app/orders/positions.py`'s
  own module docstring asserts *"The sync owns `market_value` and `unrealized_pl`; this recomputer owns
  `qty`, `avg_entry_price`, `cost_basis`, and `side`."*

> **The real defect class is two authoritative writers to the same three fields with contradictory
> documented ownership** — not a broken accumulator. The corrupted value most plausibly entered through
> the broker-payload path or a restoration script, not through the recomputer.

⇒ Any B3 repair scoped to "fix the accumulation" would fix **nothing that is broken**. Re-scope to
writer ownership, and note the recomputer would in fact *self-heal* such a row on the next fill for
that symbol — provided the `fills` history is complete.

### ☐ B1 — §21.5 owner ruling ⏰ **DATED**

The question is now narrower and better-posed than v0.5 rev 2 framed it. Rule on **both** failure modes:

- **Mode 1 — corrupted existing row.** Currently **zero live instances** (B0). Residual risk only, and
  the recomputer self-heals on the next fill when fill history is complete.
- **Mode 2 — `pos is None`, by design.** `ref_price = 0` ⇒ the notional check passes trivially for
  **every market-order BUY opening a new name**, platform-wide, all five templates. 100% live. This is
  the mode that matters, and it is a design decision the `:317` comment concedes explicitly.

- [ ] **RULE:** repair · isolate · or accept-with-reason. Review recommendation (v0.5 §4.1) is
      **repair or isolate** — a pre-trade deny control that can be trivially satisfied is not a control.
- [ ] if accepting: record why next-sync gross exposure is sufficient compensation, given that Mode 2
      is not an accident but the documented behaviour
- [ ] **⏰ Due before the Monday 2026-08-31 10:32 America/New_York fire** — either ruled and closed, or
      an explicit *IDLE-through-rebalance* decision recorded
- **Owner action: YES — this is the one blocking decision.**

⭐ **Decision aid from A1:** the 08-24 rebalance's largest order was **$1,089** against a **$25,000**
cap — a 23× margin. LOW-001's equal-weight construction at ~40 names on this account size cannot
approach the cap. The gate is not what protects this strategy; the practical exposure is other books
and future position sizes, not LOW-001's next rebalance.

### ☐ B2 — remaining sub-item

- [x] characterize `app/orders/positions.py` — **done**, see B-FINDINGS 3
- [ ] open or link a **platform-level position-accounting defect record** for the dual-writer ownership
      conflict (correct the mechanism; do not carry the "overwrote instead of accumulated" wording forward)
- [ ] reconcile the `positions.py` docstring with what `position_sync.py` actually writes — whichever
      way the ownership is ruled, the two must stop contradicting each other
- [x] enumerate affected rows — **done**, zero
- **Owner action:** none.

### ☐ B3 — implement and prove the chosen repair/isolation *(depends on B1)*

- [ ] gate uses a trusted bounded execution-price reference for market orders, or fails closed
- [ ] regression: `pos is None` new-position case — old path passes trivially, repaired path cannot
- [ ] regression: HON-shaped corrupted `avg_entry_price` — old path under-rejects, repaired path cannot
- [ ] ⚠ **`app/risk/` requires ≥95% coverage** (`check_risk_coverage.py`) — this is Tier 3, risk/order-path
- [ ] ⚠ **the `risk-engine` skill is binding** for this change; the invariant "risk gates are
      non-bypassable" is in play — tightening a gate that currently fails open is a behaviour change for
      **every armed strategy**, so the static books must be regression-proven, not assumed
- [ ] no position-data disposition needed (B0: zero rows)
- **Owner action:** depends on B1.

---

## C. Track C — Dynamic PIT acquisition programme

⛔ **May not begin before A3 passes.** Final activation additionally requires Track B closure.
**None of this code exists.**

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
- **Owner action: YES — activation.**

---

## T. Standalone tasks surfaced by A1

### ☐ T1 — Capture `pit_name_not_registered` as a recurring measurement

Signal 2811 (08-24) recorded **6** PIT-selected names the runtime could not buy: CB, CSX, TRV, PLD,
HLT, ORLY. This is the first *quantified, live* instance of the drift the whole programme exists to
close, and it recurs every Monday.

- [ ] record the 08-24 instance in the LOW-PIT evidence record (n=6, the six tickers, ISO week 2026-35)
- [ ] capture the same signal each week until C1 lands — it is the natural before/after measurement for
      the Dynamic PIT case, and it is free
- [ ] ⛔ do **not** treat it as authorization to accelerate C1 past A3
- **Owner action:** none. **Value:** turns the programme's premise into evidence at zero cost.

---

## Dependency graph

```
A1 ✅ ──> A2 ──> A3 ──> C1 ──> C2 ──> C3 activation
A4 ✅ moot

B0 ✅ ──> B1 ⏰ ──> B2* ──> B3 ─────────────> C3 activation
          (dated: before 2026-08-31 10:32 ET)
B2 partially ✅

T1 independent, read-only, no dependencies
```

**Critical path right now:** `A2 → A3`. **Only blocking decision:** `B1`, dated.

---

## What is NOT in scope

Unchanged from v0.5 §11 and v0.3 §14. Specifically not authorized by anything in this list: changing
LOW-001 economics; weakening static registration for other strategies; treating post-repair paper P&L
as validation; any DISC-001 / Opportunity / DISC-MDQ coupling; any Account 5 change; any live-money
authorization; starting strategy 8 while the §4 gate is open.

The eleven STOP conditions of v0.3 §22 remain in force.
