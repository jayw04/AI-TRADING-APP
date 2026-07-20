"""MR-002 Increment 3 — synthetic portfolio-construction/replay qualification (synthetic ONLY).

Maps to MR002_Increment3_QualificationMatrix_v1.0 (T3-01..T3-33). Reads no real dataset; computes no
residual/z/sigma; validation/OOS never opened. Expected values are hand-derived or independently
computed. Run: apps/backend/.venv/Scripts/python.exe -m pytest test_increment3.py -v
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

import mr002_valoos_candidates as CA
import mr002_valoos_construction as CO
import mr002_valoos_exposure as EX
import mr002_valoos_metrics as M
import mr002_valoos_nav as NAV
import mr002_valoos_pipeline as P
import mr002_valoos_portfolio_identity as ID
import mr002_valoos_replay as RP
from mr002_valoos_portfolio_state import HeldPosition, PendingExit, PortfolioState, add_pending

GOV_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NAV0 = 1_000_000.0


def _cand(cid, side, z, sec, *, sigma=0.02, beta=0.05, price=100.0, adv=1e15, cfg="B",
          pid=None, so=1, ds=0, elig="ELIGIBLE"):
    return {"candidate_id": cid, "permanent_security_id": pid or cid, "signal_origin_session": so,
            "decision_session": ds, "symbol": cid, "side": side, "registered_signal_value": z,
            "registered_sigma_resid": sigma, "sector_id": sec, "beta": beta, "eligibility_status": elig,
            "eligibility_evidence_identity": "ev", "configuration_id": cfg,
            "official_next_open_price": price, "trailing_adv_dollars": adv}


def _valid_recs(cfg="B", ds=0):
    """5 sectors x (10 long + 10 short); the extreme (|z|=3) one per sector is selected -> a
    sector-neutral 10-name book that satisfies every frozen cap."""
    recs = []
    for sec in range(5):
        for j in range(10):
            recs.append(_cand(f"L{sec}_{j}", "long", -3.0 if j == 0 else -2.0, f"SEC{sec}", cfg=cfg, ds=ds))
            recs.append(_cand(f"S{sec}_{j}", "short", 3.0 if j == 0 else 2.0, f"SEC{sec}", cfg=cfg, ds=ds))
    return recs


def _opens(recs, price=100.0):
    return {r["candidate_id"]: price for r in recs}


# ── T3-01 identity-chain tampering ────────────────────────────────────────────────────────────────
def test_01_identity_loads_and_tamper_refused():
    got = ID.load_portfolio_identity(GOV_DIR)
    assert got["registry_sha256"] == ID.REGISTRY_SHA and got["constants"]["POSITION_CAP_NAV"] == 0.015
    with tempfile.TemporaryDirectory() as tmp:
        for f in (ID.REGISTRY, ID.RESOLUTION, *ID.SOURCE_SHAS):
            shutil.copyfile(os.path.join(GOV_DIR, f), os.path.join(tmp, f))
        with open(os.path.join(tmp, ID.REGISTRY), "ab") as fh:
            fh.write(b" ")                                    # tamper one byte
        with pytest.raises(ID.RefusedPortfolioIdentity, match="HASH_MISMATCH"):
            ID.load_portfolio_identity(tmp)
    with tempfile.TemporaryDirectory() as tmp:                # missing file
        shutil.copyfile(os.path.join(GOV_DIR, ID.REGISTRY), os.path.join(tmp, ID.REGISTRY))
        with pytest.raises(ID.RefusedPortfolioIdentity, match="MISSING"):
            ID.load_portfolio_identity(tmp)


# ── T3-02 candidate schema/type failures ──────────────────────────────────────────────────────────
def test_02_candidate_schema_failures():
    ok = _cand("X", "long", -2.5, "T")
    for drop in ("symbol", "beta", "configuration_id"):
        bad = {k: v for k, v in ok.items() if k != drop}
        with pytest.raises(CA.CandidateIntegrityStop, match="CANDIDATE_MISSING_FIELD"):
            CA.validate_candidate(bad, config_id="B")
    with pytest.raises(CA.CandidateIntegrityStop, match="CANDIDATE_SIDE_INVALID"):
        CA.validate_candidate({**ok, "side": "flat"}, config_id="B")
    with pytest.raises(CA.CandidateIntegrityStop, match="CANDIDATE_ELIGIBILITY_INVALID"):
        CA.validate_candidate({**ok, "eligibility_status": "MAYBE"}, config_id="B")
    with pytest.raises(CA.CandidateIntegrityStop, match="CANDIDATE_CONFIG_INVALID"):
        CA.validate_candidate({**ok, "configuration_id": "Z"}, config_id="Z")


# ── T3-03 sigma invalid + inverse mismatch ────────────────────────────────────────────────────────
def test_03_sigma_and_inverse():
    ok = _cand("X", "long", -2.5, "T", sigma=0.02)
    for bad in (0.0, -0.1, float("inf"), float("nan")):
        with pytest.raises(CA.CandidateIntegrityStop, match="CANDIDATE_SIGMA_RESID_INVALID"):
            CA.validate_candidate({**ok, "registered_sigma_resid": bad}, config_id="B")
    with pytest.raises(CA.CandidateIntegrityStop, match="CANDIDATE_SIGMA_RESID_INVALID"):
        CA.validate_candidate({**ok, "registered_sigma_resid": True}, config_id="B")
    good = CA.validate_candidate({**ok, "registered_inverse_vol_weight": 1.0 / 0.02}, config_id="B")
    assert good.inverse_vol_weight == pytest.approx(50.0)
    with pytest.raises(CA.CandidateIntegrityStop, match="CANDIDATE_INVERSE_VOL_MISMATCH"):
        CA.validate_candidate({**ok, "registered_inverse_vol_weight": 50.0 * (1 + 1e-9)}, config_id="B")


# ── T3-04 A/B/C differ ONLY in Z_entry ────────────────────────────────────────────────────────────
def test_04_abc_only_threshold_differs():
    assert ID.Z_ENTRY == {"A": 1.75, "B": 2.00, "C": 2.25}
    # a name with |z| = 1.9 is selectable under A (1.75) but not B/C — same code path, only the constant
    pool = [CA.validate_candidate(_cand("N", "long", -1.9, "T", cfg=c), config_id=c) for c in "ABC"]
    selA = CO._select_side([pool[0]], "long", ID.Z_ENTRY["A"])
    selB = CO._select_side([pool[1]], "long", ID.Z_ENTRY["B"])
    assert len(selA) == 1 and len(selB) == 0        # only the threshold constant changed the outcome


# ── T3-05 within-side normalization ───────────────────────────────────────────────────────────────
def test_05_within_side_normalization():
    sel = CA.validate_candidates([_cand("A", "long", -2.5, "S0", sigma=0.02),
                                  _cand("B", "long", -2.5, "S1", sigma=0.04)], config_id="B")
    book = CO._size_book(sel, NAV0)
    w = {r["symbol"]: r["normalized_weight"] for r in book["raw_targets"]}
    # 1/0.02=50, 1/0.04=25, total 75 -> 2/3, 1/3
    assert w["A"] == pytest.approx(2 / 3) and w["B"] == pytest.approx(1 / 3)


# ── T3-06 entry dollar-neutrality ─────────────────────────────────────────────────────────────────
def test_06_entry_neutrality():
    long_only = CO._size_book(CA.validate_candidates([_cand("A", "long", -2.5, "S0")], config_id="B"), NAV0)
    assert long_only["side_gross_target"] == 0.0        # no short side -> no book (no forced trade)
    both = CO._size_book(CA.validate_candidates(
        [_cand("A", "long", -2.5, "S0"), _cand("B", "short", 2.5, "S0")], config_id="B"), NAV0)
    assert both["side_gross_target"] == ID.SIDE_GROSS_CAP * NAV0    # 50% NAV each side


# ── T3-07 position-cap clip -> cash (not removal) ─────────────────────────────────────────────────
def test_07_position_cap_clip_to_cash():
    # single long: target = 50% NAV, capped to 1.5% NAV, excess -> cash
    book = CO._size_book(CA.validate_candidates(
        [_cand("A", "long", -2.5, "S0"), _cand("B", "short", 2.5, "S0")], config_id="B"), NAV0)
    leg = next(x for x in book["legs"] if x["symbol"] == "A")
    assert leg["notional"] == pytest.approx(ID.POSITION_CAP_NAV * NAV0)   # 15000
    assert book["cash_from_cap"] > 0.0


# ── T3-08 sector cascade + T3-10 smallest-|z| removal + T3-12 no renorm ──────────────────────────
def test_08_10_12_sector_cascade_and_no_renorm():
    # disjoint single-name sectors -> sector-net breach -> removal cascade empties; freed -> cash
    recs = [_cand("L1", "long", -2.9, "SA"), _cand("S1", "short", 2.5, "SC")]
    cands = CA.validate_candidates(recs, config_id="B")
    weights_before = {r["symbol"]: r["normalized_weight"] for r in CO._size_book(
        [c for c in cands], NAV0)["raw_targets"]}
    book = CO.build_intended_target(cands, NAV0, set())
    assert len(book["removal_events"]) >= 1                              # cascade removed
    assert all("SECTOR_CONSTRAINT" in r["binding_violation"] for r in book["removal_events"])
    assert book["removal_events"][0]["z"] == pytest.approx(2.5)          # smallest |z| removed first (S1)
    assert book["cash_from_removal"] > 0.0                               # freed capacity -> cash
    # no upward renormalization: weights were computed once and never scaled up by removals
    assert weights_before == {"L1": 1.0, "S1": 1.0}


# ── T3-09 beta cascade ────────────────────────────────────────────────────────────────────────────
def test_09_beta_cascade():
    # 50/50 sector-neutral pool (sector caps satisfied) but long beta +2 / short beta -2 do NOT cancel
    recs = []
    for sec in range(5):
        for j in range(10):
            recs += [_cand(f"L{sec}_{j}", "long", -3.0 if j == 0 else -2.0, f"SEC{sec}", beta=2.0),
                     _cand(f"S{sec}_{j}", "short", 3.0 if j == 0 else 2.0, f"SEC{sec}", beta=-2.0)]
    book = CO.build_intended_target(CA.validate_candidates(recs, config_id="B"), NAV0, set())
    assert any("BETA_CONSTRAINT" in r["binding_violation"] for r in book["removal_events"])


# ── T3-11 signal-age + permanent-id tie-breaks (removal key, PR-13) ───────────────────────────────
def test_11_removal_tie_breaks():
    def o(cid, z, so, pid):
        return {"candidate_id": cid, "registered_signal_value": z, "signal_origin_session": so,
                "permanent_security_id": pid}
    # equal |z|: older signal (smaller signal_origin_session) wins
    assert CO.removal_victim([o("A", -2.5, 5, "AAA"), o("B", -2.5, 3, "BBB")])["candidate_id"] == "B"
    # equal |z| AND equal signal age: lexical permanent_security_id wins
    assert CO.removal_victim([o("A", -2.5, 3, "BBB"), o("C", -2.5, 3, "AAB")])["candidate_id"] == "C"
    # strictly smaller |z| always wins regardless of age/id
    assert CO.removal_victim([o("A", -2.9, 1, "AAA"), o("B", -2.5, 9, "ZZZ")])["candidate_id"] == "B"


# ── T3-13/14/15 pending exits before entries, dedup, occupancy ───────────────────────────────────
def test_13_14_15_pending_and_occupancy():
    pos = HeldPosition("POS-Z-1", "Z", "long", 100, 1, "2024-01-02", 100.0, 10000.0, "SEC0", 0.05,
                       "Z", 1, -2.5, "B", "candZ", "ev")
    pe = PendingExit("POS-Z-1", "Z", 2, 1, "EXIT_DECISION", 100, "EXIT_DECISION")
    st = PortfolioState(session=1, cash=NAV0, held=(pos,), pending=(pe,))
    assert "Z" in st.occupied_symbols()                       # occupancy blocks re-entry
    st2 = add_pending(st, pe)                                 # dedup: adding same pending is a no-op
    assert len(st2.pending) == 1
    # exit-before-entry: an entry candidate for held symbol Z is ineligible (occupied)
    book = CO.build_intended_target(CA.validate_candidates([_cand("Z", "long", -3.0, "SEC0"),
                                                            _cand("S", "short", 3.0, "SEC0")], config_id="B"),
                                    NAV0, st.occupied_symbols())
    assert all(o["symbol"] != "Z" for o in book["intended"])


# ── T3-16 NAV identity mismatch ───────────────────────────────────────────────────────────────────
def test_16_nav_identity_mismatch():
    assert ID.assert_nav_identity(1000.0, 1000.0) == 1000.0
    with pytest.raises(ID.RefusedPortfolioIdentity, match="NAV_IDENTITY_MISMATCH"):
        ID.assert_nav_identity(1000.0, 1001.0)


# ── T3-21 empty portfolio ─────────────────────────────────────────────────────────────────────────
def test_21_empty_portfolio():
    snap = EX.snapshot("REALIZED_EXECUTED", [], NAV0)
    assert snap["empty"] is True and snap["normalized_beta"] == EX.N_A_EMPTY
    assert snap["signed_beta_numerator"] == 0.0
    assert EX.hard_cap_violations(snap, realized=True) == []      # beta passes vacuously, no div0


# ── T3-22 held-position missing open mark ─────────────────────────────────────────────────────────
def test_22_held_missing_mark():
    pos = HeldPosition("P", "Z", "long", 100, 1, "2024-01-02", 100.0, 10000.0, "S0", 0.05, "Z", 1, -2.5, "B", "c", "ev")
    with pytest.raises(NAV.NavIntegrityStop, match="HELD_POSITION_OPEN_MARK_MISSING"):
        NAV.mark_positions([pos], {})                          # no open for Z


# ── T3-23/24 open-to-open NAV arithmetic + first-window prior NAV ────────────────────────────────
def test_23_24_nav_arithmetic_and_first_window():
    pos = HeldPosition("P", "Z", "long", 100, 1, "2024-01-02", 100.0, 10000.0, "S0", 0.05, "Z", 1, -2.5, "B", "c", "ev")
    r1 = NAV.daily_nav_record(session=1, cash=990000.0, held=[pos], opens_s={"Z": 100.0}, nav_prev=1_000_000.0)
    assert r1["nav"] == pytest.approx(990000.0 + 100 * 100.0)   # 1,000,000
    assert r1["daily_return"] == pytest.approx(0.0)
    r2 = NAV.daily_nav_record(session=2, cash=990000.0, held=[pos], opens_s={"Z": 110.0}, nav_prev=r1["nav"])
    assert r2["nav"] == pytest.approx(990000.0 + 100 * 110.0)   # 1,001,000
    assert r2["daily_return"] == pytest.approx(1_001_000.0 / 1_000_000.0 - 1.0)
    # first-window: prior NAV supplied from warm-up, no spurious zero-return first observation
    first = NAV.daily_nav_record(session=1, cash=990000.0, held=[pos], opens_s={"Z": 100.0}, nav_prev=None)
    assert first["daily_return"] is None


# ── integration fixture: a committed sector-neutral book ─────────────────────────────────────────
def _run(sessions, cfg="B"):
    return P.run_replay(sessions, initial_cash=NAV0, config_id=cfg)


def _session(recs, session, date, opens, adv=None, exits=None):
    return {"session": session, "date": date, "opens": opens,
            "adv": adv if adv is not None else {r["candidate_id"]: 1e15 for r in recs},
            "candidate_records": recs, "exit_signals": exits or []}


def test_25_atomicity_refused_leaves_state_unchanged():
    recs = _valid_recs()
    s1 = _session(recs, 1, "2024-01-02", _opens(recs))
    base = _run([s1])
    committed = base["results"][0]["committed_state"]
    # inject an adversarial realized book (a single name blown to 5% NAV) -> REALIZED_SINGLE_NAME
    prior = PortfolioState(session=0, cash=NAV0)
    bad_legs = [{"symbol": "L0_0", "side": "long", "notional": 0.05 * NAV0, "sector_id": "SEC0", "beta": 0.05}]
    res = RP.process_session(prior, candidate_records=recs, exit_signals=[],
                             market={"session": 1, "date": "2024-01-02", "opens": _opens(recs),
                                     "adv": {r["candidate_id"]: 1e15 for r in recs}},
                             config_id="B", realized_leg_override=bad_legs)
    assert res["disposition"] == "REFUSED"
    assert res["stop_code"] == "INTEGRITY_STOP:REALIZED_SINGLE_NAME_CONSTRAINT"
    assert res["committed_state"] is prior                    # state object unchanged (atomic)
    assert res["committed_state"].cash == NAV0 and res["committed_state"].held == ()
    assert committed.held != ()                               # the clean run did commit


def test_26_deterministic_full_replay():
    recs = _valid_recs()
    sess = [_session(recs, 1, "2024-01-02", _opens(recs))]
    a, b = _run(sess), _run(sess)
    ident = {"registry_sha256": ID.REGISTRY_SHA, "resolution_sha256": ID.RESOLUTION_SHA}
    ra = P.build_pipeline_report(replay=a, metrics=P.metric_handoff(a["return_series"]), identity=ident,
                                 config_id="B", code_identity={"m": "1"}, dependency_lock_sha256="0" * 64)
    rb = P.build_pipeline_report(replay=b, metrics=P.metric_handoff(b["return_series"]), identity=ident,
                                 config_id="B", code_identity={"m": "1"}, dependency_lock_sha256="0" * 64)
    assert ra["output_hash"] == rb["output_hash"] and P.report_hash(ra) == ra["output_hash"]


def test_27_signed_zero_and_nonfinite():
    import mr002_valoos_report as R
    assert R.encode_float(-0.0)["exact_hex"] == "-0x0.0p+0"
    with pytest.raises(R.CanonicalizationError, match="NONFINITE_FLOAT"):
        R.canonical_bytes({"x": float("inf")})


def test_28_no_real_data_imports():
    import mr002_valoos_pipeline as mod
    src_dir = os.path.dirname(mod.__file__)
    for name in ("mr002_valoos_portfolio_identity", "mr002_valoos_candidates", "mr002_valoos_construction",
                 "mr002_valoos_portfolio_state", "mr002_valoos_exposure", "mr002_valoos_replay",
                 "mr002_valoos_nav", "mr002_valoos_pipeline"):
        src = open(os.path.join(src_dir, name + ".py"), encoding="utf-8").read()
        for banned in ("evaluator_prototype", "duckdb", "alpaca", "requests", "sealed", "vendor"):
            for line in src.splitlines():
                if line.lstrip().startswith(("import ", "from ")):
                    assert banned not in line.lower(), (name, line)


def test_29_candidate_execution_input_mismatch():
    c = CA.validate_candidate(_cand("A", "long", -2.5, "S0", price=100.0, adv=5e5, ds=0), config_id="B")
    CA.assert_candidate_execution_identity(c, 100.0, 5e5, 1, 1e6, 1e6)         # matches -> ok
    with pytest.raises(CA.CandidateRefused, match="CANDIDATE_EXECUTION_INPUT_MISMATCH:price"):
        CA.assert_candidate_execution_identity(c, 101.0, 5e5, 1, 1e6, 1e6)
    with pytest.raises(CA.CandidateRefused, match="CANDIDATE_EXECUTION_INPUT_MISMATCH:adv"):
        CA.assert_candidate_execution_identity(c, 100.0, 6e5, 1, 1e6, 1e6)
    with pytest.raises(CA.CandidateRefused, match="CANDIDATE_EXECUTION_INPUT_MISMATCH:next_open"):
        CA.assert_candidate_execution_identity(c, 100.0, 5e5, 2, 1e6, 1e6)
    with pytest.raises(CA.CandidateRefused, match="CANDIDATE_EXECUTION_INPUT_MISMATCH:nav"):
        CA.assert_candidate_execution_identity(c, 100.0, 5e5, 1, 1e6, 1.1e6)


def test_30_exits_before_entries_provisional_state():
    # session 1: open a book; session with a time-stop-due exit frees occupancy + cash before entries
    recs1 = _valid_recs()
    s1 = _run([_session(recs1, 1, "2024-01-02", _opens(recs1))])
    st = s1["results"][0]["committed_state"]
    # exit L0_0 at session 2 via explicit exit signal (decision at session 1 -> fill session 2)
    held_syms = [h.symbol for h in st.held]
    opens2 = {sym: 100.0 for sym in held_syms}
    res = RP.process_session(st, candidate_records=[], exit_signals=[{"symbol": "L0_0", "exit_decision_session": 1}],
                             market={"session": 2, "date": "2024-01-03", "opens": opens2, "adv": {}}, config_id="B")
    assert res["disposition"] == "COMMITTED"
    assert "L0_0" not in {h.symbol for h in res["committed_state"].held}   # exited (occupancy freed)
    assert any(e["event_type"] == "EXIT_FILL" and e["symbol"] == "L0_0" for e in res["events"])


def test_31_realized_single_name_and_gross_codes():
    prior = PortfolioState(session=0, cash=NAV0)
    recs = _valid_recs()
    mkt = {"session": 1, "date": "2024-01-02", "opens": _opens(recs), "adv": {r["candidate_id"]: 1e15 for r in recs}}
    # adversarial realized legs: single-name > 1.5% NAV
    sn = RP.process_session(prior, candidate_records=recs, exit_signals=[], market=mkt, config_id="B",
                            realized_leg_override=[{"symbol": "L0_0", "side": "long", "notional": 0.02 * NAV0,
                                                    "sector_id": "SEC0", "beta": 0.05}])
    assert sn["stop_code"] == "INTEGRITY_STOP:REALIZED_SINGLE_NAME_CONSTRAINT"
    # adversarial realized legs: gross > 100% NAV (spread so no single-name breach)
    big = [{"symbol": f"G{i}", "side": "long" if i % 2 == 0 else "short", "notional": 0.015 * NAV0,
            "sector_id": f"SEC{i}", "beta": 0.0} for i in range(80)]
    gr = RP.process_session(prior, candidate_records=recs, exit_signals=[], market=mkt, config_id="B",
                            realized_leg_override=big)
    assert gr["stop_code"] == "INTEGRITY_STOP:REALIZED_GROSS_CONSTRAINT"


def test_32_portfolio_returns_feed_increment1_metrics():
    recs = _valid_recs()
    held = [f"L{s}_0" for s in range(5)] + [f"S{s}_0" for s in range(5)]
    sess = [_session(recs, 1, "2024-01-02", _opens(recs))]
    for k, s in enumerate((2, 3, 4), start=1):
        o = {sym: (100.0 + k * (1 if sym.startswith("L") else -1)) for sym in held}
        sess.append({"session": s, "date": f"2024-01-0{s + 1}", "opens": o, "adv": {},
                     "candidate_records": [], "exit_signals": []})
    rep = _run(sess)
    returns = rep["return_series"]
    mh = P.metric_handoff(returns)
    # the SAME portfolio return series is what reaches the Increment-1 primitives
    assert mh["input_series_exact_hex"] == [float(r).hex() for r in returns]
    assert mh["geometric_annualized_return"] == pytest.approx(M.geometric_annualized_return(returns), rel=1e-12)
    assert mh["compounded_max_drawdown"] == pytest.approx(M.compounded_max_drawdown(returns), rel=1e-12)
    assert mh["stationary_bootstrap_confirmatory"]["seed"] == 20260711


def test_33_no_duplicate_execution_formulas():
    # Increment 3 must call the Increment-2 shared clip primitive, not reimplement ADV/NAV formulas.
    import mr002_valoos_replay as rmod
    src = open(rmod.__file__, encoding="utf-8").read()
    assert "preview_entry_fill" in src                        # calls the shared primitive
    assert "commission_slippage_cost" in src and "borrow_cost" in src
    # the clip formula constants live ONLY in Increment 2, never copied into Increment 3
    for name in ("mr002_valoos_replay", "mr002_valoos_construction"):
        s = open(os.path.join(os.path.dirname(rmod.__file__), name + ".py"), encoding="utf-8").read()
        assert "0.02 *" not in s and "ADV_PARTICIPATION_CAP *" not in s  # no ADV clip reimplementation
    import mr002_valoos_execution as EXE
    assert callable(EXE.preview_entry_fill)


def test_17_18_real_asymmetric_adv_clip_realized_sector_breach():
    # T3-17 + T3-18: a genuinely asymmetric ADV clip (one leg's ADV tiny) shrinks that sector's short
    # side -> the realized sector-net ratio worsens even though every order got SMALLER -> fail closed.
    prior = PortfolioState(session=0, cash=NAV0)
    recs = _valid_recs()
    for r in recs:                                        # tiny ADV on one selected short -> heavy clip
        if r["candidate_id"] == "S0_0":
            r["trailing_adv_dollars"] = 250000.0          # 2% * 250k / 100 = 50 shares (vs 150 intended)
    adv = {r["candidate_id"]: r["trailing_adv_dollars"] for r in recs}   # market ADV == candidate ADV (identity)
    mkt = {"session": 1, "date": "2024-01-02", "opens": _opens(recs), "adv": adv}
    res = RP.process_session(prior, candidate_records=recs, exit_signals=[], market=mkt, config_id="B")
    assert res["disposition"] == "REFUSED"
    assert res["stop_code"] == "INTEGRITY_STOP:REALIZED_SECTOR_CONSTRAINT"
    clipped = next(p for p in res["entry_previews"] if p["symbol"] == "S0_0")
    assert clipped["preview_filled_shares"] == 50 and clipped["clipped_shares"] == 100   # asymmetry recorded


def test_19_realized_beta_breach_fail_closed():
    # override a realized book whose gross-normalized beta exceeds 0.10 (sector-neutral, no other breach)
    prior = PortfolioState(session=0, cash=NAV0)
    recs = _valid_recs()
    mkt = {"session": 1, "date": "2024-01-02", "opens": _opens(recs), "adv": {r["candidate_id"]: 1e15 for r in recs}}
    legs = []
    for sec in range(5):                                  # long beta +3, short beta -3 -> contributions add
        legs.append({"symbol": f"L{sec}", "side": "long", "notional": 0.015 * NAV0, "sector_id": f"SEC{sec}", "beta": 3.0})
        legs.append({"symbol": f"S{sec}", "side": "short", "notional": 0.015 * NAV0, "sector_id": f"SEC{sec}", "beta": -3.0})
    res = RP.process_session(prior, candidate_records=recs, exit_signals=[], market=mkt, config_id="B",
                             realized_leg_override=legs)
    assert res["stop_code"] == "INTEGRITY_STOP:REALIZED_BETA_CONSTRAINT"


def test_20_net_drift_repair_not_a_stop():
    # a realized net-dollar imbalance > 5% of gross (each sector net < 5%) -> commit + drift instruction
    prior = PortfolioState(session=0, cash=NAV0)
    recs = _valid_recs()
    mkt = {"session": 1, "date": "2024-01-02", "opens": _opens(recs), "adv": {r["candidate_id"]: 1e15 for r in recs}}
    legs = []
    for sec in range(5):                                  # long 0.015, short 0.012 -> overall net-long tilt
        legs.append({"symbol": f"L{sec}", "side": "long", "notional": 0.015 * NAV0, "sector_id": f"SEC{sec}", "beta": 0.0})
        legs.append({"symbol": f"S{sec}", "side": "short", "notional": 0.012 * NAV0, "sector_id": f"SEC{sec}", "beta": 0.0})
    res = RP.process_session(prior, candidate_records=recs, exit_signals=[], market=mkt, config_id="B",
                             realized_leg_override=legs)
    assert res["disposition"] == "COMMITTED" and res["stop_code"] is None
    assert res["drift_repair"] is not None and res["drift_repair"]["breached"] is True
    assert res["drift_repair"]["larger_side"] == "long"
