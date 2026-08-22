# Trading Workbench — LOW-001 Dynamic PIT Execution
## Design & Implementation Specification v0.3

**Strategy:** LOW-001 (`low-volatility`)
**Current live implementation:** v1.0.0 on Account 6 · **v1.0.1** conformance repair in PR #661
**Planned dynamic-PIT implementation:** v1.0.2 candidate
**Strategy ID:** 8 · **Paper account:** Account 6 / user 6
**Status:** IMPLEMENTATION-READY DEVELOPER CONTRACT — SUPERSEDES v0.2
**Date:** 2026-08-22

> **v0.3 supersedes v0.2 in full.** v0.2 remains readable as the pre-audit design record. Where the
> two disagree, v0.3 governs. Nothing in LOW-001's economics has changed in either direction.

---

## Version 0.3 change summary

v0.3 is not an editorial pass. LOW-PIT-01 discovered facts that change the *architecture*, not merely
the implementation notes. v0.2 assumed registration **blocks orders**. It does not: registration makes
the strategy **unable to see** unregistered positions, prices, and pending quantities. Everything below
follows from that single correction.

| # | Change from v0.2 | Section |
|---:|---|---|
| 1 | New non-negotiable invariant: no deployable revision may be able to acquire dynamically unless dynamically-acquired holdings are discoverable, priceable, reconcilable and liquidatable | §4.6 |
| 2 | **READ authority** and **BUY authority** are separated and defined independently | §4.7 |
| 3 | Held-position discovery promoted to **P0**; LOW-PIT-04 may no longer follow LOW-PIT-03 | §8, §18 |
| 4 | Automated halt/deactivation liquidation promoted to **P0** with its own activation gate | §8, §11 G4b |
| 5 | A **v1.0.1 sell-visibility compatibility release** is inserted as its own merge step before v1.0.2 | §10, §20 |
| 6 | Resolver placement settled: `app/universe/`, injected via `StrategyContext` — *not* `app/strategies/` | §5.3 |
| 7 | Security identity settled: Sharadar `permaticker` + effective interval. No new ID system | §6 |
| 8 | `PITUniverseProvider` returns a typed snapshot, not `list[str]` | §17.1 |
| 9 | `min_executable_fraction = 0.70` adopted as an **activation control** (not research economics) | §7.3 |
| 10 | Test-harness fidelity repair is commit **A1**; G2/G4 require a DB-backed real-context test | §9.1 |
| 11 | Branch point corrected: the **final merged #661 SHA**, not `c15df67` | §20 |
| 12 | **G-A CLOSED — PASS.** Account 6 risk limits are unrestricted (measured) | §11 G-A |
| 13 | **G-B RULED.** Set-level ownership from `orders.source_id`; quantity reconstruction is impossible | §5.4 |
| 14 | Live-state findings that affect G0 (stale params, orphan schema key, version, universe count) | §21 |
| 15 | ★ New invariant: **no retrospective quantity reconstruction** | §4.8 |
| 16 | ★ `ownership_ambiguous` frozen as a five-condition rule; MANUAL SELL explicitly excluded | §5.4.1 |
| 17 | ★ Six recorded triggers reopen the position-attribution persistence design | §5.4.2 |
| 18 | ★ G-A closed as **NO IMPLEMENTATION REQUIRED** — reuse the global symbol/risk machinery, write nothing to it | §11 G-A |
| 19 | ★ PR S scope frozen (allowed / forbidden) and renamed *pre-Dynamic-PIT safety/conformance compatibility* | §10.1 |
| 20 | ★ LOW-001 class-default schedule is a latent 3½-hour deployment defect; repaired in PR S with a timezone-resolving test | §21.3, PIT-T24 |
| 21 | ★ Executable floor frozen: `ceil(selected × 0.70)`, signal `executable_set_below_floor`, ratio logged every rebalance | §7.3 |
| 22 | ★ HON OPS item reclassified off the 7/27 label | §21.5 |

**v0.3 does not authorize live-money trading, does not upgrade LOW-001 above Diversifier (B), and does
not make post-repair P&L an economic-validation dataset.**

---

## 1. Executive decision

LOW-001 remains **KEEP / REPAIR**. Economics are frozen. The remaining work removes execution drift
between the frozen research construction and the live runtime: research reconstructs the point-in-time
top-200 universe every rebalance, but execution is still limited by the statically registered symbol list.

Dynamic PIT execution remains authorized. **The order of construction has changed:** the platform must
be able to *see and exit* a holding outside the static universe **before** any code exists that can
*acquire* one.

### Decision summary

| Decision | Ruling |
|---|---|
| Change LOW-001 economics? | **No** |
| Change lookback / quintile / weighting / weekly cadence? | **No** |
| Keep v1.0.1 separate and independently deployable? | **Yes** |
| Insert a v1.0.1 sell-visibility compatibility release before v1.0.2? | **Yes — required** (new in v0.3) |
| Permit new PIT names to trade without re-registration? | **Yes, through a governed dynamic-enrollment path** |
| Remove static registration globally? | **No** |
| Preserve sell capability for held names outside the universe? | **Mandatory — and it is a POSITIVE requirement, not the absence of a check** |
| Treat missing/untradable names by substitution? | **No — fail explicit** |
| Generalize "all positions on the account belong to this strategy"? | **No** (new in v0.3, §5.4) |
| Upgrade LOW-001 above Diversifier (B) on recent paper P&L? | **No** |

---

## 2. Governing evidence and boundaries

Sealed and immutable, an **input** to this program and not rewritable by it:

- `docs/implementation/TradingWorkbench_LOW001_PaperWindow_2026-08-12_2026-08-21_v1.0.md`
- `docs/implementation/low001_paper_window_20260812_20260821.json`
- SHA-256 `81be681c6c3d1766a0098dbf7b82fdb199aef86c8076ff51dd5ec07ed244566b`
- Classification `OBSERVATION_ONLY`

Also governing:

- **LOW-PIT-01 characterization** — `TradingWorkbench_LOW001_LOW-PIT-01_Registration_Dependency_Map_v1.0.md`.
  ACCEPTED 2026-08-22. Characterization SHA `c15df67`. Preserve as design evidence; attach to PR A.

### v1.0.1 boundary

v1.0.1 independently addresses: SPY cash gate removed · fractional sizing restored · unpriced names
dropped before allocation · session-aware factor-staleness HOLD · durable
`rebalance_started`→`rebalance_completed` · PIT universe scored even for unregistered names (logged
`pit_name_not_registered`, omitted from execution).

Dynamic PIT addresses the last item's remaining execution gap only. HON / cost-basis reconciliation
remains a separate operations task (§21.5). **G0 blocks Account 6 activation** until the v1.0.1
deployment/evidence boundary exists.

---

## 3. Problem statement

### 3.1 Research behavior (frozen)

```text
rebalance_date
    -> universe_asof(rebalance_date, n=200)
    -> valid 252-session realized-vol scores
    -> sort ascending by realized volatility
    -> select lowest quintile (~40 names)
    -> equal-weight executable names
    -> rebalance weekly
```

### 3.2 Current live limitation — restated correctly (CHANGED in v0.3)

v0.2 described the limitation as an intersection filter on buys. That is true but incomplete. The
measured behavior is:

