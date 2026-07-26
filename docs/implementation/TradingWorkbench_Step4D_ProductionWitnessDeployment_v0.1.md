# Step 4D — Production witness deployment and activation readiness

| Field | Value |
|---|---|
| Version | v0.1 (execution plan + evidence schema) |
| Date | 2026-07-26 |
| Status | Draft — provisioning gated on acceptance of ADR 0047 |
| Governs | ADR 0047 (production witness infrastructure), ADR 0046 (AWS SDK / KMS signer boundary) |
| Related | ADR 0045, ADR 0044, ADR 0032, ADR 0017, issue #522, Step 4C plan v0.1 |
| Depends on | `1816012` — Step 4C integration proof complete |

Step 4C created a temporary fixture and destroyed it. Step 4D creates a **permanent bucket, a standing
role and a registered host**, which the 4C plan states is ADR-class — hence ADR 0047, which this
document executes and does not restate. Where the two disagree, ADR 0047 governs.

## 1. What 4D establishes, and what it explicitly does not

**Establishes:** that the deployed forward-validation host, at an exact commit, under a least-privilege
standing role, can compose the real production witness against the real production KMS key and the real
production Object-Lock bucket; that it signs, publishes, reads back and verifies a synthetic receipt
byte-for-byte; and that every way of getting it wrong is refused rather than tolerated.

**Does not establish and does not authorize:** real ACTIONS ingestion, a first observation, opening the
forward window, starting a cooldown, clearing the operational hold, submitting a broker order, or
activating Account 4. Account 4 stays PAUSED, hold ACTIVE, session count 0, window NOT OPEN. Activation
requires a separate adjudication on the activation-readiness report §8 produces.

## 2. Coverage gap carried in from 4C — read before assuming this is a re-run

Step 4C ran **seven** in-process negative cases. Its plan listed fourteen; the remaining seven needed
conditions a least-privilege role cannot create for itself and were deferred. Four of the nine cases
Step 4D's scope requires were therefore **never exercised against real AWS**.

Evidence states are ADR 0047 (11): **PROVEN IN 4C** (observed against real AWS in a fixture that no
longer exists) · **PROVEN IN 4D** (observed during this deployment) · **EXPECTED** (a code-defined
prediction, not evidence). Nothing below is PROVEN IN 4D until the live run says so.

| Required by 4D | State entering 4D | How 4D reaches it |
|---|---|---|
| Wrong installed key | **PROVEN IN 4C** — `WITNESS_SIGNER_KEY_UNTRUSTED` | in-process, foreign SPKI |
| Alias / bare key id | **PROVEN IN 4C** — `WITNESS_SIGNER_NOT_SEPARATELY_CONTROLLED` | in-process |
| Wrong bucket or prefix | **PROVEN IN 4C** — `WITNESS_SINK_STORAGE_MISBOUND` | in-process |
| Wrong key ARN (valid grammar, real but different key) | **EXPECTED** | a **temporary** second KMS key, scheduled for deletion at teardown |
| Object Lock / versioning misconfigured | **EXPECTED** | a **temporary** bucket with neither, deleted at teardown |
| Missing IAM permission | **EXPECTED** | the standing role narrowed, one action at a time, then restored |
| KMS unavailable | **EXPECTED** | `AWS_ENDPOINT_URL_KMS` at an unroutable address for one invocation |
| S3 unavailable | **EXPECTED** | `AWS_ENDPOINT_URL_S3`, likewise |
| Unsupported platform | **PROVEN IN 4C** — real refusal on the Windows dev machine | `tests/validation/`, plus the new gate assertion |

If the endpoint-URL environment variables do not reach the adapters' clients — they are constructed with
an explicit `region_name` and `Config`, and this has not been verified against boto3 1.35+ on the host —
the fallback is to remove the security group's outbound HTTPS rule for the duration of one invocation.
That is coarser (it makes both services unavailable at once) and is recorded as such if used.

The alias/bare-key-id case is worth one note: the 4C plan **predicted** `WITNESS_KMS_KEY_ARN_INVALID`
and the run **observed** `WITNESS_SIGNER_NOT_SEPARATELY_CONTROLLED`, because the gate refuses on
separate-control grounds before the ARN grammar is reached. The observed code is the governed one and is
what 4D asserts. Predicting a code and recording the prediction is how the first idempotency case went
wrong; expectations here come from the 4C run, not from the 4C plan.

## 3. Issue #522 — what "formally contain" means here

Scope item 2 is discharged by three things, not one:

1. **Enforcement in the production gate.** `assert_supported_platform()` moves to the SDK-free
   `app/validation/witness_platform.py` and is asserted inside `enforce_production_witness`, right after
   the PRODUCTION-profile check and before the trust root, the factories or any AWS client (ADR 0047
   §7). It cannot live where it is today: `check_aws_sdk_isolation.sh` forbids `witness_enforcement`
   from importing `app/validation/aws/` at all.
2. **Host confirmation.** The evidence package records `platform.system`, `os.name`, kernel release and
   machine from the running host, observed rather than asserted.
3. **Interaction confirmation.** The preflight records `ssl.SSLContext.__module__` and
   `truststore_injected` **at the moment botocore clients are constructed**, and constructs a client
   under whatever state the deployed application actually produces. If the ADR-0017 injection is active
   on the host and client construction succeeds, that is the finding; if the injection is absent, the
   evidence says so and the containment rests on the platform boundary alone.

#522 remains open. 4D contains it; it does not fix it.

## 4. Execution order

Nothing in 1–3 runs before ADR 0047 is accepted. Nothing in 4 onward runs before the code in §5 is
merged to `main`.

1. **Provision the KMS key** — `ECC_NIST_P256`, `SIGN_VERIFY`, no alias, tagged. Record the ARN.
2. **Provision the bucket** — Object Lock at creation, then `COMPLIANCE`/2555 days, then `witness/` and
   `preflight/` established. ⚠ Irreversible from this point (ADR 0047 §2).
3. **Provision the role and instance profile** — the eight witness actions, prefix-scoped; SSM
   host-management attached separately. Run `iam simulate-principal-policy` over every action the
   adapters call, *and* over every action they must be denied, before anything uses it.
4. **Launch `ec2-forward-validation`** — t3.small, Amazon Linux, SSM-managed, no inbound, outbound HTTPS.
5. **Install Python 3.12 and the exact commit** into a clean virtualenv. (⚠ AL2023 ships 3.9; 3.11+ is a
   `dnf install`. The 4C host used 3.11 — 4D pins whatever the deployed application requires and records
   it.)
6. **Install the trust root** — export the DER SPKI, write it `root:root 0444` under a `0755` root-owned
   `/opt/workbench/witness`, and verify its fingerprint against `GetPublicKey` **independently** of the
   signer that will later be challenged against it.
7. **Install the governed configuration** — the `witness` block of ADR 0047, signer and sink factories
   pinned, full ARN, exact bucket/region/prefix, no credentials, no fallback.
8. **Run the preflight** (`preflight` prefix, synthetic tip only) — §6.
9. **Run the negative battery** — §7. Restore every temporarily-narrowed permission and delete every
   temporary resource, verifying restoration.
10. **Assemble, hash and copy off the evidence package** — §8.
11. **Issue the activation-readiness report.** No further action.

Steps 1–4 are recorded commands run by the operator, not opaque automation, and each resource identity
enters the evidence package as it is created — the same discipline 4C used, and the reason its
provisioning journal could be marked `OPERATOR_PROVISIONED`: the runner never holds `kms:CreateKey` or
`s3:CreateBucket`.

## 5. Code that must merge first

```
app/validation/witness_platform.py          NEW  SDK-free platform boundary
app/validation/aws/platform_guard.py        keeps capture_runtime; re-exports the boundary
app/validation/witness_enforcement.py       the gate asserts the platform after the profile check
app/validation/aws/production_witness.py    NEW  the 4D preflight harness (module entry point only)
tests/validation/test_witness_platform.py   NEW
tests/validation/aws/test_production_witness.py  NEW
```

`production_witness.py` is a separate module from `integration_proof.py` rather than a mode of it. 4C's
harness is a record of what was proven in a fixture that no longer exists; its strings say "4C", its
tags say `workbench-production=false`, and editing it to also mean production would make the 4C evidence
harder to read later. It carries the `--negatives-only` capability the 4C closure asked for, from the
start: the `preflight` verb fresh-attests, so it is single-use per prefix/sequence, and a second full run
would always diverge.

Subcommands: `install-key`, `preflight`, `negatives`, `verify` (read-back only, no write).

## 6. Preflight — the positive battery

Synthetic evidence only, `preflight/` prefix, one tip whose session date (`0001-01-01`) is not a trading
date and whose digests derive from a fixed marker string.

| # | Check | Property |
|---|---|---|
| P1 | Platform boundary passes | Linux/POSIX confirmed on the host, injection state recorded |
| P2 | Deployment identity | exact commit, runtime and dependency versions observed |
| P3 | Signer challenge | the installed key accepts what KMS produced; fingerprints equal |
| P4 | Storage identity | declared == reported == attested == publication, all four |
| P5 | Object Lock attested **from storage** | `enforced=true`, `COMPLIANCE`, 2555 days, source `STORAGE` |
| P6 | Sign → publish → read back | canonical bytes equal, local ↔ external |
| P7 | Idempotency | republishing the **stored receipt bytes** is a no-op; record unchanged; still exactly one object version |
| P8 | Divergence | a **fresh** attestation of the same tip is refused `EXTERNAL_WITNESS_DIVERGES` |
| P9 | Divergence | a different tip at the same sequence, likewise |

