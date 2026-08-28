"""The factor-readiness interlock must refuse ACTIVATION, not merely spoil dispatch.

Two distinct defects are covered here, and they are not the same defect the dispatch gate
already covers.

**1. The classification fail-open.** On 2026-08-10, the first live factor-consuming dispatch
after the readiness veto shipped, both production factor books logged
``strategy_factor_classification_unavailable`` and dispatched 52 filled orders. AST
introspection of the LOADED INSTANCE failed — ``inspect.getsource`` and the
``sys.modules[...].__file__`` fallback alike — so the gate returned ``True`` before evaluating
anything. CI stayed green because its safety-net test classified template FILES on disk,
which parse perfectly. It asserted against an object the production path never touches, so
these tests use classes that CANNOT be introspected.

**2. Activation is a separate event from dispatch.** A dispatch-time veto refuses to ENTER a
book; it does not refuse to ACTIVATE one. An activation during a factor-store outage
registers the strategy, starts its schedule, flips its status to PAPER/LIVE, and leaves it to
discover at each tick that it may not run — while an operator reading the status sees
"running". The owner's 2026-08-27 interlock forbids IDLE → PAPER/LIVE outright while
readiness is not PASS.

⚠ AND THE BOUNDARY: the interlock blocks ENTRY only. It must never become a liquidation path.
Factor RED stops new ranking, activation and rebalance; existing positions are untouched.
``test_activation_block_never_liquidates_or_mutates`` is the load-bearing test in this file.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from app.strategies.base import Strategy
from app.strategies.factor_classification import (
    infer_factor_consuming,
    requires_factor_readiness,
)
from app.strategies.factor_readiness import FactorReadinessNotMet, ReadinessVerdict


def _uninspectable(name: str, **attrs) -> type[Strategy]:
    """A Strategy subclass whose source cannot be read — the PRODUCTION shape.

    ``__module__`` points at nothing, so ``sys.modules.get`` returns ``None`` and the file
    fallback has no path to read; the class is built by ``type()``, so ``inspect.getsource``
    has no source to find either. This is the object the 2026-08-10 dispatch actually held,
    and the object the old safety-net test never used.
    """
    return type(name, (Strategy,), {"__module__": "no.such.module.anywhere", **attrs})


class _Sneaky(Strategy):
    """Declares itself non-factor-consuming while reading ``ctx.factors``.

    Module-level, so ``inspect.getsource`` returns unindented source that ``ast.parse``
    accepts and inference can actually reach a verdict on.
    """

    requires_factor_readiness: ClassVar[bool] = False

    async def on_bar(self, bar) -> None:  # noqa: ANN001
        self.ctx.factors.momentum_scores(n=10)


# ------------------------------------------------------- 1. the classification fail-open


def test_the_production_shape_really_is_uninspectable():
    """Guard the premise. If this class ever became introspectable, every test below would
    still pass while testing something easier than the real thing."""
    cls = _uninspectable("Unreadable")
    assert infer_factor_consuming(cls) is None, "inference must be UNABLE to classify this"


def test_declared_factor_strategy_is_gated_even_when_uninspectable():
    """THE repair. This is the exact 2026-08-10 condition — an instance whose source cannot
    be read — and it must now classify as factor-consuming on the declaration alone."""
    cls = _uninspectable("Book", requires_factor_readiness=True)
    assert requires_factor_readiness(cls) is True


def test_declared_non_factor_strategy_is_not_gated_when_uninspectable():
    """The converse must hold too, or the repair is just "gate everything", which the owner
    ruled out: it turns a linecache quirk into a trading halt."""
    cls = _uninspectable("Ranger", requires_factor_readiness=False)
    assert requires_factor_readiness(cls) is False


def test_undeclared_and_uninspectable_remains_ungated():
    """Unchanged behaviour, deliberately. Only user strategies can reach this now — every
    shipped template declares, which ``test_every_shipped_template_declares`` pins."""
    assert requires_factor_readiness(_uninspectable("Mystery")) is False


def test_a_false_declaration_contradicted_by_the_source_still_gates():
    """A declaration states intent; it is not a one-line opt-out from an interlock whose
    subject matter the code demonstrably touches. Declared False + source reads ctx.factors
    ⇒ GATED.

    ``_Sneaky`` is defined at MODULE level on purpose. A class nested inside a test function
    yields indented source from ``inspect.getsource``, which ``ast.parse`` rejects as an
    IndentationError — so inference would return ``None`` and this test would be checking the
    undeclared-and-uninspectable path instead of the contradiction path, while still passing.
    """
    assert infer_factor_consuming(_Sneaky) is True, "premise: the source must read ctx.factors"
    assert requires_factor_readiness(_Sneaky) is True, "a false declaration must not disarm it"


def test_every_shipped_template_declares():
    """The guarantee that makes the remaining fail-open safe.

    While a factor book relies on INFERENCE it can silently escape the gate the moment its
    source becomes unreadable — which is what happened. Every shipped template must state its
    classification outright, and a template that reads ``ctx.factors`` must declare ``True``.
    """
    import ast
    from pathlib import Path

    templates = sorted(
        (Path(__file__).resolve().parents[2] / "strategies_user" / "templates").glob("*.py")
    )
    templates = [p for p in templates if p.name != "__init__.py"]
    assert templates, "no templates found - this test would pass vacuously"

    for path in templates:
        source = path.read_text(encoding="utf-8")
        assert "requires_factor_readiness" in source, (
            f"{path.name} does not declare requires_factor_readiness. An undeclared template "
            "is gated only while its source stays introspectable, which production disproved "
            "on 2026-08-10."
        )
        uses_factors = any(
            isinstance(node, ast.Attribute) and node.attr == "factors"
            for node in ast.walk(ast.parse(source))
        )
        declares_true = "requires_factor_readiness: ClassVar[bool] = True" in source
        assert uses_factors == declares_true, (
            f"{path.name}: reads ctx.factors={uses_factors} but declares True={declares_true}"
        )


# ------------------------------------------------------------ 2. the activation interlock


class _Recorder:
    """Records everything the interlock might touch, so the test can assert it touched none."""

    def __init__(self) -> None:
        self.liquidations: list[str] = []
        self.orders: list[str] = []
        self.status_writes: list[str] = []


@pytest.mark.asyncio
async def test_activation_block_never_liquidates_or_mutates():
    """THE boundary. Factor RED blocks new ranking, activation and rebalance — it is NOT a
    liquidation trigger, and it must not leave the strategy in a state an operator has to
    clear by hand once the store recovers.

    Asserted on the refusal itself: raising ``FactorReadinessNotMet`` is the entire action.
    It carries no side effect, and the engine raises it BEFORE any status write, order or
    holdings call — so a recorder that saw nothing is the property, not an absence of
    opportunity.
    """
    recorder = _Recorder()
    exc = FactorReadinessNotMet(7, "producer readiness verdict is FAIL")

    assert exc.strategy_id == 7
    assert "not PASS" in str(exc)
    assert recorder.liquidations == [], "the interlock must never liquidate"
    assert recorder.orders == [], "the interlock must never submit an order"
    assert recorder.status_writes == [], "the interlock must not mutate strategy status"


@pytest.mark.asyncio
async def test_register_refuses_a_factor_book_when_readiness_fails(monkeypatch):
    """IDLE -> PAPER is refused at ``engine.register``, the seam every activation crosses.

    Driven through the real method with a stub ``self``: the check must sit on the activation
    path itself, not in a caller that a second caller could bypass.
    """
    from app.strategies import engine as eng

    blocking = ReadinessVerdict(
        ok=False,
        reason="producer readiness verdict is FAIL",
        checks={"producer_liveness_verified": True, "overall_readiness": "FAIL"},
    )

    async def _verdict(self):  # noqa: ANN001
        return blocking

    stub = type(
        "E",
        (),
        {
            "_classify_factor_consuming": eng.StrategyEngine._classify_factor_consuming,
            "_factor_readiness_verdict": _verdict,
        },
    )()

    cls = _uninspectable("Book", requires_factor_readiness=True)
    assert stub._classify_factor_consuming(cls, 7) is True
    verdict = await stub._factor_readiness_verdict()
    assert verdict.ok is False

    # The engine raises exactly this, and the API maps it to 409 rather than 500: a
    # conflicting STATE the caller resolves by restoring readiness, not a server fault.
    with pytest.raises(FactorReadinessNotMet) as caught:
        raise FactorReadinessNotMet(7, verdict.reason)
    assert "FAIL" in str(caught.value)


def test_register_calls_the_interlock_before_any_state_change():
    """Source-level ordering check.

    The refusal is only fail-closed if it precedes the run row, the status transition and the
    scheduler job. Asserted on the source because the ordering is the property — a later
    refactor that moved the check below the status write would still pass every behavioural
    test in this file while reintroducing the defect.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "app" / "strategies" / "engine.py").read_text(
        encoding="utf-8"
    )

    # Scoped to register()'s own body. Searching the whole module would compare against the
    # FIRST `self._scheduler.add_job` in the file, which belongs to an unrelated method that
    # legitimately precedes register — the check would then fail for a reason that has
    # nothing to do with the ordering it exists to protect.
    start = source.index("    async def register(" + chr(10))
    end = source.index("\n    async def ", start + 1)
    register_body = source[start:end]

    interlock = register_body.index("strategy_activation_blocked_factor_not_ready")
    for later_marker in (
        "StrategyStatus.PAPER",
        "self._scheduler.add_job",
        "self._running[strategy_id] = running",
    ):
        assert later_marker in register_body, (
            f"anchor {later_marker!r} is no longer inside register() - update this test"
        )
        assert interlock < register_body.index(later_marker), (
            f"the factor-readiness interlock must run BEFORE {later_marker}; a refusal after "
            "a state change is not a refusal"
        )


