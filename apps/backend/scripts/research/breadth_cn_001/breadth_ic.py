"""
BREADTH-CN-001 — 中证500股指期货(IC) 情绪广度波段策略  (research harness v0.1)

Pipeline
  1. stock_breadth()      全A股(剔除ST/*ST/退市整理/N/C) 收盘价站上5日均线的比例/数量
  2. period_breadth()     同口径 周线(5周均线) / 月线(5月均线)
  3. pit_percentile()     时点分位(扩展窗口, 只用 <=t 的历史) —— 无未来函数
  4. daily_setups()       高区向下拐头 -> 空头预备; 低区向上拐头 -> 多头预备
  5. build_main_series()  IC 主力合约(前一日持仓量最大), 差值复权连续价用于MA60
  6. backtest()           30分钟K线: 预备有效期内 close 与 MA60 关系触发开仓, 反向穿越止损
  7. metrics()            胜率 / 盈亏比 / 回撤 / 分年 / 分多空

Timing contract (no look-ahead):
  * 日线广度在 T 日收盘后才可知 -> 预备信号从 T+1 第一根30分钟K线起生效
  * 30分钟信号在 bar 收盘确认 -> 下一根 bar 开盘价成交
  * 主力合约在 D 日由 D-1 收盘持仓量决定 -> D 日开盘换月
  * 分位数仅用截至当日(含)的历史

Input schemas (CSV/DataFrame, see README.md):
  stocks : date, code, close_adj, is_excluded           (one row per stock per trading day it traded)
  ic_30m : datetime, contract, open, high, low, close    (all listed IC contracts, 30-minute bars)
  ic_oi  : date, contract, oi, expiry                    (daily close open interest per contract)
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- config
@dataclass(frozen=True)
class Config:
    # --- indicator
    ma_len: int = 5                    # 5日/5周/5月均线
    ma_max_span: int = 10              # the 5 observations must lie within the last 10 market periods;
                                       # otherwise (long suspension) the stock is ineligible until it has 5 fresh bars
    measure: str = "ratio"             # "ratio" (pre-registered primary) | "count" (user's literal spec, diagnostic only)
    pct_warmup: int = 500              # 分位数计算前至少需要的交易日数 (约2年)
    high_pct: float = 0.80             # 高区: 分位 >= 80%   (原文写"20%以下", 视为笔误, 见 SPEC §2)
    low_pct: float = 0.20              # 低区: 分位 <= 20%
    zone_on: str = "prev"              # 拐头判定时, 高/低区看拐点前一日(峰/谷)的分位
    setup_valid_days: int = 3          # 预备信号有效交易日数 (T+1 .. T+K)
    one_entry_per_setup: bool = True   # 止损后同一预备期内不再开仓
    # --- execution
    ma_bars: int = 60                  # 30分钟 MA60
    multiplier: float = 200.0          # IC 每点 200 元
    tick: float = 0.2
    slippage_ticks: float = 1.0        # 每边滑点
    fee_open: float = 0.23e-4          # 按成交金额; 以中金所现行标准核对后冻结
    fee_close: float = 0.23e-4
    fee_close_today: float = 2.3e-4    # 平今 (历史上曾显著更高, 见 SPEC §5)
    # --- evaluation
    start: str = "2016-10-17"          # 10年回测起点
    dev_end: str = "2023-12-31"        # 开发期终点; 之后为封存样本外
    lots: int = 1

    def digest(self) -> str:
        blob = json.dumps(dataclasses.asdict(self), sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:12]


# ---------------------------------------------------------------- 1-2. breadth
def _above_ma(df: pd.DataFrame, ma_len: int, max_span: int) -> pd.DataFrame:
    """df: one row per (code, period-end) with close_adj, is_excluded. MA over the stock's own last
    `ma_len` observations (suspended days absent -> not counted).  Staleness rule: those observations must
    fall within the last `max_span` market periods (periods = dates present anywhere in df); after a longer
    suspension the stock is ineligible until it has `ma_len` fresh bars."""
    df = df.sort_values(["code", "date"]).copy()
    ordinal = pd.Series(np.arange(df["date"].nunique()), index=np.sort(df["date"].unique()))
    df["_ord"] = df["date"].map(ordinal)
    df["ma"] = (df.groupby("code", sort=False)["close_adj"]
                  .rolling(ma_len, min_periods=ma_len).mean()
                  .reset_index(level=0, drop=True))
    span = df["_ord"] - df.groupby("code", sort=False)["_ord"].shift(ma_len - 1) + 1
    df["stale"] = span > max_span
    df["eligible"] = (~df["is_excluded"].astype(bool)) & df["ma"].notna() & ~df["stale"]
    df["above"] = df["eligible"] & (df["close_adj"] > df["ma"])
    return df


def _aggregate(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("date")
    out = pd.DataFrame({"n_above": g["above"].sum(), "n_eligible": g["eligible"].sum()})
    out = out[out["n_eligible"] > 0].copy()          # MA warm-up days carry no breadth
    out["ratio"] = out["n_above"] / out["n_eligible"]
    return out


def stock_breadth(stocks: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """日线广度."""
    s = stocks[["date", "code", "close_adj", "is_excluded"]].copy()
    s["date"] = pd.to_datetime(s["date"])
    return _aggregate(_above_ma(s, cfg.ma_len, cfg.ma_max_span))


def period_breadth(stocks: pd.DataFrame, cfg: Config, freq: str) -> pd.DataFrame:
    """周线 (freq='W') / 月线 (freq='M'): 每只股票取该周期最后一个交易日收盘价及当日剔除状态.
    索引为该周期实际最后交易日. 注意: 当前未完成的周期不应参与交易决策."""
    s = stocks[["date", "code", "close_adj", "is_excluded"]].copy()
    s["date"] = pd.to_datetime(s["date"])
    key = s["date"].dt.to_period("W-FRI" if freq == "W" else "M")
    s["pkey"] = key
    last = s.sort_values("date").groupby(["code", "pkey"], sort=False).tail(1)
    # report each period at the market's last trading day in that period
    period_end = s.groupby("pkey")["date"].max()
    last = last.assign(date=last["pkey"].map(period_end)).drop(columns="pkey")
    return _aggregate(_above_ma(last, cfg.ma_len, cfg.ma_max_span))


# ---------------------------------------------------------------- 3. point-in-time percentile
def pit_percentile(x: pd.Series, warmup: int) -> pd.Series:
    """pct_t = share of {x_s : s <= t} that are <= x_t.  NaN before `warmup` observations.
    O(n^2) worst case but n ~ 3000 days -> trivial."""
    v = x.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    hist = []
    import bisect
    for i, xi in enumerate(v):
        if np.isnan(xi):
            continue
        bisect.insort(hist, xi)
        if len(hist) >= warmup:
            out[i] = bisect.bisect_right(hist, xi) / len(hist)
    return pd.Series(out, index=x.index, name="pct")


# ---------------------------------------------------------------- 4. daily setups
def daily_setups(breadth: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """拐头定义 (pre-registered):
       空头预备 @T:  zone(T-1)=高区  且  B(T) < B(T-1)  且  B(T-1) >= B(T-2)   (高区第一天回落)
       多头预备 @T:  zone(T-1)=低区  且  B(T) > B(T-1)  且  B(T-1) <= B(T-2)   (低区第一天回升)
    zone_on='today' 则改用 T 日分位判定区间 (敏感性分析用)."""
    b = breadth[cfg.measure].astype(float)
    pct = pit_percentile(b, cfg.pct_warmup)
    zpct = pct.shift(1) if cfg.zone_on == "prev" else pct
    d1, d0 = b.diff(), b.diff().shift(1)
    short = (zpct >= cfg.high_pct) & (d1 < 0) & (d0 >= 0)
    long_ = (zpct <= cfg.low_pct) & (d1 > 0) & (d0 <= 0)
    out = pd.DataFrame({"B": b, "pct": pct, "setup": 0}, index=b.index)
    out.loc[short, "setup"] = -1
    out.loc[long_, "setup"] = 1
    return out


def setup_windows(setups: pd.DataFrame, trading_days: pd.DatetimeIndex, cfg: Config) -> pd.Series:
    """Map each trading day to the active setup (-1/0/+1) and its id.  A setup formed at close of T
    is active on trading days T+1 .. T+K.  A newer setup (either side) replaces an older one."""
    td = pd.DatetimeIndex(sorted(set(trading_days)))
    pos = {d: i for i, d in enumerate(td)}
    side = pd.Series(0, index=td, dtype=int)
    sid = pd.Series(-1, index=td, dtype=int)
    for k, (d, row) in enumerate(setups[setups["setup"] != 0].iterrows()):
        if d not in pos:
            continue
        i = pos[d]
        rng = td[i + 1: i + 1 + cfg.setup_valid_days]
        side.loc[rng] = int(row["setup"])
        sid.loc[rng] = k
    return pd.DataFrame({"side": side, "setup_id": sid})


# ---------------------------------------------------------------- 5. main contract & continuous series
def main_contract_by_day(ic_oi: pd.DataFrame) -> pd.Series:
    """主力 for day D = contract with max OI at close of D-1 among contracts not expiring before D.
    Known before D's open -> no look-ahead.  Index: trading date, value: contract."""
    oi = ic_oi.copy()
    oi["date"] = pd.to_datetime(oi["date"])
    oi["expiry"] = pd.to_datetime(oi["expiry"])
    days = pd.DatetimeIndex(sorted(oi["date"].unique()))
    best = (oi.sort_values(["date", "oi"], ascending=[True, False])
              .groupby("date").head(1).set_index("date")["contract"])
    main = best.shift(1).reindex(days)          # yesterday's max-OI contract
    # never trade a contract on/after its expiry day: fall back to today's next-max
    exp = oi.drop_duplicates("contract").set_index("contract")["expiry"]
    for d in days:
        c = main.get(d)
        if isinstance(c, str) and exp.get(c, pd.Timestamp.max) <= d:
            prev = oi[(oi["date"] < d)]
            if len(prev):
                lastday = prev["date"].max()
                cand = prev[(prev["date"] == lastday) & (prev["expiry"] > d)]
                if len(cand):
                    main.loc[d] = cand.sort_values("oi", ascending=False)["contract"].iloc[0]
    return main.dropna()


