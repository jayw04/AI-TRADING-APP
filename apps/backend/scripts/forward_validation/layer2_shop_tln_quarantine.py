"""Layer 2 Step 3 item 9 — quarantine the two UNEXPLAINED_VENDOR_ADJUSTMENT_ANOMALY histories and
measure what excluding them does to the July 27 decision.

## What is being quarantined, and what is emphatically NOT

SHOP and TLN each carry sessions where `closeadj` moves against `close` with **zero ACTIONS rows** to
explain it. These are genuine artifacts of the sealed vintage, not classification gaps: unlike the
spinoff and ADR-ratio cases in the same census, there is no declared action on the date at all.

This is a **VERSION-SPECIFIC PRICE-HISTORY QUARANTINE**, not a permanent universe removal. The
securities remain governed identities; what is withheld is *this vintage's* price history for them. If
a later vintage resolves the anomaly the quarantine lapses — nothing about the identity changed.

⛔ NO tolerance is widened and NO source row is edited. The anomaly is preserved verbatim in the
evidence; the only action taken is to exclude the affected securities from the consumed lookback and
then re-run every gate UNRELAXED.

## The decision rule the owner set

If either name reaches the TOP FIVE, or if removing them makes the proxy or the regime incomplete, then
**this vintage cannot support observation #1**. That is a property of the measurement, not a judgement
call, so it is computed and printed as a verdict rather than discussed.

## Why the top five must be RECOMPUTED rather than reasoned about

The selection is the highest-momentum names among the top-200 by trailing dollar volume. Removing a
name from the pool does not merely delete it from the ranking — it PROMOTES the name at rank 201 into
the scoring universe, and that promoted name can itself enter the top five. A "they weren't in the top
five, so nothing changes" argument is therefore unsound, and the whole selection is re-derived both
ways instead.
"""

# ⚠ PORTED into the repository for REPRODUCIBILITY. Operator machine paths are removed: the
# backend root resolves relative to this file and every data location comes from an argument or
# an environment override. A hard-coded working-copy path would make the tool unrunnable by
# anyone else, which is the opposite of what a reproducible build tool is for.

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.factor_data.factors.cross_section import winsorize, zscore  # noqa: E402
from app.factor_data.factors.momentum import compute_momentum  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402
from app.factor_data.universe import universe_asof  # noqa: E402
from app.validation.data_finality import ConstructionSpec  # noqa: E402
from app.validation.governed_corpus import canonical_json  # noqa: E402
from app.validation.security_lineage import SessionLineageFilter  # noqa: E402
from scripts.forward_validation._session_arg import (  # noqa: E402
    add_session_argument,
)

#: The governed session, supplied per run via --session and assigned in main(). Deliberately NOT a
#: module default -- it WAS `SESSION = date(2026, 7, 27)`. See `_session_arg` for why a default is the
#: wrong shape for a governed boundary.
SESSION: date

#: The anomalies as MEASURED by the Step-3 reconciliation on corpus-v2 — not as remembered.
QUARANTINE = {
    "SHOP": ["2025-06-26", "2025-06-27"],
    "TLN": ["2026-02-02", "2026-02-03"],
}
DISPOSITION = "UNEXPLAINED_VENDOR_ADJUSTMENT_ANOMALY"

# Registered construction constants (momentum-daily params_schema + data_finality spec).
MOMENTUM_LOOKBACK_DAYS = 252
MOMENTUM_SKIP_DAYS = 21
MIN_RAW_MOMENTUM = 0.0
MIN_SCORE = 0.0
SELECTION_N = 5

NDL_SEP = "https://data.nasdaq.com/api/v3/datatables/SHARADAR/SEP"


def _anomaly_record(con, ticker: str, sessions: list[str]) -> dict:
    """The raw rows around each anomalous session, preserved verbatim, plus both factor ratios."""
    lo = min(date.fromisoformat(s) for s in sessions) - timedelta(days=7)
    hi = max(date.fromisoformat(s) for s in sessions) + timedelta(days=7)
    rows = con.execute(
        'SELECT date, "close", closeadj, closeunadj, volume, lastupdated FROM sep '
        "WHERE ticker = ? AND date BETWEEN ? AND ? ORDER BY date", [ticker, lo, hi]).fetchall()
    out, prev = [], None
    for d, c, a, u, v, lu in rows:
        rec = {"date": d.isoformat(), "close": c, "closeadj": a, "closeunadj": u,
               "volume": int(v) if v is not None else None,
               "lastupdated": lu.isoformat() if lu else None,
               "dividend_factor": (a / c) if c else None,
               "split_factor": (c / u) if u else None,
               "is_anomalous_session": d.isoformat() in sessions}
        if prev:
            rec["dividend_factor_ratio"] = ((a / c) / (prev["dividend_factor"])
                                            if c and prev["dividend_factor"] else None)
            rec["split_factor_ratio"] = ((c / u) / (prev["split_factor"])
                                         if u and prev["split_factor"] else None)
        out.append(rec)
        prev = rec
    actions = con.execute(
        "SELECT date, action, value, contraticker FROM actions "
        "WHERE ticker = ? AND date BETWEEN ? AND ? ORDER BY date", [ticker, lo, hi]).fetchall()
    return {
        "ticker": ticker, "anomalous_sessions": sessions,
        "window": [lo.isoformat(), hi.isoformat()],
        "rows_preserved_verbatim": out,
        "declared_actions_in_window": [
            {"date": a[0].isoformat(), "action": a[1], "value": a[2], "contraticker": a[3]}
            for a in actions],
        "declared_action_count_in_window": len(actions),
        "no_declared_action_explains_the_movement": len(actions) == 0,
    }


