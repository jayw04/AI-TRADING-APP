"""MR-002 Increment 3 — session replay: PREVIEW -> VERIFY -> COMMIT (synthetic only).

Full-session transaction (clarification #3): (1) preview all due exits/reductions, (2) provisional
post-exit state, (3) construct entries against the provisional state, (4) preview entries, (5) verify
the complete REALIZED session against the hard caps, (6) commit atomically only if verification
passes. A failed verification commits nothing (cash/positions/pending/ledger/NAV unchanged) and retains
the preview as REFUSED evidence (RC-2 atomicity). Sector/beta realized breaches fail closed with the
distinct REALIZED_* codes; net-dollar drift alone produces a next-open DriftRepairInstruction.

All ADV/NAV clipping, commission, and borrow math is delegated to the Increment-2 primitives
(preview_entry_fill / commission_slippage_cost / borrow_cost) — never reimplemented.
"""

from __future__ import annotations

import datetime as _dt

from mr002_valoos_candidates import assert_candidate_execution_identity, validate_candidates
from mr002_valoos_construction import build_intended_target
from mr002_valoos_costmodel import BASE, borrow_cost, commission_slippage_cost
from mr002_valoos_execution import ledger_event, preview_entry_fill
from mr002_valoos_exposure import snapshot, worsened_or_new_violations
from mr002_valoos_nav import NavIntegrityStop, mark_positions
from mr002_valoos_portfolio_identity import NET_DRIFT_BAND, assert_nav_identity
from mr002_valoos_portfolio_state import HeldPosition, PendingExit, PortfolioState

TIME_STOP_OFFSET = 5             # entry_session + 5 = open of session 6 (Inc-2 horizon)


def _due_exits(prior: PortfolioState, exit_signals: list, s: int) -> list:
    """(position, decision_type, decision_session, reason) due at session s: carried pending +
    time-stop (entry+5) + explicit exit signals (exit_decision+1 == s). Deduped by position_id."""
    held = {h.position_id: h for h in prior.held}
    due, seen = [], set()
    for pe in prior.pending:                                    # carried deferred exits
        if pe.position_id in held and pe.position_id not in seen:
            due.append((held[pe.position_id], pe.decision_type, pe.decision_session, pe.reason))
            seen.add(pe.position_id)
    explicit = {sig["symbol"]: sig for sig in exit_signals if sig["exit_decision_session"] + 1 == s}
    for h in prior.held:
        if h.position_id in seen:
            continue
        if h.symbol in explicit:
            due.append((h, "EXIT_DECISION", explicit[h.symbol]["exit_decision_session"], "EXIT_DECISION"))
            seen.add(h.position_id)
        elif h.entry_session + TIME_STOP_OFFSET == s:
            due.append((h, "TIME_STOP_SCHEDULED_AT_ENTRY", s - 1, "TIME_STOP"))
            seen.add(h.position_id)
    return due


def _ev(**kw):
    """Build a 17-field Increment-2 ledger event (shared constructor; no second schema)."""
    return ledger_event(**kw)


