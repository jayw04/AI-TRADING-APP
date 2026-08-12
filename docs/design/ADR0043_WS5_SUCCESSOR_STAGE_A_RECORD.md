# ADR0043-LIVE-CANARY-WS5-SUCCESSOR-START-001 — STAGE A RECORD

> ## TERMINAL RESULT: **STAGE_A_PASS**
>
> Stage A is metadata and history verification plus additive tagging. **No container, credential,
> database, migration or broker call.** Stage B is NOT invoked and requires its own explicit
> invocation.

| Field | Value |
|---|---|
| Stage | **A — adopt and verify clean resources** |
| Result | **STAGE_A_PASS** |
| Operator | `jayw04:delegated-agent/claude-code` (Jay Wang accountable) |
| Authorization | `9845c6df…` effective 2026-08-04T00:26:48Z, expires 2026-08-18T00:26:48Z |
| Verified at | 2026-08-04T00:28–01:50Z |

## 1. Adopted resource identities — all verified

```
runtime_instance   i-0fff7076ad461aa9a   running · t4g.medium · ami-02c4144237becae44
                                         launched 2026-08-03T01:05:18Z · 0 interactive users
data_volume        vol-0710769fb6981102d in-use · encrypted=true · 20 GiB
                                         DeleteOnTermination=false · attached to the runtime
security_group     sg-08b1284b33d9159c4  ingress rules = 0 · egress rules = 4 · vpc-0812b4c51d3042437
iam_role           adr0043-canary-ws5-52b3ff136196-role      created 2026-08-03T01:02:46Z
instance_profile   adr0043-canary-ws5-52b3ff136196-profile   -> the above role
runtime_stack      adr0043-canary-ws5-52b3ff136196            CREATE_COMPLETE
evidence_stack     adr0043-canary-ws5-52b3ff136196-evidence   CREATE_COMPLETE
ecr_repository     219024422756.dkr.ecr.us-east-1.amazonaws.com/adr0043-canary-ws5
evidence_store     s3://adr0043-ws5-evidence-219024422756-us-east-1
                                         versioning Enabled · object count 0
```

Image identities, verified distinct and correctly typed:

```
sha256:c0c1b0c48fbb…  application/vnd.oci.image.manifest.v1+json  untagged  = THE DEPLOYABLE
sha256:59f3f26123ca…  application/vnd.oci.image.index.v1+json     tag: 1880fcdb05e367306e81fa96b355b996f73b7819
```

The index carries the authorized source commit as its tag; the deployable is the untagged
single-platform manifest. The §12 prohibition on describing the index as deployable is satisfied.

## 2. Cleanliness at adoption — all six criteria verified

Verified by direct host inspection over SSM Session Manager (read-only), not by inference.

```
container_created          = false    docker ps -a  ->  container_count = 0
database_created           = false    /var/lib/adr0043-ws5/workbench.sqlite ABSENT
                                      sqlite files anywhere on the root filesystem = 0
credential_attached        = false    no .env files · docker secrets = 0 · docker volumes = 0
broker_called_from_runtime = false    no credential present and no container has ever existed
migration_applied          = false    no database, and STAGE1_MARKER attests migration_applied=false
application_started        = false    workbench/compose systemd units = 0 · container_count = 0
evidence_directory         = ABSENT   /var/lib/adr0043-ws5/evidence not yet created (Stage B creates it)
```

The Stage-1 marker written under the **prior** authorization independently attests the same:

```
authorization_body_sha256   52b3ff136196…   stage  STAGE_1_CREATION_ONLY
database_created            false           application_deployed       false
migration_applied           false           broker_credential_attached false
bootstrap_completed_utc     2026-08-03T01:06:26Z
```

### 2.1 Credential scan — how the raw counts resolve

A naive `grep -rl ALPACA` over `/etc /opt /root /home /var/lib` returns **380 files**. That figure is
recorded here with its decomposition so it is never mistaken for staged credentials:

```
216  /var/lib/adr0043-ws5   the three source checkouts (src, src-1880fcdb05e3, src-ed604d49ef9e)
161  /var/lib/containerd    container image layer snapshots (app/config.py, credentials.py, …)
  4  /var/lib/amazon        the SSM inspection scripts issued by this very verification
```

All three are source text or this procedure's own artifacts. Separately, a key-shaped pattern search
`(PK|SK)[A-Z0-9]{18,}` returns **37 files**, every one a compiled binary — the `cryptography`
`_rust.abi3.so`, `libllvmlite`, `_duckdb…so` — where the match is a random byte run, not key
material. **No `.env` file exists outside the source trees; there are no Docker secrets and no Docker
volumes.** `credential_attached = false` holds.

### 2.2 Disclosed: the prior Stage-1 image is resident on the host

```
docker images = 3
  …/adr0043-canary-ws5   sha256:c0c1b0c48fbb…   AUTHORIZED DEPLOYABLE
  …/adr0043-canary-ws5   sha256:37e52bc941cd…   PRIOR_STAGE1_ARTIFACT
  moby/buildkit          sha256:2f5adac4ecd1…   build tooling
```

`37e52bc9…` is the artifact of the refused attempt's Stage 1. **Presence is not execution.** §10
prohibits *executing* any image other than the authorized deployable manifest, and
`container_count = 0` establishes that no container has ever been created from any of them. Stage B
must therefore pull and run **by digest**, never by tag and never by image recency.

