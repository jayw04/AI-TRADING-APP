"""Typed refusals for the screen kernel. Exceptions are classes: no callable to gate."""

from __future__ import annotations


class ScreenError(Exception):
    """Base class for screen-kernel refusals."""


class ParamsUnsetError(ScreenError):
    """A spec value the kernel reads is null/unsupported: the kernel fails closed (R9)."""


class SpecBindingError(ScreenError):
    """Params/spec/capability do not describe the same frozen specification."""


class DataDefectError(ScreenError):
    """Wrong feed, wrong timestamp convention, unsorted/duplicate/out-of-session bars,
    bad OHLC, or a session outside the capability's date range: engineering/data DEFECT,
    never a strategy verdict."""


class FunnelMismatchError(ScreenError):
    """Stage counts do not reconcile to the eligible symbol-days."""
