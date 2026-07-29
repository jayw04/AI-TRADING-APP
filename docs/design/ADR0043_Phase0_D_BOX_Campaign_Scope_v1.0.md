# ADR-0043 Phase-0 D-BOX Evidence Campaign Scope

| Field | Value |
|-------|-------|
| Document ID | ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.0 |
| Status | **FROZEN FOR CAMPAIGN — contingent on effective ADR0043-PH0-D-BOX-001** |
| Freeze date | 2026-07-29 |
| Supersedes | ADR0043-PH0-D-BOX-CAMPAIGN-001 v0.1 |
| Authorization ruling | ADR0043-PH0-D-BOX-001 |
| Integration design | ADR0043-PH0-INTEGRATION-DESIGN-001 v1.0 |
| Controlling design | ADR0043-PH0-CTRL-001 v1.1 |
| Offline baseline | `d1c2fbf` |
| Account | **3 only** |
| Broker order submission | **HOLD — not in scope** |
| Production OrderRouter Phase-0 submit | **Not in scope** |
| D-WIRE | **Deferred** — eligibility only after §7 exit criteria |

This scope enumerates the isolated evidence campaign D-BOX authorizes when
ADR0043-PH0-D-BOX-001 is **effective**. Execution must not begin until that ruling is
effective and the **pre-campaign freeze manifest** (§3) is sealed.

---

## 1. Campaign objective

Produce sealed, reviewable evidence for:

1. **CORR-06 exit** (account isolation) before O1/O2 structural approval on the box;
2. Formal Gates **O1–O5** under **controlling meanings** (not redefined):
   - O1 — Contract and structural conformance
   - O2 — Deterministic unit and property tests
   - O3 — Historical replay and backtest
   - O4-A / O4-B — Decision-time vs forensic replay (no mixing; both required)
   - O5 — Shadow-session validation (**no broker order submission**)
3. Owner adjudication per package: **APPROVE** | **REJECT** | **INCONCLUSIVE**.

---

## 2. Environment and isolation

| Constraint | Requirement |
|------------|-------------|
| Runtime | Isolated box and/or dedicated worktree / harness |
| Production OrderRouter | **Not** activated for Phase-0 order submission |
| Production path imports | **Forbidden** under D-BOX (belongs to D-WIRE) |
| Phase-0 mode | `DISABLED` or `OBSERVE_ONLY` in isolated harness only |
| Deployed production `OBSERVE_ONLY` | **Out of scope** (D-WIRE) |
| Account | **3 only**; no trade/risk mutation outside account 3 |
| Account-1 credential metadata | Zero mutation (campaign invariant) |

---

## 3. Pre-campaign freeze manifest (required before CORR-06 or any O-gate)

Before CORR-06 or any O-gate execution, one **signed/sealed campaign freeze manifest**
must bind at least:

| Manifest field | Requirement |
|----------------|-------------|
| Campaign ID and runbook version | Exact IDs |
| Code / tool commits | Implementation and harness commits used on the box |
| Account 3 identity | Workbench account id + broker account binding as used |
| Limits digest | July 24 (or current frozen) digest identity — **unchanged** by this campaign |
| Loss-control version | `loss_control_state_version` / schema identity |
| Datasets | Names, partitions, eligibility windows |
| S3 objects | Version IDs + SHA-256 for every large/raw input |
| Evidence-tier assignments | Tier A–D mappings for each evidence class used |
| Sample and stratum definitions | Including O5 floors / strata |
| Permitted broker reads | Exact endpoints/operations; all must satisfy §4.1 |
| Permitted writes | Account-3 checkpoint / test-state only as enumerated |
| Gate pass criteria | Per-package APPROVE criteria |
| Independence / clustering assumptions | As required for O5 / statistical reporting |

**Post-unseal lock:** No dataset substitution or threshold change after unseal, except the
**single governed WP5 floor replacement** before model evaluation (if used), followed by
**relock**. Any other change requires a new sealed manifest and owner acknowledgment.

Campaign execution is **prohibited** until this manifest is sealed and recorded.

