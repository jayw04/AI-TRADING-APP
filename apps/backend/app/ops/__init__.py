"""Operations & Reliability (P11) — read-only operational surfaces.

This package answers operational questions about the *running* system (what is enabled,
is it healthy) without touching the order path, the risk engine, or any persistent store.
Everything here is read-only and derives state from existing sources (P11 §1 — ADR 0021).
"""
