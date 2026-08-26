"""Adversarial identity fixtures — the cases that decide whether a binding is real.

These are the tests the V3 failure says must exist: every one of them describes a way to
manufacture an identity that looks right and is not.
"""

from __future__ import annotations

import ast
import json

import pytest

from app.altdata.sec001_v31 import cover_parser
from app.altdata.sec001_v31.concepts import (
    COVER_IDENTITY_CONCEPTS,
    FORBIDDEN_CONCEPT_VOCABULARY,
    RETAINED_FIELD_SCHEMA,
)
from app.altdata.sec001_v31.layers import (
    PARSED_FROM_COVER,
    FilingMetadata,
    IdentityScopeViolation,
    Observation,
    ProvenanceViolation,
    SecurityClassEvidence,
)
from tests.altdata.sec001_v31.fixtures import ALPHABET_CLASSES, FORBIDDEN_VALUES, cover_doc

META = FilingMetadata(
    cik=1652044,
    form="10-Q",
    accession="0001652044-26-000070",
    accepted_at="2026-07-23T01:15:54.000Z",
)


def parse(doc: bytes, **kw):
    """Default to EOF so each test states only the condition it is about."""
    kw.setdefault("eof_reached", True)
    return cover_parser.parse_cover_identity(doc, **kw)


# ---------------------------------------------------------------- case 1: ticker only
def test_ticker_only_evidence_is_disputed_never_binding():
    r = parse(cover_doc(classes=[("GOOGL", "", "", "c-classA")]))
    assert r.status == cover_parser.STATUS_DISPUTED_TICKER_ONLY
    assert r.class_tuples == []
    assert not r.is_bound


def test_ticker_only_cannot_be_forced_into_an_observation():
    with pytest.raises(IdentityScopeViolation):
        Observation.build(
            META, SecurityClassEvidence("GOOGL", "", "", "c-classA", source=PARSED_FROM_COVER)
        )


# ------------------------------------------- case 2: one CIK, two independent classes
def test_multiclass_same_cik_yields_two_independently_supported_class_tuples():
    r = parse(cover_doc(classes=ALPHABET_CLASSES))
    assert r.is_bound
    assert r.cik == 1652044
    assert len(r.class_tuples) == 2

    by_symbol = {e.trading_symbol: e for e in r.class_tuples}
    assert set(by_symbol) == {"GOOG", "GOOGL"}
    # each security identity matches its OWN declared class, not a CIK-wide assignment
    assert "Class A" in by_symbol["GOOGL"].security_12b_title
    assert "Class C" in by_symbol["GOOG"].security_12b_title
    assert by_symbol["GOOG"].context_ref != by_symbol["GOOGL"].context_ref

    obs = [Observation.build(META, e) for e in r.class_tuples]
    ids = {o.observation_id("PRIMARY_DOCUMENT_COVER") for o in obs}
    assert len(ids) == 2, "one accession must yield two DISTINCT observation identities"


# ---------------------------------------- case 4: missing title or exchange is disputed
@pytest.mark.parametrize(
    "cls,expected",
    [
        (("GOOG", "", "Nasdaq", "c1"), cover_parser.STATUS_DISPUTED_TICKER_ONLY),
        (("GOOG", "Class C Capital Stock", "", "c1"), cover_parser.STATUS_DISPUTED_INCOMPLETE),
        (("", "Class C Capital Stock", "Nasdaq", "c1"), cover_parser.STATUS_DISPUTED_INCOMPLETE),
    ],
)
def test_incomplete_class_tuple_is_disputed_not_inferred(cls, expected):
    r = parse(cover_doc(classes=[cls]))
    assert r.status == expected
    assert r.class_tuples == []


# ------------------------------- case 5: competing class bindings inside ONE filing
def test_same_title_claiming_two_symbols_fails_closed():
    r = parse(
        cover_doc(
            classes=[
                ("GOOG", "Class C Capital Stock", "Nasdaq", "c1"),
                ("GOOGL", "Class C Capital Stock", "Nasdaq", "c2"),
            ]
        )
    )
    assert r.status == cover_parser.STATUS_FAIL_COMPETING_CLASS
    assert r.class_tuples == []


