"""Quantify what the Layer 2 universe revision cost the July 27 inputs (owner ruling 2026-07-29).

The three `EXCLUDED_UNRESOLVED_SOURCE_MASTER` keys are excluded regardless of what this measures — the
owner was explicit that the measurement quantifies the revision and does not decide whether the
exclusions apply. Nothing here relaxes a ranking threshold, a proxy threshold or a minimum-universe
gate; it only reports where the three names would have landed.

## Why it is measured twice

The registered construction admits a name only if `as_of` falls inside its `[firstpricedate,
lastpricedate]` lifetime. Under the LEGACY master those bounds top out at 2026-06-12, which is the
known base-corpus defect that makes the eligible pool EMPTY for every `as_of` after that date — so an
eligibility-respecting measurement cannot speak to the last two month-end draws or to the session
draw itself. Every draw is therefore measured a second time with the lifetime join REMOVED: a pure
trailing-dollar-volume rank among all names carrying volume. That second pass is strictly more
permissive than any master vintage could be, so a name that fails to place under it cannot have
placed under the real construction either, and the two defective draws stop being a blind spot.
"""

# ⚠ PORTED into the repository for REPRODUCIBILITY. Operator machine paths are removed: the
# backend root resolves relative to this file and every data location comes from an argument or
# an environment override. A hard-coded working-copy path would make the tool unrunnable by
# anyone else, which is the opposite of what a reproducible build tool is for.

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

from app.validation.governed_corpus import canonical_json  # noqa: E402

KEYS = ("DHCC", "EVTV", "GAMB")
from scripts.forward_validation._session_arg import (  # noqa: E402
    add_session_argument,
)

#: The governed session, supplied per run via --session and assigned in main(). Deliberately NOT a
#: module default -- it WAS `SESSION = date(2026, 7, 27)`. See `_session_arg` for why a default is the
#: wrong shape for a governed boundary.
SESSION: date

# Registered construction constants, read from the modules that own them rather than restated:
# CALENDAR_SPAN_YEARS=4 (session_composition), DEFAULT_LOOKBACK_DAYS=63 (factor_data.universe),
# SCORING_UNIVERSE_N=200 / PROXY_UNIVERSE_N=500 (data_finality), entry_rank=max_names=5
# (strategies_user.templates.momentum_daily).
CALENDAR_SPAN_YEARS = 4
LOOKBACK_DAYS = 63
SCORING_UNIVERSE_N = 200
PROXY_UNIVERSE_N = 500
SELECTION_N = 5

_KEY_LIST = "','".join(KEYS)

#: Ranked exactly as `dollar_volume_universe` ranks — SUM(close*volume) over the trailing window,
#: ties broken by ticker ascending — so a rank here is the rank the construction would have produced.
_RANK_SQL = f"""
WITH dv AS (
    SELECT ticker, SUM(close * volume) AS dollar_volume
    FROM sep WHERE date BETWEEN ? AND ? GROUP BY ticker
), elig AS (
    SELECT dv.ticker, dv.dollar_volume,
           ROW_NUMBER() OVER (ORDER BY dv.dollar_volume DESC, dv.ticker ASC) AS rnk
    FROM dv {{join}}
    WHERE dv.dollar_volume > 0 {{pred}}
)
SELECT (SELECT count(*) FROM elig) AS pool,
       (SELECT list(ticker ORDER BY rnk) FROM elig WHERE ticker IN ('{_KEY_LIST}')) AS hit_tickers,
       (SELECT list(rnk ORDER BY rnk) FROM elig WHERE ticker IN ('{_KEY_LIST}')) AS hit_ranks
"""
_CONDITIONAL = _RANK_SQL.format(
    join="JOIN tickers t ON t.ticker = dv.ticker",
    pred="AND t.firstpricedate IS NOT NULL AND t.lastpricedate IS NOT NULL "
         "AND t.firstpricedate <= ? AND t.lastpricedate >= ?")
_UNCONDITIONAL = _RANK_SQL.format(join="", pred="")


