# SEC-001 V3 — Governed Canary on Implementation `66247ad` v1.0

## VERDICT: **PASS** — Gate-1 re-proof for the Gate-5 implementation

**Why a second canary exists.** Gate 5 required an artifact-granularity storage guard inside the
acquisition path. Implementing it changed `fetch.py` and `policy.py`, so the successor no longer
executes the bytes that `e500bcc` proved. Under Gate 1, a changed transport identity means the
prior canary **does not transfer** — it must be re-proven.

⛔ **`e500bcc` remains valid historical evidence for `517cab0` and is not rewritten.** This record
covers a different implementation identity.

---

## 1. Result

```
implementation      66247ad17f0e38a5f6c67ac11d74891b0e45fd3e
accession           0000065984-14-000065      known entity  422,424,674 bytes
http_status         200                       range_class   200_FULL_RANGE_IGNORED
range_honored       false                     content_length  null (chunked)
wire_bytes_consumed 15,687                    ceiling       1,048,576
truncated_at_ceiling  true                    elapsed       0.042 s
assertions          A-I  9/9 PASS
```

Gate-5 constants confirmed **live during the canary**, proving the guard was active and did not
perturb bounded transport:

```
TERMINAL_RESERVE_BYTES            2,147,483,648
PREARTIFACT_FREE_REQUIRED_BYTES   2,149,646,336
RESPONSE_CONSUMPTION_CEILING      1,048,576
CONSUMPTION_STOP_THRESHOLD          983,040
```

**Comparison with `e500bcc`** (`517cab0`): 15,687 vs 15,707 bytes consumed. The ~20-byte difference
is chunk-boundary noise on a live response, not a behavioural change — same status, same
classification, same truncation cause, same ceiling. **The Gate-5 addition does not alter bounded
transport behaviour.**

---

## 2. Prestart re-proof, all on the successor host before the network call

| gate | result |
|---|---|
| 1a blob identity vs `66247ad` | **12/12 PASS** — incl. `client.py 6c1d7006f42f`, `spine.py 3f37faba3861`, frozen `mr002/sic_history.py 48779adaaaec`; changed: `fetch.py 62646f2d2190`, `policy.py 53d21a15ac62` |
| 1b dependency identity | **PASS** — httpx 0.28.1 · httpcore 1.0.9 · `READ_NUM_BYTES` 65,536 · `http11.py` sha256 `f644ff92…` |
| 2 runtime forms | **PASS** — `policy.FORMS` includes 20-F/20-F/A/40-F/40-F/A, driver wired, frozen spine unchanged, `CRAWL_SINCE 2000-01-01` |

Payload built with `git -c core.autocrlf=false -c core.eol=lf archive`, sha256
`10f3ffb9e48689d5a8bcf2d2360711395ef884b2942001a6cc963072246f101e`, blob-verified on the host —
the CRLF-export lesson applied.

---

## 3. Scope and non-claims

One accession, one request, 0.042 s, zero retries. `5b26ffa2…` **not** consumed; the successor
epoch has **not** started and remains at **0/1,167**.

This record establishes only that `66247ad` reproduces the Defect-F bound. It does **not** close
Gate 5 — the controlled-stop end-to-end proof is separate and still pending — and it makes no claim
about SIC correctness, the 374 halted units, or Q5.
