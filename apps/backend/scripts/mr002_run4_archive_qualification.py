"""MR-002 Run-4 archived-record qualification tool (host phase; laptop-reviewed; v1.0a).

CLASSIFICATION: test-only diagnostic QUALIFICATION tooling — NOT registered execution code, NOT
performance analysis, NOT part of any registered run, NOT a checkpoint converter. It proves, on
the immutable archived Run-4 evidence, that the committed schema-2.0 encoding round-trips the
canonical corpus arrays bit-exactly — including every negative zero the v1 ratio encoding lost.

EXECUTION MODEL (v1.0a): the tool is mounted SEPARATELY from the implementation checkout and
executed as a standalone file —
    /work    clean detached implementation checkout at the pinned commit (imports resolve here
             via PYTHONPATH=/work/apps/backend)
    /tools   this reviewed script, mounted read-only
    /archive the immutable Run-4 evidence, mounted read-only
    command: python /tools/mr002_run4_archive_qualification.py --archive /archive --work-root /work

CONTAINMENT (v1.0a): EVERY runtime failure — argument parsing, path/type checks, checkpoint
reading, row reconciliation, corpus-source exceptions, per-record qualification exceptions,
report serialization — lands in EXACTLY ONE bounded JSON document on stdout. Dispositions:
PASS = exit 0, FAIL = exit 1, REFUSED = exit 2. No traceback escapes.

The tool performs no cascade resolution, no population run, no checkpoint write, no resume, no
validation/OOS access, and no performance calculation, and it writes NOTHING anywhere. (The
committed corpus source internally replays the frozen capture path over the DEV window exactly
as the registered runner does; the tool adds no solve of its own.)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

import numpy as np

from app.research.mr002.stage3_cascade import (
    EVIDENCE_SCHEMA_VERSION,
    _exact_hex_list,
    rec_content_hash,
)
from scripts.mr002_stage3_population_runner import (
    _decode_exact_hex,
    production_corpus_source,
    read_checkpoint,
    verify_numerical_evidence_record,
)

# ── frozen gates (the tool REFUSES unless every one holds) ──────────────────────────────────────
PINNED_IMPLEMENTATION_COMMIT = "ecaa262480fb2b81fb0ba7d11b97721b617722bf"
PINNED_CHECKPOINT_SHA256 = "b9b0a94817deb540d768fc5b5909978e22f40f04e40a81e1bd5733a6637b7445"
PINNED_MANIFEST_SHA256 = "1132d3b8a3feeefe8c92107468b488cd31da52ec67df4abd78567d8879c96e40"
PINNED_CORPUS_HASH = "1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b"
REQUIRED_SCHEMA_VERSION = "2.0"
EXPECTED_N_RECORDS = 3895
# run-4 forensic population split (reported cross-check, not a refusal gate)
EXPECTED_FORMERLY_FAILING = 3639
EXPECTED_FORMERLY_CLEAN = 256

REPORT_TYPE = "MR002_RUN4_ARCHIVE_QUALIFICATION"
CHECKPOINT_NAME = "MR002_Stage3_CleanRun_checkpoint.jsonl"
MANIFEST_NAME = "MR002_Stage3_CleanRun_Manifest.json"
COMPONENTS = ("t", "A_ub", "b_ub", "A_eq", "b_eq", "upper")
MAX_SELECTED = 64            # explicit bound — the tool REFUSES rather than silently truncating
MAX_LOCATIONS = 64           # per-component location lists are capped WITH the total recorded
MAX_DETAIL = 500             # every detail string in the report is bounded


class ArchiveQualificationRefused(RuntimeError):
    pass


class _RefusingParser(argparse.ArgumentParser):
    """Parser failures are contained in the single JSON result — never a SystemExit/usage dump."""

    def error(self, message):  # noqa: A003 - argparse contract
        raise ArchiveQualificationRefused(f"ARGUMENT_PARSE:{message}")


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _head_commit(work_root: str) -> str:
    try:
        out = subprocess.run(["git", "-C", work_root, "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=60, check=True)
    except Exception as exc:  # noqa: BLE001 — any failure to PROVE the commit refuses
        raise ArchiveQualificationRefused(f"COMMIT_UNPROVABLE:{type(exc).__name__}") from exc
    return out.stdout.strip()


def _strict_path(path: str, kind: str, expect: str) -> None:
    """v1.0a: strict type + immutability — real dir / real regular file, non-symlink, non-writable."""
    if os.path.islink(path):
        raise ArchiveQualificationRefused(f"ARCHIVE_{kind}_IS_SYMLINK:{path}")
    if not os.path.exists(path):
        raise ArchiveQualificationRefused(f"ARCHIVE_{kind}_MISSING:{path}")
    if expect == "dir" and not os.path.isdir(path):
        raise ArchiveQualificationRefused(f"ARCHIVE_{kind}_NOT_A_DIRECTORY:{path}")
    if expect == "file" and not os.path.isfile(path):
        raise ArchiveQualificationRefused(f"ARCHIVE_{kind}_NOT_A_REGULAR_FILE:{path}")
    if os.access(path, os.W_OK):
        raise ArchiveQualificationRefused(f"ARCHIVE_{kind}_WRITABLE:{path}")


def _bits(a: np.ndarray) -> bytes:
    return np.ascontiguousarray(np.asarray(a, dtype=np.float64)).tobytes()


def _neg_zero_locations(arr: np.ndarray) -> list[int]:
    flat = np.asarray(arr, dtype=np.float64).ravel()
    return [int(i) for i in np.nonzero((flat == 0.0) & np.signbit(flat))[0]]


def run_gates(archive: str, work_root: str) -> dict:
    if EVIDENCE_SCHEMA_VERSION != REQUIRED_SCHEMA_VERSION:
        raise ArchiveQualificationRefused(
            f"SCHEMA_VERSION_MISMATCH:{EVIDENCE_SCHEMA_VERSION}!={REQUIRED_SCHEMA_VERSION}")
    head = _head_commit(work_root)
    if head != PINNED_IMPLEMENTATION_COMMIT:
        raise ArchiveQualificationRefused(
            f"IMPLEMENTATION_COMMIT_MISMATCH:{head}!={PINNED_IMPLEMENTATION_COMMIT}")
    cp = os.path.join(archive, CHECKPOINT_NAME)
    mf = os.path.join(archive, MANIFEST_NAME)
    _strict_path(archive, "DIR", "dir")
    _strict_path(cp, "CHECKPOINT", "file")
    _strict_path(mf, "MANIFEST", "file")
    cp_sha = _sha256_file(cp)
    if cp_sha != PINNED_CHECKPOINT_SHA256:
        raise ArchiveQualificationRefused(f"CHECKPOINT_HASH_MISMATCH:{cp_sha}")
    mf_sha = _sha256_file(mf)
    if mf_sha != PINNED_MANIFEST_SHA256:
        raise ArchiveQualificationRefused(f"MANIFEST_HASH_MISMATCH:{mf_sha}")
    return {"implementation_commit": head, "checkpoint_sha256": cp_sha,
            "manifest_sha256": mf_sha, "schema_version": EVIDENCE_SCHEMA_VERSION,
            "archive_read_only": True, "checkpoint_path": cp}


def _reconcile_rows(state: dict, rows: list) -> dict:
    """v1.0a exact row-identity reconciliation — every mismatch REFUSES with a bounded detail."""
    terminal = state.get("terminal")
    if terminal is None or terminal.get("status") != "COMPLETE":
        raise ArchiveQualificationRefused(
            f"ARCHIVE_TERMINAL_NOT_COMPLETE:{terminal.get('status') if terminal else None}")
    if terminal.get("n_records") != EXPECTED_N_RECORDS:
        raise ArchiveQualificationRefused(
            f"ARCHIVE_TERMINAL_COUNT_MISMATCH:{terminal.get('n_records')}!={EXPECTED_N_RECORDS}")
    rec_list = state.get("records", [])
    if len(rec_list) != EXPECTED_N_RECORDS:
        raise ArchiveQualificationRefused(
            f"ARCHIVE_RECORD_COUNT_MISMATCH:{len(rec_list)}!={EXPECTED_N_RECORDS}")
    ids = [r.get("row_id") for r in rec_list]
    bad = [i for i in ids if not isinstance(i, int)]
    if bad:
        raise ArchiveQualificationRefused(f"ARCHIVE_ROW_ID_INVALID:{bad[:5]}")
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ArchiveQualificationRefused(f"DUPLICATE_ARCHIVED_ROW_IDS:{dupes[:5]}")
    if len(rows) != EXPECTED_N_RECORDS:
        raise ArchiveQualificationRefused(
            f"POPULATION_COUNT_MISMATCH:{len(rows)}!={EXPECTED_N_RECORDS}")
    corpus_ids = {rid for rid, _ in rows}
    if corpus_ids != set(ids):
        missing = sorted(corpus_ids - set(ids))[:5]
        extra = sorted(set(ids) - corpus_ids)[:5]
        raise ArchiveQualificationRefused(
            f"ARCHIVE_CORPUS_ROW_SET_MISMATCH:missing={missing}:extra={extra}")
    return dict(zip(ids, rec_list, strict=True))


def _parse_explicit_rows(spec: str, corpus_ids: set) -> list[int]:
    out = []
    for s in spec.split(","):
        s = s.strip()
        if not s:
            continue
        try:
            rid = int(s)
        except ValueError as exc:
            raise ArchiveQualificationRefused(f"INVALID_ROW_ID:{s[:40]}") from exc
        if rid not in corpus_ids:
            raise ArchiveQualificationRefused(f"INVALID_ROW_ID:{rid}")
        out.append(rid)
    return out


def qualify_record(row_id: int, canon: tuple, archived: dict) -> dict:
    """One record's schema-2 round-trip proof against the canonical arrays."""
    out: dict = {"row_id": row_id}
    canonical_hash = rec_content_hash(canon)
    out["archived_content_hash_equal"] = archived.get("input_content_hash") == canonical_hash
    # committed producer path: the schema-2 input block exactly as numerical_evidence builds it
    input_block = {k: {"shape": list(np.asarray(v, float).shape),
                       "exact_hex": _exact_hex_list(np.asarray(v, float))}
                   for k, v in zip(COMPONENTS, canon, strict=True)}
    # committed replay path on a minimal non-qualified diagnostic record
    diagnostic = {"evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
                  "input_content_hash": canonical_hash,
                  "input": input_block, "class": "archive_diagnostic"}
    replay_defect = verify_numerical_evidence_record(diagnostic)
    out["schema2_replay_defect"] = replay_defect
    comps = {}
    bit_equal = {}
    neg_zero = {}
    for k, arr in zip(COMPONENTS, canon, strict=True):
        decoded = _decode_exact_hex(input_block[k]["exact_hex"])
        if isinstance(decoded, str):
            bit_equal[k] = f"DECODE_REFUSED:{decoded}"
            continue
        decoded = decoded.reshape(input_block[k]["shape"])
        comps[k] = decoded
        bit_equal[k] = _bits(decoded) == _bits(arr)
        locs = _neg_zero_locations(arr)
        neg_zero[k] = {"count": len(locs), "locations": locs[:MAX_LOCATIONS],
                       "locations_truncated": len(locs) > MAX_LOCATIONS}
    out["uint64_bit_equality"] = bit_equal
    out["negative_zero"] = neg_zero
    out["content_hash_equal"] = (
        len(comps) == len(COMPONENTS)
        and rec_content_hash(tuple(comps[k] for k in COMPONENTS)) == canonical_hash)
    out["pass"] = (replay_defect is None and out["archived_content_hash_equal"]
                   and out["content_hash_equal"]
                   and all(v is True for v in bit_equal.values()))
    return out


