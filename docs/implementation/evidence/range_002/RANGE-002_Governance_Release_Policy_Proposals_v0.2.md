# RANGE-002 Governance and Release Policy Proposals v0.2

| Field | Value |
|---|---|
| Status | **DRAFT FOR OWNER REVIEW. Proposals only. Nothing here is a decision, an approval, a signature, or an applied setting.** |
| Written | v0.1 2026-10-09 against `b31b5f7b` (#738 merged). **v0.2 refreshed 2026-10-10 against `origin/main` = `d61f313a` (#737, #738, #739 merged).** See section 0. |
| Scope | (1) main-branch review requirement, (2) permanent evidence retention, (3) Level 1 final acceptance checklist template |
| What was done to produce this | Read-only reads of the repository and read-only `gh api` / `gh run` GET queries (re-run for v0.2). No ruleset, branch-protection or repository setting was written. No bucket was created, nothing was uploaded, no AWS call was made, nothing was pushed. |
| Convention | Every recommendation is labelled "Recommendation (not a decision)". Owner decisions are listed in section 4. |
| Related | Level 1 Acceptance Test Plan v0.1 (`1d06024e`), CI and Release Coordination v0.1 (`cb2055e0`), P0 Owner Decision Package v0.1 (`f5cee030`), Governance Hardening Design v0.1, GITHUB-OPS-001 v1.2 |

**Explicit statement: NOTHING in this document is applied without separate, explicit owner approval.** Applying a ruleset, changing branch protection, adding CODEOWNERS, creating a bucket, or uploading evidence are each separate owner-authorized steps, and the first three are Tier 3 governance changes under GITHUB-OPS-001.

---

## 0. v0.2 refresh (2026-10-10)

### 0.1 Read-only re-check of protection and settings (no write of any kind)

| Query | v0.2 result | Changed since v0.1? |
|---|---|---|
| `GET .../branches/main/protection` | Required status check `Python CI Gate` (`app_id` 15368), `strict: true`; `enforce_admins: true`; no force pushes; no deletions; `required_signatures` false; linear history false; conversation resolution false; **no `required_pull_request_reviews`** | NO |
| `GET .../rulesets` | `[]` | NO |
| `GET .../collaborators` | `jayw04` only | NO |
| `GET repos/jayw04/AI-TRADING-APP` | public; user-owned; squash, merge and rebase merge all allowed; `allow_auto_merge` false; `delete_branch_on_merge` false; secret scanning, push protection and Dependabot security updates all `disabled` (new observation, not in v0.1) | secret-scanning fields newly recorded |
| `GET .../actions/permissions` and `/workflow` | Actions enabled, `allowed_actions: all`, `sha_pinning_required: false`; default workflow token `read`; `can_approve_pull_request_reviews: false` (so a workflow cannot approve PRs; option C therefore needs a repository-wide setting write) | newly recorded |
| CODEOWNERS / Dependabot config in the tree | none | NO |

So the single-owner feasibility problem is unchanged and remains the central constraint (section 1.3).

### 0.2 What happened since v0.1

- PR #738 and PR #739 merged. `main` is `d61f313a`; its tree equals the reviewed PR 3 head `808d10fb`. With the protection unchanged, the only GitHub-enforced controls on those merges were `strict` plus `Python CI Gate`; no GitHub-enforced human review existed, which is the control gap section 1 describes. (Any review done outside GitHub, such as the delta reviews recorded in the RANGE-002 documents, is real but not enforced by the platform.)
- The required-test manifest on `main` now lists **33 ids** (4 `pr2`, 29 `pr3`; none carries `pending_pr`), not 20. Section 3.5 is updated accordingly. Items A-5, L-2 and L-3 now have tests (manifest ids 21 to 33); the kill-mid-append item is covered by id 27 (SIGKILL during an append loop). The "no test found" table in v0.1 is therefore obsolete; the owner dispositions it asked for are no longer about missing tests, only about whether the new tests are sufficient.
- Actions artifacts are time-limited (30 days). Artifacts currently live (read-only `gh api actions/artifacts`):

| Artifact name (as printed) | Run id | Expires (UTC) |
|---|---|---|
| `range002-linux-acceptance-17a386f54347262e3a44d43dd0d04e64fa7f3815-1` | 38006570598 | 2026-11-09 00:22 |
| `range002-linux-acceptance-0c8112371331880bbe2c4ab4097128442388add1-1` | 38009454039 | 2026-11-09 00:55 |
| `range002-linux-acceptance-601b73633c77e04cb91e32cb2f9cae7f764e9442-1` | 38054522473 | 2026-11-09 13:24 |
| `range002-linux-acceptance-3778b06982dbfcd0b54748ab899b183247c1d25d-1` | 38057712216 | 2026-11-09 14:28 |

**Update (same day, local only):** all four artifact ZIPs were downloaded read-only and hashed; every local SHA-256 equals the GitHub-reported digest (4 of 4 MATCH, sizes equal). They are in `C:\LLM-APP\evidence\range002_artifact_zips_v0.1\` (outside the repository) with a `checksums.txt`; nothing was uploaded. Run context: 38006570598 and 38009454039 are PR 2 head runs (`2a28f270`, `7b27360a`); 38054522473 is a PR 3 run at `f93ee084`; **38057712216 is the PR 3 run at head `808d10fb`, whose tree equals `main` `d61f313a` (the final-tree run)**. Remaining step: the S3 package (section 2) is still unauthorised and not started.

The deadline for capturing and hashing them was therefore **about 2026-11-08** (the earliest expiry is 2026-11-09 00:22 UTC; v0.1 said about 2026-11-08 for the #738 pair, still the working deadline). The two newer artifacts come from the #739 runs (see the update above for which is the final-tree run).
- A push run of `main` at `d61f313a` was in progress at read time. Nightlies remain red (CI Nightly Remediation Proposal v0.2); they do not affect this document except that the `schedule` Gate is not currently a usable signal.
- Retention is still not done: no bucket was created, nothing was uploaded, no AWS call was made in this refresh.

### 0.3 Consequence for the recommendation (Recommendation (not a decision))

The recommendation in section 1.4 is unchanged: A if a second person exists, otherwise D recorded by ADR, with B only as a labelled process step. The new fact is only timing: two consequential governance PRs have now merged without an enforced second reviewer. If the owner wants the ruleset in force before the next consequential PR (for example the Level 2 implementation PRs or a spec-freeze PR), the dry run (section 1.9, step 4) needs to start well before it, because it should observe a week of real PRs. This is a sequencing remark, not a decision.

### 0.4 Secret scanning and push protection (verified read-only; NOT changed)

Read-only facts, 2026-10-10 (`gh api repos/jayw04/AI-TRADING-APP`; caller has admin):

| Setting (`security_and_analysis`) | Status |
|---|---|
| `secret_scanning` | **disabled** |
| `secret_scanning_push_protection` | **disabled** |
| `secret_scanning_non_provider_patterns` | disabled |
| `secret_scanning_validity_checks` | disabled |
| `dependabot_security_updates` | disabled (Dependabot alerts endpoint also returns 404, i.e. alerts are off) |

`GET .../secret-scanning/alerts` returns `404 "Secret scanning is disabled on this repository."` Code scanning has no analysis. Private vulnerability reporting is `enabled: false`. Availability: the repository is **public** and all five secret-scanning keys are present in the API response (the API omits keys for features the plan or repository cannot use), which indicates the feature is available for this repository; for public repositories GitHub offers secret scanning and push protection at no charge. The authoritative confirmation is the toggle becoming editable in the UI; I could not test by writing.

Exact change the owner would make (not performed here):

- UI: repository **Settings** > **Code security** (older UI: *Code security and analysis*) > **Secret scanning**: Enable; then **Push protection**: Enable. Optionally enable Dependabot alerts and security updates, and private vulnerability reporting, on the same page.
- API (needs admin; `gh auth` token with repo admin rights):

```text
PATCH /repos/jayw04/AI-TRADING-APP
{
  "security_and_analysis": {
    "secret_scanning": { "status": "enabled" },
    "secret_scanning_push_protection": { "status": "enabled" }
  }
}
```

Behaviour and risk: secret scanning scans the existing history and new pushes of a public repository and raises alerts (visible to admins; for provider patterns the provider may be notified). Push protection **blocks a push that contains a detected secret** until the pusher removes it or records a bypass reason (false positive, used in tests, will fix later); bypass is audited. False positives are possible (test fixtures, synthetic keys, high-entropy strings); the repository contains test and fixture material, so expect to meet some. It does not delete a secret already pushed: any alert on an existing secret means the credential must be rotated (CLAUDE.md: credentials are Fernet-encrypted at rest and not in the repository, so the expected alert count is zero). Enabling is reversible in the same place. It adds no Actions minutes and is not a workflow change.

Recommended verification step (Recommendation (not a decision)): after enabling, (1) confirm the two settings read `enabled` via the same GET; (2) review the initial alert list (`GET .../secret-scanning/alerts`) and rotate anything real; (3) on a throwaway branch, push a commit containing a documented non-secret test token pattern from the provider's published test strings to see a push-protection block (do this only with the owner's approval, and use a pattern GitHub documents as a test value, never a real credential). Because it changes repository settings, it needs the owner's explicit approval.

---

## 1. Main branch review requirement

### 1.1 What the owner recommended

A GitHub ruleset on `main` requiring: at least one approving review from someone other than the author; approvals dismissed when new commits are pushed; restricted administrative bypass; protection for `.github/workflows/` and research-governance / security-sensitive paths through CODEOWNERS plus a designated reviewer group.

### 1.2 Current state (read-only API queries, 2026-10-09)

| Query | Result |
|---|---|
| `GET repos/jayw04/AI-TRADING-APP` | User-owned (`owner.type = User`), **public**, default branch `main`. `allow_squash_merge`, `allow_merge_commit`, `allow_rebase_merge` all true. `allow_auto_merge` false. `delete_branch_on_merge` false. `allow_update_branch` false. Caller has admin. |
| `GET .../branches/main/protection` (classic) | **Exists.** `required_status_checks`: `strict: true`, one check `Python CI Gate` (`app_id` 15368). `enforce_admins: true`. `allow_force_pushes: false`, `allow_deletions: false`. `required_signatures: false`. `required_linear_history: false`. `required_conversation_resolution: false`. `lock_branch: false`, `block_creations: false`. **No `required_pull_request_reviews` block at all** (no PR requirement, no approvals, no code-owner review, no stale-review dismissal). No push restrictions. |
| `GET .../rulesets` | `[]`. **No rulesets exist.** |
| `GET .../collaborators` | One collaborator: `jayw04`, role `admin`. |
| `GET .../teams` | `[]` (a user-owned repository cannot have teams). |
| CODEOWNERS | **Absent.** Not at `CODEOWNERS`, `.github/CODEOWNERS` or `docs/CODEOWNERS` in the tree. |
| Dependabot / bots | No `.github/dependabot.yml` is tracked. The only workflow is `.github/workflows/ci.yml`. No bot is known to open PRs. |
| Merge queue / auto-merge | `allow_auto_merge` is false. Merge queue is believed unavailable for user-owned repositories (verify before relying on this). The exact-merge-result bar in the github-ops skill section 3.1 is therefore met only by `strict: true` today. |

Reading: today a change reaches `main` only if the exact head passes `Python CI Gate` and is up to date, even for the admin (`enforce_admins: true`), but **no second human, and no human at all, is required to look at it**. The owner's own merge is the only review event, and the walk-away interval is a convention, not an enforced control.

### 1.3 FEASIBILITY PROBLEM (read this first)

**The repository has exactly one collaborator, the owner, who is also the author of essentially every PR.** GitHub does not count an author's approval of their own PR toward required approvals. Therefore:

- A rule "at least one approving review from someone other than the author" **cannot be satisfied by anyone** with the current collaborator set. Applied without a bypass path, **every PR becomes unmergeable (solo-owner lockout)**.
- `enforce_admins: true` in the existing classic protection makes this worse: if the classic protection gained `required_pull_request_reviews` as it stands, the admin could not bypass it either.
- Without a bypass actor, the rule can only be applied safely if a second approver exists. With a bypass actor, the rule is applied but the owner can override it, so it constrains accidents and automation, not the owner.
- A user-owned repository has no teams, so "designated reviewer group" cannot be a team. CODEOWNERS on a user-owned repository can name only individual users who have write access (a CODEOWNERS entry naming someone without write access is ignored, and `require_code_owner_review` can then become unsatisfiable).
- Combining `require_code_owner_review` with the owner as sole code owner reproduces the same lockout: the owner is a code owner but is the author.

What the control can and cannot deliver, honestly: with one human, a "review by someone other than the author" is not independent review. It can at most be (a) a real second person, or (b) a deliberate extra step that changes credentials or context but is not independence.

### 1.4 Options

All are "Recommendation (not a decision)" ranked by how much real independence they supply.

| Option | What it is | Independence | Cost / risk | Notes |
|---|---|---|---|---|
| **A. Second human reviewer** | Invite one trusted person (write access, "Triage" is not enough for an approval that counts toward required reviews) and name them in CODEOWNERS. | **Real.** The only option that delivers what the owner described. | Needs a person who can read governance code and the owner's agreement to be blocked by them. Availability becomes a merge dependency; the ruleset should then have no bypass (or a logged, owner-only `pull_request`-mode bypass for incidents). | Matches the Level 1 plan's "independent reviewer, non-AI person" question (Q-A1). The same person can plausibly be both. |
| **B. Dedicated reviewer machine account** | A second GitHub account controlled by the owner (GitHub terms allow a machine account for automation, one per person; confirm current terms), added with write access, used only to approve. | **None in substance** (same human). It adds a second credential and a deliberate context switch, and makes approvals attributable to a distinct identity. | Cheap. Risk: it can be mistaken for independence in an audit. Must be described as a process control, never as independent review. Credentials of the second account need separate protection (2FA, separate password manager entry). | If chosen, state in the ruleset description and in the acceptance report that approvals by this account are not independent reviews. |
| **C. Actions-based required approval check** | A workflow job (required status check) that passes only when a signed or attested review artifact exists for the head SHA, for example a reviewer-produced review report committed outside the PR or a checked label from a non-author. | Depends on who produces the attestation; a GitHub Actions bot approving its own repository's PRs adds **no** independence (and requires enabling "Allow GitHub Actions to create and approve pull requests", which is off by default and is a repository-wide settings write). | Adds a new check to the required set, edits `ci.yml` (flags FULL for every project, GITHUB-OPS-001 section 3), and creates a fail-open or fail-closed design question. Not recommended as the primary control. | Could complement A or B for checking that a review report file exists and matches the head SHA. |
| **D. Owner-acknowledged risk acceptance** | Apply the ruleset with the owner as `pull_request`-mode bypass actor (or apply only the non-review rules) and record in an ADR that single-owner review is an accepted residual risk until a second reviewer exists. | None for the review rule. Still delivers: no direct pushes, no deletion, no force-push, required `Python CI Gate`, strict, CODEOWNERS visibility on PRs. | Lowest friction. The review rule exists on paper but the owner can bypass it, so it must not be cited as an enforced independent control. | Honest fallback. A governing ADR is required for a deviation from the "disciplined" claim (CLAUDE.md: invariants relax by ADR). |

Recommendation (not a decision): **A if a person is available; otherwise D recorded by ADR, with B added only as an explicit, labelled process step.** Do not ship C alone.

### 1.5 Effect on the owner's merge flow and on automation

| Topic | Effect of the proposed ruleset | Mitigation |
|---|---|---|
| `gh pr merge N --squash --match-head-commit <sha>` | Fails with "review required" until an approval from a non-author exists. With a bypass actor in `pull_request` mode, the owner merges with `gh pr merge --admin` (or the UI bypass button) and the bypass is logged. | Document the exact command in the runbook. Keep `--match-head-commit`. |
| Required status check `Python CI Gate`, `strict: true` | Unchanged; the ruleset repeats the same check and the same strict flag, so both mechanisms agree. | Keep `integration_id` 15368 so only GitHub Actions can report it. |
| Dismiss stale approvals on push | Each new commit, including a local `git merge origin/main` pushed to satisfy `strict`, dismisses the approval. The github-ops skill section 7.2 flow (merge main once, push once) therefore costs one more review round whenever `main` moves. | Merge approved PRs in an order that avoids BEHIND churn; accept re-approval on base moves; with `require_last_push_approval` the reviewer must be someone other than the last pusher. |
| `require_last_push_approval` | The person who pushed the most recent commit cannot be the approver. For a sole owner this is again unsatisfiable without a second account. | Include only if option A or B is chosen. |
| Walk-away discipline | Not enforced by either rule set. | Unchanged: convention in CLAUDE.md (1 h; 2 h consequential). |
| Dependabot and bots | None configured. If added later, their PRs also need an approval; they cannot approve themselves. | Decide at that time; do not add bypass for bots by default. |
| Merge queue | Not available (believed) for user-owned repositories. | Exact-merge-result remains `strict: true`. |
| Auto-merge | Disabled at the repository level; a ruleset does not change that. | None. |
| Draft PRs | CI runs zero jobs on drafts (ci.yml); a ruleset does not change that. | None. |
| Direct pushes to `main` | Blocked by both the classic checks (already) and the ruleset `pull_request` rule. The `push`-to-main CI trigger continues to run after merges. | None. |
| Editing rulesets | Ruleset administration is an admin repository setting, not subject to the rules it defines, so a misconfigured ruleset can always be fixed or disabled by the owner. Lockout of merges is recoverable; it is a delay, not a loss of the repository. | Rollback steps in 1.9. |
| `.github/workflows/ci.yml` edits | The ruleset itself does not need a `ci.yml` change. | Keep it that way (a `ci.yml` change flags FULL for all four projects). |

### 1.6 Proposed ruleset JSON (for `POST /repos/jayw04/AI-TRADING-APP/rulesets`)

Not applied. Two variants. Variant 1 assumes a second approver (option A or B). Variant 2 is option D (owner bypass in `pull_request` mode, which allows bypass only through a pull request and records it).

Verify before applying: that the personal-repository plan accepts `bypass_actors` with a `RepositoryRole` actor (role id 5 is the repository Admin role in GitHub's ruleset API), and whether `"enforcement": "evaluate"` (dry-run, "Evaluate" mode) is accepted for this account. Evaluate mode is documented as an Enterprise-plan feature; if the API rejects it, use the dry-run alternative in 1.9.

Variant 1, no bypass (second approver required):

```json
{
  "name": "main-protection-review-v1",
  "target": "branch",
  "enforcement": "evaluate",
  "conditions": {
    "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] }
  },
  "bypass_actors": [],
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": true,
        "require_last_push_approval": true,
        "required_review_thread_resolution": false,
        "allowed_merge_methods": ["squash", "merge"]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          { "context": "Python CI Gate", "integration_id": 15368 }
        ]
      }
    }
  ]
}
```

Variant 2, owner bypass through pull request only (option D):

```json
{
  "name": "main-protection-review-v1-owner-bypass",
  "target": "branch",
  "enforcement": "evaluate",
  "conditions": {
    "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] }
  },
  "bypass_actors": [
    { "actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request" }
  ],
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": true,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false,
        "allowed_merge_methods": ["squash", "merge"]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          { "context": "Python CI Gate", "integration_id": 15368 }
        ]
      }
    }
  ]
}
```

Notes:

- `allowed_merge_methods` is set to squash and merge-commit because those are what the repository history uses; the owner may drop it (all three methods stay allowed) or restrict it. Recommendation (not a decision).
- The ruleset coexists with the existing classic protection; when both apply, the more restrictive result wins. Leaving the classic protection in place is the safer rollout (it keeps `enforce_admins`), but note that `enforce_admins: true` on the classic protection does not by itself block a ruleset bypass actor, and the classic protection has no review rule, so the two do not conflict.
- Path-specific rules (`file_path_restriction`) are an Enterprise-plan ruleset feature and are not proposed; path protection is delivered by CODEOWNERS (1.8).
- `require_signed_commits` is deliberately not proposed: the owner's local signing setup was not examined, and Approval Signing design is a separate owner topic.

### 1.7 Exact equivalent classic branch-protection payload (for `PUT /repos/jayw04/AI-TRADING-APP/branches/main/protection`)

Not applied. The classic `PUT` **replaces the whole protection object**, so this payload restates every existing setting found in 1.2 and adds only `required_pull_request_reviews`. Save the current `GET` output first (1.9).

```json
{
  "required_status_checks": {
    "strict": true,
    "checks": [ { "context": "Python CI Gate", "app_id": 15368 } ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true,
    "required_approving_review_count": 1,
    "require_last_push_approval": true
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": false,
  "lock_branch": false,
  "allow_fork_syncing": false
}
```

Classic-protection caveats:

- **`enforce_admins: true` plus a review requirement plus a single collaborator is the full lockout configuration**: even the admin cannot bypass. If the owner takes option D, classic protection cannot express a `pull_request`-mode bypass for a personal repository (`bypass_pull_request_allowances` is available only on organization-owned repositories, believed; verify). That is the main reason the ruleset form is preferred.
- Classic protection has no evaluate mode and applies immediately.
- Recommendation (not a decision): use the ruleset (Variant 1 or 2) and **leave the classic protection exactly as is**.

### 1.8 CODEOWNERS proposal

Proposed file `.github/CODEOWNERS` (not created). The last matching pattern wins. Replace `@REVIEWER_TBD` only after the owner names the reviewer (none is chosen here, and a user without write access is silently ignored). Until a second user exists, listing only `@jayw04` documents ownership and requests his review but cannot create independence.

```text
# Proposed. Not in effect until the owner approves and commits this file.
# Owner decides the reviewer(s). No reviewer is chosen by this proposal.
# Format: <pattern> <users with write access>

*                                                @jayw04
/.github/workflows/                              @jayw04 @REVIEWER_TBD
/.github/CODEOWNERS                              @jayw04 @REVIEWER_TBD
/apps/backend/app/research/range002/             @jayw04 @REVIEWER_TBD
/apps/backend/app/risk/                          @jayw04 @REVIEWER_TBD
/apps/backend/app/orders/                        @jayw04 @REVIEWER_TBD
/docs/adr/                                       @jayw04 @REVIEWER_TBD
/manifests/                                      @jayw04 @REVIEWER_TBD
/docs/implementation/evidence/range_002/RANGE-002_governance_manifest.json  @jayw04 @REVIEWER_TBD
/apps/backend/ci/                                @jayw04 @REVIEWER_TBD
```

Notes: CODEOWNERS is evaluated from the base branch's copy of the file (a PR cannot weaken its own ownership). The `/.github/CODEOWNERS` line protects the file itself. A catch-all `*` line makes every PR request the owner as a reviewer and, with `require_code_owner_review`, makes every PR need a code-owner approval; drop it if only the sensitive paths should require approval. Recommendation (not a decision): omit `*` and let only the listed paths require code-owner approval. Editing `.github/CODEOWNERS` is not a `GLOBAL_PATTERNS` path in `apps/backend/scripts/ci_classify_changes.py` (only `.github/workflows/ci.yml` and root dependency manifests are), so it should stay LIGHT; verify with the classifier before pushing.

### 1.9 Compatibility checklist, rollout, rollback

Compatibility checklist (all must be answered by the owner or verified before applying):

- [ ] A second approver exists and has write access (option A or B), or option D is chosen and recorded by ADR.
- [ ] CODEOWNERS names only users with write access; the owner is not the only code owner on a path with `require_code_owner_review` unless bypass exists.
- [ ] `Python CI Gate` still reports on the exact head SHA for docs-only PRs (it does; LIGHT/FULL resolves to a pass), and its `integration_id` is 15368 as in the current protection.
- [ ] `strict: true` kept in both mechanisms.
- [ ] The owner's merge command is documented, including `--match-head-commit` and (if option D) `--admin`.
- [ ] The github-ops skill and CONTRIBUTING.md are updated in the same change to describe the review requirement (they currently say nothing about required reviews). Recommendation (not a decision): batch with other governance edits to avoid separate CI cycles.
- [ ] No GitHub Actions workflow depends on pushing to `main` from the workflow token (none found in `ci.yml`; confirm).
- [ ] No Dependabot or other bot PR flow exists or is planned.
- [ ] The Level 1 acceptance reviewer and the repository reviewer are decided together (same person or not), so the independent-reviewer question (Q-A1) is answered once.
- [ ] The `docs/methodology/GITHUB_OPS_001_Phase2_Org_Settings_Checklist.md` known gap (github-ops section 9) is acknowledged; this proposal does not create it.

Rollout plan (each step needs owner approval; none is performed by this document):

1. Owner decides options and names reviewer(s) (section 4).
2. Capture the current state to controlled storage: save the output of `GET .../branches/main/protection` and `GET .../rulesets` (the content in 1.2), timestamped, with SHA-256. This is the rollback source.
3. Merge CODEOWNERS (and any CONTRIBUTING / skill text) through a normal reviewed PR. No ruleset is active yet, so this cannot lock anyone out.
4. **Dry run.** Preferred: create the ruleset with `"enforcement": "evaluate"` and watch the rule insights for one week of real PRs. If the API rejects evaluate mode for this account, use the substitute: create the ruleset targeting a throwaway branch pattern (change `conditions.ref_name.include` to `refs/heads/ruleset-trial/*`), open two trial PRs against a trial base, and confirm approve / dismiss-on-push / bypass behaviour. Neither approach affects `main`.
5. Owner reviews the dry-run result, then separately approves switching `enforcement` to `active` on `main` (PATCH the ruleset).
6. After activation, merge one low-risk docs-only PR through the full new flow, including the base-move re-approval case, before relying on it for RANGE-002 PR 3.
7. Record the activation in an ADR (or a governing doc update) with the ruleset id and the saved pre-change JSON checksum.

Rollback:

- Ruleset: `PATCH /repos/jayw04/AI-TRADING-APP/rulesets/{id}` with `"enforcement": "disabled"`, or `DELETE` the ruleset. Takes effect immediately. The owner is an admin and can always do this.
- Classic protection (only if the classic payload was applied): `PUT` the saved pre-change JSON from step 2 (restates `strict`, `Python CI Gate`, `enforce_admins`, no review block), or `DELETE .../protection/required_pull_request_reviews`.
- CODEOWNERS: revert the file by a normal PR (merge may itself need the rollback above if a code-owner rule is locking).
- Emergency: if a production incident requires a merge while locked, disable the ruleset first, merge, then re-enable and record the reason in the PR (GITHUB-OPS-001 section 6 exception).

### 1.10 Single-owner risk write-up and Option D ADR proposal

**Why a second-person review rule is unsatisfiable today.**

1. GitHub never counts an author's approval of their own pull request toward `required_approving_review_count`. The repository has exactly one collaborator (`jayw04`), who is the author of essentially every PR. With a rule "at least one approval from someone other than the author", no PR can ever reach the required count.
2. `enforce_admins: true` is already set on the classic protection. Adding `required_pull_request_reviews` to that same protection would apply to the admin too, so the owner could not bypass it: every PR, including a PR that removes the rule, would be unmergeable from the UI/API without first editing the protection (an admin settings action that is always available, but is a manual detour for every merge).
3. A user-owned repository has no teams, so a reviewer group cannot exist. CODEOWNERS can name only individual users with write access; a name without write access is ignored, and `require_code_owner_review` with the owner as the only code owner reproduces the same lock-out.
4. `require_last_push_approval` and `dismiss_stale_reviews_on_push` add churn: the owner's own base-branch merge (to satisfy `strict: true`) would dismiss approvals.
5. Using a second account controlled by the same person satisfies the counter but not the purpose: it is a process control, not independent review, and must be described as such in any audit statement.

Consequence today: the controls that actually bind a merge into `main` are `Python CI Gate` (required, `strict`), no force-push, no deletion and the owner's own merge. Walk-away intervals are a convention. For order-path code (OrderRouter, risk gates), CLAUDE.md's invariants rely on CI invariant scripts and the owner; there is no enforced second human.

**What each path costs.** A real second reviewer (option A) gives the only genuine independence and makes the ruleset enforceable with no bypass. Option D keeps the ruleset or the existing protection as is and records, by ADR, that single-owner review is an accepted residual risk until a second reviewer exists. Option D does not weaken any CI invariant; it states honestly what is and is not enforced.

**Proposed ADR text for Option D (PROPOSAL ONLY; blank approval; not an ADR until the owner adopts it through the normal ADR process).**

```text
ADR NNNN (PROPOSED): Single-owner review of changes to main is an accepted, recorded risk
Status: PROPOSED. Not adopted. Date: ____  Decision owner: ____
Context: The repository has one collaborator, the owner, who authors changes. GitHub cannot
  enforce a review "by someone other than the author" (author approvals do not count), and
  enforce_admins is true, so enabling a required-review rule today would make every PR
  unmergeable. Required checks today: Python CI Gate (strict). No force-push, no deletion.
Decision (to be chosen by the owner): until a second human reviewer with write access exists,
  (1) no required-review rule is activated on main; (2) changes to the order path, risk
  engine, audit log, workflows and RANGE-002 governance code are merged only after the PR
  walk-away interval (CLAUDE.md) and a recorded self-review checklist in the PR body;
  (3) this limitation is stated, not hidden, in every acceptance report: reviews by the owner
  or by a second account controlled by the owner are not independent reviews;
  (4) the decision is re-evaluated when a second reviewer is added or by ____ (date).
Consequences: No new enforcement. The invariants in CLAUDE.md and the CI invariant scripts
  remain the binding controls. Independence claims in RANGE-002 reports require an external
  reviewer (see the Level 1 Acceptance Test Plan).
Alternatives considered: A second human reviewer plus ruleset Variant 1; a machine account
  (process control only); an Actions-based approval check (no independence).
Approval: Owner: ______________________  Date: ____________   (blank; nothing is approved)
```

Recommendation (not a decision): adopt option A when a person is available; until then option D by ADR is the honest state. Adopting option D requires an ADR through the normal ADR process; this text is a draft only.

---

## 2. Permanent evidence retention

### 2.1 Two levels

| Level | Where | Lifetime | Role |
|---|---|---|---|
| 1. GitHub Actions artifacts | `actions/upload-artifact@v4`, `retention-days: 30` in `ci.yml` | **Temporary, 30 days.** The #738 artifacts (run 38006570598 `range002-linux-acceptance-17a386f5...-1`, run 38009454039 `range002-linux-acceptance-0c811237...-1`) expire about **2026-11-08/09**; the #739 run artifacts expire 2026-11-09 (section 0.2). | Working evidence. Not a record. |
| 2. Controlled, versioned S3 Level 1 acceptance package | Bucket and prefix to be decided by the owner, versioning on, SSE on, public access blocked | Permanent / retention-class per owner | The record. The acceptance report cites this package, not the Actions artifact. |

Rule (GITHUB-OPS-001 section 5, github-ops section 5): Git carries the **manifest and the report**; S3 carries the **bulk**. Guidance for a package of small files (this package is tens of kilobytes): the policy table classes "CI evidence" as S3 or short-lived artifacts, so the JUnit XML and logs go to S3; the human-readable acceptance report and the manifest are governing and are reviewable in a diff, so they belong in Git.

### 2.2 Package contents

| Item | Source | Notes |
|---|---|---|
| JUnit XML from every Linux run used as evidence | Actions artifact `range002-linux-acceptance-<github.sha>-<attempt>` | `<github.sha>` is the PR **merge** commit sha, not the PR head (CI Release Coordination U10). Record the run id too. |
| Verifier tables / summary output | Same artifact and run log | The required-test verifier output (PASSED / PENDING / FAILED per id). |
| Commit SHAs | Frozen SHA under test, PR head sha, merge sha | One row each, with the role. |
| Workflow run ids and artifact names | `gh run view`, `gh api .../actions/runs/{id}/artifacts` | Copy exactly as printed. |
| Artifact SHA-256 checksums | Computed locally at download time (2.5) | Of the downloaded `.zip` and of each extracted file. |
| Windows run output | Reviewer's Windows run | Separate from Linux. |
| Independent review report(s) | Reviewer | The acceptance plan section 8 report. |
| Final acceptance decision | Owner | Signed by the owner only; blank until then. |
| The test manifest (`apps/backend/ci/range002_required_linux_tests.json`) at the frozen SHA | `git show <sha>:...` | So the id list is part of the record. |
| Package manifest | Generated, committed to Git | 2.3. |

### 2.3 Manifest format (conforming to GITHUB-OPS-001 section 5.1, no invented scheme)

**What exists in the repository, verified:**

- `manifests/s3/` does **not** exist. `scripts/s3_fetch_verify.py`, `scripts/s3_publish_manifest.py`, `scripts/check_s3_manifests.py`, the `S3 manifest gate` CI job and `docs/runbook/s3-artifacts.md` are **not in the repository** (policy working copy Phase 3 table and github-ops section 5 both say so; no tracked path matches).
- `manifests/` today holds `deploy/`, `forward/`, `layer2/`, `mdq/`: domain-specific, hand-written JSON manifests. The nearest precedent is `manifests/deploy/amendment8_3f32c75b.json`, whose `artifact` block carries `s3_bucket`, `s3_key`, `s3_version_id`, `s3_etag`, `archive_sha256`, `archive_size_bytes`. The bucket named there (`workbench-backups-219024422756`) is the existing custody bucket; `deploy/aws/provision-versioned-s3.sh` provisions versioned buckets. These are precedent for the field names, not a governed schema.
- `apps/backend/app/validation/aws/s3_sink.py` is an existing Object Lock witness sink (ADR 0046) and shows the repository's stance: `GetBucketVersioning` and Object Lock configuration are verified and the writer holds no `BypassGovernanceRetention`.

**Consequence.** There is no merged tooling or schema to conform to. github-ops section 5 says: do not hand-roll a competing scheme; raise it. The minimal conforming approach, **Recommendation (not a decision)**:

1. Use exactly the field list that the binding policy (section 5.1) already mandates, as a single JSON package manifest, so a future `manifests/s3/` gate can adopt it without change. Fields per object: `bucket`, `key`, `s3_version_id`, `sha256`, `size_bytes`, `artifact_id`, `format_version`, `created_utc`, `producer` (workflow run id or reviewer), `owner`, `retention_class`, `sensitivity`. Package-level: `package_id`, `schema` (a version string, `range002-level1-acceptance-package/1`, clearly marked provisional), `frozen_commit_sha`, `object_lock` (mode, retain-until), and the manifest's own SHA-256 recorded in the acceptance report and the PR.
2. Place it at `manifests/range002/level1_acceptance_<frozen_sha8>.json` (beside the existing domain manifests; **not** under `manifests/s3/`, which is reserved for the unmerged scheme) and say in its `notes` that it is provisional until the `manifests/s3/` tooling lands, at which point it is migrated. This avoids occupying `manifests/s3/` with an unreviewed schema.
3. **Fail closed, never `latest`**: every reference carries a Version ID; the verifier (a procedure for now, a script later) fetches by `(key, versionId)`, recomputes SHA-256, and fails on missing object, mismatch, access denied, or unknown schema.
4. Do not add CI changes for this; verification is a manual procedure run by the reviewer and recorded in the report. A `ci.yml` edit would flag all four projects FULL.

What the owner must authorize (none done here): the bucket and prefix; Object Lock mode and period; who may write and read; creation of the manifest file and its PR; whether to write the minimal fetch/verify script now or wait for the Phase 3 tooling; the exact `schema` string.

### 2.4 Bucket, versioning, Object Lock, access

| Item | Proposal | Status |
|---|---|---|
| Bucket | Reuse an existing custody bucket under a dedicated prefix (for example `range002/level1/<frozen_sha8>/`) or a new bucket. Either needs owner approval. | Recommendation (not a decision): a dedicated prefix in a versioned bucket, so no new bucket is created for ~tens of KB. |
| Versioning | Required, SSE on, public access blocked, access logging per policy section 5.2. | Recommendation (not a decision) |
| Object Lock | Optional; **owner decision on mode and period**. Object Lock can only be enabled with versioning and, for a new bucket, at creation (enabling on an existing bucket is possible but irreversible once on). `GOVERNANCE` mode: protected from ordinary deletion, removable only by a principal holding `s3:BypassGovernanceRetention`, so recoverable. `COMPLIANCE` mode: **nobody, including the account root, can shorten or remove the retention before it expires**; a mistaken upload (secrets, wrong file) or an over-long period cannot be undone, and the objects bill for storage until expiry. | **Owner decision.** Recommendation (not a decision): if a lock is wanted, use `GOVERNANCE` for the acceptance package with a period the owner states; reserve `COMPLIANCE` for classes the owner has explicitly approved, as github-ops section 5 requires ("never enable it casually on a working bucket"). Do not place Object Lock on a bucket that holds working data. |
| Retention class | Owner-defined label in the manifest (`retention_class`). | Owner decision |
| Writers | Exactly one: the owner's AWS identity, or a dedicated least-privilege role/principal assumed only for this upload; **no long-lived keys in CI** (policy: OIDC short-lived credentials only). Uploads performed by a human, not by a workflow. The writer has `s3:PutObject` on the prefix and no `s3:DeleteObjectVersion`, no `s3:BypassGovernanceRetention`, no `s3:PutBucketObjectLockConfiguration`. | Recommendation (not a decision) |
| Readers | The owner and the named independent reviewer (read-only, `s3:GetObject` and `s3:GetObjectVersion` on the prefix), plus a CI role only if the owner later wants an automated verifier. | Owner decision |
| Separation | The reviewer should not be able to write or delete, and the package writer should not be the only person who verifies it. | Recommendation (not a decision) |
| Secrets | Nothing secret goes in the package. The JUnit XML and logs are synthetic-fixture outputs; scan before upload. | Required by policy |

### 2.5 How to fetch and hash the Actions artifacts (while they are still live, before about 2026-11-08)

Run from a clean working directory, one directory per run (downloaded files are untrusted data; do not run anything from them):

```text
gh run view 38009454039 --repo jayw04/AI-TRADING-APP --json databaseId,headSha,conclusion,workflowName,createdAt,url
gh api repos/jayw04/AI-TRADING-APP/actions/runs/38009454039/artifacts --jq '.artifacts[] | {id,name,size_in_bytes,expired,expires_at,digest}'
gh run download 38009454039 --repo jayw04/AI-TRADING-APP --name "range002-linux-acceptance-0c8112371331880bbe2c4ab4097128442388add1-1" --dir <fresh-empty-dir-1>
sha256sum <fresh-empty-dir-1>/*          # Git Bash; PowerShell: Get-FileHash -Algorithm SHA256
```

Notes: `gh run download` extracts the artifact zip, so also hash the extracted files; the API artifact listing may expose a server-side `digest` for the zip, which should be recorded beside the locally computed values and compared if both are present (do not assume the field exists). Repeat for run 38006570598. For the **final acceptance run** (a PR 3 run on the frozen SHA, not yet existing), do the same within the 30-day window, and record the run id, the artifact name exactly as printed, and the digests.

### 2.6 Order of operations and verification

1. Freeze the commit SHA (acceptance plan section 7) and confirm the run(s) used as Linux evidence are on that SHA.
2. While artifacts are live: download, hash (2.5), and record run ids / names / SHAs. Do not wait for the 30-day expiry.
3. Collect the Windows run output, the reviewer's report, and the manifest at the frozen SHA.
4. Scan the set for secrets and unrelated data.
5. Owner approves bucket, prefix, lock mode and period, and the writer (section 2.4). Only then does anything touch AWS.
6. Upload the objects with versioning on; read back each `VersionId` from the response (the AWS CLI or SDK upload result), never `latest`.
7. Download each object by `(key, versionId)` to a fresh directory, recompute SHA-256, and compare with the local values from step 2. A mismatch stops the process.
8. Write the package manifest with bucket, key, version id, sha256, size for every object; commit it with the acceptance report in one PR (a coherent deliverable, one review round); record the manifest's own SHA-256 in the report and the PR.
9. A second person (the reviewer, with read access) repeats step 7 independently from the manifest alone. Only then is the package considered preserved.
10. Record in the report that the Actions artifacts remain temporary and are not the record.

---

## 3. Final Level 1 acceptance checklist template

Not a result. Every cell is blank or PENDING. No signature, approval or name is filled in. The owner names reviewers; none is chosen here.

Source note: the repository's Level 1 Acceptance Test Plan v0.1 defines the matrix (sections 5.1 to 5.12), the stop criteria STOP-1 to STOP-7 and the claim wording, but **contains no list titled "seven criteria"**. The seven rows below are a preparer's consolidation of the plan, labelled Recommendation (not a decision). The owner should replace them if a different seven are intended.

### 3.1 Header

| Field | Value |
|---|---|
| Frozen commit SHA under test | |
| PR head SHA / PR merge SHA (Linux run) | |
| Date frozen | |
| Plan version | Level 1 Acceptance Test Plan v0.1 (`1d06024e`) with X-L2, X-F4, X-N1..N8 texts supplied (STOP-4) |
| Executor (independent reviewer, named by the owner) | |
| Package manifest path and SHA-256 | |
| S3 bucket / prefix / manifest version ids recorded | |

### 3.2 The seven criteria

Legend: PASS, FAIL, PENDING (default), N/A (owner-recorded only).

| # | Criterion | Plan reference | Status | Evidence (run ids, artifact names, SHAs, report sections) |
|---|---|---|---|---|
| 1 | Every previously demonstrated exploit (X-H1..X-F11, X-N1..N8) re-run against the frozen SHA as originally demonstrated, and refused or contained; original texts supplied | 5.1, STOP-1, STOP-4 | PENDING | |
| 2 | Series tests I, P, D, K, H, C, T, R, S, A, L executed with the expected outcomes (T-2 recorded as documented residual, not claimed as detected) | 5.2 to 5.12 | PENDING | |
| 3 | Linux CI run on the frozen SHA: all manifest ids PASSED (33 ids at `d61f313a`; re-read the manifest at the frozen SHA), required-test verifier succeeded, zero skips in the must-not-skip set | 3, 6, STOP-2 | PENDING | |
| 4 | Windows run reported separately, skipped tests listed as SKIPPED with reason and symlink privilege stated | 3, 8 | PENDING | |
| 5 | Executor independent of the implementation; report written without implementer edits; no change to code or tests after the SHA freeze | 2, 7, STOP-5, STOP-6 | PENDING | |
| 6 | No stop criterion fired (STOP-1 to STOP-7); no non-deterministic result; no Level 2 claim needed to explain a pass | 9, STOP-3, STOP-7 | PENDING | |
| 7 | Evidence preserved: Actions artifacts hashed, S3 package uploaded with Version IDs, independently re-verified, manifest merged to Git, residual risk register and skip register complete | 8, section 2 of this document | PENDING | |

### 3.3 Windows result table

Kept separate from Linux. A Linux pass never fills a Windows cell.

| Test id / series | Env | Result (PASS / FAIL / SKIPPED / NOT RUN / NOT IN SCOPE) | Skip reason | Evidence reference |
|---|---|---|---|---|
| X-series | W | | | |
| I, P, D, K, H series | W | | | |
| C series | W | | | |
| T, R, S series | W | | | |
| A-1, A-2, A-3, A-4, A-5, A-6 (aliases) | W | | symlink privilege available? Y/N | |
| Totals | W | PASS = , FAIL = , SKIPPED = , NOT RUN = , NOT IN SCOPE = | | |

### 3.4 Linux result table

| Test id / series | Env | Result (PASS / FAIL / SKIPPED / NOT RUN / NOT IN SCOPE) | Skip reason | Run id / artifact name |
|---|---|---|---|---|
| X-series | L | | | |
| I, P, D, K, H series | L | | | |
| C series | L | | | |
| T, R, S series | L | | | |
| A-1, A-2, A-4, A-5 (aliases; no skips allowed) | L | | | |
| L-1 to L-6 (`fcntl`) | L | | | |
| Totals | L | PASS = , FAIL = , SKIPPED = , NOT RUN = , NOT IN SCOPE = | | |

### 3.5 Mandatory-test list (v0.2: 33 ids)

The manifest on `main` (`apps/backend/ci/range002_required_linux_tests.json`, `d61f313a`) lists **33 ids**: 4 `pr2` and 29 `pr3`; none carries `pending_pr`, so every one is mandatory. A run is PASS for this row only if the verifier reports every id PASSED (skipped, missing, errored and failed all fail). The list below is read from `main` and must be re-read at the frozen SHA before the table is filled.

| # | Test id (under `tests/research/range002/`) | Phase | Linux result | Run id / artifact |
|---|---|---|---|---|
| 1 | `spec/test_freeze_hardening.py::test_symlink_target_refused_and_nothing_written_through_it` | pr2 | PENDING | |
| 2 | `spec/test_freeze_hardening.py::test_dangling_symlink_target_refused` | pr2 | PENDING | |
| 3 | `spec/test_freeze_hardening.py::test_canary_symlinks_work_on_linux` | pr2 | PENDING | |
| 4 | `spec/test_manifest.py::test_symlinked_manifest_refused` | pr2 | PENDING | |
| 5 | `governance/test_round3.py::test_f9_symlink_alias_shares_the_lock` | pr3 | PENDING | |
| 6 | `governance/test_round3.py::test_f9_hardlink_alias_shares_the_lock` | pr3 | PENDING | |
| 7 | `governance/test_round3.py::test_f9_readers_are_not_blocked_by_the_writer_lock` | pr3 | PENDING | |
| 8 | `governance/test_round5_lock_backend.py::test_canary_lock_backend_matches_the_platform` | pr3 | PENDING | |
| 9 | `governance/test_round5_lock_backend.py::test_the_real_backend_excludes_a_second_holder` | pr3 | PENDING | |
| 10 | `governance/test_round5_lock_backend.py::test_fcntl_branch_runs_on_any_platform[False]` | pr3 | PENDING | |
| 11 | `governance/test_round5_lock_backend.py::test_fcntl_branch_runs_on_any_platform[True]` | pr3 | PENDING | |
| 12 | `governance/test_round5_lock_backend.py::test_four_processes_append_concurrently_through_the_real_backend` | pr3 | PENDING | |
| 13 | `governance/test_round5_lock_backend.py::test_namespace_lock_is_exclusive_through_the_real_backend` | pr3 | PENDING | |
| 14 | `governance/test_hashchain_lock.py::test_threads_with_stale_views_never_fork_the_chain` | pr3 | PENDING | |
| 15 | `governance/test_hashchain_lock.py::test_processes_serialize_appends_without_forking` | pr3 | PENDING | |
| 16 | `governance/test_hashchain_lock.py::test_second_writer_with_same_stale_view_serialises_after_the_first` | pr3 | PENDING | |
| 17 | `governance/test_hashchain_lock.py::test_lock_is_exclusive_and_fails_closed_on_timeout` | pr3 | PENDING | |
| 18 | `governance/test_hashchain_lock.py::test_append_blocked_by_a_held_lock_is_refused_not_forked` | pr3 | PENDING | |
| 19 | `governance/test_round5_nd_enroll_race.py::test_exactly_one_enrollment_wins_each_round[different]` | pr3 | PENDING | |
| 20 | `governance/test_round5_nd_enroll_race.py::test_exactly_one_enrollment_wins_each_round[same]` | pr3 | PENDING | |
| 21 | `governance/test_pr3_acceptance_a5_l2_l3.py::test_a5_symlinked_token_directory_is_one_identity` | pr3 | PENDING | |
| 22 | `governance/test_pr3_acceptance_a5_l2_l3.py::test_a5_symlinked_registry_directory_is_one_identity_one_lock_one_chain` | pr3 | PENDING | |
| 23 | `governance/test_pr3_acceptance_a5_l2_l3.py::test_a5_symlink_planted_over_a_file_name_is_never_written_through` | pr3 | PENDING | |
| 24 | `governance/test_pr3_acceptance_a5_l2_l3.py::test_a5_token_directory_redirected_through_a_link_cannot_reopen_the_holdout` | pr3 | PENDING | |
| 25 | `governance/test_pr3_acceptance_a5_l2_l3.py::test_l2_killed_chain_lock_holder_frees_the_lock_and_leaves_the_chain_intact` | pr3 | PENDING | |
| 26 | `governance/test_pr3_acceptance_a5_l2_l3.py::test_l2_killed_namespace_lock_holder_frees_the_lock_and_enrollment_still_works` | pr3 | PENDING | |
| 27 | `governance/test_pr3_acceptance_a5_l2_l3.py::test_l2_sigkill_during_an_append_loop_never_leaves_a_torn_or_forked_chain` | pr3 | PENDING | |
| 28 | `governance/test_pr3_acceptance_a5_l2_l3.py::test_l3_forked_child_cannot_append_while_the_parent_holds_the_lock` | pr3 | PENDING | |
| 29 | `governance/test_pr3_acceptance_a5_l2_l3.py::test_l3_lock_released_by_the_parent_is_not_kept_by_a_live_forked_child` | pr3 | PENDING | |
| 30 | `governance/test_pr3_acceptance_a5_l2_l3.py::test_l3_killed_parents_lock_stays_held_while_a_forked_descendant_lives` | pr3 | PENDING | |
| 31 | `governance/test_pr3_acceptance_a5_l2_l3.py::test_l3_capability_cannot_be_serialised_into_another_process` | pr3 | PENDING | |
| 32 | `governance/test_pr3_acceptance_a5_l2_l3.py::test_l3_capability_in_a_forked_child_is_valid_only_while_its_run_is_open` | pr3 | PENDING | |
| 33 | `governance/test_pr3_acceptance_a5_l2_l3.py::test_l3_forked_child_handle_appends_under_the_lock_without_forking_the_chain` | pr3 | PENDING | |

Former "additions pending" items: A-5 (ids 21 to 24), L-2 (ids 25 to 27, including the SIGKILL-during-append test that covers the former "kill-mid-append" gap) and L-3 (ids 28 to 33) now have tests in the manifest. Owner dispositions still open: whether these tests are accepted as sufficient for plan rows 5.11 and 5.12, and which Level 1 properties are accepted as stated (fork-inherited capability is run-bound; directory aliases yield a consistent identity but no confinement; a torn tail fails closed and locks out; R1-L1b distinct signatories is an accepted limitation, with a distinct-role follow-up separate).

### 3.6 Residual risk and skip registers

| Register | Required content | Status |
|---|---|---|
| Skip register | Every skipped test by node id, reason, platform; confirmation of zero skips on the required Linux set | PENDING |
| Level 2 residual risk register | Each Level 2 theme observed with the Level 1 behaviour found (for example T-2 clean truncation accepted by a fresh process; H4 approval signatures not implemented; M1 execution boundary absent) | PENDING |
| Deviations and missing inputs | Deviations from the plan; how X-L2, X-F4, X-N1..N8 were resolved | PENDING |

### 3.7 Sign-off (all blank; no names chosen)

| Role | Name (owner names) | Signature | Date |
|---|---|---|---|
| Independent reviewer / executor | | | |
| Second verifier of the S3 package (read-only) | | | |
| Owner (receipt of report, decision on merge) | | | |

The report is evidence, not approval. The owner decides the merge.

### 3.8 Claim wording

**Level 1 claim the report may make (only if every criterion is PASS and no stop criterion fired)**, verbatim from the plan section 11.1:

> "At commit <SHA>, an independent reviewer executed the RANGE-002 Level 1 Acceptance Test Plan v0.1 against the PR 2 / PR 3 governance and spec code. Every previously demonstrated Level 1 exploit listed in the plan was re-run and was refused or contained as specified. Windows results and Linux results are reported separately; the symlink, hardlink and POSIX fcntl tests ran on Linux with zero skips. The code resists accidental misuse, casual bypass, crashes, concurrent writers and wrong-path use as tested. This is a Level 1 result only."

**Level 2 claims that are prohibited** (plan section 11.2; the report must not state or imply any of these):

- That the registry, holdout or run counts are tamper-proof, tamper-evident against a determined actor, or "secure".
- That tail truncation or rollback of the registry is detected by a fresh process (it is not, without external anchoring).
- That holdout integrity is guaranteed against an actor with write access to the state directories.
- That research code cannot read unsealed results (no trusted execution boundary exists).
- That approvals or sign-offs are cryptographically authenticated (H4 not implemented).
- That the exposure ledger or spec are independently attested.
- That a Level 2 or "adversarial" review has been passed, or that the system is "production ready", "audited", or "certified".
- That any strategy, spec or result is valid; the plan tests governance mechanics only.
- That passing implies merge approval; the owner decides.

Added by this document, Recommendation (not a decision): the report must also not describe a main-branch review approval by a machine account (option B) as an independent review, and must not call Actions artifacts the permanent record.

---

## 4. Questions for the owner (nothing is decided here)

1. Is there a second person who can be the repository reviewer and the Level 1 executor, or is option D (recorded risk acceptance by ADR) the intended path? (Option A / B / C / D, section 1.4.)
2. If a second account is used (option B), do you accept that it is a process control and not independence, and that the report will say so?
3. Ruleset variant 1 (no bypass) or variant 2 (owner bypass in `pull_request` mode); include `require_last_push_approval` or not; keep `allowed_merge_methods` or not.
4. May the dry run use evaluate mode, or, if the account rejects it, the throwaway-branch substitute?
5. Reviewer identity for CODEOWNERS, whether to include the catch-all `*` line, and whether `.github/CODEOWNERS` and the governance manifest should require the second reviewer.
6. S3: which bucket and prefix, whether Object Lock is wanted at all, and if so mode (GOVERNANCE or COMPLIANCE) and retention period; who writes and who reads.
7. May the provisional package manifest live at `manifests/range002/` until the `manifests/s3/` tooling lands, or should the package wait for that tooling?
8. Confirm or replace the seven criteria in section 3.2 (the plan has no list under that name).
9. (v0.2) A-5, L-2, L-3 and the kill-mid-append item now have tests (manifest ids 21 to 33). Are they accepted as sufficient for plan rows 5.11 and 5.12, or are further tests wanted?
10. Authorization to capture the live Actions artifacts and digests (the #738 pair and the #739 pair, section 0.2) before about 2026-11-08 (a local download only; no upload implied).
11. (v0.2) Because #738 and #739 merged with only the owner's own merge as the GitHub review event, is the ruleset wanted before the next consequential PR, and if so which option (A to D)?

Nothing in this document is approved, signed or applied. Every recommendation above is a Recommendation (not a decision).
