**Strategy Lifecycle & Research Operating Model**

**v1.0 --- OWNER-ACCEPTED IMPLEMENTATION BASELINE**

*Durable operating model for discovering, validating, promoting,
monitoring, modifying, retiring, and replacing investment strategies.
Companion to the ATP Implementation Plan and the governed frozen
research specifications.*

Accepted: 2026-09-02 · Supersedes the non-governing v0.1 Discussion
Draft and v0.2 Final Review Draft. This v1.0 is the implementation
baseline once merged at the canonical repository path and its SHA-256 is
recorded in custody.

  ----------------------------------------------------------------------------------------------
  **Field**      **Value**
  -------------- -------------------------------------------------------------------------------
  Status         OWNER-ACCEPTED IMPLEMENTATION BASELINE --- becomes repository-governing when
                 merged at the canonical path and its SHA-256 is recorded in custody.
                 Operational actions still require their own ATP/owner authority.

  Canonical path docs/design/Lifecycle/Strategy_Lifecycle_and_Research_Operating_Model_v1_0.md
                 (§0.3)

  Purpose        Define the recurring, evidence-driven strategy lifecycle and the vocabulary,
                 gates, and controls that make it repeatable --- without carrying current-state
                 facts, priorities, or authority.

  Relationship   ATP (AlgoTraderPlus_v1_4_1_ImplementationPlan_v1_0_3 and successors) remains
  to ATP         the current execution plan: priorities, enablers, platform work, PAPER
                 operations, owner gates, and all observation-dated state. This model changes
                 none of that.

  Relationship   Each frozen specification (currently
  to frozen      NewStrategy_FrozenResearchSpecs_2026-09-01_v1_2_FINAL) is the authoritative
  research specs prospective experiment contract for its batch. This model may not reinterpret,
                 extend, or repair any frozen spec.

  Authority      Frozen registrations / sealed evidence / accepted ADRs / explicit owner rulings
  position       \> ATP (current state and priorities) \> this model (default lifecycle
                 procedure) \> subordinate task lists. See §0.1.

  Core objective Continuously generate robust, deployable, net-profitable strategies at
                 acceptable risk, and terminate or change strategies when prospective evidence
                 no longer supports their thesis --- at a throughput that never trades away
                 evidentiary integrity.
  ----------------------------------------------------------------------------------------------

0\. Document control and authority position

0.1 Authority order

This model sits **below** ATP in the authority hierarchy, not above it.
It is the more durable and less specific document; ATP is the more
specific one for anything that is true \*now\*. The ATP developer rule
applies unchanged: if this model conflicts with a frozen registration,
sealed evidence record, accepted ADR, explicit owner ruling, or the
current ATP, stop and use the higher-authority artifact. Do not
reconcile by inference.

Consequences:

-   This model never sets a priority, opens a lane, or schedules a
    batch. A sentence here that reads as a priority is a **proposal for
    an ATP successor version**, not an instruction (v0.1 §17 contained
    several; they were removed from the durable v1.0).

-   This model never grants research capital, implementation, account
    binding, scheduler change, deployment, PAPER activation, retirement
    execution, or order authority. Every such act requires its own owner
    ruling under the ATP gate discipline.

-   Where this model and ATP §1 describe the same admission test, ATP
    §1's wording controls.

0.2 What this document contains --- and deliberately excludes

The value of a durable layer is that it does not go stale. To keep it
durable, this document contains **no observation-dated facts**: no
commit SHAs, deployment pins, corpus day counts, verdicts, account
states, or candidate dispositions. Those live in ATP's compact
current-state block and in custody records.

0.3 Versioning and custody

-   Versions follow the ATP convention: a predecessor is never mutated;
    its SHA-256 is recorded; CURRENT moves only on merge.

-   Because the body carries no state, this document needs **no state
    syncs**. A change to lifecycle states, verdict vocabulary, gate
    definitions, or authority position requires a successor version with
    a review pass. Editorial corrections may ship as a patch version.

-   Documentation custody of this model grants nothing operational,
    consistent with ATP §2.6 and §10.

1\. Executive directive --- operate a strategy factory

The platform is an evidence-driven strategy lifecycle system. Its
purpose is not merely to backtest ideas or to operate a fixed set of
strategies. It should repeatedly convert market and fundamental evidence
into testable hypotheses; validate them under prospective, reproducible
rules; promote survivors into PAPER; monitor the continuing validity of
each thesis; modify strategies only when new prospective evidence
justifies a change; and retire or replace strategies whose thesis is no
longer supported.

Governing lifecycle: DISCOVER → HYPOTHESIS → CENSUS → FREEZE → VALIDATE
→ PROMOTE → PAPER → MONITOR → KEEP / MODIFY / PAUSE / RETIRE / REPLACE →
DISCOVER AGAIN

Governance, infrastructure, data engineering, evidence custody, and
execution controls are means to make this lifecycle trustworthy and
repeatable. They are not substitutes for strategy throughput.
Conversely, desired strategy count, stakeholder presentation needs,
available PAPER accounts, calendar cadence, or schedule pressure must
never determine a research verdict or a lifecycle disposition.

