# MR-002 v1.1 — Sample B-C1: replication on the countersigned disjoint sample

**Status:** SAMPLE B-C1 **PASS** — 100/100, zero stops. STOP for adjudication (§10). Not
countersigned as accepted.
**Authorization:** owner ruling 2026-07-14 §7–§10 + the B-C1 cardinality-100 correction + the
selection-amendment countersign.
**Run commit:** `8d85c62` (evidence-only successor; solver-path module hashes verified `== c130149`
at runtime).
**Image:** `mr002-research@sha256:aa930021c072d01a5a14f389b53bea9d338e53b71e2aac08550972060a08610a`

**Performance NOT computed. Validation and sealed OOS SEALED AND UNREAD. Preflight STOPPED. Full
overlap population CLOSED. Erratum UNDRAFTED.**

---

## 1. Outcome (§8 aggregate)

```
total overlaps                    100
successful exact repairs          100
exactly infeasible repairs          0
invalid runs                        0
resource-ceiling breaches           0
distance-agreement passes         100   failures 0
objective-agreement passes        100   failures 0
determinism failures                0
canonical shuffle failures          0
stops                               0
worst repair wall-clock          61.5 s   (10.3% of the frozen 600 s ceiling)
```

Every one of the 100 countersigned disjoint problems produced an exactly feasible repaired point,
both agreement certificates passed, and each was deterministic and canonically shuffle-invariant.

## 2. Distributions (§8 — not only the maximum)

| quantity | min | p50 | p90 | p99 | max |
|---|---|---|---|---|---|
| repair wall-clock (s) | 0.04 | 1.5 | 17.7 | 55.9 | **61.5** |
| pivots (Phase I + II) | 18 | 87 | 207 | 299 | 328 |
| core dimension | 2 | 7 | 26 | 40 | 44 |
| numerator bits | 54 | 170 | 402 | 503 | 550 |
| denominator bits | 79 | 167 | 410 | 520 | 556 |
| ρ\* (log₁₀) | −99* | −16.7 | −14.7 | −13.5 | −13.5 |
| agreement margin (bound − dz) | 2.1e-9 | 8.4e-8 | 3.1e-7 | 3.7e-7 | 3.8e-7 |
| objective margin (bound − df) | 1.0e-12 | 1.3e-12 | 7.4e-12 | 1.0e-11 | 1.1e-11 |

\* one overlap (`0724f06d…`) had ρ\* = 0 — the submitted solver point was already exactly feasible;
`log₁₀` of it is recorded as the −99 sentinel. All agreement and objective margins are **strictly
positive**, so every bound held with room to spare, not on the edge.

The distributions matter as much as the maxima here: the worst repair (61.5 s) is a tail, not the
norm — the median is 1.5 s and p90 is 17.7 s. Core dimension stays small (p50 = 7) because the shared
basis decomposition is doing its job; the pivot and bit-growth distributions confirm the exact
arithmetic never approached the frozen ceilings (max 328 pivots vs 4000; max 556 bits vs 200,000).

## 3. Frozen specification, verified before any repair

**§4 call-graph binding** — the criterion is provenance of the *invoked* functions, not module
presence:
* `certify_repair`, `agreement`, `objective_agreement` all resolve to
  `app.research.mr002.exact_repair` (canonical);
* `exact_repair.solve_lp is exact_simplex.solve_lp`;
* `exact_repair` does not import the retired module;
* solver-path module hashes equal the `c130149` manifest.
* The retired R2 module is present-but-unused in `sys.modules` (dragged in by the corpus/selection
  harness), never on the repair path — the same benign state confirmed for Sample A.

**§7 pre-proofs** — all six passed:

| check | result |
|---|---|
| matches the countersigned selection (`sample_b_c1`) | ✅ |
| content hashes match | ✅ |
| cardinality = 100 | ✅ |
| unique content hashes = 100 | ✅ |
| zero overlap with Sample A | ✅ |
| no internal duplicate | ✅ |

**Frozen path** (unchanged from Sample A): QUADPROG_SQRT → PIQP_P2 cascade; two-sided signed
Lagrangian gap; canonical exact rational min-L∞ repair; shared exact basis decomposition; Bland
pivots; exact primal / reduced-cost / objective-identity certificates; corrected directed rounding;
600 s per-repair ceiling.

## 4. What B-C1 establishes — and what it does not (§10)

B-C1 **replicates** on a second preregistered, disjoint problem set: the exact-repair and
agreement-certificate path works on all 100 corrected overlaps within the frozen resource ceiling,
after the single content-hash twin was replaced (1434 → 3573) under the countersigned amendment.

It does **not** by itself authorize the full overlap population, preflight, development performance,
validation, sealed OOS, or the erratum. Per §10 the run **stops here** and this immutable evidence
package is presented for adjudication.

## 5. Artifacts

| artifact | sha256 |
|---|---|
| `MR002_SampleBC1.json` | `850e8ad69313447fe60cd2180bd3d24e0043559a49710eb1e78252c476d77ccc` |
| selection amendment (countersigned) `MR002_SampleBC1_Selection.json` | `e57ffd4090751637818a6ef695722dd4c68c943859247f7693e89d2e21500c95` |
| duplicate census `MR002_DuplicateCensus.json` | `216349d1…` |

Corpus reproduced exactly: `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b`.
Run wall-clock 1462 s. The single B-C1 change vs original B: position 42, index 1434 → 3573.

## 6. Lineage note

The original frozen Sample B remains preserved and unchanged as the historical (selection-defective)
selection; it was never run to repair. B-C1 is the corrected replication sample, and its one
replacement is fully accounted for in the countersigned amendment. Sample A remains valid and
unchanged.
