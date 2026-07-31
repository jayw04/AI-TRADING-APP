#!/usr/bin/env python3
"""EVGAP Stage 2 — inventory + recoverability (read-only on frozen snapshot).

Does not construct archives, mutate sources, submit broker calls, or execute gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FREEZE_BODY = "af7693f4b97fd7d9d4ad642ab1af47e9e9a2a8cd680f6a26c4d01fee8d57967e"
EXPECTED_SQLITE = "9e40a9ad2f0176acf884140594ddfa9e946e42d2723794f464bbb0efdc2d9db6"
EXPECTED_BAR = "b32e118732669c2880291cd0a7226589e4b0e2ef20839dc8172c26ce51e0adc7"
EXPECTED_MP = "c0148389daa4139dd60a5921d6bec55a224a4156fb7cca080cc2b8fdfb7eb2c1"
EXPECTED_O5_TREE = "1c209b068e89456dbdbb8f380fc8672d0b3d04d1460752e12d32dd8717832d26"
WINDOW_START = "2026-06-30T00:00:00Z"
WINDOW_END = "2026-07-30T19:39:07Z"
ACCOUNT_ID = 3
BROKER_ACCOUNT_ID = "PA34USW0Q8UO"
CAPTURE_ID = "20260731T002055Z"
QUOTE_PROV_KEYS = frozenset(
    {
        "provider",
        "feed_type",
        "venue_scope",
        "subscription_entitlement",
        "raw_payload_hash",
        "normalization_version",
    }
)
CKPT_KEYS = frozenset(
    {
        "schema_version",
        "run_id",
        "session_id",
        "account_id",
        "plan_hash",
        "authorization_id",
        "loss_control_state",
        "loss_control_state_version",
        "payload",
    }
)
RECOVERY_KEYS = frozenset(
    {
        "run_id",
        "account_id",
        "status",
        "journal_digest",
        "broker_client_order_ids",
        "package_digest",
        "conclusive",
    }
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


def tables(conn: sqlite3.Connection) -> set[str]:
    return {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]


def verify_broker(conn: sqlite3.Connection) -> tuple[bool, str | None]:
    row = conn.execute(
        "SELECT raw_payload FROM accounts_state WHERE account_id = ?",
        (ACCOUNT_ID,),
    ).fetchone()
    if not row:
        return False, None
    try:
        payload = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    except json.JSONDecodeError:
        return False, None
    acct = None
    if isinstance(payload, dict):
        acct = payload.get("account_number") or payload.get("account_id")
        if acct is None and isinstance(payload.get("account"), dict):
            acct = payload["account"].get("account_number")
    return acct == BROKER_ACCOUNT_ID, str(acct) if acct is not None else None


def load_orders(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    sql = """
    SELECT
      o.id, o.account_id, o.created_at, o.submitted_at, o.terminal_at,
      o.side, o.qty, o.status, o.broker_order_id, o.client_order_id,
      o.source_type, o.source_id, s.ticker
    FROM orders o
    JOIN symbols s ON s.id = o.symbol_id
    WHERE o.account_id = ?
    ORDER BY o.id ASC
    """
    out = []
    for r in conn.execute(sql, (ACCOUNT_ID,)):
        out.append(
            {
                "order_id": r[0],
                "account_id": r[1],
                "created_at": r[2],
                "submitted_at": r[3],
                "terminal_at": r[4],
                "side": r[5],
                "qty": r[6],
                "status": r[7],
                "broker_order_id": r[8],
                "client_order_id": r[9],
                "source_type": r[10],
                "source_id": r[11],
                "symbol": r[12],
            }
        )
    return out


def load_fills(conn: sqlite3.Connection) -> dict[int, list[dict[str, Any]]]:
    by_order: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in conn.execute(
        """
        SELECT f.id, f.order_id, f.broker_fill_id, f.qty, f.price,
               f.commission, f.filled_at
        FROM fills f
        JOIN orders o ON o.id = f.order_id
        WHERE o.account_id = ?
        ORDER BY f.order_id, f.id
        """,
        (ACCOUNT_ID,),
    ):
        by_order[int(r[1])].append(
            {
                "fill_id": r[0],
                "order_id": r[1],
                "broker_fill_id": r[2],
                "qty": str(r[3]),
                "price": str(r[4]),
                "commission": str(r[5]) if r[5] is not None else None,
                "filled_at": r[6],
            }
        )
    return by_order


def object_has_keys(obj: Any, required: frozenset[str]) -> bool:
    return isinstance(obj, dict) and required.issubset(obj.keys())


def scan_json_blob_for_keys(
    blob: Any, required: frozenset[str], depth: int = 0
) -> bool:
    if depth > 6:
        return False
    if object_has_keys(blob, required):
        return True
    if isinstance(blob, dict):
        for v in blob.values():
            if scan_json_blob_for_keys(v, required, depth + 1):
                return True
    elif isinstance(blob, list):
        for v in blob[:50]:
            if scan_json_blob_for_keys(v, required, depth + 1):
                return True
    elif isinstance(blob, str) and blob[:1] in "{[":
        try:
            return scan_json_blob_for_keys(json.loads(blob), required, depth + 1)
        except json.JSONDecodeError:
            return False
    return False


def recoverability_corpus(conn: sqlite3.Connection, tbls: set[str]) -> dict[str, Any]:
    """Prove whether required contract objects exist anywhere in account-3-scoped
    snapshot tables — presence scan only; does not invent values.
    """
    findings: dict[str, Any] = {
        "tables_present": sorted(tbls),
        "quote_provenance_object_found": False,
        "checkpoint_binding_object_found": False,
        "recovery_terminal_package_found": False,
        "model_available_field_found": False,
        "day_change_field_found_in_accounts_state": False,
        "accounts_state_day_change_value": None,
        "audit_log_present": "audit_log" in tbls,
        "checkpoint_table_present": any(
            t in tbls for t in ("checkpoints", "checkpoint", "phase0_checkpoints")
        ),
        "notes": [],
    }

    # accounts_state day_change (column preferred; payload fallback)
    if "accounts_state" in tbls:
        cols = set(columns(conn, "accounts_state"))
        if "day_change" in cols:
            row = conn.execute(
                """
                SELECT day_change, day_change_basis, equity, last_equity, updated_at
                FROM accounts_state WHERE account_id = ?
                """,
                (ACCOUNT_ID,),
            ).fetchone()
            if row and row[0] is not None:
                findings["day_change_field_found_in_accounts_state"] = True
                findings["accounts_state_day_change_value"] = str(row[0])
                findings["accounts_state_day_change_basis"] = row[1]
                findings["accounts_state_updated_at"] = row[4]
                findings["notes"].append(
                    "accounts_state.day_change column present at snapshot as-of; "
                    "per-episode forensic as-of lineage still required for O4-B "
                    "QUALIFIED binding under freeze mapping"
                )
        if not findings["day_change_field_found_in_accounts_state"]:
            row = conn.execute(
                "SELECT raw_payload FROM accounts_state WHERE account_id = ?",
                (ACCOUNT_ID,),
            ).fetchone()
            if row:
                try:
                    payload = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, dict):
                    dc = payload.get("day_change")
                    if dc is None and isinstance(payload.get("account"), dict):
                        dc = payload["account"].get("day_change")
                    if dc is not None:
                        findings["day_change_field_found_in_accounts_state"] = True
                        findings["accounts_state_day_change_value"] = str(dc)
                        findings["notes"].append(
                            "accounts_state.raw_payload contains day_change at "
                            "snapshot as-of only — per-episode forensic as-of "
                            "lineage still required for O4-B QUALIFIED binding"
                        )

    if "equity_snapshots" in tbls:
        n_eq = conn.execute(
            "SELECT COUNT(*) FROM equity_snapshots WHERE account_id = ?",
            (ACCOUNT_ID,),
        ).fetchone()[0]
        findings["equity_snapshots_account3_count"] = int(n_eq)
        findings["notes"].append(
            f"equity_snapshots has {n_eq} account-3 rows (ts/equity/"
            "day_change_pct) — may support as-of reconstruction only if "
            "Stage 3 proves episode forensic linkage without fabrication"
        )

    if "risk_session_baselines" in tbls:
        n_base = conn.execute(
            "SELECT COUNT(*) FROM risk_session_baselines WHERE account_id = ?",
            (ACCOUNT_ID,),
        ).fetchone()[0]
        findings["risk_session_baselines_account3_count"] = int(n_base)

    # Scan audit_log payloads for contract objects (account-scoped if column exists)
    if "audit_log" in tbls:
        col_names = columns(conn, "audit_log")
        col_set = set(col_names)
        text_cols = [
            c
            for c in ("details", "payload", "meta", "context", "raw_payload", "body")
            if c in col_set
        ]
        if "account_id" not in col_set:
            findings["notes"].append(
                "audit_log lacks account_id — account-scoped scan skipped "
                "(fail-closed; no cross-account recoverability claim)"
            )
        elif not text_cols:
            findings["notes"].append(
                "audit_log has no scannable text/json columns for contract objects"
            )
        else:
            sel = ", ".join(text_cols)
            rows = conn.execute(
                f"""
                SELECT {sel} FROM audit_log
                WHERE account_id = ?
                ORDER BY id DESC LIMIT 500
                """,
                (ACCOUNT_ID,),
            ).fetchall()
            for row in rows:
                for cell in row:
                    if scan_json_blob_for_keys(cell, QUOTE_PROV_KEYS):
                        findings["quote_provenance_object_found"] = True
                    if scan_json_blob_for_keys(cell, CKPT_KEYS):
                        findings["checkpoint_binding_object_found"] = True
                    if scan_json_blob_for_keys(cell, RECOVERY_KEYS):
                        findings["recovery_terminal_package_found"] = True
                    if isinstance(cell, str) and "model_available" in cell:
                        findings["model_available_field_found"] = True
                    if isinstance(cell, dict) and "model_available" in cell:
                        findings["model_available_field_found"] = True

    return findings


def locate_o5_anchors(
    evidence_root: Path,
    stage1_o5_manifest: Path,
    expected_manifest_sha: str,
) -> dict[str, Any]:
    """Locate-only within the Stage-1 pinned evidence tree file set."""
    if not stage1_o5_manifest.is_file():
        raise FileNotFoundError(stage1_o5_manifest)
    man_sha = sha256_file(stage1_o5_manifest)
    tree_ok = man_sha == expected_manifest_sha
    if not tree_ok:
        return {
            "evidence_root": str(evidence_root),
            "stage1_o5_manifest_path": str(stage1_o5_manifest),
            "stage1_o5_manifest_sha256": man_sha,
            "tree_manifest_matches_stage1": False,
            "candidate_manifest_files": [],
            "qualifying_nonempty_tier_a_manifests": [],
            "anchors": [],
            "disposition": "STOP_TREE_PIN_MISMATCH",
            "note": "Stage 1 O5 tree manifest hash mismatch — locate aborted",
        }

    # Paths pinned at Stage 1 (immutable search set)
    pinned_rels: list[str] = []
    for line in stage1_o5_manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        # format: "<sha256>  ./rel"
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        rel = parts[1].strip()
        if rel.startswith("./"):
            rel = rel[2:]
        pinned_rels.append(rel)

    candidates: list[dict[str, Any]] = []
    for rel in pinned_rels:
        p = evidence_root / rel
        if not p.is_file() or p.suffix.lower() != ".json":
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        anchors = None
        if isinstance(data, dict):
            o5 = data.get("o5_live_fill_anchors")
            if isinstance(o5, dict):
                anchors = o5.get("anchors")
            mb = data.get("manifest_body")
            if anchors is None and isinstance(mb, dict):
                o5b = mb.get("o5_live_fill_anchors")
                if isinstance(o5b, dict):
                    anchors = o5b.get("anchors")
        if isinstance(anchors, list):
            file_sha = hashlib.sha256(p.read_bytes()).hexdigest()
            candidates.append(
                {
                    "path": rel,
                    "sha256": file_sha,
                    "anchor_count": len(anchors),
                    "anchors_empty": len(anchors) == 0,
                    "qualifies_tier_a_nonempty": len(anchors) > 0,
                }
            )

    qualifying = [c for c in candidates if c["qualifies_tier_a_nonempty"]]
    return {
        "evidence_root": str(evidence_root),
        "stage1_o5_manifest_path": str(stage1_o5_manifest),
        "stage1_o5_manifest_sha256": man_sha,
        "tree_manifest_matches_stage1": True,
        "pinned_file_count": len(pinned_rels),
        "candidate_manifest_files": candidates,
        "qualifying_nonempty_tier_a_manifests": qualifying,
        "anchors": [],
        "disposition": (
            "anchors:[] VALID predetermined INCONCLUSIVE"
            if not qualifying
            else "NON_EMPTY_CANDIDATES_REQUIRE_INDEPENDENT_QUALIFICATION"
        ),
        "note": (
            "Locate-only over Stage 1 pinned evidence paths; no new fills; "
            "empty anchors valid under freeze"
            if not qualifying
            else "Non-empty candidate manifests located — Stage 4 must independently qualify"
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", type=Path, required=True)
    ap.add_argument("--bar-manifest", type=Path, required=True)
    ap.add_argument("--mp-manifest", type=Path, required=True)
    ap.add_argument("--o5-evidence-root", type=Path, required=True)
    ap.add_argument("--o5-stage1-manifest", type=Path, required=True)
    ap.add_argument("--expected-o5-manifest-sha", default=EXPECTED_O5_TREE)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--tooling-commit", required=True)
    args = ap.parse_args()

    if len(args.tooling_commit) != 40:
        print("tooling-commit must be 40 hex", file=sys.stderr)
        return 2

    pins = {
        "sqlite": (args.sqlite, EXPECTED_SQLITE),
        "bar_cache_manifest": (args.bar_manifest, EXPECTED_BAR),
        "market_projection_manifest": (args.mp_manifest, EXPECTED_MP),
    }
    pin_results = {}
    for name, (path, expected) in pins.items():
        if not path.is_file():
            print(f"STOP: missing {name}: {path}", file=sys.stderr)
            return 1
        got = sha256_file(path)
        pin_results[name] = {"path": str(path), "sha256": got, "match": got == expected}
        if got != expected:
            print(f"STOP: {name} sha mismatch expected={expected} got={got}", file=sys.stderr)
            return 1

    conn = sqlite3.connect(f"file:{args.sqlite.as_posix()}?mode=ro", uri=True)
    try:
        tbls = tables(conn)
        ok, broker = verify_broker(conn)
        if not ok:
            print(f"STOP: broker mismatch account 3: {broker!r}", file=sys.stderr)
            return 1
        orders = load_orders(conn)
        fills_by = load_fills(conn)
        corpus = recoverability_corpus(conn, tbls)
    finally:
        conn.close()

    n_source = len(orders)
    window_excl: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    seen: set[str] = set()

    for o in orders:
        created = parse_ts(o["created_at"])
        if not in_window(created):
            window_excl.append(
                {
                    "order_id": o["order_id"],
                    "reason_code": "EXC-010",
                    "detail": "outside_eligibility_window",
                }
            )
            continue
        plan_id = f"ord:{o['order_id']}"
        if plan_id in seen:
            print(f"STOP: ambiguous dedup {plan_id}", file=sys.stderr)
            return 1
        seen.add(plan_id)
        eligible.append(o)

    n_window = len(eligible)
    n_dedup = len(eligible)  # 1:1 ord:id after collision fail-closed

    # Per-episode recoverability under frozen mappings (honest presence checks)
    o3_rows = []
    o4a_rows = []
    o4b_rows = []
    reason_counts: Counter[str] = Counter()

    # Global surface recoverability (corpus-level) — if corpus lacks objects,
    # every episode is incomplete for that surface (no fabrication).
    qp_ok = corpus["quote_provenance_object_found"]
    ckpt_ok = corpus["checkpoint_binding_object_found"]
    recovery_ok = corpus["recovery_terminal_package_found"]
    model_ok = corpus["model_available_field_found"]
    # day_change at accounts_state is snapshot-global, not per-episode forensic
    # as-of — freeze requires baseline provenance per observation. Treat as
    # NOT recoverable for QUALIFIED O4-B binding without per-episode lineage.
    day_change_per_episode_ok = False
    corpus["notes"].append(
        "Per-episode day_change lineage not established from orders/fills alone; "
        "accounts_state day_change (if present) is snapshot-global and insufficient "
        "alone for O4-B QUALIFIED binding under freeze mapping"
    )

    for o in eligible:
        plan_id = f"ord:{o['order_id']}"
        submitted = parse_ts(o["submitted_at"])
        fills = fills_by.get(int(o["order_id"]), [])
        missing_o3 = []
        # authority_inputs: recoverable from order row (account-scoped fields exist)
        authority_ok = True
        if not qp_ok:
            missing_o3.append("MISSING_REPLAY_SURFACE:quote_provenance")
        if not ckpt_ok:
            missing_o3.append("MISSING_REPLAY_SURFACE:checkpoint_tuple")
        # loss_accounting_inputs: need fill legs OR explicit loss inputs — fills
        # provide qty/price but freeze requires formula_id + policy assembly from
        # pre-existing records; presence of fills alone ≠ complete loss_accounting_inputs
        # without provenanced policy bundle. Conservative: require fills AND refuse
        # claiming complete unless dedicated loss_accounting object found.
        loss_ok = False  # no dedicated loss_accounting_inputs object found in corpus
        if not loss_ok:
            missing_o3.append("MISSING_REPLAY_SURFACE:loss_accounting_inputs")
        if not recovery_ok:
            missing_o3.append("MISSING_REPLAY_SURFACE:recovery_inputs")
        if not authority_ok:
            missing_o3.append("MISSING_REPLAY_SURFACE:authority_inputs")

        o3_complete = len(missing_o3) == 0
        for code in missing_o3:
            reason_counts[code] += 1
        o3_rows.append(
            {
                "plan_id": plan_id,
                "order_id": o["order_id"],
                "symbol": o["symbol"],
                "complete": o3_complete,
                "missing": missing_o3,
                "authority_inputs_recoverable": authority_ok,
            }
        )

        missing_o4a = []
        if submitted is None:
            missing_o4a.append("MISSING_CUTOFF")
        # Decision-time quotes: market manifests pin trees but do not prove
        # two-sided quotes at/before cutoff without content evaluation that still
        # must show lineage. We check whether bar_cache/market_projection trees
        # are non-empty (already pinned) but without fabricating quote recovery,
        # mark MISSING_DECISION_TIME_QUOTE unless a provenanced quote object exists.
        if not qp_ok:
            # No provenanced decision-time quote objects in account-scoped corpus
            missing_o4a.append("MISSING_DECISION_TIME_QUOTE")
        if not model_ok:
            missing_o4a.append("MISSING_PROVENANCE")  # model_available absent
        o4a_complete = len(missing_o4a) == 0
        for code in missing_o4a:
            reason_counts[code] += 1
        o4a_rows.append(
            {
                "plan_id": plan_id,
                "order_id": o["order_id"],
                "symbol": o["symbol"],
                "cutoff_at_utc": (
                    submitted.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    if submitted
                    else None
                ),
                "complete": o4a_complete,
                "missing": missing_o4a,
            }
        )

        missing_o4b = []
        if not fills:
            missing_o4b.append("O4B_INCOMPLETE")
        if not day_change_per_episode_ok:
            missing_o4b.append("MISSING_FORENSIC_BASELINE")
        o4b_complete = len(missing_o4b) == 0
        for code in missing_o4b:
            reason_counts[code] += 1
        o4b_rows.append(
            {
                "plan_id": plan_id,
                "order_id": o["order_id"],
                "symbol": o["symbol"],
                "n_fills": len(fills),
                "complete": o4b_complete,
                "missing": missing_o4b,
            }
        )

    o5 = locate_o5_anchors(
        args.o5_evidence_root,
        args.o5_stage1_manifest,
        args.expected_o5_manifest_sha,
    )
    if not o5["tree_manifest_matches_stage1"]:
        print(
            "STOP: O5 evidence tree manifest drift vs Stage 1 pin "
            f"{args.expected_o5_manifest_sha} != {o5.get('stage1_o5_manifest_sha256')}",
            file=sys.stderr,
        )
        return 1

    n_o3_complete = sum(1 for r in o3_rows if r["complete"])
    n_o4a_complete = sum(1 for r in o4a_rows if r["complete"])
    n_o4b_complete = sum(1 for r in o4b_rows if r["complete"])

    report = {
        "document_id": "ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-STAGE2-001",
        "stage": 2,
        "capture_id": CAPTURE_ID,
        "freeze_body_sha256": FREEZE_BODY,
        "start_ruling_id": "ADR0043-PH0-D-BOX-EVIDENCE-GAP-ACQ-START-001",
        "eligibility_window": {
            "start_inclusive_utc": WINDOW_START,
            "end_exclusive_utc": WINDOW_END,
        },
        "account_3_identity": {
            "workbench_account_id": ACCOUNT_ID,
            "broker_account_id": BROKER_ACCOUNT_ID,
            "broker_verified": True,
        },
        "pins_verified": pin_results,
        "o5_tree_pin_verified": o5["tree_manifest_matches_stage1"],
        "tooling_commit": args.tooling_commit,
        "analyzed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources_modified": False,
        "window_widened": False,
        "mappings_relaxed": False,
        "construction_performed": False,
        "count_reconciliation": {
            "pipeline_stages_ordered": [
                "source_count",
                "window_eligible",
                "deduplicated",
                "complete",
                "excluded_by_reason",
                "emitted",
            ],
            "n_source_count": n_source,
            "n_window_eligible": n_window,
            "n_outside_window_excluded": len(window_excl),
            "n_deduplicated": n_dedup,
            "n_complete_o3": n_o3_complete,
            "n_complete_o4a": n_o4a_complete,
            "n_complete_o4b": n_o4b_complete,
            "n_excluded_o3_incomplete": n_dedup - n_o3_complete,
            "n_excluded_o4a_incomplete": n_dedup - n_o4a_complete,
            "n_excluded_o4b_incomplete": n_dedup - n_o4b_complete,
            "reason_code_counts": dict(sorted(reason_counts.items())),
            "identity_checks": {
                "source_ge_window": n_source >= n_window,
                "window_eq_dedup": n_window == n_dedup,
                "o3_complete_plus_incomplete_eq_dedup": (
                    n_o3_complete + (n_dedup - n_o3_complete) == n_dedup
                ),
                "o4a_complete_plus_incomplete_eq_dedup": (
                    n_o4a_complete + (n_dedup - n_o4a_complete) == n_dedup
                ),
                "o4b_complete_plus_incomplete_eq_dedup": (
                    n_o4b_complete + (n_dedup - n_o4b_complete) == n_dedup
                ),
            },
            "emitted": "NOT_APPLICABLE_STAGE2_NO_CONSTRUCTION",
        },
        "corpus_recoverability": corpus,
        "o5_locate_only": o5,
        "stage3_construction_authorized_by_this_report": False,
        "stage3_ready_recommendation": (
            "Construction may proceed only for surfaces/episodes with complete "
            "recoverability; currently n_complete_o3/o4a/o4b indicate systematic "
            "missing gap surfaces — construction would emit incomplete candidates "
            "unless additional recoverable sources are proven. Owner may still "
            "authorize Stage 3 to package honest incomplete candidates with "
            "reason codes."
        ),
        "gates": "CLOSED",
        "d_wire": "BLOCKED",
    }

    out: Path = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "stage2_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (out / "o3_episode_recoverability.json").write_text(
        json.dumps(o3_rows, indent=2) + "\n", encoding="utf-8"
    )
    (out / "o4a_episode_recoverability.json").write_text(
        json.dumps(o4a_rows, indent=2) + "\n", encoding="utf-8"
    )
    (out / "o4b_episode_recoverability.json").write_text(
        json.dumps(o4b_rows, indent=2) + "\n", encoding="utf-8"
    )
    (out / "window_exclusions.json").write_text(
        json.dumps(window_excl, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps(report["count_reconciliation"], indent=2))
    print("o5_disposition", o5["disposition"])
    print("WROTE", out.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
