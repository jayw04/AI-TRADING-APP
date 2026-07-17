# MR-002 Stage-3 — Prospective Implementation Adjudication of the Cascade `QUADPROG_SQRT → PIQP_P2`

**Version:** v1.0 — **DRAFT FOR OWNER COUNTERSIGNATURE.**
**Status of this document:** document-only. Countersignature of this document authorizes the successor Stage-3 **design only**. Stage-3 execution remains prohibited until a **separate execution countersignature** binds the finalized implementation, fixtures, source manifest, image digest, runtime configuration, and clean-run protocol (§10). No preflight, performance computation, validation access, or sealed-OOS access is authorized.
**Classification:** numerical-implementation adjudication. It does **not** alter the registered MR-002 research design, the feasible portfolio set, the lexicographic objectives, the unique economic solution, the signal, risk limits, position bounds, costs, gates, data windows, or blindness controls.

---

## §0. Scope and authorization basis

This adjudication is drafted under the owner's final ruling (`docs/review/comments.md`), which:
- accepted three prerequisite evidence gates as PASS (§1–§6 below cite the committed evidence);
- directed **Disposition A** (a new *prospective* implementation adjudication of the cascade, followed by a clean rerun) and rejected the two shortcut dispositions;
- installed the conditional-coverage fallback-selection rule and the operational eligibility decision table required here.

It is a **prospective** adjudication in the following exact sense: the normative design frozen here (the primary formulation, the fallback profile, the eligibility rule, the certifier, the stop conditions) is justified from the registered model and the immutable pre-quarantine solver-characterization evidence **alone**. The prospective character attaches to *this* countersigned design and the *subsequent* clean rerun. It does **not** attach retroactively to the 2026-07-13 nonconforming execution, which remains quarantined.

---

## §1. Governance history

| Item | Identity |
|---|---|
| Superseded authority (erratum) | `docs/implementation/evidence/mr_002/MR002_Erratum_Stage3_EquivalentFormulationRetry.md`, SHA-256 `9ce8f53a4367c5817881cab55d9550db058a171e8ee504f57ad6a7060fe378fb`, 13,764 B, LF; preserved at commit `f3d0d15` (rescued byte-exact from stash `e7774f6`). |
| Superseded authority (countersign) | `MR002_Erratum_Countersign_Stage3Retry.json`, SHA-256 `7deae8c471bc4910415fa6619cc1526868de7e33f87c2ae52c84690830b87b4a`, 3,694 B, LF; committed **contemporaneously** at `b972f72` (2026-07-12 18:51, by the countersigner, added and never modified). Preservation census: commit `87fd05c` (`MR002_Stage3Countersign_PreservationCensus_v1.0.json`). |
| Nonconformance confirmed / evidence quarantined | commit `e506069` (`MR002_Governance_Reconciliation_Stage3_Cascade_v1.0.md`). |
| Quarantine countersigned — now GOVERNING | commit `13453b6` (`MR002_GovernanceReconciliation_Countersign_Stage3Cascade.json`). |
| Directed disposition | DISPOSITION_A (this document). |
| `MR002_Implementation_Erratum_v1.0` | **remains SUSPENDED.** It is not countersigned by this document and is not a basis for anything here. |

**What the superseded 2026-07-12 authority permitted.** The Equivalent-Formulation Retry erratum authorized a *restrictive* implementation: raw quadprog always attempted first; rescue only for the exact registered `ValueError`; the retry using the **same** solver under a positive-diagonal coordinate transformation `T = diag(t)`; and — explicitly — **no alternate optimizer, fallback solver, third attempt, regularization, jitter, tolerance relaxation, or inclusion-floor change.**

**What actually ran (quarantined).** The 2026-07-13 live cascade was `QUADPROG_SQRT → PIQP_P2`: it replaced the raw primary with the square-root-scaled primary, changed `diag(t)` to `diag(√t)`, and added the prohibited `PIQP_P2` fallback optimizer — with **no preserved prior adjudication** authorizing any of it. That execution, its 3,839-member population, the AMENDED PASS, the row-2307 disposition, and every derived artifact are governance-quarantined and are **not** evidence for anything in this document.

---

## §2. Supersession