```text
PIT selected names
    -> intersect with statically registered strategy symbols     [buy side]
       AND
    the strategy can see positions/prices/pending qty ONLY for
    statically registered symbols                                [read side]
```

The **read side** is the load-bearing half. The order path performs **no** strategy-universe check at
all: `OrderRouter` and the risk engine contain zero references to `strategies.symbols_json`. A SELL of
an unregistered symbol submitted through `ctx.submit_order` reaches the router and is accepted. What
prevents it is that `_current_holdings()` enumerates only `ctx.symbols`, so the intent is never formed,
and `get_position_for()` returns `None`, so the quantity is unknowable.

**Consequence:** a holding outside the static universe is not *unsellable*. It is *undiscoverable*.
That is worse, because nothing errors.

### 3.3 Required target behavior

```text
PIT universe
    -> factor eligibility
    -> LOW-001 selection
    -> governed dynamic symbol enrollment
    -> broker-asset validation
    -> price validation
    -> target sizing
    -> order plan
    -> execution + reconciliation

and, independently and always:

strategy-owned holdings (registered OR enrolled OR historical)
    -> discoverable
    -> priceable
    -> reducible / exitable
    -> liquidatable by the automated halt/deactivation path
```

---

## 4. Design principles and non-negotiable invariants

### 4.1 Strategy economics are frozen

Unchanged: 252-session realized-vol definition · lowest-quintile rule · equal weight · weekly cadence ·
always-invested V1 intent subject to explicit fail-closed conditions · universe-independent risk controls.

### 4.2 Static and dynamic universe modes must be explicit

```text
universe_mode = STATIC | DYNAMIC_PIT
```

`STATIC` is the default and preserves current behavior exactly. Unknown values **fail closed**. Missing
values resolve to `STATIC`. No migration may auto-convert an existing strategy.

### 4.3 Held positions must always be reducible

A symbol leaving the PIT universe or the selected quintile **must remain sellable** while the strategy
holds it. This invariant outranks buy eligibility.

### 4.4 No silent substitution

Unavailable (inactive / untradable / unpriced / factor-invalid / broker-unresolvable) selected names are
logged with an explicit reason, omitted, and the remaining executable set is re-weighted. **Never**
replaced by the next-ranked name.

### 4.5 Evidence must be reproducible

Every rebalance must permit reconstruction of: PIT as-of and membership (with hash) · factor as-of ·
valid/invalid factor sets · selected quintile · dynamic enrollments · broker and price eligibility
decisions · executable set · targets · orders · fills/rejections · reconciliation · rebalance state.

### 4.6 ★ NEW — the acquisition/disposal symmetry invariant

> **Dynamic acquisition capability SHALL NOT exist in any deployable revision unless strategy-owned
> held securities outside the static universe are discoverable, priceable, reconcilable, and
> liquidatable through both normal strategy exits and automated halt/deactivation paths.**

Enforced as a **merge invariant**, not a review preference:

```text
No code capable of dynamic BUY may merge
unless dynamically introduced holdings are
discoverable and reducible on the same commit.
```

Rationale: the failure this prevents is silent. A dynamic buy that works and a disposal path that does
not produces a correct-looking book that the platform can never unwind — and it produces it on the
happy path, not on an error path.

### 4.7 ★ NEW — READ authority and BUY authority are different sets

```text
READ AUTHORITY                          BUY AUTHORITY
= static registered symbols             = research-selected
∪ dynamically enrolled current symbols  ∩ dynamically authorized
∪ strategy-owned held symbols           ∩ broker-valid
                                        ∩ risk-valid
                                        ∩ price-valid
```

**Visibility into a held security does not confer permission to buy it.** Widening READ authority is
strictly risk-reducing: its only strategy-side consumers are exit discovery, pricing for exit sizing,
and reconciliation. Widening BUY authority is the governed, gated change.

Every widening of READ authority must be accompanied by a test proving BUY authority did not widen with
it (§9 PIT-T16).

### 4.8 ★ NEW — no retrospective quantity reconstruction

> **Strategy-owned quantities SHALL NOT be reconstructed from historical fills.** Order provenance is
> authoritative for *which strategy may claim a security*. The broker position is authoritative for
> *how much of it exists now*. These two authorities may never be substituted for one another.

Measured basis (§5.4): the 2026-07-07 manual unwind consumed strategy-acquired shares with no
consumption rule, so the strategy-attributed fill net disagrees with the live position on 41 of 43
tickers and is negative on one. A reconstruction would be confidently wrong, which is worse than
declining to answer.

---

## 5. Architecture

### 5.1 Separation of concerns

| Component | Responsibility | Must not do |
|---|---|---|
| `PITUniverseProvider` | `universe_asof(date, n=200)` → typed snapshot with evidence metadata | Place orders |
| `LowVolSelector` | 252-session vol eligibility, rank, lowest quintile | Know broker or registration rules |
| `DynamicSymbolResolver` | Convert selected symbols into governed execution eligibility; resolve broker metadata; own identity resolution | Change factor ranking; choose substitutes |
| `HoldingsResolver` **(new in v0.3)** | Answer "which held securities does this strategy own?" across registered, enrolled and historical names | Decide what to buy |
| `TargetBuilder` | Price executable names, build equal-weight targets, apply the executable floor | Invent substitute symbols |
| `ExecutionReconciler` | Submit/recover orders, reconcile target vs broker state | Change research selection |

### 5.2 Dynamic symbol enrollment model

Registration remains the stable strategy identity/configuration. Enrollment is per-rebalance runtime
permission:

```text
strategy registration
    + strategy-owned held symbols          <-- READ only
    + dynamic PIT enrollment (this rebalance)
    = permitted execution context
```

A dynamically enrolled symbol carries at least: `strategy_id`, `strategy_version`, `rebalance_id`,
`rebalance_week`, `symbol`, `permaticker`, `source="pit_universe"`, `pit_as_of`, `factor_as_of`,
`selected_rank`, score, `broker_asset_status`, `fractionable`, `price_status`, `enrollment_status`,
`exclusion_reason`, `created_at`.

**Do not** rewrite `strategies.symbols_json` weekly. It is mutable configuration, and §19.2 forbids
using a mutable registration row as the only evidence that a symbol was eligible for a historical
rebalance. (Note: `range_auto_select.py:369` does mutate `symbols_json` at runtime for a different
program. That is prior art, not precedent — it is exactly the pattern this clause rejects for LOW-PIT.)

### 5.3 ★ Resolver placement — SETTLED

`check_strategy_isolation.sh` forbids `apps/backend/app/strategies/**` from importing `app.brokers`. The
resolver must call `AlpacaAdapter.get_asset` / `is_fractionable`. Therefore:

```text
app/universe/dynamic_symbol_resolver.py     <-- lives here, NOT app/strategies/
app/universe/pit_universe_provider.py
app/universe/holdings_resolver.py
app/universe/types.py                       <-- immutable records (§17.1)

Engine
   -> constructs and injects
StrategyContext.dynamic_symbol_resolver     <-- same seam as submit_order_fn
   -> LOW-001 requests resolution
```

`app/universe/` rather than `app/orders/` because the responsibility is broader than order placement:
broker metadata resolution, enrollment, identity resolution, execution eligibility. The strategy never
imports a broker SDK. The engine wires the resolver exactly as it wires `submit_order_fn` today
(`engine.py:396-467`).

