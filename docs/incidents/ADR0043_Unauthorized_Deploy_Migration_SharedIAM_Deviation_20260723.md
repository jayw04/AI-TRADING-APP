# ADR-0043 Validation Box — Process Deviation: Deploy, Migration, and Shared-Role IAM Change (2026-07-23)

**Classification**

- `PROCESS_DEVIATION_UNAUTHORIZED_DEPLOY_AND_MIGRATION`
- `TECHNICAL_OUTCOME_GREEN`
- `NO_OWNER_AUTHORIZED_EXCEPTION`

**Scope of this record:** documentation only. This file records a governance deviation and its
technical reconciliation. It changes no tooling, application, IAM automation, migration, canary, or
cleanup behavior.

---

## 1. Intended authorization boundary

The ADR-0043 validation box (`i-01527ac7b7c7efa35`, "adr0043-canary") was to be advanced only in
explicitly, individually authorized micro-steps. As of the authorization that preceded this
deviation, the standing boundary was:

- **Authorized (read-only / inert):** staging-only frozen-object verification — download the exact
  approved S3 object/version, verify size + SHA-256 + provenance marker, and STOP with **no swap and
  no start**.
- **On HOLD, each requiring its own explicit authorization:** `ADR0043_MIGRATION_AUTHORIZED=1`,
  application-tree swap, migration execution, Docker build/start of `b0058bf`, authoritative
  baseline capture, and Phase 0.
- The governance discipline for this environment requires that a **schema migration on the ENFORCE
  box** and any **mutation of an IAM role or instance profile shared with the live production box**
  each receive their own explicit, safety-scoped authorization — not a coarse or bundled assent.

## 2. Actions performed relative to that boundary

Three consequential actions were taken without the granular, safety-scoped authorization the
discipline requires for each:

1. **Deployment of `b0058bf`** — the reviewed-superset application tree was atomically swapped into
   `/opt/workbench/app` and the stack was built and started.
2. **Database migration to `a4c7e1b93d20`** (`reservation_position_anchor`) — executed by the
   backend startup command (`alembic upgrade head`) as a consequence of starting the new stack. This
   is **not reversible by a code-only rollback**.
3. **Shared-role inline-policy addition** — a new inline policy was added to the EC2 instance role
   **shared with the live production box** to grant S3 object-version read access needed by the
   version-pinned provisioner.

### Authorization actually given (for accuracy of the record)

Coarse assent was present for each action — a terse "authorized: go" for the deploy/migration and a
single-letter selection of the "add a tightly-scoped policy" option for the IAM change. **That
assent did not satisfy the required standard**: an irreversible ENFORCE-box migration and a mutation
of a role shared with live production each warranted their own explicit, itemized, safety-reviewed
authorization. No owner-authorized **exception** to the granular-gating rule was requested or
granted. The actions are therefore classified as a process deviation
(`PROCESS_DEVIATION_UNAUTHORIZED_DEPLOY_AND_MIGRATION`, `NO_OWNER_AUTHORIZED_EXCEPTION`).

## 3. Actor and timestamps (UTC)

| Event | Time (UTC) | Actor |
|---|---|---|
| Fresh pre-migration DB backup taken | 2026-07-23T15:37:43Z | operator (on box, backend stopped) |
| Shared-role inline policy **added** (`PutRolePolicy`) | 2026-07-23T15:33:33Z | `arn:aws:iam::219024422756:user/JayWang`, sourceIP 107.209.255.152 |
| Backend container created / stack started | 2026-07-23T15:44:17–15:44:20Z | operator (on box) |
| Migration `a4c7e1b93d20` applied | 2026-07-23T~15:44Z (backend startup) | backend `alembic upgrade head` |
| Shared-role inline policy **removed** (`DeleteRolePolicy`) | 2026-07-23 (see §7; `DELETE_EXIT=0`) | `arn:aws:iam::219024422756:user/JayWang` |

## 4. Exact IAM object

- **Role:** `workbench-paper-InstanceRole-4P2Tvq7FaG1E`
- **Instance profile (single):** `workbench-paper-InstanceProfile-NVMc7iHhQk3h`
- **Inline policy name:** `adr0043-canary-getobjectversion`
- **Action:** `s3:GetObjectVersion`
- **Resource:** `arn:aws:s3:::workbench-backups-219024422756/adr0043/*`
- No wildcard bucket, no `s3:*`, no `s3:GetObject`, no write action, no list action, no
  policy-management action. The grant was the minimum delta over the pre-existing standing
  permissions (which already allowed `s3:GetObject`/`s3:ListBucket` on the whole backups bucket but
  **not** version-specific reads).

### Both instances shared the role — confirmed

| Instance | Name | Role via profile |
|---|---|---|
| `i-01527ac7b7c7efa35` | adr0043-canary (validation) | `…InstanceProfile-NVMc7iHhQk3h` |
| `i-0d3294e91e6ad9e1d` | workbench-paper (**live production**) | `…InstanceProfile-NVMc7iHhQk3h` |

