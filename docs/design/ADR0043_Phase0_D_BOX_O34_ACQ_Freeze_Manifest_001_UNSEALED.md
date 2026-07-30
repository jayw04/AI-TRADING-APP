# O34 Construction Freeze Manifest — UNSEALED DRAFT

| Field | Value |
|-------|-------|
| Document ID | ADR0043-PH0-D-BOX-O34-ACQ-FREEZE-001 |
| Status | **UNSEALED DRAFT — must be sealed before any record selection** |
| Authorization | ADR0043-PH0-D-BOX-O34-ACQ-AUTH-001 (EFFECTIVE, amended) |
| Design package | ADR0043-PH0-D-BOX-O34-EVIDENCE-ACQ-001 v1.0 |
| Option 2A evidence merge | `5cb711c5be35d53c3d42277adbd0dc379dead44c` |
| Seal | **Not sealed** — populate all REQUIRED fields, then seal before selection |

> Rule changes after outcome inspection require a **superseding** freeze manifest and owner
> acknowledgment. Temporary / invented observation identities are **forbidden**.

---

## 1. Source inventories and exact snapshots

| Source class | Snapshot identity (path / Version ID / commit / query pin) | Status |
|--------------|-------------------------------------------------------------|--------|
| Historical market / quote data | REQUIRED | unbound |
| Application audit / plan / checkpoint / terminal records | REQUIRED | unbound |
| Account-3 paper records (prior authority only) | REQUIRED | unbound |
| Other (if any) | none unless declared | — |

## 2. Eligibility window

| Field | Value |
|-------|-------|
| Start (UTC) | REQUIRED |
| End (UTC) | REQUIRED |
| Inclusive/exclusive bounds | REQUIRED |

## 3. Inclusion and exclusion rules

| Rule ID | Type | Description | Status |
|---------|------|-------------|--------|
| INC-* | inclusion | REQUIRED | unbound |
| EXC-* | exclusion | REQUIRED | unbound |

## 4. Deduplication key

| Field | Value |
|-------|-------|
| Key fields (ordered) | REQUIRED |
| Collision policy | REQUIRED (fail-closed preferred) |

## 5. Unit of observation

| Field | Value |
|-------|-------|
| Unit definition | REQUIRED (e.g., ExecutionPlan episode / session-leg) |
| Mapping to O3 / O4-A / O4-B rows | REQUIRED |

## 6. Symbol / session clustering rule

| Field | Value |
|-------|-------|
| Clustering definition | REQUIRED |
| Independence assumption for counting | REQUIRED |

## 7. O4-A cutoff rule

| Field | Value |
|-------|-------|
| Cutoff event | first broker submission boundary (or reconstructed equivalent) |
| Reconstruction method | REQUIRED |
| Post-cutoff fields prohibited in O4-A | fills; terminal broker state; post-submit quotes |

## 8. O4-B terminal-completeness rule

| Field | Value |
|-------|-------|
| Completeness criteria | REQUIRED |
| Incomplete observation treatment | REQUIRED (exclude with reason / fail-closed) |

## 9. Missing-data treatment

| Field | Value |
|-------|-------|
| Policy | REQUIRED |
| Reason codes | REQUIRED |

## 10. Target archive schemas

| Archive | Schema ID / path | Status |
|---------|------------------|--------|
| O3 | REQUIRED | unbound |
| O4-A | REQUIRED | unbound |
| O4-B | REQUIRED | unbound |

## 11. Permitted transformations

| Transform ID | Description | Deterministic? | Status |
|--------------|-------------|----------------|--------|
| T-* | REQUIRED enumeration | must be yes | unbound |

Forbidden: non-deterministic sampling after freeze; outcome-conditioned rewrites.

## 12. Expected count reconciliation

| Metric | Expected / formula | Status |
|--------|--------------------|--------|
| Source row count after filters | REQUIRED | unbound |
| Deduplicated observation count | REQUIRED | unbound |
| O3 / O4-A / O4-B emitted counts | REQUIRED | unbound |

## 13. Broker reads (optional)

| Operation | Declared? | Side-effect-free proof | Status |
|-----------|-----------|------------------------|--------|
| *(none by default)* | no | n/a | default empty |

Any broker history read must be listed here before use.

## 14. Seal envelope (populate at seal)

| Field | Value |
|-------|-------|
| manifest_status | UNSEALED_DRAFT |
| body_sha256 | null |
| sealed_at_utc | null |
| operator | null |
| owner_countersignature | null |

---

## Disposition

**Do not select records until this manifest is SEALED.**  
Candidate archives remain **CONSTRUCTED** until an independent qualification report yields
**QUALIFIED** or **REJECTED_AS_NON-BINDABLE**. Gate binding requires a later campaign amendment.

*End of ADR0043-PH0-D-BOX-O34-ACQ-FREEZE-001 (UNSEALED DRAFT).*
