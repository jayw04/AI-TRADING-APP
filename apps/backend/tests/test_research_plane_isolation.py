"""Tests for the research-plane isolation invariant.

These are FALSIFICATION tests, and that is the point. A check that reports OK on the current
tree proves nothing on its own — the tree is currently clean, so a check that always exits 0
would look identical. Each case below constructs a synthetic module tree, plants one specific
violation (or one specific *legitimate* pattern), and asserts the checker discriminates.

The two negative controls matter as much as the positives: they pin that the invariant is a
prohibition on **capability**, not on research. If ``test_market_data_import_is_allowed`` or
``test_string_and_comment_are_not_imports`` ever starts failing, the check has become a blanket
ban and is wrong even though it is "stricter".
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CHECK = Path(__file__).resolve().parents[1] / "scripts" / "check_research_plane_isolation.py"

PACKAGES = (
    "app/research",
    "app/research/sub",
    "app/research/capture",
    "app/risk",
    "app/orders",
    "app/brokers",
    "app/strategies",
    "app/factor_data",
    "app/altdata",
    "app/services",
)


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    """A minimal backend layout with the checker installed at its expected depth."""
    (tmp_path / "scripts").mkdir()
    shutil.copy(CHECK, tmp_path / "scripts" / CHECK.name)
    for pkg in PACKAGES:
        d = tmp_path / pkg
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").touch()
    return tmp_path


def run(tree: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(tree / "scripts" / CHECK.name)],
        capture_output=True,
        text=True,
    )


def test_clean_tree_passes(tree: Path) -> None:
    r = run(tree)
    assert r.returncode == 0, r.stderr
    assert "research-plane isolation OK" in r.stdout


# --- property A: the research plane must not acquire execution capability ------------------


def test_direct_order_path_import_fails(tree: Path) -> None:
    (tree / "app/research/bad.py").write_text("from app.risk import RiskEngine\n")
    r = run(tree)
    assert r.returncode == 1
    assert "RESEARCH-PLANE CAPABILITY VIOLATION" in r.stderr
    assert "app.risk" in r.stderr


def test_capability_laundered_through_a_sibling_module_fails(tree: Path) -> None:
    """The bypass a direct-import check does not close: move the call one module over."""
    (tree / "app/research/sub/helper.py").write_text("from app.risk import RiskEngine\n")
    (tree / "app/research/launder.py").write_text(
        "from app.research.sub.helper import RiskEngine\n"
    )
    r = run(tree)
    assert r.returncode == 1
    # the reported chain must name the intermediary, not just the endpoints
    assert "app.research.launder -> app.research.sub.helper -> app.risk" in r.stderr


def test_real_trading_sdk_import_fails(tree: Path) -> None:
    (tree / "app/research/bad.py").write_text("from alpaca.trading.client import TradingClient\n")
    r = run(tree)
    assert r.returncode == 1
    assert "alpaca.trading" in r.stderr


# --- property B: the order path must not consume the MDQ archive ---------------------------


def test_order_path_importing_mdq_archive_fails(tree: Path) -> None:
    (tree / "app/risk/bad.py").write_text(
        "from app.research.capture.admissibility import Verdict\n"
    )
    r = run(tree)
    assert r.returncode == 1
    assert "ORDER-PATH ARCHIVE VIOLATION" in r.stderr
    assert "app.research.capture" in r.stderr


# --- negative controls: the invariant is about capability, NOT about research ---------------


def test_market_data_import_is_allowed(tree: Path) -> None:
    """Research may read market data. Banning this would be stricter and wrong."""
    (tree / "app/research/ok.py").write_text(
        "from alpaca.data.historical import StockHistoricalDataClient\n"
    )
    r = run(tree)
    assert r.returncode == 0, r.stderr


def test_string_and_comment_are_not_imports(tree: Path) -> None:
    """Both patterns exist in the real tree and are correct code; a grep check fails them."""
    (tree / "app/research/ok.py").write_text(
        '# deliberately not the alpaca.trading SDK\nDENY = ["alpaca.trading"]\n'
    )
    r = run(tree)
    assert r.returncode == 0, r.stderr


def test_shared_module_is_a_leaf_not_a_violation(tree: Path) -> None:
    """Research importing app.strategies is legitimate even though strategies dispatches.

    Unbounded transitivity reported every backtester as holding execution capability. Whether
    ``app.strategies`` may touch the order path is check_adr0002 / check_strategy_isolation's
    question, not this one.
    """
    (tree / "app/strategies/engine.py").write_text("from app.risk import RiskEngine\n")
    (tree / "app/research/backtest.py").write_text("from app.strategies.engine import Engine\n")
    r = run(tree)
    assert r.returncode == 0, r.stderr


def test_the_real_repository_satisfies_the_invariant() -> None:
    """The live tree must pass — this is the invariant, not a fixture."""
    r = subprocess.run([sys.executable, str(CHECK)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