> *R1 --- CENSUS and PROMOTE added to the lifecycle. CENSUS is the
> data-feasibility / NO-START gate that ATP §7.1 already uses for SF1
> (zero strategy code; STOP if PIT coverage, OOS depth or power is
> inadequate). PROMOTE is the separate owner decision between a research
> verdict and PAPER operation; v0.1 folded it into VALIDATE → PAPER,
> which blurred the boundary the frozen spec draws explicitly ("Research
> PASS creates no ... PAPER activation").*

2\. Three-document operating hierarchy

  ---------------------------------------------------------------------------------------
  **Document**       **Primary    **What it controls**               **What it may not
                     role**                                          do**
  ------------------ ------------ ---------------------------------- --------------------
  Strategy Lifecycle Durable      Lifecycle states and vocabulary;   Set priorities;
  & Research         operating    discovery loop; census, freeze and carry current state;
  Operating Model    model        validation contract shape;         reinterpret any
  (this document)                 promotion gate shape; PAPER        frozen spec or
                                  learning rules; adaptation         observed result;
                                  dispositions; metrics; stakeholder grant
                                  capability model.                  PAPER/production
                                                                     authority.

  ATP Implementation Current      Near-term priorities;              Change a frozen
  Plan (current      program      strategy-direct work; required     registration or
  version)           execution    enablers; platform implementation; sealed evidence;
                     plan         PAPER operations; owner gates;     grant live mutation
                                  observation-dated state.           by implication.

  Frozen Research    Candidate /  Prospective hypotheses, dataset    Argue for promotion;
  Specification(s)   batch        identities, PIT rules, signals,    change after any
                     experiment   parameters, estimators,            result is observed;
                     contract     falsifiers, acceptance rules,      transfer evidence to
                                  decisive-run protocol,             another program.
                                  inherited-mechanism bindings,      
                                  owner parameters.                  
  ---------------------------------------------------------------------------------------

Authority remains with the more specific frozen or accepted artifact for
the decision it governs. **Conflict rule:** a conflict between this
model and ATP is resolved in ATP's favour for current execution, and is
recorded as a candidate finding for the next successor of whichever
document is wrong. A conflict with a frozen spec is resolved in the
spec's favour always; the spec is not reopened.

3\. Strategy-first planning principle

ATP §1's admission test controls. Every active task must, before
engineering time is allocated: (1) name the strategy or economic
decision it serves; (2) state how it can improve net P&L, risk-adjusted
return, capacity, execution cost, drawdown, or time-to-verdict; (3)
state a measurable stop condition or time-box; (4) state the next
conversion gate; (5) otherwise **DEFER / MOVE TO OPS / STOP**. In
lifecycle terms, each task must also name the capability it enables:
DISCOVER, CENSUS, VALIDATE, PROMOTE, PAPER, MONITOR, MODIFY, RETIRE, or
REPLACE.

> *R2 --- v0.1 said work without a conversion target "should normally be
> deferred". "Normally" is a loophole ATP §1 does not have. Removed; the
> ATP wording is adopted verbatim.*

  ------------------------------------------------------------------------------------
  **Class**         **Admission question**         **Illustrative examples**
  ----------------- ------------------------------ -----------------------------------
  STRATEGY-DIRECT   Does it create, validate,      A frozen candidate's decisive run;
                    improve, monitor, modify,      a prospective successor hypothesis;
                    retire, or replace a named     a governed retirement of a named
                    investment mechanism?          strategy.

  REQUIRED ENABLER  Is it the minimum capability   PIT data controls; trusted
                    without which strategy-direct  reference-price path; the
                    work cannot run safely or      retirement control; reproducible
                    produce admissible evidence?   evidence records; the lifecycle
                                                   registry (§13).

  PLATFORM / OPS    Useful work with no current    Defer unless an operational or
                    strategy conversion target?    security risk independently
                                                   requires it (ATP §8 list applies).
  ------------------------------------------------------------------------------------

4\. Continuous opportunity discovery

Discovery is a continuous lane, not an activity performed only after the
queue is empty. New observations may create candidates while other
strategies are in validation or PAPER. Sources include: cross-sectional
anomalies or factor behaviour that becomes statistically and
economically interesting; regime-specific failures or strengths in
existing strategies; new data sources or materially improved PIT
coverage; execution or microstructure observations revealing a durable
implementable edge or cost reduction; portfolio gaps (defensive,
diversifying, convex, income, event, or return-source exposure); and a
failed or weakening strategy whose failure mode suggests a distinct
successor hypothesis (§11).

Discovery output is a candidate hypothesis, not authority. Before a
candidate may be frozen it must have an economic rationale, a
falsifiable mechanism, defined data requirements, an expected portfolio
role, a trial-ledger entry (§5.2), and a passed census (§5.1).

4.1 Discovery boundaries (mechanisms, not intentions)

-   **Data-partition discipline.** Discovery runs on exploration data
    only. Any partition sealed or designated for decisive validation of
    any program is out of bounds to discovery; touching it consumes it
    (ATP §12: no exploratory holdout access before pre-registration).
    The evidence record for a decisive run must show that its validation
    window was not read by the discovery that motivated it.

-   **Discovery is ledger work, not engineering by default.** Recording
    an observation, a hypothesis, and a falsifier costs nothing and
    needs no authority. Building tooling for discovery (feature
    libraries, census automation, screeners) is engineering and must
    pass ATP §1 and clear the ATP §8 exclusions.

-   **Discovery output is not a signal.** Candidate, watchlist, or
    screener output may not touch order, risk, sizing, or any governed
    strategy's inputs without a separately registered economic mechanism
    (ATP §7.4, §12).

-   **Cross-program isolation.** Programs share infrastructure
    (identity, calendar, PIT/as-of, evidence metadata) but never share
    evidence. A terminated or rejected program transfers no evidence to
    a successor; the successor's decisive evidence is generated fresh
    under its own frozen spec.

5\. Candidate funnel and research throughput

The platform deliberately maintains a funnel rather than a single-file
queue. Counts below are planning targets for capacity, **never**
acceptance criteria and never inputs to any verdict.

  ------------------------------------------------------------------------------
  **Stage**      **Illustrative   **Required output**
                 operating        
                 target**         
  -------------- ---------------- ----------------------------------------------
  Opportunity    10--20 active    Ledger entry: evidence note / anomaly /
  observations                    portfolio need

  Research       5--10            Economic mechanism + falsifier + expected
  hypotheses                      role; trial-ledger citation

  Census passed  as many as pass  CENSUS_PASS / CENSUS_WAIT --- \<reason\> /
  (NO-START)                      CENSUS_STOP --- \<reason\>; zero strategy code
                                  written

  Frozen         3--5 per batch   Merged, custodied prospective spec; pinned
  candidates                      dataset identities; inherited-mechanism
                                  bindings; owner parameters bound

  Decisive       2--4 per cycle   PASS / REVISE / REJECT / NOT EVALUABLE,
  validations                     recorded whatever it is

  PAPER          1--3 when        Separate implementation / readiness /
  promotions     evidence earns   activation authority
                 it               
  ------------------------------------------------------------------------------

A low promotion rate is not failure if weak ideas are rejected
efficiently. Optimise for credible learning and time-to-decision, not
for manufacturing PASS results.

5.1 Census (NO-START) gate

Between HYPOTHESIS and FREEZE every candidate passes a read-only census
that measures, for the data it would use: minimum/maximum dates, PIT
keys and floors, eligible-security count, missingness, spine freshness,
and OOS / statistical-power feasibility. The census writes **zero
strategy code**, produces no return series, and cannot generate a
verdict. Outcomes: CENSUS_PASS (freeze may proceed), CENSUS_WAIT ---
\<reason\> (temporary evidence/data condition; the candidate waits under
a time-box), or CENSUS_STOP --- \<reason\> (the proposed candidate is
not feasible under the declared corpus/contract). These are census
outcomes, not research verdicts. This generalises ATP §7.1 and the
frozen spec's PIT-trap rules into a standing stage so that PIT traps are
discovered before freezing, not inside a decisive run.

5.2 Trial ledger and multiplicity

Throughput multiplies the multiple-comparison problem. A funnel that
freezes 3--5 candidates per batch, several batches per year, will
produce spurious PASS results at a predictable rate unless every shot is
counted. Therefore:

-   Every hypothesis receives a trial-ledger entry at creation,
    recording prior exposure of the same history to related tests (the
    frozen spec already does this per batch under §0.5.4).

-   Every frozen spec cites its ledger entry and states, prospectively,
    whether cross-candidate correction applies and why.

-   The **promotion** decision (§7) must weigh shots taken in the
    family, not only the individual verdict.

-   The operating scorecard (§15) reports **decisions delivered** and
    **shots taken**, never PASS count or PASS rate. This is the
    mechanism that keeps throughput targets from becoming PASS pressure:
    no metric anyone is measured on improves by a PASS rather than a
    REJECT.

> *R3 --- v0.1 stated the throughput objective and stated that counts
> "must never pressure a candidate toward PASS" but supplied no
> mechanism. §5.1, §5.2 and §15 supply three: the census gate, the
> ledger citation, and PASS-neutral counting.*

6\. Canonical vocabulary and state model

This section proposes the platform's canonical lifecycle vocabulary
(owner decision LD-1). Each term is mapped to the wording already in use
in ATP and the frozen specs so that adoption changes labels, not
meanings.

6.1 Lifecycle states

  --------------------------------------------------------------------------
  **State**    **Definition**                      **Existing wording it
                                                   absorbs**
  ------------ ----------------------------------- -------------------------
  DISCOVER     Observation recorded in the ledger; ATP §7.4 "candidate
               no hypothesis yet.                  observation"; DISC /
                                                   Opportunity output

  HYPOTHESIS   Economic mechanism, falsifier,      ATP §7.4 "mechanism →
               expected role, data requirement,    cost model →
               ledger citation written.            falsification →
                                                   discovery-ledger
                                                   citation"

  CENSUS       Read-only data-feasibility          ATP §7.1 SF1 NO-START
               measurement; NO-START; zero         census
               strategy code.                      

  FREEZE       Prospective spec merged to the      Frozen spec §Freeze
               governed branch with pinned         record, §0.6, §0.7,
               identities, bindings, owner         custody gate
               parameters. Decisive execution      
               authorised only after MERGED        
               custody.                            

  VALIDATE     One decisive run per candidate      Frozen spec §0.5; ATP
               under the frozen protocol; result   §7.4 "untouched
               recorded whatever it is.            prospective validation"

  PROMOTE      Separate owner decision:            Frozen spec Execution
               implementation, readiness,          boundary; ATP §5.2 chain;
               account/capital, activation ---     "promotion decision"
               each its own gate.                  

  PAPER        Governed operation in a paper       ATP §5.3;
               account under a frozen observation  EVIDENCE_NOT_FEEDBACK
               protocol; evidence, not feedback.   

  MONITOR      Scheduled and event-driven thesis   ATP §5.3 observation
               review against a frozen             metrics; thesis review
               thesis-health envelope.             (new)

  KEEP /       Adaptation dispositions (§9).       ATP §5.3 KEEP / DEMOTE
  MODIFY /     RETIRE is terminal for the          (DEMOTE maps to PAUSE or
  PAUSE /      identity.                           RETIRE, §9); ATP §12 "any
  RETIRE /                                         revival is a new
  REPLACE                                          prospective program"
  --------------------------------------------------------------------------

6.2 Verdict and disposition vocabularies (kept distinct)

  ---------------------------------------------------------------------------------------
  **Vocabulary**   **Values**          **Used by**    **Rule**
  ---------------- ------------------- -------------- -----------------------------------
  Research verdict PASS · REVISE ·     VALIDATE       Decided by frozen rules;
                   REJECT · NOT        (frozen spec   sensitivities never decide; NOT
                   EVALUABLE           primary        EVALUABLE is not REJECT and is
                                       metrics)       never silently converted.

  Execution status STOP (pipeline /    Decisive-run   Describes the run, not the
                   data defect, defect pipeline       economics; carries no economic
                   record filed) ·                    verdict.
                   INTEGRITY_FAILURE ·                
                   CONSUMED                           

  Program          GO · HOLD (with     ATP owner      Owner act; expected disposition
  disposition      stated extension) · gates          recorded prospectively where
                   STOP ·              (e.g. G3)      required.
                   STOP-FOR-CYCLE                     

  Census outcome   CENSUS_PASS ·       §5.1           Never a verdict on the hypothesis.
                   CENSUS_WAIT ---                    
                   \<reason\> ·                       
                   CENSUS_STOP ---                    
                   \<reason\>                         

  PAPER /          KEEP · MODIFY ·     MONITOR        Opened by triggers; never
  adaptation       PAUSE · RETIRE ·    reviews (§9)   predetermined by them. PAPER
  disposition      REPLACE                            results may support KEEP, PAUSE or
                                                      RETIRE but never upgrade the frozen
                                                      economic verdict (ATP §5.3).
  ---------------------------------------------------------------------------------------

6.3 Identity register

Four identifiers are in use and must not be conflated:

-   **Program ID** --- a mechanism family and its research history
    (MOM-001, LOW-001, SEC-001, MF-001). The trial ledger is kept per
    program.

-   **Candidate ID** --- batch-local label inside one frozen spec (C1,
    C2, C3). Meaningless outside that spec; always cite with the spec
    identity.

-   **Strategy ID / account binding** --- a deployed instance (Strategy
    8 on a paper account). Created only by PROMOTE; released only by
    RETIRE.

-   **Version** --- V1/V2 marks an economic change and therefore a **new
    candidate with its own pre-registration** (MF-001 V2 = C2). A patch
    version (v1.0.x) marks a non-economic operational change within the
    same identity, with a conformance check (§7.2). This is the answer
    proposed for LD-6.

> *R4 --- v0.1 mixed "Strategy 8", "LOW-002", "C3" and "Strategy 9"
> without a register. "Strategy 9" and "Mechanism-C" appear in neither
> ATP v1.0.3 nor the frozen spec v1.2; they must be defined (or cited)
> before they appear in a governing document.*

7\. Prospective validation contract

The frozen spec is the contract; this section states the invariants
every future spec must satisfy so that batches are comparable.

-   Freeze before any outcome observation: hypothesis, dataset identity
    (path, bytes, SHA-256, re-verified before each run), PIT keys and
    floors, signal, universe and tradability screen, costs, estimator
    (pinned artifact + SHA-256), parameters and seeds, primary metrics,
    falsifiers, verdict rules, allowed sensitivities, prohibited
    changes.

-   **Inherited mechanisms are bound by artifact reference + SHA-256**
    (frozen spec §0.6). Prose inheritance ("unchanged") is not a
    binding. A candidate with an unbound inheritance is STOPPED, not
    run.

-   **Owner parameters are economic judgments and are bound before the
    affected run** (frozen spec §0.7 pattern). Proposed defaults are
    stated; the owner may change them only before the run.

-   **Execution-input freeze:** the complete parameter artifact, its
    SHA-256, the seeds, and the exact research-code commit are recorded
    before any result is read. No post-result seed or parameter
    substitution.

-   **Custody gate:** decisive execution begins only after the spec is
    MERGED to the governed branch --- not a local commit, not an open
    PR.

-   **One decisive run per candidate.** The standing default permits a
    replacement attempt only after a documented, result-blind
    execution/pipeline or dataset failure, with the interruption/defect
    record sealed before the replacement attempt and a separate owner
    ruling authorising that attempt. A candidate-specific frozen
    specification may narrow this default and therefore controls. No
    economic output from the failed attempt may be used to motivate the
    replacement. Result-motivated reruns are prohibited.

-   Observed results may not cause window recuts, parameter
    substitution, estimator changes, comparator invention, universe
    re-cutting, or acceptance-rule repair.

-   **NOT EVALUABLE** is the correct verdict when the evidence contract
    cannot support the intended decision. It preserves uncertainty; it
    is not REJECT, and it is not converted to PASS or REJECT by later
    argument.

-   **Sensitivities never decide.** They inform robustness language and
    cannot flip a verdict in either direction.

-   A result whose inputs cannot be re-identified is not evidence.

-   A research PASS creates no production implementation, account
    binding, scheduler, deployment, PAPER activation, or order
    authority.

> *R5 --- v0.1 §6 read "sensitivity analyses ... cannot rescue a failed
> primary verdict unless prospectively decisive". A prospectively
> decisive metric is a primary metric by definition, so the clause was
> self-contradictory and created a rescue path. Replaced with
> "sensitivities never decide", matching frozen spec §0.5.5.*

8\. Promotion from research to PAPER

  ---------------------------------------------------------------------------------
  **Gate**         **Question**                          **Evidence required**
  ---------------- ------------------------------------- --------------------------
  Economic         Did the candidate satisfy its frozen  Recorded verdict with CI;
  validation       primary acceptance criteria?          frozen-spec / dataset /
                                                         code identities.

  Robustness       Are costs, walk-forward / regime      Named sensitivities as
                   behaviour, and falsifiers acceptable? reported; falsifier
                                                         outcomes (e.g. redundancy
                                                         classification) stated,
                                                         not argued around.

  Multiplicity     How many shots were taken in this     Trial-ledger citation;
                   family, and does the result survive   family disclosure (§5.2).
                   that context?                         

  Portfolio role   Does it add return, reduce drawdown / Portfolio incremental test
                   tail risk, improve diversification,   under the frozen
                   or replace a weaker same-factor       combination scheme; no
                   strategy --- in the role              promotion on standalone
                   pre-specified before the run?         Sharpe alone.

  Implementation   Can the mechanism be implemented      Conformance identity
  conformance      without changing the validated        (§8.2): implemented
                   economics, and can that be proven?    parameters hash-matched to
                                                         the promoted spec;
                                                         conformance tests pass.

  Execution / data Are required market data, trusted     Readiness proof chain;
  readiness        prices, risk controls, scheduling,    platform interlocks
                   and evidence paths governed and       (e.g. factor readiness)
                   operational?                          GREEN where the strategy
                                                         depends on them.

  Observation      Is the PAPER observation protocol     Frozen protocol in custody
  protocol frozen  (§9.1) owner-frozen?                  before activation.

  PAPER authority  Has a separate owner decision         Owner ruling;
                   assigned account / capital and        account-binding record.
                   authorised PAPER operation?           
  ---------------------------------------------------------------------------------

8.1 Ranking and capacity

Each batch adjudication ranks survivors (**#1 PAPER PROMOTION CANDIDATE
/ #2 NEXT / #3 RESEARCH-ONLY, REVISE, OR REJECT**). Available PAPER
capacity must not determine which candidate passes research or which
ranks first; capacity affects sequencing only after evidence establishes
eligibility. An idle account is capacity, not a selection criterion.

8.2 Conformance identity

A promoted strategy's deployed configuration (signal parameters,
universe rules, rebalance cadence, sizing, cost assumptions) is hashed
against the promoted spec and recorded at activation and at every
subsequent deployment. **Drift between deployed configuration and
promoted spec is a PAUSE trigger and renders PAPER evidence gathered
under the drifted configuration inadmissible for the strategy's
thesis.** The live book must be measuring the strategy that was
validated.

> *R6 --- Added. The SEC-001 V2 retirement was caused by exactly this
> failure class: the deployed runtime drifted from the governed
> definition, so the paper book measured a different strategy and its
> P&L was inadmissible. A lifecycle model that does not carry a
> conformance mechanism will repeat it.*

9\. PAPER is a learning state, not a finish line

PAPER tests whether validated research survives operational reality:
live data timing, order construction, costs, slippage, risk controls,
scheduling, portfolio interaction, and changing regimes.

9.1 Frozen observation protocol

Before activation, the owner freezes the observation protocol for the
strategy. Minimum contents (LD-4 proposes the mandatory set):

-   observation window (e.g. ≥13 weekly rebalances / \~one quarter for a
    weekly strategy; scaled to the strategy's horizon);

-   the frozen reference the strategy is measured against (e.g. the
    PIT-static book from the validated construction);

-   the **thesis-health envelope**: expected ranges for net return vs
    reference, maximum drawdown, turnover, implementation shortfall vs
    decision price, conformance-check pass rate, and the factor / regime
    exposures implied by the pre-specified role;

-   the review dispositions available at the end of the window and at
    each trigger (§10) --- pre-declared, so the review cannot invent an
    outcome;

-   EVIDENCE_NOT_FEEDBACK inside the window: PAPER observations are
    recorded, never used to change the strategy while it is being
    observed.

9.2 Standing rules

-   **Contamination rule.** Any change to a strategy's economic
    definition made in response to its own PAPER results terminates that
    version's observation window and evidence; the change is a MODIFY
    (§9.3) and starts a new candidate.

-   PAPER results may support KEEP, PAUSE, or RETIRE; they may **not**
    upgrade the frozen economic verdict, and they do not silently alter
    any allocation program's standing.

-   An allocation / ranking program (e.g. RANK-001) allocates only among
    independently validated strategies; PAPER observation does not
    create a validated strategy.

9.3 Strategy thesis record

Every PAPER strategy carries a thesis record --- the object the MONITOR
state reads --- containing: original investment thesis and expected
economic role; frozen / accepted research evidence supporting promotion
(identities, verdict, CI); the frozen observation protocol and
thesis-health envelope; current performance and risk metrics versus the
envelope; execution quality, turnover, capacity and realised
transaction-cost behaviour; regime and factor exposures relevant to the
thesis; known limitations and falsifiers; conformance identity and last
verification; last thesis review date and next review trigger.

> *R7 --- v0.1 §8 listed these fields as bare bullets with no lead-in,
> so it was not clear what object they described or who maintained it.
> Restored as the thesis record, with the envelope and conformance
> identity added.*

10\. Evidence-driven strategy adaptation

  ---------------------------------------------------------------------------------------
  **Disposition**   **Meaning**         **Required behaviour**        **Identity effect**
  ----------------- ------------------- ----------------------------- -------------------
  KEEP              Thesis and          Continue under current        None.
                    operating evidence  authority; keep monitoring;   
                    remain inside the   record the review.            
                    envelope.                                         

  MODIFY            Evidence suggests a Write a prospective successor New candidate
                    plausible           hypothesis; census; freeze;   identity and
                    improvement that    validate before replacing     pre-registration
                    changes the         current behaviour. The        (economic change).
                    governed mechanism. incumbent continues unchanged Operational patch
                                        meanwhile.                    versions are not
                                                                      MODIFY (§6.3).

  PAUSE             A temporary         Stop new governed action as   None; PAUSE is not
                    operational / data  required; preserve positions  terminal. IDLE must
                    / readiness         under independent risk rules; converge (§17
                    condition --- or a  define the recovery gate      principle 4).
                    platform interlock  before pausing. Evidence      
                    --- prevents        gathered while paused is      
                    trustworthy         inadmissible.                 
                    operation.                                        

  RETIRE            Original thesis no  Execute under the governed    Terminal. The
                    longer supported,   retirement control (§10.1);   identity never
                    or no longer        preserve evidence; reclaim    re-activates; any
                    justifies capital / account / capital.            revival is a new
                    complexity.                                       prospective
                                                                      program.

  REPLACE           A validated         Promote the successor through Successor gets a
                    successor dominates its own gates; retire the     new identity;
                    the incumbent for   incumbent with an explicit    incumbent retires.
                    the same            transition plan (position     
                    pre-specified role. handover or flatten).         
  ---------------------------------------------------------------------------------------

Observed deterioration is not authority to tune the live strategy.
Modification is a new prospective hypothesis or an explicitly governed
successor version. ATP §5.3's **DEMOTE** maps to PAUSE (recoverable) or
RETIRE (terminal); the review must say which.

10.1 Governed retirement control --- minimum contract

RETIRE and REPLACE must reclaim PAPER accounts deterministically (LD-7).
The minimum control, proposed for owner acceptance:

1.  A first-class RETIRED state in the strategy registry, set only by
    the retirement control, never by ad-hoc database mutation.

2.  Pre-state evidence: registry state, open positions, account binding,
    conformance identity --- recorded before any action.

3.  Position disposition through the authenticated order path (flatten
    or governed handover to a successor), with the fill record attached
    to the retirement record.

4.  Post-state evidence: zero governed positions, scheduler unbound,
    account released to the free pool, evidence archive pointer
    recorded.

5.  The account-release record is the **only** thing that makes an
    account available to PROMOTE; an account whose strategy has no
    retirement record is not free, however idle it looks.

6.  A single owner ruling authorises the retirement execution; the
    control is idempotent and fails closed.

11\. Thesis revalidation and change detection

Every PAPER / ACTIVE strategy has scheduled and event-driven thesis
review. **Triggers open a review; they do not predetermine the
outcome.** Every trigger references a value frozen in the observation
protocol, so that "beyond the expected range" is a comparison, not a
judgment made after the fact.

-   Risk-adjusted return or drawdown outside the frozen envelope.

-   Loss of the factor / anomaly relationship that motivated the
    strategy (pre-specified diagnostic).

-   Regime behaviour inconsistent with the pre-specified role.

-   Transaction costs, liquidity, capacity, or slippage making the edge
    uneconomic against the frozen cost assumptions.

-   Redundancy with another strategy above the frozen overlap /
    correlation threshold, removing the intended portfolio benefit.

-   Data-source, execution-venue, or platform-interlock changes that
    alter mechanism assumptions.

-   A newly validated strategy materially dominating the incumbent for
    the same role.

**Scheduled cadence (LD-5 proposal):** review at a fixed multiple of the
strategy's rebalance cadence (e.g. every 13 rebalances for weekly
strategies; every 4 for monthly), plus event triggers. The review's
admissible dispositions are those pre-declared in the protocol (§9.1).

12\. Learning loop --- failures generate research

A strategy failure should produce structured information, not merely a
closed record. When evidence identifies a specific failure mode, the
platform asks whether that failure supports a distinct, economically
motivated successor hypothesis.

Example: if momentum deterioration is concentrated in a pre-identifiable
high-volatility sideways regime, discovery may propose a regime-gated
momentum successor. The observed failure motivates the question; the
successor's mechanism, thresholds, window, and acceptance rules are
frozen prospectively.

**In-sample rule.** The data that revealed the failure is in-sample for
the successor. It may be cited as motivation and used for census; it may
not serve as the successor's decisive validation evidence. The
successor's frozen spec names a validation window or holdout that the
motivating analysis did not read, or --- where none exists --- a
prospective accrual window, and the trial ledger records the motivating
exposure.

> *R8 --- Added. v0.1 §11 required the successor to be frozen
> prospectively but was silent on the status of the motivating data,
> which is the most common route by which a "prospective" successor
> quietly becomes a post-hoc fit.*

13\. Portfolio-level strategy management

  -----------------------------------------------------------------------
  **Role**       **Illustrative families (not an inventory)**
  -------------- --------------------------------------------------------
  Core return    Momentum, quality / value, trend

  Defensive /    Low-volatility family
  low volatility 

  Diversifier /  Range / mean-reversion candidates
  mean reversion 

  Tail / crash   Trend de-risk or convex overlay candidates (insurance
  protection     roles are judged on carry vs protection, not on Sharpe)

  Event /        Insider, gap, corporate-event candidates (subject to the
  catalyst       same census and ledger rules; prior rejections count as
                 shots)
  -----------------------------------------------------------------------

Redundant strategies compete for capital rather than accumulate. A
stronger same-factor successor is a REPLACE candidate, not an additional
sleeve; whether it replaces or joins is a PROMOTE-stage owner question,
never something the research argues for (the frozen spec's C3 redundancy
falsifier is the precedent). Portfolio roles are declared **before**
validation so that a candidate cannot be re-described into a role that
its result happens to fit.

14\. Platform architecture implications

ADR-0051 already defines the platform's planes (Presentation →
Research/Analytics → Execution/Core) and the rule **Evidence ≠
Allocation Authority** (research recommends · governance authorises ·
core activates). This model does not introduce a competing plane
taxonomy. The capabilities below are placed inside ADR-0051's planes;
where a capability needs a structural home the ADR does not provide,
that is an ADR amendment, not a lifecycle-document decision.

  --------------------------------------------------------------------------------------
  **Capability**   **Plane          **Provides**
                   (ADR-0051)**     
  ---------------- ---------------- ----------------------------------------------------
  Research plane   Research /       Reproducible PIT datasets; census tooling; frozen
  capabilities     Analytics        specs; decisive execution; evidence artifacts; trial
                                    ledger. Read-only; no broker credentials, SDK, or
                                    router token.

  Execution /      Execution / Core Governed strategy implementations; conformance
  PAPER                             identity; account bindings; scheduling; market data;
  capabilities                      risk controls; orders; audit.

  Observation      Research /       PAPER performance; thesis-health metrics vs
  capabilities     Analytics (reads envelope; execution quality; regime / factor
                   Core evidence)   diagnostics; trigger evaluation. Observation reads
                                    Core; it never writes to it (decision-plane /
                                    observation-plane firewall).

  Lifecycle        Governance       Candidate registry; strategy state and disposition;
  registry         (cross-plane     successor relationships; promotion, pause and
                   record;          retirement records; account / capital reclamation;
                   owner-written)   authority references (artifact + SHA-256) for every
                                    state transition.
  --------------------------------------------------------------------------------------

