"""Session token unit tests (P5 §3)."""

from app.auth.tokens import (
    generate_session_token,
    hash_session_token,
    token_hashes_equal,
)


def test_token_length():
    t = generate_session_token()
    # 32 bytes base64-urlsafe (no padding): typically 43 chars.
    assert 40 <= len(t) <= 48


def test_token_uniqueness():
    tokens = {generate_session_token() for _ in range(100)}
    assert len(tokens) == 100


def test_hash_is_deterministic():
    t = generate_session_token()
    assert hash_session_token(t) == hash_session_token(t)


def test_hash_changes_with_token():
    t1 = generate_session_token()
    t2 = generate_session_token()
    assert hash_session_token(t1) != hash_session_token(t2)


def test_constant_time_compare():
    h = hash_session_token("foo")
    assert token_hashes_equal(h, h) is True
    assert token_hashes_equal(h, "x" * len(h)) is False
