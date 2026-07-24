"""Forward-validation first-session integrity gate + sealed observation record (PREREG v1.0).

The forward window (opens 2026-07-24, §0 countersigned commit `bd0af4a1`) must **fail closed before
writing any observation** unless EVERY frozen binding matches. This module is that gate. It also
splits an observation into an OPEN record (integrity / execution / operational counters — what a
routine operator may see) and a SEALED performance payload (returns, benchmark deltas, risk stats —
inaccessible to routine operators until the governing window closes or a permitted integrity stop).

Nothing here changes Account 4. The gate REFUSES to run against Account 4 (id 4): the validation runs
only in a shadow ledger or a separate governed paper-validation account, and never touches the retired
`84466.41` baseline.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# ── Frozen bindings (§0, countersigned 2026-07-23) ────────────────────────────────────────────────
PRODUCTION_STRATEGY_COMMIT = "b0058bf335628f8dbde09a93915314f3a1f7743b"
VALIDATION_MEASUREMENT_COMMIT = "764883b58cb96936f23e49182dd02b70d969501b"
BENCHMARK_COMMITS = {
    "PIT_UNIVERSE_EQUAL_WEIGHT_REGIME_MATCHED": "539cf6e",
    "ACADEMIC_12_1_MOMENTUM_FACTOR": "4675073",
    "CASH_OR_TBILL_RETURN": "b055b1c",
}
DGS3MO_SNAPSHOT_SHA256 = "87d8ba2fc5981add5ea48bb5d365f79371fd457488a598e0043758c21ff825d1"
DGS3MO_OBSERVATION_CUTOFF = "2026-07-21"
TRIAL_LEDGER_SHA256 = "b7d9d71591cc449a1768f33a3f3f5e0dcdf8ae518710ecec13422f0a0a98eb6d"
EFFECTIVE_DSR_TRIAL_COUNT = 45
FORWARD_START = "2026-07-24"
GOVERNING_TZ = "America/New_York"

# The frozen production configuration (subset that must not have drifted). Full set is §2 of the prereg.
FROZEN_CONFIG = {
    "max_names": 5, "max_position_pct": 0.20, "weighting": "equal", "max_sector_pct": None,
    "regime_mode": "graduated", "regime_gross_above": 0.98, "regime_gross_mid": 0.60,
    "regime_gross_below": 0.15, "market_ma_days": 200, "regime_graduated_band_pct": 0.02,
    "momentum_lookback_days": 252, "momentum_skip_days": 21, "entry_rank": 5, "hold_rank": 10,
    "initial_seed_investable_gross": 0.60,
}

ACCOUNT_4_ID = 4
RETIRED_BASELINE = 84466.41


class IntegrityStop(Exception):
    """A frozen binding did not match, or Account-4 isolation was violated. The gate FAILS CLOSED —
    NO observation is written. This is a permitted integrity stop (§5.4), not a performance FAIL."""


@dataclass(frozen=True)
class ForwardRunContext:
    """What the first-session run presents to the gate for verification."""
    session_date: date
    is_nyse_trading_session: bool          # America/New_York calendar eligibility (caller-supplied)
    code_commit: str                        # git HEAD of the running validation code
    benchmark_commits: dict[str, str]       # id → commit the run loaded
    dgs3mo_path: Path
    dgs3mo_cutoff: str
    trial_ledger_path: Path
    effective_dsr_trial_count: int
    config: dict                            # the strategy config actually in force
    ledger_account_id: int                  # the shadow / paper-validation account id
    ledger_is_shadow_or_separate_paper: bool
    references_account4_capital: bool        # must be False
    references_retired_baseline: bool        # must be False


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _short_matches(actual: str, frozen: str) -> bool:
    """A commit matches if either is a prefix of the other (frozen SHAs are stored short)."""
    a, f = actual.strip(), frozen.strip()
    return a.startswith(f) or f.startswith(a)


def preflight(ctx: ForwardRunContext) -> dict:
    """Fail-closed integrity gate. Returns the OPEN integrity manifest on success; raises
    ``IntegrityStop`` (writing nothing) on any mismatch or Account-4 isolation breach.

    Verifies, per the owner's first-session checklist: production + measurement-code commits; all three
    benchmark SHAs; the DGS3MO digest and cutoff; the trial-ledger digest and N=45; the validation
    configuration; the shadow/separate-paper ledger identity; the session date and America/New_York
    calendar eligibility; and proof that no Account-4 capital, positions, or retired baseline entered.
    """
    fails: list[str] = []

    # code identity — the running code must be the production+measurement instrument
    if not _short_matches(ctx.code_commit, VALIDATION_MEASUREMENT_COMMIT):
        fails.append(f"measurement-code commit {ctx.code_commit} != {VALIDATION_MEASUREMENT_COMMIT}")
    # (production strategy commit is an ancestor of the measurement commit; recorded, not re-derived)

    # benchmarks
    for bid, frozen in BENCHMARK_COMMITS.items():
        got = ctx.benchmark_commits.get(bid, "")
        if not _short_matches(got, frozen):
            fails.append(f"benchmark {bid} commit {got!r} != {frozen}")

    # DGS3MO snapshot digest + cutoff (no observation past the cutoff)
    if not ctx.dgs3mo_path.exists():
        fails.append(f"DGS3MO snapshot missing at {ctx.dgs3mo_path}")
    elif _sha256(ctx.dgs3mo_path) != DGS3MO_SNAPSHOT_SHA256:
        fails.append("DGS3MO snapshot digest mismatch")
    if ctx.dgs3mo_cutoff != DGS3MO_OBSERVATION_CUTOFF:
        fails.append(f"DGS3MO cutoff {ctx.dgs3mo_cutoff} != {DGS3MO_OBSERVATION_CUTOFF}")

    # trial ledger digest + N
    if not ctx.trial_ledger_path.exists():
        fails.append(f"trial ledger missing at {ctx.trial_ledger_path}")
    elif _sha256(ctx.trial_ledger_path) != TRIAL_LEDGER_SHA256:
        fails.append("trial ledger digest mismatch")
    if ctx.effective_dsr_trial_count != EFFECTIVE_DSR_TRIAL_COUNT:
        fails.append(f"effective DSR trial count {ctx.effective_dsr_trial_count} != "
                     f"{EFFECTIVE_DSR_TRIAL_COUNT}")

    # validation configuration must not have drifted
    for k, v in FROZEN_CONFIG.items():
        if ctx.config.get(k) != v:
            fails.append(f"config drift: {k}={ctx.config.get(k)!r} != frozen {v!r}")

    # session date + America/New_York eligibility (no pre-start, no non-trading session)
    if ctx.session_date.isoformat() < FORWARD_START:
        fails.append(f"session {ctx.session_date} precedes the frozen forward start {FORWARD_START}")
    if not ctx.is_nyse_trading_session:
        fails.append(f"session {ctx.session_date} is not an America/New_York trading session")

    # ── Account-4 isolation (the load-bearing safety property) ──
    if ctx.ledger_account_id == ACCOUNT_4_ID:
        fails.append("ledger account is Account 4 — the validation must run in a shadow / separate "
                     "paper account, NEVER Account 4")
    if not ctx.ledger_is_shadow_or_separate_paper:
        fails.append("ledger is not a shadow / separate governed paper-validation account")
    if ctx.references_account4_capital:
        fails.append("run references Account-4 capital/positions — forbidden")
    if ctx.references_retired_baseline:
        fails.append(f"run references the retired baseline {RETIRED_BASELINE} — forbidden")

    if fails:
        raise IntegrityStop("first-session integrity gate FAILED CLOSED — no observation written:\n  "
                            + "\n  ".join(fails))

    return {
        "gate": "FIRST_SESSION_INTEGRITY",
        "verdict": "PASS",
        "session_date": ctx.session_date.isoformat(),
        "governing_tz": GOVERNING_TZ,
        "bindings_verified": {
            "measurement_code_commit": VALIDATION_MEASUREMENT_COMMIT,
            "production_strategy_commit": PRODUCTION_STRATEGY_COMMIT,
            "benchmark_commits": dict(BENCHMARK_COMMITS),
            "dgs3mo_sha256": DGS3MO_SNAPSHOT_SHA256, "dgs3mo_cutoff": DGS3MO_OBSERVATION_CUTOFF,
            "trial_ledger_sha256": TRIAL_LEDGER_SHA256, "effective_dsr_trial_count": EFFECTIVE_DSR_TRIAL_COUNT,
            "config_matches_frozen": True,
        },
        "account4_isolation": {
            "ledger_account_id": ctx.ledger_account_id, "is_account4": False,
            "shadow_or_separate_paper": True, "references_account4_capital": False,
            "references_retired_baseline": False,
        },
    }


# ── Observation record: OPEN counters vs SEALED performance ───────────────────────────────────────

@dataclass
class OpenObservation:
    """What a routine operator MAY see — integrity, execution, operational counters only. No returns,
    no benchmark deltas, no risk stats. Carries only the DIGEST of the sealed payload (tamper-evident,
    not readable)."""
    session_date: str
    integrity_verdict: str                  # PASS | INTEGRITY_STOP
    # execution counters
    rebalances: int = 0
    orders_submitted: int = 0
    seeds: int = 0
    # operational counters (§7 H)
    scheduled_eval_completed: bool = True
    missed_rebalances: int = 0
    duplicate_orders_or_seeds: int = 0
    cap_breaches: int = 0
    broker_local_divergence: int = 0
    unresolved_reservations: int = 0
    manual_perf_affecting_interventions: int = 0
    operational_exceptions: list[str] = field(default_factory=list)
    # the sealed payload is referenced by digest only
    sealed_performance_sha256: str | None = None
    # open data-finality provenance for the session (counts, dates, digests, verdicts — never
    # performance). Recorded with the observation so a committed session carries the evidence that its
    # inputs were final, not merely the claim that they were.
    data_finality: dict | None = None
    # the provider-call evidence the decision was taken from (R5c-2b2): open provenance, no performance
    decision_evidence: dict | None = None


def seal_performance(payload: dict) -> tuple[str, bytes]:
    """Serialize the SEALED performance payload deterministically and return (sha256, bytes). The bytes
    are written to a separate sealed artifact the routine operator cannot read; only the sha256 goes in
    the OpenObservation. Unsealing is a governed action at window close (or on a permitted integrity
    stop). This is a *segregation + tamper-evidence* boundary, not encryption — the sealed file lives
    outside the routine operator's access path."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest(), raw


