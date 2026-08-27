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
    #: Set when a result is computed from caller-injected inputs that carry no governed authority.
    #: Such a result is diagnostic even if every session was admissible.
    ungoverned_inputs: tuple[str, ...] = ()
    definition_source: str = ""

    def __post_init__(self) -> None:
        for t in self.tokens:
            if not isinstance(t, AdmissibilityToken):
                raise TypeError(
                    f"KResult.tokens must contain AdmissibilityToken objects, got {type(t).__name__}; "
                    f"evidentiary status is derived from real tokens and cannot be asserted"
                )

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
            "ungoverned_inputs": list(self.ungoverned_inputs),
            "definition_source": self.definition_source,
            # Stated in the record itself, so the distinction survives being pasted somewhere else.
            "evidentiary_note": (
                "evidentiary=true means every session below passed the section 7.1 admissibility "
                "check before this value was computed, and no ungoverned caller-injected input "
                "contributed to it. evidentiary=false means this is a diagnostic number and is NOT a "
                "governed K-value."
            ),
        }