### 5.4 ★ NEW — position ownership (G-B ruling)

**Ruling.** Dynamic PIT must **not** generalize "all positions in the account belong to this strategy."
Position ownership must be strategy-attributed. Account-6 exclusivity may be used only as a temporary
migration/recovery fact, never as the platform contract.

**What the ledger can and cannot do — measured on the live Account 6 book, 2026-08-22:**

| Question | Answerable from `orders`/`fills` today? | Evidence |
|---|---|---|
| *Which tickers does strategy 8 own?* (set) | **YES — exactly** | 39 held tickers; all 39 have a `STRATEGY:8` BUY; `held_without_S8_BUY = []`. No other strategy has ever ordered on account 6; strategy 8 has never ordered on another account. |
| *How many shares of ticker X does strategy 8 own?* (quantity) | **NO** | Strategy-attributed fill net disagrees with `positions.qty` on **41 of 43** tickers, typically ~2×, because 42 MANUAL SELLs (all FILLED, 2026-07-07 17:43–19:07 UTC) consumed strategy-bought shares with no consumption rule. AXP nets **−1**: the strategy sold shares it never bought under its own `source_id`. A ledger sum is not merely imprecise — it can go negative. |

**The two authorities are distinct and must stay distinct** (owner ruling 2026-08-22):

| Question | Authority |
|---|---|
| *Which strategy may claim this security?* | **order provenance** (`orders.source_type` / `source_id`) — and **only** this |
| *How much of it exists right now?* | **the broker position** (`positions.qty`) — and **only** this |

Neither may substitute for the other. See the §4.8 invariant.

```text
owned_symbols(strategy_id, account_id)
    = { security : has qualifying STRATEGY:<strategy_id> acquisition provenance
                   on this account }

held_positions_for_strategy(account_id, strategy_id)
    = current broker/account positions ∩ owned_symbols(strategy_id, account_id)
      with qty taken from the position, never from the ledger
```

This requires **no schema change**, is exact for Account 6 today, and is precisely the shape
`_current_holdings()` already has — except that it derives the set from `ctx.symbols` instead of from
provenance.

**Authorized scope:** Account 6 only, under the fail-closed attribution contract below.

#### 5.4.1 `ownership_ambiguous` — frozen rule

A currently held security is **ambiguous** if **any** of the following is true:

1. Another strategy has acquisition provenance for the same account/security.
2. A **MANUAL BUY** or other non-strategy acquisition could contribute to the currently held quantity.
3. Ownership cannot be followed across ticker/security lineage.
4. More than one strategy may own the same security on that account.
5. Account 6 ceases to be a dedicated LOW-001 account without a durable attribution mechanism.

**A MANUAL SELL by itself does not make ownership ambiguous.** On today's dedicated Account 6 it does
not disturb the *set*; it only demonstrates why the *quantity* cannot come from the strategy ledger.
Condition 2 is about acquisitions, not disposals.

When ambiguous, the `HoldingsResolver` **fails closed for every attribution-dependent automated
operation**: emit `ownership_ambiguous`, exclude the security from automated exit and from automated
liquidation, surface it to the operator. Never guess, never default to "probably ours", never default
to "not ours" silently.

#### 5.4.2 Triggers that reopen the persistence design

`positions` gets **no** `strategy_id` column now. Build a durable position-attribution table/model when
**any one** of these becomes true — and record the trigger in the reopening ADR:

1. Two automated strategies share one account.
2. Two strategies may trade the same permanent security.
3. MANUAL BUYs are permitted alongside strategy ownership.
4. Position transfers or external acquisitions must coexist with strategies.
5. The platform needs exact per-strategy **quantity** attribution rather than set membership.
6. Netting across multiple strategy sources becomes supported.

This clause exists so that today's Account-6 shortcut cannot silently become tomorrow's platform
architecture.

### 5.5 Buy eligibility

```text
selected_by_LOW001
AND dynamic_PIT_authorized_for_strategy
AND broker_asset_resolved AND asset_active AND asset_tradable
AND required_price_available
AND factor_freshness_gate_passed
AND executable_floor_satisfied
AND strategy/risk gates_passed
```

Fractionability is **not** a buy/no-buy gate. Non-fractionable assets fall through to the existing
OrderRouter whole-share flooring (`router.py:149-174`).

### 5.6 Sell eligibility

```text
strategy_owns_the_holding (§5.4)
AND risk-reducing_or_rebalance_exit
```

The symbol need not be in the PIT universe, the selected quintile, the enrollment set, or
`symbols_json`. No universe-membership check may appear on this path.

---

## 6. Security identity — SETTLED

```text
SECURITY_IDENTITY_CONTRACT = "PERMATICKER_EFFECTIVE_INTERVAL_V1"
security identity = Sharadar permaticker + effective-date interval
```

Owner-ruled 2026-07-29; implemented in `app/validation/security_lineage.py` (pure stdlib — importable
from the order plane with no isolation-invariant risk). `permaticker` is already materialized in the
factor store's `tickers` table and `store.dollar_volume_universe()` already joins it.

**No new security identity system.** Two planes, reconciled identity-first:

| Plane | Key | Authority |
|---|---|---|
| Research / universe / lineage | `permaticker` + effective interval | what security this *is* |
| Execution / broker | `symbols.id` + `ticker` | what can be sent to Alpaca |

A ticker change within one `permaticker` is an attribute change. A ticker that changes `permaticker`
inside the required lookback is a **refusal**, removed before ranking (existing lineage rule).

---

## 7. Universe provider contract and the executable floor

### 7.1 The frozen definition of "top 200"

Verbatim, from `store.dollar_volume_universe()`:

> Rank by `SUM(close × volume)` over the trailing `lookback_days` calendar-day window; restrict to
> tickers whose `firstpricedate ≤ as_of ≤ lastpricedate`; require `dollar_volume > 0`; order
> `dollar_volume DESC, ticker ASC`; `LIMIT n`.

Deterministic, survivorship-free, no look-ahead. **This text is the contract.** Changing it is a
research decision, not an implementation decision.

### 7.2 What must be added (custody, not computation)

| Requirement | Present today |
|---|---|
| PIT-200 membership persisted per rebalance | ❌ |
| Membership hash | ❌ |
| `pit_as_of` recorded | ❌ |
| `permaticker` projected alongside ticker | ❌ |
| Store/source version binding | ❌ |
| Short-universe HOLD | ❌ |

**Short-universe HOLD:** if the provider returns materially fewer than `n` members, the rebalance HOLDs
with `pit_universe_short` and makes no changes. An impeccable execution system faithfully trading a
wrong universe is still wrong.

### 7.3 ★ Executable-set floor — FROZEN (activation ruling 2026-08-22)

```text
min_executable_fraction = 0.70          # activation control, NOT research economics
required_executable     = ceil(selected_count * 0.70)
```

| Selected | Minimum executable |
|---:|---:|
| 40 | 28 |
| 39 | 28 |
| 38 | 27 |
| 35 | 25 |

Below the floor: emit **`executable_set_below_floor`**, **HOLD**, build no new rebalance target.
Existing holdings must remain risk-manageable during the HOLD — a floor HOLD suppresses *new target
construction*, never a risk-reducing exit (§4.3, §5.6).

