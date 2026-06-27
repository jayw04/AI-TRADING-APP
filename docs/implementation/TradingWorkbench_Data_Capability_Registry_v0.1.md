# TradingWorkbench — Data Capability Registry (v0.1)

> The catalog of the **external data capabilities** every research program depends on — the registry the
> review (`Docs/implementation/comments.md`, 2026-06-25) identified as missing alongside the **Research
> Program Registry**, the (platform) **Capability Registry**, and **Continuous Evidence**. Where the
> Research Program Registry answers *"what have we researched?"* and the platform Capability Matrix answers
> *"what reusable engines/methods did programs leave behind?"*, this answers *"what information can the
> platform see, and under what contract?"* — because **every research program is gated by the data
> capabilities it consumes.**

| Field | Value |
|---|---|
| Version | v0.1 (2026-06-25) — initial draft, folding the `comments.md` strategic review ("Data Capability Registry — the one missing registry"). |
| Namespace | **`DCAP-NNN`** — deliberately **distinct from the platform `CAP-NNN`** in the Research Program Registry. `CAP-NNN` = reusable *engines / methods* (bootstrap, Evidence Package, sector-neutral construction…). `DCAP-NNN` = external *data inputs*. A program needs both. |
| Posture (all entries) | **Read-only and off the order path** (ADR 0002). Data flows Source → store → research → governance → execution; it is never itself an order signal. Outbound TLS rides the OS trust store (ADR 0017, beats Norton SSL inspection). |
| Convention | IDs are permanent, assigned in adoption order. A new research program's feasibility = *which DCAPs it requires* (some new programs need a new DCAP first — e.g. INSIDER-001 needs DCAP-005). |
| Source of truth | The governing ADRs + `app/config.py` (vendor config) + the local stores. This doc is the narrative companion the whitepaper/patent cite. |

---

## The registry

| DCAP | Capability | Information class | Source | Auth | Governing ADR(s) | Status | Consumers (programs) |
|---|---|---|---|---|---|---|---|
| **DCAP-001** | **Survivorship-free PIT equities spine** | price + fundamental (PIT) | **Sharadar** (Nasdaq Data Link) — SEP / SF1 / DAILY / METRICS / TICKERS / ACTIONS / SF3 13F | `Settings` env-alias `NASDAQ_DATA_LINK_API_KEY` (not CredentialStore) | 0018, 0023 | **Live** | MOM-001, SEC-001, LOW-001, TREND-001, SCAN-001 (the spine of nearly everything) |
| **DCAP-002** | **Fundamentals + regime data** | fundamental + regime | **FMP** (Financial Modeling Prep `/stable`) — income/balance/cash-flow/ratios + `^VIX` | `Settings` env-alias `FMP_API_KEY` | 0018, 0022 | **Live** | the value/quality multi-factor work, the §5 regime overlay (`vix_percentile`) |
| **DCAP-003** | **Market bars (intraday + daily)** | market data | **Alpaca** market-data API → `BarCache` (parquet) | broker creds (encrypted `CredentialStore`, ADR 0003) — shared with execution | 0024 (realized-outcome back-fill), rides 0017 | **Live** | Range Trader (5-min intraday), SCAN-001 gate back-fill, equity/account sync |
| **DCAP-004** | **Premarket gappers feed** | event / discovery | external `premarket_gappers_<date>.json` (sibling `claude-trading-view` scanner), mounted read-only | none (file mount) | — (SCAN-001 era) | **Live** | SCAN-001 Production Validation Gate (the premarket scan) |
| **DCAP-005** | **Corporate-event filings (SEC EDGAR)** | **event-driven / alternative data** (NEW class) | **SEC EDGAR** (`data.sec.gov`) — Form 4 now; 8-K / 13F / 10-Q/10-K / earnings later | **none** (public) — `Settings` `User-Agent` + rate limit | **0027 (Draft)** | **Planned** — §1 build in progress | **INSIDER-001** (the first consumer of the Event-Driven Research Capability) |
| **DCAP-006** | **Total-Return Adapter** (a **Canonical Data Adapter**) | market data — *canonical/derived* | **derived**: `app/factor_data/total_return.py` post-processes DCAP-003 (Alpaca raw closes) + DCAP-001 (Sharadar `actions` distributions/splits) into total-return bars | inherits DCAP-001/003 creds (no new source) | **0030 (Proposed)**, ADR 0014 (reproducibility) | **Built (offline core)** — live distributions fetch Norton-gated (deferred) | **PORT-001** (cross-asset sleeve); future dividend/bond/ETF strategies |

