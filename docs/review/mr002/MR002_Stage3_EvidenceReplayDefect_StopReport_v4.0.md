# MR-002 Stage-3 — Registered-Execution STOP Report v4.0: Evidence-Replay Serialization Defect (Run 4)

- **Date:** 2026-07-19 (launch 02:21:39.444Z, terminal 02:28:39Z, ~7m00s)
- **Disposition:** **STOPPED at the FINAL gate.** The registered container ran the ENTIRE
  Stage-3 pipeline to completion for the first time: governance chain, in-container
  preflight, output-root control, corpus regeneration with hash equality against the
  pins, the full 3,895-row identity manifest, and the complete resolution loop —
  **3,895 / 3,895 rows processed, 3,895 qualified, 0 stopped** (3,890 primary
  `QUADPROG_SQRT`, 5 fallback `PIQP_P2`), terminal `COMPLETE`, evidence fully persisted.
  The run was then refused a PASS by `aggregate_verdict`'s semantic replay: **3,639 of
  3,895 durable records fail `INPUT_RATIOS_DO_NOT_MATCH_CONTENT_HASH`**. No patch,
  retry, resume, or bypass. **Validation/OOS SEALED AND UNREAD** (DEV window only,
  2013-01-02 → 2019-10-02, per the frozen corpus source).

## Required post-run evidence (stop outcome)

| Item | Value |
|---|---|
| Launcher stdout/stderr | `MR002_Exec4_Stop_20260719.log` — sha256 `b862e954b92c9a855993d3751ea3d338c673b758c5efd000cbe65a730b1144a4`, 2,836 B |
| Exact executed argv | in the log: the attested v4 template + the derived binding field |
| Derived binding token | `MR002_EXECUTION_BINDING_SHA256=83d1bcbf…` — present exactly once (grep count 1) |
| Container / image | `dce65497…` (auto-removed by the attested `--rm`), image `sha256:81e8d7a7…` |
| Runner stdout | `{"disposition": "STOP", "detail": "", "corpus_hash": "1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b", "run_manifest": "/out/cleanrun/MR002_Stage3_CleanRun_Manifest.json"}` — exit code **1** |
| Preflight / governance chain | **ALL PASSED** — every gate that stopped runs 1–3 cleared; corpus hash derived by the runner equals the registered pins (the row loop is unreachable otherwise) |
| Rows attempted / completed | **3,895 / 3,895** — all qualified, zero stop records, terminal `{"kind":"terminal","status":"COMPLETE","n_records":3895}` as the final checkpoint line |
| Run counters (manifest) | `n_expected=3895, n_processed=3895, n_qualified=3895, n_stopped=0, stopped=false, refused=false, passed=false, evidence_persisted=true, resumable=true` |
| Output inventory | `/out/cleanrun`: exactly 2 entries — checkpoint `MR002_Stage3_CleanRun_checkpoint.jsonl` (67,293,482 B, sha256 `b9b0a948…6637b7445`, 3,896 lines = 3,895 records + terminal) + run manifest `MR002_Stage3_CleanRun_Manifest.json` (130,846 B, sha256 `1132d3b8…79c96e40`) |
| Row-manifest hash | `row_manifest_sha256 = 699b17df…94d7ac7eb` (in the run manifest) |
| Host-state recheck | `docker ps -a` empty; all 9 staged input hashes unchanged (authorization `487c6ecb…`, binding `83d1bcbf…`, package `66c8d42f…`, pins `ddfa43d0…`, report `26bbdff8…`, attestation `7c65a901…`, receipt `6462e6c8…`, realism `f7cccd65…`, source manifest `27d2819b…`); checkpoint/manifest owned by container root, host untouched |
| Validation / OOS | SEALED AND UNREAD |

## Root cause — a code defect in evidence serialization: `-0.0` cannot round-trip

**PROVEN byte-exact by read-only forensics** (scripts in `forensics_run4/`, run in the
pinned image with `/work` and `/out` mounted read-only):

