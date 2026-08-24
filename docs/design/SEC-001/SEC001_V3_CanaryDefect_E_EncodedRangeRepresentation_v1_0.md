# SEC-001 V3 — Canary Acquisition Defect E v1.0

## ENCODED RANGE REPRESENTATION PASSED TO FROZEN PARSER

**Status:** Owner-ruled 2026-08-24. Committed **before** the remediation is implemented — that
ordering is the control this document exists to provide.
**Authorized by:** the bounded diagnostic granted under Pre-Crawl Manifest v1.3 (`9256fa34`).
**Governing:** `SEC001_V3_CanaryDefect_AcquisitionRemediation_v1_0.md` (`0eaa064`),
`SEC001_V3_PreCrawl_CoverageFreeze_v1_0.md`.

---

## 1. The defect

The pinned client (`6c1d7006…`) sends `Accept-Encoding: gzip, deflate` on every request. For a
**ranged** request, SEC serves a byte range of the **compressed** representation. The V3
transport's `_decode` then called `gzip.decompress()` on a fragment, which raises, and the
handler swallowed it:

```python
except (OSError, zlib.error, EOFError):
    body = raw   # malformed encoding: record what arrived, let the caller fail
```

Compressed bytes were therefore handed to the frozen parser as if they were document bytes. The
parser searched gzip noise.

**Two independent errors compounded.** Range offsets referred to the *compressed* representation
while the frozen spine assumes *document-byte* semantics; and a decode failure fell back to raw
instead of failing closed. Either alone would have been visible. Together they produced a
plausible, self-consistent, entirely false picture across three canaries.

### Diagnostic evidence

Accession `0000912057-00-024277` (ABT, 10-Q, accepted 2000-05-15), four requests, bytes retained:

```
first 8 bytes: 1f8b080000000000        <- gzip magic
28,350 compressed  ->  106,350 decompressed

<SEC-HEADER>                                                             @   423
STANDARD INDUSTRIAL CLASSIFICATION:  PHARMACEUTICAL PREPARATIONS [2834]  @   748
</SEC-HEADER>                                                            @ 1,169
```

The SIC was always present, inside a properly terminated SEC header, within the first ~1.2 KB.

---

## 2. Two hypotheses, both REFUTED

Recorded explicitly so a later reader who encounters the header-completion machinery does not
infer that the theories which motivated it remained factual.