**Log the raw executable ratio on every rebalance, pass or fail.** A book that repeatedly runs at 29/40
technically passes while telling you something important about research-vs-live executability; that
signal is lost if the ratio is only recorded on failure.

Changeable only by an explicit, recorded owner/config ruling.

Why it is required — measured against the current sizing rule
`per_name = min(equity/k, equity × max_position_pct)` with `max_position_pct = 0.10`:

| Executable `k` | per-name | gross deployed | behavior |
|---:|---:|---:|---|
| 40 | 2.5% | 100% | intended |
| 25 | 4.0% | 100% | **1.6× concentration, fully invested, no signal emitted** |
| 10 | 10.0% | 100% | at the cap |
| 5 | 10.0% | **50%** | concentrated **and** under-deployed |

`max_position_pct` does not bind until `k < 10`, and when it binds it silently under-deploys instead of
holding. Two distinct failures, neither of which HOLDs today. Labelling the floor an *activation
control* keeps it out of the frozen economics: it decides whether to trade, never what to select.

---

## 8. Detailed rebalance flow

**Step 0 — Resolve strategy-owned holdings (NEW, and it comes first).**
`HoldingsResolver` returns owned symbols per §5.4, independent of PIT, enrollment and registration.
Ambiguous symbols are excluded and reported. This runs before anything universe-related so that an exit
is never contingent on a successful universe build.

**Step 1 — Establish rebalance identity.** Durable weekly state with a stable `rebalance_id`:

```text
not_started -> rebalance_started -> plan_built
            -> orders_dispatched / recovering -> reconciled -> rebalance_completed
```

`rebalance_started` / `rebalance_completed` semantics from v1.0.1 remain intact.

**Step 2 — Resolve the expected PIT session.** Reuse `MarketSession.previous_trading_day` and the
v1.0.1 `expected_last_session` / `session_lag` helpers. **Do not add a second freshness implementation.**
Persist rebalance timestamp, expected latest completed session, actual factor `as_of`, pass/HOLD.
Failure → `factor_stale_hold`, no selection or order changes.

**Step 3 — Build PIT-200.** Same governed `universe_asof(..., n=200)`. Persist full membership, `pit_as_of`,
permatickers, and the membership hash. Short universe → `pit_universe_short` HOLD.

**Step 4 — Compute factor-eligible universe.** Separate valid / missing / stale / invalid-non-finite.
No invalid name enters the ranked set.

**Step 5 — Select the LOW-001 quintile.** Frozen rule. Persist symbols, scores, ranks, count.

**Step 6 — Resolve dynamic execution eligibility.** For each selected symbol not already known to the
strategy: resolve broker asset metadata (batched where supported), confirm active and tradable, enroll,
emit durable evidence. Failures emit `pit_asset_not_found` / `pit_asset_inactive` /
`pit_asset_not_tradable` / `pit_asset_resolution_error`. One symbol's resolver failure must not drop
another's evidence. `pit_name_not_registered` survives only as a pre-resolver observation, never a
terminal outcome. **Do not delete the signal name** — the sealed window's evidence parses it.

**Step 7 — Price and build the executable equal-weight book.** Drop unpriced names
(`pit_price_unavailable` / `pit_price_invalid`) **before** sizing. Apply the §7.3 floor. Then:

```text
allocatable_equity = equity * (1 - cash_buffer_pct)
weight_per_name    = 1 / executable_name_count
notional_per_name  = allocatable_equity / executable_name_count
```

Existing router sizing handles fractional vs whole-share.

**Step 8 — Build a deterministic target plan.** Exits · reductions · within-tolerance · increases · new
entrants. Identical inputs must produce an identical plan.

**Step 9 — Execute with recovery semantics.** Sells precede buys. A retry inspects broker/current state
and continues an incomplete rebalance rather than replaying every original order. Restart after
`rebalance_started` and before `rebalance_completed` enters recovery mode.

**Step 10 — Reconcile and complete.** Before `rebalance_completed`, compare `research_selected_set`,
`executable_selected_set`, `final_target_set`, `broker_position_set`, and `owned_symbols`. Every
difference must carry a recorded reason. **Zero unexplained symbol discrepancies.**

---

## 9. Test matrix

| Test ID | Scenario | Required result |
|---|---|---|
| PIT-T01 | Selected symbol is statically registered | Unchanged behavior |
| PIT-T02 | Selected symbol unregistered but active/tradable | Enrolled; buy target allowed |
| PIT-T03 | Selected symbol unregistered and non-fractionable | Target allowed; router floors qty |
| PIT-T04 | Selected symbol unresolvable at broker | Excluded with reason; no substitution |
| PIT-T05 | Selected symbol inactive/untradable | Excluded with reason; no substitution |
| PIT-T06 | Selected symbol has no valid price | Dropped before weighting; remainder re-weighted |
| PIT-T07 | Held symbol leaves the selected quintile | Sell/reduce allowed |
| PIT-T08 | Held symbol leaves PIT-200 entirely | Sell/reduce allowed |
| PIT-T09 | Factor store stale | `factor_stale_hold`; no orders |
| PIT-T10 | Restart after rebalance start | Resume/reconcile the same rebalance |
| PIT-T11 | Restart after sells, before buys | Recover without duplicate sells |
| PIT-T12 | Two dispatch callbacks, same week | Storm guard prevents a duplicate logical rebalance |
| PIT-T13 | Static strategy sees an unregistered symbol | Existing static behavior unchanged |
| PIT-T14 | Same inputs run twice, dry-run | Identical selected set and plan |
| PIT-T15 | Final broker set differs from target | Completion blocked or discrepancy explicitly failed |
| **PIT-T16** ★ | READ authority widened for a held symbol | That symbol is **visible and sellable but NOT buy-eligible** unless independently selected |
| **PIT-T17** ★ | Name enrolled week N, absent from PIT-200 week N+1 | Discovered and exited in week N+1 — *the within-version stranding case* |
| **PIT-T18** ★ | Halt / deactivation with a dynamically acquired holding | Liquidated through the **real** `activation.py` path, not `submit_order()` |
| **PIT-T19** ★ | Executable count below the floor | `executable_set_below_floor` HOLD; no orders; no concentration |
| **PIT-T20** ★ | Provider returns a short universe | `pit_universe_short` HOLD |
| **PIT-T21** ★ | Two strategies have traded the same `(account, symbol)` | `ownership_ambiguous`; symbol excluded from automated exit; operator notified |
| **PIT-T22** ★ | Rollback: v1.0.2 buys X, revert to v1.0.1+PR S | v1.0.1 discovers and can exit X |
| **PIT-T23** ★ | Held security acquired by a **MANUAL BUY** on the account | `ownership_ambiguous`; excluded from automated exit and liquidation (§5.4.1 cond. 2) |
| **PIT-T24** ★ | LOW-001 class-default schedule resolved through the engine's timezone | Next fire time is **10:32 America/New_York**; assert the resolved instant, not the cron literal |

### 9.0 ★ The five visibility assertions PR S must prove

