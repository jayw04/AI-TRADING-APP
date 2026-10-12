# RANGE-002 role appointments (recorded by the owner)

| Field | Value |
|---|---|
| Status | **DRAFT for the owner.** Records the owner's role assignments of 2026-10-12 (instruction revision 2, section 0). The owner's merge of this PR is the record; the agent does not merge. |
| Baseline | commit `1ecf811b` (CI #1851 green) |
| Rule | **A role marked PENDING is VACANT for every gate until a signed acceptance record exists in Git.** An assignment is not an acceptance. |
| Acceptance recorded | **2026-10-12, owner statement.** 方炳雄 accepted `signoff.trading_expert` (rows 2, 19, 20). 陈友潼 accepted the independent-validator role (rows 3, 13, 19, 29). Jay Wang accepted the non-author reviewer role (row 31). This commit is that record. It is **not GENUINE**: no original-message evidence file is attached, the Lane K checker has not returned GENUINE, and #740 is unmerged. |
| Not changed here | No role was reassigned by the agent. This file records, it does not appoint. |

## 1. Assignments

| Person | Role | Scope | Sign-off authority | Independence status | Acceptance |
|---|---|---|---|---|---|
| Claude Code (agent) | Code author | Wrote the RANGE-002 screening build under owner direction. Prepares drafts and evidence. | **NONE.** May not approve, self-review, count any agent session as a reviewer, or merge. | Not independent of the code it wrote. | n/a (agent) |
| Jay Wang | Owner; non-author code reviewer | Owner and gate-setter; reviews the guard-adjacent files per the code-review ruling; holds `signoff.owner`, the run-authorization acts and every "owner act" in the plan. | **GATE** (as owner). The code review is evidence for the merge; it is not a validator sign-off. | **Dual role disclosed** (owner / gate-setter / reviewer). Eligibility as the non-author reviewer where the owner directed the change remains UNKNOWN (AMD:49). Independence for the run is supplied by the validator, whose sign-off the owner may not hold or waive. | **ACCEPTED 2026-10-12** for the non-author reviewer role (row 31). Not GENUINE. |
| 陈友潼 (Chen Youtong) | Independent validator | Independent validation of the plan, worksheet, probe pre-registration, spec and criteria **before any probe or loader output exists**. Rows 3, 13, 19, and 29. | **GATE** (`signoff.independent_validator` and the validator attestations listed in the sign-off reconciliation). | **NOT ESTABLISHED.** Eligibility is subject to verification; no verifier record exists in Git. The owner cannot waive it. | **ACCEPTED 2026-10-12** (owner statement). Not GENUINE. |
| 肖学焦 (Xiao Xuejiao) | Risk / loss-control reviewer | Advisory review of risk and loss-limit parameters (per-trade risk, daily-loss, exposure caps, concurrency). | **ADVISORY. No gate sign-off.** | Not assessed. | **PENDING** |
| 方炳雄 (Fang Bingxiong) | **Trading expert (gate holder for `signoff.trading_expert`)**; exit / take-profit design reviewer | Advisory review of exit design, take-profit, stop, scale-out and trailing parameters and how they were chosen. Holds the spec's `signoff.trading_expert` on rows 2, 19, and 20. | **GATE for `signoff.trading_expert`. ADVISORY on exit design.** Accepted 2026-10-12. Not GENUINE. | Not assessed. The owner may not hold this sign-off (SoD-A). V-2.6 and V-2.7 for him are not on file. | **ACCEPTED 2026-10-12** (owner ruling and his acceptance, owner statement). Not GENUINE. |
| 梁云鹏 (Liang Yunpeng) | Team liaison | Coordination only. | **NONE. No sign-offs of any kind.** | **The owner's relative; may not hold any independence-bearing role.** | n/a |

## 2. Effect on gates (stated, not decided)
- 方炳雄 and 陈友潼 are **accepted, not GENUINE**. Their gates are no longer vacant for lack of acceptance. They still do not count toward a freeze until a hash-bound record exists, the Lane K checker returns GENUINE, and #740 is merged.
- 肖学焦 remains **PENDING** and advisory; no gate depends on him.
- The spec's `signoff.trading_expert` holder is 方炳雄, accepted 2026-10-12. The research lead (`governance.roles`) still has none.

## 3. Acceptance blocks (blank; each person completes their own)
Each block must be a signed record committed to Git before the role is treated as held.

### 3.1 陈友潼 (Chen Youtong) — independent validator
| Field | Entry |
|---|---|
| Name | 陈友潼 (Chen Youtong) |
| Date (UTC) | 2026-10-12 |
| Statement of acceptance (scope, and that no relationship with the owner, the code author or the liaison impairs independence) | Owner statement: he has accepted the independent-validator role on rows 3, 13, 19, and 29. The independence statement itself is not in this file. |
| Confidentiality acknowledgment | Not separately recorded here. |
| Signature / commit reference | This commit. Owner-relayed. No original-message evidence file. Not GENUINE. |

### 3.2 肖学焦 (Xiao Xuejiao) — risk / loss-control reviewer (advisory)
| Field | Entry |
|---|---|
| Name | |
| Date (UTC) | |
| Statement of acceptance (advisory scope; no gate sign-off) | |
| Confidentiality acknowledgment | |
| Signature / commit reference | |

### 3.3 方炳雄 (Fang Bingxiong) — trading expert (gate) and exit / take-profit design reviewer (advisory)
| Field | Entry |
|---|---|
| Name | 方炳雄 (Fang Bingxiong) |
| Date (UTC) | 2026-10-12 |
| Statement of acceptance of the advisory scope | Owner statement: accepted. |
| Statement of acceptance of `signoff.trading_expert` (only if the owner has ruled) | Owner ruling and his acceptance, rows 2, 19, and 20. |
| Statement that no relationship with the owner or code author impairs independence | Not on file (V-2.6, V-2.7). |
| Confidentiality acknowledgment | Not separately recorded here. |
| Signature / commit reference | This commit. Owner-relayed. No original-message evidence file. Not GENUINE. |

### 3.4 梁云鹏 (Liang Yunpeng) — team liaison
| Field | Entry |
|---|---|
| Name | |
| Date (UTC) | |
| Acknowledgment that the role carries no sign-off and no independence-bearing role | |
| Confidentiality acknowledgment | |
| Signature / commit reference | |
