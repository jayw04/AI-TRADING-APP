"""Production decision provider (R5c-2a) — the REAL frozen instrument decides, or nothing does.

Every test here drives the actual `MomentumDaily` through the §7A-proven `DriftCtxAdapter` /
`capture_seam` path. Nothing in the provider recomputes a ranking, a weight, a regime state or the
trade gate, so the tests assert on what the instrument produced and on the refusals that keep a
non-decision from being recorded as one.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.strategies.drift_audit_driver import DriftCtxAdapter
from app.validation.decision_provider import (
    DecisionProviderError,
    InstrumentSnapshot,
    ProductionDecisionProvider,
    capture_instrument_snapshot,
)
from app.validation.forward_window import PRODUCTION_STRATEGY_COMMIT

SESSION = date(2026, 7, 24)
NEXT_SESSION = date(2026, 7, 27)
SYMBOLS = ["SPY", "AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
NAMES = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
STRATEGY_ID = 11
DURABLE_ID = "instrument-durable-state-901"
LEDGER_ID = "shadow-ledger-accounting-901"
CAPTURED_AT = "2026-07-24T20:05:00Z"
STORE_IDENTITY = "store-identity-under-test"
REGIME_SOURCE = "broad-equal-weight-proxy@test"


def _scores(day: date) -> pd.DataFrame:
    """A deterministic eligible cross-section (raw > 0 and z >= 0 for every name)."""
    return pd.DataFrame(
        {"momentum": [0.30, 0.25, 0.20, 0.15, 0.10, 0.05],
         "winsorized": [0.30, 0.25, 0.20, 0.15, 0.10, 0.05],
         "zscore": [1.5, 1.2, 0.9, 0.6, 0.3, 0.1],
         "rank": [1, 2, 3, 4, 5, 6],
         "score": [1.5, 1.2, 0.9, 0.6, 0.3, 0.1]},
        index=pd.Index(NAMES, name="ticker"))


def _bars(symbol: str, as_of: date, n: int) -> pd.DataFrame:
    """The §7A harness's bar shape: SPY in a strong uptrend (risk-on), other names flat."""
    n = max(n, 220)
    closes = [80.0 + 0.2 * i for i in range(n)] if symbol == "SPY" else [100.0] * n
    idx = pd.to_datetime([as_of] * n)
    df = pd.DataFrame({"o": closes, "h": closes, "l": closes, "c": closes, "v": [1_000] * n},
                      index=idx)
    df.index.name = "t"
    return df


def _price(symbol: str, session: date) -> float | None:
    return 100.0


def _adapter() -> DriftCtxAdapter:
    from app.strategies.deployment_state import initial_blob
    from strategies_user.templates.momentum_daily import _K_DEPLOYMENT

    a = DriftCtxAdapter(symbols=list(SYMBOLS), strategy_id=STRATEGY_ID,
                        scores_provider=_scores, bars_provider=_bars, sim_day=SESSION)
    # The instrument refuses to evaluate an uninitialized deployment lifecycle (ADR 0044); the forward
    # run starts from the same NEVER_DEPLOYED blob the §7A harness uses.
    a._state[_K_DEPLOYMENT] = initial_blob().to_dict()
    return a


def _strategy(adapter: DriftCtxAdapter):
    from strategies_user.templates.momentum_daily import MomentumDaily
    params = {**MomentumDaily.default_params, "order_pacing_seconds": 0.0,
              "regime_mode": "graduated", "use_market_regime_filter": True,
              "initial_seed_investable_gross": 0.60}
    return MomentumDaily(ctx=adapter, params=params)


def _snapshot(strategy, adapter, session=SESSION, **kw) -> InstrumentSnapshot:
    return capture_instrument_snapshot(
        strategy, adapter, session, captured_at=kw.pop("captured_at", CAPTURED_AT),
        regime_source_identity=kw.pop("regime_source_identity", REGIME_SOURCE),
        store_identity_sha256=kw.pop("store_identity_sha256", STORE_IDENTITY), **kw)


def _provider(strategy, adapter, snapshot, **kw) -> ProductionDecisionProvider:
    return ProductionDecisionProvider(
        strategy=strategy, adapter=adapter, snapshot=snapshot,
        durable_state_id=kw.pop("durable_state_id", DURABLE_ID),
        fill_price_fn=kw.pop("fill_price_fn", _price), **kw)


