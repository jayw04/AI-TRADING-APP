"""Fernet encryption with a process-level master key.

The master key is loaded once at startup from WORKBENCH_MASTER_KEY env var.
Subsequent encrypt/decrypt calls use that key without re-reading the env.

Fernet wraps AES-128-CBC with HMAC-SHA256 for authenticated encryption.
That's plenty for our threat model (host-disk read by moderate adversary).
For higher-stakes deployments, KMS/HSM-backed envelope encryption would
be the upgrade path — but Fernet's interface (encrypt() returns bytes,
decrypt() takes bytes) maps to whatever backend we'd swap in.
"""
from __future__ import annotations

import os

import structlog
from cryptography.fernet import Fernet, InvalidToken

logger = structlog.get_logger(__name__)


MASTER_KEY_ENV_VAR = "WORKBENCH_MASTER_KEY"


class MasterKeyMissingError(RuntimeError):
    """Raised when the master key env var is unset or invalid. Backend
    refuses to boot."""


class InvalidCiphertextError(RuntimeError):
    """Raised when decrypt() can't decode a ciphertext. Either the master
    key is wrong (rotation happened or env var was changed) or the data
    is corrupted."""


_cached_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Load the master key once. After first call, cached."""
    global _cached_fernet
    if _cached_fernet is None:
        key = os.environ.get(MASTER_KEY_ENV_VAR, "").strip()
        if not key:
            raise MasterKeyMissingError(
                f"{MASTER_KEY_ENV_VAR} environment variable is required. "
                f"Generate one with scripts/generate_master_key.py and add to .env."
            )
        try:
            _cached_fernet = Fernet(key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise MasterKeyMissingError(
                f"{MASTER_KEY_ENV_VAR} is not a valid Fernet key: {exc}. "
                f"Generate a new one with scripts/generate_master_key.py."
            ) from exc
    return _cached_fernet


def verify_master_key() -> None:
    """Call at startup to fail fast if the master key is missing or
    malformed. Logs that the key is loaded (helpful for rotation later)."""
    f = _get_fernet()
    # Sanity round-trip
    ciphertext = f.encrypt(b"verify")
    plaintext = f.decrypt(ciphertext)
    assert plaintext == b"verify", "Fernet round-trip failed at startup"
    logger.info("crypto_master_key_verified")


def encrypt(plaintext: str) -> bytes:
    """Encrypt a UTF-8 string. Returns the Fernet token as bytes.

    Fernet tokens include the encryption timestamp, IV, ciphertext, and
    HMAC. They're URL-safe base64 — typically 100-200 bytes for short
    plaintexts. Storing as `bytes` (BLOB) in SQLite, not as text.
    """
    if not isinstance(plaintext, str):
        raise TypeError("encrypt() requires a str input")
    if not plaintext:
        raise ValueError("encrypt() cannot encrypt empty string")
    return _get_fernet().encrypt(plaintext.encode("utf-8"))


def decrypt(ciphertext: bytes) -> str:
    """Decrypt to UTF-8. Raises InvalidCiphertextError on any failure."""
    if not ciphertext:
        raise InvalidCiphertextError("Empty ciphertext")
    try:
        plaintext_bytes = _get_fernet().decrypt(ciphertext)
    except InvalidToken as exc:
        raise InvalidCiphertextError(
            "Cannot decrypt — wrong master key or corrupted data."
        ) from exc
    return plaintext_bytes.decode("utf-8")


def _reset_cache_for_tests() -> None:
    """Test-only: clear the cached Fernet so a different key can be tested."""
    global _cached_fernet
    _cached_fernet = None
