# TradingWorkbench SEC-001 V3.1 — Historical Issuer-Lineage & PIT Sector Classification Redesign
## Design / Implementation Plan v1.4 — FINAL DESIGN

**Status:** FINAL DESIGN + **WP0A AUTHORIZED** (owner, 2026-08-26; see §23) — supersedes v1.3; owner implementation authorization required before Gate 0a / WP0A execution  
**Program:** SEC-001  
**Candidate:** SEC-001 V3.1-RC (new successor candidate; V3-RC is STOP / REDESIGN and is not resumed)  
**Date:** 2026-08-26  
**Design decisions:** **O-1 through O-9 resolved in §19**  
**Implementation authority:** **WP0A ONLY — AUTHORIZED 2026-08-26**, inclusive of the bounded WP0A-Q substep. Everything later remains unauthorized. See §23.  
**Economic authority:** **NONE until the new classification-coverage gate passes**  
**Runtime authority:** **NONE until research GO and separate runtime gates pass**

**v1.4 finalization (2026-08-26):** records the owner's **WP0A-ONLY authorization** and its exact
bounded scope (§23), and folds in the first two authorized WP0A results.
**(a)** The §1 candidate population was **re-derived deterministically** rather than adopting v1.3's
list: 23 candidates confirmed, but the decisive-proof count is **K = 16, not 13** — v1.3's 13 was
computed for a single terminal-window length, and the tightest admissible window (the 20-year span's
189-week terminal) needs 16. §4.1.2a-3 is corrected.
**(b)** A survey of every sealed and local artifact establishes that **no qualifying
`SECURITY_CIK_BINDING` source exists anywhere in current custody** (§23.4). WP0A-Q therefore cannot
complete under present authority: it requires a bounded new SEC acquisition, which is **not** covered by
the WP0A authorization. That is the open owner decision; nothing further was executed.

**v1.3 finalization (2026-08-26):** closes the P0 the owner identified in v1.2 and three smaller
items. **(P0)** §4.1.2a's stability test proved *registrant* continuity — that the CIK filed before and
after the week — and then claimed *security→registrant* continuity in its derivation. Those are
different claims, and conflating them is the V3 failure mode. `LINEAGE_STABLE` now additionally
requires an **effective-dated security→CIK binding covering the week** from an O-9-approved source,
plus the absence of a competing binding. **A check of the sealed V3 artifacts establishes that no
qualifying binding exists today** (§4.1.2a-2), so a bounded **WP0A-Q** substep is added to obtain it
for the ranked binding set only — measured at **23 identities, minimum sufficient subset 13**.
**(P1)** O-3's alias universe is frozen as `G0_FORM_ALIAS_CANDIDATES_V1 = {10-K405}` so the claim that
alias uncertainty cannot reach 2018–2025 is mechanically true rather than assumed. **(P1)** Zero-filing
identities now default to DISPUTED/optimistic in Gate 0a and defer to Gate 0b, since WP0A precedes the
source-availability work that §4.1.2b required. **(P1)** §4.1.2d's undefined "material share" is
replaced by a **deterministic two-sided sensitivity test**. §4.1.6 also now precommits the methodology
any taxonomy successor must use.

**v1.2 finalization (2026-08-26):** incorporates the post-v1.1 review, which tested the new
lineage-stability condition rather than assuming it. Five changes are load-bearing.
**(1)** §4.1.2's optimistic "could change under later lawful evidence" clause is replaced by a
**closed, enumerated list of change channels** — read literally the open-ended form credited every
cell as resolved and made Gate 0a vacuous.
**(2)** §4.1.2 now carries an **operational lineage-stability test** derivable from sealed V3
artifacts, with its derivation from O-9 inward bounding and the no-overlap rule; without it WP0A had
no executable definition of "lineage-stable" and depended circularly on WP1.
**(3)** Gate 0b is corrected to **accumulate monotonically**: v1.1 §4.2.5 credited `excluded_low` as
resolved, re-introducing the exact v1.0 error one gate downstream, so that neither gate ever tested
the joint constraint θ_name actually is. Gate 0a now emits a per-week **residual budget** that Gate 0b
consumes.
**(4)** §4.1.3 states the **structural mechanism** of the stop — the fixed 2026-06-12 end date makes
the terminal window unavoidable — so the adjudication reads as a proof rather than a number.
**(5)** Gate 0a must emit a **distance-to-feasibility**, so a STOP hands a successor a specification
instead of a dead end.
Also added: a zero-filing-identity branch in the stability test, the sealed fixture Version IDs for
positive control 4, the §1.4 binding-versus-largest-constraint finding, and the HOLD/optimistic-credit
precedence rule.

**v1.1 finalization (2026-08-26):** incorporates the post-v1.0 review. A new **Gate 0a / WP0A frozen-class satisfiability gate** now precedes the FPI source gate: every class permanently unresolved by already-ratified rules (especially `excluded_low`, plus lineage-stable zero-filing cases) remains unresolved and every disputed/repairable cell is treated optimistically as resolved. Gate 0a is computed from existing sealed V3 artifacts, is return-blind, and hard-stops V3.1 if even that ceiling cannot satisfy O-2. The existing FPI gate becomes **Gate 0b / WP0B**. The source contract now explicitly treats SEC `index-headers.html` SIC as admissible even when `inside_sec_header=false`; literal `<SEC-HEADER>` containment is required only on the filing-document path. F-6 is reclassified as a labeling/flag-semantics issue, not an observed body-text-SIC defect. Added Gate-0b lineage re-entry, governed-slot denominator control, exact V3 known-answer fixture, pre-WP4 capacity envelope, return-blind CI enforcement, and clarification that CIK-once acquisition structurally prevents the V3 shared-CIK collision while immutable artifact keys remain defense-in-depth.

**Diagnostic evidence motivating Gate 0a (not itself the governed Gate-0a adjudication):** on the
sealed V3 corpus, `excluded_low` alone exceeds the ten-name weekly unresolved budget in 193/1,247
governed weeks (15.48%); the last four years reach only a 71.579% weekly-pass ceiling against
`theta_window = 95%`.

