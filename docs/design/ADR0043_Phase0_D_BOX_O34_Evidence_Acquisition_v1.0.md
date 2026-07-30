# ADR-0043 Phase-0 D-BOX — O3/O4 Evidence Acquisition (Successor Package)

| Field | Value |
|-------|-------|
| Document ID | ADR0043-PH0-D-BOX-O34-EVIDENCE-ACQ-001 v1.0 |
| Status | **DESIGN PACKAGE — construction/qualification authorized only under O34-ACQ-AUTH-001 + sealed O34-ACQ-FREEZE-001** |
| Created | 2026-07-29 |
| Parent campaign | ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.1 (Option 2A) |
| Controlling design | ADR0043-PH0-CTRL-001 v1.1 |
| Integration design | ADR0043-PH0-INTEGRATION-DESIGN-001 v1.0 |
| Acquisition authorization | ADR0043-PH0-D-BOX-O34-ACQ-AUTH-001 (EFFECTIVE, amended) |
| Construction freeze | ADR0043-PH0-D-BOX-O34-ACQ-FREEZE-001 (must seal before selection) |
| Broker order submission | **HOLD — not authorized by this package** |
| D-BOX gate package execution | **Not authorized** (no O3/O4/O5 PASS attempts under this package) |
| D-WIRE | **Deferred / blocked** |

This package defines rules for constructing **candidate** O3 and O4 archives after the
governed locate established that no pre-existing bindable corpora exist. Construction and
qualification require **O34-ACQ-AUTH-001** and a **sealed** construction freeze. This
package does **not** reopen gates, lift HOLD, or make CONSTRUCTED archives gate-ready.

---

## 1. Purpose

Enable a **future** campaign version to bind:

1. an **O3** sealed historical-replay corpus; and
2. separate **O4-A** decision-time and **O4-B** forensic observation sets;

each with identity, size, SHA-256, provenance, eligibility window, and observation counts —
without look-ahead contamination of O4-A.

---

## 2. Observation-set construction rules (prospective)

### 2.1 Shared rules

| Rule | Requirement |
|------|-------------|
| Account scope | Account **3** only for any account-scoped evidence |
| Immutability | Once sealed, archive is append-forbidden; supersession requires a new archive id |
| Identity | Stable `observation_set_id` / `sealed_archive_id` assigned at seal time |
| Hash | SHA-256 of canonical archive bytes; pinned in freeze manifest |
| Storage | Local sealed path and/or S3 object with **Version ID** + SHA-256 (fail closed) |
| Provenance | Written seal record: constructor, host, tooling commit, source systems, exclusions |
| No invention | Temporary / “TBD during execution” names **forbidden** in any freeze seal |

### 2.2 O3 historical-replay corpus

| Field | Prospective requirement |
|-------|-------------------------|
| Content | Eligible historical observations sufficient to exercise integrated plan, quote provenance, authority, loss, checkpoint, and recovery behavior; support false-reachable scoring and model-coverage recording |
| Eligibility window | Explicit UTC `[start, end]` frozen **before** evaluation; no post-hoc extension without superseding archive |
| Sampling | Document inclusion rules, stratum definitions, and exclusion list (halts, bad ticks, out-of-scope symbols, non-account-3 events) |
| Exclusions | Record every excluded class with reason codes |
| Archive procedure | Deterministic pack → SHA-256 → seal record → optional S3 pin → bind into a **new** freeze manifest |
| Relation to AMD-08 | Sealed-set open/unseal remains a logged procedure; this package supplies the corpus that AMD-08 would open |

### 2.3 O4-A decision-time set

