"""The reader crosses a governed privilege boundary, and only that one.

v3 bound a package that reached PRE_ACCESS_READY faithfully and then could not cross it: its
`s3_reader` built an ambient-credential S3 client, so the read would have been attempted as the
qualified host role -- which holds an explicit Deny on the sealed bucket, and which the owner
requires to keep it. The only sanctioned path is to assume `mr002-validation-reader` and build the
S3 client from the temporary credentials that returns.

What these tests protect:

  * a dry run never calls STS, so PRE_ACCESS_READY still costs nothing;
  * there is NO ambient fallback -- a failed assumption refuses before any S3 call rather than
    quietly reading as the host role;
  * the role ARN is bound in the module, not supplied at runtime;
  * only the returned temporary credentials construct the S3 client.
"""

from __future__ import annotations

import inspect

import pytest

from app.research.mr002.phase3b import entrypoint as EP
from app.research.mr002.phase3b.readers import PinnedObject

CREDS = {
    "AccessKeyId": "ASIAREADER",
    "SecretAccessKey": "reader-secret",
    "SessionToken": "reader-token",
}


class FakeS3:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []

    def get_object(self, **kw):
        self.calls.append(kw)
        return {"Body": _Body(b"payload")}


class _Body:
    def __init__(self, data):
        self._d = data

    def read(self):
        return self._d


class FakeSTS:
    def __init__(self, *, credentials=CREDS, error=None):
        self.credentials = credentials
        self.error = error
        self.calls = []

    def assume_role(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return {"Credentials": self.credentials} if self.credentials is not None else {}


class FakeBoto3:
    """Records every client built, so a hidden ambient client cannot go unnoticed."""

    def __init__(self, sts=None):
        self.sts = sts or FakeSTS()
        self.built = []

    def client(self, service, **kwargs):
        self.built.append((service, kwargs))
        if service == "sts":
            return self.sts
        return FakeS3(**kwargs)


OBJ = PinnedObject(
    "workbench-mr002-sealed-219024422756",
    "validation/prices.parquet",
    "ver-1",
    __import__("hashlib").sha256(b"payload").hexdigest(),
)


# -- laziness: PRE_ACCESS_READY must still cost nothing -------------------------------------


def test_constructing_the_reader_calls_no_sts_and_builds_no_client():
    b3 = FakeBoto3()
    reader = EP.s3_reader(boto3_module=b3)
    assert b3.built == [], "a client was built at construction time"
    assert b3.sts.calls == [], "STS was called before any read"
    assert reader._client is None


def test_a_dry_run_never_calls_sts():
    """The whole point of dry: no credential transition happens at all."""
    b3 = FakeBoto3()
    EP.s3_reader(boto3_module=b3)
    # Nothing beyond construction happens in dry mode; the reader is never read from.
    assert b3.sts.calls == [] and b3.built == []


# -- the privilege transition ----------------------------------------------------------------


def test_the_first_read_assumes_the_reader_role_then_builds_s3_from_its_credentials():
    b3 = FakeBoto3()
    reader = EP.s3_reader(boto3_module=b3)
    reader.read(OBJ)

    assert [svc for svc, _ in b3.built] == ["sts", "s3"], "s3 must be built AFTER the assumption"
    assert b3.sts.calls == [
        {"RoleArn": EP.VALIDATION_READER_ROLE_ARN, "RoleSessionName": EP.READER_SESSION_NAME}
    ]
    _, s3_kwargs = b3.built[1]
    assert s3_kwargs["aws_access_key_id"] == CREDS["AccessKeyId"]
    assert s3_kwargs["aws_secret_access_key"] == CREDS["SecretAccessKey"]
    assert s3_kwargs["aws_session_token"] == CREDS["SessionToken"]


def test_the_s3_client_is_built_from_temporary_credentials_only():
    """No ambient client: every S3 client must carry an explicit session token."""
    b3 = FakeBoto3()
    EP.s3_reader(boto3_module=b3).read(OBJ)
    for service, kwargs in b3.built:
        if service == "s3":
            assert kwargs.get("aws_session_token"), "an ambient-credential S3 client was built"


def test_the_role_arn_is_bound_in_the_module_not_supplied_at_runtime():
    """A caller-chosen ARN would let the caller decide which identity reads the sealed store."""
    params = inspect.signature(EP.s3_reader).parameters
    assert "role_arn" not in params and "RoleArn" not in params
    assert EP.VALIDATION_READER_ROLE_ARN.endswith(":role/mr002-validation-reader")
    assert EP.VALIDATION_READER_ROLE_ARN.startswith("arn:aws:iam::219024422756:")


# -- no fallback ------------------------------------------------------------------------------


def test_assumption_failure_refuses_before_any_s3_call():
    b3 = FakeBoto3(sts=FakeSTS(error=RuntimeError("AccessDenied")))
    reader = EP.s3_reader(boto3_module=b3)
    with pytest.raises(EP.ReaderAssumptionRefused, match="could not assume"):
        reader.read(OBJ)
    assert [svc for svc, _ in b3.built] == ["sts"], "an S3 client was built despite the failure"
    assert reader.reads == []


def test_assumption_returning_no_credentials_refuses_rather_than_falling_back():
    b3 = FakeBoto3(sts=FakeSTS(credentials=None))
    with pytest.raises(EP.ReaderAssumptionRefused, match="no usable credentials"):
        EP.s3_reader(boto3_module=b3).read(OBJ)
    assert [svc for svc, _ in b3.built] == ["sts"]


def test_partial_credentials_refuse():
    b3 = FakeBoto3(sts=FakeSTS(credentials={"AccessKeyId": "A", "SecretAccessKey": "B"}))
    with pytest.raises(EP.ReaderAssumptionRefused, match="missing"):
        EP.s3_reader(boto3_module=b3).read(OBJ)


def test_the_source_contains_no_ambient_s3_client_construction():
    """Belt and braces: no `client("s3"` without explicit credentials anywhere in the factory."""
    src = inspect.getsource(EP.s3_reader)
    assert "aws_session_token" in src
    assert src.count('"s3"') == 1, "more than one S3 client construction path"


# -- evidence ---------------------------------------------------------------------------------


def test_the_reader_exposes_the_identity_it_will_assume():
    reader = EP.s3_reader(boto3_module=FakeBoto3())
    assert reader.assumed_role_arn == EP.VALIDATION_READER_ROLE_ARN
    assert reader.reader_session_name == EP.READER_SESSION_NAME


def test_a_successful_read_is_still_pinned_and_verified():
    reader = EP.s3_reader(boto3_module=FakeBoto3())
    reader.read(OBJ)
    assert reader.reads == [(OBJ.key, OBJ.version_id)]
