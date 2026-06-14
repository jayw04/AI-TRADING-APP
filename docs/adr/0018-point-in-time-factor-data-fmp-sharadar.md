# ADR 0018 — Point-in-time factor data via FMP and Nasdaq Data Link (Sharadar)

| Field | Value |
|---|---|
| Date | 2026-06-13 |
| Status | Accepted (2026-06-13, owner — credential-storage decision §5 confirmed: vendor keys as `Settings` env-aliases) |
| Phase | P9 (point-in-time data backbone + multi-factor equity model) |
| Supersedes | — |
| Related | 0002 (single OrderRouter — these are read-only data, never the order path), 0003 (Fernet credential encryption — the credential-storage question below), 0014 (backtests as primary eval ground truth — survivorship-free PIT data is what makes those backtests honest), 0017 (OS trust store for outbound TLS — the new vendors ride that path) |

## Context

The platform's two sanctioned external dependencies are Alpaca (execution +
market data) and Anthropic (LLM assistance). Adding a new external dependency
requires an ADR (CLAUDE.md, "Local-first, with explicit external dependencies").

P9 introduces a stock-level **multi-factor equity model**. A factor model is only
as honest as its data: it must be **survivorship-free** (include delisted names,
or it systematically overstates returns) and **point-in-time / PIT** (join each
date to the fundamentals and universe membership that were *knowable on that
date*, or it leaks look-ahead bias). The current data layer cannot support this:

- `app/market_data/` is **Alpaca-only** (`_alpaca_fetch_bars`, `_fetch_from_alpaca`
  are hardcoded; there is no provider abstraction).
