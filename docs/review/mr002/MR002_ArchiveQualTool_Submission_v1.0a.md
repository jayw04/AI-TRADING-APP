# MR-002 Run-4 Archive-Qualification Tool v1.0a — SUBMISSION FOR REVIEW (blocking corrections)

- **Date:** 2026-07-19 (laptop-side; real archive untouched; EC2 still stopped; nothing committed)
- **Scope:** the five blocking items from the v1.0 review, each implemented and tested. This is
  the ACTUAL v1.0a delta — tool and test sources both changed (identities below).

## Corrections

### 1. `/tools` separation — RESOLVED (and it dissolves the v1.0 sequencing flag)

The tool is now specified and tested as a STANDALONE FILE mounted separately from the
implementation checkout: `/work` = clean detached checkout at `ecaa262…` (imports resolve via
`PYTHONPATH=/work/apps/backend`), `/tools` = this reviewed script (read-only), `/archive` = the
immutable evidence (read-only). The command executes `python /tools/mr002_run4_archive_qualification.py`
— never `python scripts/…` from `/work`. Because the tool is not part of `/work`, its
`PINNED_IMPLEMENTATION_COMMIT = ecaa262…` stays exactly the frozen evidence-schema commit with no
sequencing interaction. `test_v10a_runs_as_standalone_tools_file` proves file-path execution from
outside the checkout with a bounded JSON result.

### 2. Total failure containment — one bounded JSON, always

`main()` now guarantees EXACTLY ONE bounded JSON document on stdout for every outcome:
PASS = exit 0, FAIL = exit 1, REFUSED = exit 2. Specifically: argparse failures raise through a
`_RefusingParser` (no SystemExit/usage dump — `ARGUMENT_PARSE:*`); every gate/reconciliation
refusal is typed; ANY unexpected exception (corpus source, checkpoint reader, gates) becomes
`UNHANDLED:<type>:<bounded msg>` REFUSED; a per-record qualification fault is contained into that
record (`pass: false, error: <bounded>`) with overall FAIL; and report-serialization failure
falls back to a minimal `REPORT_SERIALIZATION_FAILED` JSON, exit 2. All detail strings bounded
at 500 chars. Tests cover each path, including fault injection into the gate layer.

### 3. Exact row-identity reconciliation (`_reconcile_rows` + `_parse_explicit_rows`)

Refusals (each tested): missing or non-COMPLETE terminal (`ARCHIVE_TERMINAL_NOT_COMPLETE`);
terminal count ≠ the new hard pin `EXPECTED_N_RECORDS = 3895` (`ARCHIVE_TERMINAL_COUNT_MISMATCH`);
record count ≠ 3,895; non-integer archived row ids (`ARCHIVE_ROW_ID_INVALID`); duplicate archived
row ids (`DUPLICATE_ARCHIVED_ROW_IDS`, first 5 listed); corpus population count ≠ 3,895;
archive/corpus row-set mismatch (`ARCHIVE_CORPUS_ROW_SET_MISMATCH:missing=[…]:extra=[…]`,
bounded); invalid `--rows` entries — non-integer or absent from the corpus (`INVALID_ROW_ID`).

### 4. Strict path types (`_strict_path`)

Archive must be a real directory; checkpoint and manifest real regular files; all three
non-symlink AND non-writable; missing paths named explicitly. Tested: archive-is-a-file,
checkpoint-is-a-directory, symlinked checkpoint (privilege-aware skip on Windows), writable file.

### 5. Host-only real-Docker mount test

`test_v10a_real_docker_mount_semantics` — env-gated (`MR002_REAL_DOCKER_ARCHIVE_TEST=1`,
`MR002_REAL_DOCKER_IMAGE`, `MR002_REAL_DOCKER_WORK`), skipped locally, follows the accepted
launcher-suite real-CLI-test precedent. In the ACTUAL Linux container it probes `_strict_path`
against real bind mounts and asserts: ro mounts PASS all three probes; a writable mount refuses
`*_WRITABLE`; a symlinked checkpoint refuses `*_IS_SYMLINK`; a directory-typed checkpoint
refuses `*_NOT_A_REGULAR_FILE`.

## Suite

**35 passed + 1 host-only skip** (was 16): the 16 v1.0 tests (fixture updated for the
`EXPECTED_N_RECORDS` pin) + 19 new v1.0a cases (standalone-/tools execution, argparse containment
×2, invalid `--rows` ×2, duplicate ids, row-set mismatch, non-integer id, missing/FAILED
terminal, wrong terminal count, archive-not-dir, checkpoint-is-dir, symlink, corpus-source
exception, malformed checkpoint, per-record fault containment, serialization-failure fallback,
gate-layer fault containment, `EXPECTED_N_RECORDS=3895` pin assertion, real-Docker host test).
Population-runner + launcher suites re-verified untouched: **232 passed, 1 host-only skip**.
Ruff: all checks passed.

## Artifact identities

| Artifact | SHA-256 | Bytes |
|---|---|---|
| `apps/backend/scripts/mr002_run4_archive_qualification.py` (v1.0a) | `3b60de2a1d96d97152ea62b77c81ff25861d2e9582698b75f4e25b4dee8c7db5` | 15,225 |
| `apps/backend/tests/research/test_mr002_run4_archive_qualification.py` (v1.0a) | `0478369e9ba324392737df67bebdb1c0942bf664cd2cc7762396a80071e94509` | 25,515 |
| `MR002_ArchiveQualTool_Delta_v1.0a.patch` (both files, supersedes v1.0) | `3e11a2fc14e7bfcf4ecd71f871bb500b56d998fb96a0d497b40e6cd72a595999` | 42,144 |
| `MR002_ArchiveQualTool_v10a_DevSuite.log` — 35 passed, 1 skipped | `10c49c198663ae8d9d9d729fec6d41e2c2e0b4d9a1841c42adce7757f67f9559` | — |
| `MR002_ArchiveQualTool_v10a_Ruff.log` — all checks passed (content-identical to prior clean ruff logs) | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` | — |

## Proposed exact host invocation (v1.0a execution model)

```
sudo docker run --rm --network=none \
  --mount type=bind,src=/home/ec2-user/mr002/numrepo,dst=/work,ro \
  --mount type=bind,src=/home/ec2-user/mr002/tools,dst=/tools,ro \
  --mount type=bind,src=/home/ec2-user/mr002/evidence/run4_replay_defect,dst=/archive,ro \
  --env=OPENBLAS_CORETYPE=HASWELL --env=OPENBLAS_NUM_THREADS=1 \
  --env=OMP_NUM_THREADS=1 --env=MKL_NUM_THREADS=1 \
  --env=PYTHONPATH=/work/apps/backend --workdir=/work/apps/backend \
  <v5-qualified image digest — pinned at host qualification> \
  python /tools/mr002_run4_archive_qualification.py --archive /archive --work-root /work \
  > /home/ec2-user/mr002/launch/run4_archive_qualification_report.json
```

Host preconditions: `/work` = clean detached `ecaa262` checkout with the registered DB inside
(the commit gate enforces it); `~/mr002/tools/` holds the reviewed tool byte-verified against the
accepted identity `3b60de2a…` before launch; archive mounted exactly as locked at preservation;
the host-only Docker mount test runs during requalification with the same image before this
invocation. Unchanged v1.0 disclosures remain in force (input-arrays-only scope; the corpus
source internally replays the frozen capture path exactly as registered).

## Requested owner actions

1. Review + accept v1.0a (this doc + patch `3e11a2fc…`).
2. On acceptance: commit authorization (tool + tests + v1.0/v1.0a review artifacts; logs via
   `git add -f`).