Shared infrastructure supplies capabilities but must not invent
strategy-specific thresholds, freshness policies, economic acceptance
rules, or activation authority. **Every lifecycle state transition in
the registry carries the reference of the artifact that authorised it**;
a transition without one is refused.

> *R9 --- v0.1 §13 proposed four planes (research, execution/PAPER,
> observation, lifecycle). ADR-0051 is an accepted higher-authority
> artifact with three; a lifecycle document may not redefine it by
> implication. Rewritten to place the same capabilities inside the ADR's
> planes.*

15\. Stakeholder capability model

  -------------------------------------------------------------------------------
  **Capability**   **Stakeholder demonstration**
  ---------------- --------------------------------------------------------------
  Discover         Show an opportunity surfaced from data or a portfolio gap,
                   with its ledger entry.

  Hypothesise      Show the economic rationale and falsifier written before
                   testing.

  Census           Show a candidate stopped or deferred for data reasons before
                   any strategy code existed.

  Validate         Show frozen inputs, decisive result, CI / robustness, and an
                   honest PASS / REVISE / REJECT / NOT EVALUABLE.

  Promote          Show how a survivor became a governed PAPER candidate through
                   separate gates, and what it was ranked against.

  Operate          Show scheduling, risk controls, market-data path, positions,
                   conformance identity, and audit.

  Monitor          Show thesis health against the frozen envelope: performance,
                   drawdown, costs, exposure, regime behaviour.

  Adapt            Show evidence opening a successor / modification study without
                   tuning the incumbent.

  Retire / Replace Show a weak thesis terminated under the retirement control and
                   capital / account reclaimed or moved to a validated successor.
  -------------------------------------------------------------------------------

