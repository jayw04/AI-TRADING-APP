"""Pure CandidateFamilyEngine — frozen product admission, no I/O.

Empty is a valid result. Missing inputs must be marked unavailable by the
caller; this module never invents a fallback screen.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.research.disc001.features import GapRow, MomCoreRow, SymbolFeatures
from app.research.disc001.spec import (
    DIST_52W_MAX,
    FAMILY_HORIZON,
    FAMILY_OPERATOR_NAME,
    FAMILY_STATUS,
    MAX_ALL,
    MAX_PER_FAMILY,
    MIN_ADV_20D,
    MIN_MARKET_CAP,
    MIN_PRICE,
    RET_5D_MAX,
    RS_20_VS_SPY_MIN,
    RS_ACCEL_MIN,
    RSI14_MAX,
    RSI_PERSIST_DAYS,
    RSI_PERSIST_MAX,
    RVOL20_MIN,
    STATUS_STRENGTH,
    EvidenceStatus,
    FamilyId,
)


@dataclass(frozen=True)
class ReasonChip:
    key: str
    value: str


@dataclass(frozen=True)
class CandidateCard:
    symbol: str
    family_ids: tuple[FamilyId, ...]
    horizon: str
    status: EvidenceStatus
    name: str | None
    sector: str | None
    chips: tuple[ReasonChip, ...]
    why: str
    tradability: str
    price_source: str
    close: float | None = None
    market_cap: float | None = None
    adv20: float | None = None
    sort_key: float = 0.0


@dataclass(frozen=True)
class FamilyResult:
    family_id: FamilyId
    available: bool
    unavailable_reason: str | None
    items: tuple[CandidateCard, ...]

    @property
    def empty(self) -> bool:
        return self.available and len(self.items) == 0


@dataclass(frozen=True)
class WatchlistResult:
    families: dict[FamilyId, FamilyResult]
    all_items: tuple[CandidateCard, ...]
    as_of: str
    universe_id: str
    screen_id: str
    screen_version: str
    vix: float | None = None
    subtitle: str = "Watch, not a signal"


@dataclass(frozen=True)
class FrozenGateObservation:
    """One frozen admission check. Eligibility is the conjunction of these."""

    key: str
    passed: bool
    summary: str


def _is_etf(category: str | None) -> bool:
    if not category:
        return False
    return "ETF" in category.upper()


def _crash_or_persist(feat: SymbolFeatures) -> bool:
    crash = feat.ret_5d is not None and feat.ret_5d <= RET_5D_MAX
    persist = (
        RSI_PERSIST_DAYS >= 2
        and feat.rsi14 is not None
        and feat.rsi14_prev is not None
        and feat.rsi14 < RSI_PERSIST_MAX
        and feat.rsi14_prev < RSI_PERSIST_MAX
    )
    return crash or persist


def shared_gate_observations(feat: SymbolFeatures) -> tuple[FrozenGateObservation, ...]:
    """Price / ADV / cap / ETF policy. Halt and pending CA are not applied here
    (HALT_CA_GATE = deferred_phase1b). Delisted-before-as_of names never reach
    this function — the PIT universe already dropped them.
    """
    return (
        FrozenGateObservation(
            key="etf",
            passed=not _is_etf(feat.category),
            summary="category contains ETF" if _is_etf(feat.category) else "not an ETF",
        ),
        FrozenGateObservation(
            key="min_price",
            passed=feat.close is not None and feat.close >= MIN_PRICE,
            summary=f"price = {_fmt_num(feat.close)}",
        ),
        FrozenGateObservation(
            key="min_adv20",
            passed=feat.adv20 is not None and feat.adv20 >= MIN_ADV_20D,
            summary=_fmt_adv(feat.adv20),
        ),
        FrozenGateObservation(
            key="min_market_cap",
            passed=feat.market_cap is not None and feat.market_cap >= MIN_MARKET_CAP,
            summary=_fmt_cap(feat.market_cap),
        ),
    )


def oversold_family_observations(feat: SymbolFeatures) -> tuple[FrozenGateObservation, ...]:
    rsi_ok = feat.rsi14 is not None and feat.rsi14 < RSI14_MAX
    trend_ok = feat.close is not None and feat.sma200 is not None and feat.close > feat.sma200
    stretch_ok = _crash_or_persist(feat)
    vs_sma: float | None = None
    sma200 = feat.sma200
    if feat.close is not None and sma200 is not None and sma200 != 0:
        vs_sma = feat.close / sma200 - 1.0
    return (
        FrozenGateObservation(
            key="rsi14",
            passed=rsi_ok,
            summary=f"RSI14 = {_fmt_num(feat.rsi14)}",
        ),
        FrozenGateObservation(
            key="sma200",
            passed=trend_ok,
            summary=f"close vs SMA(200) = {_fmt_pct(vs_sma)}",
        ),
        FrozenGateObservation(
            key="crash_or_persist",
            passed=stretch_ok,
            summary=f"ret_5d = {_fmt_pct(feat.ret_5d)}",
        ),
    )


def mom_near_family_observations(
    feat: SymbolFeatures, mom_core_symbols: frozenset[str]
) -> tuple[FrozenGateObservation, ...]:
    rvol_ok = feat.rvol20 is not None and feat.rvol20 >= RVOL20_MIN
    rising_ok = feat.volume_rising_20d is True
    dist_ok = feat.dist_52w is not None and 0 <= feat.dist_52w <= DIST_52W_MAX
    return (
        FrozenGateObservation(
            key="not_mom_core",
            passed=feat.symbol not in mom_core_symbols,
            summary="also on MOM-CORE readout"
            if feat.symbol in mom_core_symbols
            else "not on MOM-CORE readout",
        ),
        FrozenGateObservation(
            key="rs_20_vs_spy",
            passed=feat.rs_20_vs_spy is not None and feat.rs_20_vs_spy > RS_20_VS_SPY_MIN,
            summary=f"RS20 vs SPY = {_fmt_pct(feat.rs_20_vs_spy)}",
        ),
        FrozenGateObservation(
            key="rs_accel",
            passed=feat.rs_accel is not None and feat.rs_accel > RS_ACCEL_MIN,
            summary=f"RS accel = {_fmt_pct(feat.rs_accel)}",
        ),
        FrozenGateObservation(
            key="dist_52w",
            passed=dist_ok,
            summary=f"dist from 52w high = {_fmt_pct(feat.dist_52w)}",
        ),
        FrozenGateObservation(
            key="participation",
            passed=rvol_ok or rising_ok,
            summary=(f"RVOL20 = {feat.rvol20:.1f}×" if feat.rvol20 is not None else "RVOL20 = —"),
        ),
    )


def oversold_gate_observations(feat: SymbolFeatures) -> tuple[FrozenGateObservation, ...]:
    return shared_gate_observations(feat) + oversold_family_observations(feat)


def mom_near_gate_observations(
    feat: SymbolFeatures, mom_core_symbols: frozenset[str]
) -> tuple[FrozenGateObservation, ...]:
    return shared_gate_observations(feat) + mom_near_family_observations(feat, mom_core_symbols)


def shared_eligible(feat: SymbolFeatures) -> bool:
    return all(obs.passed for obs in shared_gate_observations(feat))


def oversold_eligible(feat: SymbolFeatures) -> bool:
    return all(obs.passed for obs in oversold_gate_observations(feat))


def mom_near_eligible(feat: SymbolFeatures, mom_core_symbols: frozenset[str]) -> bool:
    return all(obs.passed for obs in mom_near_gate_observations(feat, mom_core_symbols))


def weakest_status(statuses: list[EvidenceStatus]) -> EvidenceStatus:
    if not statuses:
        return EvidenceStatus.WATCH
    return min(statuses, key=lambda s: STATUS_STRENGTH[s])


def _fmt_pct(x: float | None, digits: int = 1) -> str:
    if x is None:
        return "—"
    return f"{x * 100:.{digits}f}%"


def _fmt_num(x: float | None, digits: int = 1) -> str:
    if x is None:
        return "—"
    return f"{x:.{digits}f}"


def _fmt_adv(x: float | None) -> str:
    if x is None:
        return "—"
    if x >= 1_000_000_000:
        return f"ADV ${x / 1_000_000_000:.1f}B"
    if x >= 1_000_000:
        return f"ADV ${x / 1_000_000:.0f}M"
    return f"ADV ${x:,.0f}"


def _fmt_cap(x: float | None) -> str:
    if x is None:
        return "—"
    if x >= 1_000_000_000:
        return f"${x / 1_000_000_000:.1f}B"
    return f"${x / 1_000_000:.0f}M"


def _quality_chips(feat: SymbolFeatures) -> list[ReasonChip]:
    chips = [
        ReasonChip("adv20", _fmt_adv(feat.adv20)),
        ReasonChip("mktcap", _fmt_cap(feat.market_cap)),
    ]
    if feat.sector:
        chips.append(ReasonChip("sector", feat.sector))
    return chips


def _oversold_card(feat: SymbolFeatures, *, price_source: str) -> CandidateCard:
    vs = None
    if feat.close is not None and feat.sma200 not in (None, 0):
        vs = feat.close / feat.sma200 - 1.0
    chips = [
        ReasonChip("rsi14", _fmt_num(feat.rsi14, 0)),
        ReasonChip("ret_5d", _fmt_pct(feat.ret_5d)),
        ReasonChip("vs_sma200", _fmt_pct(vs)),
        *_quality_chips(feat),
    ]
    return CandidateCard(
        symbol=feat.symbol,
        family_ids=(FamilyId.OVERSOLD,),
        horizon=FAMILY_HORIZON[FamilyId.OVERSOLD],
        status=FAMILY_STATUS[FamilyId.OVERSOLD],
        name=feat.name,
        sector=feat.sector,
        chips=tuple(chips),
        why=("quality-eligible name stretched to RSI<30 while the 200-day trend is intact"),
        tradability="not measured (Phase 1)",
        price_source=price_source,
        close=feat.close,
        market_cap=feat.market_cap,
        adv20=feat.adv20,
        sort_key=float(feat.rsi14) if feat.rsi14 is not None else 100.0,
    )


def _mom_near_card(feat: SymbolFeatures, *, price_source: str) -> CandidateCard:
    chips = [
        ReasonChip("rs_accel", _fmt_pct(feat.rs_accel)),
        ReasonChip("rs_20_vs_spy", _fmt_pct(feat.rs_20_vs_spy)),
        ReasonChip("dist_52w", _fmt_pct(feat.dist_52w)),
        ReasonChip("rvol20", f"{feat.rvol20:.1f}×" if feat.rvol20 is not None else "—"),
        *_quality_chips(feat),
    ]
    return CandidateCard(
        symbol=feat.symbol,
        family_ids=(FamilyId.MOM_NEAR,),
        horizon=FAMILY_HORIZON[FamilyId.MOM_NEAR],
        status=FAMILY_STATUS[FamilyId.MOM_NEAR],
        name=feat.name,
        sector=feat.sector,
        chips=tuple(chips),
        why="relative-strength acceleration near the 52-week high with participation",
        tradability="not measured (Phase 1)",
        price_source=price_source,
        close=feat.close,
        market_cap=feat.market_cap,
        adv20=feat.adv20,
        sort_key=-(feat.rs_accel or 0.0),
    )


def _mom_core_card(row: MomCoreRow, *, price_source: str) -> CandidateCard:
    chips = [
        ReasonChip("mom_rank", str(row.rank)),
        ReasonChip("adv20", _fmt_adv(row.adv20)),
        ReasonChip("mktcap", _fmt_cap(row.market_cap)),
    ]
    if row.sector:
        chips.append(ReasonChip("sector", row.sector))
    return CandidateCard(
        symbol=row.symbol,
        family_ids=(FamilyId.MOM_CORE,),
        horizon=FAMILY_HORIZON[FamilyId.MOM_CORE],
        status=FAMILY_STATUS[FamilyId.MOM_CORE],
        name=row.name,
        sector=row.sector,
        chips=tuple(chips),
        why="read-only MOM-001 ranked name (pattern validated; this card is still Watch-only)",
        tradability="not measured (Phase 1)",
        price_source=price_source,
        close=row.close,
        market_cap=row.market_cap,
        adv20=row.adv20,
        sort_key=float(row.rank),
    )


def _gap_card(row: GapRow, *, price_source: str) -> CandidateCard:
    chips = [
        ReasonChip("gap_pct", f"+{row.gap_pct:.1f}%" if row.gap_pct is not None else "—"),
    ]
    if row.premarket_volume is not None:
        vol = row.premarket_volume
        vol_s = f"{vol / 1_000_000:.1f}M" if vol >= 1_000_000 else f"{vol:,}"
        chips.append(ReasonChip("pre_mkt_vol", vol_s))
    if row.catalyst:
        chips.append(ReasonChip("news", row.catalyst[:80]))
    return CandidateCard(
        symbol=row.symbol,
        family_ids=(FamilyId.GAP,),
        horizon=FAMILY_HORIZON[FamilyId.GAP],
        status=FAMILY_STATUS[FamilyId.GAP],
        name=None,
        sector=None,
        chips=tuple(chips),
        why="pre-market gapper from the existing SCAN/gappers file (Backtest Pending)",
        tradability="not measured (Phase 1)",
        price_source=price_source,
        close=row.price,
        sort_key=float(row.rank),
    )


def screen_oversold(
    features: tuple[SymbolFeatures, ...],
    *,
    available: bool,
    unavailable_reason: str | None,
    price_source: str,
) -> FamilyResult:
    if not available:
        return FamilyResult(FamilyId.OVERSOLD, False, unavailable_reason, ())
    passed = [f for f in features if oversold_eligible(f)]
    cards = [_oversold_card(f, price_source=price_source) for f in passed]
    cards.sort(key=lambda c: (c.sort_key, -(c.adv20 or 0.0), c.symbol))
    return FamilyResult(FamilyId.OVERSOLD, True, None, tuple(cards[:MAX_PER_FAMILY]))


def screen_mom_near(
    features: tuple[SymbolFeatures, ...],
    mom_core_symbols: frozenset[str],
    *,
    available: bool,
    unavailable_reason: str | None,
    price_source: str,
) -> FamilyResult:
    if not available:
        return FamilyResult(FamilyId.MOM_NEAR, False, unavailable_reason, ())
    passed = [f for f in features if mom_near_eligible(f, mom_core_symbols)]
    feat_by = {f.symbol: f for f in passed}

    def _near_key(c: CandidateCard) -> tuple:
        f = feat_by[c.symbol]
        return (-(f.rs_accel or 0.0), -(f.rvol20 or 0.0), c.symbol)

    cards = [_mom_near_card(f, price_source=price_source) for f in passed]
    cards.sort(key=_near_key)
    return FamilyResult(FamilyId.MOM_NEAR, True, None, tuple(cards[:MAX_PER_FAMILY]))


def screen_mom_core(
    rows: tuple[MomCoreRow, ...],
    *,
    available: bool,
    unavailable_reason: str | None,
    price_source: str,
) -> FamilyResult:
    if not available:
        return FamilyResult(FamilyId.MOM_CORE, False, unavailable_reason, ())
    ordered = sorted(rows, key=lambda r: (r.rank, r.symbol))
    cards = [_mom_core_card(r, price_source=price_source) for r in ordered[:MAX_PER_FAMILY]]
    return FamilyResult(FamilyId.MOM_CORE, True, None, tuple(cards))


def screen_gap(
    rows: tuple[GapRow, ...],
    *,
    available: bool,
    unavailable_reason: str | None,
    price_source: str,
) -> FamilyResult:
    if not available:
        return FamilyResult(FamilyId.GAP, False, unavailable_reason, ())
    ordered = sorted(rows, key=lambda r: (r.rank, r.symbol))
    cards = [_gap_card(r, price_source=price_source) for r in ordered[:MAX_PER_FAMILY]]
    return FamilyResult(FamilyId.GAP, True, None, tuple(cards))


def _merge_card(existing: CandidateCard, incoming: CandidateCard) -> CandidateCard:
    families = tuple(dict.fromkeys((*existing.family_ids, *incoming.family_ids)))
    status = weakest_status([FAMILY_STATUS[f] for f in families])
    weakest_family = min(families, key=lambda f: STATUS_STRENGTH[FAMILY_STATUS[f]])
    seen: set[str] = set()
    merged_chips: list[ReasonChip] = []
    for chip in (*existing.chips, *incoming.chips):
        if chip.key in seen:
            continue
        seen.add(chip.key)
        merged_chips.append(chip)
    why = incoming.why if incoming.status == status else existing.why
    if len(families) > 1:
        names = ", ".join(FAMILY_OPERATOR_NAME[f] for f in families)
        why = f"also appears in {names}. " + why
    return CandidateCard(
        symbol=existing.symbol,
        family_ids=families,
        horizon=FAMILY_HORIZON[weakest_family],
        status=status,
        name=existing.name or incoming.name,
        sector=existing.sector or incoming.sector,
        chips=tuple(merged_chips),
        why=why,
        tradability=existing.tradability,
        price_source=existing.price_source,
        close=existing.close if existing.close is not None else incoming.close,
        market_cap=existing.market_cap if existing.market_cap is not None else incoming.market_cap,
        adv20=existing.adv20 if existing.adv20 is not None else incoming.adv20,
        sort_key=existing.sort_key,
    )


def assemble_all(families: dict[FamilyId, FamilyResult]) -> tuple[CandidateCard, ...]:
    """Unique symbols across available families; weakest badge wins. Cap MAX_ALL.

    Order: OVERSOLD, MOM-NEAR, GAP, MOM-CORE — first time a symbol is seen keeps
    position; later families merge onto that card.
    """
    order = (FamilyId.OVERSOLD, FamilyId.MOM_NEAR, FamilyId.GAP, FamilyId.MOM_CORE)
    by_symbol: dict[str, CandidateCard] = {}
    sequence: list[str] = []
    for fid in order:
        result = families.get(fid)
        if result is None or not result.available:
            continue
        for card in result.items:
            if card.symbol in by_symbol:
                by_symbol[card.symbol] = _merge_card(by_symbol[card.symbol], card)
            else:
                by_symbol[card.symbol] = card
                sequence.append(card.symbol)
    return tuple(by_symbol[s] for s in sequence[:MAX_ALL])