@pytest.fixture
def instrument():
    adapter = _adapter()
    strategy = _strategy(adapter)
    return strategy, adapter


# ---- the real instrument decides -------------------------------------------------------------------

def test_the_provider_returns_the_real_instruments_decision(instrument):
    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter)
    decision = _provider(strategy, adapter, snap)(SESSION)

    assert decision.record.date == SESSION.isoformat()
    assert decision.instrument_identity == PRODUCTION_STRATEGY_COMMIT
    assert decision.durable_state_id == DURABLE_ID != LEDGER_ID
    assert decision.snapshot_digest == snap.snapshot_digest       # bound to THIS run's snapshot
    # a cold-start (NEVER_DEPLOYED, flat) book seeds on day one — the instrument's own behaviour
    assert decision.record.target_names
    assert set(decision.record.weights) == set(decision.record.target_names)
    assert decision.record.trade_initiated is True
    assert decision.record.is_seed is True


def test_the_weights_come_from_the_instruments_own_sizing_seam(instrument):
    """The provider never restates the weighting rule; it carries what `target_weights` produced."""
    strategy, adapter = instrument
    decision = _provider(strategy, adapter, _snapshot(strategy, adapter))(SESSION)
    observed = decision.record.weights
    expected = strategy.target_weights(list(decision.record.target_names))
    assert observed == pytest.approx(expected)


def test_the_snapshot_is_open_provenance_only(instrument):
    strategy, adapter = instrument
    d = _snapshot(strategy, adapter).to_open_provenance()
    assert d["strategy_identity"] == PRODUCTION_STRATEGY_COMMIT
    assert d["strategy_class"].endswith(":MomentumDaily")
    assert len(d["params_digest"]) == 64 and len(d["durable_state_digest"]) == 64
    assert d["store_identity_sha256"] == STORE_IDENTITY
    forbidden = {"scores", "ranking", "weights", "strategy_return", "sharpe", "equity", "pnl"}
    assert not (forbidden & set(d))


def test_the_snapshot_digest_covers_every_bound_field(instrument):
    strategy, adapter = instrument
    base = _snapshot(strategy, adapter)
    for field_name, value in [("strategy_identity", "0" * 40), ("params_digest", "x" * 64),
                              ("durable_state_digest", "y" * 64), ("regime_source_identity", "other"),
                              ("store_identity_sha256", "moved"), ("captured_at", "2026-07-24T21:00Z")]:
        altered = InstrumentSnapshot(**{**base.to_open_provenance(),
                                        "durable_state_keys": base.durable_state_keys,
                                        field_name: value, "snapshot_digest": ""}).with_digest()
        assert altered.snapshot_digest != base.snapshot_digest, field_name


# ---- fail-closed cases -----------------------------------------------------------------------------

def test_a_missing_snapshot_is_refused(instrument):
    strategy, adapter = instrument
    provider = _provider(strategy, adapter, None)                 # type: ignore[arg-type]
    with pytest.raises(DecisionProviderError, match="no instrument snapshot"):
        provider(SESSION)


def test_a_snapshot_for_another_session_is_refused(instrument):
    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter, session=NEXT_SESSION)
    with pytest.raises(DecisionProviderError, match="snapshot was taken for"):
        _provider(strategy, adapter, snap)(SESSION)


def test_a_tampered_snapshot_digest_is_refused(instrument):
    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter)
    forged = InstrumentSnapshot(**{**snap.to_open_provenance(),
                                   "durable_state_keys": snap.durable_state_keys,
                                   "snapshot_digest": "f" * 64})
    with pytest.raises(DecisionProviderError, match="digest does not verify"):
        _provider(strategy, adapter, forged)(SESSION)


def test_a_wrong_strategy_identity_is_refused(instrument):
    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter, strategy_identity="deadbeef" * 5)
    with pytest.raises(DecisionProviderError, match="not the frozen production instrument"):
        _provider(strategy, adapter, snap)(SESSION)


