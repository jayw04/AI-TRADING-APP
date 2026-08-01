"""Governed corpora as an immutable base plus ordered, countersigned deltas (ADR 0048).

A forward-validation session must evaluate against data whose coverage reaches that session, and must
record immutably which data it used. Those two requirements pull against each other under a
whole-file countersignature: coverage has to advance daily, but the countersigned identity may not
drift. ADR 0048 resolves it by fixing an immutable base and extending it with append-only, ordered,
individually hashed deltas.

## Two identities, and why neither substitutes for the other

  * ``corpus_manifest_sha256`` — computed here — is the identity of the AUTHORIZED CONSTRUCTION: base
    identity, every ordered delta, the governing universe, and ACTIONS provenance. It proves *which
    governed construction the deployment was permitted to assemble*.

  * ``store_identity_sha256`` — computed in :mod:`app.validation.data_finality`, NOT here — is a
    streaming value-level digest of the rows a session actually consumed, re-verified after the reads
    by ``verify_store_unchanged``. It proves *the consumed dataset did not move during execution*.

They fail differently. A deployment that assembles the authorized construction and then reads against
a store mutating underneath it satisfies the first and violates the second; a deployment reading a
stable but unauthorized store does the reverse. Collapsing them leaves one of those two failures
undetectable, so this module computes the construction identity and **deliberately does not touch the
value-level digest, its timing, or its calculation**.

## Corrections are not deltas

A delta may only extend coverage forward. A "delta" landing on or before the base cutoff is refused
here rather than applied, because that is a historical amendment, and ADR 0048 (4) routes those to a
separately documented repair producing a new corpus version. The cost asymmetry is the design:
extending is cheap, amending is expensive and visible.

## Contiguity has two shapes

A session corpus is contiguous against the governed trading calendar — the caller supplies the
expected sessions, because the authoritative calendar lives in :mod:`app.validation.eval_calendar`
and this module stays free of that dependency so the contract is testable without it. A rate series
is contiguous against its own coverage: each extension resumes exactly where the previous one
stopped. Both are exact-match rules; neither tolerates a gap, a repeat, or a reordering.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.validation.forward_window import IntegrityStop
from app.validation.security_lineage import SECURITY_IDENTITY_CONTRACT

_HEX = frozenset("0123456789abcdef")

#: The governing universe the base corpus is bound to. A universe change is a new base, never a delta.
GOVERNED_UNIVERSE_SIZE = 14_150


class CorpusConstructionError(IntegrityStop):
    """The governed construction could not be established. Fails closed — no session runs."""


class DeltaChainError(CorpusConstructionError):
    """The delta chain is missing, duplicated, out of order, future-dated, unhashed, or bound to a
    different universe."""


class HistoricalAmendmentRefused(CorpusConstructionError):
    """A delta would have modified coverage at or before the base cutoff. Historical corrections
    require a new corpus version and its own countersignature (ADR 0048 (4)), never a delta."""


class FrozenArtifactDrift(CorpusConstructionError):
    """An artifact frozen by the countersigned preregistration does not hash to its pinned value."""


class ManifestIdentityConflict(CorpusConstructionError):
    """A declared identity and the identity computed from the artifacts disagree, or a required
    identity is absent."""


class Contiguity(StrEnum):
    """How a chain proves it has no holes."""
    SESSION_CALENDAR = "SESSION_CALENDAR"        # exact match against the governed trading sessions
    COVERAGE_CONTIGUOUS = "COVERAGE_CONTIGUOUS"  # each extension resumes where the previous stopped


def canonical_json(payload: Any) -> bytes:
    """Deterministic serialization. Sorted keys, no insignificant whitespace, dates as ISO strings.

    Every identity in this module is a digest over this encoding, so two deployments that assembled
    the same construction produce the same identity byte-for-byte.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str).encode("utf-8")