The 2026-07-12 authority (erratum `9ce8f53a` + countersign `7deae8c4`) is **preserved unchanged**. This adjudication does not edit, merge, reconstruct, or invalidate it.

For the **successor execution only**, this adjudication — once countersigned — **prospectively supersedes** the raw-first / `T`-scaled-only / no-fallback authorization, replacing it with the primary formulation of §4 and the single fixed fallback of §5, governed by the eligibility table of §7.

Supersession is forward-only. Nothing here validates, ratifies, or retroactively authorizes the 2026-07-13 nonconforming run. The prior authority remains the correct governing record for what was permitted *before* this countersignature.

---

## §3. Mathematical equivalence of the coordinate transformations

The registered Stage-3 objective has Hessian `H = 2·diag(1/tᵢ)` with every `tᵢ > 0` (a modelling precondition; a non-positive `tᵢ` is an integrity defect under §7-C, never a numerical nonqualification). Its spectral condition number is

  κ₂(H) = maxᵢ tᵢ / minᵢ tᵢ.

Three exact coordinate transformations are considered. Each is a bijection for `tᵢ > 0`, maps the feasible set onto itself, and preserves the unique economic optimum after mapping back to the original coordinates. Only the numerical conditioning differs.

- **Raw** (`z` in original coordinates): Hessian `H`, κ₂ = maxᵢ tᵢ / minᵢ tᵢ.
- **T-scaled** (`z = T u`, `T = diag(tᵢ)`): `H_u = TᵀHT = 2·diag(tᵢ)`, κ₂(H_u) = maxᵢ tᵢ / minᵢ tᵢ. The *same* condition number: `T`-scaling reverses the diagonal scale but does **not** equilibrate the objective, and it imposes heterogeneous scaling on the transformed constraints.
- **Square-root** (`z = S v`, `S = diag(√tᵢ)`): `H_v = SᵀHS = 2·I`, κ₂(H_v) = **1**.

The square-root transformation is a genuine objective equilibration (`SᵀHS = 2I` exactly, by construction — see `apps/backend/scripts/mr002_solver_intersection.py:103` `solve_sqrt`). This is a model-derived numerical property, **independent of any observed solver outcome**. Constraints are transformed as `A_ub S v ≤ b_ub`, `A_eq S v = b_eq`; the square-root transform equilibrates the objective Hessian but does not by itself remove near-dependence from the transformed constraint matrices — the basis for the fallback in §5.

---

## §4. Primary formulation — `QUADPROG_SQRT`

The registered primary is the active-set quadprog solver applied under the square-root transformation of §3.

**Justification (result-independent).** Among the three exact transformations, only the square-root transform reduces the objective Hessian's condition number to one (`κ₂ = 1`). `T`-scaling leaves the condition number unchanged and is therefore not an adequate Hessian equilibration; the raw formulation carries the full `maxᵢ tᵢ / minᵢ tᵢ` conditioning. The square-root primary is selected on this conditioning analysis, derived from the registered `H` alone. It does not rely on, and is not motivated by, the quarantined full-population result.

---

## §5. Fallback — one fixed `PIQP_P2` profile

### 5.1 The normative rule (must read identically for 0, 5, or 500 primary nonqualifications)

> After a primary **eligible numerical nonqualification** (§7-B) — and only then — the one fixed fallback profile is invoked **exactly once**, on the identical registered problem, and its result is accepted **only** if it qualifies under the common external certifier (§5.4, §7-D). Any integrity, construction, provenance, or certifier defect is `INVALID_RUN` and is never rescued. If both the primary and the fallback numerically nonqualify, the outcome is `UNRESOLVED_NUMERICAL_FAILURE` and the run **STOPS**. No third attempt, no jitter, no tolerance change, no profile change, and no per-instance routing is permitted.

This rule contains no count and no row identity. It is complete and justified independently of how many instances invoke the fallback.

### 5.2 Algorithmic-path diversity (not universal superiority)

The primary is an **active-set** method; the fallback is a **proximal interior-point** method (PIQP). These are algorithmically distinct implementations with materially different numerical mechanisms and failure modes. The square-root transform equilibrates the objective but does not necessarily equilibrate or remove near-dependence from the transformed constraints; an interior-point method provides a **complementary numerical path** when the active-set attempt cannot produce an externally certifiable result. **Neither method is universally superior.** The claim is complementarity, not dominance.

