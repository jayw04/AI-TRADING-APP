"""Fail-closed checker for RELAYED sign-off decisions (RANGE-002 owner instruction rev. 3, Lane K).

    python -I scripts/research/range002/relayed_decision_check.py record.json --repo-root . [--pr740-merged]

Some reviewers send decisions to the owner outside GitHub (WeChat, email); the owner commits
them. This checker decides whether such a record may count, and it never infers:

* the original message evidence file must exist inside the repository and match its SHA-256;
* the verbatim text must be PRESENT in that evidence (a record whose only content is
  owner-authored text is never GENUINE; for the validator role that is a HARD FAIL);
* the artifact SHA reviewed must equal the artifact's CURRENT SHA-256, else STALE;
* the decision field must agree with the conclusion in the verbatim text; a conflict or an
  undetectable conclusion is flagged for the owner, never resolved by guessing;
* nothing counts as GENUINE until PR #740 (all-pairs distinct sign-off check) is merged on
  main: a record that passes everything else is ``VERIFIED_PENDING_740``.

Standard library only; reads the record and the two files it names; makes no network call.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RECORD_TYPE = "range002.relayed_decision.v1"
ROLES = ("validator", "trading_expert", "risk_reviewer", "exit_reviewer", "owner_delegate")
DECISIONS = ("APPROVE", "REJECT", "CONDITIONAL")
EVIDENCE_KINDS = ("original_message_export", "screenshot", "owner_authored_summary")
TRANSLATION_LABEL = "owner translation"

GENUINE = "GENUINE"
VERIFIED_PENDING_740 = "VERIFIED_PENDING_740"
STALE = "STALE"
NEEDS_OWNER = "NEEDS_OWNER"
OWNER_AUTHORED_ONLY = "OWNER_AUTHORED_ONLY"
INVALID = "INVALID"

REQUIRED_TEXT = (
    "person",
    "role",
    "decision",
    "artifact_path",
    "artifact_sha256",
    "evidence_path",
    "evidence_sha256",
    "evidence_kind",
    "verbatim_text",
    "date_received",
    "channel",
    "relayed_by",
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Result:
    status: str
    reasons: tuple[str, ...]
    hard_fail: bool
    counts_as_genuine: bool


def detect_conclusions(text: str) -> set[str]:
    """Conclusions stated in ``text``: a set of APPROVE / REJECT / CONDITIONAL.

    Longer Chinese forms are consumed first so that 有条件同意 and 不同意 are never also read as
    plain 同意. English forms are handled the same way. An empty set means none was detected."""
    t = unicodedata.normalize("NFKC", text).lower()
    found: set[str] = set()
    for pat, label in (
        (r"有条件同意", "CONDITIONAL"),
        (r"不同意", "REJECT"),
        (r"approve with conditions|conditionally approve|conditional approval", "CONDITIONAL"),
        (r"do not approve|don't approve|disapprove|reject", "REJECT"),
    ):
        if re.search(pat, t):
            found.add(label)
            t = re.sub(pat, " ", t)
    if re.search(r"同意|\bapprove[sd]?\b|\bagree[sd]?\b", t):
        found.add("APPROVE")
    return found


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _inside(root: Path, rel: str) -> Path | None:
    try:
        p = (root / rel).resolve()
        p.relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    return p


def evaluate(record: Any, *, repo_root: Path, pr740_merged: bool) -> Result:
    def done(status: str, reasons: list[str], validator: bool = False) -> Result:
        hard = validator and status in (INVALID, OWNER_AUTHORED_ONLY, NEEDS_OWNER)
        return Result(status, tuple(reasons), hard, status == GENUINE)

    if not isinstance(record, dict) or record.get("record_type") != RECORD_TYPE:
        return done(INVALID, [f"record_type must be {RECORD_TYPE!r}"])
    is_validator = record.get("role") == "validator"
    bad: list[str] = []
    for f in REQUIRED_TEXT:
        v = record.get(f)
        if not isinstance(v, str) or not v.strip():
            bad.append(f"{f} is blank or missing")
    if record.get("role") not in ROLES:
        bad.append(f"role must be one of {ROLES}")
    if record.get("decision") not in DECISIONS:
        bad.append(f"decision must be one of {DECISIONS}")
    if record.get("evidence_kind") not in EVIDENCE_KINDS:
        bad.append(f"evidence_kind must be one of {EVIDENCE_KINDS}")
    if record.get("relayed_by") != "owner":
        bad.append("relayed_by must be 'owner'")
    for f in ("artifact_sha256", "evidence_sha256"):
        if isinstance(record.get(f), str) and not _HEX64.match(record[f]):
            bad.append(f"{f} must be 64 lowercase hex")
    if record.get("decision") == "CONDITIONAL":
        c = record.get("conditions")
        if not isinstance(c, list) or not c or not all(isinstance(x, str) and x.strip() for x in c):
            bad.append("CONDITIONAL requires a non-empty list of conditions")
    tr = record.get("translation")
    if tr is not None and not (
        isinstance(tr, dict)
        and tr.get("label") == TRANSLATION_LABEL
        and isinstance(tr.get("text"), str)
        and tr["text"].strip()
    ):
        bad.append(f"translation must be {{'label': {TRANSLATION_LABEL!r}, 'text': ...}}")
    if bad:
        return done(INVALID, bad, is_validator)

    # evidence: present, inside the repo, hash matches
    ev = _inside(repo_root, record["evidence_path"])
    if ev is None or not ev.is_file():
        return done(INVALID, ["evidence file is missing or outside the repository"], is_validator)
    if _sha256(ev) != record["evidence_sha256"]:
        return done(INVALID, ["evidence file hash does not match evidence_sha256"], is_validator)

    # owner-authored content is never GENUINE
    if record["evidence_kind"] == "owner_authored_summary":
        return done(
            OWNER_AUTHORED_ONLY,
            ["the evidence is an owner-authored summary, not the original message"],
            is_validator,
        )
    try:
        evidence_text = ev.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return done(
            NEEDS_OWNER,
            ["evidence is binary; the verbatim text cannot be machine-verified against it"],
            is_validator,
        )
    if _norm(record["verbatim_text"]) not in _norm(evidence_text):
        return done(
            OWNER_AUTHORED_ONLY,
            ["the verbatim text does not appear in the hashed original message"],
            is_validator,
        )

    # artifact currency
    art = _inside(repo_root, record["artifact_path"])
    if art is None or not art.is_file():
        return done(INVALID, ["artifact file is missing or outside the repository"], is_validator)
    current = _sha256(art)
    if current != record["artifact_sha256"]:
        return done(
            STALE,
            [f"reviewed artifact SHA differs from the current SHA ({current[:12]}...)"],
            is_validator,
        )

    # the decision field against the stated conclusion: flag, never infer
    concl = detect_conclusions(record["verbatim_text"])
    if not concl:
        return done(
            NEEDS_OWNER,
            ["no explicit conclusion (同意 / 不同意 / 有条件同意) in the text"],
            is_validator,
        )
    if concl != {record["decision"]}:
        return done(
            NEEDS_OWNER,
            [
                f"decision field {record['decision']} conflicts with the stated conclusion {sorted(concl)}"
            ],
            is_validator,
        )

    if not pr740_merged:
        return done(VERIFIED_PENDING_740, ["all checks passed; PR #740 is not merged on main"])
    return done(GENUINE, [])


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    root = Path(".")
    if "--repo-root" in argv:
        root = Path(argv[argv.index("--repo-root") + 1])
        args = [a for a in args if a != argv[argv.index("--repo-root") + 1]]
    if len(args) != 1:
        print(__doc__)
        return 2
    try:
        record = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"{INVALID}: cannot read record: {exc}")
        return 1
    r = evaluate(record, repo_root=root, pr740_merged="--pr740-merged" in flags)
    print(r.status + (" (HARD FAIL: validator)" if r.hard_fail else ""))
    for reason in r.reasons:
        print(f"  - {reason}")
    return 0 if r.counts_as_genuine else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
