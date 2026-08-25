# SEC-001 V3 — Defect-F Governed Canary Result v1.0

## VERDICT: **PASS** — the real ignored-`Range` 200 was reproduced and bounded

**Authority:** ruling `SEC001_V3_AcquisitionDefect_F_IgnoredRangeUnboundedRetention_v1_0.md` §7C
(sealed `89b7399`) · pre-change baseline (`5db2d3e`) · implementation evidence (`517cab0`).

⛔ **This record states a canary result. It does not itself close Defect F, spend `5b26ffa2…`, or
start the successor epoch.** Those require adjudication of this result.

Executed 2026-08-25. Times US Central (CDT, UTC−5); sealed Z values retained.

---

## 1. Headline

```
accession                  0000065984-14-000065   (Entergy 10-K)
known entity               422,424,674 bytes
SEC header closes at       byte 6,195
governed hard ceiling      1,048,576 bytes

http_status                200
range_class                200_FULL_RANGE_IGNORED     <- the real Defect-F condition
range_honored              false
wire_bytes_consumed        15,707                     <- 0.0037% of the entity
elapsed                    0.121 s
```

> Under the pre-repair implementation this exact request consumed the entire **422,424,674 bytes**.
> It now stops at **15,707**. The decision remains reachable inside what was consumed.

---

## 2. Governed assertions — all PASS

| id | assertion | result |
|---|---|---|
| A | `wire_bytes_consumed <= RESPONSE_CONSUMPTION_CEILING_BYTES` | **PASS** (15,707 ≤ 1,048,576) |
| B | consumption far below the entity | **PASS** |
| C | remainder (~421.9 MB) not drained | **PASS** |
| D | incremental digest binds exactly the consumed bytes | **PASS** |
| E | response classified explicitly, no silent third state | **PASS** |
| F | decode succeeded | **PASS** |
| G | **the real ignored-Range 200 condition was observed** | **PASS** |
| H | `</SEC-HEADER>` present within consumed bytes | **PASS** |
| I | `STANDARD INDUSTRIAL CLASSIFICATION` present | **PASS** |

**D in detail** — the digest is over what was pulled, with no second read to compute it:

```
wire_consumed_sha256   c08f172ba7bb2c28d1ca762acf01d0534d2a62ebf60af9bc0f9c172a2cef6f4c
retained_body_sha256   c08f172ba7bb2c28d1ca762acf01d0534d2a62ebf60af9bc0f9c172a2cef6f4c
wire_bytes_consumed    15,707        retained_body_bytes   15,707
```

**G is the load-bearing one.** A valid `206` would have proven only that the new 206 path works; the
transition condition is tied to demonstrating the **actual Defect-F condition**. The server returned
`200` to `Range: bytes=0-4095` under `Accept-Encoding: identity` — exactly the behaviour that
produced the 94.7 GB epoch — and the client bounded it.

### Two observations that strengthen the result

1. **`wire_truncated_at_ceiling = true`** — the read stopped by *our own stopping rule*, not because
   the server ended the stream. The bound was actively exercised, not incidentally satisfied.
2. **`response_content_length = null`** — SEC used chunked transfer encoding, so no entity size was
   advertised. The bound therefore held **with no advance notice of how large the entity was**,
   which is stronger than bounding against a declared `Content-Length`. It also confirms
   `Content-Length` is metadata the implementation does not depend on.

---

## 3. Provenance — verified before the network call

| item | value |
|---|---|
| implementation commit | `517cab0fe28b03cc28d3929a932c6855e3967dc2` |
| ephemeral canary host | `i-073001108a2aa7136` (t4g.small, us-east-1c, research plane, no broker capability) |
| blob verification | **11/11 PASS on the host** against `517cab0`, incl. `sec/client.py` = `6c1d7006f42f` and frozen `spine.py` = `3f37faba3861` |
| dependency gate | **PASS** — httpx 0.28.1 · httpcore 1.0.9 · `READ_NUM_BYTES` 65,536 · `http11.py` sha256 `f644ff92a0a10822544c7c30db866647f7b371d6e94585a4b03fa060dce464ff` |
| raw result artifact | `canary_result.json`, 1,813 B, sha256 `7ef617ff98b5a1705cf5a34238877f41e4d512bef486d75f4ec84cc21fd40026` |

**Scope discipline:** exactly **one** accession, **one** request, 0.121 s, zero retries. No batch, no
successor identities, no opportunistic crawl. `5b26ffa2…` was not consumed.

### ⚠ A provenance defect caught during setup — recorded, not smoothed over

`git archive` **silently applied CRLF conversion on export**, shipping the *worktree* representation
of `client.py` (3,474 B, 92 CR bytes) instead of the committed blob (3,382 B, 0 CR). The on-host
blob verification caught it: the payload hash matched while the blob identities did not.

Rebuilt with `git -c core.autocrlf=false -c core.eol=lf archive`, after which all 11 blobs
reproduced their `517cab0` identities exactly.

> **Had the canary run without on-host blob verification, it would have executed code that was not
> byte-identical to `517cab0` while claiming that it was.** Functionally the CRLF variant behaves
> the same in Python — which is precisely why this class of defect survives testing and can only be
> caught by identity checks.

A second, separate issue was a bug in the *verifier itself*: `\\0` in a shell-escaped heredoc
collapsed to a literal backslash-zero rather than a NUL byte, so the first run compared
non-Git-blob hashes and reported 11 spurious failures. Corrected with `bytes([0])`. Recorded so the
first FAIL output in the execution log is not later mistaken for a real mismatch.

---

## 4. Bound scope — restated, because the canary does not widen it

| property | status |
|---|---|
| `wire_bytes_consumed <= RESPONSE_CONSUMPTION_CEILING_BYTES` | **HARD** — proven here at 15,707 |
| a 4 KiB logical range causes only 4 KiB of socket consumption | **NOT guaranteed** — 15,707 > 4,096 |

The observed 15,707 bytes exceed the 4,096-byte *window* and are well within the governed *ceiling*.
That is the documented and expected granularity of the pinned HTTP stack. §7C binds total response
consumption; the canary proves that bound.

---

## 5. What this result does and does not establish

**Establishes:** the repaired transport bounds actual socket consumption under the genuine
ignored-`Range` 200 condition, classifies it explicitly, hashes incrementally over exactly what it
pulled, and closes without draining — with the pinned client byte-identical throughout.

**Does not establish:**

- ⛔ SIC classification *correctness* for this or any filing — assertion I confirms the field is
  present in the consumed bytes, nothing about its value being right;
- ⛔ anything about the 374 halted units, which remain nonconforming acquisition evidence;
- ⛔ successor-epoch readiness. The successor still starts at **0/1,167**.

---

## 6. State at sealing

```
governed canary   PASS (sealed by this record)
Defect F          OPEN - pending adjudication of this result
successor         BLOCKED at 0/1,167
5b26ffa2...       UNSPENT
```

Per §7C, a canary PASS closes the **implementation** question for F. The disposition itself is a
separate act, recorded in its own artifact — this record does not perform it.
