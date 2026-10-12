# CI Nightly Remediation Proposal v0.2

Status: PROPOSAL ONLY. Nothing here is implemented, pushed, dispatched or decided. Every recommendation is marked "Recommendation (not a decision)".
v0.1 was prepared 2026-10-10 against `origin/main` b31b5f7b; v0.2 (this file) is refreshed the same day against `origin/main` d61f313a (PR #737, #738, #739 merged). Section 0 lists what changed; sections 1-8 are v0.1 text with the packaging recommendation (section 1, section 8 row 4, risk 6) revised. Workstream: CI reliability (GITHUB-OPS-001). It is deliberately NOT part of RANGE-002 and must NOT be combined with RANGE-002 PR 3.
Root-cause evidence: `docs/implementation/evidence/range_002/RANGE-002_Nightly_CI_Incident_Analysis_v0.1.md` (included in the same commit as this file; originally local commit 253b1610). Method for this document: read of `ci.yml`, `ci_classify_changes.py` and its tests, `check_dependency_locks.py`, `regenerate_dependency_locks.py`, `constraints/*.txt` headers, `docs/runbook/dependency-locks.md`, and the #543 commit message. `uv` is NOT installed on this machine (`uv --version` fails), so nothing about uv behaviour below was reproduced here; claims about uv come from the incident analysis (which reproduced with uv 0.12.0) or from uv documentation as I know it, and are flagged "to verify".

## 0. v0.2 refresh: drift since v0.1 and nightly status

### 0.1 Nightly status (read-only `gh run list --event schedule`, 2026-10-10)

| Run (scheduled, UTC) | Head | Conclusion |
|---|---|---|
| 2026-10-10 07:18 (run 38033950996) | `b31b5f7b` | **failure** |
| 2026-10-09 07:23 (run 37898721472) | `3bc28fd6` | failure |
| 2026-10-08 07:23 (run 37743126671) | `3bc28fd6` | failure |
| 2026-10-07 07:22 (run 37586927688) | `3bc28fd6` | failure |
| 2026-10-06 07:21 (run 37429140026) | `3bc28fd6` | failure |

Nightlies are STILL red; the streak that began 2026-08-30 continues (about 41 consecutive). Job detail of the latest run (read-only `gh run view`): `Detect changes` failure, `Fresh resolution proof (uncached)` failure, `Python CI Gate` failure (`unknown adr0043_gate flag ''` - the knock-on of `Detect changes` failing), and the build/LIGHT/FULL/frontend jobs skipped. The `Fresh resolution proof` log prints `re-resolution DIFFERS from the committed file` for all four projects (backend, mcp-server, mcp-workbench, agent), consistent with defect B. A `push` run of `main` at d61f313a was in progress at read time and is not a nightly.

### 0.2 Drift check against current `main` (d61f313a)

| Item | v0.1 statement | Status on d61f313a |
|---|---|---|
| Defect A site | `CHANGED_FILES_JSON: ${{ steps.filter.outputs.all_files }}` in the `Classify changes` step | UNCHANGED (ci.yml line 143). The proposed A1 diff still applies by context. |
| Defect A size | 2,448 files, 137,163 bytes | Now **2,486 tracked files, about 139.8 kB** as compact JSON (measured in a checkout of this branch), still over the 131,072-byte limit and growing. |
| Defect B | `scripts/check_dependency_locks.py` and `constraints/*` | UNCHANGED since #543 (c76ed269); `git diff b31b5f7b..origin/main` over `scripts/`, `constraints/`, `.github/`, `docs/runbook/` shows no change. The proposed B1+B2 diff still applies. Still unverified: uv behaviour (uv not available here). |
| RANGE-002 step in `ci.yml` | not mentioned | EXISTS now (the `range002` path filter, the `RANGE-002 Linux acceptance` step and the evidence upload). The `range002` filter lists `.github/workflows/ci.yml`, so ANY `ci.yml` PR, including defect A's, also runs this step on the PR (backend FULL leg). It requires the 33 manifest ids to PASS on Linux; it adds roughly one to two minutes to that leg (not measured on Actions). Defect A's PR therefore exercises the RANGE-002 acceptance as a side effect; that is expected, not a reason to couple them. |
| Pending guard-removal PR | not mentioned | A separate local branch (`ci/range002-remove-hashfiles-guards-v2`) also edits `ci.yml` (the `if:` of the RANGE-002 step, a different hunk from the classify step, so no textual overlap). Two pending `ci.yml` PRs each cost a global FULL run; whichever merges second must be updated against `main` first (`strict: true`), so merge them one at a time. They must stay separate PRs (different owners of risk: RANGE-002 vs nightly). |
| Test style | proposed test snippets in 2.4 and 3.5 | `apps/backend/tests/ci/test_ci_classify_changes.py` was reformatted on main (ruff format, `b31b5f7b..d61f313a`) and `tests/ci` now passes `ruff check` and `ruff format --check` (verified locally on 5 files). Any new test in `tests/ci` must be run through `ruff format` before commit; the snippets below are NOT formatted that way. |
| Classifier | `scripts/check_dependency_locks.py` is a GLOBAL path | Re-verified with `apps/backend/scripts/ci_classify_changes.py`: a change set of `scripts/check_dependency_locks.py` plus its runbook and test flags all four projects (`backend_code`, `mcp_server_code`, `mcp_workbench_code`, `agent_code`, `adr0043_gate` all true). So defect B's PR is a FULL run for all four projects, same as defect A's. |
| Protection | `Python CI Gate` is the single required check | Re-read: classic protection on `main` unchanged (strict, `Python CI Gate`, `enforce_admins: true`, no review requirement); no rulesets. |

### 0.2a Status update (2026-10-10, later the same day)

- Fix A is now a local PR candidate: branch `ci/nightly-fix-a-classify-env` (f1d6b7ff) with regression tests. An independent review of it has been commissioned by the coordinator; nothing is pushed.
- Fix B: the owner prefers B2 only if it fails whenever reproducibility cannot be proven, otherwise B3 or a further ruling. A fail-closed B2 specification (behaviour table with distinct exit codes 10-16, drift analysis versus B3, 31 offline tests, Linux first-run commands) and an updated UNAPPLIED patch are on local branch `ci/nightly-fix-b-lock-recheck` (12a02485). Real-uv behaviour is NOT verified (uv is not installed on the preparing machine). No script is changed on that branch.
- The RANGE-002 guard-removal PR candidate (`ci/range002-remove-hashfiles-guards-v2`, 4cb14752) now also drops `--allow-pending`.

### 0.3 Packaging: revised recommendation

v0.1 recommended ONE PR for both fixes to save one global FULL run. Revised, Recommendation (not a decision): **TWO narrow PRs, A first, then B, neither combined with any RANGE-002 PR.**

| Order | PR | Contents | Why separate | Cost |
|---|---|---|---|---|
| 1 | Fix A (and optionally alert L2) | `ci.yml` one-line env gating (A1) plus the section 2.4 tests (formatted by ruff). Optionally the L2 notify job if the owner wants it. | Certain, mechanical, no owner policy question and no tool I cannot run here. It restores the nightly `Detect changes` and therefore the nightly Gate and all four FULL suites, which are currently not running at all. Waiting for B would keep that coverage off. | One global FULL (about 30-35 runner minutes, per GITHUB-OPS-001 practice; this is the repository figure, not remeasured) plus the RANGE-002 step. |
| 2 | Fix B | `scripts/check_dependency_locks.py` header stripping plus preference seeding (B2), new `tests/ci/test_check_dependency_locks.py`, runbook wording. Constraints files unchanged for B2. | Has open prerequisites: the owner's policy decision (B2 reproducibility guard vs B3 dated byte-identity), local verification of uv 0.12.0 behaviour on Linux x86_64 CPython 3.12.13 (V0), and possibly regenerating all four lock files if B3 is chosen. It must not hold fix A back. | A second global FULL (about 30-35 runner minutes). |

Cost of splitting versus v0.1's single PR: one extra global FULL run (about 30-35 runner minutes). If the owner prefers the lower cost, bundling is still safe only AFTER B's V0 verification is green on Linux; the order of landing inside one PR is irrelevant. Remaining pushes per PR: 1 each (GITHUB-OPS-001: 1-3 per work item). Consequential-PR walk-away of at least 2 hours applies to both (CI-gating change).

Sequencing with the RANGE-002 guard-removal PR: no dependency in either direction. Merge them one at a time. Suggested order, Recommendation (not a decision): fix A, then guard removal, then fix B, so that fix B is verified against a nightly baseline that already passes `Detect changes`. (The RANGE-002 step does not run on nightlies: a `schedule` event is neither `pull_request` nor `workflow_dispatch`; that is intended.)

After fix A merges, expect the first healthy nightly to run all four FULL suites for the first time since 2026-08-29; new red results there are real signals to triage separately (risk 1 below).

---

## 1. Summary

Two independent, mechanical defects keep every scheduled `CI` run red since 2026-08-30 (about 40 consecutive nightlies). Neither is reachable from a pull request.

| | Defect A: `Detect changes` / Classify step | Defect B: `Fresh resolution proof (uncached)` |
|---|---|---|
| Root cause | `CHANGED_FILES_JSON` env var is set on every event. On `schedule` (no `before` in the payload) `dorny/paths-filter` returns the whole tree (2,448 tracked files, 137,163 bytes as compact JSON here), which exceeds Linux `MAX_ARG_STRLEN` (131,072 bytes per env string). The runner cannot exec bash: `Argument list too long`. The value is never read on non-PR events. | `check_dependency_locks.py --recompile` compares `uv pip compile --no-header` output byte-for-byte with committed files that begin with a 19-line generated header, so equality is impossible. Separately the compile is unconstrained, so upstream drift (anthropic 1.13.0 vs committed 0.120.2) would still differ after the header is handled. |
| Since | 2026-08-30 (repo growth past the limit) | #543, 2026-07-29 (never passed) |
| Blast radius today | Fails `Detect changes`, so `Python CI Gate` fails closed on schedule and all test jobs are skipped. | Fails only that job (not in any `needs`). It also masks its own next step: the clean `--require-hashes` install of all four projects never runs, because the step before it fails. |
| Recommendation (not a decision) | Option A1: export the env var only on `pull_request` (one-line workflow change), plus tests that pin the behaviour. | Option B2 (with B1's header stripping as its first half): strip the header AND seed `uv pip compile` with the committed pins as preferences, so the proof asserts "the committed graph is still a valid, reproducible resolution of the manifests" without chasing upstream. |

Recommended packaging (not a decision) - REVISED in v0.2, see section 0.3: two narrow PRs, fix A first, then fix B (v0.1 recommended one PR; it saved one global FULL run, about 30-35 runner minutes, but coupled a certain one-line fix to an unresolved policy and tooling question). Both PRs touch GLOBAL classifier paths (`ci.yml`; `scripts/check_dependency_locks.py`), so each is a full FULL run.

## 2. Defect A: `Argument list too long` in Classify changes

### 2.1 Facts from the code

- `changes` job, step `Classify changes (per-project FULL?)`: `env: CHANGED_FILES_JSON: ${{ steps.filter.outputs.all_files }}` for every event.
- The script reads that variable only inside `if [ "$GITHUB_EVENT_NAME" = "pull_request" ]`; the `else` branch hard-codes `backend_code=true ... adr0043_gate=true`.
- `pull_request`: `all_files` is the PR diff (small). `push`: the pushed commits' diff (small). `schedule`: no `before` in the payload, so the filter falls back to "last commit" and reports every file as added.
- Measured size here: 2,448 files, 137,163 bytes (compact JSON). The repository only grows, so the failure does not self-heal. Last green scheduled run #1692 was at about 130.8 kB; first red #1710.
- `workflow_dispatch` also has no `before`, so it very likely reproduces the same failure (to verify). This is also why a dispatch is a faithful equivalent for verification.

### 2.2 Options compared

| Option | Change | Blast radius | Classifier pure-function contract | Cost | Risk |
|---|---|---|---|---|---|
| A1 (recommended) | Pass the list only on `pull_request`: `CHANGED_FILES_JSON: ${{ github.event_name == 'pull_request' && steps.filter.outputs.all_files \|\| '[]' }}` | One line in `ci.yml`. PR and push behaviour provably unchanged (PRs get the identical string; non-PR code never read it). | Unchanged (Python untouched). | One FULL run of all four projects (ci.yml is GLOBAL), same as any ci.yml edit. | Very low. Edge: on a PR where `all_files` is empty, the expression yields `'[]'`; before, it yielded `''`, which the classifier already turns into `[]` (`raw.strip() or "[]"`). Identical result. |
| A1b | A1 plus `list-files: ${{ github.event_name == 'pull_request' && 'json' \|\| 'none' }}` on the paths-filter step, so the large output is never produced on non-PR events | Two lines. | Unchanged. | Same. | Low. `none` is a documented `list-files` value (to verify against the pinned dorny/paths-filter@v3 README). More surface than A1 for no extra safety. |
| A2 | Add `--event <name>` to `ci_classify_changes.py`; for `schedule`/`push`/`workflow_dispatch` the CLI prints all-true without reading input; the workflow always calls the CLI | Workflow plus classifier. Moves the "everything FULL" rule from bash into the unit-tested module (a real benefit). | Extended (new argument and code path); existing `classify()`/`requires_*()` unchanged. | Same. | Medium-low. By itself it does NOT fix the defect: the failure is at process start, so the env var must still be gated (A1). |
| A3 | Pass the list through a file on disk | `dorny/paths-filter` has no file output, so this needs a new diff/API step replacing `list-files`, with its own base-SHA logic. | Unchanged. | Same. | Highest: re-implements the action for a case (non-PR) that does not need the list at all. |
| A4 | Cap or zip the list | Touches classifier input handling. | Changed. | Same. | Rejected: truncation can drop a GLOBAL path and silently under-classify, the failure direction the classifier is built to avoid; compression only moves the threshold. |

Recommendation (not a decision): A1. It is the smallest change that removes the cause (an unused value being exported), it cannot change PR or push classification, and it leaves the classifier untouched. A1b is an optional extra. A2's "schedule resolves to all FULL" test intent is achieved without code change by executing the real step script in tests (section 2.4).

### 2.3 Exact proposed diff (A1)

```diff
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -137,10 +137,14 @@
       # error exits non-zero here, failing this job so `Python CI Gate` fails closed.
       #
       # SECURITY: the changed-file list is PR-controlled (untrusted). It is passed via an ENV VAR and
       # written to a file — NEVER interpolated into the shell command — so a hostile filename (quotes,
       # $(...), backticks, newlines) cannot alter the command. The classifier treats filenames as data.
+      #
+      # SIZE: the list is exported ONLY on pull_request. On schedule/dispatch (no `before` in the payload)
+      # it is the whole tree (~137 kB), which exceeds the Linux 131,072-byte per-env-string limit and
+      # made the runner fail with `Argument list too long` before the script started (nightlies red since
+      # 2026-08-30). Non-PR events never read it (they are FULL for every project by rule).
       - name: Classify changes (per-project FULL?)
         id: classify
         env:
-          CHANGED_FILES_JSON: ${{ steps.filter.outputs.all_files }}
+          CHANGED_FILES_JSON: ${{ github.event_name == 'pull_request' && steps.filter.outputs.all_files || '[]' }}
         run: |
```

Hunk line numbers are indicative; apply by context. Everything else in the step, including the `else` branch, is unchanged.

Known latent limit, out of scope (Recommendation: record, do not fix now): a single PR changing roughly 2,000+ files would also exceed 131,072 bytes and the step would fail closed with the same error. It fails safe (gate red), and no PR in the history approaches it.

### 2.4 Tests (proposed text, not applied)

Proposed: append to `apps/backend/tests/ci/test_ci_classify_changes.py` (or a sibling `test_ci_workflow_classify_step.py`).

```python
import os
import shutil

REPO_ROOT = Path(__file__).resolve().parents[4]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _classify_step() -> dict:
    import yaml  # pyyaml is pinned in constraints/backend-py312.txt (transitive); fail loudly if missing

    wf = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    steps = wf["jobs"]["changes"]["steps"]
    return next(s for s in steps if s.get("id") == "classify")


def _run_step(tmp_path, event, files_json):
    out = tmp_path / f"gh_output_{event}"
    out.write_text("")
    env = {**os.environ, "GITHUB_EVENT_NAME": event, "GITHUB_OUTPUT": str(out),
           "RUNNER_TEMP": str(tmp_path), "CHANGED_FILES_JSON": files_json}
    proc = subprocess.run(["bash", "-c", _classify_step()["run"]], cwd=REPO_ROOT, env=env,
                          capture_output=True, text=True)
    return proc, out.read_text()


def test_classify_env_is_only_exported_on_pull_request():
    # Regression for the nightly `Argument list too long`: on schedule/dispatch the whole-tree list
    # must never reach the step environment.
    expr = _classify_step()["env"]["CHANGED_FILES_JSON"]
    assert "github.event_name == 'pull_request'" in expr
    assert expr.rstrip().endswith("|| '[]' }}")


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize("event", ["schedule", "workflow_dispatch", "push"])
def test_non_pr_events_resolve_to_all_projects_full(tmp_path, event):
    proc, out = _run_step(tmp_path, event, "[]")  # what the fixed expression yields on non-PR events
    assert proc.returncode == 0, proc.stderr
    assert set(out.split()) == {
        "backend_code=true", "mcp_server_code=true", "mcp_workbench_code=true",
        "agent_code=true", "adr0043_gate=true",
    }


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize("files,backend", [(["docs/x.md"], "false"), (["apps/backend/app/x.py"], "true")])
def test_pull_request_event_still_uses_the_classifier(tmp_path, files, backend):
    proc, out = _run_step(tmp_path, "pull_request", json.dumps(files))
    assert proc.returncode == 0, proc.stderr
    assert f"backend_code={backend}" in out


def test_classifier_cli_accepts_a_list_larger_than_the_env_limit(tmp_path):
    # Same entry point the workflow uses (argv file path). The classifier has no size limit; the limit
    # was only ever the env var.
    paths = [f"apps/frontend/src/generated/file_{i:05d}.ts" for i in range(4000)]
    payload = json.dumps(paths)
    assert len(payload.encode()) > 131_072
    f = tmp_path / "big.json"
    f.write_text(payload)
    proc = subprocess.run([sys.executable, str(CLASSIFIER), str(f)], capture_output=True, text=True)
    assert proc.returncode == 0
    assert "backend_code=false" in proc.stdout  # frontend-only list: LIGHT


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="MAX_ARG_STRLEN is a Linux limit")
def test_premise_a_single_env_string_over_131072_bytes_cannot_exec():
    # Pins WHY the env var is gated, so nobody "simplifies" the expression back.
    with pytest.raises(OSError):
        subprocess.run(["bash", "-c", ":"], env={"X": "a" * 140_000}, check=False)
```

Notes: the first test checks the expression text because `${{ }}` is evaluated by GitHub, not bash; the next tests execute the real `run:` script from `ci.yml` under bash, so they track any later edit of the step. The `yaml` import must be confirmed available in the backend CI environment; if it is only transitive, import it without `importorskip` so a missing module fails loudly rather than silently skipping a gating test. All tests are offline and fast. The big-list CLI test shows the classifier is not the limiting component; it does not by itself reproduce the env-var failure (the Linux premise test and the step-script tests cover that).

### 2.5 Behaviour matrix after the fix

| Event | Env var value | Classify step result | Downstream |
|---|---|---|---|
| `pull_request` | PR diff list (as today) | classifier runs (as today) | unchanged |
| `push` (main) | `'[]'` (never read) | hard-coded all-true (as today) | unchanged |
| `schedule` | `'[]'` | hard-coded all-true | `Detect changes` succeeds; all four FULL suites and the Gate run again |
| `workflow_dispatch` | `'[]'` | hard-coded all-true | as schedule |

## 3. Defect B: Fresh resolution proof can never pass

### 3.1 What the proof is meant to guarantee

From the job comment in `ci.yml` and the runbook: the repository "can still be built from the committed resolution in a clean environment, and re-resolving reproduces the committed files byte-for-byte"; it is "the one that is not served from a cache, so a drifted or unbuildable locked graph cannot hide behind a warm cache". The #543 commit says the lock is a prerequisite for environment caching (a cache key over non-deterministic resolution is unsound). So the load-bearing guarantees are: (1) the committed files are what installs, complete and hash-bearing; (2) they still correspond to the manifests; (3) they still install from the index in a clean environment. Byte-identity against a fresh unbounded resolve was the mechanism chosen, but no `--exclude-newer`, date or index snapshot is recorded anywhere (the header records python, platform and uv version only), so the stated byte-for-byte reproducibility cannot hold over time even with a correct comparator.

### 3.2 Mechanism (code-level, no uv needed)

- `recompile_one()` always passes `--no-header` and writes to a fresh temp path, so uv starts with no preferences.
- `main()` compares `out.read_text()` with `constraints/<p>-py312.txt`, which starts with the 19 header lines from `regenerate_dependency_locks.header()`. Unequal for any content.
- After header handling, a fresh unconstrained resolve takes the newest allowed versions, so any upstream release since generation makes the files differ.
- No unit tests exist for `check_dependency_locks.py` (it is only named in the classifier tests as a GLOBAL path). The `--recompile` path has never been exercised by a test.

### 3.3 Options

| Option | What it asserts | Lock regeneration needed? | Residual weakness | Policy question |
|---|---|---|---|---|
| B1: strip the header, compare bodies | A fresh unconstrained resolve equals the committed pins | No | Red whenever any upstream release lands (near-daily). Fixes the structural bug only. | Is a nightly that is red on every upstream release acceptable signal? |
| B2: seed uv with the committed pins as preferences (strip header, write the committed body to the temp output path before compiling; uv treats an existing output file as preferred versions when `--upgrade` is absent), then compare bodies | "The committed graph is still a valid resolution of the manifests: a non-upgrading re-resolve reproduces it exactly." Catches manifest/lock mismatch, a pin that became unresolvable or yanked, hash changes for a pinned version. | No | Does not flag "newer upstream exists" (by design; the monthly refresh PR owns that). | Is the nightly an upgrade-detector or a reproducibility guard? B2 chooses the latter. |
| B3: `--exclude-newer <date>` recorded in the lock header | True byte-identity, stable over time (re-resolution as of the recorded date) | YES: header and generator change, so all four files regenerate in one reviewed PR; a cutoff date must be chosen | Relies on index metadata and hashes for pre-cutoff releases staying immutable (yanks aside). Adds a field to the governed tuple. | Which cutoff rule? Accept a new header field? |
| B4: re-scope to "resolves and installs" (e.g. `uv pip install --dry-run --require-hashes -r constraints/x`) | Weakest: buildability only | No | Does not detect lock body vs. re-resolution drift. The clean-install step already does the real install. | Is buildability alone enough? |

Recommendation (not a decision): B2, with B1's header stripping as its necessary first half. It matches the stated purpose (cache soundness: the committed graph is reproducible and valid), needs no lock regeneration (constraints/ stays unchanged), removes the upstream-drift flake, and keeps a real byte comparison. B3 is the stricter long-term alternative and a deliberate owner choice because it changes the governed tuple. Whichever is chosen, the runbook wording should state exactly what is compared.

To verify before implementation (uv not available here): (a) that uv 0.12.0 `uv pip compile` with an existing `--output-file` reuses its pins as preferences when `--upgrade` is absent and `--no-header` is set; (b) that the result is byte-identical to the committed body for all four projects (hashes and `# via` comments included) on Linux x86_64 with CPython 3.12.13 (the governed tuple; Windows output may differ). If (a) or (b) fails, fall back to B3.

### 3.4 Exact proposed diff (B1 + B2)

```diff
--- a/scripts/check_dependency_locks.py
+++ b/scripts/check_dependency_locks.py
@@
-  6. With ``--recompile`` (nightly / on demand, needs network + uv): re-resolve and require
-     the output to be byte-identical to what is committed.
+  6. With ``--recompile`` (nightly / on demand, needs network + uv): re-resolve WITHOUT
+     upgrading (the committed pins seed the resolver as preferences) and require the body to be
+     byte-identical to the committed body (the generated header is excluded from the comparison).
+     This proves the committed graph is still a valid, reproducible resolution of the manifests;
+     it deliberately does not flag newer upstream releases (the monthly refresh owns those).
@@
 PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)", re.M)
 BACKSLASH = chr(92)
 
 
+def strip_header(text: str) -> str:
+    """Drop the leading generated header (comment and blank lines before the first pin).
+
+    ``regenerate_dependency_locks.header()`` prepends a block of ``#`` lines; ``uv pip compile
+    --no-header`` does not emit one. Per-pin ``# via`` comments are indented, so they are never
+    treated as header."""
+    lines = text.splitlines(keepends=True)
+    i = 0
+    while i < len(lines) and (not lines[i].strip() or lines[i].startswith("#")):
+        i += 1
+    return "".join(lines[i:])
+
+
 def norm(name: str) -> str:
@@
-def recompile_one(project: str, directory: str, out: Path) -> tuple[bool, str]:
+def recompile_one(project: str, directory: str, out: Path, seed: str | None = None) -> tuple[bool, str]:
+    if seed is not None:
+        # uv treats an existing output file as preferred versions (no --upgrade passed), so a
+        # re-resolve reproduces the committed pins instead of drifting to newer releases.
+        out.write_text(seed, encoding="utf-8")
     cmd = [
@@
-                ok, why = recompile_one(project, directory, out)
+                committed_body = strip_header(constraints_path(project).read_text(encoding="utf-8"))
+                ok, why = recompile_one(project, directory, out, seed=committed_body)
                 if not ok:
                     errors.append(f"{project}: {why}")
                     continue
-                committed = constraints_path(project).read_text(encoding="utf-8")
-                if out.read_text(encoding="utf-8") != committed:
+                if out.read_text(encoding="utf-8") != committed_body:
                     errors.append(
                         f"{project}: re-resolution DIFFERS from the committed file — "
                         "the committed graph is not reproducible; regenerate and review the diff"
                     )
```

Runbook (`docs/runbook/dependency-locks.md`, Verification section): replace "re-resolution differing from what is committed" with "a non-upgrading re-resolution (committed pins as preferences, header excluded) differing from what is committed". No change to `regenerate_dependency_locks.py`, `constraints/*`, or the workflow job for B2 itself.

### 3.5 Tests (proposed new file `apps/backend/tests/ci/test_check_dependency_locks.py`)

The root `scripts/` package is not on the backend import path, so load the module by file path.

```python
import importlib.util
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location(
    "check_dependency_locks", REPO_ROOT / "scripts" / "check_dependency_locks.py")
cdl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cdl)

BODY = "foo==1.0 \\\n    --hash=sha256:" + "a" * 64 + "\n    # via bar\n"
HEADER = "# GENERATED FILE - DO NOT EDIT BY HAND.\n#\n# more header\n#\n"


def test_strip_header_removes_only_the_leading_block():
    assert cdl.strip_header(HEADER + BODY) == BODY


def test_strip_header_is_identity_without_a_header():
    assert cdl.strip_header(BODY) == BODY


def test_strip_header_keeps_indented_via_comments():
    assert "    # via bar" in cdl.strip_header(HEADER + BODY)


@pytest.mark.parametrize("project", sorted(cdl.PROJECTS))
def test_every_real_committed_file_strips_to_its_first_pin(project):
    body = cdl.strip_header(cdl.constraints_path(project).read_text(encoding="utf-8"))
    assert cdl.PIN_RE.match(body), "header stripping must land exactly on the first pinned package"


def test_recompile_seeds_uv_with_the_committed_body_and_never_upgrades(monkeypatch, tmp_path):
    seen = {}

    def run(cmd, **kwargs):
        out = Path(cmd[cmd.index("--output-file") + 1])
        seen["seed"] = out.read_text(encoding="utf-8")
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(cdl.subprocess, "run", run)
    ok, _ = cdl.recompile_one("backend", "apps/backend", tmp_path / "o.txt", seed=BODY)
    assert ok and seen["seed"] == BODY
    assert "--upgrade" not in seen["cmd"] and "-U" not in seen["cmd"]
    assert "--no-header" in seen["cmd"]


def test_recompile_without_seed_does_not_touch_the_output_path(monkeypatch, tmp_path):
    monkeypatch.setattr(cdl.subprocess, "run",
                        lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, "", ""))
    out = tmp_path / "o.txt"
    cdl.recompile_one("backend", "apps/backend", out)
    assert not out.exists()
```

Not written out: end-to-end `main(["--recompile"])` tests (header-only difference passes; a moved pin fails with "re-resolution DIFFERS"). `main()` interleaves the structural checks with the recompile loop, so these are awkward to test directly. A small behaviour-preserving refactor (extract the loop into `check_recompile(read_committed, compile_fn) -> list[str]`) would make them straightforward; the diff in 3.4 deliberately omits it to stay minimal. This is owner decision 7.

Local run: `uv run pytest tests/ci -q` from `apps/backend`, plus `ruff check` and `ruff format --check` on the new files. Also run `python scripts/check_dependency_locks.py` (offline structural gate) to confirm it still passes.

## 4. Effect on required checks

| Check | Before | After the fixes | Notes |
|---|---|---|---|
| `Python CI Gate` on `pull_request` | Required | UNCHANGED. The gate job script is not edited. Classifier input on PRs is byte-identical (A1) and `ci_classify_changes.py` is untouched. Fix B edits a script that PR CI runs only in its offline form (`python scripts/check_dependency_locks.py`, no `--recompile`), whose logic is unchanged apart from added helpers; `--recompile` runs only in the schedule/dispatch-only job. | The PR that lands these changes is itself FULL for all four projects (ci.yml and the lock scripts are GLOBAL paths). |
| `Python CI Gate` on `push` main | Green | Unchanged. | |
| `Python CI Gate` on `schedule` | Red since 2026-08-30 (fails closed on `changes_result != success`) | Meaningful again: `Detect changes` passes, then all four LIGHT and FULL suites run and the Gate reports their real result. | First run executes pytest + coverage for all four projects after about 40 days of not doing so (see risks). |
| `Fresh resolution proof (uncached)` | Always red; not in any `needs` | Passes iff the committed graph reproduces under a non-upgrading re-resolve and then installs cleanly. | Not a required check. |

## 5. Verification plan (against a real scheduled run or equivalent)

This document does no dispatch, rerun or push. Options and cost:

| Option | What it proves | Cost | Owner approval needed |
|---|---|---|---|
| V0 local, before any push | Defect A: the section 2.4 tests (step-script tests run under Git Bash on the laptop; the Linux-only premise test in WSL or CI). Defect B: `python scripts/check_dependency_locks.py --recompile` on Linux x86_64 with CPython 3.12.13 and `uv==0.12.0` (WSL or a throwaway container; Windows output may differ, and Norton TLS inspection may block the index since the checker has no `--system-certs` option). | Zero Actions minutes. | No |
| V1 `act`-style simulation | Not recommended. `act` cannot faithfully reproduce the `schedule` payload or `dorny/paths-filter` API behaviour, which is the root of defect A. The size-limit premise is directly reproducible in WSL with one 140,000-byte env var, which V0 already covers. | Setup time only. | No |
| V2 the PR's own CI run | Proves the `pull_request` path is unchanged (classifier runs, Gate behaves as today). Does NOT exercise the schedule path or the fresh job (both skipped on PRs). | One FULL+LIGHT run of all four Python projects, about 30-35 runner minutes (ci.yml is GLOBAL). Unavoidable for any ci.yml edit. | No (normal PR) |
| V3 `workflow_dispatch` on the fix branch | Closest equivalent to a scheduled run: dispatch has no `before` either, so the old workflow fails identically; it also runs `fresh-resolution-proof`, FULL for all four, and rebuilds all five images. | About 30-35 min FULL, plus five image builds (not measured here), plus the fresh job (20 min timeout). Roughly double V2. | YES, explicit |
| V4 the next scheduled run on main after merge (07:00 UTC) | The real thing. | No extra cost beyond the run that happens anyway. | No. If red, a second fix PR is needed. |

Recommendation (not a decision), minimising pushes per GITHUB-OPS-001:
1. Build each fix and its tests locally; run V0 until green (format tests with `ruff format`). This is the "validate locally first" rule and replaces most of V3's value at zero cost.
2. Push ONCE per PR and open that PR (V2); fix A first (see section 0.3). Observe the 2-hour walk-away while re-reading the final diff.
3. If the owner wants evidence before merge, run a single V3 dispatch on the branch after explicit approval. If V0 was fully green on a Linux environment, V3 can reasonably be skipped.
4. Merge; the post-merge push run is the normal FULL; then confirm with V4 (next 07:00 UTC schedule).
Total pushes: 1 per PR (policy: 1-3 per work item). Total extra Actions cost versus doing nothing: one FULL run per PR (two PRs in v0.2), plus an optional single dispatch.

## 6. Alerting for scheduled failures

About 40 consecutive nightly failures went unnoticed. Options within the cost policy (proposal only; nothing is configured here):

| Option | Mechanism | Cost | Notes |
|---|---|---|---|
| L1 (lightest) | Owner notification setting: GitHub Settings > Notifications > Actions, "Send notifications for failed workflows only", via email and/or web. GitHub sends scheduled-workflow failure notices to the account that last modified the cron line. History shows that is `jayw04` (commit 5f0fb9b0, #320, 2026-07-02), so the owner account's own notification settings decide whether anything was delivered. | Zero Actions minutes, zero code. | Verify the setting and where the email goes; check for mail filters. GitHub also disables scheduled workflows after 60 days of repository inactivity, which this setting would not announce (to verify). |
| L2 | Add a small `notify-on-scheduled-failure` job to `ci.yml`: `needs: [python-ci-gate, fresh-resolution-proof]`, `if: failure() && github.event_name == 'schedule'`, job-level `permissions: issues: write`, opens or comments on one labelled issue ("Nightly CI red") via `gh issue`. | A few seconds of runner time on a failing nightly (about 0.1 runner minute); none when green. | A workflow edit; it can ride in the same ci.yml PR at no extra push. Adds one job-scoped permission. De-duplicate by searching for an open issue first so a long outage is one issue, not forty. It is a job, not a new scheduled workflow. |
| L3 | Periodic human or agent review of `gh run list --event schedule`. | None in Actions. | Depends on a person remembering, the failure mode that already occurred. |

Recommendation (not a decision): L1 now (zero cost, can be done today), and L2 only if the owner wants a repo-visible record; if chosen, include it in the same ci.yml PR.

## 7. Risks

1. Un-hiding the suites: once `Detect changes` passes, the nightly runs FULL for all four projects for the first time since 2026-08-29. Latent date-pinned or environment-sensitive failures (the class seen in run #1488, partly fixed by #735) may appear. These are real signals, not regressions caused by the fix; the first healthy nightly or dispatch may be red for different reasons and should be triaged as separate items.
2. The clean-install step of the fresh job has never run on any nightly because the preceding step always failed. Its first execution (four `pip install --require-hashes` installs, 20 minute timeout) may expose an independent problem (hash availability, platform wheels).
3. B2 depends on uv preferring the existing output file's pins. Unverified here (no uv). If wrong, the proof stays red on upstream drift. Mitigation: the V0 gate; fallback B3.
4. B2 narrows what the nightly detects (it no longer flags "newer upstream exists"). Intentional, but a policy change; it needs an explicit owner decision and a runbook edit.
5. A1 changes only the value of an env var that non-PR code never reads; the only way it harms is a typo in the expression. The section 2.4 tests execute the real step script under each event to guard that. The `a && b || c` idiom returns `c` when `b` is an empty string; shown equivalent for the PR case in 2.2.
6. The ci.yml edit is GLOBAL: it flags every project FULL (and the `range002` filter, since ci.yml is in its pattern), so the PR consumes a full run. Combining it with any RANGE-002 PR would couple an unrelated CI change to a RANGE-002 review and force RANGE-002 evidence to be re-derived; hence keep separate.
7. The latent PR-side limit (a PR of 2,000+ changed files hits the same env limit) remains; it fails closed.
8. This proposal touches the CI gating path. No architectural or CI invariant (single router, risk coverage, audit immutability, no-LLM-in-order-path, etc.) is touched or weakened, and no migration, security safeguard or cooldown is affected.

Walk-away note: this is a CI-gating change. Recommendation (not a decision): hold the implementation PR open for at least 2 hours between "ready for review" and merge (the consequential-PR tier), re-read the final `ci.yml` diff after the break, and do not merge on the strength of the PR run alone if the owner wants V3.

## 8. Owner decisions (blank for the owner to fill)

| # | Decision | Options | Owner decision | Date |
|---|---|---|---|---|
| 1 | Defect A fix | A1 (recommended) / A1b / A2+A1 / other | | |
| 2 | Defect B policy: what does the nightly guarantee? | Reproducibility guard (B2, recommended) / upgrade detector (B1) / strict dated byte-identity (B3) / buildability only (B4) | | |
| 3 | If B3: cutoff date rule and header field | e.g. generation date; regenerate all four files in one PR | | |
| 4 | Packaging | Two PRs, A then B (recommended in v0.2) / one PR for A+B (v0.1 recommendation, lower cost, only after B's V0 is green) | | |
| 5 | Pre-merge verification | V0 only / V0 + one V3 dispatch (explicit approval) / V4 only | | |
| 6 | Alerting | L1 only / L1+L2 (issue-on-failure in the same PR) / other | | |
| 7 | Refactor `check_dependency_locks.main()` so the recompile loop is unit-testable | Yes / No | | |
| 8 | Walk-away duration for the implementation PR | 2 h (recommended) / other | | |
| 9 | Triage owner for newly visible FULL failures on the first healthy nightly | | | |
