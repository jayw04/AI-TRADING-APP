# MR-002 / SPQ-1 Development Plan — v1.2

> ⛔ **SUPERSEDED by** [`MR002_Development_Plan_Next_Phases_v1.3.md`](MR002_Development_Plan_Next_Phases_v1.3.md) (v1.3.1, 2026-08-09). **Never quote this document for status.** Its Phase 3A section states drafting is "NOT YET AUTHORIZED / not drafted", which was already untrue on its 2026-07-24 publication date — the Phase 3A package landed at `be8ab53` and the Phase 3B/C adjudication at `953bda9`, both 2026-07-22. See v1.3 §0. Retained as the Phase 2B completion record only.

**Program:** MR-002 — Sector-Neutral Residual Reversion · **Workstream:** SPQ-1  
**Date:** 2026-07-24  
**Type:** planning and governance record only — opens no validation/OOS data and authorizes no performance computation  
**Supersedes:** `MR002_Development_Plan_Next_Phases_v1.1.1.md` (erratum merged herein) and the status sections of `MR002_Development_Plan_Next_Phases_v1.1.md`  
**Companion:** `docs/review/mr002/MR002_Architecture_Review_v1.1.md` (platform integration; research-only until promotion)

---

## 0. What changed in v1.2

| Topic | v1.1.1 state | v1.2 state |
|---|---|---|
| Phase 2B | COMPLETE (pre–2B-3 closeout narrative) | **CLOSED** — Increments 2B-2 (clean post-amendment) + **2B-3 governance closeout** accepted |
| Identity collision | Amendment required (comments adjudication) | **Amendment `MR002_SPQ1_NONINJECTIVE_REQUEST_IDENTITY_V1` applied**; clean full run + deterministic replay **PASS** |
| Run specification | v1.0 halted mid-run | Governing **`RunSpecification_v1.1`** (`fd19aef5…`) |
| Terminal-key nomenclature | Ambiguous “resolved keys” field | **Clarified in 2B-3** — 375,728 accepted resolved permsec/session keys; 49,272 `UNRESOLVED:<symbol>` (no rerun required) |
| Governing prereg | v1.0.4 erratum (v1.1.1 §A–F) | **Retained and binding** (§5–§7) |
| Next authorized work | WP 3A drafting **NOT YET AUTHORIZED** | **Immediate target remains Phase 3A** — drafting still requires **separate authorization** |
| Architecture | Not cross-linked | **Aligned** with Architecture Review v1.1 (publication boundary, decision/execution seam, no duplicate product economics) |

Phases **3A through 8** retain the v1.1 design (amendments A1–A6, OOS consumption rule, product path). v1.2 updates **status, baseline identities, prereg pins, and authorization** only where progress required it.

---

## 1. Executive summary

SPQ-1 has completed **Phase 2B — deterministic development signal production** across the full **425,000** request-unit population. The workstream proved:

- Point-in-time governed signal production on the frozen development partition  
- Immutable publication discipline and deterministic replay (independent passes A + B)  
- Restart invariance and shard reconciliation  
- Governed **non-injective request-identity collision** handling (all-claimants-stop; no canonical winner)  
- **Zero** validation/OOS reads and **zero** performance interpretation  

Phase 2B establishes **machinery and evidence integrity only**. It does **not** establish profitability, statistical significance, portfolio utility, or production readiness.

**Next governed milestone:** **Phase 3A — Validation Authorization Package** — freeze the complete validation contract (including technical seal, conservative short model, enrichment edge cases, and v1.0.4 prereg pins) **before** any validation partition is opened.

---

## 2. Program governance state (2026-07-24)

