# TradingWorkbench SEC-001 V3.1 — Historical Issuer-Lineage & PIT Sector Classification Redesign
## Design / Implementation Plan v1.1 — FINAL DESIGN

**Status:** FINAL DESIGN — supersedes v1.0; owner implementation authorization required before Gate 0a / WP0A execution  
**Program:** SEC-001  
**Candidate:** SEC-001 V3.1-RC (new successor candidate; V3-RC is STOP / REDESIGN and is not resumed)  
**Date:** 2026-08-26  
**Design decisions:** **O-1 through O-9 resolved in §19**  
**Implementation authority:** **NONE until explicit owner authorization; when authorized, Gate 0a / WP0A ONLY**  
**Economic authority:** **NONE until the new classification-coverage gate passes**  
**Runtime authority:** **NONE until research GO and separate runtime gates pass**

**v1.1 finalization (2026-08-26):** incorporates the post-v1.0 review. A new **Gate 0a / WP0A frozen-class satisfiability gate** now precedes the FPI source gate: every class permanently unresolved by already-ratified rules (especially `excluded_low`, plus lineage-stable zero-filing cases) remains unresolved and every disputed/repairable cell is treated optimistically as resolved. Gate 0a is computed from existing sealed V3 artifacts, is return-blind, and hard-stops V3.1 if even that ceiling cannot satisfy O-2. The existing FPI gate becomes **Gate 0b / WP0B**. The source contract now explicitly treats SEC `index-headers.html` SIC as admissible even when `inside_sec_header=false`; literal `<SEC-HEADER>` containment is required only on the filing-document path. F-6 is reclassified as a labeling/flag-semantics issue, not an observed body-text-SIC defect. Added Gate-0b lineage re-entry, governed-slot denominator control, exact V3 known-answer fixture, pre-WP4 capacity envelope, return-blind CI enforcement, and clarification that CIK-once acquisition structurally prevents the V3 shared-CIK collision while immutable artifact keys remain defense-in-depth.

**Diagnostic evidence motivating Gate 0a (not itself the governed Gate-0a adjudication):** on the sealed V3 corpus, `excluded_low` alone exceeds the ten-name weekly unresolved budget in 193/1,247 governed weeks (15.48%); the last four years reach only a 71.579% weekly-pass ceiling against `theta_window=95%`. Because these diagnostics were computed on the V3 lineage model, Gate 0a must treat any lineage-disputed cell as resolved and count only lineage-stable permanently-unresolved cells before issuing a hard STOP.

---

## 0. Executive decision

SEC-001 V3-RC failed its frozen classification-coverage gate before economics were run.

The successor must **not** repair the failed epoch in place, retune thresholds, relax `excluded_low`, move the start date for convenience, or reuse the spent coverage token.

The redesign keeps the economic strategy unchanged and replaces the historical issuer/classification infrastructure with an explicit three-layer model:

1. **Trading identity** — permanent security identity / permaticker used by the PIT-200 portfolio population.
2. **Registrant episode** — effective-dated `(permaticker, CIK, valid_from, valid_to)` lineage.
3. **Acquisition identity** — unique SEC CIKs that must be crawled to support those registrant episodes, including predecessor CIKs and any prospectively approved pre-period state-seeding scope.

The first gate is not implementation. It is **Gate 0a — frozen-class satisfiability** using existing sealed, return-blind V3 artifacts. Gate 0a holds every class that is permanently unresolved under already-ratified V3.1 rules unresolved, treats every disputed or potentially repairable cell optimistically as resolved, and asks whether O-2 is satisfiable in principle.

Only if Gate 0a passes does V3.1 proceed to **Gate 0b — FPI source-availability / satisfiability**. If either gate proves the frozen coverage requirements impossible, V3.1 stops before lineage engineering or a new large crawl.

---

## 1. Why a new candidate is required

### 1.1 V3-RC disposition

V3-RC is permanently recorded as:

**STOP / REDESIGN — CLASSIFICATION COVERAGE GATE FAILED**

Measured pre-F-6-adjudication coverage:

- ticker-week resolution: `231,446 / 249,400 = 92.801%`
- qualifying rebalances at `theta_name = 0.95`: `425 / 1,247 = 34.08%`
- no trailing start satisfied `theta_window = 0.95`
- best measured start reached only `65.089%` qualifying rebalances
- economics were **DENIED / NOT REACHED**

The coverage token `5b26ffa2...` is **SPENT / CONSUMED** and may never govern a successor run.

### 1.2 Primary failure anatomy

Unresolved ticker-week cells in V3-RC were dominated by:

| Cause | Cells | Share of unresolved | V3.1 interpretation |
|---|---:|---:|---|
| Successor-CIK / issuer-lineage gap | 10,800 | 60.2% | Primary redesign target |
| `excluded_low` SIC mapping rows | 5,224 | 29.1% | Frozen behavior; do not retune |
| crawl-window warm-up / left-edge state | 1,870 | 10.4% | Redesign acquisition seeding |
| CIKs with no classification segment | 60 | 0.3% | Already decomposed: GX/FRCB have zero in-window filings; LHSP has six filings, all NO_SIC. GX/FRCB feed Gate 0a as source-empty cases where lineage is stable. |
| effective-date conflicts | 0 | 0% | Existing fail-closed resolver behaved correctly |

When lineage and `excluded_low` were ignored diagnostically, the epoch classified 99%+ of ticker-weeks. This shows that the acquisition/parser machinery was broadly capable; the dominant defect was **historical registrant identity**, not SEC throughput.

### 1.3 Why the current-CIK model is invalid for deep history

The V3 population associated each permanent trading identity with a current CIK. For re-registered issuers, that CIK does not necessarily exist across the identity's historical PIT membership.

Example observed in V3:

- DIS current CIK: `1744489`
- first in-window filing for that registrant: 2019-05-08
- PIT-200 membership for the permanent identity begins in 2000
- result: hundreds of historically unresolved cells despite a continuous economic/security identity

The successor therefore requires an **effective-dated registrant lineage**, not a current CIK projected backward.

---

## 2. Governing principles

### 2.1 Preserve the failed candidate

V3-RC artifacts, epochs, coverage result, Defects E/F/G, and STOP record remain immutable history.

V3.1 is a new candidate. It does not:

- resume a failed V3 epoch;
- inherit V3 terminal credit;
- reuse V3 acquisition order;
- reuse the V3 union artifact;
- reuse the V3 coverage token;
- rewrite failed evidence.

### 2.2 Change the minimum necessary layer

The redesign targets historical classification infrastructure only.

The following economic choices carry forward unchanged under O-1:

- momentum signal: **252/21**
- sectors selected: **K = 3**
- equal sector sleeves
- long-only
- 10% name cap
- strongest 4–5 names per selected sector
- weekly rebalance
- governed research slot: Monday 10:24 America/New_York when Monday is a regular open U.S. equity session
- transaction costs: 10 bps one-way base / 25 bps stress
- absolute Sharpe gate: `>= 0.75`
- five-window robustness gate: `>= 4/5` positive net-return windows
- corrected true-traded-dollar PIT liquidity universe
- `excluded_low` treatment unchanged

**Final decision O-1 — RATIFIED:** all economic construction and economic thresholds above remain unchanged for V3.1.

### 2.3 Coverage standards are not tuned after failure

Carry-forward under O-2:

- `theta_name = 0.95` → at least 190/200 resolved per rebalance
- `theta_window = 0.95`
- `theta_span_min = 20 years`
- original period tested first
- earliest coverage-qualified start only
- no interior span excision
- deterministic five-window construction
- no economics before coverage PASS

**Final decision O-2 — RATIFIED:** these coverage rules remain unchanged for V3.1.

### 2.4 Fail closed

No successor stage may manufacture a historical answer from:

- ticker equality;
- latest/current CIK projected backward;
- current sector label;
- current `shortable` / metadata used as historical truth;
- silent SIC default;
- heuristic predecessor assignment;
- outside-`<SEC-HEADER>` SIC;
- retroactive artifact overwrite;
- missing source interpreted as negative classification evidence.

Unresolved is a valid state. Guessing is not.

### 2.5 Trial-ledger standing *(added v0.2)*

The SEC-001 trial ledger recorded V3-RC as trial #1. Its entry is annotated **`ECONOMICS_NOT_REACHED`**: the coverage gate stopped the candidate before any return was observed, so the historical evaluation window's **economic** information remains unconsumed. Consequences:

- Under the **SEC-001 trial-ledger convention**, V3-RC did not consume an economic look because economics were never reached. **V3.1-RC is therefore the first economic trial of this hypothesis on this governed window under that ledger.** No additional multiplicity adjustment is triggered by V3-RC alone. This also supports O-8A: same economic hypothesis, first governed economic look — a point release rather than a new major economic candidate.
- Coverage diagnostics (resolution rates, lineage-gap censuses, per-week grids) contain **no return information**; a redesign informed by them is not economic mining. This exemption holds **only while coverage artifacts stay return-blind** — no coverage-stage artifact may contain, join to, or be filtered by any return, price-performance, or P&L field. A coverage artifact that touches returns forfeits the exemption and increments the economic ledger.
- Coverage-gate iterations are themselves ledgered (as coverage attempts, distinct from economic trials) so the record shows how many redesigns the classification problem consumed, even though the economic clock has not started.

---

## 3. Three identity layers

### 3.1 Layer A — trading identity

Canonical key:

`permaticker` / permanent security identity

Purpose:

- PIT-200 membership
- weekly coverage denominator
- portfolio construction
- economic evaluation

The trading population remains security-centric.

### 3.2 Layer B — registrant episode

Canonical record:

```text
permaticker
registrant_episode_id
cik
valid_from
valid_to
source_identity
source_effective_at
evidence_refs[]
adjudication_status
```

Rules:

- one permanent trading identity may have multiple effective-dated registrant CIK episodes;
- intervals may not silently overlap;
- a same-date conflict fails closed;
- gaps remain unresolved unless governed evidence closes them;
- ticker is descriptive metadata only, never a lineage key;
- no current-CIK backfill into earlier history.

### 3.3 Layer C — acquisition identity

Canonical key:

`CIK`

Purpose:

- SEC submissions/index acquisition
- filing/header retrieval
- effective-dated SIC observations

Each governed CIK should be acquired **once per frozen acquisition scope**, regardless of how many trading identities reference it.

This removes the V3 pattern where shared CIKs were crawled multiple times under different ticker identities.

---

## 4. Gate 0 — pre-engineering satisfiability

Gate 0 has two ordered subgates. **Gate 0a is strictly first.** Gate 0b may not run if Gate 0a stops the candidate.

### 4.1 Gate 0a — frozen-class satisfiability

#### 4.1.1 Why Gate 0a comes first

O-2 freezes the coverage requirements. O-6 freezes the exact SIC mapping and the rule that `excluded_low` is unresolved.

Therefore an optimistic satisfiability bound may **not** treat `excluded_low` as resolvable. Doing so would be counterfactual to a ratified rule and could authorize expensive lineage/acquisition work into a candidate already foreclosed by its frozen taxonomy.

Gate 0a asks:

> Assuming perfect lineage, perfect FPI availability, perfect acquisition, and perfect classification everywhere except classes that are permanently unresolved by already-ratified V3.1 rules, can any admissible >=20-year span ending 2026-06-12 satisfy `theta_name` and `theta_window`?

This is a **return-blind structural satisfiability** question.

#### 4.1.2 Gate-0a unresolved classes

