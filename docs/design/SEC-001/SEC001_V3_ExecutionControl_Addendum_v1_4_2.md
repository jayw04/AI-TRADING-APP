# SEC-001 V3 — Execution-Control Addendum v1.4.2

## Structural runtime assertions; supersedes the controller bound by v1.4.1

**Status:** Owner-ruled 2026-08-24. Narrow addendum to Pre-Crawl Manifest v1.4
(`126640240b94…`), superseding the controller binding in Addendum v1.4.1 (`59f6044f…`).
Neither v1.4 nor v1.4.1 is edited.
**Scope:** binds a new execution controller only. No acquisition semantics, population,
ordering, retry policy, evidence content or coverage boundary changes.

---

## 1. Why this addendum exists

The owner ruled that nine checkpoint conditions be treated as **hard runtime assertions
rather than informational monitoring**, and added a completion criterion requiring exactly
1,167 **unique** terminal identities **in frozen order** — not merely `terminal_count == 1167`.

The controller bound by v1.4.1 (`9571c9eb…`) enforces the acquisition, encoding, rate,
domain, method and form conditions. It enforces **none** of these four:

- terminal count never decreases;
- terminal identities are a prefix of the frozen deterministic order;
- no duplicate terminal identity;
- no partial unit can become terminal.

Those four were guaranteed **by construction** rather than asserted. That is exactly the
posture this program has been burned by three times already — the CRLF pin, the gate section
registry, and the encoding fallback were all "structurally fine" until they were not. A
guarantee nobody checks is a belief.

The owner's own restart invariant therefore applies: *a modified runner requires another
pre-execution governance amendment before it may control the crawl.* Continuing under
`9571c9eb…` while claiming those assertions were live would have been a false claim, so the
crawl was stopped at a unit boundary and this addendum written before the new controller
runs.

## 2. Disposition of work already collected

Stopped at a true unit boundary: **8 identities terminal**, every one with complete outputs,
no partial state, 685 decision artifacts. Nothing is discarded and no new epoch is created —
the controller change alters supervision only, not what was acquired or how it was
interpreted.

---

## 3. Bound execution controller

```
runner            /opt/workbench/sec001-v3/crawl_full.py
sha256            894e474472111c129ad2eec8471f4d614a15956ee9521850e610d627925d21bc
supersedes        9571c9eb5331381fa659cd800f6b9117e10daee67453bfe99c85349209aa2a5e (v1.4.1)
epoch             /opt/workbench/sec001-v3/crawl-v1.4   (unchanged)
driver            /opt/workbench/sec001-v3/driver/86f3cca1  (unchanged)
```

### 3.1 Authorized scope — unchanged from v1.4.1, restated

The runner **may**: inspect evidence; halt; write `RUNNER_STOPPED.json`; resume deterministic
pending work from the existing `crawl_progress.jsonl`.

The runner **may not**: alter identity order, retry policy, acquisition semantics, evidence
contents, classification output, or compute coverage.

### 3.2 Restart invariant (frozen)

> A runner restart is authorized only when the executable bytes still hash to the
> addendum-bound value **and** the frozen crawl state determines the next pending identity.
> Any modified runner requires another pre-execution governance amendment before it may
> control the crawl.

Enforced operationally: resume re-hashes the on-host runner against the bound value and
aborts on mismatch, aborts if a stop file is present, and aborts if a runner is already
alive.

### 3.3 The nine hard runtime assertions

Evaluated **after every unit** unless marked otherwise. Any trip writes
`RUNNER_STOPPED.json` and exits non-zero.

| # | assertion | new in v1.4.2 |
|---|---|---|
| 1 | terminal count never decreases | **yes** |
| 2 | terminal identities are a prefix of the frozen deterministic order | **yes** |
| 3 | no duplicate terminal identity | **yes** |
| 4 | no partial unit can become terminal (every terminal unit has its observation file) | **yes** |
| 5 | process alive, or an explicit governed stop reason exists | operational |
| 6 | no acquisition hard-stop condition (`ACQUISITION_HEADER_INCOMPLETE`, `ACQUISITION_ENCODING_UNSUPPORTED`, digest mismatch, missing decision bytes, undecoded encoded body, ranged non-identity encoding, 403) | v1.4.1 |
| 7 | whole-log method / domain / form proof, every 25 units | v1.4.1 |
| 8 | every actual-send delta ≥ 0.2 s, every 25 units over all stamps | v1.4.1 |
| 9 | no coverage field or calculation anywhere, at completion | v1.4.1 |

### 3.4 Completion criterion (strengthened)

Completion requires **exactly 1,167 unique terminal identities equal to the frozen order**,
asserted as three separate checks: count, uniqueness, and order equality.

`terminal_count == 1167` alone is insufficient — a duplicate plus a gap satisfies it while
leaving an identity uncrawled. That is precisely the silent-shortfall shape this program
exists to prevent.

### 3.5 What remains deliberately NOT a stop

A **complete, valid source that genuinely contains no SIC** is a legitimate source
observation. Only acquisition failures halt. Exhausted bounded retries that cannot acquire
the required source **do** stop, rather than being converted into historical missingness.

---

## 4. Completion boundary — unchanged

At 1,167/1,167 the execution apparatus **stops**. Successful completion does **not** invoke
coverage. The next artifact is the acquisition-only crawl-integrity report, which must also
record the v1.4.1 controller nonconformance and this v1.4.2 remediation as **execution
provenance** — not as a classification or coverage failure.

`5b26ffa2…` remains **UNSPENT**.

---

## 5. State at addendum

```
epoch                 crawl-v1.4 (unchanged, not recreated)
terminal identities   8 of 1,167   (ABT retained as #1)
outputs               complete for all 8; no partial state
decision artifacts    685
prior epochs          v1.1, v1.2 canaries and v1.3 diagnostic — preserved, unresumed
population            1,167 unchanged
coverage              none computed; 5b26ffa2… UNSPENT
```
