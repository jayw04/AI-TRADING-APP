# 2026-08-12 — Accidental truncation of the MR-002 session-memory file

**Status:** CLOSED (recovered, bounded, no governed evidence affected)
**Severity:** Low for the program, high as a process lesson
**Scope:** Claude Code session memory only — `~/.claude/projects/C--LLM-RAG-APP-ai-trading-app/memory/mr002_mean_reversion_program.md`

---

## What happened

While prepending a new status block to the MR-002 session-memory file, a helper script executed:

```python
io.open(path, "w", encoding="utf-8").write(out)
```

`out` contained an emoji written as two `\uXXXX` escapes rather than one `\U0001F51C` escape, which
produces a **lone surrogate pair**. The UTF-8 encoder rejected it and raised `UnicodeEncodeError`.

`open(path, "w")` truncates the file **at open time**, before the write is attempted. The exception
therefore left the file at **0 bytes**. Roughly 323 KB / ~1,065 lines of MR-002 navigation notes were
destroyed by a single call. The memory directory is not under version control and has no backup.

## What was NOT affected

**No governed MR-002 evidence artifact was lost, altered, or reconstructed from memory.** The
session-memory file is navigation context. Every governed artifact — the preregistration, the
Phase 3A/3B specifications, the P1–P12 prerequisite register, the evaluator binding and image
manifests, the custody and access-history records, the D3 submission, the P12 grant, and the
authorization state — lives in the repository, in the sealed S3 store, or in AWS control-plane state,
and none of them were touched. The validation partition was not read, no credential was assumed, and
the single granted validation opening remains unconsumed.

## Recovery method

Every mutation of the file is recorded in the Claude Code session transcripts under
`~/.claude/projects/C--LLM-RAG-APP-ai-trading-app/*.jsonl` as `Write` / `Edit` tool inputs. Recovery
replayed that mutation history forward from the most recent **unlimited** `Read` snapshot
(2026-07-18T21:14, 161 lines — the whole file at that moment; a `Read` carrying a `limit` is only a
prefix and cannot serve as a base). 141 operations were replayed: 139 applied, 2 missed. Both misses
were individually checked and proven benign — one was superseded by a successful retry seconds later,
the other targeted a paragraph that a later edit removed regardless.

Recovery scripts are preserved in the session scratchpad: `recover_mem2.py` (provenance scan),
`replay2.py` (replay), `restore_mem.py` (verified restore).

## Verified vs. unrecovered

| | |
|---|---|
| **Verified exact** | Recovered lines 1–110 are byte-identical to a ground-truth `Read` captured minutes before the truncation; the only difference is the harness-maintained `modified:` stamp. Block headers land on the exact line numbers recorded by a pre-truncation `grep -n`: 11, 69, 105, 140, 170, 241, 338, 380, 426, 445, 513, 558. |
| **Restored file** | 966 lines / 321,668 bytes (including ~91 lines of newly added content). |
| **Original file** | ~1,065 lines / ~323 KB. |
| **Unrecovered** | ~190 lines. Because alignment is exact through line 558, the gap lies entirely in the deepest **pre-2026-07-19** tail (Stage-3 run history). Everything from 2026-07-19 forward is intact. |

**966 reconstructed lines is not proof that the historical memory is complete.** The exact alignment
through line 558 is recovery evidence for the recovered range only.

## Owner ruling (2026-08-12)

1. Treat the reconstructed memory file as **convenience context, not authoritative MR-002 evidence**.
2. Do not spend further effort reconstructing the missing ~190 historical lines unless a concrete
   decision actually depends on them.
3. **Git and the governed evidence records are the source of truth for MR-002.** The recovered memory
   may aid navigation, but it must never resolve an identity, ruling, hash, authorization, or
   historical fact where the repository record differs or is absent.

## Prevention

- **Never open a file you cannot reproduce in `"w"` mode.** Build the complete new content in memory,
  write it to a **temp path**, re-read and assert on it (size floor plus required content markers),
  and only then replace the target. This is absolute for append/prepend-only records — memories,
  ledgers, evidence logs.
- The same trap applies to `>` redirection, `Set-Content`, `New-Item -Force` on an existing file, and
  copying onto a live target.
- Prefer an anchored edit over a rewrite script: a failed anchor leaves the file untouched.
- Emoji above U+FFFF must be written as `"\U0001F51C"` (8-digit) or as the literal character. Two
  `\uXXXX` escapes produce lone surrogates that no UTF-8 encoder accepts — and the failure lands
  *after* the truncation.
- On Windows, set `PYTHONIOENCODING=utf-8`; a `cp1252` console aborts scripts mid-way for the same
  class of reason.
