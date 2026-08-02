# Layer 2 countersignature — Amendment 3

**Scope: the repository-side construction toolchain only.** The prior countersignature and Amendments
1–2 remain effective. This amendment does **not** change the governed corpus, the corpus manifest, the
July 27 decision, the quarantine disposition, the deployment conditions, or the trust boundary that
keeps `build_normalized_corpus.py` outside every repository production tree.

| | |
|---|---|
| amends | countersignature package `72b98dbb40f8eadae16e91799062dd378f43b64738e814176a839aa3601817c5` |
| corpus manifest | `1e269fadedff74b04135dea5441f2f3338852464c3d06a74c81c98dfc43ca064` — **unchanged** |
| base commit | `1556fc6647c7f9e57211a4ace41a9611fd4dfe59` (PR #589 squash) |
| amended | 2026-08-02 |

## 0. Governance status

```
LAYER 2 CORPUS COUNTERSIGNATURE :  REMAINS VALID
JULY 27 CONSTRUCTION            :  UNCHANGED — semantics preserved and tested
FAILED ITEM                     :  three SESSION-CONSTANT SHAPE CLASSES that PR #589's
                                   sweep could not see
TRUST BOUNDARY                  :  UNCHANGED
```

## 1. What PR #589 closed, and what it did not

PR #589 generalized the Layer 2 toolchain from the single session 2026-07-27 to a per-run governed
parameter, on the finding that a *default* session is the wrong shape for a governed boundary: a tool
that silently uses the previous session produces a corpus, manifest, attestation and readiness receipt
that **all agree with one another and are all wrong together**, and no digest downstream can detect it.

Its sweep looked for **scalar assignments** — `SESSION = date(...)`, `GOVERNED_CUTOFF = "..."`. Three
shape classes survived:

| # | shape | site | why the sweep missed it |
|---|---|---|---|
| 1 | tuple-bound decision window | `build_universe_crosswalk.py` `DECISION_WINDOW = (date(2025, 6, 25), date(2026, 7, 27))` | a tuple is not a scalar assignment |
| 2 | declared base-coverage edge | `build_delta_artifacts.py`, `build_combined_delta.py` `BASE_COVERAGE_THROUGH = date(2026, 7, 24)` | reads as a fixed base property; it is not |
| 3 | declared mutable base census | `build_tickers_delta.py` `BASE_TICKERS_ROWS`, `BASE_MAX_LASTPRICEDATE` | same |

## 2. The material finding

Class 2 is not merely a stale literal. `BASE_COVERAGE_THROUGH` named the coverage of the base corpus
**before any delta**. The lower edge of a *new* delta is the coverage of the corpus as it now stands —
base **plus every committed delta**.

Those two coincided **exactly once**: at the first governed session, when the manifest carried no prior
delta. That coincidence is why the constant went unnoticed through the July 27 construction. They
diverge for every session after it. A 2026-07-28 delta bounded at 2026-07-24 would have opened its
window three sessions early and re-ingested sessions the corpus already holds.

The runtime contract in `app/validation/governed_corpus.py` refuses a delta whose `session_date` is at
or before `base_coverage_through`, but 2026-07-28 clears that test — so the runtime would **not** have
caught it. The refusal added here is the one that would.

## 3. What changed

- **Decision window — derived, never declared.** `build_universe_crosswalk.py` now requires `--session`
  and derives the window through the shared rule in `scripts/forward_validation/_governed_window.py`:
  the last 273 SEP sessions at or before the session, refusing unless the corpus yields exactly that
  many *ending on the session*. `layer2_step5_exclusion_impact_273.py` imports the same length rather
  than redeclaring it, so the two cannot drift.
- **Base facts — measured and manifest-bound.** `scripts/forward_validation/_base_facts.py` measures
  coverage, the TICKERS census and max `lastpricedate` from the bound corpus and reconciles them with
  the countersigned manifest, parsed through the **same typed contract the runtime reads**
  (`CorpusManifest.from_payload`) rather than a bespoke reader. The three delta tools now require
  `--base-manifest`.
- **Refusals** (all fail-closed): store disagrees with its manifest · session at or before coverage ·
  delta dates outside `(bound_lower, session]` · TICKERS census mismatch · max-`lastpricedate`
  mismatch · corpus cannot supply the exact window · window does not end on the session.
- **`SOURCE_MASTER_BOUNDARY` remains a constant**, now documented as a *historical contract fact*: it
  describes the vendor source master underlying the owner's 2026-07-29 exclusion ruling, not a corpus
  property. Measuring it would let a later corpus silently redefine what a past ruling was about.

## 4. The new invariant

`scripts/check_layer2_date_literals.py` (+ `.sh`) walks the **parsed AST** of every tool in
`scripts/forward_validation/`, so a date literal is caught whatever shape it takes — bare assignment,
tuple, list, dict value, `date(...)` call, argument default, inline comparison.

AST rather than text scanning is deliberate. A line-based scan cannot distinguish code from
commentary; the existing `test_only_the_store_finalizer_writes_dataset_coverage` scan has twice tripped
on explanatory comments that merely *mentioned* what they described, which trains authors to reword
prose to appease a checker rather than to fix code. Here comments are invisible and docstrings are
skipped, so a tool may document the constant it used to carry.

Genuine historical constants are registered **by exact literal value**, never by variable name — a
name-level exemption would silently cover every future date added to that assignment. Five are
registered: `SOURCE_MASTER_BOUNDARY`, `ACTIONS_COVERAGE_START`, the countersigned SHOP/TLN quarantine
anomaly dates (twice, in the quarantine tool and the evidence package), and the seam-contaminated
predecessor measurement window retained for comparison only.

## 5. What this amendment does NOT do

- It does **not** move `build_normalized_corpus.py` into the repository, or change its
  source-authority classification. That exclusion is a trust-boundary decision, not a missing file.
- It does **not** reopen whether the offline builder's raw coverage writes remain authorized.
- It does **not** authorize a 2026-07-28 extraction, corpus installation, supersession
  countersignature, session execution, or any Account 4 change.
- It does **not** alter the July 27 construction. `test_july27_semantics_are_preserved` pins the
  derivation to return exactly `2026-07-24` for that session, which is the value the retired constant
  carried.
