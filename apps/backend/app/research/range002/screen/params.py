"""Typed parameter extraction: the only place spec values reach the screen kernel.

Reads a parsed ``DraftSpec``, verifies its content hash equals the capability's spec hash, and
returns a fully non-null ``ScreenParams`` or raises ``ParamsUnsetError`` naming every field that
is null or outside what the kernel implements. Nothing is defaulted (R9).
"""

from __future__ import annotations

from datetime import time

from app.research.range002.governance.results_guard import requires_capability
from app.research.range002.screen.errors import ParamsUnsetError, SpecBindingError
from app.research.range002.screen.types import (
    HALT_POLICY_UNEXECUTABLE,
    SUPPORTED_FAMILIES,
    SUPPORTED_INTRADAY_BASIS,
    ExitSpec,
    ScreenParams,
)
from app.research.range002.spec.loader import spec_sha256
from app.research.range002.spec.schema import SCREEN_V2_UNMODELLED, DraftSpec

_ARM_POLICIES = ("SKIP", "MARKET_AT_NEXT_ACTIVE_BAR_OPEN")
#: Parameter key under which a ``fixed_r`` candidate carries its R multiple. The spec leaves the
#: per-family vocabulary open (D19); this is the kernel's proposal, listed as unresolved.
R_MULTIPLE_KEY = "r_multiple"
TRAIL_KEY = "trail_r"
REMAINDER_KEY = "remainder"


def _positive(raw: object) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, int | float) or raw <= 0:
        return None
    return float(raw)


def _per_trade_fraction(value: float, unit: str) -> float | None:
    """The fraction of equity risked per trade, or None when it is outside the open (0, 1)."""
    frac = value / 100.0 if unit == "percent" else value
    return frac if 0.0 < frac < 1.0 else None


def _hhmmss(text: str) -> time:
    hh, mm, ss = (int(p) for p in text.split(":"))
    return time(hh, mm, ss)