P7 and P8 are the distinction the first 4C run got wrong. Only stored bytes can be byte-identical:
ECDSA signing is randomised and `signed_at` advances, so re-attesting the same tip always produces a
different receipt and is correctly refused. P7 asserts the object version count from S3 rather than
inferring "no write" from the absence of an error.

## 7. Negative battery — all nine required cases

Each must produce a **governed refusal**, and the observed code is recorded whether or not it matches.
A case that does not refuse is recorded as `refused: false` and fails the run; it never aborts the
battery, because a run that stopped at the first surprise would hide the rest.

| # | Case | Expected | Reached by |
|---|---|---|---|
| N1 | Wrong installed key | `WITNESS_SIGNER_KEY_UNTRUSTED` | foreign DER SPKI |
| N2a | Wrong key ARN, **role may not use it** | `INDEPENDENT_WITNESS_UNAVAILABLE` | temporary second KMS key, policy unchanged |
| N2b | Wrong key ARN, **role may use it** | `WITNESS_SIGNER_KEY_UNTRUSTED` | same key, temporarily added to the policy |
| N3 | Alias ARN | `WITNESS_SIGNER_NOT_SEPARATELY_CONTROLLED` | in-process |
| N4 | Bare key id | `WITNESS_SIGNER_NOT_SEPARATELY_CONTROLLED` | in-process |
| N5 | KMS unavailable | `INDEPENDENT_WITNESS_UNAVAILABLE` | `AWS_ENDPOINT_URL_KMS` unroutable |
| N6 | S3 unavailable | `WITNESS_SINK_IMMUTABILITY_UNPROVEN` | `AWS_ENDPOINT_URL_S3` unroutable |
| N7 | Missing IAM permission | `INDEPENDENT_WITNESS_UNAVAILABLE` (`kms:Sign`) / `WITNESS_SINK_IMMUTABILITY_UNPROVEN` (config reads) | role narrowed, then restored |
| N8 | Wrong bucket **or** wrong prefix declared | `WITNESS_SINK_STORAGE_MISBOUND` | declared identity ≠ publication identity |
| N9 | Object Lock / versioning misconfigured | `WITNESS_SINK_NOT_IMMUTABLE` | temporary unlocked bucket |
| N10 | Unsupported platform | `AWS_WITNESS_PLATFORM_UNSUPPORTED` | off-host, and by the new gate assertion |

**N2 splits in two, and running only one of them would prove the wrong thing.** With the policy
unchanged, a foreign ARN is refused because the role cannot reach that key — which demonstrates the IAM
scoping and says nothing about the trust root. With the key temporarily added to the policy, the same
ARN is refused because the SPKI it returns is not the installed one — which demonstrates the trust root
and says nothing about IAM. Both properties are load-bearing and each hides the other, so the battery
records both and the harness forces neither to a single expected code.

N5–N7 are the cases where the expected code is a *prediction* rather than an observation, because 4C
never ran them. The battery records what actually happens; a mismatch between prediction and observation
is a finding to adjudicate, not a failure to suppress — and if a refusal code turns out to be wrong or
unhelpfully generic, that is exactly the kind of defect this step exists to surface. The harness fails a
run only on a case that was **not refused**; a case refused with an unexpected code is listed under
`unmatched_codes` for adjudication.

⚠ One property the harness deliberately cannot assert: **the S3 object-version count** after the
idempotency case. Reading it needs `s3:ListBucketVersions`, which the eight-action contract withholds,
and widening a standing role to make a check convenient is the wrong trade. The version count is
captured operator-side and enters the package as operator evidence — the same split 4C used.

Every temporary resource and every narrowed permission is restored and **verified restored** before the
evidence package is sealed. The role's effective permissions are captured before and after.

## 8. Evidence package

One JSON bundle assembled on the host, hashed, and copied off before the step is called complete.