Demonstrations use sealed, custodied artifacts; nothing is re-run for a
demonstration. Rejected and NOT EVALUABLE candidates strengthen the
demonstration. The capability claim is trustworthy decision-making, not
that every hypothesis wins.

16\. Operating metrics and scorecard

  -----------------------------------------------------------------------------
  **Dimension**   **Metrics (all PASS-neutral)**
  --------------- -------------------------------------------------------------
  Discovery       New observations; hypotheses created; source diversity;
                  ledger entries opened

  Census          Censuses run; CENSUS_PASS / CENSUS_WAIT / CENSUS_STOP mix;
                  median time hypothesis → census outcome

  Research        Candidates frozen; decisive runs completed; decisions
  throughput      delivered (any verdict); median time freeze → verdict; shots
                  taken per program family

  Research        Verdict mix; defect-record reruns; evidence-contract defects
  quality         found before vs after freeze; NOT EVALUABLE causes

  Conversion      Validated candidates reaching PROMOTE; time verdict →
                  activation; gates failed and why

  PAPER quality   Conformance pass rate; execution quality; risk incidents;
                  strategies inside vs outside envelope

  Adaptation      Reviews opened (scheduled vs triggered); KEEP / MODIFY /
                  PAUSE / RETIRE / REPLACE; time trigger → disposition

  Capital         Active vs idle PAPER accounts; days-in-IDLE; accounts
  efficiency      reclaimed via retirement control; redundant sleeves removed
  -----------------------------------------------------------------------------

