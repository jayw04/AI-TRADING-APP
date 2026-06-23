# SCAN-001 — The Premarket-Data Gate: Plan & Forward Pre-Registration (v0.1)

| Field | Value |
|---|---|
| Document version | v0.1 (plan + forward pre-registration draft — open questions OPEN; not yet frozen) |
| Date | 2026-06-23 |
| Program | SCAN-001 (Market Opportunity Discovery Engine — first profile of the Discovery Lab) |
| Type | Platform Capability · **the L3 → L4 prerequisite** (Production-Ready) |
| Predecessor | v0.5 results (DECOUPLED-CALIBRATED; PR #237) — Discovery Lab v1.0 complete on **daily-bar** data |
| Depends on | **PR #221** (`feat/premarket-gappers-panel`) — the read-only premarket data source; **PR #237** (Discovery Confidence / `confidence_gr`) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Close the one remaining gap before any *live* SCAN use: the engine was validated on **daily-bar approximations** of gap/RVOL; this gate replaces them with **real 09:25 premarket data** and **forward-replicates** the selection edge on it. |
| Tag on completion | `scan-001-premarket-gate-complete` (after the forward window clears the bar) |
| Out of scope | Any order routing (SCAN stays advisory — the candidate set is *evidence*, not a signal, §0a); the gappers *panel* itself (that is PR #221); intraday entry/exit/sizing. |

> **Why this gate exists (stated plainly).** Every SCAN study to date — v0.1 through v0.5 — used **daily bars** as
> a *proxy* for premarket data: gap ≈ (official open − prior close), RVOL ≈ a daily-volume ratio. Every plan
> said the same thing in its honest-scope: *"a real premarket feed stays a hard gate before any promotion."*
> This is that gate. It is the **only** thing standing between Discovery Lab v1.0 (validated on proxies) and L4
> (Production-Ready on real data). It is **not** a new research idea — it is the validation of the existing one
> on the data it will actually run on.

> **Reframe (folds the review): this is the *Production Validation Gate*, premarket instance.** The gate is not
> fundamentally about *premarket data* — it is about *validating that a capability works in its intended
> production environment before promotion.* Premarket gappers are the **first instance**; future capabilities get
> sibling gates (Options / Macro / ETF Validation Gates). Code stays `premarket_*` (the instance); the concept is
> Production Validation. It runs in **two logical phases**: **Phase A — Technical Validation** (data → adapter →
> scanner → persistence = increments A, B, C-persist) and **Phase B — Scientific Validation** (realized outcome →
> evidence → bootstrap → verdict = increments C-backfill, D).

---

## 0. Two hard realities that shape everything (read first)

These are not risks to mitigate later — they are the facts the whole plan is built around.

### 0a. There is no historical premarket store — the gate is a FORWARD study

The premarket data source (PR #221) is a sibling scanner that writes **one `premarket_gappers_<date>.json` per
trading day, going forward**. There is no back-history of real premarket snapshots to backtest against. So
"replicate the edge on premarket data" **cannot be a one-shot backtest** — it is a **forward replication**:
accumulate daily (premarket-candidate → realized-intraday-outcome) pairs and test the edge after a
pre-registered minimum window. This is the same Evidence-Engineering shape as a live paper track record (ADR
0014: short live P&L is not edge evidence — but an *accumulating, pre-registered* series is).

### 0b. The premarket gappers universe ≠ the validated universe

SCAN's edge was validated on a **top-200 / top-500 liquid** universe (mega/large-cap, from the DuckDB store)
with daily-bar features. The #221 source is the **Yahoo gainers** table — small/mid-cap, *catalyst-driven*
gappers, a **different population**. So the gate is **not a clean data-swap**: running the frozen engine on
gappers tests whether the selection edge **transfers** to that population. Two sub-questions fall out:

- **Eligibility overlap:** SCAN's gates (price > $10, prev-day $-vol > $20M) will filter many small-cap gappers.
  How many gappers survive into the engine at all? (An empirical first finding, not an assumption.)
- **Feature provenance:** a gapper row gives real premarket **gap %** and **premarket volume** (→ a *real* RVOL),
  but **ATR** and **prev-day $-volume** still come from the historical store (a join on symbol). Names not in the
  store have no ATR → either excluded or ATR-gated out.

**Consequence:** the gate may conclude the edge **transfers** (promote to L4), **does not transfer to gappers**
(the engine is a *liquid-universe* tool; premarket use needs a liquid premarket feed, not the gappers panel), or
**is inconclusive pending more days**. All three are citable, honest outcomes.

---

## 1. What the gate must prove (the forward replication)

> The frozen SCAN engine, fed **real premarket** features, selects candidates whose **realized intraday
> expansion** beats the eligible-field baseline — i.e. the daily-bar-validated edge **survives** on real data.

The outcome metrics are unchanged from v0.2–v0.5: **expansion ratio `E`** (primary), **capturable move `CM`**
(companion). The baseline is the same candidate-vs-eligible-field construction. The only change is the **input**:
real premarket gap/RVOL instead of daily-bar proxies.

---

## 2. Architecture — four increments (read-only, invariant-safe throughout)

```
  (A) premarket-feature adapter   (B) daily live SCAN scan        (C) forward-evidence accumulator
  gappers row + store join   ──►  frozen engine → Candidate   ──►  append (date, candidates, features)
  → engine feature panel          Report w/ Discovery               at 09:25; append realized T-outcome
  (real gap, real RVOL,           Confidence (advisory)             after the close → daily evidence row
   ATR/$vol from store)                  │                                 │
                                         ▼                                 ▼
                                  read-only, no order path     (D) replication verdict after N≥? days
                                  (SCAN §0a)                        (frozen bar, §3) → L4 or not
```

- **(A) Premarket-feature adapter** — *pure, unit-tested.* `premarket_panel(gappers, store_features)` maps each
  gapper (symbol, premarket price, gap %, premarket volume) + the symbol's store features (ATR%, prev-day
  $-vol, prior close) into the engine's feature-panel row. Real gap and real RVOL replace the proxies; ATR/$vol
  come from the store. Names with no store coverage are dropped (logged). **No network, no LLM** — reads the
  #221 file + the local store.
- **(B) Daily live SCAN scan** — a read-only job that, at ~09:25 ET, builds the premarket panel and runs the
  **frozen** engine → a real **Candidate Report** (with **Discovery Confidence**, `confidence_gr`). Surfaced as
  *evidence/advisory* only (Opportunities/Discovery surface), **never** to the OrderRouter. Fail-soft like #221.
- **(C) Forward-evidence accumulator** — persist each day's premarket candidate set; after the close, attach the
  realized intraday outcome (`E`, `CM`) per candidate and per eligible-field baseline. One durable evidence row
  per day. (Storage: a small append-only table or dated JSON under `evidence/`, mirroring #221's file pattern —
  §7 OQ.)
- **(D) Replication verdict** — after a pre-registered **N-day** window, run the v0.2-style edge test on the
  accumulated real-premarket series → the gate's verdict (§3). This is the only step that produces the L4 call.

---

## 3. Frozen forward hypothesis & success bar (pre-registration)

| Item | Value (proposed — owner to freeze, §7) |
|---|---|
| **Hypothesis** | Candidate-set mean `E` > eligible-field baseline mean `E`, on real premarket data, CI-separated. |
| **Primary metric** | Expansion ratio `E` (continuity with v0.2–v0.5); `CM` companion. |
| **Minimum window** | **N ≥ 40 trading days** with ≥ some candidates/day (a forward analogue of the v0.3 60-day cell floor; ~2 months). |
| **Test** | Seeded circular-block bootstrap on the daily edge series (the v0.2 machinery), 95% CI excludes 0. |
| **Verdict gate** | **TRANSFERS** (edge CI-separated > 0 → recommend L4) · **DOES-NOT-TRANSFER** (CI ≤ 0 → the engine is a liquid-universe tool; document the boundary) · **INSUFFICIENT** (< N days or too few candidates/day → keep accruing). |

**Honest constraint (ADR 0014):** until the window clears, the live Candidate Report is **advisory only** and
the gate verdict is **INSUFFICIENT** — no live ranking/sizing use is unlocked by partial data.

---

## 4. Invariants & safety (non-negotiable)

- **Advisory only — no order path.** The Candidate Report is *evidence* (§0a). It never reaches `OrderRouter`,
  generates no orders, and is not a strategy. (No risk-engine interaction; nothing to bypass.)
- **No new external dependency / no LLM in our app.** All web fetching + any catalyst LLM happen in the *sibling*
  scanner (PR #221); TradingWorkbench reads a **local file** + the local store. Clear of the
  external-dependency and no-LLM-in-order-path invariants.
- **Fail-soft.** Missing/stale/malformed premarket file → empty panel, the scan is a no-op, the page degrades to
  a stale badge (as #221 already does). Never 500s, never blocks.
- **Read-only research.** No migrations beyond an optional append-only evidence table; no order-path code.

---

## 5. Constraints & dependencies

- **#221 is the data source and must land first** (it is MERGEABLE; ⚠ **CI is currently UNSTABLE — one failing
  check** — to be diagnosed before relying on it). The gate's adapter reads its `premarket_gappers_<date>.json`.
- **#237 (Discovery Confidence) provides `confidence_gr`** for the Candidate Report's confidence field.
- **Norton SSL** (blocks `data.alpaca.markets`) is **sidestepped**: the gappers come from the sibling scanner's
  local file, not a direct premarket API call from our app. (If a *liquid* premarket feed is later wanted —
  §0b's alternative — that would reintroduce the Norton/data-source question; out of scope here.)
- **Activation needs a backend rebuild** (the #221 read-only mount + any new job register on rebuild).

---

## 6. Deliverables

1. **(A)** Pure `premarket_panel(...)` adapter + tests (gappers row + store join → engine panel; real gap/RVOL).
2. **(B)** Read-only daily live SCAN scan → advisory Candidate Report with Discovery Confidence (fail-soft).
3. **(C)** Forward-evidence accumulator (durable daily premarket-candidate → realized-outcome rows).
4. **(D)** The replication harness + verdict (run after the N-day window) → the L4 recommendation.
5. **Session/results doc** + registry update (record the gate's status; advance to **L4** only on a TRANSFERS
   verdict after the window).

Read-only research/infrastructure throughout. **Walk-away ≥ 1 h** before merge (≥ 2 h if any new persistence is
added, per the audit/migration convention).

### Build status (2026-06-23)

- **(A) Premarket-feature adapter — ✅ BUILT** (`app/factor_data/premarket_adapter.py`): pure
  `premarket_feature_row` / `premarket_panel` + `features_from_bars` (store-join core); real gap, RVOL proxy,
  store ATR, drop rules; 15 tests; ruff/mypy clean.
- **(B) Read-only live premarket scan — ✅ BUILT** (`app/services/premarket_scan.py`): `store_features_for`
  (PIT store join) + `run_premarket_scan` (read gappers → join → panel → select), fail-soft, surfaces the §0b
  funnel; 6 tests. *Independent of #237 — uses the engine's selection only; a Discovery-Confidence overlay on
  the report is a one-line follow-on once #237 lands.* **Activation** (registering a ~09:25 job) needs a backend
  rebuild — deferred, like #221.
- **(C) Forward-evidence accumulator — ✅ BUILT (both halves).** *Persist* (`premarket_evidence.py`):
  `evidence_record` + `persist_record` + `record_premarket_scan` (Option 3 — persist now, no new dependency; also
  persists the eligible FIELD for the baseline). *Back-fill* (`premarket_outcomes.py`, **ADR 0024 accepted**):
  `compute_outcome` (pure realized `E`/`CM`/`NM`) + `backfill_record` (candidate outcomes + eligible baseline +
  candidate-vs-field edge + coverage; `filled`/`uncovered`) + `fetch_realized_bars` (thin Alpaca daily-bar read
  via `BarCache`, fail-soft) + `backfill_evidence` (orchestration).
- **(D) Replication verdict — ✅ harness BUILT** (`premarket_verdict.py`): `gate_verdict` (the v0.2 circular-block
  bootstrap on the daily `edge_E` series) → **INSUFFICIENT** (< 40 filled days) / **TRANSFERS** (CI-sep > 0) /
  **DOES-NOT-TRANSFER** (CI ≤ 0) + `load_records` + `run_gate_verdict`. The harness is complete; its **verdict is
  forward** — INSUFFICIENT until the ~40-day window of back-filled records accrues (ADR 0014).

> **The (C)/(D) decision — RESOLVED + BUILT (owner, 2026-06-23): Option 3 then Option 2.** Option 3 persists the
> premarket candidate set from today (zero new dependency); **Option 2 (ADR 0024, accepted)** back-fills the
> realized outcomes from **Alpaca** (the existing audited dependency — not a new feed), with coverage recorded.
> All four increments (A–D) are now built; what remains is **forward accrual** + **activation** (registering the
> ~09:25 scan + ~16:30 back-fill jobs + a runtime evidence dir — needs a backend rebuild).

---

## 7. Open questions — to RESOLVE with the owner before freezing

1. **Universe scope (the §0b crux)** — run the frozen engine **on the gappers universe as-is** (tests transfer
   to the catalyst-gapper population) ★ *recommended start*, OR source a **liquid premarket feed** to match the
   validated universe exactly (reintroduces a data-source/Norton question)? The former is buildable now and is
   itself a finding; the latter is the "true" replication of the validated universe.
2. **Minimum window N** — ★ **40 trading days** (~2 months) as the forward floor? Longer = more robust, slower.
3. **Evidence storage** — ★ dated JSON under `evidence/scan_001_premarket_gate/` (mirrors #221, zero schema
   risk), OR a small append-only `premarket_scan_evidence` table (queryable, but a migration + ≥ 2 h walk-away)?
4. **Sequencing** — land **#221** (fix its failing CI first) and **#237** before building the adapter (the gate
   stacks on both), OR build the adapter now against a fixture and wire the real source after they merge?
5. **Scope of THIS step** — does "proceed to #221" mean (a) get **#221 itself** review-ready/merged (the data
   source), (b) build increments **(A)+(B)** now (adapter + advisory live scan), or (c) the **full** gate
   including the forward accumulator? *Recommendation: confirm #221's CI + merge it, then build (A)+(B) stacked
   on #237; (C)+(D) follow once data flows.*

**Partially resolved (owner, 2026-06-23):** **OQ1 → gappers universe as-is** (test edge *transfer* to the
catalyst-gapper population; buildable now, the transfer result is itself a finding). **OQ5 → fix + merge #221
first** (diagnose its failing CI, make it merge-ready as the data source), then build (A)+(B) stacked on #237.
OQ2/3/4 take the ★ defaults when the build phase is frozen. *This step = get #221 merge-ready.*

The rest stays not-approved-for-build until §3 + the remaining OQs are frozen. This is a forward study +
read-only infra; nothing here touches the order path.

---

## 8. Honest framing

This gate is deliberately *unglamorous*: it does not deepen SCAN (the reviewer's "don't keep extending SCAN" —
this is not a v0.6, it is the **promotion validation** v0.2–v0.5 always named as the prerequisite). Its most
likely near-term verdict is **INSUFFICIENT** (data must accrue), and a genuinely possible verdict is
**DOES-NOT-TRANSFER** (the engine is a liquid-universe tool, and the gappers panel is the wrong feed for it) —
which would be a valuable, citable boundary, not a failure. Either way, it is the honest last step before any
claim that SCAN is production-ready.
