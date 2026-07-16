# MR-002 — Sample A evidence recovery + archive-integrity hash note

A `git stash -u` used to switch between the MR-002 and momentum branches left three Sample A
evidence files **untracked** — they were captured by the stash rather than committed by the §3–§6
commit (`c0615e2`) as intended:

* `MR002_SampleA.json`
* `MR002_BinaryArchiveIntegrity.json`
* `MR002_ComplementaryCoverage_LineageAnnotation.md`

They are recovered from the stash and committed here. The load-bearing artifacts
(`MR002_DirectedRounding_Correction.json`, `MR002_DirectedRounding_Inventory.jsonl.gz`, the report,
and `MR002_SampleB_Stop_Report.md`) were already committed and are unaffected. `git stash` is
repository-global — a recurring hazard when moving between branches — and this is the failure mode.

## The archive-integrity hash discrepancy (benign, disclosed)

The sealed `MR002_DirectedRounding_ImmutableRecord.json` (commit `c130149`) recorded
`archive_integrity.sha256 = c8c4a52d77f2f2bfba75c3dddaecd5d5bce42ba6fb66affb04a33489e36ef7f3`.
The committed `MR002_BinaryArchiveIntegrity.json` hashes to
`58afb21ccb2916277c4631662cd41547eec5cf9ad92c95640cebaa01a85545c3`.

**Cause:** `MR002_BinaryArchiveIntegrity.json` embeds `git_blob_id_head` for each archive — a
**HEAD-relative** value — so the file is commit-dependent by construction. Hashing a HEAD-dependent
artifact into a record sealed at one commit is only meaningful at that commit; as commits accrued the
recorded value no longer matched the working tree.

**Substance is unchanged and reproducible.** Regenerating the archive-integrity record
deterministically at the current HEAD reproduces `58afb21…` exactly, with identical conclusions:

```
archives evaluated                 10
archives with embedded CRLF pairs   8   (max 297)
round-trip hash changes             0
git text attribute on archives  unset  (every one)
```

**Disposition.** The sealed immutable record is **not edited** — it stays as sealed. Its
`archive_integrity.sha256` is a seal-time working-tree value; the authoritative artifact is the
committed, deterministically-reproducible `MR002_BinaryArchiveIntegrity.json` at
`58afb21…`. The Sample A verdict (50/50 PASS) and the directed-rounding correction (27,265 verdicts,
0 flips) rest on `MR002_SampleA.json` and `MR002_DirectedRounding_Correction.json`, whose recorded
hashes match exactly.

**Lesson recorded:** hash the *substantive content* of an artifact into a sealed record, or commit
the artifact first — never hash a HEAD-relative derived file into a commit-sealed manifest. And do
not use `git stash` to move work between branches.
