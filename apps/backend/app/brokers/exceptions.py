"""Exceptions for the governed broker boundary (ADR 0043 WS5 controls).

These are deliberately distinct from :mod:`app.brokers.alpaca.errors`, which
classifies responses the broker *sent back*. Everything here is raised
**before** a request reaches the network, so a denial can never be confused
with a broker-side rejection.
"""

from __future__ import annotations


class BrokerBoundaryError(RuntimeError):
    """Base class for governed-boundary failures."""


class BrokerConfigurationError(BrokerBoundaryError):
    """The broker access configuration is absent, unknown, or self-inconsistent.

    Raised at construction/startup. Never downgraded to a warning: an
    unreadable access mode must not resolve to a permissive one.
    """


class BrokerOperationDenied(BrokerBoundaryError):
    """A mutation was refused by policy before transport dispatch.

    Carries the operation name and the mode that refused it so audit records
    can state *what* was attempted, not merely that something failed.
    """

    def __init__(self, operation: str, mode: str, detail: str = "") -> None:
        self.operation = operation
        self.mode = mode
        msg = f"broker operation {operation!r} is denied in mode {mode!r}"
        if detail:
            msg = f"{msg}: {detail}"
        super().__init__(msg)


class BrokerAccountMismatch(BrokerBoundaryError):
    """The broker reported an account identity other than the expected one.

    ADR 0043 §10 treats a broker-identity mismatch as a stop condition, so the
    client latches shut rather than continuing to read from the wrong account.
    """

    def __init__(self, expected: str, actual: str) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"broker account identity mismatch: expected {expected!r}, got {actual!r}")