```text
registered symbol                                   -> readable
unregistered, not held, not enrolled                -> NOT readable
unregistered but strategy-owned and held            -> readable for position/exit purposes
dynamically enrolled selected symbol                -> readable where BUY planning requires it
mere READ visibility                                -> NOT buy authority          (PIT-T16)
```

The last line is the one that keeps the widening honest; it is the invariant, not a nicety.

### 9.1 ★ Test-harness fidelity is a prerequisite, not a nicety

`_ctx()` in `tests/strategies/test_low_volatility_template.py:68-113` is a `MagicMock` that **ignores
`ctx.symbols` entirely** — `get_position_for` returns a position for any ticker in `holdings`, and
`get_recent_bars` returns a price for any symbol. Production `StrategyContext` returns `None` and an
empty frame. The fake is therefore **more permissive than production**, and an exit-invariant test
written against it will pass on code that strands positions live. The existing
`test_sells_names_leaving_the_book` does not catch this because its held name is registered.

**Required, in this order:**

```
Commit A1:  test(low001): make template context enforce production symbol visibility
Commit A2+: everything else
```

**G2 and G4 additionally require at least one DB-backed test against the real `StrategyContext`**
(the `session_factory` fixture used by `tests/strategies/test_context.py`), not only the template mock.
A mock cannot discharge a visibility invariant whose whole content is what the real object hides.

---

## 10. Pull request structure

| PR | Contents | Gate |
|---|---|---|
| **#661** | v1.0.1 conformance repair | must be green and merged first |
| **PR A** — scaffolding | A1 test-fidelity fix · LOW-PIT-01 doc · `universe_mode` capability (default STATIC) · typed `PITUniverseSnapshot` · resolver/holdings interfaces and evidence types · static-strategy regressions | No behavior change for any existing strategy |
| **PR S** — **LOW-001 pre-Dynamic-PIT safety/conformance compatibility** ★ | see §10.1 | **This is the safe rollback and re-registration baseline.** Merged *and deployed* before PR B |
| **PR B** — dynamic eligibility | Broker asset resolution · dynamic enrollment · identity-first reconciliation · exit invariants proven against the resolver · static regressions | May not merge before PR S |
| **PR C** — target & reconciliation | Executable set · floor · target planning · evidence/reconciliation · restart/failure tests | |
| **PR D** — v1.0.2 activation record | Version bump / config authorization for LOW-001 only · runbook · no economic parameters | After G0–G7 |

Every PR states: no LOW-001 economics changed · no Account 5 change · no live-money authorization ·
whether persistence schema changed · static-strategy regression status · exact test commands and
results · new event/signal names · remaining open drift · **and that LOW-001 remains Diversifier (B)**.

**PR S exists because "pre-staged" is not good enough.** A rollback that requires a code change before it
is safe is not a rollback. The compatibility repair must already be merged, deployed and exercised
*before* v1.0.2 can create a position v1.0.1 did not know statically.

### 10.1 ★ PR S scope — frozen

**Allowed**

- production-realistic context test fix (commit A1, §9.1);
- strategy-owned held-symbol discovery (`HoldingsResolver`, §5.4);
- `get_position_for()` visibility for authorized held positions;
- `get_positions()` visibility for authorized held positions;
- LOW-001 `_current_holdings()` union (`ctx.symbols ∪ owned`);
- automated deactivation / halt liquidation widening (`activation.py`);
- permanent-security identity handling (`permaticker`, §6);
- `ownership_ambiguous` fail-closed behavior (§5.4.1);
- **LOW-001 default-schedule conformance repair** (§21.3);
- tests, including PIT-T16 / T18 / T21 / T22 and the timezone-resolving schedule test.

**Forbidden**

- dynamic BUY of any kind;
- the broker resolver or any enrollment path;
- PIT execution of new names;
- economic changes;
- Account 5 changes;
- target-selection changes.

The resulting safety boundary:

```text
v1.0.1
   ↓
PR S            <-- merged AND deployed
   ↓
runtime can safely discover and exit future dynamic holdings
   ↓
PR B
   ↓
dynamic BUY becomes permissible
```

The schedule repair belongs here rather than in a micro-PR because PR S's purpose is to make v1.0.1 a
**trustworthy rollback and re-registration baseline**, and a default that re-registers the book 3½ hours
late is exactly a re-registration hazard.

---

## 11. Deployment gates

### G-A — Account 6 risk-limit envelope · **CLOSED / PASS** (measured 2026-08-22, ec2-paper, read-only)

`risk_limits` row id=8, user 6, scope GLOBAL, broker_mode paper:

```
allowed_symbols = null      denied_symbols = null      allow_short = 0
max_position_notional = 25,000   max_gross_exposure = 110,000   max_daily_loss = 5,000
max_orders_per_minute = 200      max_orders_per_day = null
```

`strategies.risk_limits_id` for strategy 8 is NULL, so the user-6 GLOBAL row is the resolved envelope.
**No symbol allowlist or denylist exists for any user in the table.** Dynamic PIT is not blocked by the
risk allow/deny gate, and there is no latent exit hazard from it. `symbols` holds 14,894 rows / 14,203
active, so the risk engine's `SYMBOL_DENIED` resolution is broadly satisfied for Alpaca-active US
equities without any new writes.

**Status: CLOSED / PASS / NO IMPLEMENTATION REQUIRED.**

The result is better than "no blocker": the existing global symbol and risk machinery already covers the
whole tradable universe. Dynamic PIT therefore **reuses it as-is** and must **not**:

- populate strategy-specific allowlists;
- bypass or special-case `SYMBOL_DENIED`;
- maintain a second broker-symbol registry;
- add `symbols`-table writes as part of enrollment.

That is a real simplification of the resolver: it *reads* broker asset metadata to decide eligibility;
it *writes* nothing to the symbol or risk layer.

⚠ Re-verify after any change to user-6 risk limits. A future non-empty `allowed_symbols` would silently
defeat both dynamic buys and dynamic exits — and it must be solved by governance, **never** by teaching
Dynamic PIT to bypass a risk control.

### G-B — Position ownership · **RULED** (§5.4)

Set-level attribution from `orders.source_id`; broker `positions.qty` for quantity; explicit
fail-closed guard on multi-strategy ambiguity; durable attribution table deferred with recorded
trigger conditions.

### G0 — v1.0.1 boundary established

Capture Account 6 pre-deploy (strategy/version, `params_json`, positions, cash/equity, current
rebalance week/state) · deploy v1.0.1 · prove the running process reports 1.0.1 · clean the stale live
params (§21.1) · restart/reload · prove restart does not create a second rebalance when
`rebalance_completed` exists for the week · verify factor freshness by the NYSE-session rule · record a
durable deployment timestamp/version/config boundary · classify results from that timestamp as
post-1.0.1 observation, outside the sealed 08-12→08-21 record.

### G1 — Static-strategy regression
All static-universe strategies preserve current registration enforcement. Account 5 code path unchanged.

### G2 — Research-selection conformance
Historical dry-runs prove the selected quintile is unchanged by the execution work. Includes at least one
DB-backed real-context test.

### G3 — Dynamic enrollment correctness
A fixture containing an unregistered but PIT-selected valid name proves it becomes executable.

### G4 — Exit safety (normal path)
Held names remain discoverable and sellable after leaving the selected set and the PIT universe
(PIT-T07/T08/T17/T22), proven against the **tightened** fake and at least one real-context test.

