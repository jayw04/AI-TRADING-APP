# MR-002 Validation / OOS Preregistration v1.0.2 (supersedes v1.0.1)

**Status:** IMMUTABLE. **Supersedes `MR002_ValidationOOS_Preregistration_v1.0.1`** for one immediate
reason: the v1.0.1 machine-readable companion simultaneously declared DSR `N` unbound (in
`gates_frozen`) **and** encoded a stale top-level `dsr.trials_N = 3` — governance-incompatible, since
a downstream evaluator could read the `3` and silently implement the prohibited choice. v1.0.2
removes that contradiction and makes the DSR block **non-executable** until a countersigned trial
ledger exists. **No economic rule, window, date, fold, threshold, estimator, benchmark, or
D-decision changes vs v1.0.1** — this is a machine-readable-consistency + DSR-blocking correction.

Machine-readable: `MR002_ValidationOOS_Preregistration_v1.0.2.json` (`8afdacd6…`); correction:
`MR002_ValidationOOS_CorrectionRecord_v1.0.2.json` (`9d2562e4…`).

## The correction (JSON consistency)

- **`dsr` block:** `trials_N: null`, `status: BLOCKED_UNTIL_COUNTERSIGNED_TRIAL_LEDGER`,
  `trial_ledger_sha256: null`. The old `trials_N: 3` / "A,B,C tried" text is removed. DSR remains
  the **governing significance gate**, but is **non-executable** until countersigned.
- **`pbo` block:** reconciled to **DIAGNOSTIC** (N=3, "underpowered") — reported, never a PASS/FAIL
  gate (the stale block still carried a "< 0.20" gate framing).
- **Added `dsr_schema_assertion` invariant:** if `dsr.status != READY` then `trials_N` must be null,
  validation authorization is false, the evaluator cannot reach PASS, and no validation input may be
  opened.

## DSR-N ruling applied — explicit ledger reconstruction, not A/B/C = 3

Per the owner's ruling, **A/B/C = 3 is REJECTED** (it contradicts the frozen inclusion language:
"A/B/C + RNG-001 + documented sub-studies + informal MR variants logged before freeze"). A
conservative, evidence-based **candidate ledger** is submitted:
`MR002_DSR_TrialLedger_Candidate_v1.0.json` (`3477179a…`).

- **Included (candidate):** MR002-A/B/C (z-entry 1.75/2.00/2.25), **RNG-001** (VWAP-deviation fade,
  Completed·Rejected·Evidenced — explicitly named in the frozen ledger), and the **RNG range
  entry-logic sub-study** (2026-07-06, conservative inclusion).
- **Excluded (with reasons):** RNG-002 (chartered separately/later, no pre-freeze result);
  `rsi_meanreversion.py` (reference/template, not a study); all 2026-07-12+ numerical/solver
  characterizations (post-freeze + economic series unchanged).
- **Candidate N: 4 (strict: A/B/C + RNG-001) / 5 (conservative: + RNG entry-logic).** The frozen
  "informal MR variants logged before freeze" clause is open-ended; **completeness cannot be proven
  from the repo**, so the exact N is **the owner's to reconstruct and countersign** — the analyst
  provides only the evidence-based candidate. Conservatism rule: on ambiguity, INCLUDE (higher N
  raises the DSR bar).

**The DSR gate stays BLOCKED** until the ledger is countersigned and `dsr.trials_N` +
`trial_ledger_sha256` + `status = READY` are bound by a narrowly-scoped resolution record (or
v1.0.3) that changes **no** economic rule.

## Everything else — unchanged from v1.0.1

The corrected gate battery (`gates_frozen`), windows, AAPL-authoritative seam dates (validation
2020-01-13→2023-02-08 775; OOS 2023-05-30→2026-07-01 775), five 155-session folds, six-session
horizon, D-decisions (S_min 0.70), Sharpe estimator, moving-block bootstrap, zero benchmark,
sequencing, sealed-access protocol, and the governing-source census remain as in v1.0.1 (see
`…v1.0.1.md` `dfd0987b…`). The v1.0 and v1.0.1 files are preserved unchanged as the superseded
chain.

## Boundary

Validation/OOS SEALED AND UNREAD; performance interpretation + production promotion NOT AUTHORIZED.
Workstream B (evaluator) remains STOPPED pending owner acceptance of v1.0.2 **and** countersignature
of the DSR trial ledger.