---

## Per-capability detail

- **DCAP-001 — Sharadar.** The survivorship-free, point-in-time equities spine (local `factor_data_full.duckdb`); ~10-yr SF1 depth (2016+, a known limit, ADR 0023). The single most-depended-on capability — every price/factor program reads it. PIT correctness (ADR 0018) is what makes the catalog's backtests honest (ADR 0014).
- **DCAP-002 — FMP.** Read-only fundamentals + `^VIX` (the regime input behind the P10 §5 exposure overlay, ADR 0022). Same env-alias posture as Sharadar.
- **DCAP-003 — Alpaca market bars.** The intraday/daily bar feed (cached to parquet). Dual-purpose vendor: the *data* side is read-only and lives here; *execution* is the order path (ADR 0002, out of this registry's scope). The ADR-0017 OS-trust-store fix is what keeps it flowing under Norton SSL inspection.
- **DCAP-004 — Premarket gappers.** A read-only external feed from the sibling scanner, mounted into the container. Advisory only; SCAN-001's premarket scan joins it to DCAP-001 features. A missing day's file ⇒ 0 candidates (fail-soft).
- **DCAP-005 — SEC EDGAR.** The **first event-driven / alternative-data** capability — a genuinely new *information class* (corporate events), not just a vendor (ADR 0027). Public, no key. Initial implementation = Form 4; architected as *Corporate Event Capability → SEC Filing Capability → Form 4* so 8-K / 13F / earnings drop in later. Persisted into a **PIT Event Store** at the corporate-event level, reusable by future event programs (Earnings, Buybacks, Dividends). **Planned** — unlocked by ratifying ADR 0027 and the §1 build.
- **DCAP-006 — Total-Return Adapter.** The **first Canonical Data Adapter** — a new *sub-class* of data capability that **normalizes** existing raw vendor data into a canonical, reproducible form rather than adding a new source. It post-processes DCAP-003 (unadjusted Alpaca closes) + DCAP-001 (Sharadar `actions` distributions/splits) into **total-return** bars (ADR 0030 #2; the adjustment is recorded in the Evidence Package, ADR 0014 — no opaque vendor flag). No new vendor → no new external dependency. Built (offline core, `total_return.py`, unit-tested); the live distributions fetch is Norton-gated. PORT-001's cross-asset sleeve is the first consumer; future dividend/bond/ETF strategies reuse it. _(Future Canonical Data Adapter peers: a Corporate-Action adapter, FX normalization, trading-calendar normalization — ADR 0030 #2.)_

---

## Why this registry matters

- **Every program is gated by its data.** A program's feasibility is "which DCAPs does it need, and are they Live?" INSIDER-001 was blocked on a *new* DCAP (DCAP-005) — making that dependency explicit is exactly what the new program plan does.
- **Data capabilities compound across programs** — DCAP-001 alone powers five programs; DCAP-005's Event Store will power a whole event-driven family. This is the platform's *capability-by-capability* evolution (the review's "quantitative operating system" framing) seen from the data side.
- **One contract, audited once.** Every DCAP shares the read-only / off-order-path / OS-trust-store posture, so the safety review is per-capability, not per-program.

## Relationship to the other registries (the four-layer model)

```
Evidence Engineering (methodology)
   │
Research Framework (ProgramSpec / Factor Lab / Discovery Lab / Event-Study Engine …)
   │
Platform Capabilities ─┬─ CAP-NNN  (reusable engines/methods)   ← Research Program Registry's Capability Matrix
                       └─ DCAP-NNN (external data inputs)        ← THIS registry
   │
Research Programs (MOM / SEC / LOW / TREND / SCAN / INSIDER …)  ← Research Program Registry
```

Each research program in the Research Program Registry declares the **DCAPs it consumes**; each DCAP here lists the **programs it serves**. Together with the Decision Register and Continuous Evidence, these are the platform's institutional memory.

---

*v0.1 — folds the `comments.md` review. Grows one capability at a time; never closes. DCAP-005 flips to **Live** when ADR 0027 is ratified and the §1 EDGAR ingestion ships.*
