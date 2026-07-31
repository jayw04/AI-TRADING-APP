# EVIDENCE-GAP Acquisition Opening Record — Stage 1 Snapshot Capture

| Field | Value |
|-------|-------|
| Record ID | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-OPENING-001 |
| Capture ID | `20260731T002055Z` |
| Captured at (UTC) | `2026-07-31T00:20:56Z` |
| Capture host | `ip-172-31-7-230` (ssh `workbench`, instance `i-084f47fe4e69192e9`) |
| Operator (box) | `ubuntu` |
| Start ruling | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-START-001 **EFFECTIVE** @ `eb9b660` |
| Freeze body SHA-256 | `af7693f4b97fd7d9d4ad642ab1af47e9e9a2a8cd680f6a26c4d01fee8d57967e` |
| Local seal verify | **PASS** (JCS body-hash match + `manifest_status=SEALED`) before capture |
| Production `b0058bf` | **UNUSED_CONFIRMED** (no modify; docker mutation none) |
| Selection / SQL SELECT | **false** |
| O5 anchor search | **false** |
| Recoverability inspection | **false** |
| Broker calls | **none** |
| All mandatory sources CAPTURED | **true** |
| Stage 2 permitted | **true** (inventory/recoverability only under frozen mappings) |

## Pre-capture controls

1. Verified sealed freeze body `af7693f4…`  
2. Confirmed isolated capture path (ssh workbench; local Trading Workbench stack not started)  
3. Confirmed production `b0058bf` unused/unmodified  
4. Captured immutable identities **before** any SELECT / join / recoverability / O5 search  

## Access restore note

SSH to `13.217.236.134:22` initially timed out. Operator public IP `79.127.147.206/32`
was missing from SG `sg-00dcdde89fa30e99a` (prior allows included `79.127.147.204/32`).
Ingress rule `sgr-07159645d4cea8175` added 2026-07-31; capture then proceeded.

## Stage 1 outcomes by source class

| Source ID | Outcome | Immutable identity |
|-----------|---------|-------------------|
| SRC-APP-AUDIT-PLAN-CKPT-TERM-001 | **CAPTURED** | sqlite snapshot SHA-256 `9e40a9ad2f0176acf884140594ddfa9e946e42d2723794f464bbb0efdc2d9db6` (22,683,648 bytes); live pre==post; mutation **NONE** |
| SRC-ACCT3-PAPER-PRIOR-AUTH-001 | **CAPTURED** | shares sqlite snapshot `9e40a9ad…` |
| SRC-MKT-QUOTE-LAWFUL-001 | **CAPTURED** | `bar_cache` manifest `b32e1187…` (70 files); `market_projection` manifest `c0148389…` (2 files); S3 Version IDs none |
| SRC-O5-TIERA-LOCATE-CORPUS-001 | **CAPTURED** | governing git `docs/design/evidence` tree manifest `1c209b06…` (50 files; operator worktree — on-box clone unavailable); **no** anchor content search |
| SRC-GOV-GIT-IMMUTABLE-001 | **CAPTURED** | governing refs: auth `29eece3…`, tip `853f5f6…`, seal `ec243c5…`, start `eb9b660…` |

## On-box capture root

`/opt/workbench/data/ops/adr0043_evgap_acq_snapshots/20260731T002055Z/`

Git holds `capture_summary.json` + file manifests under
`docs/design/evidence/dbox_evgap_acq_001/snapshots/20260731T002055Z/`
(not the sqlite binary).

## Explicit non-actions

- No SQL SELECT / candidate-row queries / joins / filters  
- No recoverability file-content evaluation  
- No market/quote content searches  
- No O5 Tier-A anchor searches  
- No broker activity; no production / canary / ENFORCE / caps / July 24 changes  
- Gates remain **CLOSED**; D-WIRE remains **BLOCKED**  

## Disposition

Mandatory Stage 1 captures **PASS**. Stage 2 inventory and recoverability inspection may
begin under sealed freeze mappings. Stage 2 must not modify frozen sources.

*End of ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-OPENING-001.*
