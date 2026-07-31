#!/usr/bin/env python3
"""Deterministic O34 record selection + candidate archive construction.

Reads ONLY the bound immutable sqlite snapshot (and pinned market manifests).
Does NOT: broker calls, mutate live DB, invent observations, execute gates.

Unit of observation (freeze): ExecutionPlan episode. When no plan table exists,
episodes are deterministically derived from account-3 orders:

    plan_id = "ord:" + str(orders.id)

First-broker-submission cutoff = orders.submitted_at (else MISSING_CUTOFF).
O4-B completeness requires >=1 fill row.

Usage (on workbench, after snapshot path reachable)::

    python3 construct_o34_archives.py \\
      --sqlite /opt/workbench/data/ops/adr0043_o34_acq_snapshots/20260730T022316Z/workbench.sqlite.snapshot \\
      --capture-summary /opt/workbench/data/ops/adr0043_o34_acq_snapshots/20260730T022316Z/capture_summary.json \\
      --out-dir /opt/workbench/data/ops/adr0043_o34_acq_snapshots/20260730T022316Z/constructed \\
      --tooling-commit <40hex>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FREEZE_BODY_SHA256 = (
    "80dfd8ec6d90182cdeabaab2d1457720ca417bcd5cb1511b4dd9d77989951bb0"
)
EXPECTED_SQLITE_SHA256 = (
    "26bae1f5b754c4ff80e031126674d1818ae4a9a90e4faa6b36820f2690278d5b"
)
WINDOW_START = "2026-06-30T00:00:00Z"
WINDOW_END = "2026-07-30T00:21:33Z"
ACCOUNT_ID = 3
BROKER_ACCOUNT_ID = "PA34USW0Q8UO"
SNAPSHOT_ID = "20260730T022316Z"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def iso_z(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def session_id(symbol: str, dt: datetime | None) -> str:
    if dt is None:
        return f"{symbol}|UNKNOWN_DATE"
    return f"{symbol}|{dt.date().isoformat()}"


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
      o.source_type, o.source_id,
      s.ticker
    FROM orders o
    JOIN symbols s ON s.id = o.symbol_id
    WHERE o.account_id = ?
    ORDER BY o.id ASC
    """
    out: list[dict[str, Any]] = []
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
    sql = """
    SELECT f.id, f.order_id, f.broker_fill_id, f.qty, f.price, f.commission, f.filled_at
    FROM fills f
    JOIN orders o ON o.id = f.order_id
    WHERE o.account_id = ?
    ORDER BY f.order_id ASC, f.id ASC
    """
    by_order: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in conn.execute(sql, (ACCOUNT_ID,)):
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True, type=Path)
    ap.add_argument("--capture-summary", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--tooling-commit", required=True)
    args = ap.parse_args()

    if len(args.tooling_commit) != 40:
        print("tooling-commit must be 40-hex", file=sys.stderr)
        return 2

    sqlite_path: Path = args.sqlite
    if not sqlite_path.is_file():
        print(f"STOP: snapshot unavailable: {sqlite_path}", file=sys.stderr)
        return 1

    got = sha256_file(sqlite_path)
    if got != EXPECTED_SQLITE_SHA256:
        print(
            f"STOP: sqlite sha mismatch expected={EXPECTED_SQLITE_SHA256} got={got}",
            file=sys.stderr,
        )
        return 1

    capture = json.loads(args.capture_summary.read_text(encoding="utf-8"))
    if capture.get("freeze_body_sha256") != FREEZE_BODY_SHA256:
        print("STOP: capture summary freeze hash mismatch", file=sys.stderr)
        return 1
    if not capture.get("all_mandatory_snapshots_bound"):
        print("STOP: capture summary not fully bound", file=sys.stderr)
        return 1

    conn = sqlite3.connect(f"file:{sqlite_path.as_posix()}?mode=ro", uri=True)
    try:
        ok, broker = verify_broker(conn)
        if not ok:
            print(
                f"STOP: broker identity mismatch for account 3: {broker!r}",
                file=sys.stderr,
            )
            return 1

        orders = load_orders(conn)
        fills_by_order = load_fills(conn)
    finally:
        conn.close()

    exclusions: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    seen_plan: set[str] = set()

    for o in orders:
        created = parse_ts(o["created_at"])
        submitted = parse_ts(o["submitted_at"])
        # Eligibility uses plan_created_at ≈ order created_at (deterministic mapping)
        if not in_window(created):
            exclusions.append(
                {
                    "order_id": o["order_id"],
                    "reason_code": "EXC-010",
                    "detail": "outside_eligibility_window",
                }
            )
            continue

        plan_id = f"ord:{o['order_id']}"
        if plan_id in seen_plan:
            print(f"STOP: ambiguous dedup for {plan_id}", file=sys.stderr)
            return 1
        seen_plan.add(plan_id)

        selected.append(
            {
                "order": o,
                "plan_id": plan_id,
                "created": created,
                "submitted": submitted,
                "fills": fills_by_order.get(int(o["order_id"]), []),
            }
        )

    constructed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    source_snap = EXPECTED_SQLITE_SHA256

    o3_obs: list[dict[str, Any]] = []
    o4a_obs: list[dict[str, Any]] = []
    o4b_obs: list[dict[str, Any]] = []
    o4a_excl: list[dict[str, Any]] = []
    o4b_excl: list[dict[str, Any]] = []

    clusters: set[str] = set()

    for ep in selected:
        o = ep["order"]
        plan_id = ep["plan_id"]
        created = ep["created"]
        submitted = ep["submitted"]
        fills = ep["fills"]
        symbol = o["symbol"]
        sid = session_id(symbol, created)
        clusters.add(sid)
        lineage = {
            "source_class": "application_audit_plan_checkpoint_terminal_records",
            "source_snapshot_id": SNAPSHOT_ID,
            "source_row_key": f"orders.id={o['order_id']}",
        }

        o3_obs.append(
            {
                "observation_id": f"o3:{plan_id}",
                "plan_id": plan_id,
                "symbol": symbol,
                "session_id": sid,
                "plan_created_at_utc": iso_z(created),
                "quote_provenance": None,
                "authority_inputs": {
                    "account_id": ACCOUNT_ID,
                    "broker_account_id": BROKER_ACCOUNT_ID,
                    "side": o["side"],
                    "qty": str(o["qty"]),
                    "status": o["status"],
                    "source_type": o["source_type"],
                    "source_id": o["source_id"],
                },
                "checkpoint_tuple": None,
                "loss_accounting_inputs": None,
                "recovery_inputs": None,
                "source_lineage": lineage,
            }
        )

        if submitted is None:
            o4a_excl.append(
                {"plan_id": plan_id, "reason_code": "MISSING_CUTOFF"}
            )
        else:
            o4a_obs.append(
                {
                    "observation_id": f"o4a:{plan_id}",
                    "plan_id": plan_id,
                    "episode_id": plan_id,
                    "cutoff_event": "FIRST_BROKER_SUBMISSION_BOUNDARY",
                    "cutoff_at_utc": iso_z(submitted),
                    "quotes": {},
                    "symbols": [symbol],
                    "day_change": None,
                    "model_available": True,
                    "evidence_tier": "TIER_D_DISPLAYED_SPREAD",
                    "authority_inputs": {
                        "account_id": ACCOUNT_ID,
                        "broker_account_id": BROKER_ACCOUNT_ID,
                    },
                    "plan_inputs": {
                        "side": o["side"],
                        "qty": str(o["qty"]),
                        "created_at_utc": iso_z(created),
                    },
                    "fills": [],
                    "terminal_broker_state": None,
                    "post_submit_quotes": None,
                    "source_lineage": lineage,
                }
            )

        if not fills:
            o4b_excl.append(
                {"plan_id": plan_id, "reason_code": "O4B_INCOMPLETE"}
            )
        else:
            # Deterministic fill loss placeholder: sum qty*price as string accounting input
            notional = 0.0
            for f in fills:
                notional += float(f["qty"]) * float(f["price"])
            o4b_obs.append(
                {
                    "observation_id": f"o4b:{plan_id}",
                    "plan_id": plan_id,
                    "episode_id": plan_id,
                    "o4a_episode_link": {
                        "episode_id": plan_id,
                        "o4a_observation_id": (
                            f"o4a:{plan_id}" if submitted is not None else None
                        ),
                    },
                    "quotes": {},
                    "symbols": [symbol],
                    "day_change": None,
                    "fills": fills,
                    "fill_loss_per_round_trip": f"{notional:.8f}",
                    "terminal_broker_state": {
                        "order_status": o["status"],
                        "terminal_at": o["terminal_at"],
                    },
                    "terminal_loss_accounting_inputs": {
                        "fill_notional_sum": f"{notional:.8f}"
                    },
                    "evidence_tier": "TIER_B_PAPER_OR_EXECUTABLE_ESTIMATE",
                    "terminal_completeness": {
                        "complete": True,
                        "criteria_id": "O4B-TERM-COMPLETE-001",
                    },
                    "source_lineage": lineage,
                }
            )

    provenance = {
        "constructor": "construct_o34_archives.py",
        "tooling_commit": args.tooling_commit,
        "constructed_at_utc": constructed_at,
        "host": "workbench",
    }
    window = {
        "start_inclusive_utc": WINDOW_START,
        "end_exclusive_utc": WINDOW_END,
    }
    account_scope = {
        "workbench_account_id": ACCOUNT_ID,
        "broker_account_id": BROKER_ACCOUNT_ID,
    }

    o3 = {
        "archive_id": f"O3-CAND-{SNAPSHOT_ID}",
        "archive_kind": "O3_HISTORICAL_REPLAY",
        "schema_id": "ADR0043-PH0-D-BOX-O34-O3-ARCHIVE-SCHEMA-001",
        "account_scope": account_scope,
        "eligibility_window": window,
        "observations": o3_obs,
        "counts": {
            "n_observations": len(o3_obs),
            "n_unique_plans": len({x["plan_id"] for x in o3_obs}),
            "n_clusters": len(clusters),
        },
        "construction_freeze_id": "ADR0043-PH0-D-BOX-O34-ACQ-FREEZE-001",
        "provenance": provenance,
    }
    o4a = {
        "archive_id": f"O4A-CAND-{SNAPSHOT_ID}",
        "archive_kind": "O4A_DECISION_TIME",
        "schema_id": "ADR0043-PH0-D-BOX-O34-O4A-ARCHIVE-SCHEMA-001",
        "account_scope": account_scope,
        "eligibility_window": window,
        "observations": o4a_obs,
        "counts": {
            "n_observations": len(o4a_obs),
            "n_unique_plans": len({x["plan_id"] for x in o4a_obs}),
        },
        "construction_freeze_id": "ADR0043-PH0-D-BOX-O34-ACQ-FREEZE-001",
        "provenance": provenance,
    }
    o4b = {
        "archive_id": f"O4B-CAND-{SNAPSHOT_ID}",
        "archive_kind": "O4B_FORENSIC",
        "schema_id": "ADR0043-PH0-D-BOX-O34-O4B-ARCHIVE-SCHEMA-001",
        "account_scope": account_scope,
        "eligibility_window": window,
        "observations": o4b_obs,
        "counts": {
            "n_observations": len(o4b_obs),
            "n_unique_plans": len({x["plan_id"] for x in o4b_obs}),
            "n_fills": sum(len(x["fills"]) for x in o4b_obs),
        },
        "construction_freeze_id": "ADR0043-PH0-D-BOX-O34-ACQ-FREEZE-001",
        "provenance": provenance,
    }

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    def write_archive(name: str, doc: dict[str, Any]) -> dict[str, Any]:
        # Canonical-ish stable JSON for hashing (sorted keys, no extra spaces variance)
        raw = (json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode(
            "utf-8"
        )
        path = out_dir / name
        path.write_bytes(raw)
        return {
            "path": str(path),
            "sha256": sha256_bytes(raw),
            "size_bytes": len(raw),
            "counts": doc["counts"],
        }

    meta = {
        "outcome": "CONSTRUCTED",
        "freeze_body_sha256": FREEZE_BODY_SHA256,
        "sqlite_snapshot_sha256": source_snap,
        "capture_id": SNAPSHOT_ID,
        "unit_of_observation_mapping": (
            "ExecutionPlan episode reconstructed as plan_id='ord:'+orders.id "
            "because no execution_plan table exists in workbench.sqlite"
        ),
        "broker_verified": BROKER_ACCOUNT_ID,
        "n_source_orders_account3": len(orders),
        "n_excluded_window": len(exclusions),
        "n_selected_episodes": len(selected),
        "n_o4a_missing_cutoff": len(o4a_excl),
        "n_o4b_incomplete": len(o4b_excl),
        "exclusions_window": exclusions,
        "exclusions_o4a": o4a_excl,
        "exclusions_o4b": o4b_excl,
        "archives": {
            "O3": write_archive("O3_CANDIDATE.json", o3),
            "O4_A": write_archive("O4A_CANDIDATE.json", o4a),
            "O4_B": write_archive("O4B_CANDIDATE.json", o4b),
        },
        "gate_ready": False,
        "qualification_status": "PENDING_INDEPENDENT_QUALIFICATION",
        "selection_performed": True,
        "broker_calls": [],
    }
    (out_dir / "construction_manifest.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