def test_same_symbol_claiming_two_titles_fails_closed():
    r = parse(
        cover_doc(
            classes=[
                ("GOOG", "Class C Capital Stock", "Nasdaq", "c1"),
                ("GOOG", "Class A Common Stock", "Nasdaq", "c2"),
            ]
        )
    )
    assert r.status == cover_parser.STATUS_FAIL_COMPETING_CLASS


def test_two_distinct_entity_ciks_in_one_document_fail_closed_as_their_own_state():
    r = parse(cover_doc(classes=ALPHABET_CLASSES, extra_cik="0000320193"))
    # a document-internal contradiction, NOT the cross-filing competing-binding conjunct
    assert r.status == cover_parser.STATUS_FAIL_MULTIPLE_CIK
    assert r.status != cover_parser.STATUS_FAIL_COMPETING_CLASS
    assert r.diagnostics["reason"] == "multiple_entity_cik"


def test_absent_entity_cik_fails_closed():
    assert (
        parse(cover_doc(cik=None, classes=ALPHABET_CLASSES)).status
        == cover_parser.STATUS_FAIL_NO_CIK
    )


# --------------------------------- case 11: forbidden concepts are never extracted at all
def test_forbidden_concepts_present_in_fixture_are_never_extracted_or_leaked():
    doc = cover_doc(classes=ALPHABET_CLASSES, include_forbidden=True)
    for concept in FORBIDDEN_CONCEPT_VOCABULARY:
        assert concept.encode() in doc, "fixture must really contain the forbidden concepts"
    for value in FORBIDDEN_VALUES.values():
        assert value.encode() in doc

    r = parse(doc)
    assert r.is_bound

    blob = json.dumps(
        {
            "status": r.status,
            "cik": r.cik,
            "tuples": [e.__dict__ for e in r.class_tuples],
            "diagnostics": r.diagnostics,
            "records": [Observation.build(META, e).to_record() for e in r.class_tuples],
        },
        default=str,
    )
    for value in FORBIDDEN_VALUES.values():
        assert value not in blob, f"forbidden value {value!r} leaked into output"
    for concept in FORBIDDEN_CONCEPT_VOCABULARY:
        assert concept not in blob
    assert "7370" not in blob and "sic" not in blob.lower()


def test_parser_module_never_references_the_forbidden_vocabulary():
    """Structural, not behavioural: there is nothing to filter against.

    Checked over the parsed AST rather than the source text, so the docstring may explain
    the design without the test mistaking prose for a reference.
    """
    with open(cover_parser.__file__ or "", encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    imported: set[str] = set()
    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)

    assert "FORBIDDEN_CONCEPT_VOCABULARY" not in imported
    assert "FORBIDDEN_CONCEPT_VOCABULARY" not in referenced
    assert "COVER_IDENTITY_CONCEPTS" in imported


def test_allowlist_is_exactly_the_four_identity_concepts():
    assert set(COVER_IDENTITY_CONCEPTS) == {
        "dei:EntityCentralIndexKey",
        "dei:TradingSymbol",
        "dei:Security12bTitle",
        "dei:SecurityExchangeName",
    }
    assert not set(COVER_IDENTITY_CONCEPTS) & set(FORBIDDEN_CONCEPT_VOCABULARY)


# ------------------------------------------ case 10: emission outside the schema fails
def test_observation_record_is_exactly_the_seven_frozen_fields():
    r = parse(cover_doc(classes=ALPHABET_CLASSES))
    rec = Observation.build(META, r.class_tuples[0]).to_record()
    assert set(rec) == set(RETAINED_FIELD_SCHEMA)
    assert len(rec) == 7
    assert "context_ref" not in rec


def test_evidence_without_cover_provenance_is_rejected():
    forged = SecurityClassEvidence("GOOG", "Class C", "Nasdaq", "c1", source="TRANSPORT_LOCATOR")
    with pytest.raises(ProvenanceViolation):
        Observation.build(META, forged)


