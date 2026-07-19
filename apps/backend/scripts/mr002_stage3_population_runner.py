"""MR-002 Stage-3 — clean successor population runner + orchestration (review cycle 3).

Cycle-3 review (`docs/review/comments.md`) findings addressed here:

  * the REAL entry point (`run_clean_successor`) now constructs the production corpus source, calls
    `orchestrate()` with `resolve_instance`, and emits the clean-run manifest — no placeholder. The
    corpus-regeneration code EXISTS and is reviewable now; EXECUTING it stays gated on the verified
    authorization artifact (findings 1, 29);
  * `orchestrate()` INDEPENDENTLY derives the corpus hash from the actual row bytes (the registered
    scheme) — it never trusts the hash string the corpus source returns (finding 2);
  * the authorization artifact is semantically validated (record type, version, decision,
    execution_authorized, countersigner, repository) and CROSS-VALIDATED against the expected-pins
    identities (findings 3, 4). The operator-supplied artifact hash remains an acknowledged gap until
    the signed launch attestation exists (finding 5);
  * the runner canonicalizes each row ONCE and uses that immutable record for manifest comparison,
    resolution, and evidence (finding 9);
  * checkpoint I/O failures are preserved via an emergency sidecar and reported as
    `evidence_persisted=False` — "the terminal always is" is no longer claimed (finding 10); iterator
    construction and drain are guarded (finding 11);
  * the checkpoint is STRICT: any malformed non-final line, unknown event kind, duplicate terminal,
    or record-after-terminal is corruption and fails the checkpoint (findings 12, 13);
  * `aggregate_verdict` re-verifies every record's `record_sha256`, every input content hash against
    the row manifest, the single-final-terminal invariant, and the terminal's own count (finding 12);
  * the row manifest is schema-validated (dict entries, exact keys, 64-hex hashes) (finding 14);
  * the run manifest binds the full execution provenance AND the final checkpoint bytes hash
    (findings 15, 16); `orchestrate()` fails closed on any orchestration exception (finding 17);
  * output-root controls are executable: fresh empty non-symlink out_dir, checkpoint inside it
    (finding 18).

    ╔══════════════════════════════════════════════════════════════════════════════════════════╗
    ║  EXECUTION IS NOT AUTHORIZED until the SEPARATE execution countersignature (adjudication    ║
    ║  §10). run_clean_successor verifies + cross-validates the countersigned authorization        ║
    ║  artifact before the corpus source is even constructed.                                      ║
    ╚══════════════════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import traceback
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import numpy as np

from app.research.mr002.stage3_cascade import (
    CERTIFICATE_NONQUALIFICATION,
    EVIDENCE_SCHEMA_VERSION,
    FALLBACK_QUALIFIED,
    INVALID_RUN,
    NUMERICAL_STATUS_NONQUALIFICATION,
    PRIMARY_QUALIFIED,
    QUALIFIED,
    REQUIRED_CERT_FIELDS,
    UNRESOLVED_NUMERICAL_FAILURE,
    Outcome,
    canonicalize,
    numerical_evidence,
    rec_content_hash,
    validate_model_inputs,
    validate_outcome,
)

QUALIFIED_DISPOSITIONS = frozenset({PRIMARY_QUALIFIED, FALLBACK_QUALIFIED})
STOP_DISPOSITIONS = frozenset({INVALID_RUN, UNRESOLVED_NUMERICAL_FAILURE})
TERMINAL_COMPLETE = "COMPLETE"
TERMINAL_FAILED = "FAILED"
ALLOWED_WINDOWS = frozenset({"dev"})
# frozen governance identifiers (cycle-4 findings 5, 6, 7, 8, 17)
ROW_MANIFEST_PROTOCOL = "MR002_STAGE3_ROW_IDENTITY_V1"
AUTHORIZATION_VERSION = "1.0"
AUTHORIZED_COUNTERSIGNER = "Jay Wang (owner)"
PINS_RECORD_TYPE = "MR002_STAGE3_EXPECTED_PINS"
PINS_VERSION = "1.0"
SUPPORTED_EXECUTION_PACKAGE_VERSION = "1.9"
EXPECTED_CORPUS_INSTANCES = 3895   # the registered characterization-instance count
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class WindowAccessError(RuntimeError):
    """Raised if a caller tries to resolve anything but the development window."""


class CheckpointRefused(RuntimeError):
    """Raised when a preexisting/inconsistent checkpoint blocks a fresh governed run."""


class Stage3RunRefused(RuntimeError):
    """A run-level refusal (authorization/pins/manifest/preflight)."""


# ══════════════════════════════════════════════════════════════════════════════════════════════
# independent corpus hashing (finding 2) — the registered scheme, computed BY THE RUNNER
# ══════════════════════════════════════════════════════════════════════════════════════════════
def instance_hash(rec) -> str:
    """The registered per-instance hash: sha256 over each array's shape string + float64 bytes, in
    canonical component order. Replicates `mr002_solver_intersection._hash_instance` exactly (kept
    dependency-free so the runner never imports the solver stack to hash)."""
    h = hashlib.sha256()
    for arr in rec:
        a = np.ascontiguousarray(np.asarray(arr, dtype=np.float64))
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def derive_corpus_hash(recs: list) -> str:
    """The registered corpus hash: sha256 of the '|'-joined ordered per-instance hashes. Derived from
    the ACTUAL row bytes — never trusted from the corpus source (finding 2)."""
    return hashlib.sha256("|".join(instance_hash(r) for r in recs).encode()).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ROW-IDENTITY MANIFEST (findings 11, 12, 14) — the canonical ordered population contract
# ══════════════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class RowIdentityManifest:
    corpus_hash: str
    rows: tuple                       # ordered tuple of {"row_id":..., "content_hash":...}

    @property
    def n_expected(self) -> int:
        return len(self.rows)

    def defect(self) -> str | None:
        """Full schema validation (finding 14): dict entries with EXACTLY {row_id, content_hash};
        hashable int/str IDs; 64-lowercase-hex hashes; nonempty; unique IDs."""
        if not isinstance(self.corpus_hash, str) or not _HEX64.match(self.corpus_hash):
            return "CORPUS_HASH_NOT_64HEX"
        if not self.rows:
            return "EMPTY_ROW_MANIFEST"
        ids = []
        for i, r in enumerate(self.rows):
            if not isinstance(r, dict) or set(r.keys()) != {"row_id", "content_hash"}:
                return f"ROW_ENTRY_MALFORMED:{i}"
            rid = r["row_id"]
            if not isinstance(rid, (int, str)):
                return f"ROW_ID_BAD_TYPE:{i}:{type(rid).__name__}"
            ch = r["content_hash"]
            if not isinstance(ch, str) or not _HEX64.match(ch):
                return f"CONTENT_HASH_NOT_64HEX:{i}"
            ids.append(rid)
        if len(set(ids)) != len(ids):
            return "DUPLICATE_ROW_IDS"
        return None

    def expected_at(self, index: int) -> dict:
        return self.rows[index]

    def canonical_hash(self) -> str:
        return hashlib.sha256(json.dumps(
            {"corpus_hash": self.corpus_hash, "rows": list(self.rows)},
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_row_manifest(path: str) -> RowIdentityManifest:
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    return RowIdentityManifest(corpus_hash=d["corpus_hash"], rows=tuple(d["rows"]))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# STRICT append-only checkpoint (findings 10, 12, 13)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class CheckpointSink:
    def __init__(self, path: str):
        self.path = path
        self._fh = open(path, "a", encoding="utf-8")  # noqa: SIM115 — long-lived append handle

    def _emit(self, obj: dict) -> None:
        self._fh.write(json.dumps(obj, separators=(",", ":"), default=str) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def write_record(self, rec: dict) -> None:
        self._emit({"kind": "record", **rec})

    def mark_failed(self, reason: str, row_id: object, extra: dict | None = None) -> None:
        self._emit({"kind": "terminal", "status": TERMINAL_FAILED, "reason": reason,
                    "row_id": row_id, **(extra or {})})

    def mark_complete(self, n_records: int) -> None:
        self._emit({"kind": "terminal", "status": TERMINAL_COMPLETE, "n_records": n_records})

    def close(self) -> None:
        self._fh.close()


def read_checkpoint(path: str) -> dict:
    """STRICT read (finding 13). Returns {records, terminal, resumable, trailing_partial,
    corruption}. Rules: every nonempty line must parse as a dict whose kind is `record` or
    `terminal`; a malformed FINAL line is a trailing partial (interrupted write); a malformed or
    unknown line anywhere else is CORRUPTION; a second terminal, or any event after the terminal,
    is corruption."""
    records, terminal, trailing_partial = [], None, False
    corruption: list[str] = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh.readlines()]
        nonempty = [(i, ln) for i, ln in enumerate(lines) if ln]
        for pos, (i, line) in enumerate(nonempty):
            is_last = pos == len(nonempty) - 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                if is_last:
                    trailing_partial = True
                else:
                    corruption.append(f"MALFORMED_LINE:{i}")
                continue
            if not isinstance(obj, dict) or obj.get("kind") not in ("record", "terminal"):
                corruption.append(f"UNKNOWN_EVENT:{i}")
                continue
            if terminal is not None:
                corruption.append(f"EVENT_AFTER_TERMINAL:{i}")
                continue
            if obj["kind"] == "terminal":
                terminal = obj
            else:
                records.append(obj)
    return {"records": records, "terminal": terminal, "trailing_partial": trailing_partial,
            "corruption": corruption,
            "resumable": is_resumable(terminal) and not corruption}


def is_resumable(terminal: dict | None) -> bool:
    return not (terminal is not None and terminal.get("status") == TERMINAL_FAILED)


def precheck_checkpoint(path: str) -> str | None:
    """Refuse a fresh governed run against ANY preexisting/inconsistent checkpoint (findings 9, 10)."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None if not os.path.exists(path) else "CHECKPOINT_EXISTS_EMPTY"
    state = read_checkpoint(path)
    if state["corruption"]:
        return f"CHECKPOINT_CORRUPT:{state['corruption'][0]}"
    if state["trailing_partial"]:
        return "CHECKPOINT_TRAILING_PARTIAL"
    if state["terminal"] is not None:
        return f"CHECKPOINT_TERMINAL_{state['terminal'].get('status')}"
    if state["records"]:
        return "CHECKPOINT_NONEMPTY_NO_TERMINAL"
    return "CHECKPOINT_UNRECOGNIZED_CONTENT"


