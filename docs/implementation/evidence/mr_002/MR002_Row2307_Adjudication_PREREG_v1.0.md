# MR-002 row 2307 — exact adjudication PRE-REGISTRATION v1.0 (FROZEN)

**Frozen before execution**, per the owner ruling of 2026-07-16. Authorises exactly one question:
which of **A / B / C** holds for corpus row 2307. It does not authorise a population resume.

Preceded by, and depends on, `MR002_Row2307_Provenance_Note_v0.1.md`, which established **Case 1**:
binary64 values become exact rationals via `as_integer_ratio` and ARE the Phase-I constraint
coefficients and RHS. Adjudication is therefore about the constructor and the simplex, not about
tolerances.

---

## 1. Binding identity

| Field | Value |
|---|---|
| Registered corpus hash | `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b` |
| Row index | `2307` |
| Content hash (`fixture_hash`) | `cfdc115e46f16226fafbe59b73890adca2f0c2f27b6f42c3ebebdce4d18ea30f` |
| Record hash | `b349d83d5cbaf9fe50fff8ee24ae67c0c4d213a95d418437494422574d83916f` |
| Bound population manifest | `289a834ca328ac734c0a036d9ab22479b901f73ae12d58e7e4f1132b89de9c46` |
| Production constructor commit | `5e5bde66ead13ab2e974e340f8fac542dae5694b` |
| Production simplex commit | `5e5bde66ead13ab2e974e340f8fac542dae5694b` (same tree) |
| Rationalization semantics | `to_fraction(x) = Fraction(*float(x).as_integer_ratio())` — REGISTERED, unchanged |
| Execution environment | c6a.large (Zen 3, AVX2-only), image `mr002-research:v1.4` (`sha256:aa930021…`), `OPENBLAS_CORETYPE=HASWELL` — the environment that reproduces corpus `1d231930…` and manifest `289a834c…` exactly and that produced the stop |

**Source hashes (sha256, first 16 hex):** `exact_repair.py` `7325abe5ef4fa113` · `exact_simplex.py`
`1403ed8dc0a5228e` · `certificate.py` `1ba6aef49d0483fb` · `directed.py` `7f8d44d252512f76` ·
`joint_portfolio.py` `7e9b55c33746faa4` · `mr002_coverage_signed_gap.py` `e66f273c2007b1dc` ·
`mr002_full_population.py` `5d9a35d5522092cb`.

**Front gates (STOP if violated).** Corpus hash must equal the registered value; `fixture_hash(CORPUS[2307])`
must equal the content hash above. Row 2307 is addressed by **content hash**, not index alone.

---

## 2. Resource ceilings

Inherited unchanged from the registered path: `MAX_PIVOTS_PHASE_I = 4000`,
`MAX_PIVOTS_PHASE_II = 4000`, `MAX_SECONDS_PER_REPAIR = 600.0`. The independent tracks adopt the
same ceilings. Exceeding a ceiling is a recorded STOP, never a retry with a raised ceiling.

---

## 3. Tracks

### Track 1 — production replay with trace (read-only)

Call `exact_repair(z_s, A_ub, b_ub, A_eq, b_eq, upper, trace={})` **directly** for `z_s` from BOTH
`QUADPROG_SQRT` (PRIMARY) and `PIQP_P2` (FALLBACK). No production code changes: `exact_repair`
already accepts `trace`, and `solve_lp` populates it at `exact_simplex.py:543-547` **before** the
Phase-I gate raises at `:548`.

Capture: exact Phase-I optimum **as a `Fraction` (numerator/denominator)**; Phase-I basis; which
artificial variables remain positive **and their exact values**; artificial sum; pivot count; pivot
sequence hash; final basis hash; `M` hash; `h` hash; canonical column-order (`perm`) hash; `rows`
kept; structurally-empty rows omitted; seconds; peak memory.

The decimal `4.109e-25` is a rendering and carries no evidentiary weight.

### Track 1b — canonical permutation determinism

Re-run Track 1 after permuting the **input** constraint-row and variable order, then letting the
existing canonicalization run. Evidentiary outputs (exact Phase-I optimum, `M`/`h` hashes,
canonical order) MUST be identical. This is a determinism check. **A differing basis is not a
finding to pursue; a differing exact optimum or LP hash is a STOP.**

### Track 2 — independent ORIGINAL-model feasibility constructor

Constructs, without calling `build_standard_form`, `empty_rows_of`, `canonical_order`, or any
production repair-LP assembly:

