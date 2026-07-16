Overall decision

v1.1 is conceptually approved, but I would not sign the current text exactly as written. The portfolio-construction correction is sound, narrow, and appropriately governed. No additional economic redesign is needed.

Four specification inconsistencies should be corrected before the re-freeze signature. They are documentation and implementation-determinism issues—not objections to the joint LP/QP design.

The two uploaded copies are byte-identical, so there is no document-version divergence.

Freeze blockers
1. Correct the sealed-OOS contradiction

Section 2 says:

“sealed OOS … opened once”

But the document repeatedly states that validation and sealed OOS remain unread. “Opened once” would mean the sealed sample had already been consumed.

Replace it with:

Sealed OOS: 2023-02-17 through 2026-07-10, 850 sessions, config B only; currently sealed and unread, designated for one future opening after validation and all prerequisite gates.

This must be unambiguous because the untouched status of the sealed period is central to allowing v1.1 to reuse it.

2. Correct the PIT-SIC inheritance wording

Section 2 describes the inherited classification chain as:

“PIT-SIC sector chain (no forward-fill)”

That conflicts with the previously frozen effective-dated construction in which a valid SIC observation remains effective until the next accepted filing supplies a new valid SIC. Missing SIC values do not overwrite the last valid observation.

Because v1.1 is portfolio-construction-only, it must not silently alter this data rule.

Replace that phrase with the exact inherited rule:

PIT-SIC effective-dated chain: a SIC becomes effective at its filing acceptance timestamp and remains effective until the next accepted filing supplies a new valid SIC; a missing SIC does not overwrite the last valid observation. No current-classification fallback is permitted.

Alternatively, reference the precise immutable v1.0 section and hash rather than paraphrasing it.

3. Add the exact linearized combined-book equations

The conceptual formulation is correct, but post_trade = f + y + x does not explicitly register signs, sector membership, beta contributions, or the net-drift inequalities.

Add a mathematical appendix defining fixed signs d_p ∈ {−1,+1}:

G =
    Σ_j f_j
  + Σ_j y_j
  + Σ_i x_i

sector_gross_k =
    Σ_{j∈F_k} f_j
  + Σ_{j∈E_k} y_j
  + Σ_{i∈N_k} x_i

sector_net_k =
    Σ_{j∈F_k} d_j f_j
  + Σ_{j∈E_k} d_j y_j
  + Σ_{i∈N_k} d_i x_i

portfolio_beta =
    Σ_j d_j β_j f_j
  + Σ_j d_j β_j y_j
  + Σ_i d_i β_i x_i

portfolio_net =
    Σ_j d_j f_j
  + Σ_j d_j y_j
  + Σ_i d_i x_i

Freeze the inequalities:

sector_gross_k ≤ 0.20 G

−0.05 G ≤ sector_net_k ≤ 0.05 G

−0.10 G ≤ portfolio_beta ≤ 0.10 G

−0.05 G ≤ portfolio_net ≤ 0.05 G

G ≤ 1.00

Also state explicitly:

f, y, c, x, and w are nonnegative absolute NAV weights.
Directions are carried only by d.
When G = 0, the linearized constraints are satisfied without division.
y_j ≤ min(c_j, 0.015) for tradable existing positions.
A fixed position above the position cap can create EXECUTION_CONSTRAINED_INFEASIBLE.

This eliminates any remaining ambiguity between signed and absolute exposures.

4. Rename and correct “Valid no-trade day”

The document defines a valid no-trade day as Q*=0. That is not necessarily a no-trade day:

Existing positions may be reduced because y<c.
Hard exits may already have executed.
Existing positions may remain open while there are simply no new entries.

Rename it:

VALID_ZERO_ENTRY_OUTCOME

Definition:

Stages 1 and 2 are optimal and Q*=0 within tolerance. No new entries are submitted. Existing positions are retained or reduced according to the Stage-1/Stage-3 solution, and previously scheduled exits remain effective. It is a full-cash day only when no post-trade positions remain.

