# ADR 0047 — Production witness infrastructure for forward validation

| Field | Value |
|---|---|
| Date | 2026-07-26 |
| Status | Accepted (2026-07-26) |
| Phase | Forward validation (Workstream B, Step 4D) — Account-4 critical path |
| Supersedes | — |
| Related | 0046 (AWS SDK dependency and the KMS witness-signer boundary), 0045 (algorithm-qualified witness receipts), 0032 (AWS EC2 paper stack deployment), 0044 (deployment lifecycle and fail-closed operational holds), 0017 (OS trust store), issue #522 |

## Context

ADR 0046 built the production signer and sink and confined them to `app/validation/aws/`. Step 4C then
ran them once against real KMS and real S3 on a temporary EC2 host and destroyed the fixture. Both were
deliberately scoped to *code* and to a *proof*: 4C's plan states in its opening paragraph that it
introduces "no persistent operational policy," and that if that changes — "a permanent bucket, a
standing role, a registered host" — the change is ADR-class and the plan stops being sufficient.

Step 4D creates exactly those three things. The forward-validation program they support is a year-plus
process: at least 252 sessions, at least 40 rebalances, a complete forward year, then a gate battery and
a separate activation adjudication. Every one of those sessions anchors its chain tip to an external
witness, and the entire value of the witness rests on properties that are decided once, at creation, and
cannot be revised afterwards. Object Lock retention is set when the bucket is made and, under
`COMPLIANCE`, cannot be shortened or bypassed by anyone including the account root. A KMS key's ARN is
the trust root the deployment installs and the receipt records; changing it is a discontinuity in the
evidence chain, not a configuration edit.

There is also an unresolved defect sitting directly on this path. Issue #522: ADR 0017's
`truststore.inject_into_ssl()` replaces `ssl.SSLContext` process-wide, and constructing a botocore
client under the resulting state can exhaust the recursion limit on Windows. Step 4C's owner ruling was
to proceed Linux-only, enforced by `app/validation/aws/platform_guard.py`. That guard sits in the 4C
harness path — and `check_aws_sdk_isolation.sh` forbids any module outside `app/validation/aws/` from
importing that package, so **the production witness gate cannot currently enforce the boundary it
depends on**. A deployment is where the boundary has to hold; a harness is not.

## Decision

A **dedicated, permanent witness boundary** is provisioned in AWS account `219024422756`, region
`us-east-1`, structurally separate from `ec2-paper`, and the platform boundary that protects it is moved
out of the AWS package so production composition can enforce it.

1. **One production KMS signing key**, `ECC_NIST_P256` / `SIGN_VERIFY`, usable only with
   `ECDSA_SHA_256`, identified everywhere by its **full immutable key ARN**. **No alias is created**,
   so no alias can later be configured; ADR 0046 (10) already refuses aliases and bare key ids, and
   creating none removes the temptation as well as the risk.

2. **One production S3 witness bucket**, created with **versioning enabled** and **Object Lock enabled
   at creation**, with a default retention of **`COMPLIANCE`, 2555 days (7 years)**.

   `COMPLIANCE` because a witness an operator can delete is not a witness; the mode is the only one
   under which the account root itself cannot remove a receipt. 2555 days because the evidence must
   outlive the program that produces it — a year-plus of sessions, a gate battery, an activation
   adjudication, and any later audit of that decision — and because it matches the horizon financial
   recordkeeping generally assumes. This is irreversible in both directions: nothing written to the
   bucket can be deleted for seven years, and the bucket itself cannot be removed while it holds a
   locked object.

3. **Two governed prefixes in that one bucket, and never one.**

   - `witness/` — the operational prefix. Real forward-validation chain tips only. **It stays empty
     until the first real observation**, which Step 4D does not authorize.
   - `preflight/` — synthetic evidence only. Deployment preflight receipts, including Step 4D's.

   The separation is load-bearing, not tidiness. `S3ObjectLockAnchorSink.read_all()` lists and parses
   *everything* under its configured prefix, so a synthetic tip published into `witness/` would become a
   permanent sequence-1 record that `verify_anchor_consistency` sees for the life of the chain — and
   under (2) it could never be removed. The sink binds to exactly one prefix through
   `publication_storage_identity()`, and the gate's four-identity equality check makes the binding
   structural: a preflight run and an operational run cannot reach each other's records.