# ==========================================================================
# REVISED CONTROL 1 — completeness requires EOF. Distance proves nothing.
# ==========================================================================
def test_non_eof_read_with_one_apparently_complete_class_is_evidence_unavailable():
    """The precise failure the revision exists to prevent."""
    doc = cover_doc(classes=[ALPHABET_CLASSES[0]])
    r = cover_parser.parse_cover_identity(doc, eof_reached=False, bytes_consumed=len(doc))
    assert r.status == cover_parser.STATUS_EVIDENCE_UNAVAILABLE
    assert r.diagnostics["reason"] == "bounded_read_did_not_reach_eof"
    assert r.class_tuples == []
    assert r.cik is None


def test_last_fact_far_beyond_the_margin_still_cannot_manufacture_completeness():
    """The rule the previous revision got wrong: 200 KiB of distance is not a proof."""
    doc = cover_doc(classes=ALPHABET_CLASSES, pad_after=200_000)
    r = cover_parser.parse_cover_identity(doc, eof_reached=False, bytes_consumed=len(doc))
    assert r.status == cover_parser.STATUS_EVIDENCE_UNAVAILABLE
    assert r.diagnostics["reason"] == "bounded_read_did_not_reach_eof"


@pytest.mark.parametrize("n_classes", [1, 2, 3])
@pytest.mark.parametrize("symbols", [("AAA", "BBB", "CCC"), ("GOOG", "GOOGL", "GOOGM")])
def test_completeness_is_independent_of_symbol_values_and_tuple_count(n_classes, symbols):
    """Completeness must not be a function of what, or how much, was observed."""
    classes = [
        (symbols[i], f"Class {i} Common Stock", "Nasdaq Global Select Market", f"c{i}")
        for i in range(n_classes)
    ]
    doc = cover_doc(classes=classes)

    not_eof = cover_parser.parse_cover_identity(doc, eof_reached=False, bytes_consumed=len(doc))
    assert not_eof.status == cover_parser.STATUS_EVIDENCE_UNAVAILABLE

    at_eof = cover_parser.parse_cover_identity(doc, eof_reached=True, bytes_consumed=len(doc))
    assert at_eof.is_bound and len(at_eof.class_tuples) == n_classes


