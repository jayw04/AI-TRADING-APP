# Amendment 8 — deployment record, evidence, and permanent corrections

**Status: DEPLOYED / ACCEPTED / CLOSED — 2026-08-27.**
Companion to `Prereg_Amendment_8_Derived_Runtime_Deployment_Identity.md` (the instrument) and
`manifests/deploy/amendment8_3f32c75b.json` (the pinned artifact record).

This document exists so the deployment is reconstructible from governed source control alone, and not
only from a session transcript or a local working tree.

---

## 1. What was deployed

The deployed object is exactly the previously approved, **pre-#696** target. There was no substitution
with current `main`.

| | |
|---|---|
| approved / deployed commit | `3f32c75b1053f8181f98ddf51bbc473364ffd34c` |
| deployed code digest | `sha256:813be1b9775fb98e4276a499e8c715b745c7a518decf04072ef5a75999b72610` |
| archive SHA-256 | `de2b8fc8e9addc004b6028c37094d5d0d615753ee676523591ec7da9626eba50` |
| build marker SHA-256 | `a387527ff33cfc743171c43cada176a09d573dd16a74c9b63ea6c31508f64fba` |
| build-info schema | `workbench-deployed-build-info/2` |
| first governing READY | all six gates PASS, 2026-08-27T21:04:29Z |

Because the artifact was built from the approved pin **before** PR #696, it does **not** contain the
K1/K3 calculator changes merged through #696. PR #696 is a separate source-control release (approved
head `77461c74…`, squash `15456560a99ecd857306771831a61e81d846a629`, CI run 1669 / 33095118928).
**The Amendment 8 deployment and #696 must not be conflated.**

## 2. Runtime identity — divergence closed

Before Amendment 8 the marker and `.deploy_src_sha` both reported `07a9233…` while the running image
was `ada7a5be…`, recreated a day later; the host could not reliably detect that divergence.

After Amendment 8, runtime identity is **measured, not declared**. At container startup, *before*
Alembic migration, the runtime verifies:

```
runtime code identity verified: sha256:813be1b9775fb98e4276a499e8c715b745c7a518decf04072ef5a75999b72610
```

Two independent derivations converge on the same digest:

1. git-blob calculation from the approved source commit — `compute_deploy_code_digest.py --ref 3f32c75b…`
2. Gate 6 host-side collection from the **actual running container**

This also resolves the CRLF concern: the git-blob calculation preserved LF parity despite
`core.autocrlf=true` on the build host.

**Runtime identity authority is the measured running-container/code-hash result, not a host self-report.**

## 3. Constraints respected

Artifact transported as a distinct pinned S3 object `bootstrap/amendment8/3f32c75b-code.tgz` with its
specific VersionId; the shared mutable `bootstrap/code.tgz` was **not** overwritten. Digest verified
**before** extraction, fail-closed. Backend-only path; `provision-from-s3.sh` **not** used. Frontend,
MCP and agent remained running. `.env` byte-stable, mtime unchanged. Alembic a proven no-op (revision
sets byte-identical, head `c8e2a4b1d7f0`). `run2_b3a_proof.sh` **not** reconstructed. Strategy 8
remains IDLE with zero orders. Only `ec2-paper` armed. MDQ capture idle at closure.

Pre-deploy backup: `pre-amendment8-2026-08-27T2100Z.sqlite`, SHA-256
`14552142e743fcada523c7eb2465b00994721c84342db0e7afef266eada4eee5`, `audit_log` 7,823 rows.

## 4. Permanent evidence corrections

Two execution mistakes occurred during deployment **verification**. They are corrected and do not
invalidate Amendment 8. Both the original observations and their corrections are retained deliberately;
they must not be rewritten out of history.

### 4.1 SQLite backup error

The initial pre-state probe targeted `/app/data/workbench.db`, **which did not exist**. Because
`sqlite3.connect()` creates a database when the requested file is absent, the probe **created an empty
database**. `PRAGMA integrity_check` then returned `ok`, producing reassuring evidence about the wrong
object. **That evidence is invalid.** The accidentally created artifacts were removed and the actual
live database, `workbench.sqlite`, was backed up correctly (§3).

> **Permanent guard.** `integrity_check=ok` is meaningless until the database under test has first been
> proven to be the intended, existing, non-empty database. **Database identity and existence must
> precede any integrity conclusion.**

### 4.2 Scheduler exit-code error

A reported `SCHED_EXIT=0` was actually the exit status of an intervening `tail`, not of the governed
scheduler command. The check was rerun capturing status from the correct command; the true result was
also `SCHED_EXIT=0`, one armed host `ec2-paper`. **The final result is valid; the first method was not.**

> **Permanent guard.** Process status must be captured directly from the governed command. Never infer
> it from an intervening `tail`, pipeline stage, logging command, or other process.

## 5. `bootstrap/code.tgz` — standing stop clause

The shared default object `bootstrap/code.tgz` is now **stale** relative to the deployed runtime, and
`provision-from-s3.sh` still defaults to it. Gate 6 should detect the resulting mismatch and fail
closed, so the condition is no longer silent — but that is a backstop, not a selection mechanism.

**Ruling: do NOT refresh or overwrite `bootstrap/code.tgz` to make it current.** It is classified
**LEGACY / NOT AUTHORIZED FOR GOVERNED DEPLOYMENT**. Refreshing the mutable shared key would recreate
precisely the ambiguity the pinned artifact was designed to eliminate.

> **Standing stop clause.** `bootstrap/code.tgz` is a legacy mutable default and is not an Amendment 8
> deployment authority. Its existence, contents, or freshness must never be used to select or infer the
> governed deployment artifact.

Governed deployments follow the Amendment 8 pattern:
**explicit target → explicit pinned S3 object → VersionId → archive SHA-256 → expected code digest →
runtime measurement.**

Any redesign of `provision-from-s3.sh`, or retirement/replacement of the shared key, is a separate
governed change.

## 6. What this record does not confer

Amendment 8 is **closed**; observation is next, activation is not. This deployment confers no
authority over LOW-001 S8.6, the rollback-baseline restore, prospective B3a, or Strategy-8
reactivation. Each gated transition retains its own evidence requirement and authorization boundary.
Governed K1 remains **NOT EVALUABLE** — an honest governance state, not an engineering defect.
