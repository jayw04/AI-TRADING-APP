# ADR NNNN (PROPOSED, number not reserved): Single-owner review of changes to `main` is an accepted, recorded risk (Option D)

> **PROPOSAL ONLY. Not an ADR until the owner adopts it through the normal ADR process (`docs/adr/`).** All approval fields are blank. The filename in `docs/adr/` should be `NNNN-single-owner-review-risk-acceptance.md`; the number is a placeholder. On `origin/main` (d61f313a) the highest ADR file is 0056, and the ADR 0055 numbering note records 0052 and 0053 as reserved by in-flight workstreams and 0054 as taken by an unmerged branch; 0050 is also absent from `main`. The next free number therefore cannot be determined from `main` alone and is deliberately not chosen here.

| Field | Value |
|---|---|
| Date | ____ |
| Status | PROPOSED (not adopted) |
| Phase | Cross-phase (repository governance; RANGE-002 research track and the platform) |
| Decision owner | ____ (blank) |
| Related | CLAUDE.md (walk-away discipline, GITHUB-OPS-001 v1.2, "when conventions and request conflict"); Governance and Release Policy Proposals v0.2 (sections 0.1, 1.3, 1.10); RANGE-002 Level 1 Acceptance Test Plan v0.1 (independent reviewer, Q-A1) |

## Context

1. The repository has exactly one collaborator, the owner (`jayw04`), who authors essentially every change. The repository is user-owned, so it has no teams and no reviewer group.
2. GitHub never counts an author's approval of their own pull request toward required approvals. A rule "at least one approval from someone other than the author" therefore cannot be satisfied today.
3. The classic protection on `main` already has `enforce_admins: true`. Adding a required-review rule would apply to the admin as well, leaving no bypass: every PR, including one that removes the rule, would be unmergeable without first editing the protection by hand (a solo-owner lock-out).
4. Today's binding merge controls are: required status check `Python CI Gate` with `strict: true`, no force pushes, no branch deletion, and the owner's own explicit merge. No human review other than the owner's is enforced by the platform.
5. A second GitHub account controlled by the same person would satisfy the counter but not the purpose. It is a process control, not independent review.

## Decision (to be chosen by the owner; this is the proposed text)

Until a second qualified human reviewer with write access exists:

1. **No required-review rule is activated on `main`** (neither a ruleset nor classic protection), because it cannot be satisfied and, with `enforce_admins`, would lock the owner out.
2. **Explicit owner merge approval remains the operating policy.** Nothing is merged without the owner's explicit approval in that session; no agent merges, pushes to `main`, enables auto-merge, or changes repository settings on its own authority.
3. **Walk-away discipline is retained**: at least 1 hour between "ready for review" and merge, and at least 2 hours for consequential PRs (CI gating, risk gates, live path, governance code).
4. **Self-review is recorded, not skipped**: the PR body carries the checklist from the pull request template, and for order-path, risk-engine, audit-log, workflow and RANGE-002 governance code the owner re-reads the final diff after the walk-away.
5. **Honest statements.** Every acceptance report and evidence package says that reviews by the owner, or by a second account the owner controls, are not independent human reviews. **Independent review performed by separate AI agents is also NOT human review**: it is useful evidence of defects found, but it is not a substitute for a second qualified human and must not be described as one.
6. **Invariants unchanged.** This ADR relaxes no architectural or CI invariant in CLAUDE.md (single OrderRouter, hash-chained audit log, no-LLM-in-order-path, risk gates, activation cooldowns, the CI invariants). It records what is and is not enforced by GitHub.

## Compensating controls (what stands in for a second reviewer)

| Control | State |
|---|---|
| `Python CI Gate` required, `strict: true`, `enforce_admins: true` (no force-push, no deletion) | In force |
| CI invariants and coverage gates (CLAUDE.md) | In force |
| Walk-away discipline and recorded owner approval | Operating policy |
| Secret scanning and push protection | Enabled by the owner/coordinator (2026-10-10); see Governance proposals v0.2 section 0.4 for verified state and the private alert-review procedure |
| Independent reviews by separate agents (labelled as NOT human review) | Used for RANGE-002 and CI changes; recorded in PR or evidence packages |
| Evidence packages: Actions artifacts hashed locally now; permanent versioned S3 package with Version ID + SHA-256 is pending separate authorisation | Partially in place |
| Status boxes / "DESIGN ONLY, not implemented" banners and blank signature fields on proposals | Convention |

## Consequences

- Positive: the owner is never locked out; the limitation is stated rather than hidden; no new enforcement mechanism that cannot work.
- Negative: any change to `main`, including order-path or risk-engine code, can be merged by the owner's own decision after CI passes. A mistake or a compromised owner credential is not caught by a second human. This residual risk is accepted by this ADR if adopted.
- Independence claims in RANGE-002 (Level 1 acceptance, P0 approvals) require an external human reviewer; this ADR does not provide one.

## Triggers to revisit

Re-open this decision when any of the following occurs: a second qualified reviewer with write access exists (then adopt Option A: ruleset Variant 1 with CODEOWNERS for workflows, `range002`, risk, orders, ADRs and manifests); the repository moves to an organisation (teams and `bypass_pull_request_allowances` become available); a consequential PR is proposed that the owner judges needs enforced independent review; or the date recorded in the Decision section passes.

## Alternatives considered

A: second human reviewer plus ruleset Variant 1 (preferred when a person exists). B: machine account (process control only; not independence). C: Actions-based approval check (no independence; needs a repository-wide setting write). D (this proposal): record the exception.

## Approval (all blank; nothing is approved)

| Role | Name | Signature | Date |
|---|---|---|---|
| Owner | | | |
