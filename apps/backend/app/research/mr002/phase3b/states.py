"""The S0..S11 launch sequence and the PRE_ACCESS_READY gate.

Everything that can fail without cost must fail before the reader is assumed. The sequence is
ordered so that identity, contract, configuration, runtime, inputs and output destinations are all
proven while a restart still costs nothing; only then may the credential be assumed and the single
validation read performed.

Two asymmetries are deliberate and are the point of the whole design:

  * before S9 a restart is free and consumes nothing;
  * after S9 the opening is spent and a restart is prohibited without adjudication.
"""

from __future__ import annotations

from dataclasses import dataclass, field

S0_INIT = "S0_INIT"
S1_CODE_IDENTITY_VERIFIED = "S1_CODE_IDENTITY_VERIFIED"
S2_CONTRACT_IDENTITY_VERIFIED = "S2_CONTRACT_IDENTITY_VERIFIED"
S3_CONFIG_BOUND = "S3_CONFIG_BOUND"
S4_RUNTIME_VERIFIED = "S4_RUNTIME_VERIFIED"
S5_INPUTS_STAGED = "S5_INPUTS_STAGED"
S6_OUTPUTS_PREPARED = "S6_OUTPUTS_PREPARED"
S7_PRE_ACCESS_READY = "S7_PRE_ACCESS_READY"
S8_READER_ASSUMED = "S8_READER_ASSUMED"
S9_OPENING_CONSUMED = "S9_OPENING_CONSUMED"
S10_ENRICHED = "S10_ENRICHED"
S11_PUBLISHED = "S11_PUBLISHED"

SEQUENCE = (
    S0_INIT,
    S1_CODE_IDENTITY_VERIFIED,
    S2_CONTRACT_IDENTITY_VERIFIED,
    S3_CONFIG_BOUND,
    S4_RUNTIME_VERIFIED,
    S5_INPUTS_STAGED,
    S6_OUTPUTS_PREPARED,
    S7_PRE_ACCESS_READY,
    S8_READER_ASSUMED,
    S9_OPENING_CONSUMED,
    S10_ENRICHED,
    S11_PUBLISHED,
)

GATE = S7_PRE_ACCESS_READY
IRREVERSIBLE = S9_OPENING_CONSUMED


class SequenceViolation(Exception):
    """An out-of-order transition, or an action attempted from a state that forbids it."""


@dataclass
class LaunchSequence:
    """Ordered, no-skip state machine. Every transition is recorded for the run evidence."""

    state: str = S0_INIT
    history: list[str] = field(default_factory=lambda: [S0_INIT])

    def advance(self, to: str) -> None:
        if to not in SEQUENCE:
            raise SequenceViolation(f"unknown state {to}")
        expected = SEQUENCE[SEQUENCE.index(self.state) + 1] if self.state != S11_PUBLISHED else None
        if to != expected:
            raise SequenceViolation(
                f"out-of-order transition {self.state} -> {to}; expected {expected}"
            )
        self.state = to
        self.history.append(to)

    # -- the two questions the rest of the runner asks -------------------------------
    @property
    def pre_access_ready(self) -> bool:
        return SEQUENCE.index(self.state) >= SEQUENCE.index(GATE)

    @property
    def opening_consumed(self) -> bool:
        return SEQUENCE.index(self.state) >= SEQUENCE.index(IRREVERSIBLE)

    def assert_may_assume_reader(self) -> None:
        if self.state != GATE:
            raise SequenceViolation(
                f"the reader may be assumed only from {GATE}, not from {self.state}"
            )

    def assert_may_restart(self) -> None:
        """Free before the opening is consumed; prohibited after, without adjudication."""
        if self.opening_consumed:
            raise SequenceViolation(
                "restart PROHIBITED: the validation opening is consumed. Classify the outcome "
                "under the preregistered failure/recovery rules instead of repairing forward."
            )

    def restart_disposition(self) -> str:
        return "PROHIBITED_WITHOUT_ADJUDICATION" if self.opening_consumed else "PERMITTED_FREE"
