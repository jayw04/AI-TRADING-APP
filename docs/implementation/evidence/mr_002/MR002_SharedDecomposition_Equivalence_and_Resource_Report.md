# MR-002 v1.1 — Shared Exact Basis Decomposition: Equivalence Replay and Resource Characterization

**Status:** EQUIVALENCE REPLAY **PASS** · RESOURCE CEILINGS **PASS** · not countersigned
**Authorization:** owner ruling 2026-07-14 §6 (shared decomposition), §7 (frozen equivalence replay),
§8 (resource evidence)
**Image:** `mr002-research:v1.4`,
`sha256:aa930021c072d01a5a14f389b53bea9d338e53b71e2aac08550972060a08610a`
**Reference produced by:** commit `5e26f5b` (instrumentation only — no change to the solver's
arithmetic; 58/58 certificate fixtures unchanged)

**Performance: NOT COMPUTED. Validation and sealed OOS: SEALED AND UNREAD. Preflight and the
development run: STOPPED. The erratum: UNDRAFTED.**

---

## 1. The verdict

The shared decomposition reproduces the reference **exactly** and runs **21.3× faster**.

```
equivalence sha256   854e8652bf34544b5cbc03d92f8b7079a078803dfa6baa4b99cbdc9734495c4a   (reference)
equivalence sha256   854e8652bf34544b5cbc03d92f8b7079a078803dfa6baa4b99cbdc9734495c4a   (replay)
wall-clock           1222.4s  ->  57.4s
worst single repair  514.7s   ->  29.3s        (4.9% of the frozen 600s ceiling)
```

Identical across all 13 cases (5 analytic + the same 8 content-hashed corpus repairs), for every
item §7 enumerates: Phase-I pivot sequence, Phase-II pivot sequence, entering and leaving identity
at every pivot, basis-content hash after every pivot, Phase-I optimum, ρ\*, exact repaired point,
exact dual vector, all exact reduced costs, primal/dual objective identity, and the certificate
inputs (the canonical LP content hash) and outputs.

The equivalence hash covers the exact record only. Timings live in a separate `resources` block and
are deliberately outside it — they are the one thing that was supposed to change.

---

## 2. What was actually wrong

The previous implementation performed three exact solves per pivot and rediscovered the structure
from scratch for each:

```
B x_B = h          singleton-first + fraction-free core        cheap  — the core is small
B d   = a_enter    singleton-first + fraction-free core        cheap  — same structure
B' y  = c_B        singleton-first + fraction-free core        THE BOTTLENECK
```

The transpose was the defect, and not because it was slow arithmetic. Singleton discovery run
independently on `B'` searches for **columns of `B'` with exactly one nonzero** — but the columns of
`B'` are the **rows of `B`**, which carry 2–3 nonzeros each. No singleton exists to find. The
reduction therefore eliminated nothing, and the solve fell through to a dense Bareiss elimination on
the full basis with several-hundred-bit integers, once per pivot.

The measurement makes this unambiguous. `core_dim_max` is the largest core any solve at that basis
required:

| instance | basis | core (reference) | core (shared) |
|---|---|---|---|
| `022fb779…` | 116 | **115** | **29** |
| `0866ce11…` | 131 | **122** | **33** |
| `08bbf668…` | 70 | 64 | 9 |
| `00d93332…` | 61 | 57 | 8 |
| `0244e6f8…` | 25 | 25 | 3 |

The core was never 115. That number was the transpose solve failing to see structure that was
present the whole time. §3 of the ruling read the symptom correctly — "fails to reuse the structural
decomposition of B for its transpose" — and the corrected core dimensions are the direct measurement
of it.

## 3. Why the transpose is now free

The singleton eliminations of `B` **are** a permutation of `B` to block-triangular form, and that
form transposes at no cost:

```
rows [core | r_1 … r_s]              B_perm = [ A_core    0  ]
cols [core | j_1 … j_s]                       [   X       U  ]
```

When column `j_q` is eliminated, its only nonzero among the *live* rows is at `r_q`. Core rows are
live throughout, so `B[r][j_q] = 0` for every core row `r`; and `r_p` for `p > q` was still live at
step `q`, so `B[r_p][j_q] = 0` there too. Hence `U` is upper triangular with the pivots
`B[r_q][j_q]` on its diagonal, and the block above it is exactly zero.

Transposing gives `B_perm' = [[A_core', X'], [0, U']]` — block upper triangular, with `U'` **lower**
triangular. So the dual reuses the same eliminations walked in the opposite direction:

* **primal** — core solve, then the singletons by **back** substitution (reverse elimination order)
* **dual** — the singletons by **forward** substitution (elimination order), then the core on `A'`

The core itself is factored **once per basis**, fraction-free, on the augmented `[A | I]`, yielding
`T @ A = U`. `T` accumulates the row operations, so a later right-hand side is transformed by a
matrix-vector product rather than a re-elimination, and the transpose solve runs on the *same*
factors:

```
A = T⁻¹U   ⟹   A' = U' T⁻'   ⟹   U' w = d,   y' = T' w
```

No second singleton discovery. No second factorization. No new pivoting. This is a reuse of
structure, not a new method — which is why every pivot and every exact value is unchanged.

## 4. Authority is unchanged

The decomposition carries **no evidentiary authority**. Every value it produces — primal, direction
and dual — is verified against the **full unreduced system** (`Bx=h`, `Bd=a_enter`, `B'y=c_B`) before
it is used, exactly as §6 requires. A defect in the acceleration cannot reach a certificate; it can
only stop the run. `test_verification_catches_a_corrupted_decomposition` corrupts a single pivot of
`U` and asserts the solve raises rather than returning a wrong vector.

Verification is now the **largest single cost** in the solver (10.7s of the 29.3s worst repair, 37%).
That is the correct place for the time to be: it is the authority, and it is not a candidate for
optimization.

## 5. §8 resource characterization

Per repair, seconds. `#dec` = decompositions built (one per basis, per §6).

| case | basis | core | ref s | new s | speedup | decomp | factor | primal | direction | dual | verify | #dec | bits (num/den) | peak MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A1 single-coordinate | 7 | 2 | 0.01 | 0.01 | 0.8× | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 9 | 3/4 | 0.0 |
| A2 multi-coordinate | 10 | 4 | 0.04 | 0.02 | 1.6× | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 16 | 55/56 | 0.0 |
| A3 degenerate | 16 | 5 | 0.10 | 0.04 | 2.9× | 0.00 | 0.00 | 0.01 | 0.00 | 0.00 | 0.01 | 21 | 4/5 | 0.0 |
| A4 redundant row | 9 | 2 | 0.01 | 0.01 | 1.2× | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 11 | 3/4 | 0.0 |
| A5 infeasible | — | — | 0.01 | 0.01 | — | — | — | — | — | — | — | — | — | 0.0 |
| `00d93332…` | 61 | 8 | 33.42 | **1.61** | 20.8× | 0.16 | 0.05 | 0.19 | 0.20 | 0.17 | 0.61 | 92 | 167/166 | 0.5 |
| `022fb779…` | 116 | 29 | 558.28 | **20.72** | 26.9× | 1.61 | 2.09 | 3.43 | 2.70 | 2.07 | 7.84 | 209 | 348/355 | 1.6 |
| `0244e6f8…` | 25 | 3 | 1.34 | **0.18** | 7.3× | 0.02 | 0.00 | 0.02 | 0.03 | 0.02 | 0.07 | 45 | 166/161 | 0.1 |
| `02877e76…` | 34 | 5 | 6.18 | **0.37** | 16.7× | 0.03 | 0.01 | 0.05 | 0.05 | 0.04 | 0.15 | 46 | 225/219 | 0.1 |
| `02d95fbf…` | 31 | 2 | 1.90 | **0.24** | 7.8× | 0.02 | 0.00 | 0.04 | 0.03 | 0.02 | 0.09 | 45 | 60/112 | 0.1 |
| `06470155…` | 58 | 8 | 37.47 | **1.66** | 22.5× | 0.16 | 0.06 | 0.20 | 0.23 | 0.19 | 0.65 | 86 | 169/165 | 0.4 |
| `0866ce11…` | 131 | 33 | 514.65 | **29.26** | 17.6× | 2.31 | 2.29 | 5.30 | 3.84 | 3.19 | 10.74 | 269 | 442/447 | 1.7 |
| `08bbf668…` | 70 | 9 | 69.02 | **3.22** | 21.4× | 0.32 | 0.11 | 0.40 | 0.42 | 0.34 | 1.21 | 134 | 221/221 | 0.6 |
| **TOTAL** | | | **1222.4** | **57.4** | **21.3×** | | | | | | | | | |

**Against the frozen ceilings** (all unchanged, none raised):

| ceiling | value | worst observed | headroom |
|---|---|---|---|
| seconds per repair | 600 | **29.3** | 4.9% used |
| numerator bits | 200,000 | 442 | 0.2% used |
| denominator bits | 200,000 | 447 | 0.2% used |
| peak memory MB | 4,096 | 1.7 | 0.04% used |
| Phase-I / II pivots | 4,000 / 4,000 | 267 / 3 | 6.7% used |

The dual solve now costs approximately what the primal does (3.19s vs 5.30s on the largest instance)
rather than dominating. Integer bit growth is **unchanged** from the reference — the fraction-free
core is preserved, and integerising each core row before factoring keeps Bareiss's determinant bound
applicable (it is an integer-matrix property; feeding it rationals would let denominators compound
exactly where the bound was meant to stop them).

## 6. What this does NOT establish

