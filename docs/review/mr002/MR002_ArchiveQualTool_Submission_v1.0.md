# MR-002 Run-4 Archive-Qualification Tool v1.0 — SUBMISSION FOR REVIEW

- **Date:** 2026-07-19 (laptop-side, per the closeout authorization: design, implementation, and
  local tests ONLY; the real archived Run-4 evidence was NOT accessed — it lives on the stopped
  launch host; nothing committed; EC2 not restarted)
- **Classification:** test-only diagnostic QUALIFICATION tooling — not registered execution code,
  not performance analysis, not a checkpoint converter.

## Design

`apps/backend/scripts/mr002_run4_archive_qualification.py` proves, on the immutable archived
Run-4 evidence, that the committed schema-2.0 encoding round-trips the canonical corpus arrays
bit-exactly — including every negative zero the v1 ratio encoding destroyed.

**Fail-closed gates (hard-pinned constants; REFUSED + exit 2 unless ALL hold):**
implementation checkout == `ecaa262480fb2b81fb0ba7d11b97721b617722bf` (proven via
`git rev-parse HEAD` on the mounted checkout; any failure to prove refuses); archive dir +
checkpoint + manifest non-symlink and non-writable; checkpoint sha256 ==
`b9b0a948…6637b7445` and manifest sha256 == `1132d3b8…79c96e40` (hashed BEFORE parsing);
reconstructed corpus hash == `1d231930…8390b`; committed `EVIDENCE_SCHEMA_VERSION` == `"2.0"`.

