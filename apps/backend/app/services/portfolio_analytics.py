"""Portfolio Analytics Engine — reusable cross-account portfolio-engineering metrics.

Per report-review.md: today's real lesson wasn't that momentum lost, it was that
three accounts lost in lockstep — a *portfolio correlation* problem. This engine
measures that as a standing platform capability (not momentum-specific):

  Strategies → Portfolio Analytics Engine → Daily Report v2 (+ future endpoints/UI)

It computes, across accounts, from data we already have:
  - return-correlation matrix   (from equity snapshots → daily returns)
  - holdings overlap %          (from positions — Jaccard of symbols)
  - a diversification score     (100 = independent bets; low = correlated)

Read-only; touches no trading state. Pure-python stats so it is trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.equity_snapshot import EquitySnapshot
from app.db.models.position import Position
from app.db.models.symbol import Symbol

# ---- pure stats (unit-tested) --------------------------------------------------

def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation of two equal-length series; None if < 3 points or a
    series is constant."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return cov / (vx ** 0.5 * vy ** 0.5)


def jaccard(a: set[str], b: set[str]) -> float:
    """Symbol-set overlap in [0,1]. 1.0 = identical holdings."""
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def diversification_score(corrs: list[float]) -> int:
    """0-100 from the pairwise correlations (100 = uncorrelated / well diversified).
    Uses the average *positive* correlation — negative/uncorrelated pairs are the
    diversification we want, so they don't penalize."""
    pos = [c for c in corrs if c is not None and c > 0]
    if not pos:
        return 100
    return max(0, round(100 * (1 - sum(pos) / len(pos))))


# ---- results -------------------------------------------------------------------

@dataclass
class PairMetric:
    a: int
    b: int
    a_label: str
    b_label: str
    correlation: float | None
    overlap_pct: float
    n_days: int


@dataclass
class PortfolioAnalytics:
    as_of: datetime
    window_days: int
    pairs: list[PairMetric] = field(default_factory=list)
    diversification: int = 100
    highest_corr: PairMetric | None = None   # the pair most in lockstep

    @property
    def correlation_status(self) -> str:
        if self.highest_corr and self.highest_corr.correlation is not None:
            c = self.highest_corr.correlation
            if c >= 0.9:
                return "High"
            if c >= 0.6:
                return "Medium"
        return "Low"


# ---- engine --------------------------------------------------------------------

async def _daily_returns(
    session: AsyncSession, account_ids: list[int], window_days: int
) -> dict[int, dict]:
    """Per account: {date: daily_return} from equity snapshots (last snapshot per ET
    day → pct change). Returns dates keyed by ISO string for easy alignment."""
    since = datetime.now(UTC) - timedelta(days=window_days + 5)
    out: dict[int, dict] = {}
    for aid in account_ids:
        rows = (
            await session.execute(
                select(EquitySnapshot.ts, EquitySnapshot.equity)
                .where(EquitySnapshot.account_id == aid, EquitySnapshot.ts >= since)
                .order_by(EquitySnapshot.ts.asc())
            )
        ).all()
        # last equity per calendar day
        by_day: dict[str, float] = {}
        for ts, eq in rows:
            by_day[ts.date().isoformat()] = float(eq)
        days = sorted(by_day)
        rets: dict[str, float] = {}
        for i in range(1, len(days)):
            prev, cur = by_day[days[i - 1]], by_day[days[i]]
            if prev > 0:
                rets[days[i]] = cur / prev - 1.0
        out[aid] = rets
    return out


async def _holdings(session: AsyncSession, account_ids: list[int]) -> dict[int, set[str]]:
    tickers = {
        s.id: s.ticker
        for s in (await session.execute(select(Symbol))).scalars().all()
    }
    out: dict[int, set[str]] = {aid: set() for aid in account_ids}
    for p in (
        await session.execute(select(Position).where(Position.qty != 0))
    ).scalars().all():
        if p.account_id in out:
            out[p.account_id].add(tickers.get(p.symbol_id, str(p.symbol_id)))
    return out


async def compute(
    session: AsyncSession,
    accounts: list[tuple[int, str]],  # (account_id, label)
    window_days: int = 30,
) -> PortfolioAnalytics:
    """Compute the cross-account correlation matrix + holdings overlap + score."""
    account_ids = [a for a, _ in accounts]
    label = dict(accounts)
    returns = await _daily_returns(session, account_ids, window_days)
    holdings = await _holdings(session, account_ids)

    pa = PortfolioAnalytics(as_of=datetime.now(UTC), window_days=window_days)
    corrs: list[float] = []
    for i, ai in enumerate(account_ids):
        for aj in account_ids[i + 1:]:
            common = sorted(set(returns[ai]) & set(returns[aj]))
            xs = [returns[ai][d] for d in common]
            ys = [returns[aj][d] for d in common]
            c = pearson(xs, ys)
            pm = PairMetric(
                a=ai, b=aj, a_label=label[ai], b_label=label[aj],
                correlation=c, overlap_pct=round(100 * jaccard(holdings[ai], holdings[aj]), 1),
                n_days=len(common),
            )
            pa.pairs.append(pm)
            if c is not None:
                corrs.append(c)
                if pa.highest_corr is None or (
                    pa.highest_corr.correlation is None or c > pa.highest_corr.correlation
                ):
                    pa.highest_corr = pm
    pa.diversification = diversification_score(corrs)
    return pa