These are management metrics, not research thresholds, and by
construction none of them improves when a REJECT becomes a PASS. They
are computed from the registry and ledger **after** verdicts are
recorded and are never inputs to a verdict, a review, or a gate.

17\. Parallelism and sequencing

Parallel by default where independent: opportunity discovery and
candidate economic review; censuses; independent frozen candidates using
isolated outputs and no shared mutation; read-only data-quality
analysis; design / custody work; PAPER observation and thesis
monitoring.

Serialise or separately authorise: any evidence-affecting change after a
result exists; schema / data migrations on shared stores; account
binding or capital changes; broker credential changes; same-runtime
deployments; canary orders, activation, liquidation, rebalance,
retirement, or replacement execution. Programs may run in parallel; they
may not share evidence.

18\. Standing principles

1.  Evidence decides strategy disposition; desired strategy count does
    not.

2.  New data can create a strategy, modify the research agenda, or
    invalidate an existing thesis.

3.  Modification is prospective: never tune a governed strategy in place
    because recent results disappoint.

4.  IDLE is temporary. A PAPER strategy / account converges to ACTIVE
    with current authority or to RETIRED / REPLACED with capacity
    reclaimed through the retirement control.

5.  A research failure is useful when it eliminates a weak hypothesis
    quickly and honestly; a census STOP is cheaper still.

