"""PU-1 commercial-safe path: presentation material is rebuilt only from ``COMMERCIAL_OK``
sources. When none exist the analysis is omitted with an explicit notice; a personal-use result is
never substituted.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from app.licensing import registry as _registry
from app.licensing.scopes import LicenseScope

OMISSION_TEMPLATE = (
    "ANALYSIS OMITTED — {name}: no COMMERCIAL_OK-licensed data source is available for this "
    "analysis (PU-1). No personal-use result has been substituted."
)


def omission_notice(analysis_name: str) -> str:
    """Explicit notice that an analysis is omitted from presentation material."""
    return OMISSION_TEMPLATE.format(name=analysis_name)


def commercial_ok_source_set(
    candidate_source_sets: Sequence[Sequence[str]],
) -> tuple[str, ...] | None:
    """First candidate source set whose every member is ``COMMERCIAL_OK``; ``None`` if none (or if
    the registry is unusable)."""
    try:
        reg = _registry.load_registry()
    except _registry.LicenseRegistryError:
        return None
    for sources in candidate_source_sets:
        if sources and reg.scope_of(sources) is LicenseScope.COMMERCIAL_OK:
            return tuple(sources)
    return None


def commercial_safe_section(
    analysis_name: str,
    *,
    candidate_source_sets: Sequence[Sequence[str]],
    build: Callable[[tuple[str, ...]], str],
) -> str:
    """Build one presentation section. ``build`` is called ONLY with a source set that is entirely
    ``COMMERCIAL_OK``; otherwise the omission notice is returned and ``build`` is never invoked."""
    chosen = commercial_ok_source_set(candidate_source_sets)
    if chosen is None:
        return omission_notice(analysis_name)
    return build(chosen)
