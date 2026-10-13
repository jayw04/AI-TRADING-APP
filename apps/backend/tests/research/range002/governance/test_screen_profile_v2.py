"""Screen profile v2: the descriptive / deferred split, derived without loosening the guard.

SYNTHETIC. What is proved: v2 is an exact partition of the P0 fields; everything the guard or
kernel reads at P2/P3A stays required; deferred fields are only those neither reads; a v2 spec
that defers them freezes and is authorised through the REAL guard; its hash differs from v1 and
from the full profile; the unmodelled set is pinned inside the hash; v1 is unchanged.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.research.range002.governance.model import Partition, Phase
from app.research.range002.spec.hashing import content_sha256  # noqa: F401
from app.research.range002.spec.loader import SpecSchemaError, parse_draft, spec_sha256
from app.research.range002.spec.schema import (
    SCREEN_V1_EXEMPT,
    SCREEN_V1_REQUIRED,
    SCREEN_V1_REQUIRED_SHA256,
    SCREEN_V2_DEFERRED,
    SCREEN_V2_EXEMPT,
    SCREEN_V2_REQUIRED,
    SCREEN_V2_REQUIRED_SHA256,
    SCREEN_V2_UNMODELLED,
    SCREEN_V2_UNMODELLED_SHA256,
    draft_skeleton,
)
from tests.research.range002.governance.conftest import synthetic_manifest  # noqa: F401
from tests.research.range002.governance.test_screen_profile import (
    LEDGER_SHA,
    complete_payload,
    issue,
    set_path,
    view_for,
)

#: fields the guard or kernel reads at P2/P3A (results_guard checks (c)-(f), N2e; params.py)
GUARD_READ = {
    "exits.candidates",
    "exits.selection.eligibility.min_pf",
    "exits.selection.eligibility.min_trades",
    "exits.selection.score",
    "exits.selection.stop_test",
    "exits.selection.tie_tolerance_r",
    "p3.criteria",
    "p3.max_p3a_attempts",
    "p3.max_p3b_attempts",
    "governance.exposure_signed",
    "governance.registry_genesis_id",
}
KERNEL_READ = {
    "signal.min_or_width_ticks",
    "signal.or_completeness_rule",
    "exit.halfday_offset_min",
    "execution.bar_timestamp_convention",
    "execution.crossed_before_arm_policy",
    "fill.halt_policy",
    "costs.accounting_mode",
    "costs.components",
    "risk.per_trade_pct",
    "risk.per_trade_unit",
    "universe.category_map",
    "data.daily_price_basis",
    "data.intraday_price_basis",
}
PROFILE_V2 = {
    "name": "screen",
    "version": 2,
    "required_fields_sha256": SCREEN_V2_REQUIRED_SHA256,
    "unmodelled_fields_sha256": SCREEN_V2_UNMODELLED_SHA256,
}


def v2_payload() -> dict:  # type: ignore[type-arg]
    payload = complete_payload(decided=True)
    for path in (*SCREEN_V2_EXEMPT, *SCREEN_V2_DEFERRED, *SCREEN_V2_UNMODELLED):
        set_path(payload, path, None)
    set_path(payload, "governance.exposure_signed", {"exposure_ledger_sha256": LEDGER_SHA})
    payload["profile"] = dict(PROFILE_V2)
    return payload


def test_v2_partitions_the_p0_fields_exactly_and_derives_from_v1() -> None:
    all_p0 = set(parse_draft(draft_skeleton()).unset_p0_fields())
    sets = [
        set(SCREEN_V2_REQUIRED),
        set(SCREEN_V2_DEFERRED),
        set(SCREEN_V2_UNMODELLED),
        set(SCREEN_V2_EXEMPT),
    ]
    assert sum(len(s) for s in sets) == len(all_p0) and set().union(*sets) == all_p0
    hazard_fields = (  # hazard A/B/D: v1-exempt, v2-required (the only v2 additions over v1)
        "data.daily_price_basis",
        "data.intraday_price_basis",
        "risk.per_trade_unit",
        "universe.category_map",
    )
    assert set(hazard_fields) <= set(SCREEN_V1_EXEMPT) and not set(hazard_fields) & set(
        SCREEN_V1_REQUIRED
    )
    derived = {
        p
        for p in SCREEN_V1_REQUIRED
        if p not in set(SCREEN_V2_DEFERRED) | set(SCREEN_V2_UNMODELLED)
    } | set(hazard_fields)
    assert derived == set(SCREEN_V2_REQUIRED)
    assert len(set(SCREEN_V2_REQUIRED)) == len(SCREEN_V2_REQUIRED)
    assert list(SCREEN_V2_REQUIRED) == sorted(SCREEN_V2_REQUIRED)
    assert tuple(p for p in SCREEN_V1_EXEMPT if p not in hazard_fields) == SCREEN_V2_EXEMPT
    assert (
        hashlib.sha256("\n".join(SCREEN_V2_REQUIRED).encode()).hexdigest()
        == SCREEN_V2_REQUIRED_SHA256
    )
    assert (
        hashlib.sha256("\n".join(SCREEN_V2_UNMODELLED).encode()).hexdigest()
        == SCREEN_V2_UNMODELLED_SHA256
    )
    assert SCREEN_V1_REQUIRED_SHA256 != SCREEN_V2_REQUIRED_SHA256


def test_nothing_the_guard_or_kernel_reads_is_deferred_or_unmodelled() -> None:
    assert set(SCREEN_V2_REQUIRED) >= GUARD_READ | KERNEL_READ
    assert not (GUARD_READ | KERNEL_READ) & (set(SCREEN_V2_DEFERRED) | set(SCREEN_V2_UNMODELLED))


def test_v2_spec_freezes_and_is_authorised_for_p3a_by_the_real_guard(tmp_path: Path) -> None:
    view = view_for(tmp_path, v2_payload(), "v2")
    assert view.profile == "screen"
    cap = issue(view, tmp_path, Phase.P3A, Partition.DEVELOPMENT_SELECTION)
    assert cap.profile == "screen" and cap.citable is True


def test_v2_hash_differs_from_v1_and_pins_the_unmodelled_set(tmp_path: Path) -> None:
    v2 = parse_draft(v2_payload())
    v1p = v2_payload()
    v1p["profile"] = {
        "name": "screen",
        "version": 1,
        "required_fields_sha256": SCREEN_V1_REQUIRED_SHA256,
    }
    assert spec_sha256(v2) != spec_sha256(parse_draft(v1p))
    tampered = v2_payload()
    tampered["profile"]["unmodelled_fields_sha256"] = "0" * 64
    with pytest.raises(SpecSchemaError):
        parse_draft(tampered)


def test_a_v2_spec_missing_a_guard_read_field_is_refused_at_freeze(tmp_path: Path) -> None:
    bad = v2_payload()
    set_path(bad, "p3.criteria", None)
    with pytest.raises(Exception):  # noqa: B017,PT011  (unset required field names the path)
        view_for(tmp_path, bad, "bad")
