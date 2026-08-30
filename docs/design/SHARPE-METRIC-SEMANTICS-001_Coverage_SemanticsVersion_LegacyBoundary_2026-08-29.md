# SHARPE-METRIC-SEMANTICS-001 — Rolling Coverage, Semantics Version, Legacy Boundary (v1.0 FROZEN)

| Field | Value |
|---|---|
| **Status** | **FROZEN / IMPLEMENTATION NOT AUTHORIZED** |
| **Frozen** | 2026-08-29, prospectively — before any implementation, gate change, or backfill |
| **Rolling coverage floor** | **0.75** |
| **Semantics version** | **`sharpe_semantics_version = "1.0"`** |
| **Mixed-semantics comparison** | **PROHIBITED** |
| **Authority** | Owner ruling, 2026-08-29 |
| **Builds on** | `docs/design/SHARPE-METRIC-SEMANTICS-001_Frozen_Semantics_and_CV_Floor_2026-08-29.md` (merged `e56c5e3c`) |
| **Grants** | **NOTHING operational.** Not implementation authority, not a gate change, not a backfill |

---

## 1. Rolling-window minimum valid coverage — 0.75

```
rolling_sharpe_min_valid_coverage = 0.75
```

**This is a governance/evidence-sufficiency choice, not a statistical estimate.** ⛔ It must never be
described as empirically optimal. The census could not identify it: at the production window (63)
only one real curve produced windows at all, and at window 21 the observed curves were bimodal —
wholly valid or wholly `ZERO_INFORMATION`. **No real curve exercised the partial-coverage regime
this floor governs**, so the value was chosen, not measured.

A rolling aggregate claims to characterize a *requested period*. Requiring at least three quarters
of candidate windows to be valid means the aggregate describes a clear majority of that period while
tolerating a bounded amount of unavailable evidence — the permitted missing portion is capped at one
quarter.

Alternatives rejected **on policy grounds**, not on outcomes:

- **50%** — too permissive. An aggregate could characterize a period with up to half the requested
  evidence absent. That is weak support for a governed decision statistic.
- **90%** — defensible but unnecessarily strict here. It turns modest gaps into non-evaluability
  without evidence that rolling Sharpe requires near-complete coverage.

⛔ The floor was **not** selected by computing which choice changes any current book's outcome.
Choosing a threshold by what it lets pass is the failure the prospective discipline exists to
prevent.

### 1.1 Frozen aggregate semantics

```
total_candidate_windows
valid_windows
coverage = valid_windows / total_candidate_windows

if total_candidate_windows == 0:
    rolling_sharpe_status       = NOT_EVALUABLE
    rolling_sharpe_positive_frac = absent

elif valid_windows == 0:
    rolling_sharpe_status       = NOT_EVALUABLE
    rolling_sharpe_positive_frac = absent

elif coverage < 0.75:
    rolling_sharpe_status       = INSUFFICIENT_COVERAGE
    rolling_sharpe_positive_frac = absent

else:
    rolling_sharpe_status       = VALID
    rolling_sharpe_positive_frac = positive_valid_windows / valid_windows
```

- Each window is typed by the structural rule and the **1e−6** floor already custodied at `e56c5e3c`.
- **Invalid windows are neither positive, negative, nor zero.** They affect **coverage only** — never
  the numerator, never the denominator of the positive fraction.
- `coverage` is **always reported**, including when the status is `INSUFFICIENT_COVERAGE`.
- `pos_frac = 0.0` is reserved for an evaluable population containing VALID windows and zero
  positive ones.

### 1.2 ⚠ The absent-vs-zero trap (load-bearing)

`ge()` in `app/research/promotion/gate.py` is `v is not None and v >= thr`. It fails closed on
`None` but **not** on `0.0`.

⛔ An under-covered aggregate must therefore be **absent**, never `0.0`. Emitting zero would make the
gate read *no measurement* as a *measured failure* — a different claim, and one that would look
identical in every summary.

---

## 2. Metric semantics version — "1.0"

```
sharpe_semantics_version = "1.0"
```

- Every artifact calculated prospectively under the frozen structural rule and CV floor carries it.
- An artifact with **no** version field is **`LEGACY / PRE-SHARPE-SEMANTICS-1.0`**.
- ⚠ **Refinement:** `PRE-SHARPE-SEMANTICS-1.0` describes the artifact's **governance class**. It is
  *not* proof of which historical calculation behaviour actually produced it. Missing means
  **unknown/legacy** — it must never default to `1.0`.
- ⛔ **No historical artifact is stamped retroactively.** Legacy artifacts remain immutable.

"1.0" denotes the structural rule and the 1e−6 floor as custodied at `e56c5e3c`. A later change to
either is a **new version**, never an edit of this one.

---

## 3. Legacy/current comparison boundary — PROHIBITED

```
LEGACY vs 1.0 comparison:  NOT AUTHORIZED
```

unless a separate, explicit compatibility policy later authorizes a particular comparison.

⛔ **A numeric Python type is not measurement compatibility.** A legacy `0.0` may represent a
historically valid zero, an exact-zero guard result, or a non-computable state collapsed into zero —
and, per the second recorded defect, a legacy value may also be a finite number produced from
numerically unresolved variance. None of those is comparable to a `1.0` value, which is either
genuinely computed or explicitly non-computable.

### The two known sites — both read persisted `metrics_json`

| Site | Comparison | Required behaviour |
|---|---|---|
| `app/services/proposal_evaluation.py:190` | `variant_sharpe >= baseline_sharpe` → `VERDICT_ABOVE` | ⛔ Must **not** default a missing Sharpe to `0.0`. If the measurements do not share authorized semantics, the result is **`NOT_EVALUABLE`** — not pass, not fail |
| `app/services/range_auto_select.py:184` → `range_insight.py:438` | sort tiebreak `-sharpe`; the path then rewrites `symbols_json` and stop/starts the PAPER sleeve | ⛔ Must **not** rank mixed-semantics values against each other. **Fail-closed behaviour is required before ranking or selection**, because the downstream effect is a live sleeve change |

⚠ `proposal_evaluation.py:190` currently reads `float(metrics.get("sharpe_ratio", 0.0))` — a missing
key already defaults to `0.0`, the silent-zero pattern in its purest form. That default must go.

**No backfill follows from this ruling.** The rule governs *comparison*, not stored values. If an
active decision genuinely needs legacy data under 1.0 semantics, that produces a **separately
labelled recomputed artifact**; the original is never overwritten.

---

## 4. Explicitly still open — do not read this document as resolving it

**CONTINUOUS-EVIDENCE-INSUFFICIENT-SEVERITY-001 = IDENTIFIED / UNADJUDICATED / NO FIX AUTHORIZED.**

`None → INSUFFICIENT`, `_STATE_SEVERITY[INSUFFICIENT] = 0`, and `overall` takes `max()`, so a
required-but-unmeasurable Sharpe can be outranked and vanish from the overall state.

⛔ The 0.75 coverage ruling does **not** answer this. They are different policy layers: coverage
governs whether a rolling aggregate may be reported at all; CE-001 governs whether an unmeasurable
metric may be dominated by other evidence in a composite state. It must not be fixed incidentally
inside any Sharpe implementation.

---

## 5. Gate

Implementation remains behind: semantics custody ✅ → rolling census ✅ → coverage ruling ✅ →
**consumer-policy custody** → implementation review.

⛔ Nothing in this document authorizes code, a consumer change, a gate change, a backfill, or a
historical rewrite.
