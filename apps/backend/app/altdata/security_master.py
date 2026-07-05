"""Point-in-Time Security Master (CAP-024, ADR 0037 Decision 9) — v0 minimal resolver.

Alternative data arrives keyed by inconsistent identity: SEC by **CIK**, price/factor data by
**ticker**, Quiver government contracts by **company/recipient name** (often a subsidiary). Every
EAD event must resolve to a stable security identity **or** be explicitly, typed-unresolved,
because a *silent bad mapping fabricates an event study*.

**v0 is deliberately minimal** (ADR 0037: "do not overbuild v0"): it resolves the common cases
and *labels* the rest. It does not yet solve historical ticker reuse, mergers, delistings, or
subsidiary→parent mapping — those are reserved reasons + v1 work (design note §6). The one
non-negotiable property: **no silent bad mapping** — every uncertain case returns unresolved with
a typed reason, never a confident-looking wrong id.

Read-only, pure, deterministic, off the order path (ADR 0037 Decision 11 CI invariant). Built
from a ``CikMap`` (SEC ``company_tickers.json``); a point-in-time ticker/issuer history backs the
``as_of`` semantics in v1 without a contract change.

See ``Docs/design/TradingWorkbench_EAD_Phase0B_SecurityMaster_CAP024_v0.1.md``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher

from app.altdata.sec.cik_map import CikMap

# --- pre-registered thresholds (design note §11; confirm at Phase 0 sign-off) ----------------
FUZZY_MIN = 0.90      # minimum similarity for a fuzzy resolve; below -> insufficient_confidence
FUZZY_MARGIN = 0.03   # top-2 fuzzy candidates within this -> ambiguous_name, not a coin-flip

# --- typed unresolved reasons (design note §3) -----------------------------------------------
REASON_AMBIGUOUS = "ambiguous_name"
REASON_NO_PUBLIC = "no_public_security"
REASON_SUBSIDIARY = "subsidiary_unmapped"     # reserved for v1 (needs a subsidiary map)
REASON_TICKER_REUSED = "ticker_reused"        # reserved for v1 (needs ticker-change history)
REASON_INSUFFICIENT = "insufficient_confidence"

# Trailing corporate-suffix tokens dropped during normalization (design note §4).
_SUFFIX = frozenset({
    "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LLC", "LP", "LLP",
    "LTD", "LIMITED", "PLC", "NV", "SA", "AG", "SE", "COM", "CLASS", "A", "B", "C",
    "HLDG", "HLDGS", "HOLDING", "HOLDINGS", "GRP", "GROUP", "THE",
})

_NON_ALNUM = re.compile(r"[^0-9A-Z]+")


def _fold(s: str) -> str:
    """NFKD-fold accents to ASCII (é -> e)."""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_name(name: str) -> tuple[str, frozenset[str]]:
    """Deterministic company-name normalization (design note §4). Returns ``(joined, tokens)``.
    Upper/fold/``&``->AND, strip punctuation to spaces, drop the leading ``THE`` and trailing
    corporate-suffix tokens. This is the one place sloppiness would create silent bad mappings,
    so it is explicit and tested."""
    s = _fold(name).upper().replace("&", " AND ")
    s = _NON_ALNUM.sub(" ", s)
    tokens = s.split()
    if tokens and tokens[0] == "THE":
        tokens = tokens[1:]
    while tokens and tokens[-1] in _SUFFIX:
        tokens = tokens[:-1]
    return " ".join(tokens), frozenset(tokens)


@dataclass(frozen=True)
class ResolutionResult:
    """The outcome of one resolution. ``is_resolved`` iff a canonical id was assigned; an
    unresolved result carries a typed ``unresolved_reason`` and ``confidence = 0.0``."""

    resolved_security_id: str | None
    resolved_ticker: str | None
    cik: int | None
    confidence: float
    method: str                 # 'cik' | 'ticker' | 'exact_name' | 'fuzzy_name' | 'unresolved'
    unresolved_reason: str | None

    @property
    def is_resolved(self) -> bool:
        return self.resolved_security_id is not None


def _security_id(cik: int) -> str:
    """Canonical id — the zero-padded CIK (the most stable public-issuer key). Opaque to callers."""
    return f"CIK{cik:010d}"


class SecurityMaster:
    """v0 resolver over a ``CikMap``. Construct once (the map is a snapshot); ``resolve_security``
    is pure and deterministic."""

    def __init__(self, cik_map: CikMap, *, fuzzy_min: float = FUZZY_MIN,
                 fuzzy_margin: float = FUZZY_MARGIN) -> None:
        self._fuzzy_min = fuzzy_min
        self._fuzzy_margin = fuzzy_margin
        self._by_ticker: dict[str, int] = dict(cik_map.by_ticker)
        self._titles: dict[int, str] = dict(cik_map.titles)
        # first (lowest-index) ticker per CIK, for resolved_ticker
        self._cik_to_ticker: dict[int, str] = {}
        for tk, c in cik_map.by_ticker.items():
            self._cik_to_ticker.setdefault(c, tk)
        # normalized-name indexes
        self._norm: dict[int, str] = {}
        self._tok: dict[int, frozenset[str]] = {}
        self._name_index: dict[str, set[int]] = {}     # exact normalized name -> {cik}
        self._token_index: dict[str, set[int]] = {}    # token -> {cik} (fuzzy candidate pruning)
        for c, title in self._titles.items():
            norm, tokens = normalize_name(title)
            self._norm[c] = norm
            self._tok[c] = tokens
            if norm:
                self._name_index.setdefault(norm, set()).add(c)
            for t in tokens:
                self._token_index.setdefault(t, set()).add(c)

    # --- resolution ---------------------------------------------------------------------------

    def resolve_security(
        self, *, issuer_name: str | None = None, ticker: str | None = None,
        cik: int | None = None, as_of: date | None = None,
    ) -> ResolutionResult:
        """Resolve to a canonical security id via the tiered hierarchy (design note §2). The
        harder identifier wins: CIK -> ticker -> exact normalized name -> gated fuzzy name ->
        unresolved. ``as_of`` is accepted but v0 is as-of-agnostic (design note §6)."""
        # tier 1 — CIK (known filer)
        if cik is not None and int(cik) in self._titles:
            return self._resolved(int(cik), "cik", 1.0)

        # tier 2 — exact ticker
        if ticker:
            c = self._by_ticker.get(ticker.strip().upper())
            if c is not None:
                return self._resolved(c, "ticker", 0.99)

        # tier 3/4 — name
        if issuer_name:
            norm, tokens = normalize_name(issuer_name)
            if norm:
                exact = self._name_index.get(norm)
                if exact:
                    if len(exact) == 1:
                        return self._resolved(next(iter(exact)), "exact_name", 0.95)
                    return self._unresolved(REASON_AMBIGUOUS)
                return self._resolve_fuzzy(norm, tokens)

        # nothing matched (or nothing given / an unknown ticker/cik)
        return self._unresolved(REASON_NO_PUBLIC)

    def _resolve_fuzzy(self, norm: str, tokens: frozenset[str]) -> ResolutionResult:
        """Gated fuzzy tier (design note §5): candidates must share >=1 normalized token (prevents
        zero-overlap cross-company matches), the best must clear ``fuzzy_min``, and it must be
        unique by ``fuzzy_margin`` — otherwise unresolved with a typed reason. Never a silent pick."""
        candidates: set[int] = set()
        for t in tokens:
            candidates |= self._token_index.get(t, set())
        if not candidates:
            return self._unresolved(REASON_NO_PUBLIC)
        scored = sorted(
            ((self._similarity(norm, tokens, c), c) for c in candidates),
            key=lambda x: (x[0], -x[1]), reverse=True,
        )
        top_score, top_cik = scored[0]
        if top_score < self._fuzzy_min:
            return self._unresolved(REASON_INSUFFICIENT)
        if len(scored) > 1 and (top_score - scored[1][0]) < self._fuzzy_margin:
            return self._unresolved(REASON_AMBIGUOUS)
        return self._resolved(top_cik, "fuzzy_name", round(top_score, 4))

    def _similarity(self, norm: str, tokens: frozenset[str], cik: int) -> float:
        """Similarity = sequence ratio, **gated to 0 unless the names share >=1 token**. The
        token gate is the anti-false-positive guard; the high ``fuzzy_min`` bar does the rest."""
        if tokens.isdisjoint(self._tok[cik]):
            return 0.0
        return SequenceMatcher(None, norm, self._norm[cik]).ratio()

    # --- result builders ----------------------------------------------------------------------

    def _resolved(self, cik: int, method: str, confidence: float) -> ResolutionResult:
        return ResolutionResult(
            resolved_security_id=_security_id(cik),
            resolved_ticker=self._cik_to_ticker.get(cik),
            cik=cik, confidence=confidence, method=method, unresolved_reason=None,
        )

    @staticmethod
    def _unresolved(reason: str) -> ResolutionResult:
        return ResolutionResult(
            resolved_security_id=None, resolved_ticker=None, cik=None,
            confidence=0.0, method="unresolved", unresolved_reason=reason,
        )
