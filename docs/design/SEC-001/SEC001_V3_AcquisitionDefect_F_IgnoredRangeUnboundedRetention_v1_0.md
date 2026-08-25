# SEC-001 V3 — Acquisition Defect F v1.0

## IGNORED `Range` DEFEATED THE FROZEN ACQUISITION BOUND; EPOCH v1.4 HALTED ON ENOSPC

**Status:** Owner-ruled 2026-08-25. Committed **before** the remediation is implemented — the same
ordering control used for Defect E.
**Governing:** `SEC001_V3_CanaryDefect_E_EncodedRangeRepresentation_v1_0.md`,
`SEC001_V3_PreCrawl_Manifest_v1_4.json` (`126640240b94`),
`SEC001_V3_ExecutionControl_Addendum_v1_4_2.md` (`d3912c7a`).
**Supersedes:** nothing. Epoch v1.4 is halted, not amended.

---

## 1. The defect

The Defect-E remediation added `Accept-Encoding: identity` to every ranged request so that range
offsets would refer to **document** bytes rather than to the compressed representation. It did.

It also caused SEC to stop honouring `Range` altogether.

```
ranged requests answered 206 :      0
ranged requests answered 200 : 19,616      <- full document returned, every time
no-Range (index-headers, gzip): 12,030
attempts per manifest record  : 1 for all 31,646
```

`fetch.py::_complete_sec_header` performs no status check and imposes no read bound. It appends
whatever arrived:

```python
cap = self._recorder.last
served = len(cap.body) if cap else 0
if cap is not None:
    chunks.append(cap.body)          # <- the entire 200 response
if SEC_HEADER_CLOSE in b"".join(chunks):
    return finish(policy.ACQ_HEADER_TERMINATED)
consumed += served                   # <- steps past every remaining window at once
```

The loop therefore terminates on its **first** request with `HEADER_TERMINATED` — a correct SIC
decision wrapped around an entire filing — and persists that filing as the "decision bytes".

**The frozen ceiling was never a ceiling.** `HEADER_COMPLETION_CAP_BYTES = 1 MiB` and
`HEADER_COMPLETION_MAX_REQUESTS = 8` bound only the values the client places in the `Range` header
and the number of times it asks. Neither bounds what a single response may deliver, nor what is
retained. A 422 MB document retained to answer a decision whose header closed at byte 6,195 is
sufficient by itself to prove the bound was not a bound.

### Measured amplification

```
bytes required to reach the decision (sum sec_header_close_offset) :        39,542,324   (~39.5 MB)
bytes retained as source_decision_bytes                            :    94,675,961,427   (~94.7 GB)
                                                                      => ~2,400x amplification

artifacts > 1 MiB : 9,777 files (9,941 manifest records, = 91,733,104,231 B)
artifacts > 10 MiB: 2,608        artifacts > 100 MiB: 26
largest artifact  : 422,424,674 B  accession 0000065984-14-000065 (Entergy 10-K)
                    -> sec_header_close_offset 6,195 ; parser_result SIC ; 1 attempt ; http 200
```

Projection: 374 units consumed 94.7 GB, so 1,167 units require **~295 GB**. The 100 GiB root
volume could never have completed this crawl. The halt was arithmetically inevitable from the
first ranged request of the epoch.

---

## 2. Why every prior gate passed

The ABT canary passed **37/37 under manifest v1.4 with Defect F already fully present.** Its
ranged filings were answered 200 as well; they were merely small. Nine hard runtime assertions
were live, four of them structural. **None asserted a 206, a per-response byte ceiling, or a
retention ceiling.** Every assertion tested whether the *decision* was correct — SIC located
inside a terminated SEC header, `parser_body_sha256 == source_decision_bytes_sha256`, no encoded
representation reaching the parser undecoded. All of those remained true. The host gate's 82/82
PASS sized free space from that same canary.

This is the recurring failure mode, now for the third time in this program: **a remediation scoped
to the last observed loss, validated by assertions scoped to the same loss.** Defect E was cured by
removing compression, and the cure silently purchased unbounded acquisition. The controls could not
see it because nothing in the control set measured volume.

---

## 3. What survived, and what did not

**Classification correctness is not impeached by any evidence now in hand.** SIC values sit inside
properly terminated SEC headers; `parser_body_sha256 == wire_sha256` throughout; fair-access rate
stayed compliant (<= 2.15 req/s, zero 403, zero 429).

