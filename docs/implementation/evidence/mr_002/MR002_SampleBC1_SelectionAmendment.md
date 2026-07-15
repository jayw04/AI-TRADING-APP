# MR-002 — Sample B-C1 Selection Amendment (for countersign)

**Owner ruling 2026-07-14 §6/§7/§8 + the cardinality correction (B-C1 = 100).**
**SELECTION ONLY. No repair executed, no certificate produced, no performance computed. B-C1 repairs
are NOT authorized until this amendment is countersigned (§12).**

---

## 1. Decision applied

Reading **(a)** — canonical content-hash disjointness is required. The original frozen Sample B is
**selection-defective** (its index 1434 is the content-hash twin of Sample A's index 7), not
mathematically failed, and is **preserved unchanged** as the historical selection. B-C1 is a
separately named, prospectively constructed corrected selection at the preregistered cardinality
**100** (`PROSPECTIVE_N`; the earlier "50" is withdrawn).

## 2. Reserve order (§7) — frozen before construction, from corpus identity only

The preregistration's `[:100]` truncation froze only the first 100 of a deterministic generator. The
reserve order is that generator's **continuation**:

> **`sorted(rest, key=canonical_content_hash)` beyond the original 100**, where
> `rest = qualifying_overlaps \ Sample_A` (by index).

Derived **only** from corpus identity (content hashes) and the original selection mechanism. **Not**
from solver outcomes, problem dimensions, runtime, agreement margins, or economic data.

**Duplicate-exclusion rule (applied to originals and replacements alike):** reject a candidate iff
its canonical content hash appears in Sample A, or has already been accepted into B-C1.

## 3. The construction result

| | |
|---|---|
| original-B candidates preserved | **99** |
| rejected duplicates | **1** |
| replacements | **1** |
| reserve indices consumed | `[3573]` |

**The single change (row-by-row):**

| original B position | original index | original hash | status | replacement index | replacement hash |
|---|---|---|---|---|---|
| 42 | **1434** | `02d95fbf047841471171…` | rejected — `content_hash_in_sample_a` | **3573** | `077d7a2c98786989…` |

- **Replacement index:** `3573`
- **Replacement content hash:** `077d7a2c98786989…`
- **Absent from Sample A:** ✅ (verified against A's content-hash set)
- **Absent from accepted B-C1 members:** ✅
- **Replacement arrays differ from the rejected twin:** ✅ (not another accidental duplicate)
- Every other position (0–41, 43–99) is **byte-for-byte the original B index**.

## 4. §8 selection proof

```
cardinality                          100      (== PROSPECTIVE_N)
unique content hashes                100
overlap with Sample A                  0
internal duplicate hashes              0
unexplained changes from original B    0
rejected duplicate count               1
replacement count                      1      (== rejected count)
```

`selection_valid = true`. If the reserve had been exhausted before 100 unique disjoint hashes, the
run would have **stopped and reported the shortfall** — not relaxed eligibility, extended the frame,
or filled by judgment (§6). It did not: only one reserve candidate was needed.

## 5. Artifacts (to be countersigned)

| artifact | sha256 |
|---|---|
| `MR002_SampleBC1_Selection.json` | `e57ffd4090751637818a6ef695722dd4c68c943859247f7693e89d2e21500c95` |
| construction script `scripts/mr002_sample_b_c1_selection.py` | in-tree at the evidence commit |
| census (predicate) `MR002_DuplicateCensus.json` | `216349d1…` |

Corpus reproduced exactly: `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b`.
Run selection-only from the evidence commit; the cascade qualification was reproduced from the frozen
procedure.

## 6. What is NOT done, by rule

Per §12, this is the stopping point. **Not authorized until countersign:** B-C1 repairs, the full
overlap run, preflight, development performance, validation, sealed OOS, erratum drafting. The B-C1
repair runner will reuse the exact Sample A code path (frozen cascade, canonical exact min-L∞ repair,
shared exact basis decomposition, Bland pivots, exact certificates, corrected directed rounding,
600 s ceiling, determinism + shuffle invariance) and the corrected §4 call-graph guard that checks
the provenance of the invoked functions, not module presence.

## 7. Requested action

Countersign this selection amendment (the reserve order, the single replacement 1434 → 3573, and the
§8 proof). On countersign, B-C1 execution is authorized under the unchanged frozen specification; it
stops after B-C1 for adjudication.
