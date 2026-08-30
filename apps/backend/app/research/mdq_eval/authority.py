"""Frozen governance authority for evidentiary K evaluation.

Every value here is a **frozen constant read from a governed record**. Nothing in this
module may be supplied, widened, or overridden by a caller, a CLI flag, or an environment
variable. That is the whole point: the original defect was that
``mdq_evaluate_k.py`` passed no approved collector identity at all, so
``collector_code_identity`` came back ``NOT_EVALUABLE`` and every session was excluded —
and the only offered remedy was an operator-supplied ``--approved-collector-version``,
which would have let the operator define the authority they were being checked against.

⛔ Do not add a function that merges caller input into any constant below.

Two claims are kept deliberately separate, because the evidence for them is different:

``B1a`` **manifest-native identity** — what a frozen partition can itself mechanically
prove. The manifest records ``collector_version`` plus the provenance fields the collector
actually wrote. Those are checkable against this authority.

``B1b`` **implementation invariance** — the measured fact that the five governed collector
blobs are byte-identical across the repository identities named below. This is real
evidence and it is useful, but it is *not* a per-partition binding.

⚠ The distinction is load-bearing. The frozen manifests do **not** record a source commit
or the collector blob hashes (``CaptureStore.freeze`` writes ``collector_version`` and a
caller-supplied provenance dict; the ``files[].sha256`` entries hash the *captured data*,
not the collector source). So for the already-admitted partitions a full per-partition
source tuple **cannot be reconstructed** — the information was never written. Claiming
otherwise would convert measured invariance into fictitious provenance, which is exactly
the overclaim this split exists to prevent.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

#: Bumped when the *meaning* of the authority changes, never for cosmetic edits.
AUTHORITY_SCHEMA: Final = "mdq-k-authority/1"

#: The governing record these constants are transcribed from.
GOVERNING_ARTIFACT: Final = "docs/design/MDQ-001_Collector_Identity_Approval_2026-08-19.md"

# --- B1a: manifest-native authority -----------------------------------------------------

#: The only collector version an evidentiary evaluation will accept.
#: ⚠ The governing record is explicit that the bare string is NOT sufficient on its own —
#: "it can be reused accidentally by a later build". It is retained here because it is the
#: single identity field the frozen manifests actually carry; the stronger tuple below is
#: recorded separately and must never be presented as if the manifest proved it.
APPROVED_COLLECTOR_VERSIONS: Final[tuple[str, ...]] = ("mdq-collector/0.1.0",)

#: Provenance keys the collector demonstrably wrote into every governed manifest. A
#: governed evaluation requires these to be present; absence is a manifest-native failure,
#: not something to be inferred around.
REQUIRED_PROVENANCE_KEYS: Final[tuple[str, ...]] = (
    "provider",
    "entitlement",
    "credential_fingerprint",
    "account_number",
    "capture_modes",
    "universe",
    "universe_sha256",
)

#: Provenance values that are themselves frozen, so a mismatch is a hard failure rather
#: than a recorded observation.
FROZEN_PROVENANCE: Final[Mapping[str, str]] = MappingProxyType({"provider": "alpaca"})

#: ⛔ A partition carrying this label is quarantined from the governed K corpus
#: (registration §4: thresholds freeze BEFORE collection).
QUARANTINE_LABEL: Final = "PRE_REGISTRATION_SMOKE"

# --- B1b: implementation invariance (SEPARATE claim) -------------------------------------

#: The approved collector source commit, per the governing record.
APPROVED_COLLECTOR_SOURCE_COMMIT: Final = "86d8cbd5a6201a8938062c35f915604b08652fbe"

#: The five governed collector files and their approved LF-normalised blob SHA-256.
#: Paths are relative to ``apps/backend/``. The LF rule is part of the identity, not a
#: footnote: ``.gitattributes`` does not pin ``*.py`` to ``eol=lf``, so deployed files are
#: CRLF on disk and a raw ``sha256sum`` in the container will NOT match. Canonical form is
#: the raw git blob.
APPROVED_COLLECTOR_BLOBS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "app/research/capture/__init__.py": "f38fbd649430ce17e507920aab0c9ed284207b096688d1eed7b5f4fadf142fba",
        "app/research/capture/collector.py": "e5e030a97eed0a64d4abeb621484e8069dd152dde27ccf75f254f9a1286ebd97",
        "app/research/capture/identity.py": "588e258f4b6ee6b88f250c6ec77100e7dc2a8690f1502ca1567de11f452b63d8",
        "app/research/capture/store.py": "22c3405e5acbba6c7a86ef71468898ec0515126399770b02dfb42373f211e222",
        "scripts/mdq_collector.py": "b5feb2a9c84521c1a624d4436577dcc093f2451c13dd17dda8ca1a52261ab7e2",
    }
)

#: Repository identities across which the five blobs above were **measured** byte-identical
#: (2026-08-29). These span every runtime live during the 08-19..08-28 capture window.
#: ⚠ This establishes that the collector implementation did not change across these named
#: revisions. It does NOT establish which revision produced any particular partition.
INVARIANCE_MEASURED_IDENTITIES: Final[tuple[str, ...]] = (
    "86d8cbd5a6201a8938062c35f915604b08652fbe",
    "956e932c8860602060b627b9c8f7966d31565337",
    "3f32c75b1053f8181f98ddf51bbc473364ffd34c",
)

#: Status recorded whenever a per-partition full source tuple is requested. It is never
#: True for the historical corpus, because the manifests never carried the binding.
HISTORICAL_BINDING_UNAVAILABLE: Final = "HISTORICAL_BINDING_UNAVAILABLE"


@dataclass(frozen=True)
class ApprovedCollectorIdentity:
    """The full governed collector tuple, canonicalised.

    ``digest`` is a compact citation label for the tuple. ⛔ It is **not** the comparison:
    comparisons are made field by field against the frozen constants, so a future change
    that happened to collide on a digest could not pass.
    """

    version: str
    source_commit: str
    blobs: Mapping[str, str]

    def canonical(self) -> str:
        return json.dumps(
            {
                "schema": AUTHORITY_SCHEMA,
                "version": self.version,
                "source_commit": self.source_commit,
                "blobs": dict(sorted(self.blobs.items())),
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical().encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "source_commit": self.source_commit,
            "blobs": dict(sorted(self.blobs.items())),
            "canonical_digest": self.digest,
            "governing_artifact": GOVERNING_ARTIFACT,
        }


#: The single approved identity. Module-level and frozen; there is no constructor taking
#: caller input, and no registry to extend.
APPROVED_COLLECTOR_IDENTITY: Final = ApprovedCollectorIdentity(
    version=APPROVED_COLLECTOR_VERSIONS[0],
    source_commit=APPROVED_COLLECTOR_SOURCE_COMMIT,
    blobs=APPROVED_COLLECTOR_BLOBS,
)


def invariance_record() -> dict[str, object]:
    """The B1b claim, in the words it is allowed to be stated in.

    ⛔ Never name this ``partition_collector_identity``. It is evidence about repository
    revisions, not about which revision produced a partition.
    """
    return {
        "claim": "collector_implementation_invariance",
        "statement": (
            "The five governed collector blobs were measured byte-identical across the "
            "repository identities listed, for the approved collector file set."
        ),
        "measured_identities": list(INVARIANCE_MEASURED_IDENTITIES),
        "blobs": dict(sorted(APPROVED_COLLECTOR_BLOBS.items())),
        "does_not_establish": (
            "which repository identity produced any particular frozen partition; the "
            "manifests do not record a source commit or collector blob hashes"
        ),
    }
