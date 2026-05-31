"""Alpaca credential loader with paper-default and live-ack gating.

Live mode is intentionally annoying to enable. See docs/runbook/live-mode.md
(landing in a later session) and ADR 0002.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.security import CredentialKind, CredentialStore


@dataclass(frozen=True)
class AlpacaCredentials:
    api_key: str
    api_secret: str
    paper: bool

    @property
    def base_url(self) -> str:
        return (
            "https://paper-api.alpaca.markets"
            if self.paper
            else "https://api.alpaca.markets"
        )


class CredentialsError(RuntimeError):
    """Raised when credentials cannot be loaded safely."""


async def credentials_for_mode(
    mode: str,
    user_id: int,
    session_factory: async_sessionmaker[AsyncSession],
) -> AlpacaCredentials:
    """Build :class:`AlpacaCredentials` for an explicit mode ('paper'|'live'),
    for the given ``user_id``, by reading from the encrypted credential store.

    Used by :class:`app.brokers.registry.BrokerRegistry` to construct one
    adapter per account, selected by the account's ``AccountMode``. Raises
    :class:`CredentialsError` when the requested mode's keys are absent — live
    never silently falls back to paper (same posture as :func:`load_credentials`).

    P5 §4 swapped this function's body from env-var reads to credential-store
    reads. The *shape* of the swap-point is preserved (mode in, AlpacaCredentials
    out), but the function is now **async** because the credential store is async;
    callers propagate the ``await``. The live-activation acknowledgment
    (``WORKBENCH_LIVE_ACK``) gate lives in :func:`load_credentials` only; this
    helper is for adapter construction, and live accounts cannot be created
    until P5 §7.
    """
    m = (mode or "paper").lower()
    if m not in ("paper", "live"):
        raise CredentialsError(
            f"broker mode must be 'paper' or 'live', got '{m}'."
        )

    async with session_factory() as session:
        store = CredentialStore(session)
        if m == "live":
            key = await store.get(user_id, CredentialKind.ALPACA_LIVE_KEY)
            secret = await store.get(user_id, CredentialKind.ALPACA_LIVE_SECRET)
            if not key or not secret:
                raise CredentialsError(
                    f"Live mode requested but ALPACA_LIVE_KEY / "
                    f"ALPACA_LIVE_SECRET are not set for user_id={user_id}. "
                    f"Set them via Settings → Credentials."
                )
            return AlpacaCredentials(api_key=key, api_secret=secret, paper=False)

        # paper
        key = await store.get(user_id, CredentialKind.ALPACA_PAPER_KEY)
        secret = await store.get(user_id, CredentialKind.ALPACA_PAPER_SECRET)
        if not key or not secret:
            raise CredentialsError(
                f"ALPACA_PAPER_KEY / ALPACA_PAPER_SECRET are not set for "
                f"user_id={user_id}. Set them via Settings → Credentials."
            )
        return AlpacaCredentials(api_key=key, api_secret=secret, paper=True)


def load_credentials() -> AlpacaCredentials:
    """Load Alpaca credentials based on configured trading mode.

    - Default mode is 'paper'. Returns paper creds from env.
    - 'live' mode requires WORKBENCH_LIVE_ACK == 'I_UNDERSTAND' AND non-empty
      live keys. Any other condition raises CredentialsError. Live mode does
      NOT silently fall back to paper — that would be worse than failing loudly.
    """
    s = get_settings()
    mode = (s.trading_mode or "paper").lower()

    if mode == "live":
        if s.live_ack != "I_UNDERSTAND":
            raise CredentialsError(
                "Live mode requested but WORKBENCH_LIVE_ACK != 'I_UNDERSTAND'. "
                "See docs/runbook/live-mode.md."
            )
        if not s.alpaca_live_api_key or not s.alpaca_live_api_secret:
            raise CredentialsError(
                "Live mode requested but ALPACA_LIVE_API_KEY / "
                "ALPACA_LIVE_API_SECRET are not set."
            )
        return AlpacaCredentials(
            api_key=s.alpaca_live_api_key,
            api_secret=s.alpaca_live_api_secret,
            paper=False,
        )

    if mode != "paper":
        raise CredentialsError(
            f"WORKBENCH_TRADING_MODE must be 'paper' or 'live', got '{mode}'."
        )

    if not s.alpaca_paper_api_key or not s.alpaca_paper_api_secret:
        raise CredentialsError(
            "ALPACA_PAPER_API_KEY / ALPACA_PAPER_API_SECRET are not set in .env."
        )

    return AlpacaCredentials(
        api_key=s.alpaca_paper_api_key,
        api_secret=s.alpaca_paper_api_secret,
        paper=True,
    )
