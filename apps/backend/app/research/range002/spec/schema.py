"""RANGE-002 spec schema (Implementation Plan v0.5 WP0.2, Appendix A, Addendum A1).

Two stages, one shape:

* :class:`DraftSpec` -- the Appendix A skeleton. Every ``P0:`` field is a REQUIRED KEY whose value
  may be ``None``. There is deliberately no default anywhere for a P0 field (rule R9): a missing
  key is a schema error, an explicit ``null`` is "not decided yet". Values that the skeleton
  states outright (feed=sip, min_price 10, 5/15 bps, partitions, gate thresholds ...) are
  asserted equal to the skeleton, so a draft cannot quietly loosen them.
* :class:`FrozenSpec` -- a DraftSpec in which every P0 field is set. Construction fails with a
  :class:`UnsetP0FieldsError` that NAMES every unset field. It never invents a value.

Shape-checks that only need the data (candidate count 1..8, family set, unique ids, partition
layout) run on the draft as soon as the data is present. Nothing here knows the value of any
open decision D01-D19; open-ended fields are typed loosely on purpose.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Sequence
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    JsonValue,
    field_validator,
    model_validator,
)

from app.research.range002.spec.genesis import is_canonical_uuid4
from app.research.range002.spec.limits import MAX_ATTEMPT_LIMIT

EXIT_FAMILIES: tuple[str, ...] = ("time", "fixed_r", "trailing", "scale_out")
MAX_EXIT_CANDIDATES = 8

# Dotted paths that are legitimately null at freeze time (not P0 decisions).
# registration.trial_ledger_id is assigned by run_registry; `decision` is checked separately.
_NON_P0_NULLABLE = frozenset({"registration.trial_ledger_id", "profile"})

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]{0,31}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class UnsetP0FieldsError(ValueError):
    """A spec was asked to be frozen while P0 fields are still unset."""

    def __init__(self, fields: Sequence[str]) -> None:
        self.fields: tuple[str, ...] = tuple(fields)
        super().__init__(
            f"{len(self.fields)} P0 field(s) unset, spec cannot be frozen: "
            + ", ".join(self.fields)
        )


class DecisionRefError(ValueError):
    """The meeting-decision reference is absent or not usable. The freeze tool never fabricates
    one: every field comes from the recorded meeting minutes."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems: tuple[str, ...] = tuple(problems)
        super().__init__("meeting-decision reference problem(s): " + "; ".join(self.problems))


# --------------------------------------------------------------------------- helpers


def _equals(expected: Any) -> Callable[[Any], Any]:
    def check(value: Any) -> Any:
        if value != expected:
            raise ValueError(f"fixed by the spec skeleton: must be {expected!r}, got {value!r}")
        return value

    return check


def _eq(expected: Any) -> AfterValidator:
    return AfterValidator(_equals(expected))


def _hhmmss(value: str) -> str:
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d:[0-5]\d", value):
        raise ValueError(f"expected HH:MM:SS, got {value!r}")
    return value


def _positive(value: float | int | None) -> float | int | None:
    if value is not None and not (math.isfinite(value) and value > 0):
        raise ValueError(f"must be a finite positive number, got {value!r}")
    return value


def _non_negative(value: float | int | None) -> float | int | None:
    if value is not None and not (math.isfinite(value) and value >= 0):
        raise ValueError(f"must be a finite non-negative number, got {value!r}")
    return value


