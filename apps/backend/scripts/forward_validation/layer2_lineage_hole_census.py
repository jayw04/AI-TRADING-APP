"""Layer 2 Step 2 — lineage and structural-hole census on the rebuilt corpus.

Two distinct questions, deliberately answered separately:

**Lineage census** — for session 2026-07-27, does every candidate the construction actually consumes
resolve to exactly ONE permanent lineage across its whole lookback? Run through the ratified
`PERMATICKER_EFFECTIVE_INTERVAL_V1` contract (`assess_universe`) rather than reimplemented, so what is
measured here is what the session would really apply. Both consumer sets are assessed, because they
have different lookbacks and different failure modes: the top-200 scoring candidates over the 273-session
history window, and the market-proxy basket over the 200-session MA window.

**Structural-hole census** — independently of identity resolution, how much of each identity's own
priced span is missing? A long internal hole was the signature that exposed the ECHO reuse collision
(Echo Global 2009-2021, a 4.5-year hole, then EchoStar 2026), and it is also how the old corpus's
conflated keys were detectable at all. Measured in GOVERNED SESSIONS from the corpus's own calendar —
a fortnight of holidays is not a hole.

⚠ A hole is NOT automatically an identity defect. The owner ruled on BKYI that a 22-session hole with a
single authoritative lineage and no competing claim is a DATA-CONTINUITY GAP, not identity ambiguity.
So holes are counted and attributed here; they are not converted into refusals. Only the bridge-shape
check (`assess_bridge_risk`) can add a refusal, and only for names the contract already excluded.
"""

# ⚠ PORTED into the repository for REPRODUCIBILITY. Operator machine paths are removed: the
# backend root resolves relative to this file and every data location comes from an argument or
# an environment override. A hard-coded working-copy path would make the tool unrunnable by
# anyone else, which is the opposite of what a reproducible build tool is for.

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import UTC, date, datetime
from pathlib import Path

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.factor_data.store import FactorDataStore  # noqa: E402
from app.factor_data.universe import universe_asof  # noqa: E402
from app.validation.data_finality import ConstructionSpec  # noqa: E402
from app.validation.governed_corpus import canonical_json  # noqa: E402
from app.validation.security_lineage import (  # noqa: E402
    LINEAGE_BRIDGE_HOLE_MIN_SESSIONS,
    assess_bridge_risk,
    assess_universe,
    require_permanent_identifier,
)

SESSION = date(2026, 7, 27)

