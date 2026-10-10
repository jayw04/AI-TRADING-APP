# RANGE-002 Approval Signing and Verification — Design v0.1 (DESIGN ONLY)

> **Status: DESIGN ONLY -- NOT IMPLEMENTED.** Level 2 controls described here (signed approvals H4, execution boundary M1, external anchoring M3, copied-registry detection, holdout recovery, exposure severity policy, torn-tail recovery) are not implemented. The merged PR #738 (`b31b5f7b`) and PR #739 (`d61f313a`) provide Level 1 only. Nothing in this document is signed, approved or selected by the owner; all owner decision tables are blank.
>
> **NOTE (2026-10-10, refreshed):** Current code facts (2026-10-10): PR #737 (docs), PR #738 (spec infrastructure) and PR #739 (Level 1 governance infrastructure) are MERGED; `main` is `d61f313a`, whose tree is identical to the reviewed PR 3 head `808d10fb` (tree `8b04684f`). The spec manifest `governance`/`manifest` fields are all-null (nothing is frozen or signed). The Linux acceptance verifier and its 33-id required-test manifest are on `main`. The run-registry/exposure ledger is strict JSON (not YAML); `MAX_ATTEMPT_LIMIT` = 10,000 is a technical ceiling only (not a policy value); attempt budgets are per (genesis, phase) across windows; phase P5 is refused at Level 1. Owner-accepted Level 1 properties (unchanged by this document): a fork-inherited capability is run-bound and is not a security boundary; directory aliases yield a consistent identity but no confinement; a torn registry tail fails closed and locks out (no governed recovery path; see the Registry Recovery Procedure design). Review finding R1-L1b (distinct signatories) is an accepted Level 1 limitation; its distinct-role follow-up (`57dadd52`) is a separate item. No Level 2 control (signed approvals, execution boundary, external anchoring, recovery tool) is implemented or enabled. Superseded statements: the header 'Code facts verified at `69c36654` (`fix/range002-review-findings` base)' and the Section 0 baseline describe a pre-merge branch. The body is unchanged and was not re-verified against the merged code.

| Field | Value |
|---|---|
| Status | **DRAFT FOR OWNER REVIEW. No code, no AWS call, no key creation, no IAM change is authorized by this document.** |
| Date | 2026-10-09 |
| Covers | Owner direction 2026-10-09 items (A) cryptographic H4 approval signatures, (E) H3 exposure-ledger binding, and the D08 role/separation-of-duties part |
| Builds on | `RANGE-002_Governance_Hardening_Design_v0.1.md` (hardening design; Sections 1.6, 3.3, 3.6 reused, not contradicted), Plan v0.5 (WP0.3, WP0.4, WP0.6, R9), Addendum A1 section 10, Decision Sheet D08, ADR 0045 / 0046 / 0047 |
| Companion | `RANGE-002_Execution_Boundary_and_Registry_Anchoring_Design_v0.1.md` (boundary, anchoring, holdout-recovery checklist, exposure severity) |
| Code facts verified at | `69c36654` (`fix/range002-review-findings` base) |

> **Nothing here is a decision.** Every item labelled "Recommendation (not a decision)" is a recommendation only. Role assignments, signature requirements, key custodians and every value in a decision table are **UNSELECTED and UNSIGNED**. No agent signs, holds a key or fills a decision row (rule R9).

---

## 0. Baseline: what sign-off is today

Verified in the code at `69c36654`:

- `spec/schema.py` `Signoff` is `{owner, trading_expert, independent_validator: str|None, date, spec_sha256}`. `missing_signoff_fields()` only checks that the three names are non-blank and a date is set. **A sign-off is three typed strings.** Anyone who can edit the draft can "sign" for everyone.
- `signoff` is deliberately **excluded** from `hashable_payload()`; `spec_sha256` covers everything else. The freeze tool computes the hash and refuses an existing output file. `SpecView.is_signed` is true iff all fields are present and the recorded hash equals the recomputed one: it proves **the file was not edited after freezing, not that any person approved it**.
- `exposure_ledger.py` `signoff` is a `{signed_by, signed_on}` string pair, and the ledger sha256 is not pinned by anything signed (hardening design S3).
- `spec/hashing.py` provides `canonical_json` (sorted keys, compact separators, ASCII, finite numbers only, 5 and 5.0 equal), `loads_strict` (duplicate keys and NaN refused), `content_sha256`, `file_sha256`. These are the only hashing primitives this design uses.
- Existing signing machinery (reuse, no new dependency): `app/validation/witness_protocol.py` defines the algorithm allowlist, `P256PrehashedVerifier` (DER SPKI key, ECDSA over a **prehashed** SHA-256 digest), `fingerprint_public_key`, and a domain-prefixed envelope pattern (`workbench.witness.v2\n`). ADR 0046 fixes the production signature profile: AWS KMS `ECC_NIST_P256`, `ECDSA_SHA_256`, `MessageType=DIGEST` over exactly 32 bytes, full immutable key ARN as identity, installed public key (not KMS) as trust root, no fallback of any kind. `boto3` is importable **only** under `app/validation/aws/` (`check_aws_sdk_isolation.sh`, ADR 0046 decision 2).

### 0.1 The constraint that shapes the whole design