**Flow:** committed `read_checkpoint` reads the archived v1 checkpoint (read-only) → committed
`production_corpus_source` reconstructs the canonical arrays (required because the v1 ratios
cannot recover negative-zero bits) → every row is classified deterministically
(formerly-failing ⇔ its canonical input carries ≥1 negative zero — the byte-proven run-4 failure
criterion) and the distinct negative-zero placement patterns (the set of components carrying
negative zeros) are enumerated → the selection is deterministic by registered row identity: the
LOWEST row id representing each distinct pattern + the lowest formerly-clean row id + any
explicit `--rows`; a selection above the explicit bound (64) REFUSES rather than silently
truncating → each selected record is encoded through the committed producer path
(`_exact_hex_list` + shape, exactly as `numerical_evidence` builds the input block) and decoded
through the committed replay path (`verify_numerical_evidence_record` on a minimal non-qualified
diagnostic record + direct `_decode_exact_hex`), comparing **raw uint64 bits per component** and
**input_content_hash** (both the archived record's stored hash and the schema-2 recompute).

**Report:** ONE bounded JSON document on stdout — gates, population split
(with a cross-check against the run-4 forensic counts 3,639 / 256; a mismatch FAILS the
disposition loudly but is not a refusal gate, since those counts are evidence rather than pinned
identities), the pattern enumeration, and per-record `{row_id, negative-zero component counts +
locations (capped at 64 per component WITH the truncation recorded), uint64 bit-equality per
component, hash results, replay verdict, pass}`. Exit 0 only if everything passes. The tool
writes NOTHING anywhere (stdout only; proven by test).

**Scope disclosures:**
1. **Input arrays only.** `z`/`lam` are solver OUTPUTS — reconstructing them would require
   resolution, which this tool must never perform. The run-4 defect was proven on the input
   encoding; the z/lam encoders share the corrected `_exact_hex_list` and are covered by the
   committed 134-test suite.
2. **The committed corpus source internally replays the frozen capture path** over the DEV window
   (including the capture-time solve continuation), exactly as the registered runner does — the
   verdict mandates `production_corpus_source`, and the tool adds no solve, no cascade
   resolution, and no new solver-based evidence of its own.
3. The archived v1 records themselves are read only for row identity and their stored
   `input_content_hash`; no converted checkpoint, repaired record, or output replacement exists
   or is implied.

## Static composition (pinned by test)

The import set is EXACT (asserted by AST test): stdlib `argparse/hashlib/json/os/subprocess/sys`
+ `numpy` + exactly `EVIDENCE_SCHEMA_VERSION`, `_exact_hex_list`, `rec_content_hash` from the
committed cascade and `_decode_exact_hex`, `production_corpus_source`, `read_checkpoint`,
`verify_numerical_evidence_record` from the committed runner. Forbidden capabilities are asserted
absent as identifiers anywhere in the tool (population, orchestration, CheckpointSink/writes,
resolution, resume, validation/OOS, performance terms), no write-mode `open` exists, and the
default corpus-source binding IS the committed `production_corpus_source`.

## Artifact identities

| Artifact | SHA-256 | Bytes |
|---|---|---|
| `apps/backend/scripts/mr002_run4_archive_qualification.py` | `8f90b1a5bd855c9c04a743026da15c161e86d706bf05a548a0232655a8a05edb` | 11,780 |
| `apps/backend/tests/research/test_mr002_run4_archive_qualification.py` | `80f6f3c727a9c398d2e55d5c80e6c23bb515ca2b60341a8c3722435dce23724c` | 12,339 |
| `MR002_ArchiveQualTool_Delta_v1.0.patch` (both new files, git no-index diff) | `9e6c427e82c8d0ba9e445ce7169dbf355889f74c06468723d4630faa30a4028a` | 25,180 |
| `MR002_ArchiveQualTool_DevSuite.log` — **16 passed** | `928b441371fee18a610bfb0830b7f600e2e6df3f3da68db90c35e6cc61a558ea` | — |
| `MR002_ArchiveQualTool_Ruff.log` — all checks passed (content-identical to prior clean ruff logs, same hash) | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` | — |

Existing suites re-verified untouched after adding the tool: population-runner + launcher
**232 passed, 1 host-only skip** (134 + 98+1 — identical to the accepted v1.8a baseline).

**Local-test method:** functional tests run against a SYNTHETIC read-only archive (3 rows, two
distinct negative-zero placement patterns + one clean row) with the module's pinned constants
monkeypatched to the synthetic identities — the committed tool itself stays hard-pinned to the
real ones (asserted by `test_pins_are_the_governing_identities`). Refusal tests cover wrong
commit, checkpoint/manifest/corpus hash mismatches, writable archive file, schema-version drift,
selection over bound, and the loud forensic-count mismatch.

## Proposed exact host invocation (host phase, after requalification; for your review)

```
sudo docker run --rm --network=none \
  --mount type=bind,src=/home/ec2-user/mr002/numrepo,dst=/work,ro \
  --mount type=bind,src=/home/ec2-user/mr002/evidence/run4_replay_defect,dst=/archive,ro \
  --env=OPENBLAS_CORETYPE=HASWELL --env=OPENBLAS_NUM_THREADS=1 \
  --env=OMP_NUM_THREADS=1 --env=MKL_NUM_THREADS=1 \
  --env=PYTHONPATH=/work/apps/backend --workdir=/work/apps/backend \
  <v5-qualified image digest — pinned at host qualification> \
  python scripts/mr002_run4_archive_qualification.py --archive /archive --work-root /work \
  > /home/ec2-user/mr002/launch/run4_archive_qualification_report.json
```

Preconditions this implies (host-phase checklist items): numrepo re-staged as a clean detached
checkout of `ecaa262` with the registered DB inside (the tool's commit gate enforces this);
archive mounted read-only exactly as locked at preservation; BLAS pinning env identical to the
registered template; the report lands host-side via stdout redirection — the tool itself writes
nothing. Whether this invocation is added to the v5 attested-command family or executed as a
separately-authorized qualification step is your ruling.

## Requested owner actions

1. Review + accept (or amend) the tool design, source, tests, and the proposed invocation.
2. On acceptance: commit authorization (tool + tests + these review artifacts; logs via
   `git add -f`). NOTE: committing the tool changes the tree — if it lands before the v5 chain
   is produced, the tool's own commit pin must be updated to the NEW registered implementation
   commit in the same reviewed change (or the tool commits first and `ecaa262` is superseded as
   the pin) — your sequencing ruling, flagged here so it cannot surprise the host phase.
