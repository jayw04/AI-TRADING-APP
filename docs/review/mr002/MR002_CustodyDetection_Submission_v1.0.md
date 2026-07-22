# MR-002 Custody Detection — Design and Implementation Submission v1.0

**Date:** 2026-07-22
**Authority:** Custody adjudication of 2026-07-22, which authorized a single work package:
*Custody Detection Design and Implementation Submission.*
**Disposition:** Produced and implemented. Submitted for adjudication. **Stop point reached.**

---

## 0. Governing statement carried forward

> In the current single-account AWS management-account topology, absolute prevention of
> deletion or policy removal is **not achievable**. The custody design therefore relies on
> rapid detection, independently immutable redundancy, verified recoverability, and explicit
> disclosure of the remaining single-principal risk.

Nothing in this submission claims deletion prevention.

---

## 1. Authorization boundaries — what was NOT done

Every prohibition in the authorization was honored:

| Prohibited | Status |
|---|---|
| Implement Requirement 7 / modify `require_binding()` | **NOT DONE** — no resolver exists; no order-path or evaluator code touched |
| Access validation, OOS, or sealed values | **NOT DONE** — the monitor reads registry metadata only |
| Begin P6–P13 | **NOT DONE** |
| Enable S3 Object Lock Compliance retention | **NOT DONE** — no Object Lock configuration was created |
| Create a new AWS member account | **NOT DONE** |
| Migrate or rebind the P5 image | **NOT DONE** — the bound index is untouched and byte-exact |
| Claim deletion prevention | **NOT DONE** — see §6 |
| Change `validation_authorization` | **NOT DONE** — remains `false` |
| Create a D3 event | **NOT DONE** |

Standing state unchanged: **P5 satisfied; custody requirements 1–6 satisfied; Requirement 7
SPECIFIED_NOT_IMPLEMENTED; validation partition closed; single opening unconsumed; OOS under
DENY; `validation_authorization = false`.**

---

## 2. Priority 1 — Audit and event detection

Before this work the account had **no CloudTrail trail at all** (`describe-trails` → `[]`).
Only 90-day console Event history existed, and EventBridge "API Call via CloudTrail" rules
require a trail. Deletion of the custody repository would have been **silent, and unprovable
after 90 days.**

### Implemented

| Resource | Identity |
|---|---|
| Trail | `mr002-custody-trail` — multi-region, **log-file validation enabled**, global service events included |
| Log bucket | `workbench-cloudtrail-219024422756` — versioned, SSE-S3 + bucket keys, all public access blocked, TLS-only bucket policy |
| ECR rule | `mr002-custody-ecr-mutation` |
| Control-plane rule | `mr002-custody-control-plane` |
| Notification | existing `arn:aws:sns:us-east-1:219024422756:workbench-paper-alarms` → `jay.w0416@gmail.com` |

The SNS topic policy was **extended, not replaced** — the pre-existing default statement that
the daily-digest publisher relies on is preserved verbatim, with one added statement allowing
`events.amazonaws.com` to publish under an `AWS:SourceAccount` condition.

### Monitored events

**ECR (scoped to the custody repository):** `BatchDeleteImage`, `DeleteRepository`,
`SetRepositoryPolicy`, `DeleteRepositoryPolicy`, `PutLifecyclePolicy`, `DeleteLifecyclePolicy`,
`PutImageTagMutability`, `PutImage`, `TagResource`, `UntagResource`.

Scoping uses an `$or` over `requestParameters.repositoryName` and a suffix match on
`requestParameters.resourceArn`, because `TagResource`/`UntagResource` carry the ARN rather
than the repository name. A name-only filter would have silently dropped those two events.

