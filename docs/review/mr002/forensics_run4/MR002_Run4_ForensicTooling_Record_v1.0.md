# MR-002 Run-4 Forensic Tooling Record v1.0

**Classification (per the run-4 evidence-replay verdict, 2026-07-19):**

> READ-ONLY POST-STOP DIAGNOSTIC TOOLING
> NOT REGISTERED EXECUTION CODE
> NOT PERFORMANCE ANALYSIS
> NOT PART OF THE QUALIFIED RUN

These four scripts were written AFTER the run-4 STOP to root-cause the non-PASS
disposition. They read the durable run-4 evidence and the bound source; they write
nothing, mutate nothing, and touch no solver outcome semantically. They must not be
promoted into production, replay, or registered-execution tooling; any future reuse
requires its own review under whatever chain then governs.

## Script identities

| Script | SHA-256 | Bytes |
|---|---|---|
| `mr002_run4_structural_diag.py` | `6c945f4bd345e32f7650d432871e8f2532dd8f6983e58dddddf7917ce209c31c` | 4,025 |
| `mr002_run4_replay_diag.py` | `382ed5b6ec8dc937bf3e236e448f95490d63d84fe2a1934b8c8f3e81eda934e5` | 1,777 |
| `mr002_run4_zero_diag.py` | `ab58df3f951815b6921499bdd0938c01448e74a078ef3008fecb944e2878df74` | 2,225 |
| `mr002_run4_corpus_diff.py` | `cad3c30d58461bcdb8a5ca2d4c306de1611c21f23c2c5042cbb1238e9e38f1ce` | 3,109 |

## Execution environments

**Stage 1 — `mr002_run4_structural_diag.py`** ran on the c6a HOST (no container):

```
python3 /tmp/mr002_run4_structural_diag.py
```

Pure-stdlib (json/hashlib) structural replay of `read_checkpoint` + the
non-numerical `aggregate_verdict` conditions against
`/home/ec2-user/mr002/out/cleanrun/MR002_Stage3_CleanRun_checkpoint.jsonl` (read).
Output: stdout only. Result: 3,896 lines = 3,895 records + terminal `COMPLETE`;
zero corruption; zero trailing partial; all `record_sha256` re-verify; zero
duplicate row ids → structural layer clean.

**Stages 2–4 — the other three scripts** ran inside the pinned Stage-3 image
`sha256:81e8d7a7be6bb022d7bde68e923ea6ef2a41b029390200e0240235f35aa173ea`
(`--rm --network=none`), with every mount READ-ONLY — including `/out`, which the
registered run mounted writable:

```
sudo docker run --rm --network=none \
  --mount type=bind,src=/home/ec2-user/mr002/numrepo,dst=/work,ro \
  --mount type=bind,src=/home/ec2-user/mr002/out,dst=/out,ro \
  --mount type=bind,src=/tmp/<script>.py,dst=/diag.py,ro \
  --env=PYTHONPATH=/work/apps/backend --workdir=/work/apps/backend \
  sha256:81e8d7a7be6bb022d7bde68e923ea6ef2a41b029390200e0240235f35aa173ea \
  python /diag.py
```

(`mr002_run4_corpus_diff.py` additionally ran with the registered BLAS pinning env
`OPENBLAS_CORETYPE=HASWELL OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`,
matching the attested template, since it re-derives the corpus.)

Reads: the checkpoint, the run manifest, the bound source tree at `/work`
(numrepo, commit `d26bd9e` / tree `c0e52d8e`), and — corpus-diff only — the
registered DuckDB `/work/apps/backend/data/mr002_research.duckdb`. Writes: none
(stdout only; all mounts ro; containers auto-removed).

## Outputs (summarized; full detail in the stop report)

- `mr002_run4_replay_diag.py`: `verify_numerical_evidence_record` over all 3,895
  records → **3,639 defects, all `INPUT_RATIOS_DO_NOT_MATCH_CONTENT_HASH`**; 256 clean.
- `mr002_run4_zero_diag.py`: mechanism check (`(-0.0).as_integer_ratio() == (0, 1)`;
  `tobytes` distinguishes signed zeros) + correlation: every record contains zeros;
  defect status partitions 3,639 / 256 exactly.
- `mr002_run4_corpus_diff.py`: corpus REBUILT from the DuckDB via the runner's own
  `production_corpus_source` (corpus hash reproduced
  `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b`); canonical
  arrays element-diffed against ratio-rebuilt arrays across 40 sampled failing
  records → **every differing element is canonical `-0.0` (bits
  `0x8000000000000000`) vs replay `+0.0` (bits `0x0`)**; no other diff kind exists.

One incidental note: `mr002_run4_zero_diag.py` and `mr002_run4_corpus_diff.py` were
authored to run to completion; the recorded conclusions above are from their actual
executions on 2026-07-19 (~10:00–10:40Z), logged in the session transcript and
reflected byte-exactly in stop report v4.0.