| Item | Status |
|---|---|
| Stage-3 (MR-002 execution package) | **CLOSED** |
| Workstream B Increments 1–3 | **CLOSED** |
| OQ-1 | **CLOSED** |
| SPQ-1 Phase 0 specification package | **SUBMITTED** (formal Phase-0 closure **HELD** pending spec-package review) |
| SPQ-1 Phase 1 (synthetic implementation) | **CLOSED** |
| SPQ-1 Phase 2A (dev-data adapters) | **CLOSED** |
| SPQ-1 Phase 2B (full dev signal production) | **CLOSED** (2B-3 closeout) |
| Phase 3A validation authorization package | **NOT YET AUTHORIZED** |
| Validation partition access | **SEALED AND UNREAD** |
| OOS partition access | **SEALED AND UNREAD** |
| Performance / ranking / portfolio / execution | **NOT AUTHORIZED** |
| Production promotion | **NOT AUTHORIZED** |

---

## 3. Phase 2B completion record

### 3.1 Increment history

| Increment | Scope | Outcome |
|---|---|---|
| **2B-0 / 2B-1** | Run-spec materialization, shard qualification, partial runs | Qualification artifacts accepted; led to full-run authorization |
| **2B-2 (first attempt)** | Full development run | **HALTED** — non-injective request→permanent-security mapping detected (AGN/AGN1, CB/CB1, DD/DD1); fail-fast stop **correct**; shards **not** reusable |
| **2B-2 amendment** | `MR002_SPQ1_Phase2B_2B2_CollisionRuleAmendment_v1.1` | **APPROVED** — all-claimants `INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS`; terminal key `UNRESOLVED:<request_symbol>`; diagnostic retention of claimed permsec |
| **2B-2 (clean)** | Full run + independent replay pass B | **PASS** — 425,000/425,000 reconciled; determinism equal across passes |
| **2B-3** | Governance closeout only | **CLOSED** — acceptance gate all pass; no performance forward-return |

### 3.2 Final development census (both passes identical)

| Metric | Value |
|---|---:|
| Development sessions | 1,700 |
| Monthly shards | 82 |
| Request units | 425,000 |
| `SIGNAL_DECISION_RECORD_EMITTED` | 320,771 |
| `INELIGIBLE` | 40,457 |
| `INTEGRITY_STOP` | 50,399 |
| `REFUSED_CODE_OR_DATA_IDENTITY` | 13,373 |
| Missing / orphan outcomes | 0 |
| Duplicate request keys | 0 |
| Duplicate **accepted** resolved permsec/session keys | 0 |
| Collision groups | 35 |
| Collision-affected request units | 70 |
| Deterministic replay | **PASS** |
| Restart invariance | **PASS** |
| Validation/OOS reads | **0** |

**Terminal-code highlights:** `OLS_WINDOW_INSUFFICIENT` 25,149 · `SECURITY_IDENTITY_AMBIGUOUS` 50,399 (70 collision-caused + 50,329 single-request lineage) · `SIGNAL_INPUT_IDENTITY_MISMATCH` 13,373 · eligibility/sector PIT refusals as censused.

**Frozen interpretation (unchanged):**

> Phase 2B establishes deterministic, PIT-governed development signal production and evidence integrity only. It makes no claim regarding profitability, statistical significance, robustness, portfolio utility, or production readiness.

### 3.3 Bound governing identities (Phase 2B closeout)

| Artifact | Identity |
|---|---|
| Governing run specification | `RunSpecification_v1.1` · SHA-256 `fd19aef5230bac56bc82be1efb1be55ba3fe5d4f9daae33608f49ebbfd4554c3` |
| Run ID | `MR002-SPQ1-P2B-DEV-V1` |
| Frozen orchestration code | `bb029a96bb0c9e31600bd0b7ab068c31f70bbc7ac23afce0a3ffe0cb4412845b` |
| Collision rule module | `d827cc422b93aef3e89eaac1b95956f520cc78c721e7f6bcb83e3ec7422b0c33` |
| Collision rule ID | `MR002_SPQ1_NONINJECTIVE_REQUEST_IDENTITY_V1` |
| Phase 2B-2 evidence commit | `1cc98f55b71c5fa9751f4c7ea3df79f585804158` |
| Publication core SHA-256 | `f72902c5aa6db19204658c8487cda53a42a11cb391ec555ba46e0dd365508aff` |
| Canonical merge SHA-256 | `1d6defec7373a32bd213078fa656bd12069a4790a7c5b30fe2418b1ce7e526ef` |
| Development snapshot content | `1c6a5121467ea68a18a0e1b779e7aed10f39b606a2c769517a938b8f6f4a359a` |
| Closeout record | `docs/review/mr002/spq1/phase2b/2b3/MR002_SPQ1_Phase2B_2B3_ClosureCloseout_v1.0.json` |