**Control plane (monitoring the monitoring):** CloudTrail `StopLogging`, `DeleteTrail`,
`UpdateTrail`, `PutEventSelectors`; EventBridge `DisableRule`, `DeleteRule`, `RemoveTargets`,
`PutRule`; SNS `SetTopicAttributes`, `DeleteTopic`, `RemovePermission`, `Unsubscribe`; S3
`DeleteBucket`, `PutBucketPolicy`, `DeleteBucketPolicy`, `PutBucketVersioning`,
`PutLifecycleConfiguration`; Lambda and Scheduler mutations to the monitor itself.

### Evidence — patterns proven, not assumed

`aws events test-event-pattern`, non-destructive:

| Test | Expected | Result |
|---|---|---|
| `BatchDeleteImage` on `mr002-evaluator-p5` | match | `True` |
| `BatchDeleteImage` on `rag-lab-prod-app` | no match | `False` |
| `StopLogging` on the custody trail | match | `True` |

The negative case matters: it shows the rule is scoped to the custody repository and will not
be drowned by unrelated `rag-lab-prod-app` deploy traffic.

**Known scope choice:** S3 events in the control-plane rule are *not* bucket-filtered, so
bucket-policy changes on unrelated buckets will alert. This errs toward over-alerting and is
deliberate.

---

## 3. Priority 2 — Scheduled custody-integrity monitor

**Source:** `scripts/mr002_custody/custody_monitor.py` (versioned in-repo, deployed as Lambda
`mr002-custody-monitor`, schedule `mr002-custody-monitor-daily`, `cron(0 13 * * ? *)`).

### Separation from Requirement 7 — stated in code, receipt, and function description

| Property | This monitor | Requirement 7 resolver |
|---|---|---|
| Purpose | Detect loss or drift | Block execution |
| Timing | Scheduled | Immediately before a window read |
| Failure effect | Alert + incident | Fail closed; no read |
| Registry unavailable | Report custody failure | Prevent execution |
| Satisfies Requirement 7 | **No** | Yes, once implemented and accepted |

Every receipt carries `satisfies_requirement_7: false`, `not_an_execution_gate: true`, and
`reads_sealed_data: false`, plus an explicit instruction that it **must not be consumed by
`require_binding()` as a cached substitute for live pre-read resolution.** A passing run
authorizes nothing.

### Checks performed

Bound-graph verification (index retrieves and hashes **byte-exact**; index media type; the
linux/amd64 manifest at its bound digest; `linux/amd64` platform; the configuration digest;
the BuildKit attestation descriptor accounted for; no extra descriptors) plus custody-control
verification (tag immutability still `IMMUTABLE`; **no lifecycle policy**; and the
**single-artifact repository invariant** — inventory reconciled against the expected OCI graph,
alerting on any foreign object, tagged or not).

### Evidence

- **Live run against the real registry: 11/11 checks PASS**, both locally and via the deployed
  Lambda. Receipts written to `s3://workbench-backups-219024422756/mr002/custody/receipts/`.
- **12/12 negative tests pass** (`scripts/mr002_custody/test_custody_monitor.py`), covering
  foreign objects, missing bound objects, tampered index bytes, stripped attestation, extra
  platform descriptor, lifecycle policy appearing, tag-mutability regression, config drift,
  repository absent, and **registry unavailable reported as custody failure rather than PASS.**
- Per the adjudication, drift testing was driven by **stubs, touching no AWS resource** — the
  custody repository was never probed.
- One test is deliberately inverted: a stub **cannot** forge bytes hashing to the bound index
  digest, since that would require a SHA-256 preimage. The residual failure is the property
  content addressing exists to provide, and is asserted as such rather than papered over.

### Least privilege

`MR002CustodyMonitorRole` is **read-only on the custody repository** (resource-scoped to that
one repository ARN), may write **only** under the receipts prefix, may publish **only** to the
existing topic. It holds no delete, no policy-write, and no ECR write permission of any kind.

---

## 4. Single-artifact repository invariant

Stated precisely, and now **mechanically enforced by detection**:

- the repository is dedicated exclusively to the P5-qualified image;
- the only permitted objects are the bound index and descriptors reachable from it
  (`60b15568…` → `a4e3ac54…` linux/amd64 → `6962e4a7…` config, plus attestation `b81cd073…`);
