"""Forward-validation session recorder — observations 2..N (R3).

`first_session` opens the window (sequence 1). This module records every session after it, through the
IDENTICAL fail-closed commit protocol in `observation_store`: the same atomic no-overwrite directory
publish, the same storage-derived session count, the same per-sequence publish mutex, the same
authoritative Account-4 before/after probes, the same strict fsync durability, and the same complete
digest verification of every staged file. There is no "later sessions are routine" path — session 250 is
committed exactly as session 1 was.

What this module adds is the part that only exists once there is a record to extend:

  • the sequence is DERIVED from fully validated committed storage (never supplied by a caller);
  • the window must already be open — recording refuses while the committed count is 0, so a forward
    record can never begin at sequence 2 with a missing first observation;
  • each observation binds the previous observation's `commit.json` digest, making the committed tree an
    append-only hash chain (a rewritten earlier observation invalidates every later one);
  • the session date must strictly follow the previous observation's, so a session cannot be recorded
    twice and cannot be back-dated into the record;
  • the frozen-binding gate (`forward_window.preflight`) runs on EVERY session, not just the first — a
    mid-window config drift, benchmark change, DGS3MO/trial-ledger substitution, or any Account-4
    isolation breach stops the run with nothing written.

An integrity stop here is a permitted outcome (§5.4), not a performance result: no observation is
written, the session count does not advance, and Account 4 is untouched.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from app.validation.forward_window import (
    ForwardRunContext,
    OpenObservation,
    preflight,
    seal_performance,
)
from app.validation.observation_store import (
    Account4StateProbe,
    Durability,
    ObservationCommitError,
    assert_open_record_has_no_sealed_content,
    build_open_record,
    canon,
    commit_observation,
    committed_observations,
    semantic_digest,
)


@dataclass
class ObservationProvenance:
    """The provenance a session observation (sequence ≥ 2) records. It is the first-observation set plus
    the two chain facts that only exist for a continued record: the previous observation's commit digest
    and its session date."""
    preflight_execution_timestamp: str          # ISO8601 UTC — caller-supplied (Date.now unavailable)
    deployed_tree_identity: str                 # git commit/tree of the running validation code
    shadow_ledger_identity: str                 # the shadow / separate paper-validation ledger id
    observation_sequence: int                   # derived from validated committed storage
    open_record_sha256: str
    sealed_payload_sha256: str
    account4_unchanged: bool                     # True iff the authoritative after-probe == before-probe
    account4_state_digest_before: str            # authoritative before-probe
    account4_state_digest_after: str             # authoritative after-probe (verified == before at publish)
    previous_commit_sha256: str                  # the chain link this observation extends
    previous_session_date: str                   # the session this observation strictly follows


def record_forward_session(
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
) -> tuple[OpenObservation, ObservationProvenance, int]:
    """Record ONE forward session after the window is open (sequence ≥ 2) and return
    `(open_record, provenance, session_count)` with the count derived from validated committed storage.

    Fails closed — writing nothing and leaving the count unchanged — if the integrity gate fails, if the
    window is not open, if committed storage is corrupt/tampered/non-contiguous or its chain is broken,
    if the session date does not strictly follow the last committed session, if Account 4 changes across
    the commit, if any staged digest or fsync fails, or if an observation directory already exists at the
    derived sequence.
    """
    preflight(ctx)                                          # every session, not just the first

    existing = committed_observations(store_dir)            # fully validated (chain + contiguity + dates)
    if not existing:
        raise ObservationCommitError(
            "the forward window is not open — no committed observation exists. Session 1 is the governed "
            "window-open transition (first_session.open_first_window_session); this path only extends an "
            "already-open record")
    sequence = len(existing) + 1

    sealed_sha, sealed_bytes = seal_performance(sealed_performance)
    open_obs = build_open_record(ctx, rebalances=rebalances, orders=orders, seeds=seeds,
                                 operational=operational, sealed_sha=sealed_sha,
                                 data_finality=data_finality,
                                 decision_evidence=decision_evidence)
    open_dict = asdict(open_obs)
    assert_open_record_has_no_sealed_content(open_dict, sealed_performance)
    open_bytes = canon(open_dict)

    previous_session_date = existing[-1].session_date
    written: dict[str, ObservationProvenance] = {}

    def _build_provenance(before_digest: str, previous_commit_sha256: str | None) -> dict:
        if previous_commit_sha256 is None:                  # unreachable for seq ≥ 2; fail closed anyway
            raise ObservationCommitError(
                f"observation {sequence} has no previous commit to chain to — refusing to break the chain")
        prov = ObservationProvenance(
            preflight_execution_timestamp=preflight_timestamp,
            deployed_tree_identity=deployed_tree_identity,
            shadow_ledger_identity=shadow_ledger_identity,
            observation_sequence=sequence,
            open_record_sha256=semantic_digest(open_dict),
            sealed_payload_sha256=sealed_sha,
            account4_unchanged=True,                        # enforced by the publish gate (after == before)
            account4_state_digest_before=before_digest,
            account4_state_digest_after=before_digest,      # verified == before authoritatively at publish
            previous_commit_sha256=previous_commit_sha256,
            previous_session_date=previous_session_date,
        )
        written["prov"] = prov
        return asdict(prov)

    result = commit_observation(
        store_dir=store_dir, sequence=sequence, session_date=ctx.session_date.isoformat(),
        open_bytes=open_bytes, sealed_bytes=sealed_bytes, build_provenance=_build_provenance,
        account4_probe=account4_probe, preflight_timestamp=preflight_timestamp,
        deployed_tree_identity=deployed_tree_identity, durability=durability)
    return open_obs, written["prov"], result.session_count
