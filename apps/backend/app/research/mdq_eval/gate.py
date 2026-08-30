"""The §7.1 admissibility gate — the only place an `AdmissibilityToken` is minted.

Every governed K-value must be downstream of an admissibility decision that actually passed. This
module is the single point where that decision is turned into a capability, so there is exactly one
place to audit and exactly one place that could ever be wrong.

⛔ **UNDETERMINED is not a pass.** The §7.1 adjudicator has three verdicts, and only ADMISSIBLE mints
a token. Treating UNDETERMINED as admissible would convert "we could not tell" into evidence, which is
worse than either a clean pass or a clean refusal because it looks like a pass in every summary.

⛔ **The evidentiary path takes no threshold parameters.** `require_admissible` deliberately has no
``**kwargs``. `assess_partition` accepts `min_completeness`, `max_gap_minutes`,
`cadence_tolerance_seconds`, `cadence_seconds`, `sampler_start_et`, `signoff_date`, `feeds`,
`frozen_universe` and `pins` — every one of which weakens the frozen contract. Forwarding arbitrary
kwargs meant a *library* caller could relax every threshold and still receive a genuine token, so the
evidentiary boundary was enforced only by the CLI's restraint rather than by the gate. Weakening a
threshold on this path is now a `TypeError` at the call site, not a policy question.

Diagnostic experimentation lives in `assess_diagnostic`, which returns a report and **cannot reach**
`_mint_token`. There is deliberately no function that converts a diagnostic result into a token: a
validation blacklist of forbidden kwargs would have to be kept correct forever, whereas an absent
code path cannot be got wrong.

Three identities are kept distinct because they answer three different questions:

``input_partition_identity``      deterministic — *which bytes were adjudicated*
``adjudication_instance_digest``  run-specific — *which adjudication run this was*
source identity                   *which code computed it* (recorded by the calculator)

⚠ They must never be collapsed into one field. The run digest hashes the report, which contains
`generated_at`, so it changes on every run over identical bytes. It was previously named
`admissibility_digest`, which reads as a content hash of the partition and is not one. The
**algorithm and bytes are unchanged**; only the name and the documented meaning are corrected.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.research.capture.admissibility import AdmissibilityReport, Verdict, assess_partition
from app.research.capture.store import FEEDS
from app.research.mdq_eval.authority import (
    APPROVED_COLLECTOR_IDENTITY,
    APPROVED_COLLECTOR_VERSIONS,
    FROZEN_PROVENANCE,
    HISTORICAL_BINDING_UNAVAILABLE,
    QUARANTINE_LABEL,
    REQUIRED_PROVENANCE_KEYS,
    invariance_record,
)
from app.research.mdq_eval.results import (
    AdmissibilityToken,
    ValidatedScope,
    _mint_scope,
    _mint_token,
)


class NotAdmissible(RuntimeError):
    """The partition did not pass §7.1, so no evidentiary K-value may be computed over it.

    Raised rather than returned: a caller that wanted evidence and got an inadmissible partition has
    asked for something that does not exist, and silently degrading to a diagnostic would hide that.
    Callers who genuinely want a diagnostic ask for one explicitly.
    """


def _adjudication_instance_digest(report: AdmissibilityReport) -> str:
    """Identifies THIS adjudication run, so a token names the decision it came from.

    ⚠ Not a content hash of the partition. `report.as_dict()` carries `generated_at`, so two runs
    over byte-identical inputs produce different values. Use `input_partition_identity` when the
    question is "which bytes". Algorithm deliberately unchanged from the previous
    `admissibility_digest` so existing records stay comparable.
    """
    payload = json.dumps(report.as_dict(), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def input_partition_identity(root: Path | str, session: date) -> str:
    """Deterministic identity of the adjudicated bytes, across both feeds.

    Built only from the frozen manifests' per-file entries (path, sha256, bytes) — never from
    `frozen_at` or any other run-local field — so re-deriving it over an unchanged partition always
    yields the same value. This is the field that can answer "did two runs read the same data".
    """
    entries: list[dict[str, Any]] = []
    for feed in FEEDS:
        mpath = Path(root) / feed / session.isoformat() / "manifest.json"
        if not mpath.exists():
            raise NotAdmissible(
                f"no frozen manifest for {feed}/{session}; a partition without a manifest is not "
                f"frozen and cannot be given a deterministic input identity"
            )
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        for f in sorted(manifest.get("files", []), key=lambda e: str(e.get("path"))):
            entries.append(
                {
                    "feed": feed,
                    "path": f.get("path"),
                    "sha256": f.get("sha256"),
                    "bytes": f.get("bytes"),
                }
            )
    payload = json.dumps(
        {
            "schema": "mdq-input-partition-identity/1",
            "session": session.isoformat(),
            "entries": entries,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_manifest_native_identity(root: Path | str, session: date) -> dict[str, Any]:
    """**B1a** — check what the frozen partition can itself mechanically prove.

    Only fields the manifests actually carry are checked: `collector_version` against the frozen
    authority, and the provenance keys the collector demonstrably wrote. A missing or mismatched
    required field fails closed.

    ⛔ This deliberately does **not** attempt a per-partition source-tuple check. The manifests record
    no source commit and no collector blob hashes, so that binding cannot be reconstructed — see
    `authority` for why claiming it would be fictitious.
    """
    problems: list[str] = []
    version_ok = True
    provenance_ok = True

    for feed in FEEDS:
        mpath = Path(root) / feed / session.isoformat() / "manifest.json"
        if not mpath.exists():
            problems.append(f"{feed}: no manifest")
            version_ok = False
            provenance_ok = False
            continue
        m = json.loads(mpath.read_text(encoding="utf-8"))

        if m.get("collector_version") not in APPROVED_COLLECTOR_VERSIONS:
            version_ok = False
            problems.append(
                f"{feed}: collector_version {m.get('collector_version')!r} is not the approved "
                f"{list(APPROVED_COLLECTOR_VERSIONS)}"
            )
        if m.get("label") == QUARANTINE_LABEL:
            provenance_ok = False
            problems.append(
                f"{feed}: labelled {QUARANTINE_LABEL}; quarantined from the governed corpus"
            )
        for key in REQUIRED_PROVENANCE_KEYS:
            if key not in m:
                provenance_ok = False
                problems.append(
                    f"{feed}: required provenance field {key!r} absent from the manifest"
                )
        for key, want in FROZEN_PROVENANCE.items():
            if key in m and m[key] != want:
                provenance_ok = False
                problems.append(
                    f"{feed}: provenance {key!r} is {m[key]!r}, frozen value is {want!r}"
                )

    return {
        "manifest_collector_version_verified": version_ok,
        "manifest_provenance_verified": provenance_ok,
        "collector_implementation_invariance_verified": True,
        "collector_implementation_invariance": invariance_record(),
        "per_partition_full_source_tuple_verified": False,
        "per_partition_full_source_tuple_status": HISTORICAL_BINDING_UNAVAILABLE,
        "approved_collector_identity": APPROVED_COLLECTOR_IDENTITY.as_dict(),
        "problems": problems,
    }


def require_admissible(
    root: Path | str,
    session: date,
    *,
    session_close_utc: datetime | None,
) -> tuple[AdmissibilityToken, AdmissibilityReport]:
    """Adjudicate one session under the FROZEN contract and mint a token iff it is ADMISSIBLE.

    ⛔ No threshold, feed, universe, pin, or signoff parameter is accepted. Every such value comes
    from the frozen authority or from `assess_partition`'s own frozen defaults. A caller who wants to
    vary one is asking for a diagnostic and must say so — see `assess_diagnostic`.

    Returns the report alongside the token deliberately: the caller should be able to record *why*
    the partition was admissible, not merely that something said so.
    """
    native = verify_manifest_native_identity(root, session)
    if not (
        native["manifest_collector_version_verified"] and native["manifest_provenance_verified"]
    ):
        raise NotAdmissible(
            f"{session} fails manifest-native identity, so no evidentiary K-value may be computed "
            f"over it: {native['problems']}"
        )

    report = assess_partition(
        Path(root),
        session,
        session_close_utc=session_close_utc,
        approved_collector_versions=APPROVED_COLLECTOR_VERSIONS,
    )
    if report.verdict is not Verdict.ADMISSIBLE:
        not_passing = report.as_dict().get("not_passing", [])
        raise NotAdmissible(
            f"{session} is {report.verdict} under the section 7.1 admissibility check, so no "
            f"evidentiary K-value may be computed over it. Non-passing conditions: "
            f"{json.dumps(not_passing, default=str)}"
        )
    token = _mint_token(
        root=str(Path(root).resolve()),
        session=session,
        verdict=str(report.verdict),
        assessed_at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        adjudication_instance_digest=_adjudication_instance_digest(report),
        input_partition_identity=input_partition_identity(root, session),
    )
    return token, report


def assess_diagnostic(
    root: Path | str,
    session: date,
    *,
    session_close_utc: datetime | None,
    **overrides: Any,
) -> AdmissibilityReport:
    """Adjudicate with caller-supplied overrides, for investigation only.

    ⛔ Returns a report and nothing else. It does not mint, cannot mint, and there is deliberately no
    function anywhere that promotes its result into an `AdmissibilityToken`. That structural gap is
    the control.
    """
    return assess_partition(Path(root), session, session_close_utc=session_close_utc, **overrides)


def validate_tokens(
    root: Path | str, sessions: Iterable[date], tokens: Iterable[AdmissibilityToken]
) -> ValidatedScope:
    """Check that the supplied tokens cover exactly the sessions being evaluated, under this root.

    Returns a `ValidatedScope` capability, not the tokens: `KResult` derives `evidentiary` from a
    validated scope, because possession of a token proves nothing about whether it was ever checked
    against the sessions a result reports.

    ⚠ This is not ceremony. Without it, a token minted for an admissible day could be passed
    alongside a *different*, inadmissible day and the result would still be stamped evidentiary — the
    laundering path the token was introduced to close.
    """
    want = {s for s in sessions}
    resolved_root = str(Path(root).resolve())
    by_session: dict[date, AdmissibilityToken] = {}
    for t in tokens:
        if not isinstance(t, AdmissibilityToken):
            raise TypeError(f"not an AdmissibilityToken: {t!r}")
        if t.root != resolved_root:
            raise NotAdmissible(
                f"token for {t.session} was minted under root {t.root}, but evaluation root is "
                f"{resolved_root}; a token does not travel between corpora"
            )
        by_session[t.session] = t

    missing = sorted(s.isoformat() for s in want - set(by_session))
    if missing:
        raise NotAdmissible(
            f"no admissibility token for session(s) {missing}; every evaluated session must have "
            f"passed section 7.1 before its data becomes evidence"
        )
    extra = sorted(s.isoformat() for s in set(by_session) - want)
    if extra:
        raise NotAdmissible(
            f"token(s) supplied for session(s) {extra} that are not being evaluated; refusing rather "
            f"than silently ignoring evidence of a scope mismatch"
        )
    ordered = tuple(sorted(want))
    return _mint_scope(
        root=resolved_root,
        sessions=tuple(s.isoformat() for s in ordered),
        tokens=tuple(by_session[s] for s in ordered),
    )
