# MDQ-001 — Approved Collector Code Identity (Phase-A governed capture period)

**Status:** OWNER-APPROVED
**Ruling date:** 2026-08-19
**Record written:** 2026-08-19T14:27:14Z (2026-08-19 10:27:14 EDT)
**Effective:** before the 2026-08-19 16:45 ET freeze, with the candidate partition
still open and **unread** — this is a pre-commitment, not a post-hoc rationalisation.

---

## 1. Why this record exists

Implementation plan §7.1 requires that *"collector code identity is approved for the
period"*. Until this record, no approved version or SHA was frozen in the registration
or in any program-start record. The mechanical admissibility checker
(`app/research/capture/admissibility.py`) therefore returned **NOT_EVALUABLE** for the
`collector_code_identity` condition unless an approved version was supplied explicitly,
and NOT_EVALUABLE makes the whole adjudication **UNDETERMINED**.

That is the checker behaving correctly: it forces the identity to be *governed* rather
than inferring approval from whatever happened to be running. This record supplies the
governed input. It removes an artificial UNDETERMINED; it does not make any verdict
inevitable.

## 2. The approved identity

The governed identity is the **tuple**, not the version string. The bare string
`mdq-collector/0.1.0` is explicitly **NOT** sufficient on its own — it can be reused
accidentally by a later build.

| Field | Value |
|---|---|
| Collector version | `mdq-collector/0.1.0` |
| Approved source commit | `86d8cbd5a6201a8938062c35f915604b08652fbe` |
| Approved file set | exactly the five files below — no more, no fewer |

### 2.1 Approved collector set — five files, full SHA-256

Paths are relative to `apps/backend/`.

| File | SHA-256 (LF-normalised) |
|---|---|
| `app/research/capture/__init__.py` | `f38fbd649430ce17e507920aab0c9ed284207b096688d1eed7b5f4fadf142fba` |
| `app/research/capture/collector.py` | `e5e030a97eed0a64d4abeb621484e8069dd152dde27ccf75f254f9a1286ebd97` |
| `app/research/capture/identity.py` | `588e258f4b6ee6b88f250c6ec77100e7dc2a8690f1502ca1567de11f452b63d8` |
| `app/research/capture/store.py` | `22c3405e5acbba6c7a86ef71468898ec0515126399770b02dfb42373f211e222` |
| `scripts/mdq_collector.py` | `b5feb2a9c84521c1a624d4436577dcc093f2451c13dd17dda8ca1a52261ab7e2` |

### 2.2 The LF-normalisation rule (part of the identity, not a footnote)

**The approved SHA-256 values are over LF-normalised bytes.** This is load-bearing and is
recorded explicitly because the CRLF deployment finding proved that byte-normalisation is
now part of reproducibly mapping the Git identity to the deployed files.

- `.gitattributes` pins `*.sh`/`*.service`/`*.timer` to `eol=lf` but **not `*.py`**.
  `git archive` from the Windows checkout therefore emits **CRLF**, and every deployed
  `.py` file on the box is CRLF on disk.
- A plain `sha256sum` inside the container consequently does **not** match the Git blob.
  That is expected and is not a tamper signal.
- **Canonical form** = the raw Git blob (`git cat-file blob`), verified LF-only on
  2026-08-19: CR **byte** count 0, and stripping CR is a no-op on it (byte length
  unchanged at 1740 for `__init__.py`).
- **Reproduction rule on the box:** strip CR before hashing —
  `docker exec workbench-backend sh -c "tr -d '\015' < /app/<path> | sha256sum"`
- ⚠ Do **not** probe for CR with an ANSI-C quoted pattern: `AWS-RunShellScript` runs
  `/bin/sh` (dash), which has no ANSI-C quoting, so the test silently matches nothing.
  Use `tr` or Python.
- ⚠ A `grep -c` CR probe under Git Bash was observed on 2026-08-19 to report a false
  positive against an LF-only blob. The decisive evidence is hash equality plus the CR
  **byte** count, not a line-oriented grep.

