"""Forward-validation PRODUCTION decision provider (R5c-2) — the real instrument decides.

The forward record's whole claim is that the FROZEN production instrument decided a session. That claim
is only true if the decision came out of the production path itself:

    MomentumDaily  →  DriftCtxAdapter  →  capture_seam  →  ForwardDecision

Nothing here recomputes a ranking, a weight, a regime state or a trade gate. `capture_seam` observes the
class's own seams (including its `target_weights` sizing seam, which it refuses to substitute for), and
this module carries that observation into the evaluator unchanged. A provider that reconstructed any of
those would agree with production by construction and could not detect a change in it — the blind spot
the 21-year census was built to close.

## Identity is derived from what is bound, and must be STABLE

Two closures built by the same factory over different stores share a module and a qualified name, as do
two bound methods on differently-configured provider instances. `provider_identity` therefore binds the
code object and the closed-over configuration as well — and when it cannot establish an identity that
would reproduce in another process (a closure over an object with no governed identity), it RAISES
rather than returning a name that could collide. A provider may present its own identity explicitly by
exposing `forward_identity()`, which is the contract production wiring should use.

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
  * the live instrument itself is not the one the snapshot bound — a different class, different
    parameters, or a different deployment lifecycle;
  * an input provider cannot present a STABLE identity (a closure over an object with no governed
    identity, an unconfigurable callable): unverifiable is refused, never assumed equal;
  * the decision's shape is structurally invalid (targets/weights disagree, non-finite numbers).

A genuinely evaluated zero-gross decision is valid and books normally. An ABSENT evaluation — the class
returning before `_evaluate`, which `capture_seam` renders as targets with no weights — is an integrity
stop, never a flat no-trade observation (owner ruling 2026-07-24).
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
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
    lifecycle_identity: str                 # DERIVED from the instrument's own deployment blob
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
) -> InstrumentSnapshot:
    """Snapshot the instrument BEFORE it reads or mutates state for this session.

    The durable state is digested, not copied out: its contents are the instrument's own decision state
    (deployment lifecycle, seed attempts, last-applied targets), and the record needs to prove it did
    not move, not to publish it.
    """
    state = dict(getattr(adapter, "_state", {}) or {})
    ctx = context_identity(adapter)
    live = instrument_identity(strategy, adapter)
    snap = InstrumentSnapshot(
        session_date=session_date.isoformat(),
        captured_at=captured_at,
        strategy_identity=strategy_identity,
        strategy_class=live["strategy_class"],
        lifecycle_identity=live["lifecycle_identity"],
        params=dict(getattr(strategy, "params", {}) or {}),
        params_digest=live["params_digest"],
        durable_state_digest=_digest(state),
        durable_state_keys=tuple(sorted(state)),
        regime_source_identity=regime_source_identity,
        store_identity_sha256=store_identity_sha256,
        **ctx,
    )
    return snap.with_digest()


class UnstableIdentity(DecisionProviderError):
    """A provider cannot present an identity that would reproduce in another process. Refused rather
    than approximated: an identity that collides across differently-bound inputs is worse than none."""


_STABLE_SCALARS = (str, int, float, bool, bytes, type(None))


def _stable_value(value: Any) -> str | None:
    """A deterministic rendering of `value`, or None when it cannot be rendered stably.

    `repr()` of an ordinary object embeds its memory address, so it differs between processes: a
    snapshot built on it would neither reproduce nor distinguish two differently-configured providers.
    Only scalars, paths, plain containers of those, and objects presenting `forward_identity()` count.
    """
    from pathlib import Path as _Path

    if isinstance(value, _STABLE_SCALARS):
        return f"{type(value).__name__}:{value!r}"
    if isinstance(value, _Path):
        return f"Path:{value.as_posix()}"
    if isinstance(value, date):
        return f"date:{value.isoformat()}"
    if callable(getattr(value, "forward_identity", None)):
        return f"identity:{value.forward_identity()}"
    if isinstance(value, list | tuple):
        rendered_items = [_stable_value(v) for v in value]
        if any(item is None for item in rendered_items):
            return None
        return "seq[" + "|".join(str(item) for item in rendered_items) + "]"
    if isinstance(value, set | frozenset):
        parts = sorted(str(_stable_value(v)) for v in value)
        return None if any(p == "None" for p in parts) else f"set[{'|'.join(parts)}]"
    if isinstance(value, dict):
        items = []
        for k in sorted(map(str, value)):
            rendered = _stable_value(value[k])
            if rendered is None:
                return None
            items.append(f"{k}={rendered}")
        return f"map[{'|'.join(items)}]"
    return None


def _code_digest(fn: Any) -> str:
    code = getattr(fn, "__code__", None)
    if code is None:
        return "no-code"
    consts = [_stable_value(c) or "<opaque>" for c in getattr(code, "co_consts", ())]
    return _digest([bytes(code.co_code).hex(), list(code.co_names), list(code.co_varnames), consts])


def _closure_identity(fn: Any) -> str:
    """The values a function closed over. Unstable cells fail closed — two closures from one factory
    over different stores must not share an identity."""
    cells = getattr(fn, "__closure__", None) or ()
    names = getattr(getattr(fn, "__code__", None), "co_freevars", ()) or ()
    if not cells:
        return "no-closure"
    parts = []
    for name, cell in zip(names, cells, strict=False):
        try:
            value = cell.cell_contents
        except ValueError:                       # an empty cell (recursive definition)
            parts.append(f"{name}=<empty>")
            continue
        rendered = _stable_value(value)
        if rendered is None:
            raise UnstableIdentity(
                f"the provider closes over {name!r} ({type(value).__name__}), which presents no stable "
                f"identity; expose forward_identity() on it or bind the provider explicitly")
        parts.append(f"{name}={rendered}")
    return _digest(parts)


def provider_identity(fn: Any) -> str:
    """A STABLE identity for an input provider, derived from the implementation and everything it is
    bound to. Raises `UnstableIdentity` when that cannot be established.

    Production wiring should give providers an explicit `forward_identity()` (bound store path, digest,
    construction parameters) rather than relying on this to infer semantics."""
    import functools

    if fn is None:
        raise UnstableIdentity("no provider is bound")
    if callable(getattr(fn, "forward_identity", None)):
        return f"declared:{fn.forward_identity()}"
    if isinstance(fn, functools.partial):
        return (f"partial({provider_identity(fn.func)}|args={_digest([_stable_value(a) or _unstable(a)
                for a in fn.args])[:16]}"
                f"|kw={_digest({k: _stable_value(v) or _unstable(v) for k, v in fn.keywords.items()})[:16]})")
    if inspect.ismethod(fn):                      # a bound method: the INSTANCE is part of the identity
        owner = fn.__self__
        state = _stable_value(dict(getattr(owner, "__dict__", {}) or {}))
        if state is None:
            raise UnstableIdentity(
                f"the provider is a bound method of {type(owner).__name__}, whose configuration "
                f"presents no stable identity; expose forward_identity() on it")
        return (f"method:{type(owner).__module__}:{type(owner).__qualname__}.{fn.__name__}"
                f"|state={_digest(state)[:16]}|code={_code_digest(fn.__func__)[:16]}")
    if inspect.isfunction(fn):
        return (f"function:{fn.__module__}:{fn.__qualname__}|code={_code_digest(fn)[:16]}"
                f"|closure={_closure_identity(fn)[:16]}")
    if callable(fn):                              # a callable object: class + its configuration
        state = _stable_value(dict(getattr(fn, "__dict__", {}) or {}))
        if state is None:
            raise UnstableIdentity(
                f"the provider object {type(fn).__name__} presents no stable configuration identity; "
                f"expose forward_identity() on it")
        return f"object:{type(fn).__module__}:{type(fn).__qualname__}|state={_digest(state)[:16]}"
    raise UnstableIdentity(f"{fn!r} is not callable and cannot identify a provider")


def _unstable(value: Any) -> str:
    raise UnstableIdentity(
        f"a bound argument of type {type(value).__name__} presents no stable identity")


def instrument_identity(strategy: Any, adapter: Any) -> dict[str, str]:
    """The LIVE instrument's identity: the class, its parameters, and the deployment lifecycle it is
    actually in. Re-derived immediately before the decision and compared with the snapshot — a snapshot
    that recorded parameters is not the same as one that proves the instrument still has them."""
    deployment = dict((getattr(adapter, "_state", {}) or {}).get("deployment", {}) or {})
    lifecycle = (f"{deployment.get('state', 'UNINITIALIZED')}@rev{deployment.get('_rev', 'none')}"
                 f"|seed={bool(deployment.get('active_seed_attempt'))}")
    return {
        "strategy_class": f"{type(strategy).__module__}:{type(strategy).__qualname__}",
        "params_digest": _digest(dict(getattr(strategy, "params", {}) or {})),
        "lifecycle_identity": lifecycle,
    }


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
        "scores_provider_identity": provider_identity(getattr(adapter, "scores_provider", None)),
        "bars_provider_identity": provider_identity(getattr(adapter, "bars_provider", None)),
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

        # the LIVE instrument must still be the instrument the snapshot bound
        live_instrument = instrument_identity(self.strategy, self.adapter)
        for field_name, live_value in live_instrument.items():
            bound = getattr(self.snapshot, field_name)
            if live_value != bound:
                raise DecisionProviderError(
                    f"the live instrument's {field_name} is {live_value!r} but the snapshot bound "
                    f"{bound!r} — the instrument changed after the snapshot was taken")

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
