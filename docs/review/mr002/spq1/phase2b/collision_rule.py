"""Governed request-identity collision rule (SPQ-1 Phase 2B run-spec amendment v1.1) — runner-side.

Implements MR002_SPQ1_NONINJECTIVE_REQUEST_IDENTITY_V1 OUTSIDE the frozen Phase-2B execution modules, so
``phase2b_orchestration_code_identity`` (bb029a96...) is unchanged. Detection is a governed
pre-production step: resolve the provisional permanent_security_id via the SAME registered lineage
resolver + session ordinal that ``run_unit`` uses, group by (session, permsec), and for any group with
>1 distinct request symbol emit an UNRESOLVED INTEGRITY_STOP for EVERY claimant (no winner selected, no
signal produced). This module applies NO alternative identity logic, caching, fallback, or tie-break.

This module's SHA-256 is the runner-side governed-collision identity bound in the amended manifests
(separate from the frozen bb029a96 orchestration identity).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(str(Path(__file__).resolve().parents[5]), "apps", "backend"))

from app.research.mr002.spq1.identities import canonical_sha256  # noqa: E402
from app.research.mr002.spq1.phase2b import orchestrator as ORCH  # noqa: E402
from app.research.mr002.spq1.refusals import SignalRefusal  # noqa: E402

COLLISION_RULE_ID = "MR002_SPQ1_NONINJECTIVE_REQUEST_IDENTITY_V1"
COLLISION_CODE = "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS"
LINEAGE_IDENTITY_SOURCE = ("registered_pit_identity_registry "
                           "(adapters.identity_adapter.load_identity_registry.resolve_permanent_id)")


def detect_request_identity_collisions(units, resolve):  # noqa: ANN001
    """Governed pre-production collision detection.

    units: iterable of (request_symbol, session_ordinal). ``resolve`` MUST be the same registered lineage
    resolver + session ordinal ``run_unit`` uses -> resolve(symbol, t) returns a permanent_security_id, or
    raises SignalRefusal / returns "" when no provisional identity is established. No alternative identity
    logic, caching, fallback, or tie-break is applied.

    A collision group = a (session, provisional permanent_security_id) claimed by >1 DISTINCT request
    symbol -> the request->permanent-security mapping is non-injective at t. Returns (collisions, groups):
      collisions: {(t, symbol): {claimed_permanent_security_id, colliding_request_symbols, collision_cardinality}}
      groups:     {(t, permsec): sorted distinct claimant symbols}   (cardinality > 1 only)
    """
    prov: dict = {}
    for symbol, t in units:
        try:
            ps = resolve(symbol, t)
        except SignalRefusal:
            ps = None                      # single-request lineage ambiguity is NOT a collision
        if ps:
            prov.setdefault((t, ps), []).append(symbol)
    collisions: dict = {}
    groups: dict = {}
    for (t, ps), syms in prov.items():
        distinct = sorted(set(syms))
        if len(distinct) > 1:              # non-injective at t -> all claimants stop, no winner
            groups[(t, ps)] = distinct
            for s in distinct:
                collisions[(t, s)] = {"claimed_permanent_security_id": ps,
                                      "colliding_request_symbols": distinct,
                                      "collision_cardinality": len(distinct)}
    return collisions, groups


def assert_whole_session_request_set(units, expected_members):  # noqa: ANN001
    """Whole-session collision-detection invariant: for EVERY session in this shard, the requests
    presented to detection MUST equal the complete authorized in_long_universe request set for that
    session. A session may never be split across independently-detected batches -- a split could hide a
    collision spanning those batches. Fail-fast STOP on violation."""
    exp = set(expected_members)
    by_session: dict = {}
    for symbol, t in units:
        by_session.setdefault(t, set()).add(symbol)
    for t, syms in by_session.items():
        if syms != exp:
            raise ValueError(
                f"whole-session invariant violated at session {t}: presented {len(syms)} requests != "
                f"complete authorized member set ({len(exp)}) -> session split across batches; STOP")
    return len(by_session)


def run_shard_governed(ctx, units, expected_members=None):  # noqa: ANN001
    """Frozen-code-preserving governed shard runner. Detects non-injective request-identity collisions
    (AFTER provisional resolution, BEFORE sector/earnings/producer/record-identity), emits an UNRESOLVED
    INTEGRITY_STOP for EVERY claimant in a collision group (no winner, no signal produced), and calls the
    frozen ``run_unit`` ONLY for non-colliding requests. Returns (results, content_sha256, collision_rows)
    where collision_rows are per-request diagnostics for the CollisionCensus.

    ``expected_members`` (the authorized in_long_universe member set for this shard's governing month), when
    provided, enforces the whole-session invariant BEFORE detection: every session must present its
    complete authorized request set (no split batches)."""
    if expected_members is not None:
        assert_whole_session_request_set(units, expected_members)
    resolve = ctx.lineage.resolve_permanent_id          # the SAME registered resolver run_unit uses
    collisions, _groups = detect_request_identity_collisions(units, resolve)
    cal = ctx.calendar.sessions
    results = []
    collision_rows = []
    for symbol, t in units:
        info = collisions.get((t, symbol))
        if info is not None:
            # collision: provisional identity is NOT accepted -> unresolved integrity stop for this claimant
            results.append(ORCH.UnitResult("", symbol, t, "INTEGRITY_STOP", COLLISION_CODE, None, None))
            ps = info["claimed_permanent_security_id"]
            collision_rows.append({
                "decision_session": t, "session_date": cal[t], "request_symbol": symbol,
                "request_key": [t, symbol], "collision_group_id": f"{cal[t]}|{ps}",
                "claimed_permanent_security_id": ps,
                "colliding_request_symbols": info["colliding_request_symbols"],
                "collision_cardinality": info["collision_cardinality"],
                "identity_source": LINEAGE_IDENTITY_SOURCE, "collision_rule_id": COLLISION_RULE_ID,
                "terminal_disposition": "INTEGRITY_STOP", "terminal_code": COLLISION_CODE,
                "terminal_key": [t, f"UNRESOLVED:{symbol}"]})
        else:
            results.append(ORCH.run_unit(ctx, symbol, t))   # frozen production, non-colliding requests only
    results.sort(key=lambda r: r.key())
    content = canonical_sha256([r.as_row() for r in results])
    return results, content, collision_rows


def module_identity() -> str:
    """SHA-256 of this module's source (the runner-side governed-collision identity)."""
    import hashlib
    return hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()
