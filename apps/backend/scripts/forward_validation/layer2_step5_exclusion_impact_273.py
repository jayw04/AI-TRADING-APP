"""Layer 2 Step 5 — the EXACT 273-session exclusion-impact re-check.

## Why this had to be redone

The ratified July-27 impact check was anchored on a corpus whose latest session was 2026-07-24, so it
measured **272** of the governed window's 273 sessions and could not speak to the session draw itself.
It also covered only the three `EXCLUDED_UNRESOLVED_SOURCE_MASTER` keys. This re-check uses the exact
273-session window ending on the session, and covers **every** excluded identity.

## Where it must run, and why

The excluded identities are ABSENT from the rebuilt corpus by construction, so their rank cannot be
measured there — asking "where would DHCC have placed?" of a corpus that does not contain DHCC is not a
question with an answer. The measurement therefore runs against the SUPERSEDED corpus, which still
holds all seven, using the governed window and the registered ranking.

## Measured twice, for a reason that is not redundancy

  CONDITIONAL   respects the registered PIT lifetime rule (`firstpricedate <= as_of <= lastpricedate`).
  UNCONDITIONAL removes the lifetime join entirely — a pure trailing-dollar-volume rank among all names
                carrying volume.

The unconditional pass is STRICTLY MORE PERMISSIVE than any master vintage could be, so a name that
fails to place under it cannot have placed under the real construction. That closes the blind spot the
legacy master's defective lifetime bounds would otherwise leave.

⛔ Nothing here relaxes a ranking threshold, a proxy threshold or a minimum-universe gate. The
exclusions apply regardless of what this measures; the measurement quantifies the revision.
"""

# ⚠ PORTED into the repository for REPRODUCIBILITY. Operator machine paths are removed: the
# backend root resolves relative to this file and every data location comes from an argument or
# an environment override. A hard-coded working-copy path would make the tool unrunnable by
# anyone else, which is the opposite of what a reproducible build tool is for.

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.forward_validation._governed_window import (  # noqa: E402
    REQUIRED_HISTORY_SESSIONS as _REQUIRED_HISTORY_SESSIONS,
)
from scripts.forward_validation._session_arg import (  # noqa: E402
    add_session_argument,
)

#: The governed session, supplied per run via --session and assigned in main(). Deliberately NOT a
#: module default -- it WAS `SESSION = date(2026, 7, 27)`. See `_session_arg` for why a default is the
#: wrong shape for a governed boundary.
SESSION: date

#: Every identity the rebuilt corpus excludes, with the class that excluded it.
EXCLUDED = {
    "DHCC": "EXCLUDED_UNRESOLVED_SOURCE_MASTER",
    "EVTV": "EXCLUDED_UNRESOLVED_SOURCE_MASTER",
    "GAMB": "EXCLUDED_UNRESOLVED_SOURCE_MASTER",
    "MRXLY": "EXCLUDED_DOCUMENTED_HISTORICAL_DELISTING",
    "PGIE": "EXCLUDED_DOCUMENTED_HISTORICAL_DELISTING",
    "OCCI": "EXCLUDED_NO_AUTHORITATIVE_SEP_PRICE_COVERAGE",
    "HYPG": "EXCLUDED_NO_AUTHORITATIVE_SEP_PRICE_COVERAGE",
}
#: Version-specific price-history QUARANTINE — a different question from exclusion.
#:
#: ⚠ These are EXPECTED to place: SHOP is a large-cap and ranks inside the top-200. Placing is not a
#: failure for a quarantined name, because the quarantine WITHHOLDS the history from the decision path
#: rather than claiming the name was never relevant. What must hold is that withholding them changes
#: no decision — which Step 4 measured directly (top five, weights and regime identical with and
#: without). Measuring them here puts that on the same 273-session footing as the exclusions.
QUARANTINED = {
    "SHOP": "UNEXPLAINED_VENDOR_ADJUSTMENT_ANOMALY",
    "TLN": "UNEXPLAINED_VENDOR_ADJUSTMENT_ANOMALY",
}

#: Reinstated before countersignature — measured too, to CONFIRM they are price-bearing rather than
#: assumed. ⚠ In a permaticker-keyed corpus these carry SUCCESSOR symbols (VYNE→YARW, LTGRU→LTGR), so
#: a by-ticker presence test is the wrong test and reports a false zero.
REINSTATED = {"VYNE": "120814", "LTGRU": "6399330"}