def _check_json_finite(value: Any, path: str = "") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite number at {path or '<root>'}")
    if isinstance(value, dict):
        for k, v in value.items():
            _check_json_finite(v, f"{path}.{k}" if path else str(k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _check_json_finite(v, f"{path}[{i}]")


def _category_map(value: tuple[str, ...] | None) -> tuple[str, ...] | None:
    if value is not None:
        if any(not isinstance(v, str) or not v.strip() or v != v.strip() for v in value):
            raise ValueError("category_map entries must be non-blank, trimmed strings")
        if len(set(value)) != len(value):
            raise ValueError("category_map entries must be unique")
    return value


def _basis(value: str | None) -> str | None:
    if value is not None and (not value.strip() or value != value.strip()):
        raise ValueError("a price-basis tag must be a non-blank, trimmed string")
    return value


_OptCategoryMap = Annotated[tuple[str, ...] | None, AfterValidator(_category_map)]
_OptBasis = Annotated[str | None, AfterValidator(_basis)]
OptPos = Annotated[float | None, AfterValidator(_positive)]
OptPosInt = Annotated[int | None, AfterValidator(_positive)]
OptNonNeg = Annotated[float | None, AfterValidator(_non_negative)]


class _Model(BaseModel):
    # strict: no lax coercion ("300" -> 300, 1 -> True ...). Validate decoded payloads through
    # ``loader.parse_draft`` (JSON mode), where ISO date strings and arrays are the legal forms.
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


# JSON-ish P0 field whose shape is itself an open decision.
OpenValue = JsonValue | None


class _OpenFieldsModel(_Model):
    @model_validator(mode="after")
    def _finite_open_values(self) -> Any:
        for name in type(self).model_fields:
            _check_json_finite(getattr(self, name), name)
        return self


# --------------------------------------------------------------------------- partitions

_Window = tuple[date, date]
_DEV_SEL = (date(2016, 1, 1), date(2019, 12, 31))
_DEV_CONF = (date(2020, 1, 1), date(2021, 12, 31))
_HOLDOUT = (date(2022, 1, 1), date(2025, 12, 31))
_EXPOSED = ((date(2026, 1, 1), date(2026, 7, 31)),)


def validate_partition_layout(windows: Iterable[tuple[str, date, date]]) -> None:
    """Windows must each be well formed, non-overlapping and listed in chronological order."""
    prev_name: str | None = None
    prev_end: date | None = None
    for name, start, end in windows:
        if start > end:
            raise ValueError(f"partition {name}: start {start} is after end {end}")
        if prev_end is not None and start <= prev_end:
            raise ValueError(
                f"partition {name} ({start}..{end}) overlaps or precedes {prev_name} "
                f"(ends {prev_end}); partitions must be disjoint and chronological"
            )
        prev_name, prev_end = name, end


class Partitions(_Model):
    development_selection: Annotated[_Window, _eq(_DEV_SEL)]  # P3a
    development_confirmation: Annotated[_Window, _eq(_DEV_CONF)]  # P3b
    holdout: Annotated[_Window, _eq(_HOLDOUT)]
    exposed: Annotated[tuple[_Window, ...], _eq(_EXPOSED)]

    @model_validator(mode="after")
    def _layout(self) -> Partitions:
        windows: list[tuple[str, date, date]] = [
            ("development_selection", *self.development_selection),
            ("development_confirmation", *self.development_confirmation),
            ("holdout", *self.holdout),
        ]
        windows += [(f"exposed[{i}]", *w) for i, w in enumerate(self.exposed)]
        validate_partition_layout(windows)
        return self


# --------------------------------------------------------------------------- exits (Addendum A1)

ExitFamily = Literal["time", "fixed_r", "trailing", "scale_out"]


class ExitCandidate(_Model):
    id: str
    family: ExitFamily
    # Parameter vocabulary per family is part of the open D19 decision, so only the value types
    # are constrained here (R units are plain numbers).
    params: dict[str, int | float | str]

    @field_validator("id")
    @classmethod
    def _id_ok(cls, v: str) -> str:
        if not _ID_RE.fullmatch(v):
            raise ValueError(f"candidate id {v!r} must match {_ID_RE.pattern}")
        return v

    @field_validator("params")
    @classmethod
    def _params_finite(cls, v: dict[str, Any]) -> dict[str, Any]:
        _check_json_finite(v)
        return v


class ExitEligibility(_Model):
    min_trades: OptPosInt
    min_pf: OptPos


class ExitSelection(_Model):
    score: str | None
    tie_tolerance_r: OptNonNeg
    eligibility: ExitEligibility
    stop_test: str | None

    @field_validator("score", "stop_test")
    @classmethod
    def _not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("must not be blank (use null for 'not decided')")
        return v


class Exits(_Model):
    candidates: tuple[ExitCandidate, ...] | None
    complexity_order: tuple[ExitFamily, ...] | None
    selection: ExitSelection

    @field_validator("candidates")
    @classmethod
    def _candidates_ok(cls, v: tuple[ExitCandidate, ...] | None) -> Any:
        if v is None:
            return v
        if not 1 <= len(v) <= MAX_EXIT_CANDIDATES:
            raise ValueError(
                f"exits.candidates must have 1..{MAX_EXIT_CANDIDATES} entries, got {len(v)}"
            )
        ids = [c.id for c in v]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate candidate id(s): {', '.join(dupes)}")
        return v

    @field_validator("complexity_order")
    @classmethod
    def _order_ok(cls, v: tuple[str, ...] | None) -> Any:
        if v is not None and (not v or len(set(v)) != len(v)):
            raise ValueError("complexity_order must be non-empty with no repeated family")
        return v

    @model_validator(mode="after")
    def _order_covers_candidates(self) -> Exits:
        if self.candidates is not None and self.complexity_order is not None:
            missing = sorted({c.family for c in self.candidates} - set(self.complexity_order))
            if missing:
                raise ValueError(
                    "complexity_order does not rank candidate famil(ies): " + ", ".join(missing)
                )
        return self


# --------------------------------------------------------------------------- sections


class Registration(_OpenFieldsModel):
    trial_ledger_id: str | None  # set by run_registry, not a P0 decision
    related_programs: OpenValue  # P0: D09


class Universe(_Model):
    instrument_types: Annotated[tuple[str, ...], _eq(("common_stock",))]
    n: OptPosInt  # P0: D03
    #: P0: the exact vendor category strings treated as common stock (hash-bound, hazard A)
    category_map: _OptCategoryMap
    min_price: Annotated[float, _eq(10.0)]
    adv_window_days: Annotated[int, _eq(20)]
    rebuild: Annotated[str, _eq("monthly")]
    include_delisted: Annotated[bool, _eq(True)]


class Data(_Model):
    feed: Literal["sip"]  # asserted (R6)
    vendor: str | None  # P0: D03
    bar: Annotated[str, _eq("1min")]
    session: Annotated[str, _eq("rth")]
    tz: Annotated[str, _eq("America/New_York")]
    fetch_mode: str | None  # P0: D11
    #: P0 (hazard A/B): the daily price pairing and the intraday bar basis, inside the spec hash.
    #: Only one compatible pair is implemented; the join check lives in the data adapters.
    daily_price_basis: _OptBasis
    intraday_price_basis: _OptBasis


class Signal(_OpenFieldsModel):
    missing_minute_classes: Annotated[tuple[str, ...], _eq(("NO_TRADE_MINUTE", "DATA_GAP"))]
    or_start: Annotated[str, _eq("09:30:00")]
    or_end: Annotated[str, _eq("09:59:59")]
    or_completeness_rule: OpenValue  # P0: D05
    min_or_width_ticks: OptPos  # P0: D05
    entry_window: Annotated[tuple[str, str], _eq(("10:00:00", "14:59:59"))]
    tick_offset: Annotated[int, _eq(1)]
    max_entries_per_symbol_day: Annotated[int, _eq(1)]


class Exit(_Model):
    stop: Annotated[str, _eq("or_low")]
    eod_flat: Annotated[str, _eq("15:55:00")]
    halfday_offset_min: OptNonNeg  # P0: D05


class Fill(_OpenFieldsModel):
    slippage_model: OpenValue  # P0: D05
    same_bar_policy: Annotated[str, _eq("worst_case")]
    halt_policy: OpenValue  # P0: D05


class Costs(_OpenFieldsModel):
    base_bps_per_side: Annotated[float, _eq(5.0)]
    stress_bps_per_side: Annotated[float, _eq(15.0)]
    accounting_mode: Literal["all_in", "itemized_additive"] | None  # P0: D15
    components: OpenValue  # P0: itemized


class Risk(_Model):
    per_trade_pct: OptPos  # P0 (the 0.25 proposal lives in the plan, not here)
    #: P0 (hazard D): the unit of ``per_trade_pct``; "percent" (0.25 = 0.25 %) or "fraction"
    #: (0.0025). Inside the spec hash, so the same number under another unit is another spec.
    per_trade_unit: Literal["percent", "fraction"] | None
    per_name_cap: OptPos
    gross_cap: OptPos
    max_concurrent: OptPosInt
    daily_loss_limit: OptPos
    max_participation: OptPos
    fill_risk_tolerance: OptNonNeg


class RandomEntry(_OpenFieldsModel):
    repetitions: OptPosInt
    seed: int | None
    invalid_draw_policy: OpenValue


class NaiveOrb(_OpenFieldsModel):
    definition: OpenValue


class Controls(_Model):
    random_entry: RandomEntry  # P0: D06
    naive_orb: NaiveOrb


class Bootstrap(_Model):
    # ruling C11: the method is NOT chosen anywhere in code or in the committed skeleton.
    method: str | None  # P0: D06
    cluster: Annotated[str, _eq("trading_day")]
    # Method-neutral: fixed length for a circular/moving block method, mean length for a
    # stationary method. What it means is fixed by `method` (D06), so nothing here presumes one.
    block_len: OptPos  # P0: D06
    reps: OptPosInt  # P0: D06
    ci_type: str | None  # P0: D06 (e.g. percentile; the owner chooses)
    confidence_level: float | None  # P0: D06
    seed: int | None  # P0: D06

    @field_validator("confidence_level")
    @classmethod
    def _conf_ok(cls, v: float | None) -> float | None:
        if v is not None and not (0.0 < v < 1.0):
            raise ValueError(f"must be in (0, 1), got {v!r}")
        return v

    @field_validator("method", "ci_type")
    @classmethod
    def _method_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("must not be blank (use null for 'not decided')")
        return v


class Regime(_OpenFieldsModel):
    definition: OpenValue  # P0: D12
    criterion: OpenValue


class Stats(_OpenFieldsModel):
    bootstrap: Bootstrap
    hypothesis_family: OpenValue  # P0: D02
    adjustment: Literal["holm", "fixed_sequence"]  # skeleton: holm (ruling C6), or per D02
    alpha_one_sided: float | None  # P0: D06
    regime: Regime

    @field_validator("alpha_one_sided")
    @classmethod
    def _alpha_ok(cls, v: float | None) -> float | None:
        if v is not None and not (0.0 < v < 1.0):
            raise ValueError(f"must be in (0, 1), got {v!r}")
        return v


class Execution(_OpenFieldsModel):  # P0: D14
    bar_timestamp_convention: Literal["start", "end"] | None
    vendor_delay_ms: OptNonNeg
    submit_latency_ms: OptNonNeg
    ack_latency_ms: OptNonNeg
    crossed_before_arm_policy: (
        Literal["SKIP", "MARKET_AT_NEXT_ACTIVE_BAR_OPEN", "REQUIRE_RETRACE"] | None
    )
    order_type: Literal["stop_market", "stop_limit", "emulated"] | None
    stop_protection_policy: OpenValue
    tie_break: OpenValue
    eod_lead_s: OptNonNeg
    order_reservation_policy: OpenValue


class P3(_OpenFieldsModel):
    criteria: OpenValue  # P0: D17
    # Attempt limits (round 4, N2e): P0 decision values, owner-selected, NO default. The results
    # guard refuses P3A / P3B while the matching field is unset or the number of recorded runs
    # of that phase for this spec hash (failed and aborted included) exceeds it.
    max_p3a_attempts: OptPosInt  # P0
    max_p3b_attempts: OptPosInt  # P0

    @field_validator("max_p3a_attempts", "max_p3b_attempts")
    @classmethod
    def _within_technical_bound(cls, v: int | None) -> int | None:
        # Technical upper bound only (see spec/limits.py); the value itself is an owner decision.
        if v is not None and v > MAX_ATTEMPT_LIMIT:
            raise ValueError(f"must be <= {MAX_ATTEMPT_LIMIT} (technical bound), got {v}")
        return v


class Gates(_OpenFieldsModel):
    basis: Literal["portfolio_constrained", "signal_level"] | None  # P0: D18
    trade_unit: OpenValue  # P0: D18
    min_trades: Annotated[int, _eq(300)]
    pf_base: Annotated[float, _eq(1.30)]
    stress_mean_positive: Annotated[bool, _eq(True)]
    yearly: OpenValue  # P0: D04
    # Ruling C3 / D10: REQUIRED KEY, NO DEFAULT. The platform > 50% gate applies until a
    # formal D10 deviation is signed, so the spec must state which regime it runs under.
    win_rate: OpenValue
    max_dd: OpenValue  # P0: D10
    redundancy_corr_max: Annotated[float, _eq(0.85)]


class P5(_OpenFieldsModel):
    account_id: str | None  # P0: D07
    min_days: Annotated[int, _eq(60)]
    min_trades: Annotated[int, _eq(100)]
    max_cost_ratio: Annotated[float, _eq(1.5)]
    degradation_tolerance: OpenValue
    cost_ratio_contract: OpenValue  # P0: D07
    shadow_acceptance: OpenValue  # P0: D16


class Diagnostics(_OpenFieldsModel):
    taxonomy: OpenValue  # P0: D16 (explanatory only)


class Governance(_OpenFieldsModel):
    # D01: the recorded conclusion on exposure / holdout applicability. Content is the
    # meeting record's (which decision, which exposure-ledger sha256); the schema does not shape it.
    exposure_signed: OpenValue  # P0: D01
    # Round 4 (N1): the genesis id of the one run registry this spec may open runs in. Created by
    # RunRegistry.enroll_new and copied here by the owner BEFORE freezing; unset at draft, no
    # default. A canonical lowercase UUIDv4 string (uuid.uuid4()). Level 1: an identity marker
    # that binds a spec to a registry file's genesis row; it is NOT authentication.
    registry_genesis_id: str | None  # P0

    @field_validator("registry_genesis_id")
    @classmethod
    def _genesis_ok(cls, v: str | None) -> str | None:
        if v is not None and not is_canonical_uuid4(v):
            raise ValueError("must be a canonical lowercase UUIDv4 registry genesis id")
        return v


DECISION_VALUES = ("approved", "revise", "defer", "stop")
DECISION_SCOPES = ("build", "run")
_PARTITION_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


def _repo_relative(value: str) -> str:
    """A committed minutes file's repo-relative path: forward slashes, no absolute form, no
    ``..`` or ``.`` segment, no empty segment, no drive letter."""
    if not value.strip() or value != value.strip():
        raise ValueError("minutes_path must be a non-blank, trimmed string")
    if "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise ValueError("minutes_path must be a repo-relative path with forward slashes")
    if any(seg in ("", ".", "..") for seg in value.split("/")):
        raise ValueError("minutes_path must not contain empty, '.' or '..' segments")
    return value


class DecisionRef(_Model):
    """Reference to the decision that covers this spec (pure data, no authority of its own).
    ``record_kind`` is ``meeting_minutes`` (a weekly-meeting decision) or ``owner_instruction`` (an
    explicit between-meeting instruction by the owner, summarized in the next weekly minutes);
    both kinds carry the same scope/version binding and get identical checks, and there is no
    default. ``decision_date`` is the date of the meeting OR of the owner's instruction. The
    minutes file is the decision record; this block only POINTS at it and
    binds the decision to an exact spec version by hash. It is held OUTSIDE the hashed payload
    (as the block it replaced was): the decision attests TO the hash.

    ``minutes_sha256`` is the SHA-256 of the committed minutes file's bytes; the guard re-reads the
    file and compares. ``spec_sha256`` is filled by the freeze tool, never by hand: ``None`` only
    in a draft. Only ``decision == "approved"`` authorizes anything, and a results run needs
    ``"run"`` in ``scope`` and the requested partition in ``partitions``.
    """

    decision_date: date
    record_kind: Literal["meeting_minutes", "owner_instruction"]
    minutes_path: Annotated[str, AfterValidator(_repo_relative)]
    minutes_sha256: str
    decision: Literal["approved", "revise", "defer", "stop"]
    scope: tuple[Literal["build", "run"], ...]
    partitions: tuple[str, ...]
    strategy_version: str
    baseline_id: str
    spec_sha256: str | None

    @field_validator("minutes_sha256", "spec_sha256")
    @classmethod
    def _sha_ok(cls, v: str | None) -> str | None:
        if v is not None and not _SHA_RE.fullmatch(v):
            raise ValueError("must be a lowercase 64-hex sha256")
        return v

    @field_validator("strategy_version", "baseline_id")
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v.strip() or v != v.strip():
            raise ValueError("must be a non-blank, trimmed string")
        return v

    @field_validator("scope")
    @classmethod
    def _scope_ok(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if not v:
            raise ValueError("scope must name at least one of 'build', 'run'")
        if len(set(v)) != len(v):
            raise ValueError("scope entries must be unique")
        return v

    @field_validator("partitions")
    @classmethod
    def _partitions_ok(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if any(not _PARTITION_NAME_RE.fullmatch(p) for p in v):
            raise ValueError("partition names must be upper-case identifiers such as 'HOLDOUT'")
        if len(set(v)) != len(v):
            raise ValueError("partition names must be unique")
        return v

    @model_validator(mode="after")
    def _scope_partitions_consistent(self) -> DecisionRef:
        if "run" in self.scope and not self.partitions:
            raise ValueError("a decision whose scope includes 'run' must name its partitions")
        if "run" not in self.scope and self.partitions:
            raise ValueError(
                "partitions may be named only by a decision whose scope includes 'run'"
            )
        return self


# --------------------------------------------------------------------------- screen profile (A-SCREEN, O-8 B)
#
# A *restricted screening profile*: a versioned, hashed declaration that a frozen spec is for the
# preliminary development screen only. The guard (results_guard) authorises such a spec for
# (P2, REPLAY_RNG001) and (P3A, DEVELOPMENT_SELECTION) and refuses every other phase. A spec with
# no ``profile`` block is the FULL profile and behaves exactly as before (its hash is unchanged:
# ``profile`` is omitted from the hash payload when absent). The required-field list is the
# profile's exact contract: it names every P0 field that affects signals, fills, costs, sample
# eligibility, selection or interpretation (whether or not the current kernel reads it).
# Everything else is EXEMPT and may stay null only because the profile cannot authorise P3B, P4,
# P5/PAPER or any broker operation. ``SCREEN_V1_REQUIRED`` and ``SCREEN_V1_EXEMPT`` must
# partition the P0 field set exactly (tested), so a new P0 field forces an explicit decision.
SCREEN_PROFILE_NAME = "screen"
SCREEN_PROFILE_VERSION = 1
SCREEN_V1_REQUIRED = (
    "controls.naive_orb.definition",
    "controls.random_entry.invalid_draw_policy",
    "controls.random_entry.repetitions",
    "controls.random_entry.seed",
    "costs.accounting_mode",
    "costs.components",
    "data.fetch_mode",
    "data.vendor",
    "execution.ack_latency_ms",
    "execution.bar_timestamp_convention",
    "execution.crossed_before_arm_policy",
    "execution.eod_lead_s",
    "execution.order_reservation_policy",
    "execution.order_type",
    "execution.stop_protection_policy",
    "execution.submit_latency_ms",
    "execution.tie_break",
    "execution.vendor_delay_ms",
    "exit.halfday_offset_min",
    "exits.candidates",
    "exits.complexity_order",
    "exits.selection.eligibility.min_pf",
    "exits.selection.eligibility.min_trades",
    "exits.selection.score",
    "exits.selection.stop_test",
    "exits.selection.tie_tolerance_r",
    "fill.halt_policy",
    "fill.slippage_model",
    "gates.basis",
    "gates.trade_unit",
    "governance.exposure_signed",
    "governance.registry_genesis_id",
    "p3.criteria",
    "p3.max_p3a_attempts",
    "p3.max_p3b_attempts",
    "registration.related_programs",
    "risk.per_trade_pct",
    "signal.min_or_width_ticks",
    "signal.or_completeness_rule",
    "stats.alpha_one_sided",
    "stats.bootstrap.block_len",
    "stats.bootstrap.ci_type",
    "stats.bootstrap.confidence_level",
    "stats.bootstrap.method",
    "stats.bootstrap.reps",
    "stats.bootstrap.seed",
    "stats.hypothesis_family",
    "universe.n",
)
SCREEN_V1_EXEMPT = (
    # Hazard A/B/D fields: exempt in v1 (its required digest and behaviour are unchanged), REQUIRED
    # in v2 (SCREEN_V2_REQUIRED below).
    "data.daily_price_basis",
    "data.intraday_price_basis",
    "risk.per_trade_unit",
    "universe.category_map",
    "p5.account_id",
    "p5.cost_ratio_contract",
    "p5.degradation_tolerance",
    "p5.shadow_acceptance",
    "diagnostics.taxonomy",
    "gates.max_dd",
    "gates.win_rate",
    "gates.yearly",
    "risk.daily_loss_limit",
    "risk.fill_risk_tolerance",
    "risk.gross_cap",
    "risk.max_concurrent",
    "risk.max_participation",
    "risk.per_name_cap",
    "stats.regime.criterion",
    "stats.regime.definition",
)
#: sha256 of the newline-joined SCREEN_V1_REQUIRED (UTF-8); asserted by a test.
SCREEN_V1_REQUIRED_SHA256 = "fa3ed823e6764886d905d5d648bd346abf7bffcae87362b8e477397e876f2355"


# --------------------------------------------------------------------------- screen profile v2
#
# A versioned split of the v1 contract. v1 is untouched (its hash and tests stand). v2 separates
# what the DESCRIPTIVE screen needs from what only selection / advancement needs, WITHOUT
# loosening anything the guard itself reads at P2/P3A:
#   * the guard requires p3.criteria, exits.candidates, exits.selection.*, both attempt limits,
#     the exposure binding and the genesis id before it authorises a P3A run, so they stay
#     required in v2 (a v2 spec that omitted them would freeze and then be refused);
#   * DEFERRED fields are read by neither the guard (at P2/P3A) nor the kernel; they are required
#     again before statistical selection or advancement. A spec that defers them has a different
#     hash from the spec that later sets them, so stage 2 on the same run needs an owner decision
#     (see the review notes); nothing here pre-empts it;
#   * UNMODELLED fields are execution settings the bar-level kernel does not simulate. They may
#     stay null; if present they are carried into the params and every report as UNMODELLED, so a
#     non-null value never implies simulated execution realism.
SCREEN_V2_DEFERRED = (
    "controls.naive_orb.definition",
    "controls.random_entry.invalid_draw_policy",
    "controls.random_entry.repetitions",
    "controls.random_entry.seed",
    "exits.complexity_order",
    "registration.related_programs",
    "stats.alpha_one_sided",
    "stats.bootstrap.block_len",
    "stats.bootstrap.ci_type",
    "stats.bootstrap.confidence_level",
    "stats.bootstrap.method",
    "stats.bootstrap.reps",
    "stats.bootstrap.seed",
    "stats.hypothesis_family",
)
SCREEN_V2_UNMODELLED = (
    "execution.ack_latency_ms",
    "execution.eod_lead_s",
    "execution.order_reservation_policy",
    "execution.order_type",
    "execution.stop_protection_policy",
    "execution.submit_latency_ms",
    "execution.tie_break",
    "execution.vendor_delay_ms",
    "fill.slippage_model",
)
# v1 required minus DEFERRED minus UNMODELLED, PLUS the hazard A/B/D fields (v1-exempt), as a
# literal (a test asserts the derivation).
SCREEN_V2_REQUIRED = (
    "costs.accounting_mode",
    "costs.components",
    "data.daily_price_basis",
    "data.fetch_mode",
    "data.intraday_price_basis",
    "data.vendor",
    "execution.bar_timestamp_convention",
    "execution.crossed_before_arm_policy",
    "exit.halfday_offset_min",
    "exits.candidates",
    "exits.selection.eligibility.min_pf",
    "exits.selection.eligibility.min_trades",
    "exits.selection.score",
    "exits.selection.stop_test",
    "exits.selection.tie_tolerance_r",
    "fill.halt_policy",
    "gates.basis",
    "gates.trade_unit",
    "governance.exposure_signed",
    "governance.registry_genesis_id",
    "p3.criteria",
    "p3.max_p3a_attempts",
    "p3.max_p3b_attempts",
    "risk.per_trade_pct",
    "risk.per_trade_unit",
    "signal.min_or_width_ticks",
    "signal.or_completeness_rule",
    "universe.category_map",
    "universe.n",
)
#: v2 exempt = v1 exempt minus the hazard A/B/D fields that v2 requires, as a literal (an exact
#: partition of the P0 set with SCREEN_V2_REQUIRED / _DEFERRED / _UNMODELLED; a test asserts both).
SCREEN_V2_EXEMPT = (
    "p5.account_id",
    "p5.cost_ratio_contract",
    "p5.degradation_tolerance",
    "p5.shadow_acceptance",
    "diagnostics.taxonomy",
    "gates.max_dd",
    "gates.win_rate",
    "gates.yearly",
    "risk.daily_loss_limit",
    "risk.fill_risk_tolerance",
    "risk.gross_cap",
    "risk.max_concurrent",
    "risk.max_participation",
    "risk.per_name_cap",
    "stats.regime.criterion",
    "stats.regime.definition",
)
#: sha256 of the newline-joined SCREEN_V2_REQUIRED (UTF-8); asserted by a test.
SCREEN_V2_REQUIRED_SHA256 = "16f904a3094b375f32792201efb6fc6a40eb22ea46c9e26caeb978318ff96899"
#: sha256 of the newline-joined SCREEN_V2_UNMODELLED; part of the declaration, so the unmodelled
#: set is inside the spec hash and cannot be changed without changing the spec.
SCREEN_V2_UNMODELLED_SHA256 = "0298fe82ad0374a5139a0d739f49188081bf358a283edcb142c2b180725efb2c"


class ScreenProfileDecl(_Model):
    """The ``profile`` block of a v1 screen-profile spec. It is inside the spec hash."""

    name: Literal["screen"]
    version: Literal[1]
    required_fields_sha256: Annotated[str, _eq(SCREEN_V1_REQUIRED_SHA256)]


class ScreenProfileDeclV2(_Model):
    """v2: the descriptive/deferred split. It also pins its unmodelled-execution set, so that set
    is inside the spec hash and cannot change without changing the spec."""

    name: Literal["screen"]
    version: Literal[2]
    required_fields_sha256: Annotated[str, _eq(SCREEN_V2_REQUIRED_SHA256)]
    unmodelled_fields_sha256: Annotated[str, _eq(SCREEN_V2_UNMODELLED_SHA256)]


# --------------------------------------------------------------------------- top level


class DraftSpec(_Model):
    program: Literal["RANGE-002"]
    spec_version: Literal[1]
    registration: Registration
    universe: Universe
    data: Data
    signal: Signal
    exits: Exits
    exit: Exit
    fill: Fill
    costs: Costs
    risk: Risk
    partitions: Partitions
    controls: Controls
    stats: Stats
    execution: Execution
    p3: P3
    gates: Gates
    p5: P5
    diagnostics: Diagnostics
    governance: Governance
    #: the meeting-decision reference; null = no decision recorded yet. Outside the hash.
    decision: DecisionRef | None
    profile: ScreenProfileDecl | ScreenProfileDeclV2 | None = None

    @field_validator("spec_version", mode="before")
    @classmethod
    def _version_is_int(cls, v: Any) -> Any:
        if type(v) is not int:  # Literal[1] would otherwise admit True
            raise ValueError("spec_version must be the integer 1")
        return v

    def hashable_payload(self) -> dict[str, Any]:
        """The content the spec hash covers: everything except ``decision``.

        The decision attests TO the hash, so it cannot be inside it.
        """
        payload = self.model_dump(mode="json")
        payload.pop("decision")
        if payload.get("profile") is None:  # the FULL profile: hash unchanged by this feature
            payload.pop("profile", None)
        return payload

    def unset_p0_fields(self) -> list[str]:
        """Dotted paths of every P0 field that is still null/blank, sorted."""
        out: list[str] = []
        _walk_unset(self.model_dump(mode="python"), "", out)
        if self.profile is not None:  # screen profile: only its exact required list is enforced
            required = frozenset(
                SCREEN_V1_REQUIRED if self.profile.version == 1 else SCREEN_V2_REQUIRED
            )
            out = [path for path in out if path in required]
        return sorted(out)


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list | tuple):
        return all(_is_blank(item) for item in value)  # empty, or only None/blank strings
    if isinstance(value, dict):
        return len(value) == 0
    return False


def _walk_unset(node: dict[str, Any], path: str, out: list[str]) -> None:
    """Collect null/blank leaves. Lists (exit candidates, fixed tuples) are validated
    structurally elsewhere and not walked; dicts inside open P0 values are."""
    for key, value in node.items():
        child = f"{path}.{key}" if path else key
        if child == "decision" or child in _NON_P0_NULLABLE:
            continue
        if isinstance(value, dict) and value:
            _walk_unset(value, child, out)
        elif _is_blank(value):
            out.append(child)


class FrozenSpec:
    """A DraftSpec with every P0 field set. Construct via :meth:`from_draft`."""

    __slots__ = ("_draft",)
    _draft: DraftSpec

    def __init__(self, draft: DraftSpec) -> None:
        unset = draft.unset_p0_fields()
        if unset:
            raise UnsetP0FieldsError(unset)
        object.__setattr__(self, "_draft", draft)

    @classmethod
    def from_draft(cls, draft: DraftSpec) -> FrozenSpec:
        return cls(draft)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("FrozenSpec is immutable")

    @property
    def draft(self) -> DraftSpec:
        return self._draft


# --------------------------------------------------------------------------- skeleton


def draft_skeleton() -> dict[str, Any]:
    """Appendix A with every P0 value null. Fixed values are exactly those the plan states."""
    return {
        "program": "RANGE-002",
        "spec_version": 1,
        "registration": {"trial_ledger_id": None, "related_programs": None},
        "universe": {
            "instrument_types": ["common_stock"],
            "n": None,
            "category_map": None,
            "min_price": 10.0,
            "adv_window_days": 20,
            "rebuild": "monthly",
            "include_delisted": True,
        },
        "data": {
            "feed": "sip",
            "vendor": None,
            "bar": "1min",
            "session": "rth",
            "tz": "America/New_York",
            "fetch_mode": None,
            "daily_price_basis": None,
            "intraday_price_basis": None,
        },
        "signal": {
            "missing_minute_classes": ["NO_TRADE_MINUTE", "DATA_GAP"],
            "or_start": "09:30:00",
            "or_end": "09:59:59",
            "or_completeness_rule": None,
            "min_or_width_ticks": None,
            "entry_window": ["10:00:00", "14:59:59"],
            "tick_offset": 1,
            "max_entries_per_symbol_day": 1,
        },
        "exits": {
            "candidates": None,
            "complexity_order": None,
            "selection": {
                "score": None,
                "tie_tolerance_r": None,
                "eligibility": {"min_trades": None, "min_pf": None},
                "stop_test": None,
            },
        },
        "exit": {"stop": "or_low", "eod_flat": "15:55:00", "halfday_offset_min": None},
        "fill": {"slippage_model": None, "same_bar_policy": "worst_case", "halt_policy": None},
        "costs": {
            "base_bps_per_side": 5,
            "stress_bps_per_side": 15,
            "accounting_mode": None,
            "components": None,
        },
        "risk": {
            "per_trade_pct": None,
            "per_trade_unit": None,
            "per_name_cap": None,
            "gross_cap": None,
            "max_concurrent": None,
            "daily_loss_limit": None,
            "max_participation": None,
            "fill_risk_tolerance": None,
        },
        "partitions": {
            "development_selection": ["2016-01-01", "2019-12-31"],
            "development_confirmation": ["2020-01-01", "2021-12-31"],
            "holdout": ["2022-01-01", "2025-12-31"],
            "exposed": [["2026-01-01", "2026-07-31"]],
        },
        "controls": {
            "random_entry": {"repetitions": None, "seed": None, "invalid_draw_policy": None},
            "naive_orb": {"definition": None},
        },
        "stats": {
            "bootstrap": {
                "method": None,
                "cluster": "trading_day",
                "block_len": None,
                "ci_type": None,
                "confidence_level": None,
                "reps": None,
                "seed": None,
            },
            "hypothesis_family": None,
            "adjustment": "holm",
            "alpha_one_sided": None,
            "regime": {"definition": None, "criterion": None},
        },
        "execution": {
            "bar_timestamp_convention": None,
            "vendor_delay_ms": None,
            "submit_latency_ms": None,
            "ack_latency_ms": None,
            "crossed_before_arm_policy": None,
            "order_type": None,
            "stop_protection_policy": None,
            "tie_break": None,
            "eod_lead_s": None,
            "order_reservation_policy": None,
        },
        "p3": {"criteria": None, "max_p3a_attempts": None, "max_p3b_attempts": None},
        "gates": {
            "basis": None,
            "trade_unit": None,
            "min_trades": 300,
            "pf_base": 1.30,
            "stress_mean_positive": True,
            "yearly": None,
            "win_rate": None,
            "max_dd": None,
            "redundancy_corr_max": 0.85,
        },
        "p5": {
            "account_id": None,
            "min_days": 60,
            "min_trades": 100,
            "max_cost_ratio": 1.5,
            "degradation_tolerance": None,
            "cost_ratio_contract": None,
            "shadow_acceptance": None,
        },
        "diagnostics": {"taxonomy": None},
        "governance": {
            "exposure_signed": None,
            "registry_genesis_id": None,
        },
        "decision": None,
    }


__all__ = [
    "EXIT_FAMILIES",
    "MAX_EXIT_CANDIDATES",
    "DECISION_SCOPES",
    "DECISION_VALUES",
    "DecisionRef",
    "DecisionRefError",
    "DraftSpec",
    "ExitCandidate",
    "ExitSelection",
    "FrozenSpec",
    "UnsetP0FieldsError",
    "draft_skeleton",
    "validate_partition_layout",
]


# Spec handling computes no returns; declared for the range002 import-lint.
PURE_FUNCTIONS = ("validate_partition_layout", "draft_skeleton")
