# ADR-0043 Phase-0 D-BOX Evidence Campaign Scope

| Field | Value |
|-------|-------|
| Document ID | ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.1 |
| Status | **FROZEN FOR PARTIAL STRUCTURAL CAMPAIGN — contingent on effective ADR0043-PH0-D-BOX-001** |
| Freeze date | 2026-07-29 |
| Supersedes | ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.0 |
| Amendment reason | Pre-existing O3 corpus and O4-A/O4-B observation-set identities **not found** after governed locate (two passes); inventing identities prohibited |
| Campaign label | **PARTIAL STRUCTURAL CAMPAIGN ONLY — NO D-WIRE ELIGIBILITY — O3/O4/O5 DEFERRED** |
| Authorization ruling | ADR0043-PH0-D-BOX-001 (HOLD / D-WIRE deferred unchanged) |
| Integration design | ADR0043-PH0-INTEGRATION-DESIGN-001 v1.0 |
| Controlling design | ADR0043-PH0-CTRL-001 v1.1 |
| Offline baseline | `d1c2fbf` |
| Successor freeze manifest | ADR0043-PH0-D-BOX-FREEZE-MANIFEST-002 |
| Prior freeze manifest | ADR0043-PH0-D-BOX-FREEZE-MANIFEST-001 — **UNSEALED — SUPERSEDED DUE TO ABSENT O3/O4 EVIDENCE IDENTITIES** |
| O3/O4 evidence successor package | ADR0043-PH0-D-BOX-O34-EVIDENCE-ACQ-001 v1.0 |
| Account | **3 only** |
| Broker order submission | **HOLD — not in scope** |
| Production OrderRouter Phase-0 submit | **Not in scope** |
| D-WIRE | **Deferred / blocked** — incomplete load-bearing evidence |

This scope enumerates the **amended** isolated evidence campaign under D-BOX when
ADR0043-PH0-D-BOX-001 is **effective**. It selects **Option 2A** (partial structural
campaign). Execution of permitted packages must not begin until FREEZE-MANIFEST-002 is
sealed. Sealing does **not** authorize campaign start; a separate owner start decision
is required.

---

## 0. Formal locate result (binding for this amendment)

Second locate pass (2026-07-29) is **sufficient**. Further indefinite search is not
required before this amendment.

| Item | Verdict |
|------|---------|
| O3 historical replay corpus | **NOT FOUND** |
| O4-A decision-time observation set | **NOT FOUND** |
| O4-B forensic / terminal observation set | **NOT FOUND** |

### Locations checked (non-exhaustive inventory of the governed search)

| Location class | Result |
|----------------|--------|
| Local repo / worktrees (`ai-trading-app`, `ai-trading-app-dbox-isolated`, `ai-trading-app-adr0043-ph0`, `wt-lcboot`, `wt-lineage`, `wt-5173b7c`, related `wt-*`) | No bindable O3/O4 archive |
| S3 / `docs_fetch` inventories / `manifests/s3` | **0** ADR0043 Phase-0 O3/O4 corpus keys |
| WP0 seal outputs (`20260729T161843Z`, manifest SHA `08c9a914…`) | Production ops snapshot — **not** an O3 historical-replay corpus |
| Canary / FrozenExecutionPlan / RepairB documents | Prep/governance only — no sealed observation archive |
| WP7 harness + hermetic fixtures (`obs-a`/`obs-b`/`arc-1`, inline KOKU) | Protocol/tests only — **forbidden** as seal identities |
| Canary validation host `3.80.11.61` | **Unreachable** (SSH timed out) this pass |
| ADR 0048 SEP/ACTIONS corpus; CI gate-replay population; acct7/v13 journals | Wrong program / wrong purpose |

### Conclusion

**No bindable artifact** exists that supplies identity, size, hash, provenance, eligibility
window, and observation counts for O3, O4-A, or O4-B. Inventing identities is **prohibited**.
Manufacturing new datasets solely to close a freeze manifest is **prohibited**.

---

## 1. Amended campaign objective (Option 2A)

**PARTIAL STRUCTURAL CAMPAIGN ONLY — NO D-WIRE ELIGIBILITY — O3/O4/O5 DEFERRED**

Produce sealed, reviewable evidence **only** for:

1. **CORR-06 exit** (account isolation);
2. Formal Gates **O1** and **O2** under controlling meanings (structural / deterministic).

### Predetermined dispositions (not executable as PASS in this campaign)

| Package | Predetermined disposition |
|---------|---------------------------|
| **O3** | **INCONCLUSIVE — REQUIRED CORPUS ABSENT** |
| **O4-A** | **INCONCLUSIVE — DECISION-TIME SET ABSENT** |
| **O4-B** | **INCONCLUSIVE — FORENSIC SET ABSENT** |
| **O5** | **INCONCLUSIVE** (no qualified pre-existing Tier-A anchors; `anchors: []`) |

These packages **cannot pass** under v1.1. They are **deferred** to a successor
evidence-acquisition design (ADR0043-PH0-D-BOX-O34-EVIDENCE-ACQ-001) plus a future
campaign amendment that reintroduces them only after bindable corpora exist.

---

## 2. Environment and isolation

Unchanged from v1.0:

| Constraint | Requirement |
|------------|-------------|
| Runtime | Isolated box and/or dedicated worktree / harness |
| Production OrderRouter | **Not** activated for Phase-0 order submission |
| Production path imports | **Forbidden** under D-BOX (belongs to D-WIRE) |
| Phase-0 mode | `DISABLED` or `OBSERVE_ONLY` in isolated harness only |
| Deployed production `OBSERVE_ONLY` | **Out of scope** (D-WIRE) |
| Account | **3 only** |
| Account-1 credential metadata | Zero mutation |
| Production paper stack `b0058bf` | **Environment exclusion** — not the D-BOX baseline; **do not modify** |

