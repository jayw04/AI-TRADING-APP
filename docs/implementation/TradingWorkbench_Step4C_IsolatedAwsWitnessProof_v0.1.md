# Step 4C — Isolated AWS Witness Integration Proof

| Field | Value |
|---|---|
| Version | v0.1 (execution plan + evidence schema) |
| Date | 2026-07-26 |
| Status | Draft — one open input (retention), see §5 |
| Governs | ADR 0046 (AWS SDK dependency and the KMS witness-signer boundary) |
| Related | ADR 0045 (algorithm-qualified witness receipts), ADR 0017 (OS trust store), issue #522 |
| Depends on | `28a1009` — ADR 0046 `295c817`, Step 4A `c4f0790`, Step 4B `3f41172`, test isolation `28a1009` |

Not an ADR. Provisioning here introduces no new architecture and no persistent operational policy — it
creates a temporary integration fixture and destroys it. If that changes (a permanent bucket, a standing
role, a registered host), that is an ADR and this document stops being sufficient.

## 1. What this proves, and what it does not

Steps 4A and 4B are complete and merged: the KMS signer and the S3 Object-Lock sink exist, are
CI-policed, and are proven against `botocore.stub.Stubber`. Stubs prove the *logic*. They cannot prove
that the code works against the real service — that the instance-role credential chain resolves, that
`GetPublicKey` returns DER the installed key matches, that Object Lock actually refuses an overwrite,
that IAM denies what it is supposed to deny.

**Proves:** one synthetic witnessed tip, end to end, against real KMS and real S3, under a
least-privilege instance role, on a Linux host resembling the eventual deployment boundary.

**Does not prove and does not authorise:** deployment of `ec2-forward-validation`, real ACTIONS
ingestion, opening the forward window, starting a cooldown, a first observation, or anything touching
Account 4. The temporary host is an integration test fixture, not a deployment.

## 2. The platform boundary is enforced, not documented

Step 4C runs on Linux/POSIX only. The guard (`app/validation/aws/platform_guard.py`) refuses anything
else with **`AWS_WITNESS_PLATFORM_UNSUPPORTED`**, *before* any client is constructed and *before*
anything is provisioned.

Two reasons it is a hard gate:

- **Correctness of the proof.** WSL would show the Python runs on a Linux kernel. It would not exercise
  the EC2 instance-role credential chain, instance metadata, deployment-file ownership, or VPC/DNS/TLS
  composition — which is most of what 4C exists to establish.
- **Failure shape.** Issue #522: ADR-0017's process-global `truststore.inject_into_ssl()` can make
  botocore client construction exhaust the recursion limit on Windows. An unenforced boundary would
  provision real AWS resources and *then* fail somewhere inside botocore, leaving half-built
  infrastructure and an unreadable error.

The guard lives in the harness, **not** in `KmsAnchorSigner` or `S3ObjectLockAnchorSink`. The adapters
stay independently constructible and unit-testable on any platform; production composition states where
they are authorised to run. This is an explicit platform boundary for this workstream — **not** a
finding that the Windows behaviour is acceptable. That remains open in issue #522.

## 3. Architecture

```
Temporary EC2 integration runner  (Amazon Linux, SSM-managed, no inbound)
        |
        |-- instance profile: Step4CIntegrationRunner
        |     |-- Step4CWitnessProof  (inline) — the EIGHT witness actions:
        |     |     |-- kms:GetPublicKey          on the one key ARN
        |     |     |-- kms:Sign                  on the one key ARN
        |     |     |-- s3:PutObject              on the one bucket/prefix
        |     |     |-- s3:GetObject              on the one bucket/prefix
        |     |     |-- s3:ListBucket             on the one bucket, s3:prefix-conditioned
        |     |     |-- s3:GetBucketVersioning    on the one bucket
        |     |     |-- s3:GetBucketObjectLockConfiguration
        |     |     `-- s3:GetBucketLocation      on the one bucket
        |     `-- AmazonSSMManagedInstanceCore (attached) — host management, SEPARATE and
        |           excluded from the witness-authority analysis
        |
        |-- dedicated NON-PRODUCTION KMS key   (ECC_NIST_P256, SIGN_VERIFY)
        `-- dedicated S3 bucket                (versioning + Object Lock at creation)
