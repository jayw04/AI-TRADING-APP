# MR-002 — IMPLEMENTATION ERRATUM v1.0 — **DRAFT**

**Status: DRAFT. Drafting only is authorized (owner, 2026-07-16).**
Nothing beyond drafting. **Preflight, development performance, validation and sealed OOS remain
CLOSED.** After this draft's evidence bindings are verified, work **STOPS for countersignature**
before preflight.

**Purpose.** Bind, in one immutable record, the implementation actually used to produce the MR-002
exact-repair and agreement-certificate evidence over the registered overlap population — and the
corrections and amendments that were made along the way.

This erratum **does not alter the economic design** and **does not generalize the row-2307
disposition**.

---

## 1. Adjudicated result

```
Registered overlap rows evaluated:       3,839 / 3,839
Exactly feasible rows repaired:           3,838 / 3,838
Registered exactly infeasible singleton:      1  — row 2307
Invalid or unresolved rows:                   0
Exit status:                                  0
Wall-clock:                                 5.8 h
```

**This is not "3,839 repairs."** It is **3,838 certified repairs plus one prospectively
adjudicated, exactly infeasible original-model row.** That distinction is binding on every summary
of this result.

The agreement census contains:

- **3,838** certified feasible rows
- **1** countersigned exactly infeasible singleton
- **0** unresolved rows

## 2. Two populations — bound separately

The totals differ, and the difference is **not** missing records. Both definitions are bound here
with their own manifests:

| Population | Count | Identity | Definition |
|---|---|---|---|
| Stage-3 solver-characterization **corpus** | **3,895** instances | corpus hash `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b` | every captured Stage-3 QP model |
| Registered **overlap population** | **3,839** rows | manifest `289a834ca328ac734c0a036d9ab22479b901f73ae12d58e7e4f1132b89de9c46` | `sorted(set(PRIMARY_qualifies) & set(FALLBACK_qualifies))` by corpus index |

The 56-row difference is corpus rows where the cascade did not produce a qualifying overlap. The
overlap population is a **subset by construction**; its manifest is the authority for what was
required to be repaired. 20 duplicate equivalence classes are **kept, not deduplicated**.

## 3. Frozen specification bound

| Item | Binding |
|---|---|
| Pre-registration **v1.1** (refreeze candidate) | `Docs/implementation/TradingWorkbench_MR002_PreRegistration_v1.1_REFREEZE_CANDIDATE.md` · sha256 `311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5` |
| Signed-gap correction | `MR002_SignedGap_and_Repair_Report.md` — predicate = registered KKT `LIMITS` **AND** two-sided signed Lagrangian gap, band `[-1e-10, +1e-10]`, `max_interval_width 1e-30` |
| Final cascade | **`QUADPROG_SQRT → PIQP_P2`** |
| Exact repair | `EXACT_MIN_LINF_REPAIR_LP` — `min rho s.t. original feasible set AND |w_i − z_s,i| <= rho` |
| Exact solver | canonical exact rational Phase-I/Phase-II simplex, **Bland's rule** over canonical column identities |
| Shared exact basis decomposition | `MR002_ExactSimplex_EquivalenceReplay.json` · sha256 `ce110c517d659c030e5235f1d7a03721c3303d9ea4fc9ec8d037472af390b17a` |
| Directed-rounding correction | `MR002_DirectedRounding_Correction.json` · sha256 `93666948d3a0156833ce7dcf399640915a4283b2269ae65e465b2f10d46bd822` — serializer = corrected directed (outward) binary64, `app/research/mr002/directed.py` |
| Basis oracle | **RETIRED** — the exact rational simplex *is* the repair optimizer. HiGHS retired (it returned an exactly infeasible `rho=0` basis). |
| `floating_point_in_evidentiary_path` | **False** |
| Optimality authority | EXACT dual feasibility (`M'y <= c`, reduced costs ≥ 0). Primal/dual objective equality is a **reconstruction-consistency check only** — it cannot detect a feasible-but-suboptimal basis. |
| Feasibility authority | EXACT rational verification of `Mx = h, x >= 0` against the **unreduced** system, and of the ORIGINAL Stage-3 constraints at the mapped-back point. |
| Resource ceilings | `max_pivots_phase_i/ii 4000` · `max_seconds_per_repair 600` · `max_numerator/denominator_bits 200000` · `max_peak_memory_mb 4096`. Operational stop limits, **not tolerances**; they may not be raised after observing a stopped instance without a new adjudication. |

