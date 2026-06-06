"""P7 §3 — the AST safety validator for generated strategy code."""
from __future__ import annotations

import pytest

from app.services.strategy_authoring.code_safety import (
    UnsafeCodeError,
    validate_generated_code,
)

SAFE = """
from __future__ import annotations
from decimal import Decimal
from typing import Any, ClassVar
from datetime import time
from app.db.enums import OrderSide, OrderType
from app.risk import OrderRequest
from app.strategies import Strategy

class Gen(Strategy):
    name = "gen"
    async def on_bar(self, bar):
        pos = await self.ctx.get_position_for(bar.symbol)
        side = getattr(pos, "side", None)   # getattr is allowed
        if side == "long":
            pass
"""


def test_safe_code_passes():
    validate_generated_code(SAFE)  # no raise


@pytest.mark.parametrize("src", [
    "import os",
    "import socket",
    "import subprocess",
    "import requests",
    "from app.brokers import alpaca",
    "from urllib import request",
    "import httpx",
    "import threading",
    "import importlib",
])
def test_forbidden_imports_rejected(src):
    with pytest.raises(UnsafeCodeError, match="forbidden import"):
        validate_generated_code(src)


@pytest.mark.parametrize("src", [
    "x = eval('1+1')",
    "exec('y = 2')",
    "f = open('/etc/passwd')",
    "m = __import__('os')",
    "g = globals()",
])
def test_forbidden_calls_rejected(src):
    with pytest.raises(UnsafeCodeError, match="forbidden call"):
        validate_generated_code(src)


def test_sandbox_escape_attr_rejected():
    with pytest.raises(UnsafeCodeError, match="forbidden attribute"):
        validate_generated_code("klass = ().__class__.__subclasses__()")


def test_relative_import_rejected():
    with pytest.raises(UnsafeCodeError, match="relative import"):
        validate_generated_code("from . import something")


def test_syntax_error_propagates():
    with pytest.raises(SyntaxError):
        validate_generated_code("def oops(:\n    pass")