4. **One standing instance role** carrying exactly the **eight witness actions** established by ADR
   0046's implementation-status correction, each scoped to the one key ARN and the one bucket, with the
   S3 object actions scoped to the two prefixes in (3) and `s3:ListBucket` conditioned on them:

   ```
   kms:GetPublicKey · kms:Sign
   s3:GetBucketLocation · s3:GetBucketVersioning · s3:GetBucketObjectLockConfiguration
   s3:ListBucket · s3:PutObject · s3:GetObject
   ```

   Deliberately absent, and required to stay absent: `kms:*`, `kms:ScheduleKeyDeletion`,
   `kms:DisableKey`, `s3:DeleteObject`, `s3:DeleteObjectVersion`,
   `s3:PutBucketObjectLockConfiguration`, `s3:PutBucketVersioning`, `s3:BypassGovernanceRetention`, and
   any wildcard resource. **Host management (`AmazonSSMManagedInstanceCore`) is a separate attached
   policy and is excluded from the witness-authority analysis** — the evidence package reports the two
   sets separately so an auditor can see that no host-management grant contributes witness authority.

5. **One registered host, `ec2-forward-validation`**: dedicated, always-on `t3.small`, Amazon Linux
   (x86_64), SSM-managed, **no inbound rules**, outbound HTTPS only, and **not `ec2-paper`**. Isolation
   from the live trading stack is structural, not contingent on Account 4 being paused. The host runs
   the forward-validation session and nothing else.

6. **The trust root is the deployment-installed DER SPKI**, at `/opt/workbench/witness/`, root-owned,
   mode `0444`, no symlink on any component of the path from the governed `trusted_root` down, and its
   fingerprint verified against `GetPublicKey` **independently** of the adapter that will later be
   challenged against it. ADR 0046 (13) already forbids KMS from being the trust root; this states where
   the trust root physically lives and under what ownership.

7. **The platform boundary moves out of the AWS package and into the gate.**
   `assert_supported_platform()` and the truststore-injection detector move to a new SDK-free module,
   `app/validation/witness_platform.py`; `app/validation/aws/platform_guard.py` keeps
   `capture_runtime()` (which reads SDK versions) and re-exports the boundary for its existing callers.
   **`enforce_production_witness` asserts the platform immediately after the PRODUCTION-profile check**,
   before the trust root is read, before either factory is resolved and before any AWS client can be
   constructed.

   The siting is deliberate on both sides. *After* the profile check, because a REFERENCE deployment
   constructs no AWS client and touches no POSIX-protected trust root — refusing it on platform grounds
   would be true but would replace the accurate finding with a misleading one. *In the gate* rather than
   in `session_composition.resolve_witness`, because the boundary belongs to every production witness
   rather than to one caller: the composition root, the readiness CLI and the Step 4D preflight all
   inherit it instead of each remembering to assert it. The adapters themselves stay unguarded and
   independently unit-testable on any platform, exactly as ADR 0046 and the 4C plan intend.

8. **Issue #522 is contained, not resolved.** The containment is: production composition refuses
   non-Linux/POSIX, and the deployment records the observed `ssl.SSLContext` module and injection state
   at client-construction time as evidence that the interaction does not arise on the registered host.
   The Windows behaviour remains an open defect. Nothing here declares it acceptable, and this ADR is
   not a closure of #522.

9. **Preflight before operation.** No forward-validation session may run on a host that has not passed
   the production witness preflight at the exact commit deployed there. The preflight uses synthetic
   evidence only, writes only to `preflight/`, and its refusal is a refusal to run — never a warning.

10. **This ADR authorizes infrastructure, not operations.** It does not authorize real ACTIONS
    ingestion, a first observation, opening the forward window, starting a cooldown, clearing the
    operational hold, or activating Account 4. Account 4 remains PAUSED with its hold ACTIVE and its
    session count at zero. Activation requires a separate adjudication on a separate report.

11. **Every claim about fail-closed behaviour carries an evidence state, and the three are not
    interchangeable.** Any artifact that asserts a refusal — the Step 4D evidence package, the
    activation-readiness report, this ADR, the plan — must label each one:

    | State | Means |
    |---|---|
    | **PROVEN IN 4C** | Observed against real AWS during the Step 4C integration proof, in a fixture that no longer exists. |
    | **PROVEN IN 4D** | Observed during this production deployment, against the production key, bucket, role and host. |
    | **EXPECTED / NOT YET OBSERVED** | A code-defined refusal awaiting live execution. A prediction. |

    **The activation-readiness report must not treat a predicted refusal code as equivalent to observed
    fail-closed behaviour**, and no artifact may describe an EXPECTED case as proven. The distinction is
    not pedantry: Step 4C's own first run recorded an idempotency case as passing that had never
    exercised idempotency at all, and the eight-action permission contract was written from a
    seven-action prediction that a real deployment would have been denied. Predictions here have already
    been wrong twice, in the two places where being wrong mattered most.

    A state may only advance by observation. A case whose observed code differs from its prediction is
    recorded with both and adjudicated; it does not become PROVEN by having refused, only by having
    refused as the governed contract says it should — and if the contract was wrong, the contract is
    what changes.

