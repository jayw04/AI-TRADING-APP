"""The frozen acquisition authority, loaded from governed artifacts rather than configured.

Review finding (P0): the harness previously took ``permitted_forms``, ``cutoff_utc``, caps,
byte limits, rate and retry behaviour as *constructor options*, and fetched whatever URL the
caller passed. It therefore checked values the caller supplied and proved nothing about the
sealed authority. A caller could construct a different policy and fetch outside Envelope B.

This module closes that. It re-hashes all three governed artifacts and derives every frozen
parameter from them, so the chain

    manifest 3a30ad02...  ->  selection 2b6839e3...  ->  envelope f10c1ad1...
        ->  this accession is one of the 452 authorized requests

is verified in code before anything can be fetched. Nothing here is overridable: the
constructor is private-by-convention and every value comes out of a hash-verified file.

``authorized_keys`` is the decisive object — an immutable set of the exact
``(cik, form, accession, accepted_at)`` tuples the owner selected. A filing not *exactly* in
that set is refused before any network call, no matter how plausible it looks.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final
from urllib.parse import urlparse

from app.altdata.sec001_v31.clock import accepted_at_utc

#: Governance identities. A mismatch is fatal: these are the bytes the owner ruled on.
MANIFEST_SHA256: Final = "3a30ad0296aa945f6b7a68c2bf578e47c69f75267670c2e3d0e72d4473339724"
SELECTION_SHA256: Final = "2b6839e36be1234dab67d8c191b1b250440b953c8b56ec259b6206c49b8b66ed"
ENVELOPE_SHA256: Final = "f10c1ad17589e5a8bec044d7aa5c1df2e0f752c37c6e75b9ed80ba044eece515"

MANIFEST_PATH: Final = Path("manifests/wp0aq/WP0AQ_COVER_PREACQUISITION_MANIFEST_V1.json")
SELECTION_PATH: Final = Path("artifacts/wp0aq/WP0AQ_COVER_ENVELOPE_SELECTION_V1.json")
ENVELOPE_PATH: Final = Path("artifacts/wp0aq/WP0AQ_COVER_ENVELOPE_V1.json")

#: Step-1 custody: the index requests already spent deriving the envelope. A restart must
#: not silently reset these to zero -- see ``transport.DurableLedger``.
STEP1_INDEX_REQUESTS_SPENT: Final = 28
STEP1_DOCUMENT_REQUESTS_SPENT: Final = 0

#: Live-authorized continuation policy. The owner ruled that any nonzero value must be
#: prospectively frozen *before* request #1, never chosen after seeing which real filings
#: exceed the first window.
LIVE_MAX_CONTINUATIONS: Final = 0


class AuthorityError(RuntimeError):
    """A governed artifact failed verification, or the chain between them is broken."""


class NotAuthorized(RuntimeError):
    """A filing is not in the frozen authorized set, or a URL is not the canonical one."""


#: A primary-document name must be a plain basename. Anything that could redirect the
#: request to another path -- separators, traversal, a query or a fragment -- is refused.
_UNSAFE_DOCUMENT_CHARS: Final = ("/", "\\", "?", "#", ":")


def require_safe_document_name(name: str) -> str:
    """Constrain a primary-document name to a basename in the accession's own directory."""
    if not name or name in (".", ".."):
        raise NotAuthorized(f"primary document name {name!r} is not a file name")
    if any(c in name for c in _UNSAFE_DOCUMENT_CHARS) or ".." in name:
        raise NotAuthorized(
            f"primary document name {name!r} is not a plain basename; path separators, "
            "traversal, query and fragment are all refused"
        )
    return name


