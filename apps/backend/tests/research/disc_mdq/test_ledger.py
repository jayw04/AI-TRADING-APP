"""DISC-MDQ-001 discovery ledger — the twelve-item acceptance gate.

Plan v0.13 section 4.10.7 is explicit that "the ledger was built" is not the
acceptance criterion. The tests are therefore organised by acceptance item, and
the load-bearing ones are items 10-12: that the reader cannot be constructed
without an initialised ledger, that the governed artifacts verify before any
partition is opened, and that initialisation failure closes the gate instead of
logging a warning.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.research.disc_mdq.ledger import (
    LEDGER_PUBLIC_API,
    CodeIdentity,
    DiscoveryLedger,
    LedgerEvent,
    LedgerInitError,
    LedgerIntegrityError,
    LedgerRecordError,
    conditions_examined,
)
from app.research.disc_mdq.policy import (
    ArtifactAttestation,
    MdqExplorationPolicy,
    PolicyError,
    ReviewWindow,
    canonical_symbol_sha256,
    verify_governed_artifacts,
)
from app.research.disc_mdq.spec import (
    HOLDOUT_SYMBOLS_SHA256,
    LEDGER_GENESIS_HASH,
    LEDGER_VERSION,
    PROGRAM_ID,
    UNIVERSE_SYMBOLS_SHA256,
    ReadPurpose,
)

SESSION = date(2026, 8, 20)
FIXED_NOW = datetime(2026, 8, 21, 14, 30, 0, tzinfo=UTC)

PARTITION = {
    "feed": "sip",
    "session_date": "2026-08-20",
    "manifest_sha256": "a" * 64,
    "collector_version": "mdq-collector/0.1.0",
    "files": [{"path": "quotes/samples.jsonl", "sha256": "b" * 64}],
    "integrity_verified": True,
}


def _lf_sha256(path: Path) -> str:
    """The governed hashes are over LF-normalised bytes — see the CRLF test.

    Every file this helper is pointed at is written by ``json.dumps`` on a
    single line, so there is nothing to normalise; the name records which hash
    is being reproduced.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def governed_config(name: str) -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "config" / name
        if candidate.exists():
            return candidate
    raise AssertionError(f"could not locate config/{name} from {here}")


@pytest.fixture
def attestation() -> ArtifactAttestation:
    return verify_governed_artifacts(
        universe_symbols_path=governed_config("mdq_phase_a_universe_symbols.json"),
        holdout_path=governed_config("mdq_phase_a_holdout.json"),
    )


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "ledger" / "discovery.jsonl"


@pytest.fixture
def ledger(ledger_path: Path, attestation: ArtifactAttestation) -> DiscoveryLedger:
    return DiscoveryLedger.open(
        ledger_path, attestation=attestation, code_identity=CodeIdentity.current("pytest")
    )


@pytest.fixture
def scope(attestation: ArtifactAttestation):
    """A scope over the real governed artifacts, deliberately including two
    held-out names so every record carries real denials (item 9)."""
    policy = MdqExplorationPolicy.from_config(
        universe_symbols_path=governed_config("mdq_phase_a_universe_symbols.json"),
        holdout_path=governed_config("mdq_phase_a_holdout.json"),
    )
    return policy.authorize(["AAPL", "NVDA", "TSLA", "XOM"], [SESSION], ReadPurpose.EXPLORATION)


def record_a_condition(ledger: DiscoveryLedger, scope, **overrides):
    kwargs = {
        "condition_id": "spread_median_bps@rth",
        "family": "MOM-CORE",
        "definition": {
            "feature": "spread_median_bps",
            "window": "09:30-16:00 ET",
            "source": "sip quote snapshots",
        },
        "scope": scope,
        "partitions": [PARTITION],
        "disposition": "examined",
        "result": {"median_bps": 1.7, "n": 390},
    }
    kwargs.update(overrides)
    return ledger.record_condition(**kwargs)


# === items 1-2: structure ===================================================


