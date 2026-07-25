"""Forward-validation chain-tip ANCHOR log — the independent witness of each committed tip (R5d).

The observation store (`observation_store`) is an append-only hash chain: every `commit.json` binds the
previous observation's `commit.json` digest, so rewriting observation 7 invalidates 8..N *relative to an
unchanged later tip*. But a local attacker who rewrites observation 7 can recompute the entire downstream
suffix — the chain is only tamper-evident against a root or tip recorded somewhere the rewrite cannot
reach (the #494 review requirement).

This module is the local half of that record, and it is made INDEPENDENT of a local attacker by binding
each tip to a separate trust boundary (`chain_witness`):

  * every anchor line is SIGNED by a key the observation-store writer does not hold — an attacker with
    local write access can alter the tip bytes but cannot forge the signature for the altered tip
    (rewrite protection); and
  * every signed tip is also recorded in an EXTERNAL append-only sink with separately governed write
    authority — an attacker who truncates the local log to hide the latest sessions cannot remove the
    externally recorded tip (truncation/rollback protection).

The local anchor log (`chain_anchors.jsonl`, at the store ROOT, never under `observations/`) additionally
carries its OWN hash chain (`previous_anchor_sha256`) so its internal integrity is self-checking. But
tamper-evidence against the requirement's attacker comes from the signature + external sink, verified by
`verify_anchor_consistency`, which needs the public verifying key and the sink to pass.

Nothing here touches Account 4 or imports the order path.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from app.validation.chain_witness import (
    AnchorSigner,
    AnchorVerifier,
    ExternalAnchorSink,
    SignedReceipt,
    WitnessedTip,
    WitnessError,
)
from app.validation.forward_window import IntegrityStop
from app.validation.observation_store import (
    CommittedObservation,
    Durability,
    committed_observations,
    default_durability,
)

ANCHOR_LOG_FILENAME = "chain_anchors.jsonl"        # store ROOT — never under observations/

# the anchor-line fields that make up the SIGNED/DIGESTED core (the witness fields are added around it)
_CORE_FIELDS = ("sequence", "session_date", "commit_sha256", "previous_commit_sha256",
                "previous_anchor_sha256", "deployed_tree_identity", "anchored_at")
_WITNESS_FIELDS = ("witness_signature", "witness_public_key_id", "witness_identity")


class AnchorError(IntegrityStop):
    """The chain-tip anchor log is invalid, or it diverges from the committed observation record or the
    external witness. Fails closed: nothing is anchored, and a divergence is never repaired by
    regenerating the anchor."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AnchorRecord:
    """One anchor line: an independent witness of a committed chain tip. `anchor_sha256` is derived from
    the CORE fields; `previous_anchor_sha256` is the digest of the previous anchor line (the log's own
    chain); and the witness fields carry the separate-trust-boundary signature over the tip."""
    sequence: int
    session_date: str
    commit_sha256: str                     # the committed tip's commit.json digest (the observation chain)
    previous_commit_sha256: str | None     # the tip's own previous link (None for sequence 1)
    previous_anchor_sha256: str | None     # digest of the previous anchor LINE (None for sequence 1)
    deployed_tree_identity: str
    anchored_at: str                       # ISO8601 UTC — caller-supplied (Date.now unavailable)
    witness_signature: str                 # base64 Ed25519 signature over the witnessed tip
    witness_public_key_id: str             # fingerprint of the signing key
    witness_identity: str                  # human identity of the external witness

    def core_body(self) -> dict:
        return {k: getattr(self, k) for k in _CORE_FIELDS}

    def anchor_sha256(self) -> str:
        return _digest(self.core_body())

    def witnessed_tip(self) -> WitnessedTip:
        return WitnessedTip(sequence=self.sequence, session_date=self.session_date,
                            commit_sha256=self.commit_sha256, anchor_sha256=self.anchor_sha256())

    def receipt(self) -> SignedReceipt:
        return SignedReceipt(signature_b64=self.witness_signature,
                             public_key_id=self.witness_public_key_id,
                             witness_identity=self.witness_identity)