### 5.3 Development-discovery disclosure (candid)

The cascade architecture `QUADPROG_SQRT → PIQP_P2` was **discovered during development**, after the countersigned raw / `T`-scaled route proved numerically inadequate. Its use in the 2026-07-13 execution was **unauthorized**. This adjudication now selects the cascade — and specifically `PIQP_P2` — **prospectively**, from the registered model and the admissible characterization evidence, and explicitly states that the quarantined result was already known and is **not** the basis for the selection.

A pre-registered PIQP profile record exists (`apps/backend/scripts/mr002_piqp.py`, "FROZEN LEXICOGRAPHIC PROFILE RULE, registered before the first PIQP corpus solve"). Full candor requires distinguishing its scope from this selection:
- That record fixes the two profiles (`P1: preconditioner_scale_cost=false` vendor default; `P2: preconditioner_scale_cost=true`; everything else identical — §5.5) and a **sole-solver** selection rule: run `P1` first; select it only if it qualifies on **every** one of the 3,895 instances; else `P2`, which must independently qualify on **all** 3,895; else stop.
- Under the authoritative counts (§6) neither profile qualifies on all 3,895 standalone (`P1`: 59 nonqualifications; `P2`: 51). That **sole-solver** rule therefore **stops** — it selects neither.
- This adjudication does **not** use the sole-solver rule. `PIQP_P2` is selected for the distinct **fallback** role under the owner's conditional-coverage rule (§5.4), whose question is not "does a PIQP profile qualify on all 3,895?" but "which admissible profile best rescues the primary's nonqualification set?"

The profile **definitions and frozen settings** in `mr002_piqp.py` are the configuration source of truth; its sole-solver selection *rule* is not the operative rule and is superseded by §5.4 for the fallback role.

### 5.4 Conditional-coverage selection rule and its frozen result

Selection is over admissible fallback profiles: algorithmically distinct from the active-set primary; one globally fixed configuration; valid primal and dual mappings; no integrity defects; deterministic; canonically shuffle-invariant; judged by the identical external certifier; no per-instance adjustment.

- **Primary criterion:** minimize `|F_Q ∩ F_Pⱼ|` — equivalently, maximize conditional coverage of the primary's nonqualification set `F_Q`.
- **Tie-break:** lower standalone nonqualification count `|F_Pⱼ|`; then lower registered resource burden under the same frozen protocol; then a deterministic profile identifier.

Frozen audit result (`MR002_Stage3FallbackSelection_Audit_v1.0.json`, committed `5ded766`; both row-level and unique-content-hash views agree):

| profile | `\|F_Q ∩ F_Pⱼ\|` | conditional coverage | standalone `\|F_Pⱼ\|` |
|---|---|---|---|
| PIQP_P1 | 0 | 5/5 | 59 |
| PIQP_P2 | 0 | 5/5 | 51 |

Both profiles rescue all five characterized `QUADPROG_SQRT` nonqualifications (tie on the primary criterion). **`PIQP_P2` wins the frozen tie-break** on the lower authoritative standalone nonqualification count (51 < 59).

**Closed candidate universe.** The selection is closed over **every** previously-characterized solver profile, not only the two PIQP profiles (`MR002_Stage3FallbackCandidateUniverse_v1.0.json`; existing pre-quarantine evidence only, no new solver runs). The frozen rule applies in a strict order: **admissibility filter → primary criterion (minimize `U = |F_Q ∩ F_candidate|`) → standalone tie-break.**

| profile | family | admissible? | rescues F_Q | standalone |
|---|---|---|---|---|
| CLARABEL (QP-form) | interior-point | **yes** | 4/5 (U=1) | 29 |
| PIQP_P1 | interior-point | yes | 5/5 (U=0) | 59 |
| **PIQP_P2** | interior-point | **yes** | **5/5 (U=0)** | **51** |
| HIGHS_QPASM | active-set | no (family) | 5/5 (U=0) | 592 |
| QUADPROG_RAW | active-set | no (family) | 2/5 (U=3) | 70 |
| QUADPROG_TSCALED | active-set | no (family) | 1/5 (U=4) | 185 |

