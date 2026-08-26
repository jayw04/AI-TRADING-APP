# SEC-001 V3 — Successor Epoch Identity (Gate 6) v1.0

## `SUCCESSOR_EPOCH_0_1167` — EXECUTION PACKAGE SEALED

Sealed **before request #1**, per Gate 6. All six prestart gates PASS. On sealing, the successor
token `5b26ffa2…` transitions **UNSPENT → CONSUMED** and the crawl starts at **0/1,167**.

The v1.4 374 never enter this count.

---

## 1. Execution package

| component | identity |
|---|---|
| transport implementation | `66247ad17f0e38a5f6c67ac11d74891b0e45fd3e` |
| runner commit | `69be56e663f0d2d9b259edf5c8e4f9d64ee70d04` |
| runner file sha256 | `337a0472cac53f1f3cdea439eee94a4e241307f1afb71259a44c115822db1958` |
| frozen identity order | `e8445b0b6ea08bf1ff5ad5a08db6cc3797f5161fb53be3a0aed4b9b24c8f9c35` |
| CIK source artifact | `SEC001_V3_CIK_RESOLUTION_V1.json` — `1f7d523b9419301a16d36234f19584266f3e61fc4e5673e589d0ba7016877146` |
| population | **1,167** identities |
| host | `i-0407ca119eb85cdb1` (m7g.large, us-east-1c, research plane, no broker capability) |
| epoch volume | `vol-0c55ac93dc1736a80` — 250 GiB gp3, encrypted, `DeleteOnTermination=false` |

### Protected blobs — reasserted once against the final package

```
PASS  sec/client.py               6c1d7006f42f      <- binding invariant
PASS  sec001_v3/spine.py          3f37faba3861      <- frozen MR-002 spine
PASS  mr002/sic_history.py        48779adaaaec      <- frozen, also asserted at runtime
PASS  sections.py ae97502b1c9a · forbidden.py 8570677325aa · __init__.py a50bc6c76896
PASS  decision_bytes.py 06de91a92acc · evidence.py cdd61346212c
PASS  driver.py c6f147eda499 · state.py 0d23793590d8
CHANGED (authorized)  fetch.py 62646f2d2190 · policy.py 53d21a15ac62
```

The runner is a **new file** (`apps/backend/scripts/sec001_v3/successor_runner.py`) and modifies no
protected code, so **no further Defect-F canary is required**.

### Dependencies

```
httpx 0.28.1 · httpcore 1.0.9 · duckdb (transitive: spine -> sec.ingest -> events.store)
HTTP11Connection.READ_NUM_BYTES = 65,536
httpcore/_sync/http11.py sha256 f644ff92a0a10822544c7c30db866647f7b371d6e94585a4b03fa060dce464ff
```

### Acquisition configuration

```
FORMS        10-K, 10-K/A, 10-Q, 10-Q/A, 20-F, 20-F/A, 40-F, 40-F/A
CRAWL_SINCE  2000-01-01
RESPONSE_CONSUMPTION_CEILING_BYTES   1,048,576
CONSUMPTION_STOP_THRESHOLD_BYTES       983,040
MAX_UPSTREAM_CHUNK_BYTES                65,536
rate limit   5.0 req/s policy (SEC ceiling 10)
```

---

## 2. Gate results

| gate | result |
|---|---|
| **1** code + dependency identity | **PASS** — 12/12 blobs on host vs `66247ad`; dependency gate PASS; canary re-proven (`154c31a`) |
| **2** 20-F/40-F extension | **PASS** — proven at runtime by importing the modules: `policy.FORMS` ⊇ required set, driver passes `forms=policy.FORMS`, frozen spine unchanged |
| **3** clean epoch storage | **PASS** — `blkid` showed no filesystem before `mkfs`: a virgin volume, zero entries, no investigation artifacts |
| **4** capacity | **PASS** — 232.5 GiB usable vs **101.19 GiB** deterministic ceiling (2.3×) |
| **5** evidence-preservation reserve | **PASS** — implementation, unit proof, and controlled-stop E2E |
| **6** epoch identity sealed | **this record** |

### Capacity — two distinct concepts, not to be conflated

**Deterministic capacity proof (the launch gate):** 97,519 projected artifacts × 1 MiB =
**95.23 GiB**; allowing one 64 KiB upstream-chunk overshoot per artifact ⇒ **~101.19 GiB**.

**Expected-use scenarios (planning only):** heterogeneous model — 21,312 measured small artifacts
retain their observed ~4.2 GB contribution, only the 9,941 Defect-F-sensitive large artifacts are
replaced with bounded assumptions, manifest/observation overhead scaled alongside ⇒
**~12.8–20 GiB**. These are *not* the capacity guarantee and must never be cited as one.

