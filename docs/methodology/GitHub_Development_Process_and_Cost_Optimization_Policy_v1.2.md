# GitHub Development Process and Cost Optimization Policy

| Field | Value |
|-------|-------|
| **Document ID** | GITHUB-OPS-001 |
| **Version** | 1.2 |
| **Status** | Approved for engineering use (Actions cost source confirmed; S3 migration and CI controls refined) |
| **Owner** | Engineering / Architecture |
| **Formal source** | `docs/methodology/GitHub_Development_Process_and_Cost_Optimization_Policy_v1.2_Actions_and_S3.docx` |
| **Review cycle** | Monthly for the first 90 days; quarterly thereafter |

**Purpose:** Accelerate delivery and reduce GitHub Actions consumption by eliminating unnecessary workflow runs, right-sizing CI, and moving large datasets and generated artifacts to controlled Amazon S3 storage where that reduces checkout, transfer, artifact-retention, and full-data test overhead.

**Primary target:** Reduce avoidable GitHub Actions consumption by at least **60% within 30 days** while preserving code quality, traceability, reproducibility, and release safety.

---

## 1. Executive summary

The current process creates too many repository events for the value delivered: frequent small commits, premature PRs, repeated full CI runs, and routine documentation-only changes trigger unnecessary GitHub Actions work. A single CI cycle may take 20–30 minutes. July 2026 billing confirms metered usage is attributable to **GitHub Actions** (not Copilot or repo storage alone); **AI-TRADING-APP** accounts for nearly all repository-level usage.

This policy introduces a lean, risk-based model:

- Develop locally in **coherent batches**
- Run **fast local checks** before pushing
- Open **fewer, better-prepared PRs**
- Reserve **full CI** for meaningful integration points
- Use **Amazon S3** for large datasets and generated artifacts (paired with workflow changes — migration alone is not a cost cure)

GitHub remains authoritative for production code, release-ready configuration, architecture decisions, manifests, and **approved** documentation.

---

## 2. Governing principles

1. Optimize for **completed, reviewable increments** — not repository event count.
2. Perform **cheap validation early and locally**; reserve expensive validation for integration and release risk.
3. Keep GitHub **authoritative but not noisy** — only durable, review-worthy artifacts belong in the main repository.
4. **One PR per coherent outcome** — no checkpoint PRs for unfinished work.
5. Document decisions, interfaces, controls, and release evidence; minimize transient narrative and duplicate status documents.
6. **No cost reduction** may weaken security, production safeguards, database migration controls, or independently verifiable release evidence.
7. **Right system for the right artifact:** GitHub governs change and review; S3 governs durable data, generated evidence, and archives.
8. Treat S3 migration and Actions optimization as **one coordinated change**.
9. Measure savings by Actions minutes, workflow runs, job duration, artifact storage, and data-transfer behavior — **not repository size alone**.

---

## 3. Target operating model

### 3.1 Work in coherent local batches

1. Create a local branch for a defined work item with explicit acceptance criteria.
2. Develop, test, and refine locally until the change is internally coherent and reviewable.
3. Use local commits for safety; **do not push every checkpoint**. Squash before first remote push when appropriate.
4. Push at a **meaningful integration point**: review-ready, blocked and needing collaboration, or remote-only validation.
5. **Do not open a PR solely to back up unfinished work** — use local backup or approved encrypted storage.

| Activity | Default | Exception | Record |
|----------|---------|-----------|--------|
| Remote pushes | 1–3 per work item | Urgent collaboration, remote-only test failure, conflict resolution | Explain in PR when exceeded |
| Pull requests | One per coherent deliverable | Independent risk domains or urgent hotfix | Link issue + acceptance criteria |
| Documentation publication | Weekly or governed milestone | ADR, security finding, release instruction, production incident | Owner sets status + effective date |
| Full CI | Review-ready integration + before merge | High-risk infra, schema, security, release | CI tier by changed paths |
| PR revisions | Batch review responses before re-push | Critical blocker for other reviewers | Prefer one consolidated push |

### 3.2 Adapted agile workflow

**Plan → Build locally → Validate locally → Consolidate → Push review-ready → Risk-tiered CI → Merge/release**

Local validation before push: formatting, linting, focused unit tests, type checks, affected integration tests.