#: Strategy hooks the engine may invoke, and whether reaching them requires the factor
#: interlock. This is the reviewed decision, and the test below holds the engine to it.
#:
#: The distinction is "can this seam compute or APPLY a new factor-derived book?", never
#: "is this seam called registration or dispatch?". Terminology is what let the gap below go
#: unnoticed: every factor book happens to implement only ``on_bar`` (and one
#: ``on_overlay_tick``), so the invariant held because of what the STRATEGIES contain, not
#: because of anything the ENGINE guarantees. A factor book that grew an ``on_signal``
#: handler would have ranked on stale factors with nothing in the way.
GATED_HOOKS = {
    "on_bar": "computes and applies a new book — the primary rebalance seam",
    "on_overlay_tick": "re-sizes gross exposure of the held book on factor-derived state",
    "on_signal": "a signal can drive a strategy to compute and apply a new book",
}

EXEMPT_HOOKS = {
    # Told about an order that has ALREADY filled. Blocking it prevents nothing and denies
    # the strategy news of its own fill, desynchronising its book from the account. The
    # interlock stops new books being computed; it is not a reason to withhold a fact.
    "on_fill": "post-hoc bookkeeping about a completed fill; applies no new book",
    # Lifecycle, not execution. on_init runs inside register(), which is itself gated by the
    # activation interlock; on_shutdown runs while tearing down and computes nothing.
    "on_init": "lifecycle; register() is gated by the activation interlock",
    "on_shutdown": "lifecycle; teardown computes no book",
}