## 4. Prior-stage evidence bound

| Stage | Artifact | sha256 | Result |
|---|---|---|---|
| Sample A | `MR002_SampleA.json` | `573f0e80b97011e9a084345756a29eb5e08cabb3095432bb0eff8ba246a12779` | `sample_a_pass: true`, 0 stops |
| Sample B-C1 | `MR002_SampleBC1.json` | `850e8ad69313447fe60cd2180bd3d24e0043559a49710eb1e78252c476d77ccc` | `sample_b_c1_pass: true`, 0 stops; countersigned selection, cardinality 100, unique hashes, zero overlap with A |
| Duplicate census | `MR002_DuplicateCensus.json` | `216349d1c9d0bcd07c0bd08b5d16e695a6da6679c27e1e424a8c884e7481a872` | 20 classes, kept |

Both sample artifacts independently record `repair_module_source_sha256:
aa2877e13c4fbb6346b03d816d71ff8b31b104ec3dbb8d53bd62f5e7aba3772e` (see §8).

## 5. The six returned artifacts

All returned from the c6a instance and verified **byte-identical** (md5 diff empty on every file)
**before** teardown. Laptop path `.mr002out/fullpop_final_20260716/`.

| Artifact | sha256 |
|---|---|
| `MR002_FullPopulation.json` | `29b0f71c8a08d2f1c8f78744e6f3549c7eee98f7853f3ec74a5bebe094bb0357` |
| `MR002_FullPopulation_checkpoint.jsonl` | `d9453737b5e494c680348b42567592343b1df34490f4d814c89edf2bdc650d2f` |
| `MR002_Population_Manifest.json` | `0f77d7a649b9f31be4ad4bdbec2bba19c0f2b309508aca0e2019f82ecdfcd8fd` |
| `MR002_PopulationFeasibilityCensus.json` | `2dd7a6c0f9dac24b2ae686a82550727091b6ce5c8ed8122b298992596f8ee1e3` |
| `MR002_Row2307_Adjudication.json` | `179d571d5c6b1db201fda235198c10aaff5623a348f3b31e263f711ad1a3cdef` |
| `MR002_Row2307_Lineage.json` | `dac050347aff1d50f0eef97a17cdc3c49b399a606c6805f8aa51e29c220cd860` |

**Preservation: COMPLETE.** These are **no longer single-copy**. All six — with every other
load-bearing artifact, the source as run, and the pinned image — are preserved durably and were
**verified by retrieval** (downloaded from the durable copy and re-hashed; an upload response alone
was not accepted as evidence). See **§15**.

## 6. Final counters — all zero

From `MR002_FullPopulation.json.aggregate`:

```
expected_records                       3839
exactly_feasible_repair_population     3838
exactly_infeasible_registered_models      1
successful_exact_repairs               3838
agreement_failures                        0
objective_agreement_failures              0
determinism_failures                      0
shuffle_invariance_failures               0
invalid_runs                              0
resource_ceiling_breaches                 0
unclassified_records                      0
```

## 7. Row 2307 — the countersigned singleton

| Field | Value |
|---|---|
| Corpus index | `2307` |
| **Content hash** | `cfdc115e46f16226fafbe59b73890adca2f0c2f27b6f42c3ebebdce4d18ea30f` |
| Record hash | `b349d83d5cbaf9fe50fff8ee24ae67c0c4d213a95d418437494422574d83916f` |
| Status | `EXACTLY_INFEASIBLE_REGISTERED_MODEL` |
| `repair_status` | `NOT_APPLICABLE` |
| `agreement_certificates` | `NOT_APPLICABLE` |
| Population inclusion | `INCLUDED` |
| Feasible-population inclusion | `EXCLUDED` |
| n / m_ub / m_eq | 13 / 31 / 1 |
| Exact Phase-I optimum | `8947896785247447 / 21778071482940060754961610164661284503552` (≈ `4.108673e-25`) |
| Farkas certificate | verified: `Mᵀy <= 0` on **every** column (0 violations), `hᵀy > 0`, in exact rationals against the **unreduced** system |
| Certificate support | **9 of 45 rows**, weights exactly ±1 |
| Solver qualification | `QUADPROG_SQRT: QUALIFIES` (gap `-8.674e-17`), `PIQP_P2: QUALIFIES` (gap `+4.107e-17`) |

