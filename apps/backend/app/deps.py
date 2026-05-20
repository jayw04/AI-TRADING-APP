"""FastAPI dependency-injection helpers. Expanded in later phases."""

from app.auth import get_current_user

__all__ = ["get_current_user"]