**Admissibility filter.** Admits the three algorithmically-distinct interior-point profiles with valid primal-and-dual mappings under the common certifier: **`CLARABEL` (QP-form), `PIQP_P1`, `PIQP_P2`**. Excludes the active-set family (`QUADPROG_RAW`, `QUADPROG_TSCALED`, `HIGHS_QPASM`) — not algorithmically distinct from the active-set primary.

**Primary criterion.** Among the admissible set: `CLARABEL` `U=1` (rescues 4/5 — it numerically nonqualifies row 2765 on a KKT/stationarity residual) → **eliminated**; `PIQP_P1` `U=0`; `PIQP_P2` `U=0`.

**Tie-break** among the `U=0` admissible profiles: `PIQP_P2` (51) `<` `PIQP_P1` (59) → **`PIQP_P2` wins.** Note `CLARABEL`'s lower standalone count (29) never enters the tie-break, because it already failed the primary criterion — the ordering (filter, then coverage, then count) is what excludes it, not its count. Had any admissible candidate rescued all five *and* carried a lower standalone count than `PIQP_P2`, this draft would STOP rather than preserve the observed cascade.

**Clarabel lineage — two distinct implementations (do not conflate).**
- **QP-form `CLARABEL` profile** — the one in the authoritative 3,895-instance corpus. Valid primal **and** dual mapping under the common certifier; fully qualifies 4 of the 5 `F_Q` rows; its row-2765 result is a *numerical* certificate nonqualification (KKT/stationarity residual), **not** an integrity or dual-mapping defect. **Admissible**; eliminated on the primary criterion.
- **Abandoned exact-conic Clarabel reformulation** (commit `18c55f5`) — a *different* implementation that rewrote the QP as a conic program; its dual transformation could not survive `1/√t` and it was **retired**. It is **not** the profile characterized above, and the conic-remediation manifest (`MR002_QP_CandidateCapabilityManifest_ClarabelRemediation.json`) is historical evidence about a Clarabel dependency/API field only — **not** exclusion evidence against the admissible QP-form profile.

> `PIQP_P2` is prospectively selected as the fixed rescue profile because, over the **closed candidate universe**, it survives the admissibility filter, ties for complete conditional coverage of the characterized `QUADPROG_SQRT` nonqualification set, and wins the frozen standalone-qualification tie-break. This selection is derived from the authoritative solver-characterization evidence and is **not** based on the quarantined full-population result.

The **common external certifier** — the two-sided signed-gap + KKT predicate of §7 — not either solver's status string, is the acceptance authority for every accepted point, primary or fallback.

### 5.5 Frozen `PIQP_P2` configuration

One global configuration (`mr002_piqp.py` `BASE`), `preconditioner_scale_cost = true`, fresh solver object per instance (no update, reuse, or warm start): `eps_abs=1e-10`, `eps_rel=1e-11`, `check_duality_gap=true`, `eps_duality_gap_abs=eps_duality_gap_rel=1e-11`, `max_iter=1000`, `preconditioner_reuse_on_update=false`, `iterative_refinement_always_enabled=true`, `iterative_refinement_eps_abs=eps_rel=1e-13`, `iterative_refinement_max_iter=20`, `kkt_solver=sparse_ldlt`. No per-instance parameter is changed.

### 5.6 Characterization-corpus vs future-run unresolved sets (must not be conflated)

- **Characterization-corpus unresolved set** = `|F_Q ∩ F_P2|` = **0** (an admissible, established fact — §6).
- **Future clean-rerun unresolved set** = **unknown until executed.** It is not asserted to be zero. The 3,839/3,839 completion of the quarantined run is inadmissible and is **not** imported here. `UNRESOLVED_NUMERICAL_FAILURE → STOP` (§7-D) remains a **live** successor-run outcome.

---

## §6. Characterization evidence (admissible; identities and intersections)

Source: the immutable 3,895-instance solver-characterization corpus, corpus hash `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b`, verified. Authoritative per-solver results: `runtime/MR002_R2_RegressionSampleA.json` and `runtime/MR002_RepairSizingSample.json` (post-dual-mapping-fix), which **agree row-for-row**. Predicate: KKT-qualified **and** two-sided signed-gap-qualified (band `[-1e-10, +1e-10]`, exact `as_integer_ratio` inputs, outward-rounded ≥100-digit intervals, no `max(Γ,0)`, no cushion, no KKT-to-objective conversion).