12. **Key and bucket lifecycle are operator-governed invariants, not IAM locks.** The production key
    must not be scheduled for deletion or disabled, and the bucket's Object Lock configuration must not
    be weakened, while the forward window is open or its evidence is live. These are enforced by the
    absence of the permissions in (4) for the runner, and by convention for the administrator —
    deliberately *not* by a key policy or bucket policy denying the account root, because a policy that
    locks the root out of its own key is an unrecoverable state and a worse failure than the one it
    prevents.

## Rationale

**Why `COMPLIANCE` and not `GOVERNANCE`.** `GOVERNANCE` gives the same write-once property against the
least-privilege role, which lacks `s3:BypassGovernanceRetention` — and for the *runner*, that is
identical protection. The difference is what the evidence proves to a reader who is not the operator. A
`GOVERNANCE` witness says "the runner could not alter this record"; a `COMPLIANCE` witness says "nobody
could." The entire reason the chain tip is anchored externally is that a local actor who can rewrite an
observation can recompute the whole unanchored suffix, and the external record is what makes that
detectable. If the same administrator who could rewrite the observations could also delete the receipt
that would expose it, the anchor adds materially less than it appears to. The cost of `COMPLIANCE` is
that a mistake is permanent — which is precisely why the mode and the duration are being ratified here
rather than passed as a command-line argument.

**Why seven years and not one.** Retention is per-object from write time against the bucket default, so
a 365-day retention means receipts written in the first month of the program become deletable while the
program is still running — the witness would decay from underneath the evidence it exists to protect.
The horizon has to cover the sessions, the gate battery, the activation adjudication, and a later audit
of that adjudication. Ten years was available and rejected as buying little beyond seven at the price of
three more years of an irreversible commitment. Storage is kilobytes; the commitment is the cost, and
the commitment is what is being sized.

**Why the preflight prefix exists at all.** The alternative — a second, throwaway bucket for preflight —
was seriously considered and rejected because it proves the wrong thing. What the preflight has to
establish is that *this* role, against *this* bucket, with *this* lock configuration and *this* key,
signs and publishes and reads back correctly. A preflight against a different bucket demonstrates that
some bucket works. The cost of keeping it in the production bucket is that synthetic receipts are
permanently retained under (2), which is acceptable: they are self-evidently synthetic (a `0001-01-01`
session date and digests derived from a fixed marker string), they are in a prefix no operational reader
ever lists, and a permanent record that the deployment was proven before it was trusted is closer to an
asset than a liability.

**Why the platform boundary has to move.** Step 4C sited the guard in the harness for a good reason: the
adapters keep their Stubber test suites running on Windows, and the 4C plan says explicitly that
"production composition states where they are authorised to run." The gap is that *production
composition then did not state it* — and could not, because the guard lives behind an import CI forbids
it from making. Duplicating the check outside the package would leave two definitions of the boundary to
drift apart; relaxing the invariant would trade a structural property for a convenience. Moving the
platform predicate to an SDK-free module leaves the AWS package holding only what genuinely needs the
SDK (`capture_runtime` reads `boto3.__version__`) and keeps one definition.

**Why the gate and not the composition root.** The first implementation of this decision put the
assertion in `session_composition.resolve_witness`, and an existing test caught the error: a
REFERENCE-profile deployment on Windows started refusing with `AWS_WITNESS_PLATFORM_UNSUPPORTED`
instead of `WITNESS_PROFILE_NOT_PRODUCTION`. Both statements were true, but the platform one is not the
*finding* — a reference deployment constructs no AWS client and reads no POSIX-protected trust root, so
telling its operator about a platform boundary buries the thing they need to know. Placing the
assertion inside `enforce_production_witness`, after the profile check, keeps the accurate refusal for
reference deployments and gives the boundary to every production caller at once: the composition root,
the readiness CLI and the Step 4D preflight all inherit it rather than each remembering it.

**Why a standing role rather than short-lived credentials.** Assumed-role sessions with a short TTL are
the stronger pattern in general, and were rejected here because the runner is a single unattended
process on a single dedicated host that must run once a day for a year without an operator present. An
instance role delivers rotating credentials through the ambient provider chain — which ADR 0046 (7)
already requires — with no credential material anywhere in configuration and no refresh mechanism to
fail at 4am. The authority being held is deliberately small enough that its continuity is not the risk:
the role can sign, write and read, and can destroy nothing.