def _digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _line_digest(line: str) -> str:
    """The digest a following anchor binds as its `previous_anchor_sha256`: the exact JSON text of a
    line, without the trailing newline."""
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def _serialize(record: AnchorRecord) -> str:
    """The canonical one-line JSON for an anchor: the core body, its `anchor_sha256`, and the witness
    fields (no newline)."""
    payload = {**record.core_body(), "anchor_sha256": record.anchor_sha256(),
               "witness_signature": record.witness_signature,
               "witness_public_key_id": record.witness_public_key_id,
               "witness_identity": record.witness_identity}
    return json.dumps(payload, sort_keys=True)


def read_anchors(store_dir: Path) -> list[AnchorRecord]:
    """The fully validated anchor log, in order — structural integrity only (self-digest, own chain,
    contiguity, dates, witness fields present). Signature and external-sink verification is done by
    `verify_anchor_consistency`, which holds the trusted keys. FAILS CLOSED (AnchorError code
    ANCHOR_LOG_INVALID). An absent log is empty."""
    path = store_dir / ANCHOR_LOG_FILENAME
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AnchorError(f"the anchor log is unreadable: {exc}", code="ANCHOR_LOG_INVALID") from exc

    lines = [ln for ln in raw.split("\n") if ln != ""]
    records: list[AnchorRecord] = []
    prev_line_digest: str | None = None
    for i, line in enumerate(lines, start=1):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AnchorError(f"anchor line {i} is not valid JSON: {exc}",
                              code="ANCHOR_LOG_INVALID") from exc
        stored_anchor = obj.pop("anchor_sha256", None)
        missing = [f for f in (*_CORE_FIELDS, *_WITNESS_FIELDS) if f not in obj]
        if missing:
            raise AnchorError(f"anchor line {i} is missing field(s) {missing}",
                              code="ANCHOR_LOG_INVALID")
        try:
            record = AnchorRecord(**obj)
        except TypeError as exc:
            raise AnchorError(f"anchor line {i} has an unexpected field set: {exc}",
                              code="ANCHOR_LOG_INVALID") from exc
        if record.anchor_sha256() != stored_anchor:
            raise AnchorError(f"anchor line {i}: anchor_sha256 does not verify — the line was altered",
                              code="ANCHOR_LOG_INVALID")
        if record.sequence != i:
            raise AnchorError(
                f"anchor line {i}: sequence {record.sequence} is not contiguous from 1",
                code="ANCHOR_LOG_INVALID")
        if record.previous_anchor_sha256 != prev_line_digest:
            raise AnchorError(
                f"anchor line {i}: previous_anchor_sha256 {record.previous_anchor_sha256!r} does not "
                f"match the prior line ({prev_line_digest!r}) — the anchor chain is broken",
                code="ANCHOR_LOG_INVALID")
        if records and record.session_date <= records[-1].session_date:
            raise AnchorError(
                f"anchor line {i}: session_date {record.session_date} does not strictly follow "
                f"{records[-1].session_date}", code="ANCHOR_LOG_INVALID")
        records.append(record)
        prev_line_digest = _line_digest(line)
    return records


def _assert_matches_observations(anchors: list[AnchorRecord],
                                 obs: list[CommittedObservation]) -> None:
    """The local anchors and the committed observations must witness exactly the same tips."""
    if len(anchors) > len(obs):
        raise AnchorError(
            f"the anchor log records {len(anchors)} tip(s) but committed storage holds {len(obs)} "
            f"observation(s) — an anchor witnesses a tip that does not exist",
            code="ANCHOR_AHEAD_OF_RECORD")
    for anchor, observation in zip(anchors, obs, strict=False):
        if (anchor.commit_sha256 != observation.commit_sha256
                or anchor.previous_commit_sha256 != observation.previous_commit_sha256
                or anchor.session_date != observation.session_date):
            raise AnchorError(
                f"anchor {anchor.sequence} witnesses commit {anchor.commit_sha256[:16]}… / session "
                f"{anchor.session_date} but committed observation {observation.sequence} is "
                f"{observation.commit_sha256[:16]}… / {observation.session_date} — the observation chain "
                f"was rewritten but the independent anchor was not",
                code="ANCHOR_DIVERGES_FROM_RECORD")
    if len(anchors) < len(obs):
        missing = [o.sequence for o in obs[len(anchors):]]
        raise AnchorError(
            f"committed observation(s) {missing} have no independent anchor — the chain tip is "
            f"unwitnessed; recovery is a governed adjudication, the anchor is never regenerated from the "
            f"observation it is meant to witness",
            code="ANCHOR_BEHIND_RECORD")


