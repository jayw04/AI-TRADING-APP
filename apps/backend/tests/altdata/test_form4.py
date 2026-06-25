"""Form 4 ownershipDocument parsing — open-market-buy extraction, role, value (offline)."""

from __future__ import annotations

from app.altdata.sec.form4 import parse_form4

# An officer Form 4: one open-market BUY (P/A, 1000 @ 150.50) and one SELL (S/D) to prove the
# sell is excluded from open_market_buys.
OFFICER_BUY = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>APPLE INC</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>COOK TIMOTHY D</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>0</isDirector><isOfficer>1</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner><officerTitle>CEO</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-06-10</value></transactionDate>
      <transactionCoding><transactionFormType>4</transactionFormType><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>150.50</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-06-10</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>500</value></transactionShares>
        <transactionPricePerShare><value>151.00</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

# A director with only an option exercise (M/A) — NOT an open-market buy.
DIRECTOR_NONBUY = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerCik>0000789019</issuerCik><issuerTradingSymbol>MSFT</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>0</isOfficer></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-06-01</value></transactionDate>
      <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>200</value></transactionShares>
        <transactionPricePerShare><value>0</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_parses_issuer_role_and_open_market_buy():
    f = parse_form4(OFFICER_BUY)
    assert f.issuer_cik == 320193
    assert f.issuer_ticker == "AAPL"
    assert f.owner_name == "COOK TIMOTHY D"
    assert f.is_officer is True and f.is_director is False
    assert f.officer_title == "CEO"
    assert f.is_exec_officer is True
    # only the P/A transaction is an open-market buy; the S/D sell is excluded
    assert len(f.open_market_buys) == 1
    assert f.has_open_market_buy is True
    assert f.buy_shares == 1000.0
    assert f.buy_value == 150500.0
    assert f.open_market_buys[0].date == "2026-06-10"


def test_non_buy_filing_has_no_open_market_buy():
    f = parse_form4(DIRECTOR_NONBUY)
    assert f.issuer_ticker == "MSFT"
    assert f.is_officer is False and f.is_director is True
    assert f.has_open_market_buy is False
    assert f.open_market_buys == []
    assert f.buy_value == 0.0


def test_malformed_xml_degrades_not_raises_on_fields():
    # Missing tables / fields must not crash the parser.
    f = parse_form4("<ownershipDocument><issuer/></ownershipDocument>")
    assert f.issuer_cik is None and f.issuer_ticker is None
    assert f.transactions == ()
    assert f.has_open_market_buy is False
