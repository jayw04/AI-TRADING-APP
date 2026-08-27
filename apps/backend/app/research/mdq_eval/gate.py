"""The §7.1 admissibility gate — the only place an `AdmissibilityToken` is minted.

Every governed K-value must be downstream of an admissibility decision that actually passed. This
module is the single point where that decision is turned into a capability, so there is exactly one
place to audit and exactly one place that could ever be wrong.

⛔ **UNDETERMINED is not a pass.** The §7.1 adjudicator has three verdicts, and only ADMISSIBLE mints
a token. Treating UNDETERMINED as admissible would convert "we could not tell" into evidence, which is
worse than either a clean pass or a clean refusal because it looks like a pass in every summary.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.research.capture.admissibility import AdmissibilityReport, Verdict, assess_partition
from app.research.mdq_eval.results import AdmissibilityToken, _mint_token


class NotAdmissible(RuntimeError):
    """The partition did not pass §7.1, so no evidentiary K-value may be computed over it.

    Raised rather than returned: a caller that wanted evidence and got an inadmissible partition has
    asked for something that does not exist, and silently degrading to a diagnostic would hide that.
    Callers who genuinely want a diagnostic ask for one explicitly.
    """


def _digest(report: AdmissibilityReport) -> str:
    """A stable digest of the adjudication, so a token names the decision it came from.

    Without this a token would assert "some assessment passed" rather than "this one did", and two
    runs against different corpora would be indistinguishable in the record.
    """
    payload = json.dumps(report.as_dict(), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def require_admissible(
    root: Path | str,
    session: date,
    *,
    session_close_utc: datetime | None,
    **assess_kwargs: Any,
) -> tuple[AdmissibilityToken, AdmissibilityReport]:
    """Adjudicate one session and mint a token iff it is ADMISSIBLE.

    Returns the report alongside the token deliberately: the caller should be able to record *why*
    the partition was admissible, not merely that something said so.
    """
    report = assess_partition(
        Path(root), session, session_close_utc=session_close_utc, **assess_kwargs
    )
    if report.verdict is not Verdict.ADMISSIBLE:
        not_passing = report.as_dict().get("not_passing", [])
        raise NotAdmissible(
            f"{session} is {report.verdict} under the section 7.1 admissibility check, so no "
            f"evidentiary K-value may be computed over it. Non-passing conditions: "
            f"{json.dumps(not_passing, default=str)}"
        )
    token = _mint_token(
        root=str(Path(root).resolve()),
        session=session,
        verdict=str(report.verdict),
        assessed_at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        admissibility_digest=_digest(report),
    )
    return token, report


def validate_tokens(
    root: Path | str, sessions: Iterable[date], tokens: Iterable[AdmissibilityToken]
) -> tuple[dict[str, Any], ...]:
    """Check that the supplied tokens cover exactly the sessions being evaluated, under this root.

    ⚠ This is not ceremony. Without it, a token minted for an admissible day could be passed
    alongside a *different*, inadmissible day and the result would still be stamped evidentiary — the
    laundering path the token was introduced to close.
    """
    want = {s for s in sessions}
    resolved_root = str(Path(root).resolve())
    by_session: dict[date, AdmissibilityToken] = {}
    for t in tokens:
        if not isinstance(t, AdmissibilityToken):
            raise TypeError(f"not an AdmissibilityToken: {t!r}")
        if t.root != resolved_root:
            raise NotAdmissible(
                f"token for {t.session} was minted under root {t.root}, but evaluation root is "
                f"{resolved_root}; a token does not travel between corpora"
            )
        by_session[t.session] = t

    missing = sorted(s.isoformat() for s in want - set(by_session))
    if missing:
        raise NotAdmissible(
            f"no admissibility token for session(s) {missing}; every evaluated session must have "
            f"passed section 7.1 before its data becomes evidence"
        )
    extra = sorted(s.isoformat() for s in set(by_session) - want)
    if extra:
        raise NotAdmissible(
            f"token(s) supplied for session(s) {extra} that are not being evaluated; refusing rather "
            f"than silently ignoring evidence of a scope mismatch"
        )
    return tuple(by_session[s].as_dict() for s in sorted(want))
