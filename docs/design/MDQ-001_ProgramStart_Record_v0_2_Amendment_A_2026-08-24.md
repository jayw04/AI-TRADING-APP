# MDQ-001 — Program-Start Record v0.2, Amendment A (post-start findings, 2026-08-24)

| Field | Value |
|---|---|
| Document | **Amendment A to `MDQ-001_ProgramStart_Record_v0_2.md` §6** |
| Authority | **Append-only, limited to §6.** Owner-approved 2026-08-24. |
| Amends | **§6 only.** Adds findings 5–7. Sections 1–5 and 7–9 of v0.2 are carried forward **unchanged** and are not modified by this document. |
| Written | 2026-08-24, pre-market (before the 09:25 ET sampler) |
| **Base document identity** | `docs/design/MDQ-001_ProgramStart_Record_v0_2.md` — **19,490 B (LF)**, sha256 **`2ea77393c91cc06edb04ae0a5789f91df8e11f7f7b837df4f97c8cd2da74702a`**, git blob `16a2fd4a8e377a694db9915c2ff4ea663203eed5`. This amendment attaches to that exact base; if the base does not hash to this value, resolve the discrepancy before relying on either document. |
| Basis | Owner ruling 2026-08-20 ("record as a post-start finding in Program Start Record §6; do **not** spend a governance act re-latching") · registration signed §8 · `MDQ-001_Collector_Identity_Approval_2026-08-19.md` |
| Governance stance | **Recording instrument, not a decision instrument.** It approves nothing, re-latches nothing, and adjusts no K-criterion, threshold, tolerance, denominator, or evaluability clause. If it conflicts with the registration or an owner ruling, those control and this record is wrong. |
| Decision owner | Platform owner (Jay Wang) |

> **Scope statement (binding).** Amendment A changes **only** the §6 matter authorized by the owner ruling of 2026-08-20. It does **not** reopen, revisit, or qualify **K1–K6**, **D0**, the **symbol or period holdouts**, the **PX rulings**, or the **approved producer identity**. Each of those remains exactly as established by its own signed instrument.

> **Why an amendment rather than v0.3.** The owner's 2026-08-20 ruling was narrow: record the producer-identity move as a post-start finding. Reissuing the whole record would also require restating §7 "Effective state", which later signed and merged acts have changed — cited here **by identity only**, deliberately without reproducing their substance: `d43817b` (PR #647) · `dcc2c97` (PR #657) · `07f745b` (PR #659). Their content governs from those instruments, not from any summary of them. This amendment therefore touches **§6 and nothing else**; §7 is refreshed when the owner next reissues the record.

---

## §6, finding 5 — the deployed producer commit moved twice more after D0

The commit-label component of the deployed producer identity has now moved **three times** since D0.
It is a **label** move in every case: the governed collector substance is unchanged.