def test_the_ledger_is_append_only_and_has_no_mutation_path() -> None:
    """Item 2 — pinned as a test so a delete path fails CI, not review.

    ``LEDGER_PUBLIC_API`` is the whole public surface. Adding ``delete``,
    ``prune``, ``compact`` or ``rewrite`` breaks this assertion, which is the
    point: the prohibition has to survive a future session that has a good
    reason for wanting one.
    """
    public = {name for name in dir(DiscoveryLedger) if not name.startswith("_")}
    assert public == LEDGER_PUBLIC_API

    forbidden = ("delete", "remove", "prune", "compact", "rewrite", "truncate", "update", "clear")
    assert not [name for name in public if any(f in name.lower() for f in forbidden)]


def test_the_writer_opens_the_file_in_append_mode_only() -> None:
    """Item 1 — enforced by the kernel, not by convention.

    ``os.O_APPEND`` moves the file offset to the end before *every* write, so a
    caller that seeks cannot overwrite an earlier record. The check reads the
    source because that is where the guarantee lives; a behavioural test can
    only show that the current code path happens not to overwrite.
    """
    source = Path(DiscoveryLedger.__module__.replace(".", "/"))
    module_file = Path(__file__).resolve().parents[3] / f"{source}.py"
    text = module_file.read_text(encoding="utf-8")
    assert "os.O_APPEND" in text
    assert "os.O_TRUNC" not in text
    assert ".unlink(" not in text
    assert ".write_text(" not in text
    assert ".write_bytes(" not in text


def test_records_accumulate_and_are_chained(ledger: DiscoveryLedger, scope) -> None:
    first = ledger.records()[-1]
    assert first.event is LedgerEvent.LEDGER_OPENED
    assert first.prev_hash == LEDGER_GENESIS_HASH

    second = record_a_condition(ledger, scope)
    third = record_a_condition(ledger, scope, condition_id="spread_p95_bps@rth")

    records = ledger.verify()
    assert [r.seq for r in records] == [1, 2, 3]
    assert records[1].prev_hash == records[0].row_hash
    assert records[2].prev_hash == records[1].row_hash
    assert second.entry_ref != third.entry_ref
    assert second.entry_ref.startswith(f"{PROGRAM_ID}#2:")


def test_a_second_open_appends_rather_than_restarting(
    ledger_path: Path, attestation: ArtifactAttestation, scope
) -> None:
    first = DiscoveryLedger.open(ledger_path, attestation=attestation)
    record_a_condition(first, scope)

    second = DiscoveryLedger.open(ledger_path, attestation=attestation)
    assert second.count == 3  # opened, condition, opened
    records = second.verify()
    assert [r.event for r in records] == [
        LedgerEvent.LEDGER_OPENED,
        LedgerEvent.CONDITION_EXAMINED,
        LedgerEvent.LEDGER_OPENED,
    ]
    assert records[-1].payload["existing_records"] == 2


# === items 3-9: what one record must carry ==================================


def test_a_condition_record_carries_every_required_field(ledger: DiscoveryLedger, scope) -> None:
    record = record_a_condition(ledger, scope, now=FIXED_NOW)
    payload = record.payload

    # 3 timestamp
    assert record.recorded_at == "2026-08-21T14:30:00+00:00"
    # 4 authorized scope
    assert payload["scope"]["fingerprint"] == scope.fingerprint()
    assert payload["scope"]["authorized_pairs"] == [f"AAPL|{SESSION}", f"NVDA|{SESSION}"]
    assert payload["scope"]["purpose"] == "exploration"
    # 5 corpus / partition identity
    assert payload["partitions"][0]["manifest_sha256"] == "a" * 64
    # 6 code / version identity
    assert payload["code"]["ledger_version"] == LEDGER_VERSION
    assert payload["code"]["enriches_screen_version"] == "v0.3.0"
    # 7 condition / feature definition
    assert payload["condition"]["feature"] == "spread_median_bps"
    # 8 disposition / result
    assert payload["disposition"] == "examined"
    assert payload["result"]["n"] == 390
    # 9 denial information
    assert payload["scope"]["denials"]["counts"] == {"denied_holdout_symbol": 2}