def _emergency_preserve(checkpoint_path: str, payload: dict) -> bool:
    """Governed emergency sidecar (cycle-5 finding 10): atomic staged write, sequence-numbered so a
    second failure NEVER overwrites the first, self-describing, with post-write byte verification."""
    try:
        seq = 1
        while os.path.exists(f"{checkpoint_path}.emergency.{seq}.json"):
            seq += 1
        path = f"{checkpoint_path}.emergency.{seq}.json"
        doc = {"record_type": "MR002_STAGE3_EMERGENCY_SIDECAR", "version": "1.0",
               "failure_sequence": seq, "checkpoint_path": checkpoint_path, **payload}
        if os.path.exists(checkpoint_path):
            try:
                doc["checkpoint_sha256"] = _sha256_file(checkpoint_path)
            except OSError:
                doc["checkpoint_sha256"] = None
        expected = _atomic_write_json(path, doc)
        return _sha256_file(path) == expected
    except Exception:  # noqa: BLE001 — the caller records evidence_persisted=False
        return False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# the population loop
# ══════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class RunResult:
    refused: bool = False
    refusal_reason: str = ""
    stopped: bool = False
    stop_row: object = None
    stop_reason: str = ""
    passed: bool = False
    resumable: bool = True
    evidence_persisted: bool = True      # False if terminal/record writes failed (finding 10)
    n_expected: int = 0
    n_processed: int = 0
    n_qualified: int = 0
    n_stopped: int = 0
    checkpoint: str = ""
    windows: tuple = ()

    def summary(self) -> dict:
        return dict(self.__dict__)


def _failure_fingerprint(exc: BaseException) -> dict:
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return {"exception_class": type(exc).__name__,
            "message_sha256": hashlib.sha256(str(exc).encode()).hexdigest(),
            "traceback_sha256": hashlib.sha256(tb.encode()).hexdigest()}


def run_population(
    rows: Iterable[tuple],
    resolve_fn: Callable[[tuple], Outcome],
    checkpoint_path: str,
    *,
    preflight_passed: bool,
    row_manifest: RowIdentityManifest,
    windows: Iterable[str] = ("dev",),
) -> RunResult:
    """Resolve a population of (row_id, rec) pairs through `resolve_fn`, enforcing all stop gates."""
    win = tuple(windows)
    res = RunResult(checkpoint=checkpoint_path, windows=win, n_expected=row_manifest.n_expected)

    if not preflight_passed:
        return _refuse(res, "PREFLIGHT_NOT_PASSED")
    if set(win) - ALLOWED_WINDOWS:
        _refuse(res, f"WINDOW_NOT_ALLOWED:{sorted(set(win) - ALLOWED_WINDOWS)}")
        raise WindowAccessError(res.refusal_reason)
    md = row_manifest.defect()
    if md is not None:
        return _refuse(res, f"ROW_MANIFEST_{md}")
    pc = precheck_checkpoint(checkpoint_path)
    if pc is not None:
        _refuse(res, pc)
        raise CheckpointRefused(pc)

    try:
        sink = CheckpointSink(checkpoint_path)
    except Exception as exc:  # noqa: BLE001 — finding 10 + cycle-5 f11: open itself can fail
        res.evidence_persisted = _emergency_preserve(
            checkpoint_path, {"status": TERMINAL_FAILED, "reason": "CHECKPOINT_OPEN_FAILED",
                              **_failure_fingerprint(exc)})
        return _refuse(res, "CHECKPOINT_OPEN_FAILED")

    try:
        try:
            row_iter = iter(rows)                            # finding 11: creation may raise
        except Exception as exc:  # noqa: BLE001
            return _stop(res, sink, "ROW_ITERATOR_ERROR", None, _failure_fingerprint(exc))

        for index in range(row_manifest.n_expected):
            try:
                row_id, rec = next(row_iter)
            except StopIteration:
                return _stop(res, sink, "POPULATION_SHORTER_THAN_MANIFEST", index)
            except Exception as exc:  # noqa: BLE001
                return _stop(res, sink, "ROW_ITERATOR_ERROR", index, _failure_fingerprint(exc))

            expected = row_manifest.expected_at(index)
            if row_id != expected["row_id"]:
                return _stop(res, sink, "ROW_ID_ORDER_MISMATCH", row_id,
                             {"expected_row_id": expected["row_id"], "index": index})

            # Canonicalize ONCE (finding 9): this immutable record is used for the manifest
            # comparison, the resolution, AND the evidence — no time-of-check/time-of-use gap.
            try:
                canon = canonicalize(rec)
            except Exception as exc:  # noqa: BLE001
                return _stop(res, sink, "ROW_CANONICALIZATION_ERROR", row_id,
                             _failure_fingerprint(exc))
            chash = rec_content_hash(canon)
            if chash != expected["content_hash"]:
                return _stop(res, sink, "ROW_CONTENT_HASH_MISMATCH", row_id,
                             {"expected": expected["content_hash"], "observed": chash})

            try:
                outcome = resolve_fn(canon)
                defect = validate_outcome(outcome, canon)          # findings 7, 30
                if defect is not None:
                    return _stop(res, sink, f"MALFORMED_OUTCOME:{defect}", row_id)
                record = {"row_id": row_id, "index": index,
                          "class": "qualified" if outcome.disposition in QUALIFIED_DISPOSITIONS
                          else "stop",
                          **numerical_evidence(outcome, canon)}    # findings 6, 8
                record["record_sha256"] = _record_hash(record)
            except Exception as exc:  # noqa: BLE001 — resolver/evidence fault (finding 8)
                return _stop(res, sink, "RESOLVER_ERROR", row_id, _failure_fingerprint(exc))
            try:
                sink.write_record(record)
                res.n_processed += 1
            except Exception as exc:  # noqa: BLE001 — cycle-4 finding 12: a WRITE fault may leave a
                # partial line, so the checkpoint can no longer be trusted as governed evidence even
                # if a terminal later appends successfully. Sidecar ALWAYS written.
                res.evidence_persisted = False
                _emergency_preserve(checkpoint_path, {
                    "status": TERMINAL_FAILED, "reason": "RECORD_WRITE_ERROR", "row_id": row_id,
                    **_failure_fingerprint(exc)})
                return _stop(res, sink, "RECORD_WRITE_ERROR", row_id, _failure_fingerprint(exc))

            if record["class"] == "stop":
                return _stop(res, sink, outcome.disposition, row_id)
            res.n_qualified += 1

        try:                                                 # finding 11: drain is guarded too
            next(row_iter)
        except StopIteration:
            pass
        except Exception as exc:  # noqa: BLE001
            return _stop(res, sink, "ROW_ITERATOR_ERROR", res.n_processed,
                         _failure_fingerprint(exc))
        else:
            return _stop(res, sink, "POPULATION_LONGER_THAN_MANIFEST", res.n_processed)
        try:
            sink.mark_complete(res.n_processed)
        except Exception as exc:  # noqa: BLE001 — cycle-5 finding 11                               # finding 10
            res.evidence_persisted = _emergency_preserve(
                checkpoint_path, {"status": TERMINAL_COMPLETE, "n_records": res.n_processed,
                                  "note": "terminal write failed", **_failure_fingerprint(exc)})
            res.passed = False
            res.resumable = False
            res.stopped = True
            res.stop_reason = "TERMINAL_WRITE_FAILED"
            return res
    finally:
        try:
            sink.close()
        except Exception as exc:  # noqa: BLE001 — cycle-5 finding 11
            # cycle-4 finding 11: a close failure means the evidence stream is not known durable —
            # the run cannot PASS even if the bytes happen to parse and reconcile.
            res.evidence_persisted = False
            res.stopped = True
            res.stop_reason = res.stop_reason or "CHECKPOINT_CLOSE_FAILED"
            _emergency_preserve(checkpoint_path, {
                "status": TERMINAL_FAILED, "reason": "CHECKPOINT_CLOSE_FAILED",
                **_failure_fingerprint(exc)})

    state = read_checkpoint(checkpoint_path)
    # a governed PASS additionally requires a fully persisted evidence stream (cycle-4 finding 11)
    vdefect = aggregate_verdict_defect(state, row_manifest)
    res.passed = (vdefect is None and res.evidence_persisted and not res.stopped)
    # delta v1.8: a verdict failure must surface a deterministic nonempty reason — run 4 emitted
    # {"disposition": "STOP", "detail": ""} and the manifest carried no stop_reason
    if vdefect is not None and not res.stopped and not res.refused:
        res.stop_reason = vdefect
    res.resumable = is_resumable(state["terminal"]) and not state["corruption"]
    return res


def _refuse(res: RunResult, reason: str) -> RunResult:
    res.refused = True
    res.refusal_reason = reason
    res.passed = False
    return res


def _stop(res: RunResult, sink: CheckpointSink, reason: str, row_id: object,
          extra: dict | None = None) -> RunResult:
    res.stopped = True
    res.stop_row = row_id
    res.stop_reason = reason
    res.n_stopped = 1
    res.passed = False
    res.resumable = False
    try:
        sink.mark_failed(reason, row_id, extra)
    except Exception as exc:  # noqa: BLE001 — ANY persistence failure must prevent PASS (cycle-5 f11)                                   # finding 10: mark_failed can fail
        res.evidence_persisted = _emergency_preserve(
            sink.path, {"status": TERMINAL_FAILED, "reason": reason, "row_id": row_id,
                        "extra": extra, "terminal_write_error": _failure_fingerprint(exc)})
    return res


_RECORD_ENVELOPE_KEYS = ("kind", "record_sha256")


def _record_hash(rec: dict) -> str:
    body = {k: v for k, v in rec.items() if k not in _RECORD_ENVELOPE_KEYS}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def _replay_certificate_defect(cert: object) -> str | None:
    """Replay the FULL serialized-certificate schema + value invariants (cycle-5 finding 7) — the
    same checks validate_outcome applies at acceptance, against the durable record."""
    if not isinstance(cert, dict):
        return "CERTIFICATE_NOT_A_DICT"
    missing = [f for f in REQUIRED_CERT_FIELDS if f not in cert]
    if missing:
        return f"CERTIFICATE_FIELDS_MISSING:{missing}"
    if cert.get("qualifies") is not True:
        return "CERTIFICATE_NOT_QUALIFYING"
    numeric = [cert[f] for f in REQUIRED_CERT_FIELDS
               if f not in ("qualifies", "n_multipliers_clipped")]
    try:
        if not all(np.isfinite(float(v)) for v in numeric):
            return "CERTIFICATE_NONFINITE_FIELD"
    except (TypeError, ValueError):
        return "CERTIFICATE_NON_NUMERIC_FIELD"
    if not (cert["gamma_lower"] <= cert["gamma_upper"]
            and cert["primal_lower"] <= cert["primal_upper"]
            and cert["dual_lower"] <= cert["dual_upper"]):
        return "CERTIFICATE_INTERVAL_REVERSED"
    n_clip = cert["n_multipliers_clipped"]
    if not (isinstance(n_clip, int) and n_clip >= 0):
        return "CERTIFICATE_CLIP_COUNT_INVALID"
    return None


