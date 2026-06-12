"""Route outbound TLS verification through the OS trust store (ADR 0017).

The alpaca-py SDK — and the requests/httpx/urllib clients underneath it, plus
the Anthropic SDK — verify server certificates against the bundled ``certifi``
CA set, which is INDEPENDENT of the operating system's trust store. On a host
running a TLS-inspecting proxy (e.g. Norton's "encrypted-connection scanning"
on the developer's Windows machine), the proxy MITMs the connection and presents
a certificate signed by a root that IS trusted by the OS store (the proxy
installs it there) but is NOT present in certifi. Result:
``CERTIFICATE_VERIFY_FAILED`` and Alpaca/Anthropic become unreachable — even
though browsers and any OS-trust-store client on the same machine work fine.

``truststore.inject_into_ssl()`` monkeypatches the stdlib ``ssl`` module so that
default-context certificate verification defers to the OS trust store. Because
requests/httpx/urllib all build their contexts from ``ssl``, they pick this up —
so the proxy's root is trusted and HTTPS succeeds WITHOUT disabling the
inspector. This mirrors how the sibling ``claude-trading-view`` app reaches
Alpaca (stdlib ``urllib`` with the default OS-backed context) and never needed
the inspector turned off.

Conservative by construction:
- Idempotent — safe to call from multiple entry points; injects once.
- Never raises — a missing package or injection failure logs and no-ops, so it
  can't take down startup. On a host without an inspecting proxy, certifi keeps
  working unchanged either way.
- Opt-out with ``WORKBENCH_TLS_USE_OS_TRUST=0`` if a deployment needs the
  certifi-only behavior back.
"""

from __future__ import annotations

import os

import structlog

logger = structlog.get_logger(__name__)

_injected = False


def enable_os_trust_store() -> bool:
    """Make outbound TLS verify against the OS trust store. Returns True if the
    injection is active (now or from a prior call), False if disabled/unavailable.

    Call as early as possible at process start — before the first HTTPS
    connection builds an SSL context."""
    global _injected
    if _injected:
        return True
    if os.environ.get("WORKBENCH_TLS_USE_OS_TRUST", "1") == "0":
        logger.info("tls_os_trust_store_disabled_by_env")
        return False
    try:
        import truststore

        truststore.inject_into_ssl()
        _injected = True
        logger.info("tls_os_trust_store_enabled")
        return True
    except Exception as exc:  # noqa: BLE001 — TLS trust must never block startup
        logger.warning("tls_os_trust_store_unavailable", error=str(exc))
        return False
