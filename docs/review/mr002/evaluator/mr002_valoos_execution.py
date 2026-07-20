"""MR-002 validation/OOS evaluator — synthetic execution + trade ledger (Increment 2, hardened v1.1).

Pure, synthetic-only. Applies the frozen next-open execution semantics and the frozen cost model to
synthetic trade intents and emits an immutable trade ledger. Reads NO real dataset; performs NO
signal generation, universe reconstruction, sector mapping, portfolio optimization, or exposure
constraints (those are Increment 3 and are NOT implemented here). Only the mechanical execution
controls (2% trailing-ADV participation clip, 1.5% NAV new-entry cap, clip-never-delay) are applied.

Next-open semantics (frozen; horizon 6, seam_rule realization_horizon_governing = 6):
  * signal decision after close t  -> entry at the official open of session t+1
  * exit decision after close e    -> exit at the official open of session e+1
  * time-stop                      -> exit at the official open of session t+6 (scheduled at entry)
  * missing entry open at t+1       -> ENTRY_CANCELLED (order cancelled; no position)
  * missing exit open               -> remain PENDING until the next valid official open (deferred)
  * no same-open re-entry           -> a new entry that would fill at the SAME session as a prior
                                       exit fill for that symbol is refused (ENTRY_REFUSED_SAME_OPEN)
  * clip, never delay               -> ADV/NAV-clipped quantity is dropped to cash, not carried

v1.1 hardening (adjudication 2026-07-20):
  1. Event-level decision provenance: every event carries decision_type + the CAUSAL decision_session
     (entry signal t; explicit exit e; time-stop t+5 = TIME_STOP_SCHEDULED_AT_ENTRY). Entry decision
     date is NEVER stamped on an exit event.
  2. Borrow accrues over ELAPSED CALENDAR DAYS from explicit entry/exit dates (session_dates), not a
     trading-session count. The interface carries session dates alongside ordinals.
  3. The governing 6-session horizon is identity-enforced (horizon != 6 -> ExecRefused).
  4. Missing/invalid ADV or NAV is a data-integrity stop, never a silent zero fill.
  5. Cost schedules are identity-validated against the governing specs before use.
  6. Strict integer/type validation on sessions, shares, dates; duplicate trade_id / position_id and
     exit-before-entry are refused.

Every ledger event carries the 17 frozen fields (16 originals + decision_type). All computed floats
serialize via the exact-float report schema; signed zero preserved, non-finite refuses.

INTEGRITY_STOP codes: EXEC_PRICE_NONFINITE, EXEC_PRICE_NONPOSITIVE, EXEC_NAV_MISSING,
EXEC_NAV_NONFINITE, EXEC_NAV_NONPOSITIVE, EXEC_ADV_MISSING, EXEC_ADV_NONFINITE, EXEC_ADV_NEGATIVE,
EXEC_DATE_MISSING, EXEC_DATE_INVALID, EXEC_INVALID_SIDE, EXEC_INVALID_SHARES, EXEC_INVALID_SESSION,
EXEC_EXIT_BEFORE_ENTRY, plus the cost-model codes. REFUSED codes:
REFUSED_CODE_OR_DATA_IDENTITY:{EXECUTION_HORIZON, DUPLICATE_TRADE_ID, DUPLICATE_POSITION_ID,
COST_SCHEDULE}.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import math
from dataclasses import dataclass

import mr002_valoos_report as R
from mr002_valoos_costmodel import (
    BASE,
    CostSchedule,
    borrow_cost,
    commission_slippage_cost,
    validate_schedule,
)

GOVERNING_HORIZON = 6              # frozen v0.3 realization horizon; next-open exit t+1..t+6
NAV_NEW_ENTRY_CAP = 0.015          # 1.5% of NAV per new entry
ADV_PARTICIPATION_CAP = 0.02       # 2% of trailing ADV (dollars)

EVENT_FIELDS = ("trade_id", "symbol", "side", "decision_session", "decision_type",
                "scheduled_execution_session", "actual_execution_session", "event_type", "shares",
                "official_open_price", "executed_notional", "commission_slippage_cost", "borrow_cost",
                "gross_pnl", "net_pnl", "position_id", "reason")


class ExecIntegrityStop(Exception):
    """Degenerate / out-of-domain execution input (frozen INTEGRITY_STOP with a specific code)."""


class ExecRefused(Exception):
    """REFUSED_CODE_OR_DATA_IDENTITY — an execution input failed governing-identity validation."""


@dataclass(frozen=True)
class TradeIntent:
    trade_id: str
    symbol: str
    side: str                       # "long" | "short"
    position_id: str
    decision_session: int           # signal after close of this session; entry fills at +1
    desired_shares: int
    reason: str = "SYNTHETIC_SIGNAL"
    exit_decision_session: int | None = None   # None -> time-stop only
    horizon: int = GOVERNING_HORIZON


@dataclass(frozen=True)
class Market:
    opens: dict                     # session ordinal -> official open price (missing key or None = no open)
    adv_dollars: dict               # session ordinal -> trailing ADV in dollars (MUST be present for a fill)
    session_dates: dict             # session ordinal -> ISO "YYYY-MM-DD" (explicit calendar date)
    nav: float | None               # None -> EXEC_NAV_MISSING


def _finite(x, code: str) -> float:
    xf = float(x)
    if not math.isfinite(xf):
        raise ExecIntegrityStop(code)
    return xf


def _session_int(v, code: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise ExecIntegrityStop(f"{code}:{v!r}")
    return v


def _price(market: Market, session: int):
    p = market.opens.get(session)
    if p is None:
        return None                 # no official open this session
    pf = _finite(p, "EXEC_PRICE_NONFINITE")
    if pf <= 0.0:
        raise ExecIntegrityStop("EXEC_PRICE_NONPOSITIVE")
    return pf


def _adv(market: Market, session: int) -> float:
    if session not in market.adv_dollars:
        raise ExecIntegrityStop(f"EXEC_ADV_MISSING:{session}")
    v = _finite(market.adv_dollars[session], "EXEC_ADV_NONFINITE")
    if v < 0.0:
        raise ExecIntegrityStop(f"EXEC_ADV_NEGATIVE:{v}")
    return v


def _nav(market: Market) -> float:
    if market.nav is None:
        raise ExecIntegrityStop("EXEC_NAV_MISSING")
    v = _finite(market.nav, "EXEC_NAV_NONFINITE")
    if v <= 0.0:
        raise ExecIntegrityStop(f"EXEC_NAV_NONPOSITIVE:{v}")
    return v


def _date(market: Market, session: int) -> _dt.date:
    s = market.session_dates.get(session)
    if s is None:
        raise ExecIntegrityStop(f"EXEC_DATE_MISSING:{session}")
    try:
        return _dt.date.fromisoformat(s)
    except (ValueError, TypeError):
        raise ExecIntegrityStop(f"EXEC_DATE_INVALID:{session}:{s!r}") from None


def _event(intent: TradeIntent, *, decision_session, decision_type, event_type, scheduled, actual,
           shares, open_price, executed_notional, commission, borrow, gross, net, reason) -> dict:
    return {
        "trade_id": intent.trade_id, "symbol": intent.symbol, "side": intent.side,
        "decision_session": decision_session, "decision_type": decision_type,
        "scheduled_execution_session": scheduled, "actual_execution_session": actual,
        "event_type": event_type, "shares": shares, "official_open_price": open_price,
        "executed_notional": executed_notional, "commission_slippage_cost": commission,
        "borrow_cost": borrow, "gross_pnl": gross, "net_pnl": net,
        "position_id": intent.position_id, "reason": reason,
    }


def _resolve_exit_session(market: Market, target: int):
    """Return (fill_session, deferred) resolving a missing official open forward to the next valid
    open. (None, False) if no valid open exists at or after `target`."""
    keys = [s for s in market.opens if s >= target and market.opens.get(s) is not None]
    if not keys:
        return None, False
    s = min(keys)
    return s, (s != target)


def simulate_position(intent: TradeIntent, market: Market, schedule: CostSchedule = BASE) -> dict:
    """Simulate one synthetic round trip under the frozen next-open + cost model. Returns
    {events: [...17-field...], position: {...} | None, disposition}."""
    validate_schedule(schedule)                          # governing cost-schedule identity (fail-closed)
    if intent.side not in ("long", "short"):
        raise ExecIntegrityStop(f"EXEC_INVALID_SIDE:{intent.side}")
    if not isinstance(intent.desired_shares, int) or isinstance(intent.desired_shares, bool) or intent.desired_shares <= 0:
        raise ExecIntegrityStop(f"EXEC_INVALID_SHARES:{intent.desired_shares!r}")
    if intent.horizon != GOVERNING_HORIZON:
        raise ExecRefused(f"REFUSED_CODE_OR_DATA_IDENTITY:EXECUTION_HORIZON:{intent.horizon}")
    t = _session_int(intent.decision_session, "EXEC_INVALID_SESSION")
    if intent.exit_decision_session is not None:
        e = _session_int(intent.exit_decision_session, "EXEC_INVALID_SESSION")
        if e < t or (e + 1) <= (t + 1):                  # exit decision before entry / target <= entry fill
            raise ExecIntegrityStop(f"EXEC_EXIT_BEFORE_ENTRY:e={e},t={t}")

    nav = _nav(market)
    entry_sched = t + 1
    entry_open = _price(market, entry_sched)

    if entry_open is None:
        ev = _event(intent, decision_session=t, decision_type="ENTRY_SIGNAL",
                    event_type="ENTRY_CANCELLED", scheduled=entry_sched, actual=None, shares=0,
                    open_price=None, executed_notional=0.0, commission=0.0, borrow=0.0, gross=0.0,
                    net=0.0, reason="MISSING_ENTRY_OPEN")
        return {"events": [ev], "position": None, "disposition": "CANCELLED"}

    # mechanical clips: 1.5% NAV new-entry cap AND 2% trailing-ADV participation; clip never delay
    adv = _adv(market, entry_sched)
    nav_cap_shares = int((NAV_NEW_ENTRY_CAP * nav) // entry_open)
    adv_cap_shares = int((ADV_PARTICIPATION_CAP * adv) // entry_open)
    filled = max(0, min(int(intent.desired_shares), nav_cap_shares, adv_cap_shares))
    clipped = int(intent.desired_shares) - filled
    is_short = intent.side == "short"

    entry_notional = filled * entry_open
    entry_comm = commission_slippage_cost(entry_notional, schedule)
    entry_reason = intent.reason if clipped == 0 else f"{intent.reason};CLIPPED_{clipped}_SHARES_TO_CASH"
    entry_ev = _event(intent, decision_session=t, decision_type="ENTRY_SIGNAL",
                      event_type="ENTRY_FILL", scheduled=entry_sched, actual=entry_sched,
                      shares=filled, open_price=entry_open, executed_notional=entry_notional,
                      commission=entry_comm, borrow=0.0, gross=0.0, net=0.0, reason=entry_reason)
    events = [entry_ev]

    if filled == 0:                 # fully clipped -> no position established
        return {"events": events, "position": None, "disposition": "NO_FILL"}

    # exit target + CAUSAL decision provenance: explicit exit (e -> e+1) capped by the time stop.
    time_stop_fill = t + GOVERNING_HORIZON
    if intent.exit_decision_session is not None and (intent.exit_decision_session + 1) <= time_stop_fill:
        target_exit = intent.exit_decision_session + 1
        exit_reason, exit_decision_session, exit_decision_type = "EXIT_DECISION", intent.exit_decision_session, "EXIT_DECISION"
    else:
        target_exit = time_stop_fill
        exit_reason = "TIME_STOP"
        exit_decision_session, exit_decision_type = t + GOVERNING_HORIZON - 1, "TIME_STOP_SCHEDULED_AT_ENTRY"

    exit_fill, deferred = _resolve_exit_session(market, target_exit)
    if exit_fill is None:
        ev = _event(intent, decision_session=exit_decision_session, decision_type=exit_decision_type,
                    event_type="EXIT_PENDING", scheduled=target_exit, actual=None, shares=filled,
                    open_price=None, executed_notional=0.0, commission=0.0, borrow=0.0, gross=0.0,
                    net=0.0, reason=f"{exit_reason};PENDING_NO_OPEN")
        events.append(ev)
        return {"events": events, "position": None, "disposition": "PENDING"}

    exit_open = _price(market, exit_fill)
    if deferred:
        exit_reason = f"{exit_reason};DEFERRED_FROM_{target_exit}"

    # borrow accrues over ELAPSED CALENDAR DAYS between explicit entry/exit dates
    entry_date, exit_date = _date(market, entry_sched), _date(market, exit_fill)
    borrow_days = (exit_date - entry_date).days
    if borrow_days < 0:
        raise ExecIntegrityStop(f"EXEC_DATE_INVALID:exit_before_entry:{exit_date}<{entry_date}")

    exit_notional = filled * exit_open
    exit_comm = commission_slippage_cost(exit_notional, schedule)
    borrow = borrow_cost(entry_notional if is_short else 0.0, borrow_days if is_short else 0,
                         schedule, is_short=is_short)
    direction = 1.0 if intent.side == "long" else -1.0
    gross = (exit_open - entry_open) * filled * direction
    total_costs = entry_comm + exit_comm + borrow
    net = gross - total_costs

    exit_ev = _event(intent, decision_session=exit_decision_session, decision_type=exit_decision_type,
                     event_type="EXIT_FILL", scheduled=target_exit, actual=exit_fill, shares=filled,
                     open_price=exit_open, executed_notional=exit_notional, commission=exit_comm,
                     borrow=borrow, gross=gross, net=net, reason=exit_reason)
    events.append(exit_ev)

    position = {
        "position_id": intent.position_id, "symbol": intent.symbol, "side": intent.side,
        "entry_session": entry_sched, "exit_session": exit_fill,
        "entry_date": entry_date.isoformat(), "exit_date": exit_date.isoformat(),
        "borrow_calendar_days": borrow_days, "shares": filled,
        "entry_open_price": entry_open, "exit_open_price": exit_open,
        "entry_notional": entry_notional, "exit_notional": exit_notional,
        "entry_commission": entry_comm, "exit_commission": exit_comm, "borrow_cost": borrow,
        "total_costs": total_costs, "gross_pnl": gross, "net_pnl": net,
        "exit_decision_session": exit_decision_session, "exit_decision_type": exit_decision_type,
        "reconciles": bool(net == gross - total_costs), "schedule": schedule.name,
    }
    return {"events": events, "position": position, "disposition": "CLOSED"}


def simulate_sequence(intents, market: Market, schedule: CostSchedule = BASE) -> dict:
    """Run intents in order, enforcing: NO duplicate trade_id / position_id (REFUSED) and NO same-open
    re-entry (a new entry whose fill session equals a prior exit fill for that symbol is refused)."""
    validate_schedule(schedule)
    seen_trades, seen_positions = set(), set()
    prior_exit_sessions: dict[str, set] = {}
    all_events, positions = [], []
    for intent in intents:
        if intent.trade_id in seen_trades:
            raise ExecRefused(f"REFUSED_CODE_OR_DATA_IDENTITY:DUPLICATE_TRADE_ID:{intent.trade_id}")
        if intent.position_id in seen_positions:
            raise ExecRefused(f"REFUSED_CODE_OR_DATA_IDENTITY:DUPLICATE_POSITION_ID:{intent.position_id}")
        seen_trades.add(intent.trade_id)
        seen_positions.add(intent.position_id)

        entry_sched = intent.decision_session + 1
        would_fill = market.opens.get(entry_sched) is not None
        if would_fill and entry_sched in prior_exit_sessions.get(intent.symbol, set()):
            all_events.append(_event(intent, decision_session=intent.decision_session,
                                     decision_type="ENTRY_SIGNAL", event_type="ENTRY_REFUSED_SAME_OPEN",
                                     scheduled=entry_sched, actual=None, shares=0, open_price=None,
                                     executed_notional=0.0, commission=0.0, borrow=0.0, gross=0.0,
                                     net=0.0, reason="NO_SAME_OPEN_REENTRY"))
            continue
        res = simulate_position(intent, market, schedule)
        all_events.extend(res["events"])
        if res["position"] is not None:
            positions.append(res["position"])
            prior_exit_sessions.setdefault(intent.symbol, set()).add(res["position"]["exit_session"])
    return {"events": all_events, "positions": positions}


def recompute_position_under_schedule(position: dict, schedule: CostSchedule) -> dict:
    """Recompute a CLOSED position's costs + net under a different frozen schedule (cost-stress /
    severe). Gross P&L, prices, shares, and calendar holding period are unchanged; only costs move."""
    validate_schedule(schedule)
    is_short = position["side"] == "short"
    entry_comm = commission_slippage_cost(position["entry_notional"], schedule)
    exit_comm = commission_slippage_cost(position["exit_notional"], schedule)
    borrow = borrow_cost(position["entry_notional"] if is_short else 0.0,
                         position["borrow_calendar_days"] if is_short else 0, schedule, is_short=is_short)
    total_costs = entry_comm + exit_comm + borrow
    net = position["gross_pnl"] - total_costs
    return {"schedule": schedule.name, "entry_commission": entry_comm, "exit_commission": exit_comm,
            "borrow_cost": borrow, "total_costs": total_costs, "gross_pnl": position["gross_pnl"],
            "net_pnl": net, "reconciles": bool(net == position["gross_pnl"] - total_costs),
            "classification": schedule.classification}


# ── canonical exact-float ledger report (deterministic hash) ──────────────────────────────────────
def ledger_report(*, events: list, positions: list, base_schedule: str,
                  stress: dict | None = None, severe: dict | None = None,
                  code_identity: dict, dependency_lock_sha256: str) -> dict:
    """Assemble a canonical, exact-float, deterministic Increment-2 ledger report and stamp its
    output_hash. Every float encodes as {display, exact_hex}; signed zero preserved; non-finite
    refuses (CanonicalizationError)."""
    record = {
        "record_type": "MR002_ValOOS_TradeLedger",
        "schema_version": "increment2-v1.1-synthetic",
        "base_schedule": base_schedule,
        "event_fields": list(EVENT_FIELDS),
        "events": events,
        "positions": positions,
        "cost_stress": stress,
        "severe_cost_diagnostic": severe,
        "code_identity": code_identity,
        "dependency_lock_sha256": dependency_lock_sha256,
        "validation_data_read": False,
        "oos_data_read": False,
        "development_performance_computed": False,
        "synthetic_fixture_only": True,
    }
    canonical = R._canonicalize(record)
    canonical["output_hash"] = hashlib.sha256(R._serialize(canonical)).hexdigest()
    return canonical


def ledger_report_hash(record: dict) -> str:
    r = {k: v for k, v in record.items() if k != "output_hash"}
    return hashlib.sha256(R._serialize(r)).hexdigest()
