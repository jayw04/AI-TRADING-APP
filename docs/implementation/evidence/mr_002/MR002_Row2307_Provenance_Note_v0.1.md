# MR-002 row 2307 — exact-data provenance note (v0.1)

**Status:** provenance trace ONLY. No model, tolerance, solver or corpus change has been made. The
STOP remains in force and the full-population run remains halted at row 2307/3839.

**Purpose.** Establish, before any adjudication, whether binary64 values enter the exact Phase-I LP
as *model data* or only as an *initial basis / warm start*. Per the owner's ruling (2026-07-16) this
determines whether `EXACT_PHASE_I_POSITIVE` on row 2307 can be reasoned about at all.

---

## The incident

| Field | Value |
|---|---|
| Corpus index | `2307` |
| Content hash | `cfdc115e46f16226fafbe59b73890adca2f0c2f27b6f42c3ebebdce4d18ea30f` |
| Record hash | `b349d83d5cbaf9fe50fff8ee24ae67c0c4d213a95d418437494422574d83916f` |
| Bound manifest | `289a834ca328ac734c0a036d9ab22479b901f73ae12d58e7e4f1132b89de9c46` |
| n / m_ub | 13 / 31 |
| Solvers | `QUADPROG_SQRT: QUALIFIES`, `PIQP_P2: QUALIFIES` |
| Signed gap (QUADPROG_SQRT) | `[-8.674025588492589e-17, -8.674025588492588e-17]` |
| Signed gap (PIQP_P2) | `[+4.1067801459266096e-17, +4.10678014592661e-17]` |
| `exact_repair_status` | `EXACT_PHASE_I_POSITIVE` |
| Reported Phase-I optimum | `4.109e-25` (decimal rendering only — see *Not yet available*) |
| Run position | row 2307 of 3839; 2268 prior rows all `EXACT_REPAIR_OK` |
| Code | `5e5bde66ead13ab2e974e340f8fac542dae5694b` |

**Not yet available.** The **exact Phase-I optimum as a rational**, the **Phase-I basis**, and the
**artificial variables remaining positive** are NOT in the checkpoint. `solve_lp` records them only
when a `trace` dict is passed (`exact_simplex.py:543-547`), which the full-population runner does not
enable. Recovering them requires a single-row exact replay of 2307. That is a *read-only re-solve of
the recorded input*, not a rerun of the population — but it is deferred until this note is accepted,
per "provenance trace only".

---

## Value lineage

| Stage | Representation |
|---|---|
| Authoritative source | **The registered corpus itself.** `REGISTERED_CORPUS_HASH` over 3,895 instances; per-instance hash = `sha256` of `np.float64` `.tobytes()` (`fixture_hash`, `mr002_coverage_signed_gap.py:180-193`). |
| Upstream of the corpus | Market data in `mr002_research.duckdb` (`FrozenDataset`, 2013-01-02 → 2019-10-02). |
| Corpus construction | **Derived, not read.** `jp._solve_qp = capture` monkey-patches the QP entry point; `run_config(days, CONFIGS[cfg])` for cfg A/B/C replays real MR-002 portfolio construction, and `capture()` snapshots each model the pipeline builds (`mr002_coverage_signed_gap.py:246-256`). `A_ub/b_ub/A_eq/b_eq/upper/t` are therefore **outputs of float64 algebra over market data**, not source decimals. |
| Corpus serialization | `np.float64` arrays, `.copy()`, in memory; identity via `tobytes()`. |
| Deserialization | None — the corpus is regenerated in-process each run and gated on hash equality. |
| Scaling / transformation | The `sqrt` / `t`-scaled variants (`solve_sqrt`, `solve_tscaled`) are applied **inside the QP solvers only**. `capture()` stores the *unscaled original* model, so scaling does not enter the repair LP's coefficients. `_qp_matrices` is pure `vstack`/`concatenate`/negation (exact in binary64) and feeds the QP, not the repair LP. |
| Rationalization method | `to_fraction(x)` = `Fraction(*float(x).as_integer_ratio())` (`certificate.py:134-137`), documented as *"A frozen double as an exact rational. The only sanctioned entry point."* Module contract (`certificate.py:54-57`): *"Every frozen IEEE-754 input enters through its exact binary rational (`as_integer_ratio`), never through `str()`."* |
| Exact constraint coefficients | `build_standard_form` (`exact_repair.py:199-256`) forces every input through `np.asarray(..., dtype=np.float64)`, then applies `to_fraction` to **every** coefficient and RHS: `Aeq`, `Beq`, `Aub`, `Bub`, `U`, `Z`. These become `M` and `h` directly. |

