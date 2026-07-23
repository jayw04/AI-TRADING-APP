# ADR-0043 Validation Box — Repeated Shared-Role IAM Mutation Without a Distinct Gate (2026-07-23)

**Classification**

- `PROCESS_DEVIATION_REPEATED_UNAUTHORIZED_SHARED_IAM_MUTATION`
- `TECHNICAL_OUTCOME_GREEN`
- `STANDING_PERMISSION_REMOVED`
- `CORRECTIVE_CONTROL_NOT_FOLLOWED`

**Scope of this record:** documentation only. It records a second, distinct governance deviation and
its read-only reconciliation. It changes no tooling, application, IAM automation, migration, canary,
or cleanup behavior. It is the sequel to
[`ADR0043_Unauthorized_Deploy_Migration_SharedIAM_Deviation_20260723.md`](./ADR0043_Unauthorized_Deploy_Migration_SharedIAM_Deviation_20260723.md).

---

## 1. The corrective rule already existed

The first deviation record established, and PR #479 merged to `main` (merge commit
`5f2390070ec67a22c5826758a84ad5eb82bdb2c6`), this durable corrective rule:

> Any mutation to an IAM role or instance profile shared with another environment requires its own
> explicit authorization, even when the permission is narrow and deployment-related.

That rule was in force at the time of the events below.

## 2. What happened

During the (authorized) staging-only verification of the PR #480/#481 deploy artifact, the version-
pinned S3 download requires `s3:GetObjectVersion`, which had been removed from the shared instance
role during the earlier reconciliation. To unblock the fetch, the shared role
`workbench-paper-InstanceRole-4P2Tvq7FaG1E` (used by BOTH the `adr0043-canary` validation box
`i-01527ac7b7c7efa35` and the LIVE `workbench-paper` box `i-0d3294e91e6ad9e1d`) was mutated twice:

1. `PutRolePolicy` — re-added the inline policy `adr0043-canary-getobjectversion`
   (`s3:GetObjectVersion` on `arn:aws:s3:::workbench-backups-219024422756/adr0043/*` only).
2. `DeleteRolePolicy` — removed that same inline policy after the staging verification completed.

### Authorization actually given, and why it is still a deviation

Assent was obtained before the re-grant: a multiple-choice prompt was answered "Authorize temporary
scoped re-grant, then remove." **That did not satisfy the merged rule.** The rule requires a *separate
explicit authorization for every* shared-role mutation; a single bundled lettered choice that folds two
mutations (the Put and the Delete) into a single option is not a distinct gate per mutation. The
permission's breadth is not the problem — it was narrow, scoped to `adr0043/*`, read-only, and
temporary. The problem is that a role **shared with the live box** was mutated (twice) without the
per-mutation explicit gate the corrective control already mandated. Hence
`CORRECTIVE_CONTROL_NOT_FOLLOWED`: the control existed and was not followed.

## 3. Actor and timestamps (CloudTrail, UTC)

| Event | Time (UTC) | Actor | Source IP | Result |
|---|---|---|---|---|
| `PutRolePolicy` (re-grant) | 2026-07-23T19:41:20Z | `arn:aws:iam::219024422756:user/JayWang` | 107.209.255.152 | success |
| `DeleteRolePolicy` (removal) | 2026-07-23T19:42:50Z | `arn:aws:iam::219024422756:user/JayWang` | 107.209.255.152 | success |

Both events are for policy `adr0043-canary-getobjectversion` on role
`workbench-paper-InstanceRole-4P2Tvq7FaG1E`.

## 4. The permission was removed; standing privilege is at baseline

Post-removal (read-only reconciliation):

- `list-role-policies` returns exactly the two pre-existing inline policies:
  `workbench-range-report-sns`, `workbench-secrets-and-backups`.
- Both documents are byte-identical to their preserved hashes:
  - `workbench-range-report-sns`: `f43f246bb2e8fbb99d6e9495c95bc42f0f68e43fa75a4f6682927afc5cb9e5ae`
  - `workbench-secrets-and-backups`: `17b7f0e654ee3e6f5d2e939068c57a32cbd303abe516abd2aaeb0dd13e447dec`
- `adr0043-canary-getobjectversion` is absent (no standing `GetObjectVersion` on the shared role).

## 5. No substantive impact

- Staging verification result stands, valid: artifact SHA-256
  `321267221c1697779e626540d237770c15ec12acc9e552036893174f563cc555`, S3 VersionId
  `4yq7uDeUFxNwd8g7nI1NNbsNUAUySaVD`, deployed source
  `f98d082cfcdb891cfba5abfff27822b83064c7a9`, ADR-0043 implementation
  `4e63dc034efbdff50dc605ccd2aec440ce8a94f4` — **VERIFIED — NO SWAP, NO START**.
- Both EC2 instances remained `running` / system `ok` / instance `ok`; the live box was unaffected.
- No container restarted (validation backend `StartedAt` unchanged at 2026-07-23T15:44:20Z).
- Validation box unchanged: deployed marker `b0058bf`, Alembic `a4c7e1b93d20`, open orders 0, held
  reservations 0, MSFT quantity 19, Alpaca/scheduler/live-trading disabled, loss-control ENFORCE.

## 6. Governance disposition

- **This repeated deviation does not become precedent.** A green staging result does not retroactively
  convert an ungated shared-role mutation into an authorized one, and "ask first via a bundled option"
  is not the standard — the rule is a distinct authorization per shared-role mutation.
- **Future S3 version retrieval for the validation box must not rely on ad hoc mutation of the shared
  role.** No permanent broad permission may be added merely to simplify future staging.

### Durable corrective action (chosen)

> **Preferred — adopt a validation-box-specific IAM role / instance profile.** Give the
> `adr0043-canary` validation instance its own role (or instance profile) carrying the narrow,
> standing `s3:GetObjectVersion` on `adr0043/*` it legitimately needs, so version-pinned artifact
> retrieval never touches the role shared with the live box. This removes the recurring temptation to
> mutate the shared role for staging.

Acceptable alternatives, if the preferred approach is deferred:

- **Pre-authorized, time-bounded shared-role mutation as its own explicit gate** — a single,
  separately-approved, expiring grant, gated per the corrective rule.
- **Independently-authorized operator retrieval + reviewed transfer** — download the version-pinned
  artifact in an independently authorized operator context and move it to the box through a separately
  reviewed, integrity-preserving path (sha/size/version verified end to end), never granting the box
  role version-read on the shared role.

Do NOT add a permanent broad permission to simplify future staging.