Count as unresolved only cells that are proven non-recoverable under the final design **without relying on the V3 current-CIK defect**.

At minimum:

- `excluded_low` mapping outcomes under the exact O-6 mapping, **only where the registrant identity for that week is lineage-stable / not disputed**;
- zero-in-window-filing identities whose relevant registrant identity is already lineage-stable and for which no admissible state seed can exist inside the governed source boundary;
- any other class explicitly frozen by O-1 through O-9 as permanently unresolved.

For hard-stop purposes:

- a lineage-disputed cell is treated as **resolved**;
- a source-availability-disputed cell is treated as **resolved**;
- an FPI cell is treated as **resolved** until Gate 0b;
- a classification observation that could change under later lawful evidence is treated as **resolved**.

This makes Gate 0a a true optimistic ceiling. It may miss a future failure; it may not manufacture one.

#### 4.1.3 Gate-0a governed grid

The denominator is driven exclusively by the frozen **1,247 governed research slots**, not by keys present in `pit200_membership_v2.json`.

The membership artifact contains 1,380 Monday keys: 1,247 governed slots plus 133 holiday Mondays. Holiday keys are not rebalances and never enter the coverage denominator.

For each governed slot:

1. obtain the exact 200 trading identities from the pinned PIT-200 membership;
2. count only Gate-0a-proven permanently unresolved identities;
3. compute `resolved_ceiling = 200 - permanently_unresolved_count`;
4. apply `theta_name >= 190/200`;
5. roll qualifying weeks into the frozen five-window / `theta_window` / `theta_span_min` rules.

No averages decide the gate.

#### 4.1.4 Gate-0a decision

- **G0A PASS — FROZEN CLASSES SATISFIABLE**: at least one admissible >=20-year span remains mathematically satisfiable under the optimistic frozen-class ceiling.
- **G0A STOP — FROZEN CLASSES FORECLOSE COVERAGE**: no admissible span can satisfy O-2 even under the optimistic ceiling.
- **G0A HOLD — INPUT STABILITY UNRESOLVED**: a cell proposed as permanently unresolved cannot yet be proven lineage-stable/source-stable. HOLD must name the exact evidence needed and defaults to STOP if the bounded evidence task expires unresolved.

A G0A STOP ends V3.1. **WP0B, WP1, acquisition, a new coverage token, and economics are not authorized.**

#### 4.1.5 Diagnostic V3 evidence

The post-v1.0 review measured the following on the sealed V3 corpus:

```text
excluded_low names/week: mean 4.19, median 2, p90 11, max 14
weeks excluded_low alone > 10 names: 193 / 1,247 = 15.48%
terminal 4-year weekly-pass ceiling: 71.579%
```

These figures are **motivation and regression evidence**, not by themselves the V3.1 Gate-0a adjudication, because they were computed on the V3 lineage model. Gate 0a must re-establish that every cell counted against the ceiling is lineage-stable; disputed cells are credited optimistically.

#### 4.1.6 If Gate 0a stops — legitimate redesign boundary

A Gate-0a failure may not be answered by changing O-2 or O-6 inside V3.1.

The legitimate path is a **new versioned successor/adjudication**. If the SIC mapping or `excluded_low` classification quality is independently re-reviewed, that review must:

- be justified on classification/taxonomy quality grounds, not on coverage impact;
- use prospectively stated quality criteria;
- be performed by an evaluator isolated from the row-level coverage-impact table to the maximum practical extent;
- record any unavoidable prior knowledge/conflict explicitly;
- seal the revised mapping **before** any new satisfiability or coverage measurement;
- create a new candidate/version and new coverage ledger entry.

Example: a future classification-quality review could independently ask whether SIC `7370` maps correctly under the intended GICS taxonomy. The fact that `7370` materially affects the failed gate is **not** evidence for how it should map.

### 4.2 Gate 0b — FPI source-availability / satisfiability

Gate 0b runs only after G0A PASS.

#### 4.2.1 Why Gate 0b exists

Observed V3 facts:

- 141 FPI-filing CIKs in the V3-reachable population;
- 122/141 had no acquired filing before 2002;
- in 2000, affected FPI names averaged ~8.1 per 200-name rebalance, max 11;
- in 2001, average ~6.1;
- `theta_name` permits only 10 unresolved names total.

Lineage repair does not solve single-CIK FPIs whose earlier electronic filings may not exist.

#### 4.2.2 Gate-0b provisional population

Before WP1, the available population is necessarily derived from V3's trading population/current-reachable registrants.

Freeze it explicitly as:

**`V3_REACHABLE_FPI_CIK_POPULATION_PROVISIONAL`**

It is a Gate-0b screening population, **not** the final V3.1 lineage population.

If WP1 later discovers any additional FPI registrant episode intersecting the candidate span, or changes FPI/source-unavailable status in a way that can add unresolved identity-week cells, **Gate 0b must be re-entered and re-adjudicated before WP2 population freeze**. The earlier G0B PASS is not inherited automatically.

#### 4.2.3 Gate-0b question

> Do admissible electronic SEC sources contain enough pre-2002 filing-existence history for the provisional FPI population to leave the frozen V3.1 coverage rules satisfiable, assuming every non-source-unavailable cell is resolved?

This is a **source-availability** question, not a classification or economic question.

#### 4.2.4 Gate-0b source scope

Gate 0b may inspect SEC source availability only.

Prospective source classes:

- submissions API current filing index;
- submissions older-shard indexes;
- SEC Archives filing/index-header resources;
- historically applicable 20-F / 20-F/A / 40-F / 40-F/A paths;
- historical form aliases/equivalents only under O-3.

**SIC-blind scope guard:** Gate 0b operates at index/metadata level only — filing existence, form types and dates. **No SIC extraction** from headers, index-header renderings, filing bodies or exhibits.

No sector mapping, price, return, P&L, or economic field may enter Gate 0b.

