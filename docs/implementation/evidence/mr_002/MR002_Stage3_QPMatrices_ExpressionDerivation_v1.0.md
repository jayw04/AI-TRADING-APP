# MR-002 Stage-3 — Expression-Level Derivation of the Model-Input Contract v1.0

**Record status:** IMMUTABLE governance artifact (docs-only; no executable code changed).
**Derives:** `MR002_Stage3_QPMatrices_InputContract_v1.0.json` (sha256 `0eca052cbd15c44b9e034ee69044198dff4fd182513dd4898b70655b1026c9a0`)
**Against implementation commit:** `8a87280071936bf23ad82c648968e810e832d12a` (tree `1a0144d9…`).
**Purpose (review requirement):** map each individual expression/slice in the frozen numerical
modules that consumes a component of `rec = (t, A_ub, b_ub, A_eq, b_eq, upper)` to the contract
clause that permits it — expression-level, not file/function-level — and argue completeness.

## 1. Canonical constraint construction — `app/research/mr002/joint_portfolio.py`

| Line | Expression | Assumption used | Clause |
|---|---|---|---|
| 374 | `C = np.vstack([A_eq, -A_ub, np.eye(n), -np.eye(n)]).T` | `A_eq`, `A_ub` are 2-D with exactly `n` columns (vstack requires equal column counts with `eye(n)`) | AEQ_2D_NCOLS, AUB_2D_NCOLS |
| 375 | `b = np.concatenate([b_eq, -b_ub, np.zeros(n), -upper])` | `b_eq` is 1-D length `meq`; `b_ub` is 1-D length `m_ub` (row-count agreement with C's blocks); `upper` is 1-D length `n`; negation requires numeric finiteness | BEQ_MATCH, BUB_MATCH, UPPER_1D_N, ALL_FINITE |
| 375 | `-upper` and the bound rows `-z ≥ -upper` with `z ≥ 0` | a nonempty feasible box needs `upper ≥ 0`; a negative `upper` is infeasible-by-construction, which must be an integrity refusal, not a solver outcome | UPPER_NONNEG |

## 2. Registered objective + acceptance — `joint_portfolio._acceptance` / `canonical_qualify`

| Line | Expression | Assumption | Clause |
|---|---|---|---|
| `coverage_signed_gap.py:112` | `H = np.diag(2.0 / t)` | division by every `t_i`: `t_i ≠ 0`, and the registered convexity requires `t_i > 0`; `t` 1-D length `n ≥ 1` | T_POSITIVE, T_1D_NONEMPTY, ALL_FINITE |
| `joint_portfolio.py:391` | `ineq = lam[meq:]` | dual layout `meq + m_ub + 2n` (slice boundary derives from `A_eq.shape[0]`) | AEQ_2D_NCOLS (meq), derived_properties.lam_layout |
| `joint_portfolio.py:393` | `stat = max(abs(H @ z − a − C @ lam))` | `H` is `n×n` (from `t` length), `C` is `n×(meq+m_ub+2n)` (from lines 374-375) | T_1D_NONEMPTY, AUB_2D_NCOLS, AEQ_2D_NCOLS |
| `joint_portfolio.py:395` | `comp = max(abs(ineq * slack[meq:]))` | same layout boundary at index `meq` | derived_properties.lam_layout |

## 3. SQRT transformation + dual reconstruction — `mr002_solver_intersection.solve_sqrt` (the frozen primary path, re-used verbatim by `coverage_signed_gap._quadprog_variant`)

| Line | Expression | Assumption | Clause |
|---|---|---|---|
| 111 (and `coverage_signed_gap.py:141`) | `s = np.sqrt(t)` | `t_i ≥ 0` for a real root, and the subsequent divisions require strictly `t_i > 0` | T_POSITIVE |
| 115 | `_qp_matrices(A_ub @ S, b_ub, A_eq @ S, b_eq, s, n)` | `A_ub @ S`, `A_eq @ S`: matrix products require exactly `n` columns; `s` becomes the transformed `upper` (length `n`) | AUB_2D_NCOLS, AEQ_2D_NCOLS, UPPER_1D_N |
| 121 | `nr = meq + A_ub.shape[0]` | dual block boundary from the row counts | BEQ_MATCH, BUB_MATCH |
| 123-124 (and `coverage_signed_gap.py:148-149`) | `lam_z[nr:nr+n] /= s` ; `lam_z[nr+n:] /= s` | division by `s_i = √t_i`: strictly `t_i > 0`; slice lengths `n`/`n` complete the `meq+m_ub+2n` layout | T_POSITIVE, derived_properties.lam_layout |

## 4. PIQP construction — `mr002_piqp.solve_piqp`

| Line | Expression | Assumption | Clause |
|---|---|---|---|
| 84 | `sp.csc_matrix(np.diag(2.0 / t))`, `-2.0 * np.ones(n)` | division by `t_i`: `t_i > 0`; `n` from `len(t)` | T_POSITIVE, T_1D_NONEMPTY |
| 85-86 | `sp.csc_matrix(A_eq), b_eq` and `sp.csc_matrix(A_ub), full(m_ub, −INF), b_ub` | 2-D matrices with `n` columns; 1-D rhs of matching row counts; finite entries (sparse conversion + PIQP reject NaN/Inf non-deterministically otherwise) | AEQ_2D_NCOLS, AUB_2D_NCOLS, BEQ_MATCH, BUB_MATCH, ALL_FINITE |
| 87 | `np.zeros(n), np.asarray(upper, float)` | box `0 ≤ x ≤ upper`: `upper` 1-D length `n`, `upper ≥ 0` for a nonempty box | UPPER_1D_N, UPPER_NONNEG |
| 94-96 | `lam = concat([−y, z_u − z_l, z_bl, z_bu])` | reconstructed dual has exactly `meq + m_ub + n + n` entries | derived_properties.lam_layout |

## 5. Certifier indexing — `app/research/mr002/certificate.py`

| Line | Expression | Assumption | Clause |
|---|---|---|---|
| 198 | `project_dual(lam, meq)` | the sign gate splits the dual at index `meq`; the multiplier count must equal `meq+m_ub+2n` (enforced upstream by `stage3_cascade.normalize`'s `WRONG_SIZED_CANDIDATE` check, whose expected length derives from the same clauses) | AEQ_2D_NCOLS, derived_properties.lam_layout |
| `gap_intervals` (exact conversion) | `as_integer_ratio()` per entry | every entry is a finite float (NaN/Inf have no integer ratio) | ALL_FINITE, CONVERTIBLE |

## 6. Entry conversion — `stage3_cascade.canonicalize` / `validate_model_inputs`

| Expression | Assumption | Clause |
|---|---|---|
| `len(rec) != 6` unpack | six components | ARITY6 |
| `np.asarray(x, dtype=float)` per component | float64-convertible, non-ragged, non-object | CONVERTIBLE, derived_properties.dtype |
| zero-row `A_eq`/`A_ub` handling in lines 374-375 (`vstack` accepts `(0,n)`) | empty equality/inequality blocks are VALID | derived_properties.empty_constraint_convention |

## 7. Completeness argument

Enumeration basis: every read of a `rec` component in the five bound modules on the cascade
numerical path (`stage3_cascade`, `coverage_signed_gap`, `solver_intersection.solve_sqrt`,
`mr002_piqp.solve_piqp`, `certificate` + `joint_portfolio._qp_matrices/_acceptance`) is one of the
expressions tabulated above — verified by searching each module for the six component names; no
other expression consumes them before the certifier completes. Assumptions deliberately **not**
required (and therefore absent from the contract): matrix rank/consistency (a rank-deficient or
inconsistent system raises inside the solver → normalized by `stage3_cascade.normalize` to the
§7 enum, never undefined behavior); a `t_i` upper bound (large `t_i` degrades conditioning but
violates no construction precondition — conditioning is the SQRT transform's purpose); signs of
`b_ub`/`b_eq` (any finite values define a valid, possibly empty, region — emptiness is a solver
outcome, not a construction defect); duplicate constraint rows (preserved by design per the
population protocol). Every tabulated assumption maps to a contract clause; conversely every
contract clause appears in at least one row above and carries a boundary fixture + the one-to-one
contract↔validator test in `test_mr002_stage3_input_contract.py`, so no clause is unenforced and
no enforcement is undeclared.

*— End. This artifact accompanies the input contract into structured Phase B for the execution countersignature.*
