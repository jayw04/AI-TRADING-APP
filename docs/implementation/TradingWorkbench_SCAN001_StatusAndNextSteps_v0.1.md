# SCAN-001 — Status & Next Steps (consolidated, for review)

| Field | Value |
|---|---|
| Document | Status + handoff snapshot (not a plan/pre-registration) |
| Date | 2026-06-23 |
| Scope | The full SCAN-001 arc this session: Confidence research (v0.4–v0.5) + the premarket-data gate (A–D) |
| Purpose | One place to review *what is done* and *what is next*, with PR/evidence pointers |

> **One line.** SCAN-001's **Discovery Lab v1.0** is research-complete — Selection (v0.2) · Operating Envelope
> (v0.3) · **Discovery Confidence (v0.5, accepted)** — and the **Production Validation Gate** (premarket instance;
> the L3→L4 prerequisite) is **built end-to-end (A–D)**. What remains is **merging the open PRs**, **~40 days of
> forward data accrual**, and a **rebuild-gated activation** — no new research or building is outstanding.

> **Naming (folds the review).** What was the "Premarket-Data Gate" is better understood as the **Production
> Validation Gate** — *validate that a capability works in its intended production environment before promotion.*
> Premarket gappers are the **first instance**; later capabilities get sibling gates (Options / Macro / ETF
> Validation Gates). The code modules stay `premarket_*` (they are the premarket instance); the **concept** is
> Production Validation. The gate has two logical phases: **Phase A — Technical Validation** (data → adapter →
> scanner → persistence; increments A, B, C-persist) and **Phase B — Scientific Validation** (realized outcome →
> evidence → bootstrap → verdict; increments C-backfill, D).

## 0. Program timeline & the Capability Promotion Pipeline

**SCAN-001 in one picture (2026):**

```
 v0.1          v0.2         v0.3              v0.4         v0.5          Production        L4
 Discovery  →  Validation → Operating      → Confidence → Confidence  → Validation Gate → Production-
 (prototype)   (de-taut.)   Envelope         REJECTED     ACCEPTED       (premarket,       Ready
                            (regime-robust)  (ATR-blended)(ATR-decoupled) forward)          → L5 Continuous
                                                                                              Evidence
   L1            L2           L3                — (no maturity change) —    gate → L4         L5
```

**Capability Promotion Pipeline (L0–L5) — platform-wide, not just Discovery Lab** (the review's framing; every
capability — Discovery *and* Factor Lab — travels the same ladder):

| Stage | Meaning | SCAN-001 |
|---|---|---|
| **L0** | Concept | — |
| **L1** | Prototype | v0.1 |
| **L2** | Validated | v0.2 |
| **L3** | Operating Envelope defined | v0.3 (current) |
| **L4** | Production-Ready | **on the Production Validation Gate passing** (TRANSFERS verdict) |
| **L5** | Continuously Verified | after deployment (continuous evidence) |

**Discovery Lab v1.0 — FROZEN on gate pass.** With Selection (v0.2) · Operating Envelope (v0.3) · Discovery
Confidence (v0.5) · Production Validation Gate (A–D) · Continuous Evidence → **Evidence Dashboard** (`/evidence`,
the human-readable surface, so people can *see* the evidence), Discovery Lab is a **complete subsystem**. The
owner directive holds: **no SCAN v0.6, no new Discovery concepts** — freeze it and move to repeatability (§4).

*Framing (review): **Evidence Engineering** is the umbrella over all of this —
`Evidence Engineering → Research Program → Production Validation → Capability Promotion`. The pipeline below is
the promotion mechanism within that umbrella; it is **platform-wide**, not Discovery-specific.*

---

## 0a. Platform maturity (where the whole platform stands — for execs / investors / partners)

A platform-level companion to the per-capability pipeline above: an at-a-glance read of the *whole* system, not
just one research program.

