# SEC-001 V3 — Research Host: Pre-Acquisition Provenance Record v1.0

**Discharges:** the *record before the vendor pull* required by `SEC001_V3_GovernedStore_PreIngestionFreeze_v1_0.md` §5–§6.
**Recorded:** 2026-08-24, **before any SEP or TICKERS acquisition**.
**Coverage rule status:** `5b26ffa209a6…` (0.95 / 0.95 / 20 y) remains **UNSPENT**.

---

## 1. Host identity (empty state)

| Property | Value |
|---|---|
| Instance | `i-00e6b78fcabd32413` — fresh, provisioned solely for this build |
| AMI | `ami-02c4144237becae44` — `ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-arm64-server-20260714` |
| OS / kernel | Ubuntu 24.04.4 LTS · `6.17.0-1019-aws` · system Python 3.12.3 |
| Type / arch / AZ | `m7g.xlarge` · `aarch64` · `us-east-1c` |
| Root volume | `vol-0cf17223018c3a1c6` — 100 GB gp3, **encrypted** (`kms:…/febac2a9-602b-412b-9177-1cff029af2ab`) |
| Launched (UTC) | `2026-08-24T00:34:50Z` |
| Network | SG `sg-0bb8045e6adee2728` — **0 inbound rules**; egress restricted to **TCP 443 IPv4 only** (no IPv6 egress) |
| Access | SSM Session Manager only; no SSH key, no public ingress |
| Instance profile | `arn:aws:iam::219024422756:instance-profile/sec001-v3-research-role` |
| Assumed identity | `arn:aws:sts::219024422756:assumed-role/sec001-v3-research-role/i-00e6b78fcabd32413` |
| Stack | standalone `run-instances`. **No CloudFormation operation was performed** (2026-07-27 incident control). |

**Toolchain installed before acquisition:** AWS CLI `2.36.29`; venv at `/opt/sec001` with **duckdb 1.5.5**, pandas 3.0.5, pyarrow 25.0.1, requests 2.34.2.

*Note on egress:* Ubuntu's arm64 apt mirrors default to **port 80** and prefer IPv6. Rather than widen the security group, apt was repointed to `https://ports.ubuntu.com/ubuntu-ports/` with `Acquire::ForceIPv4`. The 443-only IPv4 egress posture was **preserved, not relaxed**.

## 2. IAM — exact effective policy

| Property | Value |
|---|---|
| Role | `arn:aws:iam::219024422756:role/sec001-v3-research-role` |
| Customer policy | `arn:aws:iam::219024422756:policy/sec001-v3-research-policy` v1 |
| Policy document SHA-256 | `d007cc18755cfebc16054afcafcbe62d9c142fff9407f34b755b149b3b8ef13d` |
| Also attached | `AmazonSSMManagedInstanceCore` (Session Manager transport only) |

Grants, in full: `ssm:GetParameter`/`GetParameters` on the **single exact ARN** `…:parameter/workbench/prod/NASDAQ_DATA_LINK_API_KEY`; `kms:Decrypt` on `…:key/6b654ce3-97df-4d9e-b8b0-64f7cf376973` **conditioned** on `kms:ViaService = ssm.us-east-1.amazonaws.com` **and** `kms:EncryptionContext:PARAMETER_ARN` equal to that parameter; object read/write under `build/*` and `raw/*`; `ListBucket` limited to those prefixes.

Explicit denies: every other SSM parameter (`NotResource`), `GetParametersByPath` entirely, all KMS outside that one key, Secrets Manager and `sts:AssumeRole`, the whole `sealed/*` prefix, and every retention/governance action — `PutObjectRetention`, `PutObjectLegalHold`, `BypassGovernanceRetention`, `PutBucketObjectLockConfiguration`, `PutBucketPolicy`, `PutBucketVersioning`, `PutBucketPublicAccessBlock`, `PutEncryptionConfiguration`, `DeleteObject`, `DeleteObjectVersion`, `PutObjectAcl`.

> **The builder can produce evidence; the builder cannot declare its own output immutable or qualified.** Promotion into `sealed/` and application of COMPLIANCE retention require a separate identity.

## 3. Isolation proof — by execution, fail-closed

`/workbench/prod/` holds **26 SecureString parameters**, of which **18 are live Alpaca broker credentials** and one is `WORKBENCH_MASTER_KEY`. A path-wildcard grant would have exposed all of them; the policy grants one exact ARN.

Run from the instance under its own role, 2026-08-24T00:41:26Z:

| Probe | Result |
|---|---|
| `ALPACA_PAPER_7_API_KEY` / `_API_SECRET` | **DENIED (explicit)** |
| `ALPACA_PAPER_API_KEY` | **DENIED (explicit)** |
| `ADR0043_CANARY_ALPACA_API_KEY` | **DENIED (explicit)** |
| `WORKBENCH_MASTER_KEY` | **DENIED (explicit)** |
| `ANTHROPIC_API_KEY` | **DENIED (explicit)** |
| `GetParametersByPath /workbench/prod` | **DENIED (explicit)** |
| `NASDAQ_DATA_LINK_API_KEY` | **OK** — decrypted, len 20, `sha256=753417c970e0d65d…` (**value never printed or logged**) |
| write to `build/` | OK |
| write to `sealed/` | **DENIED** |
| apply COMPLIANCE retention | **DENIED** |
| `import alpaca` | `ModuleNotFoundError` — no broker SDK present (ADR 0051) |

> ⚠ **The first isolation run was invalid and is recorded rather than discarded.** The AWS CLI was not yet installed, so every probe returned `aws: not found`; the probe classified "no `AccessDenied` string" as *readable* and reported six false isolation failures. It **failed open** — the same defect class this codebase has repeatedly paid for. The probe was rewritten so that **both** verdicts require positive evidence (`AccessDeniedException` for denial, a parseable `"Value"`/`"Type": "SecureString"` for success) and anything else reports `INDETERMINATE`. The corroborating detail: the bogus run reported the vendor key as `len=168` (the length of the error text); the valid run reports `len=20`.

## 4. Source identity — selected before acquisition

| Property | Value |
|---|---|
| Ingestion commit | **`992e45401404ef46fcd64130a39bf915893e682e`** — `fix(scan-001): admit only same-day, contrast-bearing forward evidence (#511)` |
| Selection | `origin/main` was re-fetched immediately before archiving, per the pre-ingestion rule. It had **advanced** from the previously observed `a992a9e` (an older PR merged late at 17:46 CDT). Current HEAD was taken. |
| Verification | `a992a9e` **is** an ancestor of `992e454` — main advanced normally, no rewrite. `git diff --name-only a992a9e 992e454 -- apps/backend/app/factor_data/ apps/backend/scripts/ingest_sharadar.py` is **empty**: the ingestion path is byte-identical between the two commits, so the selection is inert with respect to this build. |
| Source archive | `git archive` of that commit — content from **Git blobs**, not the Windows working tree, so the hash is LF-stable and immune to the CRLF fail-close trap |
| Archive size / SHA-256 | 6,372,992 B · **`e5be0ffcd149f3c1960bc0f31f9643fee8aae03812c95356fa34890ce738b313`** |
| Archive location | `s3://workbench-sec001-v3-research-219024422756/build/source/repo-992e454.tar.gz` @ VersionId **`wuCKCZfQNWJ7aV6hI0.PI8XWPh2fudkx`** |
| Acquisition/ingest code | `apps/backend/scripts/ingest_sharadar.py` SHA-256 `ce97658e7f55d0792ea04f83297793c9db1f8df64e2ab9ff71f8073a25c64156` |
| Store implementation | `apps/backend/app/factor_data/store.py` SHA-256 `9b2e32ed4c48a9c775b992e9de25c1a4460284119d51469438dc26f6888de8a9` |

**No GitHub credential exists on the host.** Source arrives only as this SHA-pinned archive.

## 5. Storage configuration

| Property | Value |
|---|---|
| Bucket | `workbench-sec001-v3-research-219024422756` (us-east-1) |
| Versioning | Enabled |
| Object Lock | **Enabled (capability), `Rule: None` — no default retention** |
| Public access block | all four: true |
| Encryption | AES256, bucket key enabled |
| `build/`, `raw/` | builder-writable, no retention |
| `sealed/` | builder **denied entirely**; qualified artifacts promoted here by a separate identity, with COMPLIANCE retention applied at sealing |
| Target store path (empty) | `/opt/sec001-data/factor_data_sec001v3.duckdb` — does not yet exist |

## 6. State at this record

Acquisition has **not** begun. No SEP or TICKERS data has been pulled, no store created, no reconciliation run, no PIT-200 derived. The EDGAR crawl remains blocked until a qualified store yields a sealed union artifact. The Monday 2026-08-24 09:25 ET MDQ free-space obligation is untouched by this work and is **not** satisfied or modified by anything recorded here.
