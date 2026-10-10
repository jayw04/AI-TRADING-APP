"""L1 hardening: strict-mode spec models, blank-list handling, date handling."""

from __future__ import annotations

from datetime import date

import pytest

from app.research.range002.spec.loader import SpecSchemaError, parse_draft

from ._fixtures import complete_payload, set_path


def _problems(payload: dict) -> str:
    with pytest.raises(SpecSchemaError) as ei:
        parse_draft(payload)
    return " | ".join(ei.value.problems)


@pytest.mark.parametrize(
    ("path", "bad"),
    [
        ("gates.min_trades", "300"),  # numeric string for an int
        ("gates.min_trades", 300.0),  # float for an int
        ("gates.stress_mean_positive", 1),  # int for a bool
        ("gates.stress_mean_positive", "true"),
        ("universe.include_delisted", 1),
        ("universe.n", "3"),
        ("universe.n", True),  # bool for an int
        ("risk.per_trade_pct", "0.1"),
        ("stats.bootstrap.seed", "14"),
        ("spec_version", "1"),
        ("spec_version", True),
    ],
)
def test_strict_mode_rejects_lax_coercion(path, bad):
    payload = complete_payload()
    set_path(payload, path, bad)
    _problems(payload)


def test_iso_date_strings_still_accepted_for_date_fields():
    spec = parse_draft(complete_payload())
    assert spec.signoff.date == date(2000, 1, 1)
    assert spec.partitions.holdout == (date(2022, 1, 1), date(2025, 12, 31))


@pytest.mark.parametrize("bad", [20000101, 946684800.0, True, "2000-1-1x"])
def test_non_iso_dates_rejected(bad):
    payload = complete_payload()
    set_path(payload, "signoff.date", bad)
    _problems(payload)


def test_unset_walk_treats_lists_of_blanks_as_unset():
    payload = complete_payload()
    set_path(payload, "costs.components", [None])
    set_path(payload, "governance.roles", {"owners": ["  ", None]})
    set_path(payload, "gates.yearly", ["", ""])
    unset = parse_draft(payload).unset_p0_fields()
    assert "costs.components" in unset
    assert "governance.roles.owners" in unset
    assert "gates.yearly" in unset
    set_path(payload, "costs.components", [None, "x"])
    assert "costs.components" not in parse_draft(payload).unset_p0_fields()


def test_payload_that_is_not_json_is_a_schema_error():
    with pytest.raises(SpecSchemaError, match="not strict JSON"):
        parse_draft({"program": object()})
    with pytest.raises(SpecSchemaError):
        parse_draft(None)
