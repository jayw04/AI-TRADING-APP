# `tools/quarantine/`

Tools that **ran**, did something the architecture forbids, and are kept because deleting them
would erase the only record of what they did.

Nothing in this directory is a utility. Nothing here may be restored to a working path. A tool
lands here instead of in the bin when its *output* is still in the system — the artifact is
evidence about the corpus, not a program someone might want again.

**The rule for this directory:** a quarantined tool must have **no write path at all**. Not a
disabled flag, not a confirmation prompt, not a dry-run default. If it can still write, it is not
quarantined — it is merely inconvenient.

---

## `repair_premarket_gate_provenance.py` — quarantined 2026-08-23

**What it did.** It inferred a `provenance` value for SCAN-001 premarket-gate evidence records
from *then-current disk state* (`"live"` if `scanned_at` happened to be present, else
`"replayed"`), then wrote it into the records as though it were an observation. It also derived
`recorded_at` from each file's mtime — the filesystem's opinion at repair time, which its own
docstring conceded is the 16:30 ET back-fill clock, not the 09:25 scan clock.

**What it violates.** GAPPER Research Design **v2.1.1 §5.5**: every published record carries
immutable **write-time** provenance — creation time, source artifact and hash, producing
code/version, invocation/run id, and write class. Provenance is stamped when the record is
written, or it does not exist. It is never reconstructed afterwards, however good the inference.

**It is not hypothetical.** It ran once with `--apply` against the **live** corpus on `ec2-paper`
between 2026-07-16 and 2026-07-17. Measured 2026-08-23, read-only:

| | |
|---|---|
| Records in `/opt/workbench/data/premarket_gate_evidence` | **51** |
| Carrying the manufactured `provenance` string | **26** (20 `replayed` + 6 `live`), 2026-06-08 → 2026-07-16 |
| Carrying none | **25**, 2026-07-17 → 2026-08-21 |
| Schema tag on **both** shapes | `scan_001_premarket_gate/v1` |

⚠ **The consequence to carry:** in `/v1`, the **absence** of `provenance` does not mean
"unknown" — it means "written after the one-time repair", so it marks the **newest** records, not
the least known. Anyone reading `/v1` provenance as a quality, freshness, authenticity, admission,
or trust signal has it backwards. It is none of those things.

**Owner disposition, 2026-08-23 — Option B.** Full text in
`docs/design/Gapper/GAPPER_PremarketGateProvenance_Quarantine_Review_v1.0.md` §5. In short:

- All 51 `/v1` records stay **byte-unchanged**. ⛔ Not stripped. ⛔ Not back-stamped.
- The writer moved forward to **`scan_001_premarket_gate/v2`**
  (`apps/backend/app/services/premarket_evidence.py`), which stamps a genuine §5.5 provenance
  dict at creation, reusing the already-merged `app/research/gapper_stage0/provenance.py`.
- Every `/v2` record carries `provenance_semantics` so no consumer can mistake the legacy `/v1`
  **string** for the conformant `/v2` **structure**.
- ⛔ **No retroactive repair or backfill of provenance — permanently.** Enforced by tests in
  `apps/backend/tests/services/test_premarket_evidence.py`, which assert that the 16:30 ET
  outcome back-fill neither adds provenance to an unstamped `/v1` record nor normalises the
  legacy string on a stamped one.

**What was done to this file.** The `--apply` write loop and every write-mode `open()` were
removed. `--apply` still parses, solely so that reaching for it produces a loud refusal (exit 2)
naming the rule, rather than a silent no-op. What remains is a read-only inspector.

⭐ **Why it was quarantined rather than deleted.** It was untracked, absent from `main`, and
absent from the box — so deleting it would have left no record anywhere that those 26 records'
provenance was manufactured, or by what rule. Its commit into this directory is simultaneously its
first and its final commit.