**Signing is performed by humans, outside the repository and outside the agent environment; verification is offline and needs only `cryptography` (already a dependency).** Consequently this design adds **no boto3 import anywhere**, no new package and no new import location. The freeze tool, the results guard and the verifier never call AWS and never hold a private key. If a future implementation wanted a repo tool that calls `kms:Sign` for the human, that tool would have to live under `app/validation/aws/` and would need an ADR 0046 amendment; **it is not proposed**.

---

## 1. Purpose

Replace "three names typed into a JSON file" with **content-bound, cryptographically verifiable, role-attributed approvals** such that:

1. a verifier who holds only pinned public keys can prove, offline, that a specific key approved a specific `spec_sha256` and a specific document set in a specific role;
2. a person or process that can write files in the research tree cannot manufacture, alter, replay or re-scope an approval;
3. the owner, the trading expert and the independent validator are distinguishable parties with distinguishable keys, and the validator controls which keys are trusted;
4. the exposure ledger (H3) is bound to the approved spec by hash **and** a verified signature.

## 2. Threat model

| ID | Threat | Today | After this design |
|---|---|---|---|
| T1 | Agent or developer writes names into the draft and freezes | Accepted by the freeze tool | Refused: no verified approval records |
| T2 | Valid approval re-used for a different spec / role / purpose / document set | Not applicable (no signatures) | Refused: all bound in the signed envelope; domain-separated |
| T3 | Post-signing edit of a decision sheet, Addendum A1 or the plan | Hash recorded nowhere signed | Refused: document hashes are in the signed payload |
| T4 | Same person signs two roles with two keys | Possible (names) | Detected only procedurally (Section 9); technically enforced as distinct key ids and distinct IAM principals |
| T5 | Attacker adds their own public key to the trusted set | n/a | Refused unless the allowlist hash matches the validator-reviewed, externally anchored pin (Section 7) |
| T6 | Agent environment obtains signing capability (IAM role, copied credentials) | n/a | Key policy denies `kms:Sign` to every non-human principal; CloudTrail reconciliation (Section 5.5) |
| T7 | Key compromise | n/a | Revocation, suspect-window rule, re-signing without re-freezing the spec (Section 7.4) |
| T8 | KMS / AWS outage during approval | n/a | Signing impossible; no fallback; verification unaffected (offline) (Section 8) |
| T9 | Blind signing (signer signs a digest they did not derive) | n/a | Signer-side recomputation procedure and validator spot-check (Section 5.4); residual risk stated |
| T10 | AWS account administrator changes key policy to let anyone sign | n/a | **Not prevented technically.** Detected by key-policy snapshot hashing and CloudTrail review; residual risk accepted by the owner (Section 11) |

Out of scope: an attacker holding signing keys of all required roles simultaneously; coercion; loss of the AWS account itself.

## 3. Mechanism overview

```
 draft spec (all P0 set) --freeze tool--> signing requests (one per role; unsigned; contain digest)
        |                                         |
        | (hash recomputed independently)         v
        |                              human signer, own machine, own IAM identity:
        |                              recompute digest -> aws kms sign (MessageType=DIGEST)
        |                                         |
        |                                         v
        |                              detached signature record (JSON) returned out-of-band
        v                                         |
 freeze tool --approvals DIR --> verify offline against pinned allowlist --> frozen spec + sidecar records
                                                  |
                  results_guard.authorize() re-verifies on every result-bearing call
                  independent validator re-verifies in a separate environment (Section 7.2)
```

The frozen spec stays immutable and keeps its existing hash rule (sign-off block excluded). Approvals are **detached, append-only sidecar records**: they sign the spec hash, so they can be added, withdrawn, revoked and re-issued without ever changing `spec_sha256` and without a "re-freeze".

## 4. The signing contract

### 4.1 Algorithm and key spec

- **Key spec** `ECC_NIST_P256`, usage `SIGN_VERIFY`; **signing algorithm** `ECDSA_SHA_256`; **message type** `DIGEST` over exactly 32 bytes; signatures kept as ASN.1 DER, base64 in the record. This is identical to ADR 0045 / 0046 so `witness_protocol.P256PrehashedVerifier` (via `build_verifier`) verifies RANGE-002 approvals **unchanged**.
- The Ed25519 *reference* algorithm is **refused** for approvals (it exists for development and tests only; an in-process key is exactly what we are replacing). A record naming any algorithm outside `{ECDSA_SHA_256_P256}` is a hard refusal.
- Alternative considered, not recommended as primary: an offline hardware key (FIDO2/PIV) producing P-256 signatures. It satisfies "independently protected" and avoids AWS dependency for signing, but has no CloudTrail-style external signing log. Because the verifier path is algorithm-qualified and P-256-only, a hardware P-256 key could be pinned the same way. **Recommendation (not a decision):** AWS KMS per the owner's preference; hardware P-256 as a permitted equivalent only if the owner records why KMS is unavailable to a given signer (Q-A1).

### 4.2 The canonical message

```
message = DOMAIN_PREFIX || canonical_json(payload)          # spec/hashing.canonical_json
digest  = SHA-256(message)                                  # the 32 bytes handed to KMS
DOMAIN_PREFIX = b"range002.approval.v1\n"                   # distinct from b"workbench.witness.v2\n"
```

Distinct domain tags, one per purpose, so a signature for one purpose can never verify as another even under the same key (Section 4.6):

