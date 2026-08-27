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
    admissibility_digest: str

    def __init__(self, *, root: str, session: date, verdict: str, assessed_at: str,
                 admissibility_digest: str, _mint: _TokenMint | None = None) -> None:
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
        object.__setattr__(self, "admissibility_digest", admissibility_digest)

    def as_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "session": self.session.isoformat(),
            "verdict": self.verdict,
            "assessed_at": self.assessed_at,
            "admissibility_digest": self.admissibility_digest,
        }


def _mint_token(*, root: str, session: date, verdict: str, assessed_at: str,
                admissibility_digest: str) -> AdmissibilityToken:
    """⛔ INTERNAL. The single construction site, imported by `gate` and by nothing else.

    ⚠ Do not import this in tests. A test that mints its own "ADMISSIBLE" token is not exercising the
    gate — it is asserting that a bypass works. Tests obtain tokens by driving
    `gate.require_admissible` against a controlled passing adjudication, which is also the only way
    the integration itself gets covered.
    """
    return AdmissibilityToken(
        root=root, session=session, verdict=verdict, assessed_at=assessed_at,
        admissibility_digest=admissibility_digest, _mint=_MINT,
    )


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
        return {"identifier": self.identifier, "digest": self.digest,
                "governed_artifact": self.governed_artifact}


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
                if self.decision_provider_authority else None),
            "defect_list_supplied": self.defect_list_supplied,
            "defect_registry_authority": (
                self.defect_registry_authority.as_dict()
                if self.defect_registry_authority else None),
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
    #: Real tokens only. Anything else is refused at construction.
    tokens: tuple[AdmissibilityToken, ...] = ()
    #: Where the inputs came from. `ungoverned_inputs` is DERIVED from this, not passed in.
    provenance: InputProvenance = field(default_factory=InputProvenance)
    definition_source: str = ""

    def __post_init__(self) -> None:
        for t in self.tokens:
            if not isinstance(t, AdmissibilityToken):
                raise TypeError(
                    f"KResult.tokens must contain AdmissibilityToken objects, got {type(t).__name__}; "
                    f"evidentiary status is derived from real tokens and cannot be asserted"
                )

    @property
    def ungoverned_inputs(self) -> tuple[str, ...]:
        """Stable ids for supplied-but-unbound authorities. Derived from provenance."""
        return self.provenance.ungoverned()

    @property
    def evidentiary(self) -> bool:
        """True iff every evaluated session carried a real admissibility token AND no ungoverned
        caller-injected input contributed to the value."""
        return bool(self.tokens) and not self.ungoverned_inputs

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
