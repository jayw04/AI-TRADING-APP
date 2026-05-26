"""StrategyLoader tests — path-traversal, missing files, multi-subclass guard."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.strategies.loader import StrategyLoader, StrategyLoadError


@pytest.fixture
def fixtures_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "strategies"


def test_loader_finds_echo_strategy(fixtures_root):
    loader = StrategyLoader(fixtures_root)
    cls = loader.load("echo_strategy.py")
    assert cls.__name__ == "EchoStrategy"
    assert cls.name == "echo"


def test_loader_rejects_path_outside_root(fixtures_root):
    loader = StrategyLoader(fixtures_root)
    with pytest.raises(StrategyLoadError, match="escapes"):
        loader.load("../../app/main.py")


def test_loader_rejects_missing_file(fixtures_root):
    loader = StrategyLoader(fixtures_root)
    with pytest.raises(StrategyLoadError, match="file not found"):
        loader.load("does_not_exist.py")


def test_loader_rejects_non_python(fixtures_root):
    j = fixtures_root / "junk.txt"
    j.write_text("not python")
    try:
        loader = StrategyLoader(fixtures_root)
        with pytest.raises(StrategyLoadError, match="not a Python file"):
            loader.load("junk.txt")
    finally:
        j.unlink()


def test_loader_rejects_no_strategy_subclass(fixtures_root):
    f = fixtures_root / "_no_subclass.py"
    f.write_text("def hello(): return 'world'\n")
    try:
        loader = StrategyLoader(fixtures_root)
        with pytest.raises(StrategyLoadError, match="no Strategy subclass"):
            loader.load("_no_subclass.py")
    finally:
        f.unlink()


def test_loader_requires_dunder_strategy_when_multiple_subclasses(fixtures_root):
    """If a file defines >1 Strategy subclass, the loader insists on
    ``__strategy__ = TheClass`` to disambiguate."""
    f = fixtures_root / "_multi.py"
    f.write_text(
        "from app.strategies import Strategy\n"
        "class A(Strategy):\n"
        "    name = 'a'\n"
        "class B(Strategy):\n"
        "    name = 'b'\n"
    )
    try:
        loader = StrategyLoader(fixtures_root)
        with pytest.raises(StrategyLoadError, match="declare __strategy__"):
            loader.load("_multi.py")
    finally:
        f.unlink()


def test_loader_uses_dunder_strategy_when_declared(fixtures_root):
    f = fixtures_root / "_multi_resolved.py"
    f.write_text(
        "from app.strategies import Strategy\n"
        "class A(Strategy):\n"
        "    name = 'a'\n"
        "class B(Strategy):\n"
        "    name = 'b'\n"
        "__strategy__ = B\n"
    )
    try:
        loader = StrategyLoader(fixtures_root)
        cls = loader.load("_multi_resolved.py")
        assert cls.name == "b"
    finally:
        f.unlink()


# ---------- P4 §7: params_schema is read off the class ----------


def test_base_strategy_params_schema_defaults_to_none():
    """The base class default is ``None`` — distinguishable from an empty
    declared dict so the frontend can choose between form vs textarea
    fallback."""
    from app.strategies.base import Strategy

    assert hasattr(Strategy, "params_schema")
    assert Strategy.params_schema is None


def test_loader_reads_params_schema_from_subclass(fixtures_root):
    """A strategy that declares ``params_schema`` exposes it on the loaded
    class without the loader copying or transforming the dict."""
    f = fixtures_root / "_with_schema.py"
    f.write_text(
        "from typing import ClassVar\n"
        "from app.strategies import Strategy\n"
        "class WithSchema(Strategy):\n"
        "    name = 'with-schema'\n"
        "    params_schema: ClassVar[dict] = {\n"
        '        "lookback": {"type": "integer", "min": 1, "max": 200, "default": 14},\n'
        '        "threshold": {"type": "number", "min": 0, "max": 1, "default": 0.5},\n'
        "    }\n"
    )
    try:
        loader = StrategyLoader(fixtures_root)
        cls = loader.load("_with_schema.py")
        assert cls.params_schema is not None
        assert cls.params_schema["lookback"]["type"] == "integer"
        assert cls.params_schema["threshold"]["default"] == 0.5
    finally:
        f.unlink()


def test_loader_schema_is_none_when_subclass_does_not_declare(fixtures_root):
    """Subclasses that don't override inherit the base ``None`` default —
    the frontend interprets this as 'no schema declared, show textarea'."""
    f = fixtures_root / "_no_schema.py"
    f.write_text(
        "from app.strategies import Strategy\n"
        "class NoSchema(Strategy):\n"
        "    name = 'no-schema'\n"
    )
    try:
        loader = StrategyLoader(fixtures_root)
        cls = loader.load("_no_schema.py")
        assert getattr(cls, "params_schema", "missing") is None
    finally:
        f.unlink()


def test_reference_rsi_strategy_declares_schema():
    """The reference RSI strategy ships with a real schema so the form is
    demonstrable on day one."""
    root = (
        Path(__file__).resolve().parents[2] / "strategies_user"
    )
    loader = StrategyLoader(root)
    cls = loader.load("examples/rsi_meanreversion.py")
    assert cls.params_schema is not None
    assert "entry_threshold" in cls.params_schema
    assert cls.params_schema["timeframe"]["type"] == "enum"
    assert cls.params_schema["max_position_qty"]["type"] == "integer"
