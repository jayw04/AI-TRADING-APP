"""WP0A-Q document canary #1: acquire ONE authorized document, parse its cover page, STOP.

Uses the accession's ALREADY-RESOLVED locator -- no further index request is spent, because
the locator is authoritative and journaled.

Run:  python scripts/sec001_v31_document_canary.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # pragma: no cover
    pass

from app.altdata.sec001_v31 import canary
from app.altdata.sec001_v31.acquire import CoverAcquisition
from app.altdata.sec001_v31.authority import (
    LIVE_MAX_CONTINUATIONS,
    MAX_DOCUMENT_BYTES,
    AcquisitionAuthority,
)
from app.altdata.sec001_v31.custody import (
    AccessionState,
    AcquisitionJournal,
    TransactionalEvidenceStore,
    reconcile,
)
from app.altdata.sec001_v31.layers import FilingMetadata
from app.altdata.sec001_v31.locator import LocatorResolver
from app.altdata.sec001_v31.transport import BoundedFetcher, DurableLedger

REPO = Path(__file__).resolve().parents[3]
STATE = REPO / "artifacts" / "wp0aq" / "state"
USER_AGENT = "TradingWorkbench SEC001-V3 (GlobalComplyAI, LLC) jay.w0416@gmail.com"

CIK, FORM, ACCESSION = 97210, "10-K", "0001193125-21-050735"


def main() -> int:
    authority = AcquisitionAuthority.load(REPO)
    key = authority.require_authorized_accession(ACCESSION)
    assert key[0] == CIK and key[1] == FORM, key
    meta = FilingMetadata(cik=CIK, form=FORM, accession=ACCESSION, accepted_at=key[3])
    print(f"authorized target: {CIK} / {FORM} / {ACCESSION}")

    ledger = DurableLedger.open(STATE / "request_ledger.json", authority)
    journal = AcquisitionJournal(STATE / "acquisition_journal.json")
    store = TransactionalEvidenceStore(STATE / "evidence")
    idx_before, doc_before = ledger.index_requests, ledger.document_requests
    print(f"before: index {idx_before}/200  documents {doc_before}/1200")

    fetcher = BoundedFetcher(authority, ledger, user_agent=USER_AGENT)
    try:
        # The locator is already LOCATOR_RESOLVED -- this replays it, spending no request.
        resolved = LocatorResolver(authority, fetcher, journal).resolve(CIK, ACCESSION)
        assert ledger.index_requests == idx_before, "the locator must be replayed, not re-fetched"
        print(
            f"locator replayed (0 index requests): {resolved.primary_document} "
            f"{resolved.document_size:,} bytes"
        )

        eligible, reason = canary.screen(resolved.document_size)
        print(
            f"screen: {'PASS' if eligible else 'FAIL'} -- {reason} "
            f"(ceiling {MAX_DOCUMENT_BYTES:,}, C={LIVE_MAX_CONTINUATIONS})"
        )
        if not eligible:
            print("REFUSING: ineligible under the frozen screen", file=sys.stderr)
            return 2

        result = CoverAcquisition(authority, fetcher, store, ledger, journal).acquire(
            meta, resolved.transport_locator()
        )
    finally:
        fetcher.close()
        print(
            f"after : index {ledger.index_requests}/200  documents {ledger.document_requests}/1200"
        )

    print()
    print(f"  status           {result.status}")
    print(f"  parse status     {result.parse_status}")
    print(f"  accession state  {result.accession_state}")
    print(f"  document requests consumed  {result.document_requests_spent}")
    d = result.diagnostics
    print(f"  continuations    {d.get('continuations')}")
    print(
        f"  bytes            {d.get('bytes_consumed'):,}"
        if d.get("bytes_consumed")
        else f"  bytes {d.get('bytes_consumed')}"
    )
    print(f"  eof proof        {d.get('eof_reached')}")
    print(f"  content type     {d.get('content_type')}")
    print(f"  body sha256      {d.get('body_sha256')}")

    if result.observations:
        print(f"\n  COVER-PAGE IDENTITY ({len(result.observations)} class tuple(s)):")
        for o in result.observations:
            print(
                f"    cik={o.cik}  symbol={o.trading_symbol!r}  "
                f"title={o.security_12b_title!r}  exchange={o.security_exchange_name!r}"
            )
        for ident in result.artifact_identities:
            print(f"    artifact identity  {ident}")
        p = store.path_for(CIK, ACCESSION, authority.source_variant)
        print(f"    artifact sha256    {hashlib.sha256(p.read_bytes()).hexdigest()}")

    print(f"\n  journal   {journal.state_of(ACCESSION).value}")
    print(f"  reconcile {reconcile(journal, store, authority.source_variant)}")
    print(f"  remaining document budget  {1200 - ledger.document_requests}")
    print("\nSTOP -- no second document.")
    return 0 if result.accession_state == AccessionState.SEALED.value else 3


if __name__ == "__main__":
    raise SystemExit(main())
