# SEC-001 V3 — Defect F Snapshot Custody Record v1.0

## FAILED EPOCH v1.4 — PRESERVATION CUSTODY CLOSED

**Status:** Custody step 1 of the owner's 2026-08-25 post-snapshot authorization. Recorded before
any investigation action. Deliberately kept **separate** from
`SEC001_V3_AcquisitionDefect_F_IgnoredRangeUnboundedRetention_v1_0.md`, which remains untouched and
uncommitted pending storage forensics.

All times given in **US Central (CDT, UTC−5)** with the UTC Z value alongside. Sealed Z values are
not rewritten.

---

## 1. Custody snapshot — `completed`

| field | value |
|---|---|
| snapshot | `snap-01a33687b1588626b` |
| state | **`completed`**, progress **100%** |
| source volume | `vol-0cf17223018c3a1c6` |
| volume size | 100 GiB |
| encrypted | **true** |
| KMS key | `arn:aws:kms:us-east-1:219024422756:key/febac2a9-602b-412b-9177-1cff029af2ab` |
| owner account | `219024422756` |
| storage tier | **`standard`** — not archived, per the `ArchiveTier=FORBIDDEN` tag |
| region | `us-east-1` |

### Timestamps

| event | US Central | UTC |
|---|---|---|
| snapshot started | 2026-08-25 **08:25:31 AM CDT** | `2026-08-25T13:25:31.052Z` |
| last `pending` observation (91%) | 2026-08-25 **09:55:00 AM CDT** | `2026-08-25T14:55:00Z` |
| observed `completed` | 2026-08-25 **10:01:07 AM CDT** | `2026-08-25T15:01:07Z` |

> ⚠ **`CompletionTime` is not populated by the EC2 API for this snapshot** — the field returned
> `null`. The completion instant is therefore recorded as a **bounded observation**, not an API
> fact: completion occurred between `14:55:00Z` (91% observed) and `15:01:07Z` (waiter returned).
> Elapsed duration ≈ **1 h 36 min**. This bound is derived from the polling log, and is stated as a
> bound deliberately rather than promoted to a precise timestamp.

### Tags (10, intact)

```
Name         sec001-v3-defectF-halted-epoch-v1.4
Program      SEC-001-V3
Purpose      evidence-custody-failed-epoch
Epoch        v1.4-bulk-crawl
Defect       F-ignored-range-unbounded-acquisition
HaltUTC      2026-08-25T04-15-31Z
TerminalUnits 374-of-1167
Disposition  PRESERVE-DO-NOT-DELETE
ArchiveTier  FORBIDDEN
Plane        research-no-broker-capability
```

---

## 2. Original instance — confirmed still stopped

| field | value |
|---|---|
| instance | `i-00e6b78fcabd32413` (`sec001-v3-research-build`, m7g.xlarge, us-east-1c) |
| state | **`stopped`** |
| transition reason | `User initiated (2026-08-25 13:24:38 GMT)` = **08:24:38 AM CDT** |
| plane | `research-no-broker-capability` |

Not terminated. Not restarted at any point since the halt.

---

## 3. Original volume — confirmed unchanged

| field | value |
|---|---|
| volume | `vol-0cf17223018c3a1c6` |
| state | `in-use`, `attached` to `i-00e6b78fcabd32413` |
| size / type / AZ | 100 GiB · gp3 · `us-east-1c` |
| encrypted | true |
| created | `2026-08-24T00:34:51.070Z` = 2026-08-23 **07:34:51 PM CDT** |
| `DeleteOnTermination` | **`false`** — cleared 2026-08-25 08:24 AM CDT as a mechanical preservation control |

The volume remains attached to the stopped instance in its failure state: 100% full,
892,928 bytes free, zero-byte `RUNNER_STOPPED.json`, torn final line in
`source_decision_bytes.jsonl`. **No mount, no fsck, no write, no reclaim has been performed
against it.**

---

## 4. Custody assertion

> The failed v1.4 filesystem is preserved in two independent places: the **original volume**
> `vol-0cf17223018c3a1c6`, still attached to a stopped instance with termination-deletion disabled;
> and the **completed snapshot** `snap-01a33687b1588626b`, encrypted, standard tier, tagged
> `PRESERVE-DO-NOT-DELETE`.
>
> All subsequent investigation is to be performed on a **temporary volume restored from the
> snapshot**, attached to a **separate investigation host**, mounted **read-only with no recovery
> writes**. The original volume is not an investigation target.

---

## 5. Program state at custody close

```
v1.4 crawl        HALTED at 374/1,167
successor credit  0
coverage          NOT EVALUATED
economics         NOT EVALUATED
5b26ffa2...       UNSPENT
Defect-F ruling   413 lines, UNTRACKED, UNCOMMITTED, unmodified since 2026-08-25
Defect G          candidate, unverified
```

Next authorized step: restore a temporary investigation volume from the snapshot, attach to a
separate host, mount read-only/no-recovery, and perform **acquisition/storage forensics only**.