### Gate 5 — the reserve, accurately described

```
TERMINAL_RESERVE_BYTES             2,147,483,648   physically preallocated (fallocate)
MAX_NEXT_ARTIFACT_FOOTPRINT            1,114,112   ceiling + one max chunk
METADATA_ALLOWANCE_BYTES               1,048,576
PREARTIFACT_FREE_REQUIRED_BYTES    2,149,646,336   asserted before EVERY artifact
```

Because the 2 GiB file is already allocated, ordinary `free` excludes it. The guard therefore
preserves **a physical 2 GiB emergency reserve PLUS ~2.15 GiB of ordinary operating headroom
(~4.15 GiB total)** — not the same 2 GiB counted twice.

**Controlled-stop E2E, one run, governed threshold forced while the disk was healthy:**

```
free at trip     247,353,016,320   (247 GB free — the RULE tripped, not the disk)
required         258,090,520,576
exit code        3                 (controlled TERMINAL_STORAGE_RESERVE stop)
stop record      587 bytes, parseable, controlled_stop true
reserve          released 2,147,483,648 B -> free 249,500,499,968
units credited   0        artifacts written 0        temp files left 0
```

⚠ **3 HTTP requests were recorded** — `get_json` submissions-index fetches, which precede the
artifact path. The guard governs artifact acquisition, so **zero artifacts started**. Recorded
precisely rather than as "no network activity."

---

## 3. Frozen identity order — recovered, not regenerated

Priority order was followed: repo custody held only hashes, so the artifacts were extracted
**read-only** from the preserved snapshot `snap-01a33687b1588626b`.

```
SEC001_V3_CIK_RESOLUTION_V1.json  1f7d523b9419…  == manifest v1.4 cik_resolution_sha256
pit200_union.json                 d338e65f9ece…  == manifest v1.4 population_union_sha256
v1.4 controller crawl_full.py     894e4744…      == EXECUTION_SEGMENTS segment-3 controller
```

The controller gave the exact construction, which the manifest's prose did not:

```python
sorted({WorkUnit(cik=int(r["cik"]),
                 ticker=str(r["tickers_source_row"]["ticker"]).upper(),
                 permaticker=int(r["permaticker"]))
        for r in art["identities"] if r["status"] == "RESOLVED_CIK"})
```

**Order identity proven against execution history, not asserted:**

```
PREFIX_IDENTICAL_TO_V1_4_EXECUTION   True   (all 374 executed units, in order)
#1->#2   0000001800:ABT  -> 0000002135:ACS      matches EXECUTION_SEGMENTS
#5->#6   0000002969:APD  -> 0000003333:ABS      matches
#8->#9   0000004127:SWKS -> 0000004281:HWM      matches
derived[373] == last executed  0000833320:BR1
```

> Two earlier derivations were **wrong**: sorting by `(cik, ticker)` from the manifest's prose used
> a degenerate key (the field is `tickers`, plural), and `load_work_units` rejects the union because
> it carries no CIKs. With 1,146 unique CIKs across 1,167 identities, 21 CIKs would have been left
> in undetermined order. The prefix check against real execution is what caught it.

The runner re-derives this order at startup and asserts it equals the sealed
`e8445b0b…` before any request.

---

## 4. Credit semantics and stop discipline

```
0/1,167 -> 1/1,167 -> ... -> 1,167/1,167
```

The old 374 **never** enter this count. Unit-boundary credit only: an interrupted unit restarts from
its governed unit boundary; no partial-unit credit is invented.

Completion is **conjunctive**: `count == 1167` **AND** unique **AND** equal to the frozen order.

⛔ If a new material acquisition defect appears, **do not improvise a repair mid-crawl and keep
counting.** Stop, adjudicate whether the epoch remains conforming, then decide continuation vs
another successor.

The crawl runs to completion without intermediate review unless: the Gate-5 reserve trips; a new
material acquisition defect appears; manifest/order integrity fails; or protected/runtime identity
changes.

---

## 5. What completion does NOT unblock

```
successor completes -> governed WEEKLY-GRID coverage measured -> source/taxonomy/coverage freeze
finalized -> §9.4 becomes servable -> only THEN V3-RC executes
```

That is where the first real economic evidence begins. ⚠ **Weekly** grid: §5.1b's 798-name floor was
an *annual* grid; the weekly rebalance grid exceeds it.

---

## 6. Successor token

```
5b26ffa2...   UNSPENT -> CONSUMED at the sealing of this record
```
