# SEC-001 V3 — Canary Defect / Acquisition Remediation Ruling v1.0

**Status:** Owner-ruled 2026-08-24. Committed **before** the remediation is implemented — that
ordering is the control this document exists to provide.
**Supersedes for execution:** Pre-Crawl Manifest v1.1 (`77f1169`) — v1.1 authorized the canary; the
canary found the machinery nonconforming.
**Governing:** `SEC001_V3_PreCrawl_CoverageFreeze_v1_0.md` (θ values, anti-peek), Pre-Crawl
Manifest v1.0 (`c581253`) and v1.1 (`77f1169`).

---

## 0. What happened

The one-identity canary authorized by Manifest v1.1 ran against live EDGAR on 2026-08-24 for the
deterministically-first identity `cik=1800 / ABT / permaticker 199997`. It issued 171 requests,
took zero 403s and zero 429s, recovered five 503s through the frozen retry policy, and halted
nothing. Inspection scored 22 of 23 declared checks.

It also found two defects in acquisition machinery. Both must be repaired before the remaining
1,166 identities are crawled.

---

## 1. Defect A — the legacy ranged fallback recovers no SIC

Pre-~2014 accessions have no `…-index-headers.html`; the frozen spine's `fetch_header_text`
therefore falls back to the full-submission `.txt` with `Range: bytes=0-4095`. Measured outcome
for ABT, a perfect split:

| final fetch path | SIC recovered |
|---|---|
| `index_headers` HTTP 200 | **53** |
| ranged fallback HTTP 206 (every body exactly 4,096 bytes) | **0** — 53 × NO_SIC |

The `STANDARD INDUSTRIAL CLASSIFICATION: … [code]` line does not lie within the first 4 KiB of
those archives. The fetches *succeed*; they simply return too little of the file.

**Why this is not acceptable as a limitation.** The affected filings are the oldest ones. Left in
place, an extraction defect would present as historical *missingness*, and that missingness feeds
directly into the ≥20-year span provision of the coverage gate. It would have produced a
convincing but entirely artificial "classification history begins around 2014" result and
contaminated the later `5b26ffa2…` adjudication. This is emphatically **not** the sanctioned
"the first issuer legitimately has no history" case — Abbott has ample history.

### Ruling A

Do **not** modify the frozen `sic_history.py` blob (`48779ada…`), and do **not** accept
"no pre-2014 SIC" as a limitation. Implement a **V3-owned acquisition override**.

The frozen spine remains authoritative for: filing/form selection, form precedence, effective-date
semantics, SIC parsing, and conflict behaviour. Only the **transport behaviour of its
full-submission fallback** is augmented.

**Contract.** When the frozen spine requests a full-submission `.txt` using its legacy
`Range: bytes=0-4095`, SEC-001 V3 transparently retrieves enough of *the same filing* to complete
the SEC header. It does not select a different filing, use a different source, or alter SIC
parsing.

- Bounded **progressive** ranges, never whole-file fetches.
- Stop when the SIC-bearing header is complete, **or** `</SEC-HEADER>` is observed without a SIC,
  **or** the frozen absolute cap is reached.
- **Cap frozen at 1 MiB.**
- Every individual range request is separately recorded with URI, Range header, status,
  `Content-Range` where present, timestamp and body SHA-256.

**Invariant.** The override may change *how many bytes are obtained from the same frozen filing*.
It may not change *which filing is authoritative* or *how SIC is interpreted*. MR-002 is untouched.

### The distinction that must never blur

| status | meaning |
|---|---|
| `no_pit_sic` | a fact about available historical evidence — the header was read completely and carries no SIC |
| `ACQUISITION_HEADER_INCOMPLETE` | a failure of acquisition machinery — the cap was reached before the header could be completed |

`ACQUISITION_HEADER_INCOMPLETE` must **never** quietly count against classification coverage.

---

## 2. Defect B — the evidence clock cannot substantiate rate compliance

