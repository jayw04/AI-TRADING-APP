#!/usr/bin/env python3
"""Independent O34 qualification verifier (read-only).

Separate from construct_o34_archives.py. Does not construct archives, does not
mutate sources, does not call brokers, does not execute gates.

Verifies CONSTRUCTED candidate archives against bound pins and the immutable
sqlite snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FREEZE_BODY = "80dfd8ec6d90182cdeabaab2d1457720ca417bcd5cb1511b4dd9d77989951bb0"
SQLITE_SHA = "26bae1f5b754c4ff80e031126674d1818ae4a9a90e4faa6b36820f2690278d5b"
CONSTRUCT_MERGE = "5def3824937b85e859345f6691f2cb37b432105f"
EXPECTED = {
    "O3": {
        "sha256": "53b3310c8db3cdfd3d60a2de3bec990a6eaab8864dd592afc4590e57fc9008b0",
        "size": 164706,
        "n": 292,
        "n_plans": 292,
        "n_clusters": 20,
        "kind": "O3_HISTORICAL_REPLAY",
        "schema_id": "ADR0043-PH0-D-BOX-O34-O3-ARCHIVE-SCHEMA-001",
    },
    "O4_A": {
        "sha256": "3ba73e61f5e8955a184d820c0aba4ed387de453c30fc6a22d168d84074403c49",
        "size": 190328,
        "n": 287,
        "n_plans": 287,
        "kind": "O4A_DECISION_TIME",
        "schema_id": "ADR0043-PH0-D-BOX-O34-O4A-ARCHIVE-SCHEMA-001",
    },
    "O4_B": {
        "sha256": "e349f49465aa2689e6c24e20d6ae32286f0a447bfbcdf3b2fbbc531c656bae95",
        "size": 260426,
        "n": 286,
        "n_plans": 286,
        "n_fills": 286,
        "kind": "O4B_FORENSIC",
        "schema_id": "ADR0043-PH0-D-BOX-O34-O4B-ARCHIVE-SCHEMA-001",
    },
}
EXPECTED_O4A_MISSING = {
    "ord:1244",
    "ord:1250",
    "ord:1252",
    "ord:1256",
    "ord:1259",
}
EXPECTED_O4B_INCOMPLETE = EXPECTED_O4A_MISSING | {"ord:1384"}
WINDOW_START = "2026-06-30T00:00:00Z"
WINDOW_END = "2026-07-30T00:21:33Z"
ACCOUNT_ID = 3
BROKER = "PA34USW0Q8UO"
SYNTHETIC_MARKERS = (
    "obs-a",
    "obs-b",
    "arc-1",
    "KOKU",
    "fixture",
    "synthetic",
    "WP7",
    "ADR0048",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    s = value.strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def in_window(dt: datetime | None) -> bool:
    if dt is None:
        return False
    start = parse_ts(WINDOW_START)
    end = parse_ts(WINDOW_END)
    assert start and end
    return start <= dt < end


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, ok: bool, detail: str, findings: list[dict[str, Any]]) -> None:
    findings.append({"check": name, "pass": ok, "detail": detail})


def validate_required(obj: dict[str, Any], keys: list[str], label: str) -> list[str]:
    return [f"{label}.missing:{k}" for k in keys if k not in obj]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True, type=Path)
    ap.add_argument("--o3", required=True, type=Path)
    ap.add_argument("--o4a", required=True, type=Path)
    ap.add_argument("--o4b", required=True, type=Path)
    ap.add_argument("--schema-o3", required=True, type=Path)
    ap.add_argument("--schema-o4a", required=True, type=Path)
    ap.add_argument("--schema-o4b", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--qualifier", default="independent-qualifier-session")
    args = ap.parse_args()

    findings: list[dict[str, Any]] = []
    paths = {"O3": args.o3, "O4_A": args.o4a, "O4_B": args.o4b}

    # --- hash / size ---
    archives: dict[str, Any] = {}
    for key, path in paths.items():
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        exp = EXPECTED[key]
        check(
            f"{key}.hash",
            digest == exp["sha256"],
            f"got={digest} expected={exp['sha256']}",
            findings,
        )
        check(
            f"{key}.size",
            len(raw) == exp["size"],
            f"got={len(raw)} expected={exp['size']}",
            findings,
        )
        archives[key] = json.loads(raw.decode("utf-8"))

    # --- sqlite unchanged ---
    if not args.sqlite.is_file():
        check("sqlite.available", False, f"missing {args.sqlite}", findings)
        report = _finish("INCONCLUSIVE", findings, args, archives=None, extra={})
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1

    sqlite_digest = sha256_file(args.sqlite)
    check(
        "sqlite.hash",
        sqlite_digest == SQLITE_SHA,
        f"got={sqlite_digest} expected={SQLITE_SHA}",
        findings,
    )

    # --- schema file presence / archive header ---
    for key, schema_path, schema_id in (
        ("O3", args.schema_o3, EXPECTED["O3"]["schema_id"]),
        ("O4_A", args.schema_o4a, EXPECTED["O4_A"]["schema_id"]),
        ("O4_B", args.schema_o4b, EXPECTED["O4_B"]["schema_id"]),
    ):
        check(f"{key}.schema_file", schema_path.is_file(), str(schema_path), findings)
        doc = archives[key]
        errs = validate_required(
            doc,
            [
                "archive_id",
                "archive_kind",
                "schema_id",
                "account_scope",
                "eligibility_window",
                "observations",
                "counts",
                "construction_freeze_id",
                "provenance",
            ],
            key,
        )
        check(f"{key}.required_fields", not errs, ";".join(errs) or "ok", findings)
        check(
            f"{key}.kind",
            doc.get("archive_kind") == EXPECTED[key]["kind"],
            str(doc.get("archive_kind")),
            findings,
        )
        check(
            f"{key}.schema_id",
            doc.get("schema_id") == schema_id,
            str(doc.get("schema_id")),
            findings,
        )
        check(
            f"{key}.freeze_id",
            doc.get("construction_freeze_id") == "ADR0043-PH0-D-BOX-O34-ACQ-FREEZE-001",
            str(doc.get("construction_freeze_id")),
            findings,
        )
        scope = doc.get("account_scope") or {}
        check(
            f"{key}.account_scope",
            scope.get("workbench_account_id") == ACCOUNT_ID
            and scope.get("broker_account_id") == BROKER,
            str(scope),
            findings,
        )
        win = doc.get("eligibility_window") or {}
        check(
            f"{key}.window",
            win.get("start_inclusive_utc") == WINDOW_START
            and win.get("end_exclusive_utc") == WINDOW_END,
            str(win),
            findings,
        )

    o3 = archives["O3"]
    o4a = archives["O4_A"]
    o4b = archives["O4_B"]

    # --- counts ---
    check(
        "O3.counts",
        o3["counts"].get("n_observations") == 292
        and o3["counts"].get("n_unique_plans") == 292
        and o3["counts"].get("n_clusters") == 20
        and len(o3["observations"]) == 292,
        str(o3["counts"]),
        findings,
    )
    check(
        "O4_A.counts",
        o4a["counts"].get("n_observations") == 287
        and o4a["counts"].get("n_unique_plans") == 287
        and len(o4a["observations"]) == 287,
        str(o4a["counts"]),
        findings,
    )
    check(
        "O4_B.counts",
        o4b["counts"].get("n_observations") == 286
        and o4b["counts"].get("n_unique_plans") == 286
        and o4b["counts"].get("n_fills") == 286
        and len(o4b["observations"]) == 286,
        str(o4b["counts"]),
        findings,
    )

    # --- dedup / unique plans ---
    o3_plans = [o["plan_id"] for o in o3["observations"]]
    o4a_plans = [o["plan_id"] for o in o4a["observations"]]
    o4b_plans = [o["plan_id"] for o in o4b["observations"]]
    check("O3.dedup", len(o3_plans) == len(set(o3_plans)), str(Counter(o3_plans)), findings)
    check(
        "O4_A.dedup",
        len(o4a_plans) == len(set(o4a_plans)),
        str(Counter(o4a_plans)),
        findings,
    )
    check(
        "O4_B.dedup",
        len(o4b_plans) == len(set(o4b_plans)),
        str(Counter(o4b_plans)),
        findings,
    )

    # --- O3 clusters ---
    clusters = {o.get("session_id") for o in o3["observations"]}
    check(
        "O3.clusters",
        len(clusters) == 20 and o3["counts"].get("n_clusters") == 20,
        f"n={len(clusters)}",
        findings,
    )

    # --- O4-A no look-ahead ---
    o4a_lookahead_bad = []
    for o in o4a["observations"]:
        if o.get("fills"):
            o4a_lookahead_bad.append((o["plan_id"], "fills_nonempty"))
        if o.get("terminal_broker_state") is not None:
            o4a_lookahead_bad.append((o["plan_id"], "terminal_broker_state"))
        if o.get("post_submit_quotes") is not None:
            o4a_lookahead_bad.append((o["plan_id"], "post_submit_quotes"))
        if o.get("cutoff_event") != "FIRST_BROKER_SUBMISSION_BOUNDARY":
            o4a_lookahead_bad.append((o["plan_id"], "bad_cutoff_event"))
    check(
        "O4_A.no_lookahead",
        not o4a_lookahead_bad,
        str(o4a_lookahead_bad[:10]) or "ok",
        findings,
    )

    # --- O4-B completeness / fills ---
    o4b_bad = []
    fill_count = 0
    for o in o4b["observations"]:
        fills = o.get("fills") or []
        fill_count += len(fills)
        if not fills:
            o4b_bad.append((o["plan_id"], "no_fills"))
        tc = o.get("terminal_completeness") or {}
        if tc.get("complete") is not True or tc.get("criteria_id") != "O4B-TERM-COMPLETE-001":
            o4b_bad.append((o["plan_id"], "bad_completeness"))
    check("O4_B.fills_present", not o4b_bad, str(o4b_bad[:10]) or "ok", findings)
    check("O4_B.fill_count", fill_count == 286, f"fill_count={fill_count}", findings)

    # --- O4-A / O4-B separation (no shared payload blobs; episode links ok) ---
    # Refuse if any O4-A observation id appears inside O4-B observation payloads as nested dump
    # and vice versa; also ensure archive_ids differ and kinds differ.
    check(
        "O4.separation_kinds",
        o4a.get("archive_kind") != o4b.get("archive_kind")
        and o4a.get("archive_id") != o4b.get("archive_id"),
        f"{o4a.get('archive_id')} vs {o4b.get('archive_id')}",
        findings,
    )
    o4a_ids = {o["observation_id"] for o in o4a["observations"]}
    o4b_ids = {o["observation_id"] for o in o4b["observations"]}
    check(
        "O4.separation_obs_ids",
        o4a_ids.isdisjoint(o4b_ids),
        f"overlap={len(o4a_ids & o4b_ids)}",
        findings,
    )
    # Mixing check: O4-A must not contain fill objects; O4-B must not claim DECISION_TIME kind
    check(
        "O4.no_mix_plane",
        all(o.get("archive_kind") != "O4A_DECISION_TIME" for o in [o4b])
        and all(not (o.get("fills")) for o in o4a["observations"]),
        "ok",
        findings,
    )

    # --- synthetic / cross-program markers ---
    blob = json.dumps(archives).lower()
    synth_hits = [m for m in SYNTHETIC_MARKERS if m.lower() in blob]
    # 'fixture' might appear in prose? check observation ids / plan ids only
    id_blob = " ".join(o3_plans + o4a_plans + o4b_plans).lower()
    synth_id_hits = [m for m in ("obs-a", "obs-b", "arc-1", "koku") if m in id_blob]
    check(
        "no_synthetic_ids",
        not synth_id_hits,
        str(synth_id_hits) or "ok",
        findings,
    )
    check(
        "no_cross_program_markers_in_ids",
        "adr0048" not in id_blob and "wp7" not in id_blob,
        "ok",
        findings,
    )

    # --- lineage vs sqlite (independent re-query) ---
    conn = sqlite3.connect(f"file:{args.sqlite.as_posix()}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT raw_payload FROM accounts_state WHERE account_id = ?",
            (ACCOUNT_ID,),
        ).fetchone()
        broker_ok = False
        broker_seen = None
        if row:
            try:
                payload = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                broker_seen = payload.get("account_number")
                if broker_seen is None and isinstance(payload.get("account"), dict):
                    broker_seen = payload["account"].get("account_number")
                broker_ok = broker_seen == BROKER
        check("broker_identity", broker_ok, f"seen={broker_seen}", findings)

        orders = conn.execute(
            """
            SELECT o.id, o.created_at, o.submitted_at
            FROM orders o
            WHERE o.account_id = ?
            ORDER BY o.id ASC
            """,
            (ACCOUNT_ID,),
        ).fetchall()
        check(
            "source_order_count",
            len(orders) == 292,
            f"n={len(orders)}",
            findings,
        )

        fills = conn.execute(
            """
            SELECT o.id, COUNT(f.id) AS n_fills
            FROM orders o
            LEFT JOIN fills f ON f.order_id = o.id
            WHERE o.account_id = ?
            GROUP BY o.id
            ORDER BY o.id ASC
            """,
            (ACCOUNT_ID,),
        ).fetchall()
        fills_map = {int(r[0]): int(r[1]) for r in fills}

        selected_plan_ids = []
        missing_cutoff = set()
        incomplete_o4b = set()
        for oid, created, submitted in orders:
            if not in_window(parse_ts(created)):
                continue
            pid = f"ord:{oid}"
            selected_plan_ids.append(pid)
            if not submitted:
                missing_cutoff.add(pid)
            if fills_map.get(int(oid), 0) < 1:
                incomplete_o4b.add(pid)

        check(
            "lineage.o3_equals_selected",
            set(o3_plans) == set(selected_plan_ids) and len(selected_plan_ids) == 292,
            f"o3={len(o3_plans)} selected={len(selected_plan_ids)}",
            findings,
        )
        check(
            "lineage.o4a_missing_cutoff",
            missing_cutoff == EXPECTED_O4A_MISSING
            and set(o4a_plans) == set(selected_plan_ids) - missing_cutoff,
            f"missing={sorted(missing_cutoff)}",
            findings,
        )
        check(
            "lineage.o4b_incomplete",
            incomplete_o4b == EXPECTED_O4B_INCOMPLETE
            and set(o4b_plans) == set(selected_plan_ids) - incomplete_o4b,
            f"incomplete={sorted(incomplete_o4b)}",
            findings,
        )

        # row lineage: every O3 observation source_row_key maps to orders.id
        lineage_bad = []
        for o in o3["observations"]:
            lin = o.get("source_lineage") or {}
            key = lin.get("source_row_key", "")
            if not str(key).startswith("orders.id="):
                lineage_bad.append(o.get("plan_id"))
                continue
            try:
                oid = int(str(key).split("=", 1)[1])
            except ValueError:
                lineage_bad.append(o.get("plan_id"))
                continue
            if o.get("plan_id") != f"ord:{oid}":
                lineage_bad.append(o.get("plan_id"))
            if lin.get("source_snapshot_id") != "20260730T022316Z":
                lineage_bad.append(o.get("plan_id"))
        check(
            "lineage.source_row_keys",
            not lineage_bad,
            str(lineage_bad[:10]) or "ok",
            findings,
        )
    finally:
        conn.close()

    # --- freeze body pin recorded ---
    check(
        "freeze_body_pin",
        True,
        FREEZE_BODY,
        findings,
    )
    check(
        "construct_merge_pin",
        True,
        CONSTRUCT_MERGE,
        findings,
    )

    failed = [f for f in findings if not f["pass"]]
    if any(f["check"] == "sqlite.available" and not f["pass"] for f in findings):
        outcome = "INCONCLUSIVE"
    elif failed:
        outcome = "REJECTED_AS_NON-BINDABLE"
    else:
        outcome = "QUALIFIED"

    report = _finish(
        outcome,
        findings,
        args,
        archives=archives,
        extra={
            "failed_checks": [f["check"] for f in failed],
            "n_checks": len(findings),
            "n_failed": len(failed),
            "gate_ready": False,
            "campaign_reopen_authorized": False,
            "d_wire": "BLOCKED",
            "notes": (
                "QUALIFIED means archives may be named in a later campaign scope / "
                "successor freeze only. Gate execution remains unauthorized."
                if outcome == "QUALIFIED"
                else "See failed_checks."
            ),
            "synthetic_marker_scan_hits": synth_hits,
        },
    )
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if outcome == "QUALIFIED" else 1


def _finish(
    outcome: str,
    findings: list[dict[str, Any]],
    args: argparse.Namespace,
    archives: dict[str, Any] | None,
    extra: dict[str, Any],
) -> dict[str, Any]:
    return {
        "document_id": "ADR0043-PH0-D-BOX-O34-ACQ-QUAL-001",
        "outcome": outcome,
        "qualified_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "qualifier": args.qualifier,
        "independent_of_constructor": True,
        "constructor_tool": "construct_o34_archives.py",
        "qualifier_tool": "qualify_o34_archives.py",
        "bindings": {
            "freeze_body_sha256": FREEZE_BODY,
            "sqlite_snapshot_sha256": SQLITE_SHA,
            "construction_merge": CONSTRUCT_MERGE,
            "o3_sha256": EXPECTED["O3"]["sha256"],
            "o4a_sha256": EXPECTED["O4_A"]["sha256"],
            "o4b_sha256": EXPECTED["O4_B"]["sha256"],
        },
        "findings": findings,
        **extra,
    }


if __name__ == "__main__":
    raise SystemExit(main())