### G4b ★ — Exit safety (automated safety path)
A dynamically enrolled security bought in a test must liquidate successfully through the **actual
automated activation/halt/deactivation path**, not merely through `submit_order()` (PIT-T18).

### G5 — Failure/restart safety
Restart, broker lookup failure, missing price, rejection, partial fill.

### G6 — Reconciliation
Zero unexplained symbol differences between target and broker state.

### G7 — Paper-only first activation
v1.0.2 activated on Account 6 PAPER only. No production/live-money authorization implied.

---

## 12. Rollback plan

Rollback restores **execution eligibility behavior**; it never rewrites observed evidence.

1. Stop new LOW-001 rebalance dispatch if needed.
2. Preserve broker positions and all v1.0.2 evidence.
3. Roll the strategy runtime back to the last known-good **v1.0.1 + PR S** artifact/config — *not* bare
   v1.0.1, which cannot see a dynamically acquired holding.
4. Confirm risk-reducing sells remain available for every position v1.0.2 introduced (PIT-T22).
5. Do not liquidate dynamically introduced positions merely to recreate the old static universe;
   reconcile them explicitly.
6. Record the rollback reason and the affected `rebalance_id` / week.
7. Resume only after the defect is reproduced and corrected.

A rollback must never make a dynamically introduced held symbol undiscoverable or unsellable.

---

## 13. Operational observability

Counters/fields must answer: PIT names considered · valid factors · selected · selected-but-unregistered
· dynamically enrolled · broker-validation failures and why · price-validation failures · executable
targets · **owned holdings discovered outside the static universe** · **ownership-ambiguous symbols** ·
exits/additions · completed vs recovered · unexplained target-vs-broker discrepancies.

```text
pit_universe_resolved        pit_dynamic_enrolled        pit_asset_not_found
pit_asset_inactive           pit_asset_not_tradable      pit_asset_resolution_error
pit_price_unavailable        pit_price_invalid           pit_execution_set_built
pit_reconciliation_complete  pit_reconciliation_mismatch pit_universe_short
executable_set_below_floor     holdings_outside_universe   ownership_ambiguous
```

Associate events with the stable `rebalance_id`; avoid per-dispatch-loop duplication.

---

## 14. Explicit non-goals

No news/catalyst inputs · no SIP-driven intraday selection · no mid-week rotation · no change to the
252-day realized-vol calculation · no change to the lowest-quintile rule · no volatility targeting · no
sector tilts/caps beyond frozen V1 · no new SPY regime filter · no optimization on August paper P&L ·
no HON cost-basis repair · no Account 5 change · no research-verdict upgrade.

Any such proposal is a separate decision and must not ride inside this workstream.

---

## 15. Definition of Done

- [ ] LOW-001 explicitly declares the approved dynamic-PIT universe capability; all other strategies remain STATIC.
- [ ] PIT-200 reconstructed from the governed point-in-time universe each rebalance, persisted with `pit_as_of`, permatickers and a membership hash.
- [ ] 252-session realized-vol selection unchanged from frozen V1.
- [ ] A selected, broker-valid symbol can be bought without permanent re-registration.
- [ ] **A strategy-owned holding outside the static universe is discoverable, priceable, reducible and liquidatable — through the normal exit path and the automated halt path.**
- [ ] READ-authority widening demonstrably did not widen BUY authority.
- [ ] No missing/inactive/untradable/unpriced name silently substituted.
- [ ] Dead legs excluded before equal-weight sizing; executable floor enforced.
- [ ] Factor freshness and durable week/restart controls enforced.
- [ ] Every selected-to-executable difference recorded with a reason.
- [ ] Final broker positions reconcile to the executable target with zero unexplained discrepancies.
- [ ] Historical/dry-run, restart/failure and static-regression tests pass.
- [ ] Ownership ambiguity fails closed and is observable.
- [ ] v1.0.2 deployment isolated to Account 6 PAPER; post-deploy observation separated from the sealed benchmark.
- [ ] LOW-001 remains **B (Diversifier)**.

---

## 16. Developer execution order

| Step | Action | Status |
|---|---|---|
| — | Fix #661 (`_last_dispatch_seq`) | ✅ pushed `ef5e327` |
| — | Read G-A on ec2-paper | ✅ **PASS / CLOSED / no implementation required** (§11 G-A) |
| — | G-B ownership ruling | ✅ **RULED** (§5.4) |
| **A** | Finish #661: FULL green · Python Gate green · merge · **record the final merge SHA** | in flight |
| **B** | Cut a clean worktree from the merged SHA — never the contaminated primary worktree | |
| **C** | Commit v0.3 (governing spec) + LOW-PIT-01 (completed design evidence) | |
| **D** | Implement **PR S** (§10.1): production-faithful fake context · ownership resolver / set provenance · broker quantity authoritative · `ownership_ambiguous` · held-symbol read union · normal LOW-001 exits · halt/deactivation liquidation · ticker/permaticker identity path · LOW-001 default-schedule correction · regression tests | |
| **E** | Deploy PR S — establish the safe rollback baseline (G4, G4b) | |
| **F** | Only then: PR A/B Dynamic PIT capability + enrollment | |
| **G** | PR C: executable floor, evidence/hash, identity-first reconciliation; historical/failure/restart tests | |
| **H** | Account-6 v1.0.1 deployment and the G0 boundary | |
| **I** | Only after G0–G7: activate v1.0.2 PAPER on Account 6 (PR D) | |

---

## 17. Implementation contracts

### 17.1 Core data contracts (immutable records)

```text
PITUniverseSnapshot                      # replaces list[str]
  rebalance_id
  pit_as_of
  members[] = {ticker, permaticker, effective_interval, rank, dollar_volume}
  member_count
  membership_hash                        # over the ordered (permaticker, ticker) sequence
  source_version / store_fingerprint
  identity_contract = "PERMATICKER_EFFECTIVE_INTERVAL_V1"

LowVolSelection
  rebalance_id · factor_as_of
  ranked[] = {ticker, permaticker, realized_vol, rank}
  selected[]

OwnedHolding                             # NEW
  ticker · permaticker · symbol_id
  qty                                     # from positions (broker truth)
  ownership_basis = "static_registration" | "order_provenance"
  ambiguous: bool · ambiguity_reason

ExecutionEligibility
  ticker · permaticker · selected
  was_registered · was_owned
  broker_resolved · active · tradable · fractionable
  price_status · enrollment_status · exclusion_reason

TargetPlan
  rebalance_id
  executable_symbols[] · target_weight_by_symbol · target_qty_by_symbol
  planned_actions[]
  floor_satisfied: bool · executable_fraction
```

Immutable once the rebalance reaches `rebalance_completed`. Corrections are additive evidence, never
destructive rewrites.

### 17.2 Function boundaries

```python
owned = holdings_resolver.owned_holdings(
    strategy_id=8, account_id=6,
)                                          # runs FIRST, independent of the universe

pit = pit_universe_provider.universe_asof(as_of=expected_pit_session, n=200)

selection = low_vol_selector.select(pit_universe=pit, factor_as_of=expected_factor_session)

eligibility = dynamic_symbol_resolver.resolve(
    strategy_id=8, rebalance_id=rebalance_id,
    selected=selection.selected, owned=owned, universe_mode="DYNAMIC_PIT",
)

target = target_builder.build_equal_weight(
    selection=selection, eligibility=eligibility, owned=owned,
    equity=current_equity, cash_buffer=configured_cash_buffer,
    min_executable_fraction=0.70,
)

result = execution_reconciler.execute_or_recover(
    rebalance_id=rebalance_id, target=target, broker_state=current_broker_state,
)
```

