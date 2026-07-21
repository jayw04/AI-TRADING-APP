# momentum-daily — Step 5B: Actual-Book Inception Test (Policy M vs Policy H) — v1.0
**Purpose:** decide `initial_seed_investable_gross` using the **actual 5-name momentum book** (not the market proxy), per the owner-required stronger test.
**Date:** 2026-07-21. **Status:** ✅ **DECISION LOCKED (owner 2026-07-21): `initial_seed_investable_gross = 0.60`** — scope = inception eligibility only. Step 6 CLOSED.

## LOCKED production decision
```
initial_seed_investable_gross = 0.60
status = LOCKED
scope = inception eligibility only
```
**Adjudication of record:** *Policy M is retained because actual five-name portfolio testing shows positive and subperiod-stable median incremental returns across all evaluated horizons (10/21/42/63d). Policy H reduces adverse tail exposure but causes prolonged cash parking (19% not deployed within 63 sessions) and misses compensating upside (+0.63% median during waits). The predeclared conditions required to replace Policy M (rule conditions 3 and 4) were not met.*

**⚠ Documented tail-risk characteristic:** the near-zero *means* alongside positive *medians* indicate a minority of severe episodes offsets the typical benefit — a real left-tail cost (p5 P&L −5.5…−11%; tail maxDD ~14pp worse than H), retained knowingly because it comes with compensating median return and reliable deployment.

**★ Governance lesson (called out):** the *proxy* analysis (Step 5A) favored 0.98; the *actual governed portfolio* (Step 5B) favored retaining 0.60. The production decision correctly follows the actual book, not the proxy.

## Method
Reused the Stage 4 harness construction **verbatim** — `select_n` / `weigh` (hybrid_50_50, 5 names, no sector cap) + gross-scaling + `TURNOVER_COST_BPS` cost + the six warm-book triggers — changing **only inception eligibility**:
- **Policy M:** deploy at the first session with `regime_target_gross ≥ 0.60`.
- **Policy H:** stay 100% cash until the first session with `regime_target_gross == 0.98`, then identical warm-book logic.
Scores computed once over 2005-01-03..2026-06-12 (5,395 days). For each of the **123** 0.60-inception episodes, a fresh flat book was simulated forward 63 sessions under each policy. Data: `factor_data_full.duckdb` (read-only). Driver: `actualbook_5B_driver.py`; per-episode data: `actualbook_5B.csv`.

## Results (n=123, horizon 63d)
### P&L difference, M − H (% of equity)
| horizon | median | mean | p5 | p95 |
|---|---|---|---|---|
| 10d | **+0.58** | +0.41 | −5.54 | +5.81 |
| 21d | **+0.44** | −0.07 | −7.56 | +4.57 |
| 42d | **+0.64** | −0.05 | −11.03 | +5.82 |
| 63d | **+0.76** | −0.14 | −9.96 | +6.59 |

→ **M has a positive median P&L edge at every horizon**, but a **fatter left tail** (mean ≈ 0, p5 down to −11%): M wins the typical case, loses big in a minority.

### Drawdown / turnover
- maxDD: **M median −9.56%** vs **H median −6.69%** (M ~2.9pp deeper). Paired (M−H) median ≈ **−0.00**, p5 **−14.34%** → M's drawdown penalty is concentrated in a **tail**, not systematic.
- Turnover over 63d: M median 4.55 vs H 3.74 (M−H median **+0.62**) — modest extra churn.

### Policy-H waiting cost
- **M book return during H's wait:** median **+0.63%** (H's missed upside), mean −0.28%, p5 −9.96%, p95 +6.59%, negative 33% (H avoids a loss 1/3 of the time).
- **Prolonged cash under H:** NOT deployed within 10d **42%** · 21d **31%** · 42d **26%** · **63d 19%**. Wait (when deployed ≤63d): median 4, mean 10.9, max 63. → typically fast, but **~1 in 5 inceptions leaves the book in cash for >13 weeks**.
- First-portfolio overlap M vs H (Jaccard): median 0.67.

### Subperiod stability
| era | n | P&L diff @21d (med) | ddDiff M−H (med) | M ret during wait (med) |
|---|---|---|---|---|
| 2005–12 | 53 | +0.55% | −0.00% | +0.56% |
| 2013–19 | 33 | +0.37% | −0.00% | +0.50% |
| 2020–26 | 37 | +0.47% | −0.00% | +0.86% |

→ M's positive median edge is **stable across all three subperiods**.

## Adjudication (owner's 5-condition rule to lock 0.98)
Lock 0.98 **only if ALL** hold:
1. M has materially worse inception drawdown/loss — **MET** (drawdown ~3pp deeper; worse left tail).
2. M creates meaningful avoidable turnover/cost — **weakly met** (+0.62 median turnover).
3. M's early entry does **not** provide compensating median/tail upside — **NOT MET** (M median P&L +0.44…+0.76%, stable; p95 +4.6…+6.6%).
4. H's prolonged-cash cases do not create comparable/larger missed gains — **NOT MET** (H parks in cash >63d 19% of the time; median +0.63% missed during waits).
5. Stable across regime episodes/subperiods — MET (but the stable result **favors M's median**).

**Conditions 3 and 4 fail ⇒ the rule does NOT support locking 0.98.** The actual-book test **contradicts** the proxy interim signal: seeding at 0.60 gives a positive, subperiod-stable median P&L edge and reliable deployment; H's protection is real but limited to tail drawdown (~3pp) and is bought with a stable median-upside sacrifice **plus** frequent prolonged cash.

## Recommendation → **retain 0.60** (lock the candidate default as production)
- The predeclared **retain-0.60** condition holds: *retain unless M produces higher reversal/drawdown **without** compensating return* — M's deeper drawdown comes **with** compensating (positive, stable) median return, so retain applies.
- 0.98's concrete failures: 19% prolonged cash >63d and sacrifice of the stable positive median edge, for only ~3pp median drawdown relief.
- **Caveat / owner risk-preference:** M's cost is a **fatter left tail** (p5 P&L −5.5…−11%, tail maxDD 14pp worse than H). A risk-averse owner who weights first-deployment tail-drawdown heavily could still prefer H — but that is a risk-preference choice, not what the pre-declared rule supports.

## Deferred research hypothesis (NOT an implementation option)
```
Deferred hypothesis:
  A persistence-qualified 0.60 inception rule (seed only after 0.60 persists
  K≈3-5 sessions) may reduce left-tail whipsaw while preserving part of
  Policy M's median benefit.
Disposition:
  OUT OF SCOPE for the cold-start conformance repair. Introducing it now would
  expand a conformance repair into a new strategy-policy study, delay the
  confirmed-defect correction, and create a third inception behavior never
  previously validated or live. Requires separate preregistration and validation.
```

## Implementation safeguards (carried into Step 7 — the tail is real)
- Log the exact `regime_target_gross` state that authorized inception; record whether deployment occurred at 0.60 or 0.98-equivalent.
- Report early post-seed drawdown separately for the first 10 / 21 / 63 sessions.
- Preserve the ordinary risk engine and concentration controls (no bypass).
- **Do NOT auto-escalate the threshold after a single bad live inception.**
- **Changing the locked default requires a governed evidence review** (not an ad-hoc edit).