- Alpaca's free IEX feed is **not survivorship-free**, carries **no fundamentals**,
  **no point-in-time universe**, and thin/short history (the recurring "thin IEX
  prints" caveat).

The owner has two data subscriptions whose keys are already in `.env`
(`FMP_API_KEY`, `NASDAQ_DATA_LINK_API_KEY`):

- **Nasdaq Data Link → Sharadar (FULL):** `SEP` survivorship-free adjusted prices
  (1998+, incl. delisted), `TICKERS` (62k-name universe with first/last price
  dates, i.e. an as-of universe), `ACTIONS` (splits/divs/delistings), `SF3` (13F
  institutional holdings, full). Sample-only (do not rely on): `SF1` fundamentals,
  `DAILY` marketcap/PE/PB, `METRICS`/`SFP`.
- **FMP:** fundamentals (income/balance/cash-flow/ratios, ~5y Starter depth),
  earnings surprises, macro/treasury/economic series.

Combined, these cover the inputs a stock-level multi-factor model needs —
survivorship-free prices (Sharadar) + fundamentals (FMP) + institutional flow
(SF3) + earnings surprises (FMP) + macro (FMP). The remaining genuine gaps
(news/social sentiment, options flow, intraday/tick) are explicitly **out of
scope** for P9.

The question: should the platform adopt these two vendors, and on what terms?

## Decision

1. **Adopt FMP and Nasdaq Data Link (Sharadar) as two new explicit external data
   dependencies.** They are **read-only reference/market data only**. They never
   touch the order path, the risk engine, or broker execution — those stay
   Alpaca-only, so ADR 0002 (single OrderRouter) is unaffected.

2. **Introduce a data-provider abstraction** in `app/market_data/`. Alpaca, FMP,
   and Sharadar become pluggable *data sources* behind a small typed interface;
   existing Alpaca behavior is refactored to sit behind it without changing the
   bar-cache contract. Execution/quotes for live trading remain Alpaca.

3. **Point-in-time discipline is mandatory for the factor layer.** Vendor data is
   ingested into a **local PIT store** (the price/universe spine: Sharadar `SEP` /
   `TICKERS` / `ACTIONS` / `SF3`; the fundamental/macro layer: FMP). Factor
   computation and factor backtests use **as-of joins** against the universe and
   fundamentals that were knowable on each date — no survivorship, no look-ahead.
   This is what makes ADR-0014 backtests trustworthy as ground truth.

4. **Local-first is preserved.** Vendor responses are cached/persisted locally
   (parquet/SQLite, the same posture as the bar cache). Outbound calls verify TLS
   through the OS trust store (ADR 0017, already default-on), so they work under
   Norton inspection without a toggle.

5. **Credential storage:** the two vendor keys are **app-wide vendor keys, not
   per-user broker secrets**, so they are read as pydantic `Settings` fields with
   env aliases (`FMP_API_KEY`, `NASDAQ_DATA_LINK_API_KEY`) — the same mechanism
   `alpaca_paper_api_key` already uses, which does not trip
   `check_no_env_credentials.sh` (that invariant guards a fixed list of
   broker/Anthropic/auth secret *names*, which these are deliberately not added
   to). They are **not** placed in the per-user encrypted `CredentialStore`
   (ADR 0003) because they are not per-user trading secrets. See re-evaluation
   triggers for when that should change.

6. **Licensing posture:** Sharadar and FMP data are licensed for the operator's
   own use. The platform may compute and surface **derived** factors/signals, but
   must **not redistribute raw vendor datasets** (e.g. expose raw Sharadar tables
   over the public API or the read-only MCP) without checking the vendor license.

## Rationale

- **Why not stay Alpaca-only.** A factor backtest on a non-survivorship-free,
  non-PIT universe is biased upward by construction (dead companies vanish;
  today's fundamentals get applied to past dates). Shipping such a backtest would
  violate the spirit of ADR 0014 — it would *look* like ground truth while being
  systematically misleading. The whole value of the factor model rests on honest
  data, which Alpaca cannot provide.

- **Why two vendors, not one.** They are complementary, not redundant. Sharadar
  is the **deep, survivorship-free price + universe + 13F spine** (back to 1998);
  FMP is the **fundamental + macro + earnings layer**. The known depth split —
  Sharadar prices to 1998, FMP fundamentals ~5y on the Starter tier — is designed
  around: deep-history price/return factors price from Sharadar; fundamental
  factors accept the ~5y FMP window (or an FMP upgrade later extends it).

- **Why read-only / off the order path.** Keeping the new vendors strictly in the
  data/analysis layer preserves every order-path invariant (single OrderRouter,
  no-LLM-in-order-path, non-bypassable risk gates). Factor signals feed *strategy
  logic, discovery, and backtests*; any resulting order still flows through
  `OrderRouter.submit` and the activation/cooldown gates unchanged.

- **Why env-alias Settings over the encrypted CredentialStore (for now).** The
  CredentialStore exists for **per-user** secrets whose compromise loses a user's
  money or account (broker keys, Anthropic key). The vendor data keys are a single
  operator-level subscription, read at process start like other config. Routing
  them through the per-user encrypted store would add machinery without matching
  the threat model, and would diverge from the existing `alpaca_paper_api_key`
  precedent. The honest trade-off: this choice is right for the **local-first,
  single-operator** deployment the platform targets today, and is explicitly
  flagged to revisit if that changes.

## Implementation notes

- **Settings** (`app/config.py`): add
  `fmp_api_key: str = Field(default="", alias="FMP_API_KEY")` and
  `nasdaq_data_link_api_key: str = Field(default="", alias="NASDAQ_DATA_LINK_API_KEY")`.
  Empty default = the corresponding provider is disabled (degrade gracefully,
  mirroring how an absent Alpaca key degrades the bar cache).
- **Provider layer** (`app/market_data/providers/`): a typed source interface
  (e.g. `prices`, `actions`, `universe_asof`, `fundamentals_asof`,
  `institutional_holdings`, `macro_series`) with `alpaca`, `sharadar`, `fmp`
  implementations. The existing `_alpaca_fetch_bars` path is refactored to sit
  behind it; the `BarCache.get_bars` contract is preserved.
- **PIT store**: local persistence for the price/universe/13F spine and the
  fundamental/macro layer, in a local **DuckDB** store (resolved in the P9
  Direction doc, 2026-06-13 — columnar engine chosen for cross-sectional factor
  scans; local-first, zero server). v1 ingests the Sharadar price/universe spine
  (`SEP`/`TICKERS`/`ACTIONS`) scoped to the S&P 500; the FMP fundamental/macro
  layer and SF3 are added in later sessions.
- **TLS**: provider HTTP clients inherit the ADR-0017 OS-trust-store path; no
  per-client cert handling.
- **CI invariants**: the existing `check_no_env_credentials.sh` NAMES list is **not**
  extended (these are intentionally not per-user encrypted credentials). If a
  future change reads these names anywhere they could leak (logs, audit, API
  responses), add redaction — `structlog` credential redaction already exists.
- **Audit**: connection-layer use is audited consistently with the other external
  dependencies; raw vendor payloads are not written to the audit log.

## Consequences

- **Positive**: honest, survivorship-free, point-in-time factor backtests; a
  genuine fundamental + institutional + macro signal surface for strategies and
  discovery; native fundamental screening (closes the reviewer-flagged
  "stock selection / institutional ownership" gaps); the data layer gains a
  provider abstraction it has lacked since P2.
- **Negative**: two more external dependencies to monitor (rate limits, vendor
  outages, the FMP ~5y depth caveat, Sharadar refresh cadence); a PIT ingestion +
  storage subsystem to build and maintain; a data-licensing constraint to respect
  (no raw-dataset redistribution); more surface for "the data is stale/wrong"
  failure modes that a factor model is sensitive to.
- **Neutral**: the order path, risk engine, and live execution are unchanged —
  this is purely additive on the read/analysis side.

## Alternatives considered (not chosen)

- **Alpaca-only, accept the bias.** Rejected: produces dishonest factor backtests;
  defeats the purpose and contradicts ADR 0014. Reconsider never — bias-free data
  is the whole point.
- **One vendor (FMP-only or Sharadar-only).** Rejected: FMP lacks deep
  survivorship-free price history + a clean as-of universe; Sharadar's
  *full-access* fundamentals (`SF1`) are sample-only on this subscription. Each
  alone leaves a load-bearing gap. Reconsider if one vendor's coverage expands to
  subsume the other.
- **Store vendor keys in the encrypted per-user CredentialStore (ADR 0003).**
  Rejected for v1: wrong threat model (operator-level, not per-user) and diverges
  from the `alpaca_paper_api_key` precedent. Reconsider on multi-user/hosted
  deployment (see triggers).
- **Build the factor store as a hosted/columnar warehouse.** Rejected for v1:
  violates local-first. A local parquet/SQLite/DuckDB store matches the bar-cache
  posture. Reconsider only if dataset size outgrows local query performance.

## Re-evaluation triggers

- **Multi-user or hosted deployment.** Decision 5 (env-alias key storage) assumes a
  single-operator, local-first install. If the platform becomes multi-user or
  hosted, move the vendor keys to an encrypted per-deployment secret store and
  re-audit redaction.
- **Factor backtests do not beat baselines** (per ADR 0014, ≥5 backtested
  evaluations): if the multi-factor model fails to clear its baseline on
  survivorship-free holdouts, the data investment and this dependency are
  reconsidered rather than treated as sunk.
- **Coverage gaps become load-bearing.** If news/social sentiment, options flow,
  or intraday/tick move from "out of scope" to "required," that is a new
  dependency decision (a new ADR), not a quiet expansion of this one.
- **Vendor terms change** (depth, price, redistribution rights, rate limits) in a
  way that breaks the depth-split design or the licensing posture.
