# ADR 0022 — Market-regime data (breadth & VIX) for the exposure overlay

| Field | Value |
|---|---|
| Date | 2026-06-19 |
| Status | Accepted (2026-06-19, owner — after a review pass folding signal classification, VIX-percentile representation, validity/freshness, breadth-universe scope, provenance, and a research promotion gate) |
| Phase | P10 §5 |
| Supersedes | — |
| Related | 0018 (PIT factor data via FMP/Sharadar — the existing vendors this rides), 0020 (daily gross-exposure overlay — the consumer of these signals), 0017 (OS-trust-store TLS — outbound vendor calls ride it), 0014 (backtests as eval ground truth — any regime signal must beat baselines), 0002 (single OrderRouter — these are read-only data, off the order path) |

## Context

P10 §1/§2 scale the book's gross exposure off **realized** EWMA volatility of the
market proxy. The owner's review (items 1/4/5) flagged two additional regime inputs
worth considering for the overlay: **market breadth** (how broadly the market is
participating — e.g. the fraction of names above their 200-day MA) and the **VIX**
(forward-looking *implied* volatility, which realized vol cannot anticipate).

Both are *new data* relative to what the overlay uses today, and "adding a new
external dependency requires an ADR" (CLAUDE.md; the rule ADR 0018 was written
under). The question is narrowly a **data-dependency** one: where do breadth and VIX
come from, under what point-in-time discipline, and **do they require a genuinely new
vendor** — not how they feed the overlay's gross target (that signal design is a
follow-on §5 session, governed by ADR 0020).

Relevant facts about what we already have:

- **Breadth is derivable from data already ingested.** The Sharadar `SEP` + `TICKERS`
  spine (ADR 0018) holds survivorship-free daily closes for the full PIT liquidity
  universe. Breadth (% of the as-of universe above its 200-day MA, advance/decline,
  new-highs/lows) is a *computation over prices we already store* — no vendor.
- **VIX is a genuinely external series** (a CBOE index, not an equity; absent from
  `SEP`). But **FMP is already an accepted vendor** (ADR 0018), and our FMP client is
  a thin REST wrapper over the `/stable` API with a generic `fetch(endpoint, …)` — so
  an index series like `^VIX` is reachable through the *existing* dependency, not a
  new one, subject to plan coverage.

## Decision

1. **Adopt NO genuinely new external vendor for §5.** Market-regime data is sourced
   from what the platform already has: breadth is **derived internally**, and VIX (if
   used) **rides the already-accepted FMP dependency** (ADR 0018).
2. **Breadth — derived internally** from the Sharadar `SEP`/`TICKERS` factor store as
   a point-in-time series. It is a computed signal, not an ingested dataset; no new
   dependency. **Breadth is computed over the *portfolio-construction universe*** (the
   same PIT liquidity top-N the book selects from), **not the entire US market** — so
   the regime signal and the book see the same names, keeping research consistent.
3. **VIX — optional, secondary, sourced from FMP** via the existing `/stable` client,
   ingested into the local PIT store as an as-of-by-date daily series. VIX is an
   *enhancement* (forward-looking implied vol), not load-bearing — breadth + the
   §1/§2 realized vol are the floor. If FMP's plan does not carry `^VIX` history, the
   fallback order is: (a) a VIX **ETF proxy** (e.g. `VIXY`) via Alpaca (already
   accepted) — explicitly a roll-decaying proxy, second choice; (b) **defer VIX**
   entirely and ship breadth-only. A new dedicated vendor is **not** adopted without a
   new ADR.
4. **PIT + fail-open discipline.** Both series are joined as-of-by-date (no
   look-ahead) and are **read-only, off the order path** (ADR 0018/0002). When a
   series is missing/stale, the overlay **fails open to gross = 1.0** (ADR 0020's
   boundary) — a regime-data gap must never force a liquidation.