**The v1.1 lineage-stability condition has now been applied to those diagnostics and does not blunt
them.** Under the strict-interiority test of §4.1.2 — which credits both edges of every filing span as
disputed — **4,750 of 5,224 `excluded_low` cells (90.9%) remain lineage-stable**, 158 of 1,247 weeks
still breach the ten-name budget on the stable subset alone (12.67%), and the terminal-window ceiling
is 82.105% at four years, 76.056% at three and 75.949% at five, against a required 95%. The condition
therefore does what it was added to do — it prevents the broken V3 identity model from proving V3.1
impossible — **without making Gate 0a unable to stop anything.** These remain motivation and
regression evidence, not the governed adjudication.

---

## 0. Executive decision

SEC-001 V3-RC failed its frozen classification-coverage gate before economics were run.

The successor must **not** repair the failed epoch in place, retune thresholds, relax `excluded_low`, move the start date for convenience, or reuse the spent coverage token.

The redesign keeps the economic strategy unchanged and replaces the historical issuer/classification infrastructure with an explicit three-layer model:

1. **Trading identity** — permanent security identity / permaticker used by the PIT-200 portfolio population.
2. **Registrant episode** — effective-dated `(permaticker, CIK, valid_from, valid_to)` lineage.
3. **Acquisition identity** — unique SEC CIKs that must be crawled to support those registrant episodes, including predecessor CIKs and any prospectively approved pre-period state-seeding scope.

The first gate is not implementation. It is **Gate 0a — frozen-class satisfiability** using existing sealed, return-blind V3 artifacts. Gate 0a holds every class that is permanently unresolved under already-ratified V3.1 rules unresolved, treats every disputed or potentially repairable cell optimistically as resolved, and asks whether O-2 is satisfiable in principle.

Only if Gate 0a passes does V3.1 proceed to **Gate 0b — FPI source-availability / satisfiability**,
which **accumulates** Gate 0a's permanently-unresolved classes rather than re-crediting them. If either
gate proves the frozen coverage requirements impossible, V3.1 stops before lineage engineering or a new
large crawl.

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

### 1.4 The largest cause is not the binding constraint *(added v1.2)*

§1.2 ranks causes by cell count. Feasibility is decided by a different question — which cause exhausts
the ten-name weekly budget — and the two answers differ.

- **Largest cause:** successor-CIK lineage, 10,800 cells (60.2%). Repairing it perfectly still leaves
  the terminal four-year window at roughly an 82% weekly-pass ceiling against `theta_window = 95%`.
- **Binding cause:** `excluded_low`, 5,224 cells (29.1%), concentrated in 2018–2025 and driven by a
  small set of modern large-caps — DHR (813 cells), TMO (504), NOC (349), GOOG / GOOGL / META (343
  each), TTD (235), BIDU (235), SNAP (214). These are not re-registered issuers; their current CIK is
  already the evidence-supported registrant, so **lineage repair does not reduce this class at all**.

The consequence for sequencing is deliberate and must not be lost: **WP1–WP4 (lineage engineering plus
a full re-acquisition) address the largest cause, not the binding one.** That is precisely why Gate 0a
runs first and costs almost nothing. The lineage defect is real and worth fixing on its own merits, but
it should not be the first investment if a frozen taxonomy class already forecloses the candidate.

⛔ This finding is **not** a licence to reopen O-6. It is a statement about *ordering of expenditure*.
If Gate 0a stops V3.1, §4.1.6 governs what a legitimate successor looks like.

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

Count as unresolved only cells that are proven non-recoverable under the final design **without relying
on the V3 current-CIK defect**.

At minimum:

- `excluded_low` mapping outcomes under the exact O-6 mapping, **only where the registrant identity for
  that week is lineage-stable** by the test in §4.1.2a;
- zero-in-window-filing identities that satisfy §4.1.2b;
- any other class explicitly frozen by O-1 through O-9 as permanently unresolved.

##### 4.1.2a Operational lineage-stability test *(added v1.2 — this was previously undefined)*

v1.1 required cells to be proven "lineage-stable" but gave no executable definition, and WP0A runs
**before** WP1 builds lineage. Left unresolved that is circular: a strict reading proves nothing stable
and Gate 0a passes vacuously; a loose reading is unreviewable judgement. The following test closes it
using **sealed V3 artifacts only**.

⛔⛔ **v1.2 defect, corrected here.** v1.2 defined stability as "the assigned CIK filed before and
after the week" and then derived from it that those observations *tie the CIK to the security*. **Those
are different claims.** A registrant can file continuously across a date without that proving the
particular permanent security belonged to it throughout — a merger, acquisition, reverse merger,
security transfer or share-class change can make `CIK filed at t−1 and t+1` true while
`permaticker → that CIK at t` is false. Inferring the security relationship from registrant activity is
the **same error class that killed V3-RC**, and it may not be used to justify a hard stop.

##### 4.1.2a-1 The corrected definition

```text
LINEAGE_STABLE(cell) =
        CIK_FILING_SPAN_BRACKETS_WEEK
    AND SECURITY_CIK_BINDING_COVERS_WEEK
    AND NO_COMPETING_SECURITY_CIK_BINDING
```

- **`CIK_FILING_SPAN_BRACKETS_WEEK`** — the assigned CIK has an admissible filing observation with
  accepted timestamp strictly before the week's close-t cutoff and at least one strictly after it.
  *Necessary, not sufficient.*
- **`SECURITY_CIK_BINDING_COVERS_WEEK`** — an **O-9-approved** effective-dated security→registrant
  record independently covers that week: a pinned vendor effective-dated permanent-identity/CIK history;
  or authoritative transition / succession / re-registration evidence establishing the boundary; or
  another previously governed security→registrant evidence record.
  ⛔ **Current CIK assignment is not sufficient. CIK filing existence is not sufficient.**
- **`NO_COMPETING_SECURITY_CIK_BINDING`** — no other admissible binding covers the same week for that
  identity.

Any cell failing any conjunct is **DISPUTED** and receives optimistic credit. This will reduce the
stable subset, and that is the intended direction: **a Gate-0a STOP must survive the most generous
defensible treatment.**

What survives from v1.2's derivation is only the *first* conjunct's justification — inward bounding
cannot shrink away a week interior to an episode's own evidence bounds, no overlapping episode may
claim it, predecessor discovery adds only earlier episodes, and state seeding adds only earlier
observations. That argument bounds what lineage can do to an **already-established** binding. It does
not establish the binding.

##### 4.1.2a-2 Availability of the binding in sealed artifacts — **checked, and it is absent**

