# ADR 0024 — Realized-outcome feed for the SCAN-001 premarket Discovery gate

| Field | Value |
|---|---|
| Date | 2026-06-23 |
| Status | Draft |
| Phase | SCAN-001 premarket-data gate (increment C back-fill → D verdict) |
| Supersedes | — |
| Related | 0014 (backtests as eval ground truth), 0017 (OS trust store for outbound TLS), 0022 (market-regime data), 0023 (Sharadar SF1 PIT fundamentals) |

## Context

The SCAN-001 premarket-data gate (plan `TradingWorkbench_SCAN001_PremarketDataGate_Plan_v0.1.md`) is the
L3→L4 prerequisite: it replays the frozen Candidate Engine on **real** 09:25 premarket data and
**forward-replicates** the selection edge before any live use. Increments A (adapter), B (live scan), and C's
persist-half (the forward-evidence accumulator) are built and merged/open (#238, #239): each trading day we now
persist the premarket candidate set to a dated record with `outcome_status = "pending"`.

To produce the gate's verdict (increment D), each record must be **back-filled** with every candidate's
**realized intraday outcome** — high-of-day, low-of-day, and close — from which the gate computes the same
metrics the v0.2–v0.5 research used: expansion ratio `E = (HOD−LOD)/ATR` and capturable move `CM`. The blocker
(gate plan §0b): the premarket gappers are small/mid-cap Yahoo gainers **frequently absent from our DuckDB
store** (which holds the liquid top-pool), and we have **no realized-bar source for them**. We must decide where
the gappers' realized outcomes come from. Per the repository invariant *"adding a new external dependency
requires an ADR,"* this decision is recorded here before any code.

## Decision

1. **Source the gappers' realized intraday outcomes from Alpaca market data — the existing, audited
   market-data dependency — not a new provider.** The gate's back-fill fetches daily OHLC bars (HOD/LOD/close)
   for each persisted candidate's symbol *after the close*, through the same Alpaca market-data path the platform
   already uses; no new vendor, SDK, or credential is introduced.
2. **The back-fill is a read-only, advisory EOD job.** It fills the `outcomes` field of the gate evidence
   records (ADR-scoped to `app/services/premarket_evidence.py`) and computes `E`/`CM` per candidate plus the
   eligible-field baseline. It **never** touches the OrderRouter, the risk engine, or any strategy — the
   candidate set remains *evidence, not a signal* (SCAN-001 §0a, ADR 0014).
3. **Coverage is recorded, not assumed.** Symbols Alpaca does not cover are marked `outcome_status =
   "uncovered"` (not silently dropped), so the gate's verdict (D) reports the realized coverage rate as a
   first-class honest-scope number.

## Rationale

The realized-outcome source must be (a) authoritative for small/mid-caps, (b) compatible with the order-path and
external-dependency invariants, and (c) cheap to operate forward, one EOD pull per scan day.

- **Alpaca is already a sanctioned, audited dependency** (execution + market data). Reusing it for realized bars
  adds **no new external dependency** — it is a new *use* of an existing one, which is materially weaker than the
  new-vendor decision in ADR 0022/0023 and keeps the platform's "two external dependencies" story intact
  (Alpaca, Anthropic). Alpaca's market data covers essentially all US-listed equities, including the small/mid-
  caps the store lacks — directly solving the §0b coverage gap.
- **EOD daily bars are sufficient.** The gate's metrics (`E`, `CM`) need only HOD/LOD/close — one daily bar per
  symbol per day. No intraday/tick subscription, no streaming, no new infrastructure.
- **Norton is already handled.** `data.alpaca.markets` is blocked by Norton's TLS MITM on the developer's
  machine, but ADR 0017 (OS-trust-store via `truststore`) fixed outbound TLS verification against exactly this;
  and the forward back-fill can run wherever the daily job runs (CI/WSL/cloud), so Norton is not load-bearing.
- **Authoritativeness over convenience.** Alpaca's bars are exchange-sourced and consistent with the data the
  rest of the platform trusts; deriving outcomes from the sibling scanner's free web sources would make the
  gate's *ground truth* depend on an unaudited scrape — unacceptable for a promotion gate (ADR 0014's spirit:
  the eval ground truth must be trustworthy).