1. `_exact_ratio_list` (`app/research/mr002/stage3_cascade.py:620`) serializes each
   float as `float.as_integer_ratio()`. For negative zero,
   `(-0.0).as_integer_ratio() == (0, 1)` — **the sign bit is destroyed**.
2. Replay (`verify_numerical_evidence_record`, runner line ~528) rebuilds
   `n / d = +0.0`.
3. `rec_content_hash` (`stage3_cascade.py:625`) hashes **raw float64 bytes**, and
   `-0.0` and `+0.0` differ in the sign bit — so any record whose canonical input
   contained a `-0.0` can never replay to its own `input_content_hash`.

Evidence chain:

- **Structural layer fully clean:** zero corruption, no trailing partial, terminal
  `COMPLETE` with matching count, all 3,895 `record_sha256` re-verify, zero duplicate
  row ids. The failure is purely the numerical replay.
- **Perfect partition:** 3,639 records fail, all with `INPUT_RATIOS_DO_NOT_MATCH_CONTENT_HASH`;
  256 replay clean (their zeros were all `+0.0`).
- **Decisive diff:** the corpus was rebuilt from the DuckDB via the runner's own
  `production_corpus_source` (identical code path; corpus hash reproduced `1d2319…`)
  and the canonical arrays compared element-by-element against ratio-rebuilt arrays.
  Across every sampled failing record, **every differing element is canonical `-0.0`
  (bits `0x8000000000000000`) vs replay `+0.0` (bits `0x0`)** — concentrated in `b_ub`
  (e.g., row 0: 16 zeros in `b_ub`, a sparse subset of them negative). No other
  difference of any kind exists.

The gate behaved **correctly**: the durable evidence genuinely cannot reproduce the
canonical problem bytes, so a governed PASS was rightly refused. The defect is in the
committed evidence-serialization path, present since the schema was authored, and was
unreachable by runs 1–3 (which never reached the row loop).

Two secondary findings, same delta:

- **Empty STOP detail:** in the verdict-fail path neither `stop_reason` nor
  `refusal_reason` is set, so the runner printed `"detail": ""` and the manifest
  carries no reason — root-causing required external forensics. `aggregate_verdict`
  should surface its first failing condition.
- **Same encoder on accepted evidence:** `z_exact_ratio` / `lam_exact_ratio` use the
  same `_exact_ratio_list`, so accepted arrays containing `-0.0` would fail
  `Z_RATIOS_DO_NOT_MATCH_HASH` identically. The input-hash check simply fires first.
  The 99-test suite and the realism/final-test evidence contain no `-0.0` round-trip
  case — a test-coverage gap to close with the fix.

## Remediation (OWNER DECISION — nothing executed)

- **Code delta required** (launcher untouched; evidence schema + replay only):
  replace the ratio encoding with a lossless one — recommended `float.hex()` strings
  (exact round-trip via `float.fromhex`, preserves `-0.0`, standard library) or
  `[n, d, signbit]` — applied to `input.*.exact_ratio`, `z_exact_ratio`,
  `lam_exact_ratio`, with the replay side updated symmetrically; surface the first
  failing `aggregate_verdict` condition as the STOP detail; add `-0.0` round-trip
  tests to the suite.
- This is a **schema change to the registered evidence format**: it requires a new
  review delta (v1.8), a new execution package / binding / countersignature chain
  (v5), and a fresh clean run. The v4 single-run countersignature is **consumed** —
  the registered command ran to completion.
- Run-4's checkpoint remains preserved on the box as evidence; the 3,895-row solve
  itself completed with zero numerical stops, but per the preregistration NO
  performance analysis is authorized from a non-PASS run, and none was performed.

## Gate-progression record (for perspective)

Run 1: refused at the Docker CLI flag parser. Run 2: refused at the in-container
preflight. Run 3: governance + preflight passed; refused at the output-root gate.
**Run 4: every gate passed, all 3,895 rows resolved and qualified; refused a PASS at
the terminal semantic-replay audit.** The remaining distance to a clean PASS is a
single evidence-encoding fix — the solvers, cascade, corpus identity, and governance
chain have now all been exercised end-to-end without defect.
