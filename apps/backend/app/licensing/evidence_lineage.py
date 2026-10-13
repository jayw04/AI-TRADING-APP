"""PU-1 input lineage of the Evidence panels and KPI rows (declarative, traced by hand).

Each KPI row, and each Evidence panel that is built from owner records, declares the INPUTS it
reads. An input is either

* a ``RecordInput`` -- one of the owner's own operational records (audit-log action counts,
  reconciliation runs, equity-snapshot dates, strategy configuration rows), or
* a ``BrokerFieldInput`` -- a field of a broker response that reaches the row through a stored copy
  (e.g. the circuit breaker's ``unrealized_pnl_now`` is ``SUM(positions.unrealized_pl)``), classified
  per field by ``broker_field_classification.json``.

The row's sources are the union of its inputs' sources, so a row that depends (even indirectly) on
a marked-to-market value is PERSONAL while sibling rows built only from owner records stay
COMMERCIAL_OK. Taint is never removed here to make a panel presentable; to change a classification,
change the input list (with its trace) in review.

``trace`` strings are the file:line evidence for the declaration (as of the commit that wrote
them); they are data for the reviewer and for the ``test_every_input_has_a_trace`` test.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.licensing.broker_fields import sources_of_fields
from app.licensing.registry import OWNER_GENERATED_RECORDS


@dataclass(frozen=True)
class RecordInput:
    """An owner-created operational record (no vendor value is read from it)."""

    name: str
    trace: str


@dataclass(frozen=True)
class BrokerFieldInput:
    """A broker-response field that reaches the artifact (directly or via a stored copy)."""

    kind: str
    fields: tuple[str, ...]
    trace: str


Input = RecordInput | BrokerFieldInput


def sources_of_inputs(inputs: Iterable[Input]) -> tuple[str, ...]:
    """Sorted licence source ids of ``inputs``. No inputs => ``()`` (UNKNOWN at the gate)."""
    out: set[str] = set()
    for i in inputs:
        if isinstance(i, RecordInput):
            out.add(OWNER_GENERATED_RECORDS)
        else:
            out |= sources_of_fields(i.kind, i.fields)
    return tuple(sorted(out))


# --- shared inputs -----------------------------------------------------------------------------

_AUDIT_COUNTS = RecordInput(
    "audit_log action counts (ORDER_RISK_PASSED, ORDER_REJECTED_BY_RISK, ORDER_REJECTED_BY_BROKER, "
    "CIRCUIT_BREAKER_TRIPPED/RESET, ORDER_SUBMITTED, ORDER_FILL_INGESTED, REPLAY_MISMATCH, "
    "RECONCILIATION_DISCREPANCY): the owner's own audit rows, counted; no payload value is read",
    "app/api/v1/evidence.py (audit = GROUP BY action); scripts/ops_kpis.py:build; "
    "scripts/confidence_score.py:_audit_counts",
)
_RECON_RUNS = RecordInput(
    "reconciliation_runs.result / n_discrepancies: position quantity comparison only "
    "(symbol + qty of local vs broker positions)",
    "app/services/reconciliation.py:64-104 (_local_qty_by_ticker, _broker_qty_by_ticker, "
    "diff_positions use symbol and qty only)",
)
_SNAPSHOT_DATES = RecordInput(
    "equity_snapshots: the DATES on which a snapshot exists (min/distinct date); the equity "
    "values are not read",
    "app/api/v1/evidence.py (min(EquitySnapshot.ts), count(distinct(date(ts)))); "
    "scripts/ops_kpis.py:build; scripts/confidence_score.py:_track_record_days",
)
_REPLAY_RUN_COUNTS = RecordInput(
    "replay_runs.n_checked / n_matched / n_mismatched: counters of the owner's replay passes",
    "app/db/models/replay_run.py; app/services/replay.py:run_replay",
)
_REPLAY_BREAKER_INPUT = BrokerFieldInput(
    "position",
    ("unrealized_pl",),
    "replay recomputes the circuit-breaker trip from the audit payload: net_pnl = "
    "realized_pnl_today + unrealized_pnl_now (app/services/replay.py:94-107). unrealized_pnl_now "
    "is SUM(positions.unrealized_pl) (app/risk/circuit_breaker.py:543-552, audit payload at :184 "
    "and :234), a broker marked-to-market field mirrored by app/services/position_sync.py:252-257. "
    "A replay MATCH therefore re-validates a decision taken on a market-marked value. The "
    "aggregate counters cannot be split by decision type, so the whole ratio carries the taint.",
)


# --- KPI rows ----------------------------------------------------------------------------------

KPI_ROW_INPUTS: dict[str, tuple[Input, ...]] = {
    "reconciliation_success": (_RECON_RUNS,),
    "reconciliation_drift": (_RECON_RUNS, _AUDIT_COUNTS),
    "replay_consistency": (_REPLAY_RUN_COUNTS, _REPLAY_BREAKER_INPUT),
    "risk_gate_efficacy": (_AUDIT_COUNTS,),
    "breaker_recovery": (_AUDIT_COUNTS,),
    "fill_success": (_AUDIT_COUNTS,),
    "operational_continuity": (_SNAPSHOT_DATES,),
}

# Confidence panel: track-record days (snapshot dates), replay mismatch counters (market-dependent
# through the breaker-trip replay), reconciliation discrepancies, and audit-action counts.
CONFIDENCE_INPUTS: tuple[Input, ...] = (
    _SNAPSHOT_DATES,
    _REPLAY_RUN_COUNTS,
    _REPLAY_BREAKER_INPUT,
    _RECON_RUNS,
    _AUDIT_COUNTS,
)

# Strategies panel: the owner's strategy configuration rows (id, name, status, params_json keys
# vol_target_annual / use_daily_overlay). No market data.
STRATEGIES_INPUTS: tuple[Input, ...] = (
    RecordInput(
        "strategies rows: id, name, status, params_json.vol_target_annual, "
        "params_json.use_daily_overlay (owner configuration)",
        "app/api/v1/evidence.py (strategies list)",
    ),
)


def kpi_row_sources() -> dict[str, tuple[str, ...]]:
    """Per-KPI-row sources, evaluated at call time (so a changed input list is honoured)."""
    return {key: sources_of_inputs(inputs) for key, inputs in KPI_ROW_INPUTS.items()}


def kpi_scorecard_sources() -> tuple[str, ...]:
    """Sources of the whole scorecard: the union over its rows (most restrictive wins)."""
    return tuple(sorted({s for srcs in kpi_row_sources().values() for s in srcs}))


def confidence_sources() -> tuple[str, ...]:
    return sources_of_inputs(CONFIDENCE_INPUTS)


def strategies_sources() -> tuple[str, ...]:
    return sources_of_inputs(STRATEGIES_INPUTS)
