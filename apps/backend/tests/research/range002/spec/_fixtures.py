"""SYNTHETIC fixtures only. None of these values is a RANGE-002 decision (D01-D19)."""

from __future__ import annotations

import atexit
import copy
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.spec.schema import draft_skeleton

SIGNOFF = {
    "owner": "SYNTH-OWNER",
    "trading_expert": "SYNTH-EXPERT",
    "independent_validator": "SYNTH-VALIDATOR",
    "date": "2000-01-01",
    "spec_sha256": None,
}

#: Synthetic registry genesis id; governance test helpers enroll registries carrying exactly this id.
SYNTH_GENESIS_ID = "5eed5eed-5eed-4eed-9eed-5eed5eed5eed"  # canonical lowercase UUIDv4
OTHER_GENESIS_ID = "0badc0de-0bad-4ade-8bad-0badc0de0bad"  # a different valid UUIDv4

CANDIDATES = [
    {"id": "X1", "family": "time", "params": {}},
    {"id": "X2", "family": "fixed_r", "params": {"synthetic_k": 1.0}},
    {"id": "X3", "family": "trailing", "params": {"synthetic_t": 1.0}},
]


def set_path(payload: dict[str, Any], path: str, value: Any) -> None:
    node = payload
    parts = path.split(".")
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value


def get_path(payload: dict[str, Any], path: str) -> Any:
    node: Any = payload
    for part in path.split("."):
        node = node[part]
    return node


# Every P0 leaf of the skeleton -> an obviously synthetic placeholder value.
_P0_VALUES: dict[str, Any] = {
    "registration.related_programs": "SYNTH",
    "universe.n": 3,
    "data.vendor": "SYNTH-VENDOR",
    "data.fetch_mode": "SYNTH-MODE",
    "signal.or_completeness_rule": "SYNTH",
    "signal.min_or_width_ticks": 2,
    "exits.candidates": CANDIDATES,
    "exits.complexity_order": ["time", "fixed_r", "trailing", "scale_out"],
    "exits.selection.score": "synthetic_score",
    "exits.selection.tie_tolerance_r": 0.5,
    "exits.selection.eligibility.min_trades": 7,
    "exits.selection.eligibility.min_pf": 1.5,
    "exits.selection.stop_test": "synthetic_stop_test",
    "exit.halfday_offset_min": 4,
    "fill.slippage_model": "SYNTH",
    "fill.halt_policy": "SYNTH",
    "costs.accounting_mode": "all_in",
    "costs.components": ["SYNTH"],
    "risk.per_trade_pct": 0.1,
    "risk.per_name_cap": 0.2,
    "risk.gross_cap": 0.3,
    "risk.max_concurrent": 2,
    "risk.daily_loss_limit": 0.4,
    "risk.max_participation": 0.5,
    "risk.fill_risk_tolerance": 0.6,
    "controls.random_entry.repetitions": 11,
    "controls.random_entry.seed": 12,
    "controls.random_entry.invalid_draw_policy": "SYNTH",
    "controls.naive_orb.definition": "SYNTH",
    "stats.bootstrap.method": "SYNTH-METHOD",
    "stats.bootstrap.block_len": 2.5,
    "stats.bootstrap.ci_type": "SYNTH-CI",
    "stats.bootstrap.confidence_level": 0.9,
    "stats.bootstrap.reps": 13,
    "stats.bootstrap.seed": 14,
    "stats.hypothesis_family": "SYNTH",
    "stats.alpha_one_sided": 0.07,
    "stats.regime.definition": "SYNTH",
    "stats.regime.criterion": "SYNTH",
    "execution.bar_timestamp_convention": "start",
    "execution.vendor_delay_ms": 1,
    "execution.submit_latency_ms": 2,
    "execution.ack_latency_ms": 3,
    "execution.crossed_before_arm_policy": "SKIP",
    "execution.order_type": "emulated",
    "execution.stop_protection_policy": "SYNTH",
    "execution.tie_break": "SYNTH",
    "execution.eod_lead_s": 5,
    "execution.order_reservation_policy": "SYNTH",
    "p3.criteria": {"synthetic": True},
    "p3.max_p3a_attempts": 9,
    "p3.max_p3b_attempts": 8,
    "gates.basis": "signal_level",
    "gates.trade_unit": "SYNTH",
    "gates.yearly": "SYNTH",
    "gates.win_rate": "SYNTH",
    "gates.max_dd": "SYNTH",
    "p5.account_id": "SYNTH-ACCT",
    "p5.degradation_tolerance": "SYNTH",
    "p5.cost_ratio_contract": "SYNTH",
    "p5.shadow_acceptance": "SYNTH",
    "diagnostics.taxonomy": "SYNTH",
    "governance.economic_thesis_sha": "ab" * 32,
    "governance.roles": {"synthetic": "SYNTH"},
    "governance.exposure_signed": {"synthetic": "SYNTH"},
    "governance.registry_genesis_id": SYNTH_GENESIS_ID,
}

