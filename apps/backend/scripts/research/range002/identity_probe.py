"""RANGE-002 identity probe harness (BUILD only; never executed on real data from this repo state).

Question (pre-registered in RANGE-002_Identity_Probe_Preregistration_v1.json): does a vendor
response (TICKERS rows plus ACTIONS rows for a probe sample) actually contain the historical
identity intervals needed to reconstruct point-in-time membership?

    RETAIN_RAW_INTERVALS  - the response demonstrably carries the intervals; retain raw rows
    SCOPE_AMENDMENT       - it does not, or the sample cannot show it; fail closed

Properties, each pinned by a test:
* the labels and the decision rule are READ FROM the pre-registration file, whose SHA-256 is
  pinned below; a changed file refuses to run (a new version file is required instead);
* the outcome is binary and fails closed: an empty, small, vacuous or ambiguous response can
  only give SCOPE_AMENDMENT;
* output carries labels and counts only, never prices, returns or volumes;
* the command-line entry refuses unless an explicit owner authorization record is supplied, so
  the probe cannot be run on real data by accident.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

PREREGISTRATION_SHA256 = "116a0601ff29374a38c4290cc355c506374c7137d420c908a15b76e91e3a17fc"
PREREGISTRATION_PATH = (
    Path(__file__).resolve().parents[5]
    / "docs/implementation/evidence/range_002/RANGE-002_Identity_Probe_Preregistration_v1.json"
)
FOREVER = date.max


class PreregistrationError(RuntimeError):
    """The pre-registration is missing or does not match its pinned digest."""


class ProbeInputError(ValueError):
    """The probe input is structurally unusable (not a tickers/actions mapping of lists)."""


@dataclass(frozen=True)
class Preregistration:
    labels: tuple[str, ...]
    decision_labels: tuple[str, ...]
    blocking: frozenset[str]
    identity_change: frozenset[str]
    min_issuers: int
    min_change_cases: int
    gap_days: int
    change_substring: str


def load_preregistration(path: Path | None = None) -> Preregistration:
    p = path or PREREGISTRATION_PATH
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise PreregistrationError(f"cannot read pre-registration: {exc}") from exc
    if hashlib.sha256(raw).hexdigest() != PREREGISTRATION_SHA256:
        raise PreregistrationError("pre-registration digest differs from the pinned value")
    d = json.loads(raw)
    prm = d["parameters"]
    return Preregistration(
        tuple(d["per_issuer_labels"]),
        tuple(d["decision_labels"]),
        frozenset(d["blocking_labels"]),
        frozenset(d["identity_change_labels"]),
        int(prm["min_issuers_in_sample"]),
        int(prm["min_identity_change_cases"]),
        int(prm["gap_days_threshold"]),
        str(prm["change_action_substring"]),
    )


@dataclass(frozen=True)
class Row:
    permaticker: str
    ticker: str
    first: date | None
    last: date | None
    delisted: bool


@dataclass(frozen=True)
class Action:
    day: date
    action: str
    ticker: str
    contraticker: str


def _d(v: Any) -> date | None:
    if v in (None, ""):
        return None
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def parse_input(payload: Any) -> tuple[list[Row], list[Action], list[str]]:
    """Returns (rows, actions, structural_defects). A row that cannot be parsed is reported as a
    defect for its issuer and kept as an INVALID row, never dropped."""
    if not isinstance(payload, dict) or not isinstance(payload.get("tickers"), list):
        raise ProbeInputError("expected {'tickers': [...], 'actions': [...]}")
    rows: list[Row] = []
    defects: list[str] = []
    for r in payload["tickers"]:
        try:
            rows.append(
                Row(
                    str(r.get("permaticker", "")).strip(),
                    str(r.get("ticker", "")).strip(),
                    _d(r.get("firstpricedate")),
                    _d(r.get("lastpricedate")),
                    str(r.get("isdelisted", "")).strip().upper() in ("Y", "TRUE", "1"),
                )
            )
        except (ValueError, AttributeError, TypeError):
            defects.append(f"unparseable row: {str(r)[:60]}")
            rows.append(Row("", "", None, None, False))
    acts: list[Action] = []
    for a in payload.get("actions") or []:
        try:
            acts.append(
                Action(
                    date.fromisoformat(str(a["date"])),
                    str(a.get("action", "")),
                    str(a.get("ticker", "")).strip(),
                    str(a.get("contraticker", "")).strip(),
                )
            )
        except (KeyError, ValueError, TypeError):
            defects.append(f"unparseable action: {str(a)[:60]}")
    return rows, acts, defects


def _end(r: Row) -> date:
    return r.last if r.last is not None else FOREVER


def _overlap(a: Row, b: Row) -> bool:
    assert a.first is not None and b.first is not None
    return a.first <= _end(b) and b.first <= _end(a)


def _valid(r: Row) -> bool:
    if not r.permaticker or not r.ticker or r.first is None:
        return False
    if r.delisted and r.last is None:
        return False
    return r.last is None or r.first <= r.last


def classify(rows: list[Row], actions: list[Action], pre: Preregistration) -> dict[str, str]:
    """One primary label per issuer (permaticker), by the pre-registered precedence."""
    by_issuer: dict[str, list[Row]] = {}
    for r in rows:
        by_issuer.setdefault(r.permaticker or f"<blank-{len(by_issuer)}>", []).append(r)
    by_ticker: dict[str, set[str]] = {}
    for r in rows:
        if r.ticker and r.permaticker:
            by_ticker.setdefault(r.ticker, set()).add(r.permaticker)

    labels: dict[str, str] = {}
    for issuer, rs in by_issuer.items():
        found: set[str] = set()
        if not issuer or issuer.startswith("<blank-") or not all(_valid(r) for r in rs):
            found.add("INVALID_RECORD")
        else:
            tickers = {r.ticker for r in rs}
            ordered = sorted(rs, key=lambda r: (r.first, _end(r)))  # type: ignore[type-var,return-value]
            for i, a in enumerate(ordered):
                for b in ordered[i + 1 :]:
                    if a.ticker != b.ticker and _overlap(a, b):
                        found.add("AMBIGUOUS_MAPPING")
            for t in tickers:
                owners = by_ticker.get(t, set())
                if len(owners) > 1:
                    other_rows = [r for r in rows if r.ticker == t and r.permaticker in owners]
                    if any(
                        x.permaticker != y.permaticker
                        and _valid(x)
                        and _valid(y)
                        and _overlap(x, y)
                        for x in other_rows
                        for y in other_rows
                    ):
                        found.add("AMBIGUOUS_MAPPING")
                    elif all(_valid(x) for x in other_rows):
                        found.add("SUCCESSOR_IDENTITY_RESOLVED")
            change_actions = [
                a
                for a in actions
                if pre.change_substring in a.action.lower().replace(" ", "")
                and (a.ticker in tickers or a.contraticker in tickers)
            ]
            distinct_intervals = {(r.ticker, r.first, r.last) for r in rs}
            if change_actions and len(tickers) < 2:
                found.add("TICKER_CHANGE_CURRENT_ONLY")
            elif len(tickers) >= 2 and len(distinct_intervals) >= 2:
                found.add("TICKER_CHANGE_INTERVALS_PRESENT")
            for a_row, b_row in zip(ordered, ordered[1:], strict=False):
                if a_row.last is None:
                    continue
                gap = (b_row.first - a_row.last).days  # type: ignore[operator]
                if gap > pre.gap_days:
                    inside = any(
                        a_row.last < ac.day < b_row.first  # type: ignore[operator]
                        and (ac.ticker in tickers or ac.contraticker in tickers)
                        for ac in actions
                    )
                    found.add("INTERVAL_GAP_EXPLAINED" if inside else "INTERVAL_GAP_UNEXPLAINED")
            if not found:
                found.add("CLEAN_SINGLE_INTERVAL")
        for label in (
            "INVALID_RECORD",
            "AMBIGUOUS_MAPPING",
            "TICKER_CHANGE_CURRENT_ONLY",
            "INTERVAL_GAP_UNEXPLAINED",
            "INTERVAL_GAP_EXPLAINED",
            "SUCCESSOR_IDENTITY_RESOLVED",
            "TICKER_CHANGE_INTERVALS_PRESENT",
            "CLEAN_SINGLE_INTERVAL",
        ):
            if label in found:
                labels[issuer] = label
                break
    return labels


@dataclass(frozen=True)
class ProbeResult:
    decision: str
    reasons: tuple[str, ...]
    issuers: int
    identity_change_cases: int
    blocking_cases: int
    label_counts: dict[str, int]
    structural_defects: tuple[str, ...]


def run_probe(payload: Any, pre: Preregistration | None = None) -> ProbeResult:
    pre = pre or load_preregistration()
    rows, actions, defects = parse_input(payload)
    labels = classify(rows, actions, pre)
    counts = dict(sorted(Counter(labels.values()).items()))
    unknown = [lab for lab in counts if lab not in pre.labels]
    if unknown:  # a label outside the pre-registered set is a harness defect, never a result
        raise PreregistrationError(f"label(s) outside the pre-registered set: {unknown}")
    blocking = sum(n for lab, n in counts.items() if lab in pre.blocking)
    change = sum(n for lab, n in counts.items() if lab in pre.identity_change)
    reasons: list[str] = []
    if defects:
        reasons.append("STRUCTURAL_DEFECTS")
    if len(labels) < pre.min_issuers:
        reasons.append("INSUFFICIENT_SAMPLE")
    if change < pre.min_change_cases:
        reasons.append("TOO_FEW_IDENTITY_CHANGE_CASES")
    if blocking > 0:
        reasons.append("BLOCKING_LABELS_PRESENT")
    decision = "SCOPE_AMENDMENT" if reasons else "RETAIN_RAW_INTERVALS"
    return ProbeResult(
        decision, tuple(reasons), len(labels), change, blocking, counts, tuple(defects)
    )


def main(argv: list[str]) -> int:
    if len(argv) != 5 or argv[1] != "--authorization-record" or argv[3] != "--input":
        print("usage: identity_probe.py --authorization-record RECORD.json --input PROBE.json")
        return 2
    try:
        auth = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        auth = {}
    if not (
        isinstance(auth, dict)
        and auth.get("record_type") == "range002.identity_probe_authorization.v1"
        and auth.get("decision") == "ALLOW"
        and str(auth.get("owner_record_ref", "")).strip()
    ):
        print("REFUSED: no owner authorization record permitting this probe run")
        return 2
    result = run_probe(json.loads(Path(argv[4]).read_text(encoding="utf-8")))
    print(json.dumps(result.__dict__, default=list, sort_keys=True, indent=2))
    return 0 if result.decision == "RETAIN_RAW_INTERVALS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
