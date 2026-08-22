# LOW-PIT-01 — Registration Dependency Map & Sell-Path Audit

**Ticket:** LOW-PIT-01A (dependency map) + LOW-PIT-01B (sell-path audit)
**Governing spec:** `TradingWorkbench_LOW001_Dynamic_PIT_Execution_Design_Implementation_v0.2.md` §8, §21 Task 1–2
**Status:** COMPLETE — read-only characterization. No bypass code written. No files under `app/` modified.
**Date:** 2026-08-22
**Deliverable of:** PR A (capability + dependency map + static regressions)

---

## 0. Base commit (LOW-PIT-00)

All findings below are read against the **authoritative v1.0.1 tree**, not the primary worktree.

| | |
|---|---|
| Characterized tree | `C:/LLM-RAG-APP/ai-trading-app-low001-pr` (clean) |
| Branch | `fix/low001-v1.0.1-conformance` |
| Base SHA | **`c15df67146fd4936fbcc772edc1abff140279cdd`** (= `origin/fix/low001-v1.0.1-conformance`, PR #661 head) |
| Merge-base with `main` | `a8f1be2692c825a699965d9099ed48fc99da2ad0` |
| Commits ahead of `main` | 1 |

**⚠ Contamination hazard — the primary worktree is NOT the v1.0.1 base.** `C:/LLM-RAG-APP/ai-trading-app`
is on `research/mr002-validation2-lineage` and carries **uncommitted, partially-divergent copies** of the
LOW-001 files. Of the five `app/` files in #661: `accessor.py`, `session.py`, `low_volatility.py` match
PR #661 byte-for-byte, but `context.py` and `backtest_context.py` match **neither #661 nor `main`** — the
primary tree's copies are missing the P7 §7-A durable-state / settled-fill machinery that #661's branch
carries. Any LOW-PIT work started in the primary worktree would silently revert that. **Cut the
dynamic-PIT scaffold branch from `c15df67`, in its own worktree.**

---

## 1. What "registration" actually is

Two independent registries are both called "registration" in conversation. Conflating them is the single
biggest hazard in this workstream — they gate different things, at different layers, with different
failure modes.

| | **Strategy universe** | **Global symbol registry** |
|---|---|---|
| Storage | `strategies.symbols_json` (JSON list of tickers) | `symbols` table (`id, ticker, exchange, asset_class, name, active`) |
| Scope | one strategy row | platform-wide |
| Written by | `POST /strategies` · `PATCH /strategies/{id}` · `range_auto_select.py:369` | `AssetSyncService.sync_once()` — daily Alpaca `list_assets(active=True)` upsert |
| Loaded into runtime | `engine.py:387` → `StrategyContext.symbols` | queried per order |
| Enforced by | `StrategyContext` read methods + the template + the liquidation path | **risk engine** `engine.py:218–233` → `SYMBOL_DENIED` |
| Blocks orders? | **NO** | **YES** — hard reject, buys *and* sells |
| Model | `app/db/models/strategy.py:61` | `app/db/models/symbol.py` |

**The order path contains no strategy-universe check at all.** `grep -rn "symbols_json" app/risk app/orders
app/brokers` returns **zero hits**. Registration is enforced *upstream*, inside `StrategyContext`, by making
the strategy blind — not by refusing its orders.

That asymmetry is the load-bearing fact of this entire epic, and it cuts both ways: it is why dynamic
*buying* is reachable with a contained change, and it is why dynamic *selling* is currently
**unreachable** (§3).

---

## 2. Dependency map — the ten touch points (v0.2 §21 Task 1)

| # | Question | Location | Registration-gated? | Notes |
|---:|---|---|:---:|---|
| 1 | Where LOW-001 obtains its registered universe | `engine.py:387` `symbols = list(row.symbols_json) or list(cls.symbols)` → `StrategyContext(symbols=…)` `engine.py:456-467` → `ctx.symbols` `context.py:175` | — | `cls.symbols` is `[]` for LOW-001, so `symbols_json` is always authoritative |
| 2 | Where `universe_asof(n=200)` is called | `low_volatility.py:311` `ctx.factors.low_vol_scores(n=200)` → `accessor.py:87` → `factors/low_vol.py` → `universe.py:33` → `store.dollar_volume_universe()` `store.py:866` | **NO** | PIT universe is registration-blind. Already correct. |
| 3 | Where factor scores join to symbols | `accessor.py:87-104`; returns a DataFrame indexed by **ticker** | **NO** | |
| 4 | Where buy targets are filtered by registration | **`low_volatility.py:371,381-382`** — `allowed = {s.upper() for s in self.ctx.symbols …}`; `executable = [t for t in pit if t in allowed]`; `dropped` → `pit_name_not_registered` | **YES** | The named gap. In the *template*, not the platform. |
| 5 | Where held-position sells are authorized | `ctx.submit_order` `context.py:~530-563` → `OrderRouter.submit` → risk engine | **NO** (strategy universe) / **YES** (`symbols.active`) | See §3 |
| 6 | Where prices/subscriptions initialize | `low_volatility.py:525` `_price()` → **`ctx.get_recent_bars` `context.py:244`** → `bar_cache.get_bars` | **YES at the context; NO at the data layer** | `bar_cache.get_bars` (`market_data/bar_cache.py:94`) REST-backfills **any** ticker. The WS subscription set (`bar_stream.py:232`) covers only `schedule == "event"` strategies — LOW-001 is cron (`0 14 * * mon`), so it contributes nothing and needs nothing from it. |
| 7 | Where broker asset metadata is fetched/cached | `AlpacaAdapter.list_assets()` `brokers/alpaca/adapter.py:118` (daily sync) · `AlpacaAdapter.is_fractionable()` `:133` (per-symbol, cached, **fail-open**) | — | `get_asset` is the only per-symbol `tradable` source. `symbols` persists **`active` only** — no `tradable`, no `fractionable` column. |
| 8 | Where order ownership / attribution is enforced | `context.py:552-560` stamps `source_type=STRATEGY`, `source_id=str(strategy_id)`, `user_id`, `account_id` | **NO** | Attribution is by `source_id`, **not** by symbol membership |
| 9 | Where the week guard / durable signals participate | `low_volatility.py:242-289` (`_as_of_date`, `_week_completed`, `_mark`) · `ctx.recent_payloads` · `engine.py:918` `_claim_slot` · `ctx.dispatch_seq` `engine.py:928` | — | Unaffected by registration |
| 10 | Where completion is recorded | `low_volatility.py:263` `_mark("rebalance_completed", wk)` → `signals.payload_json` | — | |

### Also registration-gated (not on the v0.2 list — found during the audit)

| # | Location | Behavior | Why it matters |
|---:|---|---|---|
| 11 | **`activation.py:514`** `strategy_symbols = set(strategy.symbols_json or [])`, then `if symbol not in strategy_symbols: continue` | The **automated liquidation path** (deactivation / halt) skips any broker position whose ticker is not in `symbols_json` | A second, *safety-critical* exit path that registration silently disables. Also case-sensitive (no `.upper()`). |
| 12 | `context.py:292-317` `get_positions()` | Filters positions to `ctx.symbols` | Position *discovery* is registration-scoped |
| 13 | `context.py:319-345` `get_position_for()` | Returns `None` outside `ctx.symbols` | |
| 14 | `context.py:352` `pending_buy_qty()` | Filters to `ctx.symbols` | In-flight netting would silently under-count for enrolled names |
| 15 | `context.py:579` `log_signal()` | **Warns but proceeds** — writes the row | Evidence *can* be recorded for unregistered symbols today |
| 16 | `engine.py:932` `_dispatch_bar_tick` | Iterates `running.symbols`, fetches a bar per symbol, calls `on_bar` | Registration is also the **dispatch trigger**. `on_bar` never fires for an unregistered symbol. |
| 17 | `risk/engine.py:252-264` `limits.allowed_symbols` / `denied_symbols` | Per-user risk-limit allowlist → `SYMBOL_DENIED`, **buys and sells alike** | ⚠ **Live-config unknown.** If user 6's `risk_limits` row has a non-empty `allowed_symbols`, dynamic PIT is dead on arrival *and* exits are already at risk. **Must be read on ec2-paper before PR B.** |

### Not registration-gated (confirmed clean)

- `PositionSyncService` (`services/position_sync.py:118-197`) resolves via the **global `symbols` table**, never `symbols_json`. Positions in dynamically enrolled names **will** sync. It skips (and drift-counts) tickers with no `symbols` row.
- `OrderRouter` (`app/orders/router.py`) — no symbol-universe logic beyond fractionable flooring (`:149-174`).
- `BarCache` — ticker-agnostic.

---

## 3. LOW-PIT-01B — the unregistered-held-symbol sell question

> **Q: Can v1.0.1 sell a currently held LOW-001 position whose symbol is not in the static registration list?**

### Answer: **No — and the reason is not the one the rollback risk assumes.**

**The order path permits it. The strategy cannot form the intent.**

Verified empirically against the real `StrategyContext` on base `c15df67` (temporary probe, provenance
asserted via `app.__file__`, run and then deleted; the worktree is clean). Registered `["AAA"]`, held
position in `XYZ` with an active `symbols` row:

| Probe | Result | Meaning |
|---|---|---|
| `get_position_for("XYZ")` | **`None`** | strategy cannot see the position |
| `get_positions()` | **`[]`** | ditto, in bulk |
| `get_recent_bars("XYZ")` | **empty** + `strategy_requested_unauthorized_symbol` | cannot price it |
| `submit_order(SELL XYZ)` | **reached the router**, stamped `user 1 / acct 1 / src 8` | ✅ **no registration check on submit** |
| `log_signal("XYZ")` | **`signal_id=1`** (warns, does not drop) | ✅ evidence is recordable |
| `pending_buy_qty()` | `{}` | filtered |

Layered on top, by code reading:

- `OrderRouter.submit` — no strategy-universe check (`grep symbols_json app/orders` → 0 hits).
- Risk engine — the only symbol predicate is `Symbol.ticker == t AND Symbol.active IS TRUE`
  (`risk/engine.py:218-233`), plus the per-user `allowed_symbols` / `denied_symbols` lists (`:252-264`).

### The two blockers, precisely

1. **`low_volatility.py:474`** — `_current_holdings()` iterates `for sym in self.ctx.symbols`. A held name
   outside `symbols_json` is **never enumerated**, so `_apply_targets` never reaches the
   `if sym not in target_set: SELL` branch at `:412-414`. The exit intent is never constructed.
2. **`context.py:319`** — even given the ticker, `get_position_for` returns `None`, so the quantity is
   unknowable.

### Three consequences the spec should absorb

**(a) Rollback stranding is real, and confirmed.** v1.0.2 dynamically buys `XYZ`; roll back to v1.0.1; `XYZ`
is invisible to LOW-001 forever. It is not *unsellable* — a **manual order via the UI/API works fine**
(`source_type=MANUAL` never touches `ctx`) — but no automated path will ever exit it. v0.2 §12.4 ("keep
risk-reducing sells available") is satisfied only in the manual sense today.

**(b) The same defect exists *within* v1.0.2, not only on rollback.** If dynamic enrollment is scoped
per-rebalance (v0.2 §5.2) and `_current_holdings()` still reads `ctx.symbols`, then a name enrolled in
week *N* and dropped from PIT-200 in week *N+1* is **not enumerated in week N+1** — so it is never exited.
The exit invariant (LOW-PIT-04, gate G4) is therefore **not** "don't add a new membership check"; it is
**"make held-position discovery a union that includes held-but-unregistered names."** That is a *positive*
requirement on the resolver, and it must land in **PR B alongside** dynamic buying, never after it.
Shipping the buy without it creates positions the system cannot sell.

**(c) Automated liquidation has the same hole.** `activation.py:514` filters broker positions by
`symbols_json`. Deactivation/halt liquidation would skip a dynamically enrolled name too. This is a
*safety* control, so it must be fixed in the same PR as (b).

### Sell-only compatibility patch — recommendation

v0.2 §2 anticipates "a pre-staged sell-only compatibility patch if necessary". **It is necessary**, and it
should be **pre-staged against v1.0.1 before v1.0.2 is ever activated on Account 6** — a rollback that needs
a code change to be safe is not a rollback. Minimal shape (no new capability, no buy-side change, safe for
static strategies because for them the extra set is always empty):

- `StrategyContext`: admit **held symbols** to `get_position_for` / `get_positions` — i.e. a symbol with a
  non-zero `Position` row on this account is readable regardless of `symbols_json`. This is strictly
  risk-reducing: it grants *visibility*, and the only strategy-side use of visibility is the exit branch.
- `low_volatility.py:_current_holdings()`: enumerate `ctx.symbols ∪ held`.
- `activation.py:514`: liquidate any position the strategy can be shown to own, not only registered tickers.

**Open question for the owner (attribution).** Positions are keyed `(account_id, symbol_id)` with **no
`strategy_id`** (`db/models/position.py:20-23`). Today "which positions are LOW-001's?" is answered *only*
by `symbols_json` being that strategy's private universe on a single-strategy account. Once enrollment is
dynamic, that answer disappears. Account 6 currently runs LOW-001 alone, so "every position on the account"
is a correct-today shortcut — but it is a **STOP condition under v0.2 §22.2** if generalized. The durable
answer is attribution by **`orders.source_id`** (already stamped, `context.py:552-560`). Settle this before
PR B, not inside it.

---

## 4. Registration-dependent services dynamic enrollment must reproduce

For a dynamically enrolled symbol, the following are supplied by registration today and must be recreated —
nothing more, and nothing less:

| Service | Supplied today by | Must be reproduced how |
|---|---|---|
| **Price read** | `ctx.get_recent_bars` allow-check (`context.py:244`) | Admit enrolled symbols. Data layer already works — `bar_cache` REST-backfills any ticker. |
| **Position read** | `get_position_for` / `get_positions` (`context.py:292,319`) | Admit enrolled **and held** symbols (§3). |
| **In-flight netting** | `pending_buy_qty` (`context.py:352`) | Admit enrolled symbols, else duplicate baskets on retry (incident 2026-06-22). |
| **Signal/evidence write** | `log_signal` (`context.py:579`) | Already works (warns only). Drop the spurious warning for enrolled symbols. |
| **Risk-engine symbol resolution** | `symbols` row with `active=True` (`risk/engine.py:218`) | Already satisfied for any Alpaca-active US equity by `AssetSyncService`. **Verify the sync is actually running on ec2-paper.** |
| **Risk allow/deny list** | `limits.allowed_symbols` (`risk/engine.py:252`) | **Read user 6's live row** (§2 #17). |
| **Order attribution** | `source_id` stamping (`context.py:552`) | Nothing to do — symbol-independent. |
| **Position sync** | global `symbols` table | Nothing to do. |
| **Dispatch trigger** | `running.symbols` (`engine.py:932`) | Nothing to do — LOW-001 only needs *one* registered symbol to fire `on_bar`; enrollment is resolved inside the rebalance. **Do not empty `symbols_json`.** |
| **WS market-data subscription** | not used by LOW-001 (cron, not `event`) | Nothing to do. |
| **Automated liquidation** | `activation.py:514` | Must be widened (§3c). |

**Not** required: broker permissions (per-symbol permissioning does not exist), per-symbol risk limits
(limits are user/account-scoped), per-symbol strategy state (`strategy_state` is keyed by
`(strategy_id, key)`).

---

## 5. Hard architectural constraint discovered (shapes PR A)

**`check_strategy_isolation.sh` forbids anything under `apps/backend/app/strategies/` from importing
`app.brokers`.**

The `DynamicSymbolResolver` must call `AlpacaAdapter.get_asset` / `is_fractionable` to establish
`active` / `tradable` / `fractionable`. **Therefore the resolver cannot live under `app/strategies/`.**

It must live outside (`app/orders/`, or a new `app/universe/`) and be **injected into `StrategyContext` by
the engine**, exactly as `submit_order_fn` is today (`engine.py:396-467`). Same shape, same reason:
`StrategyContext` is the one authorized seam between strategy code and broker capability. Any design that
puts broker lookups inside the template or inside `app/strategies/` breaks a CI invariant on the first push.

Related: the ADR 0051 research-plane isolation scripts named in `CLAUDE.md`
(`check_research_plane_order_path_isolation.sh`, `check_research_plane_no_broker_capability.sh`) **do not
exist in this tree**. The invariants that actually bind today are `check_strategy_isolation.sh` and
`check_altdata_order_path_isolation.sh`, and both constrain *research → order-path*, never the reverse.

---

## 6. Design decision A — permanent security identity: **reuse, do not invent**

An owner-ruled permanent identity already exists (ruling 2026-07-29):

```
app/validation/security_lineage.py
SECURITY_IDENTITY_CONTRACT = "PERMATICKER_EFFECTIVE_INTERVAL_V1"
security identity = Sharadar permaticker + effective-date interval
```

- The module is **pure stdlib** (`dataclasses`, `datetime`, `enum`, `typing`) — importable from the order
  plane with no isolation-invariant risk.
- `permaticker` is already **materialized** in the factor store's `tickers` table
  (`factor_data/store.py:39,43,86,96,300`), non-null across the governed slice.
- `store.dollar_volume_universe()` (`:866-900`) already `JOIN`s `tickers t` — projecting `t.permaticker`
  alongside the ticker is a column addition, **not** a new data source.

**Recommendation.** The enrollment record carries **both** identities and is reconciled identity-first:

| Plane | Key | Authority |
|---|---|---|
| Research / universe / lineage | `permaticker` + effective interval | authoritative for *what security this is* |
| Execution / broker | `symbols.id` + `ticker` | authoritative for *what we can send to Alpaca* |

A ticker change within one `permaticker` is an **attribute change**, not a new security. A ticker that
changes `permaticker` inside the lookback is a **refusal** (already implemented — `LINEAGE_GAP_SESSIONS`,
lineage refusal). Do not create a third ID.

**Gap to close in PR A:** `universe_asof()` returns `list[str]` — bare tickers, no permaticker, no as-of, no
hash. The `PITUniverseProvider` contract (v0.2 §17.1 `PITUniverseSnapshot`) is the natural home for that
projection.

---

## 7. Design decision B — universe provider contract (freeze before v1.0.2 activation)

Today `universe_asof` is deterministic and genuinely PIT (`universe.py:40-53`), which is the hard part and
it is already done. What is **missing** for the v0.2 §6 Step 3 evidence requirement:

| Required | Present? |
|---|---|
| PIT-200 membership persisted | ❌ nothing persists it |
| Membership **hash** | ❌ does not exist |
| `pit_as_of` recorded | ❌ |
| Permanent identifiers alongside tickers | ❌ tickers only |
| Short-universe HOLD threshold | ❌ no floor — a store returning 12 names silently produces a 3-name book |
| Source/store version binding | ❌ |

The definition of "top 200" is already frozen and unambiguous: `SUM(close × volume)` over the trailing
`lookback_days` calendar days, restricted to `firstpricedate ≤ as_of ≤ lastpricedate`, ordered
`dollar_volume DESC, ticker ASC`, `LIMIT n`. **Freeze that text verbatim** — it is the contract.

---

## 8. Design decision C — executable-set floor: confirmed, and larger than it looks

There is **no** `min_executable_fraction` today. `_apply_targets` (`low_volatility.py:429-433`) computes:

```python
per_name = min(equity / k, equity * max_position_pct)   # k = len(priced), max_position_pct = 0.10
```

With a 40-name selection:

| Executable `k` | per-name | gross deployed | behavior |
|---:|---:|---:|---|
| 40 | 2.5% | 100% | intended |
| 25 | 4.0% | 100% | **silently 1.6× concentrated, fully invested, no signal** |
| 10 | 10.0% | 100% | at the cap |
| 5 | 10.0% | **50%** | under-deployed *and* concentrated |

`max_position_pct = 0.10` does not bind until `k < 10`, and when it does it starts silently
**under-deploying** rather than holding. So between 40 and 10 names the book concentrates invisibly, and
below 10 it both concentrates *and* leaves cash — two different failures, neither of which HOLDs.
A frozen floor (v0.2's ~70% ⇒ 28 of 40) is the right control. The number can be set later; **that a floor
exists must be decided before PR C**, because it changes the `TargetBuilder` return type (a `HOLD` outcome,
not just a plan).

---

## 9. Initial test locations and fixtures

| Purpose | Location |
|---|---|
| LOW-001 template behavior | `apps/backend/tests/strategies/test_low_volatility_template.py` (404 ln) |
| Real-`StrategyContext` gates (DB-backed, `session_factory` fixture) | `apps/backend/tests/strategies/test_context.py` (369 ln) |
| Engine dispatch / registration wiring | `test_engine.py`, `test_engine_live_dispatch.py`, `test_rebalance_dispatch_idempotency.py` |
| Static-strategy regression targets (G1) | `test_momentum_portfolio.py`, `test_combined_book_template.py`, `test_range_trader_template.py` — the *other* books that must not change |
| Risk-engine symbol gate | `apps/backend/tests/risk/` |
| Liquidation path (§3c) | `test_activation_hold_enforcement.py` |

**Already present in #661 — v0.2 §21 Task 2's "before" test exists:**
`test_pit_unregistered_names_are_logged_not_ordered` (`:344`) pins today's `pit_name_not_registered`
behavior. Reuse it as the before/after anchor.

**⚠ The template's fake context is more permissive than the real one — it will produce false passes.**
`_ctx()` (`test_low_volatility_template.py:68-113`) is a `MagicMock` whose
`get_position_for = lambda s: _pos(holdings[s]) if s in holdings else None` — it **ignores `ctx.symbols`
entirely**, while the real `StrategyContext.get_position_for` returns `None` outside it. Likewise
`get_recent_bars` returns a price for **any** symbol.

Consequence: a naive exit-invariant test written against this fake would **pass on code that strands the
position in production**. `test_sells_names_leaving_the_book` (`:265`) does not catch this because its held
name `CCC` *is* in `ctx.symbols`.

**Required before any G4 claim:** tighten `_ctx()` to mirror the real gates (return `None` / empty outside
`ctx.symbols`), *then* add the exit tests. Do this as the first commit of PR A — it is a test-fidelity fix,
not a behavior change, and it will immediately turn some currently-green assumptions red.

New fixtures needed: a `symbols`-table row for an unregistered-but-active ticker; a broker-adapter double
exposing `get_asset` with `active` / `tradable` / `fractionable`; a frozen PIT-200 list containing at least
one name absent from `symbols_json` (v0.2 §8 LOW-PIT-07A).

---

## 10. Conflicts with #661

### 10.1 #661 is currently **RED**, with a single root cause

| Check | Result |
|---|---|
| Detect changes | pass |
| Python (backend) — LIGHT | pass (3m19s) |
| **Python FULL (backend)** | **FAIL** (26m55s) |
| **Python CI Gate** | **FAIL** (3s) — purely downstream: `a Python project changed but FULL suite result='failure'` |

One failing test:

```
tests/strategies/test_rebalance_dispatch_idempotency.py::
  test_every_live_template_keys_on_the_dispatch_not_the_bar[low_volatility]
AssertionError: low_volatility still lacks the dispatch guard
assert "self._last_dispatch_seq" in src
```

This is a **source-text** cross-template invariant (`:174-190`) asserting all four live books share one
idiom. #661 renamed LOW-001's guard `_last_dispatch_seq` → `_inflight_dispatch`
(`low_volatility.py:224,246-249`). The *semantics are intact and arguably clearer*; only the literal the
invariant greps for changed. Not a flake, not environmental.

**Recommended fix: rename the attribute back to `_last_dispatch_seq` in `low_volatility.py`** (3
occurrences). It preserves the invariant's actual purpose — one shared idiom across all four books — costs
nothing behaviorally, and avoids weakening a tripwire to accommodate one strategy. The alternative
(relaxing the test to accept either name) trades a real invariant for a naming preference; don't.

Fixing this should turn both FULL and the Gate green. **This is #661's work, not LOW-PIT's** — flagged here
because it currently blocks the "merge 1.0.1 → cut clean v1.0.2 branch" sequence.

### 10.2 File-level conflicts LOW-PIT will create

| File | #661 touches | LOW-PIT will touch | Conflict risk |
|---|:---:|:---:|---|
| `app/strategies/context.py` | ✅ | ✅ **heavily** (§4 — every read gate) | **HIGH.** PR A must branch from `c15df67`, never from `main`. |
| `strategies_user/templates/low_volatility.py` | ✅ | ✅ (`_select_targets`, `_current_holdings`, `_apply_targets`) | **HIGH** — same functions #661 just rewrote. |
| `app/strategies/backtest_context.py` | ✅ | ✅ (parity with context gates) | MEDIUM — the two contexts must stay in lockstep; `test_context_pending_buy_parity.py` and `test_context_durable_state_parity.py` already enforce parity and **will fail** if only one side is changed. |
| `app/market/session.py` | ✅ | ❌ reuse only | None — v0.2 §6 Step 2 mandates reusing this exact calendar logic. |
| `app/factor_data/accessor.py` | ✅ | ✅ (permaticker / as-of projection, §6–7) | MEDIUM |
| `app/services/activation.py` | ❌ | ✅ (§3c) | None |
| `app/orders/router.py`, `app/risk/**` | ❌ | ❌ **must stay untouched** | v0.2 §17.3 forbidden dependency: `OrderRouter → infer research selection` |

### 10.3 Semantic conflicts

- **Freshness:** #661's `expected_last_session` / `session_lag` (`low_volatility.py:69-83`) via
  `MarketSession.previous_trading_day` is the **single** implementation dynamic PIT must reuse (v0.2 §6
  Step 2). Do not add a second.
- **`pit_name_not_registered`:** #661 introduces it (`:383-390`); v0.2 §6 Step 6 demotes it from a terminal
  outcome to a pre-resolver observation. Plan the transition — do not delete the signal name, or the
  sealed-window evidence stops parsing.
- **Sealed window:** #661 also carries `docs/implementation/TradingWorkbench_LOW001_PaperWindow_…` and its
  JSON, SHA `81be681c…`, `OBSERVATION_ONLY`. LOW-PIT must not touch either file (v0.2 §2, §22 STOP 6).

---

## 11. Answers to the seven questions asked

1. **Registration dependency map** — §1–§2. Two registries, seventeen touch points, five clean.
2. **Concrete code touch-point list** — §2, with `file:line`.
3. **Unregistered-held-symbol sell** — §3. **The order path permits it; the strategy cannot form the
   intent.** Rollback stranding confirmed (automated only — manual sell works). Two additional findings:
   the same defect exists *within* v1.0.2 week-over-week, and automated liquidation has the same hole.
4. **Permanent security ID to reuse** — §6. Sharadar `permaticker` + effective interval,
   `PERMATICKER_EFFECTIVE_INTERVAL_V1`, already owner-ruled, already in the store, pure-stdlib module.
   **Do not invent a new ID.**
5. **Registration-dependent services to reproduce** — §4. Six to widen; five need nothing.
6. **Initial test locations / fixtures** — §9, including the **fake-context fidelity defect** that would
   otherwise manufacture a false G4 pass.
7. **Conflicts with #661** — §10. #661 is red on one source-text assertion with a one-line fix;
   `context.py` and `low_volatility.py` are high-conflict; branch from `c15df67`.

---

## 12. Recommended gate for LOW-PIT-01 acceptance

Two items must be settled before PR B, neither of which can be answered from the repository:

- **G-A (live config):** read user 6's `risk_limits.allowed_symbols` / `denied_symbols` on `ec2-paper`.
  A non-empty allowlist blocks dynamic PIT entirely **and** is a latent exit hazard today.
- **G-B (owner ruling):** position attribution once enrollment is dynamic — `orders.source_id` (durable,
  correct) vs "every position on Account 6" (correct-today, a §22.2 STOP condition if generalized).

Both are cheap. Neither should be discovered inside PR B.

---

## 13. Compliance statement

- No LOW-001 economics changed. No code under `app/` or `strategies_user/` modified.
- No registration bypass written (v0.2 §21: "Do not begin by removing the registration check").
- No Account 5 change. No live-money authorization. No persistence schema change.
- The characterized worktree is clean; the temporary probe was deleted after execution.
- LOW-001 remains **Diversifier (B)**. This is conformance / execution engineering, not strategy
  optimization.
