"""Tokens for tests, obtained by driving the real gate — never by calling the mint.

An earlier revision of these tests imported `_mint_token` and manufactured "ADMISSIBLE" tokens
directly. That does not exercise the gate; it asserts that a bypass works, and it would keep passing
if `require_admissible` stopped checking the verdict entirely.

So the fixture here stubs the **adjudication** (a controlled §7.1 outcome) and lets
`require_admissible` do its own work: read the verdict, refuse anything that is not ADMISSIBLE, digest
the report, and mint. Everything downstream of the verdict is the real code path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.research.capture.admissibility import Verdict
from app.research.capture.store import FEEDS
from app.research.mdq_eval import gate
from app.research.mdq_eval.authority import APPROVED_COLLECTOR_VERSIONS


@dataclass
class _StubReport:
    """The minimum surface `require_admissible` consumes from an adjudication."""

    verdict: Verdict
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return self.payload


def write_governed_manifests(root: Path | str, session: date) -> None:
    """Write manifests that satisfy the B1a manifest-native check, for BOTH feeds.

    Deliberately real rather than monkeypatched: ``require_admissible`` now verifies what the
    frozen partition actually carries, and a fixture that stubbed that check away would make
    every downstream assertion vacuous — the same "green test that cannot fail" shape the
    mint guard exists to prevent.
    """
    for feed in FEEDS:
        pdir = Path(root) / feed / session.isoformat()
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "manifest.json").write_text(
            json.dumps(
                {
                    "schema": "mdq-capture-manifest/1",
                    "feed": feed,
                    "session": session.isoformat(),
                    "collector_version": APPROVED_COLLECTOR_VERSIONS[0],
                    "frozen_at": "2026-08-27T21:00:00+00:00",
                    "provider": "alpaca",
                    "entitlement": "algo_trader_plus (account-7 login)",
                    "credential_fingerprint": "0" * 12,
                    "account_number": "PA000000",
                    "capture_modes": ["quotes", "bars"],
                    "universe": ["AAA", "BBB"],
                    "universe_sha256": "0" * 64,
                    "files": [
                        {"path": "quotes/samples.jsonl", "sha256": "1" * 64, "bytes": 10},
                        {"path": "bars/bars_1min.parquet", "sha256": "2" * 64, "bytes": 20},
                    ],
                }
            ),
            encoding="utf-8",
        )


@pytest.fixture
def adjudication(monkeypatch):
    """Control what §7.1 returns, then obtain tokens through the real `require_admissible`."""

    state: dict[str, Verdict] = {}

    def _assess(root, session, **_kwargs):
        verdict = state.get("verdict", Verdict.ADMISSIBLE)
        return _StubReport(
            verdict=verdict,
            payload={
                "session": session.isoformat(),
                "verdict": str(verdict),
                "not_passing": [] if verdict is Verdict.ADMISSIBLE else [{"condition": "stub"}],
            },
        )

    monkeypatch.setattr(gate, "assess_partition", _assess)

    class Control:
        @staticmethod
        def set_verdict(verdict: Verdict) -> None:
            state["verdict"] = verdict

        @staticmethod
        def token(root: Path | str, session: date):
            write_governed_manifests(root, session)
            token, _report = gate.require_admissible(root, session, session_close_utc=None)
            return token

        @staticmethod
        def tokens(root: Path | str, sessions):
            return [Control.token(root, s) for s in sessions]

        @staticmethod
        def scope(root: Path | str, sessions):
            """A ValidatedScope obtained the only supported way: through the real scope validator."""
            return gate.validate_tokens(root, list(sessions), Control.tokens(root, sessions))

    return Control
