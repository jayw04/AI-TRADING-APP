# MR-002 Validation / OOS Preregistration v1.0.3 (DSR-resolved; supersedes v1.0.2)

**Status:** IMMUTABLE. **Governing preregistration.** A **narrow DSR resolution** of v1.0.2: the DSR
governance blocker is removed by the owner-countersigned trial ledger. **No gate, threshold, date,
fold, cost, estimator, bootstrap, D-decision, access restriction, or validation/OOS sealed status
changes vs v1.0.2** — proven by a machine diff (only DSR / version / status / supersedes /
`sequencing.validation_authorization` / schema-assertion fields differ).

Machine-readable: `MR002_ValidationOOS_Preregistration_v1.0.3.json` (`b840e01c…`).

## DSR resolution (the only change)

- **`dsr.status`** BLOCKED → **READY**
- **`dsr.trials_N`** null → **5** (owner-ratified)
- **`dsr.trial_ledger_sha256`** null → **`deda5cec0bbb72dd845633e99682849e6cf0db949e252dba956a432fcb383e9b`**
- `gates_frozen.dsr_trials_N` → 5 (mirror); `sequencing.validation_authorization` → **false**
  (explicit) — resolving the DSR prerequisite does **not** authorize validation access.

Bound by:
- **Countersigned ledger** `MR002_DSR_TrialLedger_v1.0.json` (`deda5cec…`, `TRIAL_LEDGER_COUNTERSIGNED`,
  N = 5, included MR002-A/B/C + RNG-001 + RNG-EntryLogic; exclusions retained with reasons;
  closed-evidentiary-universe statement).
- **Resolution record** `MR002_DSR_Resolution_v1.0.json` (`30b812f1…`).

## Everything else — unchanged and governing (from v1.0.2 / v1.0.1)

Corrected gate battery (`gates_frozen`: Sharpe ≥ 0.70 + bootstrap mean-return lower bound > 0;
Calmar ≥ 0.75; MaxDD ≤ 15% validation+OOS; ≥3/5 folds; A/C stability; **DSR ≥ 95% at N = 5**; net
annualized return ≥ 3%; cost stress 20/300 bps; breadth incl. ≥100 distinct entry dates; trade
concentration; annual profile; regime gates; capacity; PBO/regime-concentration/severe-cost =
diagnostics), the AAPL-authoritative windows and seam dates (validation 2020-01-13→2023-02-08 775;
OOS 2023-05-30→2026-07-01 775), five 155-session folds, six-session horizon, D-decisions (S_min
0.70, zero benchmark), Sharpe estimator, moving-block bootstrap, sequencing, sealed-access protocol,
and the governing-source census — all as frozen. The v1.0-final / v1.0.1 / v1.0.2 files are
preserved unchanged as the superseded chain.

## Boundary

Validation/OOS SEALED AND UNREAD; `sequencing.validation_authorization = false`; performance
interpretation + production promotion NOT AUTHORIZED. With DSR now READY, the **only** remaining gate
to Workstream B is owner acceptance of this v1.0.3 resolution; validation access remains a separate,
later, explicit authorization after the evaluator is qualified.
