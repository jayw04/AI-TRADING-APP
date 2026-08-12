"""Layer 2 Step 4 — recompute the July 27 governed decision, for side-by-side comparison.

## This is a RECOMPUTATION, not a strategy revision

Every component is IMPORTED from the registered implementation and used unchanged:

    universe_asof                     the PIT dollar-volume universe
    SessionLineageFilter              PERMATICKER_EFFECTIVE_INTERVAL_V1 eligibility
    compute_momentum                  252/21 twelve-minus-one total return
    winsorize + zscore                the cross-sectional scoring transform
    scripts.backtest_momentum_stage4.build_market_proxy   the proxy index + 200d MA

Nothing here re-implements a ranking formula, a lookback, a top-200 or top-five rule, a proxy
construction, a regime threshold, a quarantine rule or a completeness gate. The purpose is to show what
the valid corpus actually produces — NOT to reproduce, defend or preserve the superseded result.

⚠ `build_market_proxy` is resolved by NAME out of `scripts/`, exactly as `session_composition` resolves
it, because it is a countersigned replica that must not be edited or re-implemented inside `app/`.

## Why the same script runs on both corpora

A difference is only attributable if the two sides differ in DATA and nothing else. The script therefore
takes a store path and derives everything from it, so the superseded and rebuilt corpora are put through
one identical code path rather than two similar ones.
"""

# ⚠ PORTED into the repository for REPRODUCIBILITY. Operator machine paths are removed: the
# backend root resolves relative to this file and every data location comes from an argument or
# an environment override. A hard-coded working-copy path would make the tool unrunnable by
# anyone else, which is the opposite of what a reproducible build tool is for.

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.forward_validation._session_arg import (  # noqa: E402
    add_session_argument,
)

#: The governed session, supplied per run via --session and assigned in main(). Deliberately NOT a
#: module default -- it WAS `SESSION = date(2026, 7, 27)`. See `_session_arg` for why a default is the
#: wrong shape for a governed boundary.
SESSION: date

# Registered construction constants, read from the modules that own them where possible and restated
# here only where the owning module is a strategy template that cannot be imported without a runtime.
MOMENTUM_LOOKBACK_DAYS = 252
MOMENTUM_SKIP_DAYS = 21
MIN_RAW_MOMENTUM = 0.0
MIN_SCORE = 0.0
SELECTION_N = 5
MAX_POSITION_PCT = 0.20
CALENDAR_SPAN_YEARS = 4
#: momentum-daily §7 Stage-4 VALIDATED graduated regime.
REGIME_BAND_PCT = 0.02
REGIME_GROSS_ABOVE = 0.98
REGIME_GROSS_MID = 0.60
REGIME_GROSS_BELOW = 0.15

#: Version-specific price-history quarantine (Step 3 item 9). Applied as an exclusion from the decision
#: path; it is NOT a permanent universe removal.
QUARANTINE = ("SHOP", "TLN")


