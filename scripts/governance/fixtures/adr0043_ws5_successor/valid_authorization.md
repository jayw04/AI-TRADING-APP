# ADR0043-LIVE-CANARY-WS5-SUCCESSOR-START-001 (DRAFT — NOT EFFECTIVE — NOT INVOKED)

| Field | Value |
|-------|-------|
| Document ID | ADR0043-LIVE-CANARY-WS5-SUCCESSOR-START-001 |
| Status | **DRAFT — NOT EFFECTIVE — NOT INVOKED** |
| Execution mode | `ADOPT-CLEAN-UNUSED-RESOURCES` |
| Prior authorization | `52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae` — terminal disposition **REFUSED** |
| Body SHA-256 | *(computed at freeze; recorded in §18)* |
| Verifier | `scripts/governance/hash_adr0043_ws5_successor_authorization.py authorization` |
| Date | 2026-08-03 |

> 🚧 **DRAFT — NOT EFFECTIVE — NOT INVOKED.** Nothing in this document authorizes any action.
> No effectiveness record exists, no credential is staged, no image is pulled or run on the governed
> runtime, no AWS resource is rebound or retagged, no database exists, no migration has run, and no
> broker call has been made. Legacy Phase 2 remains held.

---

## 1. Authorized scope, if made effective

Prepare and operate a **read-only** canary readiness workstream on a clean, previously unused runtime,
adopting resources created under a terminally refused authorization without erasing that history:

1. Adopt each clean resource individually and bind its history (Stage A).
2. Verify the authorized image by digest, stage the dedicated credential, and prepare an inert,
   non-autostarting container definition (Stage B).
3. Perform governed read-only reconciliation against the authorized broker account (Stage C).
4. Seal readiness evidence and issue one terminal disposition (Stage D).

## 2. Non-negotiable prohibitions

- any broker **mutation**: order submit / replace / cancel, position close, account configuration
  change, paper-account reset, funding or transfer;
- Start A, Start B, Phase 0, A1–A5, ENFORCE, D-WIRE;
- authoritative session-baseline capture or persistence;
- executing the default application image `Cmd`;
- running Alembic outside an explicitly authorized, separately checkpointed step;
- scheduler or strategy activation;
- modification of the legacy canary `i-01527ac7b7c7efa35` or any of its volumes;
- use of `ALPACA_PAPER_7_*` as the runtime credential name — it collides with Workbench account 7 and
  strategy 9 (`combined-book`, historically `PA3344TNRFYD`).

## 3. Relationship to the prior refused attempt

This authorization **does not amend, cure, reopen, extend or erase** the prior attempt. Authorization
`52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae` reached terminal disposition
**REFUSED** and remains refused. Its refusal record —
`ADR0043_LIVE_CANARY_WS5_OPENING_RECORD_001.md` §11 — stays attached and immutable.

```
prior_authorization_sha  = 52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae
prior_disposition        = REFUSED
prior_refusal_reasons    = ACTIVE_RESTARTABLE_LEGACY_RUNTIME · SHARED_TRADING_CAPABLE_CREDENTIAL
                           ACCOUNT_CONSUMER_EXCLUSIVITY_NOT_PROVEN
                           BROKER_WRITE_CONTROL_1_ABSENT · BROKER_WRITE_CONTROL_2_ABSENT
                           AUTHORIZED_IMAGE_PIN_PREVENTS_REMEDIATION
remediation_evidence     = PR #598 (governed broker boundary, both write-prevention controls)
                           PR #599 (Stage-C runner; the prior image had the capability but no procedure)
                           legacy Phase-1 preservation (snapshot snap-01d3da50af60eeffb + 31 objects)
changed_circumstance     = new broker account, new source commit, new deployable image
```

## 4. Adopted resources and ownership

`execution_mode = ADOPT-CLEAN-UNUSED-RESOURCES`. Every adopted resource is named individually; nothing
is adopted by pattern, tag sweep or inference.

