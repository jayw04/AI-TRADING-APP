# MR-002 v1.1 — Sample B STOP: content-hash twin between A and B (ruling §7 / §9)

**Status:** STOPPED at the §7 pre-proofs, **before any repair began.** No repair, no performance,
nothing computed. Awaiting adjudication.
**Runner commit:** `77b30b8` (evidence-only successor to `c130149`; solver-path hashes verified
identical)

**Performance NOT computed. Validation and sealed OOS SEALED AND UNREAD. Preflight STOPPED. Erratum
UNDRAFTED.**

---

## 1. The stop

The §7 pre-proofs run before the first repair. Four of the five passed; one did not:

```
[ok]   matches_preregistration     B reproduces the frozen prospective_B list exactly
[ok]   content_hashes_match        B's content hashes == the frozen prospective_B_content_hashes
[ok]   disjoint_from_A             B shares no corpus INDEX with A
[STOP] no_A_content_hash           B shares a content HASH with A
[ok]   size_100
```

This is a §9 stop condition — "sample-list or disjointness mismatch" — and the run halted at it
without proceeding to any repair.

## 2. What it is, exactly

**One** collision, and it is a genuine duplicate in the corpus:

| | corpus index | content hash | arrays |
|---|---|---|---|
| Sample A | **7** | `02d95fbf047841471171…` | — |
| Sample B | **1434** | `02d95fbf047841471171…` | **byte-identical to A[7]** |

Indices 7 and 1434 are two different positions in the immutable characterization corpus that carry
**byte-identical** `(t, A_ub, b_ub, A_eq, b_eq, upper)` — the same mean-reversion problem generated
on two different days. Verified: `arrays_identical = True` across all six arrays.

So the corpus contains a content-duplicate, and the two copies fell on opposite sides of the A/B
split.

## 3. Why the frozen B contains it

The preregistered selection rule (frozen in `mr002_coverage_signed_gap.py`, recorded in
`MR002_R2_RegressionSampleA.json`) defines the split by **corpus index**:

```
A    = qualifying[:50]                                    # first 50 in canonical corpus order
rest = [i for i in qualifying if i not in set(A)]         # disjoint BY INDEX
B    = sorted(rest, key=content_hash)[:100]               # 100 by content-hash order
```

`rest` excludes A's *indices*, not A's *content*. Index 1434 is not in A, so it is eligible for B;
it happens to be the content-twin of A's index 7. Index-disjointness therefore does **not** imply
content-disjointness whenever the corpus has a duplicate — and here it has exactly one that straddles
the split.

This is a property of the **frozen preregistration**, not of anything introduced now. My recomputed B
matches the frozen `prospective_B` list and content hashes exactly (checks 1 and 2 above), so the
collision is in the registered sample, not in my reconstruction of it.

## 4. Why I did not work around it

The ruling forecloses every workaround I might reach for:

* §7 — "no substituted or regenerated instance." Dropping index 1434, swapping in the next
  content-hash candidate, or deduplicating the corpus would each *regenerate* B.
* §9 — "Preserve the failing instance and all partial evidence. Do not replace it or continue to
  obtain a cleaner aggregate."

So the sample is left exactly as frozen, and this is brought for adjudication rather than resolved.

## 5. The two readings, for the owner to choose between

**(a) Content-hash disjointness is the operative requirement (§7 as written).** Then the frozen B is
defective: it must not contain A's content. Remedying it changes the preregistration and needs
explicit authorization — either re-freeze B excluding the twin, or deduplicate the corpus and
re-derive both samples. Both are preregistration changes, not runner changes.

**(b) Index-disjointness is the operative definition (the frozen rule).** Then B[1434] is a
legitimately distinct sample POINT that happens to be the same PROBLEM as A[7], and content-hash
disjointness was a stricter phrasing than the frozen rule implements. Sample B would then be
authorized to run as-is, and this report records that the one shared content hash is an accepted
consequence of a corpus duplicate — the repair on it would simply reproduce A[7]'s exact result
(deterministically), which is a replication data point rather than a contamination.

I have a view but it is the owner's call: reading (b) is internally consistent with how the sample
was actually frozen, and the "contamination" the disjointness rule guards against — B's outcome
being influenced by what was learned from A — cannot occur here, because the repair is a
deterministic exact function of the (identical) inputs. But §7 says "content hash," and I will not
reinterpret a written requirement to avoid a stop.

## 6. What is verified and intact

The stop happened *after* the §4 call-graph binding passed and *before* any repair, so everything
upstream is confirmed:

* §4 — the repair functions resolve to `app.research.mr002.exact_repair` (canonical); `exact_repair`
  does not import the retired module; `exact_repair.solve_lp is exact_simplex.solve_lp`; solver-path
  module hashes equal the `c130149` manifest. (The retired R2 module is present-but-unused in
  `sys.modules`, dragged in by the corpus/selection harness — the same benign state that held during
  Sample A.)
* corpus reproduced exactly: `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b`.
* B matches the frozen `prospective_B` list and content hashes.

## 7. A prior-guard note

My first §4 guard stopped on "the retired module is in `sys.modules`". That was the wrong criterion —
the module is imported by the corpus harness for its own machinery and is never on the repair path,
and the same state held during Sample A. The guard was corrected to check the **provenance of the
functions actually called** (commit `77b30b8`). That correction is unrelated to the §7 collision
above; it is recorded here only so the two stops are not conflated.

## 8. Requested decision

1. Reading (a) or (b) for the A/B disjointness definition.
2. If (a): authorization for a specific preregistration remedy (re-freeze B excluding the twin, or
   deduplicate the corpus), since either changes the frozen sample.
3. If (b): authorization to run Sample B as frozen, with this report recording the one shared content
   hash as an accepted corpus-duplicate replication point.

No Sample B repair runs until this is decided.
