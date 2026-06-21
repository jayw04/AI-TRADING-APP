# ADR 0023 — Sharadar SF1 full fundamentals as the primary point-in-time fundamental source

| Field | Value |
|---|---|
| Date | 2026-06-21 |
| Status | **Draft** (owner-confirmed direction in `comments.md` 2026-06-21; acceptance gated on procurement — see Implementation notes) |
| Phase | P13 → **P14 (Factor Lab)** — the deep fundamental spine the multi-factor research program needs |
| Supersedes | — |
| Related | **0018** (point-in-time factor data via FMP + Sharadar — this ADR resolves its "SF1 sample-only" limitation and revises its FMP-as-fundamental-spine depth split), 0014 (backtests = primary eval ground-truth — SF1 is what makes the multi-factor verdict *decisive*), 0019 (Research Engine — read-only/advisory), 0017 (OS trust store — the vendor call rides that path), 0002 (single OrderRouter — SF1 is read-only data, never the order path) |

## Context

ADR 0018 adopted Nasdaq Data Link (Sharadar) and FMP as two read-only point-in-time data
dependencies. It made a deliberate **depth split**: Sharadar supplies the deep, survivorship-free
**price / universe** spine (`SEP` / `TICKERS` / `ACTIONS`, 1998+), while **FMP** supplies the
**fundamentals** (~5-year Starter depth). ADR 0018 explicitly listed Sharadar's `SF1` fundamentals as
**"sample-only (do not rely on)"** on the current subscription.

That depth split has now become the binding constraint on the research program. P12 §3 (multi-factor)
found that Value and Quality are genuine, near-uncorrelated diversifiers of Momentum and that a
composite book *looks* promising (Sharpe 1.23 vs 1.00, drawdown roughly halved) — **but the result was
statistically Inconclusive**: the confidence interval overlapped momentum because the only usable
fundamentals were FMP's **~5 years, ~197 mega-cap names, not survivorship-free**. That data cannot
decisively answer whether Momentum + Value + Quality + Profitability + Low-Vol actually outperform.

The owner's decision (P13 Direction v0.2 §8.1, `comments.md`): this is the **single highest-priority
strategic investment** — not because the *platform* needs it (the platform is proven end-to-end), but
because the **research roadmap** needs it. The deferred multi-factor verdict, and the entire Factor
Lab (P14), are blocked on institutional-grade fundamentals: **20+ years, ~3000+ stocks,
survivorship-free, point-in-time.**

The question: should the platform acquire Sharadar's **full SF1** fundamentals product and make it the
primary point-in-time fundamental source, and on what terms?

## Decision

1. **Acquire the full Sharadar `SF1` (Core US Fundamentals) datatable** via the existing Nasdaq Data
   Link subscription, upgrading from the current sample-only access. SF1 becomes the platform's
   **primary point-in-time fundamental source** for factor research and the Factor Lab.

2. **SF1 is read-only reference data**, ingested into the existing local **DuckDB** PIT store
   (`apps/backend/data/factor_data_full.duckdb`) alongside the Sharadar price/universe spine. It never
   touches the order path, the risk engine, or broker execution (ADR 0002 unaffected).

3. **Point-in-time discipline is mandatory and unchanged (ADR 0018 §3).** SF1 rows carry both a
   reporting period and a `datekey` (the date the figure became known); factor computation joins each
   rebalance date **as-of `datekey`** (using SF1's point-in-time dimensions — `ARQ`/`ART`/`MRQ` as
   appropriate), so no fundamental is used before it was publicly available. Survivorship-free coverage
   (incl. delisted issuers) is preserved by joining against the existing as-of universe.

4. **FMP is retained as a complementary / fallback fundamental source, not the primary one.** This
   **revises ADR 0018's depth split**: SF1 becomes the deep PIT fundamental spine; FMP remains for
   coverage SF1 lacks (e.g. certain macro/treasury/earnings-surprise series) and as a cross-check. The
   price/universe spine stays exactly as ADR 0018 set it.

5. **Credential storage and licensing follow ADR 0018 unchanged.** SF1 rides the existing
   `NASDAQ_DATA_LINK_API_KEY` env-alias `Settings` field (no new credential, no `CredentialStore`
   change). Licensing posture is identical: the platform may compute and surface **derived**
   factors/signals but must **not redistribute raw SF1 tables** over the public API or the read-only
   MCP.

## Rationale

- **Why SF1 specifically, and why now.** The research program's next decisive question — does a
  multi-factor book beat momentum out-of-sample — is unanswerable on FMP's ~5y / mega-cap / biased
  fundamentals. SF1 is the dataset ADR 0018 already identified as the right one but couldn't use
  (sample-only). It is survivorship-free, point-in-time, ~20+ years, ~thousands of names — exactly the
  shape ADR 0014 demands for an honest verdict. Acquiring it now (long procurement lead time) lets the
  Factor Lab build in parallel with product work (P13).

- **Why make it primary over FMP.** Two PIT fundamental sources with different depth/coverage invite
  silent inconsistency (which source backed a given factor on a given date?). Designating SF1 the
  primary spine — with FMP explicitly the fallback/complement — keeps the factor provenance
  unambiguous, which matters because every research result must be reproducible and citable (the
  Evidence Engineering thesis). It also directly revises the one ADR-0018 assumption (FMP-as-spine)
  that the data has outgrown.

- **Why read-only / off the order path.** Identical to ADR 0018: fundamentals feed strategy logic,
  discovery, and backtests; any resulting order still flows through `OrderRouter.submit` and the
  activation/cooldown gates unchanged. No order-path invariant is touched.