### 3.4 Terminal-key clarification (2B-3; no rerun)

| Count | Meaning |
|---:|---|
| 425,000 | Distinct terminal keys (one per request unit) |
| 375,728 | Distinct **accepted** resolved `(session, permanent_security_id)` keys |
| 49,272 | `UNRESOLVED:<request_symbol>` terminals (70 collision + 49,202 permsec-resolution failures) |

The prior label “distinct resolved terminal keys” mixed accepted and unresolved keys. **2B-3 corrected nomenclature only**; the completed run was **not** regenerated.

### 3.5 Registered collision pairs (development window)

| Pair | Claimed permsec | Groups | Window |
|---|---|---:|---|
| AGN / AGN1 | PSEC-198103 | 12 | 2015-03 |
| CB / CB1 | PSEC-199850 | 2 | 2016-01 |
| DD / DD1 | PSEC-199769 | 21 | 2017-08/09 |

---

## 4. Governing principles (unchanged)

- Frozen MR-002 signal logic must not change after validation/OOS observation.  
- Validation and OOS remain **sealed until separately authorized**; seal must be **technically evidenced** (v1.1 §4.2 A3).  
- **Config B** is the only candidate eligible for sealed OOS; A/C are robustness neighbors only.  
- DSR multiplicity **N = 5** (trial ledger `deda5cec…`).  
- Close-**t** `SignalDecisionRecord` remains separate from **t+1** `ExecutionEnrichedCandidateRecord`; `FUTURE_INFORMATION_DETECTED` on violation.  
- **Conservative short/borrow view** governs economic interpretation; frictionless short is diagnostic only (§7).  
- Product code consumes **immutable published records** only — no duplicate signal economics (Architecture Review v1.1 D10).  
- No grafting into Momentum, Range Trader, or other live templates; portfolio combination requires a **separate preregistered study**.

---

## 5. Governing preregistration identity (bind; do not abbreviate)

| Item | Value |
|---|---|
| Governing prereg | `MR002_ValidationOOS_Preregistration_v1.0.4` |
| Governing commit | `4385ec7728a81c0db965e2f44d6017e6116d027c` |
| Prereg content SHA-256 | `b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c` |
| Superseded (bootstrap block only) | v1.0.3 / `c7a2e4b…` |
| Correction record | `MR002_ValidationOOS_CorrectionRecord_v1.0.4.json` |
| Correction class | **GOVERNANCE_ONLY** — `SIGNAL_OR_TRIAL_AFFECTING` count must remain **0** |

---

## 6. Preregistration facts Phase 3A must BIND (not redesign)

Phase 3A binds each row **by content hash and machine-readable diff** against **v1.0.4**. It must not reselect or reinterpret.