```
runtime_instance   = i-0fff7076ad461aa9a
data_volume        = vol-0710769fb6981102d
security_group     = sg-08b1284b33d9159c4
iam_role           = adr0043-canary-ws5-52b3ff136196-role
instance_profile   = adr0043-canary-ws5-52b3ff136196-profile
runtime_stack      = adr0043-canary-ws5-52b3ff136196
evidence_stack     = adr0043-canary-ws5-52b3ff136196-evidence
ecr_repository     = 219024422756.dkr.ecr.us-east-1.amazonaws.com/adr0043-canary-ws5
evidence_store     = s3://adr0043-ws5-evidence-219024422756-us-east-1
```

**Cleanliness at adoption** — each verified before Stage A completes:

```
container_created          = false
database_created           = false
credential_attached        = false
broker_called_from_runtime = false
migration_applied          = false
application_started        = false
```

### 4A. Resource-history binding

Adoption preserves origin history rather than overwriting it:

```
origin_authorization_sha    = 52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae
resource_history            = CREATED_UNDER_REFUSED_AUTHORIZATION_THEN_EXPLICITLY_ADOPTED
```

The successor `authorization_sha` tag value is applied additively at Stage A and equals the
authorization identity recorded in §18. `expires_on` is `effective_at + 336 hours exactly` (§14).

Successor tags are **additive**. The origin `authorization_sha` tag value is retained in the
resource-history record so a reviewer can reconstruct which authorization created each resource.
Loss of prior binding history is a stop condition (§10).

### 4B. Frozen source and image identity

```
authorized_source_commit  = 1880fcdb05e367306e81fa96b355b996f73b7819
source_archive_sha256     = 17d24c3ead5ee00029b63b6d8df89cf8122bf078cc227efe6fe539d41731dd7c
source_object_version_id  = dEDhokQBpFY8u9AyF7KM0aHX1wDnEEpu
Dockerfile_sha256         = e4ee353aed8abdce98e8ac7881b928dcbb9c30ab1abef04dea0e261ae6be9042
image_manifest_digest     = sha256:c0c1b0c48fbb4d4318207f589ee9a64ee795ca34100028bfd84d4d9d81c6a54d
image_index_digest        = sha256:59f3f26123ca0c19174fefc06575f960bb2c50c555c9eba23b0aaeb22f78071d
image_config_digest       = sha256:a3c2081f067bc412061e285661264ab91a3ca20797d9f38c94cf72467cc9f584
attestation_digest        = sha256:04f8a047f94c4b3bb69d5908db0269416d040319dcb832c3441b379d05e72f5f
sbom_digest               = sha256:eae1ae6e977f8aeb9eabee6524d5d2d3232b23ca52c8bf5266ef01b1d2def07e
provenance_digest         = sha256:c303de1baba56c0e0d00ad3196e7928450da83aca1e5a99d04c4e7b1060e016b
platform                  = linux/arm64
```

**Deployment identity.**

Only `sha256:c0c1b0c48fbb4d4318207f589ee9a64ee795ca34100028bfd84d4d9d81c6a54d` is the deployable and authoritative image identity.

The image index digest is **not** deployable; it resolves to a multi-manifest list and is retained as
supporting provenance only, as are the config, attestation, SBOM and provenance digests.

**Prior artifacts, retained and never deployed:**

```
7342ebbd… / sha256:37e52bc9…  = PRIOR_STAGE1_ARTIFACT
ed604d49… / sha256:825ac355…  = SUPERSEDED_PREAUTH_ARTIFACT
```

### 4C. Canonical binding manifest

Every frozen operational identity, bound cryptographically. The verifier **extracts these values from
this block** and hashes them as an ordered manifest — it does not assert them from a hardcoded list,
because asserting a value appears somewhere is not the same as binding it. Changing any line here
changes `binding_manifest_sha256` and therefore the authorization identity.

