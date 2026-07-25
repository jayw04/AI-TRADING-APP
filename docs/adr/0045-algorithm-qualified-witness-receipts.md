# ADR 0045 — Algorithm-qualified witness receipts

| Field | Value |
|---|---|
| Date | 2026-07-25 |
| Status | Accepted |
| Phase | Forward validation (Workstream B, R5e onward) — Account-4 critical path |
| Supersedes | — |
| Related | 0018 (factor-data isolation), 0032 (AWS migration), 0044 (deployment lifecycle and fail-closed holds) |

## Context

R5d gave the forward-validation observation chain an independent witness: each committed chain tip is
signed by a signer whose private key the store-writer does not hold, and published to an external
append-only sink. R5e-1 and R5e-2 then made that boundary real rather than nominal — the reference
implementations are refused, the signer is challenged against a deployment-installed public key, the
sink must evidence its own write-once enforcement, and only an enforced `ProductionWitness` can reach a
`SessionRuntime`.

Every one of those controls is in place. None of them can run, because **no production signer exists**.
The gate correctly refuses `Ed25519AnchorSigner` (it holds its key in the runner's process) and
`FileExternalAnchorSink` (the store-writer can reach it), and the deployment has nothing else to offer.
The chosen production signer is AWS KMS, so that the private key is never present in the runner at all.

The obstacle is that the witness protocol is Ed25519-specific in three places, and **no KMS key spec
can satisfy it as written** — including the Ed25519 ones:

- `AnchorVerifier.__init__` calls `Ed25519PublicKey.from_public_bytes()`, and the installed-key reader
  requires **exactly 32 raw bytes**.
- `SignedReceipt` carries `signature_b64`, `public_key_id` and `witness_identity` — **no algorithm
  field**, so a verifier has nothing to check an algorithm against and a reader cannot tell what
  produced the signature.
- `WitnessedTip.signing_bytes()` covers the tip fields only — **no protocol version, no algorithm, no
  key identity** — so none of those are cryptographically bound to the signature.

AWS KMS asymmetric `SIGN_VERIFY` supports RSA (2048/3072/4096), ECC (NIST P-256/P-384/P-521,
secp256k1) **and Ed25519** (`ED25519_SHA_512`, `ED25519_PH_SHA_512`). The Ed25519 support does not
rescue the current protocol: `GetPublicKey` returns a DER SubjectPublicKeyInfo for *every* key spec,
including Ed25519, so a KMS key of any kind is rejected by the installed-key reader — which requires 32
raw bytes — before a signature is ever attempted. A KMS Ed25519 signature also arrives with no
algorithm field to record it under, because the receipt has none.

So the generalization is required whichever KMS algorithm is eventually pinned. What KMS Ed25519
support changes is the *choice*: selecting P-256 is now a deliberate decision between two available
options, argued below, rather than the only thing KMS could do.

One fact makes this the right moment. **No observation has ever been recorded**: session count is 0,
no observation store exists, and the only `SignedReceipt` values in existence are in tests. There is no
legacy evidence to remain compatible with. That is true today and stops being true the moment the first
observation is committed.

## Decision

The witness protocol becomes **algorithm-qualified and versioned**, and the verifier's authority comes
from deployment-installed material rather than from anything the signer returns.

1. **Receipts carry an explicit protocol version and algorithm.** `SignedReceipt` gains
   `protocol_version`, `algorithm`, `key_id`, `public_key_fingerprint`, `message_digest` and
   `signed_at`, alongside the existing `signature` and `witness_identity`.

2. **The signed message binds the protocol, the algorithm and the key identity**, not just the tip. A
   signature over one algorithm or key identity cannot be replayed as a signature over another.

3. **The verifier dispatches through a closed allowlist**, and a deployment pins exactly **one**
   production algorithm. An algorithm not on the allowlist is refused; an algorithm on the allowlist
   but not the pinned one is refused.

4. **The signer's response is evidence, never authority.** The algorithm, the trust root and the key
   identity used for verification are read from the installed public key and the governed
   configuration. A receipt whose `algorithm`, `key_id` or `public_key_fingerprint` disagrees with the
   pinned values is refused — the receipt's own fields are checked *against* the pinned material, never
   used to select it.

5. **The governed production profile is AWS KMS `ECC_NIST_P256` with `ECDSA_SHA_256`.** Exactly one
   production algorithm is implemented; the others KMS offers are not.

6. **Ed25519 remains, as a reference and test implementation only** — permitted under the `REFERENCE`
   witness profile, and refused for production exactly as it is today.

7. **Protocol version 1 is retired without migration.** No v1 receipt has ever been committed, so v2 is
   the only version a production verifier accepts. A v1 receipt is refused rather than upgraded.

## Rationale

### Why generalize rather than wrap KMS

The tempting shortcut is an adapter that calls KMS and returns a `SignedReceipt` labelled as it is
today. It does not work and should not be made to. A KMS ECDSA signature is an ASN.1 DER SEQUENCE of
`(r, s)` over a P-256 curve; the current verifier hands it to `Ed25519PublicKey.verify()`, which will
reject it. The public key is DER SPKI, which the installed-key reader rejects for not being 32 bytes.
Making it "work" would mean bypassing both, at which point the receipt says Ed25519 while the
cryptography is ECDSA — a record that misstates how it was signed is worse than one that refuses to be
produced.

### Why the algorithm must be in the signed bytes

If the algorithm is a receipt field but not covered by the signature, an attacker who can rewrite
stored receipts can relabel one — presenting an ECDSA signature as though it were produced under a
different scheme, or claiming a stronger algorithm than was used. Binding `protocol_version`,
`algorithm`, `key_id` and `public_key_fingerprint` into the signed message makes the label
unforgeable-without-the-key: change any of them and the signature stops verifying.

### Why a closed allowlist, and one production algorithm

Algorithm agility is usually argued for as future-proofing. In a verifier it is a downgrade surface:
every algorithm the verifier will dispatch to is one an attacker may try to steer it toward, and the
weakest one bounds the security of the whole scheme. The verifier therefore accepts a fixed set of
identifiers and a deployment pins one of them. Adding an algorithm is an ADR-level change, not a
configuration change.

Implementing only `ECDSA_SHA_256` on P-256 for production — rather than every KMS scheme — keeps the
verifier small enough to reason about. RSA signing in KMS is materially slower and larger for no
benefit here; the other curves add code paths no deployment will use.

### Why P-256 rather than KMS Ed25519

AWS KMS now supports Ed25519 key specifications and signing algorithms. The program nevertheless
selects `ECC_NIST_P256` with `ECDSA_SHA_256`, because the witness pipeline signs a **precomputed
SHA-256 digest** submitted with `MessageType=DIGEST`. KMS Ed25519 does not offer that shape:

| Algorithm | Message rule |
|---|---|
| `ECDSA_SHA_256` (P-256) | `MessageType=DIGEST`, 32-byte SHA-256 digest — matches the pipeline |
| `ED25519_SHA_512` | `MessageType=RAW` — the full canonical envelope must be sent to KMS |
| `ED25519_PH_SHA_512` | `MessageType=DIGEST`, but the digest is an **SHA-512** prehash (Ed25519ph) |

Choosing either Ed25519 variant introduces a second digest convention: `RAW` means shipping the whole
envelope to KMS rather than a digest, and Ed25519ph means the receipt's `message_digest` and the value
actually signed are computed under different hash functions — precisely the sort of divergence that
makes a record hard to re-verify years later. Neither preserves the current raw-key protocol unchanged
either, since KMS returns DER SPKI regardless.

**This choice is deliberate, not a consequence of KMS lacking Ed25519 support.** Should the pipeline's
digest convention ever change, or should Ed25519ph become preferable for custody reasons, the
allowlist is the mechanism and the pinned algorithm is the decision to revisit.

### Why the signer's response cannot be authority

This is the same circularity R5e-1 closed for the key challenge, applied to the protocol. If the
verifier selected its algorithm from `receipt.algorithm`, a substituted signer would choose the terms
on which it is judged. The installed public key and the pinned configuration are the deployment's
statements about what it trusts; the receipt is the signer's claim about what it did. Verification is
the comparison of the second against the first, in that direction only.

### Why retire v1 rather than support both

Supporting two receipt schemas forever, to remain compatible with records that do not exist, would be
pure cost: two verification paths, two sets of failure modes, and a permanent question about which
records were produced under which. The reason this is cheap today is precisely that session count is 0
— and that window closes at the first observation. Taking it now converts a permanent compatibility
burden into a single sentence in this ADR.

## Implementation notes

### Receipt schema (protocol version 2)

```
protocol_version        int     2
algorithm               str     an allowlisted identifier, e.g. "ECDSA_SHA_256_P256"
key_id                  str     the deployment's key handle (KMS key ARN); opaque to the verifier
public_key_fingerprint  str     sha256 hex of the EXACT installed DER SPKI bytes (full 64 hex chars)
message_digest          str     sha256 hex of the canonical signing bytes
signature               str     base64 of the raw signature bytes (ASN.1 DER for ECDSA)
signed_at               str     ISO-8601 UTC, evidence only — never trusted for ordering
witness_identity        str     the signing service's own identity string
```

`public_key_fingerprint` is the **full** SHA-256 hex over the installed DER SPKI bytes. The current
`public_key_id` truncates to 16 hex characters (64 bits) over raw Ed25519 bytes; truncation is dropped
because a fingerprint is a mismatch detector and there is no reason to weaken it.

`signed_at` is recorded because an operator will want it, and is explicitly **not** used for ordering
or freshness — the chain sequence and the anchor linkage carry that.

### The canonical signed envelope

There is **exactly one** byte serialization of what gets signed, and it carries an explicit domain and
version prefix so a signature can never be reinterpreted under a different protocol:

```
b"workbench.witness.v2\n" + canonical_json
```

where `canonical_json` is

```json
{"algorithm":"…","anchor_sha256":"…","commit_sha256":"…","key_id":"…",
 "protocol_version":2,"public_key_fingerprint":"…","sequence":N,"session_date":"…"}
```

serialized with `sort_keys=True`, `separators=(",", ":")`, UTF-8 — the existing convention, extended
with the four binding fields. The domain prefix provides separation from any other signature this key
might ever produce; the in-JSON `protocol_version` keeps the version inside the signed payload rather
than only in the framing.

`message_digest` is the SHA-256 of **exactly these bytes**, prefix included. KMS receives that 32-byte
digest and nothing else.

### Key identity

- **`key_id` is the full immutable KMS key ARN**, never an alias. An alias is a mutable pointer, and a
  record that names one does not say which key signed it.
- An alias **may** be a deployment input for operational convenience, but it must be resolved to the
  key ARN before signing, and the resolved ARN must equal the pinned `key_id`. Resolution is an input
  step, never a substitute for the pin.
- The `Sign` response's returned key ARN must **equal** the pinned ARN. A response naming any other key
  is refused, even if the signature would verify.
- At composition, `GetPublicKey` metadata — key spec, key usage, and supported signing algorithms —
  must match the configured contract (`ECC_NIST_P256`, `SIGN_VERIFY`, `ECDSA_SHA_256`). A key that is
  the right ARN but the wrong shape is refused.

### KMS parameters

- Key spec `ECC_NIST_P256`, usage `SIGN_VERIFY`, signing algorithm `ECDSA_SHA_256`.
- `Sign` is called with `MessageType=DIGEST` and `Message` = the 32-byte SHA-256 of the canonical
  envelope. The runner computes the digest; the envelope itself is never sent to KMS. The verifier's
  counterpart is the prehashed contract below — the two must be read together.
- The `Sign` response's `KeyId` and `SigningAlgorithm` are checked against the pinned configuration and
  refused on mismatch — they corroborate, they do not select.
- `GetPublicKey` output is DER SPKI (X.509 `SubjectPublicKeyInfo`), together with the metadata above.
  The deployment installs those exact bytes at `witness.public_key_path`; the fingerprint is computed
  over them unchanged.

### Verification

Verification is **local and offline**: it uses the installed SPKI public key, never a KMS `Verify`
call. Asking the signing service whether its own signature is valid would restore the circularity the
whole design removes.

Order is load-bearing. Before any cryptography runs, the verifier requires:

1. `receipt.protocol_version == 2`
2. `receipt.algorithm` is allowlisted **and** equals the pinned algorithm
3. `receipt.key_id` equals the pinned key ARN
4. `receipt.public_key_fingerprint` equals `sha256(installed_spki_bytes)`

Checking identity first means a receipt from the wrong key or algorithm is refused as a mismatch rather
than as a signature failure — the operator sees which of the two actually happened.

#### The verification contract is PREHASHED, and this is not optional

The verifier reconstructs the canonical envelope, computes its SHA-256 digest, and requires that digest
to equal `receipt.message_digest`. It then verifies the DER ECDSA signature over **those 32 digest
bytes** using ECDSA with `Prehashed(SHA-256)`. **It must not apply SHA-256 to the digest a second
time.**

```
canonical envelope
  → independently compute SHA-256
  → require equality with receipt.message_digest      (else WITNESS_MESSAGE_DIGEST_MISMATCH)
  → verify DER ECDSA signature over those 32 bytes
    using ECDSA(Prehashed(SHA-256))                   (else ANCHOR_SIGNATURE_INVALID)
```

Concretely:

```python
public_key.verify(
    signature,                       # DER, from the receipt
    message_digest_bytes,            # the 32 bytes, NOT the envelope
    ec.ECDSA(utils.Prehashed(hashes.SHA256())),
)
```

The trap this closes: KMS with `MessageType=DIGEST` signs `SHA256(envelope)` as the hash itself. Passing
those same digest bytes to `ec.ECDSA(hashes.SHA256())` would hash them *again*, so the verifier would be
checking a signature over `SHA256(SHA256(envelope))` and every valid signature would fail.

Verifying the original envelope with ordinary `ECDSA(SHA256())` is mathematically equivalent, because it
recomputes the same digest internally. It is **not** the contract chosen here: the prehashed form
mirrors the KMS `MessageType=DIGEST` call exactly, and it makes `message_digest` a verified part of the
procedure rather than a decorative field nothing checks. One contract is pinned so that an implementer
cannot pick the other and leave the digest unexamined.

### Key rotation

Rotation is a **governed event**, not an operational convenience. A new key requires installing new
trusted-root material at `witness.public_key_path` and updating the pinned `key_id` and fingerprint in
the governed configuration. Rotation **cannot** occur silently by re-pointing an alias: the pinned ARN
and the installed fingerprint would both disagree with the new key, and signing would be refused. Tips
signed under a retired key remain verifiable only against that key's installed material, so retiring a
key is an evidence-retention decision as much as a credential one.

### Refusal codes

| Code | Condition |
|---|---|
| `WITNESS_PROTOCOL_VERSION_UNSUPPORTED` | receipt version is not 2 |
| `WITNESS_ALGORITHM_NOT_ALLOWLISTED` | algorithm is outside the closed allowlist |
| `WITNESS_ALGORITHM_NOT_PINNED` | allowlisted but not the deployment's pinned algorithm |
| `WITNESS_KEY_IDENTITY_MISMATCH` | `key_id` or `public_key_fingerprint` disagrees with pinned material |
| `WITNESS_KEY_CONTRACT_MISMATCH` | `GetPublicKey` key spec / usage / algorithms disagree with the configured contract |
| `WITNESS_SIGNER_KEY_ARN_MISMATCH` | the `Sign` response names a key other than the pinned ARN |
| `WITNESS_MESSAGE_DIGEST_MISMATCH` | the recomputed envelope digest differs from `receipt.message_digest` |
| `ANCHOR_SIGNATURE_INVALID` | the signature does not verify (retained from R5d) |

`WITNESS_MESSAGE_DIGEST_MISMATCH` is deliberately distinct from `ANCHOR_SIGNATURE_INVALID`. An altered
or incorrectly serialized envelope is a different operational finding from a mathematically invalid
signature: the first says the record no longer reconstructs, the second says the signature was never
valid over what it claims to cover. Collapsing them would lose that distinction exactly when an
operator needs it.

### Configuration

The governed `witness` block gains `algorithm` and `key_id`, both required for the `PRODUCTION`
profile, alongside the existing `public_key_path`, `trusted_root`, `signer` and `sink`. As with every
other governed value, a deployment that omits them fails to load rather than defaulting.

### Sequencing

This ADR authorizes no code. Implementation is a **protocol-generalization PR** touching
`chain_witness.py`, `witness_enforcement.py`, the production witness composition and receipt
serialization, with **no AWS code**. The KMS signer and the S3 Object-Lock sink follow in a separate PR
behind a separate dependency decision for `boto3` (a new external dependency, per the platform's
standing rule).

The decoder docstring and test-name corrections deferred from PR #514 land in the generalization PR,
which rewrites that function.

## Consequences

**Positive**

- A production witness becomes possible at all; the R5e boundary stops being a control with nothing
  behind it.
- The record states how it was signed, in a field bound by the signature.
- The private key is never in the runner's process, address space or host — the property the attribute
  walk in R5e-1 can only approximate.
- Downgrade attacks have no surface: the verifier will not dispatch to an algorithm a deployment has
  not pinned.

**Negative**

- The evidence chain gains a hard dependency on AWS KMS availability. A KMS outage stops observations —
  correctly, since an unwitnessed observation must not be recorded, but it is a real new failure mode
  on the critical path.
- Signing moves from microseconds in-process to a network round trip, with the retry, timeout and
  latency handling that implies.
- ECDSA is randomized: two signatures over identical bytes differ. Nothing may assume signature
  determinism, and no test may compare signatures byte-for-byte.
- Verification now depends on `cryptography`'s EC support and on DER parsing, a larger surface than
  `Ed25519PublicKey.from_public_bytes`.
- Key rotation becomes a governed event with a real procedure, because the fingerprint and `key_id` are
  pinned. Rotating without one breaks verification of new tips.

**Neutral**

- Ed25519 remains in the codebase as the reference implementation, so the test suite keeps a fast
  in-process signer and does not need AWS to exercise the chain.
- The receipt grows from three fields to eight. Immaterial against the observation payload.

## Alternatives considered (not chosen)

**Wrap KMS while keeping the Ed25519-labelled receipt.** Not implementable — the signature format and
public-key encoding both differ — and if forced, it produces a record that misstates its own
cryptography. Reconsider never.

**Use KMS Ed25519 (`ED25519_SHA_512` or `ED25519_PH_SHA_512`).** Available, and it would have kept the
signature scheme closer to R5d's. Rejected on message convention rather than capability:
`ED25519_SHA_512` requires `MessageType=RAW`, shipping the whole envelope to KMS instead of a digest,
and `ED25519_PH_SHA_512` uses an SHA-512 prehash, so the receipt's SHA-256 `message_digest` and the
value actually signed would be computed under different hash functions. Neither preserves the current
raw-key protocol anyway, since `GetPublicKey` returns DER SPKI for Ed25519 too. Reconsider if the
pipeline's digest convention changes, or if Ed25519ph becomes preferable for custody reasons — via the
allowlist, as an ADR.

**Use a self-hosted remote Ed25519 signing service instead of KMS.** This would preserve the protocol
exactly and keep the key out of the runner. Rejected because it moves the custody problem rather than
solving it: something must run that service, hold the key, and be secured and audited — and that
something would be our own infrastructure, defeating most of the point of an independent boundary. KMS
gives hardware-backed custody and CloudTrail-recorded use without our operating a signer. Reconsider if
an AWS dependency becomes unacceptable for the evidence path, or if a hardware token with an Ed25519
capability is adopted for custody generally.

**Open-ended algorithm agility, with the algorithm taken from configuration as a free string.**
Rejected: every reachable algorithm is a downgrade target, and a free-string configuration means a
deployment can silently pick a weak one. The allowlist makes adding an algorithm a reviewed decision.
Reconsider if a genuine second production algorithm is required — as another ADR.

**Support v1 and v2 receipts side by side.** Rejected because there are no v1 receipts to support.
Reconsider only if a v1 record is ever discovered to have been committed, which would itself be a
finding worth investigating.

**Defer the whole thing and open the forward window with the reference witness.** Rejected outright.
It would produce observations that look witnessed while being tamper-evident against nothing — the
exact failure R5e-1 exists to prevent — and their governance status would be near-impossible to
communicate afterwards.

## Re-evaluation triggers

- **The witness pipeline's digest convention changes** (for example to SHA-512). KMS Ed25519ph would
  then align where it currently does not, and the pinned algorithm would be worth revisiting.
- **P-256 or ECDSA-SHA-256 is deprecated** by NIST or the platform's compliance posture. The allowlist
  is the mechanism; the pinned choice is the decision.
- **KMS unavailability blocks observations more than once in a forward window**, or its latency
  materially affects the session schedule. That would argue for a queued or deferred-witness design,
  which is a different decision and would need its own ADR.
- **A second signer or a second witness sink becomes necessary** (multi-region, multi-custodian). The
  single-pinned-algorithm rule assumes one production signer.
- **Any v1 receipt is found in a committed observation.** That contradicts the premise of clause 7 and
  invalidates the no-migration decision.

---

⚠ **Status is `Accepted`** (owner review of `18c5b422`, accepted on correction of the prehashed-ECDSA
verification contract). Acceptance authorizes the protocol-generalization work only.

Everything downstream remains separately unauthorized: `boto3` as a dependency, the AWS KMS signer and
S3 Object-Lock sink, provisioning `ec2-forward-validation`, real ACTIONS ingestion, opening the forward
window, and the first Account-4 observation. Account 4 is PAUSED with the operational hold ACTIVE, and
session count is 0.