P0_PATHS = tuple(_P0_VALUES)


def complete_payload(*, signed: bool = True) -> dict[str, Any]:
    """A complete synthetic draft: every P0 field set; sign-off filled when ``signed``."""
    payload = draft_skeleton()
    for path, value in _P0_VALUES.items():
        set_path(payload, path, copy.deepcopy(value))
    if signed:
        payload["signoff"] = dict(SIGNOFF)
    return payload


# --- synthetic governance manifest (Round 5 N-A). Never a real approval: tests inject it through
# the explicit ``manifest_path`` parameter; production code reads only the committed fixed path.
SYNTH_P3A_LIMIT = 9  # equals _P0_VALUES["p3.max_p3a_attempts"]
SYNTH_P3B_LIMIT = 8  # equals _P0_VALUES["p3.max_p3b_attempts"]


def synthetic_manifest_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "approved_registry_genesis_id": SYNTH_GENESIS_ID,
        "approved_by": "SYNTH-OWNER",
        "approved_on": "2000-01-01",
        "p3_attempt_limits": {"p3a": SYNTH_P3A_LIMIT, "p3b": SYNTH_P3B_LIMIT},
        "notes": "synthetic test manifest",
    }
    payload.update(overrides)
    return payload


def write_manifest(path: Path, payload: dict[str, Any] | None = None) -> Path:
    path.write_text(
        json.dumps(synthetic_manifest_payload() if payload is None else payload),
        encoding="utf-8",
        newline="\n",
    )
    return path


_SYNTH_DIR = tempfile.mkdtemp(prefix="range002-synth-manifest-")
atexit.register(shutil.rmtree, _SYNTH_DIR, ignore_errors=True)
#: A pre-written, approved synthetic manifest matching SYNTH_GENESIS_ID and the synthetic limits.
SYNTH_MANIFEST_PATH = write_manifest(Path(_SYNTH_DIR) / "manifest.json")


# --- links: a skip must never hide a test on Linux (CI) ------------------------------------------
def _link_unavailable(what: str, exc: BaseException) -> None:
    if sys.platform.startswith("linux"):
        pytest.fail(f"{what} creation failed on Linux, where it must work (never skipped): {exc!r}")
    pytest.skip(f"SKIPPED (not passed): {what} unavailable on {sys.platform}: {exc!r}")


def make_symlink(link: Path, target: Path) -> None:
    """Create a symlink. Skips ONLY off Linux when the OS/user cannot; on Linux a failure FAILS
    the test, so a green Linux job proves the symlink-dependent test actually executed."""
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        _link_unavailable("symlink", exc)


def make_hardlink(link: Path, target: Path) -> None:
    """Same policy as :func:`make_symlink`, for hard links."""
    try:
        os.link(target, link)
    except (OSError, NotImplementedError) as exc:
        _link_unavailable("hard link", exc)