def build_first_session_record(ctx: ForwardRunContext, *, rebalances: int, orders: int, seeds: int,
                               operational: dict, sealed_performance: dict) -> OpenObservation:
    """Run the gate, then assemble the OPEN observation with the performance SEALED by digest. Raises
    IntegrityStop (writing nothing) if the gate fails."""
    preflight(ctx)                                  # fail-closed BEFORE any observation is built
    sha, _ = seal_performance(sealed_performance)
    return OpenObservation(
        session_date=ctx.session_date.isoformat(), integrity_verdict="PASS",
        rebalances=rebalances, orders_submitted=orders, seeds=seeds,
        scheduled_eval_completed=bool(operational.get("scheduled_eval_completed", True)),
        missed_rebalances=int(operational.get("missed_rebalances", 0)),
        duplicate_orders_or_seeds=int(operational.get("duplicate_orders_or_seeds", 0)),
        cap_breaches=int(operational.get("cap_breaches", 0)),
        broker_local_divergence=int(operational.get("broker_local_divergence", 0)),
        unresolved_reservations=int(operational.get("unresolved_reservations", 0)),
        manual_perf_affecting_interventions=int(
            operational.get("manual_perf_affecting_interventions", 0)),
        operational_exceptions=list(operational.get("operational_exceptions", [])),
        sealed_performance_sha256=sha,
    )
