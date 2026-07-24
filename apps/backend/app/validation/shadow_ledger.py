"""Non-ordering shadow ledger for the equal-weight forward-validation program (PREREG v1.0 §5.3).

The forward validation runs the EXACT frozen momentum-daily strategy against a **non-ordering shadow
ledger** — a durable, simulated portfolio that NEVER routes an order through the broker / OrderRouter and
NEVER touches Account 4 capital, positions, or the retired 84466.41 baseline. Each eligible session the
runner (built on top of this module) marks the book to market, asks the strategy for target weights,
applies them through the frozen cost model, and advances the ledger by one session.

FIDELITY IS LOAD-BEARING. `ShadowLedger.step()` is a faithful transcription of the §7A-proven Stage-4
transition in `drift_audit_driver.capture_replica_seams` (mark-to-market → trade gate
`changed|regime_flip|drift|backstop` → turnover cost `equity *= 1 - bps/1e4 * turnover` → same-session
rebalance). It does NOT modify that frozen reference; instead a regression test drives this ledger over
the census days and asserts it reproduces the reference SeamRecords + equity path byte-for-byte. If the
two ever diverge, the test fails — a divergence would be an INVALID_RUN, not a performance result.

The registered inputs (PREREG §2 / §7): starting capital is a GOVERNED input (owner-set; NOT 84466.41,
NOT Account 4 capital); the base cost is `TURNOVER_COST_BPS = 10.0` (the ×1/×2/×3 stress lives in the
adjudicator, not here — this ledger carries the base run). Nothing in this module imports the order path.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from app.strategies.drift_audit import SeamRecord
from app.validation.first_session import Durability, default_durability


class DayScores(Protocol):
    """Duck-typed daily scores the strategy produces: ranked (best-first), score, rank."""
    ranked: list[str]
    score: dict[str, float]
    rank: dict[str, int]

# Registered base transaction cost (bps of turnover), PREREG §2. The stress multipliers ×1/×2/×3 are
# applied by the §7F adjudicator over the sealed record — they are NOT baked into the base ledger.
TURNOVER_COST_BPS = 10.0

# The governed starting capital for the forward-validation shadow ledger (owner-set 2026-07-23).
# NOT the retired 84466.41 baseline and NOT Account 4 capital.
FORWARD_STARTING_CAPITAL = 100_000.0

# The retired baseline that must never be reused as the research ledger (guard).
_RETIRED_BASELINE = 84466.41

SelectFn = Callable[[DayScores, "set[str]", "dict[str, int] | None"], "list[str]"]
WeighFn = Callable[["list[str]", date], "dict[str, float]"]
PriceFn = Callable[[str, date], "float | None"]


class ShadowLedgerError(Exception):
    """A governance/integrity violation in the shadow ledger (e.g. a forbidden starting capital)."""


@dataclass
class ShadowLedgerState:
    """The full durable state carried across sessions — the exact variables of the proven transition."""
    equity: float
    cash: float
    sleeves: dict[str, float]                 # ticker -> current notional
    target_w: dict[str, float]                # last applied gross-scaled target weights
    last_px: dict[str, float]                  # last mark price per held name
    held: list[str]                            # sorted for deterministic serialization; set semantics in use
    since: int                                 # sessions since the last rebalance
    prev_rank: dict[str, int] | None
    applied_gross: float
    sessions_processed: int = 0
    starting_capital: float = FORWARD_STARTING_CAPITAL


@dataclass
class SessionOutcome:
    """One session's result: the decision seam record plus the (sealed) performance deltas."""
    record: SeamRecord                         # decision seams (comparable to capture_replica_seams)
    traded: bool
    equity_before: float
    equity_after: float
    session_return: float                      # (equity_after / equity_before) - 1, mark-to-market + cost
    turnover: float
    cost_drag: float                           # equity lost to transaction cost this session


