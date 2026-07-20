# MR-002 Validation/OOS Evaluator — Workstream B, Increment 1 Submission v1.0

**Scope delivered (and ONLY this):** governing-identity loader · metric primitives · gate engine ·
report-schema kernel · synthetic fixtures · qualification evidence. **Synthetic / development-free
only.** No portfolio replay, signal generation, position lifecycle, next-open execution, five-session
holding, ADV clipping, cost application, corporate actions, sealed-data adapters, CloudTrail
machinery, or validation/OOS runners was implemented. No real dataset was opened.

Governing package unchanged: preregistration **v1.0.3** (`b840e01c…`), countersigned trial ledger
(`deda5cec…`, **N = 5**), resolution (`30b812f1…`); `sequencing.validation_authorization = false`.

## 1. Changed-file inventory (all under `docs/review/mr002/evaluator/`)

| File | sha256 (16) | Role |
|------|-------------|------|
| `mr002_valoos_identity.py` | `5860c77bdd6192ae` | fail-closed governing-identity loader |
| `mr002_valoos_metrics.py`  | `5bd6d7e4ac8d3baf` | pure metric primitives (GATE + DIAGNOSTIC) |
| `mr002_valoos_gates.py`    | `85585f303027c762` | deterministic gate/verdict engine |
| `mr002_valoos_report.py`   | `ccb20e98232e03ba` | canonical report-schema kernel |
| `test_increment1.py`       | `0140a501a23d0bcf` | 14 synthetic fixtures |
| `_gen_evidence.py`         | `34225b17a627d47b` | evidence generator (reproducibility) |
| `MR002_Increment1_Qualification.json` | `eb8eca7c71c140d8` | qualification evidence bundle |
| `MR002_Increment1_CanonicalReport.json` | `9f696d886b3c3017` | canonical synthetic report |
| `MR002_Increment1_TestLog.txt` | — | captured pytest run (14 passed) |

## 2. Governing-identity loader (A)

`load_governing_identity(gov_dir)` is fail-closed and refuses (`REFUSED_CODE_OR_DATA_IDENTITY`)
BEFORE accepting any evaluator input unless ALL hold: prereg/ledger/resolution sha256 equal the
pinned identities; `dsr.status == READY`; `dsr.trial_ledger_sha256 == deda5cec…`; ledger
`decision == TRIAL_LEDGER_COUNTERSIGNED` and `record_status == IMMUTABLE`; prereg and ledger
`trials_N` agree and equal 5; `sequencing.validation_authorization is False`. **The governing N is
sourced FROM the ledger bytes** — there is no independent `TRIALS_N = 5` constant (test 13 asserts
`not hasattr(module, "TRIALS_N")`); the `== 5` line is an assertion on the loaded value, not its
source. Symlinked governing files are refused.

## 3. Metric fixture matrix (B) — synthetic, closed-form / hand-verified

Sharpe (arith mean / std ddof=1 × √252; `ptp==0` → `IntegrityStop`), annualized return, max
drawdown, Calmar, moving-block bootstrap (L=21, 2000 resamples, PCG64 seed 42, one-sided 95% lower
bound), positive-fold count, annual profile, trade concentration, regime gates, breadth, cost-stress
ingestion, capacity ingestion, and DSR at the **loaded N=5** (no default). DIAGNOSTICS: PBO (CSCV
plumbing), annual Herfindahl, positive-P&L regime concentration — each tagged `DIAGNOSTIC`.

## 4. Gate / diagnostic classification matrix (C)

Every entry is `GATE | DIAGNOSTIC | DESCRIPTIVE` with status `PASS | FAIL | N_A | ERROR`. The window
disposition (`PASS | FAIL | REFUSED | INTEGRITY_STOP`) is a pure function of the **GATE** entries
plus caller-signalled refusal/integrity-stop; DIAGNOSTIC/DESCRIPTIVE entries carry status `N_A` and
are **structurally unable** to move the disposition (tests 05, 06, 12). An all-GATE-PASS battery with
a failing diagnostic still disposes PASS; a battery with zero GATE entries disposes INTEGRITY_STOP
(no silent pass).

## 5. Report kernel (D) + determinism

Canonical serialization is sorted-key / compact-separator / ensure_ascii UTF-8; `output_hash` is the
sha256 over the record minus `output_hash`. Every report records `validation_data_read=false`,
`oos_data_read=false`, `development_performance_computed=false`, `synthetic_fixture_only=true`.
**Determinism:** identical fixture + seed 42 → byte-identical report
(`output_hash = d3412e49a36accdd73abb1f965781aa89ab39a6a0f9e47b762ae90187337fedb`, two runs
byte-identical; `report_hash()` re-verifies).

## 6. Synthetic-fixture results (E) — 14/14 PASS

1 full PASS · 2 Sharpe<0.70→FAIL · 3 mean-return LB≤0→FAIL **independently** · 4 DSR<95%→FAIL ·
5 PBO-diagnostic-fail ≠ window FAIL · 6 positive-P&L regime-concentration diagnostic no verdict
effect · 7 missing governing identity→refusal · 8 ledger hash mismatch→refusal · 9 ledger N=4 & N=3
→refusal · 10 zero-volatility→INTEGRITY_STOP · 11 identical fixture+seed→byte-identical report ·
12 diagnostic-only change→disposition unchanged · 13 loaded N=5 from ledger, no `TRIALS_N` constant ·
14 breadth/concentration/annual/regime supporting-gate closed-form checks.

## 7. DSR N=5 binding proof

`test_09` mutates the ledger `trials_N` to 4 and to 3; because the value is inside the hash-bound
ledger, the mutation changes the sha256 and the loader refuses at `HASH_MISMATCH` — a tampered N can
never be loaded. `test_13` proves the loaded N originates from the ledger and equals 5, and that no
code-constant fallback exists. The evidence bundle records `dsr_N_source` = the countersigned ledger.

## 8. Boundary confirmation

`sequencing.validation_authorization` remains **false**; no validation/OOS partition was read; no
development performance computed. Increment 1 stops here. The authorized forward sequence (owner
correction, 2026-07-20) is: **Increment 2** = cost model + synthetic trade ledger + next-open
execution semantics; **Increment 3** = portfolio replay + exposure constraints; a **later
operational increment** = sealed-access controls and adapters. No validation/OOS adapter or sealed
partition access is introduced during Increment 2. Each is a separate authorization and none is
begun.