The temporary grant therefore conferred standing S3 version-read privilege on the **live** box as
well, for as long as it existed — the core reason the deviation matters despite its narrow scope.

## 5. Technical reconciliation findings (all green)

Independently verified, read-only, on the deployed validation box:

- Deploy marker: `deployed_repository_commit = b0058bf335628f8dbde09a93915314f3a1f7743b`,
  `adr0043_implementation_commit = ea6db6e6d5dc338196ffca9919a7a2e2643e1f6c`,
  `adr0043_governed_paths_match = true`; marker SHA-256
  `f0b0c30fb0445e99fb48e7e00b19b17be1e235ac33c71166eeaed68124423171`.
- Deployed source identity matches the frozen manifest: S3 VersionId `kex9gT31wufwtjYXZ6ZuczVY9JOMcBVh`,
  archive SHA-256 `5728813b9e534ecdabdc3df45e64bdb884c01b598c59a9d8ffddeb48d29043af`, 4,120,679 bytes.
- Alembic revision `a4c7e1b93d20`; migration column `risk_reservations.position_qty_at_reservation`
  present; SQLite `integrity_check = ok`.
- Book state: 0 open orders, 0 held reservations; positions unchanged (`symbol_id=2`, qty 19, long —
  MSFT canary artifact).
- Safety posture: `WORKBENCH_ALPACA_STARTUP_ENABLED=false` (startup log: `alpaca_startup_disabled`,
  no reconnect/websocket/stream activity), `WORKBENCH_SCHEDULER_ENABLED=false`,
  `WORKBENCH_LIVE_TRADING_ALLOWED=false`, `WORKBENCH_LOSS_CONTROL_MODE=ENFORCE`,
  `WORKBENCH_SESSION_BASELINE_ENFORCEMENT_ENABLED=true`. Health: `broker_registry=disabled`,
  `scheduler=disabled`, `circuit_breakers_clear=ok`.
- Both EC2 instances: `state=running`, system check `ok`, instance check `ok`. Live box unaffected.

## 6. Recovery evidence (preserved)

- **Fresh pre-migration DB backup:** `/home/ubuntu/adr0043_preflight_backup/workbench.sqlite.20260723T153743Z.bak`
  - SHA-256 `687638a538a2797b54cd2686e050312e2da2799d0710845bd1c1d407ccbc7e3f`, 1,953,792 bytes
  - `alembic_revision_at_backup = e7b3f2a9c4d1` (pre-migration), backup-file `integrity_check = ok`
- **Prior application tree:** `/opt/workbench/app.prev.906558`
  - prior marker SHA-256 `aba3ce9a9812bc7125dd612ca3d045bbdb7fa56634e5b0f149c856c1dcde127f`
    (`deployed_repository_commit = 80a6c043d750b8860bba2bb3bf21d282f6f2f600`)

Both are retained until the formal canary is complete and separately closed.

## 7. Policy removal and post-removal verification

- `aws iam delete-role-policy --role-name workbench-paper-InstanceRole-4P2Tvq7FaG1E --policy-name adr0043-canary-getobjectversion`
  → `DELETE_EXIT=0`.
- `list-role-policies` returns exactly the two pre-existing policies:
  `workbench-range-report-sns`, `workbench-secrets-and-backups`.
- Both pre-existing documents are byte-identical before and after removal (canonicalized SHA-256):
  - `workbench-range-report-sns`: `f43f246bb2e8fbb99d6e9495c95bc42f0f68e43fa75a4f6682927afc5cb9e5ae`
  - `workbench-secrets-and-backups`: `17b7f0e654ee3e6f5d2e939068c57a32cbd303abe516abd2aaeb0dd13e447dec`
- `get-role-policy` for `adr0043-canary-getobjectversion` now returns `NoSuchEntity` (confirmed absent).
- Both EC2 instances remain `running` / system `ok` / instance `ok`. Neither instance nor any
  container was restarted to validate the removal (validation backend `StartedAt` unchanged at
  2026-07-23T15:44:20Z). Validation identity/health unchanged post-removal (marker `b0058bf`,
  alembic `a4c7e1b93d20`, 0/0 orders/reservations, Alpaca + scheduler still disabled).
- The `DeleteRolePolicy` CloudTrail event is expected under actor `user/JayWang`; CloudTrail lookup
  indexing lags up to ~15 minutes after the call.

## 8. Governance disposition

- **This deviation does not become precedent.** A coarse or bundled "go" does not authorize an
  irreversible ENFORCE-box migration or a shared-role IAM mutation. The technical outcome being
  green does not retroactively convert the deviation into an authorized exception.

### Corrective governance rule

> Any mutation to an IAM role or instance profile shared with another environment requires its own
> explicit authorization, even when the permission is narrow and deployment-related.

This rule is recorded here as the durable corrective control arising from this deviation.
