"""WP0A-Q-LOCATOR-DISCOVERY: one authorized SEC request to establish the real schema.

Sequence, in this order and no other:

  1. load the hash-verified acquisition authority
  2. PROVE the frozen target is outside all 452 governed accessions
  3. freeze the target to disk BEFORE the request
  4. issue exactly ONE counted index request to the filing-detail page
  5. persist the raw response as evidence with its digest

Run:  python scripts/sec001_v31_locator_discovery.py
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # pragma: no cover
    pass

from app.altdata.sec001_v31 import discovery
from app.altdata.sec001_v31.authority import AcquisitionAuthority
from app.altdata.sec001_v31.canary import is_out_of_population
from app.altdata.sec001_v31.custody import atomic_write_json
from app.altdata.sec001_v31.transport import BoundedFetcher, DurableLedger

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "artifacts" / "wp0aq" / "discovery"
STATE = REPO / "artifacts" / "wp0aq" / "state"
USER_AGENT = "TradingWorkbench SEC001-V3 (GlobalComplyAI, LLC) jay.w0416@gmail.com"


def main() -> int:
    authority = AcquisitionAuthority.load(REPO)
    print(f"authority loaded: manifest {authority.manifest_sha256[:16]}… envelope B, 452 keys")

    cik = discovery.SCHEMA_DISCOVERY_CIK
    acc = discovery.SCHEMA_DISCOVERY_ACCESSION

    # ---- 2. the required proof, before anything is spent -------------------------
    proof = is_out_of_population(authority, acc)
    print(f"is_out_of_population({acc}) = {proof}")
    if not proof:
        print("REFUSING: target is inside Envelope B", file=sys.stderr)
        return 2
    assert cik not in {k[0] for k in authority.ordered_keys}, "CIK is in the population"
    assert acc not in authority.bracket_accessions
    print("  target is outside all 452 governed accessions, and outside the 22-CIK population")

    # ---- 3. freeze the target BEFORE the request ---------------------------------
    OUT.mkdir(parents=True, exist_ok=True)
    frozen = OUT / "WP0AQ_LOCATOR_DISCOVERY_TARGET.json"
    if not frozen.exists():
        atomic_write_json(
            frozen,
            {
                "artifact": "SEC001_V3_1_WP0AQ_LOCATOR_DISCOVERY_TARGET",
                "authority": "WP0A-Q-LOCATOR-DISCOVERY (owner) -- exactly 1 request",
                "frozen_before_request": True,
                "cik": cik,
                "form": discovery.SCHEMA_DISCOVERY_FORM,
                "accession": acc,
                "representation": "filing-detail ...-index.html (NOT accession-directory index.json)",
                "out_of_population_proof": proof,
                "confers_no_form_scope": discovery.DISCOVERY_CONFERS_NO_FORM_SCOPE,
                "manifest_sha256": authority.manifest_sha256,
            },
        )
        print(f"target frozen -> {frozen.name}")

    # ---- 4/5. one counted request, response persisted as evidence -----------------
    ledger = DurableLedger.open(STATE / "request_ledger.json", authority)
    print(
        f"ledger before: index {ledger.index_requests}/{ledger.max_index_requests} "
        f"documents {ledger.document_requests}/{ledger.max_document_requests}"
    )

    fetcher = BoundedFetcher(authority, ledger, user_agent=USER_AGENT)
    try:
        ev = discovery.run_discovery(authority, fetcher, OUT, cik=cik, accession=acc)
    finally:
        fetcher.close()
        print(
            f"ledger after : index {ledger.index_requests}/{ledger.max_index_requests} "
            f"documents {ledger.document_requests}/{ledger.max_document_requests}"
        )

    print()
    print(f"  url        {ev.url}")
    print(f"  status     {ev.http_status}")
    print(f"  bytes      {ev.byte_length}")
    print(f"  eof        {ev.eof_reached}  truncated {ev.truncated}")
    print(f"  sha256     {ev.sha256}")
    print(f"  raw        {ev.raw_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