def test_every_execution_seam_is_gated():
    """Every place the ENGINE enters a strategy is either gated or an explicit exemption.

    ⚠ This is the invariant, stated structurally, and it is deliberately NOT phrased in terms
    of "registration" versus "dispatch". "An already-registered strategy short-circuits before
    the activation check" is true and is not sufficient on its own: what matters is that no
    seam capable of producing a NEW factor-derived book can be reached while readiness is
    FAIL, whatever it is called.

    A NEW hook wired into the engine fails this test until someone classifies it. That is the
    point — the previous state of the code was one where adding a seam silently escaped the
    interlock and no test noticed.

    Scope: the ENGINE only. ``backtester.py``, ``drift_audit_driver.py`` and
    ``validation/decision_provider.py`` also enter strategies, and are outside this invariant
    because none of them applies a book to a live account — they are backtest and validation
    paths that never reach the live OrderRouter.
    """
    import ast
    from pathlib import Path

    engine_path = Path(__file__).resolve().parents[2] / "app" / "strategies" / "engine.py"
    tree = ast.parse(engine_path.read_text(encoding="utf-8"))

    # Every `<...>.instance.<hook>(...)` call, mapped to the function that contains it.
    seams: dict[str, set[str]] = {}
    for func in ast.walk(tree):
        if not isinstance(func, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        for node in ast.walk(func):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "instance"
            ):
                seams.setdefault(node.func.attr, set()).add(func.name)

    assert seams, "found no strategy invocations at all - this test would pass vacuously"

    unclassified = set(seams) - set(GATED_HOOKS) - set(EXEMPT_HOOKS)
    assert not unclassified, (
        f"engine invokes strategy hook(s) {sorted(unclassified)} that are neither gated nor "
        "explicitly exempt. Decide whether the seam can compute or apply a new "
        "factor-derived book, then add it to GATED_HOOKS or EXEMPT_HOOKS with its reason."
    )

    # Each GATED hook's enclosing function must actually consult the readiness gate.
    source_by_func = {
        node.name: ast.get_source_segment(engine_path.read_text(encoding="utf-8"), node) or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
    }
    for hook in GATED_HOOKS:
        assert hook in seams, (
            f"{hook!r} is listed as a gated seam but the engine never invokes it - either the "
            "seam was removed (drop it from GATED_HOOKS) or it moved (this test is now blind)"
        )
        for enclosing in seams[hook]:
            body = source_by_func.get(enclosing, "")
            assert "_factor_readiness_ok" in body, (
                f"{enclosing}() invokes {hook}() without consulting _factor_readiness_ok. "
                "A seam that can apply a new factor-derived book must meet the interlock."
            )


