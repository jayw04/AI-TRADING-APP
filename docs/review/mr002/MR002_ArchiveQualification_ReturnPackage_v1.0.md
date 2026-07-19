# MR-002 Run-4 Archive-Qualification Return Package v1.0 — RESULT: PASS

- **Executed:** 2026-07-19, ONE execution, through accepted wrapper v2.0. Start
  `16:39:39Z` → publication `16:46:15Z` (~6m36s, dominated by the registered corpus
  regeneration). No retry occurred; no artifact was edited, deleted, recreated, or normalized.

## Invocation

- Command: `bash ~/mr002/launch/MR002_ArchiveQual_PublicationWrapper_v2.0.sh` (nohup, console →
  a fresh vacant file). The wrapper embeds the ACCEPTED Docker command byte-identically.
- Staged wrapper: `~/mr002/launch/MR002_ArchiveQual_PublicationWrapper_v2.0.sh` — staged
  no-overwrite (vacancy-refused first), sha256
  `11447ca2dfacf1f6ff963cd558d1c3a1471cf3d4a8c3ac0915c65b767dce7db8` (the accepted identity),
  6,623 B, locked 444.
- Pre-execution reconfirmation (all EXACT immediately before launch): docker ps -a = 0; /work
  detached `ecaa262…` tree `1cb95e25…` porcelain 0, read-only, 0 symlinks; /tools tool
  `3b60de2a…` 444/dir 555, 0 symlinks; /archive checkpoint `b9b0a948…` + manifest `1132d3b8…`
  regular non-symlink 444 root, dir 555 read-only, 0 symlinks; all three destinations ABSENT;
  validation/OOS sealed.

## Outcome

| Item | Value |
|---|---|
| Wrapper exit | **0** (validator succeeded: publication record created + all three outputs locked; console shows the full success path) |
| Tool exit | **0 = PASS** |
| Report disposition | **PASS** (exit↔disposition agreement validated by the wrapper) |
| Wrapper console | `MR002_run4_archive_qualification_wrapper_console.log` sha `9ba76af0…` — `tool_exit=0` + the three output hashes; nothing else |
| Report | sha256 `3a399021451a054301db7c2f87695652d52c2f38c6c78ba7f075d04f2320f072`, **2,854 B** |
| Stderr | sha256 `e3b0c442…b7852b855` (the empty-string SHA-256), **0 B — completely clean** |
| Publication record | sha256 `1a0eb4f9373d33b09a59b4fe12af4284cbcc970a043319b4d6dd70f34a5188ee`, 794 B — full JSON below |
| Final states | all three files `-r--r--r-- 444 ec2-user`, dev 66305, inodes 17486113 / 17486114 / 17486115 (report/stderr/publication) — the report/stderr inodes are the pre-Docker exclusive creations, unreplaced |

## Qualification findings (full report committed as `MR002_run4_archive_qualification_report.json`; byte-identical copy pulled and hash-verified)

- **Gates:** implementation commit, checkpoint hash, manifest hash, schema 2.0, archive
  read-only — ALL passed inside the container.
- **Population reconciliation — EXACT:** 3,895 rows; **3,639 formerly-failing / 256
  formerly-clean — matching the run-4 forensic counts precisely**
  (`counts_match_run4_forensics: true`).
- **Negative-zero placement patterns: exactly ONE across the whole population — `b_ub` only.**
  Every distinct pattern is therefore covered by the selection {row 0 (pattern representative),
  row 39 (lowest clean row)} — the owner's "every distinct placement pattern" requirement is
  satisfied in full, not sampled.
- **Row 0 (formerly failing):** 12 negative zeros in `b_ub` at flat indices
  [0,1,3,4,6,7,9,10,12,13,14,15] — consistent with the run-4 STOP forensics (which sampled
  diffs at b_ub indices 0,1,3,4,6…). Archived `input_content_hash` EQUAL to the canonical
  recompute; schema-2 replay defect NULL; **raw uint64 bit equality TRUE for all six
  components**; content-hash equality TRUE; record PASS.
- **Row 39 (formerly clean):** zero negative zeros anywhere; all equalities TRUE; record PASS.
- **Scope (as ruled):** input arrays only — this proves canonical input reconstruction +
  schema-2 exact-hex round-trip + raw binary64 bit equality + negative-zero preservation +
  input-content-hash equality. It does NOT claim z/lam equivalence, and no checkpoint was
  converted or repaired.

## Publication record (verbatim)

```json
{
 "record_type": "MR002_ARCHIVE_QUALIFICATION_PUBLICATION",
 "tool_exit": 0,
 "report_disposition": "PASS",
 "tool_sha256": "3b60de2a1d96d97152ea62b77c81ff25861d2e9582698b75f4e25b4dee8c7db5",
 "report_sha256": "3a399021451a054301db7c2f87695652d52c2f38c6c78ba7f075d04f2320f072",
 "report_bytes": 2854,
 "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
 "stderr_bytes": 0,
 "image_digest": "sha256:81e8d7a7be6bb022d7bde68e923ea6ef2a41b029390200e0240235f35aa173ea",
 "implementation_commit": "ecaa262480fb2b81fb0ba7d11b97721b617722bf",
 "checkpoint_sha256": "b9b0a94817deb540d768fc5b5909978e22f40f04e40a81e1bd5733a6637b7445",
 "manifest_sha256": "1132d3b8a3feeefe8c92107468b488cd31da52ec67df4abd78567d8879c96e40",
 "published_at_utc": "2026-07-19T16:46:15Z"
}
```

## Post-run rechecks

- `docker ps -a`: **0** (the `--rm` container auto-removed).
- /work still detached `ecaa262…`; /tools tool hash unchanged `3b60de2a…`; **archive hashes
  unchanged** (`b9b0a948…` / `1132d3b8…` re-verified after the run).
- Validation/OOS: **SEALED AND UNREAD** (the tool's corpus source reads the DEV window only, by
  frozen construction).
- Stderr contents: empty (0 bytes) — nothing to reproduce.

## Held per the verdict

Fingerprint regeneration, expected-pin changes, execution-package assembly, v5 attestation
work, and Run 5 are NOT started — awaiting your review of this result.
