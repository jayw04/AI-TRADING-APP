Approve the joint existing-retention/new-order solve for v1.1.

Requiring the existing book to be independently feasible would recreate the same scale-invariant infeasibility that invalidated v1.0. Diversifying, signal-qualified new orders may legitimately make the complete post-trade portfolio compliant. That is not concealing a breach; the relevant object is the portfolio that will exist immediately after the common execution open.

Frozen joint formulation

After processing hard exits, define:

f_j: fixed existing exposure that cannot trade at this open
y_j: retained exposure for a tradable existing position
c_j: its current exposure
x_i: new candidate exposure
w_i: its registered unconstrained inverse-volatility weight
s ∈ {−1,+1}: fixed short/long direction

Bounds:

0 ≤ y_j ≤ c_j
0 ≤ x_i ≤ w_i

No held symbol may also appear as a new-order variable. No pyramiding and no same-open re-entry remain unchanged.

All constraints apply to the combined post-trade book:

post_trade_weight = fixed exposure + retained existing + new orders

G = Σ |post_trade_weight|

sector_gross_k / G ≤ 0.20
|sector_net_k| / G ≤ 0.05
|portfolio_beta| / G ≤ 0.10
G ≤ 1.00 NAV
position weight ≤ 1.5% NAV

New entries remain dollar-neutral:

Σ new_long x_i = Σ new_short x_i

The registered net-drift band applies to the complete post-trade portfolio. The solver may retain an existing imbalance when diversifying new orders bring the resulting book within the band.

Approved lexicographic stages
Stage 1 — minimize forced liquidation
maximize R = Σ y_j

x participates in the feasibility constraints during this stage. This is intentional: eligible new positions may provide the diversification needed to retain existing positions.

Stage 2 — maximize new deployment

At the Stage-1 optimum:

R ≥ R* − ε_retention
maximize Q = Σ x_i
Stage 3 — unique closest allocation

At the first two lexicographic optima:

R ≥ R* − ε_retention
Q ≥ Q* − ε_new

minimize:

D =
    Σ_j ((y_j − c_j)² / c_j)
  + Σ_i ((x_i − w_i)² / w_i)

Every included c_j and w_i must be strictly positive; zero-bound variables are removed before matrix construction. The Hessian is then positive definite, making the Stage-3 optimum unique.

This combined objective is approved, but its equal weighting between existing-position distortion and new-order distortion is an economic rule, not a mathematical inevitability. Register the coefficient of each block explicitly as 1.0; it must not later be tuned using development performance.

Signal-strength and identifier tie-breaks should not be active optimization objectives. Permanent identifiers remain the canonical ordering for variables, matrices, logs and serialization. A materially different second Stage-3 solution is a defect.

Active-set QP ruling

Using Python quadprog directly is reasonable for this small, dense, strictly convex QP. Its documented implementation uses the Goldfarb–Idnani dual active-set method.

One wording correction is required:

Do not call it an “exact QP solver.”

Goldfarb–Idnani has finite active-set properties in mathematical arithmetic, but the Python implementation uses floating-point numerical computation. It does not produce exact-arithmetic solutions or exact KKT multipliers. Final acceptance must depend on registered primal, dual and KKT residual checks.

The concern about OSQP is otherwise valid. OSQP is an ADMM-based solver, and its optional polishing step guesses the active constraints before solving an additional system; if the guess is unsuccessful, it retains the ADMM solution.

Freeze the complete solver stack

Recommended registration:

Stages 1 and 2:
scipy.optimize.linprog(method="highs-ds")

Stage 3:
quadprog.solve_qp
Goldfarb–Idnani active-set method

SciPy’s generic method="highs" can automatically choose between HiGHS dual simplex and interior point, so explicitly pinning highs-ds removes that choice from the frozen environment.

Record:

Python version
NumPy version
SciPy version
HiGHS version
quadprog version and wheel hash
Container-image digest
Operating system and CPU architecture
BLAS/LAPACK vendor
Solver tolerances
Accepted status codes
Maximum iterations
Canonical variable ordering
Matrix and objective hashes
Determinism controls

