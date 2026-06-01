"""structlog processor that scrubs known credential patterns from log events
before they reach stdout (P5 §8.4).

**Defense in depth, not the primary defense.** Credentials should never be
passed to ``logger.*`` in the first place. This processor catches accidental
leaks; if you find yourself relying on it, fix the upstream call.

Pattern families (evaluated most-specific first, generic catch-all last — so a
specific token isn't half-eaten by the generic rule and left with a residue):
  - Fernet tokens (the ``gAAAAA`` version-byte prefix) — every secret in the
    §4 credential store is stored as one of these.
  - Anthropic API keys (``sk-ant-``).
  - Alpaca live keys (``PKLIVE``) and paper keys (``PKTEST``).
  - Generic ``password=`` / ``secret=`` / ``api_key=`` assignments.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping
from typing import Any

# Order matters: specific → generic.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"gAAAAA[A-Za-z0-9_\-=]{20,}"), "[REDACTED:fernet]"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"), "[REDACTED:anthropic]"),
    (re.compile(r"PKLIVE[A-Z0-9]{8,}"), "[REDACTED:alpaca_live]"),
    (re.compile(r"PKTEST[A-Z0-9]{8,}"), "[REDACTED:alpaca_paper]"),
    (
        re.compile(
            r"(password|secret|api_key|api_secret|totp_secret|webhook_secret)"
            r"(\s*[=:]\s*)['\"]?([A-Za-z0-9+/=_\-]{6,})['\"]?",
            re.IGNORECASE,
        ),
        r"\1\2[REDACTED:generic]",
    ),
]


def _redact_value(value: Any) -> Any:
    """Recursively redact strings inside strings, dicts, and lists."""
    if isinstance(value, str):
        for pattern, replacement in _PATTERNS:
            value = pattern.sub(replacement, value)
        return value
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_value(v) for v in value]
    return value


def redact_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> Mapping[str, Any]:
    """structlog processor: redact known credential patterns from every field.

    Must run BEFORE the JSON renderer so redaction applies to the final
    serialized fields, not after they've been turned into bytes."""
    return {k: _redact_value(v) for k, v in event_dict.items()}
