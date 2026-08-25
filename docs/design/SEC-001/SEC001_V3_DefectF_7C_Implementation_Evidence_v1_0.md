# SEC-001 V3 — §7C Implementation Evidence v1.0

## `V3_LOCAL_BOUNDED_RECORDING_TRANSPORT_REPAIR` — IMPLEMENTATION REVIEW **PASS / READY FOR GOVERNED CANARY**

**Authority:** ruling `SEC001_V3_AcquisitionDefect_F_IgnoredRangeUnboundedRetention_v1_0.md` §7C,
sealed at commit `89b7399`. Pre-change baseline sealed at `5db2d3e`.

⛔ **This record does not close Defect F.** Implementation PASS is not a disposition:
**Defect F OPEN · successor BLOCKED at 0/1,167 · `5b26ffa2…` UNSPENT.** Only the governed canary on
`0000065984-14-000065` can transition F.

---

## 1. The P0 that review caught — recorded, not smoothed over

The first repair was **still defective** and the adversarial test proved it rather than argued it:

```
ceiling 1,048,576   consumption at stop-1 then one 8 MiB chunk
=> wire_bytes_consumed = 9,371,647     *** DEFECT F SURVIVED THE FIRST REPAIR ***
```

The first implementation guaranteed only *"stop requesting another chunk once cumulative consumption
reaches the ceiling"*. The sealed determination requires *"consumes at most ceiling bytes"*. Those
are not equivalent: the final chunk is pulled **before** the check, so slicing it afterwards keeps
the artifact small while the bytes have already crossed the socket. That is why
`wire_bytes_consumed` — not artifact size — is the governing field.

---

## 2. How the hard bound is established

**M is proved from the pinned implementation, not inferred from observed traffic.**
`httpcore/_sync/http11.py:44` declares `READ_NUM_BYTES = 64 * 1024`, and it bounds every network
read:

```python
data = self._network_stream.read(self.READ_NUM_BYTES, timeout=timeout)
```

| dependency | identity |
|---|---|
| httpx | 0.28.1 |
| httpcore | 1.0.9 |
| `HTTP11Connection.READ_NUM_BYTES` | **65,536** |
| `httpcore/_sync/http11.py` sha256 | `f644ff92a0a10822544c7c30db866647f7b371d6e94585a4b03fa060dce464ff` (3,445 B) |

`test_max_upstream_chunk_matches_the_pinned_transport` binds
`HTTP11Connection.READ_NUM_BYTES == policy.MAX_UPSTREAM_CHUNK_BYTES`, so dependency drift **fails
loudly** rather than silently widening the overshoot the guard band is sized against.

**Guard band arithmetic:**

```
RESPONSE_CONSUMPTION_CEILING_BYTES   1,048,576   (hard, governed)
MAX_UPSTREAM_CHUNK_BYTES                65,536   (proved M)
CONSUMPTION_STOP_THRESHOLD_BYTES       983,040   = ceiling - M
worst compliant pull   983,039 + 65,536 = 1,048,575  <  1,048,576   PASS
```

**Defense in depth, not the proof.** `ConsumptionCeilingExceeded` raises if
`wire_bytes_consumed` ever exceeds the hard ceiling. It is **not** what establishes the physical
bound — an upstream component violating its proven M contract could return too many bytes before the
check runs. The bound comes from the pinned 64 KiB read contract plus the guard band; the exception
prevents a silent return to Defect-F behaviour. It is what caught the defective first repair.

---

## 3. Scope of the bound — stated precisely

| property | status |
|---|---|
| `wire_bytes_consumed <= RESPONSE_CONSUMPTION_CEILING_BYTES` | **HARD — guaranteed, and what §7C binds** |
| a 4 KiB logical range causes only 4 KiB of socket consumption | **NOT guaranteed** |

The second is a granularity property of the pinned HTTP stack: a 4 KiB window against a large entity
may pull one 64 KiB chunk. Changing that would require modifying the pinned client, which §7C
forbids. The authority binds **total response consumption**, and that bound is proven.