The sealed V3 artifacts were examined for a qualifying `SECURITY_CIK_BINDING`. **None qualifies.**

- The **V3 CIK-resolution artifact** self-describes as "governed snapshot-resolved CIK identity — NOT
  an effective-dated CIK history". Disqualified by its own provenance statement.
- The **MR-002 `crosswalk`** (`permaticker, cik, effective_from, effective_to`) is effective-dated in
  *form* but is substantively the current-CIK model with ticker-interval dates attached:

```text
crosswalk rows 1,068 over 754 permatickers    source: sharadar_tickers.secfilings
permatickers carrying >1 distinct CIK:  2 of 754   (both Alphabet: 1288776 -> 1652044)
V3.1 trading identities with any crosswalk row:   652 of 1,167
V3.1 trading identities with NO crosswalk row:    515 of 1,167
re-registered issuers that drove the V3 lineage gap, as the crosswalk sees them:
  DIS [1744489] · ORCL [1341439] · MDT [1613103] · CI [1739940] · APA [1841666]
  ESRX [1532063] · BLK [2012383] · AVGO [1730168] · ICE [1571949] · WBA [1618921] · MRVL [1835632]
  -- in every case the CURRENT CIK only, with no predecessor episode
```

⛔ **The crosswalk is therefore explicitly disqualified as a `SECURITY_CIK_BINDING` source for Gate
0a.** Admitting it would re-assert the current-CIK model under a new name, which is exactly what V3.1
exists to eliminate. It may be used as corroborating context and as an input to WP1; it may not
establish a binding for a hard-stop count.

**Consequence, stated plainly:** with no qualifying binding available, **no cell can be proven
`LINEAGE_STABLE` from sealed artifacts alone**, every cell receives optimistic credit, and Gate 0a as
specified would return `G0A_HOLD` under §4.1.2d — optimistic PASS, pessimistic STOP. That is an honest
outcome, but it defers the decision to WP1, which is the expenditure §1.4 argues against. §4.1.2a-3
resolves this with a bounded substep rather than by weakening the test.

##### 4.1.2a-3 WP0A-Q — bounded security→CIK binding qualification *(added v1.3)*

⛔ Do **not** launch WP1 to answer this. WP0A-Q is a **strictly bounded pre-engineering substep** that
establishes `SECURITY_CIK_BINDING` **only for the identities proposed to count against the Gate-0a
ceiling**, in descending order of their contribution to the binding window, stopping as soon as the
ceiling's verdict is determined.

Measured scope, from the sealed V3 corpus:

```text
binding window (terminal, per 4.1.3a)   190 rebalances, 2022-05-09 .. 2026-06-08
identities contributing ANY excluded_low cell there                      23
identities contributing over the whole 26-year grid                      42
terminal-window excluded_low cells                                    1,731
theta_window fails once  >9 of 190 weeks exceed the ten-name budget
weeks currently over budget                                              54 of 190

MINIMUM SUFFICIENT PROOF SET  K = 13 identities   [SUPERSEDED -- see below]
  GOOGL, GOOG, META, TMO, DHR, NOC, APP, TTD, TT, SNAP, BIDU, NBIS, ASTS
  (the first five are in the PIT-200 and excluded_low in ALL 190 weeks)
```

⛔ **Corrected in v1.4 by the authorized §1 re-derivation.** The K = 13 figure was computed for **one**
terminal-window length. Admissible spans run 20 y … 26.4 y, so admissible terminal windows run 189 …
249 rebalances, and the *tightest* is the 20-year span's 189-week window (max 9 failing weeks). Across
all of them the worst case is **K = 16**. See §23.3 for the derived candidate set, the deterministic
review order, and the per-window thresholds. **Scope WP0A-Q to K = 16 as the working expectation and
23 as the hard bound.**

Proving the binding for those **13 identities over 2022–2026** is sufficient to determine the Gate-0a
verdict. If any of the 13 fails to qualify, extend down the ranked list toward the bound of 23; if the
full 23 cannot carry the window past the failing threshold, Gate 0a does not STOP and returns
`G0A_HOLD` or `G0A_PASS` on the §4.1.2d rule.

⚠ The ranked list is derived from V3's SIC assignments; WP0A-Q must re-derive it from its own pinned
inputs rather than adopting these names on trust. They are stated so the substep can be scoped and
budgeted, not so it can skip the derivation.

**Implementation notes.** Use exact accepted timestamps, not year granularity — the diagnostics in
§4.1.5 are year-granular and are not the governed test. Record the mask and the binding evidence
reference per cell so the adjudication is reproducible and reviewable.

##### 4.1.2b Zero-filing identities *(added v1.2)*

An identity whose CIK has **no** in-window filing has an empty filing span, so §4.1.2a's bracketing
test cannot classify it and would silently credit it as resolved.

⚠ **v1.2 required a proof WP0A cannot perform.** Counting such a cell as permanently unresolved needs
(i) no admissible filing anywhere in the governed source boundary and (ii) no possible pre-period seed —
both of which are **source-availability** facts, and WP0A precedes the source-availability work.

**Rule (v1.3):** zero-filing identities are **DISPUTED and optimistically resolved in Gate 0a**, and
they carry forward to Gate 0b, **unless** pre-existing sealed evidence independently proves source
exhaustiveness and the impossibility of a seed. `GX` and `FRCB` are the known V3 instances at **60 cells
total** — there is no reason to weaken Gate-0a purity to capture them.

##### 4.1.2c Optimistic credit — closed list of change channels *(replaces the v1.1 open-ended clause)*

v1.1 credited as resolved "a classification observation that could change under later lawful evidence."
Read literally **every** observation could change under later lawful evidence, which credits every cell
as resolved and makes Gate 0a vacuous. The clause is replaced by a **closed enumeration**. A cell is
DISPUTED, and therefore credited as resolved, if and only if one of the following named channels could
change its outcome:

1. **lineage reassignment** — the cell fails the §4.1.2a interiority test;
2. **pre-period state seeding** (§7) — the week precedes the CIK's first observed admissible filing;
3. **historical form-alias admission under O-3**, bounded by the frozen candidate universe of
   §4.1.2c-1 — an alias admitted by Gate 0b necessity could insert an admissible observation at or before
   the week and change the governing segment;