**Disposition scope — closed, not open.** `EXACTLY_INFEASIBLE_REGISTERED_MODEL` is authorized for
the **row-2307 identity only**, bound to its immutable content hash **and** to the countersigned
amendment. It is **not** an open category.

> **Any further Phase-I-positive row must be classified `INVALID_RUN`, pending verifier or
> constructor investigation** — because it would contradict the completed exact-feasibility census
> (which certified all 3,838 other rows feasible with verified primal witnesses). Two mutually
> contradicting verified certificates indicate a broken verifier or constructor, not a model
> property. A candidate certificate does **not** rescue such a row.

### 7.1 Why the sequence is scientifically valid

1. The population run **stopped** when the frozen gate met the anomaly.
2. **No result was laundered** into an existing category during the run.
3. Original-model infeasibility was established by an **exact Farkas certificate**.
4. Alternatives **B** (repair-LP construction defect) and **C** (exact-solver defect) were
   **excluded by evidence**, not assumption — an independently implemented exact simplex returned
   the **identical exact objective** on the production `M,h` (excludes C), and an independent
   constructor with **no elimination**, different layout and 57 vs 83 variables reached the **same
   exact optimum** (excludes B, and incidentally validated the empty-row elimination).
5. The **full census** established the other 3,838 rows are feasible (each with a verified primal
   witness); row 2307 reproduced independently, so the count is **absence, not blindness**.
6. The amendment registered row 2307 as a **specific singleton before the resume**.
7. The resumed run encountered **no additional infeasible rows**.

## 8. Numerical lineage — conditioning mechanism, **not** an exact cause

**Binding language:**

> Row 2307 is exactly infeasible under the registered binary64 model inputs, as established by its
> verified Farkas certificate. The contradictory constants are near-zero differences associated with
> an effectively empty book, including gross exposure of approximately 1.7×10⁻⁸, and arise through
> cancellation across roughly 16 orders of magnitude. The surviving contradiction is on the ULP
> scale of its constituent terms. This establishes a severe conditioning and finite-precision
> construction mechanism, but **it does not identify a unique incorrectly rounded input or prove
> that a single misplaced ULP caused the infeasibility.**

Explicitly:

| Claim | Status |
|---|---|
| exact model infeasibility | **established** |
| cancellation / conditioning mechanism | **established** |
| unique source value | **not identified** |
| single-ULP historical cause | **not established** |

Supporting measurements (`MR002_Row2307_Lineage.json`, sha256 `dac05034…`): `F_gross =
1.72275933518761803e-08` (hex `0x3e527f7c1c000000`); support constants ~`1e-9`–`6e-9`; largest
`|y·h|` term `6.676940e-09`; exact surviving sum `4.108673e-25`; cancellation ratio `1.625e+16`;
relative residue `6.154e-17` = `0.277` ULP at the term scale. Contributing factor: four of five caps
(`0.20/0.05/0.10/0.05`) are **not representable** in binary64 (`0x3fc999999999999a`, etc.), so
`cap × F_gross` is rounded before the cancelling subtraction. The equality row behaved exactly
(coefficients ±1, RHS `0x0000000000000000`).

**A one-ULP perturbation experiment would not upgrade this claim.** It would prove only that a
one-ULP perturbation of that coordinate is *sufficient* to restore feasibility — not that the
coordinate was historically misrounded, not that the adjacent binary64 was the intended value, and
not that it was the unique cause. Selecting a candidate **after** inspecting the contradiction would
also make the exercise diagnostic rather than prospective causal evidence.

