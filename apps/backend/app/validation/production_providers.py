"""Data-coupled production providers (R5c-2b2) — configuration proven, and every output proven.

Two things must be true of the inputs a forward decision is taken from, and they are NOT the same thing:

  * **identity** — which frozen construction and which identified store were configured. This is
    `forward_identity()`: stable across process restarts, carrying no runtime counters, object
    addresses, connection identities or session dates.
  * **output evidence** — what exact session and input set a call actually returned. This is checked on
    EVERY call and recorded, because a stable identity says nothing about what came back.

A provider that only presented an identity would let a malformed frame — a symbol outside the requested
PIT universe, duplicate symbols, a non-finite score, a forward-filled bar, a series running past the
session — reach the instrument with the record still claiming a correct configuration.

Both providers keep their per-call evidence in an APPEND-ONLY list. The assembly binds the evidence of
the exact call the decision used; a later call cannot overwrite the evidence of the one being committed.

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
REQUIRED_BAR_COLUMNS = ("o", "h", "l", "c", "v")
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


def _finite(value: Any, *, what: str) -> float:
    """Every conversion at this boundary is governed: a value that cannot become a finite float raises
    ProviderOutputError, never a raw ValueError/TypeError from inside the check."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProviderOutputError(f"{what} is not numeric ({value!r})") from exc
    if not math.isfinite(number):
        raise ProviderOutputError(f"{what} is not finite ({value!r})")
    return number


def canonical_symbols(raw_symbols: list[Any]) -> list[str]:
    """Canonicalize, then refuse empties, collisions and non-canonical renderings.

    `MSFT`, `msft` and ` MSFT ` are one security everywhere else in the platform; treating them as three
    names would produce three different evidence digests for one cross-section. Collisions are never
    merged and the first occurrence is never kept — as with the durable book, a disagreement about one
    security is not something this boundary may repair.
    """
    canonical: list[str] = []
    seen: dict[str, Any] = {}
    for raw in raw_symbols:
        symbol = str(raw).strip().upper()
        if not symbol:
            raise ProviderOutputError("the scored frame carries an empty symbol")
        if symbol in seen:
            raise ProviderOutputError(
                f"the scored frame carries duplicate canonical symbol {symbol!r} "
                f"({seen[symbol]!r} and {raw!r})")
        if str(raw) != symbol:
            raise ProviderOutputError(
                f"the scored frame carries a non-canonical symbol {raw!r}; the registered scoring "
                f"construction returns canonical tickers, and rewriting one here would hide the drift")
        seen[symbol] = raw
        canonical.append(symbol)
    return canonical


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
    universe_fn: Any                          # callable(session, n) -> the exact PIT universe
    spec: ScoresSpec = field(default_factory=ScoresSpec)
    trading_days: Any = None                  # callable(session) -> bool, to tie output to a session
    output_evidence: list[dict[str, Any]] = field(default_factory=list, init=False)

    @property
    def last_output_evidence(self) -> dict[str, Any]:
        """The most recent call's evidence. The assembly must bind the evidence of the call the
        decision actually used — see `output_evidence`, which is append-only for exactly that reason."""
        return dict(self.output_evidence[-1]) if self.output_evidence else {}

    def forward_identity(self) -> str:
        return _identity("scores", self.store_identity, self.spec)

    def __call__(self, session: date) -> Any:
        if self.trading_days is not None and not self.trading_days(session):
            raise ProviderOutputError(
                f"the identified store holds no session {session.isoformat()}; scores cannot be tied "
                f"to a session the data does not have")
        try:
            expected = self.universe_fn(session, self.spec.universe_n)
        except IntegrityStop:
            raise
        except Exception as exc:
            raise ProviderOutputError(
                f"the registered PIT universe could not be constructed for {session.isoformat()}: "
                f"{type(exc).__name__}: {exc}") from exc
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
        evidence = validate_scores(frame, session, self.spec,
                                   provider_identity=self.forward_identity(),
                                   expected_universe=expected)
        self.output_evidence.append(evidence)
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
    output_evidence: list[dict[str, Any]] = field(default_factory=list, init=False)

    @property
    def last_output_evidence(self) -> dict[str, Any]:
        return dict(self.output_evidence[-1]) if self.output_evidence else {}

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
        self.output_evidence.append(validate_bars(
            frame, symbol=sym, as_of=as_of, spec=self.spec, requested_n=n,
            store_sessions=self.session_dates, provider_identity=self.forward_identity(),
            is_market_symbol=sym == self.market_symbol.upper()))
        return frame