#### 4.2.5 Gate-0b optimistic satisfiability test

For each governed rebalance week:

- source-unavailable FPI identity-week cells remain unresolved;
- every other cell is resolved;
- use actual PIT-200 weekly membership;
- apply `theta_name`, then `theta_window`, then `theta_span_min`;
- use original-period-first and earliest-qualified-start only.

Decision:

- **G0B PASS — FPI SOURCE HISTORY SATISFIABLE**
- **G0B STOP — FPI SOURCE HISTORY INSUFFICIENT**
- **G0B HOLD — FPI SOURCE AVAILABILITY UNRESOLVED**

A HOLD must name the exact unresolved archive/source fact, bounded evidence task and default STOP disposition.

Gate 0b does **not** authorize WP1 automatically.

### 4.3 Historical-form rule *(O-3 RATIFIED)*

The observed 10-K deficit around the retirement of form 10-K405 is recorded but is not currently a coverage blocker because quarterly filings provided redundancy.

Final rule:

- do not add 10-K405 merely to improve a result;
- admit a historical alias only if Gate 0b/source-history work establishes that it is required for state continuity or evidence completeness under prospectively stated criteria;
- freeze the form set before successor acquisition.

## 5. Gate 1 — effective-dated issuer / CIK lineage

### 5.1 Objective

Build a reproducible, governed mapping:

`permanent trading identity -> effective-dated registrant CIK episode(s)`

for every V3.1 identity over the candidate historical span plus any state-seeding period.

### 5.2 Acceptable evidence classes

The lineage design must prefer authoritative, date-bearing evidence. Candidate evidence classes may include:

- vendor permanent-security identity history;
- vendor CIK fields when explicitly snapshot/effective-date qualified;
- SEC registrant filing history;
- corporate succession / re-registration evidence;
- separately governed predecessor/successor records.

No evidence class is automatically authoritative merely because it is available.

### 5.2a Final evidence-sufficiency standard — inward bounding *(O-9 RATIFIED)*

Episode-evidence sufficiency is a load-bearing control. The final rule is:

**Episodes are inward-bounded by evidence.** For each `(permaticker, cik)` episode:

- `valid_from` may be established by an authoritative, date-bearing transition/succession/re-registration record, or by an equivalently pinned vendor effective-dated record. **Absent such boundary evidence**, it may be no earlier than the first authoritative filing observation tying that CIK to the security;
- `valid_to` may be established by an authoritative, date-bearing transition/termination/succession record. **Absent such boundary evidence**, it may be no later than the last authoritative filing observation tying that CIK to the security;
- unsupported edges remain **gaps**, and gaps remain unresolved ticker-weeks. Filing observations support the interior span between their evidence bounds; they do not license projection beyond those bounds.

**Episode assignment** requires one of: (i) vendor permanent-identity history whose snapshot/effective-date provenance is pinned; or (ii) SEC filing-history evidence of registrant status during the interval.

**Predecessor/successor links** additionally require an explicit recorded basis — a succession/merger filing, a governed vendor succession record, or an owner-adjudicated evidence bundle — never temporal adjacency, name similarity, or "same company economically."

Why inward: this makes the lineage layer **structurally incapable of manufacturing coverage** — the failure mode that killed V3-RC was identity projected beyond its evidence (current CIK backward); inward-bounding is its exact inverse. Honest gaps cost coverage, and Gate 0 has already told us whether we can afford honesty. A future proposal to outward-extend any episode beyond its evidence is a redesign decision, never a resolver behavior.

**Final decision O-9 — RATIFIED:** inward-bounding is the episode evidence-sufficiency standard, subject to the authoritative-boundary clarification above.

### 5.3 Prohibited shortcuts

- ticker equality
- name similarity alone
- current CIK retrojected to first historical appearance
- current vendor row treated as effective-dated history
- “same company economically” without registrant evidence
- inferred predecessor relation without a recorded adjudication basis

### 5.4 Lineage census

Before acquisition population freeze, emit:

```text
trading_identities_total
single_episode_identities
multi_episode_identities
identities_with_lineage_gap
identities_with_overlap_conflict
unique_ciks
predecessor_ciks_added
source/evidence class counts
```

Gate:

- conflicts: 0
- any unresolved lineage gaps remain explicitly unresolved
- no heuristic fallback
- every accepted episode reproducible from pinned evidence

### 5.5 Successor population invalidation

V3 artifacts are not reusable as frozen successor population identities:

- V3 frozen acquisition order `e8445b0b...` — **INVALID FOR V3.1**
- V3 union `d338e65f...` — **INVALID FOR V3.1**
- V3 current-CIK sidecar — historical provenance only

V3.1 must create new artifacts after lineage is frozen.

---

## 6. Gate 2 — acquisition population and deterministic order

### 6.1 Acquisition population

Derive the unique CIK set required by:

- effective-dated registrant episodes intersecting the candidate evaluation span;
- prospectively approved pre-period state-seeding scope;
- no unrelated CIKs.

The acquisition population is not the same as the 1,167 trading-identity population.

### 6.2 Deterministic order

Freeze a new deterministic CIK order.

Final key:

```text
(min_effective_date, numeric_cik)
```

This CIK-centric order is frozen after lineage is frozen and before acquisition. It must not depend on filing count, classification success, or coverage. The rejected trading-identity-coupled alternative remains historical review context only and is not authoritative.

**Final decision O-4 — OPTION A:** successor acquisition order is `(min_effective_date, numeric_cik)`.

### 6.3 New frozen artifacts

At minimum:

- `SEC001_V3_1_TRADING_IDENTITY_POPULATION_V1`
- `SEC001_V3_1_REGISTRANT_LINEAGE_V1`
- `SEC001_V3_1_ACQUISITION_CIK_UNION_V1`
- `SEC001_V3_1_ACQUISITION_ORDER_V1`
- source/version manifest binding every input

