# MR-002 Host Requalification Package v1.0 — HOLD-POINT SUBMISSION

- **Date:** 2026-07-19 (host phase opened by owner; sequence executed through the hold point)
- **Status:** STOPPED at the mandated hold point. The archive-qualification command was NOT
  executed. No v5 artifact exists. Validation/OOS were not accessed. The instance was NOT
  terminated.

## 1. Instance and EBS identities

| Item | Value |
|---|---|
| Instance | `i-0f3ceafdd4294c572` — SAME instance restarted (state transition stopped→running confirmed via API) |
| Type / AZ | `c6a.large` / `us-east-1d` (unchanged) |
| Root EBS | `vol-0ce8c0056244d14f5` at `/dev/xvda` — SAME volume attached (API-confirmed post-restart) |
| Public IP | `35.173.237.216` (new ephemeral IP — no EIP on this host; SSH host key accepted fresh) |
| Storage | EBS-only: single disk `nvme0n1` (30G xfs `/` + EFI); no instance store |

## 2. Full host inventory (requalification)

| Item | Value |
|---|---|
| CPU | AMD EPYC 7R13, x86_64, **AVX2 present** |
| Kernel / OS | `6.1.176-221.360.amzn2023.x86_64`, Amazon Linux 2023.12.20260710 |
| Docker | client 25.0.14 / server 25.0.16 |
| Storage driver / snapshotter | `overlayfs`, driver-type `io.containerd.snapshotter.v1` (containerd snapshotter — the mandatory runbook control) |
| Containers | `docker ps -a` count **0** (verified at requalification AND after every suite run) |
| Signing keys | `~/keys/mr002_launcher_ed25519.pem` mode **600** ec2-user; `.pub.pem` 664 — on root EBS |
| Symlinks under `~/mr002` | **0** |
| Archive recheck (NO parsing — hash + stat only) | checkpoint `b9b0a948…6637b7445` (67,293,482 B, `444 root:root`), manifest `1132d3b8…79c96e40` (130,846 B, `444 root:root`), dirs `555`; EXACT match to the preservation record |
| v4 staged inputs | 9 files present (closed v4 chain, informational — not used) |
| `~/mr002/out` | EMPTY (no `cleanrun` — recreated only when a Run-5 chain is authorized) |
| Validation / OOS | SEALED AND UNREAD — nothing in this phase touched any validation or OOS data; the only data file opened by suites is the registered DEV-window DuckDB inside the checkout |

## 3. Checkouts

| Checkout | Commit / tree | State |
|---|---|---|
| `~/mr002/numrepo` (**/work**) | `ecaa262480fb2b81fb0ba7d11b97721b617722bf` / `1cb95e254c0dc82bc231b355b8ab502f4e33f752` — clean DETACHED, porcelain 0, relocked `dr-xr-xr-x`, 0 symlinks | registered implementation (tooling commit deliberately NOT used here) |
| — registered file identities in /work | cascade `1021cc28…` 45,030 B; runner `297901d7…` 85,064 B; tests `ba195125…` 78,375 B — ALL EXACT vs the accepted v1.8a identities | |
| — corpus DB in /work | survived checkout update: md5 `92a985c1…`, sha256 `24e5153c…`, 132,395,008 B | |
| `~/mr002/repo` (launcher) | `b6e5d278…` / `1657d0c7…`, porcelain 0 — untouched | |
| `~/mr002/delta-test/repo` (scratch SUITE clone) | `8f9444833f74cd9dc5fa0e7984fe1d0f43ad7c06` / `aed9aca5…`, porcelain 0 at checkout; in-tree tool/test identities exact (`3b60de2a…` / `0478369e…`) | suite venue only; subsequently carries the v1.0b test fix + editable-install metadata (disclosed §8) |

Provisioning: the box's git origin is a bundle predating `ecaa262`; objects were delivered by a
new incremental bundle `mr002_hostphase_v3.bundle` (`d26bd9e..branch`, sha256 `ed5bba44…`,
233,606 B, hash-verified after transfer).

## 4. Tool staging

`/home/ec2-user/mr002/tools/mr002_run4_archive_qualification.py` — staged NO-OVERWRITE
(directory refused-if-exists, then freshly created), bytes extracted from the COMMITTED git blob
`f02d4415…` (not a working copy). **sha256 `3b60de2a1d96d97152ea62b77c81ff25861d2e9582698b75f4e25b4dee8c7db5`,
15,225 B — EXACT.** Locked: file `444`, dir `555`, 0 symlinks.