```
document_id                  = ADR0043-LIVE-CANARY-WS5-SUCCESSOR-START-001
execution_mode               = ADOPT-CLEAN-UNUSED-RESOURCES
prior_authorization_sha      = 52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae
prior_disposition            = REFUSED
runtime_instance             = i-0fff7076ad461aa9a
data_volume                  = vol-0710769fb6981102d
security_group               = sg-08b1284b33d9159c4
iam_role                     = adr0043-canary-ws5-52b3ff136196-role
instance_profile             = adr0043-canary-ws5-52b3ff136196-profile
runtime_stack                = adr0043-canary-ws5-52b3ff136196
evidence_stack               = adr0043-canary-ws5-52b3ff136196-evidence
ecr_repository               = 219024422756.dkr.ecr.us-east-1.amazonaws.com/adr0043-canary-ws5
evidence_bucket              = adr0043-ws5-evidence-219024422756-us-east-1
runtime_name                 = adr0043-canary-ws5-52b3ff136196
broker_account_id            = PA3E97RWHKQZ
alpaca_account_id            = 0fa55b0d-74d6-4a61-a361-ab154857cfb5
credential_key_fingerprint   = ffab8796516a
credential_secret_fingerprint = c2cab6509f1b
credential_name_prefix       = ADR0043_SUCCESSOR_CANARY_ALPACA_
authorized_source_commit     = 1880fcdb05e367306e81fa96b355b996f73b7819
source_archive_sha256        = 17d24c3ead5ee00029b63b6d8df89cf8122bf078cc227efe6fe539d41731dd7c
source_object_version_id     = dEDhokQBpFY8u9AyF7KM0aHX1wDnEEpu
dockerfile_sha256            = e4ee353aed8abdce98e8ac7881b928dcbb9c30ab1abef04dea0e261ae6be9042
image_manifest_digest        = sha256:c0c1b0c48fbb4d4318207f589ee9a64ee795ca34100028bfd84d4d9d81c6a54d
image_index_digest           = sha256:59f3f26123ca0c19174fefc06575f960bb2c50c555c9eba23b0aaeb22f78071d
image_config_digest          = sha256:a3c2081f067bc412061e285661264ab91a3ca20797d9f38c94cf72467cc9f584
platform                     = linux/arm64
evidence_directory           = /var/lib/adr0043-ws5/evidence
database_identity            = vol-0710769fb6981102d :: /var/lib/adr0043-ws5/workbench.sqlite
reserved_database_path       = /var/lib/adr0043-ws5/workbench.sqlite
initial_database_state       = RESERVED_PATH_NOT_CREATED
broker_access_mode           = read_only
strategy_execution_enabled   = false
scheduler_enabled            = false
alpaca_startup_enabled       = false
container_restart_policy     = no
permitted_endpoints          = GET /v2/account | GET /v2/positions | GET /v2/orders | GET /v2/account/activities
expiration_rule              = authorization_effective_at + 336 hours exactly
effectiveness_precondition   = owner approval + merge to main + independent hash recomputation + merge SHA recorded
```

**What is deliberately *not* in the manifest, and why.** The concrete `authorization_effective_at` and
`expires_on` values do not exist at freeze time — they are produced by the effective merge. Binding a
value that does not yet exist is impossible; a placeholder would change at effectiveness and break the
very identity it was meant to fix. They are instead bound by the §18 effectiveness record: merge SHA,
plus independent recomputation of this authorization identity from the `main` blob. The expiration
*rule* is bound above.

## 5. Infrastructure ceiling

**Authorized:** additive tagging of the adopted resources; pulling the authorized image by digest;
creating **one** inert Stage-C container; writing evidence to the evidence path (§7).

**Prohibited:** creating new runtimes, volumes, security groups or roles; modifying shared or
production networks; changing the legacy canary; broadening the instance role; any inbound network
exposure; scheduler or strategy activation.

## 6. Broker-access ceiling

Permitted read operations, and nothing else:

```
GET /v2/account
GET /v2/positions
GET /v2/orders
GET /v2/account/activities
```

The first broker call **must** be `GET /v2/account`. Identity handling:

```
account_number == PA3E97RWHKQZ  -> continue the remaining approved reads
account_number mismatch          -> REFUSED, client latches closed, no further reads
request failure                  -> INCONCLUSIVE, no further reads
```