#: Imported, not redeclared: `build_universe_crosswalk` derives the SAME window from the same rule,
#: and two copies of the length are two things that can drift. Step 5's own failure semantics are
#: unchanged — it records an ABORT artifact rather than raising, because a short window here is
#: evidence about the corpus that the operator needs written down.
REQUIRED_HISTORY_SESSIONS = _REQUIRED_HISTORY_SESSIONS
REGIME_MA_SESSIONS = 200
SCORING_UNIVERSE_N = 200
PROXY_UNIVERSE_N = 500
LOOKBACK_DAYS = 63
CALENDAR_SPAN_YEARS = 4

#: Every name measured — exclusions AND quarantines — so one ranking pass serves both categories.
_MEASURED = {**EXCLUDED, **QUARANTINED}
_KEYS = "','".join(_MEASURED)

_RANK_SQL = f"""
WITH dv AS (
    SELECT ticker, SUM("close" * volume) AS dollar_volume
    FROM sep WHERE date BETWEEN ? AND ? GROUP BY ticker
), elig AS (
    SELECT dv.ticker, dv.dollar_volume,
           ROW_NUMBER() OVER (ORDER BY dv.dollar_volume DESC, dv.ticker ASC) AS rnk
    FROM dv {{join}}
    WHERE dv.dollar_volume > 0 {{pred}}
)
SELECT (SELECT count(*) FROM elig) AS pool,
       (SELECT list(ticker ORDER BY rnk) FROM elig WHERE ticker IN ('{_KEYS}')) AS hit_t,
       (SELECT list(rnk ORDER BY rnk) FROM elig WHERE ticker IN ('{_KEYS}')) AS hit_r
"""
_COND = _RANK_SQL.format(join="JOIN tickers t ON t.ticker = dv.ticker",
                         pred="AND t.firstpricedate IS NOT NULL AND t.lastpricedate IS NOT NULL "
                              "AND t.firstpricedate <= ? AND t.lastpricedate >= ?")
_UNCOND = _RANK_SQL.format(join="", pred="")


