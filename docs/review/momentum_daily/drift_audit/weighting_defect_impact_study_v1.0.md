# momentum-daily — Weighting-Defect Impact Study — Result v1.0

**Date:** 2026-07-22 · **Protocol:** `PREREG_weighting_defect_impact_study_v1.1.md` (RATIFIED 2026-07-22).
**Reproduction gate:** ✅ **PASS** (both variants).

```
PREREGISTERED_ARM_VERDICT:   MATERIALLY_DIFFERENT
PRODUCTION_ARM_VERDICT:      MATERIALLY_DIFFERENT   (measured directly — §7.2, T7 281.35 bps > 250)
```

**The `MATERIALLY_DIFFERENT` verdict is valid for the PREREGISTERED arm**, on five grounds: T7 failed at
2.25× threshold; the effect is persistent and directional; the free-running arm independently failed T7;
trade timing does not explain the difference; and T11 correctly exposed that the preregistered arm violated
its own feasibility assumption.

The preregistered arm differed from production on two rebalances (§5.2), so production sizing was measured
directly by a corrected sensitivity arm rather than inferred. **It returns the same classification**:
T11 = 0 by construction, T7 = **281.3463 bps** — *identical to four decimal places* to the preregistered
arm. The two underfilled sessions fall outside the p95 tail windows entirely, so the correction moved the
governing statistic not at all. **Production equal weighting is `MATERIALLY_DIFFERENT` from the defective
hybrid residual.**

**Consequence under the ratified decision rule:** *"If the verdict changes materially, the equal-weight
variant requires separate validation."* The activation blocker **stands**. Account 4 remains PAUSED, hold
ACTIVE, cooldown NOT STARTED. **This study does not authorize activation and does not recommend clearing
the hold.**

---

## 1. Provenance

| item | value |
|---|---|
| protocol_commit | `54b8ea4` |
| measurement_code_commit — **preregistered arms** (§2–§4) | `377d7af` (reference-loader fix; see §5.1) |
| measurement_code_commit — **production-faithful arm** (§7) | `391055d` (adds the production seam arm) |
| working_tree_clean at execution | **TRUE** for both runs — no cleanliness exception required |
| sep content digest | `d9472dfe40e6bd9997b16895bd44aad709a3f00c8aa8579d7626e05cbd07e2c7` ✓ re-verified fail-closed, matches countersigned census |
| tickers content digest | `2f21b154fa6a4746a8ce4b5aa74d52d31151a65c7462b8544037bcf38d4f22f3` ✓ re-verified |
| window | 2005-01-03 → 2026-06-12, 5,395 sessions |
| execution | laptop, read-only, offline; no EC2, no live account/book/DB |
| `weighting_defect_impact_v1.0.json` (preregistered arms) | 24,207 B · sha256 `41c3119667207c1663c49876860692310fffd921e2c94d0b7bede82c8edcce15` |
| `weighting_defect_impact_execution.log` | 3,324 B · sha256 `d55b92936f3c644ec8a6ea55fa6c44a2904934be4c6a717a8ff1dfa61c336ac6` |
| **`weighting_defect_impact_v1.1.json`** (adds the production-faithful arm; **governing**) | 38,093 B · sha256 `52123c2f0e23f16821741dc9f097eed7d0a6397ad02f0efe94f08524f3447c11` |
| `weighting_defect_impact_v1.1_execution.log` | 5,556 B · sha256 `66b40034cf416269a39fd965994e68bc151f35eb4060cf6d22472088d3385500` |

*Both `*_execution.log` files are excluded by the repo-wide `*.log` ignore rule and are therefore
**SHA-bound here and retained on disk rather than committed** — the same treatment the census gives
`census_execution.log` and the 40 MB/19 MB seam captures. The two `.json` result artifacts **are** committed.*

**Reproduction gate (hard stop, PREREG §2).** Arm A reproduced the committed
`MR_MomentumDaily_Stage4_full.json` endpoints within 1e-9 relative and exactly on `trades` for **both**
variant C (1,539) and variant D (1,378). Tier-2 results are therefore admissible.

---

## 2. GOVERNING RESULT — variant C (graduated regime), trade-date-pinned

### 2.1 Confirmatory gates (Tier 2)