4. **source availability** — the cell's evidence depends on a source class whose archive boundary is
   not yet established;
5. **FPI source availability** — deferred to Gate 0b (and thereafter accumulated, not re-credited).

No other ground credits a cell as resolved. Adding a channel to this list is a design change requiring a
new version, not an implementation choice.

⚠ Channel 3 is the only one that can affect an **interior** week. Its confinement to pre-2003 is made
mechanically true by §4.1.2c-1 rather than assumed.

##### 4.1.2c-1 Frozen Gate-0 form-alias candidate universe *(added v1.3)*

v1.2 asserted that alias-related instability is confined to pre-2003 because of 10-K405, while O-3
permits *any* historical alias later shown necessary. **The second does not imply the first.** The gap
is closed by freezing the candidate universe **before WP0A**:

```text
G0_FORM_ALIAS_CANDIDATES_V1 = { 10-K405 }
```

- The set is frozen on present evidence: 10-K405 is the only omitted form for which an evidence-based
  case currently exists (the 10-K count steps from 395/427/476 to 668 exactly at its retirement, with
  10-Q acquisition already complete across those years).
- Every Gate-0a and Gate-0b adjudication records the alias universe it was computed under.
- ⛔ **Any later proposal to admit a form outside the frozen set invalidates the applicable Gate-0a /
  Gate-0b adjudication and requires re-entry before lineage or acquisition proceeds.** It is not an
  implementation choice and may not be made during WP1–WP4.

With the universe frozen, the statement that alias uncertainty cannot reach the 2018–2025 binding
region follows mechanically: every member of the set was retired before 2003.

##### 4.1.2d Precedence between optimistic credit and HOLD *(added v1.2)*

§4.1.2c credits an unprovable cell as resolved (tending toward PASS); §4.1.4 offers HOLD for unproven
stability (tending toward STOP). These point in opposite directions for the same input.

⚠ **v1.2 resolved this with an undefined "material share", which put operator judgement inside a hard
gate.** v1.3 replaces it with a **deterministic two-sided sensitivity test**. No threshold, no
materiality call:

```text
1. OPTIMISTIC case  — every DISPUTED cell counted as RESOLVED.
2. If OPTIMISTIC STOPs                      -> STOP.
      (optimistic credit was already granted; no further evidence can rescue it)
3. Else compute PESSIMISTIC case — every DISPUTED / unproven cell counted as UNRESOLVED.
4. If OPTIMISTIC PASS and PESSIMISTIC PASS  -> PASS.
      (the verdict does not depend on the unproven cells at all)
5. If OPTIMISTIC PASS and PESSIMISTIC STOP  -> HOLD,
      naming the exact disputed cells and the evidence required to decide between them.
```

This eliminates the arbitrary materiality threshold completely and makes the HOLD condition a
computed property of the grid rather than an assessment of it.

This makes Gate 0a a true optimistic ceiling. It may miss a future failure; it may not manufacture one.

#### 4.1.3 Gate-0a governed grid

The denominator is driven exclusively by the frozen **1,247 governed research slots**, not by keys present in `pit200_membership_v2.json`.

The membership artifact contains 1,380 Monday keys: 1,247 governed slots plus 133 holiday Mondays. Holiday keys are not rebalances and never enter the coverage denominator.

For each governed slot:

1. obtain the exact 200 trading identities from the pinned PIT-200 membership;
2. count only Gate-0a-proven permanently unresolved identities;
3. compute `resolved_ceiling = 200 - permanently_unresolved_count`;
4. apply `theta_name >= 190/200`;
5. roll qualifying weeks into the frozen five-window / `theta_window` / `theta_span_min` rules;
6. emit the per-week **residual budget** `10 - permanently_unresolved_count`, which Gate 0b consumes
   under §4.2.5 rather than re-deriving.

No averages decide the gate.

##### 4.1.3a Why the terminal window is unavoidable *(added v1.2 — the mechanism, not just the number)*

The adjudication must be readable as a proof. The structural reason a frozen-class failure cannot be
escaped by moving the start date is:

- the coverage freeze **fixes the span end at 2026-06-12** and permits the start to move **forward
  only**, with no interior excision;
- `theta_span_min = 20 years` over five deterministic windows makes the **terminal window at least four
  years long**;
- the terminal window therefore always ends in, and mostly consists of, the most recent years — which
  is exactly where the `excluded_low` burden is heaviest (mean ~11 names/week in 2019–2021 and 2025
  against a ten-name budget);
- `theta_window` allows only 5% failing rebalances **within each window**, so a terminal window running
  far below that ceiling cannot be averaged away by earlier, healthier windows.

⇒ **No admissible start date escapes the terminal window.** A Gate-0a STOP is therefore structural, not
an artifact of where the span begins.

#### 4.1.4 Gate-0a decision

- **G0A PASS — FROZEN CLASSES SATISFIABLE**: at least one admissible >=20-year span remains mathematically satisfiable under the optimistic frozen-class ceiling.
- **G0A STOP — FROZEN CLASSES FORECLOSE COVERAGE**: no admissible span can satisfy O-2 even under the optimistic ceiling.
- **G0A HOLD — INPUT STABILITY UNRESOLVED**: the ceiling passes, but only because a material share of
  cells were credited without proof (see §4.1.2d — HOLD is not available for a ceiling that STOPs).
  HOLD must name the exact evidence needed, state the credited-without-proof share, and defaults to
  STOP if the bounded evidence task expires unresolved.

A G0A STOP ends V3.1. **WP0B, WP1, acquisition, a new coverage token, and economics are not authorized.**

##### 4.1.4a Distance to feasibility — required in every outcome *(added v1.2)*

A bare STOP hands a successor nothing, and §4.1.6 contemplates exactly such a successor. Gate 0a must
therefore report, in all three outcomes, **what would have to be true for the candidate to become
feasible**:

- the **binding window** and its measured weekly-pass fraction against `theta_window`;
- the **binding class or classes** and their per-week contribution inside that window;
- the **reduction required** — the maximum permanently-unresolved count per week that would satisfy
  `theta_name` in at least 95% of that window's rebalances, and the shortfall from the observed count;
- which named change channels of §4.1.2c could, in principle, deliver that reduction, and which
  provably cannot.

This converts a STOP from a dead end into a specification. ⛔ It is a description of the constraint, not
a proposal to relax it; producing it may not be used to argue for changing O-2 or O-6 inside V3.1.

