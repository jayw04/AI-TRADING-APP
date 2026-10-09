#!/usr/bin/env python3
"""RANGE-002 freeze tool (Implementation Plan v0.5 WP0.3).

    freeze_spec.py --emit-skeleton PATH      write the all-null Appendix A draft
    freeze_spec.py DRAFT --out FROZEN        validate, refuse unless complete, write frozen spec
    freeze_spec.py --verify FROZEN           re-load a frozen spec and report its status

Freezing REFUSES (exit 2) unless every P0 field is set AND the human sign-off fields (owner,
trading_expert, independent_validator, date) are already present in the draft. This tool never
fabricates a sign-off and never picks a value for an open decision (rule R9). It computes
``signoff.spec_sha256`` itself, never overwrites an existing frozen file, and does no data access.
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

from app.research.range002.spec.loader import (  # noqa: E402
    SpecHashMismatchError,
    SpecSchemaError,
    load_draft,
    load_frozen,
    spec_sha256,
)
from app.research.range002.spec.schema import (  # noqa: E402
    FrozenSpec,
    SignoffMissingError,
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


def freeze(draft_path: Path, out_path: Path) -> str:
    """Return the spec_sha256 of the written frozen file, or raise."""
    if out_path.is_symlink() or out_path.exists():
        raise FileExistsError(
            f"{out_path} exists; a frozen spec is immutable and never overwritten"
        )
    spec = load_draft(draft_path)
    FrozenSpec.from_draft(spec)  # UnsetP0FieldsError naming every unset P0 field
    missing = spec.missing_signoff_fields()
    if missing:
        raise SignoffMissingError(missing)
    signed_on = spec.signoff.date
    if signed_on is not None and signed_on > date.today():
        raise SpecSchemaError([f"signoff.date: {signed_on} is in the future"])
    digest = spec_sha256(spec)
    preset = spec.signoff.spec_sha256
    if preset is not None and preset != digest:
        raise SpecSchemaError(
            [f"signoff.spec_sha256: draft carries {preset} but content hashes to {digest}"]
        )
    payload = spec.model_dump(mode="json")
    payload["signoff"]["spec_sha256"] = digest
    _write_new(out_path, _dump(payload))
    try:
        view = load_frozen(out_path)  # round-trip: what we wrote must load, signed, at this hash
        if not view.is_signed or view.spec_sha256 != digest:
            raise RuntimeError("freeze round-trip failed; frozen file removed")
    except BaseException:
        # Whatever went wrong, never leave a frozen file that did not round-trip.
        out_path.unlink(missing_ok=True)
        raise
    return digest


def main(argv: list[str] | None = None) -> int:
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
            print(f"spec_sha256={view.spec_sha256} is_signed={view.is_signed}")
            for reason in view.unusable_reasons:
                print(f"UNUSABLE: {reason}")
            return EXIT_OK if view.is_signed else EXIT_REFUSED
        if not args.draft or not args.out:
            ap.error("DRAFT and --out are required to freeze")
        digest = freeze(args.draft, args.out)
        print(f"frozen {args.out}\nspec_sha256={digest}")
        return EXIT_OK
    except (
        UnsetP0FieldsError,
        SignoffMissingError,
        SpecSchemaError,
        SpecHashMismatchError,
        FileExistsError,
    ) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
