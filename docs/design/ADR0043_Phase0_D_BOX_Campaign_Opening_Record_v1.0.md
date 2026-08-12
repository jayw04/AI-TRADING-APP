# D-BOX Option 2A Campaign Opening Record

| Field | Value |
|-------|-------|
| Record ID | ADR0043-PH0-D-BOX-CAMPAIGN-OPEN-001 |
| Campaign | ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.1 (Option 2A) |
| Start ruling | ADR0043-PH0-D-BOX-START-001 (**APPROVED / EFFECTIVE**) |
| Freeze manifest | ADR0043-PH0-D-BOX-FREEZE-MANIFEST-002 |
| Sealed path | `docs/design/ADR0043_Phase0_D_BOX_Freeze_Manifest_002_SEALED.json` |
| Canonical body SHA-256 | `d35de863e85153f8f1a4768b62b7d89a2043525433ec8841631cb8a7c20a2d1f` |
| Opened at (UTC) | `2026-07-29T23:54:33Z` |
| Packages authorized | CORR-06 → O1 → O2 only |
| D-WIRE | **Blocked** |

## Pre-CORR-06 verify-seal (mandatory)

| Field | Value |
|-------|-------|
| Command | `python apps/backend/scripts/adr0043_dbox_freeze_manifest.py verify-seal --manifest docs/design/ADR0043_Phase0_D_BOX_Freeze_Manifest_002_SEALED.json` |
| Exit code | **0** |
| Timestamp (UTC) | `2026-07-29T23:54:33Z` |
| Output SHA-256 | `3a4f817b7f8aaa128936e599d47fb372acfdd40bb200fcd8128ba043b93fe159` |

### Output

```json
{
  "ok": true,
  "body_sha256": "d35de863e85153f8f1a4768b62b7d89a2043525433ec8841631cb8a7c20a2d1f",
  "sealed_at_utc": "2026-07-29T23:44:13Z",
  "canonicalization": "RFC8785-JCS"
}
```

## HOLD (unchanged)

No O3/O4/O5 execution, broker submission, new live fills, production imports, deployed-path
observation, D-WIRE, canary, ENFORCE, caps, or July 24 limits-digest changes.
