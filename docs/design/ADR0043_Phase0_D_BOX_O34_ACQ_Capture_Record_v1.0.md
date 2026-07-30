# O34 Construction-Start Snapshot Capture Record

| Field | Value |
|-------|-------|
| Record ID | ADR0043-PH0-D-BOX-O34-ACQ-CAPTURE-001 |
| Capture ID | `20260730T022316Z` |
| Captured at (UTC) | `2026-07-30T02:23:16Z` |
| Host | `ip-172-31-7-230` (ssh `workbench`) |
| Start ruling | ADR0043-PH0-D-BOX-O34-ACQ-START-001 (EFFECTIVE) |
| Start merge | `811a808b7122c12e5948b92947879d327ca8cc29` |
| Freeze body SHA-256 | `80dfd8ec6d90182cdeabaab2d1457720ca417bcd5cb1511b4dd9d77989951bb0` |
| Seal verify | **PASS** (local JCS body-hash match before capture) |
| Selection performed | **false** |
| Broker calls | **none** |
| All mandatory snapshots bound | **true** |
| Record selection permitted | **true** (bindings only — selection not yet started) |

## Pre-capture controls

1. Recorded freeze body hash `80dfd8ec…`  
2. Verified seal (body SHA-256 match, `manifest_status=SEALED`)  
3. Captured mutable sources without SQL SELECT / filter / join / row inspection  
4. Pre/post live sqlite hashes equal → capture process mutation **NONE**  
5. All required sources pinned exactly  

## Bound sources

| Source ID | Snapshot identity | Status |
|-----------|-------------------|--------|
| SRC-APP-AUDIT-PLAN-CKPT-TERM-001 | sqlite snapshot SHA-256 `26bae1f5b754c4ff80e031126674d1818ae4a9a90e4faa6b36820f2690278d5b` (22,515,712 bytes); live pre==post | **BOUND** |
| SRC-ACCT3-PAPER-PRIOR-AUTH-001 | shares sqlite snapshot `26bae1f5…` | **BOUND** |
| SRC-MKT-QUOTE-LAWFUL-001 | `bar_cache` manifest `b32e1187…` (70 files); `market_projection` manifest `c0148389…` (2 files); S3 Version IDs none for these roots | **BOUND** |
| SRC-GOV-GIT-IMMUTABLE-001 | governing refs / merges `a1f1fd3` (freeze), `811a808` (start) | **BOUND** |

## On-box capture root

`/opt/workbench/data/ops/adr0043_o34_acq_snapshots/20260730T022316Z/`

Git holds `capture_summary.json` + file manifests only (not the 22 MB sqlite binary).

## Disposition

Mandatory snapshot bindings **PASS**. Deterministic record selection may begin under O34-ACQ-START-001 + this capture record. Gate execution, D-WIRE, and HOLD remain unchanged.

*End of ADR0043-PH0-D-BOX-O34-ACQ-CAPTURE-001.*
