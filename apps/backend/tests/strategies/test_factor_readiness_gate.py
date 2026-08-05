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


def _eval(tmp: Path, **over):
    kw = {
        "store_path": over.pop("store_path", None) or _store(tmp, NOW.date()),
        "sealed_path": over.pop("sealed_path", None) or _sealed(tmp, NOW.date()),
        "readiness_path": over.pop("readiness_path", None),
        "now": NOW,
    }
    kw.update(over)
    return evaluate_factor_readiness(**kw)


# --------------------------------------------------------------- the happy path


def test_current_data_with_verified_generation_passes(tmp_path):
    v = _eval(tmp_path)
    assert v.ok, v.reason
    assert v.checks["lag_days"] == 0


def test_producer_liveness_is_not_claimed_when_unverifiable(tmp_path):
    """The systemd timer lives on the host, outside the container. With no readiness
    artifact the gate must not imply it checked producer liveness."""
    v = _eval(tmp_path)
    assert v.ok
    assert v.checks["producer_liveness_verified"] is False


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


# ------------------------------------------- optional producer-liveness verdict


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


def test_absent_readiness_artifact_does_not_block(tmp_path):
    """#615 does not yet persist a verdict. The gate must still run on what it can
    prove rather than blocking every dispatch until that lands."""
    v = _eval(tmp_path, readiness_path=tmp_path / "_factor_readiness.json")
    assert v.ok
    assert v.checks["producer_liveness_verified"] is False


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
    from app.strategies.engine import StrategyEngine

    det = StrategyEngine._is_factor_consuming
    assert det(object(), _running(_FactorStrategy())) is True
    assert det(object(), _running(_PlainStrategy())) is False


def test_unclassifiable_strategy_is_not_gated():
    """Deliberately NOT gated. Blocking everything we cannot classify would turn a
    diagnostic gap into a full trading halt — worse than the failure this prevents.
    The real templates are pinned by the test below, so nothing silently escapes."""
    from app.strategies.engine import StrategyEngine

    # __module__ must point nowhere, or the fallback legitimately reads this test
    # file — which DOES use .factors — and classifies it as factor-consuming.
    cls = type("Dynamic", (), {"__module__": "no.such.module.anywhere"})
    assert StrategyEngine._is_factor_consuming(object(), _running(cls())) is False


def test_all_real_templates_classify_correctly():
    """The guarantee that makes the classification fallback safe: every shipped
    template is checked against its actual file.

    Expectations are declared per template rather than as one exact dict, because
    the shipped set differs across releases (combined_book_v13 exists only on newer
    bases). An UNKNOWN template fails this test — that is the point: a new
    factor-consuming template cannot silently escape the gate by being unlisted.
    """
    import ast

    must_use = {
        "combined_book",
        "combined_book_v13",
        "low_volatility",
        "momentum_daily",
        "momentum_portfolio",
        "sector_rotation",
    }
    must_not_use = {"range_trader", "range_trader_vwap"}

    root = Path(__file__).resolve().parents[2] / "strategies_user" / "templates"
    seen: dict[str, bool] = {}
    for f in root.glob("*.py"):
        if f.stem == "__init__":
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        seen[f.stem] = any(
            isinstance(n, ast.Attribute) and n.attr == "factors" for n in ast.walk(tree)
        )

    unknown = set(seen) - must_use - must_not_use
    assert not unknown, f"unclassified template(s) {sorted(unknown)}: declare them explicitly"

    for name, uses in sorted(seen.items()):
        expected = name in must_use
        assert uses is expected, f"{name}: factor-classification drifted (got {uses})"

    # Strategies 7 and 8 are the books this gate exists to protect.
    for required in ("sector_rotation", "low_volatility"):
        assert seen.get(required) is True, f"{required} must be gated"


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
            "_sealed_universe_path": eng.StrategyEngine._sealed_universe_path,
            "_factor_readiness_path": eng.StrategyEngine._factor_readiness_path,
        },
    )()
    ok = await eng.StrategyEngine._factor_readiness_ok(self_, _running(_PlainStrategy()))
    assert ok is True, "a non-factor strategy must not be blocked by factor staleness"


def test_gate_runs_at_every_dispatch_site():
    """Three dispatch paths exist (cron bar tick, event bar, overlay). A gate on
    only some of them is the 2026-07-13 mistake repeated — HALTED was enforced on
    the cron path while the event path kept firing."""
    src = Path(eng_file()).read_text(encoding="utf-8")
    assert src.count("_factor_readiness_ok(running, dispatch_source=") == 3
    for source in ("bar_tick", "event_bar", "overlay"):
        assert f'dispatch_source="{source}"' in src, f"{source} dispatch site is ungated"


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
            "_sealed_universe_path": eng.StrategyEngine._sealed_universe_path,
            "_factor_readiness_path": eng.StrategyEngine._factor_readiness_path,
        },
    )()
    ok = await eng.StrategyEngine._factor_readiness_ok(self_, _running(inst))
    assert ok is False
    assert inst.entered is False