---

## 4. Risk-based CI/CD (Tier 0–3)

CI must classify changed paths and run the **least expensive suite** that still provides adequate evidence.

| Tier | Typical changes | Checks | Target duration | Full CI? |
|------|-----------------|--------|-----------------|----------|
| **0 — No CI** | Markdown, images, approved docs, non-runtime notes | Link/format only or skip when safe | 0–3 min | No |
| **1 — Light** | Isolated app code, narrow-impact tests/scripts | Lint, type check, focused unit tests, cache check | 3–8 min | No (unless failure or reviewer request) |
| **2 — Standard** | Cross-module backend/frontend, APIs, service behavior | Affected unit/integration tests, build, security scan | 8–15 min | Selected suite |
| **3 — Full** | Migrations, infra, auth, deployment, shared runtime, release candidate | Complete suite, coverage, image build, migration verification | 20–30 min | **Yes** |

**Required CI engineering (implementation):**

- Path filters so docs-only changes skip backend/frontend/image/deploy jobs
- Cancel superseded runs on new PR commits (concurrency groups)
- Cache dependencies/build layers; invalidate on lockfile/build-input changes
- Merge queue or required final validation instead of full suite on every draft push
- Short artifact retention for routine logs; governed evidence in S3
- Explicit ownership and review dates for scheduled workflows

**Trading Workbench non-negotiable:** Tier 3 (full CI) remains mandatory for database migrations, risk-engine changes, order-path changes, production deployment, and release candidates — regardless of cost tiering elsewhere.

---

## 5. Hybrid GitHub–S3 model

**Operating rule:** GitHub = system of **change and review**; S3 = system of **data, generated artifacts, and governed evidence**.

| Artifact | Authoritative system | Publication rule |
|----------|---------------------|------------------|
| Source code, tests, IaC, migrations, small config | GitHub | With related code change; PR review + CI |
| ADRs, approved design specs, runbooks | GitHub (+ optional S3 archive) | Promptly after approval |
| Raw/processed datasets, large binaries, model files | S3 | Manifest in GitHub; pinned version + checksum |
| Backtest outputs, logs, screenshots, generated DOCX/PDF/XLSX | S3 or short-lived CI artifacts | Reference by manifest; no bulky duplicates in Git |
| Draft notes, meeting records, exploratory analysis | Local / S3 working prefix | Weekly or milestone; not every edit |
| Small deterministic test fixtures | GitHub | Minimal, non-sensitive, reviewable |

### 5.1 S3 object identity (mandatory for governed objects)

Every governed S3 object must be referenced by a **machine-readable manifest** in the related GitHub change, release, or research decision. Minimum fields:

- bucket, object key, S3 Version ID, SHA-256 checksum
- logical dataset/artifact ID, schema/format version
- creation timestamp, producing job/run, owner, retention class, sensitivity classification

**No unpinned “latest”** in production or research workflows — resolve fixed version or immutable release prefix and verify checksum before use.

### 5.2 S3 security baseline

- Versioning + SSE; CMK when policy requires
- IAM roles + least-privilege prefix policies; GitHub Actions via **OIDC/federated short-lived credentials** (no long-lived keys in repo)
- Lifecycle classes: working, operational, governed, archive
- Block public access; audit logging; **never** store secrets or credentials in Git or unapproved S3

### 5.3 Developer and CI access pattern

- Small deterministic fixtures in Git for routine dev and Tier 1 CI
- Standard **fetch-and-verify** script: download pinned version, validate checksum, cache locally
- CI **fail closed** on missing object, checksum mismatch, access denied, or schema incompatibility
- Full dataset downloads only for Tier 3, nightly, release candidate, or governed research runs

### 5.4 Migration guardrails

Do not remove GitHub artifacts until S3 copy, manifest, access path, retention, and consuming workflows are verified. Staged migration: duplicate → validate → switch consumers → remove Git duplicate after acceptance. Record before/after Actions minutes, download bytes, and artifact storage.

---

## 6. Documentation publication

Working documents (draft research, meeting notes, status reports, screenshots, temporary evidence, large generated documents) stay in **approved local drive or controlled S3 prefix**.

Publish to GitHub:

- **Weekly** (consolidated commit/PR), or
- **Immediately** when material becomes governing: ADR, security finding, release instruction, production incident, approved design

Do not commit exploratory output, draft-only docs, or large binaries that belong in S3.

---

## 7. Mandatory exceptions (immediate GitHub activity OK)

- Production incident, security remediation, leaked-secret response, emergency rollback
- Database migration or infrastructure change requiring independent review
- Architecture/governance record that immediately constrains implementation
- Collaboration blocker that cannot be resolved locally
- Release candidate, merge to protected branch, deployment gate
- Legal/regulatory/audit requirement

Record the exception reason in the PR or issue.

---

## 8. Roles (summary)

| Role | Accountability |
|------|----------------|
| Developers | Batch work, local checks, avoid unnecessary pushes, correct doc classification, review-ready PRs |
| Technical leads | Risk tiers, exceptions, critical evidence governance |
| Repo admins | Path filters, concurrency, budgets, branch protection, retention |
| Reviewers | Consolidate feedback; request full CI only when risk justifies |
| Document owners | Controlled working copies; publish approved versions on schedule |
| Data/artifact custodians | S3 naming, manifests, versioning, retention, checksum verification |

---

## 9. Review-ready PR checklist

See `.github/pull_request_template.md` (mirrors Section 11 of the formal policy).

---

## 10. Performance targets (30 / 90 days)

| Metric | 30-day target | 90-day target |
|--------|---------------|---------------|
| CI-triggering pushes per work item | ↓ ≥40% | ↓ ≥60% |
| Documentation-only commits | ↓ ≥60% | Weekly/milestone cadence |
| Median PR validation time | ≤15 min (standard) | ≤10–12 min |
| Full CI executions | Tier 3 + final integration only | ↓ ≥50% avoidable runs |
| Actions gross usage (July 2026 ~$43.68 baseline) | ↓ ≥40%; stop growth | ↓ ≥60% controllable cost |
| Full-data downloads in routine PR CI | ↓ ≥70% | Eliminate except approved cases |
| Routine Actions artifact retention | ≤7 days unless justified | ≤3–7 days; governed evidence in S3 |
| Escaped defects | No increase | No meaningful increase |

---

## 11. Implementation phases

| Phase | Timing | Focus | Status |
|-------|--------|-------|--------|
| 1 — Baseline | Week 1 | Actions billing export; budgets/alerts; cancel superseded runs; batching rules | Billing measured (`scripts/ci_usage_report.py`); `concurrency` + `cancel-in-progress` in repo. Org budgets/alerts still manual owner steps |
| 2 — CI tiering | Weeks 2–3 | Path classifier; Tier 0–3 workflows; concurrency; caching; artifact retention | **In repo** — `.github/workflows/ci.yml`: `Detect changes` + unit-tested classifier `apps/backend/scripts/ci_classify_changes.py`, per-project LIGHT/FULL, `Python CI Gate` required check, concurrency cancel, dependency caching. ⚠ **Not** implemented: an explicit `ci_tier` output, a `CI tier summary` job, and `retention-days` on artifacts. Org budgets/branch-protection checklist (`GITHUB_OPS_001_Phase2_Org_Settings_Checklist.md`) is **unwritten** |
| 3 — S3 migration | Weeks 2–4 | Prefixes, manifests, fetch-and-cache tooling; migrate large datasets | ⛔ **Not in the repository.** Scaffolding was drafted 2026-07-27 in a local working tree (`manifests/s3/`, `scripts/s3_fetch_verify.py`, `s3_publish_manifest.py`, `check_s3_manifests.py`, `docs/runbook/s3-artifacts.md`) but **was never merged** — none of those paths exist on `main`, and there is no `S3 manifest gate` CI job. §5 remains the binding rule; the tooling to enforce it is outstanding |
| 4 — Process enforcement | Weeks 3–5 | CONTRIBUTING, PR template, branch policy, reviewer guidance | PR template + CONTRIBUTING + `github-ops` skill in repo. Branch protection **active** on `main` (required check `Python CI Gate`, strict, enforce_admins) |
| 5 — Optimize | Days 30–90 | Monthly metrics review; tune checks without weakening quality gates | Wave 1 measured: ~179 min/month recurring saving; three further optimizations rejected by measurement. The ≥60% target is **open**, and depends on the exact-merge-result control |

