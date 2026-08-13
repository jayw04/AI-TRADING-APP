# MR-002 Phase 3B — width qualification curve

**Status: complete through width 150. Width 429 NOT run — stop rule triggered.**
**Classification: `HOST_SIZING` — the qualified host is undersized for the registered universe.**

Data class: **FIXTURE / NON-SEALED**. No sealed read, no reader assumption, no IAM change, no
validation or OOS object. Attempt #1's opening remains SPENT/void; no replacement opening was
requested, granted, or consumed by any run recorded here. Containment unchanged throughout: IAM latch
closed, host stopped.

## The curve

Every point is a **full path through publication** — `disposition=PASS`, `terminal_state=S11_PUBLISHED`,
six deliverables present, non-empty, and reproducing their recorded SHA-256. Measured on the
developer laptop, not on the qualified host.

| width | run seconds | wall | peak RSS | deliverables | units | artifact |
|---:|---:|---:|---:|---:|---:|---|
| 6 | 190.1 | 0.05 h | 153.9 MiB | 6.50 MB | 10,200 | `…850SessionFullPathQualification_Run3_Authoritative_v1.0.json` |
| 12 | 445.2 | 0.12 h | 205.6 MiB | 13.54 MB | 20,400 | `…WidthQualification_012sec_v1.0.json` |
| 50 | 3,713.7 | 1.03 h | 463.7 MiB | 58.13 MB | 85,000 | `…WidthQualification_050sec_v1.0.json` |
| 150 | 9,469.2 | 2.63 h | 1,266.1 MiB | 175.45 MB | 255,000 | `…WidthQualification_150sec_v1.0.json` |
| **429** | **not run** | — | — | — | — | stop rule triggered; see below |

Peak RSS is the OS `PeakWorkingSetSize` (`performance.peak_rss_mib`), not the 15 s sampler
high-water. At width 50 the sampler undersampled the true peak by 14%; at width 150 the two agreed
exactly, because the peak persisted across a sample boundary.

## Runtime: benign, and the width-50 point is an outlier

Local log-log exponents on total runtime are 1.227 (6→12), 1.486 (12→50), **0.852 (50→150)**. The
apparent acceleration through width 50 does not survive the width-150 measurement. Fitting only
6/12/150 gives a stable **α ≈ 1.21** (1.214 on 6→150, 1.210 on 12→150), under which width 50 should
have taken 2,484 s against an actual 3,713.7 s — **+50%**. The width-50 run executed alongside other
work on the same laptop; machine contention is the most probable explanation, and no conclusion here
depends on that point.

**Width 429 projects to ≈ 9.4 h**, not the ~25 h carried into this session from the pre-150 fit.
Runtime is therefore *not* a reason to decline width 429.

## Memory: the exponent is accelerating, and that is the finding

| interval | RSS exponent |
|---|---:|
| 6 → 12 | 0.418 |
| 12 → 50 | 0.570 |
| **50 → 150** | **0.914** |

Memory scaling is worsening monotonically and has now reached **essentially linear in width**. Three
independent extrapolations to width 429 agree:

| model | width 429 peak RSS |
|---|---:|
| linear fit on 50→150 (`62.5 + 8.024·w`) | 3,505 MiB = **3.42 GiB** |
| power law at the measured α = 0.914 | 3,308 MiB = **3.23 GiB** |
| power law at α = 1.0 (if the trend completes) | 3,621 MiB = **3.54 GiB** |

The qualified host is **c6a.large — 2 vCPU / 4 GiB** (`MR002_Phase3CHostFreeze_v1.0.json`). A
3.2–3.5 GiB peak is **81–88% of the host's total RAM**, leaving 0.5–0.8 GiB for the operating system,
the container runtime, page cache, and the process's own transient allocations. That is not a margin;
it is an out-of-memory kill with a governed opening spent on it.

Width 429 also writes **~502 MB of deliverable JSON** per run, which the host must hold and persist.

## Stop rule, as applied

The rule carried into this session: *stop before 429 and classify as host sizing if the final peak RSS
approaches ~3 GiB **or** accelerates toward the 4 GiB envelope; otherwise proceed despite the runtime.*

- Width 150's final peak is **1.27 GiB** — it does **not** approach 3 GiB. First clause not met.
- The RSS exponent **accelerated** 0.418 → 0.570 → 0.914, and the resulting width-429 projection is
  **81–88% of the 4 GiB envelope**. **Second clause met.**

The second clause exists precisely to catch a run that completed comfortably while its trend
disqualified the next one. It is met. **Width 429 is not attempted.**

Running width 429 on the laptop instead would produce a number but would not change the finding: the
governed execution must run on the qualified host, and this is a statement about that host.

## What this does and does not establish

**Established.** The repaired execution path completes computation *and* durable publication at the
registered 850-session horizon across a 25× range of universe width, with a clean terminal state and
hash-reproducing deliverables at every point. The defect that voided attempt #1 does not recur at
scale. Runtime at full width is ~9.4 h and is not a blocker.

**Not established.** That width 429 executes within the frozen host envelope. The evidence says it
probably does not.

**Not claimed.** Calendar identity with the registered validation window (the fixture builds 850
consecutive weekdays); sealed-data economics; any research result. No Sharpe, return, ranking, or
config outcome exists or is implied.

## Open decisions — owner

1. **Resize the qualified host.** c6a.xlarge (4 vCPU / 8 GiB) would carry a 3.5 GiB peak with real
   margin and would roughly halve wall-clock if any stage parallelizes. ⚠ This is **not** a sysadmin
   action: the host is frozen and its numeric runtime identity is registered
   (`MR002_NumericRuntimeIdentityManifest_RuntimeInstance_v1.0.json`,
   `MR002_Phase3CHostFreeze_v1.0.json`). c6a.large → c6a.xlarge stays within the same AMD EPYC / AVX2
   family, so numeric identity is *plausibly* preserved — but that is an adjudication, not an
   inference, and it must be made before any replacement opening is granted.
2. **Reduce peak memory instead of the host.** Not investigated. Peak traced Python allocation at
   width 150 was 655.5 MiB against a 1,266.1 MiB process peak, so roughly half the footprint is
   native buffers and interpreter overhead — streaming the deliverable serialization is the obvious
   candidate. This is engineering work on the bound image and would require re-qualification.
3. **Measure width 429 on the laptop anyway**, as corroboration rather than qualification
   (~9.4 h, ~3.4 GiB). It would convert the projection into a measurement. It does not unblock the
   host question.

Recommendation: **(1)**, adjudicated explicitly, before any replacement opening is discussed.
