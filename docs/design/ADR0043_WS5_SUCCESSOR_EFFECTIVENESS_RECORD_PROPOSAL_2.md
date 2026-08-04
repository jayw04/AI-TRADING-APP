# ADR0043-LIVE-CANARY-WS5-SUCCESSOR-START-001 — §18 EFFECTIVENESS TRIGGER (RECORD 1 of 2)

> ## PROPOSED EFFECTIVENESS TRIGGER · NOT EFFECTIVE · NOT INVOKED
>
> - **Opening or approving this PR does not create effectiveness.**
> - **Only merging the exact owner-approved head creates the effectiveness event.**
> - **Merge does not invoke Stage A.**
> - **Stage A remains held pending the post-merge completion record (Record 2).**
> - **No operational action may occur in the interval between the trigger merge and acceptance of
>   the completion record.**

| Field | Value |
|---|---|
| Record | **1 of 2 — effectiveness trigger** |
| Operator | `jayw04:delegated-agent/claude-code` (Jay Wang accountable) |
| Status | **PROPOSED EFFECTIVENESS TRIGGER — NOT EFFECTIVE — NOT INVOKED** |
| Authorization | ADR0043-LIVE-CANARY-WS5-SUCCESSOR-START-001 (amendment-1) |
| Supersedes | PR #601, closed unmerged — bound a retired identity and the retired calendar-day rule |

## 1. Frozen authorization identity — reproduced independently from `main`

```
authorization_sha256               = 9845c6dfb78ee1435ecb101ca5388f2dd32447921a89cacbf31a2570c19325d8
normative_body_sha256              = 15e13585860027c2e55833421b2218111407abb8b62e1062f17961d04a7fa57d
binding_manifest_sha256            = 8769ba3013e18835c118a81e4bce378426ed2eada1ec7ba80024b1049255e118
authorization_document_blob_sha256 = 2d588eb788ffa9f5c98941d49181b12aac09a0defe7fa9d0a64a4ca45d93a7ea
authorization_document_git_blob    = ad9f851aae8af85258d93eee992c294c4ca80e96
amendment_merge_sha                = 5393dd42f3b5e242b2984353a960fb58dc30f98c
independent_verifier_result        = PASS
```

Reproduced with the verifier **as committed to `main`** against the document **as committed to
`main`**.

## 2. Retired identities — withdrawn before effectiveness, not refused

```
c7eb9737116fabe8608d9a77760c37a3816989a56f58cafb5980e04342a18a2f
  state            = OWNER_APPROVAL_WITHDRAWN_BEFORE_EFFECTIVENESS
  became effective = no
  stage invoked    = no
  consumes refusal = no
  reason           = expiration rule was deterministic but could extend authority up to ~24h
                     beyond the intended 336-hour maximum; corrected pre-effectiveness

1f8366d81883a702ffb09b49f78371725c9d7b86143168afc353d26e64697579
  disposition      = none — intermediate drafting identity, never owner-approved
  became effective = no
  stage invoked    = no
  consumes refusal = no
  reason           = restated the §14 expiration rule under the excluded key `expires_on`,
                     removing the rule from body-hash coverage while §17 claimed otherwise
```

`1f8366d8…` is deliberately **not** assigned a state. The authorization defines
`OWNER_APPROVAL_WITHDRAWN_BEFORE_EFFECTIVENESS` and the REFUSED / INCONCLUSIVE dispositions; it
defines no state for an identity that never left drafting, and this record does not invent one. It is
listed here only so the identity is traceable and cannot be mistaken for a live or retired
authorization.

Neither is a REFUSED disposition. The refusal ledger is unchanged: the original WS5 authorization is
refusal 1; this document remains attempt 2. Only `c7eb9737…` is a withdrawal; `1f8366d8…` never
reached owner approval and is therefore drafting history, not a withdrawal.

## 3. Effectiveness timestamps — derivation, not a value

```
authorization_effective_at = TO_BE_DERIVED_FROM_GITHUB_MERGED_AT_OF_THIS_EXACT_PR
expiration_rule            = authorization_effective_at + 336 hours exactly
```

UTC timestamps are authoritative. Local-time renderings are informational only. No end-of-day
rounding or extension is permitted. The concrete `expires_on` is derived mechanically from the frozen
rule in Record 2; it may not be selected, shortened, extended, or rounded by the operator.

**If this exact reviewed head is owner-approved and merged, the authoritative effectiveness event is
the GitHub `merged_at` timestamp of that merge. The merge does not invoke Stage A. Stage A remains
held until the concrete effectiveness-completion record is independently verified and merged.**

A file cannot contain the merge SHA or merge timestamp of its own future merge, and no external
automation is authorized to mutate `main` after the fact. Hence two records: this one fixes *what*
becomes effective and *how* the moment is derived; Record 2 documents the already-fixed merge
identity and timestamp.

**The 336-hour clock begins at the trigger merge timestamp — not at the later completion-record
merge.**

## 4. Record 2 — post-merge completion record (not yet created)

