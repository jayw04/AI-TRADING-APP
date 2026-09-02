#!/usr/bin/env python3
"""Hash-only rotation and read-only verification of Workbench login passwords.

Two commands that never share an entry point (CREDENTIAL-ROTATION-TOOL-CUSTODY-001):

``rotate``
    Generates a new password per user *in process*, hashes it with the backend's
    own ``app.auth.passwords.hash_password`` (so the hash is exactly what the
    login route verifies), writes the plaintext to a 0600 file under ``certs/``
    (gitignored) and the bcrypt hashes to a sibling JSON file, and prints only
    counts and SHA-256 fingerprints of the hashes. It touches no database.

``verify``
    Reads the credential file and a ``{user_id: stored_hash}`` JSON exported from
    the box, checks each password against its stored hash with the backend's
    constant-time ``verify_password``, prints VERIFIED / MISMATCH / NO STORED HASH
    per user, and writes nothing.

Plaintext never leaves this machine and never appears on a command line: the
only channel to the box is the hash file, applied with
``UPDATE users SET password_hash = :hash WHERE id = :id``. Pushing plaintext
through SSM would put it in command history (~30 days, service-side and on
disk) -- the exposure a rotation exists to close.

Rotation is NOT complete when the hash lands. It is complete when every governed
local consumer has been resynchronized and a login has been tested
(``docs/runbook/credentials.md`` section 7).

Usage::

    python scripts/rotate_user_passwords.py rotate --users 6 --reason "<incident id>"
    python scripts/rotate_user_passwords.py verify --stored-hashes certs/stored_hashes.json
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import secrets
import stat
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

# Make the backend package importable when run from the repo root, exactly as
# scripts/create_user.py does. The hashing parameters are then the backend's
# own, not a copy that can drift.
_BACKEND = Path(__file__).resolve().parents[1] / "apps" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.auth.passwords import (  # noqa: E402  (after sys.path setup)
    MAX_PASSWORD_BYTES,
    hash_password,
    verify_password,
)

# id -> email, for the accounts this tool is allowed to touch. Explicit rather
# than derived so a typo cannot rotate a user that was never in scope.
KNOWN_USERS: dict[int, str] = {
    3: "momentum-conservative@globalcomplyai.com",
    4: "momentum-growth@globalcomplyai.com",
    5: "sector-rotation@globalcomplyai.com",
    6: "low-volatility@globalcomplyai.com",
    7: "combined-book@globalcomplyai.com",
}

DEFAULT_CREDENTIAL_FILE = "certs/workbench_logins.md"
DEFAULT_HASHES_FILE = "certs/.rotation_hashes.json"


def generate_password(nbytes: int = 24) -> str:
    """URL-safe token. 24 bytes -> 32 chars, ~192 bits, well inside bcrypt's 72-byte limit."""
    pw = secrets.token_urlsafe(nbytes)
    if len(pw.encode()) > MAX_PASSWORD_BYTES:  # pragma: no cover - defensive
        raise ValueError("generated password exceeds bcrypt's 72-byte limit")
    return pw


def fingerprint(hashed: str) -> str:
    """Short, non-reversible identifier for a bcrypt hash, safe to print and paste."""
    return hashlib.sha256(hashed.encode("ascii")).hexdigest()[:12]


def _under_certs(path: Path) -> bool:
    return "certs" in path.parts