@requires_capability
def extract_params(capability: object, draft: DraftSpec) -> ScreenParams:
    sha = spec_sha256(draft)
    if sha != getattr(capability, "spec_sha256", None):
        raise SpecBindingError("draft spec hash differs from the capability's spec hash")
    problems: list[str] = []
    s, e, f, c, r, x = (
        draft.signal,
        draft.exit,
        draft.fill,
        draft.costs,
        draft.risk,
        draft.execution,
    )

    if draft.data.feed != "sip":
        problems.append("data.feed must be 'sip'")
    gap = s.or_completeness_rule
    if type(gap) is not int or gap < 0:
        problems.append(
            "signal.or_completeness_rule must be an int: max DATA_GAP minutes in the OR"
        )
    if s.min_or_width_ticks is None:
        problems.append("signal.min_or_width_ticks is null")
    if e.halfday_offset_min is None:
        problems.append("exit.halfday_offset_min is null")
    if c.accounting_mode != "all_in":
        problems.append(
            "costs.accounting_mode must be 'all_in' (itemized_additive not implemented)"
        )
    if r.per_trade_pct is None:
        problems.append("risk.per_trade_pct is null")
    if r.per_trade_unit is None:
        problems.append("risk.per_trade_unit is null (must be 'percent' or 'fraction')")
    fraction: float | None = None
    if r.per_trade_pct is not None and r.per_trade_unit is not None:
        fraction = _per_trade_fraction(float(r.per_trade_pct), r.per_trade_unit)
        if fraction is None:
            problems.append(
                f"risk.per_trade_pct={r.per_trade_pct} with unit {r.per_trade_unit!r} derives a "
                "per-trade fraction outside the open interval (0, 1)"
            )
    ibasis = draft.data.intraday_price_basis
    if ibasis != SUPPORTED_INTRADAY_BASIS:
        problems.append(
            f"data.intraday_price_basis must be {SUPPORTED_INTRADAY_BASIS!r}, got {ibasis!r}"
        )
    if x.bar_timestamp_convention != "start":
        problems.append(
            "execution.bar_timestamp_convention must be 'start': end-stamped bars are not "
            "implemented and timestamps are never shifted by assumption"
        )
    if x.crossed_before_arm_policy not in _ARM_POLICIES:
        problems.append(f"execution.crossed_before_arm_policy must be one of {_ARM_POLICIES}")
    if f.halt_policy != HALT_POLICY_UNEXECUTABLE:
        problems.append(f"fill.halt_policy must be {HALT_POLICY_UNEXECUTABLE!r}")
    if f.same_bar_policy != "worst_case":
        problems.append("fill.same_bar_policy must be 'worst_case'")

    cands = draft.exits.candidates
    specs: list[ExitSpec] = []
    if not cands:
        problems.append("exits.candidates is unset")
    else:
        for cand in cands:
            if cand.family not in SUPPORTED_FAMILIES:
                problems.append(
                    f"exits.candidates[{cand.id}].family {cand.family!r} not implemented"
                )
                continue
            mult: float | None = None
            trail: float | None = None
            rem: str | None = None
            if cand.family == "fixed_r":
                mult = _positive(cand.params.get(R_MULTIPLE_KEY))
                if mult is None:
                    problems.append(
                        f"exits.candidates[{cand.id}].params.{R_MULTIPLE_KEY} must be > 0"
                    )
                    continue
            if cand.family == "scale_out":
                rem = cand.params.get(REMAINDER_KEY)  # type: ignore[assignment]
                if rem not in ("eod", "trail"):
                    problems.append(
                        f"exits.candidates[{cand.id}].params.{REMAINDER_KEY} must be eod|trail"
                    )
                    continue
            if cand.family == "trailing" or (cand.family == "scale_out" and rem == "trail"):
                trail = _positive(cand.params.get(TRAIL_KEY))
                if trail is None:
                    problems.append(f"exits.candidates[{cand.id}].params.{TRAIL_KEY} must be > 0")
                    continue
            specs.append(ExitSpec(cand.id, cand.family, mult, trail, rem))
    if problems:
        raise ParamsUnsetError("; ".join(problems))
    assert type(gap) is int
    assert s.min_or_width_ticks is not None and e.halfday_offset_min is not None
    assert r.per_trade_pct is not None and x.bar_timestamp_convention is not None
    assert r.per_trade_unit is not None and fraction is not None and ibasis is not None
    assert x.crossed_before_arm_policy is not None and c.accounting_mode is not None
    draft_values = draft.model_dump(mode="python")

    def _present(path: str) -> bool:
        node: object = draft_values
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return False
            node = node[part]
        return node is not None and node != "" and node != []

    unmodelled = tuple(p for p in SCREEN_V2_UNMODELLED if _present(p))
    return ScreenParams(
        spec_sha256=sha,
        feed=draft.data.feed,
        or_start=_hhmmss(s.or_start),
        or_end=_hhmmss(s.or_end),
        entry_start=_hhmmss(s.entry_window[0]),
        entry_end=_hhmmss(s.entry_window[1]),
        tick_offset=s.tick_offset,
        max_entries_per_symbol_day=s.max_entries_per_symbol_day,
        min_or_width_ticks=float(s.min_or_width_ticks),
        or_max_gap_minutes=gap,
        eod_flat=_hhmmss(e.eod_flat),
        halfday_offset_min=float(e.halfday_offset_min),
        same_bar_policy=f.same_bar_policy,
        base_bps_per_side=float(c.base_bps_per_side),
        stress_bps_per_side=float(c.stress_bps_per_side),
        accounting_mode=c.accounting_mode,
        per_trade_pct=float(r.per_trade_pct),
        per_trade_pct_unit=r.per_trade_unit,
        per_trade_fraction=fraction,
        intraday_price_basis=ibasis,
        bar_timestamp_convention=x.bar_timestamp_convention,
        crossed_before_arm_policy=x.crossed_before_arm_policy,
        halt_policy=HALT_POLICY_UNEXECUTABLE,
        candidates=tuple(specs),
        unmodelled_execution=unmodelled,
        max_cost_to_risk=(float(s.max_cost_to_risk) if s.max_cost_to_risk is not None else None),
    )
