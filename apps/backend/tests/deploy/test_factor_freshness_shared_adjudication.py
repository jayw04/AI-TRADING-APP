"""The watchdog and the refresh verifier must not be able to disagree.

Before 2026-08-11 they could, and did: from the same evidence artifact, the same store
and the same universe, the watchdog published ``data_freshness=PASS`` at coverage
1.0000 while the refresh aborted the swap at 0.9784. The watchdog trusted the
``expected_classification`` written in the file; the verifier derived it and refused
what it could not corroborate. They also disagreed on the denominator.

They now consume one implementation, ``apps/backend/scripts/factor_adjudication.py``.
Because the watchdog runs against whatever backend image happens to be deployed — which
is built on its own cadence and routinely predates the host tree — it may not *import*
that module. It pipes the file's source into the container instead. These tests pin that
arrangement, because a host-tree coupling that is not asserted is a coupling that will be
silently broken by the next person to tidy the shell.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
WATCHDOG = REPO_ROOT / "deploy" / "aws" / "factor-freshness.sh"
HELPER = REPO_ROOT / "apps" / "backend" / "scripts" / "factor_adjudication.py"


def _code_lines() -> list[str]:
    """Watchdog lines that are not shell comments — prose may name anything."""
    return [
        ln
        for ln in WATCHDOG.read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith("#")
    ]


# ------------------------------------------------------- property 1: no image import


def test_watchdog_does_not_invoke_the_baked_in_refresh_module():
    """Unchanged from before: ``scripts/factor_refresh.py`` is baked into the image and
    the deployed image predates it. This watchdog must never become the reason that file
    gets deployed, so it may name the module in a comment but never invoke it."""
    assert not [ln for ln in _code_lines() if "factor_refresh.py" in ln]


def test_watchdog_does_not_import_the_helper_from_the_image():
    """The same reasoning applies to the shared helper — it is equally baked in and
    equally predated. The source is piped in; there is deliberately no import fallback."""
    code = _code_lines()
    assert not [ln for ln in code if re.search(r"^\s*(import|from)\s+factor_adjudication", ln)]
    # ...and nothing may put the host scripts directory on the container's sys.path as a
    # back door to the same coupling.
    assert not [ln for ln in code if "sys.path" in ln and "scripts" in ln]


def test_the_watchdog_does_not_mutate_the_stack_as_a_side_effect():
    code = _code_lines()
    assert not [ln for ln in code if "docker compose" in ln or "docker-compose" in ln]


# --------------------------------------------------- property 2: sources the host helper


def test_watchdog_resolves_the_helper_from_its_own_checkout():
    text = WATCHDOG.read_text(encoding="utf-8")
    assert "BASH_SOURCE" in text, "the helper path must be relative to the watchdog itself"
    assert "apps/backend/scripts/factor_adjudication.py" in text
    assert HELPER.exists(), "the resolved default path must actually exist in the tree"


def test_watchdog_pipes_the_helper_source_ahead_of_its_driver():
    """The composition itself: helper source first, driver second, one stdin."""
    text = WATCHDOG.read_text(encoding="utf-8")
    assert 'cat <<< "$ADJUDICATION_SRC"' in text
    piped = text.index('cat <<< "$ADJUDICATION_SRC"')
    driver = text.index("import datetime, json, os, zoneinfo")
    assert piped < driver, "the helper must be piped BEFORE the driver that uses it"


def test_the_watchdog_no_longer_carries_its_own_adjudication_logic():
    """The duplicated reading is gone, not merely supplemented. If any of this comes back
    the two components can disagree again."""
    text = WATCHDOG.read_text(encoding="utf-8")
    # It no longer reads the CLAIM written in the evidence file — that is what let it
    # reach a verdict the verifier refused.
    assert "expected_classification" not in text
    # Nor does it build its own exemption set or raise the ceiling problem itself; the
    # shared module decides, and the driver only relays `result["problems"]`.
    assert "exempt = set()" not in text
    assert "DATA_EXEMPTION_IMPLAUSIBLE" not in text
    assert 'for problem in result["problems"]:' in text


def test_the_driver_calls_the_shared_entry_points():
    """Every figure and every label in the watchdog's report comes from the shared module.

    The DIAGNOSTIC entry points were added on 2026-08-27 and belong on this list for the
    same reason as the rest. ``UNEXPLAINED: ['WBS']`` aborted three consecutive production
    refreshes while the watchdog reported ``unexplained_count: 0``, and both statements were
    true — they adjudicate different stores. What an operator needed was WHY the name was
    unexplained and HOW LONG the artifact remains usable, and if the two components computed
    those separately they would eventually answer differently, which is the entire failure
    mode ADR 0051 exists to prevent.
    """
    text = WATCHDOG.read_text(encoding="utf-8")
    for symbol in (
        "load_evidence_records(",
        "operational_facts(",
        "adjudicate(",
        "gating_coverage(",
        "evidence_expiry(",
        "diagnose_unexplained(",
        "EVIDENCE_DIAGNOSIS_DETAIL",
    ):
        assert symbol in text, f"driver must call the shared {symbol}"


def test_the_driver_does_not_reimplement_the_diagnostics_it_relays():
    """The diagnosis LABELS and the expiry arithmetic must not be restated in the shell.

    A hand-rolled "if the record is missing say ABSENT" in the driver would be a second
    vocabulary for a state the shared module already names, and it would drift the first time
    the rules changed on one side only.
    """
    code = _code_lines()
    for banned in ("EVIDENCE_ABSENT =", "EVIDENCE_EXPIRED =", "max_evidence_age_days ="):
        assert not [ln for ln in code if banned in ln], f"driver must not define {banned}"
    # ...and the expiry threshold must be a knob, not arithmetic reimplemented in python.
    assert not [ln for ln in code if "timedelta(days=30)" in ln]


# ------------------------------------------------------- property 3: missing = fail closed


def test_a_missing_helper_fails_closed():
    text = WATCHDOG.read_text(encoding="utf-8")
    assert "DATA_ADJUDICATION_HELPER_UNAVAILABLE" in text
    # The problem must land in the DATA ledger, which is what makes data_freshness FAIL.
    assert re.search(r"P_DATA\+=\(\"DATA_ADJUDICATION_HELPER_UNAVAILABLE", text)
    # ...and it must be appended AFTER the ledgers are initialised, or it is erased.
    assert text.index("P_PRODUCER=(); P_SEALED=(); P_DATA=()") < text.index(
        'P_DATA+=("DATA_ADJUDICATION_HELPER_UNAVAILABLE'
    )


def test_there_is_no_fallback_path_when_the_helper_is_absent():
    """Fail closed means no PASS, not a degraded assessment."""
    code = "\n".join(_code_lines())
    assert "ADJUDICATION_AVAILABLE" in code
    # No branch may set the availability flag true without the source being non-empty.
    assert re.search(r'if \[ -n "\$ADJUDICATION_SRC" \]; then', code)


# ---------------------------------------------- property 4: reported hash == executed source


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="sha256sum/bash semantics are asserted on POSIX/CI"
)
def test_the_recorded_hash_is_of_the_source_that_is_actually_piped():
    """The artifact's ``adjudication.sha256`` must identify the bytes that ran.

    The watchdog reads the file ONCE into ``$ADJUDICATION_SRC``, then hashes and pipes
    that same variable through the same ``<<<`` construct. This reproduces both halves and
    asserts they agree with a plain hash of the file, so the recorded value can never name
    an implementation that did not execute.
    """
    script = (
        "set -eu\n"
        'SRC="$(cat "$1")"\n'
        'HASHED="$(sha256sum <<< "$SRC" | cut -d" " -f1)"\n'
        'PIPED="$(cat <<< "$SRC" | sha256sum | cut -d" " -f1)"\n'
        'echo "$HASHED $PIPED"\n'
    )
    out = subprocess.run(
        ["bash", "-c", script, "_", str(HELPER)],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    ).stdout.split()
    hashed, piped = out[0], out[1]
    assert hashed == piped, "the bytes hashed are not the bytes piped"
    assert hashed == hashlib.sha256(HELPER.read_bytes()).hexdigest(), (
        "the recorded hash must equal a plain sha256 of the helper file"
    )


# ------------------------------------- property 5: only ONE figure is ever thresholded


def test_no_threshold_is_ever_applied_to_raw_coverage():
    """`raw_coverage` is observability. Thresholding it is the 2026-08-11 defect exactly:
    nine names that can never be fresh in this provider were measured against a bar they
    could never clear, and the store froze. Only `gating_coverage` may meet a threshold."""
    watchdog = WATCHDOG.read_text(encoding="utf-8")
    for line in watchdog.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "min_cov" not in stripped:
            continue
        if "<" in stripped or ">" in stripped:
            assert "coverage <" in stripped, f"a threshold on something else: {stripped}"
            assert "raw" not in stripped, f"raw coverage must never be thresholded: {stripped}"

    verifier = (REPO_ROOT / "apps" / "backend" / "scripts" / "factor_refresh.py").read_text(
        encoding="utf-8"
    )
    # Only real comparisons — an f-string that merely *reports* the two values is not a
    # threshold, and matching it would make this test fail on its own error message.
    comparisons = [
        ln.strip()
        for ln in verifier.splitlines()
        if ln.strip().startswith("if ") and "min_coverage" in ln and "<" in ln
    ]
    assert comparisons, "expected the verifier to threshold something"
    for line in comparisons:
        assert "coverage < min_coverage" in line, line
    # ...and the value bound to `coverage` immediately above it comes from the shared rule.
    assert "coverage = gating_coverage(result)" in verifier


def test_the_artifact_reports_both_figures_and_the_populations():
    """An operator seeing PASS must be able to tell an adjudicated pool from a pool that
    is quietly missing data. The verdict alone cannot carry that."""
    text = WATCHDOG.read_text(encoding="utf-8")
    assert '"coverage": {' in text
    for field in (
        '"gating_coverage"',
        '"raw_coverage"',
        '"attributed_count"',
        '"assessable_count"',
        '"unexplained_count"',
    ):
        assert field in text, f"artifact must expose {field}"
    # The definition travels with the number, so it cannot be misread later.
    assert "assessable = universe - validly attributed" in text
    assert "observability only; no gate may threshold it" in text


def test_the_published_artifact_carries_the_helper_provenance():
    text = WATCHDOG.read_text(encoding="utf-8")
    assert '"adjudication": {' in text
    assert '"sha256": opt("ADJUDICATION_SHA256")' in text
    assert '"image_import": False' in text
    # The hash must be exported into the publishing block, or it is always null.
    assert 'ADJUDICATION_SHA256="$ADJUDICATION_SHA256"' in text
