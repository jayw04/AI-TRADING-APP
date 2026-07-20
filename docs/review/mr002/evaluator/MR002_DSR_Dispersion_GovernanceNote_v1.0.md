# MR-002 DSR cross-trial Sharpe-dispersion — OPEN governance item (note v1.0)

**Status: UNRESOLVED. Not qualified. Not a rule.** This note records — but does NOT settle — the
frozen derivation required for the DSR expected-maximum-Sharpe input. Per the owner ruling
(2026-07-20), DSR *formula* work is authorized on synthetic fixtures; the *production* derivation of
the cross-trial Sharpe dispersion is an open governance item that must be settled before full
evaluator qualification.

## What is open

The Deflated Sharpe Ratio deflates the observed Sharpe by an **expected maximum Sharpe over N
trials**:

```
SR0(N, σ_trials) = benchmark + σ_trials · [ (1 − γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e)) ]
```

with `N = 5` (the countersigned ledger) and `γ` = Euler–Mascheroni. The term **`σ_trials`** — the
**standard deviation of the Sharpe ratios across the five trials** — is currently an explicit
**synthetic fixture argument** (`trial_sharpe_std`) to the pure formula. In the committed evaluator
it is labelled `trial_sharpe_std_provenance = "SYNTHETIC"`; it is **not** derived from data and the
report does not claim otherwise.

## Why it cannot be invented from the five-trial ledger as-is

The five countersigned trials (MR002-A/B/C + RNG-001 + RNG-EntryLogic) do **not** obviously share one
comparable evaluation sample:

- MR002-A/B/C are z-entry configurations of the same frozen residual-reversion family (designed
  configs; **no pre-freeze backtest** — development performance was never computed);
- RNG-001 is a *prior* mean-reversion-family study (VWAP-deviation fade) on a **different signal,
  universe, and holding horizon**, completed and rejected;
- RNG-EntryLogic is a documented pre-freeze range-entry sub-study.

Computing a naïve standard deviation of "the five Sharpes" would silently assume a common estimation
window, universe, cost model, and horizon that these trials do **not** share. Manufacturing a number
from incomparable samples would be exactly the kind of unbacked convention the governance process
exists to prevent.

## Options to be adjudicated (NOT decided here)

1. **Owner-frozen σ_trials constant**, justified and countersigned like the trial ledger.
2. **Comparable-sample re-statement**: define one common evaluation basis on which all five (or a
   defensibly-comparable subset) trial Sharpes are computed, then take their dispersion — requires an
   explicit, frozen re-statement rule.
3. **Conservative bound**: an upper bound on σ_trials that can only *raise* the DSR hurdle, with a
   stated derivation.

## Boundary

Until this is settled and countersigned, the evaluator MUST treat `trial_sharpe_std` as a synthetic
fixture input and MUST NOT publish a validation/OOS DSR that depends on an un-provenanced dispersion.
No sealed data is read; no performance is computed; this note changes no gate, threshold, or the
countersigned `N = 5`.
