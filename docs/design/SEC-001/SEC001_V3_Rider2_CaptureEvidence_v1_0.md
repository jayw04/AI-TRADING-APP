# SEC-001 V3 — Rider Item 2: Governed Capture Evidence v1.0

**Discharges:** the *capture* half of rider item 2 of `SEC001_V3_SectorClassification_Disposition_Ruling_v1_0.md`.
**Ordering evidence:** the pre-crawl coverage freeze was sealed at commit **`5b26ffa209a6a13a599a99fb28268b46be569cd2`** *before* this capture ran and before any coverage result was inspected.
**Date:** 2026-08-23 · **Method:** owner-ruled zero-downtime capture (no stop, no restart, no timer change)

> **Status: capture COMPLETE and verified. Measurement BLOCKED — see §4.** The captured artifact is sound and sealed; it is not *sufficient* to perform the rider-2 coverage measurement, for a reason discovered only by inspecting it.

---

## 1. Method ruling

The originally prescribed sequence stopped the container holding the DuckDB connection to guarantee no competing process. The pre-capture census showed that guarantee was obtainable *directly*: one physical file, no WAL, no writer handle, unchanged for two days, next known writer ~10 h away. The owner therefore ruled: **no stop, no restart, no timer change** — capture live and *prove* non-mutation by SHA equality across the capture, which is stronger evidence than assumed quiescence and leaves the live runtime untouched.

## 2. Pre-capture census (read-only, via SSM)

| Property | Value |
|---|---|
| Host | `i-084f47fe4e69192e9` / `ip-172-31-7-230` (`workbench-paper`) |
| Deployed source SHA | `0344337787a6ce27df64995f7a556b19a4bf297a` |
| Source pathname | `/opt/workbench/data/factor_data.duckdb` (`/opt/workbench/app/data` is a **symlink** to `/opt/workbench/data` — one physical file) |
| Inode | `1077418` |
| Size | 45,887,488 bytes |
| Source mtime | 2026-08-21 06:08:03.667081329 −0400 (unchanged for 2 days at capture) |
| WAL | **absent** — no `*.duckdb.wal` anywhere under `/opt/workbench` |
| Handle census | `uvicorn` PID 2575253 only, FD `21rR` — **read-only with a read lock**; **zero** handles in `w`/`u` mode, re-verified immediately before upload |
| Next writer event | `workbench-factor-refresh.timer` → Mon 2026-08-24 06:00:00 EDT (last run Fri 2026-08-21; weekday-only) |
| Free space | 27 G available, 53% used |
| Backend state | `workbench-backend` Up 3 h (healthy) — **not stopped, not restarted at any point** |

## 3. Capture and three-way SHA verification

| Property | Value |
|---|---|
| Capture window (UTC) | t0 `2026-08-23T23:25:09Z` → t1 `2026-08-23T23:25:11Z` |
| Bucket | `workbench-evidence-incidents-219024422756` |
| Key | `sec001/v3/rider2-capture/2026-08-23/factor_data.duckdb` |
| **Version ID** | **`esQHtLrTQ2g_66R6mxKXX1UZ6KwZW0xo`** |
| Object size | 45,887,488 bytes (identical to source) |
| Object Lock | **COMPLIANCE**, retain-until **2033-08-21T23:25:11.259Z** |
| Encryption | AES256 |
| Transfer | `aws s3 cp` streamed **from the source path directly**; no `/tmp` copy, no second local DB, exit 0 |

**Required equality — satisfied:**

| Measurement | SHA-256 |
|---|---|
| Source, before upload | `d1a07107b5ba9da3e7a2ee2222e35d04d544557e876351735c09e76901b81b2b` |
| Source, immediately after upload | `d1a07107b5ba9da3e7a2ee2222e35d04d544557e876351735c09e76901b81b2b` |
| **Downloaded object, independently re-hashed off-box** | `d1a07107b5ba9da3e7a2ee2222e35d04d544557e876351735c09e76901b81b2b` |

**All three equal.** Source inode, size and mtime were also identical before and after. The object was retrieved **by version ID**, not by key alone. The S3 ETag (`6c595fdd…-6`) is multipart and was **not** used as content proof, per the ruling.

**Input identity for any downstream use:** `sec001/v3/rider2-capture/2026-08-23/factor_data.duckdb` @ VersionId `esQHtLrTQ2g_66R6mxKXX1UZ6KwZW0xo`, SHA-256 `d1a07107…b1b2b`.

## 4. ⛔ Measurement blocked — the governed store cannot reconstruct the historical PIT-200

Inspection of the verified capture (coverage-only; no economic metric computed) shows the production store holds **692,600 SEP rows over 1,254 names**, and its history is **four names** — `AAPL`, `KO`, `MSFT`, `NVDA` (plus `CBNJ2`) — for **every year from 1997 through 2023**. Real cross-sectional breadth begins in **2024** (1,227 names).

It is a *production operating* store: enough history to compute 252/21 momentum on the current universe, and nothing more. **A PIT-200 cannot be built from it for any date before 2024**, so the rider-2 coverage table cannot be measured against it.

A read-only census of every other candidate on the box gives the same answer:

| Artifact | names in 2000 | names in 2008 | `permaticker` |
|---|---:|---:|---|
| `factor_data.duckdb` (governed, captured) | 4 | 4 | ✅ 21,988 non-null |
| `factor_data.prev.duckdb` | 4 | 4 | ✅ 21,988 |
| `factor_data.deepen.duckdb` (13.7 M rows, 10,492 names) | 4 | 4 | ❌ |
| `factor_data.research.duckdb` | 4 | 4 | ❌ |
| **laptop `factor_data_full.refresh.duckdb`** (39.2 M rows) | **4,699** | **6,311** | ❌ |

**The interlock:** the only artifact with the historical cross-section is the ungoverned laptop research store, and it has **no `permaticker` column** — so clause 1 (identity) of the §5.1b/freeze four-clause definition is unevaluable on it. The artifact that *has* identity has no history; the artifact that *has* history has no identity. **No existing artifact can satisfy the measurement definition**, and no substitution was made.

This is wider than rider item 2: §5.1 requires the V3 validation itself to run on the PIT-200 across the frozen evaluation period, and that universe is presently reconstructible **only** from an ungoverned laptop file. Resolving it is an owner decision, recorded before any measurement proceeds.

## 5. What was and was not done

- ✅ Capture executed, verified three ways, sealed under Object Lock.
- ✅ Coverage-only inspection of the capture — row counts, name counts, column presence. **No** return, Sharpe, CAGR, drawdown, V2/V3 comparison, or Factor Lab execution.
- ⛔ The rider-2 coverage table was **not** produced, because the definition cannot be evaluated on any available artifact.
- ⛔ No EDGAR crawl. No MR-002 modification. No backend stop, restart, or timer change. Strategy 7 remains IDLE.
- ⛔ The §3 decision rule of the coverage freeze remains **unapplied** — it is applied once, after the crawl, and nothing here consumes it.