| gate | value | threshold | ratio | |
|---|---|---|---|---|
| T1 annualized volatility \|Δ\| | 9.46 bps | ≤ 25 | 0.38 | PASS |
| T2 rolling 1m median \|Δ\| | 3.78 bps | ≤ 10 | 0.38 | PASS |
| T3 rolling 1m p95 \|Δ\| | 31.93 bps | ≤ 50 | 0.64 | PASS |
| T4 rolling 3m median \|Δ\| | 8.10 bps | ≤ 20 | 0.41 | PASS |
| T5 rolling 3m p95 \|Δ\| | 72.60 bps | ≤ 75 | 0.97 | PASS *(narrow)* |
| T6 rolling 12m median \|Δ\| | 22.22 bps | ≤ 35 | 0.63 | PASS |
| **T7 rolling 12m p95 \|Δ\|** | **281.35 bps** | **≤ 125** | **2.25** | **FAIL** |
| T8 annualized cost \|Δ\| | 0.154 bps | ≤ 10 | 0.02 | PASS |
| T9 max single-rebalance cost \|Δ\| | 0.213 bps | ≤ 2 | 0.11 | PASS |
| T10 trade-date alignment | identical | identical | — | PASS |
| **T11 cap violations (equal arm)** | **2 rebalances** | **0** | — | **FAIL** |
| T13 target/holdings path identical | identical | identical | — | PASS |

**Preregistered-arm verdict: `MATERIALLY_DIFFERENT`** — T7 exceeds **2×** its threshold (ratio 2.25).
Mechanical, per the ratified rule; no composite, no offsetting. Ten passes do not mitigate one failure
above 2×. This is the verdict **for the preregistered arm**; see §7 for the production-faithful arm.

**T5 passed at ratio 0.97** — within 3% of failing. Recorded explicitly rather than reported as a clean
pass. (In the non-governing variant D it *does* fail, at 75.38 bps.)

### 2.2 T12 — persistence (qualitative, and it does not hold)

Equal weighting is **directionally worse, persistently**, not symmetrically noisy:

- **16 of 22 calendar years negative** (equal weight below the defective hybrid); same-sign share 0.73.
- Rolling 12-month differences are positive only **29.2%** of the time; median signed **−13.35 bps**.
- Worst years: 2007 **−171 bps**, 2025 **−148 bps**, 2024 **−89 bps**, 2017 **−85 bps**; largest positive
  2021 **+209 bps**.
- Worst single rolling 12-month difference: **940 bps**.

T12 asked whether any segment shows *"a persistent one-directional effect large enough to contradict
practical equivalence."* A 71%-of-windows one-directional drag with a 940 bps worst case does. **T12 fails
in substance**, independently of T7.

### 2.3 Endpoint metrics — DESCRIPTIVE ONLY (never used to claim threshold success)

| | A: defective hybrid | B: equal (pinned) | Δ (B−A) |
|---|---|---|---|
| CAGR | 16.9150% | 16.6792% | **−23.6 bps** |
| annualized volatility | 38.6541% | 38.7487% | +9.5 bps |
| Sharpe | 0.5965 | 0.5908 | −0.0057 |
| max drawdown | −64.5944% | −64.6416% | −4.7 bps |
| trades | 1,539 | 1,539 | 0 |

---

## 3. Diagnostic — variant C free-running (NOT mixed into the verdict)

Rebalance count 1,542 vs 1,539; trade-date overlap **99.42%**; dates not identical. Rolling 12m p95 259.72
bps (vs 281.35 pinned), Δvol +9.54 bps, Δcost −0.114 bps. **The gate interaction is small and does not
explain the T7 failure** — the free-running arm fails T7 as well. The weighting difference, not trade
timing, drives the divergence.

## 4. NON-GOVERNING regime-free reproduction control — variant D

Reproduction PASS (1,378 trades). Verdict also `MATERIALLY_DIFFERENT`: **T5 FAIL** 75.38 / 75 (ratio
1.005), **T7 FAIL** 304.78 / 125 (ratio 2.44), **T11 FAIL** 2. Endpoints: CAGR 14.7832% → 14.5336%
(−25.0 bps), Sharpe 0.5282 → 0.5235. 16/22 years negative.