6.  NOT EVALUABLE preserves uncertainty; it is never silently converted
    to REJECT or PASS.

7.  Platform work is strategy-direct or a required enabler with a named
    conversion target.

8.  Throughput is an explicit objective and is measured PASS-neutrally;
    every shot is ledgered.

9.  Shared infrastructure supplies capabilities; strategy policy owns
    economic thresholds and decisions.

10. The live book must be the validated strategy: conformance identity
    is verified at activation and every deployment.

11. Data that motivated a hypothesis is in-sample for it.

12. Stakeholder value is demonstrated by the complete adaptive
    lifecycle, not by backtest performance alone.

19\. Accepted lifecycle design decisions (LD-1 ... LD-8)

The owner accepts LD-1 ... LD-8 below as the v1.0 lifecycle defaults.
They govern this operating model after repository custody, subject to
the authority hierarchy in §0.1 and to any more-specific frozen
artifact, accepted ADR, ATP rule, or explicit owner ruling.

  ----------------------------------------------------------------------------------------
  **\#**   **Decision**    **Accepted v1.0 value**               **Rationale**
  -------- --------------- ------------------------------------- -------------------------
  LD-1     Canonical       Adopt §6 as platform vocabulary.      Changes labels, not
           lifecycle       Existing documents are not rewritten; meanings; avoids
           vocabulary      the §6 mapping tables translate.      reopening ATP or the
                                                                 frozen specs.

  LD-2     Discovery batch Evidence-triggered, with a monthly    A fixed cadence is
           cadence         review floor. A batch freezes when ≥2 schedule pressure by
                           candidates have CENSUS_PASS, or at    another name; a floor
                           the monthly review if any has. No     prevents starvation
                           calendar-driven freezing.             without forcing weak
                                                                 candidates into a batch.

  LD-3     Minimum funnel  No enforced minimum. Funnel depth is  Any enforced minimum
           size            a §16 metric. Two consecutive monthly becomes a target; a
                           reviews with zero new hypotheses open starvation alarm gives
                           a \*discovery\* review, which may not the same signal without
                           touch any candidate's research.       pressure.

  LD-4     Mandatory       Mandatory for every PAPER strategy:   Mirrors the ATP §5.3
           thesis-health   net return vs frozen reference; MaxDD default already proposed
           metrics         vs envelope; turnover; implementation for LOW-001; makes
                           shortfall vs decision price;          envelopes comparable
                           conformance pass rate; exposure vs    across strategies.
                           pre-specified role. Strategy-specific 
                           metrics frozen in each protocol.      

  LD-5     Review cadence  Every 13 rebalances for weekly        Scales with the horizon
           by horizon      strategies, every 4 for monthly,      the thesis operates on;
                           every 2 for quarterly, plus event     avoids reviewing a
                           triggers --- i.e. a fixed multiple of monthly strategy on
                           rebalance cadence, \~one quarter.     weekly noise.

  LD-6     MODIFY and      Economic change → new candidate       Existing precedent:
           identity        identity + pre-registration.          LOW-001 v1.0.1
                           Non-economic operational change →     (conformance repair, same
                           same identity, patch version,         identity) vs LOW-002 /
                           conformance test, ledger note.        MF-001 V2 (economic
                                                                 change, new candidate).

  LD-7     Deterministic   Adopt §10.1 as the minimum control    Without a first-class
           RETIRE /        contract; implement as a REQUIRED     RETIRED state and an
           REPLACE control ENABLER via ATP.                      account-release record,
                                                                 capacity cannot be
                                                                 reclaimed
                                                                 deterministically --- the
                                                                 current
                                                                 unreclaimed-account case
                                                                 shows the gap.

  LD-8     First           Lifecycle board (every candidate /    The board \*is\* the
           stakeholder     strategy, its state, its authority    registry; the other views
           dashboard       reference) first; funnel view second; derive from it. Building
                           thesis-health scorecard third.        a scorecard before the
                                                                 registry exists invites
                                                                 hand-maintained state.
  ----------------------------------------------------------------------------------------

