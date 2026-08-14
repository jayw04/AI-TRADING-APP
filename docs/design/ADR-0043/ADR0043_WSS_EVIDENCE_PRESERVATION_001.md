# Owner Decision — Authorize WSS Stage-C Evidence Preservation (Narrow)

| Field | Value |
|-------|-------|
| Ruling ID | ADR0043-WSS-EVIDENCE-PRESERVATION-001 |
| Decision | **APPROVED / EFFECTIVE** — owner ruling 2026-08-14, subject to the §4 clarification |
| Scope | **Durable preservation of one existing evidence file.** Read → verify → store → verify. Nothing else. |
| Drafted (UTC) | 2026-08-14 |
| Parent disposition | WSS DEFER / CLEAN LAPSE (owner ruling, 2026-08-14) |
| Substrate build | **Not authorized — unchanged** |
| Trading activation | **Separately gated — unchanged** |
| Early teardown / extension | **Not authorized — unchanged** |

---

## Ruling (proposed)

The parent disposition directs: *"Preserve current evidence and resource state subject to the
existing expiration/teardown terms."* Preservation of **resource state** is satisfied by inaction.
Preservation of **evidence** is not: the Stage-C artifact exists in exactly one location, on a volume
whose teardown terms are the very terms the disposition leaves running.

This authorization permits copying **one already-existing file** from the WS5 volume to the governed,
versioned evidence bucket, with hash verification on both ends. It creates no new evidence, advances
no substrate stage, and grants no capability that survives the copy.

---

## 1. Binding identities

| Identity | Value |
|----------|-------|
| Source file | `/var/lib/adr0043-ws5/evidence/stage_c_20260804T152020Z.json` |
| Size / mode | 1167 bytes · `0600 root:root` · mtime 2026-08-04 15:20 UTC |
| `evidence_file_sha256` | `79011ea493cf0392dfa97b76ccb4f99e23623aa666672d9d8b82876acc647463` |
| Host | `i-0fff7076ad461aa9a` (running, SSM Online, arm64 t4g.medium) |
| Volume | `vol-0710769fb6981102d` (encrypted, 20 G, `DeleteOnTermination=false`) |
| Destination bucket | `adr0043-ws5-evidence-219024422756-us-east-1` |
| Proposed key | `stage-c/stage_c_20260804T152020Z.json` |
| Stage D record (hashes only, in Git) | PR #609, squash `7e3e0a51` |

⚠ **Do not conflate two hashes.** `evidence_file_sha256` (`79011ea4…`) is the hash of the **file**,
which is what this authorization verifies. `artifact_sha256` (`987bd76f…`) is the hash of the
**record with its own `artifact_sha256` key removed**, canonicalised, no trailing newline. The file
additionally has `"\n"` appended. Only `79011ea4…` is in scope here.

### 1.1 Destination is already governed (verified 2026-08-14)

| Property | State |
|----------|-------|
| Versioning | **Enabled** |
| Default encryption | SSE-S3 `AES256`, bucket key enabled |
| Public access block | All four settings `true` |
| Existing objects | 6 — `hashes/` ×2, `source/` ×3, `stage2/` ×1 |

⚠ **Correction to the prior record.** Earlier notes state this bucket holds **0 objects**. That was
true at survey time (2026-08-02) and was invalidated by the Stage-1 uploads on 2026-08-03. The
substantive finding is unchanged and is the reason for this authorization: **no Stage-C object exists
under any prefix.**

---

## 2. Mechanical allow-list

### 2.1 Permitted

| Step | Mechanism | Notes |
|------|-----------|-------|
| 1. Read the file | SSM `AWS-RunShellScript`, `base64` the 1167 bytes | ~1,556 chars, well under the 24,000-char `StandardOutputContent` cap |
| 2. Verify at source | Recompute sha256 on the host **and** off-host after decode; both must equal `79011ea4…` | Two independent computations, not one |
| 3. Confirm non-secret | Inspect decoded content before any upload | See §4 |
| 4. Store | `s3api put-object` **from the laptop identity** (`user/admin`) with `--checksum-algorithm SHA256` | |
| 5. Verify round-trip | `get-object` the returned `VersionId`, recompute sha256, require `79011ea4…` | |
| 6. Record | `VersionId` + both hashes into the WSS memory record | |

