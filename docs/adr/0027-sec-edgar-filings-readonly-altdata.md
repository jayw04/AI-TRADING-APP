# ADR 0027 — SEC EDGAR filings as a read-only alternative-data source (initial: Form 4)

| Field | Value |
|---|---|
| Date | 2026-06-25 |
| Status | **Accepted** (owner ratified 2026-06-25; comments.md review folded — the Corporate Event Capability → SEC Filing Capability → Form 4 hierarchy) |
| Phase | INSIDER-001 §1 — the platform's first event-driven / alternative-data program ("Event-Driven Research Capability v1") |
| Supersedes | — |
| Related | 0018 (PIT factor data — same read-only / off-order-path / config-not-CredentialStore posture, extended here to a *no-key* public source), 0019 (Research Engine — read-only subsystem the events feed), 0002 (single OrderRouter — this data never reaches the order path), 0017 (OS trust store for outbound TLS — the EDGAR fetch rides it), 0026 (Factor Lab — INSIDER-001 lands as a `ProgramSpec` consuming this data), 0014 (backtests = eval ground truth — PIT correctness is what keeps the insider event study honest), 0037 (EAD — extends this store to paid alternative data: Quiver events + first-class governance/PIT columns, Security Master CAP-024) |

## Context

TradingWorkbench's research programs to date (MOM / SEC / LOW / TREND / SCAN) are all built from **market prices or factor/fundamental data** (Sharadar/FMP, ADR 0018). The next program, **INSIDER-001**, is the platform's first **event-driven / alternative-data** program: it studies whether SEC Form 4 **corporate-insider open-market buys** drift up over ~60–120 days (validated in a sibling system; verdict = a small-cap/value factor tilt, residual alpha not significant — see `docs/implementation/TradingWorkbench_INSIDER001_InsiderConviction_Plan_v0.1.md`).

That requires a **new external data source — the SEC's EDGAR filing system** — which TradingWorkbench has never consumed. Per the platform invariant (*adding a new external dependency requires an ADR*), this decision is recorded before the ingestion code is written. The owner framed the goal (ARD review, 2026-06-25) as building a **reusable capability**, not insider-specific code: EDGAR is *"a SEC-Filing Capability (initial implementation: Form 4)"* that future event programs (8-K, 10-Q/10-K, 13F, earnings) inherit. The question: on what terms does TradingWorkbench adopt EDGAR?

## Decision

**Adopt SEC EDGAR (`data.sec.gov` / `www.sec.gov`) as a strictly read-only, off-order-path alternative-data source, built as a reusable capability whose initial implementation parses Form 4 open-market buys into a point-in-time Event Store.**

> **This ADR is about introducing a new *information class* (corporate events), not just a vendor (owner review).** The capability is deliberately layered so future event types fit without re-architecture:
>
> ```
> Corporate Event Capability        ← the general class (any corporate event)
>   └── SEC Filing Capability        ← filings specifically (EDGAR)
>         └── Form 4                  ← this program's initial implementation
>               (later: 8-K · 13F · 10-Q/10-K · earnings)
> ```
>
> The **point-in-time Event Store sits at the Corporate-Event level** (event-type-agnostic), so earnings / buybacks / dividends — whether or not they arrive as SEC filings — reuse it. EDGAR is the first *SEC-Filing* implementation of that broader class.

