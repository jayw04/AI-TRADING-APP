"""Forward-validation FIRST observation — the governed window-open transition (PREREG v1.0 §0/§5).

Builds on `forward_window.preflight` (the fail-closed gate) and on `observation_store` (the one atomic
commit protocol, shared with every later session — R3). This module is the window-OPEN transition and
nothing else: it commits sequence 1 and advances the storage-derived forward session count 0 → 1. A
preflight PASS alone does not open the window; only a completed, digest-verified, durable, no-overwrite
directory publish does.

Committed directory layout (`observations/000001/`):
  open.json        — the OPEN operator-visible record (no performance)
  sealed.bin       — the sealed performance payload (segregated; digest-referenced only)
  provenance.json  — the first-observation provenance (owner-required fields)
  manifest.json    — {file → sha256} over open.json, sealed.bin, provenance.json
  commit.json      — the IMMUTABLE ROOT MARKER: {sha256(manifest.json), sequence, session_date,
                     previous_commit_sha256 (null for the first observation — the chain starts here)}

The root binding is acyclic: commit.json hashes manifest.json; manifest.json hashes the three content
files; nothing the manifest hashes contains the manifest's own digest. commit.json is the anchor and
must never be rewritten for a committed observation — later observations bind its digest as their chain
link, so a rewrite here invalidates the whole downstream record (see `observation_store`).

The full commit protocol (owner ruling 2026-07-23, second CHANGES REQUESTED) lives in
`observation_store.commit_observation`; sessions 2..N run the identical path via `session_recorder`.

Nothing here touches Account 4: the write goes to the shadow / separate paper-validation ledger, and the
authoritative before/after probes prove the live book was unchanged across the commit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from app.validation.forward_window import (
    ForwardRunContext,
    IntegrityStop,
    OpenObservation,
    preflight,
    seal_performance,
)
from app.validation.observation_store import (
    FIRST_SEQUENCE,
    Account4StateProbe,
    BestEffortDurability,
    CommittedObservation,
    Durability,
    ObservationCommitError,
    StrictDurability,
    assert_open_record_has_no_sealed_content,
    build_open_record,
    canon,
    commit_observation,
    committed_observations,
    committed_session_count,
    default_durability,
    publish_no_overwrite,
    semantic_digest,
    validate_committed_observation,
)

# `WindowOpenError` is the name this module has raised since #476 (the window-OPEN failure). It is the
# store's commit error: one exception class for one commit protocol, whatever the sequence.
WindowOpenError = ObservationCommitError

__all__ = [
    "FIRST_SEQUENCE",
    "Account4StateProbe",
    "BestEffortDurability",
    "CommittedObservation",
    "Durability",
    "FirstObservationProvenance",
    "IntegrityStop",
    "ObservationCommitError",
    "OpenObservation",
    "StrictDurability",
    "WindowOpenError",
    "assert_open_record_has_no_sealed_content",
    "build_open_record",
    "canon",
    "commit_observation",
    "committed_observations",
    "committed_session_count",
    "default_durability",
    "open_first_window_session",
    "publish_no_overwrite",
    "semantic_digest",
    "validate_committed_observation",
]

_SEQUENCE = FIRST_SEQUENCE                      # this module opens the FIRST observation only


@dataclass
class FirstObservationProvenance:
    """The provenance fields the first successful observation must record (owner 2026-07-23)."""
    preflight_execution_timestamp: str          # ISO8601 UTC — caller-supplied (Date.now unavailable)
    deployed_tree_identity: str                 # git commit/tree of the running validation code
    shadow_ledger_identity: str                 # the shadow / separate paper-validation ledger id
    observation_sequence: int                   # 1 for the first observation
    open_record_sha256: str
    sealed_payload_sha256: str
    account4_unchanged: bool                     # True iff the authoritative after-probe == before-probe
    account4_state_digest_before: str            # authoritative before-probe
    account4_state_digest_after: str             # authoritative after-probe (verified == before at publish)


def open_first_window_session(
    ctx: ForwardRunContext,
    *,
    preflight_timestamp: str,
    deployed_tree_identity: str,
    shadow_ledger_identity: str,
    account4_probe: Callable[[], Account4StateProbe],
    rebalances: int,
    orders: int,
    seeds: int,
    operational: dict,
    sealed_performance: dict,
    store_dir: Path,
    durability: Durability | None = None,
    data_finality: dict | None = None,
    decision_evidence: dict | None = None,
) -> tuple[OpenObservation, FirstObservationProvenance, int]:
    """Run the gate, then COMMIT the first observation as one atomic, no-overwrite directory publish,
    and return the session count derived from validated committed storage (1 on success). Refuses if
    committed storage already holds an observation — this path opens the window, it never extends it
    (sessions 2..N go through `session_recorder.record_forward_session`). Nothing partial or observable
    is left on any failure path; the publish mutex is released on success and on every failure."""
    preflight(ctx)                                                          # fail closed BEFORE anything

    if committed_session_count(store_dir) != 0:                            # validated, storage-derived
        raise WindowOpenError(
            "committed storage already holds an observation — this is not the first session (expected 0)")

    sealed_sha, sealed_bytes = seal_performance(sealed_performance)
    open_obs = build_open_record(ctx, rebalances=rebalances, orders=orders, seeds=seeds,
                                 operational=operational, sealed_sha=sealed_sha,
                                 data_finality=data_finality,
                                 decision_evidence=decision_evidence)
    open_dict = asdict(open_obs)
    assert_open_record_has_no_sealed_content(open_dict, sealed_performance)
    open_bytes = canon(open_dict)

    written: dict[str, FirstObservationProvenance] = {}

    def _build_provenance(before_digest: str, previous_commit_sha256: str | None) -> dict:
        if previous_commit_sha256 is not None:                              # belt-and-braces: seq 1 only
            raise WindowOpenError(
                "the first observation must not chain to a previous commit "
                f"(got {previous_commit_sha256!r})")
        prov = FirstObservationProvenance(
            preflight_execution_timestamp=preflight_timestamp,
            deployed_tree_identity=deployed_tree_identity,
            shadow_ledger_identity=shadow_ledger_identity,
            observation_sequence=_SEQUENCE,
            open_record_sha256=semantic_digest(open_dict),
            sealed_payload_sha256=sealed_sha,
            account4_unchanged=True,              # enforced by the publish gate (after == before)
            account4_state_digest_before=before_digest,
            account4_state_digest_after=before_digest,   # verified == before authoritatively at publish
        )
        written["prov"] = prov
        return asdict(prov)

    result = commit_observation(
        store_dir=store_dir, sequence=_SEQUENCE, session_date=ctx.session_date.isoformat(),
        open_bytes=open_bytes, sealed_bytes=sealed_bytes, build_provenance=_build_provenance,
        account4_probe=account4_probe, preflight_timestamp=preflight_timestamp,
        deployed_tree_identity=deployed_tree_identity, durability=durability)
    return open_obs, written["prov"], result.session_count
