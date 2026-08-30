"""Result types for the MDQ-001 K-criteria, and the token that makes a number evidence.

## The rule this module exists to enforce

    "A K-value computed over an inadmissible partition is not evidence, it is a number."
    — MDQ-001 implementation plan, execution-order item 17

That rule is easy to state and easy to lose. Written as a convention it survives exactly as long as
everyone remembers it; written as a comment above a function it survives until someone calls the
function from somewhere else. So it is structural here instead: an evidentiary `KResult` **cannot be
constructed without an `AdmissibilityToken`**, and a token can only be minted by
`mdq_eval.gate.require_admissible`, which mints it only from a §7.1 assessment that actually returned
ADMISSIBLE.

⛔ There is deliberately no way to hand-build a token, no `force=` flag, and no environment override.
A caller who wants a number without a token can still get one — `evaluate(...)` returns a diagnostic
result — but the diagnostic is *labelled* diagnostic and carries `evidentiary=False`, so it cannot be
mistaken for a governed K-value in a record, in a log, or in a later reader's memory.

## Three outcomes, not two

NOT_EVALUABLE is a first-class outcome and is **neither PASS nor FAIL**. The registration is explicit
that a NOT-EVALUABLE criterion can neither satisfy the GO floor nor count toward Cancel. Collapsing it
into FAIL would manufacture evidence of absence; collapsing it into PASS would manufacture evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

#: Bumped when the *meaning* of a result changes, never for cosmetic edits.
K_RESULT_SCHEMA = "mdq-k-result/1"


class KOutcome(StrEnum):
    """The three outcomes a K criterion can have.

    ⛔ `NOT_EVALUABLE` is not a failure. It means the criterion could not be evaluated on this
    evidence at all — a different claim from "evaluated, and it did not meet its threshold".
    """

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class _TokenMint:
    """Private mint marker. Holding one is the only way to construct a token."""

    __slots__ = ()


_MINT = _TokenMint()


@dataclass(frozen=True)
class AdmissibilityToken:
    """Proof that a specific partition passed the §7.1 admissibility check.

    ⚠ Construct only via `mdq_eval.gate.require_admissible`. The `_mint` guard is not decoration: a
    token that anything could build would make the whole gate advisory, which is the same failure
    shape as an integrity check behind a default-off flag.

    The token names the *exact* session and root it was minted for, and the evaluators verify that
    before accepting it — otherwise a token minted for an admissible day could silently launder a
    different, inadmissible one.
    """

    root: str
    session: date
    verdict: str
    assessed_at: str
    #: Run-specific. Identifies THIS adjudication, not the partition bytes: the hashed report
    #: carries generated_at, so it differs across runs over identical data. Previously named
    #: admissibility_digest, which read as a content hash and is not one. Algorithm unchanged.
    adjudication_instance_digest: str
    #: Deterministic identity of the adjudicated bytes, from the frozen manifests' per-file
    #: entries only. Two runs over an unchanged partition produce the SAME value. This is the
    #: field that answers "did we read the same data", which the run digest cannot.
    input_partition_identity: str

    def __init__(
        self,
        *,
        root: str,
        session: date,
        verdict: str,
        assessed_at: str,
        adjudication_instance_digest: str,
        input_partition_identity: str,
        _mint: _TokenMint | None = None,
    ) -> None:
        if _mint is not _MINT:
            raise TypeError(
                "AdmissibilityToken cannot be constructed directly; it is minted only by "
                "mdq_eval.gate.require_admissible from a passing section 7.1 assessment. A token "
                "anyone could build would make the admissibility gate advisory."
            )
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "session", session)
        object.__setattr__(self, "verdict", verdict)
        object.__setattr__(self, "assessed_at", assessed_at)
        object.__setattr__(self, "adjudication_instance_digest", adjudication_instance_digest)
        object.__setattr__(self, "input_partition_identity", input_partition_identity)

    def as_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "session": self.session.isoformat(),
            "verdict": self.verdict,
            "assessed_at": self.assessed_at,
            "adjudication_instance_digest": self.adjudication_instance_digest,
            "input_partition_identity": self.input_partition_identity,
        }


def _mint_token(
    *,
    root: str,
    session: date,
    verdict: str,
    assessed_at: str,
    adjudication_instance_digest: str,
    input_partition_identity: str,
) -> AdmissibilityToken:
    """⛔ INTERNAL. The single construction site, imported by `gate` and by nothing else.

    ⚠ Do not import this in tests. A test that mints its own "ADMISSIBLE" token is not exercising the
    gate — it is asserting that a bypass works. Tests obtain tokens by driving
    `gate.require_admissible` against a controlled passing adjudication, which is also the only way
    the integration itself gets covered.
    """
    return AdmissibilityToken(
        root=root,
        session=session,
        verdict=verdict,
        assessed_at=assessed_at,
        adjudication_instance_digest=adjudication_instance_digest,
        input_partition_identity=input_partition_identity,
        _mint=_MINT,
    )


class _ScopeMint:
    """Private mint marker for ValidatedScope."""

    __slots__ = ()


_SCOPE_MINT = _ScopeMint()


@dataclass(frozen=True)
class ValidatedScope:
    """Proof that a specific set of tokens was validated against a specific evaluation scope.

    ⛔ **Possessing a token is not the same as having validated it.** An earlier revision derived
    `evidentiary` from `bool(tokens)`, so a legitimate token for one session could be lifted out of the
    evaluator and attached to a directly-constructed result naming a different session — becoming
    evidence without `validate_tokens` ever running. That is precisely the laundering the gate exists
    to stop, and the test suite had blessed it.

    The capability therefore binds the root AND the exact session set the tokens were checked against,
    and `KResult` requires the scope to match the sessions it reports.
    """

    root: str
    sessions: tuple[str, ...]
    tokens: tuple[AdmissibilityToken, ...]

    def __init__(
        self,
        *,
        root: str,
        sessions: tuple[str, ...],
        tokens: tuple[AdmissibilityToken, ...],
        _mint: _ScopeMint | None = None,
    ) -> None:
        if _mint is not _SCOPE_MINT:
            raise TypeError(
                "ValidatedScope cannot be constructed directly; it is produced only by "
                "mdq_eval.gate.validate_tokens, which checks the tokens against the exact root and "
                "session set being evaluated. A scope anyone could build would make that check "
                "optional, which is the same hole as deriving evidence from raw token possession."
            )
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "sessions", sessions)
        object.__setattr__(self, "tokens", tokens)

    def as_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "sessions": list(self.sessions),
            "tokens": [t.as_dict() for t in self.tokens],
        }


def _mint_scope(
    *, root: str, sessions: tuple[str, ...], tokens: tuple[AdmissibilityToken, ...]
) -> ValidatedScope:
    """⛔ INTERNAL. Imported by `gate.validate_tokens` and by nothing else."""
    return ValidatedScope(root=root, sessions=sessions, tokens=tokens, _mint=_SCOPE_MINT)


#: Stable identifiers for a missing governing authority. Stable because they end up in records that
#: get copied elsewhere, where prose does not survive but an identifier does.
DECISION_PROVIDER_UNBOUND = "decision_provider_unbound"
PREDECLARED_DEFECT_REGISTRY_UNBOUND = "predeclared_defect_registry_unbound"

_UNGOVERNED_REASONS: dict[str, str] = {
    DECISION_PROVIDER_UNBOUND: (
        "a caller-supplied decision provider was used; no SCAN-001/GAPPER provider has been bound as "
        "the authoritative K1 decision"
    ),
    PREDECLARED_DEFECT_REGISTRY_UNBOUND: (
        "a caller-supplied defect list was used; the registration declares no predeclared "
        "gate-material defect registry"
    ),
}


@dataclass(frozen=True)
class AuthorityRef:
    """An immutable identity for a governed authority binding.

    ⛔ **A boolean is not a binding.** An earlier revision derived "bound" from a module constant, which
    would have replaced the caller-controlled `evidentiary=True` with a module-controlled
    `BOUND=True` — better located, but still an *assertion* standing in for evidence. Flipping one line
    would have made arbitrary injected data evidentiary.

    So a binding must name what it is: an identifier, the digest of the governed artifact that
    establishes it, and a reference to that artifact. The boolean states the current position; this
    proves it.
    """

    identifier: str
    digest: str
    governed_artifact: str

    def __post_init__(self) -> None:
        if not self.identifier.strip():
            raise ValueError("an authority binding needs a non-empty identifier")
        digest = self.digest.strip().lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError(
                f"an authority binding needs the sha256 digest of the governed artifact that "
                f"establishes it, got {self.digest!r}; a binding nothing can be checked against is "
                f"an assertion, not a binding"
            )
        if not self.governed_artifact.strip():
            raise ValueError("an authority binding needs a reference to its governed artifact")

    def as_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "digest": self.digest,
            "governed_artifact": self.governed_artifact,
        }


@dataclass(frozen=True)
class InputProvenance:
    """Where a result's inputs came from, derived from the inputs themselves.

    ⛔ This exists because an earlier revision let the evaluator pass an `ungoverned_inputs` list
    directly — a caller-set flag that could be omitted or cleared, the same defect shape as the
    `evidentiary: bool` field it sat next to. Provenance is computed from whether an authority is
    bound, and binding requires an `AuthorityRef`, not a boolean.

    ⚠ Supplying a callable is not a binding. Setting a module constant is not a binding. A binding is
    a governed artifact with a digest.
    """

    #: Whether each input was supplied at all — the fact the reasons are derived from.
    decision_provider_supplied: bool = False
    defect_list_supplied: bool = False
    #: The governed binding for each authority, or None when unbound. Presence IS the binding.
    decision_provider_authority: AuthorityRef | None = None
    defect_registry_authority: AuthorityRef | None = None

    def ungoverned(self) -> tuple[str, ...]:
        """Stable ids for every supplied-but-unbound authority. Derived, never asserted."""
        out: list[str] = []
        if self.decision_provider_supplied and self.decision_provider_authority is None:
            out.append(DECISION_PROVIDER_UNBOUND)
        if self.defect_list_supplied and self.defect_registry_authority is None:
            out.append(PREDECLARED_DEFECT_REGISTRY_UNBOUND)
        return tuple(out)

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision_provider_supplied": self.decision_provider_supplied,
            "decision_provider_authority": (
                self.decision_provider_authority.as_dict()
                if self.decision_provider_authority
                else None
            ),
            "defect_list_supplied": self.defect_list_supplied,
            "defect_registry_authority": (
                self.defect_registry_authority.as_dict() if self.defect_registry_authority else None
            ),
        }


@dataclass(frozen=True)
class KResult:
    """One K criterion evaluated over one scope.

    ⛔ `evidentiary` is **not a constructor field** and cannot be asserted by a caller. It is derived
    from `tokens`, which must be real `AdmissibilityToken` objects — and those have a single guarded
    mint. An earlier revision took `evidentiary: bool` and token *dictionaries*, which meant
    `KResult(..., evidentiary=True, tokens=())` was constructible and the "structural" claim was
    merely documentary. Deriving it closes that.

    A reader who sees `evidentiary=False` is looking at a number, not a governed K-value, regardless
    of how convincing the number is.
    """

    criterion: str
    outcome: KOutcome
    #: The registered threshold this criterion is measured against, quoted not paraphrased.
    threshold: str
    #: Why the outcome is what it is, in terms a reader can check against the registration.
    detail: str
    #: The frozen definition's own numbers. Diagnostics live here too, labelled.
    measures: dict[str, Any] = field(default_factory=dict)
    sessions: tuple[str, ...] = ()
    #: The validated scope this result was computed under, or None for a diagnostic.
    #: ⛔ NOT an init field. A scope proves the PARTITIONS were admissible; it says nothing about
    #: whether an evaluator produced this outcome. Allowing it at construction let a caller pair a
    #: legitimate scope with a hand-written PASS. Only `_mint_result` — used by the evaluators — can
    #: attach one, so directly constructed results are always diagnostic.
    scope: ValidatedScope | None = field(init=False, default=None)
    #: Where the inputs came from. `ungoverned_inputs` is DERIVED from this, not passed in.
    provenance: InputProvenance = field(default_factory=InputProvenance)
    definition_source: str = ""

    @property
    def tokens(self) -> tuple[AdmissibilityToken, ...]:
        """The tokens behind this result, if any. Derived from the validated scope."""
        return self.scope.tokens if self.scope is not None else ()

    @property
    def ungoverned_inputs(self) -> tuple[str, ...]:
        """Stable ids for supplied-but-unbound authorities. Derived from provenance."""
        return self.provenance.ungoverned()

    @property
    def evidentiary(self) -> bool:
        """True iff a VALIDATED scope covers exactly the sessions reported, and no ungoverned
        caller-injected input contributed to the value.

        ⛔ The scope must match `sessions` exactly. Without that check a scope validated for one set of
        days could be attached to a result reporting another — the laundering path in a second form.
        """
        if self.scope is None or self.ungoverned_inputs:
            return False
        return tuple(self.scope.sessions) == tuple(self.sessions)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": K_RESULT_SCHEMA,
            "criterion": self.criterion,
            "outcome": str(self.outcome),
            "evidentiary": self.evidentiary,
            "threshold": self.threshold,
            "detail": self.detail,
            "measures": self.measures,
            "sessions": list(self.sessions),
            "admissibility_tokens": [t.as_dict() for t in self.tokens],
            "validated_scope": self.scope.as_dict() if self.scope else None,
            "ungoverned_inputs": [
                {"authority": a, "reason": _UNGOVERNED_REASONS[a]} for a in self.ungoverned_inputs
            ],
            "input_provenance": self.provenance.as_dict(),
            "definition_source": self.definition_source,
            # Stated in the record itself, so the distinction survives being pasted somewhere else.
            "evidentiary_note": (
                "evidentiary=true means every session below passed the section 7.1 admissibility "
                "check before this value was computed, and no ungoverned caller-injected input "
                "contributed to it. evidentiary=false means this is a diagnostic number and is NOT a "
                "governed K-value."
            ),
        }


def _mint_result(*, scope: ValidatedScope | None, **fields: Any) -> KResult:
    """⛔ INTERNAL. The single site that can attach a validated scope to a result.

    Imported by the K evaluators and by nothing else. This is what makes the capability chain
    complete:

        require_admissible -> validate_tokens -> ValidatedScope -> EVALUATOR -> evidentiary KResult

    Without it, a caller holding a legitimate scope could hand-write `KResult(outcome=PASS, ...)` and
    it would be evidentiary — the scope having proved only that the partitions were admissible, never
    that this outcome came from evaluating them.
    """
    result = KResult(**fields)
    if scope is not None:
        if not isinstance(scope, ValidatedScope):
            raise TypeError(
                f"scope must be a ValidatedScope from mdq_eval.gate.validate_tokens, got "
                f"{type(scope).__name__}"
            )
        object.__setattr__(result, "scope", scope)
    return result
