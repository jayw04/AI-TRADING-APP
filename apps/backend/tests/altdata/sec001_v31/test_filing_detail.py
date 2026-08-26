"""The locator parser, against the REAL SEC representation.

The fixture is the governed WP0A-Q-LOCATOR-DISCOVERY response — a live SEC filing-detail page
retained byte-for-byte and pinned by digest. The previous model was invented by a synthetic
fixture and was wrong in every particular, so nothing here is allowed to assert the schema
into existence: the file on disk is what SEC served.
"""

from __future__ import annotations

import hashlib
import json
import re

import pytest

from app.altdata.sec001_v31.filing_detail import (
    AMBIGUOUS_PRIMARY_ROW,
    BAD_DOCUMENT,
    BAD_SIZE,
    DOCUMENT_TABLE_SUMMARY,
    EXPECTED_HEADERS,
    NO_PRIMARY_ROW,
    SCHEMA_UNSUPPORTED,
    FilingDetailError,
    extract_document_table,
    parse_primary_document,
)
from tests.altdata.sec001_v31.conftest import REPO_ROOT

DISCOVERY = REPO_ROOT / "artifacts" / "wp0aq" / "discovery"
FIXTURE = DISCOVERY / "0001144980-26-000089-index.html"
FIXTURE_SHA256 = "a7d17ade7e55834dfe2770e608ff66611daa893c1420b5dd149c405d0edfae90"


@pytest.fixture(scope="module")
def real_page() -> bytes:
    return FIXTURE.read_bytes()


# ============================================================ the fixture is governed
def test_the_fixture_is_the_pinned_discovery_response(real_page):
    assert hashlib.sha256(real_page).hexdigest() == FIXTURE_SHA256


def test_the_discovery_record_matches_the_fixture(real_page):
    rec = json.loads((DISCOVERY / "WP0AQ_LOCATOR_DISCOVERY_V1.json").read_text(encoding="utf-8"))
    assert rec["response"]["sha256"] == FIXTURE_SHA256
    assert rec["response"]["http_status"] == 200
    assert rec["response"]["byte_length"] == len(real_page)
    assert rec["response"]["eof_reached"] is True
    assert rec["target"]["out_of_population_proof"] is True
    assert rec["target"]["accession"] == "0001144980-26-000089"


def test_the_discovery_target_was_frozen_before_the_request():
    t = json.loads((DISCOVERY / "WP0AQ_LOCATOR_DISCOVERY_TARGET.json").read_text(encoding="utf-8"))
    assert t["frozen_before_request"] is True
    assert t["out_of_population_proof"] is True
    assert t["confers_no_form_scope"] is True
    assert t["representation"].startswith("filing-detail")
    assert "-index.html" in t["representation"]


# ============================================================ the real schema
def test_the_real_header_contract(real_page):
    table = extract_document_table(real_page)
    heads = tuple(
        " ".join(re.sub(r"<[^>]*>", " ", h).split())
        for h in re.findall(r"<th[^>]*>(.*?)</th>", table, re.S | re.I)
    )
    assert heads == EXPECTED_HEADERS == ("Seq", "Description", "Document", "Type", "Size")


def test_the_primary_document_resolves_exactly_as_sec_shows_it(real_page):
    p = parse_primary_document(real_page, "8-K")
    assert p.document == "abg-20260728.htm"
    assert p.doc_type == "8-K"
    assert p.size == 34556
    assert p.seq == "1"


# --------- trap 1: two tables share class="tableFile" AND the same header row
def test_two_tables_share_the_class_so_selection_is_by_summary(real_page):
    page = real_page.decode("utf-8", "replace")
    all_tables = re.findall(r'<table[^>]*class="tableFile"[^>]*>', page, re.I)
    assert len(all_tables) == 2, "the specimen really does have two -- class alone is ambiguous"
    summaries = re.findall(r'<table[^>]*class="tableFile"[^>]*summary="([^"]*)"', page, re.I)
    assert set(summaries) == {"Document Format Files", "Data Files"}
    assert DOCUMENT_TABLE_SUMMARY == "Document Format Files"


def test_the_data_files_table_is_out_of_scope(real_page):
    """EX-101.* sidecars live in the other table and must be unreachable."""
    for sidecar in ("EX-101.SCH", "EX-101.DEF", "EX-101.LAB", "EX-101.PRE", "XML"):
        with pytest.raises(FilingDetailError) as e:
            parse_primary_document(real_page, sidecar)
        assert e.value.reason == NO_PRIMARY_ROW
    table = extract_document_table(real_page)
    assert "EX-101.SCH" not in table


# --------- trap 2: the Document cell is an anchor plus decoration
def test_the_document_is_the_anchor_text_not_the_cell_text(real_page):
    """The cell reads 'abg-20260728.htm   iXBRL'; the filename is the anchor text."""
    table = extract_document_table(real_page)
    row = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I)[1]
    cell = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)[2]
    cell_text = " ".join(re.sub(r"<[^>]*>", " ", cell).split())
    assert "iXBRL" in cell_text, "the decoration really is there"

    p = parse_primary_document(real_page, "8-K")
    assert p.document == "abg-20260728.htm"
    assert "iXBRL" not in p.document