**Optional later study** (not required before this erratum; must not "pick a candidate"). Freeze a
symmetric protocol first: test **all nine** constants; test **both** adjacent binary64 values where
finite; recompute the exact Phase-I optimum for **every** perturbation; preserve the original row
and Farkas certificate; report **all** feasibility-restoring perturbations, not only the first. Any
success is initially a **single-coordinate sensitivity witness**. Upgrading to an exact cause
requires additional provenance showing the upstream intended or correctly rounded value was
specifically the adjacent float used in the successful test. **Feasibility restoration alone does
not establish that history.**

This is a **data/model-lineage finding, not an economic performance result.**

## 9. The amendment

`MR002_FullPopulation_Amendment_v1.0` — countersigned 2026-07-16. Recorded **inside** the artifact:
`protocol_status: AMENDED_AFTER_AUTHORIZED_STOP`, `amendment_id`, `amendment_reason`,
`denominator_change`, `rates`, `row_2307_disposition`. The human-readable banner reads
**`FULL POPULATION — AMENDED PASS`**, never a bare `PASS`.

**§1 — the original STOP was CORRECT and is preserved.** Certified exact infeasibility was not an
anticipated terminal category, so §12's *"unexpected Phase-I infeasibility"* fired exactly as
specified. Row 2307's original checkpoint record is preserved **byte-identical** (it still reads
`EXACT_PHASE_I_POSITIVE`; reclassification happens only at aggregate time). Nothing was rewritten.

## 10. Stop and resume manifests

| Event | Record |
|---|---|
| Frozen run start | supervisor `2026-07-15 12:04:30 UTC`, seeded 0 |
| **STOP** | `attempt 1 exit=1 checkpoint_lines=2269` @ `2026-07-16 07:49:30 UTC` → `SCIENTIFIC STOP detected -- halting, NOT resuming (preserved for adjudication)` → `supervisor HALT` |
| Adjudication + census + amendment | 2026-07-16 (this erratum §7) |
| **Resume** | supervisor `2026-07-16 15:20:17 UTC`, **seeded checkpoint lines: 2269**; corpus + manifest re-derived and matched **before** the first new row; `2269 done, 1570 to go` |
| Completion | `attempt 1 exit=0 checkpoint_lines=3839` @ `2026-07-16 21:15:14 UTC` |

Row 2307 was in `done` on resume, so it was **skipped, never re-run, and could not re-trigger**.
The resume never re-ran only favourable rows, skipped a stopped case, changed order/code/config, or
merged incompatible manifests: the checkpoint is append-only, one line per completed row, each
binding the manifest hash and its own record hash, flushed and fsynced.

## 11. Provenance — source, tree, image, runtime

| Item | Value |
|---|---|
| Runner commit | **`355b4df057ebba87770f335356fc011bfef1d3b9`** |
| Container image | **`sha256:aa930021c072d01a5a14f389b53bea9d338e53b71e2aac08550972060a08610a`** (`mr002-research:v1.4`) |
| Python | `3.13.14`, ABI `cpython-313-x86_64-linux-gnu` |
| Platform | `Linux-6.1.176-221.360.amzn2023.x86_64-x86_64-with-glibc2.36` |
| Host | AWS **c6a.large** (AMD Zen 3, **AVX2-only, no AVX-512**), `OPENBLAS_CORETYPE=HASWELL` |
| Callable provenance | `certify_repair/agreement/objective_agreement.__module__ == app.research.mr002.exact_repair`; `exact_repair.solve_lp is exact_simplex.solve_lp` **True**; `certificate.to_fraction is exact_repair.to_fraction` **True** |

**Source hashes recorded in the artifact** (raw bytes, as read by the running interpreter):

```
scripts/mr002_full_population.py     0ac066cbede447a1…
app/research/mr002/exact_repair.py   7325abe5ef4fa113…
app/research/mr002/exact_simplex.py  7e0ef70087a0ea84…
app/research/mr002/certificate.py    1ba6aef49d0483fb…
```

**Verification against commit `355b4df`.** All four trace to that commit; the byte hashes are
**delivery-path dependent** because the binding hashed **raw** bytes (unlike ADR-0042's `_sha`,
which normalizes `\r\n`→`\n`):

- `exact_repair.py`, `exact_simplex.py`, `certificate.py` — reproduce **exactly** from
  `git archive 355b4df` (CRLF, the Windows `core.autocrlf` archive path).