```
broker_account_id             = PA3E97RWHKQZ
alpaca_account_id             = 0fa55b0d-74d6-4a61-a361-ab154857cfb5
credential_key_fingerprint    = ffab8796516a
credential_secret_fingerprint = c2cab6509f1b
credential_name               = ADR0043_SUCCESSOR_CANARY_ALPACA_*
```

The credential is trading-capable by construction (Alpaca issues no read-only paper scope), so both
write-prevention controls of §8 are mandatory, not advisory.

## 7. Database ceiling and evidence path

```
database_identity      = vol-0710769fb6981102d :: /var/lib/adr0043-ws5/workbench.sqlite
initial_database_state = RESERVED_PATH_NOT_CREATED
evidence_path          = /var/lib/adr0043-ws5/evidence
```

The Stage-C container mounts **only** `/var/lib/adr0043-ws5/evidence`.

The data-volume root is not mounted into Stage C, so no writable mount contains the reserved database path.

**Preflight required before Stage C** (all must hold):

- `/var/lib/adr0043-ws5/workbench.sqlite` absent;
- the evidence directory exists and is writable;
- the volume root is not mounted into the Stage-C container;
- no database-capable application entrypoint is invoked.

Migration, if ever authorized, occurs as a **separate one-shot step under its own checkpoint** — never
as a side effect of container startup. That separation exists because the image's default `Cmd` runs
`alembic upgrade head` before the application, and an implicit startup would migrate without an
explicit decision.

## 8. Inert posture and write-prevention controls

```
WORKBENCH_BROKER_ACCESS_MODE=read_only
WORKBENCH_STRATEGY_EXECUTION_ENABLED=false
WORKBENCH_SCHEDULER_ENABLED=false
WORKBENCH_ALPACA_STARTUP_ENABLED=false
WORKBENCH_BROKER_EXPECTED_ACCOUNT_ID=PA3E97RWHKQZ
container_restart_policy=no
application_autostart=false
compose_autostart=false
```

**Control 1 — execution authority gate.** `app/brokers/policy.py`: order capability requires
`mode is TRADING` **and** `strategy_execution_enabled` **and** `scheduler_enabled`. Absent
configuration resolves to `disabled`; an unrecognised value raises at startup.

**Control 2 — read-only broker boundary.** `app/brokers/transport.py` and `readonly_client.py`: the
policy check precedes dispatch, so a denied operation produces zero network calls. Non-GET methods,
unapproved paths, traversal forms, absolute URLs, alternate hosts, redirects and generic passthrough
are all refused.

Both controls are gated on `broker_access_mode`, so in `read_only` the legacy trading-capable
construction sites (`lifespan`, `OrderRouter`, `BrokerRegistry`, `TradeUpdatesStream`) cannot build a
client at all.

## 9. Reachability handling

Stage C computes **non-authoritative** reconciliation only. Financial values are evidence, never a
baseline: every record carries `authoritative_start_a_baseline = false`. A Stage-C result cannot
override a later Start A determination.

## 10. Mechanical stop conditions

Stop immediately and classify per §11 on any of:

- account identity mismatch;
- credential fingerprint mismatch;
- image digest mismatch, or execution of any image other than the authorized deployable manifest;
- source revision mismatch;
- any mutation attempt, or any call to an unapproved broker endpoint;
- database or Alembic state outside the authorized sequence;
- creation of `/var/lib/adr0043-ws5/workbench.sqlite` outside an authorized migration checkpoint;
- a writable mount containing the reserved database path;
- unexpected positions, orders or account activities;
- any adopted resource identity mismatch;
- loss or overwrite of prior authorization binding history;
- execution of the default image `Cmd`;
- any legacy broker client construction.

## 11. Dispositions

| Disposition | Exit code | Meaning |
|---|---|---|
| `READY` | 0 | All four approved reads completed, identity verified, evidence sealed. Only a `READY` result may be submitted to WS6; it does not authorize the WS6 seal or Start A. |
| `REFUSED` | 2 | A stop condition fired |
| `INCONCLUSIVE` | 3 | Valid work began but evidence or connectivity prevents a trustworthy conclusion |

