"""Alpaca error taxonomy.

Distinguishes transient (retryable) from permanent (don't retry; surface
to the user). Order router uses this to decide retry behavior; UI uses it
to format messages.
"""

from __future__ import annotations


class AlpacaError(Exception):
    """Base class for all Alpaca-related errors raised by the adapter."""


class TransientAlpacaError(AlpacaError):
    """Retryable: 5xx, timeouts, rate limit (429)."""


class PermanentAlpacaError(AlpacaError):
    """Not retryable: 4xx (except 429), insufficient funds, asset not tradable."""


def classify(exc: BaseException) -> AlpacaError:
    """Map an underlying exception to our taxonomy.

    Imports alpaca-py exception classes lazily so this module has no
    import-time dependency on alpaca-py (useful for tests).
    """
    try:
        from alpaca.common.exceptions import APIError

        if isinstance(exc, APIError):
            status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            if status == 429:
                return TransientAlpacaError(str(exc))
            if isinstance(status, int):
                if 500 <= status < 600:
                    return TransientAlpacaError(str(exc))
                if 400 <= status < 500:
                    return PermanentAlpacaError(str(exc))
    except ImportError:
        pass

    if isinstance(exc, ConnectionError | TimeoutError):
        return TransientAlpacaError(str(exc))

    # Default: treat as permanent. Better to surface and let the user retry
    # manually than silently retry something we don't understand.
    return PermanentAlpacaError(str(exc))
