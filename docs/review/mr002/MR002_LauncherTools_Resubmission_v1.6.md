# MR-002 Stage-3 — Digest-Channel Launcher Delta + Numerical-Checkout Qualification Resubmission (v1.6)

- **Date:** 2026-07-19
- **In response to:** preflight-refusal review verdict (stop COMPLIANT; both root causes
  CONFIRMED; separate numerical checkout AUTHORIZED; digest-channel launcher delta
  AUTHORIZED; exhaustive env inventory REQUIRED; v2 chain revoked/consumed).
- **Scope:** ONLY the two digest environment channels + closed-grammar validation + tests
  + documentation, per the authorized recovery path. The frozen verifier and report
  generator are **byte-unchanged** (diff-verified). Stop evidence was committed first
  (`9adae1d`). No numerical, runner, pins, authorization, realism, or QUAL3 artifact
  changed.

## A. Separate numerical checkout — created and qualified

`/home/ec2-user/mr002/numrepo`, detached exactly at **`d26bd9edbd875d2e3e11d4a6f6e06bad933b168e`**,
tree **`c0e52d8ec61f881a2058c9c9686fde1ec33123a0`** — native LF Linux checkout from the
verified bundle; tracked porcelain EMPTY before and after DB staging; registered corpus DB
staged at the expected gitignored path `apps/backend/data/mr002_research.duckdb` with
identity recorded (md5 `92a985c1663b8e72c5bee8a3f394d591`, sha256
`24e5153cc0ebed77c7b422562e5a8ebfa147aad3019b27035b5314aaaacfad5a`, 132,395,008 B);
directory locked read-only (`dr-xr-xr-x`) after verification; **zero symlinks**; no
launcher tooling executed from it. Registered-file spot checks at `d26bd9e`:
`population_runner 9228ebd5…`, `preflight 9c749d73…`, `stage3_cascade 8c151d4b…`.
The replacement template will mount `numrepo → /work:ro`; launcher tools stay in the
separate launcher checkout (`~/mr002/repo` @ `d8992ac` or its approved successor).

## B. The digest-channel delta

`IDENTITY_ENV_KEYS = (MR002_IMAGE_DIGEST, MR002_OCI_CONFIG_DIGEST)` — **signed template
fields, never launcher-derived**:

- Both keys REQUIRED in template AND executed modes (the finite set gains exactly these two).
- `MR002_IMAGE_DIGEST` must equal the attestation's `image_digest` — enforced IN-GRAMMAR
  against the validator's `image_digest` argument, so produce and exec both enforce it
  automatically (`IDENTITY_ENV_MISMATCH`).
- `MR002_OCI_CONFIG_DIGEST` must be a full lowercase `sha256:<64hex>` in-grammar
  (`IDENTITY_ENV_NOT_FULL_DIGEST`), and must equal the attestation's `oci_config_digest`
  at produce (vs the build argument) AND at exec (vs the signed field)
  (`IDENTITY_ENV_MISMATCH`).
- Duplicates refuse (`ENV_KEY_DUPLICATE`); omissions refuse; substitutions and
  operator-selected alternates refuse (equality, not format alone).