**Bounded acquisition and bounded retention did not survive.** `parser_body` is, for 9,941 records,
the complete filing. The bounded-decision-byte-retention invariant introduced by the C+D repair is
violated in substance while being satisfied in form.

The entire v1.4 bulk epoch is therefore **acquisition-nonconforming**.

---

## 4. Owner rulings (2026-08-25)

### 4.1 Disk custody — preserve first, do not reclaim

No in-place cleanup on the 100%-full root. Park the host, snapshot the volume, verify custody, and
only then provision **fresh execution storage** for the repaired epoch. The 94.7 GB
oversized-retention corpus is the direct physical evidence of Defect F and must remain recoverable.

Explicitly preserved **as evidence, not repaired**:

- the **zero-byte** `RUNNER_STOPPED.json` — the stop-record write itself hit ENOSPC;
- the **torn final line** of `source_decision_bytes.jsonl`;
- `runner.log`, which is consequently the **authoritative contemporaneous statement of cause**.

### 4.2 Acquisition-bound repair — bounded client-side handling of an ignored `Range`

A 200 answer to a ranged request is **not** an acquisition failure. SEC answers these
identity-encoded requests with 200 systematically; a "200 => fail" rule would confuse server range
behaviour with document unavailability and render the historical source unusable.

Nor may the current behaviour stand. For `Range: bytes=A-B`, two server behaviours are conforming:

| response | required client behaviour |
|---|---|
| **206** | `Content-Range` must be present and consistent with the requested interval. Consume no more than the ranged representation. Mismatch or absence **fails closed**. |
| **200** | Classify explicitly as `RANGE_IGNORED_200_BOUNDED`. **Stream** the response; consume only enough of the full representation to reconstruct `[A, B]`; discard `[0, A-1]`; supply only `[A, B]` to the accumulator; **close the response**. |

The advertised `Content-Length` is metadata, not permission to consume it.

#### 4.2.1 Streaming capability is a PREREQUISITE to implementation authority (owner, 2026-08-25)

The repair direction is approved; **implementation authority is not yet granted.** It depends on a
fact not yet established:

```
Does the pinned client expose a genuine streaming / raw-response interface?
  YES -> the repair stays V3-local. Do NOT modify the frozen client.
  NO  -> STOP. This becomes a frozen-client change requiring its own narrow adjudication,
         implementation identity, regression proof, and re-freeze BEFORE the successor crawl.
```

⛔ **Emulated streaming is prohibited.** Materializing the full response and slicing it afterward
preserves the exact Defect-F resource failure — the 422 MB still crosses the wire and still lands in
memory — while changing only what is retained. That is not the repair; it is the defect with better
housekeeping.

#### 4.2.2 The 206 / ignored-200 split

Progressive 4 KiB → 16 KiB → 64 KiB … re-requests against a server that ignores `Range` cause the
full document to be retransmitted from byte zero on every window. Preferred implementation:

| case | acquisition shape |
|---|---|
| **206** | normal progressive interval acquisition — existing semantics retained |
| **ignored-range 200** | **one bounded stream from byte zero**, progressively extending the locally retained prefix until `</SEC-HEADER>` is observed or the 1 MiB consumption ceiling is reached |

This is **fair-access and resource discipline, not a redesign of the frozen header-completion
algorithm.** The 1 MiB / 8-request control remains an **outer ceiling**; the optimized 200 path
should normally consume **one** request and must never reinterpret the ceiling upward.

**Three bounds, mechanically enforced before any further live crawl:**

1. **Per-request consumption** — for an ignored-Range 200:
   `wire_bytes_consumed <= requested_end + 1`.
2. **Per-record parser/retention** — `len(parser_facing_bytes) <= HEADER_COMPLETION_CAP_BYTES`
   and `len(source_decision_bytes) <= HEADER_COMPLETION_CAP_BYTES`.
3. **Whole-unit retained evidence** — no decision artifact may contain a complete filing merely
   because the server ignored `Range`.

The existing 1 MiB / 8-request ceiling now governs **bytes actually consumed and retained**, not
merely the values written into the `Range` header.

**Evidence semantics must not pretend the server returned 206.** The record must read plainly:
*server ignored Range; client enforced the frozen byte bound locally.*

#### 4.2.3 Digest semantics are VERSIONED, never redefined in place (owner, 2026-08-25)

