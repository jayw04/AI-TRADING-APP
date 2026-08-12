# Owner Decision — Evidence-Gap Acquisition Start

| Field | Value |
|-------|-------|
| Ruling ID | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-START-001 |
| Decision | **APPROVED / EFFECTIVE** |
| Scope | Snapshot capture → recoverability inventory → construction → independent qualification **only** |
| Bound acquisition freeze | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-FREEZE-001 |
| Sealed artifact | `docs/design/ADR0043_Phase0_D_BOX_Evidence_Gap_ACQ_Freeze_Manifest_001_SEALED.json` |
| Canonical body SHA-256 | `af7693f4b97fd7d9d4ad642ab1af47e9e9a2a8cd680f6a26c4d01fee8d57967e` |
| Freeze content tip | `853f5f620d3089e66e2a54261b33ee189e79c7cb` (PR #572) |
| Freeze seal merge | `ec243c57bb2cdd9e59f903a65489ea6298b99c72` (PR #573) |
| Parent acquisition auth | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-AUTH-001 **EFFECTIVE** |
| Authorization merge | `29eece313b1b2e7541a20c0440101455b78b106d` (PR #571) |
| Design package | ADR0043-PH0-D-BOX-EVIDENCE-GAP-001 **v1.0** @ `71d346d` |
| Account | workbench `3` / Alpaca paper `PA34USW0Q8UO` |
| Eligibility window | `[2026-06-30T00:00:00Z, 2026-07-30T19:39:07Z)` |
| Sign-off | Owner acknowledgment (Jay Wang) — typed governance acknowledgment |
| Ruling date (UTC) | 2026-07-30 |
| Effective upon | Publication merge of this record on `main` |
| Broker order submission | **HOLD — not lifted** |
| D-WIRE | **Blocked / not authorized** |
| Gate execution / campaign reopen | **Not authorized** |
| Production / `b0058bf` | **Reference-only — do not use or modify** |

---

## Ruling

The owner **APPROVES** ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-START-001 for
**snapshot capture → recoverability inventory → construction → independent qualification
only**, bound to EVIDENCE-GAP-ACQ-FREEZE-001 body SHA-256
`af7693f4b97fd7d9d4ad642ab1af47e9e9a2a8cd680f6a26c4d01fee8d57967e`.

Gates remain **closed**. D-WIRE remains **blocked**.

---

## 1. Binding rule

This start is **void** unless:

1. The sealed freeze artifact’s `seal.body_sha256` equals  
   `af7693f4b97fd7d9d4ad642ab1af47e9e9a2a8cd680f6a26c4d01fee8d57967e`, and  
2. Seal verification succeeds (RFC8785-JCS body-hash match + `manifest_status=SEALED`), and  
3. Governing pins match: auth `29eece3…`, content tip `853f5f6…`, seal merge `ec243c5…`.

---

## 2. Authorized sequence

### Stage 1 — Opening and snapshot capture

**Before any SQL SELECT, file-content inspection, filtering, joining, or O5 search:**

1. Verify the exact sealed freeze and body hash above.  
2. Confirm the working tree is clean and the runtime is **isolated** (not production OrderRouter path).  
3. Confirm production `b0058bf` is neither used nor modified.  
4. Capture immutable identities for every declared mutable source in the sealed freeze:
   - `workbench.sqlite` or governed export SHA-256  
   - market/quote tree hashes or object Version IDs  
   - any declared checkpoint, terminal, or audit artifact roots  
   - the governing Git evidence tree used for O5 locate-only  
5. Record timestamps, host, operator, commands, and capture hashes.  
6. Publish an **acquisition opening record**.

If a declared source is unavailable, mutated during capture, or cannot be pinned, stop that
source class as **INCONCLUSIVE**. Do **not** substitute a different source without a
superseding freeze.

### Stage 2 — Source inventory and recoverability

After snapshot capture is complete:

1. Inventory eligible account-3 records.  
2. Evaluate recoverability using **only** frozen mappings.  
3. Determine whether each required surface has provable lineage.  
4. Apply the frozen eligibility window, deduplication, and exclusions.  
5. Record all missing surfaces with predetermined reason codes.  
6. Run the O5 Tier-A **locate-only** procedure.

This stage may inspect frozen evidence; it must **not** modify it.

### Stage 3 — Construction

Construct **new** candidate archives only from recoverable frozen sources:

| Output | Rule |
|--------|------|
| New O3 archive | EVGAP naming; not QUAL-001 IDs |
| New O4-A archive | Separate DECISION_TIME pipeline |
| New O4-B archive | Separate FORENSIC pipeline; no payload merge with O4-A |
| O5 anchor manifest | Including valid `anchors: []` where none qualify |

All prior QUAL-001 archives remain **immutable** and must not be reused as output IDs.

### Stage 4 — Independent qualification

Qualification must independently verify:

- source-to-row lineage  
- hash and schema  
- completeness  
- exclusion reconciliation  
- no fabrication  
- no O4-A look-ahead  
- no O4-A / O4-B mixing  
- account-3 scope  
- count equations  
- O5 Tier-A status  

| Permitted outcome |
|-------------------|
| `QUALIFIED` |
| `REJECTED_AS_NON_BINDABLE` |
| `INCONCLUSIVE` |

---

## 3. Important limit on recovery

This start authorizes **deterministic recovery only** where the necessary source facts
**existed within the frozen source snapshot**.

A deterministic formula is **not** sufficient by itself. Every input must have frozen,
account-scoped provenance.

### 3.1 Prohibited recovery (examples)

| Prohibited |
|------------|
| Deriving a historical bid/ask from a later close |
| Setting `model_available=true` because the code existed |
| Generating `day_change` from an assumed baseline |
| Substituting O4-B terminal facts into O4-A |
| Inventing checkpoint or recovery state from expected workflow behavior |
| Using evaluator defaults to fill null fields |

---

## 4. Explicitly not authorized

| Item | Status |
|------|--------|
| Broker orders or broker writes | **Not authorized** (HOLD) |
| New live fills or sessions | **Not authorized** |
| Prospective telemetry activation or instrumentation | **Not authorized** |
| Production deployment or modification / use of `b0058bf` | **Forbidden** |
| Canary, ENFORCE, or caps changes | **Not authorized** |
| July 24 digest mutation | **Forbidden** |
| Gate execution or reopening (O3 / O4 / O5) | **Not authorized** |
| D-WIRE eligibility | **Blocked** |
| Campaign freeze / gate-start | **Not authorized** by this ruling |

---

## 5. Runtime posture

| Control | Value |
|---------|-------|
| Account | `3` / `PA34USW0Q8UO` paper |
| Eligibility window | `[2026-06-30T00:00:00Z, 2026-07-30T19:39:07Z)` |
| Runtime | Isolated harness / read-only capture hosts only |
| Evidence root (acquisition) | `docs/design/evidence/dbox_evgap_acq_001/` |

---

## 6. Signature block

| Field | Value |
|-------|-------|
| Approving role | Owner |
| Decision | **APPROVED / EFFECTIVE** — capture → inventory → construct → qualify only |
| Sign-off | Owner acknowledgment (Jay Wang) — typed governance acknowledgment |
| Effective | Upon publication merge of this record |

*End of ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-START-001.*