def test_durable_state_moving_between_snapshot_and_decision_is_refused(instrument):
    """The decision must belong to the state it was snapshotted under."""
    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter)
    adapter._state["injected_between_snapshot_and_decision"] = {"rev": 1}
    with pytest.raises(DecisionProviderError, match="durable state changed"):
        _provider(strategy, adapter, snap)(SESSION)


def test_an_account_4_context_is_refused(instrument):
    strategy, adapter = instrument
    adapter.account_id = 4
    with pytest.raises(DecisionProviderError, match="Account 4"):
        _provider(strategy, adapter, _snapshot(strategy, adapter))(SESSION)


def test_an_empty_durable_state_identity_is_refused(instrument):
    strategy, adapter = instrument
    with pytest.raises(DecisionProviderError, match="durable-state identity is empty"):
        _provider(strategy, adapter, _snapshot(strategy, adapter), durable_state_id="  ")(SESSION)


def test_a_second_decision_for_the_same_session_is_refused(instrument):
    """Deciding twice is refused. In practice an even stronger refusal fires first: deciding moved the
    instrument's own book and durable state, so the snapshot no longer describes the state a second
    decision would be taken under."""
    strategy, adapter = instrument
    provider = _provider(strategy, adapter, _snapshot(strategy, adapter))
    provider(SESSION)
    with pytest.raises(DecisionProviderError,
                       match="lifecycle_identity|instrument_book_digest|durable state changed"
                             "|already decided"):
        provider(SESSION)


def test_an_instrument_without_the_sizing_seam_is_refused(instrument, monkeypatch):
    """`capture_seam` refuses to assume production sizing when the class exposes no `target_weights`;
    the provider surfaces that as an integrity stop rather than an AttributeError. (monkeypatch removes
    the seam only for this test — mutating the shared class would leak into every other suite.)"""
    strategy, adapter = instrument
    monkeypatch.delattr(type(strategy), "target_weights", raising=True)
    with pytest.raises(DecisionProviderError, match="sizing seam"):
        _provider(strategy, adapter, _snapshot(strategy, adapter))(SESSION)


def test_an_instrument_that_raises_is_refused(instrument):
    strategy, adapter = instrument

    async def boom(*a, **k):
        raise RuntimeError("the instrument blew up")

    strategy.on_bar = boom
    with pytest.raises(DecisionProviderError, match="failed to decide"):
        _provider(strategy, adapter, _snapshot(strategy, adapter))(SESSION)


def test_a_decision_naming_targets_without_weights_is_refused(instrument, monkeypatch):
    """The absent-evaluation shape: `capture_seam` yields targets with no weights when the class
    returned before `_evaluate`. It is an integrity stop, never a flat no-trade observation."""
    strategy, adapter = instrument
    from app.strategies import drift_audit_driver as drv
    from app.strategies.drift_audit import SeamRecord

    real = drv.capture_seam

    def stripped(s, a, day):
        rec = real(s, a, day)
        return SeamRecord(date=rec.date, scores=rec.scores, eligible=rec.eligible,
                          ranking=rec.ranking, target_names=rec.target_names, weights={},
                          regime_gross=rec.regime_gross, trade_initiated=False,
                          trigger=rec.trigger, is_seed=rec.is_seed)

    monkeypatch.setattr(drv, "capture_seam", stripped)
    with pytest.raises(DecisionProviderError, match="did not evaluate this session"):
        _provider(strategy, adapter, _snapshot(strategy, adapter))(SESSION)


def test_a_decision_for_the_wrong_session_is_refused(instrument, monkeypatch):
    strategy, adapter = instrument
    from app.strategies import drift_audit_driver as drv
    from app.strategies.drift_audit import SeamRecord

    real = drv.capture_seam

    def misdated(s, a, day):
        rec = real(s, a, day)
        return SeamRecord(**{**rec.__dict__, "date": NEXT_SESSION.isoformat()})

    monkeypatch.setattr(drv, "capture_seam", misdated)
    with pytest.raises(DecisionProviderError, match="the instrument decided"):
        _provider(strategy, adapter, _snapshot(strategy, adapter))(SESSION)


# ---- the instrument's own decision-state book ------------------------------------------------------

