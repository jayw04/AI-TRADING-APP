# SEC-001 V3 — Defect-F Closure Disposition v1.0

## `DEFECT_F — CLOSED / REMEDIATED AND PROVEN BY GOVERNED CANARY`

**Owner-adjudicated 2026-08-25.** This is a **separate disposition artifact**. It edits nothing:
the sealed ruling, the §4.2.1 determination, the pre-change baseline, the implementation evidence
and the canary result all stand unmodified.

---

## 1. Disposition

> The governed canary executed the sanctioned V3-local bounded-recording-transport repair against
> `0000065984-14-000065` and satisfied the binding transition condition. Actual response consumption
> was bounded by the governed ceiling; truncation was initiated by the client-side consumption rule
> rather than response exhaustion; the ignored-`Range` response was explicitly classified; evidence
> hashes were generated incrementally over the consumed bytes; and the response was closed without
> draining the remaining entity. The pinned client and other protected components remained
> unchanged. **Defect F is therefore CLOSED.**

---

## 2. Bound evidence chain

| stage | commit | content |
|---|---|---|
| §4.2.1 determination | `725e737` | prerequisite **NOT SATISFIED**, branch 3 |
| sanctioned authority + spec v0.4 | `89b7399` | ruling §7C, five normative boundaries, mechanical transition condition |
| prospective baseline | `5db2d3e` | pre-change code identities, sealed **before** any edit |
| implementation | `517cab0fe28b03cc28d3929a932c6855e3967dc2` | bounded transport; protected blobs re-asserted at the commit |
| governed canary result | `e500bcc` | **PASS**, nine assertions, raw artifact `7ef617ff…` |
| canary reproducibility tooling | `7220efe` | `canary.py` · `gate.py` · `verify_blobs.py` |
| **closure disposition** | *this record* | **F CLOSED** |

Earlier custody in the same chain: `4e960e2` (snapshot custody + Pass-1 INTERIM), `4394eef`
(Pass-2 byte verification), `c95bcbe` (Pass-2 reproducibility artifacts).

---

## 3. Why the result is dispositive

```
accession            0000065984-14-000065        known entity  422,424,674 bytes
http_status          200                         range_class   200_FULL_RANGE_IGNORED
wire_bytes_consumed  15,707                      ceiling       1,048,576
```

Two observations make the PASS **stronger**, not merely adequate:

1. **`wire_truncated_at_ceiling = true`** — the response did **not** end naturally before the
   governed limit. The implementation itself stopped consumption. This addresses Defect F's causal
   mechanism directly rather than by coincidence.
2. **`response_content_length = null`** — SEC used chunked transfer encoding. The transport enforced
   the bound **without relying on advance knowledge of body size**: the protection operates on
   *actual consumption*, not on a convenient `Content-Length` check.

Together with the nine assertions, sealed implementation identity `517cab0`, protected-client
invariance (`6c1d7006f42f`), incremental hashing, explicit response classification and early close,
the implementation question is no longer promising — the governed empirical gate has passed.

---

## 4. What this closure explicitly does NOT claim

- ⛔ **SIC classifications are correct.** Canary assertion I confirmed only that
  `STANDARD INDUSTRIAL CLASSIFICATION` is *present* in the consumed bytes. Nothing about the value.
- ⛔ **The 374 failed-epoch units become admissible.** They remain preserved nonconforming
  acquisition evidence. Byte integrity (Pass 2) never made them conforming.
- ⛔ **§5.1b Q5 changes.** The coverage table is unchanged; no coverage has been produced.
- ⛔ **The successor crawl has started.** It has not.
- ⛔ **The successor epoch is automatically authorized.** Closing F does not start anything.

`5b26ffa2…` remains **UNSPENT** until the successor-start act is itself explicitly authorized.

---

## 5. Execution blemishes — deliberately preserved

Retained in the chain because deleting first-failure observations would make the record weaker.
Neither invalidates the canary, because the final code and payload identities were **independently**
established before the network call.

**5.1 — `git archive` CRLF conversion.** Export silently applied end-of-line conversion, shipping
the *worktree* representation of `client.py` (3,474 B, 92 CR bytes) instead of the committed blob
(3,382 B, 0 CR). On-host blob verification caught it: **the payload hash matched while the blob
identities did not.** Rebuilt with `git -c core.autocrlf=false -c core.eol=lf archive`, after which
all 11 blobs reproduced their `517cab0` identities.

> **The distinction this incident establishes: payload/content identity is not Git/code identity,
> and the two must never be casually treated as the same proof.** A matching payload digest proves
> the bytes arrived intact; it proves nothing about *which* bytes were sent. Only the per-file blob
> check answered that. The CRLF variant is functionally identical in Python — which is exactly why
> this defect class survives testing and is visible only to identity checks.

**5.2 — verifier bug.** The first on-host verification reported 11 spurious FAILs because `\\0` in a
shell-escaped heredoc collapsed to a literal backslash-zero rather than a NUL byte, so it was not
computing Git blob hashes at all. Corrected with `bytes([0])`. Recorded so that first FAIL output is
never later mistaken for a genuine mismatch.

---

## 6. Program state after this closure

```
Defect F          CLOSED / remediated and proven by governed canary
Defect G          CLOSED / REFUTED (Pass-2 forensic hypothesis, not a 7th crawl defect)
successor epoch   ELIGIBLE FOR SEPARATE AUTHORIZATION - still at 0/1,167, NOT started
5b26ffa2...       UNSPENT
coverage          NOT EVALUATED          economics   NOT EVALUATED
374 units         preserved nonconforming acquisition evidence
```

The next decision is a **separate adjudication**: whether to authorize the successor epoch start at
0/1,167. Closing F is a precondition for that decision, not the decision itself.
