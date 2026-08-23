# GAPPER Research Design v2.1.1 — Owner Approval Record

| Field | Value |
|---|---|
| Record | **Approval record** — a governance artifact binding an owner decision to an exact artifact |
| Version | v1.0 |
| Approved document | **GAPPER Research Design v2.1.1** (`docs/design/Gapper/GAPPER_Research_Design_v2_1_1.docx`) |
| **SHA-256 of the approved artifact** | **`2706c4dc406ac19350781db180c315c7f9f38f4c1c8ba9fe8466e9658873d73d`** |
| Size | 26,062 bytes |
| Approval date | **2026-08-11** (recorded 2026-08-11T14:50Z) |
| Owner disposition | **APPROVED** |
| **Authorization scope** | **Stage 0 only** |
| S3 publication | Occurs **only after** this record exists. Not published at time of writing. |

> **One line.** The owner approves GAPPER Research Design **v2.1.1**, bound to SHA-256
> `2706c4dc…d73d`, **for Stage 0 only**. Forward accrual, validation, confirmatory consumption, paper
> trading, and RANK-001 candidacy each require their own separate, later owner authorization.

---

## 1. Disposition

**APPROVED — Stage 0 only.**

The approval binds the exact artifact identified by the SHA-256 above, independently re-hashed by the owner
before approval. Because the DOCX is gitignored under ADR 0050 (`/docs/**/*.docx`, S3-resident) it carries no
Git object identity, so **the hash is the approval identity anchor**. A document whose hash does not match the
value above is not the approved document.

**Any subsequent edit — including a single character — invalidates this approval.** A revised artifact requires
a new hash and a new approval record; this record may not be transferred to it.

### Superseded hash

| Hash | State |
|---|---|
| `84913de09363bb52786d6ca93917920239533d889e4651c90f8004c07d08e993` | **SUPERSEDED — never approved.** Round-2 artifact, prior to the §3 Stage-0 two-properties clarification. Do not pin, cite, or approve. |

---

## 2. What this authorizes

**Stage 0 only** — the economic-feasibility study defined in §3 (0A data/opportunity feasibility; 0B cheap
predictability probe), executed against the frozen GO/HOLD/STOP values in §3.3 and the early-STOP rule.

Per §252 of the approved document, each of the following requires its own **subsequent** owner authorization and
is **not** authorized here: forward accrual · validation · confirmatory consumption · paper trading · RANK-001
candidacy.

Two preconditions inside the approved document remain binding and are **not** waived by this approval:

- **§9 sequencing.** Stage 0 begins only after MR-002 execution-order Steps 1–2 are complete. Developer-side
  Stage-0 preparation (dataset-contract drafting, reconstruction scripts against the development store) may
  proceed in parallel **after this approval**, which this record now supplies.
- **§8.1 operational readiness.** Forward accrual — which this approval does **not** authorize — additionally
  requires the probation window to be passed on the repaired collection path. As of 2026-08-11 probation has
  **not started and cannot start** on the current transport (measured capture rate 1 of the last 5 trading
  days). See §4.

---

## 3. What was approved — the 2026-08-11 pre-approval amendment

v2.1.1 was amended **before** approval so that the approved governing document describes the evidence state that
actually existed at approval, rather than requiring a reader to reconcile it against a separate closure
artifact. Source of fact: **GAPPER-GATE-v1 Closure Record v1.0**, verified 2026-08-11 08:06 ET by direct read of
the live evidence store.

| # | Section | Amendment |
|---|---|---|
| 1 | §2 | **C1** — unstamped forward records corrected **15 → 16** (07-17 → 08-10, the close of accrual); the published figure omitted the 08-10 record. The 22 forward records are broken out as 6 provenance-stamped + 16 unstamped, so the defect is measurable rather than inferred. |
| 2 | §2 | **C2** — the statement that the 08-10 record "was manually overwritten with genuine scan data" is replaced. Three facts are now distinguished: fabrication confirmed; the 10:35:32 ET overwrite confirmed; the mutation **did not persist** — the live record again holds fabricated 08-05 content. The restoration mechanism is recorded **UNDETERMINED**, with an explicit prohibition on converting it to a causal claim without new evidence. |
| 3 | §2 | **New v1 contrast-loss finding (root cause).** On **16 of 42** dates the upstream `eligible_panel` exceeded `eligible_count`: contrast reached the funnel and was collapsed before ranking. Therefore additional accrual under the unchanged v1 funnel could not have cured the non-identifiability — establishing `DESIGN-NONIDENTIFIABLE` rather than `INSUFFICIENT_DATA`. |
| 4 | §5.5 | **Write-time provenance generalized** into a design requirement: every published daily record SHALL carry immutable write provenance sufficient to identify creation time, source artifact and hash, producing code/version, invocation/run ID, and **write class** (collection · reconstruction · backfill · repair · manual administrative action). |
| 5 | §3 | **Stage-0 two-properties acceptance clarification** — see §5 below. |
| 6 | §8.1 | **Probation clock-start defined** — see §4 below. |
| 7 | §9 | **Approval precondition made explicit**: developer-side Stage-0 preparation may proceed in parallel only *after* v2.1.1 owner approval. Closes the reading that §9 independently authorized work ahead of §252. |
| 8 | Title | Clerical: `GAPPER Research Design v2.0` → **v2.1.1**, matching the metadata table. |

