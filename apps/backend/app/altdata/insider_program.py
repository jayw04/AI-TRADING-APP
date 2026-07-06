"""INSIDER-001 reproduction runner (plan §4) — the program as configuration + verdict-as-data.

This is the event-driven analogue of Factor Lab's ``run_program``: where a factor program rebalances
a cross-sectional quantile book, an *event* program runs the de-overlapped Event-Study Engine (§3)
over conviction hits and scores the result against a declared ``VerdictSpec`` (reused verbatim from
Factor Lab — same A/B/C/D verdict-as-data discipline, ADR 0026). It is the **independent reproduction**
on TradingWorkbench PIT data (owner OQ1): nothing is re-tuned (plan §1), and the verdict is *declared*,
not coded.

Wiring (the parts that legitimately depend on platform data, unlike the generic engine):
- prices: ``FactorDataStore.get_prices`` (survivorship-free, split/div-adjusted SEP);
- benchmark: an **equal-weight universe** daily-return index built from the same SEP spine — the
  "equal-weight small/mid-cap benchmark" H1 names — so the paired Sharpe-diff test asks the right
  question (does insider-conviction beat simply owning the small/mid-cap basket?).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.altdata.event_study import EventStudyResult, run_event_study
from app.altdata.signal import ConvictionHit
from app.factor_data.store import FactorDataStore
from app.research.factor_lab.spec import VerdictRule, VerdictSpec
from app.research.factor_lab.verdict import classify

MIN_EVENTS = 30  # below this the study has too few independent positions to verdict -> Inconclusive


# --- the verdict tree (data, not code) — faithful to the source's "factor tilt, disclosed" read ---

def _num(m: Mapping[str, Any], k: str) -> float | None:
    v = m.get(k)
    return float(v) if isinstance(v, (int, float)) and v == v else None  # NaN-safe


def _too_few(m: Mapping[str, Any]) -> bool:
    return (m.get("n_taken") or 0) < MIN_EVENTS


def _validated(m: Mapping[str, Any]) -> bool:
    lo, mer = _num(m, "h1_ci_low"), _num(m, "mean_event_return")
    return lo is not None and lo > 0 and mer is not None and mer > 0  # significant standalone edge


def _rejected(m: Mapping[str, Any]) -> bool:
    hi, mer, tr = _num(m, "h1_ci_high"), _num(m, "mean_event_return"), _num(m, "total_return")
    if hi is not None and hi < 0:
        return True  # the edge CI lies entirely below the benchmark
    return mer is not None and mer <= 0 and tr is not None and tr <= 0  # no economic return at all


def _diversifier(m: Mapping[str, Any]) -> bool:
    mer = _num(m, "mean_event_return")
    return mer is not None and mer > 0  # a real positive tilt that isn't a standalone edge


INSIDER_VERDICT = VerdictSpec(
    rules=(
        VerdictRule(_too_few, "D - Inconclusive",
                    "Too few independent positions to verdict; widen the window / universe."),
        VerdictRule(_validated, "A - Validated standalone edge",
                    "Significant risk-adjusted drift vs the equal-weight benchmark; size as a book."),
        VerdictRule(_rejected, "C - Rejected",
                    "No economic edge vs simply owning the small/mid-cap basket; do not promote."),
        VerdictRule(_diversifier, "B - Diversifier / factor tilt",
                    "A real positive tilt but not a standalone edge — size as a disclosed "
                    "diversifying sleeve, co-existing with the momentum book."),
    ),
    default_outcome="D - Inconclusive",
    default_action="Ambiguous evidence; collect more before deciding.",
)


@dataclass
class InsiderReproduction:
    study: EventStudyResult
    metrics: dict[str, Any]
    verdict: str
    action: str
    start: date
    end: date
    n_universe: int
    n_events: int


def make_price_fn(store: FactorDataStore):
    """Adapt the SEP store into the engine's ``price_fn`` (returns ``[(date, adj_close)]``)."""
    def price_fn(ticker: str, start: date, end: date) -> list[tuple[date, float]]:
        df = store.get_prices(ticker, start, end, adjusted=True)
        out: list[tuple[date, float]] = []
        for d, c in zip(df["date"].tolist(), df["close"].tolist(), strict=False):
            if c is None or c != c:  # skip NaN/None closes
                continue
            out.append((d.date() if hasattr(d, "date") else d, float(c)))
        return out
    return price_fn


