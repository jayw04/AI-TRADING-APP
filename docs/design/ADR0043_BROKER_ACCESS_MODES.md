# Broker access modes and the governed read-only boundary (ADR 0043 WS5)

Alpaca issues no read-only scope for paper API keys: any valid key can submit an
order. "Holding a credential" and "being permitted to trade" therefore cannot be
the same thing, and the separation has to live in code rather than in an
operator's environment file. This document describes the boundary that enforces
it and inventories every broker construction site in the repository.

## Modes

| Mode | Meaning |
|---|---|
| `disabled` | No broker access. **The resolved value when configuration is absent or empty.** |
| `read_only` | Exactly four GET routes; every mutation fails closed before transport. |
| `trading` | Reads plus mutation — but only when `strategy_execution_enabled` **and** `scheduler_enabled` are also true. |

An unrecognised value raises `BrokerConfigurationError` at startup. It is never
downgraded to `disabled` silently, because a typo that quietly disables the
broker is as much a governance failure as one that quietly enables it.

```
WORKBENCH_BROKER_ACCESS_MODE=            -> disabled   (fail closed)
WORKBENCH_BROKER_ACCESS_MODE=read_only   -> the four approved GETs
WORKBENCH_BROKER_ACCESS_MODE=readonly    -> startup error (not a synonym)
```

## The two controls

**Control 1 — execution authority gate** (`app/brokers/policy.py`).
`BrokerAccessPolicy.orders_allowed` requires `mode is TRADING` *and*
`strategy_execution_enabled` *and* `scheduler_enabled`. Order capability can
never rest on one boolean, and a trading-capable key with missing configuration
is inert.

**Control 2 — read-only broker boundary** (`app/brokers/transport.py`,
`readonly_client.py`). The policy check is the first statement in
`GovernedTransport.request`; nothing below it executes for a denied call. The
tests assert the injected sender's **call count is zero**, not merely that an
exception surfaced — an exception raised after dispatch would still have reached
Alpaca.

### Escapes deliberately closed

| Escape | Closure |
|---|---|
| Non-GET methods | refused by policy before dispatch |
| Sub-routes (`/v2/orders/{id}`) | allow-list is **exact**, not prefix-matched |
| Path traversal (`/v2/orders/../orders/abc`) | `normalise_path` collapses `.`/`..` before matching |
| **Check/dispatch divergence** | the path is normalised **once**; policy authorises and transport sends the identical string |
| Absolute URLs / alternate hosts | `_resolve_path` refuses any host but the bound one |
| Protocol-relative (`//host/…`) | refused |
| Redirects | refused outright (`max_redirects=0`) |
| Generic passthrough | no `get`/`post`/`raw`/`request` helper exists on the client |
| SDK handle leakage | the read-only client exposes no `client`/`session`/`sdk` attribute and returns plain dicts |
| Familiar mutator names | bound as tombstones that raise, so a refactor cannot reintroduce them by accident |

> The check/dispatch row was found by a test, not by review: `/v2/orders//` was
> authorised as `/v2/orders` and dispatched as `/v2/orders//`. A parser
> differential of exactly the kind an allow-list is supposed to prevent.

## Broker construction-site inventory

Every site that builds a broker client or reaches an Alpaca host, with its
disposition. **No site was silently rerouted** — rerouting the live order path
would change behaviour on the paper box.

| # | Site | Kind | Disposition |
|---|---|---|---|
| 1 | `app/lifespan.py:136` `AlpacaAdapter()` | trading-capable | **Left as-is.** Live paper-box startup path. Retrofitting the gate here would break an authorised trading path on next deploy. Adjudication required before rerouting. |
| 2 | `app/orders/router.py:587` `_resolve_adapter` | trading-capable | **Left as-is.** OrderRouter's per-account resolution; already governed by ADR 0002 `_router_token` and the risk engine. |
| 3 | `app/brokers/registry.py` `BrokerRegistry` | resolver | **Left as-is.** Feeds sites 1–2. |
| 4 | `app/brokers/alpaca/streaming.py` `TradeUpdatesStream` | read stream | **Left as-is.** Consumes fills; submits nothing. |
| 5 | `app/services/bar_stream_adapter_alpaca.py:48` `StockDataStream(` | market data | **Out of scope.** `data.alpaca.markets`, not a trading host; no order surface. |
| 6 | `app/market_data/**` (`BarCache`) | market data HTTP | **Out of scope.** Market-data host only. |
| 7 | `scripts/adr0043_scoped_sync.py:629` `AlpacaAdapter(credentials=creds)` | trading-capable | **Operator script, not app runtime.** Not reachable from a WS5 image; flagged for adjudication if ever run against a governed runtime. |
| 8 | `scripts/adr0043_session_open.py:508` `AlpacaAdapter(creds)` | trading-capable | Same as #7. |
| 9 | `app/brokers/factory.py` `get_broker_client` | **governed** | The new boundary. The only site a successor WS5 image uses. |

Sites 1–4 and 7–8 remain trading-capable by construction. They are **not**
governed by `broker_access_mode`; they retain their existing ADR 0002 controls.
That is a deliberate, disclosed limitation of this PR, not an oversight.

## Configuration a successor WS5 image will use

```
WORKBENCH_BROKER_ACCESS_MODE=read_only
WORKBENCH_STRATEGY_EXECUTION_ENABLED=false
WORKBENCH_SCHEDULER_ENABLED=false
WORKBENCH_ALPACA_STARTUP_ENABLED=false
WORKBENCH_BROKER_EXPECTED_ACCOUNT_ID=<successor account number>
```

Code path: `app.brokers.factory.get_broker_client(...)` →
`GovernedTransport` → `ReadOnlyBrokerClient`. The successor runtime must obtain
its client **only** from the factory; constructing `AlpacaAdapter` directly
bypasses both controls.

Credential naming for the successor canary is deliberately distinct from
`ALPACA_PAPER_7_*`, which collides with Workbench account 7 / strategy 9
(`combined-book`, historically `PA3344TNRFYD`):

```
ADR0043_SUCCESSOR_CANARY_ALPACA_API_KEY
ADR0043_SUCCESSOR_CANARY_ALPACA_API_SECRET
ADR0043_SUCCESSOR_CANARY_ACCOUNT_ID
```

## Account-identity latch

`expected_account_id` is mandatory for a read-only client. On the first
`get_account()` the reported `account_number` is compared; a mismatch raises
`BrokerAccountMismatch` and **latches** — every subsequent read re-raises without
dispatching. ADR 0043 §10 makes a broker-identity mismatch a stop condition, so
the client must not keep serving reads from an account it knows is wrong.
