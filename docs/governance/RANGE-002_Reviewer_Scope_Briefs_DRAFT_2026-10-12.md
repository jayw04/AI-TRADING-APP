# RANGE-002 reviewer scope briefs / 评审范围说明 — DRAFT, NOT SENT

| 项目 / Field | 内容 / Value |
|---|---|
| 状态 / Status | **草稿，尚未发送。** 由所有者发送；代理不联系任何人。 **DRAFT. NOT SENT.** The owner sends these; the agent contacts no one. |
| 基线 / Baseline | commit `1ecf811b` (CI #1851 通过 / green) |
| 重要 / Important | 在存在已签署的接受记录（提交到 Git）之前，各角色均为“待定 (PENDING)”，在任何关口中视为空缺。 Until a signed acceptance record is committed to Git, each role is PENDING and counts as VACANT for any gate. |

---

## 1. 陈友潼 — 独立验证人 / Independent validator

**审查内容 / What you review**
- 基线参数工作表（所有者采纳前）、身份探测的预先登记（标签与判定规则）、规格与判定标准。
  The baseline-values worksheet (before owner adoption), the identity-probe pre-registration (labels and decision rule), the spec and the screening criteria.
- **在任何探测或加载输出存在之前**完成审查。
  This review must happen **before any probe or loader output exists**.

**签署 / 不签署 What you sign, and what you do not**
- 你的验证人签署及验证人声明（见《签署核对表》）是**关口 (GATE)**；所有者**不得**代为持有或豁免。
  Your validator sign-off and attestations (see the sign-off reconciliation) are a **GATE**; the owner **may not hold or waive** them.
- 你不审批合并，也不为任何策略结果背书；目前**没有任何业绩结果**。
  You do not approve merges and do not endorse any strategy result; **no performance result exists**.
- 请在签署前书面说明自己与所有者、代码作者、联络人之间不存在影响独立性的关系。
  Before signing, state in writing that no relationship with the owner, the code author or the liaison impairs your independence.

**保密 / Confidential**
- 规格、工作表、预先登记、评审意见与任何未公开材料；供应商账户与凭据信息。
  The spec, worksheet, pre-registration, review comments and any unpublished material; vendor account and credential information.
- 不得向被指名评审人以外的任何人披露；不得用于交易。
  Do not disclose beyond the named reviewers; do not use for trading.

**待审文件与 SHA-256 / Artifact(s) under review** (值取自起草时；发送前请重新计算 / values at drafting time; recompute before sending, a later change makes the record STALE)
| 路径 / Path | SHA-256 |
|---|---|
| `docs/implementation/evidence/range_002/RANGE-002_Baseline_Values_Worksheet_v0.1.md` | `d4581f7141dc1b9e3a8a52597d7e8208902a30121d14f420e714a783e246d13d` |
| `docs/implementation/evidence/range_002/RANGE-002_Identity_Probe_Preregistration_v1.json` | `116a0601ff29374a38c4290cc355c506374c7137d420c908a15b76e91e3a17fc` |
| `docs/implementation/evidence/range_002/RANGE-002_Baseline_Conflict_Provenance_v0.1.md` | `865f7f4db4fdb00fdd337871ab587b7848beff92bf3f24c8779e840c18bda346` |
| `docs/governance/RANGE-002_Signoff_Scope_by_Gate_v0.1.md` | `5e16fc68feefdc57674bf195844b3c8fe2ab64d719977eb13e089cfac1f2362e` |

**回复要求 / Requirements for your reply** (a reply that lacks any of these cannot be counted)
1. **用您自己的话 / In your own words** — 不要复制所有者的转述。 Do not paste the owner's paraphrase.
2. **引用上面的 SHA-256 / Cite the SHA-256 above** — 否则记录会被判定为过期或无效。 Otherwise the record is STALE or INVALID.
3. **明确的结论 / An explicit conclusion** — 请写明： **同意 / 不同意 / 有条件同意** (有条件时请列出条件)。 Write exactly one of: **同意 (approve) / 不同意 (reject) / 有条件同意 (conditional, list the conditions)**.

---

## 2. 肖学焦 — 风险 / 损失控制评审（咨询）/ Risk and loss-control reviewer (advisory)

**审查内容 / What you review**
- 工作表中与风险及亏损限制相关的行：单笔风险比例、日亏损上限、总敞口与单标的上限、并发数。
  The worksheet rows on risk and loss limits: per-trade risk, daily-loss limit, gross and per-name caps, concurrency.
- 这些参数是否保守、是否与平台既有的风险引擎约束一致。
  Whether they are conservative and consistent with the platform's existing risk-engine constraints.

**签署 / 不签署 What you sign, and what you do not**
- **咨询性质，不是关口签署。** 你的意见会被记录，但没有任何关口依赖它。
  **Advisory only; not a gate sign-off.** Your comments are recorded; no gate depends on them.
- 你不审批合并，也不代表验证人。
  You do not approve merges and you do not stand in for the validator.

**保密 / Confidential**
- 与 1 相同。 Same as section 1.

**待审文件与 SHA-256 / Artifact(s) under review** (值取自起草时；发送前请重新计算 / values at drafting time; recompute before sending, a later change makes the record STALE)
| 路径 / Path | SHA-256 |
|---|---|
| `docs/implementation/evidence/range_002/RANGE-002_Baseline_Values_Worksheet_v0.1.md` | `d4581f7141dc1b9e3a8a52597d7e8208902a30121d14f420e714a783e246d13d` |

仅审阅工作表中标注了您姓名的行。 Review only the worksheet rows tagged with your name.

**回复要求 / Requirements for your reply** (a reply that lacks any of these cannot be counted)
1. **用您自己的话 / In your own words** — 不要复制所有者的转述。 Do not paste the owner's paraphrase.
2. **引用上面的 SHA-256 / Cite the SHA-256 above** — 否则记录会被判定为过期或无效。 Otherwise the record is STALE or INVALID.
3. **明确的结论 / An explicit conclusion** — 请写明： **同意 / 不同意 / 有条件同意** (有条件时请列出条件)。 Write exactly one of: **同意 (approve) / 不同意 (reject) / 有条件同意 (conditional, list the conditions)**.

---

## 3. 方炳雄 — 退出 / 止盈设计评审（咨询）及拟任交易专家（待所有者裁定）/ Exit and take-profit design reviewer (advisory) and PROPOSED trading expert (pending owner ruling)

**审查内容 / What you review**
- 工作表中与退出相关的行：候选退出族、止盈倍数、止损、分批、跟踪止损，以及这些参数**是否来自历史数据**。
  The worksheet rows on exits: the candidate exit families, take-profit multiples, stop, scale-out and trailing parameters, and **whether each was chosen from historical data**.
- 来自数据的参数必须只使用开发分区，并有试验账本条目；**不得接触保留样本 (holdout)**。
  A data-chosen parameter may use the development-only partition only and needs a trial-ledger entry; it **may never touch the holdout**.

**签署 / 不签署 What you sign, and what you do not**
- **咨询性质，不是关口签署。** Advisory only; not a gate sign-off.
- 你不审批合并，也不代表验证人。 You do not approve merges and you do not stand in for the validator.

**保密 / Confidential**
- 与 1 相同。 Same as section 1.

**待审文件与 SHA-256 / Artifact(s) under review** (值取自起草时；发送前请重新计算 / values at drafting time; recompute before sending, a later change makes the record STALE)
| 路径 / Path | SHA-256 |
|---|---|
| `docs/implementation/evidence/range_002/RANGE-002_Baseline_Values_Worksheet_v0.1.md` | `d4581f7141dc1b9e3a8a52597d7e8208902a30121d14f420e714a783e246d13d` |
| `docs/governance/RANGE-002_Signoff_Scope_by_Gate_v0.1.md` | `5e16fc68feefdc57674bf195844b3c8fe2ab64d719977eb13e089cfac1f2362e` |

工作表中标注您姓名的退出相关行；若所有者另行裁定，还包括 `signoff.trading_expert` 的范围（见签署范围文件）。 The worksheet rows tagged with your name; and, only if the owner rules, the scope of `signoff.trading_expert` (see the sign-off scope document).

**回复要求 / Requirements for your reply** (a reply that lacks any of these cannot be counted)
1. **用您自己的话 / In your own words** — 不要复制所有者的转述。 Do not paste the owner's paraphrase.
2. **引用上面的 SHA-256 / Cite the SHA-256 above** — 否则记录会被判定为过期或无效。 Otherwise the record is STALE or INVALID.
3. **明确的结论 / An explicit conclusion** — 请写明： **同意 / 不同意 / 有条件同意** (有条件时请列出条件)。 Write exactly one of: **同意 (approve) / 不同意 (reject) / 有条件同意 (conditional, list the conditions)**.

---

## 4. 联络人 / Liaison (no brief to review)
梁云鹏仅负责联络，**不持有任何签署**，也**不得担任任何与独立性相关的角色**。
Liang Yunpeng coordinates only, **holds no sign-off of any kind**, and **may not hold any independence-bearing role**.

## 5. 发送前由所有者确认 / For the owner before sending
- 发送这些说明是所有者的行为；代理没有联系任何人。 Sending is the owner's act; the agent has contacted no one.
- 接受记录的空白模板在 `RANGE-002_RoleAppointments_2026-10-12.md`。 The blank acceptance blocks are in `RANGE-002_RoleAppointments_2026-10-12.md`.
