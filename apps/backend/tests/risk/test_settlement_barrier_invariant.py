"""ADR 0043 — the settlement-barrier structural invariant, proven in both directions.

A checker that only ever passes is indistinguishable from one that checks nothing, so every test
here comes in a pair: the REAL repository satisfies the invariant, and a synthetic module that
violates it is caught. The synthetic cases are written the way the mistake would actually be made —
a harness author reaching for ``router.submit`` because it is the obvious thing to call.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts.check_settlement_barrier import (
    SEAM_CLASS,
    check_no_direct_barrier,
    check_no_direct_submit,
    check_seam_settles,
    governed_files,
    main,
    run,
)


def _tree(src: str) -> ast.AST:
    return ast.parse(src)


# ---------------------------------------------------------------------------- the real repo


def test_the_real_governed_harnesses_satisfy_the_invariant():
    assert run(governed_files()) == []


def test_the_checker_governs_every_adr0043_harness_module():
    """A glob, not a hand-maintained list: a new harness is governed the moment it is added."""
    names = {p.name for p in governed_files()}
    assert {"adr0043_canary_lib.py", "adr0043_canary_run.py", "adr0043_churn_driver.py"} <= names


def test_main_passes_on_the_real_repository(capsys):
    assert main() == 0
    assert "settlement-barrier invariant OK" in capsys.readouterr().out


# ---------------------------------------------------------------------------- (1) no direct submit


def test_direct_router_submit_in_a_harness_is_caught():
    src = """
async def place(router, req):
    return await router.submit(req)
"""
    v = check_no_direct_submit("scripts/adr0043_rogue.py", _tree(src))
    assert len(v) == 1 and v[0].invariant == "no-direct-submit"


def test_submit_through_any_object_is_caught_not_just_router():
    """The rule is about the CALL, not the receiver's name — ``self._r.submit`` is the same hole."""
    src = """
async def place(self, req):
    return await self._r.submit(req)
"""
    assert check_no_direct_submit("scripts/adr0043_rogue.py", _tree(src))


def test_multiline_submit_is_caught():
    src = """
async def place(router, req):
    return await router.submit(
        req,
    )
"""
    assert check_no_direct_submit("scripts/adr0043_rogue.py", _tree(src))


def test_the_seam_module_itself_may_submit():
    src = "async def _submit(self, req):\n    return await self.router.submit(req)\n"
    assert check_no_direct_submit("scripts/adr0043_canary_lib.py", _tree(src)) == []


def test_a_docstring_mentioning_submit_is_not_a_violation():
    src = '''
async def place(sub, req):
    """Never call router.submit() here — use the seam."""
    return await sub.submit_and_settle(step="X", request={}, order_req=req, ticker="MSFT")
'''
    assert check_no_direct_submit("scripts/adr0043_rogue.py", _tree(src)) == []


def test_calling_the_sanctioned_seam_methods_is_not_a_violation():
    src = """
async def place(sub, req):
    a = await sub.submit_and_settle(step="A", request={}, order_req=req, ticker="MSFT")
    b = await sub.submit_expecting_refusal(step="B", request={}, order_req=req, ticker="MSFT")
    return a, b
"""
    assert check_no_direct_submit("scripts/adr0043_rogue.py", _tree(src)) == []


# ---------------------------------------------------------------------------- (2) no direct barrier


def test_importing_settle_order_in_a_harness_is_caught():
    src = "from app.orders.settlement import settle_order\n"
    v = check_no_direct_barrier("scripts/adr0043_rogue.py", _tree(src))
    assert len(v) == 1 and v[0].invariant == "no-direct-barrier"


def test_calling_settle_order_in_a_harness_is_caught():
    src = """
async def go(sf, ad, c):
    return await settle_order(sf, ad, c, order_id=1, ticker="MSFT")
"""
    assert check_no_direct_barrier("scripts/adr0043_rogue.py", _tree(src))


def test_module_qualified_settle_order_call_is_caught():
    src = """
import app.orders.settlement as s

async def go(sf, ad, c):
    return await s.settle_order(sf, ad, c, order_id=1, ticker="MSFT")
"""
    assert check_no_direct_barrier("scripts/adr0043_rogue.py", _tree(src))


def test_the_seam_module_may_use_the_barrier():
    src = """
from app.orders.settlement import settle_order

async def go(sf, ad, c):
    return await settle_order(sf, ad, c, order_id=1, ticker="MSFT")
"""
    assert check_no_direct_barrier("scripts/adr0043_canary_lib.py", _tree(src)) == []


