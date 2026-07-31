# Deterministic dependency resolution — design and interpreter inventory

**GITHUB-OPS-001.** Design phase only; no implementation in this document.
Baseline `eb78365` (main, after #540).

Prerequisite for environment caching (deferred: a cache key over non-deterministic resolution is
unsound). Standalone value: prevents a repeat of the 2026-07-28 `mcp 2.0.0` outage, which took main
red for ~21 hours from one unbounded lower bound.

---

## 1. Interpreter inventory (measured, not inferred)

| Project | Declared `requires-python` | Actual CI interpreter | Runtime / deployment | Extras installed by CI |
|---|---|---|---|---|
| `backend` | `>=3.11` | **CPython 3.12.13**, ubuntu-latest x64 | `python:3.12-slim` | `[dev]` |
| `mcp-server` | `>=3.11` | **CPython 3.12.13**, ubuntu-latest x64 | `python:3.12-slim` | `[dev]` |
| `mcp-workbench` | `>=3.11` | **CPython 3.12.13**, ubuntu-latest x64 | `python:3.12-slim` | `[dev]` |
| `agent` | `>=3.12` | **CPython 3.12.13**, ubuntu-latest x64 | `python:3.12-slim` | `[dev]` |

Sources: `requires-python` from each `pyproject.toml`; CI interpreter from
`.github/workflows/ci.yml` (`python-version: "3.12"`, both `python-checks` and `python-full`)
resolved on the runner to `hostedtoolcache/Python/3.12.13` — read from run 30466252331's log;
runtime from `ARG PYTHON_VERSION=3.12-slim` in all four Dockerfiles, with no compose override;
extras from `pip install -e ".[dev]"` at ci.yml:243 and :373.

### Findings

**F1 — All four projects resolve under one interpreter.** CI and runtime are both CPython 3.12.
The Python-version axis therefore does *not* force separate files. Per the ruling, separation must
still follow **dependency-graph divergence**, not interpreter match — and the graphs do diverge
(backend carries FastAPI/SQLAlchemy/Alembic/alpaca-py/APScheduler; the MCP projects carry a small
client stack; agent carries `anthropic` + FastAPI). **Recommendation: per-project files.** Any
shared layer must be an intentionally governed common constraints file, not an inference from
matching Python versions.

**F2 — The CI interpreter patch floats.** `python-version: "3.12"` resolves to whatever patch the
runner image currently ships (3.12.13 today). A committed resolution is only valid for the
interpreter that produced it; a runner-image bump silently changes the environment the lock is
supposed to reproduce. **Recommendation: pin the exact patch in `ci.yml`** (`python-version:
"3.12.13"`) as part of the locking PR, and record that version inside each generated file. Without
this, "two clean resolutions produce identical versions" is only true until GitHub updates the
image.

**F3 — `requires-python >=3.11` is untested and undeployed.** `3.11` appears **nowhere** in
`ci.yml` or any Dockerfile. Three projects advertise 3.11 support that is never exercised and never
shipped. This matters for locking: a resolution generated on 3.12 is *not* valid for 3.11, so the
declaration and the locked artifact would disagree. **Two honest options — owner's call, and
deliberately NOT bundled into the locking PR:**
   - narrow the declaration to `>=3.12`, matching CI and runtime (cheap, truthful); or
   - add a 3.11 CI matrix and generate 3.11 resolutions too (costs runner minutes on every job —
     directly against the cost programme).

**F4 — Dev extras are load-bearing.** CI installs `.[dev]`, so every project's `pytest`,
`pytest-asyncio`, `pytest-cov`, `pytest-httpx`, `ruff`, and `mypy` are part of the environment
under test — all declared as open lower bounds. A resolution covering only runtime dependencies
would leave CI partially uncontrolled. **Locked files must include the dev graph.** Note this also
means a `ruff` or `mypy` release can change CI outcomes today with no repository change.

**F5 — No existing resolution artifact.** No `uv.lock`, no `poetry.lock`, no `requirements*.txt`,
no `constraints/`. Starting from zero. `uv.lock` is *already* listed in the classifier's
`GLOBAL_PATTERNS`, so a lockfile at that path will correctly force FULL for every project the day
it lands — no classifier change needed.

---

## 2. Resolver options

Neither `uv` nor `pip-tools` is currently installed locally; either must be introduced.

| | `uv pip compile` → pinned `.txt` | `uv` native workspace lock | `pip-tools` |
|---|---|---|---|
| Output | pip-compatible pinned file, `--generate-hashes` | `uv.lock` | pinned `.txt` |
| CI install change | `pip install -r <file> -e . --no-deps` | `uv sync` | same as uv-compile |
| Blast radius | **small** — CI keeps pip | large — replaces install path in 8 jobs | small |
| Multi-project | one file per project, explicit | workspace-oriented, assumes one root | one file per project |
| Speed | fast resolve, unchanged install | fastest | slow resolve |

**Recommendation: `uv pip compile` producing per-project pinned files with hashes.** It gives
deterministic, hash-verified resolution while leaving the CI install path on `pip` — the smallest
change that satisfies the acceptance criteria. Full `uv sync` adoption is a larger migration and
should not ride along with the first locking PR. CLAUDE.md already names `uv` as backend tooling,
so this is consistent rather than a new dependency choice.

### Provisional layout

```
constraints/
  backend-py3.12.txt
  mcp-server-py3.12.txt
  mcp-workbench-py3.12.txt
  agent-py3.12.txt
```

Final names follow the selected resolver's semantics. Each file records, in a header comment: the
exact Python version and platform used for resolution, the source manifest, the extras included
(`dev`), and the regeneration command.

---

## 3. Scope for the first locking PR

**In scope**

1. Select the resolver and add it to CI.
2. Generate committed per-project resolved files covering runtime **and `[dev]`**.
3. Preserve current direct dependencies and the exact `mcp==1.28.1` pins — **no version changes**.
4. Make CI install from the committed files.
5. Pin the CI interpreter patch (F2) — required for the reproducibility claim to hold.
6. Drift check: changing a direct dependency without regenerating fails CI.
7. Document regeneration, update and rollback.
8. Prove two independent clean resolutions produce identical versions.
9. Keep every existing check unchanged; all four suites pass.
10. A **fresh-resolution job outside any cache path** — scheduled — proving the repository still
    builds from the committed resolution in a clean environment. Required now so it predates any
    future caching.

**Explicitly out of scope:** MCP 2.x migration · broad package upgrades · environment caching ·
classifier optimization · push-to-main changes · the F3 `requires-python` decision.

**Note on cost:** locking is a safety and reproducibility change, not a saving. It *enables* the
deferred caching evaluation. It will also make every dependency change visible as a reviewable diff
— which is the point.

---

## 4. Open questions for the owner

1. **F3** — narrow `requires-python` to `>=3.12`, or add a 3.11 matrix? Affects how many
   resolutions must be generated and maintained.
2. **Hash pinning** — `--require-hashes` is strictest but makes every local install stricter too.
   Adopt immediately, or land pinned-versions first and add hashes second?
3. **Scheduled refresh cadence** — weekly or monthly for the dependency-update PR? It must not
   auto-merge.