### Phase 2 — how the tiers actually map onto the workflow

The Tier 0–3 table in §4 is the **risk vocabulary**. `.github/workflows/ci.yml` implements it as a
per-project LIGHT/FULL split rather than an explicit tier number:

| Risk tier | In practice | Jobs |
|------|-----------|------|
| 0 | Docs-only PR — classifier resolves FULL to N/A | LIGHT only; `Python CI Gate` passes cheaply. (Push-to-main additionally has `paths-ignore` for `**/*.md` and `docs/**`) |
| 1 | Aux-project or frontend-only change | `Python (<project>)` LIGHT — ruff, mypy, fast invariant checks — and/or `Frontend` |
| 2 | A Python project's testable paths changed | LIGHT + that project's `Python FULL (<project>)` — pytest + coverage |
| 3 | `.github/workflows/ci.yml` or root dependency manifests; every push to main, nightly, dispatch | FULL for **all four** projects + coverage gates + Docker image builds |

`scripts/**`, `deploy/**`, `tests/**` and `**/alembic.ini` are classified as **backend** paths, so a
repo-root script change runs the full backend suite. A test file counts as code. Draft PRs run zero
jobs. `Python CI Gate` is the single required status check and fails closed.

Additional workflow controls in repo: job timeouts, workflow-level `permissions: contents: read`,
an owned nightly schedule comment, and dependency caching.

## Phase 3 S3 scaffolding — ⛔ NOT IN THE REPOSITORY

The pieces below were drafted 2026-07-27 in a local working tree and **never merged**. None of these
paths exist on `main`; there is no `S3 manifest gate` job. This table records the intended design so
the eventual PR does not reinvent it — **do not cite any row as an available tool**, and verify with
`ls manifests/s3` before relying on it.

| Piece | Intended location | Status |
|-------|----------|---|
| Prefix layout + index | `manifests/s3/index.json` | drafted, unmerged |
| Manifest schema | `manifests/s3/schema/s3_object_manifest.v1.json` | drafted, unmerged |
| Fetch + verify (fail-closed) | `scripts/s3_fetch_verify.py` | drafted, unmerged |
| Publish helper | `scripts/s3_publish_manifest.py` | drafted, unmerged |
| CI / local gate | `scripts/check_s3_manifests.py` + workflow job | drafted, unmerged |
| Runbook | `docs/runbook/s3-artifacts.md` | drafted, unmerged |

Design intent: network S3 fetch gated behind `WORKBENCH_S3_ALLOW_FETCH=1`; unpinned `latest` Version
IDs rejected. Until it lands, §5.1's manifest requirement is enforced by review, not by CI.

**Incident (2026-07-27):** a full `cloudformation deploy` of `workbench-paper-stack.yaml` for an IAM
tweak replaced the live EC2 Instance and destroyed its root volume. Do not run a full-stack deploy
during RTH; always create a change set and check for `Replacement: True` first.

⚠ **Open risk:** the mitigation is **not** in the template. On `main`, `DeletionPolicy`/
`UpdateReplacePolicy: Retain` are set on **`BackupBucket`** only — the **`Instance`** resource carries
no retain policy, so the failure mode that destroyed the box on 2026-07-27 is still reachable.
Adding it is a Tier 3 infrastructure change and needs its own reviewed PR.

---

## 12. Weekly cadence (recommended)

| Trigger | Engineering | Documentation |
|---------|-------------|---------------|
| Daily | Develop/validate locally; push only at integration points | Working notes local/S3 |
| PR review-ready | Consolidated push; risk-tiered CI | Only docs required to review/govern the code |
| Friday / weekly | Merge completed work; review CI metrics | One consolidated commit/PR for approved/material docs |
| Release/milestone | Full validation; preserve release evidence | Publish final ADR, runbook, decision artifacts immediately |
| Monthly | Review Actions minutes, runs, artifacts, S3 download behavior | Archive superseded drafts; verify governing docs current |

---

*This markdown is the repository working copy of GITHUB-OPS-001 v1.2. The `.docx` remains the formal policy document. Agents and developers should treat this file and `.cursor/rules/github-dev-process-cost-policy.mdc` as binding guidance for all development effort in this repository.*