| Preregistered fact | Value |
|---|---|
| Validation window | 2020-01-13 → 2023-02-08 |
| OOS window | 2023-05-30 → 2026-07-01 |
| Walk-forward folds | 5 |
| **Primary Sharpe gate** | **net_oos_sharpe ≥ 0.70** (net return **including** 50 bps/yr borrow financing) |
| Borrow financing (in net) | `financing_costs_included_in_net = true`; `borrow_bps_per_year = 50`, day-count 360 |
| Cost stresses | 20 bps/side and 300 bps/yr borrow (severe diagnostic: 30 bps/side + 1000 bps/yr) |
| **Bootstrap** | **stationary (Politis–Romano, circular)**; expected block length **5 primary + 10 sensitivity**; **10,000** replications each; RNG **NumPy PCG64**; seed **20260711** |
| Bootstrap confidence | one-sided 95% lower bound |
| Confirmatory bootstrap gate | expected-L=5 lower bound of mean daily net return **> 0** (expected-L=10 = robustness diagnostic only) |
| DSR multiplicity | N = 5 |
| DSR trial ledger | `deda5cec0bbb72dd845633e99682849e6cf0db949e252dba956a432fcb383e9b` |
| DSR trial set | A, B, C, RNG-001, RNG-EntryLogic |
| DSR annualization | sqrt(252) · benchmark Sharpe = 0.0 |
| Diagnostics | PBO, regime concentration (not gates) |
| Execution endpoint | −5/−6 endpoint = next-open exit (realization horizon 6) |
| Portfolio | dollar-neutral (long_gross == short_gross); min_short = 100 |
| Current authorization | `validation_authorization = false` |

---

## 7. DSR dispersion rule (bind in 3A; compute only during validation)

| Item | Value |
|---|---|
| N | 5 |
| Dispersion source | validation-period annualized net Sharpes of Config A, B, and C |
| Dispersion estimator | sample standard deviation, `ddof = 1` |
| Per-observation conversion | divide by `sqrt(252)` |
| RNG-001 / RNG-EntryLogic | included in **N**; **excluded from dispersion** |
| Required pre-OOS artifact | `MR002_DSR_TrialDispersion_Validation_v1.0.json` (generated during authorized validation; **not** in Phase 3A) |

---

## 8. Short-side metric roles

| View | `metric_role` |
|---|---|
| Preregistered net model **including 50 bps/yr borrow financing** | `PRIMARY_GATE` |
| Conservative availability / locate / SSR model (v1.1 §4.2 A2) | `SECONDARY_GATE` / `ECONOMIC_OPERABILITY_GATE` |
| Zero-borrow-cost frictionless short attribution | `DIAGNOSTIC_ONLY` |

Phase 3A must **not** move the primary statistical gate onto the conservative-availability view.

---

## 9. Remaining phases (summary — detail in v1.1 §4–§9)

### Phase 3A — Validation Authorization Package *(next)*

Freeze the complete validation contract before opening data. Required amendments from v1.1 still apply:

- **A1** — Degrees-of-freedom attestation (`GOVERNANCE_ONLY` for v1.0.3→v1.0.4 bootstrap repair; **include Phase 2B collision amendment and 2B-3 terminal-key clarification** in the change inventory)  
- **A2** — Conservative short/borrow/locate model (governing economic view)  
- **A3** — Technical validation/OOS seal (access log + content commitment + opened-object ledger)  
- **A4** — Execution-enrichment edge-case contract (fail-closed census)  
- **A6** — Structural preflight + numeric-runtime binding  
- **§4.4a** — `metric_role` registry bound from v1.0.4  
- **§5.3a** — OOS consumption rule (define before OOS authorization)

**Baseline deliverables:** `ValidationAuthorization_v1.0.json`, `ValidationRunSpecification_v1.0.json`, input/metric/cost manifests, submission memo — see v1.1 §4.2.

**Stop:** No validation execution until package accepted.

### Phase 3B — Validation opening and enrichment

Open validation partition under seal controls; produce execution-enriched records without mutating close-**t** facts; enrichment edge-case census; OOS reads = 0.

### Phase 3C — Validation portfolio replay and metrics

Replay A/B/C under conservative + frictionless views; DSR; null-model report; `ValidationVerdict_v1.0.md`.

### Phase 3 decision gate

