"""Signal construction (INSIDER-001 plan §3; owner S6) — the conviction filter as a reusable
event-scoring step over the PIT corporate-event store.

This is the **faithful** port of the sibling system's validated conviction-buy subset
(`Docs/Strategies/Insider Strategy.md` §1, §3.1) — **no parameter is re-tuned** (plan §1
faithfulness rule). It turns raw ``insider_buy`` events into ``ConvictionHit``s:

    role ∈ {exec, officer}  AND  value ≥ $25k  AND  ( clustered ≥2 insiders within 30d
                                                       OR  big solo ≥ $100k )

The step is deliberately generic in shape — a filter + a window-cluster scorer over events —
so a *different* event score (any future ``score(event, history) -> bool``) reuses the same
construction without touching the Event-Study Engine downstream.

**PIT discipline.** A hit carries both ``event_date`` (the transaction — when the conviction
formed) and ``filed_at`` (the SEC acceptance — when it became *knowable*). Clustering is judged
on transaction dates (the economic event), but the Event-Study Engine must **enter on
``filed_at``**, never the transaction date, or the study look-aheads by the ~2-day filing lag the
§2 gate measured.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.altdata.events.store import CorporateEvent

# Validated thresholds (frozen — plan §1; do NOT re-tune before faithful reproduction).
MIN_VALUE = 25_000.0          # a conviction buy is ≥ $25k
BIG_SOLO_VALUE = 100_000.0    # a single ≥ $100k buy qualifies on its own
CLUSTER_WINDOW_DAYS = 30      # "clustered" = ≥2 distinct insiders within a trailing 30 days
CLUSTER_MIN_INSIDERS = 2


@dataclass(frozen=True)
class ConvictionHit:
    """One conviction-buy signal. ``entry_date`` (= ``filed_at`` date) is the PIT-honest anchor
    the Event-Study Engine enters on; ``event_date`` is kept for diagnostics/regime tagging."""

    ticker: str
    event_date: date          # transaction date (when the conviction formed)
    filed_at: date            # SEC acceptance date (when it became knowable — the entry anchor)
    value: float              # open-market buy value ($)
    owner_name: str | None
    n_cluster_insiders: int   # distinct qualifying insiders in the trailing window (incl. this one)
    is_cluster: bool          # ≥ CLUSTER_MIN_INSIDERS distinct insiders within the window
    is_big_solo: bool         # this single buy ≥ BIG_SOLO_VALUE

    @property
    def entry_date(self) -> date:
        """The PIT-honest entry anchor — the filing date, not the transaction date."""
        return self.filed_at


def _qualifies_role_value(e: CorporateEvent, *, min_value: float, require_officer: bool) -> bool:
    """Role + dollar gate: an officer/exec open-market buy of at least ``min_value``. Directors
    and 10% owners are excluded (faithful to the source's exec/officer subset)."""
    if e.event_type != "insider_buy":
        return False
    payload = e.payload or {}
    value = float(payload.get("buy_value") or 0.0)
    if value < min_value:
        return False
    return bool(payload.get("is_officer")) if require_officer else True


def conviction_hits(
    events: list[CorporateEvent],
    *,
    min_value: float = MIN_VALUE,
    big_solo_value: float = BIG_SOLO_VALUE,
    cluster_window_days: int = CLUSTER_WINDOW_DAYS,
    cluster_min_insiders: int = CLUSTER_MIN_INSIDERS,
    require_officer: bool = True,
) -> list[ConvictionHit]:
    """Construct conviction-buy hits from raw insider-buy events (faithful subset; plan §3).

    A qualifying event (officer role, ≥ ``min_value``) becomes a hit when it is **clustered**
    (≥ ``cluster_min_insiders`` *distinct* qualifying insiders bought the same ticker within the
    trailing ``cluster_window_days``) **or** a **big solo** (this buy ≥ ``big_solo_value``).
    Clustering is judged on ``event_date`` (the transaction) over a **trailing, forward-only**
    window ``(event_date - cluster_window_days, event_date]`` — a cluster only counts buys already
    known at that event, never future ones, so a cluster signal fires on the date the *second*
    insider makes it visible (PIT-honest), not retroactively on the first. Amendments
    (``is_amendment``) are excluded — a 4/A corrects a prior filing, it is not a new conviction.

    Returns hits sorted by ``(entry_date, ticker)`` — the order the Event-Study Engine consumes.
    """
    quals = [
        e for e in events
        if e.event_date is not None
        and not (e.payload or {}).get("is_amendment", False)
        and _qualifies_role_value(e, min_value=min_value, require_officer=require_officer)
    ]
    quals.sort(key=lambda e: (e.event_date or date.min, e.ticker or ""))

    # group qualifying events per ticker so the cluster scan is O(events) not O(events²)
    by_ticker: dict[str, list[CorporateEvent]] = {}
    for e in quals:
        by_ticker.setdefault(e.ticker or "", []).append(e)

    hits: list[ConvictionHit] = []
    window = timedelta(days=cluster_window_days)
    for ticker, evs in by_ticker.items():
        for e in evs:
            assert e.event_date is not None  # filtered above
            lo = e.event_date - window
            # distinct insiders with a qualifying buy in (event_date - window, event_date]
            insiders = {
                (o.payload or {}).get("owner_name") or o.accession
                for o in evs
                if o.event_date is not None and lo < o.event_date <= e.event_date
            }
            n_cluster = len(insiders)
            is_cluster = n_cluster >= cluster_min_insiders
            value = float((e.payload or {}).get("buy_value") or 0.0)
            is_big_solo = value >= big_solo_value
            if not (is_cluster or is_big_solo):
                continue
            hits.append(ConvictionHit(
                ticker=ticker,
                event_date=e.event_date,
                filed_at=_filed_date(e),
                value=value,
                owner_name=(e.payload or {}).get("owner_name"),
                n_cluster_insiders=n_cluster,
                is_cluster=is_cluster,
                is_big_solo=is_big_solo,
            ))

    hits.sort(key=lambda h: (h.entry_date, h.ticker))
    return hits


def _filed_date(e: CorporateEvent) -> date:
    """The filing's calendar date (the PIT entry anchor) — the date component of ``filed_at``."""
    return e.filed_at.date()