# ---------------------------------------------------------------------------- (3) the seam settles


def _seam(body_and: str, refusal_body: str = "await self.settle_existing(step=s, order_id=i)") -> str:
    return f"""
class {SEAM_CLASS}:
    async def submit_and_settle(self, *, step, request, order_req, ticker, pre=None):
        {body_and}

    async def submit_expecting_refusal(self, *, step, request, order_req, ticker):
        {refusal_body}
"""


def test_a_seam_that_settles_passes():
    src = _seam("return await self.settle_existing(step=step, order_id=1, ticker=ticker)")
    assert check_seam_settles("scripts/adr0043_canary_lib.py", _tree(src)) == []


def test_a_seam_that_submits_without_settling_is_caught():
    """The rule the other two rest on: without it, a seam could satisfy them while settling
    nothing, and every harness would be 'compliant' while placing unsettled orders."""
    src = _seam("return await self.router.submit(order_req)")
    v = check_seam_settles("scripts/adr0043_canary_lib.py", _tree(src))
    assert len(v) == 1 and v[0].invariant == "seam-does-not-settle"
    assert "submit_and_settle" in v[0].detail


def test_a_refusal_path_that_never_reconciles_is_caught():
    src = _seam("return await self.settle_existing(step=step, order_id=1, ticker=ticker)",
                refusal_body="return None")
    v = check_seam_settles("scripts/adr0043_canary_lib.py", _tree(src))
    assert len(v) == 1 and "submit_expecting_refusal" in v[0].detail


def test_a_missing_seam_class_is_caught():
    v = check_seam_settles("scripts/adr0043_canary_lib.py", _tree("x = 1\n"))
    assert len(v) == 1 and v[0].invariant == "seam-missing"


def test_a_missing_seam_method_is_caught():
    src = f"""
class {SEAM_CLASS}:
    async def submit_and_settle(self, **kw):
        return await self.settle_existing(**kw)
"""
    v = check_seam_settles("scripts/adr0043_canary_lib.py", _tree(src))
    assert len(v) == 1 and "submit_expecting_refusal" in v[0].detail


# ---------------------------------------------------------------------------- reporting


def test_a_violating_file_makes_run_report_it(tmp_path: Path, monkeypatch):
    rogue = tmp_path / "adr0043_rogue.py"
    rogue.write_text("async def go(r, q):\n    return await r.submit(q)\n", encoding="utf-8")
    monkeypatch.setattr("scripts.check_settlement_barrier.BACKEND", tmp_path)
    violations = run([rogue])
    assert [v.invariant for v in violations] == ["no-direct-submit"]
    assert violations[0].path == "adr0043_rogue.py"


def test_a_syntax_error_is_surfaced_not_swallowed(tmp_path: Path, monkeypatch):
    bad = tmp_path / "adr0043_bad.py"
    bad.write_text("def broken(:\n", encoding="utf-8")
    monkeypatch.setattr("scripts.check_settlement_barrier.BACKEND", tmp_path)
    assert [v.invariant for v in run([bad])] == ["parse-error"]


def test_no_governed_modules_at_all_is_a_failure(monkeypatch, tmp_path, capsys):
    """An empty glob must not read as 'all clear' — that is how a checker silently stops checking."""
    monkeypatch.setattr("scripts.check_settlement_barrier.SCRIPTS", tmp_path)
    assert main() == 1
    assert "no governed harness modules" in capsys.readouterr().err


@pytest.mark.parametrize("check", [check_no_direct_submit, check_no_direct_barrier])
def test_checks_are_silent_on_unrelated_code(check):
    src = """
async def compute(x):
    total = sum(x)
    return total / len(x)
"""
    assert check("scripts/adr0043_rogue.py", _tree(src)) == []


# ---------------------------------------------------------------------------- alias bypasses
# The realistic bypass is never the obvious call — a reviewer sees `router.submit(req)`. It is the
# reference extracted a few lines earlier, after which every use reads as an ordinary local call.


def test_aliasing_submit_to_a_local_name_is_caught():
    src = """
async def go(router, q):
    submit = router.submit
    return await submit(q)
"""
    v = check_no_direct_submit("scripts/adr0043_rogue.py", _tree(src))
    assert v and v[0].invariant == "no-direct-submit"


def test_extracting_submit_via_getattr_is_caught():
    src = """
async def go(router, q):
    fn = getattr(router, "submit")
    return await fn(q)
"""
    v = check_no_direct_submit("scripts/adr0043_rogue.py", _tree(src))
    assert v and "getattr" in v[0].detail


