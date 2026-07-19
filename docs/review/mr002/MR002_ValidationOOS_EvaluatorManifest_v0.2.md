# MR-002 Validation/OOS Evaluator — Qualification Manifest v0.2

**No committed MR-002 validation/OOS P&L evaluator exists** (confirmed: no
`apps/backend/scripts/mr002_*backtest*/*validation*` script; `app/factor_data/backtest.py` is the
momentum harness, not the residual-reversion evaluator). Therefore the finalized preregistration
REQUIRES an evaluator-qualification phase — build + freeze + qualify on synthetic and
development-free fixtures — BEFORE any unsealing. This manifest records what exists now (a
synthetic-only primitives prototype) and what the qualified evaluator must bind.

## 1. What exists now — synthetic-qualification prototype (identity-tested)

| File | SHA-256 | Purpose |
|---|---|---|
| `evaluator_prototype/mr002_valoos_metrics_prototype.py` | `62d10e5011a54ac6d380d2c28a037f0495760105603292b23d1131863f71ee8c` | frozen §7 Sharpe + §8 date-clustered block bootstrap + §9 non-inferiority diff primitives |
| `evaluator_prototype/test_mr002_valoos_metrics_prototype.py` | `082f7089cc988abcd2acca5552071ea0008af07d189e3b2d01e2d465e93076c8` | 11 synthetic-fixture + identity tests |
| `evaluator_prototype/synthetic_fixture_test.log` | `c7b352d19cfcf9edc26ceb7a3274ec296192ce15e743e3d315df804e57109349` | **11 passed** |
| `evaluator_prototype/ruff.log` | `82b3e6a6…` | clean |

**Prototype scope + identity:** imports ONLY `numpy` (+ `__future__`); no `open(`, no `duckdb`, no
`read_*` (asserted by `test_prototype_reads_no_data_sources`). It operates only on caller-supplied
return vectors — it reads NO development, validation, or OOS data. The synthetic tests prove:
- Sharpe closed-form on a known-mean/known-sd vector (exact to 1e-12);
- zero-volatility → `IntegrityStop("ZERO_VOLATILITY")` (detected by peak-to-peak == 0, robust to
  the ~1e-19 std of a constant series);
- non-finite/empty → `IntegrityStop`;
- bootstrap determinism (seed 42 bit-identical across runs; different seed differs);
- a strongly-positive synthetic → one-sided 95% lower bound > 0; a zero-centered synthetic → lower
  bound ≤ 0 (no spurious edge);
- frozen constants (block 21, resamples 2000, seed 42, confidence 0.95, √252).

This qualifies the §7/§8/§9 *metric primitives* as precise and independently reproducible. It is
NOT the full evaluator.

## 2. What the QUALIFIED evaluator must additionally build + bind (before any unsealing)

- **Portfolio construction / replay:** the registered residual-reversion cascade producing per-
  session target positions (dollar-/sector-/beta-neutral), next-open execution, 5-day hold — bound
  to `ecaa262…`-class registered code (or its designated successor) by commit + tree + container
  digest + dependency lock (pandas-ta transplant provenance carried forward).
- **Benchmark implementation** (D-BENCH: cash-zero on the neutral book) + **cost-model
  implementation** (D-COST: 10 bps/side, 50 bps/yr borrow, $10M NAV, 2% ADV clip, 1.5% new-entry
  cap) bound by file + version + sha256.
- **Gate battery:** Calmar, MaxDD, positive-folds (≥3/5), cost-stress 2×, PBO (<20%), DSR (≥95%),
  profit/regime concentration, capacity, trades (≥500/≥100/≥100), diversifier corr — each a
  frozen implementation with synthetic-fixture correctness tests.
- **Report schema:** an immutable per-window evidence record (record_type, window, disposition ∈
  {PASS, FAIL, REFUSED, INTEGRITY_STOP}, all gate values + CIs, seed, code/data/image identities,
  hashes). Expected output paths: `.../valoos/<window>/MR002_ValOOS_<window>_Report.json` (+ a
  publication wrapper analogous to the Run-5 no-overwrite publication).
- **Data-manifest identity:** the exact validation/OOS partitions of the pinned snapshot
  (`data/mr002_research.duckdb` `24e5153c…`) bound by object/version identity per §15.

## 3. Qualification acceptance (all on synthetic / development-free fixtures)

- Every metric/gate has a synthetic fixture with a known closed-form or hand-verifiable answer.
- An end-to-end synthetic run produces a full report with a deterministic disposition, reading no
  real returns.
- Identity tests prove the evaluator refuses on any commit/tree/image/data-manifest mismatch
  (`REFUSED_CODE_OR_DATA_IDENTITY`) before it can read a window.
- Zero development/validation/OOS performance is computed during qualification.

## 4. Boundary

This manifest and its prototype read no sealed data and compute no strategy performance. The
qualified evaluator is built and accepted BEFORE the owner authorizes the first validation opening;
the OOS partition stays inaccessible until a separate post-validation-PASS authorization.