def test_denials_are_recorded_in_full_not_as_a_count(ledger: DiscoveryLedger, scope) -> None:
    """Item 9, and the reason ``AuthorizedScope.denials`` keeps full detail.

    A count says two names were dropped. It does not say *which*, so it cannot
    afterwards show that the quarantine was honoured — which is the only thing
    the denial record is for.
    """
    detail = record_a_condition(ledger, scope).payload["scope"]["denials"]["detail"]
    assert detail == [
        f"TSLA|{SESSION}|denied_holdout_symbol",
        f"XOM|{SESSION}|denied_holdout_symbol",
    ]


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("condition_id", "  ", "condition_id"),
        ("family", "", "family"),
        ("definition", {}, "item 7"),
        ("disposition", "", "item 8"),
        ("partitions", [], "item 5"),
    ],
)
def test_an_incomplete_record_is_refused(
    ledger: DiscoveryLedger, scope, field: str, value: object, match: str
) -> None:
    """A half-filled entry is worse than none: a later pre-registration would
    cite a reference that does not say what was examined or how it came out."""
    with pytest.raises(LedgerRecordError, match=match):
        record_a_condition(ledger, scope, **{field: value})
    assert ledger.count == 1, "a refused record must not be written"


def test_a_partition_without_an_identity_is_refused(ledger: DiscoveryLedger, scope) -> None:
    with pytest.raises(LedgerRecordError, match="manifest_sha256"):
        record_a_condition(
            ledger, scope, partitions=[{"feed": "sip", "session_date": "2026-08-20"}]
        )


def test_inconclusive_and_abandoned_are_dispositions(ledger: DiscoveryLedger, scope) -> None:
    """The multiple-comparisons denominator only works if the conditions that
    went nowhere are recorded too. Nothing about the ledger prefers a result."""
    record_a_condition(ledger, scope, condition_id="c1", disposition="inconclusive")
    record_a_condition(ledger, scope, condition_id="c2", disposition="abandoned")
    record_a_condition(ledger, scope, condition_id="c3", family="GAP", disposition="examined")

    records = ledger.verify()
    assert len(conditions_examined(records)) == 3
    assert len(conditions_examined(records, family="MOM-CORE")) == 2
    assert len(conditions_examined(records, family="GAP")) == 1


# === items 10-12: enforcement ===============================================


def test_a_ledger_cannot_be_constructed_except_through_open(
    ledger_path: Path, attestation: ArtifactAttestation
) -> None:
    """Item 10's foundation: if ``__init__`` were usable, a caller could hold a
    ledger object that never verified anything, and the reader's type check
    would wave it straight through."""
    with pytest.raises(LedgerInitError, match="DiscoveryLedger.open"):
        DiscoveryLedger(
            object(),
            path=ledger_path,
            attestation=attestation,
            code_identity=CodeIdentity.current(),
            head_hash=LEDGER_GENESIS_HASH,
            count=0,
        )


def test_open_refuses_an_unverified_attestation(ledger_path: Path) -> None:
    """Item 11. A hand-built attestation is exactly what a hurried session
    reaches for when the artifacts are inconvenient to load."""
    hand_built = ArtifactAttestation(
        universe_path="nowhere",
        universe_sha256=UNIVERSE_SYMBOLS_SHA256,
        universe_symbol_count=50,
        holdout_path="nowhere",
        holdout_artifact_sha256="c" * 64,
        holdout_symbols_sha256=HOLDOUT_SYMBOLS_SHA256,
        holdout_symbols=("AMZN",),
        period_holdout_provenance="made up",
        period_holdout_start=date(2026, 10, 6),
        period_holdout_end_exclusive=date(2026, 10, 18),
    )
    assert hand_built.verified is False
    with pytest.raises(LedgerInitError, match="VERIFIED ArtifactAttestation"):
        DiscoveryLedger.open(ledger_path, attestation=hand_built)
    assert not ledger_path.exists(), "a refused init must not create the ledger"


