"""MR-002 deterministic portfolio construction — FROZEN v1.0 §5 (immutable).

Exactly the registered algorithm, in order:

 1. EXITS FIRST, then entries. One position per symbol; no pyramiding; a symbol
    exited at the t+1 open cannot be re-entered at that same open.
 2. INCREMENTAL capacity around existing positions:
        current_gross            = long_gross + short_gross
        gross_headroom           = max(0, 100% NAV - current_gross)
        long_increment_capacity  = min(candidate_long_capacity,
                                       long-side constraint headroom,
                                       gross_headroom / 2)
        short_increment_capacity = min(candidate_short_capacity,
                                       short-side constraint headroom,
                                       gross_headroom / 2)
        matched_increment        = min(long_increment_capacity,
                                       short_increment_capacity)
    New long orders and new short orders are EACH limited to matched_increment.
 3. Candidate weights ∝ 1/sigma_resid within each side, normalized TO THE
    INCREMENT (never to 50% of NAV). Unused incremental capacity remains CASH.
    Existing positions are NEVER increased to consume unused headroom.
 4. Constraints in the registered reduction order:
        (i) position cap 1.5% of NAV (applied to the COMBINED exposure of a new
            order with any existing exposure)
        (ii) sector caps: net <= 5% of gross, gross <= 20% of gross
        (iii) beta limit: |sum(w_i * beta_i)| / gross <= 0.10
    Removal NEVER renormalizes the remaining weights upward — freed capacity goes
    to CASH. Targeted removal per breach:
        sector  -> least-extreme candidate IN THE OFFENDING SECTOR
        beta    -> the candidate whose exclusion most reduces |normalized beta|,
                   tie-break smallest |z|
        gross   -> the globally least-extreme candidate
 5. FIXED SHARES until exit (no re-marking to target weights).
 6. Drift: ENTRY-NEUTRAL with a +/-5%-of-gross tolerance band. No rebalance while
    |net| <= 5% of gross; on breach, reduce the LARGER side by smallest |entry z|
    first (tie: oldest, then permanent identifier).

Gross exposure is a 100%-of-NAV MAXIMUM, never a target. No cash return is
credited in the primary result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

POSITION_CAP_NAV = 0.015          # 1.5% of NAV
SECTOR_NET_CAP = 0.05             # 5% of gross
SECTOR_GROSS_CAP = 0.20           # 20% of gross
BETA_CAP = 0.10                   # per unit of gross
DRIFT_BAND = 0.05                 # +/-5% of gross
MAX_GROSS_NAV = 1.00              # 100% of NAV maximum


@dataclass
class Position:
    permaticker: int
    ticker: str
    side: int                     # +1 long, -1 short
    shares: float
    entry_price: float
    entry_date: date
    entry_z: float
    sector_etf: str
    beta: float
    sigma_resid: float
    entry_session_idx: int
    last_mark: float = 0.0        # price at which the position was last marked


@dataclass
class Candidate:
    permaticker: int
    ticker: str
    side: int
    z: float
    sigma_resid: float
    sector_etf: str
    beta: float
    exec_price: float
    adv_dollar: float             # 20-session median dollar volume (participation cap)


@dataclass
class Order:
    permaticker: int
    ticker: str
    side: int
    shares: float
    price: float
    notional: float
    reason: str                   # entry | exit_* | reduce_*
    z: float = 0.0
    clipped_by_adv: bool = False


@dataclass
class ConstructionResult:
    orders: list[Order] = field(default_factory=list)
    rejected: list[tuple[Candidate, str]] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)


def _exposure(positions: list[Position], prices: dict[int, float]) -> tuple[float, float]:
    long_g = sum(p.shares * prices.get(p.permaticker, p.entry_price)
                 for p in positions if p.side > 0)
    short_g = sum(abs(p.shares) * prices.get(p.permaticker, p.entry_price)
                  for p in positions if p.side < 0)
    return long_g, short_g


def build_orders(
    candidates: list[Candidate],
    positions: list[Position],
    prices: dict[int, float],
    nav: float,
    adv_participation: float = 0.02,
) -> ConstructionResult:
    """The frozen deterministic construction (exits are applied by the caller first)."""
    res = ConstructionResult()
    long_g, short_g = _exposure(positions, prices)
    current_gross = long_g + short_g
    headroom = max(0.0, MAX_GROSS_NAV * nav - current_gross)

    longs = sorted([c for c in candidates if c.side > 0], key=lambda c: (c.z, c.ticker))
    shorts = sorted([c for c in candidates if c.side < 0],
                    key=lambda c: (-c.z, c.ticker))

    # per-side capacity: the sum of what each side could take under the position cap
    held = {p.permaticker: p for p in positions}

    def side_capacity(cands: list[Candidate]) -> float:
        cap = 0.0
        for c in cands:
            if c.permaticker in held:            # no pyramiding
                continue
            cap += POSITION_CAP_NAV * nav
        return cap

    long_cap = min(side_capacity(longs), headroom / 2.0)
    short_cap = min(side_capacity(shorts), headroom / 2.0)
    matched = min(long_cap, short_cap)           # dollar-neutral at order time
    res.diagnostics.update({
        "nav": nav, "current_gross": current_gross, "gross_headroom": headroom,
        "long_increment_capacity": long_cap, "short_increment_capacity": short_cap,
        "matched_increment": matched,
    })
    if matched <= 0:
        for c in candidates:
            res.rejected.append((c, "no_matched_increment"))
        # G = 0 (or unchanged): the relative constraints are vacuously satisfied
        g0 = current_gross / nav if nav > 0 else 0.0
        res.diagnostics.update({
            "constraint_audit": [], "final_gross_over_nav": g0,
            "final_sector_gross_ratio": {}, "final_sector_net_ratio": {},
            "final_normalized_beta": 0.0})
        return res

    def allocate(cands: list[Candidate], budget: float) -> list[Order]:
        elig = [c for c in cands if c.permaticker not in held]
        for c in cands:
            if c.permaticker in held:
                res.rejected.append((c, "already_held_no_pyramiding"))
        if not elig:
            return []
        # weights ∝ 1/sigma_resid, normalized TO THE INCREMENT
        inv = {c.permaticker: (1.0 / c.sigma_resid if c.sigma_resid > 0 else 0.0)
               for c in elig}
        tot = sum(inv.values())
        if tot <= 0:
            return []
        orders = []
        for c in elig:
            notional = budget * inv[c.permaticker] / tot
            # (i) position cap on COMBINED exposure (no existing exposure by
            # construction — pyramiding is prohibited)
            notional = min(notional, POSITION_CAP_NAV * nav)
            # participation cap: clip, never delay
            cap = adv_participation * c.adv_dollar
            clipped = notional > cap
            notional = min(notional, cap)
            if notional <= 0 or c.exec_price <= 0:
                res.rejected.append((c, "zero_notional_or_price"))
                continue
            shares = notional / c.exec_price * c.side
            orders.append(Order(c.permaticker, c.ticker, c.side, shares,
                                c.exec_price, notional, "entry", c.z, clipped))
        return orders

    long_orders = allocate(longs, matched)
    short_orders = allocate(shorts, matched)

    # ---- constraint evaluation: BATCHWISE, on the COMPLETE TENTATIVE POST-TRADE
    # PORTFOLIO, against ACTUAL gross, recomputed after EVERY removal.
    #
    # DEFECT CLASSIFICATION (owner adjudication, 2026-07-12): "implementation
    # sequencing ambiguity discovered during development. The frozen percentage
    # values and economic definitions remain unchanged. Relative sector and beta
    # constraints are evaluated against the actual gross exposure of the complete
    # tentative post-trade portfolio, with the denominator recomputed after each
    # deterministic candidate removal. The rejected maximum-gross denominator
    # interpretation is not used because it would materially loosen constraints in
    # underinvested states."
    #
    # Frozen formulas:
    #   w_i = signed post-trade market value / execution-open NAV basis
    #   G   = sum |w_i|                              (ACTUAL tentative gross)
    #   sector_gross_s / G <= 0.20
    #   sector_net_s   / G <= 0.05
    #   |sum w_i * beta_i| / G <= 0.10
    #   G = 0 -> the relative constraints are vacuously satisfied.
    cand_by_pt = {c.permaticker: c for c in candidates}
    orders = long_orders + short_orders

    def tentative_state(orders: list[Order]) -> tuple[float, dict, dict, float]:
        """The COMPLETE tentative post-trade portfolio: existing positions + all
        proposed orders. Returns (G, sector_gross, sector_net, net_beta) in NAV
        units (w_i = signed post-trade MV / NAV)."""
        w: list[tuple[str, float, float]] = []      # (sector, signed w, beta)
        for p in positions:
            mv = p.shares * prices.get(p.permaticker, p.entry_price)   # signed
            w.append((p.sector_etf, mv / nav, p.beta))
        for o in orders:
            c = cand_by_pt[o.permaticker]
            mv = o.notional * o.side                                   # signed
            w.append((c.sector_etf, mv / nav, c.beta))
        G = sum(abs(x[1]) for x in w)
        s_gross: dict[str, float] = {}
        s_net: dict[str, float] = {}
        for sec, wi, _b in w:
            s_gross[sec] = s_gross.get(sec, 0.0) + abs(wi)
            s_net[sec] = s_net.get(sec, 0.0) + wi
        net_beta = sum(wi * b for _s, wi, b in w)
        return G, s_gross, s_net, net_beta

    audit: list[dict] = []
    for _ in range(len(orders) + 1):
        G, s_gross, s_net, net_beta = tentative_state(orders)
        if G <= 0:                       # vacuously satisfied (empty portfolio)
            break
        # first breach, in the registered order: sector gross -> sector net -> beta
        breach_sector = None
        breach_kind = None
        for sec in sorted(s_gross):
            if s_gross[sec] / G > SECTOR_GROSS_CAP:
                breach_sector, breach_kind = sec, "sector_gross"
                break
        if breach_sector is None:
            for sec in sorted(s_net):
                if abs(s_net[sec]) / G > SECTOR_NET_CAP:
                    breach_sector, breach_kind = sec, "sector_net"
                    break
        beta_breach = abs(net_beta) / G > BETA_CAP
        if breach_sector is None and not beta_breach:
            break
        if breach_sector is not None:
            # registered target: the least-extreme candidate IN THE OFFENDING SECTOR
            in_sector = [o for o in orders
                         if cand_by_pt[o.permaticker].sector_etf == breach_sector]
            if not in_sector:
                # the breach comes from EXISTING positions, which are fixed-share by
                # the frozen rule — no candidate can cure it; stop removing.
                audit.append({"breach": breach_kind, "sector": breach_sector,
                              "G": G, "uncurable_existing_positions": True})
                break
            victim = min(in_sector, key=lambda o: (abs(o.z), o.ticker))
            reason = f"{breach_kind}_cap_{breach_sector}"
        else:
            # beta: remove the candidate whose exclusion most reduces |normalized
            # beta|; tie-break smallest |z|
            best, best_val = None, None
            for o in orders:
                trial = [x for x in orders if x is not o]
                g2, _sg, _sn, nb2 = tentative_state(trial)
                v = abs(nb2) / g2 if g2 > 0 else 0.0
                if best_val is None or v < best_val - 1e-15 or (
                        abs(v - best_val) <= 1e-15 and abs(o.z) < abs(best.z)):
                    best, best_val = o, v
            if best is None:
                break
            victim, reason = best, "beta_cap"
        orders.remove(victim)
        res.rejected.append((cand_by_pt[victim.permaticker], reason))
        audit.append({"removed": victim.ticker, "reason": reason, "G_before": G})

    G, s_gross, s_net, net_beta = tentative_state(orders)
    res.diagnostics.update({
        "constraint_audit": audit,
        "final_gross_over_nav": G,
        "final_sector_gross_ratio": {s: (v / G if G > 0 else 0.0)
                                     for s, v in sorted(s_gross.items())},
        "final_sector_net_ratio": {s: (abs(v) / G if G > 0 else 0.0)
                                   for s, v in sorted(s_net.items())},
        "final_normalized_beta": (abs(net_beta) / G if G > 0 else 0.0),
    })

    res.orders = orders
    return res


def drift_reductions(positions: list[Position], prices: dict[int, float],
                     nav: float) -> list[Order]:
    """Entry-neutral drift band (frozen §5): no rebalance while |net| <= 5% of gross.
    On breach, reduce the LARGER side by smallest |entry z| first (tie: oldest,
    then permanent identifier)."""
    long_g, short_g = _exposure(positions, prices)
    gross = long_g + short_g
    if gross <= 0:
        return []
    net = long_g - short_g
    if abs(net) <= DRIFT_BAND * gross:
        return []
    side = 1 if net > 0 else -1
    excess = abs(net) - DRIFT_BAND * gross
    victims = sorted([p for p in positions if p.side == side],
                     key=lambda p: (abs(p.entry_z), p.entry_session_idx, p.permaticker))
    out: list[Order] = []
    for p in victims:
        if excess <= 0:
            break
        px = prices.get(p.permaticker, p.entry_price)
        value = abs(p.shares) * px
        cut_value = min(value, excess)
        cut_shares = cut_value / px * p.side
        out.append(Order(p.permaticker, p.ticker, -p.side, -cut_shares, px,
                         cut_value, "reduce_drift_band", p.entry_z))
        excess -= cut_value
    return out
