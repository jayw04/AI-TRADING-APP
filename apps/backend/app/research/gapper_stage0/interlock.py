"""Execution interlock — no governed verdict without the owner token (memo §6.11).

Stage-0 **execution** is blocked on the G4 ruling / §9 sequencing. The harness
therefore refuses to emit any GO/HOLD/STOP verdict unless the caller supplies a
path to an owner-provisioned token file whose exact content equals
:data:`EXECUTION_TOKEN`. Absent or mismatched ⇒ the verdict seam returns
``NOT_EVALUABLE`` with reason :data:`NOT_AUTHORIZED_REASON`.

Census, funnel, and fidelity outputs are *measurements*, not verdicts — they
never require the token.
"""

from __future__ import annotations

from pathlib import Path

#: Exact required content of the owner-supplied token file.
EXECUTION_TOKEN = "G4-STAGE0-EXECUTION-AUTHORIZED"

#: The frozen refusal reason surfaced on every unauthorized verdict request.
NOT_AUTHORIZED_REASON = "execution not authorized (G4/§9)"


def verify_execution_token(token_path: str | Path | None) -> bool:
    """True iff ``token_path`` names a readable file whose stripped content
    equals :data:`EXECUTION_TOKEN`. Never raises: any failure is False."""
    if token_path is None:
        return False
    try:
        content = Path(token_path).read_text(encoding="utf-8")
    except OSError:
        return False
    return content.strip() == EXECUTION_TOKEN