## 3. Runtime binding — independently re-verified 2026-08-19T14:2xZ

| Field | Value |
|---|---|
| Deployment source identity (`.deploy_src_sha`) | `86d8cbd5a6201a8938062c35f915604b08652fbe` |
| Image | `sha256:cb4e42cd1481ee9193f0a87bb6793cab6cb29093b6c58fee19efd58995871594` |
| Image built | 2026-08-18T18:35:36-04:00 |
| Container `workbench-backend` created | 2026-08-18T22:36:26Z (50 s **after** the build) |
| Health | `healthy`, `/healthz` = 200 |
| `COLLECTOR_VERSION` as the container reports it | `mdq-collector/0.1.0` |

**All five LF-normalised in-container hashes reconcile EXACTLY with the raw Git blobs at
`86d8cbd`.** This reconciliation was performed against the **post-#641** file set. It is a
*different* set from the 2026-08-17 pre-#641 reconciliation at `0273012`
(`ddb088e8…`/`22c3405e…`/`9545b231…`/`211b3b18…`), which is superseded for every file
except `store.py`, whose blob is genuinely unchanged across both deployments.

The raw on-disk (CRLF) hashes observed in the container, recorded so that a future
operator who forgets the normalisation rule can still recognise what they are looking at:

| File | Raw on-disk SHA-256 (CRLF — **not** the identity) | CR bytes |
|---|---|---|
| `app/research/capture/__init__.py` | `e0edcc6c96b4dc29bdf2b46a3699267f8a03f11fbaac1159bcb7db01d6c1b116` | 62 |
| `app/research/capture/collector.py` | `c51f9e0dedf8f8b19436d5fffc46be87164f53adcb6b98fd3fd1a530606605b4` | 335 |
| `app/research/capture/identity.py` | `4f009228af7ad9ebde7cd6df0674d7cd164a56e29e61b76cb9259945bf6e620e` | 117 |
| `app/research/capture/store.py` | `f5cacdd5c70b8272ebfcbe62f37cacc1844447e827dcbe33319a98cde8dd43f5` | 185 |
| `scripts/mdq_collector.py` | `8e33072029b7ca10a21671001373a633353907a81da7b9ea86e2f6f5d2cd4623` | 438 |

## 4. What is NOT in the approved set

`app/research/capture/admissibility.py` — the offline adjudicator — is **not** part of the
approved collector five. It does not acquire or write corpus bytes; it reads frozen
partitions read-only and stamps its own identity into its JSON output:

| Field | Value |
|---|---|
| `ADMISSIBILITY_VERSION` | `mdq-admissibility/0.1.0` |
| `ADMISSIBILITY_SCHEMA` | `mdq-admissibility-report/1` |
| LF-normalised SHA-256 @ `86d8cbd` | `5eb3c0b593fed82fe224b74eea59f21332bfca3ba5f6d65a25c6aabebc4338d9` |

Recorded here for traceability only. Approving the adjudicator's identity is a separate
question and is **not** decided by this record.

## 5. Scope of this approval — approved collector ≠ approved data

This approval authorises **only** the identity used to test the §7.1
`collector_code_identity` admissibility condition. Specifically it:

- does **not** pre-approve the 2026-08-19 partition;
- does **not** waive any other admissibility condition;
- does **not** guarantee that 2026-08-19 becomes D0.

Tonight's checker must still independently evaluate integrity, completeness, gaps, feed
conditions, denominator provenance, observed-symbol match, and every other frozen §7.1
requirement. **A failure remains a failure. NOT_EVALUABLE remains UNDETERMINED.** Neither
starts the 60-calendar-day clock; D0 then moves forward to the next partition that
actually passes.

## 6. How to cite it at adjudication

    python scripts/mdq_collector.py \
      --root /app/data/mdq_capture \
      --universe-file /app/data/mdq_config/mdq_phase_a_universe_symbols.json \
      admissibility --date 2026-08-19 --json \
      --denominator sampler_window \
      --denominator-ruling "Owner ruling 2026-08-18, ruling 1; MDQ-001 Registration v1.0 section 8.2 ruling 1; merged in #641 at 86d8cbd5a6201a8938062c35f915604b08652fbe" \
      --approved-collector-version mdq-collector/0.1.0

