"""Forward-validation PRODUCTION decision provider (R5c-2) — the real instrument decides.

The forward record's whole claim is that the FROZEN production instrument decided a session. That claim
is only true if the decision came out of the production path itself:

    MomentumDaily  →  DriftCtxAdapter  →  capture_seam  →  ForwardDecision

Nothing here recomputes a ranking, a weight, a regime state or a trade gate. `capture_seam` observes the
class's own seams (including its `target_weights` sizing seam, which it refuses to substitute for), and
this module carries that observation into the evaluator unchanged. A provider that reconstructed any of
those would agree with production by construction and could not detect a change in it — the blind spot
the 21-year census was built to close.

## The snapshot is taken BEFORE the decision reads mutable state

A decision is only interpretable against the state it was taken from, so the run captures an
`InstrumentSnapshot` first: the frozen strategy identity, the exact parameters and their revision, the
instrument's durable state blob, the regime source identity, and the data-store identity R5c-1 recorded.
Its digest goes into open provenance, and the decision carries the digest of the snapshot it was taken
under — so the runner can verify the decision belongs to the snapshot created for THAT run, not to a
state that moved in between.

The snapshot is account-independent: it binds the instrument's own state, never Account 4's book.

## Fail-closed cases (each is an integrity stop, never a synthesized decision)

  * the sizing seam is absent, or `capture_seam` raises for any reason;
  * the strategy identity is not the frozen production commit;
  * the record's session date is not the session being run;
  * the context is bound to Account 4, or to the ledger's own accounting identity;
  * no snapshot was taken, or the instrument's durable state moved between the snapshot and the
    decision (snapshot digest mismatch);
  * the adapter/context supplying the decision's inputs is not the one the snapshot bound — a different
    adapter class, strategy registration, universe, scores provider, bars/regime provider or
    instrument book;
  * the decision's shape is structurally invalid (targets/weights disagree, non-finite numbers).

A genuinely evaluated zero-gross decision is valid and books normally. An ABSENT evaluation — the class
returning before `_evaluate`, which `capture_seam` renders as targets with no weights — is an integrity
stop, never a flat no-trade observation (owner ruling 2026-07-24).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from app.strategies.drift_audit import SeamRecord
from app.validation.forward_evaluator import ForwardDecision, InstrumentDecisionState
from app.validation.forward_window import ACCOUNT_4_ID, PRODUCTION_STRATEGY_COMMIT, IntegrityStop

EVAL_SYMBOL = "__eval__"


class DecisionProviderError(IntegrityStop):
    """The production decision could not be obtained, or could not be shown to belong to this run's
    snapshot. Nothing is booked and nothing is committed."""


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class InstrumentSnapshot:
    """The instrument state a session's decision is taken under. Open provenance: identities, digests
    and configuration — no factor values, rankings, returns or portfolio results."""
    session_date: str
    captured_at: str                        # ISO8601 UTC, caller-supplied
    strategy_identity: str                  # the frozen production commit
    strategy_class: str                     # module:qualname actually instantiated
    strategy_status: str                    # the harness instance's status (never Account 4's)
    params: dict                            # the registered configuration in force
    params_digest: str
    durable_state_digest: str               # the instrument's own persisted state blob
    durable_state_keys: tuple[str, ...]
    regime_source_identity: str             # the market-proxy construction the regime reads
    store_identity_sha256: str              # R5c-1's value-level data-store identity
    # the CONTEXT that supplies the decision's inputs, derived from what is actually bound — not from
    # descriptive strings a caller passes alongside it
    adapter_class: str = ""
    adapter_strategy_id: int = -1
    universe_digest: str = ""
    scores_provider_identity: str = ""
    bars_provider_identity: str = ""
    instrument_book_digest: str = ""
    context_digest: str = ""
    snapshot_digest: str = ""

    def with_digest(self) -> InstrumentSnapshot:
        body = {k: v for k, v in asdict(self).items() if k != "snapshot_digest"}
        return InstrumentSnapshot(**body, snapshot_digest=_digest(body))

    def to_open_provenance(self) -> dict[str, Any]:
        d = asdict(self)
        d["durable_state_keys"] = list(self.durable_state_keys)
        return d


def capture_instrument_snapshot(
    strategy: Any,
    adapter: Any,
    session_date: date,
    *,
    captured_at: str,
    regime_source_identity: str,
    store_identity_sha256: str,
    strategy_identity: str = PRODUCTION_STRATEGY_COMMIT,
    strategy_status: str = "FORWARD_VALIDATION_SHADOW",
) -> InstrumentSnapshot:
    """Snapshot the instrument BEFORE it reads or mutates state for this session.

    The durable state is digested, not copied out: its contents are the instrument's own decision state
    (deployment lifecycle, seed attempts, last-applied targets), and the record needs to prove it did
    not move, not to publish it.
    """
    params = dict(getattr(strategy, "params", {}) or {})
    state = dict(getattr(adapter, "_state", {}) or {})
    ctx = context_identity(adapter)
    snap = InstrumentSnapshot(
        session_date=session_date.isoformat(),
        captured_at=captured_at,
        strategy_identity=strategy_identity,
        strategy_class=f"{type(strategy).__module__}:{type(strategy).__qualname__}",
        strategy_status=strategy_status,
        params=params,
        params_digest=_digest(params),
        durable_state_digest=_digest(state),
        durable_state_keys=tuple(sorted(state)),
        regime_source_identity=regime_source_identity,
        store_identity_sha256=store_identity_sha256,
        **ctx,
    )
    return snap.with_digest()


def _callable_identity(fn: Any) -> str:
    """An identity DERIVED from the bound implementation: module:qualname, plus the bound arguments of
    a functools.partial. Never a descriptive string a caller supplies."""
    import functools

    if isinstance(fn, functools.partial):
        return (f"partial({_callable_identity(fn.func)}"
                f"|args={_digest(list(fn.args))[:16]}|kw={_digest(sorted(fn.keywords))[:16]})")
    module = getattr(fn, "__module__", None) or type(fn).__module__
    qualname = getattr(fn, "__qualname__", None) or type(fn).__qualname__
    return f"{module}:{qualname}"


def context_identity(adapter: Any) -> dict[str, Any]:
    """The decision CONTEXT's identity, read off the adapter that is actually wired.

    A snapshot that named the right store and regime while the adapter was bound to different provider
    functions, a different strategy registration or a different universe would describe a decision that
    was never taken. These fields are recomputed immediately before the decision and must match.
    """
    symbols = [str(s).upper() for s in (getattr(adapter, "symbols", []) or [])]
    positions = {str(k).upper(): str(v) for k, v in
                 dict(getattr(adapter, "_positions", {}) or {}).items()}
    book = {"equity": str(getattr(adapter, "equity", "")), "positions": positions}
    fields = {
        "adapter_class": f"{type(adapter).__module__}:{type(adapter).__qualname__}",
        "adapter_strategy_id": int(getattr(adapter, "strategy_id", -1) or -1),
        "universe_digest": _digest(sorted(symbols)),
        "scores_provider_identity": _callable_identity(getattr(adapter, "scores_provider", None)),
        "bars_provider_identity": _callable_identity(getattr(adapter, "bars_provider", None)),
        "instrument_book_digest": _digest(book),
    }
    fields["context_digest"] = _digest(fields)
    return fields


@dataclass
class ProductionDecisionProvider:
    """Drives the REAL frozen instrument for one session and returns its decision.

    `durable_state_id` identifies the instrument's own state store and must differ from the shadow
    ledger's accounting identity (the evaluator re-checks this too — the two books are separate by
    construction, and a decision that confused them would be booking against its own cost drag).
    """
    strategy: Any
    adapter: Any
    snapshot: InstrumentSnapshot
    durable_state_id: str
    fill_price_fn: Any                       # (symbol, session) -> float | None, for same-day settle
    expected_identity: str = PRODUCTION_STRATEGY_COMMIT
    settle_after_decision: bool = True
    _sessions_seen: set[str] = field(default_factory=set)

    def __call__(self, session_date: date) -> ForwardDecision:
        iso = session_date.isoformat()

        if not isinstance(self.snapshot, InstrumentSnapshot):
            raise DecisionProviderError("no instrument snapshot was taken for this run")
        if self.snapshot.session_date != iso:
            raise DecisionProviderError(
                f"the snapshot was taken for {self.snapshot.session_date}, not {iso}")
        if self.snapshot.snapshot_digest != self.snapshot.with_digest().snapshot_digest:
            raise DecisionProviderError("the snapshot's own digest does not verify")
        if not _identity_matches(self.snapshot.strategy_identity, self.expected_identity):
            raise DecisionProviderError(
                f"snapshot strategy identity {self.snapshot.strategy_identity!r} is not the frozen "
                f"production instrument {self.expected_identity!r}")
        if str(self.durable_state_id).strip() == "":
            raise DecisionProviderError("the instrument durable-state identity is empty")

        account_id = getattr(self.adapter, "account_id", None)
        if account_id == ACCOUNT_4_ID:
            raise DecisionProviderError(
                "the decision context is bound to Account 4; the forward validation reads no Account-4 "
                "state and drives no Account-4 instrument")

        # the CONTEXT that supplies the decision's inputs must be the one the snapshot bound
        live_ctx = context_identity(self.adapter)
        for field_name, live_value in live_ctx.items():
            bound = getattr(self.snapshot, field_name)
            if live_value != bound:
                raise DecisionProviderError(
                    f"the decision context's {field_name} is {live_value!r} but the snapshot bound "
                    f"{bound!r} — the instrument is not wired to the inputs this run snapshotted")

        # the instrument's own state must still be the state the snapshot was taken under
        live_state_digest = _digest(dict(getattr(self.adapter, "_state", {}) or {}))
        if live_state_digest != self.snapshot.durable_state_digest:
            raise DecisionProviderError(
                "the instrument's durable state changed between the snapshot and the decision "
                f"({self.snapshot.durable_state_digest[:16]}… → {live_state_digest[:16]}…)")

        if iso in self._sessions_seen:
            raise DecisionProviderError(f"session {iso} was already decided by this provider")

        record = self._run_session(session_date)
        if record.date != iso:
            raise DecisionProviderError(f"the instrument decided {record.date!r}, not {iso!r}")
        _assert_shape(record)

        state = _instrument_decision_state(self.strategy, self.adapter, record)
        self._sessions_seen.add(iso)
        return ForwardDecision(
            record=record, instrument_identity=self.snapshot.strategy_identity,
            durable_state_id=self.durable_state_id, instrument_state=state,
            snapshot_digest=self.snapshot.snapshot_digest)

    # ── the production path, run exactly as the §7A harness runs it ────────────────────────────────
    def _run_session(self, session_date: date) -> SeamRecord:
        from app.strategies.drift_audit_driver import capture_seam

        try:
            asyncio.run(_drive_one_session(self.strategy, self.adapter, session_date))
            record = capture_seam(self.strategy, self.adapter, session_date)
        except IntegrityStop:
            raise
        except AttributeError as exc:                 # e.g. the class exposes no `target_weights` seam
            raise DecisionProviderError(
                f"the production sizing seam is unavailable: {exc}") from exc
        except Exception as exc:
            raise DecisionProviderError(
                f"the production instrument failed to decide {session_date.isoformat()}: "
                f"{type(exc).__name__}: {exc}") from exc

        if self.settle_after_decision:
            try:
                pending = list(getattr(self.adapter, "_pending", []) or [])
                fills = {o.symbol: self.fill_price_fn(o.symbol, session_date) for o in pending}
                self.adapter.settle({k: v for k, v in fills.items() if v is not None})
            except IntegrityStop:
                raise
            except Exception as exc:
                raise DecisionProviderError(
                    f"settling the instrument's own book failed: {type(exc).__name__}: {exc}") from exc
        return record


async def _drive_one_session(strategy: Any, adapter: Any, session_date: date) -> None:
    """One production evaluation, exactly as `drive_live` performs it."""
    from datetime import UTC, datetime

    from app.strategies.context import Bar

    adapter.sim_day = session_date
    adapter.submitted_today = []
    adapter.signals_today = []
    ts = datetime(session_date.year, session_date.month, session_date.day, 21, 10, tzinfo=UTC)
    await strategy.on_bar(Bar(symbol=EVAL_SYMBOL, timeframe="1Day", t=ts, o=1, h=1, l=1, c=1, v=1))


def _instrument_decision_state(strategy: Any, adapter: Any, record: SeamRecord
                               ) -> InstrumentDecisionState:
    """The instrument's OWN decision-state book, read from the instrument and its context — the only
    authority for whether the trade gate should have fired (owner ruling 2026-07-23)."""
    positions = {k: float(v) for k, v in dict(getattr(adapter, "_positions", {}) or {}).items()
                 if float(v) > 0}
    held = tuple(sorted(positions))
    equity = float(getattr(adapter, "equity", 0) or 0)
    last_px = dict(getattr(strategy, "_last_applied_prices", {}) or {})
    current = {tk: (positions[tk] * float(last_px.get(tk, 0.0)) / equity) if equity > 0 else 0.0
               for tk in held}
    params = dict(getattr(strategy, "params", {}) or {})
    return InstrumentDecisionState(
        held=held,
        current_weights=current,
        last_applied_target_weights=dict(getattr(strategy, "_last_applied_target_weights", {}) or {}),
        prior_applied_gross=float(getattr(strategy, "_applied_gross", record.regime_gross) or 0.0),
        sessions_since_rebalance=int(getattr(strategy, "_sessions_since_rebalance", 0) or 0),
        weight_drift_threshold=float(params.get("weight_drift_pct", 0.04) or 0.0),
        backstop_days=int(params.get("backstop_max_days", 10) or 0),
    )


def _assert_shape(record: SeamRecord) -> None:
    """Structural sanity before the evaluator's own boundary checks: an absent evaluation (targets with
    no weights) and non-finite numbers are refused here so the failure names the instrument, not the
    ledger."""
    if not math.isfinite(record.regime_gross):
        raise DecisionProviderError(f"regime_gross is not finite: {record.regime_gross}")
    if set(record.weights) != set(record.target_names):
        raise DecisionProviderError(
            f"the decision names targets {sorted(record.target_names)} but carries weights for "
            f"{sorted(record.weights)} — the instrument did not evaluate this session")
    for tk, w in record.weights.items():
        if not math.isfinite(w):
            raise DecisionProviderError(f"weight for {tk!r} is not finite: {w}")


def _identity_matches(actual: str, frozen: str) -> bool:
    a, f = actual.strip().lower(), frozen.strip().lower()
    return len(a) == 40 and all(c in "0123456789abcdef" for c in a) and a == f
