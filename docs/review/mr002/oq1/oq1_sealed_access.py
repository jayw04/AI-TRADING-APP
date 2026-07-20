"""MR-002 OQ-1 — deny-by-default sealed-data access boundary (Component 4).

Every attempt to reach validation/OOS/development data, vendor/production DBs, broker APIs, secrets, or
the S3 run-5 archive contents must fail closed (REFUSED_SEALED_ACCESS) and leave durable refusal
evidence. Only an explicit allowlist of synthetic fixture paths may be opened. Guards cover direct
open, path traversal, symlink escape, env-var credential discovery, AWS shared-credentials paths,
network sockets, HTTP/DB clients, real-data-adapter imports, and subprocess bypass.
"""

from __future__ import annotations

import os
import re

# denylist: sealed / real-data / secret path patterns (case-insensitive)
SEALED_PATTERNS = [
    r"validation", r"\boos\b", r"out[_-]?of[_-]?sample", r"development[_-]?data", r"\bdev[_-]?data\b",
    r"sealed", r"vendor", r"sharadar", r"quiver", r"alpaca", r"broker", r"production",
    r"\.aws", r"credentials", r"secret", r"\.env\b", r"id_rsa", r"\.pem\b",
    r"mr002/run5", r"workbench-backups", r"\.duckdb\b", r"\.sqlite\b",
]
_SEALED = re.compile("|".join(SEALED_PATTERNS), re.IGNORECASE)

# real-data / network / db adapter modules that must never import inside the qualification
FORBIDDEN_IMPORTS = {"boto3", "botocore", "alpaca", "requests", "httpx", "urllib3", "socket",
                     "psycopg2", "sqlalchemy", "duckdb", "http.client", "ftplib", "smtplib",
                     "subprocess", "paramiko"}

CREDENTIAL_ENV = {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
                  "AWS_SHARED_CREDENTIALS_FILE", "ALPACA_API_KEY", "ALPACA_SECRET_KEY",
                  "ANTHROPIC_API_KEY", "DATABASE_URL", "WORKBENCH_MCP_KEY"}


class SealedAccessRefused(Exception):
    """REFUSED_SEALED_ACCESS — a sealed / real-data / secret access attempt was blocked."""


def _refuse(detail: str):
    raise SealedAccessRefused(f"REFUSED_SEALED_ACCESS:{detail}")


def is_sealed_path(path: str) -> bool:
    return bool(_SEALED.search(str(path).replace("\\", "/")))


def guarded_open(path: str, allowlist_root: str, mode: str = "rb"):
    """Open a file ONLY if it resolves inside the synthetic-fixture allowlist root AND is not a sealed
    pattern. Blocks path traversal (via realpath containment) and symlink escape."""
    root = os.path.realpath(allowlist_root)
    real = os.path.realpath(path)
    if os.path.islink(path):
        _refuse(f"SYMLINK_ESCAPE:{os.path.basename(path)}")
    if is_sealed_path(path) or is_sealed_path(real):
        _refuse(f"SEALED_PATTERN:{os.path.basename(path)}")
    if os.path.commonpath([root, real]) != root:              # traversal / outside allowlist
        _refuse(f"OUTSIDE_ALLOWLIST:{os.path.basename(path)}")
    if "w" in mode or "a" in mode or "+" in mode:
        _refuse("WRITE_TO_INPUT_FORBIDDEN")
    return open(real, mode)


def assert_no_credentials(environ: dict | None = None) -> None:
    """No AWS/broker/vendor/db credentials may be present in the environment."""
    env = os.environ if environ is None else environ
    present = sorted(k for k in CREDENTIAL_ENV if env.get(k))
    if present:
        _refuse(f"CREDENTIAL_PRESENT:{','.join(present)}")


def assert_no_aws_credentials_files() -> None:
    """The AWS shared-credentials / config discovery paths must not exist inside the container."""
    for p in (os.path.expanduser("~/.aws/credentials"), os.path.expanduser("~/.aws/config"),
              os.environ.get("AWS_SHARED_CREDENTIALS_FILE", "")):
        if p and os.path.exists(p):
            _refuse(f"AWS_CREDENTIALS_FILE:{os.path.basename(p)}")


def assert_no_forbidden_imports(loaded_modules) -> None:
    """No real-data / network / db / subprocess adapter may be imported by the qualification."""
    hit = sorted(set(loaded_modules) & FORBIDDEN_IMPORTS)
    if hit:
        _refuse(f"FORBIDDEN_IMPORT:{','.join(hit)}")


def assert_network_disabled() -> None:
    """Best-effort proof that outbound network is unavailable (network-disabled qualification run)."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(("1.1.1.1", 443))
        s.close()
    except OSError:
        return                                                # unreachable -> network disabled (expected)
    _refuse("NETWORK_REACHABLE")                              # reachable -> isolation not enforced