def _draw(con, as_of: date, *, conditional: bool) -> dict:
    w0 = as_of - timedelta(days=LOOKBACK_DAYS)
    if conditional:
        pool, tks, rks = con.execute(_COND, [w0, as_of, as_of, as_of]).fetchone()
    else:
        pool, tks, rks = con.execute(_UNCOND, [w0, as_of]).fetchone()
    return {"as_of": as_of.isoformat(), "eligible_pool": int(pool),
            "ranks": {t: int(r) for t, r in zip(tks or [], rks or [], strict=False)}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", required=True)
    ap.add_argument("--out", required=True)
    add_session_argument(ap)
    args = ap.parse_args()
    global SESSION
    SESSION = args.session

    import duckdb

    con = duckdb.connect(args.store, read_only=True)

    # ── the EXACT governed window ────────────────────────────────────────────────────────────────
    window = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM sep WHERE date <= ? ORDER BY date DESC LIMIT ?",
        [SESSION, REQUIRED_HISTORY_SESSIONS]).fetchall()]
    window_sessions = sorted(window)
    exact = len(window_sessions) == REQUIRED_HISTORY_SESSIONS and window_sessions[-1] == SESSION
    ma_dates = window_sessions[-REGIME_MA_SESSIONS:]

    out: dict = {
        "kind": "layer2_step5_exclusion_impact_273", "version": "v1.0",
        "store": args.store, "session": SESSION.isoformat(),
        "window": [window_sessions[0].isoformat(), window_sessions[-1].isoformat()],
        "window_sessions": len(window_sessions),
        "required_history_sessions": REQUIRED_HISTORY_SESSIONS,
        "exact_273_session_window": exact,
        "session_present_in_store": window_sessions[-1] == SESSION,
        "thresholds_relaxed": False,
        "exclusions_apply_regardless_of_this_measurement": True,
    }
    if not exact:
        out["ABORT"] = (f"the store yields {len(window_sessions)} window sessions ending "
                        f"{window_sessions[-1]}; the exact 273-session check needs 273 ending "
                        f"{SESSION.isoformat()}")
        Path(args.out).write_bytes(json.dumps(out, sort_keys=True, default=str).encode())
        print(json.dumps(out, indent=2, default=str)[:1200])
        return 1

    # ── month-end draws: BOTH the finality MA-window set and build_market_proxy's 4-year set ─────
    def month_ends(days: list[date]) -> list[date]:
        return [d for i, d in enumerate(days)
                if i + 1 == len(days) or (days[i + 1].year, days[i + 1].month) != (d.year, d.month)]

    ma_month_ends = month_ends(ma_dates)
    span_start = date(SESSION.year - CALENDAR_SPAN_YEARS, 1, 1)
    span_days = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM sep WHERE date BETWEEN ? AND ? ORDER BY date",
        [span_start, SESSION]).fetchall()]
    proxy_month_ends = month_ends(span_days)

    out["draw_sets"] = {
        "finality_ma_window_month_ends": len(ma_month_ends),
        "build_market_proxy_4y_month_ends": len(proxy_month_ends),
        "ma_window": [ma_dates[0].isoformat(), ma_dates[-1].isoformat(), len(ma_dates)],
        "proxy_calendar": [span_days[0].isoformat(), span_days[-1].isoformat(), len(span_days)],
    }

    session_draws = {"conditional": _draw(con, SESSION, conditional=True),
                     "unconditional": _draw(con, SESSION, conditional=False)}
    ma_draws = [{"month_end": d.isoformat(),
                 "conditional": _draw(con, d, conditional=True),
                 "unconditional": _draw(con, d, conditional=False)} for d in ma_month_ends]
    proxy_draws = [{"month_end": d.isoformat(),
                    "conditional": _draw(con, d, conditional=True),
                    "unconditional": _draw(con, d, conditional=False)} for d in proxy_month_ends]

    # ── per-identity verdict, on the exact window ────────────────────────────────────────────────
    summary: dict = {}
    for key, klass in _MEASURED.items():
        rows, first, last = con.execute(
            "SELECT count(*), min(date), max(date) FROM sep WHERE ticker = ? "
            "AND date BETWEEN ? AND ?", [key, window_sessions[0], SESSION]).fetchone()
        complete_ma = con.execute(
            "SELECT count(DISTINCT date) FROM sep WHERE ticker = ? AND date BETWEEN ? AND ? "
            "AND closeadj IS NOT NULL", [key, ma_dates[0], SESSION]).fetchone()[0]

        # `key` is bound as a DEFAULT ARGUMENT, not captured: a closure over the loop variable would
        # read whatever `key` happened to be at call time, which is a real defect the moment this is
        # ever called after the loop rather than inside it.
        def best(draws, mode, key=key):
            hits = [(d["month_end"], d[mode]["ranks"][key])
                    for d in draws if key in d[mode]["ranks"]]
            return (min((r for _, r in hits), default=None), len(hits))

        best_ma_c, n_ma_c = best(ma_draws, "conditional")
        best_ma_u, n_ma_u = best(ma_draws, "unconditional")
        best_px_c, n_px_c = best(proxy_draws, "conditional")
        best_px_u, n_px_u = best(proxy_draws, "unconditional")
        sess_c = session_draws["conditional"]["ranks"].get(key)
        sess_u = session_draws["unconditional"]["ranks"].get(key)

        in_top200 = bool((sess_c and sess_c <= SCORING_UNIVERSE_N)
                         or (sess_u and sess_u <= SCORING_UNIVERSE_N))
        in_basket = bool((best_px_u is not None and best_px_u <= PROXY_UNIVERSE_N)
                         or (best_ma_u is not None and best_ma_u <= PROXY_UNIVERSE_N))
        summary[key] = {
            "category": "QUARANTINED" if key in QUARANTINED else "EXCLUDED",
            "exclusion_class": klass,
            # ⚠ The bar differs by category. An EXCLUDED identity must touch NOTHING — placing anywhere
            # would mean the revision cost the decision something. A QUARANTINED identity may place;
            # what must hold is that WITHHOLDING it changes no decision, which Step 4 measured.
            "placing_would_be_a_finding": key not in QUARANTINED,
            "rows_in_273_session_window": int(rows or 0),
            "first_in_window": first.isoformat() if first else None,
            "last_in_window": last.isoformat() if last else None,
            "ma_sessions_with_marks": int(complete_ma or 0),
            "ma_sessions_required": len(ma_dates),
            "session_rank_conditional": sess_c, "session_rank_unconditional": sess_u,
            "best_rank_ma_month_ends_conditional": best_ma_c,
            "best_rank_ma_month_ends_unconditional": best_ma_u,
            "best_rank_proxy_month_ends_conditional": best_px_c,
            "best_rank_proxy_month_ends_unconditional": best_px_u,
            "eligible_ma_draws_conditional": n_ma_c,
            "ranked_ma_draws_unconditional": n_ma_u,
            "eligible_proxy_draws_conditional": n_px_c,
            "ranked_proxy_draws_unconditional": n_px_u,
            # ⚠ "present in the ranked pool" is NOT "in the scoring universe". The pool is every name
            # with nonzero dollar volume (~5,800); the RAW SCORING UNIVERSE is the top-200 draw the
            # construction actually takes. Conflating them makes a name at rank 5,835 of 5,835 read as
            # touching the decision, which is meaningless.
            "present_in_ranked_pool": bool(sess_c or sess_u),
            # the six places the ruling asks about
            "in_raw_scoring_universe": in_top200,
            "in_top_200_scoring_universe": in_top200,
            "in_proxy_basket": in_basket,
            # a basket non-member contributes no close; a contributor also needs a COMPLETE MA history
            "in_final_proxy_contributors": bool(in_basket and complete_ma >= len(ma_dates)),
            # the selection is a strict subset of the top-200 (entry_rank = max_names = 5)
            "in_top_five": in_top200,
            "in_regime_inputs": in_basket,
        }

    # ── the reinstated pair, CONFIRMED price-bearing rather than assumed ─────────────────────────
    reinstated: dict = {}
    cols = {str(r[1]).lower() for r in con.execute("PRAGMA table_info('sep')").fetchall()}
    for legacy, perma in REINSTATED.items():
        rec: dict = {"legacy_key": legacy, "permaticker": perma}
        rec["rows_by_legacy_ticker"] = con.execute(
            "SELECT count(*) FROM sep WHERE ticker = ?", [legacy]).fetchone()[0]
        if "permaticker" in cols:
            r = con.execute("SELECT count(*), min(date), max(date), any_value(ticker) FROM sep "
                            "WHERE permaticker = ?", [perma]).fetchone()
            rec.update(rows_by_permaticker=int(r[0] or 0),
                       span=[r[1].isoformat() if r[1] else None,
                             r[2].isoformat() if r[2] else None],
                       current_ticker=r[3])
            rec["price_bearing_confirmed"] = int(r[0] or 0) > 0
            rec["note"] = ("a by-TICKER test reports a false zero: the lineage carries a SUCCESSOR "
                           "symbol in a permaticker-keyed corpus")
        else:
            rec["note"] = "this store has no sep.permaticker column; measured by ticker only"
        reinstated[legacy] = rec

    # ── the ACTUAL proxy basket membership, by name ──────────────────────────────────────────────
    #
    # Recorded so a basket-size difference between corpora can be ATTRIBUTED by diffing the name sets
    # rather than inferred from which identities were excluded. Those are different questions: an
    # excluded identity that never ranked inside the top-500 cannot be the cause of a basket change,
    # and assuming otherwise produces a confident wrong answer.
    basket: set[str] = set()
    for d in ma_month_ends:
        w0 = d - timedelta(days=LOOKBACK_DAYS)
        names = con.execute(
            "WITH dv AS (SELECT ticker, SUM(\"close\"*volume) v FROM sep "
            "WHERE date BETWEEN ? AND ? GROUP BY 1) "
            "SELECT ticker FROM dv WHERE v > 0 "
            "ORDER BY v DESC, ticker ASC LIMIT ?", [w0, d, PROXY_UNIVERSE_N]).fetchall()
        basket |= {r[0] for r in names}
    out["proxy_basket_membership"] = {
        "month_ends_used": len(ma_month_ends), "n_per_draw": PROXY_UNIVERSE_N,
        "basket_size": len(basket), "names": sorted(basket),
        "note": "union of the MA-window month-end top-500 draws, unconditional (no lifetime join), "
                "recorded by NAME so a cross-corpus basket difference can be diffed rather than "
                "attributed by assumption",
    }

    out["summary"] = summary
    out["reinstated"] = reinstated
    out["session_draws"] = session_draws
    out["ma_month_end_draws"] = ma_draws
    out["proxy_month_end_draws"] = proxy_draws
    def _touches(v: dict) -> bool:
        return bool(v["in_raw_scoring_universe"] or v["in_top_200_scoring_universe"]
                    or v["in_proxy_basket"] or v["in_final_proxy_contributors"]
                    or v["in_top_five"] or v["in_regime_inputs"])

    excluded_touching = sorted(k for k, v in summary.items()
                               if v["category"] == "EXCLUDED" and _touches(v))
    quarantined_touching = sorted(k for k, v in summary.items()
                                  if v["category"] == "QUARANTINED" and _touches(v))
    out["excluded_identities_touching_the_july27_decision"] = excluded_touching
    out["quarantined_identities_that_would_have_placed"] = quarantined_touching
    out["exclusions_cost_the_july27_decision_nothing"] = not excluded_touching
    out["quarantine_effect_measured_in_step4"] = {
        "artifact": "step4_comparison.json",
        "top_five": "UNCHANGED with and without the quarantine",
        "proxy_basket": "689 -> 687", "contributors": "663 -> 661",
        "regime": "IDENTICAL (+12.3491%, ABOVE_BAND, gross 0.98)",
        "note": "a quarantined name MAY place; what matters is that withholding it changes no "
                "decision, which Step 4 measured directly rather than inferred",
    }
    # ── headroom, stated so it cannot be misread ────────────────────────────────────────────────
    #
    # ⚠ "headroom 0" in the Step-4 table means the CONFIGURED SCORING UNIVERSE IS EXACTLY FILLED at
    # 200 — NOT that the strategy scraped through on a fragile five-name pass. The selection draws 5
    # from those 200, so the selection headroom is 195.
    out["headroom_clarified"] = {
        "scoring_universe_eligible": SCORING_UNIVERSE_N,
        "scoring_universe_configured": SCORING_UNIVERSE_N,
        "scoring_universe_fill": "EXACTLY FILLED (200/200)",
        "top_five_capacity": 5,
        "selection_headroom_names": SCORING_UNIVERSE_N - 5,
        "reading": "the configured scoring universe is exactly filled at 200; the selection takes 5 "
                   "of those 200, leaving 195 names of selection headroom. 'headroom 0' refers to "
                   "universe FILL, not to selection fragility.",
    }
    con.close()

    blob = json.dumps(out, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_bytes(blob)

    print(f"window {out['window'][0]}..{out['window'][1]}  sessions={out['window_sessions']}  "
          f"EXACT 273 = {exact}")
    print(f"MA-window month-ends {len(ma_month_ends)} · proxy 4y month-ends {len(proxy_month_ends)}")
    print(f"session pool: conditional {session_draws['conditional']['eligible_pool']:,} · "
          f"unconditional {session_draws['unconditional']['eligible_pool']:,}\n")
    h = (f"{'key':<7}{'cat':<11}{'rows':>6}{'sessRkC':>9}{'sessRkU':>9}"
         f"{'bestPxU':>9}{'top200':>8}{'basket':>8}{'contrib':>9}{'top5':>6}{'regime':>8}")
    print(h)
    print("-" * len(h))
    for k, v in summary.items():
        print(f"{k:<7}{v['category']:<11}{v['rows_in_273_session_window']:>6}"
              f"{str(v['session_rank_conditional']):>9}{str(v['session_rank_unconditional']):>9}"
              f"{str(v['best_rank_proxy_month_ends_unconditional']):>9}"
              f"{str(v['in_top_200_scoring_universe']):>8}{str(v['in_proxy_basket']):>8}"
              f"{str(v['in_final_proxy_contributors']):>9}{str(v['in_top_five']):>6}"
              f"{str(v['in_regime_inputs']):>8}")
    print("\nexclusion classes:")
    for k, v in summary.items():
        if v["category"] == "EXCLUDED":
            print(f"  {k:<7}{v['exclusion_class']}")
    print("\nreinstated successor identities (must be PRICE-BEARING):")
    for k, v in reinstated.items():
        print(f"  {k:<6} perma={v['permaticker']:<9} by_ticker={v['rows_by_legacy_ticker']:<6} "
              f"by_permaticker={v.get('rows_by_permaticker','n/a')} "
              f"current={v.get('current_ticker')} confirmed={v.get('price_bearing_confirmed')}")
    print(f"\nEXCLUDED identities touching the July 27 decision : {excluded_touching or 'NONE'}")
    print(f"QUARANTINED identities that would have placed     : "
          f"{quarantined_touching or 'NONE'}  (expected; Step 4 proved no decision change)")
    print(f"EXCLUSIONS COST THE JULY 27 DECISION NOTHING      : {not excluded_touching}")
    print(f"step5_exclusion_impact_273_sha256: {hashlib.sha256(blob).hexdigest()}")
    print(f"wrote {args.out} ({len(blob):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
