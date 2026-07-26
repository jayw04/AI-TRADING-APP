# ADR 0046 — AWS SDK dependency and the KMS witness-signer boundary

| Field | Value |
|---|---|
| Date | 2026-07-26 |
| Status | Draft |
| Phase | Forward validation (Workstream B, Step 4A) — Account-4 critical path |
| Supersedes | — |
| Related | 0045 (algorithm-qualified witness receipts), 0032 (AWS EC2 paper stack deployment), 0006 v2 (LLM in order path gated — the import-allowlist precedent), 0037 (EAD governance / order-path isolation), 0044 (deployment lifecycle and fail-closed holds) |

## Context

ADR 0045 made the witness receipt algorithm-qualified and pinned the governed production profile to
AWS KMS `ECC_NIST_P256` with `ECDSA_SHA_256`. The protocol, the verifier, the governed configuration
block and the production gate are all built and merged (PR #516). What does not exist is the thing they
were built for: **there is no production signer**. `enforce_production_witness` refuses
`Ed25519AnchorSigner` because the runner holds its private key, and the deployment has nothing else to
offer, so no governed session can run.

Closing that gap means the repository acquires an AWS SDK dependency for the first time. That is not a
routine `uv add`. The platform's trust story rests on a small, explicit set of external dependencies
(CLAUDE.md: "Adding a new external dependency requires an ADR"), on the order path importing nothing
that could reach a network service it does not need, and on CI invariants that make those properties
structural rather than a matter of reviewer diligence. An SDK that can sign, encrypt, read objects and
assume roles is exactly the kind of dependency that spreads if its placement is not decided up front.

There is also a recorded design intent pointing the other way, and it has to be dealt with explicitly
rather than quietly overridden. `witness_config.WitnessComponentConfig` documents the factory field as
resolving to adapters that "live outside this repository so that adding one does not add an external
dependency to the order-path image." That sentence describes a real and defensible architecture —
deployment-supplied adapters, zero SDK in the repo. Step 4A asks for an in-repo adapter at a named
module path, which is the opposite. One of the two has to give, and pretending the comment does not
exist would leave the next reader with a contradiction and no record of which way it was settled.

Finally, the failure mode this decision must design against is already on the record. The MR-002
recovery verifier imported `boto3` at module scope for an export path; the air-gapped custodian
procedure it was written for then failed at **import**, before any verification ran, on an interpreter
that had no SDK. "Credentials stripped" proves no AWS calls are made; it does not prove the code runs
where the SDK is absent. Where the SDK is imported, and whether it is imported at all in environments
that do not use it, is a correctness question, not a packaging preference.

## Decision

The AWS SDK is introduced as a **direct, explicit dependency of the backend distribution**, and every
AWS-touching implementation is confined to a **single new package, `app/validation/aws/`**, whose only
sanctioned entry point is a witness-signer factory named in the governed configuration.

1. **`boto3` is a direct core dependency**, declared in `apps/backend/pyproject.toml` alongside
   `anthropic`, with a comment naming this ADR and the allowlisted import location. It is not an
   optional extra and not accessed through a wrapper library.

2. **A new CI invariant, `check_aws_sdk_isolation.sh`, restricts `boto3`/`botocore` imports to
   `apps/backend/app/validation/aws/` and the tests for that package.** Any import elsewhere fails CI.
   Disabling the invariant requires an ADR.

3. **The adapter lives in-repo** at `app/validation/aws/kms_signer.py`, exporting exactly one public
   factory, `build_kms_anchor_signer`. This **revises** the "adapters live outside this repository"
   intent recorded in `witness_config.py`; that docstring is corrected as part of the implementation.

4. **No AWS SDK import may appear in the order path, strategy code, research code, or the reference
   protocol modules.** Specifically `app/services/order_router.py`, `app/risk/**`, `app/brokers/**`,
   `app/strategies/**`, `app/altdata/**`, and `app/validation/witness_protocol.py` /
   `app/validation/chain_witness.py` / `app/validation/chain_anchor.py` remain SDK-free.

5. **Dependency direction is one-way.** `app/validation/aws/**` imports the protocol
   (`witness_protocol`); the protocol, `chain_witness` and `chain_anchor` import nothing from
   `app/validation/aws/**`. The invariant enforces both directions.

6. **Construction only through production composition.** The signer is instantiated solely by
   `witness_enforcement._resolve_factory`, from the `witness.signer.factory` string in the governed
   deployment configuration. No runner, script, test helper or CLI constructs it directly, and the
   factory is never imported by name anywhere outside its own module and its tests.

7. **Credentials come from the ambient AWS provider chain** (the instance role on
   `ec2-forward-validation`). Static credentials in configuration remain refused by
   `assert_no_private_key_material`, which already rejects `access_key`, `credential(s)` and `secret*`
   option names. **Region is derived from the pinned key ARN**, so region and key cannot disagree; no
   environment-variable region fallback is consulted.

8. **Every AWS failure fails closed, with bounded effort.** The client is constructed with explicit
   timeouts and a bounded retry policy (standard mode, at most 3 attempts). Credential errors, network
   errors, throttling that survives the retry budget, KMS service errors, key-state errors (disabled,
   pending deletion) and malformed responses all raise a `WitnessError` and become a governed refusal.
   Nothing is retried indefinitely and nothing degrades to a warning.

9. **There is no fallback of any kind.** Not to Ed25519, not to a local key, not to a cached or
   replayed signature, not to the reference signer. A signer that cannot sign is a refusal.

10. **The governed key identity is the full immutable key ARN**
    (`arn:aws:kms:<region>:<account>:key/<uuid>`). Aliases, bare key ids and ARNs without the `key/`
    resource are refused at construction, because an alias can be repointed at a different key without
    the configuration changing.

11. **`ECC_NIST_P256` with `ECDSA_SHA_256` only.** Any other key spec or signing algorithm — including
    the KMS Ed25519 specs — is refused, matching the single production algorithm ADR 0045 pins.

12. **Signing uses `MessageType=DIGEST` over exactly 32 bytes**, the SHA-256 of the canonical envelope
    produced by `build_witness_envelope`/`envelope_digest`. The adapter asserts the 32-byte length
    before the call; a digest of any other length is a refusal, never a truncation or a re-hash.

13. **`GetPublicKey` is called exactly once, at construction, and only as a cross-check.** Trust comes
    from the deployment-installed key file, never from KMS. The returned DER SPKI must equal the
    installed key bytes, and the returned `KeySpec`/`SigningAlgorithms` must be consistent with the
    pinned algorithm; any disagreement is a refusal. The response is held in memory for the life of the
    signer, never written to disk, and never used to construct a verifier.

14. **Returned KMS metadata is checked against the pinned identity.** The `KeyId` and
    `SigningAlgorithm` on the `Sign` response must match the pinned ARN and algorithm, and the receipt
    records the ARN **KMS returned**, not the configured string. A signer wired to the wrong key
    therefore produces a receipt that the existing signer challenge refuses.

15. **Least-privilege IAM for Step 4A is exactly two actions — `kms:Sign` and `kms:GetPublicKey` —
    scoped to the single pinned key ARN.** No `kms:*`, no wildcard resource, no S3 permissions.

16. **Tests use `botocore.stub.Stubber` (or an equivalent deterministic double) exclusively. The
    implementation PR performs no live AWS call**, creates no AWS resource, and requires no
    credentials to run the suite.

17. **The S3 Object-Lock sink is out of scope** and lands as a separate change under its own review
    (Step 4B). This ADR governs the signer only.

18. **This ADR authorizes code, not operations.** It does not authorize deployment, real ACTIONS
    ingestion, Account-4 use, opening the forward window, starting a cooldown, or a first observation.

ADR 0006 v2 and ADR 0037 constrain **where** this code may live and **what** it may import. Neither
authorizes AWS operations, and neither is weakened by this ADR.

## Rationale

**Why a direct dependency rather than an optional extra.** An optional extra keeps the SDK out of
environments that do not use it, which is genuinely attractive: only `ec2-forward-validation` ever
signs. It was rejected because the cost lands precisely where this platform can least afford it. An
optional dependency forces the import to be lazy and the module to behave differently depending on
whether the SDK happens to be installed — which is the exact shape of the MR-002 recovery-verifier
defect, where a module-scope `boto3` import made an air-gapped procedure fail at import on an
interpreter that had never had the SDK. Making the dependency unconditional means the module imports
the same way everywhere, the test suite exercises the real import, and "is boto3 present?" stops being
a runtime variable. The property we actually care about is *not* "the SDK is absent from the image" —
it is "no code outside one package can reach AWS", and a CI invariant enforces that far more reliably
than a packaging trick, because an extra can be installed by any deployment that wants it.

**Why this follows the `anthropic` precedent.** The platform already faces this exact problem with an
SDK that must exist but must not spread: `anthropic` is a core dependency, and
`check_no_llm_in_order_path.sh` polices its import locations (ADR 0006 v2). That pattern has held for
several phases. Introducing a second, different mechanism for the same class of problem would mean two
things to reason about and two ways to get it wrong. The invariant is the control; the dependency
declaration is just plumbing.

**Why in-repo, against the recorded intent.** `witness_config.py` argues for deployment-supplied
adapters so the repo never grows an SDK dependency. The argument is real, but its cost is that the
single most security-critical component in the witness chain — the thing that decides what gets signed,
with which key, over which bytes — would live somewhere it is never code-reviewed, never covered by the
test suite, never checked by a CI invariant, and never version-pinned with the code it must agree with.
An out-of-repo adapter that passes a 32-byte digest to `MessageType=RAW`, or that reports the
configured ARN rather than the returned one, would be caught by nothing until a signature failed to
verify in production. In-repo, all of that is reviewable and testable, and the deployment retains the
authority that mattered in the original design: the factory string still lives in governed
configuration, so a deployment that does not name the adapter does not get it. What moves in-repo is
the *implementation*; what stays in the deployment is the *decision to use it*.

**Why the region comes from the ARN.** Region as a separate option is a second source of truth for
something the ARN already states. A deployment that pins a `us-east-1` key and configures `us-west-2`
would build a client that cannot see the key, and the failure would surface as a not-found error rather
than as the configuration contradiction it is. Deriving it removes the class of mistake. Environment
variables are excluded for the same reason the witness block excludes caller arguments: an operator who
can set `AWS_DEFAULT_REGION` should not be able to change which endpoint the witness talks to.

**Why `GetPublicKey` is a cross-check and never a trust root.** R5e's central insight is that a
substituted signer must not be able to supply the key its own signatures are checked against. If the
adapter fetched the public key from KMS and handed it to the verifier, that circularity would be
restored through the back door: whoever controls the ARN controls both halves. So the installed file
remains the sole trust root, and the KMS response is compared *to* it. Calling `GetPublicKey` at all is
still worth doing — it converts "this ARN is wrong" from a signature failure at first anchor into a
construction-time refusal with an accurate message — but it is evidence, exactly as ADR 0045 says of
the signer's response generally.

**Why the receipt records the returned ARN.** If the adapter echoed its configured `key_arn`, a
misconfiguration where the options name key A while the governed `witness.key_id` pins key B would
produce a receipt claiming B while KMS signed with A. The signature would then fail verification and be
reported as a signature fault. Recording what KMS returned makes the same misconfiguration surface as a
key-identity mismatch, which is what it actually is, and it does so during the existing signer
challenge in `enforce_production_witness` rather than at the first real anchor.

**Why bounded retries rather than resilient ones.** The instinct with a network dependency is to retry
until it succeeds. Here the operation being retried is the production of *evidence*, and a run that
eventually signs after a long outage is not obviously better than a run that refuses: the forward
window is a governed, observable process, and a refusal is a legible state an operator can act on,
while a silently-delayed anchor is not. Three attempts absorb ordinary throttling; anything worse is a
condition someone should see.

## Implementation notes

**Dependency.**

```toml
# apps/backend/pyproject.toml — [project].dependencies
# Step 4A (ADR 0046): AWS KMS witness signer for forward validation. ONLY
# app/validation/aws/ may import this — check_aws_sdk_isolation.sh enforces it.
"boto3>=1.35,<2.0",
```

`botocore` arrives transitively and is pinned by `boto3`; `botocore.stub.Stubber` is the test double,
so no separate test dependency is added.

**Module layout.**

```
apps/backend/app/validation/aws/__init__.py        # no side effects, no re-export of the client
apps/backend/app/validation/aws/kms_signer.py      # KmsAnchorSigner + build_kms_anchor_signer
apps/backend/tests/validation/aws/test_kms_signer.py
```

**Governed configuration** (the `witness` block, PRODUCTION profile):

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
    "options": { "key_arn": "arn:aws:kms:us-east-1:219024422756:key/<uuid>" }
  },
  "sink": { "...": "Step 4B" }
}
```

`options` carries no credentials; `assert_no_private_key_material` runs over it before the factory is
imported, and `key_arn` is a pointer to where custody lives, not custody itself.

**Signer contract.** `KmsAnchorSigner` satisfies the existing `AnchorSigner` protocol
(`attest(tip) -> SignedReceipt`, `identity() -> str`) and holds only a boto3 client — no key object, so
`_assert_no_in_process_private_key` passes on the merits rather than by accident. `attest` builds the
envelope via `build_witness_envelope`, digests it via `envelope_digest`, asserts `len(digest) == 32`,
calls `Sign(KeyId=<pinned ARN>, Message=digest, MessageType='DIGEST',
SigningAlgorithm='ECDSA_SHA_256')`, and returns a `SignedReceipt` carrying `PROTOCOL_VERSION`,
`ALGORITHM_ECDSA_SHA256_P256`, the returned `KeyId`, the fingerprint of the installed key bytes, the
digest hex, the base64 DER signature, a canonical `signed_at`, and the configured witness identity. The
DER signature is stored exactly as KMS returns it — never normalized to raw `r || s`, matching
`P256PrehashedVerifier`.

**Client construction.** `botocore.config.Config(region_name=<parsed from ARN>,
retries={"mode": "standard", "max_attempts": 3}, connect_timeout=5, read_timeout=10)`.

**New CI invariant** `apps/backend/scripts/check_aws_sdk_isolation.sh`, built as an **allowlist** in the
shape of `check_no_llm_in_order_path.sh` rather than a denylist over enumerated paths: every module is
presumed forbidden from importing `boto3`/`botocore` unless it sits under an `ALLOWED_DIRS` entry, which
for Step 4A is `app/validation/aws` alone. The allowlist form is the load-bearing choice — a denylist
over named directories silently permits a new file added somewhere nobody listed, which is exactly the
PR nobody looks closely at. The invariant also asserts the reverse direction: no module outside
`app/validation/aws/**` and its tests imports that package, so the factory string in governed
configuration remains the only route to it. Wired into CI alongside the existing seventeen, making it
the eighteenth; CLAUDE.md's invariant list is updated in the same PR.

**Documentation correction.** The `WitnessComponentConfig` docstring's "live outside this repository"
sentence is rewritten to state the decision here: the implementation is in-repo and CI-policed, the
deployment retains authority over whether it is used.

**IAM policy for Step 4A** (created later, in Step 4C — recorded here so the adapter is written against
it):

```json
{ "Effect": "Allow",
  "Action": ["kms:Sign", "kms:GetPublicKey"],
  "Resource": "arn:aws:kms:us-east-1:219024422756:key/<uuid>" }
```

**Test obligations for the implementation PR.** Stubbed throughout: a successful attest produces a
receipt that `AnchorVerifier` accepts under a real P-256 key; the `Sign` call is asserted to carry
`MessageType='DIGEST'`, `SigningAlgorithm='ECDSA_SHA_256'` and a 32-byte `Message`; a returned `KeyId`
or `SigningAlgorithm` that disagrees with the pinned values is refused; an alias, bare key id or
malformed ARN is refused at construction; a `GetPublicKey` SPKI that differs from the installed key is
refused; and credential, network, throttling-after-retries, key-disabled and malformed-response
conditions each raise `WitnessError` rather than escaping. A test asserts no live network call is
attempted.

## Consequences

**Positive.** A production signer becomes possible for the first time, unblocking everything downstream
of it. The private key is never present in the runner's process, which is the property the entire
witness design exists to obtain. The most security-critical adapter in the chain becomes reviewable,
testable and version-locked to the protocol it must agree with. AWS reachability becomes a structurally
enforced property rather than a convention.

**Negative.** The backend distribution grows an AWS SDK (~15 MB installed, plus `botocore`'s data
files) that the order-path image will carry without using — the honest price of following the
`anthropic` precedent instead of an optional extra. The repository now depends on a service AWS can
deprecate or change, and on IAM state that lives outside version control, so a correct deployment can
be broken by a change no PR touches. The eighteenth CI invariant is one more thing to keep passing. And
in-repo adapters weaken the original claim that the runner image contains no code capable of reaching
external witness storage — the claim becomes "no code outside one CI-policed package", which is a
weaker and more conditional statement.

**Neutral.** Signing moves from microseconds to a network round trip, which is immaterial at one
signature per session but does mean anchoring can now fail for reasons unrelated to the record. The
adapter is dead code until Step 4D wires a deployment to it.

## Alternatives considered (not chosen)

**Optional `aws` extra, lazily imported.** Keeps the SDK out of images that do not sign. Rejected
because it makes import behaviour environment-dependent — the precise defect that broke the MR-002
custodian procedure — and because it protects a property (SDK absence) weaker than the one the CI
invariant already gives (unreachability). Reconsider if the order-path image ever ships separately from
the forward-validation image, at which point excluding the extra becomes a real boundary rather than a
packaging preference.

**Out-of-repo deployment-supplied adapter**, as `witness_config.py` originally envisaged. Rejected
because it places the code that decides what gets signed outside review, testing and CI, and because
the properties that matter (`MessageType=DIGEST`, exactly 32 bytes, returned-ARN reporting, DER
preserved) are silent-failure-shaped: nothing would catch a mistake until a signature failed to verify.
Reconsider if a second deployment ever needs a signer this repository should not know about — a
hardware HSM, or a signer operated by a third party.

**A thin vendor-neutral signing abstraction** with KMS as one implementation. Rejected as speculative
generality: there is exactly one production signer, ADR 0045 pins exactly one algorithm, and the
`AnchorSigner` protocol is *already* the vendor-neutral seam. A second abstraction over a single
implementation would add indirection without adding a choice.

**KMS Ed25519 (`ED25519_SHA_512`) to reuse the reference verifier.** Rejected in ADR 0045 and not
reopened here; noted because it is the obvious question. It would not have avoided the protocol
generalization anyway, since `GetPublicKey` returns DER SPKI for every key spec.

**Signing the envelope with `MessageType=RAW`.** Rejected: KMS caps raw messages at 4096 bytes and
would hash server-side, so the verifier's `Prehashed` contract would break and the 32-byte digest the
receipt records would no longer be what was signed. `DIGEST` keeps the signed bytes identical to the
bytes the receipt names.

## Re-evaluation triggers

- **The order-path image is ever built separately from the forward-validation image.** The optional
  extra becomes a real boundary at that point and this decision should be revisited.
- **A second witness signer is required** (a different cloud KMS, an on-premises HSM, or a
  third-party-operated signer). The out-of-repo adapter question genuinely reopens.
- **`check_aws_sdk_isolation.sh` has to be relaxed for a legitimate reason** — that is the signal that
  AWS use has spread beyond the witness boundary, and the placement decision needs re-argument rather
  than an exception.
- **AWS deprecates or materially changes `Sign`/`GetPublicKey` semantics for asymmetric keys**, or
  changes the DER encoding of either the SPKI or the signature.
- **KMS signing failures become a recurring cause of refused sessions** in operation. Bounded retries
  are a deliberate choice against availability; if they cost real observations, the trade needs
  restating rather than silently loosening.
- **A future protocol version pins a second production algorithm.** The adapter's single-algorithm
  refusals would need to become a dispatch, and that should be a decision, not a patch.
