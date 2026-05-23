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
