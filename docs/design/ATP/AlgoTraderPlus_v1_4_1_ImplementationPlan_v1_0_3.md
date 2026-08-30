# Algo Trader Plus / Strategy Proposals v1.4.1 --- Final Design & Implementation Plan

  ----------------------------------------------------------------------------------------------------------
  Field                               Value
  ----------------------------------- ----------------------------------------------------------------------
  **Document version**                **v1.0.3 --- post-#707 state sync (derived from v1.0.2; adds §2.7 only)**

  **Sync date**                       **2026-08-30** (the v1.0.2 sync date was **2026-08-28**)

  **What v1.0.3 changes**             **(a)** adds one new **§2.7** state-observation subsection; **(b)**
                                      synchronizes the affected **§11** owner-gate rows --- the G3
                                      expected-disposition row moves OPEN -> DISCHARGED by #703; a
                                      *K computation authority custody / execution* row is added and
                                      recorded **DISCHARGED / CLOSED**; and *G3 disposition* and
                                      *Future-designation defects* rows are added, carrying the current
                                      HOLD-with-one-stated-extension state and the two deferred defects;
                                      **(c)**
                                      updates four fields in this header block (document version, sync
                                      date, canonical path, supersedes). **Measured against v1.0.2,
                                      exactly 16 lines are removed** --- those four header fields (6 lines)
                                      and the superseded G3 row (10 lines) --- **and nothing else.** (The
                                      insertion count is deliberately not stated here: writing it into this
                                      row would change it. The exact +/- and the file SHA-256 are recorded
                                      in the custody PR, outside the hashed artifact.)
                                      **Nothing else is edited**: §1--§10, §12 and §13 are inherited
                                      verbatim, the §11 **K1 authority designation** row is preserved
                                      **OPEN** (it governs different unbound authorities), no dated
                                      assertion is rewritten, and no economics, frozen MDQ definition,
                                      authority hierarchy, profitability admission test, threshold or gate
                                      is reopened. v1.0.3 is a **state/procedure sync**, not a review pass.

  **Status**                          **FINAL DESIGN / IMPLEMENTATION PLAN** --- Review 2 complete; this
                                      revision is READY FOR CUSTODY / OWNER ACCEPTANCE, not a new review
                                      pass. Operational owner gates remain explicit; this document does not
                                      grant them.

  **Canonical repository path**       `docs/design/ATP/AlgoTraderPlus_v1_4_1_ImplementationPlan_v1_0_3.md`

  **Repository**                      `github.com/jayw04/AI-TRADING-APP`

  **Source-control baseline observed  `ce6dbaa61a515856f79973592037d8cc766eeb6a` --- merged factor-repair
  at state sync**                     head (#698), observed 2026-08-28. **Point-in-time repository evidence
                                      only; not a continuously maintained assertion of current `main`.
                                      Consult the repository for the current branch head.**

  **Supersedes**                      v1.0.2 for current-state execution guidance, and through it v1.0.
                                      **v1.0.2 is NOT mutated: it remains in custody unchanged at SHA-256
                                      `abb5d1d73b65f3fca96ad7ab4c3a646f9b78f98940937f8c0dda6879fac06d07`**
                                      --- its historical identity is preserved rather than overwritten.
                                      v1.0.1 was never placed in repository custody and is not a governing
                                      predecessor; do not manufacture an intermediate v1.0.1 custody
                                      record. Under the ONE CURRENT PLAN rule, **v1.0.2 remains CURRENT
                                      until v1.0.3 is actually merged**; CURRENT moves only on merge. v1.0
                                      and earlier repository versions remain historical evidence; do not
                                      rewrite their dated assertions as though later facts were known then.
                                      **Nothing in v1.0.2 reopens strategy economics, frozen MDQ
                                      definitions, the authority hierarchy, or the profitability admission
                                      test** --- it corrects the state/procedure surface only (findings
                                      F1--F6, §13).

  **Historical companion**            `AlgoTraderPlus_v1_4_1_History_v0_3_to_v0_16.md` --- exact byte copy
                                      of the supplied v0.16 final-review draft; SHA-256
                                      `51ae39e670b451d70764fb0372f4b1b6c13381df093fae47acb19aa623923dd8`.

  **Sole program objective**          **Generate robust, deployable, net-profitable strategies at acceptable
                                      risk.** Research, data, infrastructure and governance are means, not
                                      products.

  **Authority hierarchy**             Frozen registrations / sealed evidence / accepted ADRs / explicit
                                      owner rulings \> this plan \> subordinate task lists. A merge, test
                                      pass, document statement or planning priority never grants live
                                      mutation or strategy activation by implication.
  ----------------------------------------------------------------------------------------------------------

------------------------------------------------------------------------

## 1. Executive directive --- profit is the product

Every active task must pass this admission test **before** engineering
time is allocated:

1.  Name the strategy or economic decision it serves.

2.  State how it can improve net P&L, risk-adjusted return, capacity,
    execution cost, drawdown, or time-to-paper validation.

3.  State a measurable stop condition or time-box before work starts.

4.  State the next conversion gate:

    `observation → frozen mechanism → governed validation → paper candidate → promotion decision`

5.  If no named conversion target exists, **DEFER / MOVE TO OPS /
    STOP**.

Only two classes belong in the strategy program:

-   **STRATEGY-DIRECT** --- generates, validates, improves, or promotes
    a named economic mechanism.
-   **REQUIRED ENABLER** --- the minimum engineering/data/governance
    work without which a strategy-direct step cannot run safely or
    produce admissible evidence.

"Useful platform work," "more complete research," "better custody,"
"more features," and "we already have the data" are **not sufficient
reasons** to consume strategy-program time.

------------------------------------------------------------------------

## 2. Current governed state --- latest verified/reported snapshot

### 2.1 Repository / deployment

-   **Source-control baseline observed at state sync (2026-08-28):**
    **`ce6dbaa61a515856f79973592037d8cc766eeb6a`** --- the merged
    factor-repair head (#698). **Point-in-time repository evidence only;
    not a continuously maintained assertion of current `main`. Consult
    the repository for the current branch head.** Ordinary merges after
    the observation date do **not** make this document defective; this
    baseline is re-observed only when a substantive state sync has its
    own reason to establish a new one.
-   **Deployed backend:** **`3f32c75b1053f8181f98ddf51bbc473364ffd34c`**
    --- the Amendment 8 runtime pin. This is a **deployment identity,
    not a branch head**, and it **remains authoritative until a
    separately authorized deployment changes it.**
-   At the 2026-08-28 observation boundary, source control was ahead of
    the deployed backend by **at least #696 and #698**. This is
    intentionally non-exhaustive. The load-bearing statement is that
    **#696 K-calculator behavior and #698 factor-repair behavior are not
    present in the running backend merely because those changes are
    merged.** Each requires separately authorized deployment before live
    behavior may be inferred.
-   Amendment 8 is **DEPLOYED / ACCEPTED / CLOSED** at the exact pin
    above, with code digest
    `sha256:813be1b9775fb98e4276a499e8c715b745c7a518decf04072ef5a75999b72610`
    and immutable archive SHA-256
    `de2b8fc8e9addc004b6028c37094d5d0d615753ee676523591ec7da9626eba50`.
-   The mutable shared `bootstrap/code.tgz` is **LEGACY / NOT AUTHORIZED
    FOR GOVERNED DEPLOYMENT**. A fail-closed digest gate is a backstop,
    not artifact-selection authority.

### 2.2 MDQ acquisition / governed corpus

The governed Phase-A corpus now contains **seven sealed/admitted
partitions**:

`2026-08-19, 08-20, 08-21, 08-25, 08-26, 08-27, 08-28`

`2026-08-24` remains the sole lost trading day in this interval.

**2026-08-27:** SEALED / ADMITTED. Terminal evidence established 395/395
scheduled slots per feed, 19,750 quote rows per feed, successful
EOD/freeze/verify/mirror, zero alerts, unchanged universe identity, and
independent S3 custody.

**2026-08-28:** SEALED / ADMITTED after the full terminal chain. The
earlier v1.0 statement that 08-28 was not yet partition 7 was correct at
its observation time and is preserved as historical state; the later
terminal evidence discharged that condition. Admission included 395/395
scheduled slots, 19,750 quote rows per feed, successful EOD,
freeze→verify→mirror, 3 files per feed, zero alerts, unchanged universe
identity, manifest/host SHA-256 agreement, and independent S3 custody.

No day earns governed status from timer start, liveness, freeze exit
alone, or calendar passage. The complete registered admissibility chain
remains controlling. **No salvage, backfill, reconstruction, hand-start
or manufactured partition is permitted.**

### 2.3 B-1 / PR #696 / K1-K3

-   PR **#696 / B-1 = MERGED / ENGINEERING CLOSED**, squash
    `15456560a99ecd857306771831a61e81d846a629`.
-   Exact approved PR head at merge:
    `77461c747a66f2b3e5f653fafc3e89a33c0c9cb7`; exact-head CI passed.
-   **MERGED ≠ DEPLOYED** --- for live behavior. The running Amendment-8
    backend predates #696 and carries no K calculators; no live-backend
    behavior may be inferred from the merge.
-   **Governed K computation is OFFLINE and does not require backend
    deployment** *(corrected at v1.0.2)*. Under the subscription ruling
    and §9.3, MDQ calculators are read-only research consumers of frozen
    partitions and hold no credential. The evidentiary requirement for a
    governed K value is: an exact checkout of the **approved code
    identity** (merge `15456560a99ecd857306771831a61e81d846a629` /
    approved head `77461c747a66f2b3e5f653fafc3e89a33c0c9cb7`), admissible
    partitions, and the §4.1 gate path --- with that source identity
    recorded in the verdict artifact. **Do not deploy #696 to the live
    backend merely to compute K values**; that is a Tier-3 live-stack
    touch with no strategy need and fails the §1 admission test. (#698 is
    different: its behavior is live and genuinely requires authorized
    deployment.)
-   **K1 = NOT EVALUABLE / AUTHORITIES UNBOUND.**
    `DECISION_PROVIDER_AUTHORITY` and `DEFECT_REGISTRY_AUTHORITY` remain
    unbound after the bounded provenance discovery. Do not create a
    provider or "predeclared" defect list after the corpus exists.
-   Whether a newly authored governing record may designate an
    already-existing pre-corpus artifact is an **OPEN owner/governance
    decision**. Documentation must not decide it by implication.
-   **K2 remains NOT EVALUABLE unless G10 opens.** Phase-A sealed days
    do not count automatically toward the separate Phase-B streaming
    requirement.

### 2.4 LOW-001 / B3a / Strategy 8

-   Strategy 8 remains **IDLE / zero orders**. No reactivation authority
    exists.
-   Historical B3a proof is **UNPROVEN / NOT REPRODUCIBLE** because the
    expected historical proof harness is unavailable. **Do not
    reconstruct or manufacture a replacement.**
-   A future prospective B3a proof may be separately authorized, clearly
    versioned and timestamped, but it cannot repair the historical proof
    gap.
-   Amendment 8 recreated/changed the backend runtime on 2026-08-27. The
    old S8.6 12/12 result is historical evidence only.
-   **S8.6 remains HOLD / untouched.** Checks **3, 4 and 8** consume the
    factor store and receive **no governance PASS credit while factor
    readiness is RED**, even if the current implementation mechanically
    reports PASS.
-   S8.6 check 2 separately pins a running SHA incompatible with the
    Amendment-8 runtime. That conflict requires an owner ruling before
    rerun; rollback solely to satisfy the old check is not authorized.
-   No aggregate 12/12 can exist until every check is governance-valid.
    Rollback-baseline restore remains HOLD until a genuine 12/12.
-   Reactivation remains a separate final owner ruling after the
    complete proof/custody chain.

### 2.5 Factor readiness --- global operational interlock

Current factor state is **RED** *(observed 2026-08-28; re-measure, do
not carry forward)*. Live factor publication is stale relative to
staging as of that observation. The factor repair is **MERGED (#698) / UNDEPLOYED /
DEPLOYMENT NOT AUTHORIZED**.

`factor_adjudication.py` is already the single adjudication authority
under ADR-0051. Producer and readiness consumers correctly adjudicate
different stores. **Do not open a PR to "re-unify" adjudication.**

While factor readiness is FAIL or publication is stale:

> **FACTOR-READINESS INTERLOCK:** no factor-dependent strategy may
> transition `IDLE → PAPER/LIVE`, generate a new factor-ranked book for
> activation, or execute a scheduled factor-driven rebalance. Existing
> positions remain untouched unless an independently governed
> strategy/risk rule requires action.

Factor-system GREEN requires separately authorized deployment of the
merged repair, successful producer verification, successful staging
promotion/live publication to the expected SEP date, coherent
producer/readiness outcomes for their respective stores,
`overall_readiness=PASS`, and one subsequent unattended scheduled
refresh PASS.

The next natural unattended refresh slot is Monday 2026-08-31 06:00 EDT.
**Schedule pressure is not deployment authority.** The expected
advance-expiry `PROBLEM` from still-undeployed old code is already
classified as an expected undeployed-fix artifact, not a new incident.

### 2.6 GAPPER / SEC-001 / documentation custody

-   **GAPPER current cycle = STOP-FOR-CYCLE.** No tuning, rescue, or
    rerun against the same evidence. A \$0 entitlement feasibility test
    using already-held access may occur only outside the stopped cycle,
    cannot alter its disposition, and **must not touch the governed
    Phase-A collector identity** (see §7.2, added at v1.0.2).
-   **SEC-001 successor cleanup = CLOSED.** Successor hosts/volumes were
    terminated/deleted and **380 GB released**; protected exclusions
    remained untouched.
-   ATP v1.0 governing-pair custody landed through PR #699.
    Documentation merges grant **no** deployment, factor activation,
    S8.6, K1 designation, or Strategy-8 reactivation authority.
-   The Amendment-8 custody PR remains a separate object and must retain
    exact two-artifact scope and exact-head/base-sync discipline.

### 2.7 State observation 2026-08-30 --- #707 merged, G3 discharged, Sharpe semantics frozen *(added at v1.0.3)*

**This subsection records facts observed after the 2026-08-28 v1.0.2 sync.
The dated assertions in §2.1--§2.6 are preserved exactly as written and are
not retro-fitted. Where a later fact discharges an earlier condition, that
discharge is stated here, not backdated there.**

-   **Source-control baseline re-observed (2026-08-30):**
    **`a12814c611e2f786694330a2f5a3bf1ce58b8b6a`** --- the #707 squash. This
    supersedes the §2.1 `ce6dbaa6...` reading *as an observation only*, under
    the same standing caveat: point-in-time repository evidence, **not** a
    continuously maintained assertion of current `main`.
-   **Deployed backend UNCHANGED at `3f32c75b...`** (the Amendment 8 runtime
    pin). Every merge recorded below is source-control only. **MERGED !=
    DEPLOYED** remains in force; no live behavior may be inferred from any of
    them.

**K evidentiary boundary --- #707 MERGED (B1a/B1b/B2/B3).** Engineering
review = **PASS / FINAL**. Approved exact head
**`175e734f2865cb3af4fa69523a5e89bcbb25568c`**, base
`39bbe0c0da6dba8bc283ceb9c895e09a83dae387` (parent **is** the base), 9 files
**+1698/-67**, exact-head CI **run 1709 = SUCCESS**, squash-merged
2026-08-30T12:58:45Z as **`a12814c6...`** with the merge pinned to the exact
head.

-   ⛔ **The merge itself designated nothing** --- designation is a separate
    owner act, and it followed.
-   **Successor governed K source identity was subsequently DESIGNATED by
    owner ruling** as merge commit
    `a12814c611e2f786694330a2f5a3bf1ce58b8b6a` plus the frozen ten-path
    raw-byte SHA-256 tuple. **Authority-record custody and K execution
    remain separate downstream gates** (§11). The designation is of *source
    identity only* and authorizes **no** computation.
-   ⛔ **Governed K computation remains HARD HOLD.** It requires, in order:
    authority-record custody in a descendant commit touching no governed
    path → post-custody runtime identity verification → a **separate**
    execution authorization.
-   **Superseded and never designated:** `c53f3bdb` (source-level
    circularity) - `a0adab9e` (commit-level circularity) - `17c006b7`
    (pre-ancestry) - `0954963c` (shallow-clone test defect; CI run 1708
    failed).
-   The authority record `config/mdq_k_computation_authority.json` is
    **deliberately outside** `GOVERNED_SOURCE_PATHS`, so writing an approval
    cannot change the surface being approved. **Absent => no designation =>
    refuse.** A missing record never reads as permission. It must be
    custodied in a **descendant commit touching no governed path**.
-   **B1b is `collector_implementation_invariance`, never
    `partition_collector_identity`.** The frozen manifests record no source
    commit and no collector blob hashes, so a per-partition source tuple
    **cannot** be reconstructed for the seven admitted days; the verdict
    states `per_partition_full_source_tuple_verified: false` /
    `HISTORICAL_BINDING_UNAVAILABLE` rather than converting measured
    invariance into fictitious provenance.
-   ⚠ **Hash definitions must never be mixed.** The per-file custody table
    uses **Git blob SHA-1**; `measure_source_identity` uses **SHA-256 of raw
    on-disk bytes** over the ten governed paths. Two different numbers for
    the same file are expected and are not a discrepancy --- but a table must
    state which definition it uses, and a digest whose definition is not
    recorded is not custody evidence.

**G3 prospective record --- #703 MERGED (discharges a §2.3 precondition).**
PR **#703** merged 2026-08-29T17:06Z, squash
`9ab6d94dc5c494995e845b1f7fbe6ed83ee698e1`, custodying the G3 expected
disposition **prospectively**. The gate that blocked *all* governed K
computation pending that record is therefore **DISCHARGED**. This discharges
one precondition and nothing else: it is **not** K authorization, and an
expected disposition is **not** a predetermined verdict --- non-influence and
the §9.4 no-post-hoc-criterion-repair rule continue to bind. Prospective
status is **not recoverable** and must never be backdated. The GO floor is
unchanged: **>=2 EVALUABLE-and-PASS**.

**Sharpe metric semantics --- FROZEN (#706 / #708 MERGED).**
`SHARPE-METRIC-SEMANTICS-001` is in custody: squashes `e56c5e3c` (#706 ---
frozen metric semantics and the CV resolvability floor) and `39bbe0c0` (#708
--- rolling coverage floor, semantics version, legacy boundary). Frozen
values: **CV floor `1e-6`**, **rolling coverage `0.75`**. The CV floor is a
**numerical-resolvability** control, **not** an economic-plausibility one.
Implementation remains **HOLD**; no backfill. **CE-001** (an `INSUFFICIENT`
severity of 0 erased by `max()`) is a separate and **UNADJUDICATED** item.

**Standing classifications at this observation:**

-   #707 engineering architecture --- **PASS / FINAL**
-   `175e734f...` --- **EXACT HEAD APPROVED**, merged as `a12814c6...`
-   `0954963c...` --- **SUPERSEDED / NOT DESIGNATED**
-   Successor K *source* identity --- **DESIGNATED** (owner ruling, 2026-08-30)
-   K authority-record custody --- **REQUIRED / NOT YET IN CUSTODY**
-   Governed K computation --- **HARD HOLD**

**ATP document custody.** ATP **v1.0.2** is in repository custody on `main`
via **#702** (squash `1df93ebd`), SHA-256
`abb5d1d73b65f3fca96ad7ab4c3a646f9b78f98940937f8c0dda6879fac06d07`, and is
**not mutated by this revision**. **#701 was CLOSED UNMERGED**; its
correction shipped inside v1.0.2, so #701 is not a governing predecessor.
Consistent with §2.6, documentation custody grants **no** deployment, factor
activation, S8.6, K designation or Strategy-8 reactivation authority.

**SEC-001 V3.1 classification crawl = CLOSED / HOLD --- REDESIGN REQUIRED.**
The first hop has no qualified source: `FIRST_HOP_SOURCE_NOT_QUALIFIED` over
six local sources, with **zero SEC requests** issued. Gate 0a was **NOT
COMPUTED** and bindings are **0**. This is **not** a Gate-0 coverage failure
(it was never authorized to compute) and **not** a taxonomy failure.
Governance commit `4893c6a` enforces the O-9 two-registry split. CI was **NOT
TRIGGERED BY DESIGN** for that work --- never record it as PASS, FAIL or
SKIPPED. This is distinct from, and does not reopen, the §2.6
successor-cleanup closure.

**Explicitly NOT re-observed at this sync** --- carry §2.2, §2.4 and §2.5
forward unchanged and **re-measure before use**: the governed corpus day
count beyond `2026-08-28`, S8.6, Strategy 8, and the live factor reading.
Factor readiness was **RED** at the §2.5 observation with #698 **merged /
undeployed / deployment not authorized**; the next natural unattended refresh
slot remains **Monday 2026-08-31 06:00 EDT**, and schedule pressure is still
not deployment authority.

------------------------------------------------------------------------

## 3. Final executable priority queue

  --------------------------------------------------------------------------------------------------------------------------------------------
  Priority             Work                    Class             Serves               Stop rule / acceptance           Next gate
  -------------------- ----------------------- ----------------- -------------------- -------------------------------- -----------------------
  **P0-1 continuous**  Continue governed MDQ   REQUIRED ENABLER  MDQ evidence / ATP   Each day must independently      Continued corpus
                       Phase-A                                   retention context    complete terminal → EOD → freeze accrual
                       capture/admission                                              → verify → mirror → custody and  
                                                                                      registered admissibility; no     
                                                                                      salvage                          

  **P0-2               Finish narrow           REQUIRED ENABLER  Durable governing    No scope creep; moving head      Custody closure
  docs/custody**       current-state/custody                     state                reopens affected review;         
                       PRs with exact-head                                            documentation creates no         
                       discipline                                                     operational authority            

  **P0-3 owner gate**  Decide whether to       REQUIRED ENABLER  Factor-dependent     Bind exact SHA/artifact/digest   Publication/readiness
                       deploy merged factor                      strategy safety /    before authorization; deployment proof
                       repair #698                               LOW-001              alone is insufficient            

  **P0-4 conditional** If factor deployment is REQUIRED ENABLER  Factor-system GREEN  Any failed                       GREEN eligibility
                       authorized: restore                                            producer/promotion/readiness leg 
                       publication/readiness                                          keeps RED; no                    
                       and obtain subsequent                                          activation/rebalance             
                       unattended scheduled                                                                            
                       PASS                                                                                            

  **P0-5 read-only**   Resolve LOW-001 S8.6    REQUIRED ENABLER  LOW-001              Owner ruling required; do not    S8.6 eligibility
                       check-2 SHA conflict                                           rollback merely to satisfy stale 
                                                                                      pin                              

  **P0-6 conditional** Separately authorize    STRATEGY-DIRECT   LOW-001              Checks 3/4/8 receive no          Rollback-baseline
                       S8.6; obtain genuine    ENABLER                                governance PASS while factor     restore
                       12/12                                                          RED; any invalid/failed check    
                                                                                      stops chain                      

  **P0-7 conditional** Restore baseline →      STRATEGY-DIRECT   LOW-001              Historical B3a reconstruction    Strategy-8 owner ruling
                       prospective B3a →       ENABLER                                prohibited; prospective proof    
                       custody → GREEN                                                requires separate authority      
                       reconfirmation                                                                                  

  **P0-8 owner gate**  Separate Strategy-8     STRATEGY-DIRECT   LOW-001              No automatic activation from     Paper observation
                       reactivation decision                                          deployment, S8.6, B3a, or        
                                                                                      custody                          

  **P1 read-only**     Account 6 provenance    REQUIRED ENABLER  Paper-account        Establish why IDLE, ownership,   Separate disposition
                       investigation           / OPS             governance           circuit-breaker/validation holds 
                                                                                      and transition procedure; no     
                                                                                      mutation                         

  **P1 reporting**     Correct zero-variance   REQUIRED ENABLER  Reporting            Report                           Normal PR
                       Sharpe diagnostic       / OPS             correctness          `N/A / insufficient variance`;   
                                                                                      no strategy-economics change     

  **P2 owner           SF1 NO-START census     STRATEGY-DIRECT   New PIT              Default remains no early start;  One pre-registration or
  exception**                                                    fundamental-change   requires explicit sequencing     STOP
                                                                 alpha                exception; stale factor spine ⇒  
                                                                                      NOT EVALUABLE                    

  **HOLD**             Phase-B/K2              REQUIRED ENABLER  Named                Do not open merely to rescue MDQ G10
                                               only if           broad-streaming      GO floor                         
                                               economically      strategy                                              
                                               justified                                                               

  **STOP-FOR-CYCLE**   GAPPER current cycle    STRATEGY-DIRECT   GAPPER               No rescue/tuning/same-evidence   Future separately
                                                                                      rerun                            authorized cycle only
  --------------------------------------------------------------------------------------------------------------------------------------------

**Parallelism rule:** passive MDQ capture, narrow documentation/custody
work, factor-deployment **preparation**, S8.6 check-2 **read-only
analysis**, Account-6 investigation, and reporting-only diagnostic work
may proceed in parallel because none requires live strategy mutation.
Factor deployment, S8.6 execution, rollback restore, prospective B3a,
Phase-B/K2, SF1 early start, and Strategy-8 reactivation remain
separately gated.

------------------------------------------------------------------------

## 4. B-1 / #696 final implementation contract

B-1 is **engineering-complete when the evaluator machinery is sound**,
even if governed K1 remains NOT EVALUABLE. A missing K1 authority is
then a bounded provenance question, not an open-ended engineering
project.

### 4.1 Admissibility / evidentiary boundary

The implementation must satisfy these invariants, independent of
class/function naming:

1.  `evidentiary` is **derived**, never a caller-supplied Boolean.
2.  An evidentiary K result requires real admissibility token(s)
    produced through the governed §7.1 gate path.
3.  `NOT_ADMISSIBLE` and `UNDETERMINED` never mint admissibility
    authority.
4.  Tokens are bound to the evaluated root/session scope; a token for
    one partition cannot launder another.
5.  Arbitrary dictionaries, caller assertions, environment switches,
    `force=` paths, or direct test minting cannot create governed
    evidence.
6.  Tests obtain passing tokens by driving the real `require_admissible`
    path through controlled adjudication fixtures.
7.  Diagnostic evaluation remains allowed, but the serialized result
    must preserve `evidentiary=false` and why.

Python cannot be made hostile-code-proof by convention; the acceptance
boundary is that **normal production/research callers have no supported
path to governed evidence that bypasses the real gate**.

### 4.2 K1 three-valued OR

Frozen K1 remains a disjunction. Required truth behavior:

  Limb A          Limb B          K1
  --------------- --------------- ---------------
  PASS            any             PASS
  any             PASS            PASS
  FAIL            FAIL            FAIL
  FAIL            NOT EVALUABLE   NOT EVALUABLE
  NOT EVALUABLE   FAIL            NOT EVALUABLE
  NOT EVALUABLE   NOT EVALUABLE   NOT EVALUABLE

**PASS dominates. FAIL requires both limbs evaluable and both failing.
Otherwise K1 is NOT EVALUABLE.**

The test suite must pin this behavior directly.

### 4.3 K1 governed-input provenance / `AuthorityRef`

Current state: **no K1 decision-provider authority and no
predeclared-defect-registry authority are bound.** Therefore governed K1
is currently **NOT EVALUABLE**.

Final contract for a future binding:

-   a Boolean declaration such as `DECISION_PROVIDER_BOUND=True` or
    `DEFECT_REGISTRY_BOUND=True` has **zero authority by itself**;
-   a binding requires an `AuthorityRef` (or equivalent immutable
    provenance object) carrying at minimum:
    -   stable authority identifier;
    -   SHA-256 of the governed artifact establishing the authority;
    -   reviewable artifact reference/location;
-   empty identifiers, malformed digests and missing artifact references
    are refused;
-   `InputProvenance` / `ungoverned_inputs` is **derived from actual
    supplied inputs and actual bound authority**, not caller flags;
-   stable reason identifiers must survive serialization, including at
    least:
    -   `decision_provider_unbound`
    -   `predeclared_defect_registry_unbound`
-   supplying an arbitrary provider or defect list without a governed
    binding remains **diagnostic-only**, even when every partition is
    admissible;
-   a test showing that a constructed valid `AuthorityRef` makes the
    mechanism capable of governed evaluation is a **future-contract test
    only**. It is not evidence that such an authority exists today;
-   when a real authority is later proposed, the owner/custody step must
    independently verify that the referenced governed artifact exists
    and its actual bytes match the declared SHA-256 before the binding
    is accepted.

The visible current-state declarations should remain false/none until
that separate governance event is completed. Flipping a Boolean must
never grant authority.

### 4.4 Frozen threshold regressions

Tests must pin the actual boundary, not merely nearby values:

-   K1: exactly `1/10 = 0.10` and another exact denominator such as
    `2/20 = 0.10` ⇒ PASS; below 10% ⇒ FAIL for that evaluable limb.
-   K3: construct an exact 50% reduction case, e.g. IEX missing 0.40 and
    SIP missing 0.20 ⇒ reduction 0.50 ⇒ PASS; below 0.50 ⇒ FAIL.

### 4.5 K3 invariants already accepted

Do not reopen unless the successor diff materially changes them:

-   grid is the **union** of observed symbol-minute cells, not a
    symbols×minutes Cartesian product;
-   half-open window **04:00--16:00 ET**;
-   `missing_rate_IEX = 0` ⇒ NOT EVALUABLE, not PASS;
-   raw row-count difference is diagnostic-only;
-   naive timestamps are refused;
-   sub-minute events collapse to one minute cell.

### 4.6 #696 completion procedure --- ✅ DISCHARGED *(marked at v1.0.2)*

**All eight steps below completed by 2026-08-28**: #696 is MERGED
(squash `1545656…`, approved head `77461c7…`, exact-head CI green), B-1
is ENGINEERING CLOSED, and the bounded K1 authority discovery is
complete with **K1 = NOT EVALUABLE / AUTHORITIES UNBOUND** (§2.3, §11).
This block is retained as the record of the procedure that was executed;
**nothing in it is outstanding work**, and re-running any step requires
a new reason, not this list. §§4.1--4.5 remain the standing contract for
any successor diff.

1.  Re-run full `tests/research/` with an unambiguous exit code/output;
    silence is inconclusive, not PASS.
2.  Confirm focused tests (local report observed 2026-08-28: 49), ruff,
    and mypy.
3.  Commit/push the provenance successor.
4.  Freeze and report exact successor SHA, commit count, changed-file
    count, clean working tree, focused-test count, research-tree result,
    ruff and mypy.
5.  Keep #696 **draft** for the focused immutable review of §§4.1--4.4.
6.  After review, ready-state CI must pass on the exact approved head.
7.  **Merge requires a separate owner ruling.**
8.  After merge, conduct at most **two working sessions** of
    provenance-only K1 authority discovery (target close by 2026-09-04).
    If no unique pre-corpus governed authority is found, record
    `K1 = NOT EVALUABLE` and close B-1. Do not create a provider or
    "predeclared" defect list after the corpus exists.

------------------------------------------------------------------------

## 5. LOW-001 activation path --- corrected final sequencing

LOW-001 is a strategy path, not an ATP data project. Its frozen
economics remain separate from DISC/Opportunity/MDQ signals.

### 5.1 Known completed facts

-   Dynamic-PIT v1.0.3 S8.6 historically passed 12/12 on the prior
    runtime.
-   B3a code artifact is pinned by #683 / merge
    `07a92330108390f8d5299e36b411150c08b9160c`.
-   Strategy 8 remains IDLE.

### 5.2 Required chain before any reactivation

``` text
fresh no-transition observation
  → separate S8.6 execution authorization
  → factor-system GREEN before checks 3/4/8 may receive governance PASS credit
  → owner resolution of the S8.6 check-2 runtime-SHA conflict
  → fresh S8.6 checks 1–12 on the authorized runtime
  → rollback-baseline restore iff genuine 12/12
  → separately authorized prospective B3a proof
  → required custody closure
  → factor-system GREEN reconfirmed
  → freeze LOW-001 paper-observation protocol
  → separate owner reactivation decision
```

Amendment 8 deployment is already CLOSED; do not repeat it as an
outstanding step. **The v0.16 activation calendar (close before
2026-08-31 10:32 ET, else slip to 2026-09-14 --- ruling O-5) is RETIRED**
*(v1.0.2)*: factor readiness RED and the S8.6 HOLD overtook it, and the
chain is now **gate-driven, not date-driven**. The dated target in the
hash-pinned History companion is historical evidence only, not a live
ruling. **Historical B3a reconstruction remains prohibited.**
Do not reuse the prior-runtime 12/12 result as new-runtime activation
proof. Do not start Strategy 8 merely because factor readiness becomes
GREEN, S8.6 passes, prospective B3a passes, or custody closes. Each is
necessary where applicable and not sufficient.

### 5.3 Paper observation design

Before reactivation, freeze the observation design in the LOW-001 track.
The profitability-oriented default proposed by this plan is:

-   ≥13 weekly rebalances / approximately one quarter;
-   net return versus the frozen PIT-static reference;
-   maximum drawdown;
-   turnover;
-   implementation shortfall versus decision price;
-   conformance-check pass rate;
-   EVIDENCE_NOT_FEEDBACK inside the observation window;
-   paper results may support KEEP or DEMOTE, **not upgrade the frozen
    economic verdict by themselves**;
-   RANK-001 may allocate only among independently validated strategies;
    LOW-001 paper observation does not silently alter RANK standing.

This protocol itself must be explicitly owner-frozen before activation;
this planning document does not activate Strategy 8.

------------------------------------------------------------------------

## 6. MDQ economics, G3 reachability and subscription treatment

### 6.1 Frozen qualification rules stay frozen

The ratified G3 floor remains **≥2 of K1--K6 both evaluable AND PASS**.
No definition, threshold, holdout, completeness rule or GO floor is
changed by the profitability-first plan.

Current planning reachability:

-   **K3**: evaluator engineering is merged through #696 and governed
    computation runs **offline** from an exact checkout of the approved
    code identity against admissible frozen partitions (§2.3, corrected
    at v1.0.2). Backend deployment is **not** a prerequisite for the K3
    value and must not be performed for that purpose.
-   **K1**: **NOT EVALUABLE / AUTHORITIES UNBOUND** after bounded
    discovery. Do not create post-corpus authority. The separate
    question of designating an already-existing pre-corpus artifact
    remains an owner/governance decision.
-   **K2**: NOT EVALUABLE unless G10 opens.
-   **K4**: current GAPPER cycle is STOP-FOR-CYCLE; do not manufacture
    evaluability or rescue the stopped cycle.
-   **K5**: cannot contribute to the GO floor under the signed ruling.
-   **K6**: event-contingent.

Therefore, under the profitability allocation decision **GO is not the
expected outcome** unless K1 becomes legitimately evaluable or K6
occurs. Before any K value is used for disposition, the owner should
prospectively record that HOLD-with-stated-extension or STOP is an
expected legitimate outcome of the allocation decision, not a reason to
rewrite criteria.

### 6.2 Do not open G10 merely to rescue MDQ

The 20-session / ≥250-symbol K2 streaming test is a qualification
capability, not alpha. **Do not implement Phase-B/G10 solely because K1
is unavailable or because the MDQ GO floor becomes difficult.**

Open G10 only when a named strategy/overlay requires broad streaming and
states the economic mechanism it will test. Otherwise K2 remains NOT
EVALUABLE for this cycle. The 2026-09-21 last-start date is factual only
if such an economic justification appears.

### 6.3 ATP subscription retention is an economic owner decision

The frozen K verdict must still be reported exactly as registered, but
subscription retention should not be treated as an automatic consequence
of K1--K6 if those criteria are largely non-strategy qualification
tests.

Recommended owner rule to ratify before G3:

1.  Determine whether any strategy expected to trade in the next cycle
    **requires SIP** to avoid the known IEX stub/spread false-reject
    class in its governed execution path.
2.  Determine whether CEE reaches `N ≥ 50` qualifying fills with a
    median SIP--IEX shortfall difference whose 95% interval excludes 0
    bps.
3.  If a named strategy has a governed SIP dependency, retain as a
    required execution enabler regardless of the K verdict.
4.  If no strategy dependency exists and CEE remains NOT EVALUABLE or
    economically ≈0, cancel at the economic decision point unless a
    newly pre-registered strategy names a SIP dependency.

This is a **recommended owner economic rule**, not developer authority
to cancel or retain a subscription.

------------------------------------------------------------------------

## 7. Next profitable-strategy generation queue

### 7.1 SF1 --- pull forward only by explicit owner exception

Purpose: cheaply test whether a distinct PIT fundamental-change
mechanism is even viable while GAPPER remains data-blocked.

Procedure:

1.  Check Sharadar `sep` / required SF1 spines for freshness before the
    census.
2.  If stale beyond the census's own freshness requirement: record
    `NOT EVALUABLE — STALE SPINE` and stop.
3.  Run the 4--6 hour NO-START census only after the owner grants the
    one-time sequencing exception.
4.  Measure minimum/maximum dates, eligible-security count, PIT fields,
    missingness, OOS/power feasibility.
5.  Write **zero strategy code** in this tranche.
6.  If population/PIT/OOS/power is inadequate, STOP. If viable, next
    step is exactly one prospectively registered fundamental-change
    hypothesis.

### 7.2 GAPPER --- current cycle stopped

The current GAPPER cycle is **STOP-FOR-CYCLE**. The frozen data contract
was not satisfied, and the same evidence may not be tuned, rescued, or
rerun to manufacture a result.

A \$0 entitlement feasibility test using existing authorized access may
be conducted outside the stopped GAPPER cycle. It is capability evidence
only. Success may support a future separately authorized cycle, but it
cannot alter the current STOP-FOR-CYCLE disposition.

**Governance boundary for that test** *(added at v1.0.2)*: the missing
halt/LULD data is missing because the SIP `s`/`l` channels are **not
subscribed by the governed collector**, and `capture_modes` is part of
the frozen manifest governance tuple. Changing the Phase-A collector's
subscription set would split the governed corpus mid-stream --- the same
hazard class the credential-restoration ruling avoided. The feasibility
test therefore must **not** modify the governed collector, its capture
modes, or its identity tuple in any way. It runs either as (a) a clearly
quarantined scratch capture of PRE_REGISTRATION_SMOKE class, inadmissible
to every K criterion and to any GAPPER evidence, using a separate
non-governed invocation; or (b) a documentation-level entitlement check
with no capture at all. Adding `s`/`l` capture to the governed collector
is a **governed change requiring its own owner ruling**, never a
feasibility-test side effect.

Do not convert passive forward accrual, a later entitlement finding, or
a new dataset into retroactive evidence for the stopped cycle.

### 7.3 MOM-001 L1 execution enhancement

This is the preferred enhancement path when enough observations exist
because it improves an already validated alpha mechanism rather than
inventing a new one.

Reopen only when ≥50 governed fills exist within a rolling 60-session
Phase-A population. Measure lower implementation shortfall / fewer false
spread-staleness rejects / better execution timing **without changing
the underlying ranking alpha**. If population remains below the
threshold, HOLD; do not manufacture observations.

### 7.4 New alpha candidates

MOM-CAND-001 and RSI-REV-001 may advance only through:

`candidate observation → mechanism → cost model → falsification → discovery-ledger citation / multiple-comparison disclosure → prospective pre-registration → untouched prospective validation → paper candidate`

Candidate/watchlist output is not a signal and cannot touch order, risk,
sizing or LOW-001 inputs without a separately registered economic
mechanism.

SIP-native MOM-LIQ / SIP-CONT / SIP-LSR work begins only if prior
evidence shows SIP adds material economic information beyond
data-quality or execution-safety value.

OPRA work remains future/conditional; no options capture program exists
merely because entitlement is available.

------------------------------------------------------------------------

## 8. Work explicitly outside the active strategy queue

The following may live in an OPS/product backlog or prove themselves
naturally, but receive **no dedicated strategy-program session** unless
they become the minimum blocking slice for a named P0/P1 strategy:

-   wrapper/systemd source custody as a standalone PR (the pre/post
    deployment SHA read in §5 is the only current blocking slice);
-   scheduled SQLite-backup file proof;
-   90-day JSON-prune survival proof;
-   branch hygiene / stale PR cleanup;
-   generic documentation-location cleanup;
-   broad DISC-MDQ feature-library construction while the population
    remains empty/narrow;
-   repeated manual DISC census work beyond cheap natural recomputation;
-   RANGE-SIP observation without a new prospectively named economic
    mechanism;
-   local live-cache migration ADR/build before a specific L1/L2
    strategy requires it;
-   OPRA-CAP capture before a named options/risk strategy requires it;
-   G10/K2 solely to rescue the MDQ GO floor;
-   general platform refactors with no named strategy consumer.

If one becomes a real blocker, promote **only the minimum blocking
slice**, then return it to OPS.

------------------------------------------------------------------------

## 9. Evidence and implementation invariants

### 9.1 MDQ partition admissibility

A partition may enter K evaluation only after the registered §7.1
adjudication. Integrity/readiness is necessary but not evidence by
itself.

Required properties include registered account/credential identity,
explicit feed, frozen universe/cadence/session scope, approved collector
identity, terminal completeness, freeze, successful verification, no
stray/unmanifested files, no post-freeze mutation, and the frozen
completeness/gap thresholds.

Inadmissible, smoke, scratch, reconstructed or post-hoc manufactured
material is excluded from all K criteria. Value-extraction outputs (CEE,
DISC, candidate features, etc.) never flow back into qualification
evidence.

### 9.2 Feed semantics

Every governed request remains explicit: `feed=iex`, `feed=sip`, or
`feed=opra`. Entitlement must never select semantics implicitly.

### 9.3 Research-plane isolation

K calculators and strategy-research programs remain read-only
research/analytics code. No order-path, broker SDK, live risk capability
or execution token is permitted unless a separate governed design
explicitly authorizes a migration.

### 9.4 No post-hoc criterion repair

Do not revise K definitions, thresholds, evaluability clauses, holdouts,
completeness thresholds, or "predeclared" inputs after looking at the
governed corpus merely to make a criterion evaluable or pass.

------------------------------------------------------------------------

## 10. Developer PR / CI / live-change discipline

1.  **Exact immutable candidate:** every substantive review and merge
    ruling names the exact head SHA.
2.  A head change reopens only the review surface affected by the change
    unless the diff expands unexpectedly.
3.  Draft-time fail-closed CI artifacts are not substantive failures
    when prerequisite jobs never ran; inspect whether the test jobs
    actually executed.
4.  Ready-state required CI must pass on the exact approved head before
    merge.
5.  **No merge by implication.** A green PR remains HOLD until the
    explicit merge ruling when one is required.
6.  **No deployment by implication.** Merge to `main` does not authorize
    image build/recreate, backend restart, live identity mutation,
    strategy activation, S8.6 execution, B3a proof or broker activity.
7.  For live mutations, preserve pre-state, exact source SHA,
    runtime/build identity, rollback target and post-state evidence.
8.  Do not expose or log credentials/secrets in evidence records.
9.  Acquisition deadlines outrank routine PR administration when the two
    conflict.
10. "No output" or a masked exit status is **inconclusive**, never green
    evidence.

------------------------------------------------------------------------

## 11. Owner decisions still required --- current list

These are explicit gates, not developer TODOs to resolve by inference:

  -----------------------------------------------------------------------
  Decision                            State / required action
  ----------------------------------- -----------------------------------
  **Factor-repair deployment (#698)** **HOLD / NOT AUTHORIZED.** If
                                      considered, bind exact target
                                      SHA/artifact/digest and
                                      post-deployment proof chain first.

  **Factor-system GREEN**             Requires successful deployment (if
                                      authorized), producer verification,
                                      live publication, readiness PASS
                                      and one subsequent unattended
                                      scheduled refresh PASS.

  **K computation authority           **DISCHARGED / CLOSED.** Successor
  custody / execution**               source identity designated; authority
  *(added and closed v1.0.3)*         record custodied by **#710**;
                                      post-custody runtime/source
                                      verification **PASS 5/5**; one governed
                                      K execution separately authorized,
                                      executed once, and the authorization
                                      **CONSUMED / CLOSED**. K1 authorities
                                      remain separately unbound (row below).
                                      **No further K execution or rerun is
                                      authorized.**

  **G3 disposition**                  **HOLD WITH ONE STATED EXTENSION.** K1
  *(added v1.0.3)*                    **NOT_EVALUABLE**; K3 arithmetic
                                      **PASS** but G3 credit **EXCLUDED**
                                      under **B1-VERDICT-PERSISTENCE-001**;
                                      the **>=2 EVALUABLE+PASS** floor is
                                      unsatisfied. **The extension is NOT
                                      exercised.** No G10/K2 rescue, K1
                                      authority manufacture, or K rerun. If
                                      no legitimate pre-existing extension
                                      path is available, the next disposition
                                      is **STOP**. Execution and verdict
                                      custody detail lives in **#711**, which
                                      is the custody authority for it.

  **Future-designation defects**      **IDENTIFIED / DEFERRED --- no fix in
  *(added v1.0.3)*                    this designation epoch.**
                                      **B1-VERDICT-PERSISTENCE-001** (the
                                      governed verdict omits the B1a/B1b
                                      qualification fields) and
                                      **MDQ-K-AUTHORITY-SCHEMA-STRICTNESS-001**
                                      (the authority loader accepts extra
                                      blob-map keys and does not validate
                                      digest syntax). Both fixes would edit a
                                      file in `GOVERNED_SOURCE_PATHS` and so
                                      destroy the designated source identity;
                                      they belong to a future designation
                                      cycle.

  **K1 authority designation**        **OPEN governance question only**
                                      as to whether an existing
                                      pre-corpus artifact may be
                                      designated by a new governing
                                      record. No provider/registry
                                      creation is authorized.

  **LOW-001 S8.6 check-2 SHA          Owner ruling required before any
  conflict**                          rerun. Do not infer rollback or
                                      repinning.

  **LOW-001 S8.6 execution**          **HOLD.** Separate authorization
                                      required; checks 3/4/8 cannot
                                      receive governance PASS while
                                      factor readiness is RED.

  **Prospective B3a**                 **HOLD.** Historical reconstruction
                                      prohibited; future proof requires
                                      prerequisites plus separate
                                      authorization.

  **Strategy-8 reactivation**         **HOLD.** Separate final ruling
                                      after genuine proof/custody chain
                                      and factor GREEN.

  **ATP retention economic rule**     Owner ratification required before
                                      it governs keep/cancel.

  **SF1 sequencing exception**        Required before the NO-START census
                                      is pulled forward.

  **Phase-B/K2 / G10**                Closed by default; open only for a
                                      named economically justified
                                      broad-streaming need.

  **Account 6 disposition**           Investigation only until provenance
                                      and governing transition procedure
                                      are established.

  **G3 expected-disposition           **DISCHARGED by #703** *(closed at
  recording** *(added v1.0.2;         v1.0.3)*. The expected disposition was
  discharged v1.0.3)*                 recorded **prospectively** and merged
                                      2026-08-29T17:06Z, squash
                                      `9ab6d94d`, before any governed K
                                      value existed, so its prospective
                                      character is preserved. No longer an
                                      active owner gate. It changed no
                                      criterion, and an expected disposition
                                      is not a predetermined verdict:
                                      non-influence and the §9.4
                                      no-post-hoc-criterion-repair rule
                                      continue to bind.

  **LOW-001 paper-observation         **OPEN.** §5.3's protocol must be
  protocol freeze** *(added v1.0.2)*  owner-frozen in the LOW-001 track
                                      before any reactivation; this plan
                                      proposes the default but cannot
                                      freeze it.

  **Prospective B3a harness           **OPEN --- precedes the B3a HOLD
  definition** *(added v1.0.2)*       row above.** The historical harness
                                      is unavailable and reconstruction
                                      is prohibited, so a future proof
                                      first needs an owner-accepted
                                      specification of the new harness
                                      (scope, inputs, pass criteria,
                                      version/timestamp discipline).
                                      Authorization of a proof run is
                                      meaningless until the artifact it
                                      authorizes is defined.
  -----------------------------------------------------------------------

**Resolved/removed from the active owner list:** Amendment 8 deployment
is CLOSED; #696/B-1 engineering is CLOSED; K1 bounded discovery is
complete with NOT EVALUABLE / AUTHORITIES UNBOUND; current GAPPER cycle
is STOP-FOR-CYCLE; SEC-001 successor cleanup is CLOSED.

------------------------------------------------------------------------

## 12. What this final plan does NOT authorize

-   A second Algo Trader Plus subscription.
-   Any MDQ order or broker capability.
-   Phase-B/WebSocket implementation without a strategy-backed G10
    decision.
-   Direct live-consumer reads from the immutable MDQ archive.
-   SCAN/DISC/Opportunity candidate output becoming an order/risk/sizing
    signal.
-   GAPPER Stage-0 execution against a corpus that fails its frozen data
    contract.
-   Metadata fiction to satisfy a missing dataset contract.
-   MR-002 continuation; any revival is a new prospective program.
-   Profitability-Acceleration or reserve-strategy code before its
    NO-START/pre-registration gate.
-   Reopening rejected strategies without a genuinely new prospective
    economic mechanism.
-   Exploration output entering K1--K6 qualification.
-   Revising frozen K criteria after corpus inspection.
-   Exploratory holdout access before hypothesis pre-registration.
-   DISC/Opportunity/MDQ/news/SIP signals entering LOW-001 Dynamic-PIT
    economics.
-   Treating LOW-001 Dynamic PIT as permission to weaken static strategy
    registration elsewhere.
-   Credential switching to recover a failed MDQ slot.
-   Backfilling/salvaging/manufacturing a lost governed capture day.
-   Treating freeze exit 0, health checks, or code identity alone as
    proof of successful governed capture/deployment.
-   Relaxing universe, credential, readiness or evidence semantics to
    make a gate pass.
-   Deployment of merged #696/#698 behavior by implication.
-   Factor-driven activation, ranking or scheduled factor rebalance
    while readiness is RED.
-   Using `bootstrap/code.tgz` as governed deployment authority.
-   Creating or backfilling K1 provider/defect-registry authority after
    the corpus exists.
-   Governance PASS credit for S8.6 checks 3/4/8 while factor readiness
    is RED.
-   Rollback solely to satisfy the stale S8.6 check-2 runtime pin.
-   Historical B3a reconstruction.
-   Rescue/tuning/rerun of the stopped GAPPER cycle against the same
    evidence.
-   Any Strategy-8 reactivation from this document alone.

------------------------------------------------------------------------

## 13. Final review disposition

**v1.0.2 --- STATE/PROCEDURE-SURFACE SYNC: READY FOR CUSTODY / OWNER
ACCEPTANCE.**

Changes applied at v1.0.2 (findings F1--F6 of the 2026-08-28 v1.0.1
review; no economics, frozen definitions, or authority boundaries
touched):

1.  **F1 --- K computation decoupled from backend deployment** (§2.3,
    §6.1): governed K values are computed offline from the approved code
    identity against admissible partitions; deploying #696 to the live
    backend for that purpose is prohibited as an unjustified Tier-3
    touch. MERGED ≠ DEPLOYED continues to govern live behavior (#698).
2.  **F2 --- §4.6 marked DISCHARGED** so a closed procedure cannot be
    read as open work.
3.  **F3 --- GAPPER \$0 feasibility test given its governance boundary**
    (§2.6, §7.2): it may not touch the governed collector's identity
    tuple or capture modes; channel additions are a separate owner
    ruling.
4.  **F4 --- three owner decisions promoted from prose into §11**: the
    prospective G3 expected-disposition recording, the LOW-001
    paper-observation protocol freeze, and the prospective-B3a harness
    definition.
5.  **F5 --- the v0.16 LOW-001 activation calendar (08-31 → 09-14 /
    ruling O-5) explicitly RETIRED** (§5.2); the chain is gate-driven.
6.  **F6 --- observation dating applied to the remaining undated facts**
    (focused-test count, factor RED reading) and the header status
    wording aligned (ready for custody, not for another review pass).

The unlanded v1.0.1 review disposition is retained below for review
provenance. v1.0.1 was an intermediate review artifact, not a separately
custodied governing plan.

**v1.0.1 --- CURRENT-STATE SYNC (2026-08-28).**

This successor does not reopen the v1.0 strategy economics, frozen MDQ
definitions, authority hierarchy, profitability admission test, or
research-plane isolation. It updates only the execution/state surface
made stale by subsequent governed events.

Load-bearing updates:

1.  Repository state is now explicitly **point-in-time evidence**, not a
    continuously maintained assertion of `main`. The "ahead by"
    statement is deliberately non-exhaustive (`at least #696 and #698`)
    so ordinary later merges do not make the governing document false.
2.  Deployment state is separated from repository state: Amendment 8 is
    **DEPLOYED / ACCEPTED / CLOSED** at `3f32c75b…`; merged #696/#698
    behavior is not inferred into that runtime.
3.  The MDQ corpus is now **seven sealed/admitted days through
    2026-08-28**, with 08-24 retained as the sole lost trading day in
    the interval.
4.  #696/B-1 is **MERGED / ENGINEERING CLOSED**; K1 is **NOT EVALUABLE /
    AUTHORITIES UNBOUND**; K2 remains closed by default; K3 runtime
    computation still requires authorized deployment.
5.  Factor readiness is **RED** and carries a global
    activation/ranking/rebalance interlock. ADR-0051 shared adjudication
    is already established and must not be reopened.
6.  LOW-001 S8.6 remains HOLD. Checks 3/4/8 receive no governance PASS
    while factor readiness is RED; check 2 has a separate runtime-SHA
    owner decision. Historical B3a reconstruction is prohibited.
7.  GAPPER is **STOP-FOR-CYCLE**; no same-evidence rescue or tuning.
8.  The active work plan is explicitly parallel where safe: MDQ passive
    accrual, narrow custody/docs, read-only factor deployment
    preparation, S8.6 check-2 analysis, Account-6 investigation, and
    reporting correctness may proceed without granting live mutation
    authority.

Future **state-only** updates should continue to modify a compact
current-state block rather than rewrite historical sections. Mutable
repository facts must always be observation-bound. A future change to
strategy economics, qualification definitions, authority boundaries, or
the profitability queue requires an explicit successor design version or
separately governed strategy pre-registration.

**Developer rule:** if this plan conflicts with a frozen registration,
sealed evidence record, accepted ADR, or explicit owner ruling, stop and
use the higher-authority artifact. Do not reconcile the conflict by
inference.