| Purpose (`payload.purpose`) | Domain prefix |
|---|---|
| `P0_APPROVAL` (spec freeze and addendum sign-off) | `range002.approval.v1\n` |
| `EXPOSURE_LEDGER_APPROVAL` | `range002.exposure-approval.v1\n` |
| `EXPOSURE_CLASSIFICATION` (hardening 3.3, only after F is satisfied) | `range002.exposure-class.v1\n` |
| `HOLDOUT_RECOVERY` (hardening 1.6) | `range002.holdout-recovery.v1\n` |
| `HOLDOUT_RUN_AUTHORIZATION` (boundary design B) | `range002.run-authorization.v1\n` |
| `ALLOWLIST_PIN` (validator pin, Section 7.1) | `range002.allowlist-pin.v1\n` |
| `TORN_TAIL_ADJUDICATION` (anchoring design) | `range002.torn-tail.v1\n` |

(The hardening design named `RANGE002-HOLDOUT-RECOVERY-v1` as its domain string; this design adopts the byte-prefix form above for all purposes and supersedes that spelling only. The binding content of the recovery record is unchanged.)

### 4.3 Payload fields (`P0_APPROVAL`)

Strict JSON; every key required; unknown keys refused; no defaults; duplicate keys refused (`loads_strict`). Floats are not permitted anywhere in an approval payload (integers and strings only), so `canonical_json` normalisation cannot move a hash.

```
schema_version      1
purpose             "P0_APPROVAL"
spec_sha256         <64 lowercase hex>          # the frozen spec content hash (signoff block excluded)
role                "OWNER" | "TRADING_EXPERT" | "INDEPENDENT_VALIDATOR"   # closed set; P6 approver is a later, separate purpose
decision            "APPROVE" | "REJECT" | "AMEND"                          # only APPROVE ever satisfies a requirement
signer              { person_id: <str>, key_id: <full KMS key ARN>, public_key_fingerprint: <64 hex sha256 of installed DER SPKI> }
signed_on           "YYYY-MM-DD"                # the date the signer states; informational, not authority
not_before / not_after   UTC "YYYY-MM-DDTHH:MM:SSZ"   # validity window, bounded (recommended <= 30 days)
decisions_attested  ["D01", ... ]               # decision ids this signer attests (sorted, unique; may be all D01-D19 or a role-scoped subset)
documents           [ {doc_id, sha256, custody_ref} ... ]   # sorted by doc_id; the packet (see 4.4)
packet_sha256       <64 hex>                    # content_sha256 of the documents array; redundant by design, cross-checked
statement_id        "RANGE002-P0-STATEMENT-v1"
statement_sha256    <64 hex>                    # sha256 of the exact attestation text the signer read (text itself stored in the packet)
nonce               <32 lowercase hex>          # 128-bit random, generated by the signer's tool
supersedes          null | <64 hex record_sha256>   # an earlier record of the same signer/role/purpose this replaces
```

### 4.4 Which documents are hashed

`documents` is the **sign-off packet** the plan already requires (Plan v0.5 P0 exit gate: "the sign-off packet pins the SHA-256 of every document signed"): the design DOCX (custody ref = S3 bucket + Version ID per ruling C10 and GITHUB-OPS-001), Addendum A1, Plan v0.5, the decision sheets, `governing_reconciliation.md`, `recon.md`, and the frozen-spec draft file. For Git-resident documents the hash is `file_sha256` of the committed blob; for S3 artefacts the entry carries the Version ID. The `statement` (the words "I approve spec X in the role of Y, having reviewed the documents listed") is itself a packet document so its hash is bound. The packet composition is **not chosen here**: it is the owner's list, finalised at P0 (Q-A5).

### 4.5 What is deliberately NOT in the signed payload

Free-text names, titles, or comments are not authority. `signer.person_id` is a registry identifier resolved through the allowlist (Section 7); the display name in the legacy `signoff.*` fields is cross-checked against the allowlist for readability only and never satisfies a requirement.

### 4.6 Replay protection

A record is valid for exactly one `(spec_sha256, role, purpose, packet_sha256, key_id)` tuple. Specific defences:

| Replay | Defence |
|---|---|
| Other spec | `spec_sha256` in payload; verifier compares with the spec under test |
| Other role | `role` in payload **and** allowlist binds `key_id` to exactly one role; a key listed for `OWNER` cannot satisfy `INDEPENDENT_VALIDATOR` |
| Other purpose (e.g. approval re-used as recovery or exposure authority) | distinct domain prefix and `purpose`; different prefix means different digest |
| Other document set | `packet_sha256` and `documents[]` in payload; guard compares with packet on disk |
| Re-used after expiry | `not_after`; verifier takes "now" from a single injected clock and refuses outside window |
| Old record after supersession or withdrawal | `supersedes` chain; a signed `WITHDRAW` (decision `REJECT` referencing the record) invalidates; verifier uses the newest valid record per tuple and refuses a chain with a fork |
| Duplicate nonce across different payloads | nonce uniqueness check across the record set; collision is an anomaly (refuse) |
| Cross-environment | the allowlist hash (Section 7.1) is bound into the records through `statement`/packet; records signed against a different allowlist version do not satisfy a later one unless re-confirmed |

## 5. Key custody, separation, and permissions

### 5.1 Keys

One **dedicated KMS key per signing role and per person** (not one shared key per role):