#### 4.1.5 Diagnostic V3 evidence

The post-v1.0 review measured the following on the sealed V3 corpus:

```text
ALL excluded_low cells (v1.1 basis)
  names/week: mean 4.19, median 2, p90 11, max 14
  weeks excluded_low alone > 10 names: 193 / 1,247 = 15.48%
  terminal 4-year weekly-pass ceiling: 71.579%

LINEAGE-STABLE subset under the 4.1.2a test (v1.2 basis, year-granular, both edges credited)
  stable cells retained: 4,750 / 5,224 = 90.9%
  weeks stable-excluded_low alone > 10 names: 158 / 1,247 = 12.67%
  terminal weekly-pass ceiling: 3y 76.056%  4y 82.105%  5y 75.949%  6y 65.965%
  whole-span ceiling: 2000 87.330%  2006-06-12 83.263%  2010 79.560%  2015 70.577%
  top stable contributors: DHR 813, TMO 504, NOC 349, GOOG/GOOGL/META 343 each,
                           TTD 235, BIDU 235, SNAP 214
```

⛔⛔ **These figures were computed under the SUPERSEDED v1.2 stability test — CIK bracketing only —
and are NOT valid under the corrected §4.1.2a-1 definition.** Under the corrected definition no cell
qualifies from sealed artifacts at all (§4.1.2a-2), so the stable subset is **zero** until WP0A-Q
supplies the security→CIK binding. They are retained because they bound what the corrected test can
find: the corrected stable set is a **subset** of the 4,750, so the corrected ceiling can only be
**higher** (more optimistic) than the figures above, never lower. ⛔ Do not cite them as the corrected
result.

Two things follow, and both matter for how WP0A is read.

**The v1.2 condition did not blunt the gate on its own terms.** It discarded ~9% of the cells —
including all of 2000 and 2026, whose CIK filing spans have no bracketing observations at the corpus
edges — and the ceiling still failed at every window length and start date tested. What it failed to do
was prove the security relationship, which is why §4.1.2a-1 now requires it separately.

**These figures remain motivation and regression evidence, not the adjudication.** They are
year-granular where §4.1.2a requires exact accepted timestamps, and they were computed on the V3
corpus. WP0A must recompute them under the governed test and its own pinned inputs.

#### 4.1.6 If Gate 0a stops — legitimate redesign boundary

A Gate-0a failure may not be answered by changing O-2 or O-6 inside V3.1.

The legitimate path is a **new versioned successor/adjudication**. If the SIC mapping or `excluded_low` classification quality is independently re-reviewed, that review must:

- be justified on classification/taxonomy quality grounds, not on coverage impact;
- use prospectively stated quality criteria;
- be performed by an evaluator isolated from the row-level coverage-impact table to the maximum practical extent;
- record any unavoidable prior knowledge/conflict explicitly;
- seal the revised mapping **before** any new satisfiability or coverage measurement;
- create a new candidate/version and new coverage ledger entry.

##### Precommitted methodology for a taxonomy successor *(added v1.3)*

We already know which taxonomy rows hurt coverage. A successor that re-reviewed *those rows* would be
tuning after failure however carefully it was worded. The methodology is therefore precommitted:

1. **Define an independent, universal SIC→sector review methodology first**, with prospectively stated
   quality criteria, and seal it before any row is examined.
2. **Apply it to the entire mapping table** — all 110 rows — not to a selected subset, and without
   coverage information of any kind available to the evaluator.
3. **Seal the complete revised mapping** before any satisfiability or coverage measurement is
   recomputed.
4. Only then recompute satisfiability, under a new candidate, a new coverage freeze and a new token.

⛔ **Selective reconsideration of `7370`, `3823`, `3812`, `3829`, `4899` or any other row known to
affect the failed gate is prohibited**, whatever the stated rationale. Universal re-review with the
losing rows unmarked is materially stronger protection than a careful individual review, because it
removes the analyst's ability to arrive at the convenient answer.

Example of what is permissible under that methodology: a universal review could independently conclude
that SIC `7370` maps to Communication Services under the intended GICS taxonomy. The fact that `7370`
materially affects the failed gate is **not** evidence for how it should map, and may not appear in the
review record as a consideration.

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

#### 4.2.5 Gate-0b optimistic satisfiability test — **monotone accumulation** *(corrected v1.2)*

⚠ **v1.1 defect, corrected here.** v1.1 specified "source-unavailable FPI cells remain unresolved;
**every other cell is resolved**". That credited `excluded_low` as resolved — the exact counterfactual
move Gate 0a was created to eliminate, re-introduced one gate downstream. Combined with §4.1.2's
"an FPI cell is treated as resolved until Gate 0b", each gate excused the other's class and **neither
ever tested the joint constraint that `theta_name` actually is.**

**The gates accumulate. They do not reset.** For each governed rebalance week the unresolved set is:

```text
unresolved(week) = Gate-0a permanently-unresolved classes for that week
                 UNION  FPI source-unavailable cells for that week
```

Operationally, Gate 0b consumes the per-week **residual budget** emitted by Gate 0a (§4.1.3 step 6) and
tests the FPI burden against that residual, not against the full ten-name allowance. Every cell outside
the accumulated set is credited as resolved. Then:

- use actual PIT-200 weekly membership;
- apply `theta_name`, then `theta_window`, then `theta_span_min`;
- use original-period-first and earliest-qualified-start only.

⭐ **Measured today this correction changes nothing numerically** — in 2000–2001, `excluded_low`
averages only 1.4–1.6 stable names per week, so the joint count breaches in the same 4 of 95 weeks that
FPI alone does. The defect is **latent, not active**. It is corrected anyway because it is the same
error class that has already cost one candidate, and because the correction is free.

⛔ The same rule binds every later gate: no gate may re-credit a class an earlier gate proved
permanently unresolved.

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
- **WP0A-Q security→CIK binding qualification** per §4.1.2a-3 for the ranked binding set (measured
  bound: 23 identities; minimum sufficient subset 13), with the evidence reference recorded per
  identity and per covered interval;
- lineage-stability mask per §4.1.2a-1 — all three conjuncts — for every cell counted as permanently
  unresolved, recorded per cell and reproducible;