**The prospective population is not measured.** The corpus repairs run here reach basis 131. The
structural maximum implied by the frozen model bounds (`n ≤ 70`, `m_ub ≤ 40`) is
`1 + m_ub + 3n = 251` — roughly twice the largest instance observed. A log-log fit across the eight
corpus points gives

```
seconds ≈ C · basis^3.16          R² = 0.9882   (8 points, basis 25…131)

  basis 131  ->   25.3s    ( 4.2% of the 600s ceiling)   [measured: 29.3s]
  basis 200  ->   96.1s    (16.0%)
  basis 251  ->  196.8s    (32.8%)
```

So the structurally largest instance the frozen model admits extrapolates to ≈ 197s — inside the
600s ceiling, but with a margin of about **3×, not 20×**. The headline 21× speedup does not carry to
the ceiling question; the exponent does, and it is unchanged (the acceleration reduced the constant
and the effective core dimension, not the asymptotic order).

That is an extrapolation, not a measurement, and it is offered as one. The prospective instance-size
distribution cannot be measured without running the preflight, which is **STOPPED**. If the ruling's
sequence reaches the full overlap population and an instance breaches 600s, the stop is unchanged:
bring the measurements, do not raise the ceiling.

**Nothing else was touched.** Still unauthorized and still absent: constraint generation, cross-pivot
eta/product-form updates, row screening, alternate pivot rules, changed Phase-I construction, changed
repair objective, changed signed-gap tolerance, changed resource ceilings, parallel pivots,
approximate rational arithmetic.

## 7. Fixtures

* `tests/research/test_mr002_exact_simplex.py` — 16 fixtures for the decomposition: the
  factorization identity `T@A == U`; Bareiss integrality; one decomposition serving all three solves
  against an independent Fraction-Gaussian reference; RHS-independence under reuse; the
  block-triangular structural claim the transpose reuse rests on; refusal on a singular basis; and a
  corrupted-decomposition test proving a defect in the acceleration stops the run instead of
  producing a wrong certificate.
* `tests/research/test_mr002_certificate.py` — 58 fixtures, unchanged, still green.
* `tests/repo/test_gitattributes_binary_integrity.py` — 5 fixtures for the §4 attribute regression
  (below).

## 8. §3/§4 — binary normalization, corrected properly

The fix shipped during the recovery (marking `*.gz` and friends `binary`) removed today's hazard but
left tomorrow's armed: the broad rule

```
docs/implementation/evidence/mr_002/**   text eol=lf
```

matches **everything** in the tree, so the next `.zip`, `.npz` or `.pkl` dropped there would be
matched by it and by no binary rule, and would be corrupted exactly as the archives were.

The policy is now a **whitelist**: the evidence tree defaults to `-text` (no conversion), and the
text formats — `.md`, `.json`, `.csv`, `.txt`, `.sha256` — are named explicitly. A new binary format
is then safe by default; a new *text* format merely goes un-normalized until someone lists it, which
is the failure that costs nothing.

**Seven of the nine tracked archives carry embedded CRLF byte pairs** (`anchors.csv.gz`: 8;
`raw_response_manifest.jsonl.gz`: 48). Any one `git add` would have destroyed them.

The regression suite never parses `.gitattributes` — the bug was invisible to a reading of that file,
since every line in it was individually reasonable and the defect was in how the patterns *composed*.
It asks Git what Git resolved (`git check-attr`) and asks Git's own object machinery whether the
round trip is lossless (`hash-object` = the clean filter; `cat-file` = what checkout materializes).
It includes a **negative control** that hashes real archive bytes under a `.csv` path and a `.csv.gz`
path and requires the blobs to *differ* — without it, the suite would pass trivially if the filter
were inert, and would not detect the corruption it exists to prevent.

## 9. Artifacts

| artifact | sha256 |
|---|---|
| `MR002_ExactSimplex_ReferenceTrace.json` | `f0662205330204ca3090573197652c7e1de0f97daf413c30e8ea20315c6492b3` |
| `MR002_ExactSimplex_EquivalenceReplay.json` | `ce110c517d659c030e5235f1d7a03721c3303d9ea4fc9ec8d037472af390b17a` |
| equivalence record (both sides) | `854e8652bf34544b5cbc03d92f8b7079a078803dfa6baa4b99cbdc9734495c4a` |

Reproduce:

```
docker run --rm -v <repo>:/work -v <out>:/out mr002-research:v1.4 \
  python /work/apps/backend/scripts/mr002_exact_simplex_equivalence_replay.py \
    --check /out/MR002_ExactSimplex_ReferenceTrace.json
```

## 10. Next in the ruling's sequence

Resource characterization passes, so §10 continues at: the full exact-repair fixture suite → the
directed-rounding correction and the **global** no-verdict-flip proof (over the full affected
population, not from representative scales) → Sample A → the predeclared disjoint Sample B → the
complete overlap population → a separately hashed evidence artifact → the superseding implementation
erratum → **stop for countersign before preflight**.
