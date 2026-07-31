# Operational Cleanup — Temporary Workbench SSH Ingress

| Field | Value |
|-------|-------|
| Record ID | ADR0043-PH0-D-BOX-O34-ACQ-SSH-CLEANUP-001 |
| Security group | `sg-00dcdde89fa30e99a` (`workbench-paper-InstanceSecurityGroup-…`) |
| Temporary CIDR | `79.127.147.206/32` |
| Added | 2026-07-30 (restore for O34 selection/qualification) |
| Removed | 2026-07-30 after QUAL-001 |
| Result | **REVOKED** |
| Owner | Operator (Jay Wang / Cursor session) |

Post-revoke SSH CIDRs remaining (unchanged): `79.127.147.204/32`, `107.209.255.152/32`,
`109.204.74.42/32`, `18.88.0.132/32`.

*End of SSH-CLEANUP-001.*