```jsonc
{
  "step": "4D",
  "commit": "<exact deployed commit>",
  "started_at": "<ISO-8601 UTC>", "completed_at": "...",
  "platform": { /* RuntimeAttestation: system, release, machine, os_name, python, openssl,
                   ssl_context_module, truststore_injected, boto3/botocore, instance identity */ },
  "host": { "instance_id": "...", "instance_type": "t3.small", "image_id": "...",
            "availability_zone": "...", "name_tag": "ec2-forward-validation" },
  "dependencies": { /* the installed distribution set, name==version */ },
  "iam": { "role_arn": "...", "instance_profile_arn": "...",
           "witness_policy": { /* the inline policy document, verbatim */ },
           "attached_policies": [ "AmazonSSMManagedInstanceCore" ],
           "simulation": [ { "action": "...", "resource": "...", "decision": "allowed|explicitDeny|implicitDeny" } ] },
  "kms": { "key_arn": "...", "key_spec": "ECC_NIST_P256", "key_usage": "SIGN_VERIFY",
           "signing_algorithms": ["ECDSA_SHA_256"], "public_key_sha256": "..." },
  "s3":  { "bucket": "...", "region": "...", "witness_prefix": "witness",
           "preflight_prefix": "preflight", "versioning": "Enabled",
           "object_lock": { "ObjectLockEnabled": "Enabled",
                            "Rule": { "DefaultRetention": { "Mode": "COMPLIANCE", "Days": 2555 } } },
           "witness_prefix_object_count": 0 },
  "installed_key": { "path": "...", "sha256": "...", "owner_uid": 0, "owner_gid": 0, "mode": "0444",
                     "parent_mode": "0755", "symlinks_on_path": false,
                     "verified_against_kms": true },
  "config": { /* the governed witness block, option VALUES elided except identities and ARNs */ },
  "preflight": [ { "check": "P1", "passed": true, "detail": "..." } ],
  "witness_evidence": { /* enforce_production_witness evidence, verbatim */ },
  "witnessed_tip": { "sequence": 1, "session_date": "0001-01-01", "commit_sha256": "...", "anchor_sha256": "..." },
  "receipt": { /* the complete protocol-v2 SignedReceipt */ },
  "readback": { "canonical_equal": true, "s3_key": "...", "version_id": "...", "versions": 1 },
  "negative_cases": [ { "case": "N1", "expected_code": "...", "observed_code": "...",
                        "refused": true, "matched": true, "detail": "..." } ],
  "restoration": { "temporary_resources_removed": [...], "permissions_restored": true,
                   "policy_before_sha256": "...", "policy_after_sha256": "..." },
  "account4": { "strategy_status": "IDLE", "operational_hold": "ACTIVE", "hold_rev": 2,
                "session_count": 0, "window_open": false, "cooldown_started": false },
  "outcome": "PASS | FAIL",
  "findings": [ "..." ]
}
```

The package is hashed with SHA-256 over the serialized bundle, the digest is recorded separately from
the bundle, and both are copied off the host and **re-hashed independently off-host** — as 4C's evidence
was — so the recorded digest is not merely the one the producing machine claimed.

`account4` is read-only, taken from the live box, and is present because the completion gate asserts it.
Its presence in the package is not an authorization to change any of those values.

## 9. Completion gate

Step 4D is complete only when all of the following hold. Any failed or inconclusive item blocks
completion; none may be waived by a subsequent run without recording why.

- The host is healthy and reproducible from recorded commands.
- P1–P9 pass.
- N1–N10 all refuse, with observed codes recorded and any prediction mismatch adjudicated.
- Every temporary resource is removed and every narrowed permission verified restored.
- The evidence package is assembled, hashed, copied off-host and independently re-hashed.
- Every case in the package carries an evidence state per ADR 0047 (11), and **no case is labelled
  PROVEN IN 4D on the strength of a prediction**. A case that never executed stays EXPECTED and is named
  as an uncovered requirement in the activation-readiness report rather than counted as a pass.
- No unresolved deployment finding remains.
- Account 4 PAUSED · hold ACTIVE · session count 0 · window NOT OPEN · cooldown NOT STARTED.

The activation-readiness report §4 step 11 produces must state the three counts separately — PROVEN IN
4D, PROVEN IN 4C only, and EXPECTED — and must not aggregate them into a single "all negative cases
pass". A reader deciding whether to activate Account 4 needs to know which refusals have actually been
seen on the production boundary and which are still code reading.

## 10. Out of scope

- Fixing issue #522 (contained, per §3 and ADR 0047 §8).
- Any change to ADR-0017 TLS behaviour.
- The four open pre-window prerequisites (authoritative ACTIONS ingest, post-ingest tolerance
  revalidation, bound per-action evidence payload, `_stable_value` dict canonicalization).
- Anything touching Account 4 beyond the read-only state capture in §8.
- Cleanup of the Step 4C bucket `workbench-step4c-proof-20260726`, whose locked object cannot be removed
  before 2026-07-27T20:17:26Z. Tracked separately.
