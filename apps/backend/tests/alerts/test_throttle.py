"""Unit tests for the in-process throttle helpers."""

from __future__ import annotations

import time

import pytest

from app.alerts import throttle as th


@pytest.fixture(autouse=True)
def reset():
    th._reset_for_tests()
    yield
    th._reset_for_tests()


def test_dedup_first_call_is_not_duplicate() -> None:
    assert (
        th.is_duplicate_alert(
            user_id=1, symbol="AAPL", side="buy", strategy_id=None, payload={"x": 1}
        )
        is False
    )


def test_dedup_second_identical_call_is_duplicate() -> None:
    kwargs = dict(
        user_id=1, symbol="AAPL", side="buy", strategy_id=None, payload={"x": 1}
    )
    th.is_duplicate_alert(**kwargs)
    assert th.is_duplicate_alert(**kwargs) is True


def test_dedup_different_payload_is_not_duplicate() -> None:
    th.is_duplicate_alert(
        user_id=1, symbol="AAPL", side="buy", strategy_id=None, payload={"x": 1}
    )
    assert (
        th.is_duplicate_alert(
            user_id=1, symbol="AAPL", side="buy", strategy_id=None, payload={"x": 2}
        )
        is False
    )


def test_dedup_window_expires() -> None:
    kwargs = dict(
        user_id=1, symbol="AAPL", side="buy", strategy_id=None, payload={}
    )
    th.is_duplicate_alert(**kwargs)
    h = th._compute_content_hash(**kwargs)
    th._dedup_cache[h] = time.time() - (th.DEDUP_WINDOW_SECONDS + 1.0)
    assert th.is_duplicate_alert(**kwargs) is False


def test_rate_limit_allows_under_threshold() -> None:
    for _ in range(th.RATE_LIMIT_MAX_PER_WINDOW):
        assert th.is_rate_limited(secret="abc") is False


def test_rate_limit_fires_over_threshold() -> None:
    for _ in range(th.RATE_LIMIT_MAX_PER_WINDOW):
        th.is_rate_limited(secret="abc")
    assert th.is_rate_limited(secret="abc") is True


def test_rate_limit_separate_secrets_independent() -> None:
    for _ in range(th.RATE_LIMIT_MAX_PER_WINDOW):
        th.is_rate_limited(secret="abc")
    assert th.is_rate_limited(secret="def") is False


def test_failed_auth_throttle_check_is_readonly() -> None:
    """``is_auth_attempt_rate_limited`` must not record — otherwise every
    legitimate request would count toward the failed-auth budget."""
    for _ in range(100):
        assert th.is_auth_attempt_rate_limited(client_ip="1.2.3.4") is False


def test_failed_auth_throttle_fires_after_threshold() -> None:
    for _ in range(th.FAILED_AUTH_MAX_PER_WINDOW):
        assert th.is_auth_attempt_rate_limited(client_ip="1.2.3.4") is False
        th.record_auth_failure(client_ip="1.2.3.4")
    assert th.is_auth_attempt_rate_limited(client_ip="1.2.3.4") is True


def test_failed_auth_throttle_is_per_ip() -> None:
    for _ in range(th.FAILED_AUTH_MAX_PER_WINDOW):
        th.record_auth_failure(client_ip="1.2.3.4")
    assert th.is_auth_attempt_rate_limited(client_ip="1.2.3.4") is True
    assert th.is_auth_attempt_rate_limited(client_ip="5.6.7.8") is False
