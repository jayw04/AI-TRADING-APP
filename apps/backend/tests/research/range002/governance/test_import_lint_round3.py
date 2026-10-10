"""Round-3 bypass patterns for the import lint, one synthetic test per pattern.

The lint is a convenience check for accidental omissions and casual shortcuts (Level 1), not a
security boundary; these tests pin exactly which patterns it catches.
"""

from __future__ import annotations

import pytest

from .test_import_lint import GOOD_IMPORT, GOVERNANCE, PKG, RESULTS_GUARD, flagged

DEC = "@requires_capability\ndef run(*, capability):\n    return 1\n"


def lacks(src: str) -> bool:
    return any("'run' lacks" in p or "callable 'run'" in p for p in flagged(src))


# --- R-A2: public names bound to anything but plain def/class/constants ----------------------


@pytest.mark.parametrize(
    "src",
    [
        "run = make()\n",
        "import functools\nrun = functools.partial(print, 1)\n",
        "run = (lambda x: x, 2)\n",
        "a, run = 1, (lambda x: x)\n",
        "a, run = make()\n",
        "(run := lambda x: x)\n",
        "if (run := make()):\n    pass\n",
        "for run in fns:\n    pass\n",
        "with ctx() as run:\n    pass\n",
        "with a() as (x, run):\n    pass\n",
        "run = [f for f in fns]\n",
        "class K:\n    run = make()\n",
        "class K:\n    run = (lambda self: 1)\n",
        "run += make()\n",
        "run: object = make()\n",
    ],
)
def test_public_non_constant_bindings_are_flagged(src: str) -> None:
    assert any("'run' is" in p or "'K.run' is" in p for p in flagged(src)), src


def test_private_factory_returning_a_closure_bound_to_a_public_name() -> None:
    src = (
        "def _factory():\n    def inner(x):\n        return x\n    return inner\nrun = _factory()\n"
    )
    problems = flagged(src)
    assert any("'run'" in p and "factory" in p for p in problems)
    cls = "def _mk():\n    class Impl:\n        def go(self):\n            return 1\n    return Impl\nRun = _mk()\n"
    assert any("'Run'" in p for p in flagged(cls))


def test_namespace_games_are_flagged() -> None:
    assert any("globals()" in p for p in flagged("globals()['run'] = lambda: 1\n"))
    assert any("vars()" in p for p in flagged("vars()['run'] = 1\n"))
    assert any("exec()" in p for p in flagged("exec('def run(): pass')\n"))
    assert any("eval()" in p for p in flagged("x = eval('1')\n"))


def test_constants_and_private_values_are_fine() -> None:
    ok = (
        "X = 3\nY: int = 5\nZ = (1, 'a', -2)\nW = {'a': 1, 'b': [1, 2]}\nV = 1 << 4\n"
        "_hidden = make()\nfor _i in range(3):\n    pass\n"
        "class K:\n    LIMIT = 10\n    _cache = make()\n"
    )
    assert flagged(ok) == []


# --- dunder methods are entry points -----------------------------------------------------------


@pytest.mark.parametrize(
    "src",
    [
        "class K:\n    def __call__(self, x):\n        return x\n",
        "class K:\n    def __iter__(self):\n        return iter(())\n",
        "class K:\n    def __getattr__(self, n):\n        return 1\n",
        "class K:\n    async def __aenter__(self):\n        return 1\n",
        "def __getattr__(name):\n    return 1\n",
        "class _Hidden:\n    def __call__(self):\n        return 1\n",
    ],
)
def test_dunder_entry_points_are_flagged(src: str) -> None:
    assert any("dunder method" in p for p in flagged(src)), src


def test_harmless_dunders_and_decorated_call_are_fine() -> None:
    ok = (
        GOOD_IMPORT + "class K:\n    def __init__(self):\n        pass\n    def __repr__(self):\n"
        "        return 'K'\n    def __eq__(self, o):\n        return True\n"
        "    def __hash__(self):\n        return 1\n"
        "    @requires_capability\n    def __call__(self, *, capability):\n        return 1\n"
    )
    assert flagged(ok) == []


# --- every binding form of the decorator name voids the trust --------------------------------


@pytest.mark.parametrize(
    "shadow",
    [
        "a, requires_capability = 1, (lambda f: f)\n",  # tuple assignment
        "for requires_capability in (lambda f: f,):\n    pass\n",  # for target
        "with ctx() as requires_capability:\n    pass\n",  # with-as
        "(requires_capability := (lambda f: f))\n",  # walrus
        "def _x():\n    global requires_capability\n    requires_capability = lambda f: f\n",
        "class _C:\n    requires_capability = (lambda f: f)\n",  # class-body shadowing
        "def _f():\n    from other import requires_capability\n",  # import inside a function
        "def _g(requires_capability):\n    return requires_capability\n",  # parameter
        "try:\n    pass\nexcept Exception as requires_capability:\n    pass\n",
        "match 1:\n    case requires_capability:\n        pass\n",
        "del requires_capability\n",
        "import os as requires_capability\n",
    ],
)
def test_every_rebinding_form_voids_the_decorator(shadow: str) -> None:
    assert lacks(GOOD_IMPORT + shadow + DEC), shadow


def test_rebinding_an_attribute_alias_head_also_voids_it() -> None:
    src = f"import {RESULTS_GUARD} as rg\nrg = object()\n@rg.requires_capability\ndef run(*, capability):\n    return 1\n"
    assert lacks(src)
    inner = (
        f"import {RESULTS_GUARD} as rg\n"
        "def _f():\n    import functools as rg\n"
        "@rg.requires_capability\ndef run(*, capability):\n    return 1\n"
    )
    assert lacks(inner)


def test_a_clean_single_import_still_works() -> None:
    assert flagged(GOOD_IMPORT + DEC) == []


# --- R-E: reaching behind the decorator ------------------------------------------------------


def test_wrapped_and_unwrap_are_flagged() -> None:
    assert any("__wrapped__" in p for p in flagged("def _f(g):\n    return g.__wrapped__\n"))
    assert any(
        "__wrapped__" in p for p in flagged("def _f(g):\n    return getattr(g, '__wrapped__')\n")
    )
    assert any(
        "unwrap" in p for p in flagged("import inspect\ndef _f(g):\n    return inspect.unwrap(g)\n")
    )
    assert any(
        "unwrap" in p
        for p in flagged("from inspect import unwrap as u\ndef _f(g):\n    return u(g)\n")
    )
    assert any(
        "unwrap" in p for p in flagged("import inspect as i\ndef _f(g):\n    return i.unwrap(g)\n")
    )


# --- imports inside function bodies are no longer skipped -----------------------------------


def test_function_body_import_aliases_are_followed() -> None:
    src = f"def _f():\n    from {GOVERNANCE} import results_guard as r\n    return r._BOUND_REGISTRIES\n"
    assert any("private '_BOUND_REGISTRIES'" in p for p in flagged(src))
    via_getattr = f"def _f():\n    import {RESULTS_GUARD} as rg\n    return getattr(rg, '_ISSUE')\n"
    assert any("getattr" in p for p in flagged(via_getattr))
    rel = "def _f():\n    from ..governance import results_guard as r\n    return r._ISSUE\n"
    assert any("private '_ISSUE'" in p for p in flagged(rel, module=f"{PKG}.engine.mod"))
    dyn = (
        "def _f():\n    import importlib as il\n    return il.import_module('"
        + RESULTS_GUARD
        + "')\n"
    )
    assert any("dynamic import" in p for p in flagged(dyn))
