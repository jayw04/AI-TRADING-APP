"""Data Source Registry (EAD §6.4, DCAP-007) — the license flags that gate external exposure."""

from __future__ import annotations

import dataclasses

import pytest

from app.altdata.source_registry import (
    INGESTION_STATUSES,
    DataSource,
    all_sources,
    get_source,
)


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


# --- ingestion status: our ingestion contract, never inferred from provider cadence ---------


def test_quiver_govcontracts_is_paused_by_governance_not_live():
    """The corpus is a one-shot 2026-07-06 backfill with no scheduler/cron/timer behind it.

    ``refresh_frequency="daily"`` is the *provider's* cadence; reading it as our ingestion
    contract made a deliberately frozen research corpus look like a broken daily feed.
    """
    q = get_source("quiver")
    assert q.refresh_frequency == "daily"              # provider cadence, unchanged
    assert q.ingestion_status == "PAUSED_BY_GOVERNANCE"  # our contract: not ingesting
    assert "GOVCONTRACT-001" in q.ingestion_status_note


def test_ingestion_status_has_no_default_so_new_sources_cannot_be_implicitly_live():
    """Guard: re-adding a default would let a new source inherit an unwritten daily contract."""
    field = next(f for f in dataclasses.fields(DataSource) if f.name == "ingestion_status")
    assert field.default is dataclasses.MISSING
    assert field.default_factory is dataclasses.MISSING


def test_every_registered_source_declares_a_known_status():
    for source in all_sources():
        assert source.ingestion_status in INGESTION_STATUSES, source.source_name


def test_every_non_live_source_explains_itself():
    for source in all_sources():
        if source.ingestion_status != "LIVE":
            assert source.ingestion_status_note.strip(), source.source_name


def _kwargs(**overrides):
    base = dict(
        source_id="DCAP-999", source_name="test", provider="p", datasets_enabled=(),
        license_type="public", commercial_use_allowed=False, redistribution_allowed=False,
        cache_allowed=True, derived_signal_allowed=False, refresh_frequency="daily",
        known_latency="none", point_in_time_supported=True, contact_owner="t",
        renewal_date=None, ingestion_status="LIVE",
    )
    base.update(overrides)
    return base


def test_unknown_status_is_rejected():
    with pytest.raises(ValueError, match="is not one of"):
        DataSource(**_kwargs(ingestion_status="PROBABLY_FINE"))


def test_non_live_status_without_a_note_is_rejected():
    with pytest.raises(ValueError, match="requires an ingestion_status_note"):
        DataSource(**_kwargs(ingestion_status="PAUSED_BY_GOVERNANCE"))


def test_non_live_status_with_a_note_is_accepted():
    ds = DataSource(**_kwargs(ingestion_status="UNEXPECTEDLY_STALE",
                              ingestion_status_note="ingest job died 2026-07-01; investigating"))
    assert ds.ingestion_status == "UNEXPECTEDLY_STALE"