def test_open_refuses_an_attestation_that_claims_the_wrong_pins(ledger_path: Path) -> None:
    """``verified=True`` is not a password. The pins are re-checked at open."""
    forged = ArtifactAttestation(
        universe_path="nowhere",
        universe_sha256="d" * 64,
        universe_symbol_count=50,
        holdout_path="nowhere",
        holdout_artifact_sha256="c" * 64,
        holdout_symbols_sha256=HOLDOUT_SYMBOLS_SHA256,
        holdout_symbols=("AMZN",),
        period_holdout_provenance="made up",
        period_holdout_start=date(2026, 10, 6),
        period_holdout_end_exclusive=date(2026, 10, 18),
        verified=True,
    )
    with pytest.raises(LedgerInitError, match="pinned"):
        DiscoveryLedger.open(ledger_path, attestation=forged)


def test_init_fails_closed_on_a_broken_chain(
    ledger_path: Path, attestation: ArtifactAttestation, scope
) -> None:
    """Item 12. The failure mode that matters is not a crash — it is a warning
    that lets exploration proceed against a ledger nobody can trust."""
    first = DiscoveryLedger.open(ledger_path, attestation=attestation)
    record_a_condition(first, scope)

    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[1])
    tampered["payload"]["disposition"] = "promoted"
    lines[1] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
    ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(LedgerInitError, match="does not verify"):
        DiscoveryLedger.open(ledger_path, attestation=attestation)


def test_a_removed_record_breaks_the_chain(
    ledger_path: Path, attestation: ArtifactAttestation, scope
) -> None:
    first = DiscoveryLedger.open(ledger_path, attestation=attestation)
    record_a_condition(first, scope, condition_id="c1")
    record_a_condition(first, scope, condition_id="c2")

    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    del lines[1]
    ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Surfaced as an INIT failure, not merely as a read error: the point is that
    # the next session cannot open this ledger at all, so it cannot explore.
    with pytest.raises(LedgerInitError, match="seq"):
        DiscoveryLedger.open(ledger_path, attestation=attestation)


def test_a_truncated_ledger_is_detected_by_the_open_handle(ledger: DiscoveryLedger, scope) -> None:
    """The one attack the chain alone does not catch: replace the file with a
    shorter but internally consistent one. The handle knows how far it wrote."""
    record_a_condition(ledger, scope)
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    ledger.path.write_text(lines[0] + "\n", encoding="utf-8")

    with pytest.raises(LedgerIntegrityError, match="records"):
        ledger.verify()


def test_init_fails_closed_when_the_ledger_cannot_be_written(
    tmp_path: Path, attestation: ArtifactAttestation
) -> None:
    """An unwritable ledger is a closed gate, not a warning."""
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    with pytest.raises(LedgerInitError):
        DiscoveryLedger.open(blocker / "discovery.jsonl", attestation=attestation)


def test_a_record_of_an_unknown_schema_is_refused(
    ledger_path: Path, attestation: ArtifactAttestation
) -> None:
    """Forward compatibility fails closed too: a build that does not understand
    a newer record shape must not summarise a ledger it cannot fully read."""
    DiscoveryLedger.open(ledger_path, attestation=attestation)
    line = json.loads(ledger_path.read_text(encoding="utf-8").splitlines()[0])
    line["schema"] = 99
    ledger_path.write_text(json.dumps(line) + "\n", encoding="utf-8")

    with pytest.raises(LedgerInitError, match="schema"):
        DiscoveryLedger.open(ledger_path, attestation=attestation)


# === the artifact verification the ledger depends on ========================


def test_verification_covers_both_artifacts_and_every_pin(
    attestation: ArtifactAttestation,
) -> None:
    assert attestation.verified is True
    assert attestation.universe_sha256 == UNIVERSE_SYMBOLS_SHA256
    assert attestation.holdout_symbols_sha256 == HOLDOUT_SYMBOLS_SHA256
    assert attestation.universe_symbol_count == 50
    assert len(attestation.holdout_symbols) == 10
    assert attestation.period_holdout_provenance == "artifact_stamped_and_matches_rule"
    assert attestation.period_holdout_start == date(2026, 10, 6)
    assert attestation.period_holdout_end_exclusive == date(2026, 10, 18)


