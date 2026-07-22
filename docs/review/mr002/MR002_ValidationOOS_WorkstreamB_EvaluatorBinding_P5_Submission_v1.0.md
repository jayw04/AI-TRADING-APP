# MR-002 Workstream B — prerequisite **P5**: §4 pre-access evaluator binding v1.0

**Authorization:** P4 adjudication 2026-07-22 — *"P5 — §4 pre-access evaluator binding is authorized
to begin… Proceed with P5 only, then stop for adjudication."*

**Boundary held:** synthetic inputs only for behavioural verification. No validation / OOS / sealed
value access, no credential release, no performance computation, no P10, no D3 authorization event.
`validation_authorization` remains **false**; the CAS anchor is untouched; the sealed Phase 3A and
adjudication packages are git-verified unmodified.

**Products:** `evaluator/mr002_valoos_binding.py` · `evaluator/MR002_EvaluatorBinding.json` ·
`evaluator/MR002_P5_BindingQualification.json` · `evaluator/_gen_evidence_p5.py` ·
`evaluator/test_binding_p5.py`.

**Full evaluator suite: 227 passed.** Ruff clean.

---

## 1. Headline — the binding is `PARTIALLY_RESOLVED`, and that is the correct outcome

§4 requires a **container-image digest**. No qualifying bound image exists, so that leg is
`UNRESOLVED` and `PENDING_EVALUATOR_BIND` is preserved on it, exactly as instructed. The binding
therefore reports:

```
binding_state        : PARTIALLY_RESOLVED
unresolved_elements  : ["container_image_digest"]
pending_evaluator_bind: PENDING_EVALUATOR_BIND
```

`require_binding()` — the gate a run must pass before any window read — **refuses while any §4 leg is
unresolved**, on an otherwise pristine tree. So this cannot be forgotten later: P5 delivers the
authoritative **code** binding, and §4 is not fully discharged until a bound image exists. That image
is the runtime producer's deliverable and was not authorized to me.

## 2. Ordering was enforced, not assumed

A binding that names a `source_commit` must not name code that is only in a working tree. The
generator therefore **fail-stops** if any included module is missing from, or differs from, its blob
at the bound commit. Consequently the P5 modules were committed first (`6708c59`), and the binding
names that commit:

```
source_commit : 6708c59fcd442fb3675d5b8e54c8e7ee0ba0a72a
source_tree   : 89a61bffb335…
working tree clean for modules: true
all included modules committed at source_commit: true (blob digests recorded per module)
```

The artifacts emitted afterwards are `EXCLUDED_NON_EVALUATOR`, so committing them adds **no included
module** and the bound inventory stays reproducible at `source_commit`.

## 3. Inventory — mechanically enumerated, 19 was not assumed

Every directory entry is classified; nothing is silently skipped.

| Class | Count |
|---|---:|
| `INCLUDED_MODULE` | **20** |
| `EXCLUDED_TEST` | 6 |
| `EXCLUDED_GENERATOR` | 6 |
| `EXCLUDED_NON_EVALUATOR` | 16 |
| `EXCLUDED_CACHE` | 3 (`__pycache__`, `.pytest_cache`, `.ruff_cache`) |

`every_entry_classified: true` — the class counts sum exactly to the directory entry count, and every
excluded file is listed with its own SHA-256.

**The count is 20, not the 19 recorded at P4** — `mr002_valoos_binding.py` is itself an evaluator
module and enters the inventory it qualifies. This is precisely why the P4 adjudication forbade
treating 19 as a constant. The binding records that its count is derived at qualification time and
must be re-derived on any tree change.

## 4. Fail-closed detection — demonstrated, not asserted

Each defect class was injected into a sandbox copy and the binding gate refused every one:

| Defect | Result |
|---|---|
| unbound module present on disk | REFUSED `module_unbound` |
| bound module missing | REFUSED `module_missing` |
| module renamed (content matched under a new path) | REFUSED `module_renamed` + `module_renamed_target` |
| module content drifted | REFUSED `module_drift` |
| duplicate module content (ambiguous identity) | REFUSED `duplicate_module_content` |
| unresolved §4 leg on a pristine tree | REFUSED `unresolved_section4_elements:container_image_digest` |

A clean tree with **every** leg resolved passes — so the refusals are discriminating, not a gate
stuck shut.

Rename detection is content-based: a bound module whose digest reappears under a different path is
reported as a rename on both sides rather than as an unrelated missing/unbound pair, so a rename
cannot be laundered into "one file left, another arrived".

## 5. §4 element roster — every element accounted for

| Element | Status |
|---|---|
| `source_commit`, `source_tree` | RESOLVED |
| `dependency_lock` | RESOLVED (file + SHA-256) |
| `data_manifest_identity` | RESOLVED_BY_REGISTERED_IDENTITY |
| `benchmark_impl`, `cost_model_impl`, `metric_impl`, `bootstrap_impl`, `pbo_dsr_impl`, `report_schema` | RESOLVED (module + SHA-256, each inside the qualified inventory) |
| `expected_output_paths` | RESOLVED |
| `container_image_digest` | **UNRESOLVED** |

`build_binding` refuses to emit if any element is unaccounted for, if a named element module is
outside the inventory, or if a required field is a sentinel.

**The data manifest is bound by registered identity only** — the SHA-256 recorded in preregistration
v1.0.4 `governing_frozen_sources`. The physical artifact is **not opened here**; verification of it
is deferred to run time under the access boundary.

## 6. Not inferred from the Phase 3A registry

The binding was produced prospectively by enumerating the then-current directory. The Phase 3A
registry was not read, copied, or used as a fallback; it remains historical under its own all-`.py`
rule.

## 7. Not done under this authorization

Container image creation · P10 runtime instance · custodian P6–P9 and P11 · P13 · validation/OOS
access · credential release · performance computation · grant-readiness verifier · any D3
authorization event.

Work **stops here for adjudication**.
