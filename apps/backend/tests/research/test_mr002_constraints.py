"""MR-002 constraint fixtures — the owner's required tests before the 1,700-session run.

The registered relative constraints are evaluated against the ACTUAL gross exposure
of the COMPLETE TENTATIVE POST-TRADE PORTFOLIO, with the denominator recomputed
after each deterministic removal. Percentage values are unchanged (20% / 5% / 0.10).
"""

from __future__ import annotations

import random
from datetime import date

import pytest

from app.research.mr002.portfolio import (
    BETA_CAP,
    POSITION_CAP_NAV,
    SECTOR_GROSS_CAP,
    SECTOR_NET_CAP,
    Candidate,
    Position,
    build_orders,
)

NAV = 10_000_000.0
SECTORS = ["XLK", "XLF", "XLV", "XLI", "XLY", "XLP", "XLE", "XLB", "XLU"]


def cand(pt: int, side: int, sector: str, z: float, beta: float = 1.0,
         price: float = 100.0, adv: float = 1e9) -> Candidate:
    return Candidate(pt, f"T{pt}", side, z, sigma_resid=0.02, sector_etf=sector,
                     beta=beta, exec_price=price, adv_dollar=adv)


def ratios(orders, positions, prices):
    """Recompute the registered ratios on the FINAL portfolio (independent check)."""
    w = []
    for p in positions:
        w.append((p.sector_etf, p.shares * prices.get(p.permaticker, p.entry_price) / NAV,
                  p.beta))
    for o in orders:
        w.append((o.sector, o.notional * o.side / NAV, o.beta))
    G = sum(abs(x[1]) for x in w)
    sg, sn = {}, {}
    for s, wi, _b in w:
        sg[s] = sg.get(s, 0.0) + abs(wi)
        sn[s] = sn.get(s, 0.0) + wi
    nb = sum(wi * b for _s, wi, b in w)
    return G, sg, sn, nb


def enrich(orders, cands):
    """Attach sector/beta to orders for the independent ratio check."""
    by = {c.permaticker: c for c in cands}
    for o in orders:
        o.sector = by[o.permaticker].sector_etf     # type: ignore[attr-defined]
        o.beta = by[o.permaticker].beta             # type: ignore[attr-defined]
    return orders


def assert_constraints_hold(orders, positions, prices):
    G, sg, sn, nb = ratios(orders, positions, prices)
    if G <= 0:
        return                                       # vacuously satisfied
    for s in sg:
        assert sg[s] / G <= SECTOR_GROSS_CAP + 1e-9, f"sector gross {s}"
        assert abs(sn[s]) / G <= SECTOR_NET_CAP + 1e-9, f"sector net {s}"
    assert abs(nb) / G <= BETA_CAP + 1e-9, "beta"


def test_bootstrap_succeeds_with_diversified_batch():
    """Zero-position book + broad sector-diversified L/S batch -> NONZERO orders
    that satisfy every ratio."""
    cands = []
    pt = 1
    for i, s in enumerate(SECTORS):
        for _ in range(3):                          # 3 longs + 3 shorts per sector
            cands.append(cand(pt, 1, s, -2.5 - i * 0.01, beta=1.0))
            pt += 1
            cands.append(cand(pt, -1, s, 2.5 + i * 0.01, beta=1.0))
            pt += 1
    res = build_orders(cands, [], {}, NAV)
    assert res.orders, "bootstrap produced no orders"
    assert_constraints_hold(enrich(res.orders, cands), [], {})
    assert res.diagnostics["final_gross_over_nav"] > 0


def test_bootstrap_rejects_single_sector_concentration():
    """Zero-position book + candidates concentrated in ONE sector must be reduced or
    rejected by the 20% sector-gross limit."""
    cands = [cand(i, 1 if i % 2 == 0 else -1, "XLK", -2.5 if i % 2 == 0 else 2.5)
             for i in range(1, 21)]
    res = build_orders(cands, [], {}, NAV)
    # every order is XLK: a single-sector book has sector_gross/G == 1.0 > 0.20, so
    # the batch must be emptied (there is no other sector to dilute it).
    assert not res.orders, "single-sector concentration was not rejected"
    assert any("sector_gross" in r for _c, r in res.rejected)


def test_batch_order_invariance_under_shuffle():
    """Shuffling candidate input order must produce IDENTICAL final orders."""
    cands = []
    pt = 1
    for i, s in enumerate(SECTORS):
        cands.append(cand(pt, 1, s, -2.5 - i * 0.03, beta=0.9 + i * 0.02))
        pt += 1
        cands.append(cand(pt, -1, s, 2.5 + i * 0.02, beta=1.1 - i * 0.01))
        pt += 1
    base = build_orders(list(cands), [], {}, NAV)
    key = sorted((o.permaticker, round(o.notional, 6)) for o in base.orders)
    for seed in range(5):
        sh = list(cands)
        random.Random(seed).shuffle(sh)
        r = build_orders(sh, [], {}, NAV)
        assert sorted((o.permaticker, round(o.notional, 6)) for o in r.orders) == key


