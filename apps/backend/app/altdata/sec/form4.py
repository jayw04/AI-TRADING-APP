"""Parse an SEC Form 4 ``ownershipDocument`` XML into structured insider transactions (ADR 0027).

A Form 4 reports one reporting owner's transactions in an issuer's securities. The signal we
reproduce (INSIDER-001) cares about **open-market buys** — non-derivative transactions with
``transactionCode = 'P'`` and ``acquiredDisposedCode = 'A'`` — by an **exec/officer**, with
their **dollar value** and **role**. This module extracts exactly that, defensively (a missing
field degrades to ``None``/0, never raises on a malformed filing — the §2 validation gate
counts those).

XML safety: stdlib ``ElementTree`` (expat) does not resolve external entities, which is
adequate for trusted SEC content; no external DTD/entity is processed.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET  # noqa: S405 — trusted SEC XML, no external entities


def _truthy(text: str | None) -> bool:
    return (text or "").strip().lower() in ("1", "true", "yes", "y")


def _wrapped_value(parent: ET.Element, path: str) -> str | None:
    """Form 4 wraps many fields as ``<field><value>X</value></field>``; return X (or the
    element's own text if not wrapped). ``None`` if the path is absent."""
    el = parent.find(path)
    if el is None:
        return None
    inner = el.find("value")
    text = inner.text if inner is not None else el.text
    return text.strip() if text and text.strip() else None


def _to_float(text: str | None) -> float:
    if not text:
        return 0.0
    try:
        return float(text.replace(",", "").strip())
    except ValueError:
        return 0.0


@dataclass(frozen=True)
class Form4Transaction:
    code: str               # transaction code; 'P' = open-market or private purchase
    acquired_disposed: str  # 'A' acquired (buy) | 'D' disposed (sell)
    shares: float
    price_per_share: float
    date: str | None        # transaction date, ISO 'YYYY-MM-DD'

    @property
    def value(self) -> float:
        return self.shares * self.price_per_share

    @property
    def is_open_market_buy(self) -> bool:
        return self.code == "P" and self.acquired_disposed == "A"


@dataclass(frozen=True)
class Form4:
    issuer_cik: int | None
    issuer_ticker: str | None
    issuer_name: str | None
    owner_name: str | None
    is_officer: bool
    is_director: bool
    is_ten_percent_owner: bool
    officer_title: str | None
    transactions: tuple[Form4Transaction, ...]

    @property
    def open_market_buys(self) -> list[Form4Transaction]:
        return [t for t in self.transactions if t.is_open_market_buy]

    @property
    def buy_value(self) -> float:
        return round(sum(t.value for t in self.open_market_buys), 2)

    @property
    def buy_shares(self) -> float:
        return round(sum(t.shares for t in self.open_market_buys), 4)

    @property
    def is_exec_officer(self) -> bool:
        """The conviction filter's role gate: an officer (execs are officers)."""
        return self.is_officer

    @property
    def has_open_market_buy(self) -> bool:
        return any(t.is_open_market_buy for t in self.transactions)


def parse_form4(xml: str) -> Form4:
    """Parse a Form 4 ``ownershipDocument`` XML string into a :class:`Form4`."""
    root = ET.fromstring(xml)  # noqa: S314 — trusted SEC content, no external entities

    issuer = root.find("issuer")
    issuer_cik: int | None = None
    issuer_ticker = issuer_name = None
    if issuer is not None:
        raw_cik = (issuer.findtext("issuerCik") or "").strip()
        if raw_cik.isdigit():
            issuer_cik = int(raw_cik)
        issuer_ticker = (issuer.findtext("issuerTradingSymbol") or "").strip().upper() or None
        issuer_name = (issuer.findtext("issuerName") or "").strip() or None

    owner = root.find("reportingOwner")
    owner_name = None
    is_officer = is_director = is_ten = False
    officer_title = None
    if owner is not None:
        owner_name = (owner.findtext("reportingOwnerId/rptOwnerName") or "").strip() or None
        rel = owner.find("reportingOwnerRelationship")
        if rel is not None:
            is_officer = _truthy(rel.findtext("isOfficer"))
            is_director = _truthy(rel.findtext("isDirector"))
            is_ten = _truthy(rel.findtext("isTenPercentOwner"))
            officer_title = (rel.findtext("officerTitle") or "").strip() or None

    txns: list[Form4Transaction] = []
    nd = root.find("nonDerivativeTable")
    if nd is not None:
        for t in nd.findall("nonDerivativeTransaction"):
            code = (t.findtext("transactionCoding/transactionCode") or "").strip()
            txns.append(Form4Transaction(
                code=code,
                acquired_disposed=(_wrapped_value(
                    t, "transactionAmounts/transactionAcquiredDisposedCode") or "").strip().upper(),
                shares=_to_float(_wrapped_value(t, "transactionAmounts/transactionShares")),
                price_per_share=_to_float(_wrapped_value(t, "transactionAmounts/transactionPricePerShare")),
                date=_wrapped_value(t, "transactionDate"),
            ))

    return Form4(
        issuer_cik=issuer_cik, issuer_ticker=issuer_ticker, issuer_name=issuer_name,
        owner_name=owner_name, is_officer=is_officer, is_director=is_director,
        is_ten_percent_owner=is_ten, officer_title=officer_title, transactions=tuple(txns),
    )