- frozen `G0_FORM_ALIAS_CANDIDATES_V1` recorded with the adjudication (§4.1.2c-1);
- **both** the optimistic and pessimistic sensitivity cases required by §4.1.2d;
- explicit §4.1.2b treatment of zero-filing identities;
- the §4.1.2c change-channel classification for every DISPUTED cell;
- frozen-class optimistic weekly ceiling grid;
- **per-week residual budget** `10 - permanently_unresolved_count`, published for Gate 0b (§4.2.5);
- five-window / span satisfiability adjudication under §4.1.3a;
- **distance-to-feasibility report** per §4.1.4a;
- `G0A PASS / HOLD / STOP` record, with the §4.1.2d precedence applied;
- exact known-answer fixture proving shared grid machinery reproduces V3 `425 / 1,247` and `92.801%`
  on the sealed V3 inputs. **The fixture already exists and is custodied** — do not rediscover it:
  `s3://workbench-sec001-v3-research-219024422756/sealed/epoch/SUCCESSOR_EPOCH_0_1167/2026-08-26/`
  `measurement/coverage_result_v1.json` VersionId `RuKV_lvSDT0JyaE7DGEVDqkWDf2KKtiZ`
  sha256 `788755facfc2f2056dcfb4b19db0a3e4a80a03ce3dfa2f47e963c2a78ee24988`, with its five pinned
  inputs alongside it under the same `measurement/` prefix (`segments_projection.json`
  `DVAGTb8wL2z3peRI7ZyqtQjJDXaTTuiq`, `identity_rows.json` `eDDEskSPpRP8nqqTSxQGe9xgU0lhnxy8`,
  `sic_mapping.json` `l1tVyhzqON6BUVWfpQY2QSeuAR9ICs0t`) and the governed grid and PIT-200 membership
  under `sealed/2026-08-24/` (`governed_grid.json` `.l3F3H_f3YrP0CeCbsd7I64WPcheuuAe`,
  `pit200_membership_v2.json` `Yp4_vEljByrXunNWH8abpziMi0FHD1Pa`).

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
21. **Gate 0b (or any later gate) credits as resolved a class an earlier gate proved permanently
    unresolved -> FAIL** *(v1.2 — enforces §4.2.5 monotone accumulation)*
22. **A cell credited as resolved without citing one of the five named §4.1.2c change channels ->
    FAIL** *(v1.2 — prevents the open-ended optimistic clause from returning)*
23. **Gate-0a issues HOLD on a ceiling that STOPs -> FAIL** *(v1.2 — enforces §4.1.2d precedence)*
24. **Gate-0a adjudication published without a distance-to-feasibility report -> FAIL** *(v1.2)*
25. **Lineage-stability mask computed at year granularity rather than exact accepted timestamps ->
    FAIL** *(v1.2 — the §4.1.5 diagnostic is year-granular and is not the governed test)*
26. **A cell counted against the Gate-0a ceiling without an O-9-approved effective-dated security→CIK
    binding covering that week -> FAIL** *(v1.3 — the P0 conjunction)*
27. **The MR-002 `crosswalk`, or any current-CIK assignment, used as a `SECURITY_CIK_BINDING` source ->
    FAIL** *(v1.3 — §4.1.2a-2; it is the current-CIK model with dates attached)*
28. **A Gate-0a/0b adjudication that does not record the frozen alias universe it was computed under,
    or that admits a form outside `G0_FORM_ALIAS_CANDIDATES_V1` without re-entry -> FAIL** *(v1.3)*
29. **HOLD issued without both the optimistic and pessimistic cases computed, or a materiality
    judgement substituted for the §4.1.2d test -> FAIL** *(v1.3)*
30. **Zero-filing identity counted as permanently unresolved in Gate 0a without sealed source-
    exhaustiveness evidence -> FAIL** *(v1.3 — §4.1.2b)*

### 16.2 Positive controls

1. `HEADER_INDEX` observation with `inside_sec_header=false` and a valid SEC index-header SIC remains **ADMISSIBLE**.
2. Filing-document SIC inside the literal `<SEC-HEADER>` span remains admissible.
3. Shared CIK referenced by multiple trading identities is acquired exactly once and projected to each applicable registrant episode.
4. Shared grid/coverage tooling reproduces the sealed V3 known answer exactly, against the custodied
   fixture and its pinned Version IDs (see WP0A deliverables):
   - `231,446 / 249,400 = 92.801%`
   - `425 / 1,247` qualifying governed rebalances.
5. Holiday Mondays present in the membership artifact contribute exactly zero denominator cells.
6. A cell with an effective-dated security→CIK binding covering the week, bracketing CIK filings, and
   no competing binding is classified **LINEAGE-STABLE** and is eligible to count against the Gate-0a
   ceiling.
7. A cell at the first or last observed year of its CIK's filing span is classified **DISPUTED** and is
   credited as resolved.
9. A cell carrying a **current CIK assignment plus bracketing CIK filings but no effective-dated
   security→CIK binding** is classified **DISPUTED**, never LINEAGE-STABLE. *(v1.3 — enforces the
   §4.1.2a-1 conjunction)*
8. Gate 0b's unresolved set is a **superset** of Gate 0a's for every governed week.

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
| Gate-0b accumulated (frozen-class + FPI) optimistic bound cannot satisfy O-2 | STOP V3.1 before WP1 |
| Any gate re-credits a class an earlier gate proved permanently unresolved | INVALID GATE — re-run |
| Gate-0a cell credited resolved without a named §4.1.2c change channel | INVALID GATE — re-run |
| Gate-0a cell counted against the ceiling without an O-9-approved security→CIK binding | INVALID GATE — re-run |
| Form alias admitted outside the frozen `G0_FORM_ALIAS_CANDIDATES_V1` | Gate-0 adjudication VOID — re-enter |
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

All design decisions are resolved and carry forward unchanged in v1.2. v1.2 changes gate *mechanics* only — it changes no O-decision.

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

Changing any O-1 through O-9 decision after WP0A or WP0B evidence is observed requires a new versioned
redesign/adjudication. In particular, the following may not be changed merely because Gate 0 or later coverage is unfavorable:

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
Version: v1.3 FINAL

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
3. Freeze `G0_FORM_ALIAS_CANDIDATES_V1` (§4.1.2c-1) and record it with the adjudication.
4. Run **WP0A-Q** (§4.1.2a-3): establish the O-9-approved effective-dated security→CIK binding for the
   ranked binding set, in descending contribution order, stopping when the verdict is determined.
