"""Shared governed-session argument handling for the Layer 2 construction tools.

The Layer 2 toolchain was written for exactly one session (2026-07-27) and carried that date as a
module constant in nine scripts, plus a `GOVERNED_CUTOFF` constant in the extractor and the corpus
builder. Generalizing it to a per-run parameter is not merely a convenience.

A *default* session is the wrong shape for a governed boundary. Forgetting the flag would silently
produce the PREVIOUS session's evidence, and every downstream digest would still verify — because all
of them would be internally consistent with the wrong session. There is no hash that catches this
class of error, and no later gate that can distinguish it from a correct build: the corpus, the
manifest, the attestation and the readiness receipt would all agree with one another and all be wrong
together. The only available defence is to make the boundary an explicit act of the operator.

Hence: no defaults anywhere in this module, and every argument it registers is `required=True`.
"""

from __future__ import annotations

import argparse
from datetime import date

SESSION_HELP = (
    "the governed session date (YYYY-MM-DD). Required and deliberately without a default: a default "
    "would silently produce the previous session's evidence, and every downstream digest would still "
    "verify because all of them would be internally consistent with it."
)


def session_date(raw: str) -> date:
    """Parse and validate a governed session date.

    Kept strict — `date.fromisoformat` only, no tolerant formats. An operator who mistypes a session
    must get a refusal, not a nearby date.
    """
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"session must be an ISO date (YYYY-MM-DD), got {raw!r}") from exc


def add_session_argument(ap: argparse.ArgumentParser, flag: str = "--session") -> None:
    """Register the required governed-session argument on `ap`."""
    ap.add_argument(flag, required=True, type=session_date, help=SESSION_HELP)