AuthorizedKey = tuple[int, str, str, str]  # (cik, form, accession, accepted_at)


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@dataclass(frozen=True)
class AcquisitionAuthority:
    """Every frozen parameter, derived from hash-verified governed artifacts."""

    manifest_sha256: str
    selection_sha256: str
    envelope_sha256: str
    selected_envelope: str
    permitted_forms: frozenset[str]
    deferred_forms: frozenset[str]
    cutoff_utc: datetime
    domains: tuple[str, ...]
    allowed_origins: frozenset[str]
    max_index_requests: int
    max_document_requests: int
    max_total_retries: int
    retry_max_attempts: int
    retry_statuses: tuple[int, ...]
    halt_statuses: tuple[int, ...]
    rate_limit_per_sec: float
    ceiling_bytes: int
    stop_threshold_bytes: int
    retained_field_schema: tuple[str, ...]
    authorized_keys: frozenset[AuthorizedKey]
    source_variant: str = "PRIMARY_DOCUMENT_COVER"
    _by_accession: Any = field(default=None, repr=False, compare=False)

    # ---------------------------------------------------------------- loading
    @classmethod
    def load(cls, repo_root: Path) -> AcquisitionAuthority:
        man_p, sel_p, env_p = (
            repo_root / MANIFEST_PATH,
            repo_root / SELECTION_PATH,
            repo_root / ENVELOPE_PATH,
        )
        for p, expected, label in (
            (man_p, MANIFEST_SHA256, "manifest"),
            (sel_p, SELECTION_SHA256, "selection record"),
            (env_p, ENVELOPE_SHA256, "envelope"),
        ):
            if not p.exists():
                raise AuthorityError(f"{label} missing at {p}")
            got = _sha256(p)
            if got != expected:
                raise AuthorityError(f"{label} sha256 mismatch: expected {expected}, got {got}")

        man = json.loads(man_p.read_text(encoding="utf-8"))
        sel = json.loads(sel_p.read_text(encoding="utf-8"))
        env = json.loads(env_p.read_text(encoding="utf-8"))

        # ---- the chain, verified rather than assumed -------------------------------
        if sel["parent_manifest"]["sha256"] != MANIFEST_SHA256:
            raise AuthorityError("selection record does not descend from the sealed manifest")
        if sel["envelope_artifact"]["sha256"] != ENVELOPE_SHA256:
            raise AuthorityError("selection record does not point at this envelope")
        if env["manifest_sha256"] != MANIFEST_SHA256:
            raise AuthorityError("envelope does not descend from the sealed manifest")

        chosen = sel["selected_envelope"]
        keys_field = {"A": "acquisition_keys_envelope_A", "B": "acquisition_keys_envelope_B"}.get(
            chosen
        )
        if keys_field is None:
            raise AuthorityError(f"selection names an unknown envelope {chosen!r}")
        rows = env[keys_field]
        if len(rows) != sel["selected_total_eligible_accessions"]:
            raise AuthorityError(
                f"selected envelope size {sel['selected_total_eligible_accessions']} != "
                f"{len(rows)} keys present in the envelope"
            )

        permitted = frozenset(man["permitted_forms"])
        cutoff = datetime.fromisoformat(man["WP0A_Q_EVIDENCE_CUTOFF_UTC"].replace("Z", "+00:00"))

        keys: set[AuthorizedKey] = set()
        by_accession: dict[str, AuthorizedKey] = {}
        for r in rows:
            if set(r) != {"cik", "form", "accession", "accepted_at"}:
                raise AuthorityError(f"envelope key carries unexpected fields: {sorted(r)}")
            if r["form"] not in permitted:
                raise AuthorityError(f"envelope contains non-permitted form {r['form']!r}")
            if accepted_at_utc(r["accepted_at"]) > cutoff:
                raise AuthorityError(f"envelope contains a post-cutoff filing {r['accession']}")
            k: AuthorizedKey = (int(r["cik"]), r["form"], r["accession"], r["accepted_at"])
            keys.add(k)
            by_accession[r["accession"]] = k
        if len(keys) != len(rows):
            raise AuthorityError("envelope contains duplicate authorized keys")

        acq = man["acquisition"]
        domains = tuple(acq["domains"])
        origins = frozenset(f"{urlparse(d).scheme}://{urlparse(d).netloc}" for d in domains)

        return cls(
            manifest_sha256=MANIFEST_SHA256,
            selection_sha256=SELECTION_SHA256,
            envelope_sha256=ENVELOPE_SHA256,
            selected_envelope=chosen,
            permitted_forms=permitted,
            deferred_forms=frozenset(man["explicitly_deferred_forms"]),
            cutoff_utc=cutoff,
            domains=domains,
            allowed_origins=origins,
            max_index_requests=int(acq["max_index_requests"]),
            max_document_requests=int(acq["max_document_requests"]),
            max_total_retries=int(acq["max_total_retries"]),
            retry_max_attempts=int(acq["retry_max_attempts"]),
            retry_statuses=tuple(acq["retry_statuses"]),
            halt_statuses=tuple(acq["halt_statuses"]),
            rate_limit_per_sec=float(acq["rate_limit_per_sec"]),
            ceiling_bytes=int(acq["response_consumption_ceiling_bytes"]),
            stop_threshold_bytes=int(acq["consumption_stop_threshold_bytes"]),
            retained_field_schema=tuple(man["retained_field_schema"]),
            authorized_keys=frozenset(keys),
            _by_accession=MappingProxyType(by_accession),
        )

    # ---------------------------------------------------------------- checks
    def is_authorized(self, cik: int, form: str, accession: str, accepted_at: str) -> bool:
        return (cik, form, accession, accepted_at) in self.authorized_keys

    def require_authorized(self, cik: int, form: str, accession: str, accepted_at: str) -> None:
        if not self.is_authorized(cik, form, accession, accepted_at):
            raise NotAuthorized(
                f"({cik}, {form}, {accession}, {accepted_at}) is not one of the "
                f"{len(self.authorized_keys)} authorized Envelope-{self.selected_envelope} requests"
            )

    def origin_allowed(self, url: str) -> bool:
        u = urlparse(url)
        return f"{u.scheme}://{u.netloc}" in self.allowed_origins

    def require_origin(self, url: str) -> None:
        if not self.origin_allowed(url):
            raise NotAuthorized(
                f"{url!r} is outside the frozen SEC origins {sorted(self.allowed_origins)}"
            )

    def archive_url(self, cik: int, accession: str, primary_document: str) -> str:
        """Build the CANONICAL EDGAR archive URL from *governed* identifiers.

        Derived here rather than accepted from a caller, and authenticated on every
        component: the accession must be in the envelope, the supplied CIK must be the one
        the envelope associates with that accession, and the document name must be a plain
        basename. Checking merely that the accession appears *somewhere* in a URL was not
        enough -- it admitted a path under the wrong registrant, and it admitted traversal.
        """
        key = self.require_authorized_accession(accession)
        if key[0] != cik:
            raise NotAuthorized(
                f"accession {accession} is authorized under CIK {key[0]}, not {cik}"
            )
        doc = require_safe_document_name(primary_document)
        nodash = accession.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/{doc}"
        self.require_origin(url)
        return url

    def require_authorized_accession(self, accession: str) -> AuthorizedKey:
        k = self._by_accession.get(accession) if self._by_accession else None
        if k is None:
            raise NotAuthorized(f"accession {accession} is not in the authorized envelope")
        return k

    def require_canonical_url(
        self, cik: int, accession: str, primary_document: str, url: str
    ) -> None:
        """The locator URL must be byte-identical to the canonical derivation."""
        canonical = self.archive_url(cik, accession, primary_document)
        if url != canonical:
            raise NotAuthorized(
                "locator URL is not the canonical archive URL for this filing; "
                f"given {url!r}, canonical {canonical!r}"
            )