def build_main_series(ic_30m: pd.DataFrame, main: pd.Series) -> pd.DataFrame:
    """30m bars of the day's main contract + difference back-adjusted close for MA60.
    Roll gap measured at the switch day's first bar: adj = open(new) - prev_close(old) is NOT used
    (contains a real overnight move); we use the old/new close spread on the last common bar of D-1."""
    bars = ic_30m.copy()
    bars["datetime"] = pd.to_datetime(bars["datetime"])
    bars["date"] = bars["datetime"].dt.normalize()
    bars = bars.merge(main.rename("main").rename_axis("date").reset_index(), on="date")
    m = bars[bars["contract"] == bars["main"]].sort_values("datetime").reset_index(drop=True)

    # roll gaps
    m["roll"] = m["contract"] != m["contract"].shift(1)
    m.loc[0, "roll"] = False
    gap = pd.Series(0.0, index=m.index)
    for i in m.index[m["roll"]]:
        old, new = m.at[i - 1, "contract"], m.at[i, "contract"]
        t_prev = m.at[i - 1, "datetime"]
        o = bars[(bars["contract"] == old) & (bars["datetime"] == t_prev)]["close"]
        n = bars[(bars["contract"] == new) & (bars["datetime"] == t_prev)]["close"]
        if len(o) and len(n):
            gap.iat[i] = float(n.iloc[0] - o.iloc[0])
    # back-adjust history so the newest contract is unadjusted
    cum_future_gap = gap[::-1].cumsum()[::-1].shift(-1).fillna(0.0)
    m["close_cont"] = m["close"] + cum_future_gap
    m["open_cont"] = m["open"] + cum_future_gap
    m["roll_gap"] = gap
    return m