`VALIDATION_PASS` → prepare OOS authorization · `VALIDATION_INCONCLUSIVE` / `VALIDATION_FAIL` / `INTEGRITY_FAILURE` → stop (no OOS consumption unless pass).

### Phase 4 — Single sealed OOS (Config B only)

One OOS run; consumption rule enforced; `FinalResearchVerdict_v1.0.md`.

### Phases 5–8 — Product path *(only after research pass)*

5. Product-viability assessment · 6. Standalone paper strategy (publication consumer + OrderRouter) · 7. Optional multi-sleeve study · 8. Live-money readiness. Architecture Review v1.1 governs platform integration (combine-don’t-graft; no duplicate economics; ADRs for shorting if needed).

---

## 10. Recommended immediate developer assignment

Work **only** on Phase 3A **after separate authorization to draft the package**.

| # | Task |
|---|---|
| 1 | Locate governing prereg **v1.0.4** (`4385ec77…`, content `b2a042d4…`) |
| 2 | Bind validation/OOS partition definitions from prereg — do not reselect |
| 3 | Bind Config A/B/C by hash; confirm B as sole OOS candidate |
| 4 | Produce **MultiplicityAndDegreesOfFreedomAttestation** — include 2B collision amendment + 2B-3 nomenclature fix as `GOVERNANCE_ONLY` |
| 5 | Draft conservative short model spec (A2) and enrichment edge-case contract (A4) |
| 6 | Specify technical seal design (A3) and structural preflight (A6) |
| 7 | Assign `metric_role` per §8; bind from v1.0.4 |
| 8 | Define OOS consumption rule artifact (§5.3a) |
| 9 | Prove validation/OOS store access events = 0 |
| 10 | Commit Phase 3A package and **stop for authorization** — do not open validation data |

**Prohibited:** opening validation/OOS · computing returns/performance · ranking configs · changing frozen signal rules · product/broker/UI work.

---

## 11. Authorization boundary (this revision)

| Action | Status |
|---|---|
| Update roadmap to v1.2 (this document) | **AUTHORIZED** |
| Treat Phase 2B as closed baseline for downstream planning | **AUTHORIZED** |
| Draft Phase 3A validation authorization package | **NOT YET AUTHORIZED** |
| Open validation partition | **NOT AUTHORIZED** |
| Open OOS partition | **NOT AUTHORIZED** |
| Compute performance or economic interpretation | **NOT AUTHORIZED** |

---

## 12. Architecture cross-reference

Platform-facing constraints for any future promotion are fixed in **`docs/review/mr002/MR002_Architecture_Review_v1.1.md`**, including:

- SPQ-1 producer as **single signal-math source**  
- **SignalDecisionRecord** vs **ExecutionEnrichedCandidateRecord** seam (`β̂_m` in decision record; normalized beta at portfolio level only)  
- **Immutable, identity-bound daily publication** (rule census + owner rulings + schema identities)  
- Product template **must not recompute** signal economics  
- Research/live store separation; concrete persistence fixed at implementation authorization  
- Combine at **sleeve level** only — no Range/Momentum graft  

---

## 13. Relationship to prior plan versions

| Document | Role after v1.2 |
|---|---|
| `MR002_Development_Plan_Next_Phases_v1.2.md` | **Current** status, baseline, authorization, and next-step plan |
| `MR002_Development_Plan_Next_Phases_v1.1.1.md` | **Superseded** — erratum content merged into §5–§8 |
| `MR002_Development_Plan_Next_Phases_v1.1.md` | **Reference** for full Phase 3A–8 deliverable lists and amendment prose (A1–A6, §5.3a, §7.6) where not repeated here |
| `MR002_Development_Plan_Next_Phases_v1.0.md` | Historical |

---

## Final instruction

Phase 2B is **closed**. Do not rerun development production except under a **new explicit authorization**. The next stop is **Phase 3A package drafting** (when authorized), then formal review **before any validation data is opened**. Each subsequent phase stops for adjudication; no phase auto-authorizes the next.
