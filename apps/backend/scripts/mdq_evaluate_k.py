"""Evaluate MDQ-001 K-criteria over frozen partitions — admissibility first, always.

    python scripts/mdq_evaluate_k.py --root /opt/workbench/data/mdq_capture \
        --session 2026-08-19 --session 2026-08-20 --close 2026-08-19T20:00:00Z

Read-only. It opens frozen partitions, adjudicates each session under section 7.1, and computes K
values only for the sessions that passed.

⛔ **A session that fails admissibility is reported and EXCLUDED, never silently dropped and never
folded into the grid.** Quietly skipping it would shrink the corpus without saying so, which reads in
a summary as a smaller sample rather than as excluded evidence.

⚠ `--diagnostic` computes without tokens for development. Its output is labelled `evidentiary: false`
and is not a governed K-value. There is deliberately no flag that makes a diagnostic evidentiary.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.research.mdq_eval.gate import NotAdmissible, require_admissible  # noqa: E402
from app.research.mdq_eval.k1_materiality import evaluate_k1  # noqa: E402
from app.research.mdq_eval.k3_completeness import evaluate_k3  # noqa: E402
from app.research.mdq_eval.source_identity import (  # noqa: E402
    SourceIdentityRefused,
    measure_source_identity,
    verify_governed_source_identity,
)


def _parse_close(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root", required=True, help="capture root holding <feed>/<session>/ partitions"
    )
    ap.add_argument("--session", action="append", required=True, help="YYYY-MM-DD; repeatable")
    ap.add_argument(
        "--close",
        action="append",
        default=[],
        help="session close, ISO-8601, positionally matched to --session",
    )
    ap.add_argument(
        "--diagnostic",
        action="store_true",
        help="compute WITHOUT admissibility tokens; output is NOT evidence",
    )
    ap.add_argument("--out", default=None, help="write the record here as JSON")
    args = ap.parse_args(argv)

    sessions = [date.fromisoformat(s) for s in args.session]
    closes = [_parse_close(c) for c in args.close] + [None] * (len(sessions) - len(args.close))

    admitted: list[date] = []
    tokens = []
    admissibility: list[dict] = []

    # B2 - the source identity is MEASURED by this code, never asserted by the caller.
    if args.diagnostic:
        admitted = sessions
        code_identity = {
            "mode": "DIAGNOSTIC",
            "measured": measure_source_identity().as_dict(),
            "source_identity_verified": False,
        }
        print("DIAGNOSTIC MODE - results are NOT governed K-values", file=sys.stderr)
    else:
        try:
            code_identity = {"mode": "GOVERNED", **verify_governed_source_identity()}
        except SourceIdentityRefused as exc:
            # Fail closed BEFORE any partition is read: a governed run that cannot establish what
            # code it is must not proceed to produce something that looks like a K value.
            print(f"REFUSED: {exc}", file=sys.stderr)
            print(
                json.dumps(
                    {
                        "root": str(Path(args.root).resolve()),
                        "mode": "GOVERNED",
                        "code_identity": {
                            "source_identity_verified": False,
                            "refusal": str(exc),
                            "measured": measure_source_identity().as_dict(),
                        },
                        "results": [],
                        "note": "source identity refused; nothing was computed",
                    },
                    indent=2,
                    default=str,
                )
            )
            return 3
        for session, close in zip(sessions, closes, strict=True):
            try:
                token, report = require_admissible(args.root, session, session_close_utc=close)
            except NotAdmissible as exc:
                # Reported, not swallowed: an excluded session is a fact about the corpus.
                admissibility.append(
                    {"session": session.isoformat(), "admitted": False, "reason": str(exc)}
                )
                print(f"EXCLUDED {session}: not admissible under section 7.1", file=sys.stderr)
                continue
            admitted.append(session)
            tokens.append(token)
            admissibility.append(
                {
                    "session": session.isoformat(),
                    "admitted": True,
                    "verdict": report.verdict,
                    # Three distinct claims; never collapse them into one "digest".
                    "adjudication_instance_digest": token.adjudication_instance_digest,
                    "input_partition_identity": token.input_partition_identity,
                }
            )

    if not admitted:
        print("no admissible session remains; no K-value computed", file=sys.stderr)
        record = {
            "root": str(Path(args.root).resolve()),
            "mode": code_identity["mode"],
            "code_identity": code_identity,
            "admissibility": admissibility,
            "results": [],
            "note": "no admissible session; nothing was computed",
        }
        print(json.dumps(record, indent=2, default=str))
        return 2

    kwargs = {"diagnostic": True} if args.diagnostic else {"tokens": tokens}
    results = [
        evaluate_k3(args.root, admitted, **kwargs).as_dict(),  # type: ignore[arg-type]
        evaluate_k1(args.root, admitted, **kwargs).as_dict(),  # type: ignore[arg-type]
    ]
    record = {
        "schema": "mdq-k-verdict/1",
        "mode": code_identity["mode"],
        "code_identity": code_identity,
        "root": str(Path(args.root).resolve()),
        "sessions_requested": [s.isoformat() for s in sessions],
        "sessions_evaluated": [s.isoformat() for s in admitted],
        "admissibility": admissibility,
        "results": results,
    }
    payload = json.dumps(record, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
