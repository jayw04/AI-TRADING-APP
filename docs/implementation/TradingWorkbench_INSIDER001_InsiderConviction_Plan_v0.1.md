# Event-Driven Research Capability v1 — INSIDER-001 (first consumer) — Program Plan & Pre-Registration (v1.0)

| Field | Value |
|---|---|
| Document version | **v1.0 — FROZEN (owner ARD review 2026-06-25, 9.9/10; all five open questions resolved, §8). §1 may begin.** |
| Milestone | **Event-Driven Research Capability v1** — a *reusable* platform capability (SEC-Filing ingestion → Event Store → Event-Study Engine → Evidence → Governance). **INSIDER-001 is its first consumer**, not a one-off. |
| Program | INSIDER-001 — the platform's **first event-driven / alternative-data** research program |
| Type | **Capability promotion** of an already-validated sibling-system signal (like SEC-001 / LOW-001) **+ a new, reusable data capability** (SEC filings, initial = Form 4) |
| Governing | EvidenceEngineering Methodology v1.2 (lifecycle, §5 gate, verdict-as-data), ADR 0019 (Research Engine — read-only), ADR 0018 (PIT factor data), ADR 0002 (single OrderRouter), ADR 0026 (Factor Lab — programs as configuration). **A new EDGAR-specific ADR is required** (§4, OQ5). |
| Source research | `Docs/Strategies/Insider Strategy.md` (sibling system: 515 events 2021–2026, Sharpe ~0.54/60d, 90d optimal on the conviction subset; verdict = factor tilt, not significant alpha). |
| Scope | Build the reusable Event-Driven Research Capability and run **INSIDER-001** through the full EE lifecycle on it: native SEC-filing ingestion → event store → signal → event-study evidence → **independent reproduction** of the verdict → governance → (if promoted) paper activation through the OrderRouter / risk / audit stack, **co-existing** with the sibling system during an evaluation period. |
| Out of scope | Re-tuning / hedging the factor exposures; retiring the sibling system now; live (non-paper) trading; the Combined Book; a generic Alternative-Data ADR (deferred, OQ5); conviction-scoring v2. |

---

## 0. Strategic context — the platform now evolves *capability-by-capability*

The owner chose INSIDER-001 as the next research program and, on review, sharpened the framing (ARD review, 2026-06-25): **TradingWorkbench is no longer evolving strategy-by-strategy; it is evolving capability-by-capability.** Adding momentum added a *research* capability; adding LOW/SEC added a *PIT factor* capability; adding SCAN added a *discovery* capability. INSIDER-001 adds an **event-driven / alternative-data** capability — a fundamentally different *class of information* (every prior program started from market data or factors). That milestone — *the platform's first event-driven program* — is the real prize; the insider strategy is its first consumer.

So the deliverable is deliberately framed as a **reusable capability stack**, not one-off insider code:

```
SEC Filing ingestion → Event Store → Signal Construction → Event-Study Engine → Evidence → Governance
```

Each box is a first-class, reusable platform component (§4/§5) that future event programs (earnings, buybacks, dividends, analyst revisions, management changes, 13F) consume without redesign.

### 0a. Program taxonomy (owner S1) — three families, growing

| Program family | Examples | Information class |
|---|---|---|
| **Price-based** | MOM-001, TREND-001 | market prices / time-series |
| **Fundamental / factor** | LOW-001, SEC-001 | factor + fundamentals (PIT) |
| **Event-driven** | **INSIDER-001** (first) → Earnings, Buybacks, Dividends | discrete corporate events |
| *(future)* | News · Analyst · Macro · Options | alternative data |

This taxonomy organizes the Research Program Registry and the whitepaper; each new family *expands the platform*, it does not merely add a strategy.

### Why this program (and why it earns the discipline)

