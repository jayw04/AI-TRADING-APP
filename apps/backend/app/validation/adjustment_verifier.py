"""Corporate-action adjustment verifier (R5b) — prove the adjusted series reflects the declared actions.

The frozen computation reads `closeadj`. If a split or distribution is not reflected in that series the
way the declared action says it should be, the momentum window is computed over a price path that never
existed. R5a therefore refuses a session whose corporate-action reflection is unproven; this module is
what can prove it.

## The relationship being verified (already the platform's documented formulation)

`app/factor_data/total_return.py`: `r_t = s_t · (c_t + d_t) / c_{t−1} − 1`, so for each ex-date

    expected_ratio = split_multiplier · (raw_close_t + cash_per_share) / raw_close_{t−1}
    observed_ratio = closeadj_t / closeadj_{t−1}

and a correctly adjusted series satisfies `|observed − expected| ≤ abs_tol + rel_tol · |expected|`.
Cash distributions, splits, reverse splits and same-day split-plus-dividend all compose through it.

## Both directions are checked, and the second is the load-bearing one

  (a) DECLARED → SERIES: every relevant declared action must be reflected within tolerance.
  (b) SERIES → DECLARED: every adjustment EVENT visible in the data — a session where the adjusted
      one-day ratio departs from the raw one-day ratio by more than the price-quantum noise — must be
      explained by a declared action.

Direction (b) exists because the absence of action rows is not evidence that no action occurred. The
governed store today holds **zero** rows in `actions` while `closeadj` differs from `close` on ~48% of
its 39M rows: without (b), "no actions in the window" would read as "nothing to prove" and the session
would pass vacuously. With (b), an unexplained adjustment is NOT_PROVEN_INSUFFICIENT_DATA.

## What this can and cannot prove

It proves CONSISTENCY between `closeadj`, the raw closes and the declared action rows. It does NOT
prove that the declared cash amount, ratio, ex-date or classification is itself correct — that is a
property of the source, not of the arithmetic. The evidence therefore reports two separate facts:

    adjustment_series_consistent_with_declared_actions   (what the arithmetic shows)
    declared_action_source_authoritative                 (whether the source is frozen and identified)

`proven` requires BOTH. A source that has not been explicitly declared authoritative can never yield a
PROVEN verdict, however clean the arithmetic looks.

## Tolerance is derived from the stored precision and a MEASURED noise/signal separation

Prices are stored to four decimals, so the ratio noise scales with 1/price and a one-day comparison
rounds four of them (raw and adjusted, this session and the previous). The band is therefore
`safety × quantum × Σ(1/price)`, with a fixed relative floor.

The safety factor is not a round number chosen so the data passes. Measured on the governed store over
2025-07-01..2026-06-15 (1,366,300 pairs, 6,211 names), the flagged-event count as a function of the
factor is 150,115 at 1x → 7,362 at 5x → 7,302 at 20x: a sharp knee and then a plateau, i.e. two
separated populations (vendor rounding vs real adjustment events). 5x sits inside that plateau, so the
band separates the populations rather than being tuned toward a desired pass rate. 24 events per name
per year (the 1x figure) is not a corporate-action calendar; ~1.2 is.

Every check records the absolute and relative residual, both tolerances, and the precision basis.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

from app.validation.forward_window import IntegrityStop

# Sharadar action labels (lower-cased) grouped by what the arithmetic can verify.
_CASH_LABELS = frozenset({"dividend", "cash dividend", "dividends", "distribution"})
_SPLIT_LABELS = frozenset({"split", "stocksplit", "stock split", "reverse split", "reversesplit"})
_SPINOFF_LABELS = frozenset({"spinoff", "spin-off", "stockdividend", "stock dividend"})
_MERGER_LABELS = frozenset({"merger", "acquisition", "conversion", "exchange"})
_SYMBOL_LABELS = frozenset({"tickerchange", "ticker change", "namechange", "name change",
                            "symbolchange", "listed", "delisted", "relisted"})

# The stored price quantum (four decimals across `sep`) and the resulting ratio-noise model.
#
# A one-day comparison rounds FOUR prices — raw and adjusted, on this session and the previous one —
# and each contributes a relative error of about `quantum / price`, so the band is the SUM of the four
# reciprocals rather than a single term. `NOISE_SAFETY_FACTOR` is placed inside a measured plateau:
# over 2025-07-01..2026-06-15 on the governed store (1,366,300 pairs / 6,211 names) the number of
# flagged events is 7,362 at 5x and 7,302 at 20x — i.e. rounding noise and real adjustment events are
# two separated populations, and the factor sits in the gap between them rather than being tuned to a
# desired pass rate. (At 1x the same measurement flags 150,115 events, 24 per name per year, which no
# corporate-action calendar could produce.)
PRICE_QUANTUM = 1e-4
NOISE_SAFETY_FACTOR = 5.0
RELATIVE_FLOOR = 1e-6             # floating-point/representation floor
ABSOLUTE_TOLERANCE = 0.0          # the model is relative; kept explicit and recorded


class AdjustmentVerdict(StrEnum):
    PROVEN = "PROVEN"
    NO_RELEVANT_ACTIONS = "NO_RELEVANT_ACTIONS"
    NOT_PROVEN_INSUFFICIENT_DATA = "NOT_PROVEN_INSUFFICIENT_DATA"
    NOT_PROVEN_UNSUPPORTED_ACTION = "NOT_PROVEN_UNSUPPORTED_ACTION"
    INTEGRITY_STOP_CONFLICT = "INTEGRITY_STOP_CONFLICT"


class ActionClass(StrEnum):
    CASH_DIVIDEND = "CASH_DIVIDEND"
    SPLIT = "SPLIT"
    SPLIT_AND_CASH = "SPLIT_AND_CASH"
    SPINOFF_DISTRIBUTION = "SPINOFF_DISTRIBUTION"
    MERGER_CONVERSION = "MERGER_CONVERSION"
    SYMBOL_TRANSITION = "SYMBOL_TRANSITION"
    UNSUPPORTED = "UNSUPPORTED"


class AdjustmentVerificationError(IntegrityStop):
    """The store could not be interrogated. Fails closed — an unverifiable window is never proven."""


@dataclass(frozen=True)
class ActionSourceDeclaration:
    """The corporate-action source, as REGISTERED. `authoritative` is an explicit declaration that the
    source is frozen and identified; it is never inferred from the presence of rows."""
    identity: str
    authoritative: bool = False
    coverage_start: date | None = None
    coverage_end: date | None = None

    def covers(self, start: date, end: date) -> bool:
        return (self.coverage_start is not None and self.coverage_end is not None
                and self.coverage_start <= start and self.coverage_end >= end)


@dataclass(frozen=True)
class Tolerance:
    """Price-quantum derived comparison band: `safety × quantum × Σ(1/price)` over the prices a
    comparison rounds, floored at `relative_floor`. A fixed 1e-4 quantum is a far larger relative error
    on a $1 name than on a $100 one, so the band is computed per observation rather than fixed."""
    price_quantum: float = PRICE_QUANTUM
    noise_safety_factor: float = NOISE_SAFETY_FACTOR
    relative_floor: float = RELATIVE_FLOOR
    absolute: float = ABSOLUTE_TOLERANCE

    def for_prices(self, *prices: float) -> float:
        """The relative band for a comparison involving `prices` — the summed reciprocal-price
        rounding contribution, scaled by the measured noise/signal separation factor."""
        usable = [p for p in prices if p and p > 0]
        if not usable:
            return self.relative_floor
        summed = sum(1.0 / p for p in usable)
        return max(self.relative_floor,
                   self.noise_safety_factor * self.price_quantum * summed)

    def basis(self) -> dict[str, float | str]:
        return {"price_quantum": self.price_quantum,
                "noise_safety_factor": self.noise_safety_factor,
                "relative_floor": self.relative_floor, "absolute_tolerance": self.absolute,
                "precision_basis": "sep prices stored to 4 decimals; a one-day ratio comparison rounds "
                                   "four prices (raw and adjusted, this session and the previous), so "
                                   "the band sums their reciprocal-price contributions; the safety "
                                   "factor sits in the measured gap between rounding noise and real "
                                   "adjustment events (7,362 events at 5x vs 7,302 at 20x)"}


@dataclass(frozen=True)
class ActionCheck:
    """One (ticker, ex-date) group's verification, with everything needed to re-derive the verdict."""
    ticker: str
    action_date: str
    action_types: tuple[str, ...]
    action_class: ActionClass
    declared_split_multiplier: float | None
    declared_cash_per_share: float | None
    prev_close: float | None
    close: float | None
    prev_closeadj: float | None
    closeadj: float | None
    expected_ratio: float | None
    observed_ratio: float | None
    absolute_residual: float | None
    relative_residual: float | None
    absolute_tolerance: float
    relative_tolerance: float
    verdict: AdjustmentVerdict
    detail: str