def _replay_disposition_defect(rec: dict, acc: dict) -> str | None:
    """Replay the serialized equivalent of validate_outcome's disposition relationships (cycle-5
    finding 9) against the durable record."""
    disp = rec.get("disposition")
    if rec.get("stop") is not False:
        return "QUALIFIED_RECORD_WITH_STOP_FLAG"
    if disp == PRIMARY_QUALIFIED:
        if rec.get("primary_enum") != QUALIFIED:
            return "REPLAY_PRIMARY_ENUM_MISMATCH"
        if rec.get("fallback_invoked") is not False or rec.get("fallback_solver") is not None:
            return "REPLAY_FALLBACK_ON_PRIMARY_QUALIFICATION"
        if rec.get("accepted_by") != "QUADPROG_SQRT" or acc.get("solver") != "QUADPROG_SQRT":
            return "ACCEPTED_SOLVER_DISPOSITION_MISMATCH"
    elif disp == FALLBACK_QUALIFIED:
        if rec.get("primary_enum") not in (NUMERICAL_STATUS_NONQUALIFICATION,
                                           CERTIFICATE_NONQUALIFICATION):
            return "REPLAY_PRIMARY_NOT_ELIGIBLE"
        if rec.get("fallback_invoked") is not True or rec.get("fallback_enum") != QUALIFIED:
            return "REPLAY_FALLBACK_STATE_MISMATCH"
        if rec.get("accepted_by") != "PIQP_P2" or acc.get("solver") != "PIQP_P2":
            return "ACCEPTED_SOLVER_DISPOSITION_MISMATCH"
    else:
        return f"REPLAY_QUALIFIED_WITH_STOP_DISPOSITION:{disp}"
    return None


_EVIDENCE_INPUT_KEYS = ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper")
_EVIDENCE_INPUT_ENTRY_KEYS = frozenset({"shape", "exact_hex"})
# the registered accepted-block contract, frozen EXACTLY as the producer emits it (v1.8a review
# finding: every structure carrying schema-2 numerical encodings must be a CLOSED set — an unknown
# field beside z_exact_hex/lam_exact_hex must refuse, and a missing registered key must refuse
# deterministically, never as a generic replay exception). The nested certificate dict keeps its
# OWN registered contract (REQUIRED_CERT_FIELDS presence, replayed by _replay_certificate_defect)
# and is deliberately not narrowed here.
_ACCEPTED_BLOCK_KEYS = frozenset({"solver", "z_exact_hex", "lam_exact_hex",
                                  "z_sha256", "lam_sha256", "certificate"})


def _decode_exact_hex(values: object) -> np.ndarray | str:
    """Decode a schema-2.0 `*_exact_hex` list back to a float64 array (delta v1.8 canonical rules:
    decoder is float.fromhex; finite binary64 only). Returns a defect string on any refusal.
    float.fromhex accepts 'inf'/'nan' spellings, so finiteness is re-checked AFTER decode — a
    non-finite element can never have been published and is refused here too."""
    if not isinstance(values, list):
        return "EVIDENCE_EXACT_HEX_NOT_A_LIST"
    out = []
    for s in values:
        if not isinstance(s, str):
            return "EVIDENCE_EXACT_HEX_NOT_A_STRING"
        try:
            v = float.fromhex(s)
        except (ValueError, OverflowError):
            return "EVIDENCE_MALFORMED_HEX"
        if not math.isfinite(v):
            return "EVIDENCE_NON_FINITE_VALUE"
        out.append(v)
    return np.array(out, dtype=np.float64)


