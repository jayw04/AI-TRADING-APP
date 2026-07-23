# CI branch protection — activating the `Python CI Gate` (repo-settings step)

**Status:** the workflow half of the light/full hardening landed in the CI PR (per-project FULL-on-PR
+ the always-run `Python CI Gate`). This runbook is the **second, separately-recorded step**: turning
on the GitHub branch-protection rule that makes the gate actually *block* merges. Until this is applied
**and verified**, a red `Python CI Gate` does not stop a merge — the automation is in place but not
enforced.

> **Do not apply this until the final stable aggregate check `Python CI Gate` exists on `main`** — i.e.
> after the CI hardening PR has merged and at least one run has reported the check. Requiring a check
> name that has never appeared on the branch strands every PR.
>
> The protection rule is **not** considered complete until a test PR proves GitHub blocks merging on a
> red `Python CI Gate`.

## Why a repo setting (and not the workflow)

A workflow can *run* checks; only branch protection can make a check *required* for merge. That toggle
lives in repository settings / the GitHub API, so it cannot ship inside `ci.yml`. The `#475/#477`
incident had two causes — FULL didn't run on the PR (fixed in the workflow) **and** no required check
blocked merge (fixed here).

## Which check to require

Require exactly one Python status check: **`Python CI Gate`**.

It is the single stable, always-run aggregate and it guards **all** Python projects (backend, mcp-server,
mcp-workbench, agent). It already fails closed unless the LIGHT/static checks passed **and** (no Python
project changed **or** the FULL suite ran and passed for every changed project). Requiring it enforces
LIGHT *and* FULL, for every project, through one name.

- **Do NOT** require a matrix job name such as `Python (backend)` or `Python FULL (backend)` — matrix
  names are transient and can change, which strands branch protection.
- **Do NOT** require a manually dispatched run.
- Optionally also require **`Frontend`** if you want frontend lint/types/tests to gate merges too.

## STEP 0 — snapshot the current protection first (do not skip)

The API call below is a full `PUT` and **replaces** the branch-protection object. Before changing
anything, capture the current rule so you can diff and restore, and so you consciously carry forward any
settings you are not intending to change:

```bash
gh api repos/jayw04/AI-TRADING-APP/branches/main/protection > main-protection-before.json
cat main-protection-before.json
```

Review `main-protection-before.json` for settings the payload below does **not** mention and that you
want to keep — a full `PUT` can drop or reset any of them, including:

- existing **required status check contexts** (the payload replaces the whole list — include every
  check you still want required, not just `Python CI Gate`)
- **push restrictions** (`restrictions`) — who may push
- **required signatures** (commit signing) — a separate endpoint; a `PUT` here does not preserve it
  unless you re-assert it
- **required linear history**, **required conversation resolution**, **lock branch**, bypass/allowances
- **required approving review count** and other review settings

If any of those are set and you want them kept, add them to the payload before applying. When unsure,
prefer editing the rule in the GitHub **UI** (Settings → Branches → Branch protection rules), which
changes only the fields you touch, over a full `PUT`.

## STEP 1 — apply (payload preserves what it re-asserts; verify against the snapshot)

Adjust the payload to include anything from the snapshot you must keep, then:

```bash
gh api -X PUT repos/jayw04/AI-TRADING-APP/branches/main/protection \
  --input - <<'JSON'
{
  "required_status_checks": { "strict": true, "checks": [ { "context": "Python CI Gate" } ] },
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

> Note the `restrictions: null` above **clears** any existing push restrictions. If the snapshot showed
> restrictions you want to keep, replace `null` with the corresponding object from
> `main-protection-before.json`.

Verify it took (and diff against the snapshot):

```bash
gh api repos/jayw04/AI-TRADING-APP/branches/main/protection \
  --jq '{strict: .required_status_checks.strict,
         checks: [.required_status_checks.checks[].context],
         admins: .enforce_admins.enabled,
         force_push: .allow_force_pushes.enabled,
         deletions: .allow_deletions.enabled}'
```

Expected: `strict=true`, `checks=["Python CI Gate"]` (plus any you deliberately kept), `admins=true`,
`force_push=false`, `deletions=false`.

## STEP 2 — required verification (protection is not "done" until these pass)

1. **Red FULL blocks merge (backend).** Open a scratch PR adding a deliberately failing backend test
   (`def test_tmp(): assert False` under `apps/backend/tests/`). The classifier flags backend →
   `Python FULL (backend)` runs → fails → `Python CI Gate` is red → confirm GitHub shows merge
   **blocked**. Close the PR.
2. **Red FULL blocks merge (each aux project).** Repeat with a deliberately failing test under
   `apps/mcp-server/`, then `apps/mcp-workbench/`, then `apps/agent/`. Each must turn `Python CI Gate`
   red and block merge. (This is the gap the per-project design closes.)
3. **Docs-only passes without FULL.** Open a scratch PR that changes only a `.md`. The workflow runs,
   the classifier resolves all `*_code=false`, `python-full` is skipped, and `Python CI Gate` reports
   **success** (N/A) — merge is allowed. Close the PR.
4. **A real code change runs FULL.** Any normal backend PR shows `Python FULL (backend)` running and its
   result folded into the gate.

Record the outcome of steps 1–2 (the blocked-merge status) as the evidence that enforcement is live.

## Notes

- Draft PRs: `changes` is draft-guarded, so a draft's gate is not a real verdict. `ready_for_review` is
  in the PR trigger so the gate re-runs and produces its real verdict when a draft is marked ready.
- The classifier fails closed: a malformed changed-file list makes the classifier step exit non-zero,
  which fails the `changes` job, which makes `Python CI Gate` fail closed.
- The changed-file list is passed to the classifier as data via an env var + a file, never interpolated
  into the shell, so hostile filenames cannot affect the run.
