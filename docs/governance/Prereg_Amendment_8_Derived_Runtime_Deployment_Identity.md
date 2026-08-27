# Preregistration Amendment 8 — independently derived runtime evidence in the deployment-identity instrument

**Scope: the deployment-identity instrument end to end — its verifier, the build-time producer that
stamps the value it checks, the governed configuration that selects it, the production call site that
supplies the runtime root, and their tests.** Nothing else. The corpus,
the countersignature, the quarantine policy, the outcome-pin expectations, the sealed and open record
schemas, the evaluation logic, every frozen threshold and counter, the holdout, Account 4 and the store
are untouched.

| | |
|---|---|
| supersedes measurement commit | `1c73d442e3461530fbda59c9051d023102a291b6` (chain continues; anchor preserved) |
| reason | `DECLARATION_ONLY_RUNTIME_DIGEST_MISSED_RUNTIME_SELF_REPORT_DIVERGENCE` |
| amended | 2026-08-26 |

## 0. Governance status

```
ACCOUNT 4            :  UNCHANGED - not reopened by this amendment
FORWARD WINDOW       :  UNCHANGED
PRIOR RESULTS        :  UNCHANGED - no economic result, observation, corpus, threshold,
                        counter, holdout or validation verdict is altered
SEALED EVIDENCE      :  UNCHANGED - nothing previously sealed is reinterpreted
ACTIVATION AUTHORITY :  NONE CREATED - this amendment confers no strategy or runtime authority
```

## 1. What failed — observed in production, not hypothesized

On 2026-08-26 the paper backend on `ec2-paper` was rebuilt and recreated **between two legs of a
governed MDQ capture**: the sampler terminated at 19:59:00Z on the old container, the image was built
at 20:23:02Z, the container was recreated at 20:23:48Z, and the EOD (20:30Z) and freeze (20:45Z) legs
ran on the new one.

The runtime moved. **Both deployment self-reports did not.**

| Source | Declared | Reality |
|---|---|---|
| `/opt/workbench/app/.deploy_src_sha` | `07a92330…`, mtime **2026-08-25** 21:25:19 EDT | untouched by the rebuild |
| `DEPLOYED_BUILD_INFO.json` | `deployed_repository_commit 07a92330…`, `built_at_utc 2026-08-26T01:19:05Z` | image actually built **2026-08-26T20:23:02Z** |

Read through either source, the deployment answers **"unchanged"** — which is the most dangerous
possible answer, because it is indistinguishable from a correct one and requires no failure to occur.
Nothing alerted. The divergence was found only by comparing a container creation timestamp against a
file mtime by hand.

**The structural fault:** `verify_deployment_identity` already required three sources to agree, but the
"runtime artifact digest" was **read from a configured file or an environment variable**. That is an
*assertion*, and an assertion keeps whatever value it was written with after the runtime moves
underneath it. Three mutually agreeing assertions are not three independent witnesses.

⭐ The 2026-08-25 lesson said *a deployment SHA is a point-in-time reading, not a property of the box.*
2026-08-26 sharpens it: **a stale pin can read as "unchanged" while the runtime has already moved**, so
pin-stability may never be treated as runtime-stability.

## 2. What this amendment changes

One source is added to the model — the only one that cannot be written down in advance.

- **`derive_runtime_code_digest(root)`** — hashes the code **actually on disk under `root`, at the
  moment of the call**. Deterministic by construction, because the value is compared against one
  computed on a different machine at build time: relative POSIX paths, sorted; framing is explicit
  (`<relpath>` + US `0x1f` + `<sha256>` + LF) so a path containing a newline cannot shift field
  boundaries; `__pycache__`, VCS and tool-cache directories excluded; a schema tag bound into the
  digest. **An in-scope symlink is REFUSED, not skipped** (see §2.0.5).
- **An empty traversal is refused, never hashed.** An empty result would produce a stable digest for
  "nothing", which is indistinguishable from a correctly-derived identity of a wrong root.
- **`DeploymentModel.CONTAINER_ATTESTED`** requires `build_info + runtime_digest + runtime_code +
  deployment_manifest`. The build stamp gains `code_digest`: the **expected build-time value** against
  which the independently derived current tree is compared.
- **The canonicalization is factored into one function, `code_identity()`.** Build-time and runtime
  both reach the value through it; neither transcribes the framing. A producer carrying its own copy is
  a second implementation that can drift, and a stamp from a drifted producer pins a value nothing can
  reproduce — the failure the measurement-freeze generator already warns about.