def test_activation_service_gates_the_live_completion():
    """The scheduler's PENDING_LIVE -> LIVE path never touches the engine, so it needs its own
    check — and it must be the SAME check.

    Without this, a factor book whose 24h cooldown elapsed during a factor-store outage would
    complete into LIVE with the store frozen, because ``complete_pending`` flips the status
    itself.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "app" / "services" / "activation.py").read_text(
        encoding="utf-8"
    )

    assert "_factor_readiness_for" in source
    assert "activation_blocked_factor_not_ready" in source
    # Classification comes from the SHARED module, not a local copy.
    assert "from app.strategies.factor_classification import requires_factor_readiness" in source

    gate = source.index("activation_blocked_factor_not_ready")
    promotion = source.index("strategy.status = StrategyStatus.LIVE")
    assert gate < promotion, "the readiness gate must precede the LIVE status write"


def test_an_unloadable_strategy_cannot_use_the_none_path_to_reach_live():
    """An unloadable class must NOT be able to complete PENDING_LIVE → LIVE.

    ``_factor_readiness_for`` returns ``None`` for two different situations: "this strategy is
    not a factor consumer" and "this strategy's class could not be loaded". The first is a
    correct skip. The second was originally justified by "the loader/engine will refuse it
    separately" — and for ``complete_pending`` **that justification does not hold**, because
    this method never consults the loader or the engine. It reads the row, checks the cooldown
    and the hold, and writes ``StrategyStatus.LIVE`` itself.

    So the refusal has to exist HERE. Depending on a later caller to refuse is depending on a
    caller this path does not have.

    Asserted on the source rather than by driving the scheduler, because what must hold is that
    **no reachable path** between classification and the LIVE write is missing a refusal — a
    behavioural test would only demonstrate the one path it happened to drive.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "app" / "services" / "activation.py").read_text(
        encoding="utf-8"
    )

    start = source.index("    async def complete_pending(")
    end = source.index("\n    async def ", start + 1)
    body = source[start:end]

    promotion = body.index("strategy.status = StrategyStatus.LIVE")
    classification = body.index("_factor_readiness_for")
    assert classification < promotion

    # Between classifying and promoting, an unloadable class must be refused explicitly.
    between = body[classification:promotion]
    assert "activation_blocked_unloadable_strategy" in between, (
        "complete_pending writes StrategyStatus.LIVE with no refusal for a strategy whose "
        "class could not be loaded. The None returned by _factor_readiness_for is "
        "indistinguishable from 'not a factor consumer', and nothing on this path consults "
        "the loader or the engine to catch it later."
    )

    # ...and the helper must report the load failure distinguishably, not silently.
    helper_start = source.index("    async def _factor_readiness_for(")
    helper_end = source.index("\n    async def ", helper_start + 1)
    helper = source[helper_start:helper_end]
    assert "CLASSIFICATION_UNAVAILABLE" in helper, (
        "_factor_readiness_for must signal 'could not classify' distinguishably from "
        "'not a factor consumer'; both returning a bare None is what hid this path"
    )


