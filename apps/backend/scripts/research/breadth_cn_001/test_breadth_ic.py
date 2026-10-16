"""Synthetic-data contract tests for breadth_ic.py.  Run: python3 test_breadth_ic.py
Tests the plumbing, NOT the strategy: synthetic data carries no evidence about IC."""
import tempfile
from pathlib import Path

import breadth_ic as B
import numpy as np
import pandas as pd

RNG = np.random.default_rng(7)


def make_stocks(days, n=300):
    T = len(days)
    # regime factor: slow oscillation + noise so breadth visits both tails
    f = 0.004 * np.sin(np.arange(T) / 23.0) + 0.006 * RNG.standard_normal(T)
    rows = []
    for k in range(n):
        lst = RNG.integers(0, T // 3) if k % 5 == 0 else 0           # late listings
        dl = T - RNG.integers(0, T // 4) if k % 11 == 0 else T          # delistings
        r = 0.8 * f + 0.015 * RNG.standard_normal(T)
        px = 10 * np.exp(np.cumsum(r))
        excl = np.zeros(T, bool)
        excl[lst:lst + 5] = True                                         # N/C window
        if k % 13 == 0:
            a = RNG.integers(lst, max(lst + 1, dl - 60)); excl[a:a + 120] = True   # ST spell
        susp = RNG.random(T) < 0.01
        idx = np.arange(lst, dl)
        idx = idx[~susp[idx]]
        rows.append(pd.DataFrame({"date": days[idx], "code": f"S{k:04d}", "close_adj": px[idx],
                                  "is_excluded": excl[idx]}))
    return pd.concat(rows, ignore_index=True), f


def third_friday(y, m):
    d = pd.Timestamp(y, m, 1)
    d += pd.Timedelta(days=(4 - d.weekday()) % 7)
    return d + pd.Timedelta(days=14)


def make_ic(days, f):
    idx = 6000 * np.exp(np.cumsum(f * 1.1 + 0.001 * RNG.standard_normal(len(days))))
    months = pd.period_range(days[0], days[-1] + pd.Timedelta(days=70), freq="M")
    exp = {f"IC{p.strftime('%y%m')}": third_friday(p.year, p.month) for p in months}
    bars, ois = [], []
    for di, d in enumerate(days):
        live = sorted([(e, c) for c, e in exp.items() if e >= d])[:2]
        intraday = idx[di] * np.exp(np.cumsum(0.002 * RNG.standard_normal(8)))
        for rank, (e, c) in enumerate(live):
            ttm = (e - d).days
            basis = -0.0005 * ttm * idx[di]                               # discount (贴水) shrinking to 0
            oi = 100000 if (rank == 0 and ttm > 7) or (rank == 1 and live[0][0] - d <= pd.Timedelta(days=7)) else 30000
            ois.append({"date": d, "contract": c, "oi": oi + RNG.integers(0, 1000), "expiry": e})
            for b in range(8):
                t = d + pd.Timedelta(hours=10 + b // 4 * 3.5, minutes=30 * (b % 4))
                c_ = intraday[b] + basis
                o_ = (intraday[b - 1] if b else idx[di - 1] if di else idx[0]) + basis
                bars.append({"datetime": t, "contract": c, "open": o_, "high": max(o_, c_) + 2,
                             "low": min(o_, c_) - 2, "close": c_})
    return pd.DataFrame(bars), pd.DataFrame(ois)


def main():
    days = pd.bdate_range("2014-01-02", "2026-10-16")
    stocks, f = make_stocks(days)
    ic30, oi = make_ic(days, f)
    cfg = B.Config()

    # 1. breadth sanity
    br = B.stock_breadth(stocks, cfg)
    assert br["ratio"].between(0, 1).all()
    assert (br["n_eligible"] <= stocks.groupby("date").size().reindex(br.index)).all()
    wk, mo = B.period_breadth(stocks, cfg, "W"), B.period_breadth(stocks, cfg, "M")
    assert len(wk) > 600 and len(mo) > 140
    print("breadth ok   daily", len(br), " weekly", len(wk), " monthly", len(mo),
          f" ratio range {br.ratio.min():.2f}-{br.ratio.max():.2f}")

    # 2. no look-ahead: perturb everything after cutoff, setups before cutoff must not change
    cut = pd.Timestamp("2020-06-30")
    s2 = stocks.copy()
    m = s2["date"] > cut
    s2.loc[m, "close_adj"] *= np.exp(0.2 * RNG.standard_normal(m.sum()))
    a = B.daily_setups(B.stock_breadth(stocks, cfg), cfg).loc[:cut]
    b = B.daily_setups(B.stock_breadth(s2, cfg), cfg).loc[:cut]
    assert a["setup"].equals(b["setup"]) and np.allclose(a["pct"].fillna(-1), b["pct"].fillna(-1))
    B.plot_breadth(B.daily_setups(br, cfg), cfg, str(Path(tempfile.gettempdir()) / "breadth_synth.png"))
    print("look-ahead ok  setups up to cutoff invariant to future data;",
          "short setups", int((a.setup == -1).sum()), " long setups", int((a.setup == 1).sum()))

    # 3. main contract: decided from D-1, never expired
    main = B.main_contract_by_day(oi)
    exp = oi.drop_duplicates("contract").set_index("contract")["expiry"]
    assert (main.map(exp) > main.index).all(), "traded an expired contract"
    print("main contract ok  switches:", int((main != main.shift()).sum() - 1))

    # 4. continuous series removes roll gaps
    ser = B.build_main_series(ic30, main)
    first = ser["date"] != ser["date"].shift()
    d_raw, d_adj = ser["close"].diff().abs(), ser["close_cont"].diff().abs()
    raw_jump, adj_jump = d_raw[ser["roll"]].mean(), d_adj[ser["roll"]].mean()
    day_open = d_adj[first & ~ser["roll"]].mean()
    print(f"roll gap ok  |jump| at rolls raw={raw_jump:.1f} adj={adj_jump:.1f} vs ordinary day-open={day_open:.1f}")
    assert adj_jump < raw_jump and abs(adj_jump - day_open) < 0.25 * day_open, "roll gap not removed"

    # 5. end-to-end + holdout seal
    with tempfile.TemporaryDirectory() as tmp:
        led = Path(tmp) / "ledger.csv"
        try:
            B.run(stocks, ic30, oi, cfg, "dev", led, note="real without freeze")
            raise AssertionError("real-data dev run allowed without freeze")
        except B.NotFrozen as e:
            print("freeze gate ok ->", e)
        res = B.run(stocks, ic30, oi, cfg, "dev", led, note="smoke", data="synthetic")
        t = res["trades"]
        assert not t.empty
        win = B.setup_windows(res["breadth"], pd.DatetimeIndex(ser["date"].unique()), cfg)
        entry_days = pd.to_datetime(t["entry_time"]).dt.normalize()
        assert (win.loc[entry_days, "side"].to_numpy() == t["side"].to_numpy()).all(), \
            "entry outside an active same-side setup window"
        try:
            B.run(stocks, ic30, oi, cfg, "holdout", led, data="synthetic")
            raise AssertionError("holdout opened without FREEZE")
        except B.HoldoutSealed as e:
            print("seal ok ->", e)
        B.freeze(cfg, led, note="FREEZE smoke")
        try:
            B.freeze(cfg, led, note="again"); raise AssertionError("double freeze allowed")
        except ValueError:
            pass
        B.run(stocks, ic30, oi, cfg, "dev", led, note="real after freeze")          # now permitted
        B.run(stocks, ic30, oi, cfg, "holdout", led, note="one-shot")
        try:
            B.run(stocks, ic30, oi, cfg, "holdout", led)
            raise AssertionError("holdout reopened")
        except B.HoldoutSealed as e:
            print("one-shot ok ->", e)
        print("\nsynthetic dev breakdown (plumbing only, not evidence):")
        print(res["breakdown"].loc[["ALL", "LONG", "SHORT"]].to_string())
        nt = B.null_test(res, cfg, n=20)
        assert nt["p_value"].between(0, 1).all()
        print("\nnull control (n=20, synthetic):"); print(nt.round(3).to_string())
    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    main()