def _second_access_path(ticker: str, sessions: list[str]) -> dict:
    """Re-read the same sessions from the vendor's per-ticker endpoint.

    A SECOND ACCESS PATH, not a second vintage: it says whether the vendor still serves the same
    values today. A difference is evidence the sealed vintage captured a transient defect; agreement is
    evidence the anomaly is what the vendor actually publishes. Neither outcome edits the corpus.
    """
    key = os.environ.get("NASDAQ_DATA_LINK_API_KEY", "")
    if not key:
        return {"attempted": False, "status": "UNAVAILABLE_NO_API_KEY",
                "note": "recorded as unavailable rather than silently skipped"}
    lo = min(date.fromisoformat(s) for s in sessions) - timedelta(days=3)
    hi = max(date.fromisoformat(s) for s in sessions) + timedelta(days=3)
    try:
        import httpx

        # Norton's SSL inspection re-signs outbound TLS with a local root that is in the WINDOWS trust
        # store but not in certifi's bundle, so a default httpx client fails CERTIFICATE_VERIFY_FAILED
        # against every vendor host. `truststore` binds verification to the OS store, which is the
        # platform fix this repository already adopted (ADR 0017) rather than disabling verification.
        try:
            import ssl

            import truststore

            ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:                                      # noqa: BLE001 — recorded below
            ctx = True

        resp = httpx.get(NDL_SEP, verify=ctx, params={
            "ticker": ticker, "date.gte": lo.isoformat(), "date.lte": hi.isoformat(),
            "qopts.columns": "ticker,date,close,closeadj,closeunadj", "api_key": key}, timeout=60.0)
        resp.raise_for_status()
        payload = resp.json()["datatable"]
        cols = [c["name"] for c in payload["columns"]]
        recs = [dict(zip(cols, r, strict=True)) for r in payload["data"]]
    except Exception as exc:                                   # noqa: BLE001 — recorded, not raised
        return {"attempted": True, "status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
    by_date = {r["date"][:10]: r for r in recs}
    comparison = []
    for s in sessions:
        r = by_date.get(s)
        comparison.append({"date": s, "present_in_second_path": r is not None,
                           "close": r.get("close") if r else None,
                           "closeadj": r.get("closeadj") if r else None,
                           "closeunadj": r.get("closeunadj") if r else None})
    return {"attempted": True, "status": "OK", "rows_returned": len(recs),
            "endpoint": "SHARADAR/SEP per-ticker", "anomalous_sessions": comparison}


def _selection(store, session: date, spec: ConstructionSpec, *, exclude: set[str]) -> dict:
    """Re-derive the registered selection: top-200 by dollar volume → lineage filter → 12-1 momentum →
    winsorized z-score → floors → top five."""
    window = [r[0] for r in store.con.execute(
        "SELECT DISTINCT date FROM sep WHERE date <= ? ORDER BY date DESC LIMIT ?",
        [session, spec.required_history_sessions]).fetchall()]
    lineage = SessionLineageFilter(store, session_date=session, lookback_start=window[-1])

    # A quarantined history cannot contribute a price, so the name is simply not a candidate. Drawing
    # deeper (n + len(exclude)) is what PROMOTES the next-ranked name, which is the whole reason the
    # selection has to be recomputed rather than reasoned about.
    raw = list(universe_asof(store, session, n=spec.scoring_universe_n + len(exclude)))
    raw = [t for t in raw if t not in exclude][:spec.scoring_universe_n]
    candidates = lineage.filter(raw)

    # The momentum window needs lookback + skip trading days of history before `session`; a generous
    # calendar span is requested and `compute_momentum` then indexes by TRADING-DAY row offset, so
    # holidays and listing edges cannot shift the endpoints.
    start = session - timedelta(days=int((MOMENTUM_LOOKBACK_DAYS + MOMENTUM_SKIP_DAYS) * 1.9))
    scores: dict[str, float] = {}
    for t in candidates:
        px = store.get_prices(t, start, session, adjusted=True)
        if px is None or px.empty:
            continue
        m = compute_momentum(px, session, lookback_days=MOMENTUM_LOOKBACK_DAYS,
                             skip_days=MOMENTUM_SKIP_DAYS)
        if m is not None:
            scores[t] = m
    s = pd.Series(scores)
    z = zscore(winsorize(s)) if not s.empty else s
    eligible = [(t, float(z[t]), float(s[t])) for t in s.index
                if s[t] > MIN_RAW_MOMENTUM and float(z[t]) > MIN_SCORE]
    eligible.sort(key=lambda kv: (-kv[1], kv[0]))
    return {
        "raw_scoring_universe": len(raw),
        "lineage_eligible_candidates": len(candidates),
        "scored": len(scores),
        "passing_floors": len(eligible),
        "top_five": [{"ticker": t, "z": zz, "raw_momentum": rm}
                     for t, zz, rm in eligible[:SELECTION_N]],
        "candidate_set": sorted(candidates),
    }


def _proxy(store, session: date, spec: ConstructionSpec, *, exclude: set[str]) -> dict:
    """The month-end union of `universe_asof(n=500)` over the MA window, and whether the regime can
    still be formed once the quarantined names are withheld."""
    window_desc = [r[0] for r in store.con.execute(
        "SELECT DISTINCT date FROM sep WHERE date <= ? ORDER BY date DESC LIMIT ?",
        [session, spec.required_history_sessions]).fetchall()]
    ma_dates = sorted(window_desc[:spec.regime_ma_sessions])
    month_ends = [d for i, d in enumerate(ma_dates)
                  if i + 1 == len(ma_dates)
                  or (ma_dates[i + 1].year, ma_dates[i + 1].month) != (d.year, d.month)]
    basket: set[str] = set()
    for d in month_ends:
        basket |= set(universe_asof(store, d, n=spec.proxy_universe_n))
    kept = basket - exclude
    ph = ",".join("?" * len(kept))
    complete = {r[0] for r in store.con.execute(
        f"SELECT ticker FROM sep WHERE ticker IN ({ph}) AND date BETWEEN ? AND ? "
        f"AND closeadj IS NOT NULL GROUP BY ticker HAVING count(DISTINCT date) >= ?",
        [*sorted(kept), ma_dates[0], session, len(ma_dates)]).fetchall()}
    return {"ma_sessions": len(ma_dates), "month_ends": len(month_ends),
            "basket_size": len(basket), "basket_after_quarantine": len(kept),
            "contributors_with_complete_ma_history": len(complete),
            "quarantined_names_in_basket": sorted(basket & exclude),
            "regime_formable": len(complete) > 0 and len(ma_dates) >= spec.regime_ma_sessions}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-second-path", action="store_true")
    add_session_argument(ap)
    args = ap.parse_args()
    global SESSION
    SESSION = args.session

    spec = ConstructionSpec()
    store = FactorDataStore(args.store, read_only=True)
    con = store.con
    excluded = set(QUARANTINE)

    print(f"quarantine disposition : {DISPOSITION}")
    print(f"names                  : {', '.join(sorted(excluded))}")
    print("tolerance widened      : NO      source rows edited : NO\n")

    anomalies = {t: _anomaly_record(con, t, s) for t, s in QUARANTINE.items()}
    for t, rec in anomalies.items():
        print(f"-- {t}: {len(rec['anomalous_sessions'])} anomalous session(s), "
              f"{rec['declared_action_count_in_window']} declared action(s) in the +/-7d window "
              f"-> unexplained={rec['no_declared_action_explains_the_movement']}")
        for r in rec["rows_preserved_verbatim"]:
            if r["is_anomalous_session"]:
                print(f"     {r['date']}  close={r['close']}  closeadj={r['closeadj']}  "
                      f"D_ratio={r.get('dividend_factor_ratio')}  "
                      f"S_ratio={r.get('split_factor_ratio')}")

    second = ({} if args.skip_second_path
              else {t: _second_access_path(t, s) for t, s in QUARANTINE.items()})
    for t, s in second.items():
        print(f"-- {t} second access path: {s.get('status')} {s.get('error', '')}")
        for c in s.get("anomalous_sessions", []):
            print(f"     {c['date']}  close={c['close']}  closeadj={c['closeadj']}")

    print("\n-- selection, recomputed BOTH ways (unrelaxed) --")
    baseline = _selection(store, SESSION, spec, exclude=set())
    quarantined = _selection(store, SESSION, spec, exclude=excluded)
    base_top = [x["ticker"] for x in baseline["top_five"]]
    quar_top = [x["ticker"] for x in quarantined["top_five"]]
    print(f"   baseline    top5: {base_top}")
    print(f"   quarantined top5: {quar_top}")

    in_universe = {t: t in set(baseline["candidate_set"]) for t in excluded}
    in_top5 = {t: t in base_top for t in excluded}
    promoted = sorted(set(quarantined["candidate_set"]) - set(baseline["candidate_set"]))
    print(f"   in top-200 scoring universe : {in_universe}")
    print(f"   in baseline top five        : {in_top5}")
    print(f"   promoted into the universe  : {promoted}")

    print("\n-- proxy / regime, recomputed BOTH ways (unrelaxed) --")
    proxy_base = _proxy(store, SESSION, spec, exclude=set())
    proxy_quar = _proxy(store, SESSION, spec, exclude=excluded)
    print(f"   baseline    basket {proxy_base['basket_size']} -> contributors "
          f"{proxy_base['contributors_with_complete_ma_history']}, "
          f"regime_formable={proxy_base['regime_formable']}")
    print(f"   quarantined basket {proxy_quar['basket_after_quarantine']} -> contributors "
          f"{proxy_quar['contributors_with_complete_ma_history']}, "
          f"regime_formable={proxy_quar['regime_formable']}")
    print(f"   quarantined names in basket : {proxy_quar['quarantined_names_in_basket']}")

    # ---- the owner's decision rule, computed rather than argued ----
    top_five_changed = base_top != quar_top
    affects_top_five = any(in_top5.values()) or top_five_changed
    proxy_incomplete = (not proxy_quar["regime_formable"]
                        or proxy_quar["contributors_with_complete_ma_history"]
                        < proxy_base["contributors_with_complete_ma_history"] * 0.99)
    vintage_supports = not (affects_top_five or proxy_incomplete)

    print(f"\n   top five changed by the quarantine : {top_five_changed}")
    print(f"   affects the top five               : {affects_top_five}")
    print(f"   proxy/regime incomplete            : {proxy_incomplete}")
    print(f"\nVERDICT: this vintage "
          f"{'CAN' if vintage_supports else 'CANNOT'} support observation #1 "
          f"with the quarantine applied")

    payload = {
        "kind": "layer2_shop_tln_quarantine", "version": "v1.0",
        "session": SESSION.isoformat(), "store": args.store,
        "disposition": DISPOSITION,
        "quarantine_kind": "VERSION_SPECIFIC_PRICE_HISTORY_QUARANTINE",
        "permanent_universe_removal": False,
        "tolerance_widened": False, "source_rows_edited": False,
        "quarantined": QUARANTINE,
        "anomaly_records": anomalies,
        "second_access_path": second,
        "construction": {"momentum_lookback_days": MOMENTUM_LOOKBACK_DAYS,
                         "momentum_skip_days": MOMENTUM_SKIP_DAYS,
                         "min_raw_momentum": MIN_RAW_MOMENTUM, "min_score": MIN_SCORE,
                         "selection_n": SELECTION_N,
                         "scoring_universe_n": spec.scoring_universe_n,
                         "proxy_universe_n": spec.proxy_universe_n,
                         "regime_ma_sessions": spec.regime_ma_sessions,
                         "required_history_sessions": spec.required_history_sessions},
        "impact": {
            "baseline": {k: v for k, v in baseline.items() if k != "candidate_set"},
            "quarantined": {k: v for k, v in quarantined.items() if k != "candidate_set"},
            "baseline_top_five": base_top, "quarantined_top_five": quar_top,
            "in_top_200_scoring_universe": in_universe,
            "in_baseline_top_five": in_top5,
            "promoted_into_universe_by_quarantine": promoted,
            "proxy_baseline": proxy_base, "proxy_quarantined": proxy_quar,
        },
        "decision": {
            "top_five_changed": top_five_changed,
            "affects_top_five": affects_top_five,
            "proxy_or_regime_incomplete": proxy_incomplete,
            "vintage_can_support_observation_1": vintage_supports,
            "rule": "if either name reaches the top five, or the quarantine makes the proxy or the "
                    "regime incomplete, this vintage cannot support observation #1",
        },
        "gates_relaxed": False,
    }
    blob = canonical_json(payload)
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_bytes(blob)
    print(f"\nshop_tln_quarantine_sha256 : {hashlib.sha256(blob).hexdigest()}")
    print(f"wrote {outp}  ({len(blob):,} bytes)")
    store.con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
