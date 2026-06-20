"""Operational feature registry (P11 §1, ADR 0021).

The single, static source of truth for *what operational features exist and how to tell
if one is on* — the overlays, the continuous breaker monitor, the strategy sector cap.
Lives in code (not the DB) so it cannot silently drift from the implementation; a
registry-integrity test pins ``enable_flag`` to real strategy params.

``verified`` is a **curated** field — the promotion-backtest verdict is a human research
decision, not a runtime fact — kept in sync with the P10 roadmap's Implemented-vs-Proven
table (e.g. the §5 regime overlays carry ``no_go``).
"""

from __future__ import annotations

from dataclasses import dataclass

# Allowed promotion-backtest verdicts (ADR 0014/0022 §7).
VERIFIED_VALUES = frozenset({"validated", "pending", "no_go", "n_a"})

# Coarse owning-domain categories (P11 §2 review) — for filtering + dashboard grouping.
CATEGORY_VALUES = frozenset({"research", "portfolio", "risk", "operations", "infrastructure"})


@dataclass(frozen=True)
class OperationalFeature:
    key: str                 # stable id, e.g. "daily_overlay"
    title: str               # human label
    kind: str                # "overlay" | "monitor" | "selection" | "infra"
    governing_adr: str       # "ADR 0020"
    enable_flag: str | None  # strategy param that turns it on; None = infra/always-on
    verified: str            # one of VERIFIED_VALUES (promotion-backtest outcome)
    note: str = ""
    category: str = "operations"  # one of CATEGORY_VALUES (P11 §2)


# Infra actors have no per-strategy flag; they are "enabled" iff their scheduler job is
# registered. Maps feature.key → APScheduler job id (P11 §1).
INFRA_JOB_IDS: dict[str, str] = {
    "breaker_monitor": "breaker_monitor",
}


FEATURES: tuple[OperationalFeature, ...] = (
    OperationalFeature(
        "vol_target", "Vol-target overlay (§1)", "overlay", "ADR 0014/0020",
        "use_vol_scaling", "validated",
        "walk-forward across regimes; a drawdown tool, not a Sharpe booster",
        category="portfolio"),
    OperationalFeature(
        "daily_overlay", "Daily gross-exposure overlay (§2)", "overlay", "ADR 0020",
        "use_daily_overlay", "pending", "needs promotion backtest before enabling",
        category="portfolio"),
    OperationalFeature(
        "exposure_smoothing", "Exposure smoothing (§4)", "overlay", "ADR 0020",
        "overlay_gross_smooth_span", "pending", "None/0 = off",
        category="portfolio"),
    OperationalFeature(
        "breadth_overlay", "Breadth regime overlay (§5)", "overlay", "ADR 0022",
        "use_breadth_overlay", "no_go", "promotion backtest NO-GO; stays off",
        category="portfolio"),
    OperationalFeature(
        "vix_overlay", "VIX regime overlay (§5)", "overlay", "ADR 0022",
        "use_vix_overlay", "no_go", "promotion backtest NO-GO; stays off",
        category="portfolio"),
    OperationalFeature(
        "sector_cap", "Strategy sector cap (§3)", "selection", "ADR 0018",
        "max_sector_pct", "n_a", "None = off (a selection screen, not a backtested overlay)",
        category="portfolio"),
    OperationalFeature(
        "breaker_monitor", "Continuous breaker monitor (§6)", "monitor", "ADR 0021/0004",
        None, "validated", "60s lifespan job; infra, no per-strategy flag",
        category="risk"),
)