- **Why this is a new ADR, not an edit to 0018.** ADR 0018's adoption of Sharadar+FMP and its PIT
  discipline stand. But "make full SF1 the primary fundamental source, revising the FMP depth split" is
  a *new, consequential* decision with its own cost and its own re-evaluation triggers — it earns its
  own record rather than a quiet edit to an Accepted ADR (per the ADR conventions).

## Implementation notes

- **Procurement (owner action — gates `Accepted`):** subscribe to the Sharadar **SF1** product on the
  Nasdaq Data Link account that owns `NASDAQ_DATA_LINK_API_KEY`. **Owner-input fields to fill before
  acceptance:** exact product SKU/tier, annual price, and licensed-use terms (personal vs commercial —
  relevant once the platform is sold). Until subscribed, SF1 ingestion returns the sample only.
- **Settings:** no new field — SF1 uses the existing `nasdaq_data_link_api_key` (ADR 0018 §5). Empty
  key ⇒ provider disabled (graceful degrade, mirroring the existing posture).
- **Ingest:** extend the Sharadar ingestion (`scripts/ingest_sharadar.py` / `app/factor_data/`) with an
  `SF1` path → a `sf1_fundamentals` table in `factor_data_full.duckdb`, keyed by `(ticker, dimension,
  datekey)`; respect the daily row-cap/resume pattern already used for `SEP`. Provider abstraction per
  ADR 0018 §2 (`fundamentals_asof`).
- **As-of joins:** factor code reads SF1 via an as-of accessor (join rebalance date → latest
  `datekey ≤ as_of` for the chosen dimension). The composite engine (`app/factor_data/factors/`) gains
  SF1-backed Value / Quality / Profitability / Growth / Low-Vol factors; this is the Factor-Lab work
  (P14), not part of this ADR.
- **No new CI invariant.** `check_no_env_credentials.sh` NAMES list is **not** extended (consistent
  with ADR 0018). Raw SF1 payloads are not written to the audit log.
- **Docs:** update `docs/runbook/factor-data.md` (ingest + as-of usage) when SF1 lands.

## Consequences

- **Positive:** unlocks a *decisive*, survivorship-free, point-in-time multi-factor verdict (resolves
  the P12 §3 Inconclusive); enables the full Value / Quality / Profitability / Growth / Low-Vol factor
  families and the generic Factor Lab; unambiguous factor provenance (one primary fundamental spine);
  every fundamental factor becomes reproducible over ~20 years and thousands of names.
- **Negative:** a **real recurring subscription cost** (the chief trade-off — justified by the research
  roadmap, not the platform); a larger ingestion + storage footprint (SF1 across thousands of names ×
  20+ years × multiple dimensions is sizable in DuckDB); one more vendor product whose refresh cadence,
  restatements, and `datekey` semantics must be handled correctly (fundamental restatements are a
  classic look-ahead trap if `datekey` is mishandled); a tightened licensing constraint to honor once
  the platform is commercial.
- **Neutral:** the order path, risk engine, and live execution are unchanged — purely additive on the
  read/analysis side. FMP stays connected, just demoted from primary fundamental source to
  complement/fallback.

## Alternatives considered (not chosen)

- **Stay on FMP fundamentals (status quo).** Rejected: ~5y, ~197 mega-cap, not survivorship-free —
  structurally cannot deliver a decisive multi-factor verdict; leaves P12 §3 permanently Inconclusive.
  Reconsider only if FMP's tier expands to deep survivorship-free PIT coverage (it does not today).
- **Upgrade FMP to a deeper fundamentals tier instead of buying SF1.** Rejected: FMP's deeper tiers
  still lack Sharadar's survivorship-free, clean point-in-time `datekey` discipline at the same rigor,
  and would not unify with the Sharadar price/universe spine already in the store. Reconsider if FMP
  ships an equivalent PIT survivorship-free product at materially lower cost.
- **Build a free/scraped fundamentals dataset.** Rejected: re-creating survivorship-free, point-in-time
  fundamentals is a multi-year data-engineering project and the exact look-ahead/survivorship trap ADR
  0014 exists to prevent. Not worth the integrity risk.
- **Defer SF1; expand only product (P13).** Rejected as the *primary* path but **partially adopted**:
  the owner's decision is explicit parallelism — product (Track B) proceeds *while* SF1 is acquired, not
  instead of it. Deferring entirely would stall the research roadmap that is the platform's
  differentiator.

## Re-evaluation triggers

- **Procurement falls through** (price, licensing, or terms unacceptable): SF1 acceptance does not
  happen; the multi-factor program stays deferred and this ADR returns to the alternatives above
  (notably an FMP deep-tier re-evaluation).
- **Multi-factor still fails to beat baselines on SF1** (per ADR 0014, ≥5 survivorship-free
  walk-forward evaluations): if Value/Quality/Composite do not clear momentum out-of-sample even on
  decisive data, the *finding* is "momentum is the edge" — record it, keep v1.1, and treat the SF1
  spend as the cost of an honest answer rather than sunk-cost pressure to ship a weak book.
- **Multi-user / hosted deployment:** revisit credential storage exactly as ADR 0018's trigger states
  (env-alias key → encrypted per-deployment secret store) and re-audit raw-data redistribution under
  the commercial license.
- **SF1 terms change** (depth, price, restatement cadence, redistribution rights) in a way that breaks
  the primary-fundamental-source design or the licensing posture.
- **DuckDB query performance degrades** as SF1 grows the store: reconsider storage layout/partitioning
  (still local-first per ADR 0018) before any hosted-warehouse move.
