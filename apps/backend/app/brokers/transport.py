"""Governed transport boundary (ADR 0043 WS5 Control 2).

Every outbound broker request funnels through :class:`GovernedTransport`, which
consults :class:`~app.brokers.policy.BrokerAccessPolicy` **before** handing
anything to the HTTP sender. A denied operation therefore produces zero network
calls — the test suite asserts the sender's call count, not merely that an
exception was raised, because "raised after sending" would still have reached
Alpaca.

Escapes this boundary is written to close:

* non-GET methods in read-only mode;
* paths outside the exact allow-list, including traversal (``..``) forms;
* absolute URLs and alternate Alpaca hosts;
* redirects to unapproved routes;
* generic passthrough helpers.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol
from urllib.parse import urlsplit

import structlog

from app.brokers.exceptions import BrokerConfigurationError, BrokerOperationDenied
from app.brokers.policy import BrokerAccessPolicy, normalise_path

logger = structlog.get_logger(__name__)

#: The only host this transport will talk to in a paper deployment. An absolute
#: URL naming anything else is refused rather than rewritten.
PAPER_HOST = "paper-api.alpaca.markets"
LIVE_HOST = "api.alpaca.markets"


class HttpSender(Protocol):
    """Minimal sender seam. Real deployments inject an HTTP client; tests inject
    a counter so denial can be asserted as *zero* calls."""

    def __call__(
        self, method: str, url: str, *, headers: dict[str, str], timeout: float
    ) -> tuple[int, dict[str, str], bytes]: ...


class GovernedTransport:
    """Policy-enforcing request dispatcher.

    The policy check is the first statement in :meth:`request`; nothing below it
    runs for a denied call.
    """

    def __init__(
        self,
        *,
        policy: BrokerAccessPolicy,
        base_url: str,
        sender: HttpSender,
        headers_factory: Callable[[], dict[str, str]],
        timeout: float = 30.0,
        max_redirects: int = 0,
    ) -> None:
        host = urlsplit(base_url).hostname or ""
        if host not in (PAPER_HOST, LIVE_HOST):
            raise BrokerConfigurationError(f"base_url host {host!r} is not an approved Alpaca host")
        self._policy = policy
        self._base_url = base_url.rstrip("/")
        self._host = host
        self._sender = sender
        self._headers_factory = headers_factory
        self._timeout = timeout
        self._max_redirects = max_redirects

    @property
    def policy(self) -> BrokerAccessPolicy:
        return self._policy

    def request(self, method: str, path: str, *, params: dict[str, Any] | None = None) -> Any:
        """Dispatch one request, or raise before touching the sender."""
        # Normalise ONCE, then authorise and dispatch the identical string.
        # Checking one form and sending another is a parser-differential: a path
        # could be approved as /v2/orders and transmitted as something else.
        target_path = normalise_path(self._resolve_path(path))

        # ---- policy gate: nothing below runs for a denied call ----
        self._policy.check_route(method, target_path)

        url = self._base_url + target_path
        if params:
            from urllib.parse import urlencode

            url = f"{url}?{urlencode(params, doseq=True)}"

        status, headers, body = self._sender(
            method.upper(), url, headers=self._headers_factory(), timeout=self._timeout
        )

        if status in (301, 302, 303, 307, 308):
            location = headers.get("Location") or headers.get("location") or ""
            # A redirect is re-authorised as if it were a fresh request. With
            # max_redirects=0 (the WS5 default) it is refused outright.
            if self._max_redirects <= 0:
                raise BrokerOperationDenied(
                    f"{method.upper()} {target_path}",
                    self._policy.mode.value,
                    f"redirect to {location!r} refused (redirects disabled)",
                )
            raise BrokerOperationDenied(
                f"{method.upper()} {target_path}",
                self._policy.mode.value,
                "redirect following is not implemented at the governed boundary",
            )

        if status >= 400:
            raise BrokerOperationDenied(
                f"{method.upper()} {target_path}",
                self._policy.mode.value,
                f"broker returned HTTP {status}",
            )

        if not body:
            return None
        return json.loads(body.decode("utf-8"))

    # ---- deliberately absent ----
    # No get()/post()/raw()/passthrough helper exists. A generic escape hatch
    # would let a call site pass an arbitrary method+path pair that satisfies
    # the signature while defeating the allow-list's intent.

    def _resolve_path(self, path: str) -> str:
        """Reject absolute URLs and alternate hosts; return a server-relative path."""
        if "://" in path:
            parts = urlsplit(path)
            if parts.hostname != self._host:
                raise BrokerOperationDenied(
                    path,
                    self._policy.mode.value,
                    f"absolute URL host {parts.hostname!r} is not the bound broker host",
                )
            return parts.path or "/"
        if path.startswith("//"):
            raise BrokerOperationDenied(
                path, self._policy.mode.value, "protocol-relative URL refused"
            )
        return path if path.startswith("/") else "/" + path