**Answer to the control's question** — *did the Stage-3 N=5 hybrid "advantage" consist entirely of
infeasible clamp residual?* **Yes.** The Stage-3 gap (+26.1 bps CAGR, +0.0049 Sharpe) is reproduced here
as +25.0 bps / +0.0047 when the only change is feasible-vs-defective sizing on an identical trade
schedule. The advantage was entirely the residual — and the residual is **not available** to production,
because it is infeasible under the registered 20% cap.

---

## 5. ⚠ Two defects this study surfaced

### 5.1 A fabricated-reference defect in the study's own gate (resolved)

The first run reported reproduction FAIL (~1e-6 relative on all four float metrics, trades matching
exactly). Cause: the gate's reference constants were **hand-typed at full precision from a console echo
that had printed them rounded to six decimals, with the trailing digits invented**. Four of the five
variant-C constants exist in **no artifact in this repository**; the variant-D constants were taken from
the Stage-3 artifact instead of the Stage-4 one. The run had in fact reproduced exactly.

Independently confirmed: the **original unmodified** `backtest_momentum_stage4.py`, re-run today,
reproduces its own committed artifact at **0.000e+00** on every metric of variants A, C and D — no
environmental, library, or data drift. `simulate_arm` was separately verified as an arithmetically
faithful transcription of `stage4::simulate` by normalized line-by-line diff.

Fix (`377d7af`): `load_stage4_reference()` reads endpoints from the committed artifact at runtime,
fail-closed. **The gate behaved correctly — it refused to admit Tier-2 results behind a failed
reproduction check; it merely misattributed the cause.** No Tier-2 result was produced from that run.

Follow-on control: all 31 numeric claims in `weighting_defect_erratum_v1.0.md` were re-derived from source
artifacts by machine — **31/31 reproduce**. See `verify_erratum_claims.py` (re-runnable).

### 5.2 ⚠ OPEN — Arm B is not production sizing on 2 sessions (T11)

**T11 failed for the *equal-weight* arm, which should be impossible — and the reason matters.**

The cap-violating weight is exactly **0.250000 = 1/4**: two rebalances selected only **4** names. The
harness's `weigh(sizing="equal_weight")` applies **no cap**, so it allocated 25% per name. Production's
`_per_name_notional` computes `min(equity/k, equity × 0.20)` — it would cap at 20% and hold the remaining
**20% in cash**.

So on those 2 of 1,539 rebalances, **Arm B is not the portfolio production would hold.** Production is
strictly the more conservative of the two. The PREREG described Arm B as "the unique cap-feasible
fully-invested N=5 portfolio" — an assumption that silently fails whenever fewer than 5 names are
selectable.

**Does it change the verdict?** Almost certainly not: T7 is a 2.25× failure driven by weight differences
across all 1,539 rebalances, and 2 sessions cannot plausibly pull a 12-month p95 tail from 281 bps below
125 bps. But the study cannot claim to measure *production* sizing while Arm B differs from it, however
narrowly. **Correcting this is a protocol amendment and requires owner ratification — it is not applied
here, and re-specifying an arm after seeing results would be post-hoc.**

---

## 6. Conclusion

1. **Reproduction: PASS.** The harness reproduces the governing baseline exactly.
2. **Governing verdict: `MATERIALLY_DIFFERENT`** (T7 at 2.25×; T11 open per §5.2; T12 fails in substance).
3. **Equal weighting does not inherit the validated performance evidence.** Under the ratified rule the
   equal-weight variant **requires separate validation**.
4. **The defect residual was economically real but is unavailable.** Removing it costs ~24 bps CAGR/yr and
   is directionally persistent (16/22 years). The hybrid's small tilt toward lower-volatility names
   produced a genuine, if modest, edge — **which the registered constraint set cannot express**: at N=5
   with a hard 20% cap and full investment, the feasible set is the single uniform point. The constraint
   set, not the sizing code, is what forecloses any tilt. Revisiting it (more names, or a higher cap)
   would be a **new strategy question requiring its own preregistration** — explicitly out of scope here.
5. **Account 4 remains PAUSED**, hold ACTIVE, blocker unchanged, cooldown NOT STARTED.

---

