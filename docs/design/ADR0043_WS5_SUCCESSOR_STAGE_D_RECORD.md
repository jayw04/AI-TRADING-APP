# ADR0043-LIVE-CANARY-WS5-SUCCESSOR-START-001 — STAGE B4/C/D RECORD

> ## TERMINAL DISPOSITION: **READY**
>
> Stages B4, C and D executed and sealed. The authorization's scope is now **spent**.
>
> **READY is not tradable.** This authorization pins `broker_access_mode=read_only`,
> `strategy_execution_enabled=false`, `scheduler_enabled=false`, `alpaca_startup_enabled=false`.
> Binding WSS, generating an activation manifest, any order, and scheduler activation are **outside
> it** and require a separate authorization that does not exist as of this record. What this record
> attests is a verified-ready, flat, inert account — nothing more.

| Field | Value |
|---|---|
| Stages | **B4 — credential staging · C — governed read-only reconciliation · D — seal and dispose** |
| Disposition | **READY** |
| Operator | `jayw04:delegated-agent/claude-code` (Jay Wang accountable) |
| B4 secret entry | **Jay Wang, in person**, interactive SSM session — not delegated |
| Authorization | `9845c6df…` effective 2026-08-04T00:26:48Z, expires 2026-08-18T00:26:48Z |
| Executed at | 2026-08-04T15:16–15:21Z |
| Predecessor | Stage A record — `STAGE_A_PASS` (#607) |

## 1. Checkpoint B4 — owner-controlled credential staging

§2 prohibits `ALPACA_PAPER_7_*` as the runtime credential name (it collides with Workbench account 7
/ strategy 9). The staged names are the §4C/§6 successor names. Neither credential value appears in
this record, in the receipt, in the repository, or in any command history.

**Why B4 is a human checkpoint.** Every unattended channel was closed: §5 forbids broadening the
instance role, so the runtime cannot read Parameter Store; `ssm send-command` retains command text
in SSM history and on disk under `/var/lib/amazon/ssm/...`. The remaining path is an interactive
owner session, which is what `/opt/adr0043/bin/stage-successor-credential` exists to serve.

```
tooling      deploy/aws/adr0043/stage-successor-credential.sh   merged as 6e97a272 (#608)
deployed     /opt/adr0043/bin/stage-successor-credential        0755 root:root
digest       045e95d2ca369a5c7b6573cf6dc1eb8a8df91a231916ac5d1fb2e927b9c88a33
             verified equal to the merged repository blob BEFORE any credential was entered
staged_at    2026-08-04T15:16:29Z          result  B4_PASS
```

Pre-entry conditions confirmed by the script itself, before either prompt: instance identity via
IMDSv2 (`i-0fff7076ad461aa9a`), the expected authorization identity, its own installation path, and
`stage` mode. Session Manager input/output logging was independently confirmed **not configured**
(zero self-owned SSM documents, therefore no `SSM-SessionManagerRunShell` preference document; no
session log group).

### B4 verification — recomputed, not read back

`verify` recomputes from the credential file. The receipt is corroborating evidence only; the
recomputed result is authoritative. All thirteen required checks passed (`B4_VERIFY_PASS`, exit 0):

```
key fingerprint      ffab8796516a   recomputed from file, matches the authorization
secret fingerprint   c2cab6509f1b   recomputed from file, matches the authorization
entries              exactly 2 nonblank · both names authorized · no duplicate keys
file                 mode 0600 · owner root:root
parent directory     /etc/adr0043  mode 0700 · not group- or world-accessible
receipt              contains no credential value; asserts no broker request, no container
bindings             instance and authorization_sha match the effective authorization
account binding      resolved via §8 configuration = PA3E97RWHKQZ; ABSENT from the credential file
```

The account identifier is deliberately **not** staged into the credential file — that file carries
secret material only. `verify` fails closed if the §8 binding is absent or disagrees.

## 2. Stage C — governed read-only reconciliation

### Preflight (§7) — all four conditions held

```
/var/lib/adr0043-ws5/workbench.sqlite   ABSENT   (and zero sqlite files under the volume)
evidence directory                      created 0700 root:root immediately before the run
volume root mounted into the container  NO — only /var/lib/adr0043-ws5/evidence is mounted
database-capable entrypoint invoked     NO — full command override, see below
```

### Image discipline

Executed by fully-qualified **repository digest**, never by tag or image ID:

```
219024422756.dkr.ecr.us-east-1.amazonaws.com/adr0043-canary-ws5
  @sha256:c0c1b0c48fbb4d4318207f589ee9a64ee795ca34100028bfd84d4d9d81c6a54d
```

The retired `sha256:37e52bc941cd…` (`PRIOR_STAGE1_ARTIFACT`) is still present on the host. §10 makes
executing any image other than the authorized deployable a stop condition; digest-pinned invocation
makes selection unambiguous rather than dependent on tag resolution.

The image declares **no `ENTRYPOINT`** and its default `Cmd` is
`sh -c "alembic upgrade head && python scripts/seed_dev_data.py && uvicorn app.main:create_app …"`.
That command must never execute — it would migrate a database and start the application as a side
effect of container startup. A complete command override replaced it, per §15.

### Result

```
terminal_disposition        READY            failure_code                 null
approved_calls_in_order     GET /v2/account → /v2/positions → /v2/orders → /v2/account/activities
transport_dispatch_count    4                mutation_attempt_count       0
expected_account_id         PA3E97RWHKQZ     returned_account_id          PA3E97RWHKQZ
positions_count             0                orders_count                 0
activities_count            1
container                   adr0043-ws5-stage-c   Exited (0)   restart policy: no
```

Four dispatches for four approved calls: no unapproved endpoint was contacted and no call was
retried. The account-identity latch was satisfied on the first `GET /v2/account`, which is what
gates the remaining three reads.

### ⚠ The financial values are evidence, not a baseline

```
equity 100000 · cash 100000 · portfolio_value 100000 · position_market_value 0
authoritative_start_a_baseline = FALSE
```

Per §9 these figures are **non-authoritative**. They must not seed a Start-A determination, a
daily-loss breaker baseline, or an exposure baseline. A future activation must obtain a **fresh**
broker snapshot, verify the returned account identity first, and seal that snapshot instead.

This is not a formality. `last_equity` is not the prior close, and it has previously fed the
daily-loss baseline and produced a spurious breaker trip on a trivial move; separately, the
2026-07-13 incident had the daily-loss gate blocking the book's own de-risking sells. Reusing these
values as an operating baseline would re-enter that failure mode by construction.

## 3. Stage D — seal and independent reproduction

Both digests were reproduced **off-host, on a separate machine, from an independent
implementation** — not read back from the artifact's own self-report.

```
artifact_sha256       987bd76f6bc2816eda8a5d666121d544d27484b024983a7c9d4d0c79f2db8052   MATCH
evidence_file_sha256  79011ea493cf0392dfa97b76ccb4f99e23623aa666672d9d8b82876acc647463   MATCH
                      host sha256sum == locally recomputed digest of the retrieved bytes
```

The two hashes are computed differently and must not be conflated:

- `artifact_sha256` = SHA-256 of the record with the `artifact_sha256` key **removed**, serialised
  `json.dumps(indent=2, sort_keys=True, ensure_ascii=False)`, **no trailing newline**.
- `evidence_file_sha256` = SHA-256 of the published file, which is that serialisation **with
  `artifact_sha256` reinserted and a trailing `"\n"` appended**.

```
evidence  /var/lib/adr0043-ws5/evidence/stage_c_20260804T152020Z.json   0600 root:root
run_id    581b334b14064512bcbe811d031cf994
schema    adr0043-ws5-stage-c/1.0
source_commit         1880fcdb05e367306e81fa96b355b996f73b7819
image_manifest_digest sha256:c0c1b0c48fbb4d4318207f589ee9a64ee795ca34100028bfd84d4d9d81c6a54d
```

## 4. Mechanical stop conditions (§10) — none triggered

```
account identity mismatch                              NO   returned == expected
credential fingerprint mismatch                        NO   both recomputed and matched
image digest mismatch / unauthorized image executed    NO   digest-pinned; retired artifact untouched
source revision mismatch                               NO   pinned 1880fcdb…
mutation attempt / unapproved endpoint                 NO   mutation_attempt_count = 0
database or Alembic state outside the sequence         NO   default Cmd never executed
workbench.sqlite created outside a migration checkpoint NO  absent before and after
writable mount containing the reserved database path   NO   only the evidence directory mounted
loss/overwrite of prior authorization binding history  NO   successor_* tag keys only
```

## 5. §16 — controlled artifact replacement is now CLOSED

Four closure events occurred under this effective successor authorization:

```
1. successor credential attached to the governed WS5 runtime      B4
2. Stage-C container created from the authorized image            Stage C
5. broker request dispatched from WS5                             Stage C
6. authorized image executed as Stage B/C operational activity    Stage C
```

The authorized deployable digest can no longer be replaced under this authorization. Any future
image change requires a new authorization with its own replacement record; the prior digest is
**retired, not deleted**.

## 6. Terminal disposition and scope boundary

**READY.** The successor runtime holds a verified credential bound to the verified broker account,
executed the authorized image inertly, completed the four approved reads in order, attempted no
mutation, and produced sealed evidence whose digests reproduce independently.

Per §15, Stage D **does not** authorize Start A, Start B, Phase 0, order activity, or the default
application. Explicitly **not** authorized by this record:

```
binding WSS to the account          generating an activation manifest
enabling the scheduler              enabling strategy execution
submitting any order                starting the default application
establishing a Start-A baseline     migrating or creating the database
```

WSS remains **inert, read-only, unscheduled, and unstarted**. This authorization expires
2026-08-18T00:26:48Z; expiry does not retroactively invalidate this record.

## 7. Follow-on items — tracked, and deliberately not addressed here

- A **WSS activation authorization** is to be drafted separately. It must obtain a fresh
  activation-time broker snapshot and seal that as the authoritative Start-A baseline; the values in
  §2 above are not eligible.
- **PR #606** (factor-refresh fix) remains unmerged, to keep a strategy-code change out of the
  executable baseline this record attests. Activating on the currently verified factor
  implementation therefore carries the known factor-staleness behaviour; that is a decision for the
  activation authorization to make explicitly, with commit and image digest pinned either way.
- A **separate security remediation** covers a plaintext legacy-canary credential in a tracked test
  file. It is unrelated to the successor credential (distinct fingerprint, verified), does not
  affect any evidence in this record, and must not delay it. No plaintext value appears in this
  record, and none may appear in the remediation's PR, issue, or narrative.
