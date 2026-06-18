"""Monitor layer: continuous revalidation + Research Alerts (P10 Phase 2 §4)."""

from app.research.monitor.revalidation import (
    ACTIVE_DEPLOYMENT_STATES,
    DEFAULT_WATCHES,
    RevalidationWatch,
    revalidate,
)

__all__ = ["revalidate", "RevalidationWatch", "DEFAULT_WATCHES", "ACTIVE_DEPLOYMENT_STATES"]