| Platform area | Status |
|---|---|
| **Evidence Engineering** (the methodology / the IP) | **Mature** — pre-registration → evidence → governance → promotion → continuous evidence, demonstrated end-to-end |
| **Discovery Lab** | **L4-pending** — research-complete (v0.2–v0.5); Production Validation Gate built, accruing |
| **Factor Lab** | **In progress** — MOM-001 live (paper); SEC-001 / LOW-001 diversifiers; MF-001 inconclusive; TREND-001 planned |
| **Research / Capability Registry** | **Mature** — programs + capabilities (CAP-001…013) + outcome taxonomy + dependency graph |
| **Governance** (pre-reg, promotion gates, stopping rule) | **Mature** |
| **Continuous Evidence** | **Operational** — live paper books + weekly live-evidence refresh |
| **Product UX / Dashboards** | **Early** — `/evidence` dashboard shipped; Candidate Report Discovery-Confidence overlay pending |
| **Commercial packaging** (whitepaper / patent / SaaS) | **Planned** — Phase 3 (§4a) |

*This is the "where is the platform as a whole" view the review asked for — it complements, not replaces, the
per-capability L0–L5 pipeline.*

---

## 1. Completed this session

### 1a. Confidence research (the v0.4 → v0.5 arc)

| Version | Question | Verdict | Evidence | PR |
|---|---|---|---|---|
| **v0.4 Confidence Model** | Does the per-candidate confidence predict expansion `E`? | **CONFIDENCE-UNINFORMATIVE** — confidence (ATR-blended) is *inverse* to `E` (high−low −0.45). A pre-registered negative. | `evidence/scan_001_candidate_engine_v0_4/` | **#236** (open) |
| **v0.5 De-Tautologized Confidence** | Does an *ATR-decoupled* confidence (Gap+RVOL only) predict a de-tautologized outcome? | **DECOUPLED-CALIBRATED — accepted** — removing ATR *flipped* the sign (high−low `E` **−0.45 → +0.89**, CI-sep, both cuts); 3/3 ATR bands on `CM`; lifts the book with top-K ATR = flat (decoupled). | `evidence/scan_001_candidate_engine_v0_5/` | **#237** (open, on #236) |

**Lesson (reusable IP):** *ATR belongs in selection, not in confidence.* The platform **rejected two confidence
models before accepting one** — the arc is the asset. This **completes Discovery Lab v1.0**; the confidence
research line is **closed** (promote-or-close — no v0.6). Capability Maturity stays **L3**.

Artifacts: plans `..._Plan_v0.4.md` (v1.1) / `..._Plan_v0.5.md` (v1.1); results `..._Results_v0.4.md` /
`..._Results_v0.5.md`; registry → **v0.13**; whitepaper drop-in `Whitepaper_DropIn_ConfidenceModel_v0.1.md`
(v0.2, the full reject→diagnose→redesign→accept arc + Scientific Self-Correction subsection).

### 1b. Premarket-data gate (the L3→L4 prerequisite) — all four increments built

Pre-registration: `..._PremarketDataGate_Plan_v0.1.md`. Two hard realities it is built around: **no historical
premarket store** (forward-only study) and the **gappers-vs-liquid universe mismatch** (the gate tests whether
the edge *transfers*). Owner-frozen: test the **gappers universe as-is**; **fix+merge #221 first**.

| Increment | What | Code | PR |
|---|---|---|---|
| Data source | Read-only premarket gappers panel (Yahoo gainers + catalyst) | `services/premarket_gappers.py` | **#221 MERGED** |
| **(A)** Adapter | Pure: gapper row + store features → engine panel (real gap, RVOL proxy, store ATR) | `factor_data/premarket_adapter.py` | **#238 MERGED** |
| **(B)** Live scan | Read gappers → store join → panel → `select_candidates` → advisory report; fail-soft; §0b funnel | `services/premarket_scan.py` | **#238 MERGED** |
| **(C)** Accumulator — persist | Persist each day's candidate set + eligible field to dated JSON (outcomes `pending`) — Option 3 | `services/premarket_evidence.py` | **#239** (open) |
| Decision | Realized-outcome source = **Alpaca** (existing dep, not a new feed) | `docs/adr/0024-…` | **#240** (open, **Accepted**) |
| **(C)** Accumulator — back-fill | Realized `E`/`CM` per candidate + eligible baseline + candidate-vs-field edge + coverage; thin Alpaca read | `services/premarket_outcomes.py` | **#241** (open, on #239) |
| **(D)** Verdict | v0.2 bootstrap on daily `edge_E` → INSUFFICIENT / TRANSFERS / DOES-NOT-TRANSFER | `services/premarket_verdict.py` | **#241** (open, on #239) |