- **No environment path exists for the derived source, deliberately.** There is no
  `WORKBENCH_CODE_VERSION` or equivalent, and none may be added: an env-supplied value would
  reintroduce exactly the declaration-only weakness this amendment removes.

### 2.0 Two checks, deliberately unequal authority

A verifier whose expected value nothing produces is not a control, so the whole contract lands here —
and it lands as **two checks that may never substitute for each other.**

| Check | Authority | Answers |
|---|---|---|
| **In-container startup gate** | **enforcement** | *the code executing now equals the code this image claims it was built with* |
| **Host-side attestation (MDQ Gate 6)** | **independent attestation** | *the build marker, deploy manifest and running runtime reconcile* |

**Startup enforcement.** `scripts/bake_code_identity.py` writes `/app/BUILD_CODE_IDENTITY.json` at image
build, **derived from the bytes `COPY app ./app` just placed** — no build ARG, no environment variable,
nothing supplied at container creation. `scripts/verify_runtime_code_identity.py` re-derives at boot and
refuses on mismatch, missing, empty or unreadable evidence. It runs **before `alembic upgrade head`**,
not merely before serving: migrations and seeding are side effects on durable state, and a container
that cannot identify its code must not reach them.
⛔ **This is runtime integrity enforcement, never deployment provenance.** A wrong or hostile image
carries wrong code *and* a matching self-description and passes perfectly. Saying otherwise would be the
same category error the incident exposed.
⭐ The expected digest is baked precisely so that an operator facing a mismatch at 09:20 on a capture
morning **cannot** resolve it by editing the asserted value.

**Host-side attestation.** `mdq_preflight_readiness.sh` gains **Gate 6 — DEPLOYMENT/RUNTIME IDENTITY
ATTESTATION**, on the read-only host control plane that already runs before every governed slot and
after every container recreation. That is the exact surface where the blind spot sat: gates 1–5 read the
universe pin, credentials, the identity latch, disk and process state, and **none of them reads the
deployment self-report.**

⛔⛔ **Gate 6 reads the runtime with `docker cp <container>:/app/app -`, NEVER `docker exec`.** Running
the container's own digest implementation is the suspect attesting to itself. The daemon streams the
bytes out; `scripts/derive_runtime_code_digest_from_tar.py` hashes them **on the host**, importing the
same `code_identity()`. ⛔ The helper is **version-bound** — resolved as the preflight script's own
sibling, never from an environment variable. An earlier revision allowed
`${MDQ_ATTEST_HELPER:-…}` "for tests", which would have let a governed run point the load-bearing
derivation at code that simply prints the expected digest; that was **rejected on review and
removed**, and a test asserts a governed run ignores the variable entirely. `docker cp` rather than `docker export` because the scope is `/app/app`, not a
whole filesystem. The host collector fails closed on an empty measured set, duplicate entries, absolute
or `..` paths, special files, hardlinks, and **any in-scope symlink** — executable indirection is refused
rather than skipped, and the tree collector was changed to match so host and container cannot disagree
by construction.

#### 2.0.1 Gate 6 reconciles the whole tuple, not one comparison

| Leg | Source |
|---|---|
| **A. immutable build evidence** | `DEPLOYED_BUILD_INFO.json` — now emits the verifier's schema: `schema`, `commit`, `tree_clean`, `code_digest` (the legacy `deployed_repository_commit` is retained). `tree_clean: true` is honest by construction: a `git archive` of a committed SHA cannot contain uncommitted bytes. |
| **B. deploy-written runtime manifest** | `deploy/aws/write-deployment-manifest.sh` writes `DEPLOYMENT_RUNTIME_MANIFEST.json` **atomically, after container creation**: commit, code_digest, image digest, **container id**, **container creation timestamp**, **`build_info_sha256`**, deploy timestamp. ⭐ It **binds the marker by hash**, not merely by repeating its fields — otherwise a valid marker from one attempt and a valid manifest from another could be paired and every field-by-field comparison would still agree. Gate 6 re-hashes the marker on disk and compares. |
| **C. current runtime reality** | fresh from Docker: running container id, running image id, and `/app/app` bytes → host-derived digest. |

Required conjunction: marker commit == deploy-manifest commit · build `code_digest` == deploy-manifest
`code_digest` == host-derived runtime digest · deploy-manifest image == running image · deploy-manifest
container == running container · deploy-manifest `container_created` == running creation timestamp.

