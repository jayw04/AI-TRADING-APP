# GOVCONTRACT-001 — Pre-Registration & Study Plan

| Field | Value |
|---|---|
| Document version | **v0.2** (pre-registration — locks the calibration parameters + decision gates before any results are seen; supersedes the v0.1 placeholders in §2/§4/§5/§6) |
| Date | 2026-07-05 |
| Program ID | **GOVCONTRACT-001** (EAD's first event-driven research program; DCAP-007 / Quiver Government Contracts) |
| Governing ADR | **0037** (EAD governance) — inherits the matched-benchmark gate (§3.2), bounded testing, and the pre-register-before-run discipline |
| Status | **Pre-registered / data-gated.** The verdict must be computed **once, on the complete pull**, after the deploy gate (migration + ingest) and the USAspending cross-check clear. This doc fixes the hypothesis, universe, method, and thresholds so the verdict cannot be reverse-engineered from the data. |
| Related | ADR 0037 §2.6 / §3.2 / §2.6a; INSIDER-001 (`…INSIDER001_InsiderConviction_Plan_v0.1.md`) — the sibling event program whose *beta-not-alpha* rejection motivates the matched-control gate here |

---

## 0. The discipline (why this doc exists)

The registry rejected INSIDER-001's early form because its apparent edge was **beta, not alpha** — a small/mid-cap factor tilt, not residual predictive power. GOVCONTRACT-001 must not repeat that. This pre-registration fixes, **before the data is examined**: the hypothesis, the eligibility rules, the matched-control construction, the holding windows, the statistical test, the sample-size floor, the cost model, the kill criteria, and the verdict tree. A verdict computed under any deviation from this plan is not evidence — it is a new pre-registration.

## 0.2 Locked pre-registration (v0.2) — the authoritative parameters

This section supersedes the v0.1 placeholders. Two kinds of thing, kept deliberately distinct:

**Calibration parameters** (fixed model assumptions; **NOT adjusted** unless the study terminates *Insufficient Evidence*):

| Parameter | Locked value | Basis |
|---|---|---|
| Disclosure lag | **21 trading-calendar days** (`available_time = event_date + 21`) | FPDS reporting (≤3 business days) + USAspending processing (~days–2 weeks); PIT-safe. The USAspending cross-check's ~46-day `Last Modified` is an inflated record-*maintenance* proxy → not used as the primary. |
| Materiality | **award ≥ 0.25% of market cap (as-of `available_time`) AND ≥ $250k absolute** | scales across small/mid/large caps. **Primary threshold — pre-registered; no adjustment unless the study terminates Insufficient Evidence.** No sweep (that would be data dredging). |
| Transaction cost | **10 bps per side** | commission-free venue; conservative spread+slippage for mid-cap liquidity. Charged as a dollar-neutral long-short round trip (4× per side per event). |

**Decision gates** (pre-registered pass/fail):

| Gate | Threshold |
|---|---|
| Eligible, de-overlapped, **material, benchmarked** events | **Target ≥ 150; Minimum 100. Below 100 ⇒ verdict = "Insufficient Evidence"** (the study terminates; do NOT lower materiality to reach it). |
| Primary edge | 95% bootstrap CI on the **net** matched-control excess return **excludes zero** |
| Multiple testing | Benjamini–Hochberg **FDR ≤ 0.10** across the holding-window family |

**Analysis order — PRIMARY → SENSITIVITY → DECISION.** The verdict is computed from the **primary** analysis (lag 21, hold 20 days, cost 10 bps). **Sensitivity is one-factor-at-a-time** over three dimensions — disclosure lag {14, 46}, cost {20 bps}, holding period {5, 10, 60 days} — and answers only *"would a reasonable alternative flip the conclusion?"*, never *"which parameter gives the best result?"* Robustness is **one-directional**: it can confirm or caveat a verdict (a fragile Approved is flagged), but it can never upgrade one — no cherry-picking. The decision is recorded **after** the sensitivity checks. *(The primary objective is robustness across reasonable disclosure assumptions, not optimization of the disclosure lag.)*

## 1. Hypothesis (pre-registered, single primary)

> **H1 (primary):** New federal government-contract awards to public companies predict positive abnormal drift in the awarded company over the following ~20 trading days, *relative to a matched control basket* — i.e. the drift is **not** explained by sector / size / liquidity / momentum exposure.

Direction is pre-committed **long** (awards are positive news). A null or negative excess return is a valid, recordable outcome (Rejected).

**Non-goals:** no multi-hypothesis fishing (the sensitivity windows in §4 are *robustness checks* on H1, not separate hypotheses); no re-tuning after seeing results.

## 2. Universe & event eligibility

- **Events:** `gov_contract_award` events from the Event Store (`source = "quiver"`), **`research_eligible = TRUE`** only (resolved to a security via CAP-024, with a validated `available_time`).
- **Entry anchor:** `available_time = action_date + DISCLOSURE_LAG_DAYS` (PIT-safe; the lag is **calibrated by the USAspending cross-check before the run**, not chosen after). No event enters on `action_date`.
- **Liquidity floor:** the awarded security must clear a minimum price and ADV threshold as-of `available_time` (§3, decile computation excludes sub-floor names).
- **De-overlap:** collapse multiple awards to the same ticker within the holding window into one event (first available_time) — an event study must not double-count an overlapping drift window (the INSIDER-001 de-overlap discipline, CAP-017).
- **Materiality (pre-registered):** an award qualifies only if its `Amount` is ≥ a pre-registered floor relative to the company (to confirm at Phase-0-run; a $10k contract to a $200B contractor is not an event). Placeholder: award amount ≥ 0.1% of market cap **or** ≥ $10M absolute — **confirm/lock before the run.**

## 3. Matched-control benchmark (ADR 0037 §3.2 — the load-bearing gate)

For **each** event stock, select **~20 control securities as-of `available_time`** (never look-ahead):

- Same **GICS sector / industry** (Sharadar sector as the available proxy).
- **Market-cap decile ± 1.**
- **ADV / dollar-liquidity decile ± 1.**
- **6-month momentum decile ± 1.**
- Price **above** the minimum liquidity threshold.
- **No same-event-type occurrence** (no gov-contract award) within the lookback window — controls must be "clean".

**Benchmark return** = equal-weight forward return of the matched controls over the same holding window. The program is tested on **(event-basket return − matched-control-basket return)** = the excess return. **If fewer than 10 controls survive for an event, that event is excluded and flagged** (not benchmarked against a thin basket).

## 4. Holding windows & statistic

- **Primary hold:** **20 trading days** (H1).
- **Sensitivity (robustness only):** 5 / 10 / 60 trading days.
- **Statistic:** mean excess return per event; the **95% bootstrapped (block/seeded) CI on the mean excess return must exclude zero** to claim an effect (reuse the platform's seeded block-bootstrap evidence engine — no new statistic).
- **Multiple testing:** the primary is one test; across the sensitivity windows apply **Benjamini–Hochberg FDR, q ≤ 0.10**, and report which windows survive.
- **Confidence/score fields:** none from the normalizer influence ranking (ADR 0037 Decision 8 — EAD v0 has no score column).

## 5. Sample-size floor (pre-registered kill)

- **Minimum:** **≥ 100** eligible, de-overlapped, liquidity-passing events with ≥ 10 matched controls each.
- **Preferred:** 300+ events / 50+ unique tickers.
- **Kill:** too few mapped / liquid / eligible events to support the test ⇒ **Insufficient Evidence** (a recordable non-verdict; do NOT weaken the gates to reach 100).

## 6. Cost model (pre-registered)

Excess returns are reported **gross and net**. Net applies a pre-registered per-side cost (commission + a conservative spread/slippage assumption for the liquidity tier traded). Locked before the run; an edge that survives gross but dies net is **not** Approved.

## 7. Kill criteria (ADR 0037 §2.6a — checked before/with the run)

Stop and record the pilot outcome if any hold: < 70% of contract rows map confidently; < 2 years usable history; `available_time` unreconstructable; Quiver materially misses USAspending events; duplicate/revision behaviour non-idempotent; sample too small after liquidity filters.

## 8. Verdict tree (pre-registered)

Computed **once** on the complete pull:

- **Approved** — net excess-return 95% CI excludes zero at the 20-day primary, in the hypothesized (positive) direction, **and** survives the matched-control gate (the effect is not sector/size/liquidity/momentum beta), **and** the sample floor is met.
- **Diversifier** — excess return is weak/insignificant on its own but the event-basket return stream has **low/negative correlation** to the existing live books (a portfolio-diversification value), per the platform's diversifier criteria.
- **Rejected** — CI includes zero (no residual alpha over matched controls), or the effect is wrong-signed, or it dies net of cost. (This is the *expected-and-fine* outcome per ADR 0037: "the verdict does not matter; the system maturity does.")
- **Insufficient Evidence** — the §5 floor is not met.

## 9. Evidence Package (verdict-as-data, ADR 0026/0014)

The run emits a structured, reproducible Evidence Package: the pre-registered config (this plan's parameters), the event/control counts, the per-window gross/net excess returns + bootstrap CIs, the FDR table, the correlation-to-live-books table (for the Diversifier branch), the matched-control coverage stats, and the declared verdict — rendered to `docs/implementation/evidence/govcontract_001/`. Determinism: identical inputs ⇒ identical Evidence Package.

## 10. What is data-gated (the run)

This plan + the matched-benchmark engine (built alongside, unit-tested on synthetic data) are offline deliverables. The **run → verdict** is gated on: (a) the deploy gate (migration + ingest on the real store), (b) the USAspending cross-check clearing + calibrating `DISCLOSURE_LAG_DAYS`, and (c) locking the two placeholders above (materiality floor §2, cost model §6). Only then is the verdict computed — once.