## 7. Protocol deviation 2026-07-22 — POST-HOC PRODUCTION-FAITHFUL CORRECTION

**Status:** ⏳ running at time of writing; §7.2 records the result.

**Not a silent rewrite of the preregistration.** This is a dated protocol deviation, ordered by the owner
after §5.2 showed the preregistered arm departing from production. It is **not a new blind confirmatory
study** — it is a **construct-validity correction**: the preregistered arm did not measure the thing the
activation question is about.

### 7.1 The two arms

| arm | sizing | at k=5 | at k<5 (underfilled) |
|---|---|---|---|
| **B-preregistered** | harness `weigh(equal_weight)`, **uncapped** | 0.20/name, fully invested | **1/k > 0.20** — 25%/name on 4-name days |
| **B-production** | the exact `MomentumDaily._per_name_notional` seam | 0.20/name, fully invested | **0.20/name, remainder stays CASH** |

Held constant: variant-C regime path, Arm-A pinned trade dates, Tier-2 calculations, thresholds. No
re-estimation. The arm **calls the production seam itself** rather than restating its rule, so it cannot
drift from what the order path sizes.

**Disclosed discrepancy between the ruling's shorthand and the seam.** The ruling wrote
`min(gross / selected_count, 0.20)` — a flat 20% cap on the *total-equity* weight. The production seam is
`min(1/k, 0.20) × gross` — the cap **scales with gross**. Identical at k=5; they differ only on the
underfilled sessions at issue (k=4 at gross 0.98: 0.200 vs 0.196). The ruling directed use of "the exact
production `_per_name_notional()` seam", so **the seam governs** and the shorthand is read as descriptive.

### 7.2 Adjudication bands (owner-specified; thresholds unchanged)

| condition | classification |
|---|---|
| T7 > 250 bps | `MATERIALLY_DIFFERENT` |
| 125 < T7 ≤ 250 bps | `MINOR_BUT_MEASURABLE` |
| T7 ≤ 125 bps **and** all other gates pass | per the registered mechanical rule |
| **T11 ≠ 0** | **STOP — implementation defect** (must be zero *by construction*: the seam caps) |

### 7.2.1 RESULT — variant C (GOVERNING): `MATERIALLY_DIFFERENT`

Artifacts: `weighting_defect_impact_v1.1.json` (38,093 B · sha256
`52123c2f0e23f16821741dc9f097eed7d0a6397ad02f0efe94f08524f3447c11`) ·
`weighting_defect_impact_v1.1_execution.log` (5,556 B · sha256
`66b40034cf416269a39fd965994e68bc151f35eb4060cf6d22472088d3385500`) · measurement code `391055d` ·
clean tree · reproduction gate PASS (1,539 trades) · digests re-verified fail-closed.

| gate | production arm | threshold | ratio | |
|---|---|---|---|---|
| T1 volatility \|Δ\| | 9.46 bps | ≤ 25 | 0.38 | PASS |
| T2 rolling 1m median \|Δ\| | 3.83 bps | ≤ 10 | 0.38 | PASS |
| T3 rolling 1m p95 \|Δ\| | 32.05 bps | ≤ 50 | 0.64 | PASS |
| T4 rolling 3m median \|Δ\| | 8.18 bps | ≤ 20 | 0.41 | PASS |
| T5 rolling 3m p95 \|Δ\| | 72.60 bps | ≤ 75 | 0.97 | PASS *(narrow)* |
| T6 rolling 12m median \|Δ\| | 21.76 bps | ≤ 35 | 0.62 | PASS |
| **T7 rolling 12m p95 \|Δ\|** | **281.35 bps** | ≤ 125 | **2.25** | **FAIL** |
| T8 annualized cost \|Δ\| | 0.149 bps | ≤ 10 | 0.01 | PASS |
| T9 max single-rebalance cost \|Δ\| | 0.262 bps | ≤ 2 | 0.13 | PASS |
| T10 trade-date alignment | identical | identical | — | PASS |
| **T11 cap violations** | **0** | 0 | — | **PASS — zero by construction** |
| T13 target/holdings path | identical | identical | — | PASS |

