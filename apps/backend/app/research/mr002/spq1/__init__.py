"""MR-002 Workstream C — SPQ-1 Phase 1: synthetic signal & data-production implementation.

Deterministic producer implementing the CLOSED SPQ-1 Phase-0 specification
(census sha 87602e7c, owner-rulings sha d8a9071d, schema sha 49c0e550). Emits
``SignalDecisionRecord`` (close-t decision facts) and ``ExecutionEnrichedCandidateRecord``
(t+1 execution facts) — the candidate facts the closed Increment-3 replay path consumes.

SYNTHETIC-ONLY. This package imports no vendor adapter, no order-path / broker / risk /
strategy-template / Increment-3 module, and opens no real / development / validation / OOS
dataset. It qualifies implementation correctness only; it computes no performance metric.

It is INDEPENDENT of the Stage-3-frozen ``app.research.mr002.signal`` module (which it does
not import or modify): Phase 1 registers its own solver identity and rank tolerance and emits
typed refusal codes per the closed Phase-0 taxonomy.
"""
from __future__ import annotations

PHASE0_CENSUS_SHA256 = "87602e7c5e5c719a44d83d6a556690116958c58e1e0d97b687531da824f9008e"
PHASE0_OWNER_RULINGS_SHA256 = "d8a9071d53bdb036ad9e6d46cd0d899f6846d3f2af946f932ce963e10f0e206a"
PHASE0_SCHEMA_SHA256 = "49c0e550f78127e04fcf92a649645aef23560173ccf89ef630dab30d4892497f"

PRODUCER_CODE_VERSION = "spq1-phase1-v1.0-synthetic"