A CLI parse failure produces **no** Stage-C artifact and is classified outside this table as
`CLI_INVOCATION_ERROR`; it returns to the prior stage and is never a broker refusal. Classification
uses artifact presence **and** the disposition field **and** the exit code — never the exit code alone,
because `argparse` and `REFUSED` both exit 2.

## 12. Evidence integrity and digest terminology

```
artifact_sha256      = SHA-256 of the canonical JSON record BEFORE the artifact_sha256 field
                       is inserted  (the runner's existing internal field; deliberately not renamed)
evidence_file_sha256 = SHA-256 of the complete serialized evidence file, recorded externally
```

Both are reproduced independently by
`scripts/governance/hash_adr0043_ws5_successor_authorization.py stage-c-evidence`. Evidence is
published atomically — temp file, validate, hash, rename — so a partial record never appears at the
destination path. `mutation_attempt_count` must be `0` in every record.

## 13. Exit criteria

- Every adopted resource verified and history-bound (Stage A).
- Image verified by digest; credential staged by fingerprint; inert container definition prepared (Stage B).
- All four approved reads completed in order, identity first (Stage C).
- Evidence sealed, both digests independently reproduced, terminal disposition issued (Stage D).
- Explicit statement that no authoritative baseline was persisted and no order was submitted.

## 14. Expiration, clock disclosure and anti-laundering

```
authorization_effective_at = authoritative GitHub merged_at timestamp of the effectiveness-trigger PR
expiration_rule            = authorization_effective_at + 336 hours exactly
```

UTC timestamps are authoritative. Local-time renderings are informational only. No end-of-day rounding or extension is permitted.

The rule is stated under the key `expiration_rule`, deliberately not under `expires_on`. Exclusion from
the body hash is applied **by key name** (§17), so a rule written as `expires_on = …` inside sections
1–16 would be blanked before hashing and the rule itself would become unbound. `expiration_rule` is
hashed here and in §4C, and its value is additionally pinned by the verifier. `expires_on` names only
the *concrete* timestamp, which does not exist at freeze time and is derived mechanically from this
rule at effectiveness and recorded in §18.

**Fresh-clock disclosure.** This is a new authorization governing a new broker account, a new source
commit, a new deployable image and explicit adoption of unused resources after a terminal REFUSED
disposition. It **does not restart, extend or amend the prior authorization clock**. The prior
authorization's own ceiling (`2026-08-16T23:59:59 America/Chicago`) is unaffected and its refusal
stands.

**Anti-laundering.** Every terminal REFUSED disposition requires a documented owner adjudication
before any successor start authorization may be drafted, and a successor must identify the prior
refusal, the defect or changed circumstance, the remediation evidence, and why a new clock is
operationally necessary (§3). After **two consecutive REFUSED** start authorizations for this
workstream, no third successor authorization may be drafted without a broader architecture and
governance review. For counting: the original WS5 authorization is refusal 1; this document is
attempt 2. `INCONCLUSIVE` does not automatically consume a refusal count, but repeated inconclusive
attempts require owner adjudication before retry.

**Pre-effectiveness withdrawal.** A distinct state exists for an authorization that the owner approved
and then withdrew before it became effective:

```
OWNER_APPROVAL_WITHDRAWN_BEFORE_EFFECTIVENESS
  authorization became effective = no
  governed stage invoked         = no
  counts as REFUSED              = no
  consumes refusal count         = no
```

It is not a refusal, because nothing became effective and no governed stage was invoked. To prevent it
becoming a loophole parallel to repeated refusal: two consecutive pre-effectiveness owner-approval withdrawals caused by substantive authorization defects require broader architecture and governance review before another effectiveness trigger may be proposed. Purely administrative withdrawal — such as closing a duplicate PR without changing the authorization — does not count.