@dataclass(frozen=True)
class UnexplainedAdjustment:
    """An adjustment event visible in the series with no declared action to explain it."""
    ticker: str
    session_date: str
    observed_ratio: float
    raw_ratio: float
    absolute_residual: float
    relative_tolerance: float


@dataclass(frozen=True)
class AdjustmentVerificationEvidence:
    """OPEN provenance for one window's verification — actions, prices and arithmetic only. No factor
    values, rankings, returns or portfolio results."""
    session_date: str
    window_start: str
    verdict: AdjustmentVerdict
    proven: bool
    adjustment_series_consistent_with_declared_actions: bool
    declared_action_source_authoritative: bool
    source_identity: str
    source_coverage_start: str | None
    source_coverage_end: str | None
    total_actions_in_window: int
    relevant_actions_in_window: int
    irrelevant_actions_in_window: int
    relevant_ticker_count: int
    relevance_set_sha256: str
    store_identity_sha256: str
    checks_by_verdict: dict[str, int]
    unexplained_adjustment_count: int
    detail: str
    tolerance: dict[str, float | str] = field(default_factory=dict)
    checks: tuple[ActionCheck, ...] = ()
    unexplained_examples: tuple[UnexplainedAdjustment, ...] = ()

    def to_open_provenance(self) -> dict[str, Any]:
        d = asdict(self)
        d["verdict"] = str(self.verdict)
        d["checks"] = [{**asdict(c), "verdict": str(c.verdict),
                        "action_class": str(c.action_class)} for c in self.checks]
        d["unexplained_examples"] = [asdict(u) for u in self.unexplained_examples]
        return d


