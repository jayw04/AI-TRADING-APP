"""Shared harness wiring for the WP0A-Q tests.

Builds a real ``AcquisitionAuthority`` from the actual governed artifacts in the repository,
so the tests exercise the same authority-loading path production would.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.altdata.sec001_v31.authority import AcquisitionAuthority
from app.altdata.sec001_v31.custody import AcquisitionJournal, TransactionalEvidenceStore
from app.altdata.sec001_v31.transport import BoundedFetcher, DurableLedger

REPO_ROOT = Path(__file__).resolve().parents[5]
USER_AGENT = "TradingWorkbench SEC001-V3 (GlobalComplyAI, LLC) jay.w0416@gmail.com"


@pytest.fixture(scope="session")
def authority() -> AcquisitionAuthority:
    return AcquisitionAuthority.load(REPO_ROOT)


@pytest.fixture(scope="session")
def envelope_keys(authority: AcquisitionAuthority) -> list[tuple[int, str, str, str]]:
    """The authorized keys, deterministically ordered so tests can pick a real one."""
    return sorted(authority.authorized_keys)


@pytest.fixture
def ledger(tmp_path: Path, authority: AcquisitionAuthority) -> DurableLedger:
    return DurableLedger.open(tmp_path / "ledger.json", authority)


@pytest.fixture
def store(tmp_path: Path) -> TransactionalEvidenceStore:
    return TransactionalEvidenceStore(tmp_path / "evidence")


@pytest.fixture
def journal(tmp_path: Path) -> AcquisitionJournal:
    return AcquisitionJournal(tmp_path / "journal.json")


def make_fetcher(authority, ledger, handler, *, max_redirects: int = 0) -> BoundedFetcher:
    return BoundedFetcher(
        authority,
        ledger,
        user_agent=USER_AGENT,
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
        sleep=lambda _s: None,
        max_redirects=max_redirects,
    )


def ranged_response(body: bytes, request: httpx.Request, *, total: int | None = None):
    """A well-behaved byte-range reply honouring the requested window."""
    rng = request.headers.get("Range", "bytes=0-")
    start, _, end_s = rng.removeprefix("bytes=").partition("-")
    start_i = int(start)
    total_i = total if total is not None else len(body)
    end_i = min(int(end_s) if end_s else total_i - 1, total_i - 1)
    chunk = body[start_i : end_i + 1]
    return httpx.Response(
        206,
        content=chunk,
        headers={"Content-Range": f"bytes {start_i}-{start_i + len(chunk) - 1}/{total_i}"},
    )


def read_committed(
    store: TransactionalEvidenceStore, cik: int, accession: str, variant: str
) -> dict:
    return json.loads(store.path_for(cik, accession, variant).read_text(encoding="utf-8"))
