"""PU-1 visible marking. Every report/chart whose scope is not ``COMMERCIAL_OK`` carries a fixed
footer. There is deliberately NO parameter, flag or environment variable that suppresses it: the
only way to a footer-free render is for the artifact to be derived solely from ``COMMERCIAL_OK``
sources in the registry.
"""

from __future__ import annotations

import html
from collections.abc import Iterable
from typing import Literal

from app.licensing.gate import safe_effective_scope
from app.licensing.scopes import LicenseScope

PERSONAL_FOOTER = "PERSONAL USE ONLY — not for presentation (PU-1)"

Fmt = Literal["markdown", "text", "html"]


def footer_for(scope: LicenseScope, fmt: Fmt = "markdown") -> str | None:
    """The footer block for ``scope`` in ``fmt``, or ``None`` for ``COMMERCIAL_OK``."""
    if not scope.blocks_presentation:
        return None
    if fmt == "markdown":
        return f"\n\n---\n**{PERSONAL_FOOTER}**\n"
    if fmt == "html":
        return (
            '\n<footer data-pu1="personal-use-only" style="margin-top:1em;font-weight:bold">'
            f"{html.escape(PERSONAL_FOOTER)}</footer>\n"
        )
    return f"\n\n{PERSONAL_FOOTER}\n"


def stamp(
    text: str,
    *,
    sources: Iterable[str],
    declared_scope: object = None,
    fmt: Fmt = "markdown",
) -> str:
    """Return ``text`` with the PU-1 footer appended unless its sources are all ``COMMERCIAL_OK``.

    Idempotent. An unusable registry is treated as ``UNKNOWN`` (stamped).
    """
    scope = safe_effective_scope(sources=sources, declared_scope=declared_scope)
    footer = footer_for(scope, fmt)
    if footer is None or PERSONAL_FOOTER in text:
        return text
    return text.rstrip("\n") + footer