def parse_credential_file(text: str) -> dict[str, str]:
    """Return {user_id: password} from the markdown table written by ``rotate``."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("| ") or line.startswith("| user id") or "---" in line:
            continue
        parts = [c.strip() for c in line.strip("|").split("|")]
        if len(parts) < 3 or not parts[0].isdigit():
            continue
        out[parts[0]] = parts[2].strip("`")
    return out


def write_credentials_file(path: Path, rows: list[dict[str, object]], reason: str) -> None:
    """Write the credential record, then tighten permissions.

    Built in memory and written to a temp file first, then atomically replaced --
    the target is never opened for writing before the content is ready, so an
    interrupted run cannot truncate an existing credential file.
    """
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "# Workbench login credentials",
        "",
        f"Rotated: **{stamp}**",
        "",
        f"Reason: {reason}",
        "",
        "> This file lives in `certs/`, which is gitignored.",
        "> Never commit it, never paste its contents into a chat transcript, and",
        "> never pass these values on a command line that reaches SSM.",
        "",
        "| user id | email | password |",
        "|---|---|---|",
    ]
    lines += [f"| {r['id']} | {r['email']} | `{r['password']}` |" for r in rows]
    lines += [
        "",
        "## Superseded",
        "",
        "The previous values for these users are superseded as of the timestamp",
        "above and must not be reused.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    os.replace(tmp, path)
    with contextlib.suppress(OSError):  # 0600; best-effort on Windows
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


# --------------------------------------------------------------------------- rotate


def cmd_rotate(args: argparse.Namespace) -> int:
    out = Path(args.out)
    hp = Path(args.hashes_out)
    if not (_under_certs(out) and _under_certs(hp)):
        sys.stderr.write("refusing to write outside certs/\n")
        return 2
    try:
        ids = [int(u) for u in args.users.split(",") if u.strip()]
    except ValueError:
        sys.stderr.write("--users must be integers\n")
        return 2
    if not ids:
        sys.stderr.write("--users is empty\n")
        return 2
    unknown = [i for i in ids if i not in KNOWN_USERS]
    if unknown:
        sys.stderr.write(f"unknown user ids: {unknown}\n")
        return 2

    rows: list[dict[str, object]] = []
    hashes: dict[str, str] = {}
    for uid in ids:
        pw = generate_password()
        rows.append({"id": uid, "email": KNOWN_USERS[uid], "password": pw})
        hashes[str(uid)] = hash_password(pw)

    write_credentials_file(out, rows, args.reason)
    hp.parent.mkdir(parents=True, exist_ok=True)
    hp.write_text(json.dumps(hashes, indent=1), encoding="utf-8")

    # Deliberately prints neither plaintext nor hashes -- the files are the only copies.
    print(f"wrote {len(rows)} credentials to {out}")
    print(f"wrote {len(hashes)} bcrypt hashes to {hp}")
    for uid in ids:
        print(
            f"  user {uid} ({KNOWN_USERS[uid]}): hash fingerprint {fingerprint(hashes[str(uid)])}"
        )
    print("\nApply on the box:  UPDATE users SET password_hash=:h WHERE id=:id")
    print(
        "Rotation is not complete until each governed local consumer is "
        "resynchronized and a login is tested (docs/runbook/credentials.md section 7)."
    )
    return 0


# --------------------------------------------------------------------------- verify


def cmd_verify(args: argparse.Namespace) -> int:
    """Read-only: compares the credential file against stored hashes; writes nothing."""
    stored_raw = json.loads(Path(args.stored_hashes).read_text(encoding="utf-8"))
    stored = {str(k): v for k, v in stored_raw.items()}
    creds = parse_credential_file(Path(args.credentials).read_text(encoding="utf-8"))
    if not creds:
        sys.stderr.write("no credential rows found\n")
        return 2
    ok = True
    for uid, pw in creds.items():
        h = stored.get(uid)
        if h is None:
            print(f"user {uid}: NO STORED HASH")
            ok = False
            continue
        good = verify_password(pw, h)
        print(f"user {uid}: {'VERIFIED' if good else 'MISMATCH'} (fingerprint {fingerprint(h)})")
        ok &= good
    return 0 if ok else 1


# --------------------------------------------------------------------------- cli


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="command", required=True)

    rot = sub.add_parser(
        "rotate", help="generate + hash new passwords; writes files, touches no DB"
    )
    rot.add_argument(
        "--users", required=True, help="comma-separated user ids (no default: explicit scope)"
    )
    rot.add_argument(
        "--reason", required=True, help="why (incident / finding id); recorded in the file"
    )
    rot.add_argument(
        "--out", default=DEFAULT_CREDENTIAL_FILE, help="credential file (must be under certs/)"
    )
    rot.add_argument(
        "--hashes-out",
        default=DEFAULT_HASHES_FILE,
        help="{user_id: bcrypt_hash} file (must be under certs/)",
    )
    rot.set_defaults(func=cmd_rotate)

    ver = sub.add_parser(
        "verify", help="read-only check of the credential file against stored hashes"
    )
    ver.add_argument(
        "--stored-hashes", required=True, help="JSON {user_id: stored_hash} read back from the DB"
    )
    ver.add_argument(
        "--credentials", default=DEFAULT_CREDENTIAL_FILE, help="credential file written by rotate"
    )
    ver.set_defaults(func=cmd_verify)
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