---

## 3. Pre-campaign freeze manifest

Campaign execution is **prohibited** until **FREEZE-MANIFEST-002** is sealed and an owner
**start decision** is issued separately.

FREEZE-MANIFEST-001 remains:

> **UNSEALED — SUPERSEDED DUE TO ABSENT O3/O4 EVIDENCE IDENTITIES**

Do **not** modify FREEZE-MANIFEST-001 in place and call it sealed.

FREEZE-MANIFEST-002 must bind the v1.1 campaign ID, partial-package allow-list,
predetermined INCONCLUSIVE dispositions for O3/O4/O5, search-result summary, isolated
checkout identities, July 24 limits digest, and account-3 binding. It must **not** invent
O3/O4 observation-set or corpus identities.

---

## 4. Allowed mutations

Same mechanical allow-list as v1.0 §§4.1–4.4, narrowed as follows:

- Broker reads remain empty unless explicitly re-declared for a permitted CORR-06/O1/O2 step.
- Writes limited to account-3 checkpoint / test-state and evidence seals needed for
  **CORR-06, O1, O2** only.
- Forbidden list unchanged (orders, new live fills, production imports, ENFORCE, caps,
  July 24 digest mutation, undeclared reads).

---

## 5. O5 (deferred / INCONCLUSIVE)

O5 remains **required for D-WIRE eligibility** in the controlling sense, but under v1.1 it
is **not executable** and closes **INCONCLUSIVE** because no qualified Tier-A anchors exist.
D-BOX still **prohibits** generating new live fills. HOLD unchanged.

---

## 6. Gate package matrix (amended)

| Package | In v1.1 execution scope? | Load-bearing for D-WIRE? | Disposition under v1.1 |
|---------|--------------------------|--------------------------|-------------------------|
| **CORR-06** | **Yes** (if owner start authorizes) | Yes (still required later) | Executable → APPROVE / REJECT / INCONCLUSIVE from evidence |
| **O1** | **Yes** | Yes (still required later) | Executable → APPROVE / REJECT / INCONCLUSIVE from evidence |
| **O2** | **Yes** | Yes (still required later) | Executable → APPROVE / REJECT / INCONCLUSIVE from evidence |
| **O3** | **No — deferred** | Yes (blocking) | **INCONCLUSIVE — REQUIRED CORPUS ABSENT** |
| **O4-A** | **No — deferred** | Yes (blocking) | **INCONCLUSIVE — DECISION-TIME SET ABSENT** |
| **O4-B** | **No — deferred** | Yes (blocking) | **INCONCLUSIVE — FORENSIC SET ABSENT** |
| **O5** | **No — deferred** | Yes (blocking) | **INCONCLUSIVE** (anchors absent) |

---

## 7. Evidence packaging

Unchanged hybrid Git + S3 rules from v1.0 §7. Partial-campaign packages (CORR-06/O1/O2)
still require sealed package manifests when executed.

---

## 8. Adjudication and exit criteria (fail-closed; amended)

1. Seal **FREEZE-MANIFEST-002** (readiness exit 0).
2. Separate owner **campaign-start** decision for Option 2A only (sealing ≠ start).
3. If started, run **only**: **CORR-06 → O1 → O2**.
4. Record predetermined INCONCLUSIVE for **O3, O4-A, O4-B, O5** (no PASS possible).
5. **D-WIRE eligibility:** **BLOCKED**. Load-bearing evidence is incomplete. APPROVE on
   CORR-06/O1/O2 alone **does not** grant D-WIRE, production imports, deployed-path
   observation, canary, ENFORCE, caps, or limits-digest changes.
6. A future full campaign may resume O3/O4/O5 **only** after:
   - successor package ADR0043-PH0-D-BOX-O34-EVIDENCE-ACQ-001 is executed and yields
     bindable sealed corpora; and
   - a new campaign-scope version reintroduces those gates; and
   - a new freeze manifest binds those identities.

---

## 9. Explicit non-goals

All v1.0 §9 non-goals, plus:

- Not a claim that CORR-06/O1/O2 completion unlocks D-WIRE
- Not authorization to invent O3/O4 identities or manufacture corpora to force a seal
- Not suspension of useful structural work (Option 2B rejected in favor of 2A)

---

## 10. Parallel D-WIRE draft policy

Unchanged: D-WIRE design draft may proceed for review; must remain non-operative.

---

## 11. Successor evidence package (pointer)

Future O3/O4 observation-set construction is governed by:

**ADR0043-PH0-D-BOX-O34-EVIDENCE-ACQ-001 v1.0**
(`docs/design/ADR0043_Phase0_D_BOX_O34_Evidence_Acquisition_v1.0.md`)

That package is **design-only** under this amendment: it does not authorize broker orders,
does not start D-BOX packages beyond 2A, and does not seal FREEZE-MANIFEST-002 by itself.

---

## 12. Disposition

**CAMPAIGN SCOPE v1.1 — OPTION 2A PARTIAL STRUCTURAL ONLY.**

Label: **PARTIAL STRUCTURAL CAMPAIGN ONLY — NO D-WIRE ELIGIBILITY — O3/O4/O5 DEFERRED**

HOLD unchanged. D-WIRE deferred and blocked until load-bearing O3/O4/O5 evidence exists
and a later campaign version reopens those gates.

*End of ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.1.*