def _contains_ratio_fields(node: object) -> bool:
    """True if any schema-1.x ratio field (`exact_ratio` / `*_exact_ratio`) survives anywhere in
    the record tree — mixed v1/v2 representations REFUSE (delta v1.8)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and (k == "exact_ratio" or k.endswith("_exact_ratio")):
                return True
            if _contains_ratio_fields(v):
                return True
    elif isinstance(node, list):
        return any(_contains_ratio_fields(x) for x in node)
    return False


def _evidence_schema_defect(rec: dict) -> str | None:
    """Closed-schema gate (delta v1.8): version explicit and exact; no legacy ratio fields anywhere;
    the encoding-bearing structures carry EXACTLY their registered keys — unknown fields refuse."""
    ver = rec.get("evidence_schema_version")
    if ver is None:
        return "EVIDENCE_SCHEMA_VERSION_MISSING"
    if ver != EVIDENCE_SCHEMA_VERSION:
        return f"EVIDENCE_SCHEMA_VERSION_UNKNOWN:{ver!r}"
    if _contains_ratio_fields(rec):
        return "EVIDENCE_MIXED_SCHEMA_FIELDS"
    inp = rec.get("input")
    if not isinstance(inp, dict) or set(inp.keys()) != set(_EVIDENCE_INPUT_KEYS):
        return "EVIDENCE_INPUT_KEYS_INVALID"
    for k in _EVIDENCE_INPUT_KEYS:
        entry = inp[k]
        if not isinstance(entry, dict) or set(entry.keys()) != _EVIDENCE_INPUT_ENTRY_KEYS:
            return f"EVIDENCE_INPUT_ENTRY_KEYS_INVALID:{k}"
    # accepted-block closure applies to QUALIFIED records only (v1.8a): a stop/non-qualified
    # record keeps the existing disposition rules — it is never required to carry the block, and
    # a MISSING/empty block on a qualified record keeps its registered defect code
    # (QUALIFIED_WITHOUT_ACCEPTED_BLOCK, raised by the replay proper).
    if rec.get("class") == "qualified":
        acc = rec.get("accepted")
        if acc is not None and not isinstance(acc, dict):
            return "EVIDENCE_ACCEPTED_NOT_A_DICT"
        if isinstance(acc, dict) and acc:
            if set(acc.keys()) != set(_ACCEPTED_BLOCK_KEYS):
                return "EVIDENCE_ACCEPTED_KEYS_INVALID"
            if not isinstance(acc["z_exact_hex"], list):
                return "EVIDENCE_ACCEPTED_Z_EXACT_HEX_NOT_A_LIST"
            if not isinstance(acc["lam_exact_hex"], list):
                return "EVIDENCE_ACCEPTED_LAM_EXACT_HEX_NOT_A_LIST"
    return None


def verify_numerical_evidence_record(rec: dict) -> str | None:
    """Semantic REPLAY of one record's numerical claims (cycle-4 finding 9; schema 2.0 per delta
    v1.8): validate the closed schema, reconstruct the float64 arrays from the exact hex encoding,
    BYTE-VERIFY them against the recorded content hash BEFORE any semantic use, then recheck every
    nested hash and structural invariant. The outer record_sha256 is a checksum over CLAIMS; this
    validates the claims themselves."""
    try:
        sdef = _evidence_schema_defect(rec)
        if sdef is not None:
            return sdef
        comps = {}
        for k in _EVIDENCE_INPUT_KEYS:
            entry = rec["input"][k]
            a = _decode_exact_hex(entry["exact_hex"])
            if isinstance(a, str):
                return a
            comps[k] = a.reshape(entry["shape"])
        rebuilt = tuple(comps[k] for k in _EVIDENCE_INPUT_KEYS)
        if rec_content_hash(rebuilt) != rec.get("input_content_hash"):
            return "INPUT_EXACT_HEX_DOES_NOT_MATCH_CONTENT_HASH"
        mdef = validate_model_inputs(rebuilt)                # cycle-5 finding 8
        if mdef is not None:
            return f"REPLAY_MODEL_INPUT_DEFECT:{mdef}"
        if rec.get("class") == "qualified":
            acc = rec.get("accepted")
            if not acc:
                return "QUALIFIED_WITHOUT_ACCEPTED_BLOCK"
            z = _decode_exact_hex(acc["z_exact_hex"])
            if isinstance(z, str):
                return z
            lam = _decode_exact_hex(acc["lam_exact_hex"])
            if isinstance(lam, str):
                return lam
            if hashlib.sha256(np.ascontiguousarray(z).tobytes()).hexdigest() != acc.get("z_sha256"):
                return "Z_EXACT_HEX_DOES_NOT_MATCH_HASH"
            if hashlib.sha256(np.ascontiguousarray(lam).tobytes()).hexdigest() != acc.get("lam_sha256"):
                return "LAM_EXACT_HEX_DOES_NOT_MATCH_HASH"
            n = comps["t"].shape[0]
            if z.shape != (n,):
                return "Z_LENGTH_MISMATCH"
            if lam.shape != (comps["A_eq"].shape[0] + comps["A_ub"].shape[0] + 2 * n,):
                return "LAM_LENGTH_MISMATCH"
            cert = acc.get("certificate")
            cdef = _replay_certificate_defect(cert)          # cycle-5 finding 7
            if cdef is not None:
                return cdef
            ddef = _replay_disposition_defect(rec, acc)      # cycle-5 finding 9
            if ddef is not None:
                return ddef
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        return f"EVIDENCE_MALFORMED:{type(exc).__name__}"
    return None


def aggregate_verdict(state: dict, row_manifest: RowIdentityManifest) -> bool:
    """Structural PASS gate with SEMANTIC REPLAY (findings 12; cycle-4 9, 10).

    Honest scope (cycle-4 finding 10): `record_sha256` is an internal consistency CHECKSUM — it
    detects accidental modification only; a party recomputing hashes defeats it. `checkpoint_sha256`
    in the run manifest is the whole-file binding, and the AUTHENTICITY boundary is the externally
    preserved/countersigned run manifest. Record-level hashing alone is not authentication.

    PASS requires: zero corruption; one COMPLETE terminal as the final event with a matching count;
    zero stop records; exactly n_expected qualified records matching the manifest in order (id AND
    content hash); every record_sha256 re-verifying; and every record's numerical evidence REPLAYING
    (schema 2.0 exact hex → arrays → byte-verified content hash → nested hashes → structural
    invariants)."""
    return aggregate_verdict_defect(state, row_manifest) is None


def aggregate_verdict_defect(state: dict, row_manifest: RowIdentityManifest) -> str | None:
    """The PASS gate's DEFECT REPORT (delta v1.8): same conditions as aggregate_verdict, but a
    failure returns a deterministic, nonempty reason instead of a bare False — run 4 STOPped with
    an empty detail and required external forensics to diagnose. Structural failures name the
    failing condition; per-record failures report the FIRST failing record in registered row order,
    its category, and the TOTAL failing-record count (never a giant list — per-row detail stays in
    the durable evidence)."""
    if state.get("corruption"):
        return "EVIDENCE_REPLAY_FAILED:CHECKPOINT_CORRUPTION"
    if state.get("trailing_partial"):
        return "EVIDENCE_REPLAY_FAILED:CHECKPOINT_TRAILING_PARTIAL"
    terminal = state.get("terminal")
    if terminal is None or terminal.get("status") != TERMINAL_COMPLETE:
        return "EVIDENCE_REPLAY_FAILED:TERMINAL_NOT_COMPLETE"
    records = state.get("records", [])
    if terminal.get("n_records") != len(records):
        return "EVIDENCE_REPLAY_FAILED:TERMINAL_COUNT_MISMATCH"
    if any(r.get("class") != "qualified" for r in records):
        return "EVIDENCE_REPLAY_FAILED:NON_QUALIFIED_RECORD"
    if len(records) != row_manifest.n_expected:
        return "EVIDENCE_REPLAY_FAILED:RECORD_COUNT_MISMATCH"
    first: tuple[object, str] | None = None
    failed = 0
    for rec, want in zip(records, row_manifest.rows, strict=True):
        if rec.get("row_id") != want["row_id"]:
            defect = "ROW_ID_ORDER_MISMATCH"
        elif rec.get("input_content_hash") != want["content_hash"]:
            defect = "MANIFEST_CONTENT_HASH_MISMATCH"
        elif rec.get("record_sha256") != _record_hash(rec):
            defect = "RECORD_SHA256_MISMATCH"
        else:
            defect = verify_numerical_evidence_record(rec)
        if defect is not None:
            failed += 1
            if first is None:
                first = (rec.get("row_id"), defect)
    if failed:
        return (f"EVIDENCE_REPLAY_FAILED:{first[1]}:first_row_id={first[0]}:"
                f"failed_records={failed}")
    return None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# authorization + pins + static-manifest loaders (findings 2, 3, 4, 5)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


AUTHORIZATION_RECORD_TYPE = "MR002_STAGE3_EXECUTION_AUTHORIZATION"


def load_authorization(path: str, expected_sha256: str) -> dict:
    """Load + verify the countersigned execution-authorization artifact.

    Beyond the hash (which the launcher supplies via a channel independent of the file — still
    operator-controlled until the signed launch attestation exists, finding 5), the artifact's
    SEMANTICS fail closed (finding 4): record type, version, an explicit AUTHORIZED decision,
    execution_authorized exactly true, a named countersigner, and the repository identity.
    """
    got = _sha256_file(path)
    if got != expected_sha256:
        raise Stage3RunRefused(f"AUTHORIZATION_HASH_MISMATCH:{got}!={expected_sha256}")
    with open(path, encoding="utf-8") as fh:
        art = json.load(fh)
    if art.get("record_type") != AUTHORIZATION_RECORD_TYPE:
        raise Stage3RunRefused(f"AUTHORIZATION_WRONG_RECORD_TYPE:{art.get('record_type')}")
    if art.get("version") != AUTHORIZATION_VERSION:
        raise Stage3RunRefused(f"AUTHORIZATION_UNSUPPORTED_VERSION:{art.get('version')}")
    if art.get("record_status") != "IMMUTABLE":
        raise Stage3RunRefused(f"AUTHORIZATION_NOT_IMMUTABLE:{art.get('record_status')}")
    _validate_iso_date(art.get("authorized_date"), "AUTHORIZATION")   # cycle-8 issue 6
    if art.get("decision") != "AUTHORIZED":
        raise Stage3RunRefused(f"AUTHORIZATION_DECISION_NOT_AUTHORIZED:{art.get('decision')}")
    if art.get("execution_authorized") is not True:
        raise Stage3RunRefused("AUTHORIZATION_EXECUTION_FLAG_NOT_TRUE")
    if art.get("countersigned_by") != AUTHORIZED_COUNTERSIGNER:
        raise Stage3RunRefused(f"AUTHORIZATION_WRONG_COUNTERSIGNER:{art.get('countersigned_by')}")
    if art.get("repository") != "jayw04/AI-TRADING-APP":
        raise Stage3RunRefused(f"AUTHORIZATION_WRONG_REPOSITORY:{art.get('repository')}")
    for k in ("bound_commit", "bound_tree", "image_digest", "oci_config_digest",
              "source_manifest_sha256", "expected_pins_sha256",
              "execution_package_sha256", "execution_package_version"):
        if not art.get(k):
            raise Stage3RunRefused(f"AUTHORIZATION_MISSING_FIELD:{k}")
    # the protocol is a frozen identifier, exact-matched — not merely nonempty (finding 6)
    if art.get("row_manifest_protocol") != ROW_MANIFEST_PROTOCOL:
        raise Stage3RunRefused(f"AUTHORIZATION_WRONG_ROW_PROTOCOL:{art.get('row_manifest_protocol')}")
    if art.get("execution_package_version") != SUPPORTED_EXECUTION_PACKAGE_VERSION:
        raise Stage3RunRefused(
            f"AUTHORIZATION_UNSUPPORTED_PACKAGE_VERSION:{art.get('execution_package_version')}")
    return art


def verify_execution_package(path: str, auth: dict) -> dict:
    """Hash-verify the ACTUAL execution-package bytes against the authorization's binding (cycle-4
    finding 5) — the authorization may not merely NAME a package hash; the running code proves the
    referenced package exists, has those bytes, and is the supported version."""
    got = _sha256_file(path)
    if got != auth["execution_package_sha256"]:
        raise Stage3RunRefused(f"EXECUTION_PACKAGE_HASH_MISMATCH:{got}")
    with open(path, encoding="utf-8") as fh:
        pkg = json.load(fh)
    if pkg.get("record_type") != "MR002_STAGE3_EXECUTION_PACKAGE":
        raise Stage3RunRefused(f"EXECUTION_PACKAGE_WRONG_RECORD_TYPE:{pkg.get('record_type')}")
    if pkg.get("version") != SUPPORTED_EXECUTION_PACKAGE_VERSION:
        raise Stage3RunRefused(f"EXECUTION_PACKAGE_WRONG_VERSION:{pkg.get('version')}")
    return pkg


def cross_validate_authorization(auth: dict, pins) -> None:
    """The authorization artifact and the expected-pins artifact must name the SAME identities
    (finding 3) — each passing its own hash check is not enough."""
    pairs = (("bound_commit", pins.git_commit), ("bound_tree", pins.git_tree),
             ("image_digest", pins.image_digest), ("oci_config_digest", pins.oci_config_digest))
    mism = {k: (auth.get(k), v) for k, v in pairs if auth.get(k) != v}
    if mism:
        raise Stage3RunRefused(f"AUTHORIZATION_PINS_IDENTITY_MISMATCH:{sorted(mism)}")


def load_expected_pins(path: str, expected_sha256: str):
    """Load + hash-verify the countersigned expected-pins artifact into a FULL ExpectedPins."""
    from scripts.mr002_stage3_preflight import ExpectedPins
    got = _sha256_file(path)
    if got != expected_sha256:
        raise Stage3RunRefused(f"PINS_HASH_MISMATCH:{got}!={expected_sha256}")
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    if d.get("record_type") != PINS_RECORD_TYPE:
        raise Stage3RunRefused(f"PINS_WRONG_RECORD_TYPE:{d.get('record_type')}")
    if d.get("version") != PINS_VERSION:
        raise Stage3RunRefused(f"PINS_UNSUPPORTED_VERSION:{d.get('version')}")
    if d.get("record_status") != "IMMUTABLE":
        raise Stage3RunRefused(f"PINS_NOT_IMMUTABLE:{d.get('record_status')}")
    if d.get("repository") != "jayw04/AI-TRADING-APP":
        raise Stage3RunRefused(f"PINS_WRONG_REPOSITORY:{d.get('repository')}")
    # corpus_hash is MANDATORY — a countersigned pins artifact must bind it explicitly, never
    # inherit a source-code default (finding 8)
    required = ("git_commit", "git_tree", "image_digest", "oci_config_digest", "python_version",
                "python_abi", "package_versions", "material_config", "fingerprints", "corpus_hash")
    missing = [k for k in required if not d.get(k)]
    if missing:
        raise Stage3RunRefused(f"PINS_MISSING:{missing}")
    return ExpectedPins(
        git_commit=d["git_commit"], git_tree=d["git_tree"],
        image_digest=d["image_digest"], oci_config_digest=d["oci_config_digest"],
        python_version=d["python_version"], python_abi=d["python_abi"],
        package_versions=d["package_versions"], material_config=d["material_config"],
        fingerprints=d["fingerprints"], corpus_hash=d["corpus_hash"],
    )


def load_static_manifest(path: str, expected_sha256: str) -> dict:
    """Load the COMMITTED static source manifest, hash-verified against the authorization artifact.
    The checkout is verified against THIS, never a manifest regenerated from the live tree."""
    got = _sha256_file(path)
    if got != expected_sha256:
        raise Stage3RunRefused(f"SOURCE_MANIFEST_HASH_MISMATCH:{got}!={expected_sha256}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# end-to-end orchestration (findings 1, 2, 15, 16, 17, 18)
# ══════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class OrchestrationConfig:
    corpus_source: Callable[[], tuple]     # () -> (rows, claimed_hash, RowIdentityManifest, corpus_provenance)
    resolve_fn: Callable[[tuple], Outcome]
    checkpoint_path: str
    out_dir: str
    preflight_passed: bool
    expected_corpus_hash: str
    windows: tuple = ("dev",)
    provenance: dict = field(default_factory=dict)     # execution bindings (finding 15)


@dataclass
class OrchestrationResult:
    disposition: str                       # "PASS" | "STOP" | "REFUSED"
    detail: str = ""
    run: RunResult | None = None
    corpus_hash: str | None = None
    run_manifest_path: str | None = None
    run_manifest_sha256: str | None = None
    evidence_persisted: bool = True


def _output_root_defect(out_dir: str, checkpoint_path: str) -> str | None:
    """Executable output-directory controls (finding 18)."""
    if not os.path.isdir(out_dir):
        return "OUT_DIR_MISSING"
    if os.path.islink(out_dir):
        return "OUT_DIR_IS_SYMLINK"
    if os.listdir(out_dir):
        return "OUT_DIR_NOT_EMPTY"
    root = os.path.realpath(out_dir)
    if not os.path.realpath(checkpoint_path).startswith(root + os.sep):
        return "CHECKPOINT_OUTSIDE_OUTPUT_ROOT"
    return None


def orchestrate(cfg: OrchestrationConfig) -> OrchestrationResult:
    """The clean-successor run. Fails closed on EVERY exception, including a window-access violation
    (cycle-4 finding 14): each becomes a governed REFUSED/STOP with a best-effort emergency artifact
    (cycle-4 finding 13) — never an escaping traceback or a result that exists only in memory."""
    try:
        return _orchestrate_inner(cfg)
    except WindowAccessError as exc:
        res = OrchestrationResult("REFUSED", f"WINDOW_ACCESS:{exc}")
        res.evidence_persisted = _orchestration_emergency(cfg, res)
        return res
    except Exception as exc:  # noqa: BLE001
        res = OrchestrationResult("STOP", f"ORCHESTRATION_ERROR:{type(exc).__name__}:"
                                  f"{_failure_fingerprint(exc)['traceback_sha256'][:16]}")
        res.evidence_persisted = _orchestration_emergency(cfg, res, exc)
        return res


def _orchestration_emergency(cfg: OrchestrationConfig, res: OrchestrationResult,
                             exc: BaseException | None = None) -> bool:
    """Persist a run-level emergency artifact for a failed orchestration (cycle-4 finding 13)."""
    payload = {"record_type": "MR002_STAGE3_ORCHESTRATION_EMERGENCY",
               "disposition": res.disposition, "detail": res.detail}
    if exc is not None:
        payload.update(_failure_fingerprint(exc))
    if os.path.exists(cfg.checkpoint_path):
        try:
            payload["checkpoint_sha256"] = _sha256_file(cfg.checkpoint_path)
            payload["checkpoint_corruption"] = read_checkpoint(cfg.checkpoint_path)["corruption"]
        except OSError:
            payload["checkpoint_sha256"] = None
    return _emergency_preserve(os.path.join(cfg.out_dir, "MR002_Stage3_Orchestration"), payload)


def _orchestrate_inner(cfg: OrchestrationConfig) -> OrchestrationResult:
    if not cfg.preflight_passed:
        return OrchestrationResult("REFUSED", "PREFLIGHT_NOT_PASSED")
    od = _output_root_defect(cfg.out_dir, cfg.checkpoint_path)
    if od is not None:
        return OrchestrationResult("REFUSED", f"OUTPUT_ROOT:{od}")

    rows, claimed_hash, row_manifest, corpus_provenance = cfg.corpus_source()
    # cycle-7 findings 1, 10: provenance completeness is checked BEFORE any manifest is written —
    # a PASS manifest can never exist with placeholder or missing provenance.
    if not (isinstance(corpus_provenance, dict) and corpus_provenance.get("database")
            and corpus_provenance.get("days")):
        return OrchestrationResult("REFUSED", "CORPUS_PROVENANCE_INCOMPLETE")
    # Canonicalize EVERY row exactly once, BEFORE deriving any hash (cycle-4 finding 3): a mutable
    # record cannot present one value at hash time and another at resolution time. These immutable
    # read-only records are what run_population receives (its own canonicalization of an
    # already-canonical record is a byte-identical copy).
    rows = [(rid, canonicalize(r)) for rid, r in rows]

    # ── INDEPENDENT corpus verification (finding 2): derive from the actual bytes ──────────────
    derived = derive_corpus_hash([rec for _rid, rec in rows])
    if derived != cfg.expected_corpus_hash:
        return OrchestrationResult("STOP", f"CORPUS_HASH_MISMATCH:derived={derived}",
                                   corpus_hash=derived)
    if claimed_hash != derived:
        return OrchestrationResult("STOP", "CORPUS_SOURCE_CLAIMED_HASH_INCONSISTENT",
                                   corpus_hash=derived)
    if row_manifest.corpus_hash != derived:
        return OrchestrationResult("STOP", "ROW_MANIFEST_CORPUS_HASH_MISMATCH", corpus_hash=derived)

    run = run_population(rows, cfg.resolve_fn, cfg.checkpoint_path,
                         preflight_passed=cfg.preflight_passed, row_manifest=row_manifest,
                         windows=cfg.windows)
    disposition = "PASS" if run.passed else ("REFUSED" if run.refused else "STOP")

    # ── run manifest: full provenance + FINAL CHECKPOINT BYTES bound (findings 15, 16) ─────────
    checkpoint_sha = _sha256_file(cfg.checkpoint_path) if os.path.exists(cfg.checkpoint_path) else None
    run_manifest_path = os.path.join(cfg.out_dir, "MR002_Stage3_CleanRun_Manifest.json")
    doc = {
        "record_type": "MR002_STAGE3_CLEAN_RUN_MANIFEST",
        "disposition": disposition,
        "corpus_hash_derived_by_runner": derived,
        "n_expected": row_manifest.n_expected,
        "row_manifest_sha256": row_manifest.canonical_hash(),
        "corpus_source_provenance": corpus_provenance,   # cycle-7 f1: the ACTUAL pre-capture observations
        "checkpoint_sha256": checkpoint_sha,
        "execution_provenance": cfg.provenance,
        "run": run.summary(),
        "checkpoint": cfg.checkpoint_path,
        "validation_and_sealed_oos": "SEALED AND UNREAD",
        "scope_boundary": "a clean-run PASS authorizes ONLY submission of its evidence for adjudication",
    }
    expected_sha = _atomic_write_json(run_manifest_path, doc)
    # post-write BYTE-EXACT verification (cycle-5 finding 12): observed file hash == expected hash
    if _sha256_file(run_manifest_path) != expected_sha:
        return OrchestrationResult("STOP", "RUN_MANIFEST_VERIFICATION_FAILED",
                                   run=run, corpus_hash=derived)
    result = OrchestrationResult(disposition, run.refusal_reason or run.stop_reason,
                                 run=run, corpus_hash=derived, run_manifest_path=run_manifest_path)
    result.run_manifest_sha256 = _sha256_file(run_manifest_path)
    return result


def _atomic_write_json(path: str, doc: dict) -> str:
    """Byte-exact governed persistence (cycle-5 finding 12): canonical bytes generated ONCE, their
    sha256 precomputed, staged, fsynced, atomically renamed. Returns the expected sha256 so callers
    can compare the observed file hash. Shared by every governance JSON artifact."""
    payload = (json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False,
                          default=str) + "\n").encode("utf-8")
    expected = hashlib.sha256(payload).hexdigest()
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    try:
        dfd = os.open(os.path.dirname(path) or ".", os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass
    return expected


# ══════════════════════════════════════════════════════════════════════════════════════════════
# the PRODUCTION corpus source + real entry point (findings 1, 29)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def production_corpus_source() -> tuple:  # pragma: no cover - in-image, post-authorization only
    """Regenerate the registered corpus ANEW (adjudication §10) and build the successor population.

    This code exists and is reviewable BEFORE authorization (finding 29); it executes only after
    `run_clean_successor` has verified the authorization artifact, pins, static manifest, seal, and
    preflight. It replays the frozen deterministic capture over the DEV window only, then builds the
    ordered row-identity manifest from the captured instances. It reuses NO quarantined artifact:
    the corpus is regenerated from the frozen dataset by the frozen capture path, and every hash is
    recomputed here.
    """
    from datetime import date

    import app.research.mr002.joint_portfolio as jp
    from app.research.mr002.dataset import FrozenDataset
    from app.research.mr002.runner import CONFIGS
    from scripts.mr002_coverage_signed_gap import CORPUS, capture
    from scripts.mr002_development_run import run_config

    # cycle-4 finding 4: the module-level capture list must be PROVEN fresh — never assumed, never
    # silently cleared (clearing would hide contamination). The patched hook is restored either way.
    if CORPUS:
        raise Stage3RunRefused(f"CAPTURE_CORPUS_NOT_EMPTY:{len(CORPUS)}")
    # cycle-5 finding 6: the database must be verifiable BEFORE regeneration — a provenance error
    # refuses the run, it never merely appears in the final manifest.
    db_path = "/work/apps/backend/data/mr002_research.duckdb"
    if not os.path.isfile(db_path) or os.path.islink(db_path):
        raise Stage3RunRefused(f"CORPUS_DB_NOT_A_REGULAR_FILE:{db_path}")
    try:
        db_prov = {"path": db_path, "sha256": _sha256_file(db_path),
                   "byte_length": os.path.getsize(db_path)}
    except OSError as exc:
        raise Stage3RunRefused(f"CORPUS_DB_UNHASHABLE:{exc}") from exc
    prior_solve_qp = jp._solve_qp
    ds = None
    try:
        jp._solve_qp = capture
        ds = FrozenDataset(db_path)
        # cycle-5 finding 5: materialize BEFORE the config loop — config A must not exhaust an
        # iterator that B/C then see empty. Day-sequence identity is bound alongside.
        days = tuple(ds.day_inputs(date(2013, 1, 2), date(2019, 10, 2)))     # DEV window ONLY
        if not days:
            raise Stage3RunRefused("CORPUS_DAYS_EMPTY")
        day_provenance = {"n_days": len(days),
                          "first": str(getattr(days[0], "day", days[0])),
                          "last": str(getattr(days[-1], "day", days[-1])),
                          "sequence_sha256": hashlib.sha256(
                              "|".join(str(getattr(d, "day", d)) for d in days).encode()).hexdigest()}
        for cfg_name in ("A", "B", "C"):
            run_config(days, CONFIGS[cfg_name])
    finally:
        jp._solve_qp = prior_solve_qp
        close = getattr(ds, "close", None)
        if callable(close):
            close()
    provenance = {"database": db_prov, "days": day_provenance}
    # cycle-4 finding 17: independent count diagnostic BEFORE hashing (the hash stays authoritative)
    if len(CORPUS) != EXPECTED_CORPUS_INSTANCES:
        raise Stage3RunRefused(
            f"CAPTURE_COUNT_MISMATCH:{len(CORPUS)}!={EXPECTED_CORPUS_INSTANCES}")

    rows = []
    manifest_rows = []
    for i, inst in enumerate(CORPUS):
        rec = (inst["t"], inst["A_ub"], inst["b_ub"], inst["A_eq"], inst["b_eq"], inst["upper"])
        canon = canonicalize(rec)
        rows.append((i, canon))
        manifest_rows.append({"row_id": i, "content_hash": rec_content_hash(canon)})
    corpus_hash = derive_corpus_hash([r for _i, r in rows])
    return rows, corpus_hash, RowIdentityManifest(corpus_hash=corpus_hash,
                                                  rows=tuple(manifest_rows)), provenance


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Phase-B execution-evidence binding + launch attestation (cycle-5 findings 2, 3, 13, 14)
# ══════════════════════════════════════════════════════════════════════════════════════════════
BINDING_RECORD_TYPE = "MR002_STAGE3_EXECUTION_BINDING"
ATTESTATION_RECORD_TYPE = "MR002_STAGE3_LAUNCH_ATTESTATION"
# Two-phase closure of the manifest-harness-clean-tree circularity (finding 2): Phase A = the
# committed PRE_EXECUTION_SOURCE manifest (realism artifact may be absent); the preflight-gated
# harness then runs; Phase B = this EXTERNAL binding artifact, which enumerates by sha256+length the
# Phase-A manifest, the realism PASS, the final in-image test report, the package, the pins, the
# authorization, and the launch attestation. The countersignature binds Phase B. The Phase-A
# manifest is NEVER regenerated inside the authorized container.
BINDING_REQUIRED_FIELDS = (
    "implementation_manifest_sha256", "realism_pass_sha256", "final_test_report_sha256",
    "execution_package_sha256", "expected_pins_sha256", "authorization_sha256",
    "launch_attestation_sha256", "launch_verification_receipt_sha256",
    "bound_commit", "bound_tree", "image_digest", "oci_config_digest")
# The signed launch attestation (finding 3) must bind at least these — it is produced by the
# LAUNCHER/runtime, not by this process, which is what removes the operator-controlled hash channel.
ATTESTATION_REQUIRED_FIELDS = (
    "authorization_sha256", "expected_pins_sha256", "source_manifest_sha256",
    "execution_package_sha256", "bound_commit", "bound_tree", "image_digest", "oci_config_digest",
    "launcher_identity", "exact_command", "output_mount_identity", "run_nonce", "signature",
    "signature_algorithm", "signing_key_id", "canonical_signed_payload_sha256",
    "verification_tool", "verification_tool_sha256")


def _require_hex64(d: dict, fields, ctx: str) -> None:
    """Cycle-6 finding 14: hash fields must be exact 64-hex; commit/tree 40-hex; image/OCI sha256:<64hex>."""
    for k in fields:
        v = str(d.get(k, ""))
        if k in ("bound_commit", "bound_tree"):
            ok = bool(re.match(r"^[0-9a-f]{40}$", v))
        elif k in ("image_digest", "oci_config_digest"):
            ok = bool(re.match(r"^sha256:[0-9a-f]{64}$", v))
        else:
            ok = bool(_HEX64.match(v))
        if not ok:
            raise Stage3RunRefused(f"{ctx}_FIELD_NOT_VALID_FORMAT:{k}:{v[:20]}")


def load_execution_binding(path: str, expected_sha256: str) -> dict:
    """Load + verify the Phase-B execution-evidence binding artifact (findings 2, 14)."""
    got = _sha256_file(path)
    if got != expected_sha256:
        raise Stage3RunRefused(f"BINDING_HASH_MISMATCH:{got}")
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    if d.get("record_type") != BINDING_RECORD_TYPE:
        raise Stage3RunRefused(f"BINDING_WRONG_RECORD_TYPE:{d.get('record_type')}")
    missing = [k for k in BINDING_REQUIRED_FIELDS if not d.get(k)]
    if missing:
        raise Stage3RunRefused(f"BINDING_MISSING:{missing}")
    # cycle-6 finding 4: closed Phase-B schema — version/status/countersigner/date/repository
    if d.get("version") != "1.0":
        raise Stage3RunRefused(f"BINDING_UNSUPPORTED_VERSION:{d.get('version')}")
    if d.get("record_status") != "IMMUTABLE":
        raise Stage3RunRefused(f"BINDING_NOT_IMMUTABLE:{d.get('record_status')}")
    if d.get("countersigned_by") != AUTHORIZED_COUNTERSIGNER:
        raise Stage3RunRefused(f"BINDING_WRONG_COUNTERSIGNER:{d.get('countersigned_by')}")
    if d.get("repository") != "jayw04/AI-TRADING-APP":
        raise Stage3RunRefused(f"BINDING_WRONG_REPOSITORY:{d.get('repository')}")
    _validate_iso_date(d.get("countersigned_date"), "BINDING")
    _require_hex64(d, BINDING_REQUIRED_FIELDS, "BINDING")
    # cycle-7 finding 6: a CLOSED schema rejects unexpected keys
    allowed = set(BINDING_REQUIRED_FIELDS) | {"record_type", "version", "record_status",
                                             "countersigned_by", "countersigned_date",
                                             "repository", "decision", "execution_authorized",
                                             "scope"}
    extra = sorted(set(d) - allowed)
    if extra:
        raise Stage3RunRefused(f"BINDING_UNEXPECTED_KEYS:{extra}")
    # cycle-7 finding 8: Phase B carries its own explicit decision + scope
    if d.get("decision") != "EXECUTION_PACKAGE_COUNTERSIGNED":
        raise Stage3RunRefused(f"BINDING_DECISION_INVALID:{d.get('decision')}")
    if d.get("execution_authorized") is not True:
        raise Stage3RunRefused("BINDING_EXECUTION_FLAG_NOT_TRUE")
    if d.get("scope") != "MR002_STAGE3_CLEAN_SUCCESSOR_ONLY":
        raise Stage3RunRefused(f"BINDING_SCOPE_INVALID:{d.get('scope')}")
    return d


def _validate_iso_date(v, ctx: str) -> None:
    """Cycle-6 finding 15: real calendar dates, not just the YYYY-MM-DD shape."""
    import datetime
    try:
        datetime.date.fromisoformat(str(v))
    except (TypeError, ValueError) as exc:
        raise Stage3RunRefused(f"{ctx}_DATE_INVALID:{v}") from exc


def cross_validate_binding(binding: dict, *, authorization_sha: str, pins_sha: str,
                           manifest_sha: str, attestation_sha: str, package_sha: str,
                           auth: dict, realism_sha: str, final_report_sha: str) -> None:
    """Cycle-6 findings 1, 3: Phase B must agree with the ACTUAL artifact bytes and with the
    authorization's identities — a plausible 64-hex string is not evidence."""
    pairs = {"authorization_sha256": authorization_sha, "expected_pins_sha256": pins_sha,
             "implementation_manifest_sha256": manifest_sha,
             "launch_attestation_sha256": attestation_sha,
             "execution_package_sha256": package_sha,
             "realism_pass_sha256": realism_sha, "final_test_report_sha256": final_report_sha}
    mism = [k for k, v in pairs.items() if binding.get(k) != v]
    if mism:
        raise Stage3RunRefused(f"BINDING_ARTIFACT_HASH_MISMATCH:{mism}")
    idm = [k for k in ("bound_commit", "bound_tree", "image_digest", "oci_config_digest")
           if binding.get(k) != auth.get(k)]
    if idm:
        raise Stage3RunRefused(f"BINDING_IDENTITY_MISMATCH:{idm}")