def _execute(argv: list[str] | None, corpus_source) -> tuple[dict, int]:
    ap = _RefusingParser(description="MR-002 Run-4 archive qualification (read-only)")
    ap.add_argument("--archive", required=True, help="read-only archive directory")
    ap.add_argument("--work-root", default="/work", help="registered implementation checkout")
    ap.add_argument("--rows", default="", help="additional explicit row ids, comma-separated")
    args = ap.parse_args(argv)

    gates = run_gates(args.archive, args.work_root)
    state = read_checkpoint(gates["checkpoint_path"])
    if state["corruption"] or state["trailing_partial"]:
        raise ArchiveQualificationRefused("ARCHIVE_CHECKPOINT_UNREADABLE")
    rows, corpus_hash, _manifest, _prov = corpus_source()
    if corpus_hash != PINNED_CORPUS_HASH:
        raise ArchiveQualificationRefused(f"CORPUS_HASH_MISMATCH:{corpus_hash}")
    records = _reconcile_rows(state, rows)
    explicit = _parse_explicit_rows(args.rows, {rid for rid, _ in rows})

    # deterministic classification + pattern enumeration over the WHOLE population
    failing, clean, patterns = [], [], {}
    for row_id, canon in rows:
        pattern = tuple(k for k, arr in zip(COMPONENTS, canon, strict=True)
                        if _neg_zero_locations(arr))
        if pattern:
            failing.append(row_id)
            patterns.setdefault(pattern, row_id)          # lowest row id = representative
        else:
            clean.append(row_id)

    selected = sorted({*patterns.values(), *(clean[:1]), *explicit})
    if len(selected) > MAX_SELECTED:
        raise ArchiveQualificationRefused(
            f"SELECTION_EXCEEDS_BOUND:{len(selected)}>{MAX_SELECTED}:n_patterns={len(patterns)}")
    by_id = dict(rows)
    results = []
    for rid in selected:
        try:
            results.append(qualify_record(rid, by_id[rid], records[rid]))
        except Exception as exc:  # noqa: BLE001 — v1.0a: a qualification fault is CONTAINED
            results.append({"row_id": rid, "pass": False,
                            "error": f"{type(exc).__name__}:{str(exc)[:MAX_DETAIL]}"})

    counts_match = (len(failing) == EXPECTED_FORMERLY_FAILING
                    and len(clean) == EXPECTED_FORMERLY_CLEAN)
    all_pass = counts_match and all(r.get("pass") is True for r in results)
    report = {
        "record_type": REPORT_TYPE,
        "version": "1.0a",
        "disposition": "PASS" if all_pass else "FAIL",
        "gates": gates,
        "population": {"n_records": len(rows),
                       "formerly_failing": len(failing), "formerly_clean": len(clean),
                       "expected_failing": EXPECTED_FORMERLY_FAILING,
                       "expected_clean": EXPECTED_FORMERLY_CLEAN,
                       "counts_match_run4_forensics": counts_match},
        "negative_zero_patterns": [{"components": list(p), "representative_row_id": rid}
                                   for p, rid in sorted(patterns.items())],
        "selected_row_ids": selected,
        "records": results,
        "scope": "input arrays only — z/lam are solver outputs and are NOT reconstructable "
                 "without resolution, which this tool must never perform",
    }
    return report, (0 if all_pass else 1)


