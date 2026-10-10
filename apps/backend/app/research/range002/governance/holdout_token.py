"""One holdout token per spec hash, consumed at most once (R3, WP4.2).

State machine, one file per transition, each created with ``O_CREAT|O_EXCL``
(atomic: of two racing consumers exactly one wins) and fsynced::

    <spec>.token.json      ISSUED     (issue)
    <spec>.intent.json     INTENT     (phase 1: durable intent to open, names the run)
    <spec>.verified.json   CONSUMED   (phase 2: intent read back and verified)

A crash after phase 1 and before phase 2 leaves ``INTENT``. ``INTENT`` is
treated exactly like ``CONSUMED``: we cannot prove the holdout was not opened,
so no second opening is ever offered. Re-issuing after a defect needs a defect
record and owner approval (R3); that path is deliberately not built here.

Scope: the state lives in plain files of one directory, so this store defends against
accidents (a second call, a racing consumer, a crash mid-consume), not against someone who
can delete or recreate those files (T2). The authority on "was this holdout window ever
opened" is the run registry; ``results_guard.authorize`` cross-checks it. Each file records the
genesis id of the registry the token was issued for and a mismatching registry/store pairing is
refused (round 4); a recreated token directory has no files, so it is not evidence of anything
and the registry (not this store) still decides whether the window was opened. Writes loop over
short ``os.write`` returns; a failed write leaves the half-written file in place, which
reads back as invalid (fail closed) rather than re-issuable.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, final

from app.research.range002.governance.errors import (
    HoldoutAlreadyOpenedError,
    HoldoutTokenError,
    HoldoutTokenInvalidError,
    RegistryGenesisMismatchError,
    RegistryIntegrityError,
)
from app.research.range002.governance.hashchain import write_all
from app.research.range002.spec.genesis import is_canonical_uuid4

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class TokenState(StrEnum):
    NOT_ISSUED = "NOT_ISSUED"
    ISSUED = "ISSUED"
    INTENT = "INTENT"  # consume begun, never verified -- treated as opened
    CONSUMED = "CONSUMED"


@dataclass(frozen=True)
class HoldoutToken:
    spec_sha256: str
    token_id: str
    #: genesis id of the registry this token was issued for (round 4, N1d).
    registry_genesis_id: str


def _fsync_dir(directory: Path) -> None:
    # Directory fsync makes the new file name durable on POSIX; Windows has no
    # equivalent and refuses to open a directory, which is not an error here.
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _create_exclusive(path: Path, doc: dict[str, Any]) -> None:
    """Atomically create ``path`` with ``doc``; FileExistsError if it exists."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
    try:
        try:
            write_all(fd, json.dumps(doc, sort_keys=True).encode("utf-8"))
        except RegistryIntegrityError as exc:
            # The half-written file is deliberately left in place: it makes the state
            # unreadable (fail closed) rather than silently re-issuable.
            raise HoldoutTokenError(f"short write creating {path.name}: {exc}") from exc
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_dir(path.parent)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HoldoutTokenInvalidError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(doc, dict):
        raise HoldoutTokenInvalidError(f"{path.name} is not an object")
    return doc


