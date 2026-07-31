# ADR-0043 Phase-0 D-BOX Evidence Campaign Scope

| Field | Value |
|-------|-------|
| Document ID | ADR0043-PH0-D-BOX-CAMPAIGN-001 **v1.2** |
| Status | **DRAFT FOR SUCCESSOR O3/O4 CAMPAIGN — contingent on sealed FREEZE-MANIFEST-003 + separate owner start** |
| Freeze date | 2026-07-30 |
| Supersedes | ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.1 (Option 2A) for **executable package set only** |
| Amendment reason | QUALIFIED O3/O4-A/O4-B candidate archives exist (QUAL-001); reintroduce those gates without reopening Option 2A in place |
| Campaign label | **O3/O4-A/O4-B EXECUTION CAMPAIGN — O5 DEFERRED — NO D-WIRE ELIGIBILITY** |
| Authorization ruling | ADR0043-PH0-D-BOX-001 (HOLD / D-WIRE deferred unchanged) |
| Integration design | ADR0043-PH0-INTEGRATION-DESIGN-001 v1.0 |
| Controlling design | ADR0043-PH0-CTRL-001 v1.1 |
| Offline baseline | `d1c2fbf0a394c66728f6cc489577ae180ccdfb03` |
| Successor freeze manifest | ADR0043-PH0-D-BOX-FREEZE-MANIFEST-003 |
| Prior freeze manifest | ADR0043-PH0-D-BOX-FREEZE-MANIFEST-002 (**SEALED** body `d35de863…`) — **not modified in place** |
| Qualification | ADR0043-PH0-D-BOX-O34-ACQ-QUAL-001 **QUALIFIED** (merge `646d81abfdd98ce4ca99dde7821a26e869a50824`) |
| Construction | ADR0043-PH0-D-BOX-O34-ACQ-CONSTRUCT-001 (merge `5def3824937b85e859345f6691f2cb37b432105f`) |
| Account | **3 only** (`PA34USW0Q8UO`) |
| Broker order submission | **HOLD — not in scope** |
| D-WIRE | **Blocked** — O5 deferred (`anchors: []`); all-PASS on O3/O4-A/O4-B **does not** grant D-WIRE |

This scope enumerates the **successor** isolated evidence campaign under D-BOX. It does **not**
reopen CAMPAIGN-001 v1.1 / Option 2A in place. Execution of O3 → O4-A → O4-B must not begin
until FREEZE-MANIFEST-003 is sealed **and** a separate owner start decision is issued.

---

## 0. Inherited APPROVE packages (binding)

CORR-06, O1, and O2 remain **APPROVE** from Option 2A. They are **inherited**, not re-run.

| Package | Disposition | Binding |
|---------|-------------|---------|
| CORR-06 | **INHERITED APPROVE** | Option 2A evidence merge `5cb711c5be35d53c3d42277adbd0dc379dead44c`; FREEZE-002 body `d35de863e85153f8f1a4768b62b7d89a2043525433ec8841631cb8a7c20a2d1f`; close-out ADR0043-PH0-D-BOX-OPTION2A-CLOSE-001 |
| O1 | **INHERITED APPROVE** | same |
| O2 | **INHERITED APPROVE** | same |

Inherited APPROVE packages are **not** rerun, reopened, or re-adjudicated under v1.2 unless a
**separate owner ruling** explicitly orders it.

---

## 1. Campaign objective (v1.2)

**O3/O4-A/O4-B EXECUTION CAMPAIGN — O5 DEFERRED — NO D-WIRE ELIGIBILITY**

Executable packages (after seal + start), in order:

1. **O3** historical replay against QUALIFIED O3 archive  
2. **O4-A** decision-time replay against QUALIFIED O4-A archive  
3. **O4-B** forensic replay against QUALIFIED O4-B archive  

### Deferred / predetermined

| Package | Disposition under v1.2 |
|---------|-------------------------|
| **O5** | **DEFERRED / INCONCLUSIVE** — `anchors: []`; no qualified Tier-A anchors; generating new live fills **forbidden** |
| CORR-06 / O1 / O2 | **INHERITED APPROVE** (not executable in v1.2) |

### D-WIRE fail-closed posture

Even if O3, O4-A, and O4-B all **PASS**, **D-WIRE remains BLOCKED** while O5 is deferred with
`anchors: []`. Load-bearing O5 evidence is incomplete. No all-PASS on O3/O4 creates D-WIRE,
production imports, deployed-path observation, canary, ENFORCE, caps, or July 24 limits-digest
changes.

---

## 2. Environment and isolation

| Constraint | Requirement |
|------------|-------------|
| Runtime | **Isolated harness only** |
| Production OrderRouter Phase-0 submit | **Not in scope** |
| Production path imports | **Forbidden** |
| Phase-0 mode | `DISABLED` or `OBSERVE_ONLY_ISOLATED_HARNESS` only |
| Deployed production `OBSERVE_ONLY` | **Out of scope** (D-WIRE) |
| Production paper stack `b0058bf` | **Reference-only — do not modify** |
| Account | **3 only** |
| Account-1 credential metadata | Zero mutation |

