# MR-002 DSR trial-statistics — GOVERNANCE BLOCKER v1.0

**Disposition: `REFUSED_DSR_TRIAL_STATISTICS_UNAVAILABLE`.** Per the owner's DSR-dispersion ruling
(2026-07-20), σ_trials must be the ddof=1 standard deviation of the **actual frozen annualized net
Sharpe** of the five countersigned trials, and — explicitly — a synthetic value, an arbitrary
constant, or an unjustified conservative bound is **not authorized**; if a trial lacks a defensible
frozen annualized net Sharpe, do **not** manufacture one and submit a blocker. This is that blocker.

## Finding (see `MR002_DSR_TrialStatistics_Census_v1.0.json`)

**Zero of the five** trials has a defensible frozen annualized net Sharpe on a comparable
daily-net-return basis:

| trial | frozen annualized net Sharpe? | why not |
|-------|-------------------------------|---------|
| MR002-A | **no** | designed config; **never backtested** (dev perf not computed) |
| MR002-B | **no** | verdict *config* frozen, but no computed Sharpe; its OOS Sharpe is exactly what the sealed run produces later |
| MR002-C | **no** | designed config; never backtested |
| RNG-001 | **no** | frozen evidence is a **qualitative** verdict (Rejected/Evidenced/Archived); no Sharpe value |
| RNG-EntryLogic | **no** | reports per-trade return / PF / day-clustered CI on a **different** OR-entry return basis; no annualized net Sharpe |

## The deeper contradiction the owner must reconcile

The prescribed procedure lists "**MR002-A/B/C validation-period annualized Sharpe**." But:
1. **A/B/C were never backtested.** The MR-002 program invariant is that **no** development,
   validation, or OOS performance has been computed. There is no realized return series for them.
2. **Validation is sealed.** `validation_authorization = false`; computing an A/B/C validation-period
   Sharpe now would require **opening sealed validation data**, which is not authorized — and would
   also be circular, since the validation opening is the very thing DSR is meant to gate.

So the reconstruction is **not executable as written**. σ_trials cannot be bound without either (a)
opening sealed data (prohibited) or (b) manufacturing statistics (prohibited).

## Options for owner ruling (none taken here)

1. **Restate the comparable-statistic set** to trials that *do* have frozen, comparable, pre-OOS net
   Sharpes — if any exist in deeper archived evidence not cited by the ledger (the ledger cites the
   v0.3 design doc for A/B/C and the qualitative summary for RNG-001).
2. **Re-scope the DSR trial basis** (e.g., DSR N and dispersion derived from a defensibly-measured
   subset, with the ledger's closed-universe conservatism preserved) — a governance change to the
   countersigned ledger, not an evaluator change.
3. **Defer σ_trials** to the point where the verdict-config's own realized statistics become
   admissible under an explicit authorization, if the intended semantics differ from what is written.
4. **Owner-frozen σ_trials with a stated, defensible derivation** — but the current ruling explicitly
   rejects an arbitrary constant, so this needs an evidenced basis, not a number.

## Boundary

No sealed data read; no performance computed; no σ_trials bound; DSR remains executable as a **pure
formula on synthetic fixtures only**, with `trial_sharpe_std` labelled `SYNTHETIC`. The evaluator
must return `REFUSED_DSR_TRIAL_STATISTICS_UNAVAILABLE` for any production DSR until this is resolved.