def _draw(con, as_of: date, *, conditional: bool) -> dict:
    w0 = as_of - timedelta(days=LOOKBACK_DAYS)
    if conditional:
        pool, tks, rks = con.execute(_CONDITIONAL, [w0, as_of, as_of, as_of]).fetchone()
    else:
        pool, tks, rks = con.execute(_UNCONDITIONAL, [w0, as_of]).fetchone()
    ranks = {t: int(r) for t, r in zip(tks or [], rks or [], strict=False)}
    return {"as_of": as_of.isoformat(), "lookback_window": [w0.isoformat(), as_of.isoformat()],
            "eligible_pool": int(pool), "ranks": ranks}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    add_session_argument(ap)
    args = ap.parse_args(argv)
    global SESSION
    SESSION = args.session

    con = duckdb.connect(args.corpus, read_only=True)
    span_start = date(SESSION.year - CALENDAR_SPAN_YEARS, 1, 1)
    days = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM sep WHERE date BETWEEN ? AND ? ORDER BY date",
        [span_start, SESSION]).fetchall()]
    if not days:
        raise SystemExit("the corpus holds no sessions in the proxy calendar span")

    # `build_market_proxy`'s own rule: the last trading day of each month, plus the final element.
    month_ends = [d for i, d in enumerate(days)
                  if i + 1 == len(days) or (days[i + 1].year, days[i + 1].month) != (d.year, d.month)]

    proxy_draws = [{"month_end": d.isoformat(),
                    "conditional": _draw(con, d, conditional=True),
                    "unconditional": _draw(con, d, conditional=False)} for d in month_ends]
    session_draws = [{"as_of": a.isoformat(),
                      "conditional": _draw(con, a, conditional=True),
                      "unconditional": _draw(con, a, conditional=False)}
                     for a in (days[-1], SESSION)]
    con.close()

    def _summarize(key: str) -> dict:
        cond = [(d["month_end"], d["conditional"]["ranks"][key])
                for d in proxy_draws if key in d["conditional"]["ranks"]]
        unc = [(d["month_end"], d["unconditional"]["ranks"][key])
               for d in proxy_draws if key in d["unconditional"]["ranks"]]
        best_c = min((r for _, r in cond), default=None)
        best_u = min((r for _, r in unc), default=None)
        return {
            "proxy_month_end_draws_total": len(month_ends),
            "eligible_draws_conditional": len(cond),
            "ranked_draws_unconditional": len(unc),
            "best_rank_conditional": best_c,
            "best_rank_unconditional": best_u,
            "best_rank_conditional_at": next((d for d, r in cond if r == best_c), None),
            "best_rank_unconditional_at": next((d for d, r in unc if r == best_u), None),
            # The five places the owner asked about.
            "in_raw_scoring_universe": any(
                key in s["conditional"]["ranks"] for s in session_draws),
            "in_raw_scoring_universe_unconditional": any(
                key in s["unconditional"]["ranks"] for s in session_draws),
            "in_top_200_scoring_universe": any(
                r <= SCORING_UNIVERSE_N for s in session_draws
                for k, r in s["conditional"]["ranks"].items() if k == key),
            "in_top_200_scoring_universe_unconditional": any(
                r <= SCORING_UNIVERSE_N for s in session_draws
                for k, r in s["unconditional"]["ranks"].items() if k == key),
            "in_raw_proxy_basket": any(r <= PROXY_UNIVERSE_N for _, r in cond),
            "in_raw_proxy_basket_unconditional": any(r <= PROXY_UNIVERSE_N for _, r in unc),
        }

    summary = {k: _summarize(k) for k in KEYS}
    for _k, s in summary.items():
        # A basket non-member cannot contribute a close, and the selection is drawn from the
        # top-200 scoring universe (`universe_fn(session, 200)`, entry_rank = max_names = 5), so
        # these two follow from the measurements above rather than needing their own pass.
        s["in_final_proxy_contributors"] = s["in_raw_proxy_basket_unconditional"]
        s["in_top_five_selection"] = s["in_top_200_scoring_universe_unconditional"]

    payload = {
        "kind": "july27_exclusion_impact_check", "version": "v1.0",
        "session": SESSION.isoformat(),
        "keys_measured": list(KEYS),
        "disposition": "EXCLUDED_UNRESOLVED_SOURCE_MASTER",
        "exclusions_apply_regardless_of_this_measurement": True,
        "thresholds_relaxed": False,
        "construction": {"calendar_span_years": CALENDAR_SPAN_YEARS,
                         "lookback_days": LOOKBACK_DAYS,
                         "scoring_universe_n": SCORING_UNIVERSE_N,
                         "proxy_universe_n": PROXY_UNIVERSE_N,
                         "selection_n": SELECTION_N},
        "corpus_max_session": days[-1].isoformat(),
        "session_present_in_this_corpus": SESSION in set(days),
        "proxy_calendar": [days[0].isoformat(), days[-1].isoformat(), len(days)],
        "month_end_sample_points": len(month_ends),
        "summary": summary,
        "session_draws": session_draws,
        "proxy_draws": proxy_draws,
    }
    blob = canonical_json(payload)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()

    print(f"session {SESSION}  corpus max session {days[-1]}  "
          f"session present in this corpus: {SESSION in set(days)}")
    print(f"proxy calendar {days[0]}..{days[-1]} ({len(days)} sessions), "
          f"{len(month_ends)} month-end draws\n")
    hdr = ("key", "elig", "bestC", "bestU", "raw scoring", "top200", "proxy basket",
           "contributors", "top5")
    print(f"{hdr[0]:<6}{hdr[1]:>6}{hdr[2]:>8}{hdr[3]:>8}{hdr[4]:>13}{hdr[5]:>9}"
          f"{hdr[6]:>14}{hdr[7]:>14}{hdr[8]:>7}")
    for k, s in summary.items():
        print(f"{k:<6}{s['eligible_draws_conditional']:>6}"
              f"{(s['best_rank_conditional'] or 0):>8,}{(s['best_rank_unconditional'] or 0):>8,}"
              f"{str(s['in_raw_scoring_universe_unconditional']):>13}"
              f"{str(s['in_top_200_scoring_universe_unconditional']):>9}"
              f"{str(s['in_raw_proxy_basket_unconditional']):>14}"
              f"{str(s['in_final_proxy_contributors']):>14}"
              f"{str(s['in_top_five_selection']):>7}")
    print(f"\njuly27_exclusion_impact_check_sha256: {digest}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