5. Build the **lineage-stability mask** under all three conjuncts of §4.1.2a-1; every cell failing any
   conjunct is DISPUTED and defaults to resolved.
6. Mark the admissible Gate-0a permanently-unresolved classes (`excluded_low`, and other already-frozen
   cases that pass the stability test; zero-filing identities default optimistic per §4.1.2b).
7. Classify every DISPUTED cell by its §4.1.2c change channel; a cell with no named channel may not be
   credited as resolved.
8. Compute per-governed-week unresolved counts, the optimistic `theta_name` pass ceiling, and the
   per-week residual budget for Gate 0b.
9. Compute the **pessimistic** case as well (§4.1.2d) — every disputed cell unresolved.
10. Apply the frozen five-window / fixed-end / `theta_window` / `theta_span_min` satisfiability logic
    per §4.1.3a to both cases, without exposing or joining returns.
11. Run the exact V3 known-answer fixture (`92.801%`, `425/1,247`) against the shared grid machinery,
    using the custodied artifact Version IDs rather than re-derived inputs.
12. Produce the §4.1.4a distance-to-feasibility report.
13. Produce exactly one adjudication, applying the §4.1.2d two-sided test:
   - `G0A_PASS_FROZEN_CLASSES_SATISFIABLE`
   - `G0A_HOLD_INPUT_STABILITY_UNRESOLVED`
   - `G0A_STOP_FROZEN_CLASSES_FORECLOSE_COVERAGE`
14. Hash, remote-custody and fresh-fetch verify the Gate-0a artifacts and record.
15. **STOP at the owner checkpoint.**

If G0A STOPs, do not run the FPI investigation. If the program is to continue, it requires a new versioned redesign/adjudication; O-2 or O-6 may not be changed inside V3.1.

## 22. v1.3 final disposition

**FINAL DESIGN. Supersedes v1.2. No implementation has been authorized by this document alone.**

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
Gate 0b: provisional FPI source satisfiability (ACCUMULATED with Gate-0a classes)
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

The successor earns the right to spend engineering and acquisition effort only after each earlier
satisfiability gate proves that later success is still possible under the already-frozen rules.

⭐ **Expected outcome, stated in advance so it cannot be presented later as a surprise.** Under the
corrected §4.1.2a-1 test the outcome depends entirely on WP0A-Q:

- **without WP0A-Q**, no cell qualifies as LINEAGE-STABLE from sealed artifacts, so the optimistic case
  passes and the pessimistic case stops ⇒ **`G0A_HOLD`**, naming the security→CIK binding as the
  evidence required;
- **with WP0A-Q**, if the binding qualifies for the minimum sufficient set of 13 identities over
  2022–2026 — names that are single continuously-filing registrants across that window — the terminal
  window fails `theta_window` and the adjudication is
  **`G0A_STOP_FROZEN_CLASSES_FORECLOSE_COVERAGE`**.

The second is the likely path, and it is the gate working. Per §1.4 the binding constraint
is the frozen taxonomy in the modern era, not the lineage defect that WP1–WP4 were scoped to repair, so
a STOP here saves the acquisition program rather than ending a viable one. The distance-to-feasibility
report (§4.1.4a) is then the hand-off to whatever successor the owner chooses to define under §4.1.6.

**Immediate next owner decision:** ~~authorize WP0A only, or stop V3.1 before implementation~~ →
**DECIDED 2026-08-26: WP0A ONLY, AUTHORIZED.** See §23. The next owner decision is now the WP0A-Q
evidence-acquisition question in §23.5.

---

## 23. WP0A authorization and execution record *(added v1.4)*

### 23.1 Authorization

```text
SEC-001 V3.1 — WP0A ONLY: AUTHORIZED            owner, 2026-08-26
  includes: bounded WP0A-Q security->CIK qualification substep
  maximum scope: the deterministically re-derived modern Gate-0a proof population
  required terminal action: PASS / HOLD / STOP -> custody -> STOP, return to owner
```

⛔ **NOT authorized, regardless of WP0A outcome:** WP0B / FPI work · WP1 lineage construction ·
WP2 population/order · any SEC classification crawl · state-seeding acquisition · new coverage-token
creation or spend · economics · runtime implementation. **Stop at the G0A owner checkpoint.**

### 23.2 WP0A-Q authorized scope

**Objective, and its limit.** Establish *enough* effective security→CIK binding evidence in the binding
modern-period `excluded_low` population for Gate 0a to issue a mathematically valid PASS / HOLD / STOP.
**It is not a miniature WP1.** It may not construct full 26-year lineage, discover predecessor CIKs
generally, solve FPI history, repair the 10,800 lineage-gap cells, acquire classification/SIC evidence,
or expand the trading population.

**Qualification predicate** — all three conjuncts of §4.1.2a-1, at **exact accepted timestamps**. Each
of the following fails on its own: a current CIK field · a CIK filing continuously · the MR-002
crosswalk · ticker equality · company-name continuity. **The security→CIK relationship itself must be
evidenced.**

**Permitted evidence (within O-9).** (A) effective-dated permanent-security evidence whose *CIK history
is historically sourced*, not a current CIK painted across a ticker interval; (B) authoritative
date-bearing transition/security evidence — governed succession, merger, re-registration or equivalent;
(C) a governed evidence **bundle** in which every hop is explicit and independently pinned
(`permanent security identity → effective-dated security/class identity → authoritative
registrant/security-class evidence → CIK`). ⛔ No hop may rest on ticker or name similarity. Evidence
that makes the relationship merely *plausible* leaves the cell DISPUTED with optimistic credit.

**No outward extrapolation.** Binding proven from A to B qualifies cells within A–B only; cells outside
remain disputed unless separately bounded. ⛔ No "same company throughout"; ⛔ no backward projection
from present stability.

**Alias set** — `G0_FORM_ALIAS_CANDIDATES_V1 = {10-K405}` is frozen; WP0A-Q may not add a form, and any
proposal to expand it voids the Gate-0 adjudication basis.

**Zero-filing identities** — default DISPUTED / optimistic. `GX`/`FRCB` need not be solved; do not spend
effort to capture 60 cells if the modern constraint already decides the gate.

