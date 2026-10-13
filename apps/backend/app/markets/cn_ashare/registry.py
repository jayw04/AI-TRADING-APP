"""Persistent China strategy registry.

Each row is a China strategy. ``CN-MOM-20D`` and ``CN-REV-5D`` keep the ids already stored on
research runs. They are not treated as the US momentum books. A US test or activation never
changes a China row's status. Rows that cannot be adapted yet stay ``BLOCKED`` with a reason.

``seed_registry`` inserts missing ids and does not update a row that is already stored.
"""

from __future__ import annotations

import json
from typing import Any

_NOT_ASSUMED = "NOT_ASSUMED"
_BLOCKED = "BLOCKED_INCOMPATIBLE"

# (id, family, version, name, hypothesis, signal, status, reason, us_id, us_version, code, equivalence, config)
_Row = tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    str | None,
    int | None,
    str | None,
    str | None,
    str,
    dict[str, Any],
]

SEED: tuple[_Row, ...] = (
    (
        "CN-MOM-20D",
        "cn_cross_section",
        "0.1.0",
        "20-day momentum, monthly",
        "Main-board stocks with the strongest 20-day adjusted return keep outperforming over the next month. This is not the US momentum-daily or momentum-portfolio book.",
        "HFQ close-to-close return over 20 trading days",
        "CANDIDATE",
        None,
        None,
        None,
        None,
        _NOT_ASSUMED,
        {
            "lookback_days": 20,
            "direction": "high",
            "top_k": 5,
            "rebalance": "last trading day of each month; fill at the next open",
        },
    ),
    (
        "CN-REV-5D",
        "cn_cross_section",
        "0.1.0",
        "5-day reversal, monthly",
        "Main-board stocks with the weakest 5-day adjusted return rebound over the next month. This is not a US strategy.",
        "HFQ close-to-close return over 5 trading days",
        "CANDIDATE",
        None,
        None,
        None,
        None,
        _NOT_ASSUMED,
        {
            "lookback_days": 5,
            "direction": "low",
            "top_k": 5,
            "rebalance": "last trading day of each month; fill at the next open",
        },
    ),
    (
        "CN-MOM-PORTFOLIO",
        "momentum_portfolio",
        "0.1.0",
        "China counterpart of US momentum portfolio",
        "US momentum-portfolio ranks a Sharadar point-in-time universe with 12-1 momentum and submits through the US order path. No China counterpart of that universe is in the A-share store.",
        "Not adapted",
        "BLOCKED",
        "Needs a China point-in-time universe and the same 12-1 score. CN-MOM-20D is a different rule and is not this strategy.",
        None,
        None,
        "templates/momentum_portfolio.py",
        _BLOCKED,
        {},
    ),
    (
        "CN-MOM-DAILY",
        "momentum_daily",
        "0.1.0",
        "China counterpart of US momentum-daily",
        "US momentum-daily (strategy 11) evaluates a US factor book every day and trades only when one of six conditions fires.",
        "Not adapted",
        "BLOCKED",
        "The six US triggers read US factor scores and a US regime proxy. Daily A-share bars do not supply that state. CN-MOM-20D is not this strategy.",
        11,
        None,
        "templates/momentum_daily.py",
        _BLOCKED,
        {},
    ),
    (
        "CN-LOWVOL-W",
        "low_volatility",
        "0.1.0",
        "China counterpart of US low-volatility",
        "US low-volatility (strategy 8, template version 1.0.3) holds the lowest 252-day volatility quintile from the US factor store.",
        "Not adapted",
        "BLOCKED",
        "No China fundamental or point-in-time volatility universe is loaded. A US activation does not activate this row.",
        8,
        "1.0.3",
        "templates/low_volatility.py",
        _BLOCKED,
        {},
    ),
    (
        "CN-SECTOR-W",
        "sector_rotation",
        "0.1.0",
        "China counterpart of US sector rotation",
        "US sector rotation ranks US sectors by 12-month momentum and holds the top sectors.",
        "Not adapted",
        "BLOCKED",
        "No China sector membership or sector index history is in the A-share store.",
        None,
        None,
        "templates/sector_rotation.py",
        _BLOCKED,
        {},
    ),
    (
        "CN-COMB-V13",
        "combined_book",
        "0.1.0",
        "China counterpart of US combined book",
        "US combined-book (strategy 9, combined_book_v13.py 1.4.0) blends a US equity momentum sleeve with a 9-ETF cross-asset sleeve.",
        "Not adapted",
        "BLOCKED",
        "The ETF sleeve and the US factor scores have no China counterpart. The US book being idle or previously on paper does not qualify this row.",
        9,
        "1.4.0",
        "templates/combined_book_v13.py",
        _BLOCKED,
        {},
    ),
    (
        "CN-RANGE-ORB",
        "range",
        "0.1.0",
        "China opening-range candidate",
        "A China range candidate, separate from the US RANGE program and from RANGE-002. The US template fades an intraday range and force-exits before the US close.",
        "Not adapted",
        "BLOCKED",
        "US range_trader.py uses intraday bars and a same-day exit. Main-board A-shares are T+1 for sells, and this store has daily bars only. A daily adaptation needs its own version; this row is not that version.",
        None,
        None,
        "templates/range_trader.py",
        _BLOCKED,
        {},
    ),
    (
        "CN-RANGE-VWAP",
        "range_vwap",
        "0.1.0",
        "China counterpart of US VWAP range",
        "US range_trader_vwap.py fades a session VWAP band and can re-enter the same day.",
        "Not adapted",
        "BLOCKED",
        "Session VWAP needs intraday bars. Same-day re-entry is not a main-board A-share sell. This is not CN-RANGE-ORB and not the US RANGE program.",
        None,
        None,
        "templates/range_trader_vwap.py",
        _BLOCKED,
        {},
    ),
)


