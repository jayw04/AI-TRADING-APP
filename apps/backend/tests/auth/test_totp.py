"""TOTP unit tests (P5 §3)."""

import pyotp

from app.auth.totp import (
    generate_secret,
    make_provisioning_uri,
    make_qr_data_url,
    verify_code,
)


def test_secret_is_base32_and_long_enough():
    s = generate_secret()
    assert len(s) >= 16
    assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in s)


def test_verify_current_code():
    secret = generate_secret()
    code = pyotp.TOTP(secret).now()
    assert verify_code(secret, code) is True


def test_verify_wrong_code():
    secret = generate_secret()
    assert verify_code(secret, "000000") is False


def test_verify_empty_inputs():
    assert verify_code("", "123456") is False
    assert verify_code("ABCD", "") is False


def test_provisioning_uri_format():
    s = generate_secret()
    uri = make_provisioning_uri(s, account_name="test@example.com")
    assert uri.startswith("otpauth://totp/")
    assert "Trading%20Workbench" in uri or "Trading+Workbench" in uri


def test_qr_data_url_is_png_base64():
    s = generate_secret()
    uri = make_provisioning_uri(s, account_name="test@example.com")
    data_url = make_qr_data_url(uri)
    assert data_url.startswith("data:image/png;base64,")