def _is_sha256(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and set(text) <= _HEX


def _require_sha256(value: Any, *, what: str) -> str:
    text = str(value or "").strip().lower()
    if not _is_sha256(text):
        raise DeltaChainError(f"{what} is not a sha256 digest ({value!r}); an unhashed artifact "
                              f"cannot enter a governed construction")
    return text


def file_sha256(path: Path, *, chunk: int = 1 << 20) -> str:
    """SHA-256 of a file's bytes, streamed."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


@dataclass(frozen=True)
class GovernedDelta:
    """One append-only extension. Session-bounded, hashed, and bound to the governing universe.

    ``coverage_through`` is recorded separately from ``session_date`` because they answer different
    questions: the session this delta belongs to, and the last date whose rows it carries. A delta
    whose coverage runs past its own session is future-dated and refused.
    """
    session_date: date
    coverage_through: date
    sha256: str                     # the delta artifact itself
    source_sha256: str              # the upstream source artifact it was ingested from
    rows: int
    retrieved_at: str               # ISO-8601 UTC, when the source was pulled
    countersignature: str           # reference to the countersigned delta manifest record
    # Bound to the base's governing universe. A rate series has no universe, so this is None there
    # rather than a placeholder digest that would look like a real binding in the identity payload.
    universe_sha256: str | None = None
    exclusions: tuple[str, ...] = ()

    def identity_payload(self) -> dict[str, Any]:
        return {
            "session_date": self.session_date.isoformat(),
            "coverage_through": self.coverage_through.isoformat(),
            "sha256": self.sha256,
            "source_sha256": self.source_sha256,
            "universe_sha256": self.universe_sha256,
            "rows": self.rows,
            "retrieved_at": self.retrieved_at,
            "countersignature": self.countersignature,
            "exclusions": list(self.exclusions),
        }

    @staticmethod
    def from_payload(payload: Any, *, index: int, require_universe: bool = True) -> GovernedDelta:
        if not isinstance(payload, dict):
            raise DeltaChainError(f"delta {index} is not an object")
        try:
            session_date = date.fromisoformat(str(payload["session_date"]))
            coverage_through = date.fromisoformat(str(payload["coverage_through"]))
        except (KeyError, ValueError) as exc:
            raise DeltaChainError(f"delta {index} has no valid session_date/coverage_through: "
                                  f"{exc}") from exc
        rows = payload.get("rows")
        if not isinstance(rows, int) or isinstance(rows, bool) or rows < 0:
            raise DeltaChainError(f"delta {index} ({session_date}) records rows={rows!r}; a governed "
                                  f"delta must record a non-negative integer row count")
        retrieved_at = str(payload.get("retrieved_at", "")).strip()
        if not retrieved_at:
            raise DeltaChainError(f"delta {index} ({session_date}) records no retrieval timestamp")
        countersignature = str(payload.get("countersignature", "")).strip()
        if not countersignature:
            raise DeltaChainError(
                f"delta {index} ({session_date}) carries no countersignature reference; an "
                f"unattested delta cannot enter a governed construction")
        exclusions = payload.get("exclusions", [])
        if not isinstance(exclusions, list):
            raise DeltaChainError(f"delta {index} ({session_date}) records exclusions as "
                                  f"{type(exclusions).__name__}, not a list")
        return GovernedDelta(
            session_date=session_date,
            coverage_through=coverage_through,
            sha256=_require_sha256(payload.get("sha256"), what=f"delta {index} ({session_date})"),
            source_sha256=_require_sha256(payload.get("source_sha256"),
                                          what=f"delta {index} ({session_date}) source"),
            universe_sha256=(_require_sha256(payload.get("universe_sha256"),
                                             what=f"delta {index} ({session_date}) universe")
                             if require_universe else None),
            rows=rows,
            retrieved_at=retrieved_at,
            countersignature=countersignature,
            exclusions=tuple(str(x) for x in exclusions),
        )


def validate_delta_chain(
    *,
    base_coverage_through: date,
    base_universe_sha256: str | None,
    deltas: tuple[GovernedDelta, ...],
    observation_session: date,
    contiguity: Contiguity,
    expected_sessions: tuple[date, ...] | None = None,
) -> None:
    """Refuse a chain that is missing, duplicated, out of order, future-dated, unhashed, amending
    history, or bound to a different universe. Returns None; raises on any violation.

    ``expected_sessions`` is required for :attr:`Contiguity.SESSION_CALENDAR` and must be the ordered
    governed sessions strictly after ``base_coverage_through`` through ``observation_session``. It is
    supplied by the caller so that the authoritative calendar stays in one module.
    """
    previous_coverage = base_coverage_through
    seen: set[date] = set()

    for index, delta in enumerate(deltas):
        # history is never rewritten through this path
        if delta.session_date <= base_coverage_through:
            raise HistoricalAmendmentRefused(
                f"delta {index} is dated {delta.session_date}, at or before the base cutoff "
                f"{base_coverage_through}; that is a historical correction, which requires a new "
                f"corpus version and its own countersignature, not a delta")
        # no duplicates, no reordering — a strictly increasing sequence excludes both
        if delta.session_date in seen:
            raise DeltaChainError(
                f"delta {index} repeats session {delta.session_date}; a session is recorded once")
        if index > 0 and delta.session_date <= deltas[index - 1].session_date:
            raise DeltaChainError(
                f"delta {index} ({delta.session_date}) does not follow delta {index - 1} "
                f"({deltas[index - 1].session_date}); the chain must be strictly increasing")
        seen.add(delta.session_date)
        # nothing may reach past the session being observed
        if delta.session_date > observation_session:
            raise DeltaChainError(
                f"delta {index} is dated {delta.session_date}, after the observed session "
                f"{observation_session}; a session may not consume future data")
        if delta.coverage_through > delta.session_date:
            raise DeltaChainError(
                f"delta {index} ({delta.session_date}) carries coverage through "
                f"{delta.coverage_through}, past its own session; the delta is future-dated")
        # the universe is the base's universe, exactly (rate series carry no universe: None skips)
        if base_universe_sha256 is not None and delta.universe_sha256 != base_universe_sha256:
            raise DeltaChainError(
                f"delta {index} ({delta.session_date}) is bound to universe "
                f"{str(delta.universe_sha256)[:16]}… but the base is bound to "
                f"{base_universe_sha256[:16]}…; a universe change is a new base, not a delta")

        if contiguity is Contiguity.COVERAGE_CONTIGUOUS:
            if delta.coverage_through <= previous_coverage:
                raise DeltaChainError(
                    f"delta {index} ends at {delta.coverage_through}, at or before the previous "
                    f"coverage {previous_coverage}; extensions must advance coverage")
            previous_coverage = delta.coverage_through

    if contiguity is Contiguity.SESSION_CALENDAR:
        if expected_sessions is None:
            raise DeltaChainError(
                "session-calendar contiguity was requested without the governed session list; the "
                "chain cannot be proven gap-free against a calendar that was not supplied")
        actual = tuple(d.session_date for d in deltas)
        if actual != tuple(expected_sessions):
            missing = sorted(set(expected_sessions) - set(actual))
            extra = sorted(set(actual) - set(expected_sessions))
            detail = []
            if missing:
                detail.append(f"missing {[d.isoformat() for d in missing]}")
            if extra:
                detail.append(f"unexpected {[d.isoformat() for d in extra]}")
            if not detail:
                detail.append("same sessions in a different order")
            raise DeltaChainError(
                f"the delta chain does not match the governed sessions through "
                f"{observation_session}: {'; '.join(detail)}")


@dataclass(frozen=True)
class CorpusManifest:
    """The authorized construction of the governing SEP/ACTIONS/TICKERS corpus for one observation.

    TICKERS joined the bound construction on 2026-07-29, by owner ruling. It is not reference trivia:
    `universe_asof` cannot resolve an eligible universe without current effective security metadata,
    so two materially different constructions — one with a stale TICKERS that yields an EMPTY universe,
    one with a current TICKERS that yields 500 names — would otherwise share the same authorized
    identity. `security_identity_contract` is bound for the same reason one step further out: it pins
    the RULE by which those rows are interpreted, so a later resolver change cannot silently
    reinterpret identical artifacts.
    """
    base_corpus_sha256: str
    base_coverage_through: date
    governed_universe_sha256: str
    governed_universe_size: int
    actions_manifest_sha256: str
    actions_authoritative: bool
    # Embedded rather than referenced by digest: a separate file would have to be declared somewhere
    # and then checked against, which is one more place for a manifest to name an artifact it did not
    # actually assemble. Embedding makes `tickers_manifest_sha256` a COMPUTED identity, exactly like
    # `corpus_manifest_sha256`, so there is no declared-vs-actual gap to police.
    tickers: TickersManifest
    tickers_authoritative: bool
    security_identity_contract: str
    deltas: tuple[GovernedDelta, ...]
    base_countersignature: str

    @property
    def tickers_manifest_sha256(self) -> str:
        return self.tickers.tickers_manifest_sha256

    def identity_payload(self) -> dict[str, Any]:
        return {
            "kind": "governed_corpus",
            "base_corpus_sha256": self.base_corpus_sha256,
            "base_coverage_through": self.base_coverage_through.isoformat(),
            "base_countersignature": self.base_countersignature,
            "governed_universe_sha256": self.governed_universe_sha256,
            "governed_universe_size": self.governed_universe_size,
            "actions_manifest_sha256": self.actions_manifest_sha256,
            "actions_authoritative": self.actions_authoritative,
            "tickers": self.tickers.identity_payload(),
            "tickers_manifest_sha256": self.tickers_manifest_sha256,
            "tickers_authoritative": self.tickers_authoritative,
            "security_identity_contract": self.security_identity_contract,
            "deltas": [d.identity_payload() for d in self.deltas],
        }

    @property
    def corpus_manifest_sha256(self) -> str:
        """The construction identity. Deterministic over base, ordered deltas, universe and ACTIONS
        provenance — ADR 0048 (6)."""
        return hashlib.sha256(canonical_json(self.identity_payload())).hexdigest()

    @property
    def ordered_delta_manifest_sha256s(self) -> tuple[str, ...]:
        return tuple(d.sha256 for d in self.deltas)

    @property
    def coverage_through(self) -> date:
        return self.deltas[-1].coverage_through if self.deltas else self.base_coverage_through

    def validate(self, *, observation_session: date,
                 expected_sessions: tuple[date, ...]) -> None:
        if not self.actions_authoritative:
            raise CorpusConstructionError(
                "the corpus manifest declares its ACTIONS dataset non-authoritative; a governed "
                "session cannot evaluate corporate actions from a store that never ingested them")
        if not self.tickers_authoritative:
            raise CorpusConstructionError(
                "the corpus manifest declares its TICKERS dataset non-authoritative; the registered "
                "universe is resolved from effective security metadata, so a session cannot rank "
                "securities it cannot identify")
        if self.security_identity_contract != SECURITY_IDENTITY_CONTRACT:
            raise CorpusConstructionError(
                f"the corpus manifest names security identity contract "
                f"{self.security_identity_contract!r} but this deployment implements "
                f"{SECURITY_IDENTITY_CONTRACT!r}; the rule by which securities are identified is part "
                f"of the authorized construction and is never assumed to match")
        self.tickers.validate()
        if self.tickers.coverage_cutoff < observation_session:
            raise CorpusConstructionError(
                f"the governed TICKERS construction is cut off at {self.tickers.coverage_cutoff} but "
                f"the session being observed is {observation_session}; effective security metadata "
                f"that stops before the session cannot establish which securities were tradeable "
                f"during it")
        if self.governed_universe_size != GOVERNED_UNIVERSE_SIZE:
            raise CorpusConstructionError(
                f"the corpus manifest declares a universe of {self.governed_universe_size}, not the "
                f"governing {GOVERNED_UNIVERSE_SIZE}; a universe change is a new base")
        validate_delta_chain(
            base_coverage_through=self.base_coverage_through,
            base_universe_sha256=self.governed_universe_sha256,
            deltas=self.deltas,
            observation_session=observation_session,
            contiguity=Contiguity.SESSION_CALENDAR,
            expected_sessions=expected_sessions,
        )

    def to_manifest_json(self) -> dict[str, Any]:
        """The on-disk form, round-tripping exactly through `from_payload`. Shared with the generator
        so there is one definition of the construction, not a producer's and a consumer's."""
        return {
            "base_corpus_sha256": self.base_corpus_sha256,
            "base_coverage_through": self.base_coverage_through.isoformat(),
            "governed_universe_sha256": self.governed_universe_sha256,
            "governed_universe_size": self.governed_universe_size,
            "actions_manifest_sha256": self.actions_manifest_sha256,
            "actions_authoritative": self.actions_authoritative,
            "tickers": self.tickers.to_manifest_json(),
            "tickers_authoritative": self.tickers_authoritative,
            "security_identity_contract": self.security_identity_contract,
            "base_countersignature": self.base_countersignature,
            "deltas": [
                {"session_date": d.session_date.isoformat(),
                 "coverage_through": d.coverage_through.isoformat(),
                 "sha256": d.sha256, "source_sha256": d.source_sha256,
                 "universe_sha256": d.universe_sha256, "rows": d.rows,
                 "retrieved_at": d.retrieved_at, "countersignature": d.countersignature,
                 "exclusions": list(d.exclusions)}
                for d in self.deltas],
        }

    @staticmethod
    def from_payload(payload: Any) -> CorpusManifest:
        if not isinstance(payload, dict):
            raise CorpusConstructionError("the corpus manifest is not an object")
        try:
            base_coverage = date.fromisoformat(str(payload["base_coverage_through"]))
        except (KeyError, ValueError) as exc:
            raise CorpusConstructionError(
                f"the corpus manifest records no valid base_coverage_through: {exc}") from exc
        raw_deltas = payload.get("deltas", [])
        if not isinstance(raw_deltas, list):
            raise CorpusConstructionError(
                f"the corpus manifest records deltas as {type(raw_deltas).__name__}, not a list")
        authoritative = payload.get("actions_authoritative")
        if authoritative is not True and authoritative is not False:
            raise CorpusConstructionError(
                f"the corpus manifest records actions_authoritative as {authoritative!r}; it must be "
                f"the JSON boolean true or false, not a value that merely reads as one")
        tickers_authoritative = payload.get("tickers_authoritative")
        if tickers_authoritative is not True and tickers_authoritative is not False:
            raise CorpusConstructionError(
                f"the corpus manifest records tickers_authoritative as {tickers_authoritative!r}; it "
                f"must be the JSON boolean true or false, not a value that merely reads as one")
        contract = str(payload.get("security_identity_contract", "")).strip()
        if not contract:
            raise CorpusConstructionError(
                "the corpus manifest names no security_identity_contract; the rule by which tickers "
                "are resolved to permanent securities is part of the authorized construction")
        size = payload.get("governed_universe_size")
        if not isinstance(size, int) or isinstance(size, bool):
            raise CorpusConstructionError(
                f"the corpus manifest records governed_universe_size as {size!r}")
        countersignature = str(payload.get("base_countersignature", "")).strip()
        if not countersignature:
            raise CorpusConstructionError(
                "the corpus manifest carries no base countersignature reference")
        return CorpusManifest(
            base_corpus_sha256=_require_sha256(payload.get("base_corpus_sha256"),
                                               what="the base corpus identity"),
            base_coverage_through=base_coverage,
            governed_universe_sha256=_require_sha256(payload.get("governed_universe_sha256"),
                                                     what="the governed universe identity"),
            governed_universe_size=size,
            actions_manifest_sha256=_require_sha256(payload.get("actions_manifest_sha256"),
                                                    what="the ACTIONS manifest identity"),
            actions_authoritative=authoritative,
            tickers=TickersManifest.from_payload(payload.get("tickers")),
            tickers_authoritative=tickers_authoritative,
            security_identity_contract=contract,
            deltas=tuple(GovernedDelta.from_payload(d, index=i) for i, d in enumerate(raw_deltas)),
            base_countersignature=countersignature,
        )


@dataclass(frozen=True)
class Dgs3moManifest:
    """The authorized construction of the risk-free series: frozen base plus ordered extensions.

    The frozen base identity is ``forward_window.DGS3MO_SNAPSHOT_SHA256`` and stays that value. It is
    never redefined as the digest of a combined file — that would convert a frozen pin into a moving
    target and destroy the property it exists to hold (ADR 0048 (11)).
    """
    base_sha256: str
    base_coverage_through: date
    extensions: tuple[GovernedDelta, ...]

    def identity_payload(self) -> dict[str, Any]:
        return {
            "kind": "dgs3mo",
            "base_sha256": self.base_sha256,
            "base_coverage_through": self.base_coverage_through.isoformat(),
            "extensions": [e.identity_payload() for e in self.extensions],
        }

    @property
    def dgs3mo_manifest_sha256(self) -> str:
        """Base plus ordered extensions — ADR 0048 (11). Distinct from the frozen base pin."""
        return hashlib.sha256(canonical_json(self.identity_payload())).hexdigest()

    @property
    def coverage_through(self) -> date:
        return self.extensions[-1].coverage_through if self.extensions else self.base_coverage_through

    def validate(self, *, observation_session: date, frozen_base_sha256: str) -> None:
        if self.base_sha256 != frozen_base_sha256:
            raise FrozenArtifactDrift(
                f"the DGS3MO manifest names base {self.base_sha256[:16]}… but the countersigned "
                f"preregistration pins {frozen_base_sha256[:16]}…; the frozen base is installed by "
                f"exact hash and never regenerated")
        validate_delta_chain(
            base_coverage_through=self.base_coverage_through,
            base_universe_sha256=None,          # a rate series is not universe-bound
            deltas=self.extensions,
            observation_session=observation_session,
            contiguity=Contiguity.COVERAGE_CONTIGUOUS,
        )

    @staticmethod
    def from_payload(payload: Any) -> Dgs3moManifest:
        if not isinstance(payload, dict):
            raise CorpusConstructionError("the DGS3MO manifest is not an object")
        try:
            base_coverage = date.fromisoformat(str(payload["base_coverage_through"]))
        except (KeyError, ValueError) as exc:
            raise CorpusConstructionError(
                f"the DGS3MO manifest records no valid base_coverage_through: {exc}") from exc
        raw = payload.get("extensions", [])
        if not isinstance(raw, list):
            raise CorpusConstructionError(
                f"the DGS3MO manifest records extensions as {type(raw).__name__}, not a list")
        return Dgs3moManifest(
            base_sha256=_require_sha256(payload.get("base_sha256"),
                                        what="the DGS3MO base identity"),
            base_coverage_through=base_coverage,
            extensions=tuple(GovernedDelta.from_payload(e, index=i, require_universe=False)
                             for i, e in enumerate(raw)),
        )


#: The governed TICKERS schema. Bumped when the selected vendor columns change, because a column set
#: is part of what the construction IS: dropping `permaticker` turns identity resolution off, and a
#: manifest that did not name its columns could not tell that from an unchanged one.
TICKERS_SCHEMA_VERSION = "TICKERS_V2_PERMATICKER"

#: The identity-bearing columns. `row_identity_sha256` digests exactly these, so a change to a
#: security's permanent id, symbol or effective interval moves the manifest identity, while a churn-y
#: descriptive field (sector reclassification, company-site URL) does not.
TICKERS_IDENTITY_COLUMNS = ("permaticker", "ticker", "firstpricedate", "lastpricedate")


def tickers_row_identity(rows: Any) -> str:
    """Digest the identity-bearing projection of the TICKERS rows.

    Sorted by permanent id then symbol so the identity is independent of row order — two deployments
    that assembled the same securities produce the same digest whatever order the vendor returned.
    """
    projected = sorted([str(r[c] if isinstance(r, dict) else r[i]) for i, c
                        in enumerate(TICKERS_IDENTITY_COLUMNS)] for r in rows)
    return hashlib.sha256(canonical_json(projected)).hexdigest()


@dataclass(frozen=True)
class TickersManifest:
    """The authorized construction of the governed TICKERS dataset (owner ruling, 2026-07-29).

    Bound by ADR 0048 as amended because `universe_asof` cannot resolve an eligible universe without
    it: a stale TICKERS yields an EMPTY universe and a current one yields 500 names, and those two
    constructions must not be able to share an authorized identity.
    """
    schema_version: str
    columns: tuple[str, ...]
    rows: int
    permanent_ids: int
    row_identity_sha256: str
    coverage_cutoff: date
    artifact_sha256: str
    source_identity: str
    countersignature: str

    def identity_payload(self) -> dict[str, Any]:
        return {
            "kind": "tickers_manifest",
            "schema_version": self.schema_version,
            "columns": list(self.columns),
            "rows": self.rows,
            "permanent_ids": self.permanent_ids,
            "row_identity_sha256": self.row_identity_sha256,
            "coverage_cutoff": self.coverage_cutoff.isoformat(),
            "artifact_sha256": self.artifact_sha256,
            "source_identity": self.source_identity,
            "countersignature": self.countersignature,
        }

    @property
    def tickers_manifest_sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.identity_payload())).hexdigest()

    def validate(self) -> None:
        if self.schema_version != TICKERS_SCHEMA_VERSION:
            raise CorpusConstructionError(
                f"the TICKERS manifest declares schema {self.schema_version!r} but this deployment "
                f"implements {TICKERS_SCHEMA_VERSION!r}")
        missing = [c for c in TICKERS_IDENTITY_COLUMNS if c not in self.columns]
        if missing:
            raise CorpusConstructionError(
                f"the TICKERS manifest omits identity-bearing column(s) {missing}; without them a "
                f"security cannot be resolved to a permanent lineage")
        if self.rows <= 0 or self.permanent_ids <= 0:
            raise CorpusConstructionError(
                f"the TICKERS manifest records {self.rows} row(s) and {self.permanent_ids} permanent "
                f"id(s); an empty security master evidences no universe at all")
        if self.permanent_ids != self.rows:
            raise CorpusConstructionError(
                f"the TICKERS manifest records {self.rows} rows but only {self.permanent_ids} distinct "
                f"permanent ids; a symbol mapping to several lineages is ambiguous by construction")

    def to_manifest_json(self) -> dict[str, Any]:
        """The on-disk form, round-tripping exactly through `from_payload`.

        Generation and verification share this so a producer cannot drift from the consumer: any
        generator that writes the block by hand would be a second, unreviewed definition of what a
        TICKERS construction IS.
        """
        return {
            "schema_version": self.schema_version,
            "columns": list(self.columns),
            "rows": self.rows,
            "permanent_ids": self.permanent_ids,
            "row_identity_sha256": self.row_identity_sha256,
            "coverage_cutoff": self.coverage_cutoff.isoformat(),
            "artifact_sha256": self.artifact_sha256,
            "source_identity": self.source_identity,
            "countersignature": self.countersignature,
        }

    @staticmethod
    def from_payload(payload: Any) -> TickersManifest:
        if not isinstance(payload, dict):
            raise CorpusConstructionError("the TICKERS manifest is not an object")
        try:
            cutoff = date.fromisoformat(str(payload["coverage_cutoff"]))
        except (KeyError, ValueError) as exc:
            raise CorpusConstructionError(
                f"the TICKERS manifest records no valid coverage_cutoff: {exc}") from exc
        cols = payload.get("columns", [])
        if not isinstance(cols, list) or not cols:
            raise CorpusConstructionError(
                "the TICKERS manifest records no selected vendor columns")
        for key in ("rows", "permanent_ids"):
            if not isinstance(payload.get(key), int) or isinstance(payload.get(key), bool):
                raise CorpusConstructionError(
                    f"the TICKERS manifest records {key} as {payload.get(key)!r}")
        countersignature = str(payload.get("countersignature", "")).strip()
        if not countersignature:
            raise CorpusConstructionError("the TICKERS manifest carries no countersignature reference")
        return TickersManifest(
            schema_version=str(payload.get("schema_version", "")).strip(),
            columns=tuple(str(c) for c in cols),
            rows=int(payload["rows"]),
            permanent_ids=int(payload["permanent_ids"]),
            row_identity_sha256=_require_sha256(payload.get("row_identity_sha256"),
                                                what="the TICKERS row identity"),
            coverage_cutoff=cutoff,
            artifact_sha256=_require_sha256(payload.get("artifact_sha256"),
                                            what="the TICKERS artifact identity"),
            source_identity=str(payload.get("source_identity", "")).strip(),
            countersignature=countersignature,
        )


def _load_manifest_json(path: Path, *, what: str) -> dict:
    if not path.is_file():
        raise CorpusConstructionError(f"{what} is absent at {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusConstructionError(f"{what} at {path} is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise CorpusConstructionError(f"{what} at {path} is not an object")
    return payload


# ── the Layer 2 whole-corpus reconstruction ──────────────────────────────────────────────────────────
#
# A `CorpusManifest` describes `immutable base + ordered deltas`. A Layer 2 construction is NEITHER: it
# is a whole-corpus reconstruction from ONE sealed source vintage, normalized on the vendor's permanent
# identifier, and what authorizes it is CONSTRUCTION EVIDENCE — crosswalk, universes, adjudications,
# censuses, reconciliation, impact analyses — not a delta chain.
#
# ⛔ It is therefore given NATIVE support rather than being converted into a synthetic base-plus-delta
# manifest. A conversion would make the runtime accept the bytes by representing the construction as
# something it is not: it would have to invent a `base_coverage_through`, a base artifact identity and
# a delta order, none of which exist. Every one of those inventions would be a false statement carried
# in governed evidence, and the falsehood would be indistinguishable from the truth downstream.
#
# The two loaders are kept SEPARATE and the base-plus-delta path is untouched.

LAYER2_CORPUS_KIND = "layer2_governed_corpus"

#: Schema versions this runtime understands. An unknown version is REFUSED rather than best-effort
#: parsed — a construction whose meaning has changed must not be read with the old meaning.
SUPPORTED_LAYER2_SCHEMA_VERSIONS = frozenset({"LAYER2_SINGLE_VINTAGE_PERMANENT_LINEAGE_v1.0"})

#: Every evidence artifact the construction must carry. Absence is a refusal: a manifest that names
#: fewer artifacts than the construction was authorized with is a different construction.
REQUIRED_LAYER2_ARTIFACTS = frozenset({
    "universe_crosswalk_v2", "crosswalk_summary_v2", "universe_exclusions_v2",
    "quarantine_unresolved_source_master_v2", "july27_exclusion_impact_check",
    "price_universe_v2", "layer2_price_adjudication",
    "source_vintage", "extraction_evidence", "normalized_corpus_evidence",
    "lineage_hole_census",
    "adjustment_reconciliation_final", "residual_relevance", "tolerance_remeasurement",
    "shop_tln_quarantine",
    "step4_comparison", "step5_exclusion_impact_273", "step5_package",
})

REQUIRED_LAYER2_UNIVERSE_IDENTITIES = (
    "legacy_governed_universe_sha256", "governed_universe_key_crosswalk_sha256",
    "governed_mapped_identity_universe_sha256", "governed_price_universe_sha256",
    "source_vintage_sha256",
)

#: The kind marker an external countersignature sidecar must declare.
LAYER2_COUNTERSIGNATURE_KIND = "layer2_corpus_countersignature"

#: The only countersignature states that authorize a Layer 2 construction for session composition.
#:
#: ⚠ `CONDITIONALLY_COUNTERSIGNED` is authorizing HERE and only here: the conditions it names are the
#: runtime and readiness gates, which are enforced elsewhere in the session path (deployment identity,
#: data finality, narrow readiness) rather than by re-reading this field. A status this runtime does
#: not recognize is REFUSED rather than treated as approval.
ACCEPTED_COUNTERSIGNATURE_STATUSES = frozenset({
    "COUNTERSIGNED", "CONDITIONALLY_COUNTERSIGNED",
})


class CountersignatureError(CorpusConstructionError):
    """The external countersignature record is absent, malformed, or does not bind the construction
    actually loaded. FAILS CLOSED — an uncountersigned construction is never composed into a session.
    """


@dataclass(frozen=True)
class GovernedQuarantineDeclaration:
    """The manifest's `governed_quarantine` block, parsed and validated — never interpreted.

    This is the DECLARATION only: who is quarantined, under what class, and in whose words. The
    movements it covers live in the evidence artifact the manifest pins, and assembling the two into a
    usable policy is :func:`app.validation.governed_quarantine.governed_quarantine_policy`.

    ⚠ Required on every Layer 2 construction. A reconstruction that withholds price histories without
    saying which ones is not a construction this runtime can compose a session from: the session would
    have no way to tell a governed limitation from an undetected data defect.
    """
    permanent_identities: frozenset[str]
    descriptive_tickers: dict[str, str]              # permanent identity -> ticker
    anomaly_class: str
    quarantine_kind: str
    permanent_universe_removal: bool
    statement: tuple[str, ...]
    must_not_say: str

    @staticmethod
    def from_payload(payload: Any) -> GovernedQuarantineDeclaration:
        if not isinstance(payload, dict):
            raise CorpusConstructionError(
                "the Layer 2 manifest carries no governed_quarantine block; a construction that "
                "withholds price histories must name the identities it withholds")
        identities = payload.get("permanent_identities")
        names = payload.get("names")
        if not isinstance(identities, list) or not identities:
            raise CorpusConstructionError(
                "the governed_quarantine block names no permanent_identities")
        if not isinstance(names, list) or len(names) != len(identities):
            raise CorpusConstructionError(
                f"the governed_quarantine block names {len(identities)} permanent identity(ies) but "
                f"{len(names) if isinstance(names, list) else 'no'} descriptive ticker(s); the two "
                f"are parallel declarations and an unpaired one cannot be read")
        # ⚠ The pairing is POSITIONAL because that is how the countersigned artifact states it. It is
        # not trusted on that basis: a measured movement carries both its ticker and its permanent
        # identity, and readiness refuses unless the pair matches. A mis-declared pairing can only
        # refuse, never pass.
        pairs = {str(i).strip(): str(n).strip() for i, n in zip(identities, names, strict=True)}
        if "" in pairs or "" in pairs.values():
            raise CorpusConstructionError(
                "the governed_quarantine block carries an empty permanent identity or ticker")
        if len(pairs) != len(identities) or len(set(pairs.values())) != len(names):
            raise CorpusConstructionError(
                "the governed_quarantine block repeats a permanent identity or a ticker; the "
                "quarantine census would be ambiguous")
        anomaly_class = str(payload.get("class", "")).strip()
        kind = str(payload.get("kind", "")).strip()
        if not anomaly_class or not kind:
            raise CorpusConstructionError(
                "the governed_quarantine block declares no class/kind; an unclassified quarantine "
                "states what was withheld without stating why")
        removal = payload.get("permanent_universe_removal")
        if not isinstance(removal, bool):
            raise CorpusConstructionError(
                "the governed_quarantine block does not state permanent_universe_removal as a "
                "boolean; whether the identities left the universe is part of what was approved")
        statement = payload.get("statement")
        if not isinstance(statement, list) or not statement:
            raise CorpusConstructionError(
                "the governed_quarantine block carries no statement; the wording the record must "
                "use about these identities is part of the countersigned block")
        return GovernedQuarantineDeclaration(
            permanent_identities=frozenset(pairs),
            descriptive_tickers=pairs,
            anomaly_class=anomaly_class,
            quarantine_kind=kind,
            permanent_universe_removal=removal,
            statement=tuple(str(s) for s in statement),
            must_not_say=str(payload.get("must_not_say", "")).strip(),
        )

    def to_open_provenance(self) -> dict[str, Any]:
        return {
            "permanent_identities": sorted(self.permanent_identities),
            "descriptive_tickers": dict(sorted(self.descriptive_tickers.items())),
            "anomaly_class": self.anomaly_class,
            "quarantine_kind": self.quarantine_kind,
            "permanent_universe_removal": self.permanent_universe_removal,
            "statement": list(self.statement),
            "must_not_say": self.must_not_say,
        }


@dataclass(frozen=True)
class Layer2Countersignature:
    """Governance approval for a Layer 2 construction, recorded OUTSIDE the construction artifact.

    ⚠⚠ Why external. `corpus_manifest_v2.json` carries ``"countersignature": null`` and a
    construction-time ``status`` string that says PROPOSED. Those are properties of the artifact at the
    moment it was BUILT — a construction cannot countersign itself, and the approval necessarily comes
    afterwards. Rewriting the manifest to record the approval would change its digest and invalidate
    every binding already built around it, so the approval is recorded in a sidecar that NAMES the
    manifest digest instead.

    The embedded null therefore means "not self-countersigned", never "approval absent". It can
    neither override a valid sidecar nor substitute for one: the sidecar is required regardless of
    what the construction artifact says about itself.
    """
    countersignature_sha256: str
    corpus_manifest_sha256: str
    complete_package_sha256: str
    countersignature_status: str
    deployment_status: str
    supersedes_manifest_sha256: str

    def to_open_provenance(self) -> dict[str, Any]:
        return {
            "countersignature_sha256": self.countersignature_sha256,
            "countersigned_corpus_manifest_sha256": self.corpus_manifest_sha256,
            "complete_package_sha256": self.complete_package_sha256,
            "countersignature_status": self.countersignature_status,
            "deployment_status": self.deployment_status,
            "supersedes_manifest_sha256": self.supersedes_manifest_sha256,
        }

    @staticmethod
    def from_payload(payload: Any, *, computed_sha256: str) -> Layer2Countersignature:
        if not isinstance(payload, dict):
            raise CountersignatureError("the countersignature sidecar is not an object")
        kind = str(payload.get("kind", "")).strip()
        if kind != LAYER2_COUNTERSIGNATURE_KIND:
            raise CountersignatureError(
                f"the countersignature sidecar declares kind {kind!r}, not "
                f"{LAYER2_COUNTERSIGNATURE_KIND!r}")
        status = str(payload.get("countersignature_status", "")).strip()
        if status not in ACCEPTED_COUNTERSIGNATURE_STATUSES:
            raise CountersignatureError(
                f"the countersignature sidecar declares countersignature_status {status!r}, which "
                f"this runtime does not accept as approval (accepted: "
                f"{sorted(ACCEPTED_COUNTERSIGNATURE_STATUSES)})")
        deployment_status = str(payload.get("deployment_status", "")).strip()
        if not deployment_status:
            raise CountersignatureError(
                "the countersignature sidecar names no deployment_status; the conditions under which "
                "the construction may be deployed are part of what was approved")
        return Layer2Countersignature(
            countersignature_sha256=computed_sha256,
            corpus_manifest_sha256=_require_sha256(
                payload.get("corpus_manifest_sha256"),
                what="the countersigned corpus manifest identity"),
            complete_package_sha256=_require_sha256(
                payload.get("complete_package_sha256"),
                what="the countersigned complete-package identity"),
            countersignature_status=status,
            deployment_status=deployment_status,
            supersedes_manifest_sha256=_require_sha256(
                payload.get("supersedes_manifest_sha256"),
                what="the superseded manifest identity"),
        )


@dataclass(frozen=True)
class Layer2CorpusManifest:
    """A whole-corpus reconstruction, validated on its own terms.

    ⚠ It deliberately exposes NO `base_corpus_sha256`, `base_coverage_through`, delta order or delta
    coverage, because it has none. Anything that needs those must ask whether they exist rather than
    assume; see :class:`NormalizedCorpusConstruction`.
    """
    construction_schema_version: str
    session: date
    security_identity_contract: str
    corpus_manifest_sha256: str
    universe_identities: dict[str, str]
    mapped_identity_universe_size: int
    price_universe_size: int
    artifacts: dict[str, str]                       # logical name -> sha256
    #: logical name -> the path the manifest declares for it, relative to the governed root. Carried
    #: so a consumer that must READ an artifact resolves it from the manifest rather than from a
    #: filename of its own — the digest is only a binding if it names the file that was hashed.
    artifact_paths: dict[str, str]
    quarantined_histories: dict[str, str]           # filename -> sha256
    #: The countersigned price-history quarantine. Required: see `GovernedQuarantineDeclaration`.
    governed_quarantine: GovernedQuarantineDeclaration
    store_file_sha256: str
    supersedes_corpus_manifest_sha256: str
    supersession_reason: str
    countersigned: bool

    @property
    def governed_universe_sha256(self) -> str:
        """The PRICE universe — the one that governs SEP restriction, ranking, proxy and corpus
        identity. ⚠ NOT the mapped-identity universe; the two are never collapsed."""
        return self.universe_identities["governed_price_universe_sha256"]

    @property
    def governed_universe_size(self) -> int:
        return self.price_universe_size

    @staticmethod
    def from_payload(payload: Any, *, computed_sha256: str) -> Layer2CorpusManifest:
        if not isinstance(payload, dict):
            raise CorpusConstructionError("the Layer 2 corpus manifest is not an object")
        kind = str(payload.get("kind", "")).strip()
        if kind != LAYER2_CORPUS_KIND:
            raise CorpusConstructionError(
                f"the manifest declares kind {kind!r}, not {LAYER2_CORPUS_KIND!r}")
        version = str(payload.get("construction_schema_version", "")).strip()
        if version not in SUPPORTED_LAYER2_SCHEMA_VERSIONS:
            raise CorpusConstructionError(
                f"the Layer 2 manifest declares construction_schema_version {version!r}, which this "
                f"runtime does not understand (supported: {sorted(SUPPORTED_LAYER2_SCHEMA_VERSIONS)}); "
                f"a construction whose meaning may have changed is refused, never best-effort parsed")

        contract = str(payload.get("security_identity_contract", "")).strip()
        if not contract:
            raise CorpusConstructionError(
                "the Layer 2 manifest names no security_identity_contract")
        try:
            session = date.fromisoformat(str(payload["session"]))
        except (KeyError, ValueError) as exc:
            raise CorpusConstructionError(
                f"the Layer 2 manifest records no valid session: {exc}") from exc

        declared = payload.get("declared_identities")
        if not isinstance(declared, dict):
            raise CorpusConstructionError("the Layer 2 manifest carries no declared_identities")
        identities = {}
        for name in REQUIRED_LAYER2_UNIVERSE_IDENTITIES:
            identities[name] = _require_sha256(declared.get(name), what=f"the {name}")

        raw_artifacts = payload.get("artifacts")
        if not isinstance(raw_artifacts, dict):
            raise CorpusConstructionError("the Layer 2 manifest carries no artifacts block")
        artifacts = {name: _require_sha256((entry or {}).get("sha256"),
                                           what=f"the {name} artifact identity")
                     for name, entry in raw_artifacts.items() if isinstance(entry, dict)}
        artifact_paths = {name: str((entry or {}).get("path", "")).strip()
                          for name, entry in raw_artifacts.items() if isinstance(entry, dict)}
        missing = sorted(REQUIRED_LAYER2_ARTIFACTS - set(artifacts))
        if missing:
            raise CorpusConstructionError(
                f"the Layer 2 manifest is missing {len(missing)} required evidence artifact(s): "
                f"{missing}; a manifest naming fewer artifacts than the construction was authorized "
                f"with describes a different construction")

        raw_quarantine = payload.get("quarantined_histories")
        if not isinstance(raw_quarantine, dict) or not raw_quarantine:
            raise CorpusConstructionError(
                "the Layer 2 manifest carries no quarantined_histories; the withheld price histories "
                "are part of what the construction is")
        quarantine = {name: _require_sha256((entry or {}).get("sha256"),
                                            what=f"the quarantine history {name}")
                      for name, entry in raw_quarantine.items() if isinstance(entry, dict)}

        store = payload.get("store")
        if not isinstance(store, dict) or store.get("computed") is not True:
            raise CorpusConstructionError(
                "the Layer 2 manifest declares no COMPUTED store identity; a manifest must not claim "
                "a store it did not hash")
        store_sha = _require_sha256(store.get("store_file_sha256"), what="the store file identity")

        supersedes = payload.get("supersedes")
        if not isinstance(supersedes, dict):
            raise CorpusConstructionError(
                "the Layer 2 manifest declares no supersession; a whole-corpus reconstruction must "
                "name the construction it replaces")
        prior = _require_sha256(supersedes.get("corpus_manifest_sha256"),
                                what="the superseded corpus manifest identity")
        if prior == computed_sha256:
            raise CorpusConstructionError(
                "the Layer 2 manifest declares itself as its own predecessor")
        if supersedes.get("prior_identity_altered") is not False:
            raise CorpusConstructionError(
                "the Layer 2 manifest does not assert that the prior identity is UNALTERED; a "
                "supersession replaces a construction without mutating the record that made the "
                "earlier countersignature checkable")
        reason = str(supersedes.get("reason", "")).strip()
        if not reason:
            raise CorpusConstructionError("the Layer 2 supersession names no reason")

        for name, size_key in (("mapped_identity_universe_size", "mapped_identity_universe_size"),
                               ("price_universe_size", "price_universe_size")):
            value = payload.get(size_key)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise CorpusConstructionError(
                    f"the Layer 2 manifest records {name} as {value!r}")

        return Layer2CorpusManifest(
            construction_schema_version=version, session=session,
            security_identity_contract=contract, corpus_manifest_sha256=computed_sha256,
            universe_identities=identities,
            mapped_identity_universe_size=int(payload["mapped_identity_universe_size"]),
            price_universe_size=int(payload["price_universe_size"]),
            artifacts=artifacts, artifact_paths=artifact_paths,
            quarantined_histories=quarantine,
            governed_quarantine=GovernedQuarantineDeclaration.from_payload(
                payload.get("governed_quarantine")),
            store_file_sha256=store_sha, supersedes_corpus_manifest_sha256=prior,
            supersession_reason=reason,
            countersigned=payload.get("countersignature") is not None,
        )


@dataclass(frozen=True)
class NormalizedCorpusConstruction:
    """What a governed corpus construction exposes REGARDLESS of how it was assembled.

    ⚠⚠ The base-plus-delta fields are `None`/empty for a Layer 2 reconstruction and are NEVER
    fabricated. A consumer that needs a base or a delta order must ASK whether one exists; silently
    defaulting them would reintroduce exactly the false statement native support exists to avoid.
    """
    corpus_construction_kind: str
    corpus_manifest_sha256: str
    governed_universe_sha256: str
    governed_universe_size: int
    security_identity_contract: str
    coverage_through: date
    construction_schema_version: str | None = None
    supersedes_corpus_manifest_sha256: str | None = None
    # base-plus-delta ONLY — absent by design on a reconstruction
    base_corpus_sha256: str | None = None
    base_coverage_through: date | None = None
    ordered_delta_manifest_sha256s: tuple[str, ...] = ()
    actions_manifest_sha256: str | None = None
    tickers_manifest_sha256: str | None = None
    # reconstruction ONLY
    mapped_identity_universe_sha256: str | None = None
    mapped_identity_universe_size: int | None = None
    store_file_sha256: str | None = None
    evidence_artifact_count: int | None = None
    source_vintage_sha256: str | None = None
    #: The countersigned price-history quarantine, `None` on a base-plus-delta construction which
    #: declares none. ⚠ NEVER defaulted to an empty declaration: "this construction quarantines
    #: nothing" and "this construction does not say" are different statements, and only the second is
    #: true of a corpus format that predates the block.
    governed_quarantine: GovernedQuarantineDeclaration | None = None
    #: logical artifact name -> (sha256, path relative to the governed root).
    pinned_artifacts: dict[str, tuple[str, str]] = field(default_factory=dict)

    @property
    def has_base_and_deltas(self) -> bool:
        return self.base_corpus_sha256 is not None

    def artifact_sha256(self, name: str) -> str | None:
        """The digest the construction pins for one evidence artifact, or `None` if it pins none."""
        entry = self.pinned_artifacts.get(name)
        return entry[0] if entry else None

    def artifact_path(self, name: str) -> str | None:
        """The path the construction declares for one evidence artifact, relative to its root."""
        entry = self.pinned_artifacts.get(name)
        return entry[1] if entry and entry[1] else None

    def to_open_provenance(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "corpus_construction_kind": self.corpus_construction_kind,
            "construction_schema_version": self.construction_schema_version,
            "corpus_manifest_sha256": self.corpus_manifest_sha256,
            "governed_universe_sha256": self.governed_universe_sha256,
            "governed_universe_size": self.governed_universe_size,
            "security_identity_contract": self.security_identity_contract,
            "corpus_coverage_through": self.coverage_through.isoformat(),
            "supersedes_corpus_manifest_sha256": self.supersedes_corpus_manifest_sha256,
            "has_base_and_deltas": self.has_base_and_deltas,
        }
        if self.has_base_and_deltas:
            out |= {
                "base_corpus_sha256": self.base_corpus_sha256,
                "base_coverage_through": (self.base_coverage_through.isoformat()
                                          if self.base_coverage_through else None),
                "ordered_delta_manifest_sha256s": list(self.ordered_delta_manifest_sha256s),
                "actions_manifest_sha256": self.actions_manifest_sha256,
                "tickers_manifest_sha256": self.tickers_manifest_sha256,
            }
        else:
            out |= {
                "mapped_identity_universe_sha256": self.mapped_identity_universe_sha256,
                "mapped_identity_universe_size": self.mapped_identity_universe_size,
                "store_file_sha256": self.store_file_sha256,
                "evidence_artifact_count": self.evidence_artifact_count,
                "source_vintage_sha256": self.source_vintage_sha256,
                "governed_quarantine": (self.governed_quarantine.to_open_provenance()
                                        if self.governed_quarantine else None),
            }
        return out


def normalize_corpus_manifest(
    manifest: CorpusManifest | Layer2CorpusManifest,
) -> NormalizedCorpusConstruction:
    """One representation, two constructions, nothing invented."""
    if isinstance(manifest, Layer2CorpusManifest):
        return NormalizedCorpusConstruction(
            corpus_construction_kind=LAYER2_CORPUS_KIND,
            construction_schema_version=manifest.construction_schema_version,
            corpus_manifest_sha256=manifest.corpus_manifest_sha256,
            governed_universe_sha256=manifest.governed_universe_sha256,
            governed_universe_size=manifest.governed_universe_size,
            security_identity_contract=manifest.security_identity_contract,
            coverage_through=manifest.session,
            supersedes_corpus_manifest_sha256=manifest.supersedes_corpus_manifest_sha256,
            mapped_identity_universe_sha256=(
                manifest.universe_identities["governed_mapped_identity_universe_sha256"]),
            mapped_identity_universe_size=manifest.mapped_identity_universe_size,
            store_file_sha256=manifest.store_file_sha256,
            evidence_artifact_count=len(manifest.artifacts),
            source_vintage_sha256=manifest.universe_identities["source_vintage_sha256"],
            governed_quarantine=manifest.governed_quarantine,
            pinned_artifacts={name: (sha, manifest.artifact_paths.get(name, ""))
                              for name, sha in manifest.artifacts.items()},
        )
    return NormalizedCorpusConstruction(
        corpus_construction_kind="governed_corpus",
        corpus_manifest_sha256=manifest.corpus_manifest_sha256,
        governed_universe_sha256=manifest.governed_universe_sha256,
        governed_universe_size=manifest.governed_universe_size,
        security_identity_contract=manifest.security_identity_contract,
        coverage_through=manifest.coverage_through,
        base_corpus_sha256=manifest.base_corpus_sha256,
        base_coverage_through=manifest.base_coverage_through,
        ordered_delta_manifest_sha256s=manifest.ordered_delta_manifest_sha256s,
        actions_manifest_sha256=manifest.actions_manifest_sha256,
        tickers_manifest_sha256=manifest.tickers_manifest_sha256,
    )


def deployment_corpus_block(
    normalized: NormalizedCorpusConstruction,
    *,
    dgs3mo_manifest_sha256: str,
    countersignature: Layer2Countersignature | None = None,
) -> dict[str, Any]:
    """The `corpus` identity block a deployment manifest records — the ONE producer.

    ⚠ Both sides of the contract call this: `generate_deployment_evidence` WRITES it, and
    `resolve_governed_construction` RECOMPUTES it to compare against what the deployment declared. A
    second implementation on the generating side is how a manifest comes to declare something the
    session path never checks, so there is only one.

    The two constructions expose different fields because they ARE different: a reconstruction has no
    base, no delta order and no `base_coverage_through`, and its coverage is therefore reported as
    `governed_coverage_through`. Nothing is defaulted across the two shapes.
    """
    if normalized.has_base_and_deltas:
        return {
            "base_corpus_sha256": normalized.base_corpus_sha256,
            "base_coverage_through": (normalized.base_coverage_through.isoformat()
                                      if normalized.base_coverage_through else None),
            "ordered_delta_manifest_sha256s": list(normalized.ordered_delta_manifest_sha256s),
            "governed_universe_sha256": normalized.governed_universe_sha256,
            "actions_manifest_sha256": normalized.actions_manifest_sha256,
            "tickers_manifest_sha256": normalized.tickers_manifest_sha256,
            "security_identity_contract": normalized.security_identity_contract,
            "corpus_manifest_sha256": normalized.corpus_manifest_sha256,
            "dgs3mo_manifest_sha256": dgs3mo_manifest_sha256,
        }
    if countersignature is None:
        raise CountersignatureError(
            "a Layer 2 deployment corpus block cannot be produced without the countersignature "
            "sidecar; the approval is part of what the deployment is authorized to assemble")
    return {
        "corpus_construction_kind": normalized.corpus_construction_kind,
        "construction_schema_version": normalized.construction_schema_version,
        "corpus_manifest_sha256": normalized.corpus_manifest_sha256,
        "source_vintage_sha256": normalized.source_vintage_sha256,
        "governed_coverage_through": normalized.coverage_through.isoformat(),
        "governed_universe_sha256": normalized.governed_universe_sha256,
        "store_file_sha256": normalized.store_file_sha256,
        "supersedes_corpus_manifest_sha256": normalized.supersedes_corpus_manifest_sha256,
        "countersignature_sha256": countersignature.countersignature_sha256,
        "security_identity_contract": normalized.security_identity_contract,
        "dgs3mo_manifest_sha256": dgs3mo_manifest_sha256,
    }


def load_layer2_corpus_manifest(path: Path) -> Layer2CorpusManifest:
    """Load and validate a Layer 2 reconstruction manifest.

    The identity is the sha256 of the file's bytes, and the file must BE its own canonical
    serialization — the payload is re-canonicalized and required to match. That closes the gap where a
    manifest could carry a valid-looking digest while its bytes said something else.
    """
    raw = Path(path).read_bytes()
    computed = hashlib.sha256(raw).hexdigest()
    payload = _load_manifest_json(Path(path), what="the Layer 2 corpus manifest")
    if canonical_json(payload) != raw:
        raise CorpusConstructionError(
            "the Layer 2 corpus manifest is not in its own canonical form; its bytes do not "
            "re-serialize to themselves, so its identity cannot be reproduced")
    return Layer2CorpusManifest.from_payload(payload, computed_sha256=computed)


def load_any_corpus_manifest(path: Path) -> CorpusManifest | Layer2CorpusManifest:
    """Dispatch on the declared kind. A base-plus-delta manifest carries no `kind` and takes the
    ORIGINAL path, entirely unchanged."""
    payload = _load_manifest_json(Path(path), what="the corpus manifest")
    kind = str(payload.get("kind", "")).strip()
    if not kind:
        return CorpusManifest.from_payload(payload)
    if kind == LAYER2_CORPUS_KIND:
        return load_layer2_corpus_manifest(Path(path))
    raise CorpusConstructionError(
        f"the corpus manifest declares an unrecognized kind {kind!r}; this runtime supports the "
        f"base-plus-delta construction (no kind) and {LAYER2_CORPUS_KIND!r}")


def load_layer2_countersignature(path: Path | None) -> Layer2Countersignature:
    """Load the external countersignature sidecar. Its identity is the sha256 of its own bytes.

    Like the Layer 2 manifest, the file must BE its own canonical serialization, so the digest a
    deployment manifest binds is reproducible from the bytes on disk.
    """
    if path is None:
        raise CountersignatureError(
            "no countersignature sidecar is configured; a Layer 2 construction is never composed "
            "into a session on the strength of the construction artifact alone")
    p = Path(path)
    if not p.is_file():
        raise CountersignatureError(
            f"the countersignature sidecar is absent at {p}; the construction carries no external "
            f"governance approval and is refused")
    raw = p.read_bytes()
    payload = _load_manifest_json(p, what="the countersignature sidecar")
    if canonical_json(payload) != raw:
        raise CountersignatureError(
            "the countersignature sidecar is not in its own canonical form; its bytes do not "
            "re-serialize to themselves, so its identity cannot be reproduced")
    return Layer2Countersignature.from_payload(
        payload, computed_sha256=hashlib.sha256(raw).hexdigest())


def require_countersignature(manifest: Layer2CorpusManifest,
                             countersignature: Layer2Countersignature) -> None:
    """The sidecar must bind the EXACT manifest that was loaded.

    ⚠ The failure this exists to catch is a sidecar that is internally valid but approves a DIFFERENT
    construction — most plausibly the one this manifest supersedes, left installed across an upgrade.
    That case is diagnosed by name rather than as a generic mismatch, because "the countersignature is
    for the corpus you replaced" and "the countersignature is for some unrelated corpus" call for
    different operator responses.
    """
    if countersignature.corpus_manifest_sha256 == manifest.supersedes_corpus_manifest_sha256:
        raise CountersignatureError(
            f"the countersignature sidecar binds "
            f"{countersignature.corpus_manifest_sha256[:16]}…, which is the manifest this "
            f"construction SUPERSEDES, not the loaded manifest "
            f"{manifest.corpus_manifest_sha256[:16]}…; a superseded countersignature does not carry "
            f"forward to its successor")
    if countersignature.corpus_manifest_sha256 != manifest.corpus_manifest_sha256:
        raise CountersignatureError(
            f"the countersignature sidecar binds corpus manifest "
            f"{countersignature.corpus_manifest_sha256[:16]}… but the loaded manifest is "
            f"{manifest.corpus_manifest_sha256[:16]}…; approval of one construction is never "
            f"approval of another")
    if countersignature.supersedes_manifest_sha256 != manifest.supersedes_corpus_manifest_sha256:
        raise CountersignatureError(
            f"the countersignature sidecar records the supersession of "
            f"{countersignature.supersedes_manifest_sha256[:16]}… but the manifest supersedes "
            f"{manifest.supersedes_corpus_manifest_sha256[:16]}…; the approved supersession and the "
            f"assembled one are not the same event")


def load_corpus_manifest(path: Path) -> CorpusManifest:
    return CorpusManifest.from_payload(_load_manifest_json(path, what="the corpus manifest"))


def load_dgs3mo_manifest(path: Path) -> Dgs3moManifest:
    return Dgs3moManifest.from_payload(_load_manifest_json(path, what="the DGS3MO manifest"))


@dataclass(frozen=True)
class GovernedConstruction:
    """The validated construction one observation is authorized to use.

    ⚠ `corpus` is whichever manifest kind was actually loaded. Consumers that need construction facts
    should read `normalized`, which exposes the same questions for both kinds and answers `None` where
    a construction genuinely has no answer.
    """
    corpus: CorpusManifest | Layer2CorpusManifest
    dgs3mo: Dgs3moManifest
    corpus_manifest_sha256: str
    dgs3mo_manifest_sha256: str
    normalized: NormalizedCorpusConstruction
    #: Present for a Layer 2 reconstruction and `None` for a base-plus-delta construction, whose
    #: approval is carried by its per-delta countersignature references instead.
    countersignature: Layer2Countersignature | None = None

    def to_open_provenance(self) -> dict[str, Any]:
        if not isinstance(self.corpus, CorpusManifest):
            # A reconstruction emits its OWN provenance shape. It must never carry base/delta keys —
            # not even as nulls: a null `base_corpus_sha256` in governed evidence reads as "there was
            # a base and we failed to record it", which is a different and false statement.
            out = dict(self.normalized.to_open_provenance())
            out |= {
                "dgs3mo_base_sha256": self.dgs3mo.base_sha256,
                "dgs3mo_manifest_sha256": self.dgs3mo_manifest_sha256,
                "dgs3mo_coverage_through": self.dgs3mo.coverage_through.isoformat(),
            }
            if self.countersignature is not None:
                out["countersignature"] = self.countersignature.to_open_provenance()
            return out
        return {
            "base_corpus_sha256": self.corpus.base_corpus_sha256,
            "base_coverage_through": self.corpus.base_coverage_through.isoformat(),
            "ordered_delta_manifest_sha256s": list(self.corpus.ordered_delta_manifest_sha256s),
            "governed_universe_sha256": self.corpus.governed_universe_sha256,
            "governed_universe_size": self.corpus.governed_universe_size,
            "actions_manifest_sha256": self.corpus.actions_manifest_sha256,
            "tickers_manifest_sha256": self.corpus.tickers_manifest_sha256,
            "security_identity_contract": self.corpus.security_identity_contract,
            "corpus_manifest_sha256": self.corpus_manifest_sha256,
            "corpus_coverage_through": self.corpus.coverage_through.isoformat(),
            "dgs3mo_base_sha256": self.dgs3mo.base_sha256,
            "dgs3mo_manifest_sha256": self.dgs3mo_manifest_sha256,
            "dgs3mo_coverage_through": self.dgs3mo.coverage_through.isoformat(),
        }


def resolve_governed_construction(
    *,
    corpus_manifest_path: Path,
    dgs3mo_manifest_path: Path,
    dgs3mo_path: Path,
    trial_ledger_path: Path,
    frozen_dgs3mo_sha256: str,
    frozen_trial_ledger_sha256: str,
    deployment_manifest_corpus_block: Any,
    observation_session: date,
    expected_sessions: tuple[date, ...],
    countersignature_path: Path | None = None,
) -> GovernedConstruction:
    """Establish, fail-closed, which governed construction this session is authorized to consume.

    Order matters and is deliberate: the frozen artifacts are verified by exact hash BEFORE any
    manifest is trusted, because a manifest that names a drifted artifact would otherwise be validated
    against itself. Then the chains are validated, then the deployment manifest is required to agree
    with what was actually assembled.

    This function performs no data reads and never computes a value-level store identity; that stays
    with :mod:`app.validation.data_finality`, unchanged.
    """
    verify_frozen_artifact(Path(dgs3mo_path), pinned_sha256=frozen_dgs3mo_sha256,
                           what="the frozen DGS3MO base")
    verify_frozen_artifact(Path(trial_ledger_path), pinned_sha256=frozen_trial_ledger_sha256,
                           what="the governed trial ledger")

    corpus = load_any_corpus_manifest(Path(corpus_manifest_path))
    dgs3mo = load_dgs3mo_manifest(Path(dgs3mo_manifest_path))
    normalized = normalize_corpus_manifest(corpus)

    # ── the approval, before anything else is trusted ──
    #
    # A reconstruction replaces a countersigned corpus wholesale, so its authority cannot come from the
    # chain of per-delta countersignatures the base-plus-delta path relies on. It comes from an
    # external sidecar, and it is required REGARDLESS of what the construction artifact says about
    # itself: the embedded `countersignature` field describes whether the artifact self-countersigned
    # (it cannot), and is therefore neither a substitute for the sidecar nor able to override it.
    countersignature: Layer2Countersignature | None = None
    if isinstance(corpus, Layer2CorpusManifest):
        countersignature = load_layer2_countersignature(countersignature_path)
        require_countersignature(corpus, countersignature)
        # ⚠ DELIBERATELY NOT a session-equality check. Two scopes are easy to conflate and must not
        # be: the corpus countersignature approves the reconstructed CORPUS and its coverage, while a
        # READINESS ATTESTATION is valid only for its exact session. Refusing any session but the one
        # the reconstruction was built for would collapse the first into the second and deny a
        # legitimately covered session that is entitled to its own readiness run. The session binding
        # stays where it belongs — on the attestation and the receipt.
    else:
        corpus.validate(observation_session=observation_session,
                        expected_sessions=expected_sessions)
    dgs3mo.validate(observation_session=observation_session,
                    frozen_base_sha256=frozen_dgs3mo_sha256)

    if normalized.coverage_through < observation_session:
        raise CorpusConstructionError(
            f"the governed corpus reaches {normalized.coverage_through} but the session being "
            f"observed is {observation_session}; a session cannot be evaluated against data that "
            f"stops before it")
    if dgs3mo.coverage_through < observation_session:
        raise CorpusConstructionError(
            f"the DGS3MO construction reaches {dgs3mo.coverage_through} but the session being observed "
            f"is {observation_session}; the risk-free series does not cover the session")

    # The deployment must have declared the construction that was actually assembled. The expected
    # block is RECOMPUTED here from the same single producer the generator wrote it with, so the two
    # sides cannot drift into declaring and checking different things.
    expected_block = deployment_corpus_block(
        normalized, dgs3mo_manifest_sha256=dgs3mo.dgs3mo_manifest_sha256,
        countersignature=countersignature)
    if normalized.has_base_and_deltas:
        require_declared_identities(deployment_manifest_corpus_block, computed={
            key: expected_block[key] for key in REQUIRED_MANIFEST_IDENTITIES})
    else:
        require_declared_identities(
            deployment_manifest_corpus_block,
            computed={key: expected_block[key] for key in REQUIRED_LAYER2_MANIFEST_IDENTITIES},
            required=REQUIRED_LAYER2_MANIFEST_IDENTITIES,
            sha256_keys=LAYER2_MANIFEST_DIGEST_IDENTITIES,
            list_keys=())
    declared_dgs3mo = deployment_manifest_corpus_block.get("dgs3mo_manifest_sha256")
    if declared_dgs3mo is None:
        raise ManifestIdentityConflict(
            "the deployment manifest declares no dgs3mo_manifest_sha256; the risk-free construction "
            "is part of what the deployment was authorized to assemble")
    if str(declared_dgs3mo).lower() != dgs3mo.dgs3mo_manifest_sha256:
        raise ManifestIdentityConflict(
            f"the deployment manifest declares dgs3mo_manifest_sha256 {str(declared_dgs3mo)[:16]}… "
            f"but the assembled construction is {dgs3mo.dgs3mo_manifest_sha256[:16]}…")

    return GovernedConstruction(
        corpus=corpus, dgs3mo=dgs3mo,
        corpus_manifest_sha256=corpus.corpus_manifest_sha256,
        dgs3mo_manifest_sha256=dgs3mo.dgs3mo_manifest_sha256,
        normalized=normalized, countersignature=countersignature,
    )


def manifest_bound_authority_policy(
    normalized: NormalizedCorpusConstruction,
    countersignature: Layer2Countersignature | None,
) -> Any | None:
    """The source-authority policy a construction confers — the ONE derivation.

    ⚠ Both sides call this: production session composition and the deployment-evidence generator. A
    second derivation is how the generator comes to describe a deployment the session path would
    refuse, so there is only one.

    `None` for a base-plus-delta construction, whose deployment still holds the artifacts it ingested
    and whose authority is therefore the artifact-path re-hash, unchanged.

    For a countersigned Layer 2 reconstruction the source ZIPs were construction inputs on the build
    machine, so authority is carried by the manifest, the countersignature that binds it, and the
    store provenance naming the same governed vintage. That conclusion — and only that conclusion — is
    handed to `declare_action_source`, which never learns a corpus format.
    """
    if normalized.has_base_and_deltas:
        return None
    if countersignature is None:                     # pragma: no cover - resolve() refuses first
        raise CountersignatureError(
            "a Layer 2 construction reached authority derivation without a countersignature")
    vintage = normalized.source_vintage_sha256
    if not _is_sha256(vintage):
        raise CorpusConstructionError(
            f"the Layer 2 construction binds no usable source_vintage_sha256 ({vintage!r}); source "
            f"authority cannot rest on a vintage the manifest does not name")
    from app.validation.production_bindings import ManifestBoundAuthorityPolicy

    return ManifestBoundAuthorityPolicy(
        source_vintage_sha256=str(vintage).strip().lower(),
        corpus_manifest_sha256=normalized.corpus_manifest_sha256,
        countersignature_sha256=countersignature.countersignature_sha256,
        construction_kind=normalized.corpus_construction_kind)


def read_pinned_artifact(normalized: NormalizedCorpusConstruction, name: str, *,
                         governed_root: Path) -> tuple[bytes, str]:
    """Read one evidence artifact the construction pins, AFTER proving it IS that artifact.

    ⚠ The filename is never supplied by the caller: it comes from the manifest's own `artifacts`
    block, because a digest only binds anything if it names the file that was hashed. A caller can
    point this at a governed root; it cannot point it at a file of its choosing.

    Returns the bytes and their digest, so a consumer can bind the artifact it just read into its own
    evidence without hashing it a second time.
    """
    pinned = normalized.artifact_sha256(name)
    relative = normalized.artifact_path(name)
    if not pinned or not relative:
        raise CorpusConstructionError(
            f"the governed construction pins no {name} artifact; it cannot be read as evidence")
    path = Path(governed_root) / relative
    if not path.is_file():
        raise FrozenArtifactDrift(
            f"the governed {name} artifact is absent at {path}; it is installed with the "
            f"construction, never regenerated")
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != pinned:
        raise FrozenArtifactDrift(
            f"the governed {name} artifact at {path} hashes to {actual[:16]}… but the corpus "
            f"manifest pins {pinned[:16]}…; a regenerated or edited artifact is a different artifact")
    return raw, actual


def verify_frozen_artifact(path: Path, *, pinned_sha256: str, what: str) -> str:
    """Install-by-exact-hash. Refuses drift rather than accepting an equivalent-looking file.

    A regenerated, normalized, reordered or reserialized copy is NOT equivalent: the preregistration
    froze these artifacts by digest, and a different digest is a different artifact regardless of how
    similar its contents look (ADR 0048 (12)).
    """
    if not path.is_file():
        raise FrozenArtifactDrift(f"{what} is absent at {path}; it is installed, never regenerated")
    actual = file_sha256(path)
    if actual != str(pinned_sha256).strip().lower():
        raise FrozenArtifactDrift(
            f"{what} at {path} hashes to {actual[:16]}… but the countersigned preregistration pins "
            f"{str(pinned_sha256)[:16]}…; a generated replacement, an empty file, a normalized CSV, a "
            f"reordered JSON or a reserialized copy is not equivalent unless its byte hash is exact")
    return actual


#: The construction identities a deployment manifest must carry — ADR 0048 (8).
#:
#: ``store_identity_sha256`` is the sixth identity ADR 0048 (8) enumerates, and it is deliberately
#: NOT in this tuple. A deployment manifest is finalized before observation #1; a store identity does
#: not exist until a session performs its reads. Requiring it here would force the generator to invent
#: one, which is precisely the "faithful attestation to hand-made evidence" the deployment-identity
#: module exists to prevent. It is instead required in OBSERVATION evidence, where it is real — see
#: :func:`require_observation_identities`. A manifest MAY still declare it (a per-session manifest
#: legitimately can), and when it does, it is verified against the session's actual value rather than
#: trusted.
REQUIRED_MANIFEST_IDENTITIES = (
    "base_corpus_sha256",
    "ordered_delta_manifest_sha256s",
    "governed_universe_sha256",
    "actions_manifest_sha256",
    "tickers_manifest_sha256",
    "corpus_manifest_sha256",
)

#: The digest-valued keys of the base-plus-delta block. Split out so the Layer 2 path can name its
#: own without either set silently acquiring the other's fields.
BASE_MANIFEST_DIGEST_IDENTITIES = (
    "base_corpus_sha256", "governed_universe_sha256", "actions_manifest_sha256",
    "tickers_manifest_sha256", "corpus_manifest_sha256",
)

#: What a deployment manifest must declare for a Layer 2 reconstruction — ADR 0048 as amended.
#:
#: ⚠ There is deliberately no `base_corpus_sha256`, no `base_coverage_through` and no
#: `ordered_delta_manifest_sha256s`: a reconstruction has none of them, and a deployment manifest that
#: declared them would be describing a construction that does not exist. Coverage is declared as
#: `governed_coverage_through`, which is what it actually is.
REQUIRED_LAYER2_MANIFEST_IDENTITIES = (
    "corpus_construction_kind",
    "construction_schema_version",
    "corpus_manifest_sha256",
    "source_vintage_sha256",
    "governed_coverage_through",
    "governed_universe_sha256",
    "store_file_sha256",
    "supersedes_corpus_manifest_sha256",
    "countersignature_sha256",
)

LAYER2_MANIFEST_DIGEST_IDENTITIES = (
    "corpus_manifest_sha256", "source_vintage_sha256", "governed_universe_sha256",
    "store_file_sha256", "supersedes_corpus_manifest_sha256", "countersignature_sha256",
)

#: Both identities are mandatory in every observation, and neither substitutes for the other.
REQUIRED_OBSERVATION_IDENTITIES = ("corpus_manifest_sha256", "store_identity_sha256")

_IDENTITY_TOKEN = object()


class IdentitySource(StrEnum):
    """Where an identity was derived from. Carried with the value so independence is a property of
    the object rather than a claim about it."""
    GOVERNED_CONSTRUCTION_MANIFEST = "GOVERNED_CONSTRUCTION_MANIFEST"
    STREAMED_CONSUMED_ROWS = "STREAMED_CONSUMED_ROWS"


@dataclass(frozen=True)
class BoundIdentity:
    """A digest that knows how it was produced.

    Independence between the two observation identities is enforced STRUCTURALLY, by construction,
    not by comparing their values. Two SHA-256 strings being unequal proves nothing about where they
    came from: a defect that hashed two different wrappers around the same underlying declaration
    would produce unequal digests and sail through a value comparison. What must be true is that one
    is recomputed from the canonical governed construction and the other comes only from the streamed
    value-level row digest — so that is what is checked.
    """
    value: str
    source: IdentitySource

    def __post_init__(self) -> None:
        if getattr(self, "_token", None) is not _IDENTITY_TOKEN:
            raise ManifestIdentityConflict(
                "a BoundIdentity may only be produced by construction_identity() or "
                "consumed_rows_identity(); a hand-built one carries no provenance")


def _issue(value: str, source: IdentitySource) -> BoundIdentity:
    identity = BoundIdentity.__new__(BoundIdentity)
    object.__setattr__(identity, "_token", _IDENTITY_TOKEN)
    object.__setattr__(identity, "value", value)
    object.__setattr__(identity, "source", source)
    return identity


def construction_identity(manifest: CorpusManifest | Layer2CorpusManifest) -> BoundIdentity:
    """RECOMPUTED from the canonical governed construction manifest. It cannot be sourced from the
    store because nothing about the store is an input to it.

    Either governed construction kind may issue it: both recompute their identity from their own
    canonical manifest bytes, which is the property that makes the identity independent of the store.
    """
    if not isinstance(manifest, CorpusManifest | Layer2CorpusManifest):
        raise ManifestIdentityConflict(
            f"the construction identity must be recomputed from a governed corpus manifest, not from "
            f"{type(manifest).__name__}")
    return _issue(manifest.corpus_manifest_sha256, IdentitySource.GOVERNED_CONSTRUCTION_MANIFEST)


def consumed_rows_identity(finality: Any) -> BoundIdentity:
    """Taken ONLY from the existing streamed value-level row digest, off the finality evidence that
    computed it. Handing this the construction manifest is a type error, not a value that happens to
    look wrong."""
    from app.validation.data_finality import DataFinalityEvidence

    if not isinstance(finality, DataFinalityEvidence):
        raise ManifestIdentityConflict(
            f"the value-level store identity must come from DataFinalityEvidence, not from "
            f"{type(finality).__name__}; it is a property of what the session READ")
    return _issue(finality.store_identity_sha256, IdentitySource.STREAMED_CONSUMED_ROWS)


def require_declared_identities(
    declared: Any,
    *,
    computed: dict[str, Any],
    required: tuple[str, ...] = REQUIRED_MANIFEST_IDENTITIES,
    sha256_keys: tuple[str, ...] = BASE_MANIFEST_DIGEST_IDENTITIES,
    list_keys: tuple[str, ...] = ("ordered_delta_manifest_sha256s",),
) -> dict[str, Any]:
    """Reject a deployment manifest whose corpus identities are missing or conflict with the
    identities computed from the artifacts actually installed.

    The three key sets are parameters rather than constants so a Layer 2 reconstruction can state its
    own — a reconstruction has no base and no delta list, and demanding them here would refuse a valid
    construction for lacking fields it never had. The defaults are the base-plus-delta contract, so
    that call site is unchanged.
    """
    if not isinstance(declared, dict):
        raise ManifestIdentityConflict(
            "the deployment manifest carries no corpus identity block; a session cannot record which "
            "governed construction it was authorized to use")
    # An EMPTY delta list is a legitimate construction, not a missing field: observation #1 runs on a
    # base whose coverage already reaches the session, with no deltas yet. Treating [] as absent would
    # refuse the first observation the program ever takes.
    missing = [k for k in required if declared.get(k) in (None, "")]
    if missing:
        raise ManifestIdentityConflict(
            f"the deployment manifest's corpus identity block is incomplete; missing {sorted(missing)}")

    for key in sha256_keys:
        if not _is_sha256(declared.get(key)):
            raise ManifestIdentityConflict(
                f"the deployment manifest declares {key}={declared.get(key)!r}, which is not a "
                f"sha256 digest")
    for key in list_keys:
        ordered = declared.get(key)
        if not isinstance(ordered, list) or not all(_is_sha256(x) for x in ordered):
            raise ManifestIdentityConflict(
                f"the deployment manifest declares {key} that is not a list of sha256 digests")

    conflicts = []
    for key, value in computed.items():
        if key not in declared:
            raise ManifestIdentityConflict(
                f"the deployment manifest declares no {key}, so the construction it authorized "
                f"cannot be compared with the one assembled")
        want = list(value) if isinstance(value, tuple) else value
        got = declared[key]
        if isinstance(want, str) and isinstance(got, str):
            want, got = want.lower(), got.lower()
        if want != got:
            conflicts.append(f"{key}: manifest={got!r} assembled={want!r}")
    if conflicts:
        raise ManifestIdentityConflict(
            "the deployment manifest and the assembled construction disagree — "
            + "; ".join(sorted(conflicts)))
    return dict(declared)


def require_observation_identities(evidence: Any, *, construction: BoundIdentity,
                                   consumed: BoundIdentity) -> dict[str, Any]:
    """Require BOTH identities in an observation, each matching the value its own source produced.

    They are not aliases and neither substitutes for the other (ADR 0048 (7)): the first proves which
    construction was authorized, the second proves the consumed rows did not move during execution.

    Independence is enforced by PROVENANCE, not by value. Requiring the two digests to differ would
    be the wrong proof twice over — unequal values do not establish separate derivation, and a defect
    hashing two different wrappers around one declaration would pass such a check. So each argument
    must be a `BoundIdentity` carrying the correct source, which only its own factory can issue.

    Equality of the two digests is astronomically unlikely and is RECORDED as an audit condition. It
    is not a refusal: with provenance enforced, equal values would be a coincidence rather than a
    substitution, and refusing on it would stop a governed session for the wrong reason.
    """
    if not isinstance(construction, BoundIdentity) or \
            construction.source is not IdentitySource.GOVERNED_CONSTRUCTION_MANIFEST:
        raise ManifestIdentityConflict(
            "the construction identity was not recomputed from the governed construction manifest")
    if not isinstance(consumed, BoundIdentity) or \
            consumed.source is not IdentitySource.STREAMED_CONSUMED_ROWS:
        raise ManifestIdentityConflict(
            "the value-level store identity did not come from the streamed consumed-row digest")

    if not isinstance(evidence, dict):
        raise ManifestIdentityConflict("the observation carries no identity block")
    missing = [k for k in REQUIRED_OBSERVATION_IDENTITIES if evidence.get(k) in (None, "")]
    if missing:
        raise ManifestIdentityConflict(
            f"the observation is missing {sorted(missing)}; both the construction identity and the "
            f"value-level store identity are mandatory in every observation")
    if evidence["corpus_manifest_sha256"] != construction.value:
        raise ManifestIdentityConflict(
            f"the observation declares corpus_manifest_sha256 "
            f"{str(evidence['corpus_manifest_sha256'])[:16]}… but the session assembled "
            f"{construction.value[:16]}…")
    if evidence["store_identity_sha256"] != consumed.value:
        raise ManifestIdentityConflict(
            f"the observation declares store_identity_sha256 "
            f"{str(evidence['store_identity_sha256'])[:16]}… but the session read "
            f"{consumed.value[:16]}…")

    out: dict[str, Any] = {k: str(evidence[k]) for k in REQUIRED_OBSERVATION_IDENTITIES}
    out["identity_sources"] = {"corpus_manifest_sha256": str(construction.source),
                               "store_identity_sha256": str(consumed.source)}
    if construction.value == consumed.value:
        # Recorded, never refused. Provenance already proves they were derived separately.
        out["audit_condition"] = "IDENTITIES_COINCIDENTALLY_EQUAL"
    return out
