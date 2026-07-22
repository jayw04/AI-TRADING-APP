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