### Does float enter the exact coefficients?

**YES.** This is **Case 1**. The exact LP solves the **binary64-encoded model**. Consequently
`4.109e-25` **cannot be dismissed as float noise inside that model** — it is an exact positive
result, subject only to verifying the constructor and the simplex implementation.

### Does float enter only initialization?

**Also yes, but separately, and it is not the issue.** `exact_repair.py:29-37`: *"HiGHS proposes a
BASIS. That is all. Its floating-point primal, duals and objective carry NO evidentiary weight."*
The float solver's role is Case 2 (basis proposal), but the **data** path is Case 1. The two are
independent, and it is the data path that governs feasibility.

### Case 3 (decimal strings → rationals)

**Absent by design.** `Fraction(str(x))` / `Decimal(str(x))` are explicitly rejected in favour of
`as_integer_ratio`. `directed.py:74-81` records the reason: an `mpf()`/`str()` round-trip *rounds*
(measured: 336 bits → 53), which would make a correction report zero difference everywhere and
"the zero means nothing".

---

## Trap audit

| Trap | Finding |
|---|---|
| `Fraction(float)` vs `Fraction(str(float))` | Uses `as_integer_ratio` (≡ `Fraction(float)`). **Deliberate and documented**, not accidental. |
| `Decimal(float)` vs `Decimal(str(float))` | `Decimal` is not used in this path. |
| NumPy arithmetic before rationalization | **PRESENT and load-bearing.** The entire corpus is derived by float64 pipeline algebra before any rationalization. |
| Normalization factors computed in float | Scaling lives inside the QP solvers; `capture()` records the unscaled model. Not in the repair LP. |
| Constraints from differences of nearly equal floats | **Not yet excluded.** Requires reading `joint_portfolio` construction for row 2307's specific model. Open. |
| Bounds rounded before conversion | `upper` is snapshotted as float64 and converted exactly. No pre-conversion rounding found. |
| Singleton elimination / basis reduction on float equality | **Exact `== 0.0` only, no epsilon.** `empty_rows_of` (`:138`) `np.all(A_ub[r] == 0.0)`; `canonical_order` (`:174`, `:180`) `!= 0.0`. |
| Zero filtering `if abs(x) < eps` | **Absent** in the repair-LP construction path. |
| Serialization truncating precision | Identity is `tobytes()`; no decimal round-trip. |

**Reductions applied before the LP.** Only structurally-empty inequality rows are omitted, after
exact validation that `0 <= b_j` (`b_j < 0` raises `CertificateDefect: INVALID ORIGINAL MODEL`).
Omitting `0·w <= b_j` with `b_j >= 0` is sound. Row 2307 passed this check — its stop is
`EXACT_PHASE_I_POSITIVE`, not `CertificateDefect`.

---

## A structural consequence worth recording

The standard form (`exact_repair.py:186-198`) is:

```
R1  A_eq w              = b_eq
R2  A_ub w + s          = b_ub     (structurally-empty rows omitted)
R3  w + v               = u        -> w <= u
R4  w - rho*1 + p       = z_s      -> w_i - z_i <= rho
R5  -w - rho*1 + q      = -z_s     -> z_i - w_i <= rho
c = e_rho
```

