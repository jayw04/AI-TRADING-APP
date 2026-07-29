# D-BOX Freeze Manifest — Status

| Field | Value |
|-------|-------|
| Active sealed artifact | `docs/design/ADR0043_Phase0_D_BOX_Freeze_Manifest_002_SEALED.json` |
| Document ID | ADR0043-PH0-D-BOX-FREEZE-MANIFEST-002 |
| Manifest status | **SEALED** |
| Post-seal state | **SEALED AND READY FOR OWNER START DECISION — CAMPAIGN NOT YET AUTHORIZED TO RUN** |
| Campaign | ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.1 Option **2A** |
| Prior manifest 001 | **UNSEALED — SUPERSEDED** |
| Campaign start | **HOLD** — see ADR0043-PH0-D-BOX-START-001 (PROPOSED, not effective) |

## Seal record

| Field | Value |
|-------|-------|
| Path | `docs/design/ADR0043_Phase0_D_BOX_Freeze_Manifest_002_SEALED.json` |
| Tooling / content tip | `b6836eb5718ab20a7799bb261f3eea3e4054b11f` |
| Campaign merge | `709e6136900d1e5e22bb0c074dc90ea35cadf22b` |
| Validator SHA-256 | `584f5392c872191341f6a0e8f55cbb0fda7806ce280d4d4d4c739de3471df6a9` |
| Canonical body SHA-256 | `d35de863e85153f8f1a4768b62b7d89a2043525433ec8841631cb8a7c20a2d1f` |
| Sealed artifact file SHA-256 | `7e923b8f39991e2de483e5200bf7ffc07a35d9e5cd8dc054f464711a646f7168` |
| Sealed at (UTC) | `2026-07-29T23:44:13Z` |
| Operator | Jay Wang (owner) |
| Operator ack | `typed_governance_acknowledgment` |
| Owner countersignature | typed governance acknowledgment (ADR0043-PH0-D-BOX-FREEZE-002-SEAL-001) |
| Owner ack kind | `typed_governance_acknowledgment` |
| `verify-seal` | **exit 0** (`ok: true`) |
| `check` (sealed) | **exit 0** |

### Exact verification commands

```text
python apps/backend/scripts/adr0043_dbox_freeze_manifest.py verify-seal --manifest docs/design/ADR0043_Phase0_D_BOX_Freeze_Manifest_002_SEALED.json
python apps/backend/scripts/adr0043_dbox_freeze_manifest.py check --manifest docs/design/ADR0043_Phase0_D_BOX_Freeze_Manifest_002_SEALED.json
```

## Not authorized

CORR-06/O1/O2 execution; O3/O4/O5; broker orders; production imports; D-WIRE; canary;
ENFORCE; caps; limits-digest changes — until a **separate** signed start decision
(ADR0043-PH0-D-BOX-START-001) is EFFECTIVE.