### 2.2 The host must not gain S3 capability

The WS5 instance role is **ECR-scoped only** — `s3:GetObject`/`PutObject`/`ListBucket` are **DENIED**.
The copy therefore runs **outbound through SSM to the laptop identity**, which already holds S3
write. **Granting the instance role S3 access is PROHIBITED under this authorization** — that is an
IAM change to an adopted resource, the same class of change that blocked Stage B as finding B-3.
If the copy cannot complete without it, the copy does not happen.

### 2.3 Prohibited

| Class | Status |
|-------|--------|
| Any container run, image pull, image tag, or daemon/service restart | **Prohibited** |
| Any write, move, chmod, or delete on the host — **including the source file** | **Prohibited** (original stays in place, unmodified) |
| Any substrate stage: repin · DB create · migration checkpoint · seed strategy 9 · factor store · refresh scheduler | **Prohibited** |
| Reading or egressing any credential file or credential material | **Prohibited** |
| CloudFormation update to either stack | **Prohibited** (2026-07-27 replacement incident) |
| Adding, altering, or removing any resource tag | **Prohibited** |
| Early teardown, or any action extending a resource beyond its existing terms | **Prohibited** |
| Overwriting or deleting any existing object or version in the bucket | **Prohibited** |

---

## 3. Execution window — one clock, stated once

| Field | Value |
|-------|-------|
| Effective from | Owner approval, 2026-08-14 |
| **Window closes** | **2026-08-16T12:00:00Z** |
| Earliest governing resource clock | 2026-08-17T04:59:59Z (`expires_on` = 2026-08-16 23:59:59 America/Chicago, CDT = UTC−5) |
| **Safety margin** — window close → resource clock | **16 h 59 m 59 s** |
| **Time available** — approval → window close | **≈ 48 h** |

⚠ **Two different quantities; do not read either as the other.** The **16 h 59 m 59 s** is the gap
between this window's close and the earliest resource expiry — it is *headroom against the resource
clock*, deliberately sized so that a late execution still lands well clear of it. The **≈ 48 h** is
the *time actually available to execute*, measured from approval on 2026-08-14. Both figures are
correct and they are not in tension. Expected execution time is **minutes**.

The parent disposition faults the current window for not being *internally consistent*. This one is
stated as **a single UTC instant**, closes **strictly inside** the earliest resource clock with
material margin, and is **not derived from, and does not reference,** either the successor
(`2026-08-18T00:26:48Z`) or the #610 substrate clock (`2026-08-18T21:41:00Z`). Those two remain
uninvoked and lapse on their own terms. Expected execution time is **minutes**; the window is sized
for scheduling, not for work.

**No extension is contemplated.** If the window closes unexecuted, the evidence remains on the volume
under existing terms and the question returns to the owner unchanged.

---

## 4. Egress boundary — **owner clarification, 2026-08-14 (controlling text)**

> SSM retrieval is an authorized inspection/transport step, not publication. No S3 publication is
> authorized until the retrieved bytes have been independently SHA-256 verified and inspected
> sufficiently to establish that the file contains no credential, secret, token, private key, or
> other prohibited sensitive material. If that inspection cannot establish non-secret status,
> execution stops and nothing is uploaded.

**Non-secret status must be positively established, not assumed.** Inability to establish it is a
stop — the default is *do not upload*, never *upload absent evidence of a problem*.

### 4.1 Control sequence (execute strictly in order)