**Why always-on rather than started per session.** A host started on a schedule adds a control plane —
whatever starts it — to the trust boundary, and makes "the production host is healthy and reproducible"
a claim about a machine that does not currently exist. The completion gate for this work asks for a
healthy, reproducible host; that is a property of a running one. The saving was roughly ten dollars a
month against a year-long program.

**Why not `ec2-paper`.** The same reasoning 4C applied to the temporary host applies more strongly to a
permanent one. Running forward validation on the live trading host would require adding KMS and S3
witness permissions to the instance role that also holds broker authority, mix validation evidence with
operational logs, and make the isolation of the forward program from Account 4 contingent on
configuration rather than on structure. ADR 0032's stack stays exactly as it is.

## Implementation notes

**Resource identities** (exact values recorded in the Step 4D evidence package as they are created):

```
region     us-east-1                       account 219024422756
KMS key    arn:aws:kms:us-east-1:219024422756:key/<uuid>     ECC_NIST_P256 / SIGN_VERIFY, no alias
bucket     workbench-witness-forward-validation-219024422756
           versioning=Enabled, ObjectLockEnabled=Enabled,
           DefaultRetention={Mode: COMPLIANCE, Days: 2555}
prefixes   witness/     operational — empty until the first real observation
           preflight/   synthetic only
role       workbench-forward-validation-witness  (+ instance profile of the same name)
           inline policy  WitnessBoundary          — the eight actions of Decision (4)
           attached       AmazonSSMManagedInstanceCore — host management, separate
host       ec2-forward-validation   t3.small, Amazon Linux, SSM-managed, no inbound
trust root /opt/workbench/witness/anchor_public_key.der   root:root 0444
           /opt/workbench/witness                          root:root 0755  (governed trusted_root)
```

**Governed configuration** (the `witness` block; PRODUCTION profile, per ADR 0046):

```json
{
  "profile": "PRODUCTION",
  "algorithm": "ECDSA_SHA_256_P256",
  "key_id": "arn:aws:kms:us-east-1:219024422756:key/<uuid>",
  "public_key_path": "/opt/workbench/witness/anchor_public_key.der",
  "trusted_root": "/opt/workbench/witness",
  "signer": {
    "factory": "app.validation.aws.kms_signer:build_kms_anchor_signer",
    "identity": "kms-witness-forward-validation",
    "options": { "key_arn": "arn:aws:kms:...", "witness_identity": "kms-witness-forward-validation" }
  },
  "sink": {
    "factory": "app.validation.aws.s3_sink:build_s3_object_lock_sink",
    "identity": "s3://workbench-witness-forward-validation-219024422756/witness",
    "options": { "bucket": "workbench-witness-forward-validation-219024422756",
                 "prefix": "witness", "region": "us-east-1" }
  }
}
```

The preflight configuration is byte-identical except that `sink.identity` and `sink.options.prefix`
name `preflight`. There is no fallback signer, no fallback sink, and no static credential: ADR 0046 (9)
and `assert_no_private_key_material` already refuse all three, and the preflight proves the refusals
fire against the real deployment rather than a stub.

**Module changes.**

```
apps/backend/app/validation/witness_platform.py       NEW — SDK-free platform boundary
                                                      assert_supported_platform, PlatformUnsupported,
                                                      PLATFORM_UNSUPPORTED, platform_is_supported,
                                                      truststore_is_injected
apps/backend/app/validation/aws/platform_guard.py     keeps RuntimeAttestation + capture_runtime;
                                                      re-exports the boundary for existing callers
apps/backend/app/validation/witness_enforcement.py    the gate asserts the platform after the profile
                                                      check and before everything else
apps/backend/app/validation/aws/production_witness.py NEW — the Step 4D preflight harness, run as a
                                                      module, never imported (as integration_proof.py)
```

`check_aws_sdk_isolation.sh` is unchanged and must stay passing: the new module imports no SDK, and
`witness_enforcement` imports `witness_platform`, not `app.validation.aws`. A test asserts that
importing `witness_platform` in a fresh interpreter pulls in neither the SDK nor
`app.validation.aws` — the structural property the whole move exists to obtain.

**Deletion protection.** The runner's inability to delete comes from Decision (4). The administrator's
restraint is a convention under Decision (12), supported by tags (`workbench-purpose`,
`workbench-production=true`) so an accidental cleanup script has something to key off. The account's
existing budget alarms cover the marginal cost, which is roughly one dollar a month for the key plus the
instance.

## Consequences