This distinction is necessary for fill counts, daily audit classifications, and breadth reporting.

Complete the solver acceptance specification

The selected stack is reasonable, but the current text does not fully define the solver contract. “QP status accepted” and generic references to timeout or iteration limits leave room for implementation discretion.

Before signature or in a binding solver appendix, freeze:

HiGHS settings
method="highs-ds"
Presolve on or off
Primal-feasibility tolerance
Dual-feasibility tolerance
Time limit
Maximum iterations
Dual-edge-weight strategy
Exact accepted result: for example, success=True and registered optimal status code
Treatment of warnings
Quadprog behavior
Successful normal-return behavior
Exceptions that constitute fatal solver failure
External timeout/watchdog behavior, if used
No automatic retry with another solver
No fallback solver
No matrix regularization unless explicitly registered
Residual definitions

Define the calculations—not only the thresholds:

primal_residual =
    maximum inequality violation,
    equality violation,
    and bound violation

dual_residual =
    maximum violation of multiplier-sign requirements

stationarity_residual =
    infinity norm of the Lagrangian gradient

complementarity_residual =
    maximum absolute multiplier × constraint slack

KKT_residual =
    max(
        primal_residual,
        dual_residual,
        stationarity_residual,
        complementarity_residual
    )

State the matrix sign convention and whether these are absolute NAV-weight residuals or normalized values.

Also audit both sides of the lexicographic result:

R* − ε_retention ≤ realized_R ≤ R* + ε_retention
Q* − ε_new       ≤ realized_Q ≤ Q* + ε_new
Runtime and dependency condition

It is acceptable for the final application-container digest to be recorded at Implementation Freeze. However, the candidate currently registers a Windows AMD64 quadprog wheel, while the eventual container platform is not yet stated.

Before any v1.1 structural rerun:

Update and hash the dependency lockfile.
Freeze a solver-runtime manifest containing the actual OS, architecture, wheel files, BLAS implementation, package hashes and thread settings.
Ensure the structural slice and determinism rerun use that same runtime.
If the intended container is Linux, replace the Windows-wheel hash and rerun the complete fixture suite in the Linux environment.
At Implementation Freeze, record the final application-image digest and rerun the byte-identical determinism check there.

Do not rely on Windows structural evidence to establish byte-identical behavior for a different Linux solver build.

Two smaller wording corrections
Active-sector count

The mathematical rule is:

Any positive feasible portfolio requires at least five sectors with strictly positive gross exposure.

But the reporting definition uses sector_gross > 1e-6. A mathematically positive sector below that threshold will not be counted as “active.”

Clarify:

The theoretical positive-sector count is at least five. The reported active-sector count uses the frozen 1e-6 threshold and may differ only because of that reporting tolerance.

Post-rounding language

Because fractional shares eliminate order rounding, replace “post-rounding constraint breach” with:

post-target or post-execution constraint breach

Rounding loss remains zero by construction.

What is approved without change

The following are ready for re-freeze:

v1.0’s invalidated-without-verdict disposition
Joint optimization of existing retention and new entries
Actual-gross denominators
Downward-only bounds
Retain → deploy → strictly convex allocation
Equal Stage-3 block coefficients of 1.0/1.0
HiGHS dual simplex for the LP stages
Numerical Goldfarb–Idnani active-set QP
Fractional-share research execution
Solver failure never converted into cash
Execution-constrained infeasibility as a distinct market condition
Low gross as an intended design consequence
The 24-test fixture suite
Restricted structural-slice inspection
Continued blindness of validation and sealed OOS
Re-freeze disposition

Conditionally approved for re-freeze.

Issue a corrected v1.1 containing the four freeze blockers above and the completed solver appendix. After that targeted revision, I support signing MR-002 v1.1 Research-Design Re-Freeze without another conceptual-design review. No pipeline run should occur before the corrected document is signed and the solver runtime is locked.