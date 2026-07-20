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
from mr002_valoos_execution import preview_entry_fill
from mr002_valoos_exposure import hard_cap_violations, snapshot
from mr002_valoos_nav import mark_positions
from mr002_valoos_portfolio_identity import NET_DRIFT_BAND, assert_nav_identity
from mr002_valoos_portfolio_state import HeldPosition, PendingExit, PortfolioState

TIME_STOP_OFFSET = 5             # entry_session + 5 = open of session 6 (Inc-2 horizon)


def _vkey(violation) -> str:
    """Normalized constraint key (type + subject, value-independent) for intended-vs-realized
    comparison, so a clipping-induced breach is distinguished from a grandfathered held-drift breach."""
    code, detail = violation
    base = code.split(":")[-1].replace("REALIZED_", "")
    parts = detail.split(":")
    if "SINGLE_NAME" in base:
        return f"SINGLE_NAME|{parts[0]}"
    if "SECTOR" in base:
        return f"SECTOR|{parts[0]}:{parts[1]}"
    if "GROSS" in base:
        return "GROSS"
    if "BETA" in base:
        return "BETA"
    return base


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


def process_session(prior: PortfolioState, *, candidate_records: list, exit_signals: list,
                    market: dict, config_id: str, realized_leg_override=None) -> dict:
    """Atomic session. `market` = {session, date, opens{sym->price|None}, adv{sym->$}}. Returns a
    SessionReplayResult; on a realized hard-cap breach the returned committed_state == prior."""
    s = market["session"]
    opens, adv, date = market["opens"], market["adv"], market["date"]
    events = []

    # 1-2. preview + apply due exits -> provisional post-exit state
    prov_held = list(prior.held)
    cash = prior.cash
    still_pending = []
    for pos, dtype, dsession, reason in _due_exits(prior, exit_signals, s):
        open_s = opens.get(pos.symbol)
        if open_s is None:                                      # missing exit open -> defer (dedup)
            still_pending.append(PendingExit(pos.position_id, pos.symbol, s, dsession, dtype,
                                             pos.shares, f"{reason};PENDING_NO_OPEN"))
            continue
        exit_notional = pos.shares * open_s
        exit_comm = commission_slippage_cost(exit_notional, BASE)
        if pos.side == "long":
            cash += exit_notional - exit_comm
            borrow = 0.0
        else:
            days = (_dt.date.fromisoformat(date) - _dt.date.fromisoformat(pos.entry_date)).days
            borrow = borrow_cost(pos.entry_notional, days, BASE, is_short=True)
            cash -= exit_notional + exit_comm + borrow
        prov_held = [h for h in prov_held if h.position_id != pos.position_id]
        events.append({"event_type": "EXIT_FILL", "symbol": pos.symbol, "side": pos.side,
                       "shares": pos.shares, "official_open_price": open_s,
                       "executed_notional": exit_notional, "commission_slippage_cost": exit_comm,
                       "borrow_cost": borrow, "decision_session": dsession, "decision_type": dtype,
                       "position_id": pos.position_id, "reason": reason})

    prov_occupied = {h.symbol for h in prov_held} | {pe.symbol for pe in still_pending}
    nav_cycle = cash + mark_positions(prov_held, opens)         # post-exit equity = construction NAV

    # 3. construct entries against the provisional state
    cands = validate_candidates(candidate_records, config_id=config_id)
    cand_by_id = {c.candidate_id: c for c in cands}
    book = build_intended_target(cands, nav_cycle, prov_occupied)

    # 4. preview entry fills (Increment-2 shared clip primitive; identity-checked)
    new_positions, entry_previews, prov_cash = [], [], cash
    for order in book["intended"]:
        c = cand_by_id[order["candidate_id"]]
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
        new_positions.append(HeldPosition(
            position_id=f"POS-{c.symbol}-{s}", symbol=c.symbol, side=c.side, shares=filled,
            entry_session=s, entry_date=date, entry_open_price=c.official_next_open_price,
            entry_notional=notional, sector_id=c.sector_id, beta=c.beta,
            permanent_security_id=c.permanent_security_id, signal_origin_session=c.signal_origin_session,
            entry_registered_signal_value=c.registered_signal_value, configuration_id=c.configuration_id,
            originating_candidate_id=c.candidate_id, eligibility_evidence_identity=c.eligibility_evidence_identity))

    # 5. verify the complete realized session. Held positions marked at session-s opens are
    #    grandfathered (PR-16 fixed shares); a hard-cap breach is a REALIZED_* failure ONLY when it is
    #    CAUSED by execution clipping — i.e. present in REALIZED_EXECUTED but not in INTENDED_TARGET on
    #    the same (held-marked) total book (RC-2: "clipping should not increase per-name or gross").
    held_legs = [{"symbol": h.symbol, "side": h.side, "notional": h.shares * opens[h.symbol],
                  "sector_id": h.sector_id, "beta": h.beta} for h in prov_held]
    intended_new = [{"symbol": o["symbol"], "side": o["side"], "notional": o["intended_notional"],
                     "sector_id": o["sector_id"], "beta": o["beta"]} for o in book["intended"]]
    realized_new = [{"symbol": p.symbol, "side": p.side, "notional": p.entry_notional,
                     "sector_id": p.sector_id, "beta": p.beta} for p in new_positions]
    if realized_leg_override is not None:                  # adversarial seam (T3-31): inject a defect
        realized_new = realized_leg_override
    intended_snap = snapshot("INTENDED_TARGET", held_legs + intended_new, nav_cycle)
    realized = snapshot("REALIZED_EXECUTED", held_legs + realized_new, nav_cycle)
    intended_keys = {_vkey(v) for v in hard_cap_violations(intended_snap, realized=False)}
    clipping_induced = [v for v in hard_cap_violations(realized, realized=True) if _vkey(v) not in intended_keys]
    if clipping_induced:
        return {"session": s, "disposition": "REFUSED", "stop_code": clipping_induced[0][0],
                "violations": clipping_induced, "events": events, "intended": book["intended"],
                "entry_previews": entry_previews, "removal_events": book["removal_events"],
                "exposure": {"INTENDED_TARGET": intended_snap, "REALIZED_EXECUTED": realized},
                "committed_state": prior, "atomicity_committed": False}

    # 6. net-dollar drift -> next-open repair (NOT a stop)
    drift = None
    if not realized["empty"] and realized["net_fraction_of_gross"] > NET_DRIFT_BAND:
        larger = "long" if sum(h.shares * opens[h.symbol] for h in prov_held if h.side == "long") + \
            sum(p.entry_notional for p in new_positions if p.side == "long") >= \
            sum(h.shares * opens[h.symbol] for h in prov_held if h.side == "short") + \
            sum(p.entry_notional for p in new_positions if p.side == "short") else "short"
        drift = {"net_fraction_of_gross": realized["net_fraction_of_gross"], "band": NET_DRIFT_BAND,
                 "breached": True, "larger_side": larger, "scheduled_next_open": s + 1,
                 "reduction_order": "smallest |entry z| -> oldest position -> permanent_security_id"}

    # 7. commit atomically
    committed = PortfolioState(session=s, cash=prov_cash, held=tuple(prov_held) + tuple(new_positions),
                               pending=tuple(still_pending))
    return {"session": s, "disposition": "COMMITTED", "stop_code": None, "events": events,
            "intended": book["intended"], "entry_previews": entry_previews,
            "removal_events": book["removal_events"], "drift_repair": drift,
            "exposure": {"RAW_TARGET": None, "INTENDED_TARGET": book["exposure"],
                         "REALIZED_EXECUTED": realized},
            "committed_state": committed, "nav_cycle": nav_cycle, "atomicity_committed": True}
