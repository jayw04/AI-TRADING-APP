"""Positional parser for the SEC filing-detail document table. Structurally SIC-blind.

Grounded in a governed fixture — `artifacts/wp0aq/discovery/0001144980-26-000089-index.html`,
sha256 `a7d17ade…` — fetched under WP0A-Q-LOCATOR-DISCOVERY. The previous model was invented
by its own test fixture and was wrong in every particular; everything below is what SEC
actually served.

**SIC-blindness is structural, exactly as in the cover parser.** The filing-detail page
carries filer metadata including SIC *outside* the document tables. So the very first act is
to slice out the one table region, and nothing afterwards ever sees another byte of the page.
There is no page-wide text map to filter, so SIC cannot be extracted, because it is never in
scope.

Three properties of the real representation that a synthetic fixture would have hidden, and
that this parser therefore has to handle:

**Two tables share ``class="tableFile"`` with identical headers.** "Document Format Files"
and "Data Files" are indistinguishable by class or by header row; only ``summary``
separates them. Selecting by class would silently admit XBRL sidecar files.

**The Document cell is not the filename.** It is an anchor plus decoration:
``<a href="/ix?doc=/Archives/…/abg-20260728.htm">abg-20260728.htm</a> &nbsp;&nbsp;<span>iXBRL</span>``
Cell text yields ``abg-20260728.htm iXBRL``. The anchor *text* is the filename; the ``href``
is an ``/ix?doc=`` **viewer** URL and must not be mistaken for an archive path.

**Rows may carry an empty Type.** The complete-submission ``.txt`` row has no Seq and no
Type — and, in the specimen, is 1,164,076 bytes, comfortably over the frozen read bound. Any
"otherwise take the biggest/last row" fallback would select it. There is no fallback here.

**Type alone does not identify the primary document.** The size census found an accession with
*two* rows declared ``10-Q``: an HTML report at sequence 1 and a courtesy PDF of the same
report at sequence 2. Matching on Type alone was ambiguous, and a first-match rule would have
silently taken one — possibly the PDF. The owner froze the structural rule instead: the primary
document is the **sequence-1** row, and its Type must independently equal the sealed form.
Neither half is a tiebreak, and Description text such as "COURTESY COPY" is never consulted.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Final

#: The one table that describes the filing's own documents.
DOCUMENT_TABLE_SUMMARY: Final = "Document Format Files"

#: The frozen column contract. A page whose header row differs is not this representation.
EXPECTED_HEADERS: Final[tuple[str, ...]] = ("Seq", "Description", "Document", "Type", "Size")

#: The only columns ever materialised. ``Description`` is read to satisfy the column contract
#: and is deliberately not retained.
RETAINED_COLUMNS: Final[tuple[str, ...]] = ("Seq", "Document", "Type", "Size")

_TABLE = re.compile(
    r'<table[^>]*class="tableFile"[^>]*summary="(?P<summary>[^"]*)"[^>]*>(?P<body>.*?)</table>',
    re.S | re.I,
)
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TH = re.compile(r"<th[^>]*>(.*?)</th>", re.S | re.I)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_ANCHOR = re.compile(r"<a[^>]*>(.*?)</a>", re.S | re.I)
_TAG = re.compile(r"<[^>]*>")

#: The structural identity of the primary document. SEC submission representations place the
#: filing's own primary document at sequence 1; later sequences are exhibits and courtesy
#: copies. Frozen by the owner after the census found a filing carrying an HTML *and* a PDF of
#: the same report, both declared 10-Q.
PRIMARY_SEQUENCE: Final = "1"

SCHEMA_UNSUPPORTED: Final = "FILING_DETAIL_SCHEMA_UNSUPPORTED"
NO_PRIMARY_ROW: Final = "FILING_DETAIL_NO_PRIMARY_ROW"
AMBIGUOUS_PRIMARY_ROW: Final = "FILING_DETAIL_AMBIGUOUS_PRIMARY_ROW"
SEQ1_TYPE_MISMATCH: Final = "FILING_DETAIL_SEQ1_TYPE_MISMATCH"
BAD_SIZE: Final = "FILING_DETAIL_SIZE_NOT_AUTHORITATIVE"
BAD_DOCUMENT: Final = "FILING_DETAIL_DOCUMENT_NOT_RESOLVABLE"


class FilingDetailError(RuntimeError):
    """The filing-detail page did not satisfy the frozen row contract."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass(frozen=True)
