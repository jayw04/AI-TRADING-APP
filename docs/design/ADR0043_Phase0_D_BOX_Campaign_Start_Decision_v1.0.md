# Owner Decision — D-BOX Partial Structural Campaign Start (Option 2A)

| Field | Value |
|-------|-------|
| Ruling ID | ADR0043-PH0-D-BOX-START-001 |
| Decision | **PROPOSED — NOT EFFECTIVE** (pending owner signature to authorize start) |
| Scope | Partial structural packages only: **CORR-06 → O1 → O2** |
| Bound freeze manifest | ADR0043-PH0-D-BOX-FREEZE-MANIFEST-002 |
| Sealed artifact | `docs/design/ADR0043_Phase0_D_BOX_Freeze_Manifest_002_SEALED.json` |
| Canonical body SHA-256 | `d35de863e85153f8f1a4768b62b7d89a2043525433ec8841631cb8a7c20a2d1f` |
| Sealed at (UTC) | `2026-07-29T23:44:13Z` |
| Campaign | ADR0043-PH0-D-BOX-CAMPAIGN-001 v1.1 (Option 2A) |
| Campaign label | **PARTIAL STRUCTURAL CAMPAIGN ONLY — NO D-WIRE ELIGIBILITY — O3/O4/O5 DEFERRED** |
| Freeze tooling tip | `b6836eb5718ab20a7799bb261f3eea3e4054b11f` |
| Campaign merge | `709e6136900d1e5e22bb0c074dc90ea35cadf22b` |
| Status | **HOLD ON START** until this ruling is signed EFFECTIVE |

---

## 1. Purpose

This is the **separate** owner start decision required after seal of FREEZE-MANIFEST-002.
Sealing proved readiness. **Sealing did not authorize execution.**

When made **EFFECTIVE** by owner signature, this ruling authorizes **only**:

1. **CORR-06** exit package  
2. **O1** structural conformance package  
3. **O2** deterministic unit/property package  

in that order, under CAMPAIGN-001 v1.1 and the sealed freeze identity above.

---

## 2. Explicitly not authorized (even after this start is EFFECTIVE)

| Item | Status |
|------|--------|
| O3 / O4-A / O4-B / O5 execution | **Not authorized** (predetermined INCONCLUSIVE / deferred) |
| Broker order submission / new live fills | **HOLD** |
| Production imports / deployed-path `OBSERVE_ONLY` | **Not authorized** |
| D-WIRE | **Blocked** |
| Canary / ENFORCE / caps / July 24 limits-digest changes | **Not authorized** |

---

## 3. Binding rule

Any start authorization is void unless the running freeze artifact’s `seal.body_sha256`
equals:

`d35de863e85153f8f1a4768b62b7d89a2043525433ec8841631cb8a7c20a2d1f`

and `verify-seal` exits 0.

---

## 4. Signature block

| Field | Value |
|-------|-------|
| Approving role | Owner |
| Decision when signed | **APPROVED / EFFECTIVE** for Option 2A start only |
| Sign-off | ________________ |
| Effective date (UTC) | ________________ |

Until signed, campaign start remains **HOLD**.

*End of ADR0043-PH0-D-BOX-START-001 (PROPOSED).*
