"""Provider unit conventions, stated explicitly.

The store keeps one canonical unit set: volume in **shares**, traded amount in **CNY**, prices in CNY
per share. Each provider's native unit and the multiplier applied are recorded with every ingest, so
the conversion can be checked against the raw payload.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class UnitSpec:
    provider: str
    volume_unit: str
    volume_to_shares: float
    amount_unit: str
    amount_to_cny: float
    price_unit: str = "CNY/share"
    date_format: str = "%Y%m%d"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


#: Tushare ``daily``: ``vol`` is in lots (手, 100 shares); ``amount`` is in thousand CNY (千元).
TUSHARE = UnitSpec(
    provider="tushare_pro",
    volume_unit="lot (100 shares)",
    volume_to_shares=100.0,
    amount_unit="thousand CNY",
    amount_to_cny=1000.0,
    date_format="%Y%m%d",
)

#: Baostock ``query_history_k_data_plus``: ``volume`` in shares (股), ``amount`` in CNY (元).
BAOSTOCK = UnitSpec(
    provider="baostock",
    volume_unit="share",
    volume_to_shares=1.0,
    amount_unit="CNY",
    amount_to_cny=1.0,
    date_format="%Y-%m-%d",
)

SYNTHETIC = UnitSpec(
    provider="cn_synthetic",
    volume_unit="share",
    volume_to_shares=1.0,
    amount_unit="CNY",
    amount_to_cny=1.0,
    date_format="%Y-%m-%d",
)