---

## 3. QUALIFIED archive inputs (immutable)

Bound from QUAL-001 / CONSTRUCT-001 (must match FREEZE-003 `datasets.entries`):

| Archive | Archive ID | SHA-256 | Size | Counts |
|---------|------------|---------|------|--------|
| O3 | `O3-CAND-20260730T022316Z` | `53b3310c8db3cdfd3d60a2de3bec990a6eaab8864dd592afc4590e57fc9008b0` | 164706 | n=292 / plans=292 / clusters=20 |
| O4-A | `O4A-CAND-20260730T022316Z` | `3ba73e61f5e8955a184d820c0aba4ed387de453c30fc6a22d168d84074403c49` | 190328 | n=287 / plans=287 |
| O4-B | `O4B-CAND-20260730T022316Z` | `e349f49465aa2689e6c24e20d6ae32286f0a447bfbcdf3b2fbbc531c656bae95` | 260426 | n=286 / plans=286 / fills=286 |

Also bind: freeze ACQ body `80dfd8ec…`; sqlite snapshot `26bae1f5…`; construction merge
`5def382…`; qualification merge `646d81a…`; QUAL report identity.

Post-unseal substitution of archives is **FORBIDDEN**.

---

## 4. Harness input contract (`plan_id=ord:<orders.id>`)

QUALIFIED archives use episode identity:

```text
plan_id = "ord:" + str(orders.id)
```

because no `execution_plan` table exists in the bound sqlite snapshot. This mapping is an
**accepted harness input contract** for v1.2.

| Rule | Requirement |
|------|-------------|
| Acceptance | Gate harnesses MUST consume `ord:<positive_int>` deterministically via the bound adapter |
| Adapter | `apps/backend/app/risk/loss_control/phase0_o34_archive_adapter.py` (path+SHA pinned in FREEZE-003) |
| Readiness | FREEZE-003 readiness **FAILS** if the harness cannot consume the mapping deterministically |
| O4-A / O4-B | Adapter maps archive rows → `DecisionTimeEvidence` / `ForensicEvidence`; refuse look-ahead / mix |
| O3 | Adapter opens archive by hash and yields per-row replay bundles keyed by `ord:` IDs |
| Invention | Inventing new episode IDs or synthetic observations remains **FORBIDDEN** |

---

## 5. O4 no-mixing rule

O4-A and O4-B remain **separate** QUALIFIED archives. Harness or evaluator combining fields
from both into one evidence bundle must **refuse**. Episode linkage via shared `plan_id` /
`episode_id` is allowed in metadata; payload mixing is not.

---

## 6. Gate package matrix (v1.2)

| Package | In v1.2 execution scope? | Load-bearing for D-WIRE? | Disposition |
|---------|--------------------------|--------------------------|-------------|
| CORR-06 | **No — inherited** | Yes | **INHERITED APPROVE** |
| O1 | **No — inherited** | Yes | **INHERITED APPROVE** |
| O2 | **No — inherited** | Yes | **INHERITED APPROVE** |
| **O3** | **Yes** | Yes | Executable after start |
| **O4-A** | **Yes** | Yes | Executable after start |
| **O4-B** | **Yes** | Yes | Executable after start |
| **O5** | **No — deferred** | Yes (blocking) | **INCONCLUSIVE** (`anchors: []`) |

---

## 7. Pre-campaign freeze and start

1. Populate and readiness-check **FREEZE-MANIFEST-003**.  
2. Seal + countersign FREEZE-003 (readiness exit 0).  
3. Separate owner **start decision** (sealing ≠ start).  
4. If started, execute **only**: **O3 → O4-A → O4-B**.  
5. Record O5 predetermined INCONCLUSIVE.  
6. D-WIRE remains **BLOCKED**.

---

## 8. Allowed mutations / HOLD

Broker reads default empty unless separately declared side-effect-free. Writes limited to
account-3 evidence seals needed for O3/O4 execution artifacts. Forbidden unchanged: new
orders, new live fills, production imports, ENFORCE, caps, July 24 digest mutation,
undeclared broker reads, deployed-path observation, canary.

---

## 9. Explicit non-goals

- Not a reopen of Option 2A / FREEZE-002 in place  
- Not re-adjudication of CORR-06/O1/O2  
- Not D-WIRE eligibility from O3/O4 PASS alone  
- Not authorization to generate Tier-A anchors or new live fills for O5  
- Not modification of production stack `b0058bf`

---

## 10. Disposition

**CAMPAIGN SCOPE v1.2 — O3/O4-A/O4-B ONLY; O5 DEFERRED; NO D-WIRE ELIGIBILITY.**

HOLD unchanged.

*End of ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.2.*