OMP_NUM_THREADS=1 is necessary but may not control every numerical library. Pin all applicable settings:

OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1
BLIS_NUM_THREADS=1
NUMEXPR_NUM_THREADS=1

Also disable LP/QP warm starts and any adaptive behavior not required by the selected methods.

Define the byte-identical requirement as:

Byte-identical executable orders across repeated runs in the same frozen container, dependency set, CPU architecture and input snapshot.

Cross-platform runs should be required to be numerically equivalent within frozen tolerances, not necessarily byte-identical.

Serialize final floating-point values canonically—for example, IEEE-754 hexadecimal representation—rather than relying on platform-dependent decimal formatting.

Fractional-share decision

Approve fractional shares for the research harness because that is inherited from v1.0.

Register:

No integer-share rounding
No minimum-lot constraint
Target notional divided by execution price determines fractional shares
Rounding-loss fields equal zero by construction
A live implementation would require a separately governed integer/fractional-broker feasibility layer

This prevents an unregistered rounding repair from reintroducing the denominator cascade.

Important non-tradable-position case

The v1.1 formulation must distinguish fixed positions with no executable open from reducible positions.

If fixed, non-tradable exposures make the combined constraints infeasible even with:

all y = 0
all x = 0

classify the day as:

EXECUTION_CONSTRAINED_INFEASIBLE

Required behavior:

Submit no new entries.
Keep pending exits governed by the missing-open rule.
Do not misclassify the event as solver failure or an ordinary Q*=0 topology.
Record the unavoidable sector, beta and drift breaches.
Resume joint optimization at the next executable open.

A numerical solver failure remains fatal to the run; an execution-constrained infeasibility is an auditable market-data/execution condition.

Sector topology registration

Approve adding the topology report.

Since sector gross sums to total gross and no sector may exceed 20% of gross, any positive feasible portfolio requires at least five sectors with positive exposure. With exactly five active sectors, each must sit at 20% of gross.

Define an active sector as:

sector_gross > ε_active_sector

and freeze ε_active_sector.

Report per day:

Candidate sectors
Active post-trade sectors
Long/short presence by sector
Maximum sector-gross ratio
Maximum sector-net ratio
Binding constraints
Retained existing gross
New gross
Total gross
Required joint-solve fixtures

The v1.1 fixture suite should include:

The two-position counterexample: sequential repair liquidates; joint solve retains and diversifies.
Full retention when new candidates make the combined book feasible.
Minimum forced liquidation when full retention is impossible.
Empty existing book reduces exactly to the approved new-order LP/QP.
No eligible new candidates causes only necessary existing reductions.
Genuine joint R*=0, Q*=0 result.
Stage-1 and Stage-2 degenerate LP optima produce the same unique Stage-3 allocation.
Stage-3 output independent of the vertices returned by HiGHS.
Candidate and existing-position shuffle produces byte-identical orders.
No existing position increases.
No new candidate exceeds its registered starting weight.
New entries remain exactly side-matched.
Combined drift-band handling.
Fixed non-tradable position creates an execution-constrained infeasibility.
Solver failure stops the run.
Primal, dual and KKT residuals pass.
The iterative-scaling non-convergence case remains permanently rejected.
Structural-slice rule

Proceed only after v1.1 is drafted and re-frozen.

The 124-session rerun may inspect:

Retention and deployment gross
Nonzero feasible days
Valid zero-order days
Execution-constrained infeasible days
Order counts
Sector topology
Binding constraints
Solver statuses and residuals
Determinism hashes

Continue prohibiting inspection of P&L, returns, Sharpe, hit rate, drawdown and configuration comparisons until structural executability is accepted.

Final decision
Joint retention-and-entry optimization: approved.
Sequential existing-book repair: withdrawn and rejected.
Lexicographic retain → deploy → strictly convex allocation: approved.
Direct quadprog active-set QP: approved, but must be described as numerical, not exact.
Fractional research shares: approved.
Single-thread and frozen-runtime controls: approved with the expanded environment settings.
Next action: draft MR-002 v1.1 on this basis and present it for re-freeze before any pipeline run.