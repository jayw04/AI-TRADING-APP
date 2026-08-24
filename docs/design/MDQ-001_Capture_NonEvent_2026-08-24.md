# MDQ-001 — 2026-08-24 CAPTURE NON-EVENT / NO GOVERNED PARTITION

| Field | Value |
|---|---|
| Session date | **2026-08-24** (Monday) |
| Disposition | **CAPTURE NON-EVENT — no governed partition exists.** |
| Evidence contribution | **ZERO.** The date contributes no MDQ evidence and **no K-value may use it.** |
| Ruled by | Platform owner, 2026-08-24 |
| Precedent | Same evidence disposition as **2026-08-18**, when no governed partition existed |
| Status | **COMPLETE — CLOSED.** All three completion facts observed 2026-08-24 16:47 ET. |
| Root cause classification | **Runtime acquisition-environment loss after redeploy.** Explicitly **not** disk exhaustion, **not** collector-code drift, **not** universe-pin failure, **not** a data-quality failure. |
| Governance stance | **Recording instrument.** It changes no criterion, threshold, tolerance, denominator, or evaluability clause, and does not alter D0, the holdouts, or the review window. |

> **Why this record exists rather than a directory.** No sampler bytes were written. The systemd unit
> status, the journal, the alert log, and this record **are** the evidence. An `2026-08-24` partition
> directory was deliberately **not** created — manufacturing a directory to document a failure would
> put a defective, contentless partition inside a governed corpus.

---

## 1. What happened

`mdq-sample.service` failed **before acquisition**, three seconds after start.

```
Aug 24 09:25:02 ip-172-31-7-230 systemd[1]: Starting mdq-sample.service - MDQ-001 Phase-A paired IEX/SIP quote sampler (governed, until close)...
Aug 24 09:25:05 ip-172-31-7-230 mdq_run.sh[2971273]: acquisition creds absent (ALPACA_PAPER_6_API_KEY / _SECRET)
Aug 24 09:25:05 ip-172-31-7-230 systemd[1]: mdq-sample.service: Main process exited, code=exited, status=1/FAILURE
Aug 24 09:25:05 ip-172-31-7-230 systemd[1]: mdq-sample.service: Failed with result 'exit-code'.
Aug 24 09:25:05 ip-172-31-7-230 systemd[1]: Failed to start mdq-sample.service - MDQ-001 Phase-A paired IEX/SIP quote sampler (governed, until close).
Aug 24 09:25:05 ip-172-31-7-230 systemd[1]: mdq-sample.service: Triggering OnFailure= dependencies.
```

| Item | Value |
|---|---|
| Unit result | `Result=exit-code`, `ExecMainStatus=1` |
| `ExecMainStartTimestamp` | `Mon 2026-08-24 09:25:02 EDT` |
| Literal error line | `acquisition creds absent (ALPACA_PAPER_6_API_KEY / _SECRET)` |
| Alert written | `2026-08-24T13:25:05Z MDQ FAILURE unit=mdq-sample.service` |
| Emitting code | `apps/backend/scripts/mdq_collector.py` — `raise SystemExit(f"acquisition creds absent ({pins.cred_env_key} / _SECRET)")` |

### Absence of both partition directories — verified

```
ls: cannot access '/opt/workbench/data/mdq_capture/iex/2026-08-24/quotes/': No such file or directory
ls: cannot access '/opt/workbench/data/mdq_capture/sip/2026-08-24/quotes/': No such file or directory
```

The capture root holds **only** `2026-08-19`, `2026-08-20`, `2026-08-21` under each of `iex/` and `sip/`.

---

## 2. The gates that PASSED — recorded so the failure is not misattributed

The wrapper's fail-closed gates are ordered **universe pin → free space → single-instance**, and the
credential check happens *inside* the collector, after all three. Two of the three wrapper gates were
measured green **50 minutes before the slot** (08:34:39 EDT) and again at 13:40 UTC:

| Gate | Result | Evidence |
|---|---|---|
| **Universe pin** | **PASS** | `0c57bd71c0b73565328ec27036c6573f11b87594acb49ca461458a7d947f88d4` — expected == actual |
| **Free-space floor** | **PASS** | `size_gb=58 avail_gb=27 floor=11` ⇒ 16 GiB margin. Raw: 61,285,326,848 B size / 28,766,879,744 B avail. Effective fail threshold `avail_bytes <= 10,737,418,240` |
| **Single-instance** | **PASS** | 0 running `mdq_collector.py … sample` processes |
| **Acquisition credentials** | **FAIL** | `ALPACA_PAPER_6_API_KEY` / `ALPACA_PAPER_6_API_SECRET` absent from the collector's environment |

