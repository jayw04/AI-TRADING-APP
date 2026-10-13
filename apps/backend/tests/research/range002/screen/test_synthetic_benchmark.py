"""RANGE-002 synthetic ENGINEERING BENCHMARK of the seven-candidate screen pipeline.

NON-INFERENTIAL. Every bar here is a deterministic synthetic fixture designed to exercise one
behaviour (entry, stop, target, trailing, scale-out, gap, halt, half day, capital competition);
several scenarios are deliberately losing. A pass proves arithmetic and behaviour of the
screen kernel against hand-derived expectations ONLY. It says nothing about any market, any
strategy's performance, or any P0 decision. No spec value is invented: the synthetic payload of
``conftest.synth_payload`` is used as is, plus the seven-candidate ``exits.candidates`` list and
(S6 only) ``risk.per_trade_pct`` = 0.25.

Expectations were written BEFORE the first run, in
``docs/implementation/evidence/range_002/RANGE-002_Synthetic_Benchmark_Expectations_v0.1.md``
(and ``_benchmark_expected.py``, which imports nothing from the kernel).
SHA-256 of the expectations markdown file at the time of the first run:
    954014ab14e4fc51d150c135e10a76c5eb168c9fbc9d93c7d7e0a6079bd5936e
SHA-256 of ``_benchmark_expected.py`` at the time of the first run:
    f92decae92c1f75d58f5a6d5c27e32f96bc5e2b58b8da6fd5e999a3874c658c0

Each assertion failure is a FINDING: the expectation is re-derived from the rules to decide
whether the expectation or the code is wrong; expected values are never edited to fit the code.

``run_benchmark`` is reused by ``scripts/research/range002/synthetic_benchmark.py`` (print mode).
"""

from __future__ import annotations

import dataclasses
import time as clock
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.governance import results_guard
from app.research.range002.screen.causal import check_causal
from app.research.range002.screen.params import extract_params
from app.research.range002.screen.report import summarize, summarize_portfolio
from app.research.range002.screen.scheduler import (
    PortfolioRun,
    limits_from_draft,
    schedule_portfolio,
)
from app.research.range002.screen.selection import CandidateScore, select_candidate
from app.research.range002.screen.simulate import reconcile_funnel, run_screen
from app.research.range002.screen.stats import (
    BootstrapConfig,
    build_day_matrix,
    max_statistic_test,
    mean_interval,
)
from app.research.range002.screen.types import (
    TERMINAL_STATES,
    Bar,
    ScreenParams,
    ScreenRun,
    SessionBars,
    Trade,
)
from app.research.range002.spec.loader import parse_draft
from tests.research.range002.screen import _benchmark_expected as X
from tests.research.range002.screen.conftest import (
    TICK,
    make_capability,
    minutes_flat,
    mk,
    or_bars,
    session,
    synth_payload,
)
from tests.research.range002.spec._fixtures import SYNTH_MANIFEST_PATH, synthetic_minutes_root

LABEL = "NON-INFERENTIAL SYNTHETIC ENGINEERING BENCHMARK - arithmetic/behaviour only"
TOL = 1e-6
D = date
CAND_SPEC: list[dict[str, Any]] = [
    {"id": "TIME", "family": "time", "params": {}},
    {"id": "R2", "family": "fixed_r", "params": {"r_multiple": 2.0}},
    {"id": "R3", "family": "fixed_r", "params": {"r_multiple": 3.0}},
    {"id": "TRAIL1", "family": "trailing", "params": {"trail_r": 1.0}},
    {"id": "TRAIL15", "family": "trailing", "params": {"trail_r": 1.5}},
    {"id": "SCALE_EOD", "family": "scale_out", "params": {"remainder": "eod"}},
    {"id": "SCALE_TRAIL", "family": "scale_out", "params": {"remainder": "trail", "trail_r": 1.0}},
]
CUTS = [time(9, 45), time(10, 5), time(10, 30), time(12, 0), time(15, 54)]


# --------------------------------------------------------------------------- fixtures: bars
def _mins(s: str) -> int:
    hh, mm = (int(p) for p in s.split(":"))
    return hh * 60 + mm


