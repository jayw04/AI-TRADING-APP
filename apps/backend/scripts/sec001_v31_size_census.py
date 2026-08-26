"""WP0A-Q-SIZE-CENSUS: deterministic, size-blind, index-only primary-document sizing.

⛔ **No document requests.** Every result is an ordinary ``LOCATOR_RESOLVED`` accession, so
nothing sampled here is consumed -- the census reuses the same journaled resolver the canary
uses, and each sampled accession keeps its locator and digest for later.

**Selection is deterministic and size-blind**, frozen before the first request: within each
form, candidates are ordered by ``sha256(accession)`` and the first N taken. Nothing about a
document's size can influence whether it is sampled, which is the whole point -- a census that
could see sizes while choosing would answer the wrong question.

The sample is a pure function of hash-verified authority data, so it is re-derivable by anyone
holding the same manifest/selection/envelope. Freezing it is therefore a *statement*, not a
trust boundary: ``--freeze-only`` writes the list and its digest before any request is made.

Run:
    python scripts/sec001_v31_size_census.py --freeze-only
    python scripts/sec001_v31_size_census.py
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from pathlib import Path

try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # pragma: no cover
    pass

from app.altdata.sec001_v31 import canary
from app.altdata.sec001_v31.authority import AcquisitionAuthority
from app.altdata.sec001_v31.custody import AcquisitionJournal, atomic_write_json
from app.altdata.sec001_v31.locator import LocatorResolutionError, LocatorResolver
from app.altdata.sec001_v31.transport import BoundedFetcher, CrawlHalt, DurableLedger

REPO = Path(__file__).resolve().parents[3]
STATE = REPO / "artifacts" / "wp0aq" / "state"
OUT = REPO / "artifacts" / "wp0aq" / "census"
USER_AGENT = "TradingWorkbench SEC001-V3 (GlobalComplyAI, LLC) jay.w0416@gmail.com"

#: The frozen sample shape.
QUOTA_10K = 16
QUOTA_10Q = 20
QUOTA_OTHER = 4

WINDOW = 983_040  # one bounded read
BANDS = [
    ("< 983,040  (1 read)", 0, WINDOW),
    ("983,040 - 1,966,080  (2 reads)", WINDOW, 2 * WINDOW),
    ("1,966,080 - 3,932,160  (4 reads)", 2 * WINDOW, 4 * WINDOW),
    ("3,932,160 - 7,864,320  (8 reads)", 4 * WINDOW, 8 * WINDOW),
    ("> 7,864,320", 8 * WINDOW, None),
]


def _rank(accession: str) -> str:
    return hashlib.sha256(accession.encode()).hexdigest()


def freeze_sample(authority: AcquisitionAuthority) -> list[dict[str, object]]:
    """Size-blind deterministic selection from the 433 non-bracket candidates."""
    pool = canary.candidate_order(authority)
    by_form: dict[str, list] = {}
    for c in pool:
        by_form.setdefault(c.form, []).append(c)
    for form in by_form:
        by_form[form].sort(key=lambda c: _rank(c.accession))

    chosen: list = []
    chosen += by_form.get("10-K", [])[:QUOTA_10K]
    chosen += by_form.get("10-Q", [])[:QUOTA_10Q]

    # "allocated across whatever permitted forms are actually present": round-robin over the
    # other forms in deterministic name order, so all present forms are represented.
    others = sorted(f for f in by_form if f not in ("10-K", "10-Q"))
    picked: list = []
    depth = 0
    while len(picked) < QUOTA_OTHER and others:
        progressed = False
        for form in others:
            if len(picked) >= QUOTA_OTHER:
                break
            if depth < len(by_form[form]):
                picked.append(by_form[form][depth])
                progressed = True
        if not progressed:
            break
        depth += 1
    chosen += picked

    return [
        {
            "cik": c.cik,
            "form": c.form,
            "accession": c.accession,
            "accepted_at": c.accepted_at,
            "selection_rank": _rank(c.accession),
        }
        for c in chosen
    ]


def write_freeze(authority: AcquisitionAuthority, sample: list[dict[str, object]]) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "WP0AQ_SIZE_CENSUS_SAMPLE_V1.json"
    body = {
        "artifact": "SEC001_V3_1_WP0AQ_SIZE_CENSUS_SAMPLE_V1",
        "authority": "WP0A-Q-SIZE-CENSUS (owner) -- index-only, no document requests",
        "frozen_before_first_request": True,
        "selection_rule": (
            "within each form, order the non-bracket Envelope-B candidates by "
            "sha256(accession) and take the first N. Size-blind and deterministic: "
            "re-derivable from the hash-verified authority alone."
        ),
        "quotas": {"10-K": QUOTA_10K, "10-Q": QUOTA_10Q, "other": QUOTA_OTHER},
        "manifest_sha256": authority.manifest_sha256,
        "envelope_sha256": authority.envelope_sha256,
        "selection_sha256": authority.selection_sha256,
        "sample_size": len(sample),
        "by_form": dict(sorted(Counter(str(s["form"]) for s in sample).items())),
        "sample": sample,
    }
    atomic_write_json(p, body)
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-only", action="store_true")
    args = ap.parse_args()

    authority = AcquisitionAuthority.load(REPO)
    sample = freeze_sample(authority)

    for s in sample:
        assert authority.is_authorized(
            int(str(s["cik"])), str(s["form"]), str(s["accession"]), str(s["accepted_at"])
        )
        assert s["accession"] not in authority.bracket_accessions

    p = write_freeze(authority, sample)
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    print(
        f"frozen sample: {len(sample)}  {dict(sorted(Counter(str(s['form']) for s in sample).items()))}"
    )
    print(f"  {p.name}  sha256 {digest}")

    canary_acc = "0001193125-21-050735"
    in_sample = any(s["accession"] == canary_acc for s in sample)
    print(f"  existing canary in the frozen sample: {in_sample}")

    if args.freeze_only:
        return 0

    ledger = DurableLedger.open(STATE / "request_ledger.json", authority)
    journal = AcquisitionJournal(STATE / "acquisition_journal.json")
    print(
        f"before: index {ledger.index_requests}/{ledger.max_index_requests}  documents {ledger.document_requests}"
    )

    fetcher = BoundedFetcher(authority, ledger, user_agent=USER_AGENT)
    rows: list[dict[str, object]] = []
    resolver = LocatorResolver(authority, fetcher, journal)
    try:
        for i, s in enumerate(sample, 1):
            acc = str(s["accession"])
            try:
                r = resolver.resolve(int(str(s["cik"])), acc)
                rows.append(
                    {
                        "cik": r.cik,
                        "form": r.form,
                        "accession": r.accession,
                        "accepted_at": r.accepted_at,
                        "primary_document": r.primary_document,
                        "declared_type": r.form,
                        "document_size": r.document_size,
                        "index_response_sha256": r.index_body_sha256,
                        "locator_state": journal.state_of(acc).value,
                    }
                )
                print(
                    f"  [{i:>2}/{len(sample)}] {r.form:<7} {acc}  {r.document_size:>10,}  {r.primary_document}"
                )
            except LocatorResolutionError as exc:
                rows.append(
                    {
                        "cik": s["cik"],
                        "form": s["form"],
                        "accession": acc,
                        "accepted_at": s["accepted_at"],
                        "primary_document": None,
                        "declared_type": None,
                        "document_size": None,
                        "index_response_sha256": None,
                        "locator_state": journal.state_of(acc).value,
                        "reason": exc.reason,
                    }
                )
                print(f"  [{i:>2}/{len(sample)}] {s['form']:<7} {acc}  DETERMINATE: {exc.reason}")
    except CrawlHalt as halt:
        print(f"HALT: {halt}", file=sys.stderr)
    finally:
        fetcher.close()
        print(
            f"after : index {ledger.index_requests}/{ledger.max_index_requests}  documents {ledger.document_requests}"
        )

    atomic_write_json(
        OUT / "WP0AQ_SIZE_CENSUS_RESULTS_V1.json",
        {
            "artifact": "SEC001_V3_1_WP0AQ_SIZE_CENSUS_RESULTS_V1",
            "sample_artifact_sha256": digest,
            "manifest_sha256": authority.manifest_sha256,
            "index_requests_after": ledger.index_requests,
            "document_requests": ledger.document_requests,
            "window_bytes": WINDOW,
            "rows": rows,
        },
    )
    print(f"\nwrote {(OUT / 'WP0AQ_SIZE_CENSUS_RESULTS_V1.json').name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