- `mr002_full_population.py` — reproduces from the **LF** blob at `355b4df` (it was delivered by
  `scp` from the working tree rather than re-archived).

The **code is identical**; only line endings differ by delivery path. Python is newline-agnostic and
the exact arithmetic is unaffected.

### 11.1 Two provenance gaps in the artifact — disclosed, and recovered

Both are defects in the **binding**, not in the computation. The artifact is immutable and is **not**
edited; they are recorded here.

1. **`repair_manifest_source_sha256: None`.** The binding requested key `source_sha256`; the actual
   key is **`repair_module_source_sha256`**. **Recovered value:
   `aa2877e13c4fbb6346b03d816d71ff8b31b104ec3dbb8d53bd62f5e7aba3772e`** — recomputed in the pinned
   image `sha256:aa930021c072…` from the module (verified unchanged since `355b4df`), and
   **independently corroborated**: `MR002_SampleA.json` and `MR002_SampleBC1.json` both record the
   identical value under the frozen specification.
2. **Truncated image digest.** The artifact records `mr002-research@sha256:aa930021` (the env var
   was passed truncated). Full digest above; the image survives locally and its Id matches.

### 11.2 Environment reproducibility — binding

The frozen corpus `1d231930…` is **bound to an AVX2-only numerical environment**. Reproduction
requires an **AVX2-only CPU** (`c6a`/`m6a`/`r6a`) **and** `OPENBLAS_CORETYPE=HASWELL`. An AVX-512
host **cannot** reproduce it: on `c7i` the corpus hash matched but the population qualification
produced **3,843 rows / manifest `33ab41f4`** against the frozen **3,839 / `289a834c`** — 20 boundary
rows flipped. `NPY_DISABLE_CPU_FEATURES` was byte-identical to the baseline, proving **numpy SIMD is
not the cause**: AVX-512 inside the QP solvers (`quadprog` / `piqp`) is, and no env knob reaches it.
⚠ The runner's front gate checks only the **corpus hash**, so a wrong-population run would proceed
silently — **the manifest line must be verified too**.

## 12. What this erratum does NOT do

- It does **not** generalize the row-2307 disposition (§7).
- It does **not** alter the economic design.
- It does **not** claim a unique incorrectly rounded input or a single-ULP historical cause (§8).
- It does **not** open preflight, development performance, validation, or sealed OOS — all remain
  **CLOSED**.

## 13. Closed numerical gates

| Gate | Status |
|---|---|
| Stage-3 cascade coverage | PASS |
| Two-sided signed Lagrangian-gap predicate | PASS |
| Exact-repair capability | PASS |
| Directed-rounding correction | PASS |
| Sample A | PASS |
| Sample B-C1 | PASS |
| Full registered overlap population | **AMENDED PASS** |
| Artifact return and byte verification | PASS |

The full-population result establishes that **the registered exact-repair and agreement-certificate
process closes over the entire registered overlap population** under the countersigned row-2307
amendment.

## 14. Known defect in the supervising harness (disclosed)

The supervisor's completion discriminator matched the exact string `FULL POPULATION: PASS`. The
amendment renamed the banner to `FULL POPULATION — AMENDED PASS` (§9), silently killing the match;
the completed run logged `exit 0 without PASS marker; treating as completed`. **Benign** — the exit-0
branch is authoritative and the run completed correctly — but the secondary discriminator was
degraded. Fixed and version-controlled at `apps/backend/scripts/mr002_supervisor.sh` (commit
`bd56e34`): the **STOP check now runs first**, exit code governs, the banner is advisory and loosely
matched. This does not affect any evidence in this erratum.

---

## 15. Evidence preservation — the countersignature gate

**Preservation manifest sha256: `66e1e18c8a31a22e3104b33ec577e5bbfebfa59ecf33523ff79c5e742774c95d`**
(`MR002_EvidencePreservation_Manifest.json`, S3 version `x045XoE90ADA83648_Mfhp8U2SZ3P5Eh`).

No computation and no evidence rerun was performed. Preservation only.