The amendment corrects the factual record and the acceptance conditions that follow from it. **It adds no
hypothesis and broadens no stage's purpose.** Hypothesis architecture, the ≤2 confirmatory-trial limit, the
gates, the frozen thresholds, and the §252 authorization scope are unchanged.

---

## 4. §8.1 — when the probation clock may start

Probation measures the **repaired** collection path, so that path must be the subject of the test. Probation
begins only when **all** of the following hold:

1. PR **#407** (point-in-time producer fix, `read_gappers_for(day)`) **merged and deployed** to the collection host;
2. **`WORKBENCH_NATIVE_GAPPER_SCREENER_ENABLED` set true** in that host's live configuration/SSM state — the
   flag defaults **off**, so merging alone starts no clock;
3. the **first scheduled autonomous run completed** under that configuration, **with no manual transport step**.

The probation **start timestamp is that first autonomous run**. **Pre-repair observations count toward neither
the numerator, the denominator, nor the duration** — neither for nor against the repaired implementation, since
they measure a path that no longer exists.

Failing probation returns the pipeline to engineering, **never** to a lowered threshold.

---

## 5. §3 — the acceptance condition this approval binds

Stage 0 establishes **two independent feasibility properties**:

1. **Upstream field sufficiency** — the scanner/data system must regularly expose enough legitimate, tradeable
   events to support an adjudicable cross-sectional experiment.
2. **Contrast preservation** — the research funnel must preserve enough of that field through eligibility and
   ranking to produce a genuine selected-versus-non-selected decision.

These are distinct failure modes, and v1 failed the second on dates when a broader upstream field was available.
**Stage 0 may not pass on field size alone.** Every contraction of the funnel must be attributable to a frozen,
reason-coded rule:

```
scanner/event field → tradability exclusions → coverage exclusions → eligible field → ranking → selected field
                                                                                        (selected < eligible)
```

**No unexplained `eligible_panel` → `eligible_count` collapse is permitted.**

This is the acceptance condition that prevents Stage 0 from certifying another funnel that destroys the contrast
the experiment requires — the precise architectural defect that closed v1.

---

## 6. Related artifacts

| Artifact | Relationship |
|---|---|
| `TradingWorkbench_GAPPER001_v1ClosureRecord_v1.0.md` | The evidence-bearing record of the verified v1 census. **Deliberately unchanged** by the amendment — it records what was verified when it was authored, and its §5/§7 entries showing C1/C2 as *open* are correct as of its own authorship. Do not edit it to say "resolved." The forward reference from v2.1.1's metadata to that record carries the linkage. |
| PR **#511** | `INVALID-EVIDENCE / NO_SELECTION_CONTRAST` guard — the §5.5 fail-closed verdict engine. Open; until merged, a human can still invoke the void v1 verdict path. |
| PR **#407** | Box-native gapper screener (GAP-NATIVE-001, ADR 0041). Open; carries the fabrication fix. Merging alone starts no probation clock (§4). |
| ADR **0041**, ADR **0050** | Screener architecture; documentation location (this record in Git, the DOCX in S3). |

---

## 7. Provenance of this record

| Field | Value |
|---|---|
| Artifact hash | Computed at authoring time and matched against the owner's independent re-hash of the same file |
| Verification performed | Zip integrity · all 14 XML parts well-formed · §2 table 7 rows in order · §5.5 bullet numbering preserved · §3 paragraph present · §8.1 and §9 clauses present · §252 unchanged |
| Timestamp basis | UTC (`2026-08-11T14:50Z`). ET clock times are **not** derived on the developer workstation — local TZ conversion there returns UTC and would misreport. |
| Record location | Git (`docs/design/Gapper/`), per ADR 0050: this record is *governing* and must be readable under pressure without an AWS dependency. The approved DOCX itself is S3-resident. |
