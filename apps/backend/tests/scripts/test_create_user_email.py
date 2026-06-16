"""create_user.py email validation — accounts must use an email the /auth/login
route (Pydantic EmailStr) will accept, so a created user can actually log in.

The script's ``_validate_email`` is loaded directly (scripts/ isn't a package).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "create_user.py"
_spec = importlib.util.spec_from_file_location("create_user", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_validate_email = _mod._validate_email


@pytest.mark.parametrize(
    "email",
    ["jay@globalcomplyai.com", "range@local.dev", "a.b+tag@sub.example.co.uk"],
)
def test_accepts_valid_emails(email: str) -> None:
    assert _validate_email(email)  # returns the normalized address


@pytest.mark.parametrize(
    "email",
    [
        "range@local",  # domain has no dot — the bug that prompted this
        "not-an-email",
        "@example.com",
        "name@",
        "",
    ],
)
def test_rejects_invalid_emails(email: str) -> None:
    with pytest.raises(ValueError):
        _validate_email(email)