REALISM_RECORD_TYPE = "MR002_STAGE3_CASCADE_REALISM_HARNESS"
REALISM_REQUIRED_CASE_GROUPS = ("primary_qualified", "fallback_qualified", "certifier_classification")
PRODUCTION_BINDING_TEST_ID = ("tests/research/test_mr002_stage3_cascade_dispA.py"
                              "::test_production_binding_uses_frozen_solvers")
FINAL_REPORT_REQUIRED_MODULES = (
    "tests/research/test_mr002_stage3_cascade_dispA.py",
    "tests/research/test_mr002_stage3_preflight.py",
    "tests/research/test_mr002_stage3_population_runner.py",
    "tests/research/test_mr002_stage3_input_contract.py")
FINAL_REPORT_MIN_TESTS = 100
TEST_REPORT_RECORD_TYPE = "MR002_STAGE3_TEST_REPORT"
RECEIPT_RECORD_TYPE = "MR002_STAGE3_LAUNCH_VERIFICATION_RECEIPT"


def validate_realism_case(c: dict) -> str | None:
    """Cycle-9 blocker 2: group-specific semantic requirements derived from the case's durable
    fields — the case's own `pass` boolean is never the authority."""
    name = str(c.get("case", ""))
    if name.startswith("primary_qualified/"):
        if c.get("disposition") != PRIMARY_QUALIFIED:
            return "DISPOSITION_NOT_PRIMARY_QUALIFIED"
        if c.get("primary_solver") != "QUADPROG_SQRT" or c.get("primary_enum") != QUALIFIED:
            return "PRIMARY_IDENTITY_OR_ENUM"
        if c.get("fallback_invoked") is not False or c.get("accepted_by") != "QUADPROG_SQRT":
            return "FALLBACK_OR_ACCEPTED_BY"
        if c.get("stop") is not False:
            return "STOP_NOT_FALSE"
    elif name.startswith("fallback_qualified/"):
        if c.get("disposition") != FALLBACK_QUALIFIED:
            return "DISPOSITION_NOT_FALLBACK_QUALIFIED"
        if c.get("primary_enum") != NUMERICAL_STATUS_NONQUALIFICATION:
            return "PRIMARY_ENUM_NOT_NUMERICAL"
        if c.get("fallback_solver") != "PIQP_P2" or c.get("fallback_enum") != QUALIFIED:
            return "FALLBACK_IDENTITY_OR_ENUM"
        if c.get("fallback_invoked") is not True or c.get("accepted_by") != "PIQP_P2":
            return "FALLBACK_INVOCATION_OR_ACCEPTED_BY"
        if c.get("stop") is not False:
            return "STOP_NOT_FALSE"
    elif name.startswith("certifier_classification/"):
        if c.get("expected_primary_enum") != CERTIFICATE_NONQUALIFICATION \
                or c.get("primary_enum") != CERTIFICATE_NONQUALIFICATION:
            return "PRIMARY_ENUM_NOT_CERTIFICATE"
    else:
        return "UNKNOWN_CASE_GROUP"
    return None