⭐ **The disk was never the problem.** Recording this explicitly because the standing operational
lesson about redeploys has until now been framed as a free-space hazard, and a reader who assumes the
familiar cause will mis-diagnose this day.

---

## 3. Cause — the 2026-08-23 environment rewrite

| Item | Value |
|---|---|
| Env file consumed by the backend | `docker-compose.yml` → `env_file: .env` → `/opt/workbench/app/.env`, a **symlink** to `/opt/workbench/.env` |
| `/opt/workbench/.env` identity | **1,014 B**, mtime **2026-08-23 11:54:36.988332262 -0400** |
| `.deploy_src_sha` stamp | **2026-08-23 12:00:51 EDT** — the env file was rewritten **6 minutes earlier** |
| Deployed commit | `0344337787a6ce27df64995f7a556b19a4bf297a` (#666) |
| Backend image | `sha256:fc76c0ed70158978a466494852a07b27cdb750725c35e09a986d30e6f7fc7d85`, built 2026-08-23T16:16:59-04:00 |
| Backend container created | **2026-08-23T20:17:44.634887882Z** |
| Credentials now present in container | **only the unnumbered pair** — `ALPACA_PAPER_API_KEY`, `ALPACA_PAPER_API_SECRET` |
| Credentials required by the collector | `ALPACA_PAPER_6_API_KEY`, `ALPACA_PAPER_6_API_SECRET` (`AcquisitionPins`, `app/research/capture/identity.py`) |

The only `.env` backup on the box, `/opt/workbench/.env.pre-keysync-20260707-1159`, also carries no
numbered credentials, so it is not a restoration source.

Captures ran normally on **2026-08-19, 08-20 and 08-21** against the pre-redeploy container.
**2026-08-24 was the first trading day after the container was recreated.**

**Trading was unaffected** — broker adapters resolve credentials from the encrypted database. The MDQ
collector is the one component that deliberately reads environment variables, which is why it alone
failed.

### Code-identity conformance did not prove operational readiness

All five approved collector blobs remained **byte-identical and conformant** across this deploy —
verified in git at `0344337` and inside the running container. The deploy changed *runtime state*, not
*code identity*. A conformant blob check says nothing about whether the registered acquisition
environment still exists.

⛔ **This must not be repaired by pointing MDQ at the unnumbered `ALPACA_PAPER_*` credentials.**
Account 7's entitled acquisition identity and the Phase-A collector boundary are deliberate; changing
the credential identity to make a slot run would be a **governance change**, not an operational
recovery.

---

## 4. Downstream units for 2026-08-24 — OBSERVED

Observed read-only at 2026-08-24 16:47:00 EDT. Recorded rather than suppressed.

| Unit | Scheduled | Observed |
|---|---|---|
| `mdq-eod.service` | 16:30 ET | **FAILED** — `Result=exit-code`, `ExecMainStatus=1`, started 16:30:02, exited 16:30:05 |
| `mdq-freeze.service` | 16:45 ET | **Exit 0** — `Result=success`, `ExecMainStatus=0`, started and exited 16:45:02 |

### 4.1 `mdq-eod.service` — the same credential condition

```
Aug 24 16:30:02 ip-172-31-7-230 systemd[1]: Starting mdq-eod.service - MDQ-001 end-of-session 1-min bars, both feeds (governed)...
Aug 24 16:30:04 ip-172-31-7-230 mdq_run.sh[3134622]: acquisition creds absent (ALPACA_PAPER_6_API_KEY / _SECRET)
Aug 24 16:30:05 ip-172-31-7-230 systemd[1]: mdq-eod.service: Main process exited, code=exited, status=1/FAILURE
Aug 24 16:30:05 ip-172-31-7-230 systemd[1]: mdq-eod.service: Failed with result 'exit-code'.
Aug 24 16:30:05 ip-172-31-7-230 systemd[1]: Failed to start mdq-eod.service - MDQ-001 end-of-session 1-min bars, both feeds (governed).
Aug 24 16:30:05 ip-172-31-7-230 systemd[1]: mdq-eod.service: Triggering OnFailure= dependencies.
```

**Byte-for-byte the same failure line as the 09:25 sampler** — one cause, two units. A second alert
was written and is **preserved, not suppressed**:

```
2026-08-24T13:25:05Z MDQ FAILURE unit=mdq-sample.service
2026-08-24T20:30:05Z MDQ FAILURE unit=mdq-eod.service
```

### 4.2 `mdq-freeze.service` — exit 0, and it means NO PARTITION

```
Aug 24 16:45:02 ip-172-31-7-230 systemd[1]: Starting mdq-freeze.service - MDQ-001 freeze + verify + S3 mirror (governed)...
Aug 24 16:45:02 ip-172-31-7-230 mdq_run.sh[3140484]: no partitions for 2026-08-24; nothing to freeze
Aug 24 16:45:02 ip-172-31-7-230 systemd[1]: mdq-freeze.service: Deactivated successfully.
Aug 24 16:45:02 ip-172-31-7-230 systemd[1]: Finished mdq-freeze.service - MDQ-001 freeze + verify + S3 mirror (governed).
```

⚠⚠ **This zero exit means NO PARTITION / NO EVIDENCE. It does NOT mean a successful capture.** The
freeze wrapper short-circuits when neither feed directory exists. A later reader scanning unit exit
codes will see `success` for `mdq-freeze.service` on this date; it is recorded here so that success is
read correctly. **Nothing was frozen, nothing was verified, and nothing was mirrored to S3**, because
there was nothing to act on.

### 4.3 Both partition directories remain absent — verified after all three units ran

```
ls: cannot access '/opt/workbench/data/mdq_capture/iex/2026-08-24': No such file or directory
ls: cannot access '/opt/workbench/data/mdq_capture/sip/2026-08-24': No such file or directory
```

Capture root contents, unchanged from before the session:

```
/opt/workbench/data/mdq_capture/iex/2026-08-19
/opt/workbench/data/mdq_capture/iex/2026-08-20
/opt/workbench/data/mdq_capture/iex/2026-08-21
/opt/workbench/data/mdq_capture/sip/2026-08-19
/opt/workbench/data/mdq_capture/sip/2026-08-20
/opt/workbench/data/mdq_capture/sip/2026-08-21
```

No 2026-08-24 directory was created at any point, by any unit, and none was created to document the
failure.

---

## 5. Disposition

1. **2026-08-24 is a capture non-event.** No governed partition exists.
2. **No salvage.** A sampler started after 09:25 could not meet the frozen completeness floor (0.98)
   and would breach the maximum contiguous-gap limit at the opening; the slot grid is anchored at
   09:25:00 ET.
3. **No backfill, no reconstruction, no later manufacture** of the missing cycles.
4. **No credential substitution.**
5. The 60-day review window `[2026-08-19, 2026-10-18)` and **D0 = 2026-08-19** are unchanged. The
   holdouts are unchanged.

**Final disposition: 2026-08-24 NON-EVENT — CLOSED.** All three completion facts were observed and
match the disposition: `mdq-eod` failed on the same credential condition, `mdq-freeze` exited 0 with
nothing to freeze, and both partition directories remained absent after every unit had run.

Root cause: **runtime acquisition-environment loss after redeploy** — explicitly **not** disk
exhaustion, **not** collector-code drift, **not** universe-pin failure, and **not** a data-quality
failure. The governed corpus is unchanged at three partitions per feed (2026-08-19, 08-20, 08-21).

---

## 6. Corrective action

**`apps/backend/scripts/mdq_preflight_readiness.sh`** — a read-only preflight that reproduces the
collector's actual gate chain rather than one remembered leg:

```
universe pin → acquisition credential presence/non-empty → account-identity latch
             → free space → single-instance state
```

Secrets are never printed: credentials are reported as `SET`/`ABSENT` plus length, and the identity
result as pass/fail. The 12-hex key fingerprint is printed, which the collector's own docstring
records as safe for manifests and logs.

Validated against the live box on 2026-08-24 at 13:40 UTC, where it correctly returned
gate 1 PASS · gate 2 **FAIL** · gate 3 NOT EVALUABLE · gate 4 PASS · gate 5 PASS ⇒ **NOT READY**,
exit 1. Run before every governed slot, and **always** after any deployment that recreates the
collector's container.

**Operational rule this establishes:** *a deployment that recreates the collector's container must
prove the complete registered acquisition environment before the next scheduled governed slot.*