5. **VIX is consumed as a rolling percentile, never raw.** A signal feeding the overlay
   uses VIX's **trailing 252-day percentile**, not its absolute level — a VIX of 20
   means very different things across regimes (2017 vs 2020 vs 2022), and the percentile
   is comparable across them. (Breadth and realized vol are likewise consumed as
   relative/normalized signals.) The raw level is stored; the *representation* fed to
   the overlay is the percentile. The exact mapping into `desired_gross` is the
   follow-on §5 implementation (ADR 0020).
6. **Signal validity & freshness.** Each regime signal is **synchronized to the same
   as-of date** (the overlay never mixes today's breadth with yesterday's VIX) and is
   validated before use — finite, within an expected range, monotonic timestamp, not
   stale beyond a tolerance, and computed over a sufficient lookback. **An invalid or
   stale signal fails open** (contributes no de-risking), exactly as a missing series
   does (decision 4).
7. **Same promotion discipline as strategies (ADR 0014).** No regime signal governs a
   real (paper or live) book until it has cleared **survivorship-free + IS/OOS +
   walk-forward backtest validation, then paper observation** — the same gate
   strategies pass. A signal that doesn't beat the §1/§2 baseline is dropped, not
   shipped.

### Signal taxonomy

The overlay's regime inputs, classified so future additions slot into a known class:

| Signal | Class | Source | Confidence | Update |
|---|---|---|---|---|
| EWMA realized vol (§1/§2) | Reactive (trailing) | derived (proxy returns) | High | End of day |
| Breadth | Internal market participation | **derived** (Sharadar SEP, book's universe) | High (fully under our control) | End of day |
| VIX (percentile) | Forward-looking implied vol | FMP (`^VIX`), optional | Medium (vendor + term-structure dependent) | End of day |

All three are end-of-day signals consumed on the same as-of date (decision 6). Data flow:

```
   Sharadar SEP ──▶ Breadth ─┐
   proxy returns ─▶ EWMA vol ─┼─▶ (market regime) ──▶ Overlay (desired_gross)
   FMP ^VIX ──────▶ VIX %ile ─┘            (read-only; informs, never commands)
```

## Rationale

- **Why derive breadth instead of buying it.** It is computable from prices already
  ingested, so a breadth feed would be pure added surface for zero new information —
  strictly dominated. Deriving it also keeps it PIT-consistent with the universe the
  book actually trades.
- **Why VIX via FMP, not a new vendor.** ADR 0018 already took on FMP; a daily index
  close is as-of-clean and reachable through the generic `/stable` fetch. Adding CBOE
  / stooq / Tiingo for a single series would expand the external surface (another key,
  rate limit, outage mode, license) against the platform's "minimize explicit external
  dependencies" posture — unjustified when an accepted vendor likely covers it.
- **Why VIX is optional/secondary.** §1/§2 already act on realized EWMA vol; VIX adds
  genuine *forward-looking* information, but breadth + realized vol already give a
  workable regime signal. Treating VIX as additive means a plan-coverage gap degrades
  to "breadth-only," not "blocked."
- **Why the ETF proxy is only a fallback.** `VIXY`/`UVXY` carry roll/decay, so they
  are biased relative to spot VIX; acceptable as a stopgap, wrong as the primary.
- **Why this is a data-dependency ADR even though no new vendor is added.** The
  decision *is* "do not add a vendor — derive breadth, ride FMP for VIX, under PIT +
  fail-open discipline." Recording that reasoning is the point: it stops a future
  session from quietly bolting on a regime-data vendor.

## Implementation notes

- **Breadth:** a derived series in the factor layer (`app/factor_data/`), computed
  as-of over the PIT universe (e.g. fraction above the 200-day MA), cached locally
  like other factor outputs. No new Settings/credentials.
- **VIX (if adopted):** reuse the FMP `/stable` client (ADR 0018) to fetch the `^VIX`
  daily history; persist to the local PIT/DuckDB store with as-of-by-date keys;
  ingest path mirrors the existing FMP fundamentals ingest (idempotent upsert, keyed
  by date). No new vendor key — `FMP_API_KEY` already exists.
- **Consumer (separate session, governed by ADR 0020):** the overlay's
  `desired_gross` may take breadth/VIX-percentile inputs in addition to realized vol;
  that signal design + backtest is the follow-on §5 implementation, not this ADR.
- **Provenance (mirrors the Research Engine, ADR 0019):** each derived breadth value
  records the **universe version, lookback, and computation version** that produced it,
  so a regime reading is reproducible and a definition change is auditable.
- **Operational metrics (per ADR 0021 observability):** the regime-data path exports
  last-successful-update, stale-days, invalid-signal count, and fail-open count — the
  same operational surface as the §2 overlay metrics.
- **CI / credentials:** no change — no new env-credential names, no order-path
  imports; the read-only/off-order-path property is structural.
- **Licensing:** as ADR 0018 §6 — surface derived breadth/VIX signals, do not
  redistribute raw vendor series over the public API or the read-only MCP.

## Consequences

- **Positive.** A richer regime signal (breadth, optional VIX) with **zero new
  vendor**; PIT-clean and fail-open; breadth is free and always available; VIX
  degrades gracefully to a proxy or to breadth-only.
- **Negative.** A derived breadth series to define, validate, and maintain (a wrong
  breadth definition silently mis-scales the book); VIX-via-FMP depends on plan
  coverage that must be verified, and a proxy fallback would inject roll-decay bias if
  used; more inputs to the overlay means more to backtest before enabling.
- **Neutral.** The order path, risk engine, and live execution are unchanged — purely
  additive on the read/analysis side (consistent with ADR 0018).

## Alternatives considered (not chosen)

- **A dedicated VIX/breadth vendor (CBOE, stooq, Tiingo).** Rejected: new external
  surface (key, rate limit, outage, license) for series the existing data + FMP
  already cover. Reconsider only if FMP lacks `^VIX` *and* a proxy proves inadequate
  *and* VIX shows backtested value — then it is a new vendor ADR.
- **VIX ETF proxy (`VIXY`) as the primary VIX source.** Rejected as primary: roll
  decay biases it vs spot VIX. Retained only as a fallback if FMP coverage is absent.
- **Buy a market-breadth feed.** Rejected: breadth is derivable from prices we already
  store; a feed adds surface for no new information.
- **Skip VIX entirely (breadth-only).** Not rejected — it is the explicit floor of
  this decision; VIX is kept optional so a coverage gap lands here safely.
- **A composite "market-regime state" (NORMAL / RISK_OFF / STRESS) the overlay consumes
  instead of individual signals.** Deferred, not adopted: it would move signal *fusion*
  into the overlay's consumption model (ADR 0020's territory) and is a larger design
  better taken once ≥2 signals are live and validated. Noted as a future direction
  (a "market-state engine" feeding the overlay a single state) — see triggers.

## Re-evaluation triggers

- **FMP plan confirmed to lack `^VIX` history** → choose proxy-vs-defer-vs-new-vendor
  and record the outcome here (a new vendor is a new ADR).
- **No backtested benefit** (ADR 0014): if breadth/VIX inputs don't improve the
  overlay on survivorship-free holdouts, drop the regime data rather than expand it.
- **Intraday regime signals become required** → a new dependency decision (new ADR),
  not a quiet expansion.
- **Multi-user / hosted deployment** → revisit vendor-key storage exactly as ADR 0018
  flags (env-alias Settings → encrypted per-deployment store).
- **≥2 regime signals live and validated** → consider promoting signal fusion into a
  composite **market-state engine** (NORMAL / RISK_OFF / STRESS) that the overlay
  consumes as one state, so the overlay no longer knows about individual signals (a
  Phase-4-scale evolution, governed by ADR 0020 — a new ADR, not a quiet expansion).