`wire_sha256` cannot quietly change meaning between epochs. For an ignored-Range 200 there **is no
full-wire digest**, because the full representation must not be consumed — so the v1.4 field cannot
be carried forward with an altered definition.

> **The v1.4 `wire_sha256` remains historical, with its original meaning: a digest over the entire
> response body. The successor schema does not redefine it — it introduces
> `wire_consumed_sha256` instead.**

Successor per-attempt evidence fields:

| field | meaning |
|---|---|
| `response_content_length` | advertised full-representation size, if present |
| `wire_bytes_consumed` | bytes actually read from the socket / stream |
| `wire_consumed_sha256` | digest over **exactly** the bytes actually consumed |
| `selected_interval_start` / `_end` | the interval supplied to the accumulator |
| `selected_interval_sha256` | digest over the selected interval |
| `parser_body_sha256` | digest over parser-facing bytes |
| `source_decision_bytes_sha256` | digest over the retained decision artifact |
| `range_honored` | boolean — never inferred, always recorded |
| HTTP status | as returned |

This keeps cross-epoch evidence from *looking* semantically comparable when it is not.

### 4.3 Epoch policy — new epoch, zero terminals

The repaired acquisition requires a **new epoch beginning at 0/1,167.** The 374 terminals are not
carried forward.

The 374 classifications may well be correct, but they were produced under an implementation that
violated a load-bearing frozen control. Carrying them forward would yield a final population with
two materially different acquisition semantics — identities #1-#374 under whole-document
retention, the remainder under bounded streamed acquisition — and would make the final integrity
statement permanently conditional. This is consistent with the v1.2 precedent: **acquisition-bound
changes take effect prospectively.**

Nothing is deleted and nothing is rewritten. The 374 simply do not count toward completion of the
successor epoch.

---

## 5. Custody record — failed epoch v1.4

| item | value |
|---|---|
| instance | `i-00e6b78fcabd32413` (`sec001-v3-research-build`, m7g.xlarge, us-east-1c) |
| plane | `research-no-broker-capability` — no order-path or broker capability at any time |
| root volume | `vol-0cf17223018c3a1c6` — 100 GiB gp3, encrypted |
| `DeleteOnTermination` | **cleared to `false` 2026-08-25T13:24Z** (was `true`) — the evidence volume must not be destroyed by a future terminate |
| instance state | **stopped** 2026-08-25T13:24:38Z, user-initiated. NOT terminated. |
| custody snapshot | `snap-01a33687b1588626b`, started 2026-08-25T13:25:31Z |
| filesystem at halt | `/dev/nvme0n1p1` -> `/`; 102,888,095,744 B total; 102,870,425,600 B used; **892,928 B free; 100%** |
| halt timestamp | last progress record `2026-08-25T04:15:31.642587Z`; `runner.log` mtime `2026-08-25T04:17:30.622147Z` |

### Sealed facts

```
terminal prefix              374 / 1,167      374 unique, no duplicates
frozen-order prefix          continuous; first = 0000001800:ABT (frozen first identity)
final terminal               0000833320:BR1
requests issued              51,336           retries 264
http status                  200 x 31,646     403: 0      429: 0
ranged answered 206          0
ranged answered 200          19,616
manifest records             31,647 lines, 1 unparseable (final line torn by ENOSPC)
distinct .bin artifacts      31,089           <- delta 558 vs lines / 557 vs parseable; see 7.1
retained bytes               94,675,961,427
decision-needed bytes        ~39,542,324
artifacts > 1 MiB            9,777 files / 9,941 records
maximum artifact             422,424,674 B
classification decisions     not shown incorrect by any evidence in hand
fair-access rate             compliant throughout
acquisition / retention      CONTRACT VIOLATED
```

### Digests (captured on the live filesystem before the host was stopped)

```
f4aa5791ca21808e4881af7967df572ff9a7a4a84752a1347d37647f7749b902  crawl-v1.4/runner.log (2,373 B)
a66261df0899291759a0c61f7d879f0129cc8f54b86df5b56099ed298ad286c0  crawl-v1.4/state/crawl_progress.jsonl
3d7ca5fe32973e772f5d8dad1ac8adce19cbb8761526ec6b05235a502dd9c62b  .../source_decision_bytes.jsonl
affd0552a33f324210be9ea090a8ef1f3e1f92b996ab6273a7f84d96fa17d082  epochs/EXECUTION_SEGMENTS.json
```