⚠⚠ **Boundary, stated precisely — and carried into the operator-visible strings.** Gate 6 proves that
the **build marker, the deploy manifest and the running runtime reconcile**. It does **not** prove the
commit was organizationally *approved*: approval is the separate governance authorization that selected
the immutable SHA, and the marker is evidence of what was built, not of who authorized it. Calling the
marker "approval authority" would quietly make a build artifact its own sanction.

⛔ **This is why the gate's own output was corrected.** An earlier revision printed
`MISMATCH: approved commit … != deployed commit …` and, on success,
`RESULT: PASS - approved == deployed == running`. A PASS line enters a governed operational transcript,
so those strings would have asserted a fact the gate never tested. They now read
`build-marker commit` / `deploy-manifest commit` and
`RESULT: PASS - build marker == deploy manifest == running runtime`. Prose and emitted evidence must
say the same thing, or the transcript outlives the caveat.

⭐ **Leg B is what makes an unrecorded recreation visible.** A later `docker compose up -d` that
silently replaces the container no longer matches the recorded container id and creation time — which is
precisely what nobody could see on 2026-08-26.

⛔ **`.deploy_src_sha` is demoted to a corroborating declaration.** Disagreement fails Gate 6 once the
repaired system is deployed, but that file may never again be sufficient evidence by itself. It read
"unchanged" while the runtime had already moved.

⚠ The current preflight prints deployment SHA, image and container creation under **CONTEXT (not
gates)** — three disconnected observations. Gate 6 turns them into a reconciled predicate.

### 2.0.2 The MDQ standard changes — by VERSION, not by a switch

The readiness standard moves from *five-gate preflight + natural timer* to **six-gate preflight +
natural timer**. A Gate-6 failure means **NOT READY**. The three-proof chain keeps its shape; each
readiness proof becomes 6/6.

⛔⛔ **There is deliberately NO environment switch that makes Gate 6 count.** An earlier draft of this
amendment shipped it default-off behind `MDQ_GATE6_REQUIRED=1`; that was **rejected on review and
removed**, because a default-off integrity gate is silent degradation by construction — the repair could
deploy successfully while someone forgets the flag, and the control would go on declaring READY on five
gates. That is the same class of failure as a stale pin reading "unchanged".

⭐ **The prospective boundary is preserved by DEPLOYMENT, not by a flag.** Until this version is
deployed the box still runs the five-gate script, so 2026-08-27 remains the five-gate standard with no
switch existing anywhere. The moment the repaired control is deployed, six gates govern automatically.

To exercise this implementation against a pre-repair box, `--diagnostic` prints a **NON-GOVERNING**
banner and **can never emit a READY verdict**, so it cannot be mistaken for, or substituted for, a
governed run. That property is tested.

### 2.0.3 The producer runs from the commit it is describing

`build-deploy-archive.sh` deliberately packages an explicit immutable `DEPLOYED_SHA`, which may be older
than the checkout it runs from. It previously executed the *current* checkout's producer — so one
commit's canonicalization could define another commit's identity, silently, and a dirty checkout would
do it too. It now creates a **temporary detached worktree at `DEPLOYED_SHA`** and runs *that commit's*
producer, so the code bytes and the algorithm defining their identity come from the same immutable
object graph.
⛔ Deliberately **not** solved by requiring `HEAD == DEPLOYED_SHA`: that would remove the ability to
deploy an older approved commit, which is a property of this script, not an accident.

**Deployability precondition.** Under the attested deployment model, a deployable target commit must
contain the canonical code-digest producer and its required implementation dependencies. Hermetic
deployment fixtures must therefore construct commits satisfying that same precondition; tests may not
bypass the refusal or substitute a second producer implementation.

⛔ Both shortcuts were considered and rejected when this surfaced in CI. A stub producer would be
exactly the second canonicalization the design forbids. Relaxing the refusal in
`build-deploy-archive.sh` would be worse still: it would make a production integrity invariant
conditional on the shape of a test fixture.

⭐ **A cross-platform hazard surfaced while proving parity.** It depends on the archive carrying **blob**
bytes. On a Windows build host with `core.autocrlf=true` an unguarded `git archive` injects CRLF, the
runtime hashes CRLF, the producer hashes LF, and the deployment silently stops verifying. The
DEPLOY-EOL DETERMINISM `.gitattributes` rule already pins `eol=lf` — which is *why* production parity
holds — but the deploy script did not defend it. `git archive` now runs under `-c core.autocrlf=false`,
and the end-to-end fixture mirrors the production `.gitattributes` so it tests the repository that ships.

