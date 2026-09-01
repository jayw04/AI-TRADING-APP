"""OP-6 tradability-screened universe (C3 / LOW-002), frozen 2026-09-01.

Implements the pre-registered OP-6 screen from
``docs/design/NewStrategy/NewStrategy_FrozenResearchSpecs_2026-09-01_v1_2_FINAL.md`` §OP-6:

    common stock / primary listing only · close >= $5 · 63-day median dollar ADV >= $2M,
    all measured POINT-IN-TIME at each rebalance.

⚠ PRICE-FIELD SEMANTICS (owner ruling 2026-09-01) — the asymmetry is deliberate:

* **$5 floor uses ``closeunadj``** — the actually-traded nominal share price. A split/dividend
  ADJUSTED close would let a name that never traded above $5 pass (or a name that did, fail),
  which is the wrong question for an investability screen.
* **ADV uses ``close * volume``** — the EXISTING GOVERNED dollar-volume convention, inherited
  verbatim from :meth:`FactorDataStore.dollar_volume_universe`, so ADV stays comparable with the
  universe machinery the rest of the platform already uses. Not redesigned here.

Eligibility (lifetime straddle) mirrors ``dollar_volume_universe`` exactly, so this screen is
survivorship-free and point-in-time: a name listed after ``as_of`` is absent, and a name live then
but since delisted is present. Deterministic — ties broken by ticker ascending.

⛔ This module defines a UNIVERSE only. It contains no signal, no weighting and no threshold that
any candidate's economics may be tuned against.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.factor_data.store import FactorDataStore

# Frozen OP-6 thresholds. ⛔ Not tunable: changing one is a new pre-registration.
MIN_CLOSE_UNADJ_USD = 5.0
MIN_MEDIAN_DOLLAR_ADV_USD = 2_000_000.0
ADV_LOOKBACK_DAYS = 63

# "common stock / primary listing only" as it is actually encoded in Sharadar `tickers.category`.
# A single-class domestic common name carries no class qualifier and is primary by construction;
# the explicit "Primary Class" rows are the primary leg of multi-class issuers. Everything else —
# Secondary Class, Warrant, Preferred, ADR and Canadian — is excluded by omission.
PRIMARY_COMMON_CATEGORIES = (
    "Domestic Common Stock",
    "Domestic Common Stock Primary Class",
)
EXCLUDED_EXCHANGES = ("OTC",)


def op6_universe_asof(
    store: FactorDataStore,
    as_of: date,
    *,
    min_close: float = MIN_CLOSE_UNADJ_USD,
    min_median_dollar_adv: float = MIN_MEDIAN_DOLLAR_ADV_USD,
    lookback_days: int = ADV_LOOKBACK_DAYS,
) -> list[str]:
    """Tickers passing the OP-6 tradability screen as of ``as_of``, ascending.

    Signature-compatible with ``universe_asof`` for use as a ``universe_fn`` provider, so the
    same screened universe can drive a book and its equal-weight benchmark.
    """
    window_start = as_of - timedelta(days=lookback_days)
    cats = ", ".join(f"'{c}'" for c in PRIMARY_COMMON_CATEGORIES)
    exch = ", ".join(f"'{e}'" for e in EXCLUDED_EXCHANGES)
    rows = store.con.execute(
        f"""
        WITH win AS (
            SELECT ticker, close, volume, closeunadj, date
            FROM sep WHERE date BETWEEN ? AND ?
        ),
        adv AS (
            SELECT ticker, median(close * volume) AS mdadv FROM win GROUP BY ticker
        ),
        px AS (   -- last actually-traded price on or before as_of
            SELECT ticker, last(closeunadj ORDER BY date) AS last_unadj
            FROM win GROUP BY ticker
        )
        SELECT adv.ticker
        FROM adv
        JOIN px ON px.ticker = adv.ticker
        JOIN tickers t ON t.ticker = adv.ticker
        WHERE t.firstpricedate IS NOT NULL
          AND t.lastpricedate  IS NOT NULL
          AND t.firstpricedate <= ?
          AND t.lastpricedate  >= ?
          AND t.category IN ({cats})
          AND (t.exchange IS NULL OR t.exchange NOT IN ({exch}))
          AND px.last_unadj >= ?
          AND adv.mdadv     >= ?
        ORDER BY adv.ticker ASC
        """,
        [window_start, as_of, as_of, as_of, min_close, min_median_dollar_adv],
    ).fetchall()
    return [r[0] for r in rows]
