# SEC-001 V3 — Execution-Control Addendum v1.4.1

## PROCEDURAL NONCONFORMANCE: unbound execution controller at launch

**Status:** Owner-ruled 2026-08-24. Narrow addendum to Pre-Crawl Manifest v1.4
(`126640240b94d7e64dc261e02604dad47ca4910d`). v1.4 is **not edited**.
**Scope:** binds the execution controller only. It changes no acquisition semantics, no
population, no ordering, and no coverage boundary.

---

## 1. The nonconformance

`crawl_full.py` supplies hard-stop behaviour that the frozen driver does not: the driver
halts on 403 by itself, but records every other stop condition faithfully without acting on
it. The runner therefore became a **load-bearing execution controller** the moment it was
launched.

It was launched at `2026-08-24T21:22:36Z` **without prior binding**. Verified:

- Manifest v1.4 contains **zero** references to `9571c9eb…`, `crawl_full`, or a runner;
- v1.4 was committed *before* the runner was written;
- no pre-launch remotely-custodied execution record exists.

This is a **procedural execution-control nonconformance**, recorded rather than quietly
corrected. The governing principle it violated: anything that can stop or fail to stop a
governed acquisition is part of the governed apparatus and must be bound before it runs.

## 2. Disposition — work already collected is retained

The crawl was stopped at the next safe unit boundary. **5 identities are terminal**, every
one with complete outputs on disk, no partial state, and 405 decision artifacts retained.

Those units are **not discarded**, because the runner does not select filings, transform
source bytes, classify SIC, or alter the frozen population. It only supervises stopping
conditions. Nothing it did could change what was acquired or how it was interpreted — the
defect is that it was *unbound*, not that it was *wrong*.

The safe boundary is structural, not lucky: `CrawlState.mark_done` is called only after a
unit's outputs are written, so a mid-unit stop leaves that unit non-terminal and it is
re-crawled wholesale on resume.

No new epoch is created. The same v1.4 state resumes at the next pending identity.

---

## 3. Bound execution controller

```
runner            /opt/workbench/sec001-v3/crawl_full.py
sha256            9571c9eb5331381fa659cd800f6b9117e10daee67453bfe99c85349209aa2a5e
epoch             /opt/workbench/sec001-v3/crawl-v1.4
driver            /opt/workbench/sec001-v3/driver/86f3cca1
manifest          Pre-Crawl Manifest v1.4 (126640240b94…)
```

### 3.1 Authorized scope — exhaustive

The runner **may**:

1. inspect evidence already written by the frozen driver;
2. halt the run;
3. write `RUNNER_STOPPED.json` recording the reason and the state at the stop;
4. resume deterministic pending work from the existing `crawl_progress.jsonl`.

The runner **may not**:

- alter identity order;
- alter retry policy;
- alter acquisition semantics;
- alter evidence contents;
- alter classification output;
- compute coverage.

It asserts identity #1 is already terminal and refuses to start otherwise, so it cannot
restart or reorder the population.

### 3.2 Fixed supervision semantics

Evaluated after **every** unit; any trip writes `RUNNER_STOPPED.json` and exits:

| condition | stop reason |
|---|---|
| `ACQUISITION_HEADER_INCOMPLETE` on any accession | acquisition failure |
| `ACQUISITION_ENCODING_UNSUPPORTED` on any accession | acquisition failure |
| `parser_body_sha256 != source_decision_bytes_sha256` | evidence integrity |
| decision-byte artifact missing or absent from disk | evidence integrity |
| declared non-identity encoding with `wire_sha256 == parser_body_sha256` | encoded body reached the parser undecoded |
| ranged fallback returned a non-identity encoding | ranged-encoding violation |
| 403 | driver's own latch; one blocked request, state preserved |

Evaluated every 25 units over the **full** evidence log:

| condition | stop reason |
|---|---|
| host outside `www.sec.gov` / `data.sec.gov` | unexpected domain |
| method other than `GET` | unexpected HTTP method |
| form outside the frozen eight | unexpected filing form |
| any consecutive `sent_monotonic_ns` gap `< 0.196 s` | actual-send rate proof violated |

Evaluated at completion: any of the ten forbidden coverage fields present in any output.

### 3.3 What is deliberately NOT a stop

A **complete, valid source that genuinely contains no SIC** is a legitimate source
observation and does not halt the crawl. Only acquisition failures halt. This distinction is
the whole reason the four-status vocabulary exists, and the runner must not collapse it.

Exhausted bounded retries that cannot acquire the required source **do** stop, rather than
being converted into historical missingness.

---

## 4. Checkpoint minimum

Terminal count monotonically increasing · next identity consistent with the frozen order ·
process alive or an explicit stop reason · no acquisition hard-stop condition · periodic
full-log proof that method, domain and form rules hold and that the **≥0.2-second
actual-send interval** continues to hold.

Average throughput (~0.95 req/s) is informative context only. **The actual-send minimum is
the governing rate evidence**, not the average.

---

## 5. Completion boundary — unchanged

At 1,167/1,167 terminal the crawl **stops**. Successful completion does **not** invoke
coverage. The next artifact is the acquisition-only crawl-integrity report, remotely
custodied, and only then does the coverage question reopen.

`5b26ffa2…` remains **UNSPENT**.

---

## 6. State at addendum

```
epoch                 crawl-v1.4 (unchanged, not recreated)
terminal identities   5 of 1,167   (ABT retained as #1)
outputs               complete for all 5; no partial state
decision artifacts    405
prior epochs          v1.1, v1.2 canaries and v1.3 diagnostic — preserved, unresumed
population            1,167 unchanged
coverage              none computed; 5b26ffa2… UNSPENT
```
