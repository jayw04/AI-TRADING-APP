from app.brokers.alpaca.errors import (
    PermanentAlpacaError,
    TransientAlpacaError,
    classify,
)


def test_connection_error_is_transient() -> None:
    out = classify(ConnectionError("connection reset"))
    assert isinstance(out, TransientAlpacaError)


def test_timeout_error_is_transient() -> None:
    out = classify(TimeoutError("timed out"))
    assert isinstance(out, TransientAlpacaError)


def test_unknown_exception_defaults_permanent() -> None:
    out = classify(ValueError("nope"))
    assert isinstance(out, PermanentAlpacaError)


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeHTTPError:
    """Stand-in for requests.HTTPError that APIError.status_code derives from."""

    def __init__(self, status_code: int) -> None:
        self.response = _FakeResponse(status_code)


def _make_apierror(status_code: int):
    """Construct a real APIError carrying a synthetic status code.

    `APIError.status_code` is a property derived from `http_error.response.status_code`,
    so we feed in a tiny fake http_error rather than trying to set the attribute
    directly (which would fail — status_code has no setter).
    """
    from alpaca.common.exceptions import APIError

    return APIError('{"code": 0, "message": "x"}', _FakeHTTPError(status_code))


def test_apierror_5xx_transient() -> None:
    try:
        import alpaca.common.exceptions  # noqa: F401
    except ImportError:
        return
    out = classify(_make_apierror(503))
    assert isinstance(out, TransientAlpacaError)


def test_apierror_4xx_permanent() -> None:
    try:
        import alpaca.common.exceptions  # noqa: F401
    except ImportError:
        return
    out = classify(_make_apierror(422))
    assert isinstance(out, PermanentAlpacaError)


def test_apierror_429_transient() -> None:
    try:
        import alpaca.common.exceptions  # noqa: F401
    except ImportError:
        return
    out = classify(_make_apierror(429))
    assert isinstance(out, TransientAlpacaError)