def test_the_decision_carries_the_instruments_own_state_book(instrument):
    strategy, adapter = instrument
    decision = _provider(strategy, adapter, _snapshot(strategy, adapter))(SESSION)
    state = decision.instrument_state
    assert state.weight_drift_threshold == pytest.approx(strategy.params["weight_drift_pct"])
    assert state.backstop_days == strategy.params["backstop_max_days"]
    assert set(state.held) == set(state.current_weights)


# ---- the snapshot binds the CONTEXT that supplies the decision's inputs (R5c-2a review) -------------

def test_the_snapshot_binds_the_bound_context_not_a_description(instrument):
    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter)
    assert snap.adapter_class.endswith(":DriftCtxAdapter")
    assert snap.adapter_strategy_id == STRATEGY_ID
    assert len(snap.universe_digest) == 64
    # provider identities are derived from the bound callables, not from caller-supplied strings
    assert ":_scores|code=" in snap.scores_provider_identity     # implementation, not just a name
    assert ":_bars|code=" in snap.bars_provider_identity
    assert len(snap.instrument_book_digest) == 64 and len(snap.context_digest) == 64


def test_a_different_scores_provider_is_refused(instrument):
    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter)

    def other_scores(day):
        return _scores(day)

    adapter.scores_provider = other_scores
    with pytest.raises(DecisionProviderError, match="scores_provider_identity"):
        _provider(strategy, adapter, snap)(SESSION)


def test_a_different_bars_provider_is_refused(instrument):
    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter)

    def other_bars(symbol, as_of, n):
        return _bars(symbol, as_of, n)

    adapter.bars_provider = other_bars
    with pytest.raises(DecisionProviderError, match="bars_provider_identity"):
        _provider(strategy, adapter, snap)(SESSION)


def test_a_different_strategy_registration_is_refused(instrument):
    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter)
    adapter.strategy_id = 99
    with pytest.raises(DecisionProviderError, match="adapter_strategy_id"):
        _provider(strategy, adapter, snap)(SESSION)


def test_a_changed_universe_is_refused(instrument):
    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter)
    adapter.symbols = [*SYMBOLS, "GGG"]
    with pytest.raises(DecisionProviderError, match="universe_digest"):
        _provider(strategy, adapter, snap)(SESSION)


def test_a_changed_instrument_book_is_refused(instrument):
    """Equity or positions moving between the snapshot and the decision changes what the instrument
    would decide, so the snapshot no longer describes this decision."""
    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter)
    adapter.equity = adapter.equity + 1
    with pytest.raises(DecisionProviderError, match="instrument_book_digest"):
        _provider(strategy, adapter, snap)(SESSION)


def test_the_context_digest_covers_each_bound_field(instrument):
    from app.validation.decision_provider import context_identity

    strategy, adapter = instrument
    base = context_identity(adapter)["context_digest"]
    adapter.strategy_id = 42
    assert context_identity(adapter)["context_digest"] != base


# ---- the LIVE instrument is revalidated, not just recorded (R5c-2a re-review) -----------------------

def test_a_parameter_changed_after_the_snapshot_is_refused(instrument):
    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter)
    strategy.params["max_names"] = 3
    with pytest.raises(DecisionProviderError, match="params_digest"):
        _provider(strategy, adapter, snap)(SESSION)


def test_a_parameter_added_after_the_snapshot_is_refused(instrument):
    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter)
    strategy.params["an_unregistered_knob"] = True
    with pytest.raises(DecisionProviderError, match="params_digest"):
        _provider(strategy, adapter, snap)(SESSION)


def test_a_parameter_removed_after_the_snapshot_is_refused(instrument):
    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter)
    strategy.params.pop("weight_drift_pct")
    with pytest.raises(DecisionProviderError, match="params_digest"):
        _provider(strategy, adapter, snap)(SESSION)


def test_a_different_strategy_class_is_refused(instrument):
    """The snapshot describes the instrument it was taken of; substituting another class is refused
    even when the identity string and parameters are copied across."""
    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter)

    class SubstituteInstrument:
        params = dict(strategy.params)

        async def on_bar(self, bar):        # pragma: no cover - never reached
            raise AssertionError("the substitute must never be evaluated")

    with pytest.raises(DecisionProviderError, match="strategy_class"):
        _provider(SubstituteInstrument(), adapter, snap)(SESSION)