- no unrelated tags, indexes, manifests, attestations, or platform images may remain;
- **any foreign object is a custody nonconformance, even when untagged**;
- inventory is reconciled against the expected OCI graph on every run;
- testing occurs in a disposable repository — or, as here, against stubs — **never** in the
  custody repository.

This invariant does not make ECR undeletable. It makes repository-scoped controls precise
about what they protect. The earlier probe residue is exactly the condition
`test_foreign_object_breaks_single_artifact_invariant` now detects.

---

## 5. Operational custodian — proposal only, not applied

`scripts/mr002_custody/aws/PROPOSED-custody-role.json` defines an `MR002Custody` role with
MFA-conditioned assumption (`aws:MultiFactorAuthPresent`, one-hour `MultiFactorAuthAge`),
explicit denies preventing the custody role from weakening its own oversight or acting as a
deletion path, and a documented break-glass path.

**It is NOT applied.** It changes administrative access paths for the account's only human
principal, so it is submitted for adjudication.

It records truthfully:

- **Separation of duties: NOT_ACHIEVED — SINGLE-PRINCIPAL OPERATION.**
- What it achieves: separation of operating **context and credentials**, not of human authority.
- Break-glass is **detected, not blocked**, and cannot be blocked in a management account.

---

## 6. Control claims — allowed dispositions

| Control claim | Disposition |
|---|---|
| Tag immutability | **Enforced** (verified `IMMUTABLE`) |
| Ordinary-role deletion restriction | **Potentially enforceable** (proposed role, not applied) |
| Alerting on mutation/deletion attempts | **Enforceable — implemented and pattern-proven** |
| Recovery from ECR loss | **Not yet achieved** — no immutable redundant copy exists yet |
| Prevention against management-account root/admin | **Not achieved** |
| Irreversible ECR retention | **Not available in this topology** |

No IAM role or repository policy in this submission is described as making deletion impossible.

---

## 7. Cost

CloudTrail's first copy of management events is free; the trail's S3 footprint is small. Two
EventBridge rules and a once-daily 256 MB Lambda are negligible. The material new recurring
cost is trail log storage, which grows slowly and has no lifecycle policy — deliberately, since
expiry rules are what silently destroy evidence. **A retention decision for the *log* bucket
(not the custody artifact) is worth a future adjudication.**

---

## 8. What remains open

| Item | Status |
|---|---|
| Fail-closed image resolver (Requirement 7) | SPECIFIED_NOT_IMPLEMENTED — not authorized |
| Immutable recovery copy (Priority 3, Object Lock) | Not started — requires a separate retention decision |
| External failure domain copy (Priority 4) | Not started; laptop copy still **not** creditable as independent |
| Member-account migration + SCP (Priority 5) | Not started |
| Custody role application | Proposed, not applied |
| Named operational custodian | Unresolved |
| P6–P13, grant-readiness, D3 | Not started / not granted |

**Recovery from ECR loss is still unachieved.** Detection now tells you promptly if the bound
image is lost — it does not give you a way to get it back. Until Priority 3 or 4 lands, the
durable copies are ECR plus an uncredited laptop copy, both inside one failure domain.

---

## 9. Evidence index

| Artifact | Location |
|---|---|
| Monitor source | `scripts/mr002_custody/custody_monitor.py` |
| Negative tests (12/12) | `scripts/mr002_custody/test_custody_monitor.py` |
| Applied AWS configuration | `scripts/mr002_custody/aws/*.json` |
| Custody role proposal | `scripts/mr002_custody/aws/PROPOSED-custody-role.json` |
| Live receipts | `s3://workbench-backups-219024422756/mr002/custody/receipts/` |
| Durable audit log | `s3://workbench-cloudtrail-219024422756/AWSLogs/219024422756/` |

**Stop point reached. No further MR-002 work performed or authorized.**