---

## 4. Implementation

`_consumption_ceiling` was renamed **`_consumption_stop_threshold`** — it returns a stop point
deliberately *below* the ceiling, and the old name invited exactly the conflation behind the P0.

- classification happens **before** consumption, so the bound derives from the request's intent
  rather than the server's response;
- pull-bounded loop with **incremental** hashing — no second read to compute a digest;
- `response.close()` after the stopping condition, remainder never pulled;
- refusals: `206` without `Content-Range`, or with a `Content-Range` inconsistent with the request →
  `RangeContractViolation`. No silent third state.

Additive `_Capture` fields: `wire_bytes_consumed`, `wire_consumed_sha256`,
`response_content_length`, `range_class`, `range_honored`, `wire_truncated_at_ceiling`.

---

## 5. Verification

```
Defect-F tests            12 PASS
sec001_v3 module tests   150 PASS
ruff check                   PASS      mypy   PASS
```

⚠ `ruff format` **not** run: both files were already format-drifted at `HEAD` before this repair, so
reformatting would bury a governed diff in unrelated whitespace. Pre-existing repo state, verified
against the `HEAD` blobs.

### Protected blobs — all unchanged

```
PASS  sec/client.py               6c1d7006f42f   <- BINDING INVARIANT
PASS  sec001_v3/spine.py          3f37faba3861   <- frozen MR-002 SIC spine
PASS  sec001_v3/sections.py       ae97502b1c9a
PASS  sec001_v3/forbidden.py      8570677325aa
PASS  sec001_v3/__init__.py       a50bc6c76896
PASS  sec001_v3/decision_bytes.py 06de91a92acc
PASS  sec001_v3/evidence.py       cdd61346212c
PASS  sec001_v3/driver.py         c6f147eda499
PASS  sec001_v3/state.py          0d23793590d8
```

`decision_bytes.py` and `evidence.py` are **unchanged**: the §4.2.3 fields fit additively on
`_Capture` inside `fetch.py`, so the schema tripwire never fired and the blast radius stayed
*narrower* than authorized.

### Changed files

| file | baseline blob | implementation blob |
|---|---|---|
| `app/altdata/sec001_v3/fetch.py` | `48339d8ec213` | `b19145b774d8` |
| `app/altdata/sec001_v3/policy.py` | `146b6d93fda5` | `37ca0165b17d` |
| `tests/…/test_defect_f_bounded_transport.py` | *(new)* | `5acbdf2ec666` |
| `tests/…/test_fetch_policy.py` | *(fixture correction)* | `3e48997d4f47` |
| `tests/…/test_header_completion.py` | *(fixture correction)* | `9fdf07776c00` |

### Fixture correction — recorded as such, not as test churn

Three pre-existing fixtures constructed a `206` with **no `Content-Range`**, and one hardcoded
`bytes 0-4095` while the progressive loop requested later windows, so it misdescribed itself from
the second request onward. RFC 9110 §15.3.7 makes a `206` without `Content-Range` impossible, so
these modelled responses that cannot occur. The tightened contract correctly refuses them; the
fixtures now echo the granted range as a real server does. **This is fixture correction consequent
on a deliberate contract tightening — not incidental test churn.**

---

## 6. Canary requirements this implementation must satisfy

Headline: **`wire_bytes_consumed << 422,424,674`**, reported beside the governed ceiling.
A small retained artifact with a large `wire_bytes_consumed` is a **FAIL**.

Proven separately: explicit `200_FULL_RANGE_IGNORED` classification; incremental hashes binding
exactly the consumed bytes; early close without draining; retained-artifact size; evidence
reproducibility; and `client.py` still `6c1d7006f42f…`.

---

## 7. State

```
implementation   PASS / canary-ready
Defect F         OPEN
successor        BLOCKED at 0/1,167
5b26ffa2...      UNSPENT
```