def test_a_lifecycle_change_after_the_snapshot_is_refused(instrument):
    """The lifecycle identity is DERIVED from the instrument's own deployment blob, so a deployment
    state that advances between snapshot and decision invalidates the snapshot."""
    from strategies_user.templates.momentum_daily import _K_DEPLOYMENT

    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter)
    blob = dict(adapter._state[_K_DEPLOYMENT])
    blob["state"] = "DEPLOYED"
    adapter._state[_K_DEPLOYMENT] = blob
    with pytest.raises(DecisionProviderError, match="lifecycle_identity|durable state changed"):
        _provider(strategy, adapter, snap)(SESSION)


def test_the_lifecycle_identity_is_derived_from_the_deployment_blob(instrument):
    strategy, adapter = instrument
    snap = _snapshot(strategy, adapter)
    assert snap.lifecycle_identity.startswith("NEVER_DEPLOYED@rev")


def test_an_unchanged_instrument_is_accepted(instrument):
    strategy, adapter = instrument
    decision = _provider(strategy, adapter, _snapshot(strategy, adapter))(SESSION)
    assert decision.record.date == SESSION.isoformat()


# ---- provider identity is instance- and closure-complete -------------------------------------------

def test_two_closures_from_one_factory_over_different_stores_differ():
    from app.validation.decision_provider import provider_identity

    def make_scores(store_path: str):
        def scores(day):                      # same module, same qualname, different binding
            return store_path
        return scores

    a, b = make_scores("/data/store-a.duckdb"), make_scores("/data/store-b.duckdb")
    assert provider_identity(a) != provider_identity(b)
    assert provider_identity(a) == provider_identity(make_scores("/data/store-a.duckdb"))


def test_the_same_bound_method_on_two_instances_differs():
    from app.validation.decision_provider import provider_identity

    class Provider:
        def __init__(self, store: str):
            self.store = store

        def scores(self, day):
            return self.store

    assert provider_identity(Provider("a").scores) != provider_identity(Provider("b").scores)
    assert provider_identity(Provider("a").scores) == provider_identity(Provider("a").scores)


def test_two_callable_objects_of_one_class_with_different_configuration_differ():
    from app.validation.decision_provider import provider_identity

    class Scores:
        def __init__(self, store: str):
            self.store = store

        def __call__(self, day):
            return self.store

    assert provider_identity(Scores("a")) != provider_identity(Scores("b"))
    assert provider_identity(Scores("a")) == provider_identity(Scores("a"))


def test_equal_implementation_and_configuration_share_an_identity():
    from functools import partial

    from app.validation.decision_provider import provider_identity

    def scores(store, day):
        return store

    assert provider_identity(partial(scores, "a")) == provider_identity(partial(scores, "a"))
    assert provider_identity(partial(scores, "a")) != provider_identity(partial(scores, "b"))


def test_an_unstable_closure_fails_closed():
    """A closure over an object with no governed identity cannot reproduce in another process, so it is
    refused rather than given a name that would collide with a differently-bound provider."""
    from app.validation.decision_provider import UnstableIdentity, provider_identity

    class OpaqueStore:                        # no forward_identity(), default repr carries an address
        pass

    def make(store):
        def scores(day):
            return store
        return scores

    with pytest.raises(UnstableIdentity, match="stable identity"):
        provider_identity(make(OpaqueStore()))


def test_a_provider_may_declare_its_own_identity():
    """The contract production wiring should use: an explicit identity derived from the bound store."""
    from app.validation.decision_provider import provider_identity

    class DeclaredStore:
        def forward_identity(self) -> str:
            return "duckdb:/data/factor.duckdb@sha256:abc"

    def make(store):
        def scores(day):
            return store
        return scores

    identity = provider_identity(make(DeclaredStore()))
    assert "closure=" in identity
    assert provider_identity(make(DeclaredStore())) == identity


def test_an_absent_provider_fails_closed():
    from app.validation.decision_provider import UnstableIdentity, provider_identity

    with pytest.raises(UnstableIdentity, match="no provider is bound"):
        provider_identity(None)
