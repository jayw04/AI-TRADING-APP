"""Data-coupled production providers (R5c-2b2) — configuration proven, and every output proven.

Two things must be true of the inputs a forward decision is taken from, and they are NOT the same thing:

  * **identity** — which frozen construction and which identified store were configured. This is
    `forward_identity()`: stable across process restarts, carrying no runtime counters, object
    addresses, connection identities or session dates.
  * **output evidence** — what exact session and input set a call actually returned. This is checked on
    EVERY call and recorded, because a stable identity says nothing about what came back.

A provider that only presented an identity would let a malformed frame — duplicate symbols, a
non-finite score, a forward-filled bar, a series running past the session — reach the instrument with
the record still claiming a correct configuration.

## The frozen constructions

Scores: `universe_asof(n=200)` → `compute_momentum_batch(252/21)` over `closeadj`, as of the session
close, PIT by lifetime bounds and trailing dollar volume.

Regime bars: the broad equal-weight market proxy — the month-end union of `universe_asof(n=500)`,
equal-weight mean of per-constituent daily returns, cumulative index, 200-session MA — over `closeadj`,
with no session after the requested as-of included. SPY is absent from SEP, which is why the proxy
exists at all (PREREG §2).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from app.validation.forward_window import IntegrityStop

SCORES_IMPLEMENTATION = "app.factor_data.factors.engine.momentum_scores"
PROXY_IMPLEMENTATION = "scripts.backtest_momentum_stage4.build_market_proxy"
REQUIRED_SCORE_COLUMNS = ("momentum", "winsorized", "zscore", "rank", "score")
MIN_SCORED_NAMES = 30                     # stage2 MIN_NAMES: fewer is a degenerate cross-section


class ProviderError(IntegrityStop):
    """A provider could not be trusted for this session. Fails closed."""


class ProviderIdentityError(ProviderError):
    """The provider's CONFIGURATION cannot be established (unidentified store, unfrozen parameter)."""


class ProviderOutputError(ProviderError):
    """What the provider RETURNED is not usable for this session — regardless of how it was
    configured."""


@dataclass(frozen=True)
class ScoresSpec:
    """The frozen scoring construction. Every field enters the identity."""
    universe_n: int = 200
    lookback_days: int = 252
    skip_days: int = 21
    min_names: int = MIN_SCORED_NAMES
    price_field: str = "closeadj"
    implementation: str = SCORES_IMPLEMENTATION
    universe_construction: str = "universe_asof: top-n by trailing dollar volume, PIT"
    pit_rules: str = "firstpricedate <= as_of <= lastpricedate; no row after as_of is read"
    as_of_semantics: str = "scores as of the session close; the store is pinned to the session"


@dataclass(frozen=True)
class BarsSpec:
    """The frozen regime/proxy construction. Every field enters the identity."""
    proxy_n: int = 500
    ma_sessions: int = 200
    price_field: str = "closeadj"
    implementation: str = PROXY_IMPLEMENTATION
    proxy_construction: str = "month-end union of universe_asof(n=proxy_n); equal-weight basket"
    weighting: str = "equal-weight mean of per-constituent daily returns (skipna)"
    return_definition: str = "panel.pct_change() per constituent; index = cumprod(1 + mean return)"
    cutoff_semantics: str = "no session after the requested as_of is included; no forward fill"


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _identity(kind: str, store_identity: str, spec: Any) -> str:
    if not str(store_identity or "").strip():
        raise ProviderIdentityError(
            f"the {kind} provider has no identified store; an unidentified input cannot be configured "
            f"evidence")
    body = {"kind": kind, "store_identity": store_identity, "spec": asdict(spec)}
    return f"{kind}@{_digest(body)}"


@dataclass
class ProductionScoresProvider:
    """`momentum_scores` over the identified store, with every returned frame validated."""
    accessor: Any
    store_identity: str
    spec: ScoresSpec = field(default_factory=ScoresSpec)
    trading_days: Any = None                  # callable(session) -> bool, to tie output to a session
    last_output_evidence: dict[str, Any] = field(default_factory=dict, init=False)

    def forward_identity(self) -> str:
        return _identity("scores", self.store_identity, self.spec)

    def __call__(self, session: date) -> Any:
        if self.trading_days is not None and not self.trading_days(session):
            raise ProviderOutputError(
                f"the identified store holds no session {session.isoformat()}; scores cannot be tied "
                f"to a session the data does not have")
        try:
            frame = self.accessor.momentum_scores(
                as_of=session, n=self.spec.universe_n, lookback_days=self.spec.lookback_days,
                skip_days=self.spec.skip_days)
        except IntegrityStop:
            raise
        except Exception as exc:
            raise ProviderOutputError(
                f"the scoring construction failed for {session.isoformat()}: "
                f"{type(exc).__name__}: {exc}") from exc
        self.last_output_evidence = validate_scores(frame, session, self.spec,
                                                    provider_identity=self.forward_identity())
        return frame


