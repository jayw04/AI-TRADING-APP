"""The publisher/consumer contract for ``_factor_readiness.json``.

Two programs, in two languages, on two sides of a container boundary, agreeing on one
file. ``deploy/aws/factor-freshness.sh`` writes it on the host; ``app.strategies.
factor_readiness`` reads it inside the backend and BLOCKS factor-consuming dispatch on
what it finds. Neither can be tested into correctness alone — a writer that renames a
field still passes its own tests, and so does the reader.

⚠ WHY THIS FILE IS LOAD-BEARING. The consumer fails CLOSED, so schema drift does not
degrade gracefully: a missing ``evaluated_at_utc``, a lowercase ``pass``, or a renamed
``overall_readiness`` HALTS strategies 7 and 8 rather than warning about anything. The
drift and the outage are the same event. So the actual writer is executed here — its
python extracted from the shell script it lives in — and its actual output is handed to
the actual reader.

Nothing here touches the box, the store, systemd, AWS, or any deployment path.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.strategies.factor_readiness import evaluate_factor_readiness

REPO_ROOT = Path(__file__).resolve().parents[4]
WATCHDOG = REPO_ROOT / "deploy" / "aws" / "factor-freshness.sh"

#: The one basename both sides derive independently. Neither takes it from configuration,
#: so this constant is the only place they can be compared.
ARTIFACT_BASENAME = "_factor_readiness.json"


def _publisher_source() -> str:
    """The publisher's python, lifted out of the shell heredoc that hosts it.

    Executing the real block rather than a copy is the point: a copy would drift, and a
    drifted copy of a schema-drift test proves nothing.
    """
    text = WATCHDOG.read_text(encoding="utf-8")
    blocks = re.findall(r"<<'PY'[^\n]*\n(.*?)\nPY\n", text, re.S)
    matching = [b for b in blocks if '"overall_readiness"' in b and "os.replace" in b]
    assert len(matching) == 1, f"expected exactly one publisher block, found {len(matching)}"
    return matching[0]


def _publish(tmp: Path, monkeypatch, **over) -> Path:
    """Run the real writer with a controlled environment; return the artifact path."""
    dest = over.pop("dest", tmp / ARTIFACT_BASENAME)
    env = {
        "READINESS_PATH": str(dest),
        "EVALUATED_EPOCH": str(int(datetime.now(UTC).timestamp())),
        "CLOCK_SOURCE": "wall",
        "OVERALL": "PASS",
        "V_PRODUCER": "PASS",
        "V_SEALED": "PASS",
        "V_DATA": "PASS",
        "V_CAUSE": "N/A",
        "SEALED_AS_OF": "2026-08-07",
        "EXPECTED_DATE": "2026-08-07",
        "TIMER_UNIT": "workbench-factor-refresh.timer",
        "SERVICE_UNIT": "workbench-factor-refresh.service",
        "SCHEDULE_TZ": "America/New_York",
        "PROBLEMS_BLOB": "",
    }
    env.update({k: str(v) for k, v in over.items()})
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    exec(
        compile(_publisher_source(), "factor-freshness.sh:<publisher>", "exec"),
        {"__name__": "__main__"},
    )  # noqa: S102
    return dest


# ── fixtures the consumer needs in order to reach the artifact check ─────────────────
# The artifact is the LAST leg of the gate, so the store and seal have to be current or
# the evaluation short-circuits before the contract is exercised at all.


def _current_store(tmp: Path) -> Path:
    duckdb = pytest.importorskip("duckdb")
    today = datetime.now(UTC).date()
    p = tmp / "factor_data.duckdb"
    con = duckdb.connect(str(p))
    con.execute("CREATE TABLE sep (ticker VARCHAR, date DATE, close DOUBLE, volume DOUBLE)")
    con.execute("INSERT INTO sep VALUES ('AAA', ?, 1.0, 1.0)", [today])
    con.execute("CREATE TABLE tickers (ticker VARCHAR, lastpricedate DATE)")
    con.execute("INSERT INTO tickers VALUES ('AAA', ?)", [today])
    con.close()
    return p


def _current_seal(tmp: Path) -> Path:
    p = tmp / "_factor_refresh_universe_sealed.json"
    p.write_text(
        json.dumps({"as_of": datetime.now(UTC).date().isoformat(), "counts": {"total": 510}}),
        encoding="utf-8",
    )
    return p


def _consume(tmp: Path, artifact: Path):
    return evaluate_factor_readiness(
        store_path=_current_store(tmp),
        sealed_path=_current_seal(tmp),
        readiness_path=artifact,
    )


# ═══════════════════════════════════════════════════════════════════════════════════
# THE BINDING: real writer -> real reader
# ═══════════════════════════════════════════════════════════════════════════════════


def test_a_published_pass_is_accepted_by_the_gate(tmp_path, monkeypatch):
    """The green path end to end. If this breaks, Monday's rebalance does not run."""
    artifact = _publish(tmp_path, monkeypatch, OVERALL="PASS")
    verdict = _consume(tmp_path, artifact)
    assert verdict.ok, verdict.reason
    assert verdict.checks["producer_liveness_verified"] is True
    assert verdict.checks["overall_readiness"] == "PASS"


