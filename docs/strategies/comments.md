Overall Positioning

The biggest issue is the title.

Today it reads like:

Combined Book Strategy

Inside TradingWorkbench, it should instead read as:

CAPABILITY: CAP-PORT-001 – Crash-Protected Multi-Asset Portfolio

The strategy is only one part.

The platform capability includes:

research
validation
governance
execution
continuous evidence
promotion lifecycle

That distinction is central to TradingWorkbench.

1. Add Capability Metadata (Highest Priority)

Near the beginning, add a capability summary.

For example:

Field	Value
Capability ID	PORT-001
Program Type	Portfolio Construction
Research Program	PORT-001
Data Dependencies	Sharadar DAILY, FMP, Yahoo, Alpaca
Current Status	Paper Capability
Capability Level	Production Candidate
Continuous Evidence	Active
Governance Status	Approved for Paper

That immediately aligns the document with the Capability Registry.

2. Connect to Evidence Engineering

Currently the document begins with the strategy.

Instead I'd show its place in the platform.

Example:

Evidence Engineering

↓

Factor Lab

↓

PORT-001 ProgramSpec

↓

Evidence Package

↓

Capability Registry

↓

Paper Trading

↓

Continuous Evidence

This is how every major capability should begin.

3. Add Research Provenance

This is probably my biggest recommendation.

TradingWorkbench isn't just executing portfolios.

It proves how they were discovered.

I'd add something like:

Stage	Status
Research Completed	✓
Independent Reproduction	✓
Statistical Validation	✓
Governance Review	✓
Paper Promotion	✓
Continuous Monitoring	Running

That reinforces the platform methodology.

4. Separate Strategy from Capability

Today the document mixes:

investment logic
implementation
operational status

I'd reorganize it into:

Capability

↓

Research

↓

Construction

↓

Execution

↓

Continuous Evidence

This matches every other major Workbench capability.

5. ProgramSpec Reference

Since ADR-0026 now exists, I would explicitly reference it.

Instead of describing the strategy as:

crash-protected momentum

I'd state:

Implemented as a ProgramSpec within Factor Lab.

That connects the document to the architecture.

6. Capability Lifecycle

I'd add a lifecycle.

Example:

Research

↓

ProgramSpec

↓

Evidence

↓

Promotion

↓

Paper Capability

↓

Production Capability

↓

Continuous Evidence

This is becoming a standard pattern across the platform.

7. Capability Classification

The Capability Registry should classify this capability.

For example:

Attribute	Value
Type	Portfolio Construction
Investment Style	Diversified Trend
Expected Role	Core Portfolio
Return Driver	Diversification + Risk Management
Alpha Classification	Not Primary
Risk Profile	Medium

This becomes useful when multiple capabilities exist.

8. Platform Capability vs Investment Capability

One thing I noticed.

This document actually describes two capabilities.

Investment capability

Crash-Protected Portfolio

Platform capability

Portfolio Construction Engine

Those should be separated.

Because eventually

LOW

MOM

SEC

INSIDER

could all reuse

the same

Portfolio Construction Engine.

That's more valuable than the individual strategy.

9. Data Capability Mapping

Since TradingWorkbench now has ADRs for data capabilities,

I'd explicitly document:

Sharadar DAILY

↓

Momentum

Yahoo

↓

Cross Asset

Alpaca

↓

Execution

Risk Engine

↓

Portfolio

That shows how multiple platform capabilities interact.

10. Continuous Evidence

Currently there is a "Current Live State."

Inside TradingWorkbench I'd rename it:

Continuous Evidence

That terminology is now consistent across the platform.

Example:

Paper Days

Current Drawdown

Current Correlation

Current Evidence Status

Capability Health
11. Connect to Other Platform Capabilities

The document currently stands alone.

I'd add a dependency diagram.

Example:

Factor Lab

↓

Momentum

↓

Crash Engine

↓

Portfolio Optimizer

↓

Risk Engine

↓

Execution Engine

↓

Continuous Evidence

That better reflects the platform architecture.

12. Capability Promotion History

This is unique to TradingWorkbench.

Near the end I'd add:

Milestone	Date
Research Complete	
ProgramSpec Frozen	
Capability Approved	
Paper Promotion	
Production Candidate	

That reinforces governance.

Biggest Architectural Observation

Reading this document alongside the recent ADRs made me realize something important.

TradingWorkbench is no longer a collection of research labs.

It is becoming a capability platform.

Today you have capabilities like:

Factor Capability

↓

Discovery Capability

↓

Portfolio Capability

↓

Execution Capability

↓

Risk Capability

↓

Continuous Evidence Capability

This document should present PORT-001 as one node in that ecosystem, not as a standalone strategy.

White Paper Alignment

This document should eventually map directly into the White Paper.

I would reference:

Evidence Engineering
Factor Lab
ProgramSpec
Capability Registry
Continuous Evidence
Portfolio Construction Framework

Those concepts now define the platform.

My Biggest Suggestion

This is the one change I'd make before anything else.

Today the document answers:

How does this strategy work?

Inside TradingWorkbench it should answer:

How does TradingWorkbench discover, validate, govern, deploy, and continuously monitor this portfolio capability?

That subtle change aligns the document with everything you've built over the past month.

Final Assessment

Viewed as a standalone investment strategy, this document is already excellent.

Viewed as a TradingWorkbench platform capability, I think it should become one of the flagship examples of the platform's methodology. Rather than emphasizing the portfolio itself, it should demonstrate the complete lifecycle:

Evidence Engineering
        ↓
Research Program (ProgramSpec)
        ↓
Statistical Validation
        ↓
Capability Registry
        ↓
Paper Promotion
        ↓
Execution Engine
        ↓
Continuous Evidence

That tells a much more powerful story than "here is a momentum portfolio." It shows exactly what makes TradingWorkbench different: it is a platform for engineering investment capabilities, not just implementing trading strategies.