### 17.3 Forbidden dependency directions

```text
LowVolSelector          -> registered symbol list        ⛔
LowVolSelector          -> broker asset status           ⛔
PITUniverseProvider     -> current broker holdings       ⛔
DynamicSymbolResolver   -> change factor rank            ⛔
DynamicSymbolResolver   -> choose a next-ranked substitute ⛔
HoldingsResolver        -> PIT membership / selection    ⛔  (an exit must not depend on a universe build)
OrderRouter             -> infer research selection      ⛔
app/strategies/**       -> app.brokers                   ⛔  (CI-enforced)
```

### 17.4 Idempotency

For the same `rebalance_id` and unchanged governed inputs: PIT reconstruction deterministic · research
selection deterministic · enrollment upserts create no duplicate durable rows · a retry may reconcile
changed broker state but must not create a second logical weekly rebalance · `rebalance_completed`
emitted at most once.

---

## 18. Ticket backlog

| Ticket | Priority | Depends on | Deliverable | Done when |
|---|---:|---|---|---|
| `LOW-PIT-00` | P0 | — | Freeze v0.3; branch from the **merged #661 SHA** | Branch records the exact base SHA |
| `LOW-PIT-01A/B` | P0 | 00 | Registration dependency map + sell-path audit | ✅ **CLOSED / ACCEPTED 2026-08-22** |
| `LOW-PIT-01C` ★ | P0 | 01B | Test-context fidelity repair (commit A1) | Template fake mirrors production visibility |
| `LOW-PIT-02A` | P0 | 01A | `STATIC` / `DYNAMIC_PIT` capability | Default STATIC; unknown values fail closed |
| `LOW-PIT-02B` | P0 | 02A | Static-strategy regression tests | Account 5 and momentum books unchanged |
| `LOW-PIT-04A` ★ | **P0 — moved ahead of 03** | 01B, 01C | `HoldingsResolver` + READ-authority widening | Held symbol outside the universe is discoverable and reducible |
| `LOW-PIT-04B` ★ | **P0** | 04A | Automated halt/deactivation liquidation widening | PIT-T18 passes through the real activation path |
| `LOW-PIT-04C` ★ | **P0** | 04A | Ownership-ambiguity fail-closed guard | PIT-T21 passes |
| `LOW-PIT-04D` ★ | **P0** | 04A-C | **PR S** — v1.0.1 sell-visibility compatibility release | Merged and deployed; PIT-T22 passes |
| `LOW-PIT-03A` | P0 | 02A, 04D | Dynamic resolver with broker metadata lookup | Valid unregistered selected symbol resolves eligible |
| `LOW-PIT-03B` | P0 | 03A | Durable enrollment/exclusion evidence | Every selected symbol has an explicit outcome |
| `LOW-PIT-05A` | P1 | 03A | Price eligibility stage | Unpriced names excluded before sizing |
| `LOW-PIT-05B` | P1 | 05A | Equal-weight builder + executable floor | Weights over executable names only; floor HOLDs |
| `LOW-PIT-06A` | P1 | 03B, 05B | Stable rebalance evidence model + membership hash | PIT → selection → eligibility → target reconstructable |
| `LOW-PIT-06B` | P1 | 06A | End-state reconciliation | Zero unexplained differences before completion |
| `LOW-PIT-07A/B` | P1 | 05B, 06A | Historical dry-run fixtures + determinism assertions | Research sets unchanged; only eligibility differs |
| `LOW-PIT-08A` | P1 | 06B | Restart/partial-fill fault tests | Recovery duplicates nothing, strands nothing |
| `LOW-PIT-09A/B` | P1 | G0–G7 | v1.0.2 activation + first governed paper rebalance closeout | Account 6 PAPER only; full reconciliation |

**Ticket rules.** A P0 ticket blocks later implementation even if other tests are green. `LOW-PIT-03A`
may not merge before `LOW-PIT-04D`. A ticket may be split but its acceptance condition may not be
weakened. Any discovery that dynamic enrollment requires changing factor/ranking economics is a **STOP**.

---

## 19. Persistence, migration, compatibility

**19.1 Reuse before creating.** Prefer existing signal/evidence and order-reconciliation tables. Create
a migration only when the current model cannot durably answer the reconstruction questions.

**19.2 If a new persistence object is required**, key it `(strategy_id, rebalance_id, symbol)` and make
enrollment upserts idempotent. Do **not** use mutable symbol-registration rows as the only evidence that
a symbol was dynamically eligible for a historical rebalance.

**19.3 Backward compatibility.** Missing `universe_mode` → `STATIC`. No migration auto-converts. Dynamic
enrollment records must not alter ownership/attribution of other strategies' or accounts' positions.
Existing router non-fractionable handling remains authoritative.

**19.4 Evidence immutability.** After `rebalance_completed`, do not rewrite historical selected/executable
sets because a later broker sync or P&L observation changed. Corrections are separate, timestamped
evidence.

**19.5 ★ Attribution-table trigger conditions** (§5.4). Record them; do not build speculatively.

---

## 20. Branch / PR / merge sequence

```text
main
  |
  +-- #661  LOW-001 v1.0.1 conformance repair
  |      c15df67  (LOW-PIT-01 characterization SHA — evidence only)
  |      + dispatch-guard naming fix
  |      -> FULL + Gate GREEN -> merge  ==>  FINAL MERGED SHA  <== branch point
  |
  +-- lowpit/scaffold        (from FINAL MERGED SHA)
       -> PR A: A1 test fidelity, capability, typed snapshot, interfaces, static regressions
       -> PR S: v1.0.1 sell-visibility compatibility  [MERGE + DEPLOY before PR B]
       -> PR B: resolver, dynamic enrollment, identity-first reconciliation
       -> PR C: executable set, floor, evidence, reconciliation, fault tests
       -> PR D: LOW-001 v1.0.2 activation record
```

⛔ **Do not branch implementation from `c15df67`.** It is one commit behind the fix and would carry a
known-old base forward. `c15df67` is the LOW-PIT-01 *characterization* SHA and nothing more.

⛔ **Do not work in the primary worktree** `C:/LLM-RAG-APP/ai-trading-app`. It carries uncommitted copies
of `context.py` / `backtest_context.py` that match neither #661 nor `main`.

Before PR D activates Account 6, retarget onto the exact approved post-v1.0.1 base and rerun all
conformance tests.

---

## 21. Live-state findings that affect G0 (measured 2026-08-22, read-only)

### 21.1 Stale live parameters — confirmed, and one is worse than stale

`strategies.params_json` for strategy 8:

| Key | Live value | Issue |
|---|---|---|
| `fractional_shares` | `false` | Stale and misleading. v1.0.1 always sizes fractionally and documents that this cannot disable it. Clean it. |
| `use_market_regime_filter` | `true` | ⚠ **This key does not exist in the template's `default_params` or `params_schema`.** It is an orphan — exactly the "drift between strategy code and strategy schema" failure mode. It reads as an armed regime filter and is not one. Remove it. |