def load_realism_pass(path: str, expected_sha256: str) -> dict:
    """Cycle-7 finding 2: the realism artifact must SEMANTICALLY qualify, not merely hash-match —
    verdict PASS, preflight passed, cases passed, evidence persisted."""
    got = _sha256_file(path)
    if got != expected_sha256:
        raise Stage3RunRefused(f"REALISM_HASH_MISMATCH:{got}")
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    if d.get("record_type") != REALISM_RECORD_TYPE:
        raise Stage3RunRefused(f"REALISM_WRONG_RECORD_TYPE:{d.get('record_type')}")
    if d.get("verdict") != "PASS":
        raise Stage3RunRefused(f"REALISM_VERDICT_NOT_PASS:{d.get('verdict')}")
    if d.get("preflight_passed") is not True:
        raise Stage3RunRefused("REALISM_PREFLIGHT_NOT_PASSED")
    if d.get("cases_pass") is not True:
        raise Stage3RunRefused("REALISM_CASES_NOT_PASSED")
    if d.get("evidence_persisted") is not True:      # cycle-8 issue 1: NO default; missing refuses
        raise Stage3RunRefused("REALISM_EVIDENCE_NOT_PERSISTED")
    # cycle-8 issue 2: derive case qualification from the CASES, never trust the aggregate
    cases = d.get("cases")
    if not (isinstance(cases, list) and cases):
        raise Stage3RunRefused("REALISM_CASES_EMPTY")
    names = [c.get("case") for c in cases]
    if len(set(names)) != len(names):
        raise Stage3RunRefused("REALISM_CASE_NAMES_NOT_UNIQUE")
    for grp in REALISM_REQUIRED_CASE_GROUPS:
        if not any(str(n).startswith(grp + "/") for n in names):
            raise Stage3RunRefused(f"REALISM_CASE_GROUP_MISSING:{grp}")
    for c in cases:
        if c.get("pass") is not True:
            raise Stage3RunRefused(f"REALISM_CASE_NOT_PASSED:{c.get('case')}")
        for hk in ("rec_sha256", "outcome_sha256"):
            if not _HEX64.match(str(c.get(hk, ""))):
                raise Stage3RunRefused(f"REALISM_CASE_HASH_INVALID:{c.get('case')}:{hk}")
    br = d.get("binds_real")
    # cycle-9 blocker 1: EXACT closed implementation identities, never merely truthy
    if not isinstance(br, dict) or br.get("primary") != "QUADPROG_SQRT" \
            or br.get("fallback") != "PIQP_P2" \
            or not str(br.get("certifier", "")).startswith("canonical_qualify"):
        raise Stage3RunRefused(f"REALISM_BINDS_REAL_INVALID:{br}")
    # cycle-9 blocker 2: each case verdict is DERIVED from its durable fields, per group
    for c in cases:
        cdef = validate_realism_case(c)
        if cdef is not None:
            raise Stage3RunRefused(f"REALISM_CASE_SEMANTICS:{c.get('case')}:{cdef}")
    if d.get("cases_pass") is not True:               # the aggregate must AGREE with the cases
        raise Stage3RunRefused("REALISM_AGGREGATE_DISAGREES")
    return d


