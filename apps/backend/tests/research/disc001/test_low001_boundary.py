"""v0.11 bidirectional LOW-001 / Opportunity isolation.

DISC-001 admission, history, checkpoints, and Why-it-left are a product and
observation surface. LOW-001 is an independent trading program. Neither
direction may feed the other:

* DISC candidate / checkpoint / Why-it-left / MDQ  →  LOW-001 selection or orders
* LOW-001 decision records / holdings / rebalance / orders
        →  Opportunity admission, ranking, badges, or sort

Shared platform infrastructure (session calendar, Sharadar store, permanent
identity) is allowed. This slice does not implement an observation-window
product filter; it asserts the admission/history path has no LOW-001 input.
"""

from __future__ import annotations

import ast
from pathlib import Path

import app.research.disc001 as disc001
from app.research.disc001.spec import SCREEN_VERSION

PACKAGE_DIR = Path(disc001.__file__).resolve().parent
BACKEND_DIR = Path(__file__).resolve().parents[3]
REPO_DIR = BACKEND_DIR.parent.parent

DISC_EXTRA = (
    BACKEND_DIR / "app" / "services" / "opportunity_history.py",
    BACKEND_DIR / "app" / "jobs" / "disc001_watchlist.py",
    BACKEND_DIR / "scripts" / "disc001_watchlist_snapshot.py",
)

LOW001_FILES = (
    BACKEND_DIR / "strategies_user" / "templates" / "low_volatility.py",
    BACKEND_DIR / "app" / "factor_data" / "factors" / "low_vol.py",
)

DISC_FRONTEND = (
    REPO_DIR / "apps" / "frontend" / "src" / "pages" / "Opportunities" / "History.tsx",
    REPO_DIR
    / "apps"
    / "frontend"
    / "src"
    / "pages"
    / "Opportunities"
    / "widgets"
    / "CandidateWatchlistWidget.tsx",
)

DISC_FORBIDDEN_IMPORTS = (
    "app.orders",
    "app.risk",
    "app.brokers",
    "app.mdq",
    "app.services.order_router",
    "app.db.models.fill",
    "app.db.models.order",
    "app.db.models.signal",
    "app.db.models.strategy",
    "strategies_user",
    "strategies_user.templates.low_volatility",
)

LOW001_FORBIDDEN_IMPORTS = (
    "app.research.disc001",
    "app.services.opportunity_history",
    "app.db.models.opportunity_occurrence",
    "app.api.v1.opportunities",
    "app.jobs.disc001_watchlist",
)

DISC_FORBIDDEN_TEXT = (
    "low_volatility",
    "strategies_user",
    "mdq_collector",
    "from app.mdq",
)

LOW001_FORBIDDEN_TEXT = (
    "disc001",
    "why_left",
    "opportunity_history",
    "opportunity_occurrence",
    "DISC-001-WATCHLIST",
)


def _imports_of(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _disc_files() -> list[Path]:
    files = sorted(PACKAGE_DIR.glob("*.py"))
    assert files, f"no modules found under {PACKAGE_DIR}"
    extras = [path for path in DISC_EXTRA if path.is_file()]
    assert extras, "DISC extra files missing"
    return [*files, *extras]


def _assert_no_prefix(name: str, prefixes: tuple[str, ...], path: Path) -> None:
    for prefix in prefixes:
        assert not (name == prefix or name.startswith(prefix + ".")), (
            f"{path.name} imports forbidden module {name!r} (matches {prefix!r})"
        )


def test_disc001_package_resolves_inside_this_checkout() -> None:
    assert str(PACKAGE_DIR).startswith(str(BACKEND_DIR)), (
        f"app.research.disc001 resolved to {PACKAGE_DIR}, outside this "
        f"checkout {BACKEND_DIR} — set PYTHONPATH to this apps/backend first"
    )


def test_screen_version_stays_frozen() -> None:
    assert SCREEN_VERSION == "v0.3.0"


def test_disc_admission_and_history_do_not_import_low001_or_order_path() -> None:
    for path in _disc_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in _imports_of(tree):
            _assert_no_prefix(name, DISC_FORBIDDEN_IMPORTS, path)


def test_disc_admission_and_history_source_names_no_low001_or_mdq() -> None:
    for path in _disc_files():
        text = path.read_text(encoding="utf-8")
        for needle in DISC_FORBIDDEN_TEXT:
            assert needle not in text, f"{path.name} names {needle!r}"


def test_low001_does_not_import_disc_or_opportunity_history() -> None:
    for path in LOW001_FILES:
        assert path.is_file(), f"missing {path}"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in _imports_of(tree):
            _assert_no_prefix(name, LOW001_FORBIDDEN_IMPORTS, path)
        text = path.read_text(encoding="utf-8")
        for needle in LOW001_FORBIDDEN_TEXT:
            assert needle not in text, f"{path.name} names {needle!r}"


def test_watchlist_and_history_ui_do_not_name_low001() -> None:
    for path in DISC_FRONTEND:
        assert path.is_file(), f"missing {path}"
        text = path.read_text(encoding="utf-8")
        for needle in ("low_volatility", "low-volatility", "LOW-001"):
            assert needle not in text, f"{path.name} names {needle!r}"