@dataclass
class ShadowLedger:
    """A durable non-ordering shadow portfolio. Config is frozen at construction; state advances per step."""
    turnover_cost_bps: float
    backstop_days: int
    weight_drift_pct: float
    state: ShadowLedgerState

    @classmethod
    def start(cls, *, starting_capital: float = FORWARD_STARTING_CAPITAL,
              turnover_cost_bps: float = TURNOVER_COST_BPS,
              backstop_days: int, weight_drift_pct: float) -> ShadowLedger:
        """Open a fresh ledger at the governed starting capital (fully in cash, no positions)."""
        if starting_capital <= 0:
            raise ShadowLedgerError(f"starting capital must be positive, got {starting_capital}")
        if abs(starting_capital - _RETIRED_BASELINE) < 1e-6:
            raise ShadowLedgerError(
                f"starting capital {starting_capital} is the retired 84466.41 baseline — forbidden")
        return cls(
            turnover_cost_bps=turnover_cost_bps, backstop_days=backstop_days,
            weight_drift_pct=weight_drift_pct,
            state=ShadowLedgerState(
                equity=starting_capital, cash=starting_capital, sleeves={}, target_w={},
                last_px={}, held=[], since=0, prev_rank=None, applied_gross=1.0,
                sessions_processed=0, starting_capital=starting_capital))

    def step(self, d: date, ds: DayScores | None, g: float, *,
             select_fn: SelectFn, weigh_fn: WeighFn, price_fn: PriceFn) -> SessionOutcome:
        """Advance the ledger by ONE session. Faithful transcription of the §7A-proven Stage-4 transition
        (`capture_replica_seams` loop body). `ds` is the day's DayScores (or None for a thin day)."""
        s = self.state
        equity_before = s.equity
        self._mark_to_market(d, price_fn)

        if ds is None:                                    # thin day: no decision
            s.since += 1
            s.sessions_processed += 1
            rec = SeamRecord(date=d.isoformat(), scores={}, eligible=(), ranking=(),
                             target_names=(), weights={}, regime_gross=g,
                             trade_initiated=False, trigger="no_scores")
            return SessionOutcome(record=rec, traded=False, equity_before=equity_before,
                                  equity_after=s.equity, session_return=_ret(equity_before, s.equity),
                                  turnover=0.0, cost_drag=0.0)

        held_set = set(s.held)
        target = select_fn(ds, held_set, s.prev_rank)
        s.prev_rank = ds.rank
        changed = set(target) != held_set
        regime_flip = abs(g - s.applied_gross) > 1e-9
        drift = bool(s.held and s.equity > 0 and s.target_w and max(
            abs(s.sleeves.get(tk, 0.0) / s.equity - s.target_w.get(tk, 0.0)) for tk in s.held)
            > self.weight_drift_pct)
        backstop = s.since >= self.backstop_days
        trade = bool(changed or regime_flip or drift or backstop)

        base = weigh_fn(target, d) if (g > 0.0 and target) else {}
        neww = {tk: w * g for tk, w in base.items()}
        trig = "+".join(t for t, on in (("changed", changed), ("regime_flip", regime_flip),
                        ("drift", drift), ("backstop", backstop)) if on) or "reviewed_no_trigger"
        rec = SeamRecord(
            date=d.isoformat(), scores=dict(ds.score),
            eligible=tuple(ds.ranked), ranking=tuple(ds.ranked),
            target_names=tuple(target), weights=neww, regime_gross=g,
            trade_initiated=trade, trigger=trig)

        if not trade:
            s.since += 1
            s.sessions_processed += 1
            return SessionOutcome(record=rec, traded=False, equity_before=equity_before,
                                  equity_after=s.equity, session_return=_ret(equity_before, s.equity),
                                  turnover=0.0, cost_drag=0.0)

        turnover, cost_drag = self._apply_rebalance(d, neww, g, price_fn)
        s.sessions_processed += 1
        return SessionOutcome(record=rec, traded=True, equity_before=equity_before,
                              equity_after=s.equity, session_return=_ret(equity_before, s.equity),
                              turnover=turnover, cost_drag=cost_drag)

    def book_decision(self, d: date, record: SeamRecord, *, price_fn: PriceFn) -> SessionOutcome:
        """Book an EXTERNALLY-computed decision (from the live MomentumDaily instrument) into the ledger
        using the REGISTERED turnover-cost accounting. Same proven MTM + turnover-cost transition as
        `step()` — the decision (`record.weights` = the gross-scaled targets, `record.trade_initiated`)
        is INJECTED, not recomputed. This is the Option-B integration point: the real production strategy
        decides; the shadow ledger accounts at the registered `TURNOVER_COST_BPS`."""
        s = self.state
        equity_before = s.equity
        self._mark_to_market(d, price_fn)

        if not record.trade_initiated:
            s.since += 1
            s.sessions_processed += 1
            return SessionOutcome(record=record, traded=False, equity_before=equity_before,
                                  equity_after=s.equity, session_return=_ret(equity_before, s.equity),
                                  turnover=0.0, cost_drag=0.0)

        neww = dict(record.weights)
        turnover, cost_drag = self._apply_rebalance(d, neww, record.regime_gross, price_fn)
        s.sessions_processed += 1
        return SessionOutcome(record=record, traded=True, equity_before=equity_before,
                              equity_after=s.equity, session_return=_ret(equity_before, s.equity),
                              turnover=turnover, cost_drag=cost_drag)

    # ── shared accounting primitives (used by step() and book_decision) ─────────────────────────────
    def _mark_to_market(self, d: date, price_fn: PriceFn) -> None:
        """Mark held sleeves to the session's prices and refresh equity (simulate 177-188)."""
        s = self.state
        if s.held:
            for tk in list(s.held):
                p = price_fn(tk, d)
                if p is not None:
                    lp = s.last_px.get(tk, 0.0)
                    if lp > 0:
                        s.sleeves[tk] *= 1.0 + (p / lp - 1.0)
                    s.last_px[tk] = p
            s.equity = sum(s.sleeves.values()) + s.cash

    def _apply_rebalance(self, d: date, neww: dict[str, float], gross: float,
                         price_fn: PriceFn) -> tuple[float, float]:
        """Apply a rebalance to the gross-scaled target weights `neww`: turnover cost at the registered
        bps, then re-sleeve. Returns (turnover, cost_drag). Mutates state (incl. `since = 0`)."""
        s = self.state
        cash_w = 1.0 - sum(neww.values())
        curw = {tk: (s.sleeves.get(tk, 0.0) / s.equity if s.equity > 0 else 0.0)
                for tk in set(s.sleeves) | set(neww)}
        cur_cash_w = s.cash / s.equity if s.equity > 0 else 0.0
        turnover = 0.5 * (sum(abs(neww.get(k, 0.0) - curw.get(k, 0.0))
                          for k in set(neww) | set(curw)) + abs(cash_w - cur_cash_w))
        equity_pre_cost = s.equity
        s.equity *= 1.0 - (self.turnover_cost_bps / 1e4) * turnover
        cost_drag = equity_pre_cost - s.equity
        s.sleeves = {tk: w * s.equity for tk, w in neww.items()}
        s.cash = cash_w * s.equity
        s.last_px = {tk: (price_fn(tk, d) or 0.0) for tk in neww}
        s.target_w = dict(neww)
        s.held = sorted(neww)                             # set semantics; sorted only for serialization
        s.applied_gross = gross
        s.since = 0
        return turnover, cost_drag

    # ── durability ────────────────────────────────────────────────────────────────────────────────
    def to_json(self) -> str:
        return json.dumps({
            "turnover_cost_bps": self.turnover_cost_bps, "backstop_days": self.backstop_days,
            "weight_drift_pct": self.weight_drift_pct, "state": asdict(self.state),
        }, sort_keys=True, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> ShadowLedger:
        d = json.loads(raw)
        return cls(turnover_cost_bps=d["turnover_cost_bps"], backstop_days=d["backstop_days"],
                   weight_drift_pct=d["weight_drift_pct"], state=ShadowLedgerState(**d["state"]))

    def save(self, path: Path, *, durability: Durability | None = None) -> None:
        """Atomically persist the ledger with FULL rename durability: write temp → fsync the temp file
        → os.replace → fsync the PARENT DIRECTORY. Fails closed on any durability error (production
        Linux — the parent-dir fsync failure is NOT suppressed). A pre-rename failure removes the temp
        and NEVER deletes the authoritative existing ledger; a post-replace fsync failure is reported as
        a failure (the new file is on disk but its rename durability is not guaranteed)."""
        dur = durability or default_durability()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_json().encode("utf-8")
        tmp = path.with_suffix(path.suffix + ".tmp")
        replaced = False
        try:
            with open(tmp, "wb") as f:
                f.write(data)
                f.flush()
            dur.fsync_file(tmp)                 # (1) temp durable BEFORE replace (injectable; fails closed)
            os.replace(tmp, path)               # (2) atomic swap
            replaced = True
            dur.fsync_dir(path.parent)          # (3) parent-dir fsync AFTER replace (rename durability)
        except BaseException:
            if not replaced:                    # pre-rename failure: drop the temp, keep the real ledger
                with contextlib.suppress(OSError):
                    tmp.unlink()
            raise

    @classmethod
    def load(cls, path: Path) -> ShadowLedger:
        return cls.from_json(path.read_text(encoding="utf-8"))


def _ret(before: float, after: float) -> float:
    return (after / before - 1.0) if before > 0 else 0.0