All read-only · advisory · no order path · no LLM. ~58 gate tests; ruff(CI-scope)/mypy clean.

---

## 2. Open PRs & merge order

| PR | Title | Base | State |
|---|---|---|---|
| **#236** | v0.4 Confidence Model (negative) | `main` | open, CI green |
| **#237** | v0.5 De-Tautologized Confidence (accepted) | #236 | open, CI green |
| **#239** | Gate (C) accumulator persist / Option 3 | `main` | open |
| **#241** | Gate (C) back-fill + (D) verdict | #239 | open |
| **#240** | ADR 0024 — realized-outcome feed (Accepted) | `main` | open |

**Merge order:**
1. **Confidence:** merge **#236 → #237** (stacked; #237 retargets to main after #236).
2. **Gate:** merge **#239 → #241** (stacked; #241 retargets to main after #239).
3. **#240** (ADR) is independent — merge any time.

(Each honors the ≥1 h walk-away; all are docs + read-only research/infra, no order path.)

---

## 3. Remaining tasks (no new research/build)

1. **Merge the five open PRs** (order above), after walk-away.
2. **Forward accrual** — the gate verdict is **INSUFFICIENT** until **~40 back-filled scan days** accrue
   (ADR 0014: partial forward data is not edge evidence). This is *elapsed time*, not work.
