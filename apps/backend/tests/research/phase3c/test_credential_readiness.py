"""Control-path qualification for the bounded pre-sealed-read credential readiness phase.

Owner ruling 2026-08-19. These prove the credential-release state machine only; they add and
exercise no economic, numerical or data semantics.
"""

from __future__ import annotations

import pytest

from app.research.mr002.phase3c.credential_readiness import (
    DEADLINE_SECONDS,
    CredentialReadinessTimeout,
    UnexpectedStsFailure,
    acquire_reader_credentials,
)

ROLE = "arn:aws:iam::219024422756:role/mr002-validation-reader"
SESSION = "mr002-p3c-validation-v1"
CREDS = {"AccessKeyId": "ASIAFAKE", "SecretAccessKey": "s", "SessionToken": "t"}


class FakeClientError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeSts:
    """Records every AssumeRole call. Never touches S3 -- there is no reader here at all."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def assume_role(self, RoleArn, RoleSessionName):        # noqa: N803 - boto3 signature
        self.calls += 1
        assert RoleArn == ROLE
        assert RoleSessionName == SESSION
        outcome = self.script.pop(0) if self.script else "SUCCESS"
        if outcome == "SUCCESS":
            return {"Credentials": dict(CREDS)}
        raise FakeClientError(outcome)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def _run(script, **kw):
    clock = Clock()
    sts = FakeSts(script)
    creds, ev = acquire_reader_credentials(
        sts, ROLE, SESSION, latch_release_epoch=clock.t,
        clock=clock, sleep=clock.sleep, **kw)
    return sts, creds, ev, clock


# ---- 1. several AccessDenied -> success -> exactly ONE transition into reader construction ------
def test_denied_then_success_makes_exactly_one_transition():
    sts, creds, ev, _ = _run(["AccessDenied"] * 40 + ["SUCCESS"])
    assert creds == CREDS
    assert sts.calls == 41
    assert ev["denied_before_success"] == 40
    assert ev["attempts"] == 41


# ---- 2. timeout -> raises so the caller restores containment and STOPs --------------------------
def test_timeout_raises_for_containment_restoration():
    clock = Clock()
    sts = FakeSts(["AccessDenied"] * 100000)
    with pytest.raises(CredentialReadinessTimeout) as exc:
        acquire_reader_credentials(sts, ROLE, SESSION, latch_release_epoch=clock.t,
                                   clock=clock, sleep=clock.sleep)
    assert "UNCONSUMED" in str(exc.value)
    assert clock.t - 1000.0 <= DEADLINE_SECONDS


# ---- 3. an unexpected STS failure class stops IMMEDIATELY, without retrying ---------------------
@pytest.mark.parametrize("code", [
    "MalformedPolicyDocument", "ValidationError", "NoSuchEntity", "ExpiredToken",
    "Throttling", "ThrottlingException", "InvalidClientTokenId", "RegionDisabledException",
    "EndpointConnectionError", "AccessDeniedException",
])
def test_unexpected_failure_class_stops_immediately(code):
    clock = Clock()
    sts = FakeSts([code, "SUCCESS"])
    with pytest.raises(UnexpectedStsFailure):
        acquire_reader_credentials(sts, ROLE, SESSION, latch_release_epoch=clock.t,
                                   clock=clock, sleep=clock.sleep)
    assert sts.calls == 1, "must not attempt again after an unexpected failure class"


def test_unexpected_failure_after_denials_still_stops():
    clock = Clock()
    sts = FakeSts(["AccessDenied", "AccessDenied", "MalformedPolicyDocument", "SUCCESS"])
    with pytest.raises(UnexpectedStsFailure):
        acquire_reader_credentials(sts, ROLE, SESSION, latch_release_epoch=clock.t,
                                   clock=clock, sleep=clock.sleep)
    assert sts.calls == 3


# ---- 4. success is followed by NO discretionary pause -------------------------------------------
def test_no_pause_after_success():
    clock = Clock()
    sts = FakeSts(["AccessDenied", "SUCCESS"])
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        clock.t += s

    acquire_reader_credentials(sts, ROLE, SESSION, latch_release_epoch=clock.t,
                               clock=clock, sleep=sleep)
    # exactly one backoff, between the denial and the success; nothing after
    assert len(sleeps) == 1


# ---- 5. zero sealed reads during failed readiness attempts --------------------------------------
def test_zero_sealed_reads_during_readiness():
    sts, _, ev, _ = _run(["AccessDenied"] * 10 + ["SUCCESS"])
    assert ev["sealed_reads_during_readiness"] == 0
    # the fake STS is the ONLY collaborator; no reader/S3 object is constructible from here
    assert not hasattr(sts, "get_object")


# ---- 6. no second AssumeRole after the first success --------------------------------------------
def test_no_second_assume_role_after_success():
    sts, _, _, _ = _run(["SUCCESS", "SUCCESS"])
    assert sts.calls == 1


# ---- 7. the deadline is measured from LATCH RELEASE, not from process start ---------------------
def test_deadline_is_anchored_to_latch_release():
    clock = Clock()
    release = clock.t - 880.0                      # latch was released 880s ago
    sts = FakeSts(["AccessDenied"] * 100000)
    with pytest.raises(CredentialReadinessTimeout):
        acquire_reader_credentials(sts, ROLE, SESSION, latch_release_epoch=release,
                                   clock=clock, sleep=clock.sleep)
    assert clock.t - release <= DEADLINE_SECONDS


def test_success_just_inside_the_deadline_is_accepted():
    clock = Clock()
    release = clock.t
    sts = FakeSts(["AccessDenied"] * 50 + ["SUCCESS"])
    creds, ev = acquire_reader_credentials(sts, ROLE, SESSION, latch_release_epoch=release,
                                           clock=clock, sleep=clock.sleep)
    assert creds == CREDS
    assert ev["elapsed_since_release_seconds"] < DEADLINE_SECONDS


# ---- 8. backoff is modest, not a 1 Hz load test -------------------------------------------------
def test_backoff_is_modest_and_capped():
    clock = Clock()
    sts = FakeSts(["AccessDenied"] * 30 + ["SUCCESS"])
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        clock.t += s

    acquire_reader_credentials(sts, ROLE, SESSION, latch_release_epoch=clock.t,
                               clock=clock, sleep=sleep)
    assert min(sleeps) >= 2.0
    assert max(sleeps) <= 10.0
    assert sleeps[-1] == 10.0, "backoff should have grown to the cap"


# ---- evidence is complete enough to audit the phase ---------------------------------------------
def test_evidence_records_the_readiness_phase():
    _, _, ev, _ = _run(["AccessDenied"] * 3 + ["SUCCESS"])
    assert ev["phase"] == "pre_sealed_read_credential_readiness"
    assert ev["role_arn"] == ROLE
    assert ev["retryable_class_only"] == "AccessDenied"
    assert ev["deadline_seconds"] == DEADLINE_SECONDS
    assert len(ev["attempt_log"]) == 4
    assert [a["outcome"] for a in ev["attempt_log"]][-1] == "SUCCESS"
    assert "propagation probes, not validation retries" in ev["note"]
