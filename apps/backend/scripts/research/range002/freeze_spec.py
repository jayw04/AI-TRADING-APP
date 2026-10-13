#!/usr/bin/env python3
"""RANGE-002 freeze tool (Implementation Plan v0.5 WP0.3).

    freeze_spec.py --emit-skeleton PATH      write the all-null Appendix A draft
    freeze_spec.py DRAFT --out FROZEN        validate, refuse unless complete, write frozen spec
    freeze_spec.py --verify FROZEN           re-load a frozen spec and report its status

Freezing REFUSES (exit 2) unless the committed, OWNER-APPROVED governance manifest
(docs/implementation/evidence/range_002/RANGE-002_governance_manifest.json, fixed path) names a
registry genesis id equal to the spec's and pre-registered P3 attempt limits equal to the spec's
(Round 5 N-A; an unset/null manifest refuses), unless every P0 field is set AND the draft already
carries a meeting-decision reference (``decision``): an ``approved`` decision whose scope includes
``run``, whose partitions are named, and whose cited minutes file exists and hashes to
``decision.minutes_sha256``. The weekly meeting minutes are the decision record. This tool never
fabricates a decision reference and never picks a value for an open decision (rule R9). It computes
``decision.spec_sha256`` itself, never overwrites an existing frozen file, and does no data access.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.research.range002.spec import decision as decision_check  # noqa: E402
from app.research.range002.spec.loader import (  # noqa: E402
    SpecHashMismatchError,
    SpecSchemaError,
    load_draft,
    load_frozen,
    spec_sha256,
)
from app.research.range002.spec.manifest import ManifestError, load_manifest  # noqa: E402
from app.research.range002.spec.schema import (  # noqa: E402
    DecisionRefError,
    FrozenSpec,
    UnsetP0FieldsError,
    draft_skeleton,
)

EXIT_OK = 0
EXIT_REFUSED = 2


def _dump(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"


def _write_new(path: Path, text: str) -> None:
    """Create ``path`` exclusively (never overwrite, never follow a symlink)."""
    if path.is_symlink():
        raise FileExistsError(f"{path} is a symlink; refusing to write through it")
    with open(path, "x", encoding="utf-8", newline="\n") as fh:  # O_EXCL: loses a race cleanly
        fh.write(text)


def freeze(draft_path: Path, out_path: Path, *, manifest_path: Path | None = None) -> str:
    """Return the spec_sha256 of the written frozen file, or raise.

    ``manifest_path`` is a TEST seam only; the CLI never exposes it, so production always reads
    the committed governance manifest at its fixed repo-relative path. Freezing is refused unless
    that manifest is owner-approved (non-null genesis) and the spec's registry genesis id and
    P3A/P3B attempt limits equal the manifest's. Level 1 gate: editing the manifest on disk is a
    Level 2 limitation (the committed file is protected by git review, not by this tool).
    """
    if out_path.is_symlink() or out_path.exists():
        raise FileExistsError(
            f"{out_path} exists; a frozen spec is immutable and never overwritten"
        )
    manifest = load_manifest(manifest_path)  # ManifestError subclasses fail closed
    manifest.require_genesis()
    manifest.require_limits()
    spec = load_draft(draft_path)
    FrozenSpec.from_draft(spec)  # UnsetP0FieldsError naming every unset P0 field
    manifest.check_genesis(spec.governance.registry_genesis_id, what="spec")
    manifest.check_limits(spec.p3.max_p3a_attempts, spec.p3.max_p3b_attempts)
    ref = spec.decision
    if ref is None:
        raise DecisionRefError(["decision: no meeting-decision reference in the draft"])
    problems: list[str] = []
    if ref.decision != "approved":
        problems.append(f"decision.decision is {ref.decision!r}; only 'approved' can be frozen")
    if "run" not in ref.scope:
        problems.append("decision.scope lacks 'run'; a RUN spec needs a run-scope decision")
    if ref.decision_date > date.today():
        problems.append(f"decision.decision_date {ref.decision_date} is in the future")
    try:
        decision_check.check_minutes_file(ref.minutes_path, ref.minutes_sha256)
    except decision_check.MinutesError as exc:
        problems.append(f"decision.minutes: {exc}")
    if problems:
        raise DecisionRefError(problems)
    digest = spec_sha256(spec)
    preset = ref.spec_sha256
    if preset is not None and preset != digest:
        raise SpecSchemaError(
            [f"decision.spec_sha256: draft carries {preset} but content hashes to {digest}"]
        )
    payload = spec.model_dump(mode="json")
    payload["decision"]["spec_sha256"] = digest
    if payload.get("profile") is None:  # full profile: frozen file bytes unchanged
        payload.pop("profile", None)
    _write_new(out_path, _dump(payload))
    try:
        view = load_frozen(out_path)  # round-trip: what we wrote must load, decided, at this hash
        if not view.has_run_decision or view.spec_sha256 != digest:
            raise RuntimeError("freeze round-trip failed; frozen file removed")
    except BaseException:
        # Whatever went wrong, never leave a frozen file that did not round-trip.
        out_path.unlink(missing_ok=True)
        raise
    return digest


def main(argv: list[str] | None = None, *, manifest_path: Path | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("draft", nargs="?", type=Path, help="draft spec to freeze")
    ap.add_argument("--out", type=Path, help="frozen spec path to create (must not exist)")
    ap.add_argument("--emit-skeleton", type=Path, metavar="PATH")
    ap.add_argument("--verify", type=Path, metavar="FROZEN")
    args = ap.parse_args(argv)

    try:
        if args.emit_skeleton:
            _write_new(args.emit_skeleton, _dump(draft_skeleton()))
            print(f"wrote all-null draft skeleton: {args.emit_skeleton}")
            return EXIT_OK
        if args.verify:
            view = load_frozen(args.verify)
            print(f"spec_sha256={view.spec_sha256} has_run_decision={view.has_run_decision}")
            for reason in view.unusable_reasons:
                print(f"UNUSABLE: {reason}")
            return EXIT_OK if view.has_run_decision else EXIT_REFUSED
        if not args.draft or not args.out:
            ap.error("DRAFT and --out are required to freeze")
        digest = freeze(args.draft, args.out, manifest_path=manifest_path)
        print(f"frozen {args.out}\nspec_sha256={digest}")
        return EXIT_OK
    except (
        UnsetP0FieldsError,
        DecisionRefError,
        SpecSchemaError,
        SpecHashMismatchError,
        ManifestError,
        FileExistsError,
    ) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
