"""WP0A-Q-LOCATOR-DISCOVERY — establish the real SEC filing-detail representation.

Why this is a separate module rather than a mode of ``locator``: the canary resolver requires
its accession to be **inside** Envelope B, and discovery requires its target to be **outside**
it. Those are inverse assertions, and keeping them in one code path would mean a single
mistaken flag could point discovery at a governed accession. Here the two can never overlap —
``locator.index_url`` calls ``require_authorized_accession`` and this module calls
``require_out_of_population``, so each refuses exactly what the other demands.

Everything else is deliberately the same machinery the canary will use: the same
``BoundedFetcher`` (frozen origins, no automatic redirects, halt latch, bounded streaming,
retry policy) and the same ``DurableLedger`` accounting, charged to the **index** budget.
That is the whole point of proving the representation this way rather than pasting a file in
— it establishes the exact raw bytes our pinned HTTP stack actually receives.

**The response is evidence, not a test input.** Raw bytes, URL, status, content-type, byte
length, SHA-256 and retrieval time are all retained, so the fixture can be re-verified later
against what was actually served.

⚠ The filing-detail page carries filer metadata including SIC, outside the document table.
That is exactly why the parser this fixture will justify must be **table-positional and
field-limited**. Retaining the raw page as evidence is not a parser act; extracting SIC from
it would be. Nothing in this module interprets the page at all.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from app.altdata.sec001_v31.authority import AcquisitionAuthority, NotAuthorized
from app.altdata.sec001_v31.canary import is_out_of_population
from app.altdata.sec001_v31.custody import atomic_write_json
from app.altdata.sec001_v31.transport import FETCH_OK, BoundedFetcher

#: The frozen discovery target, fixed by the owner BEFORE the request was issued.
SCHEMA_DISCOVERY_CIK: Final = 1144980
SCHEMA_DISCOVERY_FORM: Final = "8-K"
SCHEMA_DISCOVERY_ACCESSION: Final = "0001144980-26-000089"

#: ⛔ The target's form is 8-K. It is a specimen of the SEC *filing-detail representation*
#: and confers no form-scope expansion whatever: the governed WP0A-Q acquisition form set is
#: unchanged, and 8-K remains explicitly deferred in the sealed manifest.
DISCOVERY_CONFERS_NO_FORM_SCOPE: Final = True


class DiscoveryScopeError(RuntimeError):
    """The discovery target is not provably outside the governed population."""


def require_out_of_population(authority: AcquisitionAuthority, accession: str) -> None:
    """The inverse of the canary assertion. Discovery may touch nothing governed."""
    if not is_out_of_population(authority, accession):
        raise DiscoveryScopeError(
            f"{accession} is inside Envelope B; discovery must not touch a governed accession"
        )


def filing_detail_url(authority: AcquisitionAuthority, cik: int, accession: str) -> str:
    """The ``…-index.html`` filing-detail page — NOT the accession-directory ``index.json``.

    The directory listing is a listing; the ``Seq | Description | Document | Type | Size``
    table lives here.
    """
    require_out_of_population(authority, accession)
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/"
        f"{accession.replace('-', '')}/{accession}-index.html"
    )
    authority.require_origin(url)
    return url


@dataclass(frozen=True)
class DiscoveryEvidence:
    url: str
    http_status: int | None
    retrieved_utc: str
    content_type: str | None
    byte_length: int
    sha256: str
    raw_path: str
    truncated: bool
    eof_reached: bool


def run_discovery(
    authority: AcquisitionAuthority,
    fetcher: BoundedFetcher,
    out_dir: Path,
    *,
    cik: int = SCHEMA_DISCOVERY_CIK,
    accession: str = SCHEMA_DISCOVERY_ACCESSION,
) -> DiscoveryEvidence:
    """Issue exactly one counted index request and persist the response as evidence."""
    url = filing_detail_url(authority, cik, accession)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_path = out_dir / f"{accession}-index.html"
    if raw_path.exists():
        raise DiscoveryScopeError(f"{raw_path} already exists; discovery is CREATE-ONCE")

    outcome = fetcher.get_index(url)
    retrieved = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    digest = hashlib.sha256(outcome.body).hexdigest()

    # Raw bytes verbatim -- no decode, no normalisation, no interpretation.
    raw_path.write_bytes(outcome.body)

    ev = DiscoveryEvidence(
        url=url,
        http_status=outcome.http_status,
        retrieved_utc=retrieved,
        content_type=None,
        byte_length=len(outcome.body),
        sha256=digest,
        raw_path=raw_path.name,
        truncated=outcome.truncated,
        eof_reached=outcome.eof_reached,
    )
    atomic_write_json(
        out_dir / "WP0AQ_LOCATOR_DISCOVERY_V1.json",
        {
            "artifact": "SEC001_V3_1_WP0AQ_LOCATOR_DISCOVERY_V1",
            "authority": "WP0A-Q-LOCATOR-DISCOVERY (owner, 1 request)",
            "manifest_sha256": authority.manifest_sha256,
            "envelope_sha256": authority.envelope_sha256,
            "selection_sha256": authority.selection_sha256,
            "target": {
                "cik": cik,
                "form": SCHEMA_DISCOVERY_FORM,
                "accession": accession,
                "out_of_population_proof": is_out_of_population(authority, accession),
                "note": (
                    "specimen of the SEC filing-detail representation; confers NO form-scope "
                    "expansion -- 8-K remains explicitly deferred in the sealed manifest"
                ),
            },
            "response": {
                "url": ev.url,
                "http_status": ev.http_status,
                "retrieved_utc": ev.retrieved_utc,
                "byte_length": ev.byte_length,
                "sha256": ev.sha256,
                "raw_file": ev.raw_path,
                "truncated": ev.truncated,
                "eof_reached": ev.eof_reached,
            },
            "sic_note": (
                "the raw page contains filer metadata including SIC; it is retained as "
                "evidence only. The locator parser must be table-positional and must never "
                "extract SIC from it."
            ),
        },
    )
    if outcome.status != FETCH_OK:
        raise NotAuthorized(
            f"discovery request did not succeed: http {outcome.http_status} ({outcome.reason}); "
            f"evidence retained at {raw_path}"
        )
    return ev


def load_fixture_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_discovery_record(out_dir: Path) -> dict:
    return json.loads((out_dir / "WP0AQ_LOCATOR_DISCOVERY_V1.json").read_text(encoding="utf-8"))
