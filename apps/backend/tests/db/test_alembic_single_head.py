"""The migration graph must have exactly ONE head.

The container starts with ``alembic upgrade head``. With two heads that command does not pick one —
it fails, and the backend never comes up. A divergence introduced by a merge would therefore not be
caught by any test, review or CI job; it would be caught by a dead container on a trading morning.

Ask Alembic, never a regex. When I hand-parsed the revision files I matched only a STRING
``down_revision`` and silently ignored merge revisions, which carry a TUPLE — so I invented two
phantom heads that did not exist and nearly wrote a merge revision to fix a problem I had made up.
The library resolves this correctly; nothing else should try.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[2]


def _scripts() -> ScriptDirectory:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_exactly_one_alembic_head():
    heads = _scripts().get_heads()
    assert len(heads) == 1, (
        f"{len(heads)} alembic heads: {heads}. `alembic upgrade head` cannot choose between them, "
        f"so the backend container will fail to start. Add a merge revision "
        f"(`alembic merge -m 'merge heads' {' '.join(heads)}`)."
    )


def test_every_revision_is_reachable_from_the_head():
    """A revision that no head descends from would never be applied — it is dead code that looks
    like a migration, which is worse than no migration at all."""
    scripts = _scripts()
    head = scripts.get_heads()[0]
    reachable = {rev.revision for rev in scripts.iterate_revisions(head, "base")}
    orphans = {rev.revision for rev in scripts.walk_revisions()} - reachable
    assert not orphans, f"revisions unreachable from head {head}: {sorted(orphans)}"


def test_every_revision_on_the_applied_path_defines_a_downgrade():
    """A migration you cannot roll back is a one-way door on a live book.

    This asserts the function EXISTS, not that it is non-empty: some historical revisions
    legitimately have nothing to undo. What it prevents is a new migration shipping with no
    downgrade at all.
    """
    scripts = _scripts()
    head = scripts.get_heads()[0]
    chain = list(scripts.iterate_revisions(head, "base"))
    assert chain, "no revisions found"

    without = [
        rev.revision
        for rev in chain
        if "def downgrade" not in Path(rev.path).read_text(encoding="utf-8")
    ]
    assert not without, f"revisions with no downgrade(): {without}"