| Event | Deployed commit | Evidence basis |
|---|---|---|
| D0 producer (2026-08-19) | `86d8cbd5a6201a8938062c35f915604b08652fbe` | Program-Start Record v0.2 §4.1 |
| 2026-08-19 22:05 EDT | `9e5cf65f7212…` (#646) | Prior session record, 2026-08-20 |
| 2026-08-21 | `50efc2fb8f8e…` (#654) | Prior session record, 2026-08-21 |
| **2026-08-23 12:00:51 EDT (current)** | **`0344337787a6ce27df64995f7a556b19a4bf297a`** (#666) | **Measured 2026-08-24 08:34 EDT** — `stat /opt/workbench/app/.deploy_src_sha` |

⭐ Only the last row was measured in this session. Rows 2 and 3 are carried from prior session records
and are **not** re-verified here; the conclusion below does not depend on them, because it is proven
against the git history and against the running container directly.

### The five approved collector blobs are byte-identical across the entire deploy history

`git cat-file blob <commit>:<path> | sha256sum` — the authoritative LF-normalised form:

| File | SHA-256 | `86d8cbd` | `9e5cf65` | `50efc2f` | `0344337` | `4c4a2b1` (main HEAD) |
|---|---|:--:|:--:|:--:|:--:|:--:|
| `app/research/capture/__init__.py` | `f38fbd649430ce17e507920aab0c9ed284207b096688d1eed7b5f4fadf142fba` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `app/research/capture/collector.py` | `e5e030a97eed0a64d4abeb621484e8069dd152dde27ccf75f254f9a1286ebd97` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `app/research/capture/identity.py` | `588e258f4b6ee6b88f250c6ec77100e7dc2a8690f1502ca1567de11f452b63d8` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `app/research/capture/store.py` | `22c3405e5acbba6c7a86ef71468898ec0515126399770b02dfb42373f211e222` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `scripts/mdq_collector.py` | `b5feb2a9c84521c1a624d4436577dcc093f2451c13dd17dda8ca1a52261ab7e2` | ✓ | ✓ | ✓ | ✓ | ✓ |

All five match the values frozen in `MDQ-001_Collector_Identity_Approval_2026-08-19.md` exactly.

**Verified in the running container, not only in git** (CRLF-normalised per the approval artifact's
rule, `tr -d '\015' | sha256sum` inside `workbench-backend`, 2026-08-24 08:36 EDT): all five runtime
files return the same five hashes. The image is
`sha256:fc76c0ed70158978a466494852a07b27cdb750725c35e09a986d30e6f7fc7d85`, built 2026-08-23T16:16:59-04:00.

⇒ `collector_version` remains `mdq-collector/0.1.0` and `collector_code_identity` continues to score
against an unchanged governed tuple. **The 2026-08-21 partition manifests, written after the second
move, still stamp `mdq-collector/0.1.0`, `credential_fingerprint b56421a28128`,
`account_number PA3BGKRLH2AP`, and `universe_sha256 a022e399…f563`** — the moves reached no byte of evidence.

**Characterisation: commit-label drift, verdict-neutral.** Per the 2026-08-20 ruling, recorded — not re-latched.

⭐ The blob-hash component of the approved tuple is what makes this benign and provable. A
version-string-only approval would have concealed all three moves, since the string never changed.
This is the second occasion on which that design decision has done real work.

---

## §6, finding 6 — the deploy label and the image were written by separate acts, 4h16m apart

On 2026-08-23 the deployed-sha stamp and the backend image were produced at materially different times:

| Artifact | Timestamp |
|---|---|
| `/opt/workbench/app/.deploy_src_sha` (mtime) | 2026-08-23 **12:00:51** EDT |
| Backend image `fc76c0ed7015` created | 2026-08-23 **16:16:59** EDT |
| `workbench-backend` container started | 2026-08-24 10:08:58 UTC |

**Characterisation: a provenance-reporting weakness, not a corpus defect.** `.deploy_src_sha` is a
*claim* about which source the running image was built from, and the two were not written atomically,
so the label alone does not establish what is running. It is recorded because a future reader who
trusts the label unverified would be trusting an artifact that demonstrably can lag its image by hours.

⭐ **Mitigation already in force, and it is the reason this finding is benign:** the governed identity
is the tuple — version + commit + five blob hashes — and finding 5 verifies the blob hashes **inside
the running container**, which no label can misreport. Continue to verify runtime blobs directly at
the start of every evidence session; never inherit a deployed identity between sessions.

---

## §6, finding 7 — the box trails `origin/main`, and this is not a defect

At 2026-08-24 08:34 EDT the box runs `0344337` while `origin/main` is `4c4a2b1` — five commits behind
(#667, #658, #668, #511, #670; LOW-001, Opportunities Slice 3, SCAN-001 evidence).

**Characterisation: expected operational state, recorded for completeness.** None of the five commits
touches the approved collector files — the table in finding 5 shows the five blobs are identical at
`4c4a2b1` as well, so a future redeploy to current `main` would also preserve the governed identity.
That is stated as a *fact about those commits*, not as advance authorisation for any redeploy.

⛔ A redeploy remains a **capture-availability event**: it shares one filesystem with the capture root,
and the free-space guard must be re-run against live box state before the next 09:25 ET sampler.

---

## Durability confirmation — the D0 partition is byte-intact

Not a finding; recorded because it is the property the findings above could have threatened.

Re-hashed on the box 2026-08-24 08:38 EDT, after three deploy-label moves and at least one image
rebuild, all six files of the 2026-08-19 partition return **exactly** the SHA-256 values frozen in
Program-Start Record §5.5:

| Feed | File | SHA-256 | Result |
|---|---|---|:--:|
| iex | `manifest.json` | `151e20add9d62a7c8167c75c581f8c7c972997134873b1fec20fc5a751116336` | MATCH |
| iex | `quotes/samples.jsonl` | `e1c2eb87ebb6b6a244811364f1ce7b8f60be7b81f696684dd36ead5736b2fe4c` | MATCH |
| iex | `bars/bars_1min.parquet` | `288e310b26b164c80518693db70a9f4679178397dbddfc61598c24722384c272` | MATCH |
| sip | `manifest.json` | `bf2d1c184e4aa78b271ae0cbe94df9c6ff3dcdfd3bcae5fb04d628362ecf8c22` | MATCH |
| sip | `quotes/samples.jsonl` | `98e115503342c33cd55003da059d89d26b769c512699c8d6d518cb886e254a43` | MATCH |
| sip | `bars/bars_1min.parquet` | `943c743c20f390047abd37b0d7ea2ba48cfa07e8bd0a58695f6898772b22990e` | MATCH |

⭐ The **2026-08-24 partition will be the first written under `0344337`**. Its manifest is the forward
check on finding 5 and should be read at the 16:45 ET freeze.

---

## What this amendment does NOT do

1. It does **not** re-latch the approved producer identity to `0344337` or to any other commit, and does not reopen the approved producer identity in any other respect.
2. It does **not** approve, authorise, or schedule a redeploy.
3. It does **not** amend, restate, or summarize §7 "Effective state" — see the note in the header table.
4. It does **not** adjust any K-criterion, threshold, tolerance, denominator, or evaluability clause, and does not reopen **K1–K6**.
5. It does **not** reopen **D0**, the **symbol holdout**, the **period holdout**, or any **PX ruling**.
6. It does **not** modify the signed body of v0.2, and does not edit v0.1 or the frozen 2026-08-19 adjudication JSON.
7. It does **not** authorise any exploratory read of the corpus.