| Key | Holder | Sign permission | Notes |
|---|---|---|---|
| `range002-approval-owner` | Owner | Owner's human IAM principal only | |
| `range002-approval-trading-expert` | Trading expert | That person only | |
| `range002-approval-validator` | Independent validator | That person only | Also signs `ALLOWLIST_PIN` records |

- **Separate from the witness key.** The forward-validation witness key (ADR 0047) signs machine tips from an EC2 instance role; approval keys are human-held. Different keys, different key policies, different principals; a witness-key signature must never be accepted as an approval and vice versa (distinct domain prefixes, and the allowlist never contains the witness key).
- **Separate account recommended.** Recommendation (not a decision): create approval keys in an AWS account or at minimum an administrative boundary that is *not* the account running `ec2-paper` / `ec2-forward-validation`, so a compromise of the workbench runtime roles cannot reach them. If a single account is used, the key policy must still carry the explicit denies in 5.2 (Q-A2).
- The agent environment, research environment (ruling C12) and every EC2 instance role hold **no** permission on these keys, not even `GetPublicKey` through role credentials; public keys are exported once by the validator.

### 5.2 Key-policy and IAM requirements (to be built later, by recorded operator command, not by code)

For each key:

1. `kms:Sign` allowed **only** to the named human's IAM Identity Center / IAM principal ARN, with `Condition: Bool aws:MultiFactorAuthPresent = true` and a `kms:SigningAlgorithm = ECDSA_SHA_256` and `kms:MessageType = DIGEST` condition. No grants (`kms:CreateGrant` denied), no `kms:*`, no wildcard principal.
2. **Explicit `Deny` of `kms:Sign` for every other principal**, including the account root where the organisation allows it, every EC2 instance profile, every CI role and any role assumable by the research or agent environment.
3. `kms:GetPublicKey` for the validator and the owner (the public key is non-secret, but the allowlist pin procedure in 7.1 requires the validator to fetch it themselves).
4. **Key administrators** (policy change, disable, schedule deletion) are a **different principal from every signer** and from the workbench operator. Waiting period for deletion set to the maximum (30 days). Key rotation is *not* enabled (asymmetric KMS keys do not auto-rotate; rotation = a new key, a new allowlist entry, Section 7.3).
5. Region and identity: the pinned identity is the **full immutable key ARN**; aliases are refused everywhere (ADR 0046 decision 10). Comparison is exact string equality after grammar validation.

### 5.3 Who holds what

| Capability | Owner | Trading expert | Validator | Research lead / engineers | Agents | Workbench operator |
|---|---|---|---|---|---|---|
| Sign with own role key | yes (own) | yes (own) | yes (own) | no | **never** | no |
| Administer approval keys / policies | no | no | no | no | never | separate key-admin role (UNSELECTED) |
| Edit the allowlist file | propose | propose | **review and pin** | propose | propose (text only, never effective) | no |
| Run the verifier | yes | yes | yes (independent environment) | yes | yes (cannot make a failing record pass) | yes |

### 5.4 Signing procedure (signer side; no key ever leaves KMS)

1. Receive the signing request bundle out-of-band (packet + draft spec + request JSON). The freeze tool produces the *unsigned* request (Section 6.1); it holds no key.
2. **Recompute independently**: on the signer's own machine, run the verifier's `request-digest` subcommand (stdlib + `cryptography`; no network) which prints the payload in human-readable form and `digest = SHA-256(message)`; independently recompute `spec_sha256` and each document hash from files the signer obtained themselves. The signer compares what is printed with what they intend to approve. (This is the control against blind signing, T9; it is procedural and the validator spot-checks it.)
3. Sign: `aws kms sign --key-id <full ARN> --message-type DIGEST --message fileb://digest.bin --signing-algorithm ECDSA_SHA_256`, under the signer's own MFA-authenticated session. The 32-byte digest is the only thing KMS sees.
4. Assemble the record (Section 6.2) and return it out-of-band (e.g. validator-controlled drop location), keeping the CLI output and shell transcript as evidence.

### 5.5 CloudTrail and evidence

- KMS `Sign` is recorded in CloudTrail (principal, key ARN, algorithm, message type, source IP, time, request id). **CloudTrail does not record the digest that was signed** (to be confirmed with a test signing in the P0 key-ceremony before relying on it); it therefore proves *that and when a key signed*, not *what*. The record's own signature proves what.
- Reconciliation rule (validator performs at each freeze and each later approval event): the count of CloudTrail `Sign` events per approval key in the period must equal the number of signature records those keys produced (accepted, rejected, withdrawn). An unexplained `Sign` event is an incident (T6 / compromise); a missing event for an existing signature means the signature was produced elsewhere (impossible for KMS keys; indicates a forged or foreign record).
- CloudTrail log file validation enabled; the trail's delivery bucket is outside the signers' write authority. A snapshot (`GetKeyPolicy`, `ListGrants`, `DescribeKey`) is taken at P0 and at each freeze, hashed and stored with the evidence packet (answers T10 detection).
- The signing request id and CloudTrail event id may be stored in the record's non-signed `evidence` block (Section 6.2) for cross-reference.

## 6. How the freeze tool obtains signatures without holding private keys

### 6.1 Two-phase freeze (design of the tool's new behaviour; no code now)