### 2.0.4 Scope parity

The Dockerfile does `WORKDIR /app` then `COPY app ./app`, so the container's `/app/app` **is**
`apps/backend/app`. Producer, startup gate and host attestation all digest that tree with identical
relative keys and identical suffix/exclusion rules — now **public constants** the producer imports
rather than transcribes. The roots and rules change together or not at all.

⚠ **The forward-validation consumer is also wired** (`ForwardDeploymentConfig.runtime_code_root`,
required for `CONTAINER_ATTESTED` and refused at load; `build_session_runtime` passes it through), but
that architecture is **not** the runtime that suffered the incident. The workbench-paper answer is the
startup gate plus Gate 6 above.

### 2.0.5 Link and special-file semantics, stated exactly

Loose wording here would be the same defect the amendment is about, so the rule is stated per collector
rather than summarised:

| Entry | Filesystem collector (`code_entries_from_tree`) | Tar collector (host, `docker cp`) |
|---|---|---|
| in-scope **symlink** (`.py`) | **REFUSED** | **REFUSED** |
| out-of-scope symlink | skipped | skipped |
| in-scope **hardlink** | **hashed as an ordinary file** — a POSIX hardlink is indistinguishable from the file itself at the filesystem layer, and there is nothing to detect | **REFUSED** — tar represents it as a distinct `LNKTYPE` entry with no content, so hashing it would silently contribute nothing |
| special file (device, fifo, socket) in scope | not a regular file → skipped | **REFUSED** |

⚠ **The collectors are therefore identical on symlinks and deliberately different on hardlinks**, for a
mechanical reason rather than a policy one: the difference exists only because the tar stream *can*
distinguish a hardlink and the filesystem walk cannot. ⛔ Do not "harmonise" this by weakening the tar
collector — the asymmetry favours refusal on the side that has the information.

⭐ In practice a hardlink cannot change the derived identity on either side: the filesystem collector
hashes the real content, and the tar collector refuses. What is ruled out is a hardlink *silently
contributing nothing* to the host attestation.

### 2.1 Which source is evidence, and which is corroboration

Stated explicitly, because the model now has four required inputs and they are not of equal weight:

| Input | Kind |
|---|---|
| `runtime_code` (derived) | **the independent attestation** — the only non-assertable source |
| `build_info` | build-time declaration, and the source of the expected `code_digest` |
| `runtime_digest` | additional declaration / corroborating source |
| `deployment_manifest` | deploy-written declaration |

**The derived value remains load-bearing even when every declaration agrees.** Under
`CONTAINER_ATTESTED`, `build_info = A` and `runtime_digest = A` and `deployment_manifest = A` must
**not** manufacture a PASS when the derived runtime code differs from the build-time `code_digest`.
That case is tested directly.

### 2.2 What is preserved

`CONTAINER` and `SOURCE_CHECKOUT` behave exactly as before; every existing caller and all 37
pre-existing tests are unchanged. `DeploymentEvidenceMissing` and `DeploymentEvidenceMismatch` remain
distinct fail-closed stops. `expected_commit` remains an operator **pin** that can only narrow the
result — it is checked against the derived identity and never substitutes for a source.

## 3. Falsification suite

Thirty regression tests, each mutating exactly one source:

- **A/A/A** verifies; the derived source is recorded as `derived:` and kept in its own field.
- Mutating the **embedded stamp**, the **running artifact**, the **deployment manifest**, or the
  **declared runtime digest** — each refuses independently.
- Adding, removing or **moving** a file in the running tree refuses; identical content at a different
  root derives the same identity; `__pycache__` does not perturb it.
- Removing **each source independently** raises missing-source, not mismatch.
- Runtime A versus runtime B derive different identities.
- The pin cannot substitute for a missing source, and cannot rescue a mutated runtime.

### 3.0 Startup enforcement and host attestation

Sixteen tests. Startup: passes on a match; refuses an edited runtime, an image with no baked identity, a
foreign canonicalization schema, and a malformed expected digest; **cannot be satisfied from the
environment** (plausible variables set to the right value do not rescue a mutated runtime); and the
baker and the gate are proven to be two ends of one contract. Host: derives the same value as the
in-container derivation from a `docker cp` stream; ignores out-of-scope files; refuses an empty scope, a
duplicate entry, path traversal, an in-scope symlink and a special file; exits non-zero at the process
boundary, because Gate 6 reads the exit status. The tree collector is proven to refuse an in-scope
symlink too, so the collectors agree exactly where §2.0.5 says they must.

