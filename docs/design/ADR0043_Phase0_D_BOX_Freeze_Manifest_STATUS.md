# D-BOX Status — Post v1.2 CLOSE / Evidence-Gap Design

| Field | Value |
|-------|-------|
| Campaign v1.2 | **CLOSED** (V12-CLOSE-001 @ `4232c1a`) |
| Execution authority | **None** under START-002 / FREEZE-003 |
| D-WIRE | **BLOCKED** |
| HOLD | Unchanged |
| Active design | ADR0043-PH0-D-BOX-EVIDENCE-GAP-001 **v1.0** — **DESIGN-ONLY** |
| Design path | `docs/design/ADR0043_Phase0_D_BOX_Evidence_Gap_Design_v1.0.md` |

## Evidence-gap coverage (prospective only)

1. O3 replay-surface capture  
2. O4-A two-sided decision-time quote capture  
3. O4-B `day_change` / forensic baseline  
4. O5 Tier-A anchor acquisition  

**No collection, production change, broker activity, or gate reopen** until a new
authorization → freeze → start.
