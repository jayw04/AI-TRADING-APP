"""P5 §4 — crypto module: Fernet round-trip + error handling."""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet

from app.security import crypto
from app.security.crypto import (
    InvalidCiphertextError,
    MasterKeyMissingError,
    decrypt,
    encrypt,
    verify_master_key,
)


@pytest.fixture
def restore_crypto_env():
    """Save/restore the master-key env var + the cached Fernet so tests that
    mutate them don't bleed into the rest of the suite."""
    saved = os.environ.get(crypto.MASTER_KEY_ENV_VAR)
    yield
    if saved is None:
        os.environ.pop(crypto.MASTER_KEY_ENV_VAR, None)
    else:
        os.environ[crypto.MASTER_KEY_ENV_VAR] = saved
    crypto._reset_cache_for_tests()


def test_round_trip():
    secret = "alpaca-paper-key-ABC123"
    token = encrypt(secret)
    assert isinstance(token, bytes)
    assert token != secret.encode()  # actually encrypted
    assert decrypt(token) == secret


def test_encrypt_rejects_empty_string():
    with pytest.raises(ValueError):
        encrypt("")


def test_encrypt_rejects_non_str():
    with pytest.raises(TypeError):
        encrypt(b"bytes-not-str")  # type: ignore[arg-type]


def test_decrypt_rejects_empty_ciphertext():
    with pytest.raises(InvalidCiphertextError):
        decrypt(b"")


def test_decrypt_wrong_key_raises(restore_crypto_env):
    # Encrypt under the suite key, then swap the key and try to decrypt.
    token = encrypt("some-secret")
    os.environ[crypto.MASTER_KEY_ENV_VAR] = Fernet.generate_key().decode("ascii")
    crypto._reset_cache_for_tests()
    with pytest.raises(InvalidCiphertextError):
        decrypt(token)


def test_verify_master_key_passes_with_valid_key():
    # The suite conftest sets a valid WORKBENCH_MASTER_KEY.
    verify_master_key()  # must not raise


def test_missing_master_key_raises(restore_crypto_env):
    os.environ[crypto.MASTER_KEY_ENV_VAR] = ""
    crypto._reset_cache_for_tests()
    with pytest.raises(MasterKeyMissingError):
        verify_master_key()


def test_invalid_master_key_raises(restore_crypto_env):
    os.environ[crypto.MASTER_KEY_ENV_VAR] = "not-a-valid-fernet-key"
    crypto._reset_cache_for_tests()
    with pytest.raises(MasterKeyMissingError):
        encrypt("x")
