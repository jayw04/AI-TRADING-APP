"""Security primitives: crypto + credential store.

ONLY this package may import `cryptography` directly. Everything else
accesses crypto operations through the public functions exposed here.

The check_no_env_credentials.sh invariant enforces that no production
code path outside this package reads broker/AI/auth secrets from env vars.
"""
from app.security.credential_store import (
    CredentialKind,
    CredentialMetadata,
    CredentialNotFoundError,
    CredentialStore,
)
from app.security.crypto import (
    InvalidCiphertextError,
    MasterKeyMissingError,
    decrypt,
    encrypt,
    verify_master_key,
)

__all__ = [
    "encrypt",
    "decrypt",
    "verify_master_key",
    "MasterKeyMissingError",
    "InvalidCiphertextError",
    "CredentialKind",
    "CredentialMetadata",
    "CredentialStore",
    "CredentialNotFoundError",
]