def process_session(prior: PortfolioState, *, candidate_records: list, exit_signals: list,
                    market: dict, config_id: str, realized_leg_override=None) -> dict:
    """Atomic session PREVIEW -> VERIFY -> COMMIT. Emits complete 17-field ledger events; constructs
    new entries against the provisional held-plus-new book; a realized hard-cap breach that is NEW or
    WORSENS a pre-existing (held) breach fails closed (numeric grandfathering). On refusal the returned
    committed_state == prior and the preview events are retained, marked uncommitted."""
    s = market["session"]
    opens, adv, date = market["opens"], market["adv"], market["date"]
    events = []
    recon = {"opening_cash": prior.cash, "exit_cash_flow": 0.0, "exit_commissions": 0.0,
             "borrow_total": 0.0, "entry_cash_flow": 0.0, "entry_commissions": 0.0}

    # 1-2. preview + apply due exits -> provisional post-exit state
    prov_held, cash, still_pending = list(prior.held), prior.cash, []
    for pos, dtype, dsession, reason in _due_exits(prior, exit_signals, s):
        open_s = opens.get(pos.symbol)
        if open_s is None:                                      # missing exit open -> defer (dedup, one logical order)
            still_pending.append(PendingExit(pos.position_id, pos.symbol, s, dsession, dtype, pos.shares,
                                             f"{reason};PENDING_NO_OPEN"))
            events.append(_ev(trade_id=f"TR-{pos.position_id}-exit-{s}", symbol=pos.symbol, side=pos.side,
                              decision_session=dsession, decision_type=dtype, scheduled=s, actual=None,
                              event_type="EXIT_PENDING", shares=pos.shares, open_price=None,
                              executed_notional=0.0, commission=0.0, borrow=0.0, gross=0.0, net=0.0,
                              position_id=pos.position_id, reason=f"{reason};PENDING_NO_OPEN"))
            continue
        exit_notional = pos.shares * open_s
        exit_comm = commission_slippage_cost(exit_notional, BASE)
        direction = 1.0 if pos.side == "long" else -1.0
        gross = (open_s - pos.entry_open_price) * pos.shares * direction
        if pos.side == "long":
            cash += exit_notional - exit_comm
            borrow = 0.0
            recon["exit_cash_flow"] += exit_notional
        else:
            days = (_dt.date.fromisoformat(date) - _dt.date.fromisoformat(pos.entry_date)).days
            borrow = borrow_cost(pos.entry_notional, days, BASE, is_short=True)
            cash -= exit_notional + exit_comm + borrow
            recon["exit_cash_flow"] -= exit_notional
        net = gross - pos.entry_commission - exit_comm - borrow
        recon["exit_commissions"] += exit_comm
        recon["borrow_total"] += borrow
        prov_held = [h for h in prov_held if h.position_id != pos.position_id]
        events.append(_ev(trade_id=f"TR-{pos.position_id}-exit-{s}", symbol=pos.symbol, side=pos.side,
                          decision_session=dsession, decision_type=dtype, scheduled=s, actual=s,
                          event_type="EXIT_FILL", shares=pos.shares, open_price=open_s,
                          executed_notional=exit_notional, commission=exit_comm, borrow=borrow,
                          gross=gross, net=net, position_id=pos.position_id, reason=reason))

    prov_occupied = {h.symbol for h in prov_held} | {pe.symbol for pe in still_pending}
    try:                                                        # post-exit equity = construction NAV
        nav_cycle = cash + mark_positions(prov_held, opens)     # a held symbol with no open fails closed
    except NavIntegrityStop as exc:                             # (incl. a deferred exit's symbol) — the
        return {"session": s, "disposition": "REFUSED",        # EXIT_PENDING evidence is retained
                "stop_code": f"INTEGRITY_STOP:{exc}", "events": events, "events_committed": False,
                "committed_state": prior, "atomicity_committed": False}
    held_legs = [{"symbol": h.symbol, "side": h.side, "notional": h.shares * opens[h.symbol],
                  "sector_id": h.sector_id, "beta": h.beta} for h in prov_held]

    # occupancy: a same-symbol candidate is refused (one-position-per-symbol / no same-open re-entry)
    cands = validate_candidates(candidate_records, config_id=config_id)
    cand_by_id = {c.candidate_id: c for c in cands}
    for sym in sorted({c.symbol for c in cands if c.eligibility_status == "ELIGIBLE" and c.symbol in prov_occupied}):
        events.append(_ev(trade_id=f"TR-{sym}-refused-{s}", symbol=sym, side="n/a", decision_session=s - 1,
                          decision_type="ENTRY_SIGNAL", scheduled=s, actual=None,
                          event_type="ENTRY_REFUSED_SAME_OPEN", shares=0, open_price=None,
                          executed_notional=0.0, commission=0.0, borrow=0.0, gross=0.0, net=0.0,
                          position_id="", reason="NO_SAME_OPEN_REENTRY"))

    # 3. construct new entries against the provisional held-plus-new book (held exposure is the baseline)
    book = build_intended_target(cands, nav_cycle, prov_occupied, held_legs=held_legs)

    # 4. preview entry fills (Increment-2 shared clip primitive; identity-checked)
    new_positions, entry_previews, prov_cash = [], [], cash
    for order in book["intended"]:
        c = cand_by_id[order["candidate_id"]]
        pos_id = f"POS-{c.symbol}-{s}"
        if opens.get(c.symbol) is None:                        # missing entry open -> cancelled
            events.append(_ev(trade_id=f"TR-{c.symbol}-entry-{s}", symbol=c.symbol, side=c.side,
                              decision_session=c.decision_session, decision_type="ENTRY_SIGNAL",
                              scheduled=s, actual=None, event_type="ENTRY_CANCELLED", shares=0,
                              open_price=None, executed_notional=0.0, commission=0.0, borrow=0.0,
                              gross=0.0, net=0.0, position_id=pos_id, reason="MISSING_ENTRY_OPEN"))
            continue
        assert_candidate_execution_identity(c, opens[c.symbol], adv[c.symbol], s, nav_cycle,
                                            assert_nav_identity(nav_cycle, nav_cycle))
        pf = preview_entry_fill(order["intended_shares"], c.official_next_open_price, nav_cycle, adv[c.symbol])
        filled = pf["filled_shares"]
        entry_previews.append({**order, "preview_filled_shares": filled,
                               "clipped_shares": order["intended_shares"] - filled,
                               "adv_cap_shares": pf["adv_cap_shares"]})
        if filled == 0:
            continue
        notional = filled * c.official_next_open_price
        entry_comm = commission_slippage_cost(notional, BASE)
        prov_cash += (-notional - entry_comm) if c.side == "long" else (notional - entry_comm)
        recon["entry_cash_flow"] += -notional if c.side == "long" else notional
        recon["entry_commissions"] += entry_comm
        events.append(_ev(trade_id=f"TR-{c.symbol}-entry-{s}", symbol=c.symbol, side=c.side,
                          decision_session=c.decision_session, decision_type="ENTRY_SIGNAL", scheduled=s,
                          actual=s, event_type="ENTRY_FILL", shares=filled,
                          open_price=c.official_next_open_price, executed_notional=notional,
                          commission=entry_comm, borrow=0.0, gross=0.0, net=0.0, position_id=pos_id,
                          reason=c.reason if hasattr(c, "reason") else "SYNTHETIC_SIGNAL"))
        new_positions.append(HeldPosition(
            position_id=pos_id, symbol=c.symbol, side=c.side, shares=filled, entry_session=s,
            entry_date=date, entry_open_price=c.official_next_open_price, entry_notional=notional,
            entry_commission=entry_comm, sector_id=c.sector_id, beta=c.beta,
            permanent_security_id=c.permanent_security_id, signal_origin_session=c.signal_origin_session,
            entry_registered_signal_value=c.registered_signal_value, configuration_id=c.configuration_id,
            originating_candidate_id=c.candidate_id, eligibility_evidence_identity=c.eligibility_evidence_identity))

    # 5. verify complete realized session vs the pre-existing (held-only) BASELINE — numeric
    #    grandfathering: a breach fails closed only when NEW or WORSENED vs baseline (defect-1 ruling).
    baseline = snapshot("HELD_BASELINE", held_legs, nav_cycle)
    realized_new = realized_leg_override if realized_leg_override is not None else \
        [{"symbol": p.symbol, "side": p.side, "notional": p.entry_notional, "sector_id": p.sector_id,
          "beta": p.beta} for p in new_positions]
    realized = snapshot("REALIZED_EXECUTED", held_legs + realized_new, nav_cycle)
    violations = worsened_or_new_violations(baseline, realized, realized=True)
    exposure = {"RAW_TARGET": book["raw_target_exposure"], "HELD_BASELINE": baseline,
                "INTENDED_TARGET": book["exposure"], "REALIZED_EXECUTED": realized}
    if violations:
        return {"session": s, "disposition": "REFUSED", "stop_code": violations[0][0],
                "violations": violations, "events": events, "events_committed": False,
                "intended": book["intended"], "entry_previews": entry_previews,
                "raw_targets": book["raw_targets"], "removal_events": book["removal_events"],
                "constraint_decisions": book["constraint_decisions"], "exposure": exposure,
                "committed_state": prior, "atomicity_committed": False}

    # 6. net-dollar drift -> next-open repair (NOT a stop)
    drift = None
    if not realized["empty"] and realized["net_fraction_of_gross"] > NET_DRIFT_BAND:
        long_d = sum(x["notional"] for x in held_legs + realized_new if x["side"] == "long")
        short_d = sum(x["notional"] for x in held_legs + realized_new if x["side"] == "short")
        drift = {"net_fraction_of_gross": realized["net_fraction_of_gross"], "band": NET_DRIFT_BAND,
                 "breached": True, "larger_side": "long" if long_d >= short_d else "short",
                 "scheduled_next_open": s + 1,
                 "reduction_order": "smallest |entry z| -> oldest position -> permanent_security_id"}

    # 7. reconciliation + atomic commit
    recon["closing_cash"] = prov_cash
    recon["derived_closing_cash"] = (recon["opening_cash"] + recon["exit_cash_flow"] + recon["entry_cash_flow"]
                                     - recon["exit_commissions"] - recon["entry_commissions"] - recon["borrow_total"])
    recon["reconciles"] = bool(prov_cash == recon["derived_closing_cash"])
    committed = PortfolioState(session=s, cash=prov_cash, held=tuple(prov_held) + tuple(new_positions),
                               pending=tuple(still_pending))
    return {"session": s, "disposition": "COMMITTED", "stop_code": None, "events": events,
            "events_committed": True, "intended": book["intended"], "entry_previews": entry_previews,
            "raw_targets": book["raw_targets"], "removal_events": book["removal_events"],
            "constraint_decisions": book["constraint_decisions"], "drift_repair": drift,
            "exposure": exposure, "reconciliation": recon, "committed_state": committed,
            "nav_cycle": nav_cycle, "atomicity_committed": True}