- `F_Q` (`QUADPROG_SQRT` nonqualifications): **5** rows `{800, 1328, 2140, 2296, 2765}`, five distinct content hashes (fingerprint `2ae80e55…`). On every one the primary outcome is the registered defect `ValueError: constraints are inconsistent, no solution`.

  **Feasibility (full qualification, not merely a primal witness).** Each of the five instances is **fully qualified under the complete registered KKT + two-sided signed-gap predicate** (which requires a valid dual) by multiple independent solver implementations. The number of full qualifiers per row, bound to the authoritative artifacts, is: **row 800 = 5, row 1328 = 5, row 2140 = 4, row 2296 = 5, row 2765 = 3** (the qualifying sets are enumerated in `MR002_Stage3FallbackCandidateUniverse_v1.0.json → per_row_feasibility.table`). This establishes that all five registered problems are **feasible** and that the `QUADPROG_SQRT` outcomes are **numerical false-infeasibilities, not economic infeasibilities.** `CLARABEL` is one of the full qualifiers on four of the five rows; its row-2765 result is a numerical certificate nonqualification, not an integrity or dual-mapping defect. (No blanket claim is made that every named solver qualifies every row — the per-row sets differ.)
- `F_P1` = **59**; `F_P2` = **51**. `|F_Q ∩ F_P1| = |F_Q ∩ F_P2| = 0` at both the row level and the unique-content-hash level.

**Marginal-count correction (must be stated so no later summary revives the obsolete counts).** Earlier direction and summaries quoted `PIQP_P2 = 50`, `PIQP_P1 = 58`. Those are the counts of `runtime/MR002_ComplementaryCoverage.json`, which the owner ruled **NON-authoritative on 2026-07-14 §5** (a hand-rolled Clarabel dual-mapping defect, since corrected and centralised in `app/research/mr002/certificate.py`). The **authoritative** counts are `QUADPROG_SQRT = 5`, `PIQP_P1 = 59`, `PIQP_P2 = 51`. The selection **ranking is robust** to this correction (`PIQP_P2` wins under both); this document uses `5 / 51 / 59` throughout, and reliance on `50 / 58` is withdrawn.

---

## §7. Total eligibility decision table (closed enum; every primary outcome maps to exactly one category)

The implementation normalizes every raw solver behavior into a closed internal enum:
`QUALIFIED · NUMERICAL_STATUS_NONQUALIFICATION · CERTIFICATE_NONQUALIFICATION · INTEGRITY_DEFECT`.
An unrecognized raw result maps to `INTEGRITY_DEFECT`, **never** to fallback eligibility.

**A — Primary qualification.** Provenance / source / configuration / problem identity match; dimensions and mappings valid; all authoritative inputs finite; solver returns a valid candidate; the external certifier completes; the complete registered predicate passes (`KKT-qualified ∧ two-sided signed-gap-qualified`).
→ `PRIMARY_QUALIFIED`; accept primary; **do not** invoke fallback.

**B — Eligible numerical nonqualification.** All model, provenance, invocation, and certifier-integrity checks pass, **and** either (i) the primary returns a normalized outcome on the frozen allowlist of numerical nonqualification codes, or (ii) it returns a finite, correctly dimensioned, correctly mapped candidate, the certifier completes normally, but the complete registered predicate is false.
→ `PRIMARY_NUMERICAL_NONQUALIFICATION`; invoke the one frozen fallback **exactly once**.
The allowlist is governed by **exact normalized reason codes**, never substring matching (frozen operationally in `MR002_Stage3EligibilityStatusMapping_v1.0.json`). The one registered `QUADPROG_SQRT` numerical mapping is:

  exact class `ValueError` + **exact complete message** `"constraints are inconsistent, no solution"` (`mr002_solver_intersection.py:240-246`) → `QUADPROG_CONSTRAINTS_INCONSISTENT` → `NUMERICAL_STATUS_NONQUALIFICATION` → invoke `PIQP_P2` once.

**Historical proof vs future eligibility (kept strictly separate).** That the *five characterized* `F_Q` instances were numerical *false*-infeasibilities is established for **those five rows only**, by five independent solvers certifying them feasible (§6). On a newly encountered instance this normalized status is **fallback-eligible but is not itself evidence that the model is feasible**; feasibility or qualification remains to be established by the fallback and the common certifier (→ D). An unknown exception class **or** an unknown message maps to `INTEGRITY_DEFECT` (§7-C), never to fallback eligibility, and never by analogy.

