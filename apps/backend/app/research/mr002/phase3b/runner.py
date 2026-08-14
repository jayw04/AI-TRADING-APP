"""The Phase 3B entry point: S0..S11, with everything expensive proven before the gate.

The runner takes its reader and its candidate source by injection, so the qualified path and the
governed path are the SAME path with different collaborators. Synthetic qualification supplies a
fixture reader that has no AWS dependency; the governed run supplies the S3 reader. Nothing else
differs, which is what makes the qualification worth anything.

`stop_at` exists so the dry launch can halt exactly at PRE_ACCESS_READY. Before that point a
restart costs nothing; after S9 the opening is spent and the runner refuses to restart.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from . import admissibility as A
from . import census as C
from . import enrichment as E
from . import publish as P
from . import roster as R
from . import states as S
from .guard import VALIDATION, ValidationGuard
from .readers import PinnedObject


class CandidateSource(Protocol):
    """Turns governed input bytes into (decision, facts) pairs.

    In the governed run this is the SPQ-1 producer over the validation window, bound to the 15
    Phase-2B module identities. In qualification it is a fixture. The runner does not care which,
    which is the point: the seam is the same.
    """

    def candidates(self, payloads: dict[str, bytes]) -> list[tuple[Any, Any]]: ...


class RunRefused(Exception):
    """A precondition failed. Where it failed determines whether anything was spent."""


@dataclass
class RunOutcome:
    disposition: str = P.REFUSED
    exit_code: int = P.EXIT_BY_DISPOSITION[P.REFUSED]
    state: str = S.S0_INIT
    opening_consumed: bool = False
    # The computation's terminal verdict, captured before publication is attempted and never
    # overwritten by it.
    primary_disposition: str | None = None
    primary_error: str | None = None
    published: bool = False
    publication_error: str | None = None
    history: list[str] = field(default_factory=list)
    enrichment_census: dict | None = None
    seam: dict | None = None
    integrity: dict | None = None
    # The three status fields are separate because they answer different questions and the answers
    # legitimately diverge: COMPLETED + FAIL + inadmissible is not a contradiction. The computation
    # succeeded; the resulting research population failed its preregistered coverage requirement.
    # Keeping them separable is what stops a later reader saying "run completed successfully" while
    # omitting that its evidence failed qualification.
    execution_status: str = "NOT_STARTED"
    qualification_status: str | None = None
    evidence_admissible: bool | None = None
    refusal_census: dict | None = None
    deliverable_hashes: dict[str, str] = field(default_factory=dict)
    publication: dict | None = None
    error: str | None = None


@dataclass
class Phase3BRunner:
    reader: Any
    candidate_source: Any
    output_root: str
    registered_objects: dict[str, set[str]]
    inputs: list[PinnedObject]
    bound_roster: dict[str, dict[str, str]]
    contract_identities: dict[str, str]
    expected_contract_identities: dict[str, str]
    config_mapping: dict[str, float]
    expected_config_mapping: dict[str, float]
    runtime_facts: dict[str, str]
    expected_runtime_facts: dict[str, str]
    identities: dict[str, str]
    # The configuration's own recording of the executing closure. Carried so the run can compare
    # the bytes it is about to execute against the identity its configuration declares, which
    # `bound_roster` cannot do -- the entrypoint supplies that from `current_roster()`, making it a
    # self-comparison. Defaulted so existing constructions keep working; absent or disagreeing
    # values REFUSE in `_verify_declared_closure_identity`, they do not pass silently.
    observed_identities: dict[str, str] = field(default_factory=dict)
    staged_open_prefix_payloads: dict[str, bytes] = field(default_factory=dict)
    # Injected only so a test can make publication deterministic. There is NO published_at input:
    # the publisher stamps it at the durable publication transition, so the run reaches
    # PRE_ACCESS_READY with no such value in existence.
    clock: Callable[[], str] | None = None

    def __post_init__(self) -> None:
        self.sequence = S.LaunchSequence()
        self.guard = ValidationGuard(registered_objects=self.registered_objects)

    # -- pre-gate: everything that can fail for free ---------------------------------
    def _verify_code_identity(self) -> None:
        R.verify(self.bound_roster)
        self._verify_declared_closure_identity()
        self.sequence.advance(S.S1_CODE_IDENTITY_VERIFIED)

    def _verify_declared_closure_identity(self) -> None:
        """The live closure must equal the identity the CONFIGURATION declares.

        Runs before reader construction, before STS, and before any sealed access, so a
        configuration that names a different execution package refuses for free.

        This check exists because of an observed failure, not a hypothetical one. On 2026-08-14 a
        stale configuration declaring the superseded identity ``f35e8209...`` was executed against
        v3.2 bytes ``487c7f8d...``; ``R.verify`` above could not catch it because the entrypoint
        hands it ``current_roster()``, i.e. it compares the live closure against itself. The
        opening was spent before anything noticed, and the published record misattributed the
        package that ran.

        Both configuration fields are required to agree with each other first: they are two
        recordings of one fact, and a configuration that disagrees with itself cannot bind
        anything.
        """
        declared = (self.identities or {}).get("code_identity")
        observed_field = (self.observed_identities or {}).get("execution_closure_sha256")
        if not declared:
            raise RunRefused(
                "identities.code_identity absent; an execution package that declares no identity "
                "cannot be bound to the bytes that are about to run"
            )
        if not observed_field:
            raise RunRefused("observed_identities.execution_closure_sha256 absent")
        if declared != observed_field:
            raise RunRefused(
                "configuration disagrees with itself: identities.code_identity "
                f"{declared} != observed_identities.execution_closure_sha256 {observed_field}"
            )
        live = R.closure_identity()
        if live != declared:
            raise RunRefused(
                f"execution closure identity mismatch: live mount {live} != declared {declared}. "
                "The configuration names a different execution package than the one executing; "
                "refusing before any credential or sealed access."
            )

    def _verify_contract_identity(self) -> None:
        drift = sorted(
            k
            for k, v in self.expected_contract_identities.items()
            if self.contract_identities.get(k) != v
        )
        if drift:
            raise RunRefused(f"contract identity drift: {drift}")
        if not self.expected_contract_identities:
            raise RunRefused("no contract identities bound; a check over nothing is not a check")
        self.sequence.advance(S.S2_CONTRACT_IDENTITY_VERIFIED)

    def _bind_config(self) -> None:
        if self.config_mapping != self.expected_config_mapping:
            raise RunRefused(
                f"configuration mismatch: {self.config_mapping} != {self.expected_config_mapping}"
            )
        self.sequence.advance(S.S3_CONFIG_BOUND)

    def _verify_runtime(self) -> None:
        drift = sorted(
            k for k, v in self.expected_runtime_facts.items() if self.runtime_facts.get(k) != v
        )
        if drift:
            raise RunRefused(f"numeric runtime mismatch: {drift}")
        self.sequence.advance(S.S4_RUNTIME_VERIFIED)

    def _stage_inputs(self) -> None:
        """Open prefixes are staged by the ordinary principal BEFORE the run; the validation set is
        only REGISTERED here, never touched."""
        registered = self.registered_objects.get(VALIDATION, set())
        if not registered:
            raise RunRefused("no validation objects registered")
        for obj in self.inputs:
            if obj.key not in registered:
                raise RunRefused(f"input outside the registered set: {obj.key}")
        self.sequence.advance(S.S5_INPUTS_STAGED)

    def _prepare_outputs(self) -> None:
        P.ensure_root(self.output_root)
        self.sequence.advance(S.S6_OUTPUTS_PREPARED)

    def preflight(self) -> None:
        self._verify_code_identity()
        self._verify_contract_identity()
        self._bind_config()
        self._verify_runtime()
        self._stage_inputs()
        self._prepare_outputs()
        self.sequence.advance(S.S7_PRE_ACCESS_READY)

    # -- the seam ---------------------------------------------------------------------
    def _assume_reader(self) -> None:
        self.sequence.assert_may_assume_reader()
        self.guard.pre_access_ready = True
        self.sequence.advance(S.S8_READER_ASSUMED)

    def _consume_opening(self) -> dict[str, bytes]:
        payloads = dict(self.staged_open_prefix_payloads)
        for obj in self.inputs:
            self.guard.open_object(VALIDATION, obj.key, version_id=obj.version_id)
            payloads[obj.key] = self.reader.read(obj)
            if self.sequence.state == S.S8_READER_ASSUMED:
                self.sequence.advance(S.S9_OPENING_CONSUMED)
        return payloads

    # -- the run ----------------------------------------------------------------------
    def run(self, *, stop_at: str | None = None) -> RunOutcome:
        outcome = RunOutcome()
        try:
            self.preflight()
            if stop_at == S.S7_PRE_ACCESS_READY:
                outcome.disposition = P.PASS
                outcome.exit_code = 0
                return outcome

            self._assume_reader()
            payloads = self._consume_opening()

            pairs = self.candidate_source.candidates(payloads)
            outcome.refusal_census = self._require_refusal_census()
            if not pairs:
                raise RunRefused(
                    "candidate source produced nothing; a run over zero candidates "
                    "cannot certify anything"
                )
            records = [E.enrich(d, f) for d, f in pairs]
            adjudications = [
                A.adjudicate_entry(r, f) for r, (_d, f) in zip(records, pairs, strict=True)
            ]
            self.sequence.advance(S.S10_ENRICHED)

            outcome.enrichment_census = C.enrichment_census(records)
            outcome.seam = C.seam_reconciliation(records, adjudications)
            outcome.integrity = C.integrity_census(records, adjudications, self.guard.counts())
            if not outcome.integrity["all_gates_zero"]:
                raise RunRefused(f"integrity gates non-zero: {outcome.integrity}")

            outcome.deliverable_hashes = self._publish_deliverables(
                records, adjudications, outcome.refusal_census
            )
            # The computation is done. What remains is not whether it ran, but whether its
            # population is admissible as governed evidence - a question the gates can only answer
            # AFTER the population exists. A breach publishes FAIL, which is already a registered
            # disposition; no new one is minted, and the opening is spent either way.
            outcome.execution_status = "COMPLETED"
            breached = bool(outcome.refusal_census["any_materiality_gate_breached"])
            outcome.qualification_status = P.FAIL if breached else P.PASS
            outcome.evidence_admissible = not breached
            outcome.disposition = P.FAIL if breached else P.PASS
            outcome.exit_code = P.EXIT_BY_DISPOSITION[outcome.disposition]
        except Exception as exc:  # published verbatim; never reinterpreted
            outcome.disposition = (
                P.INTEGRITY_STOP if isinstance(exc, C.CensusRefused) else P.REFUSED
            )
            outcome.exit_code = P.EXIT_BY_DISPOSITION[outcome.disposition]
            outcome.error = f"{type(exc).__name__}: {exc}"
            outcome.execution_status = outcome.disposition
            outcome.evidence_admissible = False
        finally:
            outcome.state = self.sequence.state
            outcome.opening_consumed = self.sequence.opening_consumed
            outcome.history = list(self.sequence.history)
            # The terminal COMPUTATION outcome is now fixed. Publication may annotate it; it may
            # never overwrite it. The first validation run lost its primary failure exactly here,
            # because a publication exception raised out of `finally` and replaced the disposition
            # that the computation had already established.
            outcome.primary_disposition = outcome.disposition
            outcome.primary_error = outcome.error
            if self.sequence.opening_consumed:
                try:
                    outcome.publication = self._publish_run(outcome)
                except Exception as pub_exc:
                    outcome.publication_error = f"{type(pub_exc).__name__}: {pub_exc}"
                    outcome.published = False
                    # Disposition and error stay as the computation left them.
                    outcome.disposition = outcome.primary_disposition
                    outcome.error = outcome.primary_error
                else:
                    outcome.published = True
                # S11 is reached by PUBLISHING, not by succeeding: a refused run that published its
                # terminal disposition is just as published as a passing one, and the state must
                # say so or the sequence has a terminal state nothing ever enters.
                if self.sequence.state == S.S10_ENRICHED:
                    self.sequence.advance(S.S11_PUBLISHED)
                outcome.state = self.sequence.state
                outcome.history = list(self.sequence.history)
        return outcome

    def _require_refusal_census(self) -> dict:
        """The census is mandatory. A source that cannot account for its units cannot be trusted.

        Deliberately fail-closed rather than defaulting to an empty census: an absent accounting
        would publish as "nothing was refused", which is precisely the silent population change the
        deliverable exists to make impossible.
        """
        produce = getattr(self.candidate_source, "refusal_census", None)
        if not callable(produce):
            raise RunRefused(
                "candidate source cannot produce the mandatory unit-refusal census; unit-scope "
                "refusal without published incidence would let a run PASS on a silently reduced "
                "population"
            )
        return produce()

    def _publish_deliverables(
        self, records: list, adjudications: list, refusal_census: dict
    ) -> dict[str, str]:
        payloads = {
            "ValidationOpenedObjectLedger_v1.0.json": {
                "record_type": "ValidationOpenedObjectLedger",
                "ledger": self.guard.ledger(),
                "counts": self.guard.counts(),
                "chain_verifies": self.guard.chain_verifies(),
            },
            "ValidationExecutionEnrichmentManifest_v1.0.json": {
                "record_type": "ValidationExecutionEnrichmentManifest",
                "records": [r.schema_surface() for r in records],
                "count": len(records),
            },
            "ValidationDecisionExecutionBindingReport_v1.0.json": {
                "record_type": "ValidationDecisionExecutionBindingReport",
                "decision_record_mutations": 0,
                "bindings": [r.decision_record_sha256 for r in records],
                "count": len(records),
            },
            "ValidationUnitReconciliation_v1.0.json": {
                "record_type": "ValidationUnitReconciliation",
                "seam": self.seam_or_empty(records, adjudications),
                "entry_adjudications": [a.as_record() for a in adjudications],
            },
            "ExecutionEnrichmentEdgeCaseCensus_v1.0.json": {
                "record_type": "ExecutionEnrichmentEdgeCaseCensus",
                **C.enrichment_census(records),
            },
            "ValidationSealVerificationReport_v1.0.json": {
                "record_type": "ValidationSealVerificationReport",
                "reader_kind": getattr(self.reader, "reader_kind", "UNKNOWN"),
                "oos_reads": self.guard.counts()["oos_reads"],
                "sealed_reads": self.guard.counts()["sealed_reads"],
                "pinned_reads": list(getattr(self.reader, "reads", [])),
            },
            "ValidationUnitRefusalCensus_v1.0.json": {
                "record_type": "ValidationUnitRefusalCensus",
                **refusal_census,
            },
        }
        return {
            name: P.publish_deliverable(self.output_root, name, body)
            for name, body in payloads.items()
        }

    def seam_or_empty(self, records: list, adjudications: list) -> dict:
        return C.seam_reconciliation(records, adjudications)

    def _publish_run(self, outcome: RunOutcome) -> dict:
        return P.publish_run(
            self.output_root,
            report={
                "record_type": "MR002_ValOOS_Report",
                "run_id": "MR002-SPQ1-P3B-VALIDATION-V1",
                "window": "validation",
                "state_history": outcome.history,
                "enrichment_census": outcome.enrichment_census,
                "seam": outcome.seam,
                "integrity_census": outcome.integrity,
                "unit_refusal_census": outcome.refusal_census,
                "execution_status": outcome.execution_status,
                "qualification_status": outcome.qualification_status,
                "evidence_admissible": outcome.evidence_admissible,
                "error": outcome.error,
            },
            disposition=outcome.disposition,
            exit_code=outcome.exit_code,
            identities=self.identities,
            clock=self.clock,
            deliverable_hashes=outcome.deliverable_hashes,
            stderr_text=outcome.error or "",
        )
