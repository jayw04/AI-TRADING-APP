# Owner Decision — Authorize O3/O4 Evidence Acquisition (Amended)

| Field | Value |
|-------|-------|
| Ruling ID | ADR0043-PH0-D-BOX-O34-ACQ-AUTH-001 |
| Decision | **APPROVED / EFFECTIVE** |
| Scope | **Construction and qualification only** of candidate O3 / O4-A / O4-B archives |
| Ruling date (UTC) | 2026-07-30 |
| Sign-off | Owner acknowledgment (Jay Wang) — typed governance acknowledgment |
| Effective date (UTC) | 2026-07-30T00:21:33Z |
| Parent close-out | ADR0043-PH0-D-BOX-OPTION2A-CLOSE-001 |
| Option 2A evidence merge | `5cb711c5be35d53c3d42277adbd0dc379dead44c` |
| Design package | ADR0043-PH0-D-BOX-O34-EVIDENCE-ACQ-001 **v1.0** |
| Construction freeze manifest | ADR0043-PH0-D-BOX-O34-ACQ-FREEZE-001 |
| PR | [#555](https://github.com/jayw04/AI-TRADING-APP/pull/555) (final content commit after this amendment) |
| Broker order submission | **HOLD — not lifted** |
| Gate execution / reopening | **Not authorized** |
| D-WIRE | **Blocked / not authorized** |
| Supersedes | `ADR0043_Phase0_D_BOX_O34_Acquisition_Authorization_v0.1.md` (PROPOSED draft) |

---

## Ruling

The owner **APPROVES** O34 evidence acquisition for **construction and qualification only**,
subject to a **sealed construction freeze manifest** (ADR0043-PH0-D-BOX-O34-ACQ-FREEZE-001).

This authorization permits **deterministic** creation of **candidate** O3, O4-A, and O4-B
archives from **pre-existing governed records**. It does **not** authorize new observations,
broker orders, live fills, gate execution, gate reopening, D-WIRE, production imports, or
designation of an archive as gate-ready without a separate **QUALIFIED** record and a
**subsequent campaign amendment**.

---

## 1. Mechanical allow-list (what “construction” may use)

### 1.1 Permitted

| Class | Notes |
|-------|-------|
| Historical market and quote data already lawfully available | Bound by construction freeze source inventories / snapshots |
| Existing application audit, plan, checkpoint, and terminal records | Pre-existing only |
| Account-3 paper records already created under prior authority | Account **3** only |
| Deterministic transformations, joins, normalization, classification, archive packaging | Must be enumerated in the construction freeze |
| Read-only broker history | Only when **separately declared** and **proven side-effect-free** |

### 1.2 Prohibited

| Class | Status |
|-------|--------|
| Generating new orders, fills, attempts, or sessions | **Prohibited** |
| Changing historical records | **Prohibited** |
| Manufacturing observations to satisfy sample size | **Prohibited** |
| Converting unit-test fixtures or synthetic examples into empirical observations | **Prohibited** |
| Silently importing evidence from another research program | **Prohibited** |

---

## 2. Construction freeze before outcome inspection

**Before any records are selected**, ADR0043-PH0-D-BOX-O34-ACQ-FREEZE-001 must be sealed and
must contain at least:

| Required field | Purpose |
|----------------|---------|
| Source inventories and exact snapshots | Pin what may be read |
| Eligibility window | UTC bounds |
| Inclusion and exclusion rules | Selection logic |
| Deduplication key | Identity of one observation |
| Unit of observation | Plan / episode / session definition |
| Symbol/session clustering rule | Dependence handling |
| O4-A cutoff rule | First-submission / decision-time boundary |
| O4-B terminal-completeness rule | What makes a forensic observation complete |
| Missing-data treatment | Fail-closed vs drop with reason codes |
| Target archive schemas | O3 / O4-A / O4-B |
| Permitted transformations | Deterministic only |
| Expected count reconciliation | Planned accounting before selection |

No rule may be changed after outcome inspection without a **superseding** construction
freeze manifest and **owner acknowledgment**.

---

## 3. Construction vs qualification (separate outcomes)

Construction may produce **candidate** archives. It does **not** automatically make them
binding or gate-ready.

| Outcome | Meaning |
|---------|---------|
| **CONSTRUCTED** | Candidate archive bytes + hashes exist under construction rules |
| **QUALIFIED** | Independent qualification report proves bindability (below) |
| **REJECTED_AS_NON-BINDABLE** | Failed qualification or stop condition |

### 3.1 Qualification report must prove

1. Complete provenance  
2. No O4-A look-ahead  
3. No O4-A / O4-B evidence mixing  
4. Reproducible source-to-archive row lineage  
5. Count reconciliation  
6. Hash and schema validation  
7. No prohibited synthetic or cross-program substitution  

**Only a later campaign amendment** may bind a **QUALIFIED** archive as an O3 or O4 input.

---

## 4. Stop conditions

Construction must **stop** and close **INCONCLUSIVE**, or require amendment, when:

| Condition |
|-----------|
| Required source snapshot is unavailable |
| Provenance cannot be proven |
| Decision-time cutoff cannot be reconstructed |
| Terminal completeness cannot be established |
| Deduplication is ambiguous |
| Source records were modified after the bound snapshot |
| Construction would require broker calls beyond authorized reads |
| Sample sufficiency would require generating new observations |

---

## 5. Explicitly not authorized

| Item | Status |
|------|--------|
| Broker order submission | **HOLD** |
| New live fills / new observations / new sessions | **Not authorized** |
| O3 / O4 / O5 gate package execution as PASS attempts | **Not authorized** |
| Declaring CONSTRUCTED archives gate-ready without QUALIFIED + campaign amendment | **Prohibited** |
| D-WIRE / production imports / deployed-path observation | **Not authorized** |
| Canary / ENFORCE / caps / July 24 limits-digest changes | **Not authorized** |

---

## 6. Binding identities

| Identity | Value |
|-----------|-------|
| Option 2A evidence merge | `5cb711c5be35d53c3d42277adbd0dc379dead44c` |
| Design package | ADR0043-PH0-D-BOX-O34-EVIDENCE-ACQ-001 v1.0 |
| Construction freeze ID | ADR0043-PH0-D-BOX-O34-ACQ-FREEZE-001 |
| PR #555 final content commit | *(bound in follow-up publication pin)* |

---

## 7. Signature block

| Field | Value |
|-------|-------|
| Approving role | Owner |
| Decision | **APPROVED / EFFECTIVE** — construction + qualification only |
| Sign-off | Owner acknowledgment (Jay Wang) — typed governance acknowledgment |
| Effective date (UTC) | 2026-07-30T00:21:33Z |

*End of ADR0043-PH0-D-BOX-O34-ACQ-AUTH-001 (EFFECTIVE, amended).*
