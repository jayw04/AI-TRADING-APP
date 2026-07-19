# MR-002 Stage-3 — Run 5 Consolidated Closeout Package v1.0

Run 5 = **GOVERNED PASS**, adjudication ACCEPTED. This is the single consolidated closeout for
the five-task evidence group. No performance interpretation; validation/OOS sealed and unread.

## A. Commit identities

| Commit | Contents |
|---|---|
| `73ac6da55d0248daea24b831fd9480819307fc81` | Run-5 return package + byte-verified manifest / exec log / start-utc |
| `a654d44520c857cb4da3e3ea9484c0e288212470` | one-run execution countersignature (`7f6e3c82…`) |
| `8a47d1bbddf6053357585a79742d59a7387e53d8` | Phase-B execution binding (`f4fb3c74…`) |
| `d99308fe5ef0a264b8532352641c65cd5727e1cb` | v5 attestation (`e82468c3…`) + receipt (`d69b95be…`) |
| `ccca22033859b71ec4d1e67e39d63afe08358062` | v5 qualification package (pins/manifest/pkg/report/realism) |

This closeout adds (committed together): Run-5 publication record
`MR002_Stage3_Run5_PublicationRecord_v1.0.json` sha `b73f2957131d4322fb2fede3da0c7e3f5e1516b56a84c318d83bb15faccf4e05`,
closure record `MR002_Stage3_Run5_ClosureRecord_v1.0.json` sha
`0a67826fedda96eb0924563d0219f0e5dce8829b94a3c5a7ce5af7b57b8b9add`, and this package.

## B. Execution result (accepted)

3,895 / 3,895 expected/processed/qualified, 0 stopped, terminal `COMPLETE`, disposition **PASS**,
`passed:true`, `evidence_persisted:true`, `windows:["dev"]`. Solver split 3,890 QUADPROG_SQRT +
5 PIQP_P2. Start `2026-07-19T21:36:06.461Z` → terminal `21:43:19.7Z`, container `02e8584e`
(`--rm`), exit 0, no sidecars, no retry.

## C. Schema-2 defect resolution

Aggregate replay accepted 3,895/3,895; 3,895 `evidence_schema_version:"2.0"` markers; 23,370
`exact_hex` fields; **0** legacy `exact_ratio`. The Run-4 negative-zero replay defect is closed —
schema 2.0 preserves the full registered population, including `-0.0` bit patterns, through
publication and terminal replay.

## D. Local preservation proof (committed)

| Artifact | SHA-256 | bytes |
|---|---|---|
| Run manifest (in git @ 73ac6da) | `27fe7624…1431fa1f` | 130,845 |
| Exec log (in git @ 73ac6da) | `48b5d478…986209a2` | 2,836 |
| Checkpoint (host + S3; too large for git) | `511d11f52ce2751aacbbe78c2b96d7ce712b5dbf3161fa7b2ed0da5df5bb02ae` | 49,612,687 (3,896 lines) |
| Row-manifest (in manifest) | `699b17df…94d7ac7eb` | — |
| Corpus | `1d231930…8390b` | — |

## E. Remote archive proof (byte-exact, versioned, no-overwrite)

Bucket `workbench-backups-219024422756` (us-east-1, **versioning Enabled**, SSE AES256). Keys
were vacant before upload (no-overwrite).

| Object | S3 URI | VersionId | ChecksumSHA256 (base64) | ContentLength |
|---|---|---|---|---|
| checkpoint | `s3://workbench-backups-219024422756/mr002/run5/MR002_Stage3_CleanRun_checkpoint.jsonl` | `Zz_TSuBsU.sMT7q8lpoaJieWbETfZdtq` | `UR0R9SzidRqsu+eMK5bXznErXb8xYfp7LtDaXfW7Aq4=` | 49,612,687 |
| run manifest | `s3://workbench-backups-219024422756/mr002/run5/MR002_Stage3_CleanRun_Manifest.json` | `kOdvCn5Ygsq2WvxfRE9XfbyfnY9UtXUj` | `J/52JKGjtOgyiDPyj2BestY26m00UTp1wfOWEBQx+h8=` | 130,845 |

**Equality demonstrated independently:** the checkpoint's server-side `ChecksumSHA256`
`UR0R9Szi…` decodes to hex `511d11f5…` (== local), and `head-object` ContentLength `49,612,687`
== local byte length. No compression, conversion, or normalization — a raw byte-for-byte
`put-object`. **The host checkpoint copy is PRESERVED (not deleted).**

## F. One-run governance closure

authorized 1 / observed 1 / containers 1 / retries 0 / resumes 0 / checkpoint-reuse 0. The v5
nonce, attestation, receipt, binding, authorization, and countersignature are **consumed and
closed**; they may never authorize another execution. No v1–v4 artifact was reused; the closed
v4 input set stays quarantined at `~/mr002/inputs_v4_closed_quarantine/`.

## G. Host-state inventory (post-run, pre-stop)

Instance `i-0f3ceafdd4294c572` (c6a.large); `docker ps -a` 0; `/inputs` 9 files / 0 symlinks;
`/out/cleanrun` 2 files (checkpoint `511d11f5…` + manifest `27fe7624…`); Run-4 archive unchanged
(`b9b0a948…`); `/work` detached `ecaa262…`, porcelain 0; keys `600`; root disk 19% used.
Validation/OOS **SEALED AND UNREAD**.

## H. Dispositions applied

- Checkpoint: **RETAINED**; remote byte-exact archive **demonstrated**; **host deletion HELD**
  pending a later explicit cleanup ruling.
- Instance: **STOPPED (not terminated)** after this closeout + verified archive (see the stop
  confirmation appended by the closing step); **termination HELD** until you review this package.
- Performance interpretation: **HELD**. Production promotion: **NOT AUTHORIZED**.

## I. Research boundary (unchanged)

Stage-3 execution qualification PASS · schema-2 evidence replay PASS · numerical population
completion PASS. This does **not** establish strategy performance, economic value, or OOS
validity. Validation/OOS remain sealed; those are a separate, later, explicitly-authorized phase.