`EXECUTION_SEGMENTS.json` is unchanged from its capture-time digest and remains the contemporaneous
four-segment provenance record. It was captured at 33 terminal identities, so `terminal_at_capture`
and segment 3's `last: "in progress"` are snapshot values; **segment 3 in fact closed at 374**
(`0000833320:BR1`). Bind it for boundaries and authorities only.

| seg | identities | runner | authority |
|---|---|---|---|
| 0 | #1 ABT | `canary_run_v3.py` (`50541e29`) | Manifest v1.4 |
| 1 | #2-#5 | `crawl_full.py` (`9571c9eb`) | **none — unbound nonconformance**, 21:22:36Z |
| 2 | #6-#8 | `crawl_full.py` (`9571c9eb`) | Addendum v1.4.1 (`59f6044f`), 21:30:48Z |
| 3 | #9-#374 | `crawl_full.py` (`894e4744`) | Addendum v1.4.2 (`d3912c7a`), 21:37:57Z |

Boundaries: `#1->#2 ABT->ACS` · `#5->#6 APD->ABS` · `#8->#9 SWKS->HWM`.

### Characterization

> **V1.4 BULK CRAWL — HALTED / NONCONFORMING ACQUISITION BOUND**
>
> The 374-unit prefix is preserved, and is admissible as corroborating classification evidence and
> as the physical evidence of Defect F. **It is not admissible as conforming terminal progress for
> the successor epoch.**

---

## 6. Required sequence before another full crawl

Patch-and-resume is prohibited.

```
Defect-F adjudication record (this document)
  -> implementation
  -> regression suite
  -> new validation / freeze
  -> new manifest version
  -> remote custody
  -> fresh zero-terminal epoch on clean execution storage
  -> Defect-F canary
  -> only then the full 1,167
```

### The successor canary

The old 37 checks are known-insufficient — ABT passed them with the defect present. The canary must
prove the defect that escaped them. Minimum population:

1. the original ABT diagnostic;
2. a filing for which SEC answers the ranged request with 200;
3. **accession `0000065984-14-000065`** (422,424,674 B; header closed at 6,195) — the strongest
   available regression: server offers the whole filing, client consumes only bounded header bytes,
   retained artifact remains small and bounded, **SIC result unchanged**;
4. at least one filing requiring progression beyond the first 4 KiB.

Two aggregate assertions, either of which would have caught Defect F on its first request:

```
max_retained_decision_bytes <= HEADER_COMPLETION_CAP_BYTES
range_request_count > 0  =>  every response is a valid 206 OR an explicit RANGE_IGNORED_200_BOUNDED
```

No silent third state. The canary **fails** if any single decision artifact exceeds the authorized
retained-byte ceiling.

---

## 7. Open items carried into the repair

**7.1 — CANDIDATE DEFECT G: decision-artifact path collision / overwrite. REQUIRED
pre-implementation evidence check (owner, 2026-08-25).**

The manifest and the artifact store disagree on cardinality:

```
manifest lines             31,647        -> delta 558
manifest parseable records 31,646        -> delta 557
distinct .bin artifacts    31,089
```

**Both deltas are arithmetically correct against different denominators; the one-record difference
is exactly the torn final line, whose artifact may or may not have been written before ENOSPC.**
Which denominator applies is a question for the preserved snapshot — **do not assume either number.**

Hypothesis: if `artifact_path` is keyed on accession alone, an accession acquired by *both* the
index-headers path and the ranged path writes the same filename twice, and the surviving artifact
does not correspond to the digest recorded against the earlier record.

The test is read-only and straightforward:

> For every manifest record referencing a retained artifact, do the retained bytes at that artifact
> path hash to the digest recorded **for that specific record**?

If not, this is **Defect G — decision-artifact path collision/overwrite**, independent of Defect F.
The affected v1.4 records would then have **non-reconstructable retained decision evidence**, even
where the classification output itself remains plausible.

⛔ Run this against the preserved snapshot/clone, never the 100%-full source volume, and never by
restarting the failed host. **Not verified** — the host was stopped before it could be, deliberately.

⭐ A Defect-G finding **strengthens** ruling 4.3 rather than changing it: the successor epoch starts
at 0/1,167 regardless of the artifact-collision outcome.

#### 7.1.a — RESOLVED. Lineage preserved as a sequence (2026-08-25)