In its current home the signal runs as standalone scripts + a Windows Task — **no single OrderRouter, no non-bypassable risk engine, no hash-chained audit, no EE governance gate.** Migration subjects it to all of those, which *is* the platform's value proposition. And it is **verdict-distinct** (research-portfolio-lineup): an alternative-data factor tilt, a different verdict shape from the price-based catalog.

**Honesty invariant — we do NOT fake a pre-registration.** This signal is already researched; its verdict is *disclosed up front* (§2a) rather than presented as a blind discovery. INSIDER-001 is an **independent reproduction + governance + a new capability**, in the SEC-001 / LOW-001 "demonstrate repeatability" tradition. **Any divergence between the sibling system and TradingWorkbench is evidence to investigate, not an implementation failure** (owner OQ1) — the scientific mindset.

---

## 1. The validated signal (faithful to the source — no re-tuning)

Promote the **conviction-buy** signal exactly as validated in the sibling system (`Docs/Strategies/Insider Strategy.md` §1, §3.1):

- **Event:** an SEC Form 4 **open-market buy** (transaction code `P`) by an **exec/officer** in a **small/mid-cap** name.
- **Conviction filter (the validated subset):** `value ≥ $25k` **and** role ∈ {exec, officer} **and** (**clustered** `≥2` insiders within 30d **or** a **big solo** `≥ $100k`).
- **Construction:** long-only swing — buy each *new* hit at equal-dollar notional, hold ~90 days (source §5.4: 90d optimal, Sharpe 1.41, t 2.18), market-close on the exit date. Stop = catastrophe cap only (source showed every stop is a return drag with no portfolio-DD benefit — reproduced, §3).
- **Universe:** the source's 134-name survivorship-checked small/mid-cap set first (OQ2).

> **Faithfulness rule (strengthened, owner S8).** **No parameter is re-tuned, and parameter changes are PROHIBITED until faithful reproduction has completed.** Only after the verdict reproduces may a deliberate, flagged change be considered. This prevents accidental optimization masquerading as a port.

---

## 2. Pre-registered hypotheses (frozen before *our* re-run; prior disclosed)

- **H1 — standalone risk-adjusted drift.** The conviction-event book earns a positive risk-adjusted return vs an **equal-weight small/mid-cap benchmark** over the 90-day hold (paired circular-block Sharpe-diff bootstrap CI; EE §5).
- **H2 — factor attribution / diversification.** A 5-factor regression (MKT/SMB/VAL/MOM/LOWVOL) shows the return is **mostly factor beta** (SMB+/VAL+/high-vol/−MOM) with **insignificant residual alpha**; and correlation to the live momentum book is low enough to **diversify**.
- **H3 — regime + downside honesty.** Characterize *when* it works (value/small-cap-led) vs not (growth-led); reproduce the realistic portfolio drawdown (~−18% at $5k/name) and the finding that the stop is a return drag with no portfolio-DD benefit (source §5.4 Phase 3).

Verdict taxonomy: **A** standalone edge · **B** Diversifier · **C** Rejected · **D** Inconclusive.

### 2a. Expected Outcome (owner S7 — stated explicitly *before* implementation)

> | Dimension | Expectation (from the prior research) |
> |---|---|
> | **Standalone alpha** | **Unlikely** (residual alpha t < 1 across all subsets) |
> | **Diversifier (B verdict)** | **Likely** — a real alternative-data factor tilt |
> | **Platform capability** | **Expected** — the Event-Driven Research Capability is delivered regardless of verdict |
> | **SEC-Filing / EDGAR capability** | **Expected** — reusable beyond insider |
>
> A reproduced **B — Diversifier** is the *expected, successful* outcome — the honest "no" on standalone alpha **plus** a real diversifying capability and a reusable event-driven stack. Success is defined in §6a so it does not hinge on the verdict.

---

## 3. The evidence gate + verdict-as-data

