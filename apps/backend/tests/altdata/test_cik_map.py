"""Ticker->CIK mapping + the explicit unresolved-coverage tracking (offline)."""

from __future__ import annotations

from app.altdata.sec.cik_map import cik_to_10digit, parse_company_tickers

RAW = {
    "0": {"cik_str": 320193, "ticker": "aapl", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
    "2": {"cik_str": 320193, "ticker": "AAPL", "title": "dup — kept first"},  # dup ticker ignored
    "3": {"ticker": "BAD"},  # missing cik — skipped
}


def test_parse_and_resolve_upper_cased():
    m = parse_company_tickers(RAW)
    assert m.resolve("AAPL") == 320193
    assert m.resolve("aapl") == 320193  # case-insensitive
    assert m.resolve("MSFT") == 789019
    assert m.resolve("BAD") is None  # the malformed row was skipped
    assert m.n == 2


def test_resolve_all_reports_unresolved():
    m = parse_company_tickers(RAW)
    resolved, unresolved = m.resolve_all(["AAPL", "MSFT", "ZZZZ", "nope"])
    assert resolved == {"AAPL": 320193, "MSFT": 789019}
    assert unresolved == ["ZZZZ", "NOPE"]  # the coverage hole is explicit, not swallowed


def test_cik_zero_padding():
    assert cik_to_10digit(320193) == "0000320193"
    assert cik_to_10digit("789019") == "0000789019"
