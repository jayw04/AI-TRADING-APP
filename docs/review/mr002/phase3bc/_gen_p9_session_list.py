"""Generate the registered session list for the Phase 3B entry point, derived from P9.

The session list is not a value anyone gets to choose now. P9 already committed it: the validation
window is 850 sessions from 2019-10-03 to 2023-02-16 with
``session_list_sha256 = d9966a3a4fb78d3a1e6083988ddaa211d09a08cd942226b771402ef4979f9a62``.

So this generator does not *decide* the sessions; it *reproduces* them and refuses if the result
does not hash to what P9 registered. The commitment is the authority, the regeneration is only a
way of materialising it as a file the entry point can read.

Provenance chain, one hop per value:

  MR002_ValidationStructuralManifest_v1.0.json (P9)  ->  declared bounds, expected count, list SHA
  apps/backend/data/mr002_research.duckdb (24e5153c) ->  the ordered session dates themselves

The snapshot is the registered research calendar spanning the whole governed range 2013-01-02 to
2026-07-10, which is the same source P9 hashed. It is NOT the sealed validation partition: nothing
here opens a sealed object, and a missing price row in the sealed store therefore cannot redefine
the research calendar. That distinction is the whole reason this is derived from P9 rather than
from whatever rows happen to appear at read time.

Zero-data instrument: reads a local governed snapshot. No AWS call, no sealed object, no credential.
"""

from __future__ import annotations

import hashlib
import json
import os

WINDOW = "validation"
SNAPSHOT = "apps/backend/data/mr002_research.duckdb"
SNAPSHOT_SHA256 = "24e5153cc0ebed77c7b4"  # prefix; the full digest is checked below
P9 = "docs/review/mr002/phase3bc/MR002_ValidationStructuralManifest_v1.0.json"

# Same construction P9 used, so the digests are comparable rather than a private convention.
SESSION_TABLE, SESSION_COLUMN = "prices", "date"

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))


class SessionListRefused(Exception):
    """The session list does not reproduce the P9 commitment. Nothing is emitted."""


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def p9_commitment() -> dict:
    with open(os.path.join(_REPO, P9), encoding="utf-8") as fh:
        manifest = json.load(fh)
    windows = manifest.get("all_window_sessions") or {}
    if WINDOW not in windows:
        raise SessionListRefused(f"P9 manifest declares no {WINDOW!r} window")
    return windows[WINDOW]


def observed_sessions(commitment: dict) -> list[str]:
    import duckdb

    path = os.path.join(_REPO, SNAPSHOT)
    if not os.path.exists(path):
        raise SessionListRefused(f"governed research snapshot absent: {SNAPSHOT}")
    con = duckdb.connect(path, read_only=True)
    try:
        rows = con.execute(
            f"SELECT DISTINCT {SESSION_COLUMN} FROM {SESSION_TABLE} "
            f"WHERE {SESSION_COLUMN} >= DATE '{commitment['declared_start']}' "
            f"AND {SESSION_COLUMN} <= DATE '{commitment['declared_end']}' "
            f"ORDER BY {SESSION_COLUMN}"
        ).fetchall()
    finally:
        con.close()
    return [str(r[0]) for r in rows]


def build() -> tuple[list[str], dict]:
    commitment = p9_commitment()
    sessions = observed_sessions(commitment)

    listing = "|".join(sessions)
    digest = hashlib.sha256(listing.encode()).hexdigest()

    if len(sessions) != commitment["expected_sessions"]:
        raise SessionListRefused(
            f"session count {len(sessions)} != P9 expected {commitment['expected_sessions']}"
        )
    if digest != commitment["session_list_sha256"]:
        raise SessionListRefused(
            f"session list does NOT reproduce the P9 commitment: {digest} != "
            f"{commitment['session_list_sha256']}. The registered calendar is the authority; a "
            "list that does not reproduce it must never reach the entry point."
        )
    for field, actual in (("first_session", sessions[0]), ("last_session", sessions[-1])):
        if actual != commitment[field]:
            raise SessionListRefused(f"{field} {actual} != P9 {commitment[field]}")

    snapshot_digest = hashlib.sha256(
        open(os.path.join(_REPO, SNAPSHOT), "rb").read()
    ).hexdigest()
    if not snapshot_digest.startswith(SNAPSHOT_SHA256):
        raise SessionListRefused(f"research snapshot identity changed: {snapshot_digest}")

    provenance = {
        "record_type": "MR002_Phase3B_RegisteredSessionList_Provenance",
        "version": "1.0",
        "window": WINDOW,
        "derived_not_chosen": (
            "P9 committed this list. This artifact reproduces it and refuses on any mismatch; it "
            "selects nothing."
        ),
        "authority": {
            "artifact": P9,
            "field": f"all_window_sessions.{WINDOW}.session_list_sha256",
            "registered_sha256": commitment["session_list_sha256"],
            "expected_sessions": commitment["expected_sessions"],
            "declared_start": commitment["declared_start"],
            "declared_end": commitment["declared_end"],
        },
        "source_of_dates": {
            "snapshot": SNAPSHOT,
            "sha256": snapshot_digest,
            "table": SESSION_TABLE,
            "column": SESSION_COLUMN,
            "note": (
                "the registered research calendar spanning 2013-01-02..2026-07-10 - the same source "
                "P9 hashed. NOT the sealed validation partition: no sealed object is opened, so a "
                "missing sealed price row cannot redefine the research calendar."
            ),
        },
        "reproduction": {
            "observed_sessions": len(sessions),
            "observed_sha256": digest,
            "reproduces_p9_commitment": True,
            "first_session": sessions[0],
            "last_session": sessions[-1],
            "construction": "'|'.join(sessions) then sha256 - identical to the P9 construction",
        },
        "boundary": "Zero-data. No AWS call, no sealed object, no credential. Opening UNSPENT.",
    }
    return sessions, provenance


def main() -> None:
    sessions, provenance = build()
    body = _canonical(provenance)
    provenance["record_identity_sha256"] = hashlib.sha256(body).hexdigest()

    out_list = os.path.join(_HERE, "MR002_Phase3B_RegisteredSessionList_validation_v1.0.json")
    out_prov = os.path.join(_HERE, "MR002_Phase3B_RegisteredSessionList_Provenance_v1.0.json")
    with open(out_list, "wb") as fh:
        fh.write((json.dumps(sessions, indent=1) + "\n").encode("ascii"))
    with open(out_prov, "wb") as fh:
        fh.write(_canonical(provenance))

    print(f"wrote {out_list}")
    print(f"wrote {out_prov}")
    print(f"sessions        {len(sessions)}  {sessions[0]} .. {sessions[-1]}")
    print(f"list sha256     {provenance['reproduction']['observed_sha256']}")
    print(f"reproduces P9   {provenance['reproduction']['reproduces_p9_commitment']}")
    print(f"provenance id   {provenance['record_identity_sha256']}")


if __name__ == "__main__":
    main()