def seed_registry(con: Any) -> None:
    """Insert any seed id that is not already stored. Existing rows are left as they are."""
    for order, row in enumerate(SEED):
        (
            cn_id,
            family,
            version,
            name,
            hypothesis,
            signal,
            status,
            reason,
            us_id,
            us_version,
            code,
            equivalence,
            config,
        ) = row
        con.execute(
            """
            INSERT INTO cn_strategies VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT (cn_strategy_id) DO NOTHING
            """,
            [
                cn_id,
                order,
                family,
                version,
                name,
                hypothesis,
                signal,
                status,
                reason,
                us_id,
                us_version,
                code,
                equivalence,
                json.dumps(config, sort_keys=True, separators=(",", ":")),
                "1970-01-01T00:00:00Z",
            ],
        )


def catalog() -> list[dict[str, Any]]:
    """The seed list, used when a store has no registry table yet."""
    out = []
    for order, row in enumerate(SEED):
        (
            cn_id,
            family,
            version,
            name,
            hypothesis,
            signal,
            status,
            reason,
            us_id,
            us_version,
            code,
            equivalence,
            config,
        ) = row
        out.append(
            {
                "cn_strategy_id": cn_id,
                "sort_order": order,
                "family": family,
                "version": version,
                "name": name,
                "hypothesis": hypothesis,
                "signal": signal,
                "status": status,
                "blocked_reason": reason,
                "source_us_strategy_id": us_id,
                "source_us_version": us_version,
                "source_us_code_path": code,
                "equivalence": equivalence,
                "config": config,
            }
        )
    return out


def to_candidate(row: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = row.get("config") or {}
    mine = [r for r in runs if r["candidate_id"] == row["cn_strategy_id"]]
    last = mine[0] if mine else None
    return {
        "candidate_id": row["cn_strategy_id"],
        "name": row["name"],
        "hypothesis": row["hypothesis"],
        "signal": row["signal"],
        "lookback_days": cfg.get("lookback_days"),
        "direction": cfg.get("direction") or "",
        "top_k": cfg.get("top_k") or 0,
        "rebalance": cfg.get("rebalance") or "",
        "status": row["status"],
        "family": row["family"],
        "version": row["version"],
        "blocked_reason": row["blocked_reason"],
        "source_us_strategy_id": row["source_us_strategy_id"],
        "source_us_version": row["source_us_version"],
        "source_us_code_path": row["source_us_code_path"],
        "equivalence": row["equivalence"],
        "run_count": len(mine),
        "last_run": None
        if last is None
        else {
            "run_id": last["run_id"],
            "created_at_utc": last["created_at_utc"],
            "sample_label": last["sample_label"],
        },
    }