The hypothesis above is **refuted**. It is retained verbatim, not deleted, so that the sequence of
reasoning remains legible:

| stage | outcome |
|---|---|
| **1. Initial hypothesis** (this §7.1) | an accession acquired by *both* the index-headers and the ranged path overwrites its own artifact ⇒ the survivor cannot match the earlier record's digest |
| **2. Pass-1 refutation of the mechanism** | 616 duplicated accessions exist, but the pairs are `(TERMINATED,TERMINATED)` ×361 and `(INDEX,INDEX)` ×255 — **zero mixed pairs**. The hypothesised mechanism does not occur. All 616 pairs record the *same* digest. Manifest-internal only; the on-disk bytes were still unverified |
| **3. Pass-2 byte-level closure** | 31,646/31,646 records and 31,030/31,030 artifacts hashed: 0 mismatched, 0 missing, 0 length mismatches. **616/616 collisions verified against the shared digest, 0 failed.** Arithmetic: 31,646 records = 31,030 physical artifacts + 616 shared-path collisions |
| **4. Disposition** | **CLOSED / REFUTED.** The collision is real and destroyed **no** evidence |

⚠ **"Defect G" is not a seventh acquisition defect.** A–F were defects discovered *during the
attempted crawl*; G was a **forensic concern raised afterwards, during Pass-1 analysis**. The crawl
defect count remains **six (A–F)**.

⛔ Byte integrity is **not** evidentiary sufficiency: Pass 2 says nothing about whether the SIC
classifications are correct, and does **not** rehabilitate the 374 units.

**7.2 — Digest semantics.** RULED — see §4.2.3. `wire_sha256` keeps its v1.4 meaning permanently;
the successor introduces `wire_consumed_sha256` rather than redefining the field in place.

**7.3 — Progressive re-download.** RULED — see §4.2.2. Classified as fair-access/resource
discipline, not a redesign of the frozen header-completion algorithm.

**7.4 — Pinned-client streaming capability.** ELEVATED to a prerequisite — see §4.2.1. This is the
**first** technical question to resolve after custody is verified, because it decides whether the
repair is V3-local or reaches a frozen artifact.

**7.5 — Second frozen-src tree.** The rejected CRLF archive is resident on the failed host. Fresh
execution storage must not inherit it.

---

## 7A. Exact sequence from here (owner, 2026-08-25)

**Now — and nothing beyond it:**

```
snapshot reaches `completed`  ->  verify snapshot custody  ->  STOP
no source-volume mutation · no reclaim · no fresh storage · no implementation
```

**Then, read-only against the snapshot/clone:**

1. establish whether the pinned client supports **genuine** bounded streaming (§4.2.1);
2. resolve the manifest/artifact count discrepancy — 557 or 558 (§7.1);
3. prove or refute artifact overwrites (candidate **Defect G**);
4. amend and finalize this ruling with those facts;
5. commit **and remote-custody** the ruling;
6. **only then** authorize implementation.

⛔ This document is **not yet committed**. Commit is authorized once the snapshot reaches
`completed` and custody is verified — before any repair code, consistent with the Defect-E
ordering control — and only after the clarifications above are incorporated and the read-only
findings are folded in.

---

## 7B. §4.2.1 bounded-streaming prerequisite — DETERMINED **NOT SATISFIED** (2026-08-25)

The prerequisite established at §4.2.1 has been evaluated read-only against the deployed artifacts.
Record: `SEC001_V3_DefectF_StreamingPrerequisite_Determination_v1_0.md` (custodied, commit
`725e737`).

**Verdict: NOT SATISFIED — branch 3.** The pinned path offers no enforceable body-consumption
ceiling. `RecordingTransport.handle_request` (`fetch.py:163`) executes
`raw = b"".join(response.stream)`, fully materialising the entity before any downstream consumer
sees a byte; `response.close()` follows only afterwards. Tests 2, 3 and 4 all fail. The pinned
`EdgarClient` (`client.py`, sha256 `7d74eda4…`, 92 lines) exposes **no** streaming or bounded-read
interface — `get_json → r.json()`, `get_text → r.text`.

⭐ Material nuance, recorded as inference and **not** as a finding: the materialising line lives in
**V3-owned** `fetch.py`, which composes only with the client's documented `transport=` and
`headers=` seams. A bounded repair inside `RecordingTransport` therefore appears possible without
touching the pinned client. Not demonstrated against a real ignored-`Range` 200 ⇒ fail-closed.

