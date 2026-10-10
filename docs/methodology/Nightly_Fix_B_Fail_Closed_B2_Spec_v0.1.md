# Nightly Fix B: Fail-Closed B2 Specification and B3 Comparison v0.1

Status: SPECIFICATION AND UNAPPLIED PATCH ONLY. Nothing in `scripts/` is changed on this branch. Prepared 2026-10-10 against `origin/main` d61f313a. Every recommendation is a Recommendation (not a decision).
Owner ruling being implemented: prefer B2 **only if it fails when reproducibility cannot be proven (missing evidence is never success)**; otherwise B3 (dated byte-identity) or return for another ruling.
Companion: `docs/methodology/CI_Nightly_Remediation_Proposal_v0.2.md` (defects A and B), patch `docs/methodology/patches/nightly_fix_b_option_b2_UNAPPLIED.patch.txt` (v2, fail-closed).

## 1. Verification status (read first)

| Claim | Status |
|---|---|
| The fail-closed logic, exit codes and messages in the patch | Implemented in the unapplied patch; **31 offline unit tests pass** locally (Windows, CPython 3.12.10, a fake `run` replaces uv). |
| `--recompile` without uv fails closed | **Observed**: with the patch applied temporarily, `python scripts/check_dependency_locks.py --recompile` printed `uv cannot be executed` and exited **11** (uv is not installed on this machine). The patch was then removed again. |
| uv 0.12.0 reuses an existing `--output-file` as preferred versions when `--upgrade` is absent | **NOT VERIFIED.** uv is not installed locally, nothing was installed, and no Linux environment was available. Stated from uv documentation as I know it. Must be proven by section 6 before the patch is applied. |
| A seeded re-resolution reproduces each committed body byte-for-byte on Linux x86_64 / CPython 3.12.13 | **NOT VERIFIED.** Same reason. |

No claim is made that B2 works against the real resolver until section 6 has been run on Linux.

## 2. What "reproducible" means under B2

For each governed project, take the committed constraints file, drop its generated header (leading `#` and blank lines before the first pin), and use the remaining body as the **seed**: write it to the temporary `--output-file` and run `uv pip compile` for the governed tuple (`--python-version 3.12`, `--python-platform x86_64-unknown-linux-gnu`, extras `dev`, `--generate-hashes`, `--no-header`), never passing an upgrade flag. The committed graph is **reproducible** iff the output body is byte-identical to the seed. In words: the committed pins are still a valid, complete resolution of the manifests, with the recorded hashes, and re-resolving does not move anything.

## 3. Behaviour table (every row except the first is a failure)

| Situation | Result | Exit code | Message (stderr) |
|---|---|---|---|
| Header-stripped committed body == seeded re-resolution body, all four projects | PASS | 0 | `dependency-lock gate OK (4 projects, structural + re-resolution parity)` |
| Structural check fails (existing checks 1 to 5) | FAIL (existing behaviour; recompile not attempted) | 1 | existing messages |
| Committed file missing / unreadable | FAIL | 10 | `committed constraints file is unavailable` |
| Committed body empty, header-only, or no `name==version` pins (absent or empty seed) | FAIL | 10 | `committed constraints body is empty or has no pins` |
| `uv` cannot be executed (not installed, not on PATH, permission) | FAIL | 11 | `uv cannot be executed: ...` |
| `uv --version` is not the governed version (0.12.0) | FAIL | 16 | `uv is '...', governed version is 0.12.0` |
| `uv pip compile` exits non-zero (resolver error, index unreachable, network failure, TLS interception) | FAIL | 12 | `uv pip compile failed: <first 300 chars of stderr>` |
| `uv pip compile` exceeds 600 s (or `uv --version` exceeds 60 s) | FAIL | 13 | `... timed out after 600s` |
| uv exits 0 but the output file is missing, unreadable, empty or has no pins | FAIL | 14 | `uv output is empty or has no pins` / `uv wrote no readable output` |
| Output body differs from the seed in any byte (a pin moved, hashes changed, a package added or removed, whitespace) | FAIL | 15 | `seeded re-resolution DIFFERS from the committed body - the committed graph is not reproducible; regenerate and review the diff` |

