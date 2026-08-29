# SHARPE-METRIC-SEMANTICS-001 — Frozen Semantics + Numeric Floor (v1.0 FROZEN)

| Field | Value |
|---|---|
| **Status** | **SEMANTICS + NUMERIC FLOOR FROZEN / IMPLEMENTATION NOT YET AUTHORIZED** |
| **Frozen** | 2026-08-29, prospectively — before any implementation, gate change, or backfill |
| **CV resolvability floor** | **1e−6** (prospective) |
| **Authority** | Owner ruling, 2026-08-29 |
| **Grants** | **NOTHING operational.** Not implementation authority, not a gate change, not a backfill |

---

## 1. The frozen structural rule

Sharpe is **computable** only when **all** hold:

1. at least one usable return can be formed;
2. the return series contains **at least two distinct represented values**;
3. all required arithmetic is finite;
4. when mean return is nonzero, `stdev / abs(mean) > 1e−6`.

A genuinely dispersed series with **mean exactly zero is VALID with Sharpe 0.0.**

Failure of any condition yields an **explicit non-computable status and no governed Sharpe value.**
⛔ It is never silently replaced with `0.0`.

### 1.1 Frozen status taxonomy

| Status | Meaning |
|---|---|
| `VALID` | Computable. May legitimately carry **0.0** when the series has genuine dispersion and mean zero |
| `INSUFFICIENT_DATA` | No usable return could be formed |
| `ZERO_INFORMATION` | Fewer than two distinct represented return values |
| `UNRESOLVED_VARIANCE` | Nonzero mean, `stdev/abs(mean) <= 1e−6` |
| `NONFINITE` | NaN / ±Inf in required arithmetic |

⛔ Do **not** collapse these into a single `INVALID`. The distinctions carry different operator meaning
and different downstream policy.

### 1.2 `distinct >= 2` is a REPRESENTED-INFORMATION guard, not a variance proxy

Mathematically constant values can produce **catastrophic** floating variance. Measured: `repeat -0.1 x3`
and `repeat 0.05 x3` give exact variance **0** under rational arithmetic (Sharpe 0) but **±9.34e16** in
float64 — unbounded relative error, the worst corruption in the study. Distinctness rejects these
**before any arithmetic is trusted**, with no numeric threshold involved.

---

## 2. Why 1e−6 — margin, not error discrimination

The floor was **not** chosen because failures begin there. Measured with the same formula in float64 vs
exact rational arithmetic over identical float inputs:

| Candidate floor | Worst rel. error admitted | ULP rejected | Near-const rejected | Drift rejected |
|---|---|---|---|---|
| 1e−8 … 1e−4 | **2.06e−16** (1 ULP) | 11/11 | 20/20 | 0/5 |
| 1e−3 | 2.06e−16 | 11/11 | 20/20 | **1/5** |

Every candidate in 1e−8 … 1e−4 is **numerically indistinguishable** on the stated objective. 1e−3 was
rejected because it begins rejecting a series whose Sharpe is numerically **exact** — a plausibility
rejection, which is out of scope for this control.

**Measured error transition** (controlled family, mean = 0.001): rel. error 3.8e−2 at CV 1e−16 →
2.3e−4 at 1e−15 → 3.7e−9 at 1e−14 → 9.6e−16 at 1e−10 → machine noise at and above CV ≈ 1e−9.

**1e−6 is the center of margin:** ~4 orders above where error has decayed to machine noise (~1e−10), and
~6.3 orders below the nearest measured real Sharpe-input series (**CV 1.863**, SHOP `closeadj`).
`sqrt(machine eps) = 1.49e−8` is a **landmark, not the rule** — the measured transition is lower, and
there is no benefit to operating near it when six orders of real-data clearance are available.

### 2.1 Clean evidentiary separation of the two guards

| Guard | Uniquely justified by | Why the other guard misses it |
|---|---|---|
| **CV floor** | **ULP-compounding family** (11/11 rejected) | `distinct` reaches 17–251; distinctness passes them |
| **`distinct >= 2`** | **Repeated-value family** (20/20 rejected) | 10 of 20 carry *infinite* rel. error; all have `distinct = 1` |

⚠ **Correction on the record:** an earlier note claimed `repeat 0.02 x3` was a case the CV floor caught
and distinctness missed. Constructed directly, that series has `distinct = 1` and exact-zero variance.
There is **no** demonstrated near-constant case that distinctness misses. The CV floor's demonstrated
unique contribution is the ULP-compounding family alone.

---

## 3. What this explicitly does NOT do

- **Does not** make a large Sharpe invalid because it is large. A `+$1/day` path at CV 7.3e−4 with
  \|Sharpe\| 21,806 is **VALID** under this semantics; its float64 result matches exact arithmetic to
  machine precision.
- **Does not** certify that the underlying equity curve is economically credible. Concerns about
  implausibly smooth paths belong to a **separately governed backtest / data-plausibility control**, and
  must not be folded back into computability.
- **Does not** prove upstream price/equity construction, rounding, or market-data representation is
  accurate. The exact-rational experiment proves numerical accuracy **conditional on the float inputs
  already supplied** to the Sharpe calculation. That is the correct scope, and the limit is recorded.

---

## 4. Still OPEN — required before implementation

1. **Consumer matrix frozen** — every consumer's role (candidate / reference / numerator / denominator),
   current invalid behaviour, and desired fail-closed behaviour, so a typed invalid state cannot become
   permissive downstream.
2. **Rolling-window aggregation rule frozen** — window validity uses this same rule; the aggregate
   coverage policy for `rolling_sharpe_positive_frac` is a **separate** decision. Invalid windows must
   count as **neither positive, negative, nor zero**.
3. **Metric semantics version identifier**, so new calculations are distinguishable from legacy ones.

⛔ No backfill. No historical rewrite. No silent replacement with zero. No consumer or gate behaviour
change. Existing persisted `metrics_json` and verdict artifacts remain immutable evidence produced under
legacy semantics.
