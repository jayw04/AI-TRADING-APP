# D-BOX Status — Evidence-Gap Acquisition Authorized (Pre-Seal)

| Field | Value |
|-------|-------|
| Campaign v1.2 | **CLOSED** (V12-CLOSE-001 @ `4232c1a`) |
| FREEZE-003 / START-002 | **Exhausted** — no remaining gate authority |
| D-WIRE | **BLOCKED** |
| HOLD | Unchanged |
| Design | ADR0043-PH0-D-BOX-EVIDENCE-GAP-001 **v1.0** @ `71d346d` |
| Acquisition auth | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-AUTH-001 **APPROVED / EFFECTIVE** |
| Acquisition freeze | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-FREEZE-001 **UNSEALED DRAFT** |
| Acquisition start | **Not issued** |
| Evidence access / selection / reconstruction / capture | **FORBIDDEN** until freeze **sealed** + separate start **EFFECTIVE** |

## Paths

| Artifact | Path |
|----------|------|
| Auth | `docs/design/ADR0043_Phase0_D_BOX_Evidence_Gap_Acquisition_Authorization_v1.0.md` |
| Freeze draft | `docs/design/ADR0043_Phase0_D_BOX_Evidence_Gap_ACQ_Freeze_Manifest_001_UNSEALED.md` |
| Design | `docs/design/ADR0043_Phase0_D_BOX_Evidence_Gap_Design_v1.0.md` |

## Next required sequence

1. Complete all freeze `REQUIRED_FILL` bindings (no exploratory selection)  
2. Readiness check  
3. Seal + countersign EVIDENCE-GAP-ACQ-FREEZE-001  
4. Separate acquisition-start decision  
5. Acquisition / construction → independent qualification of **new** archives  
6. Only then: new campaign scope / campaign freeze / gate-start  

QUAL-001 / FREEZE-003 archives remain **immutable historical evidence**.
