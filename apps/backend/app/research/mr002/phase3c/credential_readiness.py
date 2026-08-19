"""Bounded pre-sealed-read credential acquisition for the governed validation run.

Owner ruling 2026-08-19. Removing the latch Deny is acknowledged by the IAM control plane
immediately but is NOT in force at the STS enforcement path for minutes: the transition was
MEASURED at +286.1s (283 consecutive AccessDenied at 1Hz, then 590 consecutive successes, zero
denials). Latch cycle #2 failed because the executor called AssumeRole 5 seconds after release.

The fix belongs here, in credential release -- NOT in the reader's trust policy, which was proven
non-defective (three trust forms, including the live one, each admitted the host role 8/8) and is
frozen.

    latch release -> bounded STS readiness acquisition -> first successful AssumeRole
                  -> immediately begin the governed 6+4 sequence

Repeated AccessDenied responses here are propagation probes, not validation retries: no reader
credentials have been issued and no sealed or reference byte has been read. The opening is
consumed by the first sealed VALIDATION READ, never by a failed STS attempt.

The first successful AssumeRole is a ONE-WAY BOUNDARY. After it there is no further credential
attempt, no restart, and no discretionary inspection.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

# Only this failure is attributable to propagation and therefore retryable.
RETRYABLE_ERROR_CODE = "AccessDenied"
DEADLINE_SECONDS = 900.0
BACKOFF_SCHEDULE = (2.0, 2.0, 5.0, 5.0, 5.0, 10.0)     # then 10.0 for the remainder
MEASURED_PROPAGATION_SECONDS = 286.1


class CredentialReadinessTimeout(RuntimeError):
    """The latch release never became effective within the bound deadline. Restore and STOP."""


class UnexpectedStsFailure(RuntimeError):
    """An STS failure outside the single retryable readiness class. Restore and STOP."""


def _error_code(exc: BaseException) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code")
        if code:
            return str(code)
    return type(exc).__name__


def _backoff(attempt: int) -> float:
    idx = attempt - 1
    if idx < len(BACKOFF_SCHEDULE):
        return BACKOFF_SCHEDULE[idx]
    return BACKOFF_SCHEDULE[-1]


def acquire_reader_credentials(
    sts_client: Any,
    role_arn: str,
    session_name: str,
    latch_release_epoch: float | None = None,
    deadline_seconds: float = DEADLINE_SECONDS,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[dict, dict]:
    """Acquire reader credentials, tolerating ONLY propagation-attributable AccessDenied.

    Returns (credentials, evidence). Raises CredentialReadinessTimeout or UnexpectedStsFailure.
    Makes exactly one successful AssumeRole call and never calls again afterwards.
    """
    started = clock()
    origin = latch_release_epoch if latch_release_epoch is not None else started
    deadline = origin + deadline_seconds

    attempts: list[dict] = []
    attempt = 0
    while True:
        attempt += 1
        t0 = clock()
        try:
            creds = sts_client.assume_role(
                RoleArn=role_arn, RoleSessionName=session_name)["Credentials"]
        except Exception as exc:                       # noqa: BLE001 - classified immediately
            code = _error_code(exc)
            attempts.append({"attempt": attempt, "at": t0, "since_release": t0 - origin,
                             "outcome": code})
            if code != RETRYABLE_ERROR_CODE:
                raise UnexpectedStsFailure(
                    f"STS failure outside the readiness class on attempt {attempt}: {code}. "
                    "The bound IAM state may differ from the package. Restore containment and "
                    "STOP."
                ) from exc
            now = clock()
            wait = _backoff(attempt)
            if now + wait >= deadline:
                raise CredentialReadinessTimeout(
                    f"latch release did not become effective within {deadline_seconds:.0f}s "
                    f"({attempt} attempts, {now - origin:.1f}s since release). Restore "
                    "containment, preserve evidence, STOP. The opening remains UNCONSUMED."
                ) from exc
            sleep(wait)
            continue

        # ---- ONE-WAY BOUNDARY: credentials issued. No further attempt, no pause. -------------
        t1 = clock()
        attempts.append({"attempt": attempt, "at": t0, "since_release": t0 - origin,
                         "outcome": "SUCCESS"})
        evidence = {
            "phase": "pre_sealed_read_credential_readiness",
            "role_arn": role_arn,
            "session_name": session_name,
            "latch_release_epoch": origin,
            "deadline_seconds": deadline_seconds,
            "attempts": len(attempts),
            "denied_before_success": sum(1 for a in attempts if a["outcome"] != "SUCCESS"),
            "elapsed_since_release_seconds": round(t1 - origin, 3),
            "measured_reference_propagation_seconds": MEASURED_PROPAGATION_SECONDS,
            "retryable_class_only": RETRYABLE_ERROR_CODE,
            "sealed_reads_during_readiness": 0,
            "attempt_log": attempts,
            "note": ("Failed attempts here are propagation probes, not validation retries. "
                     "The opening is consumed by the first sealed validation read."),
        }
        return creds, evidence
