"""Data-coupled production providers (R5c-2b2).

The load-bearing distinction: `forward_identity()` proves which frozen construction and identified store
were CONFIGURED; the per-call evidence proves what session and input set were actually RETURNED. A
stable identity never substitutes for validating the output.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from app.validation.production_providers import (
    BarsSpec,
    ProductionBarsProvider,
    ProductionScoresProvider,
    ProviderIdentityError,
    ProviderOutputError,
    ScoresSpec,
    validate_bars,
    validate_scores,
)

SESSION = date(2026, 7, 24)
STORE_A = "a" * 64
STORE_B = "b" * 64
MARKET = "SPY"


def _sessions(end: date, n: int) -> tuple[date, ...]:
    out: list[date] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return tuple(sorted(out))


SESSIONS = _sessions(SESSION, 260)


def _scores_frame(n: int = 60, **overrides) -> pd.DataFrame:
    tickers = overrides.pop("tickers", [f"T{i:04d}" for i in range(n)])
    values = [1.0 - i * 0.001 for i in range(len(tickers))]
    frame = pd.DataFrame({"momentum": values, "winsorized": values, "zscore": values,
                          "rank": list(range(1, len(tickers) + 1)), "score": values},
                         index=pd.Index(tickers, name="ticker"))
    for column, value in overrides.items():
        frame[column] = value
    return frame


class _Accessor:
    def __init__(self, frame=None, raises=None):
        self._frame = frame if frame is not None else _scores_frame()
        self._raises = raises
        self.calls: list[dict] = []

    def momentum_scores(self, as_of=None, *, n=500, lookback_days=105, skip_days=21):
        self.calls.append({"as_of": as_of, "n": n, "lookback_days": lookback_days,
                           "skip_days": skip_days})
        if self._raises:
            raise self._raises
        return self._frame


def _scores_provider(**kw) -> ProductionScoresProvider:
    return ProductionScoresProvider(
        accessor=kw.pop("accessor", _Accessor()), store_identity=kw.pop("store_identity", STORE_A),
        spec=kw.pop("spec", ScoresSpec()), trading_days=kw.pop("trading_days", lambda d: d in SESSIONS))


def _bars_provider(**kw) -> ProductionBarsProvider:
    proxy = kw.pop("proxy_closes", {d: 100.0 + i * 0.1 for i, d in enumerate(SESSIONS)})
    return ProductionBarsProvider(
        proxy_closes=proxy, name_prices=kw.pop("name_prices", lambda s, d: 50.0),
        store_identity=kw.pop("store_identity", STORE_A), market_symbol=MARKET,
        session_dates=kw.pop("session_dates", SESSIONS), spec=kw.pop("spec", BarsSpec()))


# ---- identity: configuration, and nothing else --------------------------------------------------------

def test_a_different_store_gives_a_different_identity():
    assert _scores_provider().forward_identity() != _scores_provider(
        store_identity=STORE_B).forward_identity()
    assert _bars_provider().forward_identity() != _bars_provider(
        store_identity=STORE_B).forward_identity()


@pytest.mark.parametrize("change", [{"universe_n": 201}, {"lookback_days": 251}, {"skip_days": 20},
                                    {"price_field": "close"}, {"min_names": 31},
                                    {"pit_rules": "something else"}])
def test_one_changed_frozen_parameter_gives_a_different_scores_identity(change):
    from dataclasses import replace

    base = _scores_provider()
    changed = _scores_provider(spec=replace(ScoresSpec(), **change))
    assert base.forward_identity() != changed.forward_identity()


@pytest.mark.parametrize("change", [{"proxy_n": 501}, {"ma_sessions": 199}, {"price_field": "close"},
                                    {"weighting": "cap-weighted"},
                                    {"cutoff_semantics": "forward filled"}])
def test_one_changed_frozen_parameter_gives_a_different_bars_identity(change):
    from dataclasses import replace

    assert _bars_provider().forward_identity() != _bars_provider(
        spec=replace(BarsSpec(), **change)).forward_identity()


def test_the_same_construction_is_stable_across_instances_and_calls():
    """Stable across a process restart: no runtime counters, addresses or connection identities."""
    first = _scores_provider().forward_identity()
    second = _scores_provider(accessor=_Accessor()).forward_identity()   # a different object
    assert first == second

    provider = _scores_provider()
    provider(SESSION)
    assert provider.forward_identity() == first                          # unchanged by having run


def test_the_session_date_is_not_part_of_the_identity():
    """These providers are not session-specific objects; the session belongs to the output evidence."""
    provider = _scores_provider()
    before = provider.forward_identity()
    provider(SESSION)
    provider(SESSIONS[-2])
    assert provider.forward_identity() == before


def test_an_unidentified_store_cannot_present_an_identity():
    for identity in ["", "   ", None]:
        with pytest.raises(ProviderIdentityError, match="no identified store"):
            _scores_provider(store_identity=identity).forward_identity()
        with pytest.raises(ProviderIdentityError, match="no identified store"):
            _bars_provider(store_identity=identity).forward_identity()


def test_the_identity_names_the_registered_implementation():
    from dataclasses import replace

    other = _scores_provider(spec=replace(ScoresSpec(), implementation="some.other.module"))
    assert other.forward_identity() != _scores_provider().forward_identity()


# ---- scores: the frozen construction is requested, and the output is proven ---------------------------

def test_the_provider_requests_the_frozen_construction():
    accessor = _Accessor()
    _scores_provider(accessor=accessor)(SESSION)
    assert accessor.calls == [{"as_of": SESSION, "n": 200, "lookback_days": 252, "skip_days": 21}]


def test_the_output_evidence_ties_the_frame_to_the_session():
    provider = _scores_provider()
    provider(SESSION)
    evidence = provider.last_output_evidence
    assert evidence["session_date"] == SESSION.isoformat()
    assert evidence["scored_names"] == 60
    assert len(evidence["symbol_set_digest"]) == 64 and len(evidence["frame_digest"]) == 64
    assert evidence["provider_identity"] == provider.forward_identity()


def test_a_session_the_store_does_not_have_is_refused():
    provider = _scores_provider(trading_days=lambda d: False)
    with pytest.raises(ProviderOutputError, match="holds no session"):
        provider(SESSION)


def test_a_construction_failure_is_refused_not_swallowed():
    provider = _scores_provider(accessor=_Accessor(raises=RuntimeError("no universe")))
    with pytest.raises(ProviderOutputError, match="scoring construction failed"):
        provider(SESSION)


def test_duplicate_symbols_are_refused():
    frame = _scores_frame(tickers=["AAA", "BBB", "AAA"] + [f"T{i}" for i in range(40)])
    with pytest.raises(ProviderOutputError, match="duplicate symbol"):
        validate_scores(frame, SESSION, ScoresSpec(), provider_identity="x")


@pytest.mark.parametrize("column", ["momentum", "zscore", "score", "rank"])
def test_a_nonfinite_value_is_refused(column):
    frame = _scores_frame()
    frame.loc[frame.index[3], column] = float("nan")
    with pytest.raises(ProviderOutputError, match="not finite"):
        validate_scores(frame, SESSION, ScoresSpec(), provider_identity="x")


def test_a_missing_column_is_refused():
    frame = _scores_frame().drop(columns=["zscore"])
    with pytest.raises(ProviderOutputError, match="missing column"):
        validate_scores(frame, SESSION, ScoresSpec(), provider_identity="x")


def test_an_empty_symbol_is_refused():
    frame = _scores_frame(tickers=["", *[f"T{i}" for i in range(40)]])
    with pytest.raises(ProviderOutputError, match="empty symbol"):
        validate_scores(frame, SESSION, ScoresSpec(), provider_identity="x")


def test_a_degenerate_cross_section_is_refused():
    with pytest.raises(ProviderOutputError, match="below the frozen minimum"):
        validate_scores(_scores_frame(n=5), SESSION, ScoresSpec(), provider_identity="x")


def test_more_names_than_the_registered_universe_is_refused():
    with pytest.raises(ProviderOutputError, match="above the frozen universe size"):
        validate_scores(_scores_frame(n=201), SESSION, ScoresSpec(), provider_identity="x")


def test_an_empty_frame_is_refused():
    with pytest.raises(ProviderOutputError, match="returned nothing"):
        validate_scores(_scores_frame(n=0), SESSION, ScoresSpec(), provider_identity="x")


# ---- bars: cutoff, monotonicity, no invented sessions -------------------------------------------------

def test_the_market_series_stops_at_the_session():
    provider = _bars_provider()
    frame = provider(MARKET, SESSION, 220)
    assert frame.index.max().date() == SESSION
    assert provider.last_output_evidence["last_session"] == SESSION.isoformat()
    assert provider.last_output_evidence["is_market_symbol"] is True


def test_an_earlier_as_of_returns_only_earlier_sessions():
    provider = _bars_provider()
    earlier = SESSIONS[-30]
    frame = provider(MARKET, earlier, 220)
    assert frame.index.max().date() == earlier


def test_a_series_running_past_the_session_is_refused():
    future = pd.to_datetime([SESSIONS[-2], SESSIONS[-1], SESSION + timedelta(days=1)])
    frame = pd.DataFrame({"o": [1.0] * 3, "h": [1.0] * 3, "l": [1.0] * 3, "c": [1.0] * 3,
                          "v": [1] * 3}, index=future)
    with pytest.raises(ProviderOutputError, match="runs past"):
        validate_bars(frame, symbol="AAA", as_of=SESSION, spec=BarsSpec(),
                      store_sessions=SESSIONS, provider_identity="x", is_market_symbol=False)


def test_duplicate_marks_are_refused():
    index = pd.to_datetime([SESSIONS[-2], SESSIONS[-2], SESSIONS[-1]])
    frame = pd.DataFrame({"c": [1.0, 1.0, 1.0], "o": [1.0] * 3, "h": [1.0] * 3, "l": [1.0] * 3,
                          "v": [1] * 3}, index=index)
    with pytest.raises(ProviderOutputError, match="repeats a session"):
        validate_bars(frame, symbol="AAA", as_of=SESSION, spec=BarsSpec(),
                      store_sessions=SESSIONS, provider_identity="x", is_market_symbol=False)


def test_a_nonmonotonic_series_is_refused():
    index = pd.to_datetime([SESSIONS[-1], SESSIONS[-2]])
    frame = pd.DataFrame({"c": [1.0, 1.0], "o": [1.0] * 2, "h": [1.0] * 2, "l": [1.0] * 2,
                          "v": [1] * 2}, index=index)
    with pytest.raises(ProviderOutputError, match="not strictly increasing"):
        validate_bars(frame, symbol="AAA", as_of=SESSION, spec=BarsSpec(),
                      store_sessions=SESSIONS, provider_identity="x", is_market_symbol=False)


def test_an_invented_session_is_refused_as_a_forward_fill():
    """A date the identified store does not have can only have been synthesized."""
    index = pd.to_datetime([SESSIONS[-3], date(2026, 7, 18), SESSIONS[-1]])   # 07-18 is a Saturday
    frame = pd.DataFrame({"c": [1.0] * 3, "o": [1.0] * 3, "h": [1.0] * 3, "l": [1.0] * 3,
                          "v": [1] * 3}, index=index.sort_values())
    with pytest.raises(ProviderOutputError, match="forward fill beyond the governed construction"):
        validate_bars(frame, symbol="AAA", as_of=SESSION, spec=BarsSpec(),
                      store_sessions=SESSIONS, provider_identity="x", is_market_symbol=False)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0.0, -1.0])
def test_an_unusable_price_is_refused(bad):
    index = pd.to_datetime([SESSIONS[-2], SESSIONS[-1]])
    frame = pd.DataFrame({"c": [10.0, bad], "o": [1.0] * 2, "h": [1.0] * 2, "l": [1.0] * 2,
                          "v": [1] * 2}, index=index)
    with pytest.raises(ProviderOutputError, match="not a usable price"):
        validate_bars(frame, symbol="AAA", as_of=SESSION, spec=BarsSpec(),
                      store_sessions=SESSIONS, provider_identity="x", is_market_symbol=False)


def test_a_proxy_too_short_for_the_moving_average_is_refused():
    short = _sessions(SESSION, 50)
    provider = _bars_provider(session_dates=short,
                              proxy_closes={d: 100.0 for d in short})
    with pytest.raises(ProviderOutputError, match="below the .*moving average"):
        provider(MARKET, SESSION, 220)


def test_a_name_series_may_be_shorter_than_the_moving_average():
    """The MA requirement is the regime's, not every constituent's."""
    provider = _bars_provider()
    frame = provider("AAA", SESSION, 10)
    assert len(frame) == 10
    assert provider.last_output_evidence["is_market_symbol"] is False


def test_the_bars_evidence_records_the_series_it_returned():
    provider = _bars_provider()
    provider(MARKET, SESSION, 220)
    evidence = provider.last_output_evidence
    assert evidence["symbol"] == MARKET and evidence["as_of"] == SESSION.isoformat()
    assert evidence["sessions"] == 220
    assert len(evidence["series_digest"]) == 64
    assert evidence["provider_identity"] == provider.forward_identity()


def test_a_name_with_no_marks_is_refused():
    provider = _bars_provider(name_prices=lambda s, d: None)
    with pytest.raises(ProviderOutputError, match="no bars"):
        provider("AAA", SESSION, 10)
