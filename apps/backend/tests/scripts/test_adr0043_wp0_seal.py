"""Unit tests for ADR-0043 WP0 evidence seal helper (offline)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.adr0043_wp0_seal import build_seal, verify_seal


def test_build_and_verify_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "ok.txt").write_text("hello-wp0\n", encoding="utf-8")
    (root / "user7_password.txt").write_text("secret\n", encoding="utf-8")
    (root / "live.sqlite").write_bytes(b"not-a-real-db")

    out = tmp_path / "seal"
    record = build_seal(
        roots=[root],
        out_dir=out,
        host_id="test-host",
        operator="tester",
        include_db=False,
    )
    assert record["controlling_design_id"] == "ADR0043-PH0-CTRL-001 v1.1"
    assert record["manifest_entries"] == 1
    reasons = {e["reason"] for e in record["exclusions"]}
    assert "credential_or_secret_basename" in reasons
    assert "mutable_or_bulk_data_excluded_by_default" in reasons

    assert verify_seal(out) == 0

    # Tamper → fail closed
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    path = next(iter(manifest))
    Path(path).write_text("tampered\n", encoding="utf-8")
    assert verify_seal(out) == 1
