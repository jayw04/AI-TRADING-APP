# EVIDENCE-GAP ACQ — Temporary SSH Ingress Removal

| Field | Value |
|-------|-------|
| Record ID | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-SSH-CLEANUP-001 |
| Removed at (UTC) | 2026-07-31T01:41:00Z (approx) |
| Security group | `sg-00dcdde89fa30e99a` |
| Revoked CIDR | `79.127.147.206/32` (TCP/22) |
| Prior add rule | `sgr-07159645d4cea8175` (Stage 1 access restore) |
| Reason | Temporary operational access for ACQ Stages 1–4; not persistent admin policy |
| Evidence-scope impact | **None** — does not alter freeze, pins, or Stage 1–4 artifacts |
| Stage 4 secured merge | `1d95dbbb6d87cc810ea1f98e228e08298f6d23d8` (PR #579) |
| Remaining SSH /32 allows | `79.127.147.204/32`, `107.209.255.152/32`, `109.204.74.42/32`, `18.88.0.132/32` |

## Statement

Ingress `79.127.147.206/32` was revoked after Stage 3 refusal + Stage 4 qualification
artifacts were secured on `main`. Removal is operational hygiene only.

*End of ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-SSH-CLEANUP-001.*
