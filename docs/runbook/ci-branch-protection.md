# CI branch protection — activating the `Backend CI Gate` (repo-settings step)

**Status:** the workflow half of the light/full hardening landed in the CI PR (path-filtered FULL-on-PR
+ the always-run `Backend CI Gate`). This runbook is the **second, separately-recorded step**: turning
on the GitHub branch-protection rule that makes the gate actually *block* merges. Until this is applied
**and verified**, a red `Backend CI Gate` does not stop a merge — the automation is in place but not
enforced.

> The protection rule is **not** considered complete until a test PR proves GitHub blocks merging on a
> red `Backend CI Gate`.

## Why a repo setting (and not the workflow)

A workflow can *run* checks; only branch protection can make a check *required* for merge. That toggle
lives in repository settings / the GitHub API, so it cannot ship inside `ci.yml`. The `#475/#477`
incident had two causes — FULL didn't run on the PR (fixed in the workflow) **and** no required check
blocked merge (fixed here).

## Which check to require

Require exactly one Python status check: **`Backend CI Gate`**.

It is the single stable, always-run aggregate. It already fails closed unless the LIGHT/static checks
passed **and** (the classifier proved no testable code changed **or** the FULL backend suite ran and
passed). Requiring it therefore enforces LIGHT *and* FULL through one name.

- **Do NOT** require a matrix job name such as `Python (backend)` — matrix names are transient and can
  change, which strands branch protection.
- **Do NOT** require a manually dispatched run.
- Optionally also require **`Frontend`** if you want frontend lint/types/tests to gate merges too.

## Exact settings

On `main`, enable:

- Require a pull request before merging — **on**
- Require approvals — **1** (adjust to your governance)
- Dismiss stale pull request approvals when new commits are pushed — **on**
- Require status checks to pass before merging — **on**
  - Require branches to be up to date before merging (strict) — **on**
  - Required checks: **`Backend CI Gate`** (add `Frontend` if desired)
- Do not allow force pushes — **on** (block force pushes)
- Do not allow deletions — **on**
- Include administrators (apply rules to admins) — **on**, unless you deliberately keep a tightly
  governed emergency bypass

### Apply via the GitHub CLI

```bash
gh api -X PUT repos/jayw04/AI-TRADING-APP/branches/main/protection \
  --input - <<'JSON'
{
  "required_status_checks": { "strict": true, "checks": [ { "context": "Backend CI Gate" } ] },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "required_approving_review_count": 1
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
```

Verify it took:

```bash
gh api repos/jayw04/AI-TRADING-APP/branches/main/protection \
  --jq '{strict: .required_status_checks.strict,
         checks: [.required_status_checks.checks[].context],
         admins: .enforce_admins.enabled,
         force_push: .allow_force_pushes.enabled,
         deletions: .allow_deletions.enabled}'
```

Expected: `strict=true`, `checks=["Backend CI Gate"]`, `admins=true`, `force_push=false`,
`deletions=false`.

## Required verification (protection is not "done" until these pass)

1. **Red FULL blocks merge.** Open a scratch PR that adds a deliberately failing backend test (e.g.
   `def test_tmp(): assert False` under `apps/backend/tests/`). The classifier flags code → `backend-full`
   runs → fails → `Backend CI Gate` is red → confirm GitHub shows merge **blocked**. Close the PR.
2. **Docs-only passes without FULL.** Open a scratch PR that changes only a `.md`. The workflow runs,
   the classifier resolves `code=false`, `backend-full` is skipped, and `Backend CI Gate` reports
   **success** (N/A) — merge is allowed. Close the PR.
3. **A real code change runs FULL.** Any normal backend PR shows the `Backend FULL suite` job running
   and its result folded into the gate.

Record the outcome of step 1 (the merge-block screenshot or the blocked-merge status) as the evidence
that enforcement is live.

## Notes

- Draft PRs: `changes` is draft-guarded, so a draft's gate is not a real verdict. `ready_for_review` is
  in the PR trigger so the gate re-runs and produces its real verdict when a draft is marked ready.
- The classifier fails closed: a malformed changed-file list makes the classifier step exit non-zero,
  which fails the `changes` job, which makes `Backend CI Gate` fail closed.
