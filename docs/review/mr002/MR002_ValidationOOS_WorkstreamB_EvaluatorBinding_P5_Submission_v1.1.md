# MR-002 Workstream B — prerequisite **P5** v1.1: qualifying container image, §4 binding **RESOLVED**

**Authorization:** P5 adjudication 2026-07-22 — *"Proceed only with the qualifying container-image
completion for P5, then stop for adjudication."*

**Supersedes** the v1.0 submission's binding. Per your instruction, producing the image required new
evaluator source, so the source binding was **not** silently preserved: the new module was committed
first, the complete §4 inventory was mechanically regenerated, and a **superseding binding package**
was issued against the new source commit.

**Boundary held:** synthetic fixtures only; the build ran with **no network and no mounts**; no
validation, OOS, or sealed data was mounted or opened; no credential release; no performance
computation; no P10; no D3 event. `validation_authorization` remains **false**; the CAS anchor is
untouched; sealed packages are git-verified unmodified.

**Full evaluator suite: 252 passed.** Ruff clean.

---

## 1. Result

```
binding_state        : RESOLVED
unresolved_elements  : []
container_image_digest: sha256:60b15568aa59…   (content-addressed image config digest)
source_commit / tree : d1e7ffc6ef28… / 01503f9a77f1…
included modules     : 21
```

`require_binding()` now passes — **and only for the exact bound source-and-image combination.**

## 2. Superseding, not patching

| | Superseded | Current |
|---|---|---|
| Source commit | `6708c59` | `d1e7ffc` |
| Included modules | 20 | **21** |
| Binding state | `PARTIALLY_RESOLVED` | `RESOLVED` |

The new module `mr002_valoos_image.py` is itself an evaluator module, so the inventory grew again
(20 → 21) and was **re-derived mechanically**, never incremented by hand. The superseded
`PARTIALLY_RESOLVED` binding is preserved alongside as
`MR002_EvaluatorBinding_superseded_6708c59.json`, and the new binding records what it supersedes and
why.

## 3. Build

| Property | Value |
|---|---|
| Base image | `python@sha256:fcbd8dfc2605…` (pinned by digest, local, not pulled) |
| Platform | `linux/amd64` |
| Builder | `docker/29.5.3` |
| Build definition | Dockerfile, recorded by SHA-256 |
| Network | **none** |
| Mounts during build | **none** |
| Context | git blobs at `d1e7ffc` **only** |

Build context bytes came from `git show <commit>:<path>` — **raw blobs**, not a working-tree copy or
`git archive` export. On this platform that distinction is load-bearing: line-ending translation
would silently change every digest and the byte-identity claim would be false while appearing to
hold.

The generator refuses to run if any **included** module is dirty (an uncommitted test or generator is
excluded and correctly does not block), and refuses if the worktree module set differs from the
commit it is about to name.

## 4. Image contents verified from inside

Enumerated by the image's own interpreter under the same §4 rule:

- **21 modules present, byte-identical** to the bound set;
- **no module omitted**, **no additional included module** present;
- dependency lock inside the image matches the bound lock SHA-256.

The **§4 binding gate was then executed inside the image** — `require_binding()` run by the image's
own Python against the superseding binding, mounted read-only — and **passed, verifying 21 modules**.

## 5. Refusals — all eight classes, three inside real containers

| Defect | Where | Result |
|---|---|---|
| module drift inside the image | **inside the produced image** | REFUSED |
| module omitted from the image | **inside the produced image** | REFUSED |
| additional unbound module in the image | **inside the produced image** | REFUSED |
| altered image digest | manifest | REFUSED |
| wrong source commit | manifest | REFUSED |
| wrong source tree | manifest | REFUSED |
| changed dependency lock | manifest | REFUSED |
| mutable-tag-only identity | manifest | REFUSED |

A `repo:tag` reference is rejected as an identity outright: only `sha256:<64hex>` or
`repo@sha256:<64hex>` is accepted, so the binding cannot be satisfied by a tag someone can move.

## 6. Two limits I am not papering over

**Determinism.** The image config digest embeds a build timestamp, so rebuilding the same source
produces a *different* digest. The binding names the digest **actually produced**; bit-reproducible
image builds are **not** claimed. If reproducibility is required later, that is separate work.

**Scope.** This is the §4 **image-identity** leg only. The image carries the evaluator modules and
the dependency lock; **no numeric stack was installed or qualified**. It asserts nothing about numpy,
SciPy, BLAS/LAPACK, threading, or seeds — that is **P10**, which remains unsatisfied and
unauthorized. An image whose §4 identity leg resolves is not a qualified numeric runtime.

## 7. Not done under this authorization

P10 numeric-runtime instance · custodian P6–P9 and P11 · P13 · validation/OOS access · credential
release · performance computation · grant-readiness verifier · any D3 authorization event.

Work **stops here for adjudication**.