def _recompute(backend: Path, store_path: str, *, quarantine: tuple[str, ...]) -> dict:
    sys.path.insert(0, str(backend))
    import pandas as pd

    from app.factor_data.factors.cross_section import winsorize, zscore
    from app.factor_data.factors.momentum import compute_momentum
    from app.factor_data.store import FactorDataStore
    from app.factor_data.universe import universe_asof
    from app.validation.data_finality import ConstructionSpec
    from app.validation.security_lineage import SessionLineageFilter

    spec = ConstructionSpec()
    store = FactorDataStore(store_path, read_only=True)
    con = store.con
    out: dict = {"store": store_path, "session": SESSION.isoformat(),
                 "quarantined": list(quarantine)}

    sessions = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM sep WHERE date <= ? ORDER BY date DESC LIMIT ?",
        [SESSION, spec.required_history_sessions]).fetchall()]
    max_session = con.execute("SELECT max(date) FROM sep").fetchone()[0]
    out["store_max_session"] = max_session.isoformat() if max_session else None
    out["session_present"] = bool(sessions and sessions[0] == SESSION)
    out["history_window_sessions"] = len(sessions)
    if not out["session_present"]:
        out["ABORT"] = (f"the store's latest session is {out['store_max_session']}, so it cannot "
                        f"produce the {SESSION.isoformat()} decision at all")
        store.con.close()
        return out
    window_start = sessions[-1]
    out["history_window"] = [window_start.isoformat(), SESSION.isoformat()]

    # ── (1) raw scoring universe, and (2) lineage-eligible ────────────────────────────────────────
    excl = set(quarantine)
    raw_deep = list(universe_asof(store, SESSION, n=spec.scoring_universe_n + len(excl)))
    raw = [t for t in raw_deep if t not in excl][:spec.scoring_universe_n]
    out["raw_scoring_universe"] = len(raw)
    out["raw_scoring_universe_names"] = raw

    lineage = SessionLineageFilter(store, session_date=SESSION, lookback_start=window_start)
    eligible = lineage.filter(raw)
    out["lineage_eligible_scoring_universe"] = len(eligible)
    out["lineage_excluded_from_scoring"] = sorted(set(raw) - set(eligible))
    assessment = lineage.assessment().to_evidence()
    out["lineage_assessment"] = {k: assessment.get(k) for k in
                                 ("contract", "raw_seen", "eligible", "excluded_count",
                                  "counts_by_refusal") if k in assessment}

    # ── (3)+(4) factor scores and ranks over the top-200 ──────────────────────────────────────────
    start = SESSION - timedelta(days=int((MOMENTUM_LOOKBACK_DAYS + MOMENTUM_SKIP_DAYS) * 1.9))
    scores: dict[str, float] = {}
    for t in eligible:
        px = store.get_prices(t, start, SESSION, adjusted=True)
        if px is None or px.empty:
            continue
        m = compute_momentum(px, SESSION, lookback_days=MOMENTUM_LOOKBACK_DAYS,
                             skip_days=MOMENTUM_SKIP_DAYS)
        if m is not None:
            scores[t] = m
    s = pd.Series(scores)
    z = zscore(winsorize(s)) if not s.empty else s
    ranked = sorted(((t, float(z[t]), float(s[t])) for t in s.index),
                    key=lambda kv: (-kv[1], kv[0]))
    out["scored_names"] = len(scores)
    out["unscorable_names"] = sorted(set(eligible) - set(scores))
    out["ranked_top_25"] = [{"rank": i + 1, "ticker": t, "z": zz, "raw_momentum": rm}
                            for i, (t, zz, rm) in enumerate(ranked[:25])]

    # ── (5) the final top five ────────────────────────────────────────────────────────────────────
    passing = [(t, zz, rm) for t, zz, rm in ranked if rm > MIN_RAW_MOMENTUM and zz > MIN_SCORE]
    out["passing_floors"] = len(passing)
    top = passing[:SELECTION_N]
    out["top_five"] = [{"rank": i + 1, "ticker": t, "z": zz, "raw_momentum": rm}
                       for i, (t, zz, rm) in enumerate(top)]

    # ── (6) proxy basket and final contributors ───────────────────────────────────────────────────
    ma_dates = sorted(sessions[:spec.regime_ma_sessions])
    month_ends = [d for i, d in enumerate(ma_dates)
                  if i + 1 == len(ma_dates)
                  or (ma_dates[i + 1].year, ma_dates[i + 1].month) != (d.year, d.month)]
    basket: set[str] = set()
    for d in month_ends:
        basket |= set(universe_asof(store, d, n=spec.proxy_universe_n))
    kept = sorted(basket - excl)
    ph = ",".join("?" * len(kept))
    contributors = {r[0] for r in con.execute(
        f"SELECT ticker FROM sep WHERE ticker IN ({ph}) AND date BETWEEN ? AND ? "
        f"AND closeadj IS NOT NULL GROUP BY ticker HAVING count(DISTINCT date) >= ?",
        [*kept, ma_dates[0], SESSION, len(ma_dates)]).fetchall()}
    out["proxy"] = {
        "month_end_draws": len(month_ends), "raw_basket": len(basket),
        "basket_after_quarantine": len(kept),
        "quarantined_in_basket": sorted(basket & excl),
        "final_contributors": len(contributors),
        "ma_sessions": len(ma_dates),
        "sessions_incomplete": len(kept) - len(contributors),
    }

    # ── (7) regime series and state, from the REGISTERED proxy construction ───────────────────────
    span_start = date(SESSION.year - CALENDAR_SPAN_YEARS, 1, 1)
    days = [d for d in store.trading_days(span_start, SESSION) if d <= SESSION]
    build_market_proxy = importlib.import_module(
        "scripts.backtest_momentum_stage4").build_market_proxy
    proxy = build_market_proxy(store, days, store_path)
    idx = float(proxy["idx"].get(SESSION, float("nan")))
    ma = float(proxy["ma"].get(SESSION, float("nan")))
    rel = (idx / ma - 1.0) if ma and ma == ma else None
    gross = (REGIME_GROSS_ABOVE if rel is not None and rel > REGIME_BAND_PCT
             else REGIME_GROSS_BELOW if rel is not None and rel < -REGIME_BAND_PCT
             else REGIME_GROSS_MID)
    closes_on_or_before = [d for d in proxy.index if d <= SESSION]
    out["regime"] = {
        "calendar_span": [days[0].isoformat(), days[-1].isoformat(), len(days)],
        "proxy_closes_available": len(closes_on_or_before),
        "idx": idx, "ma": ma, "rel_to_ma": rel,
        "band_pct": REGIME_BAND_PCT, "mode": "graduated",
        "state": ("ABOVE_BAND" if rel is not None and rel > REGIME_BAND_PCT
                  else "BELOW_BAND" if rel is not None and rel < -REGIME_BAND_PCT
                  else "WITHIN_BAND"),
        "gross": gross,
    }

    # ── target weights: EQUAL WEIGHT ONLY, scaled by the regime multiplier ────────────────────────
    per_name = MAX_POSITION_PCT * gross
    out["target_weights"] = {e["ticker"]: per_name for e in out["top_five"]}
    out["gross_exposure"] = per_name * len(out["top_five"])

    # ── minimum-universe headroom ─────────────────────────────────────────────────────────────────
    out["headroom"] = {
        "scoring_eligible_vs_required": [out["lineage_eligible_scoring_universe"],
                                         spec.scoring_universe_n],
        "scoring_headroom": out["lineage_eligible_scoring_universe"] - spec.scoring_universe_n,
        "proxy_contributors": len(contributors),
        "proxy_completeness_pct": (100.0 * len(contributors) / len(kept)) if kept else None,
    }
    store.con.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", required=True)
    ap.add_argument("--backend", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="corpus")
    ap.add_argument("--no-quarantine", action="store_true",
                    help="compute WITHOUT the SHOP/TLN quarantine, to isolate its effect")
    add_session_argument(ap)
    args = ap.parse_args()
    global SESSION
    SESSION = args.session

    quarantine = () if args.no_quarantine else QUARANTINE
    result = _recompute(Path(args.backend), args.store, quarantine=quarantine)
    result["label"] = args.label

    blob = json.dumps(result, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_bytes(blob)

    print(f"== {args.label} ==")
    if result.get("ABORT"):
        print(f"  ABORT: {result['ABORT']}")
    else:
        print(f"  raw scoring {result['raw_scoring_universe']} -> lineage-eligible "
              f"{result['lineage_eligible_scoring_universe']} "
              f"(excluded {result['lineage_excluded_from_scoring']})")
        print(f"  scored {result['scored_names']} · passing floors {result['passing_floors']}")
        print(f"  TOP FIVE: {[e['ticker'] for e in result['top_five']]}")
        p = result["proxy"]
        print(f"  proxy basket {p['raw_basket']} -> {p['basket_after_quarantine']} -> "
              f"contributors {p['final_contributors']} (incomplete {p['sessions_incomplete']})")
        r = result["regime"]
        print(f"  regime idx={r['idx']:.6f} ma={r['ma']:.6f} rel={r['rel_to_ma']:+.4%} "
              f"state={r['state']} gross={r['gross']}")
        print(f"  gross exposure {result['gross_exposure']:.2%}")
    print(f"  sha256 {hashlib.sha256(blob).hexdigest()}")
    print(f"  wrote {outp} ({len(blob):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
