# CONGRESS-001 — Pre-Registration & Study Plan

| Field | Value |
|---|---|
| Document version | **v0.2** (folds the owner review, 9.3→9.8: Purchase-only primary, date-clustered bootstrap, cluster-level materiality, exact entry timing, amendment PIT handling, short-side caveat, BH-FDR rule. Supersedes v0.1's signed-pooled primary + pooled bootstrap.) |
| Date | 2026-07-07 |
| Program ID | **CONGRESS-001** (EAD's second event-driven research program; DCAP-007 / Quiver **Congressional Trading**) |
| Governing ADR | **0037** (EAD governance) — inherits the matched-control benchmark gate (§3.2), bounded testing, and the pre-register-before-run discipline |
| Status | **Pre-registered (owner-reviewed 9.8/10 — approved to build; run once after ingest).** The verdict is computed **once, on the complete pull**, after the deploy gate (client + event type + ingest) clears. This doc fixes the hypothesis, universe, method, and thresholds so the verdict cannot be reverse-engineered from the data. |
| Related | **GOVCONTRACT-001** (the sibling program whose methodology + matched-control engine this reuses wholesale); INSIDER-001 (the *beta-not-alpha* rejection that motivates the matched-control gate); ADR 0037 §2.4 (licensing — internal R&D only), §3.2 (matched-benchmark) |

## 0. The discipline (why this doc exists)

"Congress beats the market" is the most-cited alpha claim in retail finance — and therefore the most likely to be **sector/size beta wearing an alpha costume** (congresspeople disproportionately hold large-cap tech, which trended for a decade). This program exists to answer one question honestly: **after controlling for sector, size, liquidity, and momentum, does a disclosed congressional trade predict *residual* drift in the direction traded?** The pre-registration locks the test so a null result can't be re-tuned into a positive one, and a positive result can't be reverse-engineered from the data.

## 0.2 Locked pre-registration (v0.1) — the authoritative parameters

**Calibration parameters** (fixed model assumptions; **NOT adjusted** unless the study terminates *Insufficient Evidence*):

| Parameter | Locked value | Basis |
|---|---|---|
| **Primary direction** | **PURCHASE-only long** (per owner review). `Sale`-only + Signed-pooled = **descriptive diagnostics**, not the verdict. | Congressional *purchases* plausibly express positive information; *sales* are often liquidity/tax/rebalancing/divestment-driven — not an assumed short-alpha signal. Test the most realistic tradable signal first; don't turn sales into shorts before that has its own evidence (§8). |
| Entry anchor (exact) | Disclosure is public on **`ReportDate`**; entry = **the first trading day strictly after `ReportDate`** (if `ReportDate` is itself a trading day, entry is the *next* trading day; if not, the first trading day after). **Entry price = the close of the entry date.** | ⭐ The disclosure date is **directly observable** (unlike gov-contracts → no lag to calibrate). Never enter on `TransactionDate` (look-ahead into non-public info). Weekend/holiday/after-hours safe. **No trade may use market data, factor data, or control-basket membership unavailable as of the entry timestamp.** |
| Materiality (**cluster-level**) | De-overlap FIRST (same ticker + same direction within the hold window → one cluster), **sum the conservative `Range` lower-bounds across the cluster**, then require the **cluster total ≥ $50,000**. | Matches the signal actually tested — a *disclosed congressional buying cluster*, not one person's trade. Five reps buying the same name at $15k each is a material cluster, not five excluded noise trades. Primary floor; sensitivity {$15k, $250k}; **no sweep.** |
| Transaction cost | **10 bps per side** | commission-free venue; conservative spread+slippage for mid-cap liquidity. (Purchase-only primary is a long vs control basket; the sale-side diagnostic carries an explicit borrow-cost caveat, §6/§8.) |

**Decision gates** (pre-registered pass/fail):

| Gate | Threshold |
|---|---|
| Eligible, de-overlapped, **material, benchmarked** purchase events | **Target ≥ 150; Minimum 100. Below 100 ⇒ verdict = "Insufficient Evidence"** (terminate; do NOT lower the size floor to reach it). |
| Primary edge | **date-clustered bootstrap** (by `available_time` date) 95% CI on the **Purchase-only** net matched-control excess return **excludes zero** |
| Multiple testing | Benjamini–Hochberg **FDR ≤ 0.10** across the holding-window family, applied as a one-directional robustness check (§4) |

**Analysis order — PRIMARY → SENSITIVITY → DECISION.** The verdict is computed from the **primary** analysis (Purchase-only, entry = first trading day after `ReportDate`, hold 20 days, cluster size ≥ $50k, cost 10 bps, **date-clustered bootstrap**). **Sensitivity is one-factor-at-a-time** — size floor {$15k, $250k}, cost {20 bps}, holding {5, 10, 60 days} — answering only *"would a reasonable alternative flip the conclusion?"*, never *"which parameter gives the best result?"* Robustness is **one-directional** (can caveat, never upgrade). The decision is recorded **after** the sensitivity checks.

## 1. Hypothesis (pre-registered, single primary)

**H1 (primary):** A materially-sized, disclosed congressional **purchase cluster** predicts **positive residual drift** in the bought security — over a matched-control basket (same sector + market-cap / ADV / 6-month-momentum decile), net of 10 bps/side — with a **date-clustered bootstrap** 95% CI on the mean net excess return that **excludes zero**, over a 20-trading-day hold from the first trading day after `ReportDate`.

**Diagnostics (descriptive, NOT the verdict):** Sale-only excess and Signed-pooled (buys long + sales short) are reported for context (§4/§8), but a congressional *sale* is **not** treated as an assumed short-alpha signal (sales are often liquidity/tax/rebalancing-driven), and short-side results carry a borrow-cost caveat.

**Null (expected prior):** no residual drift — the apparent "edge" is explained by the sector/size/liquidity/momentum profile of the names congresspeople hold (beta-not-alpha, the INSIDER-001 outcome).

**Non-goals:** no multi-hypothesis fishing (§4 windows are robustness checks on H1, not separate hypotheses); no per-representative / per-committee ranking in v1 (a pre-registered *future* refinement, §8, not a v1 verdict); no re-tuning after seeing results.

## 2. Universe & event eligibility

- **Events:** `congress_trade` rows from the Event Store (`source = "quiver"`), **`research_eligible = TRUE`** only (resolved to a security via CAP-024). Direction from `Transaction`: `Purchase` (primary), `Sale`/`Sale (Partial)` (diagnostic); `Exchange` and other non-directional types **excluded**.
- **Entry anchor (exact, §0.2):** `available_time` = the **first trading day strictly after `ReportDate`** (weekend/holiday/after-hours safe); **entry price = the close of that entry date.** Never `TransactionDate`. **No trade may read market data, factor data, or control-basket membership unavailable as of the entry timestamp.**
- **Order of operations — DE-OVERLAP → CLUSTER → MATERIALITY (per owner review):**
  1. **De-overlap / cluster:** collapse all trades of the **same ticker + same direction** whose windows overlap the holding period into **one event** at the earliest `available_time` — a cluster of representatives buying the same name is *one* drift window, not N. Opposite-direction trades on the same ticker in the same window are **both dropped** (ambiguous).
  2. **Cluster materiality:** **sum the conservative `Range` lower-bounds across the cluster**; keep the event only if the **cluster total ≥ $50,000** (primary). This tests a *disclosed congressional buying cluster*, not one person's trade.
- **Liquidity floor:** the security must clear a minimum price + ADV threshold as-of `available_time` (decile computation excludes sub-floor names).
- **Amendments / corrections (PIT integrity):** an amended or late-corrected filing is treated **according to its own public-availability date** — a later amendment does **not** retroactively modify the original event as if the corrected information were known at the original `ReportDate`. Superseded originals are handled by the de-overlap/cluster rule; a materially different amendment landing later is a new event at its own `available_time`.

## 3. Matched-control benchmark (ADR 0037 §3.2 — the load-bearing gate)

For each event, build a control basket as-of `available_time`:
- **Same sector.**
- **Market-cap decile ± 1.**
- **ADV / dollar-liquidity decile ± 1.**
- **6-month momentum decile ± 1.**
- **No same-event-type occurrence** (no `congress_trade` on that name) within the lookback window — controls must be "clean".

**Benchmark return** = equal-weight forward return of the matched controls over the holding window. The program is tested on the **direction-signed** excess: for a *Purchase* event, `event_return − control_return`; for a *Sale* event, `control_return − event_return`. A positive signed excess = the traded direction beat matched peers. **If fewer than 10 controls survive, the event is excluded and flagged** (never benchmarked against a thin basket).

## 4. Holding windows & statistic

- **Primary hold:** **20 trading days** (H1). **Sensitivity (robustness only):** 5 / 10 / 60 trading days.
- **Statistic:** mean **Purchase-only** net excess return; CI via a **mandatory date-clustered bootstrap — resample by `available_time` DATE, not pooled event-level.** Rationale (per owner review): congressional reports cluster — multiple trades land on the same disclosure date, in the same market regime, often in correlated names — so pooled per-event resampling **overstates confidence**, exactly the false positive the RNG day-clustered bootstrap caught. Reuse the platform's seeded bootstrap engine at the date-cluster level.
- **Primary approval requires ALL of:** (1) the **20-day** primary date-clustered CI **excludes zero**; (2) **BH-FDR (q ≤ 0.10) across the {5,10,20,60} holding family does not contradict robustness**; (3) sensitivity may **downgrade or caveat, never upgrade** — a 5-day or 60-day sensitivity win can **not** rescue a failed 20-day primary.
- **Decomposition (descriptive, NOT a separate verdict):** report **Sale-only** and **Signed-pooled** date-clustered excess for context — describes which side (if any) carries signal, without creating new hypotheses. Sale-side is research evidence only until shortability/borrow costs are modeled (§6/§8).

## 5. Sample-size floor (pre-registered kill)

- **Minimum:** **≥ 100** benchmarked **purchase clusters** (de-overlapped, ≥ $50k cluster, liquidity-passing, ≥10 matched controls). **Preferred:** 300+ / 50+ unique tickers.
- **Kill:** too few mapped / liquid / material purchase clusters ⇒ **Insufficient Evidence** (a recordable non-verdict; do NOT weaken the size floor or the ≥10-control rule to reach 100). Coverage is a **data/compute** problem (broaden the small-cap universe + run on separate compute, per GOVCONTRACT-001's DCAP-008 lesson), never a threshold problem.

## 6. Cost model (pre-registered)

10 bps per side, charged on the round trip (enter at the **entry-date close**, exit at entry + hold close). Sensitivity at 20 bps. No leverage. The **primary (Purchase-only)** is a long vs the equal-weight control basket. **Short-side caveat:** the Sale-only / Signed-pooled diagnostics assume a symmetric 10 bps, which **understates** reality — shorts face borrow cost, locate constraints, and hard-to-borrow names. **Sale-side results are research evidence only until shortability + borrow costs are modeled**; they do not support a tradable short claim.

## 7. Kill criteria (checked before / with the run)

- **Licensing (ADR 0037 §2.4):** Quiver Hobbyist/Trader = "No Commercial Use Rights" ⇒ **internal R&D only**, no customer-facing surface. (Verified: the key pulls `congresstrading`.)
- **PIT integrity:** if `ReportDate` cannot be trusted as the public-disclosure date for a meaningful fraction of rows, the entry anchor is invalid ⇒ terminate and re-scope. (Spot-check `ReportDate ≥ TransactionDate` and the lag distribution at Phase-0-run.)
- **Identity resolution:** trades that don't resolve to a security via CAP-024 (ticker/issuer ambiguity) are dropped, not guessed.
- **Data completeness (ADR 0033):** the factor universe must be broad enough (small-cap-inclusive) that material small-cap trades find ≥10 same-decile controls — reuse the DCAP-008 deepened store + the `--n-universe` large pool on separate compute.

## 8. Direction handling — the CONGRESS-specific design

Congressional trades are **two-sided**, but the two sides are **not symmetric** in information content. Locked design (per owner review):
1. **Purchase-only primary** (§1): the verdict is on the Purchase-cluster long net excess — the most realistic first tradable signal; purchases plausibly express positive information.
2. **Sale-only + Signed-pooled = diagnostics, not verdicts:** sales are often liquidity/tax/rebalancing/divestment-driven, so a sale is **not** an assumed short-alpha signal — reported for context only.
3. **Short-side caveat:** Sale-side / Signed-pooled results are **research evidence**, not an executable long-short strategy, because sale-side shortability and borrow costs are not modeled.
4. **Symmetric matching:** the control basket + decile logic is identical regardless of direction; only the excess sign differs.
5. **Ambiguity drop:** same ticker both bought and sold within one holding window → dropped (no coherent direction).
6. **Future refinements (pre-registered OUT of v1, to avoid fishing):** per-committee relevance (does an Energy-committee member's energy-sector buy carry more signal?), per-representative track record, and chamber (House vs Senate) splits — each a *separate future program* with its own pre-registration, never a v1 subgroup search.

## 9. Reuse (what CONGRESS-001 inherits from GOVCONTRACT-001)

- **Matched-control engine** (`app/altdata/matched_control.py`) — unchanged; only the event source + the signed excess differ.
- **PIT Event Store** (ADR 0027) — a new `congress_trade` event type, **no second store** (ADR 0037).
- **CAP-024 Security Master** — issuer/ticker resolution.
- **The study runner** (`scripts/run_govcontract001.py` → a `run_congress001.py` sibling) + the batched momentum + the **throwaway-32 GB-EC2 compute recipe** (the live box OOMs on the broad universe).
- **The ≥100-gate / bootstrap-CI / BH-FDR verdict tree.**

## 10. Build sequence (after this plan is accepted)

1. Extend the Quiver client: `congresstrading_history(ticker)` / `congresstrading_live()`.
2. `congress_trade` normalizer + ingest (map `TransactionDate`→event_date, `ReportDate`→disclosure basis for the exact entry rule, `Transaction`→direction, `Range` lower-bound→size; CAP-024 resolution). Spot-check `ReportDate ≥ TransactionDate` + the lag distribution + amendment handling at Phase-0-run.
3. `run_congress001.py` — reuse the matched-control engine + verdict tree; add **Purchase-cluster de-overlap → cluster-materiality**, the **exact entry rule**, **direction-signed excess**, and the **date-clustered bootstrap** (by `available_time` date). Purchase-only primary; Sale-only + Signed-pooled as diagnostics.
4. Ingest → **run once on separate compute** (the throwaway-32 GB-EC2 recipe; the broad small-cap universe OOMs the live box) → **registered verdict**.
