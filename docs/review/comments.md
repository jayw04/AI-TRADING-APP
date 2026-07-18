Disposition

Authorize Option B: one bounded, read-only diagnostic run on the existing pinned image and host.

Do not change the fixture expectation yet.

The evidence shows the cascade behaved correctly: the primary candidate was rejected by the registered certifier, the fixed fallback ran once, PIQP qualified, and the terminal disposition was FALLBACK_QUALIFIED with no stop. The failed condition is specifically the realism fixture’s claim that this synthetic bound-only case must be PRIMARY_QUALIFIED.

Before deciding whether to replace or reclassify the fixture, capture the exact primary candidate and certificate residuals. The present artifact records only the failing gate names, not their magnitudes.

Authorized diagnostic scope

Run only this existing case:

primary_qualified/active_upper_bound

Using exactly:

qualification commit   3a37545e2dcf201542a5fca6fca29bade828f9c0
image / OCI digest     sha256:a7a729c9128fe3db239c6b2d376ffa5c169db2b0f400f1170ec72258c91fcd89
primary                QUADPROG_SQRT
certifier              canonical_qualify
registered LIMITS      unchanged
thread / CPU settings  unchanged

Those identities are already bound in the run record and pins draft.

Capture, without altering any source file:

input arrays and their exact hashes
primary z
primary lambda
expected optimum for the 1-D fixture
all certificate fields
kkt_residual
primal_residual
dual_residual
stationarity_residual
complementarity_residual
signed Lagrangian gap interval
interval width
multiplier clipping count
each registered limit
ratio: observed residual / registered limit
primary raw solver status and output

Also compute the elementary 1-D checks directly from the returned candidate:

z >= 0
z <= upper
upper - z
objective gradient at z
stationarity reconstruction
bound multiplier signs
complementarity products

Run the identical diagnostic at least twice in separate fresh processes to establish whether the returned candidate and residuals are byte-identical or numerically variable.

Prohibited

Do not:

change a tolerance;
change or replace the fixture;
relabel the expected disposition;
call PIQP as part of the diagnostic except to retain the already-observed cascade record;
run any corpus row;
inspect validation or OOS data;
perform a broader solver sweep;
introduce jitter, scaling experiments, or alternative profiles.

This is evidence collection only.

Required diagnostic artifact

Create one immutable JSON artifact containing:

record_type
version
record_status
authorization scope
commit/tree/image/OCI identities
fixture name and rec_sha256
two independent primary-run records
full primary candidates
full certificate fields and limits
determinism comparison
diagnostic conclusion limited to facts
artifact SHA-256 and byte length

Preserve the existing realism FAIL artifact unchanged. The diagnostic must be written to a new fresh directory.

Decision rule after the diagnostic

The next disposition will depend on the scale and character of the miss:

Tiny, stable boundary miss—for example, residuals narrowly above the fixed limits while the primary point is otherwise the expected solution: replace this fixture with a robust primary-qualified problem. Do not weaken the certifier and do not redefine qualification.
Large or structurally incorrect primary result: hold qualification and investigate the primary wrapper or bound-only formulation.
Nondeterministic result: hold qualification and investigate runtime/numerical determinism.
Evidence of a fixture construction mistake: correct the fixture through a reviewed delta, preserving the current FAIL evidence.

Merely accepting both PRIMARY_QUALIFIED and FALLBACK_QUALIFIED for this case would weaken the realism assertion and is not authorized at this stage.

Instance handling

Keep the c6a instance only long enough to run this bounded diagnostic and verify that the resulting artifact is copied, hash-matched, and made read-only in the durable evidence location. Then terminate it to stop billing; no further ruling is needed for termination once that preservation check succeeds.

Existing qualification evidence          ACCEPTED AND PRESERVED
Realism harness verdict                   FAIL — VALID STOP GATE
Bounded one-case diagnostic               AUTHORIZED
Fixture expectation change                NOT YET AUTHORIZED
Tolerance or solver change                PROHIBITED
Registered Stage-3 execution              NOT AUTHORIZED
Validation / OOS                          SEALED AND UNREAD