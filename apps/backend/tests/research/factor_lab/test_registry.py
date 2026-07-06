"""Factor Lab factor registry (plan v0.2 §3.2)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.factor_data.store import FactorDataStore
from app.research.factor_lab.registry import FACTOR_BUILDERS, build_score_fn

_AS_OF = date(2020, 6, 1)


def test_momentum_factor_resolves_and_scores(volatile_store: FactorDataStore) -> None:
    fn = build_score_fn("momentum", n=24, factor_params={"lookback_days": 252, "skip_days": 0})
    df = fn(volatile_store, _AS_OF)
    assert isinstance(df, pd.DataFrame) and "score" in df.columns and len(df) >= 20


def test_low_vol_factor_resolves_and_scores(volatile_store: FactorDataStore) -> None:
    fn = build_score_fn("low_vol", n=24, factor_params={"lookback_days": 252})
    df = fn(volatile_store, _AS_OF)
    assert "score" in df.columns
    # low-vol score = -vol, sorted desc → the calmest constructed name (VOL00) ranks at/near top
    assert df.index[0] == "VOL00"


def test_unknown_factor_raises() -> None:
    with pytest.raises(KeyError, match="unknown factor"):
        build_score_fn("does_not_exist", n=24, factor_params={})


def test_registered_factor_set() -> None:
    assert {"momentum", "low_vol", "composite"} <= set(FACTOR_BUILDERS)