| Hypothesis | Status |
|---|---|
| **"The SIC lies beyond byte 4095"** (Defect A's premise) | **REFUTED.** The SIC sits at decompressed offset 748 — comfortably inside the *original* 4 KiB window. Had decoding worked, the legacy request would have sufficed. |
| **"The historical full-submission archive lacks a SIC / SEC header"** | **REFUTED.** Both are present and correctly terminated. This was never a source-semantics condition. |

This is **Branch A** of the v1.3 ruling tree: *SIC exists in the complete bytes but the parser
returns None → parser/integration defect. Fix the machinery; do not call it historical
missingness.*

Both refuted theories were mine, and both were reached by reasoning from digests, status codes and
counts. One look at the actual bytes settled the question in a single step. The standing lesson:
**when adjudicating absence, obtain the bytes before forming the theory.**

---

## 3. Ruling

**Do not change the frozen spine or the SIC parser.** The fix is entirely in the V3 transport.

### 3.1 Identity encoding for the legacy ranged fallback

For the exact legacy ranged fallback **only**, V3 overrides `Accept-Encoding: identity`. All other
request semantics are unchanged.

Rationale is structural rather than expedient: `Range` plus `Content-Encoding: gzip` makes range
offsets refer to the compressed representation, while the frozen spine expects document-byte
semantics. Rather than teaching the transport to reconstruct and incrementally decompress
arbitrary encoded byte ranges, make the ranged request obtain the representation the spine already
assumes.

Verified implementable without touching `client.py`: a per-request `Accept-Encoding` header
overrides the pinned client's default.

### 3.2 Fail closed, everywhere

- Ranged request returning an identity / unencoded representation → parse normally.
- Ranged request unexpectedly returning `Content-Encoding: gzip` or any other encoded
  representation → **`ACQUISITION_ENCODING_UNSUPPORTED`**. Never decode-or-raw-fallback.
- Any decompression failure anywhere → fail closed.
- **`except …: body = raw` must disappear from every parser-facing path.**

Resulting invariant:

> The frozen parser only ever receives **decoded document bytes**, never compressed wire bytes.

### 3.3 Encoded-body integrity invariant (frozen)

> If a response declares a non-identity `Content-Encoding`, the parser-facing body must be the
> successfully decoded representation. Therefore the wire and parser-body identities must not
> remain identical. If `content_encoding ∉ {None, "", "identity"}` **and `wire_bytes > 0`** and
> `sha256_body == sha256_wire`, acquisition fails closed and the body must never reach the frozen
> parser.

The zero-length guard is deliberate: an empty body with a declared encoding hashes identically on
both sides and would otherwise fail closed on a spurious condition.

The gzip-magic assertion is retained alongside it. The hash invariant detects the general class;
the magic-byte check detects a concrete escaped encoding. Both were absent, which is why this
survived three canaries — and note the evidence *already contained* the signal: in every failed
run `sha256_body == sha256_wire` while `content_encoding` said `gzip`.

### 3.4 Decision-byte retention — one amendment

Retention stays and is now justified by direct diagnostic value: it is what made this ruling
possible without further SEC traffic.

Each decision artifact must now record **both representations explicitly**: request
`Accept-Encoding`, response `Content-Encoding`, wire SHA-256 and byte count, parser-body SHA-256
and byte count, decoding status, acquisition status, ranges and `Content-Range`, and the canonical
`source_decision_bytes` actually supplied to the frozen parser.

**Amendment (owner-agreed):** the retained artifact is **exactly the bytes supplied to the frozen
parser**, not a prefix trimmed at `</SEC-HEADER>`. Trimming would break the identity
`parser_body_sha256 == source_decision_bytes_sha256`, which is the property that makes the artifact
reproduce the decision. The header span is recorded as **offset metadata**
(`sec_header_open_offset`, `sec_header_close_offset`) instead of by truncation. Still bounded by
the same 1 MiB ceiling.

This closes the exact gap that caused the incident: the evidence could previously prove what bytes
came over the wire, but not that those bytes were meaningful input to the parser.

---

## 4. What the earlier repairs now mean

Not invalidated — narrower.

| Repair | Disposition |
|---|---|
| **Defect D status vocabulary** | **Retained, valid.** The four-way distinction stands on its own merits. |
| **Decision-byte retention** | **Retained**, and vindicated: it produced this ruling. |
| **Header-completion override + 1 MiB / 8-request ceiling** | **Retained**, but **reclassified** — from root-cause remedy to defensive acquisition control. Not removed merely because it was created under a mistaken diagnosis: it is still a sensible fair-access safety bound, and it alters neither filing selection nor SIC interpretation. Under identity encoding it finally does what we believed it was doing. |
| **Defect C timing fix** | **Retained, valid.** |

---

## 5. Scope

Defect E contaminates **only the ranged fallback path**. The `-index-headers.html` observations
received **complete** encoded streams, decoded successfully, and recovered SIC correctly. There is
no basis to invalidate those 53 observations.

---

## 6. Required sequence

Defect-E ruling custody → V3 transport fix → tests → freeze → scoped validation → new tag →
Git-object deployment → full host gate → **Pre-Crawl Manifest v1.4** → remote custody → new
zero-terminal v1.4 epoch → ABT canary from identity #1 → **only on full PASS**, continue to the
remaining 1,166.

### 6.1 Regression requirements

1. legacy ranged fallback sends `Accept-Encoding: identity`;
2. an identity 4 KiB response containing the ABT-style header recovers SIC 2834;
3. range offsets apply to uncompressed document bytes;
4. unexpected gzip on a ranged response fails explicitly — never raw fallback;
5. malformed gzip / non-range decode failure also fails closed;
6. no parser call can receive bytes beginning with gzip magic `1f8b`;
7. the encoded-body hash invariant fails closed, with the zero-length guard;
8. header completion still operates correctly under identity encoding;
9. the 403 single-request latch remains intact;
10. the Defect C retry timing proof remains intact;
11. the decision-byte artifact proves the exact parser input.

### 6.2 ABT canary acceptance — accession `0000912057-00-024277`

```
accession                            == 0000912057-00-024277
index_headers_status                 == 404          (observation of the SOURCE, see note)
fallback_request_1.range             == "bytes=0-4095"
fallback_request_1.accept_encoding   == "identity"
response_content_encoding            ∈ {absent, identity}
parser_body[0:2]                     != 1f8b
parser_body_sha256                   == source_decision_bytes_sha256
sec_header_open_present              == true
sec_header_close_present             == true
sic_field_present_anywhere           == true
sic_field_present_inside_sec_header  == true
frozen_parser_sic                    == 2834
acquisition_status                   == HEADER_TERMINATED
progressive_range_request_count      == 1
ACQUISITION_HEADER_INCOMPLETE        == false
DOCUMENT_EOF_NO_SEC_HEADER_TERMINATOR == false
```

The document is **not** required to begin with `<` — EDGAR archives carry preamble before the
header, and this one has 423 bytes of it. The governing condition is that parser input is valid
decoded document bytes, not an encoded representation.

**Note on `index_headers_status == 404`:** this asserts EDGAR's behaviour, not ours. It is required
because the fallback must actually execute, but it is recorded as an *observation of the source* so
that a future change there is diagnosed correctly rather than read as a regression in our machinery.

### 6.3 Whole-ABT requirements

For every ranged fallback in ABT: identity encoding forced · no encoded representation reaches the
parser · the encoded-body hash invariant passes · actual send intervals ≥ 0.2 s · every decision has
persisted source-decision bytes · every observation has source provenance · zero orphan observations
· no unexpected domains or forms · no coverage fields.

### 6.4 The six former ceiling hits — tested, not assumed

Prediction: they were manifestations of Defect E, since compressed garbage can never contain
`</SEC-HEADER>` regardless of document size.

- If all six now terminate normally under identity encoding, **record that as confirmation**.
- If **even one** still reaches the 1 MiB / 8-request ceiling, **stop after ABT and report**. That
  would be evidence of a separate remaining acquisition condition, and continuing would carry it
  into the full population.

---

## 7. Execution state

Do **not** resume the v1.3 epoch. Preserve: the v1.1 and v1.2 nonconforming canaries, the v1.3
diagnostic epoch and its evidence, and both the compressed diagnostic bytes and the decompressed
inspection result.

Population **1,167** unchanged · no coverage calculation · `5b26ffa2…` **UNSPENT**.
