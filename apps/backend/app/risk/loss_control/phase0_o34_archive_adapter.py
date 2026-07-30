"""ADR-0043 Phase-0 — QUALIFIED O34 archive → gate harness adapter.

Deterministic consumption of ``plan_id='ord:<orders.id>'`` archives for CAMPAIGN-001 v1.2.
Does not submit orders or import the order path.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.risk.loss_control.phase0_o4_replay import (
    DecisionTimeEvidence,
    ForensicEvidence,
)

_ORD_RE = re.compile(r"^ord:([1-9][0-9]*)$")


def parse_ord_plan_id(plan_id: str) -> int:
    """Accept only ``ord:<positive_int>``; refuse all other shapes."""
    m = _ORD_RE.match(plan_id)
    if not m:
        raise ValueError(f"unsupported plan_id for v1.2 harness contract: {plan_id!r}")
    return int(m.group(1))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def open_qualified_archive(path: Path, *, expected_sha256: str) -> dict[str, Any]:
    """Open a QUALIFIED candidate archive; fail closed on hash mismatch."""
    digest = sha256_file(path)
    if digest != expected_sha256:
        raise ValueError(
            f"archive hash mismatch path={path} got={digest} expected={expected_sha256}"
        )
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("archive root must be object")
    return doc


def o4a_row_to_decision_time(row: dict[str, Any]) -> DecisionTimeEvidence:
    """Map one O4-A archive observation to DecisionTimeEvidence (no look-ahead)."""
    parse_ord_plan_id(str(row["plan_id"]))
    fills = row.get("fills") or []
    if fills:
        raise ValueError(f"O4-A look-ahead fills present for {row.get('plan_id')}")
    if row.get("terminal_broker_state") is not None:
        raise ValueError(f"O4-A terminal_broker_state present for {row.get('plan_id')}")
    if row.get("post_submit_quotes") is not None:
        raise ValueError(f"O4-A post_submit_quotes present for {row.get('plan_id')}")
    day_change = row.get("day_change")
    dc = Decimal(str(day_change)) if day_change is not None else None
    quotes = row.get("quotes") or {}
    if not isinstance(quotes, dict):
        raise ValueError("O4-A quotes must be object")
    symbols = tuple(str(s) for s in (row.get("symbols") or ()))
    return DecisionTimeEvidence(
        quotes=quotes,
        symbols=symbols,
        day_change=dc,
        model_available=bool(row.get("model_available", True)),
        evidence_tier=str(row.get("evidence_tier") or "TIER_D_DISPLAYED_SPREAD"),
        fills=(),
    )


def o4b_row_to_forensic(row: dict[str, Any]) -> ForensicEvidence:
    """Map one O4-B archive observation to ForensicEvidence."""
    parse_ord_plan_id(str(row["plan_id"]))
    fills = row.get("fills") or []
    if not fills:
        raise ValueError(f"O4-B missing fills for {row.get('plan_id')}")
    day_change = row.get("day_change")
    dc = Decimal(str(day_change)) if day_change is not None else None
    quotes = row.get("quotes") or {}
    if not isinstance(quotes, dict):
        raise ValueError("O4-B quotes must be object")
    symbols = tuple(str(s) for s in (row.get("symbols") or ()))
    loss = Decimal(str(row["fill_loss_per_round_trip"]))
    fill_tuple = tuple(dict(f) for f in fills)
    return ForensicEvidence(
        quotes=quotes,
        symbols=symbols,
        day_change=dc,
        fills=fill_tuple,
        fill_loss_per_round_trip=loss,
        evidence_tier=str(row.get("evidence_tier") or "TIER_B_PAPER_OR_EXECUTABLE_ESTIMATE"),
    )


def iter_o3_replay_bundles(archive: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic O3 bundles keyed by ord: plan_id (sparse fields allowed)."""
    out: list[dict[str, Any]] = []
    for row in archive.get("observations") or []:
        plan_id = str(row["plan_id"])
        order_id = parse_ord_plan_id(plan_id)
        out.append(
            {
                "plan_id": plan_id,
                "order_id": order_id,
                "symbol": row.get("symbol"),
                "session_id": row.get("session_id"),
                "plan_created_at_utc": row.get("plan_created_at_utc"),
                "quote_provenance": row.get("quote_provenance"),
                "authority_inputs": row.get("authority_inputs"),
                "checkpoint_tuple": row.get("checkpoint_tuple"),
                "loss_accounting_inputs": row.get("loss_accounting_inputs"),
                "recovery_inputs": row.get("recovery_inputs"),
                "source_lineage": row.get("source_lineage"),
            }
        )
    out.sort(key=lambda b: b["order_id"])
    return out


def harness_can_consume_ord_mapping() -> bool:
    """Readiness probe: mapping parse + O4 dataclass construction is deterministic."""
    assert parse_ord_plan_id("ord:1080") == 1080
    try:
        parse_ord_plan_id("plan:1080")
        return False
    except ValueError:
        pass
    sample_a: dict[str, Any] = {
        "plan_id": "ord:1",
        "quotes": {},
        "symbols": ["MSFT"],
        "day_change": None,
        "model_available": True,
        "fills": [],
        "terminal_broker_state": None,
        "post_submit_quotes": None,
    }
    sample_b: dict[str, Any] = {
        "plan_id": "ord:1",
        "quotes": {},
        "symbols": ["MSFT"],
        "day_change": None,
        "fills": [{"qty": "1", "price": "1.0"}],
        "fill_loss_per_round_trip": "1.0",
    }
    o4a_row_to_decision_time(sample_a)
    o4b_row_to_forensic(sample_b)
    return True
