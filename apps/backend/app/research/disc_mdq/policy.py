"""MDQ exploration policy — the pre-read embargo for DISC-MDQ-001.

The architecture this implements, and the one it deliberately refuses:

    DISC candidate symbols
      -> MdqExplorationPolicy          (decide, before anything is opened)
      -> AuthorizedScope               (an explicit allow-set)
      -> MdqFeatureReader              (can only open what the scope allows)
      -> derived features -> DISC enrichment

**Not**: read the whole corpus, compute everything, then delete AMZN/TSLA/…
afterwards. Deleting after the fact is not quarantine — the analyst has already
seen the data, and no amount of downstream filtering un-sees it.

Every decision is fail-closed. If the policy cannot *prove* a (symbol, date)
pair is outside the holdout, it denies.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import structlog

from app.research.disc_mdq.spec import (
    HOLDOUT_ARTIFACT_ID,
    PERIOD_HOLDOUT_DAYS,
    PERIOD_HOLDOUT_UNSTAMPED,
    POLICY_VERSION,
    REVIEW_D0,
    REVIEW_END_EXCLUSIVE,
    Decision,
    ReadPurpose,
    period_holdout_bounds,
)

logger = structlog.get_logger(__name__)


class PolicyError(RuntimeError):
    """The policy cannot be constructed or cannot decide safely."""


class UnauthorizedReadError(RuntimeError):
    """A read was attempted outside the authorized scope."""


@dataclass(frozen=True)
class ReviewWindow:
    """The governed 60-day review window and the period holdout inside it."""

    d0: date
    end_exclusive: date
    period_holdout_days: int = PERIOD_HOLDOUT_DAYS

    def __post_init__(self) -> None:
        if self.end_exclusive <= self.d0:
            raise PolicyError(f"review window end {self.end_exclusive} must be after D0 {self.d0}")
        if self.period_holdout_days <= 0:
            raise PolicyError(
                f"period_holdout_days must be positive, got {self.period_holdout_days}"
            )
        span = (self.end_exclusive - self.d0).days
        if self.period_holdout_days >= span:
            raise PolicyError(
                f"period holdout ({self.period_holdout_days}d) would consume the whole "
                f"{span}d review window"
            )

    @property
    def holdout_start(self) -> date:
        return period_holdout_bounds(self.end_exclusive, self.period_holdout_days)[0]

    @property
    def holdout_end_exclusive(self) -> date:
        return self.end_exclusive

    def contains(self, session_date: date) -> bool:
        return self.d0 <= session_date < self.end_exclusive

    def in_period_holdout(self, session_date: date) -> bool:
        return self.holdout_start <= session_date < self.holdout_end_exclusive

    @classmethod
    def governed(cls) -> ReviewWindow:
        """The stamped window from the Program Start Record (D0 = 2026-08-19)."""
        return cls(d0=REVIEW_D0, end_exclusive=REVIEW_END_EXCLUSIVE)


@dataclass(frozen=True)
class PolicyDecision:
    """One (symbol, session_date) verdict, with the reason recorded."""

    symbol: str
    session_date: date
    purpose: ReadPurpose
    decision: Decision

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOWED


@dataclass(frozen=True)
class AuthorizedScope:
    """An explicit allow-set. The reader accepts nothing else.

    ``denials`` is retained in full so the discovery ledger can record what was
    *not* examined and why — a program that silently drops names cannot later
    show it honoured the quarantine.
    """

    purpose: ReadPurpose
    window: ReviewWindow
    pairs: frozenset[tuple[str, date]]
    denials: tuple[PolicyDecision, ...]
    policy_version: str = POLICY_VERSION
    universe_sha256: str | None = None
    holdout_sha256: str | None = None
    _fingerprint: str = field(default="", repr=False)

    def contains(self, symbol: str, session_date: date) -> bool:
        return (symbol, session_date) in self.pairs

    def symbols_for(self, session_date: date) -> frozenset[str]:
        return frozenset(s for s, d in self.pairs if d == session_date)

    def dates(self) -> frozenset[date]:
        return frozenset(d for _, d in self.pairs)

    @property
    def is_empty(self) -> bool:
        return not self.pairs

    def denials_by_decision(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in self.denials:
            counts[d.decision.value] = counts.get(d.decision.value, 0) + 1
        return counts

    def fingerprint(self) -> str:
        """Stable hash of the allow-set, for provenance on every read result."""
        if self._fingerprint:
            return self._fingerprint
        payload = json.dumps(
            {
                "purpose": self.purpose.value,
                "policy_version": self.policy_version,
                "d0": self.window.d0.isoformat(),
                "end_exclusive": self.window.end_exclusive.isoformat(),
                "pairs": sorted(f"{s}|{d.isoformat()}" for s, d in self.pairs),
                "universe_sha256": self.universe_sha256,
                "holdout_sha256": self.holdout_sha256,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256_lf(path: Path) -> str:
    """SHA-256 of the file's **LF-normalised** bytes.

    The holdout rule pins ``sha256(universe_symbols_file_LF)``, and every
    governed hash in this program is derived from the LF form (the Git blob).
    A Windows checkout stores these files with CRLF, so hashing raw bytes gives
    a different digest on the developer's laptop than on the Linux box — the
    control would fail closed on one and pass on the other. Normalising here is
    what makes the pin mean the same thing everywhere.
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_holdout_artifact(path: Path) -> dict[str, Any]:
    """Load and sanity-check the frozen holdout artifact.

    ⚠ The artifact still carries ``period_holdout_dates =
    "STAMPED_AT_FIRST_ADMISSIBLE_CAPTURE"``. D0 happened on 2026-08-19 and the
    concrete dates were stamped in the Program Start Record, but **this file was
    never updated**. We therefore do not read the period holdout from it; the
    caller supplies the governed window and we cross-check where we can. If a
    future version of the artifact does carry concrete dates, they are checked
    against the derived bounds and a mismatch is fatal.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("artifact") != HOLDOUT_ARTIFACT_ID:
        raise PolicyError(
            f"{path} is not the {HOLDOUT_ARTIFACT_ID} artifact "
            f"(got artifact={data.get('artifact')!r})"
        )
    symbols = data.get("holdout_symbols")
    if not isinstance(symbols, list) or not symbols:
        raise PolicyError(f"{path} carries no holdout_symbols")
    return data


def check_period_holdout_claim(artifact: dict[str, Any], window: ReviewWindow) -> str:
    """Reconcile the artifact's period-holdout field with the governed window.

    Returns the provenance string recorded on the scope. Raises if the artifact
    states concrete dates that disagree with the frozen rule — that would mean
    two governing sources disagree about what is quarantined, which is not
    something to paper over.
    """
    claim = artifact.get("period_holdout_dates")
    if claim == PERIOD_HOLDOUT_UNSTAMPED:
        logger.warning(
            "mdq_holdout_artifact_unstamped",
            artifact=HOLDOUT_ARTIFACT_ID,
            derived_start=window.holdout_start.isoformat(),
            derived_end_exclusive=window.holdout_end_exclusive.isoformat(),
            note=(
                "period_holdout_dates was never stamped after D0; using the frozen "
                "rule applied to the governed review window"
            ),
        )
        return "derived_from_governed_review_window_artifact_unstamped"

    derived = (window.holdout_start, window.holdout_end_exclusive)

    if isinstance(claim, dict):
        # The stamped form. Bounds are named explicitly rather than written as a
        # bare "A..B" range, because the inclusive/exclusive reading of such a
        # range differs by a day at each end - the defect registration section
        # 8.2 ruling 4 exists to correct. All three bounds are cross-checked.
        try:
            start = date.fromisoformat(str(claim["start_inclusive"]))
            end_excl = date.fromisoformat(str(claim["end_exclusive"]))
        except (KeyError, ValueError) as exc:
            raise PolicyError(
                f"stamped period_holdout_dates is malformed ({exc!r}); refusing to guess "
                "which dates are quarantined"
            ) from exc

        if (start, end_excl) != derived:
            raise PolicyError(
                "holdout artifact period disagrees with the frozen rule: artifact states "
                f"[{start}, {end_excl}), rule derives [{derived[0]}, {derived[1]})"
            )

        end_incl_raw = claim.get("end_inclusive")
        if end_incl_raw is not None:
            end_incl = date.fromisoformat(str(end_incl_raw))
            if end_incl != end_excl - timedelta(days=1):
                raise PolicyError(
                    f"stamped period is internally inconsistent: end_inclusive {end_incl} "
                    f"is not one day before end_exclusive {end_excl}"
                )
        return "artifact_stamped_and_matches_rule"

    if isinstance(claim, str) and ".." in claim:
        # Legacy bare-range form, retained so an older artifact still validates.
        raw_start, raw_end = (part.strip() for part in claim.split("..", 1))
        stated = (date.fromisoformat(raw_start), date.fromisoformat(raw_end))
        if stated != derived:
            raise PolicyError(
                "holdout artifact period disagrees with the frozen rule: artifact "
                f"states {stated[0]}..{stated[1]}, rule derives "
                f"{derived[0]}..{derived[1]}"
            )
        return "artifact_stamped_and_matches_rule"

    raise PolicyError(
        f"unrecognised period_holdout_dates value {claim!r}; refusing to guess "
        "which dates are quarantined"
    )


class MdqExplorationPolicy:
    """Decides, before any corpus file is opened, what exploration may read."""

    def __init__(
        self,
        *,
        universe_symbols: Iterable[str],
        holdout_symbols: Iterable[str],
        window: ReviewWindow,
        universe_sha256: str | None = None,
        holdout_sha256: str | None = None,
        period_holdout_provenance: str = "derived_from_governed_review_window",
    ) -> None:
        self.universe = frozenset(s.upper() for s in universe_symbols)
        self.holdout = frozenset(s.upper() for s in holdout_symbols)
        self.window = window
        self.universe_sha256 = universe_sha256
        self.holdout_sha256 = holdout_sha256
        self.period_holdout_provenance = period_holdout_provenance

        if not self.universe:
            raise PolicyError("universe_symbols is empty; refusing to authorize anything")
        if not self.holdout:
            raise PolicyError(
                "holdout_symbols is empty; a policy with no symbol quarantine is not "
                "the DISC-MDQ-001 policy"
            )
        stray = self.holdout - self.universe
        if stray:
            raise PolicyError(
                f"holdout symbols are not in the MDQ universe: {sorted(stray)} — the "
                "holdout is drawn FROM the universe, so this means the two artifacts "
                "are out of sync"
            )

    # --- construction -------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        *,
        universe_symbols_path: Path,
        holdout_path: Path,
        window: ReviewWindow | None = None,
    ) -> MdqExplorationPolicy:
        """Build from the frozen config artifacts, verifying they agree."""
        window = window or ReviewWindow.governed()

        universe = json.loads(universe_symbols_path.read_text(encoding="utf-8"))
        if not isinstance(universe, list):
            raise PolicyError(f"{universe_symbols_path} must contain a JSON array")
        universe_sha = _sha256_lf(universe_symbols_path)

        artifact = load_holdout_artifact(holdout_path)
        holdout_sha = _sha256_lf(holdout_path)

        # The holdout artifact pins the universe file it was drawn from. If the
        # universe has since changed, the holdout draw no longer describes a
        # 20% quarantine of the live universe — fail closed rather than
        # quarantine the wrong ten names.
        pinned = artifact.get("universe_symbols_sha256")
        if isinstance(pinned, str) and pinned != universe_sha:
            raise PolicyError(
                "holdout artifact was drawn from a different universe file: artifact "
                f"pins {pinned}, {universe_symbols_path.name} hashes to {universe_sha}"
            )

        provenance = check_period_holdout_claim(artifact, window)

        return cls(
            universe_symbols=universe,
            holdout_symbols=[str(s) for s in artifact["holdout_symbols"]],
            window=window,
            universe_sha256=universe_sha,
            holdout_sha256=holdout_sha,
            period_holdout_provenance=provenance,
        )

    # --- decisions ----------------------------------------------------------

    def can_read(self, symbol: str, session_date: date, purpose: ReadPurpose) -> PolicyDecision:
        """Decide a single (symbol, session_date) pair. Fail-closed throughout."""
        if not isinstance(purpose, ReadPurpose):
            # An unknown purpose is not a reason to guess. Notably, holdout
            # evaluation is deliberately not a ReadPurpose member.
            raise PolicyError(
                f"unknown read purpose {purpose!r}; exploration is the only sanctioned "
                "purpose, and holdout evaluation is a separate explicit act"
            )

        sym = symbol.upper()

        def verdict(decision: Decision) -> PolicyDecision:
            return PolicyDecision(
                symbol=sym,
                session_date=session_date,
                purpose=purpose,
                decision=decision,
            )

        # 1. Outside MDQ's universe: not observable, not a demotion.
        if sym not in self.universe:
            return verdict(Decision.UNAVAILABLE_NOT_IN_UNIVERSE)

        # 2. Symbol quarantine, checked before anything date-related so a
        #    holdout name is denied for the right reason on every date.
        if sym in self.holdout:
            return verdict(Decision.DENIED_HOLDOUT_SYMBOL)

        # 3. Outside the governed review window.
        if not self.window.contains(session_date):
            return verdict(Decision.DENIED_OUTSIDE_REVIEW_WINDOW)

        # 4. Period quarantine.
        if self.window.in_period_holdout(session_date):
            return verdict(Decision.DENIED_HOLDOUT_PERIOD)

        return verdict(Decision.ALLOWED)

    def authorize(
        self,
        symbols: Iterable[str],
        session_dates: Iterable[date],
        purpose: ReadPurpose = ReadPurpose.EXPLORATION,
    ) -> AuthorizedScope:
        """Produce the allow-set the reader will be constructed with."""
        dates = sorted(set(session_dates))
        syms = sorted({s.upper() for s in symbols})

        allowed: set[tuple[str, date]] = set()
        denials: list[PolicyDecision] = []
        for sym in syms:
            for d in dates:
                decision = self.can_read(sym, d, purpose)
                if decision.allowed:
                    allowed.add((sym, d))
                else:
                    denials.append(decision)

        scope = AuthorizedScope(
            purpose=purpose,
            window=self.window,
            pairs=frozenset(allowed),
            denials=tuple(denials),
            universe_sha256=self.universe_sha256,
            holdout_sha256=self.holdout_sha256,
        )
        logger.info(
            "mdq_exploration_authorized",
            purpose=purpose.value,
            requested_symbols=len(syms),
            requested_dates=len(dates),
            authorized_pairs=len(scope.pairs),
            denials=scope.denials_by_decision(),
            period_holdout_provenance=self.period_holdout_provenance,
            scope_fingerprint=scope.fingerprint(),
        )
        return scope
