---
name: github-ops
description: Use before any git commit, push, branch, PR, or merge; when editing .github/workflows/**, CI configuration, or anything that changes how GitHub Actions runs; when deciding whether a document belongs in the repository or in S3/local storage; when adding, moving, or referencing large datasets, backtest outputs, generated evidence, logs, screenshots, or DOCX/PDF/XLSX artifacts; when writing or consuming an S3 manifest under manifests/s3/; and when the user asks about GITHUB-OPS-001, Actions cost, CI tiers, batching, or the hybrid GitHub–S3 model. This skill is binding for all development effort in this repository.
---

# GITHUB-OPS-001 v1.2 — GitHub Development Process and Cost Optimization

**Status:** Approved for engineering use. **Binding for agents and humans.**

| Source | Path |
|---|---|
| Working copy (markdown) | `docs/methodology/GitHub_Development_Process_and_Cost_Optimization_Policy_v1.2.md` — **in Git** |
| Formal document | `docs/methodology/…_v1.2_Actions_and_S3.docx` — **not in Git**; controlled storage per §4 |
| Contributor summary | `CONTRIBUTING.md` |
| PR checklist | `.github/pull_request_template.md` |
| Cursor mirror | `.cursor/rules/github-dev-process-cost-policy.mdc` |

> **Reading a document.** All of `docs/**` is currently **in Git** — ADRs, runbooks, incidents,
> policies, design, implementation notes, and the generated evidence under
> `docs/implementation/evidence/**` and `docs/review/**`. Read them directly; there is no fetch
> step. The classification in §4 says where each *kind* of document belongs, and new bulk material
> should go to S3 — but no automated Git↔S3 documentation split is in force yet, so do not assume a
> missing path means "fetch it from S3." If a path under `docs/` is absent, it is absent.

**Why this exists:** July 2026 billing confirms GitHub **Actions compute** is the metered cost source — **8,073 Linux runner-minutes / $48.44**, of which **8,064 minutes (99.9%) came from AI-TRADING-APP**, all attributed to `.github/workflows/ci.yml`. Actions **storage** was ~$0.02. Gross usage rose roughly tenfold from a prior sub-$5 level; the included-use discount currently nets it to $0, which is exactly why it must be fixed before it exceeds the allowance. Target: **≥60% reduction in avoidable runs and runner minutes** (→ ~3,229 min / ~$19.38) with no increase in escaped defects and no weakening of production safeguards.

**The one-line rule:** GitHub is the system of *change and review*; S3 is the system of *data, generated artifacts, and governed evidence*. Optimize for completed reviewable increments — not repository event count.

---

## 1. Before you push — the local gate

Never push to trigger CI as a way of finding out whether something works. Run the checks locally first.

```bash
# Backend (from apps/backend/)
python -m ruff check .
python -m ruff format --check .
python -m mypy app
python -m pytest tests/<affected-area> -q          # focused, not the full suite

# Frontend (from apps/frontend/)
pnpm lint && pnpm tsc --noEmit && pnpm test

# Invariant checks (only those the change can plausibly break) — full set:
#   ls apps/backend/scripts/check_*.sh apps/backend/scripts/check_*.py
bash apps/backend/scripts/check_strategy_isolation.sh
bash apps/backend/scripts/check_no_llm_in_order_path.sh
bash apps/backend/scripts/check_loss_control_invariants.sh      # risk / order path
bash apps/backend/scripts/check_settlement_barrier.sh           # ADR 0043 harnesses
bash apps/backend/scripts/check_aws_sdk_isolation.sh            # app/validation/aws/ only
python scripts/check_dependency_locks.py                        # dependency pins
```

Coverage gates (`check_risk_coverage.py`, `check_p2_coverage.py`, `check_p3_coverage.py`) run locally when the change touches those modules — do not discover a coverage failure in CI.

**Push only at a meaningful integration point:** review-ready, blocked and needing collaboration, or genuinely requiring remote-only validation.

---

## 2. Batching defaults

| Activity | Default | Exception | Record |
|---|---|---|---|
| Remote pushes | **1–3 per work item** | Urgent collaboration, remote-only test failure, conflict resolution | Explain in PR when materially exceeded |
| Pull requests | **One per coherent deliverable** | Independent risk domains, urgent hotfix | Link issue + acceptance criteria |
| Doc publication | **Weekly or governed milestone** | ADR, security finding, release instruction, production incident | Owner sets status + effective date |
| Full CI | Review-ready integration + before merge | High-risk infra/schema/security/release | Tier selected by changed paths |
| PR revisions | **Batch review responses into one push** | Critical blocker for other reviewers | Prefer one consolidated push |

Local commits for safety are fine and encouraged; **do not push every checkpoint**. Squash noisy checkpoints before the first remote push where appropriate. **Never open a PR solely to back up unfinished work** — use local backup or approved encrypted storage.

Workflow: **Plan → Build locally → Validate locally → Consolidate → Push review-ready → Risk-tiered CI → Merge/release.**

---

## 3. What your paths actually trigger (as implemented in `.github/workflows/ci.yml`)

Tier 0–3 (policy §4) is the **risk vocabulary**. The workflow does not emit a `ci_tier`; it implements
a **per-project LIGHT/FULL split**. Know which side your change lands on *before* you push.

| Stage | What runs | When |
|---|---|---|
| `Detect changes` | `dorny/paths-filter` lists changed files; `apps/backend/scripts/ci_classify_changes.py` decides FULL per project | Every non-draft PR. **Draft PRs run zero jobs** |
| **LIGHT** — `Python (<project>)` | Ruff, mypy, fast invariant bash checks | Every PR. Backend always; the 3 aux projects only when their folder changed |
| **FULL** — `Python FULL (<project>)` | pytest + coverage gates | Only for projects the classifier flags — plus unconditionally on push-to-main, nightly, and dispatch |
| `Python CI Gate` | Aggregate; `always()`; **fails closed** | Always. The single **required** status check on `main` (branch protection) |
| `Frontend`, `Build image (<service>)` | Vitest/lint; Docker builds | Frontend paths; images only on Dockerfile/manifest change, and only after merge to main |

**Which paths flag backend FULL:** `apps/backend/**`, **`scripts/**`**, **`deploy/**`**, `tests/**`,
`**/alembic.ini`. **A test file is code.** `GLOBAL` paths — `.github/workflows/ci.yml` and the *root*
dependency manifests — flag **every** project. Docs-only and frontend-only PRs stay LIGHT and the
gate resolves FULL to a cheap N/A pass.

**Non-negotiable:** full validation stays mandatory for database migrations, risk-engine changes,
order-path changes, production deployment, and release candidates — **regardless of cost pressure**.
No cost reduction may weaken security, production safeguards, migration controls, or independently
verifiable release evidence (Governing Principle 6).

Note the multiplier: editing `.github/workflows/ci.yml` flags the FULL suite for **all four** Python
projects *and* rebuilds every Docker image. Batch workflow edits ruthlessly.

**When changing CI configuration, preserve:** path filters, `concurrency` with `cancel-in-progress`, dependency/build caching with lockfile-keyed invalidation, job timeouts, `permissions: contents: read`, short artifact retention (≤7 days for routine logs), and explicit ownership/review dates on every scheduled workflow. Removing any of these re-introduces the waste this policy exists to remove.

### Dependency reproducibility (GITHUB-OPS-001 action item, 2026-07-29)

**Direct runtime and test dependencies used by CI must resolve reproducibly** — a committed
lockfile, a constraints file, or a verified exact pin. **Open-ended lower bounds alone are not
sufficient for an independently repeatable required check.**

Established by incident: `mcp>=1.0` in `apps/mcp-server` and `apps/mcp-workbench` let a fresh CI
install resolve `mcp 2.0.0`, which moved/removed `mcp.server.fastmcp`. Every Python FULL job for
both projects failed at collection, `Python CI Gate` failed closed, and **main was red for ~21
hours with no PR able to merge** — a whole-repository outage from one unbounded lower bound.
Fixed in #539 by pinning `mcp==1.28.1`, the version read out of the last green run's CI log.

Practice:

- A required check that can change behaviour because an upstream package published is not a
  *required check* — it is a coin flip. Pin it.
- Determine the good version from **evidence** (last green run's log, lockfile, resolved-environment
  artifact) — never from release dates.
- Prefer an exact pin for incident recovery; an upper bound (`>=1.0,<2`) is acceptable only when
  compatibility has been tested across the whole permitted range.
- Add a **dependency-contract test** asserting the specific API the code imports and that the
  resolved version equals the declared pin (see `apps/*/tests/test_mcp_dependency_contract.py`).
  It converts a future recurrence into an explicit dependency-layer failure instead of an opaque
  collection error somewhere unrelated.
- Keep the declaration and any lock/resolution artifact synchronized; when several projects share a
  dependency, pin them identically unless there is a documented reason not to.
- ⚠ **Do not "just re-run" a failing workflow when the dependency is unpinned.** The re-run resolves
  the same broken version and burns runner minutes without changing the outcome. Re-running *is*
  legitimate when the hypothesis is genuine flakiness — distinguish the two before spending.
- Open item: the pin value is currently duplicated per `pyproject.toml` and per contract test. That
  is acceptable while the test explicitly checks synchronization, but a shared constraints file or
  lockfile should become the single resolution authority.

**Require approval before:** enabling larger runners, extending artifact retention, adding a new scheduled workflow, or adding a repository-wide full-suite trigger. Self-hosted runners require a security and total-cost review first — they are not automatically cheaper.

### 3.1 Where the minutes actually go — measured, July 2026

Reconstructed from the GitHub API (624 runs, 3,820 jobs, per-job durations billed rounded up):
**8,007 min computed vs 8,073 billed — 99% agreement.** Reproduce with `scripts/ci_usage_report.py`.

| Job | Billable min | % | Runs | Avg |
|---|---|---|---|---|
| `Python (backend)` (LIGHT) | 3,473 | **43.4%** | 582 | 6.0 |
| `Python FULL (backend)` | 2,239 | **28.0%** | 126 | 17.8 |
| `Detect changes` | 604 | 7.5% | 620 | 1.0 |
| `Frontend` | 342 | 4.3% | 620 | 0.6 |
| 3 aux Python projects (LIGHT) | 710 | 8.8% | 236 ea | 1.0 |
| All Docker image builds | 255 | 3.2% | — | — |

Step-level, inside those two jobs:

- **FULL backend is 95.7% one step** — `Pytest (full, with coverage)` at **1,108 s (18.5 min)**.
- **LIGHT backend is 54.2% one step** — `ADR 0043 loss-control tests + branch-coverage gate` at
  **96 s**, a pytest run embedded in the nominally-light job, executing on all 582 LIGHT runs
  (**933 min = 11.7% of the entire bill**). `Install backend` is only 40 s; pip caching already works.

⚠ **Total cost is not avoidable cost.** A 120-PR replay of the ADR-0043 gate predicate showed
**80.8% of pull requests touch backend paths** — legitimate required execution. The avoidable
portion of that 933 min is **~178 min/month (2.2%)**, shipped in PR #538. Apply the same
discipline to every lever below: measure the avoidable share before quoting a saving.

**The backend pytest suite is ~41% of the bill in its two forms.** Three things follow:

1. **Sharding does not help.** GitHub bills the *sum* of concurrent job time. Splitting an 18.5-min
   suite into 4 shards cuts wall-clock, not billable minutes. To cut minutes you must run the suite
   **less often** or make it **genuinely faster**.
2. **Checkout weight is irrelevant.** `actions/checkout@v4` measures **1.5 s**. Document migration
   cannot be an Actions-cost remedy — see §4.
3. **Trigger-level dedup is already done.** Measured: **zero** branch-days with both a push and a
   `pull_request` run; cancelled runs are only 8.1% of minutes (concurrency works); draft PRs run
   zero jobs. Do not re-propose these — verify before prescribing.

Levers and their governed status (GITHUB-OPS-001 phase 1):

| # | Lever | Status | Saving |
|---|---|---|---|
| 1 | Path-gate the ADR-0043 step | **shipped, PR #538** | ~178 min measured |
| 2 | LIGHT/FULL deduplication + failure ordering | next | ≤330 min, **pending overlap proof** |
| 3 | Shallow classifier checkout | after 2 | ~307 min, **pending parity proof** |
| 4 | push→main final-integration model | **blocked** — see approval bar below | ~4,222 min in scope, mostly NOT safely removable yet |

🏁 **Wave 1 complete (2026-07-29).** Four PRs merged (#538 #539 #540 #543): **~179 min/month measured recurring saving (~2.2%)** plus deterministic hash-verified dependency resolution. Three optimizations **rejected/deferred by measurement** — LIGHT/FULL dedup (would delete required evidence), fail-fast (~34 min ceiling, real push-cycle cost), env caching (unsound cache key pre-locking). **The 50–60% target is OPEN, not failed** — it depends on the exact-merge-result design.

⚠ **Do not count outage repairs or locking as recurring cost savings.** Their value is reliability and reproducibility. Only #538 is a measured recurring saving.

⛔ **Exact-merge-result approval bar** — before reducing push-to-main validation, prove ALL of: the exact **merge result** (not the PR head) was fully tested · the tested SHA **is** the SHA admitted to the protected branch · base movement invalidates stale approval · required checks **always** report · merge-queue/merge-commit/squash/rebase each explicitly handled · direct push, emergency merge and bot paths cannot bypass equivalent validation · post-merge deployment checks stay separate from redundant retesting. Until then the push-to-main FULL run is **expensive but justified**.

**Next, in order:** fix the flaky `BacktestRunModal.test.tsx:183` first (it contaminates the measurements everything else is judged by) → PR 3 classifier checkout → post-lock caching re-benchmark → exact-merge-result design. MCP 2.x migration stays outside the cost program.

**Phase-1 ceiling is ~815 min (~10%), an upper working estimate — not a committed saving.** The
≥60% objective **cannot** be claimed from levers 1–3. It requires lever 4, which may not proceed
until the system proves the exact merge result already passed the required full suite (merge queue,
tested merge commit, or equivalent immutable-SHA control). Cost reduction may not weaken the
protection against a failing backend suite merging under a green LIGHT result.

For lever 2, build an overlap inventory first — classify each LIGHT step as *identically repeated by
FULL* / *prerequisite FULL consumes* / *fast independent gate* / *semantically different despite a
similar command* / *embedded pytest or coverage work*. Do not assume the full 4.1% is removable.
Fail-fast belongs in lever 2 where the dependency graph is visible: stop jobs whose results are no
longer actionable, but keep independent checks whose combined results prevent another push cycle.

---

## 4. Documentation — where a document belongs (GITHUB-OPS-001 §6.1)

⚠ **Document storage is NOT the Actions cost remedy** — see §3.1. `actions/checkout` measures 1.5 s
and Actions *storage* was ~$0.02 against $48.44 of *compute*. Migrating documents is justified by a
cleaner repository and controlled archival storage, never by cost.

| Artifact | Home | Rule |
|---|---|---|
| Source, tests, IaC, migrations, small config | **GitHub** | With the related code change; PR review + CI |
| **Governing docs** — `docs/adr/**`, `docs/runbook/**`, `docs/incidents/**`, `docs/methodology/*.md`, `docs/design/*.md`, `docs/implementation/*.md` | **GitHub** | Edit + commit normally. Must be reviewable in a diff and readable during an incident with no AWS |
| **Bulk** — generated evidence, research archives, `.docx`/`.xlsx`/`.pdf`/`.gz`/`.whl`/images | **S3** | Manifest in Git; pinned Version ID + SHA-256 |
| Datasets, model files, DB exports, large binaries | **S3** | Manifest in Git; pinned Version ID + SHA-256 |
| Backtest outputs, logs, screenshots, CI evidence | **S3** or short-lived CI artifacts | Reference by manifest; **no bulky duplicates in Git** |
| `CLAUDE.md`, `CONTRIBUTING.md`, `.claude/skills/**` | **GitHub** | Tooling/agent configuration, read at session start with no network |
| Small deterministic test fixtures | **GitHub** | Minimal, non-sensitive, reviewable |

**Classifying a NEW document:** governing (someone must review it, or read it under pressure) → Git.
Generated, archival, or bulky → S3 + manifest.

> **Status (2026-07-29).** This is the *classification rule*, not yet an enforced split: all of
> `docs/**` is currently tracked in Git, including ~150 files of generated evidence and research
> archives that this table assigns to S3. Reconciling that — the `.gitignore` rules, the fetch and
> publish tooling, the per-file manifests, and the `git rm --cached` — is a separate governed change
> and needs an ADR. **Until it lands: do not add new bulk material to Git, and do not assume a
> missing `docs/` path can be fetched from S3.**

**Agent behavior:** do not create markdown or documentation the user did not request. Status
summaries, session recaps, and "here's what I did" documents are exactly the review noise this policy
removes — put them in the response, not in a file.

---

## 5. S3 artifacts

> ⚠ **No S3 manifest tooling is merged yet.** `manifests/s3/`, `scripts/s3_fetch_verify.py`,
> `scripts/s3_publish_manifest.py`, `scripts/check_s3_manifests.py`, the `S3 manifest gate` CI job and
> `docs/runbook/s3-artifacts.md` are **designed but not in the repository** — the GITHUB-OPS-001
> Phase 3 scaffolding exists only in a local working tree. Verify with
> `ls manifests/s3 2>/dev/null` before citing any of it. Until it lands, **do not hand-roll a
> competing scheme**: if a change needs a governed S3 object, raise it rather than inventing an
> ad-hoc manifest format that the real gate will later reject.

The rules below are binding on any S3 use, tooling or not:

- Every governed object needs a machine-readable manifest carrying **bucket, key, S3 Version ID, SHA-256, logical artifact ID, schema/format version, creation timestamp, producing job/run, owner, retention class, sensitivity classification**.
- **No unpinned `latest`.** Resolve a fixed Version ID or immutable release prefix and verify the checksum before use.
- **Fail closed** on missing object, checksum mismatch, access denied, or incompatible schema version.
- Routine PR CI uses **small Git fixtures**, never a network fetch. Full-dataset downloads belong to full-suite / nightly / release-candidate / governed research runs only.
- Where several files form one evidence package, publish a **package manifest** whose own checksum is recorded in Git.
- Buckets: versioning + SSE on; block public access; least-privilege IAM prefix policies; GitHub Actions authenticates via **OIDC short-lived credentials, never long-lived keys**. Object Lock only for approved immutable evidence classes — it materially restricts deletion and administration, so never enable it casually on a working bucket.
- **Never** commit or upload secrets, private keys, credentials, or regulated data — to Git or to an unapproved S3 location.

**Migration guardrails:** duplicate → validate → switch consumers → *only then* remove the Git copy. Verify developer access, CI access, disaster recovery, rollback to a previous object version, and independent reproduction of one representative run first. Record before/after Actions minutes, run counts, median duration, cache hit rate, downloaded bytes, artifact storage, and AWS transfer cost — a migration is not cost-effective until the billing report shows it. **Do not rewrite Git history** for large-file migration without separate approval.

⚠ **2026-07-27 incident:** a full `cloudformation deploy` of `workbench-paper-stack.yaml` for an IAM-only tweak **replaced the live EC2 instance and destroyed the root volume**. Never run a full-stack deploy during RTH, and **always create a change set and check for `Replacement: True` first** — for an IAM-only edit, narrow the operation to the policy rather than deploying the template.

---

## 6. Mandatory exceptions — immediate GitHub activity is correct

Batching yields immediately for:

- Production incident response, security remediation, leaked-secret response, emergency rollback
- Database migration or infrastructure change requiring independent review
- Architecture/governance record that immediately constrains implementation
- Collaboration blocker that cannot be resolved locally
- Release candidate, merge to a protected branch, deployment gate
- Legal, regulatory, contractual, or audit requirement

Exceptions are fast, not bureaucratic — **record the reason in the PR or issue** so it can be distinguished from avoidable process noise.

---

## 7. Review-ready PR checklist

Use `.github/pull_request_template.md`. Before marking ready:

- [ ] Work item is coherent; acceptance criteria stated
- [ ] Local lint, format, focused unit tests, relevant integration tests pass
- [ ] Temporary files, exploratory output, draft-only docs excluded
- [ ] One primary deliverable, or one tightly related change set
- [ ] Correct CI tier selected automatically, or explicitly justified
- [ ] Durable documentation updated; working notes stay in the external workspace
- [ ] Security, migration, infrastructure, and production risks called out
- [ ] Review feedback consolidated before the next push
- [ ] No secrets, private keys, credentials, regulated data, or unnecessary large binaries
- [ ] Every S3 dependency pinned by Version ID / immutable prefix and checksum-verified
- [ ] Manifest included or updated for any governed dataset, evidence package, model, or generated artifact
- [ ] Workflow does not download a full S3 dataset where a fixture or checksum-keyed cache suffices
- [ ] Artifact upload and retention limited to what review, release, or governance requires
- [ ] No duplicate Actions triggers, unnecessary matrix jobs, or unowned scheduled workflow

**Walk-away discipline still applies on top of this** (`CLAUDE.md`): ≥1 hour between ready-for-review and merge; ≥2 hours for risk-gate, live-path, and production-hardening changes. Cost policy shortens CI, never the walk-away window.

### 7.1 Merge readiness — which green actually authorises a merge

**Learned the hard way merging #650, 2026-08-20.** A passing test job is not merge readiness. Merge readiness is determined by the repository's **required status context(s)**, and nothing else.

```text
Python FULL (backend) PASS                       !=  merge-ready
required context PASS on the exact head SHA
  + base up to date + walk-away elapsed          ==  merge-ready
```

On `main` today the required context is exactly one job — **`Python CI Gate`** — and **it runs last**, after the ~25-minute `Python FULL (backend)` suite. When `Python FULL` reported SUCCESS the PR was still `mergeStateStatus = BLOCKED`, because the Gate had not started yet. Waiting on the wrong job costs a full suite cycle to rediscover.

```bash
# Confirm the required contexts rather than assuming:
gh api repos/<owner>/<repo>/branches/main/protection \
  --jq '{strict: .required_status_checks.strict, contexts: .required_status_checks.contexts}'

# The only two signals that matter before merging:
gh pr view <N>   --json headRefOid,mergeable,mergeStateStatus
gh pr checks <N> --json name,state
```

Merge only when `mergeStateStatus` is **`CLEAN`**, and pass `--match-head-commit <sha>` so the merge aborts if the head moved underneath you.

### 7.2 `strict: true` — merging one PR pushes every other PR BEHIND

Branch protection on `main` sets **`strict: true`** (branches must be up to date before merging). Merging any PR therefore flips every other open PR to `BEHIND` and forces a re-run.

**Do this once, not repeatedly:**

```bash
git fetch origin
git merge origin/main --no-edit      # locally, in the PR's worktree
# re-run the local gate, then:
git push                             # ONE push -> ONE CI cycle
```

⛔ Do **not** use push-then-"Update branch", and do not restart CI repeatedly — each costs a full cycle. Let the required CI run once on the resulting exact head, then merge that head.

⚠ This also means **merge order matters when PRs are related**: merge the cheap-CI PR last, or accept that the expensive one re-runs. Sequence deliberately rather than discovering it.

---

## 8. Agent-specific behavior in this repository

1. **Do not commit or push unless the user explicitly asks.** This is both a standing user rule and the policy's batching default.
2. **Prefer fewer, larger commits.** When the user does ask for a commit, one coherent commit beats a sequence of tiny ones.
3. **Do not propose next steps that multiply CI runs** — no separate PR per file, no docs-only follow-up PRs, no "let me push and see if CI passes."
   - **Wait on the required context, not on a test job** (§7.1), and when `strict` protection pushes a PR BEHIND, merge `main` in locally and push **once** (§7.2). Both mistakes cost a full suite cycle each.
4. **Do not create documentation files the user did not ask for.**
5. **Classify before you act.** Before editing, know the tier the touched paths land in; say so if it is Tier 3.
6. **Never relax an architectural or CI invariant to save cost.** If cost pressure and an invariant conflict, surface it — the answer is an ADR, not a workaround.
7. **When batching genuinely conflicts with the user's instruction** (they ask for an immediate push of unfinished work), do it and note the policy deviation in one line. The user's explicit instruction wins; silence about the deviation does not.

---

## 9. Known gap

`docs/methodology/GITHUB_OPS_001_Phase2_Org_Settings_Checklist.md` is referenced by `CONTRIBUTING.md` and by §11 of the policy working copy, but **does not exist in the repository**. Org budgets, alerts (50/75/90/100% thresholds), and branch protection are manual owner steps not captured in YAML. Do not silently create this file — flag it to the owner.