#: The old corpus's known lineage landmarks, re-measured on the rebuilt corpus so the repair is
#: demonstrated rather than asserted.
LANDMARKS = ("ECHO", "ECHO2", "SATS", "BKYI", "INFQ", "LEXX", "AMCRY")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = ConstructionSpec()
    store = FactorDataStore(args.store, read_only=True)
    require_permanent_identifier(store)
    con = store.con

    # ---- the construction's own windows, taken from the store's calendar ----
    window_desc = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM sep WHERE date <= ? ORDER BY date DESC LIMIT ?",
        [SESSION, spec.required_history_sessions]).fetchall()]
    if not window_desc or window_desc[0] != SESSION:
        raise SystemExit(f"{SESSION} is not the latest session in this store")
    history_start = window_desc[-1]
    ma_dates = sorted(window_desc[:spec.regime_ma_sessions])
    print(f"session {SESSION} | history window {history_start}..{SESSION} "
          f"({len(window_desc)} sessions, required {spec.required_history_sessions})")
    print(f"MA window {ma_dates[0]}..{ma_dates[-1]} ({len(ma_dates)} sessions)")

    # ---- 1. scoring candidates ----
    raw_scoring = list(universe_asof(store, SESSION, n=spec.scoring_universe_n))
    a_scoring = assess_universe(store, raw_scoring, session_date=SESSION,
                                lookback_start=history_start)
    print(f"\nscoring universe : raw {a_scoring.considered} -> eligible "
          f"{len(a_scoring.eligible_tickers)} | excluded {a_scoring.excluded_count} "
          f"{a_scoring.counts_by_refusal()}")
    for d in a_scoring.excluded:
        print(f"    - {d.ticker:<8} {d.refusal}  {d.detail[:90]}")

    # ---- 2. proxy basket over the MA window ----
    month_ends = [d for i, d in enumerate(ma_dates)
                  if i + 1 == len(ma_dates)
                  or (ma_dates[i + 1].year, ma_dates[i + 1].month) != (d.year, d.month)]
    basket: set[str] = set()
    for d in month_ends:
        basket |= set(universe_asof(store, d, n=spec.proxy_universe_n))
    raw_basket = sorted(basket)
    a_proxy = assess_universe(store, raw_basket, session_date=SESSION,
                              lookback_start=ma_dates[0])
    print(f"\nproxy basket     : {len(month_ends)} month-ends -> raw {a_proxy.considered} -> "
          f"eligible {len(a_proxy.eligible_tickers)} | excluded {a_proxy.excluded_count} "
          f"{a_proxy.counts_by_refusal()}")
    for d in a_proxy.excluded:
        print(f"    - {d.ticker:<8} {d.refusal}  {d.detail[:90]}")

    # ---- 3. bridge risk (the ONLY check that may add a refusal) ----
    bridges = assess_bridge_risk(store, a_proxy.excluded, window=ma_dates)
    risky = [b for b in bridges if getattr(b, "risky", False)]
    print(f"\nbridge check     : {len(risky)} risky / {len(bridges)} assessed "
          f"(min hole {LINEAGE_BRIDGE_HOLE_MIN_SESSIONS} sessions)")
    for b in risky:
        print(f"    ! {b.to_evidence()}")

    # ---- 4. structural-hole census over EVERY price-bearing identity ----
    # Longest internal hole per identity, in governed sessions, from the corpus's own calendar.
    holes = con.execute("""
        WITH cal AS (SELECT date, row_number() OVER (ORDER BY date) AS rn
                     FROM (SELECT DISTINCT date FROM sep)),
             m AS (SELECT s.permaticker AS p, c.rn AS rn FROM sep s JOIN cal c ON c.date = s.date),
             g AS (SELECT p, rn - LAG(rn) OVER (PARTITION BY p ORDER BY rn) - 1 AS gap FROM m)
        SELECT p, coalesce(max(gap), 0) AS worst_hole FROM g GROUP BY p
    """).fetchall()
    worst = {r[0]: int(r[1]) for r in holes}
    buckets = {"0": 0, "1-4": 0, "5-19": 0, "20-99": 0, "100-499": 0, "500+": 0}
    for h in worst.values():
        k = ("0" if h == 0 else "1-4" if h < 5 else "5-19" if h < 20
             else "20-99" if h < 100 else "100-499" if h < 500 else "500+")
        buckets[k] += 1
    over = sorted(((h, p) for p, h in worst.items() if h >= LINEAGE_BRIDGE_HOLE_MIN_SESSIONS),
                  reverse=True)
    print(f"\nstructural holes over {len(worst):,} price-bearing identities:")
    for k, v in buckets.items():
        print(f"    hole {k:<8} {v:>7,}")
    print(f"    identities with a hole >= {LINEAGE_BRIDGE_HOLE_MIN_SESSIONS}: {len(over):,} "
          f"({100 * len(over) / max(len(worst), 1):.2f}%)")
    names = {r[0]: r[1] for r in con.execute(
        "SELECT permaticker, ticker FROM tickers").fetchall()}
    print("    worst 12:")
    for h, p in over[:12]:
        print(f"      {names.get(p, '?'):<8} permaticker={p:<9} hole={h:>5} sessions")

    # ---- 5. the landmark cases, re-measured ----
    print("\nlandmark identities (old-corpus lineage defects):")
    landmarks = {}
    for t in LANDMARKS:
        row = con.execute(
            "SELECT permaticker, count(*), min(date), max(date) FROM sep WHERE ticker = ? GROUP BY 1",
            [t]).fetchone()
        if row is None:
            landmarks[t] = {"present": False}
            print(f"    {t:<8} absent from the rebuilt corpus")
            continue
        p, n, lo, hi = row
        landmarks[t] = {"present": True, "permaticker": p, "rows": int(n),
                        "span": [str(lo), str(hi)], "worst_hole_sessions": worst.get(p, 0)}
        print(f"    {t:<8} permaticker={p:<9} rows={int(n):>6,} {lo}..{hi} "
              f"worst_hole={worst.get(p, 0)}")

    store.con.close()

    payload = {
        "kind": "layer2_lineage_hole_census", "version": "v1.0",
        "generated_utc": datetime.now(UTC).isoformat(),
        "store": args.store,
        "session_date": SESSION.isoformat(),
        "construction": {"required_history_sessions": spec.required_history_sessions,
                         "regime_ma_sessions": spec.regime_ma_sessions,
                         "scoring_universe_n": spec.scoring_universe_n,
                         "proxy_universe_n": spec.proxy_universe_n},
        "history_window": [history_start.isoformat(), SESSION.isoformat(), len(window_desc)],
        "ma_window": [ma_dates[0].isoformat(), ma_dates[-1].isoformat(), len(ma_dates)],
        "scoring_lineage": a_scoring.to_evidence(),
        "proxy_month_ends": len(month_ends),
        "proxy_lineage": a_proxy.to_evidence(),
        "bridge_check": {"assessed": len(bridges), "risky": len(risky),
                         "min_hole_sessions": LINEAGE_BRIDGE_HOLE_MIN_SESSIONS,
                         "risky_detail": [b.to_evidence() for b in risky]},
        "hole_census": {
            "identities": len(worst),
            "buckets": buckets,
            "threshold_sessions": LINEAGE_BRIDGE_HOLE_MIN_SESSIONS,
            "identities_at_or_over_threshold": len(over),
            "worst": [{"permaticker": p, "ticker": names.get(p), "worst_hole_sessions": h}
                      for h, p in over[:50]],
            "note": ("a hole is a DATA-CONTINUITY observation, not an identity refusal — the owner "
                     "ruled on BKYI that a 22-session hole with one authoritative lineage and no "
                     "competing claim does not make the identity ambiguous"),
        },
        "landmarks": landmarks,
    }
    blob = canonical_json(payload)
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_bytes(blob)
    print(f"\nlineage_hole_census_sha256 : {hashlib.sha256(blob).hexdigest()}")
    print(f"wrote {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
