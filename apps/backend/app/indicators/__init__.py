"""Indicator computation layer.

Wraps pandas-ta with a stable interface and a short-TTL memoization cache.
The indicator set is small and curated; we deliberately don't expose
pandas-ta's full surface to avoid breaking when pandas-ta changes between
versions. The golden test in ``tests/indicators/`` is the last line of
defense against version drift.
"""

from .computer import CORE_INDICATORS, IndicatorComputer

__all__ = ["CORE_INDICATORS", "IndicatorComputer"]