- Documentation updated (constants block; the grammar's finite-set commentary).

## C. Exhaustive environment-read inventory — recorded + enforced

`MR002_RegisteredEnvReadInventory_v1.0.md` (sha `128724b6…`, 6,994 B): a static scan of
the REGISTERED bytes at `d26bd9e` across the full import closure (runner, preflight,
source-manifest, cascade, certificate, solver wrappers, coverage/development corpus path,
dataset/portfolio/runner modules), every `os.environ[...]`/`.get(...)`/`os.getenv(...)`
access classified with module:line, consumer, required/optional, expected value, and
grammar disposition (attested / launcher-derived / deliberately absent / CLI-only).
Notables: `MR002_SAMPLE` (corpus scope!) and `MR002_STORE` are DELIBERATELY ABSENT — the
grammar's refusal of unknown keys structurally guarantees the FULL population and the
registered DB path; preflight's `MR002_ROOT`/`MR002_COMMIT_SHA`/`MR002_TREE_SHA` are
CLI-`main()`-only and not in the registered path.

**Enforced forever by** `test_env_read_inventory_regression_guard`: re-scans those modules
on every suite run; a new MR002_*/numerical env read absent from the approved map fails
the suite until reviewed, dispositioned, and (if attested) added to the grammar.

## D. Required tests — all present (suite 86 → 97)

Identity channels: exact pinned values pass; missing either key refuses (parametrized);
wrong image digest refuses; malformed OCI refuses (uppercase/short/no-prefix); well-formed
wrong OCI refuses at produce; **valid-signature wrong-OCI refuses at exec with no spawn**
(hand-signed smuggle test); duplicate key refuses. `/work` may bind the numerical checkout
(`test_work_mount_may_bind_the_numerical_checkout`). **Launcher-checkout-as-/work is
detected** by the REGISTERED preflight module imported un-mocked
(`test_registered_preflight_detects_launcher_checkout_as_work`: Env at `d8992ac` identity
fails `git_commit`+`git_tree` against pins at `d26bd9e`; the registered identity passes
those checks). Plus the inventory regression guard (section C). All 86 prior tests
retained.

## E. Preflight smoke test — DESIGN PROPOSAL (submitted for review, NOT implemented)

The registered code's only preflight-only entry is `mr002_stage3_preflight.main()`, which
builds ExpectedPins from just four env values — but the registered `evaluate()` is
fail-closed on every unset pin (python/pkg/fingerprint/material checks), so that CLI can
never reach a "fully passing identity preflight". Per your instruction I am NOT altering
the runner and NOT adding an alternate production command; instead two designs for your
choice:

- **Option 1 (preferred): a new reviewed test-only script** (additive file, e.g.
  `scripts/mr002_stage3_preflight_smoke.py`, ~15 lines, itself review-frozen) that
  composes ONLY frozen registered functions: `load_authorization` +
  `load_expected_pins` (the real countersigned pins) + `run_preflight(pins, manifest)`,
  prints `Report.summary()`, exits 0 iff `rep.passed`. The smoke test then runs the
  pinned container over the numrepo mount with this script (mounted read-only like the
  final-test-report generator precedent), asserting a FULLY PASSING preflight without any
  population/corpus code path (run_preflight touches neither).
- **Option 2: accept a scoped assertion against the existing CLI** — run
  `python scripts/mr002_stage3_preflight.py` with the four env pins and assert that the
  identity checks (`git_commit`, `git_tree`, `image_digest`, `oci_config_digest`,
  `working_tree_clean`, `source_manifest`) all PASS while treating the None-pinned checks
  as out-of-scope. Weaker (exit code unusable), no new file.

## F. Evidence

| Artifact | sha256 · bytes | Result |
|---|---|---|
| `MR002_LauncherTools_HostSuite97_v1.6.log` | `0352b520…` · 21,320 | **QUALIFIED HOST, real CLI enabled: collected 97, 97 passed, ZERO skips, exit 0**; log records the exact producer/tests hashes + Docker/driver metadata (proper `--format` capture) |
| `MR002_LauncherTools_DevSuite_v1.6.log` | `986e53ce…` · 21,826 | dev venv: 96 passed + 1 intentional host-only skip, exit 0 |
| `MR002_LauncherTools_Ruff_v1.6.log` | `b28f5151…` · 422 | ruff 0.15.13, all four paths, exit 0 |
| `MR002_LauncherTools_Delta_v1.6.patch` | `2e6d5b2a…` · 15,402 | exact incremental diff vs the COMMITTED d8992ac bytes (`0fe474aa…` / `9bdffc70…`) |
| `MR002_RegisteredEnvReadInventory_v1.0.md` | `128724b6…` · 6,994 | the required inventory (section C) |

Host-suite integrity: run from the SEPARATE scratch clone (`~/mr002/delta-test/`); neither
the launcher checkout, the numrepo, nor the governed inputs were touched.

## G. Revised hashes (working tree; review copies byte-identical)

| File | sha256 | Bytes |
|---|---|---|
| `apps/backend/scripts/mr002_stage3_launch_attestation.py` (REVISED) | `8d9874beaef1732abba3f8d513df7016c301fcfeccc490f38c478edb646a1931` | 44,389 |
| `apps/backend/tests/research/test_mr002_stage3_launcher_tools.py` (EXPANDED 86→97) | `3d053fb790970b1a936c797c32cf7123829be36d75d26f8c78c8edde37d73d24` | 61,524 |
| frozen verifier (UNCHANGED, committed) | `33d08fe345b3b88f49cc85ee50cf6a53233d3523164bb7f927eb7333c4464e94` | 9,834 |
| report generator (UNCHANGED, committed) | `4b9ffb4de0ddc90d26d6d5b46539731b943dbb94aa8079ccf9328ecf0a25fca2` | 6,019 |

## Held state

v2 chain (attestation `4f8eade6…`, receipt `6a8cebe6…`, binding `a3fd33f5…`, nonce,
countersignature) REVOKED/CONSUMED — nothing reused. Execution authorization `487c6ecb…`,
pins countersignature, keys, QUAL3, and host qualification RETAINED. After this delta's
acceptance: commit → host-verify committed bytes → full recheck → NEW attestation
(new nonce; `/work` ← numrepo; both digest channels) → NEW receipt → NEW binding → NEW
execution countersignature → one new clean registered execution. Performance NOT
authorized; validation/OOS SEALED AND UNREAD.