## Implementation notes

- **New module (back-fill):** `app/services/premarket_outcomes.py` (or a function in `premarket_evidence.py`) —
  `backfill_outcomes(record, bars_by_symbol)` is **pure** (record + realized bars → record with `outcomes`
  filled, `E`/`CM` per candidate + eligible baseline); a thin Alpaca fetch wrapper supplies `bars_by_symbol`.
  Mirrors the A/B pure-core + thin-I/O split.
- **Outcome metrics** reuse `candidate_engine.intraday_range_pct` / `expansion_ratio` / `capturable_move`
  verbatim — identical math to the validated research.
- **Record schema:** `outcome_status` gains `"filled"` and `"uncovered"` alongside `"pending"`; `outcomes`
  becomes `{symbol: {E, CM, hod, lod, close}}` plus a baseline block. `RECORD_SCHEMA` stays `…/v1` (additive).
- **No order-path code, no LLM.** The Alpaca call is read-only market data; it imports no `anthropic` and routes
  no orders, so the no-LLM-in-order-path and single-OrderRouter invariants are untouched.
- **Activation:** the EOD back-fill job (~16:30 ET) registers on a backend rebuild, alongside the deferred ~09:25
  scan job — both part of the gate's activation step.

## Consequences

- **Positive:** unblocks the gate's forward verdict (D) with authoritative, invariant-clean data; no new vendor;
  coverage is measured, not assumed; reuses validated outcome math.
- **Negative:** the gate's evidence is bounded by **Alpaca's coverage and history** of the gappers (some thin
  names or halted tickers will be `uncovered`, biasing the sample toward Alpaca-covered gappers — reported, not
  hidden); a daily Alpaca read adds a small operational surface (rate limits, transient errors → the job must be
  fail-soft and retry, never block). The back-fill depends on Alpaca market-data entitlement remaining available.
- **Neutral:** ties the gate to Alpaca rather than the sibling scanner — appropriate, since Alpaca is already the
  platform's market-data spine.

## Alternatives considered (not chosen)

- **Store-covered gappers only (gate-plan Option i).** Use existing DuckDB bars; no new data at all. *Rejected:*
  restricts evidence to the liquid subset of gappers — a biased sample that defeats the point of testing the
  *gappers* population. Reconsider only if Alpaca coverage proves as biased.
- **Sibling-scanner outcome file (extend the #221 file-drop).** Have `claude-trading-view` write a
  `premarket_outcomes_<date>.json` we read read-only. *Rejected:* makes the gate's **ground truth** an unaudited
  web scrape, and couples the verdict to the sibling project's correctness. Reconsider if Alpaca coverage of
  gappers is materially worse than the scraper's.
- **Yahoo / `yfinance` EOD.** Free, broad small-cap coverage. *Rejected:* a genuinely **new external
  dependency** (the thing this ADR exists to avoid), less authoritative, and itself Norton-exposed. Reconsider
  only if Alpaca coverage is insufficient and an audited alternative is needed.

## Re-evaluation triggers

- **Coverage:** if the realized-coverage rate over the first forward window is low (a large fraction of gappers
  come back `uncovered`), revisit — Alpaca may not cover this population well enough, reopening the
  sibling-file / alternative-vendor alternatives.
- **Operational:** if the EOD Alpaca back-fill proves unreliable (sustained rate-limit/availability failures)
  such that records cannot be filled within the forward window.
- **Entitlement:** if Alpaca market-data terms change such that historical small-cap bars are no longer
  available under the existing plan.
- **Scope:** if the gate later needs intraday *path* (not just HOD/LOD/close) — e.g. to test entry/exit timing —
  the daily-bar decision here no longer suffices and a richer feed must be reconsidered.