@dataclass
class ProductionBarsProvider:
    """The regime proxy series (and per-name marks) as bars, with every returned frame validated."""
    proxy_closes: dict[date, float]           # the governed proxy index, session -> level
    name_prices: Any                          # callable(symbol, session) -> float | None
    store_identity: str
    market_symbol: str
    session_dates: tuple[date, ...]           # the store's own sessions, ascending
    spec: BarsSpec = field(default_factory=BarsSpec)
    last_output_evidence: dict[str, Any] = field(default_factory=dict, init=False)

    def forward_identity(self) -> str:
        return _identity("bars", self.store_identity, self.spec)

    def __call__(self, symbol: str, as_of: date, n: int) -> Any:
        import pandas as pd

        sym = str(symbol).upper()
        sessions = [d for d in self.session_dates if d <= as_of]
        if sym == self.market_symbol.upper():
            series = [(d, self.proxy_closes[d]) for d in sessions if d in self.proxy_closes]
        else:
            series = [(d, p) for d in sessions
                      if (p := self.name_prices(sym, d)) is not None]
        series = series[-n:] if n > 0 else series
        closes = [c for _, c in series]
        frame = pd.DataFrame(
            {"o": closes, "h": closes, "l": closes, "c": closes, "v": [1] * len(closes)},
            index=pd.to_datetime([d for d, _ in series]))
        frame.index.name = "t"
        self.last_output_evidence = validate_bars(
            frame, symbol=sym, as_of=as_of, spec=self.spec,
            store_sessions=self.session_dates, provider_identity=self.forward_identity(),
            is_market_symbol=sym == self.market_symbol.upper())
        return frame


def validate_scores(frame: Any, session: date, spec: ScoresSpec, *, provider_identity: str
                    ) -> dict[str, Any]:
    """Refuse a frame that cannot be the frozen construction's output for THIS session."""
    if frame is None or getattr(frame, "empty", True):
        raise ProviderOutputError(f"the scoring construction returned nothing for {session}")
    missing = [c for c in REQUIRED_SCORE_COLUMNS if c not in frame.columns]
    if missing:
        raise ProviderOutputError(f"the scored frame is missing column(s) {missing}")

    symbols = [str(t) for t in frame.index]
    if any(not s.strip() for s in symbols):
        raise ProviderOutputError("the scored frame carries an empty symbol")
    if len(set(symbols)) != len(symbols):
        duplicates = sorted({s for s in symbols if symbols.count(s) > 1})
        raise ProviderOutputError(f"the scored frame carries duplicate symbol(s) {duplicates}")
    if len(symbols) < spec.min_names:
        raise ProviderOutputError(
            f"{len(symbols)} name(s) scored, below the frozen minimum {spec.min_names}: the "
            f"cross-section is degenerate and would standardize against almost nothing")
    if len(symbols) > spec.universe_n:
        raise ProviderOutputError(
            f"{len(symbols)} name(s) scored, above the frozen universe size {spec.universe_n} — this "
            f"is not the registered universe")

    for column in REQUIRED_SCORE_COLUMNS:
        for symbol, value in zip(symbols, frame[column].tolist(), strict=True):
            if value is None or not math.isfinite(float(value)):
                raise ProviderOutputError(
                    f"{column} for {symbol!r} is not finite ({value!r}) on {session.isoformat()}")

    return {
        "provider_identity": provider_identity,
        "session_date": session.isoformat(),
        "scored_names": len(symbols),
        "symbol_set_digest": _digest(sorted(symbols)),
        "frame_digest": _digest([[s, *[float(frame[c].iloc[i]) for c in REQUIRED_SCORE_COLUMNS]]
                                 for i, s in enumerate(symbols)]),
    }


def validate_bars(frame: Any, *, symbol: str, as_of: date, spec: BarsSpec,
                  store_sessions: tuple[date, ...], provider_identity: str,
                  is_market_symbol: bool) -> dict[str, Any]:
    """Refuse a bar series that runs past the session, repeats a mark, or invents a date."""
    if frame is None or getattr(frame, "empty", True):
        raise ProviderOutputError(f"no bars for {symbol} as of {as_of.isoformat()}")
    index = [d.date() if hasattr(d, "date") else d for d in frame.index]

    if any(d > as_of for d in index):
        raise ProviderOutputError(
            f"the {symbol} series runs past {as_of.isoformat()} — a bar after the session would let the "
            f"decision see the future")
    if len(set(index)) != len(index):
        raise ProviderOutputError(f"the {symbol} series repeats a session (duplicate marks)")
    if any(b <= a for a, b in zip(index, index[1:], strict=False)):
        raise ProviderOutputError(f"the {symbol} series is not strictly increasing in date")

    known = set(store_sessions)
    invented = [d.isoformat() for d in index if d not in known]
    if invented:
        raise ProviderOutputError(
            f"the {symbol} series carries session(s) {invented[:5]} the identified store does not have "
            f"— a forward fill beyond the governed construction")

    closes = [float(c) for c in frame["c"].tolist()]
    for d, c in zip(index, closes, strict=True):
        if not math.isfinite(c) or c <= 0:
            raise ProviderOutputError(
                f"the {symbol} close on {d.isoformat()} is not a usable price ({c!r})")

    if is_market_symbol and len(index) < spec.ma_sessions:
        raise ProviderOutputError(
            f"the market proxy has {len(index)} session(s) as of {as_of.isoformat()}, below the "
            f"{spec.ma_sessions}-session moving average the regime requires")

    return {
        "provider_identity": provider_identity,
        "symbol": symbol,
        "as_of": as_of.isoformat(),
        "sessions": len(index),
        "first_session": index[0].isoformat(),
        "last_session": index[-1].isoformat(),
        "is_market_symbol": is_market_symbol,
        "series_digest": _digest([[d.isoformat(), c] for d, c in zip(index, closes, strict=True)]),
    }