def _verify_signature(verifier: AnchorVerifier, tip: WitnessedTip, receipt: SignedReceipt, *,
                      what: str) -> None:
    """Verify one signature, normalizing EVERY failure into a governed AnchorError — a WitnessError keeps
    its specific code (ANCHOR_SIGNATURE_INVALID); any other implementation exception (a broken verifier,
    an SDK error) becomes INDEPENDENT_WITNESS_UNAVAILABLE. No raw exception escapes the witness boundary."""
    try:
        verifier.verify(tip, receipt)
    except WitnessError as exc:
        raise AnchorError(f"{what}: {exc}", code=exc.code) from exc
    except Exception as exc:      # noqa: BLE001 - any verifier/SDK failure must become a governed stop
        raise AnchorError(f"{what}: the signature could not be verified: {exc}",
                          code="INDEPENDENT_WITNESS_UNAVAILABLE") from exc


def _read_external(external_sink: ExternalAnchorSink) -> list[tuple[WitnessedTip, SignedReceipt]]:
    """Read the external witness, normalizing EVERY failure into a governed AnchorError. A corrupt sink
    record keeps its WitnessError code; a connector/transport/credentials exception from a real sink
    (S3/Object-Lock client, network) becomes INDEPENDENT_WITNESS_UNAVAILABLE rather than escaping."""
    try:
        return external_sink.read_all()
    except WitnessError as exc:
        raise AnchorError(str(exc), code=exc.code) from exc
    except Exception as exc:      # noqa: BLE001 - any sink/SDK failure must become a governed stop
        raise AnchorError(f"the external witness could not be read: {exc}",
                          code="INDEPENDENT_WITNESS_UNAVAILABLE") from exc


def _assert_witnessed(anchors: list[AnchorRecord], verifier: AnchorVerifier,
                      external_sink: ExternalAnchorSink) -> None:
    """Every local anchor's signature must verify, and the EXTERNAL sink must witness exactly the same
    tips — the cross-boundary checks that make the anchor independent of a local attacker.

      ANCHOR_SIGNATURE_INVALID   a tip was altered after it was signed (or signed by an untrusted key).
      EXTERNAL_WITNESS_AHEAD     the external sink holds tip(s) the local log does not — the local log
                                 (and its observations) were TRUNCATED to hide the latest sessions.
      EXTERNAL_WITNESS_BEHIND    a local tip the external sink never recorded — an unwitnessed tip.
      EXTERNAL_WITNESS_DIVERGES  the sink and the local log disagree about a tip at the same sequence.
    """
    for anchor in anchors:
        _verify_signature(verifier, anchor.witnessed_tip(), anchor.receipt(),   # rewrite protection
                          what=f"local anchor {anchor.sequence}")

    external = _read_external(external_sink)
    if len(external) > len(anchors):
        extra = [tip.sequence for tip, _ in external[len(anchors):]]
        raise AnchorError(
            f"the external witness holds tip(s) {extra} the local anchor log does not — the local record "
            f"was truncated to hide committed session(s)", code="EXTERNAL_WITNESS_AHEAD")
    for (etip, ereceipt), anchor in zip(external, anchors, strict=False):
        if etip.commit_sha256 != anchor.commit_sha256 or etip.anchor_sha256 != anchor.anchor_sha256():
            raise AnchorError(
                f"the external witness for sequence {etip.sequence} records a different tip than the "
                f"local anchor log", code="EXTERNAL_WITNESS_DIVERGES")
        _verify_signature(verifier, etip, ereceipt, what=f"external witness {etip.sequence}")
    if len(external) < len(anchors):
        missing = [a.sequence for a in anchors[len(external):]]
        raise AnchorError(
            f"local anchor(s) {missing} were never recorded in the external witness — the tip is not "
            f"independently witnessed", code="EXTERNAL_WITNESS_BEHIND")


def verify_anchor_consistency(
    store_dir: Path, committed: list[CommittedObservation] | None = None, *,
    verifier: AnchorVerifier, external_sink: ExternalAnchorSink,
) -> list[AnchorRecord]:
    """Cross-verify the anchor log against the committed observation record AND the independent witness,
    and FAIL CLOSED on any divergence. Returns the validated anchors on success.

    Three chains must agree: the committed observations, the local anchor log, and the external witness.
    The local↔observation checks catch a rewrite that touched both local stores; the signature and
    external-sink checks catch a rewrite or truncation confined to the local write-authority domain."""
    anchors = read_anchors(store_dir)
    obs = committed if committed is not None else committed_observations(store_dir)
    _assert_matches_observations(anchors, obs)
    _assert_witnessed(anchors, verifier, external_sink)
    return anchors