Gate 6 additionally has one test per leg of the tuple, each mutating exactly one thing: unrecorded
container recreation (the 2026-08-26 shape), unrecorded image rebuild, running code that is not the
deployed code, a missing deploy manifest, a **swapped marker** (valid marker + valid manifest from
different attempts), a **restamped `container_created`**, a stale `.deploy_src_sha`, and the reconciled
case. Three further controls guard the control itself: **no switch can degrade six gates to five**,
**the attestation helper is not caller-supplied** (and exporting the removed variable cannot change a
governed result), and **the operational entrypoints are committed `100755`** — `git archive` preserves
modes, so a `100644` entrypoint would make the documented production sequence permission-fail on the
box.

The preflight's own regression suite gained two controls: **every `docker cp` must be the read-only
container-to-stdout form** (the previous blanket ban was correct in instinct — its usual direction
writes *into* a container — so it was narrowed, not dropped), and **Gate 6 specifically must not run
container userland**, scoped to Gate 6 because gates 2 and 3 legitimately use `docker exec` for the
container's environment and broker identity.

### 3.1 End-to-end, against the real producer

A separate fixture builds a real git repository, runs the **actual** producer script, takes a real
`git archive`, extracts it, and verifies — because the property under test is agreement between two
independently written collectors, and a fixture calling only one of them would prove nothing. It
covers: producer and runtime derive the same value; the full chain verifies; a non-code file inside
the deployed tree perturbs neither side; **mutating the runtime after an honestly-produced stamp
refuses**; a pre-Amendment-8 marker without `code_digest` refuses rather than skipping the check; the
producer refuses an empty scope and is stable across runs; a different commit stamps a different
identity.

### 3.2 The 2026-08-26 shape, as a named regression

Three tests encode the production failure so it cannot silently return:

1. **manifest declares the old commit while the runtime is a rebuilt artifact** ⇒ FAIL CLOSED. It is
   never reported as "unchanged".
2. **the same shape with the stale pin supplied as `expected_commit`** ⇒ still refuses. An operator who
   "knows" the box is on the old commit cannot manufacture a PASS.
3. **a hand-repaired manifest**: every declared source agrees, but the tree was hotfixed in place ⇒
   only the derivation disagrees, and it refuses. This closes the obvious workaround.

## 4. Why the measurement freeze moves

`manifests/forward/measurement_freeze.json` measures `app/validation`. Changing governed validation
code is therefore **supposed** to move `validation_tree_sha256`; the freeze tests pin that rule.

⛔ **Relocating this code outside `app/validation/` to keep the digest unchanged was considered and
rejected.** `deployment_identity.py` is validation/integrity code by function, and moving part of the
identity model out of the measured path purely to avoid an amendment would turn the freeze into a
directory-layout game — worse governance than ratifying a legitimate change. The red test was useful
evidence and is resolved by ratification, not by evasion or suppression.

The measurement **anchor is preserved** at `1c73d442e3461530fbda59c9051d023102a291b6`; only the
governed executable-content digest moves. This follows Amendment 7 exactly. The three generated
artifacts — `measurement_freeze.json`, `measurement_bytes.json`, `ratified_increments.json` — are
produced solely by `scripts/forward_validation/generate_measurement_freeze.py` against a
`git write-tree` staged-tree SHA, and are **never hand-edited**.

⚠ That the forward-validation path may now be retired does not make a presently enforced freeze
disposable. Until the freeze is itself formally retired, `main` is correctly reporting that
`app/validation` is governed content.

## 5. What this amendment does NOT do

- It does **not** reopen Account 4 forward validation.
- It does **not** change any prior economic result, observation, corpus, frozen threshold, counter,
  holdout, or validation verdict.
- It does **not** create new strategy or runtime activation authority.
- It does **not** reinterpret any previously sealed evidence.
- It does **not** deploy anything. Deployment of the repair, backend rebuild/recreate, mutation of
  `.deploy_src_sha` or `DEPLOYED_BUILD_INFO.json`, and any LOW-001 proof execution all remain on HOLD
  under separate authority.
- It does **not** change what any existing deployment verifies. `CONTAINER` and `SOURCE_CHECKOUT` are
  untouched; a deployment only gains the derived check by explicitly selecting `CONTAINER_ATTESTED`
  and naming `runtime_code_root`.
