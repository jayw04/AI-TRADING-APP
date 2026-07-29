# Owner Decision — D-BOX Evidence Campaign Authorization

| Field | Value |
|-------|-------|
| Ruling ID | ADR0043-PH0-D-BOX-001 |
| Decision | **APPROVED** |
| Scope | Isolated Phase-0 **evidence campaign** only (formal O1–O5 + CORR-06 exit) |
| Ruling date | 2026-07-29 |
| Status | **EFFECTIVE** — owner-signed and published under recorded repository identity |
| Governing design | ADR0043-PH0-CTRL-001 v1.1 |
| Integration design | ADR0043-PH0-INTEGRATION-DESIGN-001 v1.0 (D-DESIGN-FREEZE granted) |
| Offline baseline | `d1c2fbf` / tag `adr0043-phase0-offline-complete` |
| Campaign scope | ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.0 |
| D-WIRE | **Deferred** — not granted; may be drafted in parallel; must not be granted or implemented before D-BOX load-bearing evidence is accepted under campaign §8 |
| Broker submission | **HOLD** |
| Formal canary | **HOLD** |

---

## 1. Why D-BOX before D-WIRE

D-BOX is the lower-risk and logically prior decision: it produces the formal O1–O5
evidence needed to justify any production integration. Granting D-WIRE before D-BOX
would introduce production-path code before the architecture has been validated on the
box, even if that code is `DISABLED` or `OBSERVE_ONLY`.

---

## 2. Ruling

The owner **authorizes D-BOX** as follows.

### 2.1 Authorized

| Item | Bound |
|------|-------|
| Account | **Account 3 only** |
| Purpose | Isolated evidence campaign: CORR-06 exit + formal Gates O1–O5 under controlling meanings, per ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.0 |
| Environment | Isolated box deployment and/or dedicated worktree / harness **outside** production OrderRouter activation for Phase-0 submit |
| Phase-0 mode on box | `DISABLED` or `OBSERVE_ONLY` in isolated box/harness only (not deployed production orchestration) |
| Pre-campaign freeze manifest | **Required** before CORR-06 or any O-gate (campaign §3) |
| Broker | **Reads only**, when declared in the freeze manifest; each read must be account-3 scoped and **side-effect-free** (no incidental credential/risk/broker/account mutation unless separately enumerated as test-state and accepted by CORR-06) |
| Writes | Account-3-scoped **checkpoint** and **test-state** writes only as enumerated in the freeze manifest / campaign scope |
| O5 anchors | Pre-existing sealed Tier-A live-fill evidence only; **no new live fills**; inadequate anchors → O5 **INCONCLUSIVE**; HOLD unchanged |
| Evidence | Sealed O1–O5 packages + CORR-06 exit; hybrid repo manifests + S3 Version-ID + SHA-256 pins |
| Outcomes | APPROVE / REJECT / INCONCLUSIVE per package; D-WIRE eligibility fail-closed per campaign §8 |

### 2.2 Explicitly not authorized

| Item | Status |
|------|--------|
| Broker **order** submission (any account) | **HOLD** — not lifted |
| Generating new live fills (including for O5) | **Not authorized** |
| Production `OrderRouter` activation for Phase-0 submit | **Not authorized** |
| Production imports of Phase-0 into order / risk / startup modules | **Not authorized** (requires **D-WIRE**) |
| Deployed-path `OBSERVE_ONLY` in production orchestration | **Not authorized** (requires **D-WIRE**) |
| `PREFLIGHT_REFUSE` / `CANARY_AUTHORIZED` | **Not authorized** |
| Formal canary | **HOLD** |
| Legacy ENFORCE | **Not authorized** |
| Cap changes | **Not authorized** |
| July 24 limits-digest changes | **Not authorized** |
| Reuse of prior baselines / authorizations | **Not authorized** |
| Mutation of July 24 historical evidence chain | **Not authorized** |
| Treating D-BOX as production integration authorization | **Prohibited** |
| Campaign execution before freeze manifest seal | **Prohibited** |

### 2.3 Sequencing after campaign

```text
D-BOX effective (this ruling published)
  → Seal pre-campaign freeze manifest
  → Execute ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.0
  → Seal & review O1–O5 + CORR-06 exit
  → Owner adjudication per package
  → D-WIRE only if every load-bearing package APPROVE (campaign §8)
  → D-CANARY / D-ENFORCE / D-CAPS-DIGEST remain separate and later
```

D-WIRE may be **prepared as a design draft in parallel** but must **not** be granted or
implemented before load-bearing D-BOX evidence is accepted.

---

## 3. Effectiveness

This ruling is **owner-signed** and **effective** for campaign execution under the
Publication identity below. Campaign start still requires the pre-campaign freeze
manifest (campaign §3) to be sealed before CORR-06 or any O-gate.

---

## 4. Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Owner | Jay Wang | 2026-07-29 | Approved (owner directive 2026-07-29 — approve with four required edits, then proceed) |

## 5. Publication identity

| Item | Value |
|------|-------|
| Ruling path | `docs/design/ADR0043_Phase0_D_BOX_Authorization_v1.0.md` |
| Ruling commit (signed text) | `05095a6f91520fbcd6e01e8b937ef9895af39fc6` |
| Ruling SHA-256 (file bytes at `05095a6`) | `9eba4233ed221695b4364a7bb0331700d8f0300e91920baaeeec4a794d56d8bd` |
| Campaign scope path | `docs/design/ADR0043_Phase0_D_BOX_Campaign_Scope_v1.0.md` |
| Campaign scope commit | `05095a6f91520fbcd6e01e8b937ef9895af39fc6` |
| Campaign scope SHA-256 | `f405bdb454a18d30423890087b292d6818429af7152a84e193bf57cce2412127` |
| Integration design path | `docs/design/ADR0043_Phase0_Integration_Design_v1.0.md` |
| Integration design commit | `05095a6f91520fbcd6e01e8b937ef9895af39fc6` |
| Integration design SHA-256 | `5d0ab3c1adbb6a145345c6657cac2db2a9395644abe39127b559ae862f974078` |
| `main` merge commit | *(record after PR merge)* |

---

**HOLD unchanged:** no broker orders, production imports, deployed-path observation,
canary, ENFORCE, cap changes, or July 24 limits-digest changes.

*End of ADR0043-PH0-D-BOX-001.*