1. **Read-only and off the order path (ADR 0002, inherited from 0018/0019).** The EDGAR ingestion and the Event Store never import the OrderRouter / risk engine / brokers and never submit, modify, or halt an order. Insider events are *advisory research inputs*: they flow Event Store → signal → evidence → governance → (only then) the OrderRouter/risk/audit. The data is never itself an order signal — exactly the posture of the premarket gappers (ADR 0024 era) and the Sharadar/FMP data (ADR 0018).
2. **Public source, no credential.** EDGAR is free and unauthenticated; there is **no API key**. The only required configuration is a **declared `User-Agent`** (SEC fair-access policy) + a request rate limit — held as `Settings` fields (env-overridable), **not** the encrypted `CredentialStore` and **not** a `check_no_env_credentials` secret (there is no secret). This is the ADR-0018 "vendor config is Settings, not CredentialStore" rule, simplified by the absence of a key.
3. **Fair-access compliance is a hard requirement.** A descriptive `User-Agent` (org + contact) on every request and a client-side cap of **≤ 10 requests/second** (SEC's published limit), with backoff on 403/429. A research data pull must never get the platform's IP blocked.
4. **Point-in-time Event Store (non-negotiable for an honest verdict).** Filings are recorded **as-of their filing/acceptance timestamp**, never back-dated to the transaction date in a way that leaks look-ahead. This Event Store is the reusable artifact — a general corporate-event store, not an insider table — so future event programs reuse it. (The sibling system's #1 research gap is the absence of this PIT store; we fix it at the foundation.)
5. **A data-validation gate precedes any research.** Before a signal or verdict consumes EDGAR data, an explicit validation step checks duplicate filings, amendments, ticker→CIK resolution (the sibling system flags ~11% unresolved CIK), missing filings, and filing latency. Untrustworthy data blocks the research (plan §2).
6. **One focused EDGAR ADR now; a generic Alternative-Data Framework ADR later.** Per owner OQ5, this ADR is scoped to SEC filings. When a *second, architecturally-different* alt-data source arrives (news, macro, options), a broader framework ADR generalizes — but not pre-emptively.

## Rationale

- **EDGAR is the authoritative, free, canonical source for insider filings.** Form 4 is filed directly with the SEC; there is no cleaner or cheaper primary source. A paid insider-data vendor would add cost, a license, and a layer between us and the primary record, for data the SEC publishes openly.
- **Read-only is the safety contract, unchanged.** Keeping the whole capability off the order path means none of P5's invariants (single router, non-bypassable risk, no-LLM-in-order-path) are touched. The new information class enters only through the existing research → governance → execution discipline.
- **PIT correctness is what makes the verdict honest (ADR 0014).** An insider event study is only evidence if the data available at decision time excludes look-ahead. A general PIT Event Store enforces that once, for every event program — rather than each program re-deriving it (and risking the look-ahead that already bit the sibling system's universe).
- **Capability, not one-off (owner framing).** Architecting EDGAR as a SEC-Filing Capability + a general Event Store costs more up front than a Form-4-only script, but every future event program (earnings, buybacks, 13F) reuses it. This is the "evolve capability-by-capability" thesis (the program plan §0) made concrete.
- **Why config-not-CredentialStore.** There is no secret to protect — EDGAR is public. The `User-Agent`/rate-limit are operational config, identical in spirit to how Sharadar/FMP keys are `Settings` env-aliases (ADR 0018 §5), minus the encryption (nothing to encrypt).
- **Why a focused ADR (OQ5).** EDGAR filings have a specific shape (CIK identity, XML ownership documents, an acceptance timestamp). News, macro, and options data have *different* architectures; a premature "generic alt-data" abstraction would fit none of them well. A focused ADR is easier to maintain; the framework ADR is written when a second source proves the generalization.

## Implementation notes

- **Package:** `app/altdata/sec/` (new) — `client.py` (rate-limited read-only HTTP, declared `User-Agent`, rides the ADR-0017 OS trust store), `cik_map.py` (ticker→CIK from the SEC's `company_tickers.json`), `form4.py` (Form 4 XML parse: transaction code, role, value; the open-market-buy `P` subset), and the **Event Store** writer/reader.
- **Settings (new):** `sec_edgar_user_agent: str` (required; org + contact, SEC policy), `sec_edgar_rate_limit_per_sec: float = 8.0` (conservative under the 10/s ceiling). Empty `User-Agent` ⇒ ingestion disabled with a clear error (mirrors the agent-key-empty-disables pattern), never a silent un-throttled fetch.
- **Event Store:** a point-in-time corporate-event table/store (DuckDB alongside the factor store, or a dedicated SQLite table — decided in the §1 build), keyed by `(cik, accession, filed_at)`, recording the event as-of `filed_at`. Generic columns (issuer, event_type, payload) so non-Form-4 events fit later.
- **Off the order path / no new CI invariant.** The property is structural (the package imports no order-path module), identical to ADR 0019 — no invariant script is added; a reviewer confirms the import boundary.
- **No new pip dependency expected** beyond an HTTP client + stdlib XML already present; confirmed during the §1 build.
- **Data-validation checkpoint (plan §2):** a coverage/health report (dup filings, amendments folded, CIK resolution %, latency) gates research; a red flag blocks, mirroring the factor-data health gate (EE Methodology §7).

## Consequences

- **Positive:** a new *class* of information (corporate events) enters the platform through a reusable, PIT-correct capability; INSIDER-001 unblocks; future event programs (earnings/buybacks/13F) inherit the Event Store + the SEC-Filing client for free; no key to manage.
- **Negative:** a new external source to keep healthy (EDGAR availability, schema/endpoint drift, the ~11% ticker→CIK coverage hole that silently shrinks the universe); XML-parsing fragility across Form 4 variants; a fair-access rate cap to respect (slower bulk pulls); a second local store to maintain.
- **Neutral:** the trading/risk/execution path is entirely untouched — additive on the research side, exactly like ADR 0018/0019.

## Alternatives considered (not chosen)

- **A paid insider-data vendor.** Rejected: cost + license + a layer over the primary record, for data the SEC publishes free. Reconsider only if EDGAR coverage/latency proves inadequate at scale.
- **Bootstrap from the sibling system's already-pulled Form 4 data.** Rejected (owner OQ3): it yields a throwaway migration utility, not a reusable first-class capability. Build native EDGAR ingestion.
- **A generic "Alternative-Data Framework" ADR now.** Deferred (owner OQ5): future sources differ architecturally; a focused ADR is easier to maintain and the framework is written when a second source justifies it.
- **Store events in the existing factor store.** Rejected: corporate events are discrete records keyed by filing identity + filing time, not cross-sectional factor panels; a dedicated PIT Event Store is the honest model and the reusable artifact.
- **Skip the PIT store (scan current-universe at run time, like the sibling system).** Rejected: that is the look-ahead risk the sibling system itself flags as its #1 gap; an EE verdict requires PIT.

## Re-evaluation triggers

- **EDGAR fair-access / ToS / endpoint change** — if the SEC changes the rate limit, the `User-Agent` policy, or the `data.sec.gov` shape, revisit the client contract.
- **CIK-coverage materially biases results** — if the unresolved-CIK fraction (sibling system ~11%) is large enough to skew the event study, the ticker→CIK mapping becomes a first-class fix, not a known gap.
- **A second alt-data source arrives** (news / macro / options / a non-filing feed) — that is the trigger to write the broader Alternative-Data Framework ADR (OQ5), generalizing from two concrete sources rather than one.
- **Order-path coupling pressure** — if anything ever wants insider events to reach the order path directly (not via research → governance), that is a new decision (new ADR), not a quiet expansion — the read-only contract is load-bearing.