1. `freeze_spec.py --emit-signing-requests DRAFT --packet PACKET_MANIFEST --out-dir DIR`: validates that the draft is complete (all P0 fields set, as today), computes `spec_sha256`, and writes one **unsigned request** per required role: the payload (with `nonce` left for the signer to generate, or generated and stored in the request; recommendation: signer generates) and the digest. It writes no sign-off, fabricates nothing, and holds no key.
2. Signers sign out-of-band (5.4).
3. `freeze_spec.py DRAFT --out FROZEN --approvals DIR --allowlist FILE --pin PIN_RECORD`: runs the **same verifier** (Section 7) over every record. Freezing is refused unless every role required by the (unselected) requirement set has exactly one valid `APPROVE` for this `spec_sha256`. The legacy names-only `signoff.owner/trading_expert/independent_validator` strings are then *derived* from the verified `person_id` values (never typed); a draft whose typed names disagree with the verified signers is refused. Existing behaviour (never overwrite an existing frozen file, round-trip load) is kept.
4. The frozen spec's `signoff` gains `approval_records: [{role, record_sha256, key_id}]` pointers (sign-off remains outside `spec_sha256`, so there is no circularity: records sign the spec hash; the spec hash does not include the records).

A frozen spec with **no** verified approval records is `is_signed = False` for the results guard, exactly as an empty sign-off is today.

### 6.2 Signature record file format

One file per signature: `approvals/<spec12>.<role>.<purpose>.<n>.approval.json`. Strict JSON, canonical re-serialisation must byte-equal the file content (so formatting variants are refused), `loads_strict` on read.

```
{
  "schema_version": 1,
  "payload": { ...as 4.3... },
  "envelope_sha256": "<64 hex: SHA-256(message), i.e. the digest KMS signed>",
  "algorithm": "ECDSA_SHA_256_P256",
  "key_id": "<full KMS key ARN, must equal payload.signer.key_id>",
  "public_key_fingerprint": "<must equal payload.signer.public_key_fingerprint>",
  "signature_b64": "<base64 of the DER signature, strict base64>",
  "evidence": { "cloudtrail_event_id": "...", "kms_request_id": "...", "signed_at_utc": "..." }   // NOT authority; never verified as truth, only displayed
}
record_sha256 = content_sha256(whole record)       # what other documents cite
```

The verifier first checks `key_id` and fingerprint against the allowlist (identity before cryptography, mirroring `witness_protocol.verify_receipt`), then reconstructs `message` itself from `payload` and the domain prefix for `payload.purpose`, recomputes the digest, requires `envelope_sha256` equal, decodes the signature with strict base64, and calls `P256PrehashedVerifier.verify`. A record cannot name a class, a path or an algorithm that is not allowlisted.

## 7. Independent verification

### 7.1 Who verifies, against what

