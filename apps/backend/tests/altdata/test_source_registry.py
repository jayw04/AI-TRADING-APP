"""Data Source Registry (EAD §6.4, DCAP-007) — the license flags that gate external exposure."""

from __future__ import annotations

from app.altdata.source_registry import all_sources, get_source


def test_quiver_is_registered_as_dcap007_hobbyist():
    q = get_source("quiver")
    assert q is not None
    assert q.source_id == "DCAP-007" and q.license_type == "hobbyist"
    assert q.datasets_enabled == ("government_contracts",)
    assert q.point_in_time_supported is True


def test_quiver_is_not_customer_facing_on_hobbyist():
    q = get_source("quiver")
    # Hobbyist carries No Commercial Use Rights -> no external cards (ADR 0037 §2.4)
    assert q.commercial_use_allowed is False
    assert q.derived_signal_allowed is False
    assert q.customer_facing_allowed is False
    assert q.cache_allowed is True          # internal research caching is fine


def test_unknown_source_is_none():
    assert get_source("nope") is None
    assert len(all_sources()) >= 1