def load_final_test_report(path: str, expected_sha256: str, binding: dict | None = None) -> dict:
    """Cycle-7 finding 2: the final report must be ADMISSIBLE — exit 0, ZERO skips (the
    production-binding test must have RUN), clean tree, admissible_as_final true."""
    got = _sha256_file(path)
    if got != expected_sha256:
        raise Stage3RunRefused(f"TEST_REPORT_HASH_MISMATCH:{got}")
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    if d.get("record_type") != TEST_REPORT_RECORD_TYPE:
        raise Stage3RunRefused(f"TEST_REPORT_WRONG_RECORD_TYPE:{d.get('record_type')}")
    if d.get("exit_code") != 0:
        raise Stage3RunRefused(f"TEST_REPORT_EXIT_NONZERO:{d.get('exit_code')}")
    if d.get("collected_skipped") != 0:
        raise Stage3RunRefused(f"TEST_REPORT_HAS_SKIPS:{d.get('collected_skipped')}")
    if d.get("working_tree_dirty") is not False:
        raise Stage3RunRefused("TEST_REPORT_DIRTY_TREE")
    if d.get("admissible_as_final") is not True:
        raise Stage3RunRefused("TEST_REPORT_NOT_ADMISSIBLE")
    # cycle-8 issue 3: a machine-readable collected-test manifest is REQUIRED — zero skips alone
    # cannot prove the production-binding test ran.
    ids = d.get("collected_test_ids")
    if not (isinstance(ids, list) and len(ids) >= FINAL_REPORT_MIN_TESTS):
        raise Stage3RunRefused("TEST_REPORT_IDS_MISSING_OR_TOO_FEW")
    if PRODUCTION_BINDING_TEST_ID not in ids:
        raise Stage3RunRefused("TEST_REPORT_PRODUCTION_BINDING_NOT_COLLECTED")
    for mod in FINAL_REPORT_REQUIRED_MODULES:
        if not any(str(i).startswith(mod + "::") for i in ids):
            raise Stage3RunRefused(f"TEST_REPORT_MODULE_MISSING:{mod}")
    # cycle-9 blocker 3: a per-test RESULT map is required; every count is DERIVED from it
    results = d.get("test_results")
    if not (isinstance(results, list) and results):
        raise Stage3RunRefused("TEST_REPORT_RESULTS_MISSING")
    rids = [r.get("test_id") for r in results]
    if len(set(rids)) != len(rids):
        raise Stage3RunRefused("TEST_REPORT_DUPLICATE_RESULTS")
    if set(rids) != set(ids):
        raise Stage3RunRefused("TEST_REPORT_RESULTS_IDS_MISMATCH")
    not_passed = [r["test_id"] for r in results if r.get("outcome") != "passed"]
    if not_passed:
        raise Stage3RunRefused(f"TEST_REPORT_NOT_ALL_PASSED:{not_passed[:3]}")
    if d.get("collected_passed") != len(results):
        raise Stage3RunRefused("TEST_REPORT_PASSED_COUNT_DISAGREES")
    pb = [r for r in results if r.get("test_id") == PRODUCTION_BINDING_TEST_ID]
    if not (pb and pb[0].get("outcome") == "passed"):
        raise Stage3RunRefused("TEST_REPORT_PRODUCTION_BINDING_RECORD_NOT_PASSED")
    if d.get("production_binding_outcome") != "passed":
        raise Stage3RunRefused("TEST_REPORT_PRODUCTION_BINDING_NOT_PASSED")
    # cycle-9 blocker 4: the report must STATE the runtime identities and match Phase B — a hash
    # match alone does not prove the tests ran under the countersigned implementation/image.
    if binding is not None:
        for k in ("bound_commit", "bound_tree", "image_digest", "oci_config_digest",
                  "source_manifest_sha256", "expected_pins_sha256", "execution_package_sha256"):
            bkey = {"source_manifest_sha256": "implementation_manifest_sha256"}.get(k, k)
            if d.get(k) != binding.get(bkey):
                raise Stage3RunRefused(f"TEST_REPORT_IDENTITY_MISMATCH:{k}")
    return d


RECEIPT_ALLOWED_KEYS = frozenset({"record_type", "version", "record_status",
                                  "verification_exit_status", "verification_tool_sha256",
                                  "signing_key_id", "signature_algorithm",
                                  "canonical_signed_payload_sha256", "attestation_sha256",
                                  "verified_at", "run_nonce"})


def load_verification_receipt(path: str, expected_sha256: str, attestation_sha256: str,
                              attestation: dict | None = None) -> dict:
    """Cycle-7 finding 3: the launcher's signature-verification RECEIPT is required — this process
    does not hold the trusted key, so it requires proof that the frozen tool verified the
    attestation signature (exit 0) against the trusted key, bound to the actual attestation bytes."""
    got = _sha256_file(path)
    if got != expected_sha256:
        raise Stage3RunRefused(f"RECEIPT_HASH_MISMATCH:{got}")
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    if d.get("record_type") != RECEIPT_RECORD_TYPE:
        raise Stage3RunRefused(f"RECEIPT_WRONG_RECORD_TYPE:{d.get('record_type')}")
    if d.get("version") != "1.0":                     # cycle-9 blocker 6
        raise Stage3RunRefused(f"RECEIPT_UNSUPPORTED_VERSION:{d.get('version')}")
    if d.get("record_status") != "IMMUTABLE":
        raise Stage3RunRefused(f"RECEIPT_NOT_IMMUTABLE:{d.get('record_status')}")
    for k in ("run_nonce", "verified_at"):            # cycle-9 blocker 5: mandatory, not optional
        if not d.get(k):
            raise Stage3RunRefused(f"RECEIPT_MISSING:{k}")
    if d.get("verification_exit_status") != 0:
        raise Stage3RunRefused(f"RECEIPT_VERIFICATION_FAILED:{d.get('verification_exit_status')}")
    for k in ("verification_tool_sha256", "signing_key_id", "attestation_sha256"):
        if not d.get(k):
            raise Stage3RunRefused(f"RECEIPT_MISSING:{k}")
    if d.get("attestation_sha256") != attestation_sha256:
        raise Stage3RunRefused("RECEIPT_ATTESTATION_MISMATCH")
    if not _HEX64.match(str(d.get("verification_tool_sha256", ""))):
        raise Stage3RunRefused("RECEIPT_TOOL_HASH_INVALID")
    extra = sorted(set(d) - RECEIPT_ALLOWED_KEYS)
    if extra:
        raise Stage3RunRefused(f"RECEIPT_UNEXPECTED_KEYS:{extra}")
    # cycle-8 issues 4, 5: the receipt must agree with the PARSED attestation — same key, same
    # algorithm, same canonical payload — else a different key could claim the verification.
    if attestation is not None:
        # cycle-9 blockers 5, 7: nonce and TOOL identity must also match the attestation
        for k in ("signing_key_id", "signature_algorithm", "canonical_signed_payload_sha256",
                  "run_nonce", "verification_tool_sha256"):
            if d.get(k) != attestation.get(k):
                raise Stage3RunRefused(f"RECEIPT_ATTESTATION_FIELD_MISMATCH:{k}")
    return d