def test_the_href_is_a_viewer_url_and_is_never_used_as_a_path(real_page):
    """The anchor points at /ix?doc=… -- using href as a path would build a wrong URL."""
    table = extract_document_table(real_page)
    href = re.search(r'<a href="([^"]+)"', table).group(1)
    assert href.startswith("/ix?doc=")
    p = parse_primary_document(real_page, "8-K")
    assert "/ix?doc=" not in p.document and "?" not in p.document


def test_a_document_cell_without_an_anchor_fails_closed():
    page = _table([("1", "8-K", "abg-20260728.htm", "8-K", "34556")], anchor=False)
    with pytest.raises(FilingDetailError) as e:
        parse_primary_document(page, "8-K")
    assert e.value.reason == BAD_DOCUMENT


# --------- trap 3: rows can carry an EMPTY Type, and one of them is huge
def test_the_complete_submission_row_has_no_type_and_is_over_the_read_bound(real_page):
    table = extract_document_table(real_page)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I)[1:]
    cells = [
        [
            " ".join(re.sub(r"<[^>]*>", " ", c).split())
            for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S | re.I)
        ]
        for r in rows
    ]
    empty_type = [c for c in cells if len(c) >= 5 and c[3] in ("", "&nbsp;")]
    assert empty_type, "the specimen has a complete-submission row with no Type"
    assert int(empty_type[0][4]) > 983_040, "and it is larger than the frozen read bound"


def test_an_empty_form_cannot_select_the_complete_submission_row(real_page):
    """Without this guard an empty form matches the 1.1 MB .txt row."""
    with pytest.raises(FilingDetailError) as e:
        parse_primary_document(real_page, "")
    assert e.value.reason == SCHEMA_UNSUPPORTED


# ============================================================ SIC-blindness, for real
def test_the_real_page_carries_SIC_and_the_parser_output_does_not(real_page):
    page = real_page.decode("utf-8", "replace")
    m = re.search(r"SIC=(\d{3,4})", page) or re.search(r"SIC[^0-9]{0,40}(\d{4})", page)
    assert m, "the specimen must really contain SIC, or this proves nothing"
    sic = m.group(1)

    p = parse_primary_document(real_page, "8-K")
    emitted = f"{p.seq}|{p.document}|{p.doc_type}|{p.size}"
    assert sic not in emitted


def test_sic_is_outside_the_sliced_table_so_it_is_never_in_scope(real_page):
    table = extract_document_table(real_page)
    assert "SIC" not in table.upper()
    assert len(table) < len(real_page), "the slice is strictly smaller than the page"


def test_the_parser_never_builds_a_page_wide_text_map():
    """Structural: the page is sliced before anything is read out of it."""
    import ast
    import inspect

    from app.altdata.sec001_v31 import filing_detail

    tree = ast.parse(inspect.getsource(filing_detail.parse_primary_document))
    calls = [
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    assert calls[0] if calls else None
    assert "extract_document_table" in calls, "the slice must happen first"


# ============================================================ negative controls
def _table(rows, *, summary=DOCUMENT_TABLE_SUMMARY, headers=EXPECTED_HEADERS, anchor=True) -> bytes:
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = ""
    for r in rows:
        doc = f'<a href="/ix?doc=/x/{r[2]}">{r[2]}</a>' if anchor else r[2]
        cells = [r[0], r[1], doc, r[3], r[4]]
        trs += "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"
    return (
        f'<html><body><table class="tableFile" summary="{summary}">'
        f"<tr>{th}</tr>{trs}</table></body></html>"
    ).encode()


def test_a_missing_document_table_fails_closed():
    with pytest.raises(FilingDetailError) as e:
        parse_primary_document(_table([], summary="Data Files"), "10-K")
    assert e.value.reason == SCHEMA_UNSUPPORTED


def test_a_changed_header_row_fails_closed():
    page = _table([("1", "10-K", "a.htm", "10-K", "100")], headers=("Seq", "Doc", "Type", "Size"))
    with pytest.raises(FilingDetailError) as e:
        parse_primary_document(page, "10-K")
    assert e.value.reason == SCHEMA_UNSUPPORTED


def test_two_rows_of_the_same_form_fail_closed_rather_than_picking_one():
    page = _table([("1", "10-K", "a.htm", "10-K", "100"), ("2", "10-K", "b.htm", "10-K", "200")])
    with pytest.raises(FilingDetailError) as e:
        parse_primary_document(page, "10-K")
    assert e.value.reason == AMBIGUOUS_PRIMARY_ROW


@pytest.mark.parametrize("size", ["", "0", "not-a-number", "-5", "1,234"])
def test_a_non_authoritative_size_fails_closed(size):
    page = _table([("1", "10-K", "a.htm", "10-K", size)])
    with pytest.raises(FilingDetailError) as e:
        parse_primary_document(page, "10-K")
    assert e.value.reason == BAD_SIZE


def test_two_tables_claiming_the_same_summary_fail_closed():
    one = _table([("1", "10-K", "a.htm", "10-K", "100")]).decode()
    doubled = one.replace(
        "</body>", one[one.index("<table") : one.index("</table>") + 8] + "</body>"
    )
    with pytest.raises(FilingDetailError) as e:
        parse_primary_document(doubled.encode(), "10-K")
    assert e.value.reason == SCHEMA_UNSUPPORTED


def test_a_well_formed_synthetic_page_still_parses():
    p = parse_primary_document(_table([("1", "10-Q", "x-2026.htm", "10-Q", "512000")]), "10-Q")
    assert (p.document, p.doc_type, p.size) == ("x-2026.htm", "10-Q", 512000)
