"""§3.1 dataset contract — a frozen declarative artifact (scoping memo §6.2).

The contract is frozen **before any analysis**. Its terms are the §3.1 list:
date range, target trustworthy PIT event-days (≥250, preferred 500+), source /
vendor, survivorship rules, corporate-action handling, PIT rules, and the
minimum analyzable sample.

``source_vendor`` is an **unset owner decision** by design: the approved DOCX
contains zero feed-identity language (scoping memo §3), so choosing IEX vs SIP
vs anything else is a pre-execution governed decision recorded outside the
DOCX. The harness therefore defaults the term to the
:data:`UNSET_OWNER_DECISION` sentinel and reports the contract incomplete until
the owner sets every term. An incomplete contract keeps the verdict seam at
``NOT_EVALUABLE`` (see ``thresholds``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

#: Sentinel for a §3.1 term whose value is an owner decision not yet made.
UNSET_OWNER_DECISION = "UNSET_OWNER_DECISION"

#: §3.1 floor and preference for trustworthy PIT event-days.
TARGET_EVENT_DAYS_MINIMUM = 250
TARGET_EVENT_DAYS_PREFERRED = 500

CONTRACT_SCHEMA = "gapper_stage0/dataset_contract/v1"


@dataclass(frozen=True)
class DatasetContract:
    """Declarative §3.1 dataset contract. Frozen: terms change only by
    constructing a new contract (a new owner decision), never by mutation."""

    #: Inclusive ISO-date pair ("YYYY-MM-DD", "YYYY-MM-DD"); None until decided.
    date_range: tuple[str, str] | None = None
    #: ≥250 trustworthy PIT event-days required, 500+ preferred (§3.1).
    target_event_days: int = TARGET_EVENT_DAYS_MINIMUM
    #: Feed/vendor identity — an OPEN owner decision (scoping memo §3).
    source_vendor: str = UNSET_OWNER_DECISION
    survivorship_rules: str = UNSET_OWNER_DECISION
    corporate_action_handling: str = UNSET_OWNER_DECISION
    pit_rules: str = UNSET_OWNER_DECISION
    #: Minimum analyzable sample after exclusions; None until decided.
    min_analyzable_sample: int | None = None
    schema: str = field(default=CONTRACT_SCHEMA)

    def unset_terms(self) -> list[str]:
        """Names of §3.1 terms still awaiting an owner decision."""
        unset: list[str] = []
        if self.date_range is None:
            unset.append("date_range")
        if self.target_event_days < TARGET_EVENT_DAYS_MINIMUM:
            unset.append("target_event_days")
        for name in (
            "source_vendor",
            "survivorship_rules",
            "corporate_action_handling",
            "pit_rules",
        ):
            value = getattr(self, name)
            if not value or value == UNSET_OWNER_DECISION:
                unset.append(name)
        if self.min_analyzable_sample is None:
            unset.append("min_analyzable_sample")
        return unset

    def is_complete(self) -> bool:
        """True only when every §3.1 term has been set by an owner decision."""
        return not self.unset_terms()

    # ---- serialization ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["date_range"] = list(self.date_range) if self.date_range else None
        return d

    def canonical_json(self) -> str:
        """Deterministic JSON (sorted keys, tight separators) — the hash input."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def sha256(self) -> str:
        """SHA-256 of the canonical JSON — the contract's identity."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DatasetContract:
        raw_range = d.get("date_range")
        date_range: tuple[str, str] | None = None
        if raw_range is not None:
            if len(raw_range) != 2:
                raise ValueError(f"date_range must be a 2-item [start, end], got {raw_range!r}")
            date_range = (str(raw_range[0]), str(raw_range[1]))
        schema = d.get("schema", CONTRACT_SCHEMA)
        if schema != CONTRACT_SCHEMA:
            raise ValueError(f"unknown contract schema {schema!r}, expected {CONTRACT_SCHEMA!r}")
        return cls(
            date_range=date_range,
            target_event_days=int(d.get("target_event_days", TARGET_EVENT_DAYS_MINIMUM)),
            source_vendor=str(d.get("source_vendor", UNSET_OWNER_DECISION)),
            survivorship_rules=str(d.get("survivorship_rules", UNSET_OWNER_DECISION)),
            corporate_action_handling=str(d.get("corporate_action_handling", UNSET_OWNER_DECISION)),
            pit_rules=str(d.get("pit_rules", UNSET_OWNER_DECISION)),
            min_analyzable_sample=(
                None if d.get("min_analyzable_sample") is None else int(d["min_analyzable_sample"])
            ),
            schema=schema,
        )

    @classmethod
    def from_json(cls, text: str) -> DatasetContract:
        return cls.from_dict(json.loads(text))
