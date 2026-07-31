# O34 Independent Qualification Report — QUALIFIED

| Field | Value |
|-------|-------|
| Document ID | ADR0043-PH0-D-BOX-O34-ACQ-QUAL-001 |
| Authorization | ADR0043-PH0-D-BOX-O34-ACQ-QUAL-AUTH-001 **EFFECTIVE** |
| Outcome | **QUALIFIED** |
| Qualified at (UTC) | `2026-07-30T13:43:44Z` |
| Qualifier | `independent-qualifier-o34-acq-001` |
| Qualifier tool | `qualify_o34_archives.py` (separate from constructor) |
| Checks | **51 / 51 PASS** |
| Gate ready | **false** |
| Campaign reopen | **false** |
| D-WIRE | **BLOCKED** |

## Bound pins verified

| Pin | Value | Result |
|-----|-------|--------|
| Freeze body | `80dfd8ec…` | PASS |
| Sqlite snapshot | `26bae1f5…` (unchanged) | PASS |
| Construction merge | `5def382…` | PASS |
| O3 | `53b3310c…` / 164706 B / n=292 | PASS |
| O4-A | `3ba73e61…` / 190328 B / n=287 | PASS |
| O4-B | `e349f494…` / 260426 B / n=286 fills=286 | PASS |

## Required proofs

| Proof | Result |
|-------|--------|
| Archive hashes, sizes, schemas, counts | PASS |
| Source-to-archive row lineage (`orders.id` ↔ `ord:`) | PASS |
| 292 source orders → 292 O3 rows | PASS |
| Five O4-A `MISSING_CUTOFF` exclusions | PASS (`ord:1244,1250,1252,1256,1259`) |
| Six O4-B `O4B_INCOMPLETE` exclusions | PASS (same five + `ord:1384`) |
| No O4-A fill / terminal look-ahead | PASS |
| O4-A / O4-B separation | PASS |
| Dedup / unique-plan counts | PASS |
| O3 cluster count = 20 | PASS |
| No synthetic obs-a/obs-b/arc-1 IDs | PASS |
| No source change after snapshot | PASS (sqlite SHA match) |

## Note on informational `KOKU` scan hit

Blob substring scan reported `KOKU`. Investigation: empirical account-3 symbol/session
`session_id=koku|2026-07-13` in O3 — **not** WP7 hermetic fixture identity. Hard synthetic-ID
checks still PASS.

## Explicit non-effects

QUALIFIED does **not** authorize O3/O4 gate execution, campaign reopen, D-WIRE, broker
activity, canary, ENFORCE, caps, or limits-digest changes. Archives may only be named in a
later campaign scope + sealed successor freeze.

## Machine report

`docs/design/evidence/dbox_o34_acq_001/qualification/QUAL_001_report.json`

## SSH cleanup

Temporary SG ingress `79.127.147.206/32` on `sg-00dcdde89fa30e99a` **revoked** after
qualification (2026-07-30). Remaining operator CIDRs unchanged.

*End of ADR0043-PH0-D-BOX-O34-ACQ-QUAL-001.*