**T7 = 281.3463 bps > 250 ⟹ `MATERIALLY_DIFFERENT`.** T11 = 0 confirms the arm is genuinely calling the
production seam (the STOP condition did not trigger).

**The correction changed the governing statistic by nothing at all.** Preregistered T7 281.3463 bps →
production T7 **281.3463 bps**, identical to four decimals: the two underfilled rebalances do not fall
inside any of the p95-tail 12-month windows. The inference recorded in §5.2 is now a measurement.

Persistence is likewise unchanged: rolling 12-month differences positive only **29.9%** of the time,
median signed **−12.50 bps**, per-year same-sign share **0.68**, worst 12-month window **940.33 bps**.

Descriptive endpoints (never used to claim threshold success):

| | A: defective hybrid | B: preregistered equal | **B: production** |
|---|---|---|---|
| CAGR | 16.9150% | 16.6792% | **16.6855%** (−22.95 bps vs A) |
| Sharpe | 0.5965 | 0.5908 | **0.5910** |
| annualized volatility | 38.6541% | 38.7487% | **38.7486%** |
| max drawdown | −64.5944% | −64.6416% | **−64.6416%** |
| cap violations | 1,539 | 2 | **0** |

The two capped sessions are worth **+0.6 bps of CAGR** relative to the preregistered arm — production's
20% cap with a cash residual is very slightly *better* than the uncapped 25%/name allocation, and
immaterial either way.

### 7.2.2 RESULT — variant D (NON-GOVERNING control): `MATERIALLY_DIFFERENT`

T11 = 0 · **T5 FAIL** 78.75 / 75 (ratio 1.05) · **T7 FAIL** 304.78 / 125 (ratio 2.44) · CAGR 14.7832% →
14.5534% (−22.98 bps) · Sharpe 0.5282 → 0.5238 · 12m positive 29.3%, median signed −15.86 bps, worst
window 1,298.54 bps. Same conclusion under the regime-free control.

### 7.3 What the corrected run cannot do

It can **refine the classification** of production sizing. It **cannot** retroactively make the old hybrid
validation valid evidence for production. That conclusion is already established independently of it:

- the Stage-3 N=5 hybrid result came from an infeasible, cap-violating residual;
- equal weighting cannot automatically inherit that result;
- the preregistered equal arm was materially different;
- production was not faithfully represented on every rebalance.

**Account 4 activation remains unauthorized regardless of the corrected run's outcome.**

---

## 8. Operational instructions — what is and is not authorized

**PROHIBITED until production sizing is independently validated:**

- ❌ **Clearing the operational hold on strategy 11.** The study did not return
  `PRACTICALLY_EQUIVALENT`; only that verdict could have supported clearing.
- ❌ **Activating strategy 11 / Account 4**, by any route, including manual registration.
- ❌ **Starting the activation cooldown.** It has not begun and must not be started. The previously
  discussed documented cooldown exception is moot — it presupposed a passing study.
- ❌ **Treating Stage-3/Stage-4 performance evidence as covering production sizing.** It does not.

**AUTHORIZED, after the reviewed artifact is merged and deployed:**

- ✅ Exactly **one** hold-reason transition — `AWAITING_COLD_START_FIX` →
  **`AWAITING_PRODUCTION_SIZING_VALIDATION`** — via `scripts/update_operational_hold_reason.py`
  (dry-run first). Not through any interim label. `effective_at` preserved, `_rev` incremented,
  hold continuously ACTIVE, no cooldown started.

**Durable blocker wording:**

```
AWAITING_PRODUCTION_SIZING_VALIDATION
  "Production sizing lacks valid performance evidence after the N=5 hybrid validation
   was invalidated."
```

It names the **governing deficiency**, not a presumed remedy — the eventual validated solution could be
separately validated equal weighting, a newly preregistered *feasible* inverse-volatility design, or
another governed sizing method.

## 9. The next program (new version, not another correction to this study)

**Governing question:** *Does the exact production equal-weight, capped-with-cash strategy independently
satisfy the required performance and risk standards?*

It requires its **own preregistration, benchmark, acceptance thresholds, and out-of-sample framework** —
not an extension of this correction-impact analysis. Revisiting the **number of names** or the **20% cap**
is a **different** research program again, since those change the constraint set rather than validating the
current one.
