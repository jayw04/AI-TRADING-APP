# Runbook — deterministic dependency resolution

Committed, hash-pinned resolutions for every Python project (GITHUB-OPS-001). Established after
the 2026-07-28 `mcp 2.0.0` outage, in which one unbounded lower bound took `main` red for ~21 hours
and blocked every pull request.

## The governed tuple

A resolution is only valid for the exact inputs that produced it. All of these are pinned, and
**changing any one requires regenerating every constraints file in a single reviewed change**:

| Input | Value | Where it is pinned |
|---|---|---|
| Python line | `>=3.12,<3.13` | `requires-python` in all four `pyproject.toml` |
| Python patch | **CPython 3.12.13** | `python-version` in `ci.yml`; `PYTHON_VERSION` in Dockerfiles |
| Platform | `x86_64-unknown-linux-gnu` | `scripts/regenerate_dependency_locks.py` |
| Resolver | **uv 0.12.0** | same script + `check_dependency_locks.py` |
| Extras | `dev` | same script — CI installs `[dev]`, so it must be resolved |
| Runtime base | `python:3.12.13-slim` (digest `sha256:cab2dbf5…0464`) | each `Dockerfile` |

## Files

```
constraints/
  backend-py312.txt        mcp-workbench-py312.txt
  mcp-server-py312.txt     agent-py312.txt
```

Generated, hash-bearing, one per project — **never hand-edited**. They are per-project because the
dependency graphs genuinely differ, not because the Python versions happen to match; a shared layer
would need to be an intentional compatibility policy, not an inference.

## How CI installs

```bash
pip install --require-hashes -r constraints/<project>-py312.txt
pip install --no-deps -e "apps/<project>[dev]"
```

The third-party graph comes from the committed resolution; `--require-hashes` makes an unexpected
or tampered artifact a hard failure. The local project is installed separately with `--no-deps`
because it is repository source, not a downloadable artifact with a package hash — and `--no-deps`
guarantees pip cannot quietly resolve anything outside the locked graph.

## Changing a dependency

1. Edit the direct dependency in the project's `pyproject.toml`.
2. Regenerate:
   ```bash
   pip install uv==0.12.0
   python scripts/regenerate_dependency_locks.py --only <project>
   ```
   On a machine behind a TLS-inspecting proxy (the developer laptop runs Norton), add
   `--system-certs`, or resolution fails with `invalid peer certificate: UnknownIssuer`. It does
   not change the output.
3. Commit `pyproject.toml` **and** `constraints/` together, and review the dependency diff in the
   PR — that diff is the point of this system.

Skipping step 2 fails the drift gate. A `constraints/` change is a **GLOBAL** classifier path, so it
correctly re-runs the FULL suite for every project.

## Rollback

```bash
git checkout <previous-good-commit> -- constraints/
```

Every entry is version- and hash-pinned, so this restores exactly the graph that was previously
reviewed and green. Rebuild environments afterwards. If a manifest also changed, revert that in the
same commit or the drift gate will (correctly) fail.

## Verification

```bash
python scripts/check_dependency_locks.py              # offline structural gate — runs in every CI run
python scripts/check_dependency_locks.py --recompile  # full re-resolution parity (network + uv)
python scripts/regenerate_dependency_locks.py --check  # regenerate to temp and diff only
```

The gate fails closed on: a missing or orphan constraints file · a header that does not record the
governed tuple · `requires-python` drifting from the governed line · any pinned entry without a
sha256 hash (one is enough to silently degrade `--require-hashes`) · a direct dependency declared
but not pinned · and, with `--recompile`, re-resolution differing from what is committed.

**`fresh-resolution-proof`** (scheduled / dispatch only) re-resolves and clean-installs every
project **outside any dependency cache**. It exists deliberately *before* environment caching is
introduced: once a cache exists, every other job may be served from it, and this is the one that
never is — so a drifted or unbuildable locked graph cannot hide behind a warm cache.

## Monthly refresh

First business day of each month, one PR containing regenerated files and the dependency diff.
Normal review, all governed checks, **never auto-merged**; close without merging when nothing
meaningful changed.

Out-of-cycle refreshes are permitted immediately for a security advisory, a yanked release, an
upstream incompatibility, or a production defect — record the reason in the PR (GITHUB-OPS-001 §7).

## Known limitation

Resolutions target **linux/amd64** because that is what CI and production run. They cannot be
`--require-hashes` installed on a Windows or macOS developer machine; use an ordinary editable
install locally, and rely on CI for the hash-verified path. Generating additional per-platform
resolutions is a separate decision with its own maintenance cost.