**Stop-early rule.** Stop collecting binding evidence as soon as — counting only already-qualified
`LINEAGE_STABLE` + `excluded_low` cells as permanently unresolved, and treating **every** unreviewed or
unproven candidate as resolved — every admissible ≥20-year span fails O-2. That is the cleanest possible
Gate-0a STOP: it survives maximum generosity to every name not proven.

**Record required:** how many identities were candidate · reviewed · binding proven · disputed · not
needed because stop-early was reached.

### 23.3 §1 re-derivation — EXECUTED, and it corrects v1.3

Preflight PASS: `HEAD == origin == e84cac4`, design directory clean, v1.1/v1.2/v1.3 present with blob
identities `3cb0245d…` / `f78371e1…` / `6a1d7ee9…`.

Admissible terminal windows, spans ending 2026-06-08 with five equal windows:

```text
span 20.0y -> terminal 4.00y = 189 rebalances, 2022-05-16 .. 2026-06-08   max failing  9
span 22.0y -> terminal 4.40y = 208 rebalances, 2021-12-20 .. 2026-06-08   max failing 10
span 24.0y -> terminal 4.80y = 227 rebalances, 2021-08-02 .. 2026-06-08   max failing 11
span 26.4y -> terminal 5.28y = 249 rebalances, 2021-02-08 .. 2026-06-08   max failing 12
union of all admissible terminal windows = last 249 rebalances
```

**Candidate set = 23 identities** (matching the v1.3 regression expectation). Deterministic review order
`(-cells, permaticker)`:

| # | ticker | permaticker | CIK | cells | | # | ticker | permaticker | CIK | cells |
|---|---|---|---|---:|---|---|---|---|---|---:|
| 1 | GOOG | 119496 | 1652044 | 249 | | 13 | PINS | 110959 | 1506293 | 72 |
| 2 | META | 194817 | 1326801 | 249 | | 14 | TT | 193213 | 1466258 | 65 |
| 3 | GOOGL | 195146 | 1652044 | 249 | | 15 | NBIS | 189383 | 1513845 | 53 |
| 4 | DHR | 199122 | 313616 | 249 | | 16 | ASTS | 110558 | 1780312 | 51 |
| 5 | TMO | 199287 | 97745 | 249 | | 17 | FLUT | 641039 | 1635327 | 41 |
| 6 | SNAP | 124373 | 1564408 | 122 | | 18 | TEM | 641935 | 1717115 | 38 |
| 7 | TTD | 124697 | 1671933 | 122 | | 19 | QS | 631597 | 1811414 | 26 |
| 8 | BIDU | 190868 | 1329099 | 121 | | 20 | TER | 199292 | 97210 | 24 |
| 9 | NOC | 195878 | 1133421 | 109 | | 21 | DJT | 636114 | 1849635 | 18 |
| 10 | APP | 634780 | 1751008 | 84 | | 22 | ECHO | 193776 | 1415404 | 16 |
| 11 | ZM | 110958 | 1585521 | 80 | | 23 | ROP | 197849 | 882835 | 9 |
| 12 | TWTR | 187959 | 1418091 | 80 | | | | | | |

**Decisive K per admissible terminal window:** 20 y → **K = 16** · 22 y → K = 13 · 24 y → K = 13 ·
26.4 y → K = 13. ⭐ **Worst case K = 16**, driven by the 20-year span's tighter 9-week failure
allowance. This is why v1.3's 13 was not authority.

### 23.4 🚨 WP0A-Q is BLOCKED — no qualifying binding source exists in current custody

Every sealed and local artifact was surveyed for a source satisfying §23.2's permitted-evidence classes.
**None qualifies.**

| candidate source | verdict |
|---|---|
| V3 CIK-resolution artifact `1f7d523b…` | **snapshot** by its own provenance statement — disqualified |
| MR-002 `crosswalk` | current-CIK model with ticker-interval dates (§4.1.2a-2) — disqualified, control 27 |
| Sharadar TICKERS (sealed V3 store) | one `secfilings` snapshot URL per permanent identity; it is the crosswalk's own upstream — disqualified |
| local `factor_data_full.duckdb` `tickers` | carries no `permaticker` and no `secfilings`/CIK column at all — cannot bind |
| V3 retained decision bytes (76,821 filings) | SEC-HEADER region only: CIK, name, SIC, IRS number, state, FY end. **No security/trading-symbol field.** Cannot bind |
| SEC `submissions` JSON `tickers` array | current snapshot — same defect as the crosswalk |

⇒ Under the corrected predicate, **zero cells can be qualified from existing custody**, so WP0A-Q cannot
proceed to a decisive result and Gate 0a would return `G0A_HOLD` on the §4.1.2d two-sided test.

### 23.5 ⭐ OPEN OWNER DECISION — bounded acquisition authority for WP0A-Q

The only identified evidence class that would qualify is **date-bearing security↔registrant declaration
by the registrant itself**, which since 2019 is mandatory cover-page XBRL on 10-K/10-Q
(`dei:TradingSymbol`, `dei:Security12bTitle`, `dei:EntityCentralIndexKey`), optionally bounded by Form
8-A12B registration and Form 25 delisting records. Each such filing is an authoritative statement, at a
known acceptance timestamp, that a named trading symbol is that registrant's registered security —
evidence class (B)/(C), and inward-boundable by first/last declaration exactly as O-9 requires.

**Obtaining it requires a new SEC acquisition, which the WP0A authorization does not cover.** Indicative
bound: ≤ 23 CIKs × ~21 quarters over 2021-02 … 2026-06 ≈ **350–480 filings**, cover-page identifiers
only. It would be **SIC-blind** (negative control 16 applies unchanged), return-blind, and subject to
the frozen Defect-E/F transport controls.

⛔ **Not started.** Nothing was fetched. The decision is the owner's:

1. **authorize** a bounded, SIC-blind cover-page acquisition scoped to the §23.3 candidate set, as a
   named sub-authority of WP0A-Q; or
2. **decline**, and accept `G0A_HOLD` as the WP0A outcome, with §23.4 as the enumerated evidence gap; or
3. **rule** that some other already-custodied source qualifies, and name it.

⚠ Option 2 is a legitimate outcome, not a failure — but note it leaves the candidate undecided rather
than stopped, which is the state §1.4 argues is expensive to sit in.
