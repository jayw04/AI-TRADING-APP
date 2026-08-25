# SEC-001 V3 — Defect F §4.2.1 Bounded-Streaming Prerequisite: DETERMINATION v1.0

## VERDICT: **NOT SATISFIED** (fail-closed)

**Status:** Read-only determination against the owner's four frozen tests (2026-08-25). No code
changed, no implementation authorized, no successor crawl started. Performed on the read-only
snapshot-derived copy at `/mnt/evidence`.

---

## 1. The actual deployed path (Test 1)

Traced end-to-end on the **deployed** artifacts, not the library's advertised capability:

```
EdgarClient.get_text(url, headers=...)          app/altdata/sec/client.py   sha256 7d74eda4… (92 lines)
  -> httpx.Client.get(...)                      non-streaming call
    -> RecordingTransport.handle_request(...)   app/altdata/sec001_v3/fetch.py:149   [V3-OWNED]
      -> self._inner.handle_request(request)    real httpx.HTTPTransport
      -> raw = b"".join(response.stream)        fetch.py:163   *** FULL MATERIALIZATION ***
      -> response.close()                       fetch.py:164   after the entire entity is consumed
      -> body = _decode(raw, encoding)
      -> return httpx.Response(..., content=body)
  -> r.raise_for_status(); return r.text        client.py:91-92   materialized str
```

---

## 2. Test-by-test result

| test | result | evidence |
|---|---|---|
| **1. Actual pinned path inspected** | ✅ done | chain above; both files read from the evidence copy |
| **2. Bounded consumption end-to-end** | ❌ **FAIL** | `fetch.py:163` `b"".join(response.stream)` consumes the whole entity before any downstream consumer sees a byte |
| **3. Survives the Defect-F case** | ❌ **FAIL** | no ceiling, no `200_FULL_RANGE_IGNORED` classification, no early stop, no cancel; `close()` occurs only after full consumption. A 422 MB entity is fully read |
| **4. Evidence sound without full-body materialization** | ❌ **FAIL as designed** | `_Capture` holds `wire=raw` and `body=body` as whole objects; every digest is computed over complete in-memory bytes. Retention is currently sound *because* it materializes |

> ⚠ **`fetch.py:161-162` documents why the stream is iterated rather than `.read()`** — to avoid
> httpx's content decoder, so the recorded bytes are as they arrived. That is a *decoding* concern,
> **not a bounding** one. Iterate-then-join is materialization with extra steps.

---

## 3. Which branch of the ruling applies

The pinned client's **entire public surface is materializing by construction**:

```
get_json(url)                    -> r.json()
get_text(url, *, headers=None)   -> r.text
```

There is **no streaming method, no bounded read, no consumption ceiling** anywhere in its 92 lines.
It accepts `transport=` (an `httpx.BaseTransport`) — the documented seam V3 already uses.

> **Branch 3 applies: the pinned client/path offers no enforceable body-consumption ceiling.**
> It is *not* branch 2 — branch 2 presumes the client can stream and only the recorder spoils it.
> Here neither layer can bound consumption today.

---

## 4. The material nuance — and why it does not change the verdict

**The materializing line is in `fetch.py`, which is V3-owned.** Its own docstring states: *"Nothing
in this module modifies the pinned client. It composes with two seams the client already exposes:
the `transport=` constructor argument … and the `headers=` keyword."*

So a bounded repair is *conceivable* entirely inside `RecordingTransport`: read incrementally from
`response.stream`, stop at the governed ceiling, `close()` early, and hand the client a short body.
`httpx.Client.get()` would then materialize only the bounded bytes, and `client.py` would never
need to change — socket consumption bounded, pinned client untouched.

**That path is reasoned from the code, not demonstrated.** It has not been exercised against a
real ignored-`Range` 200, and the owner's rule is explicit:

> *uncertain or partially demonstrated → fail closed as NOT SATISFIED.*

**Verdict stands: NOT SATISFIED.** What it changes is the *likely remedy*: the evidence points
toward a **V3-local transport repair** rather than a frozen-client rewrite — but that is a
hypothesis for the Defect-F adjudication to test, not a finding.

---

## 5. What would convert this to SATISFIED

1. A `RecordingTransport` that consumes at most `ceiling` bytes from `response.stream`, closes
   early, and never buffers the remainder — demonstrated against a real 200-with-large-entity.
2. Explicit response classification: valid `206` with `Content-Range` validated against the
   requested interval, or `200_FULL_RANGE_IGNORED` — **no silent third state**.
3. **Incremental digesting.** `wire_sha256`/`parser_body_sha256` computed with a rolling hash over
   exactly the retained prefix. This is the trade the owner named: the repair must not buy bounded
   acquisition with an evidence-integrity gap. Note this interacts with §4.2.3 — the successor
   schema's `wire_consumed_sha256` is precisely the field this produces.
4. A canary proving 1–3 on `0000065984-14-000065` (422,424,674 B, header closes at 6,195).

---

## 6. Program state

```
Pass-2 custody       CLOSED (commit 4394eef)
§4.2.1 prerequisite  NOT SATISFIED - branch 3; remedy likely V3-local but UNPROVEN
Defect F             OPEN - implementation authority NOT granted
Defect G             CLOSED / REFUTED (Pass-2 forensic hypothesis, not a 7th crawl defect)
successor epoch      BLOCKED at 0/1,167
5b26ffa2...          UNSPENT
```

Investigation host `i-034baf111469c310c` and copy `vol-0e526053c6bef5887` remain up; this
determination consumed them and they are now free for the uniqueness check preceding teardown.
