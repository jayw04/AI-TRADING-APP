# SEC-001 V3 — Defect-F Pre-Change Implementation Baseline v1.0

**Purpose:** freeze the code identities **before** the §7C repair is written, so the implementation
evidence can later prove both **what changed** and — the harder and more important half — **what did
not change**.

**Authority:** ruling `SEC001_V3_AcquisitionDefect_F_IgnoredRangeUnboundedRetention_v1_0.md` §7C,
sealed at commit `89b7399`. This baseline executes no repair and changes no state:
**Defect F OPEN · successor BLOCKED at 0/1,167 · `5b26ffa2…` UNSPENT.**

Captured on branch `research/mr002-validation2-lineage` @ `c819539`. Every path below was
`git status`-clean at capture: **tracked and unmodified**.

---

## 1. Baseline identities

Two identities are recorded per file. The **Git blob** is the durable one; the LF-normalized SHA-256
is a secondary check.

⚠ **Do not use raw worktree SHA-256 as an identity here.** This worktree is CRLF, so a naive
`sha256sum` yields a Windows-local value that matches neither the deployed artifact nor the Git
object. Example: `client.py` hashes to `2f038db1…` on disk but is `7d74eda4…` once normalized.

| file | bytes (LF) | git blob | LF-normalized sha256 (first 32) |
|---|---:|---|---|
| `sec/client.py` | 3,382 | `6c1d7006f42f` | `7d74eda48df1910277b9745700a53686` |
| `sec001_v3/__init__.py` | 251 | `a50bc6c76896` | `c7844b47efc706caa4823e54b2050a83` |
| `sec001_v3/decision_bytes.py` | 6,571 | `06de91a92acc` | `dcbbd42b835deb576442839400f5c56d` |
| `sec001_v3/driver.py` | 13,659 | `c6f147eda499` | `6660855449606e445ffb5b8b99949ff9` |
| `sec001_v3/evidence.py` | 4,250 | `cdd61346212c` | `7ec15370bb187a463a1d2f14e1cbef8a` |
| `sec001_v3/fetch.py` | 26,561 | `48339d8ec213` | `ada0b46bd8cb113111b9620fccb2ea3b` |
| `sec001_v3/forbidden.py` | 5,595 | `8570677325aa` | `0a9d221b024bb1f8af89d45a9b4e1d0b` |
| `sec001_v3/policy.py` | 8,607 | `146b6d93fda5` | `e4915401491408ea0910945870725660` |
| `sec001_v3/sections.py` | 7,645 | `ae97502b1c9a` | `79880f7a1ce1e1d86e1d22dd90cb59a4` |
| `sec001_v3/spine.py` | 4,115 | `3f37faba3861` | `96582ca9d0d1d225157654acfd811e99` |
| `sec001_v3/state.py` | 7,125 | `0d23793590d8` | `38926ef941dc9b7aabfc387c747aeb22` |

---

## 2. The pinned client reconciles three ways — boundary 1 has a hard target

| identity | value | source |
|---|---|---|
| Git blob | **`6c1d7006f42f9e86121dce641af6cea525b235b8`** | this repository |
| LF-normalized sha256 | **`7d74eda48df1910277b9745700a5368636ef8f5437991d33689d22e53a2fbe90`** | this worktree |
| deployed on the failed-epoch volume | **`7d74eda48df19102…`** — identical | read during the §4.2.1 determination |

> **Boundary 1 — THE BINDING INVARIANT.** Before and after the repair:
>
> ```
> git rev-parse HEAD:apps/backend/app/altdata/sec/client.py
>   == 6c1d7006f42f9e86121dce641af6cea525b235b8
> ```
>
> Any other value means the repair reached the pinned client and the §7C **stop-work condition has
> fired**.

**Which identity means what — do not substitute one for another:**

| identity | value | status |
|---|---|---|
| Git blob | `6c1d7006f42f…` | **the binding invariant**; assert this |
| LF-normalized sha256 | `7d74eda48df1…` | the **deployed-content identity** — what actually ran |
| worktree sha256 (CRLF) | `2f038db1ca43…` | **a worktree representation only.** Never an identity |