`requested_utc` is stamped at attempt start, **before** the throttle sleeps. Measured: 83 of 170
gaps between consecutive `requested_utc` values fall below 0.2 s (minimum 0.0103 s), while median
`elapsed_ms` is 201 ms — the 0.2 s sleep sits inside the measured window.

Actual compliance is strongly indicated (average 1.243 rps over 136.8 s; the host gate verified
`_min_interval == 0.2`), but the evidence artifact cannot *demonstrate* it. For a fair-access
record that is the wrong artifact: it asks the reader to trust the code rather than the evidence.

### Ruling B

Keep `requested_utc`, redefined and documented as **attempt-start / scheduling time**. Add actual
transmission evidence inside `RecordingTransport.handle_request`, immediately before the
underlying transport sends:

- `sent_utc` — wall clock, forensic evidence
- `sent_monotonic_ns` — **the arithmetic clock for rate proof**

Wall time may jump; monotonic time may not. Rate compliance is proved from
`sent_monotonic_ns` only.

The canary report must demonstrate, across **every actual outbound attempt including retries**,
that `send_delta_monotonic >= 0.2 s`, subject only to an explicitly frozen clock-resolution
tolerance if one is genuinely required. The five recovered 503s appear as five additional real
send attempts and participate in the same calculation.

---

## 3. The first canary state cannot be resumed

The population and ordering do **not** need re-freezing. But identity #1 was processed under
machinery now known to be nonconforming, so its terminal status cannot remain authoritative while
identities 2–1,167 use corrected machinery.

- Preserve the existing state immutably as **`CANARY_V1_1_FAILED_ACQUISITION`**.
- Create a **new execution epoch** for Manifest v1.2 with the same 1,167 identities, the same
  deterministic ordering, the same first identity (ABT / 199997), and **zero prior terminal
  identities**.
- Rerun ABT from the beginning under v1.2. If it passes, continue that same v1.2 state through
  identities 2–1,167.

This is **not** a new research trial and **not** a new population. It is a superseding acquisition
execution following a pre-coverage machinery defect.

---

## 4. Required remediation sequence

1. This ruling, committed and pushed **first**.
2. V3-owned header-completion override (§1).
3. `sent_utc` + `sent_monotonic_ns` transport-send evidence (§2).
4. Regression fixtures:
   - old filing whose SIC lies beyond byte 4095;
   - complete header with SIC;
   - complete header legitimately lacking SIC;
   - cap exceeded → acquisition failure, **never** `no_pit_sic`;
   - 403 still emits exactly one request;
   - 429/503 retries remain rate-throttled;
   - actual-send intervals prove ≥ 0.2 s.
5. Freeze / commit / push the new driver blobs.
6. **Do not reuse the `0e9e14e` archival tag** as validation for the changed driver. The new driver
   gets its own scoped validation evidence and its own tag. PR #674 remains intact as evidence for
   the prior version.
7. Deploy from Git objects.
8. Rerun the **entire** host gate from zero.
9. Pre-Crawl Manifest **v1.2**, explicitly superseding v1.1 because the canary exposed acquisition
   defects, requiring: prior canary requests/evidence preserved · v1.2 crawl-state terminal count
   = 0 before rerun · population unchanged = 1,167 · `5b26ffa2…` UNSPENT · no coverage calculation
   has occurred.
10. Remote-custody and fresh-verify v1.2.
11. Rerun ABT as the same deterministic canary.
12. Only if it passes, continue through the remaining 1,166.

---

## 5. What makes the repaired canary pass

- historical pre-2014 SIC observations actually recovered;
- no systematic 4,096-byte → NO_SIC pattern;
- every legitimate `no_pit_sic` distinguishable from acquisition failure;
- zero orphan evidence;
- only authorized forms and domains;
- 403 latch still correct;
- 429/5xx retry behaviour correct;
- actual-send monotonic gaps substantiate the 5 rps policy;
- one terminal identity, 1,166 untouched;
- no coverage fields anywhere;
- `5b26ffa2…` still UNSPENT.

---

*The canary has already paid for itself: it prevented what could have become a very convincing but
completely artificial "classification history begins around 2014" result.*
