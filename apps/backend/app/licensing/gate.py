"""PU-1 presentation gate. Fail closed; there is NO override parameter anywhere in this module.

``assert_presentable`` is the single decision point. It returns only for ``COMMERCIAL_OK``;
``PERSONAL`` and ``UNKNOWN`` (including "unregistered" and "registry unreadable") raise
``PersonalScopeBlocked`` carrying the reason code ``PU1_PERSONAL_SCOPE_BLOCKED``. The only
exception route is a registry entry backed by written vendor permission — i.e. a reviewed change
to ``data_license_registry.json`` and its pinned hash, never a call-site argument.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.licensing import registry as _registry
from app.licensing.scopes import LicenseScope, combine_scopes

REASON_CODE = "PU1_PERSONAL_SCOPE_BLOCKED"


class PersonalScopeBlocked(PermissionError):
    """A personal-use (or unknown-licence) artifact reached an external-use path."""

    reason_code = REASON_CODE

    def __init__(
        self,
        *,
        scope: LicenseScope,
        sources: tuple[str, ...],
        destination: str,
        detail: str = "",
    ) -> None:
        self.scope = scope
        self.sources = sources
        self.destination = destination
        self.detail = detail
        msg = (
            f"{REASON_CODE}: {scope.name} artifact refused for {destination!r} "
            f"(sources={list(sources) or 'none declared'})"
        )
        super().__init__(msg + (f" - {detail}" if detail else ""))


def effective_scope(*, sources: Iterable[str], declared_scope: object = None) -> LicenseScope:
    """Scope of an artifact: the registry's verdict on its sources, combined with any scope the
    producer declared. A producer can only make an artifact MORE restricted, never less: an
    artifact with no declared sources is ``UNKNOWN`` however it labels itself.

    Raises ``LicenseRegistryError`` when the registry cannot be used.
    """
    src = tuple(sources)
    verdict = _registry.load_registry().scope_of(src)
    if declared_scope is None:
        return verdict
    return combine_scopes(verdict, LicenseScope.parse(declared_scope))


def safe_effective_scope(*, sources: Iterable[str], declared_scope: object = None) -> LicenseScope:
    """Like ``effective_scope`` but an unusable registry yields ``UNKNOWN`` instead of raising
    (used for MARKING and TAGGING, where the conservative answer is "restricted")."""
    try:
        return effective_scope(sources=sources, declared_scope=declared_scope)
    except _registry.LicenseRegistryError:
        return LicenseScope.UNKNOWN


def assert_presentable(
    *,
    sources: Iterable[str],
    declared_scope: object = None,
    destination: str = "external",
) -> LicenseScope:
    """Return ``COMMERCIAL_OK`` or raise ``PersonalScopeBlocked`` (``PU1_PERSONAL_SCOPE_BLOCKED``)."""
    src = tuple(sources)
    try:
        scope = effective_scope(sources=src, declared_scope=declared_scope)
    except _registry.LicenseRegistryError as exc:
        raise PersonalScopeBlocked(
            scope=LicenseScope.UNKNOWN,
            sources=src,
            destination=destination,
            detail=f"licence registry unusable: {exc}",
        ) from exc
    if scope.blocks_presentation:
        raise PersonalScopeBlocked(scope=scope, sources=src, destination=destination)
    return scope
