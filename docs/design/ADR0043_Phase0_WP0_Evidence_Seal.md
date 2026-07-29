# WP0 — Preserve and Seal Current Evidence

| Field | Value |
|-------|-------|
| Package | WP0 (AMD-12) |
| Controlling design | `ADR0043_Phase0_Controlling_Design_v1.1.md` |
| Status | **SPECIFIED — ready to execute** (no broker) |
| Owner | Jay Wang |
| Created | 2026-07-29 |

## Goal

Capture an immutable snapshot of the current Phase-0 / ADR-0043 evidence surface
**before** further structural implementation mutates paths, checkpoints, or digests.
Sealing is a precondition to later WPs and to any Phase-0 retry.

## In scope

- Inventory of evidence roots on the paper box and any laptop/S3 mirrors used for ADR-0043.
- Content hashing (SHA-256) of files and directory manifests.
- Written seal record with timestamp, operator, host id, git/deploy identity if available.
- Read-only verification that the seal can be re-checked.

## Out of scope

- Broker submission, canary execution, ENFORCE mode changes.
- Mutation of `risk_loss_control_state`, canary checkpoints, or account credentials.
- Opening or altering the sealed statistical test set (later WP).

## Suggested evidence roots (confirm on box at run time)

```
/opt/workbench/data/          # durable app data (selective; exclude secrets if policy requires)
/opt/workbench/app/DEPLOYED_BUILD_INFO.json
# plus any ADR-0043 canary/evidence paths already in use, e.g.:
#   /opt/workbench/data/ops/
#   paths cited by docs/adr/ADR-Review.md and canary runbooks
```

Do **not** seal live credential password files into a broadly shared archive; record
path + existence + mode only, or encrypt under owner key.

## Exit criteria (gate)

- [x] Inventory list committed or stored with the seal record (paths + roles). *(produced by `adr0043_wp0_seal.py build`)*
- [x] Manifest of relative path → SHA-256 for every included object. *(helper + unit test)*
- [x] Seal record JSON with: `sealed_at_utc`, `operator`, `host_id`,
      `controlling_design_id` (= `ADR0043-PH0-CTRL-001 v1.1`), `manifest_sha256`,
      `exclusions` (with reasons).
- [x] Independent re-verify command/script succeeds against the sealed store
      (checksum mismatch → fail closed). *(``verify`` subcommand)*
- [x] HOLD posture unchanged; no account 1–7 risk-state writes during the seal. *(box seal 20260729T161843Z: hash-only; PASS verify)*

## Box seal record (executed 2026-07-29)

| Field | Value |
|-------|-------|
| Seal dir | `/opt/workbench/data/ops/adr0043_wp0_seals/20260729T161843Z` |
| Verify | **PASS** (116 hashed entries) |
| Controlling design | ADR0043-PH0-CTRL-001 v1.1 |
| Roots | `DEPLOYED_BUILD_INFO.json`, `/opt/workbench/data/ops` |
| Exclusions | credentials/password basenames; nested `adr0043_wp0_seals`; bulk DB/parquet by default |

## Deliverables

1. `docs/design/ADR0043_Phase0_WP0_Seal_Record_TEMPLATE.json` (schema).
2. Offline helper: `apps/backend/scripts/adr0043_wp0_seal.py` — build + verify; never submits orders.

## Sequencing

WP0 **before** WP1–WP4 structural code that depends on frozen evidence identity.
CORR-06 remains after WP4 per controlling design §6.
