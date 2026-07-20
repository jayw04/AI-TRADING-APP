"""MR-002 Increment 3 — exposure calculations (three-state) + hard-cap checks (synthetic only).

Computes per-name / gross / net / sector-gross / sector-net / signed-beta-numerator / normalized-beta
/ cash for a set of legs at a given NAV, for any of the three states RAW_TARGET / INTENDED_TARGET /
REALIZED_EXECUTED (PR-22). Hard-cap checks return the DISTINCT realized reason codes (RC-2). Beta and
sector ratios are gross-normalized; an empty portfolio (gross 0) yields N_A_EMPTY_PORTFOLIO with no
division by zero (RC-2 empty_portfolio).
"""

from __future__ import annotations

from mr002_valoos_portfolio_identity import (
    BETA_MAX,
    GROSS_MAX,
    POSITION_CAP_NAV,
    SECTOR_GROSS_MAX,
    SECTOR_NET_MAX,
)

N_A_EMPTY = "N_A_EMPTY_PORTFOLIO"


def _signed(notional: float, side: str) -> float:
    return notional if side == "long" else -notional


def snapshot(state_label: str, legs: list, nav: float) -> dict:
    """legs: [{symbol, side, notional(>0 abs $), sector_id, beta}]. Returns an ExposureSnapshot dict of
    fractions of NAV (gross/per-name) and of gross (net/sector/beta)."""
    gross_d = sum(x["notional"] for x in legs)
    net_d = sum(_signed(x["notional"], x["side"]) for x in legs)
    per_name = {x["symbol"]: x["notional"] / nav for x in legs}
    beta_numer = sum(_signed(x["notional"], x["side"]) / nav * x["beta"] for x in legs)  # Sum w_i beta_i
    sector_gross_d, sector_net_d = {}, {}
    for x in legs:
        sector_gross_d[x["sector_id"]] = sector_gross_d.get(x["sector_id"], 0.0) + x["notional"]
        sector_net_d[x["sector_id"]] = sector_net_d.get(x["sector_id"], 0.0) + _signed(x["notional"], x["side"])
    if gross_d == 0.0:
        normalized_beta = N_A_EMPTY
        sector_gross = {}
        sector_net = {}
        net = 0.0
    else:
        normalized_beta = abs(beta_numer) / (gross_d / nav)
        sector_gross = {s: d / gross_d for s, d in sector_gross_d.items()}
        sector_net = {s: abs(d) / gross_d for s, d in sector_net_d.items()}
        net = abs(net_d) / gross_d
    return {"state_label": state_label, "nav": nav, "gross": gross_d / nav, "gross_dollars": gross_d,
            "net_fraction_of_gross": net, "per_name": per_name, "sector_gross": sector_gross,
            "sector_net": sector_net, "signed_beta_numerator": beta_numer,
            "normalized_beta": normalized_beta, "cash": nav - gross_d,
            "empty": gross_d == 0.0}


def _subject_checks(snap: dict):
    """Yield (kind, subject, value, limit) for every hard-cap subject in a snapshot."""
    for sym, frac in snap["per_name"].items():
        yield ("SINGLE_NAME", sym, frac, POSITION_CAP_NAV)
    yield ("GROSS", "", snap["gross"], GROSS_MAX)
    for s, frac in snap["sector_gross"].items():
        yield ("SECTOR", f"gross:{s}", frac, SECTOR_GROSS_MAX)
    for s, frac in snap["sector_net"].items():
        yield ("SECTOR", f"net:{s}", frac, SECTOR_NET_MAX)
    if snap["normalized_beta"] != N_A_EMPTY:
        yield ("BETA", "", snap["normalized_beta"], BETA_MAX)


def worsened_or_new_violations(baseline: dict, book: dict, *, realized: bool = False) -> list:
    """Numeric grandfathering (Increment-3 v1.1 defect-1 ruling). A hard-cap breach in `book` is a
    violation ONLY when, relative to the pre-existing `baseline` (the held-only book), it is either
    NEW (baseline subject was <= limit) or WORSENED (book value strictly exceeds the baseline value).
    A subject that was already over its limit and is not worsened is grandfathered (PR-16). Comparisons
    use actual numeric values, never violation keys alone."""
    base = {(k, subj): val for k, subj, val, _ in _subject_checks(baseline)}
    pref = "REALIZED_" if realized else ""
    out = []
    for kind, subj, val, limit in _subject_checks(book):
        if val <= limit:
            continue
        prior = base.get((kind, subj), 0.0)
        if prior <= limit or val > prior:               # NEW breach, or WORSENED beyond the grandfathered value
            code = {"SINGLE_NAME": "SINGLE_NAME_CONSTRAINT", "GROSS": "GROSS_CONSTRAINT",
                    "SECTOR": "SECTOR_CONSTRAINT", "BETA": "BETA_CONSTRAINT"}[kind]
            detail = f"{subj}:{val}>{limit}(baseline {prior})" if subj else f"{val}>{limit}(baseline {prior})"
            out.append((f"INTEGRITY_STOP:{pref}{code}", detail))
    return out


def hard_cap_violations(snap: dict, *, realized: bool = False) -> list:
    """Return the list of (code, detail) hard-cap violations. With realized=True the codes are the
    distinct REALIZED_* integrity codes (RC-2)."""
    v = []
    pref = "REALIZED_" if realized else ""
    for sym, frac in snap["per_name"].items():
        if frac > POSITION_CAP_NAV:
            v.append((f"INTEGRITY_STOP:{pref}SINGLE_NAME_CONSTRAINT", f"{sym}:{frac}>{POSITION_CAP_NAV}"))
    if snap["gross"] > GROSS_MAX:
        v.append((f"INTEGRITY_STOP:{pref}GROSS_CONSTRAINT", f"{snap['gross']}>{GROSS_MAX}"))
    for s, frac in snap["sector_gross"].items():
        if frac > SECTOR_GROSS_MAX:
            v.append((f"INTEGRITY_STOP:{pref}SECTOR_CONSTRAINT", f"gross:{s}:{frac}>{SECTOR_GROSS_MAX}"))
    for s, frac in snap["sector_net"].items():
        if frac > SECTOR_NET_MAX:
            v.append((f"INTEGRITY_STOP:{pref}SECTOR_CONSTRAINT", f"net:{s}:{frac}>{SECTOR_NET_MAX}"))
    if snap["normalized_beta"] != N_A_EMPTY and snap["normalized_beta"] > BETA_MAX:
        v.append((f"INTEGRITY_STOP:{pref}BETA_CONSTRAINT", f"{snap['normalized_beta']}>{BETA_MAX}"))
    return v
