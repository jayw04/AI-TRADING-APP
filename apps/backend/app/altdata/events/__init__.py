"""Point-in-time corporate-event store (ADR 0027).

Event-type-agnostic by design — it sits at the *Corporate Event* level, so Form 4 insider
buys, future 8-K / 13F filings, earnings, buybacks, and dividends all persist here and any
event program reuses it. The store's defining property is **point-in-time correctness**: an
event is only visible from its filing/acceptance date forward (``events_asof``), which is
what keeps an event study free of look-ahead (ADR 0014) — the gap the sibling system flagged.
"""
