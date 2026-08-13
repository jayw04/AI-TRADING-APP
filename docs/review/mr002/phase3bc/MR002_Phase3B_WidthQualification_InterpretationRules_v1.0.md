# Width qualification — how to read the evidence artifacts

Documentation only. No harness change.

## `status: RUNNING` means "no terminal checkpoint was written"

It does **not** mean "currently executing".

The harness checkpoints atomically every ~15 s while the production run proceeds. A hard kill
(`timeout`, `Stop-Process`, task-lifecycle termination) gives Python no chance to run its exception
handler, so the terminal status is never written and the last durable artifact remains `RUNNING`.

**Liveness must be determined externally**, from process state or artifact freshness:

```bash
# fresh mtime (< ~60 s) => a sampler is still writing => live
# stale mtime           => the run ended without a terminal checkpoint => LAST KNOWN STATE
```

Read a stale `RUNNING` artifact as *last known state*, never as a live run. Its `elapsed_seconds`,
`rss_peak_mib` and `rss_samples` remain valid observations up to the moment of termination.

## Terminal statuses

| status | meaning |
|---|---|
| `PASS` | completed; terminal state `S11_PUBLISHED`, deliverables present, nonempty, hashes reproduce |
| `INTERRUPTED` | an exception propagated and the handler ran; `interrupted_by` records the cause |
| `RUNNING` | no terminal checkpoint — either live (fresh artifact) or hard-killed (stale artifact) |

## Aborted width-12 attempt, 2026-08-13

Terminated at 597.6 s by an operator-supplied `timeout 600`, **not** by the code, the workload or
the environment. Not a defect verdict. 40 RSS samples survived with peak 148.7 MiB, which is what
the observability repair exists to guarantee: an interruption yields evidence rather than absence
of evidence.

## Stop rule at the wider points

Stop early only for a genuine resource condition, never for duration alone — the governed execution
has no timeout and a long successful run is better evidence than an untested width.

* rapidly accelerating RSS, or a slope projecting uncomfortably toward the 4 GiB host envelope;
* paging / thrashing;
* **forward-progress collapse**: processed-unit throughput falling toward zero for a sustained
  period while CPU remains active, which can indicate pathological algorithmic scaling even with
  flat RSS.
