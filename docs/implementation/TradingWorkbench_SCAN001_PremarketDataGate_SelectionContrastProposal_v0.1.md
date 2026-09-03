# SCAN-001 — Premarket-Data Gate: Selection-Contrast Defect & Funnel Redesign Proposal (v0.1)

| Field | Value |
|---|---|
| Document version | v0.1 (design proposal — **requires owner adjudication**; nothing here is implemented) |
| Date | 2026-07-25 |
| Program | SCAN-001 (Market Opportunity Discovery Engine) |
| Type | Governed research-design change to a **pre-registered** gate |
| Governs | `TradingWorkbench_SCAN001_PremarketDataGate_Plan_v0.1.md` §0b (funnel), §3 (verdict); ADR 0024; ADR 0014 |
| Status | **OPEN — no verdict may be issued by the gate until this is decided** |
| Out of scope | The two mechanical defects already fixed (record admission, loud sync failure) — those were bug fixes and shipped separately. This document changes **no code**. |

> **One sentence.** The gate has accrued 31 admissible forward days on which the candidate set and the
> baseline field were the *same set*, so `edge_E` was 0.0 by construction on every one of them; the gate was
> therefore never measuring transfer, and the funnel must be redesigned before accrual means anything.

---

## 1. The defect

The gate's estimand (plan §3) is the candidate-vs-field edge:

```
edge_E = mean(E over candidates) − mean(E over eligible)      with   candidates ⊆ eligible
```

When `candidate_count == eligible_count` the two sets are **identical**, so `edge_E ≡ 0.0` — not "no edge
was found", but *no comparison was performed*. The day formed no comparison group.

**This is the observed state on every accrued day.** Measured 2026-07-25 against all 32 records in
`ec2-paper:/opt/workbench/data/premarket_gate_evidence/` (2026-06-08 → 2026-07-24):

| Quantity | Value |
|---|---|
| Records on disk | 32 |
| Admitted (same-day, non-duplicate, filled) | **31** (2026-07-21 excluded — republished stale snapshot) |
| Days with selection contrast (`candidates ⊊ eligible`) | **0** |
| Mean selection ratio `candidate_count / eligible_count` | **1.0** (every day, without exception) |
| Distinct non-zero `edge_E` values observed | **0** |

**Why the funnel collapses.** `gappers_in` is **10 on all 32 days** — the sibling scanner emits a top-10 list
and nothing wider. The store join covers only 1–6 of those (gappers are predominantly micro-caps absent from
the factor store), eligibility trims 0–2 more, and the frozen engine then selects **every** survivor. There is
never a residual to serve as the field.

```
 gappers_in 10  ──►  store_covered 1–6  ──►  eligible 1–6  ──►  candidates == eligible
                          (coverage)          (filters)          (nothing left over)
```

**What the gate would have concluded.** Extrapolating the observed series to the §3 floor of N=40 and running
the frozen block bootstrap over it yields `point = 0.0`, `ci_low = 0.0`, `ci_high = 0.0` — degenerate — which
falls through to `ci_low > 0 → False` and emits:

> **DOES-NOT-TRANSFER** — *"the validated edge does not transfer to the gappers universe; the engine remains a
> liquid-universe tool (a citable boundary)."*

That sentence would have been published as a research boundary. It would have been an artifact of a collapsed
funnel, stated with full confidence, about a hypothesis the gate never tested.

**This is non-identifiability, not low power.** No sample size fixes it. The design cannot distinguish
*"the edge does not transfer"* from *"no comparison group was ever formed"*, because both produce exactly
`edge_E = 0.0`. More days produce more zeros.

## 2. What has already been done (bug fixes, not design changes)

Shipped separately and deliberately **non-adjudicating** — they only ever *withhold* a verdict:

1. **Record admission.** A record contributes a forward day only if `outcome_status == "filled"`, `stale` is
   not true, `source_date == asof`, and `source_date` is unique across admitted records. This excludes
   2026-07-21 (a 2026-07-20 snapshot republished under the next day's `asof` after the scanner failed), taking
   the valid-day count from **32 → 31**.
2. **Loud sync failure.** `deploy/sync-gappers-to-box.sh` no longer falls back to the newest file on disk; it
   validates the run manifest, exact filename, embedded Eastern `scanned_at` date, freshness window, and
   post-copy sha256, and alerts + exits non-zero rather than publishing a stale artifact.
3. **Identifiability guard.** With zero contrast-bearing days the gate now returns
   **`INVALID-EVIDENCE / NO_SELECTION_CONTRAST`** and publishes no statistic. Zero-contrast days are excluded
   from the edge series entirely — *a zero-contrast day is not a zero-edge day*.

The gate is therefore **safely frozen**: it currently reports `INVALID-EVIDENCE`, and cannot emit
DOES-NOT-TRANSFER or TRANSFERS while the funnel stays collapsed. This document is what unfreezes it.

## 3. Options for restoring selection contrast

Assessed against: does it produce a *meaningful* field, is it economically informative, and what does it cost?

### Option A — Widen the scanner universe, then rank and cut *(recommended)*

Have the sibling scanner emit a materially wider premarket list (target 50–200 names rather than 10), then let
the frozen engine select a top subset, leaving the remainder as the field.

- **Pro** — the only option that attacks the actual root cause (`gappers_in = 10`). Restores a genuine
  selection contrast and keeps the pre-registered estimand *exactly* as written; nothing about the hypothesis
  or the engine changes, only the width of the input.
- **Con** — requires work in the sibling `claude-trading-view` scanner, and the store-coverage problem (Option
  B) still caps how many wide-universe names survive the join.
- **Note** — GAP-NATIVE-001 / PR #407's Path B (batched Alpaca snapshot sweep of a ~1000-name universe, timed
  at ~5 batches and comfortably inside the premarket window) is a plausible box-native supplier of exactly this
  wider list. That PR is parked pending its own research-design question and should stay parked; it is
  mentioned here only because the two decisions share an input.

### Option B — Improve factor-store coverage

Ingest the small/micro-cap names that gappers actually consist of, so more of each day's list survives the join.

- **Pro** — raises `store_covered` (currently 1–6 of 10), which compounds with Option A; also fixes a silent
  population-mismatch problem, since today's eligible field is a *biased* subsample (only gappers large enough
  to be in a store built for a liquid universe).
- **Con** — a data-acquisition programme in its own right, with cost and vendor questions; slower than A.

### Option C — Compare selected vs. non-selected within a larger eligible field

The natural consequence of A and/or B rather than a standalone option: with a wide enough eligible field,
"selected" vs. "not selected" becomes a real contrast. **This is the pre-registered design already** — it needs
no change, only a field wide enough to have a complement.

### Option D — Redefine the research question

If a genuinely wide, well-covered gapper field is not attainable, the honest move is to change the question —
e.g. from *"does the selection edge transfer?"* to *"do the engine's premarket features carry information on
the small covered subset?"* — and re-pre-register accordingly.

- **Pro** — intellectually honest about a real data constraint; avoids indefinite accrual toward an
  unanswerable question.
- **Con** — it is a different, weaker claim, and must not be presented as the original transfer result.

### Explicitly rejected — naive rank-and-cut of the current 1–6 survivors

Mechanically forcing `candidates ⊊ eligible` on today's field (e.g. "take the top half of 3 names") would
produce contrast-bearing days and let the gate emit a verdict. **It should not be done.** A 1-vs-2 or 2-vs-4
split is dominated by single-name idiosyncratic variance, the bootstrap's block structure becomes meaningless
at that width, and the resulting CI would be unstable and economically uninformative. It converts a visibly
broken test into an invisibly broken one — strictly worse, because the output would look valid.

## 4. Parameters requiring governance

To be set by owner decision, not chosen in code. The verdict function already carries inert hooks
(`min_contrast_days`, `max_mean_selection_ratio`), both defaulting to `None` = *not yet governed, not enforced*.