Reuse the platform's standard gate (EE Methodology §5) and the Factor-Lab verdict-tree-as-data (ADR 0026): pre-registered, frozen, bootstrap CIs + p-values, walk-forward consistency, cost-robust, no in-sample tuning. The verdict tree is a `VerdictSpec` predicate list (A if H1 clears + consistent; B if it diversifies / is defensively useful; C if H1 clearly excludes a positive edge; else D) — faithful to the source's "factor tilt, sized and disclosed" conclusion.

---

## 4. The reusable capabilities (owner S2/S3/S6/S9 — four first-class components, not one)

The plan deliberately treats this as **four reusable platform components**, each outliving INSIDER-001:

```
SEC-Filing Capability → Event Store → Signal Construction → Event-Study Engine → Evidence → Governance
   (initial: Form 4)     (corporate    (conviction score    (de-overlapped,
                          events)        / any event score)   reusable per event)
```

**Why EDGAR matters — one event store, many programs (owner review).** The capability is layered
(*Corporate Event Capability → SEC Filing Capability → Form 4*, ADR 0027); the Event Store is at the
corporate-event level, so it feeds *every* future event program, not just insider:

```
SEC Filing ─▶ Event Store ─▶ Research Programs
                              ├── Insider   (INSIDER-001 — the first consumer)
                              ├── Earnings
                              ├── Buybacks
                              ├── Dividends
                              └── Future …
```

