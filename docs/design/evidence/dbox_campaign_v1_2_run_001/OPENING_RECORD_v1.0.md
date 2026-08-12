# CAMPAIGN-001 v1.2 Opening Record

| Field | Value |
|-------|-------|
| Document ID | ADR0043-PH0-D-BOX-V12-OPENING-RECORD-001 |
| Campaign | ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.2 |
| Start ruling | ADR0043-PH0-D-BOX-START-002 **EFFECTIVE** |
| Freeze | FREEZE-MANIFEST-003 |
| Expected body SHA-256 | `b2e6090dfe26bd26fbf18a3eb1be02d7e69a49423559194b93e8a95d5d663270` |
| Opened at (UTC) | `2026-07-30T18:12:42Z` |
| Outcome | **PASS** |
| Execution authority | **AUTHORIZED_FOR_O3** |

## START-002 §4 controls

| # | Control | Pass |
|---|---------|------|
| 1 | verify-seal | **PASS** |
| 2 | body_hash_exact (`b2e6090d…`) | **PASS** |
| 3 | qualified_archive_hashes_sizes (O3/O4-A/O4-B) | **PASS** |
| 4 | ord:`<orders.id>` adapter probe | **PASS** |
| 5 | isolated-harness checkout clean | **PASS** |
| 6 | production `b0058bf` neither used nor modified | **PASS** |

## Preserved command outputs / hashes

| File | Role |
|------|------|
| `opening_verify_seal.json` | verify-seal stdout |
| `opening_body_hash.txt` | body-hash stdout |
| `opening_archive_hashes.json` | QUALIFIED archive hash/size checks |
| `opening_ord_probe.json` | ord: adapter probe |
| `opening_git_status.txt` | git status --porcelain |
| `opening_production_exclusion.json` | b0058bf unused/unmodified attestation |
| `opening_controls.json` | machine-readable rollup |

## Non-effects (unchanged)

O5 remains INCONCLUSIVE; D-WIRE remains blocked; no broker orders; no production imports;
no canary / ENFORCE / caps / July 24 limits-digest changes.

*End of opening record.*