**C — `INVALID_RUN` (no fallback; STOP).** Source/commit/image/config mismatch; problem or manifest identity mismatch; dimension/shape mismatch; non-finite model input; non-finite solver output; invalid transformed-to-original mapping; unexpected exception or unregistered solver status; certifier exception or incomplete certificate; dual-mapping or sign-convention failure; internal invariant violation; contradictory/malformed result state; any `tᵢ ≤ 0`.

**D — Fallback disposition.** After an eligible primary numerical nonqualification: fallback qualifies under the common certifier → `FALLBACK_QUALIFIED`, accept the fallback point; fallback completes but does not qualify → `UNRESOLVED_NUMERICAL_FAILURE`, **STOP**; fallback has any integrity/provenance/contract defect → `INVALID_RUN`, **STOP**.

**Required test fixtures (every branch exercised).** valid solver exception eligible for rescue; finite candidate failing one KKT gate; finite candidate failing only the signed-gap gate; non-finite candidate; wrong-sized candidate; unknown status → `INTEGRITY_DEFECT`; certifier exception; both solvers numerically nonqualifying → STOP; primary integrity failure with proof the fallback was not called. The five `F_Q` fixtures (content/instance hashes in the audit binding) exercise branch B→D-qualified.

---

## §8. Design B and C dispositions (considered and rejected on the admissible evidence)

**Design B — single uniform interior-point solver (`PIQP` only), no cascade. REJECTED.** On the admissible corpus, uniform `PIQP_P2` carries **51** standalone nonqualifications versus the cascade primary `QUADPROG_SQRT`'s **5**. A single `PIQP` solver would remove the visible cascade while increasing characterized nonqualification by an order of magnitude, still require the same external certifier, and leave more unresolved numerical cases. Procedural simplicity is not numerical superiority; uniformity is gained but characterized qualification coverage materially worsens, with no compensating certificate or integrity advantage.

**Design C — `QUADPROG_SQRT` uniformly, no rescue; excluded rows. REJECTED and categorically incorrect as posed.** A valid model on which one numerical solver cannot produce a qualifying point is **not** an `INVALID_RUN` (§7-C reserves that for integrity/provenance/construction defects). Excluding such rows would convert a recoverable implementation limitation into a denominator change, knowingly discard mathematically admissible instances, make population membership depend on one solver's numerical reach, and use "cleaner governance" to conceal weaker computational coverage. Without a rescue, such rows must remain `UNRESOLVED_NUMERICAL_FAILURE → STOP`, not be silently excluded — which is precisely why the fixed fallback exists.

---

## §9. Quarantine disclosure and strict non-reuse

The quarantined 2026-07-13 execution (the `QUADPROG_SQRT → PIQP_P2` full-population run, its 3,839-member population, the `FULL POPULATION — AMENDED PASS`, `MR002_FullPopulation*`, `row-2307` disposition, feasibility census, and every derived artifact under `.mr002out/`) is disclosed here **only as governance history**. It is **not admissible** as the basis for the primary formulation, the fallback profile, the eligibility rule, the certifier, any population expectation, or any acceptance threshold, and **may not be reused** as evidence for the successor run.

Everything numerical in §3–§7 derives from the registered model and the immutable pre-quarantine characterization corpus (`1d231930…`), never from the quarantined run.

---

## §10. Clean successor-rerun protocol (post-countersignature only)

**Countersignature of this adjudication authorizes the successor Stage-3 design only. Execution remains closed.** A complete clean rerun may begin **only after a separate execution countersignature** binding the finalized implementation, the eligibility fixtures, the source manifest, the image digest, the runtime configuration, and the clean-run protocol below. Subject to that separate execution countersignature, the clean rerun runs under:
- fresh checkout at the countersigned commit + a fresh source manifest; fresh container/runtime binding recorded;
- **no** checkpoint, record, certificate, aggregate, or artifact reused from the quarantine; no quarantined row disposition copied into the successor evidence path;
- the complete corpus and all overlap/coverage manifests **regenerated anew** and re-verified against the registered corpus hash;
- validation and sealed-OOS windows **inaccessible** (sealed and unread);
- deterministic checkpoint/resume permitted **only within** the new run.

