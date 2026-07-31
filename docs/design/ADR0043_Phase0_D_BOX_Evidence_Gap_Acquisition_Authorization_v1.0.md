# Owner Decision — Authorize Evidence-Gap Acquisition Program

| Field | Value |
|-------|-------|
| Ruling ID | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-AUTH-001 |
| Decision | **APPROVED / EFFECTIVE** |
| Scope | Evidence-gap **acquisition program** for O3 / O4-A / O4-B recovery surfaces and O5 **locate-only** Tier-A anchors |
| Ruling date (UTC) | 2026-07-30 |
| Sign-off | Owner acknowledgment (Jay Wang) — typed governance acknowledgment |
| Effective upon | Publication merge of this record on `main` |
| Parent design | ADR0043-PH0-D-BOX-EVIDENCE-GAP-001 **v1.0** |
| Design merge (binding) | `71d346d8bd5665a3037d451ec4118f70431b69df` (PR #570) |
| Parent close-out | ADR0043-PH0-D-BOX-V12-CLOSE-001 **EFFECTIVE** (`4232c1a`) |
| Closed campaign | ADR0043-PH0-D-BOX-CAMPAIGN-001 **v1.2** — **not reopened** |
| Closed freeze | FREEZE-MANIFEST-003 body `b2e6090dfe26bd26fbf18a3eb1be02d7e69a49423559194b93e8a95d5d663270` — **immutable; not mutated** |
| Closed start | START-002 — **exhausted; no remaining execution authority** |
| Bound acquisition freeze (required next) | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-FREEZE-001 |
| Broker order submission | **HOLD — not lifted** |
| Gate execution / reopening | **Not authorized** |
| D-WIRE | **Blocked / not authorized** |
| Production / `b0058bf` | **Reference-only — do not use or modify** |

---

## Ruling

The owner **APPROVES** ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-AUTH-001 for the
evidence-gap **acquisition program**, subject to a **new sealed acquisition freeze**
(ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-FREEZE-001) **before** any source selection,
reconstruction, capture, or inspection for selection purposes.

This authorization is bound to EVIDENCE-GAP-001 v1.0 and PR #570 merge
`71d346d8bd5665a3037d451ec4118f70431b69df`.

**This authorization alone does not permit evidence access.** No source inventory
inspection for selection, reconstruction, capture, or packaging may begin until:

1. EVIDENCE-GAP-ACQ-FREEZE-001 is **sealed and countersigned**, and  
2. A **separate** acquisition-start decision is **EFFECTIVE**.

---

## 1. Authorized scope (program envelope)

Subject to the sealed freeze and separate start, the program **may** cover:

| Activity | Notes |
|----------|-------|
| Locate and inventory pre-existing account-3 evidence sources | Read-only; exact systems/snapshots pinned in freeze before seal |
| Determine whether missing O3, O4-A, and O4-B surfaces are reproducibly recoverable | Deterministic recovery only (§3) |
| Locate pre-existing sealed Tier-A O5 anchors | Locate + qualify only (§5) |
| Prepare deterministic extraction and packaging tooling | Tooling + commit identities pinned before seal |
| Construct and independently qualify **new** candidate archives | Only **after** freeze seal + acquisition-start; new archive IDs only |

### 1.1 Required sequence

1. Draft this acquisition authorization (**this document — EFFECTIVE**).  
2. Draft EVIDENCE-GAP-ACQ-FREEZE-001 (UNSEALED).  
3. Before sealing, bind all §2 required fields (no placeholders).  
4. Readiness check.  
5. Seal and countersign the acquisition freeze.  
6. Issue a **separate** acquisition-start decision.  
7. Perform acquisition / construction under the sealed freeze.  
8. Independently qualify each **new** archive.  
9. Only afterward consider a **new** campaign scope, campaign freeze, and gate-start.

FREEZE-003 QUALIFIED archives remain **immutable historical evidence**. They must not be
enriched or overwritten.

---

## 2. Acquisition freeze — mandatory pre-seal bindings

Before seal of ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-FREEZE-001, the freeze **must** bind:

| Binding | Purpose |
|---------|---------|
| Exact source systems and immutable snapshots (or capture-at-start protocol) | Pin what may be read |
| Source-field-to-target-surface mappings | O3 / O4-A / O4-B gap surfaces from EVIDENCE-GAP-001 §§4–6 |
| Eligibility window | UTC bounds before selection |
| Account-3 identity | workbench `3` / Alpaca paper `PA34USW0Q8UO` |
| Reconstruction rules and prohibited inference | §3 recovery vs fabrication |
| Completeness criteria | QUALIFIED eligibility bars |
| Exclusion reason codes | Fail-closed incomplete rows |
| Archive schemas | New O3 / O4-A / O4-B (and O5 locate package if any) |
| Expected count reconciliation | Planned accounting before selection |
| O4-A cutoff and O4-A / O4-B no-mix controls | No look-ahead; separate archives |
| O5 locate-only rules | §5 |
| Tooling and commit identities | Deterministic extractors / packagers |

No rule may be changed after outcome inspection without a **superseding** freeze and
**owner acknowledgment**.

---

## 3. Critical scope distinction — recovery vs fabrication

### 3.1 Permitted recovery

Deterministic extraction or reconstruction from records that:

1. **Already existed** at the frozen source cutoff, and  
2. Whose **provenance can be proven** under freeze-bound lineage.

Includes joins, normalization, classification, and packaging enumerated in the freeze.

### 3.2 Prohibited fabrication

| Prohibited | Status |
|------------|--------|
| Synthesizing quotes, checkpoints, loss inputs, recovery state, or `day_change` from assumptions | **Prohibited** |
| Using later market data as if it were decision-time | **Prohibited** |
| Importing O4-B data into O4-A (or any O4-A/O4-B mix) | **Prohibited** |
| Filling missing surfaces from evaluator defaults | **Prohibited** |
| Manufacturing observations to satisfy sample size | **Prohibited** |

### 3.3 Prospective collection of newly occurring observations

**Outside** this initial authorization. Creating a new evidence population via deployed
instrumentation or live operational observation requires a **separate** instrumentation
and collection ruling (could affect deployed systems). Not authorized here.

---

## 4. Target gap surfaces (binding design reference)

Recovery targets remain those in EVIDENCE-GAP-001 v1.0:

| Package | Missing surfaces (v1.2 INCONCLUSIVE) |
|---------|--------------------------------------|
| O3 | `quote_provenance`, `checkpoint_tuple`, `loss_accounting_inputs`, `recovery_inputs` (complete set per observation) |
| O4-A | Two-sided decision-time quotes at/before first-submission cutoff; `model_available` |
| O4-B | Forensic baseline (`day_change` or freeze-accepted equivalent) with fills/terminal completeness |
| O5 | Pre-existing Tier-A live-fill anchors only (§5) |

Episode identity default: `plan_id=ord:<orders.id>` unless a superseding contract is freeze-bound
and readiness fails closed without it.

---

## 5. O5 boundary — locate and qualification only

| Item | Status |
|------|--------|
| Locate pre-existing sealed Tier-A anchors | **Authorized** (post freeze seal + start) |
| Qualify located anchors | **Authorized** (independent qualification) |
| New orders / generation of new fills | **Forbidden** |
| Shadow-session execution | **Forbidden** |
| Broker submission | **Forbidden** (HOLD) |
| Empty result | `anchors: []` remains **valid** if no qualifying pre-existing Tier-A evidence exists → O5 stays INCONCLUSIVE; D-WIRE blocked |

---

## 6. Construction vs qualification vs campaign

| Outcome | Meaning |
|---------|---------|
| **CONSTRUCTED** | New candidate archive bytes + hashes under freeze rules |
| **QUALIFIED** | Independent report proves bindability (provenance, no look-ahead, no-mix, lineage, counts, hash/schema, no fabrication) |
| **REJECTED_AS_NON-BINDABLE** / **INCONCLUSIVE** | Failed qualification or stop condition |

**Only a later campaign amendment** (new scope + campaign freeze + gate-start) may bind a
**QUALIFIED** archive as a gate input. This authorization does **not** reopen O3 / O4 / O5.

---

## 7. Stop conditions

Acquisition / construction must **stop** (INCONCLUSIVE or amendment required) when:

| Condition |
|-----------|
| Required source snapshot unavailable or unpinnable |
| Provenance cannot be proven |
| Decision-time cutoff cannot be reconstructed |
| Terminal / forensic completeness cannot be established without fabrication |
| Deduplication is ambiguous |
| Source records mutated after the bound snapshot |
| Work would require broker calls beyond authorized side-effect-free reads (if any are freeze-declared) |
| Sample sufficiency would require generating new observations |
| Gap surfaces would require prohibited inference (§3.2) |

---

## 8. Explicit non-effects

This authorization does **not**:

| Item | Status |
|------|--------|
| Reopen O3, O4, or O5 under FREEZE-003 / START-002 | **Not authorized** |
| Modify closed FREEZE-003 / QUAL-001 archives | **Forbidden** |
| Authorize production changes or use of `b0058bf` | **Forbidden** |
| Authorize broker activity / order submission | **HOLD** |
| Authorize D-WIRE, canary, ENFORCE, caps, or July 24 digest changes | **Not authorized** |
| Authorize evidence access before freeze seal + acquisition-start | **Forbidden** |
| Authorize gate execution | **Not authorized** |

---

## 9. Binding identities

| Identity | Value |
|----------|-------|
| Design package | ADR0043-PH0-D-BOX-EVIDENCE-GAP-001 v1.0 |
| Design merge | `71d346d8bd5665a3037d451ec4118f70431b69df` |
| Design PR | [#570](https://github.com/jayw04/AI-TRADING-APP/pull/570) |
| Close-out | V12-CLOSE-001 @ `4232c1a` |
| Acquisition freeze ID | ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-FREEZE-001 |
| Account 3 | workbench `3` / `PA34USW0Q8UO` paper |
| Offline baseline (reference) | `d1c2fbf` / `adr0043-phase0-offline-complete` |
| Production exclusion | `b0058bf` reference-only |

---

## 10. Signature block

| Field | Value |
|-------|-------|
| Approving role | Owner |
| Decision | **APPROVED / EFFECTIVE** — acquisition program; evidence access gated on sealed freeze + separate start |
| Sign-off | Owner acknowledgment (Jay Wang) — typed governance acknowledgment |
| Effective | Upon publication merge of this record |

*End of ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-AUTH-001.*