---

## 7C. RULING — `V3_LOCAL_BOUNDED_RECORDING_TRANSPORT_REPAIR`

> **AUTHORIZED FOR IMPLEMENTATION AND CANARY ONLY.**
>
> ⛔ **This ruling does NOT close Defect F, and does NOT authorize the successor crawl.**

⚠ **This is not a reversal of the §4.2.1 verdict.** The determination says *the current pinned path
fails*. This ruling says *a specific V3-local remediation may now be attempted*. Both statements are
true simultaneously and must remain visibly separate. A later reader must not read the sanctioned
repair back into §7B as though the path had been fixable all along.

### Normative requirements (binding, not commentary)

1. **The pinned `EdgarClient` remains byte-identical.** No frozen-client change is authorized.
2. **Only the V3-owned recording/acquisition path may change** — `RecordingTransport` and the
   surrounding `fetch.py` acquisition logic.
3. **Actual socket/body consumption must be bounded — not merely artifact retention.** Consuming a
   full 422 MB entity and then writing a small artifact **fails**. `wire_bytes_consumed <=
   requested_end + 1` for an ignored-Range 200; the stream must be stopped and closed early and the
   remainder never read, not even for recording or hashing.
4. **Explicit ranged-response classification and incremental hashing.** Validated `206` with
   `Content-Range` checked against the requested interval, or `200_FULL_RANGE_IGNORED` — **no silent
   third state**. Digests must be computed with a rolling hash over exactly the retained bytes,
   producing the §4.2.3 `wire_consumed_sha256` rather than redefining `wire_sha256`.
5. **Stop-work condition.** If satisfying any requirement above requires modifying `EdgarClient`, a
   shared or frozen client layer, or any other governed shared component, **stop**. That exceeds
   this adjudication and requires separate authority.

### Transition condition (mechanical)

> **Defect F closes if and only if the governed canary demonstrates the bound on the real
> ignored-`Range` 200 case** — accession `0000065984-14-000065` (422,424,674 B; SEC header closes at
> byte 6,195). The proof must show **bounded transport consumption**, not a bounded artifact written
> after a full network read.

Until that canary passes:

```
Defect F        OPEN
successor epoch BLOCKED at 0/1,167
5b26ffa2...     UNSPENT
```

A canary PASS closes the *implementation* question for F. Only then may a clean successor epoch
begin at 0/1,167.

---

## 8. Program state

```
v1.4 crawl          HALTED at 374/1,167          successor credit   0
Defect F            OPEN - repair AUTHORIZED for implementation + canary only (7C)
Defect G            CLOSED / REFUTED (Pass-2 forensic hypothesis, NOT a 7th crawl defect)
S4.2.1 prerequisite NOT SATISFIED - branch 3 (7B)
failed epoch        PRESERVED - vol-0cf17223018c3a1c6 (stopped host, DeleteOnTermination=false)
                              + snap-01a33687b1588626b (completed, encrypted, standard tier)
evidence custody    branch evidence/sec001-v3-defectF-custody
                      4394eef  Pass-2 byte verification record
                      725e737  S4.2.1 determination
                      c95bcbe  Pass-2 reproducibility artifacts (4 files + manifest)
temporary infra     TORN DOWN - i-034baf111469c310c terminated,
                      vol-0e526053c6bef5887 deleted, after a clean uniqueness check
coverage            NOT COMPUTED
economic result     NONE OBSERVED
5b26ffa2...         UNSPENT
```

`5b26ffa2...` must **not** be spent against these 374 classifications. The next authorized act is
**implementation of the §7C repair and its canary** — nothing downstream of that gate.

### Evidentiary chain (complete; no dangling infrastructure dependency)

| element | state |
|---|---|
| Pass-1 storage forensics | sealed **INTERIM**, never rewritten |
| Pass-2 byte verification | sealed; 100% manifest-to-disk agreement |
| `pass2_report.json` | custodied — the only per-artifact attestation of the 108 residue objects |
| `mismatches.jsonl` | custodied at 0 bytes; `e3b0c442…` affirmatively attests zero mismatches |
| §4.2.1 determination | completed, NOT SATISFIED, custodied |
| temporary host + copy | proved non-unique, then destroyed |
| original volume + snapshot | intact and untouched throughout |