This is the same end-of-line ambiguity caught during authority custody: a "client unchanged" claim
asserted against the CRLF value would be meaningless, because that value tracks this Windows
checkout rather than either the repository object or the deployed artifact.

---

## 3. `fetch.py` — provenance of the file the repair will modify

The deployed copy can no longer be read directly: the investigation copy was deleted after its
uniqueness check, and the original host is stopped (restarting it is not authorized). Identity was
therefore established by **line-offset fingerprint** against offsets observed on the deployed copy
during the §4.2.1 determination. All nine match:

```
L137  class RecordingTransport(httpx.BaseTransport):          MATCH
L149      def handle_request(self, request: httpx.Request)    MATCH
L160          response = self._inner.handle_request(request)  MATCH
L163          raw = b"".join(cast("Iterable[bytes]", ...))    MATCH   <- the defect
L197          return httpx.Response(                          MATCH
L432      def get_json(self, url: str)                        MATCH
L437      def get_text(self, url, *, headers=None)            MATCH
L444          if headers and headers.get("Range") == ...      MATCH
L487              if requests >= HEADER_COMPLETION_MAX_...    MATCH
```

### Status of this identity claim — read this before citing it

> **Deployed `fetch.py` identity: strongly corroborated, not cryptographically re-established after
> teardown.** The §4.2.1 determination was itself made from **direct inspection of the deployed
> snapshot-derived copy before teardown**, including reading
> `raw = b"".join(cast("Iterable[bytes]", response.stream))` at line 163.

The nine matching offsets are **corroboration that the present worktree corresponds to that observed
implementation** — they are *not* the evidentiary basis of the original finding, and must never be
cited as such. The finding rests on direct observation of the deployed code; this fingerprint only
links today's editable copy to it.

Nine independent offsets across a 26,561-byte file agreeing exactly is strong evidence, **not
proof**. The only proof available would require reading the preserved volume again, which is neither
authorized nor warranted: it would not strengthen the determination, which was already made from the
deployed bytes directly.

---

## 4. Change scope under §7C

**May change** (V3-owned recording/acquisition path):

- `sec001_v3/fetch.py` — `RecordingTransport` and surrounding acquisition logic (primary target)
- `sec001_v3/policy.py` — consumption ceiling and response-classification constants
- `sec001_v3/decision_bytes.py` / `sec001_v3/evidence.py` — only to carry the §4.2.3 successor
  fields (`wire_bytes_consumed`, `wire_consumed_sha256`, `range_honored`, selected-interval fields)

**Must NOT change — assert unchanged after the repair:**

- `sec/client.py` — blob `6c1d7006f42f` (boundary 1)
- `sec001_v3/spine.py` — blob `3f37faba3861`, the frozen MR-002 spine; all SIC interpretation stays
  there
- `sec001_v3/sections.py` — `ae97502b1c9a`
- `sec001_v3/forbidden.py` — `8570677325aa`
- `sec001_v3/__init__.py` — `a50bc6c76896`

If `decision_bytes.py` or `evidence.py` require more than additive fields, that is a signal to stop
and re-scope rather than widen the blast radius silently.

---

## 5. Canary headline assertion

The decisive quantity is **`wire_bytes_consumed`**, not artifact size:

```
target accession   0000065984-14-000065
full entity        422,424,674 bytes
SEC header closes  byte 6,195
REQUIRED           wire_bytes_consumed <<  422,424,674, at or below the governed ceiling
FAIL               small retained artifact + large wire_bytes_consumed
```

That failure mode is the one worth naming explicitly: it satisfies a superficial **disk** criterion
while leaving Defect F intact at the **transport** layer. Report the governed ceiling and the
measured consumption side by side.

Proven separately, none of them substituting for the above: response classification
(`200_FULL_RANGE_IGNORED` vs validated `206` + `Content-Range`, no implicit third state);
incremental hashing over exactly the consumed/retained bytes; early close without draining the
remainder; retained-artifact size; evidence internally reproducible; and pinned-client blob
invariance per §2.

---

## 6. State machine — unchanged by this baseline

```
implementation complete        != F closed
unit tests pass                != F closed
synthetic streaming test pass  != F closed
governed real canary on 0000065984-14-000065 meeting every binding requirement = F may CLOSE
F closed                       != successor started
```
