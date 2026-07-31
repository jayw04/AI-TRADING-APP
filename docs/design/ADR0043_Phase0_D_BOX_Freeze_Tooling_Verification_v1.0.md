# ADR-0043 D-BOX freeze-manifest tooling — verification

| Field | Value |
|-------|-------|
| Document | ADR0043-PH0-D-BOX-FREEZE-TOOLING v1.0 |
| Status | **Governed tooling only — does not authorize campaign start** |
| Canonicalization | RFC 8785 JCS |
| Hash | SHA-256 over `manifest_body` only |
| Encoding | UTF-8 without BOM; final newline excluded from hash input |
| Broker / OrderRouter | **Not imported; not authorized** |

## Governed artifacts

| Artifact | Path |
|----------|------|
| Validator / seal-body utility | `apps/backend/scripts/adr0043_dbox_freeze_manifest.py` |
| JSON Schema | `docs/design/schemas/ADR0043_Phase0_D_BOX_Freeze_Manifest.schema.json` |
| Tests | `apps/backend/tests/scripts/test_adr0043_dbox_freeze_manifest.py` |

After merge, bind this tooling commit and file SHA-256 values into the **unsealed**
freeze manifest under `schema_binding` and `code_and_tools.freeze_manifest_validator`.

## Exact verification commands

From `apps/backend` (or repo root with adjusted paths):

```text
python apps/backend/scripts/adr0043_dbox_freeze_manifest.py check --manifest <manifest.json>
python apps/backend/scripts/adr0043_dbox_freeze_manifest.py body-hash --manifest <manifest.json>
python apps/backend/scripts/adr0043_dbox_freeze_manifest.py verify-seal --manifest <sealed.json>
pytest apps/backend/tests/scripts/test_adr0043_dbox_freeze_manifest.py -q
```

`check` exit 0 = seal-ready; exit 1 = not ready (JSON readiness report on stdout);
exit 2 = IO/parse error.

## Seal model

Hash covers only canonical `manifest_body`. The `seal` envelope holds `body_sha256`,
timestamps, and acknowledgments and is **not** included in the hash input.

## Non-authorization

Publishing this tooling does **not**: start D-BOX gates, modify production paper deploy,
import Phase-0 into OrderRouter, enable broker reads/orders, or seal the campaign
manifest. Manifest remains UNSEALED until readiness passes and owner countersigns.