def append_anchor(
    store_dir: Path, *, signer: AnchorSigner, external_sink: ExternalAnchorSink,
    deployed_tree_identity: str, anchored_at: str, durability: Durability | None = None,
) -> AnchorRecord:
    """Anchor the CURRENT committed chain tip: sign it across the trust boundary, record it in the
    external witness, and append it to the local log. Returns the anchor written.

    Requires the existing anchors to be a consistent prefix of the committed observations; NEVER
    regenerates a missing interior anchor. If the tip is already anchored (a safe re-run) this is a
    verified no-op. The external witness is written before the local line, so a crash between them leaves
    the local log behind the sink, which the next run diagnoses (EXTERNAL_WITNESS_AHEAD) and stops.
    """
    dur = durability or default_durability()
    obs = committed_observations(store_dir)
    if not obs:
        raise AnchorError("there is no committed observation to anchor", code="ANCHOR_BEHIND_RECORD")

    anchors = read_anchors(store_dir)
    if len(anchors) > len(obs):
        raise AnchorError(
            f"the anchor log is ahead of the record ({len(anchors)} > {len(obs)})",
            code="ANCHOR_AHEAD_OF_RECORD")
    for anchor, observation in zip(anchors, obs, strict=False):
        if (anchor.commit_sha256 != observation.commit_sha256
                or anchor.previous_commit_sha256 != observation.previous_commit_sha256
                or anchor.session_date != observation.session_date):
            raise AnchorError(
                f"existing anchor {anchor.sequence} diverges from committed observation "
                f"{observation.sequence}; refusing to extend a divergent anchor chain",
                code="ANCHOR_DIVERGES_FROM_RECORD")

    if len(anchors) == len(obs):
        return anchors[-1]                                  # the tip is already anchored — verified no-op
    if len(anchors) != len(obs) - 1:
        raise AnchorError(
            f"the anchor log is {len(obs) - 1 - len(anchors)} tip(s) behind the record; only the single "
            f"latest tip may be anchored per commit — an interior gap needs governed adjudication",
            code="ANCHOR_BEHIND_RECORD")

    tip = obs[-1]
    path = store_dir / ANCHOR_LOG_FILENAME
    prev_line_digest: str | None = None
    if anchors:
        existing_lines = [ln for ln in path.read_text(encoding="utf-8").split("\n") if ln != ""]
        prev_line_digest = _line_digest(existing_lines[-1])

    core = {"sequence": tip.sequence, "session_date": tip.session_date,
            "commit_sha256": tip.commit_sha256, "previous_commit_sha256": tip.previous_commit_sha256,
            "previous_anchor_sha256": prev_line_digest, "deployed_tree_identity": deployed_tree_identity,
            "anchored_at": anchored_at}
    anchor_digest = _digest(core)
    witnessed = WitnessedTip(sequence=tip.sequence, session_date=tip.session_date,
                             commit_sha256=tip.commit_sha256, anchor_sha256=anchor_digest)
    receipt = signer.attest(witnessed)                      # crosses the trust boundary (separate key)

    record = AnchorRecord(
        sequence=tip.sequence, session_date=tip.session_date, commit_sha256=tip.commit_sha256,
        previous_commit_sha256=tip.previous_commit_sha256, previous_anchor_sha256=prev_line_digest,
        deployed_tree_identity=deployed_tree_identity, anchored_at=anchored_at,
        witness_signature=receipt.signature_b64, witness_public_key_id=receipt.public_key_id,
        witness_identity=receipt.witness_identity)
    line = _serialize(record)

    # the EXTERNAL immutable witness first, then the local log — a crash between them leaves the local log
    # behind the sink, which the next run detects (EXTERNAL_WITNESS_AHEAD) rather than silently accepting.
    external_sink.publish(witnessed, receipt)

    created = not path.exists()
    try:
        store_dir.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except OSError as exc:
        raise AnchorError(f"could not append the chain-tip anchor for sequence {tip.sequence}: {exc}",
                          code="ANCHOR_WRITE_FAILED") from exc
    dur.fsync_file(path)
    if created:
        dur.fsync_dir(store_dir)
    return record
