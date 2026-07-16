# MR-002 row 2307 — near-cancellation LINEAGE report v1.0

**Status: DIAGNOSTIC ONLY.** Authorised by the owner (2026-07-16) *after* disposition **A** was
established. This explains **how** an exactly infeasible derived model arose. Per the ruling it
**cannot alter row 2307's registered disposition**, and no corpus was rebuilt from rearranged
arithmetic.

**Evidence:** `MR002_Row2307_Lineage.json`, sha256
`dac050347aff1d50f0eef97a17cdc3c49b399a606c6805f8aa51e29c220cd860`.
Corpus `1d231930…` and content hash `cfdc115e…` re-bound before analysis; Farkas re-verified.

---

## Answer in one line

> **Row 2307's fixed book is empty to within float noise (`F_gross ≈ 1.7e-08`). Every constraint
> constant is therefore a near-zero difference of near-equal tiny floats, and the certificate's nine
> constants — each ~1e-9 — cancel by **16 orders of magnitude**, leaving `4.109e-25`: a residue of
> **0.28 ULP** at the scale of its own terms. The infeasibility is a rounding artefact of the
> pipeline's float algebra, made exact by rationalization.**

This does **not** make the exact result wrong. Within the registered binary64 semantics the model
*is* exactly infeasible (disposition **A**, verified Farkas certificate). What the lineage shows is
*why* such a model was constructed at all.

## The certificate is remarkably simple

The Farkas support is **9 of 45 rows**, and every weight is **exactly ±1** — a plain sum/difference
of nine constraints, not a delicate combination:

| Row | y | h (RHS) | inferred label |
|---|---|---|---|
| `A_eq[0]` | +1 | `+0.000000e+00` | dollar-neutral new entries (coeffs ±1, RHS 0 — both EXACT) |
| `A_ub[2]` | −1 | `−6.243755e-09` | net_drift± |
| `A_ub[3]` | −1 | `+3.445519e-09` | sector_gross[k] |
| `A_ub[6]` | −1 | `+3.445519e-09` | sector_gross[k] |
| `A_ub[10]` | −1 | `+8.613797e-10` | net_drift± |
| `A_ub[13]` | −1 | `+8.613797e-10` | net_drift± |
| `A_ub[16]` | −1 | `+8.613797e-10` | net_drift± |
| `A_ub[18]` | −1 | `+3.445519e-09` | sector_gross[k] |
| `A_ub[21]` | −1 | `−6.676940e-09` | sector_gross[k] |

## The cancellation

```
largest |y·h| term      : 6.676940e-09
exact surviving sum     : 4.108673e-25   (== the Phase-I optimum, confirmed)
cancellation ratio      : 1.625e+16      -> 16 orders of magnitude destroyed
relative residue        : 6.154e-17
machine epsilon (2^-52) : 2.220e-16
residue / eps           : 0.277          -> ~1 ULP at the term scale
```

Nine constants of order `1e-9` sum to `4.1e-25`. Algebraically they were meant to cancel to a value
on the feasible side of zero; in binary64 they land `0.28 ULP` on the **wrong** side. That single
misplaced ULP is the entire infeasibility.

## Where the tiny constants come from

`joint_portfolio._build_model` emits every inequality as `const + coef·z <= 0` → `coef·z <= -const`,
with the constants accumulated over the **fixed** book:

```
F_gross   = sum(p.f)                 F_net = sum(p.d * p.f)      F_beta = sum(p.d * p.beta * p.f)
sector_gross[k] : const = F_gross_k - 0.20 * F_gross
sector_net±[k]  : const = ±F_net_k  - 0.05 * F_gross
net_drift±      : const = ±F_net    - 0.05 * F_gross
gross<=1        : const = F_gross   - 1.00
```

Recovered from the matrices themselves:

- **`F_gross = 1.72275933518761803e-08`** (hex `0x3e527f7c1c000000`), from `1.00 − b_ub[28]`.
  **The fixed book is empty to ~1.7e-08** — a float-accumulation residue of positions that net to
  nothing, not a real exposure.
- `v_d` recovered as `[-1, 1, 1, 1, 1, -1, -1, -1, -1, 1, 1, 1, 1]` — directions, exact.

Every constant is then `cap × F_gross` ≈ `cap × 1.7e-08`, which is exactly the `1e-9`–`6e-9` scale
observed. The two repeated values confirm the mechanism arithmetically:

```
sector rows : +3.445519e-09   hex 0x3e2d98c6938f9490     ( ≈ 0.20 × F_gross )
net rows    : +8.613797e-10   hex 0x3e0d98c6938f9490     ( ≈ 0.05 × F_gross )
```

Identical mantissas (`d98c6938f9490`), exponents differing by exactly 2 → a factor of **4**, which
is precisely `0.20 / 0.05`. The constants are the same quantity rescaled by the caps.

## A contributing factor: the caps are not representable

| cap | value | hex | exactly representable? |
|---|---|---|---|
| `SECTOR_GROSS_CAP` | 0.20 | `0x3fc999999999999a` | **No** |
| `SECTOR_NET_CAP` | 0.05 | `0x3fa999999999999a` | **No** |
| `BETA_CAP` | 0.10 | `0x3fb999999999999a` | **No** |
| `DRIFT_BAND` | 0.05 | `0x3fa999999999999a` | **No** |
| `MAX_GROSS_NAV` | 1.00 | `0x3ff0000000000000` | Yes |

Four of the five caps carry representation error, so `cap × F_gross` is already rounded before the
subtraction that cancels. This is a contributor, not the root cause: the root cause is subtracting
near-equal quantities derived from an **empty** book.

## Why the model is degenerate here

With `F_gross ≈ 0`, every cap collapses to ≈ 0: sector gross ≤ ~0, sector net ≤ ~0, net drift ≤ ~0,
plus an exact dollar-neutrality equality and `w ≥ 0`. The feasible set is pinned to essentially a
single point at the origin, and whether that point satisfies the constraints is decided entirely by
last-ULP noise in constants that should have been exactly zero. **A degenerate, empty-book instance
is where float construction is least able to produce a well-posed model.**

Note the two exact objects in the support behaved perfectly: `A_eq[0]` has ±1 coefficients and RHS
`0x0000000000000000` — exactly zero. The failure is entirely in the accumulated constants.

## What this does and does not license

**Does:** it identifies a concrete pipeline-hardening target — model construction on a near-empty
fixed book produces constants at the noise floor, and the caps compound it. Candidate directions
(none authorised here): construct the constants exactly/rationally; or treat `F_gross` below a
declared floor as structurally zero; or require construction to certify feasibility before solver
comparison.

**Does not:** it does not overturn disposition **A**, does not license a tolerance, does not license
rearranged arithmetic as a replacement model, and does not change the qualification-predicate
finding. Row 2307 remains `EXACTLY_INFEASIBLE_REGISTERED_MODEL`.

It does, however, sharpen the governance question the owner deferred: *are pipeline-generated
binary64 models permitted to be exactly infeasible, or must construction guarantee feasibility
before solver comparison?* The lineage shows the answer matters most exactly where the book is
empty — the least interesting instances, which is a point in favour of a structural floor rather
than a numerical tolerance.

---

**Scope note.** The census established this is a **singleton**: 1 of 3,839 (1 of 3,819 distinct
models). So the mechanism, while real, is reached rarely — consistent with it requiring a
near-empty fixed book AND the ULP landing on the wrong side.
