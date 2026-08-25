# MDQ-001 — Capture Recovery Record, 2026-08-25

**Program:** MDQ-001 (Market Data Quality, Phase A — paired IEX/SIP quote capture)
**Record type:** Operational recovery and evidence-continuity record
**Status:** Final
**Author:** Jay Wang (GlobalComplyAI, LLC)

---

## 1. Disposition

> **2026-08-25 — RECOVERY CAPTURE / GOVERNED PARTITION COMPLETE.**
> The 08-23 runtime-environment loss was repaired by **restoration of the existing registered
> acquisition credentials**, not by rotation or re-pinning. Producer/account identity remained
> **continuous across the recovery boundary**. **2026-08-24 remains a permanent non-event and
> contributes zero evidence.**

2026-08-25 is **not** a replacement for, substitute for, or repair of 2026-08-24. It is an
independent trading day that produced its own governed partition.

---

## 2. Scope, and why this is a separate record

This record documents **operational execution evidence**. It is deliberately **not** a Program-Start
Record §6 amendment.

Amendment A (2026-08-24, merged in PR #672) had a deliberately narrow purpose: to append post-start
findings to §6 without reopening K1–K6, D0, holdout definitions, Gate PX rulings, or producer
identity. 2026-08-25 alters **none** of those authorities. It establishes only that a previously
adjudicated failure was repaired without changing the registered acquisition identity, and that
governed acquisition resumed successfully.

Folding that into §6 would blur the boundary between **program-start findings / governing authority**
and **later operational execution evidence**. Those are kept separate.

### 2.1 What this record does not do

- It does not alter D0 (2026-08-19), K1–K6, the holdout definitions, Gate PX, or producer identity.
- It does not modify, reopen, or soften the 2026-08-24 disposition.
- It does not change any denominator, evidence window, or corpus-completeness claim.
- It does not address the DISC-001 holdout-honouring question, which remains open and separate.
- It does not place `mdq_run.sh` or the MDQ systemd units into versioned custody, which remains a
  separate owner-gated ops-governance item.

---

## 3. 2026-08-24 remains a permanent non-event

Recorded in `docs/design/MDQ-001_Capture_NonEvent_2026-08-24.md` (PR #679). Restated here only to fix
the boundary of the present record; the prior disposition is unchanged and untouched:

- **No backfill**, no reconstruction, no partial-sampler salvage, no credential substitution.
- **No denominator or evidence-window change.** The window is not extendable; the loss is permanent.
- **No retroactive evidence.** The date contributes zero MDQ evidence and no K-value may use it.
- Both 2026-08-24 partition directories were confirmed **absent** after every unit ran.

---

## 4. Recovery mechanism — config restoration, not key rotation

**Cause (previously adjudicated).** The 2026-08-23 deployment rewrote `/opt/workbench/.env` and
dropped the numbered acquisition credentials `ALPACA_PAPER_6_API_KEY` / `_API_SECRET`. Trading was
unaffected — broker adapters read the encrypted database; the MDQ collector is the only component that
deliberately reads environment variables.

**Repair, 2026-08-24T23:37Z.** The credential was already present on the host in the Fernet-encrypted
store (`user 7`, `alpaca_paper_key`), with fingerprint **`b56421a28128`** equal to the governed pin. It
was restored to `/opt/workbench/.env` through a transport in which the secret value passed from
container stdout to a host file by redirection, never entering a command body, command output, or any
transcript.

| Property | Before | After |
|---|---|---|
| `/opt/workbench/.env` size | 1,014 B | 1,135 B |
| Variable count | 21 | 23 |
| Mode / owner | 600 root:root | 600 root:root |
| Credential fingerprint in file | absent | `b56421a28128` |

Backup retained at `/opt/workbench/.env.pre-mdqcredrestore-20260824-233710Z`.

**Explicitly not done, and why it matters:**

- **No new Alpaca key pair.** The governed pin is over the key ID (`sha256(api_key_id)[:12]`). A new
  key would fail `verify_identity()` closed and force a governed re-pin of `identity.py` — one of the
  five approved collector blobs — splitting the corpus's `credential_fingerprint`.
- **No `identity.py` re-pin.** The five governed collector blobs were byte-identical before and after.
- **No account reset.** Account 7 is frozen under the transition protocol; a reset would have produced
  ghost positions and moved `account_number`.

**Container recreate, 2026-08-24T23:48:23Z.** A `docker compose up -d --no-deps backend` was required
because `docker compose stop` + `start` does not re-read `env_file` — an existing container's
environment is fixed at creation. New container `349e75043d49…`, **same image** `fc76c0ed7015…`,
healthy in 40 s.

---

## 5. Three-proof readiness chain

The governed readiness standard for the 2026-08-25 slot required three proofs, all observed:

| # | Proof | Time (ET / Z) | Result |
|---|---|---|---|
| 1 | Post-recreate five-gate preflight | 19:50:03 / 2026-08-24T23:50:03Z | **READY**, 5/5 |
| 2 | Near-slot five-gate preflight | 09:15:00 / 2026-08-25T13:15:00Z | **READY**, 5/5 |
| 3 | Natural timer start (no hand-start) | 09:25:02 / 2026-08-25T13:25:02Z | **`TriggeredBy=mdq-sample.timer`** |

Both preflights ran the governed control merged in PR #673
(`apps/backend/scripts/mdq_preflight_readiness.sh`, sha256
`2ad345b83aa3c81d3ab5041614e8e6b0d8c647f83affe1d126207ba497b902ba`), executed as an SSM command body —
no file placement, no image rebuild, no container recreate.

Near-slot gate results (2026-08-25T13:15:00Z):

| Gate | Result |
|---|---|
| 1 Universe pin | PASS — expected == actual `0c57bd71…f88d4`; holdout artifact present `7832ff38…7010` |
| 2 Credential presence | PASS — `ALPACA_PAPER_6_API_KEY` SET 26, `_API_SECRET` SET 44 (names/lengths only) |
| 3 Account-identity latch | PASS — resolved `b56421a28128`, live `/v2/account` → `PA3BGKRLH2AP` |
| 4 Free-space floor | PASS — avail 28,713,000,960 B against fail-iff ≤ 10,737,418,240 B |
| 5 Single-instance | PASS — 0 running sample collectors |

Gate 3 is the load-bearing one: it proves the restored credential is the **right key for the right
account**, end-to-end against the broker — not merely that a variable is populated. The absence of that
check is what allowed the 2026-08-24 loss to occur behind a green free-space guard.

The sampler was **not** hand-started at any point.

---

## 6. Acquisition result

`mdq-sample.service` — `Result=success`, `ExecMainStatus=0`,
**09:25:02 → 15:59:00 ET (13:25:02Z → 19:59:00Z)**.

- Slot grid: `09:25:00 ET -> 16:00:00 ET (exclusive), cadence 60s, expected_cycles=395`.
- Completion: **`sampled 395 cycle(s) x 50 symbols x 2 feeds (395/395 scheduled slots)`**.
- Execution-time identity verification by the collector itself, independent of both preflights:
  `acquisition identity verified: account PA3BGKRLH2AP, fp b56421a28128`.
- **Zero MDQ failure alerts** for the day. Both feeds — IEX and SIP — captured.

395/395 is a **completeness** result, not merely a zero exit: no scheduled slot was dropped across the
6 h 34 m session.

---

## 7. Evidence completion and custody

**`mdq-eod.service`** — `Result=success`, 16:30:00 → 16:30:04 ET (20:30:00Z → 20:30:04Z). Wrote
**16,338** IEX and **26,984** SIP 1-minute bar rows; re-verified acquisition identity at 16:30:02 ET.

**`mdq-freeze.service`** — `Result=success`, 16:45:02 → 16:45:08 ET (20:45:02Z → 20:45:08Z), executing
**freeze → verify → mirror** in order: `mdq_partition_frozen feed=iex|sip files=2` → `iex|sip/2026-08-25:
verified` → `mirrored /opt/workbench/data/mdq_capture -> s3://workbench-backups-219024422756/mdq_capture`.
(The `files=2` count is the two data files being manifested; the manifest itself is the third file.)

Final partition — **3 files per feed**, the expected shape:

| Object | Bytes | sha256 (manifest entry, verified on disk) |
|---|---|---|
| `iex/2026-08-25/bars/bars_1min.parquet` | 498,515 | `7ee77cf058344e4dc4c2af01dd0969de17d123709f7ccbbaea8c25685d3d8464` |
| `iex/2026-08-25/quotes/samples.jsonl` | 5,732,813 | `ec0bee48032892997eed360b0d128d543497dea24f66607abdc89d22a868f359` |
| `iex/2026-08-25/manifest.json` | 1,467 | — |
| `sip/2026-08-25/bars/bars_1min.parquet` | 932,581 | `560b83483f1ce9852e2e5a353392ba06ec600aed100a0008ab05df91ee331ddd` |
| `sip/2026-08-25/quotes/samples.jsonl` | 5,742,440 | `d495bc2a1e7e74fbfa1d22b1ab94344a1fc860bb821e63e7e302e160c10d207a` |
| `sip/2026-08-25/manifest.json` | 1,467 | — |

**S3 custody — independently verified**, not accepted from the box's own upload log. All six objects
are present under `s3://workbench-backups-219024422756/mdq_capture/{iex,sip}/2026-08-25/`. Verification
was performed as a chain:

1. **Manifest → disk.** Each manifest's recorded sha256 was recomputed on the host and matched.
2. **Disk → S3.** Each object's host MD5 **exactly matched the ETag returned by S3** for that object.
   This directly observed equality establishes host↔S3 content identity for these six objects. No
   generic claim is made that every single-part S3 ETag is necessarily an MD5.

⚠ Precision: `ChecksumSHA256` was null for all six objects, so **no S3-side SHA-256 verification was
available**; SHA-256 was verified **host-side against the manifests**.

Volume comparison against a known-good reference day (2026-08-21) — IEX 515,579 / 5,733,580 / 1,467 and
SIP 945,557 / 5,742,142 / 1,467 — places 2026-08-25 within 0.5 % on both feeds, consistent in shape and
volume with an established good day.

---

## 8. Load-bearing finding — no credential-identity seam was introduced

This is the governance-relevant result, and the reason this record exists. "Services returned exit 0"
is routine operations; **preserving corpus identity across a production credential-loss recovery is
not.**

Both 2026-08-25 manifests carry:

| Field | Value |
|---|---|
| `schema` | `mdq-capture-manifest/1` |
| `collector_version` | `mdq-collector/0.1.0` |
| `provider` | `alpaca` |
| `entitlement` | `algo_trader_plus (account-7 login)` |
| **`credential_fingerprint`** | **`b56421a28128`** |
| **`account_number`** | **`PA3BGKRLH2AP`** |
| `alpaca_py_version` | `0.44.0` |
| `capture_modes` | `["rest_quote_sampler_v1", "rest_eod_bars_v1"]` |
| `universe_sha256` | `a022e399e216f16328eaecd809126951f6658cb09351281fa02187a0a6faf563` (50 symbols) |

These are **identical in identity semantics to the 2026-08-19, 2026-08-20 and 2026-08-21 partitions**.
Because the repair restored the existing registered credential rather than rotating it, the
`credential_fingerprint` did not change across the recovery boundary.

⇒ **The corpus contains no credential-identity seam.** Any downstream analysis spanning 2026-08-19
through 2026-08-25 reads a single, continuous producer identity. Had the repair taken the rotation
path, this record would instead have had to declare a split in producer identity mid-corpus.

⚠ Note for future readers: `universe_sha256` is the hash of the symbol **list** inside the manifest. It
is a different object from the universe **pin-file** sha256 `0c57bd71…f88d4` checked by preflight
gate 1. Do not compare them.

---

## 9. Corpus state after this record

| Date | Feeds | Disposition |
|---|---|---|
| 2026-08-19 (D0) | IEX + SIP | Governed partition, frozen + verified + mirrored |
| 2026-08-20 | IEX + SIP | Governed partition, frozen + verified + mirrored |
| 2026-08-21 | IEX + SIP | Governed partition, frozen + verified + mirrored |
| 2026-08-18, 2026-08-24 | — | **Permanent non-events. Zero evidence. No backfill.** |
| 2026-08-25 | IEX + SIP | Governed partition, frozen + verified + mirrored |

**Corpus = 4 trading days.**

---

## 10. Operational note carried forward

`mdq-sample.service` is a `oneshot` unit that runs **until close** — approximately 6 h 34 m from the
09:25 ET timer start to the ~15:59 ET terminal, with `TimeoutStartSec=8h`. `ActiveState=activating` is
therefore the **expected** state for most of a healthy session and must not be read as a hung unit.

Liveness is judged by **governed byte growth, failure alerts, explicit failure signatures, and the
terminal timestamp** — never by `ActiveState` alone. The converse holds equally: `activating` is not
evidence of capture, and `mdq-freeze.service` exiting 0 means nothing on its own, as 2026-08-24
demonstrated when that same zero meant `no partitions for 2026-08-24; nothing to freeze`.

This is an operational interpretation rule. It weakens no failure gate and changes no admissibility
criterion.
