"""Forward-validation PRODUCTION data bindings (R5c) — every data input tied to a real source.

R5a proves the data is final; R5b proves the adjusted series reflects the declared actions. This module
is where those checks stop taking their inputs from a caller and start taking them from the governed
store itself:

  * `declare_action_source(store)` — the corporate-action source declaration DERIVED from the completed
    ingest artifact, never hand-written;
  * `pit_price_fn(store)` — the point-in-time price function the shadow ledger marks against;
  * `build_forward_context(...)` — the per-session `ForwardRunContext` on the frozen §0 bindings.

## Source authority cannot be asserted, and today it cannot even be derived

`ingest_runs` records that an ingest RAN — `(dataset, started_at, finished_at, rows, status)` — not what
it COVERED. Deriving a coverage window from `MIN(actions.date)`/`MAX(actions.date)` would be exactly the
invented coverage the governance forbids: the earliest row present is evidence of what was loaded, not
of what was requested, and on an empty table it is no evidence at all.

`declare_action_source` therefore reads `dataset_coverage` — the record a COMPLETED ingest writes,
carrying the requested window and the immutable artifact identity — and returns a NON-authoritative
declaration when that record is absent. The governed store has no such record today (its `actions`
table is empty), so the honest result is "coverage unknown", and R5b's verdict stays
NOT_PROVEN_INSUFFICIENT_DATA until an authoritative ACTIONS ingest exists.

## Prices are point-in-time by construction

`pit_price_fn` reads `closeadj` for the exact session only. It cannot return a later session's price
because it never queries one: a lookahead would have to be introduced deliberately, not by accident.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from app.validation.adjustment_verifier import ActionSourceDeclaration
from app.validation.forward_window import (
    BENCHMARK_COMMITS,
    DGS3MO_OBSERVATION_CUTOFF,
    EFFECTIVE_DSR_TRIAL_COUNT,
    FROZEN_CONFIG,
    VALIDATION_MEASUREMENT_COMMIT,
    ForwardRunContext,
    IntegrityStop,
)

ACTIONS_DATASET = "actions"


class BindingError(IntegrityStop):
    """A production binding could not be established from an authoritative source. Fails closed."""


def declare_action_source(store: Any, *, dataset: str = ACTIONS_DATASET) -> ActionSourceDeclaration:
    """Derive the corporate-action source declaration from the store's own ingest provenance.

    Authoritative ONLY when a completed ingest recorded its coverage window and artifact identity. No
    record → `authoritative=False` with no coverage, which is the truthful state of a store whose
    ACTIONS dataset was never ingested (the governed store today). The identity carries the artifact
    digest so a later verification cannot be re-read against a different load of the same dataset.
    """
    con = getattr(store, "con", store)
    if not hasattr(con, "execute"):
        raise BindingError(f"not a queryable store: {type(store).__name__}")
    try:
        row = con.execute(
            "SELECT coverage_start, coverage_end, artifact_sha256, source_identity, recorded_at "
            "FROM dataset_coverage WHERE dataset = ? AND LOWER(status) = 'ok' "
            "ORDER BY recorded_at DESC LIMIT 1", [dataset]).fetchone()
    except Exception as exc:
        # An older store predates the coverage table entirely: unknown coverage, never authoritative.
        return ActionSourceDeclaration(
            identity=f"{dataset}:coverage-unrecorded ({type(exc).__name__})", authoritative=False)
    if row is None:
        return ActionSourceDeclaration(identity=f"{dataset}:coverage-unrecorded", authoritative=False)

    coverage_start, coverage_end, artifact, source_identity, _recorded = row
    if not artifact or not source_identity:
        return ActionSourceDeclaration(
            identity=f"{dataset}:coverage-incomplete", authoritative=False,
            coverage_start=coverage_start, coverage_end=coverage_end)
    return ActionSourceDeclaration(
        identity=f"{source_identity}@{artifact}", authoritative=True,
        coverage_start=coverage_start, coverage_end=coverage_end)


def pit_price_fn(store: Any) -> Callable[[str, date], float | None]:
    """A point-in-time `closeadj` reader: the price of `ticker` ON `session`, or None.

    No fallback to a neighbouring session, no forward fill, no "last known price". A name without a
    usable mark on the session returns None, and the caller (the shadow ledger's mark-to-market) leaves
    that sleeve at its previous mark rather than inventing one — the same behaviour the census had.
    """
    con = getattr(store, "con", store)
    if not hasattr(con, "execute"):
        raise BindingError(f"not a queryable store: {type(store).__name__}")

    def price(ticker: str, session: date) -> float | None:
        row = con.execute(
            "SELECT closeadj FROM sep WHERE ticker = ? AND date = ? AND closeadj IS NOT NULL",
            [ticker, session]).fetchone()
        return float(row[0]) if row is not None and row[0] is not None else None

    return price


def build_forward_context(
    session: date,
    *,
    dgs3mo_path: Path,
    trial_ledger_path: Path,
    ledger_account_id: int,
    is_nyse_trading_session: bool = True,
    code_commit: str = VALIDATION_MEASUREMENT_COMMIT,
    config: dict | None = None,
) -> ForwardRunContext:
    """The per-session run context on the FROZEN §0 bindings.

    Everything the preflight gate verifies comes from the frozen module constants rather than from a
    caller-supplied dict, so a session cannot be run against a quietly different benchmark set, cutoff
    or trial count. The two artifact PATHS and the ledger account are deployment facts and stay
    parameters; the gate digests the artifacts themselves.
    """
    if ledger_account_id == 4:
        raise BindingError("the validation ledger may never be Account 4")
    return ForwardRunContext(
        session_date=session,
        is_nyse_trading_session=is_nyse_trading_session,
        code_commit=code_commit,
        benchmark_commits=dict(BENCHMARK_COMMITS),
        dgs3mo_path=dgs3mo_path,
        dgs3mo_cutoff=DGS3MO_OBSERVATION_CUTOFF,
        trial_ledger_path=trial_ledger_path,
        effective_dsr_trial_count=EFFECTIVE_DSR_TRIAL_COUNT,
        config=dict(config or FROZEN_CONFIG),
        ledger_account_id=ledger_account_id,
        ledger_is_shadow_or_separate_paper=True,
        references_account4_capital=False,
        references_retired_baseline=False,
    )
