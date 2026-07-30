"""Tests for EVIDENCE-GAP acquisition freeze seal readiness (no evidence access)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "apps" / "backend" / "scripts" / "adr0043_evgap_acq_freeze_seal.py"


def _load():
    spec = importlib.util.spec_from_file_location("evgap_seal", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_walk_check_rejects_required_fill():
    mod = _load()
    errs = mod.walk_check({"x": "REQUIRED_FILL here"})
    assert errs


def test_build_manifest_readiness_pass_with_dummy_tip(tmp_path, monkeypatch):
    mod = _load()
    tip = "a" * 40
    body = mod.build_manifest_body(content_tip_commit=tip)
    errs = mod.walk_check(body)
    assert errs == [], errs
    assert body["eligibility_window"]["end_exclusive_utc"] == "2026-07-30T19:39:07Z"
    assert body["account_3_identity"]["workbench_account_id"] == 3
    assert (
        body["hold_and_blocks"]["acquisition_start"]
        == "HOLD_UNTIL_SEPARATE_START_DECISION"
    )
    assert "O3-CAND-20260730T022316Z" in body["archive_identity_rules"]["forbidden_archive_ids"]


def test_cli_readiness_only(capsys):
    mod = _load()
    tip = "b" * 40
    rc = mod.main(["--content-tip-commit", tip, "--readiness-only"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "READINESS PASS" in out