def _hhmm(n: int) -> str:
    return f"{n // 60:02d}:{n % 60:02d}"


def flat(a: str, b: str, px: float) -> list[Bar]:
    return minutes_flat(a, b, px) if _mins(a) <= _mins(b) else []


def without(bars: list[Bar], *minutes: str) -> list[Bar]:
    drop = {time(int(m[:2]), int(m[3:])) for m in minutes}
    return [b for b in bars if b.start not in drop]


def minute_set(a: str, b: str) -> frozenset[time]:
    return frozenset(time(n // 60, n % 60) for n in range(_mins(a), _mins(b) + 1))


BREAK = mk("10:05", 10.09, 10.20, 10.08, 10.18)


def _sess(
    bars: list[Bar], sym: str, day: date, **kw: Any
) -> SessionBars:  # permaticker defaults to PERM-<sym>
    return session(bars, sym, day, **kw)


def build_s1() -> list[SessionBars]:
    pre = or_bars() + flat("10:00", "10:04", 10.05)
    aaa = (
        pre
        + [BREAK]
        + flat("10:06", "10:59", 10.15)
        + [mk("11:00", 10.15, 10.25, 10.15, 10.24)]
        + flat("11:01", "11:59", 10.24)
        + [mk("12:00", 10.24, 10.36, 10.24, 10.36)]
        + flat("12:01", "12:59", 10.36)
        + [mk("13:00", 10.36, 10.50, 10.36, 10.50)]
        + flat("13:01", "14:29", 10.50)
        + [mk("14:30", 10.50, 10.50, 10.30, 10.32)]
        + flat("14:31", "15:59", 10.32)
    )
    bbb = pre + [mk("10:05", 10.02, 10.03, 9.80, 9.85)] + flat("10:06", "15:59", 9.85)
    ccc = pre + [BREAK, mk("10:06", 10.18, 10.50, 10.18, 10.48)] + flat("10:07", "15:59", 10.48)
    return [
        _sess(aaa, "AAA", D(2026, 3, 2)),
        _sess(bbb, "BBB", D(2026, 3, 3)),
        _sess(ccc, "CCC", D(2026, 3, 4)),
    ]


def build_s2() -> list[SessionBars]:
    pre = or_bars() + flat("10:00", "10:04", 10.05)
    ddd = pre + [BREAK, mk("10:06", 10.15, 10.16, 9.95, 9.97)] + flat("10:07", "15:59", 9.97)
    eee = (
        pre
        + [BREAK]
        + flat("10:06", "10:29", 10.12)
        + [mk("10:30", 10.15, 10.25, 10.15, 10.24)]
        + flat("10:31", "11:59", 10.20)
        + [mk("12:00", 10.20, 10.20, 9.95, 9.98)]
        + flat("12:01", "15:59", 9.98)
    )
    return [_sess(ddd, "DDD", D(2026, 3, 5)), _sess(eee, "EEE", D(2026, 3, 6))]


def build_s3() -> list[SessionBars]:
    fff = (
        or_bars()
        + flat("10:00", "10:29", 10.05)
        + [mk("10:30", 10.20, 10.30, 10.19, 10.28)]
        + flat("10:31", "15:59", 10.28)
    )
    ggg = (
        or_bars()
        + flat("10:00", "10:04", 10.05)
        + [BREAK]
        + flat("10:06", "10:59", 10.15)
        + [mk("11:00", 9.80, 9.85, 9.70, 9.75)]
        + flat("11:01", "15:59", 9.75)
    )
    hhh = or_bars() + [mk("10:00", 10.20, 10.25, 10.19, 10.22)] + flat("10:01", "15:59", 10.22)
    return [
        _sess(fff, "FFF", D(2026, 3, 9)),
        _sess(ggg, "GGG", D(2026, 3, 10)),
        _sess(hhh, "HHH", D(2026, 3, 11)),
    ]


def build_s4() -> list[SessionBars]:
    pre = flat("10:00", "10:04", 10.05)
    day_bars = pre + [BREAK] + flat("10:06", "15:59", 10.30)
    iii = without(or_bars(), "09:40") + day_bars
    jjj = or_bars() + without(day_bars, "10:20")
    kkk = or_bars() + pre + [BREAK] + flat("10:06", "14:00", 10.30)
    lll = without(or_bars(), "09:40", "09:41") + day_bars
    mmm = (
        or_bars()
        + pre
        + [BREAK]
        + flat("10:06", "10:59", 10.15)
        + [mk("11:30", 9.70, 9.75, 9.65, 9.72)]
        + flat("11:31", "15:59", 9.72)
    )
    return [
        _sess(iii, "III", D(2026, 3, 12), gaps=frozenset({time(9, 40)})),
        _sess(jjj, "JJJ", D(2026, 3, 13), gaps=frozenset({time(10, 20)})),
        _sess(kkk, "KKK", D(2026, 3, 16), halts=minute_set("14:01", "15:59")),
        _sess(lll, "LLL", D(2026, 3, 17), gaps=frozenset({time(9, 40), time(9, 41)})),
        _sess(mmm, "MMM", D(2026, 3, 18), halts=minute_set("11:00", "11:29")),
    ]


def build_s5() -> list[SessionBars]:
    half = time(13, 0)
    nnn = or_bars() + flat("10:00", "10:04", 10.05) + [BREAK] + flat("10:06", "12:59", 10.30)
    ooo = (
        or_bars()
        + flat("10:00", "12:54", 10.05)
        + [mk("12:55", 10.09, 10.20, 10.08, 10.18)]
        + flat("12:56", "12:59", 10.18)
    )
    qqq = (
        or_bars()
        + flat("10:00", "12:55", 10.05)
        + [mk("12:56", 10.09, 10.20, 10.08, 10.18)]
        + flat("12:57", "12:59", 10.18)
    )
    return [
        _sess(nnn, "NNN", D(2026, 3, 19), close=half),
        _sess(ooo, "OOO", D(2026, 3, 20), close=half),
        _sess(qqq, "QQQ", D(2026, 3, 23), close=half),
    ]


def _s6_winner(entry: str) -> list[Bar]:
    return (
        or_bars(10.15, 10.00)
        + flat("10:00", _hhmm(_mins(entry) - 1), 10.05)
        + [mk(entry, 10.10, 10.17, 10.09, 10.15)]
        + flat(_hhmm(_mins(entry) + 1), "15:59", 10.20)
    )


def _s6_loser(entry: str, stop_at: str) -> list[Bar]:
    return (
        or_bars(10.15, 10.00)
        + flat("10:00", _hhmm(_mins(entry) - 1), 10.05)
        + [mk(entry, 10.10, 10.17, 10.09, 10.15)]
        + flat(_hhmm(_mins(entry) + 1), _hhmm(_mins(stop_at) - 1), 10.12)
        + [mk(stop_at, 10.12, 10.12, 9.95, 9.97)]
        + flat(_hhmm(_mins(stop_at) + 1), "15:59", 9.97)
    )


def build_s6() -> list[SessionBars]:
    p = X.S6_PERMA
    out: list[SessionBars] = []
    for sym in ("SYM1", "SYM2", "SYM3", "SYM4", "SYM5"):
        out.append(_sess(_s6_winner("10:05"), sym, D(2026, 3, 30), permaticker=p[sym]))
    out += [
        _sess(_s6_loser("10:05", "10:15"), "LOS1", D(2026, 3, 31), permaticker=p["LOS1"]),
        _sess(_s6_winner("10:10"), "WIN1", D(2026, 3, 31), permaticker=p["WIN1"]),
        _sess(_s6_winner("10:20"), "WIN2", D(2026, 3, 31), permaticker=p["WIN2"]),
        _sess(_s6_loser("10:05", "10:20"), "LOS2", D(2026, 4, 1), permaticker=p["LOS2"]),
        _sess(_s6_winner("10:20"), "WIN3", D(2026, 4, 1), permaticker=p["WIN3"]),
    ]
    return out


BUILDERS: dict[str, Callable[[], list[SessionBars]]] = {
    "S1": build_s1,
    "S2": build_s2,
    "S3": build_s3,
    "S4": build_s4,
    "S5": build_s5,
    "S6": build_s6,
}


# --------------------------------------------------------------------------- the pipeline
@dataclass
class ScenarioResult:
    run: ScreenRun
    sessions: list[SessionBars]
    summaries: dict[str, dict[str, Any]]
    reconciled: bool = True
    causal_problems: list[str] = field(default_factory=list)


@dataclass
class Bench:
    scenarios: dict[str, ScenarioResult]
    portfolio_default: dict[str, PortfolioRun]
    portfolio_relaxed: dict[str, PortfolioRun]
    portfolio_summary: dict[str, dict[str, Any]]
    matrix_observed: dict[str, float]
    interval_runs: tuple[Any, ...]
    max_test_runs: tuple[Any, ...]
    selection: Any
    params: ScreenParams
    timings: dict[str, float] = field(default_factory=dict)


def _timed(timings: dict[str, float], name: str) -> Callable[[float], None]:
    def stop(t0: float) -> None:
        timings[name] = timings.get(name, 0.0) + (clock.perf_counter() - t0)

    return stop


def run_benchmark(workdir: Path) -> Bench:
    """Run S1-S6 through the real guarded pipeline. Sets the same test seams the pytest autouse
    fixtures set (synthetic manifest, synthetic minutes root), so it also works standalone."""
    timings: dict[str, float] = {}
    t_total = clock.perf_counter()
    with ExitStack() as stack:
        saved = results_guard._MANIFEST_PATH
        results_guard._MANIFEST_PATH = SYNTH_MANIFEST_PATH
        stack.callback(setattr, results_guard, "_MANIFEST_PATH", saved)
        stack.enter_context(synthetic_minutes_root())
        return _run(workdir, timings, t_total)


def _run(workdir: Path, timings: dict[str, float], t_total: float) -> Bench:
    # -- stage: capability + typed params (two synthetic specs: main and S6)
    t0 = clock.perf_counter()
    main_payload = synth_payload(**{"exits__candidates": CAND_SPEC})
    s6_payload = synth_payload(**{"exits__candidates": CAND_SPEC, "risk__per_trade_pct": X.PCT_S6})
    d_main, d_s6 = workdir / "main", workdir / "s6"
    d_main.mkdir(parents=True, exist_ok=True)
    d_s6.mkdir(parents=True, exist_ok=True)
    cap_main, _ = make_capability(d_main, main_payload)
    cap_s6, _ = make_capability(d_s6, s6_payload)
    draft_main, draft_s6 = parse_draft(main_payload), parse_draft(s6_payload)
    p_main = extract_params(cap_main, draft_main)
    p_s6 = extract_params(cap_s6, draft_s6)
    _timed(timings, "1_capability_and_params")(t0)

    scenarios: dict[str, ScenarioResult] = {}
    for sc, builder in BUILDERS.items():
        cap, params, equity = (
            (cap_s6, p_s6, X.EQUITY_S6) if sc == "S6" else (cap_main, p_main, X.EQUITY_MAIN)
        )
        t0 = clock.perf_counter()
        sessions = builder()
        _timed(timings, "2_build_sessions")(t0)

        t0 = clock.perf_counter()
        run = run_screen(cap, params, sessions, TICK, equity)
        _timed(timings, "3_run_screen")(t0)

        t0 = clock.perf_counter()
        reconcile_funnel(cap, run.funnel)
        _timed(timings, "4_reconcile_funnel")(t0)

        t0 = clock.perf_counter()
        summaries = {c: summarize(cap, run.trades[c]) for c in run.trades}
        _timed(timings, "5_summarize")(t0)

        t0 = clock.perf_counter()
        problems: list[str] = []
        for s in sessions:
            problems += check_causal(cap, params, s, TICK, equity, CUTS)
        _timed(timings, "6_causality_check")(t0)
        scenarios[sc] = ScenarioResult(run, sessions, summaries, True, problems)

    # -- stage: portfolio scheduler on S6 (default limits, and a gross-relaxed harness variant)
    t0 = clock.perf_counter()
    limits = limits_from_draft(cap_s6, draft_s6, X.EQUITY_S6)
    relaxed = dataclasses.replace(limits, gross_cap=1.0)
    s6 = scenarios["S6"].run
    pf_default = {
        c: schedule_portfolio(cap_s6, s6.trades[c], limits, tie_break="PERMATICKER_ASC")
        for c in s6.trades
    }
    pf_relaxed = {
        c: schedule_portfolio(cap_s6, s6.trades[c], relaxed, tie_break="PERMATICKER_ASC")
        for c in s6.trades
    }
    pf_summary = {c: summarize_portfolio(cap_s6, pf_default[c]) for c in pf_default}
    _timed(timings, "7_portfolio_schedule_and_summary")(t0)

    # -- stage: pooled day-cluster bootstrap + selection (synthetic payload values only)
    t0 = clock.perf_counter()
    pooled: dict[str, list[Trade]] = {c["id"]: [] for c in CAND_SPEC}
    days: set[date] = set()
    for res in scenarios.values():
        days |= {s.day for s in res.sessions}
        for cid, trs in res.run.trades.items():
            pooled[cid] += list(trs)
    bs = draft_main.stats.bootstrap
    assert bs.block_len is not None and bs.reps is not None and bs.seed is not None
    assert bs.confidence_level is not None and draft_main.stats.alpha_one_sided is not None
    cfg = BootstrapConfig(float(bs.block_len), int(bs.reps), int(bs.seed))
    matrix = build_day_matrix(cap_main, pooled, sorted(days))
    ivs = tuple(
        mean_interval(cap_main, matrix, "TRAIL1", float(bs.confidence_level), cfg) for _ in (0, 1)
    )
    tests = tuple(
        max_statistic_test(cap_main, matrix, float(draft_main.stats.alpha_one_sided), cfg)
        for _ in (0, 1)
    )
    obs = {
        c: float(matrix.net_r[:, k].sum() / matrix.trades[:, k].sum())
        for k, c in enumerate(matrix.candidates)
    }
    _timed(timings, "8_bootstrap")(t0)

    t0 = clock.perf_counter()
    fam_rank = {f: i for i, f in enumerate(draft_main.exits.complexity_order or ())}
    order = [
        c["id"] for c in sorted(CAND_SPEC, key=lambda c: fam_rank[c["family"]])
    ]  # stable: family order, then listed order
    scores = []
    for c in order:
        vals = [t.net_r_base for t in pooled[c]]
        wins = sum(v for v in vals if v > 0)
        loss = -sum(v for v in vals if v < 0)
        scores.append(
            CandidateScore(c, sum(vals) / len(vals), len(vals), wins / loss if loss else None)
        )
    el = draft_main.exits.selection.eligibility
    assert el.min_trades is not None and el.min_pf is not None
    assert draft_main.exits.selection.tie_tolerance_r is not None
    sel = select_candidate(
        cap_main,
        scores,
        order,
        min_trades=int(el.min_trades),
        min_pf=float(el.min_pf),
        delta=float(draft_main.exits.selection.tie_tolerance_r),
    )
    _timed(timings, "9_selection")(t0)
    timings["total"] = clock.perf_counter() - t_total
    return Bench(
        scenarios, pf_default, pf_relaxed, pf_summary, obs, ivs, tests, sel, p_main, timings
    )


# --------------------------------------------------------------------------- the assertions
@pytest.fixture(scope="module")
def bench(tmp_path_factory: pytest.TempPathFactory) -> Bench:
    return run_benchmark(tmp_path_factory.mktemp("synthetic_benchmark"))


def _t(res: ScenarioResult, cand: str) -> dict[tuple[str, date], Trade]:
    return {(t.symbol, t.day): t for t in res.run.trades[cand]}


def _tm(s: str) -> time:
    hh, mm = (int(p) for p in s.split(":"))
    return time(hh, mm)


SCEN = list(X.EXPECTED)


@pytest.mark.parametrize("scenario", SCEN)
def test_funnel_counts_and_reconciliation(bench: Bench, scenario: str) -> None:
    n, states, exits = X.expected_funnel(scenario)
    f = bench.scenarios[scenario].run.funnel
    assert f.eligible == n
    for st in TERMINAL_STATES:
        assert f.states[st] == states.get(st, 0), (scenario, st)
    assert sum(f.states.values()) == f.eligible  # nothing dropped
    for c in X.CANDS:
        assert f.exits[c] == exits[c], (scenario, c)
    assert not bench.scenarios[scenario].causal_problems  # decisions never saw the future


@pytest.mark.parametrize("scenario", SCEN)
def test_session_states_match(bench: Bench, scenario: str) -> None:
    run = bench.scenarios[scenario].run
    entered = {(t.symbol, t.day) for t in run.trades["TIME"]}
    exp_entered = {(s.symbol, s.day) for s in X.EXPECTED[scenario] if s.state == "ENTERED"}
    assert entered == exp_entered


@pytest.mark.parametrize("cand", X.CANDS)
@pytest.mark.parametrize("scenario", SCEN)
def test_trades_match_hand_derivation(bench: Bench, scenario: str, cand: str) -> None:
    res = bench.scenarios[scenario]
    got = _t(res, cand)
    exp = X.expected_trades(scenario, cand)
    assert set(got) == {(s.symbol, s.day) for s, _ in exp}
    for s, x in exp:
        t = got[(s.symbol, s.day)]
        tag = (scenario, cand, s.symbol)
        assert t.entry_time == _tm(x.entry_time), tag
        assert t.entry_price == pytest.approx(x.entry, abs=1e-9), tag
        assert t.r_fill == pytest.approx(x.r_fill, abs=1e-9), tag
        assert t.r_pre == pytest.approx(x.r_pre, abs=1e-9), tag
        assert t.exit_time == _tm(x.exit_time), tag
        assert t.exit_reason == x.reason, tag
        assert t.exit_price == pytest.approx(x.legs[-1][1], abs=1e-9), tag
        assert t.scaled_out == x.scaled, tag
        assert t.gapped_entry == x.gapped, tag
        assert t.exit_unexecutable == x.unexec, tag
        assert t.exit_after_unavailable == x.after_unavail, tag
        assert t.path_ambiguous == x.ambiguous, tag
        assert t.gross_r == pytest.approx(x.gross, abs=TOL), tag
        assert t.net_r_base == pytest.approx(x.net_base, abs=TOL), tag
        assert t.net_r_stress == pytest.approx(x.net_stress, abs=TOL), tag
        # stress is exactly three times the base cost (15 bps vs 5 bps, same notional)
        assert (t.gross_r - t.net_r_stress) == pytest.approx(
            3 * (t.gross_r - t.net_r_base), abs=1e-9
        ), tag
        assert t.qty == x.qty, tag


@pytest.mark.parametrize("cand", X.CANDS)
@pytest.mark.parametrize("scenario", SCEN)
def test_report_totals(bench: Bench, scenario: str, cand: str) -> None:
    rep = bench.scenarios[scenario].summaries[cand]
    exp = X.expected_trades(scenario, cand)
    assert rep["trades"] == len(exp)
    assert rep["base"]["total_net_r"] == pytest.approx(X.total_net(scenario, cand), abs=TOL)
    assert rep["stress"]["total_net_r"] == pytest.approx(
        X.total_net(scenario, cand, stress=True), abs=TOL
    )
    assert rep["unexecutable_exits"] == sum(1 for _, x in exp if x.unexec)
    assert rep["gapped_entries"] == sum(1 for _, x in exp if x.gapped)
    assert rep["basis"] == "signal"
    assert rep["inferential_status"] == "NON_INFERENTIAL_DESCRIPTIVE"
    assert rep["execution_realism"] == "NOT_MODELLED"


def test_s1_short_side_is_not_implemented(bench: Bench) -> None:
    """Scenario premise correction: the kernel is long-only, so a downside break is no trade."""
    run = bench.scenarios["S1"].run
    assert run.funnel.states["NO_BREAKOUT"] == 1
    assert all(t.symbol != "BBB" for t in run.trades["TIME"])


def test_s3_gap_entry_uses_fill_risk_not_pre_risk(bench: Bench) -> None:
    t = _t(bench.scenarios["S3"], "TIME")[("FFF", D(2026, 3, 9))]
    assert t.r_pre == pytest.approx(0.11, abs=1e-9)
    assert t.r_fill == pytest.approx(0.20, abs=1e-9)
    assert t.r_fill > t.r_pre and t.gapped_entry and t.entry_price > t.trigger


# --- S6 portfolio ---------------------------------------------------------------------------
def _ids(run: PortfolioRun) -> list[tuple[str, str]]:
    return [(t.symbol, t.day.isoformat()) for t in run.accepted]


@pytest.mark.parametrize("cand", X.CANDS)
def test_s6_portfolio_default_limits(bench: Bench, cand: str) -> None:
    run = bench.portfolio_default[cand]
    assert run.signal_trades == 10
    assert _ids(run) == X.S6_DEFAULT_ACCEPTED
    assert run.rejected == X.S6_DEFAULT_REJECTED
    assert sum(t.net_r_base for t in run.accepted) == pytest.approx(-1.939625, abs=TOL)
    rep = bench.portfolio_summary[cand]
    assert rep["basis"] == "portfolio" and rep["signal_trades"] == 10
    assert rep["accepted_trades"] == 3
    assert rep["rejected_by_reason"] == dict(sorted(X.S6_DEFAULT_REJECTED.items()))
    assert rep["base"]["total_net_r"] == pytest.approx(-1.939625, abs=TOL)
    assert rep["stress"]["total_net_r"] == pytest.approx(-2.318875, abs=TOL)


@pytest.mark.parametrize("cand", X.CANDS)
def test_s6_portfolio_concurrency_variant(bench: Bench, cand: str) -> None:
    run = bench.portfolio_relaxed[cand]
    assert _ids(run) == X.S6_RELAXED_ACCEPTED
    assert run.rejected == X.S6_RELAXED_REJECTED
    assert sum(t.net_r_base for t in run.accepted) == pytest.approx(-1.3805, abs=TOL)
    assert sum(t.net_r_stress for t in run.accepted) == pytest.approx(-2.1415, abs=TOL)


def test_s6_signal_level_differs_from_portfolio_and_is_labelled(bench: Bench) -> None:
    sig = bench.scenarios["S6"].summaries["TIME"]
    assert sig["basis"] == "signal" and sig["trades"] == 10
    assert sig["base"]["total_net_r"] == pytest.approx(-0.635, abs=TOL)
    assert sig["base"]["profit_factor"] == pytest.approx(1.491 / 2.126, abs=TOL)
    assert sig["base"]["win_rate"] == pytest.approx(0.8)
    assert sig["max_drawdown_r_daily"] == pytest.approx(1.566875, abs=TOL)
    assert sig["net_r_after_removing_top5"] == pytest.approx(-1.566875, abs=TOL)
    assert sig["best_day_share_of_net"] is None  # total < 0: undefined, not a number
    port = bench.portfolio_summary["TIME"]
    assert port["base"]["total_net_r"] != pytest.approx(sig["base"]["total_net_r"], abs=0.1)


# --- pooled bootstrap + selection (determinism and hand-pooled means) ------------------------
def test_pooled_means_and_bootstrap_determinism(bench: Bench) -> None:
    for c in X.CANDS:
        v = X.pooled(c)
        assert bench.matrix_observed[c] == pytest.approx(sum(v) / len(v), abs=TOL)
    a, b = bench.interval_runs
    assert a == b and a.observed_mean == pytest.approx(0.020488, abs=1e-5)
    t1, t2 = bench.max_test_runs
    assert t1 == t2
    assert t1.observed_argmax == "TRAIL1"
    assert t1.observed_max == pytest.approx(0.020488, abs=1e-5)


def test_selection_expected_no_eligible_candidate(bench: Bench) -> None:
    sel = bench.selection
    assert sel.winner is None and sel.reason == "NO_ELIGIBLE_CANDIDATE"
    assert sel.ineligible == dict.fromkeys(X.CANDS, "PF_BELOW_FLOOR")
