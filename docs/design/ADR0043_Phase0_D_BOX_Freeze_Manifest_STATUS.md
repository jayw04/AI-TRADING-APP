# D-BOX Freeze Manifest — Status (CAMPAIGN-001 v1.1 / Option 2A)

| Field | Value |
|-------|-------|
| Active draft | `ADR0043_Phase0_D_BOX_Freeze_Manifest_002_UNSEALED_DRAFT.json` |
| Document ID | ADR0043-PH0-D-BOX-FREEZE-MANIFEST-002 |
| Campaign | ADR0043-PH0-D-BOX-CAMPAIGN-001 **v1.1** (Option **2A**) |
| Campaign label | **PARTIAL STRUCTURAL CAMPAIGN ONLY — NO D-WIRE ELIGIBILITY — O3/O4/O5 DEFERRED** |
| Prior manifest | ADR0043-PH0-D-BOX-FREEZE-MANIFEST-001 |
| 001 status | **UNSEALED — SUPERSEDED DUE TO ABSENT O3/O4 EVIDENCE IDENTITIES** |
| 001 file | `ADR0043_Phase0_D_BOX_Freeze_Manifest_001_SUPERSEDED_UNSEALED.json` |
| Successor O3/O4 package | ADR0043-PH0-D-BOX-O34-EVIDENCE-ACQ-001 v1.0 |
| Seal | **Not performed** (readiness may be green locally; seal + countersign require explicit owner step) |

## Predetermined dispositions (v1.1)

| Package | Disposition |
|---------|-------------|
| O3 | **INCONCLUSIVE — REQUIRED CORPUS ABSENT** |
| O4-A | **INCONCLUSIVE — DECISION-TIME SET ABSENT** |
| O4-B | **INCONCLUSIVE — FORENSIC SET ABSENT** |
| O5 | **INCONCLUSIVE** (`anchors: []`) |
| CORR-06 / O1 / O2 | Executable only after **002 seal** + **separate owner start** |

## D-WIRE

**Blocked.** Load-bearing O3/O4/O5 incomplete. APPROVE on CORR-06/O1/O2 alone does not grant D-WIRE.

## Locate result (formal; two passes sufficient)

O3 / O4-A / O4-B **NOT FOUND**. Checked: local worktrees, S3 inventories, WP0 seal outputs,
canary/FrozenExecutionPlan/RepairB docs, WP7 fixtures, canary host `3.80.11.61` (unreachable).
No bindable artifact with identity, size, hash, provenance, window, and counts.

## HOLD (unchanged)

Broker submission, canary, D-WIRE, deployed-path observation, ENFORCE, caps, July 24
limits-digest changes — **not authorized**.

## Next owner steps (not auto-executed)

1. Publish campaign v1.1 + O34 acq + freeze 001/002 + validator Option-2A support (if not yet on `main`)
2. Re-bind validator commit/SHA on 002 to the published tip
3. Confirm `check` exit 0 on published tree
4. **Seal** 002 body → intended state:  
   `SEALED AND READY FOR OWNER START DECISION — CAMPAIGN NOT YET AUTHORIZED TO RUN`
5. Owner countersign exact body hash
6. Separate campaign-start decision for Option 2A only