def relevance_digest(tickers: list[str], window_start: date, session_date: date,
                     store_identity_sha256: str) -> str:
    """Bind the relevance SET to the same value-level store identity R5a records, so the set a
    verification ran over cannot be reinterpreted later against different data."""
    payload = "|".join([store_identity_sha256, window_start.isoformat(), session_date.isoformat(),
                        *sorted(tickers)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def classify_action(label: str, contraticker: Any) -> ActionClass:
    """Classify a raw action label. A contraticker means another security is involved, which the
    one-security ratio relationship cannot express — those stay unsupported."""
    text = str(label or "").strip().lower()
    if contraticker not in (None, "", "nan"):
        if text in _MERGER_LABELS:
            return ActionClass.MERGER_CONVERSION
        if text in _SPINOFF_LABELS:
            return ActionClass.SPINOFF_DISTRIBUTION
        return ActionClass.UNSUPPORTED
    if text in _CASH_LABELS:
        return ActionClass.CASH_DIVIDEND
    if text in _SPLIT_LABELS:
        return ActionClass.SPLIT
    if text in _SPINOFF_LABELS:
        return ActionClass.SPINOFF_DISTRIBUTION
    if text in _MERGER_LABELS:
        return ActionClass.MERGER_CONVERSION
    if text in _SYMBOL_LABELS:
        return ActionClass.SYMBOL_TRANSITION
    return ActionClass.UNSUPPORTED


def _query(store: Any, sql: str, params: list) -> list[tuple]:
    con = getattr(store, "con", store)
    if not hasattr(con, "execute"):
        raise AdjustmentVerificationError(f"not a queryable store: {type(store).__name__}")
    try:
        return [tuple(r) for r in con.execute(sql, params).fetchall()]
    except Exception as exc:
        raise AdjustmentVerificationError(f"store query failed: {exc}") from exc


def verify_adjustments(
    store: Any,
    *,
    window_start: date,
    session_date: date,
    relevant_tickers: list[str],
    source: ActionSourceDeclaration,
    store_identity_sha256: str = "",
    tolerance: Tolerance | None = None,
    max_examples: int = 25,
) -> AdjustmentVerificationEvidence:
    """Verify that the adjusted series over `[window_start, session_date]` reflects every relevant
    declared action, and that no adjustment in the series is unexplained.

    `relevant_tickers` is the union of the securities whose adjusted observations can influence the
    session — the scoring candidates plus the proxy's expected constituents across the whole MA window,
    including names that left the universe before the session but priced into it earlier.
    """
    tol = tolerance or Tolerance()
    names = sorted(set(relevant_tickers))
    digest = relevance_digest(names, window_start, session_date, store_identity_sha256)

    total_actions = _query(store, "SELECT COUNT(*) FROM actions WHERE date BETWEEN ? AND ?",
                           [window_start, session_date])[0][0]
    rows: list[tuple] = []
    if names:
        ph = ",".join("?" * len(names))
        rows = _query(store,
                      f"SELECT ticker, date, action, value, contraticker FROM actions "
                      f"WHERE date BETWEEN ? AND ? AND ticker IN ({ph}) "
                      f"ORDER BY ticker, date, action, value",
                      [window_start, session_date, *names])
    relevant = len(rows)

    def evidence(verdict: AdjustmentVerdict, detail: str, *, consistent: bool,
                 checks: tuple[ActionCheck, ...] = (),
                 unexplained: tuple[UnexplainedAdjustment, ...] = (),
                 unexplained_count: int = 0) -> AdjustmentVerificationEvidence:
        by_verdict: dict[str, int] = {}
        for c in checks:
            by_verdict[str(c.verdict)] = by_verdict.get(str(c.verdict), 0) + 1
        proven = verdict in (AdjustmentVerdict.PROVEN, AdjustmentVerdict.NO_RELEVANT_ACTIONS)
        return AdjustmentVerificationEvidence(
            session_date=session_date.isoformat(), window_start=window_start.isoformat(),
            verdict=verdict, proven=proven,
            adjustment_series_consistent_with_declared_actions=consistent,
            declared_action_source_authoritative=source.authoritative,
            source_identity=source.identity,
            source_coverage_start=source.coverage_start.isoformat() if source.coverage_start else None,
            source_coverage_end=source.coverage_end.isoformat() if source.coverage_end else None,
            total_actions_in_window=int(total_actions), relevant_actions_in_window=relevant,
            irrelevant_actions_in_window=int(total_actions) - relevant,
            relevant_ticker_count=len(names), relevance_set_sha256=digest,
            store_identity_sha256=store_identity_sha256, checks_by_verdict=by_verdict,
            unexplained_adjustment_count=unexplained_count, detail=detail,
            tolerance=tol.basis(), checks=checks, unexplained_examples=unexplained)

    if not names:
        return evidence(AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA,
                        "no relevant securities were supplied — nothing could be verified",
                        consistent=False)

    # The source must be declared authoritative and cover the window BEFORE any arithmetic counts.
    if not source.authoritative:
        return evidence(
            AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA,
            f"the corporate-action source {source.identity!r} is not declared authoritative — an "
            f"unfrozen or unidentified source cannot evidence reflection", consistent=False)
    if not source.covers(window_start, session_date):
        return evidence(
            AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA,
            f"the declared source coverage ({source.coverage_start}..{source.coverage_end}) does not "
            f"span the consumed window {window_start}..{session_date}", consistent=False)

    # ── direction (a): every relevant declared action must be reflected ──
    groups: dict[tuple[str, date], list[tuple]] = {}
    for ticker, when, label, value, contra in rows:
        groups.setdefault((ticker, when), []).append((label, value, contra))

    marks = _marks(store, names, window_start, session_date)
    checks: list[ActionCheck] = []
    for (ticker, when), items in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        checks.append(_check_group(ticker, when, items, marks, tol))

    conflict = [c for c in checks if c.verdict is AdjustmentVerdict.INTEGRITY_STOP_CONFLICT]
    unsupported = [c for c in checks if c.verdict is AdjustmentVerdict.NOT_PROVEN_UNSUPPORTED_ACTION]
    insufficient = [c for c in checks if c.verdict is AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA]
    consistent = not conflict

    # ── direction (b): every adjustment event in the series must be explained ──
    explained = {(t, d) for (t, d) in groups}
    unexplained = _unexplained_adjustments(store, names, window_start, session_date, tol, explained,
                                           limit=max_examples)
    unexplained_total, examples = unexplained

    if conflict:
        return evidence(AdjustmentVerdict.INTEGRITY_STOP_CONFLICT,
                        f"{len(conflict)} relevant action(s) contradict the adjusted series or each "
                        f"other (e.g. {conflict[0].ticker} {conflict[0].action_date}: "
                        f"{conflict[0].detail})", consistent=False, checks=tuple(checks),
                        unexplained=examples, unexplained_count=unexplained_total)
    if unsupported:
        return evidence(AdjustmentVerdict.NOT_PROVEN_UNSUPPORTED_ACTION,
                        f"{len(unsupported)} relevant action(s) are of a class no verifier supports "
                        f"(e.g. {unsupported[0].ticker} {unsupported[0].action_date}: "
                        f"{unsupported[0].action_types}); a contraticker event needs its own verifier",
                        consistent=consistent, checks=tuple(checks), unexplained=examples,
                        unexplained_count=unexplained_total)
    if insufficient:
        return evidence(AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA,
                        f"{len(insufficient)} relevant action(s) lack the prior/current raw and "
                        f"adjusted marks the relationship needs (e.g. {insufficient[0].ticker} "
                        f"{insufficient[0].action_date})", consistent=consistent,
                        checks=tuple(checks), unexplained=examples,
                        unexplained_count=unexplained_total)
    if unexplained_total:
        return evidence(
            AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA,
            f"{unexplained_total} adjustment event(s) in the consumed window have no declared action "
            f"to explain them (e.g. {examples[0].ticker} {examples[0].session_date}) — the declared "
            f"set is incomplete, and an empty action table is not evidence that none occurred",
            consistent=consistent, checks=tuple(checks), unexplained=examples,
            unexplained_count=unexplained_total)

    if not checks:
        return evidence(AdjustmentVerdict.NO_RELEVANT_ACTIONS,
                        "an authoritative source covering the window declares no action on any "
                        "relevant security, and the series shows no unexplained adjustment",
                        consistent=True)
    return evidence(AdjustmentVerdict.PROVEN,
                    f"all {len(checks)} relevant action(s) are reflected within the price-quantum "
                    f"tolerance, and no adjustment is unexplained", consistent=True,
                    checks=tuple(checks))


def _marks(store: Any, names: list[str], window_start: date, session_date: date
           ) -> dict[tuple[str, date], tuple[float | None, float | None, float | None, float | None]]:
    """(ticker, date) → (prev_close, close, prev_closeadj, closeadj) across the window."""
    ph = ",".join("?" * len(names))
    rows = _query(store,
                  f"SELECT ticker, date, close, closeadj, "
                  f"lag(close) OVER (PARTITION BY ticker ORDER BY date), "
                  f"lag(closeadj) OVER (PARTITION BY ticker ORDER BY date) "
                  f"FROM sep WHERE ticker IN ({ph}) AND date BETWEEN ? AND ? ORDER BY ticker, date",
                  [*names, window_start, session_date])
    return {(r[0], r[1]): (r[4], r[2], r[5], r[3]) for r in rows}


def _check_group(ticker: str, when: date, items: list[tuple], marks: dict, tol: Tolerance) -> ActionCheck:
    """Verify one (ticker, ex-date) group. Rows are composed, never silently collapsed."""
    types = tuple(str(i[0]) for i in items)
    classes = [classify_action(label, contra) for label, _v, contra in items]

    def result(verdict: AdjustmentVerdict, klass: ActionClass, detail: str, *, split=None, cash=None,
               expected=None, observed=None, abs_res=None, rel_res=None, rel_tol=0.0,
               prices=(None, None, None, None)) -> ActionCheck:
        return ActionCheck(
            ticker=ticker, action_date=when.isoformat(), action_types=types, action_class=klass,
            declared_split_multiplier=split, declared_cash_per_share=cash,
            prev_close=prices[0], close=prices[1], prev_closeadj=prices[2], closeadj=prices[3],
            expected_ratio=expected, observed_ratio=observed, absolute_residual=abs_res,
            relative_residual=rel_res, absolute_tolerance=tol.absolute, relative_tolerance=rel_tol,
            verdict=verdict, detail=detail)

    # identical duplicate source rows are a contradiction, not a composition
    if len(items) != len({(str(a), float(b) if b is not None else None, c) for a, b, c in items}):
        return result(AdjustmentVerdict.INTEGRITY_STOP_CONFLICT, ActionClass.UNSUPPORTED,
                      "identical duplicate action rows for the same ticker and date")

    unsupported = [k for k in classes if k in (ActionClass.UNSUPPORTED,
                                               ActionClass.SPINOFF_DISTRIBUTION,
                                               ActionClass.MERGER_CONVERSION,
                                               ActionClass.SYMBOL_TRANSITION)]
    if unsupported:
        return result(AdjustmentVerdict.NOT_PROVEN_UNSUPPORTED_ACTION, unsupported[0],
                      f"action class {unsupported[0]} has no verifier; it may involve another "
                      f"security or a non-price event")

    splits = [float(v) for (label, v, _c), k in zip(items, classes, strict=True)
              if k is ActionClass.SPLIT and v is not None]
    cash = [float(v) for (label, v, _c), k in zip(items, classes, strict=True)
            if k is ActionClass.CASH_DIVIDEND and v is not None]
    if len(splits) > 1 and len({round(s, 10) for s in splits}) > 1:
        return result(AdjustmentVerdict.INTEGRITY_STOP_CONFLICT, ActionClass.SPLIT,
                      f"incompatible split ratios declared on the same date: {splits}")
    if any(v is None for _l, v, _c in items):
        return result(AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA, ActionClass.UNSUPPORTED,
                      "an action row carries no declared value")

    klass = (ActionClass.SPLIT_AND_CASH if splits and cash
             else ActionClass.SPLIT if splits else ActionClass.CASH_DIVIDEND)
    split_mult = splits[0] if splits else 1.0
    cash_total = sum(cash)                     # additive: recognized cash distributions compose

    prices = marks.get((ticker, when))
    if prices is None or any(p is None or p <= 0 for p in prices):
        return result(AdjustmentVerdict.NOT_PROVEN_INSUFFICIENT_DATA, klass,
                      "the prior and current raw and adjusted marks are not all available",
                      split=split_mult, cash=cash_total, prices=prices or (None, None, None, None))

    prev_close, close, prev_adj, adj = prices
    expected = split_mult * (close + cash_total) / prev_close
    observed = adj / prev_adj
    abs_res = abs(observed - expected)
    rel_res = abs_res / abs(expected) if expected else float("inf")
    rel_tol = tol.for_prices(prev_close, close, prev_adj, adj)
    if abs_res > tol.absolute + rel_tol * abs(expected):
        return result(AdjustmentVerdict.INTEGRITY_STOP_CONFLICT, klass,
                      f"the adjusted series moves {observed:.8f} where the declared action implies "
                      f"{expected:.8f} (residual {abs_res:.3e} > tolerance)",
                      split=split_mult, cash=cash_total, expected=expected, observed=observed,
                      abs_res=abs_res, rel_res=rel_res, rel_tol=rel_tol, prices=prices)
    return result(AdjustmentVerdict.PROVEN, klass,
                  "the adjusted series matches the declared action within tolerance",
                  split=split_mult, cash=cash_total, expected=expected, observed=observed,
                  abs_res=abs_res, rel_res=rel_res, rel_tol=rel_tol, prices=prices)


def _unexplained_adjustments(store: Any, names: list[str], window_start: date, session_date: date,
                             tol: Tolerance, explained: set[tuple[str, date]], *, limit: int
                             ) -> tuple[int, tuple[UnexplainedAdjustment, ...]]:
    """Adjustment EVENTS visible in the series with no declared action on that (ticker, date).

    An event is a session where the adjusted one-day ratio departs from the raw one-day ratio by more
    than the price-quantum noise — exactly what a split or distribution looks like in the data.
    """
    ph = ",".join("?" * len(names))
    rows = _query(store,
                  f"WITH s AS (SELECT ticker, date, close, closeadj, "
                  f"  lag(close) OVER (PARTITION BY ticker ORDER BY date) AS pclose, "
                  f"  lag(closeadj) OVER (PARTITION BY ticker ORDER BY date) AS padj "
                  f"  FROM sep WHERE ticker IN ({ph}) AND date BETWEEN ? AND ?) "
                  f"SELECT ticker, date, close, closeadj, pclose, padj FROM s "
                  f"WHERE pclose > 0 AND padj > 0 AND close > 0 AND closeadj > 0 "
                  f"ORDER BY ticker, date",
                  [*names, window_start, session_date])
    total = 0
    examples: list[UnexplainedAdjustment] = []
    for ticker, when, close, adj, pclose, padj in rows:
        if (ticker, when) in explained:
            continue
        observed = adj / padj
        raw = close / pclose
        residual = abs(observed - raw)
        rel_tol = tol.for_prices(pclose, close, padj, adj)
        if residual > tol.absolute + rel_tol * abs(raw):
            total += 1
            if len(examples) < limit:
                examples.append(UnexplainedAdjustment(
                    ticker=ticker, session_date=when.isoformat(), observed_ratio=observed,
                    raw_ratio=raw, absolute_residual=residual, relative_tolerance=rel_tol))
    return total, tuple(examples)
