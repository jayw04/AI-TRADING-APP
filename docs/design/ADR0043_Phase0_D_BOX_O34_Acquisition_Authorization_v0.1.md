# Owner Decision Draft — Authorize O3/O4 Evidence Acquisition

| Field | Value |
|-------|-------|
| Ruling ID | ADR0043-PH0-D-BOX-O34-ACQ-AUTH-001 |
| Decision | **PROPOSED — NOT EFFECTIVE** (pending owner signature) |
| Scope | Authorize **construction only** of bindable O3 corpus + O4-A/O4-B observation sets per ADR0043-PH0-D-BOX-O34-EVIDENCE-ACQ-001 v1.0 |
| Parent | Option 2A close-out ADR0043-PH0-D-BOX-OPTION2A-CLOSE-001 |
| Design package | `docs/design/ADR0043_Phase0_D_BOX_O34_Evidence_Acquisition_v1.0.md` |
| Broker order submission | **HOLD — not lifted** |
| New live fills | **Not authorized** |
| D-WIRE / D-BOX gate re-open | **Not authorized** by this ruling alone |
| Status | **LOCAL DRAFT — not effective until owner signature and governed publication** |

---

## 1. Why this is next

Option 2A closed with CORR-06/O1/O2 **APPROVE** and O3/O4/O5 **INCONCLUSIVE** because no
pre-existing bindable corpora existed. D-WIRE remains blocked until those identities exist
and a later campaign reopens those gates.

This ruling would authorize **evidence construction work only** — not campaign execution of
O3/O4/O5, not broker orders, and not D-WIRE.

---

## 2. Authorized when EFFECTIVE

1. Implement construction tooling / procedures under O34-EVIDENCE-ACQ-001 rules  
2. Freeze eligibility windows, sampling, exclusions, and O4-A decision-time cutoff **before** packing  
3. Produce sealed archives with path/S3 Version ID, size, SHA-256, provenance, counts  
4. Keep O4-A free of fill/terminal look-ahead; keep O4-B as a separate archive  
5. Record construction in governed evidence manifests (Git + S3 pins)

---

## 3. Explicitly not authorized

| Item | Status |
|------|--------|
| Broker order submission | **HOLD** |
| Generating new live fills (including for O5) | **Not authorized** |
| Running O3/O4/O5 gate packages as campaign PASS attempts | **Not authorized** until a new campaign scope + freeze bind the archives |
| D-WIRE / production imports / deployed-path observation | **Not authorized** |
| Canary / ENFORCE / caps / July 24 digest changes | **Not authorized** |
| Inventing temporary observation-set IDs to force a seal | **Prohibited** |

---

## 4. Signature block

| Field | Value |
|-------|-------|
| Approving role | Owner |
| Decision when signed | **APPROVED / EFFECTIVE** for O34 construction only |
| Sign-off | ________________ |
| Effective date (UTC) | ________________ |

Until signed, O34 acquisition remains **design-only**.

*End of ADR0043-PH0-D-BOX-O34-ACQ-AUTH-001 (PROPOSED).*