## 3. Additive tagging — applied and verified non-destructive

§4A requires successor tags to be additive, and §10 makes **"loss or overwrite of prior authorization
binding history"** a mechanical stop condition. AWS tags are single-valued, so the successor values
were written under **new keys**; no existing key was modified.

Applied to `i-0fff7076ad461aa9a`, `vol-0710769fb6981102d`, `sg-08b1284b33d9159c4`:

```
successor_authorization_sha  = 9845c6dfb78ee1435ecb101ca5388f2dd32447921a89cacbf31a2570c19325d8
successor_expires_on         = 2026-08-18T00:26:48Z
successor_broker_account     = PA3E97RWHKQZ
origin_authorization_sha     = 52b3ff136196e90f0a4d85b92a7280fd19355da64348958fa28706c274ac47ae
resource_history             = CREATED_UNDER_REFUSED_AUTHORIZATION_THEN_EXPLICITLY_ADOPTED
```

Verification, by diffing the complete tag set before and after:

```
pre-existing tags altered or lost : NONE
tag count per resource            : 12 -> 17  (+5, identical on all three)
```

Both authorizations are now reconstructable from each resource itself:

```
authorization_sha  52b3ff1361…  (origin, untouched)  | successor_authorization_sha  9845c6df…
broker_account     PA34USW0Q8UO (origin, untouched)  | successor_broker_account     PA3E97RWHKQZ
expires_on         2026-08-16T23:59:59 America/Chicago (origin, untouched)
                                                     | successor_expires_on         2026-08-18T00:26:48Z
```

⚠ `PA34USW0Q8UO` on these resources is **canary-era provenance, not a binding**. It appears zero
times in the governing authorization, which pins `PA3E97RWHKQZ` and hashes it into
`binding_manifest_sha256`. The CloudFormation stacks were deliberately **not** tagged: that would
require a stack update, which is the 2026-07-27 mechanism that replaced a live instance.

## 4. Legacy quiescence

```
legacy_instance  i-01527ac7b7c7efa35  running, retained, not terminated (control-plane verified)
```

Container-level quiescence is carried forward from the 2026-08-03T18:51:32Z record. §2 prohibits any
modification of the legacy canary or its volumes; none was performed.

## 5. ⚠ Correction to the trigger record

The §18 effectiveness trigger (PR #603) stated that the inert-posture affirmations were *structural*
because "`sg-08b1284b33d9159c4` has zero ingress rules, so no interactive access path to the instance
exists."

**That reasoning was wrong.** The instance is reachable through **SSM Session Manager**, which is
outbound-only and therefore unaffected by the absence of ingress rules:

```
i-0fff7076ad461aa9a   PingStatus Online   SSM agent 3.3.4793.0   Ubuntu
role grants           AmazonSSMManagedInstanceCore + inline ws5-ecr-scoped
```

The affirmations themselves are unchanged and are now supported by **stronger** evidence: §2 above is
direct host inspection rather than an argument from unreachability. The correction is recorded here
rather than left standing in a merged record.

## 6. Terminal result

```
STAGE_A_PASS
```

Every adopted resource verified and history-bound. Stage B is **not** invoked.

## 7. Stage B is BLOCKED — three findings requiring owner direction

Stage B (B1–B4) cannot proceed as written. Recorded here so the blockage is governed, not improvised.

**B-1. The runtime credential name in the working plan is a §2 prohibition.** The operating plan says
to stage "the dedicated account-7 credential names". The account-7 credential is named
`ALPACA_PAPER_7_*` everywhere else in the platform, and §2 **explicitly forbids that name as the
runtime credential name**, because it collides with Workbench account 7 and strategy 9. The
authorization requires the prefix `ADR0043_SUCCESSOR_CANARY_ALPACA_` (§4C, §6). Same key material —
fingerprints `ffab8796516a` / `c2cab6509f1b` — under a **different environment-variable name**.

**B-2. The secret value is not available through any authorized channel.** Neither
`ADR0043_SUCCESSOR_CANARY_ALPACA_*` nor `ALPACA_PAPER_7_*` exists in SSM Parameter Store;
`/workbench/prod/*` holds accounts 1–6 and the legacy canary only. B4 requires verifying **both**
fingerprints, so possession of the API key alone is insufficient.

**B-3. The runtime cannot read Parameter Store even if the values existed.** The instance role grants
`AmazonSSMManagedInstanceCore` plus an inline `ws5-ecr-scoped` policy limited to ECR actions on the
one repository. It has **no** `ssm:GetParameter` grant. Adding one is an IAM modification of an
adopted resource, which is outside the §9 authorized list — additive tagging · pulling the authorized
image by digest · creating one inert Stage-C container · writing evidence to the evidence path.

⚠ Delivering the secret via `ssm send-command` is **not** an acceptable workaround: command text is
retained in SSM history and written to `/var/lib/amazon/ssm/.../_script.sh` on the instance — this
very verification observed exactly that for its own commands.

This is structurally the same shape as the refusal of attempt 1: a required capability does not exist,
and supplying it needs a change the authorization does not permit. It is surfaced **before** Stage B
rather than discovered inside it, which is the difference that keeps it repairable.

*Stage A complete. Stage B held pending owner direction on B-1, B-2 and B-3.*
