"""No test in this package may reach AWS (ADR 0046 Decision 16).

The Step 4A implementation is proven against `botocore.stub.Stubber` and nothing else. A test that
quietly acquired credentials and talked to a real endpoint would be a live AWS call in a change that is
explicitly not authorized to make one — and it would pass, which is worse.

So the transport itself is severed for every test here: `URLLib3Session.send` is the single choke point
every botocore request passes through, and it raises. A stubbed call never reaches it; anything that
escapes the stub fails loudly and names itself.
"""

from __future__ import annotations

import pytest
from botocore.httpsession import URLLib3Session


class LiveAwsCallAttempted(AssertionError):
    """A test tried to send a real HTTP request to AWS."""


@pytest.fixture(autouse=True)
def _no_live_aws(monkeypatch):
    def _refuse(self, request, *args, **kwargs):  # noqa: ANN001 - signature mirrors botocore
        raise LiveAwsCallAttempted(
            f"a live AWS request was attempted ({getattr(request, 'method', '?')} "
            f"{getattr(request, 'url', '?')}); Step 4A is Stubber-only")

    monkeypatch.setattr(URLLib3Session, "send", _refuse)
