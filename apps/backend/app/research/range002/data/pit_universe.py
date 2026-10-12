"""Monthly point-in-time stock universe (WP1.5, L-9), built from injected records.

Rule (DESIGN v0.4 via Plan 2.1; every numeric value is an EXPLICIT parameter, none defaulted,
because D03 is unsigned): US common stocks, rebuilt for a month using only information visible
on the prior trading day, ranked by trailing average dollar volume, prior close above a floor,
top ``n``. Delisted-later names are NOT dropped: eligibility is "traded on the decision day",
and the issuer is identified by permaticker, never by a ticker string.

Structural properties (each has a synthetic test):
* no look-ahead: observations dated after ``decision_day`` are discarded before any use, and the
  later ``last_price_date`` label never influences selection;
* identity: the vendor ticker comes from the identity map on the decision day, and an unmapped
  or overlap-ambiguous issuer is EXCLUDED WITH A REASON, not silently kept or dropped;
* price bases: dollar volume is the ACTUAL TRADED price times the ACTUAL TRADED shares.
  Sharadar SEP documents ``close`` and ``volume`` as BOTH split-adjusted, so the traded share
  count is recovered with the same-vintage split factor ``close / closeunadj``:
  ``traded_shares = volume * close / closeunadj`` and
  ``dollar_volume = closeunadj * traded_shares`` (algebraically ``close * volume``; the
  split factor cancels). Written in the traded form so no split-adjusted price is ever the
  quantity ranked on. The $10 floor also uses ``closeunadj``, the price actually seen that day:
  the split-adjusted ``close`` is retro-adjusted by FUTURE splits, so a floor on it would leak
  the future. ``closeadj`` (dividend-adjusted) is never paired with ``volume``. The only
  split-adjusted inputs are the daily ``close`` and ``volume`` used for that recovery;
  intraday bars, opening range, stops and fills are all raw traded prices;
* accounting: ``population == members + below_cut + excluded``; nothing leaves unreported;
* no exclusion bound is chosen here. Whether the exclusion count is acceptable is a separate
  owner decision (``data.exclusion_bound``, UNSET); this module only reports it against the
  original population.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from app.research.range002.data.identity_map import (
    AMBIGUOUS_OVERLAP,
    RESOLVED,
    IdentityMap,
    ticker_on,
)

PURE_FUNCTIONS = ("build_universe_month",)

#: the only price/volume pairing this module accepts (see the module docstring)
BASIS_SPLIT_ADJUSTED = "SEP_SPLIT_ADJUSTED"

NOT_COMMON_STOCK = "NOT_COMMON_STOCK"
NO_DECISION_DAY_PRINT = "NO_DECISION_DAY_PRINT"
INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
PRICE_NOT_ABOVE_MIN = "PRICE_NOT_ABOVE_MIN"
NO_IDENTITY_MAPPING = "NO_IDENTITY_MAPPING"
AMBIGUOUS_IDENTITY = "AMBIGUOUS_IDENTITY"
EXCLUSION_REASONS = (
    NOT_COMMON_STOCK,
    NO_DECISION_DAY_PRINT,
    INSUFFICIENT_HISTORY,
    PRICE_NOT_ABOVE_MIN,
    NO_IDENTITY_MAPPING,
    AMBIGUOUS_IDENTITY,
)


class PitUniverseError(ValueError):
    """The inputs are defective or violate a structural rule; the build refuses, never guesses."""


@dataclass(frozen=True)
class DailyObs:
    permaticker: str
    day: date
    close: float | None  # split-adjusted close, same basis as ``volume``
    close_unadj: float | None  # the price seen that day; used only for the price floor
    volume: float | None  # split-adjusted volume
    basis: str


@dataclass(frozen=True)
class Listing:
    permaticker: str
    common_stock: bool
    last_price_date: date | None  # reporting label only; never used to select


@dataclass(frozen=True)
class UniverseParams:
    n: int
    adv_window: int
    min_price: float
    basis: str  # the daily price pairing (the spec's data.daily_price_basis)
    #: vendor category strings treated as common stock (the spec's universe.category_map)
    category_map: tuple[str, ...]
    #: the intraday bar basis the spec binds (data.intraday_price_basis); join-checked, not used
    #: for selection
    intraday_basis: str


@dataclass(frozen=True)
class Member:
    rank: int
    permaticker: str
    vendor_ticker: str
    adv: float
    prior_close: float
    last_price_date: date | None


@dataclass(frozen=True)
class Exclusion:
    permaticker: str
    reason: str
    detail: str


@dataclass(frozen=True)
class UniverseMonth:
    month_start: date
    decision_day: date
    params: UniverseParams
    members: tuple[Member, ...]
    excluded: tuple[Exclusion, ...]
    below_cut: int
    population: int


def _check(
    month_start: date,
    decision_day: date,
    params: UniverseParams,
    listings: Sequence[Listing],
    observations: Sequence[DailyObs],
) -> None:
    if decision_day >= month_start:
        raise PitUniverseError("decision_day must be strictly before the month it governs")
    if params.n <= 0 or params.adv_window <= 0 or params.min_price <= 0:
        raise PitUniverseError("n, adv_window and min_price must be positive")
    if params.basis != BASIS_SPLIT_ADJUSTED:
        raise PitUniverseError(
            f"basis must be {BASIS_SPLIT_ADJUSTED!r}: close and volume are paired on the "
            "vendor's split-adjusted basis"
        )
    if len({li.permaticker for li in listings}) != len(listings):
        raise PitUniverseError("duplicate permaticker in the listings")
    keys = [(o.permaticker, o.day) for o in observations]
    if len(set(keys)) != len(keys):
        raise PitUniverseError("duplicate (permaticker, day) observation")
    bad = sorted({o.basis for o in observations if o.basis != params.basis})
    if bad:
        raise PitUniverseError(f"observation basis {bad} differs from required {params.basis!r}")


def _traded_dollar_volume(r: DailyObs) -> float:
    """closeunadj * traded shares, with traded shares = split-adjusted volume * close / closeunadj.

    Callers guarantee ``close``, ``volume`` and ``close_unadj`` are present and positive."""
    assert r.close is not None and r.volume is not None and r.close_unadj is not None
    traded_shares = float(r.volume) * float(r.close) / float(r.close_unadj)
    return float(r.close_unadj) * traded_shares


def build_universe_month(
    month_start: date,
    decision_day: date,
    listings: Iterable[Listing],
    observations: Iterable[DailyObs],
    idmap: IdentityMap,
    params: UniverseParams,
) -> UniverseMonth:
    lst = sorted(listings, key=lambda li: li.permaticker)
    obs = list(observations)
    _check(month_start, decision_day, params, lst, obs)
    visible: dict[str, list[DailyObs]] = {}
    for o in sorted(obs, key=lambda o: (o.permaticker, o.day)):
        if o.day <= decision_day:  # the look-ahead barrier: later rows never reach selection
            visible.setdefault(o.permaticker, []).append(o)

    excluded: list[Exclusion] = []
    scored: list[tuple[float, str, float, str, date | None]] = []
    for li in lst:
        pid = li.permaticker
        rows = visible.get(pid, [])
        last = rows[-1] if rows else None
        if not li.common_stock:
            excluded.append(
                Exclusion(pid, NOT_COMMON_STOCK, "listing category is not common stock")
            )
            continue
        if (
            last is None
            or last.day != decision_day
            or not last.close
            or not last.volume
            or not last.close_unadj
        ):
            excluded.append(
                Exclusion(pid, NO_DECISION_DAY_PRINT, f"no usable print on {decision_day}")
            )
            continue
        window = rows[-params.adv_window :]
        if len(window) < params.adv_window or any(
            not r.close or not r.volume or not r.close_unadj for r in window
        ):
            excluded.append(
                Exclusion(pid, INSUFFICIENT_HISTORY, f"fewer than {params.adv_window} usable days")
            )
            continue
        if last.close_unadj <= params.min_price:
            excluded.append(
                Exclusion(
                    pid,
                    PRICE_NOT_ABOVE_MIN,
                    f"unadjusted close {last.close_unadj} <= {params.min_price}",
                )
            )
            continue
        res = ticker_on(idmap, pid, decision_day)
        if res.status != RESOLVED or res.value is None:
            code = AMBIGUOUS_IDENTITY if res.status == AMBIGUOUS_OVERLAP else NO_IDENTITY_MAPPING
            excluded.append(Exclusion(pid, code, res.detail))
            continue
        adv = sum(_traded_dollar_volume(r) for r in window) / len(window)
        scored.append((adv, pid, last.close_unadj, res.value, li.last_price_date))

    scored.sort(key=lambda s: (-s[0], s[1]))
    members = tuple(
        Member(i + 1, pid, ticker, adv, close, lpd)
        for i, (adv, pid, close, ticker, lpd) in enumerate(scored[: params.n])
    )
    universe = UniverseMonth(
        month_start,
        decision_day,
        params,
        members,
        tuple(excluded),
        max(0, len(scored) - params.n),
        len(lst),
    )
    if universe.population != len(members) + universe.below_cut + len(excluded):
        raise PitUniverseError("universe accounting does not reconcile")
    return universe
