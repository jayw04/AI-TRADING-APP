"""TOTP (RFC 6238) wrapper around pyotp (P5 §3)."""

from __future__ import annotations

import base64
import io

import pyotp
import qrcode

ISSUER = "Trading Workbench"


def generate_secret() -> str:
    """Fresh base32 TOTP secret (160 bits)."""
    return pyotp.random_base32()


def verify_code(secret: str, code: str, *, valid_window: int = 1) -> bool:
    """Constant-time TOTP verification.

    valid_window=1 accepts the previous, current, and next 30-second windows —
    gentle on clock skew. Bump only if a user genuinely has persistent drift.
    """
    if not (secret and code):
        return False
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=valid_window)
    except Exception:
        return False


def make_provisioning_uri(secret: str, *, account_name: str) -> str:
    """`otpauth://` URI for QR codes. Standard format consumed by every TOTP
    authenticator app (Google Authenticator, Authy, 1Password, etc.)."""
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=ISSUER)


def make_qr_png_bytes(provisioning_uri: str) -> bytes:
    """Render the provisioning URI as a QR code PNG. Returns raw bytes."""
    img = qrcode.make(provisioning_uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_qr_data_url(provisioning_uri: str) -> str:
    """The same QR code as a `data:image/png;base64,...` URL. Convenient to drop
    into an `<img src="...">` tag during the setup wizard."""
    png_bytes = make_qr_png_bytes(provisioning_uri)
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"
