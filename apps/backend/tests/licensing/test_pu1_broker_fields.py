"""PU-1: per-field classification of Alpaca broker/trading API responses.

The broker API returns the owner's own transaction records and marked-to-market market data in the
same response; a derived artifact is tainted by the subset of fields it actually consumed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.licensing as lic
from app.licensing import broker_fields as bf
from app.licensing.scopes import LicenseScope, Scoped, derive

OWNER = "owner_generated_records"
MARKET = "alpaca_market_data"


@pytest.fixture(autouse=True)
def _fresh_table():
    bf.reset_cache()
    yield
    bf.reset_cache()


def test_order_ids_and_qty_alone_are_owner_records() -> None:
    srcs = bf.sources_of_fields(
        "order", ["id", "client_order_id", "symbol", "side", "qty", "status"]
    )
    assert srcs == frozenset({OWNER})
    assert bf.scope_of_fields("order", ["id", "qty"]) is LicenseScope.COMMERCIAL_OK


@pytest.mark.parametrize("field", ["market_value", "current_price"])
def test_adding_a_marked_to_market_field_makes_the_metric_market_data(field) -> None:
    used = ["symbol", "qty", field]
    assert bf.sources_of_fields("position", used) == frozenset({OWNER, MARKET})
    assert bf.scope_of_fields("position", used) is LicenseScope.PERSONAL


@pytest.mark.parametrize("field", ["unrealized_pl", "unrealized_plpc", "unrealized_intraday_pl"])
def test_unrealized_pnl_is_personal(field) -> None:
    assert bf.classify_field("position", field).field_class is bf.FieldClass.MARKET_DATA
    assert bf.scope_of_fields("position", [field]) is LicenseScope.PERSONAL


def test_unknown_field_name_is_conservatively_personal() -> None:
    v = bf.classify_field("position", "some_new_alpaca_field")
    assert v.field_class is bf.FieldClass.MARKET_DATA and v.listed is False
    assert bf.scope_of_fields("position", ["qty", "some_new_alpaca_field"]) is LicenseScope.PERSONAL
    # an unknown response kind is conservative too, even for an owner-looking field name
    assert bf.scope_of_fields("brand_new_kind", ["qty"]) is LicenseScope.PERSONAL
    assert bf.classify_field("brand_new_kind", "qty").listed is False


def test_field_and_kind_names_are_case_and_space_insensitive() -> None:
    assert bf.scope_of_fields(" Position ", [" QTY "]) is LicenseScope.COMMERCIAL_OK
    assert bf.scope_of_fields("POSITION", ["Market_Value"]) is LicenseScope.PERSONAL


def test_account_object_splits_cash_from_marked_equity() -> None:
    assert bf.scope_of_fields("account", ["cash", "status", "trading_blocked"]) is (
        LicenseScope.COMMERCIAL_OK
    )
    for f in ("equity", "last_equity", "portfolio_value", "buying_power", "long_market_value"):
        assert bf.scope_of_fields("account", [f]) is LicenseScope.PERSONAL, f


def test_own_execution_prices_are_owner_records_pending_an_owner_ruling() -> None:
    for kind, field in (
        ("order", "filled_avg_price"),
        ("position", "avg_entry_price"),
        ("position", "cost_basis"),
        ("fill", "price"),
        ("activity", "price"),
    ):
        v = bf.classify_field(kind, field)
        assert v.field_class is bf.FieldClass.OWNER_RECORD, (kind, field)
        assert v.review is True, (kind, field)
    # ... but a metric that compares them with market data is tainted by the market field
    assert bf.scope_of_fields("position", ["avg_entry_price", "current_price"]) is (
        LicenseScope.PERSONAL
    )


def test_asset_master_is_vendor_reference_data_not_an_owner_record() -> None:
    assert bf.scope_of_fields("asset", ["symbol", "tradable"]) is LicenseScope.PERSONAL


def test_subset_with_lineage_taints_only_by_fields_actually_used() -> None:
    response = {
        "id": "o-1",
        "qty": "10",
        "side": "buy",
        "market_value": "1234.5",
        "current_price": 9,
    }
    owner_only = bf.subset_with_lineage(response, "position", ["qty", "side"])
    assert owner_only.value == {"qty": "10", "side": "buy"}
    assert owner_only.sources == frozenset({OWNER})
    # the response ALSO carries market_value, which was not consumed: no taint
    assert lic.effective_scope(sources=owner_only.sources) is LicenseScope.COMMERCIAL_OK
    used_mv = bf.subset_with_lineage(response, "position", ["qty", "market_value"])
    assert used_mv.sources == frozenset({OWNER, MARKET})
    assert lic.effective_scope(sources=used_mv.sources) is LicenseScope.PERSONAL
    # a requested field the response lacks still counts (the consumer depends on it)
    absent = bf.subset_with_lineage({"qty": "1"}, "position", ["qty", "unrealized_pl"])
    assert absent.value == {"qty": "1"} and MARKET in absent.sources


def test_no_fields_consumed_is_an_empty_lineage_and_unknown() -> None:
    assert bf.sources_of_fields("position", []) == frozenset()
    assert bf.scope_of_fields("position", []) is LicenseScope.UNKNOWN


def test_taint_from_fields_unions_with_extra_sources_and_survives_derive() -> None:
    t = bf.taint_from_fields({"n": 1}, ("order", ["id", "qty"]), extra_sources=["sharadar"])
    assert t.sources == frozenset({OWNER, "sharadar"})
    t2 = bf.taint_from_fields(None, ("order", ["qty"]), ("position", ["unrealized_pl"]))
    assert t2.sources == frozenset({OWNER, MARKET})
    joined = derive(lambda a, b: (a, b), Scoped.of(1, [OWNER]), t2)
    assert joined.sources == frozenset({OWNER, MARKET})
    assert lic.effective_scope(sources=joined.sources) is LicenseScope.PERSONAL


def test_unusable_table_classifies_everything_as_market_data(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(bf, "TABLE_PATH", tmp_path / "missing.json")
    bf.reset_cache()
    assert bf.sources_of_fields("order", ["id", "qty"]) == frozenset({MARKET})
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(bf, "TABLE_PATH", bad)
    bf.reset_cache()
    assert bf.scope_of_fields("order", ["id"]) is LicenseScope.PERSONAL
    assert bf.market_data_field_names() == frozenset()


def test_field_license_block_distinguishes_fields_within_one_response() -> None:
    blk = bf.field_license_block("account", ["cash", "equity"])
    assert blk["license_scope"] == "PERSONAL"
    assert blk["license_sources"] == [MARKET, OWNER]
    assert blk["license_footer"] == lic.PERSONAL_FOOTER
    assert blk["license_field_sources"] == {"cash": OWNER, "equity": MARKET}
    only_owner = bf.field_license_block("account", ["cash", "status"])
    assert only_owner["license_scope"] == "COMMERCIAL_OK"
    assert only_owner["license_footer"] is None


def test_table_is_consistent_with_the_registry_and_the_enforced_names() -> None:
    reg = lic.load_registry()
    doc = json.loads(bf.TABLE_PATH.read_text(encoding="utf-8"))
    assert doc["source_ids"] == {"OWNER_RECORD": OWNER, "MARKET_DATA": MARKET}
    assert reg.scope_of_source(OWNER) is LicenseScope.COMMERCIAL_OK
    assert reg.scope_of_source(MARKET) is LicenseScope.PERSONAL
    assert doc["default_class"] == "MARKET_DATA"
    enforced = set(doc["ast_enforced_market_data_names"])
    assert enforced == set(bf.market_data_field_names())
    seen: set[str] = set()
    for kind, body in doc["kinds"].items():
        for name, spec in body["fields"].items():
            assert spec["class"] in ("OWNER_RECORD", "MARKET_DATA"), (kind, name)
            if name in enforced:
                assert spec["class"] == "MARKET_DATA", (kind, name)
                seen.add(name)
    assert seen == enforced
    # the marked-to-market names the owner listed are all MARKET_DATA somewhere
    for name in (
        "current_price",
        "market_value",
        "unrealized_pl",
        "unrealized_plpc",
        "change_today",
        "lastday_price",
        "long_market_value",
        "portfolio_value",
        "last_equity",
    ):
        assert bf.classify_field("position", name).field_class is bf.FieldClass.MARKET_DATA or (
            bf.classify_field("account", name).field_class is bf.FieldClass.MARKET_DATA
        ), name


def test_helper_is_a_leaf_that_the_order_path_does_not_import() -> None:
    src = Path(bf.__file__).read_text(encoding="utf-8")
    for banned in ("app.orders", "app.risk", "app.brokers", "app.services.order_router"):
        assert f"import {banned}" not in src and f"from {banned}" not in src


async def test_positions_endpoint_declares_per_field_lineage(client) -> None:
    resp = await client.get("/api/v1/positions")
    assert resp.status_code == 200
    body = resp.json()
    # the response exposes market_value / unrealized P&L next to owner fields: PERSONAL as a whole,
    # and the per-field map keeps owner records distinguishable
    assert body["license_scope"] == "PERSONAL"
    assert body["license_footer"] == lic.PERSONAL_FOOTER
    fs = body["license_field_sources"]
    assert fs["qty"] == OWNER and fs["cost_basis"] == OWNER
    assert fs["market_value"] == MARKET and fs["unrealized_pl"] == MARKET
