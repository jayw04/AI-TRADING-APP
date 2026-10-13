"""Per-source access and use classification.

Each data source is classified on its own terms. Free access does not establish storage or
presentation permission, and a wrapper library is not a source: AkShare retrieves data from an
upstream site, so its rows are classified by that upstream, never as one blanket "AkShare" entry.

Presentation follows the owner's PU-1 rule (personal use): unless a source has written permission
to be shown to other people, anything derived from it is PERSONAL. ``UNKNOWN`` is treated as
PERSONAL. When the PU-1 license registry merges, these ids are the entries it should carry.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Access(StrEnum):
    TOKEN_REQUIRED = "TOKEN_REQUIRED"  # account + token; availability depends on the owner's plan
    FREE_NO_ACCOUNT = "FREE_NO_ACCOUNT"
    SYNTHETIC = "SYNTHETIC"


class Presentation(StrEnum):
    PERSONAL = "PERSONAL"  # the owner's own research only
    UNKNOWN = "UNKNOWN"  # terms not read; treated as PERSONAL
    SYNTHETIC_OK = "SYNTHETIC_OK"  # generated fixtures, no vendor data


@dataclass(frozen=True)
class SourceClass:
    source_id: str
    name: str
    access: Access
    storage: str  # what is established about keeping a local copy
    presentation: Presentation
    basis: str  # what the classification rests on
    upstream: str | None = None  # the real origin when the library is a wrapper

    @property
    def presentable(self) -> bool:
        return self.presentation is Presentation.SYNTHETIC_OK


_SOURCES: dict[str, SourceClass] = {
    s.source_id: s
    for s in (
        SourceClass(
            source_id="tushare_pro",
            name="Tushare Pro",
            access=Access.TOKEN_REQUIRED,
            storage="UNKNOWN: terms not yet read; local research copy assumed personal only",
            presentation=Presentation.UNKNOWN,
            basis="intended primary daily provider; endpoint access depends on the account's points",
        ),
        SourceClass(
            source_id="baostock",
            name="Baostock",
            access=Access.FREE_NO_ACCOUNT,
            storage="UNKNOWN: free access does not by itself establish storage terms",
            presentation=Presentation.UNKNOWN,
            basis="cross-check provider; anonymous login",
        ),
        SourceClass(
            source_id="cn_synthetic",
            name="Synthetic A-share fixtures",
            access=Access.SYNTHETIC,
            storage="generated in tests; no vendor data",
            presentation=Presentation.SYNTHETIC_OK,
            basis="deterministic generator in app.markets.cn_ashare.providers.synthetic",
        ),
    )
}


def get_source(source_id: str) -> SourceClass:
    """The classification for ``source_id``. An unregistered id is UNKNOWN (treated as PERSONAL)."""
    found = _SOURCES.get(source_id)
    if found is not None:
        return found
    if source_id.startswith("cn_synthetic:"):  # a fake client rendered in one provider's shape
        base = _SOURCES["cn_synthetic"]
        return SourceClass(
            source_id=source_id,
            name=f"{base.name} ({source_id.split(':', 1)[1]})",
            access=base.access,
            storage=base.storage,
            presentation=base.presentation,
            basis=base.basis,
        )
    return SourceClass(
        source_id=source_id,
        name=source_id,
        access=Access.TOKEN_REQUIRED,
        storage="UNKNOWN: unregistered source",
        presentation=Presentation.UNKNOWN,
        basis="not registered",
    )


def akshare_source(upstream: str) -> SourceClass:
    """Classify an AkShare call by the site it actually fetched from (for example ``eastmoney``).

    The id is ``akshare:<upstream>`` and the classification is the upstream's own. An upstream
    nobody has read the terms for is UNKNOWN, as it would be without AkShare in between."""
    up = upstream.strip().lower()
    if not up:
        raise ValueError("an AkShare call must name its upstream source")
    base = get_source(up)
    return SourceClass(
        source_id=f"akshare:{up}",
        name=f"AkShare via {up}",
        access=base.access,
        storage=base.storage,
        presentation=base.presentation,
        basis=f"classified by upstream {up!r}; AkShare is the retrieval library only",
        upstream=up,
    )


def all_sources() -> list[SourceClass]:
    return list(_SOURCES.values())