---

## 4. Allowed mutations (mechanical allow-list)

Only the following, when named in the freeze manifest and the relevant gate runbook step:

### 4.1 Broker reads — side-effect-free requirement

Account-3 broker account / position / order-status **reads** may be listed only when a
gate step explicitly requires them.

**Additional rule:** Every broker read must be:

1. **declared** in the freeze manifest;
2. **account-3 scoped**;
3. **proven not to mutate** application credential metadata, risk state, broker state, or
   account state.

A read path with incidental metadata writes is **prohibited** unless those writes are
separately enumerated as account-3 **test-state** writes and accepted under CORR-06.

This prevents a nominal “read” from bypassing the mutation boundary.

### 4.2 Other allowed reads

| Read | Notes |
|------|-------|
| Market-data / quote reads for WP9 provenance and replay inputs | Structured provenance required for binding use |
| Local DB / checkpoint / test-state reads for account 3 | |
| Sealed offline baseline artifacts at `d1c2fbf` | |
| Pre-existing sealed Tier-A live-fill evidence (O5 anchors only) | See §5 — not newly generated under D-BOX |

### 4.3 Allowed writes

| Write | Notes |
|-------|-------|
| Account-3-scoped **checkpoint** writes (WP3 binding tuple) | Test/campaign state only |
| Account-3-scoped **test-state** writes needed for O1–O5 / CORR-06 | Enumerate in freeze manifest; no production book mutation outside named test state |
| Evidence seal outputs (WP0 procedure) | Seal record + content hash required |
| Repo manifests + S3 uploads of raw evidence | S3 objects Version-ID + SHA-256 pinned |

### 4.4 Forbidden (non-exhaustive; fail closed)

- Broker **order** submission / cancel-replace that places risk
- Generating **new** live fills for O5 or any other gate
- Production OrderRouter Phase-0 submit path
- Merging Phase-0 imports into production order / risk / startup modules
- ENFORCE, cap changes, July 24 limits-digest edits
- Cross-account writes; account-1 credential-metadata mutation
- Undeclared broker reads or reads with incidental metadata mutation
- Dataset/threshold changes after manifest unseal (except one WP5 replacement + relock)

---

## 5. O5 live-fill anchor (without authorizing orders)

O5 remains required. D-BOX **prohibits** broker order submission and does **not**
authorize generating new live fills.

**O5 may use only pre-existing, sealed Tier-A live-fill evidence** whose provenance and
execution-path equivalence are **accepted before campaign evaluation** and bound in the
pre-campaign freeze manifest (§3).

- If adequate anchors **do not exist**, O5 closes **INCONCLUSIVE**.
- Broker submission remains **HOLD**.
- O5 requirements must **never** be read as implicit order-submission authorization.

---

## 6. Gate package matrix

Each row is a **separate sealed package** with its own manifest, pass criteria, and
APPROVE / REJECT / INCONCLUSIVE disposition.

| Package | Gate meaning (controlling) | Load-bearing? | Primary seams | Pass sketch |
|---------|----------------------------|---------------|---------------|-------------|
| **CORR-06 exit** | Account isolation before O1/O2 on box | **Yes** | `phase0_account_isolation` | Account-3-only ops; refuse cross-account; zero acct-1 credential-metadata mutation; side-effect-free reads proven |
| **O1** | Contract / structural conformance | **Yes** | WP1, WP3, CORR-06, ExecutionContext shape, router-only invariant (structural — no production wire) | Complete plan/context; lifecycle; max-leg reservation contract in harness; checkpoint tuple; terminal-package paths |
| **O2** | Deterministic unit / property tests | **Yes** | WP1–WP4, WP8 | Mutation/expiry/reduction-only; timestamp integrity; checkpoint tamper refuse; loss reconcile; crash transitions; proof of no cap/digest mutation |
| **O3** | Historical replay / backtest | **Yes** (unless controlling design explicitly provides a narrower adjudication) | WP1–WP4, WP8, WP9 + historical observations | Replay integrated plan/quote/authority/loss/checkpoint/recovery; false-reachable scoring; model coverage recorded |
| **O4-A** | Decision-time replay | **Yes** | WP7 + WP2 + WP9 (pre-submit evidence only) | `INDETERMINATE` + `INSUFFICIENT_EXECUTION_COST` (or `MODEL_UNAVAILABLE`); no fill look-ahead |
| **O4-B** | Forensic replay | **Yes** | WP7 + fills/WP8 | `UNREACHABLE_WITHIN_CAPS`; both O4-A and O4-B required; no mixing |
| **O5** | Shadow-session validation | **Yes** | WP5, WP6 + read-only seams + **pre-existing** Tier-A fill anchors only | Floors/CP/independence; **no new broker orders**; INCONCLUSIVE if anchors inadequate |

