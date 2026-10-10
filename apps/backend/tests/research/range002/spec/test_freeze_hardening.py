"""L1 hardening of the freeze tool: future sign-off date, exclusive create, symlink targets."""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from ._fixtures import complete_payload, make_symlink
from .test_freeze import cli


def _draft(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "draft.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_future_signoff_date_refused(tmp_path, capsys):
    payload = complete_payload()
    payload["signoff"]["date"] = (date.today() + timedelta(days=1)).isoformat()
    out = tmp_path / "frozen.json"
    assert cli.main([str(_draft(tmp_path, payload)), "--out", str(out)]) == 2
    assert not out.exists()
    assert "future" in capsys.readouterr().err


def test_today_signoff_date_accepted(tmp_path):
    payload = complete_payload()
    payload["signoff"]["date"] = date.today().isoformat()
    out = tmp_path / "frozen.json"
    assert cli.main([str(_draft(tmp_path, payload)), "--out", str(out)]) == 0


def test_symlink_target_refused_and_nothing_written_through_it(tmp_path):
    victim = tmp_path / "victim.json"
    victim.write_text("keep", encoding="utf-8")
    link = tmp_path / "frozen.json"
    make_symlink(link, victim)
    assert cli.main([str(_draft(tmp_path, complete_payload())), "--out", str(link)]) == 2
    assert victim.read_text(encoding="utf-8") == "keep"


def test_dangling_symlink_target_refused(tmp_path):
    link = tmp_path / "frozen.json"
    make_symlink(link, tmp_path / "nowhere.json")
    assert cli.main([str(_draft(tmp_path, complete_payload())), "--out", str(link)]) == 2
    assert not (tmp_path / "nowhere.json").exists()


def test_symlink_branch_without_real_symlinks(tmp_path, monkeypatch):
    out = tmp_path / "frozen.json"
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == out)
    assert cli.main([str(_draft(tmp_path, complete_payload())), "--out", str(out)]) == 2
    assert not out.exists()


def test_write_is_exclusive_create_even_if_file_appears_after_the_exists_check(tmp_path):
    out = tmp_path / "frozen.json"
    out.write_text("raced", encoding="utf-8")
    with pytest.raises(FileExistsError):
        cli._write_new(out, "x")  # the 'x' open mode is the last line of defence
    assert out.read_text(encoding="utf-8") == "raced"


def test_frozen_file_is_written_with_lf_only(tmp_path):
    out = tmp_path / "frozen.json"
    assert cli.main([str(_draft(tmp_path, complete_payload())), "--out", str(out)]) == 0
    assert b"\r" not in out.read_bytes()


def test_canary_symlinks_work_on_linux(tmp_path):
    """On Linux symlink creation must work, so the symlink tests above can never be skipped there
    (a green Linux job proves they ran). Elsewhere this asserts nothing."""
    if not sys.platform.startswith("linux"):
        return
    target = tmp_path / "t"
    target.write_text("x", encoding="utf-8")
    os.symlink(target, tmp_path / "l")
    assert (tmp_path / "l").is_symlink() and (tmp_path / "l").read_text(encoding="utf-8") == "x"
