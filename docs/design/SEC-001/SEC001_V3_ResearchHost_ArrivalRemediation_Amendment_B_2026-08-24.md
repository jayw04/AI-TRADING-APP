# Amendment B — SEC-001 V3 Research Host, Arrival-Gate remediation

**Date:** 2026-08-24 · **Host:** `i-00e6b78fcabd32413` · **Status:** FROZEN before remediation
**Amendment A (`32bc34e9d337719a29e767c8f22c986f1e98fc49`) is unchanged and remains the authorization
for the augmentation it described.** This amendment authorizes remediation of two defects the Arrival
Gate caught. `5b26ffa2…` remains **UNSPENT**; the research store is not rebuilt.

---

## 1. The Arrival Gate failed closed — as designed

Delivery and offline install succeeded, then the gate rejected the delivery on byte identity. **No
EDGAR request was issued.** 14 checks passed, including the module-origin assertion, Phase-2B
fixtures 5/5, `httpx 0.28.1`, `duckdb 1.5.5`, and `pip check`. Six blob-identity checks failed,
arising from **two unrelated defects**.

## 2. Defect 1 — augmentation archive byte-identity failure (builder defect)

**Cause:** the archive was built from a Windows checkout with `core.autocrlf=true`, so Git converted
LF→CRLF on checkout and the tar captured working-tree bytes.

| file | delivered | expected | CRLF pairs |
|---|---|---|---|
| `sic_history.py` | 7,919 B / `264a526ee105` | 7,719 B / `48779ada…` | 200 |
| `eligibility.py` | 8,381 B / `010f06b815b3` | 8,204 B / `b9eb4a6d…` | 177 |

LF-normalising each delivered file reproduces the expected Git blob **exactly**. Content is
identical; **the delivered bytes are nonconforming regardless.** The only file that passed is the
zero-byte `app/research/mr002/__init__.py`, which has no line endings to corrupt — a reminder that a
single green check can be structurally incapable of failing.

⚠ **Repeat process nonconformance.** This is the same CRLF class already recorded in the SEC-001
production-conformance incident §13.2, reproduced hours later *while building the very artifact whose
purpose is byte identity*. It is recorded as a repeat, not an isolated typo.

### 2.1 Corrective action — general source-custody rule

> **Any evidence or deployment archive whose gate requires Git byte identity MUST be built from Git
> objects (`git archive`, or `git cat-file blob` into a staging tree), or from a checkout proven to
> have `core.autocrlf=false`. Working-tree bytes from an uncontrolled Windows checkout are
> INADMISSIBLE.**

Additionally, an **automated pre-package check** must compare every governed source file against its
expected Git blob hash *before* the tar is created. The gate must not be the first place this is
detected. This prevents a third occurrence.

## 3. Defect 2 — EDGAR client provenance mismatch (host-acquisition defect)

The host's `app/altdata/sec/client.py` was **never part of the augmentation**; it arrived with the
original host build.

```
host blob    258c570dee3023a26591c4f7aec1c6b9f861e081   3,169 B  sha256 cd6672167f4d4401...
pinned blob  6c1d7006f42f9e86121dce641af6cea525b235b8   3,382 B
delta        213 bytes — NOT line endings (host has 0 CRLF; LF-normalising changes nothing)
mtime        2026-08-24 02:17:49 UTC
```

**The difference is functional, not cosmetic.** The host runs an older `get_text` that cannot accept
headers:

```diff
-    def get_text(self, url: str) -> str:
+    def get_text(self, url: str, *, headers: dict[str, str] | None = None) -> str:
+        """GET text; optional extra headers (e.g. a Range header to read only an SGML
+        header block from a large full-submission archive file)."""
         self._throttle()
-        r = self._client.get(url)
+        r = self._client.get(url, headers=headers)
```

⚠ **The authorized crawl path requires that capability.** `sic_history.py:94-95`:

```python
return client.get_text(  # type: ignore[call-arg]
    full_submission_url(cik, accession), headers={"Range": "bytes=0-4095"}
)
```

Consequences of adopting the host blob instead of replacing it:

1. `TypeError: get_text() got an unexpected keyword argument 'headers'` on the first
   full-submission fetch; **or**
