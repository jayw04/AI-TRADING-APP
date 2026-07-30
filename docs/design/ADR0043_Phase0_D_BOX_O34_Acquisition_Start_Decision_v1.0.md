# Owner Decision — O34 Construction Start

| Field | Value |
|-------|-------|
| Ruling ID | ADR0043-PH0-D-BOX-O34-ACQ-START-001 |
| Decision | **APPROVED / EFFECTIVE** |
| Scope | Snapshot capture, deterministic record selection, candidate archive construction, and independent qualification **only** |
| Bound construction freeze | ADR0043-PH0-D-BOX-O34-ACQ-FREEZE-001 |
| Sealed artifact | `docs/design/ADR0043_Phase0_D_BOX_O34_ACQ_Freeze_Manifest_001_SEALED.json` |
| Canonical body SHA-256 | `80dfd8ec6d90182cdeabaab2d1457720ca417bcd5cb1511b4dd9d77989951bb0` |
| Freeze publish merge | `a1f1fd3ccbd5f8209047d6e3f8663920abb0d04a` (PR #556) |
| Parent acquisition auth | ADR0043-PH0-D-BOX-O34-ACQ-AUTH-001 (EFFECTIVE, amended) |
| Design package | ADR0043-PH0-D-BOX-O34-EVIDENCE-ACQ-001 v1.0 |
| Option 2A evidence merge | `5cb711c5be35d53c3d42277adbd0dc379dead44c` |
| Sign-off | Owner acknowledgment (Jay Wang) — typed governance acknowledgment |
| Ruling date (UTC) | 2026-07-30 |
| Effective date (UTC) | 2026-07-30T02:10:51Z |
| Broker order submission | **HOLD — not lifted** |
| D-WIRE | **Blocked / not authorized** |
| Gate execution / campaign reopen | **Not authorized** |

---

## Ruling

The owner **APPROVES** ADR0043-PH0-D-BOX-O34-ACQ-START-001 for **snapshot capture,
deterministic record selection, archive construction, and independent qualification only**,
bound to O34-ACQ-FREEZE-001 body SHA-256
`80dfd8ec6d90182cdeabaab2d1457720ca417bcd5cb1511b4dd9d77989951bb0`.

---

## 1. Authorized (narrow)

| Step | Authorization |
|------|----------------|
| 1 | Capture **immutable snapshots** of sources declared in the sealed freeze |
| 2 | Compute and record exact file SHA-256 values, S3 Version IDs, sizes, timestamps, and source identities |
| 3 | Verify captured snapshots against sealed eligibility and source rules |
| 4 | Begin **deterministic record selection** only after every required source snapshot is successfully bound |
| 5 | Construct **candidate** O3, O4-A, and O4-B archives |
| 6 | Submit archives for **independent** qualification as `QUALIFIED`, `REJECTED_AS_NON-BINDABLE`, or `INCONCLUSIVE` |

---

## 2. Required start-time controls

**Before the first query, filter, join, or row inspection:**

1. Record the full sealed manifest body hash  
   `80dfd8ec6d90182cdeabaab2d1457720ca417bcd5cb1511b4dd9d77989951bb0`
2. Verify the seal successfully (JCS body-hash match + `manifest_status=SEALED`)
3. Capture the mutable-source snapshots
4. Record pre-capture and post-capture state hashes where applicable
5. Prove the capture process itself performed **no source mutation**
6. **Stop** if any required snapshot cannot be pinned exactly

Record selection begins only after all mandatory snapshot bindings pass.

---

## 3. Explicitly not authorized

| Item | Status |
|------|--------|
| Broker calls that create or mutate state | **Not authorized** |
| New orders, fills, sessions, or observations | **Not authorized** |
| O3 / O4 / O5 gate execution | **Not authorized** |
| Reopening the D-BOX campaign | **Not authorized** |
| Using constructed archives as gate inputs before qualification and a new campaign freeze | **Not authorized** |
| D-WIRE | **Blocked** |
| Production imports / deployed-path observation | **Not authorized** |
| Canary / ENFORCE / caps / July 24 limits-digest changes | **Not authorized** |

---

## 4. Binding rule

This start is void unless the sealed freeze artifact’s `seal.body_sha256` equals:

`80dfd8ec6d90182cdeabaab2d1457720ca417bcd5cb1511b4dd9d77989951bb0`

and seal verification succeeds.

---

## 5. Sequence after EFFECTIVE

1. Publish this ruling  
2. Capture source snapshots first (not selection)  
3. Bind snapshot identities in a construction-start capture record  
4. Only then: deterministic selection → CONSTRUCTED archives → independent qualification  

---

## 6. Signature block

| Field | Value |
|-------|-------|
| Approving role | Owner |
| Decision | **APPROVED / EFFECTIVE** — capture / select / construct / qualify only |
| Sign-off | Owner acknowledgment (Jay Wang) — typed governance acknowledgment |
| Effective date (UTC) | 2026-07-30T02:10:51Z |

*End of ADR0043-PH0-D-BOX-O34-ACQ-START-001 (EFFECTIVE).*
