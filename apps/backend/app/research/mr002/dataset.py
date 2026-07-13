"""MR-002 PIT dataset assembly — FROZEN v1.0 (immutable).

Reads ONLY the frozen research store and produces the per-session `DayInputs` the
runner consumes. Every field is point-in-time by construction: a value attached to
decision-session t is derived from data available at or before the close of t.

Window bounding is explicit: the caller passes [start, end]; warm-up history is
read BEFORE the start (that is required and legitimate — it is past data), but no
session on/after `end` is ever emitted, so the validation and sealed-OOS windows
stay unread.
"""

from __future__ import annotations

from datetime import date

import duckdb
import numpy as np

from app.research.mr002.eligibility import (
    Anchor,
    EarningsBlackout,
    SectorResolver,
)
from app.research.mr002.runner import DayInputs
from app.research.mr002.signal import (
    LOOKBACK,
    arithmetic_returns,
    residual_zscores,
    sector_residuals,
    stock_residuals,
)

ETF_LIVE = {"XLC": date(2018, 6, 19), "XLRE": date(2015, 10, 8)}
WARMUP_SESSIONS = 200        # >= LOOKBACK + 60 z-observations + 5-day window


def _d(x):
    return x.date() if hasattr(x, "date") else x


class FrozenDataset:
    def __init__(self, store: str) -> None:
        self.con = duckdb.connect(store, read_only=True)

    # ---------- frozen identity / sector chain ----------
    def sector_resolver(self) -> SectorResolver:
        xw: dict[int, list] = {}
        for p, c, f, t in self.con.execute(
                "SELECT permaticker, cik, effective_from, effective_to FROM crosswalk "
                "WHERE cik IS NOT NULL").fetchall():
            xw.setdefault(int(p), []).append([_d(f), _d(t) if t else None, int(c)])
        # apply the countersigned predecessor overrides: split at the event date
        from datetime import timedelta
        for r in self.con.execute(
                "SELECT permaticker, predecessor_cik, successor_cik, event_date "
                "FROM predecessor_overrides WHERE review_status = 'approved'").fetchall():
            perma, pred, succ, ev = int(r[0]), int(r[1]), int(r[2]), _d(r[3])
            if isinstance(ev, str):
                ev = date.fromisoformat(ev)
            new = []
            for f, t, c in xw.get(perma, []):
                if c == succ and f < ev:
                    new.append([f, ev - timedelta(days=1), pred])
                    new.append([ev, t, succ])
                else:
                    new.append([f, t, c])
            xw[perma] = new

        segs: dict[int, list] = {}
        rows = self.con.execute(
            "SELECT cik, accepted_utc, sic FROM sic_observations ORDER BY cik, "
            "accepted_utc").fetchall()
        by_cik: dict[int, list] = {}
        for c, ts, sic in rows:
            by_cik.setdefault(int(c), []).append(
                (_d(ts), str(int(float(sic))).zfill(4)))
        for cik, oo in by_cik.items():
            seq = []
            for dt, sic in oo:
                if seq and seq[-1][2] == sic:
                    continue
                if seq:
                    seq[-1] = (seq[-1][0], dt, seq[-1][2])
                seq.append((dt, None, sic))
            segs[cik] = seq          # NO forward-fill before the first observation
        mapping = [dict(zip([d[0] for d in self.con.description], r, strict=False))
                   for r in self.con.execute("SELECT * FROM sic_mapping").fetchall()]
        ovr = [dict(zip([d[0] for d in self.con.description], r, strict=False))
               for r in self.con.execute(
                   "SELECT * FROM security_sector_overrides").fetchall()]
        return SectorResolver(xw, segs, mapping, ovr, ETF_LIVE)

    # ---------- frozen V1 anchors ----------
    def blackouts(self, sessions: list[date], resolver: SectorResolver,
                  permas: list[int]) -> dict[int, EarningsBlackout]:
        rows = self.con.execute(
            "SELECT cik, session_date, availability_class, event_time_basis "
            "FROM anchors").fetchall()
        by_cik: dict[int, list[Anchor]] = {}
        for c, sd, ac, basis in rows:
            by_cik.setdefault(int(c), []).append(Anchor(_d(sd), ac, basis))
        out: dict[int, EarningsBlackout] = {}
        for pt in permas:
            anchors: list[Anchor] = []
            for f, t, cik in resolver.crosswalk.get(pt, []):
                for a in by_cik.get(cik, []):
                    if f <= a.session_date and (t is None or a.session_date <= t):
                        anchors.append(a)
            out[pt] = EarningsBlackout(anchors, sessions)
        return out

    # ---------- the PIT day stream ----------
    def day_inputs(self, start: date, end: date) -> list[DayInputs]:
        """Emit DayInputs for every session in [start, end]. Warm-up history before
        `start` is read (past data); nothing on/after `end` is emitted."""
        sessions = [_d(r[0]) for r in self.con.execute(
            "SELECT DISTINCT date FROM etf_prices WHERE ticker='SPY' "
            "AND date <= ? ORDER BY date", [end]).fetchall()]
        if not sessions:
            return []
        s_idx = {d: i for i, d in enumerate(sessions)}
        first = max(0, s_idx[min(sessions, key=lambda d: abs((d - start).days))]
                    - WARMUP_SESSIONS)
        window = sessions[first:]

        # ---- factors: SPY + orthogonalized sector residuals (PIT-recursive) ----
        etf = {}
        for sym in ("SPY", "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE",
                    "XLU", "XLV", "XLY"):
            px = dict(self.con.execute(
                "SELECT date, adjclose FROM etf_prices WHERE ticker=? ORDER BY date",
                [sym]).fetchall())
            etf[sym] = np.array([px.get(d, np.nan) for d in window], dtype=float)
        spy_ret = arithmetic_returns(etf["SPY"])
        u_sector = {sym: sector_residuals(arithmetic_returns(etf[sym]), spy_ret)
                    for sym in etf if sym != "SPY"}

        # ---- universe membership (monthly PIT) ----
        uni = {}
        for m, tick, perma, long_ok, short_ok in self.con.execute(
                "SELECT universe_month, ticker, permaticker, in_long_universe, "
                "in_short_universe FROM universe").fetchall():
            uni.setdefault(_d(m), []).append((int(perma), tick, bool(long_ok),
                                              bool(short_ok)))
        months = sorted(uni)

        def universe_at(d: date):
            m = None
            for x in months:
                if x <= d:
                    m = x
                else:
                    break
            return uni.get(m, [])

        permas = sorted({p for rows in uni.values() for p, _t, _l, _s in rows})
        resolver = self.sector_resolver()
        blackouts = self.blackouts(window, resolver, permas)

        # ---- prices (four frozen series) ----
        px = {}
        for pt, tick in {p: t for rows in uni.values() for p, t, _l, _s in rows}.items():
            rows = self.con.execute(
                "SELECT date, open, close, closeadj, volume FROM prices "
                "WHERE ticker=? ORDER BY date", [tick]).fetchall()
            if not rows:
                continue
            idx = {_d(r[0]): r for r in rows}
            px[pt] = (tick, idx)

        # ---- per-security signals over the window ----
        sig: dict[int, dict] = {}
        for pt, (_tick, idx) in px.items():
            closeadj = np.array([idx[d][3] if d in idx else np.nan for d in window],
                                dtype=float)
            if np.isnan(closeadj).all():
                continue
            ret = arithmetic_returns(closeadj)
            sig[pt] = {"ret": ret, "eps": None, "z": None, "sigma": None,
                       "beta": None, "sector_by_day": {}}

        # cache residuals per (security, sector) — the sector can change over time,
        # so residuals are computed against the sector series that is PIT-valid.
        for pt in list(sig):
            sec_series = np.full(len(window), np.nan)
            sec_name: list[str | None] = []
            for i, d in enumerate(window):
                s, _why = resolver.sector_etf(pt, d)
                sec_name.append(s)
                if s and s in u_sector:
                    sec_series[i] = u_sector[s][i]
            eps = stock_residuals(sig[pt]["ret"], spy_ret, sec_series)
            z = residual_zscores(eps)
            # sigma of the 5-day cumulative residual (the sizing input)
            r5 = np.full(len(window), np.nan)
            for t in range(4, len(window)):
                w = eps[t - 4:t + 1]
                if not np.isnan(w).any():
                    r5[t] = w.sum()
            sigma = np.full(len(window), np.nan)
            for t in range(len(window)):
                hist = r5[max(0, t - 60):t]
                if len(hist) >= 60 and not np.isnan(hist).any():
                    sigma[t] = np.std(hist, ddof=1)
            # market beta from the same rolling window (for the beta cap)
            beta = np.full(len(window), np.nan)
            for t in range(LOOKBACK, len(window)):
                y = sig[pt]["ret"][t - LOOKBACK:t]
                x = spy_ret[t - LOOKBACK:t]
                if np.isnan(y).any() or np.isnan(x).any() or np.std(x, ddof=1) == 0:
                    continue
                beta[t] = float(np.cov(y, x, ddof=1)[0, 1] / np.var(x, ddof=1))
            sig[pt].update({"eps": eps, "z": z, "sigma": sigma, "beta": beta,
                            "sector": sec_name})
        self._sig = sig
        self._window = window
        self._px = px
        self._resolver = resolver
        self._blackouts = blackouts
        self._uni_at = universe_at
        return self._emit(start, end)

    def _emit(self, start: date, end: date) -> list[DayInputs]:
        window, sig, px = self._window, self._sig, self._px
        out: list[DayInputs] = []
        # announced corporate actions (announcement-dated)
        acts: dict[str, list] = {}
        for tick, d, action in self.con.execute(
                "SELECT ticker, date, action FROM actions").fetchall():
            acts.setdefault(tick, []).append((_d(d), action))

        for i, d in enumerate(window):
            if d < start or d > end:
                continue
            nxt = window[i + 1] if i + 1 < len(window) else None
            if nxt is None or nxt > end:
                nxt = None                      # never execute beyond the window
            members = self._uni_at(d)

            # ---- EXECUTION-PRICE SERIES (erratum, Defect A) ------------------------
            # Built from the price store for EVERY security with a bar, BEFORE and
            # INDEPENDENT of the entry-eligibility funnel below. A held position must
            # never lose its execution price because its symbol left the ranking
            # universe, its z went non-finite, or its entry sector failed to resolve.
            exec_open, exec_close_next, exec_close_t = {}, {}, {}
            for pt_all, (_tk, idx_all) in px.items():
                rt = idx_all.get(d)
                if rt is not None and rt[2]:
                    exec_close_t[pt_all] = float(rt[2])
                rn = idx_all.get(nxt) if nxt else None
                if rn is not None:
                    if rn[1] and float(rn[1]) > 0:
                        exec_open[pt_all] = float(rn[1])
                    if rn[2]:
                        exec_close_next[pt_all] = float(rn[2])

            z, sigma, beta, sector, tickers = {}, {}, {}, {}, {}
            long_e, short_e = set(), set()
            open_next, close_t, close_next, dist_next, adv = {}, {}, {}, {}, {}
            bo_exit, ac_exit, confirm = set(), set(), {}
            for pt, tick, long_ok, short_ok in members:
                s = sig.get(pt)
                if not s or pt not in px:
                    continue
                zi = s["z"][i]
                if not np.isfinite(zi):
                    continue
                sec = s["sector"][i]
                if not sec:                     # unresolved sector => INELIGIBLE
                    continue
                idx = px[pt][1]
                row_t = idx.get(d)
                row_n = idx.get(nxt) if nxt else None
                if row_t is None:
                    continue
                z[pt] = float(zi)
                sigma[pt] = float(s["sigma"][i]) if np.isfinite(s["sigma"][i]) else np.nan
                beta[pt] = float(s["beta"][i]) if np.isfinite(s["beta"][i]) else 0.0
                sector[pt] = sec
                tickers[pt] = tick
                close_t[pt] = float(row_t[2])
                if row_n:
                    open_next[pt] = float(row_n[1])
                    close_next[pt] = float(row_n[2])
                dist_next[pt] = 0.0             # dividends handled via ACTIONS below
                # 20-session median dollar volume (close x volume — the frozen pair)
                hist = [idx[w] for w in window[max(0, i - 19):i + 1] if w in idx]
                dv = sorted(r[2] * r[4] for r in hist if r[2] and r[4])
                adv[pt] = float(dv[len(dv) // 2]) if dv else 0.0
                # gates
                bo = self._blackouts.get(pt)
                if bo and nxt:
                    ok, _why = bo.entry_allowed(d, nxt)
                    if ok:
                        if long_ok:
                            long_e.add(pt)
                        if short_ok:
                            short_e.add(pt)
                    if bo.must_exit(d, nxt):
                        bo_exit.add(pt)
                for ad, action in acts.get(tick, []):
                    if ad <= d and action in ("acquisitionby", "delisted", "bankruptcy"):
                        ac_exit.add(pt)
                        long_e.discard(pt)
                        short_e.discard(pt)
            out.append(DayInputs(d, nxt, z, sigma, beta, sector, long_e, short_e,
                                 open_next, close_t, close_next, dist_next, adv,
                                 tickers, bo_exit, ac_exit, confirm,
                                 exec_open, exec_close_next, exec_close_t))
        return out