def build_universe_benchmark(
    store: FactorDataStore, universe: Sequence[str], start: date, end: date,
) -> list[tuple[date, float]]:
    """An **equal-weight universe** index: each trading day's level compounds the cross-sectional
    mean daily return across every universe name with a quote that day (the H1 benchmark)."""
    sum_ret: dict[date, float] = {}
    cnt_ret: dict[date, int] = {}
    for tk in universe:
        df = store.get_prices(tk, start, end, adjusted=True)
        dates = [d.date() if hasattr(d, "date") else d for d in df["date"].tolist()]
        closes = [float(c) if c is not None and c == c else None for c in df["close"].tolist()]
        for (_d0, p0), (d1, p1) in zip(zip(dates, closes, strict=False),
                                      zip(dates[1:], closes[1:], strict=False), strict=False):
            if p0 and p1 and p0 > 0:
                sum_ret[d1] = sum_ret.get(d1, 0.0) + (p1 / p0 - 1.0)
                cnt_ret[d1] = cnt_ret.get(d1, 0) + 1
    level = 1.0
    curve: list[tuple[date, float]] = []
    for d in sorted(sum_ret):
        level *= 1.0 + sum_ret[d] / cnt_ret[d]
        curve.append((d, level))
    return curve


def run_insider_reproduction(
    hits: Sequence[ConvictionHit],
    store: FactorDataStore,
    *,
    universe: Sequence[str],
    start: date,
    end: date,
    hold_trading_days: int = 90,
    seed: int = 17,
    n_resamples: int = 2000,
) -> InsiderReproduction:
    """Run the de-overlapped event study over conviction ``hits`` against the equal-weight universe
    benchmark, assemble the flat metrics dict, and apply the declared verdict tree."""
    price_fn = make_price_fn(store)
    bench = build_universe_benchmark(store, universe, start, end)

    def benchmark_fn(s: date, e: date) -> list[tuple[date, float]]:
        return [(d, p) for d, p in bench if s <= d <= e]

    study = run_event_study(
        hits, price_fn, benchmark_fn=benchmark_fn,
        hold_trading_days=hold_trading_days, seed=seed, n_resamples=n_resamples,
    )
    metrics: dict[str, Any] = {
        "n_hits": study.n_hits,
        "n_taken": study.n_taken,
        "n_skipped_overlap": study.n_skipped_overlap,
        "n_no_data": study.n_no_data,
        "sharpe": round(study.sharpe, 3),
        "total_return": round(study.total_return, 4),
        "cagr": round(study.cagr, 4),
        "max_drawdown": round(study.max_drawdown, 4),
        "mean_event_return": round(study.mean_event_return, 4),
        "median_event_return": round(study.median_event_return, 4),
        "hit_rate": round(study.hit_rate, 4),
        "avg_hold_days": round(study.avg_hold_days, 1),
        "h1_diff": study.sharpe_diff_vs_benchmark,
        "h1_ci_low": study.sharpe_diff_ci_low,
        "h1_ci_high": study.sharpe_diff_ci_high,
        "h1_real": study.edge_excludes_zero,
        "p_value": study.sharpe_p_value,
    }
    outcome, action = classify(metrics, INSIDER_VERDICT)
    return InsiderReproduction(
        study=study, metrics=metrics, verdict=outcome, action=action,
        start=start, end=end, n_universe=len(universe), n_events=len(hits),
    )


def render_evidence(repro: InsiderReproduction) -> str:
    """Markdown evidence package for the §4 verdict (verdict-as-data, ADR 0026)."""
    m = repro.metrics
    return "\n".join([
        f"# INSIDER-001 §4 reproduction — {repro.verdict}",
        "",
        f"**Action:** {repro.action}",
        "",
        f"- **Window:** {repro.start} → {repro.end}; universe {repro.n_universe} names; "
        f"{repro.n_events} conviction hits → {m['n_taken']} taken "
        f"({m['n_skipped_overlap']} de-overlap skips, {m['n_no_data']} no-data).",
        f"- **Book vs equal-weight benchmark (H1):** Sharpe-diff {m['h1_diff']} "
        f"CI [{m['h1_ci_low']}, {m['h1_ci_high']}], bootstrap p {m['p_value']} "
        f"→ standalone edge: {'YES' if m['h1_real'] else 'no'}.",
        f"- **Book:** Sharpe {m['sharpe']}, total {m['total_return']:.1%}, "
        f"CAGR {m['cagr']:.1%}, maxDD {m['max_drawdown']:.1%}.",
        f"- **Per-event (H3):** mean {m['mean_event_return']:.2%}, median "
        f"{m['median_event_return']:.2%}, hit-rate {m['hit_rate']:.0%}, "
        f"avg hold {m['avg_hold_days']}d.",
        "",
        "_No parameter was re-tuned (plan §1 faithfulness rule); the verdict is declared, "
        "not coded (INSIDER_VERDICT)._",
    ])