**Expiration is fixed by identity, not chosen by an operator.** The effectiveness completion record may not select, shorten, extend, round, or otherwise redefine `expires_on`. It must mechanically derive the timestamp from the frozen authorization rule. This restriction does not prevent the owner from explicitly revoking or terminating authorization early through a separately governed revocation record; early revocation ends authority but does not redefine the originally frozen expiration rule.

## 15. Stage model

No stage implicitly invokes the next; each requires its own explicit invocation.

### Stage A — adoption and resource-history binding

Verify and explicitly adopt each §4 resource, confirm the cleanliness assertions, and bind the
resource history additively. **No credential, container, database, migration or broker call.**

### Stage B — inert image and credential preparation

Permitted, each behind its own named checkpoint:

- **B1** verify the exact deployable manifest digest;
- **B2** pull the authorized image by digest;
- **B3** prepare a no-restart, non-autostart Stage-C container definition;
- **B4** stage the dedicated successor credential narrowly, and verify its fingerprints **without**
  broker access.

Container creation and credential attachment are separate checkpoints; neither is implicit.

### Stage C — governed read-only reconciliation

Invoke **only**:

```
python -m app.brokers.adr0043_reconcile --output /var/lib/adr0043-ws5/evidence/<run>.json \
  --source-commit 1880fcdb05e367306e81fa96b355b996f73b7819 \
  --image-digest sha256:c0c1b0c48fbb4d4318207f589ee9a64ee795ca34100028bfd84d4d9d81c6a54d
```

with a complete command override. The default image `Cmd` must **never** execute — it runs
`alembic upgrade head`, seed data and the application. The image declares no `ENTRYPOINT`, so a
command override replaces `Cmd` entirely.

### Stage D — readiness evidence and terminal disposition

Seal evidence, independently reproduce `artifact_sha256` and `evidence_file_sha256`, determine
readiness, issue one terminal disposition, and stop. Stage D does **not** authorize Start A, Start B,
Phase 0, order activity or the default application.

## 16. Controlled artifact replacement and stage regression

**Pre-deployment artifact replacement.** A replacement image may be proposed **only before every one
of** the following has occurred:

```
credential attached · Stage-C container created · database created
migration run · broker call made · authorized image executed
```

It requires a reviewed and merged source commit, fully green CI, a new immutable deployable digest, an
owner-approved replacement record, permanent **retirement (not deletion)** of the prior digest, and
preservation of every prior binding.

Controlled artifact replacement closes at the first occurrence of any listed closure event performed under this effective successor authorization:

```
1. successor credential attached to the governed WS5 runtime
2. persistent or Stage-C container created from the authorized image
3. successor database created
4. successor migration executed
5. broker request dispatched from WS5
6. authorized image executed on WS5 as Stage B/C operational activity
```

The qualifier "under this effective successor authorization" is load-bearing. Prior ephemeral image-verification gates do not constitute a closure event: they ran before effectiveness, used no credential, created no persistent container, and were not Stage B or Stage C activity. After any listed event occurs, replacement is closed.

**Stage regression.** A recoverable Stage-C packaging or evidence-write failure seals the failed
attempt and may **return to Stage B**. Each attempt receives its own run ID and sealed result;
regression never erases evidence from a failed attempt.

Regression is **not** available for the following, which are REFUSED, or `INCONCLUSIVE` where evidence integrity is merely ambiguous:

- account mismatch, credential mismatch — REFUSED
- mutation attempt, unapproved endpoint — REFUSED
- provenance mismatch, image mismatch — REFUSED
- unexpected account state, resource-history loss — REFUSED or owner adjudication

## 17. Authorization body-hash computation

`authorization_body_sha256` = SHA-256 over the canonical UTF-8 bytes of sections **1–16**, excluding
only values unknowable until effectiveness or runtime:

```
normative exclusions = authorization_sha
                       expires_on
```

