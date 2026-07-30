# D-BOX Status — EVIDENCE-GAP-ACQ-START-001 EFFECTIVE

| Field | Value |
|-------|-------|
| Campaign v1.2 | **CLOSED** |
| FREEZE-003 / START-002 | **Exhausted** (gates not reopened) |
| ACQ-AUTH-001 | **EFFECTIVE** @ `29eece3` |
| Acquisition freeze | EVIDENCE-GAP-ACQ-FREEZE-001 **SEALED** body `af7693f4…` |
| Freeze seal merge | `ec243c5` |
| Acquisition start | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-START-001 **APPROVED / EFFECTIVE** |
| Authorized | Snapshot capture → recoverability inventory → construction → independent qualification |
| Gates / D-WIRE | **Closed** / **BLOCKED** |
| HOLD | Unchanged |

## Sequence in force

1. Stage 1 — opening + snapshot capture (before any SELECT / O5 search)  
2. Stage 2 — inventory + recoverability (inspect frozen evidence; do not modify)  
3. Stage 3 — construct **new** EVGAP archives (+ O5 locate manifest; `anchors: []` valid)  
4. Stage 4 — independent qualification (`QUALIFIED` / `REJECTED_AS_NON_BINDABLE` / `INCONCLUSIVE`)  

QUAL-001 archives remain immutable. No broker activity, production modification, or gate execution.

## Paths

| Artifact | Path |
|----------|------|
| Start | `docs/design/ADR0043_Phase0_D_BOX_Evidence_Gap_Acquisition_Start_Decision_v1.0.md` |
| Sealed freeze | `docs/design/ADR0043_Phase0_D_BOX_Evidence_Gap_ACQ_Freeze_Manifest_001_SEALED.json` |
| Evidence root | `docs/design/evidence/dbox_evgap_acq_001/` |