def load_launch_attestation(path: str, expected_sha256: str) -> dict:
    """Load + structurally verify the signed launch attestation (finding 3). Signature VERIFICATION
    against the launcher's key is performed by the verification tooling outside this process; this
    loader enforces the schema and the binding set."""
    got = _sha256_file(path)
    if got != expected_sha256:
        raise Stage3RunRefused(f"ATTESTATION_HASH_MISMATCH:{got}")
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    if d.get("record_type") != ATTESTATION_RECORD_TYPE:
        raise Stage3RunRefused(f"ATTESTATION_WRONG_RECORD_TYPE:{d.get('record_type')}")
    if d.get("version") != "1.0":                     # cycle-8 issue 7
        raise Stage3RunRefused(f"ATTESTATION_UNSUPPORTED_VERSION:{d.get('version')}")
    if d.get("record_status") != "IMMUTABLE":
        raise Stage3RunRefused(f"ATTESTATION_NOT_IMMUTABLE:{d.get('record_status')}")
    allowed = set(ATTESTATION_REQUIRED_FIELDS) | {"record_type", "version", "record_status"}
    extra = sorted(set(d) - allowed)
    if extra:
        raise Stage3RunRefused(f"ATTESTATION_UNEXPECTED_KEYS:{extra}")
    missing = [k for k in ATTESTATION_REQUIRED_FIELDS if not d.get(k)]
    if missing:
        raise Stage3RunRefused(f"ATTESTATION_MISSING:{missing}")
    _require_hex64(d, ("authorization_sha256", "expected_pins_sha256", "source_manifest_sha256",
                       "execution_package_sha256", "bound_commit", "bound_tree",
                       "image_digest", "oci_config_digest",
                       "canonical_signed_payload_sha256", "verification_tool_sha256"), "ATTESTATION")
    # cycle-7 finding 4: RECOMPUTE the canonical unsigned payload and require hash equality.
    # FROZEN definition: every field except {signature, canonical_signed_payload_sha256}, serialized
    # json.dumps(sort_keys=True, separators=(",",":")) utf-8.
    unsigned = {k: v for k, v in d.items()
                if k not in ("signature", "canonical_signed_payload_sha256")}
    payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(payload).hexdigest() != d["canonical_signed_payload_sha256"]:
        raise Stage3RunRefused("ATTESTATION_PAYLOAD_HASH_MISMATCH")
    # cycle-6 finding 5: the signature envelope must be complete. VERIFICATION against the trusted
    # key happens here structurally; cryptographic verification is executed by the frozen
    # verification tool named in the artifact BEFORE launch (still OPEN until the launcher exists).
    for k in ("signature_algorithm", "signing_key_id", "canonical_signed_payload_sha256",
              "verification_tool"):
        if not d.get(k):
            raise Stage3RunRefused(f"ATTESTATION_SIGNATURE_ENVELOPE_MISSING:{k}")
    return d


def _database_provenance(path: str) -> dict:  # pragma: no cover - in-image
    """SHA-256 + byte length + path of the regeneration database (cycle-4 finding 22)."""
    try:
        return {"path": path, "sha256": _sha256_file(path), "byte_length": os.path.getsize(path)}
    except OSError as exc:
        return {"path": path, "error": str(exc)[:120]}


def run_clean_successor() -> int:  # pragma: no cover - in-image, post-countersignature only
    """The authorized clean rerun — fully wired (finding 1): verify authorization + pins + static
    manifest (cross-validated), seal the implementations, run preflight, then orchestrate the
    population through `resolve_instance`. Refuses on any missing/mismatched governance input."""
    auth_path = os.environ.get("MR002_EXECUTION_COUNTERSIGN")
    auth_sha = os.environ.get("MR002_EXECUTION_COUNTERSIGN_SHA256")
    if not auth_path or not auth_sha:
        print("REFUSED: execution-authorization artifact + its SHA-256 are required "
              "(adjudication §10). Nothing resolved.")
        return 2
    try:
        auth = load_authorization(auth_path, auth_sha)
        pins = load_expected_pins(os.environ["MR002_EXPECTED_PINS"], auth["expected_pins_sha256"])
        cross_validate_authorization(auth, pins)                          # finding 3
        manifest_path = os.environ["MR002_SOURCE_MANIFEST"]
        manifest = load_static_manifest(manifest_path, auth["source_manifest_sha256"])
        # cycle-4 finding 5: the ACTUAL execution-package bytes are verified, not just named
        verify_execution_package(os.environ["MR002_EXECUTION_PACKAGE"], auth)
        # ★ cycle-6 findings 1, 2: Phase B + the signed launch attestation are MANDATORY
        # preconditions of the executable path — required, loaded, and cross-validated against the
        # ACTUAL artifact bytes BEFORE preflight. This makes the designed governance boundary the
        # boundary the executable enforces.
        binding_path = os.environ["MR002_EXECUTION_BINDING"]
        binding = load_execution_binding(binding_path,
                                         os.environ["MR002_EXECUTION_BINDING_SHA256"])
        att_path = os.environ["MR002_LAUNCH_ATTESTATION"]
        attestation = load_launch_attestation(att_path, binding["launch_attestation_sha256"])
        # cycle-7 finding 2: realism + final-test artifacts must SEMANTICALLY qualify
        realism_sha = binding["realism_pass_sha256"]
        report_sha = binding["final_test_report_sha256"]
        realism = load_realism_pass(os.environ["MR002_REALISM_PASS"], realism_sha)
        report = load_final_test_report(os.environ["MR002_FINAL_TEST_REPORT"], report_sha,
                                        binding=binding)
        receipt = load_verification_receipt(os.environ["MR002_LAUNCH_VERIFICATION_RECEIPT"],
                                            binding["launch_verification_receipt_sha256"],
                                            _sha256_file(att_path), attestation=attestation)
        semantic_summary = {          # finding 10: minimal normalized summary for the run manifest
            "receipt_key_id": receipt.get("signing_key_id"),
            "receipt_run_nonce": receipt.get("run_nonce"),
            "verification_tool_sha256": receipt.get("verification_tool_sha256"),
            "realism_case_count": len(realism.get("cases", [])),
            "final_test_count": len(report.get("test_results", [])),
            "production_binding_outcome": report.get("production_binding_outcome"),
        }
        cross_validate_binding(
            binding,
            authorization_sha=auth_sha,
            pins_sha=auth["expected_pins_sha256"],
            manifest_sha=auth["source_manifest_sha256"],
            attestation_sha=_sha256_file(att_path),
            package_sha=auth["execution_package_sha256"],
            auth=auth,
            realism_sha=_sha256_file(os.environ["MR002_REALISM_PASS"]),
            final_report_sha=_sha256_file(os.environ["MR002_FINAL_TEST_REPORT"]),
        )
        # the attestation must name the same identities as the authorization (finding 3)
        if (attestation.get("authorization_sha256") != auth_sha
                or attestation.get("expected_pins_sha256") != auth["expected_pins_sha256"]
                or attestation.get("source_manifest_sha256") != auth["source_manifest_sha256"]
                or attestation.get("execution_package_sha256") != auth["execution_package_sha256"]
                or any(attestation.get(k) != auth.get(k) for k in
                       ("bound_commit", "bound_tree", "image_digest", "oci_config_digest"))):
            raise Stage3RunRefused("ATTESTATION_IDENTITY_MISMATCH")
    except (Stage3RunRefused, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"REFUSED: {exc}")
        return 2

    from app.research.mr002.stage3_cascade import resolve_instance, seal_implementations
    from scripts.mr002_stage3_preflight import evaluate, gather_env
    from scripts.mr002_stage3_source_manifest import verify_source
    seal_implementations(pins.fingerprints)
    rep = evaluate(gather_env(), pins, verify_source(manifest))
    if not rep.passed:
        print("REFUSED: preflight failed:", rep.summary()["failed"])
        return 2

    out_dir = os.environ.get("MR002_OUT", "/out/cleanrun")
    cfg = OrchestrationConfig(
        corpus_source=production_corpus_source,
        resolve_fn=resolve_instance,
        checkpoint_path=os.path.join(out_dir, "MR002_Stage3_CleanRun_checkpoint.jsonl"),
        out_dir=out_dir,
        preflight_passed=rep.passed,
        expected_corpus_hash=pins.corpus_hash,
        provenance={
            # cycle-6 findings 8, 9: the database + day-sequence provenance CAPTURED by the corpus
            # source (pre-capture observation) is what reaches the manifest — never re-observed.
            "row_manifest_protocol": ROW_MANIFEST_PROTOCOL,
            "execution_binding_sha256": os.environ.get("MR002_EXECUTION_BINDING_SHA256"),
            "launch_attestation_sha256": binding["launch_attestation_sha256"],
            # cycle-7 finding 11: the executed evidence set is auditable without dereferencing Phase B
            "realism_pass_sha256": binding["realism_pass_sha256"],
            "final_test_report_sha256": binding["final_test_report_sha256"],
            "launch_verification_receipt_sha256": binding["launch_verification_receipt_sha256"],
            "semantic_summary": semantic_summary,
            "authorization_sha256": auth_sha,
            "expected_pins_sha256": auth["expected_pins_sha256"],
            "source_manifest_sha256": auth["source_manifest_sha256"],
            "execution_package_sha256": auth["execution_package_sha256"],
            "bound_commit": auth["bound_commit"], "bound_tree": auth["bound_tree"],
            "image_digest": auth["image_digest"], "oci_config_digest": auth["oci_config_digest"],
            "preflight_report_sha256": hashlib.sha256(
                json.dumps(rep.summary(), sort_keys=True).encode()).hexdigest(),
        },
    )
    result = orchestrate(cfg)
    print(json.dumps({"disposition": result.disposition, "detail": result.detail,
                      "corpus_hash": result.corpus_hash,
                      "run_manifest": result.run_manifest_path}, indent=2))
    return {"PASS": 0, "STOP": 1, "REFUSED": 2}[result.disposition]


if __name__ == "__main__":
    raise SystemExit(run_clean_successor())
