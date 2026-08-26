"""WP0A-Q canary locator: resolve ONE authorized accession's primary document, then STOP.

Authority: one counted **index** request. The document budget must not move.

  1. load and hash-verify the acquisition authority
  2. re-derive the canary candidate from hash-bound authority data and assert it is the
     frozen first candidate
  3. resolve the locator through the journaled, exactly-once resolver
  4. run the pre-document size screen
  5. STOP -- document request #1 is not authorized

Run:  python scripts/sec001_v31_canary_locator.py
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # pragma: no cover
    pass

from app.altdata.sec001_v31 import canary
from app.altdata.sec001_v31.authority import AcquisitionAuthority
from app.altdata.sec001_v31.custody import (
    AcquisitionJournal,
    TransactionalEvidenceStore,
    reconcile,
)
from app.altdata.sec001_v31.locator import LocatorResolutionError, LocatorResolver
from app.altdata.sec001_v31.transport import BoundedFetcher, CrawlHalt, DurableLedger

REPO = Path(__file__).resolve().parents[3]
STATE = REPO / "artifacts" / "wp0aq" / "state"
USER_AGENT = "TradingWorkbench SEC001-V3 (GlobalComplyAI, LLC) jay.w0416@gmail.com"

FROZEN_CIK = 97210
FROZEN_FORM = "10-K"
FROZEN_ACCESSION = "0001193125-21-050735"


def main() -> int:
    authority = AcquisitionAuthority.load(REPO)
    candidate = canary.first_candidate(authority)
    print(f"first candidate (hash-bound): {candidate}")

    if (candidate.cik, candidate.form, candidate.accession) != (
        FROZEN_CIK,
        FROZEN_FORM,
        FROZEN_ACCESSION,
    ):
        print("REFUSING: candidate does not match the frozen target", file=sys.stderr)
        return 2
    assert candidate.accession not in authority.bracket_accessions
    print("  matches the frozen authorization, and is not a bracket accession")

    ledger = DurableLedger.open(STATE / "request_ledger.json", authority)
    journal = AcquisitionJournal(STATE / "acquisition_journal.json")
    print(
        f"before: index {ledger.index_requests}/{ledger.max_index_requests}  "
        f"documents {ledger.document_requests}/{ledger.max_document_requests}"
    )

    fetcher = BoundedFetcher(authority, ledger, user_agent=USER_AGENT)
    resolved = None
    try:
        resolved = LocatorResolver(authority, fetcher, journal).resolve(
            candidate.cik, candidate.accession
        )
    except LocatorResolutionError as exc:
        print(f"\nDETERMINATE OUTCOME: {exc.reason}\n  {exc}", file=sys.stderr)
        print(f"  journal state: {journal.state_of(candidate.accession).value}")
        return 3
    except CrawlHalt as halt:
        print(f"\nHALT: {halt}", file=sys.stderr)
        return 4
    finally:
        fetcher.close()
        print(
            f"after : index {ledger.index_requests}/{ledger.max_index_requests}  "
            f"documents {ledger.document_requests}/{ledger.max_document_requests}"
        )

    eligible, reason = canary.screen(resolved.document_size)
    print()
    print(f"  primary document  {resolved.primary_document}")
    print(f"  declared type     {resolved.form}")
    print(f"  size              {resolved.document_size:,} bytes")
    print(f"  bound             {canary.CANARY_MAX_DOCUMENT_BYTES:,} (strict <)")
    print(f"  SCREEN            {'PASS' if eligible else 'FAIL'} -- {reason}")
    print(f"  locator url       {resolved.url}")
    print(f"  response sha256   {resolved.index_body_sha256}")
    print(f"  journal state     {journal.state_of(candidate.accession).value}")
    store = TransactionalEvidenceStore(STATE / "evidence")
    print(f"  reconcile         {reconcile(journal, store, authority.source_variant)}")
    print()
    print("STOP -- document request #1 is not authorized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
