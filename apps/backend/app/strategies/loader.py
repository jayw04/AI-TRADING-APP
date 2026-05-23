"""StrategyLoader — resolve a :class:`Strategy` class from a code_path under
``strategies_user/``.

Security: ``code_path`` values are *trusted* in P2 because they come from
the database, which is written only via the authenticated API. The loader
nevertheless refuses paths outside ``strategies_user/`` to prevent typos
or future API bugs from importing arbitrary files.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import structlog

from .base import Strategy

logger = structlog.get_logger(__name__)


class StrategyLoadError(Exception):
    """Raised when a code_path cannot be loaded or doesn't define a Strategy subclass."""


class StrategyLoader:
    def __init__(self, strategies_root: Path) -> None:
        self._root = strategies_root.resolve()
        if not self._root.exists():
            raise StrategyLoadError(f"strategies_user root does not exist: {self._root}")

    def load(self, code_path: str) -> type[Strategy]:
        """Resolve ``code_path`` (relative to ``strategies_user/``) and
        return the :class:`Strategy` subclass defined in it.

        Raises :class:`StrategyLoadError` on any failure: path outside root,
        file missing, no Strategy subclass found, or multiple subclasses
        without a clear ``__strategy__`` declaration.
        """
        path = (self._root / code_path).resolve()
        if not str(path).startswith(str(self._root)):
            raise StrategyLoadError(
                f"code_path escapes strategies_user/: {code_path}"
            )
        if not path.exists():
            raise StrategyLoadError(f"file not found: {path}")
        if path.suffix != ".py":
            raise StrategyLoadError(f"not a Python file: {path}")

        # Module name derived from the path so reloads work cleanly across
        # multiple register/unregister cycles.
        module_name = (
            f"strategies_user.{path.stem}_{abs(hash(str(path))) % 1_000_000}"
        )
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise StrategyLoadError(f"could not load spec for {path}")

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            raise StrategyLoadError(
                f"error executing strategy module {path}: {exc}"
            ) from exc

        # Strategy subclasses defined in this module (exclude Strategy itself
        # and any subclass imported from elsewhere).
        candidates = [
            obj
            for _, obj in inspect.getmembers(module, inspect.isclass)
            if issubclass(obj, Strategy)
            and obj is not Strategy
            and obj.__module__ == module.__name__
        ]
        if not candidates:
            raise StrategyLoadError(
                f"no Strategy subclass found in {path}. "
                "Did you forget to subclass Strategy?"
            )
        if len(candidates) > 1:
            # Convention: if multiple are defined, the module must declare
            # __strategy__ = <the_class>.
            chosen = getattr(module, "__strategy__", None)
            if chosen is None or chosen not in candidates:
                raise StrategyLoadError(
                    f"multiple Strategy subclasses in {path}; "
                    "declare __strategy__ = YourStrategy"
                )
            return chosen
        return candidates[0]
