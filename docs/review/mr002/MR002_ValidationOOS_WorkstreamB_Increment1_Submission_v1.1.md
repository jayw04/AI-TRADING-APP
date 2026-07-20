# MR-002 Validation/OOS Evaluator — Workstream B, Increment 1 Submission **v1.1** (hardened)

Supersedes the v1.0 submission. Every v1.0-review correction is implemented; scope is unchanged
(identity loader · pure metrics · gate engine · canonical report · synthetic fixtures · qualification
evidence). **Synthetic / development-free only.** No portfolio replay, cost model, trade ledger,
next-open execution, exposure constraints, sealed-data adapters, or validation/OOS access. No real
dataset opened. Governing package unchanged (prereg v1.0.3 `b840e01c`, ledger `deda5cec` N=5,
resolution `30b812f1`); `validation_authorization` stays **false**.

**Tests: 43/43 pass · ruff clean · determinism byte-identical.** Canonical report output_hash
`90d94776b78fb499fcadb27e27336f9ab1543e31e3b3ef55df571bfde63b299f`; dispositions
`research_gate_verdict = PASS`, `run_disposition = PASS`.

## Convention ruling implemented (compounded / geometric)
- Wealth path `W_t = ∏(1+r_i)` (`compounded_wealth`); `r ≤ −1 → INTEGRITY_STOP:NONPOSITIVE_WEALTH`;
  non-finite wealth → `NONFINITE_WEALTH`.
- Net annualized-return gate = `(∏(1+r))^(252/n) − 1` (`geometric_annualized_return`). Arithmetic
  `mean×252` retained as **descriptive only** (`arithmetic_annualized_mean`), never the gate.
- MaxDD off the compounded wealth index, non-negative (`compounded_max_drawdown`). Combined MaxDD =
  one continuous validation→OOS path, **no seam reset** (`combined_max_drawdown`); OOS-only MaxDD is
  a separate path from wealth 1.0.
- Calmar = geometric annualized return / compounded MaxDD. Special cases: `MaxDD=0 ∧ return>0` →
  finite status object `{"value":null,"comparison_value":"POSITIVE_INFINITY","gate_pass":true}` (no
  IEEE Infinity serialized); `MaxDD=0 ∧ return≤0` → `INTEGRITY_STOP:ZERO_DRAWDOWN_NONPOSITIVE_RETURN`.

## The seven required corrections

**1. Required-gate registry.** `mr002_valoos_registry.py` pins all **22** governing gate conditions
(comparison, threshold, sample) and is **cross-validated against the loaded v1.0.3 `gates_frozen`** —
a divergent code threshold raises `REFUSED_CODE_OR_DATA_IDENTITY:REGISTRY_THRESHOLD_DIVERGES`. Before
any verdict the engine enforces: missing → `INTEGRITY_STOP:MISSING_REQUIRED_GATE`; duplicate →
`DUPLICATE_GATE`; unknown → `UNKNOWN_GATE`; wrong sample → `GATE_SAMPLE_MISMATCH`; wrong threshold →
`REFUSED_CODE_OR_DATA_IDENTITY:GATE_THRESHOLD`; required gate ERROR → `GATE_COMPUTATION_ERROR`. A
12-of-22 battery hard-stops (test 13). The canonical report exercises the **full** battery.

**2. Diagnostic-error treatment.** Report carries both `research_gate_verdict` and `run_disposition`.
Diagnostics never move the research verdict; a required diagnostic that is missing or errors →
`research_gate_verdict = PASS` but `run_disposition = INTEGRITY_STOP:DIAGNOSTIC_COMPUTATION_ERROR`
(no confirmatory PASS published; tests 21–22). Unfavorable-but-valid diagnostics leave the verdict
unchanged (test 20).