def test_verification_refuses_a_universe_that_is_not_the_pinned_one(tmp_path: Path) -> None:
    """A self-consistent pair of artifacts is still not the governed pair.

    The two files here agree with each other perfectly — the artifact pins the
    universe it was actually drawn from, the quarantine is a subset of it, the
    period reconciles. Everything a consistency check looks at is fine. What is
    wrong is identity, which is why the pin exists as a separate check.
    """
    universe = sorted(
        {
            *json.loads(
                governed_config("mdq_phase_a_universe_symbols.json").read_text(encoding="utf-8")
            ),
            "ZZZZ",
        }
    )
    swapped_universe = tmp_path / "universe.json"
    swapped_universe.write_text(json.dumps(universe), encoding="utf-8")

    artifact = json.loads(governed_config("mdq_phase_a_holdout.json").read_text(encoding="utf-8"))
    artifact["universe_symbols_sha256"] = _lf_sha256(swapped_universe)
    swapped_artifact = tmp_path / "holdout.json"
    swapped_artifact.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(PolicyError, match="not the pinned Phase-A universe"):
        verify_governed_artifacts(
            universe_symbols_path=swapped_universe,
            holdout_path=swapped_artifact,
        )


def test_verification_refuses_a_moved_quarantine(tmp_path: Path) -> None:
    """The holdout was frozen before capture began (registration section 8 item
    17). If the ten names move, the quarantine is no longer a holdout."""
    artifact = json.loads(governed_config("mdq_phase_a_holdout.json").read_text(encoding="utf-8"))
    artifact["holdout_symbols"] = sorted([*artifact["holdout_symbols"][:-1], "AAPL"])
    # Re-published so the artifact is internally consistent: this is the shape a
    # careful but unauthorised edit would take, and the pin is what catches it.
    artifact["holdout_symbols_sha256"] = canonical_symbol_sha256(artifact["holdout_symbols"])
    swapped = tmp_path / "holdout.json"
    swapped.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(PolicyError, match="quarantined symbol set has moved"):
        verify_governed_artifacts(
            universe_symbols_path=governed_config("mdq_phase_a_universe_symbols.json"),
            holdout_path=swapped,
        )


def test_the_universe_pin_is_over_LF_normalised_bytes(tmp_path: Path) -> None:
    """Same trap as the Phase-A pin, and it bites the same way.

    A CRLF checkout hashes to something else entirely, so verification that used
    raw bytes would pass on the Linux box and fail-closed on a Windows worktree
    (or the reverse, which is worse). ``verify_governed_artifacts`` normalises,
    and this test asserts a CRLF copy of the *same* file still verifies.
    """
    original = governed_config("mdq_phase_a_universe_symbols.json").read_bytes()
    crlf = tmp_path / "universe.json"
    crlf.write_bytes(original.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert b"\r\n" in crlf.read_bytes()

    attested = verify_governed_artifacts(
        universe_symbols_path=crlf,
        holdout_path=governed_config("mdq_phase_a_holdout.json"),
    )
    assert attested.universe_sha256 == UNIVERSE_SYMBOLS_SHA256


def test_a_policy_carries_the_identity_of_the_quarantine_it_enforces() -> None:
    """The cross-check the reader performs needs a value that exists even when
    no artifact was loaded — otherwise a hand-built policy would simply skip it.
    """
    policy = MdqExplorationPolicy(
        universe_symbols=[
            "AAPL",
            "AMZN",
            "EFA",
            "KMLM",
            "MSTR",
            "NBIS",
            "NOW",
            "TSLA",
            "XLK",
            "XLV",
            "XOM",
        ],
        holdout_symbols=["AMZN", "EFA", "KMLM", "MSTR", "NBIS", "NOW", "TSLA", "XLK", "XLV", "XOM"],
        window=ReviewWindow.governed(),
    )
    assert policy.holdout_symbols_sha256 == HOLDOUT_SYMBOLS_SHA256
    scope = policy.authorize(["AAPL"], [SESSION], ReadPurpose.EXPLORATION)
    assert scope.holdout_symbols_sha256 == HOLDOUT_SYMBOLS_SHA256