def test_a_published_fail_blocks_the_gate(tmp_path, monkeypatch):
    """The 2026-08-03 window, now closed: producer dead, store still clean, dispatch
    refused because the watchdog said so in writing."""
    artifact = _publish(
        tmp_path,
        monkeypatch,
        OVERALL="FAIL",
        V_PRODUCER="FAIL",
        PROBLEMS_BLOB="producer_liveness\tTIMER_DISABLED: the timer is not armed\n",
    )
    verdict = _consume(tmp_path, artifact)
    assert not verdict.ok
    assert "producer readiness verdict is FAIL" in verdict.reason


def test_the_two_contract_fields_are_present_and_correctly_typed(tmp_path, monkeypatch):
    """Named explicitly so a rename fails HERE, with this comment attached, rather than
    silently at 10:24 ET on a Monday."""
    doc = json.loads(_publish(tmp_path, monkeypatch).read_text(encoding="utf-8"))
    assert doc["overall_readiness"] == "PASS", "the reader compares this, uppercased, to 'PASS'"
    # Parsed with the reader's exact expression, not an equivalent one.
    parsed = datetime.fromisoformat(str(doc["evaluated_at_utc"]).replace("Z", "+00:00"))
    assert parsed.tzinfo is not None, "a naive stamp would be read as UTC by luck, not design"
    assert abs((datetime.now(UTC) - parsed).total_seconds()) < 120


def test_the_verdict_is_uppercased_by_the_writer(tmp_path, monkeypatch):
    """The reader uppercases before comparing, so this is belt and braces — but the
    artifact is also read by humans during an incident, and 'pass' vs 'PASS' is exactly
    the ambiguity that costs twenty minutes at 07:00."""
    doc = json.loads(_publish(tmp_path, monkeypatch, OVERALL="pass").read_text(encoding="utf-8"))
    assert doc["overall_readiness"] == "PASS"


def test_age_tolerance_binds_to_the_published_timestamp_format(tmp_path, monkeypatch):
    """The 26h window is measured against whatever the writer stamps. A format the reader
    parses differently (local time, no offset, milliseconds) would shift the whole
    tolerance — silently, in one direction or the other."""
    old = int((datetime.now(UTC) - timedelta(hours=27)).timestamp())
    verdict = _consume(tmp_path, _publish(tmp_path, monkeypatch, EVALUATED_EPOCH=old))
    assert not verdict.ok
    assert "stale relative to this dispatch" in verdict.reason
    assert 26.5 < verdict.checks["readiness_age_hours"] < 27.5


