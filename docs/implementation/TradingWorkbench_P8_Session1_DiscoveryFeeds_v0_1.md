# Trading Workbench — P8 §1: Alpaca Discovery Feeds + Caching

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-07 |
| Phase | P8 — Discovery screener + Range Insight (§1 of 7 — opens P8a) |
| Predecessor | `p7-session8-polish-complete` (P7 complete) |
| Successor | `TradingWorkbench_P8_Session2_*` (scanner engine — §2) |
| Direction | `TradingWorkbench_P8_Direction_v0.1.md` (settled decisions 1–6; open Q1, Q2) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Fetch Alpaca's most-actives + market-movers screener feeds behind a short in-memory TTL cache, and expose them on one read endpoint. The candidate-symbol seed source for the scanner (§2) and the Discovery view (§3). |
| Estimated wall time | 3–4 hours |
| Tag on completion | `p8-session1-discovery-feeds-complete` |
| Out of scope | See §"What this session does NOT do" |

---

## Why this session exists

P8's Discovery screener needs a *candidate universe* to evaluate criteria against — Alpaca's most-actives and market-movers feeds are the structured seed sources (P8 Direction, "what P8 newly introduces": *"Two new Alpaca endpoint integrations — `/v2/stocks/most-actives` and `/v2/stocks/movers`"*). §1 lands exactly those two integrations with caching, and nothing else: no criteria evaluation (that's §2), no UI (§3), no scheduling (§4). It is the data-fetch floor the rest of P8a builds on.

These feeds are intraday-volatile and Alpaca's free tier is rate-limited, so the fetch sits behind a short in-memory TTL cache — the same pattern `app/market_data/quotes.py` already uses for latest-quote fetches (in-process dict + TTL + `asyncio.Lock` + lazy SDK import + `run_in_executor`).

## What this session ships

1. `app/market_data/discovery.py` — `get_discovery_feeds(top)` returning `{most_actives, gainers, losers, last_updated, stale, error}` behind a 5-minute in-memory TTL cache; stale-on-error fallback.
2. `app/api/v1/schemas/discovery.py` — the response models.
3. `app/api/v1/discovery.py` — `GET /api/v1/discovery/feeds` (auth-gated), registered in `app/api/v1/__init__.py`.
4. Tests: `tests/market_data/test_discovery.py` (cache hit, stale-on-error, empty+flag, payload shape) + `tests/api/v1/test_discovery_api.py` (endpoint shape, auth).

## Prerequisites

- P7 complete (`p7-session8-polish-complete`). Not a code dependency — P8a §1 is additive on P2's Alpaca client plumbing.
- `alpaca-py` 0.43.4 (already installed) exposes `ScreenerClient.get_most_actives` / `get_market_movers` and the `MostActivesRequest` / `MarketMoversRequest` request models — confirmed at draft time.
- `app.brokers.alpaca.credentials.load_credentials()` available (used by `quotes.py` / `bar_cache.py`).

## Decisions settled for §1 (owner, 2026-06-07 — AskUserQuestion)

- **Feeds (Direction Q-scope): most-actives + market-movers.** `get_most_actives` + `get_market_movers` (gainers + losers). No news feed — P8 Decision 1 forbids news-*based* scanner criteria; news would only ever be a seed list, so it's omitted here.
- **Caching (Direction Q1): in-memory TTL ~5 min, mirroring `quotes.py`.** No table, no migration; resets on restart (fine — the data re-fetches cheaply).
- **Failure (Direction Q2): stale-on-error, else empty + flag.** Serve the last cached payload (even past TTL) on a fetch error with `stale=true`; if there is no cache at all, return an empty feed with `error` set. The Discovery feed never hard-fails the page (no 5xx).

## Detailed work

### §1.1 — `app/market_data/discovery.py`

Mirrors `quotes.py`. Module-level cache keyed by `top`; one combined fetch covers both feeds.

```python
_FEED_CACHE: dict[int, tuple[float, dict[str, Any]]] = {}
_FEED_TTL_SECONDS = 300.0
_lock = asyncio.Lock()
_UNAVAILABLE = "discovery feeds unavailable"  # generic — never surface raw exc / creds

def _fetch_from_alpaca(top: int) -> dict[str, Any]:
    # lazy SDK import (matches quotes.py); sync client wrapped by caller's executor
    from alpaca.data.historical.screener import ScreenerClient
    from alpaca.data.requests import MarketMoversRequest, MostActivesRequest
    from app.brokers.alpaca.credentials import load_credentials
    creds = load_credentials()
    client = ScreenerClient(api_key=creds.api_key, secret_key=creds.api_secret)
    actives = client.get_most_actives(MostActivesRequest(top=top))
    movers = client.get_market_movers(MarketMoversRequest(top=top))
    return {
        "most_actives": [
            {"symbol": a.symbol, "volume": a.volume, "trade_count": a.trade_count}
            for a in actives.most_actives
        ],
        "gainers": [_mover(m) for m in movers.gainers],
        "losers": [_mover(m) for m in movers.losers],
        "last_updated": _iso(getattr(actives, "last_updated", None)),
    }

async def get_discovery_feeds(top: int = 20) -> dict[str, Any]:
    # fresh cache hit → return as-is; expired/miss → fetch under lock;
    # fetch error → serve any prior cache as stale, else empty + error.
    ...
```

- `_mover(m)` → `{symbol, percent_change, change, price}` (floats / str as the SDK gives).
- `last_updated` is Alpaca's feed timestamp (ISO string) when present, else `None`.
- The error string is the fixed `_UNAVAILABLE` constant — we never put `str(exc)` (or anything cred-adjacent) in the response.
- Tests monkeypatch `discovery._fetch_from_alpaca`; the cache/stale logic in `get_discovery_feeds` is what's exercised.

### §1.2 — `app/api/v1/schemas/discovery.py`

```python
class DiscoveryActiveStock(BaseModel):  # symbol, volume, trade_count
class DiscoveryMover(BaseModel):        # symbol, percent_change, change, price
class DiscoveryFeedsResponse(BaseModel):
    most_actives: list[DiscoveryActiveStock]
    gainers: list[DiscoveryMover]
    losers: list[DiscoveryMover]
    last_updated: datetime | None
    stale: bool      # served from cache past TTL because the live fetch failed
    error: str | None
```

### §1.3 — `app/api/v1/discovery.py`

```python
router = APIRouter(prefix="/discovery", tags=["discovery"])

@router.get("/feeds", response_model=DiscoveryFeedsResponse)
async def get_feeds(
    top: int = Query(20, ge=1, le=100),
    _user: CurrentUser = Depends(get_current_user),
) -> DiscoveryFeedsResponse:
    return DiscoveryFeedsResponse(**await get_discovery_feeds(top))
```

Auth-gated (`app.auth.stub.get_current_user`) for consistency with the Opportunities / Discovery page family (logged-in views). Registered after `opportunities.router` in `app/api/v1/__init__.py`. Path: `GET /api/v1/discovery/feeds`.

### §1.4 — Tests

- `tests/market_data/test_discovery.py` — monkeypatch `_fetch_from_alpaca`: (a) first call fetches + shapes the payload; (b) second call within TTL hits cache (fetch called once); (c) on fetch error with a warm cache → `stale=True`, prior data returned; (d) on fetch error cold → empty lists + `error` set, `stale=False`.
- `tests/api/v1/test_discovery_api.py` — `GET /discovery/feeds` returns 200 with the shaped body (service monkeypatched); unauthenticated → 401.

## Manual smoke

Live Alpaca is **blocked locally by Norton SSL** (`data.alpaca.markets`), so the live feed fetch is verified on a non-Norton stack (WSL/CI). Locally, the structural smoke is:

```
# with the dev stack up and an auth token:
curl -s localhost:8000/api/v1/discovery/feeds -H "Authorization: Bearer $TOK" | jq '{stale, error, n_active: (.most_actives|length)}'
# Norton-blocked machine → expect {stale:false, error:"discovery feeds unavailable", n_active:0} (cold cache, fetch failed) — the graceful path, not a 5xx.
```

The load-bearing assertion: the endpoint returns 200 with the documented shape whether or not Alpaca is reachable.

## Walk-away discipline

Routine session, no order-path / risk / audit touch → **≥1 hour** between ready-for-review and merge.

## What this session does NOT do

- **No criteria evaluation / scanner engine** — §2 (`app/services/scanner.py`).
- **No `scanner_definitions` / `scanner_runs` tables, no migration** — §2/§4.
- **No scheduled scanning** — §4 (APScheduler).
- **No Discovery view UI** — §3 (this session has no frontend).
- **No news feed** — out of scope per Decision 1.
- **No Opportunities-view integration** — §4.
- **No order-path / risk-engine / audit-log change, no new CI invariant** — P8 is additive (Direction: *"None of these additions touch the order path or the risk engine"*).
- **No per-fetch audit logging** — a feed read is not a "consequential action"; scans (§2/§4) are what get audited.

## Notes & gotchas

1. **Don't surface `str(exc)`** — the error field is the fixed `_UNAVAILABLE` constant. The raw exception from the Alpaca SDK / credential layer can carry internal detail; keep it out of the API response.
2. **Cache key is `top`** — different `top` values are distinct cache entries. The endpoint clamps `top` to 1–100 so the cache can't be blown up with arbitrary keys.
3. **`stale` vs `error` semantics** — `stale=True` means "this is older cached data, the live refresh just failed"; a cold failure is `stale=False` + empty + `error`. The UI shows a "showing cached results" hint on `stale`, an "unavailable" hint on cold `error`.
4. **Mirror `quotes.py`, don't reinvent** — same lock/double-check/executor shape so the rate-limit and event-loop behavior is identical to the existing fetch path.
5. **`MarketMoversRequest(market_type="stocks")` default** — the SDK defaults to stocks; P8 is US-equities-only (Direction out-of-scope: no non-equity), so we don't pass crypto.
