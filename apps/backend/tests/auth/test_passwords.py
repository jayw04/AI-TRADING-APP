"""Password hashing unit tests (P5 §3)."""

import pytest

from app.auth.passwords import hash_password, verify_password


def test_hash_and_verify():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) is True


def test_verify_wrong_password():
    h = hash_password("right")
    assert verify_password("wrong", h) is False


def test_hash_is_unique_per_call():
    """bcrypt salts every hash — repeated calls produce different outputs."""
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2
    assert verify_password("same", h1)
    assert verify_password("same", h2)


def test_empty_password_rejected():
    with pytest.raises(ValueError):
        hash_password("")


def test_long_password_rejected():
    with pytest.raises(ValueError):
        hash_password("x" * 73)


def test_verify_empty():
    assert verify_password("", "anything") is False
    assert verify_password("password", "") is False