```

Deliberately **absent** from the role: `kms:*`, `s3:DeleteObject`,
`s3:PutBucketObjectLockConfiguration`, `s3:BypassGovernanceRetention`, and any wildcard resource. The
runner must be unable to remove a tip, weaken the lock, or override retention — that inability is part
of what the proof demonstrates.

> **`s3:GetBucketLocation` was added after the first run refused (2026-07-26).** This document and
> ADR 0046 both originally specified SEVEN actions. The real integration run was denied at
> `build_s3_object_lock_sink`, which calls `GetBucketLocation` to verify the configured region against
> the bucket's actual region — the "two sources of truth must not disagree" check. The permission
> contract, not the adapter, was incomplete: `Stubber` cannot enforce IAM, so Steps 4A and 4B passed
> while carrying a requirement the deployment would have been denied. **That refusal is retained as a
> successful finding of the least-privilege proof, not as a failure** — finding it here is precisely
> why an integration proof exists. Full IAM simulation across every adapter call confirmed this was the
> only gap.

No access to: Alpaca or any broker, production databases, Account 4, ACTIONS data, existing witness
buckets, or existing application secrets.

**Not `ec2-paper`.** Isolation must be structural, not contingent on Account 4 happening to be paused.
Running 4C on the application host would mix an experimental proof with a live environment, require
adding KMS/S3 permissions to the application instance role, blur the evidence with operational logs, and
make teardown ambiguous.

## 4. Execution order

1. Create the KMS key and the S3 bucket (§5 — bucket creation is irreversible in the retention sense).
2. Create the instance profile and role with exactly the eight witness actions above, plus the separate SSM host-management policy.
3. Launch the temporary EC2 instance: SSM-managed, security group outbound HTTPS only, no inbound.
4. Install the exact tested commit into a clean virtualenv on the host.
5. Export the KMS public key (DER SPKI) and install it under production ownership/mode rules.
6. Run the platform + runtime preflight (`assert_supported_platform`, `capture_runtime`).
7. Run the real `enforce_production_witness` composition against the installed key.
8. Witness one synthetic tip; publish to S3.
9. Read back and verify canonical equality, local ↔ external.
10. Exercise every negative case in §7.
11. Capture the evidence bundle (§6) and copy it off the host.
12. Terminate the instance and the role. Retain KMS/S3 per §5.

Steps 1–3 are recorded commands, not opaque automation: each resource identity goes into the evidence
bundle as it is created.

## 5. ⚠ OPEN INPUT — Object Lock retention mode and duration

**This is the one decision the plan cannot make for itself, and it is set at bucket creation.**

Under `COMPLIANCE`, retention **cannot be shortened or bypassed by anyone, including the root account**.
Objects are undeletable until expiry, and a bucket containing them cannot be emptied or deleted. Choose
wrong and the resources persist for the full period with no remedy.

| Option | Proves | Cleanup |
|---|---|---|
| **COMPLIANCE, 1 day** (recommended) | Real production mode; genuine write-once | Bucket + objects removable after ~24h |
| GOVERNANCE, 1 day | Write-once *for the least-privilege role* (which lacks bypass) | Admin can force-delete early |
| COMPLIANCE, 30+ days | Production-like durability | Pinned for the whole period, no early teardown |

Recommendation: **COMPLIANCE, 1 day** — it exercises the mode the sink tests assert
(`ObjectLockEnabled=Enabled`, `Mode=COMPLIANCE`) while bounding the window in which nothing can be
cleaned up. The harness refuses to provision without an explicit retention argument; there is no default,
precisely so this cannot be decided by omission.

**Teardown consequence to accept up front:** whatever is chosen, the bucket outlives the EC2 instance.
Step 4C teardown terminates the *runner*; bucket and key removal is a later, separate act.

## 6. Evidence schema

One JSON bundle, written on the host and copied off before termination.

```jsonc
{
  "step": "4C",
  "commit": "<exact commit the harness ran from>",
  "started_at": "<ISO-8601 UTC>",            // caller-supplied, as elsewhere in the validation code
  "platform": {                               // RuntimeAttestation.to_open_provenance()
    "system": "Linux", "release": "...", "machine": "x86_64", "os_name": "posix",
    "python_version": "...", "openssl_version": "...",
    "ssl_context_module": "ssl", "truststore_injected": false,
    "boto3_version": "...", "botocore_version": "...",
    "instance_identity": { "instanceId": "...", "imageId": "...", "region": "...",
                           "instanceType": "...", "accountId": "..." }
  },
  "resources": {
    "kms_key_arn": "arn:aws:kms:...:key/<uuid>",
    "kms_key_spec": "ECC_NIST_P256",
    "s3_bucket": "...", "s3_prefix": "...", "s3_region": "...",
    "object_lock": { "enabled": "Enabled", "mode": "...", "retention": "..." },
    "versioning": "Enabled",
    "role_arn": "arn:aws:iam::...:role/workbench-step4c-integration"
  },
  "installed_key": {                          // the deployment-installed trust root
    "path": "...", "sha256": "...", "owner_uid": 0, "mode": "0444"
  },
  "preflight": { /* enforce_production_witness evidence, verbatim */ },
  "witnessed_tip": { "sequence": 1, "session_date": "...",
                     "commit_sha256": "...", "anchor_sha256": "..." },
  "receipt": { /* the complete protocol-v2 SignedReceipt */ },
  "readback": { "canonical_equal": true, "s3_key": "...", "version_id": "..." },
  "negative_cases": [ { "case": "...", "expected_code": "...",
                        "observed_code": "...", "refused": true } ],
  "outcome": "PASS | FAIL",
  "notes": "..."
}
```

Two properties this schema is written to preserve: every resource is named by **full identity** (ARNs,
not aliases), and the receipt is stored **whole**, so the bundle is independently verifiable later
without reconstructing anything from configuration that happened to be current.

## 7. Required negative proofs

Each must produce a **governed refusal**, and each refusal code is recorded in the bundle.

| # | Case | Expected |
|---|---|---|
| 1 | Wrong installed SPKI (key material ≠ KMS key) | `WITNESS_SIGNER_KEY_UNTRUSTED` |
| 2 | Wrong KMS ARN (valid grammar, different key) | `WITNESS_SIGNER_KEY_UNTRUSTED` |
| 3 | Alias ARN or bare key id | `WITNESS_KMS_KEY_ARN_INVALID` |
| 4 | Disabled / pending-deletion key | `INDEPENDENT_WITNESS_UNAVAILABLE` |
| 5 | `kms:Sign` denied | `INDEPENDENT_WITNESS_UNAVAILABLE` |
| 6 | Sink declared as a bucket it does not write through | `WITNESS_SINK_STORAGE_MISBOUND` |
| 7 | Versioning disabled | attestation `enforced=false` → `WITNESS_SINK_NOT_IMMUTABLE` |
| 8 | Object Lock absent / non-enforcing | attestation `enforced=false` → `WITNESS_SINK_NOT_IMMUTABLE` |
| 9 | Overwrite of an existing object | refused by `IfNoneMatch` + Object Lock |
| 10 | Divergent duplicate publication | `EXTERNAL_WITNESS_DIVERGES` |
| 11 | Republication of **the stored receipt bytes** | **no-op, no error, record unchanged** (the one positive in this table) |
| 11b | **Fresh re-attestation** of the same tip | `EXTERNAL_WITNESS_DIVERGES` |
| 12 | Configuration reads denied | `WITNESS_SINK_IMMUTABILITY_UNPROVEN` |
| 13 | KMS or S3 unavailable | `INDEPENDENT_WITNESS_UNAVAILABLE` |
| 14 | Execution on Windows / non-POSIX | `AWS_WITNESS_PLATFORM_UNSUPPORTED` |

Cases 11 and 11b are the distinction the first run got wrong. **Only the stored bytes can be
byte-identical**: ECDSA signing is randomised (a fresh `k` per signature) and `signed_at` advances, so
re-attesting the same tip with the same key produces a different receipt and is correctly refused as
divergent evidence. The idempotency case therefore reads the record back from the sink and republishes
exactly that — which is also the real-world shape, since `append_anchor` publishes externally *before*
writing the local line, so a crash between the two leaves the next run republishing a receipt the sink
already holds.

Cases 7, 8 and 12 need conditions the least-privilege role cannot itself create; they are exercised
against a second, deliberately-misconfigured bucket and by temporarily narrowing the role, both recorded
in the bundle. Case 14 is proven off-host — it is already covered by
`tests/validation/aws/test_platform_guard.py`, which exercises the **real** refusal on the Windows
developer machine.

## 8. Out of scope

- Any change to ADR-0017 TLS behaviour (issue #522 — deliberately not chosen here).
- Provisioning or registering `ec2-forward-validation`.
- Any use of Account 4, the production database, a broker, or real ACTIONS data.
- Retaining the temporary instance, its role, or its security group after §4 step 12.
