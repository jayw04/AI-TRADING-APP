"""Technical bounds shared by the spec schema and the governance manifest.

``MAX_ATTEMPT_LIMIT`` is a TECHNICAL upper bound on a pre-registered P3A / P3B attempt limit, so a
wildly large value is refused at validation time instead of failing late at authorization. It does
not choose, suggest or override the approved research policy: the actual limits are owner
decisions recorded in the governance manifest (currently unset).
"""

from __future__ import annotations

MAX_ATTEMPT_LIMIT = 10_000
