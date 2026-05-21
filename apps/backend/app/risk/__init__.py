"""Risk engine: pre-trade gating + post-trade halt detection.

Per ADR 0002 the engine is the only path through which an OrderRequest is
converted into an Order that can be submitted to a broker. There is no fast
path; there is no bypass.
"""

from app.risk.engine import RiskEngine
from app.risk.reason_codes import ReasonCode
from app.risk.types import OrderRequest, RiskOutcome

__all__ = ["OrderRequest", "ReasonCode", "RiskEngine", "RiskOutcome"]