1. **SEC-Filing Capability (initial implementation: Form 4)** — *not* "EDGAR Form 4 only" (owner S2). A read-only SEC-filings ingestion under `app/altdata/` (new) — ticker→CIK mapping (source flags ~11% unresolved CIK), Form 4 `P`-parsing now; architected so **8-K / 10-Q / 10-K / 13F** drop in later without redesign. Off the order path; no key (EDGAR is free/public) → not the encrypted CredentialStore. **⚠ NEW EXTERNAL DEPENDENCY → an EDGAR-specific ADR (OQ5).**
2. **Event Store** (owner S9) — a **point-in-time corporate-event store** (the source's #1 research gap; current scoring uses current-universe pulls = look-ahead risk). PIT correctness is non-negotiable for an EE verdict. *"Corporate Events → Research → Signals"* — supports many future programs, not just insider.
3. **Signal Construction** (owner S6) — the conviction scorer as a reusable construction step (cluster + role + $ value now; any event-score later).
4. **Event-Study Engine** (owner S3 — equal billing with the data capability) — a reusable de-overlapped event-study harness (per-event drift, "already-held → skip", seeded bootstrap; built on `factor_data/evidence.py`). Reusable for **earnings, dividends, buybacks, analyst upgrades, management changes** — a platform capability in its own right.

**Build native EDGAR ingestion first (owner OQ3 — differs from the v0.1 draft).** The higher up-front engineering cost buys a *reusable, first-class platform capability* that all future event research inherits — rather than a throwaway migration utility that bootstraps off the sibling system's pulls.

---

## 5. Platform mapping — reuse, don't rebuild

| Need | Reuse / new |
|---|---|
| Universe + PIT price data | Sharadar SEP spine + `universe_asof` / `pit_universe` (ADR 0018) |
| Backtest + stats | `factor_data/backtest.py` + `evidence.py` (seeded bootstrap, paired Sharpe-diff CI) |
| Program-as-config + verdict tree | Factor Lab `ProgramSpec` / `run_program` / `VerdictSpec` (ADR 0026) |
| Live execution | the single **OrderRouter** + non-bypassable **risk engine** + hash-chained **audit** (the discipline the sibling scripts lack) |
| Activation discipline | strategy lifecycle (24h paper cooldown, status gating) |
| **NEW reusable components** | **SEC-Filing Capability · Event Store · Signal Construction · Event-Study Engine** (§4) |

---

## 6. Build sequence (each its own session + PR; ADR/data sessions ≥2h walk-away)

A **data-validation checkpoint is inserted between ingestion and research** (owner S4) — do **not** go straight from ingestion to a signal:

```
§1 ADR + SEC-Filing ingestion + Event Store
        ↓
§2 DATA VALIDATION  (duplicate filings · amendments · ticker→CIK mapping · missing CIKs · filing latency)
        ↓
§3 Signal Construction + Event-Study Engine
        ↓
§4 INSIDER-001 as a Factor-Lab program → independent reproduction → Evidence Package + Registry entry
        ↓
§5 Governance → (if promoted) paper activation, CO-EXISTING with the sibling system (OQ4)
```

- **§1** Write the EDGAR-specific ADR; build the read-only SEC-filing (Form 4) ingestion + ticker→CIK map + the PIT Event Store; coverage report. *(Largest, data-heavy.)*
- **§2** **Data validation** — prove the data is trustworthy *before* any research: de-duplicate filings, fold amendments, resolve the CIK gap, measure filing latency, PIT sanity. A failing check blocks §3.
- **§3** Signal Construction (faithful) + the reusable Event-Study Engine (`evidence.py`-based).
- **§4** `ProgramSpec` + `VerdictSpec`; run the gate; **independent reproduction** on TradingWorkbench PIT data → evidence package + Registry entry; investigate any divergence from the sibling numbers (OQ1).
- **§5** Governance; if the verdict warrants, a dedicated paper book via the OrderRouter/risk/audit — **running in parallel** with the sibling system through the evaluation period (OQ4).

### 6a. Success criteria (owner S5 — success is defined independent of the verdict)

The program is **successful when**:
1. **SEC-Filing / EDGAR capability is operational** (ingestion + PIT Event Store + clean coverage).
2. **The Event-Study Engine is reusable** (built generic, not insider-specific).
3. **The reproduction is statistically consistent** with the source (or any divergence is explained — OQ1).
4. **Governance is completed** (Registry entry + evidence package + decision).
5. **Paper activation** is done **if promoted** (B/A) — co-existing with the sibling.

This holds **even if the verdict remains "Diversifier."**

---

## 7. Out of scope (explicit)

- Re-tuning / hedging the factor exposures (source: own the factors, don't fight them).
- **Retiring the sibling system now** — it co-exists through the evaluation period (OQ4); retire only after sustained agreement.
- Live (non-paper) trading; the Combined Book; conviction-scoring v2; a generic **Alternative-Data Framework ADR** (deferred — a future ADR once more sources justify it, OQ5).
- Treating a reproduced **B** as failure — it is the expected, successful outcome (§2a, §6a).

---

## 8. Open questions — RESOLVED (owner ARD review 2026-06-25) → plan FROZEN v1.0

| OQ | Decision |
|---|---|
| **OQ1 — reproduction vs port** | ✅ **Independent reproduction** on TradingWorkbench's PIT pipeline (demonstrates *repeatability*, not just migration). Divergence = evidence to investigate, not a bug. |
| **OQ2 — universe** | ✅ **134-name reproduction first**, then PIT small/mid-cap expansion (a separate research question: *does a bigger universe improve the capability?*). |
| **OQ3 — EDGAR timing** | ✅ **Build native SEC-filing ingestion first** (a reusable first-class capability, not a migration utility) — higher up-front cost, much higher platform value. |
| **OQ4 — consolidation** | ✅ **Co-exist initially** — run both for several months; compare signals / execution / reproducibility / operations; **retire the sibling only after sustained agreement.** Reduces migration risk. |
| **OQ5 — ADR scope** | ✅ **EDGAR-specific ADR now**; a broader Alternative-Data Framework ADR **later**, if/when more sources (8-K/13F/news/macro/options) justify it. |

> **Frozen for execution.** §1 (the EDGAR-specific ADR + the SEC-Filing ingestion + PIT Event Store) begins after tonight's post-close rebuild. The pre-registration above is the contract; parameter changes are prohibited until faithful reproduction completes (§1 rule).