---

## 7. Gate 3 — pre-period classification state seeding

### 7.1 Problem

Starting acquisition exactly at `2000-01-01` can leave early-2000 weeks unresolved even when an admissible SIC was filed before the evaluation period and remained effective.

### 7.2 Final state-seeding rule *(O-5=A)*

For each registrant CIK active at the first candidate evaluation slot:

1. search backward in admissible electronic filings;
2. stop when the most recent admissible SIC observation on/before the first slot is found;
3. if no such electronic filing exists, record `NO_PREPERIOD_ELECTRONIC_SIC`;
4. never infer the state from a later filing.

This is a state-seeding acquisition, not an economic warm-up.

### 7.3 Bound

Final bound:

- electronic search floor = the earliest admissible electronic-archive boundary established by Gate 0 for the relevant source/form class; no source class is projected earlier than its proven archive availability;
- no arbitrary “N-year” lookback if the authoritative archive can be bounded directly;
- acquisition request/byte ceilings remain explicit.

This is preferable to blindly setting `CRAWL_SINCE` several years earlier.

**Final decision O-5 — OPTION A:** state seeding is evidence-bounded acquisition of the latest admissible pre-start SIC state, not a fixed calendar warm-up.

---

## 8. Gate 4 — SEC acquisition and evidence custody

### 8.1 Carry forward proven Defect-E/F controls

- exact authorized forms, prospectively frozen;
- GET only;
- authorized SEC domains only;
- single-host fair-access policy;
- actual-send timing evidence;
- 403 latch/halt;
- bounded 429/5xx retry;
- ranged fallback uses decoded document-byte semantics;
- ignored-Range `200` handled by bounded streaming;
- hard per-response / per-record byte ceiling;
- no materialize-then-slice pseudo-streaming;
- exact parser-facing decision-byte retention;
- no encoded body reaches parser undecoded.

### 8.2 Immutable artifact identity — defense in depth against Defect G

CIK-once acquisition in §8.3 is the **structural fix** for the V3 Defect-G mechanism: the same CIK/accession is no longer reacquired under multiple ticker identities. Immutable artifact identity remains mandatory as defense in depth so future refactors or alternate source variants cannot reintroduce mutable-path overwrite.

Required immutable artifact identity may use either of the following governed forms:

```text
CIK /
accession /
source_variant /
observation_id
```

or content-addressed storage:

```text
sha256/parser_body
```

with immutable per-observation references.

Requirements:

- CREATE-ONCE / no overwrite
- artifact hash is part of the manifest record
- every manifest record independently resolves to retained bytes matching its digest
- duplicate content may deduplicate only through content-addressed identity, never by mutable path overwrite

### 8.3 CIK-centric acquisition — structural Defect-G prevention

Acquire each unique CIK once.

A shared CIK referenced by multiple trading identities does not trigger duplicate SEC acquisition.

Classification consumers later project the CIK result through the effective-dated lineage to the trading identities.

---

## 9. Gate 5 — admissible SIC extraction and segment construction

### 9.1 Authoritative SIC source — path-specific contract

There are two independently admissible SEC source paths.

#### A. SEC index-header path

If acquisition status/source is `HEADER_INDEX` / SEC `index-headers.html`:

- the SEC index-header SIC field is authoritative;
- literal containment inside a `<SEC-HEADER> ... </SEC-HEADER>` byte span is **not required**;
- `inside_sec_header = false` is expected for this rendering and is not evidence that the SIC came from filing body text.

#### B. Filing-document path

If the SIC is extracted from the filing document:

- it is admissible only when found inside the canonical `<SEC-HEADER> ... </SEC-HEADER>` region;
- SIC found in filing body text, exhibits, or other bytes outside that region is diagnostic only.

Not admissible on either path:

- inferred SIC;
- restated sector labels;
- body/exhibit SIC used as a substitute for authoritative header SIC.

### 9.2 Observation states

At minimum:

```text
HEADER_INDEX_SIC
HEADER_TERMINATED_SIC
NO_HEADER_SIC
FILING_BODY_SIC_DIAGNOSTIC
ACQUISITION_FAILURE
EFFECTIVE_DATE_CONFLICT
```

`FILING_BODY_SIC_DIAGNOSTIC` applies only to a filing-document/body/exhibit occurrence outside the canonical SEC-header region. It does **not** describe an admissible SEC index-header SIC merely because the rendering's `inside_sec_header` flag is false.

Acquisition failure must never be converted into `NO_HEADER_SIC`.

### 9.3 F-6 correction carried into V3.1

The V3 F-6 statement "SIC found outside the SEC header block" was a flag-semantics misdescription.

Observed V3 cross-tab:

```text
HEADER_TERMINATED + inside_header=True  + SIC    41,458
HEADER_INDEX      + inside_header=False + SIC    33,914
HEADER_TERMINATED + inside_header=False + NO_SIC  1,449
```

No observed V3 classification decision sourced SIC from filing body/exhibit text.

Therefore:

- F-6 requires **no classification-repair work** in V3.1;
- the implementation task is to encode the source-path distinction so the flag cannot be misinterpreted;
- V3's 33,914 index-header SIC observations remain admissible.

### 9.4 Effective-dated segment construction

Within each CIK:

- order admissible SIC observations by accepted filing timestamp;
- apply the frozen segment-construction rule;
- repeated same SIC extends state;
- changed SIC starts a new segment;
- same-effective-time contradictory SIC fails closed;
- no smoothing, voting, or “plausibility” override.

Observed oscillations such as PEG/EXC `4931 <-> 4911` remain source history if they survive the authoritative source-path rule.

## 10. Frozen SIC-to-sector taxonomy

Carry forward the exact countersigned mapping for V3.1 under O-6.

Rules:

- exact `sic_mapping` identity pinned;
- `excluded_low` remains unresolved for coverage;
- no remapping because V3 showed which SICs cost the gate;
- no default sector;
- Phase-2B fail-closed behavior only;
- Phase-2A silent-MATERIALS path prohibited.

**Final decision O-6 — RATIFIED:** reuse the exact countersigned mapping and exact `excluded_low` treatment unchanged.

---

## 11. Gate 6 — terminal acquisition/classification integrity

Before any V3.1 coverage token may be spent:

### 11.1 Completion

Conjunctive:

```text
terminal_count == expected
AND unique_terminal_ciks == expected
AND terminal_sequence == frozen_acquisition_order
AND no unresolved acquisition hard-stop
```

### 11.2 Evidence reconstruction

For every parser decision:

- manifest record parseable;
- retained artifact exists;
- artifact digest matches the record;
- no mutable-path overwrite;
- source/encoding/range status reconstructable;
- parser body equals retained decision bytes where specified;
- acquisition status and parser result consistent.

### 11.3 Lineage projection integrity

Before coverage:

- every PIT trading identity/week maps to at most one effective CIK;
- zero lineage overlaps;
- gaps explicitly unresolved;
- no ticker join;
- segment filename metadata never acts as denominator key.

### 11.4 Terminal report

Produce, hash, remote-custody and fresh-fetch verify the terminal integrity report.

Only after this checkpoint and all prior Gate-0a/Gate-0b obligations are closed may the owner authorize the new coverage token.

---

## 12. Gate 7 — new coverage freeze and adjudication

### 12.1 New token required

V3 token `5b26ffa2...` is spent.

V3.1 requires a new, separately hashed coverage-freeze artifact created before the measurement.

### 12.2 Frozen rules

Carry forward unchanged:

```text
theta_name   = 0.95
theta_window = 0.95
theta_span_min = 20 years
slot denominator = PIT-200 trading identities
classification join = trading identity -> effective CIK -> SIC segment -> frozen mapping
original period first
earliest coverage-qualified start only
no interior excision
five deterministic windows
```

### 12.3 Decision outcomes

- `PASS_ORIGINAL_PERIOD`
- `PASS_REFROZEN_PERIOD`
- `STOP_INSUFFICIENT_CLASSIFICATION_HISTORY`
- `STOP_WINDOW_COVERAGE`
- `STOP_LINEAGE_OR_CLASSIFICATION_INTEGRITY`

No economics are computed in any STOP state.

---

## 13. Gate 8 — economic V3.1-RC trial

Only after coverage PASS.

### 13.1 Common governed basis

Run on the same:

- corrected TRUE_TRADED_DOLLAR PIT universe;
- governed calendar;
- admissible historical span;
- effective-dated sector classification;
- cost model.

### 13.2 Required runs

1. corrected V2 structural reference;
2. SEC-001 V3.1-RC candidate.

### 13.3 Frozen economic gates

Final carry-forward:

- absolute Sharpe `>= 0.75`
- at least `4/5` positive net-return windows
- 10 bps base and 25 bps stress treatment
- no threshold changes after observing results

Any additional relative-performance gate requires prospective owner approval before the run.

---

## 14. Runtime boundary

No runtime implementation is authorized by this design.

If V3.1 receives research GO:

- create a **new** SEC-001 V3.1 strategy record/version;
- do not reactivate retired strategy 7;
- Account 5 may be considered only under the separate runtime activation gate;
- paper transition/rebalance requires its own deployment proof.

If V3.1 STOPs:

- no SEC-001 runtime is built.

---

## 15. Implementation work packages

### WP0A — frozen-class satisfiability
**First executable work package; requires explicit owner authorization**

Inputs: existing sealed V3 artifacts only.

Deliverables:

- pinned governed 1,247-slot list;
- pinned PIT-200 membership;
- exact O-6 mapping identity;
- lineage-stability mask for every cell counted as permanently unresolved;
- frozen-class optimistic weekly ceiling grid;
- five-window / span satisfiability adjudication;
- `G0A PASS / HOLD / STOP` record;
- exact known-answer fixture proving shared grid machinery reproduces V3 `425 / 1,247` and `92.801%` on the sealed V3 inputs.

Hard stop: G0A STOP ends V3.1. No WP0B or later work.

### WP0B — FPI source-availability / satisfiability
**Authorized only after G0A PASS and a new owner checkpoint**

Deliverables:

- frozen provisional `V3_REACHABLE_FPI_CIK_POPULATION_PROVISIONAL`;
- source inventory / archive-path proof;
- earliest electronic filing-existence census;
- optimistic per-week FPI satisfiability grid;
- `G0B PASS / HOLD / STOP` record.

Hard stop: G0B STOP ends V3.1.

### WP1 — effective-dated registrant lineage

Deliverables:

- lineage source inventory;
- resolver;
- evidence records;
- conflict/gap census;
- frozen lineage artifact;
- **FPI re-entry census**: any newly discovered FPI registrant episode or status change capable of adding source-unavailable cells triggers mandatory G0B re-adjudication before WP2.

### WP2 — successor population, order and capacity envelope

Deliverables:

- new acquisition CIK union;
- deterministic order;
- source manifest;
- negative-control tests;
- projected acquisition envelope from the frozen population:
  - expected CIK count;
  - expected filing/index request count;
  - expected retry allowance;
  - expected consumed/retained bytes;
  - expected evidence-volume footprint;
  - expected wall-clock envelope under the frozen fair-access rate;
  - required disk/free-space floor and S3 custody capacity.

Use V3's observed `1,146 CIKs / 122,127 requests / ~7.6 h / 1.56 GiB retained` only as calibration evidence, not as a bound.

**Capacity gate:** WP4 may not launch until the projected envelope fits the provisioned host/storage with an explicit safety margin and custody plan.

