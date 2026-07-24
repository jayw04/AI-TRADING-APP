"""Forward-validation chain-tip ANCHOR log — the independent witness of each committed tip (R5d).

The observation store (`observation_store`) is an append-only hash chain: every `commit.json` binds the
previous observation's `commit.json` digest, so rewriting observation 7 invalidates 8..N *relative to an
unchanged later tip*. But a local attacker who rewrites observation 7 can recompute the entire downstream
suffix — the chain is only tamper-evident against a root or tip recorded somewhere the rewrite cannot
reach (the #494 review requirement).

This module is that somewhere: a SEPARATE, append-only, independently hash-chained log
(`chain_anchors.jsonl` at the store ROOT, never under `observations/`) that records each committed chain
tip. Each anchor line binds two things:

  * the OBSERVATION chain — `commit_sha256` (the tip) and its own `previous_commit_sha256`; and
  * the ANCHOR chain — `previous_anchor_sha256`, the digest of the previous anchor LINE.

Tamper-evidence comes from CROSS-VERIFICATION, not from either chain alone. To rewrite observation 7 and
its suffix without detection, an attacker must ALSO rewrite anchor lines 7..N so both chains still agree —
and `verify_anchor_consistency` refuses any state where they do not: an anchor that witnesses a tip the
store does not have, a committed tip that no anchor witnesses, or a per-sequence digest that differs.
Once an anchor line is written it is the independent record; a missing or divergent anchor STOPS the run
for governed adjudication and is NEVER regenerated from the (possibly rewritten) observation — silently
re-deriving a missing anchor from the store would defeat the entire purpose.

Nothing here touches Account 4 or imports the order path.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from app.validation.forward_window import IntegrityStop
from app.validation.observation_store import (
    CommittedObservation,
    Durability,
    committed_observations,
    default_durability,
)

ANCHOR_LOG_FILENAME = "chain_anchors.jsonl"        # store ROOT — never under observations/


class AnchorError(IntegrityStop):
    """The chain-tip anchor log is invalid, or it diverges from the committed observation record. Fails
    closed: nothing is anchored, and a divergence is never repaired by regenerating the anchor."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AnchorRecord:
    """One anchor line: an independent witness of a committed chain tip. `anchor_sha256` is derived from
    the body (every field below) and stored alongside it; `previous_anchor_sha256` is the digest of the
    previous anchor line, so the anchor log is itself an append-only hash chain."""
    sequence: int
    session_date: str
    commit_sha256: str                     # the committed tip's commit.json digest (the observation chain)
    previous_commit_sha256: str | None     # the tip's own previous link (None for sequence 1)
    previous_anchor_sha256: str | None     # digest of the previous anchor LINE (None for sequence 1)
    deployed_tree_identity: str
    anchored_at: str                       # ISO8601 UTC — caller-supplied (Date.now unavailable)

    def body(self) -> dict:
        return asdict(self)

    def anchor_sha256(self) -> str:
        return _digest(self.body())


def _digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _line_digest(line: str) -> str:
    """The digest a following anchor binds as its `previous_anchor_sha256`: the exact JSON text of a
    line, without the trailing newline."""
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def _serialize(record: AnchorRecord) -> str:
    """The canonical one-line JSON for an anchor: the body plus its own `anchor_sha256` (no newline)."""
    return json.dumps({**record.body(), "anchor_sha256": record.anchor_sha256()}, sort_keys=True)


def read_anchors(store_dir: Path) -> list[AnchorRecord]:
    """The fully validated anchor log, in order. FAILS CLOSED (AnchorError code ANCHOR_LOG_INVALID) on an
    unreadable or malformed line, an `anchor_sha256` that does not verify, a broken anchor-chain link, a
    non-contiguous sequence, or a session date that does not strictly increase. An absent log is empty."""
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
        stored = obj.pop("anchor_sha256", None)
        try:
            record = AnchorRecord(**obj)
        except TypeError as exc:
            raise AnchorError(f"anchor line {i} has an unexpected field set: {exc}",
                              code="ANCHOR_LOG_INVALID") from exc
        if record.anchor_sha256() != stored:
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


def verify_anchor_consistency(
    store_dir: Path, committed: list[CommittedObservation] | None = None,
) -> list[AnchorRecord]:
    """Cross-verify the anchor log against the committed observation record and FAIL CLOSED on any
    divergence. Returns the validated anchors on success.

    The two independently-stored chains must witness exactly the same tips:

      ANCHOR_AHEAD_OF_RECORD     more anchors than committed observations — an anchor witnesses a tip the
                                 store does not have (an observation was removed, or an anchor forged).
      ANCHOR_BEHIND_RECORD       a committed tip that no anchor witnesses (a crash between the commit and
                                 the anchor append leaves this state — recovered by governed adjudication,
                                 NEVER by regenerating the anchor from the store).
      ANCHOR_DIVERGES_FROM_RECORD  a per-sequence commit digest, previous link or session date differs —
                                 the observation chain was rewritten but the independent anchor was not.
    """
    anchors = read_anchors(store_dir)
    obs = committed if committed is not None else committed_observations(store_dir)

    if len(anchors) > len(obs):
        raise AnchorError(
            f"the anchor log records {len(anchors)} tip(s) but committed storage holds {len(obs)} "
            f"observation(s) — an anchor witnesses a tip that does not exist",
            code="ANCHOR_AHEAD_OF_RECORD")

    # every anchor must match the observation at its sequence (the tamper cross-check)
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
    return anchors


def append_anchor(
    store_dir: Path, *, deployed_tree_identity: str, anchored_at: str,
    durability: Durability | None = None,
) -> AnchorRecord:
    """Anchor the CURRENT committed chain tip in the independent log, and return the anchor written.

    Reads the fully validated committed record and the fully validated anchor log, requires the anchors to
    be a consistent prefix of the observations, then appends ONE anchor for the latest committed tip. If
    the tip is already anchored (a safe re-run after a successful commit) this is a verified no-op. Fails
    closed if the anchor log is ahead of, or divergent from, the observation record; never regenerates a
    missing interior anchor.
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
    # the existing anchors must already witness the observations they cover (no interior divergence)
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
        # the digest of the previous anchor LINE, taken from the file exactly as stored
        existing_lines = [ln for ln in path.read_text(encoding="utf-8").split("\n") if ln != ""]
        prev_line_digest = _line_digest(existing_lines[-1])

    record = AnchorRecord(
        sequence=tip.sequence, session_date=tip.session_date, commit_sha256=tip.commit_sha256,
        previous_commit_sha256=tip.previous_commit_sha256, previous_anchor_sha256=prev_line_digest,
        deployed_tree_identity=deployed_tree_identity, anchored_at=anchored_at)
    line = _serialize(record)

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
