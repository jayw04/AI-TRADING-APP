# SEC-001 V3 — Pre-Crawl Classification-Coverage Freeze v1.0

**Status:** **SIGNED AND SEALED 2026-08-23 (owner).** The three numeric fields carry frozen values (§3), the earliest-qualifying-start rule is added (§3), and the `excluded_low` treatment is expressly approved (§2). Sealed **before** any new coverage measurement or crawl result was inspected — that ordering is the control this document exists to provide.
**Discharges:** rider item 3 of `SEC001_V3_SectorClassification_Disposition_Ruling_v1_0.md`, and the §10.1 window-gate consequence that rider exposed.
**Governing design:** `TradingWorkbench_SEC001_V3_Design_Implementation_v0_3.md` (§5.1a, §5.1b, §9.4, §10.1, §10.4)
**Date:** 2026-08-23 · **Authority:** **owner — signed 2026-08-23**

---

## 0. Why this exists, and why now

Rider item 3 pre-authorizes shortening the §9.4 evaluation period if the reconstructed classification spine cannot cover it — on the grounds that coverage is not performance data and no economic outcome has been observed. That authorization is only safe while the acceptance rule is fixed **in advance**. Once a coverage table has been looked at, any threshold chosen is a threshold chosen with knowledge of which start dates survive, and the distinction between "forced by data" and "selected" is gone.

Two things must therefore be frozen before the crawl runs: **what counts as sufficient coverage**, and **what happens to the §10.1 window gate if the period moves**. Both are settled below.

---

## 1. Ruling — window regeneration *(owner, adopted verbatim)*

> If the evaluation period must be re-frozen because the precommitted classification-coverage gate fails, regenerate exactly five walk-forward windows over the re-frozen evaluation span using the same deterministic V2 window-construction helper. The §10.1 gate remains **≥4 of 5 positive net-return windows**. No window boundary may be selected, moved, or discarded based on return, Sharpe, drawdown, sector performance, or any other economic result.

**Rationale of record.** Re-cutting five windows preserves the original 4/5 regime-diversification requirement and changes only the dates forced by data availability. Alternatives that mutate the gate itself — 3-of-3, 3-of-4 — were considered and **declined**: they weaken the diversification requirement precisely when coverage has already shortened the history, which is when it matters most. §9.4 already records that the five windows come from the V2 helper rather than hand-selected periods, so regeneration is a re-application of an existing deterministic rule, not a new construction.

---

## 2. What "resolved" means — the measurement definition

A name in the PIT-200 at rebalance session `t` is **classification-resolved** if and only if **all four** hold:

1. **Identity** — `FactorDataStore.permaticker_asof(ticker, t)` returns non-`None` (shipped capability, PR #542 / `PERMATICKER_EFFECTIVE_INTERVAL_V1`; it fails closed by design, so an unresolved symbol is an honest miss, not a guess).
2. **Crosswalk** — that permaticker maps to a CIK whose crosswalk row is effective at `t`.
3. **PIT SIC** — at least one SIC observation for that CIK with `accepted_utc <= close t`, resolving under the frozen resolver without `SECTOR_EFFECTIVE_DATE_CONFLICT`.
4. **Mapping** — the resolved SIC falls inside a `sic_mapping` row covering it and effective at `t`, whose `review_status` is **not** `excluded_low`.

Any name failing any clause is `sector_unclassified` and is excluded from every sector's score and breadth, with reason, per §5.1a. **`excluded_low` mapping rows count as unresolved** — deliberately: a low-confidence mapping is not classification, and letting it pass silently would inflate coverage with the weakest rows in the countersigned table. **Expressly approved by the owner at seal (2026-08-23):** sector classification is load-bearing — it determines sector score, breadth and representability — so weak classifications must not inflate the apparent coverage statistic.

Per-rebalance coverage is `R(t) = resolved names / factor-valid PIT-200 names at t`.

---

## 3. The coverage gate — structure frozen here, values frozen by the owner

| Field | Meaning | Value |
|---|---|---|
| `θ_name` | Minimum per-rebalance resolved fraction `R(t)` for that rebalance to count as covered | **0.95** — at least **190 of 200** names classification-resolved at every rebalance |
| `θ_window` | Minimum fraction of rebalances within a window that must meet `θ_name` for the window to be **coverage-admissible** | **0.95** — at least 95% of the window's scheduled rebalances meet `θ_name` |
| `θ_span_min` | Minimum admissible evaluation span, in years, below which the program STOPS rather than shortens further | **20 years** — a start later than **2006-06-12** is a STOP for insufficient classification history |

**Decision rule, applied mechanically once and only once:**

1. Measure `R(t)` at every weekly rebalance session across 2000-01-01 → 2026-06-12.
2. The evaluation period is the **longest contiguous span ending 2026-06-12** all of whose regenerated windows are coverage-admissible. **The start date may only move forward.** Interior spans may never be excised, and the end date is fixed — this is what prevents coverage from becoming a period-selection instrument.
   **Earliest-qualifying-start rule *(owner, added at seal)*:** if the original 2000-01-01 start fails the frozen coverage criteria, advance the start date using **coverage information only** and select the **earliest** start date for which the resulting contiguous span satisfies `θ_name`, `θ_window` and `θ_span_min`. **No later qualifying start may be preferred because it has higher coverage, or for any economic reason.** This closes the residual degree of freedom: several forward start dates may all qualify, and without this rule someone could later select among them.
3. If that span is shorter than `θ_span_min`, the outcome is **STOP / REDESIGN** under §10.3. A span too thin to evaluate is a stop, never a relaxation of `θ_name`, `θ_window`, or the 4-of-5 gate.
4. Regenerate exactly five windows over the surviving span with the V2 helper (§1), and seal.

**No value in this section may be revised after any coverage table has been inspected.** If the frozen values later look wrong, that is a finding for a successor design decision — not an in-flight adjustment.


### 3.1 Rationale of record *(owner, at seal 2026-08-23)*

**Why 0.95 name coverage.** 95% permits at most 10 unresolved names out of 200 at a rebalance. Ten is already enough to affect one or more sector means, or to move a sector across the representability boundary. Allowing 10% missing would permit 20 names — too permissive for the strategy's grouping variable.

**Why 0.95 window coverage.** It prevents a window qualifying merely because its *average* coverage looks acceptable. It permits occasional isolated historical gaps while requiring classification integrity through essentially the entire regime.

**Why a 20-year floor.** Deliberately stricter than a generic "long enough" rule. A 15-year floor could move the start into 2011 and discard both the dot-com aftermath and the 2008 financial crisis. With **drawdown explicitly part of the §10.1 promotion gate**, letting the coverage rule remove the principal severe historical stress regime would weaken the validation materially. Twenty years keeps roughly four years per regenerated window and preserves the 2008 regime if the start has to move at all.

**Set on evidence quality, not on the current dataset.** The presently held spine begins only in 2010 and therefore cannot satisfy the original frozen period without rebuilding — §5.1b records that the first ten years are entirely uncovered and that the spine cannot serve §9.4 as-is. That is precisely why these thresholds are set by what the evidence must be worth, rather than chosen to accommodate the data currently in hand.

---

## 4. Anti-peek controls

- This document is committed and pushed **before** the crawl is started. Its commit SHA is the ordering evidence; the crawl's own evidence record cites it.
- The coverage measurement tool emits **coverage statistics only** — resolved/unresolved counts, per-rebalance and per-window. It computes no return, no Sharpe, no drawdown, and no sector-level economic quantity. This is a mechanical guarantee of the "coverage is not performance data" premise, not an instruction to be careful.
- No Factor Lab simulation of any arm — V3-RC, the V2 structural reference, or the equal-weight control — may run until the coverage decision is sealed under §3.
- The authoritative measurement is the governed artifact per rider item 2. The §5.1b laptop figures are directional context and are **not** admissible input to this gate.

---

## 5. Consequences recorded

- **Trial ledger (§10.4).** A coverage-forced re-freeze does **not** open a new trial. V3-RC remains trial #1: no economic outcome has been observed, and the candidate's mechanism is unchanged. The ledger entry records the re-freeze and the reason.
- **Rider item 1 (V2 reference recompute).** The recomputed SEC-001 V2 pure-baskets reference must be computed over the **same final** evaluation period and the same five regenerated windows, so the §10.1 relative gates compare like with like.
- **Nothing else reopens.** Signal (252/21), K=3, the 10% cap, `N_min = 4`, the §10.1 thresholds, and the §9.4 cost model (10 bps base / 25 bps stress, one-way portfolio turnover) are untouched by this document.
- **§9.4 supersession.** If the gate fires, the re-frozen period and its five regenerated windows supersede the §9.4 dates; if it does not fire, §9.4 stands exactly as written.

---

## 6. Definition of Done for this freeze

- [x] `θ_name`, `θ_window`, `θ_span_min` carry owner-set values — **0.95 / 0.95 / 20 years**, sealed 2026-08-23.
- [x] Document signed and committed; **the commit that seals this document is the pre-crawl ordering evidence**, cited by the capture and measurement records that follow it.
- [ ] Only then: the two registered crawl changes (20-F/40-F forms; extend to 2000-01-01) and the crawl itself.

---

*Owner signature freezes the three numeric fields and the §1 window ruling. The §1 ruling is already owner-authored and is reproduced here verbatim so the freeze is self-contained.*