def validate_scores(frame: Any, session: date, spec: ScoresSpec, *, provider_identity: str,
                    expected_universe: list[str] | None = None) -> dict[str, Any]:
    """Refuse a frame that cannot be the frozen construction's output for THIS session.

    `expected_universe` is the exact PIT universe the scoring construction was asked for. The returned
    names must be a SUBSET of it: the construction legitimately drops names with insufficient usable
    history, but it can never score a security the universe did not contain, and never more names than
    the universe held.
    """
    if frame is None or getattr(frame, "empty", True):
        raise ProviderOutputError(f"the scoring construction returned nothing for {session}")
    try:
        columns = list(frame.columns)
        raw_index = list(frame.index)
    except (AttributeError, TypeError) as exc:
        raise ProviderOutputError(f"the scored output is not a frame: {type(frame).__name__}") from exc
    missing = [c for c in REQUIRED_SCORE_COLUMNS if c not in columns]
    if missing:
        raise ProviderOutputError(f"the scored frame is missing column(s) {missing}")

    symbols = canonical_symbols(raw_index)
    if len(symbols) < spec.min_names:
        raise ProviderOutputError(
            f"{len(symbols)} name(s) scored, below the frozen minimum {spec.min_names}: the "
            f"cross-section is degenerate and would standardize against almost nothing")
    if len(symbols) > spec.universe_n:
        raise ProviderOutputError(
            f"{len(symbols)} name(s) scored, above the frozen universe size {spec.universe_n} — this "
            f"is not the registered universe")

    expected_digest = None
    if expected_universe is not None:
        expected = canonical_symbols(list(expected_universe))
        expected_digest = _digest(sorted(expected))
        outside = sorted(set(symbols) - set(expected))
        if outside:
            raise ProviderOutputError(
                f"the scored frame carries {len(outside)} symbol(s) the registered PIT universe for "
                f"{session.isoformat()} does not contain (e.g. {outside[:5]}) — these scores are not "
                f"the registered construction's")
        if len(symbols) > len(expected):
            raise ProviderOutputError(
                f"{len(symbols)} name(s) scored from a universe of {len(expected)}")

    values: list[list[float]] = []
    for position, symbol in enumerate(symbols):
        row: list[float] = []
        for column in REQUIRED_SCORE_COLUMNS:
            try:
                raw = frame[column].iloc[position]
            except (KeyError, IndexError, AttributeError) as exc:
                raise ProviderOutputError(
                    f"{column} could not be read for {symbol!r}: {exc}") from exc
            row.append(_finite(raw, what=f"{column} for {symbol!r} on {session.isoformat()}"))
        values.append([symbol, *row])                      # type: ignore[list-item]

    return {
        "provider_identity": provider_identity,
        "session_date": session.isoformat(),
        "scored_names": len(symbols),
        "expected_universe_size": len(expected_universe) if expected_universe is not None else None,
        "expected_universe_digest": expected_digest,
        "returned_symbol_set_digest": _digest(sorted(symbols)),
        "symbol_set_digest": _digest(sorted(symbols)),      # retained name for existing consumers
        "frame_digest": _digest(values),
    }


def validate_bars(frame: Any, *, symbol: str, as_of: date, spec: BarsSpec,
                  store_sessions: tuple[date, ...], provider_identity: str,
                  is_market_symbol: bool, requested_n: int = -1) -> dict[str, Any]:
    """Refuse a bar series that runs past the session, repeats a mark, or invents a date."""
    if frame is None or getattr(frame, "empty", True):
        raise ProviderOutputError(f"no bars for {symbol} as of {as_of.isoformat()}")
    try:
        columns = list(frame.columns)
        raw_index = list(frame.index)
    except (AttributeError, TypeError) as exc:
        raise ProviderOutputError(f"the {symbol} bars are not a frame: {type(frame).__name__}") from exc
    missing = [c for c in REQUIRED_BAR_COLUMNS if c not in columns]
    if missing:
        raise ProviderOutputError(f"the {symbol} bars are missing column(s) {missing}")

    index: list[date] = []
    for raw in raw_index:
        value = raw.date() if hasattr(raw, "date") else raw
        if not isinstance(value, date):
            raise ProviderOutputError(
                f"the {symbol} series carries a non-date index value {raw!r}")
        index.append(value)

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

    closes: list[float] = []
    for position, d in enumerate(index):
        try:
            raw = frame["c"].iloc[position]
        except (KeyError, IndexError, AttributeError) as exc:
            raise ProviderOutputError(
                f"the {symbol} close on {d.isoformat()} could not be read: {exc}") from exc
        close = _finite(raw, what=f"the {symbol} close on {d.isoformat()}")
        if close <= 0:
            raise ProviderOutputError(
                f"the {symbol} close on {d.isoformat()} is not a usable price ({raw!r})")
        closes.append(close)

    # The 200-session completeness applies to the REGIME call — the one that requests the MA window
    # (requested_n >= ma_sessions). A caller asking the market proxy for fewer bars for another purpose
    # gets what it asked for; the regime cannot be run on an incomplete MA.
    needs_ma = is_market_symbol and (requested_n < 0 or requested_n >= spec.ma_sessions)
    if needs_ma and len(index) < spec.ma_sessions:
        raise ProviderOutputError(
            f"the market proxy has {len(index)} session(s) as of {as_of.isoformat()}, below the "
            f"{spec.ma_sessions}-session moving average the regime requires")

    return {
        "provider_identity": provider_identity,
        "symbol": symbol,
        "as_of": as_of.isoformat(),
        "requested_n": requested_n,
        "sessions": len(index),
        "first_session": index[0].isoformat(),
        "last_session": index[-1].isoformat(),
        "is_market_symbol": is_market_symbol,
        "series_digest": _digest([[d.isoformat(), c] for d, c in zip(index, closes, strict=True)]),
    }