The successor run generates all manifests, solver records, checkpoints, certificates, and aggregates freshly. This adjudication authorizes the *design*; a separate countersignature authorizes *execution*, and execution is where the future unresolved set (§5.6) is actually determined.

---

## §11. Acceptance and stop gates

- Acceptance is the frozen registered predicate only: `KKT-qualified ∧ two-sided signed-gap-qualified` at the §6 tolerances; no `max(Γ,0)`, no cushion, no KKT-to-objective conversion.
- Determinism (same-image) and canonical shuffle invariance are required and checked.
- Complete record accounting: every instance resolves to exactly one §7 category; counts reconcile to the regenerated corpus.
- **No prior row disposition or unregistered category is carried into the successor run.** A newly observed primary outcome that maps exactly to §7-B invokes the frozen fallback (this preserves the 0/5/500 invariance — a matching numerical nonqualification is *rescued*, not stopped, whatever its count). An unregistered status, a §7-C integrity defect, both solvers nonqualifying (`UNRESOLVED_NUMERICAL_FAILURE`), an unexpected Phase-I-positive result, or **any** outcome outside the total decision table causes **STOP**.

---

## §12. Evidence-binding manifest

Bound artifacts (companion machine-readable manifest: `MR002_Stage3ProspectiveAdjudication_EvidenceBinding_v1.0.json`):

| role | artifact | identity |
|---|---|---|
| superseded erratum | `MR002_Erratum_Stage3_EquivalentFormulationRetry.md` | `9ce8f53a…` @ `f3d0d15` |
| superseded countersign | `MR002_Erratum_Countersign_Stage3Retry.json` | `7deae8c4…` @ `b972f72` |
| preservation census | `MR002_Stage3Countersign_PreservationCensus_v1.0.json` | @ `87fd05c` |
| fallback-selection audit | `MR002_Stage3FallbackSelection_Audit_v1.0.json` | `c90b0556…` @ `5ded766` |
| closed candidate universe | `MR002_Stage3FallbackCandidateUniverse_v1.0.json` (v1.1) | `d0eb33c0…` |
| eligibility status mapping | `MR002_Stage3EligibilityStatusMapping_v1.0.json` | (hash in manifest) |
| Clarabel conic lineage (retired, historical) | `MR002_QP_CandidateCapabilityManifest_ClarabelRemediation.json` + commit `18c55f5` | `8c1d83ec…` |
| characterization corpus | corpus hash | `1d231930…` (3,895 instances) |
| authoritative solver results | `MR002_R2_RegressionSampleA.json`, `MR002_RepairSizingSample.json` | agree row-for-row |
| solver-robustness defect | `MR002_DEFECT_Stage3_Solver_Robustness.md` | `41da8b08…` |
| quarantine (governing, non-reusable) | reconciliation + countersign | `e506069`, `13453b6` |

`F_Q = {800, 1328, 2140, 2296, 2765}` (fingerprint `2ae80e55…`); `F_P1` fp / `F_P2` fp as bound in the audit; `|F_Q ∩ F_P1| = |F_Q ∩ F_P2| = 0`.

---

## Authorization boundary

**This document, once countersigned, authorizes:** the *design* of the successor Stage-3 implementation (primary §4, fallback §5, eligibility §7) and, under §10, a clean successor rerun **when a separate execution countersignature is given.**

**It does not authorize, and nothing here permits:** countersigning the suspended `MR002_Implementation_Erratum_v1.0`; **any Stage-3 execution before the separate execution countersignature**; reuse of any quarantined artifact or row disposition; preflight (CLOSED); performance (NOT COMPUTED); validation (SEALED AND UNREAD); sealed OOS (SEALED AND UNREAD).

**The judgment requested of the owner** is not whether the quarantined cascade passed. It is whether the frozen successor design here is mathematically equivalent (§3), numerically principled (§4–§5), independently certifiable (§7, §11), honestly derived from admissible evidence (§6, §8), strictly severed from the quarantine (§9), and fixed before execution (§10).

*— Draft ends. Awaiting owner review and countersignature. No code or Stage-3 instance may run before that countersignature.*