def test_problem_prose_round_trips_without_breaking_the_document(tmp_path, monkeypatch):
    """The details are operator prose full of quotes, backslashes and '=' signs. Hand-
    rolled JSON quoting is how a writer starts emitting documents its reader classifies
    as unreadable — which, fail-closed, is a trading halt."""
    nasty = 'TIMER_DISABLED: unit "workbench-factor-refresh.timer" is C:\\dead\\ — UnitFileState=disabled, 100% off'
    artifact = _publish(
        tmp_path,
        monkeypatch,
        OVERALL="FAIL",
        PROBLEMS_BLOB=f"producer_liveness\t{nasty}\ndata_freshness\tDATA_SEP_EMPTY: nothing\n",
    )
    doc = json.loads(artifact.read_text(encoding="utf-8"))
    assert doc["problem_count"] == 2
    assert doc["problems"][0] == {"component": "producer_liveness", "detail": nasty}
    assert doc["problems"][1]["component"] == "data_freshness"
    # And the reader still gets a usable verdict out of it.
    assert not _consume(tmp_path, artifact).ok


def test_no_problems_means_an_empty_list_not_a_missing_key(tmp_path, monkeypatch):
    doc = json.loads(_publish(tmp_path, monkeypatch).read_text(encoding="utf-8"))
    assert doc["problems"] == []
    assert doc["problem_count"] == 0


# ═══════════════════════════════════════════════════════════════════════════════════
# ATOMICITY — a reader that catches a prefix sees "unreadable", which is a halt
# ═══════════════════════════════════════════════════════════════════════════════════


def test_the_writer_never_opens_the_destination_for_writing(tmp_path):
    """Source-level, because the interleaving it prevents cannot be scheduled reliably in
    a test. temp-in-the-same-directory + rename is the only construction that gives a
    concurrent reader an all-or-nothing view; open-truncate-write would hand it a prefix
    on every single publish."""
    src = _publisher_source()
    assert "tempfile.mkstemp(dir=str(dest.parent)" in src, "the temp file must be a rename away"
    assert "os.replace(tmp, dest)" in src, "the swap must be a rename, not a copy"
    assert "os.fsync" in src, "content must reach disk before the name flips to it"
    assert not re.search(r"open\(\s*dest", src), "the destination is never opened for writing"
    assert "dest.write_text" not in src


def test_the_writer_does_not_require_a_modern_host_interpreter():
    """This block runs under the HOST's python3, not the container's — the watchdog is
    host-side by design because producer liveness is a systemd fact. ``datetime.UTC`` is
    a 3.11 alias; on an older host it would raise ImportError on every run, and once the
    gate requires the artifact that is a trading halt caused by an import style. The rest
    of the script already needs 3.9 for zoneinfo, which the box demonstrably has."""
    # Comments stripped: the block explains this rule in prose, and prose naming the
    # forbidden spelling must not read as using it.
    code = "\n".join(
        ln for ln in _publisher_source().splitlines() if not ln.lstrip().startswith("#")
    )
    assert "from datetime import UTC" not in code
    assert not re.search(r"\bdatetime\.UTC\b", code)
    assert "timezone.utc" in code


def test_publishing_leaves_no_temp_residue(tmp_path, monkeypatch):
    """A stale ``.tmp`` beside the artifact is not merely untidy — it is the visible
    signature of a writer that failed halfway, and it must not accumulate on the box."""
    _publish(tmp_path, monkeypatch)
    assert [p.name for p in tmp_path.iterdir()] == [ARTIFACT_BASENAME]


def test_republishing_replaces_the_document_wholly(tmp_path, monkeypatch):
    first = _publish(tmp_path, monkeypatch, OVERALL="FAIL", V_PRODUCER="FAIL")
    assert json.loads(first.read_text(encoding="utf-8"))["overall_readiness"] == "FAIL"
    second = _publish(tmp_path, monkeypatch, OVERALL="PASS")
    doc = json.loads(second.read_text(encoding="utf-8"))
    assert doc["overall_readiness"] == "PASS"
    assert doc["components"]["producer_liveness"] == "PASS", "stale fields must not survive"
    assert [p.name for p in tmp_path.iterdir()] == [ARTIFACT_BASENAME]


