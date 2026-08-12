# Contributing to Trading Workbench (AI-TRADING-APP)

All development in this repository follows **GITHUB-OPS-001 v1.2**.

- **Policy (markdown):** [`docs/methodology/GitHub_Development_Process_and_Cost_Optimization_Policy_v1.2.md`](docs/methodology/GitHub_Development_Process_and_Cost_Optimization_Policy_v1.2.md)
- **Formal document:** `…_v1.2_Actions_and_S3.docx` — not in Git; the markdown above is the working copy
- **Architecture & invariants:** [`CLAUDE.md`](CLAUDE.md)

## Quick rules

1. **Batch locally** — one review-ready PR per coherent outcome; 1–3 pushes per work item.
2. **Validate locally before push** — lint, format, focused tests; avoid triggering full CI for low-risk edits.
3. **Risk-tiered CI** — Tier 0 (docs) through Tier 3 (migrations, infra, release); full suite only when risk requires it. In practice CI runs a per-project LIGHT pass on every PR and adds a project's FULL pass (pytest + coverage) when its paths change; `Python CI Gate` is the required check. Note that `scripts/**` and `deploy/**` count as *backend*.
4. **Storage** — Git for source, tests, IaC, migrations, small config, and **governing documentation** (ADRs, runbooks, incidents, policies, design and implementation notes). S3 for generated evidence, research archives, large data and Office binaries, pinned by Version ID + SHA-256 in a manifest.
5. **Don't add new bulk material to Git.** The Git↔S3 documentation split is a classification rule, not yet an enforced one — the fetch/publish tooling and manifests are not merged. If a change needs a governed S3 object, raise it rather than inventing an ad-hoc manifest format.

## Pull requests

Use the [PR template](.github/pull_request_template.md). Trading Workbench **walk-away discipline** still applies: at least 1 hour (2+ hours for risk/order-path/production changes) between ready-for-review and merge.

**CI tiers:** GitHub Actions classifies each PR (Tier 0–3). See the Phase 2 org settings checklist (`docs/methodology/GITHUB_OPS_001_Phase2_Org_Settings_Checklist.md` — **not yet written**; org budgets and branch protection remain manual owner steps).

## Exceptions

Production incidents, security fixes, migrations, governing ADRs, and release gates may bypass batching — record the reason in the PR.
