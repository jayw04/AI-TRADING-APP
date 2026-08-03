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
| Authorization | ADR0043-LIVE-CANARY-WS5-SUCCESSOR-START-001 |

## 1. Frozen authorization identity — reproduced independently from `main`

```
authorization_sha256               = c7eb9737116fabe8608d9a77760c37a3816989a56f58cafb5980e04342a18a2f
normative_body_sha256              = f9d0974caef4eee310b2014399f36d96b3d5d974d1948812fc1a099589e89f6b
binding_manifest_sha256            = 6537a96f70fe5094a1a1ee2831f01ca5328c046771a403bb576b0fe80c58372a
authorization_document_blob_sha256 = de1cccaa39fb91d02b329901ee2cf9f12c8eeed200e2b5a50dacb9655f1968df
authorization_document_git_blob    = 5637cdf16be8a544901a20ce2594121ef907d4e1
draft_merge_sha                    = a636d6b4bb703be5ba44dd000ddabff323c8f85e
independent_verifier_result        = PASS
```

Reproduced with the verifier **as committed to `main`** against the document **as committed to
`main`**. All six values match the owner-approved set exactly.

## 2. Effectiveness timestamps — derivation, not a value

```
authorization_effective_at = TO_BE_DERIVED_FROM_GITHUB_MERGED_AT_OF_THIS_EXACT_PR
expires_on                 = authorization_effective_at + 14 calendar days,
                             ending 23:59:59 America/Chicago
```

**If this exact reviewed head is owner-approved and merged, the authoritative effectiveness event is
the GitHub `merged_at` timestamp of that merge. The merge does not invoke Stage A. Stage A remains
held until the concrete effectiveness-completion record is independently verified and merged.**

A file cannot contain the merge SHA or merge timestamp of its own future merge, and no external
automation is authorized to mutate `main` after the fact. Hence two records: this one fixes *what*
becomes effective and *how* the moment is derived; Record 2 documents the already-fixed merge
identity and timestamp.

**The 14-day clock begins at the trigger merge timestamp — not at the later completion-record merge.**

## 3. Record 2 — post-merge completion record (not yet created)

After this PR merges, a separate metadata-only record must carry:

```
effectiveness_trigger_pr
effectiveness_trigger_reviewed_head_sha
effectiveness_trigger_merge_sha
authorization_effective_at          # the trigger PR's actual GitHub merged_at
expires_on                          # + 14 calendar days
authorization_sha256
normative_body_sha256
binding_manifest_sha256
authorization_document_blob_sha256
independent_verifier_result
```

## 4. Legacy predicate

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
preservation_snapshot           = snap-01d3da50af60eeffb  completed, encrypted
preservation_s3_objects         = 31
```

Host marking remains in force: `DO_NOT_RUN_DOCKER_COMPOSE_WITHOUT_GOVERNANCE_APPROVAL`.

## 5. Successor state affirmations

```
successor_credential_staged   = no
successor_sqlite_files        = 0
ws5_persistent_containers     = 0
ws5_broker_calls              = 0
frozen_identities_unchanged   = yes   (tag 1880fcdb… -> index sha256:59f3f261…;
                                       deployable sha256:c0c1b0c4…)
ws5_runtime                   = i-0fff7076ad461aa9a  running, 12 authorization tags, inert
```

### Image-execution affirmation

The successor image was previously executed only for authorized ephemeral image-verification gates.
Those runs used no successor credential, created no persistent container, did not constitute Stage C
or application deployment, and produced no persistent runtime state. The image has never been run as
a Stage-C broker reconciliation or as an application deployment.

```
cached_ecr_image_layers_on_ws5 = 2
persistent_successor_containers = 0
stage_c_executions              = 0
application_deployments         = 0
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

## 6. Holds in force

Stage A · credential staging · Stage-C image execution · database creation · Alembic · broker
access · legacy application restart · legacy termination — **all prohibited**. Neither opening,
approving, nor merging this record changes any of them; merging establishes only the effectiveness
event and starts the expiration clock.