```
A_eq w        = b_eq
A_ub w + s    = b_ub
w + v         = upper
w, s, v >= 0
```

No `rho`, no `p`, no `q`, no submitted solver point. Rationalizes the frozen binary64 values with the
**same registered `as_integer_ratio` semantics** (this is the registered semantics, not an
alternative). **Includes structurally-empty rows** — it performs no elimination, so the certificate
is checked against the unreduced system.

### Track 3 — independent FULL repair constructor

Independently constructs the full min-L∞ repair LP from the recorded row, reusing no production
constructor.

**Predicted invariant** (proved in the provenance note §"structural consequence"): `rho` is unbounded
above, so for any `w` satisfying R1–R3, `rho = max_i |w_i − z_i|` gives `p_i, q_i >= 0`. Therefore

> original feasible **⇔** full repair feasible

Tracks 2 and 3 MUST agree on feasibility. **Disagreement is itself evidence of a constructor defect**
and is recorded as such.

### Track 4 — algebraic certificate verification

No solver is an authority. Every feasibility claim is settled by arithmetic on exact rationals:

- **Infeasible** ⇒ exhibit a Farkas certificate `y` for `Mx = h, x >= 0` and verify **`y'M <= 0`
  componentwise** and **`y'h > 0`**. At a Phase-I optimum `> 0` the Phase-I dual is exactly such a
  `y`; it is reconstructed from the recorded basis (`y = B^-T c_B`) and then verified independently.
  The basis is treated as a *proposal* only — consistent with the module's own stated philosophy.
- **Feasible** ⇒ exhibit a witness `x` and verify **`Mx = h` exactly** and **`x >= 0`**.

Certificates are verified against the **unreduced** system (Track 2's constructor, empty rows
included). "A second solver also said infeasible" is explicitly NOT accepted.

---

## 4. Decision matrix (owner-frozen)

| Production full LP | Independent original | Independent full LP | Disposition |
|---|---|---|---|
| Infeasible | Infeasible **with verified certificate** | Infeasible | **A** — original exactly infeasible |
| Infeasible | Feasible | Feasible | **B or C** — compare production matrices; independently verify the simplex |
| Infeasible | Feasible | Infeasible | **B** — independent full constructor defect, unless its construction is corrected |
| Infeasible | Infeasible | Feasible | **Constructor inconsistency — NO disposition until resolved** |
| Infeasible | Feasible | production `M,h` independently **feasible** | **C** — exact simplex defect |
| Infeasible | Feasible | production `M,h` independently **infeasible** | **B** — production construction/reduction defect |

**The B/C discriminator:** does an independent exact solver / certificate checker find the
**production-generated** `Mx = h, x >= 0` feasible? If yes → the simplex is wrong (**C**). If no →
compare production `M, h` against the independent full LP coefficient by coefficient (**B**).

---

## 5. Permitted outputs

A single JSON evidence artifact plus a written adjudication report recording: the front-gate results,
all Track 1–4 captures, the decision-matrix row reached, and exactly one disposition — **A**, **B**,
**C**, or **`NO_DISPOSITION`**. Byte-identical copies retained on the instance and the laptop.

**D (`REPRESENTATION_SEMANTICS_MISMATCH`) is NOT APPLICABLE under the currently registered corpus
semantics and is retained in the taxonomy, not deleted** (owner ruling). It cannot be selected here.

## 6. Stop conditions

Corpus or content-hash mismatch · resource ceiling exceeded · Track 1b non-determinism in an
evidentiary output · Tracks 2/3 disagreement · an unverifiable certificate · any non-finite or
non-rational quantity · any result not classifiable by §4.

## 7. Explicitly NOT authorised

No population resume. No tolerance/threshold change. No Phase-I epsilon. No rounding of the Phase-I
optimum. No alternate decimal rationalization. No corpus regeneration. No arithmetic rearrangement
as a replacement model. No upstream model rebuilding. **No classification based on the magnitude of
the Phase-I optimum.** No resume-from-2307 counted as repaired. No rerun seeking a different basis.

## 8. Deferred until after a disposition

The near-cancellation lineage analysis of `joint_portfolio`'s expressions for row 2307 (upstream
operands, binary64 hex, operation sequence, resulting coefficient, exact rational, cancellation
diagnostic) is **diagnostic only**. It may explain how an exactly infeasible derived model arose; it
can never override the exact result, and it is not run inside this adjudication.