**Positive.** The forward-validation program acquires an external witness whose immutability is a
property of AWS rather than of operator discipline, and whose signing key the runner cannot exfiltrate,
disable or delete. The production composition root gains the platform boundary it was designed to have
and did not, closing a gap where a deployment could construct AWS clients on a platform with a known
recursion defect. The permission contract, the retention decision and the prefix separation become
reviewable artifacts rather than command-line arguments chosen at provisioning time.

**Negative.** A seven-year irreversible commitment is created on the strength of a design that has run
once, in a temporary fixture, for a program that has not recorded its first observation. If the bucket
layout is wrong, it is wrong for seven years. Synthetic preflight receipts are permanently retained.
A standing role is a standing authority: an actor who compromises the host can sign arbitrary tips and
write them to the witness for as long as the compromise lasts, and Object Lock will then make those
false records equally undeletable — immutability protects the record from revision, not from a
compromised writer, and the chain's own consistency check is what catches the difference. An always-on
host is an always-on patching and monitoring obligation on a machine that is not the live trading host
and will therefore get less attention. The KMS key cannot be rotated without changing the ARN, the
installed trust root and the identity every prior receipt records — so a rotation mid-program is an
evidence discontinuity requiring its own decision, not an operational task. And issue #522 stays open
with a boundary drawn around it, which means the next workstream that wants AWS on Windows inherits it
unimproved.

**Neutral.** The witness prefix stays empty for however long it takes to reach a first observation,
so the bucket's existence proves nothing about the program's progress. Marginal AWS cost is on the order
of fifteen to twenty dollars a month, dominated by the instance rather than by the witness.

## Alternatives considered (not chosen)

**`GOVERNANCE` retention.** Identical protection against the runner, with an administrative escape
hatch for a mistake. Rejected because the escape hatch belongs to the same principal whose potential
rewriting of the local chain the external anchor exists to detect. Reconsider if a real, non-hypothetical
need to remove a record arises — noting that reconsidering will not help, because the mode cannot be
changed on an existing bucket; it would mean a new bucket and a chain discontinuity.

**A separate preflight bucket.** Keeps synthetic receipts out of the production bucket entirely.
Rejected because it moves the preflight off the resource under test and proves a weaker statement.
Reconsider if preflight ever needs to exercise a *destructive* case that the production bucket must not
witness.

**Short-lived assumed-role credentials instead of a standing instance role.** Stronger in principle.
Rejected for an unattended daily process on a dedicated host, where the refresh path becomes a new
unattended failure mode and the authority in question can destroy nothing. Reconsider if the host ever
runs anything besides the forward-validation session.

**Running forward validation on `ec2-paper`.** No new host, no new cost. Rejected on the same structural
grounds 4C rejected it, which strengthen rather than weaken for a permanent deployment: it would put
witness permissions on the instance role that holds broker authority.

**Resolving issue #522 as part of this work.** Attractive — the defect is real and this is the workstream
that keeps stepping around it. Rejected as scope: the fix is to ADR-0017 TLS behaviour, process-global,
and affects every module in the backend rather than the witness path. Doing it inside an infrastructure
provisioning step would put a broad change to the platform's TLS handling behind a review whose subject
is an S3 bucket.

**A key policy or bucket policy denying deletion to the account root.** Would make Decision (12)
structural. Rejected because an AWS key policy that denies the root principal is an unrecoverable state,
and a bucket policy that denies configuration changes to everyone is nearly one; the failure it creates
is worse and less reversible than the failure it prevents.

## Re-evaluation triggers

- **The forward window is abandoned, restarted, or its governing preregistration is superseded** in a
  way that changes what the witness is attesting. The prefix layout and the retention horizon were sized
  to one specific program.
- **The production KMS key must be rotated, disabled, or replaced** for any reason — key compromise, an
  AWS change, or an operational error. This is an evidence discontinuity and needs its own decision
  before anything is provisioned to replace it.
- **A witness write is ever refused in operation** for a reason other than a genuine integrity stop
  (throttling that survives the retry budget, a regional outage, an IAM change made outside a PR). The
  bounded-retry trade ADR 0046 accepted is being paid, and the trade needs restating rather than
  loosening.
- **Issue #522 is fixed**, or reproduces on Linux. The first makes Decision (7)'s boundary narrower than
  it needs to be; the second makes it insufficient.
- **A second host, a second bucket, or a second key** is proposed for any reason. The isolation
  arguments here are about there being exactly one of each.
- **The seven-year retention is reached** with the evidence still live, or the program concludes and the
  bucket becomes an archive with no writer. Either is a different set of requirements from the one this
  ADR sizes.