| Parameter | Question | Note |
|---|---|---|
| `min_contrast_days` | How many contrast-bearing days before adjudication? | Is the existing N=40 floor still right when it now counts only contributing days? |
| `max_mean_selection_ratio` | Maximum mean `candidate_count / eligible_count` for a day to count as informative | Guards against 4-of-5-style pseudo-contrast; the current value is 1.0 |
| Minimum eligible field width | Minimum `eligible_count` per day | The direct guard against the rejected rank-and-cut failure mode |
| Target `gappers_in` | How wide must the scanner list be? | Drives the Option A scope |

## 5. Accrued-evidence disposition — the decision that cannot be deferred

**Changing the funnel changes the estimand.** Days accrued under a wider universe are not exchangeable with
days accrued under the top-10 collapsed funnel; pooling them would silently mix two different populations, the
precise error the GAP-NATIVE-001 segmentation rule exists to prevent.

The recommendation is therefore that **all 31 currently accrued days be retired as pre-fix evidence and forward
accrual restart at N=0** under the redesigned funnel. This is a real cost — roughly two months of elapsed
calendar time — and it is the owner's call, not an implementation detail. The alternative (pooling) is not
recommended at any confidence level.

Whatever is decided, the 31 records should be **retained** and labelled, not deleted: they are the evidence for
this document, and they remain a valid record of the coverage problem.

**Owner's preliminary ruling (2026-07-25 — recorded here, pending formal approval of this document):**

```
PRE-FIX DAYS:                        RETAINED FOR AUDIT AND DIAGNOSTICS
POST-FIX GOVERNED ACCRUAL:           RESTART AT N=0
POOLING:                             PROHIBITED
BACKFILLING POST-FIX LABELS ON OLD DAYS:  PROHIBITED
```

This ruling is **preliminary**. It takes effect on approval of this document (D5 below), not before, and it is
deliberately not encoded in any shipped code — the mechanical PR neither retires nor relabels a single record.

## 6. Recommendation

1. Adopt **Option A** (widen the scanner list) as the primary fix, with **Option B** (store coverage) pursued in
   parallel as the compounding fix.
2. Govern the four §4 parameters before accrual restarts.
3. Restart forward accrual at N=0; retain and label the 31 pre-fix records.
4. Keep the identifiability guard permanently — it is cheap, and it is the thing that would have caught this
   before the verdict rather than after.
5. Do not unpark PR #407 on the strength of this document; its Path-B question is separate.

**Until items 1–3 are decided, the gate remains at `INVALID-EVIDENCE` and the Candidate Report stays advisory
(ADR 0014). No SCAN-001 promotion decision may cite a gate verdict produced before this adjudication.**

---

## 7. Unresolved decisions requiring a ruling

Approval of this document means ruling on each of these. **Nothing below is implemented, and approval of the
companion evidence-integrity PR does not authorise any of it.**

| ID | Decision | Status | Recommendation |
|---|---|---|---|
| **D1** | **Funnel design** — how selection contrast is restored (Option A widen scanner / B store coverage / C consequence-of-A+B / D redefine question) | **OPEN** | A primary, B in parallel; naive rank-and-cut **rejected** |
| **D2** | **Minimum contrast-day threshold** (`min_contrast_days`) — is N=40 still right now that it counts only contributing days? | **OPEN** | No recommendation; needs power analysis under the chosen D1 |
| **D3** | **Maximum mean selection ratio** (`max_mean_selection_ratio`) — the guard against pseudo-contrast (e.g. 4-of-5) | **OPEN** | No recommendation; currently 1.0 observed |
| **D4** | **Minimum eligible-set size / leftover-field requirement** — the direct guard against the rejected rank-and-cut failure mode | **OPEN** | No recommendation; must exceed the 1–6 currently observed |
| **D5** | **Historical evidence treatment** — retire the 31 days and restart at N=0, or retain only as pre-change diagnostic evidence | **OPEN** (preliminary ruling recorded in §5) | Retire from accrual; retain for audit; pooling and post-fix relabelling prohibited |

**Authorisation status at time of writing:** implement funnel changes — **NOT AUTHORISED**. Govern D2/D3/D4
thresholds — **NOT YET DECIDED**. Restart accrual at N=0 — **RECOMMENDED, PENDING FORMAL DESIGN APPROVAL**.

This document confers no authority to implement any option it describes.