def test_stashing_submit_in_a_container_is_caught():
    src = """
def wire(router):
    return {"place": router.submit}
"""
    assert check_no_direct_submit("scripts/adr0043_rogue.py", _tree(src))


def test_importing_settle_order_under_an_alias_is_caught():
    src = """
from app.orders.settlement import settle_order as settle

async def go(*a):
    return await settle(*a)
"""
    v = check_no_direct_barrier("scripts/adr0043_rogue.py", _tree(src))
    assert v and "aliased to settle" in v[0].detail


def test_aliasing_settle_order_off_a_module_is_caught():
    src = """
import app.orders.settlement as s

async def go(*a):
    barrier = s.settle_order
    return await barrier(*a)
"""
    assert check_no_direct_barrier("scripts/adr0043_rogue.py", _tree(src))


def test_extracting_settle_order_via_getattr_is_caught():
    src = """
import app.orders.settlement as s

async def go(*a):
    fn = getattr(s, "settle_order")
    return await fn(*a)
"""
    v = check_no_direct_barrier("scripts/adr0043_rogue.py", _tree(src))
    assert v and any("getattr" in x.detail for x in v)


def test_a_similarly_named_method_is_not_a_false_positive():
    """``submit_and_settle`` / ``submit_expecting_refusal`` ARE the sanctioned seam calls; an
    attribute check that fired on them would make the invariant unusable."""
    src = """
async def go(sub, req):
    return await sub.submit_and_settle(step="A", request={}, order_req=req, ticker="MSFT")
"""
    assert check_no_direct_submit("scripts/adr0043_rogue.py", _tree(src)) == []


# ---------------------------------------------------------------------------- gating assertions
# Assertion names are evidence-schema fields. Downstream verification looks for these exact strings,
# so an accidental rename is a silently missing check.


FROZEN_GATING_ASSERTIONS = {
    "A1.state_authoritative",
    "A2.verified_reduction_allowed",
    "A2.reduction_settled",
    "A2.admitted_as_verified_reduction",
    "A2.state_remains_reduction_only",
    "A2.settled",
    "A3.new_risk_refused",
    "A3.no_broker_submission",
    "A3.refusal_is_auditable",
    "A3.settled",
    "A4.reached_recovery_cooldown",
    "A5.evaluator_holds",
    "CHURN.settled",
    "CHURN.no_broker_submission",
    "PHASE0.lock_established",
    "already_complete",
}


def test_the_gating_assertion_inventory_is_frozen():
    """Two places must change together. An addition is then deliberate; a removal fails loudly
    rather than quietly dropping a required assertion from the evidence package."""
    from scripts.adr0043_canary_lib import GATING_ASSERTIONS

    assert set(GATING_ASSERTIONS) == FROZEN_GATING_ASSERTIONS


def _emitted_assertion_names() -> tuple[set[str], set[str]]:
    """Every name passed as the first argument to ``.assert_(...)`` across the governed harnesses,
    split into plain literals and the dynamic ``f"{_label(step)}.suffix"`` forms."""
    literals: set[str] = set()
    suffixes: set[str] = set()
    for path in governed_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "assert_" and node.args):
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                literals.add(first.value)
            elif isinstance(first, ast.JoinedStr):
                tail = first.values[-1]
                if isinstance(tail, ast.Constant) and isinstance(tail.value, str):
                    suffixes.add(tail.value)
    return literals, suffixes


def test_every_literal_assertion_is_registered():
    """A new assertion added to a harness without registering it fails here, so the inventory
    cannot silently fall behind the code."""
    from scripts.adr0043_canary_lib import GATING_ASSERTIONS

    literals, _ = _emitted_assertion_names()
    assert literals, "no assertion names found — the extractor is broken, not the harness"
    assert literals <= set(GATING_ASSERTIONS), literals - set(GATING_ASSERTIONS)


def test_every_dynamic_assertion_suffix_is_registered():
    """The seam emits ``f"{_label(step)}.settled"``; the concrete names it can produce must all be
    inventoried, or a gating assertion exists at runtime that nothing downstream expects."""
    from scripts.adr0043_canary_lib import GATING_ASSERTIONS

    _, suffixes = _emitted_assertion_names()
    assert suffixes, "no dynamic assertion names found — the extractor is broken"
    for suffix in suffixes:
        assert any(name.endswith(suffix) for name in GATING_ASSERTIONS), suffix