- **Verifier**: a pure, offline, stdlib + `cryptography` tool (`verify_approvals`) with no network, no AWS, no write access to governance state. It is run (a) by the freeze tool, (b) by `results_guard.authorize()` on every result-bearing call (re-verified, not cached), and (c) **by the independent validator in a separate environment on a separate machine at each gate** (P0 exit, P1 data freeze, P4 readiness, any recovery). (c) is the real control; (a) and (b) are convenience and defence in depth, because code running in the research tree can be altered by a writer of that tree (see the boundary design for what that does and does not mean).
- **Pinned public keys**: an `approval_allowlist.json` (strict JSON, canonical hash): one entry per key `{key_id (ARN), public_key_der_b64, public_key_fingerprint, person_id, role, valid_from, valid_until, status: ACTIVE|RETIRED|REVOKED, revoked_effective?, revocation_reason?}`, plus `version`, `prev_allowlist_sha256`.
  - **Obtaining the keys**: the *validator* runs `aws kms get-public-key` themselves for each ARN, compares the DER to the file, and records the fingerprint. The engineer who authored the allowlist does not.
  - **Pinning the allowlist**: the validator signs an `ALLOWLIST_PIN` record (`purpose = ALLOWLIST_PIN`, binds `allowlist_sha256`, `version`, `prev_allowlist_sha256`) with the validator key; the pin's hash is also (i) recorded in the sign-off packet, (ii) published to the external anchor (anchoring design), and (iii) held by the owner. The **validator's own key fingerprint** is bootstrapped out-of-band (read over a separate channel at the key ceremony and recorded in the owner's records), because a signature cannot vouch for its own key. Verification of any approval requires `allowlist_sha256 == the latest valid pin`.
  - Where the verifier gets the pin: from governed configuration outside the agent-writable tree and from the validator's own environment. A pin stored only in a file the agent can edit proves nothing (hardening design 1.6 makes the same point).
- **Key-ID allowlist review**: the validator reviews every allowlist version (diff against the previous, `prev_allowlist_sha256` chain) before pinning. The validator cannot add or approve their *own* key into the allowlist without the owner counter-confirmation (owner signs an `ALLOWLIST_PIN` co-pin for validator-key changes). This is a two-party rule for the trust root.

### 7.2 What the results guard checks (every result-bearing `authorize()`)

1. Loaded frozen spec hash equals recomputed hash (existing).
2. For every required role in the requirement set (UNSELECTED, Section 9): exactly one newest-valid `APPROVE` record with `payload.spec_sha256 ==` this spec, correct `purpose`, role-key binding in the allowlist, `ACTIVE` (or `RETIRED` with `valid_until` after `signed_on` and not revoked), inside `[not_before, not_after]` at the injected clock, signature valid, `packet_sha256` and every document hash equals the packet on disk, allowlist hash equals the pinned one.
3. Distinctness: the set of `key_id`s and `person_id`s across roles has no duplicates (rule SoD-min, Section 9).
4. Exposure binding (Section 10) and, for HOLDOUT, the run-authorization record.
5. Any failure: a named `ApprovalError` subclass; `is_signed` is false; no capability. There is no override, no environment variable, no "warn" mode, and no fall-back to names-only sign-off (the legacy path is deleted, not deprecated).

### 7.3 Rotation

Rotation = new key, new allowlist version. The old key becomes `RETIRED` (`valid_until`), still usable to verify records signed within its validity; new records require the new key. The validator pins the new allowlist; the signer's person_id continuity is attested in the pin record. A rotation never invalidates a frozen spec (approvals are sidecars).

### 7.4 Revocation and key compromise

- **Revocation** is an allowlist version with `status = REVOKED`, `revoked_effective` (UTC) and `revocation_reason`, validator-pinned. The verifier refuses any record from a revoked key whose `signed_on`/KMS evidence time is at or after `revoked_effective`.
- **Compromise** (suspected or confirmed): set `revoked_effective` to the **earliest time compromise cannot be excluded** (not the detection time). Every approval by that key since the last time its use was independently reconciled with CloudTrail (5.5) is `SUSPECT`; those approvals are treated as absent. The affected role re-signs with a new key; because approvals are sidecars of an unchanged `spec_sha256`, **the spec is not re-frozen**. Result-bearing runs are refused while any required role is absent. Runs already completed while an approval was `SUSPECT` are recorded in the trial ledger with an `approval_suspect` note; whether their evidence stands is an owner plus validator decision, recorded and signed (it is never auto-cleared).
- Suspected compromise of the **validator** key additionally invalidates all allowlist pins signed after the reconciliation point; the owner re-pins with an independent reviewer (UNSELECTED who).

### 7.5 Offline verification path

Everything in 7.1-7.4 needs only: the record files, the allowlist file, the pin record, the packet files, the frozen spec, and `cryptography`. No KMS, no network, no repository code from the research tree is required if the validator carries the verifier from a validator-controlled, hash-pinned release (the verifier's own source hash is part of the pin record, so a tampered verifier is detected).

## 8. Fail-closed behaviour

| Condition | Result |
|---|---|
| Any record fails any check | Refuse; named error; no partial credit |
| Allowlist missing, unpinned, hash mismatch, or pin signature invalid | Refuse every result-bearing run |
| KMS or AWS unavailable | **Signing impossible → approval cannot be created → remains unapproved.** No local key, no cached signature, no name-only fallback (mirrors ADR 0046 decision 9). Verification of existing records is unaffected (offline) |
| Key disabled / pending deletion / deleted | New signing impossible; existing records still verify against pinned public key; allowlist status updated by the validator; risk reviewed by owner |
| Clock outside window or unavailable | Refuse (no default clock) |
| Duplicate / conflicting records (fork in supersedes chain; two ACTIVE for the tuple) | Refuse and escalate |
| Verifier or allowlist cannot be loaded | Refuse |
| Reference (Ed25519) algorithm in a governance record | Refuse |

## 9. Role design for D08 (separation of duties)

**Recorded status: role assignments, the set of required signatures and the separation-of-duties rule are UNSELECTED and UNSIGNED.** No person is named here; no key is created; no requirement set is chosen. D08 remains an owner decision.

Roles that can sign under this design: OWNER, TRADING_EXPERT, INDEPENDENT_VALIDATOR (the three fields already in `Signoff`). The research lead and the sole P6 approver appear in the D08 table but have no P0 signing purpose in this design; the P6 approver's signature is a later, separate purpose (not designed here).

Separation-of-duties rule options (none selected):

| Option | Rule | Enforced by | Weakness |
|---|---|---|---|
| SoD-A | Three distinct humans, three distinct keys, for owner / trading expert / validator | Distinct `key_id` and `person_id` (technical) + identity attestation (procedural) | Technical check cannot prove two keys are two people |
| SoD-B | Owner and trading expert may be the same person; validator must be a different person | Same, with explicit recorded waiver | Per D08 sheet: D19 candidate review is then not independent of the final approver |
| SoD-C | Validator must also be distinct from the research lead and from whoever wrote the engine | Procedural + signed attestation by the validator | Needs a recorded engineer list |
| SoD-D | Any role overlap permitted | n/a | Defeats independent review; shown only for completeness |

**Recommendation (not a decision):** the owner and the independent validator are **distinct individuals with distinct keys and distinct IAM principals**, with SoD-A as the target and SoD-C as the minimum acceptable; the validator is the party that reviews and pins the key allowlist (Section 7.1) and must therefore never be a person whose key the owner or the engine author can control. If the owner is also the trading-expert reviewer (SoD-B), the design records that explicitly as a waiver in the requirement set rather than leaving it implicit. No AI agent may hold a role, a key or a principal (R9).

Requirement matrix (to be completed by the owner; all rows blank):

| Artefact | Owner signature | Trading expert | Independent validator | Other |
|---|---|---|---|---|
| Spec freeze (P0 exit) | | | | |
| Addendum A1 (section 10) | | | | |
| Decision sheets D01-D19 (packet-level or per-decision) | | | | |
| Exposure ledger (H3, Section 10) | | | | |
| Allowlist pin / rotation / revocation | | | | |
| Holdout recovery (hardening 1.6) | | | | |
| Torn-tail adjudication | | | | |

## 10. H3: the exposure ledger bound to the approved spec

### 10.1 The binding chain

```
spec.governance.exposure_signed          (inside spec content; therefore inside spec_sha256)
   = { ledger_sha256, statement_id }     # NOT the approval record hash: that would be circular
        |
        v   must equal
exposure ledger canonical sha256         # content_sha256 of the ledger document, with its own `signoff`
        |                                # block excluded from the hash (same rule as the spec)
        v   cited by
EXPOSURE_LEDGER_APPROVAL record          # payload binds { ledger_sha256, spec_sha256, ... }, signed (OWNER required;
                                         #   INDEPENDENT_VALIDATOR co-sign is a recommendation, Q-A6)
```

- **No cycle.** The spec contains the *ledger hash*, not the approval record hash. The approval record contains both the ledger hash and the spec hash. Because the spec hash already covers `governance.exposure_signed.ledger_sha256`, an approval of the spec transitively commits to that exact ledger, and the separate ledger-approval record adds an explicit, role-attributed attestation about the ledger content (the D01 conclusion).
- **Clarification of hardening design 3.6.** That section places `signoff.signature` and `classifications[].signature` *inside* the ledger document. If the ledger hash covered those fields the signature would sign a hash that includes itself. This design therefore requires: **the ledger's canonical hash covers `entries` (and `schema_version`) only; signature material lives in sidecar records or in a block excluded from the hash**, exactly like the spec's `signoff`. This refines, and does not contradict, the hardening design's intent (signed, hash-pinned, strict loader).
- The ledger payload (`EXPOSURE_LEDGER_APPROVAL`, domain `range002.exposure-approval.v1\n`) carries: `schema_version`, `purpose`, `spec_sha256`, `ledger_sha256`, `entries_count`, `entries_digest` (hash over the sorted entry ids and windows), `d01_conclusion_sha256` (hash of the owner's signed exposure/holdout conclusion text), `signer`, `role`, `decision`, `signed_on`, window, `nonce`, `supersedes`.

### 10.2 What the guard verifies

On each result-bearing `authorize()`: (1) `exposure_ledger.sha256 == spec.governance.exposure_signed.ledger_sha256`; (2) a valid `EXPOSURE_LEDGER_APPROVAL` exists for this `(spec_sha256, ledger_sha256)` with the required signers under the pinned allowlist; (3) the legacy `signoff {signed_by, signed_on}` strings are ignored for authority; (4) the capability records `exposure_ledger_sha256` and the approval `record_sha256`; (5) a ledger swapped for another (even empty and "signed") fails (1). Any miss refuses with `ExposureLedgerNotSignedError` / a new named subclass.

### 10.3 Changes after freeze

A ledger edit after P0 changes `ledger_sha256` and is refused against the frozen spec. A superseding ledger therefore requires a **new spec** (a governed, owner-decided event) or an explicit owner-decided amendment path not designed here (Q-A7). Classification (severity) records are not accepted at all until the policy exists (see the companion design, section on F).

## 11. Invariants

- I-S1 No private key material is ever read, written or held by any repository code, freeze tool, verifier, guard, agent or research environment.
- I-S2 No new dependency, no new boto3 import location; `check_aws_sdk_isolation.sh` and ADR 0046 stand unchanged.
- I-S3 Every approval is bound to exactly one spec hash, one role, one purpose, one packet, one key; replays across any of these are refused.
- I-S4 Trust roots (public keys, allowlist pin, verifier hash) come from outside the agent-writable tree and are validator-controlled.
- I-S5 Fail closed everywhere; no fallback to names-only, to a reference algorithm, or to a locally held key.
- I-S6 Approvals are append-only sidecars; the frozen spec is never mutated; revocation removes authority without altering history.
- I-S7 Roles are filled by humans; agents hold none.

## 12. Test plan (negative first; each must fail on the unfixed design)

1. Names-only freeze (no records) is refused; typed names that disagree with verified signers are refused.
2. Bad signature; signature over a different digest; truncated or non-strict-base64 signature; DER with trailing bytes.
3. Wrong key (not in allowlist); key in allowlist for another role; key revoked; key retired but record dated after `valid_until`; allowlist pin missing, mismatched, signed by non-validator key, signed by a revoked validator key.
4. Replay matrix: other spec, other role, other purpose (approval presented as recovery/exposure/run-authorization), other packet, one packet document altered after signing, expired, not yet valid, superseded record presented, withdrawn record presented, duplicate nonce, fork in the supersedes chain.
5. Domain separation property test: for every ordered pair of purposes, a valid signature for one never verifies as the other.
6. Algorithm negatives: Ed25519 record; RSA key in allowlist; P-384; non-DER key; alias instead of ARN; ARN case/whitespace variants; mismatched fingerprint.
7. Strictness: duplicate JSON keys, NaN, floats in payload, unknown keys, missing keys, non-canonical formatting (must byte-equal canonical), BOM, CRLF.
8. Separation: same `key_id` in two roles; same `person_id` in two roles; key shared by owner and validator; agent-environment principal in the allowlist.
9. Exposure binding: ledger swapped; ledger edited by one byte after approval; ledger approval for another spec; spec `exposure_signed.ledger_sha256` missing or not hex; legacy `signoff` strings present with no record; v1 ledger given to a v2 guard.
10. Fail-closed: verifier cannot load allowlist; clock source missing; any exception inside verification yields refusal, never a pass; no code path accepts when an exception is swallowed (AST/grep test for bare `except` in the module).
11. No-bypass pin test: the public API and signatures of the approval module contain no force/skip/override/env-var parameter (same technique as `REGISTRY_PUBLIC_API`).
12. Isolation lint: no `boto3`/`botocore` import in `range002/**`; no import of `app.validation.aws`; verifier imports only stdlib, `cryptography` and (if the owner allows, Q-A8) `witness_protocol`.
13. Cross-environment: the verifier release run on a clean interpreter without the research tree produces the identical verdict (offline path).
14. KMS contract tests use recorded fixtures/`Stubber`-style doubles only in the (later, separately reviewed) ceremony tooling; the verifier tests need no AWS and no credentials.
15. Positive path last: complete packet, three records, allowlist + pin, freeze succeeds, guard authorizes; revoke one key, guard refuses; re-sign with new key, guard authorizes again with the **same** `spec_sha256`.
16. Coverage: the approval and verification module is high-stakes; target >= 95% (same bar as `app/risk/`).

## 13. Review steps (before any code; and for the later code)

1. Owner reviews this design item by item; trading expert and independent validator (once named) each review Sections 4, 7, 9 for their own role's control.
2. A security review of the key-policy text (5.2) by someone other than the key administrator, before any key exists.
3. A **dry-run key ceremony** in a throw-away AWS context using test keys (recorded commands, CloudTrail confirmed to log `Sign`, confirm the digest is not recorded), with its evidence stored per GITHUB-OPS-001 (generated evidence to controlled S3 with Version ID and SHA-256).
4. Implementation PRs (later) follow CLAUDE.md walk-away discipline (this is consequential governance: >= 2 hours), negative tests first, local lint/mypy/targeted pytest before the single push (GITHUB-OPS-001).
5. The validator runs the offline verifier from their own environment against a fixture packet before any real signature is requested.

## 14. What this design does not do

- It does not create keys, accounts, roles, policies or any AWS resource, and it does not call AWS.
- It does not name any person, choose any role assignment, any requirement set, any SoD rule or any validity window.
- It does not add a dependency, a boto3 import, or an ADR-requiring component (a repo tool that calls `kms:Sign` would; it is not proposed).
- It does not change a gate, threshold, spec value, partition, or the frozen-spec hash rule.
- It does not protect against an attacker holding all required signing keys, against an AWS account administrator rewriting key policy (detected, not prevented), or against signer coercion.
- It does not prove that two keys belong to two people; that is a procedural attestation by the validator.
- It does not remove the legacy `signoff` names; it stops treating them as authority.
- It does not provide the execution boundary, anchoring or recovery mechanisms (companion design).

## 15. Open owner questions

- **Q-A1** KMS as the only signing mechanism, or is a hardware P-256 key an allowed equivalent for a named signer?
- **Q-A2** Approval keys in a separate AWS account (recommended) or the same account with explicit denies? Who is the key administrator (must not be a signer)?
- **Q-A3** Validity-window length for approvals (recommended <= 30 days) and whether `signed_on` or KMS evidence time governs revocation ordering.
- **Q-A4** Is the validator's key fingerprint bootstrapped by the owner in person, or by another channel?
- **Q-A5** Exact packet composition and whether decisions are attested per-decision or packet-level.
- **Q-A6** Is an independent-validator co-signature required on the exposure ledger (recommended)?
- **Q-A7** Is any post-freeze ledger amendment path wanted, or is "new spec" the only path?
- **Q-A8** May `range002/governance` import `app.validation.witness_protocol` (cryptography-only, SDK-free per ADR 0046 decision 4), or must the verifier be a standalone module?
- **Q-A9** Who attests identity (person-to-key) and how often?

## 16. Decision table (all rows blank; none selected; none signed)

| ID | Decision | Options | Recommendation (not a decision) | Owner decision | Signature | Date |
|---|---|---|---|---|---|---|
| AS-1 | Signing mechanism | KMS P-256 / hardware P-256 / other | KMS `ECC_NIST_P256` per ADR 0045/0046 | | | |
| AS-2 | Approval key account and key administrator | Separate account / same account with denies | Separate account; admin distinct from signers | | | |
| AS-3 | D08 roles named (research lead, trading expert, validator, P6 approver) | per D08 sheet | Four distinct humans where possible | | | |
| AS-4 | Separation-of-duties rule | SoD-A / B / C / D | Owner and validator distinct; SoD-A target, SoD-C minimum | | | |
| AS-5 | Required signatures per artefact (matrix in section 9) | | Owner + validator on spec and ledger | | | |
| AS-6 | Validity window and revocation-time rule | | Short window; earliest-possible-compromise time | | | |
| AS-7 | Allowlist custody and two-party pin rule | | Validator pins; owner co-pins validator-key changes | | | |
| AS-8 | Exposure ledger binding and co-signature | | Hash-pinned in spec + owner record + validator co-sign | | | |
| AS-9 | Dry-run key ceremony approved before any real key | | Yes | | | |