## 5. Image and OCI-config digest

Image present and inspectable: Id `sha256:81e8d7a7be6bb022d7bde68e923ea6ef2a41b029390200e0240235f35aa173ea`
(linux/amd64, created 2026-07-18T18:54:46Z, repo tag `mr002-stage3-qual`). Both digest channels
(image digest and OCI config digest) equal this value, exactly as in the accepted v3/v4 attested
templates. **Proposed qualified image for the archive-qualification command: this digest** — the
registered code is mounted at `/work`, not embedded, so no image change is required; your
confirmation fixes it.

## 6. Dependency closure (registered environment)

Suite venv `~/mr002/qualenv-v18`: **Python 3.12.13** (registered backend runtime; the box's
python3.11 stays reserved for launcher operations per the standing ruling). Installed from the
registered `pyproject.toml` dependency list + dev extras + the research-suite solver stack, with
per-wheel sha256 fingerprints recorded in pip install-reports (`pip_install_report.json` sha
`dcd5892d…`; clarabel addendum `bda05912…`). 92 packages. Key identities:
**mpmath 1.4.1** (wheel sha256 `dc4f0ea2304480d4a9a48a94c1020571558ade522b44a6912efac63a586e140f`),
numpy 2.2.6, scipy 1.18.0, pandas 2.3.3 (registered `<3` pin honored), quadprog 0.1.13
(== `REGISTERED_QUADPROG_VERSION`), piqp 0.6.3, clarabel 0.11.1, numba 0.61.2 (pandas-ta's exact
pin), duckdb 1.5.4, pytest 9.1.1, pytest-asyncio 1.4.0, ruff 0.15.22.