Only those two. `authorization_sha` is self-referential; the concrete `expires_on` does not exist until
effectiveness. Exclusion is applied **by key name**: any `expires_on = …` line inside sections 1–16 is
blanked before hashing, whatever it says. The expiration **rule** is therefore stated under the distinct
key `expiration_rule` (§4C and §14) and remains hashed; the verifier additionally pins its value and
refuses any expiration rule stated under the excluded key. `database_identity` is **not** excluded — it is a
fixed known value bound by the §4C manifest, and any statement to the contrary is a defect. Ruling and
status metadata and the §19 history sit outside sections 1–16 and are therefore outside the body hash
by construction rather than by exclusion.

**Canonicalization.** Extract `## 1.` up to `## 17.`; replace each excluded scalar's value with
`<EXCLUDED>`; normalize line endings to `\n`; strip trailing whitespace per line; drop trailing blank
lines; UTF-8 encode; SHA-256. Reference implementation:
`scripts/governance/hash_adr0043_ws5_successor_authorization.py`, whose structural contract is tested
by `apps/backend/tests/scripts/test_hash_adr0043_ws5_successor_authorization.py`.

## 18. Effectiveness

**NOT EFFECTIVE. NOT INVOKED.**

```
status                       = DRAFT — NOT EFFECTIVE — NOT INVOKED
authorization_body_sha256    = <recorded at owner approval over the frozen body>
successor_authorization_sha  = <same value, once frozen>
authorization_merge_sha      = <recorded at the effective merge>
authorization_effective_at   = <recorded at the effective merge>
expires_on                   = <effective_at + 336 hours exactly, §14>
```

Effectiveness requires: owner approval over the frozen body; merge to `main`; independent
recomputation of the canonical body hash from the `main` blob; and the merge SHA recorded. Merge alone
does not invoke any stage — Stage A requires its own explicit invocation.

## 19. Document control

| Rev | Date | Change |
|-----|------|--------|
| draft | 2026-08-03 | Initial draft against the tested structural contract. Verifier and fixtures written first; the document was drafted to satisfy an already-failing test suite. **NOT EFFECTIVE — NOT INVOKED.** |
| amendment-1 | 2026-08-03 | **Consolidated pre-effectiveness amendment.** (1) **Expiration made exact.** The prior rule was deterministic but could extend authority by up to approximately 24 hours beyond the intended 336-hour maximum. The practical risk was limited for this read-only workflow, but the rule was corrected before effectiveness because this was the last low-cost opportunity to establish an exact-duration authorization window. All four statements of the rule (§4A, §4C, §14, §18) now read `authorization_effective_at + 336 hours exactly`, with UTC authoritative and local renderings informational. (2) **Stale §17 exclusion statement corrected** — the document claimed `database_identity` was excluded from the hash, contradicting its own verifier, whose exclusion set is `{authorization_sha, expires_on}`; `database_identity` is bound by the §4C manifest. Discovered during the pre-effectiveness sweep. (3) **`OWNER_APPROVAL_WITHDRAWN_BEFORE_EFFECTIVENESS` added** — not a refusal, does not consume a refusal count; two consecutive such withdrawals for substantive defects force broader review. (4) **Replacement closure defined** as the first of six discrete post-effectiveness events, with prior ephemeral verification gates explicitly excluded. (5) **Operator-selected expiration rejected**, with owner early-revocation preserved. (6) **Expiration rule re-bound to the body hash.** The first cut of this amendment restated the §14 rule under the key `expires_on`, which `apply_exclusions` blanks *by key name* — silently removing the rule itself from hash coverage while §17 asserted it "remains hashed". Measured before owner approval: mutating §14 from 336 to 672 hours left the authorization identity byte-identical. §14 now states the rule as `expiration_rule`; the verifier pins its value and refuses any expiration rule stated under an excluded key; §17 now describes exclusion-by-key-name accurately. A regression test asserts the rule reaches the hashed bytes, and a further test asserts the governed document and the verifier fixture are byte-identical. **No authorization became effective and no governed stage was invoked**; the prior identity `c7eb9737…` is `OWNER_APPROVAL_WITHDRAWN_BEFORE_EFFECTIVENESS`, not REFUSED. |

*End of ADR0043-LIVE-CANARY-WS5-SUCCESSOR-START-001 (DRAFT — NOT EFFECTIVE — NOT INVOKED).*