Both are G0 cleanup items. Removing them changes no behavior; leaving them guarantees a future reader
draws a false conclusion about what the live book was doing.

### 21.2 Live version and status

`version = 1.0.0`, `status = PAPER`, `risk_limits_id = NULL`, `has_pending_reload = 1`,
`cooldown_until = 2026-07-13 14:33:42` (expired). G0 must prove the running process reports **1.0.1**
after deploy. Per the standing rule, `has_pending_reload` is re-set by every backend start, so verify
the reload and start with **no restart in between**.

### 21.3 ★ Schedule default — a latent deployment defect, repaired in PR S

Live `schedule = "32 10 * * mon"`. The engine pins
`CronTrigger.from_crontab(..., timezone=America/New_York)` (`engine.py:106,528`), so this resolves to
**Monday 10:32 ET** — inside RTH, and consistent with the last observed rebalance at 14:32 UTC on
2026-08-17. **The live registration is correct.**

The **class default is not**:

```text
LOW-001 default schedule
      current template:  0 14 * * mon      -> Monday 14:00 ET   (2:00 pm)
      governed / live:   32 10 * * mon     -> Monday 10:32 ET
```

The template docstring still says "Monday 14:00 UTC ≈ 09:00 ET", which was true before schedules were
pinned to ET and is now wrong twice over. Recreating or re-registering LOW-001 from defaults would move
the rebalance by **3½ hours** with nothing flagging it.

**Repair (PR S):** set the template default to `32 10 * * mon`, correct the docstring, and add a test
that **resolves the cron through the engine's timezone** and asserts the next fire time is
`10:32 America/New_York` — *not* a test that string-matches the cron literal. A literal check would have
passed throughout the period the semantics silently changed.

### 21.4 Registered universe

`symbols_json` holds **200** tickers **including SPY**, i.e. 199 tradable names — not the "top-200 + SPY
= 201" the docstring claims. Record the actual set in the G0 capture.

### 21.5 HON — diagnosed, and it is a cost-basis field defect, not a quantity error

Account 6 HON order history: BUY 10 @224.14 (2026-07-07) → **MANUAL** SELL 10 @223.72 → BUY 10 @223.67 →
BUY 1 @231.59 (2026-08-17). True position 11 shares, true cost basis ≈ 2,468.
The `positions` row reads `qty = 11` (correct), `market_value = 2,374.90` (correct), but
`cost_basis = 231.589996` — **only the most recent fill's notional** — and
`avg_entry_price = 21.053636 = 231.59 / 11`.

So the recomputer overwrote `cost_basis` with the last fill instead of accumulating it. Quantity and
market value are unaffected; unrealized P&L is materially wrong.

⚠ **Reclassify the OPS item.** Account-6 HON activity is dated **2026-07-07** and **2026-08-17**; there
is **no 2026-07-27 HON order on this account**. The defect is:

> **HON cost-basis recomputation / restoration defect, associated with 2026-07-07 and 2026-08-17
> activity** — quantity correct (11); market value apparently correct; stored `cost_basis` incorrect;
> `avg_entry_price` incorrect because the recomputer overwrote rather than accumulated; unrealized P&L
> consequently wrong.

If 2026-07-27 is the restoration-incident date on which the corruption was introduced or detected, title
it accordingly — e.g. *"7/27 restoration incident — HON cost-basis symptom from 07-07 / 08-17 activity"*.
Otherwise remove 7/27 from the OPS ticket title. Do not keep an unqualified "7/27 HON event" label; it
sends the next reader to a date with no HON order on it.

This remains **out of scope** for Dynamic PIT (§14) and does not gate it.

### 21.6 The account is not pristine

42 MANUAL SELL orders, all FILLED, 2026-07-07 17:43–19:07 UTC, across 40 tickers — a manual unwind of the
initial book. This is the reason quantity-level ledger reconstruction is unsound (§5.4) and it should be
noted in the G0 record: "Account 6 has only ever been traded by strategy 8" is true of *strategies*, not
of *orders*.

---

## 22. Handoff checklist and STOP conditions

Before claiming implementation-ready for Account 6, answer **yes** to all:

- [ ] Can we show the exact PIT-200 membership and its hash for a rebalance?
- [ ] Can we show the exact research-selected quintile before execution filtering?
- [ ] Can a newly selected valid symbol be bought without permanent re-registration?
- [ ] Can a strategy-owned symbol always be discovered and reduced after it leaves PIT membership?
- [ ] Does the automated halt/deactivation path liquidate a dynamically acquired holding?
- [ ] Does every selected-but-not-executed symbol carry exactly one explicit reason?
- [ ] Are equal weights computed only after broker/price eligibility, and does the floor HOLD below it?
- [ ] Is the logical weekly rebalance idempotent across process restart?
- [ ] Are static strategies behaviorally unchanged?
- [ ] Does ownership ambiguity fail closed and surface to an operator?
- [ ] Can we reconstruct the final broker book from stored target/order/fill evidence?
- [ ] Is Account 6 activation still PAPER-only and version-bound?

### Mandatory STOP conditions

1. Dynamic enrollment would require changing the 252-session factor, quintile rule, weighting, or cadence.
2. The only way to buy a dynamic symbol would bypass strategy ownership/risk attribution globally.
3. A held symbol can become undiscoverable or unsellable because it left registration/PIT membership.
4. The system cannot distinguish a retry of the same rebalance from a new one.
5. The resolver would need to substitute a different symbol to keep the book near 40 names.
6. A schema migration would overwrite or reinterpret sealed pre-remediation evidence.
7. Dynamic behavior cannot be restricted to explicit `DYNAMIC_PIT` strategies.
8. ★ Ownership of a held position cannot be determined, and the code would proceed anyway.
9. ★ A change would widen BUY authority as a side effect of widening READ authority.

---

## 23. Final implementation ruling

### Program gate (owner, 2026-08-22)

> **Dynamic-PIT design work is authorized. Dynamic BUY implementation may begin only after #661 is
> merged and PR S proves that a strategy-owned held security outside `symbols_json` is discoverable and
> automatically liquidatable.**

The findings point toward a **cleaner** architecture, not a larger one:

- no new symbol registry — the global `symbols` table already covers ~14K active securities (§11 G-A);
- no `positions` schema migration now — set provenance plus broker quantity is sufficient and exact for
  Account 6 (§5.4), with six recorded triggers that reopen the question (§5.4.2);
- no fill-based quantity reconstruction, ever (§4.8);
- no weakening of any risk control — the resolver reads broker metadata and writes nothing to the
  symbol or risk layer.

### Authorized direction

Continue the LOW-001 conformance workstream under this v0.3
contract. Keep v1.0.1 isolated and independently deployable. Land the sell-visibility compatibility
release **before** any dynamic-acquisition code exists. Then build v1.0.2 so the weekly research-selected
PIT universe becomes the true execution universe through an explicit, auditable, fail-closed dynamic
enrollment mechanism.

**Do not change the strategy economics. Do not weaken static registration for other strategies. Do not
treat post-change P&L as validation. Do not ship the ability to acquire before the ability to dispose.**