| # | Step | Gate to proceed |
|---|------|-----------------|
| 1 | Read **only** the named 1,167-byte file through SSM | Path exactly as §1; no other file read |
| 2 | Verify the host-side SHA-256 against the expected value | `== 79011ea4…` |
| 3 | Verify the retrieved local copy has the **identical** SHA-256 | host hash `==` local hash `==` `79011ea4…` |
| 4 | Inspect the retrieved file locally for prohibited secret material | **PASS** = non-secret positively established |
| 5 | **Only after PASS**, upload from the laptop identity to the designated versioned evidence prefix | — |
| 6 | Read back the stored object, verify its hash, record bucket/key/**`VersionId`** | round-trip `== 79011ea4…` |

Expected content is a Stage-C evidence record: account number `PA3E97RWHKQZ`, position/order counts,
equity/cash figures, dispatch counts, timestamps. **Credential material lives in a separate file
governed by §8 and is out of scope of this authorization** — it is neither read nor transported.

### 4.2 Transient local copy

The laptop copy is **transient working material**. It is **removed after successful round-trip
verification**. This authorization does **not** authorize retaining it.

---

## 5. Stop conditions

Execution stops, records the reason, and changes nothing further when:

| Condition | Action |
|-----------|--------|
| **Size mismatch** — file is not exactly **1,167 bytes** | **STOP — no S3 upload** |
| **Hash mismatch** — any of host / local / round-trip ≠ `79011ea4…`, or host ≠ local | **STOP — no S3 upload** |
| **Unexpected file, path, or content** — anything other than the named artifact at the named path with Stage-C-shaped content | **STOP — no S3 upload** |
| Source-file sha256 ≠ `79011ea4…` at read | **STOP** — do not upload; the artifact's integrity is the finding |
| Base64 output appears truncated | **STOP** |
| §4 inspection cannot **positively establish** non-secret status | **STOP** — do not upload |
| Decoded content contains any credential, secret, token, or private key (§4) | **STOP** — do not upload |
| Round-trip sha256 after upload ≠ `79011ea4…` | **STOP** — do **not** delete the object; record the failed version and return to the owner |
| Completion would require an IAM change, tag change, or CFN update | **STOP** (§2.2) |
| Window closed (§3) | **STOP** |

A stop under any condition is a **complete outcome**, not a partial failure to be worked around.

---

## 6. Explicitly not authorized

| Item | Status |
|------|--------|
| #610 `ADR0043-WSS-DATA-SUBSTRATE-001` invocation, in whole or in part | **Not authorized — lapses uninvoked** |
| Any expedited or compressed substrate variant | **Not authorized** |
| Trading activation, broker orders, activation manifest, scheduler | **Separately gated — not authorized** |
| Extension of any resource, authorization, or clock | **Not authorized** |
| Early teardown of instance, volume, SG, or stacks | **Not authorized** |
| Preserving anything beyond the single file in §1 | **Not authorized** |

Completing this authorization yields **one durable copy of one existing file**. It does not change
WSS status, which remains **DEFER / CLEAN LAPSE**.

---

## 7. Deliverable

A preservation record containing: source path · both computed sha256 values · S3 key · **`VersionId`**
· execution timestamp · stop-condition outcomes (all `NOT_TRIGGERED` on success). Recorded in the WSS
memory entry; landed as a repo document only if the owner directs.

---

## 8. Signature block

| Field | Value |
|-------|-------|
| Approving role | Owner |
| Decision | ☑ **APPROVED / EFFECTIVE** — subject to the §4 clarification (controlling) |
| Sign-off | Owner acknowledgment (Jay Wang) — typed governance acknowledgment, 2026-08-14 |
| Effective date (UTC) | 2026-08-14 |
| Publication order | Owner directed **execute first, land the ADR + execution record afterward** as the permanent governance record — process latency was judged not to improve safety within a deliberately short window |

### 8.1 Owner's closing constraint (verbatim)

> Most importantly, this should remain exactly what it claims to be: preserve the Stage-C evidence
> and stop. It should not be treated as authority to resume WSS, provision a substrate, change IAM,
> invoke the successor authorization, or extend any expired/lapsing authorization.

---

## 9. Execution record — **EXECUTED / COMPLETE, 2026-08-14**

Executed under §4 as clarified. All six control-sequence steps passed in order.

| # | Step | Result |
|---|------|--------|
| 1 | Read named file via SSM | `SIZE=1167` · `MODE=600 root:root` · `MTIME=2026-08-04 15:20:21 UTC` · base64 1,556 chars = ⌈1167/3⌉×4 exact · output terminated on `END_B64`, **not truncated** |
| 2 | Host-side SHA-256 | `79011ea4…` — **PASS** |
| 3 | Local copy SHA-256 identical | host `==` local `==` expected — **PASS** |
| 4 | Local inspection for prohibited material | **PASS** — see §9.1 |
| 5 | Upload from laptop identity (`user/admin`) | `VersionId` below; key did not previously exist (no overwrite) |
| 6 | Read back **by VersionId**, verify, record | round-trip `79011ea4…`, 1167 B — **PASS** |

### 9.1 Inspection finding (§4 step 4)

Parsed as JSON, 26 top-level keys, `schema_version = adr0043-ws5-stage-c/1.0`. Automated scan for PEM
private keys, Alpaca key IDs, AWS access keys, bearer/JWT tokens, and secret-like field names returned
**zero hits**. Three high-entropy strings matched and were each identified as an **already-published
hash**: `artifact_sha256 987bd76f…`, image digest `c0c1b0c4…`, source commit `1880fcdb…`.

**Adjudicated judgment call:** the record carries `credential_key_fingerprint = ffab8796516a` and
`credential_secret_fingerprint = c2cab6509f1b`. These are **not credentials** — 12-hex-char (48-bit)
truncations of SHA-256, non-reversible. They exist because the B4 design verified credential identity
*without the secret ever travelling*, so their presence is affirmative evidence the secret was never
written to this record. Destination is same-account, private, encrypted, all-public-access-blocked.
Non-secret status **positively established**; upload authorized.

### 9.2 Preservation identities (immutable)

```
bucket      adr0043-ws5-evidence-219024422756-us-east-1
key         stage-c/stage_c_20260804T152020Z.json
VersionId   zsfg8QPAWz0lVu3ldKWF3n6OCvifd6yA
sha256      79011ea493cf0392dfa97b76ccb4f99e23623aa666672d9d8b82876acc647463
size        1167 bytes · SSE AES256 · ETag "967aacae35987eee311bc0d15c79b244"
S3 ChecksumSHA256  eQEepJPPA5LfqXt2zLT5niNiOqZmZy2di4KHasxkdGM=
  → base64-decodes to 79011ea4…, an independent AWS-computed confirmation of the same digest
executed_at 2026-08-14 · executing identity arn:aws:iam::219024422756:user/admin
```

### 9.3 Post-conditions verified

| Assertion | Evidence |
|-----------|----------|
| Source file unmodified and in place | `1167 600 root:root 2026-08-04 15:20:21.572109292 +0000`, sha256 `79011ea4…` — **byte-identical, mtime unchanged** |
| Evidence directory unchanged | 1 file, as before |
| No container activity | `docker ps -aq` = 1 (the pre-existing Exited(0) Stage-C container) — unchanged |
| No new S3 capability on WS5 | Instance role untouched; transport ran outbound via SSM to the laptop identity (§2.2) |
| No IAM / tag / CFN change | None attempted |
| Transient local copies removed | §4.2 discharged — decoded file, round-trip file, raw SSM output, and scan output all deleted |
| Stop conditions | **all NOT_TRIGGERED** |

### 9.4 Residual disclosure

The retrieved bytes also persist in **SSM command-invocation history for ~30 days** as an artifact of
the transport. This is the control-plane channel §4 expressly characterises as inspection/transport
rather than publication, and it ages out on its own. Recorded here so it is not later discovered as a
surprise. No action proposed.

### 9.5 Scope discharged

This authorization is now **spent**. WSS status is **unchanged: DEFER / CLEAN LAPSE**. The #610
substrate authorization remains uninvoked and lapses 2026-08-18T21:41:00Z. Nothing here constitutes
authority to resume WSS, provision a substrate, change IAM, invoke the successor authorization, or
extend any lapsing authorization.

---

## 10. Terminal disposition

| Field | Value |
|-------|-------|
| This authorization | **SPENT** — executed and complete, 2026-08-14 |
| **WSS** | **DEFER / CLEAN LAPSE** — unchanged |
| #610 `ADR0043-WSS-DATA-SUBSTRATE-001` | **Remains uninvoked; lapses 2026-08-18T21:41:00Z** |
| `ADR0043-WSS-TRADING-ACTIVATION-001` | Does not exist; separately gated |
| Remaining work under this ruling | **None.** Governance/documentation only |

*End of ADR0043-WSS-EVIDENCE-PRESERVATION-001 (SPENT — executed 2026-08-14, §4 as clarified).*