| Field | Prospective requirement |
|-------|-------------------------|
| Content | Evidence available **before first broker submission only** (quotes, model/runtime presence, plan/authority inputs) |
| Decision-time cutoff | Explicit timestamp / event marker: **first submission boundary**; everything after is out of set |
| Prohibition | **No future knowledge** — fills, terminal broker state, and post-submit quotes **must not** appear in O4-A |
| Expected gate use | O4-A replay → `INDETERMINATE` + `INSUFFICIENT_EXECUTION_COST` (or `MODEL_UNAVAILABLE` if model absent) |
| Counts | Observation / plan count recorded at seal |
| Time range | UTC range ending at or before the decision-time cutoff |

### 2.4 O4-B forensic / terminal set

| Field | Prospective requirement |
|-------|-------------------------|
| Content | Complete terminal evidence **including fills** and terminal loss/accounting inputs |
| Boundary | Distinct archive from O4-A; mixing into O4-A is a refuse condition |
| Expected gate use | O4-B replay → `UNREACHABLE_WITHIN_CAPS` |
| Counts | Observation / fill / plan counts recorded at seal |
| Time range | UTC range covering terminalization of the same episodes (documented linkage to O4-A episode ids without merging blobs) |

### 2.5 No-mix rule (load-bearing)

O4-A and O4-B are **separate sealed archives**. A harness or evaluator that combines fields
from both into one bundle must **refuse**. Episode linkage (shared ids) is allowed in
metadata; payload mixing is not.

---

## 3. Construction freeze, outcomes, and stop conditions

### 3.1 Construction freeze (before selection)

Seal **ADR0043-PH0-D-BOX-O34-ACQ-FREEZE-001** before selecting records. Required contents
and allow/prohibit lists are governed by **O34-ACQ-AUTH-001** §§1–2. No rule may change
after outcome inspection without a superseding freeze and owner acknowledgment.

### 3.2 Archive outcomes (construction ≠ gate-ready)

| Outcome | Meaning |
|---------|---------|
| **CONSTRUCTED** | Candidate archive bytes + hashes under freeze rules |
| **QUALIFIED** | Independent report proves provenance, no O4-A look-ahead, no O4 mix, lineage, counts, hash/schema, no synthetic/cross-program substitution |
| **REJECTED_AS_NON-BINDABLE** | Failed qualification or stop condition |

Only a later **campaign amendment** may bind a QUALIFIED archive as an O3/O4 input.

### 3.3 Archive and hash procedure

1. Seal construction freeze (all required fields).
2. Materialize candidate archive bytes under a staging path (**CONSTRUCTED**, not gate-ready).
3. Compute SHA-256; write construction seal record (constructor, tooling commit, counts, windows).
4. Run independent qualification → QUALIFIED or REJECTED_AS_NON-BINDABLE.
5. Optional S3 pin with Version ID + SHA-256 (fail closed).
6. Campaign amendment + owner acknowledgment before any gate that consumes the archive.

### 3.4 Stop conditions

Stop and close INCONCLUSIVE, or require amendment, when: required snapshot unavailable;
provenance unproven; decision-time cutoff unreconstructable; terminal completeness
unestablished; deduplication ambiguous; sources mutated after bound snapshot; broker calls
beyond authorized reads; or sample sufficiency would require generating new observations.

---

## 4. What this package does **not** authorize

- Broker order submission or generation of new live fills / sessions / observations
- Manufacturing sample size; converting unit-test/synthetic fixtures into empirical rows
- Silent import of another research program’s evidence
- Treating WP7 hermetic fixtures or freeze-test stubs as empirical observation sets
- Declaring CONSTRUCTED archives gate-ready without QUALIFIED + campaign amendment
- Reopening O3/O4/O5 inside CAMPAIGN-001 v1.1 without a new campaign-scope version
- D-WIRE eligibility

---

## 5. Disposition

**Design package under EFFECTIVE O34-ACQ-AUTH-001.** Construction/qualification may proceed
only after **O34-ACQ-FREEZE-001** is sealed. HOLD and D-WIRE block remain.

*End of ADR0043-PH0-D-BOX-O34-EVIDENCE-ACQ-001 v1.0.*

