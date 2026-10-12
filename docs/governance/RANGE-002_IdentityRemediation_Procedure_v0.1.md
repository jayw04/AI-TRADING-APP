# RANGE-002 identity remediation: procedure and branch-protection findings (PREPARE ONLY)

| Field | Value |
|---|---|
| Status | **DRAFT. NOTHING IS EXECUTED, PUSHED OR MERGED.** `[MERGE NOT APPROVED]` |
| Owner ruling | R1: agent-authored commits are re-created under a separate machine identity supplied by the owner; no branch-protection exception. R4: any new head SHA restarts the 2-hour walk-away and needs a fresh CI run. |
| Tool | `apps/backend/scripts/research/range002/recreate_under_identity.py` (this PR). Its SHA-256 is **the SHA-256 of the file as committed** (LF bytes): obtain it with `git show <commit>:apps/backend/scripts/research/range002/recreate_under_identity.py \| sha256sum`. **Correction:** an earlier revision of this record quoted `56291316…`, which was computed on a CRLF Windows working copy and does not match the committed bytes; a hash of a working copy is not evidence. |
| Tests | `apps/backend/tests/research/range002/identity_remediation/` (10, synthetic temporary repo) |
| Established | The procedure preserves each commit's tree SHA, message bytes and dates and changes only name/email and the parent chain; verified on the three real branches in a **local dry run** (section 2). |
| NOT established | That the re-created commits pass CI or review: a new head SHA has no CI run and no walk-away yet. No credential was used and nothing was pushed. |

## 1. Procedure (F1)
Inputs from the owner (placeholders; the tool refuses unset or `<TBD>` values): `MACHINE_NAME`, `MACHINE_EMAIL`, and the machine identity's push credentials (never read by the tool).

For each branch, with `BASE` = **the branch's merge-base** (`git merge-base origin/main <branch>`):
1. `plan` lists the commits (old SHA, tree, author). Merges are refused.
2. `recreate --base BASE --branch <branch> --new-ref refs/heads/<branch>-reid` rebuilds each commit with `git commit-tree` from the original tree, original message bytes and original dates, new name/email, new parent chain. Deterministic: the same inputs give the same SHAs.
3. `verify --base BASE --branch <branch> --new-ref refs/heads/<branch>-reid --expect-email $MACHINE_EMAIL` prints per commit `old tree  new tree  MATCH|MISMATCH` and exits nonzero on any tree, message, identity or count difference.
4. `print-push` prints the push command only. Pushing is a separate owner go-ahead.

A BASE that is not an ancestor of the branch is **refused** (it would silently change the effective diff). That is not hypothetical: see #740.

## 2. Local dry run on the real branches (fake identity, local refs only, deleted afterwards)

| PR | Branch | Base used | Old tree = New tree | Result |
|---|---|---|---|---|
| #755 | `feat/range002-screen-kernel` | `origin/main` `9d90d96c` | `373c6b449d3e5310d2027b9643454fc5e93c8604` | MATCH, VERIFIED |
| #760 | `test/range002-lane-d-identity-probe` | `origin/main` `9d90d96c` | `207d16c80072ac1a4f44992365fa22ec61496fcf` | MATCH, VERIFIED |
| #740 | head `8792e043` | merge-base `d61f313a` (**not** `origin/main`) | `6bf3f2b682f0e8d3ab74b5ef176a2eaac4a8d062` | MATCH, VERIFIED; against `origin/main` the tool **refused** |

**#740 is stale.** It was cut from `d61f313a`; `main` is at `9d90d96c`. Branch protection (section 3) requires branches to be up to date, so #740 needs a rebase onto `main`, which is itself a new head SHA (R4) with a fresh CI run and walk-away. Re-creating identity and rebasing are two separate reviewed steps.

## 3. `main` branch protection and rulesets (F3, read-only)

| Control | State |
|---|---|
| Required status checks | `Python CI Gate`, **strict = true** (branch must be up to date) |
| Required pull-request reviews | **NOT CONFIGURED** (no required approvals, no dismiss-stale, no code-owner requirement) |
| CODEOWNERS | none |
| Rulesets | none |
| Require conversation resolution | off |
| Require signed commits | off |
| Linear history | off |
| Enforce for admins | **on** |
| Force pushes / deletions | disabled |
| Merge methods allowed | merge commit, squash, rebase |
| Who may merge | anyone with write access, once `Python CI Gate` is green and the branch is up to date |

**Does "machine identity + the owner's review" satisfy these with no exception? Yes, trivially, because GitHub requires no review at all.** Nothing mechanical needs an exception.

