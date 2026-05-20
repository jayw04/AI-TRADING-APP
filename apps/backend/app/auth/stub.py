from dataclasses import dataclass

from app.config import get_settings


@dataclass(frozen=True)
class CurrentUser:
    id: int
    email: str


def get_current_user() -> CurrentUser:
    settings = get_settings()
    return CurrentUser(id=1, email=settings.dev_user_email)