⚠ `--denominator` and `--denominator-ruling` must **both** be passed. Omitting either
returns NOT_EVALUABLE for `session_scope_match`, `cadence_match`, `completeness_ratio`
and `max_contiguous_gap` — the ruling must be cited, never assumed.

The denominator ruling itself is a **CORRECTION that binds a previously unbound
definition; it changes no threshold.** It fixes `session_scope` inside
`expected_cycles = f(session_scope, cadence, market calendar)` to the sampler window
(09:25 ET inclusive → official NYSE close exclusive, cadence 60 s) — **395** cycles on a
normal close, **215** on a 13:00 early close, **0** on a non-session day. The 04:00–16:00 ET
interval remains the **bar-census** scope and stays the denominator on the bar side only.
The 98% completeness floor and the 10-minute maximum-contiguous-gap rule are unchanged.

## 7. Still unratified (unchanged by this record)

- **`cadence_tolerance_seconds`** — 5.0 s is the tool default and is reported as such. It
  does *not* force NOT_EVALUABLE; `cadence_match` still scores PASS/FAIL against it.
- **`session_close_calendar_artifact`** — which calendar artifact is authoritative, and how
  its version is recorded, is surfaced but not settled. The in-container calendar is
  working: it produced the `09:25:00 ET -> 16:00:00 ET (exclusive), expected_cycles=395`
  grid at sampler start on 2026-08-19.

---

## Appendix A — owner ruling, verbatim (2026-08-19)

> Approve Option 1 now.
>
> This is a clean pre-commitment decision because the capture is still in progress and the partition has not yet been frozen/read for adjudication. The checker is correctly forcing the identity to be governed rather than inferring approval from whatever happened to run.
>
> Owner ruling — 2026-08-19
>
> I approve the following collector identity for the MDQ-001 Phase-A governed capture period beginning with the 2026-08-19 candidate partition:
>
> Collector version: mdq-collector/0.1.0
> Approved source commit: 86d8cbd5a6201a8938062c35f915604b08652fbe
> Approved collector set: exactly these five files:
> app/research/capture/\_\_init\_\_.py
> app/research/capture/collector.py
> app/research/capture/identity.py
> app/research/capture/store.py
> scripts/mdq_collector.py
> Identity: the five LF-normalized Git-blob SHA-256 values already independently reconciled against the deployed image.
> Runtime binding: deployment image cb4e42cd1481 running source from 86d8cbd….
> Scope: this approval authorizes the identity used to test §7.1 collector-version admissibility. It does not pre-approve the 2026-08-19 partition itself and does not waive any other admissibility condition.
>
> The important distinction is:
>
> Approved collector ≠ approved data.
>
> Tonight's checker must still independently evaluate integrity, completeness, gaps, feed conditions, denominator provenance, and every other frozen §7.1 requirement. A failure remains a failure; NOT_EVALUABLE remains UNDETERMINED.
>
> I would have the record include the full 64-character SHA-256 values, not the abbreviated values shown in the status table. Also preserve the LF-normalization rule explicitly because the CRLF deployment finding proved that byte-normalization is now part of reproducibly mapping the Git identity to the deployed files.
>
> One thing I would not do is approve simply:
>
> mdq-collector/0.1.0
>
> by itself. That string can be reused accidentally in a later build. The governed identity should be the tuple:
>
> version + merged commit + exact five blob hashes
>
> with the deployed image/container evidence as runtime corroboration.
>
> Therefore tonight you can pass:
>
> --approved-collector-version mdq-collector/0.1.0
>
> provided the Program Start/approval record simultaneously freezes the exact commit and five hashes above.
>
> If the 2026-08-19 partition later passes adjudication, it may become D0. This ruling removes the artificial NOT_EVALUABLE blocker; it does not make D0 inevitable.
>
> Decision: Option 1 APPROVED, effective before the 2026-08-19 freeze.
