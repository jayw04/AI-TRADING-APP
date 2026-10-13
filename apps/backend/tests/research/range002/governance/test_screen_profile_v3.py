"""Screen profile v3 (cost-aware revision): the cost-to-risk ceiling must be named explicitly.

SYNTHETIC. Old specs keep their hashes (absent field == rule disabled, no hidden default); a v3
spec with the ceiling absent or null is an incomplete specification and is refused at freeze.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.research.range002.governance.model import Partition, Phase
from app.research.range002.spec.loader import parse_draft, spec_sha256
from app.research.range002.spec.schema import (
    SCREEN_V2_REQUIRED,
    SCREEN_V2_UNMODELLED_SHA256,
    SCREEN_V3_REQUIRED,
    SCREEN_V3_REQUIRED_SHA256,
)
from tests.research.range002.governance.test_screen_profile import issue, set_path, view_for
from tests.research.range002.governance.test_screen_profile_v2 import v2_payload

PROFILE_V3 = {
    "name": "screen",
    "version": 3,
    "required_fields_sha256": SCREEN_V3_REQUIRED_SHA256,
    "unmodelled_fields_sha256": SCREEN_V2_UNMODELLED_SHA256,
}


def v3_payload(ceiling: float | None = 0.10) -> dict:  # type: ignore[type-arg]
    payload = v2_payload()
    payload["profile"] = dict(PROFILE_V3)
    payload["signal"]["max_cost_to_risk"] = ceiling
    return payload


def test_v3_required_is_v2_plus_exactly_the_ceiling() -> None:
    assert set(SCREEN_V3_REQUIRED) == set(SCREEN_V2_REQUIRED) | {"signal.max_cost_to_risk"}
    assert list(SCREEN_V3_REQUIRED) == sorted(SCREEN_V3_REQUIRED)
    digest = hashlib.sha256("\n".join(SCREEN_V3_REQUIRED).encode()).hexdigest()
    assert digest == SCREEN_V3_REQUIRED_SHA256


def test_v3_spec_with_an_explicit_ceiling_freezes_and_is_authorised(tmp_path: Path) -> None:
    view = view_for(tmp_path, v3_payload(0.10), "v3")
    assert view.profile == "screen"
    cap = issue(view, tmp_path, Phase.P3A, Partition.DEVELOPMENT_SELECTION)
    assert cap.citable is True


def test_v3_spec_without_the_ceiling_is_refused_at_freeze(tmp_path: Path) -> None:
    absent = v3_payload()
    del absent["signal"]["max_cost_to_risk"]
    for name, payload in (("null", v3_payload(None)), ("absent", absent)):
        assert parse_draft(payload).unset_p0_fields() == ["signal.max_cost_to_risk"]
        with pytest.raises(Exception):  # noqa: B017,PT011  (unset required field names the path)
            view_for(tmp_path, payload, name)


def test_legacy_specs_keep_their_hash_with_the_rule_disabled() -> None:
    legacy = v2_payload()
    assert "max_cost_to_risk" not in legacy["signal"]
    h_absent = spec_sha256(parse_draft(legacy))
    with_null = v2_payload()
    set_path(with_null, "signal.max_cost_to_risk", None)
    assert spec_sha256(parse_draft(with_null)) == h_absent
    assert parse_draft(legacy).signal.max_cost_to_risk is None  # disabled, never defaulted
    # naming a ceiling changes the hash; v3 differs from v2 with the same ceiling
    v2c = v2_payload()
    set_path(v2c, "signal.max_cost_to_risk", 0.10)
    assert spec_sha256(parse_draft(v2c)) != h_absent
    assert spec_sha256(parse_draft(v2c)) != spec_sha256(parse_draft(v3_payload(0.10)))