### WP3 — state-seeding acquisition

Deliverables:

- pre-period source-seeding implementation;
- no-later-filing fallback;
- source-unavailable state;
- archive-floor enforcement.

### WP4 — acquisition/custody successor

Deliverables:

- CIK-centric crawler;
- bounded-stream ignored-Range handling;
- collision-safe immutable evidence identity;
- Defect E/F/G regression suite.

### WP5 — classification segments

Deliverables:

- path-specific header/index-header SIC contract;
- effective-dated CIK segments;
- filing-body diagnostic separation;
- conflict tests.

### WP6 — terminal integrity

Deliverables:

- completion/order proof;
- byte reconstruction proof;
- lineage projection proof;
- sealed terminal report.

### WP7 — coverage

Deliverables:

- new coverage-freeze artifact/token;
- governed weekly-grid measurement;
- PASS/STOP adjudication.

### WP8 — economics

Only on WP7 PASS.

## 16. Required negative and positive controls

The successor must not rely only on green-path tests.

### 16.1 Negative controls

1. current CIK retrojected into predecessor period -> FAIL
2. ticker-equality lineage fallback -> FAIL
3. overlapping CIK episodes -> FAIL
4. shared CIK acquired twice under ticker identity -> FAIL
5. artifact-path collision overwrite -> FAIL
6. ignored Range `200` read beyond byte ceiling -> FAIL
7. gzip fragment reaches parser -> FAIL
8. **filing-document body/exhibit SIC outside literal `<SEC-HEADER>` used as authoritative -> FAIL**
9. `excluded_low` treated as resolved -> FAIL
10. missing pre-period SIC replaced with first later filing -> FAIL
11. coverage run with unpinned input -> FAIL
12. reuse of V3 token `5b26ffa2...` -> FAIL
13. reuse of V3 frozen acquisition order / union as V3.1 authority -> FAIL
14. economics invoked before coverage PASS -> FAIL
15. lineage episode extended beyond its evidence bounds without authoritative boundary evidence -> FAIL
16. Gate-0b artifact containing SIC values -> FAIL
17. **coverage/Gate-0 grid driven by membership-file keys rather than the frozen governed-slot list -> FAIL**; the 133 holiday Mondays must never enter the denominator.
18. Gate-0a hard-stop count includes a lineage-disputed cell as permanently unresolved -> FAIL
19. Gate-0a or Gate-0b package imports or consumes return/P&L/economic result modules -> FAIL
20. WP4 launch without a passing WP2 capacity envelope / free-space gate -> FAIL

### 16.2 Positive controls

1. `HEADER_INDEX` observation with `inside_sec_header=false` and a valid SEC index-header SIC remains **ADMISSIBLE**.
2. Filing-document SIC inside the literal `<SEC-HEADER>` span remains admissible.
3. Shared CIK referenced by multiple trading identities is acquired exactly once and projected to each applicable registrant episode.
4. Shared grid/coverage tooling reproduces the sealed V3 known answer exactly:
   - `231,446 / 249,400 = 92.801%`
   - `425 / 1,247` qualifying governed rebalances.
5. Holiday Mondays present in the membership artifact contribute exactly zero denominator cells.

### 16.3 Return-blindness as CI invariant

Return-blindness is load-bearing and must be enforced mechanically.

Required CI guard, e.g. `check_sec001_v31_coverage_return_blind.sh`, must fail if Gate-0 or coverage packages:

- import forbidden price-performance, return, P&L or economic-evaluation modules;
- declare output schemas containing return/P&L/economic-result fields;
- join to economic-result artifacts;
- invoke the economic engine before a governed coverage PASS.

Use an explicit allowlist/dependency boundary rather than relying only on filename or keyword matching.

## 17. Hard-stop matrix

| Condition | Action |
|---|---|
| Gate-0a frozen-class optimistic ceiling cannot satisfy O-2 | STOP V3.1 before WP0B |
| Gate-0b optimistic FPI source bound cannot satisfy O-2 | STOP V3.1 before WP1 |
| lineage conflict unresolved | STOP before population freeze |
| WP1 discovers new FPI source-unavailable exposure and G0B is not re-adjudicated | STOP before WP2 |
| heuristic lineage fallback required | STOP / owner adjudication |
| acquisition population/order mismatch | STOP |
| WP2 capacity envelope/free-space gate not passed | STOP before WP4 |
| evidence overwrite/collision | STOP |
| per-response/per-record acquisition bound exceeded | STOP |
| acquisition failure converted to NO_SIC | STOP |
| outside-header SIC enters authoritative segments | STOP |
| terminal reconstruction not exact | STOP |
| coverage input unpinned | STOP |
| coverage fails | STOP / REDESIGN |
| economics started before coverage PASS | INVALID RUN |

---

## 18. Evidence / custody policy

Load-bearing artifacts must be remotely custodied before the next irreversible gate consumes them.

Minimum:

- Git commit/blob identity
- SHA-256 of non-Git data artifacts
- S3 VersionId where applicable
- fresh-fetch verification
- no sole-copy research host
- no mutable artifact path standing in for immutable evidence

Failed epochs stay preserved and are never “cleaned up” into conformance.

---

## 19. Final design decisions

All design decisions are resolved for v1.0.

