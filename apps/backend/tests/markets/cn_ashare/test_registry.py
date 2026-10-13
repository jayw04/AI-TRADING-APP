"""China strategy registry: persistent, and existing run ids stay attached."""

from __future__ import annotations

from pathlib import Path

from app.markets.cn_ashare.registry import SEED, catalog
from app.markets.cn_ashare.store import CnAshareStore


def test_seed_is_idempotent_and_keeps_an_edited_row(tmp_path: Path) -> None:
    db = tmp_path / "cn_ashare_registry.duckdb"
    cache = tmp_path / "cache"
    with CnAshareStore(db, cache) as store:
        store.con.execute(
            "UPDATE cn_strategies SET status = 'CANDIDATE', blocked_reason = NULL WHERE cn_strategy_id = 'CN-RANGE-ORB'"
        )
    with CnAshareStore(db, cache) as store:
        rows = store.registry()
    assert rows is not None
    by_id = {r["cn_strategy_id"]: r for r in rows}
    assert set(by_id) == {row[0] for row in SEED}
    assert by_id["CN-MOM-20D"]["equivalence"] == "NOT_ASSUMED"
    assert by_id["CN-MOM-20D"]["source_us_strategy_id"] is None
    assert by_id["CN-RANGE-ORB"]["status"] == "CANDIDATE"
    assert by_id["CN-LOWVOL-W"]["source_us_strategy_id"] == 8
    assert by_id["CN-LOWVOL-W"]["status"] == "BLOCKED"
    ids = [c["cn_strategy_id"] for c in catalog()]
    assert ids[:2] == ["CN-MOM-20D", "CN-REV-5D"]
