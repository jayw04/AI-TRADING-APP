# Insider Reference Monitor — Onboarding Spec (v0.1)

**Date:** 2026-07-09 · **Owner:** Jay Wang · **Status:** Approved to build (owner decision 2026-07-09).

| | |
|---|---|
| **Product status** | Reference-only / Context Surface |
| **Research status** | INSIDER-001 **rejected** (beta-not-alpha); INSIDER-002 **not approved** (triage sheet Reserved, gated on the GAPPER-001 verdict) |
| **Order-path status** | **Prohibited** — `rejected_reference_only` invariant (`app/altdata/reference_only.py` + `check_reference_only_invariant.sh`) |

## What this is

A daily insider-activity **context surface** onboarded from the sibling `claude-trading-view`
insider-conviction assistant (`Docs/Strategies/Insider Strategy.md`) — the monitoring workflow,
**not** the trading strategy. Users see *"here are companies with recent insider open-market
buying, with size/role/cluster context and the honest evidence note"* — never *"buy because
insiders bought."*

**Naming (locked):** "Insider Activity Monitor" / "Insider Reference Monitor". Forbidden names:
Insider Signal · Insider Alpha · Insider Buy Recommendation · High Conviction Insider Watch —
and the sibling's "conviction" vocabulary is not carried into the UI.

**Required UI language (verbatim, on the surface itself):**
> Reference Only — INSIDER-001 found no standalone residual alpha.
> Not a validated trading signal. Not used for ranking, sizing, or orders.
(+ a link to the INSIDER-001 evidence package.)

## Architecture (assembly, not new plumbing)

Everything below already exists on main from INSIDER-001 §1 / EAD Phases 0–2; the monitor wires it
into a daily job + a read-only endpoint + a UI card:

1. **Daily ingestion job** (`app/jobs/insider_reference_monitor.py`, scheduled ~18:00 ET weekdays
   + a premarket catch-up ~08:00 ET): `app/altdata/sec/ingest.py` over the monitor universe →
   PIT Event Store (`corporate_events`, `event_type="insider_buy"`, idempotent by accession).
2. **Enrichment at read time** (not stored as scores): Security-Master resolution + Sharadar
   context (below).
3. **Read-only endpoint** `GET /api/v1/insider-reference` (auth'd, display fields only, carries
   `reference_only: true` on every row + the evidence note).
4. **Frontend card** ("Insider Activity Monitor") with the required language block. No buy/sell
   affordances, no links into order tickets, no strategy-attach.

**Enforcement (step 4 of the owner's list):** the endpoint and job live in `app/altdata/` +
`app/jobs/` + `app/api/` only; the existing CI invariant already fails the build if
`insider_buy` (or any rejected-EAD label) is named in the order-path / ranking / selection
modules. Add the monitor's modules to the invariant's *allowed* display-side list, and a test
asserting every API row carries the `reference_only` flag.

## Platform enrichments beyond the sibling (the "we have more data" answer)

The sibling monitors **134 hand-checked names** with EDGAR polling and hand-tuned conviction
filters. The platform can materially upgrade the *context* (all display-side, all allowed under
reference-only):

| Enrichment | Source (platform-only) | What the user sees |
|---|---|---|
| **Full-universe coverage** | DCAP-008 broad small-cap SF1 (9,040 tickers) + Security Master (CAP-024) | insider activity across the whole tradable small/mid-cap space, not 134 names |
| **Materiality context** | Sharadar METRICS/DAILY (marketcap, ADV) | transaction value as % of market cap and % of ADV — "large for this company," not just "$500k" |
| **Cluster detection at scale** | PIT Event Store window queries | ≥2 distinct insiders within N days, across the full universe (the sibling's strongest filter, now universe-wide) |
| **Role weighting** | Form 4 parser (already extracts officer/director/10% owner) | CEO/CFO purchases flagged distinctly from directors |
| **Sector/size context** | Sharadar TICKERS + Security Master | sector tag + size bucket per event, so users read the event in context |
| **Evidence-grounded expectations** | INSIDER-001 matched-control results | the honest note per event class: "events like this averaged +X% vs matched controls over 60d — not statistically distinguishable from zero" |
| **PIT-true freshness** | Event Store `filed_at` acceptance timestamps | "filed 2h ago" vs "transaction 2 days ago, filed today" — the disclosure lag made visible |
| **Open-market purity** | transaction-code filter (P only) already in the parser | option exercises / grants / 10b5-1-style noise excluded, and labelled |

Explicitly **not** built: any composite "score" or ranked ordering that could read as a
recommendation. Sorting is by freshness or filing time only. (A materiality *filter* — e.g. hide
sub-$10k trades — is display hygiene, not ranking.)

## What this is not (locked)

- Not a signal, not a strategy, not a paper book, not INSIDER-002.
- Never feeds ranking, sizing, portfolio construction, discovery candidate lists, or the order
  path — enforced in code, not by convention.
- The sibling's PAPER1 swing book is **not** onboarded (that is exactly the rejected standalone
  hypothesis; it stays on the sibling).

## Delivery plan

| Step | Scope |
|---|---|
| 1 | Backend: daily job + endpoint + reference_only test + CI-invariant allowlist entry |
| 2 | Frontend: monitor card + required language + evidence link |
| 3 | Docs: registry note (capability, not program), runbook entry for the job |
| 4 | Box deploy + first live ingest + verify the surface end-to-end |