`rho` is a standard-form variable with **no upper bound**. Given any `w` satisfying R1–R3, choose
`rho = max_i |w_i - z_i|`; then `p_i = rho - (w_i - z_i) >= 0` and `q_i = rho + (w_i - z_i) >= 0`
both hold. So R4/R5 are **always satisfiable** for large enough `rho`, and therefore:

> **The full repair LP is feasible if and only if {R1, R2, R3} is feasible.**

This is the algebraic basis for the owner's decisive split. A positive Phase-I optimum on the full LP
implies **either** {R1,R2,R3} — the original registered model, exactly rationalized from binary64 —
is exactly infeasible, **or** there is a construction / simplex defect. It cannot mean "the proximity
rows were too tight", because they cannot be.

---

## Bearing on the available dispositions

Because the corpus **is** the registered artifact and there is **no authoritative non-float
representation of the derived matrices** (they are pipeline outputs, not transcribed source values),
disposition **D (`REPRESENTATION_SEMANTICS_MISMATCH`) has no comparison target for the derived
model** — the binary64 corpus is the authoritative representation within MR-002's evidentiary frame.

**D is therefore recorded as NOT APPLICABLE UNDER THE CURRENTLY REGISTERED CORPUS SEMANTICS — it is
NOT removed from the taxonomy** (owner ruling, 2026-07-16). D becomes live if, and only if, a future
governance decision rules that some upstream decimal / registered-rational representation of the
market data controls and that the derived model must be rebuilt in exact arithmetic from it. Keeping
D in the record preserves the governance trail if the authoritative representation is ever
reconsidered. That decision is explicitly NOT being made or assumed here.

The dispositions live **for this adjudication** are therefore **A**, **B**, and **C**, and the
decisive split (original constraints alone, exactly) discriminates B from A.

---

## Conclusion

**Case 1 confirmed.** Binary64 values become exact rationals via `as_integer_ratio` and **are** the
Phase-I constraint coefficients and RHS. The exact LP is solving the binary64-encoded derived model.
The reported Phase-I optimum is an exact positive result within that model and is not adjudicable by
appeal to its magnitude.

Rationalization occurs **after** float64 pipeline algebra, so the result is exact only *relative to
the already-rounded derived model* — which is precisely the frame the corpus hash registers.

**Recommended next step (owner-gated):** the decisive split — construct, exactly and independently,
(A) the original registered constraints alone and (B) the full min-L∞ repair formulation, and test
feasibility of each. Per the structural consequence above, `A feasible + B infeasible` is only
reachable via a construction/reduction defect. This requires a single-row replay of 2307 and a second
minimal constructor written independently of the production reduction path.

**Not done, and not to be done without a ruling:** no Phase-I tolerance, no rounding of 4.109e-25, no
resume from 2307, no rerun for a different basis, and no claim of exact infeasibility before the
unreduced system is independently verified.

---

## Source hashes (sha256, first 16 hex; code `5e5bde6`)

| Module | Hash |
|---|---|
| `exact_repair.py` | `7325abe5ef4fa113` |
| `exact_simplex.py` | `1403ed8dc0a5228e` |
| `certificate.py` | `1ba6aef49d0483fb` |
| `directed.py` | `7f8d44d252512f76` |
| `joint_portfolio.py` | `7e9b55c33746faa4` |
| `mr002_coverage_signed_gap.py` | `e66f273c2007b1dc` |
| `mr002_full_population.py` | `5d9a35d5522092cb` |

**Key functions:** `to_fraction` (`certificate.py:134`), `as_fraction` (`directed.py:83`),
`build_standard_form` (`exact_repair.py:199`), `empty_rows_of` (`exact_repair.py:129`),
`canonical_order` (`exact_repair.py:149`), Phase-I gate (`exact_simplex.py:542-552`),
`capture` (`mr002_coverage_signed_gap.py:203`).

**Evidence preserved:** `.mr002out/fullpop_halt_20260716/` (checkpoint md5
`9f261f5985c67f26de4f7148f2335370`, byte-identical to the c6a instance, which remains halted and
running).