3. **Activation — ✅ IMPLEMENTED 2026-06-25 (PR pending; takes effect on the next backend rebuild).**
   Two read-only/advisory cron jobs are wired into the `WorkbenchScheduler` (already `America/New_York`,
   so the hours are ET) in `app/lifespan.py`, guarded by the read-only `factor_store` (skipped + logged
   `premarket_gate_disabled_no_factor_store` when absent), with a durable runtime evidence dir
   (`settings.premarket_gate_evidence_dir = data/premarket_gate_evidence`, gitignored, created on first write):
   - `premarket_gate_scan` — **mon–fri 09:25 ET** → `app/jobs/premarket_gate.run_premarket_scan_job` →
     `record_premarket_scan` (live scan + persist today's candidate set + eligible field).
   - `premarket_gate_backfill` — **mon–fri 16:30 ET** → `run_premarket_backfill_job` → `backfill_evidence`
     (attach realized outcomes; a no-scan day is a clean no-op).
   - Both are fail-soft (`logger.exception` + continue; never disturb the scheduler) and off the order path.
     Same rebuild-gated pattern as #221 (the `app/` image drifts from main until rebuilt). 5 job tests +
     16 gate-service tests green; ruff/mypy clean.
   - ⚠ Operational dependency: the scan reads `premarket_gappers_<date>.json` from `settings.premarket_gappers_dir`
     (the sibling `claude-trading-view` scanner, mounted read-only). No gappers file ⇒ 0 candidates (fail-soft),
     so that scanner must be producing files for accrual to be meaningful.
4. **Run the verdict** — once the window accrues, `run_gate_verdict(dir)` → the L4 recommendation
   (TRANSFERS → recommend L4, owner-gated; DOES-NOT-TRANSFER → documented boundary).
5. **Optional product follow-on** — wire the v0.5 **Discovery Confidence** into the live
   Candidate Report's confidence field (a one-line overlay, pre-registered OQ4; separate product PR).

---

## 4. Next-direction options (post-gate) — owner's call

The latest registry review recommended **demonstrating repeatability over deepening SCAN**. Candidate threads:

- **A — SEC-001 / LOW-001 production** *(reviewer's priority 3–4)*: take an already-validated diversifier book
  to paper, proving the platform's lifecycle is repeatable across programs. *Strongest "it's a platform" signal.*
- **B — Candidate Report UI**: surface "Discovery Confidence 0.82" on the Opportunities/Discovery page (consumes
  v0.5). Small, customer-facing.
- **C — Registry split** *(reviewer suggestion)*: split the growing registry into four permanent docs (Research
  Registry · Capability Registry · Architecture · Research History/Knowledge Graph). Maintainability/scaling.
- **D — TREND-001**: the last chartered Factor-Lab program (reviewer: only *after* the above).

**Recommendation:** land the open PRs first; then **A** (repeatability) is the highest-leverage next thread,
with **B** as a quick win. **Not** recommended: extending SCAN (v0.6+) — the program is intentionally frozen.

### 4a. The strategic arc (review framing) — feature expansion → platform consolidation

The review's three-phase recommendation, which the threads above serve:

1. **Phase 1 — Freeze Discovery Lab v1.0** (on the gate passing): no SCAN v0.6, no new Discovery concepts; treat
   it as a stable platform capability.
2. **Phase 2 — Demonstrate repeatability**: promote **SEC-001 → LOW-001 → TREND-001** through the *same* Evidence
   Engineering lifecycle without changing the methodology (proving it's a platform, not a one-off).
3. **Phase 3 — Commercialization**: shift effort to UX, dashboards, APIs, docs, the whitepaper, patent filings,
   SaaS packaging — where the commercial value is created.

The lifecycle itself (hypothesis → pre-register → detect/correct artifacts → validate → operating envelope →
production-environment validation → gated promotion → continuous evidence) is now mature enough to be the
**platform-wide standard** — the review's view (and mine) that *this methodology, not any single strategy, is
TradingWorkbench's most valuable IP.*

### 4b. Named follow-ons (review — captured, deliberately NOT built now)

The reviewer's own guidance: *spend little further effort refining SCAN docs; the ROI is in completing the gate,
demonstrating repeatability, and reflecting these concepts in the whitepaper/patent.* So these are **named, not
built**:

- **Whitepaper figures** — the canonical Discovery workflow (`Discovery Lab → Selection → Confidence → Operating
  Envelope → Production Validation → Continuous Evidence`) **and** the capability lifecycle (`Idea → Hypothesis →
  Research → Validation → Promotion → Continuous Evidence → Retirement` — capabilities evolve or die). Drop-ins
  sibling to `Whitepaper_DropIn_ConfidenceModel_v0.1.md`.
- **Capability Registry split** — when the registry next grows (the reviewer's "~next month"), split into
  Research Registry · Capability Registry · Architecture · Research History/Knowledge Graph.
- **Research Programs hierarchy** — surface `Research Programs → {Discovery Lab · Factor Lab · (future) Risk Lab ·
  Execution Lab}` in the architecture docs.
- **ADR 0024 — `RealizedOutcomeProvider` interface** — generalize the realized-outcome source to a provider
  abstraction (Alpaca today; Polygon / Databento / IBKR later); fits ADR 0024's existing re-eval triggers.

---

## 5. Honest caveats carried forward

- Gate verdict is **forward** — no result yet; INSUFFICIENT by design until accrual.
- **Coverage risk** (ADR 0024 re-eval trigger): if many gappers come back `uncovered` from Alpaca, the gate's
  sample is biased — reported as a first-class number, revisit the source if low.
- **RVOL is a premarket-vs-daily proxy** in the adapter (a true premarket-RVOL baseline doesn't exist yet).
- Survivorship-biased universe throughout — effects read as relative.
- Local config files (`vite.config.ts`, `docker-compose.yml`, `start-claude.bat`) remain modified in the working
  tree (long-standing local edits; **not** part of any PR).
