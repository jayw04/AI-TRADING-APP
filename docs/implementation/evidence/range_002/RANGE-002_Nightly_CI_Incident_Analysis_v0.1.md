# RANGE-002 - Nightly (scheduled) CI Incident Analysis v0.1

Status: READ-ONLY analysis. Recommendations are not decisions. Prepared 2026-10-10 (UTC) against `main` at `b31b5f7b` (PR #738).
Method: `gh run list/view`, `gh api .../actions/runs/{id}/jobs`, `gh api .../actions/jobs/{id}/logs`; plus a local reproduction of the lock gate with `uv 0.12.0`. No reruns, dispatches or settings changes were made.

## 1. Summary

Every scheduled `CI` run since 2026-08-30 (run #1710) has failed, with identical, mechanical causes. Two independent defects, both in workflow/tooling code, neither in product, test or RANGE-002 code:

| # | Defect | Job / step | Since |
|---|---|---|---|
| A | `Classify changes` step cannot start its shell: `Argument list too long` (the `CHANGED_FILES_JSON` env var, which on `schedule` events lists the entire repo, exceeds the Linux per-string limit of 131,072 bytes). This fails `Detect changes`, which makes `Python CI Gate` fail closed and skips every test job. | `Detect changes` -> `Python CI Gate` | #1710 (2026-08-30); last green scheduled gate #1692 (2026-08-29) |
| B | `Fresh resolution proof (uncached)` can never pass: `check_dependency_locks.py --recompile` compares a header-less `uv pip compile --no-header` output against committed files that begin with a 19-line generated header; additionally an unpinned fresh resolve now picks newer upstream versions (e.g. `anthropic` 1.13.0 vs committed 0.120.2). | `Fresh resolution proof (uncached)` / `Re-resolve and require byte-identical output` | Failing in every scheduled run in the history examined (earliest examined #1488, 2026-08-11); the job and script landed in #543 (2026-07-29) |

Neither defect is reachable from a pull request: `Fresh resolution proof` is `if: schedule || workflow_dispatch`, and defect A only occurs on the `schedule` branch of the step because PRs pass a small PR-diff file list. The required PR check (`Python CI Gate`) is green on the latest main push runs.

## 2. Evidence by run

### 2.1 Scheduled runs #1804-#1807 (headSha 3bc28fd6)

| Run # | Run id | Date (UTC) | Detect changes | Fresh resolution proof | Python CI Gate | Test jobs |
|---|---|---|---|---|---|---|
| 1804 | 37429140026 | 2026-10-06 07:21 | failure (Classify step) | failure | failure | skipped |
| 1805 | 37586927688 | 2026-10-07 07:22 | failure | failure | failure | skipped |
| 1806 | 37743126671 | 2026-10-08 07:23 | failure | failure | failure | skipped |
| 1807 | 37898721472 | 2026-10-09 07:23 | failure | failure | failure | skipped |

Jobs of #1807: Fresh 113716014016 (failure), Detect changes 113716014321 (failure), Python CI Gate 113716065490 (failure); Python (matrix), Python FULL (matrix), Frontend, Build image all `skipped` (blocked by `needs: changes`). #1804 jobs: Fresh 112155624231, Detect 112155624483, Gate 112155679434.

Failing log lines (#1807, job 113716014321, step 4 "Classify changes (per-project FULL?)"):

```
2026-10-09T07:23:24.3605262Z ##[warning]'before' field is missing in event payload - changes will be detected from last commit
2026-10-09T07:23:24.6940133Z ##[error]An error occurred trying to start process '/usr/bin/bash' with working directory '/home/runner/work/AI-TRADING-APP/AI-TRADING-APP'. Argument list too long
```

(`gh run view --log` truncates before this line; it is visible via `gh api actions/jobs/{id}/logs`. Steps 5-7 are `skipped`, step 4 `failure`.)

Failing log lines (#1807, job 113716014016, step "Re-resolve and require byte-identical output"):

```
dependency-lock gate FAILED:
  - backend: re-resolution DIFFERS from the committed file - the committed graph is not reproducible; regenerate and review the diff
  - mcp-server: re-resolution DIFFERS ...
  - mcp-workbench: re-resolution DIFFERS ...
  - agent: re-resolution DIFFERS ...
Regenerate with: python scripts/regenerate_dependency_locks.py
##[error]Process completed with exit code 1.
```

Classification against the task's (a)-(d): Fresh proof = (a); Detect changes classify step = (b); Python CI Gate = (c), a downstream, correct fail-closed consequence of (b) (`changes_result != success` -> "failing closed"); test jobs (d) = never ran (skipped), so no test failure is involved.

### 2.2 Mechanism A - environment-variable size limit

- `ci.yml` step `Classify changes` sets `env: CHANGED_FILES_JSON: ${{ steps.filter.outputs.all_files }}` for every event. The `else` (non-PR) branch never reads it, but the runner must still exec bash with it in the environment.
- On `schedule` events the payload has no `before`; `dorny/paths-filter` falls back to "last commit" and the log shows every filter reporting essentially the whole tree as `[added]` (e.g. `apps/frontend/Dockerfile.dev [added]`), so `all_files` is the whole repository file list.
- Measured sizes in the logged env line: run #1692 (2026-08-29, green) 130,850 chars including the ~50-char log prefix, i.e. just under the limit; run #1710 (2026-08-30, first failure) 131,410 chars; failed with the identical `Argument list too long`. Linux `MAX_ARG_STRLEN` is 131,072 bytes for a single `NAME=value` string.
- Local approximation of the JSON size from `git ls-tree`: 3bc28fd6 = 2,416 files, about 135 KB; origin/main b31b5f7b = 2,448 files, about 137 KB (PowerShell JSON; indicative only). The repository only grows, so this does not self-heal.
- The condition therefore was crossed by ordinary repository growth between 2026-08-29 and 2026-08-30. It predates RANGE-002 (first RANGE-002 code merged much later; PR 2 is #738, today). Nothing in the failing step touches RANGE-002.
- Why PRs and pushes are unaffected: on `pull_request` the file list is the PR diff (small) and on `push` the file list is the pushed commits' diff (small). Only `schedule` (and likely `workflow_dispatch`) yields whole-tree.

### 2.3 Mechanism B - lock-parity check is structurally unsatisfiable

- `scripts/check_dependency_locks.py::recompile_one` runs `uv pip compile ... --generate-hashes --no-header --output-file` and `main()` compares that text byte-for-byte with `constraints/<proj>-py312.txt`.
- The committed files are written by `scripts/regenerate_dependency_locks.py`, which PREPENDS a 19-line generated header (`# GENERATED FILE - DO NOT EDIT BY HAND.` ... `# source, not a downloadable third-party artifact with a package hash.`). The checker does not prepend/strip it, so the comparison can never be equal.
- Local reproduction (uv 0.12.0 installed in a scratch venv, `python scripts/check_dependency_locks.py --recompile` at b31b5f7b) printed the same four "re-resolution DIFFERS" lines. A manual comparison for `agent` with the header stripped is still unequal: line 9 fresh `anthropic==1.13.0` vs committed `anthropic==0.120.2` (fresh output 1,186 lines vs committed body 1,007), i.e. even with the header fixed, an uncached/unconstrained re-resolve drifts as upstream releases (no `--exclude-newer` or equivalent in the compile command).
- `constraints/*` and `check_dependency_locks.py` were last changed in #543 (2026-07-29); the failure is therefore not caused by any later PR. Of 99 scheduled runs in history, 18 succeeded and 81 failed; the oldest listed run is #714 (2026-07-03, success), and the 18 successes are assumed (not individually verified) to predate the Fresh job. Every run that includes the Fresh job that I examined (#1488 through #1807) shows it failing.
- Impact: the job is advisory/scheduled-only. Its failure does not feed `Python CI Gate` (`needs: [changes, python-checks, python-full]`).

### 2.4 Earlier distinct failure (context): #1488 (2026-08-11)

Run 31471994842, job 93717178747, step "Pytest (full, with coverage)": three `tests/deploy/test_factor_freshness_store_query.py` tests failed on wall-clock date (`STATUS sep_max=2026-08-06 ... et_today=2026-08-11 tolerance=4d max_lag=4d`). That is the date-pinned test class, but it was a one-off: scheduled gate runs #1494 to #1692 were green afterwards. It is unrelated to the October failures.

### 2.5 Did PR #735 address these? No.

`f5c225d9` (#735) changed only `tests/deploy/test_factor_adjudication_conformance.py`, `tests/jobs/test_sqlite_backup.py`, `tests/market_data/test_sip_cache_foundation.py` (3 files; the commit title says three tests). Those run in `Python FULL (backend)` on push/PR. The October nightly failures are in `Detect changes` and `Fresh resolution proof`, where no test code executes; the Python FULL jobs were skipped in all four runs. #735 made push run #1814 green (a real fix for the tests it touched, which would otherwise have failed push CI) but it has no bearing on defects A and B.

## 3. Latest main runs

| Run | Id | Event | SHA | Result | Notes |
|---|---|---|---|---|---|
| #1814 | 38000043472 | push 2026-10-09 22:35Z | f5c225d9 | success | Detect changes success, Python (x4) success, Python FULL (x4) success, Frontend success, `Fresh resolution proof` skipped, Build image skipped, Python CI Gate 114063015965 success |
| #1820 | 38013759012 | push 2026-10-10 01:35Z | b31b5f7b (PR #738 merge) | in progress at time of query | All completed jobs success (Detect changes, Frontend, 4x Build image, Python x4, Python FULL mcp-workbench/agent/mcp-server); `Fresh resolution proof` skipped; `Python FULL (backend)` in progress at step 5 "Pytest (full, with coverage)"; steps 6-10 pending, including step 9 "RANGE-002 Linux acceptance" and 10 "Upload RANGE-002 Linux evidence". Python CI Gate not yet started. FINAL RESULT NOT YET KNOWN. |
| Scheduled after 2026-10-10 00:00Z | - | - | - | none yet | next expected 2026-10-10 about 07:20Z; will run on b31b5f7b |

Prediction (not observed): the next scheduled run will fail in the same two places, with a slightly larger env var than before (~2,448 files). The RANGE-002 CI step is inside `python-full` and is skipped by `needs` on a scheduled run while `Detect changes` fails; it can therefore not execute on a nightly until defect A is fixed.

Why `Fresh resolution proof` is skipped on push/PR: its job-level condition is `if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'`, deliberately, so it is "scheduled only - never on a PR". It is not in the `needs` of any other job.

## 4. Do any failures implicate RANGE-002?

No. Defect A is repository-size growth against a Linux env-var limit, first hit 2026-08-30. Defect B is a gate/script bug dated 2026-07-29. The only RANGE-002 workflow addition is the `range002` paths-filter output and the final two steps of `python-full`; the filter is evaluated by `dorny/paths-filter` successfully in the logged nightlies (they predate it, but the push runs #1814/#1820 show it working). The verifier (`ci_verify_required_tests.py`) was never invoked in any failing run. Caveat: the RANGE-002 `ci.yml` change in #738 adds one more `filters:` block but does not alter the env-var size mechanism; the repository file count rose by 32 files from 3bc28fd6 to b31b5f7b (2,416 to 2,448), moving further above the limit.

## 5. Verdict table

| Run | Cause | Predates RANGE-002? | Reproduces now? | Blocks PR 3 or acceptance? | Recommended owner action (recommendation only) |
|---|---|---|---|---|---|
| #1804 (37429140026), #1805 (37586927688), #1806 (37743126671), #1807 (37898721472) - Detect changes | Defect A: `Argument list too long` (env var > 131,072 B on `schedule` events), job 113716014321 (#1807) | Yes (first failed #1710, 2026-08-30) | Yes, expected on every scheduled run; will be worse on b31b5f7b. Not on push (#1814 green, #1820 green so far) | No for PRs and push (required `Python CI Gate` green there). Affects nightly health only | Fix in a separate, workflow-only PR: do not pass the whole-tree list on non-PR events (e.g. set the env var only for `pull_request`, or write the list to a file in the paths-filter step / use `if: github.event_name == 'pull_request'` on the filter output), keeping fail-closed behaviour on PRs. Needs the ci.yml CI cost/walk-away treatment (flags all projects FULL on that PR). |
| #1804-#1807 - Python CI Gate | Consequence of A: `changes_result != success` -> "failing closed" (correct behaviour) | Yes | Yes on schedule only | No; it is the correct fail-closed outcome. Only the scheduled instance fails | None beyond fixing A |
| #1804-#1807 - Fresh resolution proof (jobs 112155624231, 113716014016 ...) | Defect B: checker compares header-less compile output with headered committed file; plus upstream drift (anthropic 0.120.2 -> 1.13.0) | Yes (job from #543, 2026-07-29; failing in every examined run since 2026-08-11) | Yes (reproduced locally with uv 0.12.0 at b31b5f7b) | No: not in any `needs`, never on PRs | Separate decision for the owner: either fix the checker (prepend/strip header, and compile with a date/exclude-newer bound or compare only the pin set) or re-scope the proof. Treat as tooling debt; do not tie to RANGE-002. |
| #1488 (31471994842), 2026-08-11 | Date-pinned tests in `test_factor_freshness_store_query.py` | Yes | No: scheduled gate green #1494-#1692; push runs green | No | None for this analysis |
| #1814 (38000043472) push f5c225d9 | Success; `Fresh` skipped by design | n/a | n/a | No | None |
| #1820 (38013759012) push b31b5f7b | In progress; `Python FULL (backend)` still pytest at query time; RANGE-002 acceptance steps pending | n/a | n/a | PENDING: PR 2 post-merge Linux acceptance depends on steps 5-10 of this job and on the Gate. Re-read when finished | Wait for completion before treating PR 2 post-merge CI as green; re-check Gate and the uploaded `range002-linux-acceptance-*` artifact |

## 6. Does this affect acceptance or PR 3?

- Nightly red is pre-existing, workflow-level, unrelated to RANGE-002 code, the RANGE-002 CI step or the verifier, and does not feed the PR-required `Python CI Gate` on pull_request or push events.
- Acceptance impact: indirect only. A nightly can never run `python-full` (and so can never run the RANGE-002 Linux acceptance step) until defect A is fixed, so "nightly green" cannot be cited as RANGE-002 evidence; the push/PR runs are the evidence path. The decisive items remain #1820's final Gate result and its RANGE-002 step output.
- PR 3 is not blocked by these nightlies. If the owner wants ci.yml fixed, doing it inside a RANGE-002 PR would flag every project and the `range002` filter, so it is better kept separate.

## 7. Recommended next steps (recommendations only)

1. Re-check #1820 once `Python FULL (backend)` and `Python CI Gate` complete; record the RANGE-002 acceptance step outcome.
2. Open one small, workflow-only PR for defect A (and optionally B), validated locally first (ci.yml change flags all projects FULL on that PR; plan for a single push).
3. Decide separately whether Fresh resolution proof should be repaired or re-scoped; until then treat its red as known noise, and record that the scheduled gate has been red since 2026-08-30 (about 40 consecutive runs) so it is not read as a regression.
4. Consider an alert/ownership for scheduled-CI failures; 40 consecutive nightly failures went unnoticed.