# ---------------------------------------------------------------- 6. backtest
def _fee(price: float, rate: float, cfg: Config) -> float:
    return price * cfg.multiplier * cfg.lots * rate


def backtest(series: pd.DataFrame, windows: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Bar-level event loop.  Decisions at bar close i, fills at open of bar i+1 (actual contract price
    +/- slippage).  Returns trade list (one row per round trip, rolls folded into the trade)."""
    s = series.copy()
    s["ma"] = s["close_cont"].rolling(cfg.ma_bars, min_periods=cfg.ma_bars).mean()
    s = s.merge(windows, left_on="date", right_index=True, how="left")
    s[["side", "setup_id"]] = s[["side", "setup_id"]].fillna({"side": 0, "setup_id": -1}).astype(int)

    slip = cfg.slippage_ticks * cfg.tick
    trades, pos = [], 0
    entry = None            # dict of open trade
    used_setups: set[int] = set()

    recs = s[["datetime", "date", "contract", "open", "close", "close_cont", "ma", "side", "setup_id"]] \
        .to_dict("records")
    for i in range(len(recs) - 1):
        r, nxt = recs[i], recs[i + 1]

        # ---- roll: next bar is a new contract while we hold -> close old at its last close, open new at next open
        if pos != 0 and nxt["contract"] != r["contract"]:
            exit_px = r["close"] - pos * slip
            entry["pnl_pts"] += pos * (exit_px - entry["px"])
            entry["fees"] += _fee(exit_px, cfg.fee_close, cfg)
            new_px = nxt["open"] + pos * slip
            entry["fees"] += _fee(new_px, cfg.fee_open, cfg)
            entry["px"], entry["open_date"] = new_px, nxt["date"]
            entry["rolls"] += 1

        # ---- execute order decided at previous bar close, at this bar's... (handled below at i+1 open)
        if pd.isna(r["ma"]):
            continue
        above, below = r["close_cont"] > r["ma"], r["close_cont"] < r["ma"]

        order = None
        if (pos == 1 and below) or (pos == -1 and above):
            order = ("close", "stop")
        if pos == 0 or (order is not None):
            sd, sid = int(r["side"]), int(r["setup_id"])
            fresh = not (cfg.one_entry_per_setup and sid in used_setups)
            if sd == -1 and below and fresh and pos != -1:
                order = ("open", -1, sid)
            elif sd == 1 and above and fresh and pos != 1:
                order = ("open", 1, sid)
        if order is None:
            continue

        fill_open = nxt["open"]
        # close existing
        if pos != 0:
            exit_px = fill_open - pos * slip
            same_day = nxt["date"] == entry["open_date"]
            rate = cfg.fee_close_today if same_day else cfg.fee_close
            entry["pnl_pts"] += pos * (exit_px - entry["px"])
            entry["fees"] += _fee(exit_px, rate, cfg)
            entry.update(exit_time=nxt["datetime"], exit_reason=order[1] if order[0] == "close" else "reverse")
            trades.append(entry)
            pos, entry = 0, None
        if order[0] == "open":
            side, sid = order[1], order[2]
            px = fill_open + side * slip
            entry = dict(side=side, setup_id=sid, entry_time=nxt["datetime"], open_date=nxt["date"],
                         contract=nxt["contract"], px=px, entry_px=px, pnl_pts=0.0,
                         fees=_fee(px, cfg.fee_open, cfg), rolls=0)
            used_setups.add(sid)
            pos = side

    if entry is not None:   # mark-to-market open trade at last close, flagged
        last = recs[-1]
        entry["pnl_pts"] += pos * (last["close"] - entry["px"])
        entry.update(exit_time=last["datetime"], exit_reason="open_at_end")
        trades.append(entry)

    t = pd.DataFrame(trades)
    if t.empty:
        return t
    t["pnl_cny"] = t["pnl_pts"] * cfg.multiplier * cfg.lots - t["fees"]
    t["notional"] = t["entry_px"] * cfg.multiplier * cfg.lots
    t["ret_notional"] = t["pnl_cny"] / t["notional"]
    return t.drop(columns=["px", "open_date"])


# ---------------------------------------------------------------- 7. metrics
def metrics(t: pd.DataFrame) -> dict:
    if t is None or t.empty:
        return {"n_trades": 0}
    w, l = t[t["pnl_cny"] > 0], t[t["pnl_cny"] <= 0]
    eq = t["pnl_cny"].cumsum()
    dd = (eq - eq.cummax()).min()
    avg_w, avg_l = w["pnl_cny"].mean(), -l["pnl_cny"].mean()
    return {
        "n_trades": int(len(t)),
        "win_rate": round(len(w) / len(t), 4),
        "payoff_ratio": round(avg_w / avg_l, 3) if len(w) and len(l) and avg_l > 0 else np.nan,
        "profit_factor": round(w["pnl_cny"].sum() / -l["pnl_cny"].sum(), 3) if len(l) and l["pnl_cny"].sum() < 0 else np.nan,
        "total_pnl_cny": round(float(t["pnl_cny"].sum()), 0),
        "total_fees_cny": round(float(t["fees"].sum()), 0),
        "max_dd_cny": round(float(dd), 0),
        "mean_ret_notional_bps": round(float(t["ret_notional"].mean() * 1e4), 2),
    }


def breakdown(t: pd.DataFrame) -> pd.DataFrame:
    if t.empty:
        return pd.DataFrame()
    rows = {"ALL": metrics(t), "LONG": metrics(t[t.side == 1]), "SHORT": metrics(t[t.side == -1])}
    for y, g in t.groupby(pd.to_datetime(t["entry_time"]).dt.year):
        rows[str(y)] = metrics(g)
    return pd.DataFrame(rows).T


# ---------------------------------------------------------------- null control
def null_test(res: dict, cfg: Config, n: int = 300, seed: int = 0) -> pd.DataFrame:
    """Primary falsifier.  Keep everything (30m MA60 entry/stop, costs, number of setups per side)
    and move the setup DATES to random eligible days inside the same segment.  If real breadth timing
    does not beat this distribution, the breadth indicator adds nothing beyond MA60 trend-following.
    Returns per-side actual PnL, null mean, and one-sided p-value (share of null >= actual)."""
    rng = np.random.default_rng(seed)
    st, ser = res["breadth"], res["series"]
    days = pd.DatetimeIndex(ser["date"].unique())
    lo, hi = pd.Timestamp(cfg.start), pd.Timestamp(cfg.dev_end)
    seg = (st.index >= lo) & (st.index <= hi) if res["segment"] == "dev" else st.index > hi
    pool = st.index[seg & st["pct"].notna().to_numpy()]
    real = st[seg & (st["setup"] != 0).to_numpy()]

    def side_pnl(t):
        if t.empty:
            return {1: 0.0, -1: 0.0}
        et = pd.to_datetime(t["entry_time"])
        t = t[(et >= lo) & (et <= hi)] if res["segment"] == "dev" else t[et > hi]
        return {k: float(t.loc[t.side == k, "pnl_cny"].sum()) for k in (1, -1)}

    actual = side_pnl(res["trades"])
    sims = []
    for _ in range(n):
        fake = pd.DataFrame({"setup": 0}, index=st.index)
        pick = rng.choice(pool, size=len(real), replace=False)
        fake.loc[pick, "setup"] = rng.permutation(real["setup"].to_numpy())
        sims.append(side_pnl(backtest(ser, setup_windows(fake, days, cfg), cfg)))
    sims = pd.DataFrame(sims)
    out = {}
    for k, name in ((1, "LONG"), (-1, "SHORT")):
        out[name] = {"actual_pnl": actual[k], "null_mean": sims[k].mean(), "null_p95": sims[k].quantile(.95),
                     "p_value": (1 + (sims[k] >= actual[k]).sum()) / (n + 1)}
    tot_a, tot_s = actual[1] + actual[-1], sims[1] + sims[-1]
    out["ALL"] = {"actual_pnl": tot_a, "null_mean": tot_s.mean(), "null_p95": tot_s.quantile(.95),
                  "p_value": (1 + (tot_s >= tot_a).sum()) / (n + 1)}
    return pd.DataFrame(out).T


# ---------------------------------------------------------------- plot
def plot_breadth(setups: pd.DataFrame, cfg: Config, path: str, title: str = "Daily breadth"):
    """情绪曲线 + 时点高/低区 + 拐头标记.  Zone bands are the PIT thresholds, so they move over time."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    b, p = setups["B"], setups["pct"]
    hi = b.expanding().quantile(cfg.high_pct).where(p.notna())
    lo = b.expanding().quantile(cfg.low_pct).where(p.notna())
    fig, ax = plt.subplots(figsize=(13, 4.5))
    ax.plot(b.index, b, lw=0.7, color="#3b6ea5", label=f"breadth ({cfg.measure})")
    ax.plot(hi.index, hi, lw=0.9, ls="--", color="#c0392b", label=f"PIT {cfg.high_pct:.0%} pct")
    ax.plot(lo.index, lo, lw=0.9, ls="--", color="#27885a", label=f"PIT {cfg.low_pct:.0%} pct")
    s, l = setups[setups.setup == -1], setups[setups.setup == 1]
    ax.scatter(s.index, s.B, marker="v", s=14, color="#c0392b", label="short setup", zorder=3)
    ax.scatter(l.index, l.B, marker="^", s=14, color="#27885a", label="long setup", zorder=3)
    ax.set_title(title); ax.legend(loc="upper left", fontsize=8, ncol=5, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


# ---------------------------------------------------------------- holdout seal + trial ledger
class HoldoutSealed(RuntimeError):
    pass


class NotFrozen(RuntimeError):
    pass


def _ledger_row(ledger: Path, cfg: Config, segment: str, n_trades, note: str, data: str):
    row = pd.DataFrame([{"ts": pd.Timestamp.now().isoformat(timespec="seconds"), "config": cfg.digest(),
                         "segment": segment, "data": data, "n_trades": n_trades,
                         "params": json.dumps(dataclasses.asdict(cfg), sort_keys=True), "note": note}])
    row.to_csv(ledger, mode="a", header=not ledger.exists(), index=False)


def freeze(cfg: Config, ledger, note: str) -> str:
    """Record the frozen rule set BEFORE any real-data P&L exists.  Computes nothing.  One freeze per digest."""
    ledger = Path(ledger)
    if ledger.exists():
        L = pd.read_csv(ledger)
        if ((L["config"] == cfg.digest()) & (L["segment"] == "freeze")).any():
            raise ValueError(f"config {cfg.digest()} already frozen")
    _ledger_row(ledger, cfg, "freeze", "", note, "none")
    return cfg.digest()


def run(stocks, ic_30m, ic_oi, cfg: Config, segment: str = "dev", ledger: Path | None = None,
        note: str = "", data: str = "real") -> dict:
    """segment: 'dev' (start..dev_end) or 'holdout' (dev_end..end).
    data='real'      : requires a ledger and a prior freeze() of this exact config digest (dev AND holdout).
                       Any IC P&L on real data - including the recent 180-day window - is a trial.
    data='synthetic' : plumbing tests only; dev runs need no freeze; holdout still needs one.
    Holdout is one-shot per digest."""
    ledger = Path(ledger) if ledger else None
    if data not in ("real", "synthetic"):
        raise ValueError("data must be 'real' or 'synthetic'")
    L = pd.read_csv(ledger) if ledger is not None and ledger.exists() else None
    frozen = L is not None and ((L["config"] == cfg.digest()) & (L["segment"] == "freeze")).any()
    if data == "real" and not frozen:
        raise NotFrozen(f"real-data run refused: config {cfg.digest()} has no freeze() entry in the ledger")
    if segment == "holdout":
        if not frozen:
            raise HoldoutSealed(f"config {cfg.digest()} not frozen; holdout stays sealed")
        if ((L["config"] == cfg.digest()) & (L["segment"] == "holdout")).any():
            raise HoldoutSealed("holdout already consumed for this config (one-shot)")

    br = stock_breadth(stocks, cfg)
    setups = daily_setups(br, cfg)
    main = main_contract_by_day(ic_oi)
    ser = build_main_series(ic_30m, main)
    win = setup_windows(setups, pd.DatetimeIndex(ser["date"].unique()), cfg)
    trades = backtest(ser, win, cfg)

    lo, hi = pd.Timestamp(cfg.start), pd.Timestamp(cfg.dev_end)
    if not trades.empty:
        et = pd.to_datetime(trades["entry_time"])
        trades = trades[(et >= lo) & (et <= hi)] if segment == "dev" else trades[et > hi]

    res = {"config": cfg.digest(), "segment": segment, "metrics": metrics(trades),
           "breakdown": breakdown(trades), "trades": trades, "breadth": setups, "series": ser}
    if ledger is not None:
        _ledger_row(ledger, cfg, segment, res["metrics"].get("n_trades", 0), note, data)
    return res