def test_a_failed_publish_leaves_the_previous_verdict_intact(tmp_path, monkeypatch):
    """Failing to publish must not also destroy yesterday's evidence. The watchdog reports
    the failure and exits 2; the file on disk is either the old document or the new one."""
    good = _publish(tmp_path, monkeypatch)
    before = good.read_bytes()
    with pytest.raises(OSError):
        _publish(tmp_path, monkeypatch, dest=tmp_path / "not_a_dir" / ARTIFACT_BASENAME)
    assert good.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == [ARTIFACT_BASENAME]


def test_the_writer_does_not_create_the_data_directory(tmp_path, monkeypatch):
    """A missing parent means the data volume is not mounted. Creating it would publish a
    verdict into a container-local path nothing reads, and the gate would then block on
    an absent artifact while the watchdog reported a clean publish."""
    with pytest.raises(OSError):
        _publish(tmp_path, monkeypatch, dest=tmp_path / "unmounted" / ARTIFACT_BASENAME)
    assert not (tmp_path / "unmounted").exists()


# ═══════════════════════════════════════════════════════════════════════════════════
# PATH AGREEMENT — the two sides derive the same filename independently
# ═══════════════════════════════════════════════════════════════════════════════════


def test_both_sides_use_the_same_basename():
    """Neither side reads this from configuration, deliberately: a config change that
    pointed them at different files would unarm the veto without failing anything."""
    from app.strategies import engine

    engine_src = Path(engine.__file__).read_text(encoding="utf-8")
    assert f'"{ARTIFACT_BASENAME}"' in engine_src
    assert f'READINESS_BASENAME="{ARTIFACT_BASENAME}"' in WATCHDOG.read_text(encoding="utf-8")


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="bash harness runs on POSIX/CI, not Windows"
)
def test_the_whole_watchdog_publishes_a_consumable_artifact(tmp_path, monkeypatch):
    """The end-to-end proof: run the actual shell script, with systemd/docker/aws faked,
    and feed whatever lands on disk to the actual gate. Everything above tests the writer
    in isolation; this tests that the script around it invokes the writer at all."""
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "systemctl").write_text(
        '#!/usr/bin/env bash\ncase "${1:-}" in show-timezone) echo America/New_York;;'
        " is-failed) echo active;; esac\nexit 0\n",
        encoding="utf-8",
    )
    (fake / "docker").write_text("#!/usr/bin/env bash\ncat >/dev/null\nexit 1\n", encoding="utf-8")
    (fake / "aws").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    for f in fake.iterdir():
        f.chmod(0o755)

    data = tmp_path / "data"
    data.mkdir()
    result = subprocess.run(
        ["bash", str(WATCHDOG)],
        capture_output=True,
        text=True,
        timeout=300,
        env={
            **os.environ,
            "SYSTEMCTL_BIN": str(fake / "systemctl"),
            "WATCHDOG_DOCKER": str(fake / "docker"),
            "AWS_BIN": str(fake / "aws"),
            "WORKBENCH_DATA_DIR": str(data),
            "PYTHON_BIN": sys.executable,
        },
    )
    # Everything is broken in this fixture, so the verdict is FAIL — and a FAIL verdict is
    # exactly what must still be WRITTEN. An unpublished FAIL is indistinguishable from a
    # watchdog that never ran.
    assert result.returncode == 2, result.stdout
    assert "READINESS_ARTIFACT=PUBLISHED" in result.stdout, result.stdout
    artifact = data / ARTIFACT_BASENAME
    assert artifact.exists(), f"the watchdog published nothing:\n{result.stdout}"
    doc = json.loads(artifact.read_text(encoding="utf-8"))
    assert doc["overall_readiness"] == "FAIL"
    assert doc["problem_count"] > 0
    verdict = _consume(tmp_path, artifact)
    assert not verdict.ok
    assert verdict.checks["producer_liveness_verified"] is True