**The consequence the owner should weigh:** GitHub does not enforce independent review on this repository. The non-author-review requirement exists only as a governance control (the owner ruling and the reviewer's per-file evidence). The owner could merge any PR on a green gate with no review and GitHub would allow it. If the owner wants the platform to enforce it, the exact change is: enable "Require a pull request before merging" with at least 1 approving review; enable "Dismiss stale pull request approvals when new commits are pushed" (this makes R4 mechanical); optionally add a CODEOWNERS file naming the guard-adjacent paths with "Require review from Code Owners"; consider "Require conversation resolution". With those settings the machine identity as author plus the owner's approving review satisfies them with no exception. **This agent changed no setting.**

## 4. Exact scope for the owner to authorize (round 4; NOTHING in this section is authorized or executed)

The owner selects the machine identity and names the branches. **Authorization of #755 does not authorize #756-#766**, and **#740 is not an identity-only case** (section 5).

| Item | Value |
|---|---|
| Identity mapping | `jayw04 <37512854+jayw04@users.noreply.github.com>` (author and committer of every listed commit) → `<TBD: machine identity chosen by the owner>` |
| Credentials | Configured by the owner in the local credential helper. The tool never reads or stores them; do not paste them into chat, documents or Git. |
| Proposed first scope | **#755 only** (`feat/range002-screen-kernel`) |
| Base | `origin/main` `9d90d96cbf4cb4f3847b092742c727211a697665` (an ancestor of the branch, so the tool accepts it) |
| Commits | 1: old `1ecf811b0b4ed7699bb4650c22387e1242f98e74`, tree `373c6b449d3e5310d2027b9643454fc5e93c8604` |
| Rollback reference | `refs/rollback/range002-screen-kernel-1ecf811b0b4e` → `1ecf811b…` (create locally and keep the old remote branch; nothing is deleted) |
| Provenance record | `manifest --base … --branch … --new-ref …` prints, per commit, the **original** author, committer, dates, tree and the new SHA. The owner commits that JSON next to the change. Re-creating changes commit metadata only: **it does not create reviewer independence** and must not erase who wrote what. |
| Tree-equality check | `verify --expect-email <machine email>`; exit 0 only if every tree and message matches and the identity is the expected one |
| After the push | New head SHA ⇒ **fresh exact-SHA CI, the review, and the 2-hour walk-away all restart** (R4). The old reviews/CI do not carry over. Final approval must name the final reviewed head. |

## 5. #740 is a separate content integration

- **What it is:** 5 files, +407/-1: `spec/schema.py`, `spec/loader.py`, `scripts/research/range002/freeze_spec.py`, `spec/__init__.py`, and a new test. It makes freeze reject non-distinct or invisible-character sign-off role strings. It is **Level 1 string comparison, not identity verification** (its own text says so).
- **Why identity tooling cannot do it:** it was cut from `d61f313a`, `main` is at `9d90d96c`, and it **overlaps #755 on three files** (`schema.py`, `loader.py`, `freeze_spec.py`). Whichever merges second needs a real rebase and conflict resolution: a content change, a new head SHA, fresh CI, a new review and a new walk-away. The tool refuses a moved base for exactly this reason.
- **Order consequence:** both touch guard-adjacent files. Merging them one at a time means the second must be reviewed on its integrated diff.

## 6. What the governing requirements say, verified (R3 / R4 and GitHub are separate)

| Requirement | Exact source text | What it requires | Satisfied by GitHub protection? |
|---|---|---|---|
| **R3** | Owner instruction rev. 3: "#740 is a precondition: no sign-off may be counted GENUINE until #740 is merged on main." | Governs **counting sign-offs GENUINE**. It does not, as written, bar merging #755, building tooling or reviewing. **It names no alternative route**; a different route needs an adopted amendment. | No. Branch protection knows nothing about it. |
| **R4** | "Any new head SHA restarts the 2-hour walk-away and requires a fresh CI run. Nothing carries over from the old commit." | Applies to every head change, including an identity-only re-creation and a #740 rebase. | **Partly.** `strict` status checks force a fresh gate on a new SHA, but nothing enforces the walk-away or review restart (no required reviews, no dismiss-stale). |
| Walk-away policy | `CLAUDE.md`: PRs sit open at least 1 hour; "consequential" PRs (guard/live path) at least 2 hours. | Time between ready-for-review and merge. | No (not enforced by GitHub). |
| Non-author review | Owner ruling (#756): reviewer must differ from the author; per-file evidence required; a bare approval does not satisfy it. | A governance control. | **No.** GitHub requires no review at all; a green gate alone would let a merge through. |
| Required check | Branch protection: `Python CI Gate`, strict | Mechanical gate on the exact head | Yes. This is the only mechanical requirement. |

**Conclusion:** satisfying GitHub protection (a green strict `Python CI Gate`) does not establish governance compliance. R3, R4, the walk-away and the per-file review each need their own evidence.

## 7. Evidence record: hashes of committed bytes (full values)

Convention: every recorded file hash is the SHA-256 of the file's **committed bytes** (`git show <full commit>:<path> | sha256sum`), never of a working copy. The CRLF working-copy value quoted earlier is withdrawn and resolved.

| Artifact | Full commit | Full SHA-256 |
|---|---|---|
| `apps/backend/scripts/research/range002/recreate_under_identity.py` | `74f27261631dbef3bfa08333ac153036609db8a1` (this PR) | `81f4af00201cb4a2062c26bc0897c655632354a4c9635a003b4a458fc4f767c5` |
| `docs/implementation/evidence/range_002/RANGE-002_Identity_Probe_Preregistration_v1.json` | `b1a38d8e7290425b1206bb90e347caace04a17f2` (#760) | `116a0601ff29374a38c4290cc355c506374c7137d420c908a15b76e91e3a17fc` |
