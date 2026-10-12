# RANGE-002 role appointments (recorded by the owner)

| Field | Value |
|---|---|
| Status | **DRAFT for the owner.** Records the owner's role assignments of 2026-10-12 (instruction revision 2, section 0). The owner's merge of this PR is the record; the agent does not merge. |
| Baseline | commit `1ecf811b` (CI #1851 green) |
| Rule | **A role marked PENDING is VACANT for every gate until a signed acceptance record exists in Git.** An assignment is not an acceptance. |
| Not changed here | No role was reassigned by the agent. This file records, it does not appoint. |

## 1. Assignments

| Person | Role | Scope | Sign-off authority | Independence status | Acceptance |
|---|---|---|---|---|---|
| Claude Code (agent) | Code author | Wrote the RANGE-002 screening build under owner direction. Prepares drafts and evidence. | **NONE.** May not approve, self-review, count any agent session as a reviewer, or merge. | Not independent of the code it wrote. | n/a (agent) |
| Jay Wang | Owner; non-author code reviewer | Owner and gate-setter; reviews the guard-adjacent files per the code-review ruling; holds `signoff.owner`, the run-authorization acts and every "owner act" in the plan. | **GATE** (as owner). The code review is evidence for the merge; it is not a validator sign-off. | **Dual role disclosed** (owner / gate-setter / reviewer). Independence for the run is supplied by the validator, whose sign-off the owner may not hold or waive. | Owner act; not applicable |
| 陈友潼 (Chen Youtong) | Independent validator | Independent validation of the plan, worksheet, probe pre-registration, spec and criteria **before any probe or loader output exists**. | **GATE** (`signoff.independent_validator` and the validator attestations listed in the sign-off reconciliation). | **NOT ESTABLISHED.** Eligibility is subject to verification; no verifier record exists in Git. The owner cannot waive it. | **PENDING** |
| 肖学焦 (Xiao Xuejiao) | Risk / loss-control reviewer | Advisory review of risk and loss-limit parameters (per-trade risk, daily-loss, exposure caps, concurrency). | **ADVISORY. No gate sign-off.** | Not assessed. | **PENDING** |
| 方炳雄 (Fang Bingxiong) | Exit / take-profit design reviewer | Advisory review of exit design, take-profit, stop, scale-out and trailing parameters and how they were chosen. | **ADVISORY. No gate sign-off.** | Not assessed. | **PENDING** |
| 梁云鹏 (Liang Yunpeng) | Team liaison | Coordination only. | **NONE. No sign-offs of any kind.** | **The owner's relative; may not hold any independence-bearing role.** | n/a |

## 2. Effect on gates (stated, not decided)
- With every named non-owner role PENDING, **no independence-bearing gate is satisfied**. The validator gate is VACANT until an acceptance record exists.
- The advisory reviewers' comments are recorded as advice; no gate depends on them.
- The spec's `signoff.trading_expert` has **no eligible holder** under these assignments (the two advisory roles hold no gate sign-off and the liaison holds none). See `RANGE-002_Signoff_Reconciliation_v0.1.md`, section 4. This record does not fill it.

## 3. Acceptance blocks (blank; each person completes their own)
Each block must be a signed record committed to Git before the role is treated as held.

### 3.1 陈友潼 (Chen Youtong) — independent validator
| Field | Entry |
|---|---|
| Name | |
| Date (UTC) | |
| Statement of acceptance (scope, and that no relationship with the owner, the code author or the liaison impairs independence) | |
| Confidentiality acknowledgment | |
| Signature / commit reference | |

### 3.2 肖学焦 (Xiao Xuejiao) — risk / loss-control reviewer (advisory)
| Field | Entry |
|---|---|
| Name | |
| Date (UTC) | |
| Statement of acceptance (advisory scope; no gate sign-off) | |
| Confidentiality acknowledgment | |
| Signature / commit reference | |

### 3.3 方炳雄 (Fang Bingxiong) — exit / take-profit design reviewer (advisory)
| Field | Entry |
|---|---|
| Name | |
| Date (UTC) | |
| Statement of acceptance (advisory scope; no gate sign-off) | |
| Confidentiality acknowledgment | |
| Signature / commit reference | |

### 3.4 梁云鹏 (Liang Yunpeng) — team liaison
| Field | Entry |
|---|---|
| Name | |
| Date (UTC) | |
| Acknowledgment that the role carries no sign-off and no independence-bearing role | |
| Confidentiality acknowledgment | |
| Signature / commit reference | |