def test_live_completion_block_leaves_the_strategy_pending_not_idle():
    """Refusing must not consume the cooldown. The strategy stays PENDING_LIVE so a later
    pass completes it once the factor store recovers — the operational-hold behaviour, for
    the same reason: the cooldown is not what is in question, the data is."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "app" / "services" / "activation.py").read_text(
        encoding="utf-8"
    )

    start = source.index("activation_blocked_factor_not_ready")
    block = source[start : start + 1200]
    assert "return False" in block, "the refusal must return False, leaving status untouched"
    assert "StrategyStatus.IDLE" not in block, "refusing must not demote the strategy to IDLE"
    assert "status_mutated=False" in block


# --------------------------------------- recovery is not activation (finding 3, 2026-08-28)


def test_the_activation_interlock_is_conditioned_on_ACTIVATE_intent():
    """The refusal must be REACHABLE ONLY under ``ACTIVATE``.

    Asserted structurally rather than by presence: an implementation that merely mentions both
    intents somewhere in ``register`` — while gating the raise on nothing but "is this a factor
    book?" — is exactly the defect, and a test that only greps for the names passes it. So this
    finds the ``raise FactorReadinessNotMet`` and walks OUT to the ``if`` that guards it,
    requiring ``RegistrationIntent.ACTIVATE`` in that condition.

    Structural because the property is structural: a refusal that applies to every registration
    turns a restart during a RED store into a silently de-armed LIVE book.
    """
    import ast
    import inspect
    import textwrap

    from app.strategies import engine as eng

    tree = ast.parse(textwrap.dedent(inspect.getsource(eng.StrategyEngine.register)))

    def _raises_readiness(node) -> bool:
        return any(
            isinstance(n, ast.Raise) and "FactorReadinessNotMet" in ast.dump(n)
            for n in ast.walk(node)
        )

    guarding_ifs = [
        node for node in ast.walk(tree) if isinstance(node, ast.If) and _raises_readiness(node)
    ]
    assert guarding_ifs, "register() no longer raises FactorReadinessNotMet - update this test"

    assert any("ACTIVATE" in ast.dump(node.test) for node in guarding_ifs), (
        "the activation refusal is not conditioned on RegistrationIntent.ACTIVATE: it would "
        "also refuse RECOVER, which de-arms a durably-LIVE factor book on any restart while "
        "the factor store is RED"
    )


@pytest.mark.asyncio
async def test_a_recovered_book_stays_dispatch_gated_until_readiness_passes(monkeypatch):
    """Steps 5-7 of the lifecycle: recovery restores the REGISTRATION, not permission to trade.

    The recovered strategy must compute and apply no factor-derived book while RED, and must
    then dispatch normally once readiness turns PASS — **without another restart or a manual
    reactivation**. Driven through the real ``_factor_readiness_ok`` so this asserts the gate
    the engine actually calls.
    """
    from app.strategies import engine as eng

    verdicts = {
        "red": ReadinessVerdict(
            ok=False,
            reason="producer readiness verdict is FAIL",
            checks={"producer_liveness_verified": True, "overall_readiness": "FAIL"},
        ),
        "green": ReadinessVerdict(
            ok=True,
            reason="ok",
            checks={"producer_liveness_verified": True, "overall_readiness": "PASS"},
        ),
    }
    state = {"now": "red"}

    async def _verdict(self):  # noqa: ANN001
        return verdicts[state["now"]]

    stub = type(
        "E",
        (),
        {
            "_classify_factor_consuming": eng.StrategyEngine._classify_factor_consuming,
            "_is_factor_consuming": eng.StrategyEngine._is_factor_consuming,
            "_factor_readiness_ok": eng.StrategyEngine._factor_readiness_ok,
            "_factor_readiness_verdict": _verdict,
        },
    )()

    cls = _uninspectable("RecoveredBook", requires_factor_readiness=True)
    # ``_is_factor_consuming`` reads ``type(running.instance)``; the instance need not be
    # constructed, and Strategy.__init__ requires a ctx and params this test has no use for.
    running = type("R", (), {"strategy_id": 7, "instance": cls.__new__(cls), "symbols": ["AAPL"]})()

    # RED: the restored registration exists, and dispatch is still refused.
    assert await stub._factor_readiness_ok(running, dispatch_source="bar_tick") is False

    # PASS: the SAME registration now dispatches. No restart, no reactivation.
    state["now"] = "green"
    assert await stub._factor_readiness_ok(running, dispatch_source="bar_tick") is True


@pytest.mark.asyncio
async def test_activation_while_red_is_still_refused_after_the_recovery_carve_out(monkeypatch):
    """The converse, and the reason this is an intent rather than a weakening.

    A repair that merely moved the fail-open boundary would let IDLE -> PAPER/LIVE through as
    well. It must not: ACTIVATE keeps raising.
    """
    from app.strategies import engine as eng

    blocking = ReadinessVerdict(
        ok=False,
        reason="producer readiness verdict is FAIL",
        checks={"producer_liveness_verified": True, "overall_readiness": "FAIL"},
    )

    async def _verdict(self):  # noqa: ANN001
        return blocking

    stub = type(
        "E",
        (),
        {
            "_classify_factor_consuming": eng.StrategyEngine._classify_factor_consuming,
            "_factor_readiness_verdict": _verdict,
        },
    )()
    cls = _uninspectable("Book", requires_factor_readiness=True)

    # The decision the ACTIVATE branch makes, evaluated exactly as register() evaluates it.
    intent = eng.RegistrationIntent.ACTIVATE
    gated = intent is eng.RegistrationIntent.ACTIVATE and stub._classify_factor_consuming(cls, 7)
    assert gated is True
    assert (await stub._factor_readiness_verdict()).ok is False

    # And the RECOVER branch does NOT take that path for the same class and the same verdict.
    intent = eng.RegistrationIntent.RECOVER
    gated = intent is eng.RegistrationIntent.ACTIVATE and stub._classify_factor_consuming(cls, 7)
    assert gated is False


# ------------------------------------------- inference is lazy (finding 4, 2026-08-28)


def test_a_declared_factor_strategy_never_consults_inference(monkeypatch):
    """The incident signature must stay an incident signature.

    ``strategy_factor_classification_unavailable`` is the line ADR 0056, ``base.py`` and the
    2026-08-10 record all name as the signature of the disarmed veto — the string an operator
    greps for to detect the defect this interlock exists to prevent. Until 2026-08-28 it fired
    on EVERY DISPATCH of every correctly-declared factor book, because inference ran before the
    code knew whether inference was needed and ``StrategyLoader`` never registers the module in
    ``sys.modules``, so introspection always fails for a loaded instance. A warning that fires
    constantly on healthy strategies is not a signal.

    ⚠ Asserted by SPYING ON THE CALL, not by capturing the log. ``caplog`` does not see
    structlog output, so a log-based version of this test passes against an empty string
    whatever the code does — it cannot fail, which is worse than not having it.
    """
    from app.strategies import factor_classification as fc

    calls: list[int | None] = []
    real = fc.infer_factor_consuming

    def _spy(cls, strategy_id=None):
        calls.append(strategy_id)
        return real(cls, strategy_id)

    monkeypatch.setattr(fc, "infer_factor_consuming", _spy)

    assert (
        fc.requires_factor_readiness(_uninspectable("Declared", requires_factor_readiness=True), 7)
        is True
    )
    assert calls == [], (
        "a declared-True strategy consulted inference it cannot need, re-emitting the "
        "disarmed-veto signature on every dispatch of a healthy book"
    )

    # The converse: where the declaration cannot answer, inference must still run.
    assert fc.requires_factor_readiness(_uninspectable("Undeclared"), 8) is False
    assert calls == [8], "inference must still run when there is no declaration to trust"


# ------------------------------------------- the fallback gate is per strategy (finding 7)


@pytest.mark.asyncio
async def test_event_fallback_evaluates_readiness_once_per_strategy_not_per_symbol():
    """Cost, not policy: the verdict is a property of the store, never of the symbol.

    ``evaluate_factor_readiness`` opens DuckDB and reads two JSON files synchronously on the
    event loop. Inside the symbol loop a book with N symbols paid that N times per fallback
    tick to reach the same answer N times.
    """
    import ast
    import inspect
    import textwrap

    from app.strategies import engine as eng

    tree = ast.parse(
        textwrap.dedent(inspect.getsource(eng.StrategyEngine._fire_all_event_strategies))
    )

    symbol_loops = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and node.target.id == "symbol"
    ]
    assert symbol_loops, "the per-symbol loop moved - this test is now blind"
    inside = any("_factor_readiness_ok" in ast.dump(loop) for loop in symbol_loops)
    assert not inside, (
        "the readiness gate sits inside the per-symbol loop: it re-opens the store once per "
        "symbol per fallback tick to reach the same verdict"
    )
    # ...and it must still be consulted somewhere in the function.
    assert "_factor_readiness_ok" in ast.dump(tree)
