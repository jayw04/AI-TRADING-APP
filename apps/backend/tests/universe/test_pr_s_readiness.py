"""PR-S startup readiness (S5.6, gate G-C).

The failure this prevents is a *silent* one: PR S merges, deploys green, and LOW-001 runs
happily with S3-S5 all on their registered-only fallback paths — i.e. with the stranding
defect the whole PR exists to repair still live, and nothing anywhere saying so.

So for safety-critical strategies an ABSENT capability is a startup failure. For everyone
else it is nothing at all: static strategies keep their legacy initialization.

Runtime lookup failures are a different matter and stay fail-closed-to-registered-only
(see test_context_read_authority). Only initialization absence is fatal.
"""

from __future__ import annotations

import pytest

from app.services.paper_strategy_liquidation import PaperLiquidationPolicy
from app.universe.security_identity import (
    PR_S_SAFETY_CRITICAL_STRATEGIES,
    FactorStoreSecurityIdentityResolver,
    PrSCapabilityUnavailable,
    assert_pr_s_capability_ready,
)


class _Provider:
    def __init__(self, ready: bool) -> None:
        self.ready = ready


def test_low_001_is_safety_critical():
    assert "low-volatility" in PR_S_SAFETY_CRITICAL_STRATEGIES


def test_low_001_cannot_start_without_a_provider():
    with pytest.raises(PrSCapabilityUnavailable, match="owned_holdings_provider"):
        assert_pr_s_capability_ready("low-volatility", None)


def test_low_001_cannot_start_with_an_unusable_provider():
    """Injected but unable to answer is not readiness.

    A provider whose identity source is unprovisioned resolves every ticker to None, so
    ownership silently degrades to "nothing is ours" — which reads as healthy and is not.
    """
    with pytest.raises(PrSCapabilityUnavailable, match="security_identity_resolver"):
        assert_pr_s_capability_ready("low-volatility", _Provider(ready=False))


def test_low_001_starts_with_a_ready_provider():
    assert_pr_s_capability_ready("low-volatility", _Provider(ready=True))


def test_paper_capability_is_checked_when_a_policy_is_supplied():
    with pytest.raises(PrSCapabilityUnavailable, match="paper_liquidation_capability"):
        assert_pr_s_capability_ready(
            "low-volatility",
            _Provider(ready=True),
            paper_liquidation_policy=PaperLiquidationPolicy(),
        )
    assert_pr_s_capability_ready(
        "low-volatility",
        _Provider(ready=True),
        paper_liquidation_policy=PaperLiquidationPolicy.for_pr_s(),
    )


@pytest.mark.parametrize(
    "name", ["sector-rotation", "momentum-portfolio", "momentum-daily", "combined-book"]
)
def test_static_strategies_are_unaffected(name):
    """No provider, no readiness requirement, no behaviour change."""
    assert_pr_s_capability_ready(name, None)
    assert_pr_s_capability_ready(name, _Provider(ready=False))


def test_unprovisioned_identity_resolver_reports_not_ready():
    """The concrete adapter's own readiness signal, which the assertion consumes."""
    assert not FactorStoreSecurityIdentityResolver(None).ready