Option A properties may appear inside O1/O2 packages. $3,000 threshold Option C behavior,
if in scope, must be an explicitly named O2/O3 sub-protocol — still **without** broker
order submission.

WP3/WP4 evidence is primarily O1/O2 and may be exercised again in O3/O5; it does not
replace O3’s historical-replay purpose.

---

## 7. Evidence packaging (hybrid)

| Store | Contents |
|-------|----------|
| Git | Gate manifests, schemas, decision records, hashes, summaries, verify scripts, freeze manifest |
| S3 | Raw logs, replay datasets, broker **read** payloads (if any), seal blobs, pre-existing Tier-A fill archives |
| Binding | Manifest pins S3 **Version ID** + SHA-256; fail closed on mismatch; no “latest” |

Each gate package must include: controlling-design ID, integration-design ID, offline
baseline commit, campaign ID, freeze-manifest hash, account ID (=3), start/end
timestamps, tool/commit identities used on the box, and disposition.

---

## 8. Adjudication and exit criteria (fail-closed)

1. Seal pre-campaign freeze manifest (§3).
2. Run packages in logical order: **CORR-06 → O1 → O2 → O3 → O4-A → O4-B → O5**
   (O4-A/O4-B may be adjacent; both required for Gate O4).
3. Owner (or designated reviewer) records **APPROVE / REJECT / INCONCLUSIVE** per package.
4. **D-WIRE eligibility (fail-closed):** requires **APPROVE on every load-bearing required
   package**. Load-bearing at minimum: **CORR-06, O1, O2, O3, O4-A, O4-B, and O5**
   (O3 remains load-bearing unless the controlling design explicitly provides a narrower
   adjudication recorded before campaign start in the freeze manifest).
5. A **partial-acceptance ruling** may authorize only explicitly **non-load-bearing**
   follow-up **design** work. It may **not** grant production imports, D-WIRE, or any
   runtime authority while any load-bearing gate is **REJECT** or unresolved
   **INCONCLUSIVE**.
6. REJECT or unresolved INCONCLUSIVE on a load-bearing package → **D-WIRE stays deferred**.

---

## 9. Explicit non-goals

- Not a canary
- Not a HOLD lift for broker submission
- Not production integration (D-WIRE)
- Not ENFORCE / caps / limits-digest change
- Not authorization to generate new live fills for O5
- Not a claim that hermetic CI tests at `d1c2fbf` satisfy O1–O5

---

## 10. Parallel D-WIRE draft policy

A D-WIRE **design draft** may be written in parallel for review. It must remain
non-operative and must not be granted or implemented until §8 exit criteria are met.

Expected D-WIRE posture when eventually considered (informative only):

- default `DISABLED`;
- `OBSERVE_ONLY` first in deployed path;
- no broker submission;
- no `PREFLIGHT_REFUSE` unless explicitly included;
- rollback and reconciliation controls required.

---

## 11. Disposition

**CAMPAIGN SCOPE v1.0 — EXECUTE ONLY UNDER EFFECTIVE D-BOX — HOLD UNCHANGED.**

No broker orders, production imports, deployed-path observation, canary, ENFORCE, cap
changes, or July 24 limits-digest changes.

*End of ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.0.*
