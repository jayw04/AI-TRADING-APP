# G4b operational disposal reachability — narrow prospective proof

**Verdict:** `G4b operational reachability = PASS / DISPOSAL PATH REACHABLE / TERMINAL LIQUIDATION EXECUTION NOT TESTED`

⛔ **Read that wording exactly.** This record establishes that the disposal control path is *reachable*
and that no gate refuses it. It is **not** evidence that a liquidation would execute correctly.
Terminal liquidation execution correctness is **out of scope and not required** unless an actual
liquidation decision is later authorized — this narrow safety proof must never be read as creating a
demand for a test order.

**Executed:** 2026-08-31, 10:03–10:06 America/New_York, read-only, on `ec2-paper`
**Authority:** owner authorization, this session — a narrow non-liquidating reachability/conformance
proof. ⛔ **NOT** an S8.6 replacement, ⛔ **NOT** liquidation authority, ⛔ **NOT** Track-C revival.

## Runtime binding (no `.deploy_src_sha`, no `956e932…` literal)

| leg | value |
|---|---|
| frozen artifact identity | `deployed_repository_commit = b94838b6aa611e02982b3d1ae5ca5333b5f1d80e` |
| embedded build record | `adr0043_implementation_commit = 38f40b46906fc91497049924f7a62e7384d67653` |
| **runtime-derived** code identity | boot log `runtime code identity verified: sha256:a52823f3bf4e7c919c0a549508230d9de66700042837ab4e9eb02fb98e320a7a` |

The obsolete `956e932…` literal is not used anywhere in this proof. `.deploy_src_sha` is absent and is
relied on for nothing.

## Q1 — Owned-holdings discovery: **PASS**

Cardinality **derived at execution time**, never asserted:

- live Account-6 position book, nonzero: **34** (from `positions ⋈ symbols`, probe time)
- `StrategyOwnedHoldingsProvider.resolve(account_id=6, strategy_id=8)` → **owned 34 · excluded 0**
- **unaccounted: 0** — every held name is classified

Identities: `AAPL, ABBV, BAC, BRK.B, CME, COST, CVX, DIS, HD, JNJ, JPM, KO, LIN, MA, MCD, MDT, MO,
NEE, PEP, PFE, PG, PH, ROST, RTX, SCHW, SHEL, T, TJX, UNP, V, VZ, WELL, WMT, XOM`

`identity_resolver.ready = True`; `default_as_of = 2026-08-28` — the **coverage frontier, not the wall
clock**. That defaulting is the repair for the 2026-08-23 failure, where wall-clock dating closed every
effective interval and all holdings resolved to `None`. It is meaningful for the first time today
because factor readiness is legitimately GREEN and the frontier advanced to 2026-08-28.

## Q2 — Disposal-path REACHABILITY: **PASS**, established without submitting an order

Every fail-closed branch of the deployed `PaperStrategyLiquidationService.liquidate()` precondition
chain resolves non-`None` on this runtime:

| seam precondition | observed | fail-closed meaning if absent |
|---|---|---|
| wiring block executed | boot log `strategy_ownership_provisioned identity_resolver_ready=true` @ `2026-08-31T10:07:43Z` | capability never provisioned |
| policy grant | `PaperLiquidationPolicy.for_pr_s()` → `enabled=True strategies={'low-volatility'}` | `PaperLiquidationDenied` |
| grant is LOW-001-**only** | permits `low-volatility`=**True**; `sector-rotation`/`combined-book`/`Range Trader Top-5`=False; default-constructed policy=False | — |
| strategy name matches grant | strategy 8 `name='low-volatility'` → `permits=True` | denied |
| PAPER account resolves | `account_id=6, broker=alpaca, mode=paper` | returns EMPTY result |
| provider / resolver non-None | `provider.ready=True`, `identity.ready=True` | returns EMPTY result |
| broker adapter resolves | `registry.load_all(); get(6)` → **`AlpacaAdapter`**, exposes `get_positions` | returns EMPTY result |
| adapter actually fetching | live app synced 34 Account-6 positions **4 s** before the probe | — |

⭐ The historical defect this check exists to prevent — *"the capability existing as an uncalled object,
or as a callable object that answers `None`"* — is **excluded at every link**.

### Boundary of the proof — stated, not glossed

`StrategyPositionLiquidator.liquidate()` was **never called**. Its terminal loop — the one that builds
`OrderRequest`s and calls `router.submit()` — is therefore **not observed**. The deployed
implementation exposes **no dry-run, plan, or preview path**, so that final step cannot be exercised
without submitting real orders, and it was deliberately not exercised. What is proven is that the
control path *reaches* the seam and that no gate refuses it; what is not proven is the submit loop.

## Q3 — Safety boundary: **PASS**

No liquidation orders. No position change. Strategy 8 untouched: still `IDLE`, schedule `32 10 * * mon`
unchanged, **`has_pending_reload = 1` left as-is** (not cleared as housekeeping). No credential rendered
at any point. All broker work was construction-only — no `connect()`, no `get_positions()` by the probe.

## Probe defects recorded (mine, not the system's)

1. Guessed `positions.symbol`; the real schema is `symbol_id → symbols.ticker`.
2. `BrokerRegistry` is `app.brokers.registry`, not `app.brokers.factory`.
3. ⚠ **A freshly-constructed `BrokerRegistry` returns `None` from `get()` until `load_all()` runs.**
   My first probe reported `get(6) -> None` and that was a **probe artifact, not a finding** — it says
   nothing about the live app's registry. Nearly logged as a G4b failure.