def main(argv: list[str] | None = None, corpus_source=production_corpus_source) -> int:
    """EVERY outcome — PASS/FAIL/REFUSED, including any unexpected exception — is exactly one
    bounded JSON document on stdout. PASS=0, FAIL=1, REFUSED=2."""
    try:
        report, rc = _execute(argv, corpus_source)
    except ArchiveQualificationRefused as exc:
        report, rc = {"record_type": REPORT_TYPE, "disposition": "REFUSED",
                      "detail": str(exc)[:MAX_DETAIL]}, 2
    except Exception as exc:  # noqa: BLE001 — no traceback may escape (v1.0a containment)
        report, rc = {"record_type": REPORT_TYPE, "disposition": "REFUSED",
                      "detail": f"UNHANDLED:{type(exc).__name__}:{str(exc)[:MAX_DETAIL]}"}, 2
    try:
        out = json.dumps(report, indent=1)
    except Exception as exc:  # noqa: BLE001 — even serialization failure yields bounded JSON
        out = json.dumps({"record_type": REPORT_TYPE, "disposition": "REFUSED",
                          "detail": f"REPORT_SERIALIZATION_FAILED:{type(exc).__name__}"})
        rc = 2
    print(out)
    return rc


if __name__ == "__main__":
    sys.exit(main())