After this PR merges, a separate metadata-only record must carry:

```
effectiveness_trigger_pr
effectiveness_trigger_reviewed_head_sha
effectiveness_trigger_merge_sha
authorization_effective_at          # the trigger PR's actual GitHub merged_at, UTC
expires_on                          # authorization_effective_at + 336 hours exactly, UTC
authorization_sha256
normative_body_sha256
binding_manifest_sha256
authorization_document_blob_sha256
independent_verifier_result
```

## 5. Successor resource state — re-verified for this record

Verified read-only against AWS account `219024422756`, `us-east-1`, at 2026-08-03T23:28:23Z.

```
ws5_runtime                   = i-0fff7076ad461aa9a  running, 12 tags, inert
ws5_security_group            = sg-08b1284b33d9159c4  ingress rules = 0, egress rules = 4
ws5_root_volume               = vol-0710769fb6981102d  in-use, DeleteOnTermination = false
ws5_stacks                    = adr0043-canary-ws5-52b3ff136196            CREATE_COMPLETE
                                adr0043-canary-ws5-52b3ff136196-evidence   CREATE_COMPLETE
ws5_evidence_bucket           = adr0043-ws5-evidence-219024422756-us-east-1  objects = 0
frozen_identities_unchanged   = yes  (index sha256:59f3f261…; deployable sha256:c0c1b0c4…,
                                      both present in ECR repo adr0043-canary-ws5)
```

**Existing tags carry the prior authorization's bindings** — `authorization_sha = 52b3ff1361…`,
`broker_account = PA34USW0Q8UO`, `expires_on = 2026-08-16T23:59:59 America/Chicago`. This is the
correct pre-Stage-A state: §4A applies successor tags **additively** and preserves the original
resource-history bindings so a reviewer can reconstruct which authorization created each resource.
Stage A adds the successor `authorization_sha`, `broker_account = PA3E97RWHKQZ` and the exact
`expires_on`; it does not overwrite the originals.

### Basis of the inert-posture affirmations

```
successor_credential_staged     = no
successor_sqlite_files          = 0
ws5_persistent_containers       = 0
ws5_broker_calls                = 0
stage_c_executions              = 0
application_deployments         = 0
```

These are **structural, not host-inspected**: `sg-08b1284b33d9159c4` has zero ingress rules, so no
interactive access path to the instance exists, and no stage of this authorization has been invoked.
They are not claims derived from logging into the host. Host-level confirmation belongs to Stage A,
whose terminal result is `STAGE_A_PASS`.

### Image-execution affirmation

The successor image was previously executed only for authorized ephemeral image-verification gates.
Those runs used no successor credential, created no persistent container, did not constitute Stage C
or application deployment, and produced no persistent runtime state. Per §16 as amended, prior
ephemeral image-verification gates **do not** constitute a controlled-artifact-replacement closure
event.

```
cached_ecr_image_layers_on_ws5  = 2
persistent_successor_containers = 0
```

### Evidence-directory affirmation

```
evidence_directory_current_state     = ABSENT
required_before_stage_c              = YES
current_absence_blocks_effectiveness = NO
current_absence_blocks_stage_c       = YES
```

Creation and writability verification of `/var/lib/adr0043-ws5/evidence` belong to the authorized
Stage A/B sequence. This record does not claim that Stage-C precondition has passed.

## 6. Legacy predicate

```
legacy_phase2_disposition       = QUIESCED_SAFE_WITH_MANUAL_RECREATION_RESIDUAL
legacy_quiescence_completed_at  = 2026-08-03T18:51:32Z
backend_exit_137                = DISCLOSED_NONCONFORMITY_WITHOUT_INTEGRITY_IMPACT
legacy_containers_retained      = 5
legacy_containers_running       = 0
legacy_restart_policies         = no  (all five)
legacy_automatic_restart_hazard = CLOSED
legacy_manual_recreation_hazard = OPEN_AND_GOVERNED
legacy_instance                 = i-01527ac7b7c7efa35  running, retained, not terminated
preservation_snapshot           = snap-01d3da50af60eeffb  completed, encrypted, of vol-0010f535850f2a74e
preservation_s3_objects         = 31
```

Container counts and restart policies are host-level facts carried forward from the quiescence
record of 2026-08-03T18:51:32Z; they are not re-readable through the AWS control plane. Re-verified
through the control plane at 2026-08-03T23:28:23Z: `i-01527ac7b7c7efa35` running, not terminated;
snapshot `snap-01d3da50af60eeffb` `completed` and `Encrypted = true`.

Host marking remains in force: `DO_NOT_RUN_DOCKER_COMPOSE_WITHOUT_GOVERNANCE_APPROVAL`.

## 7. Holds in force

Stage A · credential staging · Stage-C image execution · database creation · Alembic · broker
access · legacy application restart · legacy termination — **all prohibited**. Neither opening,
approving, nor merging this record changes any of them; merging establishes only the effectiveness
event and starts the 336-hour expiration clock.
