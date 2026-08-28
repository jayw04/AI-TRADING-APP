"""The dispatch-time factor-readiness interlock.

2026-08-03: the production refresh producer was stopped, the watchdog alerted, and
nothing stopped the books. ``readiness FAIL -> alert -> [MISSING] -> dispatch``.
Detection is not a veto. Each test names the production failure it prevents.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.strategies.factor_readiness import (
    DEFAULT_MAX_LAG_DAYS,
    evaluate_factor_readiness,
)

NOW = datetime(2026, 8, 10, 14, 24, tzinfo=UTC)  # Monday, strategy-7 dispatch


def _store(tmp: Path, sep_max: date, lpd_max: date | None = None, name: str | None = None) -> Path:
    duckdb = pytest.importorskip("duckdb")
    p = tmp / (name or f"fd_{sep_max}_{lpd_max or sep_max}.duckdb")
    con = duckdb.connect(str(p))
    con.execute("CREATE TABLE sep (ticker VARCHAR, date DATE, close DOUBLE, volume DOUBLE)")
    con.execute("INSERT INTO sep VALUES ('AAA', ?, 1.0, 1.0)", [sep_max])
    con.execute("CREATE TABLE tickers (ticker VARCHAR, lastpricedate DATE)")
    con.execute("INSERT INTO tickers VALUES ('AAA', ?)", [lpd_max or sep_max])
    con.close()
    return p


def _sealed(tmp: Path, as_of: date, total: int = 510) -> Path:
    p = tmp / f"_sealed_{as_of}.json"
    p.write_text(
        json.dumps({"as_of": as_of.isoformat(), "counts": {"total": total}}), encoding="utf-8"
    )
    return p


def _ready(tmp: Path, *, overall="PASS", age_h=1.0) -> Path:
    p = tmp / "_factor_readiness.json"
    ts = (NOW - timedelta(hours=age_h)).isoformat().replace("+00:00", "Z")
    p.write_text(
        json.dumps({"overall_readiness": overall, "evaluated_at_utc": ts}), encoding="utf-8"
    )
    return p


_UNSET = object()


def _eval(tmp: Path, **over):
    # The readiness artifact defaults to a healthy PASS so that the store/seal cases below
    # isolate the condition they name. It is REQUIRED in production, so leaving it out of
    # the default would make every one of those tests assert the artifact check instead.
    #
    # The sentinel is load-bearing: `_ready` WRITES, and `over.pop(k, _ready(tmp))` would
    # evaluate that default on every call — overwriting the very artifact a caller passing
    # `readiness_path=` had just written, one line earlier, into the same filename.
    readiness = over.pop("readiness_path", _UNSET)
    kw = {
        "store_path": over.pop("store_path", None) or _store(tmp, NOW.date()),
        "sealed_path": over.pop("sealed_path", None) or _sealed(tmp, NOW.date()),
        "readiness_path": _ready(tmp) if readiness is _UNSET else readiness,
        "now": NOW,
    }
    kw.update(over)
    return evaluate_factor_readiness(**kw)


# --------------------------------------------------------------- the happy path


def test_current_data_with_verified_generation_passes(tmp_path):
    v = _eval(tmp_path)
    assert v.ok, v.reason
    assert v.checks["lag_days"] == 0


def test_the_happy_path_actually_verified_producer_liveness(tmp_path):
    """A PASS is only a PASS if all three legs were checked. The systemd timer lives on
    the host, outside the container, so producer liveness is only ever known from the
    published artifact — and the verdict must say so rather than implying it."""
    v = _eval(tmp_path)
    assert v.ok
    assert v.checks["producer_liveness_verified"] is True
    assert v.checks["readiness_required"] is True


# ------------------------------------------------- the 2026-08-03 scenario itself


def test_stale_store_blocks_dispatch(tmp_path):
    """THE case. Producer stopped 2026-08-03; by Monday the frontier is 7 sessions
    old. The books would NOT hold — _resolve_as_of clamps the decision date down and
    they trade on stale factors. Dispatch must be refused."""
    stale = _store(tmp_path, date(2026, 7, 31))
    v = _eval(tmp_path, store_path=stale, sealed_path=_sealed(tmp_path, date(2026, 7, 31)))
    assert not v.ok
    assert "stale" in v.reason
    assert v.checks["lag_days"] == 10


@pytest.mark.parametrize("lag", [DEFAULT_MAX_LAG_DAYS, DEFAULT_MAX_LAG_DAYS + 1])
def test_tolerance_boundary(tmp_path, lag):
    d = NOW.date() - timedelta(days=lag)
    v = _eval(tmp_path, store_path=_store(tmp_path, d), sealed_path=_sealed(tmp_path, d))
    assert v.ok is (lag <= DEFAULT_MAX_LAG_DAYS)


def test_lagging_lastpricedate_blocks_even_when_sep_is_fresh(tmp_path):
    """A lagging lastpricedate removes names from the ranking pool outright, which is
    worse than ranking them on old data (2026-07-06). The effective frontier is the
    earlier of the two, so fresh SEP must not mask it."""
    p = _store(tmp_path, NOW.date(), lpd_max=date(2026, 6, 12))
    v = _eval(tmp_path, store_path=p)
    assert not v.ok
    assert v.checks["effective_frontier"] == "2026-06-12"


# --------------------------------------------------------------- fail closed


def test_missing_store_blocks(tmp_path):
    v = _eval(tmp_path, store_path=tmp_path / "nope.duckdb")
    assert not v.ok and "absent" in v.reason


def test_unreadable_store_blocks(tmp_path):
    bad = tmp_path / "corrupt.duckdb"
    bad.write_text("not a database", encoding="utf-8")
    v = _eval(tmp_path, store_path=bad)
    assert not v.ok and "unreadable" in v.reason


def test_missing_sealed_artifact_blocks(tmp_path):
    """Fresh data alone is not enough — without a seal, nothing proves the data came
    from a run that PASSED verification."""
    v = _eval(tmp_path, sealed_path=tmp_path / "absent.json")
    assert not v.ok and "sealed universe artifact absent" in v.reason


def test_corrupt_sealed_artifact_blocks(tmp_path):
    p = tmp_path / "_factor_refresh_universe_sealed.json"
    p.write_text("{not json", encoding="utf-8")
    v = _eval(tmp_path, sealed_path=p)
    assert not v.ok and "unreadable" in v.reason


def test_seal_older_than_the_store_blocks(tmp_path):
    """The seal advances only after verify+swap. A seal behind the store means the
    current data was never blessed by a passing run — exactly what a failed refresh
    leaves behind."""
    v = _eval(
        tmp_path,
        store_path=_store(tmp_path, NOW.date()),
        sealed_path=_sealed(tmp_path, NOW.date() - timedelta(days=3)),
    )
    assert not v.ok
    assert "was not produced by a verified run" in v.reason


# ------------------------------------------- REQUIRED producer-liveness verdict


def test_readiness_fail_blocks_even_when_data_looks_current(tmp_path):
    """The exact 2026-08-03 window: the producer was already dead while the store
    still looked clean. A FAIL verdict must veto regardless of freshness."""
    v = _eval(tmp_path, readiness_path=_ready(tmp_path, overall="FAIL"))
    assert not v.ok
    assert "producer readiness verdict is FAIL" in v.reason
    assert v.checks["producer_liveness_verified"] is True


def test_stale_readiness_verdict_blocks(tmp_path):
    """A verdict from days ago says nothing about THIS dispatch."""
    v = _eval(tmp_path, readiness_path=_ready(tmp_path, age_h=48))
    assert not v.ok and "stale relative to this dispatch" in v.reason


def test_unparseable_readiness_timestamp_blocks(tmp_path):
    p = tmp_path / "_factor_readiness.json"
    p.write_text(
        json.dumps({"overall_readiness": "PASS", "evaluated_at_utc": "whenever"}), encoding="utf-8"
    )
    v = _eval(tmp_path, readiness_path=p)
    assert not v.ok and "evaluated_at_utc" in v.reason


def test_readiness_pass_is_honoured(tmp_path):
    v = _eval(tmp_path, readiness_path=_ready(tmp_path))
    assert v.ok
    assert v.checks["overall_readiness"] == "PASS"
    assert v.checks["producer_liveness_verified"] is True


def test_absent_readiness_artifact_BLOCKS(tmp_path):
    """The half that was missing until 2026-08-08, and the reason this file changed.

    When the interlock first shipped, an absent artifact was tolerated: the gate
    recorded ``producer_liveness_verified=False`` and dispatched anyway. That is the
    2026-08-03 defect wearing a different hat — a check that stops checking instead of
    failing. A publisher that never ran, whose timer is dead, or that cannot write to
    the data volume produces exactly this state, and none of those is evidence that the
    producer is alive.
    """
    v = _eval(tmp_path, readiness_path=tmp_path / "does_not_exist.json")
    assert not v.ok
    assert "absent" in v.reason
    assert v.checks["producer_liveness_verified"] is False


def test_unconfigured_readiness_path_blocks(tmp_path):
    """Not passing a path at all must not be a way around the requirement."""
    v = _eval(tmp_path, readiness_path=None)
    assert not v.ok
    assert "required" in v.reason


def test_corrupt_readiness_artifact_blocks(tmp_path):
    """A half-written document is the failure mode the publisher's temp+rename exists to
    prevent. If one is ever observed anyway, it must halt rather than be skipped."""
    p = tmp_path / "_factor_readiness.json"
    p.write_text('{"overall_readiness": "PA', encoding="utf-8")
    v = _eval(tmp_path, readiness_path=p)
    assert not v.ok and "readiness artifact unreadable" in v.reason


def test_future_dated_readiness_verdict_blocks(tmp_path):
    """The only way this check could fail OPEN: a verdict stamped ahead of the clock
    never ages out, so it would be permanent permission to dispatch."""
    v = _eval(tmp_path, readiness_path=_ready(tmp_path, age_h=-72))
    assert not v.ok and "FUTURE" in v.reason


def test_readiness_required_is_the_default(tmp_path):
    """Pinned deliberately. The requirement is the control; a default of False would let
    a caller that simply forgot the flag reintroduce the tolerated-absence behaviour."""
    import inspect

    sig = inspect.signature(evaluate_factor_readiness)
    assert sig.parameters["readiness_required"].default is True


def test_optional_mode_exists_only_as_an_explicit_opt_out(tmp_path):
    """Documents what the escape hatch does, so nobody has to guess. Production never
    passes it — ``test_engine_never_makes_the_readiness_artifact_optional`` proves that."""
    v = _eval(
        tmp_path,
        readiness_path=tmp_path / "does_not_exist.json",
        readiness_required=False,
    )
    assert v.ok
    assert v.checks["producer_liveness_verified"] is False
    assert "NOT verified" in v.reason


def test_evaluate_never_raises(tmp_path):
    """A gate that throws inside the dispatch path would be worse than one that
    blocks. Every failure must come back as a verdict."""
    v = evaluate_factor_readiness(store_path=None, sealed_path=None, now=NOW)  # type: ignore[arg-type]
    assert not v.ok


# ------------------------------------------- engine wiring: never entered


class _FactorStrategy:
    """A factor-consuming strategy. Records whether it was ever entered."""

    def __init__(self) -> None:
        self.entered = False

    async def on_bar(self, *_a, **_k):  # pragma: no cover - must never run
        self.entered = True
        raise AssertionError("strategy function was ENTERED despite readiness FAIL")

    def decide(self):  # noqa: D401 - source is what the classifier reads
        return self.ctx.factors.momentum_scores()  # type: ignore[attr-defined]


class _PlainStrategy:
    """Range Trader shape. This docstring deliberately mentions ctx.factors — a
    substring check would wrongly gate it; AST parsing must not be fooled."""

    def __init__(self) -> None:
        self.entered = False

    def decide(self):
        return None


def _running(instance):
    from app.strategies.engine import RunningStrategy

    return RunningStrategy(
        strategy_id=7,
        instance=instance,
        job_id=None,
        run_id=1,
        symbols=["AAA"],
        timeframe="1Day",
        schedule="24 10 * * mon",
    )


def test_factor_consuming_detection_splits_correctly():
    """Range Trader must not be blocked by factor staleness — it does not rank on
    factor data, so gating it would stop a working strategy for no reason.

    _PlainStrategy mentions ctx.factors in its DOCSTRING: detection reads the AST,
    so prose about factors must not classify a strategy as using them."""
    from app.strategies.factor_classification import requires_factor_readiness

    # Called on the shared function rather than through an unbound engine method with a
    # dummy `self`: classification is no longer engine-private, because ActivationService
    # needs the same answer at the PENDING_LIVE -> LIVE completion the engine never sees.
    assert requires_factor_readiness(_FactorStrategy) is True
    assert requires_factor_readiness(_PlainStrategy) is False


def test_unclassifiable_strategy_is_not_gated():
    """Deliberately NOT gated. Blocking everything we cannot classify would turn a
    diagnostic gap into a full trading halt — worse than the failure this prevents.
    The real templates are pinned by the test below, so nothing silently escapes."""
    from app.strategies.factor_classification import requires_factor_readiness

    # __module__ must point nowhere, or the fallback legitimately reads this test
    # file — which DOES use .factors — and classifies it as factor-consuming.
    #
    # This class also declares NOTHING, which is the other half of the condition: an
    # undeclared AND uninspectable strategy is the only population still handled this way.
    # Every shipped template now declares requires_factor_readiness, so no factor book can
    # reach this branch — which is what made 2026-08-10 possible.
    cls = type("Dynamic", (), {"__module__": "no.such.module.anywhere"})
    assert requires_factor_readiness(cls) is False


def test_all_real_templates_classify_correctly():
    """The guarantee that makes the fallback safe: every shipped template is checked
    against its actual file. A new factor-consuming template that forgets to be
    gated fails here."""
    import ast

    root = Path(__file__).resolve().parents[2] / "strategies_user" / "templates"
    expected = {
        "combined_book": True,
        "combined_book_v13": True,
        "low_volatility": True,
        "momentum_daily": True,
        "momentum_portfolio": True,
        "sector_rotation": True,
        "range_trader": False,
        "range_trader_vwap": False,
    }
    seen = {}
    for f in root.glob("*.py"):
        if f.stem == "__init__":
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        seen[f.stem] = any(
            isinstance(n, ast.Attribute) and n.attr == "factors" for n in ast.walk(tree)
        )
    assert seen == expected, f"template factor-classification drifted: {seen}"


@pytest.mark.asyncio
async def test_dispatch_blocked_and_strategy_never_entered(tmp_path, monkeypatch):
    """The terminal criterion: readiness FAIL -> strategy function NOT entered.

    Not 'the orders were rejected'. Not 'an alert fired'. The decision code must
    never run, so no proposal, no broker call and no status mutation can occur.
    """
    from app.strategies import engine as eng

    stale = _store(tmp_path, date(2026, 7, 31))
    monkeypatch.setattr(eng, "resolve_store_path", lambda *a, **k: stale)

    inst = _FactorStrategy()
    running = _running(inst)
    self_ = type(
        "E",
        (),
        {
            "_is_factor_consuming": eng.StrategyEngine._is_factor_consuming,
            # The gate delegates through these two now: classification moved to the
            # shared app.strategies.factor_classification (so ActivationService cannot
            # carry a second copy), and the verdict is evaluated once for both the
            # dispatch gate and the activation interlock.
            "_classify_factor_consuming": eng.StrategyEngine._classify_factor_consuming,
            "_factor_readiness_verdict": eng.StrategyEngine._factor_readiness_verdict,
            "_sealed_universe_path": eng.StrategyEngine._sealed_universe_path,
            "_factor_readiness_path": eng.StrategyEngine._factor_readiness_path,
        },
    )()

    ok = await eng.StrategyEngine._factor_readiness_ok(self_, running)
    assert ok is False, "stale factor data must block dispatch"
    assert inst.entered is False, "strategy function must never have been entered"


@pytest.mark.asyncio
async def test_non_factor_strategy_is_unaffected(tmp_path, monkeypatch):
    from app.strategies import engine as eng

    monkeypatch.setattr(eng, "resolve_store_path", lambda *a, **k: tmp_path / "absent.duckdb")
    self_ = type(
        "E",
        (),
        {
            "_is_factor_consuming": eng.StrategyEngine._is_factor_consuming,
            # The gate delegates through these two now: classification moved to the
            # shared app.strategies.factor_classification (so ActivationService cannot
            # carry a second copy), and the verdict is evaluated once for both the
            # dispatch gate and the activation interlock.
            "_classify_factor_consuming": eng.StrategyEngine._classify_factor_consuming,
            "_factor_readiness_verdict": eng.StrategyEngine._factor_readiness_verdict,
            "_sealed_universe_path": eng.StrategyEngine._sealed_universe_path,
            "_factor_readiness_path": eng.StrategyEngine._factor_readiness_path,
        },
    )()
    ok = await eng.StrategyEngine._factor_readiness_ok(self_, _running(_PlainStrategy()))
    assert ok is True, "a non-factor strategy must not be blocked by factor staleness"


def _engine_self():
    from app.strategies import engine as eng

    return type(
        "E",
        (),
        {
            "_is_factor_consuming": eng.StrategyEngine._is_factor_consuming,
            # The gate delegates through these two now: classification moved to the
            # shared app.strategies.factor_classification (so ActivationService cannot
            # carry a second copy), and the verdict is evaluated once for both the
            # dispatch gate and the activation interlock.
            "_classify_factor_consuming": eng.StrategyEngine._classify_factor_consuming,
            "_factor_readiness_verdict": eng.StrategyEngine._factor_readiness_verdict,
            "_sealed_universe_path": eng.StrategyEngine._sealed_universe_path,
            "_factor_readiness_path": eng.StrategyEngine._factor_readiness_path,
        },
    )()


def _live_data_dir(tmp: Path, *, readiness: str | None = "PASS"):
    """A data volume as the box has it: current store, current seal, and — unless the
    caller is testing its absence — a published readiness verdict at the exact basenames
    the engine derives. Anchored on the real clock because the engine calls the gate
    without a pinned ``now``.

    Returns a ``resolve_store_path`` replacement rather than a path: the gate calls that
    function once per artifact it locates, so a fixture that rebuilt the store on each
    call would fail on the second CREATE TABLE.
    """
    today = datetime.now(UTC).date()
    store = _store(tmp, today, name="factor_data.duckdb")
    (tmp / "_factor_refresh_universe_sealed.json").write_text(
        json.dumps({"as_of": today.isoformat(), "counts": {"total": 510}}), encoding="utf-8"
    )
    if readiness is not None:
        stamp = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        (tmp / "_factor_readiness.json").write_text(
            json.dumps({"overall_readiness": readiness, "evaluated_at_utc": stamp}),
            encoding="utf-8",
        )
    return lambda *a, **k: store


@pytest.mark.asyncio
async def test_engine_dispatches_when_everything_is_current(tmp_path, monkeypatch):
    """The gate must not be a permanent halt. With a current store, a current seal and a
    published PASS, a factor book is allowed to run — otherwise 'fail closed' would just
    mean 'closed', and the first green Monday would look like a regression."""
    from app.strategies import engine as eng

    monkeypatch.setattr(eng, "resolve_store_path", _live_data_dir(tmp_path))
    ok = await eng.StrategyEngine._factor_readiness_ok(_engine_self(), _running(_FactorStrategy()))
    assert ok is True


@pytest.mark.asyncio
async def test_engine_blocks_when_only_the_readiness_artifact_is_missing(tmp_path, monkeypatch):
    """The terminal criterion for the half that was still open on 2026-08-06.

    Store current, seal current, data beyond reproach — and the producer's liveness
    unproven because nothing published a verdict. This is the exact shape of the
    2026-08-03 window (producer dead, data still clean), and it must not dispatch.
    """
    from app.strategies import engine as eng

    monkeypatch.setattr(eng, "resolve_store_path", _live_data_dir(tmp_path, readiness=None))
    inst = _FactorStrategy()
    ok = await eng.StrategyEngine._factor_readiness_ok(_engine_self(), _running(inst))
    assert ok is False
    assert inst.entered is False


@pytest.mark.asyncio
async def test_engine_blocks_on_a_published_fail_verdict(tmp_path, monkeypatch):
    from app.strategies import engine as eng

    monkeypatch.setattr(eng, "resolve_store_path", _live_data_dir(tmp_path, readiness="FAIL"))
    inst = _FactorStrategy()
    ok = await eng.StrategyEngine._factor_readiness_ok(_engine_self(), _running(inst))
    assert ok is False
    assert inst.entered is False


def test_engine_never_makes_the_readiness_artifact_optional():
    """``readiness_required`` defaults to True, and the dispatch path must never pass it
    at all — a call site that sets it False would silently unarm the producer-liveness
    veto while every other check kept passing, which is precisely the failure class this
    interlock exists to remove."""
    src = Path(eng_file()).read_text(encoding="utf-8")
    assert "readiness_required" not in src, (
        "the dispatch path must not parameterise the readiness requirement"
    )
    assert "readiness_path=self._factor_readiness_path()" in src


#: Every dispatch site that must consult the readiness gate, by ``dispatch_source`` label.
#:
#: ⚠ This said THREE until 2026-08-27, and the docstring below asserted "three dispatch paths
#: exist" as a statement of fact. There were five. ``_fire_all_event_strategies`` — the
#: fallback tick for event-scheduled strategies — called the same ``on_bar`` that computes the
#: book, and ``_on_signal_event`` could drive a rebalance. Neither was gated, and the hardcoded
#: count of 3 made the tree look complete.
#:
#: Both are gated now. They were found by ``test_every_execution_seam_is_gated``, which
#: enumerates seams from the AST rather than trusting a number — which is why that test, and
#: not this one, is the guard that keeps this list honest as the engine grows.
GATED_DISPATCH_SOURCES = ("bar_tick", "event_bar", "overlay", "signal", "event_fallback")


def test_gate_runs_at_every_dispatch_site():
    """A gate on only some dispatch paths is the 2026-07-13 mistake repeated — HALTED was
    enforced on the cron path while the event path kept firing."""
    src = Path(eng_file()).read_text(encoding="utf-8")
    for source in GATED_DISPATCH_SOURCES:
        assert f'dispatch_source="{source}"' in src, f"{source} dispatch site is ungated"
    # Derived from the tuple above rather than hardcoded: adding a site now means NAMING it,
    # not bumping an integer. An integer is precisely what concealed the two missing seams.
    assert src.count("_factor_readiness_ok(running, dispatch_source=") == len(
        GATED_DISPATCH_SOURCES
    )


def eng_file() -> str:
    from app.strategies import engine

    return engine.__file__


# ------------------------------- both frontiers are required, not just SEP


def _store_missing_lpd(tmp: Path, sep_max: date) -> Path:
    """SEP present, tickers table present but empty -> no lastpricedate frontier."""
    duckdb = pytest.importorskip("duckdb")
    p = tmp / "no_lpd.duckdb"
    con = duckdb.connect(str(p))
    con.execute("CREATE TABLE sep (ticker VARCHAR, date DATE, close DOUBLE, volume DOUBLE)")
    con.execute("INSERT INTO sep VALUES ('AAA', ?, 1.0, 1.0)", [sep_max])
    con.execute("CREATE TABLE tickers (ticker VARCHAR, lastpricedate DATE)")
    con.close()
    return p


def _store_missing_sep(tmp: Path, lpd_max: date) -> Path:
    duckdb = pytest.importorskip("duckdb")
    p = tmp / "no_sep.duckdb"
    con = duckdb.connect(str(p))
    con.execute("CREATE TABLE sep (ticker VARCHAR, date DATE, close DOUBLE, volume DOUBLE)")
    con.execute("CREATE TABLE tickers (ticker VARCHAR, lastpricedate DATE)")
    con.execute("INSERT INTO tickers VALUES ('AAA', ?)", [lpd_max])
    con.close()
    return p


def test_fresh_sep_with_absent_lastpricedate_blocks(tmp_path):
    """dollar_volume_universe FILTERS on lastpricedate. A store that cannot report it
    cannot be shown to be current, and falling back to SEP alone would silently
    reduce the two-sided frontier to one side."""
    v = _eval(tmp_path, store_path=_store_missing_lpd(tmp_path, NOW.date()))
    assert not v.ok
    assert "no tickers.lastpricedate frontier" in v.reason


def test_absent_sep_with_present_lastpricedate_blocks(tmp_path):
    v = _eval(tmp_path, store_path=_store_missing_sep(tmp_path, NOW.date()))
    assert not v.ok
    assert "no SEP rows" in v.reason


def test_both_present_and_current_passes(tmp_path):
    v = _eval(tmp_path, store_path=_store(tmp_path, NOW.date(), NOW.date()))
    assert v.ok, v.reason


@pytest.mark.asyncio
async def test_absent_lastpricedate_leaves_strategy_never_entered(tmp_path, monkeypatch):
    """Terminal criterion for this failure mode too, not just staleness."""
    from app.strategies import engine as eng

    monkeypatch.setattr(
        eng, "resolve_store_path", lambda *a, **k: _store_missing_lpd(tmp_path, NOW.date())
    )
    inst = _FactorStrategy()
    self_ = type(
        "E",
        (),
        {
            "_is_factor_consuming": eng.StrategyEngine._is_factor_consuming,
            # The gate delegates through these two now: classification moved to the
            # shared app.strategies.factor_classification (so ActivationService cannot
            # carry a second copy), and the verdict is evaluated once for both the
            # dispatch gate and the activation interlock.
            "_classify_factor_consuming": eng.StrategyEngine._classify_factor_consuming,
            "_factor_readiness_verdict": eng.StrategyEngine._factor_readiness_verdict,
            "_sealed_universe_path": eng.StrategyEngine._sealed_universe_path,
            "_factor_readiness_path": eng.StrategyEngine._factor_readiness_path,
        },
    )()
    ok = await eng.StrategyEngine._factor_readiness_ok(self_, _running(inst))
    assert ok is False
    assert inst.entered is False