```
required files present            : 30
unclassified or missing           :  0
local hashes verified             : 30
remote-retrieved hashes identical : 30
mismatches                        :  0
exact image preserved durably     : True
```

| | |
|---|---|
| Copy 1 | laptop `.mr002out/preservation_20260716/` |
| Copy 2 | `s3://workbench-backups-219024422756/mr002/evidence/20260716/` — **versioning Enabled**, so an overwrite cannot silently replace the evidence |

**Verification method.** Every item was **downloaded back from the durable copy and re-hashed**; a
successful upload response was not accepted. All 30 retrieved hashes are identical to local. The
manifest records per item: relative path, byte length, sha256, artifact role, source commit/tree
where applicable, raw-byte EOL form, remote key + version id, upload timestamp, post-upload download
sha256, and verification result.

**Contents.** The six full-population artifacts (original bytes) · run logs · Sample A · Sample B-C1
· duplicate census · equivalence replay · directed-rounding correction · frozen specification v1.1 ·
the four source files **as run** · image archive + inspect + full id · this erratum · the amendment ·
the provenance/adjudication/census/lineage records · the supervisor-fix record.

### 15.1 Image preservation

| Item | Value |
|---|---|
| Legacy image Id | `sha256:aa930021c072d01a5a14f389b53bea9d338e53b71e2aac08550972060a08610a` |
| OCI config digest | `sha256:770553aeae6c3d47f1735f61a4e0df75515c105ddda0431dcc2a07b8bdbfe4b6` |
| Image archive sha256 | `5d5d1f9032cc5b2f2a4ed03b63e7ff8cff00f3f195e851de06f9ab2fc423352e` (141,499,131 bytes) |
| Local-only | **No** — preserved as a versioned S3 object |

⚠ **The two image ids are the SAME image under two id schemes**, proven by the 8 identical rootfs
`diff_ids` recorded in the manifest. The artifact recorded the **legacy** id (truncated to
`aa930021`); c6a's containerd-backed docker reported the **OCI config** digest `770553aeae6c`.
Without this, a reviewer comparing the artifact's `aa930021` against c6a's logged `770553ae` would
wrongly conclude a different image ran.

### 15.2 Recovered provenance (bound in the manifest)

- `repair_manifest_source_sha256` = **`aa2877e13c4fbb6346b03d816d71ff8b31b104ec3dbb8d53bd62f5e7aba3772e`**
  — recomputed in the pinned image and **independently corroborated** by Sample A
  (`573f0e80…`) and Sample B-C1 (`850e8ad6…`), which both record the identical value under the
  frozen specification.
- **All four raw source-byte hashes** — reproduce the artifact's recorded binding exactly.
- **All four LF-normalized source hashes** — recorded alongside, so the delivery-path dependence
  (§11) is checkable without the archive.

### 15.3 Environment reproducibility, preserved

The AVX2-only constraint (§11.2) is now backed by the preserved image archive rather than a local
Docker store. A reproduction still requires an **AVX2-only host** (`c6a`/`m6a`/`r6a`) **and**
`OPENBLAS_CORETYPE=HASWELL`; the image alone is not sufficient.

---

## STOP — countersignature

| | |
|---|---|
| ERRATUM CONTENT | **ACCEPTED** (owner, 2026-07-16) |
| EVIDENCE PRESERVATION | **COMPLETE** — manifest `66e1e18c…`, 30/30 verified by retrieval, 0 mismatches |
| COUNTERSIGNATURE | **AWAITING OWNER** — the preservation gate is met; no further numerical run is required |
| PREFLIGHT | **CLOSED** |
| PERFORMANCE | **NOT COMPUTED** |
| VALIDATION | **SEALED AND UNREAD** |
| OOS | **SEALED AND UNREAD** |

Work **stops here**. Countersignature is the owner's act and is not recorded by this draft.
Preflight remains CLOSED until it is given.

**Commit identity of the reviewed draft:** the content the owner independently identified as sha256
`3639670d2c3703809dc0ed68a8615f00e47c21ac6da923d621d44e22873e4610` (19,475 bytes, 328 lines, LF)
was committed at `178c657` and is the exact byte-stream preserved in the manifest. **This section is
the only change since**; the scientific findings and predecessor artifacts are unaltered.