20\. What this document does NOT authorise

-   Any change to a frozen research specification, an owner-accepted
    parameter, a sealed evidence record, or an accepted ADR.

-   Any reinterpretation of an observed verdict, including converting
    NOT EVALUABLE to REJECT or PASS.

-   A new discovery batch, census, or freeze --- each is admitted
    through ATP §1 and scheduled by an ATP successor.

-   Exploratory access to any sealed or designated validation partition.

-   Discovery, screener, watchlist, or census output entering any order,
    risk, sizing, or governed-strategy input.

-   Implementation, account binding, scheduler change, deployment, PAPER
    activation, or orders for any candidate.

-   Tuning, rescue, or rerun of any strategy or candidate in response to
    observed results.

-   Retirement execution, position flattening, or account reclamation by
    any path other than the governed retirement control once accepted;
    ad-hoc database mutation to manufacture a RETIRED label.

-   Redefinition of ADR-0051 planes or the research-plane isolation
    rule.

-   Treating a throughput target, funnel count, or scorecard value as an
    input to any verdict, review, or gate.

-   Reviving a RETIRED identity; any revival is a new prospective
    program.

21\. Review provenance retained from v0.1 → v0.2

The following review findings explain how the non-governing v0.1 draft
was hardened before v1.0. They are provenance, not separate operational
authority.

  ------------------------------------------------------------------------------
  **\#**   **Finding**                      **Change**
  -------- -------------------------------- ------------------------------------
  R1       Lifecycle omitted the            CENSUS and PROMOTE added as states
           data-feasibility gate (ATP §7.1  (§1, §5.1, §6.1).
           NO-START pattern) and folded the 
           separate promotion decision into 
           VALIDATE → PAPER.                

  R2       "Should normally be deferred"    ATP §1 wording adopted verbatim
           weakened ATP §1's DEFER / MOVE   (§3).
           TO OPS / STOP.                   

  R3       Throughput objective stated with Census gate, mandatory ledger
           no mechanism preventing count    citation, multiplicity promotion
           pressure; no trial ledger or     gate, PASS-neutral scorecard (§5.2,
           multiplicity handling despite    §8, §16).
           frozen spec §0.5.4 and ATP §7.4. 

  R4       Identifiers mixed without a      Identity register (§6.3); any future
           register; "Strategy 9" and       use of Strategy 9, Mechanism-C, or
           "Mechanism-C" undefined in       similar deployed / program
           either governing document.       identifiers must cite the governing
                                            artifact that defines them.

  R5       "Sensitivities cannot rescue ... "Sensitivities never decide" (§7).
           unless prospectively decisive"   
           was self-contradictory and       
           opened a rescue path.            

  R6       No conformance mechanism between Conformance identity gate and PAUSE
           promoted spec and deployed       trigger (§8.2).
           runtime --- the SEC-001 V2       
           failure class.                   

  R7       §8 thesis-record fields appeared Frozen observation protocol with
           as headless bullets; no frozen   thesis-health envelope; thesis
           envelope, so review triggers     record defined (§9.1, §9.3, §11).
           were post-hoc judgments.         

  R8       Learning loop silent on the      In-sample rule (§12).
           in-sample status of motivating   
           data.                            

  R9       Four-plane architecture          Capabilities placed inside ADR-0051
           conflicted with accepted         planes; registry defined as
           ADR-0051 (three planes).         governance record (§14).

  R10      Authority position ambiguous     Authority order fixed below ATP
           ("durable layer above ATP"); §17 (§0.1); state excluded from body
           carried observation-dated state  (§0.2); the observation-dated §17
           and de-facto priority rulings    content was removed from the durable
           inside a durable document.       v1.0, with current-state facts
                                            remaining in ATP / custody.

  R11      Eight open questions left for    Converted to LD-1 ... LD-8 with
           the final pass.                  proposed defaults (§19).

  R12      No "does not authorise"          §20 added.
           boundary, unlike ATP §12 and the 
           frozen spec's execution          
           boundary.                        

  R13      PAPER rules did not name         §9.2, §10, §10.1.
           EVIDENCE_NOT_FEEDBACK, the       
           contamination rule, KEEP/DEMOTE  
           mapping, or the retirement       
           control gap already recorded in  
           the frozen spec.                 
  ------------------------------------------------------------------------------