| Decision | Final ruling | Governing consequence |
|---|---|---|
| O-1 — economic construction | **RATIFIED** | V3.1 carries the V3 economic hypothesis unchanged |
| O-2 — coverage thresholds | **RATIFIED** | `theta_name=0.95`, `theta_window=0.95`, `theta_span_min=20y`; no post-failure retuning |
| O-3 — historical forms | **RATIFIED** | no alias/form expansion by convenience; Gate-0 necessity only, then freeze prospectively |
| O-4 — acquisition order | **A** | `(min_effective_date, numeric_cik)` |
| O-5 — pre-period state seeding | **A** | evidence-bounded latest admissible pre-start SIC; no fixed warm-up |
| O-6 — SIC mapping / `excluded_low` | **RATIFIED** | exact countersigned mapping and unresolved treatment unchanged |
| O-7 — Gate-0 strength | **A — HARD GATES** | G0A frozen-class impossibility stops before FPI work; G0B FPI-source impossibility stops before lineage engineering |
| O-8 — successor naming | **A — SEC-001 V3.1** | point release of the same economic hypothesis with redesigned classification infrastructure |
| O-9 — episode evidence sufficiency | **RATIFIED** | inward-bounded episodes; explicit authoritative transition evidence may set an edge; otherwise unsupported edges remain gaps |

### 19.1 Design freeze consequence

Changing any O-1 through O-9 decision after WP0 evidence is observed requires a new versioned redesign/adjudication. In particular, the following may not be changed merely because Gate 0 or later coverage is unfavorable:

- economic construction;
- `theta_name`, `theta_window`, or `theta_span_min`;
- `excluded_low` treatment;
- acquisition-order semantics;
- lineage evidence standard;
- state-seeding semantics;
- Gate-0a / Gate-0b hard-stop character.

---

## 20. Owner implementation authorization

The design is final. **Final design does not itself authorize execution.**

The first recommended implementation authority is now narrower than v1.0:

```text
SEC-001 V3.1 IMPLEMENTATION AUTHORIZATION

Design: TradingWorkbench SEC-001 V3.1
        Historical Issuer-Lineage & PIT Sector Classification Redesign
Version: v1.1 FINAL

Design decisions:
[x] O-1 economics unchanged
[x] O-2 coverage standards unchanged
[x] O-3 historical-form policy
[x] O-4 acquisition order = (min_effective_date, numeric_cik)
[x] O-5 evidence-bounded pre-period state seeding
[x] O-6 SIC mapping / excluded_low unchanged
[x] O-7 Gate-0a / Gate-0b = hard satisfiability gates
[x] O-8 successor name = SEC-001 V3.1
[x] O-9 inward-bounded episode evidence standard

Recommended first authority:
[ ] WP0A ONLY — frozen-class satisfiability on existing sealed V3 artifacts

Not authorized by this approval:
[ ] WP0B FPI source-availability
[ ] WP1 lineage implementation
[ ] WP2 successor population/order/capacity freeze
[ ] WP3 state-seeding acquisition
[ ] WP4 full SEC acquisition
[ ] WP5 classification segment construction
[ ] WP6 terminal integrity
[ ] WP7 coverage spend
[ ] WP8 economics
[ ] runtime implementation

Owner:
Authorization date/time:
Approval/custody record identity:
```

WP0A authority, if granted, ends at a **G0A PASS / HOLD / STOP owner checkpoint**. A G0A PASS does not automatically authorize WP0B.

## 21. First execution sequence after explicit WP0A authorization

WP0A is a return-blind satisfiability proof over existing sealed artifacts. It performs no SEC acquisition and no lineage expansion.

Execution sequence:

1. Pin the exact 1,247 governed-slot artifact and prove holiday Mondays are excluded.
2. Pin PIT-200 membership and the exact O-6 SIC mapping.
3. Build a **lineage-stability mask** for candidate permanently-unresolved cells; disputed cells default to resolved.
4. Mark the admissible Gate-0a permanently-unresolved classes (`excluded_low` and other already-frozen/source-empty cases that pass the stability test).
5. Compute per-governed-week unresolved counts and the optimistic `theta_name` pass ceiling.
6. Apply the frozen five-window / fixed-end / `theta_window` / `theta_span_min` satisfiability logic without exposing or joining returns.
7. Run the exact V3 known-answer fixture (`92.801%`, `425/1,247`) against the shared grid machinery.
8. Produce exactly one adjudication:
   - `G0A_PASS_FROZEN_CLASSES_SATISFIABLE`
   - `G0A_HOLD_INPUT_STABILITY_UNRESOLVED`
   - `G0A_STOP_FROZEN_CLASSES_FORECLOSE_COVERAGE`
9. Hash, remote-custody and fresh-fetch verify the Gate-0a artifacts and record.
10. **STOP at the owner checkpoint.**

If G0A STOPs, do not run the FPI investigation. If the program is to continue, it requires a new versioned redesign/adjudication; O-2 or O-6 may not be changed inside V3.1.

## 22. v1.1 final disposition

**FINAL DESIGN. Supersedes v1.0. No implementation has been authorized by this document alone.**

The governed path is:

```text
V3-RC STOP preserved
  ->
explicit owner authorization for WP0A
  ->
Gate 0a: frozen-class satisfiability
  -> STOP: end V3.1
  -> HOLD: bounded evidence task; default STOP if unresolved
  -> PASS: owner checkpoint
       ->
       separate WP0B authority
       ->
Gate 0b: provisional FPI source satisfiability
  -> STOP: end V3.1
  -> HOLD: bounded evidence task; default STOP if unresolved
  -> PASS: owner checkpoint
       ->
       separate WP1 authority
       ->
effective-dated registrant lineage
  ->
FPI re-entry check / re-adjudicate G0B if lineage expands FPI exposure
  ->
new CIK acquisition population/order + capacity envelope
  ->
pre-period state seeding
  ->
bounded immutable CIK-once SEC acquisition
  ->
path-specific index-header / filing-header SIC segments
  ->
terminal integrity/custody
  ->
NEW coverage freeze/token
  ->
coverage PASS?
  -> NO: STOP
  -> YES: corrected V2 reference + V3.1-RC economics
```

The successor earns the right to spend engineering and acquisition effort only after each earlier satisfiability gate proves that later success is still possible under the already-frozen rules.

**Immediate next owner decision:** authorize **WP0A only**, or stop V3.1 before implementation.
