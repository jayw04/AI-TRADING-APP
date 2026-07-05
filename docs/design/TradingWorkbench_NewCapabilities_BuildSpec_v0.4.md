# TradingWorkbench — New-Capabilities Build Spec v0.4 (Phase 0 Reconciliation)

| Field | Value |
|---|---|
| Document version | v0.4 — folds the Phase 0 architecture confirmation + ADR 0037 into v0.3; corrects the paths/anchors v0.3 assumed |
| Date | 2026-07-05 |
| Relationship to v0.3 | **Additive + corrective.** v0.3 (`TradingWorkbench_NewCapabilities_BuildSpec_v0.3.docx`) stands as the capability narrative; this v0.4 is the authoritative source for confirmed repo paths, IDs, the schema shape, and the sequencing. Where they conflict, v0.4 wins. Written in `.md` for diffability (per review). Folds into the next docx cut. |
| Authority | ADR 0037 (Accepted 2026-07-05); Phase 0A note (`…EAD_Phase0A_SchemaReconciliation_v0.1.md`); Phase 0B note (`…EAD_Phase0B_SecurityMaster_CAP024_v0.1.md`) |
| Status | Phase 0 **closed** on the confirmation/pre-registration items; blocking gate remaining = owner sign-off of the Phase 0A backfill before its migration is applied. |

---

## 0. What changed from v0.3 → v0.4

Phase 0 confirmed most of v0.3's anchors against the repo but found **three divergences**; ADR 0037 resolved them and the two design notes specify them. v0.4 records the settled state so Phase 1 codes against reality, not the v0.3 proposals.

