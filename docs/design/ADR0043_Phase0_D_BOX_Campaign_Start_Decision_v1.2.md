# Owner Decision — D-BOX CAMPAIGN-001 v1.2 Start (O3 → O4-A → O4-B)

| Field | Value |
|-------|-------|
| Ruling ID | ADR0043-PH0-D-BOX-START-002 |
| Decision | **APPROVED / EFFECTIVE** |
| Scope | Executable packages only: **O3 → O4-A → O4-B** |
| Bound campaign | ADR0043-PH0-D-BOX-CAMPAIGN-001 **v1.2** |
| Campaign label | **O3/O4-A/O4-B EXECUTION CAMPAIGN — O5 DEFERRED — NO D-WIRE ELIGIBILITY** |
| Bound freeze manifest | ADR0043-PH0-D-BOX-FREEZE-MANIFEST-003 |
| Sealed artifact | `docs/design/ADR0043_Phase0_D_BOX_Freeze_Manifest_003_SEALED.json` |
| Canonical body SHA-256 | `b2e6090dfe26bd26fbf18a3eb1be02d7e69a49423559194b93e8a95d5d663270` |
| Sealed at (UTC) | `2026-07-30T16:45:54Z` |
| Seal publish merge | `99a8537f78ad758eef5f23f803ce9eff098e83b6` |
| Published scope content tip | `9b62abb98b8adbcf9713cee006201e45f3015deb` |
| Tip-rebind content commit | `141131782e812fc5a1ddb4b59d86fa7e6713e13d` |
| Tip-rebind merge | `4e3c799834e6abd420eda53ebb819dd9f1ce07b2` |
| Qualification merge | `646d81abfdd98ce4ca99dde7821a26e869a50824` |
| Prior Option 2A start | ADR0043-PH0-D-BOX-START-001 (CORR-06/O1/O2) — **closed / inherited** |
| Prior freeze | FREEZE-002 body `d35de863…` — **not mutated**; Option 2A evidence merge `5cb711c` |
| Status | **EFFECTIVE** — v1.2 start authorized for O3 → O4-A → O4-B only |
| Sign-off | Owner acknowledgment (Jay Wang) — typed governance acknowledgment |
| Effective date (UTC) | `2026-07-30T16:54:15Z` |
| Publication path | `docs/design/ADR0043_Phase0_D_BOX_Campaign_Start_Decision_v1.2.md` |

---

## 1. Purpose

This is the **separate** owner start decision required after seal of FREEZE-MANIFEST-003
(PR #564). Sealing proved readiness. **Sealing did not authorize execution**; this ruling
does, for CAMPAIGN-001 v1.2 only.

This ruling authorizes **only**, in order:

1. **O3** historical replay against QUALIFIED O3 archive  
2. **O4-A** decision-time replay against QUALIFIED O4-A archive  
3. **O4-B** forensic replay against QUALIFIED O4-B archive  

Each package must produce its own sealed evidence package and disposition of
**APPROVE**, **REJECT**, or **INCONCLUSIVE**.

---

## 2. Inherited packages (not executable under this ruling)

| Package | Disposition | Rule |
|---------|-------------|------|
| CORR-06 | **INHERITED APPROVE** (Option 2A) | Must **not** be rerun, reopened, or re-adjudicated |
| O1 | **INHERITED APPROVE** (Option 2A) | Must **not** be rerun, reopened, or re-adjudicated |
| O2 | **INHERITED APPROVE** (Option 2A) | Must **not** be rerun, reopened, or re-adjudicated |

Binding: Option 2A evidence merge `5cb711c5be35d53c3d42277adbd0dc379dead44c` and
FREEZE-002 body `d35de863e85153f8f1a4768b62b7d89a2043525433ec8841631cb8a7c20a2d1f`.
Reopen requires a **separate** owner ruling.

---

## 3. Binding rule (void-on-mismatch)

Any start authorization under this ruling is **void** unless:

1. The running freeze artifact is
   `docs/design/ADR0043_Phase0_D_BOX_Freeze_Manifest_003_SEALED.json`  
2. `verify-seal` exits 0  
3. `seal.body_sha256` equals exactly:

`b2e6090dfe26bd26fbf18a3eb1be02d7e69a49423559194b93e8a95d5d663270`

---

## 4. Mandatory opening controls (immediately before O3)

Before O3 begins, the operator **must** complete and record all of the following in a
v1.2 campaign opening record. **Any failure voids execution authority and returns the
campaign to HOLD.**

| # | Control | Pass criterion |
|---|---------|----------------|
| 1 | `verify-seal` on exact FREEZE-003 sealed artifact | exit 0 |
| 2 | Confirm body hash | equals `b2e6090d…` |
| 3 | Verify QUALIFIED archive hashes and sizes | O3 `53b3310c…` / 164706; O4-A `3ba73e61…` / 190328; O4-B `e349f494…` / 260426 |
| 4 | `ord:<orders.id>` adapter compatibility probe | `harness_can_consume_ord_mapping()` true; `parse_ord_plan_id("ord:1080")==1080` |
| 5 | Isolated-harness checkout + clean repository state | clean tree; not production stack |
| 6 | Production `b0058bf` | neither used nor modified — recorded |
| 7 | Opening record | command outputs and hashes retained under evidence root |

Opening record path (create at open):

`docs/design/evidence/dbox_campaign_v1_2_run_001/OPENING_RECORD_v1.0.md`
(and machine-readable companion JSON as needed)

---

## 5. Explicit non-effects (even if O3/O4-A/O4-B all APPROVE)

| Item | Status |
|------|--------|
| O5 | Remains **INCONCLUSIVE** (`anchors: []`) |
| D-WIRE | Remains **blocked** |
| Broker orders / new observations / new live fills | **Not authorized** |
| Production imports / deployed-path observation | **Not authorized** |
| Canary / ENFORCE / caps / July 24 limits-digest changes | **Not authorized** |
| Modification of production stack `b0058bf` | **Forbidden** |

Publication, merge, readiness, sealing, and this start ruling do **not** authorize
D-WIRE, production path observation, or broker submission.

---

## 6. Runtime

| Constraint | Requirement |
|------------|-------------|
| Runtime | **Isolated harness only** |
| Phase-0 modes | `DISABLED` or `OBSERVE_ONLY_ISOLATED_HARNESS` only |
| Account | **3 only** (`PA34USW0Q8UO`) |
| Production paper deploy `b0058bf` | Reference-only — do not use or modify |

---

## 7. Signature block

| Field | Value |
|-------|-------|
| Approving role | Owner |
| Decision | **APPROVED / EFFECTIVE** for O3 → O4-A → O4-B only |
| Bound body SHA-256 | `b2e6090dfe26bd26fbf18a3eb1be02d7e69a49423559194b93e8a95d5d663270` |
| Sign-off | Owner acknowledgment (Jay Wang) — typed governance acknowledgment |
| Effective date (UTC) | `2026-07-30T16:54:15Z` |

*End of ADR0043-PH0-D-BOX-START-002 (EFFECTIVE).*