22\. Acceptance and implementation directive

This v1.0 is owner-accepted as the durable strategy-lifecycle operating
model. In authority it remains subordinate to frozen
registrations/sealed evidence/accepted ADRs/explicit owner rulings and
to ATP for current execution; in purpose it is the long-lived default
procedure that ATP and future frozen research specifications implement.
The three document classes work together: this model defines the
recurring lifecycle, vocabulary, and gate shapes; ATP defines current
execution priorities, enablers, and state; frozen research
specifications define the prospective evidence contract for each
candidate batch. LD-1 ... LD-8 are accepted at the values in §19.
Repository implementation is: place this exact document at the canonical
path, record its SHA-256 in custody, and update the next ATP successor
only as needed to reference/adopt this model. Documentation custody
grants no operational authority.

23\. Repository implementation checklist

1.  Place this exact v1.0 at
    `docs/design/Lifecycle/Strategy_Lifecycle_and_Research_Operating_Model_v1_0.md`.
2.  Record file bytes and SHA-256 in the custody/acceptance record; do
    not place the approval record inside this governed source file.
3.  Update the next ATP successor to reference this model as the default
    lifecycle procedure and to carry any current priorities needed to
    implement LD-7 (retirement control), LD-8 (lifecycle
    registry/board), census/trial-ledger work, and thesis-health
    protocols.
4.  Do **not** modify existing frozen research specifications to conform
    retroactively. Future frozen specs adopt the v1.0 vocabulary and
    invariants prospectively.
5.  Implement the lifecycle registry before derived stakeholder
    dashboards. Every state transition must carry its authorising
    artifact reference and identity.
6.  Implement the governed retirement control as a REQUIRED ENABLER
    before treating any idle account as reclaimed capacity.
7.  Add census and trial-ledger support without allowing
    discovery/census output to enter execution, risk, sizing, or
    governed-strategy inputs.
8.  For each future PAPER promotion, freeze the observation protocol and
    thesis-health envelope before activation and record conformance
    identity at activation and each deployment.
9.  Treat any economic MODIFY as a new candidate/pre-registration.
    Preserve same identity only for proven non-economic operational
    patches.
10. Keep stakeholder reporting derived from sealed/custodied evidence;
    demonstrations do not trigger reruns.