Rules: there is no SKIP and no soft-pass anywhere in the path; a network failure is deliberately indistinguishable from any other non-zero uv exit (code 12, message carries uv's own text) because guessing from stderr text would be a fail-open risk. With several failing projects, all are printed and the exit code is that of the first failure in project order. The existing `Fresh resolution proof (uncached)` job is not in any `needs` and not a required check, so a red result does not block merges, but it no longer reports green without proof.

## 4. Drift: what B2 gives up compared with B3

| Question | B2 (seeded, non-upgrading) | B3 (dated byte-identity) |
|---|---|---|
| New upstream releases appear | Do **not** fail: seeding preserves pins | Do not fail: resolution is bounded by the recorded cutoff date |
| What the nightly proves | The committed graph is internally valid and reproducible from itself against the live index today (hashes still served, pins still resolvable, manifests still satisfied) | A **fresh unseeded** resolution as of a recorded date equals the committed files, i.e. the lock is exactly what the generator would produce from the manifests at that date |
| Guarantee lost vs B3 | B2 cannot detect a committed body that is a valid but **different** resolution than a fresh one would give (for example a pin left behind at an old version that still satisfies the manifests; hand-edited but self-consistent pins). It also depends on uv's preference behaviour. | Not lost |
| Yanked or removed releases | Fail (code 12 or 15) | Fail |
| Hash changes for a pinned version | Fail | Fail |
| Needs lock regeneration | **No** | **Yes, all four files** |
| Header / governed tuple change | None | Adds an `exclude-newer` field to the header and to `regenerate_dependency_locks.py` and the structural header check; the governed tuple changes, so every file must be regenerated in one reviewed PR |
| Dependence on index immutability | Pin-level only | Relies on pre-cutoff release metadata not changing (yanks aside) |
| Policy question for the owner | Is "reproducible from itself" enough, with the monthly refresh owning freshness? | Which cutoff rule (for example generation date) and accepting a new governed field? |
| Cost | One script + tests PR (global classifier path: FULL for all four projects, about 30-35 runner minutes) | Same, plus regeneration of four large files and review of the diff (also global) |
| Fail-closed behaviour | Section 3 | Same table applies with the comparison changed to a fresh seedless resolve bounded by `--exclude-newer` |

Recommendation (not a decision): B2 is acceptable under the owner's condition because the patch is fail-closed (section 3); B3 is the stricter long-term alternative and should be chosen if the owner wants the lock proven to equal a fresh resolution rather than only self-consistent. If section 6 shows that uv does not reproduce the committed body when seeded, return for another ruling (B3) rather than loosening the comparison.

## 5. Offline unit tests (in the patch; 31 tests, all passing locally)

- Header stripping: removes only the leading block; identity without a header; keeps indented `# via` comments; every one of the four real committed files strips to its first pin.
- The one passing case: seeded re-resolution equal to the committed body passes; uv is seeded with the committed body, is never given `--upgrade`/`-U`/`--upgrade-package`/`-P`, always gets `--no-header` and `--generate-hashes`, and is run with the 600 s timeout.
- Negative cases, each asserting a distinct exit code: absent seed (None); empty, newline-only, header-only and whitespace seeds; seed without pins; uv missing; compile error with network-style stderr; timeout; empty output (`""`, newline, comment-only); output file removed; different resolution; whitespace-only difference.
- Exit codes are distinct, non-zero and never 0 or 1.
- uv version: governed version passes, another version fails (16), missing uv fails (11).
- `main()` wiring: the offline gate still returns 0; `--recompile` without uv returns 11; `--recompile` never returns 0 when every uv call fails.

## 6. What can only be verified on Linux with real uv (first run)

Environment: Linux x86_64 (WSL Ubuntu or a throwaway container), CPython 3.12.13, `uv==0.12.0`, network access to the package index (no TLS-inspecting proxy; this laptop's Norton inspection blocks some hosts). Run from a clean checkout of this branch; apply the patch with `git apply docs/methodology/patches/nightly_fix_b_option_b2_UNAPPLIED.patch.txt`. Expected results are predictions to confirm, not observations.

| # | Command | Expected |
|---|---|---|
| 1 | `uv --version` | `uv 0.12.0 (...)` |
| 2 | `python --version` | `Python 3.12.13` |
| 3 | `python scripts/check_dependency_locks.py; echo $?` | `dependency-lock gate OK (4 projects, structural (offline))`, `0` |
| 4 | `sed -n '/^[A-Za-z0-9]/,$p' constraints/backend-py312.txt > /tmp/seed.txt; cp /tmp/seed.txt /tmp/out.txt; uv pip compile apps/backend/pyproject.toml --extra dev --python-version 3.12 --python-platform x86_64-unknown-linux-gnu --generate-hashes --no-header --output-file /tmp/out.txt; diff /tmp/seed.txt /tmp/out.txt; echo $?` | `Resolved N packages ...` on stderr, empty diff, `0`. Repeat for `mcp-server`, `mcp-workbench`, `agent`. **If the diff is non-empty, stop: B2 does not hold; return for a B3 ruling.** |
| 5 | Control (shows why seeding is needed): same as 4 but without copying the seed, writing to a fresh path | A non-empty diff (newer upstream releases, for example anthropic) |
| 6 | `python scripts/check_dependency_locks.py --recompile; echo $?` | `dependency-lock gate OK (4 projects, structural + re-resolution parity)`, `0` |
| 7 | Negative, wrong pin: edit one pin in `constraints/backend-py312.txt` to an older release, rerun 6 (revert afterwards) | exit `15`, message `seeded re-resolution DIFFERS ...` (or `12` if the older release is unresolvable) |
| 8 | Negative, no uv: `PATH=/usr/bin:/bin python scripts/check_dependency_locks.py --recompile; echo $?` | exit `11` |
| 9 | Negative, no network (disable networking or use an unreachable `UV_INDEX_URL`): rerun 6 | exit `12` with uv's error text |
| 10 | Negative, empty seed: empty a copy of one constraints file | exit `10` |
| 11 | `cd apps/backend && uv run pytest tests/ci/test_check_dependency_locks.py -q` | all 31 pass |
| 12 | Cache and time: note wall-clock of 6 against the job's 20-minute timeout | recorded for the PR |

Only after rows 1 to 6 hold may the patch be applied as a real PR (global FULL run, 2-hour walk-away, merge not approved until then). Row 5 is evidence for the decision record, not a pass criterion. This specification does not change `docs/runbook/dependency-locks.md`; the real PR must reword its Verification section to "a non-upgrading, seeded re-resolution (header excluded)".

## 7. Owner decisions (blank)

| # | Decision | Options | Owner decision | Date |
|---|---|---|---|---|
| 1 | Policy for nightly defect B | B2 fail-closed (this spec) / B3 dated byte-identity / other | | |
| 2 | Accept that B2 cannot detect a valid-but-different committed resolution (section 4) | Yes / No (then B3) | | |
| 3 | Authorise a first Linux verification run (section 6) | Yes / No | | |
| 4 | If B3: cutoff-date rule and the new header field | e.g. generation date | | |
| 5 | Timeout value (default 600 s per project) | keep / change | | |