2. if "repaired" by dropping the Range header, the crawl downloads **entire multi-MB full-submission
   archives** for 1,167 identities across 26 years instead of 4 KB slices — directly contrary to
   SEC's request to download only what is needed, and a plausible route to the 403 IP-limitation that
   V3 policy treats as a hard stop.

⭐ The `# type: ignore[call-arg]` on line 94 exists because the `_Fetcher` Protocol (line 42) declares
`get_text(self, url: str) -> str` without headers. Static checking was silenced at precisely the call
that diverges, which is why this survived until arrival-gate time.

### 3.1 Ruling

**The divergent host blob is NOT promoted to authority.** Accepting `258c570d…` after discovering it
would let the environment determine the specification instead of the specification determining the
environment — reversing the purpose of the pre-crawl identity block, which exists to bind the
behaviour controlling SEC fair-access, throttling, User-Agent enforcement and failure handling.

`258c570d…` is preserved as **pre-remediation forensic evidence only**. It is diagnostic and must
**not** influence any redesign of the client.

## 4. Authorized remediation — exactly this, nothing more

1. **Rebuild** the six-file augmentation with Git-exact bytes, sourced from Git objects (not a
   working-tree checkout), from the remotely custodied `a0a779f2bbeedc1b4b2eddab538fd0bbb1a5d5d8`.
2. **Supersede** Build Record v1.0 (`92f3eb7`) with **Build Record v1.1**. `92f3eb7` is **not
   edited**; it is marked *delivered, rejected by Arrival Gate*.
3. **Replace** the nonconforming host `app/altdata/sec/client.py` **solely** with the exact pinned
   Git blob `6c1d7006…`, delivered from the same remotely verified source custody — not copied from
   an operator working tree.
4. **Preserve** the pre-remediation host copy as forensic evidence: bytes, sha256, size, unified diff
   against the pinned blob, timestamp, path, and source-host identity.
5. **No other original host file may change.**
6. **Rerun the ENTIRE Arrival Gate from zero.** Previously green checks are evidence, not credit —
   module-origin assertions and Phase-2B fixtures included.
7. **No EDGAR request** until the complete gate passes.

⛔ Not authorized: any client redesign; any change to the sealed store, PIT-200 population, governed
grid, universe implementation or coverage rules; any MR-002 program execution; any merge of
`research/mr002-validation2-lineage`.

## 5. Post-replacement verification

```
host client.py sha256      == sha256 of pinned blob 6c1d7006...
host client.py Git blob    == 6c1d7006f42f9e86121dce641af6cea525b235b8
app.altdata.sec.client.__file__ == /opt/sec001-src/apps/backend/app/altdata/sec/client.py
```

Plus deterministic client fixtures, **no network traffic issued**:

- User-Agent absent → `EdgarDisabled` (fail closed, never anonymous fetch)
- configured User-Agent retained exactly
- `rate_limit_per_sec=5.0` honoured by constructor state (`_min_interval == 0.2`)
- throttle path callable
- `get_text` accepts `headers=` (the capability that failed)
- 403 handled by the V3 driver as a stop/cool-down policy, **not** by hidden client retry
- 429 / transient 5xx remain available to the driver's bounded-backoff layer

## 6. Unchanged identities

```
qualified_store_sha256      89c4680f76a556d56ccd2e055605b3925375366fca41a40910edd1b844216d39
qualified_store_version_id  CWQjPoJDRPIHcfQUjqMU1ynWyp5x4Umr
population_union_sha256     d338e65f9ece1ff74bab8f7e7e098529c8466c8074d215e5894c402b35450872
population_identity_count   1167
membership_sha256           045b634946c3206a1d6228bd388de4a9f1b9a64ac90e67620dbfa5b937627754
grid_sha256                 baf0da7c20bed5903986c9a94ffae5f54c06cbcba23adb1242ca27e415305a51
universe_impl               cc27f47   (PIT_LIQUID_TOP_N_V2)
coverage_freeze             5b26ffa209a6...    state = UNSPENT
```

Neither defect consumes the coverage freeze, and neither requires rebuilding the research store.