class PrimaryDocument:
    """The four retained fields for the filing's own primary document."""

    seq: str
    document: str
    doc_type: str
    size: int


def _text(fragment: str) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", fragment)).split())


def _document_name(cell: str) -> str:
    """The filename is the ANCHOR TEXT, never the cell text and never the href."""
    m = _ANCHOR.search(cell)
    if not m:
        raise FilingDetailError(BAD_DOCUMENT, "document cell carries no anchor")
    name = _text(m.group(1))
    if not name:
        raise FilingDetailError(BAD_DOCUMENT, "document anchor is empty")
    return name


def extract_document_table(raw: bytes) -> str:
    """Slice out the one in-scope table. Nothing else on the page is ever read."""
    page = raw.decode("utf-8", "replace")
    matches = [
        m for m in _TABLE.finditer(page) if m.group("summary").strip() == DOCUMENT_TABLE_SUMMARY
    ]
    if not matches:
        raise FilingDetailError(
            SCHEMA_UNSUPPORTED, f"no table with summary={DOCUMENT_TABLE_SUMMARY!r}"
        )
    if len(matches) > 1:
        raise FilingDetailError(
            SCHEMA_UNSUPPORTED, f"{len(matches)} tables claim summary={DOCUMENT_TABLE_SUMMARY!r}"
        )
    # From here on, only this fragment exists. `page` goes out of scope.
    return matches[0].group("body")


def _column_index(table: str) -> dict[str, int]:
    rows = _ROW.findall(table)
    if not rows:
        raise FilingDetailError(SCHEMA_UNSUPPORTED, "table has no rows")
    headers = tuple(_text(h) for h in _TH.findall(rows[0]))
    if headers != EXPECTED_HEADERS:
        raise FilingDetailError(
            SCHEMA_UNSUPPORTED, f"header row {headers} does not match {EXPECTED_HEADERS}"
        )
    return {name: i for i, name in enumerate(headers)}


def parse_primary_document(raw: bytes, form: str) -> PrimaryDocument:
    """Resolve the filing's own primary document by its declared Type.

    The primary document is the row at **sequence 1** whose ``Type`` is the sealed form. Both
    halves are required and neither is a fallback: ``Seq == 1`` is the structural
    primary-document identity, and ``Type == form`` independently verifies it is the governed
    form. A sequence-1 row of the wrong type is a determinate mismatch, **not** a licence to
    look at sequence 2.
    """
    # The specimen's complete-submission row carries an EMPTY Seq and Type -- and is 1.1 MB,
    # well over the frozen read bound. An empty form would therefore match it. `form` comes
    # from the sealed envelope and is never empty today; this refuses the shape anyway,
    # because "the caller cannot currently do that" is not a control.
    if not form.strip():
        raise FilingDetailError(SCHEMA_UNSUPPORTED, "form is empty; it cannot select a row")
    table = extract_document_table(raw)
    idx = _column_index(table)
    rows = _ROW.findall(table)[1:]

    seq_one: list[list[str]] = []
    for row in rows:
        cells = _TD.findall(row)
        if len(cells) <= max(idx.values()):
            continue
        if _text(cells[idx["Seq"]]) == PRIMARY_SEQUENCE:
            seq_one.append(cells)

    if not seq_one:
        raise FilingDetailError(
            NO_PRIMARY_ROW, f"the document table has no row at sequence {PRIMARY_SEQUENCE}"
        )
    if len(seq_one) > 1:
        raise FilingDetailError(
            AMBIGUOUS_PRIMARY_ROW, f"{len(seq_one)} rows claim sequence {PRIMARY_SEQUENCE}"
        )

    cells = seq_one[0]
    declared = _text(cells[idx["Type"]])
    if declared != form:
        # Determinate mismatch. Explicitly NOT a reason to consider sequence 2.
        raise FilingDetailError(
            SEQ1_TYPE_MISMATCH,
            f"sequence {PRIMARY_SEQUENCE} declares Type {declared!r}, not the sealed form {form!r}",
        )

    raw_size = _text(cells[idx["Size"]])
    if not raw_size.isdigit() or int(raw_size) <= 0:
        raise FilingDetailError(BAD_SIZE, f"size {raw_size!r} is not authoritative")
    return PrimaryDocument(
        seq=_text(cells[idx["Seq"]]),
        document=_document_name(cells[idx["Document"]]),
        doc_type=declared,
        size=int(raw_size),
    )