def test_no_structural_boundary_prover_is_implemented():
    """The second disjunct is deliberately absent; EOF is the only admission rule.

    If a future revision adds one it must be independent of observed values, and this test
    must be replaced by tests of that independence.
    """
    with open(cover_parser.__file__ or "", encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert not {n for n in names if "structural" in n.lower()}


def test_eof_claimed_alongside_truncation_is_refused_as_defence_in_depth():
    doc = cover_doc(classes=ALPHABET_CLASSES)
    r = cover_parser.parse_cover_identity(
        doc, eof_reached=True, truncated=True, bytes_consumed=len(doc)
    )
    assert r.status == cover_parser.STATUS_EVIDENCE_UNAVAILABLE
    assert r.diagnostics["reason"] == "eof_claimed_but_read_reports_truncation"


def test_eof_is_a_required_keyword():
    with pytest.raises(TypeError):
        cover_parser.parse_cover_identity(cover_doc(classes=ALPHABET_CLASSES))  # type: ignore[call-arg]


def test_empty_prefix_without_eof_is_evidence_unavailable():
    r = cover_parser.parse_cover_identity(b"<html><body>" + b"x" * 5000, eof_reached=False)
    assert r.status == cover_parser.STATUS_EVIDENCE_UNAVAILABLE


# ==========================================================================
# REVIEW FIX — duplicate facts must fail closed, never silently overwrite
# ==========================================================================
def test_two_different_entity_ciks_in_the_SAME_context_fail_closed():
    """Previously `setdefault` let the first CIK win and the second vanish."""
    doc = (
        b'<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"><body>'
        b'<ix:nonNumeric name="dei:EntityCentralIndexKey" contextRef="c-entity">0001652044</ix:nonNumeric>'
        b'<ix:nonNumeric name="dei:EntityCentralIndexKey" contextRef="c-entity">0000320193</ix:nonNumeric>'
        b'<ix:nonNumeric name="dei:Security12bTitle" contextRef="c1">Class A</ix:nonNumeric>'
        b'<ix:nonNumeric name="dei:TradingSymbol" contextRef="c1">GOOGL</ix:nonNumeric>'
        b'<ix:nonNumeric name="dei:SecurityExchangeName" contextRef="c1">Nasdaq</ix:nonNumeric>'
        b"</body></html>"
    )
    r = parse(doc)
    assert r.status == cover_parser.STATUS_FAIL_MULTIPLE_CIK
    assert r.class_tuples == []


@pytest.mark.parametrize(
    "concept,a,b",
    [
        ("dei:TradingSymbol", "GOOG", "GOOGL"),
        ("dei:Security12bTitle", "Class A Common Stock", "Class C Capital Stock"),
        ("dei:SecurityExchangeName", "Nasdaq", "NYSE"),
    ],
)
def test_two_different_values_for_one_concept_in_one_context_fail_closed(concept, a, b):
    """Previously plain assignment let the second value overwrite the first."""
    parts = [
        b'<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"><body>',
        b'<ix:nonNumeric name="dei:EntityCentralIndexKey" contextRef="e">0001652044</ix:nonNumeric>',
    ]
    for c, v in (
        ("dei:Security12bTitle", "Class A"),
        ("dei:TradingSymbol", "GOOGL"),
        ("dei:SecurityExchangeName", "Nasdaq"),
    ):
        if c != concept:
            parts.append(f'<ix:nonNumeric name="{c}" contextRef="c1">{v}</ix:nonNumeric>'.encode())
    parts.append(f'<ix:nonNumeric name="{concept}" contextRef="c1">{a}</ix:nonNumeric>'.encode())
    parts.append(f'<ix:nonNumeric name="{concept}" contextRef="c1">{b}</ix:nonNumeric>'.encode())
    parts.append(b"</body></html>")

    r = parse(b"".join(parts))
    assert r.status == cover_parser.STATUS_FAIL_COMPETING_CLASS
    assert r.diagnostics["reason"] == "conflicting_facts_in_one_context"
    assert r.class_tuples == []


def test_identical_repeated_facts_deduplicate_harmlessly():
    """Inline XBRL repeats the same fact legitimately; only DISTINCT values contradict."""
    doc = (
        b'<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"><body>'
        b'<ix:nonNumeric name="dei:EntityCentralIndexKey" contextRef="e">0001652044</ix:nonNumeric>'
        b'<ix:nonNumeric name="dei:EntityCentralIndexKey" contextRef="e2">0001652044</ix:nonNumeric>'
        b'<ix:nonNumeric name="dei:Security12bTitle" contextRef="c1">Class A</ix:nonNumeric>'
        b'<ix:nonNumeric name="dei:Security12bTitle" contextRef="c1">Class A</ix:nonNumeric>'
        b'<ix:nonNumeric name="dei:TradingSymbol" contextRef="c1">GOOGL</ix:nonNumeric>'
        b'<ix:nonNumeric name="dei:SecurityExchangeName" contextRef="c1">Nasdaq</ix:nonNumeric>'
        b"</body></html>"
    )
    r = parse(doc)
    assert r.is_bound and len(r.class_tuples) == 1
    assert r.class_tuples[0].trading_symbol == "GOOGL"


# ==========================================================================
# REVIEW FIX — provenance has no accepting default
# ==========================================================================
def test_security_class_evidence_requires_an_explicit_source():
    with pytest.raises(TypeError):
        SecurityClassEvidence("GOOG", "Class C", "Nasdaq", "c1")  # type: ignore[call-arg]


def test_parser_is_the_only_producer_of_cover_provenance():
    """Structural: PARSED_FROM_COVER is written in exactly one production module."""
    import pathlib

    pkg = pathlib.Path(cover_parser.__file__).parent
    producers = [
        f.name
        for f in pkg.glob("*.py")
        if "source=PARSED_FROM_COVER" in f.read_text(encoding="utf-8")
    ]
    assert producers == ["cover_parser.py"], producers
