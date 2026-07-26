"""No test in this package may reach AWS (ADR 0046 Decision 16).

The Step 4A implementation is proven against `botocore.stub.Stubber` and nothing else. A test that
quietly acquired credentials and talked to a real endpoint would be a live AWS call in a change that is
explicitly not authorized to make one — and it would pass, which is worse.

So the transport itself is severed for every test here: `URLLib3Session.send` is the single choke point
every botocore request passes through, and it raises. A stubbed call never reaches it; anything that
escapes the stub fails loudly and names itself.
"""

from __future__ import annotations

import ssl

import pytest
from botocore.httpsession import URLLib3Session


def _truststore_is_injected() -> bool:
    """Whether `ssl.SSLContext` is currently truststore's.

    Detected by the class's defining module rather than by comparing against a value captured at import
    time: this conftest is imported during COLLECTION, and whether the injection has already happened by
    then depends on which test modules pytest imported first. A captured-at-import baseline would
    therefore be the truststore class in exactly the runs that need fixing.
    """
    return getattr(ssl.SSLContext, "__module__", "").startswith("truststore")


class LiveAwsCallAttempted(AssertionError):
    """A test tried to send a real HTTP request to AWS."""


@pytest.fixture(autouse=True)
def _no_live_aws(monkeypatch):
    def _refuse(self, request, *args, **kwargs):  # noqa: ANN001 - signature mirrors botocore
        raise LiveAwsCallAttempted(
            f"a live AWS request was attempted ({getattr(request, 'method', '?')} "
            f"{getattr(request, 'url', '?')}); Step 4A is Stubber-only")

    monkeypatch.setattr(URLLib3Session, "send", _refuse)


@pytest.fixture(autouse=True)
def _stdlib_ssl_for_client_construction():
    """Build boto3 clients against the STDLIB `ssl`, not the truststore-injected one.

    ADR 0017 has `app/utils/tls_trust.enable_os_trust_store()` call `truststore.inject_into_ssl()`,
    which replaces `ssl.SSLContext` process-wide so outbound TLS verifies against the OS trust store
    (the Norton-interception fix). Whether that injection has happened depends on which modules the
    test session imported before reaching this package — it is ambient, process-global state.

    Constructing a botocore client under the injected context can exhaust the recursion limit:
    `tests/services/test_variant_invalidation.py` followed by this package's factory test reproduces
    `RecursionError` in `ssl.py` on Windows, while either alone passes. That made these tests
    order-dependent — green in isolation, red in the full suite — which is the failure mode that hides
    real defects rather than surfacing them.

    Extracting the injection for the duration of these tests is safe and honest: nothing here opens a
    TLS connection at all (`_no_live_aws` severs the transport, and every call is stubbed), so the OS
    trust store is irrelevant to what is being proven. The injection is restored afterwards so no other
    test observes a changed `ssl` module.

    This is a test-isolation fix, deliberately NOT a change to the ADR-0017 product behaviour. The
    underlying truststore/botocore recursion is a separate finding and belongs in its own change.
    """
    try:
        import truststore
    except ImportError:                           # pragma: no cover - truststore is a hard dependency
        yield
        return

    injected = _truststore_is_injected()
    if injected:
        truststore.extract_from_ssl()
    try:
        yield
    finally:
        if injected:
            truststore.inject_into_ssl()
