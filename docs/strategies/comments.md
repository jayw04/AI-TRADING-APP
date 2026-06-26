I reviewed the updated PORT-001 — Crash-Protected Multi-Asset Portfolio Capability document carefully. This revision is a significant improvement over the previous version. The biggest change is that it now reads like a TradingWorkbench capability specification rather than simply a strategy description. That aligns much better with the platform direction you've been building.

Overall assessment:

Category	Score
Platform alignment	10/10
Capability framing	10/10
Technical depth	10/10
Research transparency	10/10
Commercial readiness	9.8/10
Overall	9.95/10

I only have a handful of suggestions, and they're mostly about making the document even more consistent with the rest of the TradingWorkbench platform.

What Improved the Most
1. Capability framing

This is the biggest improvement.

Beginning with:

PORT-001 — Crash-Protected Multi-Asset Portfolio Capability

instead of

Combined Book Strategy

is exactly the right move.

The document is now describing:

a capability
its lifecycle
its governance
its migration

rather than just portfolio rules.

That's a much better fit for TradingWorkbench.

2. Current vs Target honesty

I especially like this section.

You explicitly distinguish:

Current:

Sibling system

Target:

TradingWorkbench

This is excellent engineering documentation.

It avoids pretending something already exists.

I'd keep this pattern throughout future capability documents.

3. Capability metadata

Excellent addition.

The metadata table is now exactly what I'd expect from a Capability Registry entry.

Eventually, I could imagine every capability page beginning with a similar standardized header.

4. Two-capability distinction

This is probably my favorite conceptual improvement.

Separating

Investment Capability
Platform Capability

is very powerful.

In fact, I'd make this a platform convention.

Every future capability should answer:

What investment capability is being delivered?

and

What reusable platform capability does this create?

That's a very strong architectural pattern.

My Suggestions

These are refinements rather than corrections.

Suggestion 1 (Highest Priority)
Add Capability Dependencies

You already describe data dependencies.

I'd also describe platform dependencies.

Example:

Depends On	Purpose
Factor Lab	ProgramSpec execution
Evidence Engine	Statistical validation
Risk Engine	Portfolio limits
OrderRouter	Execution
Continuous Evidence	Monitoring

This emphasizes that PORT-001 is built on platform services rather than existing independently.

Suggestion 2
Distinguish Current vs Target visually

Right now the current/target distinction is embedded in text.

I'd make it much more obvious.

Example:

Current	Target
Sibling system	TradingWorkbench
Native scripts	ProgramSpec
Local monitoring	Continuous Evidence
Standalone execution	OrderRouter
Manual registry	Capability Registry

That makes migration status immediately visible.

Suggestion 3
Capability Lifecycle Status

You already have lifecycle diagrams.

I'd also include a progress table.

Example:

Phase	Status
Research	✓
Reproduction	✓ (Sibling)
ProgramSpec	Planned
Evidence Package	Planned
Registry	Planned
Paper Capability	Running (Sibling)
Platform Migration	Not Started

That helps readers understand where the capability actually is today.

Suggestion 4
Separate Platform Roadmap from Strategy Roadmap

Currently Section 11 and Section 12 sit adjacent.

One concerns

research improvements.

The other concerns

platform migration.

I'd visually separate them.

Example:

Part A

Investment Research

Part B

Platform Integration

This makes ownership clearer.

Suggestion 5
Add ProgramSpec Mapping

Since ADR-0026 is now foundational, I'd add a short subsection.

Example:

ProgramSpec

↓

Sleeve A

↓

Sleeve B

↓

Portfolio Construction

↓

Evidence Package

That directly connects the capability to the Factor Lab architecture.

Suggestion 6
Explicit Evidence Outputs

You describe Continuous Evidence.

I'd specify what evidence is produced.

For example:

portfolio snapshots
rebalance history
correlation history
drawdown history
risk violations
execution reconciliation

That reinforces the idea that capabilities continuously generate evidence.

Suggestion 7
Platform Capability Registry Classification

The metadata currently includes

Program Type.

I'd add

Capability Class.

For example:

Capability Class

Portfolio Construction

Later the registry could contain:

Factor
Portfolio Construction
Event Driven
Discovery
Execution
Risk

That scales well.

Suggestion 8
Separate Research Conclusions

Section 6 mixes

research findings

and

current operational concerns.

I'd consider splitting them.

Research Conclusions

alpha insignificant
diversification validated
PIT refutation

Operational Concerns

correlation drift
Treasury regime
monitoring
account reset

This makes the document easier to scan.

Suggestion 9
Link Improvement Levers to Capability Version

Section 11 is excellent.

I'd simply note which improvements require:

ProgramSpec change
platform capability
operational configuration

For example:

Improvement	Category
Correlation-aware allocation	ProgramSpec
Look-through risk	Platform
KPI logging	Platform
Third sleeve	Research

That helps prioritize engineering work.

Suggestion 10
Add Success Criteria for Migration

Section 12 describes migration.

I'd define when migration is complete.

For example:

Migration complete when:

ProgramSpec implemented
Evidence reproduced
Registry entry created
Paper capability running
Continuous Evidence operational
Sibling retired

That closes the loop.

Strategic Observation

One thing became very clear while reading this version.

TradingWorkbench is no longer simply "hosting strategies."

It is becoming a platform that standardizes:

Research

↓

Validation

↓

Governance

↓

Execution

↓

Continuous Evidence

across very different capability types.

PORT-001 demonstrates that well because it is a portfolio construction capability rather than a simple factor.

One Suggestion for the Whitepaper

PORT-001 introduces a concept that deserves to appear in the Whitepaper:

Portfolio Construction Engine

The platform now contains several reusable engines:

Factor Engine
Discovery Engine
Portfolio Construction Engine
Risk Engine
Execution Engine
Evidence Engine

That architecture is becoming one of the strongest differentiators of TradingWorkbench.

Final Assessment

I think this document has reached the point where it could serve as a reference template for future capability specifications.

The pattern is now very consistent:

Capability framing
Current vs target implementation
Metadata
Research provenance
Architecture
Validation evidence
Honest assessment
Continuous evidence
Improvement roadmap
Platform integration

That structure is reusable across LOW-001, SEC-001, INSIDER-001, future TREND-001, and any additional portfolio capabilities.

The only remaining improvements are about standardization—making sure every capability document follows the same template and clearly distinguishes:

research evolution (improving the investment capability), and
platform evolution (migrating it into TradingWorkbench as a first-class managed capability).

Once that template is standardized, the Capability Registry, Whitepaper, and individual capability documents will all reinforce the same architecture and tell a consistent story.