**3. Identity-loader hardening.** `mr002_valoos_identity.py` now adds: duplicate-JSON-key rejection
(`object_pairs_hook`), strict types, **bool-rejected-where-int** (bool is an int subclass),
basename/parent/realpath + non-symlink checks, full resolution parsing, and the complete cross-chain
— resolution→ledger (`sha256`/`N`/`included`), resolution→prereg (`to_sha256`/`to`), prereg→ledger
(`trial_ledger_sha256`), N agreement across all three (=5), record types/versions/statuses, unique
included-ID set = the countersigned five, `validation_authorization is False` (strict). Semantics are
factored into `_validate_semantics(prereg,ledger,resolution)` so tests exercise them on **tampered
in-memory dicts**, not merely the outer hash (tests 02–07).

**4. Canonical numeric representation.** `mr002_valoos_report.py`: every computed float encoded as
`{"display":…,"exact_hex":float.hex()}`; **signed zero preserved** (`-0.0 → "-0x0.0p+0"`, distinct
from `+0.0`); NaN/Infinity rejected; `allow_nan=False`; NumPy scalars rejected (np.float64 caught
*before* the float branch since it subclasses float); sets rejected; string keys only. The hash is
over the **exact** representation. Directly forecloses the Stage-3 signed-zero class (tests 40–42).

**5. DSR qualification.** Estimator pinned: observed per-obs Sharpe uses `ddof=1`; skew/raw-kurtosis
use population (n) moments; expected-max-Sharpe via the Euler–Mascheroni two-quantile form; scipy
`norm`; min sample length 20; denom guarded **before** sqrt. Independently-derived fixtures (not
produced by the implementation under test): N=1 (`0.9485960168552995`), N=5
(`0.8296873320858645`), exact expected-max-Sharpe (`SR0(N=5,σ=0.1)=0.11925940010147894`), zero
dispersion→benchmark, too-short→`DSR_SAMPLE_TOO_SHORT`, non-positive denom→`DSR_DENOM_NONPOSITIVE`,
invalid `trials_n` (bool/0)→`INVALID_TRIALS_N` (tests 32–39). **DSR dispersion is an OPEN governance
item**: `trial_sharpe_std` remains an explicit synthetic argument labelled
`trial_sharpe_std_provenance="SYNTHETIC"`; the production derivation is **not** claimed qualified —
see `MR002_DSR_Dispersion_GovernanceNote_v1.0.md`.

**6. Independent evidence fixtures.** Expected values are hand-derived or computed via numpy/scipy
primitives, not by calling the module under test: hand compounded 5-return path (geo-ann
`3.325636719291218`, MaxDD `0.02`, Calmar `166.28183596456074`), frozen block-index sequence
(`n=5,block=2,seed=7 → [4,3,4,3,4]`), the DSR literals above, the full-battery manifest, the
signed-zero test, duplicate-key JSON text, wrong resolution/ledger cross-binding, and the
diagnostic-exception path.

**7. Dependency binding.** `MR002_Increment1_Dependencies.json`: CPython 3.13.14 / numpy 2.2.6 /
scipy 1.18.0 / pytest 9.0.3 / ruff 0.15.13, each bound by its **complete** dist-info RECORD sha256
(binds every installed file's hash) + the lock-generation command + platform. PyPI wheel hashes were
unavailable at generation (no cached wheel; Norton SSL) — addable on a non-Norton env; noted in the
lock.

## Bootstrap (unchanged algorithm; validation added)
Block-index algorithm preserved (uniform start [0,n−1], non-circular, short terminal blocks,
truncate to n, 2000 resamples, PCG64 seed 42) with added parameter validation (`n≥2`, `1≤block≤n`,
`resamples≥2000`, `0<confidence<1`) and a frozen deterministic index-sequence fixture.

## Boundary
`validation_authorization=false`; no real data opened; no development/validation/OOS performance;
Increment 2 (cost model + synthetic trade ledger + next-open semantics — **not** portfolio replay or
sealed-data) is a separate authorization and is not begun.