1. **Paths corrected** — the event stack is `apps/backend/app/altdata/*`, *not* the `app/data/…` / `app/events/…` tree v0.3 proposed. (§2.1 below.)
2. **Schema is hybrid** — extend the existing single `corporate_events` DuckDB table with real governance columns; no 24-field parallel schema. (§2.5 below.)
3. **Security Master is a real new capability (CAP-024)**, not an extension of `CikMap`. (§6.2 below.)
4. **Opportunity Registry does not exist** — it is ADR-0029 *Proposed*; the Daily Opportunity Report reads an audited `OpportunityInputAdapter`. (§4 below.)
5. **Governance ADR = 0037** (not the memo's unverified 0036/0037); **order-path isolation is now a CI invariant** (the fourteenth). (§7 below.)
6. **IDs confirmed** — Quiver = **DCAP-007**, Security Master = **CAP-024**. (§8 below.)

---

## §0.2 (corrected) — Confirmed existing assets this work builds on

| Asset (v0.3 name) | **Confirmed repo location** | How EAD uses it |
|---|---|---|
| PIT Event Store | `app/altdata/events/store.py` — `EventStore`, one generic `corporate_events` DuckDB table, free-form `event_type` string | **Extend** with governance columns (Phase 0A); add a Quiver `event_type`; **no second store** |
| SEC / Corporate-Event client | `app/altdata/sec/` — `EdgarClient`, `CikMap`, `form4.py`, `ingest.py` | **Reuse** as-is; `CikMap` becomes CAP-024's backbone |
| Data-provider abstraction | `app/factor_data/providers/` — concrete read-only classes (`SharadarProvider`, `FMPProvider`); **no ABC/registry** | Quiver client is a **sibling of `app/altdata/sec/`** (alt-data/event-driven), reading its key from `config.py` |
| SCAN-001 candidate engine | `app/factor_data/candidate_engine.py` (CAP-001) + premarket services/jobs | News/ETF/Macro/Gap/Volume/Options stay **SCAN-001 configs**, not new programs |
| Discovery Lab | Architecture concept (ADR 0029), **not** a package | EAD sits alongside SCAN-001 under this umbrella |
| Opportunity Registry | **ADR-0029 Proposed — not built.** Selection logic is fused in `range_insight.py` / `range_auto_select.py`; persists as ephemeral `symbols_json` | Report v0 reads an **adapter**, not the Registry (§4) |
| Program / Capability / Data registers | Programs: `app/research/programs.py` + Research Program Registry. Capabilities: **CAP-NNN** (max CAP-023). Data inputs: **DCAP-NNN** (max DCAP-006) | GOVCONTRACT-001 → program; Security Master → **CAP-024**; Quiver → **DCAP-007** |

> ⚠ `api/v1/opportunities.py` is the **dashboard aggregator** (six widget feeds) — it is **not** the Opportunity Registry (the frozen, pre-open, audited Top-N machine contract). Do not conflate them.

---

## §2.1 (corrected) — Component locations

| Component | **v0.4 confirmed path** | Note |
|---|---|---|
| Quiver provider client | `app/altdata/quiver/client.py` | Sibling of `app/altdata/sec/`; bearer-token from `config.py`; read-only; rides ADR-0017 OS trust store |
| Government-contract normalizer | `app/altdata/quiver/govcontracts.py` | Raw Quiver row → `CorporateEvent` (`event_type="gov_contract_award"`, `source="quiver"`), both `event_time` + `available_time` populated |
| Point-in-Time Security Master | `app/altdata/security_master.py` (CAP-024) | New cross-cutting package (§6.2 / Phase 0B) |
| Data Source Registry | `app/altdata/source_registry.py` (or a table; `app/data/` is gitignored) | Entitlement/licensing flags (§6.4); mirrors DCAP-007 |
| Event-type registration | *(none needed)* | `event_type` is a free-form string set by an `(EVENT_TYPE, SOURCE)` constant pair per ingest module — **no registry call, no schema change** |

The v0.3 paths `app/data/providers/quiver_client.py` and `app/events/normalizers/quiver_*.py` **do not match the repo** and are superseded by the above.

---

## §2.5 (corrected) — Hybrid Event schema (not a 24-field parallel schema)

The canonical fields v0.3 listed become **real columns on `corporate_events`** (the load-bearing, enforceable ones) plus the existing `payload` JSON (dataset-specific detail). Full DDL + the backfill in the Phase 0A note. Added columns:

`provider_dataset · source_event_id · available_time · revision_time · resolved_security_id · issuer_name_raw · ticker_raw · unresolved_reason · raw_payload_hash · data_source_id · research_eligible (DEFAULT FALSE)`

Retained: `event_id, cik, ticker, event_type, source, accession, filed_at, event_date, payload, ingested_at`. **No `confidence`/`score` column** (any score stays in `payload`, unreachable by ranking until pre-registered — ADR 0037 Decision 8). `available_time` is the canonical PIT anchor; `filed_at` retained (Form-4: `available_time = filed_at`). Compat view `corporate_events_pit = COALESCE(available_time, filed_at)` (no `ingested_at` fallback). EAD reads go through the new `events_asof_eligible()` (requires `research_eligible = TRUE AND available_time IS NOT NULL`); the legacy `events_asof()` is untouched.

---

## §2.6 (corrected) — Mapping acceptance gate: state the binding denominator

v0.3's "≥95% resolved-or-explicitly-unresolved" measured a completeness check that is ~100% by construction. The **binding gate** is a resolved *rate*:

- **Gate:** `confidently_resolved / public_company_events ≥ 85%` (proposed; confirm at Phase 0 sign-off).
- **Kill floor:** `< 70%` confidently resolved → stop/reassess vendor (§2.6a).
- **Separate completeness check:** `(confidently_resolved + explicitly_unresolved) = 100%` — every unresolved event carries a typed `unresolved_reason`. Not the constraint; must not be conflated with the gate.

All other §2.6 gates stand (raw hash 100%, idempotent `event_id`, ≥2yr history, PIT correctness `available_time ≤ T`, missing-`available_time` excluded). §2.6a kill criteria + the USAspending 100-event cross-check unchanged.

---

## §4 (corrected) — Daily Opportunity Report reads an audited adapter

The Opportunity Registry is **Proposed (ADR-0029), not built** — so Capability C v0 does **not** read it. Instead:

- **`OpportunityInputAdapter`** reads the Event Store (`events_asof_eligible`) + SCAN-001 candidate outputs (+ `range_auto_select` outputs, GOVCONTRACT events).
- The adapter **snapshots and audit-logs its input candidate set at read time**, so a report is reproducible from its snapshot and cannot reflect an intraday-mutated candidate set — the point-in-time repeatability the frozen Registry will eventually provide (ADR 0037 Decision 10).
- When the real Registry (ADR-0029) is built and Accepted, the adapter swaps its source; the Report code does not change.
- The internal **Data-Quality Report (§4.0) ships first**; card labels remain the strict whitelist (Watch · Research · Backtest Pending · Validated Pattern · Rejected Pattern); external exposure gated on licensing (§2.4) **and** compliance.

---

## §6.2 / §6.4 / §7 / §8 (corrected) — Capability, licensing, governance, IDs

- **§6.2 Security Master = CAP-024**, minimal v0 resolver (`resolve_security(...) -> ResolutionResult`; hierarchy CIK → ticker → exact-name → fuzzy-above-threshold → unresolved; typed reasons; fuzzy gated so no silent bad mapping). Full design in the Phase 0B note. Placement `app/altdata/security_master.py`.
- **§6.4 Data Source Registry** populated for Quiver **before** ingestion; its `commercial_use_allowed` / `derived_signal_allowed` / `cache_allowed` flags gate the Report. Mirrored at the doc level as **DCAP-007** (`TradingWorkbench_Data_Capability_Registry_v0.1.md`, current max DCAP-006).
- **§7 Governance ADR = ADR 0037** (Accepted 2026-07-05) — absorbs the §7 governance principles **and** the three reconciliation decisions. It also establishes the **fourteenth CI invariant**, `check_altdata_order_path_isolation.sh` (the EAD alt-data / Security-Master / opportunity-report packages import no order-path module) — lands with Phase 1.
- **§8 IDs:** Security Master → **CAP-024** (next free; max was CAP-023). Quiver → **DCAP-007** (next free; max was DCAP-006). GOVCONTRACT-001 → new row in `app/research/programs.py` + Research Program Registry. These are the ADR-0030 register split: CAP-024 = Platform Capability, GOVCONTRACT-001 = Research Program, DCAP-007 = data input; each onboarded through the ADR-0030 lifecycle.

Licensing (§2.4) unchanged and still blocking for external use: Quiver **Hobbyist $30/mo month-to-month** for the internal MVP; Hobbyist and Trader both carry **No Commercial Use Rights**; a written Commercial quote is required before any external card.

---

## §9 (corrected) — Build sequencing

**Phase 0 (this reconciliation) — closed** except the backfill sign-off. Deliverables: ADR 0037 (Accepted); Phase 0A schema-reconciliation note (design; backfill awaiting sign-off); Phase 0B Security-Master design; this v0.4. Thresholds pre-registered (§2.6, §3.2, Phase 0B §11). Exit gate met: no new parallel stores/registries; IDs assigned; paths confirmed.

- **Phase 0A apply** (gated on owner backfill sign-off): `store.py` columns + column-explicit INSERT + `events_asof_eligible` + compat view + `scripts/migrate_event_store_ead.py` + tests; run the INSIDER-001 reproduction-diff green before the backfill.
- **Phase 0B build:** CAP-024 v0 (`app/altdata/security_master.py`) + tests.
- **Phase 1 — Quiver government-contract ingestion (Hobbyist):** `app/altdata/quiver/` client + `govcontracts` normalizer writing `available_time` + `resolved_security_id` (via CAP-024) + `research_eligible`; Data Source Registry (DCAP-007) entry; internal Data-Quality Report; `check_altdata_order_path_isolation.sh`. **Exit:** one dataset end-to-end, all §2.6 gates green, USAspending cross-check passed, §2.6a kill criteria not triggered.
- **Phase 2 — GOVCONTRACT-001:** pre-registration, matched benchmark (§3.2), walk-forward, evidence package, registry verdict (verdict doesn't matter; system maturity does).
- **Phase 3 — Internal Daily Opportunity Report v0:** cards from Event Store + SCAN candidates via `OpportunityInputAdapter`; no external exposure; compliance + licensing reviews scheduled.
- **Phase 4 — Hypothesis Generator prototype:** 1–3/week, BH FDR q≤0.10, rejected-registry auto-check, matched benchmark before testing.

Sequencing rule (unchanged): prove one connector end-to-end before fan-out.

---

## §10 (corrected) — Open decisions: status

| # | Decision | Status |
|---|---|---|
| 1 | Next ADR number | **Closed** — ADR 0037 |
| 2 | Confirmed paths (provider / Event-Store / SEC) | **Closed** — §0.2 / §2.1 |
| 3 | Quiver commercial licensing | **Open** — Hobbyist for internal MVP; Commercial quote required before external Report (§2.4) |
| 4 | SCAN-001 configs vs new programs | **Closed** — News/ETF/Macro/Gap/Volume/Options = SCAN-001 configs |
| 5 | Security Master CAP id + owner | **Closed on id (CAP-024)**; owner = open |
| 6 | Report placement + external-exposure policy | **Partly closed** — internal v0 via adapter; external gated on licensing + compliance |
| 7 | Pre-register §2.6 / §3.2 / Phase-0B thresholds | **Closed** — pre-registered as Phase-1 MVP gates (mapping ≥85% gate / <70% kill; ~20 controls, min 10; BH q≤0.10; 20d primary + 5/10/60d; `FUZZY_MIN` 0.90) |
| 8 (new) | **Phase 0A backfill sign-off** | **Open — blocking Phase 0A apply** (Phase 0A note §6) |