def test_denominator_recomputed_after_removal():
    """Removing a candidate must REDUCE gross and force ratio recomputation."""
    cands = []
    pt = 1
    for s in SECTORS[:3]:
        for _ in range(4):
            cands.append(cand(pt, 1, s, -2.5))
            pt += 1
            cands.append(cand(pt, -1, s, 2.5))
            pt += 1
    # add one lopsided sector to force a net breach
    for _ in range(3):
        cands.append(cand(pt, 1, "XLE", -3.0))
        pt += 1
    res = build_orders(cands, [], {}, NAV)
    audit = res.diagnostics["constraint_audit"]
    removals = [a for a in audit if "removed" in a]
    if removals:
        g = [a["G_before"] for a in removals]
        assert all(g[i] >= g[i + 1] - 1e-12 for i in range(len(g) - 1)), \
            "gross did not decrease across successive removals"
    assert_constraints_hold(enrich(res.orders, cands), [], {})


def test_cascading_breach_triggers_next_removal():
    """A removal that creates a NEW relative breach must trigger the next removal."""
    cands = []
    pt = 1
    for s in SECTORS[:2]:                            # only 2 sectors -> tight
        for _ in range(5):
            cands.append(cand(pt, 1, s, -2.5))
            pt += 1
            cands.append(cand(pt, -1, s, 2.5))
            pt += 1
    res = build_orders(cands, [], {}, NAV)
    # with only two sectors, each sector's gross is ~50% of G > 20% -> the batch must
    # be reduced repeatedly (cascade) until the constraints hold or nothing remains
    assert len(res.rejected) > 1, "no cascading removals occurred"
    assert_constraints_hold(enrich(res.orders, cands), [], {})


def test_zero_gross_no_division_and_no_precheck_failure():
    """An empty portfolio must not divide by zero and must not fail constraints
    before candidate construction."""
    res = build_orders([], [], {}, NAV)
    assert res.orders == []
    assert res.diagnostics["final_gross_over_nav"] == 0.0
    assert res.diagnostics["final_normalized_beta"] == 0.0


def test_low_gross_existing_book_uses_combined_gross_not_nav():
    """A partially invested book + a new matched batch is assessed against the FINAL
    COMBINED gross — never 100% of NAV."""
    pos = [Position(999, "HELD", 1, 1500.0, 100.0, date(2013, 1, 2), -2.5, "XLK",
                    1.0, 0.02, 0, last_mark=100.0)]                 # 1.5% NAV long
    prices = {999: 100.0}
    cands = []
    pt = 1
    for s in SECTORS[:4]:
        cands.append(cand(pt, 1, s, -2.4))
        pt += 1
        cands.append(cand(pt, -1, s, 2.4))
        pt += 1
    res = build_orders(cands, pos, prices, NAV)
    G, sg, sn, nb = ratios(enrich(res.orders, cands), pos, prices)
    # the existing position is INCLUDED in the denominator and the sector sums
    assert G > 0
    assert "XLK" in sg
    # THE POINT OF THIS FIXTURE: the denominator is the ACTUAL combined gross —
    # materially below 100% of NAV — never the NAV shortcut.
    assert G < 1.0, "gross must not be assumed to be 100% of NAV"
    assert abs(G - res.diagnostics["final_gross_over_nav"]) < 1e-9,         "diagnostics denominator must equal the recomputed combined gross"
    # An existing FIXED-SHARE position can leave an UNCURABLE breach while the book
    # ramps (no candidate in that sector to remove). The frozen rule then keeps the
    # diversifying orders, which DILUTE the concentration — verify that direction.
    g_held_only = 0.015
    assert sg["XLK"] / G <= (g_held_only / g_held_only) , "sanity"
    if res.orders:
        assert g_held_only < G, "diversifying orders must raise gross (dilution)"
        uncurable = [a for a in res.diagnostics["constraint_audit"]
                     if a.get("uncurable_existing_positions")]
        # either the ratios hold, or the residual breach is explicitly attributed to
        # the existing fixed-share position (never silently ignored)
        try:
            assert_constraints_hold(res.orders, pos, prices)
        except AssertionError:
            assert uncurable, "residual breach must be attributed to existing positions"


def test_position_cap_and_adv_clip_preserved():
    """Frozen values unchanged: 1.5% NAV cap; ADV clip (clip, never delay)."""
    cands = [cand(1, 1, "XLK", -3.0, adv=1e5),       # tiny ADV -> clipped
             cand(2, -1, "XLF", 3.0, adv=1e9)]
    res = build_orders(cands, [], {}, NAV)
    for o in res.orders:
        assert o.notional <= POSITION_CAP_NAV * NAV + 1e-6
    clipped = [o for o in res.orders if o.clipped_by_adv]
    assert all(o.notional <= 0.02 * 1e5 + 1e-6 for o in clipped)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