@final
class HoldoutTokenStore:
    """Token files for one directory.

    Directory links: governance directories that are symlinks/junctions are followed; no path
    confinement is provided or claimed -- see the ``hashchain.py`` module docstring.
    For the token store: an empty redirected token directory looks fresh to the token store,
    but the registry remains the authority and refuses a second holdout opening.
    """

    def __init__(self, directory: Path) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, spec_sha256: str, kind: str) -> Path:
        if not isinstance(spec_sha256, str) or not _HEX64.fullmatch(spec_sha256):
            raise HoldoutTokenInvalidError("spec_sha256 must be a 64-hex digest")
        return self._dir / f"{spec_sha256}.{kind}.json"

    def state(self, spec_sha256: str) -> TokenState:
        if self._path(spec_sha256, "verified").exists():
            return TokenState.CONSUMED
        if self._path(spec_sha256, "intent").exists():
            return TokenState.INTENT
        if self._path(spec_sha256, "token").exists():
            return TokenState.ISSUED
        return TokenState.NOT_ISSUED

    def issue(
        self, spec_sha256: str, *, registry_genesis_id: str, now: datetime | None = None
    ) -> HoldoutToken:
        """Issue the single token for this spec hash; a second issue is refused.

        The token file records ``registry_genesis_id`` (the genesis id of the run registry this
        token is for). ``validate_unused`` refuses a token/registry pairing whose genesis ids
        differ, so a token directory cannot be reused against a replacement registry. Level 1:
        the file is plain text anyone with directory write access can edit (T2).
        """
        if not is_canonical_uuid4(registry_genesis_id):
            raise HoldoutTokenInvalidError(
                "registry_genesis_id must be a canonical lowercase UUIDv4"
            )
        token = HoldoutToken(
            spec_sha256=spec_sha256,
            token_id=secrets.token_hex(16),
            registry_genesis_id=registry_genesis_id,
        )
        try:
            _create_exclusive(
                self._path(spec_sha256, "token"),
                {
                    "spec_sha256": spec_sha256,
                    "token_id": token.token_id,
                    "registry_genesis_id": registry_genesis_id,
                    "issued_at": (now or datetime.now(UTC)).astimezone(UTC).isoformat(),
                },
            )
        except FileExistsError as exc:
            raise HoldoutTokenError(
                f"a holdout token was already issued for spec {spec_sha256[:12]} "
                "(one token per spec hash)"
            ) from exc
        return token

    def validate_unused(
        self, token: object, spec_sha256: str, registry_genesis_id: str
    ) -> HoldoutToken:
        """Token is genuine for this spec AND this registry, and still ISSUED (not
        INTENT/CONSUMED). ``registry_genesis_id`` is the genesis id of the registry in use."""
        if not isinstance(token, HoldoutToken):
            raise HoldoutTokenInvalidError("a HoldoutToken is required for the HOLDOUT partition")
        if token.spec_sha256 != spec_sha256:
            raise HoldoutTokenInvalidError("holdout token was issued for a different spec hash")
        if token.registry_genesis_id != registry_genesis_id:
            raise RegistryGenesisMismatchError(
                "the holdout token was issued for a different registry (genesis id mismatch)"
            )
        state = self.state(spec_sha256)
        if state is TokenState.NOT_ISSUED:
            raise HoldoutTokenInvalidError("no holdout token has been issued for this spec")
        if state is not TokenState.ISSUED:
            raise HoldoutAlreadyOpenedError(
                f"holdout for spec {spec_sha256[:12]} is {state.value}; a second opening "
                "is refused (R3)"
            )
        stored = _read_json(self._path(spec_sha256, "token"))
        if stored.get("registry_genesis_id") != registry_genesis_id:
            raise RegistryGenesisMismatchError(
                "the token store was issued for a different registry (genesis id mismatch)"
            )
        if stored.get("token_id") != token.token_id or stored.get("spec_sha256") != spec_sha256:
            raise HoldoutTokenInvalidError("holdout token does not match the issued token")
        return token

    def begin_consume(
        self, token: HoldoutToken, run_id: str, *, now: datetime | None = None
    ) -> None:
        """Phase 1: durably record the intent to open. Atomic; the loser of a
        race, or any later caller, gets ``HoldoutAlreadyOpenedError``."""
        self.validate_unused(token, token.spec_sha256, token.registry_genesis_id)
        try:
            _create_exclusive(
                self._path(token.spec_sha256, "intent"),
                {
                    "spec_sha256": token.spec_sha256,
                    "token_id": token.token_id,
                    "registry_genesis_id": token.registry_genesis_id,
                    "run_id": run_id,
                    "intent_at": (now or datetime.now(UTC)).astimezone(UTC).isoformat(),
                },
            )
        except FileExistsError as exc:
            raise HoldoutAlreadyOpenedError(
                f"a consume is already under way or done for spec {token.spec_sha256[:12]}"
            ) from exc

    def commit_consume(
        self, token: HoldoutToken, run_id: str, *, now: datetime | None = None
    ) -> None:
        """Phase 2: read the intent back, verify it, then mark CONSUMED."""
        intent = _read_json(self._path(token.spec_sha256, "intent"))
        if (
            intent.get("token_id") != token.token_id
            or intent.get("run_id") != run_id
            or intent.get("spec_sha256") != token.spec_sha256
            or intent.get("registry_genesis_id") != token.registry_genesis_id
        ):
            raise HoldoutTokenInvalidError("durable intent does not match this consume")
        try:
            _create_exclusive(
                self._path(token.spec_sha256, "verified"),
                {
                    "spec_sha256": token.spec_sha256,
                    "token_id": token.token_id,
                    "registry_genesis_id": token.registry_genesis_id,
                    "run_id": run_id,
                    "verified_at": (now or datetime.now(UTC)).astimezone(UTC).isoformat(),
                },
            )
        except FileExistsError as exc:
            raise HoldoutAlreadyOpenedError("holdout already marked consumed") from exc

    def consume(self, token: HoldoutToken, run_id: str, *, now: datetime | None = None) -> None:
        """Two-phase consume.

        After this returns, ``validate_unused`` refuses this token for as long as the token
        directory is untouched: the guarantee lives in the ``.intent.json`` / ``.verified.json``
        files, so deleting them (or pointing a fresh directory at the same spec hash) makes the
        token usable again. That is why ``results_guard.authorize`` also cross-checks the run
        registry, which is the authority on whether a holdout window was ever opened; this
        method alone does not defend against anyone with write access to the directory (T2).
        """
        self.begin_consume(token, run_id, now=now)
        self.commit_consume(token, run_id, now=now)
