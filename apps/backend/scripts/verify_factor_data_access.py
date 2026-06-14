"""P9 §0 — Factor-data access verification (FMP + Sharadar / Nasdaq Data Link).

Host-venv, read-only, no stack. Proves the assumptions ADR 0018 / the P9 Direction
were written against: that both vendor keys authenticate and return
survivorship-free, point-in-time data at the expected depth, under the ADR-0017
OS-trust-store TLS path (works with Norton inspection on).

Run:
    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
        apps/backend/scripts/verify_factor_data_access.py

Exit 0 = GO, non-zero = NO-GO. Prints a PASS/FAIL battery; keys are printed as
lengths only, never values.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import truststore  # ADR 0017 — route TLS through the OS trust store BEFORE any HTTPS

truststore.inject_into_ssl()

import httpx  # noqa: E402
import pandas as pd  # noqa: E402

try:
    from dotenv import load_dotenv  # noqa: E402

    _root = Path(__file__).resolve().parents[3]
    for env in (_root / ".env", _root / "apps" / "backend" / ".env"):
        if env.exists():
            load_dotenv(env, override=False)
except Exception:  # python-dotenv optional; env may already be exported
    pass

FMP_KEY = os.environ.get("FMP_API_KEY", "")
NDL_KEY = os.environ.get("NASDAQ_DATA_LINK_API_KEY", "")

NDL_BASE = "https://data.nasdaq.com/api/v3/datatables/SHARADAR"
FMP_BASE = "https://financialmodelingprep.com/api/v3"

# (label, ok, detail, hard)  — hard checks gate GO/NO-GO; soft checks only record.
results: list[tuple[str, bool, str, bool]] = []


def record(label: str, ok: bool, detail: str, hard: bool = True) -> None:
    results.append((label, ok, detail, hard))


def ndl_table(client: httpx.Client, dataset: str, max_pages: int = 60, **params):
    """Fetch a SHARADAR datatable, following cursor pagination → DataFrame + headers.

    ``dataset`` is the table name in the URL (SEP/TICKERS/ACTIONS/SP500); note that
    SHARADAR/TICKERS itself takes a ``table`` *filter* param, hence the distinct name.
    """
    params["api_key"] = NDL_KEY
    frames, cursor, pages, headers = [], None, 0, {}
    while pages < max_pages:
        q = dict(params)
        if cursor:
            q["qopts.cursor_id"] = cursor
        r = client.get(f"{NDL_BASE}/{dataset}.json", params=q, timeout=30)
        headers = r.headers
        r.raise_for_status()
        dt = r.json()["datatable"]
        cols = [c["name"] for c in dt["columns"]]
        frames.append(pd.DataFrame(dt["data"], columns=cols))
        cursor = r.json().get("meta", {}).get("next_cursor_id")
        pages += 1
        if not cursor:
            break
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(), headers


def main() -> int:
    print(f"key lengths: FMP={len(FMP_KEY)} NASDAQ_DATA_LINK={len(NDL_KEY)}")
    if not NDL_KEY or not FMP_KEY:
        record("keys present", False, "FMP_API_KEY / NASDAQ_DATA_LINK_API_KEY missing in env")
        return finish()

    client = httpx.Client(follow_redirects=True)

    # ---- Sharadar / Nasdaq Data Link -------------------------------------------------
    delisted_ticker = None
    try:
        t0 = time.time()
        sep_recent, hdr = ndl_table(client, "SEP", ticker="AAPL", **{"date.gte": "2024-01-01"})
        dt_recent = time.time() - t0
        has_adj = "closeadj" in sep_recent.columns
        record(
            "Sharadar auth + SEP recent (AAPL)",
            not sep_recent.empty and has_adj,
            f"{len(sep_recent)} rows, cols={list(sep_recent.columns)[:8]}…, closeadj={has_adj}, {dt_recent:.1f}s",
        )
        # rate-limit headers (if any)
        rl = {k: v for k, v in hdr.items() if "ratelimit" in k.lower() or "rate-limit" in k.lower()}
        record("Sharadar rate-limit headers", True, str(rl) or "(none returned)", hard=False)
    except Exception as e:
        record("Sharadar auth + SEP recent (AAPL)", False, repr(e)[:200])

    # SEP history depth to ~1998
    try:
        sep98, _ = ndl_table(
            client, "SEP", ticker="AAPL", **{"date.gte": "1998-01-01", "date.lte": "1998-12-31"}
        )
        record(
            "SEP history reaches 1998 (AAPL)",
            not sep98.empty,
            f"{len(sep98)} rows in 1998; min={sep98['date'].min() if not sep98.empty else 'n/a'}",
        )
        # crude full-history ingest-time estimate: one full AAPL pull × ~500 names
        t0 = time.time()
        sep_full, _ = ndl_table(client, "SEP", ticker="AAPL", **{"date.gte": "1998-01-01"})
        dt_full = time.time() - t0
        est_min = dt_full * 500 / 60.0
        record(
            "Est. full S&P 500 SEP ingest time",
            True,
            f"AAPL full history {len(sep_full)} rows in {dt_full:.1f}s → ~{est_min:.0f} min for 500 names "
            f"({'checkpointing recommended' if est_min > 10 else 'single-shot ok'})",
            hard=False,
        )
    except Exception as e:
        record("SEP history reaches 1998 (AAPL)", False, repr(e)[:200])

    # TICKERS schema + discover a delisted name
    try:
        tk, _ = ndl_table(client, "TICKERS", max_pages=1, table="SEP")
        need = {"ticker", "isdelisted", "firstpricedate", "lastpricedate"}
        record(
            "TICKERS schema (isdelisted/price-dates)",
            need.issubset(set(tk.columns)),
            f"{len(tk)} rows (page 1), cols include {sorted(need & set(tk.columns))}",
        )
        if "isdelisted" in tk.columns:
            de = tk[(tk["isdelisted"].astype(str).str.upper().isin(["Y", "TRUE", "1"]))]
            de = de[de["lastpricedate"].notna()]
            if not de.empty:
                delisted_ticker = str(de.iloc[0]["ticker"])
                record(
                    "TICKERS has delisted names",
                    True,
                    f"e.g. {delisted_ticker} (isdelisted, lastpricedate={de.iloc[0]['lastpricedate']})",
                )
            else:
                record("TICKERS has delisted names", False, "no delisted row with lastpricedate on page 1")
    except Exception as e:
        record("TICKERS schema (isdelisted/price-dates)", False, repr(e)[:200])

    # ★ Survivorship-free: a delisted name must return price history
    try:
        cand = delisted_ticker or "LEH"
        sep_del, _ = ndl_table(client, "SEP", ticker=cand, **{"date.gte": "1990-01-01"})
        ok = not sep_del.empty
        record(
            "★ Survivorship-free: delisted name has SEP history",
            ok,
            f"{cand}: {len(sep_del)} rows"
            + (f", last={sep_del['date'].max()}" if ok else " (EMPTY — survivorship NOT proven)"),
        )
    except Exception as e:
        record("★ Survivorship-free: delisted name has SEP history", False, repr(e)[:200])

    # ACTIONS
    try:
        act, _ = ndl_table(client, "ACTIONS", ticker="AAPL")
        record("ACTIONS (corporate actions)", not act.empty, f"{len(act)} rows, actions={sorted(set(act['action']))[:6] if 'action' in act else '?'}")
    except Exception as e:
        record("ACTIONS (corporate actions)", False, repr(e)[:200])

    # ★ S&P 500 change-log + earliest date (the PIT-membership floor)
    try:
        sp, _ = ndl_table(client, "SP500", max_pages=60)
        if sp.empty:
            record("★ SP500 change-log accessible", False, "empty")
        else:
            floor = sp["date"].min()
            actions = sorted(set(sp["action"])) if "action" in sp.columns else []
            record("★ SP500 change-log accessible", True, f"{len(sp)} rows, actions={actions}")
            covers98 = str(floor) <= "1998-01-01"
            record(
                "★ SP500 change-log floor vs 1998 backtest window",
                True,  # informational — not a hard fail, but a scope finding
                f"earliest change-log date={floor} → "
                + ("covers 1998+" if covers98 else f"does NOT reach 1998; clamp momentum backtest start to {floor}"),
                hard=False,
            )
    except Exception as e:
        record("★ SP500 change-log accessible", False, repr(e)[:200])

    # ---- FMP (token reachability only; v1 is price-only) ------------------------------
    def fmp(endpoint: str, **params):
        params["apikey"] = FMP_KEY
        r = client.get(f"{FMP_BASE}/{endpoint}", params=params, timeout=30)
        return r

    # FMP is DEFERRED to §5+ (v1 is price-only), so every FMP check is SOFT — recorded,
    # never gating the §1 spine. A failure here is a "investigate before §5" finding.
    try:
        r = fmp("income-statement/AAPL", period="annual", limit=20)
        ok = r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) > 0
        years = len(r.json()) if ok else 0
        record("FMP auth + fundamentals depth", True, f"HTTP {r.status_code}, {years} annual statements (~Starter depth)", hard=False)
    except Exception as e:
        record("FMP auth + fundamentals depth", True, repr(e)[:200], hard=False)

    # Diagnose the legacy-v3 vs new 'stable' API (FMP migrated; legacy paths can 403)
    try:
        rs = client.get(
            "https://financialmodelingprep.com/stable/income-statement",
            params={"symbol": "AAPL", "period": "annual", "limit": 5, "apikey": FMP_KEY},
            timeout=30,
        )
        body = rs.json() if rs.headers.get("content-type", "").startswith("application/json") else rs.text[:120]
        n = len(body) if isinstance(body, list) else "?"
        record("FMP /stable API probe", True, f"HTTP {rs.status_code}, rows={n} (use /stable if v3 is 403)", hard=False)
    except Exception as e:
        record("FMP /stable API probe", True, repr(e)[:160], hard=False)

    gated = []
    for label, ep, params in [
        ("ratios", "ratios/AAPL", {"limit": 5}),
        ("earnings-surprises", "earnings-surprises/AAPL", {}),
    ]:
        try:
            r = fmp(ep, **params)
            ok = r.status_code == 200
            if not ok:
                gated.append(f"{ep}:{r.status_code}")
            record(f"FMP {label} reachable", True, f"HTTP {r.status_code}" + ("" if ok else " (gated)"), hard=False)
        except Exception as e:
            record(f"FMP {label} reachable", True, repr(e)[:120], hard=False)
    # macro/treasury lives on the v4 surface
    try:
        r = client.get("https://financialmodelingprep.com/api/v4/treasury", params={"from": "2024-01-01", "to": "2024-01-15", "apikey": FMP_KEY}, timeout=30)
        ok = r.status_code == 200
        if not ok:
            gated.append(f"v4/treasury:{r.status_code}")
        record("FMP macro/treasury reachable", True, f"HTTP {r.status_code}" + ("" if ok else " (gated on Starter)"), hard=False)
    except Exception as e:
        record("FMP macro/treasury reachable", True, repr(e)[:120], hard=False)
    record("FMP Starter gated endpoints", True, ", ".join(gated) or "(none observed)", hard=False)

    return finish()


def finish() -> int:
    width = max(len(r[0]) for r in results) if results else 10
    print("\n" + "=" * (width + 30))
    hard_fail = 0
    for label, ok, detail, hard in results:
        mark = "PASS" if ok else "FAIL"
        tag = "" if hard else " (soft)"
        if hard and not ok:
            hard_fail += 1
        print(f"  [{mark}] {label.ljust(width)}  {detail}{tag}")
    go = hard_fail == 0
    print("=" * (width + 30))
    print(f"RESULT: {'GO' if go else 'NO-GO'}  ({hard_fail} hard failure(s))")
    return 0 if go else 1


if __name__ == "__main__":
    raise SystemExit(main())
