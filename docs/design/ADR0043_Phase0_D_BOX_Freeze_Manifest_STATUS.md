# D-BOX Status — EVIDENCE-GAP-ACQ-FREEZE-001 (content tip / pre-seal)

| Field | Value |
|-------|-------|
| Campaign v1.2 | **CLOSED** |
| FREEZE-003 / START-002 | **Exhausted** |
| ACQ-AUTH-001 | **EFFECTIVE** @ `29eece3` |
| Acquisition freeze | **Content tip in progress** → readiness → seal (authorized); start **HOLD** |
| Evidence access / selection / capture / construction | **FORBIDDEN** until seal + separate start |
| D-WIRE / HOLD | **BLOCKED** / unchanged |

## Artifacts

| Artifact | Path |
|----------|------|
| Auth | `docs/design/ADR0043_Phase0_D_BOX_Evidence_Gap_Acquisition_Authorization_v1.0.md` |
| Freeze tooling | `apps/backend/scripts/adr0043_evgap_acq_freeze_seal.py` |
| EVGAP schemas | `docs/design/schemas/ADR0043_Phase0_EVGAP_{O3,O4A,O4B}_Archive.schema.json` |
| Unsealed JSON | `docs/design/ADR0043_Phase0_D_BOX_Evidence_Gap_ACQ_Freeze_Manifest_001_UNSEALED.json` |
| Sealed JSON | *(after readiness + seal)* |

## Sequence remaining

1. Publish content tip (schemas + tooling + filled UNSEALED body)  
2. Rebind content-tip / tool / schema identities to merge commit  
3. Readiness validation  
4. Seal + countersign  
5. **Separate** acquisition-start (not authorized by freeze seal)
