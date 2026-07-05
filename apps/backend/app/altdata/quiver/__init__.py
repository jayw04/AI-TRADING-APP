"""Quiver Quant alternative-data ingestion (EAD Phase 1; ADR 0037, DCAP-007).

Read-only, off the order path. Feeds the existing PIT Event Store (``app/altdata/events``)
with a new ``event_type`` — it does NOT create a second store. Government contracts is the
MVP dataset (GOVCONTRACT-001).
"""
