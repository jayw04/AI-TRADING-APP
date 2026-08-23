"""Map CandidateSnapshot family cards to occurrence drafts. No DB, no MDQ."""

from __future__ import annotations

from pathlib import Path

from app.research.disc001 import history as history_mod
from app.research.disc001.history import HISTORY_FAMILIES, occurrences_from_payload
from app.research.disc001.spec import PRICE_SOURCE_GAP, PRICE_SOURCE_SEP, SCREEN_VERSION


def _payload() -> dict:
    return {
        "as_of": "2026-08-19",
        "screen_id": "DISC-001-WATCHLIST",
        "screen_version": SCREEN_VERSION,
        "sha256": "a" * 64,
        "built_at": "2026-08-20T20:20:01+00:00",
        "families": {
            "OVERSOLD": {
                "available": True,
                "horizon": "1–10d",
                "items": [
                    {
                        "symbol": "nvdA",
                        "status": "Watch",
                        "chips": [{"key": "rsi14", "value": "24"}],
                        "why": "stretched",
                        "price_source": PRICE_SOURCE_SEP,
                        "close": 120.5,
                    }
                ],
            },
            "MOM-NEAR": {"available": False, "items": []},
            "MOM-CORE": {"available": True, "horizon": "weeks–months", "items": []},
            "GAP": {
                "available": True,
                "horizon": "hours–1d",
                "items": [
                    {
                        "symbol": "XYZ",
                        "status": "Backtest Pending",
                        "chips": [{"key": "gap", "value": "+8.1%"}],
                        "why": "gap",
                        "close": 12.0,
                    }
                ],
            },
        },
        "all": {
            "count": 2,
            "items": [
                {
                    "symbol": "ONLYALL",
                    "status": "Watch",
                    "chips": [],
                    "why": "union only",
                    "close": 99.0,
                }
            ],
        },
    }


def test_family_rows_only_and_identity_fields():
    drafts = occurrences_from_payload(_payload())
    assert [d.symbol for d in drafts] == ["NVDA", "XYZ"]
    nvda, xyz = drafts
    assert nvda.candidate_date == "2026-08-19"
    assert nvda.family == "OVERSOLD"
    assert nvda.proposal_price == 120.5
    assert nvda.proposal_price_source == PRICE_SOURCE_SEP
    assert nvda.adjustment_basis == PRICE_SOURCE_SEP
    assert nvda.reason_json == {"chips": [{"key": "rsi14", "value": "24"}], "why": "stretched"}
    assert nvda.screen_version == "v0.3.0"
    assert nvda.snapshot_sha256 == "a" * 64
    assert nvda.snapshot_generated_at == "2026-08-20T20:20:01+00:00"
    assert xyz.family == "GAP"
    assert xyz.proposal_price_source == PRICE_SOURCE_GAP
    assert xyz.adjustment_basis == PRICE_SOURCE_GAP


def test_chip_strings_are_not_parsed_as_prices():
    drafts = occurrences_from_payload(_payload())
    assert drafts[0].proposal_price == 120.5
    assert "24" in drafts[0].reason_json["chips"][0]["value"]


def test_unavailable_family_and_all_tab_are_skipped():
    symbols = {d.symbol for d in occurrences_from_payload(_payload())}
    assert "ONLYALL" not in symbols
    assert all(d.family in HISTORY_FAMILIES for d in occurrences_from_payload(_payload()))


def test_history_module_stays_off_db_order_path_and_mdq():
    text = Path(history_mod.__file__).read_text(encoding="utf-8")
    assert "app.db" not in text
    assert "app.orders" not in text
    assert "app.risk" not in text
    assert "app.brokers" not in text
    assert "mdq_collector" not in text
    assert "from app.mdq" not in text
