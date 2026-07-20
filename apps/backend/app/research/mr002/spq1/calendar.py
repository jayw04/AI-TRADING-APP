"""Registered exchange calendar (SIG-01/02). Registered sessions only — no calendar arithmetic.

Sessions are addressed by their registered ordinal index. A decision session ``t`` is an index
into the registered session list; windows are taken over registered ordinals (t-60..t-1), never
over calendar days. The calendar is identity-bound (its SHA-256 is a frozen input identity).
"""
from __future__ import annotations

from dataclasses import dataclass

from .identities import canonical_sha256
from .refusals import refuse


@dataclass(frozen=True)
class RegisteredCalendar:
    """An ordered, de-duplicated list of registered session dates (ISO strings)."""

    sessions: tuple[str, ...]

    def __post_init__(self) -> None:
        if list(self.sessions) != sorted(self.sessions):
            raise refuse(
                "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH",
                "registered sessions are not in ascending order",
            )
        if len(set(self.sessions)) != len(self.sessions):
            raise refuse(
                "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH",
                "registered sessions contain duplicates",
            )

    @property
    def identity(self) -> str:
        return canonical_sha256(list(self.sessions))

    def __len__(self) -> int:
        return len(self.sessions)

    def ordinal(self, session: str) -> int:
        try:
            return self.sessions.index(session)
        except ValueError:
            raise refuse(
                "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH",
                f"session {session} not in the registered calendar",
            ) from None

    def window_ordinals(self, t: int, length: int) -> range:
        """The registered ordinals ``t-length .. t-1`` (coefficient window). Fails closed
        if the window would run before the start of the registered calendar."""
        if t - length < 0:
            raise refuse(
                "INELIGIBLE:OLS_WINDOW_INSUFFICIENT",
                f"insufficient registered history for window ending {t - 1} (need {length})",
            )
        return range(t - length, t)