Disclosures: (a) **pandas-ta 0.4.71b0 is no longer on PyPI** (upstream removal — "versions:
none"); the registered pin was satisfied by transplanting the laptop venv's installed 0.4.71b0
package (pure Python; archive sha256 `e402c0f1…`, hash-verified after transfer), with its
declared deps numba==0.61.2 + tqdm installed normally. (b) numba's pin constrains numpy to 2.2.x
in the suite venv (the frozen IMAGE keeps its own registered numpy — unaffected). (c) clarabel
was missing from my initial closure and surfaced as 20 certificate-suite failures
(`ModuleNotFoundError`), fixed by installing it — no code was touched.

## 7. Suite closure — all commands `~/mr002/qualenv-v18/bin/python -m pytest <target>` from the suite clone's `apps/backend`

Env for host runs: `MR002_REAL_CLI_TEST=1`, `MR002_REAL_DOCKER_ARCHIVE_TEST=1`,
`MR002_REAL_DOCKER_IMAGE=sha256:81e8d7a7…`, `MR002_REAL_DOCKER_WORK=/home/ec2-user/mr002/numrepo`.

| Suite | Result | Log sha256 |
|---|---|---|
| Collection, whole `tests/research/` | **749 collected, ZERO collection errors** | `9024de36…` |
| Certificate | **58 passed** | `fd75db43…` |
| Directed-rounding | **37 passed** | `129016d9…` |
| Correction-regression | **5 passed** | `268f2628…` |
| Exact-repair | **29 passed** | `dee22926…` |
| Population-runner | **134 passed** | `0e0b1cab…` |
| Launcher tools (real-CLI ENABLED) | **99 passed, ZERO skips** | `a256ac26…` |
| Archive-qualification tool (real-Docker ENABLED) | **36 passed, ZERO skips** (after the v1.0b probe fix, §8) | `1421085f…` |
| Frozen-runtime suites (joint-solve + stage3-cascade + execution-ECI) IN-IMAGE | **55 passed** (`docker run --rm --network=none` on the pinned image, suite clone ro at /work, `--confcutdir` at tests/research; 1 benign `asyncio_mode` config warning) | `0bda4657…` |
| Full `tests/research/` on host | 702 passed + the same 45 frozen-runtime-bound tests + **2 DESIGN skips** (`test_mr002_exact_simplex.py:96 "fully triangular basis — no core to factor"` — parameter-conditional by construction, skip anywhere incl. dev) | `a4d984cf…` / `-rs` rerun `dc4f9df3…` |
| Ruff frozen checks (all registered MR-002 paths) | **All checks passed** | `82b3e6a6…` |

The 45 host-side "failures" in the full-directory run are the frozen-runtime boundary WORKING:
`_assert_registered_solver` requires the in-image `/manifest/pip_report.json` and refuses any
other runtime — those 45 tests are the exact set that passed 55/55 in their designed in-image
venue (45 previously-failing + 10 that pass in both). No test was weakened; nothing was skipped
unexpectedly.

## 8. FINDING + narrow correction: v1.0b (host-only Docker probe syntax)

Real in-container execution exposed a defect in the COMMITTED v1.0a test
`test_v10a_real_docker_mount_semantics`: its inline probe joined `import os; def probe(...)` on
one line — a SyntaxError, unreachable on the laptop (env-gated skip). **The frozen tooling
commit `8f94448` was NOT modified**; a narrow test-only fix (probe rewritten as a real
multi-line script; no assertion or coverage change) was authored on the laptop, verified there
(35 passed + 1 skip, ruff clean), applied to the SCRATCH suite clone only, and re-run on the
host: **36/36 including the real mount-semantics test** (ro passes; writable refuses; symlink
refuses; directory-typed checkpoint refuses — all in the actual Linux container against real
bind mounts). Submitted for review: patch `MR002_ArchiveQualTool_Delta_v1.0b.patch` sha
`713ad4d44a5518a3fdb1a220f0a5f1f982fac9e891fe9174dbcbaf9e851d193c` (2,351 B); corrected test
file sha `87dd88f7a8151c92ee25b65fbc82c76d188c6df72156e1f99314534cc7deb810`. Commit requires
your authorization (new tooling delta).

## 9. Proposed no-overwrite publication method + exact command (HELD)

Wrapper (to be staged only after your approval; `bash` with `noclobber` create-exclusive
redirection PLUS explicit vacancy refusals PLUS pre-run tool-hash verification, then read-only
lock and hash report of both outputs):

```bash
#!/usr/bin/env bash
# MR002 archive-qualification no-overwrite publication wrapper (owner-approved text only)
set -u -o noclobber
REPORT=/home/ec2-user/mr002/launch/run4_archive_qualification_report.json
ERRLOG=/home/ec2-user/mr002/launch/run4_archive_qualification_stderr.log
TOOL=/home/ec2-user/mr002/tools/mr002_run4_archive_qualification.py
EXPECT=3b60de2a1d96d97152ea62b77c81ff25861d2e9582698b75f4e25b4dee8c7db5
[ -e "$REPORT" ] && { echo "REFUSE: report destination occupied" >&2; exit 3; }
[ -e "$ERRLOG" ] && { echo "REFUSE: stderr destination occupied" >&2; exit 3; }
got=$(sha256sum "$TOOL" | cut -d" " -f1)
[ "$got" = "$EXPECT" ] || { echo "REFUSE: tool hash $got != $EXPECT" >&2; exit 3; }
sudo docker run --rm --network=none \
  --mount type=bind,src=/home/ec2-user/mr002/numrepo,dst=/work,ro \
  --mount type=bind,src=/home/ec2-user/mr002/tools,dst=/tools,ro \
  --mount type=bind,src=/home/ec2-user/mr002/evidence/run4_replay_defect,dst=/archive,ro \
  --env=OPENBLAS_CORETYPE=HASWELL --env=OPENBLAS_NUM_THREADS=1 \
  --env=OMP_NUM_THREADS=1 --env=MKL_NUM_THREADS=1 \
  --env=PYTHONPATH=/work/apps/backend --workdir=/work/apps/backend \
  sha256:81e8d7a7be6bb022d7bde68e923ea6ef2a41b029390200e0240235f35aa173ea \
  python /tools/mr002_run4_archive_qualification.py --archive /archive --work-root /work \
  > "$REPORT" 2> "$ERRLOG"
rc=$?
chmod 444 "$REPORT" "$ERRLOG"
echo "tool_exit=$rc (PASS=0 FAIL=1 REFUSED=2)"
sha256sum "$REPORT" "$ERRLOG"
exit $rc
```

Both destinations verified **VACANT** at submission time. The tool's own gates additionally
enforce commit `ecaa262`, archive read-only + pinned hashes, corpus hash, schema 2.0, and the
3,895-row reconciliation before any qualification work.

## 10. Confirmations

- `docker ps -a`: **empty** (rechecked after the last container run).
- Validation/OOS: **SEALED AND UNREAD** throughout.
- Instance: running, NOT terminated; no state destroyed.

## Requested owner actions (hold point)

1. Review this requalification package.
2. Rule on v1.0b (test-only probe fix): accept + commit authorization.
3. Fix the qualified image digest (proposed: `sha256:81e8d7a7…`, both channels).
4. Approve the no-overwrite wrapper text + exact command → authorize the archive-qualification
   execution.
