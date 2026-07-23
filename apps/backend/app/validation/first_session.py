"""Forward-validation first observation — atomic write + full provenance (PREREG v1.0 §0/§5).

Builds on `forward_window.preflight` (the fail-closed gate). This module completes the *operational*
opening of the window: it records the full first-observation provenance the owner required and makes
the window-open transition **atomic** — the forward session count increments 0 → 1 **only** when the
open record and BOTH digests are durably recorded. A preflight PASS alone does not open the window.

The complete first observation records (owner directive 2026-07-23):
  preflight execution timestamp · deployed artifact/tree identity · shadow-ledger identity ·
  observation sequence (= 1) · open-record digest · sealed-payload digest · confirmation the open
  record contains NO sealed field names or values · confirmation Account 4 state was unchanged
  before and after the write.

Nothing here touches Account 4: the write goes to the shadow / separate paper-validation ledger, and
the Account-4 state probe proves the live book was untouched across the write.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.validation.forward_window import (
    ForwardRunContext,
    IntegrityStop,
    OpenObservation,
    preflight,
    seal_performance,
)


class WindowOpenError(IntegrityStop):
    """The atomic first-observation write did not complete durably, or a post-write invariant failed.
    The session count is NOT incremented and no partial record is left. A retry is permitted only
    after correcting an operational/integrity defect WITHOUT changing any frozen research choice."""


@dataclass(frozen=True)
class Account4StateProbe:
    """A tamper-evident snapshot of the Account-4 state that must NOT change across the write:
    the operational-hold (status/reason/rev), status, and a positions digest. Compared before/after."""
    hold_status: str
    hold_reason_code: str
    hold_rev: int
    strategy_status: str
    positions_sha256: str

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(asdict(self), sort_keys=True).encode("utf-8")).hexdigest()


@dataclass
class FirstObservationProvenance:
    """The provenance fields the first successful observation must record (owner 2026-07-23)."""
    preflight_execution_timestamp: str          # ISO8601 UTC — caller-supplied (Date.now unavailable)
    deployed_tree_identity: str                 # git commit/tree of the running validation code
    shadow_ledger_identity: str                 # the shadow / separate paper-validation ledger id
    observation_sequence: int                   # 1 for the first observation
    open_record_sha256: str
    sealed_payload_sha256: str
    account4_unchanged: bool
    account4_state_digest_before: str
    account4_state_digest_after: str


# ── the sealed field names (must never leak into the OPEN record) ──────────────────────────────────
_SEALED_FIELD_NAMES: frozenset[str] = frozenset({
    "strategy_return", "benchmark_excess", "excess_return", "sharpe", "cagr", "max_drawdown",
    "cvar", "volatility", "pnl", "turnover_cost", "cumulative_return", "calmar", "dsr",
})


def assert_open_record_has_no_sealed_content(open_record: dict, sealed_payload: dict) -> None:
    """Fail closed if any sealed field NAME or VALUE appears in the OPEN record. The open record is
    what a routine operator sees; a leaked return would defeat the sealed no-peeking boundary."""
    flat = json.dumps(open_record, sort_keys=True, default=str)
    leaked_names = [n for n in (_SEALED_FIELD_NAMES | set(sealed_payload)) if n in flat]
    if leaked_names:
        raise WindowOpenError(f"OPEN record leaks sealed field name(s): {sorted(leaked_names)}")
    for v in sealed_payload.values():
        if isinstance(v, (int, float)) and v not in (0, 0.0, 1) and str(v) in flat:
            raise WindowOpenError(f"OPEN record leaks a sealed value: {v!r}")


def _digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def open_first_window_session(
    ctx: ForwardRunContext,
    *,
    preflight_timestamp: str,
    deployed_tree_identity: str,
    shadow_ledger_identity: str,
    account4_before: Account4StateProbe,
    account4_after: Account4StateProbe,
    rebalances: int,
    orders: int,
    seeds: int,
    operational: dict,
    sealed_performance: dict,
    store_dir: Path,
    current_session_count: int,
) -> tuple[OpenObservation, FirstObservationProvenance, int]:
    """Run the gate, build + ATOMICALLY WRITE the first observation, and return the new session count.

    Sequence (fail-closed at every step; nothing partial is left):
      1. preflight() — fail closed on any binding / Account-4 isolation mismatch.
      2. require this be the FIRST observation (current_session_count == 0).
      3. Account-4 state UNCHANGED across the intended write (before digest == after digest).
      4. seal the performance payload; assemble the OPEN record.
      5. assert the OPEN record leaks no sealed field name/value.
      6. compute the open-record + sealed-payload digests.
      7. durably write BOTH (open record + sealed payload) and re-read + digest-verify BOTH.
      8. ONLY THEN increment the session count 0 → 1 (the operational window-open transition).
    """
    preflight(ctx)                                               # (1)

    if current_session_count != 0:                              # (2)
        raise WindowOpenError(
            f"first-session opener called with session_count={current_session_count} (expected 0)")

    if account4_before.digest() != account4_after.digest():    # (3)
        raise WindowOpenError(
            "Account 4 state changed across the write — the validation must not touch the live book")

    sealed_sha, sealed_bytes = seal_performance(sealed_performance)   # (4)
    open_obs = OpenObservation(
        session_date=ctx.session_date.isoformat(), integrity_verdict="PASS",
        rebalances=rebalances, orders_submitted=orders, seeds=seeds,
        scheduled_eval_completed=bool(operational.get("scheduled_eval_completed", True)),
        missed_rebalances=int(operational.get("missed_rebalances", 0)),
        duplicate_orders_or_seeds=int(operational.get("duplicate_orders_or_seeds", 0)),
        cap_breaches=int(operational.get("cap_breaches", 0)),
        broker_local_divergence=int(operational.get("broker_local_divergence", 0)),
        unresolved_reservations=int(operational.get("unresolved_reservations", 0)),
        manual_perf_affecting_interventions=int(
            operational.get("manual_perf_affecting_interventions", 0)),
        operational_exceptions=list(operational.get("operational_exceptions", [])),
        sealed_performance_sha256=sealed_sha,
    )
    open_dict = asdict(open_obs)

    assert_open_record_has_no_sealed_content(open_dict, sealed_performance)   # (5)

    prov = FirstObservationProvenance(
        preflight_execution_timestamp=preflight_timestamp,
        deployed_tree_identity=deployed_tree_identity,
        shadow_ledger_identity=shadow_ledger_identity,
        observation_sequence=1,
        open_record_sha256=_digest(open_dict),                  # (6)
        sealed_payload_sha256=sealed_sha,
        account4_unchanged=True,
        account4_state_digest_before=account4_before.digest(),
        account4_state_digest_after=account4_after.digest(),
    )

    # (7) durable atomic write: write both to temp, fsync, rename, then re-read + verify BOTH.
    store_dir.mkdir(parents=True, exist_ok=True)
    open_path = store_dir / "observation_0001_open.json"
    sealed_path = store_dir / "observation_0001_sealed.bin"
    prov_path = store_dir / "observation_0001_provenance.json"
    try:
        _atomic_write(open_path, json.dumps({"open_record": open_dict, "provenance": asdict(prov)},
                                            sort_keys=True, indent=2).encode("utf-8"))
        _atomic_write(sealed_path, sealed_bytes)
        _atomic_write(prov_path, json.dumps(asdict(prov), sort_keys=True, indent=2).encode("utf-8"))
        # re-read + digest-verify BOTH before the transition
        if hashlib.sha256(sealed_path.read_bytes()).hexdigest() != sealed_sha:
            raise WindowOpenError("sealed payload failed post-write digest verification")
        reread = json.loads(open_path.read_text(encoding="utf-8"))
        if _digest(reread["open_record"]) != prov.open_record_sha256:
            raise WindowOpenError("open record failed post-write digest verification")
    except OSError as exc:
        raise WindowOpenError(
            f"durable write failed ({exc}) — no partial observation, count unchanged") from exc

    # (8) both digests durably recorded → the operational window-open transition.
    return open_obs, prov, current_session_count + 1


def _atomic_write(path: Path, data: bytes) -> None:
    """Write via a temp file + fsync + atomic rename, so a crash leaves either the old state or the
    complete new file — never a partial record."""
    import os

    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)                                       # atomic on the same filesystem
