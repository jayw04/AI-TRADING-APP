Final ruling on D1–D4

Rev 2 resolves the four earlier freeze blockers. The solver appendix, outcome definitions, sealed-window wording, PIT-SIC inheritance, and linearized equations are now sufficiently explicit.

My rulings are:

Item	Ruling
D1 — fixed over-cap position	Approve the non-halting treatment, but remove the hard 1.5% cap from all existing positions
D2 — tolerances and warning policy	Approved
D3 — inclusion floor	Approved with two audit/terminology clarifications
D4 — Linux frozen runtime	Approved
D1 — Approved, with a broader correction

The developer is right that an untradeable position above 1.5% should not make the entire optimization infeasible merely because its individual cap cannot be cured.

More importantly, the document correctly identifies that:

v1.0 applied the 1.5% cap at entry sizing; it did not automatically trim positions that later appreciated above 1.5%.

Therefore, v1.1 should not introduce a hard post-trade 1.5% invariant. That would be an additional economic change, add turnover and costs, and contradict the stated “portfolio-construction correction only” scope.

Frozen ruling

Use:

Existing tradable positions:
0 ≤ y_j ≤ c_j

New candidates:
0 ≤ x_i ≤ w_i
w_i ≤ 0.015

The 1.5%-of-NAV limit remains a new-entry sizing cap. It is not an automatic mark-to-market trimming rule.

Consequences:

A held position may exceed 1.5% because of appreciation, NAV movement or an execution constraint.
The solver must never increase an existing position.
No new order may exceed 1.5% NAV.
No pyramiding remains unchanged.
An existing position is reduced only because of an exit or because the combined-book coupling constraints require a reduction—not solely because it appreciated beyond 1.5%.
An over-entry-cap existing position is recorded as a diagnostic, not as an LP constraint violation.

Rename the diagnostic to something that applies to both tradable and non-tradable holdings:

EXISTING_POSITION_OVER_ENTRY_CAP

Record:

permaticker
current_weight
entry_weight
amount_above_1_5pct
tradable_at_open
reduction_due_to_other_constraints

Do not classify the day as EXECUTION_CONSTRAINED_INFEASIBLE solely because of this condition.

However, the position still contributes fully to sector, beta, net and gross exposure. If it causes an uncurable coupling breach, then EXECUTION_CONSTRAINED_INFEASIBLE remains appropriate. The individual cap itself does not halt the day.

Required document changes

Remove or revise:

y_j ≤ min(c_j, 0.015)
The note describing 1.5% as a hard post-trade invariant
The changelog statement that the position cap becomes a hard post-trade invariant
Appendix A’s application of the cap to y
Fixture 17’s current wording

Revised fixture 17:

An existing position above the entry cap is fully included in accounting and coupling constraints, is never increased, is reported as EXISTING_POSITION_OVER_ENTRY_CAP, and does not by itself halt the optimization.

This preserves v1.0’s economic rule instead of adding a conservative but substantive new behavior.

D2 — Approved

Approve:

ε_retention = 1e-8
ε_new       = 1e-8

HiGHS primal feasibility tolerance = 1e-10
HiGHS dual feasibility tolerance   = 1e-10

The measured warning-and-fallback behavior is precisely the kind of silent contract violation the solver appendix should prevent. Making solver warnings fatal is appropriate.

Use a warning context around each solver call:

with warnings.catch_warnings():
    warnings.simplefilter("error")
    result = solve(...)

Any warning emitted during the solve is fatal, including an invalid-option warning that would otherwise permit SciPy to revert to a default while still returning success.

One wording correction

Because the harness permits fractional shares, there is no positive discrete “executable order quantum.” Therefore, change:

materially below any executable order quantum

to:

economically immaterial relative to the registered NAV and materially below any threshold used for portfolio decisions.

At $10 million NAV, 1e-8 equals $0.10, so the economic-materiality statement remains valid.

Fixture 18 should explicitly prove both:

An invalid below-floor tolerance emits a warning and stops the run.
The accepted runtime actually reports or otherwise verifies that 1e-10 was honored.
D3 — Approved

Approve:

ε_include = 1e-8

Treatment:

An existing exposure at or below the floor remains fully represented as a fixed constant exposure.
It is never deleted from NAV, gross, sector, net or beta accounting.
A new candidate at or below the floor is omitted and creates no order.
Hard exits are processed before the inclusion-floor classification, so a tiny position with a valid mandatory exit is still exited.
A below-floor existing position cannot increase.

I recommend recording a reason on every fixed exposure:

fixed_reason =
    NO_EXECUTABLE_OPEN
    | BELOW_NUMERICAL_INCLUSION_FLOOR

That distinction matters because only NO_EXECUTABLE_OPEN represents an execution impediment.

Two required clarifications
Rename the condition-number metric

The document uses G for total gross, while quadprog also commonly calls its Hessian matrix G. Avoid recording cond(G).

Use:

hessian_condition_number = κ(H)

with:

κ(H) > 1e10 → INVALID_RUN
Audit excluded mass

Report each day:

below_floor_existing_count
below_floor_existing_total_weight
below_floor_candidate_count
below_floor_candidate_total_weight

This confirms that the numerical floor remains economically immaterial and never silently removes meaningful exposure.

D4 — Approved

The Linux/amd64 standalone research image is the correct runtime boundary.

Approve all of the following:

No structural or determinism evidence generated on Windows
Rev-1 Windows wheel hash withdrawn
Dedicated offline mr002-research image
Frozen research store mounted read-only where practicable
No live database
No broker connection
No market-data websocket
Dependency lockfile generated and hashed inside the image
Linux quadprog artifact hash recorded
Research-image digest recorded before fixtures or structural execution
Same image used for all 27 fixtures, structural slice and determinism rerun
Final application-image digest recorded at Implementation Freeze

The solver-runtime manifest—not the developer workstation—is the authoritative execution record.

Additional approval of the completed appendix

The following rev-2 provisions are approved:

VALID_ZERO_ENTRY_OUTCOME
Fixed-only coupling infeasibility separated from numerical solver failure
Every solver warning fatal
No fallback solver or matrix jitter
Pinned highs-ds and devex
Absolute NAV-weight residuals
Lexicographic upper and lower band audits
Post-target and post-execution checks
Canonical permanent-identifier ordering
IEEE-754 hexadecimal serialization
Same-container byte-identical requirement
Cross-platform numerical-equivalence standard
Fractional shares with no rounding repair
Validation and sealed OOS remaining unread
Re-freeze disposition

MR-002 v1.1 is approved for Research-Design Re-Freeze subject only to incorporating the D1 edits above and the minor D2/D3 wording and audit clarifications.

No further conceptual review is required. The final signed version should record:

The 1.5%-of-NAV limit is a new-entry sizing cap inherited from v1.0. Existing positions are not automatically trimmed because mark-to-market exposure exceeds 1.5%; they may only decrease through registered exits or combined-book coupling-constraint reductions.

After that targeted edit:

Sign and hash v1.1.
Build the frozen Linux research image.
Emit the solver-runtime manifest.
Run all 27 fixtures.
Run the 124-session structural slice under the prohibited-inspection rules.
Stop for structural-executability adjudication before viewing performance.

Validation and sealed OOS remain sealed and reusable.